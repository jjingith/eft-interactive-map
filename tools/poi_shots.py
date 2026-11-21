# -*- coding: utf-8 -*-
"""R287 点位参考图：给地图标记附「自己截的实景图」，存本机、可离线看。

为什么是「用户自己贴」而不是内置社区图：
  别的同类项目里那批刷点实景图是社区提交到第三方站点的，直接扒进我们的包有版权风险。
  所以这里只提供通道：玩家在某处截过图，就能把它挂到对应点位上，下次找东西一眼看到。

存储：`%APPDATA%\\EFTMap\\poi-shots\\<hash>.<ext>`
  · 一个点位一张图，同名覆盖（不做版本堆叠）。
  · 文件名是 **key 的 sha1 前 20 位**，不是原始 key —— 原始 key 由前端按
    `kind:name:x:z` 拼出来，含中文与冒号，直接当文件名既不安全也不好用。
    因为落盘名只由哈希决定，任何输入都不可能跳出目录（无路径穿越面）。

只接受 jpeg / png / webp，上限 8 MB：参考图是「看一眼」用的，不是相册。
"""
from __future__ import annotations

import hashlib
import os
import time

SUBDIR = "poi-shots"
MAX_BYTES = 8 * 1024 * 1024
MAX_KEY_LEN = 300
ALLOWED = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"RIFF", ".webp"),          # 后面还要看 8..12 是不是 WEBP
)


class ShotError(ValueError):
    """参数不合法（key 为空 / 类型不支持 / 内容不是图片）。"""


def root(storage_dir: str) -> str:
    return os.path.join(storage_dir, SUBDIR)


def normalise_key(raw) -> str:
    """把前端给的 key 收敛成可哈希的字符串；空值直接报错。"""
    key = str(raw or "").strip()
    if not key:
        raise ShotError("缺少 key")
    if len(key) > MAX_KEY_LEN:
        raise ShotError("key 过长（上限 %d 字符）" % MAX_KEY_LEN)
    return key


def digest(raw) -> str:
    return hashlib.sha1(normalise_key(raw).encode("utf-8")).hexdigest()[:20]


def _sniff(data: bytes) -> str | None:
    """按魔数判断真实类型，不信 Content-Type（前端可以随便写）。"""
    for magic, ext in MAGIC:
        if data.startswith(magic):
            if ext == ".webp":
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return ext
                return None
            return ext
    return None


def path_for(storage_dir: str, raw) -> str:
    """按 key 找到已有文件（扩展名可能是三种之一）；没有就返回默认 .jpg 路径。"""
    base = os.path.join(root(storage_dir), digest(raw))
    for ext in (".jpg", ".png", ".webp"):
        if os.path.isfile(base + ext):
            return base + ext
    return base + ".jpg"


def save(storage_dir: str, raw, data: bytes, ctype: str = "") -> dict:
    key = normalise_key(raw)
    if not data:
        raise ShotError("请求体为空")
    if len(data) > MAX_BYTES:
        raise ShotError("图片超过 %d MB" % (MAX_BYTES // 1024 // 1024))
    ext = _sniff(data)
    if ext is None:
        raise ShotError("只接受 JPEG / PNG / WebP")
    declared = (ctype or "").split(";")[0].strip().lower()
    if declared and declared not in ALLOWED:
        raise ShotError("Content-Type 不支持：%s" % declared)

    directory = root(storage_dir)
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, digest(key) + ext)
    # 换过格式（先 jpg 后 png）时把旧文件清掉，避免同一点位读出两张
    for other in (".jpg", ".png", ".webp"):
        stale = os.path.join(directory, digest(key) + other)
        if stale != target and os.path.isfile(stale):
            try:
                os.remove(stale)
            except OSError:
                pass
    tmp = target + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, target)
    return {"key": key, "bytes": len(data), "ext": ext,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())}


def load(storage_dir: str, raw) -> tuple[bytes, str] | None:
    path = path_for(storage_dir, raw)
    if not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    ctype = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "application/octet-stream")
    try:
        with open(path, "rb") as fh:
            return fh.read(), ctype
    except OSError:
        return None


def delete(storage_dir: str, raw) -> bool:
    path = path_for(storage_dir, raw)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def list_keys(storage_dir: str) -> list[dict]:
    """列出所有已存参考图（只有哈希名与时间，前端自己比对哪些点位有图）。"""
    directory = root(storage_dir)
    if not os.path.isdir(directory):
        return []
    out = []
    for name in os.listdir(directory):
        if name.endswith(".tmp"):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".jpg", ".png", ".webp"):
            continue
        path = os.path.join(directory, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        out.append({"hash": stem, "ext": ext.lower(), "bytes": st.st_size,
                    "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime))})
    out.sort(key=lambda r: r["updatedAt"], reverse=True)
    return out


def hash_of(raw) -> str:
    """前端算好 key 后可以直接问「这个点位有没有图」。"""
    return digest(raw)
