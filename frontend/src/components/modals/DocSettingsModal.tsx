import React, { useEffect, useState } from 'react'
import { Settings, RotateCcw, Trash2, Plus, Sparkles } from 'lucide-react'
import { useStore } from '@/store/useStore'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Combobox } from '@/components/ui/combobox'
import * as api from '@/api/client'
import { DocSettings } from '@/types'

export function DocSettingsModal() {
  const {
    isDocSettingsModalOpen,
    setDocSettingsModalOpen,
    activeDoc,
    availableProviders,
    providersConfig,
    setActiveAssistantProvider,
    setActiveAssistantModel,
  } = useStore()

  const [settings, setSettings] = useState<DocSettings | null>(null)
  const [modelsCache, setModelsCache] = useState<Record<string, string[]>>({})
  const [isSaving, setIsSaving] = useState(false)

  const truncateModel = (name?: string, max = 22) => {
    if (!name) return ''
    if (name.length <= max) return name
    return name.slice(0, max - 3) + '...'
  }

  const loadSettings = async () => {
    try {
      const data = await api.getDocSettings(activeDoc?.doc_id)
      setSettings(data)
    } catch (e) {
      console.error('Failed to load settings:', e)
    }
  }

  useEffect(() => {
    if (isDocSettingsModalOpen) {
      loadSettings()
    }
  }, [isDocSettingsModalOpen, activeDoc])

  const fetchModelsForProvider = async (pId: string) => {
    if (!pId) return
    if (modelsCache[pId]) return
    try {
      const models = await api.getProviderModels(pId)
      setModelsCache((prev) => ({ ...prev, [pId]: models }))
    } catch {
      // Ignore
    }
  }

  if (!settings) return null

  const handleSave = async () => {
    try {
      setIsSaving(true)
      await api.saveDocSettings(settings, activeDoc?.doc_id)
      const effChatP = settings.chat_provider || settings.default_chat_provider || providersConfig?.defaults?.default_chat_provider || 'openai_compatible'
      const effChatM = settings.chat_model || settings.default_chat_model || providersConfig?.defaults?.default_chat_model || ''
      setActiveAssistantProvider(effChatP)
      if (effChatM) {
        setActiveAssistantModel(effChatM)
      }
      setDocSettingsModalOpen(false)
      alert('✅ 翻译与学习设置已成功保存！')
    } catch (e) {
      alert('保存配置失败: ' + (e as Error).message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleReset = async () => {
    if (!activeDoc) return
    if (!confirm('确定要清空该文档的专属设置，恢复全局通用默认配置吗？')) return
    try {
      await api.resetDocSettings(activeDoc.doc_id)
      await loadSettings()
      if (providersConfig?.defaults?.default_chat_provider) {
        setActiveAssistantProvider(providersConfig.defaults.default_chat_provider)
      }
      if (providersConfig?.defaults?.default_chat_model) {
        setActiveAssistantModel(providersConfig.defaults.default_chat_model)
      }
      alert('已恢复全局通用默认配置！')
    } catch (e) {
      alert('恢复默认失败: ' + (e as Error).message)
    }
  }

  const defaultTransP = settings.default_translation_provider || providersConfig?.defaults?.default_translation_provider || 'openai_compatible'
  const defaultChatP = settings.default_chat_provider || providersConfig?.defaults?.default_chat_provider || 'openai_compatible'
  const defaultVlmP = settings.default_vlm_provider || providersConfig?.defaults?.default_vlm_provider || 'openai_compatible'

  const effectiveTransP = settings.translation_provider || defaultTransP
  const effectiveChatP = settings.chat_provider || defaultChatP
  const effectiveVlmP = settings.vlm_provider || defaultVlmP

  return (
    <Dialog open={isDocSettingsModalOpen} onOpenChange={setDocSettingsModalOpen}>
      <DialogContent className="max-w-xl h-[85vh] max-h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60 flex flex-row items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Settings className="h-4 w-4 text-primary" />
            <DialogTitle className="text-base font-bold">⚙️ 翻译 Prompt 与学习设置</DialogTitle>
          </div>
          {activeDoc && settings.is_doc_level && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 text-muted-foreground mr-6"
              onClick={handleReset}
            >
              <RotateCcw className="h-3 w-3" />
              <span>恢复全局默认</span>
            </Button>
          )}
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-6 py-4">
          <div className="space-y-5">
            {/* Model Overrides Section */}
            <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-4">
              <div>
                <h4 className="text-xs font-bold text-foreground">🧠 翻译、助教与多模态模型定制</h4>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  未指定时自动继承【全局默认配置】。选择 Provider 后可从下拉列表中搜索模型。
                </p>
              </div>

              {/* Translation Model */}
              <div className="grid grid-cols-1 sm:grid-cols-[160px_minmax(0,1fr)] gap-3 items-center min-w-0">
                <div className="space-y-1 min-w-0">
                  <label className="text-[11px] font-medium text-muted-foreground">翻译 Provider</label>
                  <Select
                    value={settings.translation_provider || 'default'}
                    onValueChange={(val) => {
                      const actual = val === 'default' ? '' : val
                      setSettings((prev) => ({ ...prev!, translation_provider: actual }))
                      if (actual) fetchModelsForProvider(actual)
                    }}
                  >
                    <SelectTrigger className="h-9 truncate">
                      <SelectValue placeholder={`(跟随全局: ${defaultTransP})`} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">(跟随全局默认)</SelectItem>
                      {availableProviders.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-0 w-full overflow-hidden">
                  <label className="text-[11px] font-medium text-muted-foreground">翻译模型 (Model)</label>
                  <Combobox
                    value={settings.translation_model || ''}
                    onChange={(val) => setSettings((prev) => ({ ...prev!, translation_model: val }))}
                    options={modelsCache[effectiveTransP] || []}
                    placeholder={`留空跟随全局默认 (${truncateModel(settings.default_translation_model || 'deepseek-chat')})`}
                  />
                </div>
              </div>

              {/* Assistant Chat Model */}
              <div className="grid grid-cols-1 sm:grid-cols-[160px_minmax(0,1fr)] gap-3 items-center min-w-0">
                <div className="space-y-1 min-w-0">
                  <label className="text-[11px] font-medium text-muted-foreground">助教 Provider</label>
                  <Select
                    value={settings.chat_provider || 'default'}
                    onValueChange={(val) => {
                      const actual = val === 'default' ? '' : val
                      setSettings((prev) => ({ ...prev!, chat_provider: actual }))
                      if (actual) fetchModelsForProvider(actual)
                    }}
                  >
                    <SelectTrigger className="h-9 truncate">
                      <SelectValue placeholder={`(跟随全局: ${defaultChatP})`} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">(跟随全局默认)</SelectItem>
                      {availableProviders.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-0 w-full overflow-hidden">
                  <label className="text-[11px] font-medium text-muted-foreground">助教聊天模型 (Model)</label>
                  <Combobox
                    value={settings.chat_model || ''}
                    onChange={(val) => setSettings((prev) => ({ ...prev!, chat_model: val }))}
                    options={modelsCache[effectiveChatP] || []}
                    placeholder={`留空跟随全局默认 (${truncateModel(settings.default_chat_model || 'deepseek-chat')})`}
                  />
                </div>
              </div>

              {/* VLM Model */}
              <div className="grid grid-cols-1 sm:grid-cols-[160px_minmax(0,1fr)] gap-3 items-center min-w-0">
                <div className="space-y-1 min-w-0">
                  <label className="text-[11px] font-medium text-muted-foreground">多模态 Provider</label>
                  <Select
                    value={settings.vlm_provider || 'default'}
                    onValueChange={(val) => {
                      const actual = val === 'default' ? '' : val
                      setSettings((prev) => ({ ...prev!, vlm_provider: actual }))
                      if (actual) fetchModelsForProvider(actual)
                    }}
                  >
                    <SelectTrigger className="h-9 truncate">
                      <SelectValue placeholder={`(跟随全局: ${defaultVlmP})`} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">(跟随全局默认)</SelectItem>
                      {availableProviders.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 min-w-0 w-full overflow-hidden">
                  <label className="text-[11px] font-medium text-muted-foreground">多模态模型 (Model)</label>
                  <Combobox
                    value={settings.vlm_model || ''}
                    onChange={(val) => setSettings((prev) => ({ ...prev!, vlm_model: val }))}
                    options={modelsCache[effectiveVlmP] || []}
                    placeholder={`留空跟随全局默认 (${truncateModel(settings.default_vlm_model || '未设定')})`}
                  />
                </div>
              </div>
            </div>

            {/* Quick Prompts Configuration (Point 11) */}
            <div className="p-4 rounded-xl bg-muted/20 border border-border/80 space-y-4">
              <div>
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  <span>⚡ 研学助教快捷交互提示词 (Quick Prompts)</span>
                </h4>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  配置按段研学和按章研读时展示在助教面板上的快捷提问胶囊按钮。
                </p>
              </div>

              {/* Paragraph Quick Prompts */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-foreground">
                    📝 按段研学快捷提问按钮
                  </label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px] px-2 gap-1 border-primary/30 text-primary hover:bg-primary/10"
                    onClick={() => {
                      const current = settings.paragraph_quick_prompts || []
                      setSettings({
                        ...settings,
                        paragraph_quick_prompts: [
                          ...current,
                          { label: '💡 新提问', prompt: '请针对选中的段落材料解答我的疑问：' },
                        ],
                      })
                    }}
                  >
                    <Plus className="h-3 w-3" />
                    <span>添加按段提示词</span>
                  </Button>
                </div>
                <div className="space-y-2">
                  {(settings.paragraph_quick_prompts || []).length === 0 ? (
                    <div className="text-[11px] text-muted-foreground/70 py-2 text-center">
                      暂无按段快捷提示词，点击上方按钮添加
                    </div>
                  ) : (
                    (settings.paragraph_quick_prompts || []).map((item, idx) => (
                      <div key={idx} className="flex gap-2 items-center bg-card/60 border border-border/60 rounded-lg p-2 min-w-0">
                        <Input
                          value={item.label}
                          onChange={(e) => {
                            const updated = [...(settings.paragraph_quick_prompts || [])]
                            updated[idx] = { ...updated[idx], label: e.target.value }
                            setSettings({ ...settings, paragraph_quick_prompts: updated })
                          }}
                          placeholder="按钮名称 (如 🧐 拆解长难句)"
                          className="w-36 h-7 text-xs shrink-0"
                        />
                        <Input
                          value={item.prompt}
                          onChange={(e) => {
                            const updated = [...(settings.paragraph_quick_prompts || [])]
                            updated[idx] = { ...updated[idx], prompt: e.target.value }
                            setSettings({ ...settings, paragraph_quick_prompts: updated })
                          }}
                          placeholder="发送给助教的提示词模板"
                          className="flex-1 h-7 text-xs min-w-0"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
                          onClick={() => {
                            const updated = (settings.paragraph_quick_prompts || []).filter((_, i) => i !== idx)
                            setSettings({ ...settings, paragraph_quick_prompts: updated })
                          }}
                          title="删除此项"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Chapter Quick Prompts */}
              <div className="space-y-2 pt-3 border-t border-border/40">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-foreground">
                    📖 按章研读快捷提问按钮
                  </label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px] px-2 gap-1 border-primary/30 text-primary hover:bg-primary/10"
                    onClick={() => {
                      const current = settings.chapter_quick_prompts || []
                      setSettings({
                        ...settings,
                        chapter_quick_prompts: [
                          ...current,
                          { label: '💡 全章总结', prompt: '请总结本章的核心主线、学术观点与论证逻辑。' },
                        ],
                      })
                    }}
                  >
                    <Plus className="h-3 w-3" />
                    <span>添加按章提示词</span>
                  </Button>
                </div>
                <div className="space-y-2">
                  {(settings.chapter_quick_prompts || []).length === 0 ? (
                    <div className="text-[11px] text-muted-foreground/70 py-2 text-center">
                      暂无按章快捷提示词，点击上方按钮添加
                    </div>
                  ) : (
                    (settings.chapter_quick_prompts || []).map((item, idx) => (
                      <div key={idx} className="flex gap-2 items-center bg-card/60 border border-border/60 rounded-lg p-2 min-w-0">
                        <Input
                          value={item.label}
                          onChange={(e) => {
                            const updated = [...(settings.chapter_quick_prompts || [])]
                            updated[idx] = { ...updated[idx], label: e.target.value }
                            setSettings({ ...settings, chapter_quick_prompts: updated })
                          }}
                          placeholder="按钮名称 (如 🗺️ 全章脉络)"
                          className="w-36 h-7 text-xs shrink-0"
                        />
                        <Input
                          value={item.prompt}
                          onChange={(e) => {
                            const updated = [...(settings.chapter_quick_prompts || [])]
                            updated[idx] = { ...updated[idx], prompt: e.target.value }
                            setSettings({ ...settings, chapter_quick_prompts: updated })
                          }}
                          placeholder="发送给助教的提示词模板"
                          className="flex-1 h-7 text-xs min-w-0"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
                          onClick={() => {
                            const updated = (settings.chapter_quick_prompts || []).filter((_, i) => i !== idx)
                            setSettings({ ...settings, chapter_quick_prompts: updated })
                          }}
                          title="删除此项"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Delay rate limiting */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">
                大模型调用限速延迟（秒 / 次，单并发模式）
              </label>
              <Input
                type="number"
                step="0.1"
                min="0.1"
                value={settings.model_call_delay ?? 1.0}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev!,
                    model_call_delay: parseFloat(e.target.value) || 1.0,
                  }))
                }
              />
            </div>

            {/* Prompt template */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">
                翻译 Prompt 模板（必须保留 {'{text}'} 占位符）
              </label>
              <Textarea
                rows={5}
                value={settings.translation_prompt_template || ''}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev!,
                    translation_prompt_template: e.target.value,
                  }))
                }
                className="font-mono text-xs leading-relaxed"
              />
            </div>
          </div>
        </div>

        <DialogFooter className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0">
          <Button variant="outline" size="sm" onClick={() => setDocSettingsModalOpen(false)}>
            取消
          </Button>
          <Button size="sm" onClick={handleSave} disabled={isSaving}>
            {isSaving ? '正在保存...' : '保存配置'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
