import logging
from typing import Dict, Any, Optional
from providers.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger("provider-amd")

class AMDProvider(OpenAICompatibleProvider):
    """
    AMD AI / ROCm provider (vLLM / TGI on AMD Instinct or local ROCm).
    Default endpoint: http://127.0.0.1:8000/v1 (or custom ROCm/vLLM server)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        amd_cfg = dict(cfg)
        if not amd_cfg.get("base_url"):
            amd_cfg["base_url"] = "http://127.0.0.1:8000/v1"
        if not amd_cfg.get("model"):
            amd_cfg["model"] = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
        super().__init__(amd_cfg)

    @property
    def provider_id(self) -> str:
        return "amd"

    @property
    def display_name(self) -> str:
        return "AMD AI / ROCm (本地或云端实例)"

    async def test_connection(self) -> Dict[str, Any]:
        res = await super().test_connection()
        if res.get("connected"):
            models = res.get("models", [])
            return {
                "connected": True,
                "models": models,
                "message": f"成功连接 AMD 推理端点！检测到 {len(models)} 个可用模型"
            }
        else:
            return {
                "connected": False,
                "models": [],
                "message": f"无法连接到 AMD 推理端点 ({self.base_url}): 请确认 ROCm/vLLM 服务已启动"
            }
