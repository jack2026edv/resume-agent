"""
app.py —— 简历助手 Agent 的主程序（Streamlit 网页应用）

这是整个项目唯一需要"运行"的文件。
运行方法（在项目文件夹的终端里输入）：
    streamlit run app.py

当前进度：【第 4 步】JD 解析 + 简历模板填充（JSON）+ 多轮修改 + 导出 PDF + 模拟面试。

页面结构：
  侧边栏      —— 设置、清空对话、JD 粘贴区、证件照上传、生成简历按钮
  标签页 1    —— 对话采集（AI 顾问采访你）
  标签页 2    —— 我的简历（生成 / 修改 / 下载 PDF）
  标签页 3    —— 模拟面试（AI 面试官出题 + 点评 + STAR 示范）
"""

import json

import streamlit as st

from llm_client import chat, is_configured, LLMError
from prompts import (
    SYSTEM_PROMPT, OPENING_MESSAGE,
    JD_PARSE_PROMPT, RESUME_FILL_JSON_PROMPT, RESUME_REVISE_PROMPT,
    INTERVIEW_PROMPT,
)
from session_store import (
    save_session, load_session, clear_session,
    save_photo, get_photo_path, delete_photo,
    is_valid_session_id, new_session_id,
)
from resume_render import parse_resume_json, json_to_markdown
from pdf_export import json_to_pdf

# ---------- 页面基本设置（必须是第一个 st 命令） ----------
st.set_page_config(page_title="应届生简历助手", page_icon="📄", layout="centered")
st.title("📄 应届生简历助手")
st.caption("对话采集信息 → JD 解析 → 模板填充简历 → 模拟面试 → 导出 PDF")


def get_page_session_id() -> str:
    """给每个浏览器分配独立编号，并保存在网址参数里供刷新后恢复。"""
    current = st.query_params.get("session_id")
    if isinstance(current, list):
        current = current[0] if current else None
    if current and is_valid_session_id(current):
        return current
    session_id = new_session_id()
    st.query_params["session_id"] = session_id
    return session_id


SESSION_ID = get_page_session_id()

# ---------- 检查密钥配置 ----------
if not is_configured():
    st.warning("还没有配置 API 密钥，程序无法运行。", icon="🔑")
    st.markdown(
        """
        请按以下步骤配置：
        1. 打开项目文件夹里的 `.env` 文件
        2. 把 `API_KEY=` 后面的内容换成你的密钥并保存
        3. 回到本页面，点右上角菜单 → **Rerun**（或按 `R`）刷新
        """
    )
    st.stop()  # st.stop()：脚本到这里就停下，不再往下执行

# ---------- 初始化会话状态（含"刷新不丢"的存档恢复） ----------
if "messages" not in st.session_state:
    saved = load_session(SESSION_ID)
    if saved and saved.get("messages"):
        st.session_state.messages = saved["messages"]
        st.session_state.jd_text = saved.get("jd_text", "")
        st.session_state.jd_analysis = saved.get("jd_analysis", "")
        st.session_state.resume_json = saved.get("resume_json")
        st.session_state.interview_messages = saved.get("interview_messages", [])
        st.toast("已自动恢复上次的记录", icon="💾")
    else:
        # 全新开始：先把 AI 的开场白放进历史（prompts.py 里的固定文案，不花 API 费用）
        st.session_state.messages = [{"role": "assistant", "content": OPENING_MESSAGE}]
        st.session_state.jd_text = ""
        st.session_state.jd_analysis = ""
        st.session_state.resume_json = None
        st.session_state.interview_messages = []

# 兜底：升级代码之前就已打开的页面（老会话）可能缺少新字段，
# 逐个补上默认值，避免 KeyError
for _key, _default in [("jd_text", ""), ("jd_analysis", ""),
                       ("resume_json", None), ("interview_messages", [])]:
    if _key not in st.session_state:
        st.session_state[_key] = _default


def persist():
    """把当前会话数据写入本地文件（自动存档）。任何数据变化后都要调用。"""
    save_session(SESSION_ID, {
        "messages": st.session_state.messages,
        "jd_text": st.session_state.jd_text,
        "jd_analysis": st.session_state.jd_analysis,
        "resume_json": st.session_state.resume_json,
        "interview_messages": st.session_state.interview_messages,
    })


def transcript_text() -> str:
    """把对话历史拼成纯文本（生成简历 / 面试素材时用）。"""
    return "\n".join(
        ("用户" if m["role"] == "user" else "顾问") + "：" + m["content"]
        for m in st.session_state.messages
    )


def generate_resume():
    """简历生成主流程：JD 解析（如有 JD）→ AI 填充固定 JSON 模板 → 追问闭环。
    失败会抛出 LLMError，由调用方捕获并展示。"""
    jd = st.session_state.jd_text.strip()

    # 第 1 步：有 JD 就先做解析，提取岗位关键词（temperature 调低，输出更稳定）
    if jd:
        with st.spinner("正在解析 JD，提取岗位关键词…"):
            st.session_state.jd_analysis = chat(
                [
                    {"role": "system", "content": JD_PARSE_PROMPT},
                    {"role": "user", "content": jd},
                ],
                temperature=0.3,
            )
    else:
        st.session_state.jd_analysis = ""

    # 第 2 步：AI 只做"内容填充"——把采访信息映射进固定 JSON 模板
    # （json_mode 强制模型输出合法 JSON；排版全部由程序完成，模板钉死）
    parts = ["【对话记录】", transcript_text()]
    if jd:
        parts.append("\n【目标岗位 JD】\n" + jd)
    if st.session_state.jd_analysis:
        parts.append("\n【JD 分析】\n" + st.session_state.jd_analysis)

    with st.spinner("正在提取信息、填充简历模板…"):
        raw = chat(
            [
                {"role": "system", "content": RESUME_FILL_JSON_PROMPT},
                {"role": "user", "content": "\n".join(parts)},
            ],
            temperature=0.3,
            json_mode=True,
        )
        try:
            st.session_state.resume_json = parse_resume_json(raw)
        except ValueError as e:
            raise LLMError(f"模型输出的 JSON 无法解析，请重试一次。{e}")

    # 第 3 步：如果 AI 在 JSON 里留下了追问（questions_to_user），
    # 把它发回对话，形成"补充信息 → 重新生成"的闭环
    questions = [q for q in st.session_state.resume_json.get("questions_to_user", [])
                 if str(q).strip()]
    if questions:
        note = ("简历初稿已生成。为了让内容更完整，我还想跟你确认：\n\n"
                + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
                + "\n\n回复我之后，点侧边栏的「重新生成简历」就会用上这些信息。")
        st.session_state.messages.append({"role": "assistant", "content": note})
    persist()


# ---------- 侧边栏 ----------
with st.sidebar:
    st.header("⚙️ 设置")

    if st.button("🗑️ 清空对话，重新开始", use_container_width=True):
        clear_session(SESSION_ID)
        st.session_state.messages = [{"role": "assistant", "content": OPENING_MESSAGE}]
        st.session_state.jd_text = ""
        st.session_state.jd_analysis = ""
        st.session_state.resume_json = None
        st.session_state.interview_messages = []
        st.rerun()

    st.divider()

    with st.expander("📋 目标岗位 JD（可粘贴）"):
        jd_input = st.text_area(
            "把招聘启事原文粘贴到这里",
            value=st.session_state.jd_text,
            height=180,
            placeholder="例如：\n岗位职责：\n1. ……\n任职要求：\n1. ……",
        )
        if st.button("保存 JD", use_container_width=True):
            st.session_state.jd_text = jd_input.strip()
            persist()
            st.success("已保存！生成简历时会按这份 JD 定制。")

    # 证件照：上传到本地文件，导出 PDF 时自动排进页首右侧
    with st.expander("🖼️ 证件照（可选，放进 PDF）"):
        uploaded = st.file_uploader(
            "上传证件照（jpg / png）",
            type=["jpg", "jpeg", "png"],
            label_visibility="collapsed",
        )
        if uploaded is not None:
            ext = uploaded.name.rsplit(".", 1)[-1].lower()
            save_photo(SESSION_ID, uploaded.getvalue(), ext)
            st.success("照片已保存！")
        photo = get_photo_path(SESSION_ID)
        if photo:
            st.image(str(photo), width=110, caption="当前证件照")
            if st.button("删除照片", use_container_width=True):
                delete_photo(SESSION_ID)
                st.rerun()

    st.divider()

    # —— 生成简历（整个应用的核心动作，放在侧边栏随手可及）——
    btn_label = "🔁 重新生成简历" if st.session_state.resume_json else "✨ 生成我的简历"
    if st.button(btn_label, type="primary", use_container_width=True):
        try:
            generate_resume()
            st.success("生成完成！到【📄 我的简历】标签页查看。")
        except LLMError as e:
            st.error(f"生成失败：{e}")
    st.caption("流程：解析 JD → AI 填充固定模板 → 程序排版")

    st.divider()
    st.caption("当前版本：第 4 步（JSON 模板 + 模拟面试）")

# ---------- 三个标签页 ----------
tab_chat, tab_resume, tab_interview = st.tabs(["💬 对话采集", "📄 我的简历", "🎤 模拟面试"])

with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

with tab_resume:
    jd = st.session_state.jd_text.strip()
    if jd:
        st.info(f"已保存 JD（{len(jd)} 字）。生成简历时会先解析 JD 关键词，再按相关度给经历排序。更换 JD 请到侧边栏。", icon="📋")
    else:
        st.warning("还没有粘贴 JD。没有 JD 也能生成通用版简历，但有 JD 会更有针对性（在左侧边栏粘贴）。", icon="💡")

    # ---------- 情况 A：还没生成过简历 → 引导去侧边栏 ----------
    if not st.session_state.resume_json:
        st.markdown(
            "还没有简历。信息采集聊得差不多后：\n\n"
            "- 到**左侧边栏**点击「✨ 生成我的简历」\n"
            "- 或者在对话里直接回复「生成简历」"
        )

    # ---------- 情况 B：已有简历 → 修改 / 下载 / 预览 ----------
    else:
        data = st.session_state.resume_json

        # —— 缺失字段 / 顾问追问提示 ——
        questions = [q for q in (data.get("questions_to_user") or []) if str(q).strip()]
        missing = [m for m in (data.get("missing_fields") or []) if str(m).strip()]
        if questions:
            st.warning(
                "顾问还想跟你确认几个信息（去【对话采集】回复后，点侧边栏「重新生成简历」就会用上）：\n\n"
                + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)),
                icon="❓",
            )
        elif missing:
            st.caption("以下字段尚未提供：" + "、".join(missing))

        # —— 修改意见（st.form：填完点提交才触发运行，输入过程不刷新页面）——
        with st.form("revise_form"):
            instruction = st.text_input(
                "✏️ 想改哪里？",
                placeholder="比如：把项目经历那段重写，突出数据库优化；或者：自我评价写得更自信一点",
            )
            if st.form_submit_button("提交修改", use_container_width=True):
                if instruction.strip():
                    with st.spinner("正在按你的意见修改…"):
                        try:
                            raw = chat(
                                [
                                    {"role": "system", "content": RESUME_REVISE_PROMPT},
                                    {"role": "user", "content":
                                        "【当前简历 JSON】\n"
                                        + json.dumps(data, ensure_ascii=False)
                                        + f"\n\n【修改意见】\n{instruction}"},
                                ],
                                temperature=0.4,
                                json_mode=True,
                            )
                            st.session_state.resume_json = parse_resume_json(raw)
                            persist()
                            st.rerun()
                        except ValueError as e:
                            st.error(f"模型输出的 JSON 无法解析，请换个说法再试。{e}")
                        except LLMError as e:
                            st.error(f"修改失败：{e}")

        # —— 证件照：除了侧边栏，这里也放一个入口，方便边看简历边换照片 ——
        with st.expander("📷 证件照（放在 PDF 右上角）",
                         expanded=not bool(get_photo_path(SESSION_ID))):
            uploaded_resume = st.file_uploader(
                "上传证件照（jpg / png）",
                type=["jpg", "jpeg", "png"],
                key="resume_photo_upload",
            )
            if uploaded_resume is not None:
                ext = uploaded_resume.name.rsplit(".", 1)[-1].lower()
                save_photo(SESSION_ID, uploaded_resume.getvalue(), ext)
                st.success("照片已保存，PDF 会自动更新。")
                st.rerun()
            current_photo = get_photo_path(SESSION_ID)
            if current_photo:
                st.image(str(current_photo), width=110, caption="当前证件照")
                if st.button("删除照片", key="resume_delete_photo"):
                    delete_photo(SESSION_ID)
                    st.rerun()
            else:
                st.caption("没有上传照片时，PDF 右上角会保留一个「证件照（可上传）」占位框。")

        # —— 下载区（Markdown 由 JSON 渲染；PDF 由程序按固定模板排版，含证件照）——
        preview_md = json_to_markdown(data)
        col_md, col_pdf = st.columns(2)
        with col_md:
            st.download_button(
                "⬇️ 下载 Markdown",
                data=preview_md,
                file_name="我的简历.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_pdf:
            try:
                pdf_bytes = json_to_pdf(data, photo_path=get_photo_path(SESSION_ID))
                st.download_button(
                    "⬇️ 下载 PDF 简历",
                    data=pdf_bytes,
                    file_name="我的简历.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF 排版失败（不影响 Markdown 下载）：{e}")
        if get_photo_path(SESSION_ID):
            st.caption("📎 PDF 会包含你的证件照（可在上方或侧边栏更换 / 删除）")
        else:
            st.caption("📎 未上传照片：PDF 右上角会保留证件照占位框，方便你打印后贴照片。")

        st.divider()

        # —— JD 分析报告（让"针对性"看得见）——
        if st.session_state.jd_analysis:
            with st.expander("🔍 JD 分析报告（简历就是按这些关键词定制的）", expanded=False):
                st.markdown(st.session_state.jd_analysis)

        # —— 简历预览 + JSON 源码 ——
        st.markdown(preview_md)
        with st.expander("查看简历 JSON 源码"):
            st.json(data)

with tab_interview:
    st.caption("AI 扮演面试官，结合你的简历和目标岗位 JD 出题；每题给点评和 STAR 示范回答。")

    if not st.session_state.interview_messages:
        st.markdown(
            "面试内容：\n\n"
            "- 通用高频题（自我介绍、优缺点、职业规划……）\n"
            "- 针对你简历和 JD 的深挖题（打破砂锅问到底）\n"
            "- 每答完一题立刻得到点评 + STAR 示范，随时可「结束面试」获得总评"
        )
        if st.button("🎤 开始模拟面试", type="primary"):
            # 有简历 JSON 就用它当面试素材；没有就用顾问的采访记录
            ctx = []
            if st.session_state.resume_json:
                ctx.append("【我的简历 JSON】\n"
                           + json.dumps(st.session_state.resume_json, ensure_ascii=False))
            else:
                ctx.append("【顾问采访记录】\n" + transcript_text())
            if st.session_state.jd_text.strip():
                ctx.append("【目标岗位 JD】\n" + st.session_state.jd_text.strip())
            if st.session_state.jd_analysis:
                ctx.append("【JD 分析】\n" + st.session_state.jd_analysis)
            ctx.append("请开始面试。")
            with st.spinner("面试官准备题目中…"):
                try:
                    first = chat(
                        [
                            {"role": "system", "content": INTERVIEW_PROMPT},
                            {"role": "user", "content": "\n\n".join(ctx)},
                        ],
                        temperature=0.6,
                    )
                    st.session_state.interview_messages = [
                        {"role": "assistant", "content": first}]
                    persist()
                    st.rerun()
                except LLMError as e:
                    st.error(f"开场失败：{e}")
    else:
        # 面试对话记录
        for m in st.session_state.interview_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        with st.form("interview_form", clear_on_submit=True):
            answer = st.text_area(
                "你的回答", height=110,
                placeholder="像真实面试一样作答；也可以直接点下面的「换一题」或「结束面试」",
            )
            c1, c2, c3 = st.columns(3)
            submitted = c1.form_submit_button("提交回答", use_container_width=True)
            skipped = c2.form_submit_button("换一题", use_container_width=True)
            ended = c3.form_submit_button("结束面试并总评", use_container_width=True)

        user_said = None
        if submitted and answer.strip():
            user_said = answer.strip()
        elif skipped:
            user_said = "这题跳过，请直接出下一题。"
        elif ended:
            user_said = "结束面试"
        if user_said:
            st.session_state.interview_messages.append(
                {"role": "user", "content": user_said})
            with st.spinner("面试官思考中…"):
                try:
                    reply = chat(
                        [{"role": "system", "content": INTERVIEW_PROMPT}]
                        + st.session_state.interview_messages,
                        temperature=0.6,
                    )
                    st.session_state.interview_messages.append(
                        {"role": "assistant", "content": reply})
                    persist()
                    st.rerun()
                except LLMError as e:
                    st.error(f"出错了：{e}")

        if st.button("🔄 重新开始面试"):
            st.session_state.interview_messages = []
            persist()
            st.rerun()

# ---------- 聊天输入框（全局，页面底部） ----------
if user_input := st.chat_input("回复顾问的问题；也可以说「生成简历」，或粘贴经历 / JD……"):

    st.session_state.messages.append({"role": "user", "content": user_input})
    with tab_chat:
        with st.chat_message("user"):
            st.markdown(user_input)

    # 如果用户说的是「生成简历」，就走生成流程而不是普通聊天
    wants_resume = any(k in user_input for k in ["生成简历", "做简历", "出简历", "写简历"])

    with tab_chat:
        with st.chat_message("assistant"):
            if wants_resume:
                try:
                    generate_resume()
                    reply = ("简历初稿生成好啦 🎉 点击上方的【📄 我的简历】标签页查看。\n\n"
                             "不满意的地方，在那个页面顶部填修改意见就行；"
                             "换了 JD 的话记得点侧边栏的「重新生成简历」。")
                except LLMError as e:
                    reply = f"生成失败：{e}"
            else:
                # 普通对话：系统提示词 + 完整历史（多轮对话原理见第 3 步注释）
                messages_to_send = (
                    [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.messages
                )
                with st.spinner("顾问正在思考..."):
                    try:
                        reply = chat(messages_to_send)
                    except LLMError as e:
                        reply = f"出错了：{e}"
            st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    persist()
