# -*- coding: utf-8 -*-
"""三层切块（方案第五节）：
- 大纲节点: LLM 按话题切换信号切段, 每课 20-40 个, 带时间锚点+小标题
- 子块: 按句边界+停顿切 200-400 字, 块间重叠1句 -> BM25/稀疏检索层
- 父块: 连续子块聚合成 1500-3000 字话题段 -> 喂 LLM 的原文层
输入: 知识库/逐字稿/<课>.corrected.json
输出: 知识库/切块/<课>.chunks.json
用法: python chunk_lesson.py <课目录名>
"""
import os, sys, json, time, winreg, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def regval(name):
    k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                       r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
    v, _ = winreg.QueryValueEx(k, name)
    winreg.CloseKey(k)
    return v.strip()

def llm_json(messages, model="deepseek-chat", max_retries=3):
    key = regval("DEEPSEEK_API_KEY")
    last = None
    for i in range(max_retries):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=json.dumps({"model": model, "messages": messages,
                                 "temperature": 0.2,
                                 "response_format": {"type": "json_object"}}).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=600))
            return json.loads(r["choices"][0]["message"]["content"])
        except Exception as e:
            last = e
            time.sleep(8 * (i + 1))
    raise RuntimeError(f"LLM调用失败: {last}")

def outline_nodes(sents, lesson_title):
    """让 LLM 通读全文(分段喂)标话题边界, 返回 [{start,end,title}]"""
    CH = 400
    chunks = [sents[i:i + CH] for i in range(0, len(sents), CH)]
    nodes = []
    for ci, ch in enumerate(chunks):
        text = "\n".join(f"[{j}] {s['text']}" for j, s in enumerate(ch))
        prompt = (f"课程《{lesson_title}》逐字稿第{ci+1}/{len(chunks)}段(句号0-{len(ch)-1})如下。\n"
                  "找出话题切换边界：讲师说\"下面我们讲/接下来/这个问题先到这/我们来看代码\"等信号处。\n"
                  "输出 JSON: {\"breaks\": [句号列表]}。每个 break 是本段内一个新话题开始的全局句号。\n"
                  f"全局句号偏移 = {ci*CH}（输出时加上）。没有明确切换就给空列表。\n\n{text}")
        try:
            obj = llm_json([{"role": "system", "content": "你是课程逐字稿结构分析员，只输出JSON。"},
                            {"role": "user", "content": prompt}])
            for b in obj.get("breaks", []):
                if isinstance(b, int) and 0 <= b < len(sents):
                    nodes.append(b)
        except Exception as e:
            print(f"  大纲块{ci+1} 失败: {str(e)[:100]}")
    bounds = sorted(set([0] + nodes + [len(sents)]))
    out = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b - a < 5:
            continue
        out.append({"start_sent": a, "end_sent": b,
                    "begin_sec": sents[a]["begin"], "end_sec": sents[b - 1]["end"]})
    return out

def title_node(node, sents, lesson_title):
    seg_text = "".join(s["text"] for s in sents[node["start_sent"]:node["start_sent"] + 30])[:800]
    try:
        obj = llm_json([{"role": "system", "content": "只输出JSON。"},
                        {"role": "user", "content":
                         f"给这段课程内容起一个小标题(≤15字)和3-6个涉及术语。输出: {{\"title\": \"...\", \"terms\": [\"...\"]}}\n\n{seg_text}"}])
        node["title"] = obj.get("title", "未命名")
        node["terms"] = obj.get("terms", [])
    except Exception:
        node["title"], node["terms"] = "未命名", []
    return node

def sub_chunks(sents, target=(200, 400)):
    """按句切 200-400 字子块, 块间重叠1句"""
    out, cur, length = [], [], 0
    for s in sents:
        cur.append(s)
        length += len(s["text"])
        if length >= target[1] or (length >= target[0] and len(s["text"]) > 0 and
                                   s["text"].endswith(("。", "！", "？", "?"))):
            out.append(cur)
            cur = cur[-1:]  # 重叠1句
            length = len(cur[0]["text"])
    if cur and len(cur) > 1:
        out.append(cur)
    blocks = []
    for i, ch in enumerate(out):
        blocks.append({"block_id": i, "start_sent": None, "n_chars": sum(len(s['text']) for s in ch),
                       "begin_sec": ch[0]["begin"], "end_sec": ch[-1]["end"],
                       "text": "".join(s["text"] for s in ch)})
    return blocks

def main():
    lesson = sys.argv[1]
    corrected = os.path.join(ROOT, "知识库", "逐字稿", f"{lesson}.corrected.json")
    d = json.load(open(corrected, encoding="utf-8"))
    sents = d["sentences"]
    # 课程标题: 从 manifest 查
    mf = json.load(open(os.path.join(ROOT, "索引", "manifest.json"), encoding="utf-8"))
    title = lesson
    for it in mf["items"]:
        if it.get("lesson_no") and lesson.startswith("L" + it["lesson_no"]) or it.get("lesson_no") == lesson.replace("L", "", 1):
            title = it.get("official_title") or it.get("lesson_title") or lesson
            break
    print(f"切块 {lesson}: {len(sents)} 句, 标题《{title}》")

    # 1) 大纲
    nodes = outline_nodes(sents, title)
    print(f"大纲节点: {len(nodes)} 个, 加标题中…")
    for nd in nodes:
        title_node(nd, sents, title)
        print(f"  [{nd['begin_sec']:.0f}s-{nd['end_sec']:.0f}s] {nd['title']}")

    # 2) 子块
    subs = sub_chunks(sents)
    print(f"子块: {len(subs)} 个")
    # 子块归属大纲节点
    for sb in subs:
        # 用时间归属
        sb["node"] = None
    ni = 0
    for sb in subs:
        while ni < len(nodes) - 1 and sb["begin_sec"] >= nodes[ni + 1]["begin_sec"]:
            ni += 1
        sb["node_title"] = nodes[ni]["title"] if nodes else ""

    # 3) 父块: 相邻同节点子块聚合 1500-3000 字
    parents, buf = [], []
    for sb in subs:
        buf.append(sb)
        n_chars = sum(b["n_chars"] for b in buf)
        node_changed = nodes and buf and sb.get("node_title") != (nodes[0]["title"] if nodes else "") and False
        if n_chars >= 1500 and (n_chars >= 3000 or sb is subs[-1] or
                                subs[subs.index(sb) + 1].get("node_title") != sb.get("node_title")):
            parents.append({"begin_sec": buf[0]["begin_sec"], "end_sec": buf[-1]["end_sec"],
                            "text": "".join(b["text"] for b in buf),
                            "node_title": buf[0].get("node_title", "")})
            buf = []
    if buf:
        parents.append({"begin_sec": buf[0]["begin_sec"], "end_sec": buf[-1]["end_sec"],
                        "text": "".join(b["text"] for b in buf),
                        "node_title": buf[0].get("node_title", "")})
    print(f"父块: {len(parents)} 个")

    out = os.path.join(ROOT, "知识库", "切块", f"{lesson}.chunks.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"meta": {"lesson": lesson, "title": title,
                        "duration_sec": d["meta"]["duration_sec"],
                        "n_sentences": len(sents)},
               "outline": nodes, "sub_chunks": subs, "parent_chunks": parents},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"-> {out}")

if __name__ == "__main__":
    main()
