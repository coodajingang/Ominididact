"""
study/parser.py (原生高保真 PDF 版面与结构解析器 - 方案B)
========================================================================
本模块基于 PyMuPDF 原生版面数据结构 (get_text("dict") / blocks + find_tables)，
替代基于 pymupdf4llm 的启发式平铺清洗方案，彻底解决：
1. 多级标题编号 (如 1.1, 2.1.2, 一、, (1) 等) 被降级、抹平或丢失的问题；
2. 嵌套条目、列表项被过度归一化为平铺列表或与正文强行揉合的问题；
3. 表格与图片在正文流中的精准对齐与独立提取。

核心能力：
- 统计计算文档基准字号 (Dominant Body Font Size)，精准判定多级标题 (#, ##, ###)；
- 序号与结构屏障保护：严格保留所有段首编号并确保其独立成块；
- 原生表格提取 (page.find_tables() -> Markdown Table) 并自动屏蔽重复文本提取；
- 嵌入图片智能抽取 (page.get_text("dict") image blocks / get_images())；
- 章节依据真实 PDF 目录大纲 (TOC Bookmarks) 或一级标题智能切分。
========================================================================
"""

import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter

import fitz  # PyMuPDF

import statistics

logger = logging.getLogger("study-native-parser")

# 标号与列表匹配模式
OUTLINE_NUMBER_REGEX = re.compile(
    r'^(?:'
    r'\d+(\.\d+)+\s+'                      # 1.1, 2.1.2, 2.6.4
    r'|\(?([1-9]\d?|[ivxIVX]{1,5}|[a-zA-Z]|[一二三四五六七八九十\d]{1,3})[\.\)]\s+' # 1., 2), (1), A., (A), 一、
    r'|（?[一二三四五六七八九十\d]+[）\)]\s*' # （一）, (1), 1）
    r'|[一二三四五六七八九十]+[、.]\s*'       # 一、, 二.
    r'|第[一二三四五六七八九十\d]+[章节回篇部]\s*' # 第一章
    r'|[•\u2022\u25cf\u25cb\u25aa\u25ab\-\*]\s+' # 常见圆点列表
    r')'
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

ABBREVIATIONS = (
    "e.g.", "i.e.", "etc.", "vs.", "al.", "fig.", "figs.", "ref.", "refs.",
    "approx.", "dept.", "no.", "nos.", "vol.", "vols.", "sec.", "secs.",
    "ch.", "dr.", "mr.", "mrs.", "ms.", "prof.", "inc.", "ltd.", "co.", "corp."
)

def is_sentence_terminal(text: str) -> bool:
    """
    判断文本是否以句末终止符结尾（排除常见英文缩写、冒号/破折号引出等情况）。
    """
    t = text.strip()
    if not t:
        return True
    t = re.sub(r'[\*_`\s]+$', '', t)
    if not t:
        return True
    t_lower = t.lower()
    if re.search(r'\b(e\.g|i\.e|etc|vs|al|fig|ref|approx|dept|no|vol|sec|ch|dr|mr|mrs|ms|prof|inc|ltd|co|corp)\.$', t_lower):
        return False
    if t.endswith((':', '：', '—', '–', '--')):
        return True
    return bool(re.search(r'[\.!\?。！？]["\'\)\]\}”’]*$', t))

def has_unclosed_paren(text: str) -> bool:
    """
    检查文本是否存在未闭合的括号或方括号。
    """
    return text.count('(') > text.count(')') or text.count('[') > text.count(']')

def is_list_item(text: str) -> bool:
    """
    判断文本是否为列表项（且避免将例如 256) 这类括号数字误判为列表）。
    """
    t = text.strip()
    m = OUTLINE_NUMBER_REGEX.match(t)
    if not m:
        return False
    num_m = re.match(r'^\(?(\d+)[\.\)]', t)
    if num_m and int(num_m.group(1)) > 99:
        return False
    return True

def get_list_type(text: str) -> str:
    """
    返回列表项的类型标识，用于判定相邻列表项是否属于同一列表体系以进行段落级聚合。
    """
    t = text.strip()
    m = OUTLINE_NUMBER_REGEX.match(t)
    if not m:
        return ""
    matched = m.group(0).strip()
    if re.match(r'^[A-Za-z][\.\)]', matched):
        return "alpha"
    if re.match(r'^\(?[A-Za-z][\.\)]', matched):
        return "alpha_paren"
    if re.match(r'^\d+(\.\d+)+', matched):
        return "outline_decimal"
    if re.match(r'^\(?\d+[\.\)]', matched):
        return "decimal"
    if re.match(r'^[•\u2022\u25cf\u25cb\u25aa\u25ab\-\*]', matched):
        return "bullet"
    if re.match(r'^[一二三四五六七八九十]+[、.]', matched) or re.match(r'^（?[一二三四五六七八九十]+[）\)]', matched):
        return "zh_num"
    if re.match(r'^[ivxIVX]+[\.\)]', matched):
        return "roman"
    return "other"

def detect_language(sample_text: str) -> str:
    """
    判断样本文档语言（中文 zh 或英文 en）。
    """
    if not sample_text:
        return "en"
    chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', sample_text))
    total_chars = len(re.sub(r'\s+', '', sample_text))
    if total_chars == 0:
        return "en"
    ratio = chinese_chars / total_chars
    return "zh" if ratio >= 0.15 else "en"

def is_predominantly_target_lang(text: str, target_lang: str = "zh", threshold: float = 0.35) -> bool:
    """
    检查文本是否大部分为目标语言（默认中文 zh）。
    若大部分已是目标语言，或纯符号/代码，则无需调用大模型翻译。
    """
    if not text:
        return True

    # 过滤 markdown 图片、链接及符号标记，避免干扰字符统计
    clean = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    clean = re.sub(r'\[.*?\]\(.*?\)', '', clean)
    clean = re.sub(r'[`#*_\->~]', ' ', clean)

    # 统计有效文字与字母字符（中英文字符、数字）
    valid_chars = re.findall(r'[\w\u4e00-\u9fa5]', clean)
    if len(valid_chars) < 2:
        # 极短纯标点或纯符号段落
        return True

    if target_lang == "zh":
        chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', clean))
        ratio = chinese_chars / len(valid_chars)
        return ratio >= threshold

    return False

def is_chapter_heading(text: str) -> bool:
    """
    启发式检查文本是否构成章节/小节标题（中英文均支持）。
    """
    t = re.sub(r'^[\s\*\-_#`]+', '', text).strip()
    t = re.sub(r'[\s\*\-_#`]+$', '', t).strip()
    if len(t) < 2 or len(t) > 150:
        return False
    patterns = [
        r'^(chapter|section|part|unit)\s+[\dIVX一二三四五六七八九十]+',
        r'^[I|V|X]+\.\s+[A-Z]',
        r'^(第[一二三四五六七八九十\d]+[章节回篇部])',
        r'^(abstract|introduction|background|related\s+work|methodology|methods|experiments?|results|discussion|conclusion|references|appendix)\b',
        r'^(摘要|前言|引言|背景|相关工作|研究方法|实验结果|讨论|总结|结论|参考文献|附录)\b'
    ]
    for p in patterns:
        if re.search(p, t, re.IGNORECASE):
            return True
    return False

def compute_body_font_size(doc: fitz.Document, sample_pages: int = 25) -> float:
    """
    采样文档前若干页，根据非加粗文字的字符频数计算正文字号基准值（body_size）。
    """
    size_counter = Counter()
    max_p = min(sample_pages, len(doc))
    for pno in range(max_p):
        try:
            page = doc[pno]
            d = page.get_text("dict")
            for b in d.get("blocks", []):
                if b.get("type") == 0:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            t = s.get("text", "").strip()
                            if t and not (s.get("flags", 0) & 16):
                                size_counter[round(s.get("size", 12.0), 1)] += len(t)
        except Exception as e:
            logger.warning(f"Error sampling font size on page {pno}: {e}")
            
    if size_counter:
        return size_counter.most_common(1)[0][0]
    return 12.0

def merge_table_rects(page: fitz.Page) -> List[fitz.Rect]:
    """
    检测并智能合并同一页面上因排版切碎或无框线相邻的表格区域。
    """
    try:
        import pymupdf
        pymupdf._get_layout = None
    except Exception:
        pass
        
    try:
        tabs = page.find_tables()
        if not tabs.tables:
            return []
        raw_rects = [fitz.Rect(t.bbox) for t in tabs.tables]
        raw_rects.sort(key=lambda r: (r.y0, r.x0))
        merged = []
        for r in raw_rects:
            if not merged:
                merged.append(r)
                continue
            prev = merged[-1]
            x_overlap = min(prev.x1, r.x1) - max(prev.x0, r.x0)
            x_union = max(prev.x1, r.x1) - min(prev.x0, r.x0)
            is_same_x = (x_overlap / x_union) > 0.65 if x_union > 0 else False
            is_vert_close = (r.y0 - prev.y1) < 80.0
            if (is_same_x and is_vert_close) or not (prev & r).is_empty:
                merged[-1] = prev | r
            else:
                merged.append(r)
        return merged
    except Exception as e:
        logger.warning(f"Error finding/merging tables on page {page.number}: {e}")
        return []

def is_bbox_in_rects(bbox: Tuple[float, float, float, float], rects: List[fitz.Rect]) -> bool:
    """
    检查一个包围盒是否在给定的矩形列表（如表格矩形）内。
    """
    b_rect = fitz.Rect(bbox)
    for r in rects:
        intersect = b_rect & r
        if not intersect.is_empty and (intersect.get_area() > 0.6 * b_rect.get_area()):
            return True
    return False

def format_span_text(span: Dict[str, Any]) -> str:
    """
    根据字形标志为单文本 Span 添加内联 Markdown（粗体/斜体/行内代码）。
    """
    text = span.get("text", "")
    if not text:
        return ""
    flags = span.get("flags", 0)
    font = span.get("font", "").lower()
    
    is_bold = bool(flags & 16 or "bold" in font or "black" in font or "heavy" in font)
    is_italic = bool(flags & 2 or flags & 1 or "italic" in font or "oblique" in font)
    is_mono = bool(flags & 8 or "mono" in font or "courier" in font or "consolas" in font)
    
    stripped = text.strip()
    if not stripped:
        return text
        
    lead_space = text[:len(text) - len(text.lstrip())]
    trail_space = text[len(text.rstrip()):]
    
    styled = stripped
    if is_mono and len(styled) > 1:
        styled = f"`{styled}`"
    elif is_bold and is_italic:
        styled = f"***{styled}***"
    elif is_bold:
        styled = f"**{styled}**"
    elif is_italic:
        styled = f"*{styled}*"
        
    return f"{lead_space}{styled}{trail_space}"

def repair_english_paragraph(raw_text: str) -> str:
    """
    清洗同一段落内的断行，保留自然空行与段落。
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

def stitch_cross_page_blocks(all_pages_blocks: List[List[Dict[str, Any]]], lang: str = "en") -> List[Dict[str, Any]]:
    """
    跨页自然缝合：
    1. 跨页同族列表项聚合（如第 2 页结尾到第 3 页开头的连续大纲列表）
    2. 页面结尾单词断连字符 (如 archi- \\n tecture -> architecture)
    3. 无终止标点的跨页自然句连（未结束段落的自然拼接）
    严格保护独立标题不被跨页吞没。
    """
    flattened = []
    
    for page_blocks in all_pages_blocks:
        if not page_blocks:
            continue
        if not flattened:
            flattened.extend(page_blocks)
            continue
            
        last_prev = flattened[-1]
        first_curr = page_blocks[0]
        
        # 1. 跨页同类型列表拼接 (如 Page 2 结尾的 2.6.3 与 Page 3 开头的 2.6.4)
        if (last_prev.get("is_list") and first_curr.get("is_list")
            and last_prev.get("list_type") == first_curr.get("list_type")
            and not last_prev.get("is_heading") and not first_curr.get("is_heading")):
            last_prev["content"] = last_prev["content"] + "\n" + first_curr["content"]
            flattened.extend(page_blocks[1:])
            continue
            
        # 2. 跨页未终结正文拼接
        if (last_prev.get("type") == "text" and not last_prev.get("is_heading") and not last_prev.get("is_list")
            and first_curr.get("type") == "text" and not first_curr.get("is_heading") and not first_curr.get("is_list")):
            
            prev_content = last_prev["content"].strip()
            curr_content = first_curr["content"].strip()
            clean_prev = re.sub(r'[\*_`\s]+$', '', prev_content).strip()
            
            if not is_sentence_terminal(clean_prev):
                hyphen_match = re.search(r'(\w+)-\s*$', clean_prev)
                if hyphen_match:
                    cut_prev = re.sub(r'-\s*$', '', prev_content)
                    last_prev["content"] = cut_prev + curr_content
                else:
                    if lang == "zh" or re.search(r'[\u4e00-\u9fa5]$', clean_prev):
                        last_prev["content"] = prev_content + curr_content
                    else:
                        last_prev["content"] = prev_content + " " + curr_content
                flattened.extend(page_blocks[1:])
                continue
                
        flattened.extend(page_blocks)
        
    return flattened

def calculate_heading_similarity(toc_title: str, block_text: str) -> float:
    """计算大纲标题与待测 Block 文本的相似度 (0.0 ~ 1.0)"""
    t_clean = re.sub(r'^[#\s\*_`]+', '', toc_title).strip()
    b_first_line = block_text.splitlines()[0] if block_text else ''
    b_clean = re.sub(r'^[#\s\*_`]+', '', b_first_line).strip()
    if not t_clean or not b_clean:
        return 0.0
    
    t_norm = re.sub(r'[\s\W_]+', '', t_clean.lower())
    b_norm = re.sub(r'[\s\W_]+', '', b_clean.lower())
    if not t_norm or not b_norm:
        return 0.0
    
    if t_norm == b_norm:
        return 1.0
        
    len_min = min(len(t_norm), len(b_norm))
    len_max = max(len(t_norm), len(b_norm))
    if len_min >= 4 and (t_norm in b_norm or b_norm in t_norm):
        ratio = len_min / len_max
        if ratio >= 0.6:
            return 0.8 + 0.2 * ratio
    
    words_t = set(re.findall(r'\w+', t_clean.lower()))
    words_b = set(re.findall(r'\w+', b_clean.lower()))
    if words_t and words_b:
        overlap = len(words_t & words_b) / max(len(words_t), len(words_b))
        if overlap >= 0.65:
            return 0.65 + 0.35 * overlap
            
    c_t = set(re.findall(r'[\u4e00-\u9fa5]', t_clean))
    c_b = set(re.findall(r'[\u4e00-\u9fa5]', b_clean))
    if len(c_t) >= 2 and len(c_b) >= 2:
        overlap_c = len(c_t & c_b) / max(len(c_t), len(c_b))
        if overlap_c >= 0.65:
            return 0.65 + 0.35 * overlap_c

    return 0.0

def calculate_heading_confidence(
    toc_title: str,
    block: Dict[str, Any],
    is_target_page: bool
) -> float:
    """
    计算待测 Block 作为该章节起始标题的综合置信度。
    要求必须有显著文本相似度与标题标识，杜绝盲目切分。
    """
    content = block.get("content", "").strip()
    sim = calculate_heading_similarity(toc_title, content)
    if sim < 0.5:
        return 0.0
        
    conf = sim
    is_hd = block.get("is_heading", False)
    is_ch_hd = is_chapter_heading(content)
    
    if is_hd:
        conf += 0.15
    if is_ch_hd:
        conf += 0.15
        
    if not is_target_page:
        conf -= 0.15
        
    return min(conf, 1.0)

CONFIDENCE_THRESHOLD = 0.70
MIN_CHAPTER_BLOCKS = 2

def partition_blocks_into_chapters(
    raw_blocks: List[Dict[str, Any]],
    chapter_targets: List[Dict[str, Any]],
    lang: str = "en"
) -> List[Dict[str, Any]]:
    """
    将 raw_blocks 依照目录大纲或高置信度章节目标切分为章节。
    确保：
    1. 首章从 block 0 开始（包含前导说明、封面等）；
    2. 严格按高置信度（>= 0.70）精确识别的标题 Block 进行切分；
    3. 若未能获取精确的章节标识，坚决不切分，防止错误拆分出零碎章节；
    4. 每个 block 严格属于且仅属于一个章节，顺序连贯，无遗漏、无重复。
    """
    if not raw_blocks:
        return []
    
    if not chapter_targets or len(chapter_targets) <= 1:
        default_title = chapter_targets[0]["title"] if chapter_targets else ("文档正文" if lang == "zh" else "Document Body")
        return [{
            "title": default_title,
            "blocks": raw_blocks
        }]

    n_blocks = len(raw_blocks)
    n_targets = len(chapter_targets)
    
    valid_splits = [(0, chapter_targets[0].get("title", "Chapter 1"))]

    for i in range(1, n_targets):
        target = chapter_targets[i]
        title = target.get("title", "")
        target_page = target.get("start_page", 1)
        last_split_idx = valid_splits[-1][0]
        min_idx = last_split_idx + 1
        
        # 若已有严格提取的 block_idx（如显式识别出的真实大章节标题）
        if "block_idx" in target and target["block_idx"] >= min_idx:
            if target["block_idx"] - last_split_idx >= MIN_CHAPTER_BLOCKS:
                valid_splits.append((target["block_idx"], title))
            continue

        best_idx = None
        best_score = 0.0

        for search_pass in ("exact_page", "adjacent_pages"):
            if best_score >= 0.85:
                break
                
            for idx in range(min_idx, n_blocks):
                b = raw_blocks[idx]
                b_page = b.get("page", 1)
                is_exact = (search_pass == "exact_page")
                
                if is_exact:
                    if b_page != target_page:
                        continue
                else:
                    if abs(b_page - target_page) != 1:
                        continue
                    if b_page == target_page - 1 and idx < n_blocks - 4:
                        continue
                    if b_page == target_page + 1 and idx > min_idx + 4:
                        continue

                conf = calculate_heading_confidence(title, b, is_target_page=is_exact)
                if conf > best_score:
                    best_score = conf
                    best_idx = idx

        # 仅当获得高置信度精确标识（>= 0.70）且满足最小块间距时才切分，否则不切分
        if best_idx is not None and best_score >= CONFIDENCE_THRESHOLD:
            if best_idx - last_split_idx >= MIN_CHAPTER_BLOCKS:
                valid_splits.append((best_idx, title))

    result_chapters = []
    n_splits = len(valid_splits)
    for i in range(n_splits):
        start_idx = valid_splits[i][0]
        end_idx = valid_splits[i + 1][0] if i + 1 < n_splits else n_blocks
        ch_blocks = raw_blocks[start_idx:end_idx]
        result_chapters.append({
            "title": valid_splits[i][1],
            "blocks": ch_blocks
        })

    return result_chapters

def extract_pdf_native(
    doc_id: str,
    doc_dir: str,
    progress_callback: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    原生高保真 PDF 解析主入口：
    - 读取 PDF 物理版面与字体属性 (PyMuPDF dict)
    - 结合 find_tables 提取精准 Markdown 表格并阻断文字重合
    - 抽取原样图片并挂载至 /api/study/documents/{doc_id}/images/
    - 结合版面行距 (line pitch) 与终止符，精准合并同一段落内换行与多句
    - 连续列表/条目聚合成完整 Markdown 列表块，避免粉碎性段落影响 Chat 与翻译
    - 依据 PDF 大纲目录 (TOC) 或主标题切分章节
    """
    pdf_path = os.path.join(doc_dir, "original.pdf")
    try:
        import pymupdf
        pymupdf._get_layout = None
    except Exception:
        pass
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    toc = doc.get_toc()
    
    images_dir = os.path.join(doc_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 1. 计算全文基准字号与采样语言
    body_size = compute_body_font_size(doc, sample_pages=min(25, total_pages))
    logger.info(f"[{doc_id}] Detected dominant body font size: {body_size:.1f}pt across {total_pages} pages")

    # 预编译通用页码正则模式 (包含纯数字、破折号包裹数字 - 1 -、第X页、Page X of Y、罗马数字等)
    PAGE_NUMBER_REGEX = re.compile(
        r'^\s*([-—–·•~]*\s*\d+\s*[-—–·•~]*|(page\s+)?\d+(\s*(/|of|/共)\s*\d+)?\s*(页)?|第\s*\d+\s*页|[ivxlcdm]+)\s*$',
        re.I
    )

    # 预扫描全书边缘区域，收集高频跨页页眉与页脚文本 (出现 >= 2 次视为 Running Header/Footer)
    header_counts = Counter()
    footer_counts = Counter()
    sample_scan_pages = min(total_pages, 80)
    for p_idx in range(sample_scan_pages):
        try:
            p_obj = doc[p_idx]
            h_val = p_obj.rect.height
            for b_obj in p_obj.get_text("dict").get("blocks", []):
                if b_obj.get("type", 0) == 0:
                    for l_obj in b_obj.get("lines", []):
                        y0_val, y1_val = l_obj["bbox"][1], l_obj["bbox"][3]
                        txt_val = "".join(s.get("text", "") for s in l_obj.get("spans", [])).strip()
                        if not txt_val or len(txt_val) > 120:
                            continue
                        if y0_val < h_val * 0.11:
                            header_counts[txt_val] += 1
                        elif y1_val > h_val * 0.89:
                            footer_counts[txt_val] += 1
        except Exception:
            pass

    running_headers = {txt for txt, c in header_counts.items() if c >= 2}
    running_footers = {txt for txt, c in footer_counts.items() if c >= 2}
    logger.info(f"[{doc_id}] Detected {len(running_headers)} running headers and {len(running_footers)} running footers")

    sample_texts = []
    all_pages_blocks = []
    image_counter = 1

    for page_num_0, page in enumerate(doc):
        page_num = page_num_0 + 1
        page_rect = page.rect
        page_height = page_rect.height

        # 1. 提取本页表格并精确截图为原始高清图片
        tab_rects = merge_table_rects(page)
        page_table_items = []
        table_counter = 1
        for mr in tab_rects:
            try:
                # 预留 4pt 边缘保护边框不被削切
                clip_rect = fitz.Rect(mr.x0 - 4, mr.y0 - 4, mr.x1 + 4, mr.y1 + 4) & page_rect
                if clip_rect.width > 20 and clip_rect.height > 20:
                    pix = page.get_pixmap(clip=clip_rect, dpi=200)
                    tbl_filename = f"tbl_p{page_num:03d}_{table_counter:04d}.png"
                    tbl_save_path = os.path.join(images_dir, tbl_filename)
                    pix.save(tbl_save_path)
                    tbl_img_url = f"/api/study/documents/{doc_id}/images/{tbl_filename}"

                    page_table_items.append({
                        "bbox": (mr.x0, mr.y0, mr.x1, mr.y1),
                        "y0": mr.y0,
                        "type": "image",
                        "content": f"![Table {table_counter}]({tbl_img_url})",
                        "is_heading": False,
                        "is_list": False,
                        "no_translate": True,
                        "image_url": tbl_img_url
                    })
                    table_counter += 1
            except Exception as tbl_err:
                logger.warning(f"Failed to crop table on page {page_num}: {tbl_err}")

        # 2. 提取本页结构化内容 (文本 + 图片)
        try:
            d = page.get_text("dict")
        except Exception as dict_err:
            logger.error(f"Error getting text dict on page {page_num}: {dict_err}")
            d = {"blocks": []}

        page_image_items = []
        raw_lines = []

        for b in d.get("blocks", []):
            b_type = b.get("type", 0)
            bbox = b.get("bbox", (0, 0, 0, 0))

            # 如果该块位于表格范围内，跳过（防止表格单元格文字被打碎重出）
            if is_bbox_in_rects(bbox, tab_rects):
                continue

            # 图片块 (type == 1)
            if b_type == 1:
                img_bytes = b.get("image", b"")
                ext = b.get("ext", "png")
                if img_bytes and len(img_bytes) > 200:
                    img_filename = f"img_p{page_num:03d}_{image_counter:04d}.{ext}"
                    img_save_path = os.path.join(images_dir, img_filename)
                    try:
                        with open(img_save_path, "wb") as f_img:
                            f_img.write(img_bytes)
                        img_url = f"/api/study/documents/{doc_id}/images/{img_filename}"
                        page_image_items.append({
                            "bbox": bbox,
                            "y0": bbox[1],
                            "type": "image",
                            "content": f"![Figure {image_counter}]({img_url})",
                            "is_heading": False,
                            "is_list": False,
                            "no_translate": True,
                            "image_url": img_url
                        })
                        image_counter += 1
                    except Exception as save_err:
                        logger.warning(f"Failed to save image {img_filename}: {save_err}")
                continue

            # 文本块 (type == 0)
            if b_type == 0:
                for l in b.get("lines", []):
                    spans = l.get("spans", [])
                    if not spans:
                        continue
                    raw_text = "".join(s.get("text", "") for s in spans).strip()
                    if not raw_text:
                        continue

                    # 边缘区域判定（上边缘 11%，下边缘 11%）
                    l_y0 = l["bbox"][1]
                    l_y1 = l["bbox"][3]
                    is_in_top_margin = (l_y0 < page_height * 0.11)
                    is_in_bottom_margin = (l_y1 > page_height * 0.89)

                    # 1. 过滤页码
                    if (is_in_top_margin or is_in_bottom_margin) and PAGE_NUMBER_REGEX.match(raw_text):
                        continue
                    # 2. 过滤跨页重复页眉
                    if is_in_top_margin and raw_text in running_headers:
                        continue
                    # 3. 过滤跨页重复页脚
                    if is_in_bottom_margin and raw_text in running_footers:
                        continue

                    max_s = max((s.get("size", body_size) for s in spans), default=body_size)
                    clean_line_text = "".join(c for c in raw_text if not c.isspace())
                    bold_chars = sum(len("".join(c for c in s.get("text", "") if not c.isspace())) for s in spans if (s.get("flags", 0) & 16 or "bold" in s.get("font", "").lower()))
                    bold_ratio = (bold_chars / len(clean_line_text)) if clean_line_text else 0.0
                    raw_lines.append({
                        "text": raw_text,
                        "bbox": l["bbox"],
                        "y0": l["bbox"][1],
                        "x0": l["bbox"][0],
                        "size": max_s,
                        "bold": (bold_ratio >= 0.85),
                        "bold_ratio": bold_ratio,
                        "spans": spans
                    })
                    
        if not raw_lines and not page_table_items and not page_image_items:
            continue
            
        # 计算行距基准值
        raw_lines.sort(key=lambda l: (l["y0"], l["x0"]))
        dys = [raw_lines[i+1]["y0"] - raw_lines[i]["y0"] for i in range(len(raw_lines)-1) if raw_lines[i+1]["y0"] > raw_lines[i]["y0"] + 2]
        dys = [dy for dy in dys if 8 < dy < 80]
        median_dy = statistics.median(dys) if dys else (body_size * 1.35)
        
        # 阶段 1：行级聚合（合并折行、括号、同一段落的多句）
        items = []
        for i_l, l in enumerate(raw_lines):
            txt = l["text"]
            is_list = is_list_item(txt)
            l_type = get_list_type(txt) if is_list else ""
            is_cap = bool(CAPTION_REGEX.match(txt.strip()))
            
            # 标题层级判定
            is_hd = False
            hd_lvl = 2
            if l["size"] >= 1.5 * body_size:
                is_hd = True
                hd_lvl = 1
            elif l["size"] >= 1.25 * body_size:
                is_hd = True
                hd_lvl = 2
            elif l["size"] >= 1.14 * body_size:
                is_hd = True
                hd_lvl = 3
            elif l["bold"] and l["size"] >= 0.95 * body_size and len(txt) < 80 and not is_list and not is_cap:
                if is_chapter_heading(txt):
                    is_hd = True
                    hd_lvl = 2
                elif not is_sentence_terminal(txt):
                    # 检查下一行是否是该句的正文延续（如首句加粗的段落）
                    next_l = raw_lines[i_l + 1] if i_l + 1 < len(raw_lines) else None
                    is_followed_by_body = (
                        next_l is not None and 
                        (next_l["y0"] - l["y0"] <= 1.5 * median_dy) and
                        (not next_l["bold"] or (not (next_l["spans"][-1].get("flags", 0) & 16)))
                    )
                    if not is_followed_by_body:
                        is_hd = True
                        hd_lvl = 3
                    
            if is_hd:
                is_list = False
                l_type = ""
                
            it_obj = {
                "bbox": l["bbox"],
                "y0": l["y0"],
                "x0": l["x0"],
                "type": "text",
                "content": txt,
                "size": l["size"],
                "is_heading": is_hd,
                "heading_level": hd_lvl,
                "is_list": is_list,
                "list_type": l_type,
                "is_caption": is_cap,
                "no_translate": False,
                "image_url": ""
            }
            
            if not items:
                items.append(it_obj)
                continue
                
            prev = items[-1]
            dy = it_obj["y0"] - prev["y0"]
            
            can_merge = False
            if prev["is_heading"]:
                # 标题换行截断缝合
                prev_clean = re.sub(r'[\*_`\s]+$', '', prev["content"]).strip()
                is_wrap = (
                    prev_clean.endswith(("-", ",", "(", "[", "{", "—"))
                    or (not is_sentence_terminal(prev_clean) and it_obj.get("bold") and abs(it_obj["size"] - prev["size"]) < 2.0)
                )
                if is_wrap and not it_obj["is_heading"]:
                    can_merge = True
            elif not it_obj["is_heading"] and not prev.get("is_caption"):
                # 1. 括号未闭合，强制向后合并 (限定合理行距)
                if has_unclosed_paren(prev["content"]) and dy <= 2.5 * median_dy:
                    can_merge = True
                # 2. 上一行未结束（缺少终止标点）且当前行不是新列表项，必定为同一句自然折行 (限定合理行距，防止跨图表/大间距乱拼)
                elif not is_sentence_terminal(prev["content"]) and not it_obj["is_list"] and dy <= 2.2 * median_dy:
                    can_merge = True
                # 3. 冒号引导句衔接（紧凑行距 <= 1.4 * median_dy 时与后续正文合并，宽松行距保留独立引导句）
                elif prev["content"].rstrip().endswith((':', '：')) and dy <= 1.4 * median_dy and not it_obj.get("is_caption"):
                    can_merge = True
                # 4. 同一段落内多句合并：处于自然正文行距内，当前行不是新列表或标题
                elif (is_sentence_terminal(prev["content"]) and dy <= 1.35 * median_dy
                      and not it_obj["is_list"]
                      and not it_obj.get("is_caption")):
                    can_merge = True
                    
            if can_merge:
                prev_c = prev["content"].strip()
                curr_c = it_obj["content"].strip()
                if prev_c.endswith("-"):
                    prev["content"] = prev_c[:-1] + curr_c
                else:
                    prev["content"] = prev_c + " " + curr_c
                prev["y0"] = it_obj["y0"]
            else:
                items.append(it_obj)
                
        # 阶段 2：连续同族列表聚合为完整列表块
        grouped_text_items = []
        for it in items:
            if not grouped_text_items:
                grouped_text_items.append(it)
                continue
            prev = grouped_text_items[-1]
            can_group = (
                prev.get("is_list") and it.get("is_list")
                and not prev.get("is_heading") and not it.get("is_heading")
                and (
                    prev.get("list_type") == it.get("list_type")
                    or (prev.get("list_type") in ("decimal", "outline_decimal") and it.get("list_type") in ("decimal", "outline_decimal"))
                )
            )
            if can_group:
                prev["content"] = prev["content"] + "\n" + it["content"]
                prev["y0"] = it["y0"]
            else:
                grouped_text_items.append(it)
                
        # 格式化标题 Markdown 前缀与图表标题样式
        for it in grouped_text_items:
            if it.get("is_heading"):
                lvl = it.get("heading_level", 2)
                clean_h = re.sub(r'^[#\s]+', '', it["content"]).strip()
                it["content"] = f"{'#' * lvl} {clean_h}"
            elif it.get("is_caption"):
                c_clean = it["content"].strip()
                if not (c_clean.startswith("**") and c_clean.endswith("**")):
                    it["content"] = f"**{c_clean}**"
                
        # 汇集本页图、表、文本块并按纵坐标 y0 排序
        page_all_items = page_table_items + page_image_items + grouped_text_items
        page_all_items.sort(key=lambda x: x["y0"])
        
        clean_blocks = []
        for it in page_all_items:
            clean_blocks.append({
                "page": page_num,
                "type": it["type"],
                "content": it["content"],
                "is_heading": it.get("is_heading", False),
                "is_list": it.get("is_list", False),
                "list_type": it.get("list_type", ""),
                "no_translate": it.get("no_translate", False),
                "image_url": it.get("image_url", "")
            })
            if len(sample_texts) < 30 and it["type"] == "text":
                sample_texts.append(it["content"])
                
        all_pages_blocks.append(clean_blocks)
        
        if progress_callback:
            try:
                progress_callback(page_num, total_pages)
            except Exception as cb_e:
                logger.warning(f"Progress callback error: {cb_e}")
                
    doc.close()
    
    # 语言判断
    full_sample = " ".join(sample_texts)
    lang = detect_language(full_sample)
    
    # 跨页自然缝合
    raw_blocks = stitch_cross_page_blocks(all_pages_blocks, lang=lang)
    
    # 划分章节 (依据真实 PDF 目录 TOC，若无 TOC 则依据全局大标题切分)
    chapter_targets = []
    if toc:
        min_lvl = min((item[0] for item in toc), default=1)
        top_toc = [item for item in toc if item[0] == min_lvl]
        # 若根层级只有 1 个大项（例如单章节 PDF: Chapter 6...），且存在子层级，则下探使用 Level 2 作为章节切分
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
                # 保证第一章从第 1 页开始包含前导说明
                start_p = 1 if i == 0 else max(1, top_toc[i][2])
                chapter_targets.append({
                    "title": title,
                    "start_page": start_p
                })

    # 若无 TOC 大纲且页数较多（>= 6页），尝试从正文提取明确大章节标题（排除模糊短标题，防零碎切分）
    if not chapter_targets and total_pages >= 6:
        detected_headings = []
        for idx, b in enumerate(raw_blocks):
            if b.get("is_heading") and b.get("heading_level", 2) <= 2:
                c = b.get("content", "").strip()
                c_clean = re.sub(r'^[#\s]+', '', c).strip()
                # 仅匹配具备明确章节标识的强标题，严禁仅凭字号短文本粗暴切分
                is_strict_chapter = (
                    is_chapter_heading(c_clean)
                    or bool(re.match(r'^(第[一二三四五六七八九十0-9]+[章篇部分]|Chapter\s+[\dIVX]+|Section\s+[\dIVX]+|Part\s+[\dIVX]+|前\s*言|Preface|致\s*谢|附录|附件\s*[0-9一二三四五六七八九十A-Za-z]+)', c_clean, re.I))
                )
                if is_strict_chapter:
                    p_num = b["page"]
                    # 避免同页或极小间距产生破碎章节
                    if not detected_headings or (idx - detected_headings[-1]["block_idx"] >= 4 and p_num - detected_headings[-1]["start_page"] >= 1):
                        detected_headings.append({
                            "title": c_clean,
                            "start_page": p_num,
                            "block_idx": idx
                        })

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
            if b_type in ("image", "table"):
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
            else:
                raw_text = b["content"].strip()
                if not raw_text:
                    continue
                is_para_zh = is_predominantly_target_lang(raw_text, "zh")
                ch_paragraphs.append({
                    "id": f"p_{ch_idx:03d}_{para_counter:04d}",
                    "page": b["page"],
                    "type": "text",
                    "english": raw_text,
                    "chinese": "",
                    "status": "completed" if (lang == "zh" or is_para_zh) else "pending",
                    "no_translate": is_para_zh,
                    "image_url": ""
                })
                para_counter += 1

        chapters.append({
            "chapter_id": f"ch_{ch_idx:03d}",
            "title": ch_info["title"],
            "paragraphs": ch_paragraphs
        })
        
    logger.info(f"[{doc_id}] Native parsing completed: {len(chapters)} chapters, {para_counter-1} paragraphs, language={lang}")
    return lang, chapters

def render_chapter_markdown(chapter: Dict[str, Any], language: str = "en") -> str:
    """
    将章节渲染为研学系统的标准 Markdown。
    """
    lines = []
    title = chapter.get("title", "Chapter")
    lines.append(f"# {title}\n\n")
    
    # 1. 导读与总览
    header_notes = chapter.get("header_notes", [])
    if header_notes:
        lines.append("> 📌 **【全章导读与核心总览】**\n")
        for n in header_notes:
            content = n.get("content", "").replace("\n", "\n> ")
            lines.append(f"> {content}\n")
        lines.append("\n---\n\n")
        
    # 2. 段落主体
    for p in chapter.get("paragraphs", []):
        eng = p.get("english", "").strip()
        cn = p.get("chinese", "").strip()
        notes = p.get("notes", [])
        
        if p.get("type") == "image":
            lines.append(f"{eng}\n\n")
        elif language == "zh":
            lines.append(f"{eng}\n\n")
        else:
            lines.append(f"{eng}\n\n")
            if cn:
                cn_formatted = cn.replace("\n", "\n> ")
                lines.append(f"> {cn_formatted}\n\n")
                
        # 研读注解
        if notes:
            lines.append("> 💡 **【研读注解】**\n")
            for n in notes:
                c_clean = n.get("content", "").replace("\n", "\n> ")
                lines.append(f"> {c_clean}\n")
            lines.append("\n")
            
        lines.append("---\n\n")
        
    # 3. 尾部复盘
    footer_notes = chapter.get("footer_notes", [])
    if footer_notes:
        lines.append("> 🎯 **【本章回顾与考点复盘】**\n")
        for n in footer_notes:
            content = n.get("content", "").replace("\n", "\n> ")
            lines.append(f"> {content}\n")
        lines.append("\n---\n\n")
        
    return "".join(lines)
