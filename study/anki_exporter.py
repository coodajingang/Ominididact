from __future__ import annotations
import os
import io
import time
import json
import uuid
import sqlite3
import zipfile
import hashlib
import re
from typing import List, Dict, Any, Optional

def sanitize_for_anki_cloze(text: str) -> str:
    """
    Converts Omnididact cloze syntax {{word}} to standard Anki cloze syntax {{c1::word}}, {{c2::word}}...
    If already formatted as {{c1::word}}, leaves it intact.
    """
    if not text:
        return ""
    if re.search(r"\{\{c\d+::", text):
        return text
    counter = 0
    def replacer(match):
        nonlocal counter
        counter += 1
        content = match.group(1)
        return f"{{{{c{counter}::{content}}}}}"
    return re.sub(r"\{\{([^{}]+?)\}\}", replacer, text)

def clean_anki_html(text: str) -> str:
    """Converts standard text/markdown linebreaks to HTML for Anki cards."""
    if not text:
        return ""
    # Basic HTML escaping for safe display while preserving formatting
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Convert double newlines to paragraphs and single newlines to <br>
    paragraphs = escaped.split("\n\n")
    html_paragraphs = ["<p>" + p.replace("\n", "<br>") + "</p>" for p in paragraphs if p.strip()]
    return "".join(html_paragraphs) if html_paragraphs else escaped.replace("\n", "<br>")

def generate_anki_guid() -> str:
    """Generates an Anki-compatible 10-character unique ID."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    h = hashlib.sha256(uuid.uuid4().bytes).digest()
    result = []
    for b in h[:10]:
        result.append(alphabet[b % len(alphabet)])
    return "".join(result)

def calculate_anki_field_checksum(field_str: str) -> int:
    """Calculates Anki 32-bit field checksum for the first field."""
    h = hashlib.sha1(field_str.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")

def export_flashcards_to_apkg_bytes(
    cards: List[Dict[str, Any]],
    deck_name: str = "Omnididact 研学闪卡",
    doc_title: Optional[str] = None
) -> bytes:
    """
    Exports a list of flashcard dicts into a standard .apkg ZIP archive binary bytes.
    Works natively across all platforms without external C/Rust dependencies.
    """
    now_ts = int(time.time())
    now_ms = int(time.time() * 1000)
    deck_id = int(now_ms % 10000000000) + 1
    model_id = int((now_ms + 1) % 10000000000) + 2

    # In-memory SQLite DB
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    # 1. Create Anki schema
    cursor.execute("""
        CREATE TABLE col (
            id integer primary key,
            crt integer not null,
            mod integer not null,
            scm integer not null,
            ver integer not null,
            dty integer not null,
            usn integer not null,
            ls integer not null,
            conf text not null,
            models text not null,
            decks text not null,
            dconf text not null,
            tags text not null
        );
    """)

    cursor.execute("""
        CREATE TABLE notes (
            id integer primary key,
            guid text not null,
            mid integer not null,
            mod integer not null,
            usn integer not null,
            tags text not null,
            flds text not null,
            sfld text not null,
            csum integer not null,
            flags integer not null,
            data text not null
        );
    """)

    cursor.execute("""
        CREATE TABLE cards (
            id integer primary key,
            nid integer not null,
            did integer not null,
            ord integer not null,
            mod integer not null,
            usn integer not null,
            type integer not null,
            queue integer not null,
            due integer not null,
            ivl integer not null,
            factor integer not null,
            reps integer not null,
            lapses integer not null,
            left integer not null,
            odue integer not null,
            odid integer not null,
            flags integer not null,
            data text not null
        );
    """)

    cursor.execute("""
        CREATE TABLE revlog (
            id integer primary key,
            cid integer not null,
            usn integer not null,
            ease integer not null,
            ivl integer not null,
            lastIvl integer not null,
            factor integer not null,
            time integer not null,
            type integer not null
        );
    """)

    cursor.execute("""
        CREATE TABLE graves (
            usn integer not null,
            oid integer not null,
            type integer not null
        );
    """)

    # 2. Build Models JSON
    card_model = {
        str(model_id): {
            "id": model_id,
            "name": "Omnididact Flashcard",
            "type": 0,
            "mod": now_ts,
            "usn": -1,
            "sortf": 0,
            "did": deck_id,
            "tmpls": [
                {
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": "<div class=\"card-front\">{{Front}}</div>",
                    "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\n<div class=\"card-back\">{{Back}}</div>\n{{#Notes}}<div class=\"card-notes\"><small>💡 研学笔记: {{Notes}}</small></div>{{/Notes}}\n{{#Source}}<div class=\"card-source\"><small>📑 原文定位: {{Source}}</small></div>{{/Source}}",
                    "bqfmt": "",
                    "bafmt": "",
                    "did": None,
                    "bfont": "",
                    "bsize": 0
                }
            ],
            "flds": [
                {"name": "Front", "ord": 0, "sticky": False, "rtl": False, "font": "Arial", "size": 20, "media": []},
                {"name": "Back", "ord": 1, "sticky": False, "rtl": False, "font": "Arial", "size": 18, "media": []},
                {"name": "Notes", "ord": 2, "sticky": False, "rtl": False, "font": "Arial", "size": 14, "media": []},
                {"name": "Source", "ord": 3, "sticky": False, "rtl": False, "font": "Arial", "size": 14, "media": []}
            ],
            "css": ".card { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 16px; text-align: left; color: #1e293b; background-color: #f8fafc; line-height: 1.6; padding: 18px; }\n.card-front { font-size: 19px; font-weight: 600; color: #0f172a; margin-bottom: 12px; }\n.card-back { font-size: 17px; color: #334155; margin-top: 12px; }\n.card-notes { margin-top: 16px; padding: 8px 12px; background: #f1f5f9; border-left: 3px solid #6366f1; border-radius: 4px; color: #475569; }\n.card-source { margin-top: 8px; color: #94a3b8; font-size: 12px; }\nhr#answer { border: 0; height: 1px; background: #e2e8f0; margin: 16px 0; }",
            "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amssymb,amsmath}\n\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
            "latexPost": "\\end{document}",
            "latexsvg": False,
            "req": [[0, "all", [0]]]
        }
    }

    # 3. Build Decks JSON
    clean_deck_name = deck_name.strip() if deck_name else "Omnididact 研学闪卡"
    decks_json = {
        "1": {
            "id": 1,
            "mod": now_ts,
            "name": "Default",
            "usn": 0,
            "lrnToday": [0, 0],
            "revToday": [0, 0],
            "newToday": [0, 0],
            "timeToday": [0, 0],
            "collapsed": True,
            "browserCollapsed": True,
            "desc": "",
            "dyn": 0,
            "conf": 1,
            "extendNew": 10,
            "extendRev": 50
        },
        str(deck_id): {
            "id": deck_id,
            "mod": now_ts,
            "name": clean_deck_name,
            "usn": -1,
            "lrnToday": [0, 0],
            "revToday": [0, 0],
            "newToday": [0, 0],
            "timeToday": [0, 0],
            "collapsed": False,
            "browserCollapsed": False,
            "desc": f"Omnididact 导出的学术研学闪卡牌组 ({doc_title or '全部文献'})",
            "dyn": 0,
            "conf": 1,
            "extendNew": 10,
            "extendRev": 50
        }
    }

    dconf_json = {
        "1": {
            "id": 1,
            "mod": now_ts,
            "name": "Default",
            "usn": 0,
            "maxTaken": 60,
            "autoplay": True,
            "timer": 0,
            "replayq": True,
            "new": {"bury": True, "delays": [1, 10], "initialFactor": 2500, "ints": [1, 4, 7], "order": 1, "perDay": 20, "separate": True},
            "rev": {"bury": True, "ease4": 1.3, "fuzz": 0.05, "ivlFct": 1, "maxIvl": 36500, "minSpace": 1, "perDay": 100},
            "lapse": {"delays": [10], "leechAction": 0, "leechFails": 8, "minInt": 1, "mult": 0}
        }
    }

    cursor.execute("""
        INSERT INTO col (id, crt, mod, scm, ver, dty, usn, ls, conf, models, decks, dconf, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        1,
        now_ts,
        now_ms,
        now_ms,
        11,
        0,
        0,
        0,
        json.dumps({"nextPos": 1, "estTimes": True, "activeDecks": [deck_id], "curDeck": deck_id}),
        json.dumps(card_model),
        json.dumps(decks_json),
        json.dumps(dconf_json),
        "{}"
    ))

    # 4. Insert Notes & Cards
    note_id_counter = int(time.time() * 1000)
    card_id_counter = note_id_counter + 100000

    for idx, card in enumerate(cards):
        note_id = note_id_counter + idx
        card_id = card_id_counter + idx

        front = clean_anki_html(card.get("front") or card.get("question") or "")
        back = clean_anki_html(card.get("back") or card.get("answer") or "")
        notes = clean_anki_html(card.get("notes") or "")
        source_p = str(card.get("paragraph_id") or "").strip()
        source = f"段落 #{source_p}" if source_p else ""

        # Tags string (space separated in Anki notes table)
        raw_tags = card.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        tags_str = " " + " ".join(t.replace(" ", "_") for t in raw_tags) + " " if raw_tags else ""

        # Fields separated by \x1f
        fields_str = "\x1f".join([front, back, notes, source])
        csum = calculate_anki_field_checksum(front)
        guid = generate_anki_guid()

        stats = card.get("stats", {})
        reps = int(stats.get("reps", 0))
        lapses = int(stats.get("lapses", 0))
        interval = int(stats.get("interval_days", 0))
        factor = int(float(stats.get("ease_factor", 2.5)) * 1000)

        # Insert note
        cursor.execute("""
            INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            note_id,
            guid,
            model_id,
            now_ts,
            -1,
            tags_str,
            fields_str,
            front,
            csum,
            0,
            ""
        ))

        # Insert card
        cursor.execute("""
            INSERT INTO cards (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            card_id,
            note_id,
            deck_id,
            0,
            now_ts,
            -1,
            2 if reps > 0 else 0,  # 0=new, 1=learning, 2=review
            2 if reps > 0 else 0,  # queue
            idx + 1 if reps == 0 else int(stats.get("next_review", now_ts + 86400)),
            interval,
            factor,
            reps,
            lapses,
            0,
            0,
            0,
            0,
            ""
        ))

    conn.commit()

    # 5. Export SQLite DB bytes
    # Dump SQLite to in-memory bytes
    db_bytes_io = io.BytesIO()
    temp_db_path = f"/tmp/anki_export_{uuid.uuid4().hex}.db"
    disk_conn = sqlite3.connect(temp_db_path)
    conn.backup(disk_conn)
    disk_conn.close()
    conn.close()

    with open(temp_db_path, "rb") as f:
        sqlite_bytes = f.read()
    try:
        os.remove(temp_db_path)
    except Exception:
        pass

    # 6. Assemble .apkg ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("collection.anki2", sqlite_bytes)
        zf.writestr("media", json.dumps({}))

    return zip_buffer.getvalue()

def export_flashcards_to_anki(
    cards: List[Dict[str, Any]],
    output_path: str,
    deck_name: str = "Omnididact 研学闪卡",
    doc_title: Optional[str] = None
) -> str:
    """Exports flashcards to an .apkg file on disk."""
    data = export_flashcards_to_apkg_bytes(cards, deck_name=deck_name, doc_title=doc_title)
    with open(output_path, "wb") as f:
        f.write(data)
    return output_path

