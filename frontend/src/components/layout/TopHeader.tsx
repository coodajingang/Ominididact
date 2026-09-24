import React, { useEffect, useState } from 'react'
import {
  Menu,
  Settings,
  Bot,
  Download,
  Zap,
  Pause,
  ChevronLeft,
  ChevronRight,
  Type,
  Minus,
  Plus,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover'

export function TopHeader({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const {
    activeDoc,
    chapters,
    activeChapterId,
    selectChapter,
    setDocSettingsModalOpen,
    isAssistantOpen,
    setAssistantOpen,
    setAssistantScope,
    setSelectedParagraph,
    docFlashcardCount,
    refreshDocFlashcardCount,
    docBatchStatus,
    chapterBatchStatus,
    isBatchTranslating,
    startChapterTranslate,
    stopChapterTranslate,
    startDocTranslate,
    stopDocTranslate,
    pollBatchTranslateStatus,
    isHeaderVisible,
    fontSize,
    setFontSize,
    readingWidth,
    setReadingWidth,
    layoutMode,
    setLayoutMode,
    fontFamily,
    setFontFamily,
  } = useStore()

  const [isHovered, setIsHovered] = useState(false)
  const [openDropdowns, setOpenDropdowns] = useState(0)

  const handleDropdownOpenChange = (open: boolean) => {
    setOpenDropdowns((prev) => (open ? prev + 1 : Math.max(0, prev - 1)))
  }

  const isVisible = isHeaderVisible || isHovered || openDropdowns > 0

  // Ensure flashcard count is fetched on activeDoc change and window focus / tab switch
  React.useEffect(() => {
    const docId = activeDoc?.doc_id
    if (!docId) return

    refreshDocFlashcardCount(docId)

    const handleFocus = () => {
      refreshDocFlashcardCount(docId)
    }
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refreshDocFlashcardCount(docId)
      }
    }

    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [activeDoc?.doc_id, refreshDocFlashcardCount])

  const currentChapter = chapters.find((c) => c.chapter_id === activeChapterId) || (chapters.length > 0 ? chapters[0] : null)
  const currentChapterIdx = currentChapter ? chapters.findIndex((c) => c.chapter_id === currentChapter.chapter_id) : -1

  return (
    <>
      {/* Invisible Hover Detection Zone at the top edge of screen */}
      <div
        className="absolute top-0 left-0 right-0 h-4 z-40 pointer-events-auto"
        onMouseEnter={() => setIsHovered(true)}
      />

      <header
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`absolute top-0 left-0 right-0 h-14 border-b border-border/70 bg-card/85 backdrop-blur-xl px-4 flex items-center justify-between flex-shrink-0 z-30 transition-all duration-300 ease-in-out ${
          isVisible
            ? 'translate-y-0 opacity-100 shadow-xs pointer-events-auto'
            : '-translate-y-full opacity-0 pointer-events-none shadow-none'
        }`}
      >
        {/* Left: Document & Chapter Info */}
        <div className="flex items-center gap-2.5 min-w-0">
          <Button variant="ghost" size="icon-sm" onClick={onToggleSidebar} title="折叠/展开侧边栏">
            <Menu className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-1.5 text-sm min-w-0 max-w-[320px] md:max-w-[460px]">
            <span className="font-semibold truncate text-foreground" title={activeDoc?.title}>
              {activeDoc?.title || '请选择或上传文档'}
            </span>
            {currentChapter && (
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-muted-foreground/40 font-light">/</span>
                <span className="text-xs text-primary font-medium truncate max-w-[140px] md:max-w-[200px]" title={currentChapter.title}>
                  {currentChapter.title}
                </span>
                {/* 暂时注释掉 顶部面包屑翻章支持
                {chapters.length > 1 && (
                  <div className="flex items-center bg-muted/60 rounded-md border border-border/50 px-1 py-0.5 gap-0.5 shrink-0">
                    <button
                      type="button"
                      disabled={currentChapterIdx <= 0}
                      onClick={() => {
                        if (currentChapterIdx > 0) {
                          selectChapter(chapters[currentChapterIdx - 1].chapter_id)
                        }
                      }}
                      className="text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-20 px-0.5 transition-colors cursor-pointer disabled:cursor-not-allowed"
                      title="切换到上一章"
                    >
                      <ChevronLeft className="h-3 w-3" />
                    </button>
                    <span className="text-[10px] px-1 text-primary font-mono font-medium">
                      {currentChapterIdx + 1}/{chapters.length}
                    </span>
                    <button
                      type="button"
                      disabled={currentChapterIdx >= chapters.length - 1}
                      onClick={() => {
                        if (currentChapterIdx < chapters.length - 1) {
                          selectChapter(chapters[currentChapterIdx + 1].chapter_id)
                        }
                      }}
                      className="text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-20 px-0.5 transition-colors cursor-pointer disabled:cursor-not-allowed"
                      title="切换到下一章"
                    >
                      <ChevronRight className="h-3 w-3" />
                    </button>
                  </div>
                )}
                */}
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0 font-mono">
                  {currentChapterIdx + 1}/{chapters.length}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Controls & Actions (顺序: AI研学、批量翻译、闪卡、导出、翻译设置) */}
        <div className="flex items-center gap-2">
          {/* 1. AI Assistant Toggle Button */}
          <Button
            variant={isAssistantOpen ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              if (!isAssistantOpen) {
                setSelectedParagraph(null)
                setAssistantScope('document')
                setAssistantOpen(true)
              } else {
                setAssistantOpen(false)
              }
            }}
            className="text-xs h-8 gap-1.5 shadow-sm"
          >
            <Bot className="h-3.5 w-3.5" />
            <span>AI 研学</span>
          </Button>

          {/* 2. Batch Translation Dropdown */}
          <DropdownMenu
            onOpenChange={(open) => {
              handleDropdownOpenChange(open)
              if (open && activeDoc?.doc_id) {
                pollBatchTranslateStatus(activeDoc.doc_id, activeChapterId || undefined)
              }
            }}
          >
          <DropdownMenuTrigger asChild>
            <Button
              variant="subtle"
              size="sm"
              className={`text-xs h-8 gap-1.5 transition-all ${
                isBatchTranslating
                  ? 'text-amber-500 hover:text-amber-600 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30'
                  : 'text-sky-500 hover:text-sky-600 hover:bg-sky-500/10 border border-sky-500/20'
              }`}
              title="批量翻译本文档或当前章节"
            >
              {isBatchTranslating ? (
                <>
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                  </span>
                  <span>
                    {docBatchStatus?.is_doc_level_running
                      ? `全篇翻译中 (${docBatchStatus.percent}%)`
                      : `本章翻译中 (${chapterBatchStatus?.percent || 0}%)`}
                  </span>
                </>
              ) : (
                <>
                  <Zap className="h-3.5 w-3.5 text-sky-500" />
                  <span>⚡ 批量翻译</span>
                </>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <div className="px-3 py-2 border-b border-border/50 text-[11px] text-muted-foreground flex justify-between items-center">
              <span className="font-semibold text-foreground">批量自动翻译</span>
              {isBatchTranslating && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 font-mono animate-pulse">
                  后台执行中
                </span>
              )}
            </div>

            {isBatchTranslating && (
              <>
                <DropdownMenuItem
                  className="text-red-500 focus:text-red-600 focus:bg-red-500/10 font-medium text-xs gap-2"
                  onClick={() => {
                    if (docBatchStatus?.is_doc_level_running) {
                      stopDocTranslate()
                    } else {
                      stopChapterTranslate()
                    }
                  }}
                >
                  <Pause className="h-3.5 w-3.5" />
                  <span>⏸️ 停止当前后台批量翻译</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}

            <DropdownMenuItem
              disabled={isBatchTranslating}
              onClick={() => {
                if (!activeDoc) {
                  alert('请先选择或上传文档')
                  return
                }
                if (!activeChapterId) {
                  alert('请先选择章节')
                  return
                }
                startChapterTranslate(activeDoc.doc_id, activeChapterId)
              }}
              className="flex flex-col items-start gap-0.5 py-2 cursor-pointer"
            >
              <div className="flex items-center gap-1.5 font-medium text-xs text-foreground">
                <span>⚡ 批量翻译当前章节</span>
              </div>
              <div className="text-[11px] text-muted-foreground">
                {currentChapter ? currentChapter.title : '当前章节'}
                {chapterBatchStatus?.untranslated !== undefined
                  ? ` · ${chapterBatchStatus.untranslated} 段未译`
                  : ''}
              </div>
            </DropdownMenuItem>

            <DropdownMenuItem
              disabled={isBatchTranslating}
              onClick={() => {
                if (!activeDoc) {
                  alert('请先选择或上传文档')
                  return
                }
                const confirmed = window.confirm(
                  `确定要开始批量翻译本文档全部 ${chapters.length} 个章节吗？\n后台将按序翻译所有未译段落，已翻译段落不会重复消耗 Token。`
                )
                if (confirmed) {
                  startDocTranslate(activeDoc.doc_id)
                }
              }}
              className="flex flex-col items-start gap-0.5 py-2 cursor-pointer"
            >
              <div className="flex items-center gap-1.5 font-medium text-xs text-foreground">
                <span>📚 批量翻译本文档 (全篇)</span>
              </div>
              <div className="text-[11px] text-muted-foreground">
                共 {chapters.length} 章
                {docBatchStatus?.untranslated !== undefined
                  ? ` · 全篇 ${docBatchStatus.untranslated} 段未译`
                  : activeDoc?.paragraph_count
                  ? ` · 约 ${Math.max(0, (activeDoc.paragraph_count || 0) - (activeDoc.translated_count || 0))} 段未译`
                  : ''}
              </div>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* 3. Flashcards Learning Dropdown */}
        <DropdownMenu
          onOpenChange={(open) => {
            handleDropdownOpenChange(open)
            if (open && activeDoc?.doc_id) refreshDocFlashcardCount(activeDoc.doc_id)
          }}
        >
          <DropdownMenuTrigger asChild>
            <Button
              variant="subtle"
              size="sm"
              className="text-xs h-8 gap-1.5 text-emerald-500 hover:text-emerald-600 hover:bg-emerald-500/10 border border-emerald-500/20"
              title="3D 闪卡自测与复习系统"
            >
              <img src="/static/brand/flashcard_icon.svg" alt="Flashcards" className="w-3.5 h-3.5 rounded object-contain" />
              <span>闪卡 {docFlashcardCount}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) {
                  alert('请先选择或上传文档')
                  return
                }
                window.open(`/study/flashcards?doc_id=${activeDoc.doc_id}&mode=study`, '_blank')
              }}
            >
              🧠 开始闪卡自测 (智能记忆) ↗
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) {
                  alert('请先选择或上传文档')
                  return
                }
                window.open(`/study/flashcards?doc_id=${activeDoc.doc_id}&mode=review`, '_blank')
              }}
            >
              🎯 错题攻坚复习 (艾宾浩斯) ↗
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) {
                  alert('请先选择或上传文档')
                  return
                }
                window.open(`/study/flashcards?doc_id=${activeDoc.doc_id}`, '_blank')
              }}
            >
              ⚙️ 闪卡工作台与卡片管理 ↗
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) return
                window.open(`/api/study/documents/${activeDoc.doc_id}/export?format=flashcards_html`, '_blank')
              }}
            >
              🗂️ 导出离线闪卡单文件 (.html)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* 4. Export Menu */}
        <DropdownMenu onOpenChange={handleDropdownOpenChange}>
          <DropdownMenuTrigger asChild>
            <Button variant="subtle" size="sm" className="text-xs h-8 gap-1">
              <Download className="h-3.5 w-3.5" />
              <span>导出</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) return
                window.open(`/api/study/documents/${activeDoc.doc_id}/export?format=html`, '_blank')
              }}
            >
              🌐 导出双语电子书 (.html)
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) return
                window.open(`/api/study/documents/${activeDoc.doc_id}/export?format=flashcards_html`, '_blank')
              }}
            >
              🗂️ 导出离线闪卡系统 (.html)
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) return
                window.open(`/api/study/documents/${activeDoc.doc_id}/export?format=site_zip`, '_blank')
              }}
            >
              🚀 导出独立单篇站点 (.zip)
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) return
                window.open(`/api/study/documents/${activeDoc.doc_id}/export?format=patch_zip`, '_blank')
              }}
            >
              🧩 导出知识库增量补丁包 (.zip)
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                if (!activeDoc) return
                window.open(`/api/study/documents/${activeDoc.doc_id}/export?format=markdown`, '_blank')
              }}
            >
              📄 导出单文件 Markdown (.md)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* 5. Reading Typography Popover (阅读排版调节) */}
        <Popover onOpenChange={handleDropdownOpenChange}>
          <PopoverTrigger asChild>
            <Button
              variant="subtle"
              size="sm"
              className="text-xs h-8 gap-1.5"
              title="阅读排版与显示调节 (字号、宽度、分栏、字体)"
            >
              <Type className="h-3.5 w-3.5 text-muted-foreground" />
              <span>排版</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 p-4 space-y-3.5 shadow-xl border-border/80 bg-card/95 backdrop-blur-xl">
            <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between border-b border-border/50 pb-2">
              <div className="flex items-center gap-1.5">
                <Type className="h-3.5 w-3.5 text-primary" />
                <span className="font-bold text-foreground">阅读排版设置</span>
              </div>
            </div>

            {/* Font Size Row */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">字号大小</span>
              <div className="flex items-center gap-1 bg-muted/70 border border-border/60 rounded-lg p-0.5 shadow-2xs">
                <button
                  type="button"
                  onClick={() => setFontSize((s) => Math.max(12, s - 1))}
                  disabled={fontSize <= 12}
                  className="h-6 w-6 rounded flex items-center justify-center text-xs hover:bg-card text-foreground disabled:opacity-30 transition-colors cursor-pointer"
                  title="缩小字号 (A-)"
                >
                  <Minus className="h-3 w-3" />
                </button>
                <span className="text-xs font-mono font-semibold px-2 min-w-[38px] text-center text-foreground">
                  {fontSize}px
                </span>
                <button
                  type="button"
                  onClick={() => setFontSize((s) => Math.min(26, s + 1))}
                  disabled={fontSize >= 26}
                  className="h-6 w-6 rounded flex items-center justify-center text-xs hover:bg-card text-foreground disabled:opacity-30 transition-colors cursor-pointer"
                  title="放大字号 (A+)"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
            </div>

            {/* Reading Width Row */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">阅读宽度</span>
              <div className="grid grid-cols-3 gap-1 bg-muted/70 border border-border/60 rounded-lg p-0.5 shadow-2xs">
                {(
                  [
                    { key: 'standard', label: '标准' },
                    { key: 'wide', label: '宽屏' },
                    { key: 'full', label: '全屏' },
                  ] as const
                ).map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setReadingWidth(item.key)}
                    className={`px-2.5 py-1 text-xs rounded font-medium transition-all cursor-pointer ${
                      readingWidth === item.key
                        ? 'bg-primary text-primary-foreground shadow-xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground hover:bg-card/60'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Layout Mode Row */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">双语对照</span>
              <div className="grid grid-cols-3 gap-1 bg-muted/70 border border-border/60 rounded-lg p-0.5 shadow-2xs">
                {(
                  [
                    { key: 'stack', label: '上下' },
                    { key: 'side', label: '左右' },
                    { key: 'card', label: '卡片' },
                  ] as const
                ).map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setLayoutMode(item.key)}
                    className={`px-2.5 py-1 text-xs rounded font-medium transition-all cursor-pointer ${
                      layoutMode === item.key
                        ? 'bg-primary text-primary-foreground shadow-xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground hover:bg-card/60'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Font Family Row */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">正文字体</span>
              <div className="grid grid-cols-4 gap-1 bg-muted/70 border border-border/60 rounded-lg p-0.5 shadow-2xs">
                {(
                  [
                    { key: 'sans', label: '黑体' },
                    { key: 'wenkai', label: '文楷' },
                    { key: 'serif', label: '宋体' },
                    { key: 'system', label: '原生' },
                  ] as const
                ).map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setFontFamily(item.key)}
                    className={`px-2 py-1 text-xs rounded font-medium transition-all cursor-pointer ${
                      fontFamily === item.key
                        ? 'bg-primary text-primary-foreground shadow-xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground hover:bg-card/60'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </PopoverContent>
        </Popover>


        {/* 7. Settings Button */}
        <Button
          variant="subtle"
          size="sm"
          onClick={() => setDocSettingsModalOpen(true)}
          className="text-xs h-8 gap-1"
        >
          <Settings className="h-3.5 w-3.5 text-muted-foreground" />
          <span>翻译设置</span>
        </Button>
      </div>
    </header>
  </>
)
}
