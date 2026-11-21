"""R111：三个「页面在用、测试却没覆盖」的服务端接口。

背景：`/api/build`、`/api/overlay`、`/api/layout-calibration` 在 R19.5x 一轮重建中
被漏掉，前端只在浏览器里表现为「构建标记变成 http-404」「小浮窗开关没反应」，
pytest 全绿也发现不了。这里补三条最小回归测试，锁住路由存在性与写盘语义。

所有写盘都注入 tmp_path：校准数据写临时根目录的 data/，配置写 config_dir。
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import layoutcal
import serve

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def server(tmp_path):
    """root 用临时目录（校准写盘隔离），config_dir 也指向同一处。"""
    (tmp_path / "data").mkdir()
    # create_server 只校验根目录里有没有 index.html；本文件不测静态资源
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    httpd = serve.create_server(0, "127.0.0.1", str(tmp_path), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve.url_for("127.0.0.1", httpd.server_address[1]), tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def post_json(url, payload):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# --------------------------------------------------------------- /api/build

def test_build_reports_root_and_rev(server):
    base, tmp = server
    status, body = get_json(base + "api/build")
    assert status == 200 and body["ok"] is True
    # 启动器靠 root 判断「端口是不是本仓库」
    assert os.path.normcase(os.path.abspath(body["root"])) == os.path.normcase(os.path.abspath(str(tmp)))
    assert body["rev"].startswith("R19.")
    assert isinstance(body["assets"], list)


def test_health_and_build_share_rev(server):
    base, _ = server
    _, health = get_json(base + "api/health")
    _, build = get_json(base + "api/build")
    assert health["rev"] == build["rev"]


# --------------------------------------------------------------- /api/overlay

def test_overlay_toggle_writes_enabled_and_broadcasts(server):
    base, tmp = server
    status, body = post_json(base + "api/overlay", {"enabled": True})
    assert status == 200 and body == {"ok": True, "enabled": True}
    _, cfg = get_json(base + "api/config")
    assert cfg["config"]["overlay"]["enabled"] is True


def test_overlay_toggle_rejects_non_boolean(server):
    base, _ = server
    status, body = post_json(base + "api/overlay", {"enabled": "yes"})
    assert status == 400 and body["ok"] is False


# --------------------------------------------------------------- /api/layout-calibration

def test_calibration_get_empty_then_save_roundtrip(server):
    base, tmp = server
    status, body = get_json(base + "api/layout-calibration")
    assert status == 200 and body["ok"] is True
    assert body["data"]["guns"] == {}
    assert body["path"] == "data/" + layoutcal.FILENAME

    gun = {"name": "测试枪", "slots": {
        "mod_x|mod_x_slot|": {
            "slotId": "mod_x_slot", "slotPath": "mod_x", "ownerItemId": "",
            "logicalRow": 0, "col": 1,
        }
    }}
    status, body = post_json(base + "api/layout-calibration",
                             {"action": "save", "gunId": "gun-test", "gun": gun})
    assert status == 200 and body["summary"]["guns"] == 1
    assert (tmp / "data" / layoutcal.FILENAME).is_file()
    assert body["data"]["guns"]["gun-test"]["slots"]

    status, body = post_json(base + "api/layout-calibration", {"action": "clear", "gunId": "gun-test"})
    assert status == 200 and body["summary"]["guns"] == 0


def test_calibration_rejects_bad_payload_without_touching_disk(server):
    base, tmp = server
    path = tmp / "data" / layoutcal.FILENAME
    path.write_text(json.dumps(layoutcal.empty_doc()), encoding="utf-8")
    status, body = post_json(base + "api/layout-calibration",
                             {"action": "import", "data": {"guns": "not-an-object"}})
    assert status == 400 and body["ok"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["guns"] == {}
