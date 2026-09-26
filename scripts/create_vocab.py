# -*- coding: utf-8 -*-
"""从术语表.json 清洗出热词表并创建百炼 vocabulary，返回 vocabulary_id。"""
import os, re, json, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key

OUT_DIR = os.path.join(ROOT, "课件对齐")

JUNK_CHARS = set("(){}[]\"'`$;|\\=<>#&*!?~^")

# 课程强相关、PDF 里未必出现但讲师一定会说的术语（人工补充）
CURATED = [
    "QLoRA", "vLLM", "DPO", "PPO", "RLHF", "SFT", "PEFT", "TRL", "GGUF",
    "Ollama", "llama.cpp", "DeepSpeed", "FlashAttention", "BM25", "Faiss",
    "Milvus", "Chroma", "Rerank", "GraphRAG", "HyDE", "ColBERT", "BGE", "M3E",
    "Gradio", "Streamlit", "FastAPI", "uvicorn", "RAGAS", "Dify", "LlamaIndex",
    "HuggingFace", "Tokenizer", "Embedding", "Chunking", "Function Calling",
    "Agent", "LangChain", "LCEL", "PyTorch", "TensorFlow", "YOLO", "Unet",
    "Stable Diffusion", "ControlNet", "ChatGLM", "Qwen", "DeepSeek", "Llama",
    "Mistral", "Cursor", "Copilot", "NotebookLM", "Prompt", "RAG", "LoRA",
]

def clean():
    data = json.load(open(os.path.join(OUT_DIR, "术语表.json"), encoding="utf-8"))
    cands = {}
    for t in data["terms"]:
        tok, freq = t["term"], t["freq"]
        if any(c in JUNK_CHARS for c in tok):
            continue
        if re.search(r"\d", tok) and len(tok) < 5:   # step1 之类
            continue
        if len(tok) < 2 or len(tok) > 25:
            continue
        cands[tok.lower()] = (tok, freq)
    # 去子串碎片：若 A 是 B 的子串且 B 更长，删 A（如 euralflow ⊂ neuralflow）
    keys = sorted(cands, key=len, reverse=True)
    drop = set()
    for i, a in enumerate(keys):
        for b in keys:
            if a != b and a in b and len(cands[b][0]) > len(cands[a][0]):
                drop.add(a)
                break
    for d in drop:
        cands.pop(d, None)
    # 过滤低频纯小写
    out = []
    for low, (tok, freq) in cands.items():
        has_upper = any(c.isupper() for c in tok)
        if freq >= 3 or (has_upper and freq >= 2):
            out.append((tok, freq))
    out.sort(key=lambda x: -x[1])
    return out

def main():
    ranked = clean()
    # 合并人工补充（放最前，权重高）
    merged, seen = [], set()
    for tok in CURATED:
        if tok.lower() not in seen:
            seen.add(tok.lower())
            merged.append((tok, 99))
    for tok, freq in ranked:
        if tok.lower() not in seen and len(merged) < 400:
            seen.add(tok.lower())
            merged.append((tok, freq))

    vocabulary = []
    for tok, freq in merged:
        w = 4 if freq >= 50 else (3 if freq >= 10 else 2)
        vocabulary.append({"text": tok, "weight": w, "lang": "zh"})

    json.dump(vocabulary, open(os.path.join(OUT_DIR, "热词表.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"热词表 {len(vocabulary)} 条已写入（前 20：）")
    for v in vocabulary[:20]:
        print(f"  w{v['weight']}  {v['text']}")

    key, src = load_key()
    print(f"\n密钥来源: {src}")
    from dashscope.audio.asr import VocabularyService
    svc = VocabularyService(api_key=key)
    try:
        vocab_id = svc.create_vocabulary(
            target_model="paraformer-v2",
            prefix="llmcourse",
            vocabulary=vocabulary,
        )
        print(f"vocabulary_id = {vocab_id}")
        json.dump({"vocabulary_id": vocab_id, "count": len(vocabulary)},
                  open(os.path.join(OUT_DIR, "vocabulary_id.json"), "w",
                       encoding="utf-8"))
    except Exception as e:
        print(f"创建热词失败: {e}")
        print("→ 将降级为不带热词的样本对比（两边都不带，保持公平）")

if __name__ == "__main__":
    main()
