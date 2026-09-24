import React from 'react'
import { marked } from 'marked'

// Configure marked to convert single newlines to <br> and support GitHub Flavored Markdown
marked.use({
  breaks: true,
  gfm: true,
})

/**
 * Pre-process markdown text to ensure inline numbered lists like "1. one 2. two"
 * or "1. one 2.two" have proper spacing and line breaks for correct standard list rendering.
 */
function formatMarkdownListHelper(text: string): string {
  if (!text) return ''
  // 1. If someone types "1.one" without a space, insert space -> "1. one"
  let formatted = text.replace(/(^|[\n\s])(\d+)\.([^\s\d])/g, '$1$2. $3')
  // 2. If someone writes inline numbered items on the same line like "1. one 2. two", break them into new lines
  formatted = formatted.replace(/([^\n])\s+(\d+)\.\s+/g, '$1\n$2. ')
  return formatted
}

/**
 * Normalizes relative image paths (both HTML <img src="..."> and Markdown ![alt](...))
 * into API endpoints (/api/study/documents/{docId}/images/{filename}) for reliable display.
 */
function normalizeDocImageUrls(content: string, docId?: string): string {
  if (!content) return ''
  if (!docId) return content

  const encodedDocId = encodeURIComponent(docId)

  // 1. Normalize HTML <img ... src="..." ...> tags
  let res = content.replace(/<img([^>]+)src=["']([^"']+)["']([^>]*)>/gi, (match, prefix, src, suffix) => {
    if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('/api/') || src.startsWith('data:')) {
      return match
    }
    const filename = src.split('/').pop()?.split('?')[0] || ''
    if (!filename) return match
    return `<img${prefix}src="/api/study/documents/${encodedDocId}/images/${filename}"${suffix}>`
  })

  // 2. Normalize Markdown ![alt](url) links
  res = res.replace(/!\[(.*?)\]\((.*?)\)/g, (match, alt, target) => {
    const trimmedTarget = target.trim()
    if (
      trimmedTarget.startsWith('http://') ||
      trimmedTarget.startsWith('https://') ||
      trimmedTarget.startsWith('/api/') ||
      trimmedTarget.startsWith('data:')
    ) {
      return match
    }
    const cleanUrl = trimmedTarget.split(/\s+/)[0]
    const filename = cleanUrl.split('/').pop()?.split('?')[0] || ''
    if (!filename) return match
    return `![${alt}](/api/study/documents/${encodedDocId}/images/${filename})`
  })

  return res
}
import {
  Bot,
  RefreshCw,
  Copy,
  Check,
  Plus,
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  FileText,
  ChevronUp,
  ChevronDown,
  Loader2,
  Pencil,
  Trash2,
  GitMerge,
  ArrowUp,
  ArrowDown,
  ArrowUpLeft,
  ArrowDownRight,
  Scissors,
  MoreHorizontal,
  Edit3,
  X,
  GitFork,
  Zap,
  BookOpen,
  Columns,
  LayoutGrid,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu'
import { ParagraphItem } from '@/types'
import * as api from '@/api/client'
import { saveDocReadingProgress, markChapterCompleted, getChapterProgress } from '@/lib/progress'

export function ReadingStage() {
  const {
    paragraphs,
    chapters,
    activeChapterId,
    selectChapter,
    activeDoc,
    fontSize,
    readingWidth,
    layoutMode,
    isLoadingContent,
    setSelectedParagraph,
    setAssistantOpen,
    openNoteModal,
    openQuickFlashcardModal,
    refreshActiveDocContent,
    updateParagraph,
    targetScrollTop,
    setTargetScrollTop,
    updateDocProgress,
    chapterBatchStatus,
    docBatchStatus,
    startChapterTranslate,
    stopChapterTranslate,
    stopDocTranslate,
    setIsHeaderVisible,
    renameChapter,
    deleteChapter,
    deleteDocument,
    reloadAfterChapterStructureChange,
    fontFamily,
  } = useStore()

  const [copiedId, setCopiedId] = React.useState<string | null>(null)
  const [translatingIds, setTranslatingIds] = React.useState<Set<string>>(new Set())
  const [isTocOpen, setIsTocOpen] = React.useState(false)
  const tocRef = React.useRef<HTMLDivElement>(null)
  const scrollContainerRef = React.useRef<HTMLDivElement>(null)
  const lastScrollTopRef = React.useRef(0)

  // Chapter management state (rename / delete) in TOC
  const [editingChapterId, setEditingChapterId] = React.useState<string | null>(null)
  const [editingChapterTitle, setEditingChapterTitle] = React.useState('')
  const [deletingChapter, setDeletingChapter] = React.useState<{ id: string; title: string } | null>(null)
  const [isDeletingChapter, setIsDeletingChapter] = React.useState(false)

  const handleSaveRename = async (chId: string) => {
    if (!activeDoc?.doc_id || !editingChapterTitle.trim()) {
      setEditingChapterId(null)
      return
    }
    try {
      await renameChapter(activeDoc.doc_id, chId, editingChapterTitle.trim())
    } catch (e) {
      alert('重命名章节失败: ' + (e as Error).message)
    } finally {
      setEditingChapterId(null)
    }
  }

  const handleConfirmDeleteChapter = async () => {
    if (!activeDoc?.doc_id || !deletingChapter) return
    try {
      setIsDeletingChapter(true)
      await deleteChapter(activeDoc.doc_id, deletingChapter.id)
      setDeletingChapter(null)
    } catch (e) {
      alert('删除章节失败: ' + (e as Error).message)
    } finally {
      setIsDeletingChapter(false)
    }
  }

  // Click outside to close TOC and appearance dock
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null
      if (!target) return

      // 1. If click is inside the TOC container itself, do not close
      if (tocRef.current && tocRef.current.contains(target)) {
        return
      }

      // 2. If click is inside any Radix portal/popover/dropdown/menu/dialog, do not close
      if (
        target.closest('[role="menu"]') ||
        target.closest('[role="dialog"]') ||
        target.closest('[role="menuitem"]') ||
        target.closest('[data-radix-popper-content-wrapper]') ||
        target.closest('[data-radix-menu-content]')
      ) {
        return
      }

      // 3. If currently deleting or renaming a chapter, do not auto-close on portal click
      if (deletingChapter || editingChapterId) {
        return
      }

      setIsTocOpen(false)
    }

    if (isTocOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isTocOpen, deletingChapter, editingChapterId])

  // Current active chapter
  const currentChapter = React.useMemo(() => {
    if (!chapters || chapters.length === 0) return null
    return chapters.find((c) => c.chapter_id === activeChapterId) || chapters[0]
  }, [chapters, activeChapterId])

  const currentChapterIndex = currentChapter
    ? chapters.findIndex((c) => c.chapter_id === currentChapter.chapter_id)
    : -1

  const prevChapter = currentChapterIndex > 0 ? chapters[currentChapterIndex - 1] : null
  const nextChapter =
    currentChapterIndex >= 0 && currentChapterIndex < chapters.length - 1
      ? chapters[currentChapterIndex + 1]
      : null

  const [scrollRatio, setScrollRatio] = React.useState(0)
  const [isDragging, setIsDragging] = React.useState(false)
  const [isScrolling, setIsScrolling] = React.useState(false)
  const fadeTimerRef = React.useRef<any>(null)
  const saveDebounceRef = React.useRef<any>(null)
  const trackRef = React.useRef<HTMLDivElement>(null)
  const isSwitchingChapterRef = React.useRef(false)

  // When activeChapterId changes, immediately cancel pending debounced saves and sync scrollRatio to current chapter
  React.useEffect(() => {
    isSwitchingChapterRef.current = true
    if (saveDebounceRef.current) {
      clearTimeout(saveDebounceRef.current)
      saveDebounceRef.current = null
    }
    if (fadeTimerRef.current) {
      clearTimeout(fadeTimerRef.current)
      fadeTimerRef.current = null
    }
    if (activeDoc?.doc_id && activeChapterId) {
      const chProg = getChapterProgress(activeDoc.doc_id, activeChapterId)
      setScrollRatio(chProg)
    }
  }, [activeDoc?.doc_id, activeChapterId])

  // Restore scroll position when document or chapter loads with saved targetScrollTop
  React.useEffect(() => {
    if (isLoadingContent) {
      isSwitchingChapterRef.current = true
      return
    }
    if (scrollContainerRef.current && paragraphs.length > 0) {
      if (targetScrollTop !== null && targetScrollTop > 0) {
        const timer = setTimeout(() => {
          scrollContainerRef.current?.scrollTo({ top: targetScrollTop, behavior: 'auto' })
          setTargetScrollTop(null)
          setTimeout(() => {
            isSwitchingChapterRef.current = false
          }, 120)
        }, 60)
        return () => clearTimeout(timer)
      } else if (targetScrollTop === 0) {
        scrollContainerRef.current.scrollTo({ top: 0, behavior: 'auto' })
        setTargetScrollTop(null)
        setTimeout(() => {
          isSwitchingChapterRef.current = false
        }, 120)
      } else {
        isSwitchingChapterRef.current = false
      }
    }
  }, [activeChapterId, targetScrollTop, paragraphs.length, isLoadingContent])

  // Scroll listener
  const handleScroll = () => {
    if (isSwitchingChapterRef.current || isLoadingContent) return
    const container = scrollContainerRef.current
    if (!container) return

    const currentScrollTop = container.scrollTop
    const delta = currentScrollTop - lastScrollTopRef.current

    if (currentScrollTop <= 20) {
      setIsHeaderVisible(true)
    } else if (delta > 8 && currentScrollTop > 40) {
      // Scrolling down: auto-hide header
      setIsHeaderVisible(false)
    } else if (delta < -8) {
      // Scrolling up: auto-show header
      setIsHeaderVisible(true)
    }
    lastScrollTopRef.current = currentScrollTop

    const maxScroll = container.scrollHeight - container.clientHeight
    const ratio = maxScroll > 0 ? (container.scrollTop / maxScroll) * 100 : 0
    const clamped = Math.min(100, Math.max(0, Math.round(ratio)))
    setScrollRatio(clamped)

    setIsScrolling(true)
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
    fadeTimerRef.current = setTimeout(() => {
      setIsScrolling(false)
    }, 2500)

    // Debounce save to storage and store
    const currentDocId = activeDoc?.doc_id
    const currentChId = activeChapterId
    if (saveDebounceRef.current) clearTimeout(saveDebounceRef.current)
    saveDebounceRef.current = setTimeout(() => {
      if (currentDocId && currentChId && currentChId === activeChapterId) {
        const overallRatio = saveDocReadingProgress(
          currentDocId,
          currentChId,
          container.scrollTop,
          clamped,
          chapters
        )
        updateDocProgress(currentDocId, overallRatio)
      }
    }, 350)
  }

  const quickScrollToTop = () => {
    setIsHeaderVisible(true)
    scrollContainerRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const quickScrollToBottom = () => {
    const container = scrollContainerRef.current
    if (container) {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
    }
  }

  const handleTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const track = trackRef.current
    const container = scrollContainerRef.current
    if (!track || !container) return
    const rect = track.getBoundingClientRect()
    let ratio = (e.clientY - rect.top) / rect.height
    ratio = Math.max(0, Math.min(1, ratio))
    const maxScroll = container.scrollHeight - container.clientHeight
    container.scrollTo({ top: ratio * maxScroll, behavior: 'smooth' })
  }

  const handleThumbMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
    document.body.style.userSelect = 'none'

    const handleMouseMove = (moveEvt: MouseEvent) => {
      const track = trackRef.current
      const container = scrollContainerRef.current
      if (!track || !container) return
      const rect = track.getBoundingClientRect()
      let ratio = (moveEvt.clientY - rect.top) / rect.height
      ratio = Math.max(0, Math.min(1, ratio))
      const maxScroll = container.scrollHeight - container.clientHeight
      container.scrollTop = ratio * maxScroll
      const clamped = Math.min(100, Math.max(0, Math.round(ratio * 100)))
      setScrollRatio(clamped)
    }

    const handleMouseUp = () => {
      setIsDragging(false)
      document.body.style.userSelect = ''
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      const container = scrollContainerRef.current
      if (activeDoc?.doc_id && activeChapterId && container && !isSwitchingChapterRef.current) {
        const maxScroll = container.scrollHeight - container.clientHeight
        const ratio = maxScroll > 0 ? (container.scrollTop / maxScroll) * 100 : 0
        const clamped = Math.min(100, Math.max(0, Math.round(ratio)))
        const overallRatio = saveDocReadingProgress(
          activeDoc.doc_id,
          activeChapterId,
          container.scrollTop,
          clamped,
          chapters
        )
        updateDocProgress(activeDoc.doc_id, overallRatio)
      }
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  // Filter paragraphs to current active chapter
  const displayParagraphs = React.useMemo(() => {
    if (!currentChapter) return paragraphs
    const filtered = paragraphs.filter((p) => p.chapter_id === currentChapter.chapter_id)
    return filtered.length > 0 ? filtered : paragraphs
  }, [paragraphs, currentChapter])

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  const handleRetranslate = async (para: ParagraphItem) => {
    if (!activeDoc) return
    const pid = para.id
    setTranslatingIds((prev) => new Set(prev).add(pid))
    updateParagraph(pid, { status: 'translating' })
    try {
      const updated = await api.retranslateParagraph(activeDoc.doc_id, para.chapter_id || activeChapterId || '', pid)
      updateParagraph(pid, {
        translated_text: updated.translated_text,
        status: updated.status || 'completed',
      })
      await refreshActiveDocContent()
    } catch (e) {
      alert('重新翻译失败: ' + (e as Error).message)
      updateParagraph(pid, { status: 'pending' })
    } finally {
      setTranslatingIds((prev) => {
        const next = new Set(prev)
        next.delete(pid)
        return next
      })
    }
  }

  const handleAskAssistant = (para: ParagraphItem) => {
    setSelectedParagraph(para)
    setAssistantOpen(true)
  }

  const containerWidthClass = {
    standard: 'max-w-4xl',
    wide: 'max-w-6xl',
    full: 'max-w-[95%] px-3',
  }[readingWidth]

  const isExtracting = activeDoc?.status === 'extracting' || activeDoc?.status === 'processing'
  const isError = activeDoc?.status === 'error'

  if (isLoadingContent && !isExtracting) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-muted-foreground gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <span className="text-xs">正在加载文献材料与双语解析...</span>
      </div>
    )
  }

  if (activeDoc && isExtracting) {
    const prog = activeDoc.progress || {}
    const percent = Math.min(Math.max(prog.percent ?? activeDoc.progress_percent ?? 0, 0), 100)
    const current = prog.current_page || 0
    const total = prog.total_pages || 1
    const detail = prog.detail || `正在后台抓取清洗网页、本地化图片并切分章节 (第 ${current} / ${total} 篇)...`

    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 md:p-16 text-center animate-in fade-in duration-300">
        <div className="w-full max-w-md bg-card/90 backdrop-blur border border-border/80 rounded-2xl p-6 shadow-xl space-y-5">
          {/* Animated Spinner & Icon */}
          <div className="flex items-center justify-center">
            <div className="relative">
              <div className="w-16 h-16 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center text-primary">
                <Sparkles className="w-6 h-6 animate-pulse" />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <h3 className="text-base font-bold text-foreground">
              教材结构化构建中...
            </h3>
            <p className="text-xs text-muted-foreground font-medium truncate px-4" title={activeDoc.title || activeDoc.source_file}>
              《{activeDoc.title || activeDoc.source_file || '研学材料'}》
            </p>
          </div>

          {/* Progress Bar & Percentage */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-muted-foreground">处理进度</span>
              <span className="font-semibold text-primary">{percent}%</span>
            </div>
            <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-500 rounded-full"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>

          {/* Dynamic Detail Text */}
          <div className="p-3 bg-muted/40 rounded-lg border border-border/40 text-[11px] text-muted-foreground text-left leading-relaxed">
            <div className="flex items-center gap-2 mb-1 text-foreground font-medium">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
              <span>{detail}</span>
            </div>
            <div className="text-[10px] text-muted-foreground/70">
              💡 正在自动去除网页多余导航/广告并本地化留存高清图表，构建完成后将自动开启研学精读。
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (activeDoc && isError) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center animate-in fade-in">
        <div className="w-full max-w-md bg-destructive/10 border border-destructive/20 rounded-2xl p-6 space-y-4">
          <div className="text-3xl">⚠️</div>
          <div className="space-y-1">
            <h3 className="text-base font-bold text-destructive">材料解析遇到异常</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {(activeDoc as any).error_message || '抓取或解析未能成功完成，请检查网络链接或文件格式'}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => activeDoc.doc_id && deleteDocument(activeDoc.doc_id)}
            className="text-xs h-8"
          >
            删除并重新尝试
          </Button>
        </div>
      </div>
    )
  }

  if (!activeDoc || paragraphs.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-muted-foreground text-center">
        <div className="text-4xl mb-3">📖</div>
        <div className="text-base font-semibold text-foreground mb-1">请选择或上传文档</div>
        <div className="text-xs max-w-sm">在左侧资料库选择一篇文献材料，或点击上方“上传文档”开始双语研学。</div>
      </div>
    )
  }

  return (
    <div className="flex-1 h-full relative overflow-hidden flex">
      {/* Scrollable Reading Content Area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-6 pb-20 pt-16 md:px-10 md:pb-28 md:pt-18 flex justify-center h-full"
      >
        <div
          className={`w-full ${containerWidthClass} reading-content-area transition-[max-width] duration-300 ease-in-out space-y-8 pb-32`}
          style={{ fontFamily: 'var(--reading-font-family)' }}
        >
        {currentChapter ? (
          <div key={currentChapter.chapter_id} id={`chapter-${currentChapter.chapter_id}`} className="space-y-6">
            {/* Chapter Header */}
            <div className="border-b border-border/80 pb-4 pt-2 space-y-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium border border-primary/20">
                    第 {currentChapterIndex + 1} 章 / 共 {chapters.length} 章
                  </span>
                  <span className="text-xs text-muted-foreground hidden sm:inline">
                    本章共 {displayParagraphs.length} 个段落
                  </span>
                </div>

                {/* Chapter Actions: Batch Translate */}
                <div className="flex items-center gap-2">

                  {chapterBatchStatus?.is_running ? (
                    <Button
                      variant="subtle"
                      size="sm"
                      onClick={() => stopChapterTranslate()}
                      className="text-xs h-7 gap-1.5 text-amber-500 bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500/20"
                      title="点击暂停/停止当前章节批量翻译"
                    >
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                      </span>
                      <span>
                        ⏸️ 停止本章翻译 ({chapterBatchStatus.completed}/{chapterBatchStatus.total}, {chapterBatchStatus.percent}%)
                      </span>
                    </Button>
                  ) : docBatchStatus?.is_doc_level_running ? (
                    <Button
                      variant="subtle"
                      size="sm"
                      onClick={() => stopDocTranslate()}
                      className="text-xs h-7 gap-1.5 text-amber-500 bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500/20"
                      title="点击暂停/停止全篇批量翻译"
                    >
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                      </span>
                      <span>
                        ⏸️ 全篇批量翻译中 ({docBatchStatus.percent}%)
                      </span>
                    </Button>
                  ) : (
                    <Button
                      variant="subtle"
                      size="sm"
                      onClick={() => {
                        if (activeDoc?.doc_id && currentChapter?.chapter_id) {
                          startChapterTranslate(activeDoc.doc_id, currentChapter.chapter_id)
                        }
                      }}
                      className="text-xs h-7 gap-1 text-primary hover:bg-primary/10 border border-primary/20"
                      title="批量并发翻译本章未完成的段落"
                    >
                      <Zap className="h-3 w-3" />
                      <span>⚡ 批量翻译本章</span>
                    </Button>
                  )}
                </div>
              </div>
              <h2 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2.5">
                <span className="w-2.5 h-6 rounded-full bg-primary inline-block shrink-0" />
                <span>{currentChapter.title}</span>
              </h2>
            </div>

            {/* Chapter Header Notes (导读与学习总结) */}
            <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-primary flex items-center gap-1.5">
                  <Bookmark className="h-3.5 w-3.5" /> 本章导读与学习总结
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[11px] text-primary"
                  onClick={() =>
                    openNoteModal({
                      chapterId: currentChapter.chapter_id,
                      type: 'header',
                    })
                  }
                >
                  <Plus className="h-3 w-3 mr-1" /> 新增总结
                </Button>
              </div>
              {currentChapter.header_notes && currentChapter.header_notes.length > 0 ? (
                <div className="space-y-2 pt-1">
                  {currentChapter.header_notes.map((note) => (
                    <div key={note.id} className="text-xs leading-relaxed text-foreground/90 bg-card/60 p-3 rounded-lg border border-border/50">
                      {note.title && <div className="font-semibold mb-1">{note.title}</div>}
                      <div
                        className="para-markdown note-markdown text-xs"
                        dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdownListHelper(note.content || '')) as string }}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground/60 italic py-1">
                  暂无章节导读，可点击右上角添加本章核心要点或阅读目标。
                </div>
              )}
            </div>

            {/* Paragraphs in current chapter */}
            <div className="space-y-6 pt-2">
              {displayParagraphs.map((para, pIdx) => (
                <ParagraphCard
                  key={para.id}
                  para={para}
                  fontSize={fontSize}
                  layoutMode={layoutMode}
                  isTranslating={translatingIds.has(para.id) || para.status === 'translating'}
                  isCopied={copiedId === para.id}
                  isFirst={pIdx === 0}
                  isLast={pIdx === displayParagraphs.length - 1}
                  onAsk={() => handleAskAssistant(para)}
                  onRetranslate={(target) => handleRetranslate(target || para)}
                  onCopy={() => handleCopy(para.translated_text || para.source_text, para.id)}
                  onQuickFlashcard={() =>
                    openQuickFlashcardModal({
                      paragraphId: para.id,
                      chapterId: para.chapter_id || activeChapterId || '',
                      front: para.source_text,
                      back: para.translated_text || '',
                    })
                  }
                />
              ))}
            </div>

            {/* Chapter Footer Notes (小结与思考) */}
            {currentChapter.footer_notes && currentChapter.footer_notes.length > 0 && (
              <div className="bg-card/50 border border-border/70 rounded-xl p-4 space-y-2 mt-6">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                    <Bookmark className="h-3.5 w-3.5 text-primary" /> 本章思考与复习笔记
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={() =>
                      openNoteModal({
                        chapterId: currentChapter.chapter_id,
                        type: 'footer',
                      })
                    }
                  >
                    <Plus className="h-3 w-3 mr-1" /> 新增小结
                  </Button>
                </div>
                <div className="space-y-2 pt-1">
                  {currentChapter.footer_notes.map((note) => (
                    <div key={note.id} className="text-xs leading-relaxed text-foreground/90 bg-card p-3 rounded-lg border border-border/50">
                      {note.title && <div className="font-semibold mb-1">{note.title}</div>}
                      <div
                        className="para-markdown note-markdown text-xs"
                        dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdownListHelper(note.content || '')) as string }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Bottom Chapter Navigation Bar */}
            {chapters.length > 1 && (
              <div className="pt-8 mt-10 border-t border-border/60 flex items-center justify-between gap-4">
                {prevChapter ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => selectChapter(prevChapter.chapter_id)}
                    className="h-9 px-3.5 text-xs gap-1.5 hover:border-primary/40"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    <span>上一章: <strong className="font-normal max-w-[150px] truncate inline-block align-bottom">{prevChapter.title}</strong></span>
                  </Button>
                ) : (
                  <div />
                )}

                <span className="text-xs text-muted-foreground font-mono">
                  第 {currentChapterIndex + 1} / {chapters.length} 章
                </span>

                {nextChapter ? (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => {
                      if (activeDoc?.doc_id && currentChapter?.chapter_id) {
                        const overall = markChapterCompleted(activeDoc.doc_id, currentChapter.chapter_id, chapters)
                        updateDocProgress(activeDoc.doc_id, overall)
                      }
                      selectChapter(nextChapter.chapter_id)
                    }}
                    className="h-9 px-3.5 text-xs gap-1.5 shadow-sm"
                  >
                    <span>下一章: <strong className="font-normal max-w-[150px] truncate inline-block align-bottom">{nextChapter.title}</strong></span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      if (activeDoc?.doc_id && currentChapter?.chapter_id) {
                        const overall = markChapterCompleted(activeDoc.doc_id, currentChapter.chapter_id, chapters)
                        updateDocProgress(activeDoc.doc_id, overall)
                      }
                    }}
                    className="text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 px-3 py-1.5 rounded-lg border border-emerald-500/30 transition-colors cursor-pointer"
                    title="点击标记本文档全部阅读完成"
                  >
                    🎉 已到达文档末尾（点击完成阅读）
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          /* Fallback when no chapters detected */
          <div className="space-y-6 pt-2">
            {paragraphs.map((para, pIdx) => (
              <ParagraphCard
                key={para.id}
                para={para}
                fontSize={fontSize}
                layoutMode={layoutMode}
                isTranslating={translatingIds.has(para.id) || para.status === 'translating'}
                isCopied={copiedId === para.id}
                isFirst={pIdx === 0}
                isLast={pIdx === paragraphs.length - 1}
                onAsk={() => handleAskAssistant(para)}
                onRetranslate={(target) => handleRetranslate(target || para)}
                onCopy={() => handleCopy(para.translated_text || para.source_text, para.id)}
                onQuickFlashcard={() =>
                  openQuickFlashcardModal({
                    paragraphId: para.id,
                    chapterId: para.chapter_id || activeChapterId || '',
                    front: para.source_text,
                    back: para.translated_text || '',
                  })
                }
              />
            ))}
          </div>
        )}
        </div>
      </div>

      {/* Floating TOC Outline Dock (悬浮章节大纲坞) */}
      <div
        ref={tocRef}
        className="absolute left-[18px] top-[76px] z-30 select-none"
      >
        {/* Floating Trigger Icon Button (平时半透明悬浮) */}
        <button
          type="button"
          onClick={() => setIsTocOpen(!isTocOpen)}
          className={`group flex items-center justify-center w-9 h-9 rounded-full border backdrop-blur-xl shadow-md transition-all duration-200 cursor-pointer ${
            isTocOpen
              ? 'bg-primary text-primary-foreground border-primary shadow-primary/25 scale-105 opacity-100'
              : 'bg-card/85 hover:bg-card text-muted-foreground hover:text-foreground border-border/80 hover:border-primary/40 hover:shadow-lg hover:scale-105 opacity-40 hover:opacity-100'
          }`}
          title="章节大纲"
        >
          <BookOpen className="h-4 w-4 transition-transform group-hover:scale-110" />
        </button>

        {/* Popover Card */}
        {isTocOpen && (
          <div className="absolute left-0 top-11 w-80 max-h-[calc(100vh-140px)] flex flex-col bg-card/95 backdrop-blur-2xl border border-border/80 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border/60 bg-muted/40">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-primary" />
                <span className="text-xs font-bold text-foreground">章节大纲</span>
              </div>
              <button
                type="button"
                onClick={() => setIsTocOpen(false)}
                className="h-6 w-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Chapter TOC List (仅保留章节大纲) */}
            <div className="flex flex-col flex-1 min-h-0">
              <div className="px-3.5 py-2 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between border-b border-border/40 bg-muted/10">
                <span>章节目录</span>
                <span className="text-[10px] font-mono lowercase">共 {chapters.length} 章</span>
              </div>
              <div className="overflow-y-auto max-h-[min(520px,calc(100vh-200px))] p-2 space-y-1">
                {chapters.length === 0 ? (
                  <div className="py-6 text-center text-xs text-muted-foreground">
                    暂无章节
                  </div>
                ) : (
                  chapters.map((chap, idx) => {
                    const isActive = chap.chapter_id === activeChapterId

                    if (editingChapterId === chap.chapter_id) {
                      return (
                        <div
                          key={chap.chapter_id}
                          className="px-2 py-1.5 rounded-xl text-xs bg-muted/60 border border-primary/40 flex items-center gap-1.5"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 font-bold bg-muted text-muted-foreground">
                            #{String(idx + 1).padStart(2, '0')}
                          </span>
                          <input
                            type="text"
                            value={editingChapterTitle}
                            onChange={(e) => setEditingChapterTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveRename(chap.chapter_id)
                              if (e.key === 'Escape') setEditingChapterId(null)
                            }}
                            autoFocus
                            placeholder="输入章节标题..."
                            className="flex-1 min-w-0 bg-background border border-border px-1.5 py-0.5 rounded text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveRename(chap.chapter_id)}
                            className="h-5 w-5 rounded bg-primary text-primary-foreground flex items-center justify-center hover:opacity-90 cursor-pointer shrink-0"
                            title="保存"
                          >
                            <Check className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingChapterId(null)}
                            className="h-5 w-5 rounded bg-muted text-muted-foreground flex items-center justify-center hover:text-foreground cursor-pointer shrink-0"
                            title="取消"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      )
                    }

                    return (
                      <div
                        key={chap.chapter_id}
                        className={`group w-full px-2.5 py-1.5 rounded-xl text-xs flex items-center justify-between gap-1.5 transition-all ${
                          isActive
                            ? 'bg-primary/15 text-primary font-semibold border border-primary/30 shadow-xs'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted/60 border border-transparent'
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => {
                            selectChapter(chap.chapter_id)
                            setIsTocOpen(false)
                          }}
                          className="flex items-center gap-2 flex-1 min-w-0 text-left cursor-pointer"
                          title={chap.title}
                        >
                          <span
                            className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 font-bold ${
                              isActive
                                ? 'bg-primary text-primary-foreground'
                                : 'bg-muted text-muted-foreground'
                            }`}
                          >
                            #{String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="truncate flex-1 leading-relaxed">
                            {chap.title}
                          </span>
                        </button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              onMouseDown={(e) => e.stopPropagation()}
                              onClick={(e) => e.stopPropagation()}
                              className="h-6 w-6 rounded-md flex items-center justify-center opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-opacity cursor-pointer shrink-0"
                              title="章节操作"
                            >
                              <MoreHorizontal className="h-3.5 w-3.5" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-32 text-xs">
                            <DropdownMenuItem
                              onSelect={(e) => {
                                e.preventDefault()
                                setEditingChapterId(chap.chapter_id)
                                setEditingChapterTitle(chap.title)
                              }}
                              onClick={(e) => {
                                e.stopPropagation()
                                setEditingChapterId(chap.chapter_id)
                                setEditingChapterTitle(chap.title)
                              }}
                              className="cursor-pointer gap-2 py-1.5"
                            >
                              <Pencil className="h-3.5 w-3.5 text-primary" />
                              <span>重命名</span>
                            </DropdownMenuItem>
                            <div className="h-px bg-border/50 my-1" />
                            <DropdownMenuItem
                              onSelect={(e) => {
                                e.preventDefault()
                                setDeletingChapter({ id: chap.chapter_id, title: chap.title })
                              }}
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeletingChapter({ id: chap.chapter_id, title: chap.title })
                              }}
                              className="cursor-pointer gap-2 py-1.5 text-destructive focus:text-destructive"
                            >
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                              <span>删除章节</span>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Floating Quick-Scroll Navigator */}
      <div
        className={`quick-scroll-navigator ${isDragging ? 'dragging' : ''} ${isScrolling ? 'scrolling' : ''}`}
      >
        <button
          type="button"
          className="quick-scroll-btn"
          onClick={quickScrollToTop}
          title="快速回到顶部 (Home)"
        >
          <ChevronUp className="h-3.5 w-3.5" />
          <span className="text-[7px] leading-none -mt-0.5 font-bold">顶</span>
        </button>

        <div
          ref={trackRef}
          className="quick-scroll-track"
          onClick={handleTrackClick}
          title="点击或拖动滚动条快速跳转"
        >
          <div className="quick-scroll-fill" style={{ height: `${scrollRatio}%` }} />
          <div
            className="quick-scroll-thumb"
            style={{ top: `${scrollRatio}%` }}
            onMouseDown={handleThumbMouseDown}
          >
            <span className="quick-scroll-bubble font-mono">{scrollRatio}%</span>
          </div>
        </div>

        <button
          type="button"
          className="quick-scroll-btn"
          onClick={quickScrollToBottom}
          title="快速直达底部 (End)"
        >
          <ChevronDown className="h-3.5 w-3.5" />
          <span className="text-[7px] leading-none -mt-0.5 font-bold">底</span>
        </button>
      </div>

      {/* Chapter Deletion Confirmation Modal */}
      {deletingChapter && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="bg-card border border-border/80 rounded-xl shadow-2xl max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-2.5 text-destructive">
              <Trash2 className="h-5 w-5" />
              <h3 className="font-semibold text-base text-foreground">确认删除章节</h3>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              确定要删除章节 <span className="font-semibold text-foreground">「{deletingChapter.title}」</span> 吗？
              <br />
              <span className="text-xs text-destructive/80 mt-1 block">注意：章节删除后，其中的段落及生词卡片将被移出，此操作不可撤销。</span>
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeletingChapter(null)}
                disabled={isDeletingChapter}
              >
                取消
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleConfirmDeleteChapter}
                disabled={isDeletingChapter}
                className="gap-1.5"
              >
                {isDeletingChapter && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                <span>确认删除</span>
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ParagraphCard({
  para,
  fontSize,
  layoutMode,
  isTranslating,
  isCopied,
  isFirst,
  isLast,
  onAsk,
  onRetranslate,
  onCopy,
  onQuickFlashcard,
}: {
  para: ParagraphItem
  fontSize: number
  layoutMode: 'stack' | 'side' | 'card'
  isTranslating: boolean
  isCopied: boolean
  isFirst?: boolean
  isLast?: boolean
  onAsk: () => void
  onRetranslate: (targetPara?: ParagraphItem) => void
  onCopy: (text?: string, id?: string) => void
  onQuickFlashcard: () => void
}) {
  const {
    updateParagraph,
    replaceParagraph,
    insertParagraphAfter,
    removeParagraph,
    activeDoc,
    activeChapterId,
    openNoteModal,
    refreshActiveDocContent,
    extractingParaIds,
    setParaExtracting,
    chapters,
    reloadAfterChapterStructureChange,
  } = useStore()
  const [localExtracting, setLocalExtracting] = React.useState(false)
  const isExtracting = extractingParaIds.has(para.id) || localExtracting
  const [isExtractedOpen, setIsExtractedOpen] = React.useState(Boolean(para.extracted_text))

  React.useEffect(() => {
    if (para.extracted_text) {
      setIsExtractedOpen(true)
    }
  }, [para.extracted_text])

  // In-place editing state
  const [isEditing, setIsEditing] = React.useState(false)
  const [editText, setEditText] = React.useState(para.source_text)
  const [hasNewParagraph, setHasNewParagraph] = React.useState(false)
  const [newParaText, setNewParaText] = React.useState('')
  const editTextareaRef = React.useRef<HTMLTextAreaElement>(null)
  const [isSavingEdit, setIsSavingEdit] = React.useState(false)
  const [isDeletingPara, setIsDeletingPara] = React.useState(false)
  const [isMerging, setIsMerging] = React.useState(false)

  const getInitialType = React.useCallback((): 'text' | 'heading' | 'image' | 'code' => {
    if (para.type === 'scanned_page' || para.type === 'image' || !!para.image_url || para.source_text?.includes('![')) {
      return 'image'
    }
    if (para.type === 'code' || para.source_text?.trim().startsWith('```')) {
      return 'code'
    }
    if (para.type === 'heading' || para.source_text?.trim().startsWith('#')) {
      return 'heading'
    }
    return 'text'
  }, [para.type, para.image_url, para.source_text])

  const [editType, setEditType] = React.useState<'text' | 'heading' | 'image' | 'code'>(getInitialType)
  const [isTypeUserOverridden, setIsTypeUserOverridden] = React.useState(false)

  const currentlyTranslating = isTranslating || para.status === 'translating'

  // Cross-chapter shifting & splitting state
  const [isShifting, setIsShifting] = React.useState(false)
  const [isSplitting, setIsSplitting] = React.useState(false)
  const [showSplitModal, setShowSplitModal] = React.useState(false)
  const [newChapterTitle, setNewChapterTitle] = React.useState('')

  const currentChapterId = para.chapter_id || activeChapterId
  const chapterIdx = chapters.findIndex((c) => c.chapter_id === currentChapterId)
  const isFirstChapter = chapterIdx <= 0
  const isLastChapter = chapterIdx === -1 || chapterIdx >= chapters.length - 1

  const handleShiftChapter = async (direction: 'prev' | 'next') => {
    if (!activeDoc?.doc_id || !currentChapterId || isShifting) return
    const directionLabel = direction === 'prev' ? '上一章结尾' : '下一章开头'
    const scopeLabel = direction === 'prev' ? '本段往上（含本段）的所有段落' : '本段往下（含本段）的所有段落'
    if (!confirm(`确定要将${scopeLabel}合并到【${directionLabel}】吗？`)) {
      return
    }
    try {
      setIsShifting(true)
      const res = await api.shiftChapterParagraphs(
        activeDoc.doc_id,
        currentChapterId,
        para.id,
        direction
      )
      if (res.success) {
        const targetChapter = res.source_deleted
          ? res.target_chapter_id
          : (direction === 'prev' ? res.target_chapter_id : currentChapterId)
        await reloadAfterChapterStructureChange(activeDoc.doc_id, targetChapter)
      }
    } catch (e) {
      alert('移动段落到章节失败: ' + (e as Error).message)
    } finally {
      setIsShifting(false)
    }
  }

  const handleOpenSplitModal = () => {
    const previewText = para.source_text?.trim().slice(0, 30).replace(/[\n\r#*`]/g, '') || '新章节'
    setNewChapterTitle(previewText)
    setShowSplitModal(true)
  }

  const handleConfirmSplit = async () => {
    if (!activeDoc?.doc_id || !currentChapterId || !newChapterTitle.trim() || isSplitting) return
    try {
      setIsSplitting(true)
      const res = await api.splitChapterFromParagraph(
        activeDoc.doc_id,
        currentChapterId,
        para.id,
        newChapterTitle.trim()
      )
      if (res.success) {
        setShowSplitModal(false)
        await reloadAfterChapterStructureChange(activeDoc.doc_id, res.new_chapter_id)
      }
    } catch (e) {
      alert('拆分章节失败: ' + (e as Error).message)
    } finally {
      setIsSplitting(false)
    }
  }

  React.useEffect(() => {
    if (!isEditing) {
      setEditText(para.source_text)
      setHasNewParagraph(false)
      setNewParaText('')
      setEditType(getInitialType())
      setIsTypeUserOverridden(false)
    }
  }, [para.source_text, para.type, para.image_url, isEditing, getInitialType])

  const handleEditTextChange = (val: string) => {
    setEditText(val)
    if (!isTypeUserOverridden) {
      const trimmed = val.trim()
      const hasImg = /!\[.*?\]\(.*?\)/.test(trimmed)
      if (hasImg) {
        setEditType('image')
      } else if (trimmed.startsWith('#')) {
        setEditType('heading')
      } else if (trimmed.startsWith('```')) {
        setEditType('code')
      } else {
        setEditType('text')
      }
    }
  }

  const handleSelectType = (newType: 'text' | 'heading' | 'image' | 'code') => {
    setEditType(newType)
    setIsTypeUserOverridden(true)
    if (newType === 'heading' && !editText.trim().startsWith('#')) {
      setEditText((prev) => '## ' + prev.trim())
    } else if (newType === 'text' && editText.trim().startsWith('#')) {
      setEditText((prev) => prev.replace(/^[#\s]+/, ''))
    } else if (newType === 'code' && !editText.trim().startsWith('```')) {
      setEditText((prev) => '```\n' + prev + '\n```')
    }
  }

  const isSide = layoutMode === 'side'
  const isCard = layoutMode === 'card'
  const isImage = para.type === 'scanned_page' || para.type === 'image' || !!para.image_url || para.source_text?.includes('![')

  const isSourceChinese = React.useMemo(() => {
    const text = para.source_text || ''
    if (!text) return false
    const clean = text.replace(/!\[.*?\]\(.*?\)/g, '').replace(/[#*`_~]/g, '')
    const chineseChars = (clean.match(/[\u4e00-\u9fa5]/g) || []).length
    const validChars = (clean.match(/[\w\u4e00-\u9fa5]/g) || []).length
    return validChars >= 2 && chineseChars / validChars >= 0.35
  }, [para.source_text])

  const isEditChinese = React.useMemo(() => {
    if (!editText) return false
    const clean = editText.replace(/!\[.*?\]\(.*?\)/g, '').replace(/[#*`_~]/g, '')
    const chineseChars = (clean.match(/[\u4e00-\u9fa5]/g) || []).length
    const validChars = (clean.match(/[\w\u4e00-\u9fa5]/g) || []).length
    return validChars >= 2 && chineseChars / validChars >= 0.35
  }, [editText])

  const isNewParaChinese = React.useMemo(() => {
    if (!newParaText) return false
    const clean = newParaText.replace(/!\[.*?\]\(.*?\)/g, '').replace(/[#*`_~]/g, '')
    const chineseChars = (clean.match(/[\u4e00-\u9fa5]/g) || []).length
    const validChars = (clean.match(/[\w\u4e00-\u9fa5]/g) || []).length
    return validChars >= 2 && chineseChars / validChars >= 0.35
  }, [newParaText])

  const shouldSkipRetranslate = isEditChinese && (!hasNewParagraph || isNewParaChinese)

  const handleExtract = async () => {
    if (!para.doc_id || !para.chapter_id || isExtracting) return
    try {
      setLocalExtracting(true)
      setParaExtracting(para.id, true)
      const updated = await api.extractParagraphText(para.doc_id, para.chapter_id, para.id)
      updateParagraph(para.id, {
        extracted_text: updated.extracted_text,
        image_url: updated.image_url,
      })
      setIsExtractedOpen(true)
    } catch (e) {
      alert('提取图文内容失败: ' + (e as Error).message)
    } finally {
      setLocalExtracting(false)
      setParaExtracting(para.id, false)
    }
  }

  const handleSplitAtCursor = () => {
    if (!editTextareaRef.current) {
      setHasNewParagraph(true)
      return
    }
    const textarea = editTextareaRef.current
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    let splitContent = ''
    let remainingContent = ''

    if (start !== end) {
      splitContent = editText.slice(start, end).trim()
      remainingContent = (editText.slice(0, start) + editText.slice(end)).trim()
    } else if (start > 0 && start < editText.length) {
      remainingContent = editText.slice(0, start).trim()
      splitContent = editText.slice(start).trim()
    }

    if (splitContent) {
      setEditText(remainingContent)
      setNewParaText(splitContent)
      setHasNewParagraph(true)
    } else {
      setHasNewParagraph(true)
    }
  }

  const handleSaveEdit = async (retranslate: boolean) => {
    if (!para.doc_id || !para.chapter_id || !editText.trim()) return
    try {
      setIsSavingEdit(true)
      const res = await api.editParagraph(
        para.doc_id,
        para.chapter_id,
        para.id,
        editText,
        {
          retranslate: false,
          new_paragraph_text: hasNewParagraph && newParaText.trim() ? newParaText.trim() : undefined,
          type: editType === 'heading' ? 'text' : editType,
          is_heading: editType === 'heading' || editText.trim().startsWith('#'),
        }
      )
      setIsEditing(false)
      setHasNewParagraph(false)
      setNewParaText('')

      const updated = res.updated_paragraph
      const newP = res.new_paragraph

      if (retranslate) {
        replaceParagraph({
          ...updated,
          status: 'translating',
          translated_text: '',
        })
        onRetranslate(updated)
      } else {
        replaceParagraph(updated)
      }

      if (newP) {
        if (retranslate) {
          insertParagraphAfter(para.id, {
            ...newP,
            status: 'translating',
            translated_text: '',
          })
          onRetranslate(newP)
        } else {
          insertParagraphAfter(para.id, newP)
        }
      }
    } catch (e) {
      alert('保存段落修改失败: ' + (e as Error).message)
    } finally {
      setIsSavingEdit(false)
    }
  }

  const handleDeleteParagraph = async () => {
    if (!para.doc_id || !para.chapter_id || isDeletingPara) return
    const confirmed = window.confirm(
      '确定要删除本段吗？\n删除后将一并清理本段的所有笔记、问答聊天历史、翻译结果及关联卡片，此操作不可撤销。'
    )
    if (!confirmed) return

    try {
      setIsDeletingPara(true)
      await api.deleteParagraph(para.doc_id, para.chapter_id, para.id)
      removeParagraph(para.id)
      if (para.doc_id) {
        useStore.getState().refreshDocFlashcardCount(para.doc_id)
      }
      setIsEditing(false)
    } catch (e) {
      alert('删除段落失败: ' + (e as Error).message)
    } finally {
      setIsDeletingPara(false)
    }
  }

  const handleMerge = async (direction: 'prev' | 'next', retranslate = false) => {
    if (!para.doc_id || !para.chapter_id || isMerging || currentlyTranslating) return
    try {
      setIsMerging(true)
      const res = await api.mergeParagraphs(
        para.doc_id,
        para.chapter_id,
        para.id,
        direction,
        false
      )
      const merged = res.merged_paragraph
      if (retranslate) {
        replaceParagraph({
          ...merged,
          status: 'translating',
          translated_text: '',
        })
        removeParagraph(res.removed_id)
        onRetranslate(merged)
      } else {
        replaceParagraph(merged)
        removeParagraph(res.removed_id)
      }
    } catch (e) {
      alert('合并段落失败: ' + (e as Error).message)
    } finally {
      setIsMerging(false)
    }
  }

  const actionButtons = (
    <div className="flex items-center gap-1 bg-card/95 backdrop-blur-md px-2 py-0.5 rounded-full border border-border shadow-md pointer-events-auto">
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-[11px] gap-1 text-primary hover:bg-primary/10 rounded-full"
        onClick={onAsk}
        title="向 AI 助教提问本段"
      >
        <Bot className="h-3 w-3" />
        <span>助教</span>
      </Button>
      {isImage && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-[11px] gap-1 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500/10 rounded-full"
          onClick={handleExtract}
          disabled={isExtracting}
          title="从图片中高精度提取文字内容"
        >
          {isExtracting ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <FileText className="h-3 w-3" />
          )}
          <span>{para.extracted_text ? '重提' : '提取'}</span>
        </Button>
      )}

      {/* In-place Edit Button */}
      <Button
        variant="ghost"
        size="sm"
        disabled={currentlyTranslating}
        className={`h-6 px-2 text-[11px] gap-1 rounded-full ${
          isEditing ? 'bg-primary/15 text-primary font-medium' : 'text-muted-foreground hover:text-foreground'
        }`}
        onClick={() => {
          setEditText(para.source_text)
          setIsEditing(!isEditing)
        }}
        title="就地编辑此段原文及格式"
      >
        <Pencil className="h-3 w-3" />
        <span>{isEditing ? '编辑中' : '编辑'}</span>
      </Button>

      {/* Merge Dropdown Menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground rounded-full"
            disabled={isMerging || currentlyTranslating}
            title="段落缝合与合并"
          >
            {isMerging ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <GitMerge className="h-3 w-3" />
            )}
            <span>合并</span>
            <ChevronDown className="h-2.5 w-2.5 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48 text-xs">
          <div className="px-2 py-1 text-[10px] font-medium text-muted-foreground">段落合并</div>
          <DropdownMenuItem
            disabled={isFirst || isMerging || currentlyTranslating}
            onClick={() => handleMerge('prev', false)}
            className="cursor-pointer gap-2 py-1.5"
          >
            <ArrowUp className="h-3.5 w-3.5 text-primary" />
            <span>与上一段合并</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={isFirst || isMerging || currentlyTranslating}
            onClick={() => handleMerge('prev', true)}
            className="cursor-pointer gap-2 py-1.5 text-primary font-medium"
          >
            <RefreshCw className="h-3.5 w-3.5 text-primary" />
            <span>与上一段合并并重译</span>
          </DropdownMenuItem>
          <div className="h-px bg-border/50 my-1" />
          <DropdownMenuItem
            disabled={isLast || isMerging || currentlyTranslating}
            onClick={() => handleMerge('next', false)}
            className="cursor-pointer gap-2 py-1.5"
          >
            <ArrowDown className="h-3.5 w-3.5 text-primary" />
            <span>与下一段合并</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={isLast || isMerging || currentlyTranslating}
            onClick={() => handleMerge('next', true)}
            className="cursor-pointer gap-2 py-1.5 text-primary font-medium"
          >
            <RefreshCw className="h-3.5 w-3.5 text-primary" />
            <span>与下一段合并并重译</span>
          </DropdownMenuItem>

          <div className="h-px bg-border/50 my-1" />
          <div className="px-2 py-1 text-[10px] font-medium text-muted-foreground">跨章节操作</div>
          <DropdownMenuItem
            disabled={isFirstChapter || isShifting || currentlyTranslating}
            onClick={() => handleShiftChapter('prev')}
            className="cursor-pointer gap-2 py-1.5"
            title={isFirstChapter ? '当前为第一章，无上一章' : '将本段往上(含本段)的所有段落合并到上一章结尾'}
          >
            <ArrowUpLeft className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            <span>合并到上一章</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={isLastChapter || isShifting || currentlyTranslating}
            onClick={() => handleShiftChapter('next')}
            className="cursor-pointer gap-2 py-1.5"
            title={isLastChapter ? '当前为最后一章，无下一章' : '将本段往下(含本段)的所有段落合并到下一章开头'}
          >
            <ArrowDownRight className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            <span>合并到下一章</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={isFirst || isSplitting || currentlyTranslating}
            onClick={handleOpenSplitModal}
            className="cursor-pointer gap-2 py-1.5 text-indigo-600 dark:text-indigo-400 font-medium"
            title={isFirst ? '首段无需拆分章节' : '从本段开始拆分为一个全新的章节'}
          >
            <Scissors className="h-3.5 w-3.5" />
            <span>从本段拆为新章节</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {!isSourceChinese && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground rounded-full"
          onClick={() => onRetranslate(para)}
          disabled={currentlyTranslating}
          title={currentlyTranslating ? '正在翻译中...' : '重新翻译此段'}
        >
          <RefreshCw className={`h-3 w-3 ${currentlyTranslating ? 'animate-spin text-primary' : ''}`} />
          <span className={currentlyTranslating ? 'text-primary font-medium' : ''}>
            {currentlyTranslating ? '翻译中' : '重译'}
          </span>
        </Button>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-[11px] gap-1 text-amber-500 hover:text-amber-600 hover:bg-amber-500/10 rounded-full"
        onClick={onQuickFlashcard}
        title="将本段考点快速制作成闪卡"
      >
        <Sparkles className="h-3 w-3" />
        <span>制卡</span>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-[11px] gap-1 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10 rounded-full"
        onClick={() =>
          openNoteModal({
            chapterId: para.chapter_id || activeChapterId || '',
            type: 'paragraph',
            paragraphId: para.id,
          })
        }
        title="为本段添加研读注解或笔记"
      >
        <Bookmark className="h-3 w-3" />
        <span>笔记{para.notes && para.notes.length > 0 ? ` (${para.notes.length})` : ''}</span>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground rounded-full"
        onClick={() => onCopy(para.extracted_text || para.translated_text || para.source_text)}
        title="复制文本"
      >
        {isCopied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
        <span>{isCopied ? '已复制' : '复制'}</span>
      </Button>
    </div>
  )

  const inlineEditor = (
    <div className="space-y-2.5 p-3 rounded-xl border border-primary/40 bg-card/90 shadow-xs animate-in fade-in duration-150">
      <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
            <Pencil className="h-3.5 w-3.5 text-primary" /> 编辑段落
          </span>

          {/* Paragraph Type Selector */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 px-2 text-[11px] gap-1 border-border/70 bg-background/60 hover:bg-accent font-normal"
                title="选择段落类型"
              >
                <span className="text-muted-foreground">类型:</span>
                <span className="font-medium text-foreground">
                  {editType === 'image' && '🖼️ 图片'}
                  {editType === 'heading' && '📌 标题'}
                  {editType === 'code' && '💻 代码'}
                  {editType === 'text' && '📝 正文'}
                </span>
                <ChevronDown className="h-3 w-3 opacity-60 ml-0.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="text-xs min-w-[130px]">
              <DropdownMenuItem
                onClick={() => handleSelectType('text')}
                className={editType === 'text' ? 'font-semibold text-primary' : ''}
              >
                📝 普通正文
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => handleSelectType('heading')}
                className={editType === 'heading' ? 'font-semibold text-primary' : ''}
              >
                📌 章节标题
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => handleSelectType('image')}
                className={editType === 'image' ? 'font-semibold text-primary' : ''}
              >
                🖼️ 图片插图
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => handleSelectType('code')}
                className={editType === 'code' ? 'font-semibold text-primary' : ''}
              >
                💻 代码块
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant={editType === 'text' ? 'secondary' : 'ghost'}
            size="sm"
            className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground"
            onClick={() => handleSelectType('text')}
            title="转换为普通正文"
          >
            正文
          </Button>
          <Button
            type="button"
            variant={editType === 'heading' && editText.trim().startsWith('# ') ? 'secondary' : 'ghost'}
            size="sm"
            className="h-6 px-1.5 text-[11px] font-bold text-muted-foreground hover:text-foreground"
            onClick={() => {
              setEditText((prev) => '# ' + prev.replace(/^[#\s]+/, ''))
              setEditType('heading')
              setIsTypeUserOverridden(true)
            }}
            title="设为一级大标题 (#)"
          >
            H1
          </Button>
          <Button
            type="button"
            variant={editType === 'heading' && editText.trim().startsWith('## ') ? 'secondary' : 'ghost'}
            size="sm"
            className="h-6 px-1.5 text-[11px] font-bold text-muted-foreground hover:text-foreground"
            onClick={() => {
              setEditText((prev) => '## ' + prev.replace(/^[#\s]+/, ''))
              setEditType('heading')
              setIsTypeUserOverridden(true)
            }}
            title="设为二级标题 (##)"
          >
            H2
          </Button>
          <Button
            type="button"
            variant={editType === 'heading' && editText.trim().startsWith('### ') ? 'secondary' : 'ghost'}
            size="sm"
            className="h-6 px-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground"
            onClick={() => {
              setEditText((prev) => '### ' + prev.replace(/^[#\s]+/, ''))
              setEditType('heading')
              setIsTypeUserOverridden(true)
            }}
            title="设为三级标题 (###)"
          >
            H3
          </Button>
        </div>
      </div>

      {/* Auto-Detection Notification Banner when Image is converted to Text */}
      {isImage && editType === 'text' && (
        <div className="flex items-center justify-between text-[11px] px-2.5 py-1.5 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 animate-in fade-in duration-150">
          <span>💡 检测到图片已被替换为纯文本，保存后将自动转为普通文本段落并支持常规翻译。</span>
          <button
            type="button"
            className="underline hover:opacity-80 text-[10px] ml-2 shrink-0 font-medium cursor-pointer"
            onClick={() => {
              setEditText(para.source_text)
              setEditType('image')
              setIsTypeUserOverridden(false)
            }}
          >
            还原原图
          </button>
        </div>
      )}

      <Textarea
        ref={editTextareaRef}
        value={editText}
        onChange={(e) => handleEditTextChange(e.target.value)}
        className="min-h-[90px] text-xs leading-relaxed resize-y font-mono bg-background/90"
        placeholder="请输入或修改段落内容..."
      />

      {/* New Paragraph Sub-Editor (when user wants to split or append a new paragraph) */}
      {hasNewParagraph && (
        <div className="space-y-2 pt-2.5 pb-1 border-t border-dashed border-primary/30 animate-in fade-in slide-in-from-top-1 duration-150">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold flex items-center gap-1.5 text-primary">
              <GitFork className="h-3.5 w-3.5 rotate-180" />
              <span>新段落（将插入到本段之后）</span>
            </span>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
                onClick={() => setNewParaText((prev) => prev.replace(/^[#\s]+/, ''))}
                title="转为普通正文"
              >
                正文
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[10px] font-bold text-muted-foreground hover:text-foreground"
                onClick={() => setNewParaText((prev) => '# ' + prev.replace(/^[#\s]+/, ''))}
                title="设为一级标题 (#)"
              >
                H1
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[10px] font-bold text-muted-foreground hover:text-foreground"
                onClick={() => setNewParaText((prev) => '## ' + prev.replace(/^[#\s]+/, ''))}
                title="设为二级标题 (##)"
              >
                H2
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 px-1 text-[10px] text-muted-foreground hover:text-destructive"
                onClick={() => {
                  setHasNewParagraph(false)
                  setNewParaText('')
                }}
                title="取消新增此段落"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
          <Textarea
            value={newParaText}
            onChange={(e) => setNewParaText(e.target.value)}
            className="min-h-[80px] text-xs leading-relaxed resize-y font-mono bg-background/90 border-primary/40 focus-visible:ring-primary/40"
            placeholder="输入或粘贴新段落内容（可在此调整格式，保存后将自动成为一个独立段落）..."
          />
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-1 border-t border-border/40">
        <div className="flex items-center gap-1.5">
          {!hasNewParagraph ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 text-primary border-dashed border-primary/40 hover:bg-primary/5 hover:border-primary"
              onClick={handleSplitAtCursor}
              title="在下方新增段落；若上方已选中文本或定位光标，将自动剪切拆分至新段"
            >
              <Plus className="h-3 w-3" />
              <span>追加/拆分新段</span>
            </Button>
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              onClick={() => {
                setHasNewParagraph(false)
                setNewParaText('')
              }}
              title="取消新增段落"
            >
              <X className="h-3 w-3" />
              <span>移除新段</span>
            </Button>
          )}

          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1 text-destructive/80 hover:text-destructive hover:bg-destructive/10"
            onClick={handleDeleteParagraph}
            disabled={isDeletingPara || isSavingEdit}
            title="删除本段及其关联笔记、问答记录与翻译"
          >
            {isDeletingPara ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Trash2 className="h-3 w-3" />
            )}
            <span>删除本段</span>
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => {
              setEditText(para.source_text)
              setHasNewParagraph(false)
              setNewParaText('')
              setIsEditing(false)
            }}
            disabled={isSavingEdit || isDeletingPara}
          >
            取消
          </Button>
          {shouldSkipRetranslate ? (
            <Button
              type="button"
              variant="default"
              size="sm"
              className="h-7 text-xs gap-1 bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={() => handleSaveEdit(false)}
              disabled={isSavingEdit || isDeletingPara || !editText.trim() || (hasNewParagraph && !newParaText.trim())}
            >
              {isSavingEdit ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              保存内容
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => handleSaveEdit(false)}
                disabled={isSavingEdit || isDeletingPara || !editText.trim() || (hasNewParagraph && !newParaText.trim())}
              >
                {isSavingEdit ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                仅保存原文
              </Button>
              <Button
                type="button"
                variant="default"
                size="sm"
                className="h-7 text-xs gap-1 bg-primary text-primary-foreground hover:bg-primary/90"
                onClick={() => handleSaveEdit(true)}
                disabled={isSavingEdit || isDeletingPara || !editText.trim() || (hasNewParagraph && !newParaText.trim())}
              >
                {isSavingEdit ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-0.5" />
                )}
                保存并重译
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )

  const sourceContent = (
    <div
      className="text-muted-foreground leading-relaxed selection:bg-primary/20 space-y-2"
      style={{ fontSize: `${fontSize - 1}px`, lineHeight: 1.65 }}
    >
      {para.source_text?.includes('![') ? (
        <div
          className="para-markdown rounded-lg overflow-hidden [&_img]:rounded-lg [&_img]:border [&_img]:border-border/60 [&_img]:shadow-sm [&_img]:max-h-[650px] [&_img]:object-contain [&_img]:bg-muted/10"
          dangerouslySetInnerHTML={{ __html: marked.parse(normalizeDocImageUrls(para.source_text || '', activeDoc?.doc_id)) as string }}
        />
      ) : (
        <div
          className="para-markdown prose prose-sm dark:prose-invert max-w-none break-words [&_h1]:text-xl [&_h1]:font-bold [&_h1]:text-foreground [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-foreground [&_h2]:mt-1 [&_h2]:mb-2 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-foreground/90 [&_p]:my-1"
          dangerouslySetInnerHTML={{ __html: marked.parse(normalizeDocImageUrls(para.source_text || '', activeDoc?.doc_id)) as string }}
        />
      )}

      {/* Collapsible Extracted Text for Images / Scanned Pages */}
      {isImage && (
        <div className="pt-1">
          {para.extracted_text ? (
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setIsExtractedOpen(!isExtractedOpen)}
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground bg-muted/40 hover:bg-muted/70 px-2.5 py-1 rounded-md border border-border/60 transition-colors cursor-pointer"
              >
                <FileText className="h-3.5 w-3.5 text-primary" />
                <span>{isExtractedOpen ? '收起识别文本' : '查看识别文本'}</span>
                <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.2 rounded-full font-mono">
                  {para.extracted_text.length} 字
                </span>
                {isExtractedOpen ? <ChevronUp className="h-3 w-3 opacity-60" /> : <ChevronDown className="h-3 w-3 opacity-60" />}
              </button>

              {isExtractedOpen && (
                <div className="bg-card/95 border border-border rounded-xl p-3.5 space-y-2 shadow-xs animate-in fade-in duration-200">
                  <div className="flex items-center justify-between border-b border-border/50 pb-2">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                      <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                      <span>图片提取文本 (已转录)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                        onClick={() => onCopy(para.extracted_text!, `ocr_${para.id}`)}
                        title="复制识别出的文本"
                      >
                        {isCopied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                        <span>{isCopied ? '已复制' : '复制文本'}</span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                        onClick={() => setIsExtractedOpen(false)}
                      >
                        <ChevronUp className="h-3.5 w-3.5" />
                        <span>收起</span>
                      </Button>
                    </div>
                  </div>
                  <div className="text-xs text-foreground/90 font-mono leading-relaxed whitespace-pre-wrap selection:bg-primary/20 max-h-72 overflow-y-auto pr-1">
                    {para.extracted_text}
                  </div>
                </div>
              )}
            </div>
          ) : isExtracting ? (
            <div className="inline-flex items-center gap-2 text-xs text-cyan-700 dark:text-cyan-300 bg-cyan-500/10 px-3 py-1.5 rounded-md border border-cyan-500/30">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-500" />
              <span>正在高精度提取文字内容...</span>
            </div>
          ) : (
            <button
              type="button"
              onClick={handleExtract}
              className="inline-flex items-center gap-1.5 text-xs text-cyan-700 dark:text-cyan-300 hover:text-foreground bg-cyan-500/10 hover:bg-cyan-500/20 px-2.5 py-1 rounded-md border border-cyan-500/30 transition-colors cursor-pointer"
            >
              <FileText className="h-3.5 w-3.5" />
              <span>🔍 从图片提取文字内容</span>
            </button>
          )}
        </div>
      )}
    </div>
  )

  const hasTranslation = Boolean(
    (para.translated_text &&
      para.translated_text.trim() &&
      para.translated_text.trim() !== para.source_text?.trim()) ||
    para.status === 'translating' ||
    currentlyTranslating
  )

  const translationContent = hasTranslation ? (
    <div
      className="leading-relaxed font-normal"
      style={{ fontSize: `${fontSize}px`, lineHeight: 1.7 }}
    >
      {para.status === 'translating' || currentlyTranslating ? (
        <div className="flex items-center gap-2 text-primary text-xs py-1.5">
          <span className="w-2 h-2 rounded-full bg-primary animate-ping" />
          <span>正在精读翻译中...</span>
        </div>
      ) : (
        <div
          className="para-markdown"
          dangerouslySetInnerHTML={{ __html: marked.parse(normalizeDocImageUrls(para.translated_text || '', activeDoc?.doc_id)) as string }}
        />
      )}
    </div>
  ) : null

  const notesContent =
    para.notes && para.notes.length > 0 ? (
      <div className="space-y-2 pt-2 mt-2 border-t border-border/40">
        {para.notes.map((note, idx) => (
          <div
            key={note.id || idx}
            className="bg-amber-500/5 dark:bg-amber-500/10 border border-amber-500/20 rounded-lg p-2.5 text-xs space-y-1.5 transition-all hover:border-amber-500/40"
          >
            <div className="flex items-center justify-between text-muted-foreground">
              <div className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400 text-[11px]">
                <Bookmark className="h-3 w-3" />
                <span>研读注解 #{idx + 1}</span>
                {note.created_at && (
                  <span className="text-[10px] text-muted-foreground font-mono opacity-80">
                    {note.created_at.slice(5, 16)}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-1.5 text-[10px] gap-1 text-muted-foreground hover:text-foreground"
                  onClick={() =>
                    openNoteModal({
                      chapterId: para.chapter_id || activeChapterId || '',
                      type: 'paragraph',
                      paragraphId: para.id,
                      noteId: note.id,
                      content: note.content,
                    })
                  }
                  title="编辑注解"
                >
                  <Pencil className="h-3 w-3" />
                  <span>编辑</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-1.5 text-[10px] gap-1 text-muted-foreground hover:text-destructive"
                  onClick={async () => {
                    if (!confirm('确定删除该段落注解吗？')) return
                    if (activeDoc?.doc_id && (para.chapter_id || activeChapterId)) {
                      await api.deleteParagraphNote(
                        activeDoc.doc_id,
                        para.chapter_id || activeChapterId!,
                        para.id,
                        note.id
                      )
                      await refreshActiveDocContent()
                    }
                  }}
                  title="删除注解"
                >
                  <Trash2 className="h-3 w-3" />
                  <span>删除</span>
                </Button>
              </div>
            </div>
            <div
              className="para-markdown note-markdown text-xs text-foreground leading-relaxed pl-1"
              dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdownListHelper(note.content || '')) as string }}
            />
          </div>
        ))}
      </div>
    ) : null

  const splitModal = showSplitModal && (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-card border border-border/80 rounded-xl shadow-2xl max-w-sm w-full p-5 space-y-4">
        <div className="flex items-center gap-2.5 text-primary">
          <Scissors className="h-5 w-5 text-indigo-500" />
          <h3 className="font-semibold text-base text-foreground">从本段拆分为新章节</h3>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          将从当前段落开始（包含本段）直至本章末尾的所有段落，剥离并生成一个全新的独立章节。
        </p>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground">新章节名称</label>
          <input
            type="text"
            value={newChapterTitle}
            onChange={(e) => setNewChapterTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                handleConfirmSplit()
              } else if (e.key === 'Escape') {
                setShowSplitModal(false)
              }
            }}
            autoFocus
            className="w-full px-3 py-1.5 text-xs bg-muted/50 border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            placeholder="请输入新章节标题..."
          />
        </div>
        <div className="flex items-center justify-end gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowSplitModal(false)}
            disabled={isSplitting}
          >
            取消
          </Button>
          <Button
            size="sm"
            onClick={handleConfirmSplit}
            disabled={!newChapterTitle.trim() || isSplitting}
            className="gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {isSplitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            <span>确认拆分</span>
          </Button>
        </div>
      </div>
    </div>
  )

  let cardContent = null

  // 1. Card View Mode
  if (isCard) {
    cardContent = (
      <div className="group relative rounded-xl transition-all bg-card/80 border border-border/80 p-5 shadow-xs hover:border-primary/40 hover:shadow-md pt-5">
        {/* Floating actions elevated above top border, never obscuring text */}
        <div className={`absolute -top-3.5 right-4 ${isEditing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-all duration-150 pointer-events-none z-20`}>
          {actionButtons}
        </div>
        <div className="space-y-3 pt-1">
          {/* Source Column */}
          {isEditing ? inlineEditor : sourceContent}
          {/* Translated Chinese Quote Box */}
          {hasTranslation && (
            <div className="bilingual-quote transition-colors">
              {translationContent}
            </div>
          )}
          {notesContent}
        </div>
      </div>
    )
  } else if (isSide) {
    // 2. Side-by-Side View Mode
    cardContent = (
      <div className="group relative rounded-lg border-b border-border/40 hover:bg-card/30 transition-colors p-3.5 pt-4">
        {/* Floating actions elevated above top border, never obscuring text */}
        <div className={`absolute -top-3.5 right-4 ${isEditing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-all duration-150 pointer-events-none z-20`}>
          {actionButtons}
        </div>
        <div className="space-y-3 pt-1">
          <div className={`grid ${hasTranslation ? 'grid-cols-1 md:grid-cols-2 gap-6' : 'grid-cols-1'} items-start`}>
            {/* Source Column */}
            <div className={hasTranslation ? "md:pr-4 md:border-r md:border-border/50" : ""}>
              {isEditing ? inlineEditor : sourceContent}
            </div>
            {/* Translation Column */}
            {hasTranslation && (
              <div className="text-foreground md:pl-1">
                {translationContent}
              </div>
            )}
          </div>
          {notesContent}
        </div>
      </div>
    )
  } else {
    // 3. Stack View Mode (Default: 上下对照)
    cardContent = (
      <div className="group relative rounded-lg border-b border-border/40 hover:bg-card/30 transition-colors p-3.5 pt-4">
        {/* Floating actions elevated above top border, never obscuring text */}
        <div className={`absolute -top-3.5 right-4 ${isEditing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-all duration-150 pointer-events-none z-20`}>
          {actionButtons}
        </div>
        <div className="space-y-2.5 pt-1">
          {/* Source Column */}
          {isEditing ? inlineEditor : sourceContent}
          {/* Translated Chinese in Quote Box */}
          {hasTranslation && (
            <div className="bilingual-quote transition-colors">
              {translationContent}
            </div>
          )}
          {notesContent}
        </div>
      </div>
    )
  }

  return (
    <>
      {cardContent}
      {splitModal}
    </>
  )
}
