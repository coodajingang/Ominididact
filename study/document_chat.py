import os
import json
import time
import hashlib
import logging
import asyncio
from typing import List, Dict, Any, Tuple, Optional, AsyncGenerator

from study.service import get_doc_dir, load_doc_meta, get_study_settings
from providers import get_provider_for_task
from providers.base import StreamChunk, chunk_to_sse

logger = logging.getLogger("study-document-chat")

# Threshold configuration for chapter compression
CHAPTER_RAW_THRESHOLD = 2500       # If chapter characters <= 2500, use raw content without compression
TARGET_DIGEST_CHARS = 1000         # Target characters when compressing a long chapter
MAX_GLOBAL_DOC_CHARS = 24000       # Global context maximum character budget

def get_digests_dir(doc_dir: str) -> str:
    digests_dir = os.path.join(doc_dir, "digests")
    os.makedirs(digests_dir, exist_ok=True)
    return digests_dir

def get_chapter_readable_text(doc_dir: str, chapter_id: str) -> Tuple[str, str, int]:
    """
    Reads chapter JSON and returns (title, assembled_readable_text, char_count).
    """
    ch_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_path):
        return chapter_id, "", 0

    try:
        with open(ch_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read chapter {chapter_id} JSON: {e}")
        return chapter_id, "", 0

    ch_title = data.get("title") or chapter_id
    paras = data.get("paragraphs", [])

    lines = []
    idx = 1
    for p in paras:
        p_type = p.get("type", "text")
        src = p.get("source_text", "").strip()
        trans = p.get("translated_text", "").strip()
        extracted = p.get("extracted_text", "").strip()

        if p_type in ("scanned_page", "image") or "![" in src:
            content = extracted or (trans if trans and not trans.startswith("[OCR") else "")
            if content:
                lines.append(f"[第 {idx} 单元: 图文内容]:\n{content}")
                idx += 1
        elif src:
            if trans:
                lines.append(f"[第 {idx} 段]: {src}\n[译文/精读]: {trans}")
            else:
                lines.append(f"[第 {idx} 段]: {src}")
            idx += 1

    full_text = "\n\n".join(lines)
    return ch_title, full_text, len(full_text)

async def extract_chapter_digest_with_llm(
    ch_title: str,
    ch_text: str,
    doc_id: str,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
) -> str:
    """
    Extracts high-density structured summary from a long chapter using LLM.
    """
    settings = get_study_settings(doc_id)
    provider = get_provider_for_task("chat", settings, provider_override=provider_override, model_override=model_override)

    # Truncate input if excessively large to avoid single-call token overflow (e.g. max 40k chars)
    truncated_input = ch_text[:40000] if len(ch_text) > 40000 else ch_text

    system_prompt = (
        "你是一位极具洞察力与归纳能力的高级文献学术分析专家。\n"
        "你的任务是为长章节提炼出一份高信息密度、条理清晰的【结构化精要大纲】，供整本书的宏观研学导师作为全局知识底座。\n"
        "请严格控制在 600 ~ 1000 字符以内，绝不要讲空话套话，必须涵盖以下 4 个维度：\n\n"
        "1. 【核心主旨与逻辑主线】：一两句话清晰点明本章核心探讨的主题、解决的问题以及在全书中的承接定位。\n"
        "2. 【关键机制与核心架构】：提炼本章最关键的 2~4 个技术机制、架构组件或工作流程原理。\n"
        "3. 【重要专有术语与规范定义】：列出本章涉及的关键术语/API/协议/规范定义及简要解释。\n"
        "4. 【核心论点与关键考点】：提炼本章最重要的 2~3 条结论性要点与研学重点。\n\n"
        "格式要求：使用紧凑清晰的 Markdown 标题与列表呈现。"
    )

    user_prompt = f"【章节标题】：{ch_title}\n【章节全文（原文及译文节选）】：\n{truncated_input}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        if hasattr(provider, "chat"):
            summary = await provider.chat(messages, {"temperature": 0.2})
            if summary and summary.strip():
                return summary.strip()

        result_chunks = []
        async for chunk in provider.stream_chat(messages, {"temperature": 0.2}):
            if hasattr(chunk, "content") and chunk.content:
                result_chunks.append(chunk.content)
            elif isinstance(chunk, dict):
                c = chunk.get("content") or ""
                if c:
                    result_chunks.append(c)
        summary = "".join(result_chunks).strip()
        if summary:
            return summary
    except Exception as e:
        logger.error(f"Error extracting chapter digest for {ch_title}: {e}")

    # Fallback to smart rule-based extraction if LLM call failed
    return _rule_based_digest_fallback(ch_title, ch_text)

def _rule_based_digest_fallback(ch_title: str, ch_text: str) -> str:
    """Fallback extractor extracting headings and first paragraphs when offline."""
    lines = ch_text.splitlines()
    key_points = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("[第") or len(stripped) > 40:
            if len(key_points) < 8:
                key_points.append("- " + stripped[:120])
    return f"### 《{ch_title}》要点摘要 (快速提取)\n\n" + "\n".join(key_points)

async def get_or_build_chapter_digest(
    doc_id: str,
    chapter_id: str,
    force_refresh: bool = False,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns chapter digest info. If chapter is short, returns raw content.
    If long, checks disk cache or computes LLM digest and caches it.
    """
    doc_dir = get_doc_dir(doc_id)
    digests_dir = get_digests_dir(doc_dir)
    digest_path = os.path.join(digests_dir, f"{chapter_id}.json")

    ch_title, raw_text, char_count = get_chapter_readable_text(doc_dir, chapter_id)
    if not raw_text:
        return {
            "chapter_id": chapter_id,
            "title": ch_title,
            "is_compressed": False,
            "original_char_count": 0,
            "char_count": 0,
            "content": f"（章节《{ch_title}》暂无文字内容）"
        }

    # If chapter is short, no compression needed: 100% fidelity
    if char_count <= CHAPTER_RAW_THRESHOLD:
        return {
            "chapter_id": chapter_id,
            "title": ch_title,
            "is_compressed": False,
            "original_char_count": char_count,
            "char_count": char_count,
            "content": raw_text
        }

    # Long chapter: compute SHA256 of raw text for caching validation
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    if not force_refresh and os.path.exists(digest_path):
        try:
            with open(digest_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("source_hash") == text_hash and cached.get("digest_content"):
                return {
                    "chapter_id": chapter_id,
                    "title": ch_title,
                    "is_compressed": True,
                    "original_char_count": char_count,
                    "char_count": len(cached["digest_content"]),
                    "content": cached["digest_content"],
                    "from_cache": True
                }
        except Exception as e:
            logger.warning(f"Failed to read cached digest for {chapter_id}: {e}")

    # Build digest via LLM
    logger.info(f"Extracting digest for long chapter {chapter_id} ({char_count} chars)...")
    digest_content = await extract_chapter_digest_with_llm(
        ch_title, raw_text, doc_id, provider_override, model_override
    )

    result_data = {
        "chapter_id": chapter_id,
        "title": ch_title,
        "source_hash": text_hash,
        "is_compressed": True,
        "original_char_count": char_count,
        "char_count": len(digest_content),
        "digest_content": digest_content,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        with open(digest_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write digest cache to {digest_path}: {e}")

    return {
        "chapter_id": chapter_id,
        "title": ch_title,
        "is_compressed": True,
        "original_char_count": char_count,
        "char_count": len(digest_content),
        "content": digest_content,
        "from_cache": False
    }

async def assemble_document_global_context(
    doc_id: str,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assembles complete document context across all chapters.
    Applies adaptive compression threshold and respects total global budget.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"文档 {doc_id} 不存在")

    doc_title = meta.get("filename") or "研学文献"
    chapters = meta.get("chapters", [])
    if not chapters:
        return {
            "context_text": f"文献《{doc_title}》暂无章节内容。",
            "total_chars": 0,
            "chapters_info": []
        }

    # Fetch/build digests in parallel for all chapters
    tasks = [
        get_or_build_chapter_digest(
            doc_id,
            ch["chapter_id"],
            force_refresh=False,
            provider_override=provider_override,
            model_override=model_override
        )
        for ch in chapters
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    chapters_info = []
    blocks = []
    total_original_chars = 0
    total_compressed_chars = 0

    header_block = (
        f"【全书全局文献知识图谱与章节概要底座】\n"
        f"文献名称：《{doc_title}》\n"
        f"全书规模：共包含 {len(chapters)} 个核心章节，以下为全书完整结构与高浓度精要网络：\n"
        f"=========================================================="
    )
    blocks.append(header_block)

    for idx, r in enumerate(results, 1):
        if isinstance(r, Exception):
            logger.error(f"Error loading chapter {idx}: {r}")
            continue

        ch_title = r["title"]
        is_comp = r["is_compressed"]
        orig_len = r["original_char_count"]
        comp_len = r["char_count"]
        content = r["content"]

        total_original_chars += orig_len
        total_compressed_chars += comp_len

        tag = f"高浓缩结构化精要 (原文 {orig_len} 字 -> 提炼 {comp_len} 字)" if is_comp else f"完整原文收录 (全章 {orig_len} 字)"
        section_text = (
            f"\n\n### 【第 {idx} 章节】：{ch_title}  [{tag}]\n"
            f"{content.strip()}"
        )
        blocks.append(section_text)
        chapters_info.append({
            "index": idx,
            "chapter_id": r["chapter_id"],
            "title": ch_title,
            "is_compressed": is_comp,
            "original_char_count": orig_len,
            "char_count": comp_len
        })

    assembled_text = "".join(blocks)

    # Budget guard: if still exceeds MAX_GLOBAL_DOC_CHARS, truncate safely with note
    if len(assembled_text) > MAX_GLOBAL_DOC_CHARS:
        assembled_text = assembled_text[:MAX_GLOBAL_DOC_CHARS] + "\n\n...[已达到全书安全上下文最大预算上限]..."

    return {
        "doc_title": doc_title,
        "context_text": assembled_text,
        "total_chars": len(assembled_text),
        "total_original_chars": total_original_chars,
        "total_compressed_chars": total_compressed_chars,
        "chapters_count": len(chapters_info),
        "chapters_info": chapters_info
    }

async def stream_document_chat(
    doc_id: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Performs streaming AI chat across the whole document.
    Assembles all chapter digests into global context.
    """
    try:
        context_data = await assemble_document_global_context(
            doc_id, provider_override=provider_override, model_override=model_override
        )
    except Exception as e:
        logger.exception("Failed to assemble global document context")
        yield f"data: {json.dumps({'error': f'组装全文档全局知识网络失败: {str(e)}'})}\n\n"
        return

    doc_title = context_data.get("doc_title", "全书")
    context_text = context_data["context_text"]
    chapters_count = context_data.get("chapters_count", 1)

    system_prompt = (
        "你是一位博古通今、思维严密、统揽全局的高级学术研学导师与学科领军专家。\n"
        f"当前用户正在与你就整本巨著/技术规范《{doc_title}》（全书共 {chapters_count} 个章节）开展全书宏观研读与系统探讨。\n\n"
        f"{context_text}\n\n"
        "导师全书研学指引原则：\n"
        "1. 【全书宏观视角】：以整本书全部章节构成的知识体系为全局底座，善于跨章节梳理知识架构、脉络演进、设计哲学与逻辑递进关系。\n"
        "2. 【跨章对比与深度论证】：当用户询问特定概念或机制时，不仅给出解答，还要敏锐指出该机制在前后章节（如原理篇与实战攻防篇）中的关联和对比。\n"
        "3. 【结构化高层次解答】：优先使用清晰的 Markdown 标题层级、对比表格、核心要点清单与思维脑图方式组织答案。\n"
        "4. 【启发式内化指导】：在回答末尾，可主动提炼 1~2 个启发性思考或引申考点，帮助读者融会贯通整本书。"
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
        async for chunk in provider.stream_chat(messages, {"temperature": 0.35}):
            if isinstance(chunk, dict):
                chunk_obj = StreamChunk(
                    content=chunk.get("content", ""),
                    reasoning_content=chunk.get("reasoning_content") or chunk.get("reasoning"),
                    done=chunk.get("done", False),
                    error=chunk.get("error")
                )
                sse_line = chunk_to_sse(chunk_obj)
            else:
                sse_line = chunk_to_sse(chunk)
            if sse_line:
                yield sse_line
    except Exception as e:
        logger.exception(f"Document global chat streaming error: {e}")
        yield f"data: {json.dumps({'error': f'全书导师连接异常: {str(e)}'})}\n\n"

async def get_document_digests_status(doc_id: str) -> Dict[str, Any]:
    """
    Returns summary compression and readiness status for all chapters in a document.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        return {"error": "文档不存在"}

    doc_dir = get_doc_dir(doc_id)
    digests_dir = get_digests_dir(doc_dir)
    chapters = meta.get("chapters", [])

    ready_count = 0
    compressed_count = 0
    items = []

    for ch in chapters:
        ch_id = ch["chapter_id"]
        ch_title, _, raw_len = get_chapter_readable_text(doc_dir, ch_id)
        digest_file = os.path.join(digests_dir, f"{ch_id}.json")
        has_cache = os.path.exists(digest_file)

        is_compressed = (raw_len > CHAPTER_RAW_THRESHOLD)
        if is_compressed:
            compressed_count += 1
            if has_cache:
                ready_count += 1
        else:
            ready_count += 1

        items.append({
            "chapter_id": ch_id,
            "title": ch_title,
            "raw_length": raw_len,
            "needs_compression": is_compressed,
            "is_ready": has_cache or not is_compressed
        })

    return {
        "doc_id": doc_id,
        "total_chapters": len(chapters),
        "ready_chapters": ready_count,
        "compressed_chapters": compressed_count,
        "threshold": CHAPTER_RAW_THRESHOLD,
        "items": items
    }
