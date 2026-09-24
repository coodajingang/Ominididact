import os
import json
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

logger = logging.getLogger("study-chat-manager")

def get_chats_dir(doc_dir: str) -> str:
    chats_dir = os.path.join(doc_dir, "chats")
    os.makedirs(chats_dir, exist_ok=True)
    return chats_dir

def get_chat_file_path(doc_dir: str, chat_type: str, chapter_id: str = "", paragraph_id: Optional[str] = None) -> str:
    chats_dir = get_chats_dir(doc_dir)
    if chat_type == "document":
        return os.path.join(chats_dir, "document_global.json")
    elif chat_type == "chapter":
        return os.path.join(chats_dir, f"chapter_{chapter_id}.json")
    else:
        p_id = paragraph_id or "general"
        return os.path.join(chats_dir, f"para_{chapter_id}_{p_id}.json")

def load_chat_history(doc_dir: str, chat_type: str, chapter_id: str, paragraph_id: Optional[str] = None) -> List[Dict[str, Any]]:
    path = get_chat_file_path(doc_dir, chat_type, chapter_id, paragraph_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("messages", [])
    except Exception as e:
        logger.warning(f"Failed to read chat history from {path}: {e}")
        return []

def save_chat_history(doc_dir: str, chat_type: str, chapter_id: str, messages: List[Dict[str, Any]], paragraph_id: Optional[str] = None):
    path = get_chat_file_path(doc_dir, chat_type, chapter_id, paragraph_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "chat_type": chat_type,
                "chapter_id": chapter_id,
                "paragraph_id": paragraph_id,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messages": messages
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save chat history to {path}: {e}")

def clear_chat_history(doc_dir: str, chat_type: str, chapter_id: str, paragraph_id: Optional[str] = None) -> bool:
    path = get_chat_file_path(doc_dir, chat_type, chapter_id, paragraph_id)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete chat history file {path}: {e}")
            return False
    return True

def append_chat_message(
    doc_dir: str,
    chat_type: str,
    chapter_id: str,
    paragraph_id: Optional[str] = None,
    role: str = "user",
    content: str = ""
):
    history = load_chat_history(doc_dir, chat_type, chapter_id, paragraph_id)
    history.append({
        "role": role,
        "content": content,
        "timestamp": time.time(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    save_chat_history(doc_dir, chat_type, chapter_id, messages=history, paragraph_id=paragraph_id)

async def stream_and_persist(
    doc_dir: str,
    chat_type: str,
    chapter_id: str,
    paragraph_id: Optional[str],
    user_message: str,
    stream_generator: AsyncGenerator[str, None]
) -> AsyncGenerator[str, None]:
    """
    Wraps an upstream SSE stream generator.
    1. Records the user message to persistent storage.
    2. Yields chunks to client SSE in real-time.
    3. Concurrently collects the full assistant response.
    4. Crucially: If client disconnects (GeneratorExit / CancelledError),
       continues consuming upstream in background until completion, then saves the full assistant response to storage!
    """
    # 1. Record user message immediately
    append_chat_message(
        doc_dir=doc_dir,
        chat_type=chat_type,
        chapter_id=chapter_id,
        paragraph_id=paragraph_id,
        role="user",
        content=user_message
    )

    full_answer_chunks: List[str] = []
    
    async def drain_in_background(gen, chunks: List[str]):
        """Consumes remaining generator chunks if client disconnects early."""
        try:
            async for chunk in gen:
                # Extract text delta for persistence
                lines = chunk.split("\n")
                for line in lines:
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        if raw and raw != "[DONE]":
                            try:
                                parsed = json.loads(raw)
                                delta = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
                                if not delta:
                                    delta = parsed.get("choices", [{}])[0].get("text", "")
                                if delta:
                                    chunks.append(delta)
                            except Exception:
                                pass
        except Exception as e:
            logger.warning(f"Background drain exception: {e}")
        finally:
            full_text = "".join(chunks).strip()
            if full_text:
                append_chat_message(
                    doc_dir=doc_dir,
                    chat_type=chat_type,
                    chapter_id=chapter_id,
                    paragraph_id=paragraph_id,
                    role="assistant",
                    content=full_text
                )
                logger.info(f"Chat message saved in background for {chat_type} {chapter_id} ({len(full_text)} chars)")

    try:
        async for chunk in stream_generator:
            # Parse text delta to accumulate assistant response
            lines = chunk.split("\n")
            for line in lines:
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            parsed = json.loads(raw)
                            delta = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
                            if not delta:
                                delta = parsed.get("choices", [{}])[0].get("text", "")
                            if delta:
                                full_answer_chunks.append(delta)
                        except Exception:
                            pass
            yield chunk

        # Normal completion while client is still connected
        full_text = "".join(full_answer_chunks).strip()
        if full_text:
            append_chat_message(
                doc_dir=doc_dir,
                chat_type=chat_type,
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                role="assistant",
                content=full_text
            )
    except (GeneratorExit, asyncio.CancelledError):
        logger.info(f"Client disconnected during {chat_type} chat. Spawning background drain task to finish collecting LLM answer.")
        asyncio.create_task(drain_in_background(stream_generator, full_answer_chunks))
        raise
    except Exception as e:
        logger.exception(f"Error during stream_and_persist: {e}")
        full_text = "".join(full_answer_chunks).strip()
        if full_text:
            append_chat_message(
                doc_dir=doc_dir,
                chat_type=chat_type,
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                role="assistant",
                content=full_text
            )
        raise
