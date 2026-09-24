import React, { useState, useEffect } from 'react'
import {
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Download,
  FileQuestion,
  RefreshCw,
  ExternalLink,
  Layers,
  Settings,
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import * as api from '@/api/client'
import { useStore } from '@/store/useStore'

interface AssetInspectionModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  docId: string
  docTitle?: string
}

export function AssetInspectionModal({
  open,
  onOpenChange,
  docId,
  docTitle,
}: AssetInspectionModalProps) {
  const { setProviderModalOpen, refreshActiveDocContent } = useStore()
  const [loading, setLoading] = useState(false)
  const [reinspecting, setReinspecting] = useState(false)
  const [report, setReport] = useState<any>(null)
  const [error, setError] = useState('')

  const loadReport = async () => {
    if (!docId) return
    try {
      setLoading(true)
      setError('')
      const data = await api.getAssetInspection(docId)
      setReport(data)
    } catch (err: any) {
      setError(err.message || '获取静态资源检查报告失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open && docId) {
      loadReport()
    }
  }, [open, docId])

  const handleReinspect = async () => {
    if (!docId) return
    try {
      setReinspecting(true)
      const data = await api.reInspectAssets(docId)
      setReport(data)
      await refreshActiveDocContent()
    } catch (err: any) {
      alert('重新检查失败: ' + err.message)
    } finally {
      setReinspecting(false)
    }
  }

  const stats = report?.stats || {
    total_referenced: 0,
    local_matched: 0,
    remotely_downloaded: 0,
    missing_count: 0,
  }

  const hasAi = report?.has_ai

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[620px] max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden bg-background border-border shadow-2xl">
        <DialogHeader className="p-5 pb-3 border-b border-border/70">
          <div className="flex items-center gap-2.5">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              hasAi ? 'bg-primary/10 text-primary' : 'bg-amber-500/10 text-amber-600'
            }`}>
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold text-foreground flex items-center gap-2">
                <span>静态资源自省与对齐报告</span>
                {hasAi ? (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-primary/40 text-primary">
                    AI 智能增强分析
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-amber-500/40 text-amber-600">
                    本地启发式规则
                  </Badge>
                )}
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5 truncate max-w-[480px]">
                文献：《{docTitle || docId}》静态资源（图片/音视频）引用健康度检查
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center gap-3 text-muted-foreground">
              <div className="w-7 h-7 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              <span className="text-xs">正在分析全书静态资源与路径对齐状态...</span>
            </div>
          ) : error ? (
            <div className="p-4 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg text-xs">
              {error}
            </div>
          ) : (
            <>
              {/* Statistics Grid */}
              <div className="grid grid-cols-4 gap-2">
                <div className="p-3 bg-card border border-border/60 rounded-xl text-center">
                  <div className="text-[11px] text-muted-foreground mb-0.5">总引用资源</div>
                  <div className="text-lg font-bold font-mono text-foreground">{stats.total_referenced}</div>
                </div>

                <div className="p-3 bg-emerald-500/5 border border-emerald-500/20 rounded-xl text-center">
                  <div className="text-[11px] text-emerald-600 dark:text-emerald-400 mb-0.5">本地匹配</div>
                  <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
                    {stats.local_matched}
                  </div>
                </div>

                <div className="p-3 bg-blue-500/5 border border-blue-500/20 rounded-xl text-center">
                  <div className="text-[11px] text-blue-600 dark:text-blue-400 mb-0.5">网络自动补全</div>
                  <div className="text-lg font-bold font-mono text-blue-600 dark:text-blue-400">
                    {stats.remotely_downloaded}
                  </div>
                </div>

                <div className={`p-3 rounded-xl text-center border ${
                  stats.missing_count > 0
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400'
                    : 'bg-muted/30 border-border/40 text-muted-foreground'
                }`}>
                  <div className="text-[11px] mb-0.5">仍缺失资源</div>
                  <div className="text-lg font-bold font-mono">
                    {stats.missing_count}
                  </div>
                </div>
              </div>

              {/* Status Explanation Card */}
              <div className="p-3.5 bg-muted/40 border border-border/60 rounded-xl space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <Layers className="w-3.5 h-3.5 text-primary" />
                  <span>处理状态与诊断说明</span>
                </div>
                <div className="text-xs text-muted-foreground leading-relaxed">
                  {report?.user_notice || report?.ai_summary || '系统已自动扫描并规范化文档内的静态资源引用。'}
                </div>
                {report?.doc_origin_inferred && report.doc_origin_inferred !== '本地文件' && (
                  <div className="text-[11px] text-primary/90 font-medium">
                    🔍 AI 溯源识别：{report.doc_origin_inferred}
                  </div>
                )}
              </div>

              {/* Missing Resources Warning / Advice */}
              {!hasAi && stats.missing_count > 0 && (
                <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-start gap-3">
                  <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="text-xs space-y-1">
                    <div className="font-semibold text-amber-700 dark:text-amber-400">未配置默认 AI 模型</div>
                    <div className="text-muted-foreground leading-relaxed">
                      检测到文档中存在缺失的相对资源。配置 AI 模型后，系统将自动分析开源来源并尝试通过网络源头下载补全高清图片。
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        onOpenChange(false)
                        setProviderModalOpen(true)
                      }}
                      className="text-xs h-7 mt-1.5 gap-1.5"
                    >
                      <Settings className="w-3 h-3" />
                      前往配置大模型
                    </Button>
                  </div>
                </div>
              )}

              {/* Missing Samples List */}
              {stats.missing_count > 0 && report?.missing_samples?.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground flex items-center justify-between">
                    <span>缺失资源路径样本：</span>
                    <span className="text-[10px] font-mono">共 {stats.missing_count} 项</span>
                  </div>
                  <div className="p-2.5 bg-background border border-border/60 rounded-lg max-h-32 overflow-y-auto font-mono text-[11px] space-y-1 text-muted-foreground">
                    {report.missing_samples.map((item: string, i: number) => (
                      <div key={i} className="truncate text-destructive/80">
                        • {item}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Path Remediation Samples */}
              {report?.remediation_samples?.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground">
                    路径规范化示例（已自动对齐系统接口）：
                  </div>
                  <div className="p-2.5 bg-background border border-border/60 rounded-lg max-h-36 overflow-y-auto font-mono text-[10px] space-y-1.5 text-muted-foreground">
                    {report.remediation_samples.map((item: any, i: number) => (
                      <div key={i} className="truncate">
                        <span className="text-muted-foreground/60">{item.from}</span>
                        <br />
                        <span className="text-primary font-semibold">↳ {item.to}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter className="p-4 border-t border-border/60 flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={handleReinspect}
            disabled={reinspecting || loading}
            className="text-xs h-8 gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${reinspecting ? 'animate-spin' : ''}`} />
            <span>{reinspecting ? '重新自省与修复中...' : '重新执行自省与修复'}</span>
          </Button>

          <Button
            variant="default"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs h-8 px-4"
          >
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
