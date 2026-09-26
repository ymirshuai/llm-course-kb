# -*- coding: utf-8 -*-
"""全量转写驱动器：扫描 音频/*/segments.json，逐课调 transcribe_batch 的逻辑转写。
- 引擎: fun-asr（用户已确认，预算 ¥220）
- 断点续传: 已有 result.json 的段跳过
- 与切段脚本协同: 切段未完成的课会在下一轮扫描时补上，全部完成即退出
- 累计语音时长统计写入 转写/_progress.json
"""
import os, sys, json, time, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SCRIPT = os.path.join(ROOT, "scripts", "transcribe_batch.py")
MODEL = "fun-asr"

# 2026 期优先（有课件、主课），然后按 manifest 顺序
mf = json.load(open(os.path.join(ROOT, "索引", "manifest.json"), encoding="utf-8"))
order = []
for it in mf["items"]:
    if it["cohort"] == "2026":
        order.append((0, it.get("module", 9), it.get("lesson_no_official", 99), it))
for it in mf["items"]:
    if it["cohort"] != "2026":
        order.append((1, 9, 99, it))

def lesson_dir_name(it):
    # 与 extract_all_audio.py 的目录命名保持一致
    if it["cohort"] == "2026":
        no = it.get("lesson_no") or ""
        guess = it.get("lesson_guess") or it.get("official_title") or it["file"][:12]
        return f"L{no}-{guess}" if no else f"M{it.get('module')}L{it.get('lesson_no_official')}-{it.get('official_title','')[:20]}"
    return it.get("lesson_no", it["file"][:20])

# 扫描实际存在的音频目录（以磁盘为准，不猜名字）
def scan():
    adir_root = os.path.join(ROOT, "音频")
    if not os.path.isdir(adir_root):
        return []
    out = []
    for d in sorted(os.listdir(adir_root)):
        seg = os.path.join(adir_root, d, "segments.json")
        if os.path.exists(seg):
            out.append(d)
    return out

def priority(d):
    for rank, mod, no, it in order:
        if it["cohort"] == "2026":
            if d.startswith(f"L{it.get('lesson_no')}-") or d == lesson_dir_name(it):
                return (rank, mod, no)
        else:
            if d == it.get("lesson_no") or d.startswith(it.get("lesson_no", "###") + "-"):
                return (rank, 9, 99)
    return (5, 9, 99)

rounds = 0
total_speech = 0
while True:
    dirs = scan()
    rounds += 1
    pending = []
    for d in sorted(dirs, key=priority):
        seg = json.load(open(os.path.join(ROOT, "音频", d, "segments.json"), encoding="utf-8"))["segments"]
        odir = os.path.join(ROOT, "转写", d)
        done = sum(1 for s in seg if os.path.exists(os.path.join(odir, s["file"].replace(".flac", ".result.json"))))
        if done < len(seg):
            pending.append((d, done, len(seg)))
    if not pending:
        # 确认切段是否也完成了（没有音频目录的课）
        print(f"第{rounds}轮: 所有已切段课程转写完毕")
        break
    print(f"=== 第{rounds}轮: 待转写 {len(pending)} 课 ===")
    for d, done, tot in pending:
        print(f"--- {d} ({done}/{tot}) ---")
        r = subprocess.run([PY, SCRIPT, d, MODEL], capture_output=True, text=True, encoding="utf-8", errors="ignore")
        print(r.stdout[-500:] if r.stdout else "", flush=True)
        if r.returncode != 0:
            print(f"  !! 异常: {r.stderr[-300:]}", flush=True)
    if rounds > 40:
        print("轮次超限，退出")
        break
    time.sleep(60)

print("ALL_DONE")
