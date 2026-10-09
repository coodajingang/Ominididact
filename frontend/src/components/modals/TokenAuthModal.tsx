import React, { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { KeyRound, ShieldAlert } from 'lucide-react'
import * as api from '@/api/client'

interface TokenAuthModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function TokenAuthModal({ open, onOpenChange }: TokenAuthModalProps) {
  const [tokenInput, setTokenInput] = useState(() => api.getStoredApiToken())
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSaveAndReload = async () => {
    if (!tokenInput.trim()) {
      setError('请输入有效的 API Token')
      return
    }
    setLoading(true)
    setError('')
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: tokenInput.trim(), remember: true })
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        setError(err.detail || '访问凭证无效，请检查配置')
        setLoading(false)
        return
      }
      api.setStoredApiToken(tokenInput.trim())
      onOpenChange(false)
      window.location.reload()
    } catch (e: any) {
      setError(e.message || '网络或凭证校验异常')
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-bold text-amber-500">
            <ShieldAlert className="h-5 w-5" />
            <span>需要访问令牌 (Omnididact API Token)</span>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground pt-1.5 leading-relaxed">
            服务端已开启全局统一安全鉴权 (<code>OMNIDIDACT_API_TOKEN</code>)。请填写对应的访问凭证以继续使用研学中心、配置与 AI 网关接口。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <KeyRound className="h-3.5 w-3.5 text-primary" />
              <span>访问令牌 (Bearer Token)</span>
            </label>
            <Input
              type="password"
              placeholder="请输入 OMNIDIDACT_API_TOKEN..."
              value={tokenInput}
              onChange={(e) => {
                setTokenInput(e.target.value)
                setError('')
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveAndReload()
              }}
              className="font-mono text-xs"
              autoFocus
            />
            {error && <p className="text-[11px] text-destructive">{error}</p>}
          </div>
          <p className="text-[11px] text-muted-foreground/80 leading-normal">
            💡 提示：凭证将安全保存在浏览器本地，页面刷新后仍将有效。您也可以通过访问链接参数 <code>?token=您的凭证</code> 快捷登入。
          </p>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs"
          >
            稍后
          </Button>
          <Button
            size="sm"
            onClick={handleSaveAndReload}
            disabled={loading}
            className="text-xs"
          >
            {loading ? '正在验证凭证...' : '保存并刷新页面'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
