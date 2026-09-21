import React, { useEffect, useState } from 'react'
import { Bookmark, ClipboardCopy, Trash2, GripHorizontal, Move } from 'lucide-react'
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

export function NoteModal() {
  const {
    isNoteModalOpen,
    setNoteModalOpen,
    activeNoteParams,
    activeDoc,
    refreshActiveDocContent,
  } = useStore()

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const { position, handleMouseDown, toggleDockRight, isDocked } =
    useDraggableModal(isNoteModalOpen)

  useEffect(() => {
    if (activeNoteParams) {
      setTitle(activeNoteParams.title || '')
      setContent(activeNoteParams.content || '')
    }
  }, [activeNoteParams])

  if (!activeNoteParams) return null

  const handleGrabSelection = () => {
    const selection = window.getSelection()?.toString().trim()
    if (selection) {
      setContent((prev) => (prev ? `${prev}\n\n> ${selection}` : `> ${selection}`))
    } else {
      alert('请先在网页正文中用鼠标划选一段文字，再点击抓取！')
    }
  }

  const handleSave = async () => {
    if (!activeDoc || !content.trim()) return
    try {
      setIsSaving(true)
      if (activeNoteParams.type === 'paragraph') {
        if (!activeNoteParams.paragraphId) return
        if (activeNoteParams.noteId) {
          await api.updateParagraphNote(
            activeDoc.doc_id,
            activeNoteParams.chapterId,
            activeNoteParams.paragraphId,
            activeNoteParams.noteId,
            content
          )
        } else {
          await api.addParagraphNote(
            activeDoc.doc_id,
            activeNoteParams.chapterId,
            activeNoteParams.paragraphId,
            content
          )
        }
      } else {
        await api.saveChapterNote(
          activeDoc.doc_id,
          activeNoteParams.chapterId,
          activeNoteParams.type,
          title,
          content,
          activeNoteParams.noteId
        )
      }
      await refreshActiveDocContent()
      setNoteModalOpen(false)
    } catch (e) {
      alert('保存笔记失败: ' + (e as Error).message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!activeDoc || !activeNoteParams.noteId) return
    if (!confirm('确定删除该笔记条目吗？')) return
    try {
      setIsSaving(true)
      if (activeNoteParams.type === 'paragraph') {
        if (!activeNoteParams.paragraphId) return
        await api.deleteParagraphNote(
          activeDoc.doc_id,
          activeNoteParams.chapterId,
          activeNoteParams.paragraphId,
          activeNoteParams.noteId
        )
      } else {
        await api.deleteChapterNote(
          activeDoc.doc_id,
          activeNoteParams.chapterId,
          activeNoteParams.type,
          activeNoteParams.noteId
        )
      }
      await refreshActiveDocContent()
      setNoteModalOpen(false)
    } catch (e) {
      alert('删除笔记失败: ' + (e as Error).message)
    } finally {
      setIsSaving(false)
    }
  }

  const modalTitle = () => {
    if (activeNoteParams.type === 'paragraph') {
      return activeNoteParams.noteId ? '✏️ 编辑段落研读注解' : '📝 新增段落研读注解'
    }
    if (activeNoteParams.type === 'header') {
      return '📌 编辑本章总览 / 提纲'
    }
    return '🎯 编辑本章回顾 / 考点总结'
  }

  return (
    <Dialog open={isNoteModalOpen} onOpenChange={setNoteModalOpen} modal={false}>
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
              <Bookmark className="h-4 w-4 text-primary" />
              <span>{modalTitle()}</span>
            </DialogTitle>
          </div>

          <div className="flex items-center gap-2 mr-8">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 border-dashed border-primary/40 hover:border-primary text-primary"
              onClick={toggleDockRight}
              title={isDocked ? '恢复居中显示' : '靠右侧停靠，让出左侧正文方便对照阅读'}
            >
              <Move className="h-3.5 w-3.5" />
              <span>{isDocked ? '居中显示' : '靠右停靠'}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 text-primary hover:bg-primary/10"
              onClick={handleGrabSelection}
              title="将背景网页中鼠标划选的文字自动插入到当前笔记"
            >
              <ClipboardCopy className="h-3.5 w-3.5" />
              <span>抓取网页选中文本</span>
            </Button>
          </div>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4 max-h-[72vh]">
          {activeNoteParams.type !== 'paragraph' && (
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">笔记小标题 (可选)</label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如: 核心定义、定理推导过程、批判性思考..."
                className="text-xs h-9"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground">笔记内容 (支持 Markdown 语法)</label>
            <Textarea
              rows={9}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="输入您的研读心得、技术推演、引申对比或重点标注..."
              className="text-xs font-mono leading-relaxed min-h-[220px]"
            />
          </div>
        </div>

        <DialogFooter className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0 flex flex-row items-center justify-between sm:justify-between w-full">
          <div>
            {activeNoteParams.noteId ? (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                className="text-xs gap-1"
                onClick={handleDelete}
                disabled={isSaving}
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>删除此条</span>
              </Button>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setNoteModalOpen(false)}>
              取消
            </Button>
            <Button type="button" size="sm" onClick={handleSave} disabled={isSaving || !content.trim()}>
              {isSaving ? '正在保存...' : '保存笔记'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
