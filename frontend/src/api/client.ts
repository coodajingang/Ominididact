import {
  DocumentMeta,
  ChapterItem,
  ParagraphItem,
  ProviderItem,
  ProvidersConfig,
  DocSettings,
  BatchTranslationStatus,
} from '@/types'

const BASE_URL = ''

export async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!resp.ok) {
    const errorText = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${errorText || resp.statusText}`)
  }
  const json = await resp.json()
  return json.data !== undefined ? json.data : json
}

// Documents
export async function getDocuments(): Promise<DocumentMeta[]> {
  const docs = await apiRequest<any[]>('/api/study/documents')
  return docs.map((d) => ({
    doc_id: d.doc_id,
    title: d.filename || d.title || '未命名文档',
    source_file: d.filename || '',
    file_type: d.file_type || 'pdf',
    source_url: d.source_url || '',
    has_failed_chapters: Boolean(d.has_failed_chapters),
    failed_chapter_count: d.failed_chapter_count || 0,
    paragraph_count: d.total_paragraphs || 0,
    translated_count: d.translated_paragraphs || 0,
    created_at: d.created_at || '',
    status: d.status || 'completed',
    progress_percent: d.progress?.percent ?? (d.status === 'completed' ? 100 : 0),
    progress: d.progress || null,
    chapters: (d.chapters || []).map((ch: any, idx: number) => ({
      chapter_id: ch.chapter_id,
      title: ch.title || `第 ${idx + 1} 章`,
      index: idx,
      url: ch.url || '',
      fetch_success: ch.fetch_success !== undefined ? ch.fetch_success : true,
      paragraph_count: ch.paragraph_count || 0,
      header_notes: ch.header_notes || [],
      footer_notes: ch.footer_notes || [],
    })),
  }))
}

export async function getDocumentDetail(docId: string): Promise<DocumentMeta> {
  const d = await apiRequest<any>(`/api/study/documents/${encodeURIComponent(docId)}`)
  return {
    doc_id: d.doc_id,
    title: d.filename || d.title || '未命名文档',
    source_file: d.filename || '',
    file_type: d.file_type || 'pdf',
    source_url: d.source_url || '',
    has_failed_chapters: Boolean(d.has_failed_chapters),
    failed_chapter_count: d.failed_chapter_count || 0,
    paragraph_count: d.total_paragraphs || 0,
    translated_count: d.translated_paragraphs || 0,
    created_at: d.created_at || '',
    status: d.status || 'completed',
    progress_percent: d.progress?.percent ?? (d.status === 'completed' ? 100 : 0),
    progress: d.progress || null,
    chapters: (d.chapters || []).map((ch: any, idx: number) => ({
      chapter_id: ch.chapter_id,
      title: ch.title || `第 ${idx + 1} 章`,
      index: idx,
      url: ch.url || '',
      fetch_success: ch.fetch_success !== undefined ? ch.fetch_success : true,
      paragraph_count: ch.paragraph_count || 0,
      header_notes: ch.header_notes || [],
      footer_notes: ch.footer_notes || [],
    })),
  }
}

export async function refetchFailedChapters(docId: string): Promise<{
  code: number
  message: string
  mode?: string
  succeeded?: number
  failed?: number
}> {
  return apiRequest(`/api/study/documents/${encodeURIComponent(docId)}/refetch-failed-chapters`, {
    method: 'POST',
  })
}

export async function uploadDocument(file: File): Promise<DocumentMeta> {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await fetch('/api/study/documents/upload', {
    method: 'POST',
    body: formData,
  })
  if (!resp.ok) throw new Error(`Upload failed: ${resp.statusText}`)
  const json = await resp.json()
  const d = json.data
  return {
    doc_id: d.doc_id,
    title: d.filename || '未命名文档',
    source_file: d.filename || '',
    file_type: d.file_type || 'pdf',
    paragraph_count: d.total_paragraphs || 0,
    translated_count: 0,
    created_at: d.created_at || '',
    status: d.status || 'processing',
    chapters: (d.chapters || []).map((ch: any, idx: number) => ({
      chapter_id: ch.chapter_id,
      title: ch.title || `第 ${idx + 1} 章`,
      index: idx,
      header_notes: [],
      footer_notes: [],
    })),
  }
}

export async function inspectWebUrl(url: string) {
  return await apiRequest<import('@/types').WebInspectResult>('/api/study/documents/inspect-url', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export async function importWebDocument(payload: {
  url: string
  title?: string
  selected_chapters: any[]
}): Promise<DocumentMeta> {
  const d = await apiRequest<any>('/api/study/documents/import-url', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return {
    doc_id: d.doc_id,
    title: d.filename || '网页研学材料',
    source_file: d.filename || '',
    file_type: 'web',
    paragraph_count: 0,
    translated_count: 0,
    created_at: d.created_at || '',
    status: d.status || 'processing',
    chapters: [],
  }
}

export async function importFolderFiles(files: File[], folderName: string = 'Markdown Folder'): Promise<DocumentMeta> {
  const formData = new FormData()
  for (const f of files) {
    // preserve webkitRelativePath if present
    const pathName = (f as any).webkitRelativePath || f.name
    formData.append('files', f, pathName)
  }
  formData.append('folder_name', folderName)

  const resp = await fetch('/api/study/documents/import-folder', {
    method: 'POST',
    body: formData,
  })
  if (!resp.ok) {
    const err = await resp.text()
    throw new Error(`Folder upload failed: ${err || resp.statusText}`)
  }
  const json = await resp.json()
  const d = json.data
  return {
    doc_id: d.doc_id,
    title: d.filename || folderName,
    source_file: d.filename || '',
    file_type: 'folder',
    paragraph_count: 0,
    translated_count: 0,
    created_at: d.created_at || '',
    status: d.status || 'processing',
    chapters: [],
  }
}

export async function deleteDocument(docId: string): Promise<void> {
  await apiRequest(`/api/study/documents/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
  })
}

export async function getAssetInspection(docId: string): Promise<any> {
  const res = await apiRequest<{ code: number; data: any }>(
    `/api/study/documents/${encodeURIComponent(docId)}/asset_inspection`
  )
  return res.data
}

export async function reInspectAssets(docId: string): Promise<any> {
  const res = await apiRequest<{ code: number; data: any; message: string }>(
    `/api/study/documents/${encodeURIComponent(docId)}/re_inspect_assets`,
    { method: 'POST' }
  )
  return res.data
}

export async function getChapterDetail(
  docId: string,
  chapterId: string
): Promise<{ chapter: ChapterItem; paragraphs: ParagraphItem[] }> {
  const res = await apiRequest<any>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}`
  )
  const ch = res.chapter || {}
  const rawParagraphs: any[] = ch.paragraphs || []

  const paragraphs: ParagraphItem[] = rawParagraphs.map((p, idx) => ({
    id: p.id || `p_${idx}`,
    doc_id: docId,
    chapter_id: chapterId,
    order: idx,
    source_text: p.english || p.source_text || '',
    translated_text: p.chinese || p.translated_text || '',
    extracted_text: p.extracted_text || p.ocr_text || '',
    image_url: p.image_url || '',
    type: p.type || 'text',
    page: p.page,
    status: p.status || 'completed',
    error: p.error,
    notes: p.notes || [],
  }))

  const chapter: ChapterItem = {
    chapter_id: ch.chapter_id || chapterId,
    title: ch.title || '章节正文',
    index: ch.index || 0,
    header_notes: ch.header_notes || [],
    footer_notes: ch.footer_notes || [],
  }

  return { chapter, paragraphs }
}

export async function deleteChapter(
  docId: string,
  chapterId: string
): Promise<{
  document_deleted: boolean
  doc_id: string
  deleted_chapter_id: string
  deleted_cards_count: number
  remaining_chapters?: any[]
  total_paragraphs?: number
  translated_paragraphs?: number
}> {
  return apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}`,
    {
      method: 'DELETE',
    }
  )
}

export async function renameChapter(
  docId: string,
  chapterId: string,
  title: string
): Promise<{
  doc_id: string
  chapter_id: string
  title: string
  remaining_chapters: ChapterItem[]
}> {
  return apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}/rename`,
    {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }
  )
}

export async function shiftChapterParagraphs(
  docId: string,
  chapterId: string,
  paragraphId: string,
  direction: 'prev' | 'next'
): Promise<{
  success: boolean
  doc_id: string
  direction: 'prev' | 'next'
  source_chapter_id: string
  target_chapter_id: string
  source_deleted: boolean
  moved_count: number
  remaining_chapters: ChapterItem[]
  total_paragraphs: number
  translated_paragraphs: number
}> {
  return apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}/paragraphs/${encodeURIComponent(paragraphId)}/shift_chapter`,
    {
      method: 'POST',
      body: JSON.stringify({ direction }),
    }
  )
}

export async function splitChapterFromParagraph(
  docId: string,
  chapterId: string,
  paragraphId: string,
  newTitle: string
): Promise<{
  success: boolean
  doc_id: string
  source_chapter_id: string
  new_chapter_id: string
  new_title: string
  split_count: number
  remaining_chapters: ChapterItem[]
  total_paragraphs: number
  translated_paragraphs: number
}> {
  return apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}/paragraphs/${encodeURIComponent(paragraphId)}/split_chapter`,
    {
      method: 'POST',
      body: JSON.stringify({ new_title: newTitle }),
    }
  )
}

export async function extractParagraphText(
  docId: string,
  chapterId: string,
  paragraphId: string
): Promise<ParagraphItem> {
  const res = await apiRequest<any>(
    `/api/study/documents/${encodeURIComponent(docId)}/paragraphs/extract_text`,
    {
      method: 'POST',
      body: JSON.stringify({
        chapter_id: chapterId,
        paragraph_id: paragraphId,
      }),
    }
  )
  const p = res || {}
  return {
    id: p.id || paragraphId,
    doc_id: docId,
    chapter_id: chapterId,
    order: p.order || 0,
    source_text: p.english || p.source_text || '',
    translated_text: p.chinese || p.translated_text || '',
    extracted_text: p.extracted_text || p.ocr_text || '',
    image_url: p.image_url || '',
    type: p.type || 'scanned_page',
    page: p.page,
    status: p.status || 'completed',
  }
}

export async function retranslateParagraph(
  docId: string,
  chapterId: string,
  paragraphId: string
): Promise<ParagraphItem> {
  const res = await apiRequest<any>(
    `/api/study/documents/${encodeURIComponent(docId)}/translate_paragraph`,
    {
      method: 'POST',
      body: JSON.stringify({ chapter_id: chapterId, paragraph_id: paragraphId }),
    }
  )
  return {
    id: res.id || paragraphId,
    doc_id: docId,
    chapter_id: chapterId,
    order: 0,
    source_text: res.english || '',
    translated_text: res.chinese || '',
    status: res.status || 'completed',
  }
}

export async function editParagraph(
  docId: string,
  chapterId: string,
  paragraphId: string,
  sourceText: string,
  options?: { is_heading?: boolean; retranslate?: boolean; new_paragraph_text?: string; type?: string }
): Promise<{ updated_paragraph: ParagraphItem; new_paragraph?: ParagraphItem }> {
  const res = await apiRequest<any>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}/paragraphs/${encodeURIComponent(paragraphId)}`,
    {
      method: 'PUT',
      body: JSON.stringify({
        source_text: sourceText,
        is_heading: options?.is_heading,
        retranslate: options?.retranslate ?? false,
        new_paragraph_text: options?.new_paragraph_text,
        type: options?.type,
      }),
    }
  )
  const upRaw = res.updated_paragraph || res
  const updated_paragraph: ParagraphItem = {
    id: upRaw.id || paragraphId,
    doc_id: docId,
    chapter_id: chapterId,
    order: 0,
    source_text: upRaw.english || '',
    translated_text: upRaw.chinese || '',
    extracted_text: upRaw.extracted_text || '',
    image_url: upRaw.image_url || '',
    type: upRaw.type || 'text',
    page: upRaw.page,
    status: upRaw.status || 'pending',
    notes: upRaw.notes || [],
  }

  let new_paragraph: ParagraphItem | undefined
  if (res.new_paragraph) {
    const npRaw = res.new_paragraph
    new_paragraph = {
      id: npRaw.id,
      doc_id: docId,
      chapter_id: chapterId,
      order: 0,
      source_text: npRaw.english || '',
      translated_text: npRaw.chinese || '',
      extracted_text: npRaw.extracted_text || '',
      image_url: npRaw.image_url || '',
      type: npRaw.type || 'text',
      page: npRaw.page,
      status: npRaw.status || 'pending',
      notes: npRaw.notes || [],
    }
  }

  return { updated_paragraph, new_paragraph }
}

export async function mergeParagraphs(
  docId: string,
  chapterId: string,
  paragraphId: string,
  direction: 'prev' | 'next',
  retranslate = false
): Promise<{ merged_paragraph: ParagraphItem; removed_id: string }> {
  const res = await apiRequest<any>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}/paragraphs/${encodeURIComponent(paragraphId)}/merge`,
    {
      method: 'POST',
      body: JSON.stringify({
        direction,
        retranslate,
      }),
    }
  )
  const mp = res.merged_paragraph || {}
  return {
    merged_paragraph: {
      id: mp.id || paragraphId,
      doc_id: docId,
      chapter_id: chapterId,
      order: 0,
      source_text: mp.english || '',
      translated_text: mp.chinese || '',
      extracted_text: mp.extracted_text || '',
      image_url: mp.image_url || '',
      type: mp.type || 'text',
      page: mp.page,
      status: mp.status || 'pending',
      notes: mp.notes || [],
    },
    removed_id: res.removed_id,
  }
}

export async function deleteParagraph(
  docId: string,
  chapterId: string,
  paragraphId: string
): Promise<{ success: boolean; deleted_paragraph_id: string; chapter_id: string }> {
  return await apiRequest<{ success: boolean; deleted_paragraph_id: string; chapter_id: string }>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapters/${encodeURIComponent(chapterId)}/paragraphs/${encodeURIComponent(paragraphId)}`,
    {
      method: 'DELETE',
    }
  )
}

export async function createFlashcard(
  docId: string,
  payload: {
    type: string
    front: string
    back?: string
    chapter_id?: string
    paragraph_id?: string
    tags?: string[]
  }
): Promise<any> {
  return apiRequest(`/api/study/documents/${encodeURIComponent(docId)}/flashcards`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getDocFlashcardsCount(docId: string): Promise<number> {
  try {
    const res = await apiRequest<any>(
      `/api/study/documents/${encodeURIComponent(docId)}/flashcards`
    )
    return (
      res?.summary?.total_cards ??
      res?.summary?.total ??
      res?.total ??
      res?.cards?.length ??
      res?.data?.summary?.total_cards ??
      res?.data?.summary?.total ??
      res?.data?.total ??
      0
    )
  } catch (e) {
    console.warn(`Failed to get flashcards count for doc ${docId}:`, e)
    return 0
  }
}

// Batch Translation
export async function startChapterTranslation(docId: string, chapterId: string): Promise<BatchTranslationStatus> {
  return apiRequest<BatchTranslationStatus>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/translate_start`,
    { method: 'POST' }
  )
}

export async function stopChapterTranslation(docId: string, chapterId: string): Promise<BatchTranslationStatus> {
  return apiRequest<BatchTranslationStatus>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/translate_stop`,
    { method: 'POST' }
  )
}

export async function getChapterTranslationStatus(docId: string, chapterId: string): Promise<BatchTranslationStatus> {
  return apiRequest<BatchTranslationStatus>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/translate_status`
  )
}

export async function startDocumentTranslation(docId: string): Promise<BatchTranslationStatus> {
  return apiRequest<BatchTranslationStatus>(
    `/api/study/documents/${encodeURIComponent(docId)}/translate_start`,
    { method: 'POST' }
  )
}

export async function stopDocumentTranslation(docId: string): Promise<BatchTranslationStatus> {
  return apiRequest<BatchTranslationStatus>(
    `/api/study/documents/${encodeURIComponent(docId)}/translate_stop`,
    { method: 'POST' }
  )
}

export async function getDocumentTranslationStatus(docId: string): Promise<BatchTranslationStatus> {
  return apiRequest<BatchTranslationStatus>(
    `/api/study/documents/${encodeURIComponent(docId)}/translate_status`
  )
}

// Providers & Models
export async function getAvailableProviders(): Promise<ProviderItem[]> {
  return apiRequest<ProviderItem[]>('/api/study/providers')
}

export async function getProviderModels(providerId: string, forceRefresh = false): Promise<string[]> {
  if (!providerId) return []
  return apiRequest<string[]>('/api/study/providers/models', {
    method: 'POST',
    body: JSON.stringify({ provider: providerId, force_refresh: forceRefresh }),
  })
}

export async function getProvidersConfig(): Promise<ProvidersConfig> {
  return apiRequest<ProvidersConfig>('/api/study/providers/config')
}

export async function saveProvidersConfig(payload: ProvidersConfig): Promise<void> {
  await apiRequest('/api/study/providers/config', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function testProviderConnection(payload: any): Promise<{
  connected: boolean
  message: string
  models: string[]
}> {
  return apiRequest('/api/study/providers/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// Settings
export async function getDocSettings(docId?: string): Promise<DocSettings> {
  let url = '/api/study/settings'
  if (docId) url += `?doc_id=${encodeURIComponent(docId)}`
  return apiRequest<DocSettings>(url)
}

export async function saveDocSettings(payload: DocSettings, docId?: string): Promise<void> {
  let url = '/api/study/settings'
  if (docId) url += `?doc_id=${encodeURIComponent(docId)}`
  await apiRequest(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function resetDocSettings(docId: string): Promise<void> {
  await apiRequest(`/api/study/settings/reset?doc_id=${encodeURIComponent(docId)}`, {
    method: 'POST',
  })
}

// Notes
export async function saveChapterNote(
  docId: string,
  chapterId: string,
  type: 'header' | 'footer',
  title: string,
  content: string,
  noteId?: string
): Promise<void> {
  if (noteId) {
    await apiRequest(
      `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/notes/${encodeURIComponent(noteId)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ position: type, type, title, content }),
      }
    )
  } else {
    await apiRequest(
      `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/notes`,
      {
        method: 'POST',
        body: JSON.stringify({ position: type, type, title, content }),
      }
    )
  }
}

export async function deleteChapterNote(
  docId: string,
  chapterId: string,
  type: 'header' | 'footer',
  noteId: string
): Promise<void> {
  await apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/notes/${encodeURIComponent(noteId)}?position=${encodeURIComponent(type)}`,
    { method: 'DELETE' }
  )
}

export async function addParagraphNote(
  docId: string,
  chapterId: string,
  paragraphId: string,
  content: string
): Promise<any> {
  const res = await apiRequest<{ code: number; data: any }>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/paragraph/${encodeURIComponent(paragraphId)}/notes`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    }
  )
  return res?.data
}

export async function updateParagraphNote(
  docId: string,
  chapterId: string,
  paragraphId: string,
  noteId: string,
  content: string
): Promise<any> {
  const res = await apiRequest<{ code: number; data: any }>(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/paragraph/${encodeURIComponent(paragraphId)}/notes/${encodeURIComponent(noteId)}`,
    {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }
  )
  return res?.data
}

export async function deleteParagraphNote(
  docId: string,
  chapterId: string,
  paragraphId: string,
  noteId: string
): Promise<void> {
  await apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chapter/${encodeURIComponent(chapterId)}/paragraph/${encodeURIComponent(paragraphId)}/notes/${encodeURIComponent(noteId)}`,
    { method: 'DELETE' }
  )
}

// Chat History Persistence
export async function getChatHistory(
  docId: string,
  chatType: 'paragraph' | 'chapter' | 'document',
  chapterId: string = '',
  paragraphId?: string
): Promise<any[]> {
  const params = new URLSearchParams({
    chat_type: chatType,
    chapter_id: chapterId,
  })
  if (paragraphId) {
    params.append('paragraph_id', paragraphId)
  }
  const res = await apiRequest<{ code: number; data: { messages: any[] } }>(
    `/api/study/documents/${encodeURIComponent(docId)}/chat_history?${params.toString()}`
  )
  return res?.data?.messages || []
}

export async function saveChatHistory(
  docId: string,
  chatType: 'paragraph' | 'chapter' | 'document',
  chapterId: string = '',
  messages: any[],
  paragraphId?: string
): Promise<void> {
  const params = new URLSearchParams({
    chat_type: chatType,
    chapter_id: chapterId,
  })
  if (paragraphId) {
    params.append('paragraph_id', paragraphId)
  }
  await apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chat_history?${params.toString()}`,
    {
      method: 'POST',
      body: JSON.stringify({ messages }),
    }
  )
}

export async function clearChatHistory(
  docId: string,
  chatType: 'paragraph' | 'chapter' | 'document',
  chapterId: string = '',
  paragraphId?: string
): Promise<void> {
  const params = new URLSearchParams({
    chat_type: chatType,
    chapter_id: chapterId,
  })
  if (paragraphId) {
    params.append('paragraph_id', paragraphId)
  }
  await apiRequest(
    `/api/study/documents/${encodeURIComponent(docId)}/chat_history?${params.toString()}`,
    { method: 'DELETE' }
  )
}

