"""`tools/presets.py` 与 `/api/presets` 的测试：落盘位置、结构校验、原子写入、损坏保护、导入导出。

全部使用 tmp_path 注入存储目录，绝不读写真实的 `%APPDATA%\\EFTMap`。
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import presets
import serve

ROOT = Path(__file__).resolve().parent.parent


def loadout(slots=None, **kw):
    data = {"name": "测试方案", "slots": slots if slots is not None else {"helmet": "item-a"}}
    data.update(kw)
    return data


def weapon(items=None, **kw):
    data = {"name": "测试枪械", "gunId": "gun-ak", "items": items if items is not None else {"muzzle": "mod-1"}}
    data.update(kw)
    return data


# --------------------------------------------------------------- 路径与命名

def test_store_path_under_appdata_shop(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert presets.store_path("loadout") == os.path.join(str(tmp_path), "EFTMap", "loadout-presets.json")
    assert presets.store_path("weapon") == os.path.join(str(tmp_path), "EFTMap", "weapon-presets.json")


def test_store_path_rejects_unknown_kind(tmp_path):
    with pytest.raises(presets.PresetError) as info:
        presets.store_path("money", str(tmp_path))
    assert info.value.code == "kind"


def test_new_id_prefixes_and_uniqueness():
    ids = {presets.new_id("loadout") for _ in range(50)}
    assert len(ids) == 50
    assert all(i.startswith("lp_") for i in ids)
    assert presets.new_id("weapon").startswith("wp_")


def test_preset_files_are_not_the_bundled_gunslots():
    """用户预设与随包数据必须物理隔离，绝不能写回 data/gunslots.json。"""
    for kind in presets.KINDS:
        path = Path(presets.store_path(kind, str(ROOT / "data")))
        assert path.name != "gunslots.json"
        assert path.parent.name == "data"      # 仅证明命名不同，真实落盘由 default_storage_dir 决定
    assert presets.store_path("loadout").find("gunslots") == -1


# --------------------------------------------------------------- 结构校验

def test_normalize_loadout_fills_id_and_timestamps():
    rec = presets.normalize_preset("loadout", loadout())
    assert rec["id"].startswith("lp_")
    assert rec["name"] == "测试方案"
    assert rec["slots"] == {"helmet": "item-a"}
    assert rec["createdAt"].endswith("Z")
    assert rec["updatedAt"] == rec["createdAt"]


def test_normalize_rejects_bad_id_name_slots_and_price_mode():
    bad = [
        loadout(id="含中文"),
        loadout(name="   "),
        {"name": "x", "slots": ["helmet"]},
        {"name": "x", "slots": {"helmet": ""}},
        loadout(priceMode="rmb"),
    ]
    for raw in bad:
        with pytest.raises(presets.PresetError):
            presets.normalize_preset("loadout", raw)


def test_normalize_weapon_requires_gun_id():
    rec = presets.normalize_preset("weapon", weapon())
    assert rec["gunId"] == "gun-ak"
    assert rec["items"] == {"muzzle": "mod-1"}
    with pytest.raises(presets.PresetError):
        presets.normalize_preset("weapon", {"name": "无枪", "items": {}})


def test_normalize_store_rejects_duplicate_ids():
    raw = {"presets": [loadout(id="lp_a"), loadout(id="lp_a")]}
    with pytest.raises(presets.PresetError):
        presets.normalize_store("loadout", raw)


# --------------------------------------------------------------- 读写与损坏保护

def test_load_missing_returns_empty(tmp_path):
    store = presets.load("loadout", str(tmp_path))
    assert store == {"version": 1, "kind": "loadout", "presets": []}


def test_save_roundtrip_leaves_no_tmp(tmp_path):
    store = presets.normalize_store("loadout", {"presets": [loadout()]})
    saved = presets.save("loadout", store, str(tmp_path))
    assert len(saved["presets"]) == 1
    again = presets.load("loadout", str(tmp_path))
    assert again["presets"][0]["name"] == "测试方案"
    assert not (tmp_path / "loadout-presets.json.tmp").exists()
    raw = json.loads((tmp_path / "loadout-presets.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1 and raw["kind"] == "loadout"


def test_corrupt_file_is_reported_and_not_overwritten(tmp_path):
    path = tmp_path / "loadout-presets.json"
    path.write_text("{ 这不是 JSON", encoding="utf-8")
    with pytest.raises(presets.PresetError) as info:
        presets.load("loadout", str(tmp_path))
    assert info.value.corrupt is True
    with pytest.raises(presets.PresetError) as info:
        presets.save("loadout", presets.normalize_store("loadout", {"presets": []}), str(tmp_path))
    assert info.value.corrupt is True
    assert path.read_text(encoding="utf-8") == "{ 这不是 JSON"


def test_repair_flag_allows_overwriting_corrupt_file(tmp_path):
    path = tmp_path / "loadout-presets.json"
    path.write_text("not json", encoding="utf-8")
    store = presets.normalize_store("loadout", {"presets": [loadout()]})
    presets.save("loadout", store, str(tmp_path), repair=True)
    assert json.loads(path.read_text(encoding="utf-8"))["presets"][0]["name"] == "测试方案"


# --------------------------------------------------------------- upsert / remove / import

def test_upsert_add_then_overwrite_keeps_created_at():
    store = presets.empty_store("loadout")
    store, rec = presets.upsert("loadout", loadout(), store)
    assert len(store["presets"]) == 1
    store2, rec2 = presets.upsert("loadout", dict(loadout(name="改名了"), id=rec["id"]), store)
    assert len(store2["presets"]) == 1
    assert rec2["name"] == "改名了"
    assert rec2["createdAt"] == rec["createdAt"]


def test_remove_missing_reports_error():
    store = presets.empty_store("weapon")
    with pytest.raises(presets.PresetError) as info:
        presets.remove("weapon", "wp_nope1234", store)
    assert info.value.code == "missing"


def test_import_conflict_gets_new_id():
    existing = presets.normalize_store("loadout", {"presets": [loadout(id="lp_fixed0001")]})
    store, rec = presets.import_one("loadout", loadout(id="lp_fixed0001", name="导入的"), existing)
    assert len(store["presets"]) == 2
    assert rec["id"] != "lp_fixed0001"
    assert rec["name"] == "导入的"


def test_import_bundle_adds_every_preset():
    store, out = presets.import_one("weapon", {"presets": [weapon(name="A"), weapon(name="B")]},
                                    presets.empty_store("weapon"))
    assert out == {"count": 2}
    assert [p["name"] for p in store["presets"]] == ["A", "B"]


# --------------------------------------------------------------- HTTP 接口

@pytest.fixture
def server(tmp_path):
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(tmp_path))
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


def test_api_presets_crud_via_http(server):
    base, tmp = server
    status, body = get_json(base + "api/presets?kind=loadout")
    assert status == 200 and body["count"] == 0
    assert body["path"].endswith("loadout-presets.json")

    status, body = post_json(base + "api/presets",
                             {"kind": "loadout", "action": "save", "preset": loadout(name="夜间方案")})
    assert status == 200 and body["count"] == 1
    pid = body["preset"]["id"]
    assert (tmp / "loadout-presets.json").is_file()

    status, body = post_json(base + "api/presets",
                             {"kind": "loadout", "action": "save",
                              "preset": dict(loadout(name="夜间方案 v2"), id=pid)})
    assert status == 200 and body["count"] == 1 and body["preset"]["name"] == "夜间方案 v2"

    status, body = post_json(base + "api/presets", {"kind": "loadout", "action": "delete", "id": pid})
    assert status == 200 and body["count"] == 0
    status, body = post_json(base + "api/presets", {"kind": "loadout", "action": "delete", "id": pid})
    assert status == 400 and body["code"] == "missing"


def test_api_presets_import_and_kind_isolation(server):
    base, tmp = server
    status, body = post_json(base + "api/presets",
                             {"kind": "weapon", "action": "import", "data": weapon(name="AK 出厂")})
    assert status == 200 and body["count"] == 1
    assert (tmp / "weapon-presets.json").is_file()
    assert not (tmp / "loadout-presets.json").exists()

    status, body = get_json(base + "api/presets?kind=weapon")
    assert status == 200 and body["presets"][0]["name"] == "AK 出厂"


def test_api_presets_corrupt_file_returns_409_and_stays_intact(server):
    base, tmp = server
    path = tmp / "loadout-presets.json"
    path.write_text('{"presets": [', encoding="utf-8")
    status, body = get_json(base + "api/presets?kind=loadout")
    assert status == 409 and body["corrupt"] is True
    status, body = post_json(base + "api/presets",
                             {"kind": "loadout", "action": "save", "preset": loadout()})
    assert status == 409 and body["corrupt"] is True
    assert path.read_text(encoding="utf-8") == '{"presets": ['
    status, body = post_json(base + "api/presets",
                             {"kind": "loadout", "action": "save", "preset": loadout(), "repair": True})
    assert status == 200 and body["count"] == 1


def test_api_presets_rejects_bad_requests(server):
    base, _ = server
    status, body = get_json(base + "api/presets?kind=gold")
    assert status == 400 and body["code"] == "kind"
    status, body = post_json(base + "api/presets", {"kind": "loadout", "action": "explode"})
    assert status == 400
    status, body = post_json(base + "api/presets", {"kind": "loadout", "preset": {"name": ""}})
    assert status == 400 and body["ok"] is False
