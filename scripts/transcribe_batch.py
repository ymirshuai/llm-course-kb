# -*- coding: utf-8 -*-
"""批量转写一个课程目录的所有切段（断点续传）。
用法: python transcribe_batch.py <音频目录名，如 "L06-AI编程-从入门到精通"> [模型]
模型默认 paraformer-v2(带热词)。结果存 转写/<目录名>/segNNN.result.json
"""
import os, sys, json, time, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key

BASE = "https://dashscope.aliyuncs.com"
KEY, SRC = load_key()
H = {"Authorization": f"Bearer {KEY}"}

_vf = os.path.join(ROOT, "课件对齐", "vocabulary_id.json")
VOCAB_ID = json.load(open(_vf, encoding="utf-8"))["vocabulary_id"] if os.path.exists(_vf) else None

def upload_oss(path, model="paraformer-v2"):
    r = requests.get(f"{BASE}/api/v1/uploads", params={"action": "getPolicy", "model": model},
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
        resp = requests.post(p["upload_host"], data=form,
                             files={"file": (fname, fh)}, timeout=600)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"上传失败 {resp.status_code}")
    return f"oss://{key}"

def submit(model, oss_url, use_vocab):
    body = {"model": model, "input": {"file_urls": [oss_url]}}
    if use_vocab and VOCAB_ID and model.startswith("paraformer"):
        body["parameters"] = {"vocabulary_id": VOCAB_ID}
    r = requests.post(f"{BASE}/api/v1/services/audio/asr/transcription",
                      headers={**H, "X-DashScope-Async": "enable",
                               "X-DashScope-OssResourceResolve": "enable"},
                      json=body, timeout=30)
    d = r.json()
    tid = d.get("output", {}).get("task_id")
    if not tid:
        raise RuntimeError(f"提交失败: {json.dumps(d, ensure_ascii=False)[:300]}")
    return tid

def poll(task_id, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        o = requests.get(f"{BASE}/api/v1/tasks/{task_id}", headers=H, timeout=30).json()["output"]
        if o["task_status"] in ("SUCCEEDED", "FAILED"):
            return o
        time.sleep(8)
    raise TimeoutError(task_id)

def main():
    lesson_dir = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "paraformer-v2"
    adir = os.path.join(ROOT, "音频", lesson_dir)
    segs = json.load(open(os.path.join(adir, "segments.json"), encoding="utf-8"))["segments"]
    out_dir = os.path.join(ROOT, "转写", lesson_dir)
    os.makedirs(out_dir, exist_ok=True)
    print(f"转写 {lesson_dir}: {len(segs)} 段, model={model}, 热词={VOCAB_ID is not None}, 密钥={SRC}")

    todo = [s for s in segs if not os.path.exists(os.path.join(out_dir, s["file"].replace(".flac", ".result.json")))]
    print(f"待转写 {len(todo)} 段（已完成 {len(segs)-len(todo)}）")
    for i, s in enumerate(todo):
        tag = s["file"].replace(".flac", "")
        path = os.path.join(adir, s["file"])
        try:
            url = upload_oss(path, model)
            tid = submit(model, url, True)
            o = poll(tid)
            if o["task_status"] != "SUCCEEDED":
                print(f"[{i+1}/{len(todo)}] FAILED {tag}: {o.get('code')}")
                continue
            turl = o["results"][0]["transcription_url"]
            data = requests.get(turl, timeout=60).json()
            meta = {"segment": s, "model": model, "vocabulary_id": VOCAB_ID,
                    "content_duration": o["results"][0].get("content_duration")}
            json.dump({"meta": meta, "result": data},
                      open(os.path.join(out_dir, f"{tag}.result.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            cd = o["results"][0].get("content_duration")
            print(f"[{i+1}/{len(todo)}] OK {tag}  语音时长 {cd}s")
        except Exception as e:
            print(f"[{i+1}/{len(todo)}] !! {tag}: {str(e)[:200]}")

if __name__ == "__main__":
    main()
