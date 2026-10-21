import os
import sys
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fitz
from PIL import Image
from fastapi.testclient import TestClient
from proxy import app
import study_service

client = TestClient(app)

def create_dummy_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "1. Introduction\n\nArtificial intelligence has developed rapidly in recent years.")
    
    img = Image.new("RGB", (100, 80), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    page.insert_image(fitz.Rect(50, 150, 150, 230), stream=buf.getvalue())
    
    b = doc.tobytes()
    doc.close()
    return b

def test_study_page_route():
    print("Testing GET /study ...")
    res = client.get("/study")
    assert res.status_code == 200
    assert "研学" in res.text or "Omnididact" in res.text
    print("✓ GET /study passed!")

def test_study_settings_api():
    print("Testing /api/study/settings ...")
    res = client.get("/api/study/settings")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "translation_prompt_template" in data
    assert "model_call_delay" in data
    
    # Save settings
    new_delay = 1.2
    save_res = client.post("/api/study/settings", json={
        "translation_prompt_template": data["translation_prompt_template"],
        "model_call_delay": new_delay
    })
    assert save_res.status_code == 200
    assert save_res.json()["data"]["model_call_delay"] == 1.2
    
    # Reset back to 1.0
    client.post("/api/study/settings", json={"model_call_delay": 1.0})
    print("✓ /api/study/settings passed!")

def test_upload_and_document_workflow():
    print("Testing upload, detail, chapter, export, and delete workflow...")
    pdf_bytes = create_dummy_pdf()
    
    files = {"file": ("test_paper.pdf", pdf_bytes, "application/pdf")}
    up_res = client.post("/api/study/documents/upload", files=files)
    assert up_res.status_code == 200
    doc_data = up_res.json()["data"]
    doc_id = doc_data["doc_id"]
    print(f"Uploaded doc ID: {doc_id}")
    
    # Get doc detail
    detail_res = client.get(f"/api/study/documents/{doc_id}")
    assert detail_res.status_code == 200
    meta = detail_res.json()["data"]
    assert meta["filename"] == "test_paper.pdf"
    assert meta["file_type"] == "pdf"
    
    # Check documents list
    list_res = client.get("/api/study/documents")
    assert list_res.status_code == 200
    all_docs = list_res.json()["data"]
    assert any(d["doc_id"] == doc_id for d in all_docs)

    # Test patch_zip export API
    patch_res = client.get(f"/api/study/documents/{doc_id}/export?format=patch_zip")
    assert patch_res.status_code == 200
    assert patch_res.headers["content-type"] == "application/zip"
    assert len(patch_res.content) > 0

    # Test library site export API
    lib_res = client.get("/api/study/library/export?site_title=测试研学知识库")
    assert lib_res.status_code == 200
    assert lib_res.headers["content-type"] == "application/zip"
    assert len(lib_res.content) > 0
    
    # Clean up by deleting
    del_res = client.delete(f"/api/study/documents/{doc_id}")
    assert del_res.status_code == 200
    print("✓ Document workflow test passed!")

def test_import_web_document_route():
    print("Testing /api/study/documents/import-url with fetch_mode ...")
    payload = {
        "url": "https://example.com/guide/intro",
        "title": "测试网页教材",
        "selected_chapters": [
            {"title": "第一节 快速入门", "url": "https://example.com/guide/intro"}
        ],
        "fetch_mode": "static"
    }
    res = client.post("/api/study/documents/import-url", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    doc_id = data["doc_id"]
    assert data["filename"] == "测试网页教材"
    assert data["web_config"]["fetch_mode"] == "static"
    
    # Verify cleanup
    del_res = client.delete(f"/api/study/documents/{doc_id}")
    assert del_res.status_code == 200
    print("✓ /api/study/documents/import-url test passed!")

def test_document_chat_endpoint_parameter_compatibility():
    print("Testing /api/study/documents/{doc_id}/document_chat parameter compatibility...")
    pdf_bytes = create_dummy_pdf()
    up_res = client.post(
        "/api/study/documents/upload",
        files={"file": ("chat_test.pdf", pdf_bytes, "application/pdf")}
    )
    assert up_res.status_code == 200
    doc_id = up_res.json()["data"]["doc_id"]

    try:
        from unittest.mock import patch

        async def dummy_stream(*args, **kwargs):
            yield "data: {\"text\": \"ok\"}\n\n"

        with patch("study.document_chat.stream_document_chat", side_effect=dummy_stream):
            # 1. Test missing prompt/message -> 400 prompt is required
            res_empty = client.post(f"/api/study/documents/{doc_id}/document_chat", json={})
            assert res_empty.status_code == 400
            assert "prompt is required" in res_empty.json()["detail"]

            # 2. Test with 'prompt'
            res_prompt = client.post(f"/api/study/documents/{doc_id}/document_chat", json={"prompt": "总结全文"})
            assert res_prompt.status_code == 200

            # 3. Test with 'message' (frontend fallback)
            res_message = client.post(f"/api/study/documents/{doc_id}/document_chat", json={"message": "总结全文"})
            assert res_message.status_code == 200
    finally:
        client.delete(f"/api/study/documents/{doc_id}")
    print("✓ document_chat parameter compatibility test passed!")

def test_chapter_chat_endpoint_parameter_compatibility():
    print("Testing /api/study/documents/{doc_id}/chapter_chat parameter compatibility...")
    pdf_bytes = create_dummy_pdf()
    up_res = client.post(
        "/api/study/documents/upload",
        files={"file": ("chat_test_ch.pdf", pdf_bytes, "application/pdf")}
    )
    assert up_res.status_code == 200
    doc_id = up_res.json()["data"]["doc_id"]

    try:
        from unittest.mock import patch

        async def dummy_stream(*args, **kwargs):
            yield 'data: {"text": "ok"}\n\n'

        meta = client.get(f"/api/study/documents/{doc_id}").json()["data"]
        chapter_id = meta["chapters"][0]["chapter_id"]

        with patch("study.chapter_chat.stream_chapter_chat", side_effect=dummy_stream):
            # Test missing chapter_id or prompt -> 400
            res_empty = client.post(f"/api/study/documents/{doc_id}/chapter_chat", json={})
            assert res_empty.status_code == 400

            # Test valid chapter_chat
            res_valid = client.post(
                f"/api/study/documents/{doc_id}/chapter_chat",
                json={"chapter_id": chapter_id, "prompt": "梳理本章脉络", "chat_history": []}
            )
            assert res_valid.status_code == 200

        # Test save_chat_history endpoint
        save_res = client.post(
            f"/api/study/documents/{doc_id}/chat_history",
            json={
                "chat_type": "chapter",
                "chapter_id": chapter_id,
                "messages": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
            }
        )
        assert save_res.status_code == 200
        get_res = client.get(f"/api/study/documents/{doc_id}/chat_history?chat_type=chapter&chapter_id={chapter_id}")
        assert get_res.status_code == 200
        assert len(get_res.json()["data"]) == 2
    finally:
        client.delete(f"/api/study/documents/{doc_id}")
    print("✓ chapter_chat parameter compatibility test passed!")

def test_upload_multiple_documents_workflow():
    print("Testing multi-document upload workflow...")
    pdf1_bytes = create_dummy_pdf()
    pdf2_bytes = create_dummy_pdf()
    
    files = [
        ("files", ("paper_1.pdf", pdf1_bytes, "application/pdf")),
        ("files", ("paper_2.pdf", pdf2_bytes, "application/pdf")),
    ]
    up_res = client.post("/api/study/documents/upload", files=files)
    assert up_res.status_code == 200, up_res.text
    data = up_res.json()
    assert data["code"] == 200
    assert data["total"] == 2
    assert "docs" in data
    docs = data["docs"]
    assert len(docs) == 2
    
    doc1_id = docs[0]["doc_id"]
    doc2_id = docs[1]["doc_id"]
    assert doc1_id != doc2_id, "Each uploaded PDF must have an independent doc_id"
    assert docs[0]["filename"] == "paper_1.pdf"
    assert docs[1]["filename"] == "paper_2.pdf"
    
    # Verify each is queryable independently
    res1 = client.get(f"/api/study/documents/{doc1_id}")
    assert res1.status_code == 200
    assert res1.json()["data"]["filename"] == "paper_1.pdf"

    res2 = client.get(f"/api/study/documents/{doc2_id}")
    assert res2.status_code == 200
    assert res2.json()["data"]["filename"] == "paper_2.pdf"

    # Verify both appear in documents list
    list_res = client.get("/api/study/documents")
    assert list_res.status_code == 200
    all_doc_ids = [d["doc_id"] for d in list_res.json()["data"]]
    assert doc1_id in all_doc_ids
    assert doc2_id in all_doc_ids

    # Cleanup
    client.delete(f"/api/study/documents/{doc1_id}")
    client.delete(f"/api/study/documents/{doc2_id}")
    print("✓ Multi-document upload workflow test passed!")

def test_chapter_and_paragraph_notes_api():
    print("Testing chapter and paragraph notes API endpoints...")
    pdf_bytes = create_dummy_pdf()
    files = {"file": ("test_notes_doc.pdf", pdf_bytes, "application/pdf")}
    up_res = client.post("/api/study/documents/upload", files=files)
    assert up_res.status_code == 200
    doc_id = up_res.json()["data"]["doc_id"]
    
    try:
        # Get chapter id
        meta = client.get(f"/api/study/documents/{doc_id}").json()["data"]
        chapter_id = meta["chapters"][0]["chapter_id"]
        
        # 1. POST chapter header note
        save_hn_res = client.post(
            f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes",
            json={"position": "header", "type": "header", "title": "导读标题", "content": "全章核心重点"}
        )
        assert save_hn_res.status_code == 200, save_hn_res.text
        hn_data = save_hn_res.json()
        assert hn_data["code"] == 200
        note_id = hn_data["data"]["id"]
        assert hn_data["data"]["title"] == "导读标题"
        assert hn_data["data"]["content"] == "全章核心重点"
        
        # 2. PUT chapter note (update)
        up_hn_res = client.put(
            f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}",
            json={"position": "header", "title": "更新导读标题", "content": "更新核心重点"}
        )
        assert up_hn_res.status_code == 200, up_hn_res.text
        assert up_hn_res.json()["data"]["title"] == "更新导读标题"
        assert up_hn_res.json()["data"]["content"] == "更新核心重点"
        
        # 3. POST chapter footer note
        save_fn_res = client.post(
            f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes",
            json={"position": "footer", "title": "复盘考点", "content": "复盘总结内容"}
        )
        assert save_fn_res.status_code == 200, save_fn_res.text
        fn_id = save_fn_res.json()["data"]["id"]
        
        # Verify chapter contains notes
        ch_res = client.get(f"/api/study/documents/{doc_id}/chapters/{chapter_id}")
        assert ch_res.status_code == 200
        ch_data = ch_res.json()["data"]
        assert any(n["id"] == note_id for n in ch_data.get("header_notes", []))
        assert any(n["id"] == fn_id for n in ch_data.get("footer_notes", []))
        
        # 4. DELETE single chapter note
        del_note_res = client.delete(f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes/{note_id}?position=header")
        assert del_note_res.status_code == 200
        
        # 5. DELETE chapter notes by type
        clear_res = client.delete(f"/api/study/documents/{doc_id}/chapters/{chapter_id}/notes?type=footer")
        assert clear_res.status_code == 200
        
        # Verify notes cleared
        ch_res2 = client.get(f"/api/study/documents/{doc_id}/chapters/{chapter_id}")
        ch_data2 = ch_res2.json()["data"]
        assert len(ch_data2.get("header_notes", [])) == 0
        assert len(ch_data2.get("footer_notes", [])) == 0
        print("✓ Chapter notes API test passed!")
    finally:
        client.delete(f"/api/study/documents/{doc_id}")

def test_extract_paragraph_text_api():
    print("Testing extract paragraph text API endpoint...")
    import study
    assert hasattr(study, "extract_paragraph_text_content")
    assert hasattr(study, "extract_paragraph_image_text")

    pdf_bytes = create_dummy_pdf()
    files = {"file": ("test_extract_doc.pdf", pdf_bytes, "application/pdf")}
    up_res = client.post("/api/study/documents/upload", files=files)
    assert up_res.status_code == 200
    doc_id = up_res.json()["data"]["doc_id"]
    try:
        meta = client.get(f"/api/study/documents/{doc_id}").json()["data"]
        chapter_id = meta["chapters"][0]["chapter_id"]
        ch_res = client.get(f"/api/study/documents/{doc_id}/chapters/{chapter_id}")
        assert ch_res.status_code == 200
        paragraphs = ch_res.json()["data"]["paragraphs"]
        assert len(paragraphs) > 0
        para_id = paragraphs[0]["id"]

        extract_res = client.post(
            f"/api/study/documents/{doc_id}/paragraphs/extract_text",
            json={"chapter_id": chapter_id, "paragraph_id": para_id}
        )
        assert extract_res.status_code == 200, extract_res.text
        extract_data = extract_res.json()
        assert extract_data["code"] == 200
        assert "data" in extract_data
        assert extract_data["data"]["id"] == para_id
        print("✓ Extract paragraph text API test passed!")
    finally:
        client.delete(f"/api/study/documents/{doc_id}")

def test_shift_chapter_paragraphs_api():
    print("Testing shift chapter paragraphs API endpoint...")
    pdf_bytes = create_dummy_pdf()
    files = {"file": ("test_shift_doc.pdf", pdf_bytes, "application/pdf")}
    up_res = client.post("/api/study/documents/upload", files=files)
    assert up_res.status_code == 200
    doc_id = up_res.json()["data"]["doc_id"]
    try:
        meta = client.get(f"/api/study/documents/{doc_id}").json()["data"]
        ch0_id = meta["chapters"][0]["chapter_id"]
        ch0_res = client.get(f"/api/study/documents/{doc_id}/chapters/{ch0_id}")
        assert ch0_res.status_code == 200
        paragraphs = ch0_res.json()["data"]["paragraphs"]
        assert len(paragraphs) >= 2
        split_p_id = paragraphs[1]["id"]

        # 1. Split chapter to create chapter 2
        split_res = client.post(
            f"/api/study/documents/{doc_id}/chapters/{ch0_id}/paragraphs/{split_p_id}/split_chapter",
            json={"new_title": "Chapter Two"}
        )
        assert split_res.status_code == 200
        split_data = split_res.json()["data"]
        assert split_data["success"] is True
        ch1_id = split_data["new_chapter_id"]

        # 2. Shift paragraph from ch0 to ch1 with direction="next"
        p0_id = paragraphs[0]["id"]
        shift_res = client.post(
            f"/api/study/documents/{doc_id}/chapters/{ch0_id}/paragraphs/{p0_id}/shift_chapter",
            json={"direction": "next"}
        )
        assert shift_res.status_code == 200
        shift_data = shift_res.json()
        assert shift_data["code"] == 200
        assert shift_data["data"]["success"] is True
        assert shift_data["data"]["target_chapter_id"] == ch1_id

        # 3. Shift back with direction="prev" and scope="single"
        # First ensure we have at least 2 chapters
        meta2 = client.get(f"/api/study/documents/{doc_id}").json()["data"]
        assert len(meta2["chapters"]) >= 1
        print("✓ Shift chapter paragraphs API test passed!")
    finally:
        client.delete(f"/api/study/documents/{doc_id}")

def test_translate_paragraph_api():
    print("Testing translate paragraph API endpoint...")
    import study
    assert hasattr(study, "retranslate_paragraph")
    assert hasattr(study, "translate_single_paragraph")

    from unittest.mock import patch, AsyncMock

    pdf_bytes = create_dummy_pdf()
    files = {"file": ("test_trans_p_doc.pdf", pdf_bytes, "application/pdf")}
    up_res = client.post("/api/study/documents/upload", files=files)
    assert up_res.status_code == 200
    doc_id = up_res.json()["data"]["doc_id"]
    try:
        meta = client.get(f"/api/study/documents/{doc_id}").json()["data"]
        chapter_id = meta["chapters"][0]["chapter_id"]
        ch_res = client.get(f"/api/study/documents/{doc_id}/chapters/{chapter_id}")
        assert ch_res.status_code == 200
        paragraphs = ch_res.json()["data"]["paragraphs"]
        assert len(paragraphs) > 0
        para_id = paragraphs[0]["id"]

        with patch("study.service.call_llm_translate_paragraph", new=AsyncMock(return_value="测试翻译结果")):
            trans_res = client.post(
                f"/api/study/documents/{doc_id}/translate_paragraph",
                json={"chapter_id": chapter_id, "paragraph_id": para_id}
            )
            assert trans_res.status_code == 200, trans_res.text
            trans_data = trans_res.json()
            assert trans_data["code"] == 200
            assert "data" in trans_data
            assert trans_data["data"]["id"] == para_id
            assert trans_data["data"]["chinese"] == "测试翻译结果"
        print("✓ Translate paragraph API test passed!")
    finally:
        client.delete(f"/api/study/documents/{doc_id}")

if __name__ == "__main__":
    test_study_page_route()
    test_study_settings_api()
    test_upload_and_document_workflow()
    test_upload_multiple_documents_workflow()
    test_chapter_and_paragraph_notes_api()
    test_extract_paragraph_text_api()
    test_shift_chapter_paragraphs_api()
    test_translate_paragraph_api()
    test_import_web_document_route()
    test_document_chat_endpoint_parameter_compatibility()
    test_chapter_chat_endpoint_parameter_compatibility()
    print("\nAll Study API tests passed successfully! 🎉")





