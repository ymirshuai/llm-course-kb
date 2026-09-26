# -*- coding: utf-8 -*-
"""切样本：3 段正式对比样本(15min) + 2 段往期身份探针(5min)。"""
import os, json, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = r"D:\download\小丸工具箱rev194\tools\ffmpeg.exe"
OUT = os.path.join(ROOT, "音频", "样本")
os.makedirs(OUT, exist_ok=True)

manifest = json.load(open(os.path.join(ROOT, "索引", "manifest.json"), encoding="utf-8"))
items = manifest["items"]

def by_lesson(no):
    for r in items:
        if r.get("lesson_no") == no and r["cohort"] == "2026":
            return r["file"]
    raise KeyError(no)

def by_time_prefix(prefix):
    for r in items:
        if (r.get("platform_time") or "").startswith(prefix):
            return r["file"]
    raise KeyError(prefix)

# (输出名, 视频文件, 起始秒, 时长秒, 用途)
PLAN = [
    ("A_L13_微调原理",  by_lesson("13"), 1800, 900, "术语密集/中英夹杂"),
    ("B_L06_AI编程",    by_lesson("06"), 3600, 900, "代码实操"),
    ("C_L20_RAG",       by_lesson("20"), 1800, 900, "RAG概念讲解"),
    ("P1_往期2023",     by_time_prefix("2023-11-16"), 600, 300, "往期身份探针"),
    ("P2_往期2025",     by_time_prefix("2025-07-26"), 600, 300, "往期身份探针"),
]

for name, f, ss, t, note in PLAN:
    src = os.path.join(ROOT, "课程视频", f)
    dst = os.path.join(OUT, f"{name}.flac")
    r = subprocess.run([FF, "-v", "error", "-ss", str(ss), "-t", str(t), "-i", src,
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", dst, "-y"],
                       capture_output=True, text=True, errors="ignore")
    ok = os.path.exists(dst)
    print(f"{'OK ' if ok else 'FAIL'} {name}.flac  ({note})  src={f[:20]}...  "
          f"size={os.path.getsize(dst)/1048576:.1f}MB" if ok else f"FAIL {name}: {r.stderr[:200]}")

print("\n样本清单已写入 样本/_plan.json")
json.dump([{"name": n, "file": f, "start_sec": s, "len_sec": t, "purpose": note}
           for n, f, s, t, note in PLAN],
          open(os.path.join(OUT, "_plan.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
