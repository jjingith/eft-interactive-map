# -*- coding: utf-8 -*-
"""r58c：有界枚举 EFT 安装目录与常见位置下的 PE，判定是否 .NET 托管程序集。
只读：仅 open('rb') 读取头部字节 + 注册表读取。
"""
import os, sys, json, struct, ctypes
from ctypes import wintypes

SCAN_ROOTS = [r"D:\GAMES\EFT"]
COMMON = [(os.environ.get("LOCALAPPDATA"), 3), (os.environ.get("APPDATA"), 3),
          (os.environ.get("PROGRAMDATA"), 3), (r"D:\GAMES", 3), (r"D:\personal", 2)]
NAME_HINTS = ("spt", "aki", "server", "hazel", "localgame", "eft-server")


# ---------- PE ----------
def pe_info(path):
    """返回 (machine, is_pe, cli_dir_rva, cli_dir_size, subsystem)"""
    try:
        with open(path, "rb") as f:
            data = f.read(4096)
            if len(data) < 0x40:
                return None
            e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
            if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
                return None
            machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
            opt = e_lfanew + 24
            magic = struct.unpack_from("<H", data, opt)[0]
            if magic == 0x20B:      # PE32+
                dd = opt + 112
                nrva_off = opt + 108
            elif magic == 0x10B:    # PE32
                dd = opt + 96
                nrva_off = opt + 92
            else:
                return None
            nrva = struct.unpack_from("<I", data, nrva_off)[0]
            if nrva < 15:
                return (machine, True, 0, 0, 0)
            rva, size = struct.unpack_from("<II", data, dd + 14 * 8)  # COM descriptor
            subsystem = struct.unpack_from("<H", data, opt + 68)[0] if magic == 0x20B else 0
            return (machine, True, rva, size, subsystem)
    except Exception:
        return None


def version_info(path):
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return {}
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
            return {}
        res = ctypes.c_void_p()
        ln = wintypes.UINT()
        out = {}
        if ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(res), ctypes.byref(ln)):
            class FI(ctypes.Structure):
                _fields_ = [("dwSignature", wintypes.DWORD), ("dwStrucVersion", wintypes.DWORD),
                            ("dwFileVersionMS", wintypes.DWORD), ("dwFileVersionLS", wintypes.DWORD),
                            ("dwProductVersionMS", wintypes.DWORD), ("dwProductVersionLS", wintypes.DWORD),
                            ("dwFileFlagsMask", wintypes.DWORD), ("dwFileFlags", wintypes.DWORD),
                            ("dwFileOS", wintypes.DWORD), ("dwFileType", wintypes.DWORD),
                            ("dwFileSubtype", wintypes.DWORD), ("dwFileDateMS", wintypes.DWORD),
                            ("dwFileDateLS", wintypes.DWORD)]
            fi = ctypes.cast(res, ctypes.POINTER(FI)).contents
            out["file_version"] = "%d.%d.%d.%d" % (fi.dwFileVersionMS >> 16, fi.dwFileVersionMS & 0xFFFF,
                                                   fi.dwFileVersionLS >> 16, fi.dwFileVersionLS & 0xFFFF)
            out["product_version"] = "%d.%d.%d.%d" % (fi.dwProductVersionMS >> 16, fi.dwProductVersionMS & 0xFFFF,
                                                      fi.dwProductVersionLS >> 16, fi.dwProductVersionLS & 0xFFFF)
        return out
    except Exception:
        return {}


def classify(root):
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in ("battleye",)]
        for fn in filenames:
            if not fn.lower().endswith((".exe", ".dll")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                sz = os.path.getsize(p)
            except Exception:
                continue
            info = pe_info(p)
            if info is None:
                rows.append({"path": p, "size": sz, "pe": False, "managed": False,
                             "machine": None, "cli": None})
                continue
            machine, _, rva, dsize, _ = info
            managed = bool(rva and dsize)
            v = version_info(p) if managed else {}
            rows.append({"path": p, "size": sz, "pe": True, "managed": managed,
                         "machine": {0x8664: "x64", 0x14c: "x86"}.get(machine, hex(machine)),
                         "cli_rva": rva, "cli_size": dsize,
                         "file_version": v.get("file_version"),
                         "product_version": v.get("product_version")})
    rows.sort(key=lambda r: (not r["managed"], r["path"]))
    return rows


# ---------- 常见位置目录名 ----------
def find_hint_dirs():
    hits = []

    def walk(base, depth):
        if depth <= 0 or not os.path.isdir(base):
            return
        try:
            entries = list(os.scandir(base))
        except Exception:
            return
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            if any(h in e.name.lower() for h in NAME_HINTS):
                hits.append({"path": e.path})
            walk(e.path, depth - 1)

    for root, depth in COMMON:
        if root:
            walk(root, depth)
    return hits


# ---------- 注册表 ----------
def reg_lookups():
    out = []
    try:
        import winreg
    except Exception:
        return out
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                n = winreg.QueryInfoKey(k)[0]
                for i in range(n):
                    try:
                        name = winreg.EnumKey(k, i)
                        with winreg.OpenKey(k, name) as ck:
                            dn = ""
                            loc = ""
                            try:
                                dn = winreg.QueryValueEx(ck, "DisplayName")[0] or ""
                            except Exception:
                                pass
                            try:
                                loc = winreg.QueryValueEx(ck, "InstallLocation")[0] or ""
                            except Exception:
                                pass
                            blob = (dn + " " + loc + " " + name).lower()
                            if any(h in blob for h in ("tarkov", "spt", "aki", "battlestate")):
                                out.append({"key": sub + "\\" + name, "display": dn, "location": loc})
                    except Exception:
                        continue
        except Exception:
            continue
    return out


if __name__ == "__main__":
    roots = SCAN_ROOTS
    res = {"scan_roots": roots, "pe": [], "hint_dirs": find_hint_dirs(), "registry": reg_lookups()}
    for r in roots:
        if os.path.isdir(r):
            res["pe"] += classify(r)
    print(json.dumps(res, ensure_ascii=False, indent=1))
