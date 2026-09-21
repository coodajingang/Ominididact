// ==========================================================
// Reading Stream, Translation & Batch Processing
// ==========================================================
function renderParagraphs(paragraphs) {
            const container = document.getElementById('paragraphs-stream');
            if (!paragraphs || paragraphs.length === 0) {
                container.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted);">本章节暂无内容</div>`;
                return;
            }

            // Apply active layout class
            container.className = `paragraphs-stream layout-${currentLayoutMode}`;
            const isZh = activeDocMeta && activeDocMeta.language === 'zh';
            const isSideBySide = currentLayoutMode === 'side-by-side';
            const isTopBottom = currentLayoutMode === 'top-bottom';

            container.innerHTML = paragraphs.map(p => {
                // 1. Embedded Image Block
                if (p.type === 'image') {
                    return `
                        <div class="para-block ${isSideBySide ? 'para-block-fullwidth' : ''}" id="${p.id}">
                            <div class="scanned-img-wrapper">
                                <img src="${p.image_url}" alt="Figure" onclick="window.open('${p.image_url}', '_blank')">
                            </div>
                            <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                ${renderParaNotesList(p.id, p.notes || [])}
                            </div>
                            <hr class="para-divider">
                        </div>
                    `;
                }

                // 2. Code Block / Mathematical Formula (Preserved verbatim without translation)
                if (p.type === 'code') {
                    return `
                        <div class="para-block ${isSideBySide ? 'para-block-fullwidth' : ''}" id="${p.id}">
                            <div class="code-block-card" style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; padding: 12px; margin: 8px 0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13.5px; position: relative;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.08); color: #94a3b8; font-size: 11px;">
                                    <span>💻 代码 / 公式块 (原样保留，无需翻译)</span>
                                    <button class="action-chip" onclick="copyParagraph('${encodeURIComponent(p.english || '')}', '')" title="复制代码">📋 复制</button>
                                </div>
                                <div style="color: #38bdf8; white-space: pre-wrap; word-break: break-all;">${renderMarkdownContent(p.english || '')}</div>
                            </div>
                            <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                ${renderParaNotesList(p.id, p.notes || [])}
                            </div>
                            <hr class="para-divider">
                        </div>
                    `;
                }

                // 3. Caption / Footnote Block
                if (p.type === 'caption') {
                    return `
                        <div class="para-block ${isSideBySide ? 'para-block-fullwidth' : ''}" id="${p.id}">
                            <div style="text-align: center; color: #94a3b8; font-style: italic; font-size: 13.5px; margin: 4px 0 10px 0;">
                                ${renderMarkdownContent(p.english || '')}
                            </div>
                            <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                ${renderParaNotesList(p.id, p.notes || [])}
                            </div>
                            <hr class="para-divider">
                        </div>
                    `;
                }

                // Common Actions Bar (Pill on Hover in compact modes, Row in card mode)
                const hasTranslation = Boolean(p.chinese && p.chinese.trim());
                const canTranslate = !isZh && !p.no_translate && p.type !== 'code' && p.type !== 'caption';
                const notesCount = (p.notes && p.notes.length) || 0;
                const actionsHtml = `
                    <div class="para-actions">
                        ${canTranslate && !hasTranslation ? `
                            <button class="action-chip" id="btn-trans-${p.id}" onclick="translateParagraph('${p.id}')" title="翻译此段">
                                <span>🌐 翻译</span>
                            </button>
                        ` : ''}
                        ${canTranslate && hasTranslation ? `
                            <button class="action-chip" id="btn-trans-${p.id}" onclick="translateParagraph('${p.id}')" title="重新翻译此段">
                                <span>🔄 重译</span>
                            </button>
                        ` : ''}
                        <button class="action-chip" onclick="promptAddParagraphNote('${p.id}')" title="添加或查看段落研读笔记">
                            <span>📝 笔记${notesCount > 0 ? ` (${notesCount})` : ''}</span>
                        </button>
                        <button class="action-chip" onclick="copyParagraph('${encodeURIComponent(p.english || '')}', '${encodeURIComponent(p.chinese || '')}')" title="复制双语 Markdown">
                            <span>📋 复制</span>
                        </button>
                        <button class="action-chip chat-chip" onclick="openAiChatForParagraph('${p.id}')" title="针对此段向 AI 助教提问">
                            <span>💬 探讨</span>
                        </button>
                        <button class="action-chip" onclick="openCreateFlashcardFromParagraph('${p.id}')" title="将本段考点快速制作成闪卡">
                            <span>🗂️ 制卡</span>
                        </button>
                    </div>
                `;

                // 2. Scanned Page Block
                if (p.type === 'scanned_page') {
                    const hasOcr = Boolean(p.english && p.english.trim());
                    const engHtml = renderMarkdownContent(p.english || '');
                    const cnHtml = renderMarkdownContent(p.chinese || '');

                    if (isSideBySide) {
                        return `
                            <div class="para-block" id="${p.id}">
                                <div class="side-col side-col-left">
                                    <div class="scanned-img-wrapper">
                                        <img src="${p.image_url}" alt="Page ${p.page}" onclick="window.open('${p.image_url}', '_blank')">
                                    </div>
                                    ${hasOcr ? `
                                        <div class="ocr-extracted-box">
                                            <div class="ocr-label">📄 识别英文 (P${p.page})</div>
                                            <div>${engHtml}</div>
                                        </div>
                                    ` : ''}
                                </div>
                                <div class="side-col side-col-right">
                                    ${hasTranslation ? `
                                        <div class="para-chinese-quote">
                                            <div class="ocr-label" style="color: #a5b4fc;">🇨🇳 中文译文</div>
                                            <div>${cnHtml}</div>
                                        </div>
                                    ` : ''}
                                </div>
                                ${actionsHtml}
                                <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                    ${renderParaNotesList(p.id, p.notes || [])}
                                </div>
                            </div>
                        `;
                    }

                    return `
                        <div class="para-block" id="${p.id}">
                            <div class="scanned-page-box">
                                <div class="scanned-img-wrapper">
                                    <img src="${p.image_url}" alt="Page ${p.page}" onclick="window.open('${p.image_url}', '_blank')">
                                </div>

                                ${hasOcr ? `
                                    <div class="ocr-extracted-box">
                                        <div class="ocr-label">📄 识别英文原文 (Page ${p.page})</div>
                                        <div>${engHtml}</div>
                                    </div>
                                ` : ''}

                                ${hasTranslation ? `
                                    <div class="para-chinese-quote">
                                        <div class="ocr-label" style="color: #a5b4fc;">🇨🇳 中文译文</div>
                                        <div>${cnHtml}</div>
                                    </div>
                                ` : ''}
                            </div>

                            <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                ${renderParaNotesList(p.id, p.notes || [])}
                            </div>
                            <hr class="para-divider">
                            ${actionsHtml}
                        </div>
                    `;
                }

                // 3. Regular Text Paragraph
                const engHtml = renderMarkdownContent(p.english || '');
                const cnHtml = renderMarkdownContent(p.chinese || '');

                // Mode: Side-by-Side (bilingual_book_maker side-by-side)
                if (isSideBySide) {
                    return `
                        <div class="para-block" id="${p.id}">
                            <div class="side-col side-col-left">
                                <div class="para-english">${engHtml}</div>
                            </div>
                            <div class="side-col side-col-right">
                                ${hasTranslation ? `
                                    <div class="para-chinese-quote">${cnHtml}</div>
                                ` : ''}
                            </div>
                            ${actionsHtml}
                            <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                ${renderParaNotesList(p.id, p.notes || [])}
                            </div>
                        </div>
                    `;
                }

                // Mode: Top-Bottom (bilingual_book_maker default compact flow)
                if (isTopBottom) {
                    return `
                        <div class="para-block" id="${p.id}">
                            <div class="para-english">${engHtml}</div>
                            ${!isZh && hasTranslation ? `
                                <div class="para-chinese-quote">${cnHtml}</div>
                            ` : ''}
                            ${actionsHtml}
                            <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                                ${renderParaNotesList(p.id, p.notes || [])}
                            </div>
                        </div>
                    `;
                }

                // Mode: Card Flow
                return `
                    <div class="para-block" id="${p.id}">
                        <div class="para-english">${engHtml}</div>
                        ${!isZh && hasTranslation ? `
                            <div class="para-chinese-quote">${cnHtml}</div>
                        ` : ''}
                        <div class="para-notes-wrapper" id="notes-wrap-${p.id}">
                            ${renderParaNotesList(p.id, p.notes || [])}
                        </div>
                        <hr class="para-divider">
                        ${actionsHtml}
                    </div>
                `;
            }).join('');
        }

        // Translate a Single Paragraph On-Demand
        async function translateParagraph(paragraphId) {
            const btn = document.getElementById(`btn-trans-${paragraphId}`);
            if (btn) {
                btn.classList.add('loading');
                btn.innerHTML = `<span>⏳ 翻译中...</span>`;
            }

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/translate_paragraph`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chapter_id: activeChapterId,
                        paragraph_id: paragraphId
                    })
                });
                const result = await res.json();
                if (result.code === 200) {
                    // Update in-memory data
                    const updatedP = result.data;
                    const idx = activeChapterData.paragraphs.findIndex(item => item.id === paragraphId);
                    if (idx !== -1) {
                        activeChapterData.paragraphs[idx] = updatedP;
                    }
                    renderParagraphs(activeChapterData.paragraphs);
                } else {
                    alert("翻译失败: " + result.detail || result.message);
                    if (btn) {
                        btn.classList.remove('loading');
                        btn.innerHTML = `<span>🌐 翻译此段</span>`;
                    }
                }
            } catch (e) {
                console.error("翻译请求异常", e);
                alert("翻译请求失败，请检查服务");
                if (btn) {
                    btn.classList.remove('loading');
                    btn.innerHTML = `<span>🌐 翻译此段</span>`;
                }
            }
        }

        // Chapter Batch Translation Controller (Isolated per chapter, async background with polling)
        let chapterTranslateTimer = null;
        let lastCompletedCount = 0;

        async function checkAndUpdateChapterTranslateBtn(chapterId) {
            if (!activeDocId || !chapterId) return;
            const btn = document.getElementById('btn-batch-translate-ch');
            if (!btn) return;

            if (activeDocMeta && activeDocMeta.language === 'zh') {
                btn.style.display = 'none';
                return;
            }
            btn.style.display = 'inline-flex';

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${chapterId}/translate_status`);
                if (!res.ok) return;
                const result = await res.json();
                const status = result.data;
                if (!status) return;

                // Guard against chapter switch while fetching
                if (chapterId !== activeChapterId) return;

                if (status.is_running) {
                    btn.className = 'btn btn-warning';
                    btn.innerHTML = `<span>⏸️ 停止翻译 (${status.completed}/${status.total} 段, ${status.percent}%)</span>`;
                    btn.title = "点击暂停/停止本章后台批量翻译";
                    if (!chapterTranslateTimer) {
                        startChapterTranslatePolling(chapterId);
                    }
                } else {
                    stopChapterTranslatePolling();
                    const untranslated = (status.untranslated !== undefined) 
                        ? status.untranslated 
                        : Math.max(0, (status.total || 0) - (status.completed || 0));
                    if (untranslated === 0 && status.total > 0) {
                        btn.className = 'btn btn-primary';
                        btn.innerHTML = `<span>🔄 重新批量翻译本章</span>`;
                        btn.title = "本章所有段落已完成翻译，点击可重新检查或重译失败段";
                    } else {
                        btn.className = 'btn btn-primary';
                        btn.innerHTML = `<span>⚡ 批量翻译本章 (${untranslated} 段未译)</span>`;
                        btn.title = "自动翻译本章未完成或失败的段落";
                    }
                }
            } catch (e) {
                console.error("查询章节翻译状态失败", e);
            }
        }

        function startChapterTranslatePolling(chapterId) {
            stopChapterTranslatePolling();
            chapterTranslateTimer = setInterval(async () => {
                if (chapterId !== activeChapterId) {
                    stopChapterTranslatePolling();
                    return;
                }
                try {
                    const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${chapterId}/translate_status`);
                    if (!res.ok) return;
                    const result = await res.json();
                    const status = result.data;
                    if (!status) return;

                    const btn = document.getElementById('btn-batch-translate-ch');
                    if (status.is_running) {
                        if (btn) {
                            btn.className = 'btn btn-warning';
                            btn.innerHTML = `<span>⏸️ 停止翻译 (${status.completed}/${status.total} 段, ${status.percent}%)</span>`;
                        }
                        // Refresh chapter data when progress increases
                        if (status.completed > lastCompletedCount) {
                            lastCompletedCount = status.completed;
                            refreshChapterDataSilently(chapterId);
                        }
                    } else {
                        stopChapterTranslatePolling();
                        checkAndUpdateChapterTranslateBtn(chapterId);
                        refreshChapterDataSilently(chapterId);
                    }
                } catch (err) {
                    console.error("轮询章节翻译进度出错", err);
                }
            }, 1500);
        }

        function stopChapterTranslatePolling() {
            if (chapterTranslateTimer) {
                clearInterval(chapterTranslateTimer);
                chapterTranslateTimer = null;
            }
        }

        async function refreshChapterDataSilently(chapterId) {
            if (chapterId !== activeChapterId) return;
            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${chapterId}`);
                if (res.ok) {
                    const result = await res.json();
                    activeChapterData = result.data.chapter;
                    renderParagraphs(activeChapterData.paragraphs || []);
                }
            } catch (e) {}
        }

        async function toggleBatchTranslateCurrentChapter() {
            if (!activeDocId || !activeChapterId) return;
            const btn = document.getElementById('btn-batch-translate-ch');
            if (btn && btn.classList.contains('btn-warning')) {
                await stopBatchTranslateCurrentChapter();
            } else {
                await startBatchTranslateCurrentChapter();
            }
        }

        async function startBatchTranslateCurrentChapter() {
            if (!activeDocId || !activeChapterId) return;
            const btn = document.getElementById('btn-batch-translate-ch');
            if (btn) {
                btn.className = 'btn btn-warning';
                btn.innerHTML = `<span>⏳ 启动翻译任务中...</span>`;
            }

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/translate_start`, {
                    method: 'POST'
                });
                const result = await res.json();
                if (result.code === 200) {
                    lastCompletedCount = 0;
                    startChapterTranslatePolling(activeChapterId);
                } else {
                    alert("启动批量翻译失败: " + result.message);
                    checkAndUpdateChapterTranslateBtn(activeChapterId);
                }
            } catch (e) {
                console.error("启动批量翻译异常", e);
                checkAndUpdateChapterTranslateBtn(activeChapterId);
            }
        }

        async function stopBatchTranslateCurrentChapter() {
            if (!activeDocId || !activeChapterId) return;
            const btn = document.getElementById('btn-batch-translate-ch');
            if (btn) {
                btn.innerHTML = `<span>⏳ 正在停止...</span>`;
            }

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/translate_stop`, {
                    method: 'POST'
                });
                const result = await res.json();
                stopChapterTranslatePolling();
                await refreshChapterDataSilently(activeChapterId);
                showToast("已停止批量翻译，已完成段落已完整保留");
                setTimeout(async () => {
                    await refreshChapterDataSilently(activeChapterId);
                    checkAndUpdateChapterTranslateBtn(activeChapterId);
                }, 600);
            } catch (e) {
                console.error("停止批量翻译异常", e);
                checkAndUpdateChapterTranslateBtn(activeChapterId);
            }
        }

        // Upload Document

function copyParagraph(encEng, encCn) {
            const eng = decodeURIComponent(encEng);
            const cn = decodeURIComponent(encCn);
            let md = eng;
            if (cn) {
                md += `\n\n> ${cn}\n\n---`;
            } else {
                md += `\n\n---`;
            }
            navigator.clipboard.writeText(md).then(() => {
                showToast("已复制双语 Markdown 到剪贴板！");
            });
        }

// ==========================================================
// Quick Scroll Navigator & Reading Stream Scroll Handler
// ==========================================================
let scrollSaveDebounceTimer = null;
let isDraggingQuickScrollThumb = false;
let quickScrollFadeTimeout = null;

function flashQuickScrollNavigator() {
    const qNav = document.getElementById('quick-scroll-navigator');
    if (!qNav) return;
    qNav.classList.add('scrolling');
    if (quickScrollFadeTimeout) clearTimeout(quickScrollFadeTimeout);
    quickScrollFadeTimeout = setTimeout(() => {
        qNav.classList.remove('scrolling');
    }, 1200);
}

function initQuickScrollNavigator() {
    const container = document.getElementById('reading-container');
    if (!container) return;

    // Listen to scroll events on reading-container
    container.addEventListener('scroll', () => {
        updateQuickScrollWidget();
        flashQuickScrollNavigator();

        // Debounced persistence to avoid spamming localStorage
        if (scrollSaveDebounceTimer) clearTimeout(scrollSaveDebounceTimer);
        scrollSaveDebounceTimer = setTimeout(() => {
            if (typeof saveCurrentDocProgress === 'function') {
                saveCurrentDocProgress();
            }
        }, 400);
    }, { passive: true });

    // Drag handling for the thumb
    const thumb = document.getElementById('quick-scroll-thumb');
    const track = document.getElementById('quick-scroll-track');
    if (!thumb || !track) return;

    function handleDrag(e) {
        if (!isDraggingQuickScrollThumb) return;
        const rect = track.getBoundingClientRect();
        const clientY = (e.touches && e.touches[0]) ? e.touches[0].clientY : e.clientY;
        let ratio = (clientY - rect.top) / rect.height;
        ratio = Math.max(0, Math.min(1, ratio));

        const maxScroll = container.scrollHeight - container.clientHeight;
        container.scrollTop = ratio * maxScroll;
        updateQuickScrollWidget();
    }

    thumb.addEventListener('mousedown', (e) => {
        isDraggingQuickScrollThumb = true;
        document.body.style.userSelect = 'none';
        const qNav = document.getElementById('quick-scroll-navigator');
        if (qNav) qNav.classList.add('dragging');
        e.stopPropagation();
    });

    window.addEventListener('mousemove', handleDrag);
    window.addEventListener('mouseup', () => {
        if (isDraggingQuickScrollThumb) {
            isDraggingQuickScrollThumb = false;
            document.body.style.userSelect = '';
            const qNav = document.getElementById('quick-scroll-navigator');
            if (qNav) qNav.classList.remove('dragging');
            if (typeof saveCurrentDocProgress === 'function') {
                saveCurrentDocProgress();
            }
        }
    });

    // Touch support for mobile/tablet
    thumb.addEventListener('touchstart', (e) => {
        isDraggingQuickScrollThumb = true;
        const qNav = document.getElementById('quick-scroll-navigator');
        if (qNav) qNav.classList.add('dragging');
        e.stopPropagation();
    }, { passive: true });
    window.addEventListener('touchmove', handleDrag, { passive: true });
    window.addEventListener('touchend', () => {
        if (isDraggingQuickScrollThumb) {
            isDraggingQuickScrollThumb = false;
            const qNav = document.getElementById('quick-scroll-navigator');
            if (qNav) qNav.classList.remove('dragging');
            if (typeof saveCurrentDocProgress === 'function') {
                saveCurrentDocProgress();
            }
        }
    });
}

function updateQuickScrollWidget() {
    const container = document.getElementById('reading-container');
    if (!container) return;

    const maxScroll = container.scrollHeight - container.clientHeight;
    const ratio = maxScroll > 0 ? Math.min(1, Math.max(0, container.scrollTop / maxScroll)) : 0;
    const pct = Math.round(ratio * 100);

    const fill = document.getElementById('quick-scroll-fill');
    const thumb = document.getElementById('quick-scroll-thumb');
    const bubble = document.getElementById('quick-scroll-bubble');

    if (fill) fill.style.height = pct + '%';
    if (thumb) thumb.style.top = pct + '%';
    if (bubble) bubble.textContent = pct + '%';
}

function quickScrollToTop() {
    const container = document.getElementById('reading-container');
    if (container) {
        flashQuickScrollNavigator();
        container.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function quickScrollToBottom() {
    const container = document.getElementById('reading-container');
    if (container) {
        flashQuickScrollNavigator();
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    }
}

function onQuickScrollTrackClick(e) {
    const track = document.getElementById('quick-scroll-track');
    const container = document.getElementById('reading-container');
    if (!track || !container) return;

    flashQuickScrollNavigator();
    const rect = track.getBoundingClientRect();
    let ratio = (e.clientY - rect.top) / rect.height;
    ratio = Math.max(0, Math.min(1, ratio));

    const maxScroll = container.scrollHeight - container.clientHeight;
    container.scrollTo({ top: ratio * maxScroll, behavior: 'smooth' });
    setTimeout(() => {
        if (typeof saveCurrentDocProgress === 'function') {
            saveCurrentDocProgress();
        }
    }, 300);
}
