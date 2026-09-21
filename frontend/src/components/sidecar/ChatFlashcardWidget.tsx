import React, { useState } from 'react'
import { marked } from 'marked'
import {
  Plus,
  Check,
  Loader2,
  Sparkles,
  BookOpen,
  Puzzle,
  Tag,
  FileCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import * as api from '@/api/client'
import { useStore } from '@/store/useStore'

export interface ParsedFlashcard {
  id?: string
  type: 'qa' | 'cloze'
  front: string
  back: string
  tags: string[]
}

export type MessageSegment =
  | { type: 'markdown'; content: string }
  | { type: 'flashcard'; card: ParsedFlashcard; rawBlock: string; cardIndex: number }

export function parseFlashcardBlock(block: string): ParsedFlashcard {
  const lines = block.split('\n')
  let type: 'qa' | 'cloze' = 'qa'
  let front = ''
  let back = ''
  let tags = ''
  let currentField: 'type' | 'front' | 'back' | 'tags' | null = null

  for (const rawLine of lines) {
    const trimmed = rawLine.trim()
    const lower = trimmed.toLowerCase()

    // 1. Type
    if (
      lower.startsWith('type:') ||
      lower.startsWith('type：') ||
      lower.startsWith('**type**') ||
      lower.startsWith('类型:') ||
      lower.startsWith('类型：')
    ) {
      const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：')
      const val = trimmed.slice(colonIdx + 1).trim().toLowerCase()
      if (val.includes('cloze') || val.includes('挖空') || val.includes('镂空')) {
        type = 'cloze'
      } else {
        type = 'qa'
      }
      currentField = 'type'
      continue
    }

    // 2. Front
    if (
      lower.startsWith('front:') ||
      lower.startsWith('front：') ||
      lower.startsWith('**front**') ||
      lower.startsWith('正面:') ||
      lower.startsWith('正面：') ||
      lower.startsWith('问题:') ||
      lower.startsWith('问题：')
    ) {
      const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：')
      front = trimmed.slice(colonIdx + 1).trim()
      currentField = 'front'
      continue
    }

    // 3. Back
    if (
      lower.startsWith('back:') ||
      lower.startsWith('back：') ||
      lower.startsWith('**back**') ||
      lower.startsWith('背面:') ||
      lower.startsWith('背面：') ||
      lower.startsWith('answer:') ||
      lower.startsWith('答案:') ||
      lower.startsWith('答案：') ||
      lower.startsWith('解析:') ||
      lower.startsWith('解析：')
    ) {
      const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：')
      back = trimmed.slice(colonIdx + 1).trim()
      currentField = 'back'
      continue
    }

    // 4. Tags
    if (
      lower.startsWith('tags:') ||
      lower.startsWith('tag:') ||
      lower.startsWith('**tags**') ||
      lower.startsWith('标签:') ||
      lower.startsWith('标签：')
    ) {
      const colonIdx = trimmed.indexOf(':') !== -1 ? trimmed.indexOf(':') : trimmed.indexOf('：')
      tags = trimmed.slice(colonIdx + 1).trim()
      currentField = 'tags'
      continue
    }

    // 5. Implicit back markers inside front
    if (
      currentField === 'front' &&
      !back &&
      /^(?:\*\*|__)?(?:考点提示|备考提示|提示|解析|答案|解题思路)[:：](?:\*\*|__)?/i.test(trimmed)
    ) {
      back = trimmed
      currentField = 'back'
      continue
    }

    // 6. Multiline continuation
    if (currentField === 'front') {
      front = front ? front + '\n' + rawLine : rawLine
    } else if (currentField === 'back') {
      back = back ? back + '\n' + rawLine : rawLine
    } else if (currentField === 'tags') {
      if (trimmed) {
        tags = tags ? tags + ', ' + trimmed : trimmed
      }
    }
  }

  front = front.trim()
  back = back.trim()

  if (/\{\{.+?\}\}/.test(front)) {
    type = 'cloze'
  }

  if (!front && block.trim()) {
    front = block.trim()
  }

  const parsedTags = tags
    ? tags
        .replace(/，/g, ',')
        .split(',')
        .map((t) => t.trim().replace(/^#/, ''))
        .filter(Boolean)
    : []

  return {
    type,
    front,
    back,
    tags: parsedTags,
  }
}

export function splitMessageSegments(text: string): MessageSegment[] {
  if (!text) return []

  // Matches :::flashcard ... ::: or ```flashcard ... ``` or combinations
  const fcRegex =
    /(?:```(?:flashcard)?\s*)?:::flashcard\s*([\s\S]*?)\s*:::(?:\s*```)?|```flashcard\s*([\s\S]*?)\s*```/gi

  let lastIndex = 0
  let match: RegExpExecArray | null
  const segments: MessageSegment[] = []
  let cardIndex = 0

  while ((match = fcRegex.exec(text)) !== null) {
    const textBefore = text.slice(lastIndex, match.index)
    if (textBefore.trim()) {
      segments.push({ type: 'markdown', content: textBefore })
    }

    const block = match[1] !== undefined ? match[1] : match[2]
    if (block && block.trim()) {
      const cardObj = parseFlashcardBlock(block)
      segments.push({
        type: 'flashcard',
        card: cardObj,
        rawBlock: match[0],
        cardIndex: cardIndex++,
      })
    }

    lastIndex = fcRegex.lastIndex
  }

  const textAfter = text.slice(lastIndex)
  if (textAfter.trim()) {
    segments.push({ type: 'markdown', content: textAfter })
  }

  return segments.length > 0 ? segments : [{ type: 'markdown', content: text }]
}

interface ChatFlashcardWidgetProps {
  card: ParsedFlashcard
  docId?: string
  chapterId?: string
  paragraphId?: string
  onCardAdopted?: () => void
}

export function ChatFlashcardWidget({
  card,
  docId,
  chapterId,
  paragraphId,
  onCardAdopted,
}: ChatFlashcardWidgetProps) {
  const [isAdopting, setIsAdopting] = useState(false)
  const [isAdopted, setIsAdopted] = useState(false)

  const isCloze = card.type === 'cloze'

  const handleAdoptCard = async () => {
    if (!docId) {
      alert('未检测到当前研学文档，无法归档闪卡。请在研学文档页面中使用！')
      return
    }

    setIsAdopting(true)
    try {
      await api.createFlashcard(docId, {
        type: card.type,
        front: card.front,
        back: card.back,
        tags: card.tags,
        chapter_id: chapterId,
        paragraph_id: paragraphId,
      })
      setIsAdopted(true)
      useStore.getState().refreshDocFlashcardCount(docId)
      onCardAdopted?.()
    } catch (err: any) {
      alert('采纳闪卡入库失败: ' + (err?.message || String(err)))
    } finally {
      setIsAdopting(false)
    }
  }

  // Format front text for cloze highlighting
  const renderFrontContent = () => {
    if (isCloze) {
      const replaced = card.front.replace(
        /\{\{(.*?)\}\}/g,
        '<span class="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-700 dark:text-amber-300 font-bold border border-amber-500/30 mx-0.5 shadow-2xs">[ $1 ]</span>'
      )
      return <div className="leading-relaxed" dangerouslySetInnerHTML={{ __html: marked.parse(replaced) as string }} />
    }
    return <div className="leading-relaxed" dangerouslySetInnerHTML={{ __html: marked.parse(card.front) as string }} />
  }

  return (
    <div
      className={`rounded-xl border transition-all p-3.5 my-3 shadow-xs space-y-2.5 ${
        isCloze
          ? 'border-amber-500/30 dark:border-amber-500/25 bg-gradient-to-br from-amber-500/5 via-card to-amber-500/10'
          : 'border-indigo-500/30 dark:border-indigo-500/25 bg-gradient-to-br from-indigo-500/5 via-card to-indigo-500/10'
      }`}
    >
      {/* Header with Card Type and Action */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-border/50">
        <div className="flex items-center gap-1.5">
          {isCloze ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 font-medium">
              <Puzzle className="h-3 w-3" />
              镂空挖空闪卡 (Cloze)
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border border-indigo-500/30 font-medium">
              <BookOpen className="h-3 w-3" />
              问答记忆闪卡 (QA)
            </span>
          )}
        </div>

        {/* Adopt Button */}
        <div>
          {isAdopted ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-1 rounded-md shadow-2xs">
              <Check className="h-3 w-3 text-emerald-500" />
              已采纳到闪卡库
            </span>
          ) : (
            <Button
              size="sm"
              disabled={isAdopting}
              onClick={handleAdoptCard}
              className="h-7 px-3 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium shadow-xs transition-transform active:scale-95"
              title="确定采纳此卡片，直接保存至本文档闪卡库中"
            >
              {isAdopting ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              <span>{isAdopting ? '正在入库...' : '采纳加入闪卡'}</span>
            </Button>
          )}
        </div>
      </div>

      {/* Front Area */}
      <div className="space-y-1">
        <div className="text-[11px] font-bold text-muted-foreground flex items-center gap-1">
          <span className="text-primary font-mono">[题]</span>
          <span>正面考点 / 题目：</span>
        </div>
        <div className="chat-dialogue-content text-foreground bg-background/60 p-2.5 rounded-lg border border-border/40">
          {renderFrontContent()}
        </div>
      </div>

      {/* Back Area */}
      {card.back && (
        <div className="space-y-1">
          <div className="text-[11px] font-bold text-muted-foreground flex items-center gap-1">
            <span className="text-emerald-500 font-mono">[解]</span>
            <span>背面解析 / 答案：</span>
          </div>
          <div
            className="chat-dialogue-content text-foreground bg-background/60 p-2.5 rounded-lg border border-border/40 prose dark:prose-invert max-w-none break-words leading-relaxed"
            dangerouslySetInnerHTML={{ __html: marked.parse(card.back) as string }}
          />
        </div>
      )}

      {/* Tags Row */}
      {card.tags && card.tags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 pt-1">
          <Tag className="h-3 w-3 text-muted-foreground/70 mr-0.5" />
          {card.tags.map((tag, idx) => (
            <span
              key={idx}
              className="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground border border-border/50"
            >
              #{tag}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
