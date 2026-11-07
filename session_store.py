"""
session_store.py —— 每个浏览器独立的会话存档

同一个公网网址可能被很多设备打开。每个浏览器会得到一个随机的
session_id，聊天记录、简历和证件照分别保存在自己的文件夹里，
彼此不会看到或覆盖。

session_id 会写入网址参数 ?session_id=...。刷新页面时参数仍然存在，
所以资料可以恢复；换设备或换浏览器时会得到新的空白会话。
"""

import json
import re
import secrets
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def is_valid_session_id(session_id: str | None) -> bool:
    """检查会话编号，避免特殊字符被拼进文件路径。"""
    return bool(session_id and SESSION_ID_PATTERN.fullmatch(session_id))


def new_session_id() -> str:
    """生成一个足够长、无法猜到的随机编号。"""
    return secrets.token_urlsafe(24)


def _session_file(session_id: str) -> Path:
    """取得当前浏览器的 JSON 存档路径。"""
    if not is_valid_session_id(session_id):
        raise ValueError("无效的会话编号")
    return SESSIONS_DIR / f"{session_id}.json"


def _photo_dir(session_id: str) -> Path:
    """取得当前浏览器专属的证件照文件夹。"""
    if not is_valid_session_id(session_id):
        raise ValueError("无效的会话编号")
    return SESSIONS_DIR / session_id


def save_session(session_id: str, data: dict) -> bool:
    """保存当前浏览器的聊天、简历和面试记录。"""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _session_file(session_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def load_session(session_id: str) -> dict | None:
    """读取当前浏览器的存档；没有存档或文件损坏时返回 None。"""
    if not is_valid_session_id(session_id):
        return None
    path = _session_file(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def clear_session(session_id: str) -> bool:
    """清空当前浏览器的存档，不影响其他设备。"""
    if not is_valid_session_id(session_id):
        return False
    try:
        path = _session_file(session_id)
        if path.exists():
            path.unlink()
        return True
    except OSError:
        return False


def save_photo(session_id: str, data: bytes, ext: str = "jpg") -> None:
    """把证件照保存到当前浏览器专属文件夹，并清掉旧格式照片。"""
    photo_dir = _photo_dir(session_id)
    photo_dir.mkdir(parents=True, exist_ok=True)
    delete_photo(session_id)
    (photo_dir / f"photo.{ext}").write_bytes(data)


def get_photo_path(session_id: str) -> Path | None:
    """返回当前浏览器上传的证件照路径；没上传过则返回 None。"""
    if not is_valid_session_id(session_id):
        return None
    for ext in ("jpg", "jpeg", "png"):
        path = _photo_dir(session_id) / f"photo.{ext}"
        if path.exists():
            return path
    return None


def delete_photo(session_id: str) -> None:
    """只删除当前浏览器上传的证件照。"""
    if not is_valid_session_id(session_id):
        return
    for ext in ("jpg", "jpeg", "png"):
        path = _photo_dir(session_id) / f"photo.{ext}"
        if path.exists():
            path.unlink()
