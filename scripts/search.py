# -*- coding: utf-8 -*-
"""知识库混合检索: dense(Qwen embedding) + sparse(jieba BM25) -> Qdrant RRF 融合。
用法: python search.py "问题" [top_k]
输出: 命中的大纲节点 + 子块原文(带课名/时间戳), 父块路径提示
"""
import os, sys, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key
import jieba
from qdrant_client import QdrantClient, models

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY, _ = load_key()
DIM = 1024
client = QdrantClient("http://localhost:6333", timeout=60)

def embed_one(text):
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        data=json.dumps({"model": "text-embedding-v4", "input": [text],
                         "dimensions": DIM, "encoding_format": "float"}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    return r["data"][0]["embedding"]

def tokenize(text):
    return [t for t in jieba.lcut(text.lower()) if t.strip() and t not in "，。？！、；：（）"]

def _load_vocab(suffix):
    p = os.path.join(ROOT, "索引", f"bm25_vocab_{suffix}.json")
    if not os.path.exists(p):
        return None, None
    d = json.load(open(p, encoding="utf-8"))
    return d["vocab"], d["idf"]

VOCAB_SUBS = _load_vocab("subs")
VOCAB_OL = _load_vocab("outline")

def sparse_of(text, vocab_idf):
    if not vocab_idf:
        return models.SparseVector(indices=[0], values=[0.0])
    vocab, idf = vocab_idf
    tc = {}
    for t in tokenize(text):
        if t in vocab:
            tc[t] = tc.get(t, 0) + 1
    if not tc:
        return models.SparseVector(indices=[0], values=[0.0])
    import math
    return models.SparseVector(indices=[vocab[t] for t in tc],
                               values=[idf[t] * (1 + math.log(c)) for t, c in tc.items()])

def search(query, top_k=6):
    qv = embed_one(query)
    # 大纲层(语义) + 子块层(混合)
    ol = client.query_points("course_outline", query=qv, using="dense", limit=4,
                             with_payload=True).points
    subs = client.query_points("course_subs", prefetch=[
        models.Prefetch(query=qv, using="dense", limit=25),
        models.Prefetch(query=sparse_of(query, VOCAB_SUBS), using="bm25", limit=25),
    ], query=models.FusionQuery(fusion=models.Fusion.RRF), limit=top_k,
        with_payload=True).points
    return ol, subs

def fmt_sec(s):
    return f"{int(s//3600)}:{int(s%3600//60):02d}"

if __name__ == "__main__":
    q = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    ol, subs = search(q, k)
    print("=" * 70)
    print(f"问题: {q}")
    print("\n--- 相关章节(大纲层) ---")
    for p in ol:
        pl = p.payload
        print(f"  [{fmt_sec(pl['begin_sec'])}-{fmt_sec(pl['end_sec'])}] {pl['lesson']} | {pl['node_title']}  术语:{','.join(pl.get('terms', [])[:4])}")
    print("\n--- 命中片段(子块, RRF融合) ---")
    for p in subs:
        pl = p.payload
        print(f"\n  ▶ [{fmt_sec(pl['begin_sec'])}-{fmt_sec(pl['end_sec'])}] {pl['lesson']} · {pl['node_title']}")
        print(f"    {pl['text'][:220]}…")
