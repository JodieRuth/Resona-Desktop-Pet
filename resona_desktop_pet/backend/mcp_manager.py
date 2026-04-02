import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..cleanup_manager import register_cleanup
from ..config import ConfigManager

logger = logging.getLogger("MCP")


@dataclass
class MCPServerSpec:
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None


class MCPManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.enabled = config.mcp_enabled
        self.server_dir = Path(config.config_path).parent / config.mcp_server_dir
        self.startup_timeout = config.mcp_startup_timeout
        self.max_tool_rounds = config.mcp_max_tool_rounds
        self._exit_stack = AsyncExitStack()
        self._sessions: Dict[str, ClientSession] = {}
        self._tool_index: Dict[str, Dict[str, Any]] = {}
        self._tools_cache: List[Dict[str, Any]] = []
        self._tools_cache_meta: List[Dict[str, Any]] = []
        self._server_has_public: Dict[str, bool] = {}
        self._started = False
        register_cleanup(self.stop_sync)

    def has_tools(self) -> bool:
        return bool(self._tools_cache)

    def get_memory_tools_only(self, pack_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not hasattr(self.config, 'memory_enabled') or not self.config.memory_enabled:
            return []
        
        from memory.memory_manager import MemoryManager
        from pathlib import Path
        project_root = Path(self.config.config_path).parent
        memory_manager = MemoryManager(project_root, self.config)
        
        target_pack_id = pack_id if pack_id else self.config.pack_manager.active_pack_id
        return memory_manager.get_memory_tools(target_pack_id)

    def get_tools(self, public_only: bool = True) -> List[Dict[str, Any]]:
        tools = []
        
        memory_tools = self.get_memory_tools_only()
        tools.extend(memory_tools)
        
        if self.enabled:
            if not public_only:
                tools.extend(self._tools_cache)
            else:
                mcp_tools = [t for t in self._tools_cache if "[PRIVATE]" not in t.get("function", {}).get("description", "")]
                hide_prefixes = self.config.get("MCP", "hide_public_prefixes", "")
                if hide_prefixes:
                    prefixes = [p.strip() for p in hide_prefixes.split(",") if p.strip()]
                    if prefixes:
                        mcp_tools = [t for t in mcp_tools if not any(t.get("function", {}).get("name", "").startswith(p) for p in prefixes)]
                tools.extend(mcp_tools)
        
        return tools

    def get_tool_metadata(self, name: str) -> Dict[str, Any]:
        return self._tool_index.get(name, {})

    def _scan_server_specs(self) -> List[MCPServerSpec]:
        if not self.server_dir.exists():
            return []
        candidates = []
        for path in sorted(self.server_dir.iterdir()):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith(".mcp.json") or name.endswith(".mcp.py") or name.endswith(".mcp.js"):
                candidates.append(path)
        specs: List[MCPServerSpec] = []
        for path in candidates:
            if path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.error(f"[MCP] Failed to parse {path.name}: {e}")
                    continue
                command = data.get("command")
                if not command:
                    logger.error(f"[MCP] Missing command in {path.name}")
                    continue
                args = data.get("args", [])
                if not isinstance(args, list):
                    args = [str(args)]
                env = data.get("env")
                if env is not None and not isinstance(env, dict):
                    env = None
                cwd = data.get("cwd")
                if cwd:
                    cwd_path = Path(cwd)
                    if not cwd_path.is_absolute():
                        cwd_path = (self.server_dir / cwd_path).resolve()
                    cwd = str(cwd_path)
                else:
                    cwd = str(path.parent)

                name = data.get("name") or path.stem
                
                if command == "python":
                    command = sys.executable

                specs.append(MCPServerSpec(name=name, command=command, args=[str(a) for a in args], env=env, cwd=cwd))
            else:
                command = sys.executable if path.suffix == ".py" else "node"
                specs.append(MCPServerSpec(name=path.stem, command=command, args=[str(path)], cwd=str(path.parent)))
        return specs

    async def start(self) -> None:
        if not self.enabled or self._started:
            return
        specs = self._scan_server_specs()
        if not specs:
            logger.info("[MCP] No MCP servers found.")
            self._started = True
            return
        for spec in specs:
            try:
                server_params = StdioServerParameters(
                    command=spec.command,
                    args=spec.args,
                    env=spec.env,
                    cwd=spec.cwd
                )
                read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
                session = await self._exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools_result = await asyncio.wait_for(session.list_tools(), timeout=self.startup_timeout)
                tools = tools_result.tools or []
                tool_names = []
                for tool in tools:
                    if tool.name in self._tool_index:
                        logger.warning(f"[MCP] Tool name conflict skipped: {tool.name}")
                        continue
                    params = tool.inputSchema or {"type": "object", "properties": {}}
                    if tool.name == "schedule_timer_event":
                        props = params.get("properties")
                        if isinstance(props, dict):
                            props.pop("pack_id", None)
                        req = params.get("required")
                        if isinstance(req, list) and "pack_id" in req:
                            params["required"] = [r for r in req if r != "pack_id"]
                    tool_def = {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": params
                        }
                    }
                    desc = tool.description or ""
                    is_public = "[PUBLIC]" in desc
                    is_subagent = "[SUBAGENT]" in desc
                    if is_public:
                        self._server_has_public[spec.name] = True
                    self._tool_index[tool.name] = {
                        "session": session,
                        "server": spec.name,
                        "public": is_public,
                        "subagent": is_subagent
                    }
                    self._tools_cache.append(tool_def)
                    self._tools_cache_meta.append({
                        "tool": tool_def,
                        "server": spec.name,
                        "public": is_public,
                        "subagent": is_subagent
                    })
                    tool_names.append(tool.name)
                self._sessions[spec.name] = session
                logger.info(f"[MCP] Server ready: {spec.name} tools={tool_names}")
            except Exception as e:
                logger.error(f"[MCP] Server failed: {spec.name} error={e}")
        
        if self._tools_cache:
            logger.info("=== MCP SERVERS METADATA ===")
            for tool in self._tools_cache:
                func = tool.get("function", {})
                name = func.get("name")
                desc = func.get("description")
                server_name = self._tool_index.get(name, {}).get("server", "unknown")
                logger.info(f"Tool: {name} (Server: {server_name}) - {desc}")
            logger.info("============================")
        else:
            logger.warning("[MCP] No tools available after startup.")

        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self._exit_stack.aclose()
        finally:
            self._sessions.clear()
            self._tool_index.clear()
            self._tools_cache.clear()
            self._tools_cache_meta.clear()
            self._server_has_public.clear()
            self._started = False

    def stop_sync(self) -> None:
        if not self._started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.stop())
            return
        loop.create_task(self.stop())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if name.startswith("memory_") and hasattr(self.config, 'memory_enabled') and self.config.memory_enabled:
            from memory.memory_manager import MemoryManager
            from pathlib import Path
            project_root = Path(self.config.config_path).parent
            memory_manager = MemoryManager(project_root, self.config)
            
            pack_id = arguments.get("pack_id", self.config.pack_manager.active_pack_id)
            session_id = f"session_{pack_id}"
            
            try:
                if name == "memory_store":
                    content = arguments.get("content", "")
                    memory_uuid = memory_manager.store_memory(pack_id, content, session_id)
                    result = {"ok": True, "memory_id": memory_uuid, "content": content, "message": f"Memory stored successfully: {content[:100]}{'...' if len(content) > 100 else ''}"}
                elif name == "memory_delete":
                    memory_uuid = arguments.get("uuid", "")
                    success = memory_manager.delete_memory(pack_id, memory_uuid)
                    result = {"ok": success, "memory_id": memory_uuid, "message": "Memory deleted successfully" if success else "Memory not found"}
                elif name == "memory_update":
                    memory_uuid = arguments.get("uuid", "")
                    content = arguments.get("content", "")
                    success = memory_manager.update_memory(pack_id, memory_uuid, content)
                    result = {"ok": success, "memory_id": memory_uuid, "content": content, "message": f"Memory updated successfully: {content[:100]}{'...' if len(content) > 100 else ''}" if success else "Memory not found"}
                elif name == "memory_search":
                    query = arguments.get("query", "")
                    limit = arguments.get("limit", 5)
                    results = memory_manager.search_memories(pack_id, query, limit)
                    result = {"ok": True, "results": results, "count": len(results)}
                else:
                    raise RuntimeError(f"Unknown memory tool: {name}")
                
                import json
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"[Memory] Error calling tool {name}: {e}")
                import json
                return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        
        entry = self._tool_index.get(name)
        if not entry:
            raise RuntimeError(f"MCP tool not found: {name}")
        session: ClientSession = entry["session"]
        try:
            result = await session.call_tool(name, arguments)
            logger.info(f"[MCP] Raw tool result for {name}: {result}")
            formatted = self._format_result_content(result)
            if not formatted:
                logger.warning(f"[MCP] Tool {name} returned empty content. Raw: {result}")
            return formatted
        except Exception as e:
            logger.error(f"[MCP] Error calling tool {name}: {e}")
            raise

    def _format_result_content(self, result: Any) -> str:
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")
        
        if content is None:
            if hasattr(result, "text"):
                return getattr(result, "text")
            return str(result) if result is not None else ""

        if isinstance(content, list):
            parts = []
            for item in content:
                item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
                item_text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                
                if item_type == "text" and item_text is not None:
                    parts.append(item_text)
                elif item_text is not None:
                    parts.append(item_text)
                else:
                    parts.append(str(item))
            return "\n".join([p for p in parts if p is not None]).strip()
        
        if isinstance(content, str):
            return content.strip()
            
        return str(content).strip()
