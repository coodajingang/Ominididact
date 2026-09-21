import json
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
import httpx
from providers.base import BaseProvider, StreamChunk

logger = logging.getLogger("provider-cloudflare")

# 适合每日 10,000 Neurons 免费配额模型（轻量、低神经元消耗，极适合日常中英文献翻译与精读助教）
CF_FREE_RECOMMENDED_MODELS = [
    "@cf/meta/llama-3.1-8b-instruct",                # Meta 经典 8B 通用大模型，高性价比
    "@cf/qwen/qwen2.5-7b-instruct",                  # 强烈推荐：中英互译、学术文献理解与语法剖析极佳
    "@cf/meta/llama-3.2-3b-instruct",                # 超轻量 3B 模型，极省 Neurons
    "@cf/meta/llama-3.2-1b-instruct",                # 极简 1B 模型，超低延迟
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",   # DeepSeek R1 蒸馏 32B，逻辑推理与长难句剖析强
    "@cf/google/gemma-2-2b-it",                      # Google Gemma 2 轻量模型
    "@cf/google/gemma-7b-it",                        # Google Gemma 7B
    "@cf/meta/m2m100-1.2b",                          # Meta 专有多语言机器翻译模型
]

# 旗舰大算力模型（70B+ 参数，消耗神经元较快，建议开通 Workers Paid 每月 1000 万额度使用）
CF_PAID_HEAVY_MODELS = [
    "@cf/meta/llama-3.3-70b-instruct",                # 70B 旗舰级模型，表达最地道丰富
    "@cf/deepseek-ai/deepseek-r1-distill-llama-70b",  # 70B 满血推理大模型
    "@cf/meta/llama-3-70b-instruct",                 # Llama 3 70B
]

# 视觉与多模态模型（支持图表与公式识别 OCR）
CF_VISION_MODELS = [
    "@cf/meta/llama-3.2-11b-vision-instruct",         # 视觉图文解析（推荐）
    "@cf/llava-hf/llava-1.5-7b-hf",
]

POPULAR_CF_MODELS = CF_FREE_RECOMMENDED_MODELS + CF_PAID_HEAVY_MODELS + CF_VISION_MODELS


class CloudflareProvider(BaseProvider):
    """
    Cloudflare Workers AI Provider.
    Directly uses Cloudflare's official REST API:
    POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
    GET  https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        cfg = self.config or {}
        self.account_id = str(cfg.get("account_id") or cfg.get("cf_account_id") or "").strip()
        self.api_token = str(cfg.get("api_token") or cfg.get("api_key") or cfg.get("cf_api_token") or "").strip()
        self.default_model = str(cfg.get("model") or cfg.get("cf_model") or "@cf/meta/llama-3.1-8b-instruct").strip()
        base_url = str(cfg.get("base_url") or cfg.get("cf_base_url") or "").strip().rstrip("/")
        if not base_url and self.account_id:
            base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai"
        self.base_url = base_url

    @property
    def api_key(self) -> str:
        return self.api_token

    @property
    def provider_id(self) -> str:
        return "cloudflare"

    @property
    def display_name(self) -> str:
        return "Cloudflare Workers AI"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _get_run_url(self, model: str) -> str:
        clean_model = model.strip().lstrip("/")
        if self.base_url:
            if self.base_url.endswith("/ai/run") or self.base_url.endswith("/run"):
                return f"{self.base_url}/{clean_model}"
            if self.base_url.endswith("/ai/v1"):
                return f"{self.base_url}/chat/completions"
            return f"{self.base_url}/run/{clean_model}"
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{clean_model}"

    def _get_models_search_url(self) -> str:
        if self.base_url and "api.cloudflare.com" not in self.base_url:
            return f"{self.base_url}/models/search"
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/models/search"

    def _filter_and_sort_models(self, raw_models: List[str]) -> List[str]:
        if not raw_models:
            return POPULAR_CF_MODELS

        ordered = []
        for m in CF_FREE_RECOMMENDED_MODELS:
            if m in raw_models and m not in ordered:
                ordered.append(m)
        for m in CF_PAID_HEAVY_MODELS:
            if m in raw_models and m not in ordered:
                ordered.append(m)
        for m in CF_VISION_MODELS:
            if m in raw_models and m not in ordered:
                ordered.append(m)

        for m in raw_models:
            lower = m.lower()
            if any(k in lower for k in ["bge-", "embed", "whisper", "speech", "stable-diffusion", "flux", "resnet"]):
                continue
            if m not in ordered:
                ordered.append(m)

        return ordered or POPULAR_CF_MODELS

    async def list_models(self) -> List[str]:
        if not self.account_id or not self.api_token:
            return POPULAR_CF_MODELS

        search_url = self._get_models_search_url()
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(search_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        raw_list = data.get("result", [])
                        model_names = [m["name"] for m in raw_list if isinstance(m, dict) and m.get("name")]
                        if model_names:
                            return self._filter_and_sort_models(model_names)
        except Exception as e:
            logger.warning(f"Failed to fetch Cloudflare models from {search_url}: {e}")

        return POPULAR_CF_MODELS

    async def test_connection(self) -> Dict[str, Any]:
        if not self.account_id or not self.api_token or "YOUR_ACCOUNT_ID" in self.account_id:
            return {
                "connected": False,
                "models": POPULAR_CF_MODELS,
                "message": "请先填写 Cloudflare Account ID 和 API Token"
            }

        headers = self._get_headers()

        # Step 1: Query official Cloudflare model search API
        search_url = self._get_models_search_url()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(search_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        raw_list = data.get("result", [])
                        model_names = [m["name"] for m in raw_list if isinstance(m, dict) and m.get("name")]
                        ordered = self._filter_and_sort_models(model_names)
                        return {
                            "connected": True,
                            "models": ordered,
                            "message": f"成功连接 Cloudflare Workers AI！在线检测到 {len(ordered)} 个可用模型"
                        }
                    else:
                        errors = data.get("errors", [])
                        err_str = "; ".join([e.get("message", str(e)) for e in errors]) if errors else ""
                        logger.warning(f"Cloudflare models/search returned success=false: {err_str}")
        except Exception as e:
            logger.warning(f"Cloudflare models/search request failed: {e}")

        # Step 2: Fallback to active model inference test with ai/run (identical to user's working curl!)
        target_model = self.default_model or "@cf/meta/llama-3.1-8b-instruct"
        run_url = self._get_run_url(target_model)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                test_payload = {
                    "prompt": "ping",
                    "max_tokens": 5
                }
                resp = await client.post(run_url, json=test_payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return {
                            "connected": True,
                            "models": POPULAR_CF_MODELS,
                            "message": f"成功连接 Cloudflare Workers AI！（通过 {target_model} 推理连通验证）"
                        }
                    if resp.status_code == 403 and ("5016" in resp.text or "agree" in resp.text.lower()):
                        logger.info(f"Model Agreement required during test_connection for {target_model}. Submitting 'agree'...")
                        agreed = await self._handle_agreement(target_model)
                        if agreed:
                            return {
                                "connected": True,
                                "models": POPULAR_CF_MODELS,
                                "message": f"成功连接 Cloudflare Workers AI！（已自动签署并同意 {target_model} 协议）"
                            }
                    errors = data.get("errors", [])
                    err_str = "; ".join([e.get("message", str(e)) for e in errors]) if errors else "API 响应异常"
                    return {
                        "connected": False,
                        "models": POPULAR_CF_MODELS,
                        "message": f"Cloudflare 认证或调用异常: {err_str}"
                    }
                else:
                    if resp.status_code == 403 and ("5016" in resp.text or "agree" in resp.text.lower()):
                        logger.info(f"Model Agreement required during test_connection for {target_model}. Submitting 'agree'...")
                        agreed = await self._handle_agreement(target_model)
                        if agreed:
                            return {
                                "connected": True,
                                "models": POPULAR_CF_MODELS,
                                "message": f"成功连接 Cloudflare Workers AI！（已自动签署并同意 {target_model} 协议）"
                            }
                    return {
                        "connected": False,
                        "models": POPULAR_CF_MODELS,
                        "message": f"连接失败 (HTTP {resp.status_code}): {resp.text[:120]}"
                    }
        except Exception as e:
            return {
                "connected": False,
                "models": POPULAR_CF_MODELS,
                "message": f"无法连接到端点 ({run_url}): {str(e)}"
            }

    async def _handle_agreement(self, model: str) -> bool:
        """
        Meta's Llama 3.2 license policy requires submitting {'prompt': 'agree'}
        before first use of models like @cf/meta/llama-3.2-11b-vision-instruct.
        Submits 'agree' to Cloudflare to bind the community license to this account.
        """
        run_url = self._get_run_url(model)
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(run_url, json={"prompt": "agree"}, headers=headers)
                if resp.status_code == 200:
                    logger.info(f"Successfully accepted Meta license agreement for model {model}")
                    return True
                else:
                    logger.warning(f"License agreement for {model} returned HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Exception submitting license agreement for {model}: {e}")
        return False

    async def _process_stream_lines(self, resp: httpx.Response) -> AsyncGenerator[StreamChunk, None]:
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
                # Cloudflare native stream chunk: {"response": "..."}
                content = data.get("response")
                reasoning = None
                if content is None and "choices" in data:
                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content") or ""
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")

                if content is not None or reasoning is not None:
                    yield StreamChunk(
                        content=content or "",
                        reasoning_content=reasoning,
                        done=False,
                        raw=data
                    )
            except Exception as parse_err:
                logger.debug(f"Failed to parse SSE line: {line} -> {parse_err}")

        yield StreamChunk(done=True)

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        opts = options or {}
        model = opts.get("model") or self.default_model or "@cf/meta/llama-3.1-8b-instruct"
        temperature = opts.get("temperature", 0.7)
        max_tokens = opts.get("max_tokens")

        run_url = self._get_run_url(model)
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        timeout = httpx.Timeout(opts.get("timeout", 120.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream("POST", run_url, json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                        # Check if Meta License Agreement is required
                        if resp.status_code == 403 and ("5016" in err_text or "agree" in err_text.lower()):
                            logger.info(f"Model Agreement required for {model}. Automatically submitting 'agree'...")
                            agreed = await self._handle_agreement(model)
                            if agreed:
                                logger.info(f"Agreement accepted for {model}. Retrying stream request...")
                                async with client.stream("POST", run_url, json=payload, headers=headers) as retry_resp:
                                    if retry_resp.status_code < 400:
                                        async for chunk in self._process_stream_lines(retry_resp):
                                            yield chunk
                                        return
                                    err_text = (await retry_resp.aread()).decode("utf-8", errors="ignore")

                        logger.error(f"Cloudflare stream error {resp.status_code}: {err_text}")
                        yield StreamChunk(error=f"Cloudflare HTTP {resp.status_code}: {err_text}", done=True)
                        return

                    async for chunk in self._process_stream_lines(resp):
                        yield chunk
            except Exception as e:
                logger.exception(f"Cloudflare stream exception: {e}")
                yield StreamChunk(error=str(e), done=True)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        opts = options or {}
        model = opts.get("model") or self.default_model or "@cf/meta/llama-3.1-8b-instruct"
        temperature = opts.get("temperature", 0.7)
        max_tokens = opts.get("max_tokens")

        run_url = self._get_run_url(model)
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": False,
            "temperature": temperature
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        timeout = httpx.Timeout(opts.get("timeout", 120.0), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(run_url, json=payload, headers=headers)
            # Check if Meta License Agreement is required
            if resp.status_code == 403 and ("5016" in resp.text or "agree" in resp.text.lower()):
                logger.info(f"Model Agreement required for {model}. Automatically submitting 'agree'...")
                agreed = await self._handle_agreement(model)
                if agreed:
                    logger.info(f"Agreement accepted for {model}. Retrying chat request...")
                    resp = await client.post(run_url, json=payload, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    result = data.get("result", {})
                    if isinstance(result, dict):
                        return result.get("response", "")
                    elif isinstance(result, str):
                        return result
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]
                errors = data.get("errors", [])
                if errors:
                    err_str = "; ".join([e.get("message", str(e)) for e in errors])
                    raise RuntimeError(f"Cloudflare AI error: {err_str}")
                return ""
            else:
                err_text = resp.text
                logger.error(f"Cloudflare non-stream failed {resp.status_code}: {err_text}")
                raise RuntimeError(f"Cloudflare HTTP {resp.status_code}: {err_text}")
