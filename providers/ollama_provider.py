import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from providers.base import BaseProvider, StreamChunk

logger = logging.getLogger("provider-ollama")

class OllamaProvider(BaseProvider):
    """
    Native Ollama provider for local execution.
    Default endpoint: http://127.0.0.1:11434
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = (self.config.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        self.default_model = self.config.get("model", "").strip() or "qwen2.5:7b"

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "本地 Ollama"

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
            "options": {
                "temperature": temperature
            }
        }
        url = f"{self.base_url}/api/chat"
        timeout = httpx.Timeout(opts.get("timeout", 180.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code >= 400:
                        err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                        logger.error(f"Ollama error {resp.status_code}: {err_text}")
                        yield StreamChunk(error=f"HTTP {resp.status_code}: {err_text}", done=True)
                        return

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            msg = data.get("message", {})
                            content = msg.get("content", "")
                            done = data.get("done", False)

                            yield StreamChunk(
                                content=content,
                                done=done,
                                raw=data
                            )
                            if done:
                                break
                        except Exception as parse_err:
                            logger.debug(f"Failed to parse Ollama line: {line} -> {parse_err}")
            except Exception as e:
                logger.exception(f"Ollama stream exception: {e}")
                yield StreamChunk(error=str(e), done=True)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        opts = options or {}
        model = opts.get("model") or self.default_model
        temperature = opts.get("temperature", 0.3)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        url = f"{self.base_url}/api/chat"
        timeout = httpx.Timeout(opts.get("timeout", 120.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("message", {}).get("content", "").strip()
            else:
                err_text = resp.text
                logger.error(f"Ollama chat failed {resp.status_code}: {err_text}")
                raise RuntimeError(f"Ollama HTTP {resp.status_code}: {err_text}")

    async def list_models(self) -> List[str]:
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                    return models
        except Exception as e:
            logger.warning(f"Failed to list Ollama models from {url}: {e}")
        return []

    async def test_connection(self) -> Dict[str, Any]:
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                    return {
                        "connected": True,
                        "models": models,
                        "message": f"成功连接本地 Ollama！检测到 {len(models)} 个已下载模型"
                    }
                else:
                    return {
                        "connected": False,
                        "models": [],
                        "message": f"连接失败: HTTP {resp.status_code}"
                    }
        except Exception as e:
            return {
                "connected": False,
                "models": [],
                "message": f"无法连接到 Ollama ({self.base_url}): 请确认 Ollama 服务已启动"
            }
