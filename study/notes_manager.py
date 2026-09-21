import os
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("study-notes-manager")

def get_chapter_json_path(doc_id: str, chapter_id: str) -> str:
    from study.service import get_doc_dir
    return os.path.join(get_doc_dir(doc_id), "chapters", f"{chapter_id}.json")

def load_chapter_data(doc_id: str, chapter_id: str) -> Dict[str, Any]:
    ch_path = get_chapter_json_path(doc_id, chapter_id)
    if not os.path.exists(ch_path):
        raise ValueError(f"Chapter {chapter_id} not found in document {doc_id}")
    with open(ch_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_chapter_data(doc_id: str, chapter: Dict[str, Any], language: str = "en"):
    from study.service import write_chapter_files, load_doc_meta, assemble_full_document_markdown
    write_chapter_files(doc_id, chapter, language)
    meta = load_doc_meta(doc_id)
    if meta:
        assemble_full_document_markdown(doc_id)

# ==========================================================
# Paragraph Notes (Multiple Notes per Paragraph)
# ==========================================================

def add_paragraph_note(doc_id: str, chapter_id: str, paragraph_id: str, content: str) -> Dict[str, Any]:
    """
    Appends a new note to the paragraph's 'notes' list.
    """
    content = content.strip()
    if not content:
        raise ValueError("Note content cannot be empty")
        
    ch_data = load_chapter_data(doc_id, chapter_id)
    target_p = None
    for p in ch_data.get("paragraphs", []):
        if p["id"] == paragraph_id:
            target_p = p
            break
            
    if not target_p:
        raise ValueError(f"Paragraph {paragraph_id} not found")
        
    if "notes" not in target_p or not isinstance(target_p["notes"], list):
        target_p["notes"] = []
        
    note_obj = {
        "id": f"nt_{int(time.time())}_{uuid.uuid4().hex[:6]}",
        "content": content,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    target_p["notes"].append(note_obj)
    save_chapter_data(doc_id, ch_data)
    return note_obj

def update_paragraph_note(doc_id: str, chapter_id: str, paragraph_id: str, note_id: str, new_content: str) -> Dict[str, Any]:
    """
    Updates the content of an existing paragraph note.
    """
    new_content = new_content.strip()
    if not new_content:
        raise ValueError("Note content cannot be empty")
        
    ch_data = load_chapter_data(doc_id, chapter_id)
    for p in ch_data.get("paragraphs", []):
        if p["id"] == paragraph_id:
            for note in p.get("notes", []):
                if note["id"] == note_id:
                    note["content"] = new_content
                    note["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    save_chapter_data(doc_id, ch_data)
                    return note
            raise ValueError(f"Note {note_id} not found on paragraph {paragraph_id}")
            
    raise ValueError(f"Paragraph {paragraph_id} not found")

def delete_paragraph_note(doc_id: str, chapter_id: str, paragraph_id: str, note_id: str) -> bool:
    """
    Removes a note from a paragraph.
    """
    ch_data = load_chapter_data(doc_id, chapter_id)
    for p in ch_data.get("paragraphs", []):
        if p["id"] == paragraph_id:
            notes = p.get("notes", [])
            init_len = len(notes)
            p["notes"] = [n for n in notes if n.get("id") != note_id]
            if len(p["notes"]) < init_len:
                save_chapter_data(doc_id, ch_data)
                return True
            return False
            
    raise ValueError(f"Paragraph {paragraph_id} not found")

# ==========================================================
# Chapter Notes (Multiple Notes for Header & Footer)
# ==========================================================

def add_chapter_note(doc_id: str, chapter_id: str, position: str, content: str) -> Dict[str, Any]:
    """
    Adds a note to the chapter's 'header_notes' or 'footer_notes' list.
    """
    content = content.strip()
    if not content:
        raise ValueError("Summary content cannot be empty")
        
    pos_key = "header_notes" if position == "header" else "footer_notes"
    ch_data = load_chapter_data(doc_id, chapter_id)
    
    if pos_key not in ch_data or not isinstance(ch_data[pos_key], list):
        ch_data[pos_key] = []
        
    prefix = "hn" if position == "header" else "fn"
    note_obj = {
        "id": f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}",
        "position": position,
        "content": content,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    ch_data[pos_key].append(note_obj)
    save_chapter_data(doc_id, ch_data)
    return note_obj

def update_chapter_note(doc_id: str, chapter_id: str, position: str, note_id: str, new_content: str) -> Dict[str, Any]:
    """
    Updates an existing chapter note (header or footer).
    """
    new_content = new_content.strip()
    if not new_content:
        raise ValueError("Content cannot be empty")
        
    pos_key = "header_notes" if position == "header" else "footer_notes"
    ch_data = load_chapter_data(doc_id, chapter_id)
    
    for note in ch_data.get(pos_key, []):
        if note["id"] == note_id:
            note["content"] = new_content
            note["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_chapter_data(doc_id, ch_data)
            return note
            
    raise ValueError(f"Chapter note {note_id} not found in {position}")

def delete_chapter_note(doc_id: str, chapter_id: str, position: str, note_id: str) -> bool:
    """
    Removes a chapter note from header or footer.
    """
    pos_key = "header_notes" if position == "header" else "footer_notes"
    ch_data = load_chapter_data(doc_id, chapter_id)
    notes = ch_data.get(pos_key, [])
    init_len = len(notes)
    ch_data[pos_key] = [n for n in notes if n.get("id") != note_id]
    
    if len(ch_data[pos_key]) < init_len:
        save_chapter_data(doc_id, ch_data)
        return True
    return False
