// ==========================================================
// Multi-Notes CRUD & Chapter Summaries
// ==========================================================
function renderParaNotesList(paragraphId, notes) {
            if (!notes || notes.length === 0) return '';
            return notes.map((n, idx) => `
                <div class="para-note-card" id="note-${n.id}">
                    <div class="note-card-header">
                        <div class="note-card-meta">
                            <span>💡 研读注解 #${idx + 1}</span>
                            <span class="note-card-date">${n.created_at ? n.created_at.slice(5, 16) : ''}</span>
                        </div>
                        <div class="note-card-actions">
                            <button class="note-btn" onclick="editParagraphNote('${paragraphId}', '${n.id}')" title="编辑注解">✏️</button>
                            <button class="note-btn danger" onclick="deleteParagraphNote('${paragraphId}', '${n.id}')" title="删除注解">🗑️</button>
                        </div>
                    </div>
                    <div class="note-card-content">${renderMarkdownContent(n.content || '')}</div>
                </div>
            `).join('');
        }

        function renderChapterNotes() {
            if (!activeChapterData) return;

            // 1. Header Notes
            const headerContainer = document.getElementById('chapter-header-notes-container');
            const headerList = document.getElementById('chapter-header-notes-list');
            const headerNotes = activeChapterData.header_notes || [];

            if (headerNotes.length > 0) {
                headerContainer.style.display = 'block';
                headerList.innerHTML = headerNotes.map((n, idx) => `
                    <div class="chapter-note-item" id="header-note-${n.id}">
                        <div class="chapter-note-header">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <strong style="color: var(--accent-primary);">导读 / 核心脉络总结 #${idx + 1}</strong>
                                <span style="color: var(--text-muted); font-size: 11px;">${n.created_at ? n.created_at.slice(5, 16) : ''}</span>
                            </div>
                            <div class="note-card-actions">
                                <button class="note-btn" onclick="editChapterNote('header', '${n.id}')" title="编辑总结">✏️</button>
                                <button class="note-btn danger" onclick="deleteChapterNote('header', '${n.id}')" title="删除总结">🗑️</button>
                            </div>
                        </div>
                        <div class="note-card-content">${renderMarkdownContent(n.content || '')}</div>
                    </div>
                `).join('');
            } else {
                headerContainer.style.display = 'none';
                headerList.innerHTML = '';
            }

            // 2. Footer Notes
            const footerContainer = document.getElementById('chapter-footer-notes-container');
            const footerList = document.getElementById('chapter-footer-notes-list');
            const footerNotes = activeChapterData.footer_notes || [];

            if (footerNotes.length > 0) {
                footerContainer.style.display = 'block';
                footerList.innerHTML = footerNotes.map((n, idx) => `
                    <div class="chapter-note-item" id="footer-note-${n.id}">
                        <div class="chapter-note-header">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <strong style="color: #10b981;">回顾 / 考点总结 #${idx + 1}</strong>
                                <span style="color: var(--text-muted); font-size: 11px;">${n.created_at ? n.created_at.slice(5, 16) : ''}</span>
                            </div>
                            <div class="note-card-actions">
                                <button class="note-btn" onclick="editChapterNote('footer', '${n.id}')" title="编辑总结">✏️</button>
                                <button class="note-btn danger" onclick="deleteChapterNote('footer', '${n.id}')" title="删除总结">🗑️</button>
                            </div>
                        </div>
                        <div class="note-card-content">${renderMarkdownContent(n.content || '')}</div>
                    </div>
                `).join('');
            } else {
                footerContainer.style.display = 'none';
                footerList.innerHTML = '';
            }
        }

        // Note Modal Handlers
        function openNoteModal(context, initialContent = '') {
            activeNoteContext = context;
            const titleEl = document.getElementById('note-modal-title');
            const contentEl = document.getElementById('note-modal-content');
            contentEl.value = initialContent;

            if (context.type === 'paragraph') {
                titleEl.textContent = context.noteId ? '✏️ 编辑段落研读注解' : '📝 新增段落研读注解';
            } else {
                const posLabel = context.position === 'header' ? '章首导读/核心总结' : '章尾回顾/考点总结';
                titleEl.textContent = context.noteId ? `✏️ 编辑${posLabel}` : `📝 新增${posLabel}`;
            }

            const modal = document.getElementById('note-modal');
            const card = modal.querySelector('.modal-card');
            if (card) card.classList.remove('maximized');
            modal.classList.add('open');
            contentEl.focus();
        }

        function closeNoteModal() {
            document.getElementById('note-modal').classList.remove('open');
            activeNoteContext = null;
        }

        async function submitNoteModal() {
            if (!activeNoteContext) return;
            const content = document.getElementById('note-modal-content').value.trim();
            if (!content) {
                alert("请输入笔记内容");
                return;
            }

            const ctx = activeNoteContext;
            const btn = document.getElementById('btn-save-note');
            btn.disabled = true;

            try {
                if (ctx.type === 'paragraph') {
                    if (ctx.noteId) {
                        const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/paragraph/${ctx.paragraphId}/notes/${ctx.noteId}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ content })
                        });
                        const result = await res.json();
                        if (result.code === 200) {
                            const p = activeChapterData.paragraphs.find(item => item.id === ctx.paragraphId);
                            if (p && p.notes) {
                                const n = p.notes.find(item => item.id === ctx.noteId);
                                if (n) n.content = content;
                            }
                            updateParagraphNotesInDOM(ctx.paragraphId);
                            showToast("注解已更新！");
                        }
                    } else {
                        const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/paragraph/${ctx.paragraphId}/notes`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ content })
                        });
                        const result = await res.json();
                        if (result.code === 200) {
                            const p = activeChapterData.paragraphs.find(item => item.id === ctx.paragraphId);
                            if (p) {
                                if (!p.notes) p.notes = [];
                                p.notes.push(result.data);
                            }
                            updateParagraphNotesInDOM(ctx.paragraphId);
                            showToast("注解已保存！");
                        }
                    }
                } else if (ctx.type === 'chapter') {
                    if (ctx.noteId) {
                        const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/notes/${ctx.noteId}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ position: ctx.position, content })
                        });
                        const result = await res.json();
                        if (result.code === 200) {
                            const listKey = ctx.position === 'header' ? 'header_notes' : 'footer_notes';
                            const list = activeChapterData[listKey] || [];
                            const n = list.find(item => item.id === ctx.noteId);
                            if (n) n.content = content;
                            renderChapterNotes();
                            showToast("总结已更新！");
                        }
                    } else {
                        const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/notes`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ position: ctx.position, content })
                        });
                        const result = await res.json();
                        if (result.code === 200) {
                            const listKey = ctx.position === 'header' ? 'header_notes' : 'footer_notes';
                            if (!activeChapterData[listKey]) activeChapterData[listKey] = [];
                            activeChapterData[listKey].push(result.data);
                            renderChapterNotes();
                            showToast("总结已保存！");
                        }
                    }
                }
                closeNoteModal();
            } catch (e) {
                console.error("保存笔记出错", e);
                alert("保存失败，请检查服务连接");
            } finally {
                btn.disabled = false;
            }
        }

        function updateParagraphNotesInDOM(paragraphId) {
            const p = activeChapterData.paragraphs.find(item => item.id === paragraphId);
            if (!p) return;
            const wrap = document.getElementById(`notes-wrap-${paragraphId}`);
            if (wrap) {
                wrap.innerHTML = renderParaNotesList(paragraphId, p.notes || []);
            }
        }

        function promptAddParagraphNote(paragraphId) {
            openNoteModal({ type: 'paragraph', paragraphId, noteId: null }, '');
        }

        function editParagraphNote(paragraphId, noteId) {
            const p = activeChapterData.paragraphs.find(item => item.id === paragraphId);
            const n = (p?.notes || []).find(item => item.id === noteId);
            if (n) {
                openNoteModal({ type: 'paragraph', paragraphId, noteId }, n.content);
            }
        }

        async function deleteParagraphNote(paragraphId, noteId) {
            if (!confirm("确认删除该条段落注解？")) return;
            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/paragraph/${paragraphId}/notes/${noteId}`, {
                    method: 'DELETE'
                });
                const result = await res.json();
                if (result.code === 200) {
                    const p = activeChapterData.paragraphs.find(item => item.id === paragraphId);
                    if (p && p.notes) {
                        p.notes = p.notes.filter(item => item.id !== noteId);
                    }
                    updateParagraphNotesInDOM(paragraphId);
                    showToast("注解已删除");
                }
            } catch (e) {
                console.error("删除注解出错", e);
            }
        }

        function promptAddChapterNote(position) {
            openNoteModal({ type: 'chapter', position, noteId: null }, '');
        }

        function editChapterNote(position, noteId) {
            const listKey = position === 'header' ? 'header_notes' : 'footer_notes';
            const list = activeChapterData[listKey] || [];
            const n = list.find(item => item.id === noteId);
            if (n) {
                openNoteModal({ type: 'chapter', position, noteId }, n.content);
            }
        }

        async function deleteChapterNote(position, noteId) {
            const label = position === 'header' ? '章首总结' : '章尾总结';
            if (!confirm(`确认删除该条${label}？`)) return;
            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/notes/${noteId}?position=${position}`, {
                    method: 'DELETE'
                });
                const result = await res.json();
                if (result.code === 200) {
                    const listKey = position === 'header' ? 'header_notes' : 'footer_notes';
                    if (activeChapterData[listKey]) {
                        activeChapterData[listKey] = activeChapterData[listKey].filter(item => item.id !== noteId);
                    }
                    renderChapterNotes();
                    showToast(`${label}已删除`);
                }
            } catch (e) {
                console.error("删除总结出错", e);
            }
        }

        async function saveBubbleAsParagraphNote(btn, content) {
            if (!activeDocId || !activeChapterId || !activeParagraphForChat) return;
            btn.disabled = true;
            btn.innerHTML = '⏳ 正在保存...';

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/paragraph/${activeParagraphForChat.id}/notes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content })
                });
                const result = await res.json();
                if (result.code === 200) {
                    if (!activeParagraphForChat.notes) activeParagraphForChat.notes = [];
                    activeParagraphForChat.notes.push(result.data);
                    updateParagraphNotesInDOM(activeParagraphForChat.id);
                    btn.innerHTML = '✅ 已存为注解';
                    showToast("已将 AI 回答存为该段研读注解！");
                } else {
                    btn.disabled = false;
                    btn.innerHTML = '📌 存为段落注解';
                    alert("保存失败: " + result.message);
                }
            } catch (e) {
                btn.disabled = false;
                btn.innerHTML = '📌 存为段落注解';
                console.error("保存注解出错", e);
            }
        }

        async function saveBubbleAsChapterNote(btn, position, content) {
            if (!activeDocId || !activeChapterId) return;
            btn.disabled = true;
            btn.innerHTML = '⏳ 正在保存...';

            try {
                const res = await fetch(`/api/study/documents/${activeDocId}/chapter/${activeChapterId}/notes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ position, content })
                });
                const result = await res.json();
                if (result.code === 200) {
                    const listKey = position === 'header' ? 'header_notes' : 'footer_notes';
                    if (!activeChapterData[listKey]) activeChapterData[listKey] = [];
                    activeChapterData[listKey].push(result.data);
                    renderChapterNotes();
                    const label = position === 'header' ? '章首总结' : '章尾总结';
                    btn.innerHTML = `✅ 已存为${label}`;
                    showToast(`已将 AI 回答存为${label}！`);
                } else {
                    btn.disabled = false;
                    btn.innerHTML = position === 'header' ? '📌 存为章首总结' : '📌 存为章尾总结';
                    alert("保存失败: " + result.message);
                }
            } catch (e) {
                btn.disabled = false;
                btn.innerHTML = position === 'header' ? '📌 存为章首总结' : '📌 存为章尾总结';
                console.error("保存总结出错", e);
            }
        }

        // Initialize Resizable Right Sidebar
