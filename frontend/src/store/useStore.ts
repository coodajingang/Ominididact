import { create } from 'zustand'
import {
  ThemeMode,
  FontFamilyMode,
  ReadingWidth,
  LayoutMode,
  DocumentMeta,
  ChapterItem,
  ParagraphItem,
  ChatMessage,
  ProviderItem,
  ProvidersConfig,
  DocSettings,
  BatchTranslationStatus,
} from '@/types'
import * as api from '@/api/client'
import {
  getDocReadingProgress,
  getAllDocProgress,
  getChapterScrollTop,
  getChapterProgress,
  resetDocReadingProgress,
} from '@/lib/progress'

interface AppState {
  // Theme & Reading Layout
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
  fontFamily: FontFamilyMode
  setFontFamily: (fontFamily: FontFamilyMode) => void
  readingWidth: ReadingWidth
  setReadingWidth: (width: ReadingWidth) => void
  layoutMode: LayoutMode
  setLayoutMode: (mode: LayoutMode) => void
  fontSize: number
  setFontSize: (size: number | ((prev: number) => number)) => void
  chatFontSize: number
  setChatFontSize: (size: number | ((prev: number) => number)) => void
  isHeaderVisible: boolean
  setIsHeaderVisible: (visible: boolean) => void

  // Documents & Outline
  documents: DocumentMeta[]
  activeDocId: string | null
  activeDoc: DocumentMeta | null
  chapters: ChapterItem[]
  activeChapterId: string | null
  paragraphs: ParagraphItem[]
  isLoadingDocs: boolean
  isLoadingContent: boolean

  // Actions for Documents
  docReadingProgress: Record<string, number>
  updateDocProgress: (docId: string, ratio: number) => void
  resetDocProgress: (docId: string) => void
  targetScrollTop: number | null
  setTargetScrollTop: (top: number | null) => void
  loadDocuments: () => Promise<void>
  selectDocument: (docId: string) => Promise<void>
  refreshActiveDocContent: () => Promise<void>
  deleteDocument: (docId: string) => Promise<void>
  deleteChapter: (docId: string, chapterId: string) => Promise<void>
  renameChapter: (docId: string, chapterId: string, newTitle: string) => Promise<void>
  reloadAfterChapterStructureChange: (docId: string, targetChapterId?: string) => Promise<void>
  selectChapter: (chapterId: string, targetScroll?: number) => Promise<void>
  updateParagraph: (paragraphId: string, patch: Partial<ParagraphItem>) => void
  replaceParagraph: (updatedPara: ParagraphItem) => void
  insertParagraphAfter: (targetParagraphId: string, newPara: ParagraphItem) => void
  removeParagraph: (paragraphId: string) => void
  extractingParaIds: Set<string>
  setParaExtracting: (paraId: string, extracting: boolean) => void

  // AI Assistant Drawer
  assistantScope: 'paragraph' | 'chapter' | 'document'
  setAssistantScope: (scope: 'paragraph' | 'chapter' | 'document') => void
  isAssistantOpen: boolean
  setAssistantOpen: (open: boolean) => void
  toggleAssistant: () => void
  activeAssistantProvider: string
  setActiveAssistantProvider: (provider: string) => void
  activeAssistantModel: string
  setActiveAssistantModel: (model: string) => void
  prevContextSteps: number
  setPrevContextSteps: (steps: number) => void
  nextContextSteps: number
  setNextContextSteps: (steps: number) => void
  selectedParagraph: ParagraphItem | null
  setSelectedParagraph: (para: ParagraphItem | null) => void
  chatMessages: ChatMessage[]
  setChatMessages: (msgs: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void
  clearChatMessages: () => void
  isChatStreaming: boolean
  setIsChatStreaming: (streaming: boolean) => void

  // Provider Settings
  availableProviders: ProviderItem[]
  providersConfig: ProvidersConfig | null
  loadProvidersData: () => Promise<void>

  // Modals
  isProviderModalOpen: boolean
  setProviderModalOpen: (open: boolean) => void
  isModelTestModalOpen: boolean
  setModelTestModalOpen: (open: boolean) => void
  isDocSettingsModalOpen: boolean
  setDocSettingsModalOpen: (open: boolean) => void
  isAssetInspectionModalOpen: boolean
  assetInspectionDocId: string | null
  setAssetInspectionModalOpen: (open: boolean, docId?: string) => void
  justUploadedDocId: string | null
  setJustUploadedDocId: (docId: string | null) => void
  isNoteModalOpen: boolean
  setNoteModalOpen: (open: boolean) => void
  activeNoteParams: {
    chapterId: string
    type: 'header' | 'footer' | 'paragraph'
    paragraphId?: string
    noteId?: string
    title?: string
    content?: string
  } | null
  openNoteModal: (params: {
    chapterId: string
    type: 'header' | 'footer' | 'paragraph'
    paragraphId?: string
    noteId?: string
    title?: string
    content?: string
  }) => void

  isQuickFlashcardModalOpen: boolean
  setQuickFlashcardModalOpen: (open: boolean) => void
  quickFlashcardData: {
    paragraphId: string
    chapterId: string
    front: string
    back: string
  } | null
  openQuickFlashcardModal: (data: {
    paragraphId: string
    chapterId: string
    front: string
    back: string
  }) => void

  docFlashcardCount: number
  refreshDocFlashcardCount: (docId?: string) => Promise<void>

  // Document Extraction Polling
  pollDocumentExtraction: (docId: string) => Promise<void>

  // Batch Translation
  docBatchStatus: BatchTranslationStatus | null
  chapterBatchStatus: BatchTranslationStatus | null
  isBatchTranslating: boolean
  startChapterTranslate: (docId?: string, chapterId?: string) => Promise<void>
  stopChapterTranslate: (docId?: string, chapterId?: string) => Promise<void>
  startDocTranslate: (docId?: string) => Promise<void>
  stopDocTranslate: (docId?: string) => Promise<void>
  pollBatchTranslateStatus: (docId?: string, chapterId?: string) => Promise<void>
}

let batchTranslatePollTimer: any = null
let lastCompletedParagraphsCount = -1

function stopBatchPolling() {
  if (batchTranslatePollTimer) {
    clearInterval(batchTranslatePollTimer)
    batchTranslatePollTimer = null
  }
}

let docExtractionPollTimer: any = null

function stopDocExtractionPolling() {
  if (docExtractionPollTimer) {
    clearInterval(docExtractionPollTimer)
    docExtractionPollTimer = null
  }
}

export const useStore = create<AppState>((set, get) => ({
  // Theme & Layout
  theme: (localStorage.getItem('study_theme') as ThemeMode) || 'sepia',
  setTheme: (theme) => {
    localStorage.setItem('study_theme', theme)
    document.documentElement.className = `theme-${theme}`
    document.documentElement.setAttribute('data-theme', theme)
    document.body.className = `theme-${theme}`
    document.body.setAttribute('data-theme', theme)
    set({ theme })
  },
  fontFamily: (localStorage.getItem('study_font') as FontFamilyMode) || 'sans',
  setFontFamily: (fontFamily) => {
    localStorage.setItem('study_font', fontFamily)
    document.documentElement.setAttribute('data-font', fontFamily)
    document.body.setAttribute('data-font', fontFamily)
    const fontMap: Record<string, string> = {
      sans: "'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
      wenkai: "'Lora', 'LXGW WenKai Screen', 'LXGW WenKai', 'STKaiti', 'KaiTi', Georgia, serif",
      serif: "'Lora', 'Songti SC', 'Source Han Serif SC', 'Noto Serif SC', 'SimSun', Georgia, serif",
      system: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
    }
    const targetFont = fontMap[fontFamily] || fontMap.sans
    document.documentElement.style.setProperty('--reading-font-family', targetFont)
    document.body.style.setProperty('--reading-font-family', targetFont)
    set({ fontFamily })
  },
  readingWidth: (localStorage.getItem('study_width') as ReadingWidth) || 'standard',
  setReadingWidth: (readingWidth) => {
    localStorage.setItem('study_width', readingWidth)
    set({ readingWidth })
  },
  layoutMode: (localStorage.getItem('study_layout') as LayoutMode) || 'stack',
  setLayoutMode: (layoutMode) => {
    localStorage.setItem('study_layout', layoutMode)
    set({ layoutMode })
  },
  fontSize: parseInt(localStorage.getItem('study_font_size') || '17', 10),
  setFontSize: (updater) => {
    const newSize = typeof updater === 'function' ? updater(get().fontSize) : updater
    const clamped = Math.max(13, Math.min(26, newSize))
    localStorage.setItem('study_font_size', clamped.toString())
    set({ fontSize: clamped })
  },
  chatFontSize: parseInt(localStorage.getItem('study_chat_font_size') || '14', 10),
  setChatFontSize: (updater) => {
    const newSize = typeof updater === 'function' ? updater(get().chatFontSize) : updater
    const clamped = Math.max(12, Math.min(22, newSize))
    localStorage.setItem('study_chat_font_size', clamped.toString())
    document.documentElement.style.setProperty('--chat-font-size', `${clamped}px`)
    set({ chatFontSize: clamped })
  },
  isHeaderVisible: true,
  setIsHeaderVisible: (visible) => set({ isHeaderVisible: visible }),

  // Documents
  documents: [],
  activeDocId: null,
  activeDoc: null,
  chapters: [],
  activeChapterId: null,
  paragraphs: [],
  isLoadingDocs: false,
  isLoadingContent: false,
  docReadingProgress: {},
  targetScrollTop: null,
  setTargetScrollTop: (top) => set({ targetScrollTop: top }),
  extractingParaIds: new Set<string>(),
  setParaExtracting: (paraId: string, extracting: boolean) => {
    set((state) => {
      const next = new Set(state.extractingParaIds)
      if (extracting) {
        next.add(paraId)
      } else {
        next.delete(paraId)
      }
      return { extractingParaIds: next }
    })
  },
  updateDocProgress: (docId, ratio) => {
    set((state) => {
      const current = state.docReadingProgress[docId] ?? 0
      if (current >= 100) {
        return state
      }
      const clamped = Math.min(100, Math.max(current, Math.round(ratio)))
      return {
        docReadingProgress: {
          ...state.docReadingProgress,
          [docId]: clamped,
        },
      }
    })
  },
  resetDocProgress: (docId) => {
    resetDocReadingProgress(docId)
    set((state) => ({
      docReadingProgress: {
        ...state.docReadingProgress,
        [docId]: 0,
      },
      targetScrollTop: state.activeDocId === docId ? 0 : state.targetScrollTop,
    }))
  },

  loadDocuments: async () => {
    try {
      set({ isLoadingDocs: true })
      const docs = await api.getDocuments()
      const progMap = getAllDocProgress(docs.map((d) => d.doc_id))
      set({ documents: docs, docReadingProgress: progMap, isLoadingDocs: false })
      // If no active doc and docs exist, select first doc
      if (!get().activeDocId && docs.length > 0) {
        get().selectDocument(docs[0].doc_id)
      }
    } catch (e) {
      console.error('Failed to load documents:', e)
      set({ isLoadingDocs: false })
    }
  },

  selectDocument: async (docId: string) => {
    const cachedDoc = get().documents.find((d) => d.doc_id === docId) || null
    set({
      activeDocId: docId,
      activeDoc: cachedDoc,
      isLoadingContent: true,
      activeChapterId: null,
      targetScrollTop: null,
      isHeaderVisible: true,
    })

    try {
      const docDetail = await api.getDocumentDetail(docId)
      const chapters = docDetail.chapters || []
      set({ activeDoc: docDetail, chapters })

      if (chapters.length > 0) {
        const prog = getDocReadingProgress(docId)
        let targetChapterId = chapters[0].chapter_id
        const savedChId = prog?.lastActiveChapterId || prog?.chapterId
        if (savedChId && chapters.some((c) => c.chapter_id === savedChId)) {
          targetChapterId = savedChId
        }
        const targetScroll = getChapterScrollTop(docId, targetChapterId)

        const { chapter, paragraphs } = await api.getChapterDetail(docId, targetChapterId)
        const updatedChapters = chapters.map((c) =>
          c.chapter_id === targetChapterId ? { ...c, ...chapter } : c
        )
        set({
          chapters: updatedChapters,
          activeChapterId: targetChapterId,
          targetScrollTop: targetScroll,
          paragraphs,
          isLoadingContent: false,
        })
      } else {
        set({ activeChapterId: null, paragraphs: [], targetScrollTop: null, isLoadingContent: false })
      }
      get().refreshDocFlashcardCount(docId)
      get().pollBatchTranslateStatus(docId, chapters.length > 0 ? get().activeChapterId || undefined : undefined)

      if (get().justUploadedDocId === docId && docDetail.status === 'completed') {
        const fileType = (docDetail.file_type || '').toLowerCase()
        const isEligible = ['folder', 'zip', 'web'].includes(fileType)
        const inspection = docDetail.asset_inspection
        const totalRef = inspection?.stats?.total_referenced ?? inspection?.total_referenced ?? 0
        const shouldShowModal = isEligible && Boolean(inspection && !inspection.skipped && (totalRef > 0 || inspection.user_notice))
        if (shouldShowModal) {
          set({
            justUploadedDocId: null,
            isAssetInspectionModalOpen: true,
            assetInspectionDocId: docId,
          })
        } else {
          set({ justUploadedDocId: null })
        }
      }

      if (docDetail.status === 'extracting' || docDetail.status === 'processing') {
        get().pollDocumentExtraction(docId)
      } else {
        stopDocExtractionPolling()
      }
    } catch (e) {
      console.error('Failed to load document content:', e)
      set({ isLoadingContent: false })
    }
  },

  refreshActiveDocContent: async () => {
    const { activeDocId, activeChapterId } = get()
    if (!activeDocId || !activeChapterId) return
    try {
      const { chapter, paragraphs } = await api.getChapterDetail(activeDocId, activeChapterId)
      const updatedChapters = get().chapters.map((c) =>
        c.chapter_id === activeChapterId ? { ...c, ...chapter } : c
      )
      set({ chapters: updatedChapters, paragraphs })
      get().refreshDocFlashcardCount(activeDocId)
    } catch (e) {
      console.error('Refresh active doc content failed:', e)
    }
  },

  deleteDocument: async (docId: string) => {
    await api.deleteDocument(docId)
    const newDocs = get().documents.filter((d) => d.doc_id !== docId)
    set({ documents: newDocs })
    if (get().activeDocId === docId) {
      if (newDocs.length > 0) {
        get().selectDocument(newDocs[0].doc_id)
      } else {
        set({ activeDocId: null, activeDoc: null, activeChapterId: null, chapters: [], paragraphs: [] })
      }
    }
  },

  deleteChapter: async (docId: string, chapterId: string) => {
    const res = await api.deleteChapter(docId, chapterId)
    if (res.document_deleted) {
      const newDocs = get().documents.filter((d) => d.doc_id !== docId)
      set({ documents: newDocs })
      if (get().activeDocId === docId) {
        if (newDocs.length > 0) {
          get().selectDocument(newDocs[0].doc_id)
        } else {
          set({
            activeDocId: null,
            activeDoc: null,
            activeChapterId: null,
            chapters: [],
            paragraphs: [],
          })
        }
      }
    } else {
      const currentChapters = get().chapters.filter((c) => c.chapter_id !== chapterId)
      const currentDoc = get().activeDoc
      const updatedDoc =
        currentDoc && currentDoc.doc_id === docId
          ? {
              ...currentDoc,
              chapters: currentChapters,
              paragraph_count: res.total_paragraphs ?? currentDoc.paragraph_count,
              translated_count: res.translated_paragraphs ?? currentDoc.translated_count,
            }
          : currentDoc

      const newDocs = get().documents.map((d) =>
        d.doc_id === docId
          ? {
              ...d,
              chapters: currentChapters,
              paragraph_count: res.total_paragraphs ?? d.paragraph_count,
              translated_count: res.translated_paragraphs ?? d.translated_count,
            }
          : d
      )

      set({
        documents: newDocs,
        chapters: currentChapters,
        activeDoc: updatedDoc,
      })

      // If the deleted chapter was the currently active chapter:
      if (get().activeChapterId === chapterId) {
        if (currentChapters.length > 0) {
          await get().selectChapter(currentChapters[0].chapter_id)
        } else {
          set({ activeChapterId: null, paragraphs: [] })
        }
      }
    }
  },

  renameChapter: async (docId: string, chapterId: string, newTitle: string) => {
    await api.renameChapter(docId, chapterId, newTitle)
    const updatedChapters = get().chapters.map((c) =>
      c.chapter_id === chapterId ? { ...c, title: newTitle } : c
    )
    const currentDoc = get().activeDoc
    const updatedDoc =
      currentDoc && currentDoc.doc_id === docId
        ? { ...currentDoc, chapters: updatedChapters }
        : currentDoc

    const newDocs = get().documents.map((d) =>
      d.doc_id === docId ? { ...d, chapters: updatedChapters } : d
    )
    set({
      documents: newDocs,
      chapters: updatedChapters,
      activeDoc: updatedDoc,
    })
  },

  reloadAfterChapterStructureChange: async (docId: string, targetChapterId?: string) => {
    try {
      const docDetail = await api.getDocumentDetail(docId)
      const chapters = docDetail.chapters || []
      set({ activeDoc: docDetail, chapters })

      const currentActiveId = targetChapterId || get().activeChapterId
      const validChapterId = chapters.some((c) => c.chapter_id === currentActiveId)
        ? currentActiveId
        : chapters.length > 0
        ? chapters[0].chapter_id
        : null

      if (validChapterId) {
        await get().selectChapter(validChapterId)
      } else {
        set({ activeChapterId: null, paragraphs: [] })
      }
      get().refreshDocFlashcardCount(docId)
    } catch (e) {
      console.error('reloadAfterChapterStructureChange failed:', e)
    }
  },

  selectChapter: async (chapterId: string, targetScroll?: number) => {
    const { activeDocId, chapters } = get()
    if (!activeDocId) return
    const scroll = targetScroll !== undefined
      ? targetScroll
      : getChapterScrollTop(activeDocId, chapterId)
    set({ activeChapterId: chapterId, targetScrollTop: scroll, isLoadingContent: true, isHeaderVisible: true })

    try {
      const { chapter, paragraphs } = await api.getChapterDetail(activeDocId, chapterId)
      const updatedChapters = chapters.map((c) =>
        c.chapter_id === chapterId ? { ...c, ...chapter } : c
      )
      set({
        chapters: updatedChapters,
        paragraphs,
        targetScrollTop: scroll,
        isLoadingContent: false,
      })
      lastCompletedParagraphsCount = -1
      get().pollBatchTranslateStatus(activeDocId, chapterId)
    } catch (e) {
      console.error('Failed to load chapter content:', e)
      set({ isLoadingContent: false })
    }
  },

  updateParagraph: (paragraphId: string, patch: Partial<ParagraphItem>) => {
    set((state) => ({
      paragraphs: state.paragraphs.map((p) =>
        p.id === paragraphId ? { ...p, ...patch } : p
      ),
      selectedParagraph:
        state.selectedParagraph?.id === paragraphId
          ? { ...state.selectedParagraph, ...patch }
          : state.selectedParagraph,
    }))
  },

  replaceParagraph: (updatedPara: ParagraphItem) => {
    set((state) => ({
      paragraphs: state.paragraphs.map((p) =>
        p.id === updatedPara.id ? updatedPara : p
      ),
      selectedParagraph:
        state.selectedParagraph?.id === updatedPara.id
          ? updatedPara
          : state.selectedParagraph,
    }))
  },

  insertParagraphAfter: (targetParagraphId: string, newPara: ParagraphItem) => {
    set((state) => {
      const idx = state.paragraphs.findIndex((p) => p.id === targetParagraphId)
      if (idx === -1) {
        return { paragraphs: [...state.paragraphs, newPara] }
      }
      const newParas = [...state.paragraphs]
      newParas.splice(idx + 1, 0, newPara)
      return { paragraphs: newParas }
    })
  },

  removeParagraph: (paragraphId: string) => {
    set((state) => {
      const removed = state.paragraphs.find((p) => p.id === paragraphId)
      const nextParagraphs = state.paragraphs.filter((p) => p.id !== paragraphId)
      const activeChapterId = state.activeChapterId

      const nextChapters = state.chapters.map((ch) => {
        if (ch.chapter_id === activeChapterId) {
          return {
            ...ch,
            paragraph_count: Math.max(0, (ch.paragraph_count || 0) - 1),
          }
        }
        return ch
      })

      const nextActiveDoc = state.activeDoc
        ? {
            ...state.activeDoc,
            paragraph_count: Math.max(0, (state.activeDoc.paragraph_count || 0) - 1),
            total_paragraphs: Math.max(0, (state.activeDoc.total_paragraphs ?? state.activeDoc.paragraph_count ?? 1) - 1),
            translated_count:
              removed?.status === 'completed'
                ? Math.max(0, (state.activeDoc.translated_count || 0) - 1)
                : state.activeDoc.translated_count,
          }
        : null

      return {
        paragraphs: nextParagraphs,
        chapters: nextChapters,
        activeDoc: nextActiveDoc,
        selectedParagraph:
          state.selectedParagraph?.id === paragraphId
            ? null
            : state.selectedParagraph,
      }
    })
  },

  // AI Assistant
  assistantScope: 'chapter',
  setAssistantScope: (scope) => set({ assistantScope: scope }),
  isAssistantOpen: false,
  setAssistantOpen: (open) => set({ isAssistantOpen: open }),
  toggleAssistant: () => set((state) => ({ isAssistantOpen: !state.isAssistantOpen })),
  activeAssistantProvider: '',
  setActiveAssistantProvider: (provider) => set({ activeAssistantProvider: provider }),
  activeAssistantModel: '',
  setActiveAssistantModel: (model) => set({ activeAssistantModel: model }),
  prevContextSteps: 2,
  setPrevContextSteps: (steps) => set({ prevContextSteps: Math.max(0, steps) }),
  nextContextSteps: 2,
  setNextContextSteps: (steps) => set({ nextContextSteps: Math.max(0, steps) }),
  selectedParagraph: null,
  setSelectedParagraph: (para) => set({ selectedParagraph: para }),
  chatMessages: [
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '您好！我是您的专属文献研读助教。长难句辨析、学术概念推演、核心要点梳理或背景深挖，随时向我提问！',
      created_at: new Date().toISOString(),
    },
  ],
  setChatMessages: (updater) => {
    set((state) => ({
      chatMessages:
        typeof updater === 'function' ? updater(state.chatMessages) : updater,
    }))
  },
  clearChatMessages: () =>
    set({
      chatMessages: [
        {
          id: 'welcome-' + Date.now(),
          role: 'assistant',
          content: '已清空当前对话记录。随时选中段落开始新的探讨！',
          created_at: new Date().toISOString(),
        },
      ],
    }),
  isChatStreaming: false,
  setIsChatStreaming: (streaming) => set({ isChatStreaming: streaming }),

  // Providers
  availableProviders: [],
  providersConfig: null,
  loadProvidersData: async () => {
    try {
      const [providers, config] = await Promise.all([
        api.getAvailableProviders(),
        api.getProvidersConfig(),
      ])
      set({ availableProviders: providers, providersConfig: config })
      if (config?.defaults?.default_chat_model && !get().activeAssistantModel) {
        set({ activeAssistantModel: config.defaults.default_chat_model })
      }
    } catch (e) {
      console.error('Failed to load providers config:', e)
    }
  },

  // Modals
  isProviderModalOpen: false,
  setProviderModalOpen: (open) => set({ isProviderModalOpen: open }),
  isModelTestModalOpen: false,
  setModelTestModalOpen: (open) => set({ isModelTestModalOpen: open }),
  isDocSettingsModalOpen: false,
  setDocSettingsModalOpen: (open) => set({ isDocSettingsModalOpen: open }),
  isAssetInspectionModalOpen: false,
  assetInspectionDocId: null,
  setAssetInspectionModalOpen: (open, docId) =>
    set({
      isAssetInspectionModalOpen: open,
      assetInspectionDocId: docId !== undefined ? docId : get().assetInspectionDocId,
    }),
  justUploadedDocId: null,
  setJustUploadedDocId: (docId) => set({ justUploadedDocId: docId }),
  isNoteModalOpen: false,
  setNoteModalOpen: (open) => set({ isNoteModalOpen: open }),
  activeNoteParams: null,
  openNoteModal: (params) => set({ isNoteModalOpen: true, activeNoteParams: params }),

  isQuickFlashcardModalOpen: false,
  setQuickFlashcardModalOpen: (open) => set({ isQuickFlashcardModalOpen: open }),
  quickFlashcardData: null,
  openQuickFlashcardModal: (data) => set({ isQuickFlashcardModalOpen: true, quickFlashcardData: data }),

  docFlashcardCount: 0,
  refreshDocFlashcardCount: async (docId?: string) => {
    const targetDocId = docId || get().activeDoc?.doc_id || get().activeDocId
    if (!targetDocId) {
      set({ docFlashcardCount: 0 })
      return
    }
    try {
      const count = await api.getDocFlashcardsCount(targetDocId)
      set({ docFlashcardCount: count })
    } catch (e) {
      console.warn('Failed to refresh doc flashcard count:', e)
    }
  },

  // Batch Translation
  docBatchStatus: null,
  chapterBatchStatus: null,
  isBatchTranslating: false,

  pollBatchTranslateStatus: async (docId?: string, chapterId?: string) => {
    const targetDocId = docId || get().activeDoc?.doc_id || get().activeDocId
    const targetChapterId = chapterId || get().activeChapterId
    if (!targetDocId) return

    try {
      const [docStatus, chStatus] = await Promise.all([
        api.getDocumentTranslationStatus(targetDocId).catch(() => null),
        targetChapterId
          ? api.getChapterTranslationStatus(targetDocId, targetChapterId).catch(() => null)
          : Promise.resolve(null),
      ])

      const isRunning = Boolean(docStatus?.is_running || chStatus?.is_running)

      set({
        docBatchStatus: docStatus,
        chapterBatchStatus: chStatus,
        isBatchTranslating: isRunning,
      })

      if (isRunning) {
        if (!batchTranslatePollTimer) {
          batchTranslatePollTimer = setInterval(() => {
            get().pollBatchTranslateStatus()
          }, 1500)
        }
        if (chStatus && chStatus.completed > lastCompletedParagraphsCount) {
          lastCompletedParagraphsCount = chStatus.completed
          get().refreshActiveDocContent()
        }
      } else {
        if (batchTranslatePollTimer) {
          stopBatchPolling()
          get().refreshActiveDocContent()
          get().loadDocuments()
        }
      }
    } catch (e) {
      console.warn('Failed to poll batch translation status:', e)
    }
  },

  pollDocumentExtraction: async (docId: string) => {
    if (!docId) return
    try {
      const docDetail = await api.getDocumentDetail(docId)
      if (get().activeDocId === docId) {
        set({ activeDoc: docDetail })
      }

      const status = docDetail.status || 'completed'
      if (status === 'completed') {
        stopDocExtractionPolling()
        await get().loadDocuments()
        if (get().activeDocId === docId) {
          await get().selectDocument(docId)
        }
        if (get().justUploadedDocId === docId) {
          const docDetail = get().activeDoc
          const fileType = (docDetail?.file_type || '').toLowerCase()
          const isEligible = ['folder', 'zip', 'web'].includes(fileType)
          const inspection = docDetail?.asset_inspection
          const totalRef = inspection?.stats?.total_referenced ?? inspection?.total_referenced ?? 0
          const shouldShowModal = isEligible && Boolean(inspection && !inspection.skipped && (totalRef > 0 || inspection.user_notice))
          if (shouldShowModal) {
            set({
              justUploadedDocId: null,
              isAssetInspectionModalOpen: true,
              assetInspectionDocId: docId,
            })
          } else {
            set({ justUploadedDocId: null })
          }
        }
      } else if (status === 'error') {
        stopDocExtractionPolling()
        await get().loadDocuments()
      } else {
        if (!docExtractionPollTimer) {
          docExtractionPollTimer = setInterval(() => {
            const currentDocId = get().activeDocId
            if (currentDocId) {
              get().pollDocumentExtraction(currentDocId)
            } else {
              stopDocExtractionPolling()
            }
          }, 1200)
        }
      }
    } catch (e) {
      console.warn('Failed to poll document extraction status:', e)
    }
  },

  startChapterTranslate: async (docId?: string, chapterId?: string) => {
    const targetDocId = docId || get().activeDoc?.doc_id || get().activeDocId
    const targetChapterId = chapterId || get().activeChapterId
    if (!targetDocId || !targetChapterId) return
    try {
      const status = await api.startChapterTranslation(targetDocId, targetChapterId)
      lastCompletedParagraphsCount = status.completed
      set({ chapterBatchStatus: status, isBatchTranslating: true })
      get().pollBatchTranslateStatus(targetDocId, targetChapterId)
    } catch (e) {
      alert('启动本章批量翻译失败: ' + (e as Error).message)
    }
  },

  stopChapterTranslate: async (docId?: string, chapterId?: string) => {
    const targetDocId = docId || get().activeDoc?.doc_id || get().activeDocId
    const targetChapterId = chapterId || get().activeChapterId
    if (!targetDocId || !targetChapterId) return
    try {
      const status = await api.stopChapterTranslation(targetDocId, targetChapterId)
      set({ chapterBatchStatus: status })
      get().pollBatchTranslateStatus(targetDocId, targetChapterId)
    } catch (e) {
      alert('停止本章批量翻译失败: ' + (e as Error).message)
    }
  },

  startDocTranslate: async (docId?: string) => {
    const targetDocId = docId || get().activeDoc?.doc_id || get().activeDocId
    if (!targetDocId) return
    try {
      const status = await api.startDocumentTranslation(targetDocId)
      lastCompletedParagraphsCount = status.completed
      set({ docBatchStatus: status, isBatchTranslating: true })
      get().pollBatchTranslateStatus(targetDocId, get().activeChapterId || undefined)
    } catch (e) {
      alert('启动全篇批量翻译失败: ' + (e as Error).message)
    }
  },

  stopDocTranslate: async (docId?: string) => {
    const targetDocId = docId || get().activeDoc?.doc_id || get().activeDocId
    if (!targetDocId) return
    try {
      const status = await api.stopDocumentTranslation(targetDocId)
      set({ docBatchStatus: status })
      get().pollBatchTranslateStatus(targetDocId, get().activeChapterId || undefined)
    } catch (e) {
      alert('停止全篇批量翻译失败: ' + (e as Error).message)
    }
  },
}))
