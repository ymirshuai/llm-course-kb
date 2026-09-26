# -*- coding: utf-8 -*-
"""批量抽音频 + 静音点切段（2026 主课 + 赠课全量）。
每个视频: 第一遍 silencedetect 找静音点 -> 选切点(段长 840~1200s) -> 第二遍按段切 s16 flac。
断点续传: 已存在的段跳过。产物: 音频/<课号-标题>/segNN.flac + segments.json
用法: python extract_all_audio.py [cohort，默认 all]
"""
import os, re, sys, json, glob, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = r"D:\download\小丸工具箱rev194\tools\ffmpeg.exe"
VDIR = os.path.join(ROOT, "课程视频")
ADIR = os.path.join(ROOT, "音频")

MIN_SEG, TARGET_SEG, MAX_SEG = 840, 900, 1200

manifest = json.load(open(os.path.join(ROOT, "索引", "manifest.json"), encoding="utf-8"))
_cohort = sys.argv[1] if len(sys.argv) > 1 else "all"
if _cohort == "all":
    items = [r for r in manifest["items"] if r["cohort"] in ("2026", "archive") and r.get("lesson_no")]
else:
    items = [r for r in manifest["items"] if r["cohort"] == _cohort and r.get("lesson_no")]

def detect_silences(path):
    p = subprocess.run([FF, "-i", path, "-af", "silencedetect=noise=-35dB:d=0.5",
                        "-f", "null", "-"], capture_output=True, text=True,
                       errors="ignore", timeout=3600)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d\.]+)", p.stderr)]
    mids = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else s + 1
        mids.append((s + e) / 2)
    return mids

def plan_cuts(duration, mids):
    """在 840~1200s 窗口内选最近的静音中点作为切点。"""
    cuts, last = [], 0.0
    while duration - last > MAX_SEG:
        target = last + TARGET_SEG
        lo, hi = last + MIN_SEG, last + MAX_SEG
        cand = [m for m in mids if lo <= m <= hi]
        if cand:
            cuts.append(min(cand, key=lambda m: abs(m - target)))
        else:
            cuts.append(target)
        last = cuts[-1]
    return cuts

def main():
    for r in items:
        no, title = r.get("lesson_no"), r.get("lesson_title") or "未知"
        if not no:
            continue
        # Windows 目录名非法字符清洗（半角冒号等 → 全角）
        for ch in '\\/:*?"<>|':
            title = title.replace(ch, "：" if ch == ":" else "_")
        name = f"L{no}-{title}"
        out_dir = os.path.join(ADIR, name)
        os.makedirs(out_dir, exist_ok=True)
        seg_json = os.path.join(out_dir, "segments.json")
        if os.path.exists(seg_json):
            print(f"跳过(已完成): {name}")
            continue
        src = os.path.join(VDIR, r["file"])
        dur = r["duration_sec"]
        print(f"[{name}] 时长 {dur//3600}h{dur%3600//60:02d}m，检测静音点…", flush=True)
        mids = detect_silences(src)
        cuts = plan_cuts(dur, mids)
        bounds = [0.0] + cuts + [float(dur)]
        segs = []
        for i in range(len(bounds) - 1):
            start, end = bounds[i], bounds[i + 1]
            seg_file = os.path.join(out_dir, f"seg{i:03d}.flac")
            segs.append({"file": f"seg{i:03d}.flac", "start_sec": round(start, 2),
                         "end_sec": round(end, 2), "len_sec": round(end - start, 2)})
            if os.path.exists(seg_file):
                continue
            p = subprocess.run([FF, "-v", "error", "-ss", str(start), "-t",
                                str(end - start), "-i", src, "-vn", "-ac", "1",
                                "-ar", "16000", "-c:a", "flac", "-sample_fmt", "s16",
                                seg_file, "-y"], capture_output=True, text=True,
                               errors="ignore", timeout=1800)
            if p.returncode != 0 or not os.path.exists(seg_file):
                print(f"  !! 切段失败 seg{i:03d}: {p.stderr[:200]}", flush=True)
        json.dump({"lesson_no": no, "lesson_title": title, "source_video": r["file"],
                   "duration_sec": dur, "segments": segs},
                  open(seg_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        total_min = sum(s["len_sec"] for s in segs) / 60
        print(f"  完成: {len(segs)} 段 / {total_min:.0f} 分钟", flush=True)

if __name__ == "__main__":
    main()
