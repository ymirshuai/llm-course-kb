# -*- coding: utf-8 -*-
"""修复 BM25 稀疏向量：入库时词表是每课独立的，查询侧对不上。
方案：scroll 回读全部点（dense 向量原样保留），按全局词表重算 bm25，原 id upsert 回写。
词表持久化到 索引/bm25_vocab.json 供查询侧使用。全程零 API 成本。
"""
import os, sys, json, math
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jieba
from qdrant_client import QdrantClient, models

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
client = QdrantClient("http://localhost:6333", timeout=120)

def tokenize(text):
    return [t for t in jieba.lcut(text.lower()) if t.strip() and t not in "，。？！、；：（）"]

def scroll_all(coll):
    pts, offset = [], None
    while True:
        batch, offset = client.scroll(coll, limit=256, offset=offset,
                                      with_vectors=True, with_payload=True)
        pts.extend(batch)
        if offset is None:
            return pts

def rebuild(coll, token_lists):
    """token_lists: 与 points 顺序对应的分词结果列表"""
    df = Counter()
    for toks in token_lists:
        df.update(set(toks))
    N = len(token_lists)
    idf = {t: math.log(1 + (N - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    vocab = {t: i for i, t in enumerate(sorted(df))}
    return vocab, idf

def sparse_vec(text, vocab, idf):
    tc = Counter(t for t in tokenize(text) if t in vocab)
    if not tc:
        return models.SparseVector(indices=[0], values=[0.0])
    return models.SparseVector(
        indices=[vocab[t] for t in tc],
        values=[round(idf[t] * (1 + math.log(c)), 4) for t, c in tc.items()])

for coll, text_of in [("course_subs", lambda p: p.payload["text"]),
                      ("course_outline", lambda p: p.payload["node_title"] + " " + " ".join(p.payload.get("terms", [])))]:
    print(f"=== {coll} ===")
    pts = scroll_all(coll)
    print(f"  回读 {len(pts)} 点")
    toks_all = [tokenize(text_of(p)) for p in pts]
    vocab, idf = rebuild(coll, toks_all)
    print(f"  全局词表 {len(vocab)} 词")
    save = {"vocab": vocab, "idf": idf}
    suffix = "subs" if "subs" in coll else "outline"
    json.dump(save, open(os.path.join(ROOT, "索引", f"bm25_vocab_{suffix}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    # 分批回写
    B = 200
    for i in range(0, len(pts), B):
        batch = pts[i:i + B]
        ups = [models.PointStruct(id=p.id, vector={"dense": p.vector["dense"],
                                                   "bm25": sparse_vec(text_of(p), vocab, idf)},
                                  payload=p.payload) for p in batch]
        client.upsert(coll, points=ups, wait=True)
        print(f"  回写 {min(i + B, len(pts))}/{len(pts)}")
print("DONE")
