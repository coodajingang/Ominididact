import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional

from study.pdf_parser import (
    detect_language,
    is_chapter_heading,
    repair_english_paragraph,
    get_block_type
)
from study.parser import is_predominantly_target_lang

logger = logging.getLogger("study-text-parser")

def decode_text_bytes(file_bytes: bytes) -> str:
    """
    Decodes binary text bytes using a prioritized list of encodings:
    UTF-8 with BOM, standard UTF-8, Chinese Windows encodings (GB18030, GBK, CP936),
    Big5, and Latin-1 fallback.
    """
    encodings = ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936", "big5", "latin-1")
    for enc in encodings:
        try:
            return file_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return file_bytes.decode("utf-8", errors="replace")

def _split_markdown_into_raw_blocks(text: str) -> List[Dict[str, Any]]:
    """
    Splits markdown text into logical raw blocks, preserving fenced code blocks
    (```...```) intact even if they contain blank lines or # characters.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    current_lines = []
    in_code_block = False
    fence_marker = ""

    for line in lines:
        stripped = line.strip()
        
        # Check code fence entry / exit
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            if not in_code_block:
                if current_lines and not any(l.strip() for l in current_lines):
                    current_lines = []
                elif current_lines:
                    block_text = "\n".join(current_lines).strip()
                    if block_text:
                        blocks.append({"text": block_text, "is_code": False})
                    current_lines = []
                in_code_block = True
                fence_marker = fence
                current_lines.append(line)
            elif in_code_block and stripped.startswith(fence_marker):
                current_lines.append(line)
                in_code_block = False
                fence_marker = ""
                blocks.append({"text": "\n".join(current_lines).strip(), "is_code": True})
                current_lines = []
            else:
                current_lines.append(line)
            continue

        if in_code_block:
            current_lines.append(line)
            continue

        # Regular markdown line outside code block
        if not stripped:
            if current_lines:
                block_text = "\n".join(current_lines).strip()
                if block_text:
                    blocks.append({"text": block_text, "is_code": False})
                current_lines = []
            continue

        # Check if line is a standalone markdown heading (# ...)
        if re.match(r'^#{1,6}\s+', stripped):
            if current_lines:
                block_text = "\n".join(current_lines).strip()
                if block_text:
                    blocks.append({"text": block_text, "is_code": False})
                current_lines = []
            blocks.append({"text": stripped, "is_code": False})
            continue

        # Check if line is a standalone image (![...](...))
        if re.match(r'^!\[(.*?)\]\((.*?)\)$', stripped):
            if current_lines:
                block_text = "\n".join(current_lines).strip()
                if block_text:
                    blocks.append({"text": block_text, "is_code": False})
                current_lines = []
            blocks.append({"text": stripped, "is_code": False})
            continue

        # Check transition into or out of markdown table
        if stripped.startswith("|") and current_lines and not current_lines[-1].strip().startswith("|"):
            block_text = "\n".join(current_lines).strip()
            if block_text:
                blocks.append({"text": block_text, "is_code": False})
            current_lines = []
        elif not stripped.startswith("|") and current_lines and current_lines[-1].strip().startswith("|"):
            block_text = "\n".join(current_lines).strip()
            if block_text:
                blocks.append({"text": block_text, "is_code": False})
            current_lines = []

        current_lines.append(line)

    if current_lines:
        block_text = "\n".join(current_lines).strip()
        if block_text:
            blocks.append({"text": block_text, "is_code": in_code_block})

    return blocks

def parse_markdown_content(text: str, doc_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parses structured Markdown document into chapters and paragraph blocks.
    Identifies top-level headings (# or ##) to partition into chapters.
    Preserves tables, fenced code blocks, image links, and subheadings.
    """
    lang = detect_language(text[:3000] if len(text) > 3000 else text)
    raw_blocks = _split_markdown_into_raw_blocks(text)
    if not raw_blocks:
        return lang, [{
            "chapter_id": "ch_001",
            "title": "文档正文" if lang == "zh" else "Document Body",
            "paragraphs": []
        }]

    # Determine primary chapter heading level
    h1_count = sum(1 for b in raw_blocks if not b["is_code"] and re.match(r'^#\s+[^#]', b["text"].strip()))
    h2_count = sum(1 for b in raw_blocks if not b["is_code"] and re.match(r'^##\s+[^#]', b["text"].strip()))
    h3_count = sum(1 for b in raw_blocks if not b["is_code"] and re.match(r'^###\s+[^#]', b["text"].strip()))

    chapter_heading_regex = None
    if h1_count >= 2:
        chapter_heading_regex = re.compile(r'^#\s+(.+)$')
    elif h1_count == 1 and h2_count >= 1:
        # Single top-level document title (#) with chapter/section breakdown (##)
        chapter_heading_regex = re.compile(r'^(?:#{1,2})\s+(.+)$')
    elif h1_count == 1:
        chapter_heading_regex = re.compile(r'^#\s+(.+)$')
    elif h2_count >= 1:
        chapter_heading_regex = re.compile(r'^##\s+(.+)$')
    elif h3_count >= 2:
        chapter_heading_regex = re.compile(r'^###\s+(.+)$')

    # Partition blocks into chapters
    chapter_groups = []
    current_ch_title = "导读 / 引言" if lang == "zh" else "Introduction"
    current_ch_blocks = []

    for b in raw_blocks:
        b_text = b["text"].strip()
        is_code = b["is_code"]

        if not is_code and chapter_heading_regex:
            m = chapter_heading_regex.match(b_text)
            if m:
                # Start new chapter
                if current_ch_blocks:
                    chapter_groups.append({
                        "title": current_ch_title,
                        "blocks": current_ch_blocks
                    })
                current_ch_title = m.group(1).strip()
                current_ch_blocks = [b]
                continue

        current_ch_blocks.append(b)

    if current_ch_blocks:
        chapter_groups.append({
            "title": current_ch_title,
            "blocks": current_ch_blocks
        })

    # If only one chapter with default title, refine title
    if len(chapter_groups) == 1 and chapter_groups[0]["title"] in ("导读 / 引言", "Introduction"):
        chapter_groups[0]["title"] = "文档正文" if lang == "zh" else "Document Body"

    chapters = []
    para_counter = 1

    for ch_idx, ch_def in enumerate(chapter_groups, 1):
        ch_paragraphs = []
        for b in ch_def["blocks"]:
            b_text = b["text"].strip()
            is_code = b["is_code"]

            if is_code or b_text.startswith("```"):
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": 1,
                    "type": "code",
                    "english": b_text,
                    "chinese": "",
                    "status": "completed",
                    "no_translate": True,
                    "image_url": ""
                })
                para_counter += 1
                continue

            # Check if block is purely an image: ![alt](url)
            img_m = re.match(r'^!\[(.*?)\]\((.*?)\)$', b_text)
            if img_m:
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": 1,
                    "type": "image",
                    "english": b_text,
                    "chinese": "",
                    "status": "completed",
                    "no_translate": True,
                    "image_url": img_m.group(2)
                })
                para_counter += 1
                continue

            # Check if heading
            if b_text.startswith("#"):
                is_heading_zh = is_predominantly_target_lang(b_text, "zh")
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": 1,
                    "type": "text",
                    "english": b_text,
                    "chinese": "",
                    "status": "completed" if (lang == "zh" or is_heading_zh) else "pending",
                    "no_translate": lang == "zh" or is_heading_zh,
                    "image_url": "",
                    "is_heading": True
                })
                para_counter += 1
                continue

            # Check if table
            if b_text.startswith("|") and "|" in b_text.splitlines()[0]:
                is_table_zh = is_predominantly_target_lang(b_text, "zh")
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": 1,
                    "type": "table",
                    "english": b_text,
                    "chinese": "",
                    "status": "completed" if (lang == "zh" or is_table_zh) else "pending",
                    "no_translate": lang == "zh" or is_table_zh,
                    "image_url": ""
                })
                para_counter += 1
                continue

            # Regular text paragraph
            if lang == "en":
                clean_p = repair_english_paragraph(b_text)
            else:
                clean_p = b_text

            is_para_zh = is_predominantly_target_lang(clean_p, "zh")
            ch_paragraphs.append({
                "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                "page": 1,
                "type": "text",
                "english": clean_p,
                "chinese": "",
                "status": "completed" if (lang == "zh" or is_para_zh) else "pending",
                "no_translate": lang == "zh" or is_para_zh,
                "image_url": ""
            })
            para_counter += 1

        chapters.append({
            "chapter_id": f"ch_{ch_idx:03d}",
            "title": ch_def["title"],
            "paragraphs": ch_paragraphs
        })

    return lang, chapters

def parse_txt_content(text: str, doc_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    r"""
    Parses plain text document into chapters and paragraphs.
    1. Splits into paragraphs by double newlines (\n\s*\n).
    2. Identifies chapter headings using heuristic patterns (第X章, Chapter X, 1. Introduction, etc.).
    3. If no headings exist and paragraph count > 50, partitions into logical batches (~40-50 paragraphs/chapter).
    """
    lang = detect_language(text[:3000] if len(text) > 3000 else text)
    
    # Normalize line endings and split by blank lines
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_paras = [p.strip() for p in re.split(r'\n\s*\n+', normalized) if p.strip()]
    
    if not raw_paras:
        return lang, [{
            "chapter_id": "ch_001",
            "title": "文档正文" if lang == "zh" else "Document Body",
            "paragraphs": []
        }]

    # Scan for chapter headings
    chapter_indices = []
    for idx, p in enumerate(raw_paras):
        first_line = p.splitlines()[0].strip()
        # Heading must not be excessively long
        if len(first_line) <= 100 and is_chapter_heading(first_line):
            chapter_indices.append((idx, first_line))

    chapters = []
    para_counter = 1

    if chapter_indices:
        # Partition by detected headings
        ch_sections = []
        # Pre-heading intro
        if chapter_indices[0][0] > 0:
            ch_sections.append({
                "title": "导读 / 前言" if lang == "zh" else "Introduction",
                "paras": raw_paras[0:chapter_indices[0][0]]
            })

        for i, (p_idx, title) in enumerate(chapter_indices):
            next_p_idx = chapter_indices[i + 1][0] if i + 1 < len(chapter_indices) else len(raw_paras)
            ch_sections.append({
                "title": title,
                "paras": raw_paras[p_idx:next_p_idx]
            })

        for ch_idx, sec in enumerate(ch_sections, 1):
            ch_paras = []
            for p_text in sec["paras"]:
                is_head = is_chapter_heading(p_text.splitlines()[0].strip())
                clean_p = repair_english_paragraph(p_text) if lang == "en" else p_text
                is_para_zh = is_predominantly_target_lang(clean_p, "zh")
                ch_paras.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": 1,
                    "type": "text",
                    "english": clean_p,
                    "chinese": "",
                    "status": "completed" if (lang == "zh" or is_para_zh) else "pending",
                    "no_translate": lang == "zh" or is_para_zh,
                    "image_url": "",
                    "is_heading": is_head
                })
                para_counter += 1

            chapters.append({
                "chapter_id": f"ch_{ch_idx:03d}",
                "title": sec["title"],
                "paragraphs": ch_paras
            })
    else:
        # No headings found. If text is long (> 50 paragraphs), partition into logical sections
        chunk_size = 45
        if len(raw_paras) > 50:
            for start_i in range(0, len(raw_paras), chunk_size):
                ch_idx = len(chapters) + 1
                end_i = min(start_i + chunk_size, len(raw_paras))
                ch_paras = []
                for p_text in raw_paras[start_i:end_i]:
                    clean_p = repair_english_paragraph(p_text) if lang == "en" else p_text
                    is_para_zh = is_predominantly_target_lang(clean_p, "zh")
                    ch_paras.append({
                        "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                        "page": 1,
                        "type": "text",
                        "english": clean_p,
                        "chinese": "",
                        "status": "completed" if (lang == "zh" or is_para_zh) else "pending",
                        "no_translate": lang == "zh" or is_para_zh,
                        "image_url": ""
                    })
                    para_counter += 1

                label = f"第 {ch_idx} 部分 ({start_i+1}~{end_i}段)" if lang == "zh" else f"Part {ch_idx} (Paras {start_i+1}-{end_i})"
                chapters.append({
                    "chapter_id": f"ch_{ch_idx:03d}",
                    "title": label,
                    "paragraphs": ch_paras
                })
        else:
            # Single chapter
            ch_paras = []
            for p_text in raw_paras:
                clean_p = repair_english_paragraph(p_text) if lang == "en" else p_text
                is_para_zh = is_predominantly_target_lang(clean_p, "zh")
                ch_paras.append({
                    "id": f"p_001_{para_counter:04d}",
                    "page": 1,
                    "type": "text",
                    "english": clean_p,
                    "chinese": "",
                    "status": "completed" if (lang == "zh" or is_para_zh) else "pending",
                    "no_translate": lang == "zh" or is_para_zh,
                    "image_url": ""
                })
                para_counter += 1

            chapters.append({
                "chapter_id": "ch_001",
                "title": "文档正文" if lang == "zh" else "Document Body",
                "paragraphs": ch_paras
            })

    return lang, chapters

def extract_text_or_markdown_content(
    doc_id: str,
    doc_dir: str,
    filename: str,
    progress_callback: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Main dispatch function for text and markdown documents.
    Reads file from doc_dir, auto-detects encoding, and dispatches to appropriate parser.
    """
    ext = os.path.splitext(filename)[1].lower()
    file_path = os.path.join(doc_dir, f"original{ext}")
    if not os.path.isfile(file_path):
        # Check if original without extension or exact filename
        for candidate in (os.path.join(doc_dir, filename), os.path.join(doc_dir, "original.txt"), os.path.join(doc_dir, "original.md")):
            if os.path.isfile(candidate):
                file_path = candidate
                break

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    text = decode_text_bytes(file_bytes)
    if progress_callback:
        try:
            progress_callback(1, 1)
        except Exception:
            pass

    if ext in (".md", ".markdown"):
        return parse_markdown_content(text, doc_id)
    else:
        return parse_txt_content(text, doc_id)

