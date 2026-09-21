import os
import sys
import json
import shutil
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
import study_service
from proxy import app

client = TestClient(app)

def test_flashcard_crud_and_isolation():
    doc_a = "doc_test_flashcard_a"
    doc_b = "doc_test_flashcard_b"
    
    dir_a = study_service.get_doc_dir(doc_a)
    dir_b = study_service.get_doc_dir(doc_b)
    
    try:
        # 1. Create QA Card in Doc A
        card_qa = study_service.create_flashcard(doc_a, {
            "type": "qa",
            "front": "什么是隐含拒绝（Implicit Deny）？",
            "back": "未明确允许的访问默认一律拒绝。",
            "tags": ["CISSP", "访问控制"],
            "chapter_id": "ch_01"
        })
        assert card_qa["id"].startswith("fc_")
        assert card_qa["type"] == "qa"
        assert card_qa["stats"]["lapses"] == 0
        assert card_qa["stats"]["state"] == "new"

        # 2. Create Cloze Card in Doc A
        card_cloze = study_service.create_flashcard(doc_a, {
            "type": "cloze",
            "front": "访问控制四要素包括{{标识}}、{{鉴别}}、{{授权}}与{{问责}}。",
            "back": "对应 IAAA 模型。",
            "tags": ["CISSP"],
            "chapter_id": "ch_01"
        })
        assert card_cloze["type"] == "cloze"

        # 3. Verify Doc B is completely isolated (0 cards)
        cards_b = study_service.list_flashcards(doc_b)
        assert len(cards_b) == 0, f"Doc B should have 0 cards, got {len(cards_b)}"

        # 4. List and Filter in Doc A
        all_a = study_service.list_flashcards(doc_a)
        assert len(all_a) == 2
        
        qa_only = study_service.list_flashcards(doc_a, filter_type="qa")
        assert len(qa_only) == 1
        assert qa_only[0]["id"] == card_qa["id"]

        cloze_only = study_service.list_flashcards(doc_a, filter_type="cloze")
        assert len(cloze_only) == 1
        assert cloze_only[0]["id"] == card_cloze["id"]

        search_result = study_service.list_flashcards(doc_a, keyword="隐含拒绝")
        assert len(search_result) == 1
        assert search_result[0]["id"] == card_qa["id"]

        # 5. Update Card
        updated = study_service.update_flashcard(doc_a, card_qa["id"], {
            "front": "【更新】什么是隐含拒绝？",
            "back": "【更新】默认拒绝所有未授权访问。"
        })
        assert updated["front"] == "【更新】什么是隐含拒绝？"
        assert updated["back"] == "【更新】默认拒绝所有未授权访问。"

        # 6. SM-2 Spaced Repetition Review
        # Rating 1 (Again / 忘记) -> lapses should increase to 1
        reviewed_lapse = study_service.record_card_review(doc_a, card_qa["id"], 1)
        assert reviewed_lapse["stats"]["lapses"] == 1
        assert reviewed_lapse["stats"]["state"] == "learning"

        # Check is_error filter
        error_cards = study_service.list_flashcards(doc_a, is_error=True)
        assert len(error_cards) == 1
        assert error_cards[0]["id"] == card_qa["id"]

        # Rating 4 (Easy / 熟练) -> interval jumps, state becomes mastered
        reviewed_easy = study_service.record_card_review(doc_a, card_cloze["id"], 4)
        assert reviewed_easy["stats"]["state"] == "mastered"
        assert reviewed_easy["stats"]["reps"] == 1

        # 7. Check Statistics
        stats = study_service.get_flashcard_statistics(doc_a)
        assert stats["total_cards"] == 2
        assert stats["error_count"] == 1
        assert stats["mastered_count"] == 1
        assert stats["learning_count"] == 1
        assert stats["mastery_rate"] == 50.0

        # 8. Clear Error Counts
        cleared_count = study_service.clear_card_errors(doc_a, card_qa["id"])
        assert cleared_count == 1
        stats_after_clear = study_service.get_flashcard_statistics(doc_a)
        assert stats_after_clear["error_count"] == 0

        # 9. Batch Create in Doc B
        batch_res = study_service.batch_create_flashcards(doc_b, [
            {"type": "qa", "front": "Q1", "back": "A1"},
            {"type": "cloze", "front": "{{Q2}}", "back": "A2"}
        ])
        assert len(batch_res) == 2
        assert len(study_service.list_flashcards(doc_b)) == 2

        # 10. Batch Delete in Doc B
        deleted_count = study_service.batch_delete_flashcards(doc_b, [batch_res[0]["id"], batch_res[1]["id"]])
        assert deleted_count == 2
        assert len(study_service.list_flashcards(doc_b)) == 0

        # 11. Delete single card in Doc A
        assert study_service.delete_flashcard(doc_a, card_qa["id"]) is True
        assert len(study_service.list_flashcards(doc_a)) == 1

        print("✓ test_flashcard_crud_and_isolation passed!")
    finally:
        # Cleanup test directories
        if os.path.exists(dir_a):
            shutil.rmtree(dir_a, ignore_errors=True)
        if os.path.exists(dir_b):
            shutil.rmtree(dir_b, ignore_errors=True)

def test_flashcard_api_endpoints():
    doc_id = "doc_test_flashcard_api"
    doc_dir = study_service.get_doc_dir(doc_id)
    if os.path.exists(doc_dir):
        shutil.rmtree(doc_dir, ignore_errors=True)
    
    try:
        # 1. GET /study/flashcards page
        resp = client.get("/study/flashcards")
        assert resp.status_code == 200
        assert "闪卡管理与学习中心" in resp.text

        # 2. POST create flashcard via API
        resp_create = client.post(f"/api/study/documents/{doc_id}/flashcards", json={
            "type": "qa",
            "front": "什么是 CIA 三要素？",
            "back": "机密性（Confidentiality）、完整性（Integrity）、可用性（Availability）。",
            "tags": ["CISSP", "基础安全"],
            "chapter_id": "ch_01"
        })
        assert resp_create.status_code == 200
        data = resp_create.json()
        assert data["code"] == 200
        card_id = data["data"]["id"]

        # 3. GET flashcards list via API
        resp_list = client.get(f"/api/study/documents/{doc_id}/flashcards")
        assert resp_list.status_code == 200
        cards_data = resp_list.json()["data"]
        assert cards_data["total"] == 1
        assert cards_data["cards"][0]["id"] == card_id

        # 4. PUT update flashcard
        resp_update = client.put(f"/api/study/documents/{doc_id}/flashcards/{card_id}", json={
            "front": "什么是信息安全 CIA 三要素？"
        })
        assert resp_update.status_code == 200
        assert resp_update.json()["data"]["front"] == "什么是信息安全 CIA 三要素？"

        # 5. POST review rating (1 = Again)
        resp_review = client.post(f"/api/study/documents/{doc_id}/flashcards/{card_id}/review", json={
            "rating": 1
        })
        assert resp_review.status_code == 200
        assert resp_review.json()["data"]["stats"]["lapses"] == 1

        # 6. GET stats
        resp_stats = client.get(f"/api/study/documents/{doc_id}/flashcards/stats")
        assert resp_stats.status_code == 200
        assert resp_stats.json()["data"]["error_count"] == 1

        # 7. POST update settings
        resp_settings = client.post(f"/api/study/documents/{doc_id}/flashcards/settings", json={
            "fontSize": "large",
            "clozeStyle": "underline"
        })
        assert resp_settings.status_code == 200
        assert resp_settings.json()["data"]["fontSize"] == "large"

        # 8. POST clear errors
        resp_clear = client.post(f"/api/study/documents/{doc_id}/flashcards/clear_errors", json={
            "card_id": card_id
        })
        assert resp_clear.status_code == 200
        assert resp_clear.json()["data"]["cleared_count"] == 1

        # 9. POST flashcard chat (streaming check)
        def mock_stream(*args, **kwargs):
            yield "data: {\"chunk\": \"测试记忆口诀\"}\n\n"
            yield "data: [DONE]\n\n"

        with patch("study_router.study_service.stream_flashcard_chat", side_effect=mock_stream):
            resp_chat = client.post(f"/api/study/documents/{doc_id}/flashcards/chat", json={
                "card_data": {
                    "id": card_id,
                    "front": "什么是零信任？",
                    "back": "从不信任，始终验证。",
                    "type": "qa"
                },
                "message": "请给出记忆口诀",
                "history": []
            })
            assert resp_chat.status_code == 200
            assert "text/event-stream" in resp_chat.headers.get("content-type", "")

        # 10. DELETE card
        resp_del = client.delete(f"/api/study/documents/{doc_id}/flashcards/{card_id}")
        assert resp_del.status_code == 200
        assert resp_del.json()["data"]["success"] is True

        print("✓ test_flashcard_api_endpoints passed!")
    finally:
        if os.path.exists(doc_dir):
            shutil.rmtree(doc_dir, ignore_errors=True)

if __name__ == "__main__":
    test_flashcard_crud_and_isolation()
    test_flashcard_api_endpoints()
    print("\nAll flashcard unit & API tests passed! 🚀")
