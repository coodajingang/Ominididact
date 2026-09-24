import os
import sys
import io
import json
import zipfile
import asyncio
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import study as study_service
from study.asset_inspector import AssetInspector

class TestAssetInspector(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_docs = []

    async def asyncTearDown(self):
        for doc_id in self.test_docs:
            try:
                study_service.delete_document(doc_id)
            except Exception:
                pass

    async def test_01_collect_and_local_assets(self):
        # 1. Create a dummy doc with paragraphs containing image references
        meta = await study_service.initialize_document(b"fake dummy content", "sample.md")
        doc_id = meta["doc_id"]
        self.test_docs.append(doc_id)
        doc_dir = study_service.get_doc_dir(doc_id)

        # Create a mock chapter
        ch_data = {
            "chapter_id": "ch_001",
            "title": "Chapter One",
            "paragraphs": [
                {
                    "id": "p1",
                    "english": '<img src="Images/Architecture/overview.png" width="300" />',
                    "chinese": ""
                },
                {
                    "id": "p2",
                    "english": '![Diagram](./assets/flow.png)',
                    "chinese": ""
                },
                {
                    "id": "p3",
                    "english": '<video src="media/demo.mp4"></video>',
                    "chinese": ""
                }
            ]
        }
        ch_path = os.path.join(doc_dir, "chapters", "ch_001.json")
        with open(ch_path, "w", encoding="utf-8") as f:
            json.dump(ch_data, f)

        # Place one image physically in images/
        overview_path = os.path.join(doc_dir, "images", "overview.png")
        with open(overview_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nfake overview bytes")

        # Test collection
        refs = AssetInspector.collect_referenced_assets(doc_dir)
        self.assertEqual(len(refs), 3)
        raws = [r["raw"] for r in refs]
        self.assertIn("Images/Architecture/overview.png", raws)
        self.assertIn("./assets/flow.png", raws)
        self.assertIn("media/demo.mp4", raws)

        # Test local collection
        locals_map = AssetInspector.collect_local_assets(doc_dir)
        self.assertIn("overview.png", locals_map)
        print("\n[OK] test_01_collect_and_local_assets passed!")

    async def test_02_source_path_mapping_from_zip(self):
        # Create a zip containing markdown files with relative image paths
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("techniques/001.md", '<img src="Images/Chapters/0x05b/device.png" />\n')
            zf.writestr("techniques/002.md", '![Secret](Images/Chapters/0x05c/secret.png)\n')

        meta = await study_service.initialize_document(buf.getvalue(), "repo_bundle.zip")
        doc_id = meta["doc_id"]
        self.test_docs.append(doc_id)
        doc_dir = study_service.get_doc_dir(doc_id)

        mapping = AssetInspector.get_source_path_mapping(doc_dir)
        self.assertIn("device.png", mapping)
        self.assertEqual(mapping["device.png"], "Images/Chapters/0x05b/device.png")
        self.assertIn("secret.png", mapping)
        self.assertEqual(mapping["secret.png"], "Images/Chapters/0x05c/secret.png")

        # Check that image_sources.json was created
        src_json = os.path.join(doc_dir, "image_sources.json")
        self.assertTrue(os.path.exists(src_json))
        print("[OK] test_02_source_path_mapping_from_zip passed!")

    async def test_03_heuristic_inspection_without_ai(self):
        meta = await study_service.initialize_document(b"fake zip", "test.zip")
        doc_id = meta["doc_id"]
        self.test_docs.append(doc_id)
        doc_dir = study_service.get_doc_dir(doc_id)

        # Put dummy test.png in images
        with open(os.path.join(doc_dir, "images", "test.png"), "wb") as f:
            f.write(b"fake test png")

        # Setup chapter
        ch_data = {
            "chapter_id": "ch_001",
            "title": "Ch 1",
            "paragraphs": [
                {"id": "p1", "english": "![pic](test.png)", "chinese": ""}
            ]
        }
        with open(os.path.join(doc_dir, "chapters", "ch_001.json"), "w", encoding="utf-8") as f:
            json.dump(ch_data, f)

        # 1. When AI is not available, inspect_and_remediate must skip inspection
        with patch.object(AssetInspector, "is_ai_available", return_value=False):
            report = await AssetInspector.inspect_and_remediate(doc_id)
        self.assertTrue(report["skipped"])
        self.assertFalse(report["has_ai"])

        # 2. Directly calling apply_remediation_plan still supports deterministic local rewriting
        ref_assets = AssetInspector.collect_referenced_assets(doc_dir)
        local_assets = AssetInspector.collect_local_assets(doc_dir)
        direct_report = await AssetInspector.apply_remediation_plan(
            doc_id, doc_dir, ref_assets, local_assets, plan=None, has_ai=False
        )
        self.assertEqual(direct_report["stats"]["total_referenced"], 1)
        self.assertEqual(direct_report["stats"]["local_matched"], 1)

        # Check that chapter paragraph was rewritten to standard API endpoint
        with open(os.path.join(doc_dir, "chapters", "ch_001.json"), "r", encoding="utf-8") as f:
            ch_after = json.load(f)
        self.assertIn(f"/api/study/documents/{doc_id}/images/test.png", ch_after["paragraphs"][0]["english"])
        print("[OK] test_03_heuristic_inspection_without_ai passed!")

    async def test_04_remote_download_remediation_plan(self):
        meta = await study_service.initialize_document(b"fake zip", "remote.zip")
        doc_id = meta["doc_id"]
        self.test_docs.append(doc_id)
        doc_dir = study_service.get_doc_dir(doc_id)

        # Chapter with missing image
        ch_data = {
            "chapter_id": "ch_001",
            "title": "Ch 1",
            "paragraphs": [
                {"id": "p1", "english": '<img src="Images/Chapters/0x05b/cloud_logo.png" />', "chinese": ""}
            ]
        }
        with open(os.path.join(doc_dir, "chapters", "ch_001.json"), "w", encoding="utf-8") as f:
            json.dump(ch_data, f)

        # Save source mapping
        with open(os.path.join(doc_dir, "image_sources.json"), "w", encoding="utf-8") as f:
            json.dump({"cloud_logo.png": "Images/Chapters/0x05b/cloud_logo.png"}, f)

        # Fake AI Plan
        fake_plan = {
            "summary": "Detected missing remote documentation images",
            "doc_origin_inferred": "OWASP MASTG",
            "remote_fallback_base": "",
            "remote_path_pattern": "https://example.com/assets/{path}",
            "user_notice": "AI has inferred source repo and downloaded missing assets."
        }

        # Mock httpx download returning 200 OK
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG\r\n\x1a\n" + b"A" * 100

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            with patch.object(AssetInspector, "is_ai_available", return_value=True):
                with patch.object(AssetInspector, "request_ai_remediation_plan", return_value=fake_plan):
                    report = await AssetInspector.inspect_and_remediate(doc_id)

        self.assertTrue(report["has_ai"])
        self.assertEqual(report["stats"]["remotely_downloaded"], 1)
        self.assertEqual(report["stats"]["missing_count"], 0)

        # Verify image was saved
        saved_img = os.path.join(doc_dir, "images", "cloud_logo.png")
        self.assertTrue(os.path.exists(saved_img))

        # Verify chapter was rewritten
        with open(os.path.join(doc_dir, "chapters", "ch_001.json"), "r", encoding="utf-8") as f:
            ch_after = json.load(f)
        self.assertIn(f"/api/study/documents/{doc_id}/images/cloud_logo.png", ch_after["paragraphs"][0]["english"])
        print("[OK] test_04_remote_download_remediation_plan passed!")

    async def test_05_concurrent_deduplication(self):
        meta = await study_service.initialize_document(b"# Concurrency Test\n", "concurrent.md")
        doc_id = meta["doc_id"]
        self.test_docs.append(doc_id)

        call_count = 0

        async def slow_mock_worker(d_id):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return {
                "doc_id": d_id,
                "has_ai": True,
                "stats": {"total_referenced": 1, "local_matched": 1, "remotely_downloaded": 0, "missing_count": 0}
            }

        with patch.object(AssetInspector, "_do_inspect_and_remediate", side_effect=slow_mock_worker):
            # Fire two inspections concurrently
            res1, res2 = await asyncio.gather(
                AssetInspector.inspect_and_remediate(doc_id),
                AssetInspector.inspect_and_remediate(doc_id)
            )

        self.assertEqual(call_count, 1, "Expected exactly 1 execution of the underlying worker, second call must be deduplicated!")
        self.assertEqual(res1["doc_id"], doc_id)
        self.assertEqual(res2["doc_id"], doc_id)
        print("[OK] test_05_concurrent_deduplication passed!")

    async def test_06_prompt_files_exist_and_loadable(self):
        prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
        sys_p = os.path.join(prompts_dir, "asset_inspector_system.txt")
        user_p = os.path.join(prompts_dir, "asset_inspector_user.txt")

        self.assertTrue(os.path.isfile(sys_p), f"System prompt file missing: {sys_p}")
        self.assertTrue(os.path.isfile(user_p), f"User prompt file missing: {user_p}")

        with open(sys_p, "r", encoding="utf-8") as f:
            sys_text = f.read()
        self.assertIn("JSON", sys_text)
        self.assertIn("OWASP MASTG", sys_text)

        with open(user_p, "r", encoding="utf-8") as f:
            user_text = f.read()
        self.assertIn("{doc_title}", user_text)
        self.assertIn("{referenced_samples}", user_text)
        print("[OK] test_06_prompt_files_exist_and_loadable passed!")

    async def test_07_skip_non_eligible_documents(self):
        # 1. Verify should_inspect_document eligibility rules
        # Exclude single files (pdf, image, docx, single md/markdown)
        self.assertFalse(AssetInspector.should_inspect_document({"file_type": "pdf", "is_scanned": False}))
        self.assertFalse(AssetInspector.should_inspect_document({"file_type": "image", "is_scanned": True}))
        self.assertFalse(AssetInspector.should_inspect_document({"file_type": "docx", "is_scanned": False}))
        self.assertFalse(AssetInspector.should_inspect_document({"file_type": "md", "is_scanned": False}))
        self.assertFalse(AssetInspector.should_inspect_document({"file_type": "markdown", "is_scanned": False}))
        self.assertFalse(AssetInspector.should_inspect_document({}))

        # When AI is NOT available, even folder/zip/web must return False
        with patch.object(AssetInspector, "is_ai_available", return_value=False):
            self.assertFalse(AssetInspector.should_inspect_document({"file_type": "folder", "is_scanned": False}, doc_id="d1"))
            self.assertFalse(AssetInspector.should_inspect_document({"file_type": "zip", "is_scanned": False}, doc_id="d1"))
            self.assertFalse(AssetInspector.should_inspect_document({"file_type": "web", "is_scanned": False}, doc_id="d1"))

        # When AI IS available, only folder/zip/web return True
        with patch.object(AssetInspector, "is_ai_available", return_value=True):
            self.assertTrue(AssetInspector.should_inspect_document({"file_type": "folder", "is_scanned": False}, doc_id="d1"))
            self.assertTrue(AssetInspector.should_inspect_document({"file_type": "zip", "is_scanned": False}, doc_id="d1"))
            self.assertTrue(AssetInspector.should_inspect_document({"file_type": "web", "is_scanned": False}, doc_id="d1"))
            # Single MD must STILL be False even if AI is available
            self.assertFalse(AssetInspector.should_inspect_document({"file_type": "md", "is_scanned": False}, doc_id="d1"))

        # 2. Verify single md file skips inspection and never calls AI
        md_meta = await study_service.initialize_document(b"# Hello world", "sample.md")
        md_doc_id = md_meta["doc_id"]
        self.test_docs.append(md_doc_id)

        with patch.object(AssetInspector, "request_ai_remediation_plan") as mock_ai:
            report = await AssetInspector.inspect_and_remediate(md_doc_id)
            mock_ai.assert_not_called()
        self.assertTrue(report.get("skipped"), "Single MD inspection must be marked as skipped")

        # 3. Verify folder doc skips inspection when AI is not configured
        folder_meta = await study_service.initialize_document(b"fake zip", "material.zip")
        folder_doc_id = folder_meta["doc_id"]
        self.test_docs.append(folder_doc_id)

        with patch.object(AssetInspector, "is_ai_available", return_value=False), \
             patch.object(AssetInspector, "request_ai_remediation_plan") as mock_ai:
            report = await AssetInspector.inspect_and_remediate(folder_doc_id)
            mock_ai.assert_not_called()
        self.assertTrue(report.get("skipped"), "Folder inspection must be skipped when AI is unconfigured")
        print("[OK] test_07_skip_non_eligible_documents passed!")

if __name__ == "__main__":
    unittest.main()

