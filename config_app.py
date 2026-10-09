import os
import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import config_store
from auth import verify_api_token, is_auth_required, is_request_authenticated

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("config-router")

# Define the APIRouter to be included by proxy.py
config_router = APIRouter()

def is_debug_route_enabled() -> bool:
    """Checks whether debug endpoints are enabled in environment."""
    return os.getenv("OMNIDIDACT_ENABLE_DEBUG", "true").lower() in ("true", "1", "yes")

# Redirect root / to modern study center
@config_router.get("/")
async def root_redirect(request: Request):
    if is_auth_required() and not is_request_authenticated(request):
        return RedirectResponse(url="/login?redirect=/study", status_code=303)
    return RedirectResponse(url="/study")

# Serve the Config HTML frontend at /config
@config_router.get("/config", response_class=HTMLResponse)
async def get_index(request: Request):
    if is_auth_required() and not is_request_authenticated(request):
        return RedirectResponse(url="/login?redirect=/config", status_code=303)
    dist_html = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(dist_html):
        try:
            with open(dist_html, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.warning(f"Failed to read frontend dist: {e}")

    template_path = os.path.join("templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Frontend template index.html not found.")
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read template: {str(e)}")

# Serve the standalone Chat / Model Testing terminal at /chat
@config_router.get("/chat", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    if is_auth_required() and not is_request_authenticated(request):
        return RedirectResponse(url="/login?redirect=/chat", status_code=303)
    dist_html = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(dist_html):
        try:
            with open(dist_html, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.warning(f"Failed to read frontend dist: {e}")

    template_path = os.path.join("templates", "chat.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Chat template chat.html not found.")
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read template: {str(e)}")

# Get current configuration (Masked secrets returned - Item 02)
@config_router.get("/api/config", dependencies=[Depends(verify_api_token)])
async def get_config():
    config = config_store.load_config()
    return config_store.sanitize_config_for_export(config)

# Save basic system configuration (upstream URL)
@config_router.post("/api/config", dependencies=[Depends(verify_api_token)])
async def save_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    upstream_url = body.get("upstream_url")
    if not upstream_url:
        raise HTTPException(status_code=400, detail="upstream_url is required")
        
    config = config_store.load_config()
    config["upstream_url"] = upstream_url
    config_store.save_config(config)
    return {"status": "ok", "message": "System configuration updated successfully"}

# Parse raw cookies pasted from browser console
@config_router.post("/api/cookies", dependencies=[Depends(verify_api_token)])
async def parse_and_save_cookies(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    raw_cookie = body.get("raw_cookie", "")
    if not raw_cookie:
        raise HTTPException(status_code=400, detail="raw_cookie is required")
        
    config = config_store.load_config()
    
    parsed_cookies = {}
    if raw_cookie.lower().startswith("cookie:"):
        raw_cookie = raw_cookie[7:].strip()
        
    for part in raw_cookie.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            parsed_cookies[k.strip()] = v.strip()
            
    if not parsed_cookies:
        raise HTTPException(status_code=400, detail="No cookies could be parsed. Check formatting.")
        
    if "cookies" not in config:
        config["cookies"] = {}
        
    config["cookies"].update(parsed_cookies)
    config_store.save_config(config)
    return {"status": "ok", "message": "Cookies parsed and updated successfully", "parsed_count": len(parsed_cookies)}

# Add/Update model configuration
@config_router.post("/api/models", dependencies=[Depends(verify_api_token)])
async def save_model(request: Request):
    try:
        model_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    name = model_data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Model name is required")
        
    config = config_store.load_config()
    models = config.get("models", [])
    
    existing_idx = -1
    for i, model in enumerate(models):
        if model.get("name") == name:
            existing_idx = i
            break
            
    is_default = False
    if existing_idx != -1:
        is_default = models[existing_idx].get("is_default", False)
    elif not models:
        is_default = True
        
    new_model_config = {
        "name": name,
        "type": model_data.get("type", "text"),
        "model_url": model_data.get("model_url", "model_url"),
        "cluster_type": model_data.get("cluster_type", "operation"),
        "temperature": float(model_data.get("temperature", 0.7)),
        "max_tokens": int(model_data.get("max_tokens", 8192)),
        "top_p": float(model_data.get("top_p", 0.9)),
        "top_k": int(model_data.get("top_k", 20)),
        "repetition_penalty": float(model_data.get("repetition_penalty", 1.05)),
        "is_default": is_default,
        "is_thinking": bool(model_data.get("is_thinking", False))
    }
    if "max_output_tokens" in model_data:
        new_model_config["max_output_tokens"] = int(model_data["max_output_tokens"])
    if "max_input_tiles" in model_data:
        new_model_config["max_input_tiles"] = int(model_data["max_input_tiles"])
    
    if existing_idx != -1:
        models[existing_idx] = new_model_config
    else:
        models.append(new_model_config)
        
    config["models"] = models
    config_store.save_config(config)
    return {"status": "ok", "message": f"Model {name} updated successfully"}

# Set a model as default per type (text or vlm)
@config_router.post("/api/models/default", dependencies=[Depends(verify_api_token)])
async def set_default_model(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Model name is required")
        
    config = config_store.load_config()
    models = config.get("models", [])
    
    target_model = next((m for m in models if m.get("name") == name), None)
    if not target_model:
        raise HTTPException(status_code=404, detail=f"Model {name} not found")
        
    target_type = target_model.get("type", "text")
    
    for model in models:
        if model.get("type", "text") == target_type:
            if model.get("name") == name:
                model["is_default"] = True
            else:
                model["is_default"] = False
                
    config["models"] = models
    config_store.save_config(config)
    return {"status": "ok", "message": f"Model {name} is now the default model for type {target_type}"}

# Delete a model
@config_router.delete("/api/models/{name}", dependencies=[Depends(verify_api_token)])
async def delete_model(name: str):
    config = config_store.load_config()
    models = config.get("models", [])
    
    target_idx = -1
    for i, model in enumerate(models):
        if model.get("name") == name:
            target_idx = i
            break
            
    if target_idx == -1:
        raise HTTPException(status_code=404, detail=f"Model {name} not found")
        
    was_default = models[target_idx].get("is_default", False)
    models.pop(target_idx)
    
    if was_default and models:
        models[0]["is_default"] = True
        
    config["models"] = models
    config_store.save_config(config)
    return {"status": "ok", "message": f"Model {name} deleted successfully"}

# Get captured debug logs (Requires Auth & Debug enabled - Item 03)
@config_router.get("/api/debug", dependencies=[Depends(verify_api_token)])
async def get_debug_logs():
    if not is_debug_route_enabled():
        raise HTTPException(status_code=404, detail="Debug endpoint is disabled")
    return config_store.DEBUG_HISTORY

# Toggle debug mode status (Requires Auth & Debug enabled - Item 03)
@config_router.post("/api/debug/toggle", dependencies=[Depends(verify_api_token)])
async def toggle_debug_mode(request: Request):
    if not is_debug_route_enabled():
        raise HTTPException(status_code=404, detail="Debug endpoint is disabled")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    debug_mode = body.get("debug_mode", False)
    config = config_store.load_config()
    config["debug_mode"] = bool(debug_mode)
    config_store.save_config(config)
    return {"status": "ok", "message": f"Debug mode set to {config['debug_mode']}"}
