import os
import sys
import io
import zipfile
import asyncio
import unittest
from unittest.mock import patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import study as study_service
from study.epub_parser import inspect_epub, extract_epub_content
from study.folder_importer import extract_folder_content
from study.web_importer import inspect_web_series

class TestNewImporters(unittest.IsolatedAsyncioTestCase):
    async def test_01_web_inspector(self):
        url = "https://mas.owasp.org/MASTG/0x05a-Platform-Overview/"
        res = await inspect_web_series(url)
        self.assertIn("Android", res["title"])
        self.assertTrue(res["is_series"])
        self.assertGreaterEqual(res["total_chapters"], 5)
        # Check active chapters
        in_section = [c for c in res["chapters"] if c.get("in_section")]
        self.assertGreaterEqual(len(in_section), 5)
        print("\n[OK] Web Inspector passed! Discovered chapters:", len(in_section))

    async def test_02_markdown_folder_zip_pipeline(self):
        # Create a mock zip with SUMMARY.md and 2 markdown files + 1 fake image
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("SUMMARY.md", "* [Chapter One](ch1.md)\n* [Chapter Two](ch2.md)\n")
            zf.writestr("ch1.md", "# 第一章 基础架构\n\n这是第一章的内容，讲述了底层虚拟机的启动过程。\n\n![架构图](./images/arch.png)\n")
            zf.writestr("ch2.md", "# 第二章 安全机制\n\n这是第二章的内容，讲述了沙箱隔离与权限模型。\n")
            zf.writestr("images/arch.png", b"\x89PNG\r\n\x1a\nfake image bytes")

        zip_bytes = buf.getvalue()
        meta = await study_service.initialize_document(zip_bytes, "my_study_notes.zip")
        doc_id = meta["doc_id"]
        self.assertEqual(meta["file_type"], "folder")

        # Run extraction pipeline
        await study_service.process_document_pipeline(doc_id)

        # Verify result
        updated_meta = study_service.load_doc_meta(doc_id)
        self.assertEqual(updated_meta["status"], "completed")
        self.assertEqual(len(updated_meta["chapters"]), 2)
        self.assertIn("第一章", updated_meta["chapters"][0]["title"])
        self.assertIn("第二章", updated_meta["chapters"][1]["title"])

        # Check image copied
        doc_dir = study_service.get_doc_dir(doc_id)
        img_path = os.path.join(doc_dir, "images", "arch.png")
        self.assertTrue(os.path.exists(img_path))

        # Cleanup
        study_service.delete_document(doc_id)
        print("[OK] Markdown folder importer pipeline passed!")

    async def test_03_epub_importer_pipeline(self):
        # Construct a valid minimal EPUB in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")
            zf.writestr("OEBPS/content.opf", """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试电子书 - Android 逆向与实战</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>zh</dc:language>
  </metadata>
  <manifest>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>""")
            zf.writestr("OEBPS/toc.ncx", """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="np-1" playOrder="1">
      <navLabel><text>第 1 章：环境搭建</text></navLabel>
      <content src="ch1.xhtml"/>
    </navPoint>
    <navPoint id="np-2" playOrder="2">
      <navLabel><text>第 2 章：反编译技巧</text></navLabel>
      <content src="ch2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>""")
            zf.writestr("OEBPS/ch1.xhtml", """<!DOCTYPE html>
<html>
<head><title>第 1 章：环境搭建</title></head>
<body>
  <h1>第 1 章：环境搭建</h1>
  <p>在开始 Android 逆向之旅前，我们需要准备好开发板与测试机。</p>
  <p>安装 ADB 与 Frida 工具链是第一步。</p>
</body>
</html>""")
            zf.writestr("OEBPS/ch2.xhtml", """<!DOCTYPE html>
<html>
<head><title>第 2 章：反编译技巧</title></head>
<body>
  <h1>第 2 章：反编译技巧</h1>
  <p>通过 JADX 可以将 APK 的 classes.dex 还原为 Java 伪代码。</p>
</body>
</html>""")

        epub_bytes = buf.getvalue()
        meta = await study_service.initialize_document(epub_bytes, "android_reverse.epub")
        doc_id = meta["doc_id"]
        self.assertEqual(meta["file_type"], "epub")

        # Run pipeline
        await study_service.process_document_pipeline(doc_id)

        # Verify
        updated_meta = study_service.load_doc_meta(doc_id)
        self.assertEqual(updated_meta["status"], "completed")
        self.assertEqual(len(updated_meta["chapters"]), 2)
        self.assertIn("环境搭建", updated_meta["chapters"][0]["title"])
        self.assertIn("反编译技巧", updated_meta["chapters"][1]["title"])

        # Cleanup
        study_service.delete_document(doc_id)
        print("[OK] EPUB importer pipeline passed!")

    async def test_04_web_concurrent_in_order_extraction(self):
        from study.web_importer import extract_web_series_content

        mock_chapters = [
            {"title": "Section A", "url": "https://example.com/a"},
            {"title": "Section B", "url": "https://example.com/b"},
            {"title": "Section C", "url": "https://example.com/c"},
            {"title": "Section D", "url": "https://example.com/d"},
            {"title": "Section E", "url": "https://example.com/e"},
        ]
        meta = {
            "web_config": {"selected_chapters": mock_chapters},
            "source_url": "https://example.com"
        }

        # Mock fetch_and_clean_page to simulate varying delays (out-of-order completions)
        async def mock_fetch(url, img_dir, doc_id=""):
            # Delay inversely to index to provoke out-of-order completion
            if url.endswith("/a"):
                await asyncio.sleep(0.08)
                return "Title A", "Content for Section A"
            elif url.endswith("/b"):
                await asyncio.sleep(0.02)
                return "Title B", "Content for Section B"
            elif url.endswith("/c"):
                await asyncio.sleep(0.05)
                return "Title C", "Content for Section C"
            elif url.endswith("/d"):
                await asyncio.sleep(0.01)
                return "Title D", "Content for Section D"
            else:
                await asyncio.sleep(0.03)
                return "Title E", "Content for Section E"

        progress_calls = []
        def progress_cb(curr, total, detail=None):
            progress_calls.append((curr, total, detail))

        with patch("study.web_importer.fetch_and_clean_page", side_effect=mock_fetch):
            lang, chapters = await extract_web_series_content("doc_test_concurrent", "/tmp", meta, progress_callback=progress_cb)

        self.assertEqual(len(chapters), 5)
        # Verify strict order preservation despite varying execution times
        self.assertEqual(chapters[0]["title"], "Title A")
        self.assertEqual(chapters[1]["title"], "Title B")
        self.assertEqual(chapters[2]["title"], "Title C")
        self.assertEqual(chapters[3]["title"], "Title D")
        self.assertEqual(chapters[4]["title"], "Title E")

        self.assertEqual(chapters[0]["chapter_id"], "ch_001")
        self.assertEqual(chapters[1]["chapter_id"], "ch_002")
        self.assertEqual(chapters[4]["chapter_id"], "ch_005")

        self.assertGreaterEqual(len(progress_calls), 5)
        self.assertEqual(progress_calls[-1][0], 5)
        self.assertEqual(progress_calls[-1][1], 5)
        print("[OK] Web concurrent in-order extraction test passed!")

    async def test_05_check_missing_or_failed_and_refetch(self):
        from study.service import check_web_doc_has_missing_or_failed, refetch_failed_chapters

        # 1. Non-web document should return False
        pdf_meta = {"file_type": "pdf", "status": "completed"}
        has_failed, cnt, _ = check_web_doc_has_missing_or_failed(pdf_meta)
        self.assertFalse(has_failed)
        self.assertEqual(cnt, 0)

        # 2. Web document with failed chapter
        web_meta_failed = {
            "file_type": "web",
            "status": "completed",
            "chapters": [
                {"chapter_id": "ch_001", "title": "Good Chapter", "fetch_success": True},
                {"chapter_id": "ch_002", "title": "Failed Chapter", "fetch_success": False},
            ],
            "web_config": {
                "selected_chapters": [
                    {"title": "Good Chapter", "url": "https://example.com/1"},
                    {"title": "Failed Chapter", "url": "https://example.com/2"},
                ]
            }
        }
        has_failed, cnt, failed_list = check_web_doc_has_missing_or_failed(web_meta_failed)
        self.assertTrue(has_failed)
        self.assertEqual(cnt, 1)
        self.assertEqual(failed_list[0]["chapter_id"], "ch_002")

        # 3. Web document with extracting or missing chapters count
        web_meta_incomplete = {
            "file_type": "web",
            "status": "extracting",
            "chapters": [],
            "web_config": {
                "selected_chapters": [
                    {"title": "Ch 1", "url": "https://example.com/1"},
                    {"title": "Ch 2", "url": "https://example.com/2"},
                ]
            }
        }
        has_failed, cnt, _ = check_web_doc_has_missing_or_failed(web_meta_incomplete)
        self.assertTrue(has_failed)
        self.assertEqual(cnt, 2)
        print("[OK] check_web_doc_has_missing_or_failed test passed!")

if __name__ == "__main__":
    unittest.main()

