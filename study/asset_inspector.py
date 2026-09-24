import os
import re
import json
import logging
import hashlib
import asyncio
import urllib.parse
from typing import Dict, Any, List, Tuple, Optional
import httpx

from study.service import get_doc_dir, load_doc_meta, save_doc_meta, get_study_settings
from providers import get_provider_for_task

logger = logging.getLogger("study-asset-inspector")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class AssetInspector:
    """
    Independent AI-driven static asset inspection and path remediation pipeline.
    Analyzes references (images, media, snippets) across markdown chapters,
    infers remote source origins when local assets are missing, and executes
    deterministic structured transformations without arbitrary code execution.
    """

    _INSPECTION_FUTURES: Dict[str, asyncio.Future] = {}

    @classmethod
    def should_inspect_document(cls, meta: Optional[Dict[str, Any]], doc_id: Optional[str] = None) -> bool:
        """
        Determines whether a document requires asset inspection & remediation.
        Only multi-resource packages (web imports, markdown folders/zips) require inspection.
        Single files (PDFs, single images, Word docs, single MD files, txt) never require asset inspection.
        Additionally, if no AI model is configured, inspection is also skipped.
        """
        if not meta:
            return False
        file_type = (meta.get("file_type") or "").lower()
        is_scanned = bool(meta.get("is_scanned", False))

        # Exclude single images, scanned documents, PDFs, Word docs, and single markdown/text files
        if file_type in ("image", "pdf", "docx", "md", "markdown", "text", "other") or is_scanned:
            return False

        # Only allow web imports and folder/zip packages
        if file_type not in ("web", "folder", "zip"):
            return False

        # If no AI model is configured, skip inspection as well
        d_id = doc_id or meta.get("doc_id", "")
        if d_id and not cls.is_ai_available(d_id):
            return False

        return True

    @classmethod
    def get_source_path_mapping(cls, doc_dir: str) -> Dict[str, str]:
        """
        Retrieves or builds a mapping of {basename: original_relative_path}.
        Inspects image_sources.json, original.zip, or original.md if present.
        """
        sources_path = os.path.join(doc_dir, "image_sources.json")
        mapping: Dict[str, str] = {}
        if os.path.exists(sources_path):
            try:
                with open(sources_path, "r", encoding="utf-8") as f:
                    mapping = json.load(f)
            except Exception:
                pass

        # If mapping is empty, attempt to scan original archive or markdown
        if not mapping:
            import zipfile
            zip_cand = os.path.join(doc_dir, "original.zip")
            if os.path.isfile(zip_cand) and zipfile.is_zipfile(zip_cand):
                try:
                    with zipfile.ZipFile(zip_cand, "r") as zf:
                        for name in zf.namelist():
                            if name.endswith((".md", ".markdown", ".html")):
                                try:
                                    raw_text = zf.read(name).decode("utf-8", errors="ignore")
                                    # Find <img src="...">
                                    for m in re.finditer(r'<img[^>]+src=[\"\']([^\"\']+)[\"\']', raw_text, re.IGNORECASE):
                                        s = m.group(1).strip()
                                        if not s.startswith("http") and not s.startswith("/api/"):
                                            base = os.path.basename(urllib.parse.unquote(s.split("?")[0]))
                                            if base:
                                                mapping[base] = s
                                    # Find ![...](...)
                                    for m in re.finditer(r'!\[(.*?)\]\((.*?)\)', raw_text):
                                        s = m.group(2).strip().split()[0]
                                        if not s.startswith("http") and not s.startswith("/api/"):
                                            base = os.path.basename(urllib.parse.unquote(s.split("?")[0]))
                                            if base:
                                                mapping[base] = s
                                except Exception:
                                    pass
                except Exception as e:
                    logger.warning(f"Error scanning original.zip for image sources: {e}")

            # Also check extracted_folder if present
            ext_folder = os.path.join(doc_dir, "extracted_folder")
            if os.path.isdir(ext_folder):
                for root, _, files in os.walk(ext_folder):
                    for f in files:
                        if f.endswith((".md", ".markdown", ".html")):
                            try:
                                with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as f_in:
                                    raw_text = f_in.read()
                                for m in re.finditer(r'<img[^>]+src=[\"\']([^\"\']+)[\"\']', raw_text, re.IGNORECASE):
                                    s = m.group(1).strip()
                                    if not s.startswith("http") and not s.startswith("/api/"):
                                        base = os.path.basename(urllib.parse.unquote(s.split("?")[0]))
                                        if base:
                                            mapping[base] = s
                                for m in re.finditer(r'!\[(.*?)\]\((.*?)\)', raw_text):
                                    s = m.group(2).strip().split()[0]
                                    if not s.startswith("http") and not s.startswith("/api/"):
                                        base = os.path.basename(urllib.parse.unquote(s.split("?")[0]))
                                        if base:
                                            mapping[base] = s
                            except Exception:
                                pass

            # Save discovered mapping
            if mapping:
                try:
                    with open(sources_path, "w", encoding="utf-8") as f:
                        json.dump(mapping, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        return mapping

    @classmethod
    def collect_referenced_assets(cls, doc_dir: str) -> List[Dict[str, Any]]:
        """
        Scans all chapter files (*.json and *.md) to collect all referenced asset paths.
        Returns a list of dicts: [{"raw": ..., "clean_path": ..., "type": "img"|"md_img"|"media", "chapter_id": ...}]
        """
        chapters_dir = os.path.join(doc_dir, "chapters")
        if not os.path.exists(chapters_dir):
            return []

        results = []
        seen = set()

        for fname in sorted(os.listdir(chapters_dir)):
            if not fname.endswith(".json"):
                continue
            ch_path = os.path.join(chapters_dir, fname)
            ch_id = os.path.splitext(fname)[0]
            try:
                with open(ch_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read chapter {fname} for asset scan: {e}")
                continue

            for p in data.get("paragraphs", []):
                for text_field in ("english", "source_text", "translated_text", "chinese"):
                    text = p.get(text_field, "")
                    if not text:
                        continue

                    # 1. Match HTML <img ... src="..." ...>
                    for m in re.finditer(r'<img[^>]+src=[\"\']([^\"\']+)[\"\']', text, re.IGNORECASE):
                        src = m.group(1).strip()
                        if src and src not in seen:
                            seen.add(src)
                            results.append({
                                "raw": src,
                                "type": "html_img",
                                "chapter_id": ch_id
                            })

                    # 2. Match Markdown ![alt](url)
                    for m in re.finditer(r'!\[(.*?)\]\((.*?)\)', text):
                        src = m.group(2).strip().split()[0]
                        if src and src not in seen:
                            seen.add(src)
                            results.append({
                                "raw": src,
                                "type": "md_img",
                                "chapter_id": ch_id
                            })

                    # 3. Match <video> or <audio>
                    for m in re.finditer(r'<(?:video|audio)[^>]+src=[\"\']([^\"\']+)[\"\']', text, re.IGNORECASE):
                        src = m.group(1).strip()
                        if src and src not in seen:
                            seen.add(src)
                            results.append({
                                "raw": src,
                                "type": "media",
                                "chapter_id": ch_id
                            })

        return results

    @classmethod
    def collect_local_assets(cls, doc_dir: str) -> Dict[str, str]:
        """
        Collects all existing local physical files in doc_dir/images (and any extracted dirs).
        Returns a mapping of {lowercase_basename: relative_path_under_images}.
        """
        img_dir = os.path.join(doc_dir, "images")
        if not os.path.exists(img_dir):
            return {}

        mapping = {}
        for root, _, files in os.walk(img_dir):
            for f in files:
                if f.startswith("."):
                    continue
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, img_dir)
                mapping[f.lower()] = rel_p
        return mapping

    @classmethod
    def is_ai_available(cls, doc_id: str) -> bool:
        """
        Checks whether a chat provider and model are actively configured.
        """
        try:
            settings = get_study_settings(doc_id)
            provider = get_provider_for_task("chat", settings)
            if provider and getattr(provider, "default_model", None):
                return True
            # Also check if settings have configured chat_model
            if settings.get("chat_model") or settings.get("default_chat_model"):
                return True
        except Exception:
            pass
        return False

    @classmethod
    async def request_ai_remediation_plan(
        cls,
        doc_id: str,
        doc_meta: Dict[str, Any],
        referenced_samples: List[str],
        local_assets_samples: List[str]
    ) -> Dict[str, Any]:
        """
        Calls the LLM once to analyze resource reference patterns, identify missing targets,
        and generate a deterministic JSON remediation plan.
        """
        settings = get_study_settings(doc_id)
        provider = get_provider_for_task("chat", settings)
        doc_title = doc_meta.get("filename") or doc_meta.get("title") or "文档"
        file_type = doc_meta.get("file_type") or "markdown"
        source_url = doc_meta.get("source_url") or ""

        PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
        sys_prompt_path = os.path.join(PROMPTS_DIR, "asset_inspector_system.txt")
        user_prompt_path = os.path.join(PROMPTS_DIR, "asset_inspector_user.txt")

        # 1. Load System Prompt from template file or fallback
        system_prompt = ""
        if os.path.isfile(sys_prompt_path):
            try:
                with open(sys_prompt_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read {sys_prompt_path}: {e}")

        if not system_prompt:
            system_prompt = (
                "你是一位顶尖的文档资产架构与编译修复专家。\n"
                "用户上传了一篇技术文档，但正文中引用的静态资源（如图片）路径可能存在相对目录错乱，或者上传包中缺少了图片本地文件。\n"
                "你的任务是：根据文档标题、类型、正文中的资源路径样本、以及本地现有文件，分析出最优的【静态资源重定向与补全规约】。\n"
                "请以严格的 JSON 格式输出，不要包含 Markdown 代码块标记以外的任何文字！JSON 结构如下：\n"
                "{\n"
                '  "summary": "分析概述，简述发现了什么问题",\n'
                '  "doc_origin_inferred": "推测的文档原始开源项目或站点，如 OWASP MASTG、Kubernetes Docs 等",\n'
                '  "remote_fallback_base": "如果本地缺失且为知名公开技术文档，给出其高清图片的公共仓库/网站根路径",\n'
                '  "remote_path_pattern": "将相对路径拼接成完整远程URL的模板（使用 {path} 占位），如 https://raw.githubusercontent.com/OWASP/mastg/master/Document/{path}，无则留空",\n'
                '  "path_prefix_replacements": [\n'
                '    {"from_prefix": "Images/", "to_basename_only": true}\n'
                '  ],\n'
                '  "user_notice": "写给用户的一句温和清晰的诊断总结，说明修复了哪些图片或缺失情况"\n'
                "}"
            )

        # 2. Load User Prompt Template from file or fallback
        user_template = ""
        if os.path.isfile(user_prompt_path):
            try:
                with open(user_prompt_path, "r", encoding="utf-8") as f:
                    user_template = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read {user_prompt_path}: {e}")

        sample_count = min(40, len(referenced_samples))
        local_count = min(40, len(local_assets_samples))
        ref_samples_json = json.dumps(referenced_samples[:40], ensure_ascii=False, indent=2)
        local_samples_json = json.dumps(local_assets_samples[:40], ensure_ascii=False, indent=2)

        if user_template:
            try:
                user_content = user_template.format(
                    doc_title=doc_title,
                    file_type=file_type,
                    source_url=source_url or "无",
                    sample_count=sample_count,
                    referenced_samples=ref_samples_json,
                    local_count=local_count,
                    local_assets_samples=local_samples_json
                )
            except Exception:
                user_content = (
                    f"【文档信息】：\n- 标题/文件名：{doc_title}\n- 文档格式类型：{file_type}\n- 源地址（若有）：{source_url}\n\n"
                    f"【正文中引用的静态资源路径样本（前 {sample_count} 个）】：\n{ref_samples_json}\n\n"
                    f"【当前本地磁盘 images/ 目录下已存在的物理文件样本（前 {local_count} 个）】：\n{local_samples_json}\n"
                )
        else:
            user_content = (
                f"【文档信息】：\n- 标题/文件名：{doc_title}\n- 文档格式类型：{file_type}\n- 源地址（若有）：{source_url}\n\n"
                f"【正文中引用的静态资源路径样本（前 {sample_count} 个）】：\n{ref_samples_json}\n\n"
                f"【当前本地磁盘 images/ 目录下已存在的物理文件样本（前 {local_count} 个）】：\n{local_samples_json}\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        # Log complete prompt for debugging and traceability
        logger.info(
            f"====== [AssetInspector AI Prompt - {doc_id}] ======\n"
            f"--- System Prompt ---\n{system_prompt}\n\n"
            f"--- User Content ---\n{user_content}\n"
            f"==================================================="
        )

        try:
            reasoning_chunks = []
            content_chunks = []
            if hasattr(provider, "chat"):
                resp = await provider.chat(messages, {"temperature": 0.1})
                if isinstance(resp, str):
                    resp_text = resp
                    reasoning_text = ""
                else:
                    resp_text = getattr(resp, "content", str(resp))
                    reasoning_text = getattr(resp, "reasoning_content", "") or ""
            else:
                async for chunk in provider.stream_chat(messages, {"temperature": 0.1}):
                    if hasattr(chunk, "reasoning_content") and chunk.reasoning_content:
                        reasoning_chunks.append(chunk.reasoning_content)
                    if hasattr(chunk, "content") and chunk.content:
                        content_chunks.append(chunk.content)
                resp_text = "".join(content_chunks)
                reasoning_text = "".join(reasoning_chunks)

            # Log complete model response
            logger.info(
                f"====== [AssetInspector AI Response - {doc_id}] ======\n"
                f"--- Reasoning Content ---\n{reasoning_text}\n\n"
                f"--- Final Content ---\n{resp_text}\n"
                f"====================================================="
            )

            # Clean and robustly extract JSON object
            clean_text = re.sub(r'<think>.*?</think>', '', resp_text, flags=re.DOTALL).strip()
            if "```" in clean_text:
                m_code = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean_text, re.DOTALL)
                if m_code:
                    clean_text = m_code.group(1).strip()
                else:
                    clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text)
                    clean_text = re.sub(r'\s*```$', '', clean_text).strip()

            s_idx = clean_text.find("{")
            e_idx = clean_text.rfind("}")
            if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                clean_text = clean_text[s_idx:e_idx+1]

            plan = json.loads(clean_text)

            # Smart Fallback Deduction for Known Projects:
            # If model didn't fill remote_path_pattern or left it empty, but detected MASTG / MASVS or samples have MASTG paths
            inferred = (plan.get("doc_origin_inferred") or "").lower()
            has_mastg_paths = any("images/chapters/" in s.lower() or "images/techniques/" in s.lower() or "images/tools/" in s.lower() for s in referenced_samples)
            if not plan.get("remote_path_pattern") and ("mastg" in inferred or "owasp" in inferred or "masvs" in inferred or has_mastg_paths):
                logger.info(f"AI inferred {plan.get('doc_origin_inferred')} but remote_path_pattern was empty; auto-applying official OWASP MASTG GitHub raw repository fallback pattern.")
                plan["remote_fallback_base"] = "https://raw.githubusercontent.com/OWASP/mastg/master/Document/"
                plan["remote_path_pattern"] = "https://raw.githubusercontent.com/OWASP/mastg/master/Document/{path}"
                plan["user_notice"] = (plan.get("user_notice") or "") + "（系统已自动接入 OWASP MASTG 官方仓库源进行图片补全）"

            return plan
        except Exception as e:
            logger.error(f"AI asset remediation plan generation failed: {e}")
            # Even in failure, if samples indicate OWASP MASTG, provide the standard fallback plan!
            has_mastg_paths = any("images/chapters/" in s.lower() or "images/techniques/" in s.lower() for s in referenced_samples)
            if has_mastg_paths:
                logger.info("Falling back to pre-configured OWASP MASTG remediation rules.")
                return {
                    "summary": "AI 分析遇到异常，已自动匹配 OWASP MASTG 官方静态资源规约。",
                    "doc_origin_inferred": "OWASP Mobile Application Security Testing Guide (MASTG)",
                    "remote_fallback_base": "https://raw.githubusercontent.com/OWASP/mastg/master/Document/",
                    "remote_path_pattern": "https://raw.githubusercontent.com/OWASP/mastg/master/Document/{path}",
                    "path_prefix_replacements": [
                        {"from_prefix": "Images/Chapters/", "to_basename_only": True},
                        {"from_prefix": "Images/Techniques/", "to_basename_only": True}
                    ],
                    "user_notice": "已自动接入 OWASP MASTG 官方文档源，正在补全缺失图片。"
                }
            return {
                "summary": f"AI 分析未成功完成: {str(e)}",
                "doc_origin_inferred": "未知",
                "remote_fallback_base": "",
                "remote_path_pattern": "",
                "path_prefix_replacements": [],
                "user_notice": "AI 资产分析遇到异常，已转为本地基础规则模式。"
            }

    @classmethod
    async def apply_remediation_plan(
        cls,
        doc_id: str,
        doc_dir: str,
        referenced_assets: List[Dict[str, Any]],
        local_assets_map: Dict[str, str],
        plan: Optional[Dict[str, Any]] = None,
        has_ai: bool = False
    ) -> Dict[str, Any]:
        """
        Executes the remediation plan:
        1. If remote_path_pattern or remote_fallback_base is provided, attempts to download missing assets into doc_dir/images
        2. Rewrites all references across chapter files to standard /api/study/documents/{doc_id}/images/{filename}
        3. Returns a structured inspection and remediation report
        """
        img_dir = os.path.join(doc_dir, "images")
        os.makedirs(img_dir, exist_ok=True)
        chapters_dir = os.path.join(doc_dir, "chapters")

        total_referenced = len(referenced_assets)
        local_matched = 0
        remotely_downloaded = 0
        failed_count = 0

        # Map of raw_reference_path -> target_filename
        remediation_map: Dict[str, str] = {}
        missing_list: List[str] = []

        remote_pattern = (plan or {}).get("remote_path_pattern", "")
        remote_base = (plan or {}).get("remote_fallback_base", "")

        # Re-index local assets
        current_locals = cls.collect_local_assets(doc_dir)
        source_mapping = cls.get_source_path_mapping(doc_dir)

        # HTTP client for downloading missing assets if a remote source was deduced
        async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}, follow_redirects=True, timeout=12.0) as client:
            for item in referenced_assets:
                raw = item["raw"]

                # Check if raw is already an API path
                is_api_path = raw.startswith(f"/api/study/documents/{doc_id}/images/")
                if is_api_path:
                    base = os.path.basename(urllib.parse.unquote(raw.split("?")[0]))
                else:
                    unquoted = urllib.parse.unquote(raw)
                    base = os.path.basename(unquoted.split("?")[0])

                base_lower = base.lower()

                # 1. If physical file already exists locally in doc_dir/images
                if base_lower in current_locals or os.path.exists(os.path.join(img_dir, base)):
                    local_matched += 1
                    remediation_map[raw] = current_locals.get(base_lower, base)
                    continue

                # 2. File does not exist on disk: look up original relative path
                orig_path = source_mapping.get(base) or raw
                downloaded = False
                candidate_urls = []

                if remote_pattern and "{path}" in remote_pattern:
                    candidate_urls.append(remote_pattern.replace("{path}", orig_path.lstrip("/")))
                    if orig_path != base:
                        candidate_urls.append(remote_pattern.replace("{path}", base.lstrip("/")))
                if remote_base:
                    candidate_urls.append(urllib.parse.urljoin(remote_base, orig_path.lstrip("/")))
                    if orig_path != base:
                        candidate_urls.append(urllib.parse.urljoin(remote_base, base.lstrip("/")))

                if raw.startswith("http://") or raw.startswith("https://"):
                    candidate_urls.insert(0, raw)
                elif orig_path.startswith("http://") or orig_path.startswith("https://"):
                    candidate_urls.insert(0, orig_path)

                for c_url in candidate_urls:
                    try:
                        resp = await client.get(c_url)
                        if resp.status_code == 200 and len(resp.content) > 50:
                            clean_fname = re.sub(r'[^a-zA-Z0-9_\-.]', '_', base) or f"img_{hashlib.md5(c_url.encode()).hexdigest()[:6]}.png"
                            save_p = os.path.join(img_dir, clean_fname)
                            with open(save_p, "wb") as f_out:
                                f_out.write(resp.content)
                            current_locals[clean_fname.lower()] = clean_fname
                            remediation_map[raw] = clean_fname
                            remotely_downloaded += 1
                            downloaded = True
                            break
                    except Exception as e:
                        logger.debug(f"Failed to download remote candidate {c_url}: {e}")

                if not downloaded:
                    # Still missing
                    failed_count += 1
                    missing_list.append(orig_path)
                    # Even if missing, point it to standard API path with basename so that
                    # if user uploads the image later, it will immediately work without re-parsing markdown
                    remediation_map[raw] = base

        # Rewrite references across all chapters
        updated_chapters_count = 0
        if os.path.exists(chapters_dir):
            for fname in os.listdir(chapters_dir):
                if not fname.endswith(".json"):
                    continue
                ch_path = os.path.join(chapters_dir, fname)
                try:
                    with open(ch_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    changed = False
                    for p in data.get("paragraphs", []):
                        for field in ("english", "source_text", "translated_text", "chinese"):
                            val = p.get(field)
                            if not val or not isinstance(val, str):
                                continue

                            new_val = val
                            for raw_ref, target_fname in remediation_map.items():
                                if raw_ref in new_val:
                                    target_api = f"/api/study/documents/{doc_id}/images/{target_fname}"
                                    # Replace in HTML src
                                    new_val = new_val.replace(f'src="{raw_ref}"', f'src="{target_api}"')
                                    new_val = new_val.replace(f"src='{raw_ref}'", f"src='{target_api}'")
                                    # Replace in markdown ![alt](raw_ref)
                                    new_val = new_val.replace(f"]({raw_ref})", f"]({target_api})")
                                    # General fallback replace
                                    if raw_ref in new_val and not raw_ref.startswith("/api/"):
                                        new_val = new_val.replace(raw_ref, target_api)

                            if new_val != val:
                                p[field] = new_val
                                changed = True

                    if changed:
                        with open(ch_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        updated_chapters_count += 1
                except Exception as e:
                    logger.warning(f"Failed to rewrite chapter {fname}: {e}")

        # If any chapters were modified or images downloaded, synchronize full_bilingual.md
        if updated_chapters_count > 0 or remotely_downloaded > 0:
            try:
                from study.service import assemble_full_document_markdown
                assemble_full_document_markdown(doc_id)
            except Exception as e:
                logger.warning(f"Failed to reassemble full_bilingual.md: {e}")

        # Assemble final inspection report
        report = {
            "doc_id": doc_id,
            "has_ai": has_ai,
            "ai_summary": (plan or {}).get("summary", "基础规则模式检查"),
            "doc_origin_inferred": (plan or {}).get("doc_origin_inferred", "本地文件"),
            "user_notice": (plan or {}).get("user_notice", ""),
            "stats": {
                "total_referenced": total_referenced,
                "local_matched": local_matched,
                "remotely_downloaded": remotely_downloaded,
                "missing_count": failed_count
            },
            "missing_samples": missing_list[:20],
            "remediation_samples": [
                {"from": k, "to": f"/api/study/documents/{doc_id}/images/{v}"}
                for k, v in list(remediation_map.items())[:10]
            ],
            "updated_chapters": updated_chapters_count
        }

        # Persist report to doc_dir/asset_inspection.json
        report_path = os.path.join(doc_dir, "asset_inspection.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write asset inspection report: {e}")

        return report

    @classmethod
    async def inspect_and_remediate(cls, doc_id: str) -> Dict[str, Any]:
        """
        Public entry point to run asset inspection & remediation on a document.
        Guarantees only ONE in-flight inspection executes per document, avoiding duplicate LLM calls.
        """
        # 1. Check if an inspection is already actively running for this doc_id
        if doc_id in cls._INSPECTION_FUTURES:
            logger.info(f"Asset inspection already in-flight for document {doc_id}, awaiting existing task instead of duplicate call...")
            try:
                return await asyncio.shield(cls._INSPECTION_FUTURES[doc_id])
            except Exception as e:
                logger.warning(f"Awaited in-flight inspection encountered error for {doc_id}: {e}")

        # 2. Create in-flight Future to prevent duplicate concurrent runs
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        cls._INSPECTION_FUTURES[doc_id] = fut

        try:
            report = await cls._do_inspect_and_remediate(doc_id)
            if not fut.done():
                fut.set_result(report)
            return report
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            cls._INSPECTION_FUTURES.pop(doc_id, None)

    @classmethod
    async def _do_inspect_and_remediate(cls, doc_id: str) -> Dict[str, Any]:
        """
        Internal worker that executes inspection and remediation.
        """
        doc_dir = get_doc_dir(doc_id)
        meta = load_doc_meta(doc_id) or {}

        # 0. Check document type and AI availability eligibility
        if not cls.should_inspect_document(meta, doc_id=doc_id):
            file_type = meta.get("file_type", "unknown")
            has_ai = cls.is_ai_available(doc_id)
            reason = "文档格式无需自省（如单文件MD/PDF/图片）" if file_type not in ("web", "folder", "zip") else "未配置大模型"
            logger.info(f"Skipping asset inspection for {doc_id} (file_type={file_type}, has_ai={has_ai}). Reason: {reason}.")
            report = {
                "doc_id": doc_id,
                "skipped": True,
                "has_ai": has_ai,
                "ai_summary": f"无需静态资源对齐自省: {reason}",
                "user_notice": f"该文档无需静态资源对齐自省（{reason}）。",
                "stats": {
                    "total_referenced": 0,
                    "local_matched": 0,
                    "remotely_downloaded": 0,
                    "missing_count": 0
                },
                "missing_samples": [],
                "remediation_samples": [],
                "updated_chapters": 0
            }
            report_path = os.path.join(doc_dir, "asset_inspection.json")
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return report

        # 1. Collect references & local assets
        referenced_assets = cls.collect_referenced_assets(doc_dir)
        local_assets_map = cls.collect_local_assets(doc_dir)

        if not referenced_assets:
            report = {
                "doc_id": doc_id,
                "has_ai": False,
                "ai_summary": "文档中未检测到静态资源引用",
                "user_notice": "该文档无静态图片或音视频引用，一切正常。",
                "stats": {
                    "total_referenced": 0,
                    "local_matched": 0,
                    "remotely_downloaded": 0,
                    "missing_count": 0
                },
                "missing_samples": [],
                "remediation_samples": []
            }
            return report

        # 2. Check if AI is configured
        has_ai = cls.is_ai_available(doc_id)
        plan = None

        source_mapping = cls.get_source_path_mapping(doc_dir)
        ref_samples = []
        for item in referenced_assets:
            r = item["raw"]
            base = os.path.basename(urllib.parse.unquote(r.split("?")[0]))
            orig = source_mapping.get(base)
            ref_samples.append(orig or r)

        if has_ai:
            logger.info(f"Running AI asset inspection for document {doc_id}...")
            local_samples = list(local_assets_map.keys())
            plan = await cls.request_ai_remediation_plan(doc_id, meta, ref_samples, local_samples)
        else:
            logger.info(f"AI model not configured for {doc_id}, using local heuristic inspection.")
            plan = {
                "summary": "未配置大模型，系统使用基于文件名的本地智能对齐引擎。",
                "doc_origin_inferred": "本地文档包",
                "remote_fallback_base": "",
                "remote_path_pattern": "",
                "user_notice": "提示：当前未配置 AI 默认对话模型，系统已对本地已有图片进行名称对齐。若文档缺少图片且需自动网络溯源补全，请在系统设置中配置 AI 模型。"
            }

        # 3. Apply remediation plan
        report = await cls.apply_remediation_plan(
            doc_id, doc_dir, referenced_assets, local_assets_map, plan=plan, has_ai=has_ai
        )

        # Update meta.json
        meta["asset_inspection"] = {
            "has_ai": report["has_ai"],
            "total_referenced": report["stats"]["total_referenced"],
            "local_matched": report["stats"]["local_matched"],
            "remotely_downloaded": report["stats"]["remotely_downloaded"],
            "missing_count": report["stats"]["missing_count"],
            "user_notice": report["user_notice"]
        }
        save_doc_meta(doc_id, meta)

        return report
