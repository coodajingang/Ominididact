import json
import logging
from typing import List, Dict, Any, Optional

from study.service import get_study_settings
from providers import get_provider, get_provider_for_task
from providers.base import chunk_to_sse

logger = logging.getLogger("study-flashcard-chat")

async def stream_flashcard_chat(
    doc_id: str,
    card_data: Dict[str, Any],
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None
):
    """
    Performs streaming AI chat discussing a specific flashcard.
    Provides heuristic hints without spoilers when reviewing the front,
    or deep dives, memory devices, and distinctions when reviewing the back.
    """
    card_type = card_data.get("type", "qa")
    type_label = "问答卡 (Q&A)" if card_type == "qa" else "镂空填空卡 (Cloze)"
    front = card_data.get("front", "").strip()
    back = card_data.get("back", "").strip()
    tags = ", ".join(card_data.get("tags", [])) or "无标签"

    system_prompt = (
        "你是一位循循善诱、风趣幽默的高级备考教官与记忆法大师。\n"
        f"用户正在复习一张【{type_label}】闪卡，内容如下：\n"
        f"- 【正面/考点问题】：{front}\n"
        f"- 【背面/标准答案】：{back}\n"
        f"- 【知识点标签】：{tags}\n\n"
        "助教复习辅导核心原则：\n"
        "1. **绝不剧透原则**：如果用户处于“卡片正面（未看答案）”状态并请求提示，严禁直接告知最终答案，而必须通过启发式提问、核心线索拆解、关联知识点或情境假设引导用户自主回忆；\n"
        "2. **深度拓展原则**：若用户要求解析、追问或探究原理，请条理清晰地剖析核心考点、概念机理、典型应用场景及学术背景。\n"
        "3. **强化记忆原则**：在适当时机提供巧妙的记忆法（如词根词缀、谐音联想、形象比喻、逻辑推演或顺口溜）。\n"
        "4. **易混概念辨析**：主动指出该考点最易混淆的陷阱或近义概念，必要时使用 Markdown 对比表格。\n"
        "5. **排版规范**：使用标准优雅的 Markdown 格式输出，重点术语加粗，结构层次鲜明。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    settings = get_study_settings(doc_id)
    provider = get_provider_for_task(
        "chat",
        settings,
        provider_override=provider_override,
        model_override=model_override
    )
    try:
        async for chunk in provider.stream_chat(messages, {"temperature": 0.4}):
            sse_line = chunk_to_sse(chunk)
            if sse_line:
                yield sse_line
    except Exception as e:
        logger.exception(f"Flashcard chat streaming error: {e}")
        yield f"data: {json.dumps({'error': f'闪卡助教连接异常: {str(e)}'})}\n\n"
