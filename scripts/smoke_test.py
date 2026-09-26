# -*- coding: utf-8 -*-
"""冒烟测试：验证 DashScope key 是否已解锁（文本 + paraformer-v2 各一发）。"""
import sys, json, time, requests

sys.path.insert(0, "scripts")
from _key import load_key

KEY, _ = load_key()
H = {"Authorization": f"Bearer {KEY}"}
BASE = "https://dashscope.aliyuncs.com"


def test_text():
    r = requests.post(
        f"{BASE}/compatible-mode/v1/chat/completions",
        headers=H,
        json={"model": "qwen-turbo", "messages": [{"role": "user", "content": "回复OK"}]},
        timeout=60,
    )
    ok = r.status_code == 200
    print(f"[text] qwen-turbo: {'PASS' if ok else 'FAIL'} {'' if ok else r.text[:120]}")
    return ok


def upload_oss(path):
    r = requests.get(
        f"{BASE}/api/v1/uploads",
        params={"action": "getPolicy", "model": "paraformer-v2"},
        headers=H, timeout=30,
    )
    p = r.json()["data"]
    key = f"{p['upload_dir']}/smoke.wav"
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
        resp = requests.post(p["upload_host"], data=form, files={"file": ("smoke.wav", fh)}, timeout=120)
    if resp.status_code != 200:
        print(f"[upload] FAIL {resp.status_code} {resp.text[:150]}")
        return None
    print("[upload] PASS 200")
    return f"oss://{key}"


def test_asr(url):
    r = requests.post(
        f"{BASE}/api/v1/services/audio/asr/transcription",
        headers={**H, "X-DashScope-Async": "enable", "X-DashScope-OssResourceResolve": "enable"},
        json={"model": "paraformer-v2", "input": {"file_urls": [url]}}, timeout=30,
    )
    tid = r.json()["output"]["task_id"]
    for _ in range(30):
        w = requests.get(f"{BASE}/api/v1/tasks/{tid}", headers=H, timeout=30).json()["output"]
        st = w["task_status"]
        if st in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(4)
    if st == "SUCCEEDED":
        d = requests.get(w["results"][0]["transcription_url"], timeout=60).json()
        print(f"[asr] paraformer-v2: PASS 转写={d['transcripts'][0]['text'][:40]}")
        return True
    print(f"[asr] paraformer-v2: FAIL {st} {w.get('code')} {str(w.get('message'))[:120]}")
    return False


if __name__ == "__main__":
    t1 = test_text()
    url = upload_oss("tmp/tiny.wav")
    t2 = test_asr(url) if url else False
    print("=== 全部通过 ===" if (t1 and t2) else "=== 仍有失败，可能未到生效时间 ===")
    sys.exit(0 if (t1 and t2) else 1)
