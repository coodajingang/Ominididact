import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import study as study_service

logger = logging.getLogger("study-router-translate")
router = APIRouter()

def validate_doc_id_param(doc_id: str) -> str:
    try:
        return study_service.validate_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid doc_id format: {doc_id}")

@router.post("/api/study/documents/{doc_id}/translate_paragraph")
async def translate_paragraph_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not chapter_id or not paragraph_id:
        raise HTTPException(status_code=400, detail="chapter_id and paragraph_id are required")
        
    try:
        res = await study_service.retranslate_paragraph(
            doc_id, chapter_id, paragraph_id,
            provider_override=provider_override,
            model_override=model_override
        )
        return {"code": 200, "data": res, "message": "段落翻译完成"}
    except Exception as e:
        logger.exception("Translate paragraph failed")
        raise HTTPException(status_code=500, detail=f"翻译失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/paragraphs/extract_text")
async def extract_paragraph_text_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    force = body.get("force", False)

    if not chapter_id or not paragraph_id:
        raise HTTPException(status_code=400, detail="chapter_id and paragraph_id are required")

    try:
        res = await study_service.extract_paragraph_image_text(doc_id, chapter_id, paragraph_id, force=force)
        return {"code": 200, "data": res, "message": "图件文字提取完成"}
    except Exception as e:
        logger.exception("Extract paragraph text failed")
        raise HTTPException(status_code=500, detail=f"文字提取失败: {str(e)}")

# Chapter batch translate endpoints (Item 08: standardized on /chapters/ with 307 redirect for /chapter/)
@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/translate_start")
async def start_chapter_translate_endpoint(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = await study_service.start_chapter_translation(doc_id, chapter_id)
        return res
    except Exception as e:
        logger.exception("Start chapter translate failed")
        raise HTTPException(status_code=500, detail=f"启动翻译失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/translate_start", include_in_schema=False)
async def start_chapter_translate_legacy(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/translate_start",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/translate_stop")
async def stop_chapter_translate_endpoint(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = await study_service.stop_chapter_translation(doc_id, chapter_id)
        return res
    except Exception as e:
        logger.exception("Stop chapter translate failed")
        raise HTTPException(status_code=500, detail=f"停止翻译失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/translate_stop", include_in_schema=False)
async def stop_chapter_translate_legacy(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/translate_stop",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.get("/api/study/documents/{doc_id}/chapters/{chapter_id}/translate_status")
async def get_chapter_translate_status_endpoint(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = study_service.get_chapter_translation_status(doc_id, chapter_id)
        return {"code": 200, "data": res}
    except Exception as e:
        logger.exception("Get chapter translate status failed")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.get("/api/study/documents/{doc_id}/chapter/{chapter_id}/translate_status", include_in_schema=False)
async def get_chapter_translate_status_legacy(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/translate_status",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

# Full document batch translate endpoints
@router.post("/api/study/documents/{doc_id}/translate_start")
async def start_doc_translate_endpoint(doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = await study_service.start_document_translation(doc_id)
        return res
    except Exception as e:
        logger.exception("Start document translate failed")
        raise HTTPException(status_code=500, detail=f"启动全书翻译失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/translate_stop")
async def stop_doc_translate_endpoint(doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = await study_service.stop_document_translation(doc_id)
        return res
    except Exception as e:
        logger.exception("Stop document translate failed")
        raise HTTPException(status_code=500, detail=f"停止全书翻译失败: {str(e)}")

@router.get("/api/study/documents/{doc_id}/translate_status")
async def get_doc_translate_status_endpoint(doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = study_service.get_document_translation_status(doc_id)
        return {"code": 200, "data": res}
    except Exception as e:
        logger.exception("Get document translate status failed")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

# Legacy compatibility for translate_chapter
@router.post("/api/study/documents/{doc_id}/translate_chapter")
async def translate_chapter_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    if not chapter_id:
        raise HTTPException(status_code=400, detail="chapter_id is required")
    return await start_chapter_translate_endpoint(doc_id, chapter_id)
