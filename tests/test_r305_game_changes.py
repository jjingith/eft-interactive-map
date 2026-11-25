"""R305：游戏更新视图（官方补丁说明）。

分三块：
1. **Steam BBCode 解析**：官方公告 → 分区 + 条目，顺序与类型不能错；
2. **缓存与接口**：内置快照 + 用户缓存合并、刷新落盘、跨站拒绝（真起服务，不打网络）；
3. **前端接线**：视图标签、容器、模块、样式是否都挂上了。

数据源固定在 Steam 官方公告（BSG 自己发的 Patch 公告），所以解析器是这套功能的地基，
出错的表现是「页面上一堆 [h3] 原文」或「条目顺序颠倒」，这里逐条锁住。
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import serve

ROOT = Path(__file__).resolve().parent.parent

SAMPLE = (
    "[h3]Changes[/h3][list]"
    "[*][p]Added a thing &amp; more;[/p][/*]"
    "[*][p]Fixed a bug.[/p][/*]"
    "[/list]"
    "[p][i]Note: server restart.[/i][/p]"
)


def _entry(version: str, stamp: int, title: str | None = None) -> dict:
    return {
        "id": "steam-" + version,
        "version": version,
        "kind": serve._version_kind(version),
        "title": title or ("Patch " + version),
        "date": "2026-10-30",
        "timestamp": stamp,
        "url": "https://store.steampowered.com/news/app/3932890/view/1",
        "sections": [{"title": "Changes", "blocks": [{"type": "bullet", "text": "x"}]}],
        "bullets": 1,
    }


# ---------------------------------------------------------------- 解析
def test_parse_bbcode_keeps_block_types_and_order():
    sections = serve.parse_steam_bbcode(SAMPLE)
    assert [s["title"] for s in sections] == ["Changes"]
    blocks = sections[0]["blocks"]
    assert [b["type"] for b in blocks] == ["bullet", "bullet", "para"]
    assert blocks[0]["text"] == "Added a thing & more;"    # HTML 实体已还原
    assert blocks[2]["text"] == "Note: server restart."    # [i] 已剥掉


def test_parse_bbcode_keeps_paragraph_before_list():
    body = ("[h3]Expansion Hub[/h3][p]Added new sets:[/p]"
            "[list][*][p]A;[/p][/*][*][p]B.[/p][/*][/list]"
            "[p]More later.[/p]")
    blocks = serve.parse_steam_bbcode(body)[0]["blocks"]
    assert [b["type"] for b in blocks] == ["para", "bullet", "bullet", "para"]
    assert blocks[0]["text"] == "Added new sets:"
    assert blocks[-1]["text"] == "More later."


def test_parse_bbcode_drops_media_and_embeds():
    body = ("[p]x[/p][img src=\"{STEAM_CLAN_IMAGE}/a.jpg\"][/img]"
            "[dynamiclink href=\"https://youtu.be/x\"][/dynamiclink]"
            "[previewyoutube=\"abc;full\"][/previewyoutube]")
    sections = serve.parse_steam_bbcode(body)
    text = " ".join(b["text"] for s in sections for b in s["blocks"])
    assert text.strip() == "x"
    assert "youtube" not in text and "img" not in text


def test_parse_bbcode_without_headers_still_works():
    sections = serve.parse_steam_bbcode("[p]only text[/p]")
    assert len(sections) == 1 and sections[0]["title"] == ""
    assert sections[0]["blocks"][0]["text"] == "only text"


def test_patch_entry_only_accepts_patch_posts():
    item = {"title": "Patch 1.3.0.0", "gid": "123", "date": 1793300000,
            "contents": SAMPLE, "feedname": "steam_community_announcements"}
    entry = serve._patch_entry(item)
    assert entry["version"] == "1.3.0.0"
    assert entry["kind"] == "大版本"
    assert entry["bullets"] == 2
    assert entry["url"].endswith("/view/123")
    assert entry["date"].count("-") == 2

    assert serve._patch_entry(dict(item, title="Developer's diary")) is None
    assert serve._patch_entry(dict(item, title="Patch 1.3.0.0", contents="")) is None


def test_version_kind_labels():
    assert serve._version_kind("1.3.0.0") == "大版本"
    assert serve._version_kind("1.1.5.0") == "小版本"
    assert serve._version_kind("1.0.4.9") == "热修"
    assert serve._version_kind("") == "大版本"


def test_fetch_only_keeps_official_announcements(monkeypatch):
    payload = {"appnews": {"newsitems": [
        {"title": "Patch 1.3.0.0", "gid": "1", "date": 200, "contents": SAMPLE,
         "feedname": "steam_community_announcements"},
        {"title": "Patch 1.2.0.0", "gid": "2", "date": 100, "contents": SAMPLE,
         "feedname": "PlayGround.ru - официальная группа"},
    ]}}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, _n=-1):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(serve.urllib.request, "urlopen", lambda *a, **k: Response())
    entries = serve.fetch_game_changes()
    assert [e["version"] for e in entries] == ["1.3.0.0"], "媒体转载不算官方补丁说明"


# ---------------------------------------------------------------- 缓存 / 合并
def _write_bundled(root: Path, entries: list[dict]) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "game-changes.json").write_text(
        json.dumps({"generated_at": "2026-11-01 00:00", "entries": entries},
                   ensure_ascii=False), encoding="utf-8")


def _write_cache(config_dir: Path, entries: list[dict], fetched_at="2026-11-02 10:00") -> None:
    path = Path(serve.game_changes_cache_path(str(config_dir)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": fetched_at, "entries": entries},
                               ensure_ascii=False), encoding="utf-8")


def test_payload_merges_cache_over_bundled(tmp_path):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100), _entry("1.1.0.0", 200)])
    _write_cache(cfg, [_entry("1.1.0.0", 200, title="缓存里的新标题"),
                       _entry("1.2.0.0", 300)])

    data = serve.game_changes_payload(str(root), str(cfg))
    assert [e["version"] for e in data["entries"]] == ["1.2.0.0", "1.1.0.0", "1.0.0.0"]
    assert data["entries"][1]["title"] == "缓存里的新标题", "同一条以缓存为准"
    assert data["from"] == "cache"
    assert data["count"] == 3


def test_payload_falls_back_to_bundled_without_cache(tmp_path):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])
    data = serve.game_changes_payload(str(root), str(cfg))
    assert data["from"] == "bundled" and data["count"] == 1
    assert data["stale"] is False


def test_payload_survives_broken_cache_file(tmp_path):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])
    path = Path(serve.game_changes_cache_path(str(cfg)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    data = serve.game_changes_payload(str(root), str(cfg))
    assert data["ok"] and data["count"] == 1


def test_refresh_writes_cache_and_reports_added(tmp_path, monkeypatch):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])
    monkeypatch.setattr(serve, "fetch_game_changes",
                        lambda timeout=12.0: [_entry("1.0.0.0", 100), _entry("1.1.0.0", 200)])

    data = serve.refresh_game_changes(str(root), str(cfg))
    assert data["ok"] is True and data["added"] == 1
    assert Path(serve.game_changes_cache_path(str(cfg))).is_file()
    again = serve.game_changes_payload(str(root), str(cfg))
    assert again["from"] == "cache" and again["count"] == 2


def test_refresh_failure_keeps_what_we_have(tmp_path, monkeypatch):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])

    def boom(timeout=12.0):
        raise OSError("network down")

    # R308：Steam 失败后会尝试云端快照，这里也要断掉，确保走「全部失败」分支
    monkeypatch.setattr(serve, "fetch_game_changes", boom)
    monkeypatch.setattr(serve, "fetch_game_changes_remote", boom)
    data = serve.refresh_game_changes(str(root), str(cfg))
    assert data["ok"] is False
    assert "network down" in data["error"]
    assert data["count"] == 1, "网络失败不能把已有内容清空"


# ---------------------------------------------------------------- HTTP 接口
def _serve(config_dir: Path):
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(config_dir),
                                poll_interval=0.2)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def _stop(httpd, thread):
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _request(url: str, data: bytes | None = None, headers: dict | None = None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def api(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    httpd, thread = _serve(cfg)
    base = "http://127.0.0.1:%d/" % httpd.server_address[1]
    try:
        yield base, cfg
    finally:
        _stop(httpd, thread)


def test_get_returns_bundled_snapshot(api):
    base, _cfg = api
    status, body = _request(base + "api/game-changes")
    assert status == 200 and body["ok"] is True
    assert body["count"] >= 1
    first = body["entries"][0]
    assert first["version"] and first["sections"] and first["url"].startswith("https://")


def test_refresh_endpoint_fetches_and_caches(api, monkeypatch):
    base, cfg = api
    monkeypatch.setattr(
        serve, "fetch_game_changes",
        lambda timeout=12.0: [_entry("9.9.9.9", 10 ** 10, title="Patch 9.9.9.9")])

    status, body = _request(base + "api/game-changes/refresh", data=b"{}",
                            headers={"Content-Type": "application/json"})
    assert status == 200 and body["ok"] is True
    assert body["entries"][0]["version"] == "9.9.9.9"
    assert (cfg / "game-changes" / "news.json").is_file()


def test_refresh_endpoint_rejects_cross_origin(api):
    base, _cfg = api
    status, body = _request(base + "api/game-changes/refresh", data=b"{}",
                            headers={"Origin": "https://evil.example"})
    assert status == 403 and body["ok"] is False


def test_unknown_api_still_404(api):
    base, _cfg = api
    status, _body = _request(base + "api/game-changes/nope")
    assert status == 404


# ---------------------------------------------------------------- 内置快照
def test_bundled_snapshot_is_well_formed():
    data = json.loads((ROOT / "data" / "game-changes.json").read_text(encoding="utf-8"))
    assert data["entries"], "随包快照不能是空的（离线时全靠它）"
    for entry in data["entries"]:
        assert entry["version"].count(".") >= 2
        assert entry["kind"] in ("大版本", "小版本", "热修")
        assert entry["url"].startswith("https://store.steampowered.com/news/")
        assert entry["sections"] and entry["sections"][0]["blocks"]
        for section in entry["sections"]:
            for block in section["blocks"]:
                assert block["type"] in ("bullet", "para")
                assert block["text"].strip() == block["text"]
                assert "[" not in block["text"], "解析残留会把 [h3] 之类的原文漏到页面上"


# ---------------------------------------------------------------- 前端接线
def test_view_is_wired_into_the_app():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    mod = (ROOT / "js" / "changes.js").read_text(encoding="utf-8")
    css = (ROOT / "styles" / "changes.css").read_text(encoding="utf-8")

    assert 'id="view-btn-changes"' in html and 'data-view="changes"' in html
    assert 'id="changes-view"' in html
    assert "js/changes.js" in html and "styles/changes.css" in html

    assert '"changes"' in app and "el.changesView = $(\"changes-view\")" in app
    assert "changes: el.changesView" in app
    assert "window.GWChanges.mount()" in app
    assert 'location.hash === "#changes"' in app, "深链不能被旧配置顶回地图"

    assert "window.GWChanges = {" in mod
    assert "mount: mount" in mod and "refresh: refreshNow" in mod
    assert "data-i18n-skip" in mod, "英文正文不能被名词字典逐词替换"

    assert "#changes-view .ch-item" in css
    assert 'body[data-view="changes"] #vt-prices' in css


def test_chinese_section_labels_cover_common_titles():
    mod = (ROOT / "js" / "changes.js").read_text(encoding="utf-8")
    for title, label in (("changes", "改动"), ("fixes", "修复"),
                         ("balance changes", "平衡调整"), ("known issues", "已知问题")):
        assert '"%s": "%s"' % (title, label) in mod
