# -*- coding: utf-8 -*-
"""R308：补丁说明自动更新 + 云端发布（不用重新打包）。

用户反馈：游戏昨天更新了，「更新」页却要手动点「检查更新」才有新版本；
希望自动增加版本说明，或者把补丁说明发在云端，避免每次重新打包。

实现分三层：
1. 服务端：Steam 官方公告失败时自动回退到 GitHub 上的云端快照
   （data/game-changes.json，由 .github/workflows/update-game-changes.yml 定时提交）；
2. 前端：进入「更新」页时若本地数据缺失 / 超过 6 小时，自动补拉一次；
3. 云端：CI 定时抓 Steam → 有变化才提交快照，老客户端无需新版安装包。

这里锁住「回退顺序、缓存来源、自动触发、定时任务」四个关键点，不打真网络。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import config
import serve

ROOT = Path(__file__).resolve().parent.parent


def _entry(version: str, stamp: int) -> dict:
    return {
        "id": "steam-" + version,
        "version": version,
        "kind": serve._version_kind(version),
        "title": "Patch " + version,
        "date": "2026-11-24",
        "timestamp": stamp,
        "url": "https://store.steampowered.com/news/app/3932890/view/1",
        "sections": [{"title": "Fixes", "blocks": [{"type": "bullet", "text": "x"}]}],
        "bullets": 1,
    }


def _write_bundled(root: Path, entries: list[dict]) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "game-changes.json").write_text(
        json.dumps({"generated_at": "2026-11-01 00:00", "entries": entries},
                   ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- 云端快照
def test_remote_url_points_at_repo_snapshot():
    url = serve.GAME_CHANGES_REMOTE_URL
    assert url.startswith("https://api.github.com/repos/jjingith/eft-interactive-map/contents/")
    assert "data/game-changes.json" in url
    assert "ref=main" in url, "必须固定读 main 上的自动同步快照"


def test_fetch_remote_uses_raw_media_type_and_drops_bad_entries(monkeypatch):
    """只要合法条目；Accept 必须是 raw，否则拿回来的是 base64 包装而解析失败。"""
    seen = {}
    payload = {"generated_at": "2026-11-25 00:00",
               "entries": [_entry("1.3.5.0", 300),
                           {"version": "无 sections"},
                           {"version": "1.2.0.0", "sections": []}]}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, _n=-1):
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        seen["url"] = request.full_url
        seen["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return Response()

    monkeypatch.setattr(serve.urllib.request, "urlopen", fake_urlopen)
    entries = serve.fetch_game_changes_remote()
    assert [e["version"] for e in entries] == ["1.3.5.0"]
    assert seen["headers"].get("accept") == "application/vnd.github.raw"


def test_fetch_remote_rejects_non_list_payload(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, _n=-1):
            return b'{"error": "Not Found"}'

    monkeypatch.setattr(serve.urllib.request, "urlopen", lambda *a, **k: Response())
    try:
        serve.fetch_game_changes_remote()
    except ValueError as exc:
        assert "格式" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("非快照格式必须报错")


# ---------------------------------------------------------------- 刷新回退顺序
def test_refresh_falls_back_to_cloud_when_steam_fails(tmp_path, monkeypatch):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])

    def steam_down(timeout=12.0):
        raise OSError("steam blocked")

    monkeypatch.setattr(serve, "fetch_game_changes", steam_down)
    monkeypatch.setattr(serve, "fetch_game_changes_remote",
                        lambda timeout=8.0: [_entry("1.0.0.0", 100), _entry("1.3.5.0", 300)])

    data = serve.refresh_game_changes(str(root), str(cfg))
    assert data["ok"] is True
    assert data["from"] == "cloud"
    assert data["added"] == 1
    assert [e["version"] for e in data["entries"]][0] == "1.3.5.0"
    cache = json.loads(Path(serve.game_changes_cache_path(str(cfg))).read_text(encoding="utf-8"))
    assert cache["source"] == "cloud"

    again = serve.game_changes_payload(str(root), str(cfg))
    assert again["from"] == "cache"
    assert again["entries"][0]["version"] == "1.3.5.0", "回退结果必须落缓存，下次秒开"


def test_refresh_prefers_steam_and_skips_cloud(tmp_path, monkeypatch):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])
    monkeypatch.setattr(serve, "fetch_game_changes",
                        lambda timeout=12.0: [_entry("1.3.5.0", 300)])

    def no_cloud(timeout=8.0):
        raise AssertionError("Steam 已成功，不应再请求云端快照")

    monkeypatch.setattr(serve, "fetch_game_changes_remote", no_cloud)
    data = serve.refresh_game_changes(str(root), str(cfg))
    assert data["ok"] is True and data["from"] == "network"


def test_refresh_reports_both_failures(tmp_path, monkeypatch):
    root, cfg = tmp_path / "root", tmp_path / "cfg"
    _write_bundled(root, [_entry("1.0.0.0", 100)])

    def down(kind):
        def boom(timeout=12.0):
            raise OSError(kind)
        return boom

    monkeypatch.setattr(serve, "fetch_game_changes", down("steam down"))
    monkeypatch.setattr(serve, "fetch_game_changes_remote", down("cloud down"))
    data = serve.refresh_game_changes(str(root), str(cfg))
    assert data["ok"] is False
    assert "steam down" in data["error"] and "cloud down" in data["error"]
    assert data["count"] == 1


# ---------------------------------------------------------------- 前端自动补拉
def test_changes_js_auto_refreshes_when_stale():
    js = (ROOT / "js" / "changes.js").read_text(encoding="utf-8")
    assert "function maybeAutoRefresh" in js
    assert "refreshNow({ auto: true })" in js
    assert "state.autoTried" in js, "每个会话最多自动尝试一次"
    assert "正在后台获取最新补丁说明" in js
    assert "暂时无法获取最新补丁说明" in js, "自动失败不能弹成刺眼错误"
    assert "云端快照" in js, "来源要能显示云端快照"
    # 进入视图总是重读本地（快照+缓存），陈旧时再自动补拉
    assert js.index("open: function () {") < js.index("load();", js.index("open: function () {"))


def test_bundled_snapshot_is_well_formed():
    """不锁具体版本号：云端定时同步会不断把新版本提交进来。"""
    data = json.loads((ROOT / "data" / "game-changes.json").read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    assert entries, "随包快照不能为空"
    assert data.get("generated_at")
    assert all(e.get("version") and e.get("sections") for e in entries[:5])
    stamps = [int(e.get("timestamp") or 0) for e in entries]
    assert stamps == sorted(stamps, reverse=True), "版本必须按时间倒序"


# ---------------------------------------------------------------- 定时云端同步
def test_workflow_syncs_snapshot_on_schedule():
    text = (ROOT / ".github" / "workflows" / "update-game-changes.yml").read_text(encoding="utf-8")
    assert "cron:" in text and "workflow_dispatch" in text
    assert "tools/fetch_game_changes.py --if-changed" in text
    assert "git commit" in text and "data/game-changes.json" in text
    assert "contents: write" in text


def test_fetch_script_supports_if_changed():
    src = (ROOT / "tools" / "fetch_game_changes.py").read_text(encoding="utf-8")
    assert "--if-changed" in src
    assert "补丁条目没有变化" in src, "没变化就不写文件，避免只改 generated_at 也产生提交"


# ---------------------------------------------------------------- 视图白名单（跳回市场的根因）
def test_server_view_whitelist_matches_app():
    """服务端 config.VIEWS 必须与 app.js 的 VIEWS 完全一致，否则切换结果会被丢掉。"""
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    match = re.search(r"var VIEWS = \[([^\]]+)\]", app)
    assert match, "找不到 app.js 的 VIEWS"
    js_views = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert js_views == set(config.VIEWS)


def test_tools_and_changes_views_survive_prefs_patch(tmp_path):
    """R308 回归：在小工具里改任何设置（写 prefs → 配置广播）不能把视图顶回市场。

    根因：服务端 VIEWS 白名单缺 changes/tools → 保存的 ui.view 被丢弃，
    配置里保留旧值 market，广播后 applyUiPrefs 把界面切回市场。
    """
    for view in ("tools", "changes"):
        cfg = config.normalize({"ui": {"view": view}})
        assert cfg["ui"]["view"] == view, "白名单丢了 %s" % view
        merged = config.merge_ui(cfg, {"auto_screenshot": {"enabled": True}})
        assert merged["ui"]["view"] == view, "%s 视图被无关的 prefs 改动顶掉了" % view


# ---------------------------------------------------------------- 截图键手动设置
def test_merge_ui_accepts_manual_shot_key():
    merged = config.merge_ui({}, {"auto_screenshot": {"key": "F12"}})
    assert merged["auto_screenshot"]["key"] == "F12"
    cleared = config.merge_ui(merged, {"auto_screenshot": {"key": None}})
    assert not cleared["auto_screenshot"]["key"], "空值 = 清掉手动键，回到自动读取游戏绑定"


def test_config_payload_exposes_manual_shot_key(tmp_path):
    config.save({"auto_screenshot": {"key": "F12"}}, str(tmp_path))
    payload = serve.config_payload(str(tmp_path))
    assert payload["resolved"]["shotKey"] == "F12"
    assert payload["resolved"]["shotKeySource"] == "manual"


def test_config_payload_falls_back_to_control_ini(tmp_path, monkeypatch):
    monkeypatch.setattr(serve.eftlog, "read_screenshot_key_from_control_ini",
                        lambda path=None: "SysReq")
    payload = serve.config_payload(str(tmp_path))
    assert payload["resolved"]["shotKey"] == "SysReq"
    assert payload["resolved"]["shotKeySource"] == "control.ini"


def test_minimap_panel_has_manual_shot_key_controls():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="mini-shot-key-input"' in html
    assert 'id="mini-shot-key-save"' in html
    assert "启动器里手动填写" not in html
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function saveShotKey" in js
    assert "auto_screenshot: { key: val || null }" in js
    assert "自动读取游戏绑定" in js


# ---------------------------------------------------------------- 行情页脚注精简
def test_market_foot_note_is_concise():
    """R308：页脚只留「按游戏模式自动跟随 · 云端行情」，不再罗列会员/免费差异。"""
    js = (ROOT / "js" / "market.js").read_text(encoding="utf-8")
    assert "按游戏模式自动跟随 · 云端行情</span>" in js
    assert "不做伪实时" not in js
    assert "会员 30 秒 CD" not in js
