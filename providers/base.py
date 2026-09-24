from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, AsyncGenerator

import json

@dataclass
class StreamChunk:
    """Standardized streaming chunk across all providers."""
    content: str = ""
    reasoning_content: Optional[str] = None
    done: bool = False
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

def chunk_to_sse(chunk: StreamChunk) -> str:
    """Formats StreamChunk into standard SSE data string."""
    if chunk.error:
        return f"data: {json.dumps({'error': chunk.error}, ensure_ascii=False)}\n\n"
    if chunk.done:
        return "data: [DONE]\n\n"
    delta: Dict[str, Any] = {}
    if chunk.reasoning_content:
        delta["reasoning_content"] = chunk.reasoning_content
    if chunk.content:
        delta["content"] = chunk.content
    if not delta:
        return ""
    return f"data: {json.dumps({'choices': [{'delta': delta, 'index': 0}]}, ensure_ascii=False)}\n\n"

class BaseProvider(ABC):
    """Abstract base class for all LLM providers."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier (e.g., 'openai_compatible', 'ollama', 'lm_studio', 'custom')."""
        pass
        
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name."""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream responses from the provider yielding StreamChunk."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Non-streaming response from the provider returning full text."""
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Fetch available models from the provider endpoint."""
        pass

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test provider connectivity.
        Returns:
            {
                "connected": bool,
                "message": str,
                "models": List[str]
            }
        """
        pass
