import React, { useState, useRef } from 'react'
import {
  Globe,
  FolderArchive,
  BookOpen,
  FileText,
  Search,
  CheckSquare,
  Square,
  Loader2,
  Upload,
  AlertCircle,
  ExternalLink,
  ChevronRight,
  Sparkles,
} from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { useStore } from '@/store/useStore'
import * as api from '@/api/client'
import { WebInspectResult, WebChapterItem } from '@/types'

interface ImportMaterialModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type TabType = 'web' | 'folder' | 'epub' | 'file'

export function ImportMaterialModal({ open, onOpenChange }: ImportMaterialModalProps) {
  const { loadDocuments, selectDocument, setJustUploadedDocId } = useStore()
  const [activeTab, setActiveTab] = useState<TabType>('web')

  // --- Web Import State ---
  const [webUrl, setWebUrl] = useState('')
  const [isInspecting, setIsInspecting] = useState(false)
  const [inspectError, setInspectError] = useState('')
  const [inspectResult, setInspectResult] = useState<WebInspectResult | null>(null)
  const [docCustomTitle, setDocCustomTitle] = useState('')
  const [selectedChapters, setSelectedChapters] = useState<WebChapterItem[]>([])
  const [isImportingWeb, setIsImportingWeb] = useState(false)

  // --- Folder / Zip State ---
  const [isUploadingFolder, setIsUploadingFolder] = useState(false)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const zipInputRef = useRef<HTMLInputElement>(null)

  // --- E-Book State ---
  const [isUploadingEpub, setIsUploadingEpub] = useState(false)
  const epubInputRef = useRef<HTMLInputElement>(null)

  // --- Normal File State ---
  const [isUploadingFile, setIsUploadingFile] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Handle Inspect Web URL
  const handleInspectUrl = async () => {
    const trimmed = webUrl.trim()
    if (!trimmed) return

    try {
      setIsInspecting(true)
      setInspectError('')
      setInspectResult(null)

      const res = await api.inspectWebUrl(trimmed)
      setInspectResult(res)
      setDocCustomTitle(res.suggested_title || res.title || '网页研学教材')
      setSelectedChapters(res.chapters.filter((c) => c.selected))
    } catch (err: any) {
      setInspectError(err.message || '探测网页导航失败，请检查 URL 是否可公开访问')
    } finally {
      setIsInspecting(false)
    }
  }

  // Toggle Chapter Selection
  const toggleChapter = (chapterUrl: string) => {
    if (!inspectResult) return
    const ch = inspectResult.chapters.find((c) => c.url === chapterUrl)
    if (!ch) return

    const exists = selectedChapters.some((c) => c.url === chapterUrl)
    if (exists) {
      setSelectedChapters(selectedChapters.filter((c) => c.url !== chapterUrl))
    } else {
      setSelectedChapters([...selectedChapters, ch])
    }
  }

  const handleSelectAll = (select: boolean) => {
    if (!inspectResult) return
    if (select) {
      setSelectedChapters([...inspectResult.chapters])
    } else {
      setSelectedChapters([])
    }
  }

  const handleSelectCurrentSection = () => {
    if (!inspectResult) return
    const inSection = inspectResult.chapters.filter((c) => c.in_section)
    setSelectedChapters(inSection.length > 0 ? inSection : inspectResult.chapters)
  }

  // Execute Web Import
  const handleConfirmWebImport = async () => {
    if (!inspectResult || selectedChapters.length === 0) return

    try {
      setIsImportingWeb(true)
      const doc = await api.importWebDocument({
        url: inspectResult.url,
        title: docCustomTitle.trim() || inspectResult.suggested_title || '网页研学材料',
        selected_chapters: selectedChapters,
      })
      setJustUploadedDocId(doc.doc_id)
      await loadDocuments()
      selectDocument(doc.doc_id)
      onOpenChange(false)
      // Reset
      setInspectResult(null)
      setWebUrl('')
    } catch (err: any) {
      alert('导入失败: ' + err.message)
    } finally {
      setIsImportingWeb(false)
    }
  }

  // Execute Folder Import
  const handleFolderUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const fileList = Array.from(files)
    let folderName = 'Markdown 资料集'
    if (fileList[0]) {
      const rel = (fileList[0] as any).webkitRelativePath
      if (rel && rel.includes('/')) {
        folderName = rel.split('/')[0]
      }
    }

    try {
      setIsUploadingFolder(true)
      const doc = await api.importFolderFiles(fileList, folderName)
      setJustUploadedDocId(doc.doc_id)
      await loadDocuments()
      selectDocument(doc.doc_id)
      onOpenChange(false)
    } catch (err: any) {
      alert('文件夹导入失败: ' + err.message)
    } finally {
      setIsUploadingFolder(false)
      if (folderInputRef.current) folderInputRef.current.value = ''
    }
  }

  // Execute Zip Upload
  const handleZipUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      setIsUploadingFolder(true)
      const doc = await api.uploadDocument(file)
      setJustUploadedDocId(doc.doc_id)
      await loadDocuments()
      selectDocument(doc.doc_id)
      onOpenChange(false)
    } catch (err: any) {
      alert('Zip 导入失败: ' + err.message)
    } finally {
      setIsUploadingFolder(false)
      if (zipInputRef.current) zipInputRef.current.value = ''
    }
  }

  // Execute EPub Upload
  const handleEpubUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      setIsUploadingEpub(true)
      const doc = await api.uploadDocument(file)
      // EPUB files have self-contained images; no asset inspection modal needed
      await loadDocuments()
      selectDocument(doc.doc_id)
      onOpenChange(false)
    } catch (err: any) {
      alert('EPUB 电子书导入失败: ' + err.message)
    } finally {
      setIsUploadingEpub(false)
      if (epubInputRef.current) epubInputRef.current.value = ''
    }
  }

  // Execute Regular File Upload
  const handleNormalFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const lowerName = file.name.toLowerCase()
    if (lowerName.endsWith('.ppt') || lowerName.endsWith('.pptx')) {
      alert(
        '💡 提示：为了完整保留 PPT 幻灯片的图表与最佳双语精读排版，请在办公软件中将该 PPT 导出为 PDF 后再上传！'
      )
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    try {
      setIsUploadingFile(true)
      const doc = await api.uploadDocument(file)
      // Single files (single MD, PDF, image, txt) do not require asset inspection modal
      await loadDocuments()
      selectDocument(doc.doc_id)
      onOpenChange(false)
    } catch (err: any) {
      alert('上传失败: ' + err.message)
    } finally {
      setIsUploadingFile(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[720px] max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden bg-background border-border shadow-2xl">
        {/* Header */}
        <DialogHeader className="p-5 pb-3 border-b border-border/70">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold text-foreground">导入研学材料 · 全格式枢纽</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                支持系列在线文档、Markdown 知识包、EPUB 电子书及专业学术论文，自动转化为多章节精读教材
              </DialogDescription>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="grid grid-cols-4 gap-1.5 mt-4 p-1 bg-muted/50 rounded-lg border border-border/40">
            <button
              onClick={() => setActiveTab('web')}
              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                activeTab === 'web'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Globe className="w-3.5 h-3.5" />
              <span>系列网页 / 文档站</span>
            </button>

            <button
              onClick={() => setActiveTab('folder')}
              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                activeTab === 'folder'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <FolderArchive className="w-3.5 h-3.5" />
              <span>Markdown 资料夹</span>
            </button>

            <button
              onClick={() => setActiveTab('epub')}
              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                activeTab === 'epub'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>EPUB 电子书</span>
            </button>

            <button
              onClick={() => setActiveTab('file')}
              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                activeTab === 'file'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>单文件 (PDF/Word)</span>
            </button>
          </div>
        </DialogHeader>

        {/* Tab Contents */}
        <div className="flex-1 overflow-hidden p-5">
          {/* TAB 1: WEB SERIES / ONLINE DOCS */}
          {activeTab === 'web' && (
            <div className="flex flex-col h-full space-y-4">
              <div className="space-y-2">
                <div className="text-xs font-medium text-foreground">
                  <span>输入技术文档站入口或文章链接：</span>
                </div>

                <div className="flex items-center gap-2">
                  <Input
                    placeholder="https://mas.owasp.org/MASTG/0x05a-Platform-Overview/ 或其他文档页"
                    value={webUrl}
                    onChange={(e) => setWebUrl(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleInspectUrl()}
                    className="text-xs h-9"
                    disabled={isInspecting || isImportingWeb}
                  />
                  <Button
                    onClick={handleInspectUrl}
                    disabled={!webUrl.trim() || isInspecting || isImportingWeb}
                    className="text-xs h-9 px-4 flex-shrink-0"
                  >
                    {isInspecting ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                        探测中...
                      </>
                    ) : (
                      <>
                        <Search className="w-3.5 h-3.5 mr-1.5" />
                        探测目录
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {inspectError && (
                <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-md text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>{inspectError}</div>
                </div>
              )}

              {/* Inspect Result & Chapter Checklist */}
              {inspectResult && (
                <div className="flex-1 flex flex-col min-h-0 border border-border/80 rounded-lg p-3.5 bg-card/40 space-y-3">
                  {/* Document Title & Site Badge */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs">
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-primary/40 text-primary">
                          {inspectResult.is_series ? '系列技术规范 / 多章节' : '单篇网页'}
                        </Badge>
                        <span className="text-muted-foreground text-[11px]">{inspectResult.site_name}</span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        已选 <strong className="text-primary">{selectedChapters.length}</strong> /{' '}
                        {inspectResult.total_chapters} 篇
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground flex-shrink-0">教材名称:</span>
                      <Input
                        value={docCustomTitle}
                        onChange={(e) => setDocCustomTitle(e.target.value)}
                        className="text-xs h-8"
                        placeholder="请输入生成教材的标题"
                      />
                    </div>
                  </div>

                  {/* Actions & Filters */}
                  {inspectResult.is_series && (
                    <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[11px]">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleSelectAll(true)}
                          className="text-primary hover:underline"
                        >
                          全选
                        </button>
                        <span className="text-border">|</span>
                        <button
                          type="button"
                          onClick={() => handleSelectAll(false)}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          清空
                        </button>
                        {inspectResult.section_name && (
                          <>
                            <span className="text-border">|</span>
                            <button
                              type="button"
                              onClick={handleSelectCurrentSection}
                              className="text-primary hover:underline font-medium"
                            >
                              仅当前专题: {inspectResult.section_name}
                            </button>
                          </>
                        )}
                      </div>
                      <div className="text-muted-foreground text-[10px]">
                        💡 支持勾选需要研学的章节合并为一本教材
                      </div>
                    </div>
                  )}

                  {/* Chapter List Scroll Container */}
                  <div className="flex-1 min-h-[160px] max-h-[260px] overflow-y-auto border border-border/50 rounded-md bg-background/50 p-2 space-y-1">
                    {inspectResult.chapters.map((ch) => {
                      const isSelected = selectedChapters.some((c) => c.url === ch.url)
                      return (
                        <div
                          key={ch.url}
                          onClick={() => toggleChapter(ch.url)}
                          className={`flex items-center justify-between p-2 rounded-md text-xs cursor-pointer transition-colors ${
                            isSelected
                              ? 'bg-primary/10 border border-primary/20 text-foreground'
                              : 'hover:bg-muted/60 text-muted-foreground'
                          }`}
                        >
                          <div className="flex items-center gap-2.5 truncate">
                            {isSelected ? (
                              <CheckSquare className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                            ) : (
                              <Square className="w-3.5 h-3.5 text-muted-foreground/60 flex-shrink-0" />
                            )}
                            <span className={`truncate ${ch.is_current ? 'font-semibold text-primary' : ''}`}>
                              {ch.title}
                            </span>
                            {ch.is_current && (
                              <span className="text-[9px] px-1 py-0.5 bg-primary/20 text-primary rounded font-mono">
                                当前页
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-muted-foreground/60 font-mono truncate max-w-[150px] ml-2">
                            {ch.url.replace(/^https?:\/\//, '')}
                          </span>
                        </div>
                      )
                    })}
                  </div>

                  {/* Submit Button */}
                  <Button
                    onClick={handleConfirmWebImport}
                    disabled={selectedChapters.length === 0 || isImportingWeb}
                    className="w-full text-xs h-9"
                  >
                    {isImportingWeb ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                        正在后台创建并提取网页正文...
                      </>
                    ) : (
                      <>
                        <DownloadIcon className="w-3.5 h-3.5 mr-1.5" />
                        确认导入选中的 {selectedChapters.length} 个章节并开启精读
                      </>
                    )}
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: MARKDOWN FOLDER / ZIP */}
          {activeTab === 'folder' && (
            <div className="flex flex-col h-full space-y-4">
              <div className="text-xs text-muted-foreground leading-relaxed">
                将包含多个 Markdown（<code>.md</code>）文件的本地项目或资料包导入为结构化教材。
                系统将自动识别 <code>SUMMARY.md</code>、<code>mkdocs.yml</code> 目录层级，并自动解压关联的图片资源！
              </div>

              <div className="grid grid-cols-2 gap-3 flex-1">
                {/* Option 1: Upload Zip Archive (Recommended, 0 browser alerts) */}
                <div
                  onClick={() => zipInputRef.current?.click()}
                  className="border-2 border-dashed border-primary/50 hover:border-primary bg-primary/5 hover:bg-primary/10 rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all group relative"
                >
                  <div className="absolute top-2.5 right-2.5 px-2 py-0.5 bg-primary text-primary-foreground text-[10px] font-semibold rounded-full shadow-xs">
                    推荐 · 免浏览器确认
                  </div>
                  <input
                    type="file"
                    ref={zipInputRef}
                    className="hidden"
                    accept=".zip,.tar,.tar.gz"
                    onChange={handleZipUpload}
                  />
                  <div className="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div className="font-semibold text-xs text-foreground mb-1">上传 Markdown 压缩包 (.zip)</div>
                  <div className="text-[11px] text-muted-foreground">
                    直接将资料目录打成 zip 上传，无浏览器安全拦截弹窗，秒级提取！
                  </div>
                </div>

                {/* Option 2: Select Local Folder or Multi-Files */}
                <div
                  onClick={() => folderInputRef.current?.click()}
                  className="border-2 border-dashed border-border hover:border-primary/60 bg-card/30 hover:bg-primary/5 rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all group"
                >
                  <input
                    type="file"
                    ref={folderInputRef}
                    className="hidden"
                    // @ts-ignore
                    webkitdirectory=""
                    directory=""
                    multiple
                    onChange={handleFolderUpload}
                  />
                  <div className="w-12 h-12 rounded-full bg-secondary text-foreground flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                    <FolderArchive className="w-6 h-6" />
                  </div>
                  <div className="font-semibold text-xs text-foreground mb-1">选择本地 Markdown 文件夹</div>
                  <div className="text-[11px] text-muted-foreground">
                    选择电脑上的完整资料目录（浏览器会弹出原生读取确认）
                  </div>
                  {isUploadingFolder && (
                    <div className="mt-3 flex items-center gap-1.5 text-xs text-primary">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>正在读取与上传...</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: EPUB E-BOOK */}
          {activeTab === 'epub' && (
            <div className="flex flex-col h-full space-y-4">
              <div className="text-xs text-muted-foreground leading-relaxed">
                上传标准的 <code>.epub</code> 电子书。系统将自动解析元数据、书籍封面以及完整的目录章节（TOC），支持全书双语对照精读与图文保留。
              </div>

              <div
                onClick={() => epubInputRef.current?.click()}
                className="border-2 border-dashed border-border hover:border-primary/60 bg-card/30 hover:bg-primary/5 rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all group"
              >
                <input
                  type="file"
                  ref={epubInputRef}
                  className="hidden"
                  accept=".epub"
                  onChange={handleEpubUpload}
                />
                <div className="w-14 h-14 rounded-full bg-primary/10 text-primary flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                  <BookOpen className="w-7 h-7" />
                </div>
                <div className="font-semibold text-sm text-foreground mb-1">点击或拖拽上传 EPUB 电子书</div>
                <div className="text-xs text-muted-foreground max-w-sm">
                  支持市面上绝大多数中英文电子书，自动按章节切分并提取插图
                </div>
                {isUploadingEpub && (
                  <div className="mt-3 flex items-center gap-1.5 text-xs text-primary">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>正在解析 EPUB 电子书...</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: NORMAL FILE (PDF, WORD, TXT, IMAGE) */}
          {activeTab === 'file' && (
            <div className="flex flex-col h-full space-y-4">
              <div className="text-xs text-muted-foreground leading-relaxed">
                上传 PDF 巨著、Word 报告、学术论文或长篇 TXT/MD 单文档。
              </div>

              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-border hover:border-primary/60 bg-card/30 hover:bg-primary/5 rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all group"
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept=".pdf,.docx,.doc,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp,.svg"
                  onChange={handleNormalFileUpload}
                />
                <div className="w-14 h-14 rounded-full bg-primary/10 text-primary flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                  <FileText className="w-7 h-7" />
                </div>
                <div className="font-semibold text-sm text-foreground mb-1">选择单个文件上传</div>
                <div className="text-xs text-muted-foreground max-w-sm">
                  支持 PDF、DOCX、TXT、MD、PNG/JPG 图片（PPT 请另存为 PDF 上传）
                </div>
                {isUploadingFile && (
                  <div className="mt-3 flex items-center gap-1.5 text-xs text-primary">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>正在处理文件上传...</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function DownloadIcon(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" x2="12" y1="15" y2="3" />
    </svg>
  )
}
