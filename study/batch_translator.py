import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("study-batch-translator")

# Tracks running background tasks and stop events
ACTIVE_CHAPTER_TRANSLATIONS: Dict[str, asyncio.Task] = {}
CHAPTER_STOP_EVENTS: Dict[str, asyncio.Event] = {}
ACTIVE_DOC_TRANSLATIONS: Dict[str, asyncio.Task] = {}
DOC_STOP_EVENTS: Dict[str, asyncio.Event] = {}

def get_task_key(doc_id: str, chapter_id: str) -> str:
    return f"{doc_id}_{chapter_id}"

def get_chapter_json_path(doc_id: str, chapter_id: str) -> str:
    from study.service import get_doc_dir
    return os.path.join(get_doc_dir(doc_id), "chapters", f"{chapter_id}.json")

def get_chapter_translation_status(doc_id: str, chapter_id: str) -> Dict[str, Any]:
    """
    Returns current translation status for a chapter.
    """
    task_key = get_task_key(doc_id, chapter_id)
    ch_path = get_chapter_json_path(doc_id, chapter_id)
    if not os.path.exists(ch_path):
        return {"status": "idle", "completed": 0, "total": 0, "percent": 0, "is_running": False}
        
    try:
        with open(ch_path, "r", encoding="utf-8") as f:
            ch_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read chapter {chapter_id} JSON: {e}")
        return {"status": "error", "completed": 0, "total": 0, "percent": 0, "is_running": False}

    paragraphs = [
        p for p in ch_data.get("paragraphs", [])
        if p.get("type") not in ("image", "code") and not p.get("no_translate")
    ]
    total = len(paragraphs)
    completed = sum(
        1 for p in paragraphs
        if p.get("status") == "completed" and not p.get("chinese", "").startswith("[翻译调用异常")
    )
    percent = int(completed / max(total, 1) * 100) if total > 0 else 100
    
    is_running = (
        (task_key in ACTIVE_CHAPTER_TRANSLATIONS and not ACTIVE_CHAPTER_TRANSLATIONS[task_key].done())
        or (task_key in CHAPTER_STOP_EVENTS)
    )
    
    saved_status = ch_data.get("translation_status", {})
    curr_status = "translating" if is_running else (
        "completed" if completed >= total and total > 0 else saved_status.get("status", "idle")
    )

    untranslated = max(0, total - completed)

    return {
        "status": curr_status,
        "completed": completed,
        "total": total,
        "untranslated": untranslated,
        "percent": percent,
        "is_running": is_running
    }

async def start_chapter_translation(doc_id: str, chapter_id: str) -> Dict[str, Any]:
    """
    Starts an asynchronous background translation task for the specified chapter.
    Automatically retries paragraphs that failed or are pending.
    """
    task_key = get_task_key(doc_id, chapter_id)
    
    # Check if already running
    if task_key in ACTIVE_CHAPTER_TRANSLATIONS and not ACTIVE_CHAPTER_TRANSLATIONS[task_key].done():
        status = get_chapter_translation_status(doc_id, chapter_id)
        return {"code": 200, "message": "该章节翻译任务正在后台运行中", "data": status}
        
    stop_event = asyncio.Event()
    CHAPTER_STOP_EVENTS[task_key] = stop_event
    
    # Spawn background task
    task = asyncio.create_task(_run_chapter_batch_translation(doc_id, chapter_id, stop_event))
    ACTIVE_CHAPTER_TRANSLATIONS[task_key] = task
    
    status = get_chapter_translation_status(doc_id, chapter_id)
    status["status"] = "translating"
    status["is_running"] = True
    return {"code": 200, "message": "章节批量翻译已启动", "data": status}

async def stop_chapter_translation(doc_id: str, chapter_id: str) -> Dict[str, Any]:
    """
    Signals the running chapter translation task to pause/stop gracefully.
    """
    task_key = get_task_key(doc_id, chapter_id)
    if task_key in CHAPTER_STOP_EVENTS:
        CHAPTER_STOP_EVENTS[task_key].set()
        
    status = get_chapter_translation_status(doc_id, chapter_id)
    status["status"] = "paused"
    status["is_running"] = False
    return {"code": 200, "message": "已发送停止翻译信号", "data": status}

def get_document_translation_status(doc_id: str) -> Dict[str, Any]:
    """
    Returns current whole-document translation status aggregating all chapters.
    """
    from study.service import load_doc_meta
    meta = load_doc_meta(doc_id)
    if not meta:
        return {"status": "idle", "completed": 0, "total": 0, "percent": 0, "is_running": False}

    chapters = meta.get("chapters", [])
    total_paras = 0
    completed_paras = 0
    active_chapter_title = ""
    active_chapter_index = 0

    for idx, ch in enumerate(chapters):
        ch_id = ch.get("chapter_id")
        ch_status = get_chapter_translation_status(doc_id, ch_id)
        total_paras += ch_status.get("total", 0)
        completed_paras += ch_status.get("completed", 0)
        if ch_status.get("is_running") and not active_chapter_title:
            active_chapter_title = ch.get("title", f"第 {idx + 1} 章")
            active_chapter_index = idx + 1

    percent = int(completed_paras / max(total_paras, 1) * 100) if total_paras > 0 else 100
    is_doc_task_running = doc_id in ACTIVE_DOC_TRANSLATIONS and not ACTIVE_DOC_TRANSLATIONS[doc_id].done()
    is_any_chapter_running = any(
        get_task_key(doc_id, ch.get("chapter_id")) in ACTIVE_CHAPTER_TRANSLATIONS
        and not ACTIVE_CHAPTER_TRANSLATIONS[get_task_key(doc_id, ch.get("chapter_id"))].done()
        for ch in chapters
    )
    is_running = is_doc_task_running or is_any_chapter_running

    curr_status = "translating" if is_running else (
        "completed" if completed_paras >= total_paras and total_paras > 0 else "idle"
    )

    return {
        "status": curr_status,
        "completed": completed_paras,
        "total": total_paras,
        "untranslated": max(0, total_paras - completed_paras),
        "percent": percent,
        "is_running": is_running,
        "is_doc_level_running": is_doc_task_running,
        "active_chapter_title": active_chapter_title,
        "active_chapter_index": active_chapter_index,
        "total_chapters": len(chapters)
    }

async def start_document_translation(doc_id: str) -> Dict[str, Any]:
    """
    Starts an asynchronous background translation task for all chapters in the document.
    """
    if doc_id in ACTIVE_DOC_TRANSLATIONS and not ACTIVE_DOC_TRANSLATIONS[doc_id].done():
        status = get_document_translation_status(doc_id)
        return {"code": 200, "message": "本文档批量翻译任务正在后台运行中", "data": status}

    stop_event = asyncio.Event()
    DOC_STOP_EVENTS[doc_id] = stop_event

    task = asyncio.create_task(_run_document_batch_translation(doc_id, stop_event))
    ACTIVE_DOC_TRANSLATIONS[doc_id] = task

    status = get_document_translation_status(doc_id)
    status["status"] = "translating"
    status["is_running"] = True
    return {"code": 200, "message": "本文档全篇批量翻译已启动", "data": status}

async def stop_document_translation(doc_id: str) -> Dict[str, Any]:
    """
    Signals the running document translation task and any sub-chapter tasks to stop.
    """
    if doc_id in DOC_STOP_EVENTS:
        DOC_STOP_EVENTS[doc_id].set()

    from study.service import load_doc_meta
    meta = load_doc_meta(doc_id)
    if meta:
        for ch in meta.get("chapters", []):
            ch_id = ch.get("chapter_id")
            task_key = get_task_key(doc_id, ch_id)
            if task_key in CHAPTER_STOP_EVENTS:
                CHAPTER_STOP_EVENTS[task_key].set()

    status = get_document_translation_status(doc_id)
    status["status"] = "paused"
    status["is_running"] = False
    return {"code": 200, "message": "已发送停止全篇翻译信号", "data": status}

def update_chapter_translation_status(doc_id: str, chapter_id: str, status: str, error: Optional[str] = None):
    """
    Safely updates chapter's translation_status in chapter JSON on disk
    without overwriting paragraphs with stale in-memory data.
    """
    ch_path = get_chapter_json_path(doc_id, chapter_id)
    if os.path.exists(ch_path):
        try:
            with open(ch_path, "r", encoding="utf-8") as f:
                ch_data = json.load(f)
            status_obj = {"status": status}
            if error:
                status_obj["error"] = error
            ch_data["translation_status"] = status_obj
            from study.service import write_chapter_files, load_doc_meta
            meta = load_doc_meta(doc_id)
            lang = meta.get("language", "en") if meta else "en"
            write_chapter_files(doc_id, ch_data, language=lang)
        except Exception as e:
            logger.error(f"Failed to update chapter translation status: {e}")

async def _run_chapter_batch_translation(doc_id: str, chapter_id: str, stop_event: asyncio.Event):
    """
    Worker task: iterates over pending or failed paragraphs and translates them.
    Protects against crashes, updates progress in real-time, and preserves all
    already-translated paragraphs when interrupted.
    """
    task_key = get_task_key(doc_id, chapter_id)
    from study.service import translate_single_paragraph, write_chapter_files, load_doc_meta
    
    logger.info(f"Starting batch translation worker for {task_key}")
    ch_path = get_chapter_json_path(doc_id, chapter_id)
    
    try:
        if not os.path.exists(ch_path):
            logger.error(f"Chapter JSON not found: {ch_path}")
            return

        with open(ch_path, "r", encoding="utf-8") as f:
            ch_data = json.load(f)
            
        paragraphs = ch_data.get("paragraphs", [])
        
        # Safely mark initial translating status on disk
        update_chapter_translation_status(doc_id, chapter_id, "translating")
        
        for p in paragraphs:
            if stop_event.is_set():
                logger.info(f"Chapter translation for {task_key} stopped by user before paragraph {p.get('id')}.")
                update_chapter_translation_status(doc_id, chapter_id, "paused")
                return

            is_translatable = p.get("type") not in ("image", "code") and not p.get("no_translate")
            
            # Check latest paragraph status on disk to avoid re-translating completed paragraphs
            try:
                with open(ch_path, "r", encoding="utf-8") as f_latest:
                    latest_ch = json.load(f_latest)
                latest_p = next((x for x in latest_ch.get("paragraphs", []) if x["id"] == p["id"]), p)
            except Exception:
                latest_p = p

            needs_translation = (
                latest_p.get("status") != "completed"
                or latest_p.get("chinese", "").startswith("[翻译调用异常")
            )
            
            if is_translatable and needs_translation:
                try:
                    await translate_single_paragraph(doc_id, chapter_id, p["id"])
                except Exception as ex:
                    logger.error(f"Error translating paragraph {p['id']} in {chapter_id}: {ex}")
                    try:
                        with open(ch_path, "r", encoding="utf-8") as f_err:
                            err_ch = json.load(f_err)
                        for ep in err_ch.get("paragraphs", []):
                            if ep["id"] == p["id"]:
                                ep["chinese"] = f"[翻译调用异常: {str(ex)}]"
                                ep["status"] = "error"
                                break
                        meta = load_doc_meta(doc_id)
                        write_chapter_files(doc_id, err_ch, language=meta.get("language", "en") if meta else "en")
                    except Exception:
                        pass

            # Re-check stop event immediately after paragraph completes
            if stop_event.is_set():
                logger.info(f"Chapter translation for {task_key} stopped by user after paragraph {p.get('id')}.")
                update_chapter_translation_status(doc_id, chapter_id, "paused")
                return

        # Finished all paragraphs successfully
        update_chapter_translation_status(doc_id, chapter_id, "completed")
        logger.info(f"Chapter translation for {task_key} fully completed.")
        
    except Exception as e:
        logger.exception(f"Unexpected error in chapter translation worker for {task_key}: {e}")
        update_chapter_translation_status(doc_id, chapter_id, "error", error=str(e))
    finally:
        ACTIVE_CHAPTER_TRANSLATIONS.pop(task_key, None)
        CHAPTER_STOP_EVENTS.pop(task_key, None)

async def _run_document_batch_translation(doc_id: str, stop_event: asyncio.Event):
    """
    Worker task: iterates over all chapters of the document and translates untranslated paragraphs.
    """
    from study.service import load_doc_meta
    meta = load_doc_meta(doc_id)
    if not meta:
        return
    chapters = meta.get("chapters", [])
    logger.info(f"Starting document batch translation for {doc_id} across {len(chapters)} chapters")
    try:
        for idx, ch in enumerate(chapters):
            if stop_event.is_set():
                logger.info(f"Document translation for {doc_id} stopped before chapter {ch.get('chapter_id')}")
                break
            ch_id = ch.get("chapter_id")
            if not ch_id:
                continue

            ch_status = get_chapter_translation_status(doc_id, ch_id)
            if ch_status.get("total", 0) > 0 and ch_status.get("completed", 0) >= ch_status.get("total", 0):
                continue

            task_key = get_task_key(doc_id, ch_id)
            ch_stop_event = asyncio.Event()
            CHAPTER_STOP_EVENTS[task_key] = ch_stop_event

            async def forward_stop():
                while not stop_event.is_set() and not ch_stop_event.is_set():
                    await asyncio.sleep(0.3)
                if stop_event.is_set():
                    ch_stop_event.set()

            fwd_task = asyncio.create_task(forward_stop())
            try:
                await _run_chapter_batch_translation(doc_id, ch_id, ch_stop_event)
            finally:
                fwd_task.cancel()
                CHAPTER_STOP_EVENTS.pop(task_key, None)

            if stop_event.is_set():
                logger.info(f"Document translation for {doc_id} stopped after chapter {ch_id}")
                break
        logger.info(f"Document translation for {doc_id} completed iteration.")
    except Exception as e:
        logger.exception(f"Unexpected error in document translation worker for {doc_id}: {e}")
    finally:
        ACTIVE_DOC_TRANSLATIONS.pop(doc_id, None)
        DOC_STOP_EVENTS.pop(doc_id, None)


