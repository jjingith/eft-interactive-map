"""pytest 公共配置：把 tools/ 加入导入路径，供测试直接 import 模块。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
