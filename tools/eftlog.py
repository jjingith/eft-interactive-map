#!/usr/bin/env python3
"""EFT 游戏日志跟随与解析（运行期，纯标准库）

**只读日志文件**，不读游戏内存、不注入进程——和截图定位一样是「只看文件」的离线做法。

## 日志目录形态

    <游戏目录>/Logs/log_<日期>_<时-分-秒>_<版本>_<pid>/
        <会话名> application_000.log
        <会话名> backend_000.log
        <会话名> push-notifications_000.log
        <会话名> errors_000.log
        ...

每次启动游戏生成一个新的会话文件夹（名字里带日期时间，字典序即时间序），本模块始终
跟随**最新**的那个会话。文件名 = 会话文件夹名 + 空格 + 通道名 + `_000.log`。

## 能可靠拿到的信号（都用真实日志实测确认，见 tests/test_eftlog.py）

战局生命周期（`application_000.log`）：

| 日志行 | 含义 |
| --- | --- |
| `MatchingCompleted:0 real:0 diff:0` | 开始匹配 |
| `scene preset path:maps/<id>_preset.bundle rcid:<id>.ScenesPreset.asset` | 本局地图 id |
| `LocationLoaded:...` | 开始加载战局（场景加载完成） |
| `[Transit] Flag:Common, RaidId:<id>, Count:0, Locations:<Map> -> ` | 战局 id |
| `PlayerSpawnEvent:...` | 战局开始（玩家出生） |
| `backend_000.log` 的 `client/match/local/end` 请求 | 战局结束 |

任务进度（**日志本身的硬限制**）：`backend_000.log` 里 `client/quest/list`、`client/quest/fail`
的请求行**响应体为空**，拿不到条件级进度。唯一可靠来源是 `push-notifications_000.log` 里的
JSON 推送：

    {"type":"new_message", ... "message":{"text":"quest started",
     "templateId":"<questId> description|successMessageText","hasRewards":bool,"items":{...}}}

- `templateId` 以 `description` 结尾 = 任务开始；
- 以 `successMessageText` 结尾 = 任务完成（`hasRewards` 为真时 `items.data` 是奖励物列表）。

任务失败信号在 `errors_000.log`：`Quest with id <id> wasn't found! Side = Scav`。

因此本项目只做「事件流 + 本局计数」，**不做条件级进度**——日志给不了。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

APPLICATION = "application"
BACKEND = "backend"
PUSH = "push-notifications"
ERRORS = "errors"
OUTPUT = "output"
CHANNELS = (APPLICATION, BACKEND, PUSH, ERRORS)

# 控制绑定只在 application / output 通道的**文件头部**（实测在 application 第 161 行），
# 单看尾部窗口可能读不到，所以同步按键要单独扫这两个通道的开头。
SCAN_CHANNELS = (APPLICATION, OUTPUT)
KEY_SCAN_BYTES = 8 * 1024 * 1024       # 只扫文件头 ~8 MiB，够覆盖控制绑定那一行

SCREENSHOT_KEY_NAME = "MakeScreenshot"

# 会话文件夹名：log_2026.10.17_19-42-17_1.2.5.0.48146
# 尾巴是「版本.构建」连写（实测既有 1.1.0.1.46777 也有 1.2.5.0.48146），不做更细的拆解。
SESSION_RE = re.compile(r"^log_\d{4}\.\d{2}\.\d{2}_\d{2}-\d{2}-\d{2}_[\dA-Za-z.]+$")

TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")
MAP_RE = re.compile(r"scene preset path:maps/(?P<id>[A-Za-z0-9_]+)_preset\.bundle")
RAID_ID_RE = re.compile(r"\[Transit\][^,]*,\s*RaidId:(?P<id>[0-9a-fA-F]+)")
MATCH_END_RE = re.compile(r"client/match/local/end")
QUEST_FAIL_RE = re.compile(r"Quest with id (?P<id>\w+) wasn't found")

QUEST_START_SUFFIX = " description"
QUEST_DONE_SUFFIX = " successMessageText"


# ---------------------------------------------------------------- 目录/文件
def latest_session(logs_dir: str) -> str | None:
    """最新（名字最大）的会话文件夹；没有会话返回 None。"""
    try:
        names = os.listdir(logs_dir)
    except OSError:
        return None
    candidates = [n for n in names if SESSION_RE.match(n) and os.path.isdir(os.path.join(logs_dir, n))]
    if not candidates:
        return None
    return os.path.join(logs_dir, max(candidates))


def session_base(session_dir: str) -> str:
    """会话目录里日志文件名的前缀。

    注意目录名与文件名的差别（实测）：目录是 `log_<会话名>`，文件是 `<会话名> <通道>_000.log`，
    即文件名里的会话名**不带 `log_` 前缀**。优先从实际文件反推，避免猜错。
    """
    try:
        for name in os.listdir(session_dir):
            if name.endswith(" application_000.log"):
                return name[: -len(" application_000.log")]
    except OSError:
        pass
    base = os.path.basename(session_dir)
    return base[4:] if base.startswith("log_") else base


def channel_path(session_dir: str, channel: str, base: str | None = None) -> str:
    """会话目录里某个通道的日志文件路径。"""
    return os.path.join(session_dir, "%s %s_000.log" % (base or session_base(session_dir), channel))


# ---------------------------------------------------------------- 行解析
def _extract_ts(line: str) -> str | None:
    m = TS_RE.match(line)
    return m.group("ts") if m else None


def _ev(kind: str, ts: str | None, **data) -> dict:
    payload = {"type": kind, "ts": ts}
    payload.update(data)
    return payload


def merge_raid(prev: dict | None, ev: dict) -> dict:
    """把单条 raid 事件并入累计的战局状态。

    地图 id 与战局 id 出现在不同的日志行里，而快照只保存「最新一条」，
    所以要自带前文，页面无论何时接入都能知道当前是哪张图、哪一局。
    """
    prev = prev or {}
    phase = ev["phase"]
    if phase == "matching":
        prev = {}                       # 新一轮匹配：地图与战局 id 都还没定下来
    return {
        "type": "raid",
        "ts": ev.get("ts") or prev.get("ts"),
        "phase": phase,
        "mapId": ev.get("mapId") or prev.get("mapId"),
        "raidId": ev.get("raidId") or (None if phase == "matching" else prev.get("raidId")),
    }


def split_balanced(text: str) -> tuple[list[str], str]:
    """从文本里切出**完整且括号配平**的 JSON 对象串，返回 (对象串列表, 未闭合的尾巴)。

    只按 `{}` 配平（字符串里的括号不计），非 JSON 的前后杂文本会被丢弃——
    日志里 JSON 推送是多行的，必须靠配平才能把整块捞出来。
    """
    objects: list[str] = []
    depth = 0
    start: int | None = None
    in_str = False
    escaped = False
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(text[start:i + 1])
                    start = None
    if depth > 0 and start is not None:
        return objects, text[start:]
    return objects, ""


def _dt_to_ts(dt: Any) -> str | None:
    """推送里的 `dt`（unix 秒）→ 与日志行一致的 `YYYY-MM-DD HH:MM:SS.mmm` 本地时间。"""
    if not isinstance(dt, (int, float)) or dt <= 0:
        return None
    sec = int(dt)
    ms = int(round((dt - sec) * 1000))
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sec)) + ".%03d" % ms


def parse_notification(block: str) -> dict | None:
    """把一段 JSON 推送解析成 quest 事件；不是任务通知返回 None（任何解析失败都吞掉）。"""
    try:
        obj = json.loads(block)
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "new_message":
        return None
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return None
    tpl = msg.get("templateId")
    if not isinstance(tpl, str) or " " not in tpl:
        return None
    quest_id = tpl.split(" ", 1)[0].strip()
    if not quest_id:
        return None
    ts = _dt_to_ts(msg.get("dt"))
    if tpl.endswith(QUEST_START_SUFFIX):
        return _ev("quest", ts, action="started", questId=quest_id)
    if tpl.endswith(QUEST_DONE_SUFFIX):
        items = msg.get("items")
        data = items.get("data") if isinstance(items, dict) else None
        count = len(data) if isinstance(data, list) else 0
        return _ev("quest", ts, action="completed", questId=quest_id,
                   rewards=count, hasRewards=bool(msg.get("hasRewards")))
    return None


# ---------------------------------------------------------------- 控制绑定（同步截图键）
def _walk_keybindings(obj) -> Any:
    """在解析出的 JSON 里递归找 `keyBindings` 字段（外层可能还包了一层）。"""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("keyBindings") is not None:
                return cur["keyBindings"]
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def _first_keycode(variant) -> str | None:
    """从一个绑定变体里取第一个键名（键码可能是字符串或字符串列表）。"""
    if isinstance(variant, str):
        return variant.strip() or None
    if not isinstance(variant, dict):
        return None
    for field in ("keyCode", "key", "code"):
        value = variant.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def _keycode_of(entry) -> str | None:
    """从 `keyBindings` 里的一项取出按键名：优先 `variants`，没有就直接看顶层。"""
    if isinstance(entry, dict):
        variants = entry.get("variants")
        if isinstance(variants, list):
            for variant in variants:
                code = _first_keycode(variant)
                if code:
                    return code
            return None
    return _first_keycode(entry)


def _collect_keybindings(bindings, out: dict) -> None:
    """把 `keyBindings`（列表或字典）收敛成 `{keyName: 按键名}`。"""
    if isinstance(bindings, dict):
        for name, value in bindings.items():
            code = _keycode_of(value)
            if code:
                out[name] = code
        return
    if isinstance(bindings, list):
        for entry in bindings:
            if not isinstance(entry, dict):
                continue
            name = entry.get("keyName") or entry.get("name") or entry.get("action")
            code = _keycode_of(entry)
            if name and code:
                out[name] = code


def parse_controls_keys(text: str) -> dict:
    """从一段日志文本里找出控制绑定 JSON，返回 `{keyName: 按键名}`；找不到返回 {}。

    日志里这套绑定被整段打成一个 JSON 对象（含 `keyBindings`），同一段文本里还可能有
    别的 JSON 行，所以逐块配平、逐块尝试，命中 `keyBindings` 才收下。
    """
    blocks, _ = split_balanced(text)
    for block in blocks:
        try:
            obj = json.loads(block)
        except ValueError:
            continue
        bindings = _walk_keybindings(obj)
        if bindings is None:
            continue
        out: dict = {}
        _collect_keybindings(bindings, out)
        if out:
            return out
    return {}


def pick_screenshot_key(bindings: dict) -> str | None:
    """从 `{keyName: 按键名}` 里取游戏内截图键（`MakeScreenshot`）。"""
    for name, key in bindings.items():
        if str(name).lower() == SCREENSHOT_KEY_NAME.lower():
            return key
    return None


def scan_screenshot_key(path: str, head_bytes: int = KEY_SCAN_BYTES) -> str | None:
    """扫某个日志文件的**头部**，取出截图按键；读不了 / 没有返回 None。"""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(head_bytes)
    except OSError:
        return None
    if not raw:
        return None
    return pick_screenshot_key(parse_controls_keys(raw.decode("utf-8", errors="replace")))


def read_screenshot_key(game_dir: str | None, head_bytes: int = KEY_SCAN_BYTES) -> str | None:
    """从最新会话的控制绑定里同步游戏内截图按键；取不到返回 None。"""
    if not game_dir:
        return None
    session = latest_session(os.path.join(game_dir, "Logs"))
    if session is None:
        return None
    base = session_base(session)
    for channel in SCAN_CHANNELS:
        key = scan_screenshot_key(channel_path(session, channel, base), head_bytes)
        if key:
            return key
    return None


class LineParser:
    """把单个通道的日志行变成事件；push 通道需要跨行缓冲 JSON。"""

    MAX_JSON_BUFFER = 2_000_000

    def __init__(self):
        self._json = ""
        self._raid_id: str | None = None

    def feed(self, channel: str, line: str) -> list[dict]:
        if channel == PUSH:
            return self._feed_push(line)
        return self._feed_text(channel, line)

    # -------------------------------------------------- 文本通道
    def _feed_text(self, channel: str, line: str) -> list[dict]:
        ts = _extract_ts(line)
        if channel == APPLICATION:
            return self._feed_application(ts, line)
        if channel == BACKEND:
            if MATCH_END_RE.search(line):
                return [_ev("raid", ts, phase="end")]
            return []
        if channel == ERRORS:
            m = QUEST_FAIL_RE.search(line)
            if m:
                return [_ev("quest", ts, action="failed", questId=m.group("id"))]
            return []
        return []

    def _feed_application(self, ts: str | None, line: str) -> list[dict]:
        out: list[dict] = []
        if "MatchingCompleted" in line:
            out.append(_ev("raid", ts, phase="matching"))
        m = MAP_RE.search(line)
        if m:
            out.append(_ev("raid", ts, phase="map", mapId=m.group("id").lower()))
        if "LocationLoaded" in line:
            out.append(_ev("raid", ts, phase="loading"))
        if "PlayerSpawnEvent" in line:
            out.append(_ev("raid", ts, phase="start", raidId=self._raid_id))
        # Transit 行在 PlayerSpawnEvent 之前出现，先把战局 id 记下来，出生时一并给出
        m = RAID_ID_RE.search(line)
        if m:
            self._raid_id = m.group("id")
        return out

    # -------------------------------------------------- JSON 通道
    def _feed_push(self, line: str) -> list[dict]:
        self._json += line + "\n"
        if len(self._json) > self.MAX_JSON_BUFFER:
            self._json = self._json[-self.MAX_JSON_BUFFER:]
        blocks, self._json = split_balanced(self._json)
        out: list[dict] = []
        for block in blocks:
            ev = parse_notification(block)
            if ev:
                out.append(ev)
        return out


# ---------------------------------------------------------------- 跟随
class LogFollower:
    """后台线程跟随「最新会话」的日志，增量读出新行并产出事件。

    降级行为：没配游戏目录 / 目录不存在 / 还没有会话 → 静默（`available=False` 并给出原因），
    地图其余功能不受影响。
    """

    MAX_QUESTS = 60            # 事件流面板只留最近这么多条，防止长期运行堆积
    INITIAL_TAIL = 1024 * 1024  # 新会话首次接入只回读尾部这么多字节（application 通道通常只有几十 KB）

    def __init__(self, game_dir: str | None = None, poll_interval: float = 1.0,
                 broadcaster: Any = None):
        self.game_dir = game_dir
        self.logs_dir = os.path.join(game_dir, "Logs") if game_dir else None
        self.poll_interval = poll_interval
        self.broadcaster = broadcaster
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._session: str | None = None
        self._base: str | None = None
        self._offsets: dict[str, int] = {}
        self._parser = LineParser()
        self._lock = threading.Lock()
        self._last_raid: dict | None = None
        self._quests: list[dict] = []
        self._reason: str | None = None
        # 截图键来自本会话的**文件头**控制绑定，扫一次就缓存；换会话才重扫
        self._screenshot_key: str | None = None
        self._key_session: str | None = None
        self._key_scanned = False

    # ------------------------------------------------------------ 状态
    def enabled(self) -> bool:
        return bool(self.logs_dir)

    def snapshot(self) -> dict[str, Any]:
        """当前日志跟随状态 + 已累积的战局/任务状态（SSE 首次连接与 `/api/logstate` 用）。"""
        with self._lock:
            reason, session = self._reason, self._session
            raid, quests = self._last_raid, list(self._quests)
        if not self.enabled():
            return {"available": False, "reason": "未配置游戏目录（无法监控游戏日志）",
                    "session": None, "logDir": None, "gameDir": None, "raid": None, "quests": []}
        return {
            "available": session is not None,
            "reason": reason,
            "session": os.path.basename(session) if session else None,
            "logDir": self.logs_dir,
            "gameDir": self.game_dir,
            "raid": raid,
            "quests": quests,
        }

    # ------------------------------------------------------------ 截图键
    def screenshot_key(self) -> str | None:
        """游戏内截图键（从最新会话的控制绑定里同步）；取不到返回 None。

        与「跟随日志」解耦：即使还没轮询过，也会自己去最新会话里找。按会话缓存，
        换会话（游戏重启）才重扫，避免每轮都去读文件头。
        """
        if not self.game_dir:
            return None
        with self._lock:
            session = self._session
        if self._key_scanned and self._key_session == session:
            return self._screenshot_key
        key = read_screenshot_key(self.game_dir)
        with self._lock:
            self._screenshot_key = key
            self._key_session = session
            self._key_scanned = True
        return key

    # ------------------------------------------------------------ 轮询
    def poll_once(self) -> list[dict]:
        """读一次新日志；返回本次产出的事件（同时已通过 broadcaster 广播）。"""
        if not self.enabled():
            return []
        if not os.path.isdir(self.logs_dir):
            with self._lock:
                self._reason = "游戏日志目录不存在：%s" % self.logs_dir
            return []
        session = latest_session(self.logs_dir)
        if session is None:
            with self._lock:
                self._reason = "日志目录里还没有会话文件夹（%s）" % self.logs_dir
            return []
        if session != self._session:
            # 换了新会话：清空偏移与解析器，从会话开头重新接入
            self._session = session
            self._base = session_base(session)
            self._offsets = {}
            self._parser = LineParser()
            with self._lock:
                self._reason = None

        events: list[dict] = []
        for channel in CHANNELS:
            events.extend(self._read_channel(channel, channel_path(session, channel, self._base)))
        if events:
            self._store(events)
            self._broadcast(events)
        return events

    def _read_channel(self, channel: str, path: str) -> list[dict]:
        try:
            size = os.path.getsize(path)
        except OSError:
            return []
        offset = self._offsets.get(path)
        if offset is None:
            offset = max(0, size - self.INITIAL_TAIL)     # 首次接入只回读尾部
        if size < offset:                                  # 文件被重建/截断
            offset = 0
        if size == offset:
            self._offsets[path] = offset
            return []
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                raw = fh.read()
        except OSError:
            return []
        if not raw:
            self._offsets[path] = offset
            return []
        if not raw.endswith(b"\n"):                        # 最后一行可能只写了一半，等下次
            cut = raw.rfind(b"\n")
            if cut == -1:
                self._offsets[path] = offset
                return []
            raw = raw[:cut + 1]
        self._offsets[path] = offset + len(raw)
        text = raw.decode("utf-8", errors="replace")
        out: list[dict] = []
        for line in text.splitlines():
            out.extend(self._parser.feed(channel, line))
        return out

    def _store(self, events: list[dict]):
        """累积战局与任务状态。

        raid 事件是**增量**的（地图 id 与战局 id 分别在不同行里出现），而快照只留最新一条，
        所以这里把前文串起来记，否则页面在中途打开时拿不到 mapId，也就没法自动切图。
        """
        with self._lock:
            for ev in events:
                if ev["type"] == "raid":
                    self._last_raid = merge_raid(self._last_raid, ev)
                elif ev["type"] == "quest":
                    self._quests.append(ev)
            if len(self._quests) > self.MAX_QUESTS:
                self._quests = self._quests[-self.MAX_QUESTS:]

    def _broadcast(self, events: list[dict]):
        if self.broadcaster is None:
            return
        for ev in events:
            self.broadcaster.publish_event(ev["type"], ev)

    # ------------------------------------------------------------ 线程
    def start(self):
        if not self.enabled() or self._thread is not None:
            return
        self.poll_once()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-log-watch")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:      # 任何意外都不该让监听线程死掉
                continue
