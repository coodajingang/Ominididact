"""
[LEGACY / FALLBACK] study.pdf_parser (基于 pymupdf4llm 的旧版解析实现)
========================================================================
注：本文件保留了系统原先基于 pymupdf4llm 库的 Markdown 抽取与启发式切块逻辑。
新版推荐使用基于 PyMuPDF 原生版面/字号/表格解析的 `study.parser` 模块。
本模块代码完整保留，供特定场景对比测试及作为解析异常时的备用兜底（Fallback）。
========================================================================
"""

import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter

import fitz  # PyMuPDF

logger = logging.getLogger("study-pdf-parser-legacy")

BULLET_REGEX = re.compile(
    r'^(?:[•\u2022\u25cf\u25cb\u25aa\u25ab\-\*]|\(?\d+[\.\)]|\(?[a-zA-Z][\.\)]|[ivxIVX]+[\.\)]|（?[一二三四五六七八九十\d]+[）\)]|[一二三四五六七八九十]+[、.])\s*'
)
CAPTION_REGEX = re.compile(
    r'^(?:Figure|Fig\.|Table|Listing|Chart|Plate|图|表)\s*\d+[:\.]?',
    re.IGNORECASE
)
CODE_KEYWORDS = (
    "def ", "class ", "import ", "from ", "return ", "async def ",
    "function ", "const ", "let ", "var ", "public static void",
    "#include ", "int main(", "SELECT ", "INSERT INTO "
)

def is_chapter_heading(text: str) -> bool:
    """
    Heuristic check if a line represents a chapter / section title.
    Supports English & Chinese numbered outlines (e.g. 1.1, 2.1.2, 第一章, 一、, (1) etc.).
    """
    t = re.sub(r'^[\s\*\-_#`]+', '', text).strip()
    t = re.sub(r'[\s\*\-_#`]+$', '', t).strip()
    if len(t) < 2 or len(t) > 150:
        return False
    patterns = [
        r'^(chapter|section|part|unit)\s+[\dIVX一二三四五六七八九十]+',
        r'^\d+(\.\d+)*\s+[A-Za-z\u4e00-\u9fa5]',
        r'^[I|V|X]+\.\s+[A-Z]',
        r'^[一二三四五六七八九十]+[、.]\s*',
        r'^(第[一二三四五六七八九十\d]+[章节回篇部])',
        r'^(abstract|introduction|background|related\s+work|methodology|methods|experiments?|results|discussion|conclusion|references|appendix)\b',
        r'^(摘要|前言|引言|背景|相关工作|研究方法|实验结果|讨论|总结|结论|参考文献|附录)\b'
    ]
    for p in patterns:
        if re.search(p, t, re.IGNORECASE):
            return True
    return False

def is_structural_boundary(text: str) -> bool:
    """
    Checks if a block represents a heading, list item, or numbered outline unit
    that must be preserved as an independent structural block and NEVER merged.
    """
    if not text:
        return False
    t = text.strip()
    if t.startswith("#"):
        return True
    if is_chapter_heading(t):
        return True
    clean = re.sub(r'^[\*_`#\s]+', '', t).strip()
    if is_chapter_heading(clean):
        return True
    # Bullet or numbered item start: (1), 1., 1.1, 一、, （一）, •, -, etc.
    if BULLET_REGEX.match(clean) or BULLET_REGEX.match(t):
        return True
    if re.match(r'^\d+(\.\d+)+\s+', clean):
        return True
    return False

def get_block_type(block: str) -> str:
    """
    Identifies block type from Markdown content:
    - Heading
    - Table
    - Code
    - List
    - Caption
    - Body Text
    """
    b = block.strip()
    if b.startswith("#"):
        return "heading"
    if b.startswith("|") and "|" in b.splitlines()[0]:
        return "table"
    if b.startswith("```"):
        return "code"
    # Check if heading (including bold markdown e.g. **1.1 Overview** or outline numbering)
    if is_chapter_heading(b):
        return "heading"
    if CAPTION_REGEX.match(b):
        return "caption"
    if BULLET_REGEX.match(b):
        return "list"
    # Check if code without backticks
    if any(b.startswith(kw) for kw in CODE_KEYWORDS):
        return "code"
    return "text"

def is_bullet_line(text: str) -> bool:
    return bool(BULLET_REGEX.match(text.strip()))

def is_caption_line(text: str) -> bool:
    return bool(CAPTION_REGEX.match(text.strip()))

def is_code_or_formula_line(plain_text: str, is_mono: bool = False) -> bool:
    if is_mono and len(plain_text.strip()) > 3:
        return True
    t = plain_text.strip()
    if any(t.startswith(kw) or f" {kw}" in t for kw in CODE_KEYWORDS):
        return True
    if re.search(r'[\u2200-\u22FF]', t):  # Math symbols
        return True
    return False

def detect_language(sample_text: str) -> str:
    """
    Detects if sample text is predominantly Chinese or English.
    Returns 'zh' or 'en'.
    """
    if not sample_text:
        return "en"
    chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', sample_text))
    total_chars = len(re.sub(r'\s+', '', sample_text))
    if total_chars == 0:
        return "en"
    ratio = chinese_chars / total_chars
    return "zh" if ratio >= 0.15 else "en"

def merge_broken_blocks(blocks: List[Dict[str, Any]], lang: str = "en") -> List[Dict[str, Any]]:
    """
    Merges consecutively split text blocks on the same page while strictly
    preserving headings, numbered outlines, and list items:
    1. Non-terminal endings (colon ':', semicolon ';', comma ',', hyphen '-', or unpunctuated text)
    2. Short blocks (< 140 chars or < 22 words) lacking sufficient context for Chat
    """
    terminal_chars = ("。", "！", "？", ".", "!", "?")
    
    # Pass 1: Sentence continuation & non-terminal punctuation merge
    pass1 = []
    for item in blocks:
        if not pass1:
            pass1.append(item)
            continue
        prev = pass1[-1]
        if (prev.get("type") == "text" and not prev.get("is_heading") and not prev.get("no_translate")
            and not prev.get("is_list")
            and item.get("type") == "text" and not item.get("is_heading") and not item.get("no_translate")
            and not item.get("is_list")
            and prev.get("page") == item.get("page")):
            
            prev_text = prev["content"].strip()
            curr_text = item["content"].strip()
            
            # Protect structural units (headings, numbered outlines, lists)
            if is_structural_boundary(prev_text) or is_structural_boundary(curr_text):
                pass1.append(item)
                continue

            clean_prev = re.sub(r'[\*_`\s]+$', '', prev_text).strip()
            clean_curr = re.sub(r'^[\*_`#\s]+', '', curr_text).strip()
            
            ends_terminal = clean_prev.endswith(terminal_chars)
            
            if not ends_terminal:
                if lang == "zh":
                    if prev_text.endswith("-"):
                        prev["content"] = prev_text[:-1] + curr_text
                    elif re.search(r'[\u4e00-\u9fa5]$', clean_prev) or re.match(r'^[\u4e00-\u9fa5]', clean_curr):
                        prev["content"] = prev_text + curr_text
                    else:
                        prev["content"] = prev_text + " " + curr_text
                else:
                    if prev_text.endswith("-"):
                        prev["content"] = prev_text[:-1] + curr_text
                    else:
                        prev["content"] = prev_text + " " + curr_text
                continue
        pass1.append(item)
        
    # Pass 2: Merge overly short fragments (< 140 chars or < 22 words) into context
    pass2 = []
    for item in pass1:
        if not pass2:
            pass2.append(item)
            continue
        prev = pass2[-1]
        if (prev.get("type") == "text" and not prev.get("is_heading") and not prev.get("no_translate")
            and not prev.get("is_list")
            and item.get("type") == "text" and not item.get("is_heading") and not item.get("no_translate")
            and not item.get("is_list")
            and prev.get("page") == item.get("page")):
            
            prev_text = prev["content"].strip()
            curr_text = item["content"].strip()
            
            # Protect structural units (headings, numbered outlines, lists)
            if is_structural_boundary(prev_text) or is_structural_boundary(curr_text):
                pass2.append(item)
                continue
            
            clean_prev = re.sub(r'[\*_`#]', '', prev_text).strip()
            word_count = len(clean_prev.split())
            char_count = len(clean_prev)
            
            if char_count < 140 or word_count < 22:
                if lang == "zh":
                    prev["content"] = prev_text + curr_text
                else:
                    prev["content"] = prev_text + " " + curr_text
                continue
        pass2.append(item)
        
    return pass2

def stitch_blocks_across_pages(all_pages_blocks: List[List[Dict[str, Any]]], lang: str = "en") -> List[Dict[str, Any]]:
    """
    Stitches text blocks across consecutive pages:
    - Hyphenated words at page ends (e.g. 'archi-' on page N, 'tecture' on page N+1 -> 'architecture')
    - Unpunctuated sentence continuation (when page N does not end with terminal punctuation, merge page N+1's opening paragraph)
    """
    terminal_chars = (".", "!", "?", "。", "！", "？")
    flattened = []
    
    for page_blocks in all_pages_blocks:
        if not page_blocks:
            continue
            
        if not flattened:
            flattened.extend(page_blocks)
            continue
            
        first_curr = page_blocks[0]
        last_prev = flattened[-1]
        
        merged = False
        if (last_prev.get("type") == "text" and not last_prev.get("is_heading") and not last_prev.get("no_translate")
            and not last_prev.get("is_list")
            and first_curr.get("type") == "text" and not first_curr.get("is_heading") and not first_curr.get("no_translate")
            and not first_curr.get("is_list")):
            
            prev_content = last_prev["content"].strip()
            curr_content = first_curr["content"].strip()
            
            # Don't merge across pages if either is a structural boundary (heading, list, numbered item)
            if not is_structural_boundary(prev_content) and not is_structural_boundary(curr_content):
                clean_prev = re.sub(r'[\*_`\s]+$', '', prev_content).strip()
                clean_curr = re.sub(r'^[\*_`\s]+', '', curr_content).strip()
                
                # 1. Hyphenation check across page boundary
                hyphen_match = re.search(r'(\w+)-\s*$', clean_prev)
                if hyphen_match:
                    cut_prev = re.sub(r'-\s*$', '', prev_content)
                    last_prev["content"] = cut_prev + curr_content
                    merged = True
                # 2. Sentence continuity across page boundary
                elif not clean_prev.endswith(terminal_chars):
                    if lang == "zh" or re.search(r'[\u4e00-\u9fa5]$', clean_prev):
                        last_prev["content"] = prev_content + curr_content
                    else:
                        last_prev["content"] = prev_content + " " + curr_content
                    merged = True
                
        if merged:
            flattened.extend(page_blocks[1:])
        else:
            flattened.extend(page_blocks)
            
    return flattened

def repair_english_paragraph(raw_text: str) -> str:
    """
    Cleans up broken lines within a paragraph while preserving natural breaks.
    """
    paragraphs = raw_text.split("\n\n")
    cleaned_paragraphs = []
    
    for p in paragraphs:
        lines = p.split("\n")
        combined_lines = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if not combined_lines:
                combined_lines.append(line_str)
                continue
            prev_line = combined_lines[-1]
            if prev_line.endswith("-"):
                combined_lines[-1] = prev_line[:-1] + line_str
            else:
                combined_lines[-1] = prev_line + " " + line_str
        cleaned_paragraphs.append(" ".join(combined_lines))
        
    merged_text = "\n\n".join(cleaned_paragraphs)
    merged_text = re.sub(r'[ \t]+', ' ', merged_text)
    return merged_text.strip()

def group_lines_into_page_blocks(lines: List[Dict[str, Any]], page_num: int, body_size: float, body_line_height: float, page_width: float) -> List[Dict[str, Any]]:
    """
    Groups lines into paragraphs using line-spacing threshold (dy > 1.4 * body_line_height).
    """
    if not lines:
        return []
    blocks = []
    current_group = []
    for line in lines:
        if not current_group:
            current_group.append(line)
            continue
        prev = current_group[-1]
        dy = line["bbox"][1] - prev["bbox"][3]
        if dy > 1.4 * body_line_height:
            blocks.append({
                "page": page_num,
                "type": "text",
                "content": " ".join(l["formatted_text"] for l in current_group).strip(),
                "is_heading": False
            })
            current_group = [line]
        else:
            current_group.append(line)
    if current_group:
        blocks.append({
            "page": page_num,
            "type": "text",
            "content": " ".join(l["formatted_text"] for l in current_group).strip(),
            "is_heading": False
        })
    return blocks

def extract_text_pdf_content(doc_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Adapter function invoking extract_pdf_with_pymupdf4llm for backwards compatibility.
    """
    from study.service import get_doc_dir
    return extract_pdf_with_pymupdf4llm(doc_id, get_doc_dir(doc_id))

# ==========================================================
# PyMuPDF4LLM Extraction Engine
# ==========================================================

def extract_pdf_with_pymupdf4llm(doc_id: str, doc_dir: str, progress_callback: Optional[Any] = None) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Converts PDF to structured Markdown using pymupdf4llm,
    extracts embedded images, splits into semantic blocks (Headings, Tables, Lists, Code, Paragraphs),
    stitches across pages, and partitions into chapters based on TOC bookmarks.
    Processes pages in batches with use_ocr=False to ensure fast processing on long documents (e.g. 2800 pages).
    """
    pdf_path = os.path.join(doc_dir, "original.pdf")
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    toc = doc.get_toc()
    
    images_dir = os.path.join(doc_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 1. Convert to page chunks with pymupdf4llm in batches
    # write_images=True saves embedded images directly into images_dir
    # use_ocr=False avoids heavy Tesseract OCR on text-native PDFs
    import pymupdf4llm
    page_chunks = []
    batch_size = 25
    for start_idx in range(0, total_pages, batch_size):
        end_idx = min(start_idx + batch_size, total_pages)
        batch_pages = list(range(start_idx, end_idx))
        try:
            batch_result = pymupdf4llm.to_markdown(
                doc,
                pages=batch_pages,
                page_chunks=True,
                write_images=True,
                image_path=images_dir,
                use_ocr=False
            )
        except Exception as e:
            logger.warning(f"pymupdf4llm batch {start_idx}-{end_idx} with image extraction failed: {e}. Falling back to standard markdown.")
            try:
                batch_result = pymupdf4llm.to_markdown(
                    doc,
                    pages=batch_pages,
                    page_chunks=True,
                    use_ocr=False
                )
            except Exception as e2:
                logger.error(f"pymupdf4llm batch {start_idx}-{end_idx} failed completely: {e2}")
                batch_result = []
                
        if isinstance(batch_result, list):
            page_chunks.extend(batch_result)
            
        if progress_callback:
            try:
                progress_callback(end_idx, total_pages)
            except Exception as cb_err:
                logger.warning(f"Progress callback error: {cb_err}")

        
    all_pages_blocks = []
    sample_text_chunks = []
    
    for idx, chunk in enumerate(page_chunks):
        page_num = idx + 1
        page_text = chunk.get("text", "")
        if not page_text.strip():
            continue
            
        # Normalize image paths to our API endpoint
        # pymupdf4llm writes markdown image tags: ![](images_dir/filename.png) or ![](filename.png)
        def replace_img_path(m):
            alt = m.group(1)
            raw_path = m.group(2)
            fname = os.path.basename(raw_path)
            return f"![{alt}](/api/study/documents/{doc_id}/images/{fname})"
            
        page_text = re.sub(r'!\[(.*?)\]\((.*?)\)', replace_img_path, page_text)
        
        # Split page markdown into logical blocks by multiple newlines
        raw_blocks = re.split(r'\n{2,}', page_text)
        
        # Pre-pass: stitch lone digits/numbers if followed by a heading or section title
        cleaned_raw_blocks = []
        i = 0
        while i < len(raw_blocks):
            raw_b = raw_blocks[i].strip()
            if not raw_b:
                i += 1
                continue
            # Check if this is a lone number/prefix like "1", "1.1", "2." that precedes a title
            if re.match(r'^\d+(\.\d+)*\.?$', raw_b) and i + 1 < len(raw_blocks):
                next_b = raw_blocks[i + 1].strip()
                # If next block is relatively short and starts with text/character (likely a heading)
                if next_b and len(next_b) < 120 and not re.match(r'^\d+', next_b) and not next_b.startswith("!") and not next_b.startswith("|"):
                    cleaned_raw_blocks.append(f"{raw_b} {next_b}")
                    i += 2
                    continue
            # Filter page numbering artifacts (e.g. lone digits remaining, or page 12 of 30)
            if re.match(r'^\d+$', raw_b) or re.match(r'^page\s+\d+(\s+of\s+\d+)?$', raw_b, re.IGNORECASE):
                i += 1
                continue
            cleaned_raw_blocks.append(raw_b)
            i += 1

        page_blocks = []
        for b_str in cleaned_raw_blocks:
            b_type = get_block_type(b_str)
            
            # Check if block is purely an image
            img_match = re.match(r'^!\[(.*?)\]\((.*?)\)$', b_str)
            if img_match:
                page_blocks.append({
                    "page": page_num,
                    "type": "image",
                    "content": b_str,
                    "image_url": img_match.group(2),
                    "is_heading": False,
                    "is_list": False,
                    "no_translate": True
                })
                continue
                
            if b_type == "heading":
                content = b_str
                # Strip leading list marker if pymupdf turned "- 1.1 Heading" into list
                if content.startswith("- ") and is_chapter_heading(content[2:]):
                    content = content[2:].strip()
                if not content.startswith("#"):
                    clean_h = re.sub(r'^[\s\*_`]+', '', content).strip()
                    dots = len(re.findall(r'\.', clean_h.split()[0])) if (clean_h and clean_h[0].isdigit()) else 0
                    lvl = min(dots + 2, 5)
                    content = f"{'#' * lvl} {clean_h}"
                page_blocks.append({
                    "page": page_num,
                    "type": "text",
                    "content": content,
                    "image_url": "",
                    "is_heading": True,
                    "is_list": False,
                    "no_translate": False
                })
            elif b_type == "code":
                page_blocks.append({
                    "page": page_num,
                    "type": "code",
                    "content": b_str,
                    "image_url": "",
                    "is_heading": False,
                    "is_list": False,
                    "no_translate": True
                })
            elif b_type == "caption":
                page_blocks.append({
                    "page": page_num,
                    "type": "caption",
                    "content": b_str,
                    "image_url": "",
                    "is_heading": False,
                    "is_list": False,
                    "no_translate": False
                })
            elif b_type == "table":
                page_blocks.append({
                    "page": page_num,
                    "type": "text",
                    "content": b_str,
                    "image_url": "",
                    "is_heading": False,
                    "is_list": False,
                    "no_translate": False
                })
            elif b_type == "list":
                page_blocks.append({
                    "page": page_num,
                    "type": "text",
                    "content": b_str,
                    "image_url": "",
                    "is_heading": False,
                    "is_list": True,
                    "no_translate": False
                })
            else:
                # Standard paragraph
                clean_p = repair_english_paragraph(b_str)
                page_blocks.append({
                    "page": page_num,
                    "type": "text",
                    "content": clean_p,
                    "image_url": "",
                    "is_heading": False,
                    "is_list": False,
                    "no_translate": False
                })
                
            if len(sample_text_chunks) < 20:
                sample_text_chunks.append(b_str)
                
        all_pages_blocks.append(page_blocks)
        
    full_sample = " ".join(sample_text_chunks)
    lang = detect_language(full_sample)
    
    # 2. Cross-page stitching (Hyphenation & unpunctuated sentence continuation)
    stitched_blocks = stitch_blocks_across_pages(all_pages_blocks, lang)
    
    # 3. Post-merging pass for non-terminal colons & short fragments
    raw_blocks = merge_broken_blocks(stitched_blocks, lang)
    
    # 4. Chapter division based on PDF Table of Contents (TOC) bookmarks
    doc.close()
    
    from study.parser import partition_blocks_into_chapters

    chapter_targets = []
    if toc:
        min_lvl = min((item[0] for item in toc), default=1)
        top_toc = [item for item in toc if item[0] == min_lvl]
        if len(top_toc) == 1 and len(toc) > 1:
            sub_lvls = [item[0] for item in toc if item[0] > min_lvl]
            if sub_lvls:
                target_lvl = min(sub_lvls)
                sub_toc = [item for item in toc if item[0] == target_lvl]
                if sub_toc:
                    top_toc = sub_toc

        if top_toc:
            for i in range(len(top_toc)):
                title = top_toc[i][1].strip()
                start_p = 1 if i == 0 else max(1, top_toc[i][2])
                chapter_targets.append({
                    "title": title,
                    "start_page": start_p
                })
                
    if not chapter_targets and total_pages >= 6:
        detected_headings = []
        for idx, b in enumerate(raw_blocks):
            if b.get("is_heading"):
                c = b.get("content", "").strip()
                c_clean = re.sub(r'^[#\s]+', '', c).strip()
                is_strict_chapter = (
                    is_chapter_heading(c_clean)
                    or bool(re.match(r'^(第[一二三四五六七八九十0-9]+[章篇部分]|Chapter\s+[\dIVX]+|Section\s+[\dIVX]+|Part\s+[\dIVX]+|前\s*言|Preface|致\s*谢|附录|附件\s*[0-9一二三四五六七八九十A-Za-z]+)', c_clean, re.I))
                )
                if is_strict_chapter:
                    p_num = b["page"]
                    if not detected_headings or (idx - detected_headings[-1]["block_idx"] >= 4 and p_num - detected_headings[-1]["start_page"] >= 1):
                        detected_headings.append({"title": c_clean, "start_page": p_num, "block_idx": idx})
        if len(detected_headings) >= 2:
            detected_headings[0]["start_page"] = 1
            detected_headings[0]["block_idx"] = 0
            chapter_targets = detected_headings

    if not chapter_targets:
        chapter_targets = [{
            "title": "文档正文" if lang == "zh" else "Document Body",
            "start_page": 1,
            "block_idx": 0
        }]
        
    partitioned_chapters = partition_blocks_into_chapters(raw_blocks, chapter_targets, lang=lang)

    chapters = []
    para_counter = 1
    for ch_idx, ch_info in enumerate(partitioned_chapters, 1):
        ch_paragraphs = []
        for b in ch_info["blocks"]:
            b_type = b.get("type", "text")
            if b_type == "image":
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": b["page"],
                    "type": "image",
                    "english": b["content"],
                    "chinese": "",
                    "status": "completed",
                    "no_translate": True,
                    "image_url": b.get("image_url", "")
                })
                para_counter += 1
            elif b_type == "code":
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": b["page"],
                    "type": "code",
                    "english": b["content"],
                    "chinese": "",
                    "status": "completed",
                    "no_translate": True,
                    "image_url": ""
                })
                para_counter += 1
            elif b_type == "caption":
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": b["page"],
                    "type": "caption",
                    "english": b["content"],
                    "chinese": "",
                    "status": "completed",
                    "no_translate": True,
                    "image_url": ""
                })
                para_counter += 1
            else:
                raw_text = b["content"].strip()
                if not raw_text:
                    continue
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": b["page"],
                    "type": "text",
                    "english": raw_text,
                    "chinese": "",
                    "status": "completed" if lang == "zh" else "pending",
                    "no_translate": False,
                    "image_url": ""
                })
                para_counter += 1
                
        chapters.append({
            "chapter_id": f"ch_{ch_idx:03d}",
            "title": ch_info["title"],
            "paragraphs": ch_paragraphs
        })
        
    return lang, chapters

# ==========================================================
# Chapter and Document Markdown Builders
# ==========================================================

def render_chapter_markdown(chapter: Dict[str, Any], language: str = "en") -> str:
    """
    Renders chapter into Markdown according to user formatting rules:
    - English paragraph restored natural flow
    - > Chinese translation blockquote
    - > 💡 Paragraph notes/annotations blockquote
    - > 📌 Chapter header/footer summaries
    - --- Separator
    If language == 'zh', renders Chinese paragraphs directly with ---
    If scanned_page, renders page image + OCR text + translation + notes
    """
    lines = []
    title = chapter.get("title", "Chapter")
    lines.append(f"# {title}\n\n")
    
    # 1. Chapter Header Notes / Summaries
    header_notes = chapter.get("header_notes", [])
    if header_notes:
        for hn in header_notes:
            c = hn.get("content", "").strip()
            if c:
                quote_lines = "\n".join([f"> {line}" for line in c.splitlines()])
                lines.append(f"> 📌 **【本章总览与学习总结】**\n{quote_lines}\n\n")
        lines.append("---\n\n")
    
    # 2. Paragraphs and Paragraph Notes
    for p in chapter.get("paragraphs", []):
        p_type = p.get("type", "text")
        if p_type == "image":
            lines.append(f"{p.get('english')}\n\n---\n\n")
            continue
            
        if p_type == "scanned_page":
            img_url = p.get('image_url', '')
            lines.append(f"![Page {p.get('page', 1)}]({img_url})\n\n")
            if p.get("english"):
                lines.append(f"{p.get('english')}\n\n")
            if p.get("chinese"):
                quote_formatted = "\n".join([f"> {line}" for line in p.get("chinese").split("\n") if line.strip()])
                lines.append(f"{quote_formatted}\n\n")
            # Paragraph Notes
            for nt in p.get("notes", []):
                c = nt.get("content", "").strip()
                if c:
                    note_quote = "\n".join([f"> {line}" for line in c.splitlines()])
                    lines.append(f"> 💡 **【研读注解】**\n{note_quote}\n\n")
            lines.append("---\n\n")
            continue
            
        english_text = p.get("english", "").strip()
        chinese_text = p.get("chinese", "").strip()
        
        if language == "zh":
            lines.append(f"{english_text}\n\n")
        else:
            lines.append(f"{english_text}\n\n")
            if chinese_text:
                quote_formatted = "\n".join([f"> {line}" for line in chinese_text.split("\n") if line.strip()])
                lines.append(f"{quote_formatted}\n\n")
                
        # Paragraph Notes
        for nt in p.get("notes", []):
            c = nt.get("content", "").strip()
            if c:
                note_quote = "\n".join([f"> {line}" for line in c.splitlines()])
                lines.append(f"> 💡 **【研读注解】**\n{note_quote}\n\n")
                
        lines.append("---\n\n")
        
    # 3. Chapter Footer Notes / Review
    footer_notes = chapter.get("footer_notes", [])
    if footer_notes:
        for fn in footer_notes:
            c = fn.get("content", "").strip()
            if c:
                quote_lines = "\n".join([f"> {line}" for line in c.splitlines()])
                lines.append(f"> 🎯 **【本章回顾与考点总结】**\n{quote_lines}\n\n")
        lines.append("---\n\n")
            
    return "".join(lines)

