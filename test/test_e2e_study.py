import os
import sys
import io
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fitz  # PyMuPDF
from PIL import Image
import study_service

def create_sample_english_pdf_with_image() -> bytes:
    doc = fitz.open()
    
    # Page 1
    page1 = doc.new_page()
    text_p1 = (
        "1. Introduction\n\n"
        "Deep neural networks have demon-\n"
        "strated state-of-the-art results across various complex compu-\n"
        "tational tasks.\n\n"
        "Despite their empirical achievements, deep learning frameworks\n"
        "require substantial training data and robust validation algorithms."
    )
    page1.insert_text((50, 72), text_p1, fontsize=12)
    
    # Insert a sample image on page 1
    img = Image.new("RGB", (200, 100), color=(60, 120, 220))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_rect = fitz.Rect(50, 200, 250, 300)
    page1.insert_image(img_rect, stream=img_byte_arr.getvalue())
    
    # Page 2
    page2 = doc.new_page()
    text_p2 = (
        "2. Architecture\n\n"
        "The proposed system incorporates multi-head self-attention mecha-\n"
        "nisms with layer normalization."
    )
    page2.insert_text((50, 72), text_p2, fontsize=12)
    
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def create_sample_chinese_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "一、项目背景与研究意义\n\n"
        "本项目旨在构建一套高效的多模态人工智能代理系统。\n\n"
        "系统能够支持文本与图像的联合理解与流式问答。"
    )
    # PyMuPDF uses 'china-s' for simplified Chinese built-in font
    page.insert_text((50, 72), text, fontname="china-s", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

async def run_e2e_tests():
    print("Running e2e document processing tests...")
    
    # Test 1: English PDF with embedded image
    print("\n--- Testing English PDF with Image ---")
    en_pdf_bytes = create_sample_english_pdf_with_image()
    meta = await study_service.initialize_document(en_pdf_bytes, "english_research_paper.pdf")
    doc_id = meta["doc_id"]
    print(f"Initialized doc: {doc_id}")
    
    # Extract content
    lang, chapters = study_service.extract_text_pdf_content(doc_id)
    print(f"Detected language: {lang}")
    assert lang == "en", f"Expected language 'en', got {lang}"
    print(f"Extracted {len(chapters)} chapters:")
    for ch in chapters:
        print(f"  - [{ch['chapter_id']}] {ch['title']} ({len(ch['paragraphs'])} items)")
        for p in ch["paragraphs"]:
            if p["type"] == "image":
                print(f"    * Image embedded: {p['image_url']}")
                assert os.path.exists(os.path.join(study_service.get_doc_dir(doc_id), "images", os.path.basename(p['image_url'])))
            else:
                print(f"    * Paragraph: {p['english'][:60]}...")
                # Verify de-hyphenation happened
                assert "demon-" not in p['english']
                assert "compu-" not in p['english']
                
    # Save chapter files and update meta
    meta["chapters"] = [{"chapter_id": ch["chapter_id"], "title": ch["title"]} for ch in chapters]
    study_service.save_doc_meta(doc_id, meta)
    for ch in chapters:
        study_service.write_chapter_files(doc_id, ch, lang)
        
    full_md = study_service.assemble_full_document_markdown(doc_id)
    assert "# 1. Introduction" in full_md or "Introduction" in full_md
    assert "![" in full_md
    print("✓ English PDF extraction & image preservation passed!")
    
    # Test 2: Chinese PDF
    print("\n--- Testing Chinese PDF ---")
    zh_pdf_bytes = create_sample_chinese_pdf()
    meta_zh = await study_service.initialize_document(zh_pdf_bytes, "chinese_report.pdf")
    doc_id_zh = meta_zh["doc_id"]
    
    lang_zh, chapters_zh = study_service.extract_text_pdf_content(doc_id_zh)
    print(f"Detected language: {lang_zh}")
    assert lang_zh == "zh", f"Expected language 'zh', got {lang_zh}"
    
    meta_zh["chapters"] = [{"chapter_id": ch["chapter_id"], "title": ch["title"]} for ch in chapters_zh]
    meta_zh["language"] = "zh"
    study_service.save_doc_meta(doc_id_zh, meta_zh)
    for ch in chapters_zh:
        study_service.write_chapter_files(doc_id_zh, ch, lang_zh)
    full_md_zh = study_service.assemble_full_document_markdown(doc_id_zh)
    print(f"Rendered Chinese Markdown:\n{full_md_zh}")
    assert "项目旨在构建一套高效的多模态人工智能代理系统" in full_md_zh
    print("✓ Chinese PDF extraction & bypass translation passed!")
    
    print("\nAll e2e tests passed successfully! 🎉")

if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
