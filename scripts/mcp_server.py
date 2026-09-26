# -*- coding: utf-8 -*-
"""课程知识库 MCP server (stdio)。
工具:
  search_course_notes(query, top_k=6)  混合检索(dense+BM25 RRF)，返回命中片段与相关章节
  get_lesson_outline(lesson)           某课带时间锚点的大纲
  get_segment(lesson, begin_sec, end_sec)  取某课时间区间的逐字稿原文
依赖: 项目 venv 的 python 运行本文件。
"""
import os, sys, json, math, urllib.request
from collections import Counter

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
from _key import load_key

import jieba
from qdrant_client import QdrantClient, models
from mcp.server.fastmcp import FastMCP

KEY, _ = load_key()
DIM = 1024
client = QdrantClient("http://localhost:6333", timeout=60)
mcp = FastMCP("course-kb")

def _load_vocab(suffix):
    p = os.path.join(ROOT, "索引", f"bm25_vocab_{suffix}.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))

VOCAB = {"course_subs": _load_vocab("subs"), "course_outline": _load_vocab("outline")}

def tokenize(text):
    return [t for t in jieba.lcut(text.lower()) if t.strip() and t not in "，。？！、；：（）"]

def embed_one(text):
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        data=json.dumps({"model": "text-embedding-v4", "input": [text],
                         "dimensions": DIM, "encoding_format": "float"}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    return r["data"][0]["embedding"]

def sparse_of(text, vocab_idf):
    if not vocab_idf:
        return models.SparseVector(indices=[0], values=[0.0])
    vocab, idf = vocab_idf["vocab"], vocab_idf["idf"]
    tc = {}
    for t in tokenize(text):
        if t in vocab:
            tc[t] = tc.get(t, 0) + 1
    if not tc:
        return models.SparseVector(indices=[0], values=[0.0])
    return models.SparseVector(indices=[vocab[t] for t in tc],
                               values=[idf[t] * (1 + math.log(c)) for t, c in tc.items()])

def fmt_sec(s):
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}"

@mcp.tool()
def search_course_notes(query: str, top_k: int = 6) -> str:
    """在 71 节 LLM 课程逐字稿知识库中做混合检索。返回相关章节(大纲层)与命中片段(原文+课名+起止时间戳)。"""
    qv = embed_one(query)
    ol = client.query_points("course_outline", query=qv, using="dense", limit=4,
                             with_payload=True).points
    subs = client.query_points("course_subs", prefetch=[
        models.Prefetch(query=qv, using="dense", limit=25),
        models.Prefetch(query=sparse_of(query, VOCAB["course_subs"]), using="bm25", limit=25),
    ], query=models.FusionQuery(fusion=models.Fusion.RRF), limit=top_k,
        with_payload=True).points
    out = {"相关章节": [
        {"课名": p.payload["lesson"], "章节": p.payload["node_title"],
         "时间": f"{fmt_sec(p.payload['begin_sec'])}-{fmt_sec(p.payload['end_sec'])}",
         "术语": p.payload.get("terms", [])[:6]} for p in ol],
        "命中片段": [
        {"课名": p.payload["lesson"], "章节": p.payload.get("node_title", ""),
         "起止秒": [p.payload["begin_sec"], p.payload["end_sec"]],
         "原文": p.payload["text"]} for p in subs]}
    return json.dumps(out, ensure_ascii=False, indent=1)

@mcp.tool()
def get_lesson_outline(lesson: str) -> str:
    """获取某节课的带时间锚点大纲（章节标题+术语+起止秒）。lesson 为课名，如 'L06-AI编程-从入门到精通'。可先用 search_course_notes 拿到课名。"""
    p = os.path.join(ROOT, "知识库", "切块", f"{lesson}.chunks.json")
    if not os.path.exists(p):
        avail = sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(ROOT, "知识库", "切块")))
        return json.dumps({"error": "课名不存在", "可选": avail}, ensure_ascii=False)
    d = json.load(open(p, encoding="utf-8"))
    return json.dumps({"课名": lesson, "标题": d["meta"]["title"],
                       "时长秒": d["meta"]["duration_sec"],
                       "大纲": [{"章节": n["title"], "起止秒": [n["begin_sec"], n["end_sec"]],
                                 "术语": n.get("terms", [])} for n in d["outline"]]},
                      ensure_ascii=False, indent=1)

@mcp.tool()
def get_segment(lesson: str, begin_sec: float, end_sec: float) -> str:
    """取某课时间区间的逐字稿原文（句级）。用于根据 search/outline 得到的时间戳回读原话。"""
    p = os.path.join(ROOT, "知识库", "逐字稿", f"{lesson}.corrected.json")
    if not os.path.exists(p):
        return json.dumps({"error": "逐字稿不存在", "lesson": lesson}, ensure_ascii=False)
    d = json.load(open(p, encoding="utf-8"))
    sents = [s for s in d["sentences"] if s["end"] > begin_sec and s["begin"] < end_sec]
    return json.dumps({"课名": lesson, "区间": [begin_sec, end_sec],
                       "句子数": len(sents),
                       "原文": "".join(s["text"] for s in sents)},
                      ensure_ascii=False, indent=1)

if __name__ == "__main__":
    mcp.run()
