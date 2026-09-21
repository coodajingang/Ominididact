import os
import sys
import importlib
import logging
from typing import Dict, Any, Type, Optional, List, Union
from providers.base import BaseProvider
from providers.openai_provider import OpenAICompatibleProvider
from providers.ollama_provider import OllamaProvider
from providers.lm_studio_provider import LMStudioProvider
from providers.nvidia_provider import NvidiaProvider
from providers.amd_provider import AMDProvider
from providers.cloudflare_provider import CloudflareProvider

logger = logging.getLogger("provider-registry")

_PROVIDER_CLASSES: Dict[str, Type[BaseProvider]] = {
    "openai_compatible": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
    "lm_studio": LMStudioProvider,
    "nvidia": NvidiaProvider,
    "amd": AMDProvider,
    "cloudflare": CloudflareProvider,
}

_PLUGINS_DISCOVERED = False

def register_provider(provider_id: str, provider_cls: Type[BaseProvider]):
    """Register a new provider class into the registry."""
    _PROVIDER_CLASSES[provider_id] = provider_cls
    logger.info(f"Registered provider: '{provider_id}' ({provider_cls.__name__})")

def discover_plugins():
    """
    Dynamically discover and load external plugins from the plugins/ directory.
    If the plugins/ folder does not exist or any plugin fails, it gracefully continues.
    """
    global _PLUGINS_DISCOVERED
    if _PLUGINS_DISCOVERED:
        return
    _PLUGINS_DISCOVERED = True

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    plugins_dir = os.path.join(base_dir, "plugins")
    if not os.path.isdir(plugins_dir):
        return

    # Ensure base_dir is in sys.path
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    for item in os.listdir(plugins_dir):
        plugin_path = os.path.join(plugins_dir, item)
        if os.path.isdir(plugin_path) and not item.startswith((".", "_")):
            init_file = os.path.join(plugin_path, "__init__.py")
            if os.path.exists(init_file):
                try:
                    module_name = f"plugins.{item}"
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, "register"):
                        mod.register(register_provider)
                        logger.info(f"Successfully loaded and registered plugin: {item}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin {item}: {e}")

def get_registered_providers() -> Dict[str, Type[BaseProvider]]:
    discover_plugins()
    return _PROVIDER_CLASSES

def list_available_providers() -> List[Dict[str, str]]:
    """Returns a list of available providers for UI dropdowns."""
    providers = get_registered_providers()
    result = []
    for pid, cls in providers.items():
        try:
            inst = cls()
            result.append({
                "id": pid,
                "name": inst.display_name
            })
        except Exception:
            result.append({
                "id": pid,
                "name": pid
            })
    return result

def get_provider(settings_or_source: Union[str, Dict[str, Any]], custom_config: Optional[Dict[str, Any]] = None) -> BaseProvider:
    """
    Factory to obtain a provider instance from either settings dict or provider id.
    Supports backward compatibility with 'proxy' and 'lm_studio'.
    """
    discover_plugins()
    
    if isinstance(settings_or_source, str):
        source = settings_or_source
        settings = custom_config or {}
    else:
        settings = settings_or_source or {}
        source = settings.get("llm_source") or settings.get("provider") or "openai_compatible"

    # Backward compatibility mappings
    if source == "proxy":
        source = "openai_compatible"
    elif source in ("lmstudio", "lm-studio"):
        source = "lm_studio"

    # Read saved providers configuration from config.json
    try:
        import config_store
        global_cfg = config_store.load_config()
        saved_providers = global_cfg.get("providers", {})
        saved = saved_providers.get(source, {})
    except Exception:
        saved = {}

    # Provider specific config extraction (passed settings take precedence over saved config)
    provider_config: Dict[str, Any] = {}
    
    if source in ("openai_compatible", "openai"):
        provider_config = {
            "base_url": settings.get("openai_base_url") or settings.get("base_url") or saved.get("base_url") or "https://api.openai.com/v1",
            "api_key": settings.get("openai_api_key") or settings.get("api_key") or saved.get("api_key") or "",
            "model": settings.get("openai_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or "gpt-4o"
        }
    elif source in ("deepseek", "deepseek_r1"):
        provider_config = {
            "base_url": settings.get("deepseek_base_url") or settings.get("base_url") or saved.get("base_url") or "https://api.deepseek.com/v1",
            "api_key": settings.get("deepseek_api_key") or settings.get("api_key") or saved.get("api_key") or "",
            "model": settings.get("deepseek_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or "deepseek-chat"
        }
    elif source == "ollama":
        provider_config = {
            "base_url": settings.get("ollama_base_url") or settings.get("base_url") or saved.get("base_url") or "http://127.0.0.1:11434",
            "model": settings.get("ollama_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or "qwen2.5:7b"
        }
    elif source == "lm_studio":
        provider_config = {
            "base_url": settings.get("lm_studio_base_url") or settings.get("base_url") or saved.get("base_url") or "http://127.0.0.1:1234/v1",
            "api_key": settings.get("lm_studio_api_key") or settings.get("api_key") or saved.get("api_key") or "lm-studio",
            "model": settings.get("lm_studio_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or ""
        }
    elif source == "nvidia":
        provider_config = {
            "base_url": settings.get("nvidia_base_url") or settings.get("base_url") or saved.get("base_url") or "https://integrate.api.nvidia.com/v1",
            "api_key": settings.get("nvidia_api_key") or settings.get("api_key") or saved.get("api_key") or "",
            "model": settings.get("nvidia_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or "meta/llama-3.3-70b-instruct"
        }
    elif source == "amd":
        provider_config = {
            "base_url": settings.get("amd_base_url") or settings.get("base_url") or saved.get("base_url") or "http://127.0.0.1:8000/v1",
            "api_key": settings.get("amd_api_key") or settings.get("api_key") or saved.get("api_key") or "",
            "model": settings.get("amd_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
        }
    elif source == "cloudflare":
        provider_config = {
            "account_id": settings.get("cf_account_id") or settings.get("account_id") or saved.get("account_id") or "",
            "api_token": settings.get("cf_api_token") or settings.get("api_token") or settings.get("api_key") or saved.get("api_token") or "",
            "base_url": settings.get("cf_base_url") or settings.get("base_url") or saved.get("base_url") or "",
            "model": settings.get("cf_model") or settings.get("model") or saved.get("model") or settings.get("text_model") or "@cf/meta/llama-3.1-8b-instruct"
        }
    elif source in _PROVIDER_CLASSES:
        merged = dict(saved)
        merged.update(settings)
        provider_config = merged

    provider_cls = _PROVIDER_CLASSES.get(source)
    if not provider_cls:
        # Fallback to OpenAICompatible
        logger.warning(f"Unknown provider '{source}', falling back to 'openai_compatible'")
        provider_cls = OpenAICompatibleProvider
        
    return provider_cls(provider_config)


def get_provider_for_task(
    task: str,
    settings: Dict[str, Any],
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
) -> BaseProvider:
    """
    Helper to resolve and instantiate provider and model for a specific task:
    - task: 'translation', 'chat', or 'vlm'
    - settings: Study settings (either doc-level or global)
    - provider_override / model_override: optional explicit overrides
    """
    # 1. Resolve Provider
    target_provider = provider_override or settings.get(f"{task}_provider")
    if not target_provider or target_provider == "default":
        target_provider = settings.get(f"default_{task}_provider")
    if not target_provider or target_provider == "default":
        target_provider = settings.get("llm_source") or "openai_compatible"

    # 2. Resolve Model
    target_model = model_override or settings.get(f"{task}_model")
    if not target_model or target_model == "default":
        target_model = settings.get(f"default_{task}_model")
    if not target_model:
        if task == "vlm":
            target_model = settings.get("vlm_model", "") or settings.get("default_vlm_model", "")
        else:
            target_model = settings.get("text_model", "") or settings.get("default_translation_model", "")

    # Auto-infer provider if model is distinctive or provider was left as default
    if target_model and (not target_provider or target_provider in ("openai_compatible", "default")):
        if target_model.startswith("@cf/"):
            target_provider = "cloudflare"

    custom_cfg = {}
    if target_model:
        custom_cfg["model"] = target_model

    return get_provider(target_provider, custom_cfg)

