# -*- coding: utf-8 -*-
"""样本转写：临时上传 -> 提交异步任务 -> 轮询 -> 下载结果 JSON。
模型: paraformer-v2(带热词) vs fun-asr(热词若支持则带)；探针段只跑 paraformer-v2。
"""
import os, sys, json, time, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _key import load_key

SAMPLE_DIR = os.path.join(ROOT, "音频", "样本")
RAW_DIR = os.path.join(ROOT, "转写", "样本")
os.makedirs(RAW_DIR, exist_ok=True)

BASE = "https://dashscope.aliyuncs.com"
KEY, SRC = load_key()
H = {"Authorization": f"Bearer {KEY}"}

VOCAB_ID = None
_vf = os.path.join(ROOT, "课件对齐", "vocabulary_id.json")
if os.path.exists(_vf):
    VOCAB_ID = json.load(open(_vf, encoding="utf-8"))["vocabulary_id"]

def upload_oss(path, model="paraformer-v2"):
    r = requests.get(f"{BASE}/api/v1/uploads", params={"action": "getPolicy", "model": model},
                     headers=H, timeout=30)
    r.raise_for_status()
    policy = r.json()["data"]
    fname = os.path.basename(path)
    key = f"{policy['upload_dir']}/{fname}"
    form = {
        "OSSAccessKeyId": policy["oss_access_key_id"],
        "Signature": policy["signature"],
        "policy": policy["policy"],
        "x-oss-object-acl": policy.get("x_oss_object_acl", "private"),
        "success_action_status": "200",
        "key": key,
    }
    if policy.get("x_oss_forbid_overwrite"):
        form["x-oss-forbid-overwrite"] = policy["x_oss_forbid_overwrite"]
    with open(path, "rb") as fh:
        resp = requests.post(policy["upload_host"], data=form,
                             files={"file": (fname, fh)}, timeout=600)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"上传失败 {resp.status_code}: {resp.text[:300]}")
    return f"oss://{key}"

def submit(model, oss_url, use_vocab):
    body = {"model": model, "input": {"file_urls": [oss_url]}, "parameters": {}}
    if use_vocab and VOCAB_ID:
        body["parameters"]["vocabulary_id"] = VOCAB_ID
    if not body["parameters"]:
        body.pop("parameters")
    r = requests.post(f"{BASE}/api/v1/services/audio/asr/transcription",
                      headers={**H, "X-DashScope-Async": "enable",
                               "X-DashScope-OssResourceResolve": "enable"},
                      json=body, timeout=30)
    d = r.json()
    if r.status_code != 200 or d.get("output", {}).get("task_id") is None:
        raise RuntimeError(f"提交失败[{model}] {r.status_code}: {json.dumps(d, ensure_ascii=False)[:400]}")
    return d["output"]["task_id"]

def poll(task_id, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(f"{BASE}/api/v1/tasks/{task_id}", headers=H, timeout=30).json()
        st = r.get("output", {}).get("task_status")
        if st in ("SUCCEEDED", "FAILED"):
            return r
        time.sleep(10)
    raise TimeoutError(task_id)

JOBS = [  # (样本名, 文件, 模型, 是否带热词)
    ("A_L13_微调原理", "A_L13_微调原理.flac", "paraformer-v2", True),
    ("A_L13_微调原理", "A_L13_微调原理.flac", "fun-asr", False),
    ("B_L06_AI编程", "B_L06_AI编程.flac", "paraformer-v2", True),
    ("B_L06_AI编程", "B_L06_AI编程.flac", "fun-asr", False),
    ("C_L20_RAG", "C_L20_RAG.flac", "paraformer-v2", True),
    ("C_L20_RAG", "C_L20_RAG.flac", "fun-asr", False),
    ("P1_往期2023", "P1_往期2023.flac", "paraformer-v2", True),
    ("P2_往期2025", "P2_往期2025.flac", "paraformer-v2", True),
]

def main():
    tasks = {}
    for name, fname, model, uv in JOBS:
        path = os.path.join(SAMPLE_DIR, fname)
        tag = f"{name}__{model}"
        out_json = os.path.join(RAW_DIR, f"{tag}.result.json")
        if os.path.exists(out_json):
            print(f"跳过(已有结果): {tag}")
            continue
        try:
            url = upload_oss(path, model)
            print(f"上传OK {tag}  {os.path.getsize(path)/1048576:.1f}MB")
            tid = submit(model, url, uv)
            tasks[tag] = tid
            print(f"  提交任务 {tid}")
        except Exception as e:
            print(f"!! {tag}: {e}")

    print(f"\n共提交 {len(tasks)} 个任务，开始轮询…")
    for tag, tid in tasks.items():
        try:
            res = poll(tid)
            st = res["output"]["task_status"]
            out_json = os.path.join(RAW_DIR, f"{tag}.task.json")
            json.dump(res, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            if st == "SUCCEEDED":
                turl = res["output"]["results"][0].get("transcription_url")
                sub = res["output"]["results"][0].get("subtask_results")
                data = requests.get(turl, timeout=60).json() if turl else sub
                json.dump(data, open(os.path.join(RAW_DIR, f"{tag}.result.json"), "w",
                                     encoding="utf-8"), ensure_ascii=False, indent=1)
                cd = res["output"]["results"][0].get("content_duration")
                print(f"DONE {tag}  content_duration={cd}s  -> {tag}.result.json")
            else:
                print(f"FAILED {tag}: {json.dumps(res['output'], ensure_ascii=False)[:400]}")
        except Exception as e:
            print(f"!! 轮询 {tag}: {e}")

if __name__ == "__main__":
    main()
