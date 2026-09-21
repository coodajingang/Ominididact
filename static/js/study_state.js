// ==========================================================
// Global Application State
// ==========================================================
// Global Application State
        let activeDocId = null;
        let activeDocMeta = null;
        let activeChapterId = null;
        let activeChapterData = null;
        let activeParagraphForChat = null;
        let chatHistory = [];
        let currentFontSize = 17;
        const widthModes = ['standard', 'wide', 'full'];
        let widthModeIndex = 0; // standard: 900px, wide: 1250px, full: 96%
        
        // Bilingual Layout Modes (inspired by yihong0618/bilingual_book_maker)
        const layoutModes = ['top-bottom', 'side-by-side', 'card'];
        const layoutModeLabels = {
            'top-bottom': '上下对照',
            'side-by-side': '左右并排',
            'card': '卡片视图'
        };
        let currentLayoutMode = localStorage.getItem('study_layout_mode') || 'top-bottom';

        // Theme Engine State
        const themeLabels = {
            'dark': '🌙 深邃夜色',
            'white': '☀️ 纯净雅白',
            'sepia': '📜 墨玉羊皮',
            'forest': '🍵 雅致墨绿'
        };
        let currentTheme = localStorage.getItem('study_theme') || 'sepia';

// Notes & Flashcard Context
let activeNoteContext = null;
let quickFlashcardType = 'qa';
let quickFlashcardParagraphId = null;

// Chat Mode State ('paragraph' or 'chapter')
let currentChatMode = 'paragraph';

// Customizable Quick Prompts State (Separated for Paragraph & Chapter)
const defaultParagraphQuickPrompts = [
    { label: "🔍 长难句剖析", prompt: "请深度拆解本段的长难句结构、主干成分与关键语法点" },
    { label: "📖 核心术语提炼", prompt: "请提炼出本段的核心专业词汇和术语，并给出精准含义与用法语境" },
    { label: "💡 通俗解释论点", prompt: "请用通俗易懂的中文和实际例子，解释这一段的核心论点与逻辑" },
    { label: "❓ 自测思考题", prompt: "请根据本段内容出一道自测思考题，检验我的理解深度" },
    { label: "🗂️ 生成本段闪卡", prompt: "请根据本段的核心考点和学术概念，提炼生成 1~2 张记忆闪卡（包括问答 QA 或镂空 Cloze 题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: 核心标签1, 核心标签2\n:::" },
    { label: "🗂️ 生成引用范围闪卡", prompt: "请综合当前【核心研读段落】以及前文背景、后文背景所引用的全部段落，提炼出跨段落的 2~4 张关键考点记忆闪卡（包括问答 QA 或镂空 Cloze 题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: 核心考点, 关联概念\n:::" }
];

const defaultChapterQuickPrompts = [
    { label: "🗺️ 全章脉络主线", prompt: "请系统性梳理本章的核心论述脉络与逻辑展开主线，说明作者是如何一步步展开推导的。" },
    { label: "🎯 核心论点清单", prompt: "请提炼本章最关键的 3~5 个核心论点和学术知识要点，以结构化清单呈现。" },
    { label: "💡 全景概念总结", prompt: "请用通俗生动的语言，概括本章的核心思想以及它对读者的主要认知启示。" },
    { label: "📝 本章考点复习", prompt: "如果针对本章内容设计专业测评或自测题，最重要的考点和关键概念问答有哪些？" },
    { label: "🗂️ 生成本章考点闪卡", prompt: "请根据本章全局核心脉络与重要考点，提炼生成 3~5 张高频复习闪卡（涵盖 QA 问答与 Cloze 镂空填空题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: CISSP, 章节考点\n:::" }
];

let customParagraphQuickPrompts = [...defaultParagraphQuickPrompts];
let customChapterQuickPrompts = [...defaultChapterQuickPrompts];

