import os
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("study-flashcard-manager")

def get_flashcards_path(doc_id: str) -> str:
    from study.service import get_doc_dir
    return os.path.join(get_doc_dir(doc_id), "flashcards.json")

def load_doc_flashcards(doc_id: str) -> Dict[str, Any]:
    path = get_flashcards_path(doc_id)
    if not os.path.exists(path):
        default_data = {
            "doc_id": doc_id,
            "settings": {
                "theme": "inherit",
                "fontSize": "medium",
                "clozeStyle": "badge",
                "flipAnimation": "flip3d"
            },
            "cards": []
        }
        return default_data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "cards" not in data or not isinstance(data["cards"], list):
                data["cards"] = []
            if "settings" not in data or not isinstance(data["settings"], dict):
                data["settings"] = {
                    "theme": "inherit",
                    "fontSize": "medium",
                    "clozeStyle": "badge",
                    "flipAnimation": "flip3d"
                }
            return data
    except Exception as e:
        logger.error(f"Failed to read flashcards for doc {doc_id}: {e}")
        return {"doc_id": doc_id, "settings": {}, "cards": []}

def save_doc_flashcards(doc_id: str, data: Dict[str, Any]):
    path = get_flashcards_path(doc_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save flashcards for doc {doc_id}: {e}")
        raise

def list_flashcards(
    doc_id: str,
    filter_type: Optional[str] = None,
    chapter_id: Optional[str] = None,
    is_error: bool = False,
    keyword: Optional[str] = None
) -> List[Dict[str, Any]]:
    data = load_doc_flashcards(doc_id)
    cards = data.get("cards", [])
    
    filtered = []
    kw = keyword.lower().strip() if keyword else None
    
    for c in cards:
        if filter_type and filter_type != "all" and c.get("type") != filter_type:
            continue
        if chapter_id and chapter_id != "all" and c.get("chapter_id") != chapter_id:
            continue
        if is_error:
            stats = c.get("stats", {})
            if stats.get("lapses", 0) <= 0 and stats.get("state") != "lapsed":
                continue
        if kw:
            front = str(c.get("front", "")).lower()
            back = str(c.get("back", "")).lower()
            tags = " ".join([str(t).lower() for t in c.get("tags", [])])
            if kw not in front and kw not in back and kw not in tags:
                continue
        filtered.append(c)
        
    return filtered

def get_flashcard(doc_id: str, card_id: str) -> Optional[Dict[str, Any]]:
    data = load_doc_flashcards(doc_id)
    for c in data.get("cards", []):
        if c.get("id") == card_id:
            return c
    return None

def create_flashcard(doc_id: str, card_dict: Dict[str, Any]) -> Dict[str, Any]:
    data = load_doc_flashcards(doc_id)
    
    front = card_dict.get("front", "").strip()
    back = card_dict.get("back", "").strip()
    if not front:
        raise ValueError("闪卡正面内容不能为空")
        
    card_type = card_dict.get("type", "qa")
    if card_type not in ("qa", "cloze"):
        card_type = "qa"
        
    tags = card_dict.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        
    new_id = card_dict.get("id") or f"fc_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    new_card = {
        "id": new_id,
        "chapter_id": card_dict.get("chapter_id", ""),
        "paragraph_id": card_dict.get("paragraph_id", ""),
        "type": card_type,
        "front": front,
        "back": back,
        "tags": tags,
        "stats": {
            "reps": 0,
            "lapses": 0,
            "state": "new",
            "interval_days": 0,
            "ease_factor": 2.5,
            "last_reviewed": None,
            "next_review": None
        },
        "created_at": now_str,
        "updated_at": now_str
    }
    
    data["cards"].append(new_card)
    save_doc_flashcards(doc_id, data)
    return new_card

def batch_create_flashcards(doc_id: str, cards_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not cards_list:
        return []
    data = load_doc_flashcards(doc_id)
    created = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    for item in cards_list:
        front = item.get("front", "").strip()
        if not front:
            continue
        card_type = item.get("type", "qa")
        if card_type not in ("qa", "cloze"):
            card_type = "qa"
            
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
            
        card_obj = {
            "id": item.get("id") or f"fc_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            "chapter_id": item.get("chapter_id", ""),
            "paragraph_id": item.get("paragraph_id", ""),
            "type": card_type,
            "front": front,
            "back": item.get("back", "").strip(),
            "tags": tags,
            "stats": {
                "reps": 0,
                "lapses": 0,
                "state": "new",
                "interval_days": 0,
                "ease_factor": 2.5,
                "last_reviewed": None,
                "next_review": None
            },
            "created_at": now_str,
            "updated_at": now_str
        }
        data["cards"].append(card_obj)
        created.append(card_obj)
        
    save_doc_flashcards(doc_id, data)
    return created

def update_flashcard(doc_id: str, card_id: str, card_dict: Dict[str, Any]) -> Dict[str, Any]:
    data = load_doc_flashcards(doc_id)
    target = None
    for c in data.get("cards", []):
        if c.get("id") == card_id:
            target = c
            break
            
    if not target:
        raise ValueError(f"Flashcard {card_id} not found")
        
    if "front" in card_dict:
        front = card_dict["front"].strip()
        if not front:
            raise ValueError("闪卡正面内容不能为空")
        target["front"] = front
        
    if "back" in card_dict:
        target["back"] = card_dict["back"].strip()
        
    if "type" in card_dict and card_dict["type"] in ("qa", "cloze"):
        target["type"] = card_dict["type"]
        
    if "chapter_id" in card_dict:
        target["chapter_id"] = card_dict["chapter_id"]
        
    if "tags" in card_dict:
        tags = card_dict["tags"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        target["tags"] = tags
        
    target["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_doc_flashcards(doc_id, data)
    return target

def delete_flashcard(doc_id: str, card_id: str) -> bool:
    data = load_doc_flashcards(doc_id)
    initial_len = len(data.get("cards", []))
    data["cards"] = [c for c in data.get("cards", []) if c.get("id") != card_id]
    if len(data["cards"]) < initial_len:
        save_doc_flashcards(doc_id, data)
        return True
    return False

def batch_delete_flashcards(doc_id: str, card_ids: List[str]) -> int:
    data = load_doc_flashcards(doc_id)
    card_id_set = set(card_ids)
    initial_len = len(data.get("cards", []))
    data["cards"] = [c for c in data.get("cards", []) if c.get("id") not in card_id_set]
    deleted_count = initial_len - len(data["cards"])
    if deleted_count > 0:
        save_doc_flashcards(doc_id, data)
    return deleted_count

def delete_flashcards_by_chapter(doc_id: str, chapter_id: str) -> int:
    """
    Deletes all flashcards associated with a specific chapter.
    """
    data = load_doc_flashcards(doc_id)
    initial_len = len(data.get("cards", []))
    data["cards"] = [
        c for c in data.get("cards", [])
        if str(c.get("chapter_id", "")).strip() != str(chapter_id).strip()
    ]
    deleted_count = initial_len - len(data["cards"])
    if deleted_count > 0:
        save_doc_flashcards(doc_id, data)
    return deleted_count

def delete_flashcards_by_paragraph(doc_id: str, paragraph_id: str) -> int:
    """
    Deletes all flashcards associated with a specific paragraph.
    """
    data = load_doc_flashcards(doc_id)
    initial_len = len(data.get("cards", []))
    data["cards"] = [
        c for c in data.get("cards", [])
        if str(c.get("paragraph_id", "")).strip() != str(paragraph_id).strip()
    ]
    deleted_count = initial_len - len(data["cards"])
    if deleted_count > 0:
        save_doc_flashcards(doc_id, data)
    return deleted_count

def record_card_review(doc_id: str, card_id: str, rating: int) -> Dict[str, Any]:
    """
    Records review result using simplified SM-2 spaced repetition:
    rating:
      1 = Again (忘记/又错了)
      2 = Hard (困难/模糊)
      3 = Good (良好/记得)
      4 = Easy (熟练/掌握)
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError("Rating must be an integer between 1 and 4")
        
    data = load_doc_flashcards(doc_id)
    target = None
    for c in data.get("cards", []):
        if c.get("id") == card_id:
            target = c
            break
            
    if not target:
        raise ValueError(f"Flashcard {card_id} not found")
        
    stats = target.setdefault("stats", {})
    reps = stats.get("reps", 0)
    lapses = stats.get("lapses", 0)
    ease = stats.get("ease_factor", 2.5)
    interval = stats.get("interval_days", 0)
    is_mistake = stats.get("is_mistake", lapses > 0)
    mistake_streak = stats.get("mistake_streak", 0)
    graduated_from_mistakes = False
    now_ts = int(time.time())
    
    if rating == 1:
        # Lapse / Forgot: Enter mistake pool, reset streak
        lapses += 1
        reps = 0
        interval = 0
        state = "learning"
        ease = max(1.3, ease - 0.2)
        next_review_ts = now_ts + 600  # 10 minutes later
        is_mistake = True
        mistake_streak = 0
    elif rating == 2:
        # Hard: Keep in mistake pool, reset streak
        reps += 1
        if interval == 0:
            interval = 1
        else:
            interval = max(1, int(interval * 1.2))
        state = "learning"
        ease = max(1.3, ease - 0.15)
        next_review_ts = now_ts + interval * 86400
        mistake_streak = 0
    elif rating == 3:
        # Good: If in mistake pool, consecutive streak + 1; 2 consecutive Goods graduate card
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 3
        else:
            interval = max(1, int(interval * ease))
        state = "review"
        next_review_ts = now_ts + interval * 86400
        if is_mistake:
            mistake_streak += 1
            if mistake_streak >= 2:
                is_mistake = False
                mistake_streak = 0
                graduated_from_mistakes = True
    else:
        # Easy (Rating 4): Mastered, directly graduate from mistake pool
        reps += 1
        if reps == 1:
            interval = 4
        elif reps == 2:
            interval = 7
        else:
            interval = max(1, int(interval * ease * 1.3))
        state = "mastered"
        ease = min(3.0, ease + 0.15)
        next_review_ts = now_ts + interval * 86400
        if is_mistake:
            is_mistake = False
            mistake_streak = 0
            graduated_from_mistakes = True

    stats["reps"] = reps
    stats["lapses"] = lapses
    stats["state"] = state
    stats["ease_factor"] = round(ease, 2)
    stats["interval_days"] = interval
    stats["last_reviewed"] = time.strftime("%Y-%m-%d %H:%M:%S")
    stats["next_review"] = next_review_ts
    stats["is_mistake"] = is_mistake
    stats["mistake_streak"] = mistake_streak
    
    target["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_doc_flashcards(doc_id, data)
    target["graduated_from_mistakes"] = graduated_from_mistakes
    return target

def clear_card_errors(doc_id: str, card_id: Optional[str] = None) -> int:
    """
    Clears active mistake flag and resets error count for a specific card or all cards.
    """
    data = load_doc_flashcards(doc_id)
    cleared = 0
    for c in data.get("cards", []):
        if card_id is None or c.get("id") == card_id:
            stats = c.setdefault("stats", {})
            if stats.get("is_mistake") or stats.get("lapses", 0) > 0:
                stats["is_mistake"] = False
                stats["lapses"] = 0
                stats["mistake_streak"] = 0
                cleared += 1
    if cleared > 0:
        save_doc_flashcards(doc_id, data)
    return cleared

def get_flashcard_statistics(doc_id: str) -> Dict[str, Any]:
    data = load_doc_flashcards(doc_id)
    cards = data.get("cards", [])
    now_ts = int(time.time())
    
    total = len(cards)
    new_count = 0
    learning_count = 0
    review_count = 0
    mastered_count = 0
    error_count = 0
    due_count = 0
    chapter_dist: Dict[str, Dict[str, int]] = {}
    
    for c in cards:
        stats = c.get("stats", {})
        state = stats.get("state", "new")
        if state == "new":
            new_count += 1
        elif state == "learning":
            learning_count += 1
        elif state == "review":
            review_count += 1
        elif state == "mastered":
            mastered_count += 1
            
        is_card_mistake = stats.get("is_mistake", stats.get("lapses", 0) > 0)
        if is_card_mistake:
            error_count += 1
            
        next_review = stats.get("next_review")
        if next_review and next_review <= now_ts:
            due_count += 1
            
        ch_id = c.get("chapter_id") or "未分类"
        if ch_id not in chapter_dist:
            chapter_dist[ch_id] = {"total": 0, "mastered": 0, "errors": 0}
        chapter_dist[ch_id]["total"] += 1
        if state == "mastered":
            chapter_dist[ch_id]["mastered"] += 1
        if is_card_mistake:
            chapter_dist[ch_id]["errors"] += 1

    mastery_rate = round((mastered_count / total * 100), 1) if total > 0 else 0.0
    
    return {
        "total_cards": total,
        "new_count": new_count,
        "learning_count": learning_count,
        "review_count": review_count,
        "mastered_count": mastered_count,
        "error_count": error_count,
        "due_count": due_count,
        "mastery_rate": mastery_rate,
        "chapter_distribution": chapter_dist,
        "settings": data.get("settings", {})
    }

def update_flashcard_settings(doc_id: str, new_settings: Dict[str, Any]) -> Dict[str, Any]:
    data = load_doc_flashcards(doc_id)
    current = data.setdefault("settings", {})
    current.update(new_settings)
    save_doc_flashcards(doc_id, data)
    return current
