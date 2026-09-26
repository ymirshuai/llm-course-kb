# -*- coding: utf-8 -*-
"""样本转写质量评估：用 400 条热词表统计命中/错词。"""
import os, sys, json, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "转写", "样本")
HOT = json.load(open(os.path.join(ROOT, "课件对齐", "热词表.json"), encoding="utf-8"))
names = [t["text"] if isinstance(t, dict) else t for t in HOT]

def count_hits(text, name):
    if re.search(r"[A-Za-z]", name):
        return len(re.findall(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])",
                              text, flags=re.IGNORECASE))
    return text.count(name)

print(f"热词表共 {len(names)} 条\n")
for f in sorted(glob.glob(os.path.join(RAW, "*.result.json"))):
    d = json.load(open(f, encoding="utf-8"))
    text = d["transcripts"][0]["text"]
    hits = [(n, c) for n in names if (c := count_hits(text, n)) > 0]
    hits.sort(key=lambda x: -x[1])
    miss_kw = [n for n in ("LoRA", "QLoRA", "vLLM", "RAG", "LangChain", "Transformer", "Embedding")
               if count_hits(text, n) == 0]
    print(f"=== {os.path.basename(f).replace('.result.json','')} ===")
    print(f"  热词命中 {len(hits)}/{len(names)}  总出现 {sum(c for _, c in hits)} 次")
    print(f"  Top12: {', '.join(f'{n}×{c}' for n, c in hits[:12])}")
    print(f"  重点词未命中: {', '.join(miss_kw) if miss_kw else '无'}")
    print()
