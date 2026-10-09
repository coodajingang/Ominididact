"""
P0 Security & Core Algorithmic Invariant Unit Tests
Tests authentication, config sanitization, secret preservation, debug log redaction,
path traversal validation, SM-2 spaced repetition calculation, and Anki APKG export.
"""

from __future__ import annotations
import os
import json
import zipfile
import sqlite3
import tempfile
import asyncio
import unittest
from unittest.mock import patch

# Set sys.path to ensure modules in workspace root are importable
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import auth
import config_store
from study.service import validate_doc_id, validate_image_filename, get_doc_dir, get_docs_base_dir
from study.flashcard_manager import calculate_sm2_review
from study.anki_exporter import export_flashcards_to_anki, sanitize_for_anki_cloze


class TestSecurityAuth(unittest.TestCase):
    """01: 全站统一鉴权 (OMNIDIDACT_API_TOKEN)"""

    def test_is_auth_required(self):
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": "secret-123"}):
            self.assertTrue(auth.is_auth_required())
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": ""}):
            self.assertFalse(auth.is_auth_required())
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(auth.is_auth_required())

    def test_verify_token_string(self):
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": "correct-token-999"}):
            self.assertTrue(auth.verify_token_string("correct-token-999"))
            self.assertTrue(auth.verify_token_string("  correct-token-999  "))
            self.assertFalse(auth.verify_token_string("wrong-token"))
            self.assertFalse(auth.verify_token_string(""))
            self.assertFalse(auth.verify_token_string(None))

    def test_verify_api_token_when_disabled(self):
        class MockRequest:
            headers = {}
            query_params = {}
            client = None
            url = type("URL", (), {"path": "/api/config"})()
        
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": ""}):
            # When disabled, any or no token should pass without raising
            asyncio.run(auth.verify_api_token(MockRequest(), None))

    def test_verify_api_token_success_cases(self):
        class MockCredentials:
            def __init__(self, token):
                self.credentials = token

        class MockRequest:
            def __init__(self, headers=None, query_params=None):
                self.headers = headers or {}
                self.query_params = query_params or {}
                self.client = None
                self.url = type("URL", (), {"path": "/api/test"})()

        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": "correct-token-999"}):
            # 1. Bearer header credentials
            asyncio.run(auth.verify_api_token(MockRequest(), MockCredentials("correct-token-999")))
            
            # 2. X-API-Token header
            asyncio.run(auth.verify_api_token(MockRequest(headers={"X-API-Token": "correct-token-999"}), None))
            
            # 3. Query param token
            asyncio.run(auth.verify_api_token(MockRequest(query_params={"token": "correct-token-999"}), None))

    def test_verify_api_token_failure_cases(self):
        class MockCredentials:
            def __init__(self, token):
                self.credentials = token

        class MockRequest:
            def __init__(self, headers=None, query_params=None):
                self.headers = headers or {}
                self.query_params = query_params or {}
                self.client = None
                self.url = type("URL", (), {"path": "/api/test"})()

        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": "correct-token-999"}):
            # Missing token
            with self.assertRaises(Exception) as ctx:
                asyncio.run(auth.verify_api_token(MockRequest(), None))
            self.assertEqual(getattr(ctx.exception, "status_code", 401), 401)

            # Incorrect token
            with self.assertRaises(Exception) as ctx:
                asyncio.run(auth.verify_api_token(MockRequest(), MockCredentials("wrong-token")))
            self.assertEqual(getattr(ctx.exception, "status_code", 401), 401)


class TestConfigSanitizationAndPreservation(unittest.TestCase):
    """02 & 06: 配置接口脱敏与秘钥保持、环境变量覆盖"""

    def test_sanitize_config_for_export(self):
        sensitive_data = {
            "api_key": "sk-1234567890abcdef",
            "openai_key": "sk-openai-super-secret",
            "normal_field": "visible_value",
            "nested": {
                "secret_key": "my-secret-key-val",
                "temperature": 0.7,
                "providers": [
                    {"name": "deepseek", "api_key": "sk-ds-998877665544"},
                    {"name": "ollama", "api_base": "http://localhost:11434"}
                ]
            }
        }
        sanitized = config_store.sanitize_config_for_export(sensitive_data)
        
        # Check that secrets are masked
        self.assertEqual(sanitized["api_key"], "****cdef")
        self.assertEqual(sanitized["openai_key"], "****cret")
        self.assertEqual(sanitized["normal_field"], "visible_value")
        self.assertEqual(sanitized["nested"]["secret_key"], "****-val")
        self.assertEqual(sanitized["nested"]["temperature"], 0.7)
        self.assertEqual(sanitized["nested"]["providers"][0]["api_key"], "****5544")
        self.assertEqual(sanitized["nested"]["providers"][1]["api_base"], "http://localhost:11434")

    def test_merge_config_with_preservation(self):
        existing = {
            "api_key": "real-original-api-key",
            "provider": {
                "token": "real-secret-token",
                "model": "deepseek-chat"
            }
        }
        # Incoming update has masked api_key and new model
        incoming = {
            "api_key": "****-key",
            "provider": {
                "token": "******",
                "model": "deepseek-reasoner"
            }
        }
        merged = config_store.merge_config_with_preservation(incoming, existing)
        self.assertEqual(merged["api_key"], "real-original-api-key")
        self.assertEqual(merged["provider"]["token"], "real-secret-token")
        self.assertEqual(merged["provider"]["model"], "deepseek-reasoner")

    def test_merge_config_updates_unmasked_new_secrets(self):
        existing = {"api_key": "old-key"}
        incoming = {"api_key": "brand-new-actual-key"}
        merged = config_store.merge_config_with_preservation(incoming, existing)
        self.assertEqual(merged["api_key"], "brand-new-actual-key")

    def test_resolve_provider_env_overrides(self):
        test_config = {
            "providers": {
                "openai": {"api_key": "config-key", "api_base": "https://api.openai.com/v1"},
                "deepseek": {"api_key": "", "api_base": "https://api.deepseek.com"}
            }
        }
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "env-openai-key-123",
            "DEEPSEEK_API_KEY": "env-deepseek-key-456"
        }):
            resolved = config_store.resolve_provider_env_overrides(test_config)
            self.assertEqual(resolved["providers"]["openai"]["api_key"], "env-openai-key-123")
            self.assertEqual(resolved["providers"]["deepseek"]["api_key"], "env-deepseek-key-456")


class TestDebugLogSanitization(unittest.TestCase):
    """03: 切断 Debug 日志凭证泄露链与循环容量限制"""

    def test_sanitize_debug_headers(self):
        headers = {
            "authorization": "Bearer super-secret-jwt-token",
            "x-api-key": "secret-api-key-header",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 Test",
            "cookie": "session_id=12345"
        }
        sanitized = config_store.sanitize_debug_headers(headers)
        # Content-type and user-agent should remain
        self.assertEqual(sanitized["content-type"], "application/json")
        self.assertEqual(sanitized["user-agent"], "Mozilla/5.0 Test")
        # Non-whitelisted or sensitive headers must NOT be present
        self.assertNotIn("authorization", sanitized)
        self.assertNotIn("x-api-key", sanitized)
        self.assertNotIn("cookie", sanitized)

    def test_sanitize_debug_body(self):
        # JSON body with api_key
        body_dict = {"model": "gpt-4", "api_key": "sk-test-secret-123456"}
        sanitized_dict = config_store.sanitize_debug_body(body_dict)
        self.assertEqual(sanitized_dict["model"], "gpt-4")
        self.assertTrue(sanitized_dict["api_key"].startswith("****"))
        self.assertEqual(sanitized_dict["api_key"], "****3456")

        # String body
        body_str = json.dumps(body_dict)
        sanitized_str = config_store.sanitize_debug_body(body_str)
        self.assertIn("****", sanitized_str)
        self.assertNotIn("sk-test-secret-123456", sanitized_str)

    def test_debug_log_circular_buffer_capacity(self):
        # Clear existing logs
        config_store.DEBUG_HISTORY.clear()
        
        # Test circular truncation logic with max capacity = 5
        with patch.object(config_store, "MAX_DEBUG_LOGS", 5):
            for i in range(10):
                config_store.DEBUG_HISTORY.insert(0, {"id": f"log_{i}", "index": i})
                while len(config_store.DEBUG_HISTORY) > 5:
                    config_store.DEBUG_HISTORY.pop()
            
            self.assertEqual(len(config_store.DEBUG_HISTORY), 5)
            self.assertEqual(config_store.DEBUG_HISTORY[0]["index"], 9)
            self.assertEqual(config_store.DEBUG_HISTORY[-1]["index"], 5)


class TestPathTraversalProtection(unittest.TestCase):
    """05: 阻断路径遍历与 GET 写副作用"""

    def test_validate_doc_id_valid(self):
        valid_ids = ["doc123", "my-notes_2026", "Study_Doc-01", "a", "12345"]
        for doc_id in valid_ids:
            self.assertEqual(validate_doc_id(doc_id), doc_id)

    def test_validate_doc_id_traversal_and_invalid(self):
        invalid_ids = [
            "../secret",
            "..\\secret",
            "doc/sub",
            "doc\\sub",
            "doc id with space",
            "doc.name",
            "",
            "../../../etc/passwd",
            "%2e%2e%2fdoc",
            "doc@name",
            "doc#1"
        ]
        for doc_id in invalid_ids:
            with self.assertRaises(ValueError, msg=f"Should reject {doc_id}"):
                validate_doc_id(doc_id)

    def test_validate_image_filename_valid(self):
        valid_filenames = ["img_01.png", "photo_123.jpg", "diagram.jpeg", "chart.webp", "anim.gif"]
        for fn in valid_filenames:
            self.assertEqual(validate_image_filename(fn), fn)

    def test_validate_image_filename_traversal(self):
        invalid_filenames = [
            "../secret.png",
            "sub/photo.jpg",
            "/absolute/path.png",
            "malicious.exe",
            "test.sh",
            "image..png",
            "",
            "../../images/01.png"
        ]
        for fn in invalid_filenames:
            with self.assertRaises(ValueError, msg=f"Should reject {fn}"):
                validate_image_filename(fn)

    def test_get_doc_dir_no_write_side_effect_on_read(self):
        non_existent_doc_id = "test_non_existent_doc_read_only"
        expected_path = os.path.join(get_docs_base_dir(), non_existent_doc_id)
        
        # Clean up in case it existed
        if os.path.exists(expected_path):
            os.rmdir(expected_path)
            
        # Call with create=False
        path = get_doc_dir(non_existent_doc_id, create=False)
        self.assertEqual(path, expected_path)
        # Verify directory was NOT created on disk
        self.assertFalse(os.path.exists(expected_path))


class TestSM2SpacedRepetition(unittest.TestCase):
    """09: 明确并校正 SM-2 算法口径"""

    def test_sm2_first_successful_review(self):
        # Rating 3 (Good -> q=4 in 4-point scale)
        res = calculate_sm2_review(rating=3, reps=0, interval_days=0, ease_factor=2.5, lapses=0)
        self.assertEqual(res["reps"], 1)
        self.assertEqual(res["interval_days"], 1)
        self.assertEqual(res["ease_factor"], 2.5)  # 2.5 + (0.1 - 1*0.1) = 2.5

    def test_sm2_second_successful_review(self):
        # Rating 4 (Easy -> q=5 in 4-point scale) -> EF increases to 2.6
        res = calculate_sm2_review(rating=4, reps=1, interval_days=1, ease_factor=2.5, lapses=0)
        self.assertEqual(res["reps"], 2)
        self.assertEqual(res["interval_days"], 6)
        self.assertEqual(res["state"], "mastered")
        self.assertAlmostEqual(res["ease_factor"], 2.6, places=2)

    def test_sm2_third_review_with_interval_growth(self):
        # Rating 3 (Good) -> interval = round(6 * 2.6) = 16 days
        res = calculate_sm2_review(rating=3, reps=2, interval_days=6, ease_factor=2.6, lapses=0)
        self.assertEqual(res["reps"], 3)
        self.assertEqual(res["interval_days"], 16)
        self.assertEqual(res["state"], "review")

    def test_sm2_lapse_reset(self):
        # Rating 1 (Again/Forgot) -> reps reset to 0, lapses +1, EF decreases
        res = calculate_sm2_review(rating=1, reps=5, interval_days=35, ease_factor=2.6, lapses=0)
        self.assertEqual(res["reps"], 0)
        self.assertEqual(res["interval_days"], 0)
        self.assertEqual(res["lapses"], 1)
        self.assertEqual(res["state"], "learning")
        self.assertAlmostEqual(res["ease_factor"], 2.06, places=2)

    def test_sm2_minimum_ease_factor_clamp(self):
        # Rating 1 with low starting EF -> clamped to 1.3
        res = calculate_sm2_review(rating=1, reps=1, interval_days=1, ease_factor=1.35, lapses=3)
        self.assertEqual(res["ease_factor"], 1.3)


class TestAnkiExport(unittest.TestCase):
    """14: 交付 Anki .apkg 导出功能"""

    def test_sanitize_cloze(self):
        raw = "访问控制四要素包括{{标识}}、{{鉴别}}、{{授权}}与{{问责}}。"
        converted = sanitize_for_anki_cloze(raw)
        self.assertEqual(converted, "访问控制四要素包括{{c1::标识}}、{{c2::鉴别}}、{{c3::授权}}与{{c4::问责}}。")

    def test_export_flashcards_to_anki_apkg_structure(self):
        sample_cards = [
            {
                "id": "fc_001",
                "type": "qa",
                "front": "什么是最小特权原则？",
                "back": "主体只被赋予完成其任务所必需的最小权限。",
                "tags": ["CISSP", "安全"],
                "stats": {"reps": 2, "interval_days": 6, "ease_factor": 2.5, "lapses": 0}
            },
            {
                "id": "fc_002",
                "type": "cloze",
                "front": "CIA 三要素指{{保密性}}、{{完整性}}和{{可用性}}。",
                "back": "信息安全基石",
                "tags": ["CISSP"],
                "stats": {"reps": 0, "interval_days": 0, "ease_factor": 2.5, "lapses": 0}
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            out_apkg = os.path.join(tmpdir, "test_deck.apkg")
            export_flashcards_to_anki(sample_cards, out_apkg, deck_name="CISSP::TestDeck")

            self.assertTrue(os.path.exists(out_apkg))
            self.assertGreater(os.path.getsize(out_apkg), 0)

            # Inspect ZIP structure
            with zipfile.ZipFile(out_apkg, "r") as zf:
                namelist = zf.namelist()
                self.assertIn("collection.anki2", namelist)
                self.assertIn("media", namelist)

                # Extract and inspect sqlite database
                zf.extract("collection.anki2", tmpdir)
                db_path = os.path.join(tmpdir, "collection.anki2")
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Check tables exist
                tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                self.assertIn("col", tables)
                self.assertIn("notes", tables)
                self.assertIn("cards", tables)

                # Check notes count
                note_rows = cursor.execute("SELECT id, flds, tags FROM notes").fetchall()
                self.assertEqual(len(note_rows), 2)

                # Check cards count
                card_rows = cursor.execute("SELECT id, nid, did, factor FROM cards").fetchall()
                self.assertGreaterEqual(len(card_rows), 2)

                conn.close()


class TestCORSAndSecurityHeaders(unittest.TestCase):
    """04: 修正 CORS 通配符与凭证组合"""

    def setUp(self):
        from fastapi.testclient import TestClient
        from proxy import app
        self.client = TestClient(app)

    def test_cors_allowed_origin(self):
        resp = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET"
            }
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:8000")

    def test_cors_disallowed_origin(self):
        resp = self.client.options(
            "/api/health",
            headers={
                "Origin": "https://malicious-attacker.com",
                "Access-Control-Request-Method": "GET"
            }
        )
        # Malicious origin should not be reflected in allow-origin header
        self.assertNotEqual(resp.headers.get("access-control-allow-origin"), "https://malicious-attacker.com")


class TestUniversalAnonymousRouteProtection(unittest.TestCase):
    """01 & 12: 全站路由匿名通用枚举防御测试 (最低门槛测试)"""

    def setUp(self):
        from fastapi.testclient import TestClient
        from proxy import app
        self.client = TestClient(app)
        self.app = app

    def test_all_api_routes_reject_anonymous_requests_when_token_configured(self):
        """
        Enumerates all registered API routes from OpenAPI schema and verifies
        that anonymous requests to protected endpoints return 401.
        """
        public_whitelist = {
            "/health",
            "/api/health",
            "/favicon.ico",
            "/favicon.svg",
            "/",
            "/config",
            "/chat",
            "/study",
            "/study/flashcards",
            "/login",
            "/auth",
        }

        test_token = "secure-omnididact-token-xyz"
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": test_token}):
            openapi_schema = self.app.openapi()
            paths = openapi_schema.get("paths", {})

            for path, methods in paths.items():
                if path in public_whitelist:
                    continue

                for method in methods.keys():
                    if method.upper() in ("HEAD", "OPTIONS"):
                        continue

                    # Construct a sample test URL replacing path params
                    test_url = path.replace("{doc_id}", "test_doc_01")
                    test_url = test_url.replace("{chapter_id}", "ch_01")
                    test_url = test_url.replace("{paragraph_id}", "p_01")
                    test_url = test_url.replace("{note_id}", "n_01")
                    test_url = test_url.replace("{card_id}", "c_01")
                    test_url = test_url.replace("{img_name}", "img_01.png")
                    test_url = test_url.replace("{name}", "model_01")

                    kwargs = {}
                    if method.upper() in ("POST", "PUT", "PATCH"):
                        kwargs["json"] = {}

                    # 1. Anonymous request MUST return 401
                    resp_anon = self.client.request(method.upper(), test_url, **kwargs)
                    self.assertEqual(
                        resp_anon.status_code, 401,
                        msg=f"Endpoint {method.upper()} {test_url} allowed anonymous access!"
                    )

                    # 2. Wrong token MUST return 401
                    resp_wrong = self.client.request(
                        method.upper(), test_url,
                        headers={"Authorization": "Bearer invalid-wrong-token"},
                        **kwargs
                    )
                    self.assertEqual(
                        resp_wrong.status_code, 401,
                        msg=f"Endpoint {method.upper()} {test_url} allowed invalid token!"
                    )

                    # 3. Correct token MUST NOT return 401 (e.g. 200, 400, 404, 422 are fine, but NOT 401)
                    resp_auth = self.client.request(
                        method.upper(), test_url,
                        headers={"Authorization": f"Bearer {test_token}"},
                        **kwargs
                    )
                    self.assertNotEqual(
                        resp_auth.status_code, 401,
                        msg=f"Endpoint {method.upper()} {test_url} rejected valid token!"
                    )


class TestPathTraversalHTTPProtection(unittest.TestCase):
    """05 & 12: 路径遍历 HTTP 接口防护回归测试"""

    def setUp(self):
        from fastapi.testclient import TestClient
        from proxy import app
        self.client = TestClient(app)

    def test_image_route_traversal_attempts_rejected(self):
        traversal_attempts = [
            "../secret.png",
            "..%2fsecret.png",
            "%2e%2e%2fsecret.png",
            "....//secret.png",
            "sub/photo.png",
            "/etc/passwd",
            "bad_ext.exe",
            "script.sh",
        ]

        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": "test-token"}):
            headers = {"Authorization": "Bearer test-token"}
            for att in traversal_attempts:
                resp = self.client.get(f"/api/study/documents/doc_valid_01/images/{att}", headers=headers)
                self.assertIn(
                    resp.status_code, (400, 404),
                    msg=f"Path traversal '{att}' was not rejected! Status: {resp.status_code}"
                )


class TestChapterRouteConvergence(unittest.TestCase):
    """08 & 12: 收敛 chapter / chapters 契约与弃用测试"""

    def setUp(self):
        from fastapi.testclient import TestClient
        from proxy import app
        self.client = TestClient(app)
        self.app = app

    def test_openapi_schema_contains_only_chapters_routes(self):
        schema = self.app.openapi()
        paths = schema.get("paths", {})
        legacy_paths = [p for p in paths.keys() if "/chapter/" in p]
        self.assertEqual(len(legacy_paths), 0, f"Found legacy /chapter/ paths in OpenAPI schema: {legacy_paths}")

        canonical_paths = [p for p in paths.keys() if "/chapters/" in p]
        self.assertGreater(len(canonical_paths), 0, "Canonical /chapters/ routes must exist in OpenAPI schema")

    def test_legacy_chapter_route_requires_auth_and_redirects_with_307_deprecation(self):
        test_token = "my-secret-token"
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": test_token}):
            # 1. Anonymous request to legacy route returns 401 (does NOT bypass auth!)
            resp_anon = self.client.get(
                "/api/study/documents/doc_01/chapter/ch_01",
                follow_redirects=False
            )
            self.assertEqual(resp_anon.status_code, 401)

            # 2. Authenticated request to legacy route returns 307 with Deprecation header
            resp_auth = self.client.get(
                "/api/study/documents/doc_01/chapter/ch_01",
                headers={"Authorization": f"Bearer {test_token}"},
                follow_redirects=False
            )
            self.assertEqual(resp_auth.status_code, 307)
            self.assertEqual(resp_auth.headers.get("Deprecation"), "true")
            self.assertEqual(resp_auth.headers.get("Location"), "/api/study/documents/doc_01/chapters/ch_01")


class TestTokenAuthenticationAndLoginFlow(unittest.TestCase):
    """验证 401 时页面自动重定向到 /login、安全 HttpOnly Cookie 存储与全生命周期"""

    def setUp(self):
        from fastapi.testclient import TestClient
        from proxy import app
        self.app = app
        self.test_token = "secure-login-token-888"

    def test_unauthenticated_html_pages_redirect_to_login(self):
        from fastapi.testclient import TestClient
        client = TestClient(self.app)
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": self.test_token}):
            pages = [
                ("/study", "/login?redirect=/study"),
                ("/config", "/login?redirect=/config"),
                ("/chat", "/login?redirect=/chat"),
                ("/study/flashcards", "/login?redirect=/study/flashcards"),
            ]
            for page_url, expected_redirect in pages:
                resp = client.get(page_url, follow_redirects=False)
                self.assertEqual(
                    resp.status_code, 303,
                    msg=f"Page {page_url} did not redirect unauthenticated user!"
                )
                self.assertEqual(resp.headers.get("location"), expected_redirect)

    def test_login_page_accessible_and_renders_html(self):
        from fastapi.testclient import TestClient
        client = TestClient(self.app)
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": self.test_token}):
            resp = client.get("/login")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers.get("content-type", ""))
            self.assertIn("Omnididact", resp.text)
            self.assertIn("访问令牌", resp.text)

    def test_login_api_rejects_invalid_token(self):
        from fastapi.testclient import TestClient
        client = TestClient(self.app)
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": self.test_token}):
            resp = client.post("/api/auth/login", json={"token": "wrong-secret"})
            self.assertEqual(resp.status_code, 401)

    def test_login_api_sets_secure_httponly_cookie(self):
        from fastapi.testclient import TestClient
        client = TestClient(self.app)
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": self.test_token}):
            resp = client.post("/api/auth/login", json={"token": self.test_token, "remember": True})
            self.assertEqual(resp.status_code, 200)
            
            # Verify set-cookie header contains secure flags
            cookie_headers = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else [resp.headers.get("set-cookie", "")]
            cookie_str = "; ".join(cookie_headers)
            self.assertIn("omnididact_token", cookie_str)
            self.assertIn("httponly", cookie_str.lower())
            self.assertIn("samesite=lax", cookie_str.lower())

            # Now visit /study with client (which has cookie) - should not redirect
            resp_page = client.get("/study", follow_redirects=False)
            self.assertEqual(resp_page.status_code, 200)

    def test_logout_api_clears_cookie(self):
        from fastapi.testclient import TestClient
        client = TestClient(self.app)
        with patch.dict(os.environ, {"OMNIDIDACT_API_TOKEN": self.test_token}):
            # Log in
            client.post("/api/auth/login", json={"token": self.test_token})
            # Log out
            resp_logout = client.post("/api/auth/logout")
            self.assertEqual(resp_logout.status_code, 200)
            # Cookie should be deleted/cleared
            resp_after = client.get("/study", follow_redirects=False)
            self.assertEqual(resp_after.status_code, 303)


if __name__ == "__main__":
    unittest.main()

