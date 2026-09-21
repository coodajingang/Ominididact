import React, { useEffect, useRef, useState } from 'react'
import { marked } from 'marked'
import {
  Sparkles,
  Bot,
  User,
  Send,
  Trash2,
  Paperclip,
  Image as ImageIcon,
  Square,
  Copy,
  Check,
  RotateCw,
  Eye,
  Settings,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
  Sun,
  Moon,
  Zap,
  Sliders,
  X,
  Maximize2,
  FileText,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { ChatFlashcardWidget, splitMessageSegments } from '@/components/sidecar/ChatFlashcardWidget'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import * as api from '@/api/client'
import { ProviderItem } from '@/types'

interface AttachedImage {
  id: string
  name: string
  size: number
  dataUrl: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  images?: string[]
  timestamp: string
  modelTag?: string
}

export function ModelTerminalPage() {
  const {
    theme,
    setTheme,
    availableProviders,
    providersConfig,
    loadProvidersData,
    activeDoc,
    activeChapterId,
    refreshActiveDocContent,
  } = useStore()

  // Connection & model states
  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [customModel, setCustomModel] = useState<string>('')
  const [isCustomModelActive, setIsCustomModelActive] = useState<boolean>(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [isLoadingModels, setIsLoadingModels] = useState<boolean>(false)
  const [modelSearch, setModelSearch] = useState<string>('')

  // Parameters
  const [temperature, setTemperature] = useState<number>(0.7)
  const [maxTokens, setMaxTokens] = useState<string>('4096')
  const [systemPrompt, setSystemPrompt] = useState<string>(
    '你是一位博学、严谨且富有启发性的通用人工智能与多模态视觉助手。请以规范 Markdown 格式回答用户的问题，并清晰标注推理逻辑与关键论点。'
  )
  const [isParamsOpen, setIsParamsOpen] = useState<boolean>(false)

  // Chat message & streaming state
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputMessage, setInputMessage] = useState<string>('')
  const [isStreaming, setIsStreaming] = useState<boolean>(false)
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null)
  const [previewImage, setPreviewImage] = useState<string | null>(null)

  // Multimodal image attachments
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([])
  const [isDragging, setIsDragging] = useState<boolean>(false)

  // Collapsed reasoning states
  const [expandedReasoningIds, setExpandedReasoningIds] = useState<Set<string>>(new Set())

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const currentAssistantIdRef = useRef<string | null>(null)

  // Determine if active model has vision capability
  const activeModelName = isCustomModelActive && customModel.trim() ? customModel.trim() : selectedModel
  const isVisionModel = (modelName: string) => {
    if (!modelName) return false
    const m = modelName.toLowerCase()
    return (
      m.includes('vision') ||
      m.includes('-vl') ||
      m.includes('vl-') ||
      m.includes('llava') ||
      m.includes('gpt-4o') ||
      m.includes('gemini') ||
      m.includes('claude-3') ||
      m.includes('vlm')
    )
  }
  const isVisionActive = isVisionModel(activeModelName)

  // Auto scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  // Initialize providers
  useEffect(() => {
    loadProvidersData()
  }, [])

  // Set default provider and load its models
  useEffect(() => {
    if (availableProviders.length > 0 && !selectedProvider) {
      const defaultP =
        providersConfig?.defaults?.default_chat_provider ||
        providersConfig?.defaults?.default_vlm_provider ||
        availableProviders[0].id
      setSelectedProvider(defaultP)
    }
  }, [availableProviders, providersConfig, selectedProvider])

  // Load models when provider changes
  const fetchModelsForProvider = async (providerId: string, forceRefresh = false) => {
    if (!providerId) return
    setIsLoadingModels(true)
    try {
      const models = await api.getProviderModels(providerId, forceRefresh)
      setAvailableModels(models)

      // Auto select model
      const defaultM = providersConfig?.defaults?.default_chat_model
      if (defaultM && models.includes(defaultM)) {
        setSelectedModel(defaultM)
        setIsCustomModelActive(false)
      } else if (models.length > 0) {
        setSelectedModel(models[0])
        setIsCustomModelActive(false)
      } else {
        setSelectedModel('')
      }
    } catch (e) {
      console.warn('Failed to load models for provider:', providerId, e)
    } finally {
      setIsLoadingModels(false)
    }
  }

  useEffect(() => {
    if (selectedProvider) {
      fetchModelsForProvider(selectedProvider)
    }
  }, [selectedProvider])

  // Process files to Base64
  const processImageFiles = (files: FileList | File[]) => {
    Array.from(files).forEach((file) => {
      if (!file.type.startsWith('image/')) return
      const reader = new FileReader()
      reader.onload = (e) => {
        const result = e.target?.result as string
        if (result) {
          setAttachedImages((prev) => [
            ...prev,
            {
              id: `img_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
              name: file.name,
              size: file.size,
              dataUrl: result,
            },
          ])
        }
      }
      reader.readAsDataURL(file)
    })
  }

  // Handle clipboard paste (multimodal feature)
  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items
    const imageFiles: File[] = []
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile()
        if (file) imageFiles.push(file)
      }
    }
    if (imageFiles.length > 0) {
      e.preventDefault()
      processImageFiles(imageFiles)
    }
  }

  // Drag & drop image files
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }
  const handleDragLeave = () => {
    setIsDragging(false)
  }
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processImageFiles(e.dataTransfer.files)
    }
  }

  // Stop current streaming
  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsStreaming(false)
    if (currentAssistantIdRef.current) {
      const aid = currentAssistantIdRef.current
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aid
            ? {
                ...m,
                content: m.content.trim() ? `${m.content}\n\n*(已由用户中断)*` : '⚠️ 会话已由用户手动中止。',
              }
            : m
        )
      )
      currentAssistantIdRef.current = null
    }
  }

  // Clear chat history
  const handleClearHistory = () => {
    if (isStreaming) handleStopStreaming()
    setMessages([])
    setAttachedImages([])
  }

  // Copy message markdown
  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedMsgId(id)
    setTimeout(() => setCopiedMsgId(null), 2000)
  }

  // Send message
  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim()
    const images = [...attachedImages]
    if ((!text && images.length === 0) || isStreaming) return

    setInputMessage('')
    setAttachedImages([])

    const userMsgId = `user_${Date.now()}`
    const asstMsgId = `asst_${Date.now()}`
    currentAssistantIdRef.current = asstMsgId

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    // Build user message content for OpenAI format
    let userApiContent: any = text
    if (images.length > 0) {
      userApiContent = []
      if (text) {
        userApiContent.push({ type: 'text', text })
      }
      images.forEach((img) => {
        userApiContent.push({
          type: 'image_url',
          image_url: { url: img.dataUrl },
        })
      })
    }

    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: text,
        images: images.map((img) => img.dataUrl),
        timestamp: timeStr,
      },
      {
        id: asstMsgId,
        role: 'assistant',
        content: '',
        timestamp: timeStr,
        modelTag: activeModelName,
      },
    ])

    abortControllerRef.current = new AbortController()

    try {
      setIsStreaming(true)

      const payloadMessages: any[] = []
      if (systemPrompt.trim()) {
        payloadMessages.push({ role: 'system', content: systemPrompt.trim() })
      }

      // Add conversation history
      messages.forEach((m) => {
        if (m.images && m.images.length > 0) {
          const parts: any[] = []
          if (m.content) parts.push({ type: 'text', text: m.content })
          m.images.forEach((url) => parts.push({ type: 'image_url', image_url: { url } }))
          payloadMessages.push({ role: m.role, content: parts })
        } else {
          payloadMessages.push({ role: m.role, content: m.content })
        }
      })

      // Add latest user message
      payloadMessages.push({ role: 'user', content: userApiContent })

      const resp = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          provider: selectedProvider || 'openai_compatible',
          model: activeModelName || 'default',
          messages: payloadMessages,
          stream: true,
          temperature: temperature,
          max_tokens: maxTokens ? parseInt(maxTokens) : undefined,
        }),
      })

      if (!resp.ok) {
        let errDetail = `HTTP ${resp.status}`
        try {
          const errJson = await resp.json()
          errDetail = errJson.detail || errJson.error?.message || errJson.error || JSON.stringify(errJson)
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
      let asstContent = ''
      let asstReasoning = ''
      let hasStreamError = false

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
                  asstContent += `\n\n⚠️ **模型服务错误**: ${errMsg}`
                  hasStreamError = true
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === asstMsgId ? { ...m, content: asstContent, reasoning: asstReasoning } : m
                    )
                  )
                  break
                }
                const delta = parsed.choices?.[0]?.delta || {}
                if (delta.reasoning_content || delta.reasoning) {
                  asstReasoning += delta.reasoning_content || delta.reasoning
                }
                if (delta.content) {
                  asstContent += delta.content
                } else if (parsed.text) {
                  asstContent += parsed.text
                }
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === asstMsgId ? { ...m, content: asstContent, reasoning: asstReasoning } : m
                  )
                )
              } catch {
                if (dataStr && !dataStr.startsWith('{')) {
                  asstContent += dataStr
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === asstMsgId ? { ...m, content: asstContent, reasoning: asstReasoning } : m
                    )
                  )
                }
              }
            }
          }
          if (hasStreamError) break
        }
      }

      if (!asstContent.trim() && !hasStreamError) {
        asstContent = '⚠️ 未能收到模型响应，请确认服务提供商连接状态或所选模型是否已就绪。'
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstMsgId ? { ...m, content: asstContent, reasoning: asstReasoning } : m
          )
        )
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstMsgId
              ? {
                  ...m,
                  content: m.content.trim() ? `${m.content}\n\n*(已由用户中止)*` : '⚠️ 会话已由用户手动中止。',
                }
              : m
          )
        )
      } else {
        const errMsg = err?.message || String(err)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstMsgId ? { ...m, content: `⚠️ 请求异常: ${errMsg}` } : m
          )
        )
      }
    } finally {
      setIsStreaming(false)
      abortControllerRef.current = null
      currentAssistantIdRef.current = null
    }
  }

  // Toggle reasoning accordion
  const toggleReasoning = (id: string) => {
    setExpandedReasoningIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Preset quick prompt samples
  const quickTestCases = [
    {
      title: '👋 模型自我介绍',
      desc: '测试基本对话与版本',
      prompt: '请用简洁专业的中文，介绍你的模型名称、架构背景、支持的上下文长度以及你的核心优势。',
    },
    {
      title: '⚡ Python LRU 缓存',
      desc: '测试代码与算法推演',
      prompt: '请用 Python 编写一个高并发线程安全的 LRU 缓存类，支持 get/put 和过期清理，并分析时空复杂度。',
    },
    {
      title: '🔬 逻辑深度推理',
      desc: '测试复杂命题与论证',
      prompt: '“所有不鸣之鸟必有暗羽；若一羽为暗，则风息不至；现风息畅达。”请严格按命题逻辑分析能否推出“所有鸟皆鸣”？给出完整推理步骤。',
    },
    {
      title: '🖼️ 多模态看图测试',
      desc: '测试图像与视觉理解',
      prompt: '请仔细观察我上传的图片，列出画面的主要元素、排版结构、文字内容与潜在的深层信息。',
      requiresImage: true,
    },
  ]

  const filteredModels = availableModels.filter((m) =>
    m.toLowerCase().includes(modelSearch.toLowerCase())
  )

  const currentProviderObj = availableProviders.find((p) => p.id === selectedProvider)

  return (
    <div
      className="flex h-screen w-screen overflow-hidden bg-background text-foreground font-sans select-text"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Dragging overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-primary/20 backdrop-blur-xs border-4 border-dashed border-primary flex flex-col items-center justify-center pointer-events-none">
          <ImageIcon className="h-16 w-16 text-primary animate-bounce mb-3" />
          <p className="text-xl font-bold text-primary">松开鼠标即可添加图片至测试会话</p>
          <p className="text-sm text-muted-foreground mt-1">支持 PNG, JPG, WEBP, GIF 等格式</p>
        </div>
      )}

      {/* Left Sidebar: Settings & Provider/Model Picker */}
      <aside className="w-80 border-r border-border/70 bg-card/60 backdrop-blur-md flex flex-col h-full shrink-0 shadow-sm">
        {/* Header Branding */}
        <div className="p-4 border-b border-border/60 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-500 text-white flex items-center justify-center shadow-md shadow-indigo-500/20">
              <Zap className="h-4 w-4 fill-current" />
            </div>
            <div>
              <h1 className="font-bold text-sm leading-none flex items-center gap-1.5">
                模型测试终端
                <span className="text-[10px] font-normal px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                  v2.0
                </span>
              </h1>
              <p className="text-[11px] text-muted-foreground mt-0.5">多模型与多模态 VLM 交互控制台</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setTheme(theme === 'dark' ? 'white' : 'dark')}
            title="切换浅色/深色主题"
            className="h-7 w-7 text-muted-foreground"
          >
            {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </Button>
        </div>

        {/* Back Link to Study Workspace */}
        <div className="px-4 py-2 bg-muted/20 border-b border-border/40 flex items-center justify-between">
          <a
            href="/study"
            className="text-xs text-primary hover:text-primary/80 flex items-center gap-1 font-medium group transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
            <span>返回材料翻译研学中心</span>
          </a>
        </div>

        {/* Config & Controls Content */}
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-4">
            {/* Provider Section */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                <span>服务提供商 (Provider)</span>
                {currentProviderObj && (
                  <span className="flex items-center gap-1 text-[10px] text-emerald-500 font-normal">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    {currentProviderObj.is_local ? '本地' : '云端'}
                  </span>
                )}
              </label>
              <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="选择服务提供商..." />
                </SelectTrigger>
                <SelectContent>
                  {availableProviders.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-xs">
                      <div className="flex items-center justify-between w-full gap-2">
                        <span>{p.name}</span>
                        <span className="text-[10px] text-muted-foreground font-mono">({p.id})</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Model Section */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-foreground flex items-center gap-1">
                  <span>模型 (Model)</span>
                  {isVisionActive && (
                    <span className="px-1.5 py-0.2 rounded-full text-[9px] bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20 font-medium flex items-center gap-0.5">
                      <Eye className="h-2.5 w-2.5" /> 视觉 VLM
                    </span>
                  )}
                </label>
                <button
                  onClick={() => fetchModelsForProvider(selectedProvider, true)}
                  disabled={isLoadingModels}
                  className="text-[11px] text-primary hover:underline flex items-center gap-0.5 disabled:opacity-50"
                  title="重新检测刷新模型列表"
                >
                  <RotateCw className={`h-3 w-3 ${isLoadingModels ? 'animate-spin' : ''}`} />
                  刷新
                </button>
              </div>

              {!isCustomModelActive ? (
                <div className="space-y-2">
                  <Select value={selectedModel} onValueChange={setSelectedModel}>
                    <SelectTrigger className="h-9 text-xs">
                      <SelectValue placeholder={isLoadingModels ? '正在载入模型...' : '选择可用模型...'} />
                    </SelectTrigger>
                    <SelectContent>
                      <div className="p-1.5">
                        <Input
                          placeholder="搜索模型关键词..."
                          value={modelSearch}
                          onChange={(e) => setModelSearch(e.target.value)}
                          className="h-7 text-xs mb-1"
                        />
                      </div>
                      {filteredModels.length > 0 ? (
                        filteredModels.map((m) => (
                          <SelectItem key={m} value={m} className="text-xs font-mono">
                            <div className="flex items-center justify-between w-full gap-2">
                              <span className="truncate max-w-[200px]">{m}</span>
                              {isVisionModel(m) && (
                                <span className="text-[9px] text-sky-500 bg-sky-500/10 px-1 rounded">
                                  Vision
                                </span>
                              )}
                            </div>
                          </SelectItem>
                        ))
                      ) : (
                        <div className="p-2 text-center text-xs text-muted-foreground">
                          {isLoadingModels ? '加载中...' : '未检测到可用模型'}
                        </div>
                      )}
                    </SelectContent>
                  </Select>

                  <button
                    type="button"
                    onClick={() => setIsCustomModelActive(true)}
                    className="text-[11px] text-muted-foreground hover:text-primary underline text-left"
                  >
                    + 自定义手动输入模型名称
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Input
                    placeholder="输入完整模型名称 (如 qwen2.5-vl-7b)..."
                    value={customModel}
                    onChange={(e) => setCustomModel(e.target.value)}
                    className="h-9 text-xs font-mono"
                  />
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground">手动自定义输入模式</span>
                    <button
                      type="button"
                      onClick={() => setIsCustomModelActive(false)}
                      className="text-primary hover:underline"
                    >
                      返回列表选择
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Parameters Expandable */}
            <div className="pt-2 border-t border-border/50 space-y-3">
              <button
                type="button"
                onClick={() => setIsParamsOpen(!isParamsOpen)}
                className="w-full flex items-center justify-between text-xs font-semibold text-foreground py-1 hover:text-primary transition-colors"
              >
                <span className="flex items-center gap-1.5">
                  <Sliders className="h-3.5 w-3.5" />
                  推理参数与系统设定
                </span>
                {isParamsOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>

              {isParamsOpen && (
                <div className="space-y-3 bg-muted/30 p-3 rounded-lg border border-border/40 text-xs">
                  {/* Temperature */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-muted-foreground">采样温度 (Temperature)</span>
                      <span className="font-mono font-semibold text-primary">{temperature.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.05"
                      value={temperature}
                      onChange={(e) => setTemperature(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-muted-foreground/30 rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>

                  {/* Max Tokens */}
                  <div className="space-y-1">
                    <span className="text-[11px] text-muted-foreground">最大生成 Token 数</span>
                    <Input
                      type="number"
                      value={maxTokens}
                      onChange={(e) => setMaxTokens(e.target.value)}
                      placeholder="4096"
                      className="h-7 text-xs font-mono"
                    />
                  </div>

                  {/* System Prompt */}
                  <div className="space-y-1">
                    <span className="text-[11px] text-muted-foreground">系统指令 (System Prompt)</span>
                    <Textarea
                      value={systemPrompt}
                      onChange={(e) => setSystemPrompt(e.target.value)}
                      rows={3}
                      className="text-xs resize-none leading-relaxed"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </ScrollArea>

        {/* Sidebar Footer Actions */}
        <div className="p-3 border-t border-border/60 bg-muted/20 flex items-center justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleClearHistory}
            className="flex-1 text-xs gap-1 text-muted-foreground hover:text-destructive h-8"
            title="清空当前所有测试会话"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>清空会话</span>
          </Button>
          <span className="text-[10px] text-muted-foreground/80 font-mono px-2">
            {messages.length} 轮对话
          </span>
        </div>
      </aside>

      {/* Main Chat Canvas */}
      <main className="flex-1 flex flex-col h-full min-w-0 bg-background/50 relative">
        {/* Top Navbar */}
        <header className="h-14 border-b border-border/60 px-6 flex items-center justify-between bg-card/40 backdrop-blur-xs shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <span className="font-semibold text-sm truncate">
              {activeModelName || '未选定模型'}
            </span>
            <span className="text-xs text-muted-foreground/70 hidden sm:inline">|</span>
            <span className="text-xs text-muted-foreground truncate hidden sm:inline">
              提供商: {currentProviderObj?.name || selectedProvider || '默认'}
            </span>
            {isVisionActive && (
              <span className="px-2 py-0.5 rounded-full text-[11px] bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20 font-medium flex items-center gap-1">
                <Eye className="h-3 w-3" /> 支持图片多模态分析
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {isStreaming && (
              <span className="inline-flex items-center gap-1.5 text-xs text-primary font-medium bg-primary/10 px-2.5 py-1 rounded-full border border-primary/20">
                <span className="w-2 h-2 rounded-full bg-primary animate-ping" />
                正在流式推理中...
              </span>
            )}
          </div>
        </header>

        {/* Message Stream */}
        <ScrollArea className="flex-1 p-6">
          <div className="max-w-4xl mx-auto space-y-6">
            {messages.length === 0 ? (
              /* Empty Hero Showcase */
              <div className="py-12 px-4 flex flex-col items-center justify-center text-center max-w-2xl mx-auto">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-primary/20 to-purple-500/20 border border-primary/30 flex items-center justify-center text-primary mb-4 shadow-xl">
                  <Sparkles className="h-8 w-8 animate-pulse" />
                </div>
                <h2 className="text-xl font-bold tracking-tight text-foreground">
                  欢迎使用模型与多模态交互测试终端
                </h2>
                <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                  选择左侧的服务提供商与模型，测试文本对话、复杂编程推理与多模态看图能力。
                  支持直接通过剪贴板粘贴截图（Ctrl+V / ⌘+V）、文件上传或拖拽图片。
                </p>

                {/* Quick test prompt cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full mt-8 text-left">
                  {quickTestCases.map((tc, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSendMessage(tc.prompt)}
                      className="p-3.5 rounded-xl bg-card border border-border/70 hover:border-primary/50 hover:bg-muted/40 transition-all text-left group shadow-xs"
                    >
                      <div className="font-semibold text-xs text-foreground group-hover:text-primary flex items-center justify-between">
                        <span>{tc.title}</span>
                        <Send className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">{tc.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              /* Chat Message Bubbles */
              messages.map((msg) => {
                const isUser = msg.role === 'user'
                const isActivelyGenerating = isStreaming && msg.id === currentAssistantIdRef.current

                return (
                  <div
                    key={msg.id}
                    className={`flex gap-3.5 w-full ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary/20 to-indigo-500/20 text-primary border border-primary/30 flex items-center justify-center shrink-0 mt-0.5 shadow-xs">
                        <Bot className="h-4 w-4" />
                      </div>
                    )}

                    <div className={`flex flex-col gap-1.5 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
                      {/* Attached images gallery (for user message) */}
                      {msg.images && msg.images.length > 0 && (
                        <div className="flex flex-wrap gap-2 mb-1">
                          {msg.images.map((imgUrl, i) => (
                            <div
                              key={i}
                              onClick={() => setPreviewImage(imgUrl)}
                              className="relative group cursor-pointer overflow-hidden rounded-lg border border-border/80 shadow-xs max-w-[200px] max-h-[160px]"
                            >
                              <img src={imgUrl} alt="Attached" className="object-cover w-full h-full" />
                              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-xs gap-1 transition-opacity">
                                <Maximize2 className="h-3.5 w-3.5" /> 放大
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Bubble */}
                      <div
                        className={`rounded-2xl px-5 py-3 text-xs leading-relaxed shadow-xs ${
                          isUser
                            ? 'bg-primary text-primary-foreground rounded-tr-xs'
                            : 'bg-card text-foreground border border-border/60 rounded-tl-xs'
                        }`}
                      >
                        {/* Reasoning Accordion (For DeepSeek R1 / Reasoning models) */}
                        {!isUser && msg.reasoning && (
                          <div className="mb-3 border border-border/60 rounded-lg overflow-hidden bg-muted/30">
                            <button
                              type="button"
                              onClick={() => toggleReasoning(msg.id)}
                              className="w-full px-3 py-1.5 bg-muted/50 hover:bg-muted text-[11px] font-medium text-muted-foreground flex items-center justify-between transition-colors"
                            >
                              <span className="flex items-center gap-1.5 text-primary">
                                <Sparkles className="h-3 w-3" />
                                思考与推理过程 ({msg.reasoning.length} 字)
                              </span>
                              {expandedReasoningIds.has(msg.id) ? (
                                <ChevronUp className="h-3.5 w-3.5" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5" />
                              )}
                            </button>
                            {expandedReasoningIds.has(msg.id) && (
                              <div className="p-3 text-[11px] text-muted-foreground font-mono leading-relaxed border-t border-border/40 whitespace-pre-wrap max-h-60 overflow-y-auto">
                                {msg.reasoning}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Content text */}
                        {msg.content ? (
                          isUser ? (
                            <div
                              className="chat-dialogue-content prose dark:prose-invert max-w-none break-words leading-relaxed"
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
                                    onCardAdopted={() => {
                                      refreshActiveDocContent?.()
                                    }}
                                  />
                                )
                              })}
                            </div>
                          )
                        ) : isActivelyGenerating ? (
                          <span className="inline-flex gap-1.5 items-center text-primary font-medium">
                            <Sparkles className="h-3.5 w-3.5 animate-spin" />
                            模型深度推理中...
                          </span>
                        ) : (
                          <span className="inline-flex gap-1.5 items-center text-destructive text-xs">
                            ⚠️ 响应为空或请求已中断
                          </span>
                        )}
                      </div>

                      {/* Footer Info & Copy Button */}
                      {!isUser && msg.content && (
                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground px-1">
                          {msg.modelTag && <span>模型: {msg.modelTag}</span>}
                          <span>•</span>
                          <span>{msg.timestamp}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyMessage(msg.id, msg.content)}
                            className="h-5 px-1.5 text-[10px] gap-1 hover:text-foreground rounded"
                            title="复制 Markdown 原文"
                          >
                            {copiedMsgId === msg.id ? (
                              <Check className="h-3 w-3 text-emerald-500" />
                            ) : (
                              <Copy className="h-3 w-3" />
                            )}
                            <span>{copiedMsgId === msg.id ? '已复制' : '复制'}</span>
                          </Button>
                        </div>
                      )}
                    </div>

                    {isUser && (
                      <div className="w-8 h-8 rounded-full bg-muted text-muted-foreground border border-border flex items-center justify-center shrink-0 mt-0.5 shadow-xs">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                )
              })
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Bottom Input Area (Multimodal support) */}
        <div className="p-4 border-t border-border/60 bg-card/60 backdrop-blur-md shrink-0">
          <div className="max-w-4xl mx-auto space-y-2.5">
            {/* Attached Images Preview Tray */}
            {attachedImages.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 p-2 bg-muted/40 rounded-lg border border-border/50">
                <span className="text-[11px] font-medium text-muted-foreground px-1 flex items-center gap-1">
                  <ImageIcon className="h-3 w-3" /> 待发送图像 ({attachedImages.length}):
                </span>
                {attachedImages.map((img) => (
                  <div
                    key={img.id}
                    className="relative group rounded-md border border-border overflow-hidden bg-background h-14 w-14 shadow-xs"
                  >
                    <img src={img.dataUrl} alt={img.name} className="object-cover w-full h-full" />
                    <button
                      onClick={() => setAttachedImages((prev) => prev.filter((item) => item.id !== img.id))}
                      className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-black/70 hover:bg-destructive text-white flex items-center justify-center text-[10px] transition-colors"
                      title="移除此图片"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Input Row */}
            <div className="flex items-end gap-2 bg-background border border-border/80 rounded-xl p-2 shadow-sm focus-within:border-primary/70 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
              {/* Image Upload Trigger */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) processImageFiles(e.target.files)
                }}
              />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => fileInputRef.current?.click()}
                className={`h-9 w-9 shrink-0 text-muted-foreground hover:text-primary hover:bg-muted/70 rounded-lg ${
                  attachedImages.length > 0 ? 'text-primary' : ''
                }`}
                title="上传图片进行多模态测试 (支持 PNG/JPG/WEBP 等)"
              >
                <Paperclip className="h-4 w-4" />
              </Button>

              {/* Text Input */}
              <Textarea
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onPaste={handlePaste}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    if (!isStreaming && (inputMessage.trim() || attachedImages.length > 0)) {
                      handleSendMessage()
                    }
                  }
                }}
                placeholder={
                  isVisionActive
                    ? '输入测试问题，支持在此直接粘贴图片 (Ctrl+V / ⌘+V) 或点击左侧回形针上传...'
                    : '输入问题测试模型连通性与回复质量 (Enter 发送, Shift+Enter 换行)...'
                }
                className="min-h-[40px] max-h-36 text-xs resize-none flex-1 py-2 leading-relaxed border-none shadow-none focus-visible:ring-0 px-2"
                rows={1}
                disabled={isStreaming}
              />

              {/* Action Buttons: Stop / Send */}
              {isStreaming ? (
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleStopStreaming}
                  className="h-9 px-3.5 shrink-0 gap-1.5 font-medium shadow-sm"
                  title="点击中止当前流式生成"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                  <span>停止</span>
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => handleSendMessage()}
                  disabled={!inputMessage.trim() && attachedImages.length === 0}
                  className="h-9 px-3.5 shrink-0 gap-1.5 font-medium shadow-sm"
                  title="发送提问 (Enter)"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>发送</span>
                </Button>
              )}
            </div>

            {/* Hint footnote */}
            <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
              <span>💡 支持拖拽图片、截图后直接 Ctrl+V / ⌘+V 粘贴图片进行多模态视觉推理测试</span>
              <span>OpenAI Compatible API (/v1/chat/completions)</span>
            </div>
          </div>
        </div>
      </main>

      {/* Lightbox Modal for Image Preview */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-center justify-center p-4 cursor-zoom-out"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-4xl max-h-[90vh] overflow-hidden rounded-xl border border-white/20 shadow-2xl">
            <img src={previewImage} alt="Preview" className="object-contain max-h-[85vh] w-auto" />
            <button
              onClick={() => setPreviewImage(null)}
              className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/90 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
