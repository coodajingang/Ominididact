import os
import re
import json
import time
import uuid
import base64
import asyncio
import logging
import unicodedata
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF
import config_store
import doc_converter
from study.parser import (
    extract_pdf_native,
    render_chapter_markdown,
    detect_language,
    is_predominantly_target_lang,
    repair_english_paragraph,
    is_chapter_heading
)
from study.pdf_parser import (
    extract_pdf_with_pymupdf4llm
)
from study.translator import (
    call_llm_translate_paragraph,
    call_vllm_ocr,
    stream_paragraph_chat,
    test_lm_studio_endpoint,
    MODEL_LOCK
)
from study.text_parser import extract_text_or_markdown_content
from study.chat_manager import (
    load_chat_history,
    save_chat_history,
    clear_chat_history,
)


logger = logging.getLogger("study-service")

BASE_DATA_DIR = os.path.join(os.getcwd(), "data", "documents")
os.makedirs(BASE_DATA_DIR, exist_ok=True)

# Active translation tasks tracking: doc_id -> asyncio.Event
ACTIVE_TASKS: Dict[str, asyncio.Event] = {}

DEFAULT_TRANSLATION_PROMPT = (
    "你是一位资深信息安全（InfoSec / Cybersecurity）专家及 CISSP 官方知识体系（CBK 八大领域）双语翻译导师。\n"
    "请将待翻译的英文学术与认证备考材料翻译为严谨、地道、符合信息安全专业规范的中文译文。\n\n"
    "【核心翻译与排版规范】：\n"
    "1. 【仅输出译文，严禁输出原文】：输出内容必须严格仅包含目标段落的中文翻译。严禁在输出中重复出现英文原文，严禁输出任何多余的开场白、问候语、翻译说明或结尾总结。\n"
    "2. 【CISSP 专业术语精准对应】：严格遵循 CISSP 官方教材与考试大纲权威中文术语规范（如：主体/客体 Subject/Object、机密性/完整性/可用性 CIA 三要素、身份标识/鉴别/授权/问责制 IAAA、访问控制 Access Control、隐含拒绝 Implicit Deny、最小特权 Least Privilege、职责分离 Separation of Duties、防御纵深 Defense-in-Depth 等）。对于核心考点术语，建议在首次出现的中文译名后保留带括号的英文术语（如：隐含拒绝（Implicit Deny）），方便备考记忆与对照。\n"
    "3. 【引用块排版格式】：所有中文译文必须严格采用 Markdown 引用块（以 `> ` 开头）展示。如果原文包含多个逻辑自然段，各段译文均以 `> ` 开头，段落之间用空行隔开。\n"
    "4. 【格式标记严格继承】：严格保留原文中的 Markdown 加粗（`**...**`）、斜体（`*...*`）、行内代码（`` `...` ``）等强调标记，将中文译文中对应的重点词句或考点关键词做相同标记。\n"
    "5. 【语流自然连贯】：自动修复原文断行和单词断连，行文要求逻辑严密、概念清晰，符合中文专业技术文献阅读与考试理解习惯。\n\n"
    "【待处理英文段落】：\n{text}"
)

DEFAULT_PARAGRAPH_QUICK_PROMPTS = [
    {"label": "🔍 长难句剖析", "prompt": "请深度拆解本段的长难句结构、主干成分与关键语法点"},
    {"label": "📖 核心术语提炼", "prompt": "请提炼出本段的核心专业词汇和术语，并给出精准含义与用法语境"},
    {"label": "💡 通俗解释论点", "prompt": "请用通俗易懂的中文和实际例子，解释这一段的核心论点与逻辑"},
    {"label": "❓ 自测思考题", "prompt": "请根据本段内容出一道自测思考题，检验我的理解深度"},
    {"label": "🗂️ 生成本段闪卡", "prompt": "请根据本段的核心考点和学术概念，生成 1~2 张记忆闪卡（包括问答 QA 或挖空 Cloze 题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、解析与备考要点\ntags: 考点, 术语\n:::"},
    {"label": "🗂️ 生成引用范围闪卡", "prompt": "请综合当前【核心研读段落】以及前文背景、后文背景所引用的全部段落，提炼出跨段落的 2~4 张关键考点记忆闪卡（包括问答 QA 或镂空 Cloze 题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: 核心考点, 关联概念\n:::"}
]

DEFAULT_CHAPTER_QUICK_PROMPTS = [
    {"label": "🗺️ 全章脉络主线", "prompt": "请系统性梳理本章的核心论述脉络与逻辑展开主线，说明作者是如何一步步展开推导的。"},
    {"label": "🎯 核心论点清单", "prompt": "请提炼本章最关键的 3~5 个核心论点和学术知识要点，以结构化清单呈现。"},
    {"label": "💡 全景概念总结", "prompt": "请用通俗生动的语言，概括本章的核心思想以及它对读者的主要认知启示。"},
    {"label": "📝 本章考点复习", "prompt": "如果针对本章内容设计专业测评或自测题，最重要的考点和关键概念问答有哪些？"},
    {"label": "🗂️ 生成本章考点闪卡", "prompt": "请根据本章全局核心脉络与关键考点，提炼生成 3~5 张高频复习闪卡（涵盖 QA 问答与 Cloze 镂空题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: CISSP, 章节考点\n:::"}
]

DEFAULT_QUICK_PROMPTS = DEFAULT_PARAGRAPH_QUICK_PROMPTS

# ==========================================================
# Settings & Document Storage Management
# ==========================================================

def get_study_settings(doc_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns settings for study mode.
    If doc_id is provided, returns document-specific settings (initialized from global defaults if not yet created).
    If doc_id is None, returns global default settings.
    """
    config = config_store.load_config()
    global_settings = config.get("study_settings", {})
    
    para_prompts = global_settings.get("paragraph_quick_prompts") or global_settings.get("chat_quick_prompts") or DEFAULT_PARAGRAPH_QUICK_PROMPTS
    chap_prompts = global_settings.get("chapter_quick_prompts") or global_settings.get("chapter_chat_quick_prompts") or DEFAULT_CHAPTER_QUICK_PROMPTS

    defaults = {
        "translation_prompt_template": global_settings.get("translation_prompt_template", DEFAULT_TRANSLATION_PROMPT),
        "model_call_delay": float(global_settings.get("model_call_delay", 1.0)),
        "default_translation_provider": global_settings.get("default_translation_provider", global_settings.get("llm_source", "openai_compatible")),
        "default_translation_model": global_settings.get("default_translation_model", global_settings.get("text_model", "deepseek-chat")),
        "default_chat_provider": global_settings.get("default_chat_provider", global_settings.get("llm_source", "openai_compatible")),
        "default_chat_model": global_settings.get("default_chat_model", global_settings.get("text_model", "deepseek-chat")),
        "default_vlm_provider": global_settings.get("default_vlm_provider", "openai_compatible"),
        "default_vlm_model": global_settings.get("default_vlm_model", global_settings.get("vlm_model", "")),
        "translation_provider": "",
        "translation_model": "",
        "chat_provider": "",
        "chat_model": "",
        "vlm_provider": "",
        "vlm_model": "",
        "text_model": global_settings.get("text_model", ""),
        "vlm_model": global_settings.get("vlm_model", ""),
        "llm_source": global_settings.get("llm_source", "openai_compatible"),
        "openai_base_url": global_settings.get("openai_base_url", "https://api.deepseek.com/v1"),
        "openai_api_key": global_settings.get("openai_api_key", ""),
        "openai_model": global_settings.get("openai_model", "deepseek-chat"),
        "ollama_base_url": global_settings.get("ollama_base_url", "http://127.0.0.1:11434"),
        "ollama_model": global_settings.get("ollama_model", "qwen2.5:7b"),
        "lm_studio_base_url": global_settings.get("lm_studio_base_url", "http://127.0.0.1:1234/v1"),
        "lm_studio_model": global_settings.get("lm_studio_model", ""),
        "nvidia_base_url": global_settings.get("nvidia_base_url", "https://integrate.api.nvidia.com/v1"),
        "nvidia_api_key": global_settings.get("nvidia_api_key", ""),
        "nvidia_model": global_settings.get("nvidia_model", "meta/llama-3.3-70b-instruct"),
        "amd_base_url": global_settings.get("amd_base_url", "http://127.0.0.1:8000/v1"),
        "amd_api_key": global_settings.get("amd_api_key", ""),
        "amd_model": global_settings.get("amd_model", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"),
        "cf_account_id": global_settings.get("cf_account_id", ""),
        "cf_api_token": global_settings.get("cf_api_token", ""),
        "cf_model": global_settings.get("cf_model", "@cf/meta/llama-3.3-70b-instruct"),
        "chat_quick_prompts": para_prompts,
        "paragraph_quick_prompts": para_prompts,
        "chapter_quick_prompts": chap_prompts,
        "chapter_chat_quick_prompts": chap_prompts,
        "is_doc_level": False
    }

    # Overlay with saved providers config if available
    providers_cfg = config.get("providers", {})
    if "openai_compatible" in providers_cfg:
        defaults["openai_base_url"] = providers_cfg["openai_compatible"].get("base_url") or defaults["openai_base_url"]
        defaults["openai_api_key"] = providers_cfg["openai_compatible"].get("api_key") or defaults["openai_api_key"]
        defaults["openai_model"] = providers_cfg["openai_compatible"].get("model") or defaults["openai_model"]
    if "ollama" in providers_cfg:
        defaults["ollama_base_url"] = providers_cfg["ollama"].get("base_url") or defaults["ollama_base_url"]
        defaults["ollama_model"] = providers_cfg["ollama"].get("model") or defaults["ollama_model"]
    if "lm_studio" in providers_cfg:
        defaults["lm_studio_base_url"] = providers_cfg["lm_studio"].get("base_url") or defaults["lm_studio_base_url"]
        defaults["lm_studio_model"] = providers_cfg["lm_studio"].get("model") or defaults["lm_studio_model"]
    if "nvidia" in providers_cfg:
        defaults["nvidia_base_url"] = providers_cfg["nvidia"].get("base_url") or defaults["nvidia_base_url"]
        defaults["nvidia_api_key"] = providers_cfg["nvidia"].get("api_key") or defaults["nvidia_api_key"]
        defaults["nvidia_model"] = providers_cfg["nvidia"].get("model") or defaults["nvidia_model"]
    if "amd" in providers_cfg:
        defaults["amd_base_url"] = providers_cfg["amd"].get("base_url") or defaults["amd_base_url"]
        defaults["amd_api_key"] = providers_cfg["amd"].get("api_key") or defaults["amd_api_key"]
        defaults["amd_model"] = providers_cfg["amd"].get("model") or defaults["amd_model"]
    if "cloudflare" in providers_cfg:
        defaults["cf_account_id"] = providers_cfg["cloudflare"].get("account_id") or defaults["cf_account_id"]
        defaults["cf_api_token"] = providers_cfg["cloudflare"].get("api_token") or defaults["cf_api_token"]
        defaults["cf_model"] = providers_cfg["cloudflare"].get("model") or defaults["cf_model"]

    if not doc_id:
        return defaults

    doc_dir = get_doc_dir(doc_id)
    doc_settings_path = os.path.join(doc_dir, "settings.json")
    if os.path.exists(doc_settings_path):
        try:
            with open(doc_settings_path, "r", encoding="utf-8") as f:
                doc_settings = json.load(f)
                result = dict(defaults)
                result.update(doc_settings)
                doc_para = doc_settings.get("paragraph_quick_prompts") or doc_settings.get("chat_quick_prompts") or para_prompts
                doc_chap = doc_settings.get("chapter_quick_prompts") or doc_settings.get("chapter_chat_quick_prompts") or chap_prompts
                result["paragraph_quick_prompts"] = doc_para
                result["chat_quick_prompts"] = doc_para
                result["chapter_quick_prompts"] = doc_chap
                result["chapter_chat_quick_prompts"] = doc_chap
                # Ensure task models fallback to defaults if unset
                if not result.get("chat_provider"):
                    result["chat_provider"] = result.get("default_chat_provider", "openai_compatible")
                if not result.get("chat_model"):
                    result["chat_model"] = result.get("default_chat_model", "deepseek-chat")
                if not result.get("translation_provider"):
                    result["translation_provider"] = result.get("default_translation_provider", "openai_compatible")
                if not result.get("translation_model"):
                    result["translation_model"] = result.get("default_translation_model", "deepseek-chat")
                if not result.get("vlm_provider"):
                    result["vlm_provider"] = result.get("default_vlm_provider", "openai_compatible")
                if not result.get("vlm_model"):
                    result["vlm_model"] = result.get("default_vlm_model", "")
                result["is_doc_level"] = True
                result["doc_id"] = doc_id
                return result
        except Exception as e:
            logger.warning(f"Failed to read doc settings for {doc_id}: {e}")

    # Copy global defaults to doc settings file with explicit pre-populated task models
    doc_settings = dict(defaults)
    doc_settings["translation_provider"] = defaults.get("default_translation_provider", "openai_compatible")
    doc_settings["translation_model"] = defaults.get("default_translation_model", "deepseek-chat")
    doc_settings["chat_provider"] = defaults.get("default_chat_provider", "openai_compatible")
    doc_settings["chat_model"] = defaults.get("default_chat_model", "deepseek-chat")
    doc_settings["vlm_provider"] = defaults.get("default_vlm_provider", "openai_compatible")
    doc_settings["vlm_model"] = defaults.get("default_vlm_model", "")
    doc_settings["is_doc_level"] = True
    doc_settings["doc_id"] = doc_id
    try:
        with open(doc_settings_path, "w", encoding="utf-8") as f:
            json.dump(doc_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to create doc settings file for {doc_id}: {e}")

    return doc_settings

def save_study_settings(new_settings: Dict[str, Any], doc_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Saves study settings.
    If doc_id is provided, saves to doc_dir/settings.json.
    If doc_id is None, updates global study_settings.
    """
    norm_settings = dict(new_settings)
    if "paragraph_quick_prompts" in norm_settings:
        norm_settings["chat_quick_prompts"] = norm_settings["paragraph_quick_prompts"]
    elif "chat_quick_prompts" in norm_settings:
        norm_settings["paragraph_quick_prompts"] = norm_settings["chat_quick_prompts"]

    if "chapter_quick_prompts" in norm_settings:
        norm_settings["chapter_chat_quick_prompts"] = norm_settings["chapter_quick_prompts"]
    elif "chapter_chat_quick_prompts" in norm_settings:
        norm_settings["chapter_quick_prompts"] = norm_settings["chapter_chat_quick_prompts"]

    if doc_id:
        doc_dir = get_doc_dir(doc_id)
        doc_settings_path = os.path.join(doc_dir, "settings.json")
        current = get_study_settings(doc_id)
        current.update(norm_settings)
        current["is_doc_level"] = True
        current["doc_id"] = doc_id
        with open(doc_settings_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        return get_study_settings(doc_id)
    else:
        config = config_store.load_config()
        current = config.get("study_settings", {})
        current.update(norm_settings)
        config["study_settings"] = current
        config_store.save_config(config)
        return get_study_settings()

def reset_doc_settings(doc_id: str) -> Dict[str, Any]:
    """Resets document-level settings to inherit the current global defaults."""
    doc_dir = get_doc_dir(doc_id)
    doc_settings_path = os.path.join(doc_dir, "settings.json")
    if os.path.exists(doc_settings_path):
        try:
            os.remove(doc_settings_path)
        except Exception:
            pass
    return get_study_settings(doc_id)

def get_doc_dir(doc_id: str) -> str:
    path = os.path.join(BASE_DATA_DIR, doc_id)
    os.makedirs(os.path.join(path, "images"), exist_ok=True)
    os.makedirs(os.path.join(path, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(path, "chats"), exist_ok=True)
    return path

def save_doc_meta(doc_id: str, meta: Dict[str, Any]):
    doc_dir = get_doc_dir(doc_id)
    meta_path = os.path.join(doc_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def load_doc_meta(doc_id: str) -> Optional[Dict[str, Any]]:
    doc_dir = get_doc_dir(doc_id)
    meta_path = os.path.join(doc_dir, "meta.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)

def list_all_documents() -> List[Dict[str, Any]]:
    docs = []
    if not os.path.exists(BASE_DATA_DIR):
        return docs
    for entry in os.listdir(BASE_DATA_DIR):
        entry_dir = os.path.join(BASE_DATA_DIR, entry)
        if os.path.isdir(entry_dir):
            meta = load_doc_meta(entry)
            if meta:
                docs.append(meta)
    docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return docs

def delete_document(doc_id: str) -> bool:
    doc_dir = get_doc_dir(doc_id)
    if os.path.exists(doc_dir):
        import shutil
        shutil.rmtree(doc_dir, ignore_errors=True)
        return True
    return False

def delete_chapter(doc_id: str, chapter_id: str) -> Dict[str, Any]:
    """
    Deletes a specific chapter from a document.
    1. Removes all associated flashcards for this chapter.
    2. Deletes chapter JSON and Markdown files.
    3. Deletes associated chapter/paragraph chats.
    4. If no chapters remain in outline, completely deletes the document and all remaining cards.
    5. Otherwise, recalculates paragraph counts and updates document metadata.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")

    doc_dir = get_doc_dir(doc_id)
    chapters = meta.get("chapters", [])

    target_idx = -1
    for idx, ch in enumerate(chapters):
        if str(ch.get("chapter_id", "")).strip() == str(chapter_id).strip():
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Chapter {chapter_id} not found in document {doc_id}")

    deleted_ch_meta = chapters.pop(target_idx)

    # 1. Delete flashcards associated with this chapter
    deleted_cards_count = 0
    try:
        from study.flashcard_manager import delete_flashcards_by_chapter
        deleted_cards_count = delete_flashcards_by_chapter(doc_id, chapter_id)
    except Exception as e:
        logger.warning(f"Failed to delete flashcards for chapter {chapter_id}: {e}")

    # 2. Delete chapter json & md files
    for ext in (".json", ".md"):
        p = os.path.join(doc_dir, "chapters", f"{chapter_id}{ext}")
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception as e:
                logger.warning(f"Failed to delete chapter file {p}: {e}")

    # 3. Delete chapter chat files and paragraph chat files in chats/
    chats_dir = os.path.join(doc_dir, "chats")
    if os.path.exists(chats_dir):
        try:
            for fname in os.listdir(chats_dir):
                if fname.startswith(f"chapter_{chapter_id}.") or fname.startswith(f"para_{chapter_id}_"):
                    try:
                        os.remove(os.path.join(chats_dir, fname))
                    except Exception as e:
                        logger.warning(f"Failed to remove chat file {fname}: {e}")
        except Exception as e:
            logger.warning(f"Failed to scan chats dir: {e}")

    # 4. Check if all chapters have been deleted
    if len(chapters) == 0:
        # All chapters deleted: delete the document and all remaining files/flashcards
        delete_document(doc_id)
        return {
            "document_deleted": True,
            "doc_id": doc_id,
            "deleted_chapter_id": chapter_id,
            "deleted_cards_count": deleted_cards_count,
            "remaining_chapters": []
        }

    # 5. Recalculate remaining paragraphs and translated count
    total_paras = 0
    translated_paras = 0
    for ch in chapters:
        ch_p = os.path.join(doc_dir, "chapters", f"{ch['chapter_id']}.json")
        if os.path.exists(ch_p):
            try:
                with open(ch_p, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    paras = cdata.get("paragraphs", [])
                    total_paras += len(paras)
                    translated_paras += sum(1 for p in paras if p.get("status") == "completed")
            except Exception:
                total_paras += ch.get("paragraph_count", 0)
        else:
            total_paras += ch.get("paragraph_count", 0)

    meta["chapters"] = chapters
    meta["total_paragraphs"] = total_paras
    meta["translated_paragraphs"] = translated_paras
    save_doc_meta(doc_id, meta)

    return {
        "document_deleted": False,
        "doc_id": doc_id,
        "deleted_chapter_id": chapter_id,
        "deleted_cards_count": deleted_cards_count,
        "remaining_chapters": chapters,
        "total_paragraphs": total_paras,
        "translated_paragraphs": translated_paras
    }

def rename_chapter(doc_id: str, chapter_id: str, new_title: str) -> Dict[str, Any]:
    """
    Renames a specific chapter in document meta.json, chapter JSON, and chapter Markdown.
    """
    new_title = (new_title or "").strip()
    if not new_title:
        raise ValueError("章节标题不能为空")

    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")

    chapters = meta.get("chapters", [])
    target_idx = -1
    for idx, ch in enumerate(chapters):
        if str(ch.get("chapter_id", "")).strip() == str(chapter_id).strip():
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Chapter {chapter_id} not found in document {doc_id}")

    chapters[target_idx]["title"] = new_title
    meta["chapters"] = chapters
    save_doc_meta(doc_id, meta)

    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if os.path.exists(ch_json_path):
        with open(ch_json_path, "r", encoding="utf-8") as f:
            ch_data = json.load(f)
        ch_data["title"] = new_title
        write_chapter_files(doc_id, ch_data, meta.get("language", "en"))

    return {
        "doc_id": doc_id,
        "chapter_id": chapter_id,
        "title": new_title,
        "remaining_chapters": chapters
    }

def update_flashcards_chapter_for_paragraphs(doc_id: str, paragraph_ids: set, new_chapter_id: str):
    """
    Updates the chapter_id reference on any flashcard attached to the specified paragraph IDs.
    """
    if not paragraph_ids:
        return
    try:
        from study.flashcard_manager import load_doc_flashcards, save_doc_flashcards
        fc_data = load_doc_flashcards(doc_id)
        cards = fc_data.get("cards", [])
        changed = False
        for card in cards:
            if card.get("paragraph_id") in paragraph_ids:
                card["chapter_id"] = new_chapter_id
                changed = True
        if changed:
            save_doc_flashcards(doc_id, fc_data)
    except Exception as e:
        logger.warning(f"Failed to update flashcard chapter references: {e}")

def _recalc_and_save_doc_meta(doc_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    doc_dir = get_doc_dir(doc_id)
    chapters = meta.get("chapters", [])
    total_paras = 0
    translated_paras = 0
    for ch in chapters:
        ch_p = os.path.join(doc_dir, "chapters", f"{ch['chapter_id']}.json")
        if os.path.exists(ch_p):
            try:
                with open(ch_p, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    paras = cdata.get("paragraphs", [])
                    ch["paragraph_count"] = len(paras)
                    ch["translated_count"] = sum(1 for p in paras if p.get("status") == "completed")
                    total_paras += len(paras)
                    translated_paras += ch["translated_count"]
            except Exception:
                total_paras += ch.get("paragraph_count", 0)
        else:
            total_paras += ch.get("paragraph_count", 0)
    meta["chapters"] = chapters
    meta["total_paragraphs"] = total_paras
    meta["translated_paragraphs"] = translated_paras
    save_doc_meta(doc_id, meta)
    return meta

def shift_chapter_paragraphs(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    direction: str = "prev"
) -> Dict[str, Any]:
    """
    Shifts a slice of paragraphs from chapter_id into the adjacent chapter:
    - 'prev': paragraphs from index 0 up to paragraph_id (inclusive) are moved to the END of the previous chapter.
    - 'next': paragraphs from paragraph_id to the end (inclusive) are moved to the BEGINNING of the next chapter.
    If all paragraphs in chapter_id are moved away, chapter_id is automatically deleted.
    """
    if direction not in ("prev", "next"):
        raise ValueError(f"Invalid direction: {direction}. Must be 'prev' or 'next'")

    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")

    chapters = meta.get("chapters", [])
    target_idx = -1
    for idx, ch in enumerate(chapters):
        if str(ch.get("chapter_id", "")).strip() == str(chapter_id).strip():
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Chapter {chapter_id} not found in document {doc_id}")

    if direction == "prev":
        if target_idx == 0:
            raise ValueError("当前章节已是第一章，无法向上合并")
        dest_idx = target_idx - 1
    else:
        if target_idx >= len(chapters) - 1:
            raise ValueError("当前章节已是最后一章，无法向下合并")
        dest_idx = target_idx + 1

    dest_chapter_id = chapters[dest_idx]["chapter_id"]
    doc_dir = get_doc_dir(doc_id)

    src_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    dest_json_path = os.path.join(doc_dir, "chapters", f"{dest_chapter_id}.json")

    if not os.path.exists(src_json_path) or not os.path.exists(dest_json_path):
        raise ValueError("Source or destination chapter file not found")

    with open(src_json_path, "r", encoding="utf-8") as f:
        src_ch = json.load(f)
    with open(dest_json_path, "r", encoding="utf-8") as f:
        dest_ch = json.load(f)

    src_paras = src_ch.get("paragraphs", [])
    dest_paras = dest_ch.get("paragraphs", [])

    p_idx = -1
    for idx, p in enumerate(src_paras):
        if str(p.get("id")) == str(paragraph_id):
            p_idx = idx
            break

    if p_idx == -1:
        raise ValueError(f"Paragraph {paragraph_id} not found in chapter {chapter_id}")

    if direction == "prev":
        moved_paras = src_paras[:p_idx + 1]
        remaining_paras = src_paras[p_idx + 1:]
        # Update chapter_id in moved paragraphs and append to dest
        for p in moved_paras:
            p["chapter_id"] = dest_chapter_id
        dest_paras = dest_paras + moved_paras
    else:
        moved_paras = src_paras[p_idx:]
        remaining_paras = src_paras[:p_idx]
        # Update chapter_id in moved paragraphs and prepend to dest
        for p in moved_paras:
            p["chapter_id"] = dest_chapter_id
        dest_paras = moved_paras + dest_paras

    dest_ch["paragraphs"] = dest_paras
    lang = meta.get("language", "en")
    write_chapter_files(doc_id, dest_ch, lang)

    # Update flashcards references for moved paragraphs
    moved_para_ids = {p.get("id") for p in moved_paras if p.get("id")}
    update_flashcards_chapter_for_paragraphs(doc_id, moved_para_ids, dest_chapter_id)

    source_deleted = False
    if len(remaining_paras) == 0:
        # All paragraphs moved out, delete empty source chapter
        source_deleted = True
        for ext in (".json", ".md"):
            fp = os.path.join(doc_dir, "chapters", f"{chapter_id}{ext}")
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception as e:
                    logger.warning(f"Failed to remove {fp}: {e}")
        # Remove from chapters list
        chapters.pop(target_idx)
    else:
        src_ch["paragraphs"] = remaining_paras
        write_chapter_files(doc_id, src_ch, lang)

    meta["chapters"] = chapters
    meta = _recalc_and_save_doc_meta(doc_id, meta)

    return {
        "success": True,
        "doc_id": doc_id,
        "direction": direction,
        "source_chapter_id": chapter_id,
        "target_chapter_id": dest_chapter_id,
        "source_deleted": source_deleted,
        "moved_count": len(moved_paras),
        "remaining_chapters": meta.get("chapters", []),
        "total_paragraphs": meta.get("total_paragraphs", 0),
        "translated_paragraphs": meta.get("translated_paragraphs", 0)
    }

def split_chapter_from_paragraph(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    new_title: str
) -> Dict[str, Any]:
    """
    Splits chapter_id at paragraph_id into two chapters:
    - chapter_id retains paragraphs strictly before paragraph_id.
    - A new chapter is created containing paragraphs from paragraph_id to the end, titled new_title.
    """
    new_title = (new_title or "").strip()
    if not new_title:
        new_title = "新章节"

    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")

    chapters = meta.get("chapters", [])
    target_idx = -1
    for idx, ch in enumerate(chapters):
        if str(ch.get("chapter_id", "")).strip() == str(chapter_id).strip():
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Chapter {chapter_id} not found in document {doc_id}")

    doc_dir = get_doc_dir(doc_id)
    src_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(src_json_path):
        raise ValueError(f"Chapter {chapter_id} file not found")

    with open(src_json_path, "r", encoding="utf-8") as f:
        src_ch = json.load(f)

    src_paras = src_ch.get("paragraphs", [])
    p_idx = -1
    for idx, p in enumerate(src_paras):
        if str(p.get("id")) == str(paragraph_id):
            p_idx = idx
            break

    if p_idx == -1:
        raise ValueError(f"Paragraph {paragraph_id} not found in chapter {chapter_id}")

    if p_idx == 0:
        raise ValueError("无法在章节第一段执行拆分（原章节将变为空章节），如需重命名请在目录中操作")

    retained_paras = src_paras[:p_idx]
    new_paras = src_paras[p_idx:]

    import uuid
    new_chapter_id = f"ch_{uuid.uuid4().hex[:8]}"

    # Update chapter_id in newly split paragraphs
    for p in new_paras:
        p["chapter_id"] = new_chapter_id

    lang = meta.get("language", "en")

    # Save new chapter
    new_ch = {
        "chapter_id": new_chapter_id,
        "title": new_title,
        "paragraphs": new_paras,
        "notes": []
    }
    write_chapter_files(doc_id, new_ch, lang)

    # Update source chapter
    src_ch["paragraphs"] = retained_paras
    write_chapter_files(doc_id, src_ch, lang)

    # Update flashcard references
    moved_para_ids = {p.get("id") for p in new_paras if p.get("id")}
    update_flashcards_chapter_for_paragraphs(doc_id, moved_para_ids, new_chapter_id)

    # Insert into meta.json outline right after source chapter
    new_ch_meta = {
        "chapter_id": new_chapter_id,
        "title": new_title,
        "paragraph_count": len(new_paras),
        "translated_count": sum(1 for p in new_paras if p.get("status") == "completed")
    }
    chapters.insert(target_idx + 1, new_ch_meta)

    meta["chapters"] = chapters
    meta = _recalc_and_save_doc_meta(doc_id, meta)

    return {
        "success": True,
        "doc_id": doc_id,
        "source_chapter_id": chapter_id,
        "new_chapter_id": new_chapter_id,
        "new_title": new_title,
        "split_count": len(new_paras),
        "remaining_chapters": meta.get("chapters", []),
        "total_paragraphs": meta.get("total_paragraphs", 0),
        "translated_paragraphs": meta.get("translated_paragraphs", 0)
    }

def write_chapter_files(doc_id: str, chapter: Dict[str, Any], language: str = "en"):
    doc_dir = get_doc_dir(doc_id)
    ch_id = chapter["chapter_id"]
    json_path = os.path.join(doc_dir, "chapters", f"{ch_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chapter, f, ensure_ascii=False, indent=2)
    md_path = os.path.join(doc_dir, "chapters", f"{ch_id}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_chapter_markdown(chapter, language))

def get_image_base64_data_uri(doc_id: str, img_ref: str) -> Optional[str]:
    """
    Resolves an image reference (filename, relative path, or /api/study/documents/{doc_id}/images/{img_name})
    to a Base64 Data URI from doc_dir/images/.
    """
    if not img_ref:
        return None
    img_name = os.path.basename(img_ref.strip())
    doc_dir = get_doc_dir(doc_id)
    img_path = os.path.join(doc_dir, "images", img_name)
    if not os.path.isfile(img_path):
        return None

    ext = os.path.splitext(img_name)[1].lower()
    mime = "image/png"
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    elif ext == ".svg":
        mime = "image/svg+xml"
    elif ext == ".gif":
        mime = "image/gif"

    try:
        with open(img_path, "rb") as f:
            data = f.read()
        b64_str = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64_str}"
    except Exception as e:
        logger.warning(f"Failed to encode image {img_path} to base64: {e}")
        return None

def transform_markdown_images(doc_id: str, md_content: str, mode: str = "base64") -> str:
    """
    Transforms image markdown links in `md_content`.
    mode='base64': converts matching image links to data:image/...;base64,...
    mode='relative': converts matching image links to images/{filename}
    """
    doc_dir = get_doc_dir(doc_id)
    pattern = re.compile(rf'!\[(.*?)\]\((?:/api/study/documents/{re.escape(doc_id)}/images/|images/)?([^)]+)\)')

    def _replace(match):
        alt = match.group(1)
        raw_target = match.group(2).strip()
        if raw_target.startswith("data:") or raw_target.startswith("http://") or raw_target.startswith("https://"):
            return match.group(0)

        img_name = os.path.basename(raw_target)
        img_path = os.path.join(doc_dir, "images", img_name)
        if not os.path.isfile(img_path):
            return match.group(0)

        if mode == "base64":
            data_uri = get_image_base64_data_uri(doc_id, img_name)
            if data_uri:
                return f"![{alt}]({data_uri})"
        elif mode == "relative":
            return f"![{alt}](images/{img_name})"
        return match.group(0)

    return pattern.sub(_replace, md_content)

def assemble_full_document_markdown(doc_id: str, image_mode: str = "base64") -> str:
    """
    Assembles and returns full document Markdown text.
    image_mode:
      - 'base64': embedded data URIs (self-contained single .md file)
      - 'relative': relative 'images/{filename}' links (for zip archive)
      - 'raw': unchanged original internal API paths
    Also saves raw bilingual markdown to full_bilingual.md.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        return ""
    doc_dir = get_doc_dir(doc_id)
    full_md_lines = [f"# {meta.get('filename', 'Document')}\n\n"]
    for ch_info in meta.get("chapters", []):
        rel_file = ch_info.get("file")
        if not rel_file:
            ch_id = ch_info.get("chapter_id")
            if ch_id:
                rel_file = f"chapters/{ch_id}.md"
        if not rel_file:
            continue
        ch_md_path = os.path.join(doc_dir, rel_file)
        if os.path.isfile(ch_md_path):
            with open(ch_md_path, "r", encoding="utf-8") as f:
                full_md_lines.append(f.read())
            full_md_lines.append("\n\n---\n\n")
    raw_content = "".join(full_md_lines)
    with open(os.path.join(doc_dir, "full_bilingual.md"), "w", encoding="utf-8") as f:
        f.write(raw_content)

    if image_mode in ("base64", "relative"):
        return transform_markdown_images(doc_id, raw_content, mode=image_mode)
    return raw_content

def assemble_full_document_zip(doc_id: str) -> bytes:
    """
    Assembles a complete standalone zip archive containing:
    1. {safe_title}.md using relative 'images/{filename}' links
    2. 'images/' directory containing all image assets from doc_dir/images
    """
    import zipfile
    import io

    meta = load_doc_meta(doc_id) or {}
    doc_title = meta.get("filename", "Document")
    base_name = os.path.splitext(doc_title)[0]
    safe_name = "".join([c for c in base_name if c.isalnum() or c in " ._-\u4e00-\u9fa5"]).strip() or "document"

    doc_dir = get_doc_dir(doc_id)
    images_dir = os.path.join(doc_dir, "images")

    # Generate markdown with relative images/ paths
    md_content = assemble_full_document_markdown(doc_id, image_mode="relative")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add markdown document
        zf.writestr(f"{safe_name}.md", md_content.encode("utf-8"))

        # Add all images in doc_dir/images
        if os.path.isdir(images_dir):
            for img_file in sorted(os.listdir(images_dir)):
                full_img_path = os.path.join(images_dir, img_file)
                if os.path.isfile(full_img_path) and not img_file.startswith("."):
                    zf.write(full_img_path, arcname=f"images/{img_file}")

    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def _format_html_text(text: str, doc_id: Optional[str] = None) -> str:
    import html
    if not text:
        return ""
    escaped = html.escape(text)
    # Simple inline bold, italic, code formatting
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'\*(.*?)\*', r'<em>\1</em>', escaped)
    escaped = re.sub(r'`(.*?)`', r'<code>\1</code>', escaped)

    # Check for inline markdown images !\[(.*?)\]\((.*?)\)
    if doc_id and "![" in escaped:
        def img_repl(m):
            alt = m.group(1)
            raw_url = m.group(2).strip()
            b64_uri = get_image_base64_data_uri(doc_id, raw_url)
            src = b64_uri or raw_url
            return f'<span class="inline-img-box"><img src="{src}" alt="{alt}" class="content-img" loading="lazy" /></span>'
        escaped = re.sub(r'!\[(.*?)\]\((.*?)\)', img_repl, escaped)

    return escaped.replace("\n", "<br>")

def assemble_full_document_html(
    doc_id: str,
    flashcards_link: Optional[str] = "flashcards.html",
    portal_link: Optional[str] = None
) -> str:
    """
    Generates a standalone, production-ready HTML bilingual eBook for local viewing or
    static deployment (Nginx / Cloudflare Pages).
    Includes:
      - 4 Curated Themes (Dark, White, Sepia, Forest)
      - Font size stepping adjuster (A- / A+)
      - Reading width adjuster (Compact, Standard, Wide, Full)
      - Floating Quick Scroll Navigator with real-time percentage progress
      - Inlined marked.js for authentic Markdown tables and rich text rendering
      - LocalStorage persistence for user reading preferences
      - Embedded Base64 figures & print-ready CSS
    """
    import html
    meta = load_doc_meta(doc_id)
    if not meta:
        return ""
    doc_dir = get_doc_dir(doc_id)
    doc_title = meta.get("filename", "Document")
    total_paras = meta.get("total_paragraphs", 0)
    trans_paras = meta.get("translated_paragraphs", 0)
    created_at = meta.get("created_at", time.strftime("%Y-%m-%d"))

    # Table of Contents HTML
    toc_items = []
    chapters_html = []

    for ch_idx, ch_info in enumerate(meta.get("chapters", []), 1):
        ch_id = ch_info.get("chapter_id", "")
        ch_json_path = os.path.join(doc_dir, "chapters", f"{ch_id}.json")
        if not os.path.exists(ch_json_path):
            continue
        with open(ch_json_path, "r", encoding="utf-8") as f:
            ch_data = json.load(f)

        ch_title = ch_data.get("title", f"第 {ch_idx} 章")
        toc_items.append(f'<li><a href="#ch_{ch_id}"><span class="toc-num">{ch_idx}.</span> {_format_html_text(ch_title)}</a></li>')

        # Chapter Content Blocks
        ch_blocks = []
        ch_blocks.append(f'<section class="chapter-section" id="ch_{ch_id}">')
        ch_blocks.append(f'<h2 class="chapter-title"><span class="ch-badge">CHAPTER {ch_idx}</span> {_format_html_text(ch_title)}</h2>')

        # 1. Chapter Header Notes
        header_notes = ch_data.get("header_notes", [])
        if header_notes:
            ch_blocks.append('<div class="notes-container header-notes-box">')
            ch_blocks.append('<div class="notes-box-header">📌 【本章总览与研学总结】</div>')
            for hn in header_notes:
                c = hn.get("content", "").strip()
                if c:
                    esc_raw = html.escape(c, quote=True)
                    ch_blocks.append(f'<div class="note-entry"><div class="note-body md-render" data-raw="{esc_raw}">{_format_html_text(c, doc_id)}</div><div class="note-time">{hn.get("created_at", "")}</div></div>')
            ch_blocks.append('</div>')

        # 2. Paragraphs
        for p in ch_data.get("paragraphs", []):
            p_type = p.get("type", "text")
            p_eng = p.get("english", "").strip()
            p_cn = p.get("chinese", "").strip()
            p_notes = p.get("notes", [])

            if p_type == "image":
                img_url = p.get("image_url", "")
                caption = ""
                if not img_url and p_eng:
                    m = re.search(r'!\[(.*?)\]\((.*?)\)', p_eng)
                    if m:
                        caption = m.group(1).strip()
                        img_url = m.group(2).strip()
                elif p_eng and not p_eng.startswith("!["):
                    caption = p_eng

                b64_uri = get_image_base64_data_uri(doc_id, img_url) if img_url else None
                src_attr = b64_uri if b64_uri else img_url
                caption_html = f'<div class="img-caption">{_format_html_text(caption, doc_id)}</div>' if caption else ''
                if src_attr:
                    ch_blocks.append(f'<div class="content-block image-block"><img src="{src_attr}" alt="{html.escape(caption)}" class="content-img" loading="lazy" />{caption_html}</div>')
                elif caption_html:
                    ch_blocks.append(f'<div class="content-block image-block">{caption_html}</div>')
                continue

            ch_blocks.append('<div class="bilingual-para-block">')
            if p_type == "scanned_page" and p.get("image_url"):
                b64_scanned = get_image_base64_data_uri(doc_id, p["image_url"]) or p["image_url"]
                ch_blocks.append(f'<div class="scanned-page-img"><img src="{b64_scanned}" alt="Page {p.get("page", 1)}" class="content-img" loading="lazy"></div>')

            if p_eng:
                esc_eng = html.escape(p_eng, quote=True)
                ch_blocks.append(f'<div class="para-source md-render" data-raw="{esc_eng}">{_format_html_text(p_eng, doc_id)}</div>')
            if p_cn:
                esc_cn = html.escape(p_cn, quote=True)
                ch_blocks.append(f'<blockquote class="para-translation md-render" data-raw="{esc_cn}">{_format_html_text(p_cn, doc_id)}</blockquote>')

            # Paragraph Notes
            if p_notes:
                ch_blocks.append('<div class="para-notes-list">')
                for nt in p_notes:
                    c = nt.get("content", "").strip()
                    if c:
                        esc_note = html.escape(c, quote=True)
                        ch_blocks.append(f'<div class="para-note-item"><span class="para-note-tag">💡 注解</span><span class="para-note-text md-render" data-raw="{esc_note}">{_format_html_text(c, doc_id)}</span><span class="para-note-date">{nt.get("created_at", "")}</span></div>')
                ch_blocks.append('</div>')

            ch_blocks.append('</div>')

        # 3. Chapter Footer Notes
        footer_notes = ch_data.get("footer_notes", [])
        if footer_notes:
            ch_blocks.append('<div class="notes-container footer-notes-box">')
            ch_blocks.append('<div class="notes-box-header">🎯 【本章回顾与核心考点】</div>')
            for fn in footer_notes:
                c = fn.get("content", "").strip()
                if c:
                    esc_fn = html.escape(c, quote=True)
                    ch_blocks.append(f'<div class="note-entry"><div class="note-body md-render" data-raw="{esc_fn}">{_format_html_text(c, doc_id)}</div><div class="note-time">{fn.get("created_at", "")}</div></div>')
            ch_blocks.append('</div>')

        ch_blocks.append('</section>')
        chapters_html.append("\n".join(ch_blocks))

    toc_html = f'<ul class="toc-list">{"".join(toc_items)}</ul>'
    body_content = "\n\n".join(chapters_html)

    # Read marked.min.js to embed
    marked_js = ""
    marked_path = os.path.join(os.getcwd(), "static", "js", "marked.min.js")
    if os.path.exists(marked_path):
        try:
            with open(marked_path, "r", encoding="utf-8") as mf:
                marked_js = mf.read()
        except Exception as me:
            logger.error(f"Failed to read marked.min.js for HTML export: {me}")

    portal_nav_html = ""
    if portal_link:
        portal_nav_html = f'<a href="{portal_link}" class="topbar-nav-link" id="link-portal" title="返回个人研习大厅">🏠 研习大厅</a>'

    flashcards_nav_html = ""
    if flashcards_link:
        flashcards_nav_html = f'<a href="{flashcards_link}" class="topbar-nav-link" id="link-flashcards" title="查看本材料配套考点闪卡">🗂️ 考点闪卡</a>'

    # Generate document-specific SEO & GEO metadata
    raw_text_pieces = []
    ch_keywords = []
    for ch_info in meta.get("chapters", []):
        t = ch_info.get("title", "")
        if t and t not in ch_keywords and len(t) <= 12:
            ch_keywords.append(t)
        ch_id = ch_info.get("chapter_id", "")
        ch_json_path = os.path.join(doc_dir, "chapters", f"{ch_id}.json")
        if os.path.exists(ch_json_path) and len(raw_text_pieces) < 3:
            try:
                with open(ch_json_path, "r", encoding="utf-8") as f:
                    ch_d = json.load(f)
                for p in ch_d.get("paragraphs", []):
                    txt = (p.get("chinese") or p.get("english") or "").strip()
                    if txt and not txt.startswith("!["):
                        clean_txt = re.sub(r'[*_`#\[\]]', '', txt)
                        clean_txt = re.sub(r'\s+', ' ', clean_txt).strip()
                        if len(clean_txt) > 20:
                            raw_text_pieces.append(clean_txt)
                            if len(raw_text_pieces) >= 3:
                                break
            except Exception:
                pass

    if raw_text_pieces:
        seo_description = " ".join(raw_text_pieces)[:150].strip() + "..."
    else:
        seo_description = f"《{doc_title}》双语研学文献材料。共包含 {total_paras} 个研学段落，已对齐完成 {trans_paras} 个段落，支持中英对照与句级研学。"

    seo_description_esc = html.escape(seo_description, quote=True)
    keywords_list = ["Omnididact", "双语研学", "自学系统", "深度阅读", "考点闪卡"]
    if meta.get("file_type"):
        keywords_list.append(meta.get("file_type").upper())
    keywords_list.extend(ch_keywords[:5])
    seo_keywords_esc = html.escape(",".join(keywords_list), quote=True)
    doc_title_esc = html.escape(doc_title, quote=True)
    json_ld_doc_title = json.dumps(doc_title, ensure_ascii=False)
    json_ld_doc_desc = json.dumps(seo_description, ensure_ascii=False)
    json_ld_created_at = json.dumps(str(created_at), ensure_ascii=False)

    html_document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_format_html_text(doc_title)} - 双语研学文献</title>
    <meta name="description" content="{seo_description_esc}">
    <meta name="keywords" content="{seo_keywords_esc}">
    <meta name="author" content="Omnididact (https://github.com/coodajingang/Ominididact)">
    <meta name="generator" content="Omnididact (https://github.com/coodajingang/Ominididact)">

    <!-- Open Graph / GEO Metadata -->
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="Omnididact">
    <meta property="og:title" content="{doc_title_esc} - 双语研学文献">
    <meta property="og:description" content="{seo_description_esc}">
    <meta property="article:published_time" content="{created_at}">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{doc_title_esc} - 双语研学文献">
    <meta name="twitter:description" content="{seo_description_esc}">

    <!-- Schema.org JSON-LD for Search Engines & Generative AI (GEO) -->
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "LearningResource",
      "name": {json_ld_doc_title},
      "description": {json_ld_doc_desc},
      "learningResourceType": "Bilingual Study Material",
      "inLanguage": ["zh-CN", "en"],
      "dateCreated": {json_ld_created_at},
      "publisher": {{
        "@type": "Organization",
        "name": "Omnididact",
        "url": "https://github.com/coodajingang/Ominididact"
      }}
    }}
    </script>
    <style>
        :root {{
            --container-max-width: 1100px;
            --content-font-size: 16px;
        }}

        body[data-theme="dark"], :root {{
            --bg: #0a0e17;
            --card-bg: rgba(30, 41, 59, 0.55);
            --topbar-bg: rgba(15, 23, 42, 0.88);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #818cf8;
            --primary-bg: rgba(99, 102, 241, 0.2);
            --quote-bg: rgba(99, 102, 241, 0.1);
            --quote-border: #818cf8;
            --note-bg: rgba(99, 102, 241, 0.08);
            --note-border: rgba(99, 102, 241, 0.3);
            --header-note-bg: rgba(99, 102, 241, 0.14);
            --header-note-border: #818cf8;
            --footer-note-bg: rgba(16, 185, 129, 0.14);
            --footer-note-border: #10b981;
            --border: rgba(255, 255, 255, 0.1);
            --table-header-bg: rgba(99, 102, 241, 0.2);
            --table-stripe-bg: rgba(255, 255, 255, 0.02);
            --btn-bg: rgba(255, 255, 255, 0.08);
            --btn-border: rgba(255, 255, 255, 0.15);
            --shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }}

        body[data-theme="white"] {{
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --topbar-bg: rgba(255, 255, 255, 0.94);
            --text-main: #0f172a;
            --text-muted: #64748b;
            --primary: #4f46e5;
            --primary-bg: #e0e7ff;
            --quote-bg: #eef2ff;
            --quote-border: #4f46e5;
            --note-bg: #f0f4ff;
            --note-border: #c7d2fe;
            --header-note-bg: #eef2ff;
            --header-note-border: #4f46e5;
            --footer-note-bg: #f0fdf4;
            --footer-note-border: #10b981;
            --border: #e2e8f0;
            --table-header-bg: #eef2ff;
            --table-stripe-bg: #f8fafc;
            --btn-bg: #f1f5f9;
            --btn-border: #cbd5e1;
            --shadow: 0 4px 18px rgba(0, 0, 0, 0.06);
        }}

        body[data-theme="sepia"] {{
            --bg: #f5eedc;
            --card-bg: #faf4e6;
            --topbar-bg: rgba(245, 238, 220, 0.95);
            --text-main: #292524;
            --text-muted: #78716c;
            --primary: #b45309;
            --primary-bg: #fde68a;
            --quote-bg: #f0e6ce;
            --quote-border: #b45309;
            --note-bg: #f5ebd3;
            --note-border: #d7c29e;
            --header-note-bg: #f5ebd3;
            --header-note-border: #b45309;
            --footer-note-bg: #eef3e2;
            --footer-note-border: #4d7c0f;
            --border: #e7dbc5;
            --table-header-bg: #eddcc2;
            --table-stripe-bg: #f3e9d8;
            --btn-bg: #f0e6ce;
            --btn-border: #d7c29e;
            --shadow: 0 4px 18px rgba(90, 60, 20, 0.08);
        }}

        body[data-theme="forest"] {{
            --bg: #091712;
            --card-bg: rgba(18, 38, 32, 0.75);
            --topbar-bg: rgba(9, 23, 18, 0.92);
            --text-main: #ecfdf5;
            --text-muted: #6ee7b7;
            --primary: #10b981;
            --primary-bg: rgba(16, 185, 129, 0.2);
            --quote-bg: rgba(16, 185, 129, 0.12);
            --quote-border: #10b981;
            --note-bg: rgba(16, 185, 129, 0.08);
            --note-border: rgba(16, 185, 129, 0.3);
            --header-note-bg: rgba(16, 185, 129, 0.15);
            --header-note-border: #10b981;
            --footer-note-bg: rgba(5, 150, 105, 0.15);
            --footer-note-border: #34d399;
            --border: rgba(16, 185, 129, 0.2);
            --table-header-bg: rgba(16, 185, 129, 0.2);
            --table-stripe-bg: rgba(255, 255, 255, 0.02);
            --btn-bg: rgba(16, 185, 129, 0.12);
            --btn-border: rgba(16, 185, 129, 0.25);
            --shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.75;
            padding: 0 0 100px;
            font-size: var(--content-font-size);
            transition: background 0.2s, color 0.2s;
        }}

        /* Sticky Top Toolbar */
        .reader-topbar {{
            position: sticky;
            top: 0;
            z-index: 1000;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 24px;
            background: var(--topbar-bg);
            border-bottom: 1px solid var(--border);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
            flex-wrap: wrap;
            gap: 12px;
        }}
        .topbar-left {{
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 220px;
        }}
        .topbar-title {{
            font-size: 15px;
            font-weight: 700;
            color: var(--text-main);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 360px;
        }}
        .topbar-right {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .control-group {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: var(--text-muted);
        }}
        .ctrl-btn {{
            background: var(--btn-bg);
            border: 1px solid var(--btn-border);
            color: var(--text-main);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .ctrl-btn:hover {{
            border-color: var(--primary);
            color: var(--primary);
        }}
        .reader-select {{
            background: var(--btn-bg);
            border: 1px solid var(--btn-border);
            color: var(--text-main);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12.5px;
            cursor: pointer;
            outline: none;
        }}
        .topbar-nav-link {{
            background: var(--primary-bg);
            color: var(--primary);
            border: 1px solid var(--primary);
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12.5px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        .topbar-nav-link:hover {{
            opacity: 0.85;
            transform: translateY(-1px);
        }}
        .size-indicator {{
            font-size: 12px;
            font-weight: 600;
            min-width: 34px;
            text-align: center;
        }}

        /* Content Container */
        .container {{
            max-width: var(--container-max-width);
            margin: 0 auto;
            padding: 24px 20px;
            transition: max-width 0.25s ease;
        }}
        .doc-header {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px 36px;
            margin-bottom: 32px;
            box-shadow: var(--shadow);
        }}
        .doc-title {{
            font-size: 26px;
            font-weight: 800;
            margin-bottom: 12px;
            color: var(--text-main);
            letter-spacing: -0.5px;
        }}
        .doc-meta-row {{
            display: flex;
            gap: 16px;
            font-size: 13px;
            color: var(--text-muted);
            flex-wrap: wrap;
            align-items: center;
        }}
        .doc-badge {{
            background: var(--primary-bg);
            color: var(--primary);
            padding: 3px 10px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
        }}
        .toc-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px 30px;
            margin-bottom: 36px;
            box-shadow: var(--shadow);
        }}
        .toc-title {{
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .toc-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .toc-list a {{
            color: var(--primary);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            transition: color 0.15s;
            display: inline-flex;
            gap: 6px;
        }}
        .toc-list a:hover {{
            text-decoration: underline;
        }}
        .toc-num {{
            font-weight: 700;
            opacity: 0.85;
        }}

        /* Chapter Section */
        .chapter-section {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px 36px;
            margin-bottom: 36px;
            box-shadow: var(--shadow);
        }}
        .chapter-title {{
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 2px solid var(--border);
            padding-bottom: 14px;
        }}
        .ch-badge {{
            background: var(--primary);
            color: #fff;
            font-size: 11px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 5px;
            letter-spacing: 0.5px;
        }}

        /* Notes Box */
        .notes-container {{
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 24px;
        }}
        .header-notes-box {{
            background: var(--header-note-bg);
            border-left: 4px solid var(--header-note-border);
        }}
        .footer-notes-box {{
            background: var(--footer-note-bg);
            border-left: 4px solid var(--footer-note-border);
            margin-top: 28px;
        }}
        .notes-box-header {{
            font-weight: 700;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .note-entry {{
            margin-bottom: 10px;
            font-size: 13.5px;
            line-height: 1.65;
        }}
        .note-entry:last-child {{
            margin-bottom: 0;
        }}
        .note-time {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        /* Paragraphs */
        .bilingual-para-block {{
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }}
        .bilingual-para-block:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        .para-source {{
            font-size: 1em;
            color: var(--text-main);
            margin-bottom: 10px;
            word-break: break-word;
        }}
        .para-translation {{
            background: var(--quote-bg);
            border-left: 3.5px solid var(--quote-border);
            padding: 10px 14px;
            border-radius: 0 8px 8px 0;
            font-size: 0.95em;
            color: var(--text-main);
            margin-bottom: 10px;
        }}
        .para-notes-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-top: 10px;
        }}
        .para-note-item {{
            background: var(--note-bg);
            border: 1px solid var(--note-border);
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12.5px;
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .para-note-tag {{
            font-weight: 700;
            color: #d97706;
        }}
        .para-note-date {{
            margin-left: auto;
            font-size: 11px;
            color: var(--text-muted);
        }}

        /* Images & Figures */
        .scanned-page-img img {{
            max-width: 100%;
            border-radius: 8px;
            border: 1px solid var(--border);
            margin-bottom: 12px;
        }}
        .image-block {{
            text-align: center;
            margin: 20px 0;
            padding: 14px;
            background: rgba(0, 0, 0, 0.02);
            border-radius: 12px;
            border: 1px dashed var(--border);
        }}
        .content-img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
            display: inline-block;
        }}
        .img-caption {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 10px;
            font-weight: 500;
        }}
        .inline-img-box {{
            display: block;
            text-align: center;
            margin: 12px 0;
        }}

        /* Table Styles */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 14px 0;
            font-size: 0.9em;
            background: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border);
        }}
        th, td {{
            padding: 9px 12px;
            border: 1px solid var(--border);
            text-align: left;
            line-height: 1.5;
        }}
        th {{
            background: var(--table-header-bg);
            color: var(--text-main);
            font-weight: 700;
        }}
        tr:nth-child(even) {{
            background: var(--table-stripe-bg);
        }}

        code {{
            background: rgba(125, 125, 125, 0.15);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 85%;
        }}

        /* Quick Scroll Float Bar */
        .quick-scroll-navigator {{
            position: fixed;
            bottom: 28px;
            right: 28px;
            z-index: 999;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            background: var(--topbar-bg);
            border: 1px solid var(--border);
            border-radius: 30px;
            padding: 8px 6px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(12px);
            opacity: 0.18;
            transition: opacity 0.25s ease, transform 0.2s ease;
        }}
        .quick-scroll-navigator:hover, .quick-scroll-navigator.scrolling {{
            opacity: 1;
            transform: translateY(-2px);
        }}
        .qs-btn {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: none;
            background: transparent;
            color: var(--text-main);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.15s, transform 0.15s;
            text-decoration: none;
        }}
        .qs-btn:hover {{
            background: var(--primary-bg);
            color: var(--primary);
            transform: scale(1.1);
        }}
        .qs-progress-badge {{
            font-size: 11px;
            font-weight: 700;
            color: var(--primary);
            padding: 2px 4px;
            user-select: none;
        }}

        @media (max-width: 768px) {{
            .reader-topbar {{
                padding: 8px 12px;
                gap: 8px;
            }}
            .topbar-left {{
                min-width: 0;
                flex: 1 1 auto;
                gap: 8px;
            }}
            .topbar-title {{
                max-width: 140px;
                font-size: 13.5px;
            }}
            .topbar-right {{
                gap: 6px;
            }}
            .control-width-group {{
                display: none !important;
            }}
            .ctrl-label {{
                display: none;
            }}
            .ctrl-btn {{
                padding: 4px 7px;
                font-size: 12px;
                min-height: 28px;
            }}
            .reader-select {{
                padding: 4px 6px;
                font-size: 12px;
            }}
            .topbar-nav-link {{
                padding: 4px 8px;
                font-size: 12px;
            }}
            .size-indicator {{
                min-width: 28px;
                font-size: 11px;
            }}
            .container {{
                padding: 12px 10px;
                max-width: 100% !important;
            }}
            .doc-header {{
                padding: 18px 16px;
                margin-bottom: 16px;
                border-radius: 12px;
            }}
            .doc-title {{
                font-size: 18px;
                line-height: 1.35;
                margin-bottom: 8px;
            }}
            .doc-meta-row {{
                gap: 6px 10px;
                font-size: 11.5px;
            }}
            .toc-card {{
                padding: 16px 14px;
                margin-bottom: 16px;
                border-radius: 12px;
            }}
            .toc-title {{
                font-size: 14.5px;
                margin-bottom: 10px;
            }}
            .toc-list a {{
                font-size: 13px;
            }}
            .chapter-section {{
                padding: 18px 14px;
                margin-bottom: 18px;
                border-radius: 12px;
            }}
            .chapter-title {{
                font-size: 17px;
                margin-bottom: 16px;
                padding-bottom: 10px;
                flex-wrap: wrap;
                gap: 6px;
            }}
            .bilingual-para-block {{
                margin-bottom: 16px;
                padding-bottom: 14px;
            }}
            .para-source {{
                font-size: 15px;
                line-height: 1.6;
                word-break: break-word;
                overflow-wrap: break-word;
            }}
            .para-translation {{
                font-size: 14px;
                padding: 8px 10px;
                margin-bottom: 8px;
                line-height: 1.6;
                word-break: break-word;
                overflow-wrap: break-word;
            }}
            .para-notes-list {{
                gap: 6px;
                margin-top: 8px;
            }}
            .para-note-item {{
                padding: 6px 8px;
                font-size: 12px;
                flex-wrap: wrap;
                gap: 4px;
            }}
            .para-note-date {{
                margin-left: 0;
                width: 100%;
                font-size: 10px;
                opacity: 0.8;
            }}
            .notes-container {{
                padding: 12px 14px;
                margin-bottom: 16px;
                border-radius: 8px;
            }}
            .notes-box-header {{
                font-size: 13px;
                margin-bottom: 8px;
            }}
            .note-entry {{
                font-size: 12.5px;
                line-height: 1.55;
            }}
            table {{
                display: block;
                width: 100%;
                max-width: 100%;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }}
            th, td {{
                padding: 6px 8px;
                font-size: 12px;
                min-width: 70px;
            }}
            .quick-scroll-navigator {{
                bottom: 16px;
                right: 12px;
                padding: 4px 3px;
                gap: 3px;
                border-radius: 20px;
                opacity: 0.35;
            }}
            .qs-btn {{
                width: 32px;
                height: 32px;
                font-size: 12px;
            }}
            .qs-progress-badge {{
                font-size: 9.5px;
                padding: 1px 2px;
            }}
        }}

        @media (max-width: 480px) {{
            .topbar-title {{
                max-width: 105px;
                font-size: 12.5px;
            }}
            .topbar-right {{
                gap: 4px;
            }}
            .btn-print {{
                display: none;
            }}
            .doc-title {{
                font-size: 16.5px;
            }}
            .chapter-title {{
                font-size: 15.5px;
            }}
        }}

        @media print {{
            .reader-topbar, .quick-scroll-navigator {{ display: none !important; }}
            body {{ background: #fff; color: #000; padding: 0; font-size: 14px; }}
            .container {{ max-width: 100%; }}
            .chapter-section {{ page-break-after: always; border: none; box-shadow: none; padding: 0; }}
            .doc-header {{ border: none; box-shadow: none; padding: 0; }}
            .para-translation {{ background: #f5f5f5; border-left-color: #333; }}
            .image-block, .content-img {{ break-inside: avoid; page-break-inside: avoid; }}
        }}
    </style>
</head>
<body data-theme="sepia">
    <!-- Sticky Top Toolbar -->
    <header class="reader-topbar">
        <div class="topbar-left">
            <span class="doc-badge">双语研学</span>
            <span class="topbar-title">{_format_html_text(doc_title)}</span>
        </div>
        <div class="topbar-right">
            <!-- Theme Select -->
            <div class="control-group">
                <label for="theme-select" class="ctrl-label">🎨</label>
                <select id="theme-select" class="reader-select" onchange="setReaderTheme(this.value)">
                    <option value="dark">🌙 深邃夜色</option>
                    <option value="white">☀️ 纯净雅白</option>
                    <option value="sepia" selected>📜 墨玉羊皮</option>
                    <option value="forest">🍵 雅致墨绿</option>
                </select>
            </div>
            <!-- Font Size -->
            <div class="control-group">
                <span class="ctrl-label">字号:</span>
                <button class="ctrl-btn" onclick="adjustFontSize(-1)" title="缩小字号">A-</button>
                <span id="font-size-label" class="size-indicator">16px</span>
                <button class="ctrl-btn" onclick="adjustFontSize(1)" title="放大字号">A+</button>
            </div>
            <!-- Width -->
            <div class="control-group control-width-group">
                <span class="ctrl-label">版心:</span>
                <select id="width-select" class="reader-select" onchange="setReaderWidth(this.value)">
                    <option value="compact">紧凑 (850px)</option>
                    <option value="standard" selected>标准 (1100px)</option>
                    <option value="wide">宽屏 (1400px)</option>
                    <option value="full">全宽 (100%)</option>
                </select>
            </div>
            <!-- Portal & Flashcards Link -->
            {portal_nav_html}
            {flashcards_nav_html}
            <!-- Print -->
            <button class="ctrl-btn btn-print" onclick="window.print()" title="打印或保存为 PDF">🖨️ 打印</button>
        </div>
    </header>

    <div class="container">
        <header class="doc-header">
            <h1 class="doc-title">{_format_html_text(doc_title)}</h1>
            <div class="doc-meta-row">
                <span class="doc-badge">全景双语电子书</span>
                <span>全篇段落: {total_paras} 段</span>
                <span>已译段落: {trans_paras} 段</span>
                <span>生成时间: {created_at}</span>
            </div>
        </header>

        <nav class="toc-card" id="toc-nav-card">
            <div class="toc-title">📑 章节目录导航</div>
            {toc_html}
        </nav>

        <main class="chapters-container">
            {body_content}
        </main>

        <footer class="reader-footer" style="margin-top: 48px; padding: 28px 12px; text-align: center; border-top: 1px solid var(--border); color: var(--text-muted); font-size: 13px;">
            <p>基于开源项目 <a href="https://github.com/coodajingang/Ominididact" target="_blank" rel="noopener noreferrer" style="color: var(--primary); text-decoration: none; font-weight: 600;">Omnididact</a> 构建 · 全材料系统化自我教育与研学引擎</p>
            <p style="margin-top: 6px; font-size: 12px; opacity: 0.85;">遵循 Apache 2.0 开源协议 · 专注深度理解与长效记忆巩固，拒绝浮于表面的笔记收藏</p>
        </footer>
    </div>

    <!-- Quick Scroll Navigator -->
    <div class="quick-scroll-navigator" id="quick-scroll-nav">
        <button class="qs-btn" onclick="scrollToTop()" title="回到顶部">⬆️</button>
        <a href="#toc-nav-card" class="qs-btn" title="查看目录">📑</a>
        <div class="qs-progress-badge" id="qs-progress-text">0%</div>
        <button class="qs-btn" onclick="scrollToBottom()" title="滚到底部">⬇️</button>
    </div>

    <!-- Inlined Marked Parser -->
    <script>
    {marked_js}
    </script>

    <!-- Client-side Interactive Script -->
    <script>
    function setReaderTheme(theme) {{
        document.body.setAttribute('data-theme', theme);
        localStorage.setItem('study_reader_theme', theme);
        const sel = document.getElementById('theme-select');
        if (sel) sel.value = theme;
    }}

    let currentFontSize = 16;
    function adjustFontSize(delta) {{
        currentFontSize = Math.max(13, Math.min(24, currentFontSize + delta));
        document.documentElement.style.setProperty('--content-font-size', currentFontSize + 'px');
        const label = document.getElementById('font-size-label');
        if (label) label.textContent = currentFontSize + 'px';
        localStorage.setItem('study_reader_font_size', currentFontSize);
    }}

    function setReaderWidth(w) {{
        let maxWidth = '1100px';
        if (w === 'compact') maxWidth = '850px';
        else if (w === 'wide') maxWidth = '1400px';
        else if (w === 'full') maxWidth = '96%';
        document.documentElement.style.setProperty('--container-max-width', maxWidth);
        localStorage.setItem('study_reader_width', w);
        const sel = document.getElementById('width-select');
        if (sel) sel.value = w;
    }}

    function scrollToTop() {{
        window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function scrollToBottom() {{
        window.scrollTo({{ top: document.body.scrollHeight, behavior: 'smooth' }});
    }}

    document.addEventListener('DOMContentLoaded', () => {{
        // 1. Restore Preferences
        const savedTheme = localStorage.getItem('study_reader_theme') || 'sepia';
        setReaderTheme(savedTheme);

        const savedSize = parseInt(localStorage.getItem('study_reader_font_size'), 10);
        if (savedSize) {{
            currentFontSize = savedSize;
            adjustFontSize(0);
        }}

        const savedWidth = localStorage.getItem('study_reader_width') || 'standard';
        setReaderWidth(savedWidth);

        // 2. Render Markdown formatting and tables
        if (typeof marked !== 'undefined' && marked.parse) {{
            document.querySelectorAll('.md-render').forEach(el => {{
                const raw = el.getAttribute('data-raw');
                if (raw) {{
                    try {{
                        el.innerHTML = marked.parse(raw);
                    }} catch (e) {{
                        console.error('Marked render error:', e);
                    }}
                }}
            }});
        }}

        // 3. Quick scroll progress tracking
        const qsNav = document.getElementById('quick-scroll-nav');
        const progressText = document.getElementById('qs-progress-text');
        let scrollTimer = null;

        window.addEventListener('scroll', () => {{
            const scrollTop = window.scrollY || document.documentElement.scrollTop;
            const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
            const pct = scrollHeight > 0 ? Math.min(100, Math.max(0, Math.round((scrollTop / scrollHeight) * 100))) : 0;
            if (progressText) progressText.textContent = pct + '%';

            if (qsNav) {{
                qsNav.classList.add('scrolling');
                clearTimeout(scrollTimer);
                scrollTimer = setTimeout(() => {{
                    qsNav.classList.remove('scrolling');
                }}, 1200);
            }}
        }}, {{ passive: true }});
    }});
    </script>
</body>
</html>
"""
    with open(os.path.join(doc_dir, "full_bilingual.html"), "w", encoding="utf-8") as f:
        f.write(html_document)
    return html_document


def assemble_offline_flashcards_html(
    doc_id: str,
    index_link: str = "index.html",
    portal_link: Optional[str] = None
) -> str:
    """
    Generates a standalone, fully offline interactive Flashcard Study App (SPA)
    HTML file that runs seamlessly without Python / backend on Nginx or Cloudflare Pages.
    All card study, 3D flip, SM-2 reviews, mistake tracking, and settings are
    persisted locally in browser localStorage.
    """
    meta = load_doc_meta(doc_id) or {}
    doc_title = meta.get("filename", "研学材料")

    from study.flashcard_manager import load_doc_flashcards
    fc_data = load_doc_flashcards(doc_id)

    offline_payload = {
        "doc_id": doc_id,
        "title": doc_title,
        "index_link": index_link,
        "portal_link": portal_link,
        "chapters": meta.get("chapters", []),
        "settings": fc_data.get("settings", {}),
        "cards": fc_data.get("cards", [])
    }

    template_path = os.path.join(os.getcwd(), "templates", "flashcards.html")
    if not os.path.exists(template_path):
        return ""

    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 1. Inline marked.min.js
    marked_path = os.path.join(os.getcwd(), "static", "js", "marked.min.js")
    marked_code = ""
    if os.path.exists(marked_path):
        try:
            with open(marked_path, "r", encoding="utf-8") as mf:
                marked_code = mf.read()
        except Exception as me:
            logger.error(f"Failed to read marked.min.js for flashcards: {me}")

    script_marked_tag = '<script src="/static/js/marked.min.js"></script>'
    if script_marked_tag in html_content:
        html_content = html_content.replace(
            script_marked_tag,
            f'<script>\n{marked_code}\n</script>'
        )

    # 2. Inject window.OFFLINE_FLASHCARDS_DATA before the main script
    injection = f"""<script>
        window.OFFLINE_FLASHCARDS_DATA = {json.dumps(offline_payload, ensure_ascii=False)};
    </script>"""
    html_content = html_content.replace(
        "<script>\n        // Global State",
        f"{injection}\n    <script>\n        // Global State"
    )

    return html_content


def assemble_static_site_zip(doc_id: str) -> bytes:
    """
    Packages a production-ready, zero-dependency static study website for Nginx / Cloudflare Pages.
    Contains:
      - index.html (Bilingual Study Reader with themes, font scale, width adjuster, quick scroll)
      - flashcards.html (Interactive Offline Flashcard SPA with localStorage persistence)
      - README.md (Nginx configuration and Cloudflare Pages 1-click deployment guide)
    """
    import zipfile
    import io

    meta = load_doc_meta(doc_id) or {}
    doc_title = meta.get("filename", "Document")

    # Generate bilingual HTML linking to flashcards.html
    index_html = assemble_full_document_html(doc_id, flashcards_link="flashcards.html")

    # Generate offline flashcards HTML linking to index.html
    flashcards_html = assemble_offline_flashcards_html(doc_id, index_link="index.html")

    readme_content = f"""# 🌐 《{doc_title}》 静态研学站点发布包

本压缩包是由 **文件材料翻译与研学中心** 自动构建的纯静态 Web 资产包，**无需任何 Python 或后端服务器依赖**。
解压后可直接部署到 **Nginx**、**Apache**、**Cloudflare Pages**、**GitHub Pages** 或 **Vercel** 等任何静态 Web 托管服务。

---

## 📁 包含文件
* `index.html`: 双语研学文献阅读系统（含 4 套主题切换、字号/版心调节、快速滚动雷达、Markdown 表格自适应渲染）
* `flashcards.html`: 考点闪卡复习系统（3D 卡片翻转、Cloze 挖空揭晓、SM-2/错题攻坚、浏览器本地进度持久化）
* `README.md`: 本部署指南

---

## 🚀 部署方式一：Cloudflare Pages（推荐，免费且全球极速 CDN）
1. 登录 [Cloudflare 控制台](https://dash.cloudflare.com/)，在左侧导航选择 **Workers & Pages** -> **Create application** -> **Pages**。
2. 点击 **Upload assets**（直接上传静态资产）。
3. 项目名称任意填写（如 `cissp-study`），然后将本 zip 解压后的文件夹直接拖入网页上传区域。
4. 点击 **Deploy site**，10 秒内即可获得一个支持全局访问的专属 HTTPS 网址！

---

## 🐧 部署方式二：Nginx 部署
将本压缩包解压到服务器目标目录，例如 `/usr/share/nginx/html/study`：
```nginx
server {{
    listen 80;
    server_name study.yourdomain.com;

    root /usr/share/nginx/html/study;
    index index.html;

    location / {{
        try_files $uri $uri/ /index.html;
    }}

    # 启用 Gzip 加速传输
    gzip on;
    gzip_types text/plain text/css application/javascript application/json text/html;
}}
```
执行 `nginx -s reload` 即可上线！

---

## 💡 使用说明与特性
* **无网环境支持**：所有插图（Base64）和样式脚本均已完整打包在 HTML 中，在内网、断网或离线设备上双击 `index.html` 亦可无缝阅读与背诵。
* **学习进度保护**：闪卡页面的背诵进度、评分和错题集会自动保存在您访问浏览器的 `localStorage` 中。您也可以随时在卡片页点击 **【📤 导出 JSON】** 备份进度。
"""

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", index_html.encode("utf-8"))
        zf.writestr("flashcards.html", flashcards_html.encode("utf-8"))
        zf.writestr("README.md", readme_content.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def assemble_portal_html(site_title: str = "Omnididact · 个人研习大厅") -> str:
    """
    Renders the static Study Portal (Study Hall / Dashboard) SPA HTML.
    Driven dynamically by the sibling `./docs.json` file.
    """
    template_path = os.path.join(os.getcwd(), "templates", "portal.html")
    if not os.path.exists(template_path):
        return "<html><body><h1>研习大厅模板不存在</h1></body></html>"
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Robust template substitution for site_title
    content = re.sub(r'\{\{\s*site_title\s*(\|\s*default\([^)]+\))?\s*\}\}', site_title, content)
    return content


def assemble_incremental_patch_zip(doc_id: str) -> bytes:
    """
    Packages an incremental patch for adding a new document into an existing Multi-Doc Static Library.
    Directory structure inside zip:
      - docs/{doc_id}/index.html (links to flashcards.html and ../../index.html)
      - docs/{doc_id}/flashcards.html (links to index.html and ../../index.html)
      - patch_entry.json (the json block ready to append into the root docs.json)
      - README_PATCH.md (clear 3-step incremental update instructions)
    """
    import zipfile
    import io

    meta = load_doc_meta(doc_id) or {}
    doc_title = meta.get("filename", "Document")
    total_paras = meta.get("total_paragraphs", 0)
    created_at = meta.get("created_at", time.strftime("%Y-%m-%d"))
    file_type = meta.get("file_type", "doc")

    from study.flashcard_manager import load_doc_flashcards
    fc_data = load_doc_flashcards(doc_id) or {}
    cards = fc_data.get("cards", [])
    fc_count = len(cards)

    tags = []
    if file_type:
        tags.append(file_type.upper())
    for ch in meta.get("chapters", []):
        ch_title = ch.get("title", "")
        if ch_title and len(ch_title) <= 8 and ch_title not in tags:
            tags.append(ch_title)
    tags = tags[:4]

    # Generate document pages with portal_link
    index_html = assemble_full_document_html(
        doc_id,
        flashcards_link="flashcards.html",
        portal_link="../../index.html"
    )
    flashcards_html = assemble_offline_flashcards_html(
        doc_id,
        index_link="index.html",
        portal_link="../../index.html"
    )

    patch_entry = {
        "id": doc_id,
        "title": doc_title,
        "path": f"docs/{doc_id}/index.html",
        "flashcards_path": f"docs/{doc_id}/flashcards.html",
        "updated_at": created_at,
        "paragraph_count": total_paras,
        "flashcard_count": fc_count,
        "type": file_type,
        "tags": tags,
        "description": f"共包含 {total_paras} 个研学段落，配套 {fc_count} 个考点记忆闪卡。"
    }

    patch_entry_str = json.dumps(patch_entry, ensure_ascii=False, indent=2)

    readme_patch = f"""# 🧩 《{doc_title}》 研习空间增量更新包 (Patch)

本更新包用于将新研学材料《{doc_title}》增量并入你已经部署的 **多材料纯静态研习空间**（Cloudflare Pages、GitHub Pages 或 Nginx），无需重新全量打包。

---

## 🚀 增量发布 2 步法

### 第 1 步：解压并合并 `docs/` 目录
将本压缩包内的 `docs/{doc_id}/` 文件夹直接复制或上传到你站点根目录的 `docs/` 文件夹下。
完成后的目录结构应为：
```text
你的站点根目录/
├── index.html
├── docs.json
└── docs/
    ├── 已有材料A/
    └── {doc_id}/             <-- 刚才放进来的新材料
        ├── index.html
        └── flashcards.html
```

### 第 2 步：将下方 JSON 追加到根目录 `docs.json`
打开站点根目录的 `docs.json`，在最前方或最后方追加粘贴本文档的元数据对象（内容即同级 `patch_entry.json`）：

```json
{patch_entry_str}
```

---
💡 **更新完成**！刷新你的研习大厅首页，新材料的双语研学与考点闪卡将立即呈现！
"""

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"docs/{doc_id}/index.html", index_html.encode("utf-8"))
        zf.writestr(f"docs/{doc_id}/flashcards.html", flashcards_html.encode("utf-8"))
        zf.writestr("patch_entry.json", patch_entry_str.encode("utf-8"))
        zf.writestr("README_PATCH.md", readme_patch.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def assemble_library_site_zip(
    doc_ids: Optional[List[str]] = None,
    site_title: str = "Omnididact · 个人研习大厅"
) -> bytes:
    """
    Packages a full-featured, zero-dependency Multi-Document Static Knowledge Base for
    Nginx / Cloudflare Pages.
    Contains:
      - index.html (Central Knowledge Base Portal SPA)
      - docs.json (Manifest containing metadata for all bundled documents)
      - README.md (Comprehensive deployment & incremental maintenance guide)
      - docs/{doc_id}/... (Bilingual reader & flashcards for each document)
    """
    import zipfile
    import io

    if doc_ids is None:
        # Collect all existing documents
        all_docs = list_all_documents()
        doc_ids = [d["doc_id"] for d in all_docs if "doc_id" in d]

    from study.flashcard_manager import load_doc_flashcards

    docs_json_entries = []
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_id in doc_ids:
            meta = load_doc_meta(doc_id)
            if not meta:
                continue

            doc_title = meta.get("filename", "Document")
            total_paras = meta.get("total_paragraphs", 0)
            created_at = meta.get("created_at", time.strftime("%Y-%m-%d"))
            file_type = meta.get("file_type", "doc")

            fc_data = load_doc_flashcards(doc_id) or {}
            cards = fc_data.get("cards", [])
            fc_count = len(cards)

            tags = []
            if file_type:
                tags.append(file_type.upper())
            for ch in meta.get("chapters", []):
                ch_title = ch.get("title", "")
                if ch_title and len(ch_title) <= 8 and ch_title not in tags:
                    tags.append(ch_title)
            tags = tags[:4]

            entry = {
                "id": doc_id,
                "title": doc_title,
                "path": f"docs/{doc_id}/index.html",
                "flashcards_path": f"docs/{doc_id}/flashcards.html",
                "updated_at": created_at,
                "paragraph_count": total_paras,
                "flashcard_count": fc_count,
                "type": file_type,
                "tags": tags,
                "description": f"共包含 {total_paras} 个研学段落，配套 {fc_count} 个考点记忆闪卡。"
            }
            docs_json_entries.append(entry)

            # Build sub-doc index.html & flashcards.html
            index_html = assemble_full_document_html(
                doc_id,
                flashcards_link="flashcards.html",
                portal_link="../../index.html"
            )
            flashcards_html = assemble_offline_flashcards_html(
                doc_id,
                index_link="index.html",
                portal_link="../../index.html"
            )

            zf.writestr(f"docs/{doc_id}/index.html", index_html.encode("utf-8"))
            zf.writestr(f"docs/{doc_id}/flashcards.html", flashcards_html.encode("utf-8"))

        # Build Central Portal index.html & docs.json
        portal_html = assemble_portal_html(site_title=site_title)
        docs_json_str = json.dumps(docs_json_entries, ensure_ascii=False, indent=2)

        zf.writestr("index.html", portal_html.encode("utf-8"))
        zf.writestr("docs.json", docs_json_str.encode("utf-8"))

        # Robots.txt
        robots_txt = """User-agent: *
Allow: /

Sitemap: sitemap.xml
"""
        zf.writestr("robots.txt", robots_txt.encode("utf-8"))

        # Sitemap.xml for search engines & AI index (GEO)
        curr_date = time.strftime("%Y-%m-%d")
        sitemap_urls = [
            f"""  <url>
    <loc>index.html</loc>
    <lastmod>{curr_date}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""
        ]
        for entry in docs_json_entries:
            doc_path = entry.get("path", "")
            fc_path = entry.get("flashcards_path", "")
            entry_date = entry.get("updated_at", curr_date)
            if doc_path:
                sitemap_urls.append(f"""  <url>
    <loc>{doc_path}</loc>
    <lastmod>{entry_date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
            if fc_path:
                sitemap_urls.append(f"""  <url>
    <loc>{fc_path}</loc>
    <lastmod>{entry_date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>""")

        sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(sitemap_urls)}
</urlset>
"""
        zf.writestr("sitemap.xml", sitemap_xml.encode("utf-8"))

        if os.path.exists("static/favicon.svg"):
            zf.write("static/favicon.svg", "static/favicon.svg")

        # Build Root README.md
        readme_md = f"""# 🏛️ {site_title} 多材料静态发布包

本压缩包是由 **Omnididact · 全材料系统化自我教育与研学引擎** 构建的纯静态研习空间，**无需任何 Python 或后端服务器依赖**。
解压后可直接部署到 **GitHub Pages**、**Cloudflare Pages**、**Nginx**、**Vercel** 或任何静态 Web 托管服务。

---

## 📁 目录结构
* `index.html`: 个人研习大厅门户（含独立 SEO/GEO、结构化元数据、即时搜索与主题切换）
* `docs.json`: 站点研习材料清单数据源
* `robots.txt`: 搜索引擎爬虫协议规范
* `sitemap.xml`: 站点地图，助力 Google / Bing / 百度 等搜索引擎及 AI 引擎快速收录
* `docs/`: 各材料研学独立子空间（每个子目录下包含独有 SEO/GEO 双语阅读器与离线闪卡系统）
* `README.md`: 本部署与维护指引

---

## 🚀 部署指引

### 方式一：GitHub Pages（极简免费）
1. 在 GitHub 创建新仓库（如 `my-study-hall`）。
2. 将本压缩包内的所有文件解压后推送到仓库的 `main` 分支（或 `gh-pages` 分支）。
3. 在 GitHub 仓库的 **Settings** -> **Pages** 中，将 Source 选为 **Deploy from a branch**，Branch 选择 `main` / `root`。
4. 保存后约 1 分钟即可通过 `https://<用户名>.github.io/my-study-hall/` 在线访问！

### 方式二：Cloudflare Pages（推荐，全球极速）
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)，进入 **Workers & Pages** -> **Create application** -> **Pages** -> **Upload assets**。
2. 项目名称填写（如 `my-study-hall`）。
3. 将本压缩包解压后的**整个文件夹**直接拖入网页上传区。
4. 点击 **Deploy site**，10 秒内即可拥有全局 CDN 加速的专属个人研习空间！

### 方式二：Nginx 服务器
解压到目标目录（如 `/var/www/study-library`）：
```nginx
server {{
    listen 80;
    server_name library.yourdomain.com;
    root /var/www/study-library;
    index index.html;

    location / {{
        try_files $uri $uri/ /index.html;
    }}

    gzip on;
    gzip_types text/plain text/css application/javascript application/json text/html;
}}
```
执行 `nginx -s reload` 即刻上线！

---

## 🧩 后续如何增量添加新文档？
后续若有新材料处理完成，无需重新全量打包整站：
1. 在研学系统中选择该文档导出 **【🧩 增量补丁包 (.zip)】**；
2. 将补丁包解压后的 `docs/{doc_id}` 放入服务器/站点的 `docs/` 目录下；
3. 将补丁包中的 `patch_entry.json` 内容追加粘贴进站点根目录的 `docs.json` 数组中；
4. 刷新首页，新文档即可自动在导航大厅中亮相！
"""
        zf.writestr("README.md", readme_md.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# ==========================================================
# Document Inspection & Initialization
# ==========================================================

async def initialize_document(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    doc_id = f"doc_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    doc_dir = get_doc_dir(doc_id)
    
    ext = os.path.splitext(filename)[1].lower()
    orig_path = os.path.join(doc_dir, f"original{ext}")
    with open(orig_path, "wb") as f:
        f.write(file_bytes)
        
    if ext in (".ppt", ".pptx"):
        raise ValueError("PPT 演示文稿请在 PowerPoint、WPS 或 Keynote 中点击【文件 -> 另存为 / 导出为 PDF】后再上传，以确保完整保留幻灯片图表与排版！")

    is_scanned = False
    if ext == ".pdf":
        file_type = "pdf"
    elif ext in (".docx", ".doc"):
        file_type = "docx"
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg"):
        file_type = "image"
        is_scanned = True
    elif ext == ".txt":
        file_type = "txt"
    elif ext in (".md", ".markdown"):
        file_type = "md"
    else:
        file_type = "other"

    total_pages = 1
    
    if ext == ".pdf":
        try:
            doc = fitz.open(orig_path)
            total_pages = len(doc)
            check_pages = min(total_pages, 10)
            total_chars = sum(len(doc[p].get_text().strip()) for p in range(check_pages))
            avg_chars = total_chars / max(check_pages, 1)
            is_scanned = (avg_chars < 30)
            doc.close()
        except Exception as e:
            logger.error(f"PDF inspection error: {e}")
            is_scanned = True
    elif ext in (".docx", ".doc"):
        info = doc_converter.inspect_document(file_bytes, filename)
        total_pages = info.get("total_pages", 1)
        is_scanned = True
    elif ext in (".txt", ".md", ".markdown"):
        try:
            lines = len(file_bytes.splitlines())
            total_pages = max(1, (lines + 49) // 50)
        except Exception:
            total_pages = 1
        is_scanned = False
        
    meta = {
        "doc_id": doc_id,
        "filename": filename,
        "file_type": file_type,
        "is_scanned": is_scanned,
        "language": "en",
        "total_pages": total_pages,
        "total_paragraphs": 0,
        "translated_paragraphs": 0,
        "status": "uploaded",
        "progress": {
            "current_page": 0,
            "total_pages": total_pages,
            "percent": 0
        },
        "error_message": "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chapters": []
    }
    save_doc_meta(doc_id, meta)
    # Initialize per-document settings by inheriting global defaults
    get_study_settings(doc_id)
    return meta

async def extract_scanned_or_doc_content(
    doc_id: str,
    is_doc: bool = False,
    progress_callback: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    doc_dir = get_doc_dir(doc_id)
    meta = load_doc_meta(doc_id) or {}
    doc_title = meta.get("filename", "材料原件")

    # Locate the actual original uploaded file
    file_path = None
    ext = ".pdf"
    for candidate in os.listdir(doc_dir):
        if candidate.startswith("original."):
            file_path = os.path.join(doc_dir, candidate)
            ext = os.path.splitext(candidate)[1].lower()
            break

    if not file_path or not os.path.exists(file_path):
        ext = ".docx" if is_doc else ".pdf"
        file_path = os.path.join(doc_dir, f"original{ext}")
        if not os.path.exists(file_path) and is_doc:
            file_path = os.path.join(doc_dir, "original.doc")
        
    with open(file_path, "rb") as f:
        file_bytes = f.read()
        
    filename = os.path.basename(file_path)
    page_images = doc_converter.convert_document_to_page_images(file_bytes, filename, pages_str="all", dpi=150)
    total_pages = len(page_images)
    
    for page_num, img_bytes in page_images:
        img_name = f"page_{page_num}.png"
        img_path = os.path.join(doc_dir, "images", img_name)
        with open(img_path, "wb") as f_img:
            f_img.write(img_bytes)
        if progress_callback:
            try:
                progress_callback(page_num, total_pages)
            except Exception:
                pass
            
    chapter_defs = []
    if not is_doc and ext == ".pdf":
        try:
            doc = fitz.open(file_path)
            toc = doc.get_toc()
            min_lvl = min((item[0] for item in toc), default=1) if toc else 1
            top_toc = [item for item in toc if item[0] == min_lvl]
            if top_toc:
                for i in range(len(top_toc)):
                    title = top_toc[i][1].strip()
                    start_p = max(1, top_toc[i][2])
                    end_p = (max(1, top_toc[i+1][2]) - 1) if i + 1 < len(top_toc) else total_pages
                    if end_p < start_p:
                        end_p = start_p
                    chapter_defs.append({"title": title, "start_page": start_p, "end_page": end_p})
            doc.close()
        except Exception as e:
            logger.warning(f"Error reading PDF toc: {e}")
        
    if not chapter_defs:
        chapter_defs = [{"title": doc_title or "文档全文", "start_page": 1, "end_page": total_pages}]
        
    chapters = []
    para_counter = 1
    for ch_idx, ch_def in enumerate(chapter_defs, 1):
        ch_paras = []
        for pno in range(ch_def["start_page"], ch_def["end_page"] + 1):
            ch_paras.append({
                "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                "page": pno,
                "type": "scanned_page",
                "image_url": f"/api/study/documents/{doc_id}/images/page_{pno}.png",
                "english": f"![{doc_title} (第 {pno} 页)](/api/study/documents/{doc_id}/images/page_{pno}.png)",
                "chinese": "",
                "status": "pending",
                "no_translate": False
            })
            para_counter += 1
        chapters.append({
            "chapter_id": f"ch_{ch_idx:03d}",
            "title": ch_def["title"],
            "paragraphs": ch_paras
        })
        
    return "en", chapters

# ==========================================================
# Background Extraction Pipeline
# ==========================================================

async def process_document_pipeline(doc_id: str):
    """
    Main background pipeline:
    Extracts content using pymupdf4llm, partitions by TOC bookmarks, saves structured chapters.
    Fast conversion without calling LLMs at upload time.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        logger.error(f"Cannot process doc {doc_id}: meta not found")
        return
        
    try:
        meta["status"] = "extracting"
        meta["progress"] = {
            "current_page": 0,
            "total_pages": meta.get("total_pages", 1),
            "percent": 0
        }
        save_doc_meta(doc_id, meta)
        doc_dir = get_doc_dir(doc_id)
        
        def on_progress(curr: int, total: int):
            m = load_doc_meta(doc_id)
            if m:
                pct = int(curr / max(total, 1) * 100)
                m["progress"] = {
                    "current_page": curr,
                    "total_pages": total,
                    "percent": pct
                }
                save_doc_meta(doc_id, m)
                
        if meta.get("file_type") in ("txt", "md"):
            lang, chapters = extract_text_or_markdown_content(
                doc_id, doc_dir, meta.get("filename", ""), progress_callback=on_progress
            )
        elif meta["file_type"] == "docx":
            lang, chapters = await extract_scanned_or_doc_content(doc_id, is_doc=True, progress_callback=on_progress)
        elif meta["is_scanned"]:
            lang, chapters = await extract_scanned_or_doc_content(doc_id, is_doc=False, progress_callback=on_progress)
        else:
            try:
                lang, chapters = extract_pdf_native(doc_id, doc_dir, progress_callback=on_progress)
            except Exception as e_native:
                logger.warning(f"Native parser failed on {doc_id}: {e_native}. Falling back to legacy pymupdf4llm parser.")
                lang, chapters = extract_pdf_with_pymupdf4llm(doc_id, doc_dir, progress_callback=on_progress)
            
        meta["language"] = lang
        total_paras = 0
        completed_paras = 0
        chapter_metas = []
        
        for ch in chapters:
            ch_paras = ch.get("paragraphs", [])
            total_paras += len(ch_paras)
            if lang == "zh":
                completed_paras += len(ch_paras)
            else:
                completed_paras += sum(1 for p in ch_paras if p.get("status") == "completed")
                
            write_chapter_files(doc_id, ch, lang)
            chapter_metas.append({
                "chapter_id": ch["chapter_id"],
                "title": ch["title"],
                "paragraph_count": len(ch_paras),
                "file": f"chapters/{ch['chapter_id']}.md"
            })
            
        meta["total_paragraphs"] = total_paras
        meta["translated_paragraphs"] = completed_paras
        meta["chapters"] = chapter_metas
        meta["progress"] = {
            "current_page": meta.get("total_pages", 1),
            "total_pages": meta.get("total_pages", 1),
            "percent": 100
        }
        meta["status"] = "completed"
        save_doc_meta(doc_id, meta)
        assemble_full_document_markdown(doc_id)
        logger.info(f"Document {doc_id} extraction completed and ready for study.")
    except Exception as e:
        logger.exception(f"Error in document pipeline for {doc_id}: {e}")
        meta["status"] = "error"
        meta["error_message"] = str(e)
        save_doc_meta(doc_id, meta)

def pause_document_pipeline(doc_id: str):
    if doc_id in ACTIVE_TASKS:
        ACTIVE_TASKS[doc_id].set()
    meta = load_doc_meta(doc_id)
    if meta and meta["status"] == "translating":
        meta["status"] = "paused"
        save_doc_meta(doc_id, meta)

# ==========================================================
# On-Demand Translation Operations
# ==========================================================

async def translate_single_paragraph(doc_id: str, chapter_id: str, paragraph_id: str) -> Dict[str, Any]:
    """
    Translates a single paragraph on-demand when user clicks 'Translate'.
    Carries sliding context window (preceding paragraph) for terminology & pronoun consistency.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")
        
    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)
        
    target_p = None
    target_idx = -1
    for idx, p in enumerate(ch_data.get("paragraphs", [])):
        if p["id"] == paragraph_id:
            target_p = p
            target_idx = idx
            break
            
    if not target_p:
        raise ValueError(f"Paragraph {paragraph_id} not found")
        
    if target_p.get("type") in ("code", "formula") or target_p.get("no_translate"):
        target_p["chinese"] = ""
        target_p["status"] = "completed"
        write_chapter_files(doc_id, ch_data, meta.get("language", "en"))
        return target_p
        
    # Sliding context window: find nearest preceding readable text paragraph
    prev_english = ""
    prev_chinese = ""
    if target_idx > 0:
        for prev_p in reversed(ch_data["paragraphs"][:target_idx]):
            if prev_p.get("type") in ("text", "scanned_page") and prev_p.get("english"):
                prev_english = prev_p.get("english", "")
                prev_chinese = prev_p.get("chinese", "")
                break
                
    settings = get_study_settings(doc_id)
    prompt_template = settings.get("translation_prompt_template", DEFAULT_TRANSLATION_PROMPT)
    
    if target_p.get("type") == "scanned_page":
        img_url = target_p.get("image_url", "")
        img_filename = os.path.basename(img_url)
        img_path = os.path.join(doc_dir, "images", img_filename)
        if os.path.exists(img_path):
            with open(img_path, "rb") as f_img:
                b64_img = base64.b64encode(f_img.read()).decode("utf-8")
            ocr_text = await call_vllm_ocr(b64_img, settings)
            target_p["extracted_text"] = ocr_text or ""
            target_p["image_url"] = img_url
            target_p["english"] = f"![原件材料]({img_url})"
            
            if ocr_text:
                if is_predominantly_target_lang(ocr_text, "zh"):
                    logger.info(f"Scanned page {paragraph_id} OCR is predominantly Chinese, skipping LLM translation.")
                    target_p["chinese"] = ""
                    target_p["no_translate"] = True
                else:
                    cn_trans = await call_llm_translate_paragraph(
                        ocr_text,
                        prompt_template,
                        settings,
                        prev_english=prev_english,
                        prev_chinese=prev_chinese
                    )
                    target_p["chinese"] = cn_trans
            else:
                target_p["chinese"] = "[OCR 未检测到有效文字]"
        target_p["status"] = "completed"
    else:
        eng_text = target_p.get("english", "")
        if eng_text:
            if is_predominantly_target_lang(eng_text, "zh"):
                logger.info(f"Paragraph {paragraph_id} is predominantly Chinese, skipping LLM translation.")
                target_p["chinese"] = ""
                target_p["no_translate"] = True
            else:
                cn_trans = await call_llm_translate_paragraph(
                    eng_text,
                    prompt_template,
                    settings,
                    prev_english=prev_english,
                    prev_chinese=prev_chinese
                )
                target_p["chinese"] = cn_trans
        else:
            target_p["chinese"] = ""
        target_p["status"] = "completed"
        
    write_chapter_files(doc_id, ch_data, meta.get("language", "en"))
    
    total_completed = 0
    for ch_info in meta.get("chapters", []):
        ch_file = os.path.join(doc_dir, "chapters", f"{ch_info['chapter_id']}.json")
        if os.path.exists(ch_file):
            with open(ch_file, "r", encoding="utf-8") as f_ch:
                c_data = json.load(f_ch)
            total_completed += sum(1 for item in c_data.get("paragraphs", []) if item.get("status") == "completed")
            
    meta["translated_paragraphs"] = total_completed
    save_doc_meta(doc_id, meta)
    assemble_full_document_markdown(doc_id)
    return target_p

async def extract_paragraph_text_content(doc_id: str, chapter_id: str, paragraph_id: str) -> Dict[str, Any]:
    """
    Extracts high-fidelity text/OCR from a scanned page or image paragraph using VLM,
    and persists it into paragraph's `extracted_text`.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")
        
    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)
        
    target_p = None
    for p in ch_data.get("paragraphs", []):
        if p["id"] == paragraph_id:
            target_p = p
            break
            
    if not target_p:
        raise ValueError(f"Paragraph {paragraph_id} not found")

    settings = get_study_settings(doc_id)
    img_url = target_p.get("image_url", "")
    if not img_url and "![" in target_p.get("english", ""):
        m = re.search(r'\((/api/study/documents/[^/]+/images/[^)]+)\)', target_p.get("english", ""))
        if m:
            img_url = m.group(1)

    if img_url:
        img_filename = os.path.basename(img_url)
        img_path = os.path.join(doc_dir, "images", img_filename)
        if os.path.exists(img_path):
            with open(img_path, "rb") as f_img:
                b64_img = base64.b64encode(f_img.read()).decode("utf-8")
            ocr_text = await call_vllm_ocr(b64_img, settings)
            target_p["extracted_text"] = ocr_text or ""
            target_p["image_url"] = img_url
            write_chapter_files(doc_id, ch_data, meta.get("language", "en"))
            return target_p

    # Fallback if already plain text
    if not target_p.get("extracted_text"):
        target_p["extracted_text"] = target_p.get("english", "")
    return target_p

def edit_paragraph_content(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    source_text: str,
    is_heading: Optional[bool] = None,
    paragraph_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates the source text (english) of a paragraph.
    Handles paragraph type transition (e.g. image -> text),
    clears image_url if converted to text, and resets translation status.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")

    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)

    target_p = None
    for p in ch_data.get("paragraphs", []):
        if p["id"] == paragraph_id:
            target_p = p
            break

    if not target_p:
        raise ValueError(f"Paragraph {paragraph_id} not found")

    cleaned_text = source_text.strip()
    if is_heading is True and not cleaned_text.startswith("#"):
        cleaned_text = f"## {cleaned_text}"

    has_img_markdown = bool(re.search(r'!\[.*?\]\(.*?\)', cleaned_text))

    # Determine final paragraph type
    new_type = paragraph_type
    if not new_type:
        if is_heading is True or cleaned_text.startswith("#"):
            new_type = "text"
        elif has_img_markdown:
            new_type = "image"
        elif target_p.get("type") in ("image", "scanned_page") or target_p.get("image_url"):
            new_type = "text"
        else:
            new_type = target_p.get("type", "text")

    if new_type == "heading":
        new_type = "text"
        if not cleaned_text.startswith("#"):
            cleaned_text = f"## {cleaned_text}"

    target_p["type"] = new_type

    # If transitioning away from image, clear image_url
    if new_type not in ("image", "scanned_page") and not has_img_markdown:
        target_p["image_url"] = ""
    elif has_img_markdown and not target_p.get("image_url"):
        m = re.search(r'!\[.*?\]\((.*?)\)', cleaned_text)
        if m:
            target_p["image_url"] = m.group(1)

    is_zh = is_predominantly_target_lang(cleaned_text, "zh")
    target_p["english"] = cleaned_text
    target_p["chinese"] = ""

    if new_type in ("image", "code"):
        target_p["no_translate"] = True
        target_p["status"] = "completed"
    else:
        target_p["no_translate"] = is_zh
        target_p["status"] = "completed" if is_zh else "pending"

    write_chapter_files(doc_id, ch_data, meta.get("language", "en"))

    total_completed = 0
    for ch_info in meta.get("chapters", []):
        ch_file = os.path.join(doc_dir, "chapters", f"{ch_info['chapter_id']}.json")
        if os.path.exists(ch_file):
            with open(ch_file, "r", encoding="utf-8") as f_ch:
                c_data = json.load(f_ch)
            total_completed += sum(1 for item in c_data.get("paragraphs", []) if item.get("status") == "completed")
    meta["translated_paragraphs"] = total_completed
    save_doc_meta(doc_id, meta)

    return target_p

def insert_paragraph_after(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    new_text: str
) -> Dict[str, Any]:
    """
    Inserts a newly created paragraph immediately after the specified paragraph_id.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")

    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)

    paragraphs = ch_data.get("paragraphs", [])
    target_idx = -1
    for idx, p in enumerate(paragraphs):
        if p["id"] == paragraph_id:
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Paragraph {paragraph_id} not found")

    target_p = paragraphs[target_idx]
    cleaned_text = new_text.strip()
    is_zh = is_predominantly_target_lang(cleaned_text, "zh")

    prefix = "p"
    if "_" in target_p.get("id", ""):
        parts = target_p["id"].split("_")
        if len(parts) >= 2:
            prefix = f"{parts[0]}_{parts[1]}"
    new_id = f"{prefix}_{str(int(time.time()))[-4:]}_{uuid.uuid4().hex[:4]}"

    new_p = {
        "id": new_id,
        "type": "text",
        "english": cleaned_text,
        "chinese": "",
        "status": "completed" if is_zh else "pending",
        "no_translate": is_zh,
        "notes": [],
        "page": target_p.get("page", 1)
    }

    paragraphs.insert(target_idx + 1, new_p)
    write_chapter_files(doc_id, ch_data, meta.get("language", "en"))

    meta["total_paragraphs"] = meta.get("total_paragraphs", 0) + 1
    for ch_meta in meta.get("chapters", []):
        if ch_meta.get("chapter_id") == chapter_id:
            ch_meta["paragraph_count"] = len(paragraphs)
            break
    save_doc_meta(doc_id, meta)

    return new_p

TERMINAL_PUNCTUATION = {'.', '。', '!', '！', '?', '？', '…', '｡', '﹗', '﹖'}
CLOSING_QUOTES_BRACKETS = {'"', "'", '”', '’', '»', '›', '」', '』', ')', '）', ']', '】', '}', '｝', '〉', '》', '>'}
PUNCT_CHARS = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
                  "，。！？；：、“”‘’（）《》【】…—～·・「」『』〈〉〔〕［］｛｝")

def is_sentence_terminator(text: str) -> bool:
    """检查文本末尾是否为句号等结束符（兼容末尾紧随的闭引号、括号等）"""
    s = text.rstrip()
    if not s:
        return False
    idx = len(s) - 1
    while idx >= 0 and s[idx] in CLOSING_QUOTES_BRACKETS:
        idx -= 1
    if idx < 0:
        return False
    core = s[:idx + 1]
    if core.endswith("..."):
        return True
    return core[-1] in TERMINAL_PUNCTUATION

def ends_with_punctuation(text: str) -> bool:
    """检查文本末尾是否以标点符号结尾"""
    s = text.rstrip()
    if not s:
        return False
    c = s[-1]
    cat = unicodedata.category(c)
    if cat.startswith('P') or cat.startswith('S'):
        return True
    return c in PUNCT_CHARS

def concatenate_merged_paragraphs(t1: str, t2: str) -> str:
    """
    合并段落拼接规则：
    1. 若前一段结尾为句号等结束符，使用换行拼接；
    2. 若无标点，使用空格拼接；
    3. 否则直接拼接。
    """
    s1 = t1.rstrip()
    s2 = t2.lstrip()
    if not s1:
        return s2
    if not s2:
        return s1

    if is_sentence_terminator(s1):
        return f"{s1}\n{s2}"
    elif not ends_with_punctuation(s1):
        return f"{s1} {s2}"
    else:
        return f"{s1}{s2}"

def merge_paragraphs(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    direction: str = "next"
) -> Dict[str, Any]:
    """
    Merges a paragraph with either its preceding ('prev') or succeeding ('next') paragraph.
    Clears translation and chat history of the merged paragraphs.
    Removes the other paragraph and persists changes.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")

    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)

    paragraphs = ch_data.get("paragraphs", [])
    target_idx = -1
    for idx, p in enumerate(paragraphs):
        if p["id"] == paragraph_id:
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Paragraph {paragraph_id} not found")

    if direction == "prev":
        if target_idx == 0:
            raise ValueError("当前段落已是本章第一段，无法与上一段合并")
        first_idx = target_idx - 1
        second_idx = target_idx
    elif direction == "next":
        if target_idx >= len(paragraphs) - 1:
            raise ValueError("当前段落已是本章最后一段，无法与下一段合并")
        first_idx = target_idx
        second_idx = target_idx + 1
    else:
        raise ValueError(f"Invalid merge direction: {direction}")

    first_p = paragraphs[first_idx]
    second_p = paragraphs[second_idx]

    t1 = first_p.get("english", "")
    t2 = second_p.get("english", "")

    merged_text = concatenate_merged_paragraphs(t1, t2)

    first_p["english"] = merged_text
    first_p["chinese"] = ""
    is_zh = is_predominantly_target_lang(merged_text, "zh")
    first_p["status"] = "completed" if is_zh else "pending"
    first_p["no_translate"] = is_zh

    # Merge notes if any
    first_notes = first_p.get("notes") or []
    second_notes = second_p.get("notes") or []
    first_p["notes"] = first_notes + second_notes

    removed_id = second_p["id"]
    paragraphs.pop(second_idx)

    # Clear chat history for both paragraph IDs
    try:
        clear_chat_history(doc_dir, "paragraph", chapter_id, first_p["id"])
        clear_chat_history(doc_dir, "paragraph", chapter_id, removed_id)
    except Exception as e:
        logger.warning(f"Failed to clear chat history on merge: {e}")

    write_chapter_files(doc_id, ch_data, meta.get("language", "en"))

    # Update document meta
    meta["total_paragraphs"] = max(0, meta.get("total_paragraphs", 1) - 1)
    for ch_meta in meta.get("chapters", []):
        if ch_meta.get("chapter_id") == chapter_id:
            ch_meta["paragraph_count"] = len(paragraphs)
            break
    save_doc_meta(doc_id, meta)

    return {
        "merged_paragraph": first_p,
        "removed_id": removed_id,
        "chapter_id": chapter_id
    }

def delete_paragraph(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str
) -> Dict[str, Any]:
    """
    Deletes a paragraph from a chapter, along with its notes, chat history, and associated flashcards.
    Updates chapter files and document metadata.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")

    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)

    paragraphs = ch_data.get("paragraphs", [])
    target_idx = -1
    for idx, p in enumerate(paragraphs):
        if p["id"] == paragraph_id:
            target_idx = idx
            break

    if target_idx == -1:
        raise ValueError(f"Paragraph {paragraph_id} not found")

    removed_p = paragraphs.pop(target_idx)

    # 1. Clear chat history
    try:
        clear_chat_history(doc_dir, "paragraph", chapter_id, paragraph_id)
    except Exception as e:
        logger.warning(f"Failed to clear chat history for {paragraph_id}: {e}")

    # 2. Delete associated flashcards if any
    deleted_cards_count = 0
    try:
        from study.flashcard_manager import delete_flashcards_by_paragraph
        deleted_cards_count = delete_flashcards_by_paragraph(doc_id, paragraph_id)
    except Exception as e:
        logger.warning(f"Failed to delete flashcards for {paragraph_id}: {e}")

    # 3. Update and write chapter files
    write_chapter_files(doc_id, ch_data, meta.get("language", "en"))
    assemble_full_document_markdown(doc_id)

    # 4. Update document metadata
    meta["total_paragraphs"] = max(0, meta.get("total_paragraphs", 1) - 1)
    if removed_p.get("status") == "completed":
        meta["translated_paragraphs"] = max(0, meta.get("translated_paragraphs", 1) - 1)
    for ch_meta in meta.get("chapters", []):
        if ch_meta.get("chapter_id") == chapter_id:
            ch_meta["paragraph_count"] = len(paragraphs)
            break
    save_doc_meta(doc_id, meta)

    return {
        "success": True,
        "deleted_paragraph_id": paragraph_id,
        "chapter_id": chapter_id,
        "remaining_paragraphs": len(paragraphs),
        "deleted_cards_count": deleted_cards_count,
        "total_paragraphs": meta["total_paragraphs"],
        "translated_paragraphs": meta["translated_paragraphs"]
    }

async def translate_chapter_paragraphs(doc_id: str, chapter_id: str) -> Dict[str, Any]:
    """
    Translates all untranslated paragraphs in a chapter consecutively.
    """
    meta = load_doc_meta(doc_id)
    if not meta:
        raise ValueError(f"Document {doc_id} not found")
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")
    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)
        
    for p in ch_data.get("paragraphs", []):
        if p.get("status") != "completed" and p.get("type") not in ("image", "code") and not p.get("no_translate"):
            await translate_single_paragraph(doc_id, chapter_id, p["id"])
            
    with open(ch_json_path, "r", encoding="utf-8") as f:
        updated_data = json.load(f)
    return updated_data

# ==========================================================
# Chat discussion with Surrounding Context (Default N=2, M=2)
# ==========================================================

async def chat_with_paragraph(
    doc_id: str,
    chapter_id: str,
    paragraph_id: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    prev_count: int = 2,
    next_count: int = 2,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
):
    doc_dir = get_doc_dir(doc_id)
    ch_json_path = os.path.join(doc_dir, "chapters", f"{chapter_id}.json")
    if not os.path.exists(ch_json_path):
        raise ValueError(f"Chapter {chapter_id} not found")
        
    with open(ch_json_path, "r", encoding="utf-8") as f:
        ch_data = json.load(f)
        
    paragraphs = ch_data.get("paragraphs", [])
    target_idx = -1
    for idx, p in enumerate(paragraphs):
        if p["id"] == paragraph_id:
            target_idx = idx
            break
            
    if target_idx == -1:
        raise ValueError(f"Paragraph {paragraph_id} not found")
        
    target_p = paragraphs[target_idx]
    settings = get_study_settings(doc_id)
    target_model_name = (model_override or settings.get("chat_model") or settings.get("default_chat_model") or "").lower()
    is_vision = any(k in target_model_name for k in ("vision", "-vl", "vl-", "vlm", "llava", "gpt-4o", "gemini", "claude-3", "paddleocr-vl")) or target_model_name == "qwen3.5-27b-v20260417"

    is_target_img = target_p.get("type") in ("scanned_page", "image") or bool(target_p.get("image_url")) or "![" in target_p.get("english", "")

    # If target is image and model is text-only, and no extracted_text yet -> Auto OCR extract!
    if is_target_img and not is_vision and not target_p.get("extracted_text"):
        try:
            target_p = await extract_paragraph_text_content(doc_id, chapter_id, paragraph_id)
        except Exception as e:
            logger.warning(f"Auto OCR extraction failed in chat_with_paragraph: {e}")

    def format_para_chat_text(p: Dict[str, Any], is_target: bool) -> str:
        is_img = p.get("type") in ("scanned_page", "image") or bool(p.get("image_url")) or "![" in p.get("english", "")
        ext = (p.get("extracted_text") or "").strip()
        if not is_img:
            return p.get("english", "").strip()
        if is_target:
            if is_vision:
                ocr_part = f"\n[图片参考识别文字]:\n{ext}" if ext else ""
                return f"(已作为视觉图像输入模型){ocr_part}"
            else:
                return f"[图片识别文字]:\n{ext}" if ext else "[图片材料：未提取有效文本]"
        else:
            if ext:
                return f"(图片识别文字):\n{ext}"
            return "[图件/插图材料]"

    target_english = format_para_chat_text(target_p, is_target=True)

    # Preceding readable text paragraphs (chronological order)
    prev_candidates = [
        format_para_chat_text(p, is_target=False)
        for p in paragraphs[:target_idx]
        if p.get("english", "").strip()
    ]
    prev_texts = prev_candidates[-prev_count:] if prev_count > 0 else []

    # Subsequent readable text paragraphs
    next_candidates = [
        format_para_chat_text(p, is_target=False)
        for p in paragraphs[target_idx + 1:]
        if p.get("english", "").strip()
    ]
    next_texts = next_candidates[:next_count] if next_count > 0 else []

    # Image payload for vision models
    target_b64_img = None
    if is_target_img and is_vision:
        img_url = target_p.get("image_url", "")
        if not img_url and "![" in target_p.get("english", ""):
            m = re.search(r'\((/api/study/documents/[^/]+/images/[^)]+)\)', target_p.get("english", ""))
            if m:
                img_url = m.group(1)
        if img_url:
            img_filename = os.path.basename(img_url)
            img_path = os.path.join(doc_dir, "images", img_filename)
            if os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as f_img:
                        target_b64_img = base64.b64encode(f_img.read()).decode("utf-8")
                except Exception as e:
                    logger.warning(f"Failed to read image for vision chat: {e}")

    async for chunk in stream_paragraph_chat(
        target_english=target_english,
        prev_texts=prev_texts,
        next_texts=next_texts,
        settings=settings,
        user_message=user_message,
        history=history,
        provider_override=provider_override,
        model_override=model_override,
        image_base64=target_b64_img
    ):
        yield chunk

chat_with_paragraph_wrapper = chat_with_paragraph


