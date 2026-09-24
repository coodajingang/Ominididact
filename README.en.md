<div align="center">

<img src="docs/assets/logo.png" width="120" height="120" alt="Omnididact Logo" />

# Omnididact

### The AI-Powered Deep Study Assistant for Systematically Learning & Mastering Any Material
**Master complex books, technical papers, certifications, and foreign documents with paragraph-level bilingual alignment, in-situ Feynman probing, 3D SM-2 flashcards, and zero-dependency offline exports.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Frontend: React 18 / 19](https://img.shields.io/badge/Frontend-React_%2B_Vite-61dafb.svg)](https://react.dev/)
[![Docker: Ready](https://img.shields.io/badge/Docker-Ready-2496ed.svg)](Dockerfile)
[![Self-Directed Learning](https://img.shields.io/badge/Philosophy-Autodidact-purple.svg)](#-why-omnididact)

[ English ](./README.en.md) | [ 简体中文 ](./README.md)

</div>

---

## 🌟 Why Omnididact?

> *"Education is what remains after one has forgotten what one has learned in school." — Albert Einstein*

When tackling an 800-page CISSP certification guide, an arXiv deep learning paper, an intricate distributed systems whitepaper, or a dense foreign monograph, every serious **Autodidact** faces the same bottlenecks:
* **Fragmented Machine Translation**: Word-by-word automated tools miss macro-context, mutilate hyphenated lines, and produce jarring, incoherent phrasing;
* **The "Illusion of Competence" from Superficial Summaries**: Skimming a 3-bullet AI summary feels satisfying, but leaves zero retention or structural comprehension when you actually try to apply the knowledge;
* **Lack of Deep Deconstruction & In-Situ Questioning**: When encountering obscure mathematical derivations, implicit assumptions, or domain concepts, there is nowhere to probe questions and trace the author's train of thought.

> 💡 **Special Clarification**: **Omnididact is NOT a generic "knowledge base", nor is it a tool to "organize fragmented notes".**  
> Its core mission is to act as your **deep study assistant**: grounded in the science of self-education, it helps you **dissect line by line, interrogate in-situ, break down difficulties, and genuinely comprehend and internalize complex knowledge into your own mastery.**

---

## 🔄 The Self-Education & Study Closed Loop

```
     📥 Omni-Material Hub                🔍 Structural Ingestion             📖 Bilingual Studio
 [Web Series / Folder / EPUB] ──▶  [TOC Tree Sniff / Concurrent Sync] ──▶ [Side-by-Side Paragraphs]
 [PDF / Word / MD / TXT]           [Hyphen Stitch / Asset Offline Cache]        │
                                                                                ▼
    🌐 Offline Review Portal             🗂️ Scientific Retention          🤖 In-Situ Study Copilot
  [Single-File / Static SPA]  ◀──   [SM-2 Spaced Repetition]    ◀──   [Feynman Probing & Q&A]
```

1. **Omni-Material Ingestion**: Accurately extracts hierarchical headings, code blocks, equations, and diagrams from PDFs, Word docs, EPUBs, Markdown folders, and web series docs.
2. **In-Order Concurrency & Self-Healing**: Crawls massive web documentation (e.g. 1000+ chapters) with 8 parallel controlled workers, 25s fault isolation, automatic retries, online image fallbacks, and selective chapter refetching.
3. **Bilingual Studio**: Parallel paragraph alignment with default Sepia and 4 curated eye-care themes; auto-hiding topbar on scroll down for distraction-free focus.
4. **In-Situ Copilot (Core)**: Sliding-window context-aware AI tutor at the paragraph level. Interrogate obscure phrasing, explore engineering tradeoffs, and deconstruct complex formulas on the fly.
5. **Scientific Retention**: Distills key concepts into interactive 3D flashcards and cloze-deletion tests driven by the scientific **SuperMemo SM-2** spaced repetition algorithm for active recall.
6. **Portable Offline Results**: All bilingual alignments, copilot explanations, and self-testing flashcards can be exported into standalone HTML or zero-dependency static portals for offline review anywhere, or deployed to Cloudflare Pages / GitHub Pages.

---

## 📸 Visual Workflow & Operating Guide

Omnididact delivers a complete closed-loop learning experience: **"LLM Configuration ➔ Material Ingestion ➔ Batch Translation & Bilingual Alignment ➔ Paragraph Copilot Q&A ➔ Flashcard Extraction ➔ SM-2 Retention"**. Below is a detailed walkthrough of each stage:

### 1️⃣ LLM Provider & Service Matrix Configuration (Provider Settings)

A decoupled model abstraction layer lets private local engines collaborate smoothly with cloud APIs, assigning specialized models to distinct learning roles:

<div align="center">
  <img src="docs/assets/screenshots/01-provider_register.png" alt="01 LLM Provider Configuration" width="88%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);" />
</div>

* **Unified Multi-Provider Ingestion**: Native support for **OpenAI-compatible protocols** (DeepSeek, OpenRouter, SiliconFlow, Moonshot, vLLM), **Local runtimes** (Ollama, LM Studio), **Cloud & Edge AI** (Cloudflare Workers AI, NVIDIA NIM, AMD ROCm), and extensible gateway plugins;
* **Task-Specific Model Routing**: Assign dedicated providers and models for **Text Translation**, **Study Copilot**, and **Multimodal / OCR Vision**;
* **Instant Connectivity Testing**: Verify Base URLs and API Keys with one click while automatically fetching and updating the latest available model catalog.

---

### 2️⃣ Deep Study Studio & In-Situ AI Copilot (Study Workbench)

Inside the Study Center (`/study`), enjoy an all-in-one workbench for document reading, bilingual alignment, contextual inquiry, annotation, and flashcard creation:

<div align="center">
  <img src="docs/assets/screenshots/03-main_chat.png" alt="02 Study Workbench & Copilot" width="88%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);" />
</div>

* **📥 Omni-Material Import Hub**:
  Click **【Import Study Materials】** in the sidebar to ingest up to 4 major knowledge carriers:
  * **🌐 Web Series / Technical Docs Site**:
    * Automatically sniffs documentation sidebars (MkDocs, Docusaurus, GitBook, Sphinx, etc.);
    * Detects active modules and sister sections (e.g. OWASP MASTG chapters) with multi-select tree picking;
    * **8-Worker In-Order Concurrency**: Compresses 1000+ chapter crawl times from 1+ hour down to 5~8 minutes while strictly preserving original reading sequence;
    * **25s Fault Isolation & Auto-Retry**: Prevents single-page timeouts from stalling the pipeline;
    * **Dual-Track Image Fallback**: Preserves original remote absolute URLs if local download fails, preventing 404 broken images;
    * **Selective Chapter Refetch**: Displays `Refetch Failed (X)` in the document options menu to rapidly heal missing or timed-out chapters on demand.
  * **📁 Markdown Folders & Zip Bundles**:
    * Pick native local folders in the browser or upload `.zip` archives;
    * Detects `SUMMARY.md`, `mkdocs.yml`, `_sidebar.md`, or numeric ordering, and migrates `images/` attachments automatically.
  * **📚 Native EPUB E-Books**:
    * Pure native container unpacker that extracts title, author, NCX/NAV navigation, and chapters in linear reading spine order.
  * **📄 Standard Academic Documents**:
    * Native support for **PDF (Text/Scanned), Word (DOCX), Markdown, and TXT**.
* **⚡ Batch Translation & Bilingual Alignment**:
  * Trigger **【⚡ Batch Translate】** in the top bar or **【⚡ Batch Translate Chapter】** to automatically translate paragraphs with the selected model;
  * Enjoy parallel paragraph formatting with default Sepia and 4 eye-care themes, plus auto-hiding topbar on downward scroll for deep focus.
* **🤖 Paragraph-Level In-Situ Copilot**:
  * Click the **【🤖】** icon next to any paragraph to open the sidecar AI tutor;
  * **Sliding Context Window**: Automatically ingest previous and subsequent paragraphs ($N$ preceding and $M$ succeeding blocks) to preserve holistic context;
  * **Pre-Engineered Prompt Capsules**: Instantly analyze complex sentences, extract technical jargon, get intuitive Feynman analogies, or generate self-testing quiz questions.
* **📝 Structured Study Notes & Chapter Overviews**:
  * Add chapter overview summaries at the top of each chapter, or capture selected text into rich markdown notes.
* **🗂️ One-Click Flashcard Extraction**:
  * When the copilot distills key insights, it automatically produces formatted QA or Cloze flashcard candidates;
  * Click **【➕ Adopt into Flashcards】** to immediately save them into the active document's flashcard deck.

---

### 3️⃣ SM-2 Flashcard Retention & Socratic Self-Testing (Flashcard Center)

Click **【🗂️ Flashcards】** in the top navigation to enter the **SM-2 Memory Center**, turning synthesized insights into permanent knowledge:

<div align="center">
  <img src="docs/assets/screenshots/02-flashcard_chat.png" alt="03 SM-2 Flashcard Study" width="88%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);" />
</div>

* **🎴 Tactile 3D Card Flips**:
  * Front side presents the question or cloze passage; tap `Space` or click to smoothly flip to the detailed reverse explanation;
  * Engages **Active Recall** to counter passive illusions of competence.
* **🧠 Heuristic Socratic AI Copilot (No Spoilers)**:
  * When stuck, don't surrender and flip immediately. Click **【💡 Clues & Hints】**, **【🎯 Key Concept Anchor】**, or **【🗺️ Conceptual Background】** — the AI tutor provides guided hints without revealing the answer, prompting your brain to retrieve it actively.
* **📈 SuperMemo SM-2 Spaced Repetition Scheduling**:
  * Grade your recall difficulty:
    * `[1] Again / Forgot` (Resets review interval, adds to error drill deck)
    * `[2] Hard / Vague` (Shortens interval for intensified practice)
    * `[3] Good / Remembered` (Advances standard spaced repetition curve)
    * `[4] Easy / Mastered` (Extends review interval for solidified retention)
  * The SM-2 algorithm calculates the optimal next review date, banishing the Ebbinghaus forgetting curve.

---

## 🔥 Key Features

### 1. Immersive Bilingual Reading Workbench (React + TypeScript + Tailwind)
- **Fluid Layout Modes**: Switch between Standard (1100px), Compact (850px), Wide, and Full-Width reading containers with incremental font resizing (`A-` / `A+`).
- **4 Reading Themes**: Eye-friendly Antique Sepia (Default), Midnight Dark, Crisp Light, and Forest Calm.
- **Dynamic Smart Navigation**: Auto-hiding header that smoothly reappears when scrolling up; instant chapter jump tree.

### 2. Omni-Material Ingestion Engine (Import Hub)
- **Multi-Carrier Material Support**:
  - **Web Series / Technical Docs Site**: Native MkDocs, Docusaurus, GitBook, and Sphinx sidebar sniffing with multi-select picking;
  - **Project Bundles (Folder & Zip)**: Browser folder selection or `.zip` archives with automatic `SUMMARY.md` / `mkdocs.yml` resolution;
  - **Native E-Books (EPUB)**: Zero-loss container parsing for OPF metadata, NCX navigation, and embedded graphics;
  - **Academic Documents**: High-fidelity processing of **PDF (text and scan-based), DOCX, and TXT**.
- **Embedded Visuals & Dual-Track Fallback**: Localized offline image caching with automatic online absolute URL fallback to eliminate 404 broken images;
- **Typography Auto-Repair**: Heuristic line-break stitcher reconciles mid-word hyphenations across page breaks;
- **8-Worker In-Order Concurrency & Self-Healing**: Controlled parallel web ingestion for 1000+ chapter books with 25s timeout isolation and on-demand selective chapter refetching.

### 3. Universal Multi-Model Engine (Local & Cloud Agnostic)
Decoupled model abstraction layer with hot-swapping and live latency testing:
- 🟢 **LM Studio**: Run local weights privately on your GPU (default: `http://127.0.0.1:1234/v1`);
- 🦙 **Ollama**: Instant local inference for Llama 3, Qwen 2.5, DeepSeek-R1 (default: `http://127.0.0.1:11434`);
- 🌐 **OpenAI Compatible**: Direct connection to DeepSeek, OpenAI, OpenRouter, Moonshot, SiliconFlow, or vLLM;
- ⚡ **Cloud Providers**: Native support for Anthropic Claude, Google Gemini, and Cloudflare Workers AI;
- 🧩 **Plugin Architecture**: Zero-friction extensibility via `plugins/` to integrate private enterprise gateways or bespoke reverse proxies.

### 4. 🎴 Interactive 3D SM-2 Flashcards
<p align="left">
  <img src="docs/assets/flashcard_icon.png" width="48" height="48" alt="Flashcards SM-2" style="vertical-align: middle; margin-right: 8px;" />
  <span>Powered by the scientific <b>SuperMemo SM-2 Spaced Repetition Algorithm</b> and <b>tactile 3D card flips</b> to overcome the Ebbinghaus forgetting curve.</span>
</p>
- **Realistic 3D Card Flips**: Front prompt, reverse deep-dive breakdown with keyboard navigation (`Space` to flip, `1-4` for grading).
- **Cloze Deletion Masks**: Hide key terminology until clicked to actively trigger memory retrieval.
- **SuperMemo SM-2 Scheduling**: Automatically calculates the next review interval based on recall difficulty (*Again, Hard, Good, Easy*).
- **Flashcard AI Tutor**: Ask for heuristic hints (without spoiling the answer) or mnemonics directly within the card widget.

### 5. Zero-Dependency Offline Study Results & Self-Testing Portal
- **Offline Multi-Document Portal SPA**: One-click bundling of all your studied materials, parallel translations, AI Q&A notes, and flashcards into a standalone static review portal with fuzzy search, category filtering, and review progress memory.
- **Zero-Cost Edge Hosting & Local Use**: Double-click to browse and self-test completely offline without Python, or drag-and-drop onto **Cloudflare Pages** or **GitHub Pages** for instant global hosting.
- **Incremental Patch Workflow**: When you digest a new paper, simply export an incremental patch zip and merge it into your portal — no need to recompile the full archive!

---

## 🚀 5-Minute Quickstart

### Option A: Run with Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/coodajingang/Ominididact.git
cd Ominididact

# 2. Prepare configuration
cp config.example.json config.json

# 3. Start container in background
docker compose up -d

# 4. Open in your browser
# Visit http://localhost:8000/study
```

### Option B: Local Python & React Setup

#### 1. Backend Setup
```bash
git clone https://github.com/coodajingang/Ominididact.git
cd Ominididact

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start backend server
python proxy.py
```

#### 2. Frontend Development Server
```bash
cd frontend
npm install
npm run dev
# Vite dev server starts at http://localhost:5173
```

To create a production build served directly by FastAPI:
```bash
cd frontend
npm run build
# Now accessible directly at http://localhost:8000/study
```

---

## 📦 Zero-Dependency Offline Study Results & Self-Testing Guide

Omnididact allows you to export your completed studies, bilingual alignments, and flashcard decks as standalone static files that run without Python:

```
your-offline-study-pack/
├── index.html            # 🏛️ Multi-Document Study Portal & Review SPA
├── docs.json             # 🗂️ Metadata index of all studied materials
└── docs/
    ├── doc_001/          # 📄 Material A
    │   ├── index.html    # Standalone bilingual deep reading view
    │   └── flashcards.html # Offline 3D SM-2 flashcard self-testing
    └── doc_002/          # 📄 Material B
```

### Local Offline Review or Cloudflare Pages Hosting
1. In the Omnididact sidebar, click **[📦 Export Library Site]**.
2. **Local Offline Review**: Unzip the downloaded archive and double-click `index.html`. You can review all study notes, parallel translations, and test your memory cards in any browser completely offline.
3. **Free Edge Hosting**: Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **Create application** → **Pages** → **Upload assets**. Drag and drop the folder to host your study results worldwide.

### Incremental Updates (Patching)
When you finish studying a new document later:
1. Click **[Export]** → **[🧩 Export Patch Package (.zip)]** on that document's page.
2. Unzip and copy `docs/<doc_id>` into your existing `docs/` folder.
3. Copy the entry from `patch_entry.json` into your root `docs.json`. The portal will immediately surface the new material.

---

## 🔌 Custom Gateway Plugin System

To integrate an internal corporate proxy, specialized token exchange, or proprietary LLM endpoint without modifying core code:

1. Create a directory under `plugins/` (see `plugins/custom_gateway_example/` for reference);
2. Inherit from `BaseProvider` and implement `stream_chat()` and `get_available_models()`;
3. Omnididact will automatically discover, load, and surface it in the UI settings!

---

## 🧪 Testing

Omnididact includes a comprehensive automated test suite:

```bash
# Run unit tests
python3 -m unittest discover -s test

# Run document parsing & bilingual service tests
python3 test/test_study_service.py

# Run API integration tests
python3 test/test_study_api.py

# Run provider abstraction tests
python3 test/test_providers.py
```

---

## 🛣️ Roadmap

- [x] Paragraph-level parallel bilingual reader with 4 custom themes
- [x] Multi-provider LLM abstraction (Ollama, LM Studio, OpenAI, Gemini, Claude, Cloudflare)
- [x] 3D Spaced-repetition Flashcards with SM-2 algorithm & cloze masks
- [x] Multi-document static library portal with search & tag filtering
- [x] Incremental patch export for Cloudflare Pages / GitHub Pages
- [x] Docker multi-stage build & Docker Compose 1-click startup
- [ ] EPUB and MOBI eBook parser integration
- [ ] Anki export package (`.apkg`) bidirectional sync
- [ ] Voice synthesis (Web Speech API & Edge-TTS) for ear-training companion
- [ ] Multi-document semantic vector search across personal study library

---

## 📄 License

This project is licensed under the [Apache 2.0 License](LICENSE).
