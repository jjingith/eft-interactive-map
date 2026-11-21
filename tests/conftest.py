"""pytest 公共配置：把 tools/ 加入导入路径，供测试直接 import 模块。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


@pytest.fixture(autouse=True)
def _reset_member_state(tmp_path, monkeypatch):
    """R108：会员态是进程内缓存（服务端下发），用例之间必须隔离，避免跨文件泄漏。

    R255：云端拉取 20 分钟节流也是进程内缓存（_cloud_fetch_at / _cloud_last），
    同样会在用例间泄漏——用固定 now 的会员云端用例先后跑时，前者会把记录记成同一
    时间戳，导致后者被节流返回缓存而非重新打云端。每个用例前后一并清空。
    """
    import config
    import prices_source

    # R273：本机试用记录一律写进用例临时目录，绝不碰真实的
    # %APPDATA%\EFTMap\local-trial.json（注册 / 登录用例都会写这个文件）。
    monkeypatch.setattr(config, "trial_path",
                        lambda directory=None: str(tmp_path / "local-trial.json"))

    def _reset_trial():
        # R273：新注册赠送 3 天试用是**本机文件**（local-trial.json）。
        # 测试机上一旦真跑过注册，这个文件就会让 is_member() 变 True，
        # 用例之间 / 本机 ↔ CI 结果都会不一致，所以每个用例强制「无试用」。
        config._trial_cache = None
        config._trial_loaded = True

    config.set_member_state(None)
    _reset_trial()
    prices_source.reset_cloud_throttle()
    yield
    config.set_member_state(None)
    _reset_trial()
    prices_source.reset_cloud_throttle()

