// ==========================================================
// Application Entry Point & Initialization
// ==========================================================
document.addEventListener('DOMContentLoaded', () => {
            initTheme();
            loadDocumentsList();
            loadSettings();
            initDrawerResize();
            if (typeof syncChatActiveModelSelector === 'function') {
                syncChatActiveModelSelector();
            }
            if (typeof initQuickScrollNavigator === 'function') {
                initQuickScrollNavigator();
            }
            applyFontSize(currentFontSize);
            applyLayoutMode(currentLayoutMode);
            if (localStorage.getItem('study_sidebar_collapsed') === 'true') {
                const sb = document.getElementById('app-sidebar');
                if (sb) sb.classList.add('collapsed');
                updateSidebarToggleBtn();
            }
        });

        // Toggle Sidebar & Persist
