import os
import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
import study as study_service
import config_store
from auth import is_auth_required, is_request_authenticated

logger = logging.getLogger("study-router-docs")
router = APIRouter()

def validate_doc_id_param(doc_id: str) -> str:
    try:
        return study_service.validate_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid doc_id format: {doc_id}")

@router.get("/study", response_class=HTMLResponse)
async def get_study_page(request: Request):
    if is_auth_required() and not is_request_authenticated(request):
        return RedirectResponse(url="/login?redirect=/study", status_code=303)
    dist_html = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(dist_html):
        try:
            with open(dist_html, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.warning(f"Failed to read frontend dist: {e}")

    # Fallback to a clean UI page if frontend has not been built
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>Omnididact · 研学中心</title></head>
    <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #0f172a; color: #e2e8f0;">
        <div style="text-align: center; max-width: 500px; padding: 24px; border: 1px solid #334155; border-radius: 12px; background: #1e293b;">
            <h2>🤖 Omnididact 研学服务正在运行</h2>
            <p style="color: #94a3b8; font-size: 14px;">前端构建产物未找到，请在 <code>frontend/</code> 目录运行 <code>npm run build</code> 构建完整前端界面。</p>
        </div>
    </body>
    </html>
    """)

@router.get("/api/study/documents")
async def get_documents_list():
    docs = study_service.list_all_documents()
    return {"code": 200, "data": docs}

@router.post("/api/study/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename or "document.pdf"
        meta = await study_service.initialize_document(content, filename)
        doc_id = meta["doc_id"]
        import asyncio
        asyncio.create_task(study_service.process_document_pipeline(doc_id))
        return {"code": 200, "data": meta, "message": "文件上传成功，正在启动提取与翻译任务"}
    except Exception as e:
        logger.exception("Upload document failed")
        raise HTTPException(status_code=500, detail=f"上传处理失败: {str(e)}")

@router.post("/api/study/documents/inspect-url")
async def inspect_url_endpoint(req: Request):
    try:
        body = await req.json()
        url = body.get("url", "").strip()

        if not url:
            raise HTTPException(status_code=400, detail="URL 不能为空")

        result = await study_service.inspect_web_series(url)
        return {"code": 200, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Inspect URL failed")
        raise HTTPException(status_code=500, detail=f"网页探测分析失败: {str(e)}")

@router.post("/api/study/documents/import-url")
async def import_url_endpoint(req: Request):
    try:
        body = await req.json()
        url = body.get("url", "").strip()
        title = body.get("title", "").strip()
        selected_chapters = body.get("selected_chapters", [])
        fetch_mode = body.get("fetch_mode", "static")

        if not url:
            raise HTTPException(status_code=400, detail="URL 不能为空")

        meta = await study_service.initialize_web_document(
            url=url,
            title=title,
            selected_chapters=selected_chapters,
            fetch_mode=fetch_mode
        )
        doc_id = meta["doc_id"]
        import asyncio
        asyncio.create_task(study_service.process_document_pipeline(doc_id))
        return {"code": 200, "data": meta, "message": "网页文档任务已创建，正在开始抓取与提取"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import URL failed")
        raise HTTPException(status_code=500, detail=f"网页导入失败: {str(e)}")

@router.post("/api/study/documents/import-folder")
async def import_folder_endpoint(
    files: List[UploadFile] = File(...),
    folder_name: str = Form("Markdown Folder")
):
    try:
        import zipfile
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                file_bytes = await f.read()
                fname = f.filename or "doc.md"
                zf.writestr(fname, file_bytes)

        zip_bytes = zip_buffer.getvalue()
        zip_filename = f"{folder_name.strip() or 'markdown_project'}.zip"
        meta = await study_service.initialize_document(zip_bytes, zip_filename)
        doc_id = meta["doc_id"]
        import asyncio
        asyncio.create_task(study_service.process_document_pipeline(doc_id))
        return {"code": 200, "data": meta, "message": "文件夹资料包上传成功，已启动结构化解析"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import folder failed")
        raise HTTPException(status_code=500, detail=f"文件夹导入失败: {str(e)}")

@router.get("/api/study/documents/{doc_id}")
async def get_document_detail(doc_id: str):
    validate_doc_id_param(doc_id)
    meta = study_service.load_doc_meta(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"code": 200, "data": meta}

@router.delete("/api/study/documents/{doc_id}")
async def delete_document(doc_id: str):
    validate_doc_id_param(doc_id)
    success = study_service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在或删除失败")
    return {"code": 200, "message": "文档删除成功"}

@router.post("/api/study/documents/{doc_id}/refetch-failed-chapters")
async def refetch_failed_chapters_endpoint(doc_id: str):
    validate_doc_id_param(doc_id)
    try:
        res = await study_service.refetch_failed_chapters(doc_id)
        return {
            "code": 200,
            "data": res,
            "message": f"重试完成: 成功抓取 {res.get('succeeded', 0)} 章，失败 {res.get('failed', 0)} 章"
        }
    except Exception as e:
        logger.exception("Refetch failed chapters error")
        raise HTTPException(status_code=500, detail=f"重试抓取失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/process")
async def start_process(doc_id: str):
    validate_doc_id_param(doc_id)
    import asyncio
    meta = study_service.load_doc_meta(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")
    asyncio.create_task(study_service.process_document_pipeline(doc_id))
    return {"code": 200, "message": "文档处理任务已启动"}

@router.post("/api/study/documents/{doc_id}/pause")
async def pause_process(doc_id: str):
    validate_doc_id_param(doc_id)
    study_service.pause_document_pipeline(doc_id)
    return {"code": 200, "message": "已发送暂停指令"}

@router.get("/api/study/documents/{doc_id}/chapters/{chapter_id}")
async def get_chapter_detail(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    try:
        data = study_service.load_chapter_data(doc_id, chapter_id)
    except Exception:
        data = None
    if not data:
        raise HTTPException(status_code=404, detail="章节不存在")

    doc_dir = study_service.get_doc_dir(doc_id, create=False)
    md_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.md")
    md_content = ""
    if os.path.exists(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()
        except Exception:
            pass

    doc_settings = study_service.get_study_settings(doc_id)
    data["doc_settings"] = doc_settings

    has_failed, failed_cnt, failed_list = study_service.check_web_doc_has_missing_or_failed(
        study_service.load_doc_meta(doc_id),
        doc_dir
    )
    data["has_failed_chapters"] = has_failed
    data["failed_chapter_count"] = failed_cnt

    return {
        "code": 200,
        "data": {
            "chapter": data,
            "markdown": md_content,
            **data
        }
    }

@router.get("/api/study/documents/{doc_id}/chapter/{chapter_id}", include_in_schema=False)
async def get_chapter_detail_legacy(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}")
async def delete_chapter_endpoint(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    try:
        updated_meta = study_service.delete_chapter(doc_id, chapter_id)
        return {
            "code": 200,
            "data": updated_meta,
            "message": f"章节 {chapter_id} 已彻底删除"
        }
    except Exception as e:
        logger.exception("Delete chapter failed")
        raise HTTPException(status_code=500, detail=f"删除章节失败: {str(e)}")

@router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}", include_in_schema=False)
async def delete_chapter_endpoint_legacy(doc_id: str, chapter_id: str):
    validate_doc_id_param(doc_id)
    return RedirectResponse(
        url=f"/api/study/documents/{doc_id}/chapters/{chapter_id}",
        status_code=307,
        headers={"Deprecation": "true", "Warning": '299 - "Deprecated URI pattern /chapter/, use /chapters/"'}
    )

@router.patch("/api/study/documents/{doc_id}/chapters/{chapter_id}/rename")
@router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/rename")
async def rename_chapter_endpoint(doc_id: str, chapter_id: str, request: Request):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
        new_title = body.get("title", "").strip()
        if not new_title:
            raise HTTPException(status_code=400, detail="新章节标题不能为空")

        updated_meta = study_service.rename_chapter(doc_id, chapter_id, new_title)
        return {
            "code": 200,
            "data": updated_meta,
            "message": f"章节已重命名为: {new_title}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Rename chapter failed")
        raise HTTPException(status_code=500, detail=f"重命名章节失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}/shift_chapter")
async def shift_paragraph_chapter_endpoint(doc_id: str, chapter_id: str, paragraph_id: str, request: Request):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
        target_direction = body.get("direction", "prev").strip()
        scope = body.get("scope", "single").strip()

        if target_direction not in ("prev", "next"):
            raise HTTPException(status_code=400, detail="direction 必须为 prev 或 next")

        updated_meta = study_service.shift_chapter_paragraphs(
            doc_id, chapter_id, paragraph_id, target_direction, scope
        )
        return {
            "code": 200,
            "data": updated_meta,
            "message": "跨章节段落转移成功"
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Shift paragraph chapter failed")
        raise HTTPException(status_code=500, detail=f"移动段落失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}/split_chapter")
async def split_chapter_at_paragraph_endpoint(doc_id: str, chapter_id: str, paragraph_id: str, request: Request):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
        new_chapter_title = body.get("new_title", "").strip() or body.get("title", "").strip() or "新章节"

        res = study_service.split_chapter_from_paragraph(
            doc_id, chapter_id, paragraph_id, new_chapter_title
        )
        return {
            "code": 200,
            "data": res,
            "message": "从段落拆分新章节成功"
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Split chapter failed")
        raise HTTPException(status_code=500, detail=f"拆分章节失败: {str(e)}")

@router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}")
async def update_paragraph_endpoint(doc_id: str, chapter_id: str, paragraph_id: str, request: Request):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    source_text = body.get("source_text")
    if source_text is None:
        source_text = body.get("english")

    if source_text is None and "chinese" not in body and "status" not in body:
        raise HTTPException(status_code=400, detail="至少需要提供 source_text / english, chinese 或 status 字段")

    is_heading = body.get("is_heading")
    retranslate = body.get("retranslate", False)
    new_paragraph_text = body.get("new_paragraph_text")
    paragraph_type = body.get("type") or body.get("paragraph_type")

    try:
        updated_p = None
        if source_text is not None or is_heading is not None or paragraph_type is not None:
            updated_p = study_service.edit_paragraph_content(
                doc_id=doc_id,
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                source_text=source_text if source_text is not None else "",
                is_heading=is_heading,
                paragraph_type=paragraph_type
            )

        if "chinese" in body or "status" in body:
            doc_dir = study_service.get_doc_dir(doc_id)
            ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
            if os.path.exists(ch_json_path):
                with open(ch_json_path, "r", encoding="utf-8") as f:
                    ch_data = json.load(f)
                for p in ch_data.get("paragraphs", []):
                    if p["id"] == paragraph_id:
                        if "chinese" in body:
                            p["chinese"] = body["chinese"]
                        if "status" in body:
                            p["status"] = body["status"]
                        updated_p = p
                        break
                meta = study_service.load_doc_meta(doc_id) or {}
                study_service.write_chapter_files(doc_id, ch_data, meta.get("language", "en"))

        new_p = None
        if new_paragraph_text and new_paragraph_text.strip():
            new_p = study_service.insert_paragraph_after(
                doc_id=doc_id,
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                new_text=new_paragraph_text.strip()
            )

        if retranslate and updated_p:
            updated_p = await study_service.translate_single_paragraph(doc_id, chapter_id, paragraph_id)
            if new_p:
                new_p = await study_service.translate_single_paragraph(doc_id, chapter_id, new_p["id"])

        res_data = {
            **(updated_p or {}),
            "updated_paragraph": updated_p,
            "new_paragraph": new_p
        }
        return {"code": 200, "data": res_data, "message": "段落修改已保存"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Update paragraph failed")
        raise HTTPException(status_code=500, detail=f"更新段落失败: {str(e)}")

@router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}/merge")
async def merge_paragraph_endpoint(doc_id: str, chapter_id: str, paragraph_id: str, request: Request):
    validate_doc_id_param(doc_id)
    try:
        body = await request.json()
    except Exception:
        body = {}
    direction = body.get("direction", "next").strip()
    if direction not in ("prev", "next"):
        raise HTTPException(status_code=400, detail="direction 必须为 prev 或 next")
    retranslate = body.get("retranslate", False)
    try:
        res = study_service.merge_paragraphs(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            direction=direction
        )
        if retranslate:
            merged_p = res.get("merged_paragraph", {})
            if merged_p.get("id"):
                updated_p = await study_service.translate_single_paragraph(doc_id, chapter_id, merged_p["id"])
                res["merged_paragraph"] = updated_p
        return {
            "code": 200,
            "data": res,
            "message": "段落合并成功"
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Merge paragraph failed")
        raise HTTPException(status_code=500, detail=f"合并段落失败: {str(e)}")

@router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}")
async def delete_paragraph_endpoint(doc_id: str, chapter_id: str, paragraph_id: str):
    validate_doc_id_param(doc_id)
    try:
        removed_id = study_service.delete_paragraph(doc_id, chapter_id, paragraph_id)
        return {
            "code": 200,
            "data": {"removed_id": removed_id},
            "message": f"段落 {removed_id} 已删除"
        }
    except Exception as e:
        logger.exception("Delete paragraph failed")
        raise HTTPException(status_code=500, detail=f"删除段落失败: {str(e)}")

# Image serving with path traversal protection (Item 05) - NO os.makedirs
@router.get("/api/study/documents/{doc_id}/images/{img_name}")
async def get_document_image(doc_id: str, img_name: str):
    validate_doc_id_param(doc_id)
    # Safe basename and containment validation
    safe_name = os.path.basename(img_name.strip())
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid image name")

    doc_dir = study_service.get_doc_dir(doc_id, create=False)
    images_dir = Path(doc_dir).resolve() / "images"
    target_file = (images_dir / safe_name).resolve()

    try:
        target_file.relative_to(images_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path traversal attempt")

    if not target_file.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")

    return FileResponse(str(target_file))

@router.get("/api/study/documents/{doc_id}/asset_inspection")
async def get_document_asset_inspection(doc_id: str):
    validate_doc_id_param(doc_id)
    doc_dir = study_service.get_doc_dir(doc_id, create=False)
    report_path = os.path.join(doc_dir, "asset_inspection.json")
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            return {"code": 200, "data": report}
        except Exception as e:
            logger.warning(f"Failed to read asset inspection report: {e}")

    from study.asset_inspector import AssetInspector
    report = await AssetInspector.inspect_and_remediate(doc_id)
    return {"code": 200, "data": report}

@router.post("/api/study/documents/{doc_id}/re_inspect_assets")
async def re_inspect_document_assets(doc_id: str):
    validate_doc_id_param(doc_id)
    from study.asset_inspector import AssetInspector
    report = await AssetInspector.inspect_and_remediate(doc_id)
    return {"code": 200, "data": report, "message": "静态资源重新检查与路径修复完成"}

@router.get("/api/study/documents/{doc_id}/digests/status")
async def get_document_digests_status(doc_id: str):
    validate_doc_id_param(doc_id)
    from study.document_chat import get_document_digests_status as doc_digest_status
    status = await doc_digest_status(doc_id)
    return {"code": 200, "data": status}

@router.post("/api/study/documents/{doc_id}/digests/context")
async def build_digest_context_endpoint(doc_id: str, req: Request):
    validate_doc_id_param(doc_id)
    try:
        body = await req.json()
    except Exception:
        body = {}
    from study.document_chat import assemble_document_global_context
    try:
        ctx = await assemble_document_global_context(doc_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"code": 200, "data": {"context": ctx}}

@router.get("/api/study/settings")
async def get_settings_endpoint(doc_id: Optional[str] = None):
    settings = study_service.get_study_settings(doc_id)
    return {"code": 200, "data": settings}

@router.post("/api/study/settings")
async def save_settings_endpoint(request: Request, doc_id: Optional[str] = None):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    saved = study_service.save_study_settings(body, doc_id)
    return {"code": 200, "data": saved, "message": "设置已更新"}

@router.post("/api/study/documents/{doc_id}/settings/reset")
async def reset_doc_settings_endpoint(doc_id: str):
    validate_doc_id_param(doc_id)
    res = study_service.reset_doc_settings(doc_id)
    return {"code": 200, "data": res, "message": "已重置为全局默认配置"}

@router.post("/api/study/settings/test_lm_studio")
async def test_lm_studio_endpoint_route(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    base_url = body.get("lm_studio_base_url")
    if base_url:
        res = await study_service.test_lm_studio_endpoint(base_url)
    else:
        res = await study_service.test_lm_studio_endpoint()
    return {"code": 200, "data": res}
