# -*- coding: utf-8 -*-
"""术语纠错 pass（DeepSeek/GLM，key 从 HKLM 环境变量读）。
流程:
1. merge: 把 转写/<课>/segNNN.result.json 按 segments.json 的时间偏移合并成整课句子流
   -> 知识库/逐字稿/<课>.raw.json (可跳过, 已存在则不重做)
2. correct: 分块(~50句)调 deepseek-chat, 只修术语/同音字错词, 句数不变校验
   -> 知识库/逐字稿/<课>.corrected.json
3. report: 纠错差异清单 -> 知识库/逐字稿/<课>.corrections.md
用法: python correct_terms.py <课目录名> [--redo-merge]
"""
import os, sys, json, re, time, winreg, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def regval(name):
    k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                       r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
    v, _ = winreg.QueryValueEx(k, name)
    winreg.CloseKey(k)
    return v.strip()

def llm(messages, model="deepseek-chat", base="https://api.deepseek.com", max_retries=3):
    key = regval("DEEPSEEK_API_KEY")
    last = None
    for i in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=json.dumps({"model": model, "messages": messages, "temperature": 0.1,
                                 "response_format": {"type": "json_object"}}).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=300))
            return r["choices"][0]["message"]["content"]
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"LLM调用失败: {last}")

# ---------- merge ----------
def merge_lesson(lesson):
    adir = os.path.join(ROOT, "音频", lesson)
    odir = os.path.join(ROOT, "转写", lesson)
    out = os.path.join(ROOT, "知识库", "逐字稿", f"{lesson}.raw.json")
    if os.path.exists(out):
        print(f"merge 已存在: {out}")
        return out
    segs = json.load(open(os.path.join(adir, "segments.json"), encoding="utf-8"))["segments"]
    sentences = []
    for s in segs:
        rf = os.path.join(odir, s["file"].replace(".flac", ".result.json"))
        if not os.path.exists(rf):
            print(f"  !! 缺转写结果: {rf}")
            continue
        d = json.load(open(rf, encoding="utf-8"))
        if d["meta"].get("no_speech"):
            continue
        for t in d["result"]["transcripts"]:
            for sent in t.get("sentences", []):
                sentences.append({
                    "begin": round(s["start_sec"] + sent["begin_time"] / 1000, 2),
                    "end": round(s["start_sec"] + sent["end_time"] / 1000, 2),
                    "text": sent["text"]})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    meta = {"lesson": lesson, "n_sentences": len(sentences),
            "duration_sec": segs[-1]["end_sec"] if segs else 0}
    json.dump({"meta": meta, "sentences": sentences}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"merge 完成: {len(sentences)} 句 -> {out}")
    return out

# ---------- correct ----------
def load_terms():
    p = os.path.join(ROOT, "课件对齐", "热词表.json")
    d = json.load(open(p, encoding="utf-8"))
    items = d.get("terms", d) if isinstance(d, dict) else d
    terms = []
    for x in items:
        if isinstance(x, dict):
            terms.append(x.get("text") or x.get("term") or x.get("word") or "")
        else:
            terms.append(str(x))
    return [t for t in terms if t and len(t) >= 2]

SYSTEM = """你是ASR逐字稿校对员。老师讲课逐字稿里术语常被误写。规则：
1. 只修正【术语拼写】和【明显同音错字】，尤其是英文技术词（如 Laura/LORA→LoRA、信统→系统、retrial→retrieval）
2. 绝不改动语序、用词风格、口语气；不加字、不删字、不改标点结构（除错字修复必需）
3. 不确定的保持原样
4. 输出 JSON: {"corrections": [{"wrong": "原文错词", "right": "正确词"}]}，只列确实出现的错误，去重"""

def correct_lesson(raw_path, terms):
    d = json.load(open(raw_path, encoding="utf-8"))
    sents = d["sentences"]
    full = "".join(s["text"] for s in sents)
    # 只把可能出现在本文中的术语给模型（省 token）
    terms_hit = sorted({t for t in terms if re.search(re.escape(t), full, re.I)})
    terms_show = terms_hit[:120]
    print(f"句数 {len(sents)}，字数 {len(full)}，命中术语表 {len(terms_show)} 条")

    chunks, CH = [], 50
    for i in range(0, len(sents), CH):
        chunks.append(sents[i:i + CH])
    all_corrections, changed_chunks = [], 0
    for ci, ch in enumerate(chunks):
        text = "\n".join(f"{j}. {s['text']}" for j, s in enumerate(ch))
        prompt = f"术语参考表: {json.dumps(terms_show, ensure_ascii=False)}\n\n逐字稿(带句号):\n{text}\n\n找出其中的术语/同音字错误，输出 corrections JSON。"
        try:
            resp = llm([{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": prompt}])
            obj = json.loads(resp)
            corrs = obj.get("corrections", [])
        except Exception as e:
            print(f"  块{ci+1}/{len(chunks)} 失败: {str(e)[:100]}")
            corrs = []
        # 过滤：wrong 必须真实出现在本块；单个汉字 wrong 禁止（全局替换会毁文本，如 入→Rule）
        block_text = "".join(s["text"] for s in ch)
        valid = [c for c in corrs if isinstance(c, dict) and c.get("wrong") and c.get("right")
                 and c["wrong"] in block_text and c["wrong"] != c["right"]
                 and not (len(c["wrong"]) == 1 and re.match(r"[\u4e00-\u9fff]", c["wrong"]))]
        if valid:
            changed_chunks += 1
        all_corrections.extend([dict(c, chunk=ci) for c in valid])
        print(f"  块{ci+1}/{len(chunks)}: {len(valid)} 处修正")
        time.sleep(1)
    # 逐句应用修正（保留每句真实时间戳）
    # ASCII 词/短语用词边界替换（防 ai→AI 污染 training）；中文多字词用普通替换
    def apply_reps(t, reps):
        skipped = 0
        for c in sorted(reps, key=lambda x: -len(x["wrong"])):
            w, r = c["wrong"], c["right"]
            if re.fullmatch(r"[A-Za-z0-9 .+\-]+", w):
                t2 = re.sub(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])",
                            lambda m: r, t)
            elif len(w) == 1 and re.match(r"[\u4e00-\u9fff]", w):
                skipped += 1
                continue
            else:
                t2 = t.replace(w, r)
            t = t2
        return t, skipped

    rebuilt, pos = [], 0
    total_skipped = 0
    for s in sents:
        new_text, sk = apply_reps(s["text"], all_corrections)
        total_skipped += sk
        rebuilt.append({"begin": s["begin"], "end": s["end"], "text": new_text})
        pos += 1
    replace_log = []
    for s_old, s_new in zip(sents, rebuilt):
        if s_old["text"] != s_new["text"]:
            replace_log.append({"before": s_old["text"][:60], "after": s_new["text"][:60]})
    if total_skipped:
        print(f"  跳过 {total_skipped} 次危险的单汉字替换")
    out = os.path.join(ROOT, "知识库", "逐字稿", os.path.basename(raw_path).replace(".raw.json", ".corrected.json"))
    json.dump({"meta": {**d["meta"], "corrected": True,
                        "n_corrections": len(replace_log)},
               "sentences": rebuilt, "replacements": replace_log},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 差异报告
    rp = out.replace(".corrected.json", ".corrections.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write(f"# 纠错报告: {d['meta']['lesson']}\n\n改动的句子数: {len(replace_log)}\n\n")
        f.write("| 原句(前60字) | 修正后(前60字) |\n|---|---|\n")
        for r in replace_log[:200]:
            f.write(f"| {r['before']} | {r['after']} |\n")
    print(f"纠错完成: {len(replace_log)} 类替换 -> {out}")
    return out

if __name__ == "__main__":
    lesson = sys.argv[1]
    redo = "--redo-merge" in sys.argv
    raw = os.path.join(ROOT, "知识库", "逐字稿", f"{lesson}.raw.json")
    if redo and os.path.exists(raw):
        os.remove(raw)
    if not os.path.exists(raw):
        raw = merge_lesson(lesson)
    terms = load_terms()
    correct_lesson(raw, terms)
