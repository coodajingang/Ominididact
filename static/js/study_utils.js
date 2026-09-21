// ==========================================================
// General Utilities & Markdown Renderer
// ==========================================================
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function copyText(text) {
            navigator.clipboard.writeText(text).then(() => {
                showToast("已复制到剪贴板！");
            });
        }

        function showToast(msg) {
            const toast = document.createElement('div');
            toast.textContent = msg;
            toast.style.position = 'fixed';
            toast.style.bottom = '25px';
            toast.style.left = '50%';
            toast.style.transform = 'translateX(-50%)';
            toast.style.background = 'rgba(16, 185, 129, 0.9)';
            toast.style.color = '#fff';
            toast.style.padding = '8px 16px';
            toast.style.borderRadius = '8px';
            toast.style.fontSize = '12px';
            toast.style.fontWeight = '600';
            toast.style.zIndex = '9999';
            toast.style.boxShadow = '0 4px 15px rgba(0,0,0,0.3)';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2200);
        }

        // Export Operations (Markdown & HTML)

function wrapMarkdownTables(html) {
    if (!html) return '';
    return html
        .replace(/<table(\s*[^>]*)>/gi, '<div class="md-table-wrapper"><table class="md-table"$1>')
        .replace(/<\/table>/gi, '</table></div>');
}

function parseMarkdownTablesFallback(text) {
    const tableRegex = /((?:^[ \t]*\|.+?\|[ \t]*(?:\r?\n|$))+)/gm;
    return text.replace(tableRegex, (block) => {
        const lines = block.trim().split(/\r?\n/).map(l => l.trim()).filter(Boolean);
        if (lines.length < 2) return block;
        const sepLine = lines[1];
        if (!/^[|:\-\s]+$/.test(sepLine) || !sepLine.includes('-')) {
            return block;
        }
        const parseRow = (line) => {
            let cells = line.split('|');
            if (cells.length > 0 && cells[0].trim() === '') cells.shift();
            if (cells.length > 0 && cells[cells.length - 1].trim() === '') cells.pop();
            return cells.map(c => c.trim());
        };
        const headers = parseRow(lines[0]);
        let html = '<div class="md-table-wrapper"><table class="md-table"><thead><tr>';
        headers.forEach(h => {
            html += `<th>${escapeHtml(h)}</th>`;
        });
        html += '</tr></thead><tbody>';
        for (let i = 2; i < lines.length; i++) {
            const rowCells = parseRow(lines[i]);
            html += '<tr>';
            for (let j = 0; j < headers.length; j++) {
                html += `<td>${escapeHtml(rowCells[j] !== undefined ? rowCells[j] : '')}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>\n';
        return html;
    });
}

function renderMarkdownContent(text) {
    if (!text) return '';

    // 1. High-fidelity parsing with marked if loaded
    if (typeof marked !== 'undefined' && marked.parse) {
        try {
            if (marked.setOptions) {
                marked.setOptions({
                    gfm: true,
                    breaks: true
                });
            }
            let parsed = marked.parse(text);
            return wrapMarkdownTables(parsed);
        } catch (e) {
            console.warn('marked.parse error, falling back to regex renderer:', e);
        }
    }

    // 2. Fallback: Parse markdown tables first, then escape and apply basic typography
    let content = parseMarkdownTablesFallback(text);
    let safe = escapeHtml(content);

    // Unescape generated table tags
    safe = safe.replace(/&lt;(\/?(div|table|thead|tbody|tr|th|td)[^&gt;]*)&gt;/gi, '<$1>');

    // Markdown Headings
    safe = safe.replace(/^###\s+(.+)$/gm, '<h4 class="para-subheading">$1</h4>');
    safe = safe.replace(/^##\s+(.+)$/gm, '<h3 class="para-heading">$1</h3>');
    safe = safe.replace(/^#\s+(.+)$/gm, '<h2 class="para-main-title">$1</h2>');

    // Bold + Italic (***text***)
    safe = safe.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
    // Bold (**text**)
    safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic (*text*)
    safe = safe.replace(/\*([^\*]+?)\*/g, '<em>$1</em>');
    // Inline Code (`code`)
    safe = safe.replace(/`([^`]+?)`/g, '<code class="inline-code">$1</code>');

    // Paragraph breaks and line breaks
    safe = safe.replace(/\n\n+/g, '</p><p class="para-sub-p">');
    safe = safe.replace(/\n/g, '<br>');
    return safe;
}

// Chat Markdown & Interactive Flashcard Widget Renderer
function renderSimpleMarkdown(text) {
    return renderMarkdownContent(text);
}

// ==========================================================
// Clear-View Draggable Floating Modals & Selection Grabbers
// ==========================================================

let lastDocumentSelection = '';
document.addEventListener('selectionchange', () => {
    const sel = window.getSelection() ? window.getSelection().toString().trim() : '';
    const active = document.activeElement;
    // Keep track of document selection when user selects outside modal input textareas
    if (sel && (!active || !active.closest('.modal-card'))) {
        lastDocumentSelection = sel;
    }
});

function getBestAvailableDocumentSelection() {
    const current = window.getSelection() ? window.getSelection().toString().trim() : '';
    return current || lastDocumentSelection || '';
}

function makeModalDraggable(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    const card = modal.querySelector('.modal-card');
    const handle = modal.querySelector('.modal-drag-handle');
    if (!card || !handle) return;

    let isDragging = false;
    let startX = 0, startY = 0;
    let initialLeft = 0, initialTop = 0;

    handle.addEventListener('mousedown', (e) => {
        // Prevent drag initiation when clicking buttons, inputs, links, or close icon
        if (e.target.closest('button, input, textarea, a, select')) return;
        if (card.classList.contains('maximized')) return;

        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;

        const rect = card.getBoundingClientRect();
        initialLeft = rect.left;
        initialTop = rect.top;

        card.style.position = 'fixed';
        card.style.left = `${initialLeft}px`;
        card.style.top = `${initialTop}px`;
        card.style.margin = '0';
        card.style.transform = 'none';

        document.body.style.userSelect = 'none';

        const onMouseMove = (moveEvent) => {
            if (!isDragging) return;
            const dx = moveEvent.clientX - startX;
            const dy = moveEvent.clientY - startY;

            let newLeft = initialLeft + dx;
            let newTop = initialTop + dy;

            const maxLeft = Math.max(10, window.innerWidth - card.offsetWidth - 10);
            const maxTop = Math.max(10, window.innerHeight - card.offsetHeight - 10);
            newLeft = Math.min(Math.max(10, newLeft), maxLeft);
            newTop = Math.min(Math.max(10, newTop), maxTop);

            card.style.left = `${newLeft}px`;
            card.style.top = `${newTop}px`;
        };

        const onMouseUp = () => {
            isDragging = false;
            document.body.style.userSelect = '';
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    });
}

function toggleModalMaximize(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    const card = modal.querySelector('.modal-card');
    if (!card) return;

    if (card.classList.contains('maximized')) {
        card.classList.remove('maximized');
        if (card._prevPosition) {
            card.style.left = card._prevPosition.left;
            card.style.top = card._prevPosition.top;
            card.style.width = card._prevPosition.width;
            card.style.height = card._prevPosition.height;
            card.style.position = card._prevPosition.position || 'relative';
        } else {
            card.style.left = '';
            card.style.top = '';
            card.style.width = '';
            card.style.height = '';
            card.style.position = '';
        }
    } else {
        card._prevPosition = {
            left: card.style.left,
            top: card.style.top,
            width: card.style.width,
            height: card.style.height,
            position: card.style.position
        };
        card.classList.add('maximized');
    }
}

function insertSelectedTextIntoNote() {
    const selection = getBestAvailableDocumentSelection();
    if (!selection) {
        showToast("请先在网页正文中用鼠标划选文字！");
        return;
    }
    const textarea = document.getElementById('note-modal-content');
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const val = textarea.value;

    if (start !== undefined && end !== undefined && start !== end) {
        textarea.value = val.substring(0, start) + selection + val.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + selection.length;
    } else if (start !== undefined && start > 0) {
        textarea.value = val.substring(0, start) + "\n\n" + selection + "\n" + val.substring(start);
        textarea.selectionStart = textarea.selectionEnd = start + selection.length + 3;
    } else {
        textarea.value = (val ? val + "\n\n" : "") + selection;
    }
    textarea.focus();
    showToast("已抓取正文划选文字入笔记！");
}

function insertSelectedTextIntoQuickFc(field) {
    const selection = getBestAvailableDocumentSelection();
    if (!selection) {
        showToast("请先在网页正文中用鼠标划选文字！");
        return;
    }
    const textareaId = field === 'back' ? 'qfc-input-back' : 'qfc-input-front';
    const textarea = document.getElementById(textareaId);
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const val = textarea.value;

    if (start !== undefined && end !== undefined && start !== end) {
        textarea.value = val.substring(0, start) + selection + val.substring(end);
    } else if (start !== undefined && start > 0) {
        textarea.value = val.substring(0, start) + "\n" + selection + val.substring(start);
    } else {
        textarea.value = (val ? val + "\n" : "") + selection;
    }
    textarea.focus();
    showToast(field === 'back' ? "已填入反面核心解析！" : "已填入正面考点题目！");
}

// Initialize floating draggable modals and global Esc shortcut
document.addEventListener('DOMContentLoaded', () => {
    makeModalDraggable('note-modal');
    makeModalDraggable('quick-flashcard-modal');
});

window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const noteModal = document.getElementById('note-modal');
        if (noteModal && noteModal.classList.contains('open')) {
            if (typeof closeNoteModal === 'function') closeNoteModal();
            return;
        }
        const qfcModal = document.getElementById('quick-flashcard-modal');
        if (qfcModal && qfcModal.classList.contains('open')) {
            if (typeof closeQuickFlashcardModal === 'function') closeQuickFlashcardModal();
            return;
        }
        const delModal = document.getElementById('delete-doc-modal');
        if (delModal && delModal.classList.contains('open')) {
            if (typeof closeDeleteDocModal === 'function') closeDeleteDocModal();
            return;
        }
        const setModal = document.getElementById('settings-modal');
        if (setModal && setModal.classList.contains('open')) {
            if (typeof closeSettingsModal === 'function') closeSettingsModal();
            return;
        }
    }
});

