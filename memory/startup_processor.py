import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from resona_desktop_pet.config.config_manager import ConfigManager
from resona_desktop_pet.backend.llm_backend import LLMBackend
from resona_desktop_pet.backend.mcp_manager import MCPManager
from .memory_manager import MemoryManager

class StartupProcessor:
    def __init__(self, project_root: Path, config: ConfigManager):
        self.project_root = project_root
        self.config = config
        self.memory_manager = MemoryManager(project_root, config)
    
    async def process_startup(self):
        if not self.config.memory_startup_processing:
            return

        temp_sessions = self.memory_manager.load_temp_session()
        if not temp_sessions:
            return

        print(f"[Memory] Processing {len(temp_sessions)} startup memories...")

        try:
            llm_backend = self._create_startup_llm_backend()

            prompt = self._create_processing_prompt_all(temp_sessions)

            active_pack = getattr(self.config.pack_manager, 'active_pack_id', 'default')
            response = await llm_backend.query(
                prompt,
                pack_id=active_pack,
                source="startup"
            )

            if response.text_display:
                print(f"[Memory] Processing result: {response.text_display[:200]}...")

        except Exception as e:
            print(f"[Memory] Error during startup processing: {e}")
        finally:
            self.memory_manager.delete_temp_session()
            print("[Memory] Startup processing finished")
    
    def _create_startup_llm_backend(self) -> LLMBackend:
        startup_base_url = self.config.memory_startup_base_url
        startup_api_key = self.config.memory_startup_api_key
        startup_model_name = self.config.memory_startup_model_name
        
        class StartupConfig:
            def __init__(self, base_config, base_url, api_key, model_name):
                self.__dict__ = base_config.__dict__.copy()
                self.memory_enabled = True  
                self.memory_force_operation = True
                self._startup_base_url = base_url
                self._startup_api_key = api_key
                self._startup_model_name = model_name
            
            def get_llm_config(self):
                config = self.__dict__['config'].get_llm_config()
                if self._startup_base_url:
                    config['base_url'] = self._startup_base_url
                if self._startup_api_key:
                    config['api_key'] = self._startup_api_key
                if self._startup_model_name:
                    config['model_name'] = self._startup_model_name
                return config
        
        startup_config = StartupConfig(self.config, startup_base_url, startup_api_key, startup_model_name)
        log_path = self.project_root / "logs" / f"startup_{int(time.time())}.log"

        mcp_manager = MCPManager(startup_config)

        return LLMBackend(startup_config, log_path, mcp_manager=mcp_manager)
    
    def _create_processing_prompt_all(self, temp_sessions: List[Dict[str, Any]]) -> str:

        conversation_lines = []
        for i, session in enumerate(temp_sessions, 1):
            user_msg = session.get("user_message", "")
            llm_msg = session.get("llm_response", "")
            conversation_lines.append(f"Turn {i}:")
            conversation_lines.append(f"User: {user_msg}")
            conversation_lines.append(f"Assistant: {llm_msg}")
            conversation_lines.append("")

        conversation_text = "\n".join(conversation_lines)

        prompt = f"""You are a memory processing assistant. Your task is to analyze the conversation history and store important information in long-term memory.

Conversation History:
{conversation_text}

Instructions:
1. Review all the conversations above
2. Identify important facts, preferences, user information, or context that should be remembered
3. Use memory_store tool to save each important piece of information separately
4. If there are conflicting facts (e.g., user said different things at different times), store the most recent one with a note about the change
5. Do not ask for additional input - just store the memories
6. Store facts in a clear, concise format

Examples of what to store:
- User preferences (likes, dislikes, habits)
- Important personal information (name, location if shared)
- Key facts discussed
- Context that would be helpful for future conversations

Use memory_store tool to save each piece of information."""

        return prompt