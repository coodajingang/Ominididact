// ==========================================================
// Multi-Provider, Dynamic Searchable Models & System Settings
// ==========================================================

let availableProvidersList = [];
const providerModelsCache = {};

// Combobox Controller instances
let gTransCombobox = null;
let gChatCombobox = null;
let gVlmCombobox = null;

let docTransCombobox = null;
let docChatCombobox = null;
let docVlmCombobox = null;

// Global cache of latest loaded config
let globalProvidersConfig = {};
let globalDefaultModels = {};

/**
 * Fetches registered providers from backend
 */
async function checkAvailableProviders() {
    try {
        const resp = await fetch('/api/study/providers');
        if (resp.ok) {
            const res = await resp.json();
            availableProvidersList = res.data || [];
            
            // Check for custom gateway plugin
            const hasCustom = availableProvidersList.some(p => p.id === 'custom_gateway');
            const customTabBtn = document.getElementById('ptab-btn-custom');
            if (customTabBtn) {
                customTabBtn.style.display = hasCustom ? 'inline-block' : 'none';
            }
        }
    } catch (e) {
        console.warn("获取 Providers 列表失败:", e);
    }
}

/**
 * Fetches available models for a specific provider with caching
 */
async function fetchProviderModels(providerId, forceRefresh = false) {
    if (!providerId) return [];
    if (!forceRefresh && providerModelsCache[providerId] && providerModelsCache[providerId].length > 0) {
        return providerModelsCache[providerId];
    }
    try {
        const res = await fetch('/api/study/providers/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: providerId })
        });
        if (res.ok) {
            const data = await res.json();
            const models = data.data || [];
            if (models.length > 0) {
                providerModelsCache[providerId] = models;
            }
            return models;
        }
    } catch (e) {
        console.warn(`拉取 Provider [${providerId}] 模型列表失败:`, e);
    }
    return providerModelsCache[providerId] || [];
}

/**
 * Searchable Combobox Component
 * Provides an input field with dropdown search & select capabilities
 */
function createSearchableCombobox({ containerId, inputId, placeholder, getProviderId, onSelect, initialValue = '' }) {
    const container = document.getElementById(containerId);
    if (!container) return null;

    // Clean up any existing dropdown attached to body
    const existingDropdown = document.getElementById(`${inputId}-dropdown`);
    if (existingDropdown) {
        existingDropdown.remove();
    }

    container.innerHTML = `
        <div class="searchable-combobox" id="${inputId}-combobox">
            <div class="combobox-input-wrap">
                <input type="text" class="combobox-input" id="${inputId}" placeholder="${placeholder || '输入或选择模型...'}" value="${escapeHtml(initialValue)}" autocomplete="off" spellcheck="false">
                <button type="button" class="combobox-toggle-btn" id="${inputId}-toggle" title="展开/收起模型清单">▾</button>
            </div>
        </div>
    `;

    // Create the floating portal dropdown attached to body
    const dropdownEl = document.createElement('div');
    dropdownEl.className = 'combobox-dropdown';
    dropdownEl.id = `${inputId}-dropdown`;
    dropdownEl.style.display = 'none';
    dropdownEl.innerHTML = `
        <div class="combobox-search-box">
            <input type="text" class="combobox-search-input" id="${inputId}-search" placeholder="🔍 搜索模型 (输入关键词过滤)...">
        </div>
        <div class="combobox-list" id="${inputId}-list">
            <div class="combobox-empty">点击展开模型列表</div>
        </div>
    `;
    document.body.appendChild(dropdownEl);

    const inputEl = document.getElementById(inputId);
    const toggleBtn = document.getElementById(`${inputId}-toggle`);
    const searchEl = document.getElementById(`${inputId}-search`);
    const listEl = document.getElementById(`${inputId}-list`);

    let loadedModels = [];

    function renderList(filtered) {
        if (!filtered || filtered.length === 0) {
            listEl.innerHTML = `<div class="combobox-empty">无匹配模型 (支持直接在上框手动输入)</div>`;
            return;
        }
        const curVal = inputEl.value.trim();
        listEl.innerHTML = filtered.map(m => {
            const activeClass = (m === curVal) ? 'active' : '';
            return `<div class="combobox-item ${activeClass}" data-model="${escapeHtml(m)}">
                <span class="combobox-item-name">${escapeHtml(m)}</span>
            </div>`;
        }).join('');

        listEl.querySelectorAll('.combobox-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const chosen = item.getAttribute('data-model');
                inputEl.value = chosen;
                closeDropdown();
                if (onSelect) onSelect(chosen);
            });
        });
    }

    function updateDropdownPosition() {
        if (dropdownEl.style.display !== 'flex') return;
        const rect = inputEl.getBoundingClientRect();
        // If input is scrolled out of viewport or hidden, close
        if (rect.bottom < 0 || rect.top > window.innerHeight || rect.width === 0) {
            closeDropdown();
            return;
        }

        const dropdownHeight = 240;
        dropdownEl.style.position = 'fixed';
        dropdownEl.style.left = `${rect.left}px`;
        dropdownEl.style.width = `${rect.width}px`;
        dropdownEl.style.zIndex = '999999';

        const spaceBelow = window.innerHeight - rect.bottom;
        if (spaceBelow < dropdownHeight && rect.top > dropdownHeight) {
            // Open upwards
            dropdownEl.style.top = `${rect.top - dropdownHeight - 4}px`;
        } else {
            // Open downwards
            dropdownEl.style.top = `${rect.bottom + 4}px`;
        }
    }

    function openDropdown() {
        if (inputEl.disabled) return;
        // Close other combobox dropdowns
        document.querySelectorAll('.combobox-dropdown').forEach(d => {
            if (d !== dropdownEl) d.style.display = 'none';
        });
        dropdownEl.style.display = 'flex';
        updateDropdownPosition();
        searchEl.value = '';
        loadAndRender();
        setTimeout(() => searchEl.focus(), 50);
    }

    function closeDropdown() {
        dropdownEl.style.display = 'none';
    }

    async function loadAndRender(force = false) {
        const pId = getProviderId ? getProviderId() : '';
        if (!pId) {
            listEl.innerHTML = `<div class="combobox-empty">请先选择 Provider</div>`;
            return;
        }
        listEl.innerHTML = `<div class="combobox-empty">⏳ 正在拉取 Provider 最新模型...</div>`;
        loadedModels = await fetchProviderModels(pId, force);
        if (loadedModels.length === 0) {
            listEl.innerHTML = `<div class="combobox-empty">未拉取到模型列表，可在上方手动输入</div>`;
        } else {
            renderList(loadedModels);
        }
    }

    inputEl.addEventListener('click', openDropdown);
    toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (dropdownEl.style.display === 'flex') {
            closeDropdown();
        } else {
            openDropdown();
        }
    });

    searchEl.addEventListener('input', () => {
        const kw = searchEl.value.trim().toLowerCase();
        if (!kw) {
            renderList(loadedModels);
        } else {
            const filtered = loadedModels.filter(m => m.toLowerCase().includes(kw));
            renderList(filtered);
        }
    });

    // Close when clicking outside
    const onDocClick = (e) => {
        if (!container.contains(e.target) && !dropdownEl.contains(e.target)) {
            closeDropdown();
        }
    };
    document.addEventListener('pointerdown', onDocClick);

    // Update position on scroll/resize
    const onScrollOrResize = () => {
        if (dropdownEl.style.display === 'flex') {
            updateDropdownPosition();
        }
    };
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);

    return {
        getValue: () => inputEl.value.trim(),
        setValue: (val) => { inputEl.value = val || ''; },
        setPlaceholder: (ph) => { inputEl.placeholder = ph; },
        refresh: (force = false) => loadAndRender(force),
        setDisabled: (disabled) => {
            inputEl.disabled = disabled;
            toggleBtn.disabled = disabled;
            if (disabled) {
                closeDropdown();
                inputEl.style.opacity = '0.6';
            } else {
                inputEl.style.opacity = '1';
            }
        },
        destroy: () => {
            document.removeEventListener('pointerdown', onDocClick);
            window.removeEventListener('scroll', onScrollOrResize, true);
            window.removeEventListener('resize', onScrollOrResize);
            if (dropdownEl.parentNode) {
                dropdownEl.parentNode.removeChild(dropdownEl);
            }
        }
    };
}

// ==========================================================
// Provider Settings Modal (Global Providers & Default Models)
// ==========================================================

function switchProviderConfigTab(tabKey) {
    const tabKeys = ['openai', 'ollama', 'lmstudio', 'nvidia', 'amd', 'cloudflare', 'intranet'];
    tabKeys.forEach(k => {
        const btn = document.getElementById(`ptab-btn-${k}`);
        const content = document.getElementById(`pcfg-tab-${k}`);
        if (btn && content) {
            if (k === tabKey) {
                btn.classList.add('active');
                content.style.display = 'block';
            } else {
                btn.classList.remove('active');
                content.style.display = 'none';
            }
        }
    });
}

function populateProviderSelectOptions(selectEl, includeDefaultOption = false, defaultLabel = "(跟随全局默认)") {
    if (!selectEl) return;
    const currentVal = selectEl.value;
    selectEl.innerHTML = '';
    
    if (includeDefaultOption) {
        const optDef = document.createElement('option');
        optDef.value = '';
        optDef.textContent = defaultLabel;
        selectEl.appendChild(optDef);
    }

    availableProvidersList.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name || p.id;
        selectEl.appendChild(opt);
    });

    if (currentVal) {
        selectEl.value = currentVal;
    }
}

async function loadProviderSettings() {
    await checkAvailableProviders();

    try {
        const resp = await fetch('/api/study/providers/config');
        if (resp.ok) {
            const res = await resp.json();
            const data = res.data || {};
            globalProvidersConfig = data.providers || {};
            globalDefaultModels = data.defaults || {};

            // Populate form fields for each provider
            const p = globalProvidersConfig;
            
            // OpenAI Compatible
            const pOpenAI = p.openai_compatible || {};
            setInputValue('pcfg-openai-url', pOpenAI.base_url || 'https://api.deepseek.com/v1');
            setInputValue('pcfg-openai-key', pOpenAI.api_key || '');
            setInputValue('pcfg-openai-model', pOpenAI.model || 'deepseek-chat');

            // Ollama
            const pOllama = p.ollama || {};
            setInputValue('pcfg-ollama-url', pOllama.base_url || 'http://127.0.0.1:11434');
            setInputValue('pcfg-ollama-model', pOllama.model || 'qwen2.5:7b');

            // LM Studio
            const pLM = p.lm_studio || {};
            setInputValue('pcfg-lmstudio-url', pLM.base_url || 'http://127.0.0.1:1234/v1');
            setInputValue('pcfg-lmstudio-model', pLM.model || '');

            // NVIDIA
            const pNvidia = p.nvidia || {};
            setInputValue('pcfg-nvidia-url', pNvidia.base_url || 'https://integrate.api.nvidia.com/v1');
            setInputValue('pcfg-nvidia-key', pNvidia.api_key || '');
            setInputValue('pcfg-nvidia-model', pNvidia.model || 'meta/llama-3.3-70b-instruct');

            // AMD
            const pAMD = p.amd || {};
            setInputValue('pcfg-amd-url', pAMD.base_url || 'http://127.0.0.1:8000/v1');
            setInputValue('pcfg-amd-key', pAMD.api_key || '');
            setInputValue('pcfg-amd-model', pAMD.model || 'deepseek-ai/DeepSeek-R1-Distill-Qwen-32B');

            // Cloudflare
            const pCF = p.cloudflare || {};
            setInputValue('pcfg-cf-account', pCF.account_id || '');
            setInputValue('pcfg-cf-token', pCF.api_token || '');
            setInputValue('pcfg-cf-model', pCF.model || '@cf/meta/llama-3.3-70b-instruct');

            // Populate global default provider selects
            const transSelect = document.getElementById('global-default-trans-provider');
            const chatSelect = document.getElementById('global-default-chat-provider');
            const vlmSelect = document.getElementById('global-default-vlm-provider');

            populateProviderSelectOptions(transSelect, false);
            populateProviderSelectOptions(chatSelect, false);
            populateProviderSelectOptions(vlmSelect, false);

            if (transSelect) transSelect.value = globalDefaultModels.default_translation_provider || 'openai_compatible';
            if (chatSelect) chatSelect.value = globalDefaultModels.default_chat_provider || 'openai_compatible';
            if (vlmSelect) vlmSelect.value = globalDefaultModels.default_vlm_provider || 'openai_compatible';

            // Initialize global searchable comboboxes
            gTransCombobox = createSearchableCombobox({
                containerId: 'global-default-trans-model-wrap',
                inputId: 'global-default-trans-model',
                placeholder: '选择或输入默认翻译模型...',
                getProviderId: () => document.getElementById('global-default-trans-provider').value,
                initialValue: globalDefaultModels.default_translation_model || 'deepseek-chat'
            });

            gChatCombobox = createSearchableCombobox({
                containerId: 'global-default-chat-model-wrap',
                inputId: 'global-default-chat-model',
                placeholder: '选择或输入默认助教模型...',
                getProviderId: () => document.getElementById('global-default-chat-provider').value,
                initialValue: globalDefaultModels.default_chat_model || 'deepseek-chat'
            });

            gVlmCombobox = createSearchableCombobox({
                containerId: 'global-default-vlm-model-wrap',
                inputId: 'global-default-vlm-model',
                placeholder: '选择或输入默认多模态模型...',
                getProviderId: () => document.getElementById('global-default-vlm-provider').value,
                initialValue: globalDefaultModels.default_vlm_model || ''
            });

            // Prefetch models for selected providers
            if (transSelect && transSelect.value) fetchProviderModels(transSelect.value);
            if (chatSelect && chatSelect.value) fetchProviderModels(chatSelect.value);
            if (vlmSelect && vlmSelect.value) fetchProviderModels(vlmSelect.value);
        }
    } catch (e) {
        console.error("加载 Providers 配置失败:", e);
    }
}

function onGlobalDefaultProviderChange(task) {
    if (task === 'trans' && gTransCombobox) {
        gTransCombobox.refresh();
    } else if (task === 'chat' && gChatCombobox) {
        gChatCombobox.refresh();
    } else if (task === 'vlm' && gVlmCombobox) {
        gVlmCombobox.refresh();
    }
}

async function openProviderSettingsModal() {
    await loadProviderSettings();
    const modal = document.getElementById('provider-settings-modal');
    if (modal) modal.classList.add('open');
}

function closeProviderSettingsModal() {
    const modal = document.getElementById('provider-settings-modal');
    if (modal) modal.classList.remove('open');
    document.querySelectorAll('.combobox-dropdown').forEach(d => d.style.display = 'none');
}

async function testProviderInConfig(providerType) {
    let payload = { provider: providerType };
    let resultSpan = null;

    if (providerType === 'openai_compatible') {
        resultSpan = document.getElementById('pcfg-openai-test-result');
        payload.base_url = getInputValue('pcfg-openai-url') || 'https://api.deepseek.com/v1';
        payload.api_key = getInputValue('pcfg-openai-key');
        payload.model = getInputValue('pcfg-openai-model');
    } else if (providerType === 'ollama') {
        resultSpan = document.getElementById('pcfg-ollama-test-result');
        payload.base_url = getInputValue('pcfg-ollama-url') || 'http://127.0.0.1:11434';
        payload.model = getInputValue('pcfg-ollama-model');
    } else if (providerType === 'lm_studio') {
        resultSpan = document.getElementById('pcfg-lmstudio-test-result');
        payload.base_url = getInputValue('pcfg-lmstudio-url') || 'http://127.0.0.1:1234/v1';
        payload.model = getInputValue('pcfg-lmstudio-model');
    } else if (providerType === 'nvidia') {
        resultSpan = document.getElementById('pcfg-nvidia-test-result');
        payload.base_url = getInputValue('pcfg-nvidia-url') || 'https://integrate.api.nvidia.com/v1';
        payload.api_key = getInputValue('pcfg-nvidia-key');
        payload.model = getInputValue('pcfg-nvidia-model');
    } else if (providerType === 'amd') {
        resultSpan = document.getElementById('pcfg-amd-test-result');
        payload.base_url = getInputValue('pcfg-amd-url') || 'http://127.0.0.1:8000/v1';
        payload.api_key = getInputValue('pcfg-amd-key');
        payload.model = getInputValue('pcfg-amd-model');
    } else if (providerType === 'cloudflare') {
        resultSpan = document.getElementById('pcfg-cloudflare-test-result');
        payload.account_id = getInputValue('pcfg-cf-account');
        payload.api_token = getInputValue('pcfg-cf-token');
        payload.model = getInputValue('pcfg-cf-model');
    } else if (providerType === 'custom_gateway') {
        resultSpan = document.getElementById('pcfg-custom-test-result');
    }

    if (resultSpan) {
        resultSpan.className = 'test-status-badge loading';
        resultSpan.innerText = '⏳ 正在测试连通性...';
    }

    try {
        const resp = await fetch('/api/study/providers/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (resp.ok) {
            const res = await resp.json();
            const info = res.data || {};
            if (info.connected) {
                const models = info.models || [];
                const sampleModels = models.slice(0, 5).join(', ');
                if (resultSpan) {
                    resultSpan.className = 'test-status-badge success';
                    resultSpan.innerText = `✅ ${info.message || '连接成功！'} (${models.length}个模型: ${sampleModels}${models.length > 5 ? '...' : ''})`;
                }
                // Cache models
                if (models.length > 0) {
                    providerModelsCache[providerType] = models;
                }
            } else {
                if (resultSpan) {
                    resultSpan.className = 'test-status-badge error';
                    resultSpan.innerText = `❌ ${info.message || '连接失败'}`;
                }
            }
        } else {
            if (resultSpan) {
                resultSpan.className = 'test-status-badge error';
                resultSpan.innerText = `❌ HTTP ${resp.status}: 服务异常`;
            }
        }
    } catch (err) {
        if (resultSpan) {
            resultSpan.className = 'test-status-badge error';
            resultSpan.innerText = `❌ 请求异常: ${err.message || '网络超时'}`;
        }
    }
}

async function saveProviderSettings() {
    const payload = {
        providers: {
            openai_compatible: {
                base_url: getInputValue('pcfg-openai-url') || 'https://api.deepseek.com/v1',
                api_key: getInputValue('pcfg-openai-key'),
                model: getInputValue('pcfg-openai-model') || 'deepseek-chat'
            },
            ollama: {
                base_url: getInputValue('pcfg-ollama-url') || 'http://127.0.0.1:11434',
                model: getInputValue('pcfg-ollama-model') || 'qwen2.5:7b'
            },
            lm_studio: {
                base_url: getInputValue('pcfg-lmstudio-url') || 'http://127.0.0.1:1234/v1',
                model: getInputValue('pcfg-lmstudio-model') || ''
            },
            nvidia: {
                base_url: getInputValue('pcfg-nvidia-url') || 'https://integrate.api.nvidia.com/v1',
                api_key: getInputValue('pcfg-nvidia-key'),
                model: getInputValue('pcfg-nvidia-model') || 'meta/llama-3.3-70b-instruct'
            },
            amd: {
                base_url: getInputValue('pcfg-amd-url') || 'http://127.0.0.1:8000/v1',
                api_key: getInputValue('pcfg-amd-key'),
                model: getInputValue('pcfg-amd-model') || 'deepseek-ai/DeepSeek-R1-Distill-Qwen-32B'
            },
            cloudflare: {
                account_id: getInputValue('pcfg-cf-account'),
                api_token: getInputValue('pcfg-cf-token'),
                model: getInputValue('pcfg-cf-model') || '@cf/meta/llama-3.3-70b-instruct'
            }
        },
        defaults: {
            default_translation_provider: document.getElementById('global-default-trans-provider') ? document.getElementById('global-default-trans-provider').value : 'openai_compatible',
            default_translation_model: gTransCombobox ? gTransCombobox.getValue() : 'deepseek-chat',
            default_chat_provider: document.getElementById('global-default-chat-provider') ? document.getElementById('global-default-chat-provider').value : 'openai_compatible',
            default_chat_model: gChatCombobox ? gChatCombobox.getValue() : 'deepseek-chat',
            default_vlm_provider: document.getElementById('global-default-vlm-provider') ? document.getElementById('global-default-vlm-provider').value : 'openai_compatible',
            default_vlm_model: gVlmCombobox ? gVlmCombobox.getValue() : ''
        }
    };

    try {
        const resp = await fetch('/api/study/providers/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (resp.ok) {
            showToast("✅ 模型与服务 Provider 配置已成功保存！");
            closeProviderSettingsModal();
            // Sync chat drawer model dropdown
            if (typeof syncChatActiveModelSelector === 'function') {
                syncChatActiveModelSelector();
            }
        } else {
            alert("保存失败，HTTP状态码: " + resp.status);
        }
    } catch (e) {
        console.error("保存 Provider 配置失败:", e);
        alert("保存配置异常: " + e.message);
    }
}

// ==========================================================
// Document Settings Modal (Translation & Document Overrides)
// ==========================================================

async function loadSettings() {
    try {
        await checkAvailableProviders();

        let url = '/api/study/settings';
        if (activeDocId) {
            url += `?doc_id=${encodeURIComponent(activeDocId)}`;
        }
        const res = await fetch(url);
        const result = await res.json();
        const s = result.data || {};
        const isDocLevel = !!s.is_doc_level;

        // Update scope badge and reset button
        const badge = document.getElementById('setting-scope-badge');
        const resetBtn = document.getElementById('btn-reset-doc-settings');
        if (badge) {
            if (isDocLevel && activeDocMeta) {
                badge.textContent = `📄 当前文档专属配置 (${activeDocMeta.title || '当前文档'})`;
                badge.style.background = 'rgba(16, 185, 129, 0.2)';
                badge.style.color = '#6ee7b7';
            } else {
                badge.textContent = '🌐 全局通用默认配置';
                badge.style.background = 'rgba(99, 102, 241, 0.2)';
                badge.style.color = '#c7d2fe';
            }
        }
        if (resetBtn) {
            resetBtn.style.display = isDocLevel ? 'inline-block' : 'none';
        }

        // Basic settings
        setInputValue('setting-prompt-template', s.translation_prompt_template || '');
        setInputValue('setting-delay', s.model_call_delay || 1.0);

        // Providers dropdowns for Doc
        const transSelect = document.getElementById('doc-trans-provider');
        const chatSelect = document.getElementById('doc-chat-provider');
        const vlmSelect = document.getElementById('doc-vlm-provider');

        const defTransName = s.default_translation_provider || 'openai_compatible';
        const defChatName = s.default_chat_provider || 'openai_compatible';
        const defVlmName = s.default_vlm_provider || 'openai_compatible';

        populateProviderSelectOptions(transSelect, true, `(跟随全局默认: ${defTransName})`);
        populateProviderSelectOptions(chatSelect, true, `(跟随全局默认: ${defChatName})`);
        populateProviderSelectOptions(vlmSelect, true, `(跟随全局默认: ${defVlmName})`);

        if (transSelect) transSelect.value = s.translation_provider || '';
        if (chatSelect) chatSelect.value = s.chat_provider || '';
        if (vlmSelect) vlmSelect.value = s.vlm_provider || '';

        // Searchable Comboboxes for Doc
        docTransCombobox = createSearchableCombobox({
            containerId: 'doc-trans-model-wrap',
            inputId: 'setting-doc-trans-model',
            placeholder: `留空跟随默认 (${s.default_translation_model || 'deepseek-chat'})`,
            getProviderId: () => {
                const val = document.getElementById('doc-trans-provider').value;
                return val || s.default_translation_provider || 'openai_compatible';
            },
            initialValue: s.translation_model || ''
        });

        docChatCombobox = createSearchableCombobox({
            containerId: 'doc-chat-model-wrap',
            inputId: 'setting-doc-chat-model',
            placeholder: `留空跟随默认 (${s.default_chat_model || 'deepseek-chat'})`,
            getProviderId: () => {
                const val = document.getElementById('doc-chat-provider').value;
                return val || s.default_chat_provider || 'openai_compatible';
            },
            initialValue: s.chat_model || ''
        });

        docVlmCombobox = createSearchableCombobox({
            containerId: 'doc-vlm-model-wrap',
            inputId: 'setting-doc-vlm-model',
            placeholder: `留空跟随默认 (${s.default_vlm_model || '未设定'})`,
            getProviderId: () => {
                const val = document.getElementById('doc-vlm-provider').value;
                return val || s.default_vlm_provider || 'openai_compatible';
            },
            initialValue: s.vlm_model || ''
        });

        // Quick Prompts
        const paraPrompts = s.paragraph_quick_prompts || s.chat_quick_prompts;
        if (Array.isArray(paraPrompts) && paraPrompts.length > 0) {
            customParagraphQuickPrompts = paraPrompts.map(p => ({ label: p.label || '', prompt: p.prompt || '' }));
        } else {
            customParagraphQuickPrompts = [...defaultParagraphQuickPrompts];
        }

        const chapPrompts = s.chapter_quick_prompts || s.chapter_chat_quick_prompts;
        if (Array.isArray(chapPrompts) && chapPrompts.length > 0) {
            customChapterQuickPrompts = chapPrompts.map(p => ({ label: p.label || '', prompt: p.prompt || '' }));
        } else {
            customChapterQuickPrompts = [...defaultChapterQuickPrompts];
        }

        if (currentChatMode === 'chapter') {
            renderChapterQuickPromptsChips();
        } else {
            renderParagraphQuickPromptsChips();
        }

        renderParagraphQuickPromptsEditor();
        renderChapterQuickPromptsEditor();
    } catch (e) {
        console.error("加载设置失败", e);
    }
}

function onDocProviderChanged(task) {
    if (task === 'trans' && docTransCombobox) {
        docTransCombobox.refresh();
    } else if (task === 'chat' && docChatCombobox) {
        docChatCombobox.refresh();
    } else if (task === 'vlm' && docVlmCombobox) {
        docVlmCombobox.refresh();
    }
}

async function openSettingsModal() {
    await loadSettings();
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.add('open');
}

function closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.remove('open');
    document.querySelectorAll('.combobox-dropdown').forEach(d => d.style.display = 'none');
}

async function saveSettings() {
    const promptVal = getInputValue('setting-prompt-template');
    const delayVal = parseFloat(getInputValue('setting-delay')) || 1.0;

    const transProvider = document.getElementById('doc-trans-provider') ? document.getElementById('doc-trans-provider').value : '';
    const transModel = docTransCombobox ? docTransCombobox.getValue() : '';

    const chatProvider = document.getElementById('doc-chat-provider') ? document.getElementById('doc-chat-provider').value : '';
    const chatModel = docChatCombobox ? docChatCombobox.getValue() : '';

    const vlmProvider = document.getElementById('doc-vlm-provider') ? document.getElementById('doc-vlm-provider').value : '';
    const vlmModel = docVlmCombobox ? docVlmCombobox.getValue() : '';

    try {
        const payload = {
            translation_prompt_template: promptVal,
            model_call_delay: delayVal,
            translation_provider: transProvider,
            translation_model: transModel,
            chat_provider: chatProvider,
            chat_model: chatModel,
            vlm_provider: vlmProvider,
            vlm_model: vlmModel,
            paragraph_quick_prompts: customParagraphQuickPrompts,
            chat_quick_prompts: customParagraphQuickPrompts,
            chapter_quick_prompts: customChapterQuickPrompts,
            chapter_chat_quick_prompts: customChapterQuickPrompts
        };
        if (activeDocId) {
            payload.doc_id = activeDocId;
        }

        const res = await fetch('/api/study/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (res.ok && result.code === 200) {
            const scopeDesc = activeDocId ? "当前文档专属设置" : "全局默认设置";
            showToast(`✅ ${scopeDesc}已成功保存！`);
            if (currentChatMode === 'chapter') {
                renderChapterQuickPromptsChips();
            } else {
                renderParagraphQuickPromptsChips();
            }
            closeSettingsModal();
            // Sync chat drawer model selector
            if (typeof syncChatActiveModelSelector === 'function') {
                syncChatActiveModelSelector();
            }
        } else {
            alert("保存失败: " + (result.message || result.detail || `HTTP ${res.status}`));
        }
    } catch (e) {
        console.error("保存设置异常", e);
        alert("保存失败: " + e.message);
    }
}

async function resetDocSettings() {
    if (!activeDocId) return;
    if (!confirm("确定要恢复此文档为全局默认配置吗？")) return;

    try {
        const res = await fetch(`/api/study/documents/${activeDocId}/settings/reset`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("已成功恢复为全局默认配置！");
            await loadSettings();
            if (typeof syncChatActiveModelSelector === 'function') {
                syncChatActiveModelSelector();
            }
        } else {
            alert("恢复默认配置失败");
        }
    } catch (e) {
        console.error("恢复默认配置异常", e);
        alert("恢复失败");
    }
}

// Quick Prompts Editor Handlers (Uses state from study_state.js)
function renderParagraphQuickPromptsEditor() {
    const container = document.getElementById('para-quick-prompts-editor');
    if (!container) return;
    container.innerHTML = customParagraphQuickPrompts.map((item, idx) => `
        <div class="quick-prompt-edit-item" style="display: flex; gap: 8px; align-items: center; background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 6px; padding: 6px 10px;">
            <input type="text" class="form-input" style="width: 130px; padding: 5px 8px; font-size: 12px;" value="${escapeHtml(item.label || '')}" placeholder="按钮名称" oninput="updateParagraphQuickPromptItem(${idx}, 'label', this.value)">
            <input type="text" class="form-input" style="flex: 1; padding: 5px 8px; font-size: 12px;" value="${escapeHtml(item.prompt || '')}" placeholder="发送给助教的提问模板" oninput="updateParagraphQuickPromptItem(${idx}, 'prompt', this.value)">
            <button type="button" class="btn" style="padding: 4px 8px; font-size: 11px; color: #f87171; border-color: rgba(239, 68, 68, 0.3);" onclick="deleteParagraphQuickPromptItem(${idx})" title="删除此项">✕</button>
        </div>
    `).join('');
}

function addParagraphQuickPromptItem() {
    customParagraphQuickPrompts.push({ label: "💡 新增提问", prompt: "请针对本段内容解答我的疑问..." });
    renderParagraphQuickPromptsEditor();
    if (currentChatMode === 'paragraph') renderParagraphQuickPromptsChips();
}

function updateParagraphQuickPromptItem(idx, field, value) {
    if (customParagraphQuickPrompts[idx]) {
        customParagraphQuickPrompts[idx][field] = value.trim();
        if (currentChatMode === 'paragraph') renderParagraphQuickPromptsChips();
    }
}

function deleteParagraphQuickPromptItem(idx) {
    customParagraphQuickPrompts.splice(idx, 1);
    renderParagraphQuickPromptsEditor();
    if (currentChatMode === 'paragraph') renderParagraphQuickPromptsChips();
}

function renderChapterQuickPromptsEditor() {
    const container = document.getElementById('chapter-quick-prompts-editor');
    if (!container) return;
    container.innerHTML = customChapterQuickPrompts.map((item, idx) => `
        <div class="quick-prompt-edit-item" style="display: flex; gap: 8px; align-items: center; background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 6px; padding: 6px 10px;">
            <input type="text" class="form-input" style="width: 130px; padding: 5px 8px; font-size: 12px;" value="${escapeHtml(item.label || '')}" placeholder="按钮名称" oninput="updateChapterQuickPromptItem(${idx}, 'label', this.value)">
            <input type="text" class="form-input" style="flex: 1; padding: 5px 8px; font-size: 12px;" value="${escapeHtml(item.prompt || '')}" placeholder="发送给助教的提问模板" oninput="updateChapterQuickPromptItem(${idx}, 'prompt', this.value)">
            <button type="button" class="btn" style="padding: 4px 8px; font-size: 11px; color: #f87171; border-color: rgba(239, 68, 68, 0.3);" onclick="deleteChapterQuickPromptItem(${idx})" title="删除此项">✕</button>
        </div>
    `).join('');
}

function addChapterQuickPromptItem() {
    customChapterQuickPrompts.push({ label: "💡 新增提问", prompt: "请针对全章内容解答我的疑问..." });
    renderChapterQuickPromptsEditor();
    if (currentChatMode === 'chapter') renderChapterQuickPromptsChips();
}

function updateChapterQuickPromptItem(idx, field, value) {
    if (customChapterQuickPrompts[idx]) {
        customChapterQuickPrompts[idx][field] = value.trim();
        if (currentChatMode === 'chapter') renderChapterQuickPromptsChips();
    }
}

function deleteChapterQuickPromptItem(idx) {
    customChapterQuickPrompts.splice(idx, 1);
    renderChapterQuickPromptsEditor();
    if (currentChatMode === 'chapter') renderChapterQuickPromptsChips();
}

// Utility Helpers
function getInputValue(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function setInputValue(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val;
}
