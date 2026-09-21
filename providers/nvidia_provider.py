import logging
from typing import Dict, Any, Optional
from providers.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger("provider-nvidia")

class NvidiaProvider(OpenAICompatibleProvider):
    """
    NVIDIA NIM & API Catalog provider (build.nvidia.com).
    Default endpoint: https://integrate.api.nvidia.com/v1
    Uses API keys typically starting with 'nvapi-'.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        nv_cfg = dict(cfg)
        if not nv_cfg.get("base_url"):
            nv_cfg["base_url"] = "https://integrate.api.nvidia.com/v1"
        if not nv_cfg.get("model"):
            nv_cfg["model"] = "meta/llama-3.3-70b-instruct"
        super().__init__(nv_cfg)

    @property
    def provider_id(self) -> str:
        return "nvidia"

    @property
    def display_name(self) -> str:
        return "NVIDIA NIM (build.nvidia.com)"

    async def test_connection(self) -> Dict[str, Any]:
        res = await super().test_connection()
        if res.get("connected"):
            models = res.get("models", [])
            return {
                "connected": True,
                "models": models,
                "message": f"成功连接 NVIDIA NIM！检测到 {len(models)} 个可用模型"
            }
        else:
            return {
                "connected": False,
                "models": [],
                "message": f"无法连接到 NVIDIA API: {res.get('message', '请检查 nvapi- 密钥是否有效')}"
            }
