# -*- coding: utf-8 -*-
"""全量转写驱动器（并发版）。
- 引擎: fun-asr（用户确认，预算 ¥220）
- 并发: 6 个在途任务（提交+轮询解耦），断点续传（已有 result.json 跳过）
- 与切段协同: 每轮重新扫描 音频/*/segments.json，切段新完成的课自动纳入；全部完成即退出
- 进度: 转写/_progress.json（累计语音计费时长/任务数）
"""
import os, sys, json, time, threading, queue, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key

BASE = "https://dashscope.aliyuncs.com"
KEY, SRC = load_key()
H = {"Authorization": f"Bearer {KEY}"}
MODEL = "fun-asr"
CONCURRENCY = 6
PROGRESS = os.path.join(ROOT, "转写", "_progress.json")

def upload_oss(path):
    r = requests.get(f"{BASE}/api/v1/uploads", params={"action": "getPolicy", "model": MODEL},
                     headers=H, timeout=30)
    p = r.json()["data"]
    fname = os.path.basename(path)
    key = f"{p['upload_dir']}/{fname}"
    form = {"OSSAccessKeyId": p["oss_access_key_id"], "Signature": p["signature"],
            "policy": p["policy"], "x-oss-object-acl": p.get("x_oss_object_acl", "private"),
            "success_action_status": "200", "key": key}
    if p.get("x_oss_forbid_overwrite"):
        form["x-oss-forbid-overwrite"] = p["x_oss_forbid_overwrite"]
    with open(path, "rb") as fh:
        resp = requests.post(p["upload_host"], data=form, files={"file": (fname, fh)}, timeout=600)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"上传失败 {resp.status_code}: {resp.text[:120]}")
    return f"oss://{key}"

def submit(oss_url):
    body = {"model": MODEL, "input": {"file_urls": [oss_url]}}
    r = requests.post(f"{BASE}/api/v1/services/audio/asr/transcription",
                      headers={**H, "X-DashScope-Async": "enable",
                               "X-DashScope-OssResourceResolve": "enable"},
                      json=body, timeout=30)
    d = r.json()
    tid = d.get("output", {}).get("task_id")
    if not tid:
        raise RuntimeError(f"提交失败: {json.dumps(d, ensure_ascii=False)[:200]}")
    return tid

lock = threading.Lock()
stats = {"ok": 0, "fail": 0, "speech_sec": 0, "lessons_done": set(), "errors": []}

def save_progress():
    with lock:
        json.dump({"ok": stats["ok"], "fail": stats["fail"],
                   "speech_hours": round(stats["speech_sec"] / 3600, 2),
                   "lessons_done": sorted(stats["lessons_done"]),
                   "errors": stats["errors"][-20:]},
                  open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def worker(q):
    while True:
        item = q.get()
        if item is None:
            return
        lesson, seg, out_path = item
        tag = f"{lesson}/{seg['file']}"
        try:
            url = upload_oss(os.path.join(ROOT, "音频", lesson, seg["file"]))
            tid = submit(url)
            t0 = time.time()
            o = None
            while time.time() - t0 < 3600:
                o = requests.get(f"{BASE}/api/v1/tasks/{tid}", headers=H, timeout=30).json()["output"]
                if o["task_status"] in ("SUCCEEDED", "FAILED"):
                    break
                time.sleep(6)
            if o and o["task_status"] == "SUCCEEDED":
                data = requests.get(o["results"][0]["transcription_url"], timeout=60).json()
                ms = data.get("transcripts", [{}])[0].get("content_duration_in_milliseconds", 0)
                cd_sec = int(ms or 0) // 1000
                meta = {"segment": seg, "model": MODEL, "content_duration_ms": ms}
                json.dump({"meta": meta, "result": data},
                          open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                with lock:
                    stats["ok"] += 1; stats["speech_sec"] += cd_sec
                print(f"OK {tag} 语音{cd_sec}s 累计{stats['speech_sec']/3600:.2f}h", flush=True)
            elif o and o.get("code") in ("ASR_RESPONSE_HAVE_NO_WORDS", "SUCCESS_WITH_NO_VALID_FRAGMENT"):
                # 无有效语音段（纯静音/操作无讲解）：写空结果桩，不再重试
                meta = {"segment": seg, "model": MODEL, "no_speech": True, "code": o.get("code")}
                json.dump({"meta": meta, "result": {"transcripts": []}},
                          open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                with lock:
                    stats["ok"] += 1
                print(f"SKIP(无语音) {tag}", flush=True)
            else:
                code = o.get("code") if o else "timeout"
                with lock:
                    stats["fail"] += 1; stats["errors"].append(f"{tag}: {code}")
                print(f"FAIL {tag}: {code}", flush=True)
        except Exception as e:
            with lock:
                stats["fail"] += 1; stats["errors"].append(f"{tag}: {str(e)[:120]}")
            print(f"ERR  {tag}: {str(e)[:150]}", flush=True)
        save_progress()
        q.task_done()

def build_queue():
    tasks = []
    adir_root = os.path.join(ROOT, "音频")
    for d in sorted(os.listdir(adir_root)):
        segf = os.path.join(adir_root, d, "segments.json")
        if not os.path.exists(segf):
            continue
        segs = json.load(open(segf, encoding="utf-8"))["segments"]
        odir = os.path.join(ROOT, "转写", d)
        os.makedirs(odir, exist_ok=True)
        for s in segs:
            out = os.path.join(odir, s["file"].replace(".flac", ".result.json"))
            if not os.path.exists(out):
                tasks.append((d, s, out))
    return tasks

def main():
    q = queue.Queue()
    threads = [threading.Thread(target=worker, args=(q,), daemon=True) for _ in range(CONCURRENCY)]
    for t in threads: t.start()
    idle_rounds = 0
    for rnd in range(1, 200):
        tasks = build_queue()
        if not tasks:
            idle_rounds += 1
            # 可能切段还在产出，等 3 轮确认
            print(f"[轮{rnd}] 队列空（{idle_rounds}/3）", flush=True)
            if idle_rounds >= 3:
                break
            time.sleep(180)
            continue
        idle_rounds = 0
        print(f"[轮{rnd}] 入队 {len(tasks)} 段", flush=True)
        for t in tasks:
            q.put(t)
        q.join()
    for _ in threads: q.put(None)
    save_progress()
    print(f"ALL_DONE ok={stats['ok']} fail={stats['fail']} 语音时长={stats['speech_sec']/3600:.2f}h", flush=True)

if __name__ == "__main__":
    main()
