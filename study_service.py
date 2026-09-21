"""
study_service.py (Facade & Re-export Module)

This file maintains backwards-compatibility by re-exporting the decoupled
study modules located in the `study/` directory:
- study.service: Document lifecycle, metadata, chapter persistence & orchestration
- study.pdf_parser: PyMuPDF4LLM-based layout analysis & paragraph extraction
- study.translator: LLM/VLLM translation, sliding context window, LM Studio client & AI chat
"""

from study import *

