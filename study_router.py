import os
import json
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse, Response

import study as study_service
import config_store

logger = logging.getLogger("study-router")
study_router = APIRouter()

@study_router.get("/study", response_class=HTMLResponse)
async def get_study_page():
    # Prefer built React frontend if available
    dist_html = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(dist_html):
        try:
            with open(dist_html, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.warning(f"Failed to read frontend dist: {e}")

    template_path = os.path.join("templates", "study.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Template study.html not found.")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read template: {str(e)}")

@study_router.get("/api/study/documents")
async def get_documents_list():
    docs = study_service.list_all_documents()
    return {"code": 200, "data": docs}

@study_router.post("/api/study/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename or "document.pdf"
        meta = await study_service.initialize_document(content, filename)
        # Trigger processing in background
        doc_id = meta["doc_id"]
        import asyncio
        asyncio.create_task(study_service.process_document_pipeline(doc_id))
        return {"code": 200, "data": meta, "message": "文件上传成功，正在启动提取与翻译任务"}
    except Exception as e:
        logger.exception("Upload document failed")
        raise HTTPException(status_code=500, detail=f"上传处理失败: {str(e)}")

@study_router.post("/api/study/documents/inspect-url")
async def inspect_url_endpoint(req: Request):
    try:
        body = await req.json()
        url = body.get("url", "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="URL 不能为空")
        res = await study_service.inspect_web_series(url)
        return {"code": 200, "data": res}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Inspect URL failed")
        raise HTTPException(status_code=500, detail=f"解析网页或系列目录失败: {str(e)}")

@study_router.post("/api/study/documents/import-url")
async def import_url_endpoint(req: Request):
    try:
        body = await req.json()
        url = body.get("url", "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="URL 不能为空")
        title = body.get("title", "").strip()
        selected_chapters = body.get("selected_chapters") or []
        
        meta = await study_service.initialize_web_document(url, title, selected_chapters)
        doc_id = meta["doc_id"]
        import asyncio
        asyncio.create_task(study_service.process_document_pipeline(doc_id))
        return {"code": 200, "data": meta, "message": "网页材料已创建，正在后台抓取与切分..."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import URL failed")
        raise HTTPException(status_code=500, detail=f"导入网页材料失败: {str(e)}")

@study_router.post("/api/study/documents/import-folder")
async def import_folder_endpoint(files: List[UploadFile] = File(...), folder_name: str = Form("Markdown Folder")):
    try:
        import zipfile
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                file_bytes = await f.read()
                # Use filename or webkitRelativePath if present
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
        raise HTTPException(status_code=500, detail=f"导入资料夹失败: {str(e)}")

@study_router.get("/api/study/documents/{doc_id}")
async def get_document_detail(doc_id: str):
    meta = study_service.load_doc_meta(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"code": 200, "data": meta}

@study_router.delete("/api/study/documents/{doc_id}")
async def delete_document_endpoint(doc_id: str):
    success = study_service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档未找到或删除失败")
    return {"code": 200, "message": "文档删除成功"}

@study_router.post("/api/study/documents/{doc_id}/refetch-failed-chapters")
async def refetch_failed_chapters_endpoint(doc_id: str):
    try:
        res = await study_service.refetch_failed_chapters(doc_id)
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Refetch failed chapters for {doc_id} failed: {e}")
        raise HTTPException(status_code=500, detail=f"重抓失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/process")
async def process_document_endpoint(doc_id: str):
    meta = study_service.load_doc_meta(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")
        
    import asyncio
    asyncio.create_task(study_service.process_document_pipeline(doc_id))
    return {"code": 200, "message": "任务已启动/已恢复"}

@study_router.post("/api/study/documents/{doc_id}/pause")
async def pause_document_endpoint(doc_id: str):
    study_service.pause_document_pipeline(doc_id)
    return {"code": 200, "message": "任务已暂停"}

@study_router.get("/api/study/documents/{doc_id}/chapter/{chapter_id}")
async def get_chapter_detail(doc_id: str, chapter_id: str):
    doc_dir = study_service.get_doc_dir(doc_id)
    json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    md_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.md")
    
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail=f"章节 {chapter_id} 不存在")
        
    with open(json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)
        
    md_content = ""
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
            
    return {
        "code": 200,
        "data": {
            "chapter": ch_data,
            "markdown": md_content
        }
    }

@study_router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}")
@study_router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}")
async def delete_chapter_endpoint(doc_id: str, chapter_id: str):
    try:
        res = study_service.delete_chapter(doc_id, chapter_id)
        return {"code": 200, "data": res, "message": "章节及对应闪卡删除成功"}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.exception("Delete chapter failed")
        raise HTTPException(status_code=500, detail=f"删除章节失败: {str(e)}")

@study_router.patch("/api/study/documents/{doc_id}/chapters/{chapter_id}/rename")
@study_router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/rename")
async def rename_chapter_endpoint(request: Request, doc_id: str, chapter_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="章节标题不能为空")
    try:
        res = study_service.rename_chapter(doc_id, chapter_id, title)
        return {"code": 200, "data": res, "message": "章节重命名成功"}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.exception("Rename chapter failed")
        raise HTTPException(status_code=500, detail=f"重命名章节失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}/shift_chapter")
async def shift_chapter_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str):
    try:
        body = await request.json()
    except Exception:
        body = {}
    direction = body.get("direction", "prev")
    try:
        res = study_service.shift_chapter_paragraphs(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            direction=direction
        )
        return {"code": 200, "data": res, "message": "跨章节段落合并成功"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Shift chapter paragraphs failed")
        raise HTTPException(status_code=500, detail=f"跨章节合并段落失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}/split_chapter")
async def split_chapter_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str):
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_title = body.get("new_title", "").strip() or "新章节"
    try:
        res = study_service.split_chapter_from_paragraph(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            new_title=new_title
        )
        return {"code": 200, "data": res, "message": "从段落拆分新章节成功"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Split chapter failed")
        raise HTTPException(status_code=500, detail=f"拆分章节失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/translate_paragraph")
async def translate_paragraph_endpoint(request: Request, doc_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    if not chapter_id or not paragraph_id:
        raise HTTPException(status_code=400, detail="chapter_id and paragraph_id are required")
        
    try:
        updated_p = await study_service.translate_single_paragraph(doc_id, chapter_id, paragraph_id)
        return {"code": 200, "data": updated_p, "message": "段落翻译成功"}
    except Exception as e:
        logger.exception("Paragraph translation failed")
        raise HTTPException(status_code=500, detail=f"段落翻译异常: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/paragraphs/extract_text")
async def extract_paragraph_text_endpoint(request: Request, doc_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    if not chapter_id or not paragraph_id:
        raise HTTPException(status_code=400, detail="chapter_id and paragraph_id are required")
        
    try:
        from study.service import extract_paragraph_text_content
        updated_p = await extract_paragraph_text_content(doc_id, chapter_id, paragraph_id)
        return {"code": 200, "data": updated_p, "message": "图文内容提取成功"}
    except Exception as e:
        logger.exception("Paragraph text extraction failed")
        raise HTTPException(status_code=500, detail=f"图文内容提取失败: {str(e)}")

@study_router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}")
async def edit_paragraph_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    source_text = body.get("source_text")
    if source_text is None:
        raise HTTPException(status_code=400, detail="source_text is required")

    is_heading = body.get("is_heading")
    retranslate = body.get("retranslate", False)
    new_paragraph_text = body.get("new_paragraph_text")
    paragraph_type = body.get("type") or body.get("paragraph_type")

    try:
        updated_p = study_service.edit_paragraph_content(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            source_text=source_text,
            is_heading=is_heading,
            paragraph_type=paragraph_type
        )
        new_p = None
        if new_paragraph_text and new_paragraph_text.strip():
            new_p = study_service.insert_paragraph_after(
                doc_id=doc_id,
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                new_text=new_paragraph_text.strip()
            )
        if retranslate:
            updated_p = await study_service.translate_single_paragraph(doc_id, chapter_id, paragraph_id)
            if new_p:
                new_p = await study_service.translate_single_paragraph(doc_id, chapter_id, new_p["id"])

        res_data = {
            **updated_p,
            "updated_paragraph": updated_p,
            "new_paragraph": new_p
        }
        return {"code": 200, "data": res_data, "message": "段落内容修改成功"}
    except Exception as e:
        logger.exception("Edit paragraph failed")
        raise HTTPException(status_code=500, detail=f"修改段落失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}/merge")
async def merge_paragraph_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str):
    try:
        body = await request.json()
    except Exception:
        body = {}

    direction = body.get("direction", "next")
    retranslate = body.get("retranslate", False)

    try:
        res = study_service.merge_paragraphs(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            direction=direction
        )
        if retranslate:
            merged_p = res["merged_paragraph"]
            updated_p = await study_service.translate_single_paragraph(doc_id, chapter_id, merged_p["id"])
            res["merged_paragraph"] = updated_p
        return {"code": 200, "data": res, "message": "段落合并成功"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Merge paragraph failed")
        raise HTTPException(status_code=500, detail=f"合并段落失败: {str(e)}")

@study_router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}")
async def delete_paragraph_endpoint(doc_id: str, chapter_id: str, paragraph_id: str):
    try:
        res = study_service.delete_paragraph(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id
        )
        return {"code": 200, "data": res, "message": "段落删除成功"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Delete paragraph failed")
        raise HTTPException(status_code=500, detail=f"删除段落失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/translate_start")
async def start_chapter_translate_endpoint(doc_id: str, chapter_id: str):
    try:
        res = await study_service.start_chapter_translation(doc_id, chapter_id)
        return res
    except Exception as e:
        logger.exception("Start chapter translation failed")
        raise HTTPException(status_code=500, detail=f"启动章节翻译失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/translate_stop")
async def stop_chapter_translate_endpoint(doc_id: str, chapter_id: str):
    try:
        res = await study_service.stop_chapter_translation(doc_id, chapter_id)
        return res
    except Exception as e:
        logger.exception("Stop chapter translation failed")
        raise HTTPException(status_code=500, detail=f"停止章节翻译失败: {str(e)}")

@study_router.get("/api/study/documents/{doc_id}/chapter/{chapter_id}/translate_status")
async def get_chapter_translate_status_endpoint(doc_id: str, chapter_id: str):
    try:
        status = study_service.get_chapter_translation_status(doc_id, chapter_id)
        return {"code": 200, "data": status}
    except Exception as e:
        logger.exception("Get chapter translation status failed")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/translate_start")
async def start_document_translate_endpoint(doc_id: str):
    try:
        res = await study_service.start_document_translation(doc_id)
        return res
    except Exception as e:
        logger.exception("Start document translation failed")
        raise HTTPException(status_code=500, detail=f"启动文档翻译失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/translate_stop")
async def stop_document_translate_endpoint(doc_id: str):
    try:
        res = await study_service.stop_document_translation(doc_id)
        return res
    except Exception as e:
        logger.exception("Stop document translation failed")
        raise HTTPException(status_code=500, detail=f"停止文档翻译失败: {str(e)}")

@study_router.get("/api/study/documents/{doc_id}/translate_status")
async def get_document_translate_status_endpoint(doc_id: str):
    try:
        status = study_service.get_document_translation_status(doc_id)
        return {"code": 200, "data": status}
    except Exception as e:
        logger.exception("Get document translation status failed")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

# Legacy compatibility for translate_chapter
@study_router.post("/api/study/documents/{doc_id}/translate_chapter")
async def translate_chapter_endpoint(request: Request, doc_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    if not chapter_id:
        raise HTTPException(status_code=400, detail="chapter_id is required")
    return await start_chapter_translate_endpoint(doc_id, chapter_id)


@study_router.get("/api/study/documents/{doc_id}/images/{img_name}")
async def get_document_image(doc_id: str, img_name: str):
    doc_dir = study_service.get_doc_dir(doc_id)
    img_path = os.path.join(doc_dir, "images", img_name)
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(img_path)

@study_router.get("/api/study/documents/{doc_id}/asset_inspection")
async def get_document_asset_inspection(doc_id: str):
    doc_dir = study_service.get_doc_dir(doc_id)
    report_path = os.path.join(doc_dir, "asset_inspection.json")
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            return {"code": 200, "data": report}
        except Exception as e:
            logger.warning(f"Failed to read asset inspection report: {e}")

    # Fallback to computing on the fly
    from study.asset_inspector import AssetInspector
    report = await AssetInspector.inspect_and_remediate(doc_id)
    return {"code": 200, "data": report}

@study_router.post("/api/study/documents/{doc_id}/re_inspect_assets")
async def re_inspect_document_assets(doc_id: str):
    from study.asset_inspector import AssetInspector
    report = await AssetInspector.inspect_and_remediate(doc_id)
    return {"code": 200, "data": report, "message": "静态资源重新检查与路径修复完成"}

@study_router.get("/api/study/documents/{doc_id}/export")
async def export_document(doc_id: str, format: str = "markdown"):
    meta = study_service.load_doc_meta(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")
    raw_name = os.path.splitext(meta.get('filename', 'document'))[0]

    fmt = format.lower().strip()
    if fmt in ("html", "htm", "bilingual_html"):
        html_content = study_service.assemble_full_document_html(doc_id)
        if not html_content:
            raise HTTPException(status_code=404, detail="文档内容尚未生成")
        filename = f"{raw_name}_bilingual.html"
        return Response(
            content=html_content.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    elif fmt in ("flashcards_html", "flashcards", "flashcard_html"):
        flashcards_html = study_service.assemble_offline_flashcards_html(doc_id)
        if not flashcards_html:
            raise HTTPException(status_code=404, detail="未找到该文档的闪卡数据或模板")
        filename = f"{raw_name}_flashcards.html"
        return Response(
            content=flashcards_html.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    elif fmt in ("patch_zip", "patch", "incremental_zip", "subsite_zip"):
        patch_zip_bytes = study_service.assemble_incremental_patch_zip(doc_id)
        if not patch_zip_bytes:
            raise HTTPException(status_code=404, detail="构建增量补丁包失败")
        filename = f"{raw_name}_patch.zip"
        return Response(
            content=patch_zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    elif fmt in ("site_zip", "static_site", "web_bundle", "deploy_zip"):
        site_zip_bytes = study_service.assemble_static_site_zip(doc_id)
        if not site_zip_bytes:
            raise HTTPException(status_code=404, detail="构建静态研学站点包失败")
        filename = f"{raw_name}_static_site.zip"
        return Response(
            content=site_zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    elif fmt in ("markdown_zip", "zip"):
        zip_bytes = study_service.assemble_full_document_zip(doc_id)
        if not zip_bytes:
            raise HTTPException(status_code=404, detail="文档内容尚未生成")
        filename = f"{raw_name}_archive.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    else:
        # Default: self-contained single .md file with Base64 embedded images
        full_md = study_service.assemble_full_document_markdown(doc_id, image_mode="base64")
        if not full_md:
            raise HTTPException(status_code=404, detail="文档内容尚未生成")
        filename = f"{raw_name}_bilingual.md"
        return Response(
            content=full_md.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

@study_router.get("/api/study/library/export")
async def export_library_site(site_title: str = "研学知识库"):
    """
    Exports the entire static Knowledge Base with Central Portal SPA, docs.json,
    and all processed study documents. Ready for 1-click deployment on Cloudflare Pages / Nginx.
    """
    library_zip_bytes = study_service.assemble_library_site_zip(site_title=site_title)
    if not library_zip_bytes:
        raise HTTPException(status_code=500, detail="构建全站多文档知识库包失败")
    filename = "study_library_static_site.zip"
    return Response(
        content=library_zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    )

# ==========================================================
# Chat History Management & Streaming with Persistence
# ==========================================================

@study_router.get("/api/study/documents/{doc_id}/chat_history")
async def get_chat_history_endpoint(
    doc_id: str,
    chat_type: str = "paragraph",
    chapter_id: str = "",
    paragraph_id: Optional[str] = None
):
    doc_dir = study_service.get_doc_dir(doc_id)
    messages = study_service.load_chat_history(doc_dir, chat_type, chapter_id, paragraph_id)
    return {"code": 200, "data": {"messages": messages}}

@study_router.delete("/api/study/documents/{doc_id}/chat_history")
async def clear_chat_history_endpoint(
    doc_id: str,
    chat_type: str = "paragraph",
    chapter_id: str = "",
    paragraph_id: Optional[str] = None
):
    doc_dir = study_service.get_doc_dir(doc_id)
    study_service.clear_chat_history(doc_dir, chat_type, chapter_id, paragraph_id)
    return {"code": 200, "message": "聊天历史已清空"}

@study_router.post("/api/study/documents/{doc_id}/chat_history")
async def save_chat_history_endpoint(
    request: Request,
    doc_id: str,
    chat_type: str = "paragraph",
    chapter_id: str = "",
    paragraph_id: Optional[str] = None
):
    body = await request.json()
    messages = body.get("messages", [])
    doc_dir = study_service.get_doc_dir(doc_id)
    study_service.save_chat_history(doc_dir, chat_type, chapter_id, messages, paragraph_id)
    return {"code": 200, "message": "聊天历史已保存"}

@study_router.post("/api/study/documents/{doc_id}/paragraph_chat")
async def paragraph_chat_endpoint(request: Request, doc_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    paragraph_id = body.get("paragraph_id")
    user_message = body.get("message", "").strip()
    history = body.get("history", [])
    
    prev_count = int(body.get("prev_count", 2))
    next_count = int(body.get("next_count", 2))
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not chapter_id or not paragraph_id or not user_message:
        raise HTTPException(status_code=400, detail="chapter_id, paragraph_id, and message are required")
        
    try:
        stream_gen = study_service.chat_with_paragraph(
            doc_id=doc_id,
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            user_message=user_message,
            history=history,
            prev_count=prev_count,
            next_count=next_count,
            provider_override=provider_override,
            model_override=model_override
        )
        doc_dir = study_service.get_doc_dir(doc_id)
        persisted_stream = study_service.stream_and_persist(
            doc_dir=doc_dir,
            chat_type="paragraph",
            chapter_id=chapter_id,
            paragraph_id=paragraph_id,
            user_message=user_message,
            stream_generator=stream_gen
        )
        return StreamingResponse(
            persisted_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
    except Exception as e:
        logger.exception("Paragraph chat error")
        raise HTTPException(status_code=500, detail=f"AI 对话服务异常: {str(e)}")

# ==========================================================
# Chapter Chat (Whole-chapter Macro Discussion)
# ==========================================================

@study_router.post("/api/study/documents/{doc_id}/chapter_chat")
async def chapter_chat_endpoint(request: Request, doc_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    chapter_id = body.get("chapter_id")
    user_message = body.get("message", "").strip()
    history = body.get("history", [])
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not chapter_id or not user_message:
        raise HTTPException(status_code=400, detail="chapter_id and message are required")
        
    try:
        stream_gen = study_service.stream_chapter_chat(
            doc_id=doc_id,
            chapter_id=chapter_id,
            user_message=user_message,
            history=history,
            provider_override=provider_override,
            model_override=model_override
        )
        doc_dir = study_service.get_doc_dir(doc_id)
        persisted_stream = study_service.stream_and_persist(
            doc_dir=doc_dir,
            chat_type="chapter",
            chapter_id=chapter_id,
            paragraph_id=None,
            user_message=user_message,
            stream_generator=stream_gen
        )
        return StreamingResponse(
            persisted_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
    except Exception as e:
        logger.exception("Chapter chat error")
        raise HTTPException(status_code=500, detail=f"全章对话服务异常: {str(e)}")

# ==========================================================
# Document Chat (Whole-document Global Macro Discussion)
# ==========================================================

@study_router.post("/api/study/documents/{doc_id}/document_chat")
async def document_chat_endpoint(request: Request, doc_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    user_message = body.get("message", "").strip()
    history = body.get("history", [])
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")
        
    try:
        stream_gen = study_service.stream_document_chat(
            doc_id=doc_id,
            user_message=user_message,
            history=history,
            provider_override=provider_override,
            model_override=model_override
        )
        doc_dir = study_service.get_doc_dir(doc_id)
        persisted_stream = study_service.stream_and_persist(
            doc_dir=doc_dir,
            chat_type="document",
            chapter_id="",
            paragraph_id=None,
            user_message=user_message,
            stream_generator=stream_gen
        )
        return StreamingResponse(
            persisted_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
    except Exception as e:
        logger.exception("Document global chat error")
        raise HTTPException(status_code=500, detail=f"全书对话服务异常: {str(e)}")

@study_router.get("/api/study/documents/{doc_id}/digests/status")
async def get_digests_status_endpoint(doc_id: str):
    try:
        status = await study_service.get_document_digests_status(doc_id)
        return {"code": 200, "data": status}
    except Exception as e:
        logger.exception("Get digests status error")
        raise HTTPException(status_code=500, detail=f"获取章节精要状态失败: {str(e)}")

@study_router.post("/api/study/documents/{doc_id}/digests/context")
async def get_document_context_endpoint(doc_id: str):
    try:
        ctx = await study_service.assemble_document_global_context(doc_id)
        return {"code": 200, "data": ctx}
    except Exception as e:
        logger.exception("Get document context error")
        raise HTTPException(status_code=500, detail=f"组装全局上下文失败: {str(e)}")
# Notes and Summaries Management
# ==========================================================

@study_router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/paragraph/{paragraph_id}/notes")
@study_router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes")
async def add_paragraph_note_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    try:
        note = study_service.add_paragraph_note(doc_id, chapter_id, paragraph_id, content)
        return {"code": 200, "data": note, "message": "段落注解添加成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@study_router.put("/api/study/documents/{doc_id}/chapter/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}")
@study_router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}")
async def update_paragraph_note_endpoint(request: Request, doc_id: str, chapter_id: str, paragraph_id: str, note_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    try:
        note = study_service.update_paragraph_note(doc_id, chapter_id, paragraph_id, note_id, content)
        return {"code": 200, "data": note, "message": "段落注解更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@study_router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}")
@study_router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/paragraph/{paragraph_id}/notes/{note_id}")
async def delete_paragraph_note_endpoint(doc_id: str, chapter_id: str, paragraph_id: str, note_id: str):
    try:
        success = study_service.delete_paragraph_note(doc_id, chapter_id, paragraph_id, note_id)
        return {"code": 200, "data": {"success": success}, "message": "段落注解已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@study_router.post("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes")
@study_router.post("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes")
async def add_chapter_note_endpoint(request: Request, doc_id: str, chapter_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    position = body.get("position") or body.get("type") or "header" # header or footer
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    try:
        note = study_service.add_chapter_note(doc_id, chapter_id, position, content)
        return {"code": 200, "data": note, "message": "章节总结添加成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@study_router.put("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes/{note_id}")
@study_router.put("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}")
async def update_chapter_note_endpoint(request: Request, doc_id: str, chapter_id: str, note_id: str):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    position = body.get("position") or body.get("type") or "header"
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    try:
        note = study_service.update_chapter_note(doc_id, chapter_id, position, note_id, content)
        return {"code": 200, "data": note, "message": "章节总结更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@study_router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes/{note_id}")
@study_router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}")
async def delete_chapter_note_endpoint(doc_id: str, chapter_id: str, note_id: str, position: str = "header", type: Optional[str] = None):
    try:
        pos = type or position or "header"
        success = study_service.delete_chapter_note(doc_id, chapter_id, pos, note_id)
        return {"code": 200, "data": {"success": success}, "message": "章节总结已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@study_router.delete("/api/study/documents/{doc_id}/chapter/{chapter_id}/notes")
@study_router.delete("/api/study/documents/{doc_id}/chapters/{chapter_id}/notes")
async def delete_chapter_note_by_query_endpoint(doc_id: str, chapter_id: str, note_id: str, position: str = "header", type: Optional[str] = None):
    try:
        pos = type or position or "header"
        success = study_service.delete_chapter_note(doc_id, chapter_id, pos, note_id)
        return {"code": 200, "data": {"success": success}, "message": "章节总结已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@study_router.get("/api/study/settings")
async def get_settings_endpoint(doc_id: Optional[str] = None):
    return {"code": 200, "data": study_service.get_study_settings(doc_id)}

@study_router.post("/api/study/settings")
async def save_settings_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    doc_id = body.pop("doc_id", None)
    updated = study_service.save_study_settings(body, doc_id=doc_id)
    return {"code": 200, "data": updated, "message": "配置保存成功"}

@study_router.post("/api/study/documents/{doc_id}/settings/reset")
async def reset_doc_settings_endpoint(doc_id: str):
    updated = study_service.reset_doc_settings(doc_id)
    return {"code": 200, "data": updated, "message": "已重置为全局默认配置"}

@study_router.post("/api/study/settings/test_lm_studio")
async def test_lm_studio_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    base_url = body.get("base_url", "http://127.0.0.1:1234/v1")
    result = await study_service.test_lm_studio_endpoint(base_url)
    return {"code": 200, "data": result}

@study_router.get("/api/study/providers")
async def get_providers_endpoint():
    """Returns list of registered LLM providers available in the system."""
    import providers
    return {"code": 200, "data": providers.list_available_providers()}

@study_router.post("/api/study/providers/test")
async def test_provider_endpoint(request: Request):
    """Tests connectivity and lists models for any configured provider."""
    import providers
    try:
        body = await request.json()
    except Exception:
        body = {}
    provider_id = body.get("provider") or body.get("llm_source") or "openai_compatible"
    provider_inst = providers.get_provider(provider_id, body)
    result = await provider_inst.test_connection()
    return {"code": 200, "data": result}

@study_router.post("/api/study/providers/models")
async def get_provider_models_endpoint(request: Request):
    """Fetches list of available models for a given provider."""
    import providers
    try:
        body = await request.json()
    except Exception:
        body = {}
    provider_id = body.get("provider") or body.get("llm_source") or "openai_compatible"
    provider_inst = providers.get_provider(provider_id, body)
    models = await provider_inst.list_models()
    return {"code": 200, "data": models}

@study_router.get("/api/study/providers/config")
async def get_providers_config_endpoint():
    """Returns saved providers configurations and global default models."""
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
    return {
        "code": 200,
        "data": {
            "providers": providers_cfg,
            "defaults": defaults
        }
    }

@study_router.post("/api/study/providers/config")
async def save_providers_config_endpoint(request: Request):
    """Saves providers configurations and global default models into config.json."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    config = config_store.load_config()
    
    # Update providers
    if "providers" in body:
        current_providers = config.get("providers", {})
        current_providers.update(body["providers"])
        config["providers"] = current_providers
        
    # Update default models in study_settings
    if "defaults" in body:
        defaults = body["defaults"]
        study_settings = config.get("study_settings", {})
        for k in ["default_translation_provider", "default_translation_model",
                  "default_chat_provider", "default_chat_model",
                  "default_vlm_provider", "default_vlm_model"]:
            if k in defaults:
                study_settings[k] = defaults[k]
        # Also keep llm_source and text_model aligned for backward compatibility
        if "default_translation_provider" in defaults:
            study_settings["llm_source"] = defaults["default_translation_provider"]
        if "default_translation_model" in defaults:
            study_settings["text_model"] = defaults["default_translation_model"]
        if "default_vlm_model" in defaults:
            study_settings["vlm_model"] = defaults["default_vlm_model"]
            
        config["study_settings"] = study_settings
        
    config_store.save_config(config)
    return {"code": 200, "message": "模型与服务配置已保存"}



# ==========================================================
# Flashcard Management, Learning, and Statistics Endpoints
# ==========================================================

@study_router.get("/study/flashcards", response_class=HTMLResponse)
async def get_flashcards_page():
    template_path = os.path.join("templates", "flashcards.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Template flashcards.html not found.")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read template: {str(e)}")


@study_router.get("/api/study/documents/{doc_id}/flashcards")
async def get_document_flashcards(
    doc_id: str,
    type: Optional[str] = None,
    chapter_id: Optional[str] = None,
    is_error: bool = False,
    keyword: Optional[str] = None
):
    try:
        cards = study_service.list_flashcards(
            doc_id=doc_id,
            filter_type=type,
            chapter_id=chapter_id,
            is_error=is_error,
            keyword=keyword
        )
        stats = study_service.get_flashcard_statistics(doc_id)
        return {
            "code": 200,
            "data": {
                "cards": cards,
                "total": len(cards),
                "summary": stats
            }
        }
    except Exception as e:
        logger.exception("Failed to get flashcards")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.post("/api/study/documents/{doc_id}/flashcards")
async def create_document_flashcard(doc_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        if "cards" in body and isinstance(body["cards"], list):
            created = study_service.batch_create_flashcards(doc_id, body["cards"])
            return {"code": 200, "data": created, "message": f"成功批量导入 {len(created)} 张闪卡"}
        else:
            card = study_service.create_flashcard(doc_id, body)
            return {"code": 200, "data": card, "message": "闪卡添加成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create flashcard")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.put("/api/study/documents/{doc_id}/flashcards/{card_id}")
async def update_document_flashcard(doc_id: str, card_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        updated = study_service.update_flashcard(doc_id, card_id, body)
        return {"code": 200, "data": updated, "message": "闪卡更新成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update flashcard")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.delete("/api/study/documents/{doc_id}/flashcards/{card_id}")
async def delete_document_flashcard(doc_id: str, card_id: str):
    try:
        success = study_service.delete_flashcard(doc_id, card_id)
        if not success:
            raise HTTPException(status_code=404, detail="闪卡未找到或已被删除")
        return {"code": 200, "data": {"success": True}, "message": "闪卡已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete flashcard")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.post("/api/study/documents/{doc_id}/flashcards/batch_delete")
async def batch_delete_flashcards_endpoint(doc_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    card_ids = body.get("card_ids", [])
    if not isinstance(card_ids, list):
        raise HTTPException(status_code=400, detail="card_ids must be a list")
    try:
        count = study_service.batch_delete_flashcards(doc_id, card_ids)
        return {"code": 200, "data": {"deleted_count": count}, "message": f"成功删除 {count} 张闪卡"}
    except Exception as e:
        logger.exception("Failed to batch delete flashcards")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.post("/api/study/documents/{doc_id}/flashcards/{card_id}/review")
async def review_flashcard_endpoint(doc_id: str, card_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    rating = body.get("rating")
    if rating is None or not isinstance(rating, int) or rating not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="rating 必须为 1, 2, 3 或 4")
    try:
        updated = study_service.record_card_review(doc_id, card_id, rating)
        return {"code": 200, "data": updated, "message": "复习记录已保存"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to record flashcard review")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.post("/api/study/documents/{doc_id}/flashcards/clear_errors")
async def clear_flashcard_errors_endpoint(doc_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    card_id = body.get("card_id")
    try:
        cleared = study_service.clear_card_errors(doc_id, card_id)
        return {"code": 200, "data": {"cleared_count": cleared}, "message": f"已重置 {cleared} 张卡片的错题标记"}
    except Exception as e:
        logger.exception("Failed to clear card errors")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.get("/api/study/documents/{doc_id}/flashcards/stats")
async def get_flashcard_stats_endpoint(doc_id: str):
    try:
        stats = study_service.get_flashcard_statistics(doc_id)
        return {"code": 200, "data": stats}
    except Exception as e:
        logger.exception("Failed to get flashcard statistics")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.post("/api/study/documents/{doc_id}/flashcards/settings")
async def update_flashcard_settings_endpoint(doc_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        updated = study_service.update_flashcard_settings(doc_id, body)
        return {"code": 200, "data": updated, "message": "闪卡偏好设置已更新"}
    except Exception as e:
        logger.exception("Failed to update flashcard settings")
        raise HTTPException(status_code=500, detail=str(e))


@study_router.post("/api/study/documents/{doc_id}/flashcards/chat")
async def flashcard_chat_endpoint(doc_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    card_data = body.get("card_data") or {
        "id": body.get("card_id", ""),
        "type": body.get("type", "qa"),
        "front": body.get("front", ""),
        "back": body.get("back", ""),
        "chapter_title": body.get("chapter_title", ""),
        "tags": body.get("tags", [])
    }
    user_message = body.get("message", "")
    history = body.get("history", [])
    provider_override = body.get("provider")
    model_override = body.get("model")
    
    if not user_message:
        raise HTTPException(status_code=400, detail="message 不能为空")
        
    try:
        stream_gen = study_service.stream_flashcard_chat(
            doc_id=doc_id,
            card_data=card_data,
            user_message=user_message,
            history=history,
            provider_override=provider_override,
            model_override=model_override
        )
        return StreamingResponse(stream_gen, media_type="text/event-stream")
    except Exception as e:
        logger.exception("Flashcard chat failed")
        raise HTTPException(status_code=500, detail=str(e))

