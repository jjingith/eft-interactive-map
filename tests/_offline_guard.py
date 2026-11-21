"""离线铁律的判定口径（测试辅助模块，名字带下划线，不会被 pytest 当测试收集）。

## 为什么要改判据

原来的写法是一刀切：

    assert "https://" not in body

简单，但把两件事混成了一件：

* **页面自己去下载外部资源** —— 这才是「零运行期联网」真正要拦的
  （`fetch` 外部地址、`<script src>` 外链、`url()` 引外部图片、`@import` 外部样式…）；
* **用户点一下跳去攻略站** —— 导航行为，页面自身一个字节都不下载
  （`a.href = "https://tarkov.dev/task/…"` + `target="_blank"`）。

任务栏的「查看攻略」属于后者，但会被旧判据判成违规。所以这里改成两步，
**保护范围反而比原来更宽也更准**：

1. 扫「加载型」模式，命中即失败（旧判据根本不管这些）；
2. 抽出文件里出现的**每一个**外部地址，逐个对照白名单 —— 白名单外的地址照样失败。

白名单每一项都必须写明「为什么它不算运行期联网」，避免它慢慢变成一张随便加的表。
"""

from __future__ import annotations

import re

# 允许出现的外部地址（前缀匹配）。新增一条前先问：页面会因为它发起请求吗？
ALLOWED_PREFIXES = {
    "https://tarkov.dev/task/":
        "任务栏「查看攻略」：只给 <a> 设 href，用户点击后在新标签打开，页面自身不加载",
    "http://www.w3.org/":
        "SVG / XML 命名空间（xmlns），只是标识符，不会发起任何请求",
    "http://127.0.0.1":
        "提示文本里的本机地址，指向本服务自己",
    "http://localhost":
        "提示文本里的本机地址，指向本服务自己",
}

# 一旦出现就说明「页面真的会去外面取东西」的写法。
# 注意刻意**不**收录 XMLHttpRequest / new Image()：它们本身是通用 API，
# 常用来请求本地接口或预载本地图标，跟「外部资源」无关。
LOADING_PATTERNS = (
    (r"""\bfetch\s*\(\s*['"`]https?://""", "fetch 外部地址"),
    (r"""\bimport\s*\(\s*['"`]https?://""", "动态 import 外部地址"),
    (r"""\bnew\s+(?:Worker|EventSource|WebSocket|SharedWorker)\s*\(\s*['"`](?:https?|wss?)://""",
     "构造到外部地址的连接"),
    (r"""<script[^>]+src\s*=\s*['"]https?://""", "<script> 引外部脚本"),
    (r"""<link[^>]+href\s*=\s*['"]https?://""", "<link> 引外部样式/资源"),
    (r"""<img[^>]+src\s*=\s*['"]https?://""", "<img> 引外部图片"),
    (r"""url\(\s*['"]?\s*https?://""", "CSS url() 引外部资源"),
    (r"""@import\s+(?:url\s*\()?\s*['"]?https?://""", "CSS @import 外部样式"),
)

# URL 提取：遇到引号、空白、括号、尖括号即止（够覆盖 JS 字符串与 HTML 属性两种写法）
_URL_RE = re.compile(r"""https?://[^\s"'`<>)\]]+""")


def external_urls(body: str) -> list[str]:
    """文件里出现过的所有 http(s) 地址（去重 + 排序，便于报错时一眼看全）。"""
    return sorted(set(_URL_RE.findall(body or "")))


def unlisted_urls(body: str, allowed: dict | None = None) -> list[str]:
    """不在白名单前缀里的地址。"""
    table = ALLOWED_PREFIXES if allowed is None else allowed
    return [url for url in external_urls(body) if not any(url.startswith(p) for p in table)]


def loading_hits(body: str) -> list[tuple[str, str]]:
    """命中的「加载型」写法 → `[(说明, 片段)]`。"""
    out = []
    text = body or ""
    for pattern, label in LOADING_PATTERNS:
        match = re.search(pattern, text)
        if match:
            out.append((label, match.group(0)[:80]))
    return out


def assert_offline(body: str, path: str, allowed: dict | None = None) -> None:
    """断言：这个文件**不会在运行期加载外部资源**，也没出现未登记的外部地址。"""
    hits = loading_hits(body)
    assert not hits, "%s 出现运行期加载外部资源：%s" % (path, hits)

    extra = unlisted_urls(body, allowed)
    assert not extra, (
        "%s 出现了未登记的外部地址：%s\n"
        "如果它只是「用户点击才跳转」的链接，请到 tests/_offline_guard.py 的 "
        "ALLOWED_PREFIXES 里登记并写明理由；如果页面真的会去加载它，那就是违规。"
        % (path, extra))
