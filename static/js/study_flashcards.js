// ==========================================================
// Flashcards Toolbar, Dropdown & Paragraph Quick Card
// ==========================================================
async function updateTopFlashcardBadge() {
            if (!activeDocId) return;
            try {
                const resp = await fetch(`/api/study/documents/${activeDocId}/flashcards`);
                if (resp.ok) {
                    const res = await resp.json();
                    const total = res.data.total || 0;
                    const badge = document.getElementById('top-flashcard-count');
                    if (badge) badge.textContent = total;
                }
            } catch (e) {}
        }

        function toggleFlashcardMenu(e) {
            if (e) e.stopPropagation();
            const menu = document.getElementById('flashcard-dropdown-menu');
            if (menu) {
                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
            }
        }

        function openFlashcardManagementPage() {
            if (!activeDocId) {
                alert("请先选择或上传研学文档！");
                return;
            }
            window.open(`/study/flashcards?doc_id=${encodeURIComponent(activeDocId)}&mode=manage`, '_blank');
        }

        function startFlashcardStudyFromStudy() {
            if (!activeDocId) {
                alert("请先选择或上传研学文档！");
                return;
            }
            window.open(`/study/flashcards?doc_id=${encodeURIComponent(activeDocId)}&mode=study`, '_blank');
        }

        function startFlashcardErrorDrillFromStudy() {
            if (!activeDocId) {
                alert("请先选择或上传研学文档！");
                return;
            }
            window.open(`/study/flashcards?doc_id=${encodeURIComponent(activeDocId)}&mode=errors`, '_blank');
        }

        function openCreateFlashcardFromParagraph(paragraphId) {
            if (!activeChapterData) return;
            const p = (activeChapterData.paragraphs || []).find(item => item.id === paragraphId);
            if (!p) return;

            quickFlashcardParagraphId = paragraphId;
            selectQuickFlashcardType('qa');

            // Check if user selected text in browser window
            const selectedText = window.getSelection() ? window.getSelection().toString().trim() : '';
            if (selectedText) {
                document.getElementById('qfc-input-front').value = selectedText;
                document.getElementById('qfc-input-back').value = p.chinese ? p.chinese.trim() : '';
            } else {
                document.getElementById('qfc-input-front').value = p.english ? p.english.trim() : '';
                document.getElementById('qfc-input-back').value = p.chinese ? p.chinese.trim() : '';
            }
            document.getElementById('qfc-input-tags').value = '核心考点';
            const modal = document.getElementById('quick-flashcard-modal');
            const card = modal.querySelector('.modal-card');
            if (card) card.classList.remove('maximized');
            modal.classList.add('open');
            document.getElementById('qfc-input-front').focus();
        }

        function closeQuickFlashcardModal() {
            document.getElementById('quick-flashcard-modal').classList.remove('open');
            quickFlashcardParagraphId = null;
        }

        function selectQuickFlashcardType(type) {
            quickFlashcardType = type;
            const btnQa = document.getElementById('qfc-type-btn-qa');
            const btnCloze = document.getElementById('qfc-type-btn-cloze');
            const helper = document.getElementById('qfc-cloze-helper');
            const label = document.getElementById('qfc-label-front');

            if (type === 'cloze') {
                btnCloze.className = 'btn btn-primary';
                btnQa.className = 'btn btn-secondary';
                helper.style.display = 'flex';
                label.textContent = '正面挖空语句 (使用 {{挖空词}} 标记填空)';
            } else {
                btnQa.className = 'btn btn-primary';
                btnCloze.className = 'btn btn-secondary';
                helper.style.display = 'none';
                label.textContent = '正面内容 (题目 / 考点问题)';
            }
        }

        function wrapQuickFlashcardSelection() {
            const textarea = document.getElementById('qfc-input-front');
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            const text = textarea.value;
            if (start === end) {
                alert("请先在上方输入框中选中需要设为填空的词句！");
                return;
            }
            const selected = text.substring(start, end);
            const wrapped = `{{${selected}}}`;
            textarea.value = text.substring(0, start) + wrapped + text.substring(end);
            textarea.focus();
            textarea.setSelectionRange(start, start + wrapped.length);
        }

        async function submitQuickFlashcard() {
            const front = document.getElementById('qfc-input-front').value.trim();
            const back = document.getElementById('qfc-input-back').value.trim();
            const tags = document.getElementById('qfc-input-tags').value.replace(/，/g, ',').split(',').map(t => t.trim()).filter(Boolean);

            if (!front) {
                alert("正面内容不能为空！");
                return;
            }
            if (!activeDocId) {
                alert("未选定有效文档！");
                return;
            }

            const payload = {
                type: quickFlashcardType,
                front: front,
                back: back,
                chapter_id: activeChapterId || '',
                paragraph_id: quickFlashcardParagraphId || '',
                tags: tags
            };

            try {
                const resp = await fetch(`/api/study/documents/${activeDocId}/flashcards`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (resp.ok) {
                    showToast("🎉 闪卡制作成功，已存入卡片组！");
                    closeQuickFlashcardModal();
                    updateTopFlashcardBadge();
                } else {
                    const err = await resp.json();
                    alert(`保存失败: ${err.detail || '未知错误'}`);
                }
            } catch (err) {
                console.error("保存闪卡异常", err);
                alert("保存操作失败");
            }
        }


        // Switch Sidebar Tabs
