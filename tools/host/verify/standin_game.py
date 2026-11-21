#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验收用「假游戏窗口」：一块铺满屏幕的深色窗口，记录鼠标点击。

用途：验证小地图宿主是否真的置顶在游戏窗口之上、以及点击穿透是否把
鼠标事件交给了下面的窗口。只在验收时手动运行，不属于产品运行路径。
"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standin-clicks.log")


def main() -> int:
    root = tk.Tk()
    root.title("EFT StandIn")
    root.configure(bg="#101010")
    root.overrideredirect(True)
    root.geometry("1920x1080+0+0")
    root.attributes("-topmost", False)
    canvas = tk.Canvas(root, bg="#101010", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(960, 60, text="STAND-IN GAME WINDOW", fill="#e8e8e8",
                       font=("Segoe UI", 28, "bold"))
    canvas.create_text(960, 110, text="点击会写入 standin-clicks.log", fill="#666666",
                       font=("Segoe UI", 14))

    def on_click(event):
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%.3f %d %d\n" % (time.time(), event.x_root, event.y_root))

    root.bind_all("<Button-1>", on_click)
    root.after(120000, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
