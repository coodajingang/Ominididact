import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Request
import config_store
import providers

logger = logging.getLogger("study-router-providers")
router = APIRouter()

@router.get("/api/study/providers")
async def get_providers_endpoint():
    """Returns list of registered LLM providers available in the system."""
    return {"code": 200, "data": providers.list_available_providers()}

@router.post("/api/study/providers/test")
async def test_provider_endpoint(request: Request):
    """Tests connectivity and lists models for any configured provider."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    provider_id = body.get("provider") or body.get("llm_source") or "openai_compatible"
    
    # If the request contains a masked key or empty key, load the saved key from config
    raw_api_key = body.get("api_key", "")
    if not raw_api_key or config_store.is_masked_secret(raw_api_key):
        saved_cfg = config_store.load_config().get("providers", {}).get(provider_id, {})
        if saved_cfg.get("api_key"):
            body["api_key"] = saved_cfg["api_key"]

    provider_inst = providers.get_provider(provider_id, body)
    result = await provider_inst.test_connection()
    return {"code": 200, "data": result}

@router.post("/api/study/providers/models")
async def get_provider_models_endpoint(request: Request):
    """Fetches list of available models for a given provider."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    provider_id = body.get("provider") or body.get("llm_source") or "openai_compatible"
    
    # If the request contains a masked key or empty key, load the saved key from config
    raw_api_key = body.get("api_key", "")
    if not raw_api_key or config_store.is_masked_secret(raw_api_key):
        saved_cfg = config_store.load_config().get("providers", {}).get(provider_id, {})
        if saved_cfg.get("api_key"):
            body["api_key"] = saved_cfg["api_key"]

    provider_inst = providers.get_provider(provider_id, body)
    models = await provider_inst.list_models()
    return {"code": 200, "data": models}

@router.get("/api/study/providers/config")
async def get_providers_config_endpoint():
    """Returns saved providers configurations (with masked secrets) and global default models."""
    config = config_store.load_config()
    study_settings = config.get("study_settings", {})
    providers_cfg = config.get("providers", {})
    
    defaults = {
        "default_translation_provider": study_settings.get("default_translation_provider") or study_settings.get("llm_source") or "openai_compatible",
        "default_translation_model": study_settings.get("default_translation_model") or study_settings.get("text_model") or "deepseek-chat",
        "default_chat_provider": study_settings.get("default_chat_provider") or study_settings.get("llm_source") or "openai_compatible",
        "default_chat_model": study_settings.get("default_chat_model") or study_settings.get("text_model") or "deepseek-chat",
        "default_vlm_provider": study_settings.get("default_vlm_provider") or "openai_compatible",
        "default_vlm_model": study_settings.get("default_vlm_model") or study_settings.get("vlm_model") or ""
    }
    
    # Sanitize provider configs for export (Item 02)
    sanitized_providers = config_store.sanitize_config_for_export(providers_cfg)

    return {
        "code": 200,
        "data": {
            "providers": sanitized_providers,
            "defaults": defaults
        }
    }

@router.post("/api/study/providers/config")
async def save_providers_config_endpoint(request: Request):
    """
    Saves providers configurations and global default models into config.json.
    Preserves existing secrets if incoming values are empty or masked (Item 02).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    config = config_store.load_config()
    
    # Update providers preserving existing secrets
    if "providers" in body and isinstance(body["providers"], dict):
        current_providers = config.get("providers", {})
        merged_providers = dict(current_providers)
        for pid, incoming_pcfg in body["providers"].items():
            if isinstance(incoming_pcfg, dict):
                existing_pcfg = current_providers.get(pid, {})
                merged_providers[pid] = config_store.merge_config_with_preservation(incoming_pcfg, existing_pcfg)
            else:
                merged_providers[pid] = incoming_pcfg
        config["providers"] = merged_providers
        
    # Update default models in study_settings
    if "defaults" in body:
        defaults = body["defaults"]
        study_settings = config.get("study_settings", {})
        for k in ["default_translation_provider", "default_translation_model",
                  "default_chat_provider", "default_chat_model",
                  "default_vlm_provider", "default_vlm_model"]:
            if k in defaults:
                study_settings[k] = defaults[k]
        if "default_translation_provider" in defaults:
            study_settings["llm_source"] = defaults["default_translation_provider"]
        if "default_translation_model" in defaults:
            study_settings["text_model"] = defaults["default_translation_model"]
        if "default_vlm_model" in defaults:
            study_settings["vlm_model"] = defaults["default_vlm_model"]
            
        config["study_settings"] = study_settings
        
    config_store.save_config(config)
    return {"code": 200, "message": "模型与服务配置已安全保存"}
