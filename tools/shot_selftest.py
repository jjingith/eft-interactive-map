#!/usr/bin/env python3
"""EFT 自动截图自检（运行期，纯标准库）。

## 为什么要有这个

「自动截图没反应」有六七种完全不同的原因，而它们在旧实现里**表现一模一样**：
页面显示「已发送 0 张」，或者更糟 —— 显示「已发送 N 张」但其实一个键都没送进游戏。

这个脚本把整条链路拆成 9 步逐项检查，每步都给出**可执行的下一步**，不用再猜。

## 用法

    python tools/shot_selftest.py                # 只读检查，不发任何按键
    python tools/shot_selftest.py --send         # 额外真的发一次截图键，并等到货结果
    python tools/shot_selftest.py --send --key Ctrl+F10

## 它检查什么

| # | 检查 | 失败说明 |
| --- | --- | --- |
| 1 | 平台 | 非 Windows 直接不支持 |
| 2 | 本工具是否管理员 | 影响第 4 步的判定 |
| 3 | 游戏进程在不在 | EFT 没运行 |
| 4 | 游戏是否前台 | 模拟按键只能打进本机前台窗口 |
| 5 | **权限是否对等** | 游戏管理员 + 工具普通 = SendInput 被 UIPI 静默丢弃 |
| 6 | 截图键解析 | 键名认不出 / 修饰键写法不对 |
| 7 | 注入方式 | PrintScreen 家族强制虚拟键码（扫描码对它无效） |
| 8 | 截图目录 | 不存在就没法校验「到底有没有拍到」 |
| 9 | 真发一次 + 到货校验 | 最权威的一条：目录里有没有出现新文件 |

## 边界

`--send` 会真的按一次键、并且要求游戏在前台（否则拒绝发送，免得把内容打进别的程序）。
不加 `--send` 时全程只读：不发键、不改任何文件。
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import eftlog          # noqa: E402
import keyinput        # noqa: E402
import screenshot      # noqa: E402
import serve           # noqa: E402

GAME_PROCESS = serve.GAME_PROCESS          # escapefromtarkov.exe
ARRIVAL_WAIT = 1.6                          # 发键后等多久再查目录（秒）

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"
INFO = "[ -- ]"

# VK_SNAPSHOT：PrintScreen / SysRq。Windows 11 默认把它拿去开截屏工具，游戏收不到。
_VK_SNAPSHOT = 0x2C


class Report:
    """收集检查结果，最后统一打印——这样即使中途某步失败也能把已知信息全给出来。"""

    def __init__(self):
        self.lines: list[tuple[str, str]] = []
        self.blocking: str | None = None
        self.sent = False

    def add(self, level: str, title: str, detail: str = ""):
        self.lines.append((level, "%s %s%s" % (level, title, ("：" + detail) if detail else "")))
        if level == FAIL and self.blocking is None:
            self.blocking = title

    def show(self):
        print()
        for _, line in self.lines:
            print(line)
        print()
        if self.blocking:
            print("结论：卡在「%s」——先解决这一条，其余检查才有意义。" % self.blocking)
        else:
            print("结论：这一轮没有发现硬阻塞。")
        print("（本次%s发送任何按键）" % ("已" if self.sent else "未"))


def _resolve_game_dir(explicit: str | None) -> str:
    """游戏目录：命令行 > 配置 > 自动探测。"""
    if explicit:
        return explicit
    cfg = config.load(config.app_dir()) or {}
    return cfg.get("game_dir") or serve.default_game_dir() or ""


def _resolve_shots_dir(explicit: str | None, game_dir: str) -> str:
    if explicit:
        return explicit
    cfg = config.load(config.app_dir()) or {}
    return cfg.get("screenshots_dir") or serve.default_screenshots_dir() or ""


def _foreground_desc() -> str:
    proc = keyinput.foreground_process_name()
    pid = keyinput.foreground_pid()
    if not proc:
        return "取不到（无前台窗口，或权限不足）"
    return "%s (pid %s)" % (os.path.basename(proc), pid if pid else "?")


# 日志尾部回放窗口：phase 是「最后状态」，读尾部足够；整份日志可能几十 MB，不能全读
LOG_TAIL_BYTES = 512 * 1024


def _log_phase(game_dir: str) -> tuple[str | None, str]:
    """回放最新会话的日志尾部，推出当前战局阶段 → `(phase, 说明)`。

    这一步对应 `AutoShotter` 的第二道门（`phase == "start"`）。**参考实现没有这道门**
    （它只要游戏在前台就发键），所以这道门一旦判错，表现就是「开关开着、一张都不发」。
    """
    if not game_dir:
        return None, "没有游戏目录，读不到日志"
    logs = os.path.join(game_dir, "Logs")
    if not os.path.isdir(logs):
        return None, "找不到 Logs 目录：%s" % logs
    try:
        session = eftlog.latest_session(logs)
        if not session:
            return None, "Logs 里没有可识别的会话目录"
        path = eftlog.channel_path(session, eftlog.APPLICATION, eftlog.session_base(session))
    except Exception as exc:        # 日志模块出问题不能中断自检
        return None, "读取会话失败：%s" % exc

    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > LOG_TAIL_BYTES:
                fh.seek(size - LOG_TAIL_BYTES)
                fh.readline()                   # 丢掉可能被截断的半行
            raw = fh.read()
    except OSError as exc:
        return None, "读不了 %s：%s" % (os.path.basename(path), exc)

    parser = eftlog.LineParser()
    raid = None
    for line in raw.decode("utf-8", "replace").splitlines():
        for event in parser.feed(eftlog.APPLICATION, line):
            if event.get("type") == "raid":
                raid = eftlog.merge_raid(raid, event)
    phase = (raid or {}).get("phase")
    where = os.path.basename(session)
    if phase is None:
        return None, "%s 里没读到战局阶段事件（可能是旧日志，或格式变了）" % where
    return phase, "%s（会话 %s）" % (phase, where)


def _wait_for_game_foreground(seconds: int, poll: float = 0.3) -> bool:
    """等游戏变成前台窗口，最多等 `seconds` 秒。

    为什么要等：这个脚本本身一启动就会把终端/IDE 顶到前台，而模拟按键只能打进前台窗口。
    如果启动时立刻判「不在前台」就放弃，那么从命令行驱动时永远测不了——
    所以改成「先喊一声，等用户切过去，切到了再发键」。
    """
    deadline = time.monotonic() + max(0, seconds)
    while time.monotonic() < deadline:
        proc = keyinput.foreground_process_name()
        if proc and os.path.basename(proc).lower() == GAME_PROCESS:
            return True
        time.sleep(poll)
    return False


def run(args) -> int:
    report = Report()
    report.sent = False

    # 1. 平台
    if not keyinput.IS_WINDOWS:
        report.add(FAIL, "平台", "%s —— 模拟按键只在 Windows 上可用" % platform.platform())
        report.show()
        return 3
    report.add(OK, "平台", platform.platform())

    # 2. 本工具权限
    self_admin = keyinput.is_elevated()
    report.add(
        OK if self_admin else INFO,
        "本工具权限",
        "管理员" if self_admin else ("普通用户" if self_admin is False else "查不出来"))

    # 3. 游戏进程
    game_dir = _resolve_game_dir(args.game_dir)
    if game_dir:
        reachable = os.path.isdir(game_dir)
        report.add(
            OK if reachable else WARN,
            "游戏目录",
            "%s%s" % (game_dir, "" if reachable else "（当前访问不到）"))
    else:
        report.add(WARN, "游戏目录", "没配置，也没探测到 —— 读不到游戏内的截图键绑定")

    running = _game_running()
    if running:
        report.add(OK, "游戏进程", "在运行")
    else:
        report.add(WARN, "游戏进程", "没检测到 %s（没开游戏时属正常）" % GAME_PROCESS)

    # 4. 前台窗口
    fg_desc = _foreground_desc()
    fg_proc = keyinput.foreground_process_name()
    is_game_fg = bool(fg_proc) and os.path.basename(fg_proc).lower() == GAME_PROCESS
    report.add(OK if is_game_fg else WARN, "前台窗口", fg_desc + ("" if is_game_fg else "（不是游戏）"))

    # 5. 权限对等（只在游戏前台时才有意义）
    if is_game_fg:
        blocked = keyinput.injection_blocked()
        if blocked:
            report.add(FAIL, "权限对等", blocked)
        elif self_admin is False and keyinput.process_elevated(keyinput.foreground_pid()):
            report.add(FAIL, "权限对等", "游戏以管理员运行、本工具不是 —— SendInput 会被静默丢弃")
        else:
            report.add(OK, "权限对等", "没有发现提权差")
    else:
        report.add(INFO, "权限对等", "游戏不在前台，跳过（这一项最容易出问题，进游戏后务必再跑一次）")

    # 6. 日志门：自动截图只在「日志显示已进战局」时发键（参考实现没有这道门）
    phase, phase_note = _log_phase(game_dir)
    if phase == "start":
        report.add(OK, "日志 / 战局阶段", phase_note + " —— 日志门是开的")
    elif phase is None:
        report.add(WARN, "日志 / 战局阶段", phase_note + " —— 自动截图会一直等不到「进战局」")
    else:
        report.add(WARN, "日志 / 战局阶段",
                   phase_note + " —— 不在战局中，自动截图会暂停发键（进战局后才会拍）")

    # 7. 截图键解析
    key = args.key or _key_from_config_or_log(game_dir)
    combo = keyinput.parse_combo(key) if key else None
    if not key:
        report.add(FAIL, "截图键", "没有键可用 —— 在启动器里点「从日志同步」，或填游戏内实际绑定的键")
    elif combo is None:
        report.add(FAIL, "截图键", "%s —— %s" % (key, keyinput.unsupported_reason(key)))
    else:
        main, mods = combo
        report.add(OK, "截图键", "%s（vk 0x%02X / scan 0x%02X%s%s）" % (
            key, main.vk, main.scan, " + 扩展位" if main.extended else "",
            "，修饰键 %d 个" % len(mods) if mods else ""))
        # 2026-11-02 实测：本机游戏内截图绑的就是 SysReq，前两轮全在查注入层，
        # 真正原因是 Windows 11 默认「按 PrtSc 打开截屏工具」把这个键截走了 ——
        # 人手按也没图。所以这一族键必须报警，不能显示成绿色的 OK。
        snapshot_warning = _snapshot_key_warning(key)
        if snapshot_warning:
            report.add(WARN, "按键归属", snapshot_warning)

    # 7. 注入方式
    if combo is not None:
        mode = keyinput.preferred_mode(key)
        note = "（PrintScreen/SysRq 用扫描码无效，已强制虚拟键码）" if mode == keyinput.MODE_VK else ""
        report.add(OK, "注入方式", "%s%s" % (mode, note))

    # 8. 截图目录
    shots_dir = _resolve_shots_dir(args.shots_dir, game_dir)
    shots_ok = bool(shots_dir) and os.path.isdir(shots_dir)
    if not shots_dir:
        report.add(FAIL, "截图目录", "没配置也没探测到 —— 无法判断「到底有没有拍到」")
    elif not shots_ok:
        report.add(FAIL, "截图目录", "%s（不存在）" % shots_dir)
    else:
        newest = screenshot.newest_mtime(shots_dir)
        count = len(screenshot.list_screenshot_files(shots_dir))
        report.add(OK, "截图目录", "%s（%d 张图，最新一张 %s）" % (
            shots_dir, count,
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(newest)) if newest else "无"))

    # 9. 真发一次
    if not args.send and not args.manual:
        report.add(INFO, "实际发送", "未执行（加 --send 由本脚本按键；加 --manual 你自己按一次）")
        report.show()
        return 0 if report.blocking is None else 1

    if combo is None or not shots_ok:
        report.add(FAIL, "实际发送", "跳过：上面有阻塞项，先解决再发键（避免把按键打进别的窗口）")
        report.show()
        return 1

    report.show()          # 检查结果先摆出来，后面的「发送 → 等 → 判定」单独打印

    if args.manual:
        return _manual_check(key, shots_dir, wait=args.wait, game_fg=is_game_fg)

    if not is_game_fg:
        if args.wait_foreground > 0:
            print("%s 请在 %d 秒内把游戏切到前台，我会等你切过去之后再发键…" % (
                INFO, args.wait_foreground))
            is_game_fg = _wait_for_game_foreground(args.wait_foreground)
            print("%s %s" % (OK if is_game_fg else FAIL,
                             "游戏已在前台，开始发键" if is_game_fg
                             else "等超时了，游戏仍不在前台"))
        if not is_game_fg:
            print("%s 跳过：游戏不在前台。模拟按键只能打进前台窗口，"
                  "现在发键会打到「%s」上" % (FAIL, fg_desc))
            return 1

    base = screenshot.newest_mtime(shots_dir)
    ok, error = keyinput.send_key(key, keyinput.preferred_mode(key))
    if not ok:
        print("%s 发送失败：%s" % (FAIL, error or "未知原因"))
        return 1
    report.sent = True
    print("%s 已按下 %s，等 %.1f 秒看目录…" % (OK, key, ARRIVAL_WAIT))

    time.sleep(ARRIVAL_WAIT)
    newest = screenshot.newest_mtime(shots_dir)
    if newest is not None and (base is None or newest > base):
        print("%s 到货：目录里出现了新截图，自动截图这条链路是通的。" % OK)
        return 0
    print("%s 到货：按键送出去了，但目录里没有新文件。" % FAIL)
    print("     依次排查：")
    print("       1) 游戏内「截图」绑定是不是 %s（设置 → 控制 → 界面）；" % key)
    print("       2) 上面「截图目录」是不是游戏真正写图的目录；")
    print("       3) 游戏是否以管理员运行而本工具不是（「权限对等」那一行）。")
    print("     关键是先分清「游戏自己拍不拍得到」：再跑一次 --manual，用键盘手动按一次截图键。")
    return 1


def _manual_check(key: str | None, shots_dir: str, wait: int = 10, game_fg: bool = False) -> int:
    """让用户**自己**按一次截图键，只看目录 —— 最权威的一条判定。

    它能一刀切开两种完全不同的故障：

    * 手动按也没图 → 游戏截图本身没工作（键位没绑、目录不对、游戏设置里关了），
      **跟模拟输入无关**，再怎么调注入方式也没用；
    * 手动按有图、`--send` 没图 → 模拟输入不被游戏接受，问题在注入层
      （权限 / 注入方式 / 反作弊），这才需要往那边查。
    """
    base = screenshot.newest_mtime(shots_dir)
    print()
    print("%s 请切到游戏（保持在前台），在接下来 %d 秒内**手动按一次**截图键%s。" % (
        INFO, wait, "（绑定为 %s）" % key if key else ""))
    if not game_fg:
        print("     注意：游戏现在不在前台，切过去再按。")
    for left in range(wait, 0, -1):
        print("     倒计时 %2d 秒…" % left, end="\r", flush=True)
        time.sleep(1)
    print(" " * 24, end="\r", flush=True)

    newest = screenshot.newest_mtime(shots_dir)
    if newest is not None and (base is None or newest > base):
        print("%s 手动按键后目录出现了新截图 —— 游戏的截图功能本身是好的。" % OK)
        print("     那么「自动发键没反应」就只剩注入层的问题：")
        print("       · 游戏以管理员运行、本工具不是（UIPI 会静默丢弃模拟输入）；")
        print("       · 或游戏的反作弊不接受合成输入。")
        return 0
    print("%s 手动按键后目录也没有新截图 —— 问题在游戏侧，跟模拟输入无关：" % FAIL)
    print("     1) 游戏设置 → 控制 → 界面，确认「截图」这一项真的绑了键；")
    print("     2) 确认游戏把截图写到上面那个目录（有些版本写在用户文档下，有些写在游戏目录）；")
    print("     3) 手动按一次时听有没有快门声/看有没有提示，确认游戏收到了这个键。")
    return 1


def _game_running() -> bool:
    """EFT 进程在不在（不看窗口，任务管理器里有就算）。

    走 `tasklist` 而不是遍历 `Process.GetProcesses`：后者要么依赖 WMI、要么要第三方库，
    而 `tasklist` 是系统自带、输出稳定、不需要任何依赖。
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq %s" % GAME_PROCESS, "/NH"],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return GAME_PROCESS.lower() in (out.stdout or "").lower()


def _snapshot_key_warning(key) -> str | None:
    """截图键属于 PrtSc / SysRq 家族时返回警告文案（否则 None）。

    这一族键（`VK_SNAPSHOT`）在 Windows 11 上默认被「按 Print Screen 打开截屏工具」
    接管：按键在到达焦点窗口之前就被系统消费掉了，人手按也一样没有截图。
    这是本机 2026-11-02 实测到的真因，所以必须在自检里显式说出来。
    """
    combo = keyinput.parse_combo(key) if key else None
    if combo is None:
        return None
    if combo[0].vk != _VK_SNAPSHOT:
        return None
    return ("PrtSc / SysRq 会被 Windows 截屏工具抢走（系统默认开启），游戏收不到；"
            "请在游戏里把它改成 F10 这类普通功能键")


def _key_from_config_or_log(game_dir: str) -> str | None:
    """截图键：配置里填的优先，否则从游戏日志里的控制绑定读。"""
    cfg = config.load(config.app_dir()) or {}
    key = ((cfg.get("auto_screenshot") or {}).get("key") or "").strip()
    if key:
        return key
    if not game_dir:
        return None
    try:
        import eftlog
        return eftlog.read_screenshot_key(game_dir)
    except Exception:      # 日志读不了就当没有，不因此中断自检
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EFT 自动截图链路自检（默认只读，不发按键）")
    parser.add_argument("--send", action="store_true", help="真的发一次截图键并等到货结果")
    parser.add_argument("--manual", action="store_true",
                        help="让你自己在游戏里按一次截图键，只看目录有没有新图（最权威的判定）")
    parser.add_argument("--wait", type=int, default=10, help="--manual 的等待秒数（默认 10）")
    parser.add_argument("--wait-foreground", type=int, default=0,
                        help="--send 时最多等多少秒让游戏切到前台（默认 0 = 不等）")
    parser.add_argument("--key", default=None, help="临时指定截图键（默认用配置里的或从日志读）")
    parser.add_argument("--game-dir", default=None, help="游戏目录（默认用配置里的或自动探测）")
    parser.add_argument("--shots-dir", default=None, help="截图目录（默认用配置里的或自动探测）")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
