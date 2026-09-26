# -*- coding: utf-8 -*-
"""赠课时长匹配：把 48 个往期视频按时长对到赠课目录标题上。
交叉验证：同学科的课号顺序应与平台录制时间顺序大体一致。
产出: 索引/赠课映射.json + 控制台对照表
"""
import os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 赠课目录（来自课程平台截图，格式: (课程, 序号, 标题, MM:SS)）----
BONUS = [
    ("原理课", 1, "预训练+微调的训练范式 开源生态和OpenAI的差异详解", "169:09"),
    ("原理课", 2, "探索神经网络的奥妙", "191:21"),
    ("原理课", 3, "揭秘Transformer的真面目-1", "132:29"),
    ("原理课", 4, "揭秘Transformer的真面目-2", "179:54"),
    ("原理课", 5, "多模态领域的Transformer--创意生成的基底原理", "151:12"),
    ("原理课", 6, "揭开文字、人脸、精密零件、无人驾驶的智能识别面纱", "158:18"),
    ("原理课", 7, "探索DALL.E、Stable Diffusion如何编织创意图像的魔法", "156:39"),
    ("原理课", 8, "类Sora模型 解锁动态视觉艺术的密码", "164:52"),
    ("原理课", 9, "人体姿态识别模型-Meta Sapiens", "152:38"),
    ("原理课", 10, "Deepseek性价比之王者后的极致压缩技术MLA", "67:40"),
    ("原理课", 11, "MoE架构在Scaling Law之后继续提升大模型能力", "78:56"),
    ("原理课", 12, "超级引擎:英伟达GPU与CUDA相关的必备知识点", "180:33"),
    ("原理课", 13, "推理模型是如何训练出来的-Deepseek R1与V3", "170:57"),
    ("原理课", 14, "如何训练自动操作电脑和手机的Agent-智谱AutoGLM", "146:39"),
    ("demo课", 1, "文件自动处理AutoGPT", "152:48"),
    ("demo课", 2, "支小助", "161:43"),
    ("demo课", 3, "教育行业核心demo实战1-拍照搜知识点视频", "41:49"),
    ("demo课", 4, "教育行业核心demo实战2-自动化出题与智能组卷", "89:21"),
    ("demo课", 5, "教育行业核心demo实战3-知识点掌握程度检验", "43:18"),
    ("demo课", 6, "财务部门核心demo实战1-AI识别财务表格的数字", "129:33"),
    ("demo课", 7, "财务部门核心demo实战2-AI财务表格准确率的提升", "95:37"),
    ("demo课", 8, "人力资源部门核心demo实战1-数字人培训视频", "96:38"),
    ("demo课", 9, "人力资源部门核心demo实战2-AI培训对练", "44:21"),
    ("demo课", 10, "电商行业核心demo实战1-电商评论区互动助手", "52:47"),
    ("demo课", 11, "泛娱乐内容行业核心demo实战1-AI生成视频工作流", "34:11"),
    ("算法课", 1, "人工智能基础", "133:49"),
    ("算法课", 2, "深度学习-CNN I", "139:08"),
    ("算法课", 3, "深度学习-CNN II", "127:47"),
    ("算法课", 4, "深度学习-RNN/LSTM", "142:05"),
    ("算法课", 5, "深度学习-Transformer【代码】", "136:20"),
    ("算法课", 6, "你的第一个自然语言处理流程", "144:29"),
    ("算法课", 7, "文本表示和语言模型", "117:48"),
    ("算法课", 8, "自然语言处理核心深度网络", "126:05"),
    ("算法课", 9, "Word2vec及企业应用实战", "133:56"),
    ("算法课", 10, "注意力机制及注意力机制在企业落地中的应用", "139:41"),
    ("算法课", 11, "大规模预训练模型", "107:06"),
    ("算法课", 12, "大规模预训练模型在工程应用中的改进", "157:36"),
    ("算法课", 13, "项目一总结:智能客服项目源码解析", "132:57"),
    ("算法课", 14, "大模型必知必会", "202:52"),
    ("算法课", 15, "向量工程和CVP开发流", "193:30"),
    ("算法课", 16, "增强大模型能力", "183:44"),
    ("算法课", 17, "知识图谱技术概览", "193:10"),
    ("算法课", 18, "使用DeepKE-LLM大模型进行知识图谱构建", "193:35"),
    ("算法课", 19, "大模型训练的Pipeline", "192:55"),
    ("算法课", 20, "Retrieval Augmented Generation (RAG)", "220:29"),
    ("算法课", 21, "长度外推的解决方法.SOTA ROPE", "195:30"),
    ("算法课", 22, "多跳问题的解决方法.ReAct", "186:01"),
    ("算法课", 23, "训练框架DeepSpeed强化", "197:25"),
]

def to_sec(ms):
    m, s = ms.split(":")
    return int(m) * 60 + int(s)

def main():
    manifest = json.load(open(os.path.join(ROOT, "索引", "manifest.json"), encoding="utf-8"))
    pool = [v for v in manifest["items"] if v["cohort"] in ("archive", "unknown")]
    lessons = [{"course": c, "no": n, "title": t, "dur": to_sec(d)} for c, n, t, d in BONUS]

    # 全局贪心：所有(视频,课)对按|时长差|升序，两边都未占用才分配
    pairs = []
    for vi, v in enumerate(pool):
        for li, l in enumerate(lessons):
            pairs.append((abs(v["duration_sec"] - l["dur"]), vi, li))
    pairs.sort()
    used_v, used_l, matches = set(), set(), []
    for diff, vi, li in pairs:
        if vi in used_v or li in used_l:
            continue
        used_v.add(vi); used_l.add(li)
        matches.append((vi, li, diff))

    print(f"匹配结果（贪心，容差内才分配；共视频 {len(pool)} / 赠课 {len(lessons)}）\n")
    rows = []
    for vi, li, diff in sorted(matches, key=lambda x: (lessons[x[1]]["course"], lessons[x[1]]["no"])):
        v, l = pool[vi], lessons[li]
        ok = "OK " if diff <= 90 else ("近 " if diff <= 300 else "疑 ")
        print(f"{ok} [{l['course']}{l['no']:>2}] 差{diff:>3}s  平台时间{v['platform_time'][:10] if v['platform_time'] else '  无  '}  {l['title'][:38]}")
        print(f"      -> {v['file'][:44]}  ({v['duration_sec']//60}min)")
        rows.append({"file": v["file"], "duration_sec": v["duration_sec"],
                     "platform_time": v["platform_time"], "diff_sec": diff,
                     "course": l["course"], "lesson_no": l["no"], "lesson_title": l["title"]})

    print("\n--- 未匹配视频 ---")
    for vi in range(len(pool)):
        if vi not in used_v:
            v = pool[vi]
            print(f"  {v['file'][:50]}  {v['duration_sec']//60}min  平台{v['platform_time'][:10] if v['platform_time'] else '?'}")
    print("--- 未匹配赠课 ---")
    for li in range(len(lessons)):
        if li not in used_l:
            l = lessons[li]
            print(f"  [{l['course']}{l['no']:>2}] {l['title']}  ({l['dur']//60}min)")

    # 交叉验证：同一课程内课号 vs 平台时间是否单调
    print("\n--- 时间顺序交叉验证（课号升序时平台时间应大体递增）---")
    by_course = {}
    for r in rows:
        by_course.setdefault(r["course"], []).append(r)
    for c, rs in by_course.items():
        rs.sort(key=lambda r: r["lesson_no"])
        times = [r["platform_time"][:10] if r["platform_time"] else "?" for r in rs]
        inversions = sum(1 for a, b in zip(times, times[1:]) if a > b)
        print(f"  {c}: 逆序对 {inversions} 个  时间跨度 {times[0]} ~ {times[-1]}")

    json.dump(rows, open(os.path.join(ROOT, "索引", "赠课映射.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n已写入 索引/赠课映射.json（{len(rows)} 条）")

if __name__ == "__main__":
    main()
