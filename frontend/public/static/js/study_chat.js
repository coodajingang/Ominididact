// ==========================================================
// AI Assistant Chat, Streaming & In-Chat Flashcards
// ==========================================================
function parseFlashcardBlock(block) {
    const lines = block.split('\n');
    let type = 'qa';
    let front = '';
    let back = '';
    let tags = '';
    let currentField = null;

    for (let rawLine of lines) {
        const trimmed = rawLine.trim();
        const lower = trimmed.toLowerCase();

        // 1. Type
        if (lower.startsWith('type:') || lower.startsWith('类型:') || lower.startsWith('类型：')) {
            const val = trimmed.split(/[:：]/)[1]?.trim()?.toLowerCase() || '';
            if (val.includes('cloze') || val.includes('挖空') || val.includes('镂空')) {
                type = 'cloze';
            } else {
                type = 'qa';
            }
            currentField = 'type';
            continue;
        }

        // 2. Front
        if (lower.startsWith('front:') || lower.startsWith('正面:') || lower.startsWith('正面：') || lower.startsWith('问题:') || lower.startsWith('问题：')) {
            const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：');
            const val = trimmed.slice(colonIdx + 1).trim();
            front = val;
            currentField = 'front';
            continue;
        }

        // 3. Back / Answer / Explanation
        if (lower.startsWith('back:') || lower.startsWith('背面:') || lower.startsWith('背面：') || 
            lower.startsWith('answer:') || lower.startsWith('答案:') || lower.startsWith('答案：') || 
            lower.startsWith('解析:') || lower.startsWith('解析：')) {
            const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：');
            const val = trimmed.slice(colonIdx + 1).trim();
            back = val;
            currentField = 'back';
            continue;
        }

        // 4. Tags
        if (lower.startsWith('tags:') || lower.startsWith('tag:') || lower.startsWith('标签:') || lower.startsWith('标签：')) {
            const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：');
            const val = trimmed.slice(colonIdx + 1).trim();
            tags = val;
            currentField = 'tags';
            continue;
        }

        // 5. Implicit back markers inside front (e.g. **考点提示：**, **解析：**, 考点提示：)
        if (currentField === 'front' && !back && /^(?:\*\*|__)?(?:考点提示|备考提示|提示|解析|答案|解题思路)[:：](?:\*\*|__)?/i.test(trimmed)) {
            back = trimmed;
            currentField = 'back';
            continue;
        }

        // 6. Multiline continuation
        if (currentField === 'front') {
            if (front) {
                front += '\n' + rawLine;
            } else {
                front = rawLine;
            }
        } else if (currentField === 'back') {
            if (back) {
                back += '\n' + rawLine;
            } else {
                back = rawLine;
            }
        } else if (currentField === 'tags') {
            if (trimmed) {
                tags = tags ? tags + ', ' + trimmed : trimmed;
            }
        }
    }

    front = front.trim();
    back = back.trim();

    // Auto-detect cloze if {{...}} syntax is present
    if (/\{\{.+?\}\}/.test(front)) {
        type = 'cloze';
    }

    // Fallback: If front is still empty, salvage any non-empty block content
    if (!front && block.trim()) {
        front = block.trim();
    }

    return {
        type: type,
        front: front,
        back: back,
        tags: tags.trim() ? tags.replace(/，/g, ',').split(',').map(t => t.trim()).filter(Boolean) : [],
        chapter_id: activeChapterId || ''
    };
}

function renderFlashcardWidget(c) {
    const isCloze = c.type === 'cloze';
    const badgeClass = isCloze ? 'chat-fc-cloze' : 'chat-fc-qa';
    const badgeText = isCloze ? '🧩 镂空闪卡' : '📝 问答闪卡';
    const frontHtml = isCloze
        ? renderMarkdownContent(c.front.replace(/\{\{(.*?)\}\}/g, '<span style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; padding: 1px 6px; border-radius: 4px; font-weight: bold;">[ $1 ]</span>'))
        : renderMarkdownContent(c.front);
    const backHtml = c.back ? renderMarkdownContent(c.back) : '';
    const tagsHtml = (c.tags || []).map(t => `<span style="background: rgba(0,0,0,0.15); padding: 1px 6px; border-radius: 4px; margin-right: 4px;">#${escapeHtml(t)}</span>`).join('');
    const cardJson = escapeHtml(JSON.stringify(c));

    return `
        <div class="chat-flashcard-widget" data-card="${cardJson}">
            <div class="chat-fc-header">
                <span class="chat-fc-badge ${badgeClass}">${badgeText}</span>
                <button type="button" class="chat-fc-add-btn" onclick="addCardFromChat(this)">+ 确认加入卡片组</button>
            </div>
            <div class="chat-fc-front"><strong>[题]</strong> ${frontHtml}</div>
            ${backHtml ? `<div class="chat-fc-back"><strong>[解]</strong> ${backHtml}</div>` : ''}
            ${tagsHtml ? `<div class="chat-fc-tags">${tagsHtml}</div>` : ''}
        </div>
    `;
}

function renderChatBubbleContent(text) {
    if (!text) return '';

    // Match :::flashcard ... ::: blocks, also tolerant of optional ``` wrapper or ```flashcard ... ```
    const fcRegex = /(?:```(?:flashcard)?\s*)?:::flashcard\s*([\s\S]*?)\s*:::(?:\s*```)?|```flashcard\s*([\s\S]*?)\s*```/g;
    
    let lastIndex = 0;
    let match;
    const pieces = [];

    // Parse into independent segments: Markdown text segments and Flashcard widget segments.
    // This avoids using temporary placeholders that can be mangled by Markdown compilers.
    while ((match = fcRegex.exec(text)) !== null) {
        const textBefore = text.slice(lastIndex, match.index);
        if (textBefore.trim()) {
            pieces.push(renderMarkdownContent(textBefore));
        }

        const block = match[1] !== undefined ? match[1] : match[2];
        const cardObj = parseFlashcardBlock(block);
        pieces.push(renderFlashcardWidget(cardObj));

        lastIndex = fcRegex.lastIndex;
    }

    const textAfter = text.slice(lastIndex);
    if (textAfter.trim()) {
        pieces.push(renderMarkdownContent(textAfter));
    }

    return pieces.length > 0 ? pieces.join('\n') : renderMarkdownContent(text);
}

async function addCardFromChat(btn) {
    if (btn.classList.contains('added')) return;
    const widget = btn.closest('.chat-flashcard-widget');
    if (!widget) return;
    try {
        const rawJson = widget.getAttribute('data-card');
        const cardData = JSON.parse(rawJson);
        if (!activeDocId) {
            alert("请先选择研学文档！");
            return;
        }
        cardData.chapter_id = activeChapterId || cardData.chapter_id || '';
        if (!cardData.paragraph_id && activeParagraphForChat && activeParagraphForChat.id) {
            cardData.paragraph_id = activeParagraphForChat.id;
        }
        btn.disabled = true;
        btn.textContent = '正在入库...';

        const resp = await fetch(`/api/study/documents/${activeDocId}/flashcards`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cardData)
        });

        if (resp.ok) {
            btn.classList.add('added');
            btn.innerHTML = '✓ 已加入卡片组';
            showToast("🎉 闪卡已成功加入卡片组！");
            updateTopFlashcardBadge();
        } else {
            const err = await resp.json();
            btn.disabled = false;
            btn.textContent = '+ 确认加入卡片组';
            alert(`加入失败: ${err.detail || '未知错误'}`);
        }
    } catch (err) {
        console.error("从对话加入闪卡异常", err);
        btn.disabled = false;
        btn.textContent = '+ 确认加入卡片组';
        alert("操作异常");
    }
}

        // Flashcards Toolbar & Quick Modal Handlers (State managed in study_state.js)

function adjustContextStep(type, delta) {
    if (type === 'prev') {
        chatPrevCount = Math.max(0, chatPrevCount + delta);
        const el = document.getElementById('step-prev-val');
        if (el) el.textContent = chatPrevCount;
    } else if (type === 'next') {
        chatNextCount = Math.max(0, chatNextCount + delta);
        const el = document.getElementById('step-next-val');
        if (el) el.textContent = chatNextCount;
    }
    updateDrawerContextPreview();
}

function promptSetContextStep(type) {
    const current = type === 'prev' ? chatPrevCount : chatNextCount;
    const label = type === 'prev' ? '前带段落数' : '后带段落数';
    const input = prompt(`请输入${label}（>= 0）：`, current);
    if (input === null) return;
    const val = parseInt(input.trim(), 10);
    if (!isNaN(val) && val >= 0) {
        if (type === 'prev') {
            chatPrevCount = val;
            const el = document.getElementById('step-prev-val');
            if (el) el.textContent = chatPrevCount;
        } else {
            chatNextCount = val;
            const el = document.getElementById('step-next-val');
            if (el) el.textContent = chatNextCount;
        }
        updateDrawerContextPreview();
    }
}

        function getParaPreviewHtml(p, isTarget) {
            const isImg = p.type === 'image' || p.type === 'scanned_page' || (p.english && p.english.includes('!['));
            if (!isImg) {
                return escapeHtml(p.english ? p.english.trim() : '');
            }
            const ext = (p.extracted_text || '').trim();
            if (isTarget) {
                return ext ? `🖼️ <b>[图片识别文字]</b>: ${escapeHtml(ext)}` : `🖼️ <b>[图件材料]</b> <span style="font-size:11px; opacity:0.8;">(多模态模型看图，文本模型识别文字)</span>`;
            } else {
                return ext ? `🖼️ <i>(图片识别文字)</i>: ${escapeHtml(ext)}` : `🖼️ <i>[图件/插图材料]</i>`;
            }
        }

        function updateDrawerContextPreview() {
            if (!activeChapterData || !activeParagraphForChat) return;
            const allParas = activeChapterData.paragraphs || [];
            const targetIdx = allParas.findIndex(p => p.id === activeParagraphForChat.id);
            if (targetIdx === -1) return;

            const prevCandidates = allParas.slice(0, targetIdx).filter(p => p.english && p.english.trim());
            const selectedPrev = chatPrevCount > 0 ? prevCandidates.slice(-chatPrevCount) : [];

            const nextCandidates = allParas.slice(targetIdx + 1).filter(p => p.english && p.english.trim());
            const selectedNext = chatNextCount > 0 ? nextCandidates.slice(0, chatNextCount) : [];

            let html = '';
            if (selectedPrev.length > 0) {
                const prevText = selectedPrev.map(p => getParaPreviewHtml(p, false)).join('<br><br>');
                html += `<div style="margin-bottom: 8px;"><span class="ctx-tag ctx-tag-prev">【前文背景（前 ${selectedPrev.length} 段）】</span><div style="color: var(--text-muted); font-size: 11.5px; line-height: 1.45;">${prevText}</div></div>`;
            }

            const targetText = getParaPreviewHtml(activeParagraphForChat, true);
            html += `<div><span class="ctx-tag ctx-tag-target">【核心研读段落】</span><div style="color: var(--text-main); font-weight: 600; font-size: 12.5px; line-height: 1.5;">${targetText}</div></div>`;

            if (selectedNext.length > 0) {
                const nextText = selectedNext.map(p => getParaPreviewHtml(p, false)).join('<br><br>');
                html += `<div style="margin-top: 8px;"><span class="ctx-tag ctx-tag-next">【后文背景（后 ${selectedNext.length} 段）】</span><div style="color: var(--text-muted); font-size: 11.5px; line-height: 1.45;">${nextText}</div></div>`;
            }

            document.getElementById('drawer-context-text').innerHTML = html;
        }

        // Chat Mode & AI Drawer Operations


        async function openChapterChat() {
            if (!activeChapterData) return;
            currentChatMode = 'chapter';
            chatHistory = [];

            document.querySelectorAll('.para-block').forEach(el => el.classList.remove('highlight'));

            const titleEl = document.querySelector('.drawer-title span');
            if (titleEl) titleEl.textContent = '🤖 AI 研学助教 · 全章脉络研读';

            // Hide paragraph steppers in chapter mode
            const steppers = document.querySelector('.context-steppers');
            if (steppers) steppers.style.display = 'none';

            // Set Chapter Context Banner
            const contextText = document.getElementById('drawer-context-text');
            if (contextText) {
                const pCount = activeChapterData.paragraphs?.length || 0;
                contextText.innerHTML = `
                    <div style="font-weight: 700; color: var(--accent-primary); font-size: 13px; margin-bottom: 4px;">
                        【全章宏观语境】《${escapeHtml(activeChapterData.title || '当前章节')}》
                    </div>
                    <div style="color: var(--text-muted); font-size: 12px; line-height: 1.5;">
                        共聚合本章全部 ${pCount} 个段落作为研学上下文。专用于全章逻辑脉络梳理、核心要点清单构建、宏观思辨与考点复习。
                    </div>
                `;
            }

            // Render chapter quick prompts chips
            renderChapterQuickPromptsChips();

            showAiDrawer();
            const inputEl = document.getElementById('drawer-input');
            inputEl.placeholder = "探讨全章核心观点、脉络演进或考点总结 (Enter 发送)...";
            inputEl.focus();

            // Load and render persistent chat history
            await loadAndRenderChatHistory('chapter', activeChapterId, null);
        }

        function renderChapterQuickPromptsChips() {
            const container = document.getElementById('drawer-quick-prompts');
            if (!container) return;
            container.innerHTML = customChapterQuickPrompts.map((item, idx) => `
                <div class="prompt-chip" onclick="handleChapterQuickPromptClick(${idx})" title="${escapeHtml(item.prompt)}">
                    ${escapeHtml(item.label)}
                </div>
            `).join('');
        }

        function handleChapterQuickPromptClick(idx) {
            const item = customChapterQuickPrompts[idx];
            if (item && item.prompt) {
                sendQuickPrompt(item.prompt);
            }
        }

        async function openAiChatForParagraph(paragraphId) {
            if (!activeChapterData) return;
            const p = activeChapterData.paragraphs.find(item => item.id === paragraphId);
            if (!p) return;

            currentChatMode = 'paragraph';
            activeParagraphForChat = p;
            chatHistory = [];
            chatPrevCount = 2;
            chatNextCount = 2;

            document.querySelectorAll('.para-block').forEach(el => el.classList.remove('highlight'));
            const el = document.getElementById(paragraphId);
            if (el) el.classList.add('highlight');

            const titleEl = document.querySelector('.drawer-title span');
            if (titleEl) titleEl.textContent = '🤖 AI 研学助教 · 段落研读';

            // Show paragraph steppers
            const steppers = document.querySelector('.context-steppers');
            if (steppers) steppers.style.display = 'flex';

            const prevEl = document.getElementById('step-prev-val');
            if (prevEl) prevEl.textContent = '2';
            const nextEl = document.getElementById('step-next-val');
            if (nextEl) nextEl.textContent = '2';

            updateDrawerContextPreview();
            renderParagraphQuickPromptsChips();

            showAiDrawer();
            const inputEl = document.getElementById('drawer-input');
            inputEl.placeholder = "输入您对该段落的疑问 (Enter 发送)...";
            inputEl.focus();

            // Load and render persistent chat history
            await loadAndRenderChatHistory('paragraph', activeChapterId, paragraphId);
        }

        function renderParagraphQuickPromptsChips() {
            const container = document.getElementById('drawer-quick-prompts');
            if (!container) return;
            container.innerHTML = customParagraphQuickPrompts.map((item, idx) => `
                <div class="prompt-chip" onclick="handleParagraphQuickPromptClick(${idx})" title="${escapeHtml(item.prompt)}">
                    ${escapeHtml(item.label)}
                </div>
            `).join('');
        }

        function handleParagraphQuickPromptClick(idx) {
            const item = customParagraphQuickPrompts[idx];
            if (item && item.prompt) {
                sendQuickPrompt(item.prompt);
            }
        }

        // Backward compatibility aliases
        function renderChapterQuickPrompts() { renderChapterQuickPromptsChips(); }
        function renderQuickPromptsChips() { renderParagraphQuickPromptsChips(); }

        async function loadAndRenderChatHistory(chatType, chapterId, paragraphId) {
            const msgBox = document.getElementById('drawer-messages');
            if (!msgBox) return;

            msgBox.innerHTML = `
                <div style="text-align: center; padding: 24px 10px; color: var(--text-muted); font-size: 12px;">
                    <div style="display: inline-block; animation: spin 1s linear infinite; margin-bottom: 6px;">⏳</div>
                    <div>正在载入研学对话记录...</div>
                </div>
            `;

            try {
                let url = `/api/study/documents/${activeDocId}/chat_history?chat_type=${chatType}&chapter_id=${encodeURIComponent(chapterId)}`;
                if (chatType === 'paragraph' && paragraphId) {
                    url += `&paragraph_id=${encodeURIComponent(paragraphId)}`;
                }

                const resp = await fetch(url);
                const res = resp.ok ? await resp.json() : null;
                const messages = (res && res.data && Array.isArray(res.data.messages)) ? res.data.messages : [];

                msgBox.innerHTML = '';
                chatHistory = [];

                if (messages.length === 0) {
                    const greeting = chatType === 'chapter'
                        ? `您好！我是您的全章文献研读助教。我已经通读了《${escapeHtml(activeChapterData?.title || '当前章节')}》的全章内容，随时向我提问全章脉络架构、核心观点对比或考点总结！`
                        : `您好！我是您的文献研读助教。我已经锁定了当前核心研读段落，并默认带入前2段与后2段作为背景上下文（可根据需要在上方按需调整）。随时向我提问长难句、学术词汇或核心观点！`;

                    msgBox.innerHTML = `
                        <div class="chat-bubble-container">
                            <div class="chat-bubble assistant">${escapeHtml(greeting)}</div>
                        </div>
                    `;
                    return;
                }

                for (const msg of messages) {
                    chatHistory.push({ role: msg.role, content: msg.content });
                    const container = document.createElement('div');
                    container.className = 'chat-bubble-container';

                    if (msg.role === 'user') {
                        container.innerHTML = `<div class="chat-bubble user">${escapeHtml(msg.content)}</div>`;
                    } else {
                        const bubble = document.createElement('div');
                        bubble.className = 'chat-bubble assistant';
                        bubble.innerHTML = renderChatBubbleContent(msg.content);
                        container.appendChild(bubble);

                        const actionsRow = document.createElement('div');
                        actionsRow.className = 'bubble-actions-row';

                        const copyBtn = document.createElement('button');
                        copyBtn.className = 'bubble-action-btn';
                        copyBtn.innerHTML = '📋 复制回答';
                        copyBtn.onclick = () => copyText(msg.content);
                        actionsRow.appendChild(copyBtn);

                        if (chatType === 'paragraph') {
                            const saveParaNoteBtn = document.createElement('button');
                            saveParaNoteBtn.className = 'bubble-action-btn btn-highlight';
                            saveParaNoteBtn.innerHTML = '📌 存为段落注解';
                            saveParaNoteBtn.onclick = () => saveBubbleAsParagraphNote(saveParaNoteBtn, msg.content);
                            actionsRow.appendChild(saveParaNoteBtn);
                        } else {
                            const saveHeaderBtn = document.createElement('button');
                            saveHeaderBtn.className = 'bubble-action-btn btn-highlight';
                            saveHeaderBtn.innerHTML = '📌 存为章首总结';
                            saveHeaderBtn.onclick = () => saveBubbleAsChapterNote(saveHeaderBtn, 'header', msg.content);
                            actionsRow.appendChild(saveHeaderBtn);

                            const saveFooterBtn = document.createElement('button');
                            saveFooterBtn.className = 'bubble-action-btn';
                            saveFooterBtn.innerHTML = '📌 存为章尾总结';
                            saveFooterBtn.onclick = () => saveBubbleAsChapterNote(saveFooterBtn, 'footer', msg.content);
                            actionsRow.appendChild(saveFooterBtn);
                        }
                        container.appendChild(actionsRow);
                    }
                    msgBox.appendChild(container);
                }
                msgBox.scrollTop = msgBox.scrollHeight;
            } catch (err) {
                console.error("加载历史对话记录异常", err);
                msgBox.innerHTML = `
                    <div class="chat-bubble-container">
                        <div class="chat-bubble assistant">加载历史记录失败，可直接开始新的对话。</div>
                    </div>
                `;
            }
        }

        async function clearCurrentChatHistory() {
            if (!activeDocId || !activeChapterId) return;
            const scopeDesc = currentChatMode === 'chapter' ? '本章研读' : '本段研读';
            if (!confirm(`确定要清空【${scopeDesc}】的历史对话记录吗？清空后不可恢复。`)) return;

            try {
                let url = `/api/study/documents/${activeDocId}/chat_history?chat_type=${currentChatMode}&chapter_id=${encodeURIComponent(activeChapterId)}`;
                if (currentChatMode === 'paragraph' && activeParagraphForChat) {
                    url += `&paragraph_id=${encodeURIComponent(activeParagraphForChat.id)}`;
                }
                const resp = await fetch(url, { method: 'DELETE' });
                if (resp.ok) {
                    showToast("历史对话记录已清空");
                    chatHistory = [];
                    if (currentChatMode === 'chapter') {
                        await loadAndRenderChatHistory('chapter', activeChapterId, null);
                    } else if (activeParagraphForChat) {
                        await loadAndRenderChatHistory('paragraph', activeChapterId, activeParagraphForChat.id);
                    }
                } else {
                    alert("清空对话记录失败");
                }
            } catch (err) {
                console.error("清空历史记录异常", err);
                alert("清空操作异常");
            }
        }

        let activeChatProvider = 'openai_compatible';
        let activeChatModel = 'deepseek-chat';

        async function syncChatActiveModelSelector() {
            const selectEl = document.getElementById('chat-active-model-select');
            if (!selectEl) return;

            try {
                let url = '/api/study/settings';
                if (activeDocId) {
                    url += `?doc_id=${encodeURIComponent(activeDocId)}`;
                }
                const resp = await fetch(url);
                if (resp.ok) {
                    const data = await resp.json();
                    const s = data.data || {};
                    activeChatProvider = s.chat_provider || s.default_chat_provider || s.llm_source || 'openai_compatible';
                    activeChatModel = s.chat_model || s.default_chat_model || s.text_model || 'deepseek-chat';

                    // Fetch models for active chat provider
                    let models = [];
                    if (typeof fetchProviderModels === 'function') {
                        models = await fetchProviderModels(activeChatProvider);
                    }

                    const currentSelected = selectEl.value;
                    selectEl.innerHTML = '';

                    const allModels = Array.from(new Set([activeChatModel, ...models])).filter(Boolean);

                    allModels.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m;
                        opt.textContent = m;
                        opt.dataset.provider = activeChatProvider;
                        if (currentSelected ? m === currentSelected : m === activeChatModel) {
                            opt.selected = true;
                        }
                        selectEl.appendChild(opt);
                    });

                    if (allModels.length === 0) {
                        const opt = document.createElement('option');
                        opt.value = activeChatModel;
                        opt.textContent = activeChatModel || '默认模型';
                        opt.dataset.provider = activeChatProvider;
                        opt.selected = true;
                        selectEl.appendChild(opt);
                    }
                }
            } catch (e) {
                console.warn("同步聊天模型列表失败:", e);
            }
        }

        function onChatActiveModelChanged() {
            const selectEl = document.getElementById('chat-active-model-select');
            if (selectEl) {
                activeChatModel = selectEl.value;
                const opt = selectEl.options[selectEl.selectedIndex];
                if (opt && opt.dataset.provider) {
                    activeChatProvider = opt.dataset.provider;
                }
                showToast(`🤖 当前助教模型已切换为: ${activeChatModel}`);
            }
        }

        function showAiDrawer() {
            const drawer = document.getElementById('ai-drawer');
            if (!drawer) return;
            const savedW = localStorage.getItem('study_drawer_width') || '460px';
            drawer.style.width = savedW;
            drawer.classList.add('open');
            const toggleBtn = document.getElementById('btn-toggle-ai-drawer');
            if (toggleBtn) {
                toggleBtn.classList.add('active');
                toggleBtn.style.borderColor = 'var(--accent-primary)';
                toggleBtn.style.color = 'var(--accent-primary)';
            }
            syncChatActiveModelSelector();
        }

        function closeAiDrawer() {
            const drawer = document.getElementById('ai-drawer');
            if (drawer) {
                drawer.classList.remove('open');
                drawer.style.width = '';
            }
            const toggleBtn = document.getElementById('btn-toggle-ai-drawer');
            if (toggleBtn) {
                toggleBtn.classList.remove('active');
                toggleBtn.style.borderColor = '';
                toggleBtn.style.color = '';
            }
            document.querySelectorAll('.para-block').forEach(el => el.classList.remove('highlight'));
        }

        function toggleAiDrawer() {
            const drawer = document.getElementById('ai-drawer');
            if (!drawer) return;
            if (drawer.classList.contains('open')) {
                closeAiDrawer();
            } else {
                if (activeParagraphForChat) {
                    openAiChatForParagraph(activeParagraphForChat.id);
                } else if (activeChapterData) {
                    openChapterChat();
                } else {
                    showAiDrawer();
                    const inputEl = document.getElementById('drawer-input');
                    if (inputEl) inputEl.focus();
                }
            }
        }

        function sendQuickPrompt(promptText) {
            document.getElementById('drawer-input').value = promptText;
            sendDrawerMessage();
        }

        function handleDrawerInputKey(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendDrawerMessage();
            }
        }

        async function sendDrawerMessage() {
            const input = document.getElementById('drawer-input');
            const message = input.value.trim();
            if (!message) return;

            if (currentChatMode === 'paragraph' && !activeParagraphForChat) {
                if (activeChapterData && activeChapterData.paragraphs && activeChapterData.paragraphs.length > 0) {
                    activeParagraphForChat = activeChapterData.paragraphs[0];
                    updateDrawerContextPreview();
                } else {
                    alert("请先点击正文段落右侧的【💬 探讨】选择研读段落，或点击章首的【🧠 全章研读】！");
                    return;
                }
            }
            if (currentChatMode === 'chapter' && !activeChapterId) {
                alert("请先选择研读的章节！");
                return;
            }

            input.value = '';
            const msgBox = document.getElementById('drawer-messages');

            // User Bubble
            const userContainer = document.createElement('div');
            userContainer.className = 'chat-bubble-container';
            userContainer.innerHTML = `
                <div class="chat-bubble user">${escapeHtml(message)}</div>
            `;
            msgBox.appendChild(userContainer);

            // Assistant Bubble Container
            const assistantContainer = document.createElement('div');
            assistantContainer.className = 'chat-bubble-container';
            assistantContainer.innerHTML = `
                <div class="chat-bubble assistant">思考解答中...</div>
            `;
            msgBox.appendChild(assistantContainer);
            msgBox.scrollTop = msgBox.scrollHeight;

            chatHistory.push({ role: "user", content: message });

            try {
                let endpoint, payload;
                const activeModelSelect = document.getElementById('chat-active-model-select');
                const selectedModel = activeModelSelect ? activeModelSelect.value : activeChatModel;
                const selectedProvider = (activeModelSelect && activeModelSelect.selectedOptions && activeModelSelect.selectedOptions[0]) 
                    ? activeModelSelect.selectedOptions[0].dataset.provider 
                    : activeChatProvider;

                if (currentChatMode === 'chapter') {
                    endpoint = `/api/study/documents/${activeDocId}/chapter_chat`;
                    payload = {
                        chapter_id: activeChapterId,
                        message: message,
                        history: chatHistory.slice(0, -1),
                        model: selectedModel,
                        provider: selectedProvider
                    };
                } else {
                    endpoint = `/api/study/documents/${activeDocId}/paragraph_chat`;
                    payload = {
                        chapter_id: activeChapterId,
                        paragraph_id: activeParagraphForChat.id,
                        message: message,
                        history: chatHistory.slice(0, -1),
                        prev_count: chatPrevCount,
                        next_count: chatNextCount,
                        model: selectedModel,
                        provider: selectedProvider
                    };
                }

                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    let errDetail = `HTTP ${response.status}`;
                    try {
                        const errJson = await response.json();
                        if (errJson.detail) errDetail = errJson.detail;
                    } catch(e) {}
                    assistantContainer.querySelector('.chat-bubble').innerHTML = `<span style="color:#ef4444;">[请求异常: ${escapeHtml(errDetail)}]</span>`;
                    return;
                }

                const bubbleEl = assistantContainer.querySelector('.chat-bubble');
                bubbleEl.innerHTML = '';
                let fullAnswer = '';

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data:')) {
                            const raw = line.slice(5).trim();
                            if (raw === '[DONE]') continue;
                            try {
                                const parsed = JSON.parse(raw);
                                if (parsed.error) {
                                    fullAnswer += `\n\n> ⚠️ **助教提示**: ${parsed.error}`;
                                    bubbleEl.innerHTML = renderMarkdownContent(fullAnswer);
                                    continue;
                                }
                                const delta = parsed.choices?.[0]?.delta?.content ?? parsed.choices?.[0]?.text ?? '';
                                if (delta) {
                                    fullAnswer += delta;
                                    bubbleEl.innerHTML = renderChatBubbleContent(fullAnswer);
                                }
                            } catch (err) {}
                        }
                    }
                }

                if (!fullAnswer.trim()) {
                    bubbleEl.innerHTML = `<span style="color:#ef4444;">[未能从大模型获取到有效回复，请在【⚙️ 翻译设置】中检查模型连接及配置]</span>`;
                    return;
                }

                bubbleEl.innerHTML = renderChatBubbleContent(fullAnswer);

                // Add bubble actions bar (copy + save note)
                const actionsRow = document.createElement('div');
                actionsRow.className = 'bubble-actions-row';

                const copyBtn = document.createElement('button');
                copyBtn.className = 'bubble-action-btn';
                copyBtn.innerHTML = '📋 复制回答';
                copyBtn.onclick = () => copyText(fullAnswer);
                actionsRow.appendChild(copyBtn);

                if (currentChatMode === 'paragraph') {
                    const saveParaNoteBtn = document.createElement('button');
                    saveParaNoteBtn.className = 'bubble-action-btn btn-highlight';
                    saveParaNoteBtn.innerHTML = '📌 存为段落注解';
                    saveParaNoteBtn.onclick = () => saveBubbleAsParagraphNote(saveParaNoteBtn, fullAnswer);
                    actionsRow.appendChild(saveParaNoteBtn);
                } else {
                    const saveHeaderBtn = document.createElement('button');
                    saveHeaderBtn.className = 'bubble-action-btn btn-highlight';
                    saveHeaderBtn.innerHTML = '📌 存为章首总结';
                    saveHeaderBtn.onclick = () => saveBubbleAsChapterNote(saveHeaderBtn, 'header', fullAnswer);
                    actionsRow.appendChild(saveHeaderBtn);

                    const saveFooterBtn = document.createElement('button');
                    saveFooterBtn.className = 'bubble-action-btn';
                    saveFooterBtn.innerHTML = '📌 存为章尾总结';
                    saveFooterBtn.onclick = () => saveBubbleAsChapterNote(saveFooterBtn, 'footer', fullAnswer);
                    actionsRow.appendChild(saveFooterBtn);
                }

                assistantContainer.appendChild(actionsRow);
                chatHistory.push({ role: "assistant", content: fullAnswer });
            } catch (e) {
                console.error("AI 提问失败", e);
                assistantContainer.querySelector('.chat-bubble').textContent = "提问遇到异常，请检查服务连接。";
            }
        }

        // Multi-Notes CRUD & State (activeNoteContext managed in study_state.js)

function initDrawerResize() {
            const drawer = document.getElementById('ai-drawer');
            const handle = document.getElementById('drawer-resize-handle');
            if (!drawer || !handle) return;
            let isResizing = false;
            let startX, startWidth;

            // Restore saved width if preference exists
            const savedWidth = localStorage.getItem('study_drawer_width');
            if (savedWidth) {
                const parsed = parseInt(savedWidth, 10);
                if (parsed >= 340 && parsed <= Math.min(window.innerWidth - 450, 950)) {
                    drawer.style.width = parsed + 'px';
                }
            }

            handle.addEventListener('mousedown', (e) => {
                isResizing = true;
                startX = e.clientX;
                startWidth = parseInt(document.defaultView.getComputedStyle(drawer).width, 10);
                drawer.classList.add('resizing');
                handle.classList.add('active');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
                document.documentElement.addEventListener('mousemove', onMouseMove, false);
                document.documentElement.addEventListener('mouseup', onMouseUp, false);
                e.preventDefault();
            });

            function onMouseMove(e) {
                if (!isResizing) return;
                // Dragging to left increases width; dragging to right decreases it
                const delta = startX - e.clientX;
                const newWidth = startWidth + delta;
                const minW = 340;
                const maxW = Math.max(minW, Math.min(window.innerWidth - 450, 950));
                if (newWidth >= minW && newWidth <= maxW) {
                    drawer.style.width = newWidth + 'px';
                }
            }

            function onMouseUp() {
                if (!isResizing) return;
                isResizing = false;
                drawer.classList.remove('resizing');
                handle.classList.remove('active');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                document.documentElement.removeEventListener('mousemove', onMouseMove, false);
                document.documentElement.removeEventListener('mouseup', onMouseUp, false);

                const finalW = parseInt(document.defaultView.getComputedStyle(drawer).width, 10);
                if (finalW >= 340) {
                    localStorage.setItem('study_drawer_width', finalW + 'px');
                }
            }
        }

        // Settings Modal
