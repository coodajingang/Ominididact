import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from providers.base import BaseProvider, StreamChunk

logger = logging.getLogger("provider-custom-gateway")

class CustomGatewayProvider(BaseProvider):
    """
    Example Custom LLM Gateway Provider.
    Demonstrates how to route requests to internal or custom-protocol model gateways.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = (
            self.config.get("proxy_url") or 
            self.config.get("base_url") or 
            "http://127.0.0.1:8000/v1"
        ).rstrip("/")
        self.api_key = (self.config.get("api_key") or "").strip()
        self.default_model = (self.config.get("model") or "").strip() or "custom-model"

    @property
    def provider_id(self) -> str:
        return "custom_gateway"

    @property
    def display_name(self) -> str:
        return "自定义私有网关 (示例插件)"

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

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature
        }
        if "max_tokens" in opts:
            payload["max_tokens"] = opts["max_tokens"]

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        timeout = httpx.Timeout(opts.get("timeout", 120.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    yield StreamChunk(
                        content=f"\n[Custom Gateway Error {resp.status_code}]: {err_body.decode('utf-8', errors='ignore')}",
                        is_final=True
                    )
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            yield StreamChunk(content="", is_final=True)
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            choices = chunk_data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                text = delta.get("content", "")
                                if text:
                                    yield StreamChunk(content=text, is_final=False)
                        except Exception:
                            continue

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        parts = []
        async for chunk in self.stream_chat(messages, options):
            if chunk.content:
                parts.append(chunk.content)
        return "".join(parts)

    async def list_models(self) -> List[str]:
        return [self.default_model]

    async def test_connection(self) -> Dict[str, Any]:
        url = f"{self.base_url}/models"
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return {"connected": True, "message": "成功连接自定义网关服务！"}
                return {"connected": False, "message": f"连接返回状态码 {res.status_code}"}
        except Exception as e:
            return {"connected": False, "message": f"连接失败: {str(e)}"}
