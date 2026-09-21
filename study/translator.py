import os
import re
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional

import httpx
import config_store
from providers import get_provider, get_provider_for_task
from providers.base import chunk_to_sse

logger = logging.getLogger("study-translator")

# Global lock to ensure single concurrency for LLM calls during translation
MODEL_LOCK = asyncio.Lock()

async def test_lm_studio_endpoint(base_url: str = "http://127.0.0.1:1234/v1") -> Dict[str, Any]:
    """
    Tests connectivity to a local LM Studio server via Provider layer.
    Returns connection status and list of detected loaded models.
    """
    provider = get_provider("lm_studio", {"base_url": base_url})
    return await provider.test_connection()

async def call_vllm_ocr(base64_img: str, settings: Dict[str, Any]) -> str:
    """
    Calls VLM provider/model to perform high-precision OCR on an image.
    Resolves the configured VLM provider (e.g. Cloudflare, LM Studio, etc.) directly.
    """
    async with MODEL_LOCK:
        try:
            provider = get_provider_for_task("vlm", settings)
            logger.info(f"Executing VLM OCR with provider '{provider.provider_id}' ({provider.display_name})")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请高精度识别提取并转录图片中的全部文字内容。按版面顺序保留标题、自然段与列表，保留英文原始拼写与标点，不要添加多余的解释与问候语。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_img}"
                            }
                        }
                    ]
                }
            ]
            ocr_text = await provider.chat(messages, {"temperature": 0.1, "max_tokens": 4096})
            return ocr_text.strip() if ocr_text else ""
        except Exception as e:
            logger.error(f"VLM OCR request failed: {e}", exc_info=True)
            raise e
        finally:
            await asyncio.sleep(settings.get("model_call_delay", 1.0))

async def call_llm_translate_paragraph(
    english_para: str,
    prompt_template: str,
    settings: Dict[str, Any],
    prev_english: Optional[str] = None,
    prev_chinese: Optional[str] = None
) -> str:
    """
    Translates a single English paragraph into Chinese with single concurrency and configurable delay.
    Injects sliding context window (prev_english & prev_chinese) for pronoun & terminology consistency.
    Supports either proxy server or local LM Studio endpoint.
    """
    config = config_store.load_config()
    llm_source = settings.get("llm_source", "proxy")
    
    ref_parts = []
    if prev_english and prev_english.strip():
        ref_parts.append(f"前文段落: {prev_english.strip()}")
    if prev_chinese and prev_chinese.strip():
        ref_parts.append(f"前文译文: {prev_chinese.strip()}")
        
    if ref_parts:
        context_block = (
            "[上下文参考（仅作术语和代词参考，无需重复翻译）]:\n"
            + "\n".join(ref_parts) + "\n\n"
            "[待翻译段落]:\n"
            + english_para.strip()
        )
    else:
        context_block = english_para.strip()
        
    prompt = prompt_template.format(text=context_block)
    
    async with MODEL_LOCK:
        try:
            provider = get_provider_for_task("translation", settings)
            messages = [{"role": "user", "content": prompt}]
            ans = await provider.chat(messages, {"temperature": 0.3})
            return parse_translated_chinese(ans, english_para)
        except Exception as e:
            logger.error(f"Error calling LLM translation: {e}")
            return f"[翻译调用异常: {str(e)}]"
        finally:
            delay = settings.get("model_call_delay", 1.0)
            await asyncio.sleep(delay)

def parse_translated_chinese(model_output: str, original_english: str) -> str:
    """
    Parses model output to extract the complete Chinese translation of the target paragraph.
    Handles outputs with `> ` quotes, multiple sections separated by '---', or plain text.
    Preserves all translated sections while filtering out echoed reference context.
    """
    if not model_output or not model_output.strip():
        return ""

    # Strip explicit prompt delimiters if echoed by model
    cleaned_output = model_output
    for marker in ("[待翻译段落]:", "[待翻译段落]", "【待翻译段落】：", "【待翻译段落】", "[待翻译]:", "【待翻译】："):
        if marker in cleaned_output:
            cleaned_output = cleaned_output.split(marker, 1)[1].strip()
            break

    sections = [s.strip() for s in cleaned_output.split("---") if s.strip()]
    if not sections:
        sections = [cleaned_output.strip()]

    def _join_text_lines(lines: List[str]) -> str:
        res = ""
        for l in lines:
            if not res:
                res = l
            elif re.search(r'[\u4e00-\u9fa5]$', res) and re.search(r'^[\u4e00-\u9fa5]', l):
                res += l
            else:
                res += " " + l
        return res

    def _is_context_echo(sec: str) -> bool:
        first_line = sec.strip().splitlines()[0].strip().lstrip("> ").strip()
        context_markers = ("前文段落", "前文译文", "前文参考", "上下文参考", "前文内容", "【前文", "[前文")
        if any(marker in first_line for marker in context_markers):
            return True
        if first_line.startswith("前文") or sec.strip().startswith("> 前文"):
            return True
        return False

    # Filter out pure context echo sections if multiple sections exist
    if len(sections) > 1:
        valid_sections = [s for s in sections if not _is_context_echo(s)]
        if not valid_sections:
            valid_sections = [sections[-1]]
    else:
        valid_sections = sections

    parsed_sections = []
    for sec in valid_sections:
        lines = sec.split("\n")
        quote_paras = []
        current_quote_lines = []
        plain_paras = []
        current_plain_lines = []

        for l in lines:
            stripped = l.strip()
            if stripped.startswith(">"):
                if current_plain_lines:
                    plain_paras.append(_join_text_lines(current_plain_lines))
                    current_plain_lines = []
                current_quote_lines.append(stripped.lstrip("> ").strip())
            elif not stripped:
                if current_quote_lines:
                    quote_paras.append(_join_text_lines(current_quote_lines))
                    current_quote_lines = []
                if current_plain_lines:
                    plain_paras.append(_join_text_lines(current_plain_lines))
                    current_plain_lines = []
            else:
                if current_quote_lines:
                    quote_paras.append(_join_text_lines(current_quote_lines))
                    current_quote_lines = []
                current_plain_lines.append(stripped)

        if current_quote_lines:
            quote_paras.append(_join_text_lines(current_quote_lines))
        if current_plain_lines:
            plain_paras.append(_join_text_lines(current_plain_lines))

        if quote_paras:
            sec_text = "\n\n".join(quote_paras).strip()
            if sec_text:
                parsed_sections.append(sec_text)
        elif plain_paras:
            # Keep plain text lines with Chinese
            cn_paras = [p for p in plain_paras if re.search(r'[\u4e00-\u9fa5]', p)]
            sec_text = "\n\n".join(cn_paras if cn_paras else plain_paras).strip()
            if sec_text:
                parsed_sections.append(sec_text)

    if parsed_sections:
        return "\n\n".join(parsed_sections)

    return model_output.strip()

async def stream_paragraph_chat(
    target_english: str,
    prev_texts: List[str],
    next_texts: List[str],
    settings: Dict[str, Any],
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_url: Optional[str] = None
):
    """
    Performs streaming chat discussing a specific paragraph with surrounding context.
    Injects:
    - 【前文背景（前 N 段）】
    - 【核心研读段落】
    - 【后文背景（后 M 段）】
    """
    context_sections = []
    if prev_texts:
        prev_combined = "\n\n".join(prev_texts)
        context_sections.append(f"【前文背景（前 {len(prev_texts)} 段）】：\n{prev_combined}")
        
    context_sections.append(f"【核心研读段落】：\n{target_english.strip()}")
    
    if next_texts:
        next_combined = "\n\n".join(next_texts)
        context_sections.append(f"【后文背景（后 {len(next_texts)} 段）】：\n{next_combined}")
        
    full_context_str = "\n\n".join(context_sections)

    system_prompt = (
        "你是一位博学、亲切且专业的双语学术研读与英语教学导师。\n"
        "用户当前正在研读学习以下材料段落及上下文：\n\n"
        f"{full_context_str}\n\n"
        "导师研读指引：\n"
        "1. 请以【核心研读段落】为主要研读与解析对象，结合前文与后文背景提供准确的语境理解；若用户明确要求基于上下文、引用范围或关联段落生成闪卡/总结，请综合前文背景、核心段落及后文背景引用的全部内容进行全局提炼。\n"
        "2. 针对用户提出的疑问、长难句剖析、语法分析、核心术语、逻辑推导或上下文脉络，给出详尽、启发式、结构清晰的解答。\n"
        "3. 解答格式使用规范 Markdown（支持代码块、重点加粗、要点列表）。\n"
        "4. 保持热情、专业与耐心。"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-30:]:
            role = h.get("role", "user")
            content = (h.get("content") or "").strip()
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

    user_payload: Any = user_message
    if image_base64 or image_url:
        img_src = f"data:image/png;base64,{image_base64}" if image_base64 else image_url
        user_payload = [
            {"type": "text", "text": user_message},
            {"type": "image_url", "image_url": {"url": img_src}}
        ]
    messages.append({"role": "user", "content": user_payload})
    
    provider = get_provider_for_task("chat", settings, provider_override=provider_override, model_override=model_override)
    try:
        async for chunk in provider.stream_chat(messages, {"temperature": 0.5}):
            sse_line = chunk_to_sse(chunk)
            if sse_line:
                yield sse_line
    except Exception as e:
        logger.exception(f"Chat streaming error: {e}")
        yield f"data: {json.dumps({'error': f'导师连接异常: {str(e)}'})}\n\n"

async def chat_with_paragraph(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    user_message: str,
    p_english: str,
    settings: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None
):
    """Legacy compatibility adapter."""
    async for chunk in stream_paragraph_chat(
        target_english=p_english,
        prev_texts=[],
        next_texts=[],
        settings=settings,
        user_message=user_message,
        history=history
    ):
        yield chunk

