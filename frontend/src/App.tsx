import React, { useEffect, useState } from 'react'
import { useStore } from '@/store/useStore'
import { TooltipProvider } from '@/components/ui/tooltip'
import { LeftSidebar } from '@/components/layout/LeftSidebar'
import { TopHeader } from '@/components/layout/TopHeader'
import { ReadingStage } from '@/components/reading/ReadingStage'
import { AssistantDrawer } from '@/components/sidecar/AssistantDrawer'
import { ProviderSettingsModal } from '@/components/modals/ProviderSettingsModal'
import { DocSettingsModal } from '@/components/modals/DocSettingsModal'
import { NoteModal } from '@/components/modals/NoteModal'
import { QuickFlashcardModal } from '@/components/modals/QuickFlashcardModal'
import { AssetInspectionModal } from '@/components/modals/AssetInspectionModal'
import { ModelTerminalPage } from '@/components/terminal/ModelTerminalPage'

export default function App() {
  const {
    theme,
    fontFamily,
    chatFontSize,
    loadDocuments,
    loadProvidersData,
    isAssetInspectionModalOpen,
    setAssetInspectionModalOpen,
    assetInspectionDocId,
    activeDoc,
  } = useStore()
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)

  // Route detection: route /chat directly renders the modern ModelTerminalPage
  const isChatRoute =
    window.location.pathname === '/chat' ||
    window.location.pathname.startsWith('/chat') ||
    window.location.search.includes('route=chat')

  // Keep document theme and font in sync reactively
  useEffect(() => {
    document.documentElement.className = `theme-${theme}`
    document.documentElement.setAttribute('data-theme', theme)
    document.body.className = `theme-${theme}`
    document.body.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    document.documentElement.setAttribute('data-font', fontFamily)
    document.body.setAttribute('data-font', fontFamily)
    const fontMap: Record<string, string> = {
      sans: "'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
      wenkai: "'Lora', 'LXGW WenKai Screen', 'LXGW WenKai', 'STKaiti', 'KaiTi', Georgia, serif",
      serif: "'Lora', 'Songti SC', 'Source Han Serif SC', 'Noto Serif SC', 'SimSun', Georgia, serif",
      system: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
    }
    const targetFont = fontMap[fontFamily] || fontMap.sans
    document.documentElement.style.setProperty('--reading-font-family', targetFont)
    document.body.style.setProperty('--reading-font-family', targetFont)
  }, [fontFamily])

  useEffect(() => {
    document.documentElement.style.setProperty('--chat-font-size', `${chatFontSize}px`)
  }, [chatFontSize])

  // Initialize data on startup
  useEffect(() => {
    loadProvidersData()
    if (!isChatRoute) {
      loadDocuments()
    }
  }, [isChatRoute])

  if (isChatRoute) {
    return (
      <TooltipProvider>
        <ModelTerminalPage />
      </TooltipProvider>
    )
  }

  return (
    <TooltipProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        {/* Left Sidebar */}
        <LeftSidebar
          isCollapsed={isSidebarCollapsed}
          onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col h-full overflow-hidden relative min-w-0">
          <TopHeader onToggleSidebar={() => setIsSidebarCollapsed(!isSidebarCollapsed)} />
          <ReadingStage />
        </div>

        {/* AI Assistant Right Sidebar (Docked & Resizable) */}
        <AssistantDrawer />

        {/* Modals */}
        <ProviderSettingsModal />
        <DocSettingsModal />
        <NoteModal />
        <QuickFlashcardModal />
        <AssetInspectionModal
          open={isAssetInspectionModalOpen}
          onOpenChange={(open) => setAssetInspectionModalOpen(open)}
          docId={assetInspectionDocId || activeDoc?.doc_id || ''}
          docTitle={activeDoc?.title || activeDoc?.filename || ''}
        />
      </div>
    </TooltipProvider>
  )
}
