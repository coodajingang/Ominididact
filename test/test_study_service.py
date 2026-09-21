import os
import sys
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import study_service

def test_repair_english_paragraph():
    print("Testing test_repair_english_paragraph...")
    # Test hyphenation at line breaks
    broken_text = (
        "Deep learning architectures have achieved remark-\n"
        "able performance across many domains, such as com-\n"
        "puter vision and natural language processing.\n\n"
        "In this work, we propose a novel transformer-based\n"
        "framework for document translation."
    )
    repaired = study_service.repair_english_paragraph(broken_text)
    
    assert "remarkable" in repaired, f"Hyphenation 'remark-able' should be merged, got: {repaired}"
    assert "computer" in repaired, f"Hyphenation 'com-puter' should be merged, got: {repaired}"
    assert "remark-\n" not in repaired
    assert "com-\n" not in repaired
    
    paras = repaired.split("\n\n")
    assert len(paras) == 2, f"Should have 2 natural paragraphs, got {len(paras)}"
    assert "Deep learning architectures have achieved remarkable performance across many domains, such as computer vision and natural language processing." == paras[0]
    print("✓ test_repair_english_paragraph passed!")

def test_detect_language():
    print("Testing test_detect_language...")
    en_sample = "Artificial intelligence is transforming modern scientific discovery and computational engineering."
    zh_sample = "人工智能正在深刻变革现代科学研究与计算工程领域的方方面面。"
    mixed_zh = "这是一篇关于 Deep Learning 模型的中文综述论文，分析其在各项 NLP 任务上的表现。"
    
    assert study_service.detect_language(en_sample) == "en"
    assert study_service.detect_language(zh_sample) == "zh"
    assert study_service.detect_language(mixed_zh) == "zh"
    print("✓ test_detect_language passed!")

def test_is_chapter_heading():
    print("Testing test_is_chapter_heading...")
    assert study_service.is_chapter_heading("Chapter 1. Introduction")
    assert study_service.is_chapter_heading("1.2 Related Work")
    assert study_service.is_chapter_heading("Abstract")
    assert study_service.is_chapter_heading("References")
    assert study_service.is_chapter_heading("一、研究背景与意义")
    assert not study_service.is_chapter_heading("This is a long sentence explaining the dataset and methods used in Section 2.")
    print("✓ test_is_chapter_heading passed!")

def test_render_chapter_markdown():
    print("Testing test_render_chapter_markdown...")
    ch_en = {
        "chapter_id": "ch_001",
        "title": "1. Introduction",
        "paragraphs": [
            {
                "id": "p_001_0001",
                "type": "text",
                "english": "Natural language processing models have evolved dramatically.",
                "chinese": "自然语言处理模型经历了巨大的演进发展。",
                "status": "completed"
            },
            {
                "id": "p_001_0002",
                "type": "image",
                "english": "![Figure 1-1](/api/study/documents/doc_test/images/p1_img1.png)",
                "chinese": "",
                "status": "completed"
            }
        ]
    }
    
    md_output = study_service.render_chapter_markdown(ch_en, language="en")
    print(f"Rendered Markdown:\n{md_output}")
    
    assert "# 1. Introduction" in md_output
    assert "Natural language processing models have evolved dramatically." in md_output
    assert "> 自然语言处理模型经历了巨大的演进发展。" in md_output
    assert "---" in md_output
    assert "![Figure 1-1]" in md_output
    print("✓ test_render_chapter_markdown passed!")

def test_chinese_document_rendering():
    print("Testing test_chinese_document_rendering...")
    ch_zh = {
        "chapter_id": "ch_001",
        "title": "第一章 概述",
        "paragraphs": [
            {
                "id": "p_001_0001",
                "type": "text",
                "english": "本文介绍了一种创新的深度学习分布式训练架构方案。",
                "chinese": "",
                "status": "completed"
            }
        ]
    }
    md_zh = study_service.render_chapter_markdown(ch_zh, language="zh")
    assert "# 第一章 概述" in md_zh
    assert "本文介绍了一种创新的深度学习分布式训练架构方案。" in md_zh
    assert "---" in md_zh
    assert ">" not in md_zh  # Chinese document has no translation blockquote
    print("✓ test_chinese_document_rendering passed!")

def test_settings_save_and_load():
    print("Testing test_settings_save_and_load...")
    settings = study_service.get_study_settings()
    assert "translation_prompt_template" in settings
    assert settings["model_call_delay"] >= 0.1
    
    # Update delay
    study_service.save_study_settings({"model_call_delay": 1.5})
    updated = study_service.get_study_settings()
    assert updated["model_call_delay"] == 1.5
    
    # Restore default 1.0
    study_service.save_study_settings({"model_call_delay": 1.0})
    assert study_service.get_study_settings()["model_call_delay"] == 1.0
    print("✓ test_settings_save_and_load passed!")

def test_formatted_pdf_extraction():
    print("Testing test_formatted_pdf_extraction with bold, italic, headings...")
    import fitz
    import shutil
    test_doc_id = "doc_test_formatting_999"
    doc_dir = study_service.get_doc_dir(test_doc_id)
    pdf_path = os.path.join(doc_dir, "original.pdf")
    
    doc = fitz.open()
    page = doc.new_page()
    # Heading
    page.insert_text((50, 60), "1. Introduction and Overview", fontsize=16, fontname="hebo")
    # Body with bold and italic
    page.insert_text((50, 100), "Deep learning relies on ", fontsize=10, fontname="helv")
    page.insert_text((160, 100), "neural networks", fontsize=10, fontname="hebo")
    page.insert_text((245, 100), " and ", fontsize=10, fontname="helv")
    page.insert_text((275, 100), "gradient descent.", fontsize=10, fontname="heit")
    doc.save(pdf_path)
    doc.close()
    
    lang, chapters = study_service.extract_text_pdf_content(test_doc_id)
    assert lang == "en"
    assert len(chapters) >= 1
    
    all_texts = [p.get("english", "") for ch in chapters for p in ch.get("paragraphs", [])]
    full_str = " ".join(all_texts)
    print("Extracted full text:", full_str)
    assert "**neural networks**" in full_str or "**neural networks" in full_str, f"Expected bold text in {full_str}"
    assert ("*gradient descent" in full_str or "_gradient descent" in full_str), f"Expected italic text in {full_str}"
    
    # Cleanup
    shutil.rmtree(doc_dir, ignore_errors=True)
    print("✓ test_formatted_pdf_extraction passed!")

def test_colon_and_short_block_merging():
    print("Testing test_colon_and_short_block_merging...")
    blocks = [
        {"page": 1, "type": "text", "content": "Integrity can be examined from three perspectives:"},
        {"page": 1, "type": "text", "content": "First, from the perspective of data storage, cryptographic signatures guarantee immutability across distributed ledgers."},
        {"page": 1, "type": "text", "content": "Second, execution integrity ensures"},
        {"page": 1, "type": "text", "content": "that virtual machine state transitions conform strictly to the consensus protocol specification."}
    ]
    merged = study_service.merge_broken_blocks(blocks, lang="en")
    print("Merged blocks count:", len(merged))
    for idx, b in enumerate(merged):
        print(f"Block {idx+1}: {b['content']}")
    
    # "Integrity can be examined from three perspectives:" must be merged with "First..."
    assert len(merged) <= 2
    assert "Integrity can be examined from three perspectives: First, from the perspective" in merged[0]["content"]
    assert "Second, execution integrity ensures that virtual machine state transitions" in merged[0]["content"] or "Second, execution integrity ensures that virtual machine state transitions" in merged[1]["content"]
    print("✓ test_colon_and_short_block_merging passed!")

def test_line_spacing_threshold_and_indent():
    print("Testing test_line_spacing_threshold_and_indent...")
    # Synthetic lines: Line 1 & Line 2 are close (line spacing < 1.4 * height -> same paragraph)
    # Line 3 is separated by large vertical gap (dy > 1.4 * height -> separate paragraph)
    lines = [
        {
            "bbox": (50, 100, 450, 114),
            "formatted_text": "This is the first line of the opening paragraph in the section.",
            "plain_text": "This is the first line of the opening paragraph in the section.",
            "font_size": 10.0,
            "is_bold": False, "is_italic": False, "is_mono": False,
            "is_heading": False, "is_bullet": False, "is_caption": False, "is_code": False
        },
        {
            "bbox": (50, 118, 450, 132),  # dy = 118 - 114 = 4 < 1.4 * 14 -> merge!
            "formatted_text": "This is the second line continuing the exact same discussion smoothly.",
            "plain_text": "This is the second line continuing the exact same discussion smoothly.",
            "font_size": 10.0,
            "is_bold": False, "is_italic": False, "is_mono": False,
            "is_heading": False, "is_bullet": False, "is_caption": False, "is_code": False
        },
        {
            "bbox": (50, 165, 450, 179),  # dy = 165 - 132 = 33 > 1.4 * 14 -> split!
            "formatted_text": "A completely new paragraph starts here due to substantial paragraph spacing.",
            "plain_text": "A completely new paragraph starts here due to substantial paragraph spacing.",
            "font_size": 10.0,
            "is_bold": False, "is_italic": False, "is_mono": False,
            "is_heading": False, "is_bullet": False, "is_caption": False, "is_code": False
        }
    ]
    blocks = study_service.group_lines_into_page_blocks(lines, page_num=1, body_size=10.0, body_line_height=14.0, page_width=595.0)
    print(f"Grouped into {len(blocks)} blocks")
    assert len(blocks) == 2, f"Expected 2 paragraphs from line-spacing threshold, got {len(blocks)}"
    assert "This is the first line of the opening paragraph in the section. This is the second line" in blocks[0]["content"]
    assert "A completely new paragraph starts here" in blocks[1]["content"]
    print("✓ test_line_spacing_threshold_and_indent passed!")

def test_cross_page_hyphenation_and_continuation():
    print("Testing test_cross_page_hyphenation_and_continuation...")
    # Page 1 ends with hyphen: 'archi-'
    # Page 2 starts with: 'tecture provides fault tolerance across nodes.'
    p1_blocks = [
        {
            "page": 1,
            "type": "text",
            "content": "In distributed consensus protocols, the modern micro-service archi-",
            "is_heading": False,
            "no_translate": False
        }
    ]
    p2_blocks = [
        {
            "page": 2,
            "type": "text",
            "content": "tecture provides fault tolerance across nodes. Furthermore, state transitions are validated.",
            "is_heading": False,
            "no_translate": False
        }
    ]
    stitched = study_service.stitch_blocks_across_pages([p1_blocks, p2_blocks], lang="en")
    print("Stitched hyphenation count:", len(stitched))
    print("Content:", stitched[0]["content"])
    assert len(stitched) == 1
    assert "architecture provides fault tolerance" in stitched[0]["content"], f"Word should be stitched, got: {stitched[0]['content']}"

    # Page 2 ends with non-terminal ending: 'networks rely heavily on'
    # Page 3 starts with: 'backpropagation and gradient descent.'
    p3_blocks = [
        {
            "page": 3,
            "type": "text",
            "content": "backpropagation and gradient descent.",
            "is_heading": False,
            "no_translate": False
        }
    ]
    stitched_continuation = study_service.stitch_blocks_across_pages([
        [{"page": 2, "type": "text", "content": "Deep neural networks rely heavily on", "is_heading": False, "no_translate": False}],
        p3_blocks
    ], lang="en")
    assert len(stitched_continuation) == 1
    assert stitched_continuation[0]["content"] == "Deep neural networks rely heavily on backpropagation and gradient descent."
    print("✓ test_cross_page_hyphenation_and_continuation passed!")

def test_logical_boundary_classification():
    print("Testing test_logical_boundary_classification...")
    assert study_service.is_bullet_line("1. First item in ordered list")
    assert study_service.is_bullet_line("• Bullet point in unordered list")
    assert study_service.is_bullet_line("- Hyphenated item")
    assert study_service.is_bullet_line("(a) Sub-item description")
    assert not study_service.is_bullet_line("Normal text line describing algorithms.")

    assert study_service.is_caption_line("Figure 1: Architecture of Transformer.")
    assert study_service.is_caption_line("Fig. 2. Performance benchmark across datasets.")
    assert study_service.is_caption_line("Table 3: Hyperparameter specifications.")
    assert not study_service.is_caption_line("We can observe that the results in Table 3 are impressive.")

    assert study_service.is_code_or_formula_line("def forward(self, x):", is_mono=True)
    assert study_service.is_code_or_formula_line("import torch.nn as nn", is_mono=False)
    print("✓ test_logical_boundary_classification passed!")

def test_sliding_context_prompt_and_parsing():
    print("Testing test_sliding_context_prompt_and_parsing...")
    # 1. Test Chinese output extraction from single and multi section responses
    ans_single = "> 自然语言处理模型经历了巨大发展。\n\n---"
    parsed1 = study_service.parse_translated_chinese(ans_single, "Natural language processing models have evolved.")
    assert parsed1 == "自然语言处理模型经历了巨大发展。"

    ans_multi = (
        "> 前文段落译文\n\n---\n\n"
        "> 目标段落精准中文译文展示。"
    )
    parsed2 = study_service.parse_translated_chinese(ans_multi, "Target paragraph text.")
    assert parsed2 == "目标段落精准中文译文展示。"

    # 3. Test multi-paragraph multi-section translation (user's exact bug scenario)
    user_bug_sample = (
        "> 欢迎来到本课程关于访问与授权的章节。\n\n---\n\n"
        "> 本章首先通过一节简短课程介绍问责制。\n\n---\n\n"
        "> 接下来我们将进入逻辑访问控制部分。\n\n---\n\n"
        "> 访问控制和授权与我们下一节课密切相关。\n\n---\n\n"
        "> 最后，我们将深入探讨密码攻击。\n\n---\n\n"
        "> 最后，在本章结束时我们将进行一个简短测验。"
    )
    parsed3 = study_service.parse_translated_chinese(user_bug_sample, "Target English")
    assert "欢迎来到本课程关于访问与授权的章节。" in parsed3
    assert "本章首先通过一节简短课程介绍问责制。" in parsed3
    assert "接下来我们将进入逻辑访问控制部分。" in parsed3
    assert "访问控制和授权与我们下一节课密切相关。" in parsed3
    assert "最后，我们将深入探讨密码攻击。" in parsed3
    assert "最后，在本章结束时我们将进行一个简短测验。" in parsed3
    assert len(parsed3.split("\n\n")) == 6
    print("✓ test_sliding_context_prompt_and_parsing passed!")



def test_context_expansion_chat():
    print("Testing test_context_expansion_chat...")
    # Create temporary mock chapter to test surrounding paragraph extraction
    doc_id = "test_doc_ctx"
    doc_dir = study_service.get_doc_dir(doc_id)
    ch_data = {
        "chapter_id": "ch_001",
        "title": "Context Test Chapter",
        "paragraphs": [
            {"id": "p_1", "english": "Paragraph 1: Background info.", "type": "text"},
            {"id": "p_2", "english": "Paragraph 2: Detailed setup.", "type": "text"},
            {"id": "p_3", "english": "Paragraph 3: Target core paragraph to study.", "type": "text"},
            {"id": "p_4", "english": "Paragraph 4: Following consequence.", "type": "text"},
            {"id": "p_5", "english": "Paragraph 5: Subsequent conclusion.", "type": "text"}
        ]
    }
    study_service.write_chapter_files(doc_id, ch_data, "en")
    
    # Verify chat_with_paragraph returns async generator with prev=2, next=2
    async def run_chat():
        chunks = []
        gen = study_service.chat_with_paragraph(
            doc_id=doc_id,
            chapter_id="ch_001",
            paragraph_id="p_3",
            user_message="Explain core concept",
            prev_count=2,
            next_count=2
        )
        assert hasattr(gen, "__aiter__"), "Must return an async generator"
        
    asyncio.run(run_chat())
    study_service.delete_document(doc_id)
    print("✓ test_context_expansion_chat passed!")

def test_notes_and_batch_and_chapter_chat():
    print("Testing test_notes_and_batch_and_chapter_chat...")
    doc_id = "test_doc_modular"
    study_service.get_doc_dir(doc_id)
    ch_data = {
        "chapter_id": "ch_001",
        "title": "Modular Architecture Chapter",
        "header_notes": [],
        "footer_notes": [],
        "paragraphs": [
            {"id": "p_1", "english": "Paragraph 1: Testing modular notes.", "chinese": "", "status": "pending", "type": "text", "notes": []},
            {"id": "p_2", "english": "Paragraph 2: Another paragraph.", "chinese": "", "status": "pending", "type": "text", "notes": []}
        ]
    }
    study_service.write_chapter_files(doc_id, ch_data, "en")
    
    # 1. Test paragraph multi-notes
    n1 = study_service.add_paragraph_note(doc_id, "ch_001", "p_1", "First note for p1")
    assert n1["content"] == "First note for p1"
    n2 = study_service.add_paragraph_note(doc_id, "ch_001", "p_1", "Second note for p1")
    assert n2["content"] == "Second note for p1"
    
    # Test update
    up_n = study_service.update_paragraph_note(doc_id, "ch_001", "p_1", n1["id"], "Updated first note")
    assert up_n["content"] == "Updated first note"
    
    # Test chapter header & footer notes
    hn = study_service.add_chapter_note(doc_id, "ch_001", "header", "Chapter Header Summary 1")
    fn = study_service.add_chapter_note(doc_id, "ch_001", "footer", "Chapter Footer Review 1")
    assert hn["content"] == "Chapter Header Summary 1"
    assert fn["content"] == "Chapter Footer Review 1"
    
    # Verify markdown rendering with notes
    ch_loaded = study_service.load_chapter_data(doc_id, "ch_001")
    md = study_service.render_chapter_markdown(ch_loaded, "en")
    assert "本章总览与学习总结" in md
    assert "Updated first note" in md
    assert "Second note for p1" in md
    assert "本章回顾与考点总结" in md
    
    # 2. Test batch translation status
    st = study_service.get_chapter_translation_status(doc_id, "ch_001")
    assert st["total"] == 2
    assert st["completed"] == 0
    assert st["is_running"] is False
    
    # 3. Test chapter chat generator
    gen = study_service.stream_chapter_chat(doc_id, "ch_001", "Summarize this chapter")
    assert hasattr(gen, "__aiter__"), "Chapter chat must return an async generator"
    
    # 4. Test delete note
    del_res = study_service.delete_paragraph_note(doc_id, "ch_001", "p_1", n2["id"])
    assert del_res is True
    
    study_service.delete_document(doc_id)
    print("✓ test_notes_and_batch_and_chapter_chat passed!")

def test_document_settings_isolation_and_reset():
    print("Testing test_document_settings_isolation_and_reset...")
    doc_id = "test_doc_settings_iso"
    doc_dir = study_service.get_doc_dir(doc_id)
    
    # 1. Global settings baseline
    global_s = study_service.get_study_settings()
    assert global_s.get("is_doc_level") is False
    
    # 2. Document inherits global defaults initially (auto-copied to doc-level settings.json)
    doc_s = study_service.get_study_settings(doc_id)
    assert doc_s.get("is_doc_level") is True
    assert doc_s["model_call_delay"] == global_s["model_call_delay"]
    
    # 3. Save custom settings for this document
    custom_para_prompts = [{"label": "🔬 专有测试提问", "prompt": "测试提问详情"}]
    custom_chapter_prompts = [{"label": "🗺️ 专有章节主线", "prompt": "测试全章主线"}]
    study_service.save_study_settings({
        "model_call_delay": 2.5,
        "chat_quick_prompts": custom_para_prompts,
        "chapter_chat_quick_prompts": custom_chapter_prompts
    }, doc_id=doc_id)
    
    # 4. Verify document settings are updated and isolated
    doc_s_updated = study_service.get_study_settings(doc_id)
    assert doc_s_updated.get("is_doc_level") is True
    assert doc_s_updated["model_call_delay"] == 2.5
    assert len(doc_s_updated["chat_quick_prompts"]) == 1
    assert doc_s_updated["chat_quick_prompts"][0]["label"] == "🔬 专有测试提问"
    assert len(doc_s_updated["chapter_chat_quick_prompts"]) == 1
    assert doc_s_updated["chapter_chat_quick_prompts"][0]["label"] == "🗺️ 专有章节主线"
    
    # Global settings remain untouched
    global_s_check = study_service.get_study_settings()
    assert global_s_check.get("is_doc_level") is False
    assert global_s_check["model_call_delay"] != 2.5
    
    # 5. Reset document settings to global
    reset_res = study_service.reset_doc_settings(doc_id)
    assert reset_res["model_call_delay"] == global_s["model_call_delay"]
    doc_s_after_reset = study_service.get_study_settings(doc_id)
    assert doc_s_after_reset["model_call_delay"] == global_s["model_call_delay"]
    
    study_service.delete_document(doc_id)
    print("✓ test_document_settings_isolation_and_reset passed!")

def test_export_markdown_and_html():
    print("Testing test_export_markdown_and_html...")
    doc_id = "test_doc_export"
    doc_dir = study_service.get_doc_dir(doc_id)
    
    # Setup mock document metadata
    meta = {
        "doc_id": doc_id,
        "filename": "Sample_Study_Document.pdf",
        "language": "en",
        "total_pages": 5,
        "status": "completed",
        "chapters": [
            {"chapter_id": "ch_001", "title": "Chapter 1: Foundational Theories", "paragraph_count": 2},
            {"chapter_id": "ch_002", "title": "Chapter 2: Empirical Evaluations", "paragraph_count": 1}
        ]
    }
    study_service.save_doc_meta(doc_id, meta)
    
    # Create a dummy image file
    img_dir = os.path.join(doc_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    dummy_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    with open(os.path.join(img_dir, "figure1.png"), "wb") as f:
        f.write(dummy_png_bytes)
        
    # Setup chapter 1 with an image paragraph
    ch1 = {
        "chapter_id": "ch_001",
        "title": "Chapter 1: Foundational Theories",
        "header_notes": [{"id": "hn1", "content": "Chapter 1 Macro Blueprint", "created_at": "2026-09-09"}],
        "footer_notes": [{"id": "fn1", "content": "Chapter 1 Exam Highlights", "created_at": "2026-09-09"}],
        "paragraphs": [
            {
                "id": "p_1_1",
                "type": "text",
                "english": "Statistical learning models form the mathematical backbone of modern machine intelligence.",
                "chinese": "统计学习模型构成了现代机器智能的数学基石。",
                "status": "completed",
                "notes": [{"id": "n1", "content": "Key Term: Statistical learning", "created_at": "2026-09-09"}]
            },
            {
                "id": "p_1_img",
                "type": "image",
                "english": "![Figure 1: Neural Architecture](/api/study/documents/" + doc_id + "/images/figure1.png)",
                "chinese": "",
                "status": "completed",
                "image_url": "/api/study/documents/" + doc_id + "/images/figure1.png"
            },
            {
                "id": "p_1_2",
                "type": "text",
                "english": "Generalization error measures how well algorithms perform on unseen data.",
                "chinese": "泛化误差衡量算法在未知数据上的表现能力。",
                "status": "completed",
                "notes": []
            }
        ]
    }
    study_service.write_chapter_files(doc_id, ch1, "en")
    
    # Setup chapter 2
    ch2 = {
        "chapter_id": "ch_002",
        "title": "Chapter 2: Empirical Evaluations",
        "header_notes": [],
        "footer_notes": [],
        "paragraphs": [
            {
                "id": "p_2_1",
                "type": "text",
                "english": "We conduct extensive experiments across multiple benchmark datasets.",
                "chinese": "我们在多个基准数据集上进行了广泛的实验。",
                "status": "completed",
                "notes": []
            }
        ]
    }
    study_service.write_chapter_files(doc_id, ch2, "en")
    
    # 1. Test get_image_base64_data_uri
    b64_uri = study_service.get_image_base64_data_uri(doc_id, "figure1.png")
    assert b64_uri is not None
    assert b64_uri.startswith("data:image/png;base64,")
    
    # 2. Test assemble_full_document_markdown (Base64 Mode)
    full_md_b64 = study_service.assemble_full_document_markdown(doc_id, image_mode="base64")
    assert isinstance(full_md_b64, str)
    assert len(full_md_b64) > 0, "Markdown export string must not be empty"
    assert "# Sample_Study_Document.pdf" in full_md_b64
    assert "data:image/png;base64," in full_md_b64, "Base64 image must be embedded in Markdown"
    assert "Chapter 1: Foundational Theories" in full_md_b64
    assert "统计学习模型构成了现代机器智能的数学基石。" in full_md_b64
    
    # 3. Test assemble_full_document_markdown (Relative Mode)
    full_md_rel = study_service.assemble_full_document_markdown(doc_id, image_mode="relative")
    assert "images/figure1.png" in full_md_rel, "Relative images/ link must be present in relative mode"
    assert "data:image/png;base64," not in full_md_rel
    
    # 4. Test assemble_full_document_zip
    import zipfile
    import io
    zip_bytes = study_service.assemble_full_document_zip(doc_id)
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        print("Zip contents:", namelist)
        assert any(n.endswith(".md") for n in namelist), "Zip must contain markdown document"
        assert "images/figure1.png" in namelist, "Zip must contain image inside images/ directory"
        extracted_img = zf.read("images/figure1.png")
        assert extracted_img == dummy_png_bytes, "Extracted image content must match original"
    
    # 5. Test assemble_full_document_html
    full_html = study_service.assemble_full_document_html(doc_id)
    assert isinstance(full_html, str)
    assert len(full_html) > 0, "HTML export string must not be empty"
    assert "<!DOCTYPE html>" in full_html
    assert "Sample_Study_Document.pdf" in full_html
    assert "ch_ch_001" in full_html  # TOC anchor link
    assert "data:image/png;base64," in full_html, "Base64 image must be embedded in HTML"
    assert "content-img" in full_html
    assert "image-block" in full_html
    assert "@media print" in full_html  # Print style sheet included
    assert "reader-topbar" in full_html, "Must contain sticky reader topbar"
    assert "quick-scroll-navigator" in full_html, "Must contain quick scroll navigator"
    assert "theme-select" in full_html, "Must contain theme selector"
    assert "adjustFontSize" in full_html, "Must contain font size adjust logic"
    assert "setReaderWidth" in full_html, "Must contain width adjust logic"

    # 6. Test assemble_offline_flashcards_html
    from study.flashcard_manager import create_flashcard
    create_flashcard(doc_id, {
        "front": "What is {{Implicit Deny}}?",
        "back": "A default security posture where access is blocked unless explicitly permitted.",
        "type": "cloze",
        "chapter_id": "ch_001",
        "tags": ["CISSP", "Access Control"]
    })
    offline_fc_html = study_service.assemble_offline_flashcards_html(doc_id)
    assert isinstance(offline_fc_html, str)
    assert len(offline_fc_html) > 0
    assert "window.OFFLINE_FLASHCARDS_DATA" in offline_fc_html, "Offline flashcard HTML must inject data payload"
    assert "Implicit Deny" in offline_fc_html
    assert "isOfflineMode" in offline_fc_html

    # 7. Test assemble_static_site_zip
    site_zip = study_service.assemble_static_site_zip(doc_id)
    assert isinstance(site_zip, bytes)
    assert len(site_zip) > 0
    with zipfile.ZipFile(io.BytesIO(site_zip), "r") as szf:
        site_files = szf.namelist()
        print("Static site zip files:", site_files)
        assert "index.html" in site_files, "Static site must include index.html"
        assert "flashcards.html" in site_files, "Static site must include flashcards.html"
        assert "README.md" in site_files, "Static site must include deployment README.md"
        assert len(szf.read("index.html")) > 0
        assert len(szf.read("flashcards.html")) > 0
        assert len(szf.read("README.md")) > 0

    # 8. Test assemble_incremental_patch_zip
    patch_zip = study_service.assemble_incremental_patch_zip(doc_id)
    assert isinstance(patch_zip, bytes)
    assert len(patch_zip) > 0
    with zipfile.ZipFile(io.BytesIO(patch_zip), "r") as pzf:
        patch_files = pzf.namelist()
        print("Patch zip files:", patch_files)
        assert f"docs/{doc_id}/index.html" in patch_files
        assert f"docs/{doc_id}/flashcards.html" in patch_files
        assert "patch_entry.json" in patch_files
        assert "README_PATCH.md" in patch_files
        patch_entry_data = json.loads(pzf.read("patch_entry.json").decode("utf-8"))
        assert patch_entry_data["id"] == doc_id
        assert patch_entry_data["path"] == f"docs/{doc_id}/index.html"
        assert patch_entry_data["flashcards_path"] == f"docs/{doc_id}/flashcards.html"
        # Verify portal_link back to hall
        sub_index_html = pzf.read(f"docs/{doc_id}/index.html").decode("utf-8")
        assert 'id="link-portal"' in sub_index_html
        sub_fc_html = pzf.read(f"docs/{doc_id}/flashcards.html").decode("utf-8")
        assert 'portal_link' in sub_fc_html

    # 9. Test assemble_library_site_zip
    lib_zip = study_service.assemble_library_site_zip([doc_id], site_title="测试研学文库")
    assert isinstance(lib_zip, bytes)
    assert len(lib_zip) > 0
    with zipfile.ZipFile(io.BytesIO(lib_zip), "r") as lzf:
        lib_files = lzf.namelist()
        print("Library site zip files:", lib_files)
        assert "index.html" in lib_files
        assert "docs.json" in lib_files
        assert "README.md" in lib_files
        assert f"docs/{doc_id}/index.html" in lib_files
        assert f"docs/{doc_id}/flashcards.html" in lib_files
        docs_json_data = json.loads(lzf.read("docs.json").decode("utf-8"))
        assert len(docs_json_data) == 1
        assert docs_json_data[0]["id"] == doc_id
        portal_html = lzf.read("index.html").decode("utf-8")
        assert "测试研学文库" in portal_html
        assert "docs.json" in portal_html
    
    study_service.delete_document(doc_id)
    print("✓ test_export_markdown_and_html passed!")

def test_chat_manager_persistence_and_streaming():
    print("Testing test_chat_manager_persistence_and_streaming...")
    doc_id = "test_doc_chat_mgr"
    doc_dir = study_service.get_doc_dir(doc_id)
    
    # 1. Test basic CRUD
    initial_history = study_service.load_chat_history(doc_dir, "paragraph", "ch_001", "p_1")
    assert initial_history == []
    
    study_service.append_chat_message(doc_dir, "paragraph", "ch_001", "p_1", "user", "What is gradient descent?")
    study_service.append_chat_message(doc_dir, "paragraph", "ch_001", "p_1", "assistant", "Gradient descent is an optimization algorithm.")
    
    h1 = study_service.load_chat_history(doc_dir, "paragraph", "ch_001", "p_1")
    assert len(h1) == 2
    assert h1[0]["role"] == "user"
    assert h1[0]["content"] == "What is gradient descent?"
    assert h1[1]["role"] == "assistant"
    assert h1[1]["content"] == "Gradient descent is an optimization algorithm."
    
    # Clear history
    del_ok = study_service.clear_chat_history(doc_dir, "paragraph", "ch_001", "p_1")
    assert del_ok is True
    assert study_service.load_chat_history(doc_dir, "paragraph", "ch_001", "p_1") == []
    
    # 2. Test stream_and_persist end-to-end
    async def mock_llm_stream():
        yield 'data: {"choices":[{"delta":{"content":"Deep "}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"neural "}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"networks."}}]}\n\n'
        yield 'data: [DONE]\n\n'
        
    async def run_stream_test():
        collected_chunks = []
        gen = study_service.stream_and_persist(
            doc_dir=doc_dir,
            chat_type="chapter",
            chapter_id="ch_001",
            paragraph_id=None,
            user_message="Summarize network structures",
            stream_generator=mock_llm_stream()
        )
        async for chunk in gen:
            collected_chunks.append(chunk)
            
        # Give asyncio background task a moment to finish file write if needed
        await asyncio.sleep(0.05)
        
        # Verify chunks received
        assert len(collected_chunks) == 4
        # Verify persistent history was automatically saved
        ch_hist = study_service.load_chat_history(doc_dir, "chapter", "ch_001", None)
        assert len(ch_hist) == 2
        assert ch_hist[0]["role"] == "user"
        assert ch_hist[0]["content"] == "Summarize network structures"
        assert ch_hist[1]["role"] == "assistant"
        assert ch_hist[1]["content"] == "Deep neural networks."
        
    asyncio.run(run_stream_test())
    
    # 3. Test background disconnect resilience
    async def mock_slow_llm_stream():
        yield 'data: {"choices":[{"delta":{"content":"Part "}}]}\n\n'
        await asyncio.sleep(0.02)
        yield 'data: {"choices":[{"delta":{"content":"One, "}}]}\n\n'
        await asyncio.sleep(0.02)
        yield 'data: {"choices":[{"delta":{"content":"Part Two."}}]}\n\n'
        yield 'data: [DONE]\n\n'

    async def run_disconnect_test():
        gen = study_service.stream_and_persist(
            doc_dir=doc_dir,
            chat_type="paragraph",
            chapter_id="ch_001",
            paragraph_id="p_9",
            user_message="Question before disconnect",
            stream_generator=mock_slow_llm_stream()
        )
        # Consume ONLY the first chunk and then exit (simulating client drawer closed)
        first_chunk = await gen.__anext__()
        assert "Part " in first_chunk
        # Force closing the generator (triggers GeneratorExit)
        await gen.aclose()
        
        # Wait for drain_in_background task to complete in the background
        await asyncio.sleep(0.15)
        
        # Verify history captured the full message despite early client disconnect!
        p9_hist = study_service.load_chat_history(doc_dir, "paragraph", "ch_001", "p_9")
        assert len(p9_hist) == 2
        assert p9_hist[0]["role"] == "user"
        assert p9_hist[0]["content"] == "Question before disconnect"
        assert p9_hist[1]["role"] == "assistant"
        assert p9_hist[1]["content"] == "Part One, Part Two."
        
    asyncio.run(run_disconnect_test())
    
    study_service.delete_document(doc_id)
    print("✓ test_chat_manager_persistence_and_streaming passed!")

def test_txt_and_markdown_support():
    print("Testing test_txt_and_markdown_support...")
    
    # 1. Test multi-encoding decoding (UTF-8, UTF-8 BOM, GBK)
    import codecs
    utf8_bytes = "这是标准的UTF-8文本内容。".encode("utf-8")
    assert study_service.decode_text_bytes(utf8_bytes) == "这是标准的UTF-8文本内容。"
    
    bom_bytes = codecs.BOM_UTF8 + "带BOM的UTF-8文本。".encode("utf-8")
    assert study_service.decode_text_bytes(bom_bytes) == "带BOM的UTF-8文本。"
    
    gbk_bytes = "这是Windows常见的GBK中文编码文献内容。".encode("gbk")
    assert study_service.decode_text_bytes(gbk_bytes) == "这是Windows常见的GBK中文编码文献内容。"
    
    # 2. Test Markdown parsing with Code Blocks, Tables, and Chapters
    md_content = """# Overview of Systems

This document introduces modern distributed systems and concepts.

Here is an architectural diagram:
![Architecture Diagram](images/sys_arch.png)

```python
def init_cluster():
    # Blank line inside code block must not split the code!

    nodes = ["node1", "node2"]
    return nodes
```

| Component | Status | Role |
| --- | --- | --- |
| Node A | Active | Primary |
| Node B | Standby | Secondary |

## Deep Dive into Consensus

Paxos and Raft represent two foundational consensus protocols.

### Raft Algorithm
Raft achieves consensus via leader election and log replication.
"""
    lang, md_chapters = study_service.parse_markdown_content(md_content, "doc_test_md")
    assert lang == "en"
    assert len(md_chapters) == 2
    assert "Overview of Systems" in md_chapters[0]["title"]
    assert "Deep Dive into Consensus" in md_chapters[1]["title"]
    
    ch1_paras = md_chapters[0]["paragraphs"]
    # Check that code block was preserved intact as a code type
    code_paras = [p for p in ch1_paras if p.get("type") == "code"]
    assert len(code_paras) == 1
    assert "def init_cluster():" in code_paras[0]["english"]
    assert "nodes = [\"node1\", \"node2\"]" in code_paras[0]["english"]
    assert code_paras[0]["no_translate"] is True  # Code block should not be translated by default
    
    # Check table was preserved as table type
    table_paras = [p for p in ch1_paras if p.get("type") == "table"]
    assert len(table_paras) == 1
    assert "| Node A |" in table_paras[0]["english"]
    
    # Check image was preserved
    img_paras = [p for p in ch1_paras if p.get("type") == "image"]
    assert len(img_paras) == 1
    assert "images/sys_arch.png" in img_paras[0]["english"]

    # 3. Test TXT parsing with chapter headings
    txt_content = """Chapter 1. Background and Motivation

Deep neural networks have reshaped computing paradigms in the modern era.
They require substantial compute power.

Chapter 2. Algorithmic Innovations

We propose a pruned quantization strategy to reduce latency.
The experimental results demonstrate notable efficiency gains.
"""
    txt_lang, txt_chapters = study_service.parse_txt_content(txt_content, "doc_test_txt")
    assert txt_lang == "en"
    assert len(txt_chapters) == 2
    assert "Chapter 1" in txt_chapters[0]["title"]
    assert "Chapter 2" in txt_chapters[1]["title"]
    assert len(txt_chapters[0]["paragraphs"]) == 2
    assert txt_chapters[0]["paragraphs"][0]["is_heading"] is True
    assert txt_chapters[0]["paragraphs"][1]["is_heading"] is False
    assert len(txt_chapters[1]["paragraphs"]) == 2

    # 4. Test pipeline integration with .md upload
    async def run_pipeline_test():
        # Initialize Markdown doc
        md_meta = await study_service.initialize_document(md_content.encode("utf-8"), "distributed_systems.md")
        md_doc_id = md_meta["doc_id"]
        assert md_meta["file_type"] == "md"
        assert md_meta["is_scanned"] is False
        
        # Run pipeline
        await study_service.process_document_pipeline(md_doc_id)
        
        # Verify result
        final_meta = study_service.load_doc_meta(md_doc_id)
        assert final_meta["status"] == "completed"
        assert len(final_meta["chapters"]) == 2
        assert final_meta["total_paragraphs"] > 0
        
        # Verify full markdown was assembled
        doc_dir = study_service.get_doc_dir(md_doc_id)
        bilingual_md_path = os.path.join(doc_dir, "full_bilingual.md")
        assert os.path.isfile(bilingual_md_path)
        with open(bilingual_md_path, "r", encoding="utf-8") as f:
            bilingual_text = f.read()
        assert "Overview of Systems" in bilingual_text
        assert "Deep Dive into Consensus" in bilingual_text
        
        study_service.delete_document(md_doc_id)

        # Initialize GBK TXT doc
        gbk_sample = """第一章 绪论与研究背景

随着大语言模型技术的快速发展，跨语言学术阅读与文献分析成为重要的科研辅助工具。

第二章 系统设计与实现

本系统基于异步微服务架构设计，支持多种文件格式的高效解析与双语对照呈现。
"""
        txt_meta = await study_service.initialize_document(gbk_sample.encode("gbk"), "chinese_report.txt")
        txt_doc_id = txt_meta["doc_id"]
        assert txt_meta["file_type"] == "txt"
        assert txt_meta["is_scanned"] is False
        
        await study_service.process_document_pipeline(txt_doc_id)
        txt_final_meta = study_service.load_doc_meta(txt_doc_id)
        assert txt_final_meta["status"] == "completed"
        assert txt_final_meta["language"] == "zh"
        assert len(txt_final_meta["chapters"]) == 2
        
        study_service.delete_document(txt_doc_id)

    asyncio.run(run_pipeline_test())
    print("✓ test_txt_and_markdown_support passed!")

def test_batch_translation_interruption_and_cissp_prompt():
    print("Testing test_batch_translation_interruption_and_cissp_prompt...")
    
    # 1. Test CISSP Prompt contains necessary constraints
    prompt = study_service.DEFAULT_TRANSLATION_PROMPT
    assert "仅输出译文，严禁输出原文" in prompt
    assert "CISSP" in prompt
    assert "信息安全" in prompt
    
    # 2. Test default settings
    settings = study_service.get_study_settings()
    assert settings.get("llm_source") in ("proxy", "openai_compatible", "lm_studio"), f"Default llm_source should be 'proxy', 'openai_compatible' or 'lm_studio', got: {settings.get('llm_source')}"
    
    # 3. Test batch translation interruption: already translated paragraphs are NEVER lost!
    doc_id = "test_doc_batch_stop"
    doc_dir = study_service.get_doc_dir(doc_id)
    ch_data = {
        "chapter_id": "ch_001",
        "title": "Access Control Test",
        "paragraphs": [
            {
                "id": "p_1",
                "type": "text",
                "english": "Accountability is a fundamental tenet of security.",
                "chinese": "问责制是安全的基本原则。",
                "status": "completed"
            },
            {
                "id": "p_2",
                "type": "text",
                "english": "Implicit deny ensures that anything not explicitly permitted is forbidden.",
                "chinese": "",
                "status": "pending"
            },
            {
                "id": "p_3",
                "type": "text",
                "english": "Separation of duties prevents fraud by requiring multiple individuals.",
                "chinese": "",
                "status": "pending"
            }
        ]
    }
    study_service.write_chapter_files(doc_id, ch_data, "en")
    meta = {
        "doc_id": doc_id,
        "filename": "test.txt",
        "file_type": "txt",
        "language": "en",
        "total_paragraphs": 3,
        "translated_paragraphs": 1,
        "chapters": [{"chapter_id": "ch_001", "title": "Access Control Test"}]
    }
    study_service.save_doc_meta(doc_id, meta)
    
    # Test stopping translation: simulate stop_event set
    stop_event = asyncio.Event()
    stop_event.set() # already stopped
    
    from study.batch_translator import _run_chapter_batch_translation
    asyncio.run(_run_chapter_batch_translation(doc_id, "ch_001", stop_event))
    
    # Verify: ch_001.json must STILL have p_1 translated! Never wiped out!
    ch_path = os.path.join(doc_dir, "chapters", "ch_001.json")
    with open(ch_path, "r", encoding="utf-8") as f:
        ch_after = json.load(f)
    assert ch_after["paragraphs"][0]["chinese"] == "问责制是安全的基本原则。"
    assert ch_after["paragraphs"][0]["status"] == "completed"
    assert ch_after.get("translation_status", {}).get("status") == "paused"
    
    # Test manually completing p_2, then updating status - verify no overwrite
    ch_after["paragraphs"][1]["chinese"] = "隐含拒绝确保未明确允许的均被禁止。"
    ch_after["paragraphs"][1]["status"] = "completed"
    study_service.write_chapter_files(doc_id, ch_after, "en")
    
    from study.batch_translator import update_chapter_translation_status
    update_chapter_translation_status(doc_id, "ch_001", "paused")
    
    with open(ch_path, "r", encoding="utf-8") as f:
        ch_recheck = json.load(f)
    assert ch_recheck["paragraphs"][0]["chinese"] == "问责制是安全的基本原则。"
    assert ch_recheck["paragraphs"][1]["chinese"] == "隐含拒绝确保未明确允许的均被禁止。"
    assert ch_recheck["translation_status"]["status"] == "paused"
    
    study_service.delete_document(doc_id)
    print("✓ test_batch_translation_interruption_and_cissp_prompt passed!")

def test_delete_paragraph():
    print("Testing test_delete_paragraph...")
    import asyncio
    from study.chat_manager import append_chat_message, load_chat_history
    from study.flashcard_manager import create_flashcard, list_flashcards

    async def _run():
        md_sample = """# Chapter 1
First paragraph content to keep.

Second paragraph content to be deleted.

Third paragraph content to keep.
"""
        meta = await study_service.initialize_document(md_sample.encode("utf-8"), "delete_test.md")
        doc_id = meta["doc_id"]
        await study_service.process_document_pipeline(doc_id)

        meta = study_service.load_doc_meta(doc_id)
        assert meta["total_paragraphs"] == 4
        ch_id = meta["chapters"][0]["chapter_id"]
        ch_data = study_service.load_chapter_data(doc_id, ch_id)
        assert len(ch_data["paragraphs"]) == 4

        p_to_delete = ch_data["paragraphs"][2]
        p_id = p_to_delete["id"]

        # Add a note
        study_service.add_paragraph_note(doc_id, ch_id, p_id, "Test note to delete")
        # Add a chat message
        doc_dir = study_service.get_doc_dir(doc_id)
        append_chat_message(doc_dir, "paragraph", ch_id, p_id, role="user", content="hello para")
        chat_hist = load_chat_history(doc_dir, "paragraph", ch_id, p_id)
        assert len(chat_hist) > 0

        # Add a flashcard linked to this paragraph
        create_flashcard(doc_id, {
            "type": "word",
            "front": "Deleted word",
            "back": "Deleted definition",
            "chapter_id": ch_id,
            "paragraph_id": p_id
        })
        cards = list_flashcards(doc_id)
        assert any(c.get("paragraph_id") == p_id for c in cards)

        # Now delete paragraph
        res = study_service.delete_paragraph(doc_id, ch_id, p_id)
        assert res["success"] is True
        assert res["deleted_paragraph_id"] == p_id

        # Verify chapter paragraphs count is now 3
        updated_ch_data = study_service.load_chapter_data(doc_id, ch_id)
        assert len(updated_ch_data["paragraphs"]) == 3
        assert all(p["id"] != p_id for p in updated_ch_data["paragraphs"])

        # Verify meta counts
        updated_meta = study_service.load_doc_meta(doc_id)
        assert updated_meta["total_paragraphs"] == 3
        assert updated_meta["chapters"][0]["paragraph_count"] == 3

        # Verify chat history is cleared
        updated_chat_hist = load_chat_history(doc_dir, "paragraph", ch_id, p_id)
        assert len(updated_chat_hist) == 0

        # Verify flashcard is deleted
        updated_cards = list_flashcards(doc_id)
        assert not any(c.get("paragraph_id") == p_id for c in updated_cards)

        # Cleanup
        study_service.delete_document(doc_id)

    asyncio.run(_run())
    print("✓ test_delete_paragraph passed!")

def test_paragraph_type_conversion():
    print("Testing test_paragraph_type_conversion...")
    import asyncio

    async def _run():
        md_sample = """# Chapter 1
![Diagram](/images/sample.png)
"""
        meta = await study_service.initialize_document(md_sample.encode("utf-8"), "img_convert_test.md")
        doc_id = meta["doc_id"]
        await study_service.process_document_pipeline(doc_id)

        meta = study_service.load_doc_meta(doc_id)
        ch_id = meta["chapters"][0]["chapter_id"]
        ch_data = study_service.load_chapter_data(doc_id, ch_id)

        img_p = ch_data["paragraphs"][1]
        assert img_p["type"] == "image"
        p_id = img_p["id"]

        # Case 1: Replace image markdown with English text (auto-detect to text)
        updated = study_service.edit_paragraph_content(
            doc_id, ch_id, p_id,
            source_text="This is an English paragraph replacing the image."
        )
        assert updated["type"] == "text"
        assert updated["image_url"] == ""
        assert updated["no_translate"] is False
        assert updated["status"] == "pending"

        # Case 2: Explicitly change to code block
        updated_code = study_service.edit_paragraph_content(
            doc_id, ch_id, p_id,
            source_text="```python\nprint('hello')\n```",
            paragraph_type="code"
        )
        assert updated_code["type"] == "code"
        assert updated_code["no_translate"] is True

        # Case 3: Convert back to image by adding image markdown
        updated_img = study_service.edit_paragraph_content(
            doc_id, ch_id, p_id,
            source_text="![New Diagram](https://example.com/new_pic.png)"
        )
        assert updated_img["type"] == "image"
        assert updated_img["image_url"] == "https://example.com/new_pic.png"
        assert updated_img["no_translate"] is True

        study_service.delete_document(doc_id)

    asyncio.run(_run())
    print("✓ test_paragraph_type_conversion passed!")

def test_chapter_partitioning_avoids_paragraph_leak():
    print("Testing test_chapter_partitioning_avoids_paragraph_leak...")
    from study.parser import partition_blocks_into_chapters

    # Scenario: Chapter 1 ends on page 2, Chapter 2 starts on page 2.
    raw_blocks = [
        {"page": 1, "content": "Chapter 1: Overview", "is_heading": True},
        {"page": 1, "content": "Paragraph 1-1 introduction.", "is_heading": False},
        {"page": 2, "content": "Paragraph 1-2 continuing chapter 1.", "is_heading": False},
        {"page": 2, "content": "Paragraph 1-3 final summary of chapter 1.", "is_heading": False},
        {"page": 2, "content": "## Chapter 2: Security Architecture", "is_heading": True},
        {"page": 2, "content": "Paragraph 2-1 start of security.", "is_heading": False},
        {"page": 3, "content": "Paragraph 2-2 details.", "is_heading": False},
        {"page": 3, "content": "Paragraph 2-3 conclusion.", "is_heading": False},
        {"page": 4, "content": "## Chapter 3: Cryptography", "is_heading": True},
        {"page": 4, "content": "Paragraph 3-1 crypto intro.", "is_heading": False},
    ]

    chapter_targets = [
        {"title": "Chapter 1: Overview", "start_page": 1},
        {"title": "Chapter 2: Security Architecture", "start_page": 2},
        {"title": "Chapter 3: Cryptography", "start_page": 4}
    ]

    res = partition_blocks_into_chapters(raw_blocks, chapter_targets, lang="en")
    assert len(res) == 3, f"Expected 3 chapters, got {len(res)}"

    # Chapter 1 must contain 4 blocks (including Para 1-2 and Para 1-3 on page 2)
    ch1_blocks = res[0]["blocks"]
    assert len(ch1_blocks) == 4
    assert ch1_blocks[-1]["content"] == "Paragraph 1-3 final summary of chapter 1."

    # Chapter 2 must start at block "## Chapter 2: Security Architecture"
    ch2_blocks = res[1]["blocks"]
    assert len(ch2_blocks) == 4
    assert ch2_blocks[0]["content"] == "## Chapter 2: Security Architecture"
    assert ch2_blocks[1]["content"] == "Paragraph 2-1 start of security."

    # Chapter 3 must start at block "## Chapter 3: Cryptography"
    ch3_blocks = res[2]["blocks"]
    assert len(ch3_blocks) == 2
    assert ch3_blocks[0]["content"] == "## Chapter 3: Cryptography"

    # Total blocks must equal original count
    assert sum(len(c["blocks"]) for c in res) == len(raw_blocks)

    # Test: Unmatched / low-confidence target should NOT split (preventing fragmented chapters)
    unmatched_targets = [
        {"title": "Chapter 1: Overview", "start_page": 1},
        {"title": "Random Non-Existent Subsection", "start_page": 2},  # Low confidence -> must be skipped!
        {"title": "## Chapter 2: Security Architecture", "start_page": 2}, # Exact match -> split!
        {"title": "Another Vague Note", "start_page": 3},             # Low confidence -> must be skipped!
        {"title": "## Chapter 3: Cryptography", "start_page": 4}       # Exact match -> split!
    ]
    res_unmatched = partition_blocks_into_chapters(raw_blocks, unmatched_targets, lang="en")
    assert len(res_unmatched) == 3, f"Expected 3 chapters (low-confidence skipped), got {len(res_unmatched)}"
    assert res_unmatched[0]["title"] == "Chapter 1: Overview"
    assert res_unmatched[1]["title"] == "## Chapter 2: Security Architecture"
    assert res_unmatched[2]["title"] == "## Chapter 3: Cryptography"

    # Test detected_headings block_idx fallback (no TOC scenario)
    detected_targets = [
        {"title": "Chapter 1", "start_page": 1, "block_idx": 0},
        {"title": "Chapter 2", "start_page": 2, "block_idx": 4},
        {"title": "Chapter 3", "start_page": 4, "block_idx": 8},
    ]
    res_detected = partition_blocks_into_chapters(raw_blocks, detected_targets, lang="en")
    assert len(res_detected[0]["blocks"]) == 4
    assert res_detected[0]["blocks"][-1]["content"] == "Paragraph 1-3 final summary of chapter 1."
    assert res_detected[1]["blocks"][0]["content"] == "## Chapter 2: Security Architecture"

    print("✓ test_chapter_partitioning_avoids_paragraph_leak passed!")

def test_run_in_heading_paragraph_merging():
    """
    测试首句/首词加粗引导语（Run-in Head / Lead-in bold）与正文后续折行段落自然合并。
    确保不会因为句首加粗短语导致整行被误判为独立标题（###）并发生错误拆段。
    """
    print("Testing test_run_in_heading_paragraph_merging...")
    import fitz
    from study.parser import extract_pdf_native
    
    # 验证 doc_20260917_163901_d69c79 原文档中关于 Key distribution 的段落合并效果
    pdf_path = "data/documents/doc_20260917_163901_d69c79/original.pdf"
    if os.path.exists(pdf_path):
        lang, chapters = extract_pdf_native("doc_20260917_163901_d69c79", "data/documents/doc_20260917_163901_d69c79")
        ch2 = next((c for c in chapters if c["chapter_id"] == "ch_002"), None)
        assert ch2 is not None
        key_dist_paras = [p for p in ch2["paragraphs"] if "Key distribution is a major problem" in p.get("english", "")]
        assert len(key_dist_paras) == 1, "Key distribution 应合并为一个段落"
        kd_text = key_dist_paras[0]["english"]
        # 验证 have a secure 与 method of exchanging 成功合并且未加 ### 前缀
        assert not kd_text.startswith("###"), "不应被误判为标题"
        assert "Parties must have a secure method of exchanging the secret key" in kd_text, "跨行正文应无缝合并"
        
        # 验证 nonrepudiation 同样正常合并
        nonrep_paras = [p for p in ch2["paragraphs"] if "nonrepudiation" in p.get("english", "") and "does not implement" in p.get("english", "")]
        assert len(nonrep_paras) == 1
        assert "does not implement nonrepudiation." in nonrep_paras[0]["english"]
        
    print("✓ test_run_in_heading_paragraph_merging passed!")

if __name__ == "__main__":
    test_repair_english_paragraph()
    test_detect_language()
    test_is_chapter_heading()
    test_render_chapter_markdown()
    test_chinese_document_rendering()
    test_settings_save_and_load()
    test_formatted_pdf_extraction()
    test_colon_and_short_block_merging()
    test_line_spacing_threshold_and_indent()
    test_cross_page_hyphenation_and_continuation()
    test_logical_boundary_classification()
    test_sliding_context_prompt_and_parsing()
    test_context_expansion_chat()
    test_notes_and_batch_and_chapter_chat()
    test_document_settings_isolation_and_reset()
    test_export_markdown_and_html()
    test_chat_manager_persistence_and_streaming()
    test_txt_and_markdown_support()
    test_batch_translation_interruption_and_cissp_prompt()
    test_delete_paragraph()
    test_paragraph_type_conversion()
    test_chapter_partitioning_avoids_paragraph_leak()
    test_run_in_heading_paragraph_merging()
    print("\nAll study service unit tests passed successfully! 🎉")




