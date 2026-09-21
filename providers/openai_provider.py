import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from providers.base import BaseProvider, StreamChunk

logger = logging.getLogger("provider-openai")

class OpenAICompatibleProvider(BaseProvider):
    """
    Standard OpenAI-compatible provider.
    Supports OpenAI, DeepSeek, OpenRouter, Moonshot, SiliconFlow, vLLM, etc.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = (self.config.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = self.config.get("api_key", "").strip()
        self.default_model = self.config.get("model", "").strip() or "deepseek-chat"

    @property
    def provider_id(self) -> str:
        return "openai_compatible"

    @property
    def display_name(self) -> str:
        return "OpenAI 兼容 (DeepSeek / OpenRouter 等)"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        opts = options or {}
        model = opts.get("model") or self.default_model
        temperature = opts.get("temperature", 0.7)
        max_tokens = opts.get("max_tokens")
        
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        timeout = httpx.Timeout(opts.get("timeout", 120.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                        logger.error(f"OpenAICompatible error {resp.status_code}: {err_text}")
                        yield StreamChunk(error=f"HTTP {resp.status_code}: {err_text}", done=True)
                        return

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            yield StreamChunk(done=True)
                            break
                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content") or ""
                            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                            finish_reason = choice.get("finish_reason")

                            yield StreamChunk(
                                content=content,
                                reasoning_content=reasoning,
                                done=bool(finish_reason and finish_reason != "null"),
                                raw=data
                            )
                        except Exception as parse_err:
                            logger.debug(f"Failed to parse SSE line: {line} -> {parse_err}")
            except Exception as e:
                logger.exception(f"OpenAICompatible request exception: {e}")
                yield StreamChunk(error=str(e), done=True)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        opts = options or {}
        model = opts.get("model") or self.default_model
        temperature = opts.get("temperature", 0.3)
        max_tokens = opts.get("max_tokens")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        timeout = httpx.Timeout(opts.get("timeout", 90.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                return message.get("content", "").strip()
            else:
                err_text = resp.text
                logger.error(f"OpenAICompatible non-stream failed {resp.status_code}: {err_text}")
                raise RuntimeError(f"HTTP {resp.status_code}: {err_text}")

    async def list_models(self) -> List[str]:
        url = f"{self.base_url}/models"
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                    return models
        except Exception as e:
            logger.warning(f"Failed to fetch models from {url}: {e}")
        return []

    async def test_connection(self) -> Dict[str, Any]:
        url = f"{self.base_url}/models"
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                    return {
                        "connected": True,
                        "models": models,
                        "message": f"连接成功！获取到 {len(models)} 个可用模型"
                    }
                else:
                    return {
                        "connected": False,
                        "models": [],
                        "message": f"连接失败: HTTP {resp.status_code} - {resp.text[:150]}"
                    }
        except Exception as e:
            return {
                "connected": False,
                "models": [],
                "message": f"无法连接到端点 ({self.base_url}): {str(e)}"
            }
