import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from study.document_chat import (
    CHAPTER_RAW_THRESHOLD,
    MAX_GLOBAL_DOC_CHARS,
    get_or_build_chapter_digest,
    assemble_document_global_context,
    get_document_digests_status,
    stream_document_chat
)


class TestDocumentChat(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_doc_chat_")
        self.doc_id = "test_doc_global_123"
        self.doc_path = os.path.join(self.test_dir, self.doc_id)
        os.makedirs(os.path.join(self.doc_path, "chapters"), exist_ok=True)
        os.makedirs(os.path.join(self.doc_path, "digests"), exist_ok=True)

        # Create meta.json
        meta = {
            "doc_id": self.doc_id,
            "filename": "OWASP MASTG 安全测试指南",
            "created_at": "2026-09-23 10:00:00",
            "chapters": [
                {"chapter_id": "ch_short", "title": "第1章：架构概览", "order": 1},
                {"chapter_id": "ch_long", "title": "第2章：Android 代码安全分析", "order": 2}
            ]
        }
        with open(os.path.join(self.doc_path, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        # Create a short chapter (under 2500 chars)
        short_paras = [
            {"type": "text", "source_text": "Overview of mobile app architecture.", "translated_text": "移动应用架构概述。"},
            {"type": "text", "source_text": "Security boundaries between user space and kernel.", "translated_text": "用户空间与内核间的安全边界。"}
        ]
        with open(os.path.join(self.doc_path, "chapters", "ch_short.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "第1章：架构概览", "paragraphs": short_paras}, f, ensure_ascii=False)

        # Create a long chapter (over 2500 chars)
        long_text_block = "Android reverse engineering and bytecode analysis. " * 80  # ~4160 chars
        long_paras = [
            {"type": "text", "source_text": long_text_block, "translated_text": "Android 逆向工程与字节码安全分析实战。"}
        ]
        with open(os.path.join(self.doc_path, "chapters", "ch_long.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "第2章：Android 代码安全分析", "paragraphs": long_paras}, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("study.document_chat.get_doc_dir")
    async def test_short_chapter_no_compression(self, mock_get_doc_dir):
        """Chapters under CHAPTER_RAW_THRESHOLD (2500 chars) should not be compressed."""
        mock_get_doc_dir.return_value = self.doc_path

        result = await get_or_build_chapter_digest(self.doc_id, "ch_short")
        self.assertFalse(result["is_compressed"])
        self.assertLessEqual(result["char_count"], CHAPTER_RAW_THRESHOLD)
        self.assertIn("移动应用架构概述", result["content"])
        self.assertEqual(result["original_char_count"], result["char_count"])

    @patch("study.document_chat.extract_chapter_digest_with_llm")
    @patch("study.document_chat.get_doc_dir")
    async def test_long_chapter_compressed_and_cached(self, mock_get_doc_dir, mock_extract):
        """Chapters exceeding 2500 chars should trigger extraction and be cached on disk."""
        mock_get_doc_dir.return_value = self.doc_path
        mock_extract.return_value = (
            "### 1. 核心主旨\n分析 Android DEX 与 Native 层的攻防机制。\n"
            "### 2. 关键架构\nSmali 反编译与 Hook 监测。\n"
            "### 3. 重要术语\nJNI, Frida, ProGuard\n"
            "### 4. 关键考点\n防止动态代码注入。"
        )

        # 1. First fetch: should call LLM extract
        result1 = await get_or_build_chapter_digest(self.doc_id, "ch_long")
        self.assertTrue(result1["is_compressed"])
        self.assertFalse(result1.get("from_cache", False))
        self.assertIn("核心主旨", result1["content"])
        self.assertEqual(mock_extract.call_count, 1)

        # Verify disk cache file was written
        digest_file = os.path.join(self.doc_path, "digests", "ch_long.json")
        self.assertTrue(os.path.exists(digest_file))

        # 2. Second fetch: should hit disk cache without calling extract again
        result2 = await get_or_build_chapter_digest(self.doc_id, "ch_long")
        self.assertTrue(result2["is_compressed"])
        self.assertTrue(result2["from_cache"])
        self.assertEqual(mock_extract.call_count, 1)  # not called again

    @patch("study.document_chat.load_doc_meta")
    @patch("study.document_chat.get_doc_dir")
    async def test_assemble_document_global_context(self, mock_get_doc_dir, mock_load_meta):
        """Assembling global context combines both short (raw) and long (digest) chapters."""
        mock_get_doc_dir.return_value = self.doc_path
        with open(os.path.join(self.doc_path, "meta.json"), "r", encoding="utf-8") as f:
            meta = json.load(f)
        mock_load_meta.return_value = meta

        with patch("study.document_chat.extract_chapter_digest_with_llm", new=AsyncMock(return_value="【摘要】逆向防护")):
            context_data = await assemble_document_global_context(self.doc_id)

            self.assertEqual(context_data["doc_title"], "OWASP MASTG 安全测试指南")
            self.assertEqual(context_data["chapters_count"], 2)
            self.assertIn("第 1 章节", context_data["context_text"])
            self.assertIn("第 2 章节", context_data["context_text"])
            self.assertLessEqual(context_data["total_chars"], MAX_GLOBAL_DOC_CHARS)

            # Check individual chapter statuses
            ch_infos = context_data["chapters_info"]
            self.assertFalse(ch_infos[0]["is_compressed"])  # ch_short
            self.assertTrue(ch_infos[1]["is_compressed"])   # ch_long

    @patch("study.document_chat.load_doc_meta")
    @patch("study.document_chat.get_doc_dir")
    async def test_get_document_digests_status(self, mock_get_doc_dir, mock_load_meta):
        """Returns readiness and compression requirements for all chapters."""
        mock_get_doc_dir.return_value = self.doc_path
        with open(os.path.join(self.doc_path, "meta.json"), "r", encoding="utf-8") as f:
            meta = json.load(f)
        mock_load_meta.return_value = meta

        status = await get_document_digests_status(self.doc_id)
        self.assertEqual(status["total_chapters"], 2)
        self.assertEqual(status["compressed_chapters"], 1)  # only ch_long needs compression
        self.assertEqual(status["threshold"], CHAPTER_RAW_THRESHOLD)

    @patch("study.document_chat.assemble_document_global_context")
    @patch("study.document_chat.get_study_settings")
    @patch("study.document_chat.get_provider_for_task")
    async def test_stream_document_chat(self, mock_get_provider, mock_settings, mock_assemble):
        """stream_document_chat yields SSE chunks properly."""
        mock_assemble.return_value = {
            "doc_title": "OWASP MASTG",
            "context_text": "全书知识网络...",
            "chapters_count": 2
        }
        mock_settings.return_value = {}

        async def fake_stream_chat(messages, options):
            yield {"type": "content", "content": "你好，我是全书研学导师。"}
            yield {"type": "content", "content": "针对全书的架构设计..."}

        mock_provider = AsyncMock()
        mock_provider.stream_chat = fake_stream_chat
        mock_get_provider.return_value = mock_provider

        chunks = []
        async for chunk in stream_document_chat(self.doc_id, "请总结全书核心安全策略"):
            chunks.append(chunk)

        full_output = "".join(chunks)
        self.assertIn("data: ", full_output)
        self.assertIn("全书研学导师", full_output)


if __name__ == "__main__":
    unittest.main()
