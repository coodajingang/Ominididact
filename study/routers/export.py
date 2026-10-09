import io
import os
import time
import zipfile
import logging
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Response
import study as study_service
from study.flashcard_manager import load_doc_flashcards
from study.anki_exporter import export_flashcards_to_apkg_bytes

logger = logging.getLogger("study-router-export")
router = APIRouter()

def validate_doc_id_param(doc_id: str) -> str:
    try:
        return study_service.validate_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid doc_id format: {doc_id}")

@router.get("/api/study/documents/{doc_id}/export")
async def export_document(doc_id: str, format: str = "markdown"):
    validate_doc_id_param(doc_id)
    meta = study_service.load_doc_meta(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="文档不存在")

    doc_title = meta.get("filename") or meta.get("title") or "未命名文档"
    raw_name = os.path.splitext(doc_title)[0]
    doc_title_clean = "".join(c for c in raw_name if c.isalnum() or c in (" ", "_", "-", ".")).strip() or "document"

    fmt = format.lower().strip()
    if fmt in ("html", "htm", "bilingual_html"):
        html_content = study_service.assemble_full_document_html(doc_id)
        if not html_content:
            raise HTTPException(status_code=404, detail="文档内容尚未生成")
        filename = f"{doc_title_clean}_bilingual.html"
        return Response(
            content=html_content.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

    elif fmt in ("flashcards_html", "flashcards", "flashcard_html"):
        flashcards_html = study_service.assemble_offline_flashcards_html(doc_id)
        if not flashcards_html:
            raise HTTPException(status_code=404, detail="未找到该文档的闪卡数据或模板")
        filename = f"{doc_title_clean}_flashcards.html"
        return Response(
            content=flashcards_html.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

    elif fmt in ("patch_zip", "patch", "incremental_zip", "subsite_zip"):
        patch_zip_bytes = study_service.assemble_incremental_patch_zip(doc_id)
        if not patch_zip_bytes:
            raise HTTPException(status_code=404, detail="构建增量补丁包失败")
        filename = f"{doc_title_clean}_patch.zip"
        return Response(
            content=patch_zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

    elif fmt in ("site_zip", "static_site", "web_bundle", "deploy_zip"):
        site_zip_bytes = study_service.assemble_static_site_zip(doc_id)
        if not site_zip_bytes:
            raise HTTPException(status_code=404, detail="构建静态研学站点包失败")
        filename = f"{doc_title_clean}_static_site.zip"
        return Response(
            content=site_zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

    elif fmt in ("markdown_zip", "zip"):
        zip_bytes = study_service.assemble_full_document_zip(doc_id)
        if not zip_bytes:
            raise HTTPException(status_code=404, detail="文档内容尚未生成")
        filename = f"{doc_title_clean}_archive.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

    elif fmt == "raw_markdown":
        md_content = study_service.export_bilingual_markdown(doc_id, embed_images="relative")
        filename = f"{doc_title_clean}_研学原版.md"
        encoded_filename = quote(filename)
        return Response(
            content=md_content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )

    elif fmt == "anki":
        fc_data = load_doc_flashcards(doc_id)
        cards = fc_data.get("cards", [])
        if not cards:
            raise HTTPException(status_code=400, detail="该文档暂无闪卡可供导出")
        
        apkg_bytes = export_flashcards_to_apkg_bytes(cards, deck_name=f"Omnididact::{doc_title}", doc_title=doc_title)
        filename = f"{doc_title_clean}_flashcards.apkg"
        encoded_filename = quote(filename)
        return Response(
            content=apkg_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )

    elif fmt in ("markdown", "md", "bilingual_md"):
        full_md = study_service.assemble_full_document_markdown(doc_id, image_mode="base64")
        if not full_md:
            full_md = study_service.export_bilingual_markdown(doc_id)
        filename = f"{doc_title_clean}_bilingual.md"
        return Response(
            content=full_md.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )

    else:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")

@router.get("/api/study/library/export")
async def export_library_site(site_title: str = "研学知识库"):
    """
    Exports the entire static Knowledge Base with Central Portal SPA, docs.json,
    and all processed study documents.
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
