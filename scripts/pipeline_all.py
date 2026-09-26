# -*- coding: utf-8 -*-
"""全量批处理：71 课 逐课 纠错 -> 切块 -> 入库。断点续传（各阶段产物存在即跳过）。
进度写 批处理进度.json。用 DeepSeek（用户 key），纠错+大纲约 ¥30-40。
"""
import os, sys, json, subprocess, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PROG = os.path.join(ROOT, "批处理进度.json")

def load_prog():
    if os.path.exists(PROG):
        return json.load(open(PROG, encoding="utf-8"))
    return {"done": [], "failed": [], "stage": {}}

def save_prog(p):
    json.dump(p, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def lessons():
    out = []
    for d in sorted(os.listdir(os.path.join(ROOT, "音频"))):
        if d == "样本":
            continue
        seg = os.path.join(ROOT, "音频", d, "segments.json")
        raw = os.path.join(ROOT, "知识库", "逐字稿", f"{d}.raw.json")
        res_ok = True
        if os.path.exists(seg):
            segs = json.load(open(seg, encoding="utf-8"))["segments"]
            odir = os.path.join(ROOT, "转写", d)
            res_ok = all(os.path.exists(os.path.join(odir, s["file"].replace(".flac", ".result.json")))
                         for s in segs)
        if res_ok:
            out.append(d)
    return out

def run(cmd):
    r = subprocess.run([PY] + cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode, (r.stdout or "")[-400:], (r.stderr or "")[-400:]

def main():
    p = load_prog()
    ls = lessons()
    print(f"共 {len(ls)} 课待处理", flush=True)
    for i, lesson in enumerate(ls):
        if lesson in p["done"]:
            continue
        print(f"=== [{i+1}/{len(ls)}] {lesson} ===", flush=True)
        stages = [
            (["scripts/correct_terms.py", lesson], "纠错"),
            (["scripts/chunk_lesson.py", lesson], "切块"),
            (["scripts/embed_ingest.py", lesson], "入库"),
        ]
        ok = True
        for cmd, name in stages:
            tag = f"{lesson}:{name}"
            # 幂等检查
            if name == "纠错" and os.path.exists(os.path.join(ROOT, "知识库", "逐字稿", f"{lesson}.corrected.json")):
                continue
            if name == "切块" and os.path.exists(os.path.join(ROOT, "知识库", "切块", f"{lesson}.chunks.json")):
                continue
            code, out, err = run(cmd)
            tail = (out + err).replace("\n", " | ")[-260:]
            if code != 0:
                print(f"  !! {name}失败: {tail}", flush=True)
                p["failed"].append({"lesson": lesson, "stage": name, "err": tail})
                save_prog(p)
                ok = False
                break
            print(f"  {name} OK: {tail[-120:]}", flush=True)
        if ok:
            p["done"].append(lesson)
            p["failed"] = [f for f in p["failed"] if f["lesson"] != lesson]
            save_prog(p)
        time.sleep(2)
    print(f"ALL_DONE 完成{len(p['done'])} 失败{len(p['failed'])}", flush=True)

if __name__ == "__main__":
    main()
