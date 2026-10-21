# 🎙️ 离线语音合成（TTS）系统设计方案与 Windows 离线部署指南 (Review 修订版)

> **核心目标**：为 Omnididact 研学系统引入**零外网依赖、低硬件开销、高音质中英双语**的本地离线语音合成能力。支持按段即时点播、Header 多维度批量预生成持久化、双语交替顺次朗读、段落合并/编辑音频联动自愈与智能视口平滑居中滚动。

---

## 目录
1. [技术选型与路线 A 架构总览](#1-技术选型与路线-a-架构总览)
2. [Windows 离线环境安装与包管理规范 (基于 packages/)](#2-windows-离线环境安装与包管理规范-基于-packages)
3. [TTS 数据存储、生命周期清理与重生成触发矩阵](#3-tts-数据存储生命周期清理与重生成触发矩阵)
4. [前端 UX 交互与播放体验设计 (Header 批量 + 段落悬浮面板)](#4-前端-ux-交互与播放体验设计-header-批量--段落悬浮面板)
5. [分步实施与工程排期计划](#5-分步实施与工程排期计划)

---

## 1. 技术选型与路线 A 架构总览

### 1.1 核心方案：Sherpa-onnx 驱动 MeloTTS 权重 (`vits-melo-tts-zh_en`)
- **底层引擎**：`sherpa-onnx`（基于 ONNXRuntime，C++ 底层封装为纯 Python Wheel，无需编译）。
- **模型权重**：`vits-melo-tts-zh_en`（包含 MeloTTS 官方中英双语训练权重，转换为了轻量 ONNX 格式）。
- **核心优势**：
  * **完全脱离 PyTorch**：无需安装 2GB~5GB 的 PyTorch/CUDA 庞大生态，运行时内存常驻仅 ~150MB。
  * **零 C++ 编译环境要求**：预编译 Wheel 自带静态绑定的 `onnxruntime.dll`，在 Windows 离线环境下**无需安装 Visual Studio C++ Build Tools**。
  * **中英无缝混读**：继承 MeloTTS 优异的中英双语自然衔接能力，完美发音专业文献中的中英文穿插术语（如 “*CIA 三要素*”、“*Access Control 机制*”）。
  * **CPU 毫秒级极速合成**：实时率 RTF < 0.1，1 秒音频仅需 50ms 即可计算完成。

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Omnididact Study Engine                         │
│                                                                        │
│   [段落纯文本] ──> [Markdown清洗管线] ──> [文本哈希校验 (MD5)]          │
│                                                 │                      │
│                                 ┌───────────────┴──────────────┐       │
│                                 ▼ (未命中缓存/失效)            ▼ (命中)│
│                     ┌────────────────────────┐         直接返回已有    │
│                     │  TTS 服务调度 (异步队列)│         音频 URL 播放   │
│                     │  Sherpa-onnx + MeloTTS │                        │
│                     └───────────┬────────────┘                        │
│                                 ▼                                      │
│                     [写入 data/.../audio/*.wav]                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Windows 离线环境安装与包管理规范 (基于 packages/)

本项目所有 Windows 离线依赖 Wheel 包**严格统一归档存放在根目录的 `packages/` 目录下**，并通过 `requirements.txt` 与 `pyproject.toml` 统一管理版本。

### 2.1 依赖项登记
已在 `requirements.txt` 与 `pyproject.toml` 中显式固化记录依赖：
```text
# requirements.txt
sherpa-onnx>=1.10.0
soundfile>=0.12.0
```

### 2.2 外网机器“备料”准备（一次性准备）

#### 步骤 1：下载 Windows 对应的预编译 Wheel 包到 packages/
在任意有外网的电脑上执行以下命令，直接下载 Windows x64 平台专用 Wheel 到 `packages/` 目录：
```bash
pip download \
    --only-binary=:all: \
    --platform win_amd64 \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    -d packages/ \
    sherpa-onnx soundfile
```
> 下载后，`packages/` 目录下将新增：
> - `sherpa_onnx-*-cp312-cp312-win_amd64.whl`
> - `sherpa_onnx_core-*-cp312-cp312-win_amd64.whl`
> - `soundfile-*-py2.py3-none-any.whl`
> - `cffi-*-cp312-cp312-win_amd64.whl`

#### 步骤 2：下载 MeloTTS 中英双语 ONNX 模型包
下载官方 Release 模型归档（约 160MB）：
- 下载地址：`https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2`
- 解压后得到目录 `vits-melo-tts-zh_en/`，其内部包含：
  * `model.onnx`（声学模型主体）
  * `lexicon.txt`（发音词典）
  * `tokens.txt`（标记表）
  * `dict/`（分词核心数据）
  * `espeak-ng-data/`（音素数据）

---

### 2.3 内网 Windows 目标机器离线装配

将 `packages/` 文件夹中新增的 wheel 与解压好的 `vits-melo-tts-zh_en` 文件夹拷贝至项目内：

#### 目录放置规范
```text
ai_jh_proxy/
├── packages/                       <-- 统一存放全部离线 .whl 文件
│   ├── sherpa_onnx-1.13.8-cp312-cp312-win_amd64.whl
│   ├── soundfile-0.13.1-py2.py3-none-any.whl
│   └── ... (现有45个离线wheels)
├── models/
│   └── tts/
│       └── vits-melo-tts-zh_en/    <-- 放置解压后的模型资源
│           ├── model.onnx
│           ├── lexicon.txt
│           ├── tokens.txt
│           ├── dict/
│           └── espeak-ng-data/
```

#### 执行离线安装命令（在 Windows CMD / PowerShell）
```bat
REM 若使用 uv 环境
uv pip install --no-index --find-links=packages sherpa-onnx soundfile

REM 若使用标准 Python 虚拟环境
.venv\Scripts\pip.exe install --no-index --find-links=packages sherpa-onnx soundfile
```

---

## 3. TTS 数据存储、生命周期清理与重生成触发矩阵

### 3.1 音频落盘存储目录
遵循系统现有的“文档+章节”物理隔离原则：
```text
data/documents/{doc_id}/
├── chapters/
│   └── ch_001.json
└── audio/
    └── ch_001/
        ├── p_001_0001_source.wav   # 原文语音文件
        ├── p_001_0001_target.wav   # 译文语音文件
        └── ...
```

### 3.2 段落生命周期与音频文件同步物理清理机制
当文档内容与段落结构发生变动时，必须联动清理关联音频，杜绝脏文件与“音文不符”：

| 用户操作 | 触发的服务端函数 | 音频处理与清理逻辑 |
| :--- | :--- | :--- |
| **合并段落 (Merge)** | `study_service.merge_paragraphs()` | **物理删除被合并段落的所有音频**：同步从磁盘删除 `p_first` 与 `p_second` 的 `_source.wav` 和 `_target.wav` 文件；清空段落数据中的 `audio` 状态字段；新合并段落作为全新未生成状态。 |
| **删除段落 (Delete)** | `study_service.delete_paragraph()` | **彻底清理该段音频**：物理删除该段落对应的 `_source.wav` 与 `_target.wav` 文件，避免产生孤儿音频文件。 |
| **拆分章节/拆分段落** | `shift_chapter` / `split_chapter` | 原段落文本被截断或拆解时，同步删除原段落旧音频，促使其按新段落文本重新计算生成。 |
| **删除文档/章节** | `delete_document` / `delete_chapter` | 递归级联删除对应的 `audio/{chapter_id}/` 整个目录。 |

### 3.3 重新生成（Regeneration）触发矩阵
系统界定以下 4 种明确触发重新生成的场景：

```
                              ┌───────────────────────────────┐
                              │      触发语音重新生成场景     │
                              └───────────────┬───────────────┘
                                              │
         ┌────────────────────┬───────────────┴───────────────┬────────────────────┐
         ▼                    ▼                               ▼                    ▼
【场景 1: 用户主动触发】  【场景 2: 段落内容编辑】        【场景 3: 文本 Hash 校验】 【场景 4: 磁盘文件缺失】
- 段落浮动面板点“重生成” - 用户在界面编辑原文 (edit)      - 请求播放时计算文本 MD5   - 元数据标记 completed
- Header 批量选“重新生成”- 用户修改译文或点击“重译”        与元数据记录 hash 不匹配   但物理 .wav 文件丢失
                         (分别使 source/target 失效)      (检测到内容漂移自动重制)   (自动自愈重新生成)
```

1. **用户主动触发重新生成**：
   - 用户在段落卡片 TTS 浮动面板中点击“🔄 重新生成原文”或“🔄 重新生成译文”；
   - 用户在 Header 点击批量 TTS 时，勾选了“覆盖重新生成”选项。
2. **段落内容发生变更（编辑 / 重译）**：
   - 用户编辑了原文内容（`api.editParagraph`）：`source_hash` 发生变化，原文音频标记为失效并自动重新生成；
   - 用户编辑了译文内容或点击了“重译”（`onRetranslate`）：`target_hash` 发生变化，译文音频标记为失效并自动重新生成。
3. **文本 Hash 校验不匹配（自动防漂移）**：
   - 前端或后端请求播放某段时，动态比对当前文本的 MD5 与音频元数据记录的 `hash`。若不一致（例如通过外部导入或脚本更新了文本），自动判定为过时，就地触发重新生成。
4. **磁盘物理文件缺失自愈**：
   - 即使元数据中标记为 `status: "completed"`，但底层物理音频文件不存在时，请求触发自愈重新生成。

---

## 4. 前端 UX 交互与播放体验设计 (Header 批量 + 段落悬浮面板)

### 4.1 Header 顶部批量 TTS 生成入口（6 大核心维度）
在阅读界面的 Header 章节操作区（与批量翻译按钮并列），新增 **“🎧 批量生成语音”** 菜单按钮：

```text
┌────────────────────────────────────────────────────────────────────────┐
│  第 2 章 / 共 10 章  《系统架构设计》         [🎧 批量生成语音 ▾] [翻译] │
└──────────────────────────────────────┬─────────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            │  本章范围 (Current Chapter)                         │
            │  ├─ 📄 本章 · 原文语音 (英语听力磨耳朵)              │
            │  ├─ 🇨🇳 本章 · 译文语音 (中文听书温习)                │
            │  └─ 🌐 本章 · 原文+译文语音 (全套双语)               │
            │  ─────────────────────────────────────────────────  │
            │  全篇范围 (Full Document)                           │
            │  ├─ 📚 全篇 · 原文语音                              │
            │  ├─ 🇨🇳 全篇 · 译文语音                              │
            │  └─ 🌐 全篇 · 原文+译文语音 (离线打包准备)           │
            └─────────────────────────────────────────────────────┘
```

#### 批量生成运行状态指示（Running Indicator）：
- 触发后在 Header 动态展示生成进度徽标：
  `🎧 正在生成语音: 本章双语 (14/28, 50%) ⏸️ 停止`
- 支持点击随时中止或暂停后台生成队列。

---

### 4.2 段落卡片级微交互：TTS 专属浮动操作面板（Floating Popover）
在段落卡片右下角的操作栏上，新增 **专属 TTS 图标按钮（🎧）**。
点击或悬浮即呼出精致的**浮动微面板（Popover Panel）**，集成“生成/重生成”与“手动点播”两大功能区：

```text
┌───────────────────────────────────────────────────────────────┐
│  🎧 段落语音伴读 (第 5 段)                                    │
│  状态: 原文 [已就绪]  │  译文 [未生成]                        │
├───────────────────────────────────────────────────────────────┤
│  ⚡ 生成与重生成                                              │
│  ├─ [ 🔄 重生成原文 ]   (当前: 已生成 4.2s)                   │
│  ├─ [ ⚡ 生成译文   ]   (当前: 未生成，点击合成)              │
│  └─ [ 🌐 一键生成双语 ]                                       │
├───────────────────────────────────────────────────────────────┤
│  ▶️ 手动点播控制                                              │
│  ├─ [ ▶ 播放原文 ]                                            │
│  ├─ [ ▶ 播放译文 ] (若未生成，自动一键“合成并播放”)           │
│  └─ [ ⏯ 顺序播放双语 ] (先播放原文 ➔ 停顿0.8s ➔ 播放译文)    │
└───────────────────────────────────────────────────────────────┘
```

---

### 4.3 自动顺次播放与智能视口跟随（Auto-Scroll Playing Indicator）
当用户从底部播放器或面板启动**“连续自动播放模式”**时：
1. **自动滚动呈现播放状态**：无需多余的弹窗遮挡阅读，系统通过 **平滑居中滚动 (`scrollIntoView({ behavior: 'smooth', block: 'center' })`)**，让正在播放的段落卡片始终保持在屏幕正中视觉焦点；
2. **段落声波与聚光灯效果**：
   - 正在发声的段落卡片亮起 **柔和主题发光外边框（`ring-2 ring-primary/60 bg-primary/5`）**；
   - 段落标题或右下角展示跳动的 **动态声波（Audio Wave Animation）**；
3. **用户手动接管与防抖机制**：
   - 若用户在播放过程中主动滑动鼠标或触控板查看其他内容，**自动暂停滚动 6 秒**；
   - 底部播放器显示“*已暂停自动跟踪，点击恢复居中*”，避免自动滚屏与用户的阅读手势互相争抢。

---

## 5. 分步实施与工程排期计划

### Phase 1: 后端核心引擎、依赖与单段合成闭环 (预计 1.5 天)
1. **依赖与规范**：
   - 确认 `packages/` 离线包齐备，`requirements.txt` 与 `pyproject.toml` 已登记 `sherpa-onnx` 与 `soundfile`；
   - 新建 `study/tts_engine.py`，实现单例 `OfflineTTSManager`，封装模型加载、预热与中英混读推理；
2. **存储与生命周期**：
   - 在 `study/service.py` 的 `merge_paragraphs`、`delete_paragraph` 中加入对应 `_source.wav` / `_target.wav` 的物理删除清理逻辑；
   - 实现文本 Hash 校验与自动失效重生成逻辑；
3. **API 接口**：
   - 新增单段生成接口 `POST /api/study/documents/{doc_id}/chapters/{chapter_id}/paragraphs/{para_id}/tts`；
   - 新增音频流式获取接口 `GET /api/study/documents/{doc_id}/audio/{chapter_id}/{para_id}/{target}`（支持 Range 206 断点请求）。

### Phase 2: 后端批量调度队列与多维度生成 (预计 1 天)
1. **异步任务队列**：
   - 基于 `asyncio.Queue` 实现单工作线程后台消费者（`max_workers = 1~2`），控制 CPU 负载；
   - 编写 `POST /api/study/documents/{doc_id}/tts/batch` 接口，支持 6 个维度范围（本章/全篇 + 原文/译文/双语）；
   - 提供批量任务状态查询与随时取消/停止接口。

### Phase 3: 前端交互、连续播放器与自动滚动 (预计 2 天)
1. **Header 批量操作**：
   - 在 `ReadingStage.tsx` 顶部操作区新增“批量生成语音”下拉菜单（6 维度）；
   - 增加批量生成进行中的动态进度胶囊标签；
2. **段落微交互**：
   - 段落卡片添加 TTS 浮动图标与 Popover 微面板（生成、重生成、播放原文/译文/双语）；
3. **连续播放与视口跟随**：
   - 封装底部吸底毛玻璃播放控制器 `ReadingAudioPlayer.tsx`；
   - 实现顺次自动播放引擎与平滑自动滚动居中（含用户手动滑动手势防抖拦截）。

### Phase 4: Windows 离线包验证与交付 (预计 0.5 天)
1. 验证在无网络 Windows 环境下通过 `packages/` 离线安装与运行自检；
2. 完善 `start.bat` 离线启动引导与自检。
