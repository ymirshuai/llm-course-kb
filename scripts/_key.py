# -*- coding: utf-8 -*-
"""共享工具：DASHSCOPE_API_KEY 加载。项目内不落密钥，查找顺序：
1. 环境变量 DASHSCOPE_API_KEY
2. 环境变量 COURSE_KB_KEY_FILE 指向的 JSON 文件
3. 项目根 .secrets/Key.json（需自行创建，已被 .gitignore 排除）
4. Windows 注册表用户/系统级环境变量（本机已配置的情况）
"""
import os, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _from_file(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
        k = d.get("DASHSCOPE_API_KEY")
        return (k, f"file:{path}") if k else None
    except Exception:
        return None


def load_key():
    k = os.environ.get("DASHSCOPE_API_KEY")
    if k:
        return k, "env"
    kf = os.environ.get("COURSE_KB_KEY_FILE")
    if kf and os.path.exists(kf):
        r = _from_file(kf)
        if r:
            return r
    local = os.path.join(ROOT, ".secrets", "Key.json")
    if os.path.exists(local):
        r = _from_file(local)
        if r:
            return r
    try:
        import winreg
        for hive, name in [(winreg.HKEY_CURRENT_USER, "Environment"),
                           (winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")]:
            try:
                key = winreg.OpenKey(hive, name)
                v, _ = winreg.QueryValueEx(key, "DASHSCOPE_API_KEY")
                winreg.CloseKey(key)
                if v and v.strip():
                    return v.strip(), "registry"
            except OSError:
                continue
    except ImportError:
        pass
    raise RuntimeError(
        "未找到 DASHSCOPE_API_KEY。请任选其一：\n"
        "  1) 设置环境变量 DASHSCOPE_API_KEY\n"
        "  2) 创建 项目根/.secrets/Key.json，内容 {\"DASHSCOPE_API_KEY\": \"sk-...\"}\n"
        "  3) 设置环境变量 COURSE_KB_KEY_FILE 指向你的 Key.json")
