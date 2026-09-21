import sys
import os
import time
import json
import uuid
import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

import config_store
from config_app import config_router
from study_router import study_router
import doc_converter
import providers

# Force standard streams to use UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("study-engine")

app = FastAPI(
    title="Omnididact · 全材料系统化自我教育与研学引擎",
    description="Omnididact: The AI-Powered Self-Education System for Systematically Mastering Any Material",
    version="2.0.0"
)

# Include configuration & study routes
app.include_router(config_router)
app.include_router(study_router)

# Redirect root-level favicon requests to static asset
@app.get("/favicon.ico")
@app.get("/favicon.svg")
async def favicon_redirect():
    return RedirectResponse(url="/static/favicon.svg")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

frontend_assets_dir = os.path.join("frontend", "dist", "assets")
if os.path.exists(frontend_assets_dir):
    app.mount("/assets", StaticFiles(directory=frontend_assets_dir), name="frontend-assets")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_trace_id(n: int = 21) -> str:
    """Generates a cryptographically secure trace ID."""
    random_bytes = os.urandom(n)
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
    result = []
    for b in random_bytes:
        result.append(alphabet[b % len(alphabet)])
    return "".join(result)

def resolve_image_for_provider(img_url: str) -> str:
    """
    If image URL is a local study document image, convert to base64 data URI so any provider can consume it.
    """
    if not img_url:
        return ""
    if img_url.startswith("data:"):
        return img_url
    if "/api/study/documents/" in img_url and "/images/" in img_url:
        try:
            from study import service as study_service
            parts = img_url.split("/documents/")[1].split("/images/")
            doc_id = parts[0]
            img_name = parts[1].split("?")[0]
            data_uri = study_service.get_image_base64_data_uri(doc_id, img_name)
            if data_uri:
                return data_uri
        except Exception as e:
            logger.warning(f"Could not convert local image to data URI: {e}")
    return img_url

@app.get("/v1/models")
async def list_models():
    """
    OpenAI-compatible models listing.
    Collects configured models across all active providers and defaults.
    """
    config = config_store.load_config()
    model_ids = set()

    # 1. Models from study settings
    study_settings = config.get("study_settings", {})
    for k in ["default_chat_model", "default_translation_model", "default_vlm_model", "text_model", "vlm_model"]:
        m = study_settings.get(k)
        if m:
            model_ids.add(m)

    # 2. Models from providers configuration
    for p_cfg in config.get("providers", {}).values():
        if isinstance(p_cfg, dict) and p_cfg.get("model"):
            model_ids.add(p_cfg["model"])

    # 3. Legacy models list if present
    for m in config.get("models", []):
        if isinstance(m, dict) and m.get("name"):
            model_ids.add(m["name"])

    if not model_ids:
        model_ids.add("DEEPSEEK-V4-284B-FLASH-V20260509")

    data_list = [
        {
            "id": mid,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "study-engine"
        }
        for mid in sorted(model_ids)
    ]
    return {
        "object": "list",
        "data": data_list
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Standard OpenAI-compatible chat completions endpoint.
    Dynamically routes requests to configured Provider (LM Studio, Ollama, Cloudflare, OpenAI, Intranet Proxy, etc.)
    """
    chat_id = f"chatcmpl-{uuid.uuid4()}"
    try:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="messages is required")

        config = config_store.load_config()
        study_settings = config.get("study_settings", {})

        # Record debug log
        config_store.add_debug_log(
            log_id=chat_id,
            model=body.get("model", "unknown"),
            stream=body.get("stream", False),
            client_req=body,
            client_headers=dict(request.headers)
        )

        requested_provider = body.get("provider")
        requested_model = body.get("model")
        is_stream = bool(body.get("stream", False))

        target_provider = requested_provider
        target_model = requested_model

        # Provider resolution heuristics
        if not target_provider:
            if target_model and target_model != "default":
                # Check if model matches any specific provider
                if target_model == study_settings.get("default_chat_model") or target_model == study_settings.get("chat_model"):
                    target_provider = study_settings.get("default_chat_provider") or study_settings.get("chat_provider")
                elif target_model == study_settings.get("default_vlm_model") or target_model == study_settings.get("vlm_model"):
                    target_provider = study_settings.get("default_vlm_provider") or study_settings.get("vlm_provider")
                elif target_model == study_settings.get("default_translation_model") or target_model == study_settings.get("translation_model"):
                    target_provider = study_settings.get("default_translation_provider") or study_settings.get("translation_provider")
                elif target_model.startswith("@cf/"):
                    target_provider = "cloudflare"
                else:
                    for p_name, p_cfg in config.get("providers", {}).items():
                        if p_cfg.get("model") == target_model:
                            target_provider = p_name
                            break
            if not target_provider:
                target_provider = study_settings.get("default_chat_provider") or study_settings.get("llm_source") or "openai_compatible"

        if not target_model or target_model == "default":
            target_model = study_settings.get("default_chat_model") or study_settings.get("text_model") or ""

        # Normalize messages and images for provider
        provider_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                new_items = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    itype = item.get("type")
                    if itype == "text":
                        new_items.append({"type": "text", "text": item.get("text", "")})
                    elif itype == "image_url":
                        img_val = item.get("image_url", "")
                        img_u = img_val.get("url", "") if isinstance(img_val, dict) else str(img_val)
                        resolved_u = resolve_image_for_provider(img_u)
                        new_items.append({"type": "image_url", "image_url": {"url": resolved_u}})
                provider_messages.append({"role": role, "content": new_items})
            else:
                provider_messages.append({"role": role, "content": content})

        provider_inst = providers.get_provider(target_provider, {"model": target_model})
        logger.info(f"Completions routed to provider '{target_provider}' ({provider_inst.display_name}) with model '{target_model}'. is_stream={is_stream}")

        opts = {
            "model": target_model,
            "temperature": float(body.get("temperature", 0.7)),
        }
        if "max_tokens" in body:
            opts["max_tokens"] = int(body["max_tokens"])

        if is_stream:
            async def provider_stream_generator():
                try:
                    async for chunk in provider_inst.stream_chat(provider_messages, opts):
                        sse_line = providers.chunk_to_sse(chunk)
                        if sse_line:
                            config_store.append_debug_log_chunk(chat_id, sse_line)
                            yield sse_line.encode("utf-8")
                except Exception as stream_err:
                    logger.exception(f"Provider stream error: {stream_err}")
                    err_sse = f"data: {json.dumps({'error': str(stream_err)})}\n\n"
                    config_store.append_debug_log_chunk(chat_id, err_sse)
                    yield err_sse.encode("utf-8")

            return StreamingResponse(
                provider_stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                }
            )
        else:
            resp_content = await provider_inst.chat(provider_messages, opts)
            return {
                "id": chat_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": target_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": resp_content
                        },
                        "finish_reason": "stop"
                    }
                ]
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat completions error")
        raise HTTPException(status_code=500, detail=f"LLM 服务异常: {str(e)}")

@app.post("/api/document/inspect")
async def inspect_document_endpoint(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    limit: int = Form(24)
):
    """
    Parses an uploaded document (PDF, PPTX, DOCX, Image) and returns page count and thumbnail previews.
    """
    try:
        content = await file.read()
        filename = file.filename or "document.pdf"
        info = doc_converter.inspect_document(content, filename)
        total_pages, thumbnails = doc_converter.generate_document_thumbnails(
            content, filename, start_page=start_page, max_pages=limit
        )
        return {
            "code": 200,
            "data": {
                "filename": filename,
                "file_type": info["file_type"],
                "total_pages": total_pages,
                "thumbnails": thumbnails,
                "has_more": (start_page + len(thumbnails) - 1) < total_pages
            },
            "message": "文档解析成功"
        }
    except Exception as e:
        logger.error(f"Failed to inspect document: {e}")
        raise HTTPException(status_code=500, detail=f"解析文档失败: {str(e)}")

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() in ("true", "1", "yes")
    logger.info(f"Starting Study & Research Engine on http://{host}:{port} (reload={reload})")
    uvicorn.run("proxy:app", host=host, port=port, reload=reload, log_level="info")

