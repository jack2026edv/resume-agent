"""
llm_client.py —— 大模型 API 调用封装

这个文件负责"打电话"：把我们写好的提示词和聊天记录发给大模型，
然后把模型的回复拿回来。app.py 不需要关心网络请求的细节，
直接调用这里的函数就行。

本文件为【第 2 步】完成的版本：封装了最简单的对话调用 + 中文友好报错。
"""

import os

from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, APIConnectionError, APIError

# ---------- 读取配置 ----------
# load_dotenv() 会读取项目目录下 .env 文件里的每一行 KEY=VALUE，
# 把它们变成"环境变量"，之后用 os.getenv("KEY") 就能读到。
# 这样密钥只存在于 .env 文件里，代码中不出现任何真实密钥，
# 代码上传到 GitHub 也不会泄露密钥。
load_dotenv()


def _get_setting(name: str, default: str = "") -> str:
    """先读本地环境变量，再读 Streamlit Cloud 的 Secrets。

    本地开发时密钥放在 .env；部署到 Streamlit Cloud 后，.env 不会上传，
    而是在网页后台的 Secrets 输入框里配置。两种方式都不需要改代码。
    """
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value) if value is not None else default


API_KEY = _get_setting("API_KEY")
BASE_URL = _get_setting("BASE_URL", "https://api.deepseek.com")
MODEL_NAME = _get_setting("MODEL_NAME", "deepseek-chat")


class LLMError(Exception):
    """调用大模型失败时抛出的错误。自带中文提示，界面直接展示给用户看即可。"""


def is_configured() -> bool:
    """检查密钥是否已经配置好（app.py 用它来决定要不要显示"请先配置密钥"的引导）。"""
    return bool(API_KEY) and "在这里" not in API_KEY


def chat(messages: list, temperature: float = 0.7, json_mode: bool = False) -> str:
    """
    把一段对话发给大模型，返回模型的回复文本。

    参数 messages 是 OpenAI 通用的对话格式：一个列表，每条消息是一个字典。
    role 有三种身份：
        system    —— 系统提示词，设定 AI 的角色和任务（用户看不到）
        user      —— 用户说的话
        assistant —— AI 之前回复的话
    示例：
        [
            {"role": "system", "content": "你是一个耐心的中文助手"},
            {"role": "user", "content": "你好"},
        ]

    temperature 控制 AI 的"发挥程度"：0 最严谨稳定，1 以上更发散。
    简历场景需要一点文采但不能胡编，0.7 比较合适。

    json_mode=True 时，强制模型输出合法 JSON（DeepSeek 的 JSON Output 功能，
    第 4 步"简历模板填充"用它保证输出能被程序解析）。
    """
    if not is_configured():
        raise LLMError("API 密钥还没配置。本地运行请填写 .env；云端部署请在 Streamlit Secrets 中填写 API_KEY。")

    # 创建客户端。base_url 指向 DeepSeek；
    # 以后换 Kimi、智谱等任何"兼容 OpenAI 协议"的服务，只需改 .env 里的 BASE_URL。
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    try:
        extra = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
            stream=False,  # 第 2 步先用"一次性返回"最简方式；第 5 步可换成流式（打字机效果）
            **extra,
        )
        # 返回结果的结构里，回复文本在 choices[0].message.content
        return response.choices[0].message.content

    # 下面把常见的英文报错"翻译"成新手能看懂的中文提示
    except AuthenticationError:
        raise LLMError("密钥验证失败（401）。请检查 API_KEY 是否复制完整、首尾有没有多余空格。")
    except APIConnectionError:
        raise LLMError("连不上大模型服务器。请检查网络（DeepSeek 国内可直连；如果你开着代理/VPN，试试关掉再试）。")
    except APIError as e:
        if "Insufficient Balance" in str(e) or "402" in str(e):
            raise LLMError("账户余额不足（402）。请到 platform.deepseek.com 充值后再试。")
        raise LLMError(f"大模型返回了错误：{e}")
