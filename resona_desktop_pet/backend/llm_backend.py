import json
import re
from datetime import datetime
from typing import Optional, Callable, Any, List
from pathlib import Path
from dataclasses import dataclass, field

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
        
        self.reconnect()

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

    def _build_messages(self, question: str) -> list:
        messages = []
        system_prompt = self.config.get_prompt()
        
        messages.append({"role": "system", "content": system_prompt})

        processed_question = question
        if self.config.enable_time_context:
            time_info = self._get_precise_time_context()
            processed_question = f"[Local Time: {time_info}]\n{question}"

        raw_history = self.history.get_messages()
        for msg in raw_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": processed_question})
        return messages

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
            messages = self._build_messages(question)
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
