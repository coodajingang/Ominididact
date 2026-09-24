import os
import re
import zipfile
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional
from urllib.parse import unquote
from bs4 import BeautifulSoup

from study.pdf_parser import detect_language, repair_english_paragraph
from study.text_parser import parse_markdown_content

logger = logging.getLogger("study-epub-parser")

# XML Namespaces commonly used in EPUB
NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml"
}

def _clean_html_to_markdown_blocks(soup: BeautifulSoup, base_img_dir: str, doc_id: str = "") -> str:
    """
    Converts a chapter HTML/XHTML DOM into clean, structured markdown.
    Preserves headings (#, ##), paragraphs, blockquotes, code blocks, tables, and images.
    """
    # Remove unwanted tags
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    body = soup.find("body") or soup
    lines = []

    for elem in body.children:
        if isinstance(elem, str):
            text = elem.strip()
            if text:
                lines.append(text + "\n")
            continue

        tag_name = elem.name.lower() if elem.name else ""

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            heading_text = elem.get_text().strip()
            if heading_text:
                lines.append(f"{'#' * level} {heading_text}\n")
        elif tag_name == "p":
            # Check for embedded images in p
            imgs = elem.find_all("img")
            p_text = elem.get_text().strip()
            if imgs:
                for img in imgs:
                    src = img.get("src", "")
                    alt = img.get("alt", "") or "image"
                    if src:
                        if src.startswith("/api/study/documents/") or src.startswith("http://") or src.startswith("https://"):
                            lines.append(f"![{alt}]({src})\n")
                        else:
                            filename = os.path.basename(unquote(src))
                            if doc_id:
                                lines.append(f"![{alt}](/api/study/documents/{doc_id}/images/{filename})\n")
                            else:
                                lines.append(f"![{alt}](./images/{filename})\n")
            if p_text:
                lines.append(f"{p_text}\n")
        elif tag_name in ("pre", "code"):
            code_text = elem.get_text().strip()
            lines.append(f"```\n{code_text}\n```\n")
        elif tag_name in ("ul", "ol"):
            for li in elem.find_all("li", recursive=False):
                li_text = li.get_text().strip()
                if li_text:
                    lines.append(f"- {li_text}")
            lines.append("")
        elif tag_name == "blockquote":
            b_text = elem.get_text().strip()
            if b_text:
                lines.append(f"> {b_text}\n")
        elif tag_name == "table":
            # Extract simple markdown table
            rows = []
            for tr in elem.find_all("tr"):
                cells = [c.get_text().strip().replace("\n", " ") for c in tr.find_all(["td", "th"])]
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
            if rows:
                if len(rows) > 1:
                    header_sep = "| " + " | ".join(["---"] * len(rows[0].split("|")[1:-1])) + " |"
                    rows.insert(1, header_sep)
                lines.extend(rows)
                lines.append("")
        elif tag_name == "img":
            src = elem.get("src", "")
            alt = elem.get("alt", "") or "image"
            if src:
                if src.startswith("/api/study/documents/") or src.startswith("http://") or src.startswith("https://"):
                    lines.append(f"![{alt}]({src})\n")
                else:
                    filename = os.path.basename(unquote(src))
                    if doc_id:
                        lines.append(f"![{alt}](/api/study/documents/{doc_id}/images/{filename})\n")
                    else:
                        lines.append(f"![{alt}](./images/{filename})\n")
        else:
            text = elem.get_text().strip()
            if text:
                lines.append(f"{text}\n")

    return "\n".join(lines).strip()

def inspect_epub(epub_path: str) -> Dict[str, Any]:
    """
    Inspects an EPUB file to extract book title, author, cover, language, and chapter outline.
    """
    if not zipfile.is_zipfile(epub_path):
        raise ValueError("Provided file is not a valid ZIP/EPUB container")

    with zipfile.ZipFile(epub_path, "r") as zf:
        # 1. Read META-INF/container.xml to find the OPF file
        try:
            container_xml = zf.read("META-INF/container.xml")
            tree = ET.fromstring(container_xml)
            rootfile_el = tree.find(".//container:rootfile", NS)
            if rootfile_el is None:
                rootfile_el = tree.find(".//rootfile")
            if rootfile_el is None or "full-path" not in rootfile_el.attrib:
                raise ValueError("Cannot locate full-path in container.xml")
            opf_path = rootfile_el.attrib["full-path"]
        except Exception as e:
            # Fallback: look for *.opf file in root or OEBPS
            candidates = [f for f in zf.namelist() if f.endswith(".opf")]
            if not candidates:
                raise ValueError(f"Failed to locate OPF in EPUB: {e}")
            opf_path = candidates[0]

        opf_dir = os.path.dirname(opf_path)
        opf_data = zf.read(opf_path)
        opf_tree = ET.fromstring(opf_data)

        # 2. Extract Metadata
        title = "Untitled E-Book"
        title_el = opf_tree.find(".//dc:title", NS)
        if title_el is None:
            title_el = opf_tree.find(".//title")
        if title_el is not None and title_el.text:
            title = title_el.text.strip()

        author = ""
        creator_el = opf_tree.find(".//dc:creator", NS)
        if creator_el is None:
            creator_el = opf_tree.find(".//creator")
        if creator_el is not None and creator_el.text:
            author = creator_el.text.strip()

        lang = "en"
        lang_el = opf_tree.find(".//dc:language", NS)
        if lang_el is None:
            lang_el = opf_tree.find(".//language")
        if lang_el is not None and lang_el.text:
            lang_raw = lang_el.text.strip().lower()
            lang = "zh" if ("zh" in lang_raw or "chi" in lang_raw) else "en"

        # 3. Extract Manifest
        manifest_items = {}
        for item in opf_tree.findall(".//opf:item", NS) or opf_tree.findall(".//item"):
            item_id = item.attrib.get("id")
            item_href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")
            if item_id and item_href:
                manifest_items[item_id] = {
                    "href": item_href,
                    "media_type": media_type
                }

        # 4. Extract Spine (reading order)
        spine_refs = []
        for itemref in opf_tree.findall(".//opf:itemref", NS) or opf_tree.findall(".//itemref"):
            idref = itemref.attrib.get("idref")
            if idref and idref in manifest_items:
                href = manifest_items[idref]["href"]
                # Resolve relative to OPF dir
                full_href = os.path.normpath(os.path.join(opf_dir, href)).replace("\\", "/")
                spine_refs.append({
                    "id": idref,
                    "href": full_href,
                    "media_type": manifest_items[idref]["media_type"]
                })

        # 5. Extract TOC (NCX or NAV)
        toc_titles = {}
        ncx_candidates = [f for f in zf.namelist() if f.endswith(".ncx")]
        if ncx_candidates:
            try:
                ncx_data = zf.read(ncx_candidates[0])
                ncx_tree = ET.fromstring(ncx_data)
                for navpoint in ncx_tree.findall(".//ncx:navPoint", NS) or ncx_tree.findall(".//navPoint"):
                    text_el = navpoint.find(".//ncx:text", NS)
                    if text_el is None:
                        text_el = navpoint.find(".//text")
                    content_el = navpoint.find(".//ncx:content", NS)
                    if content_el is None:
                        content_el = navpoint.find(".//content")
                    if text_el is not None and content_el is not None:
                        src = content_el.attrib.get("src", "").split("#")[0]
                        nav_title = text_el.text.strip() if text_el.text else ""
                        if src and nav_title:
                            norm_src = os.path.normpath(os.path.join(os.path.dirname(ncx_candidates[0]), src)).replace("\\", "/")
                            toc_titles[norm_src] = nav_title
            except Exception as e:
                logger.warning(f"Failed to parse NCX TOC: {e}")

        chapters = []
        for idx, item in enumerate(spine_refs, 1):
            ch_title = toc_titles.get(item["href"])
            if not ch_title:
                ch_title = f"Chapter {idx}"
            chapters.append({
                "index": idx,
                "title": ch_title,
                "href": item["href"]
            })

        return {
            "title": title,
            "author": author,
            "language": lang,
            "chapters_count": len(chapters),
            "chapters": chapters
        }

def extract_epub_content(
    doc_id: str,
    doc_dir: str,
    filename: str,
    progress_callback: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts structured chapters and paragraphs from an EPUB file into Omnididact format.
    Extracts images into `doc_dir/images`.
    """
    ext = os.path.splitext(filename)[1].lower()
    epub_path = os.path.join(doc_dir, f"original{ext}")
    if not os.path.isfile(epub_path):
        candidate = os.path.join(doc_dir, filename)
        if os.path.isfile(candidate):
            epub_path = candidate

    img_out_dir = os.path.join(doc_dir, "images")
    os.makedirs(img_out_dir, exist_ok=True)

    info = inspect_epub(epub_path)
    total_chapters = len(info["chapters"])
    detected_lang = info["language"]

    chapters = []
    para_counter = 1

    with zipfile.ZipFile(epub_path, "r") as zf:
        # Extract all image assets first
        for name in zf.namelist():
            lower = name.lower()
            if any(lower.endswith(img_ext) for img_ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                img_name = os.path.basename(name)
                if img_name:
                    target_img_path = os.path.join(img_out_dir, img_name)
                    with open(target_img_path, "wb") as f_out:
                        f_out.write(zf.read(name))

        for ch_idx, ch_info in enumerate(info["chapters"], 1):
            if progress_callback:
                try:
                    progress_callback(ch_idx, total_chapters)
                except Exception:
                    pass

            href = ch_info["href"]
            if href not in zf.namelist():
                # Try relative search
                matched = [n for n in zf.namelist() if n.endswith(href)]
                if matched:
                    href = matched[0]
                else:
                    continue

            html_content = zf.read(href).decode("utf-8", errors="replace")
            soup = BeautifulSoup(html_content, "html.parser")

            # If chapter title is default 'Chapter X', try to extract from <title> or <h1>
            ch_title = ch_info["title"]
            if ch_title.startswith("Chapter "):
                h1 = soup.find(["h1", "h2"])
                if h1 and h1.get_text().strip():
                    ch_title = h1.get_text().strip()
                elif soup.title and soup.title.get_text().strip():
                    ch_title = soup.title.get_text().strip()

            markdown_text = _clean_html_to_markdown_blocks(soup, img_out_dir)
            if not markdown_text.strip():
                continue

            # Parse markdown into paragraph items
            _, parsed_chapters = parse_markdown_content(markdown_text, doc_id)

            ch_paras = []
            for sub_ch in parsed_chapters:
                for p in sub_ch.get("paragraphs", []):
                    p["id"] = f"p_{ch_idx:03d}_{para_counter:04d}"
                    p["chapter_id"] = f"ch_{ch_idx:03d}"
                    p["order"] = para_counter
                    para_counter += 1
                    ch_paras.append(p)

            if ch_paras:
                chapters.append({
                    "chapter_id": f"ch_{ch_idx:03d}",
                    "title": ch_title,
                    "paragraphs": ch_paras
                })

    if not chapters:
        # Fallback if nothing extracted
        chapters.append({
            "chapter_id": "ch_001",
            "title": info["title"] or "正文",
            "paragraphs": []
        })

    return detected_lang, chapters
