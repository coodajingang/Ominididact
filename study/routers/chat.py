import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import study as study_service
from study.chat_manager import (
    load_chat_history,
    save_chat_history,
    clear_chat_history,
)

logger = logging.getLogger("study-router-chat")
router = APIRouter()

def validate_doc_id_param(doc_id: str) -> str:
    try:
        return study_service.validate_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid doc_id format: {doc_id}")

@router.get("/api/study/documents/{doc_id}/chat_history")
async def get_chat_history_endpoint(
    doc_id: str,
    chat_type: str = "paragraph",
    chapter_id: Optional[str] = None,
    paragraph_id: Optional[str] = None
):
    validate_doc_id_param(doc_id)
    history = load_chat_history(doc_id, chat_type, chapter_id, paragraph_id)
    return {"code": 200, "data": history}

@router.delete("/api/study/documents/{doc_id}/chat_history")
async def clear_chat_history_endpoint(
    doc_id: str,
    chat_type: str = "paragraph",
    chapter_id: Optional[str] = None,
    paragraph_id: Optional[str] = None
):
    validate_doc_id_param(doc_id)
    res = clear_chat_history(doc_id, chat_type, chapter_id, paragraph_id)
    return {"code": 200, "data": res, "message": "对话历史已清空"}

@router.post("/api/study/documents/{doc_id}/chat_history")
async def save_chat_history_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    chat_type = body.get("chat_type", "paragraph")
    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    messages = body.get("messages", [])

    res = save_chat_history(
        doc_dir=doc_id,
        chat_type=chat_type,
        chapter_id=chapter_id or "",
        messages=messages,
        paragraph_id=paragraph_id
    )
    return {"code": 200, "data": res, "message": "对话历史已保存"}

@router.post("/api/study/documents/{doc_id}/paragraph_chat")
async def paragraph_chat_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    user_prompt = body.get("prompt")
    chat_history = body.get("chat_history", [])
    prev_count = body.get("prev_count", 2)
    next_count = body.get("next_count", 2)
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not chapter_id or not paragraph_id or not user_prompt:
        raise HTTPException(status_code=400, detail="chapter_id, paragraph_id, and prompt are required")
        
    try:
        gen = study_service.chat_with_paragraph(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            user_message=user_prompt,
            history=chat_history,
            prev_count=prev_count,
            next_count=next_count,
            provider_override=provider_override,
            model_override=model_override
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except Exception as e:
        logger.exception("Paragraph chat failed")
        raise HTTPException(status_code=500, detail=f"对话生成失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/chapter_chat")
async def chapter_chat_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    user_prompt = body.get("prompt")
    chat_history = body.get("chat_history", [])
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not chapter_id or not user_prompt:
        raise HTTPException(status_code=400, detail="chapter_id and prompt are required")
        
    try:
        gen = study_service.stream_chapter_chat(
            doc_id=doc_id,
            chapter_id=chapter_id,
            user_message=user_prompt,
            history=chat_history,
            provider_override=provider_override,
            model_override=model_override
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except Exception as e:
        logger.exception("Chapter chat failed")
        raise HTTPException(status_code=500, detail=f"全章对话生成失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/document_chat")
async def document_chat_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    user_prompt = body.get("prompt") or body.get("message")
    chat_history = body.get("chat_history") or body.get("history") or []
    provider_override = body.get("provider")
    model_override = body.get("model")

    if not user_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    try:
        from study.document_chat import stream_document_chat
        gen = stream_document_chat(
            doc_id=doc_id,
            user_message=user_prompt,
            history=chat_history,
            provider_override=provider_override,
            model_override=model_override
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except Exception as e:
        logger.exception("Document chat failed")
        raise HTTPException(status_code=500, detail=f"全篇对话生成失败: {str(e)}")
