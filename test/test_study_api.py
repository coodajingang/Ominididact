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

if __name__ == "__main__":
    test_study_page_route()
    test_study_settings_api()
    test_upload_and_document_workflow()
    print("\nAll Study API tests passed successfully! 🎉")
