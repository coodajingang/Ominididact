import os
import sys
import asyncio
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
import proxy
import config_store

client = TestClient(proxy.app)

class TestProviderSettingsAPI(unittest.TestCase):
    def setUp(self):
        self.orig_config = config_store.load_config()

    def tearDown(self):
        config_store.save_config(self.orig_config)

    def test_list_providers(self):
        resp = client.get("/api/study/providers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        providers = [p["id"] for p in data["data"]]
        self.assertIn("openai_compatible", providers)
        self.assertIn("ollama", providers)
        self.assertIn("lm_studio", providers)
        self.assertIn("nvidia", providers)
        self.assertIn("amd", providers)
        self.assertIn("cloudflare", providers)

    def test_get_and_save_providers_config(self):
        # 1. Get current config
        resp = client.get("/api/study/providers/config")
        self.assertEqual(resp.status_code, 200)
        orig_data = resp.json()["data"]

        # 2. Save updated config
        new_payload = {
            "providers": {
                "openai_compatible": {
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "test-key-123",
                    "model": "deepseek-chat"
                }
            },
            "defaults": {
                "default_translation_provider": "openai_compatible",
                "default_translation_model": "deepseek-chat",
                "default_chat_provider": "openai_compatible",
                "default_chat_model": "deepseek-chat",
                "default_vlm_provider": "openai_compatible",
                "default_vlm_model": "deepseek-chat"
            }
        }
        post_resp = client.post("/api/study/providers/config", json=new_payload)
        self.assertEqual(post_resp.status_code, 200)

        # 3. Verify changes persisted
        verify_resp = client.get("/api/study/providers/config")
        v_data = verify_resp.json()["data"]
        self.assertEqual(v_data["providers"]["openai_compatible"]["api_key"], "test-key-123")
        self.assertEqual(v_data["defaults"]["default_translation_model"], "deepseek-chat")

    def test_provider_models_endpoint(self):
        # Test models endpoint for a simulated provider
        resp = client.post("/api/study/providers/models", json={"provider": "ollama"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        self.assertIsInstance(data["data"], list)

    def test_study_settings_with_doc_overrides(self):
        # Test global settings
        resp = client.get("/api/study/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIn("default_translation_provider", data)
        self.assertIn("default_chat_provider", data)
        self.assertIn("default_vlm_provider", data)

if __name__ == "__main__":
    unittest.main()
