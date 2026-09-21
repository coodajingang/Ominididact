import logging
from typing import Dict, Any, Optional
from providers.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger("provider-lmstudio")

class LMStudioProvider(OpenAICompatibleProvider):
    """
    Preset OpenAI-compatible provider for local LM Studio.
    Default endpoint: http://127.0.0.1:1234/v1
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        # Provide LM Studio defaults
        lm_cfg = dict(cfg)
        if not lm_cfg.get("base_url"):
            lm_cfg["base_url"] = "http://127.0.0.1:1234/v1"
        if not lm_cfg.get("api_key"):
            lm_cfg["api_key"] = "lm-studio"
        super().__init__(lm_cfg)

    @property
    def provider_id(self) -> str:
        return "lm_studio"

    @property
    def display_name(self) -> str:
        return "本地 LM Studio"

    async def test_connection(self) -> Dict[str, Any]:
        res = await super().test_connection()
        if res.get("connected"):
            models = res.get("models", [])
            return {
                "connected": True,
                "models": models,
                "message": f"成功连接 LM Studio！检测到 {len(models)} 个可用模型"
            }
        else:
            return {
                "connected": False,
                "models": [],
                "message": f"无法连接到 LM Studio ({self.base_url}): 请确认 LM Studio 本地服务器已开启"
            }
