# -*- coding: utf-8 -*-
"""生成知识库顶层 INDEX.md：课名/时长/大纲节点数/关键术语/文件路径。"""
import os, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = os.path.join(ROOT, "知识库", "切块")
OUT = os.path.join(ROOT, "知识库", "INDEX.md")

mf = json.load(open(os.path.join(ROOT, "索引", "manifest.json"), encoding="utf-8"))
info = {r["file"]: r for r in mf["items"]}

# manifest 与切块目录名的 lesson_no 映射
lesson_dirs = sorted(glob.glob(os.path.join(CH, "*.chunks.json")))
rows = []
for p in lesson_dirs:
    lesson = os.path.basename(p).replace(".chunks.json", "")
    d = json.load(open(p, encoding="utf-8"))
    meta = d.get("meta", {})
    ol = d.get("outline", [])
    terms = {}
    for n in ol:
        for t in n.get("terms", []):
            terms[t] = terms.get(t, 0) + 1
    top_terms = sorted(terms, key=lambda t: -terms[t])[:10]
    dur = meta.get("duration_sec", 0)
    rows.append({
        "lesson": lesson,
        "title": meta.get("title", lesson),
        "dur": dur,
        "nodes": len(ol),
        "subs": len(d.get("sub_chunks", [])),
        "parents": len(d.get("parent_chunks", [])),
        "terms": top_terms,
    })

def fmt_h(sec):
    return f"{int(sec)//3600}h{int(sec)%3600//60:02d}m" if sec else "?"

lines = [
    "# 课程知识库 INDEX",
    "",
    f"- 课程总数：{len(rows)}（主课 2026 期 23 + 赠课 48）",
    f"- 生成时间：{__import__('datetime').datetime.now():%Y-%m-%d %H:%M}",
    "- 用法：先读本表定位课名 → 再查 `知识库/切块/<课名>.chunks.json` 的 outline（带时间锚点大纲）→ 最后按时间区间取 `知识库/逐字稿/<课名>.corrected.json` 原文。也可用 `scripts/search.py \"问题\"` 直接混合检索。",
    "",
    "| # | 课名 | 时长 | 大纲节点 | 子块 | 高频术语 |",
    "|---|---|---|---|---|---|",
]
for i, r in enumerate(rows, 1):
    lines.append(f"| {i} | **{r['title']}** | {fmt_h(r['dur'])} | {r['nodes']} | {r['subs']} | {('、'.join(r['terms'][:6])) or '—'} |")
lines.append("")
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"INDEX.md 写入完成：{len(rows)} 课")
for r in rows[:5]:
    print(" ", r["title"], fmt_h(r["dur"]), f"{r['nodes']}节点 {r['subs']}子块")
