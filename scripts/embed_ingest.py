# -*- coding: utf-8 -*-
"""把切块结果入库 Qdrant（dense: Qwen text-embedding-v4 + sparse: jieba BM25 权重）。
集合:
- course_subs: 子块（vector + sparse + payload），检索主力
- course_outline: 大纲节点（vector + payload），语义层
用法: python embed_ingest.py <课目录名> [...]
"""
import os, sys, json, glob, math, time, urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key
import jieba
from qdrant_client import QdrantClient, models

KEY, SRC = load_key()
EMB_MODEL = "text-embedding-v4"
DIM = 1024

def embed_texts(texts, batch=10):
    """DashScope OpenAI 兼容 embeddings。返回 list[list[float]]"""
    out = []
    for i in range(0, len(texts), batch):
        part = texts[i:i + batch]
        req = urllib.request.Request(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            data=json.dumps({"model": EMB_MODEL, "input": part,
                             "dimensions": DIM, "encoding_format": "float"}).encode(),
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=120))
        data = sorted(r["data"], key=lambda x: x["index"])
        out.extend([d["embedding"] for d in data])
        if i + batch < len(texts):
            time.sleep(0.5)
    return out

def build_sparse(corpus_tokens):
    """BM25 风格 idf 稀疏向量"""
    df = Counter()
    for toks in corpus_tokens:
        df.update(set(toks))
    N = len(corpus_tokens)
    idf = {t: math.log(1 + (N - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    vocab = {t: i for i, t in enumerate(sorted(df))}
    vecs = []
    for toks in corpus_tokens:
        tc = Counter(t for t in toks if t in vocab)
        vecs.append(models.SparseVector(
            indices=[vocab[t] for t in tc],
            values=[round(idf[t] * (1 + math.log(c)), 4) for t, c in tc.items()]))
    return vecs, vocab, idf

def tokenize(text):
    return [t for t in jieba.lcut(text.lower()) if t.strip() and t not in "，。？！、；：（）"]

def ensure_collections(client):
    if not client.collection_exists("course_subs"):
        client.create_collection(
            "course_subs",
            vectors_config={"dense": models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
            sparse_vectors_config={"bm25": models.SparseVectorParams()})
    if not client.collection_exists("course_outline"):
        client.create_collection(
            "course_outline",
            vectors_config={"dense": models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
            sparse_vectors_config={"bm25": models.SparseVectorParams()})

def ingest_lesson(client, lesson, vocab_ref):
    cf = os.path.join(ROOT, "知识库", "切块", f"{lesson}.chunks.json")
    d = json.load(open(cf, encoding="utf-8"))
    meta = d["meta"]
    subs = d["sub_chunks"]
    # 该课已有则先删（重跑幂等）
    client.delete("course_subs", points_selector=models.FilterSelector(
        filter=models.Filter(must=[models.FieldCondition(key="lesson",
            match=models.MatchValue(value=lesson))])))
    client.delete("course_outline", points_selector=models.FilterSelector(
        filter=models.Filter(must=[models.FieldCondition(key="lesson",
            match=models.MatchValue(value=lesson))])))

    toks = [tokenize(s["text"]) for s in subs]
    dense = embed_texts([s["text"][:2000] for s in subs])
    sparse_all, _, _ = build_sparse(toks)
    points = []
    for s, dv, sv in zip(subs, dense, sparse_all):
        import uuid
        pid = uuid.uuid5(uuid.NAMESPACE_URL, f"{lesson}:{s['block_id']}").hex
        points.append(models.PointStruct(
            id=pid, vector={"dense": dv, "bm25": sv},
            payload={"lesson": lesson, "title": meta["title"], "node_title": s.get("node_title", ""),
                     "begin_sec": s["begin_sec"], "end_sec": s["end_sec"],
                     "n_chars": s["n_chars"], "text": s["text"]}))
    client.upsert("course_subs", points=points, wait=True)

    ol = d["outline"]
    otexts = [f"{n['title']} " + " ".join(n.get("terms", [])) for n in ol]
    odense = embed_texts(otexts)
    osparse, _, _ = build_sparse([tokenize(t) for t in otexts])
    opoints = []
    for n, dv, sv in zip(ol, odense, osparse):
        import uuid
        oid = uuid.uuid5(uuid.NAMESPACE_URL, f"{lesson}:ol:{n['start_sent']}").hex
        opoints.append(models.PointStruct(
            id=oid, vector={"dense": dv, "bm25": sv},
            payload={"lesson": lesson, "title": meta["title"], "node_title": n["title"],
                     "terms": n.get("terms", []), "begin_sec": n["begin_sec"], "end_sec": n["end_sec"]}))
    client.upsert("course_outline", points=opoints, wait=True)
    print(f"入库 {lesson}: {len(points)} 子块 + {len(opoints)} 大纲节点")

if __name__ == "__main__":
    client = QdrantClient("http://localhost:6333", timeout=60)
    ensure_collections(client)
    vocab_ref = {"vocab": None, "corpus": []}
    for lesson in sys.argv[1:]:
        ingest_lesson(client, lesson, vocab_ref)
    for c in ("course_subs", "course_outline"):
        print(c, client.count(c, exact=True).count, "条")
