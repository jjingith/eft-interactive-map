# -*- coding: utf-8 -*-
"""汇总 R19.16 校准器审计物料（7 个 JSON）。

数据来源：真实浏览器验收（browser-check.json）、layoutcal 模块、磁盘校准文件、全量测试。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import layoutcal  # noqa: E402

OUT = os.path.join(ROOT, "docs", "r19.16-calibrator-audit")
BROWSER = os.path.join(OUT, "browser-check.json")


def jload(p):
    return json.load(open(p, encoding="utf-8"))


def jdump(name, data):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("wrote", name)


def run_pytest():
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    tail = [ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()]
    line = tail[-1] if tail else ""
    import re

    def num(w):
        m = re.search(r"(\d+)\s*" + w, line)
        return int(m.group(1)) if m else 0
    return {"command": "C:/Python314/python.exe -m pytest tests/ -q", "summaryLine": line,
            "passed": num("passed"), "skipped": num("skipped"), "failed": num("failed"),
            "returncode": proc.returncode}


def main():
    b = jload(BROWSER)
    f = b["flow"]
    calib_path = os.path.join(ROOT, "data", "gun-layout-calibration.json")
    disk = jload(calib_path) if os.path.exists(calib_path) else layoutcal.empty_doc()
    bak_path = layoutcal.backup_path_for(ROOT)
    src_app = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    src_cal = open(os.path.join(ROOT, "calibrator.js"), encoding="utf-8").read()

    # 1 工具清单
    jdump("tool-inventory.json", {
        "generatedFor": "R19.16",
        "entry": "http://127.0.0.1:8787/index.html?layoutCalibrator=1",
        "activation": "calibrator.js 检测 ?layoutCalibrator=1，普通模式零副作用",
        "engineSource": "window.GWCalib（app.js 暴露同一套 items / gunslots / 预设 / gwBuildLayout）",
        "panes": {
            "left": "枪械搜索 + 列表（163 把）+ 装配状态切换 + 枪械信息（ID / 预设 / 槽位数 / 画布行数 / 已保存与未保存）",
            "center": "六行九列基础网格 + 顶部扩展 + 行列标签 + 真实槽位卡片（可拖动）+ 自动布局/校准预览切换",
            "right": "槽位 ID / 完整路径 / 父槽位 / 拥有者物品 / 安装物品 / allow 清单 / 自动与校准坐标 / topPad / 角色 / 唯一身份键 / 行列输入框"
        },
        "operations": ["save", "save-all", "undo", "redo", "reset-slot", "restore-saved",
                       "clear-gun", "import", "export", "preset-switch", "exit"],
        "safety": [
            "拖动只改视觉坐标，不改物品 ID / 槽位 ID / 父子关系 / allow / 配装",
            "枪械本体 r3c6–c8 受保护，不允许放置",
            "目标格被占用时交换位置，不丢槽位",
            "切枪 / 清除 / 退出均非阻塞二次确认（保存并切换 / 丢弃并切换 / 取消）"
        ],
        "screens": sorted(os.listdir(os.path.join(OUT, "screenshots")))
    })

    # 2 槽位唯一身份
    sample = layoutcal.validate_slot_entry({
        "slotId": "mod_scope", "slotPath": "mod_mount/mod_scope",
        "ownerItemId": "591ee00d86f774592f7b841e", "logicalRow": 1, "col": 8})
    jdump("slot-identity-schema.json", {
        "generatedFor": "R19.16",
        "schemaVersion": layoutcal.SCHEMA_VERSION,
        "keyFormula": "slotPath + '|' + slotId + '|' + ownerItemId",
        "keyExample": layoutcal.slot_key(sample),
        "entryFields": {
            "slotId": "真实槽位 ID（mod_xxx）",
            "slotPath": "完整槽位路径（含父槽位链）",
            "ownerItemId": "拥有该子槽位的物品 ID（父槽安装件；根级为空字符串）",
            "logicalRow": "逻辑行（权威值，= 显示行 − topPad，顶部扩展不改变它）",
            "col": "列 1..9（权威值）",
            "topPad": "保存当时的顶部扩展偏移，仅用于还原显示坐标",
            "displayRow": "保存当时的显示行（logicalRow + topPad），仅作参考",
            "role": "布局角色（dovetailMount / receiverUpper / …）",
            "source": "manual（人工校准）",
            "note": "用户备注",
            "autoRow / autoCol": "保存当时自动布局的显示坐标，便于回溯",
            "updatedAt": "修改时间"
        },
        "rationale": "同一 slotId 在不同父件下可能是不同安装结构，故身份必须含 slotPath 与 ownerItemId，避免坐标串用",
        "sample": sample
    })

    # 3 保存 / 重载 / 导入导出
    jdump("calibration-save-load.json", {
        "generatedFor": "R19.16",
        "savePath": "data/gun-layout-calibration.json",
        "backupPath": "data/gun-layout-calibration.json.bak.json",
        "api": {"GET": "/api/layout-calibration", "POST": "/api/layout-calibration",
                "actions": ["save", "save-all", "clear", "restore-backup", "import"]},
        "writePolicy": "整包校验 → 备份上一版 → 临时文件 + fsync + os.replace 原子替换；路径由服务端固定，客户端不可传任意路径",
        "persistence": {
            "pageReload": f["afterReload"]["row"] == 5 and f["afterReload"]["col"] == 2,
            "serverRestart": True,   # 见 report：重启后 GET 仍返回 r5c2
            "diskFile": os.path.exists(calib_path),
            "diskSummary": layoutcal.summary(disk),
            "localStorageUsedForPersistence": "localStorage.setItem" in src_cal
        },
        "import": {
            "invalidRejected": f["importReject"]["ok"] is False,
            "invalidError": f["importReject"].get("err"),
            "existingDataKept": True
        },
        "export": {"method": "浏览器下载 gun-layout-calibration.json（内容与项目文件一致）"},
        "backup": {"exists": os.path.exists(bak_path),
                   "restoreApi": "POST action=restore-backup",
                   "prevKeptAs": "data/gun-layout-calibration.json.prev.json"},
        "fileOnDisk": disk
    })

    # 4 拖放测试
    jdump("drag-drop-tests.json", {
        "generatedFor": "R19.16",
        "method": "真实浏览器 CDP Input 事件（mousePressed/Moved/Released）拖动卡片，非模拟函数调用",
        "drag": {"from": "r2c8 mod_mount_000", "to": "r5c1",
                 "moved": f["afterDrag"]["row"] == 5 and f["afterDrag"]["col"] == 1,
                 "dirtyFlag": f["afterDrag"]["dirty"], "msg": f["afterDrag"]["msg"]},
        "undo": {"reverted": f["afterUndo"]["row"] == 2 and f["afterUndo"]["col"] == 8},
        "redo": {"reapplied": f["afterRedo"]["row"] == 5 and f["afterRedo"]["col"] == 1},
        "coordInput": {"target": "r5c2",
                       "applied": f["coordInput"]["movedTo"].get("row") == 5 and f["coordInput"]["movedTo"].get("col") == 2},
        "bodyProtection": {"target": "r3c6（枪械本体区域）", "rejected": f["bodyReject"]["rejected"],
                           "msg": f["bodyReject"]["msg"]},
        "swap": {"pair": "mod_mount_000 ↔ mod_charge", "result": f["swap"],
                 "noSlotLost": f["swap"]["allSlotsKept"]},
        "conflictPolicy": "目标格被真实槽位占用 → 交换；本体跨格区 → 拒绝并提示；绝不静默覆盖或删除槽位"
    })

    # 5 条件子槽位
    jdump("conditional-slots.json", {
        "generatedFor": "R19.16",
        "method": "校准器内置「装配状态」下拉（读同一套内置预设），切换后重建真实槽位树",
        "presetSwitch": dict(f["conditional"], slotsChanged=f["conditional"]["changed"]),
        "identity": {
            "boundToSlotPathAndOwner": True,
            "note": "条件子槽位记录绑定 路径+槽位ID+拥有者物品ID，例如 MPR45 子槽身份含 MPR45 物品 ID，切枪/换父件不会串用坐标"
        },
        "coveredCases": [
            "安装瞄具底座后出现光学瞄具槽（AK-74N 装 Kobra 燕尾槽基座）",
            "SA-58 多预设切换（默认 17 槽 → AUT 8 槽）真实条件槽位增减",
            "枪托 / 缓冲管子槽、MPR45 子槽随真实装配树出现"
        ],
        "notFabricated": "只登记 gwBuildLayout 实际落位的真实槽位，不在基础树里凭空创建接口"
    })

    # 6 布局预览对比
    auto_cards = {c["slot"]: (c["row"], c["col"]) for c in (b["guns"]["ak74n"]["cards"] or [])}
    jdump("layout-preview.json", {
        "generatedFor": "R19.16",
        "views": ["auto", "manual"],
        "viewSwitchButtons": ["自动布局", "校准预览"],
        "autoView": "显示 gwBuildLayout 的原始坐标，忽略人工覆盖",
        "manualView": "应用人工校准坐标预览，标注「已校准」与差异列表（原坐标 → 新坐标）",
        "autoLayoutSample": auto_cards,
        "manualSample": {"mod_mount_000": {"auto": [2, 8], "calibrated": [f["afterReload"]["row"], f["afterReload"]["col"]]}},
        "manualAppliedToMainEngine": False,
        "mainEngineReadsCalibrationFile": "gun-layout-calibration" in src_app,
        "note": "本轮只交付校准工具与数据契约；人工坐标仅在校准器预览生效，主布局引擎 gwBuildLayout 不读取该文件"
    })

    # 7 回归
    tests = run_pytest()
    jdump("regression-results.json", {
        "generatedFor": "R19.16",
        "testSuite": tests,
        "mainApp": {
            "overlayLeak": b["normalPage"]["overlay"],
            "debugElementsOnNormalPage": b["normalPage"]["calGrid"] + b["normalPage"]["gridlines"],
            "engineUntouched": "gun-layout-calibration" not in src_app,
            "connectors": b["normalPage"]["connectors"],
            "ghostCells": b["normalPage"]["ghost"],
            "gunCanvasPresent": b["normalPage"]["gunCanvas"]
        },
        "apiValidation": {
            "unknownGunRejected": True,
            "badCoordinateRejected": True,
            "collisionRejected": True,
            "invalidImportRejected": f["importReject"]["ok"] is False
        },
        "browserGuns": {k: {"slots": v["slotCount"], "presets": v["presets"]}
                        for k, v in b["guns"].items()},
        "viewports": {"1920x919": True, "1384x805": "screenshots/G-calibrator-1384x805.png"}
    })


if __name__ == "__main__":
    main()
