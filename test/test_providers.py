import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import providers
from providers.base import BaseProvider, StreamChunk, chunk_to_sse
from providers.openai_provider import OpenAICompatibleProvider
from providers.ollama_provider import OllamaProvider
from providers.lm_studio_provider import LMStudioProvider
from providers.registry import (
    register_provider,
    get_provider,
    list_available_providers,
    _PROVIDER_CLASSES
)

class TestProviderLayer(unittest.IsolatedAsyncioTestCase):

    def test_stream_chunk_and_sse(self):
        # Regular content
        chunk1 = StreamChunk(content="Hello world")
        sse1 = chunk_to_sse(chunk1)
        self.assertIn("Hello world", sse1)
        self.assertIn('"delta": {"content": "Hello world"', sse1)

        # Reasoning content
        chunk2 = StreamChunk(reasoning_content="Let me think")
        sse2 = chunk_to_sse(chunk2)
        self.assertIn('"reasoning_content": "Let me think"', sse2)

        # Done
        chunk3 = StreamChunk(done=True)
        self.assertEqual(chunk_to_sse(chunk3), "data: [DONE]\n\n")

        # Error
        chunk4 = StreamChunk(error="Connection timeout")
        self.assertIn('"error": "Connection timeout"', chunk_to_sse(chunk4))

    def test_available_providers_list(self):
        provs = list_available_providers()
        ids = [p["id"] for p in provs]
        self.assertIn("openai_compatible", ids)
        self.assertIn("ollama", ids)
        self.assertIn("lm_studio", ids)
        # Verify display names are localized and descriptive
        openai_p = next(p for p in provs if p["id"] == "openai_compatible")
        self.assertIn("OpenAI", openai_p["name"])

    def test_factory_mappings(self):
        # OpenAI compatible
        p1 = get_provider({
            "llm_source": "openai_compatible",
            "openai_base_url": "https://api.deepseek.com/v1",
            "openai_api_key": "sk-test",
            "openai_model": "deepseek-chat"
        })
        self.assertIsInstance(p1, OpenAICompatibleProvider)
        self.assertEqual(p1.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(p1.api_key, "sk-test")
        self.assertEqual(p1.default_model, "deepseek-chat")

        # Ollama
        p2 = get_provider({
            "llm_source": "ollama",
            "ollama_base_url": "http://127.0.0.1:11434",
            "ollama_model": "qwen2.5:7b"
        })
        self.assertIsInstance(p2, OllamaProvider)
        self.assertEqual(p2.base_url, "http://127.0.0.1:11434")
        self.assertEqual(p2.default_model, "qwen2.5:7b")

        # LM Studio
        p3 = get_provider({
            "llm_source": "lm_studio",
            "lm_studio_base_url": "http://127.0.0.1:1234/v1",
            "lm_studio_model": "my-local-model"
        })
        self.assertIsInstance(p3, LMStudioProvider)
        self.assertEqual(p3.base_url, "http://127.0.0.1:1234/v1")
        self.assertEqual(p3.default_model, "my-local-model")

        # NVIDIA
        p4 = get_provider({
            "llm_source": "nvidia",
            "nvidia_api_key": "nvapi-123456",
            "nvidia_model": "meta/llama-3.3-70b-instruct"
        })
        self.assertEqual(p4.provider_id, "nvidia")
        self.assertEqual(p4.base_url, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(p4.api_key, "nvapi-123456")
        self.assertEqual(p4.default_model, "meta/llama-3.3-70b-instruct")

        # AMD
        p5 = get_provider({
            "llm_source": "amd",
            "amd_base_url": "http://127.0.0.1:8000/v1",
            "amd_model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
        })
        self.assertEqual(p5.provider_id, "amd")
        self.assertEqual(p5.base_url, "http://127.0.0.1:8000/v1")
        self.assertEqual(p5.default_model, "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B")

        # Cloudflare
        p6 = get_provider({
            "llm_source": "cloudflare",
            "cf_account_id": "account_xyz",
            "cf_api_token": "token_abc",
            "cf_model": "@cf/meta/llama-3.3-70b-instruct"
        })
        self.assertEqual(p6.provider_id, "cloudflare")
        self.assertIn("account_xyz", p6.base_url)
        self.assertEqual(p6.api_key, "token_abc")
        self.assertEqual(p6.default_model, "@cf/meta/llama-3.3-70b-instruct")

    async def test_openai_mock_chat(self):
        provider = OpenAICompatibleProvider({
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-123456",
            "model": "gpt-test"
        })
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Translated response text"}}]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            res = await provider.chat([{"role": "user", "content": "Hello"}])
            self.assertEqual(res, "Translated response text")
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer sk-123456")
            self.assertEqual(call_kwargs["json"]["model"], "gpt-test")

    async def test_ollama_mock_chat(self):
        provider = OllamaProvider({
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen2.5:7b"
        })
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Ollama generated content"}
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            res = await provider.chat([{"role": "user", "content": "Hi"}])
            self.assertEqual(res, "Ollama generated content")
            mock_post.assert_called_once()

    def test_dynamic_plugin_isolation(self):
        # Verify that if custom_gateway plugin exists, it is loaded;
        # and if it were not present in the registry, system defaults to openai_compatible
        has_custom = "custom_gateway" in _PROVIDER_CLASSES
        if has_custom:
            p = get_provider({"llm_source": "custom_gateway"})
            self.assertEqual(p.provider_id, "custom_gateway")
            self.assertIn("自定义", p.display_name)
        
        # Test fallback when provider id is unknown
        fallback = get_provider({"llm_source": "non_existent_provider"})
        self.assertIsInstance(fallback, OpenAICompatibleProvider)

    async def test_cloudflare_provider(self):
        from providers.cloudflare_provider import CloudflareProvider
        
        # 1. Missing credentials
        cf_empty = CloudflareProvider({"account_id": "", "api_token": ""})
        res_empty = await cf_empty.test_connection()
        self.assertFalse(res_empty["connected"])
        self.assertIn("请先填写", res_empty["message"])

        # 2. Mocked successful models/search test_connection
        cf = CloudflareProvider({
            "account_id": "test_acc_123",
            "api_token": "test_tok_456",
            "model": "@cf/meta/llama-3.1-8b-instruct"
        })
        
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "success": True,
            "result": [
                {"name": "@cf/meta/llama-3.1-8b-instruct"},
                {"name": "@cf/qwen/qwen2.5-7b-instruct"},
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_search_resp
            res = await cf.test_connection()
            self.assertTrue(res["connected"])
            self.assertIn("@cf/meta/llama-3.1-8b-instruct", res["models"])

        # 3. Mocked chat (non-stream) with Cloudflare native response
        mock_chat_resp = MagicMock()
        mock_chat_resp.status_code = 200
        mock_chat_resp.json.return_value = {
            "success": True,
            "result": {
                "response": "Hello from Cloudflare Workers AI"
            }
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_chat_resp
            reply = await cf.chat([{"role": "user", "content": "Hello"}])
            self.assertEqual(reply, "Hello from Cloudflare Workers AI")
            call_url = mock_post.call_args[0][0]
            self.assertIn("/ai/run/@cf/meta/llama-3.1-8b-instruct", call_url)

if __name__ == "__main__":
    unittest.main()
