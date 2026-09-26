# LLM 课程知识库（Course KB）

把 181.5 小时的 LLM 在线课程（71 节：主课 + 算法/原理/demo 赠课）转写、纠错、结构化，
建成一个 **AI 助手可直接检索的课程知识库**，并以 **MCP server** 的形式暴露给 Claude Code / WorkBuddy 等助手。

> 仓库只包含**管线代码与元数据**。视频、音频、逐字稿等课程内容**不入库**（版权归课程方），
> 请自行用本仓库的管线从你合法获得的课程录像生成。

## 管线全景

```
课程视频 (mp4)
   │  ① extract_all_audio.py    ffmpeg silencedetect 找静音点 → 切 10-15 分钟段 → s16 flac
   ▼
音频切段 (~739 段)
   │  ② transcribe_parallel.py  阿里云百炼 fun-asr（6 并发/断点续传/词级置信度）
   ▼
逐字稿 JSON (句级时间戳)
   │  ③ correct_terms.py        DeepSeek 逐句纠错（术语表来自课件 PDF 自动抽取）
   │  ④ chunk_lesson.py         三层切块：大纲节点 / 子块 200-400字 / 父块 1500-3000字
   │  ⑤ embed_ingest.py         Qwen text-embedding-v4 + jieba BM25 → Qdrant
   ▼
Qdrant (dense + sparse 双路)
   │  ⑥ search.py / mcp_server.py   混合检索（RRF 融合）
   ▼
AI 助手 / 命令行查询
```

实际运行数据（供参考）：739 段转写约 1 小时（6 并发）、纠错+切块+入库 71 课约 5 小时、
转写费用约 ¥1/小时语音（静音不计费）。

## 目录结构

```
├── scripts/              # 全部管线脚本（见下）
├── 索引/                  # 课程大纲、视频↔课号映射、BM25 词表等元数据
├── 知识库/INDEX.md        # 71 课总览（不含在仓库中时可用 make_index.py 生成）
└── 方案-课程转写与知识库.md
```

| 脚本 | 作用 |
|---|---|
| `make_manifest.py` | 解析视频文件名 UUIDv1 内嵌时间戳，与课件 mtime 对齐生成映射清单 |
| `extract_terms.py` | PyMuPDF 抽课件术语 + LLM 清洗 → 热词表 |
| `extract_all_audio.py` | 静音点切段（断点续传） |
| `transcribe_parallel.py` / `transcribe_samples.py` | fun-asr 并发转写（断点续传、无语音段跳过） |
| `correct_terms.py` | DeepSeek 逐句术语纠错（单汉字禁替换 + ASCII 词边界两道护栏） |
| `chunk_lesson.py` | LLM 话题边界三层切块 |
| `embed_ingest.py` | 向量化入 Qdrant |
| `rebuild_sparse.py` | 全局 BM25 词表重建（修每课词表索引不一致问题） |
| `search.py` | 命令行混合检索 |
| `mcp_server.py` | MCP server（stdio）：`search_course_notes` / `get_lesson_outline` / `get_segment` |
| `make_index.py` | 生成知识库 INDEX.md |
| `pipeline_all.py` | 71 课批处理驱动（纠错→切块→入库，断点续传） |

## 快速开始

### 0. 前置

- Python 3.10+，ffmpeg（含 silencedetect）
- 阿里云百炼 API Key（[bailian.console.aliyun.com](https://bailian.console.aliyun.com)，用 fun-asr / text-embedding-v4）
- DeepSeek API Key（纠错用；也可换成任何 OpenAI 兼容接口）

```bash
python -m venv .venv
.venv/Scripts/pip install requests dashscope jieba pymupdf tqdm qdrant-client "mcp[cli]"
```

### 1. 密钥（三选一）

```bash
# 方式 A：环境变量
set DASHSCOPE_API_KEY=sk-xxx        # DEEPSEEK_API_KEY 同理

# 方式 B：项目根建 .secrets/Key.json（已被 .gitignore 排除）
# {"DASHSCOPE_API_KEY": "sk-xxx", "DEEPSEEK_API_KEY": "sk-xxx"}

# 方式 C：Windows 注册表环境变量（脚本会自动读）
```

### 2. 启动 Qdrant（无需 Docker）

从 [Qdrant Releases](https://github.com/qdrant/qdrant/releases) 下载对应平台二进制，
放到 `tools/qdrant/qdrant.exe` 并运行（默认监听 `:6333`）。
Windows 直连超时可加 gh-proxy 镜像前缀下载。

### 3. 跑管线

```bash
.venv/Scripts/python scripts/extract_all_audio.py     # ① 切段
.venv/Scripts/python scripts/transcribe_parallel.py   # ② 转写（百炼，按量计费）
.venv/Scripts/python scripts/pipeline_all.py          # ③④⑤ 纠错+切块+入库（71 课自动批处理）
.venv/Scripts/python scripts/rebuild_sparse.py        # 重建全局 BM25 词表
.venv/Scripts/python scripts/make_index.py            # 生成 INDEX.md
```

### 4. 检索

```bash
# 命令行
.venv/Scripts/python scripts/search.py "LSTM 遗忘门的作用" 4

# 或接入 MCP 客户端（Claude Code / WorkBuddy 的 mcp.json）：
{
  "mcpServers": {
    "course-kb": {
      "type": "stdio",
      "command": "<项目路径>/.venv/Scripts/python.exe",
      "args": ["<项目路径>/scripts/mcp_server.py"]
    }
  }
}
```

三个 MCP 工具：
- `search_course_notes(query, top_k)` — 混合检索，返回命中原文 + 课名 + 时间戳
- `get_lesson_outline(lesson)` — 某课带时间锚点的章节大纲
- `get_segment(lesson, begin_sec, end_sec)` — 按时间区间回读逐字稿原话

## 检索设计要点

- **两层双路**：语义检索跑在大纲层（抗口语稀释），关键词 BM25 + 语义跑在子块层（抓报错信息、API 名等细节），RRF 融合后取父块原文。
- **BM25 词表必须全局一致**：入库与查询两侧共用同一份词表映射（`rebuild_sparse.py` 持久化到 `索引/bm25_vocab_*.json`）。每课独立建词表会让稀疏向量完全失配——这是本项目实际踩过的坑。
- **术语纠错两道护栏**：单汉字禁止全局替换（防"输入"→"输Rule"）、ASCII 词用词边界（防 ai→AI 污染 training）。
- **热词表的教训**：paraformer-v2 带/不带 400 条热词输出几乎相同——声学层错词救不动，术语准确性靠转写后 LLM 纠错兜底。

## License 与声明

- 管线代码：MIT
- 课程视频、音频、逐字稿内容版权归原作者所有，本仓库与其衍生文件均不得用于商业用途。
