import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { marked } from 'marked'
import {
  Send,
  Trash2,
  X,
  Bot,
  Zap,
  ChevronDown,
  Sparkles,
  Quote,
  Server,
  Bookmark,
  Check,
  Loader2,
  Copy,
  Square,
  BookOpen,
  ChevronUp,
  Eye,
  Layers,
  ArrowRight,
  RotateCcw,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import * as api from '@/api/client'
import { QuickPromptItem, ChatMessage, ParagraphItem } from '@/types'
import { ChatFlashcardWidget, splitMessageSegments } from '@/components/sidecar/ChatFlashcardWidget'

export function AssistantDrawer() {
  const {
    isAssistantOpen,
    setAssistantOpen,
    activeAssistantProvider,
    setActiveAssistantProvider,
    activeAssistantModel,
    setActiveAssistantModel,
    prevContextSteps,
    setPrevContextSteps,
    nextContextSteps,
    setNextContextSteps,
    selectedParagraph,
    setSelectedParagraph,
    chatMessages,
    setChatMessages,
    clearChatMessages,
    isChatStreaming,
    setIsChatStreaming,
    activeDoc,
    activeChapterId,
    chatFontSize,
    setChatFontSize,
    chapters,
    paragraphs,
    availableProviders,
    providersConfig,
    refreshActiveDocContent,
    updateParagraph,
    setParaExtracting,
  } = useStore()

  const [inputMessage, setInputMessage] = useState('')
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [drawerWidth, setDrawerWidth] = useState(460)
  const isResizingRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const currentAssistantMsgIdRef = useRef<string | null>(null)

  // Scope-based independent chat history state (persisted per-document across paragraph/chapter scopes)
  const [historyMap, setHistoryMap] = useState<Record<string, ChatMessage[]>>(() => {
    try {
      const stored = localStorage.getItem('ai_study_chat_history')
      return stored ? JSON.parse(stored) : {}
    } catch {
      return {}
    }
  })
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)

  // Sync historyMap to localStorage whenever updated
  useEffect(() => {
    try {
      localStorage.setItem('ai_study_chat_history', JSON.stringify(historyMap))
    } catch (e) {
      console.warn('Failed to sync chat history to localStorage:', e)
    }
  }, [historyMap])

  const [savedNoteMsgIds, setSavedNoteMsgIds] = useState<Set<string>>(new Set())
  const [savingNoteMsgId, setSavingNoteMsgId] = useState<string | null>(null)
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null)

  // Dynamic context viewer expansion toggle
  const [isContextPreviewExpanded, setIsContextPreviewExpanded] = useState(false)

  // Compact Provider | Model selector Popover state
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false)
  const [modelSearchQuery, setModelSearchQuery] = useState('')
  const [pickerSelectedProvider, setPickerSelectedProvider] = useState<string>('')
  const [customModelInput, setCustomModelInput] = useState('')
  const [providerModelsMap, setProviderModelsMap] = useState<Record<string, string[]>>({})

  // Custom quick prompts from doc settings
  const [customParagraphPrompts, setCustomParagraphPrompts] = useState<QuickPromptItem[]>([])
  const [customChapterPrompts, setCustomChapterPrompts] = useState<QuickPromptItem[]>([])

  // Load custom quick prompts from doc settings
  useEffect(() => {
    if (!activeDoc?.doc_id) return
    let isCancelled = false
    api.getDocSettings(activeDoc.doc_id).then((settings) => {
      if (isCancelled) return
      if (settings.paragraph_quick_prompts && settings.paragraph_quick_prompts.length > 0) {
        setCustomParagraphPrompts(settings.paragraph_quick_prompts)
      }
      if (settings.chapter_quick_prompts && settings.chapter_quick_prompts.length > 0) {
        setCustomChapterPrompts(settings.chapter_quick_prompts)
      }
    }).catch(() => {})
    return () => {
      isCancelled = true
    }
  }, [activeDoc?.doc_id])

  // Scope-based independent context steps state (persisted per-document across paragraph scopes)
  const [paraContextMap, setParaContextMap] = useState<Record<string, { prev: number; next: number }>>(() => {
    try {
      const stored = localStorage.getItem('ai_study_para_context_map')
      return stored ? JSON.parse(stored) : {}
    } catch {
      return {}
    }
  })

  // Sync paraContextMap to localStorage whenever updated
  useEffect(() => {
    try {
      localStorage.setItem('ai_study_para_context_map', JSON.stringify(paraContextMap))
    } catch (e) {
      console.warn('Failed to sync para context map to localStorage:', e)
    }
  }, [paraContextMap])

  // Current active chapter info
  const currentChapter = useMemo(() => {
    return chapters.find((c) => c.chapter_id === activeChapterId) || (chapters.length > 0 ? chapters[0] : null)
  }, [chapters, activeChapterId])

  // Current scope identification (Point: independent history per chapter & per paragraph)
  const docId = activeDoc?.doc_id || ''
  const chapterId = currentChapter?.chapter_id || activeChapterId || ''
  const paragraphId = selectedParagraph?.id || ''
  const isParagraphMode = Boolean(selectedParagraph)

  const scopeKey = useMemo(() => {
    if (!docId) return 'global'
    if (isParagraphMode && paragraphId) {
      return `doc_${docId}_ch_${chapterId}_para_${paragraphId}`
    }
    return `doc_${docId}_ch_${chapterId}_chapter`
  }, [docId, chapterId, paragraphId, isParagraphMode])

  const paraKey = selectedParagraph ? `para_${docId}_${chapterId}_${selectedParagraph.id}` : ''

  const currentPrevSteps = selectedParagraph && paraKey && paraContextMap[paraKey]?.prev !== undefined
    ? paraContextMap[paraKey].prev
    : 2

  const currentNextSteps = selectedParagraph && paraKey && paraContextMap[paraKey]?.next !== undefined
    ? paraContextMap[paraKey].next
    : 2

  const handleSetPrevSteps = (newVal: number) => {
    const clamped = Math.max(0, newVal)
    if (paraKey) {
      setParaContextMap((prev) => ({
        ...prev,
        [paraKey]: {
          prev: clamped,
          next: prev[paraKey]?.next ?? 2,
        },
      }))
    }
    setPrevContextSteps(clamped)
  }

  const handleSetNextSteps = (newVal: number) => {
    const clamped = Math.max(0, newVal)
    if (paraKey) {
      setParaContextMap((prev) => ({
        ...prev,
        [paraKey]: {
          prev: prev[paraKey]?.prev ?? 2,
          next: clamped,
        },
      }))
    }
    setNextContextSteps(clamped)
  }

  // Synchronize store's context steps with active paragraph
  useEffect(() => {
    if (selectedParagraph && paraKey) {
      const saved = paraContextMap[paraKey]
      setPrevContextSteps(saved?.prev ?? 2)
      setNextContextSteps(saved?.next ?? 2)
    }
  }, [selectedParagraph?.id, paraKey])

  // Context range calculation for paragraph mode (uses per-paragraph context steps)
  const { currentIdx, startIdx, endIdx, contextParagraphs } = useMemo(() => {
    if (!selectedParagraph) {
      return { currentIdx: -1, startIdx: 0, endIdx: 0, contextParagraphs: [] }
    }
    const idx = paragraphs.findIndex((p) => p.id === selectedParagraph.id)
    const validIdx = idx >= 0 ? idx : 0
    const s = Math.max(0, validIdx - currentPrevSteps)
    const e = Math.min(paragraphs.length - 1, validIdx + currentNextSteps)
    return {
      currentIdx: validIdx,
      startIdx: s,
      endIdx: e,
      contextParagraphs: paragraphs.slice(s, e + 1),
    }
  }, [selectedParagraph, paragraphs, currentPrevSteps, currentNextSteps])

  // Welcome message generator for active scope
  const getDefaultWelcomeMessage = useCallback(
    (
      scope: 'paragraph' | 'chapter',
      pIdx?: number,
      pCount?: number,
      chTitle?: string
    ): ChatMessage => {
      if (scope === 'paragraph') {
        return {
          id: `welcome-para-${pIdx ?? 0}`,
          role: 'assistant',
          content: `您好！我是您的专属段落研读助教。当前正在研读第 ${(pIdx ?? 0) + 1} 段。长难句语法辨析、专业术语溯源、前后文逻辑推演，随时向我提问！`,
          created_at: new Date().toISOString(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }
      } else {
        return {
          id: `welcome-ch-${chTitle || 'current'}`,
          role: 'assistant',
          content: `您好！我是您的全章宏观学术研读导师。当前章节《${chTitle || '全章节'}》共包含 ${pCount || 0} 个段落。欢迎就整篇架构脉络、核心论点归纳或跨段对比向我提问！`,
          created_at: new Date().toISOString(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }
      }
    },
    []
  )

  // Current active messages in the active scope
  const currentMessages = useMemo(() => {
    if (historyMap[scopeKey] && historyMap[scopeKey].length > 0) {
      return historyMap[scopeKey]
    }
    return [
      getDefaultWelcomeMessage(
        isParagraphMode ? 'paragraph' : 'chapter',
        currentIdx,
        paragraphs.length,
        currentChapter?.title
      ),
    ]
  }, [
    historyMap,
    scopeKey,
    isParagraphMode,
    currentIdx,
    paragraphs.length,
    currentChapter?.title,
    getDefaultWelcomeMessage,
  ])

  // Updater for active scope messages
  const updateCurrentScopeMessages = useCallback(
    (updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
      setHistoryMap((prev) => {
        const curList =
          prev[scopeKey] && prev[scopeKey].length > 0
            ? prev[scopeKey]
            : [
                getDefaultWelcomeMessage(
                  isParagraphMode ? 'paragraph' : 'chapter',
                  currentIdx,
                  paragraphs.length,
                  currentChapter?.title
                ),
              ]
        const nextList = typeof updater === 'function' ? updater(curList) : updater
        return { ...prev, [scopeKey]: nextList }
      })
    },
    [
      scopeKey,
      isParagraphMode,
      currentIdx,
      paragraphs.length,
      currentChapter?.title,
      getDefaultWelcomeMessage,
    ]
  )

  // Fetch persistent history from backend whenever scope changes
  useEffect(() => {
    if (!isAssistantOpen || !docId || !chapterId) return

    // If already loaded in memory, keep memory state
    if (historyMap[scopeKey]) return

    let isCancelled = false
    setIsLoadingHistory(true)

    const chatType = isParagraphMode ? 'paragraph' : 'chapter'
    api
      .getChatHistory(docId, chatType, chapterId, isParagraphMode ? paragraphId : undefined)
      .then((msgs) => {
        if (isCancelled) return
        if (Array.isArray(msgs) && msgs.length > 0) {
          const formatted: ChatMessage[] = msgs.map((m, idx) => ({
            id: `hist_${idx}_${m.timestamp || Date.now()}`,
            role: m.role || 'assistant',
            content: m.content || '',
            created_at:
              m.created_at ||
              (m.timestamp ? new Date(m.timestamp * 1000).toISOString() : new Date().toISOString()),
            timestamp: m.created_at ? m.created_at.slice(11, 16) : undefined,
          }))
          setHistoryMap((prev) => ({ ...prev, [scopeKey]: formatted }))
        } else {
          const welcome = getDefaultWelcomeMessage(
            isParagraphMode ? 'paragraph' : 'chapter',
            currentIdx,
            paragraphs.length,
            currentChapter?.title
          )
          setHistoryMap((prev) => ({ ...prev, [scopeKey]: [welcome] }))
        }
      })
      .catch((err) => {
        console.warn('Failed to load chat history:', err)
        if (!isCancelled) {
          const welcome = getDefaultWelcomeMessage(
            isParagraphMode ? 'paragraph' : 'chapter',
            currentIdx,
            paragraphs.length,
            currentChapter?.title
          )
          setHistoryMap((prev) => ({ ...prev, [scopeKey]: [welcome] }))
        }
      })
      .finally(() => {
        if (!isCancelled) setIsLoadingHistory(false)
      })

    return () => {
      isCancelled = true
    }
  }, [
    scopeKey,
    isAssistantOpen,
    docId,
    chapterId,
    paragraphId,
    isParagraphMode,
    currentIdx,
    paragraphs.length,
    currentChapter?.title,
    getDefaultWelcomeMessage,
    historyMap,
  ])

  // Fetch models for a provider and cache
  const fetchModels = async (providerId: string) => {
    if (!providerId) return []
    if (providerModelsMap[providerId]) return providerModelsMap[providerId]
    try {
      const models = await api.getProviderModels(providerId)
      setProviderModelsMap((prev) => ({ ...prev, [providerId]: models }))
      return models
    } catch (e) {
      console.warn('Failed to load models for', providerId, e)
      return []
    }
  }

  // Sync available models for the active assistant provider
  useEffect(() => {
    const p = activeAssistantProvider || 'openai_compatible'
    setPickerSelectedProvider(p)
    fetchModels(p).then((models) => {
      setAvailableModels(models)
    })
  }, [activeAssistantProvider])

  // Initialize and synchronize selected provider and model with active document settings
  useEffect(() => {
    let isCancelled = false
    const initProviderAndModels = async () => {
      let chatProvider = providersConfig?.defaults?.default_chat_provider || 'openai_compatible'
      let preferredModel = providersConfig?.defaults?.default_chat_model || ''

      if (activeDoc?.doc_id) {
        try {
          const docSettings = await api.getDocSettings(activeDoc.doc_id)
          if (docSettings.chat_provider) {
            chatProvider = docSettings.chat_provider
          } else if (docSettings.default_chat_provider) {
            chatProvider = docSettings.default_chat_provider
          }
          if (docSettings.chat_model) {
            preferredModel = docSettings.chat_model
          } else if (docSettings.default_chat_model) {
            preferredModel = docSettings.default_chat_model
          }
        } catch (e) {
          console.warn('Failed to load doc settings for chat:', e)
        }
      }

      if (isCancelled) return
      setActiveAssistantProvider(chatProvider)

      try {
        const models = await api.getProviderModels(chatProvider)
        if (!isCancelled && models.length > 0) {
          setAvailableModels(models)
          setProviderModelsMap((prev) => ({ ...prev, [chatProvider]: models }))
          const chosenModel = preferredModel && models.includes(preferredModel)
            ? preferredModel
            : (preferredModel || models[0])
          setActiveAssistantModel(chosenModel)
        } else if (!isCancelled && preferredModel) {
          setActiveAssistantModel(preferredModel)
        }
      } catch (e) {
        console.warn('Failed to load chat models:', e)
        if (!isCancelled && preferredModel) {
          setActiveAssistantModel(preferredModel)
        }
      }
    }
    initProviderAndModels()
    return () => {
      isCancelled = true
    }
  }, [activeDoc?.doc_id, providersConfig?.defaults?.default_chat_provider, providersConfig?.defaults?.default_chat_model])

  // Drag to resize drawer width
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return
      const newWidth = window.innerWidth - e.clientX
      if (newWidth >= 320 && newWidth <= window.innerWidth * 0.75) {
        setDrawerWidth(newWidth)
      }
    }
    const handleMouseUp = () => {
      isResizingRef.current = false
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  // Copy assistant response
  const handleCopyMessage = async (msgId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMsgId(msgId)
      setTimeout(() => setCopiedMsgId(null), 2000)
    } catch {
      alert('复制失败，请手动选择复制')
    }
  }

  // Save assistant response as note
  const handleSaveMessageAsNote = async (msgId: string, content: string) => {
    if (!activeDoc?.doc_id) return
    const chId = selectedParagraph?.chapter_id || activeChapterId || (currentChapter?.chapter_id || '')
    if (!chId) return

    try {
      setSavingNoteMsgId(msgId)
      if (selectedParagraph) {
        await api.addParagraphNote(activeDoc.doc_id, chId, selectedParagraph.id, content)
      } else {
        await api.saveChapterNote(activeDoc.doc_id, chId, 'header', '全章研读助教总结', content)
      }
      await refreshActiveDocContent()
      setSavedNoteMsgIds((prev) => new Set(prev).add(msgId))
    } catch (e) {
      alert('保存笔记失败: ' + (e as Error).message)
    } finally {
      setSavingNoteMsgId(null)
    }
  }

  // Quick prompt presets: paragraph vs chapter
  const defaultParagraphPrompts: QuickPromptItem[] = [
    { label: '🧐 拆解长难句', prompt: '请帮我精细拆解这一段中的长难句语法结构与修饰成分。' },
    { label: '🎯 核心论点', prompt: '请用一句话提炼本段的核心观点和学术论证逻辑。' },
    { label: '🔍 术语辨析', prompt: '请解释本段中出现的专业学术词汇，并给出具体语境含义。' },
    {
      label: '🗂️ 提炼本段闪卡',
      prompt:
        '请根据本段的核心考点和学术概念，提炼生成 1~2 张记忆闪卡（包括问答 QA 或镂空 Cloze 题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: 核心考点, 专业术语\n:::',
    },
    {
      label: '🗂️ 提炼关联范围闪卡',
      prompt:
        '请综合当前【核心研读段落】以及前文背景、后文背景所引用的全部段落，提炼出跨段落的 2~3 张关键考点记忆闪卡（包括问答 QA 或镂空 Cloze 题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: 核心考点, 关联概念\n:::',
    },
    { label: '🌐 延展背景', prompt: '这段内容在学术或工程领域有哪些典型背景和衍生讨论？' },
  ]

  const defaultChapterPrompts: QuickPromptItem[] = [
    { label: '🗺️ 全章主线脉络', prompt: '请梳理本章节的核心主线脉络、论述框架与核心逻辑。' },
    { label: '🎯 各段论点对比', prompt: '请总结本章各部分段落的核心学术论点，并对比其递进或支撑关系。' },
    {
      label: '🗂️ 提炼全章考点闪卡',
      prompt:
        '请根据本章全局核心脉络与重要考点，提炼生成 3~5 张高频复习闪卡（涵盖 QA 问答与 Cloze 镂空填空题型）。\n请务必严格使用如下格式输出每张闪卡：\n:::flashcard\ntype: qa 或 cloze\nfront: 正面考点问题或包含{{挖空词}}的语句\nback: 答案、详细解析与备考要点\ntags: 核心考点, 章节复习\n:::',
    },
    { label: '📝 考点难点总结', prompt: '请针对本章出现的关键专业学术词汇与核心考点进行系统归纳总结。' },
    { label: '💡 章首导读概述', prompt: '请用精炼有力的语言为本章撰写一段高水平的研读导读与背景概要。' },
  ]

  const activeQuickPrompts = selectedParagraph
    ? (customParagraphPrompts.length > 0 ? customParagraphPrompts : defaultParagraphPrompts)
    : (customChapterPrompts.length > 0 ? customChapterPrompts : defaultChapterPrompts)

  const isVision = (modelName: string) => {
    if (!modelName) return false
    const m = modelName.toLowerCase()
    return (
      m.includes('vision') ||
      m.includes('-vl') ||
      m.includes('vl-') ||
      m.includes('vlm') ||
      m.includes('llava') ||
      m.includes('gpt-4o') ||
      m.includes('gemini') ||
      m.includes('claude-3') ||
      m.includes('qwen-vl') ||
      m.includes('qwen2-vl') ||
      m.includes('qwen2.5-vl') ||
      m.includes('paddleocr-vl') ||
      m === 'qwen3.5-27b-v20260417'
    )
  }

  const isImageParagraph = (p?: ParagraphItem | null) => {
    if (!p) return false
    return (
      p.type === 'scanned_page' ||
      p.type === 'image' ||
      Boolean(p.image_url) ||
      Boolean(p.source_text?.includes('!['))
    )
  }

  const getCleanParagraphText = (
    p: ParagraphItem,
    isTarget: boolean,
    isVisionActive: boolean,
    currentExtracted?: string
  ) => {
    const isImg = isImageParagraph(p)
    const extText = isTarget ? (currentExtracted || p.extracted_text || '').trim() : (p.extracted_text || '').trim()

    if (!isImg) {
      return p.source_text
    }

    if (isTarget) {
      if (isVisionActive) {
        const ocrPart = extText ? `\n[图片参考识别文字]:\n${extText}` : ''
        return `(已作为视觉图像输入模型)${ocrPart}`
      } else {
        return extText || '[图片材料：暂未提取出文字内容]'
      }
    } else {
      // Surrounding background paragraph
      if (extText) {
        return `(图片识别文字):\n${extText}`
      }
      let altDesc = ''
      const match = p.source_text?.match(/!\[(.*?)\]/)
      if (match && match[1] && match[1] !== '原件材料') {
        altDesc = ` - ${match[1]}`
      }
      return `[图件/插图材料${altDesc}]`
    }
  }

  // Construct context text: Chapter mode vs Paragraph mode
  const getContextText = (isVisionActive = false, currentExtracted?: string) => {
    if (selectedParagraph) {
      // Paragraph mode: selected paragraph + steppers
      if (currentIdx === -1) {
        const text = getCleanParagraphText(selectedParagraph, true, isVisionActive, currentExtracted)
        return `[★ 核心研读段落]:\n${text}`
      }

      return paragraphs
        .slice(startIdx, endIdx + 1)
        .map((p, i) => {
          const pNum = startIdx + i + 1
          const isTarget = p.id === selectedParagraph.id
          const tag = isTarget ? `★ 核心研读段落 ${pNum}` : `背景参考段落 ${pNum}`
          const text = getCleanParagraphText(p, isTarget, isVisionActive, currentExtracted)
          return `[${tag}]:\n${text}`
        })
        .join('\n\n')
    } else {
      // Chapter mode: entire current chapter paragraphs
      const chTitle = currentChapter?.title || '当前章节'
      const fullText = paragraphs
        .map((p, i) => {
          const isImg = isImageParagraph(p)
          if (isImg) {
            if (p.extracted_text?.trim()) {
              return `[第 ${i + 1} 段 (图片提取文字)]:\n${p.extracted_text.trim()}`
            }
            let altDesc = ''
            const match = p.source_text?.match(/!\[(.*?)\]/)
            if (match && match[1] && match[1] !== '原件材料') {
              altDesc = ` - ${match[1]}`
            }
            return `[第 ${i + 1} 段: 图件/插图材料${altDesc}]`
          }
          return `[第 ${i + 1} 段]:\n${p.source_text}`
        })
        .join('\n\n')
      return `【全章研学文献】: 《${chTitle}》（全章共 ${paragraphs.length} 段）\n\n${fullText}`
    }
  }

  // Stop streaming handler
  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsChatStreaming(false)
    if (currentAssistantMsgIdRef.current) {
      const activeId = currentAssistantMsgIdRef.current
      updateCurrentScopeMessages((prev) =>
        prev.map((msg) => {
          if (msg.id === activeId) {
            return {
              ...msg,
              content: msg.content.trim()
                ? `${msg.content}\n\n*(已由用户中断)*`
                : '⚠️ 对话已由用户中止。',
            }
          }
          return msg
        })
      )
      currentAssistantMsgIdRef.current = null
    }
  }

  // Clear chat history for the active scope (both local state and backend file)
  const handleClearChatHistory = async () => {
    const welcome = getDefaultWelcomeMessage(
      isParagraphMode ? 'paragraph' : 'chapter',
      currentIdx,
      paragraphs.length,
      currentChapter?.title
    )
    const resetMsg: ChatMessage = {
      ...welcome,
      id: 'welcome-cleared-' + Date.now(),
      content: '已清空当前会话记录。随时向我提出新的疑问！',
    }
    setHistoryMap((prev) => ({ ...prev, [scopeKey]: [resetMsg] }))

    if (docId && chapterId) {
      try {
        await api.clearChatHistory(
          docId,
          isParagraphMode ? 'paragraph' : 'chapter',
          chapterId,
          isParagraphMode ? paragraphId : undefined
        )
      } catch (err) {
        console.error('Failed to clear backend chat history:', err)
      }
    }
  }

  // Delete a specific conversation turn (both user query and assistant reply) to prevent polluting model context
  const handleDeleteTurn = async (msgId: string) => {
    const targetIdx = currentMessages.findIndex((m) => m.id === msgId)
    if (targetIdx === -1) return

    const targetMsg = currentMessages[targetIdx]
    const idsToRemove = new Set<string>([msgId])

    if (targetMsg.role === 'assistant') {
      for (let i = targetIdx - 1; i >= 0; i--) {
        if (currentMessages[i].role === 'user') {
          idsToRemove.add(currentMessages[i].id)
          break
        }
      }
    } else if (targetMsg.role === 'user') {
      for (let i = targetIdx + 1; i < currentMessages.length; i++) {
        if (currentMessages[i].role === 'assistant') {
          idsToRemove.add(currentMessages[i].id)
          break
        }
      }
    }

    const updated = currentMessages.filter((m) => !idsToRemove.has(m.id))
    if (updated.length === 0 || updated.every((m) => m.id.startsWith('welcome'))) {
      const welcome = getDefaultWelcomeMessage(
        isParagraphMode ? 'paragraph' : 'chapter',
        currentIdx,
        paragraphs.length,
        currentChapter?.title
      )
      updateCurrentScopeMessages([welcome])
    } else {
      updateCurrentScopeMessages(updated)
    }

    if (docId && chapterId) {
      const activeHistoryToSave = updated
        .filter((m) => !m.id.startsWith('welcome'))
        .map((m) => ({ role: m.role, content: m.content }))
      try {
        await api.saveChatHistory(
          docId,
          isParagraphMode ? 'paragraph' : 'chapter',
          chapterId,
          activeHistoryToSave,
          isParagraphMode ? paragraphId : undefined
        )
      } catch (err) {
        console.warn('Failed to sync updated chat history to backend:', err)
      }
    }
  }

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputMessage).trim()
    if (!query || isChatStreaming) return

    setInputMessage('')

    const userMsgId = `user_${Date.now()}`
    const assistantMsgId = `asst_${Date.now()}`
    currentAssistantMsgIdRef.current = assistantMsgId

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const activeHistory = currentMessages.filter((m) => !m.id.startsWith('welcome'))

    const newMessages: ChatMessage[] = [
      ...currentMessages,
      {
        id: userMsgId,
        role: 'user',
        content: query,
        timestamp: timeStr,
        created_at: new Date().toISOString(),
      },
      {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: timeStr,
        created_at: new Date().toISOString(),
      },
    ]

    updateCurrentScopeMessages(newMessages)
    // Scroll once on sending a new message
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 50)

    abortControllerRef.current = new AbortController()

    try {
      setIsChatStreaming(true)

      const visionActive = isVision(activeAssistantModel)
      const isTargetImage = isImageParagraph(selectedParagraph)

      // Resolve target image url if present
      let targetImgUrl = selectedParagraph?.image_url || ''
      if (!targetImgUrl && selectedParagraph?.source_text?.includes('![')) {
        const match = selectedParagraph.source_text.match(/\(([^)]+)\)/)
        if (match) targetImgUrl = match[1]
      }

      // If text model & referenced paragraphs contain images without extracted text -> Auto-extract OCR first!
      let currentTargetExtracted = selectedParagraph?.extracted_text || ''
      if (!visionActive && docId && chapterId) {
        const imageParasToExtract: ParagraphItem[] = []
        if (selectedParagraph && isImageParagraph(selectedParagraph) && !selectedParagraph.extracted_text) {
          imageParasToExtract.push(selectedParagraph)
        }
        for (const cp of contextParagraphs) {
          if (
            isImageParagraph(cp) &&
            !cp.extracted_text &&
            !imageParasToExtract.some((item) => item.id === cp.id)
          ) {
            imageParasToExtract.push(cp)
          }
        }

        for (const imgP of imageParasToExtract) {
          setParaExtracting(imgP.id, true)
          try {
            const updated = await api.extractParagraphText(docId, chapterId, imgP.id)
            if (updated.extracted_text) {
              updateParagraph(imgP.id, {
                extracted_text: updated.extracted_text,
                image_url: updated.image_url || imgP.image_url,
              })
              if (selectedParagraph?.id === imgP.id) {
                currentTargetExtracted = updated.extracted_text
              }
            }
          } catch (e) {
            console.warn(`Auto OCR extraction for para ${imgP.id} failed:`, e)
          } finally {
            setParaExtracting(imgP.id, false)
          }
        }
      }

      const contextText = getContextText(visionActive, currentTargetExtracted)
      const scopeDesc = selectedParagraph
        ? `【参考上下文材料】(已带入第 ${startIdx + 1} ~ ${endIdx + 1} 段):\n${contextText}`
        : `【全章参考材料】(章节《${currentChapter?.title || '本章'}》全部 ${paragraphs.length} 段):\n${contextText}`

      const promptWithContext = contextText
        ? `${scopeDesc}\n\n【研学提问】:\n${query}`
        : query

      let userMessageContent: any = promptWithContext

      // Attach image ONLY if vision model selected and target paragraph is an image
      if (visionActive && isTargetImage && targetImgUrl) {
        const fullImgUrl = targetImgUrl.startsWith('http')
          ? targetImgUrl
          : window.location.origin + targetImgUrl
        userMessageContent = [
          {
            type: 'text',
            text: promptWithContext,
          },
          {
            type: 'image_url',
            image_url: {
              url: fullImgUrl,
            },
          },
        ]
      }

      const systemPrompt = selectedParagraph
        ? '你是一位严谨博学的学术研读助教。请根据用户提供的文献段落及前后上下文背景，深入、清晰、详尽地解答用户关于长难句、学术词汇、专业论点的疑问。格式支持规范 Markdown。'
        : `你是一位博学的全章学术研读导师。当前用户正在研读《${currentChapter?.title || '全章节'}》全篇内容。请基于提供的整章所有段落文献，从全局架构、脉络递进、核心观点和对比论证等宏观与微观角度解答疑问。格式支持规范 Markdown。`

      const payloadMessages = [
        {
          role: 'system',
          content: systemPrompt,
        },
        ...activeHistory.slice(-20).map((m) => ({
          role: m.role,
          content: m.content,
        })),
        { role: 'user', content: userMessageContent },
      ]

      const resp = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          provider: activeAssistantProvider || 'openai_compatible',
          model: activeAssistantModel || 'default',
          messages: payloadMessages,
          stream: true,
        }),
      })

      if (!resp.ok) {
        let errDetail = `HTTP ${resp.status}`
        try {
          const errJson = await resp.json()
          errDetail =
            errJson.detail ||
            errJson.error?.message ||
            errJson.error ||
            JSON.stringify(errJson)
        } catch {
          try {
            const errText = await resp.text()
            if (errText) errDetail = errText
          } catch {}
        }
        throw new Error(errDetail)
      }

      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''
      let streamHasError = false

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim()
              if (dataStr === '[DONE]') continue
              try {
                const parsed = JSON.parse(dataStr)
                if (parsed.error) {
                  const errMsg =
                    typeof parsed.error === 'string'
                      ? parsed.error
                      : parsed.error.message || JSON.stringify(parsed.error)
                  assistantContent += `\n\n⚠️ **模型服务错误**: ${errMsg}`
                  streamHasError = true
                  updateCurrentScopeMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMsgId
                        ? { ...msg, content: assistantContent }
                        : msg
                    )
                  )
                  break
                }
                const token = parsed.choices?.[0]?.delta?.content || parsed.text || ''
                assistantContent += token
                updateCurrentScopeMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: assistantContent }
                      : msg
                    )
                  )
              } catch {
                if (dataStr && !dataStr.startsWith('{')) {
                  assistantContent += dataStr
                  updateCurrentScopeMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMsgId
                        ? { ...msg, content: assistantContent }
                        : msg
                    )
                  )
                }
              }
            }
          }
          if (streamHasError) break
        }
      }

      // Check empty response after normal completion
      if (!assistantContent.trim() && !streamHasError) {
        assistantContent = '⚠️ 未能收到模型响应，请检查服务提供商连接状态或所选模型是否已正常加载。'
        updateCurrentScopeMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, content: assistantContent }
              : msg
          )
        )
      }

      // Persist conversation turn to backend if successful
      if (docId && chapterId && assistantContent.trim() && !streamHasError) {
        const toSave = [
          ...activeHistory.map((m) => ({ role: m.role, content: m.content })),
          { role: 'user', content: query },
          { role: 'assistant', content: assistantContent },
        ]
        api
          .saveChatHistory(
            docId,
            isParagraphMode ? 'paragraph' : 'chapter',
            chapterId,
            toSave,
            isParagraphMode ? paragraphId : undefined
          )
          .catch((saveErr) => {
            console.warn('Failed to persist chat history to backend:', saveErr)
          })
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        console.log('Chat generation was stopped by user.')
        updateCurrentScopeMessages((prev) =>
          prev.map((msg) => {
            if (msg.id === assistantMsgId) {
              return {
                ...msg,
                content: msg.content.trim()
                  ? `${msg.content}\n\n*(已由用户中断)*`
                  : '⚠️ 对话已由用户中止。',
              }
            }
            return msg
          })
        )
      } else {
        const errMsg = err?.message || String(err)
        updateCurrentScopeMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, content: `⚠️ 请求发生异常: ${errMsg}` }
              : msg
          )
        )
      }
    } finally {
      setIsChatStreaming(false)
      abortControllerRef.current = null
      currentAssistantMsgIdRef.current = null
    }
  }


  if (!isAssistantOpen) return null

  const currentProviderObj = availableProviders.find((p) => p.id === activeAssistantProvider)
  const providerDisplayName = currentProviderObj?.name || activeAssistantProvider || 'OpenAI 兼容'

  return (
    <aside
      className="h-full flex flex-col border-l border-border bg-card/95 backdrop-blur-md shadow-xl overflow-hidden shrink-0 relative z-20 transition-[width] duration-75 ease-out select-text"
      style={{ width: `${drawerWidth}px`, maxWidth: '75vw', minWidth: '320px' }}
    >
      {/* Resizable handle on the left edge */}
      <div
        className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-primary/50 active:bg-primary z-50 group flex items-center justify-center -translate-x-1"
        onMouseDown={(e) => {
          e.preventDefault()
          isResizingRef.current = true
        }}
        title="拖拽调整侧边栏宽度"
      >
        <div className="w-0.5 h-8 bg-muted-foreground/30 group-hover:bg-primary rounded-full transition-colors" />
      </div>

      {/* Drawer Header */}
      <div className="p-3 border-b border-border/70 flex flex-col gap-2 bg-muted/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-lg shrink-0">🤖</span>
            <div className="flex flex-col min-w-0">
              <span className="font-bold text-xs tracking-tight text-foreground flex items-center gap-1.5">
                AI 研学助教
                {selectedParagraph ? (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-primary/10 text-primary font-normal">
                    按段研学
                  </span>
                ) : (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-purple-500/10 text-purple-600 dark:text-purple-400 font-normal">
                    全章研读
                  </span>
                )}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Context steppers (only when in paragraph mode, Point 7) */}
            {selectedParagraph && (
              <div className="flex items-center text-xs bg-muted/70 border border-border/60 rounded-md px-1.5 py-0.5 gap-1">
                <span className="text-[10px] text-muted-foreground">前带</span>
                <button
                  className="px-1 hover:text-primary font-bold"
                  onClick={() => handleSetPrevSteps(currentPrevSteps - 1)}
                  title="减少前置背景段落"
                >
                  -
                </button>
                <span className="font-mono text-primary font-semibold">{currentPrevSteps}</span>
                <button
                  className="px-1 hover:text-primary font-bold"
                  onClick={() => handleSetPrevSteps(currentPrevSteps + 1)}
                  title="增加前置背景段落"
                >
                  +
                </button>
                <span className="text-[10px] text-muted-foreground ml-1">后带</span>
                <button
                  className="px-1 hover:text-primary font-bold"
                  onClick={() => handleSetNextSteps(currentNextSteps - 1)}
                  title="减少后置背景段落"
                >
                  -
                </button>
                <span className="font-mono text-primary font-semibold">{currentNextSteps}</span>
                <button
                  className="px-1 hover:text-primary font-bold"
                  onClick={() => handleSetNextSteps(currentNextSteps + 1)}
                  title="增加后置背景段落"
                >
                  +
                </button>
              </div>
            )}

            {/* Quick Chat Font Size Stepper */}
            <div className="flex items-center bg-card/80 border border-border/70 rounded-md px-1 py-0.5 text-[11px] font-mono text-muted-foreground gap-0.5 shadow-2xs">
              <button
                type="button"
                onClick={() => setChatFontSize((prev) => Math.max(12, prev - 1))}
                disabled={chatFontSize <= 12}
                className="px-1 hover:text-primary disabled:opacity-30 cursor-pointer font-bold"
                title="缩小对话字号 (A-)"
              >
                -
              </button>
              <span className="text-[10px] text-primary font-bold min-w-[24px] text-center" title="当前对话字号">
                {chatFontSize}px
              </span>
              <button
                type="button"
                onClick={() => setChatFontSize((prev) => Math.min(22, prev + 1))}
                disabled={chatFontSize >= 22}
                className="px-1 hover:text-primary disabled:opacity-30 cursor-pointer font-bold"
                title="放大对话字号 (A+)"
              >
                +
              </button>
            </div>

            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handleClearChatHistory}
              title={selectedParagraph ? '清空当前段落会话历史' : '清空本章全章会话历史'}
              className="text-muted-foreground hover:text-destructive h-7 w-7"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setAssistantOpen(false)}
              title="关闭助教"
              className="h-7 w-7"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Compact Provider | Model Selector (Point 4) */}
        <div className="flex items-center justify-between gap-2">
          <Popover open={isModelPickerOpen} onOpenChange={setIsModelPickerOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2.5 flex-1 justify-between gap-1.5 text-xs bg-card border-border/80 hover:bg-muted/60 min-w-0 shadow-2xs"
                title={`${providerDisplayName} ｜ ${activeAssistantModel || '选择模型'}`}
              >
                <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
                  <Server className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span className="font-medium text-foreground shrink-0 text-[11px]">{providerDisplayName}</span>
                  <span className="text-muted-foreground/40 shrink-0">｜</span>
                  <span className="truncate min-w-0 text-muted-foreground font-mono text-[11px] text-left">
                    {activeAssistantModel || '选择模型'}
                  </span>
                </div>
                <ChevronDown className="h-3 w-3 opacity-50 shrink-0 ml-1" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[340px] p-2 shadow-2xl border bg-popover rounded-xl" align="start">
              <div className="space-y-2">
                <div className="flex items-center justify-between pb-1.5 border-b border-border/60">
                  <span className="text-xs font-bold text-foreground">切换对话服务商与模型</span>
                  <span className="text-[10px] text-muted-foreground">点选即生效</span>
                </div>

                {/* Provider Selector Pills */}
                <div className="flex gap-1 overflow-x-auto pb-1 no-scrollbar">
                  {availableProviders.map((p) => {
                    const isSelected = p.id === pickerSelectedProvider
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={async () => {
                          setPickerSelectedProvider(p.id)
                          await fetchModels(p.id)
                        }}
                        className={`text-[11px] px-2 py-1 rounded-md shrink-0 transition-colors font-medium border ${
                          isSelected
                            ? 'bg-primary text-primary-foreground border-primary'
                            : 'bg-muted/40 text-muted-foreground hover:text-foreground border-border/60'
                        }`}
                      >
                        {p.name}
                      </button>
                    )
                  })}
                </div>

                {/* Search Filter */}
                <Input
                  value={modelSearchQuery}
                  onChange={(e) => setModelSearchQuery(e.target.value)}
                  placeholder="🔍 搜索模型..."
                  className="h-7 text-xs"
                />

                {/* Model List */}
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {(providerModelsMap[pickerSelectedProvider] || availableModels || [])
                    .filter((m) =>
                      m.toLowerCase().includes(modelSearchQuery.trim().toLowerCase())
                    )
                    .map((modelName) => {
                      const isActive =
                        activeAssistantProvider === pickerSelectedProvider &&
                        activeAssistantModel === modelName
                      return (
                        <div
                          key={modelName}
                          onClick={() => {
                            setActiveAssistantProvider(pickerSelectedProvider)
                            setActiveAssistantModel(modelName)
                            setIsModelPickerOpen(false)
                          }}
                          className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs cursor-pointer transition-colors ${
                            isActive
                              ? 'bg-primary/15 text-primary font-medium'
                              : 'hover:bg-muted text-foreground'
                          }`}
                        >
                          <span className="truncate min-w-0 flex-1 font-mono text-[11px]" title={modelName}>
                            {modelName}
                          </span>
                          {isActive && <Check className="h-3.5 w-3.5 text-primary shrink-0 ml-1.5" />}
                        </div>
                      )
                    })}
                </div>

                {/* Custom Model Input */}
                <div className="pt-2 border-t border-border/60 flex gap-1.5 items-center">
                  <Input
                    value={customModelInput}
                    onChange={(e) => setCustomModelInput(e.target.value)}
                    placeholder="或直接输入自定义模型..."
                    className="h-7 text-xs flex-1"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && customModelInput.trim()) {
                        setActiveAssistantProvider(pickerSelectedProvider)
                        setActiveAssistantModel(customModelInput.trim())
                        setIsModelPickerOpen(false)
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-7 text-xs px-2 shrink-0"
                    disabled={!customModelInput.trim()}
                    onClick={() => {
                      setActiveAssistantProvider(pickerSelectedProvider)
                      setActiveAssistantModel(customModelInput.trim())
                      setIsModelPickerOpen(false)
                    }}
                  >
                    选用
                  </Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>

          {/* Quick mode switcher if paragraph is selected */}
          {selectedParagraph && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedParagraph(null)}
              className="h-7 px-2 text-[10px] text-muted-foreground hover:text-foreground shrink-0"
              title="清除段落锁定，切换到全章研读模式"
            >
              <span>切为全章</span>
              <ArrowRight className="h-2.5 w-2.5 ml-0.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Dynamic Context Preview Area (Point 5 & Point 7) */}
      {selectedParagraph ? (
        <div className="bg-primary/5 border-b border-border/50 text-xs text-muted-foreground flex flex-col">
          <div className="p-2.5 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <Quote className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="font-semibold text-[11px] text-foreground shrink-0">
                第 {currentIdx + 1} 段研学
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-primary/10 text-primary font-mono truncate">
                带入第 {startIdx + 1} ~ {endIdx + 1} 段 ({contextParagraphs.length}段)
              </span>
            </div>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsContextPreviewExpanded(!isContextPreviewExpanded)}
              className="h-6 px-1.5 text-[10px] text-primary hover:bg-primary/10 shrink-0 gap-0.5"
            >
              <span>{isContextPreviewExpanded ? '收起' : '查看上下文'}</span>
              {isContextPreviewExpanded ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </Button>
          </div>

          {/* Dynamic Context Details Panel (Point 5) */}
          {isContextPreviewExpanded ? (
            <div className="px-3 pb-2.5 max-h-48 overflow-y-auto space-y-1.5 border-t border-border/30 pt-2">
              {contextParagraphs.map((p, i) => {
                const pNum = startIdx + i + 1
                const isCore = p.id === selectedParagraph.id
                return (
                  <div
                    key={p.id}
                    className={`p-1.5 rounded text-[11px] leading-relaxed border ${
                      isCore
                        ? 'bg-primary/15 border-primary/40 text-foreground font-medium'
                        : 'bg-card/40 border-border/30 text-muted-foreground'
                    }`}
                  >
                    <div className="flex items-center justify-between text-[10px] font-mono mb-0.5">
                      <span className={isCore ? 'text-primary font-bold' : 'text-muted-foreground'}>
                        {isCore ? `★ 第 ${pNum} 段 · 核心研学` : `# 第 ${pNum} 段 · 语境参考`}
                      </span>
                      {p.extracted_text && <span>🖼️ 图片识别</span>}
                    </div>
                    <div className="line-clamp-2">
                      {p.extracted_text
                        ? p.extracted_text
                        : isImageParagraph(p)
                        ? '🖼️ [图件材料]'
                        : p.source_text}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="px-2.5 pb-2 text-[11px] leading-relaxed line-clamp-1">
              {selectedParagraph.extracted_text
                ? `[已识别文本]: ${selectedParagraph.extracted_text}`
                : isImageParagraph(selectedParagraph)
                ? '🖼️ [图件材料]'
                : selectedParagraph.source_text}
            </div>
          )}
        </div>
      ) : (
        /* Chapter Mode Context Banner */
        <div className="p-2.5 bg-purple-500/5 border-b border-border/50 text-xs text-muted-foreground flex items-center justify-between">
          <div className="flex items-center gap-1.5 min-w-0">
            <BookOpen className="h-3.5 w-3.5 text-purple-500 shrink-0" />
            <span className="font-medium text-[11px] text-foreground truncate">
              《{currentChapter?.title || '当前章节'}》
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 shrink-0">
              全章共 {paragraphs.length} 段
            </span>
          </div>
          <span className="text-[10px] text-muted-foreground/70 shrink-0">以整章为上下文</span>
        </div>
      )}

      {/* Quick Prompts (Point 11) */}
      <div className="px-3 py-2 border-b border-border/40 flex gap-1.5 overflow-x-auto no-scrollbar">
        {activeQuickPrompts.map((item, idx) => (
          <Button
            key={idx}
            variant="outline"
            size="sm"
            className="h-6 px-2 text-[11px] shrink-0 rounded-full font-normal border-primary/20 text-muted-foreground hover:text-primary hover:border-primary"
            onClick={() => handleSendMessage(item.prompt)}
            disabled={isChatStreaming}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {/* Chat Messages Stream */}
      <ScrollArea className="flex-1 w-full min-w-0 p-4">
        {isLoadingHistory && (
          <div className="flex items-center justify-center py-2.5 mb-3 text-xs text-muted-foreground gap-1.5 bg-muted/30 border border-border/50 rounded-lg">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            <span>正在载入专属研读会话记录...</span>
          </div>
        )}
        <div className="space-y-4 w-full min-w-0">
          {currentMessages.map((msg) => {
            const isUser = msg.role === 'user'
            const isActivelyGenerating = isChatStreaming && msg.id === currentAssistantMsgIdRef.current
            return (
              <div
                key={msg.id}
                className={`group flex gap-2.5 w-full min-w-0 ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                {/* Rollback/Delete button for User message on hover */}
                {isUser && !isChatStreaming && !msg.id.startsWith('welcome') && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeleteTurn(msg.id)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity h-6 w-6 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10 self-center"
                    title="撤销并删除本轮对话（避免带入后续模型上下文）"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}

                {!isUser && (
                  <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-1">
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                )}
                <div
                  className={`rounded-2xl px-4 py-2.5 chat-dialogue-content leading-relaxed max-w-[85%] min-w-0 ${
                    isUser
                      ? 'bg-primary text-primary-foreground rounded-tr-xs shadow-xs'
                      : 'bg-muted/60 text-foreground border border-border/50 rounded-tl-xs'
                  }`}
                >
                  {msg.content ? (
                    <>
                      {isUser ? (
                        <div
                          className="chat-dialogue-content prose dark:prose-invert max-w-none break-words"
                          dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) as string }}
                        />
                      ) : (
                        <div className="space-y-3">
                          {splitMessageSegments(msg.content).map((seg, sIdx) => {
                            if (seg.type === 'markdown') {
                              return (
                                <div
                                  key={sIdx}
                                  className="chat-dialogue-content prose dark:prose-invert max-w-none break-words leading-relaxed"
                                  dangerouslySetInnerHTML={{ __html: marked.parse(seg.content) as string }}
                                />
                              )
                            }
                            return (
                              <ChatFlashcardWidget
                                key={sIdx}
                                card={seg.card}
                                docId={activeDoc?.doc_id}
                                chapterId={activeChapterId || undefined}
                                paragraphId={selectedParagraph?.id}
                                onCardAdopted={() => {
                                  refreshActiveDocContent?.()
                                }}
                              />
                            )
                          })}
                        </div>
                      )}
                      {/* Copy & Save Note & Delete Actions Row */}
                      {!isUser && (
                        <div className="flex items-center gap-2 pt-2 mt-2 border-t border-border/40">
                          {/* Copy Button */}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyMessage(msg.id, msg.content)}
                            className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground hover:bg-muted/80 rounded-md"
                            title="复制回答内容"
                          >
                            {copiedMsgId === msg.id ? (
                              <Check className="h-3 w-3 text-emerald-500" />
                            ) : (
                              <Copy className="h-3 w-3" />
                            )}
                            <span>{copiedMsgId === msg.id ? '已复制' : '复制回答'}</span>
                          </Button>

                          {/* Save Note Button */}
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={savingNoteMsgId === msg.id}
                            onClick={() => handleSaveMessageAsNote(msg.id, msg.content)}
                            className="h-6 px-2 text-[11px] gap-1 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10 rounded-md"
                            title={selectedParagraph ? '将此回答存为当前段落注解' : '将此回答存为本章总结笔记'}
                          >
                            {savingNoteMsgId === msg.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : savedNoteMsgIds.has(msg.id) ? (
                              <Check className="h-3 w-3 text-emerald-500" />
                            ) : (
                              <Bookmark className="h-3 w-3" />
                            )}
                            <span>
                              {savedNoteMsgIds.has(msg.id)
                                ? '已存为笔记'
                                : selectedParagraph
                                ? '存为段落笔记'
                                : '存为章节笔记'}
                            </span>
                          </Button>

                          {/* Rollback/Delete Turn Button */}
                          {!msg.id.startsWith('welcome') && !isChatStreaming && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteTurn(msg.id)}
                              className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md"
                              title="从历史记录中删除本轮对话，避免将此轮信息带入后续模型上下文"
                            >
                              <Trash2 className="h-3 w-3" />
                              <span>删除本轮</span>
                            </Button>
                          )}
                        </div>
                      )}
                    </>
                  ) : isActivelyGenerating ? (
                    <span className="inline-flex gap-1.5 items-center text-primary font-medium">
                      <Sparkles className="h-3.5 w-3.5 animate-spin" />
                      思考撰写中...
                    </span>
                  ) : (
                    <div className="space-y-2">
                      <span className="inline-flex gap-1.5 items-center text-destructive text-xs">
                        ⚠️ 响应为空或请求已中断
                      </span>
                      {!isChatStreaming && !msg.id.startsWith('welcome') && (
                        <div className="pt-1">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDeleteTurn(msg.id)}
                            className="h-6 px-2 text-[11px] gap-1 text-destructive border-destructive/30 hover:bg-destructive/10 rounded-md"
                            title="从历史记录中彻底删除该失败轮次"
                          >
                            <RotateCcw className="h-3 w-3" />
                            <span>撤销并移出上下文</span>
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input Area: Input and Send/Stop button horizontally centered (Point 4 & Point 8) */}
      <div className="p-3 border-t border-border/60 bg-muted/15 flex items-center gap-2">
        <Textarea
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (!isChatStreaming && inputMessage.trim()) {
                handleSendMessage()
              }
            }
          }}
          placeholder={
            selectedParagraph
              ? `针对第 ${currentIdx + 1} 段提问 (Enter 发送, Shift+Enter 换行)...`
              : '针对全章文献提问 (Enter 发送, Shift+Enter 换行)...'
          }
          className="min-h-[42px] max-h-28 text-xs resize-none flex-1 py-2 leading-relaxed"
          rows={1}
          disabled={isChatStreaming}
        />

        {isChatStreaming ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={handleStopStreaming}
            className="h-[42px] px-3.5 shrink-0 gap-1.5 shadow-sm font-medium"
            title="点击中止当前生成"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
            <span>停止</span>
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={() => handleSendMessage()}
            disabled={!inputMessage.trim()}
            className="h-[42px] px-3.5 shrink-0 gap-1.5 shadow-sm font-medium"
            title="发送提问 (Enter)"
          >
            <Send className="h-3.5 w-3.5" />
            <span>发送</span>
          </Button>
        )}
      </div>
    </aside>
  )
}
