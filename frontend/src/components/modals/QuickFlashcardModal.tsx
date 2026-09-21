import React, { useEffect, useRef, useState } from 'react'
import { Sparkles, Tag, Bookmark, GripHorizontal, Move, ClipboardCopy } from 'lucide-react'
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
import * as api from '@/api/client'
import { useDraggableModal } from '@/lib/useDraggableModal'

export function QuickFlashcardModal() {
  const {
    isQuickFlashcardModalOpen,
    setQuickFlashcardModalOpen,
    quickFlashcardData,
    activeDoc,
    refreshDocFlashcardCount,
  } = useStore()

  const [cardType, setCardType] = useState<'qa' | 'cloze'>('qa')
  const [front, setFront] = useState('')
  const [back, setBack] = useState('')
  const [tags, setTags] = useState('核心考点')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const frontInputRef = useRef<HTMLTextAreaElement>(null)

  const { position, handleMouseDown, toggleDockRight, isDocked } =
    useDraggableModal(isQuickFlashcardModalOpen)

  // Initialize fields when opened
  useEffect(() => {
    if (isQuickFlashcardModalOpen && quickFlashcardData) {
      const selected = window.getSelection()?.toString().trim()
      setFront(selected || quickFlashcardData.front || '')
      setBack(quickFlashcardData.back || '')
      setTags('核心考点')
      setCardType('qa')
    }
  }, [isQuickFlashcardModalOpen, quickFlashcardData])

  const wrapCloze = () => {
    const el = frontInputRef.current
    if (!el) return
    const start = el.selectionStart
    const end = el.selectionEnd
    if (start === end) {
      alert('请先在上方正面输入框中选中需要挖空的词句！')
      return
    }
    const val = el.value
    const selectedText = val.substring(start, end)
    const wrapped = `{{${selectedText}}}`
    const updated = val.substring(0, start) + wrapped + val.substring(end)
    setFront(updated)
    setTimeout(() => {
      el.focus()
      el.setSelectionRange(start, start + wrapped.length)
    }, 50)
  }

  const handleGrabToFront = () => {
    const sel = window.getSelection()?.toString().trim()
    if (sel) {
      setFront(sel)
    } else {
      alert('请先在正文中用鼠标划选一段文字，再点击抓取！')
    }
  }

  const handleGrabToBack = () => {
    const sel = window.getSelection()?.toString().trim()
    if (sel) {
      setBack(sel)
    } else {
      alert('请先在正文中用鼠标划选一段文字，再点击抓取！')
    }
  }

  const handleSubmit = async () => {
    if (!front.trim()) {
      alert('正面内容不能为空！')
      return
    }
    if (!activeDoc) {
      alert('未选定有效文档！')
      return
    }

    try {
      setIsSubmitting(true)
      const tagsList = tags
        .replace(/，/g, ',')
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)

      await api.createFlashcard(activeDoc.doc_id, {
        type: cardType,
        front: front.trim(),
        back: back.trim(),
        chapter_id: quickFlashcardData?.chapterId || '',
        paragraph_id: quickFlashcardData?.paragraphId || '',
        tags: tagsList,
      })

      await refreshDocFlashcardCount(activeDoc.doc_id)
      setQuickFlashcardModalOpen(false)
    } catch (err) {
      alert('保存闪卡失败: ' + (err as Error).message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={isQuickFlashcardModalOpen} onOpenChange={setQuickFlashcardModalOpen} modal={false}>
      <DialogContent
        hideOverlay={true}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        className="w-[94vw] max-w-2xl sm:max-w-3xl flex flex-col p-0 overflow-hidden shadow-2xl border-primary/30 bg-card/95 backdrop-blur-md transition-shadow"
        style={{
          transform: `translate3d(calc(-50% + ${position.x}px), calc(-50% + ${position.y}px), 0)`,
        }}
      >
        <DialogHeader
          className="px-6 pt-4 pb-3 border-b border-border/60 shrink-0 cursor-move select-none flex flex-row items-center justify-between"
          onMouseDown={handleMouseDown}
          title="按住此处可任意拖拽移动窗口位置"
        >
          <div className="flex items-center gap-2">
            <GripHorizontal className="h-4 w-4 text-muted-foreground/60 hover:text-foreground" />
            <DialogTitle className="flex items-center gap-2 text-base font-bold">
              <Sparkles className="h-5 w-5 text-amber-500" />
              <span>快速制作双语研学闪卡</span>
            </DialogTitle>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1 mr-8 border-dashed border-primary/40 hover:border-primary text-primary"
            onClick={toggleDockRight}
            title={isDocked ? '恢复居中显示' : '靠右停靠，让出左侧正文方便边看边记'}
          >
            <Move className="h-3.5 w-3.5" />
            <span>{isDocked ? '居中显示' : '靠右停靠'}</span>
          </Button>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4 max-h-[72vh]">
          {/* Card Type Selector */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground">卡片类型</label>
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant={cardType === 'qa' ? 'default' : 'outline'}
                size="sm"
                className="text-xs h-8"
                onClick={() => setCardType('qa')}
              >
                📝 问答卡 (QA)
              </Button>
              <Button
                type="button"
                variant={cardType === 'cloze' ? 'default' : 'outline'}
                size="sm"
                className="text-xs h-8"
                onClick={() => setCardType('cloze')}
              >
                🧩 镂空填空 (Cloze)
              </Button>
            </div>
          </div>

          {/* Front / Question Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-foreground">
                {cardType === 'cloze'
                  ? '正面挖空语句 (使用 {{挖空词}} 标记)'
                  : '正面内容 (题目 / 考点问题)'}
              </label>
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 px-2 text-[11px] gap-1 text-primary hover:bg-primary/10"
                  onClick={handleGrabToFront}
                  title="将网页当前划选的高亮文本填入正面"
                >
                  <ClipboardCopy className="h-3 w-3" />
                  <span>抓取选区填入</span>
                </Button>
                {cardType === 'cloze' && (
                  <Button
                    type="button"
                    variant="subtle"
                    size="sm"
                    className="h-6 px-2 text-[11px] text-primary"
                    onClick={wrapCloze}
                  >
                    ✨ 设为挖空 {"{{...}}"}
                  </Button>
                )}
              </div>
            </div>
            <Textarea
              ref={frontInputRef}
              rows={4}
              value={front}
              onChange={(e) => setFront(e.target.value)}
              placeholder={
                cardType === 'cloze'
                  ? '例如: Antigravity 是由 {{Google Deepmind}} 打造的高级智能体。'
                  : '输入考点、问题或原文句子（可直接在正文中划选后点击右上角“抓取选区填入”）...'
              }
              className="font-sans text-xs leading-relaxed min-h-[90px]"
            />
          </div>

          {/* Back / Answer Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-foreground">
                {cardType === 'cloze' ? '背面补充解析 / 译文' : '背面内容 (答案 / 译文 / 解析)'}
              </label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 px-2 text-[11px] gap-1 text-primary hover:bg-primary/10"
                onClick={handleGrabToBack}
                title="将网页当前划选的高亮文本填入背面"
              >
                <ClipboardCopy className="h-3 w-3" />
                <span>抓取选区填入</span>
              </Button>
            </div>
            <Textarea
              rows={4}
              value={back}
              onChange={(e) => setBack(e.target.value)}
              placeholder="输入参考答案、解析要点或对照译文..."
              className="font-sans text-xs leading-relaxed min-h-[90px]"
            />
          </div>

          {/* Tags */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              <Tag className="h-3 w-3" />
              <span>分类标签 (逗号分隔)</span>
            </label>
            <Input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="例如: 核心考点, 专业术语, 难点"
              className="h-8 text-xs"
            />
          </div>
        </div>

        <DialogFooter className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0">
          <Button variant="outline" size="sm" onClick={() => setQuickFlashcardModalOpen(false)}>
            取消
          </Button>
          <Button size="sm" onClick={handleSubmit} disabled={isSubmitting} className="gap-1">
            <Bookmark className="h-3.5 w-3.5" />
            <span>{isSubmitting ? '正在保存...' : '保存入卡片库'}</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
