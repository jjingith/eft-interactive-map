"""R279：OCR 模型目录在冻结产物里也要能找到（截图识别「没反应」的根因）。

PyInstaller 把 ocr.py 放进 `_internal`，`PROJECT_ROOT` 因此变成产物根目录，
而模型实际在 `_internal/assets/ocr`——原来那条路径指不到模型，
`/api/ocr/recognize` 一律 503，用户看到的就是「框选完什么都没发生」。
这里锁住探测顺序：_MEIPASS → exe/_internal → exe → 源码仓库。
"""

from __future__ import annotations

import os
import sys

import ocr


def _make_assets(base: str) -> str:
    path = os.path.join(base, "assets", "ocr")
    os.makedirs(path, exist_ok=True)
    for name in ocr.OCR_FILES:
        with open(os.path.join(path, name), "wb") as fh:
            fh.write(b"x")
    return path


def test_source_tree_resolves_to_repo_assets():
    path = ocr.resolve_assets_dir()
    assert os.path.isdir(path)
    for name in ocr.OCR_FILES:
        assert os.path.isfile(os.path.join(path, name)), "源码树里 %s 必须找得到" % name


def test_frozen_prefers_meipass(tmp_path, monkeypatch):
    frozen = _make_assets(str(tmp_path / "_mei"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_mei"), raising=False)
    assert ocr.resolve_assets_dir() == frozen


def test_frozen_falls_back_to_internal(tmp_path, monkeypatch):
    """没有 _MEIPASS（部分引导模式不给）时按 exe 同级 _internal 找。"""
    exe_dir = tmp_path / "EFTMap"
    internal = exe_dir / "_internal"
    assets = _make_assets(str(internal))
    fake_exe = exe_dir / "EFTMap.exe"
    exe_dir.mkdir(parents=True, exist_ok=True)
    fake_exe.write_bytes(b"MZ")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    assert ocr.resolve_assets_dir() == assets


def test_missing_models_reports_lookup_dir(tmp_path, monkeypatch):
    empty = tmp_path / "empty-assets"
    empty.mkdir()
    monkeypatch.setattr(ocr, "resolve_assets_dir", lambda: str(empty))
    ok, hint = ocr.check_available()
    assert ok is False
    assert "assets/ocr" in hint and str(empty) in hint, "报错要带上实际查找目录，便于远程排障"


def test_unknown_layout_falls_back_to_repo_assets(tmp_path, monkeypatch):
    """所有冻结候选都空时回退源码路径——开发机不会被误判成「模型缺失」。"""
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_mei"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "nowhere" / "EFTMap.exe"))
    path = ocr.resolve_assets_dir()
    for name in ocr.OCR_FILES:
        assert os.path.isfile(os.path.join(path, name))
