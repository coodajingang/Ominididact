import React, { useRef, useState } from 'react'
import {
  Upload,
  Trash2,
  Settings,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  RotateCcw,
  FolderDown,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import * as api from '@/api/client'

export function LeftSidebar({ isCollapsed, onToggle }: { isCollapsed: boolean; onToggle: () => void }) {
  const {
    documents,
    activeDocId,
    selectDocument,
    deleteDocument,
    resetDocProgress,
    setProviderModalOpen,
    loadDocuments,
    docReadingProgress,
  } = useStore()

  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const lowerName = file.name.toLowerCase()
    if (lowerName.endsWith('.ppt') || lowerName.endsWith('.pptx')) {
      alert(
        '💡 提示：为了完整保留 PPT 幻灯片的图表、排版与最佳双语研学体验，请在 PowerPoint、WPS 或 Keynote 中将该 PPT【另存为或导出为 PDF】后再上传！'
      )
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    try {
      setIsUploading(true)
      const doc = await api.uploadDocument(file)
      await loadDocuments()
      selectDocument(doc.doc_id)
    } catch (err) {
      alert('上传失败: ' + (err as Error).message)
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (isCollapsed) {
    return (
      <div className="w-12 h-screen border-r border-border bg-card/60 flex flex-col items-center py-3.5 gap-2.5 flex-shrink-0 z-20 select-none">
        {/* Project Logo / Icon */}
        <button
          onClick={onToggle}
          className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-accent/60 transition-all cursor-pointer group focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          title="Omnididact · 点击展开侧边栏"
        >
          <img
            src="/static/favicon.svg"
            alt="Omnididact"
            className="w-6 h-6 object-contain brand-logo transition-transform duration-200 group-hover:scale-110"
          />
        </button>

        <div className="w-6 h-px bg-border/60 my-0.5" />

        <Button variant="ghost" size="icon-sm" onClick={onToggle} title="展开侧边栏">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" onClick={() => setProviderModalOpen(true)} title="设置">
          <Settings className="h-4 w-4 text-muted-foreground hover:text-foreground" />
        </Button>
      </div>
    )
  }

  return (
    <aside className="w-[300px] h-screen border-r border-border bg-card/70 backdrop-blur-xl flex flex-col flex-shrink-0 select-none overflow-hidden">
      {/* Sidebar Header */}
      <div className="p-4 border-b border-border/60">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-sm tracking-tight text-foreground">
            <div className="w-7 h-7 flex items-center justify-center flex-shrink-0">
              <img src="/static/favicon.svg" alt="Omnididact" className="w-full h-full object-contain brand-logo" />
            </div>
            <span className="font-extrabold tracking-tight">Omnididact</span>
            <span className="text-[11px] font-normal text-muted-foreground font-mono">
              ({documents.length})
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => {
                if (documents.length === 0) {
                  alert('当前资料库暂无文档，请先上传并处理材料后再导出！')
                  return
                }
                window.open('/api/study/library/export', '_blank')
              }}
              title="导出全站静态多文档知识库包 (.zip)"
            >
              <FolderDown className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setProviderModalOpen(true)}
              title="设置"
            >
              <Settings className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={onToggle} title="折叠侧边栏">
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Upload Button */}
      <div className="p-3 border-b border-border/40">
        <input
          type="file"
          ref={fileInputRef}
          className="hidden"
          accept=".pdf,.docx,.doc,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp,.svg"
          onChange={handleFileUpload}
        />
        <Button
          variant="outline"
          className="w-full text-xs h-8 border-dashed border-primary/40 hover:border-primary hover:bg-primary/5 text-primary"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          <Upload className="h-3.5 w-3.5 mr-1.5" />
          {isUploading ? '正在处理上传...' : '上传材料 (PDF / 图片 / DOC / TXT / MD)'}
        </Button>
        <div className="text-[10px] text-muted-foreground/75 mt-1.5 px-1 text-center leading-tight">
          💡 支持学术图表/截图与文档；PPT 请另存为 PDF 上传
        </div>
      </div>

      {/* Main Document Library List */}
      <ScrollArea className="flex-1 w-full min-w-0">
        <div className="p-3 space-y-1.5 w-full min-w-0 box-border">
          {documents.length === 0 ? (
            <div className="text-center py-10 text-xs text-muted-foreground">
              暂无文档，请点击上方上传
            </div>
          ) : (
            documents.map((doc) => {
              const isActive = doc.doc_id === activeDocId
              const ratio = docReadingProgress[doc.doc_id] ?? 0
              const isDone = ratio >= 98
              const isReading = ratio > 0 && !isDone
              const extIcon =
                doc.file_type === 'docx'
                  ? '📝'
                  : doc.file_type === 'pdf'
                  ? '📕'
                  : '📄'

              return (
                <div
                  key={doc.doc_id}
                  onClick={() => selectDocument(doc.doc_id)}
                  className={`group relative p-2.5 rounded-xl cursor-pointer transition-all border text-xs flex flex-col gap-1.5 w-full min-w-0 box-border overflow-hidden ${
                    isActive
                      ? 'bg-primary/15 border-primary/40 text-foreground font-medium shadow-xs'
                      : 'bg-card/40 border-transparent hover:border-border hover:bg-card/80 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className="flex items-center justify-between gap-1 w-full min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
                      <span className="text-sm shrink-0">{extIcon}</span>
                      <span
                        className="truncate font-medium text-foreground block min-w-0 flex-1 text-left"
                        title={doc.title || doc.source_file || '未命名文档'}
                      >
                        {doc.title || doc.source_file || '未命名文档'}
                      </span>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          className="opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100 p-1 text-muted-foreground hover:text-foreground transition-opacity shrink-0 rounded-md hover:bg-muted/80"
                          onClick={(e) => e.stopPropagation()}
                          title="更多操作"
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-36">
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation()
                            if (
                              confirm(
                                `确定将文档《${doc.title || doc.source_file}》的阅读进度重置为 0% 吗？`
                              )
                            ) {
                              resetDocProgress(doc.doc_id)
                            }
                          }}
                          className="text-xs flex items-center gap-2 cursor-pointer"
                        >
                          <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" />
                          <span>重置阅读进度</span>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation()
                            if (
                              confirm(
                                `确定删除文档《${doc.title || doc.source_file}》及其全部研读记录吗？`
                              )
                            ) {
                              deleteDocument(doc.doc_id)
                            }
                          }}
                          className="text-xs flex items-center gap-2 text-destructive focus:text-destructive cursor-pointer"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          <span>删除文档</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-muted-foreground w-full min-w-0">
                    <span className="truncate">
                      {doc.paragraph_count || doc.total_paragraphs || 1} 段 ·{' '}
                      {doc.chapters ? doc.chapters.length : 1} 章
                    </span>
                    {isDone ? (
                      <span className="shrink-0 px-1.5 py-0.2 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium">
                        ✅ 已读完
                      </span>
                    ) : isReading ? (
                      <span className="shrink-0 px-1.5 py-0.2 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium font-mono">
                        📖 进度 {ratio}%
                      </span>
                    ) : (
                      <span className="shrink-0 px-1.5 py-0.2 rounded-full bg-muted text-muted-foreground/80">
                        未阅读
                      </span>
                    )}
                  </div>

                  {/* Progress Track */}
                  <div className="h-1 bg-muted/60 rounded-full overflow-hidden w-full">
                    <div
                      className={`h-full transition-all duration-300 rounded-full ${
                        isDone ? 'bg-emerald-500' : 'bg-primary'
                      }`}
                      style={{ width: `${ratio}%` }}
                    />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </ScrollArea>
    </aside>
  )
}
