import React, { useEffect, useState } from 'react'
import {
  Settings,
  ExternalLink,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
  Server,
  Sparkles,
  Palette,
  Type,
  Minus,
  Plus,
  MessageSquare,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Combobox } from '@/components/ui/combobox'
import { ScrollArea } from '@/components/ui/scroll-area'
import * as api from '@/api/client'
import { ProvidersConfig, ThemeMode, FontFamilyMode } from '@/types'

const THEMES: { id: ThemeMode; label: string; icon: string; bg: string; border: string; text: string; ringColor: string }[] = [
  { id: 'dark', label: '深邃夜色', icon: '🌙', bg: 'bg-[#18181b]', border: 'border-zinc-700', text: 'text-zinc-100', ringColor: 'ring-blue-500' },
  { id: 'white', label: '纯净雅白', icon: '☀️', bg: 'bg-[#ffffff]', border: 'border-zinc-300', text: 'text-zinc-900', ringColor: 'ring-blue-500' },
  { id: 'sepia', label: '墨玉羊皮', icon: '📜', bg: 'bg-[#f6f1e5]', border: 'border-[#d8ccb4]', text: 'text-[#4e3b26]', ringColor: 'ring-amber-600' },
  { id: 'forest', label: '雅致墨绿', icon: '🍵', bg: 'bg-[#1b2620]', border: 'border-[#2d4035]', text: 'text-[#cfe0d5]', ringColor: 'ring-emerald-500' },
]

const FONTS: {
  id: FontFamilyMode
  label: string
  icon: string
  desc: string
  sample: string
  fontFamilyPreview: string
}[] = [
  {
    id: 'sans',
    label: '现代黑体 (Inter + 思源黑体)',
    icon: '✨',
    desc: '清晰利落，高屏幕辨识度，现代科技文献与双语对照首选',
    sample: 'The quick brown fox • 敏捷的棕色狐狸',
    fontFamilyPreview: "'Inter', 'Noto Sans SC', sans-serif",
  },
  {
    id: 'wenkai',
    label: '霞鹜文楷 (Lora + 霞鹜文楷屏幕版)',
    icon: '📖',
    desc: '典雅文人书卷感，字形温润舒展，长文沉浸研读舒适不伤眼',
    sample: 'Serendipity & Wisdom • 落霞与孤鹜齐飞',
    fontFamilyPreview: "'Lora', 'LXGW WenKai Screen', serif",
  },
  {
    id: 'serif',
    label: '沉浸宋体 (Lora + 经典宋体)',
    icon: '📜',
    desc: '学术典籍出版物排版风格，古雅庄重，印刷油墨质感',
    sample: 'Scholarship & Inquiry • 博学而笃志，切问而近思',
    fontFamilyPreview: "'Lora', 'Songti SC', 'Source Han Serif SC', serif",
  },
  {
    id: 'system',
    label: '系统原生 (System Default)',
    icon: '⚡',
    desc: '直接调用操作系统原生字体（苹方/微软雅黑），零资源开销最快响应',
    sample: 'Native Typography • 原生流畅排版体验',
    fontFamilyPreview: "-apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif",
  },
]

export function ProviderSettingsModal() {
  const {
    isProviderModalOpen,
    setProviderModalOpen,
    setModelTestModalOpen,
    availableProviders,
    providersConfig,
    loadProvidersData,
    theme,
    setTheme,
    fontFamily,
    setFontFamily,
    chatFontSize,
    setChatFontSize,
  } = useStore()

  const [activeTab, setActiveTab] = useState('openai')
  const [config, setConfig] = useState<ProvidersConfig | null>(null)
  const [modelsCache, setModelsCache] = useState<Record<string, string[]>>({})
  const [testStatus, setTestStatus] = useState<Record<string, { loading: boolean; success?: boolean; message?: string }>>({})
  const [isSaving, setIsSaving] = useState(false)

  // Initialize config from store
  useEffect(() => {
    if (providersConfig) {
      setConfig(JSON.parse(JSON.stringify(providersConfig)))
    }
  }, [providersConfig])

  // Fetch models for a given provider
  const fetchModelsForProvider = async (pId: string, force = false) => {
    if (!pId) return []
    if (!force && modelsCache[pId] && modelsCache[pId].length > 0) {
      return modelsCache[pId]
    }
    try {
      const models = await api.getProviderModels(pId, force)
      setModelsCache((prev) => ({ ...prev, [pId]: models }))
      return models
    } catch {
      return []
    }
  }

  // When modal opens, prefetch models for default providers
  useEffect(() => {
    if (isProviderModalOpen && config?.defaults) {
      if (config.defaults.default_translation_provider) fetchModelsForProvider(config.defaults.default_translation_provider)
      if (config.defaults.default_chat_provider) fetchModelsForProvider(config.defaults.default_chat_provider)
      if (config.defaults.default_vlm_provider) fetchModelsForProvider(config.defaults.default_vlm_provider)
    }
  }, [isProviderModalOpen, config?.defaults])

  if (!config) return null

  const handleTestProvider = async (providerType: string, payload: any) => {
    setTestStatus((prev) => ({
      ...prev,
      [providerType]: { loading: true },
    }))

    try {
      const res = await api.testProviderConnection({ provider: providerType, ...payload })
      setTestStatus((prev) => ({
        ...prev,
        [providerType]: {
          loading: false,
          success: res.connected,
          message: res.connected
            ? `✅ ${res.message || '连接成功！'} (${res.models?.length || 0}个模型: ${res.models?.slice(0, 4).join(', ') || ''})`
            : `❌ ${res.message || '连接失败'}`,
        },
      }))
      if (res.connected && res.models?.length) {
        setModelsCache((prev) => ({ ...prev, [providerType]: res.models }))
      }
    } catch (err) {
      setTestStatus((prev) => ({
        ...prev,
        [providerType]: {
          loading: false,
          success: false,
          message: `❌ 请求异常: ${(err as Error).message}`,
        },
      }))
    }
  }

  const handleSave = async () => {
    try {
      setIsSaving(true)
      await api.saveProvidersConfig(config)
      await loadProvidersData()
      setProviderModalOpen(false)
    } catch (e) {
      alert('保存失败: ' + (e as Error).message)
    } finally {
      setIsSaving(false)
    }
  }

  const pOpenAI = config.providers.openai_compatible || {}
  const pOllama = config.providers.ollama || {}
  const pLM = config.providers.lm_studio || {}
  const pNvidia = config.providers.nvidia || {}
  const pAmd = config.providers.amd || {}
  const pCf = config.providers.cloudflare || {}
  const pCustom = (config.providers as Record<string, any>)?.custom_gateway || {}

  const hasCustomGateway = availableProviders.some((p) => p.id === 'custom_gateway')

  return (
    <Dialog open={isProviderModalOpen} onOpenChange={setProviderModalOpen}>
      <DialogContent className="max-w-2xl h-[88vh] max-h-[88vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60 shrink-0">
          <DialogTitle className="flex items-center gap-2 text-base font-bold">
            <Settings className="h-5 w-5 text-primary" />
            <span>设置</span>
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-6 py-4 space-y-5">
          {/* Section 0: Reading Theme Preferences */}
          <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <Palette className="h-4 w-4 text-primary" />
                <span>🎨 阅读界面主题 (Theme)</span>
              </h3>
              <span className="text-[11px] text-primary font-semibold">
                当前: {THEMES.find((t) => t.id === theme)?.label}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              切换双语研学页面的配色风格，设置将即时生效并持久保存。
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
              {THEMES.map((t) => {
                const isSelected = theme === t.id
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTheme(t.id)}
                    className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg border transition-all text-center cursor-pointer ${t.bg} ${t.border} ${
                      isSelected
                        ? `ring-2 ${t.ringColor} ring-offset-2 ring-offset-background shadow-xs font-semibold scale-[1.02]`
                        : 'opacity-70 hover:opacity-100 hover:scale-[1.01]'
                    }`}
                    title={t.label}
                  >
                    <span className="text-base leading-none">{t.icon}</span>
                    <span className={`text-xs leading-tight font-medium ${t.text}`}>
                      {t.label}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Section 0.5: Reading Font Preferences */}
          <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <Type className="h-4 w-4 text-primary" />
                <span>🔤 阅读字体设置 (Font Family)</span>
              </h3>
              <span className="text-[11px] text-primary font-semibold">
                当前: {FONTS.find((f) => f.id === fontFamily)?.label}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              为双语研读和全文页面挑选最舒适的字体搭配。所有字体均已内置离线静态资源，内网环境下极速加载。
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
              {FONTS.map((f) => {
                const isSelected = fontFamily === f.id
                return (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFontFamily(f.id)}
                    className={`flex flex-col items-start gap-1.5 p-3 rounded-lg border transition-all cursor-pointer text-left ${
                      isSelected
                        ? 'bg-primary/10 border-primary ring-2 ring-primary/40 shadow-xs'
                        : 'bg-card/60 border-border/70 hover:bg-card hover:border-border'
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                        <span>{f.icon}</span>
                        <span>{f.label}</span>
                      </span>
                      {isSelected && (
                        <span className="text-[10px] bg-primary text-primary-foreground font-bold px-1.5 py-0.5 rounded-full">
                          生效中
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground line-clamp-1">
                      {f.desc}
                    </span>
                    <div
                      className="text-xs text-foreground/90 mt-0.5 px-2.5 py-1 rounded bg-background/60 border border-border/40 w-full"
                      style={{ fontFamily: f.fontFamilyPreview }}
                    >
                      {f.sample}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Section 0.6: Chat Dialogue Font Size */}
          <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-3.5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <MessageSquare className="h-4 w-4 text-primary" />
                <span>💬 对话消息字号 (Chat Message Font Size)</span>
              </h3>
              <span className="text-[11px] text-primary font-semibold">
                当前: {chatFontSize}px
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              调节 AI 助教、模型终端及闪卡对话中交流消息的正文字号。按钮、模型标签与上下文等界面元素保持原生紧凑，不影响排版。
            </p>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1">
              {/* Stepper controls */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground whitespace-nowrap">微调字号:</span>
                <div className="flex items-center bg-card border border-border/80 rounded-lg p-0.5 shadow-2xs">
                  <button
                    type="button"
                    onClick={() => setChatFontSize(Math.max(12, chatFontSize - 1))}
                    disabled={chatFontSize <= 12}
                    className="h-7 w-7 rounded flex items-center justify-center text-xs hover:bg-muted text-foreground disabled:opacity-30 transition-colors cursor-pointer"
                    title="缩小字号 (A-)"
                  >
                    <Minus className="h-3.5 w-3.5" />
                  </button>
                  <span className="text-xs font-mono font-bold px-2.5 min-w-[44px] text-center text-foreground">
                    {chatFontSize}px
                  </span>
                  <button
                    type="button"
                    onClick={() => setChatFontSize(Math.min(22, chatFontSize + 1))}
                    disabled={chatFontSize >= 22}
                    className="h-7 w-7 rounded flex items-center justify-center text-xs hover:bg-muted text-foreground disabled:opacity-30 transition-colors cursor-pointer"
                    title="放大字号 (A+)"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Preset buttons */}
              <div className="flex items-center gap-1.5 flex-wrap">
                {(
                  [
                    { size: 13, label: '小 13px' },
                    { size: 14, label: '默认 14px' },
                    { size: 15, label: '舒适 15px' },
                    { size: 16, label: '大号 16px' },
                    { size: 18, label: '超大 18px' },
                  ] as const
                ).map((preset) => (
                  <button
                    key={preset.size}
                    type="button"
                    onClick={() => setChatFontSize(preset.size)}
                    className={`px-2.5 py-1 text-xs rounded-md border font-medium transition-all cursor-pointer ${
                      chatFontSize === preset.size
                        ? 'bg-primary text-primary-foreground border-primary shadow-xs font-semibold'
                        : 'bg-card/70 border-border/70 text-muted-foreground hover:text-foreground hover:bg-muted'
                    }`}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Live Chat Preview snippet */}
            <div className="mt-2 p-3 rounded-lg bg-background/60 border border-border/50 space-y-2">
              <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                实时效果预览 (Live Preview)
              </div>
              <div className="flex flex-col gap-2">
                {/* Assistant bubble simulation */}
                <div className="flex items-start gap-2 max-w-[92%]">
                  <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 text-[10px]">
                    🤖
                  </div>
                  <div className="bg-muted/60 text-foreground border border-border/50 rounded-xl rounded-tl-xs px-3 py-2 shadow-2xs">
                    <p
                      className="chat-dialogue-content leading-relaxed"
                      style={{ fontSize: `${chatFontSize}px` }}
                    >
                      AI 助教解析：这里展示的是实际对话消息的正文内容。字号调节将只影响这里的对话讨论和闪卡问答文本，不会撑大其他操作按钮。
                    </p>
                  </div>
                </div>

                {/* Flashcard snippet simulation */}
                <div className="ml-7 bg-indigo-500/5 border border-indigo-500/20 rounded-lg p-2.5 space-y-1">
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span className="font-semibold text-indigo-600 dark:text-indigo-400">📖 闪卡问答 (Flashcard)</span>
                    <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-500 font-mono text-[10px]">#术语</span>
                  </div>
                  <div
                    className="chat-dialogue-content text-foreground bg-background/50 p-2 rounded border border-border/30"
                    style={{ fontSize: `${chatFontSize}px` }}
                  >
                    Q: What is the main distinction?
                    <br />
                    A: 这一部分的解析与记忆考点字体亦会随之同步舒适缩放。
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div>
            {/* Section 1: Global Default Models */}
            <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-4">
              <div>
                <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  🎯 全局默认模型设置 (Default Models)
                </h3>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  为翻译、文献研学助教、多模态 OCR 指定全局生效的默认 Provider 与模型。
                </p>
              </div>

              {/* Translation Model */}
              <div className="grid grid-cols-1 sm:grid-cols-[180px_minmax(0,1fr)] gap-3 items-center min-w-0">
                <div className="space-y-1 min-w-0">
                  <label className="text-[11px] font-medium text-muted-foreground">默认翻译 Provider</label>
                  <Select
                    value={config.defaults.default_translation_provider}
                    onValueChange={(val) => {
                      setConfig((prev) => ({
                        ...prev!,
                        defaults: { ...prev!.defaults, default_translation_provider: val },
                      }))
                      fetchModelsForProvider(val)
                    }}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="选择 Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableProviders.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-0 w-full overflow-hidden">
                  <label className="text-[11px] font-medium text-muted-foreground">默认翻译模型 (Model)</label>
                  <Combobox
                    value={config.defaults.default_translation_model}
                    onChange={(val) =>
                      setConfig((prev) => ({
                        ...prev!,
                        defaults: { ...prev!.defaults, default_translation_model: val },
                      }))
                    }
                    options={modelsCache[config.defaults.default_translation_provider] || []}
                    placeholder="选择或输入翻译模型..."
                  />
                </div>
              </div>

              {/* Assistant Chat Model */}
              <div className="grid grid-cols-1 sm:grid-cols-[180px_minmax(0,1fr)] gap-3 items-center min-w-0">
                <div className="space-y-1 min-w-0">
                  <label className="text-[11px] font-medium text-muted-foreground">默认助教聊天 Provider</label>
                  <Select
                    value={config.defaults.default_chat_provider}
                    onValueChange={(val) => {
                      setConfig((prev) => ({
                        ...prev!,
                        defaults: { ...prev!.defaults, default_chat_provider: val },
                      }))
                      fetchModelsForProvider(val)
                    }}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="选择 Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableProviders.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-0 w-full overflow-hidden">
                  <label className="text-[11px] font-medium text-muted-foreground">默认助教聊天模型 (Model)</label>
                  <Combobox
                    value={config.defaults.default_chat_model}
                    onChange={(val) =>
                      setConfig((prev) => ({
                        ...prev!,
                        defaults: { ...prev!.defaults, default_chat_model: val },
                      }))
                    }
                    options={modelsCache[config.defaults.default_chat_provider] || []}
                    placeholder="选择或输入助教聊天模型..."
                  />
                </div>
              </div>

              {/* VLM Model */}
              <div className="grid grid-cols-1 sm:grid-cols-[180px_minmax(0,1fr)] gap-3 items-center min-w-0">
                <div className="space-y-1 min-w-0">
                  <label className="text-[11px] font-medium text-muted-foreground">默认多模态 / OCR Provider</label>
                  <Select
                    value={config.defaults.default_vlm_provider}
                    onValueChange={(val) => {
                      setConfig((prev) => ({
                        ...prev!,
                        defaults: { ...prev!.defaults, default_vlm_provider: val },
                      }))
                      fetchModelsForProvider(val)
                    }}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="选择 Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableProviders.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-0 w-full overflow-hidden">
                  <label className="text-[11px] font-medium text-muted-foreground">默认多模态模型 (Model)</label>
                  <Combobox
                    value={config.defaults.default_vlm_model}
                    onChange={(val) =>
                      setConfig((prev) => ({
                        ...prev!,
                        defaults: { ...prev!.defaults, default_vlm_model: val },
                      }))
                    }
                    options={modelsCache[config.defaults.default_vlm_provider] || []}
                    placeholder="选择或输入多模态模型..."
                  />
                </div>
              </div>
            </div>

            {/* Section 2: Provider Details Config */}
            <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-4">
              <div>
                <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  🔌 Provider 服务参数与连通性配置
                </h3>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  配置各后端大模型服务的 API 地址与凭据，支持一键连通性测试。
                </p>
              </div>

              {/* Provider Tabs */}
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="flex flex-wrap h-auto p-1 gap-1 justify-start bg-muted/40">
                  <TabsTrigger value="openai" className="text-xs">🌐 OpenAI 兼容</TabsTrigger>
                  <TabsTrigger value="ollama" className="text-xs">🦙 Ollama</TabsTrigger>
                  <TabsTrigger value="lmstudio" className="text-xs">🟢 LM Studio</TabsTrigger>
                  <TabsTrigger value="nvidia" className="text-xs">⚡ NVIDIA NIM</TabsTrigger>
                  <TabsTrigger value="amd" className="text-xs">🔴 AMD AI</TabsTrigger>
                  <TabsTrigger value="cloudflare" className="text-xs">⛅ Cloudflare</TabsTrigger>
                  {hasCustomGateway && <TabsTrigger value="custom_gateway" className="text-xs">🧩 自定义网关</TabsTrigger>}
                </TabsList>

                {/* OpenAI Compatible */}
                <TabsContent value="openai" className="space-y-3 pt-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">API Base URL</label>
                    <Input
                      value={pOpenAI.base_url || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            openai_compatible: { ...pOpenAI, base_url: e.target.value },
                          },
                        }))
                      }
                      placeholder="https://api.deepseek.com/v1 或 https://openrouter.ai/api/v1"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">API Key</label>
                    <Input
                      type="password"
                      value={pOpenAI.api_key || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            openai_compatible: { ...pOpenAI, api_key: e.target.value },
                          },
                        }))
                      }
                      placeholder="sk-..."
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">推荐默认模型</label>
                    <Input
                      value={pOpenAI.model || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            openai_compatible: { ...pOpenAI, model: e.target.value },
                          },
                        }))
                      }
                      placeholder="deepseek-chat"
                    />
                  </div>
                  <div className="pt-1 flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleTestProvider('openai_compatible', {
                          base_url: pOpenAI.base_url,
                          api_key: pOpenAI.api_key,
                          model: pOpenAI.model,
                        })
                      }
                      disabled={testStatus.openai_compatible?.loading}
                      className="text-xs gap-1.5"
                    >
                      {testStatus.openai_compatible?.loading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span>测试连通性并拉取最新模型</span>
                    </Button>
                    {testStatus.openai_compatible?.message && (
                      <span className="text-xs text-muted-foreground">{testStatus.openai_compatible.message}</span>
                    )}
                  </div>
                </TabsContent>

                {/* Ollama */}
                <TabsContent value="ollama" className="space-y-3 pt-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">Ollama 服务地址</label>
                    <Input
                      value={pOllama.base_url || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            ollama: { ...pOllama, base_url: e.target.value },
                          },
                        }))
                      }
                      placeholder="http://127.0.0.1:11434"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">推荐模型</label>
                    <Input
                      value={pOllama.model || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            ollama: { ...pOllama, model: e.target.value },
                          },
                        }))
                      }
                      placeholder="qwen2.5:7b"
                    />
                  </div>
                  <div className="pt-1 flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleTestProvider('ollama', {
                          base_url: pOllama.base_url,
                          model: pOllama.model,
                        })
                      }
                      disabled={testStatus.ollama?.loading}
                      className="text-xs gap-1.5"
                    >
                      {testStatus.ollama?.loading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span>测试 Ollama 连通性</span>
                    </Button>
                    {testStatus.ollama?.message && (
                      <span className="text-xs text-muted-foreground">{testStatus.ollama.message}</span>
                    )}
                  </div>
                </TabsContent>

                {/* LM Studio */}
                <TabsContent value="lmstudio" className="space-y-3 pt-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">LM Studio 地址</label>
                    <Input
                      value={pLM.base_url || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            lm_studio: { ...pLM, base_url: e.target.value },
                          },
                        }))
                      }
                      placeholder="http://127.0.0.1:1234/v1"
                    />
                  </div>
                  <div className="pt-1 flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleTestProvider('lm_studio', {
                          base_url: pLM.base_url,
                          model: pLM.model,
                        })
                      }
                      disabled={testStatus.lm_studio?.loading}
                      className="text-xs gap-1.5"
                    >
                      {testStatus.lm_studio?.loading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span>测试 LM Studio 连通性</span>
                    </Button>
                    {testStatus.lm_studio?.message && (
                      <span className="text-xs text-muted-foreground">{testStatus.lm_studio.message}</span>
                    )}
                  </div>
                </TabsContent>

                {/* NVIDIA NIM */}
                <TabsContent value="nvidia" className="space-y-3 pt-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">NVIDIA API Base URL</label>
                    <Input
                      value={pNvidia.base_url || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            nvidia: { ...pNvidia, base_url: e.target.value },
                          },
                        }))
                      }
                      placeholder="https://integrate.api.nvidia.com/v1"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">API Key (nvapi-...)</label>
                    <Input
                      type="password"
                      value={pNvidia.api_key || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            nvidia: { ...pNvidia, api_key: e.target.value },
                          },
                        }))
                      }
                      placeholder="nvapi-..."
                    />
                  </div>
                  <div className="pt-1 flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleTestProvider('nvidia', {
                          base_url: pNvidia.base_url,
                          api_key: pNvidia.api_key,
                          model: pNvidia.model,
                        })
                      }
                      disabled={testStatus.nvidia?.loading}
                      className="text-xs gap-1.5"
                    >
                      {testStatus.nvidia?.loading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span>测试 NVIDIA 连通性</span>
                    </Button>
                    {testStatus.nvidia?.message && (
                      <span className="text-xs text-muted-foreground">{testStatus.nvidia.message}</span>
                    )}
                  </div>
                </TabsContent>

                {/* AMD */}
                <TabsContent value="amd" className="space-y-3 pt-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">AMD ROCm / vLLM 端点地址</label>
                    <Input
                      value={pAmd.base_url || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            amd: { ...pAmd, base_url: e.target.value },
                          },
                        }))
                      }
                      placeholder="http://127.0.0.1:8000/v1"
                    />
                  </div>
                  <div className="pt-1 flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleTestProvider('amd', {
                          base_url: pAmd.base_url,
                          api_key: pAmd.api_key,
                          model: pAmd.model,
                        })
                      }
                      disabled={testStatus.amd?.loading}
                      className="text-xs gap-1.5"
                    >
                      {testStatus.amd?.loading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span>测试 AMD 连通性</span>
                    </Button>
                    {testStatus.amd?.message && (
                      <span className="text-xs text-muted-foreground">{testStatus.amd.message}</span>
                    )}
                  </div>
                </TabsContent>

                {/* Cloudflare */}
                <TabsContent value="cloudflare" className="space-y-3 pt-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">Account ID</label>
                    <Input
                      value={pCf.account_id || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            cloudflare: { ...pCf, account_id: e.target.value },
                          },
                        }))
                      }
                      placeholder="Cloudflare Account ID"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">API Token</label>
                    <Input
                      type="password"
                      value={pCf.api_token || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            cloudflare: { ...pCf, api_token: e.target.value },
                          },
                        }))
                      }
                      placeholder="Workers AI API Token"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">测试与默认模型 (Model Name)</label>
                    <Input
                      value={pCf.model || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev!,
                          providers: {
                            ...prev!.providers,
                            cloudflare: { ...pCf, model: e.target.value },
                          },
                        }))
                      }
                      placeholder="@cf/meta/llama-3.1-8b-instruct"
                    />
                  </div>
                  <div className="pt-1 flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleTestProvider('cloudflare', {
                          account_id: pCf.account_id,
                          api_token: pCf.api_token,
                          model: pCf.model,
                        })
                      }
                      disabled={testStatus.cloudflare?.loading}
                      className="text-xs gap-1.5"
                    >
                      {testStatus.cloudflare?.loading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                      )}
                      <span>测试 Cloudflare 连通性并拉取最新模型</span>
                    </Button>
                    {testStatus.cloudflare?.message && (
                      <span className="text-xs text-muted-foreground">{testStatus.cloudflare.message}</span>
                    )}
                  </div>

                  {/* Cloudflare Pricing & Free Tier Explanation */}
                  <div className="p-3 bg-muted/30 border border-border/70 rounded-xl space-y-2.5 text-xs">
                    <div className="flex items-center justify-between font-semibold text-foreground">
                      <span className="flex items-center gap-1.5">
                        <span>💡 Cloudflare 免费配额机制与模型分类</span>
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        每日 10,000 Neurons 免费
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Cloudflare 为所有账号（无需绑卡）每日提供 <strong>10,000 Neurons</strong> 免费算力（每日 UTC 00:00 自动刷新）。选用小型模型极省神经元，足够日常研学数十万字翻译与解析！
                    </p>

                    {/* Quick Pick Model Categories */}
                    <div className="space-y-2 pt-1 border-t border-border/50">
                      <div>
                        <div className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400 mb-1.5 flex items-center gap-1">
                          <span>🟢 每日免费配额极力推荐（低消耗·中英双语极佳）:</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {[
                            { name: 'Qwen 2.5 7B (最推荐)', id: '@cf/qwen/qwen2.5-7b-instruct' },
                            { name: 'Llama 3.1 8B', id: '@cf/meta/llama-3.1-8b-instruct' },
                            { name: 'Llama 3.2 3B', id: '@cf/meta/llama-3.2-3b-instruct' },
                            { name: 'DeepSeek R1 32B (推理)', id: '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b' },
                            { name: 'Gemma 2 7B', id: '@cf/google/gemma-7b-it' },
                            { name: 'M2M-100 (纯翻译)', id: '@cf/meta/m2m100-1.2b' },
                          ].map((item) => (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => {
                                setConfig((prev) => ({
                                  ...prev!,
                                  defaults: {
                                    ...prev!.defaults,
                                    default_translation_provider: 'cloudflare',
                                    default_translation_model: item.id,
                                    default_chat_provider: 'cloudflare',
                                    default_chat_model: item.id,
                                  },
                                }))
                              }}
                              className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 transition-colors"
                              title={`点击一键设为默认翻译与助教模型: ${item.id}`}
                            >
                              + {item.name}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <div className="text-[11px] font-medium text-amber-600 dark:text-amber-400 mb-1.5 flex items-center gap-1">
                          <span>🟡 70B 旗舰大算力（建议开通 Workers Paid 计划或轻度使用）:</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {[
                            { name: 'Llama 3.3 70B', id: '@cf/meta/llama-3.3-70b-instruct' },
                            { name: 'DeepSeek R1 70B', id: '@cf/deepseek-ai/deepseek-r1-distill-llama-70b' },
                          ].map((item) => (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => {
                                setConfig((prev) => ({
                                  ...prev!,
                                  defaults: {
                                    ...prev!.defaults,
                                    default_translation_provider: 'cloudflare',
                                    default_translation_model: item.id,
                                    default_chat_provider: 'cloudflare',
                                    default_chat_model: item.id,
                                  },
                                }))
                              }}
                              className="text-[11px] px-2 py-0.5 rounded-md bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/30 transition-colors"
                              title={`点击设为默认模型: ${item.id}`}
                            >
                              + {item.name}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <div className="text-[11px] font-medium text-blue-600 dark:text-blue-400 mb-1.5 flex items-center gap-1">
                          <span>🖼️ 多模态图文识别 (Vision / VLM):</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {[
                            { name: 'Llama 3.2 11B Vision', id: '@cf/meta/llama-3.2-11b-vision-instruct' },
                            { name: 'LLaVA 1.5 7B', id: '@cf/llava-hf/llava-1.5-7b-hf' },
                          ].map((item) => (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => {
                                setConfig((prev) => ({
                                  ...prev!,
                                  defaults: {
                                    ...prev!.defaults,
                                    default_vlm_provider: 'cloudflare',
                                    default_vlm_model: item.id,
                                  },
                                }))
                              }}
                              className="text-[11px] px-2 py-0.5 rounded-md bg-blue-500/10 hover:bg-blue-500/20 text-blue-700 dark:text-blue-300 border border-blue-500/30 transition-colors"
                              title={`点击设为默认多模态模型: ${item.id}`}
                            >
                              + {item.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </TabsContent>

                {/* Custom Gateway Example Plugin */}
                {hasCustomGateway && (
                  <TabsContent value="custom_gateway" className="space-y-4 pt-3">
                    <div className="text-xs text-muted-foreground p-3 rounded-lg bg-card border leading-relaxed">
                      💡 自定义网关插件：支持通过 plugins 目录扩展企业私有大模型平台、私有代理或特定协议网关。
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="text-xs font-semibold">网关服务地址 (Base URL)</label>
                        <Input
                          value={pCustom.proxy_url || pCustom.base_url || ''}
                          onChange={(e) =>
                            setConfig((prev) => ({
                              ...prev!,
                              providers: {
                                ...prev!.providers,
                                custom_gateway: { ...pCustom, base_url: e.target.value },
                              },
                            }))
                          }
                          placeholder="http://127.0.0.1:8000/v1"
                          className="mt-1 font-mono text-xs"
                        />
                      </div>

                      <div>
                        <label className="text-xs font-semibold">API Key（选填）</label>
                        <Input
                          type="password"
                          value={pCustom.api_key || ''}
                          onChange={(e) =>
                            setConfig((prev) => ({
                              ...prev!,
                              providers: {
                                ...prev!.providers,
                                custom_gateway: { ...pCustom, api_key: e.target.value },
                              },
                            }))
                          }
                          placeholder="留空或输入自定义鉴权 Token"
                          className="mt-1 font-mono text-xs"
                        />
                      </div>

                      <div>
                        <label className="text-xs font-semibold">模型标识 (Model)</label>
                        <Input
                          value={pCustom.model || ''}
                          onChange={(e) =>
                            setConfig((prev) => ({
                              ...prev!,
                              providers: {
                                ...prev!.providers,
                                custom_gateway: { ...pCustom, model: e.target.value },
                              },
                            }))
                          }
                          placeholder="custom-model"
                          className="mt-1 font-mono text-xs"
                        />
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          handleTestProvider('custom_gateway', {
                            base_url: pCustom.proxy_url || pCustom.base_url || 'http://127.0.0.1:8000/v1',
                            api_key: pCustom.api_key,
                            model: pCustom.model,
                          })
                        }
                        disabled={testStatus.custom_gateway?.loading}
                        className="text-xs gap-1.5"
                      >
                        {testStatus.custom_gateway?.loading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : null}
                        <span>测试自定义网关连通性</span>
                      </Button>
                      {testStatus.custom_gateway?.message && (
                        <span className="text-xs text-muted-foreground">{testStatus.custom_gateway.message}</span>
                      )}
                    </div>
                  </TabsContent>
                )}
              </Tabs>
            </div>
          </div>
        </div>

        <DialogFooter className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0 flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              window.open('/study?route=chat', '_blank')
            }}
            className="text-xs gap-1.5 border-primary/30 text-primary hover:bg-primary/10 mr-auto"
            title="在新标签页中打开模型测试终端"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>进入模型测试终端</span>
            <ExternalLink className="h-3 w-3 opacity-70" />
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setProviderModalOpen(false)}>
              取消
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isSaving}>
              {isSaving ? '正在保存...' : '保存配置'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
