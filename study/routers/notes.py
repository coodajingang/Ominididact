import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import study as study_service

logger = logging.getLogger("study-router-notes")
router = APIRouter()

def validate_doc_id_param(doc_id: str) -> str:
    try:
        return study_service.validate_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid doc_id format: {doc_id}")

# 1. Paragraph Notes (Item 08: standardized on /chapters/ with 307 redirect for /chapter/)
@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes")
async def add_paragraph_note_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    try:
        note = study_service.add_paragraph_note(doc_id, chapter_id, paragraph_id, content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"code": 200, "data": note, "message": "笔记添加成功"}

@router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/paragraph/{paragraph_id}/notes", include_in_schema=False)
async def add_paragraph_note_legacy(doc_id: str, chapter_id: str, paragraph_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}")
async def update_paragraph_note_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    try:
        note = study_service.update_paragraph_note(doc_id, chapter_id, paragraph_id, note_id, content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"code": 200, "data": note, "message": "笔记修改成功"}

@router.put("/api/study/documents/{doc_id}/chapter/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}", include_in_schema=False)
async def update_paragraph_note_legacy(doc_id: str, chapter_id: str, paragraph_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}")
async def delete_paragraph_note_endpoint(doc_id: str, chapter_id: str, paragraph_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    try:
        success = study_service.delete_paragraph_note(doc_id, chapter_id, paragraph_id, note_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"code": 200, "message": "笔记已删除"}

@router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}", include_in_schema=False)
async def delete_paragraph_note_legacy(doc_id: str, chapter_id: str, paragraph_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

# 2. Chapter Notes (Header / Footer) (Item 08: standardized on /chapters/ with 307 redirect for /chapter/)
@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes")
async def save_chapter_note_endpoint(request: Request, doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    note_type = body.get("position") or body.get("type") or "header"
    title = body.get("title", "")
    content = body.get("content", "")

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    try:
        saved_note = study_service.save_chapter_note(
            doc_id=doc_id,
            chapter_id=chapter_id,
            position=note_type,
            title=title,
            content=content
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"code": 200, "data": saved_note, "message": "章节笔记已保存"}

@router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes", include_in_schema=False)
async def save_chapter_note_legacy(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}")
async def update_chapter_note_endpoint(request: Request, doc_id: str, chapter_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    note_type = body.get("position") or body.get("type") or "header"
    title = body.get("title", "")
    content = body.get("content", "")

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    try:
        updated_note = study_service.update_chapter_note(
            doc_id=doc_id,
            chapter_id=chapter_id,
            position=note_type,
            note_id=note_id,
            new_content=content,
            title=title
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not updated_note:
        raise HTTPException(status_code=404, detail="章节或笔记不存在")
    return {"code": 200, "data": updated_note, "message": "章节笔记已更新"}

@router.put("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes/{note_id}", include_in_schema=False)
async def update_chapter_note_legacy(doc_id: str, chapter_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}")
async def delete_chapter_note_endpoint(doc_id: str, chapter_id: str, note_id: str, position: str = "header"):
    validate_doc_id_param(doc_id)
    try:
        deleted = study_service.delete_chapter_note(doc_id, chapter_id, position, note_id)
        if not deleted:
            other_pos = "footer" if position == "header" else "header"
            deleted = study_service.delete_chapter_note(doc_id, chapter_id, other_pos, note_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="章节或笔记不存在")
    return {"code": 200, "message": "章节笔记已删除"}

@router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes/{note_id}", include_in_schema=False)
async def delete_chapter_note_legacy(doc_id: str, chapter_id: str, note_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes")
async def delete_chapter_notes_by_type_endpoint(doc_id: str, chapter_id: str, type: str = "header"):
    validate_doc_id_param(doc_id)
    try:
        updated_chapter = study_service.delete_chapter_notes(doc_id, chapter_id, type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"code": 200, "data": updated_chapter, "message": f"本章全部 {type} 笔记已清空"}

@router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes", include_in_schema=False)
async def delete_chapter_notes_by_type_legacy(doc_id: str, chapter_id: str, type: str = "header"):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes?type={type}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )
