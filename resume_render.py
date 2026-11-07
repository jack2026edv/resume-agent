"""
resume_render.py —— 简历 JSON 的解析与预览渲染

第 4 步新架构：AI 只输出结构化 JSON（见 prompts.py 的 RESUME_FILL_JSON_PROMPT），
这个模块负责：
  parse_resume_json(text)  —— 把模型输出解析成 dict（带容错和字段补齐）
  json_to_markdown(data)   —— 把 JSON 渲染成 Markdown（页面预览 + .md 下载用）

PDF 渲染在 pdf_export.py 的 json_to_pdf()。
"""

import json


def _limit_summary(text: str, limit: int = 120) -> str:
    '''清理空白并把自我评价控制在 120 个字符以内，尽量不截断半句话。'''
    clean = ' '.join(str(text).split())
    if len(clean) <= limit:
        return clean
    window = clean[:limit]
    for mark in ('。', '！', '？', '；'):
        pos = window.rfind(mark)
        if pos >= int(limit * 0.72):
            return window[:pos + 1]
    base = window.rstrip('，,、；;：: 。')[:limit - 1].rstrip()
    return (base or window[:limit - 1]) + '。'


def parse_resume_json(text: str) -> dict:
    """把模型的 JSON 输出解析成 dict。

    容错处理：
    - 剥掉 ```json ... ``` 代码围栏（模型偶尔不听话会加）；
    - 截取第一个 { 到最后一个 } 之间的内容（容忍开头结尾的废话）；
    - 补齐缺失的顶层字段，保证后续渲染不炸。
    解析失败抛 ValueError（附带原文片段，方便排查）。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 去掉首行 ```json 和结尾的 ```
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("输出里没有 JSON 对象：" + text[:120])
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败：{e}；原文片段：{cleaned[start:start + 120]}")
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层不是对象")

    # 补齐顶层字段
    if isinstance(data.get('summary'), str):
        data['summary'] = _limit_summary(data['summary'])
    if not isinstance(data.get("basic"), dict):
        data["basic"] = {}
    for key in ("edu", "work", "campus", "skills", "certs",
                "missing_fields", "questions_to_user"):
        if not isinstance(data.get(key), list):
            data[key] = []
    if not isinstance(data.get("summary"), str):
        data["summary"] = ""
    if not isinstance(data.get("job_intention"), str):
        data["job_intention"] = ""
    return data


def _v(x) -> str:
    """把 JSON 字段值变成安全文本：None / "null" / 空串 都视为"未填写"。"""
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() in ("null", "none") else s


def _period(start, end) -> str:
    """拼接起止时间：'2022.09 - 2026.06'；只有一个就写一个；都没有就空。"""
    return " - ".join(p for p in (_v(start), _v(end)) if p)


def json_to_markdown(data: dict) -> str:
    """把简历 JSON 渲染成 Markdown 文本（用于页面预览和 .md 下载）。
    未填写的字段/模块一律不出现。"""
    basic = data.get("basic") or {}
    lines = []

    # —— 页首：姓名 + 基本信息行 ——
    lines.append("# " + (_v(basic.get("name")) or "个人简历"))
    info = []
    for label, key in [("电话", "phone"), ("邮箱", "email"), ("出生年月", "birth"),
                       ("政治面貌", "politics"), ("现居地", "city"), ("身高", "height")]:
        val = _v(basic.get(key))
        if val:
            info.append(f"{label}：{val}")
    if info:
        lines.append(" | ".join(info))
    intention = _v(data.get("job_intention"))
    if intention:
        lines.append("")
        lines.append("**求职意向：** " + intention)

    lines.append("")

    # —— 教育背景 ——
    if data["edu"]:
        lines.append("## 教育背景")
        for e in data["edu"]:
            e = e or {}
            degree = _v(e.get("degree"))
            major = _v(e.get("major")) + (f"（{degree}）" if degree else "")
            lines.append("### " + " | ".join(
                [_period(e.get("start"), e.get("end")), _v(e.get("school")), major]))
            courses = [_v(c) for c in (e.get("courses") or []) if _v(c)]
            if courses:
                lines.append("- 主修课程：" + "、".join(courses))
        lines.append("")

    # —— 实习 / 项目经历 ——
    if data["work"]:
        lines.append("## 实习 / 项目经历")
        for w in data["work"]:
            w = w or {}
            lines.append("### " + " | ".join(
                [_period(w.get("start"), w.get("end")), _v(w.get("company")), _v(w.get("role"))]))
            for b in (w.get("bullets") or []):
                if _v(b):
                    lines.append("- " + _v(b))
        lines.append("")

    # —— 校园经历 ——
    if data["campus"]:
        lines.append("## 校园经历")
        for c in data["campus"]:
            c = c or {}
            lines.append("### " + " | ".join(
                [_period(c.get("start"), c.get("end")), _v(c.get("org")), _v(c.get("role"))]))
            for b in (c.get("bullets") or []):
                if _v(b):
                    lines.append("- " + _v(b))
        lines.append("")

    # —— 技能证书 ——
    skill_items = [_v(s) for s in data["skills"] if _v(s)]
    cert_items = [_v(c) for c in data["certs"] if _v(c)]
    if skill_items or cert_items:
        lines.append("## 技能证书")
        lines += ["- " + s for s in skill_items]
        lines += ["- " + c for c in cert_items]
        lines.append("")

    # —— 自我评价 ——
    if _v(data.get("summary")):
        lines.append("## 自我评价")
        lines.append(_v(data["summary"]))

    return "\n".join(lines).strip() + "\n"
