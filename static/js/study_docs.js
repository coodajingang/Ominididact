// ==========================================================
// Document Lifecycle, TOC & Export
// ==========================================================
function switchSidebarTab(tab) {
            const docsBtn = document.getElementById('tab-docs-btn');
            const tocBtn = document.getElementById('tab-toc-btn');
            const docsContainer = document.getElementById('docs-list-container');
            const tocContainer = document.getElementById('toc-list-container');

            if (tab === 'docs') {
                docsBtn.classList.add('active');
                tocBtn.classList.remove('active');
                docsContainer.style.display = 'flex';
                tocContainer.style.display = 'none';
            } else {
                tocBtn.classList.add('active');
                docsBtn.classList.remove('active');
                docsContainer.style.display = 'none';
                tocContainer.style.display = 'flex';
            }
        }

        // Fetch & Render Documents List
        async function loadDocumentsList() {
            try {
                const res = await fetch('/api/study/documents');
                const result = await res.json();
                const docs = result.data || [];
                renderDocumentsList(docs);

                if (!activeDocId && docs.length > 0) {
                    selectDocument(docs[0].doc_id);
                }
            } catch (e) {
                console.error("加载文档列表失败", e);
            }
        }

        let docProgressPollingTimer = null;

        function startDocProgressPolling(docId) {
            if (docProgressPollingTimer) clearInterval(docProgressPollingTimer);
            docProgressPollingTimer = setInterval(async () => {
                try {
                    const res = await fetch(`/api/study/documents/${docId}`);
                    if (!res.ok) return;
                    const result = await res.json();
                    const meta = result.data;
                    if (!meta) return;

                    activeDocMeta = meta;
                    const currPage = (meta.progress && meta.progress.current_page) || 0;
                    const totalPages = (meta.progress && meta.progress.total_pages) || (meta.total_pages || 1);
                    const percent = (meta.progress && meta.progress.percent) || 0;

                    const barEl = document.getElementById('extracting-bar-fill');
                    if (barEl) barEl.style.width = percent + '%';
                    const pageEl = document.getElementById('extracting-page-info');
                    if (pageEl) pageEl.textContent = `正在提取: 第 ${currPage} / ${totalPages} 页`;
                    const pctEl = document.getElementById('extracting-percent-info');
                    if (pctEl) pctEl.textContent = `${percent}%`;

                    // Also refresh doc card progress in the sidebar
                    const cardBadge = document.querySelector(`.doc-card.active .badge`);
                    if (cardBadge && meta.status === 'extracting') {
                        cardBadge.textContent = `⚡ 解析中 ${percent}%`;
                    }

                    if (meta.status === 'completed') {
                        stopDocProgressPolling();
                        await loadDocumentsList();
                        selectDocument(docId);
                        showToast("🎉 文档已成功解析并提取章节，开始研读！");
                    } else if (meta.status === 'error') {
                        stopDocProgressPolling();
                        alert("文档解析失败: " + (meta.error_message || "未知错误"));
                        await loadDocumentsList();
                        selectDocument(docId);
                    }
                } catch (err) {
                    console.error("Progress polling error", err);
                }
            }, 1500);
        }

        function stopDocProgressPolling() {
            if (docProgressPollingTimer) {
                clearInterval(docProgressPollingTimer);
                docProgressPollingTimer = null;
            }
        }

        // ==========================================================
        // Reading Progress Storage & Synchronization
        // ==========================================================
        const DOC_PROGRESS_KEY_PREFIX = 'study_doc_progress_';

        function getDocReadingProgress(docId) {
            if (!docId) return null;
            try {
                const raw = localStorage.getItem(DOC_PROGRESS_KEY_PREFIX + docId);
                return raw ? JSON.parse(raw) : null;
            } catch (e) {
                return null;
            }
        }

        function saveDocReadingProgress(docId, chapterId, scrollTop, scrollRatio) {
            if (!docId) return;
            try {
                const data = {
                    docId,
                    chapterId: chapterId || null,
                    scrollTop: Math.max(0, Math.round(scrollTop || 0)),
                    scrollRatio: Math.min(100, Math.max(0, Math.round(scrollRatio || 0))),
                    updatedAt: Date.now()
                };
                localStorage.setItem(DOC_PROGRESS_KEY_PREFIX + docId, JSON.stringify(data));
                updateDocCardProgressInSidebar(docId, data.scrollRatio);
            } catch (e) {
                console.warn("Failed to save doc reading progress", e);
            }
        }

        function saveCurrentDocProgress() {
            if (!activeDocId) return;
            const container = document.getElementById('reading-container');
            if (!container) return;
            const maxScroll = container.scrollHeight - container.clientHeight;
            const ratio = maxScroll > 0 ? (container.scrollTop / maxScroll) * 100 : 0;
            saveDocReadingProgress(activeDocId, activeChapterId, container.scrollTop, ratio);
        }

        function updateDocCardProgressInSidebar(docId, ratio) {
            const card = document.querySelector(`.doc-card[data-doc-id="${docId}"]`);
            if (!card) return;
            const fill = card.querySelector('.doc-card-progress-fill');
            if (fill) fill.style.width = ratio + '%';
            const badge = card.querySelector('.doc-card-meta .badge');
            if (badge && !badge.classList.contains('badge-extracting')) {
                if (ratio >= 98) {
                    badge.className = 'badge badge-read-done';
                    badge.textContent = '✅ 已读完';
                } else if (ratio > 0) {
                    badge.className = 'badge badge-reading';
                    badge.textContent = `📖 进度 ${ratio}%`;
                }
            }
        }

        window.addEventListener('beforeunload', saveCurrentDocProgress);

        function renderDocumentsList(docs) {
            const container = document.getElementById('docs-list-container');
            if (!docs || docs.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px 10px; color: var(--text-muted); font-size: 13px;">
                        暂无文档<br>点击上方按钮上传 PDF / Word / TXT / Markdown
                    </div>
                `;
                return;
            }

            container.innerHTML = docs.map(doc => {
                const isActive = doc.doc_id === activeDocId;
                let badgeClass = 'badge-completed';
                let badgeText = doc.language === 'zh' ? '中文材料' : '已就绪';

                const prog = getDocReadingProgress(doc.doc_id);
                const ratio = (prog && prog.scrollRatio !== undefined) ? prog.scrollRatio : 0;

                if (doc.status === 'extracting' || doc.status === 'uploaded') {
                    badgeClass = 'badge-extracting';
                    const pct = (doc.progress && doc.progress.percent !== undefined) ? doc.progress.percent : 0;
                    badgeText = `⚡ 解析中 ${pct}%`;
                } else if (doc.status === 'error') {
                    badgeClass = 'badge-zh';
                    badgeText = '解析失败';
                } else if (ratio >= 98) {
                    badgeClass = 'badge-read-done';
                    badgeText = '✅ 已读完';
                } else if (ratio > 0) {
                    badgeClass = 'badge-reading';
                    badgeText = `📖 进度 ${ratio}%`;
                } else {
                    badgeClass = 'badge-unread';
                    badgeText = '未读';
                }

                const extIcon = doc.file_type === 'docx' ? '📝' : '📄';

                return `
                    <div class="doc-card ${isActive ? 'active' : ''}" data-doc-id="${doc.doc_id}" onclick="selectDocument('${doc.doc_id}')">
                        <div class="doc-card-title-row">
                            <div class="doc-card-title" title="${escapeHtml(doc.filename)}">
                                <span>${extIcon}</span>
                                <span>${escapeHtml(doc.filename)}</span>
                            </div>
                            <button type="button" class="doc-delete-btn" onclick="confirmDeleteDocument(event, '${doc.doc_id}', '${encodeURIComponent(doc.filename)}')" title="物理删除文档及对应卡片">🗑️</button>
                        </div>
                        <div class="doc-card-meta">
                            <span>${doc.total_pages || 1} 页 · ${doc.chapters ? doc.chapters.length : 1} 章</span>
                            <span class="badge ${badgeClass}">${badgeText}</span>
                        </div>
                        <div class="doc-card-progress-track">
                            <div class="doc-card-progress-fill" style="width: ${ratio}%;"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // ==========================================================
        // Document Physical Deletion Handlers
        // ==========================================================
        let pendingDeleteDocId = null;

        function confirmDeleteDocument(e, docId, encodedFilename) {
            if (e) {
                e.stopPropagation();
                e.preventDefault();
            }
            pendingDeleteDocId = docId;
            const filename = decodeURIComponent(encodedFilename || '');
            const nameEl = document.getElementById('delete-doc-name');
            if (nameEl) nameEl.textContent = `《${filename}》`;
            const modal = document.getElementById('delete-doc-modal');
            if (modal) modal.classList.add('open');
        }

        function closeDeleteDocModal() {
            pendingDeleteDocId = null;
            const modal = document.getElementById('delete-doc-modal');
            if (modal) modal.classList.remove('open');
        }

        async function executeDeleteDocument() {
            if (!pendingDeleteDocId) return;
            const docId = pendingDeleteDocId;
            const btn = document.getElementById('btn-confirm-delete-doc');
            if (btn) {
                btn.disabled = true;
                btn.textContent = '正在删除...';
            }

            try {
                const res = await fetch(`/api/study/documents/${docId}`, {
                    method: 'DELETE'
                });
                const result = await res.json();
                if (res.ok) {
                    showToast("文档及关联闪卡已成功物理删除！");
                    closeDeleteDocModal();

                    // Remove saved progress for this doc
                    try {
                        localStorage.removeItem(DOC_PROGRESS_KEY_PREFIX + docId);
                    } catch (e) {}

                    // If deleted doc was currently active
                    if (activeDocId === docId) {
                        activeDocId = null;
                        activeDocMeta = null;
                        activeChapterId = null;
                        activeChapterData = null;

                        document.getElementById('empty-state').style.display = 'block';
                        document.getElementById('reading-content').style.display = 'none';
                        const qNav = document.getElementById('quick-scroll-navigator');
                        if (qNav) qNav.style.display = 'none';

                        const headerTitle = document.getElementById('header-doc-title');
                        if (headerTitle) headerTitle.textContent = '未选择文件';
                        const headerMeta = document.getElementById('header-doc-meta');
                        if (headerMeta) headerMeta.textContent = '';

                        const tocContainer = document.getElementById('toc-list-container');
                        if (tocContainer) {
                            tocContainer.innerHTML = `
                                <div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px;">请先选择文档</div>
                            `;
                        }
                    }

                    // Reload documents list
                    await loadDocumentsList();
                } else {
                    alert("删除文档失败: " + (result.detail || result.message || "未知错误"));
                }
            } catch (err) {
                console.error("Delete document error", err);
                alert("删除文档网络请求失败");
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '🗑️ 确认永久删除';
                }
            }
        }

        // Select Document
        async function selectDocument(docId) {
            // Save current doc progress before switching away
            if (activeDocId && activeDocId !== docId) {
                saveCurrentDocProgress();
            }
            activeDocId = docId;
            loadDocumentsList();
            try {
                const res = await fetch(`/api/study/documents/${docId}`);
                const result = await res.json();
                activeDocMeta = result.data;
                updateHeaderInfo();
                updateTopFlashcardBadge();
                renderChapterToc(activeDocMeta.chapters || []);
                if (typeof syncChatActiveModelSelector === 'function') {
                    syncChatActiveModelSelector();
                }

                if (activeDocMeta.status === 'extracting' || activeDocMeta.status === 'uploaded') {
                    document.getElementById('empty-state').style.display = 'none';
                    document.getElementById('reading-content').style.display = 'none';
                    const qNav = document.getElementById('quick-scroll-navigator');
                    if (qNav) qNav.style.display = 'none';
                    document.getElementById('extracting-state').style.display = 'flex';

                    const currPage = (activeDocMeta.progress && activeDocMeta.progress.current_page) || 0;
                    const totalPages = (activeDocMeta.progress && activeDocMeta.progress.total_pages) || (activeDocMeta.total_pages || 1);
                    const percent = (activeDocMeta.progress && activeDocMeta.progress.percent) || 0;

                    document.getElementById('extracting-bar-fill').style.width = percent + '%';
                    document.getElementById('extracting-page-info').textContent = `正在提取: 第 ${currPage} / ${totalPages} 页`;
                    document.getElementById('extracting-percent-info').textContent = `${percent}%`;

                    startDocProgressPolling(docId);
                    return;
                } else {
                    stopDocProgressPolling();
                    document.getElementById('extracting-state').style.display = 'none';
                }

                if (activeDocMeta.chapters && activeDocMeta.chapters.length > 0) {
                    document.getElementById('empty-state').style.display = 'none';
                    // Check saved progress for this doc
                    const prog = getDocReadingProgress(docId);
                    let targetChId = activeDocMeta.chapters[0].chapter_id;
                    let targetScrollTop = 0;
                    if (prog && prog.chapterId && activeDocMeta.chapters.some(c => c.chapter_id === prog.chapterId)) {
                        targetChId = prog.chapterId;
                        targetScrollTop = prog.scrollTop || 0;
                    }
                    selectChapter(targetChId, targetScrollTop);
                    loadSettings();
                } else {
                    document.getElementById('empty-state').style.display = 'block';
                    document.getElementById('reading-content').style.display = 'none';
                    const qNav = document.getElementById('quick-scroll-navigator');
                    if (qNav) qNav.style.display = 'none';
                }
            } catch (e) {
                console.error("加载文档详情失败", e);
            }
        }

        function updateHeaderInfo() {
            if (!activeDocMeta) return;

            document.getElementById('active-doc-title').textContent = activeDocMeta.filename;
            const badge = document.getElementById('active-doc-badge');
            badge.style.display = 'inline-block';
            
            if (activeDocMeta.language === 'zh') {
                badge.className = 'badge badge-zh';
                badge.textContent = '中文材料 (免翻译)';
            } else {
                badge.className = 'badge badge-completed';
                badge.textContent = '双语研学模式';
            }

            const exportContainer = document.getElementById('export-dropdown-container');
            if (exportContainer) exportContainer.style.display = 'inline-flex';
        }

        // Render Chapter TOC
        function renderChapterToc(chapters) {
            const container = document.getElementById('toc-list-container');
            if (!chapters || chapters.length === 0) {
                container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px;">暂无章节目录</div>`;
                return;
            }

            container.innerHTML = chapters.map(ch => {
                const isActive = ch.chapter_id === activeChapterId;
                return `
                    <div class="chapter-nav-item ${isActive ? 'active' : ''}" onclick="selectChapter('${ch.chapter_id}')">
                        <span class="chapter-nav-title" title="${escapeHtml(ch.title)}">${escapeHtml(ch.title)}</span>
                        <span class="chapter-nav-count">${ch.paragraph_count} 项</span>
                    </div>
                `;
            }).join('');
        }

        // Select & Load Chapter
        async function selectChapter(chapterId, targetScrollTop = null) {
            stopChapterTranslatePolling();
            // Save progress of old chapter before changing
            if (activeChapterId && activeChapterId !== chapterId) {
                saveCurrentDocProgress();
            }
            activeChapterId = chapterId;
            if (activeDocMeta && activeDocMeta.chapters) {
                renderChapterToc(activeDocMeta.chapters);
            }

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${chapterId}`);
                const result = await res.json();
                activeChapterData = result.data.chapter;

                document.getElementById('empty-state').style.display = 'none';
                document.getElementById('reading-content').style.display = 'block';
                const qNav = document.getElementById('quick-scroll-navigator');
                if (qNav) qNav.style.display = 'flex';
                document.getElementById('active-chapter-title').textContent = activeChapterData.title || '章节正文';

                renderChapterNotes();
                checkAndUpdateChapterTranslateBtn(activeChapterId);

                renderParagraphs(activeChapterData.paragraphs || []);

                // Determine target scroll position
                let scrollPos = 0;
                if (targetScrollTop !== null && targetScrollTop !== undefined) {
                    scrollPos = targetScrollTop;
                } else {
                    const prog = getDocReadingProgress(activeDocId);
                    if (prog && prog.chapterId === chapterId) {
                        scrollPos = prog.scrollTop || 0;
                    }
                }

                const container = document.getElementById('reading-container');
                if (container) {
                    // Slight delay to let paragraphs render and DOM layout settle
                    setTimeout(() => {
                        container.scrollTop = scrollPos;
                        if (typeof updateQuickScrollWidget === 'function') {
                            updateQuickScrollWidget();
                        }
                    }, 50);
                }
            } catch (e) {
                console.error("加载章节失败", e);
            }
        }

        // Render Paragraphs

async function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/study/documents/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await res.json();
                if (result.code === 200) {
                    await loadDocumentsList();
                    selectDocument(result.data.doc_id);
                } else {
                    alert("上传失败: " + result.message);
                }
            } catch (e) {
                console.error("上传错误", e);
                alert("上传处理失败，请检查网络或服务状态");
            } finally {
                event.target.value = '';
            }
        }

        // Copy Paragraph Markdown

function toggleExportMenu(e) {
            if (e) e.stopPropagation();
            const menu = document.getElementById('export-dropdown-menu');
            if (menu) {
                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
            }
        }

        function exportDocument(format) {
            const menu = document.getElementById('export-dropdown-menu');
            if (menu) menu.style.display = 'none';
            if (!activeDocId) {
                alert("请先选择或上传文档材料！");
                return;
            }
            const formatNames = {
                'html': '双语电子书 (.html)',
                'flashcards_html': '离线闪卡系统 (.html)',
                'site_zip': '静态站点发布包 (.zip)',
                'markdown_zip': 'Markdown 资产包 (.zip)',
                'markdown': '单文件 Markdown (.md)'
            };
            const formatName = formatNames[format] || format;
            showToast(`正在导出 ${formatName}...`);
            window.open(`/api/study/documents/${activeDocId}/export?format=${format}`, '_blank');
        }

        // Context Expansion State (Default N=2, M=2)
        let chatPrevCount = 2;
        let chatNextCount = 2;
