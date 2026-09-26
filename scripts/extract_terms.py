# -*- coding: utf-8 -*-
"""从课件 PDF + 名词记录.txt 抽候选术语，产出 课件对齐/术语表.json。
过滤规则：只取每课目录顶层的授课 PDF（1-*.pdf / 课号-*.pdf），排除一切 site-packages/.venv。
"""
import os, re, json, glob, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(ROOT, "..", "课件")
OUT_DIR = os.path.join(ROOT, "课件对齐")

BAD_DIR = ("site-packages", ".venv", "node_modules", ".git", "__pycache__")

def collect_pdfs():
    """收集真实授课 PDF（避开 vendored 内容）。"""
    pdfs = []
    for root, dirs, files in os.walk(CW):
        if any(b in root for b in BAD_DIR):
            dirs[:] = []
            continue
        for f in files:
            if not f.lower().endswith(".pdf"):
                continue
            rel = os.path.relpath(os.path.join(root, f), CW)
            # 授课 PDF：目录顶层（深度<=1）的 1-xxx.pdf 或 根目录散装 PDF
            depth = rel.count(os.sep)
            if depth <= 1:
                pdfs.append((rel, os.path.join(root, f)))
    return sorted(pdfs)

def extract_text(path, max_pages=None):
    try:
        import pymupdf
        doc = pymupdf.open(path)
        pages = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        txt = []
        for i in range(pages):
            txt.append(doc[i].get_text())
        doc.close()
        return "\n".join(txt)
    except Exception as e:
        print(f"  [warn] 无法解析 {os.path.basename(path)}: {e}")
        return ""

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+(\-/@_\.]{1,40}[A-Za-z0-9+\)]")
NOISE = {"the", "and", "for", "with", "from", "this", "that", "www", "http", "https",
         "com", "cn", "org", "pdf", "png", "jpg", "import", "from", "def", "class",
         "return", "self", "print", "true", "false", "none", "int", "float", "str",
         "list", "dict", "len", "range", "input", "output", "step", "case", "new",
         "api", "ai", "llm", "it", "of", "in", "on", "to", "is", "as", "by", "we",
         "ok", "no", "yes", "vs", "etc", "eg", "ie"}

def looks_term(tok):
    if len(tok) < 2:
        return False
    low = tok.lower()
    if low in NOISE:
        return False
    letters = sum(c.isalpha() for c in tok)
    if letters < 2:
        return False
    if re.fullmatch(r"[0-9\.\-]+", tok):
        return False
    # 纯小写常见单词过滤：保留驼峰/全大写/带符号（vLLM/LoRA/RAG）
    if tok.islower() and len(tok) <= 4:
        return False
    return True

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pdfs = collect_pdfs()
    print(f"收集到授课 PDF {len(pdfs)} 份：")
    freq = collections.Counter()
    src = collections.defaultdict(set)
    for rel, path in pdfs:
        text = extract_text(path)
        for tok in TOKEN_RE.findall(text):
            t = tok.strip("._-")
            if looks_term(t):
                key = t.lower()
                freq[key] += 1
                src[key].add(rel.split(os.sep)[0])
        print(f"  {rel}: {len(text)} 字符")

    # 名词记录.txt 作为种子
    seeds = []
    seed_file = os.path.join(CW, "名词记录.txt")
    if os.path.exists(seed_file):
        for line in open(seed_file, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line and re.search(r"[A-Za-z]", line):
                seeds.append(line)

    # 排序：频次降序
    ranked = sorted(freq.items(), key=lambda kv: -kv[1])
    terms = [{"term": k, "freq": f, "lessons": sorted(src[k])} for k, f in ranked]
    out = {"generated_from": [r for r, _ in pdfs], "seeds": seeds, "terms": terms}
    with open(os.path.join(OUT_DIR, "术语表.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    print(f"\n抽取英文候选术语 {len(terms)} 个，Top 60：")
    for k, f in ranked[:60]:
        print(f"  {f:>4}  {k}")
    print(f"\n名词记录种子 {len(seeds)} 条: {seeds[:10]}")

if __name__ == "__main__":
    main()
