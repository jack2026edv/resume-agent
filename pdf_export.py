"""
pdf_export.py —— 把 Markdown 格式的简历导出为 PDF 文件

使用 reportlab 库：
- 字体用 reportlab 内置的中文字体 STSong-Light（Adobe CID 字体），
  不需要下载任何字体文件，对中文简历开箱即用；
- 用 Platypus（reportlab 的排版引擎）把简历排成 A4 一页纸的版式；
- 支持在页首右侧插入证件照（左文右图，还原常见中文简历模板）。

本文件为【第 4 步】完成的版本，包含两套渲染：
    json_to_pdf(data, photo_path)   —— 当前主流程，AI 填 JSON、程序排固定模板
    markdown_to_pdf(md_text, photo_path) —— 旧版兼容入口

版式原则（按用户要求）：
- 所有文字一律用黑色，不用白字、不用彩色字；
- 姓名下方先放“求职意向”，让 HR 一眼知道投什么岗位；
- 右上角永远保留证件照位置：上传了照片就显示照片，没上传就显示占位框；
- 用浅灰模块标题、分隔线、双栏信息网格把版面撑得饱满但不花哨。
"""

import re
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, Image as RLImage,
)

# ---------- 注册内置中文字体（模块加载时执行一次即可） ----------
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
FONT = "STSong-Light"

# ---------- 配色（文字统一黑色，颜色只用于线条和浅色底） ----------
BLACK = HexColor("#000000")
INK = BLACK                      # 所有文字
LINE_DARK = HexColor("#2F3B4A")  # 页首分隔线
LINE = HexColor("#AAB4C0")       # 细边框
SOFT_BG = HexColor("#F1F3F6")    # 模块标题浅灰底
BOX_BG = HexColor("#F7F8FA")        # 自我评价等信息框底色
ACCENT = HexColor("#1F3A5F")     # 左侧强调竖线（不是文字颜色）

# 旧版 markdown_to_pdf 仍会引用这两个名字，保留为黑色/线条色
PRIMARY = BLACK
GRAY = BLACK

# ---------- 排版样式 ----------
STYLE_NAME = ParagraphStyle(
    "name", fontName=FONT, fontSize=24, leading=28,
    alignment=1, textColor=BLACK, spaceAfter=2,
)
STYLE_NAME_L = ParagraphStyle("name_l", parent=STYLE_NAME, alignment=0)
STYLE_CONTACT = ParagraphStyle(
    "contact", fontName=FONT, fontSize=9.5, leading=13,
    alignment=1, textColor=BLACK, spaceAfter=6,
)
STYLE_CONTACT_L = ParagraphStyle("contact_l", parent=STYLE_CONTACT,
                                 alignment=0, spaceAfter=2)
STYLE_H2 = ParagraphStyle(  # 模块大标题：浅灰底 + 黑字，整份简历统一
    "h2", fontName=FONT, fontSize=11.5, leading=15,
    textColor=BLACK, backColor=SOFT_BG,
    borderPadding=(4, 6, 4, 6),
    spaceBefore=10, spaceAfter=5,
)
STYLE_H3 = ParagraphStyle(  # 经历标题（无 " | " 分隔时的备用样式）
    "h3", fontName=FONT, fontSize=10.5, leading=14,
    textColor=BLACK, spaceBefore=5, spaceAfter=1,
)
# 三栏小标题的单元格样式：全部黑字，只靠粗细/位置区分层级
STYLE_H3_LEFT = ParagraphStyle("h3l", parent=STYLE_H3, spaceBefore=0, spaceAfter=0)
STYLE_H3_MID = ParagraphStyle("h3m", parent=STYLE_H3, alignment=1,
                              spaceBefore=0, spaceAfter=0)
STYLE_H3_RIGHT = ParagraphStyle("h3r", parent=STYLE_H3, alignment=2,
                                textColor=BLACK, spaceBefore=0, spaceAfter=0)
STYLE_BODY = ParagraphStyle(
    "body", fontName=FONT, fontSize=10.2, leading=15.5,
    textColor=BLACK, spaceAfter=1,
)
STYLE_BULLET = ParagraphStyle(
    "bullet", parent=STYLE_BODY, leftIndent=13, bulletIndent=2,
    firstLineIndent=0, spaceAfter=2.5,
)


def _inline(text: str) -> str:
    """处理行内格式：先把 XML 特殊字符转义（reportlab 的 Paragraph 用类 HTML 语法），
    再把 Markdown 的 **加粗** 转成 <b>加粗</b>。"""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text


def _h3_flowable(content: str):
    """经历标题行的排版：
    - 含 " | " 分隔（如 "2025.03-2025.06 | 某某公司 | 实习生"）→ 排成左|中|右三栏；
    - 不含分隔 → 普通小标题。"""
    parts = [p.strip() for p in content.split("|")]
    if len(parts) < 2:
        return Paragraph(_inline(content), STYLE_H3)
    left = parts[0]
    right = parts[-1]
    middle = " | ".join(parts[1:-1]) if len(parts) > 2 else ""
    available = A4[0] - 4 * cm  # 页面可用宽度（A4 宽 - 左右边距）
    table = Table(
        [[
            Paragraph(_inline(left), STYLE_H3_LEFT),
            Paragraph(_inline(middle), STYLE_H3_MID),
            Paragraph(_inline(right), STYLE_H3_RIGHT),
        ]],
        colWidths=[available * 0.30, available * 0.45, available * 0.25],
    )
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _photo_flowable(photo_path, max_w=2.6 * cm, max_h=3.5 * cm):
    """读取证件照，等比缩放到一寸照大小以内。
    读取失败返回 None（照片坏了也不影响正文导出）。"""
    try:
        from PIL import Image as PILImage  # 延迟导入：不用照片时无需 PIL
        with PILImage.open(str(photo_path)) as im:
            w, h = im.size
        scale = min(max_w / w, max_h / h)
        return RLImage(str(photo_path), width=w * scale, height=h * scale)
    except Exception:
        return None


def markdown_to_pdf(md_text: str, photo_path=None) -> bytes:
    """把简历 Markdown 渲染成 PDF，返回字节内容。
    photo_path：可选的证件照文件路径；有照片时页首排成"左文右图"。"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm,
        title="简历", author="简历助手 Agent",
    )

    story = []    # reportlab 把所有排版元素叫 flowable，按顺序放进 story
    header = []   # 页首区域（姓名 + 联系方式）：有照片时要包进"左文右图"的表格
    seen_section = False  # 是否已遇到第一个 "## 模块标题"

    def flush_header():
        """把页首区域输出到 story：有照片 → 左文右图表格；没照片 → 直接居中排列。"""
        if not header:
            return
        photo = _photo_flowable(photo_path) if photo_path else None
        if photo is not None:
            available = A4[0] - 4 * cm
            # 注意：必须传 header 的副本（header[:]），
            # 否则后面的 header.clear() 会把表格里已引用的内容一并清空
            t = Table([[header[:], photo]],
                      colWidths=[available - 3.2 * cm, 3.2 * cm])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),  # 照片靠右
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))
        else:
            story.extend(header)
        header.clear()

    for raw in md_text.splitlines():
        line = raw.strip()

        if not seen_section:
            # —— 页首区域（第一个 ## 之前）——
            if line.startswith("## "):
                seen_section = True
                flush_header()
                story.append(Paragraph(_inline(line[3:]), STYLE_H2))
            elif not line:
                continue  # 页首的空行忽略，保持头部紧凑
            elif line.startswith("# "):
                style = STYLE_NAME_L if photo_path else STYLE_NAME
                header.append(Paragraph(_inline(line[2:]), style))
            else:
                style = STYLE_CONTACT_L if photo_path else STYLE_CONTACT
                header.append(Paragraph(_inline(line), style))
            continue

        # —— 正文区域 ——
        if not line:
            story.append(Spacer(1, 3))
        elif line.startswith("### "):
            story.append(_h3_flowable(line[4:]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline(line[3:]), STYLE_H2))
        elif line.startswith("# "):
            story.append(Paragraph(_inline(line[2:]), STYLE_H2))  # 正文中的一号标题按模块标题处理
        elif set(line) <= {"-", "="} and len(line) >= 3:
            story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY))
        elif line.startswith(("- ", "* ")):
            story.append(Paragraph("• " + _inline(line[2:]), STYLE_BULLET))
        else:
            story.append(Paragraph(_inline(line), STYLE_BODY))

    flush_header()  # 没有任何 ## 模块时，也要把页首输出
    doc.build(story)
    return buffer.getvalue()


# ======================================================================
# 以下是【第 4 步·新版】的 JSON 渲染：模板固定，AI 只填内容，程序负责排版
# ======================================================================

STYLE_INFO = ParagraphStyle(  # 页首基本信息网格（两栏，黑字）
    "info", fontName=FONT, fontSize=9.3, leading=14, textColor=BLACK,
)
STYLE_COURSES = ParagraphStyle(  # 主修课程行
    "courses", parent=STYLE_BODY, fontSize=9.3, textColor=BLACK, spaceAfter=2,
)
STYLE_JOB = ParagraphStyle(  # 姓名下方的求职意向
    "job", fontName=FONT, fontSize=10.5, leading=15,
    textColor=BLACK, spaceBefore=5,
)
STYLE_PHOTO_LABEL = ParagraphStyle(  # 没上传照片时的占位框文字
    "photo_label", fontName=FONT, fontSize=11, leading=16,
    alignment=1, textColor=BLACK,
)
STYLE_PHOTO_HINT = ParagraphStyle(
    "photo_hint", fontName=FONT, fontSize=7.5, leading=10,
    alignment=1, textColor=BLACK,
)

PHOTO_W = 2.5 * cm   # 一寸照宽度
PHOTO_H = 3.4 * cm   # 一寸照高度


def _v(x) -> str:
    """把 JSON 字段值变成安全文本：None / "null" / 空串 都视为"未填写"。"""
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() in ("null", "none") else s


def _entry_row(start, end, middle, right):
    """经历的三栏标题行：起止时间 | 单位 | 身份（复用 markdown 版的三栏排版）。"""
    period = " - ".join(p for p in (_v(start), _v(end)) if p)
    return _h3_flowable(" | ".join([period, _v(middle), _v(right)]))


def _photo_or_placeholder(photo_path):
    """返回右上角的照片位：有照片放照片，没照片放带边框的“证件照”占位框。"""
    photo = _photo_flowable(photo_path, max_w=PHOTO_W - 0.16 * cm,
                            max_h=PHOTO_H - 0.16 * cm) if photo_path else None
    if photo is not None:
        table = Table([[photo]], colWidths=[PHOTO_W], rowHeights=[PHOTO_H])
        table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return table

    box = Table(
        [[Paragraph("证 件 照", STYLE_PHOTO_LABEL)],
         [Paragraph("（可上传）", STYLE_PHOTO_HINT)]],
        colWidths=[PHOTO_W],
        rowHeights=[PHOTO_H * 0.62, PHOTO_H * 0.38],
    )
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FAFBFC")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return box


def _two_col_bullets(items: list, available: float):
    """把技能/证书排成两栏，视觉上更饱满，且全部黑字。"""
    rows = []
    for i in range(0, len(items), 2):
        left = Paragraph("• " + _inline(items[i]), STYLE_BULLET)
        right = (Paragraph("• " + _inline(items[i + 1]), STYLE_BULLET)
                 if i + 1 < len(items) else Paragraph("", STYLE_BULLET))
        rows.append([left, right])
    table = Table(rows, colWidths=[available / 2, available / 2])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def _summary_box(text: str, available: float):
    """自我评价放在浅底框里，避免整页看起来空。"""
    table = Table([[Paragraph(_inline(text), STYLE_BODY)]], colWidths=[available])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BOX_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def json_to_pdf(data: dict, photo_path=None) -> bytes:
    """把简历 JSON 渲染成 PDF，返回字节内容。

    版式（从上到下）：
      姓名 + 求职意向 + 两栏基本信息          右上角证件照/占位框
      ————————————— 分隔线 —————————————
      教育背景 / 实习项目 / 校园经历 / 技能证书 / 自我评价
    所有文字为黑色。
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.4 * cm, bottomMargin=1.5 * cm,
        title="简历", author="简历助手 Agent",
    )
    story = []
    available = A4[0] - 4 * cm
    basic = data.get("basic") or {}

    # ---------- 页首：左边文字，右边永远有照片位 ----------
    name = _v(basic.get("name")) or "个人简历"
    left_blocks = [
        Paragraph(_inline(name),
                  ParagraphStyle("nm", parent=STYLE_NAME_L, fontSize=23, leading=27)),
    ]

    intention = _v(data.get("job_intention"))
    if intention:
        left_blocks.append(Paragraph("求职意向：" + _inline(intention), STYLE_JOB))

    fields = []
    for label, key in [("电话", "phone"), ("邮箱", "email"), ("出生年月", "birth"),
                       ("政治面貌", "politics"), ("现居地", "city"), ("身高", "height"),
                       ("学校", "school"), ("学历", "degree")]:
        val = _v(basic.get(key))
        if val:
            fields.append(f"{label}：{val}")

    text_width = available - PHOTO_W - 0.55 * cm
    if fields:
        half = (len(fields) + 1) // 2
        rows = []
        for i in range(half):
            l_cell = Paragraph(_inline(fields[i]), STYLE_INFO)
            r_cell = (Paragraph(_inline(fields[i + half]), STYLE_INFO)
                      if i + half < len(fields) else Paragraph("", STYLE_INFO))
            rows.append([l_cell, r_cell])
        grid = Table(rows, colWidths=[text_width / 2, text_width / 2])
        grid.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        left_blocks.append(Spacer(1, 5))
        left_blocks.append(grid)

    header_table = Table([[left_blocks, _photo_or_placeholder(photo_path)]],
                         colWidths=[text_width, PHOTO_W + 0.55 * cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.2, color=LINE_DARK,
                            spaceBefore=8, spaceAfter=4))

    # ---------- 各模块 ----------
    def banner(text):
        story.append(Paragraph(_inline(text), STYLE_H2))

    def bullets(items):
        for it in items:
            s = _v(it)
            if s:
                story.append(Paragraph("• " + _inline(s), STYLE_BULLET))

    if data.get("edu"):
        banner("教育背景")
        for e in data["edu"]:
            e = e or {}
            degree = _v(e.get("degree"))
            major = _v(e.get("major")) + (f"（{degree}）" if degree else "")
            story.append(_entry_row(e.get("start"), e.get("end"),
                                    e.get("school"), major))
            courses = [_v(c) for c in (e.get("courses") or []) if _v(c)]
            if courses:
                story.append(Paragraph(_inline("主修课程：" + "、".join(courses)),
                                       STYLE_COURSES))

    if data.get("work"):
        banner("实习 / 项目经历")
        for w in data["work"]:
            w = w or {}
            story.append(_entry_row(w.get("start"), w.get("end"),
                                    w.get("company"), w.get("role")))
            bullets(w.get("bullets") or [])

    if data.get("campus"):
        banner("校园经历")
        for c in data["campus"]:
            c = c or {}
            story.append(_entry_row(c.get("start"), c.get("end"),
                                    c.get("org"), c.get("role")))
            bullets(c.get("bullets") or [])

    skills = [_v(s) for s in (data.get("skills") or []) if _v(s)]
    certs = [_v(c) for c in (data.get("certs") or []) if _v(c)]
    if skills or certs:
        banner("技能证书")
        if skills:
            story.append(Paragraph("专业技能", STYLE_H3))
            story.append(_two_col_bullets(skills, available))
        if certs:
            story.append(Paragraph("证书 / 语言", STYLE_H3))
            story.append(_two_col_bullets(certs, available))

    if _v(data.get("summary")):
        banner("自我评价")
        story.append(_summary_box(_v(data["summary"]), available))

    # 多页时加页码（小字、黑字）
    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(BLACK)
        canvas.drawCentredString(A4[0] / 2, 0.9 * cm, f"第 {_doc.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
