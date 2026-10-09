import os
import json
import logging
import time
import re
from typing import Dict, Any, List, Optional, Union

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

SENSITIVE_KEY_NAMES = {
    "api_key", "secret", "token", "password", "key", "auth_token",
    "api_token", "secret_key", "access_token", "credential", "credentials"
}

SAFE_DEBUG_HEADERS = {
    "content-type", "accept", "user-agent", "host", "accept-encoding",
    "content-length", "x-request-id", "x-trace-id"
}

# Provider environment variable mappings (Item 06)
PROVIDER_ENV_KEYS: Dict[str, List[str]] = {
    "openai_compatible": ["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "PROVIDER_OPENAI_API_KEY"],
    "openai": ["OPENAI_API_KEY", "PROVIDER_OPENAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY", "PROVIDER_DEEPSEEK_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY", "PROVIDER_NVIDIA_API_KEY"],
    "amd": ["AMD_API_KEY", "PROVIDER_AMD_API_KEY"],
    "cloudflare": ["CLOUDFLARE_API_KEY", "PROVIDER_CLOUDFLARE_API_KEY"],
    "ollama": ["OLLAMA_BASE_URL", "PROVIDER_OLLAMA_BASE_URL"],
    "lm_studio": ["LM_STUDIO_BASE_URL", "PROVIDER_LM_STUDIO_BASE_URL"],
}

# Global in-memory logs repository
DEBUG_HISTORY: List[Dict[str, Any]] = []
debug_logs = DEBUG_HISTORY
MAX_DEBUG_LOGS = 20

def is_sensitive_key(key: str) -> bool:
    """Checks whether a dictionary key name represents a sensitive credential."""
    if not isinstance(key, str):
        return False
    k = key.lower().strip()
    if k in SENSITIVE_KEY_NAMES:
        return True
    return any(k.endswith(f"_{suffix}") for suffix in SENSITIVE_KEY_NAMES) or any(k.startswith(f"{prefix}_") for prefix in ("api_key", "auth", "secret"))

def mask_secret(value: Any) -> str:
    """Masks sensitive secret string for safe API export (e.g. ****1234)."""
    if value is None:
        return ""
    val_str = str(value).strip()
    if not val_str:
        return ""
    if len(val_str) <= 4:
        return "****"
    return f"****{val_str[-4:]}"

def is_masked_secret(value: Any) -> bool:
    """Returns True if the string is already a masked secret placeholder."""
    if not isinstance(value, str):
        return False
    val = value.strip()
    return val.startswith("****") or ("****" in val) or (val.count("*") >= 4)

def sanitize_config_for_export(obj: Any) -> Any:
    """
    Recursively sanitizes configuration dictionary, masking any API keys or secrets.
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if is_sensitive_key(k):
                if v:
                    result[k] = mask_secret(v)
                    result[f"is_{k}_configured"] = True
                else:
                    result[k] = ""
                    result[f"is_{k}_configured"] = False
            else:
                result[k] = sanitize_config_for_export(v)
        return result
    elif isinstance(obj, list):
        return [sanitize_config_for_export(item) for item in obj]
    return obj

def merge_config_with_preservation(incoming: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merges incoming config into existing config.
    If an incoming sensitive field is empty, null, or masked (e.g. ****1234),
    it preserves the existing secret value instead of overwriting it!
    """
    merged = dict(existing)
    for k, v in incoming.items():
        if is_sensitive_key(k):
            # If incoming value is masked or empty, preserve existing value if present
            if v is None or v == "" or is_masked_secret(v):
                merged[k] = existing.get(k, "")
            else:
                merged[k] = v
        elif isinstance(v, dict) and isinstance(existing.get(k), dict):
            merged[k] = merge_config_with_preservation(v, existing[k])
        else:
            merged[k] = v
    return merged

def get_env_provider_key(provider_id: str) -> Optional[str]:
    """Finds configured provider key from environment variables."""
    # 1. Look up specific provider keys
    env_names = PROVIDER_ENV_KEYS.get(provider_id, [])
    for name in env_names:
        val = os.getenv(name)
        if val and val.strip():
            return val.strip()

    # 2. Generic pattern: PROVIDER_<PROVIDER_ID>_API_KEY
    generic_name = f"PROVIDER_{provider_id.upper()}_API_KEY"
    generic_val = os.getenv(generic_name)
    if generic_val and generic_val.strip():
        return generic_val.strip()

    return None

def resolve_provider_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Injects environment-level provider API keys into provider configs if present.
    """
    providers_cfg = config.get("providers", {})
    if not isinstance(providers_cfg, dict):
        return config

    updated_providers = dict(providers_cfg)
    for pid, pcfg in providers_cfg.items():
        if isinstance(pcfg, dict):
            env_key = get_env_provider_key(pid)
            if env_key:
                pcfg_copy = dict(pcfg)
                pcfg_copy["api_key"] = env_key
                pcfg_copy["_source"] = "env"
                updated_providers[pid] = pcfg_copy

    config["providers"] = updated_providers
    return config

def load_config() -> Dict[str, Any]:
    """
    Loads config from config.json. If it does not exist, initializes it.
    If it exists, migrates older config fields and resolves environment variable overrides.
    """
    if not os.path.exists(CONFIG_PATH):
        logger.info(f"Config file {CONFIG_PATH} not found. Creating default config.")
        save_config(DEFAULT_CONFIG)
        cfg = dict(DEFAULT_CONFIG)
    else:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # Ensure essential keys exist
            for key, val in DEFAULT_CONFIG.items():
                if key not in cfg:
                    cfg[key] = val

            # Migration: Ensure each model has a type
            models = cfg.get("models", [])
            has_vlm = False
            updated = False

            for model in models:
                if "type" not in model:
                    model["type"] = "text"
                    updated = True
                if model.get("type") == "vlm":
                    has_vlm = True

            if not has_vlm:
                logger.info("No VLM model found in config.json. Adding default VLM model.")
                qwen_model = next((m for m in DEFAULT_CONFIG["models"] if m.get("type") == "vlm"), None)
                if qwen_model:
                    models.append(qwen_model)
                    updated = True

            if updated:
                cfg["models"] = models
                save_config(cfg)
        except Exception as e:
            logger.error(f"Error loading config.json: {e}. Returning default config.")
            cfg = dict(DEFAULT_CONFIG)

    # Apply environment variable overrides for Provider keys (Item 06)
    cfg = resolve_provider_env_overrides(cfg)
    return cfg

def save_config(config: Dict[str, Any]) -> None:
    """
    Saves config to config.json.
    """
    try:
        # Strip runtime helper keys before saving
        clean_config = dict(config)
        if "providers" in clean_config and isinstance(clean_config["providers"], dict):
            clean_providers = {}
            for pid, pcfg in clean_config["providers"].items():
                if isinstance(pcfg, dict):
                    clean_p = {k: v for k, v in pcfg.items() if not k.startswith("_")}
                    clean_providers[pid] = clean_p
                else:
                    clean_providers[pid] = pcfg
            clean_config["providers"] = clean_providers

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(clean_config, f, indent=2, ensure_ascii=False)
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

    for model in models:
        if model.get("type", "text") == model_type and model.get("is_default"):
            return model

    for model in models:
        if model.get("type", "text") == model_type:
            return model

    return models[0]

# --- Debug Logging Utilities (Item 03) ---

def sanitize_debug_headers(headers: Any) -> Dict[str, str]:
    """
    Sanitizes HTTP headers for debug logging:
    - Only allows safe headers in SAFE_DEBUG_HEADERS whitelist
    - Excludes and redacts Authorization, Cookie, Proxy-Auth, API keys, etc.
    """
    if not headers or not isinstance(headers, (dict, list)):
        return {}

    sanitized = {}
    items = headers.items() if isinstance(headers, dict) else headers
    for k, v in items:
        k_str = str(k).lower().strip()
        if k_str in SAFE_DEBUG_HEADERS and not any(secret in k_str for secret in ("auth", "key", "token", "cookie", "secret")):
            val_str = str(v)
            if len(val_str) > 512:
                val_str = val_str[:512] + "..."
            sanitized[k_str] = val_str
    return sanitized

def sanitize_debug_body(body: Any, max_str_len: int = 4096) -> Any:
    """
    Recursively masks sensitive values and truncates excessively long strings for debug logs.
    """
    if isinstance(body, dict):
        sanitized = {}
        for k, v in body.items():
            if is_sensitive_key(k):
                sanitized[k] = mask_secret(v)
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_debug_body(v, max_str_len)
            elif isinstance(v, str):
                if len(v) > max_str_len:
                    sanitized[k] = v[:max_str_len] + f"... [truncated {len(v)} chars]"
                else:
                    sanitized[k] = v
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(body, list):
        return [sanitize_debug_body(item, max_str_len) for item in body]
    elif isinstance(body, str):
        # 1. If it's JSON encoded, decode, sanitize nested dict/list, and re-encode
        trimmed = body.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                parsed = json.loads(trimmed)
                sanitized_obj = sanitize_debug_body(parsed, max_str_len)
                return json.dumps(sanitized_obj, ensure_ascii=False)
            except Exception:
                pass

        # 2. String secret masking with regex
        res = body
        # Mask sk- keys
        res = re.sub(r"sk-[a-zA-Z0-9_\-\.]{8,}", lambda m: mask_secret(m.group(0)), res)
        # Mask Bearer tokens
        res = re.sub(r"Bearer\s+([a-zA-Z0-9_\-\.]{8,})", lambda m: f"Bearer {mask_secret(m.group(1))}", res)

        if len(res) > max_str_len:
            return res[:max_str_len] + f"... [truncated {len(res)} chars]"
        return res
    return body

def add_debug_log(log_id: str, model: str, stream: bool, client_req: dict, client_headers: dict) -> None:
    """
    Creates a new sanitized debug entry inside DEBUG_HISTORY.
    Enforces header whitelist, body masking, and max circular capacity.
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
            "headers": sanitize_debug_headers(client_headers),
            "body": sanitize_debug_body(client_req)
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

    # Enforce circular capacity limit
    while len(DEBUG_HISTORY) > MAX_DEBUG_LOGS:
        DEBUG_HISTORY.pop()

def update_debug_log_upstream(log_id: str, upstream_url: str, upstream_req: dict, upstream_headers: dict) -> None:
    """
    Updates the log entry with sanitized upstream parameters.
    """
    global DEBUG_HISTORY
    for entry in DEBUG_HISTORY:
        if entry["id"] == log_id:
            entry["upstream_request"] = {
                "url": upstream_url,
                "headers": sanitize_debug_headers(upstream_headers),
                "body": sanitize_debug_body(upstream_req)
            }
            break

def append_debug_log_chunk(log_id: str, chunk: str) -> None:
    """
    Appends an incoming response chunk string (truncated if excessive).
    """
    global DEBUG_HISTORY
    for entry in DEBUG_HISTORY:
        if entry["id"] == log_id:
            clean_chunk = chunk if len(chunk) <= 2048 else (chunk[:2048] + "...")
            entry["response_chunks"].append(clean_chunk)
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
                # Sanitize error message to prevent leaking tokens in exception traces
                entry["error"] = sanitize_debug_body(error_msg)
            break
