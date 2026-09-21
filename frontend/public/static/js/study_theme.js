// ==========================================================
// Theme, Layout & Typography Controls
// ==========================================================
function initTheme() {
            selectTheme(currentTheme, false);
            // Close dropdowns when clicking outside
            document.addEventListener('click', (e) => {
                const menu = document.getElementById('theme-dropdown-menu');
                const btn = document.getElementById('btn-theme-toggle');
                if (menu && menu.style.display !== 'none') {
                    if (!menu.contains(e.target) && !btn.contains(e.target)) {
                        menu.style.display = 'none';
                    }
                }
                const expMenu = document.getElementById('export-dropdown-menu');
                const expBtn = document.getElementById('btn-export-toggle');
                if (expMenu && expMenu.style.display !== 'none') {
                    if (!expMenu.contains(e.target) && !expBtn?.contains(e.target)) {
                        expMenu.style.display = 'none';
                    }
                }
                const fcMenu = document.getElementById('flashcard-dropdown-menu');
                const fcBtn = document.getElementById('btn-flashcard-toggle');
                if (fcMenu && fcMenu.style.display !== 'none') {
                    if (!fcMenu.contains(e.target) && !fcBtn?.contains(e.target)) {
                        fcMenu.style.display = 'none';
                    }
                }
            });
        }

        function toggleThemeMenu(e) {
            if (e) e.stopPropagation();
            const menu = document.getElementById('theme-dropdown-menu');
            if (menu) {
                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
            }
        }

        function selectTheme(themeName, save = true) {
            currentTheme = themeName;
            if (save) localStorage.setItem('study_theme', themeName);

            if (themeName === 'dark') {
                document.body.removeAttribute('data-theme');
            } else {
                document.body.setAttribute('data-theme', themeName);
            }

            const labelEl = document.getElementById('theme-btn-label');
            if (labelEl) {
                labelEl.textContent = `🎨 主题: ${themeLabels[themeName] || themeName}`;
            }

            document.querySelectorAll('.theme-menu-item').forEach(el => {
                if (el.getAttribute('data-theme-val') === themeName) {
                    el.classList.add('active');
                } else {
                    el.classList.remove('active');
                }
            });

            const menu = document.getElementById('theme-dropdown-menu');
            if (menu) menu.style.display = 'none';
        }

        // Boot

function toggleSidebar() {
            const sidebar = document.getElementById('app-sidebar');
            sidebar.classList.toggle('collapsed');
            const isCollapsed = sidebar.classList.contains('collapsed');
            localStorage.setItem('study_sidebar_collapsed', isCollapsed ? 'true' : 'false');
            updateSidebarToggleBtn();
        }

        function updateSidebarToggleBtn() {
            const sidebar = document.getElementById('app-sidebar');
            const btn = document.getElementById('btn-toggle-sidebar');
            if (sidebar && btn) {
                if (sidebar.classList.contains('collapsed')) {
                    btn.innerHTML = '<span>☰ 显示侧栏</span>';
                    btn.style.width = 'auto';
                    btn.style.padding = '0 10px';
                    btn.style.color = '#818cf8';
                    btn.style.borderColor = 'rgba(99, 102, 241, 0.4)';
                    btn.style.background = 'rgba(99, 102, 241, 0.12)';
                    btn.title = "展开侧边栏（当前已隐藏）";
                } else {
                    btn.innerHTML = '☰';
                    btn.style.width = '32px';
                    btn.style.padding = '0';
                    btn.style.color = '';
                    btn.style.borderColor = '';
                    btn.style.background = '';
                    btn.title = "折叠侧边栏";
                }
            }
        }

        // Adjust Font Size
        function adjustFontSize(delta) {
            currentFontSize = Math.min(Math.max(currentFontSize + delta, 13), 26);
            applyFontSize(currentFontSize);
        }

        function applyFontSize(size) {
            document.documentElement.style.setProperty('--font-size-base', size + 'px');
            document.getElementById('font-size-display').textContent = size + 'px';
        }

        // Toggle Width Mode
        function toggleWidthMode() {
            widthModeIndex = (widthModeIndex + 1) % widthModes.length;
            const mode = widthModes[widthModeIndex];
            const displayEl = document.getElementById('width-mode-display');

            if (mode === 'standard') {
                document.documentElement.style.setProperty('--reading-max-width', '900px');
                displayEl.textContent = '标准 (900px)';
            } else if (mode === 'wide') {
                document.documentElement.style.setProperty('--reading-max-width', '1250px');
                displayEl.textContent = '宽屏 (1250px)';
            } else {
                document.documentElement.style.setProperty('--reading-max-width', '96%');
                displayEl.textContent = '全宽 (96%)';
            }
        }

        // Apply and Toggle Bilingual Layout Mode
        function applyLayoutMode(mode) {
            currentLayoutMode = mode;
            localStorage.setItem('study_layout_mode', mode);
            const container = document.getElementById('paragraphs-stream');
            if (container) {
                container.classList.remove('layout-top-bottom', 'layout-side-by-side', 'layout-card');
                container.classList.add(`layout-${mode}`);
            }
            const displayEl = document.getElementById('layout-mode-display');
            if (displayEl) {
                displayEl.textContent = layoutModeLabels[mode] || mode;
            }
            if (activeChapterData && activeChapterData.paragraphs) {
                renderParagraphs(activeChapterData.paragraphs);
            }
        }

        function toggleLayoutMode() {
            const idx = layoutModes.indexOf(currentLayoutMode);
            const nextMode = layoutModes[(idx + 1) % layoutModes.length];
            applyLayoutMode(nextMode);
        }

        // Markdown Rich Text Renderer (Safe against XSS)
