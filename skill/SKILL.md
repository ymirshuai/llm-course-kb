---
name: llm-course-kb
description: 查询"知学堂 LLM 课程"知识库（76 节课 / 190+ 小时逐字稿，含 2026 主课 28 节 + 算法/原理/demo 赠课 48 节）。当对话涉及 AI/LLM 原理、技术方案、选型对比，或用户想引用课程原话时使用。提供混合检索（语义+关键词）返回带课名和时间戳的课程原文。
read_when:
  - 用户问题涉及 AI/LLM/RAG/Agent/微调/向量库/Transformer 等原理或方案
  - 用户说"课程里怎么讲的""老师说过""查一下课程"
  - 做 AI 技术选型、方案对比、设计评审需要依据时
---

# LLM 课程知识库查询

> **使用说明**：本 skill 是用户级触发器，安装到自己 AI 助手的 skills 目录（如 WorkBuddy 的 `~/.workbuddy/skills/llm-course-kb/`）后，对话涉及 AI/LLM 方案时助手会自动查课程知识库。文中路径为作者本机示例，**请按你的仓库 clone 位置修改**；数据补充包（qdrant.exe + storage + 逐字稿）需先解压到仓库根目录。

## 知识库在哪

- 根目录：`G:\知学堂-LLM学习\课程转义\`
- 索引：`知识库/INDEX.md`（76 课总览：课名/时长/高频术语）
- 向量库：Qdrant `http://localhost:6333`（course_subs 20151 子块 + course_outline 2862 大纲节点）
- 原始逐字稿：`知识库/逐字稿/<课名>.corrected.json`（句级时间戳）
- 切块大纲：`知识库/切块/<课名>.chunks.json`

## 查询优先级（按序尝试，前一步不可用才走下一步）

1. **MCP 工具**（最优先）：如果当前会话有 `course-kb` MCP server 的工具（`search_course_notes` / `get_lesson_outline` / `get_segment`），直接用。
2. **检查 Qdrant 是否在跑**：`curl -s --max-time 3 http://localhost:6333/collections`。
   - 没响应 → 后台启动：`cd "G:/知学堂-LLM学习/课程转义/tools/qdrant" && ./qdrant.exe`（run_in_background），等 3 秒重试。
   - 还不行 → 跳到第 4 步文件直读。
3. **CLI 兜底**：`"G:/知学堂-LLM学习/课程转义/.venv/Scripts/python.exe" "G:/知学堂-LLM学习/课程转义/scripts/search.py" "问题" 6`（需要 DASHSCOPE_API_KEY 环境 key 做 embedding）。
4. **文件直读兜底**：Read `知识库/INDEX.md` 定位课名 → Read 对课的 `chunks.json`（outline 有时间锚点和术语）→ 按时间区间 Read `corrected.json` 取原话。

## 引用规范

- 回答中引用课程内容时，**必须带出处**：课名 + 时间点（如 `算法课5 2:07`），方便用户回跳视频。
- 检索结果只取相关段落原文，不要整段照搬；先答结论再附课程原话。
- 课程只覆盖到 2026-10 前的 LLM 技术；知识库里没有的新东西要明说"课程未涉及"，不要冒充课程内容。

## 维护

- 新增课程视频后：切段（extract_all_audio.py）→ 转写（transcribe_parallel.py）→ 纠错+切块+入库（pipeline_all.py）→ 重建索引（make_index.py）。全脚本在 `scripts/`，支持断点续传。
- Qdrant 数据目录在 `tools/qdrant/storage/`，重启机器后需手动拉起 qdrant.exe。
