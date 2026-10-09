import os
import io
import time
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, Response, JSONResponse, StreamingResponse, RedirectResponse
import study as study_service
from auth import is_auth_required, is_request_authenticated
from study.flashcard_manager import (
    load_doc_flashcards,
    save_doc_flashcards,
    list_flashcards,
    get_flashcard,
    create_flashcard,
    batch_create_flashcards,
    update_flashcard,
    delete_flashcard,
    batch_delete_flashcards,
    record_card_review,
    clear_card_errors,
    get_flashcard_statistics,
    update_flashcard_settings,
    add_flashcard,
    get_flashcards_stats,
    save_flashcard_settings,
)
from study.anki_exporter import export_flashcards_to_apkg_bytes

logger = logging.getLogger("study-router-flashcards")
router = APIRouter()

def validate_doc_id_param(doc_id: str) -> str:
    try:
        return study_service.validate_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid doc_id format: {doc_id}")

@router.get("/study/flashcards", response_class=HTMLResponse, include_in_schema=False)
async def get_flashcards_page(request: Request):
    if is_auth_required() and not is_request_authenticated(request):
        return RedirectResponse(url="/login?redirect=/study/flashcards", status_code=303)
    template_path = os.path.join("templates", "flashcards.html")
    if os.path.exists(template_path):
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read template: {str(e)}")

    dist_html = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(dist_html):
        try:
            with open(dist_html, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.warning(f"Failed to read frontend dist: {e}")

    raise HTTPException(status_code=404, detail="Flashcards interface not found")

@router.get("/api/study/documents/{doc_id}/flashcards")
async def get_document_flashcards(
    doc_id: str,
    type: Optional[str] = None,
    chapter_id: Optional[str] = None,
    paragraph_id: Optional[str] = None,
    is_error: bool = False,
    keyword: Optional[str] = None,
    filter_mode: Optional[str] = None,
):
    validate_doc_id_param(doc_id)
    data = load_doc_flashcards(doc_id)
    cards = list_flashcards(
        doc_id=doc_id,
        filter_type=type,
        chapter_id=chapter_id,
        is_error=is_error,
        keyword=keyword,
    )
    if paragraph_id:
        cards = [c for c in cards if c.get("paragraph_id") == paragraph_id]

    now_ts = int(time.time())
    if filter_mode == "due":
        cards = [c for c in cards if c.get("stats", {}).get("next_review", 0) <= now_ts]
    elif filter_mode == "mistakes":
        cards = [c for c in cards if c.get("stats", {}).get("is_mistake", False) or c.get("stats", {}).get("lapses", 0) > 0]
    elif filter_mode == "mastered":
        cards = [c for c in cards if c.get("stats", {}).get("state") == "mastered"]
    elif filter_mode == "learning":
        cards = [c for c in cards if c.get("stats", {}).get("state", "new") in ("new", "learning")]

    stats = get_flashcard_statistics(doc_id)
    return {
        "code": 200,
        "data": {
            "cards": cards,
            "total": len(cards),
            "summary": stats,
            "settings": data.get("settings", {}),
        },
    }

@router.post("/api/study/documents/{doc_id}/flashcards")
async def add_document_flashcard(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        if "cards" in body and isinstance(body["cards"], list):
            created = batch_create_flashcards(doc_id, body["cards"])
            return {"code": 200, "data": created, "message": f"成功批量导入 {len(created)} 张闪卡"}
        else:
            card = create_flashcard(doc_id, body)
            return {"code": 200, "data": card, "message": "闪卡添加成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create flashcard")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/study/documents/{doc_id}/flashcards/{card_id}")
async def update_document_flashcard(request: Request, doc_id: str, card_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        card = update_flashcard(doc_id, card_id, body)
        return {"code": 200, "data": card, "message": "闪卡修改已保存"}
    except ValueError as e:
        err_str = str(e)
        if "not found" in err_str.lower():
            raise HTTPException(status_code=404, detail="闪卡不存在")
        raise HTTPException(status_code=400, detail=err_str)
    except Exception as e:
        logger.exception("Failed to update flashcard")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/study/documents/{doc_id}/flashcards/{card_id}")
async def delete_document_flashcard(doc_id: str, card_id: str):
    validate_doc_id_param(doc_id)
    try:
        success = delete_flashcard(doc_id, card_id)
        if not success:
            raise HTTPException(status_code=404, detail="闪卡未找到或已被删除")
        return {"code": 200, "data": {"success": True}, "message": "闪卡已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete flashcard")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/study/documents/{doc_id}/flashcards/batch_delete")
async def batch_delete_flashcards_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    card_ids = body.get("card_ids", [])
    if not isinstance(card_ids, list):
        raise HTTPException(status_code=400, detail="card_ids list is required")

    try:
        count = batch_delete_flashcards(doc_id, card_ids)
        return {"code": 200, "data": {"deleted_count": count}, "message": f"成功删除 {count} 张闪卡"}
    except Exception as e:
        logger.exception("Failed to batch delete flashcards")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/study/documents/{doc_id}/flashcards/{card_id}/review")
async def review_document_flashcard(request: Request, doc_id: str, card_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    rating = body.get("rating")
    if rating is None or not isinstance(rating, int) or rating not in (1, 2, 3, 4, 5):
        raise HTTPException(status_code=400, detail="rating 必须为 1(Again), 2(Hard), 3(Good), 4(Easy) 或 1-5 评分")

    try:
        card = record_card_review(doc_id, card_id, int(rating))
        return {"code": 200, "data": card, "message": "复习记录已更新"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Review flashcard failed")
        raise HTTPException(status_code=500, detail=f"复习更新失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/flashcards/clear_errors")
async def clear_document_flashcard_errors(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        body = {}

    card_id = body.get("card_id")
    try:
        cleared_count = clear_card_errors(doc_id, card_id)
        return {"code": 200, "data": {"cleared_count": cleared_count}, "message": f"已将 {cleared_count} 张闪卡从错题本中移出"}
    except Exception as e:
        logger.exception("Failed to clear card errors")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/study/documents/{doc_id}/flashcards/stats")
async def get_document_flashcards_stats(doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        stats = get_flashcard_statistics(doc_id)
        return {"code": 200, "data": stats}
    except Exception as e:
        logger.exception("Failed to get flashcard statistics")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/study/documents/{doc_id}/flashcards/settings")
async def save_document_flashcards_settings(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        saved = update_flashcard_settings(doc_id, body)
        return {"code": 200, "data": saved, "message": "闪卡设置已保存"}
    except Exception as e:
        logger.exception("Failed to save flashcard settings")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/study/documents/{doc_id}/flashcards/chat")
async def flashcard_chat_endpoint(request: Request, doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    user_message = body.get("message") or body.get("prompt")
    card_data = body.get("card_data") or body.get("card") or {
        "id": body.get("card_id", ""),
        "type": body.get("type", "qa"),
        "front": body.get("front", ""),
        "back": body.get("back", ""),
        "chapter_title": body.get("chapter_title", ""),
        "tags": body.get("tags", []),
    }
    history = body.get("history") or body.get("chat_history") or []
    provider_override = body.get("provider")
    model_override = body.get("model")

    if not user_message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    try:
        gen = study_service.stream_flashcard_chat(
            doc_id=doc_id,
            card_data=card_data,
            user_message=user_message,
            history=history,
            provider_override=provider_override,
            model_override=model_override,
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except Exception as e:
        logger.exception("Flashcard chat failed")
        raise HTTPException(status_code=500, detail=f"闪卡伴读对话失败: {str(e)}")

# Anki .apkg Export Endpoints (Item 14)
@router.get("/api/study/documents/{doc_id}/flashcards/export/anki")
async def export_document_flashcards_anki(doc_id: str):
    validate_doc_id_param(doc_id)
    meta = study_service.load_doc_meta(doc_id)
    doc_title = (meta.get("filename") or meta.get("title") or "未命名文献") if meta else "未命名文献"
    
    data = load_doc_flashcards(doc_id)
    cards = data.get("cards", [])
    if not cards:
        raise HTTPException(status_code=400, detail="当前文档暂无闪卡可导出")

    clean_deck_name = f"Omnididact::{doc_title}"
    apkg_bytes = export_flashcards_to_apkg_bytes(cards, deck_name=clean_deck_name, doc_title=doc_title)

    filename = f"{doc_title}_flashcards.apkg"
    ascii_filename = "flashcards.apkg"
    encoded_filename = quote(filename)

    return Response(
        content=apkg_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}",
            "Content-Type": "application/octet-stream",
        },
    )

@router.get("/api/study/flashcards/export/anki")
async def export_all_flashcards_anki():
    docs = study_service.list_all_documents()
    all_cards = []
    for d in docs:
        d_id = d.get("doc_id")
        if d_id:
            fc_data = load_doc_flashcards(d_id)
            for c in fc_data.get("cards", []):
                c_copy = dict(c)
                c_copy["doc_title"] = d.get("filename") or d.get("title") or d_id
                all_cards.append(c_copy)

    if not all_cards:
        raise HTTPException(status_code=400, detail="当前知识库暂无任何闪卡可导出")

    apkg_bytes = export_flashcards_to_apkg_bytes(all_cards, deck_name="Omnididact 全知识库闪卡", doc_title="全知识库")
    filename = "omnididact_all_flashcards.apkg"
    encoded_filename = quote(filename)

    return Response(
        content=apkg_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}",
            "Content-Type": "application/octet-stream",
        },
    )
