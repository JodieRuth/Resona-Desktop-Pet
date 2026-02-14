import json
import re
import asyncio
import base64
import io
from datetime import datetime
from typing import Optional, Callable, Any, List
from pathlib import Path
from dataclasses import dataclass, field

import requests
import psutil
import win32con
import win32gui
import win32api
import win32process
from PIL import ImageGrab

from ..config import ConfigManager


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


class LLMBackend:

    def __init__(self, config: ConfigManager, log_path: Optional[Path] = None):
        self.config = config
        self.log_path = log_path
        self.history = ConversationHistory(max_rounds=config.max_rounds)
        
        self._openai_client = None
        self._claude_client = None
        self._gemini_safety = {}
        self._active_model_name = None
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
        
        print(f"[LLM] Initializing persistent client for: {model_name}")

        try:
            if model_type == 5:
                import google.generativeai as genai
                from google.generativeai.types import HarmCategory, HarmBlockThreshold
                
                genai.configure(api_key=api_key)
                self._gemini_safety = {
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            
            elif model_type == "local" or model_type in [1, 2, 4, 6, 7, 8, 9]:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                
            elif model_type == 3:
                import anthropic
                self._claude_client = anthropic.AsyncAnthropic(api_key=api_key)
                
            self._active_model_name = model_name
            print(f"[LLM] Client metadata initialized.")
        except Exception as e:
            print(f"[LLM] Failed to pre-initialize client: {e}")

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

    def _build_messages(self, question: str, extra_context: Optional[str] = None) -> list:
        messages = []
        system_prompt = self.config.get_prompt()
        
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

    async def _get_ocr_context(self) -> Optional[str]:
        ocr_config = self.config.get_ocr_config()
        ocr_active = ocr_config.get("enabled") and not self._ocr_disabled
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
            process_items = self._get_visible_processes_on_active_monitor()
            if process_items:
                process_text = "\n".join([f"- {item}" for item in process_items])
                blocks.append(f"Foreground Monitor Processes:\n{process_text}")

        if not blocks:
            return None
        return "\n\n".join(blocks)

    def _parse_response(self, text: str) -> LLMResponse:
        response = LLMResponse(raw_response=text)
        print(f"[LLM] Raw response from API: {text[:200]}...")

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
            print(f"[LLM] JSON Parse Error: {e} | Candidate: {json_str[:100]}...")
            response.error = f"JSON parsing failed: {str(e)}"
            return response

    def _log_interaction(self, request_data: Any, response_raw: str):
        import logging
        llm_logger = logging.getLogger("LLM")
        
        if not self.log_path: return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n={'='*20} {ts} {'='*20}\n")
                f.write(f"[REQUEST]\n{json.dumps(request_data, ensure_ascii=False, indent=2)}\n")
                f.write(f"[RESPONSE RAW]\n{response_raw}\n")
            
            llm_logger.info(f"Interaction logged to {self.log_path.name}")
        except Exception as e:
            print(f"[LLM] Logging error: {e}")

    async def query_openai_compatible(
        self,
        messages: list,
        model_name: str,
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 500
    ) -> LLMResponse:
        try:
            if not self._openai_client: self.reconnect()
            self._log_interaction(messages, "WAITING...")
            
            response = await self._openai_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            

            if isinstance(response, str):
                return LLMResponse(error=f"API returned an unexpected string. Please check if the Base URL is correct (Current: {self.config.get_llm_config().get('base_url')}). Error preview: {response[:100]}")

            if not hasattr(response, 'choices') or not response.choices:
                return LLMResponse(error="Abnormal API response: missing 'choices' field.")

            message = response.choices[0].message
            raw_text = message.content or ""
            reasoning = getattr(message, "reasoning_content", "")
            
            for tag in ["think", "thinking"]:
                if f"<{tag}>" in raw_text:
                    pattern = rf"<{tag}>(.*?)</{tag}>"
                    match = re.search(pattern, raw_text, re.DOTALL)
                    if match:
                        reasoning += match.group(1).strip()
                        raw_text = re.sub(pattern, "", raw_text, flags=re.DOTALL).strip()

            log_content = f"[Reasoning]\n{reasoning}\n\n[Content]\n{raw_text}" if reasoning else raw_text
            self._log_interaction("DONE", log_content)
            
            if not raw_text: return LLMResponse(error="Empty response from LLM", thought=reasoning)

            llm_resp = self._parse_response(raw_text)
            llm_resp.thought = reasoning
            return llm_resp
        except Exception as e:
            self._log_interaction("EXCEPTION", str(e))
            return LLMResponse(error=str(e))

    async def query_gemini(
        self,
        messages: list,
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 500
    ) -> LLMResponse:
        try:
            import google.generativeai as genai
            
            gemini_msgs = []
            system_instruction = ""
            
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                elif msg["role"] == "user":
                    gemini_msgs.append({"role": "user", "parts": [msg["content"]]})
                elif msg["role"] == "assistant":
                    gemini_msgs.append({"role": "model", "parts": [msg["content"]]})

            model = genai.GenerativeModel(
                model_name=self._active_model_name,
                safety_settings=self._gemini_safety,
                system_instruction=system_instruction
            )
            
            response = await model.generate_content_async(
                gemini_msgs,
                generation_config={"temperature": temperature, "top_p": top_p, "max_output_tokens": max_tokens}
            )
            
            if not response.candidates: return LLMResponse(error="Empty response")
            
            raw_text = response.text
            thought_text = ""
            for tag in ["think", "thinking"]:
                pattern = rf"<{tag}>(.*?)</{tag}>"
                match = re.search(pattern, raw_text, re.DOTALL)
                if match:
                    thought_text += match.group(1).strip()
                    raw_text = re.sub(pattern, "", raw_text, flags=re.DOTALL).strip()

            self._log_interaction("DONE", f"[Thought]\n{thought_text}\n\n[Text]\n{raw_text}")
            llm_resp = self._parse_response(raw_text)
            llm_resp.thought = thought_text
            return llm_resp
        except Exception as e:
            self._log_interaction("EXCEPTION", str(e))
            return LLMResponse(error=str(e))

    async def query_claude(
        self,
        messages: list,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> LLMResponse:
        try:
            if not self._claude_client: self.reconnect()
            
            system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
            filtered_messages = [m for m in messages if m["role"] != "system"]
            
            self._log_interaction(filtered_messages, "WAITING...")
            response = await self._claude_client.messages.create(
                model=model_name,
                system=system_prompt,
                messages=filtered_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            final_text = "".join(block.text for block in response.content if block.type == "text")
            thought_text = "".join(block.thinking for block in response.content if block.type == "thinking")

            self._log_interaction("DONE", f"[Thought]\n{thought_text}\n\n[Text]\n{final_text}")
            llm_resp = self._parse_response(final_text)
            llm_resp.thought = thought_text
            return llm_resp
        except Exception as e:
            self._log_interaction("EXCEPTION", str(e))
            return LLMResponse(error=str(e))

    async def query(self, question: str) -> LLMResponse:
        llm_config = self.config.get_llm_config()
        model_type = llm_config["model_type"]
        model_name = llm_config["model_name"]
        
        if model_name != self._active_model_name:
            self.reconnect()

        try:
            ocr_context = await self._get_ocr_context()
            messages = self._build_messages(question, ocr_context)
            processed_question = messages[-1]["content"]

            if model_type == "local" or model_type in [1, 2, 4, 6, 7, 8, 9]:
                response = await self.query_openai_compatible(
                    messages, model_name,
                    temperature=llm_config.get("temperature", 0.7),
                    top_p=llm_config.get("top_p", 1.0),
                    max_tokens=llm_config.get("max_tokens", 500)
                )
            elif model_type == 5:
                response = await self.query_gemini(
                    messages,
                    temperature=llm_config.get("temperature", 0.7),
                    top_p=llm_config.get("top_p", 1.0),
                    max_tokens=llm_config.get("max_tokens", 500)
                )
            elif model_type == 3:
                response = await self.query_claude(
                    messages, model_name,
                    temperature=llm_config.get("temperature", 0.7),
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
