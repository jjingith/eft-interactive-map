"""R277d：打包版（PyInstaller onedir）资源路径回归。

冻结后 `serve.__file__` 在 `<exe>/_internal/serve.py`，`ROOT` 会算成 exe 目录，
而 `--add-data` 的资源实际落在 `_internal`。云证书找不到会让会员、行情、
激活码兑换全部 502，所以这里锁住候选路径兜底。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_ca_path_falls_back_to_internal_dir(tmp_path, monkeypatch):
    import serve

    # 模拟冻结布局：exe 目录下没有 assets，_internal 里有
    exe_dir = tmp_path / "EFTMap"
    internal = exe_dir / "_internal"
    (internal / "assets").mkdir(parents=True)
    ca = internal / "assets" / "cloud-ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")

    monkeypatch.setattr(serve, "ROOT", str(exe_dir))
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "EFTMap.exe"), raising=False)

    assert serve._cloud_ca_path() == str(ca)
    client = serve.make_cloud_client(str(tmp_path / "cfg"))
    assert client.ca_path == str(ca) and os.path.isfile(client.ca_path)


def test_ca_path_prefers_repo_assets_in_source_mode(monkeypatch):
    import serve

    expected = os.path.join(serve.ROOT, "assets", "cloud-ca.pem")
    assert os.path.isfile(expected), expected
    monkeypatch.setattr(sys, "_MEIPASS", "/nonexistent", raising=False)
    assert serve._cloud_ca_path() == expected


def test_make_cloud_client_no_longer_uses_bare_root_join():
    """防止有人把兜底改回去（打包版会 502）。"""
    source = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
    assert "def _cloud_ca_path()" in source
    assert 'os.path.join(ROOT, "assets", "cloud-ca.pem")' in source
    assert '"cloud-ca.pem"' in source
    assert 'getattr(sys, "_MEIPASS", None)' in source
    assert '"_internal", "assets", "cloud-ca.pem"' in source
