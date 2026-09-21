export type ThemeMode = 'dark' | 'white' | 'sepia' | 'forest'

export type FontFamilyMode = 'sans' | 'wenkai' | 'serif' | 'system'

export type ReadingWidth = 'standard' | 'wide' | 'full'

export type LayoutMode = 'stack' | 'side' | 'card'

export interface DocumentMeta {
  doc_id: string
  title: string
  source_file: string
  file_type: string
  paragraph_count: number
  translated_count: number
  total_paragraphs?: number
  created_at: string
  status: string
  progress_percent?: number
  chapters?: ChapterItem[]
}

export interface ChapterNoteItem {
  id: string
  title: string
  content: string
  created_at: string
}

export interface ChapterItem {
  chapter_id: string
  title: string
  index: number
  paragraph_count?: number
  start_paragraph_id?: string
  end_paragraph_id?: string
  header_notes?: ChapterNoteItem[]
  footer_notes?: ChapterNoteItem[]
}

export interface ParagraphNoteItem {
  id: string
  content: string
  created_at?: string
}

export interface ParagraphItem {
  id: string
  doc_id: string
  chapter_id?: string
  order: number
  source_text: string
  translated_text?: string
  extracted_text?: string
  image_url?: string
  type?: string
  page?: number
  status: 'pending' | 'translating' | 'completed' | 'failed'
  error?: string
  notes?: ParagraphNoteItem[]
}

export interface ProviderItem {
  id: string
  name: string
  type: string
  is_local: boolean
  supports_vision: boolean
}

export interface ProvidersConfig {
  providers: {
    openai_compatible?: {
      base_url?: string
      api_key?: string
      model?: string
    }
    ollama?: {
      base_url?: string
      model?: string
    }
    lm_studio?: {
      base_url?: string
      model?: string
    }
    nvidia?: {
      base_url?: string
      api_key?: string
      model?: string
    }
    amd?: {
      base_url?: string
      api_key?: string
      model?: string
    }
    cloudflare?: {
      account_id?: string
      api_token?: string
      model?: string
    }
    [key: string]: any
  }
  defaults: {
    default_translation_provider: string
    default_translation_model: string
    default_chat_provider: string
    default_chat_model: string
    default_vlm_provider: string
    default_vlm_model: string
  }
}

export interface QuickPromptItem {
  label: string
  prompt: string
}

export interface DocSettings {
  is_doc_level?: boolean
  translation_prompt_template?: string
  model_call_delay?: number
  translation_provider?: string
  translation_model?: string
  chat_provider?: string
  chat_model?: string
  vlm_provider?: string
  vlm_model?: string
  paragraph_quick_prompts?: QuickPromptItem[]
  chapter_quick_prompts?: QuickPromptItem[]
  default_translation_provider?: string
  default_translation_model?: string
  default_chat_provider?: string
  default_chat_model?: string
  default_vlm_provider?: string
  default_vlm_model?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
  timestamp?: string
}

export interface BatchTranslationStatus {
  status: 'idle' | 'translating' | 'completed' | 'paused' | 'error'
  completed: number
  total: number
  untranslated?: number
  percent: number
  is_running: boolean
  is_doc_level_running?: boolean
  active_chapter_title?: string
  active_chapter_index?: number
  total_chapters?: number
}

