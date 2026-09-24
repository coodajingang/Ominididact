import os
import re
import zipfile
import logging
import shutil
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional

from study.pdf_parser import detect_language
from study.text_parser import decode_text_bytes, parse_markdown_content

logger = logging.getLogger("study-folder-importer")

def _normalize_folder_markdown_images(md_text: str, available_images: Dict[str, str], doc_id: str) -> str:
    """
    Normalizes both <img ... src="..."> tags and ![alt](...) markdown links
    to /api/study/documents/{doc_id}/images/{filename} if filename matches extracted images.
    """
    if not md_text or not available_images:
        return md_text

    # 1. Replace <img ... src="..." ...>
    def replace_img_tag(match):
        full_tag = match.group(0)
        src = match.group(1)
        base = os.path.basename(urllib.parse.unquote(src)).lower()
        if base in available_images:
            real_name = available_images[base]
            new_src = f"/api/study/documents/{doc_id}/images/{real_name}"
            return full_tag.replace(src, new_src)
        return full_tag

    normalized = re.sub(r'<img[^>]+src=[\"\']([^\"\']+)[\"\'][^>]*>', replace_img_tag, md_text, flags=re.IGNORECASE)

    # 2. Replace ![alt](path)
    def replace_md_img(match):
        alt = match.group(1)
        target = match.group(2).strip()
        base = os.path.basename(urllib.parse.unquote(target.split()[0])).lower()
        if base in available_images:
            real_name = available_images[base]
            new_target = f"/api/study/documents/{doc_id}/images/{real_name}"
            return f"![{alt}]({new_target})"
        return match.group(0)

    normalized = re.sub(r'!\[(.*?)\]\((.*?)\)', replace_md_img, normalized)
    return normalized

def parse_summary_md(summary_text: str) -> List[Dict[str, str]]:
    """
    Parses GitBook or Docsify style SUMMARY.md / _sidebar.md:
    * [0x05a Platform Overview](Document/0x05a-Platform-Overview.md)
    * [Chapter 1](chapter1.md)
    """
    items = []
    for line in summary_text.splitlines():
        line = line.strip()
        m = re.search(r'\[(.*?)\]\((.*?)\)', line)
        if m:
            title = m.group(1).strip()
            path = m.group(2).strip().split("#")[0]
            if path.endswith((".md", ".markdown")):
                items.append({"title": title, "path": path})
    return items

def parse_mkdocs_nav(yaml_text: str) -> List[Dict[str, str]]:
    """
    Extracts navigation items from mkdocs.yml (nav: section) without heavy PyYAML dependency.
    """
    items = []
    in_nav = False
    for line in yaml_text.splitlines():
        if re.match(r'^\s*nav:\s*$', line):
            in_nav = True
            continue
        if in_nav:
            # If line is not indented, nav section ended
            if line and not line.startswith(" ") and not line.startswith("\t"):
                break
            # Match lines like: - 'Title': 'file.md' or - Title: file.md
            m = re.search(r'-\s*(?:["\']?([^"\':]+)["\']?\s*:\s*)?["\']?([^"\']+\.md)["\']?', line)
            if m:
                title = (m.group(1) or "").strip()
                path = m.group(2).strip()
                if not title:
                    title = os.path.splitext(os.path.basename(path))[0]
                items.append({"title": title, "path": path})
    return items

def natural_sort_key(s: str):
    """Sort strings with numbers naturally (e.g., '1', '2', '10' instead of '1', '10', '2')."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def extract_folder_content(
    doc_id: str,
    doc_dir: str,
    filename: str,
    progress_callback: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts structured chapters and paragraphs from a zipped Markdown project or folder.
    Extracts all images to `doc_dir/images`.
    """
    ext = os.path.splitext(filename)[1].lower()
    zip_path = os.path.join(doc_dir, f"original{ext}")
    if not os.path.isfile(zip_path):
        candidate = os.path.join(doc_dir, filename)
        if os.path.isfile(candidate):
            zip_path = candidate

    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"File {filename} is not a valid zip archive")

    extract_tmp_dir = os.path.join(doc_dir, "extracted_folder")
    os.makedirs(extract_tmp_dir, exist_ok=True)
    img_out_dir = os.path.join(doc_dir, "images")
    os.makedirs(img_out_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_tmp_dir)

    # 1. Move all extracted images to doc_dir/images
    for root, _, files in os.walk(extract_tmp_dir):
        for f in files:
            lower = f.lower()
            if any(lower.endswith(img_ext) for img_ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                src_path = os.path.join(root, f)
                dst_path = os.path.join(img_out_dir, f)
                try:
                    shutil.copy2(src_path, dst_path)
                except Exception:
                    pass

    available_images = {os.path.basename(f).lower(): f for f in os.listdir(img_out_dir)}

    # 2. Look for outline definitions (SUMMARY.md, _sidebar.md, mkdocs.yml)
    ordered_files = []
    summary_candidates = ["SUMMARY.md", "summary.md", "_sidebar.md"]
    found_summary = None
    for root, _, files in os.walk(extract_tmp_dir):
        for cand in summary_candidates:
            if cand in files:
                found_summary = os.path.join(root, cand)
                break
        if found_summary:
            break

    if found_summary:
        try:
            with open(found_summary, "rb") as f:
                content = decode_text_bytes(f.read())
            items = parse_summary_md(content)
            base_dir = os.path.dirname(found_summary)
            for it in items:
                resolved = os.path.normpath(os.path.join(base_dir, it["path"]))
                if os.path.isfile(resolved):
                    ordered_files.append({"title": it["title"], "file_path": resolved})
        except Exception as e:
            logger.warning(f"Error parsing summary: {e}")

    # If no summary, look for mkdocs.yml
    if not ordered_files:
        mkdocs_path = os.path.join(extract_tmp_dir, "mkdocs.yml")
        if os.path.isfile(mkdocs_path):
            try:
                with open(mkdocs_path, "rb") as f:
                    content = decode_text_bytes(f.read())
                items = parse_mkdocs_nav(content)
                for it in items:
                    # mkdocs docs_dir is usually docs/ or root
                    for cand_prefix in ("", "docs", "Document"):
                        cand = os.path.normpath(os.path.join(extract_tmp_dir, cand_prefix, it["path"]))
                        if os.path.isfile(cand):
                            ordered_files.append({"title": it["title"], "file_path": cand})
                            break
            except Exception as e:
                logger.warning(f"Error parsing mkdocs.yml: {e}")

    # Fallback: scan all .md files and natural-sort them
    if not ordered_files:
        all_mds = []
        for root, _, files in os.walk(extract_tmp_dir):
            for f in files:
                if f.lower().endswith((".md", ".markdown")):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, extract_tmp_dir)
                    all_mds.append((f, full_p, rel_p))

        # Put README.md first if present, then sort by natural filename
        all_mds.sort(key=lambda x: (0 if "readme" in x[0].lower() else 1, natural_sort_key(x[2])))
        for fname, fpath, relp in all_mds:
            title = os.path.splitext(fname)[0].replace("-", " ").replace("_", " ").title()
            ordered_files.append({"title": title, "file_path": fpath})

    if not ordered_files:
        raise ValueError("Zip 压缩包内未找到任何 Markdown (.md) 文件！")

    chapters = []
    para_counter = 1
    detected_langs = []

    total_files = len(ordered_files)
    for ch_idx, item in enumerate(ordered_files, 1):
        if progress_callback:
            try:
                progress_callback(ch_idx, total_files)
            except Exception:
                pass

        try:
            with open(item["file_path"], "rb") as f:
                raw_bytes = f.read()
            md_text = decode_text_bytes(raw_bytes)
        except Exception as e:
            logger.warning(f"Failed to read {item['file_path']}: {e}")
            continue

        if not md_text.strip():
            continue

        md_text = _normalize_folder_markdown_images(md_text, available_images, doc_id)
        file_lang, parsed_chapters = parse_markdown_content(md_text, doc_id)
        detected_langs.append(file_lang)

        # Check if first line of markdown is H1 title, if so adopt it as chapter title
        ch_title = item["title"]
        first_line = md_text.strip().split("\n")[0].strip()
        if first_line.startswith("# "):
            h1_title = first_line[2:].strip()
            if h1_title:
                ch_title = h1_title

        # Combine blocks of this file into this chapter
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

    # Cleanup extract tmp dir
    try:
        shutil.rmtree(extract_tmp_dir, ignore_errors=True)
    except Exception:
        pass

    final_lang = "zh" if detected_langs.count("zh") > len(detected_langs) / 2 else "en"
    return final_lang, chapters
