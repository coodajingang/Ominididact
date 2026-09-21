import os
import json
import logging
from typing import List, Dict, Any, Optional

from study.service import get_doc_dir, get_study_settings
from providers import get_provider, get_provider_for_task
from providers.base import chunk_to_sse

logger = logging.getLogger("study-chapter-chat")

async def stream_chapter_chat(
    doc_id: str,
    chapter_id: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
):
    """
    Performs streaming AI chat discussing the whole chapter.
    Assembles all readable text paragraphs of the chapter as broad context.
    """
    ch_path = os.path.join(get_doc_dir(doc_id), "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_path):
        yield f"data: {json.dumps({'error': f'章节 {chapter_id} 不存在'})}\n\n"
        return

    try:
        with open(ch_path, "r", encoding="utf-8") as f:
            ch_data = json.load(f)
    except Exception as e:
        yield f"data: {json.dumps({'error': f'读取章节数据失败: {str(e)}'})}\n\n"
        return

    ch_title = ch_data.get("title") or chapter_id
    paras = ch_data.get("paragraphs", [])
    
    chapter_body_lines = []
    idx = 1
    for p in paras:
        p_type = p.get("type", "text")
        eng = p.get("english", "").strip()
        extracted = p.get("extracted_text", "").strip()
        chn = p.get("chinese", "").strip()

        # If it's a scanned page / image with extracted text
        if p_type in ("scanned_page", "image") or "![" in eng:
            content_text = extracted or (chn if chn and not chn.startswith("[OCR") else "")
            page_info = f"第 {p.get('page', idx)} 页"
            if content_text:
                line = f"[{page_info} 识别图文内容]:\n{content_text}"
                if chn and chn != content_text and not chn.startswith("[OCR"):
                    line += f"\n[{page_info} 译文/精读]:\n{chn}"
                chapter_body_lines.append(line)
                idx += 1
        elif eng:
            if chn:
                chapter_body_lines.append(f"[段落 {idx} 原文]: {eng}\n[段落 {idx} 译文]: {chn}")
            else:
                chapter_body_lines.append(f"[段落 {idx} 原文]: {eng}")
            idx += 1
            
    chapter_body = "\n\n".join(chapter_body_lines)
    if len(chapter_body) > 16000:
        chapter_body = chapter_body[:16000] + "\n...[篇幅超出限制，后文已截断]..."

    system_prompt = (
        "你是一位博学、严谨、循循善诱的高级研读学术导师与考试专家。\n"
        f"用户当前正在宏观研读探讨【{ch_title}】的全章脉络与核心体系。\n\n"
        f"【全章正文文段节选（共 {len(chapter_body_lines)} 个自然段/单元）】：\n"
        f"{chapter_body}\n\n"
        "导师全章研读指引：\n"
        "1. 请以全章为全局视野，帮助用户梳理全章知识脉络、逻辑演进脉络、核心论点与关键考点。\n"
        "2. 针对用户对全章提出的总结、脉络梳理、核心术语网络或自测复习疑问，给出详尽、结构清晰、启发式的解答。\n"
        "3. 解答格式使用规范 Markdown（善用标题层级、要点列表、重点加粗和表格对比）。\n"
        "4. 保持热情、专业与耐心。"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-30:]:
            role = h.get("role", "user")
            content = (h.get("content") or "").strip()
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    
    settings = get_study_settings(doc_id)
    provider = get_provider_for_task("chat", settings, provider_override=provider_override, model_override=model_override)
    try:
        async for chunk in provider.stream_chat(messages, {"temperature": 0.4}):
            sse_line = chunk_to_sse(chunk)
            if sse_line:
                yield sse_line
    except Exception as e:
        logger.exception(f"Chapter chat streaming error: {e}")
        yield f"data: {json.dumps({'error': f'全章助教连接异常: {str(e)}'})}\n\n"