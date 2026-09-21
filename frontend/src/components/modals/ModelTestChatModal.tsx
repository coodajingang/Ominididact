import React, { useEffect, useRef, useState } from 'react'
import { marked } from 'marked'
import {
  Sparkles,
  Bot,
  Send,
  Trash2,
  X,
  Server,
  Zap,
  RotateCw,
  Cpu,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Combobox } from '@/components/ui/combobox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import * as api from '@/api/client'

interface TestMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  timestamp: string
}

export function ModelTestChatModal() {
  const {
    isModelTestModalOpen,
    setModelTestModalOpen,
    availableProviders,
    providersConfig,
  } = useStore()

  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [isLoadingModels, setIsLoadingModels] = useState(false)
  const [inputMessage, setInputMessage] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [messages, setMessages] = useState<TestMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '欢迎使用模型测试与调试终端！请在上方选择 **服务提供商 (Provider)** 和 **模型 (Model)**，发送任意问题测试接口连通性、生成速度与推理质量。',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ])

  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Initialize selected provider
  useEffect(() => {
    if (isModelTestModalOpen && availableProviders.length > 0 && !selectedProvider) {
      const defaultP =
        providersConfig?.defaults?.default_chat_provider || availableProviders[0].id
      setSelectedProvider(defaultP)
    }
  }, [isModelTestModalOpen, availableProviders, providersConfig])

  // Load models whenever provider changes
  useEffect(() => {
    if (!selectedProvider) return
    let isCancelled = false

    const fetchModels = async () => {
      setIsLoadingModels(true)
      try {
        const models = await api.getProviderModels(selectedProvider, true)
        if (!isCancelled) {
          setAvailableModels(models)
          const defaultM = providersConfig?.defaults?.default_chat_model
          if (defaultM && models.includes(defaultM)) {
            setSelectedModel(defaultM)
          } else if (models.length > 0) {
            setSelectedModel(models[0])
          } else {
            setSelectedModel('')
          }
        }
      } catch (e) {
        console.warn('Failed to load models for test provider:', e)
      } finally {
        if (!isCancelled) setIsLoadingModels(false)
      }
    }

    fetchModels()
    return () => {
      isCancelled = true
    }
  }, [selectedProvider])

  // Auto-scroll on new message / stream
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  const quickPrompts = [
    { label: '👋 自我介绍', prompt: '请简要介绍你自己的架构背景、模型版本及核心优势。' },
    { label: '💡 相对论', prompt: '请用通俗生动且准确的一句话，向中学生解释爱因斯坦相对论的核心观点。' },
    { label: '⚡ LRU 算法', prompt: '请用 Python 实现一个高并发线程安全的 LRU 缓存类，并简要说明其复杂度。' },
    { label: '🛡️ CIA 三要素', prompt: '简要阐述信息安全领域中的机密性、完整性与可用性（CIA），并结合实际案例说明。' },
  ]

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputMessage).trim()
    if (!query || isStreaming) return

    setInputMessage('')

    const userMsgId = `user_${Date.now()}`
    const asstMsgId = `asst_${Date.now()}`

    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: query,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
      {
        id: asstMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ])

    try {
      setIsStreaming(true)

      const resp = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel || 'default',
          messages: [
            {
              role: 'system',
              content: '你是一位博学、精确且专业的通用人工智能助手。支持以规范 Markdown 格式回答。',
            },
            ...messages
              .filter((m) => m.id !== 'welcome')
              .map((m) => ({
                role: m.role,
                content: m.content,
              })),
            { role: 'user', content: query },
          ],
          stream: true,
        }),
      })

      if (!resp.ok) {
        const errText = await resp.text()
        throw new Error(`HTTP ${resp.status}: ${errText}`)
      }

      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()
      let asstContent = ''
      let asstReasoning = ''

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
                  asstContent += `\n\n> ⚠️ **错误**: ${parsed.error}`
                  break
                }
                const delta = parsed.choices?.[0]?.delta || {}
                const token = delta.content || ''
                const reasoningToken = delta.reasoning_content || delta.reasoning || ''

                if (reasoningToken) asstReasoning += reasoningToken
                if (token) asstContent += token

                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === asstMsgId
                      ? { ...msg, content: asstContent, reasoning: asstReasoning }
                      : msg
                  )
                )
              } catch {
                asstContent += dataStr
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === asstMsgId ? { ...msg, content: asstContent } : msg
                  )
                )
              }
            }
          }
        }
      }
    } catch (e: any) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === asstMsgId
            ? { ...msg, content: `❌ **请求失败**: ${e.message || '未知错误'}` }
            : msg
        )
      )
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <Dialog open={isModelTestModalOpen} onOpenChange={setModelTestModalOpen}>
      <DialogContent className="max-w-3xl h-[88vh] max-h-[88vh] flex flex-col p-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="px-6 pt-4 pb-3 border-b border-border/60 shrink-0">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2 text-base font-bold">
              <Sparkles className="h-4 w-4 text-primary" />
              <span>🧪 模型测试与调试终端 (Model Test & Debugging Chat)</span>
            </DialogTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive gap-1"
                onClick={() =>
                  setMessages([
                    {
                      id: 'welcome-' + Date.now(),
                      role: 'assistant',
                      content: '对话记录已清空，随时发送新问题进行测试。',
                      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    },
                  ])
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>清空</span>
              </Button>
            </div>
          </div>

          {/* Provider & Model Dual Selectors */}
          <div className="flex items-center gap-3 pt-3 flex-wrap">
            {/* Provider Selector */}
            <div className="flex items-center gap-1.5 bg-muted/50 border border-border/80 rounded-md px-2.5 py-1">
              <Server className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="text-[11px] font-medium text-muted-foreground shrink-0">提供商:</span>
              <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                <SelectTrigger className="h-6 border-none bg-transparent shadow-none px-1 text-xs w-[170px]">
                  <SelectValue placeholder="选择服务商..." />
                </SelectTrigger>
                <SelectContent>
                  {availableProviders.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-xs">
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Model Selector */}
            <div className="flex items-center gap-1.5 bg-muted/50 border border-border/80 rounded-md px-2.5 py-1 flex-1 min-w-[240px]">
              <Zap className="h-3.5 w-3.5 text-amber-500 shrink-0" />
              <span className="text-[11px] font-medium text-muted-foreground shrink-0">测试模型:</span>
              <Combobox
                value={selectedModel}
                onChange={setSelectedModel}
                options={availableModels}
                placeholder={isLoadingModels ? '正在拉取模型...' : '选择或输入模型...'}
                className="h-6 border-none bg-transparent shadow-none px-1 text-xs flex-1"
              />
              {isLoadingModels && <RotateCw className="h-3 w-3 animate-spin text-muted-foreground" />}
            </div>
          </div>
        </DialogHeader>

        {/* Quick Prompts Bar */}
        <div className="px-6 py-2 border-b border-border/40 bg-muted/20 flex gap-2 overflow-x-auto no-scrollbar shrink-0">
          {quickPrompts.map((item, idx) => (
            <Button
              key={idx}
              variant="outline"
              size="sm"
              className="h-6 px-2.5 text-[11px] shrink-0 rounded-full font-normal border-primary/20 hover:border-primary text-muted-foreground hover:text-primary"
              onClick={() => handleSendMessage(item.prompt)}
              disabled={isStreaming}
            >
              {item.label}
            </Button>
          ))}
        </div>

        {/* Messages Stream Area */}
        <ScrollArea className="flex-1 p-6">
          <div className="space-y-4 max-w-2xl mx-auto">
            {messages.map((msg) => {
              const isUser = msg.role === 'user'
              return (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className="w-7 h-7 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}
                  <div
                    className={`rounded-2xl px-4 py-2.5 text-xs leading-relaxed max-w-[85%] ${
                      isUser
                        ? 'bg-primary text-primary-foreground rounded-tr-xs shadow-xs'
                        : 'bg-muted/60 text-foreground border border-border/60 rounded-tl-xs'
                    }`}
                  >
                    {/* Deep Thinking reasoning display */}
                    {msg.reasoning && (
                      <details className="mb-2 p-2 rounded bg-background/50 border border-border/40 text-[11px] text-muted-foreground leading-normal" open>
                        <summary className="cursor-pointer font-medium text-primary hover:underline flex items-center gap-1 mb-1">
                          <Cpu className="h-3 w-3" />
                          <span>思维链推理过程 (Thinking)</span>
                        </summary>
                        <div className="whitespace-pre-wrap font-mono text-[10px] pl-2 border-l border-primary/30">
                          {msg.reasoning}
                        </div>
                      </details>
                    )}

                    {msg.content ? (
                      <div
                        className="chat-dialogue-content prose dark:prose-invert max-w-none break-words"
                        dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) as string }}
                      />
                    ) : (
                      <span className="inline-flex gap-1.5 items-center text-primary">
                        <Sparkles className="h-3.5 w-3.5 animate-spin" />
                        思考生成中...
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Bar */}
        <div className="p-4 border-t border-border/60 bg-card shrink-0">
          <div className="max-w-2xl mx-auto flex gap-2 items-end">
            <Textarea
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSendMessage()
                }
              }}
              placeholder={`向 [${selectedProvider || '未选择'} / ${selectedModel || '未选择'}] 提问测试... (Enter 发送, Shift+Enter 换行)`}
              rows={2}
              className="resize-none text-xs min-h-[50px] max-h-[120px]"
            />
            <Button
              size="sm"
              onClick={() => handleSendMessage()}
              disabled={isStreaming || !inputMessage.trim()}
              className="h-9 px-4 gap-1.5 shrink-0"
            >
              <Send className="h-3.5 w-3.5" />
              <span>发送</span>
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
