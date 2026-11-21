"""`tests/_offline_guard.py` 自身的测试：证明新判据**比旧判据更严**，而不是放水。

旧判据是 `assert "https://" not in body`，一句话搞定；新判据多了白名单，
所以必须证明三件事：

1. 真正会联网的写法一律拦住（fetch / 外链脚本 / 外链样式 / CSS url() / 动态 import / 外部连接）；
2. 只有「用户点击才跳转」的地址能过，而且**必须登记**（没登记的域名照样失败）；
3. 原来能过的干净文件依然全过。
"""

from __future__ import annotations

import pytest

from _offline_guard import ALLOWED_PREFIXES, assert_offline, external_urls, loading_hits, unlisted_urls


# --------------------------------------------------------------- 该拦的必须拦住

@pytest.mark.parametrize("snippet,label", [
    ("""fetch("https://evil.example/api")""", "fetch 外部地址"),
    ("""await import("https://evil.example/m.js")""", "动态 import 外部地址"),
    ("""new WebSocket("wss://evil.example/ws")""", "构造到外部地址的连接"),
    ("""new EventSource("https://evil.example/sse")""", "构造到外部地址的连接"),
    ("""<script src="https://evil.example/a.js"></script>""", "<script> 引外部脚本"),
    ("""<link rel="stylesheet" href="https://evil.example/a.css">""", "<link> 引外部样式/资源"),
    ("""<img src="https://evil.example/a.png">""", "<img> 引外部图片"),
    ("background: url(https://evil.example/bg.png)", "CSS url() 引外部资源"),
    ("@import url(https://evil.example/a.css);", "CSS @import 外部样式"),
])
def test_loading_patterns_are_rejected(snippet, label):
    """只要页面会去外面取东西，哪怕地址在白名单域名下也不放行。"""
    hits = loading_hits(snippet)
    assert hits, "这个写法应该被拦下：%s" % snippet
    assert any(h[0] == label for h in hits), hits


def test_loading_pattern_is_rejected_even_on_allowlisted_host():
    """白名单只豁免「地址出现」，不豁免「拿它去加载」。"""
    with pytest.raises(AssertionError, match="运行期加载外部资源"):
        assert_offline("""fetch("https://tarkov.dev/task/1")""", "x.js")


# --------------------------------------------------------------- 该放的才放

def test_navigation_only_link_passes():
    body = ('guide.target = "_blank";\n'
            'guide.rel = "noopener";\n'
            'guide.href = "https://tarkov.dev/task/" + id;')
    assert_offline(body, "tasks.js")            # 不抛异常即通过


def test_xml_namespace_passes():
    """`xmlns="http://www.w3.org/2000/svg"` 只是标识符，不发起请求。"""
    assert_offline('var NS = "http://www.w3.org/2000/svg";', "app.js")


def test_local_service_address_passes():
    assert_offline('提示：<code>http://127.0.0.1:8787/</code>', "app.js")


# --------------------------------------------------------------- 白名单不是摆设

def test_unregistered_host_fails():
    """没登记过的域名照样失败——白名单是白名单，不是免死金牌。"""
    with pytest.raises(AssertionError, match="未登记的外部地址"):
        assert_offline('a.href = "https://someone-else.example/page";', "x.js")


def test_unregistered_host_message_tells_how_to_register():
    with pytest.raises(AssertionError, match="ALLOWED_PREFIXES"):
        assert_offline('a.href = "https://someone-else.example/page";', "x.js")


def test_every_allow_entry_has_a_reason():
    """白名单每一条都必须写清楚「为什么它不算运行期联网」，防止它变成随手加的表。"""
    for prefix, reason in ALLOWED_PREFIXES.items():
        assert prefix.startswith(("http://", "https://")), prefix
        assert len(reason) >= 10, "白名单条目缺少理由：%s" % prefix


# --------------------------------------------------------------- 工具函数

def test_external_urls_dedupes_and_sorts():
    body = ('"https://b.example/x" "https://a.example/y" "https://a.example/y" '
            '"http://www.w3.org/2000/svg"')
    assert external_urls(body) == ["http://www.w3.org/2000/svg",
                                   "https://a.example/y", "https://b.example/x"]


def test_unlisted_urls_reports_only_the_unknown_ones():
    body = '"https://tarkov.dev/task/1" "https://evil.example/x"'
    assert unlisted_urls(body) == ["https://evil.example/x"]


def test_empty_body_is_clean():
    assert external_urls("") == []
    assert loading_hits("") == []
    assert_offline("", "empty.js")
