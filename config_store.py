import os
import json
import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger("config-store")

CONFIG_PATH = os.getenv("CONFIG_PATH", "config.json")

DEFAULT_CONFIG = {
    "upstream_url": "https://api.openai.com/v1/chat/completions",
    "debug_mode": False,
    "cookies": {},
    "models": [
        {
            "name": "deepseek-chat",
            "type": "text",
            "model_url": "model_url",
            "cluster_type": "operation",
            "temperature": 0.7,
            "max_tokens": 8192,
            "top_p": 0.9,
            "top_k": 20,
            "repetition_penalty": 1.05,
            "is_default": True,
            "is_thinking": False
        },
        {
            "name": "gpt-4o",
            "type": "vlm",
            "temperature": 0.7,
            "max_output_tokens": 4096,
            "top_p": 0.95,
            "repetition_penalty": 1.0,
            "max_input_tiles": 12,
            "is_default": True,
            "is_thinking": False
        }
    ]
}

# Global in-memory logs repository
DEBUG_HISTORY: List[Dict[str, Any]] = []

def load_config() -> Dict[str, Any]:
    """
    Loads config from config.json. If it does not exist, initializes it.
    If it exists, migrates older config fields to maintain compatibility.
    """
    if not os.path.exists(CONFIG_PATH):
        logger.info(f"Config file {CONFIG_PATH} not found. Creating default config.")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Ensure essential keys exist
        for key, val in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = val
                
        # Migration: Ensure each model has a type
        models = config.get("models", [])
        has_vlm = False
        updated = False
        
        for model in models:
            if "type" not in model:
                model["type"] = "text"
                updated = True
            if model["type"] == "vlm":
                has_vlm = True
                
        # Migration: If no VLM model is configured, append the default QWEN model
        if not has_vlm:
            logger.info("No VLM model found in config.json. Adding default VLM model.")
            qwen_model = next((m for m in DEFAULT_CONFIG["models"] if m["type"] == "vlm"), None)
            if qwen_model:
                models.append(qwen_model)
                updated = True
                
        if updated:
            config["models"] = models
            save_config(config)
            
        return config
    except Exception as e:
        logger.error(f"Error loading config.json: {e}. Returning default config.")
        return DEFAULT_CONFIG

def save_config(config: Dict[str, Any]) -> None:
    """
    Saves config to config.json.
    """
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"Config successfully written to {CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Error saving config.json: {e}")

def get_default_model(config: Dict[str, Any], model_type: str = "text") -> Dict[str, Any]:
    """
    Finds the default model configuration for a specific type (text or vlm).
    """
    models = config.get("models", [])
    if not models:
        for m in DEFAULT_CONFIG["models"]:
            if m.get("type") == model_type:
                return m
        return DEFAULT_CONFIG["models"][0]
    
    # 1. Try to find marked default of correct type
    for model in models:
        if model.get("type", "text") == model_type and model.get("is_default"):
            return model
            
    # 2. Fallback to first model of correct type
    for model in models:
        if model.get("type", "text") == model_type:
            return model
            
    # 3. Fallback to any model
    return models[0]

def add_debug_log(log_id: str, model: str, stream: bool, client_req: dict, client_headers: dict) -> None:
    """
    Creates a new debug entry inside DEBUG_HISTORY.
    """
    global DEBUG_HISTORY
    config = load_config()
    if not config.get("debug_mode", False):
        return
        
    log_entry = {
        "id": log_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "model": model,
        "stream": stream,
        "status": "processing",
        "client_request": {
            "headers": client_headers,
            "body": client_req
        },
        "upstream_request": {
            "url": "",
            "headers": {},
            "body": {}
        },
        "response_chunks": [],
        "error": None
    }
    
    DEBUG_HISTORY.insert(0, log_entry)
    
    # Keep only the latest 10 logs
    if len(DEBUG_HISTORY) > 10:
        DEBUG_HISTORY.pop()

def update_debug_log_upstream(log_id: str, upstream_url: str, upstream_req: dict, upstream_headers: dict) -> None:
    """
    Updates the log entry with mapped upstream parameters.
    """
    global DEBUG_HISTORY
    for entry in DEBUG_HISTORY:
        if entry["id"] == log_id:
            entry["upstream_request"] = {
                "url": upstream_url,
                "headers": upstream_headers,
                "body": upstream_req
            }
            break

def append_debug_log_chunk(log_id: str, chunk: str) -> None:
    """
    Appends an incoming response chunk string.
    """
    global DEBUG_HISTORY
    for entry in DEBUG_HISTORY:
        if entry["id"] == log_id:
            entry["response_chunks"].append(chunk)
            break

def finalize_debug_log(log_id: str, status: str, error_msg: str = None) -> None:
    """
    Marks the log status as completed or error.
    """
    global DEBUG_HISTORY
    for entry in DEBUG_HISTORY:
        if entry["id"] == log_id:
            entry["status"] = status
            if error_msg:
                entry["error"] = error_msg
            break
