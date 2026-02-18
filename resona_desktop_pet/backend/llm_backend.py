import json
import re
import asyncio
import base64
import io
import logging
from datetime import datetime
from typing import Optional, Callable, Any, List, Dict, Tuple
from pathlib import Path
from dataclasses import dataclass, field

import requests
import psutil
import win32con
import win32gui
import win32api
import win32process
from PIL import ImageGrab
from litellm import acompletion

from ..config import ConfigManager
from .mcp_manager import MCPManager


@dataclass
class LLMResponse:
    emotion: str = "<E:smile>"
    text_display: str = ""
    text_tts: str = ""
    thought: str = ""
    raw_response: str = ""
    error: Optional[str] = None


@dataclass
class ConversationHistory:
    max_rounds: int = 14
    history: list = field(default_factory=list)

    def add(self, role: str, content: str) -> None:
        if self.max_rounds <= 0:
            self.history = []
            return
        self.history.append({"role": role, "content": content})
        limit = self.max_rounds * 2
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    def get_messages(self) -> list:
        return self.history

    def clear(self) -> None:
        self.history.clear()


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [LLM] {message}")


class LLMBackend:

    def __init__(self, config: ConfigManager, log_path: Optional[Path] = None, mcp_manager: Optional[MCPManager] = None):
        self.config = config
        self.log_path = log_path
        self.history = ConversationHistory(max_rounds=config.max_rounds)
        self._mcp_manager = mcp_manager
        
        self._active_model_name = None
        self._active_model_signature = None
        self._ocr_last_text = None
        self._ocr_same_count = 0
        self._ocr_disabled = False
        self._ip_context = None

        if self.config.ocr_enabled:
            self.config.get_ocr_config()
        
        if self.config.enable_ip_context:
            import threading
            threading.Thread(target=self._fetch_ip_context_sync, daemon=True).start()
        
        self.reconnect()

    def _fetch_ip_context_sync(self):
        try:
            response = requests.get("http://ip-api.com/json/?lang=zh-CN", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    ip = data.get("query")
                    country = data.get("country")
                    region = data.get("regionName")
                    city = data.get("city")
                    isp = data.get("isp")
                    self._ip_context = f"{ip} ({country}, {region}, {city}, ISP: {isp})"
                    print(f"[LLM] IP Context initialized: {self._ip_context}")
                else:
                    print(f"[LLM] IP-API error: {data.get('message')}")
        except Exception as e:
            print(f"[LLM] Failed to fetch IP context: {e}")

    def reconnect(self):
        llm_cfg = self.config.get_llm_config()
        model_type = llm_cfg["model_type"]
        model_name = llm_cfg["model_name"]
        api_key = llm_cfg["api_key"]
        base_url = llm_cfg.get("base_url", "")
        
        print(f"[LLM] Initializing LLM session for: {model_name}")
        self._active_model_name = model_name
        self._active_model_signature = (model_type, model_name, api_key, base_url)
        print(f"[LLM] Client metadata initialized.")

    def _get_precise_time_context(self) -> str:
        now = datetime.now()
        weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        weekday = weekday_map[now.weekday()]
        
        hour = now.hour
        if 0 <= hour < 5: period = "深夜"
        elif 5 <= hour < 8: period = "凌晨"
        elif 8 <= hour < 11: period = "早上"
        elif 11 <= hour < 13: period = "中午"
        elif 13 <= hour < 17: period = "下午"
        elif 17 <= hour < 19: period = "傍晚"
        elif 19 <= hour < 23: period = "晚上"
        else: period = "深夜"
        
        return f"{time_str} ({weekday}, {period})"

    def _get_mcp_system_instruction(self) -> str:
        return (
            "If tools are available, use them when needed. "
            "When you call a tool, do not return JSON in that turn. "
            "After tool results are provided, reply with one final JSON only."
        )

    def _extract_tool_calls(self, response: Any) -> List[Any]:
        if isinstance(response, dict):
            choices = response.get("choices", [])
        else:
            choices = getattr(response, "choices", [])
        if not choices:
            return []
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message") or {}
        else:
            message = getattr(first, "message", None) or {}
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls")
        else:
            tool_calls = getattr(message, "tool_calls", None)
        return tool_calls or []

    def _normalize_tool_call(self, tool_call: Any) -> Tuple[Optional[str], Optional[str], Any]:
        if isinstance(tool_call, dict):
            call_id = tool_call.get("id")
            func = tool_call.get("function") or {}
            name = func.get("name")
            arguments = func.get("arguments")
            return call_id, name, arguments
        call_id = getattr(tool_call, "id", None)
        func = getattr(tool_call, "function", None)
        name = getattr(func, "name", None) if func else None
        arguments = getattr(func, "arguments", None) if func else None
        return call_id, name, arguments

    def _build_messages(self, question: str, extra_context: Optional[str] = None) -> list:
        messages = []
        system_prompt = self.config.get_prompt()
        if self._mcp_manager and self._mcp_manager.enabled and self._mcp_manager.has_tools():
            system_prompt = f"{system_prompt}\n\n{self._get_mcp_system_instruction()}"
        
        messages.append({"role": "system", "content": system_prompt})

        question_blocks = []
        if self.config.enable_time_context:
            time_info = self._get_precise_time_context()
            question_blocks.append(f"[Local Time: {time_info}]")
        if self.config.enable_ip_context and self._ip_context:
            question_blocks.append(f"[User IP: {self._ip_context}]")
        sentence_limit = self.config.ocr_sentence_limit
        if sentence_limit > 0:
            question_blocks.append(f"Note: Keep your response under {sentence_limit} sentences and maintain your persona.")
        question_blocks.append(question)
        processed_question = "\n".join(question_blocks)

        raw_history = self.history.get_messages()
        for msg in raw_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        if extra_context:
            messages.append({"role": "user", "content": extra_context})

        messages.append({"role": "user", "content": processed_question})
        return messages

    def _build_messages_with_image(self, question: str, extra_context: Optional[str], image_base64: str) -> list:
        messages = self._build_messages(question, extra_context)
        image_url = f"data:image/png;base64,{image_base64}"
        last_message = messages[-1]
        last_message["content"] = [
            {"type": "text", "text": last_message["content"]},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        return messages

    def _extract_text_content(self, content: Any) -> str:
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return part.get("text", "")
            return ""
        return content if isinstance(content, str) else str(content)

    def _normalize_model_name(self, model_type: Any, model_name: str) -> str:
        if not model_name:
            return model_name
        if "/" in model_name:
            return model_name
        provider = None
        if model_type == "local":
            provider = "openai"
        elif model_type == 1:
            provider = "openai"
        elif model_type == 2:
            provider = "deepseek"
        elif model_type == 3:
            provider = "anthropic"
        elif model_type == 4:
            provider = "moonshot"
        elif model_type == 5:
            provider = "gemini"
        elif model_type == 6:
            provider = "xai"
        elif model_type in [7, 8, 9]:
            provider = "openai"
        if provider:
            return f"{provider}/{model_name}"
        return model_name

    def _extract_litellm_message(self, response: Any) -> tuple[str, str]:
        if isinstance(response, dict):
            choices = response.get("choices", [])
        else:
            choices = getattr(response, "choices", [])
        if not choices:
            return "", ""
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message") or {}
        else:
            message = getattr(first, "message", None) or {}
        if isinstance(message, dict):
            raw_text = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
        else:
            raw_text = getattr(message, "content", "") or ""
            reasoning = getattr(message, "reasoning_content", "") or ""
        if not isinstance(raw_text, str):
            raw_text = self._extract_text_content(raw_text)
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)
        return raw_text, reasoning

    def _get_visible_processes_on_active_monitor(self) -> list:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return []
        active_monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        results = []

        def enum_callback(handle, acc):
            if not win32gui.IsWindowVisible(handle):
                return
            title = win32gui.GetWindowText(handle)
            if not title:
                return
            monitor = win32api.MonitorFromWindow(handle, win32con.MONITOR_DEFAULTTONULL)
            if monitor != active_monitor:
                return
            _, pid = win32process.GetWindowThreadProcessId(handle)
            try:
                proc_name = psutil.Process(pid).name()
            except Exception:
                proc_name = "unknown"
            acc.append(f"{proc_name} | {title}")

        win32gui.EnumWindows(enum_callback, results)
        return sorted(set(results))

    def _prepare_image_base64(self) -> str:
        screenshot = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format="PNG")
        return base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

    def _baidu_ocr(self, image_base64: str, api_key: str, secret_key: str) -> str:
        session = requests.Session()
        session.trust_env = False
        token_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
        token_resp = session.get(token_url, timeout=10)
        if token_resp.status_code != 200:
            raise RuntimeError(token_resp.text)
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError(token_resp.text)
        request_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
        params = {"image": image_base64}
        headers = {"content-type": "application/x-www-form-urlencoded"}
        ocr_resp = session.post(f"{request_url}?access_token={access_token}", data=params, headers=headers, timeout=15)
        if ocr_resp.status_code != 200:
            raise RuntimeError(ocr_resp.text)
        ocr_data = ocr_resp.json()
        words = [item.get("words", "") for item in ocr_data.get("words_result", [])]
        return "\n".join([w for w in words if w])

    def _tencent_ocr(self, image_base64: str, secret_id: str, secret_key: str) -> str:
        try:
            from tencentcloud.common import credential
            from tencentcloud.ocr.v20181119 import ocr_client, models
        except Exception as e:
            raise RuntimeError(f"Tencent OCR SDK not available: {e}")
        cred = credential.Credential(secret_id, secret_key)
        client = ocr_client.OcrClient(cred, "ap-shanghai")
        req = models.GeneralBasicOCRRequest()
        req.ImageBase64 = image_base64
        resp = client.GeneralBasicOCR(req)
        detections = resp.TextDetections or []
        texts = [item.DetectedText for item in detections if getattr(item, "DetectedText", None)]
        return "\n".join(texts)

    def _run_ocr(self, ocr_config: dict) -> str:
        image_base64 = self._prepare_image_base64()
        provider = ocr_config.get("provider")
        if provider == "baidu":
            return self._baidu_ocr(image_base64, ocr_config["api_key"], ocr_config["secret_key"])
        if provider == "tencent":
            return self._tencent_ocr(image_base64, ocr_config["secret_id"], ocr_config["secret_key"])
        raise RuntimeError(f"Unsupported OCR provider: {provider}")

    async def _get_ocr_context(self, ocr_config: Optional[dict] = None) -> Optional[str]:
        if ocr_config is None:
            ocr_config = self.config.get_ocr_config()
        ocr_active = ocr_config.get("enabled") and not self._ocr_disabled and not ocr_config.get("vlm_enabled", False)
        process_active = ocr_config.get("include_process_list", False)

        if not ocr_active and not process_active:
            return None

        blocks = []
        
        if ocr_active:
            try:
                ocr_text = await asyncio.to_thread(self._run_ocr, ocr_config)
                if ocr_text:
                    ocr_text = ocr_text.strip()
                    if ocr_text == self._ocr_last_text:
                        self._ocr_same_count += 1
                    else:
                        self._ocr_same_count = 0
                    self._ocr_last_text = ocr_text

                    if self._ocr_same_count >= 2:
                        self._ocr_disabled = True
                    else:
                        blocks.append(f"OCR Result:\n{ocr_text}")
            except Exception as e:
                print(f"[LLM] OCR Context Error: {e}")

        if process_active:
            try:
                process_items = await asyncio.wait_for(
                    asyncio.to_thread(self._get_visible_processes_on_active_monitor),
                    timeout=5
                )
            except asyncio.TimeoutError:
                process_items = []
            except Exception:
                process_items = []
            if process_items:
                process_text = "\n".join([f"- {item}" for item in process_items])
                blocks.append(f"Foreground Monitor Processes:\n{process_text}")

        if not blocks:
            return None
        return "\n\n".join(blocks)

    def _parse_response(self, text: str) -> LLMResponse:
        response = LLMResponse(raw_response=text)
        log(f"Raw response from API: {text}")

        json_str = text.strip()
        if "```" in json_str:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", json_str, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
        
        if not json_str.startswith("{"):
            match = re.search(r"({.*})", json_str, re.DOTALL)
            if match:
                json_str = match.group(1).strip()

        try:
            data = json.loads(json_str)
            response.emotion = data.get("emotion", "<E:smile>")
            response.text_display = data.get("text_display", "")
            response.text_tts = data.get("text_tts", response.text_display)
            return response
        except json.JSONDecodeError as e:
            log(f"JSON Parse Error: {e} | Candidate: {json_str}")
            response.error = f"JSON parsing failed: {str(e)}"
            return response

    def _log_interaction(self, request_data: Any, response_raw: str):
        import logging
        import copy
        llm_logger = logging.getLogger("LLM")
        
        if not self.log_path: return

        def mask_base64(obj):
            if isinstance(obj, dict):
                new_dict = {}
                for k, v in obj.items():
                    if k == "url" and isinstance(v, str) and v.startswith("data:image/"):
                        new_dict[k] = v[:50] + "... [BASE64 TRUNCATED]"
                    elif k == "data" and isinstance(v, str) and len(v) > 200:
                        new_dict[k] = v[:50] + "... [BASE64 TRUNCATED]"
                    else:
                        new_dict[k] = mask_base64(v)
                return new_dict
            elif isinstance(obj, list):
                return [mask_base64(item) for item in obj]
            return obj

        try:
            safe_data = mask_base64(request_data)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n={'='*20} {ts} {'='*20}\n")
                f.write(f"[REQUEST]\n{json.dumps(safe_data, ensure_ascii=False, indent=2)}\n")
                f.write(f"[RESPONSE RAW]\n{response_raw}\n")
            
            llm_logger.info(f"Interaction logged to {self.log_path.name}")
        except Exception as e:
            print(f"[LLM] Logging error: {e}")

    async def _call_litellm_raw(
        self,
        messages: list,
        model_name: str,
        model_type: Any,
        api_key: str,
        base_url: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 500
    ) -> Tuple[Any, str, str, List[Any]]:
        resolved_model = self._normalize_model_name(model_type, model_name)
        if "gemini-3" in resolved_model.lower() and temperature < 1.0:
            print(f"[LLM] Overriding temperature for {resolved_model}: {temperature} -> 1.0 (Required for Gemini 3)")
            temperature = 1.0
        request_payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens
        }
        if base_url:
            request_payload["base_url"] = base_url
        if tools:
            request_payload["tools"] = tools
            if tool_choice:
                request_payload["tool_choice"] = tool_choice
        self._log_interaction(request_payload, "WAITING...")
        print(f"[LLM] Sending to {resolved_model}")
        response = await acompletion(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            api_key=api_key or None,
            base_url=base_url or None,
            tools=tools or None,
            tool_choice=tool_choice or None
        )
        raw_text, reasoning = self._extract_litellm_message(response)
        for tag in ["think", "thinking"]:
            if f"<{tag}>" in raw_text:
                pattern = rf"<{tag}>(.*?)</{tag}>"
                match = re.search(pattern, raw_text, re.DOTALL)
                if match:
                    reasoning += match.group(1).strip()
                    raw_text = re.sub(pattern, "", raw_text, flags=re.DOTALL).strip()
        tool_calls = self._extract_tool_calls(response)
        log_content = f"[Reasoning]\n{reasoning}\n\n[Content]\n{raw_text}" if reasoning else raw_text
        self._log_interaction("DONE", log_content)
        return response, raw_text, reasoning, tool_calls

    async def _query_litellm(
        self,
        messages: list,
        model_name: str,
        model_type: Any,
        api_key: str,
        base_url: str,
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 500
    ) -> LLMResponse:
        try:
            _, raw_text, reasoning, _ = await self._call_litellm_raw(
                messages,
                model_name,
                model_type,
                api_key,
                base_url,
                tools=None,
                tool_choice=None,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens
            )

            if not raw_text:
                return LLMResponse(error="Empty response from LLM", thought=reasoning)

            llm_resp = self._parse_response(raw_text)
            llm_resp.thought = reasoning
            return llm_resp
        except Exception as e:
            self._log_interaction("EXCEPTION", str(e))
            return LLMResponse(error=str(e))

    async def _query_with_tools(
        self,
        messages: list,
        model_name: str,
        model_type: Any,
        api_key: str,
        base_url: str,
        tools: List[Dict[str, Any]],
        max_tool_rounds: int,
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 500
    ) -> LLMResponse:
        attempted_retry = False
        for _ in range(max_tool_rounds + 1):
            _, raw_text, reasoning, tool_calls = await self._call_litellm_raw(
                messages,
                model_name,
                model_type,
                api_key,
                base_url,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens
            )

            if tool_calls:
                serializable_tool_calls = []
                for tc in tool_calls:
                    if hasattr(tc, "model_dump"):
                        serializable_tool_calls.append(tc.model_dump())
                    elif hasattr(tc, "dict"):
                        serializable_tool_calls.append(tc.dict())
                    elif isinstance(tc, dict):
                         serializable_tool_calls.append(tc)
                    else:
                        serializable_tool_calls.append(dict(tc))
                
                messages.append({"role": "assistant", "content": raw_text or "", "tool_calls": serializable_tool_calls})
                for tool_call in tool_calls:
                    call_id, name, arguments = self._normalize_tool_call(tool_call)
                    if not name:
                        messages.append({"role": "tool", "content": "Tool call missing name.", "tool_call_id": call_id or ""})
                        continue
                    parsed_args: Dict[str, Any] = {}
                    if isinstance(arguments, str):
                        if arguments.strip():
                            try:
                                parsed_args = json.loads(arguments)
                            except Exception as e:
                                parsed_args = {"_error": f"Invalid arguments: {e}", "_raw": arguments}
                    elif isinstance(arguments, dict):
                        parsed_args = arguments
                    
                    try:
                        tool_result = await self._mcp_manager.call_tool(name, parsed_args)
                    except Exception as e:
                        tool_result = f"Tool error: {e}"
                    
                    if not isinstance(tool_result, str):
                        tool_result = str(tool_result)
                    
                    log(f"[LLM] Called tool {name}, result: {tool_result}")
                        
                    messages.append({"role": "tool", "content": tool_result, "tool_call_id": call_id or ""})
                continue

            if raw_text:
                llm_resp = self._parse_response(raw_text)
                llm_resp.thought = reasoning
                if not llm_resp.error:
                    return llm_resp
                if not attempted_retry:
                    attempted_retry = True
                    messages.append({"role": "assistant", "content": raw_text})
                    messages.append({"role": "user", "content": "Your response is not valid JSON. Please return ONLY valid JSON, no other text."})
                    continue
                return llm_resp

            if not attempted_retry:
                attempted_retry = True
                messages.append({"role": "assistant", "content": raw_text or ""})
                messages.append({"role": "user", "content": "Your response is empty. Please return ONLY valid JSON."})
                continue

            return LLMResponse(error="Empty response from LLM")

        return LLMResponse(error="Tool call exceeded max rounds")

    async def query(self, question: str) -> LLMResponse:
        llm_config = self.config.get_llm_config()
        model_type = llm_config["model_type"]
        model_name = llm_config["model_name"]
        api_key = llm_config["api_key"]
        base_url = llm_config.get("base_url", "")
        
        current_signature = (model_type, model_name, api_key, base_url)
        if current_signature != self._active_model_signature:
            self.reconnect()

        try:
            ocr_config = self.config.get_ocr_config()
            ocr_context = await self._get_ocr_context(ocr_config)
            vlm_enabled = ocr_config.get("vlm_enabled", False)
            image_base64 = None
            if vlm_enabled:
                try:
                    image_base64 = await asyncio.wait_for(
                        asyncio.to_thread(self._prepare_image_base64),
                        timeout=10
                    )
                except asyncio.TimeoutError:
                    image_base64 = None
                except Exception:
                    image_base64 = None
            openai_compatible = model_type == "local" or model_type in [1, 2, 4, 6, 7, 8, 9]
            image_capable = openai_compatible or model_type in [3, 5]
            if image_base64 and image_capable:
                messages = self._build_messages_with_image(question, ocr_context, image_base64)
            else:
                messages = self._build_messages(question, ocr_context)
            processed_question = self._extract_text_content(messages[-1]["content"])
            tools: List[Dict[str, Any]] = []
            max_tool_rounds = 0
            if self._mcp_manager and self._mcp_manager.enabled and self._mcp_manager.has_tools():
                tools = self._mcp_manager.get_tools()
                max_tool_rounds = max(self._mcp_manager.max_tool_rounds, 0)
            prompt_parts = []
            if self.config.enable_time_context:
                prompt_parts.append("time")
            if self.config.enable_ip_context and self._ip_context:
                prompt_parts.append("ip")
            if ocr_context:
                if "OCR Result" in ocr_context:
                    prompt_parts.append("ocr")
                if "Foreground Monitor Processes" in ocr_context:
                    prompt_parts.append("process")
                if "OCR Result" not in ocr_context and "Foreground Monitor Processes" not in ocr_context:
                    prompt_parts.append("extra_context")
            if image_base64 and image_capable:
                prompt_parts.append("image")
            if self.history.get_messages():
                prompt_parts.append("history")
            parts_text = ", ".join(prompt_parts) if prompt_parts else "base"
            print(f"[LLM] Prompt built. Parts: {parts_text}")

            supported_types = {"local", 1, 2, 3, 4, 5, 6, 7, 8, 9}
            if model_type in supported_types:
                if tools:
                    response = await self._query_with_tools(
                        messages,
                        model_name,
                        model_type,
                        api_key,
                        base_url,
                        tools=tools,
                        max_tool_rounds=max_tool_rounds,
                        temperature=llm_config.get("temperature", 0.7),
                        top_p=llm_config.get("top_p", 1.0),
                        max_tokens=llm_config.get("max_tokens", 500)
                    )
                else:
                    response = await self._query_litellm(
                        messages,
                        model_name,
                        model_type,
                        api_key,
                        base_url,
                        temperature=llm_config.get("temperature", 0.7),
                        top_p=llm_config.get("top_p", 1.0),
                        max_tokens=llm_config.get("max_tokens", 500)
                    )
            else:
                response = LLMResponse(error=f"Unsupported model type: {model_type}")
        except Exception as e:
            response = LLMResponse(error=f"Request Failed: {e}")

        if not response.error and response.text_display:
            self.history.add("user", processed_question)
            self.history.add("assistant", response.raw_response)

        return response

    def clear_history(self) -> None:
        self.history.clear()
