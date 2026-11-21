# -*- coding: utf-8 -*-
"""R287 点位参考图：本机存储 + 上传接口 + 前端契约。

口径：参考图是**用户自己贴的**，只存本机 `%APPDATA%\\EFTMap\\poi-shots\\`。
不内置、不下载第三方社区图（版权），所以这里测的是通道与边界，不是内容。
"""
from __future__ import annotations

import http.client
import json
import os
import threading
import urllib.parse
from pathlib import Path

import pytest

import poi_shots
import serve

ROOT = Path(__file__).resolve().parent.parent
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 存储层
def test_key_is_hashed_and_cannot_escape(tmp_path):
    """key 里带 ../ 也只能落成 20 位哈希文件名，不可能跳出目录。"""
    info = poi_shots.save(str(tmp_path), "../../etc/passwd", JPEG)
    assert info["ext"] == ".jpg"
    files = os.listdir(poi_shots.root(str(tmp_path)))
    assert len(files) == 1
    stem = os.path.splitext(files[0])[0]
    assert len(stem) == 20 and all(c in "0123456789abcdef" for c in stem)
    assert "/" not in files[0] and ".." not in files[0]
    assert poi_shots.load(str(tmp_path), "../../etc/passwd")[0] == JPEG


def test_empty_key_rejected(tmp_path):
    with pytest.raises(poi_shots.ShotError):
        poi_shots.save(str(tmp_path), "   ", JPEG)


def test_overlong_key_rejected(tmp_path):
    with pytest.raises(poi_shots.ShotError):
        poi_shots.save(str(tmp_path), "k" * (poi_shots.MAX_KEY_LEN + 1), JPEG)


def test_rejects_non_image_payload(tmp_path):
    """不信 Content-Type，按魔数判定：随便一段字节不能当图。"""
    with pytest.raises(poi_shots.ShotError):
        poi_shots.save(str(tmp_path), "a", b"not an image at all")
    with pytest.raises(poi_shots.ShotError):
        poi_shots.save(str(tmp_path), "a", b"")


def test_rejects_bad_content_type(tmp_path):
    with pytest.raises(poi_shots.ShotError):
        poi_shots.save(str(tmp_path), "a", JPEG, "text/plain")


def test_rejects_too_large(tmp_path):
    big = b"\xff\xd8\xff\xe0" + b"\x00" * poi_shots.MAX_BYTES
    with pytest.raises(poi_shots.ShotError):
        poi_shots.save(str(tmp_path), "a", big)


def test_roundtrip_and_extension_switch(tmp_path):
    poi_shots.save(str(tmp_path), "keys:name:1.0:2.0", JPEG)
    data, ctype = poi_shots.load(str(tmp_path), "keys:name:1.0:2.0")
    assert data == JPEG and ctype == "image/jpeg"

    # 换成 png 后旧 jpg 必须被清掉，同一点位不能读出两张
    poi_shots.save(str(tmp_path), "keys:name:1.0:2.0", PNG)
    data, ctype = poi_shots.load(str(tmp_path), "keys:name:1.0:2.0")
    assert data == PNG and ctype == "image/png"
    assert len(os.listdir(poi_shots.root(str(tmp_path)))) == 1

    assert poi_shots.delete(str(tmp_path), "keys:name:1.0:2.0") is True
    assert poi_shots.load(str(tmp_path), "keys:name:1.0:2.0") is None
    assert poi_shots.delete(str(tmp_path), "keys:name:1.0:2.0") is False


def test_list_keys_reports_size_and_time(tmp_path):
    assert poi_shots.list_keys(str(tmp_path)) == []
    poi_shots.save(str(tmp_path), "a", JPEG)
    poi_shots.save(str(tmp_path), "b", PNG)
    items = poi_shots.list_keys(str(tmp_path))
    assert len(items) == 2
    assert {i["ext"] for i in items} == {".jpg", ".png"}
    assert all(i["bytes"] > 0 and i["updatedAt"] for i in items)


# ---------------------------------------------------------------- 接口层
@pytest.fixture()
def server(tmp_path):
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _call(port, method, path, body=None, ctype=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {}
    if body is not None:
        headers["Content-Length"] = str(len(body))
    if ctype:
        headers["Content-Type"] = ctype
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_api_upload_read_list_delete(server):
    port, cfg = server
    key = urllib.parse.quote("keys:宿舍306:12.3:-45.6")

    assert _call(port, "GET", "/api/poi-shot?key=" + key)[0] == 404

    status, raw = _call(port, "POST", "/api/poi-shot?key=" + key, JPEG, "image/jpeg")
    assert status == 200, raw
    body = json.loads(raw)
    assert body["ok"] is True and body["bytes"] == len(JPEG) and body["ext"] == ".jpg"
    assert body["hash"] == poi_shots.hash_of("keys:宿舍306:12.3:-45.6")

    status, raw = _call(port, "GET", "/api/poi-shot?key=" + key)
    assert status == 200 and raw == JPEG

    status, raw = _call(port, "GET", "/api/poi-shots")
    listing = json.loads(raw)
    assert status == 200 and listing["ok"] is True and len(listing["items"]) == 1
    assert listing["maxBytes"] == poi_shots.MAX_BYTES

    status, raw = _call(port, "POST", "/api/poi-shot?key=" + key + "&action=delete")
    assert status == 200 and json.loads(raw)["removed"] is True
    assert _call(port, "GET", "/api/poi-shot?key=" + key)[0] == 404


def test_api_rejects_non_image(server):
    port, _cfg = server
    status, raw = _call(port, "POST", "/api/poi-shot?key=k", b"hello", "image/png")
    assert status == 400
    assert "JPEG" in json.loads(raw)["error"]


def test_api_over_limit_keeps_connection_usable(server):
    """超限要读尽请求体再回 413，否则同一 keep-alive 连接上的下一个请求会被污染。"""
    port, _cfg = server
    big = b"\xff\xd8\xff\xe0" + b"\x00" * (poi_shots.MAX_BYTES + 1024)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        conn.request("POST", "/api/poi-shot?key=k", body=big,
                     headers={"Content-Length": str(len(big)), "Content-Type": "image/jpeg"})
        resp = conn.getresponse()
        assert resp.status == 413
        resp.read()
        # 同连接继续请求：能被正常解析说明残留字节已被读尽
        conn.request("GET", "/api/poi-shots")
        resp2 = conn.getresponse()
        assert resp2.status == 200
        resp2.read()
    finally:
        conn.close()


# ---------------------------------------------------------------- 前端契约
def test_frontend_wires_shot_section_into_inspector():
    js = read("app.js")
    assert "function shotKeyOf(" in js
    assert "function appendShotSection(" in js
    assert "appendShotSection(kind, item, name);" in js, "详情面板必须挂上参考图区块"
    assert "function openShotLightbox(" in js
    # 查看器四件套
    for token in ("deltaY", "mousedown", "dblclick", 'ev.key === "Escape"'):
        assert token in js, "大图查看器缺 %s" % token
    # 上传走原始字节，不是 JSON 包一层 base64
    assert 'method: "POST"' in js and "readAsArrayBuffer" in js


def test_style_has_shot_blocks_and_sits_above_dialogs():
    css = read("style.css")
    assert ".inspector-shot {" in css and ".shot-lightbox {" in css
    assert "z-index: 13000" in css, "查看器必须盖住现有最高层（12000）"


def test_server_routes_registered():
    src = read("tools/serve.py")
    assert "import poi_shots" in src
    assert 'if path == "/api/poi-shot":' in src
    assert 'if path == "/api/poi-shots":' in src
    assert "def _handle_poi_shot_get" in src
    assert "def _handle_poi_shot_post" in src
    assert "def _read_raw" in src
