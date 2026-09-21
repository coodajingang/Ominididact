const DOC_PROGRESS_KEY_PREFIX = 'study_doc_progress_'

export interface DocReadingProgress {
  docId: string
  lastActiveChapterId?: string
  chapterId?: string
  scrollTop: number
  scrollRatio: number // Aggregated total document progress (0-100)
  chapterProgress?: Record<string, number> // Record<chapterId, max_ratio_0_to_100>
  chapterScrolls?: Record<string, number> // Record<chapterId, scrollTop>
  isCompleted?: boolean // Once reached 100%, locked permanently
  updatedAt: number
}

export function getDocReadingProgress(docId: string): DocReadingProgress | null {
  if (!docId) return null
  try {
    const raw = localStorage.getItem(DOC_PROGRESS_KEY_PREFIX + docId)
    if (!raw) return null
    const parsed: DocReadingProgress = JSON.parse(raw)
    // If it was already completed or reached 100%, lock to 100%
    if (parsed && (parsed.isCompleted || parsed.scrollRatio >= 100)) {
      parsed.isCompleted = true
      parsed.scrollRatio = 100
    }
    // Backward compatibility: ensure chapterProgress and chapterScrolls exist
    if (parsed && !parsed.chapterProgress && (parsed.lastActiveChapterId || parsed.chapterId)) {
      const activeCh = parsed.lastActiveChapterId || parsed.chapterId!
      parsed.chapterProgress = { [activeCh]: parsed.scrollRatio || 0 }
    }
    if (parsed && !parsed.chapterScrolls && (parsed.lastActiveChapterId || parsed.chapterId)) {
      const activeCh = parsed.lastActiveChapterId || parsed.chapterId!
      parsed.chapterScrolls = { [activeCh]: parsed.scrollTop || 0 }
    }
    return parsed
  } catch {
    return null
  }
}

export function getChapterProgress(docId: string, chapterId: string): number {
  if (!docId || !chapterId) return 0
  const prog = getDocReadingProgress(docId)
  if (!prog) return 0
  if (prog.isCompleted) return 100
  return prog.chapterProgress?.[chapterId] ?? 0
}

export function getChapterScrollTop(docId: string, chapterId: string): number {
  if (!docId || !chapterId) return 0
  const prog = getDocReadingProgress(docId)
  if (!prog) return 0
  return prog.chapterScrolls?.[chapterId] ?? 0
}

export function calculateAggregatedProgress(
  chapterMap: Record<string, number>,
  chapters?: Array<{ chapter_id: string; paragraph_count?: number }>
): number {
  if (!chapters || chapters.length === 0) {
    const vals = Object.values(chapterMap)
    if (vals.length === 0) return 0
    return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
  }

  let totalParas = 0
  let weightedSum = 0
  let allHaveParas = true

  for (const ch of chapters) {
    const count = ch.paragraph_count ?? 0
    if (count <= 0) {
      allHaveParas = false
    }
    totalParas += count
    const chProg = chapterMap[ch.chapter_id] ?? 0
    weightedSum += chProg * count
  }

  if (allHaveParas && totalParas > 0) {
    return Math.round(weightedSum / totalParas)
  }

  const sumRatio = chapters.reduce((sum, ch) => sum + (chapterMap[ch.chapter_id] ?? 0), 0)
  return Math.round(sumRatio / chapters.length)
}

export function saveDocReadingProgress(
  docId: string,
  chapterId?: string,
  scrollTop: number = 0,
  currentChapterRatio: number = 0,
  chapters?: Array<{ chapter_id: string; paragraph_count?: number }>
): number {
  if (!docId) return 0
  try {
    const existing = getDocReadingProgress(docId)

    const chapterMap: Record<string, number> = { ...(existing?.chapterProgress || {}) }
    const chapterScrolls: Record<string, number> = { ...(existing?.chapterScrolls || {}) }

    if (chapterId) {
      const rawRatio = Math.min(100, Math.max(0, Math.round(currentChapterRatio || 0)))
      // If user reached >= 95% of chapter, count as 100% completed for this chapter
      const effectiveRatio = rawRatio >= 95 ? 100 : rawRatio
      const prevRatio = chapterMap[chapterId] ?? 0
      chapterMap[chapterId] = Math.max(prevRatio, effectiveRatio)
      chapterScrolls[chapterId] = Math.max(0, Math.round(scrollTop || 0))
    }

    const aggregated = calculateAggregatedProgress(chapterMap, chapters)
    const prevOverallRatio = existing?.scrollRatio ?? 0
    let finalRatio = Math.min(100, Math.max(prevOverallRatio, aggregated))

    const isCompleted = (existing?.isCompleted ?? false) || finalRatio >= 100
    if (isCompleted) {
      finalRatio = 100
    }

    const data: DocReadingProgress = {
      docId,
      lastActiveChapterId: chapterId || existing?.lastActiveChapterId || existing?.chapterId,
      chapterId: chapterId || existing?.chapterId,
      scrollTop: Math.max(0, Math.round(scrollTop || 0)),
      scrollRatio: finalRatio,
      chapterProgress: chapterMap,
      chapterScrolls,
      isCompleted,
      updatedAt: Date.now(),
    }
    localStorage.setItem(DOC_PROGRESS_KEY_PREFIX + docId, JSON.stringify(data))
    return finalRatio
  } catch (e) {
    console.warn('Failed to save reading progress:', e)
    return 0
  }
}

export function markChapterCompleted(
  docId: string,
  chapterId: string,
  chapters?: Array<{ chapter_id: string; paragraph_count?: number }>
): number {
  return saveDocReadingProgress(docId, chapterId, 0, 100, chapters)
}

export function resetDocReadingProgress(docId: string): void {
  if (!docId) return
  try {
    const data: DocReadingProgress = {
      docId,
      scrollTop: 0,
      scrollRatio: 0,
      chapterProgress: {},
      chapterScrolls: {},
      isCompleted: false,
      updatedAt: Date.now(),
    }
    localStorage.setItem(DOC_PROGRESS_KEY_PREFIX + docId, JSON.stringify(data))
  } catch (e) {
    console.warn('Failed to reset reading progress:', e)
  }
}

export function getAllDocProgress(docIds: string[]): Record<string, number> {
  const result: Record<string, number> = {}
  for (const id of docIds) {
    const prog = getDocReadingProgress(id)
    if (prog) {
      result[id] = prog.isCompleted || prog.scrollRatio >= 100 ? 100 : prog.scrollRatio
    }
  }
  return result
}

