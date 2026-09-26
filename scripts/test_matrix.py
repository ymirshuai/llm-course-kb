# -*- coding: utf-8 -*-
"""最小转写测试：变体矩阵（位深 x 格式 x 文件名），定位 SERVER_ERROR 原因。"""
import os, sys, json, time, subprocess, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key

FF = r"D:\download\小丸工具箱rev194\tools\ffmpeg.exe"
BASE = "https://dashscope.aliyuncs.com"
KEY, _ = load_key()
H = {"Authorization": f"Bearer {KEY}"}
SRC = os.path.join(ROOT, "音频", "样本", "A_L13_微调原理.flac")
TMP = os.path.join(ROOT, "tmp")

def make(dst, args):
    subprocess.run([FF, "-v", "error", "-i", SRC, "-t", "60"] + args + [dst, "-y"],
                   check=True, capture_output=True)

def upload(path):
    r = requests.get(f"{BASE}/api/v1/uploads",
                     params={"action": "getPolicy", "model": "paraformer-v2"},
                     headers=H, timeout=30)
    p = r.json()["data"]
    key = f"{p['upload_dir']}/{os.path.basename(path)}"
    form = {
        "OSSAccessKeyId": p["oss_access_key_id"],
        "Signature": p["signature"],
        "policy": p["policy"],
        "x-oss-object-acl": p.get("x_oss_object_acl", "private"),
        "success_action_status": "200",
        "key": key,
    }
    if p.get("x_oss_forbid_overwrite"):
        form["x-oss-forbid-overwrite"] = p["x_oss_forbid_overwrite"]
    with open(path, "rb") as fh:
        resp = requests.post(p["upload_host"], data=form,
                             files={"file": (os.path.basename(path), fh)}, timeout=300)
    return resp.status_code, f"oss://{key}"

def transcribe(oss_url, poll_max=40):
    body = {"model": "paraformer-v2", "input": {"file_urls": [oss_url]}}
    r = requests.post(f"{BASE}/api/v1/services/audio/asr/transcription",
                      headers={**H, "X-DashScope-Async": "enable"}, json=body, timeout=30)
    tid = r.json()["output"]["task_id"]
    for _ in range(poll_max):
        o = requests.get(f"{BASE}/api/v1/tasks/{tid}", headers=H, timeout=30).json()["output"]
        if o["task_status"] in ("SUCCEEDED", "FAILED"):
            return o
        time.sleep(5)
    return {"task_status": "TIMEOUT"}

VARIANTS = [
    ("flac16_ascii", ["-c:a", "flac", "-sample_fmt", "s16"], "v_flac16.flac"),
    ("flac24_ascii", ["-c:a", "flac"], "v_flac24.flac"),
    ("wav16_ascii",  ["-c:a", "pcm_s16le"], "v_wav16.wav"),
]

for name, args, fname in VARIANTS:
    dst = os.path.join(TMP, fname)
    make(dst, args)
    code, url = upload(dst)
    if code not in (200, 201):
        print(f"{name}: UPLOAD {code}")
        continue
    o = transcribe(url)
    msg = o.get("task_status")
    if msg == "SUCCEEDED":
        turl = o["results"][0]["transcription_url"]
        d = requests.get(turl, timeout=60).json()
        text = d["transcripts"][0]["text"]
        print(f"{name}: OK  首句: {text[:60]}")
        json.dump(d, open(os.path.join(ROOT, "tmp", f"{name}.json"), "w",
                          encoding="utf-8"), ensure_ascii=False)
        break   # 找到一个可用格式就停
    else:
        print(f"{name}: {msg}  code={o.get('code')}  msg={str(o.get('message'))[:120]}")
