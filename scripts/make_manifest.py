# -*- coding: utf-8 -*-
"""生成 manifest.json：视频文件 ↔ 课号映射。
依据：UUIDv1 内嵌的平台时间戳 + 课件 mtime 对齐 + 人工推断标记。
原始视频文件不做任何改名/移动。
"""
import os, re, json, uuid, subprocess, datetime, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "课程视频")
FF = r"D:\download\小丸工具箱rev194\tools\ffmpeg.exe"
OUT = os.path.join(ROOT, "索引")

# 2026 期推断映射：平台时间戳(日期) -> (课号, 课名, 置信度)
# 置信度: confirmed=课件mtime与时间戳同日咬合 | inferred=顺序推断 | pending=需转写内容校验
LESSON_MAP_2026 = {
    "2026-07-09": ("00", "开班典礼", "inferred"),
    "2026-07-14": ("01", "提示词和RAG", "pending"),   # 课件mtime 07-10，视频08:43上传，待内容校验
    "2026-07-16": ("02", "未知(疑为Agent相关)", "pending"),  # Agent.pdf mtime 07-13
    "2026-07-21": ("05", "AI大模型原理与API使用", "confirmed"),
    "2026-07-23": ("06", "AI编程-从入门到精通", "confirmed"),
    "2026-07-28": ("07", "LangChain：多任务应用开发", "confirmed"),
    "2026-08-02": ("08", "AI框架设计与选型", "confirmed"),
    "2026-08-04": ("09", "HuggingFace生态实战", "confirmed"),
    "2026-08-07": ("10", "神经网络基础与Tensorflow实战", "confirmed"),
    "2026-08-11": ("11", "Pytorch与视觉检测", "confirmed"),
    "2026-08-14": ("12", "开发框架相关面试辅导", "confirmed"),
    "2026-08-18": ("13", "LLM微调原理", "confirmed"),
    "2026-08-24": ("14", "高质量微调数据工程与评估", "confirmed"),
    "2026-08-25": ("15", "LLM模型蒸馏与微调实操", "confirmed"),
    "2026-08-28": ("16", "未知(课件缺失)", "inferred"),
    "2026-09-01": ("17", "项目实战：AI质检", "confirmed"),
    "2026-09-04": ("18", "模型训练与微调相关面试辅导", "confirmed"),
    "2026-09-08": ("19", "Embeddings和向量数据库", "confirmed"),
    "2026-09-11": ("20", "RAG技术与应用", "pending"),
    "2026-09-15": ("21", "RAG多模态数据处理", "pending"),
    "2026-09-18": ("22", "RAG高级技术与调优", "confirmed"),
    "2026-09-22": ("23", "项目实战：企业知识库", "confirmed"),
}

def probe_duration(path):
    try:
        out = subprocess.run([FF, "-i", path], capture_output=True, text=True,
                             errors="ignore", timeout=60).stderr
        m = re.search(r"Duration: (\d+):(\d+):(\d+)", out)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    except Exception:
        pass
    return 0

def main():
    os.makedirs(OUT, exist_ok=True)
    items = []
    for f in sorted(glob.glob(os.path.join(VDIR, "*.mp4"))):
        name = os.path.basename(f)
        m = re.match(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", name)
        rec = {
            "file": name,
            "size_mb": round(os.path.getsize(f) / 1048576, 1),
            "duration_sec": probe_duration(f),
        }
        if m:
            u = uuid.UUID(m.group(1))
            ts = datetime.datetime(1582, 10, 15, tzinfo=datetime.timezone.utc) + \
                 datetime.timedelta(microseconds=u.time / 10)
            ts = ts.astimezone()
            rec["platform_time"] = ts.strftime("%Y-%m-%d %H:%M:%S")
            day = ts.strftime("%Y-%m-%d")
            if ts.year == 2026 and day in LESSON_MAP_2026:
                no, title, conf = LESSON_MAP_2026[day]
                rec.update({"cohort": "2026", "lesson_no": no, "lesson_title": title,
                            "confidence": conf})
            else:
                rec.update({"cohort": "archive", "lesson_no": None,
                            "lesson_title": None, "confidence": None})
        else:
            # 无 UUID 段（如 提示词工程到RAG.mp4）
            rec.update({"platform_time": None, "cohort": "unknown",
                        "lesson_no": None, "lesson_title": None, "confidence": None})
        items.append(rec)

    items.sort(key=lambda r: (r.get("platform_time") or "9999", r["file"]))
    manifest = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(items),
        "total_duration_sec": sum(r["duration_sec"] for r in items),
        "cohorts": {
            "2026": [r for r in items if r["cohort"] == "2026"],
            "archive": [r for r in items if r["cohort"] == "archive"],
            "unknown": [r for r in items if r["cohort"] == "unknown"],
        },
        "items": items,
    }
    path = os.path.join(OUT, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)

    c26 = manifest["cohorts"]["2026"]
    print(f"总: {len(items)} 个 / {manifest['total_duration_sec']/3600:.1f}h")
    print(f"2026期: {len(c26)} 个 / {sum(r['duration_sec'] for r in c26)/3600:.1f}h")
    conf = sum(1 for r in c26 if r['confidence'] == 'confirmed')
    print(f"  映射置信: confirmed={conf} inferred/pending={len(c26)-conf}")
    print(f"往期: {len(manifest['cohorts']['archive'])} 个 / "
          f"{sum(r['duration_sec'] for r in manifest['cohorts']['archive'])/3600:.1f}h")
    print(f"未知: {len(manifest['cohorts']['unknown'])} 个")
    for r in c26:
        print(f"  [{r.get('confidence','?'):9s}] {r.get('platform_time','')[:10]} "
              f"{r['duration_sec']//3600}h{r['duration_sec']%3600//60:02d}m  "
              f"L{r.get('lesson_no','--')} {r.get('lesson_title') or ''}")

if __name__ == "__main__":
    main()
