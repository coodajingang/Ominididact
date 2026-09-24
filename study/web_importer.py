import os
import re
import hashlib
import logging
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional
import httpx
from bs4 import BeautifulSoup

from study.pdf_parser import detect_language
from study.text_parser import parse_markdown_content

logger = logging.getLogger("study-web-importer")

# Standard desktop browser user agent
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

async def fetch_url_html(url: str, timeout: float = 15.0) -> str:
    """Fetches raw HTML string with standard headers and redirect following."""
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    client_timeout = httpx.Timeout(timeout, connect=8.0)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=client_timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

def _extract_sidebar_links(soup: BeautifulSoup, base_url: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Sniffs documentation sidebars (MkDocs, Docusaurus, GitBook, Sphinx).
    Deduplicates by distinct page URL, detects active section/module, and preserves reading order.
    Returns (section_name, list_of_chapters).
    """
    base_parsed = urllib.parse.urlparse(base_url)
    base_domain = base_parsed.netloc.lower()
    norm_base = urllib.parse.urlunparse((base_parsed.scheme, base_parsed.netloc, base_parsed.path, "", "", "")).rstrip("/")

    # Detect active section title (e.g. 'Android Security Testing' in MkDocs)
    active_section_name = ""
    active_nested = soup.find_all(class_=lambda x: x and 'md-nav__item--nested' in x and 'md-nav__item--active' in x)
    active_container = None
    if active_nested:
        active_container = active_nested[-1]
        label = active_container.find(class_='md-nav__link')
        if label:
            active_section_name = label.get_text().strip()

    # Search candidates for sidebar navigation
    candidates = []
    if active_container:
        candidates.append(active_container)

    primary_nav = soup.find("nav", class_=re.compile(r"md-nav--primary|md-sidebar--primary"))
    if primary_nav:
        candidates.append(primary_nav)

    candidates.extend([
        soup.find("nav", class_=re.compile(r"md-nav")),
        soup.find("nav", class_=re.compile(r"menu")),
        soup.find("div", class_=re.compile(r"book-summary")),
        soup.find("ul", class_=re.compile(r"summary")),
        soup.find("div", class_=re.compile(r"wy-side-scroll")),
        soup.find("aside"),
        soup.find("nav")
    ])

    seen_urls = set()
    links = []

    # If we found an active container, first collect items belonging to the current module/section
    section_urls = set()
    if active_container:
        for a in active_container.find_all("a", href=True):
            raw_href = a["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
                continue
            abs_url = urllib.parse.urljoin(base_url, raw_href)
            parsed = urllib.parse.urlparse(abs_url)
            clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).rstrip("/")
            if parsed.netloc.lower() == base_domain:
                section_urls.add(clean_url)

    # Always ensure the input URL itself is included
    if norm_base:
        section_urls.add(norm_base)

    for container in candidates:
        if not container:
            continue

        for a in container.find_all("a", href=True):
            raw_href = a["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
                continue

            abs_url = urllib.parse.urljoin(base_url, raw_href)
            parsed = urllib.parse.urlparse(abs_url)
            if parsed.netloc.lower() != base_domain:
                continue

            clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).rstrip("/")
            if clean_url in seen_urls:
                continue

            title = a.get_text().strip()
            title = re.sub(r'\s+', ' ', title).strip()
            # Ignore empty or pure anchor labels
            if not title or title.lower() in ("table of contents", "目录"):
                continue

            seen_urls.add(clean_url)
            is_in_section = clean_url in section_urls
            is_current = (clean_url == norm_base)

            links.append({
                "title": title,
                "url": clean_url,
                "in_section": is_in_section,
                "is_current": is_current,
                "selected": is_in_section  # Auto-check items belonging to the active section
            })

        if len(links) >= 2:
            break

    # If links were found, ensure the current page title is accurate
    if links:
        # Sort so that items in the active section appear first, or maintain sequential order
        pass

    return active_section_name, links

async def inspect_web_series(url: str) -> Dict[str, Any]:
    """
    Inspects a given documentation URL to detect if it belongs to a series or is a standalone page.
    Returns page title, site name, whether it's a series, and list of outline chapters.
    """
    html = await fetch_url_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # Extract Site / Page Title
    page_title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        page_title = og_title["content"].strip()
    elif soup.title and soup.title.get_text().strip():
        page_title = soup.title.get_text().strip()
    elif soup.find("h1"):
        page_title = soup.find("h1").get_text().strip()
    else:
        page_title = "网页研学材料"

    # Clean site title (e.g. '0x05a... - OWASP MASTG' -> site: 'OWASP MASTG')
    site_name = page_title
    if " - " in page_title:
        parts = page_title.split(" - ")
        page_title = parts[0].strip()
        site_name = parts[-1].strip()
    elif " | " in page_title:
        parts = page_title.split(" | ")
        page_title = parts[0].strip()
        site_name = parts[-1].strip()

    section_name, sidebar_links = _extract_sidebar_links(soup, url)

    if len(sidebar_links) >= 2:
        is_series = True
        chapters = []
        for idx, item in enumerate(sidebar_links, 1):
            chapters.append({
                "index": idx,
                "title": item["title"],
                "url": item["url"],
                "in_section": item.get("in_section", False),
                "is_current": item.get("is_current", False),
                "selected": item.get("selected", True)
            })
    else:
        is_series = False
        chapters = [{
            "index": 1,
            "title": page_title,
            "url": url,
            "in_section": True,
            "is_current": True,
            "selected": True
        }]

    # Recommend document title
    suggested_title = f"{site_name}: {section_name}" if section_name and section_name != site_name else (page_title or site_name)

    return {
        "url": url,
        "site_name": site_name,
        "section_name": section_name,
        "suggested_title": suggested_title,
        "title": page_title,
        "is_series": is_series,
        "total_chapters": len(chapters),
        "chapters": chapters
    }

async def fetch_and_clean_page(url: str, img_dir: str, doc_id: str = "") -> Tuple[str, str]:
    """
    Fetches a page, extracts the clean Markdown body (excluding header/sidebar/footer/ads),
    resolves all relative/absolute images, downloads them to `img_dir`, and replaces image links.
    """
    html = await fetch_url_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = ""
    h1 = soup.find("h1")
    if h1 and h1.get_text().strip():
        title = h1.get_text().strip()
    elif soup.title and soup.title.get_text().strip():
        title = soup.title.get_text().strip().split(" - ")[0].split(" | ")[0].strip()
    else:
        title = "正文"
    title = title.rstrip("¶").strip()

    # Pre-clean noisy tags
    for tag in soup(["script", "style", "nav", "aside", "header", "footer", "meta", "link", "noscript"]):
        tag.decompose()

    # Target primary content container
    content_container = (
        soup.find("article") or
        soup.find("main") or
        soup.find("div", class_=re.compile(r"md-content__inner|markdown-body|post-content|article-content|entry-content")) or
        soup.find("body") or
        soup
    )

    os.makedirs(img_dir, exist_ok=True)

    # 1. Pre-process and download all <img> tags in the DOM
    img_timeout = httpx.Timeout(6.0, connect=3.0)
    async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}, follow_redirects=True, timeout=img_timeout) as client:
        for img in content_container.find_all("img")[:40]:
            raw_src = img.get("src") or img.get("data-src") or ""
            if not raw_src:
                continue

            # Skip tracking pixels
            if "scarf.sh" in raw_src or "badge" in raw_src.lower():
                img.decompose()
                continue

            abs_img_url = urllib.parse.urljoin(url, raw_src)
            try:
                parsed_p = urllib.parse.urlparse(abs_img_url).path
                base_name = os.path.basename(parsed_p)
                ext = os.path.splitext(base_name)[1]
                if not ext or len(ext) > 5 or ext.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
                    ext = ".png"

                clean_name = re.sub(r'[^a-zA-Z0-9_\-.]', '_', os.path.splitext(base_name)[0]) or "img"
                url_hash = hashlib.md5(abs_img_url.encode("utf-8")).hexdigest()[:8]
                local_fname = f"{clean_name}_{url_hash}{ext}"
                local_fpath = os.path.join(img_dir, local_fname)

                is_saved = os.path.exists(local_fpath)
                if not is_saved:
                    try:
                        resp = await client.get(abs_img_url)
                        if resp.status_code == 200 and len(resp.content) > 50:
                            with open(local_fpath, "wb") as f_img:
                                f_img.write(resp.content)
                            is_saved = True
                    except Exception:
                        pass

                if is_saved:
                    img["src"] = f"/api/study/documents/{doc_id}/images/{local_fname}" if doc_id else f"./images/{local_fname}"
                else:
                    # Fallback to direct absolute remote URL so the image remains visible online
                    img["src"] = abs_img_url
            except Exception as e:
                logger.debug(f"Failed to fetch image {abs_img_url} from {url}: {e}")
                img["src"] = abs_img_url

        # 2. Extract clean Markdown from content container
        from study.epub_parser import _clean_html_to_markdown_blocks
        markdown_text = _clean_html_to_markdown_blocks(content_container, img_dir, doc_id=doc_id)

        # 3. Post-process any remaining markdown image patterns ![alt](path)
        img_matches = list(re.finditer(r'!\[(.*?)\]\((.*?)\)', markdown_text))[:30]
        for m in img_matches:
            alt = m.group(1)
            target = m.group(2).strip()
            if not target or target.startswith("/api/study/documents/"):
                continue

            abs_url = urllib.parse.urljoin(url, target)
            try:
                base_name = os.path.basename(urllib.parse.urlparse(abs_url).path)
                ext = os.path.splitext(base_name)[1]
                if not ext or len(ext) > 5:
                    ext = ".png"
                clean_name = re.sub(r'[^a-zA-Z0-9_\-.]', '_', os.path.splitext(base_name)[0]) or "img"
                url_hash = hashlib.md5(abs_url.encode("utf-8")).hexdigest()[:8]
                local_fname = f"{clean_name}_{url_hash}{ext}"
                local_fpath = os.path.join(img_dir, local_fname)

                is_saved = os.path.exists(local_fpath)
                if not is_saved:
                    try:
                        resp = await client.get(abs_url)
                        if resp.status_code == 200 and len(resp.content) > 50:
                            with open(local_fpath, "wb") as f_img:
                                f_img.write(resp.content)
                            is_saved = True
                    except Exception:
                        pass

                if is_saved:
                    replacement = f"/api/study/documents/{doc_id}/images/{local_fname}" if doc_id else f"./images/{local_fname}"
                else:
                    replacement = abs_url

                markdown_text = markdown_text.replace(f"![{alt}]({target})", f"![{alt}]({replacement})")
            except Exception as e:
                logger.debug(f"Failed to resolve and download markdown image {target}: {e}")

    return title, markdown_text

async def extract_web_series_content(
    doc_id: str,
    doc_dir: str,
    meta: Dict[str, Any],
    progress_callback: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Crawls and extracts selected web pages into a multi-chapter Omnididact document.
    Executes with concurrent workers (Semaphore) to dramatically accelerate crawling (8x faster),
    while strictly guaranteeing the exact original chapter order and providing automatic retry.
    """
    import asyncio

    web_config = meta.get("web_config", {})
    chapters_to_fetch = web_config.get("selected_chapters", [])
    if not chapters_to_fetch:
        chapters_to_fetch = [{"title": meta.get("filename", "Web Content"), "url": meta.get("source_url", "")}]

    img_out_dir = os.path.join(doc_dir, "images")
    os.makedirs(img_out_dir, exist_ok=True)

    total_ch = len(chapters_to_fetch)
    # Pre-allocate array of size total_ch to store results at their exact original index
    ordered_results: List[Optional[Dict[str, Any]]] = [None] * total_ch
    completed_count = 0

    # Concurrency limit (8 parallel workers avoids overwhelming targets while achieving ~8x speedup)
    max_concurrency = min(8, max(2, total_ch))
    sem = asyncio.Semaphore(max_concurrency)

    async def fetch_worker(ch_idx: int, item: Dict[str, Any]):
        nonlocal completed_count
        url = item.get("url")
        ch_title_hint = item.get("title") or f"章节 {ch_idx + 1}"

        if not url:
            completed_count += 1
            return

        async with sem:
            ch_title = ch_title_hint
            md_content = ""
            fetch_success = False

            # Automatic retry up to 2 attempts for transient connection jitter
            for attempt in range(2):
                try:
                    ch_title, md_content = await asyncio.wait_for(
                        fetch_and_clean_page(url, img_out_dir, doc_id=doc_id),
                        timeout=25.0
                    )
                    if not ch_title or ch_title == "正文":
                        ch_title = ch_title_hint
                    fetch_success = True
                    break
                except asyncio.TimeoutError:
                    if attempt == 0:
                        await asyncio.sleep(0.8)
                        continue
                    logger.warning(f"Timeout (25s) fetching chapter {ch_idx + 1} ({ch_title_hint}) from {url}")
                    md_content = f"> ⚠️ 抓取此章节内容时超时（已自动重试）。可在阅读时点击下方重新抓取，或直接访问原网页。\n\n🔗 **原始链接**: [{url}]({url})"
                except Exception as e:
                    if attempt == 0:
                        await asyncio.sleep(0.8)
                        continue
                    logger.error(f"Error fetching chapter {ch_idx + 1} from {url}: {e}")
                    md_content = f"> ⚠️ 抓取此章节内容时遇到网络错误（已自动重试）: {str(e)}\n\n🔗 **原始链接**: [{url}]({url})"

            ch_lang, parsed_chapters = parse_markdown_content(md_content, doc_id)
            
            # Store at exact original position to preserve order
            ordered_results[ch_idx] = {
                "idx": ch_idx,
                "title": ch_title,
                "url": url,
                "lang": ch_lang,
                "fetch_success": fetch_success,
                "parsed_chapters": parsed_chapters
            }

            completed_count += 1
            if progress_callback:
                try:
                    pct = int(completed_count / total_ch * 100)
                    progress_callback(
                        completed_count,
                        total_ch,
                        f"正在并发抓取清洗: 已完成 {completed_count}/{total_ch} 章 ({pct}%) · 最新: {ch_title[:24]}"
                    )
                except Exception:
                    pass

    # Launch all workers concurrently
    await asyncio.gather(*(fetch_worker(i, item) for i, item in enumerate(chapters_to_fetch)))

    # Assemble chapters strictly in original order (0 to total_ch - 1)
    chapters = []
    detected_langs = []
    para_counter = 1
    chapter_seq = 1

    for res in ordered_results:
        if not res:
            continue

        detected_langs.append(res["lang"])
        ch_paras = []
        for sub_ch in res["parsed_chapters"]:
            for p in sub_ch.get("paragraphs", []):
                p["id"] = f"p_{chapter_seq:03d}_{para_counter:04d}"
                p["chapter_id"] = f"ch_{chapter_seq:03d}"
                p["order"] = para_counter
                para_counter += 1
                ch_paras.append(p)

        if ch_paras:
            chapters.append({
                "chapter_id": f"ch_{chapter_seq:03d}",
                "title": res["title"],
                "url": res["url"],
                "fetch_success": res.get("fetch_success", True),
                "paragraphs": ch_paras
            })
            chapter_seq += 1

    if not chapters:
        chapters.append({
            "chapter_id": "ch_001",
            "title": "网页正文",
            "paragraphs": []
        })

    final_lang = "zh" if detected_langs.count("zh") > len(detected_langs) / 2 else "en"
    return final_lang, chapters
