﻿﻿﻿﻿﻿﻿﻿// EFT 互动地图 · 游戏内小地图宿主（WinForms + WebView2 Core）
//
// 只做三件事：创建一个**没有系统边框**的顶层窗口、把现有网页小地图装进去、
// 让它可以置顶 / 不抢焦点 / 点击穿透。地图本身仍由 index.html?mini=1 渲染，
// 本宿主不碰前端、不碰地图数据。
//
// 编译：Windows 自带 .NET Framework 4.8 的 csc.exe（见 build.ps1），不联网、不装 SDK。
// 运行期只访问 127.0.0.1 的本地服务；WebView2 Runtime 由系统 Edge 提供。

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace EftMapMiniHost
{
    internal sealed class Options
    {
        public string Url;
        public string ConfigDir;
        public string LogPath;
        public double Scale;            // 0 = 自动按系统 DPI
        public int FullWidth = 900;
        public int FullHeight = 640;
        public string OpacityMode = "window";   // window | page
        public bool Transparent = true;
        public int ClickThrough = -1;   // -1 = 跟随配置
        public bool Hotkeys = true;
        public int ExitAfterMs;
        public bool IgnoreEnabled;
        public bool DumpDom;
        public string MapKey;
        public bool SimulateNoRuntime;
        public bool ShellMode;          // 由 EFTMapDesktop 托管：配置关小窗时只隐藏，不销毁窗口
        public bool StartHidden;         // 壳启动时先不显示小地图，等热键/配置打开
        public string DumpWindowJson;   // 可选：把窗口样式/DPR/布局写成 JSON
        public string ToggleHotkey = "Ctrl+Shift+M";
        public string FullHotkey = "Ctrl+Shift+F";

        public static Options Parse(string[] args)
        {
            Options o = new Options();
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                string v = (i + 1 < args.Length) ? args[i + 1] : null;
                if (a == "--url") { o.Url = v; i++; }
                else if (a == "--config-dir") { o.ConfigDir = v; i++; }
                else if (a == "--log") { o.LogPath = v; i++; }
                else if (a == "--scale") { o.Scale = double.Parse(v, System.Globalization.CultureInfo.InvariantCulture); i++; }
                else if (a == "--full-size")
                {
                    string[] parts = (v ?? "900x640").ToLowerInvariant().Split('x');
                    o.FullWidth = int.Parse(parts[0]);
                    o.FullHeight = int.Parse(parts.Length > 1 ? parts[1] : parts[0]);
                    i++;
                }
                else if (a == "--opacity-mode") { o.OpacityMode = v; i++; }
                else if (a == "--transparent") { o.Transparent = v != "0"; i++; }
                else if (a == "--click-through") { o.ClickThrough = int.Parse(v); i++; }
                else if (a == "--no-hotkey") { o.Hotkeys = false; }
                else if (a == "--exit-after-ms") { o.ExitAfterMs = int.Parse(v); i++; }
                else if (a == "--ignore-enabled") { o.IgnoreEnabled = true; }
                else if (a == "--dump-dom") { o.DumpDom = true; }
                else if (a == "--map-key") { o.MapKey = v; i++; }
                else if (a == "--simulate-no-runtime") { o.SimulateNoRuntime = true; }
                else if (a == "--shell-mode") { o.ShellMode = true; }
                else if (a == "--start-hidden") { o.StartHidden = true; }
                else if (a == "--dump-window-json") { o.DumpWindowJson = v; i++; }
            }
            if (String.IsNullOrEmpty(o.ConfigDir))
            {
                o.ConfigDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "EFTMap");
            }
            if (String.IsNullOrEmpty(o.LogPath))
            {
                o.LogPath = Path.Combine(o.ConfigDir, "minimap-host.log");
            }
            // 相对路径按当前进程目录解析，避免 WebView2 的 user-data 被写到 exe 目录下
            o.ConfigDir = Path.GetFullPath(o.ConfigDir);
            if (!String.IsNullOrEmpty(o.LogPath)) o.LogPath = Path.GetFullPath(o.LogPath);
            return o;
        }
    }

    internal static class Log
    {
        private static string _path;
        private static readonly object _lock = new object();

        public static void Init(string path)
        {
            _path = path;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.AppendAllText(path, "\r\n=== " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " start pid=" + System.Diagnostics.Process.GetCurrentProcess().Id + " ===\r\n", Encoding.UTF8);
            }
            catch { }
        }

        public static void Write(string message)
        {
            string line = DateTime.Now.ToString("HH:mm:ss.fff") + "  " + message;
            try
            {
                lock (_lock)
                {
                    if (_path != null) File.AppendAllText(_path, line + "\r\n", Encoding.UTF8);
                }
            }
            catch { }
        }
    }

    internal static class Native
    {
        public const int GWL_STYLE = -16;
        public const int GWL_EXSTYLE = -20;

        public const int WS_CAPTION = 0x00C00000;
        public const int WS_THICKFRAME = 0x00040000;
        public const int WS_SYSMENU = 0x00080000;
        public const int WS_MINIMIZEBOX = 0x00020000;
        public const int WS_MAXIMIZEBOX = 0x00010000;
        public const int WS_BORDER = 0x00800000;
        public const int WS_DLGFRAME = 0x00400000;

        public const int WS_EX_LAYERED = 0x00080000;
        public const int WS_EX_TRANSPARENT = 0x00000020;
        public const int WS_EX_NOACTIVATE = 0x08000000;
        public const int WS_EX_TOOLWINDOW = 0x00000080;
        public const int WS_EX_TOPMOST = 0x00000008;
        public const int WS_VISIBLE = 0x10000000;

        public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        public const uint SWP_NOSIZE = 0x0001;
        public const uint SWP_NOMOVE = 0x0002;
        public const uint SWP_NOZORDER = 0x0004;
        public const uint SWP_NOACTIVATE = 0x0010;
        public const uint SWP_FRAMECHANGED = 0x0020;

        public const int SW_HIDE = 0;
        public const int SW_SHOW = 5;
        public const int SW_RESTORE = 9;
        public const int SW_SHOWNOACTIVATE = 4;

        public const uint SPI_GETWORKAREA = 0x0030;
        public const int LWA_ALPHA = 0x2;

        public const uint MONITOR_DEFAULTTONEAREST = 2;
        public const uint WDA_NONE = 0x0;
        public const uint WDA_EXCLUDEFROMCAPTURE = 0x11;

        public const int WM_HOTKEY = 0x0312;
        public const int WM_DPICHANGED = 0x02E0;
        public const int WM_DISPLAYCHANGE = 0x007E;
        public const int WM_CLOSE = 0x0010;
        public const int WM_NCHITTEST = 0x0084;
        public const int WM_NCLBUTTONDOWN = 0x00A1;

        public const int HTCLIENT = 1;
        public const int HTCAPTION = 2;
        public const int HTLEFT = 10;
        public const int HTRIGHT = 11;
        public const int HTTOP = 12;
        public const int HTTOPLEFT = 13;
        public const int HTTOPRIGHT = 14;
        public const int HTBOTTOM = 15;
        public const int HTBOTTOMLEFT = 16;
        public const int HTBOTTOMRIGHT = 17;

        public const int DWMWA_NCRENDERING_POLICY = 2;
        public const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        public const int DWMWA_BORDER_COLOR = 34;
        public const int DWMNCRP_DISABLED = 1;
        public const int DWMNCRP_ENABLED = 2;
        public const int DWMWCP_DONOTROUND = 1;
        public const int DWMWCP_ROUND = 2;
        public const uint DWMWA_COLOR_NONE = 0xFFFFFFFE;

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT { public int Left, Top, Right, Bottom; }

        [StructLayout(LayoutKind.Sequential)]
        public struct POINT { public int X, Y; }

        [DllImport("user32.dll")] public static extern int SetWindowRgn(IntPtr hwnd, IntPtr region, bool redraw);
        [DllImport("gdi32.dll")] public static extern IntPtr CreateEllipticRgn(int left, int top, int right, int bottom);
        [DllImport("gdi32.dll")] public static extern bool DeleteObject(IntPtr obj);
        [DllImport("user32.dll")] public static extern bool SetWindowDisplayAffinity(IntPtr hwnd, uint affinity);

        [StructLayout(LayoutKind.Sequential)]
        public struct MARGINS { public int Left, Right, Top, Bottom; }

        [StructLayout(LayoutKind.Sequential)]
        public struct MONITORINFO
        {
            public int cbSize;
            public RECT rcMonitor;
            public RECT rcWork;
            public uint dwFlags;
        }

        [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
        [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
        [DllImport("gdi32.dll")] public static extern int GetDeviceCaps(IntPtr hdc, int index);
        [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool SystemParametersInfoW(uint action, uint param, ref RECT rect, uint winIni);

        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] private static extern IntPtr GetWindowLongPtr64(IntPtr hwnd, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern IntPtr SetWindowLongPtr64(IntPtr hwnd, int index, IntPtr value);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongW")] private static extern int GetWindowLong32(IntPtr hwnd, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongW")] private static extern int SetWindowLong32(IntPtr hwnd, int index, int value);

        [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int cmd);
        [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT pt);
        [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
        [DllImport("user32.dll")] public static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint colorKey, byte alpha, uint flags);
        [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr hwnd, int id, uint modifiers, uint vk);
        [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr hwnd, int id);
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
        [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out RECT rect);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr hwnd);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string className, string windowName);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);
        [DllImport("user32.dll")] public static extern IntPtr MonitorFromPoint(POINT pt, uint flags);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool GetMonitorInfo(IntPtr monitor, ref MONITORINFO info);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int maxCount);
        [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
        [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
        [DllImport("user32.dll")] public static extern bool ReleaseCapture();
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam);
        [DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

        public delegate bool EnumChildProc(IntPtr hwnd, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumChildProc callback, IntPtr lParam);

        public static IntPtr GetStyle(IntPtr hwnd, int index)
        {
            if (IntPtr.Size == 8) return GetWindowLongPtr64(hwnd, index);
            return new IntPtr(GetWindowLong32(hwnd, index));
        }

        public static void SetStyle(IntPtr hwnd, int index, IntPtr value)
        {
            if (IntPtr.Size == 8) { SetWindowLongPtr64(hwnd, index, value); return; }
            SetWindowLong32(hwnd, index, (int)value.ToInt64());
        }

        public static string GetWindowTitle(IntPtr hwnd)
        {
            StringBuilder sb = new StringBuilder(256);
            try { GetWindowText(hwnd, sb, sb.Capacity); } catch { }
            return sb.ToString();
        }

        public static bool PostMessageClose(IntPtr hwnd)
        {
            try { return PostMessage(hwnd, WM_CLOSE, IntPtr.Zero, IntPtr.Zero); } catch { return false; }
        }

        public static void MouseClickAt(int x, int y)
        {
            try
            {
                SetCursorPos(x, y);
                mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero); // LEFTDOWN
                mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero); // LEFTUP
            }
            catch { }
        }

        public static void BeginDrag(IntPtr hwnd)
        {
            try
            {
                ReleaseCapture();
                SendMessage(hwnd, WM_NCLBUTTONDOWN, new IntPtr(HTCAPTION), IntPtr.Zero);
            }
            catch { }
        }

        public static uint GetWindowDpi(IntPtr hwnd)
        {
            try
            {
                uint dpi = GetDpiForWindow(hwnd);
                if (dpi > 0) return dpi;
            }
            catch { }
            return SystemDpi();
        }

        public static uint SystemDpi()
        {
            try
            {
                uint dpi = GetDpiForSystem();
                if (dpi > 0) return dpi;
            }
            catch { }
            IntPtr dc = GetDC(IntPtr.Zero);
            int fallbackDpi = GetDeviceCaps(dc, 88); // LOGPIXELSX
            ReleaseDC(IntPtr.Zero, dc);
            return fallbackDpi > 0 ? (uint)fallbackDpi : 96u;
        }

        public static bool GetWorkArea(out RECT rect)
        {
            rect = new RECT();
            return SystemParametersInfoW(SPI_GETWORKAREA, 0, ref rect, 0);
        }

        /// <summary>窗口所在显示器的工作区。hwnd 无效时退到主屏（SPI_GETWORKAREA）。</summary>
        public static bool GetMonitorWorkArea(IntPtr hwnd, out RECT work)
        {
            work = new RECT();
            try
            {
                IntPtr monitor = IntPtr.Zero;
                if (hwnd != IntPtr.Zero && IsWindow(hwnd)) monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
                if (monitor == IntPtr.Zero)
                {
                    // 用主屏左上角取主显示器，避免 SPI_GETWORKAREA 在混合 DPI 下返回逻辑坐标
                    POINT pt;
                    pt.X = 0;
                    pt.Y = 0;
                    monitor = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST);
                }
                if (monitor != IntPtr.Zero)
                {
                    MONITORINFO info = new MONITORINFO();
                    info.cbSize = Marshal.SizeOf(typeof(MONITORINFO));
                    if (GetMonitorInfo(monitor, ref info))
                    {
                        work = info.rcWork;
                        return true;
                    }
                }
            }
            catch { }
            return GetWorkArea(out work);
        }

        public static bool GetMonitorBounds(IntPtr hwnd, out RECT bounds)
        {
            bounds = new RECT();
            try
            {
                IntPtr monitor = IntPtr.Zero;
                if (hwnd != IntPtr.Zero && IsWindow(hwnd)) monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
                if (monitor == IntPtr.Zero)
                {
                    POINT pt;
                    pt.X = 0;
                    pt.Y = 0;
                    monitor = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST);
                }
                if (monitor != IntPtr.Zero)
                {
                    MONITORINFO info = new MONITORINFO();
                    info.cbSize = Marshal.SizeOf(typeof(MONITORINFO));
                    if (GetMonitorInfo(monitor, ref info))
                    {
                        bounds = info.rcMonitor;
                        return true;
                    }
                }
            }
            catch { }
            return GetWorkArea(out bounds);
        }
    }

    internal sealed class HostConfig
    {
        public bool Enabled = true;
        public int Size = 260;                  // size_mode=fixed 时才用；auto 忽略
        public string SizeMode = "auto";        // auto: min(工作区宽,高)×20%×Scale；fixed: 旧像素值
        public double Scale = 1.0;              // 0.5–3，与 DPI 无关的用户缩放
        public double Opacity = 0.9;
        public string Corner = "bottom-right";
        public int OffsetX;
        public int OffsetY;
        public string Shape = "square";
        public bool Labels;
        public bool Follow = true;
        public bool ClickThrough = true;
        public bool ExcludeFromCapture;         // WDA_EXCLUDEFROMCAPTURE，默认关
        public int MiniRadius = 100;             // R106：小地图视野半径（米），五档 25/50/100/200/300

        public static HostConfig Read(string dir)
        {
            HostConfig cfg = new HostConfig();
            string path = Path.Combine(dir, "eftmap.config.json");
            if (!File.Exists(path)) return cfg;
            try
            {
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> root = ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
                if (root == null) return cfg;
                object ovObj = root.ContainsKey("overlay") ? root["overlay"] : null;
                if (!(ovObj is Dictionary<string, object>)) return cfg;
                Dictionary<string, object> ov = (Dictionary<string, object>)ovObj;
                cfg.Enabled = Bool(ov, "enabled", cfg.Enabled);
                cfg.Size = Int(ov, "size", cfg.Size, 120, 1200);
                cfg.SizeMode = Text(ov, "size_mode", cfg.SizeMode);
                cfg.Scale = Double(ov, "scale", cfg.Scale, 0.5, 3.0);
                cfg.Opacity = Double(ov, "opacity", cfg.Opacity, 0.3, 1.0);
                cfg.Corner = Text(ov, "corner", cfg.Corner);
                cfg.OffsetX = Int(ov, "offset_x", cfg.OffsetX, -800, 800);
                cfg.OffsetY = Int(ov, "offset_y", cfg.OffsetY, -800, 800);
                cfg.Shape = Text(ov, "shape", cfg.Shape);
                cfg.Labels = Bool(ov, "labels", cfg.Labels);
                cfg.Follow = Bool(ov, "follow", cfg.Follow);
                cfg.ClickThrough = Bool(ov, "click_through", cfg.ClickThrough);
                cfg.ExcludeFromCapture = Bool(ov, "exclude_from_capture", cfg.ExcludeFromCapture);
                // R106：五档米制半径。新配置读 mini_radius_m；旧配置只有 map_scale 时按
                // 「半径 = 75 / map_scale」迁移（1.0 = 旧 150 米视野 = 半径 75 米），再吸附到最近档。
                int wantRadius = 100;
                if (ov.ContainsKey("mini_radius_m"))
                {
                    wantRadius = Int(ov, "mini_radius_m", 100, 25, 300);
                }
                else if (ov.ContainsKey("map_scale"))
                {
                    double mapScale = Double(ov, "map_scale", 1.0, 0.5, 3.0);
                    wantRadius = (int)Math.Round(75.0 / mapScale);
                }
                int[] choices = new int[] { 25, 50, 100, 200, 300 };
                int bestRadius = 100;
                int bestDiff = int.MaxValue;
                foreach (int choice in choices)
                {
                    int diff = Math.Abs(choice - wantRadius);
                    if (diff < bestDiff || (diff == bestDiff && choice > bestRadius))
                    {
                        bestRadius = choice;
                        bestDiff = diff;
                    }
                }
                cfg.MiniRadius = bestRadius;
                if (cfg.Corner != "top-left" && cfg.Corner != "top-right" && cfg.Corner != "bottom-left" && cfg.Corner != "bottom-right")
                {
                    cfg.Corner = "bottom-right";
                }
                if (cfg.Shape != "circle") cfg.Shape = "square";
                if (cfg.SizeMode != "fixed") cfg.SizeMode = "auto";
            }
            catch (Exception ex)
            {
                Log.Write("读配置失败，用默认值：" + ex.Message);
            }
            return cfg;
        }

        /// R104：把显隐状态写回 eftmap.config.json 的 overlay.enabled。
        /// 宿主热键 / 托盘切换后调用，保证「左侧栏开关」与「热键状态」永远读同一处；
        /// serve.py 的配置看守线程发现 mtime 变化后会广播 config，主界面开关随之同步。
        /// 只在 ShellMode 下调用（独立小窗隐藏后要能再打开，不能把自己写关）。
        public static void WriteEnabled(string dir, bool enabled)
        {
            string path = Path.Combine(dir, "eftmap.config.json");
            try
            {
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> root = null;
                if (File.Exists(path))
                {
                    root = ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
                }
                if (root == null) root = new Dictionary<string, object>();
                object ovObj = root.ContainsKey("overlay") ? root["overlay"] : null;
                Dictionary<string, object> ov = ovObj as Dictionary<string, object>;
                if (ov == null)
                {
                    ov = new Dictionary<string, object>();
                    root["overlay"] = ov;
                }
                if (Bool(ov, "enabled", false) == enabled) return;   // 值没变就不写，少一次广播
                ov["enabled"] = enabled;
                File.WriteAllText(path, ser.Serialize(root), new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                Log.Write("写 overlay.enabled 失败：" + ex.Message);
            }
        }

        private static bool Bool(Dictionary<string, object> d, string key, bool fallback)
        {
            if (!d.ContainsKey(key)) return fallback;
            object v = d[key];
            if (v is bool) return (bool)v;
            if (v is string) return ((string)v).ToLowerInvariant() == "true";
            return fallback;
        }

        private static int Int(Dictionary<string, object> d, string key, int fallback, int low, int high)
        {
            if (!d.ContainsKey(key)) return fallback;
            try
            {
                int n = Convert.ToInt32(d[key]);
                return Math.Max(low, Math.Min(high, n));
            }
            catch { return fallback; }
        }

        private static double Double(Dictionary<string, object> d, string key, double fallback, double low, double high)
        {
            if (!d.ContainsKey(key)) return fallback;
            try
            {
                double n = Convert.ToDouble(d[key]);
                if (double.IsNaN(n)) return fallback;
                return Math.Max(low, Math.Min(high, n));
            }
            catch { return fallback; }
        }

        private static string Text(Dictionary<string, object> d, string key, string fallback)
        {
            if (!d.ContainsKey(key)) return fallback;
            object v = d[key];
            return v == null ? fallback : Convert.ToString(v);
        }
    }

    internal sealed class HotkeySpec
    {
        public uint Modifiers;
        public uint Vk;
        public string Text;

        public static HotkeySpec Parse(string text)
        {
            if (String.IsNullOrEmpty(text)) return null;
            // 兼容旧写法 `Ctrl-Shift-M`；缩放键请写 Plus / Minus（单独一个 "-" 会被这行当分隔符）
            string[] parts = text.Replace("-", "+").Split('+');
            uint mod = 0;
            string main = null;
            foreach (string raw in parts)
            {
                string p = raw.Trim().ToLowerInvariant();
                if (String.IsNullOrEmpty(p)) continue;
                if (p == "ctrl" || p == "control") mod |= 0x0002;
                else if (p == "alt") mod |= 0x0001;
                else if (p == "shift") mod |= 0x0004;
                else if (p == "win") mod |= 0x0008;
                else main = p;
            }
            if (main == null) return null;
            uint vk;
            if (main.Length == 1 && main[0] >= 'a' && main[0] <= 'z') vk = (uint)(main[0] - 'a' + 'A');
            else if (main.Length == 1 && main[0] >= '0' && main[0] <= '9') vk = (uint)('0' + (main[0] - '0'));
            // R78：缩放热键要能写成 Plus / Minus（VK_OEM_PLUS / VK_OEM_MINUS），
            // RegisterHotKey 收不到滚轮，所以锁定时用这两个键代替 Ctrl+Shift+滚轮。
            else if (main == "plus" || main == "equals" || main == "=" || main == "+") vk = 0xBB;
            else if (main == "minus" || main == "-") vk = 0xBD;
            else if (main.StartsWith("f") && main.Length <= 3)
            {
                int n;
                if (!int.TryParse(main.Substring(1), out n) || n < 1 || n > 24) return null;
                vk = (uint)(0x70 + n - 1);
            }
            else return null;
            HotkeySpec spec = new HotkeySpec();
            spec.Modifiers = mod;
            spec.Vk = vk;
            spec.Text = text;
            return spec;
        }
    }

    internal sealed class MiniForm : Form
    {
        private const int ID_TOGGLE = 0x1001;
        private const int ID_FULL = 0x1002;
        private const int ID_ESC = 0x1003;
        // R78：小地图内部缩放的全局热键（锁定/点击穿透时窗口收不到滚轮，只能走壳）
        private const int ID_ZOOM_IN = 0x1004;
        private const int ID_ZOOM_OUT = 0x1005;
        // R281：游戏内齿轮菜单打开期间临时占用 Esc（与全图的 ID_ESC 分开注册，互不干扰）
        private const int ID_MENU_ESC = 0x1006;
        // 齿轮在页面右上角：6px 边距 + 28px 触控目标；这里给到 44 DIP 的容差热区
        private const int GEAR_HIT_DIP = 44;

        private readonly Options _opt;
        private readonly CoreWebView2Environment _environment;
        private HostConfig _cfg;
        private double _scale;
        private bool _scaleOverride;
        private bool _full;
        private bool _hidden;
        private bool _clickThrough;
        private bool _webReady;
        private bool _webFailed;
        // R281：齿轮菜单状态。_clickThrough 是「当前实际样式」，_cfg.ClickThrough 是用户配置值；
        // 菜单 / 齿轮悬停只改前者，绝不写回配置。
        private bool _menuOpen;
        private bool _gearHover;
        private int _menuOutsideTicks;
        private bool _hotkeyMenuEscOk;
        private bool _hotkeyToggleOk;
        private bool _hotkeyFullOk;
        private bool _hotkeyEscOk;
        private bool _hotkeyZoomInOk;
        private bool _hotkeyZoomOutOk;
        private int _zoomHotkeyCount;
        private HotkeySpec _toggleSpec;
        private HotkeySpec _fullSpec;
        private HotkeySpec _zoomInSpec;
        private HotkeySpec _zoomOutSpec;

        private CoreWebView2Controller _controller;
        private CoreWebView2 _web;
        private string _userDataDir;

        public event EventHandler StateChanged;

        private Timer _configTimer;
        private Timer _topmostTimer;
        private Timer _exitTimer;
        private Timer _gearTimer;

        private readonly Native.EnumChildProc _childProc;
        private readonly List<IntPtr> _children = new List<IntPtr>();
        private bool _applyingChildren;
        private string _shapeApplied = "square";
        private bool _excludeApplied;
        private uint _excludeAffinityResult;
        private int _focusRestoreCount;
        private int _hotkeyCount;

        public MiniForm(Options opt)
            : this(opt, null)
        {
        }

        public MiniForm(Options opt, CoreWebView2Environment environment)
        {
            _opt = opt;
            _environment = environment;
            _cfg = HostConfig.Read(opt.ConfigDir);
            _clickThrough = opt.ClickThrough >= 0 ? (opt.ClickThrough != 0) : _cfg.ClickThrough;
            _scaleOverride = opt.Scale > 0;
            _scale = _scaleOverride ? opt.Scale : Native.SystemDpi() / 96.0;
            _hidden = opt.StartHidden;
            _userDataDir = Path.Combine(opt.ConfigDir, "WebView2");
            _toggleSpec = HotkeySpec.Parse(opt.ToggleHotkey);
            _fullSpec = HotkeySpec.Parse(opt.FullHotkey);
            if (_toggleSpec == null) _toggleSpec = HotkeySpec.Parse("Ctrl+Shift+M");
            if (_fullSpec == null) _fullSpec = HotkeySpec.Parse("Ctrl+Shift+F");
            // R78：缩放热键固定成 Ctrl+Shift+Plus / Minus，明确避开已用的 M / F；
            // 用 OEM_PLUS / OEM_MINUS 是为了让玩家按「+ / -」直觉操作，而不是记字母。
            _zoomInSpec = HotkeySpec.Parse("Ctrl+Shift+Plus");
            _zoomOutSpec = HotkeySpec.Parse("Ctrl+Shift+Minus");

            Text = "EFT 小地图";
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            MinimizeBox = false;
            MaximizeBox = false;
            AutoScaleMode = AutoScaleMode.None;
            BackColor = Color.Black;
            _childProc = new Native.EnumChildProc(OnChildWindow);

            _configTimer = new Timer();
            _configTimer.Interval = 500;
            _configTimer.Tick += OnConfigTick;

            _topmostTimer = new Timer();
            // R76：1 秒重钉一次。全屏游戏/其它置顶窗口会抢 Z 序，3 秒太慢。
            _topmostTimer.Interval = 1000;
            _topmostTimer.Tick += OnTopmostTick;

            // R281：指针轮询。小窗默认点击穿透，页面收不到鼠标事件，
            // 只能由宿主判断「指针是否落在齿轮热区 / 是否已离开窗口」。
            _gearTimer = new Timer();
            _gearTimer.Interval = 90;
            _gearTimer.Tick += OnGearTick;

            if (opt.ExitAfterMs > 0)
            {
                _exitTimer = new Timer();
                _exitTimer.Interval = opt.ExitAfterMs;
                _exitTimer.Tick += delegate { Log.Write("exit-after 到时，关闭宿主"); Close(); };
            }
        }

        protected override bool ShowWithoutActivation
        {
            get { return true; }
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                // WS_POPUP + 去掉一切系统边框；扩展样式固定为工具窗 + 不激活 + 分层
                cp.Style &= ~(Native.WS_CAPTION | Native.WS_THICKFRAME | Native.WS_SYSMENU |
                              Native.WS_MINIMIZEBOX | Native.WS_MAXIMIZEBOX |
                              Native.WS_BORDER | Native.WS_DLGFRAME);
                cp.Style |= unchecked((int)0x80000000); // WS_POPUP
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE | Native.WS_EX_LAYERED;
                if (_clickThrough) cp.ExStyle |= Native.WS_EX_TRANSPARENT;
                else cp.ExStyle &= ~Native.WS_EX_TRANSPARENT;
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            Log.Write("HWND 创建：" + Handle.ToString());
            ApplyWindowStyles();
            DisableDwmDecorations();
            ApplyLayout();
            if (_opt.Hotkeys) RegisterHotkeys();
            _configTimer.Start();
            _topmostTimer.Start();
            _gearTimer.Start();
            if (_exitTimer != null) _exitTimer.Start();
            if (!_opt.StartHidden)
            {
                Native.ShowWindow(Handle, Native.SW_SHOWNOACTIVATE);
            }
            BeginInvoke(new Action(InitializeWebView));
        }

        protected override void OnDpiChanged(DpiChangedEventArgs e)
        {
            base.OnDpiChanged(e);
            if (!_scaleOverride)
            {
                _scale = (double)e.DeviceDpiNew / 96.0;
                Log.Write("DPI 变化：" + e.DeviceDpiOld + " -> " + e.DeviceDpiNew + "，scale=" + _scale.ToString("0.###"));
                ApplyLayout();
            }
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (_controller != null)
            {
                _controller.Bounds = new Rectangle(0, 0, ClientSize.Width, ClientSize.Height);
            }
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            _configTimer.Stop();
            _topmostTimer.Stop();
            _gearTimer.Stop();
            if (_exitTimer != null) _exitTimer.Stop();
            if (_opt.Hotkeys)
            {
                Native.UnregisterHotKey(Handle, ID_TOGGLE);
                Native.UnregisterHotKey(Handle, ID_FULL);
                Native.UnregisterHotKey(Handle, ID_ESC);
                Native.UnregisterHotKey(Handle, ID_ZOOM_IN);
                Native.UnregisterHotKey(Handle, ID_ZOOM_OUT);
                Native.UnregisterHotKey(Handle, ID_MENU_ESC);
            }
            if (_controller != null)
            {
                try { _controller.Close(); } catch { }
                _controller = null;
            }
            base.OnFormClosed(e);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_HOTKEY)
            {
                int id = m.WParam.ToInt32();
                // R76 还焦：热键处理前记住前台窗口；只有确认焦点被本窗口夺走时才还原，
                // 否则会误抢用户正在用的其它窗口。
                IntPtr before = Native.GetForegroundWindow();
                _hotkeyCount++;
                if (id == ID_TOGGLE) ToggleVisible();
                else if (id == ID_FULL) ToggleFull();
                else if (id == ID_ESC) ExitFull();
                else if (id == ID_MENU_ESC)
                {
                    // R281：菜单打开期间 Esc 被宿主占用，页面收不到键盘事件，这里转发关闭指令。
                    SendMenuToPage(false);
                    CloseMenuState();
                }
                else if (id == ID_ZOOM_IN) { _zoomHotkeyCount++; SendZoomToPage(1); }
                else if (id == ID_ZOOM_OUT) { _zoomHotkeyCount++; SendZoomToPage(-1); }
                RestoreFocusSoon(before);
                return;
            }
            if (m.Msg == Native.WM_DISPLAYCHANGE)
            {
                // 分辨率/显示器变化：按新的工作区重新算尺寸与位置，不沿用旧像素值。
                BeginInvoke(new Action(delegate { ApplyLayout(); ApplyShape(); }));
            }
            base.WndProc(ref m);
        }

        private void RestoreFocusSoon(IntPtr before)
        {
            if (before == IntPtr.Zero) return;
            Task.Delay(250).ContinueWith(delegate
            {
                try { BeginInvoke(new Action(delegate { RestoreFocus(before); })); }
                catch { }
            });
        }

        private void RestoreFocus(IntPtr before)
        {
            try
            {
                if (!Native.IsWindow(before)) return;
                IntPtr now = Native.GetForegroundWindow();
                if (now == before || now == IntPtr.Zero) return;
                // 只有当焦点确实落在本窗口（或本窗口的子窗口）时才还焦。
                bool ours = now == Handle || IsChildOfOurs(now);
                if (!ours)
                {
                    Log.Write("前台已切到其它窗口（非小地图），不还焦：before=" + before.ToInt64() + " now=" + now.ToInt64());
                    return;
                }
                Native.SetForegroundWindow(before);
                _focusRestoreCount++;
                Log.Write("还焦 → " + before.ToInt64() + "（hotkey #" + _hotkeyCount + "）");
            }
            catch (Exception ex) { Log.Write("还焦失败：" + ex.Message); }
        }

        private bool IsChildOfOurs(IntPtr hwnd)
        {
            try
            {
                foreach (IntPtr child in _children)
                {
                    if (child == hwnd) return true;
                }
            }
            catch { }
            return false;
        }

        private void RegisterHotkeys()
        {
            _hotkeyToggleOk = Native.RegisterHotKey(Handle, ID_TOGGLE, _toggleSpec.Modifiers, _toggleSpec.Vk);
            _hotkeyFullOk = Native.RegisterHotKey(Handle, ID_FULL, _fullSpec.Modifiers, _fullSpec.Vk);
            string zoomInErr = "";
            if (_zoomInSpec != null && _zoomOutSpec != null)
            {
                _hotkeyZoomInOk = Native.RegisterHotKey(Handle, ID_ZOOM_IN, _zoomInSpec.Modifiers, _zoomInSpec.Vk);
                _hotkeyZoomOutOk = Native.RegisterHotKey(Handle, ID_ZOOM_OUT, _zoomOutSpec.Modifiers, _zoomOutSpec.Vk);
                if (!_hotkeyZoomInOk || !_hotkeyZoomOutOk)
                {
                    zoomInErr = "（缩放热键被占用，" + _zoomInSpec.Text + "=" + _hotkeyZoomInOk +
                                " " + _zoomOutSpec.Text + "=" + _hotkeyZoomOutOk + "）";
                }
            }
            Log.Write("热键注册 " + _toggleSpec.Text + "=" + _hotkeyToggleOk + " " + _fullSpec.Text + "=" + _hotkeyFullOk +
                      (_zoomInSpec == null ? "" : " " + _zoomInSpec.Text + "=" + _hotkeyZoomInOk +
                                               " " + _zoomOutSpec.Text + "=" + _hotkeyZoomOutOk) + zoomInErr);
            RaiseStateChanged();
        }

        private void ToggleVisible()
        {
            if (_full) ExitFull();
            if (_hidden) ShowNoActivate();
            else HideWindow();
            // R104：热键 / 托盘切换后回写同一个配置项，避免「页面开关是开、热键已关」的分叉。
            // 独立小窗（非壳模式）隐藏后会等配置轮询把自己关掉，所以只在壳模式回写。
            if (_opt.ShellMode) HostConfig.WriteEnabled(_opt.ConfigDir, !_hidden);
            RaiseStateChanged();
        }

        private void ToggleFull()
        {
            if (_full) ExitFull();
            else EnterFull();
        }

        private void EnterFull()
        {
            if (_full) return;
            _full = true;
            _hidden = false;
            ShowNoActivate();
            // R281：全图模式不显示齿轮；先把菜单关掉（全图本身就不穿透，不要在这里恢复配置值）
            _gearHover = false;
            SendMenuToPage(false);
            CloseMenuState();
            SetClickThrough(false);
            ApplyLayout();
            SendFullToPage(true);
            _hotkeyEscOk = Native.RegisterHotKey(Handle, ID_ESC, 0, 0x1B);
            Log.Write("进入全图模式，Esc 注册=" + _hotkeyEscOk);
            RaiseStateChanged();
        }

        private void ExitFull()
        {
            if (!_full) return;
            _full = false;
            Native.UnregisterHotKey(Handle, ID_ESC);
            _hotkeyEscOk = false;
            SetClickThrough(_cfg.ClickThrough);
            ApplyLayout();
            SendFullToPage(false);
            Log.Write("退出全图模式");
            RaiseStateChanged();
        }

        private void SendFullToPage(bool on)
        {
            if (_web == null) return;
            try
            {
                _web.ExecuteScriptAsync("window.__tkMiniFull && window.__tkMiniFull('" + (on ? "on" : "off") + "')");
            }
            catch (Exception ex) { Log.Write("__tkMiniFull 调用失败：" + ex.Message); }
        }

        // ------------------------------------------------------------ R281 齿轮菜单
        /// <summary>把菜单开合指令发给小地图页面（页面负责搬入/搬出三个页签的内容）。</summary>
        private void SendMenuToPage(bool on)
        {
            if (_web == null) return;
            try
            {
                _web.ExecuteScriptAsync("window.__tkMiniMenu && window.__tkMiniMenu('" + (on ? "on" : "off") + "')");
            }
            catch (Exception ex) { Log.Write("__tkMiniMenu 调用失败：" + ex.Message); }
        }

        /// <summary>
        /// 页面通过 WebMessage 汇报菜单开合：开着必须保持窗口可点（菜单里的滑条 / 勾选要能用），
        /// 关上就回到「配置里的穿透值」；只在当前实际样式与目标不同时才改，避免每帧刷样式。
        /// </summary>
        private void OnWebMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string msg = null;
            try { msg = e.TryGetWebMessageAsString(); } catch { }
            if (String.IsNullOrEmpty(msg)) return;
            if (msg == "tk-mini-menu:1") OpenMenuState();
            else if (msg == "tk-mini-menu:0") CloseMenuState();
        }

        private void OpenMenuState()
        {
            if (_menuOpen || _full) return;
            _menuOpen = true;
            _menuOutsideTicks = 0;
            _gearHover = false;
            _clickThrough = false;
            ApplyWindowStyles();
            ApplyShape();   // 菜单期间改回方形，避免圆角区域裁掉菜单
            if (_opt.Hotkeys)
            {
                // 点开菜单后窗口不会激活（WS_EX_NOACTIVATE），页面收不到键盘事件；
                // 菜单期间临时注册 Esc，让「Esc 收起」在游戏里也成立。
                _hotkeyMenuEscOk = Native.RegisterHotKey(Handle, ID_MENU_ESC, 0, 0x1B);
                Log.Write("齿轮菜单打开，Esc 注册=" + _hotkeyMenuEscOk);
            }
            Log.Write("齿轮菜单打开，点击穿透=关闭");
            RaiseStateChanged();
        }

        private void CloseMenuState()
        {
            if (!_menuOpen) return;
            _menuOpen = false;
            _menuOutsideTicks = 0;
            if (_opt.Hotkeys)
            {
                Native.UnregisterHotKey(Handle, ID_MENU_ESC);
                _hotkeyMenuEscOk = false;
            }
            // 指针可能还停在齿轮上：保持可点，交给下一拍轮询判断是否离开热区。
            // 窗口已隐藏时不要把指针判成「悬停」，否则再显示会停在关穿透状态。
            _gearHover = _hidden ? false : CursorInGearArea();
            _clickThrough = _full || _gearHover ? false : _cfg.ClickThrough;
            ApplyWindowStyles();
            ApplyShape();   // 恢复配置里的圆形 / 方形
            Log.Write("齿轮菜单关闭，点击穿透=" + _clickThrough);
            RaiseStateChanged();
        }

        /// <summary>指针是否落在右上角齿轮热区（窗口物理像素；多屏 DPI 用 _scale 换算）。</summary>
        private bool CursorInGearArea()
        {
            Native.POINT pt;
            if (!Native.GetCursorPos(out pt)) return false;
            Native.RECT wr;
            if (!Native.GetWindowRect(Handle, out wr)) return false;
            return PointInGearArea(pt, wr);
        }

        private bool PointInGearArea(Native.POINT pt, Native.RECT wr)
        {
            double s = _scale > 0 ? _scale : 1.0;
            int w = wr.Right - wr.Left;
            int h = wr.Bottom - wr.Top;
            if (w <= 0 || h <= 0) return false;
            if (_cfg.Shape == "circle")
            {
                // 圆形窗口被 SetWindowRgn 裁成椭圆：页面把齿轮按 17% 内缩放进圆内，
                // 热区必须跟着走，否则贴着窗口角落判断会永远点不到。
                int insetX = (int)Math.Round(w * 0.17);
                int insetY = (int)Math.Round(h * 0.17);
                int gear = (int)Math.Round(28 * s);
                int pad = (int)Math.Round(10 * s);
                return pt.X >= wr.Right - insetX - gear - pad && pt.X <= wr.Right - insetX + pad &&
                       pt.Y >= wr.Top + insetY - pad && pt.Y <= wr.Top + insetY + gear + pad;
            }
            int hit = (int)Math.Round(GEAR_HIT_DIP * s);
            if (hit > w / 2) { hit = Math.Max(24, w / 2); }
            return pt.X >= wr.Right - hit && pt.X <= wr.Right &&
                   pt.Y >= wr.Top && pt.Y <= wr.Top + hit;
        }

        /// <summary>
        /// R281：90ms 一拍。小窗默认穿透，页面拿不到任何鼠标事件，所以：
        /// 1) 菜单关着 → 指针进齿轮热区临时关穿透（离开就恢复）；
        /// 2) 菜单开着 → 指针离开窗口 2 拍（约 180ms）自动收起，避免长时间吃掉游戏鼠标。
        /// </summary>
        private void OnGearTick(object sender, EventArgs e)
        {
            if (!IsHandleCreated) return;
            Native.POINT pt;
            if (!Native.GetCursorPos(out pt)) return;
            Native.RECT wr;
            if (!Native.GetWindowRect(Handle, out wr)) return;

            if (_hidden || _full)
            {
                if (_gearHover)
                {
                    _gearHover = false;
                    // 全图模式必须保持不穿透（EnterFull 已经关掉了）；隐藏时恢复与否无所谓，
                    // 但回到配置值可以避免下次显示时停在「临时关穿透」的残留状态。
                    if (!_full)
                    {
                        _clickThrough = _cfg.ClickThrough;
                        ApplyWindowStyles();
                    }
                }
                return;
            }

            if (_menuOpen)
            {
                bool inside = pt.X >= wr.Left && pt.X <= wr.Right &&
                              pt.Y >= wr.Top && pt.Y <= wr.Bottom;
                if (inside)
                {
                    _menuOutsideTicks = 0;
                }
                else if (++_menuOutsideTicks >= 2)
                {
                    SendMenuToPage(false);
                    CloseMenuState();
                }
                return;
            }

            // 当前本来就不可点（用户关了穿透 / 全图 / 菜单）时不需要热区判断。
            if (!_clickThrough)
            {
                if (_gearHover)
                {
                    _gearHover = false;
                    _clickThrough = false;
                    ApplyWindowStyles();
                }
                return;
            }

            bool over = PointInGearArea(pt, wr);
            if (over == _gearHover) return;
            _gearHover = over;
            _clickThrough = !over;
            ApplyWindowStyles();
            Log.Write("齿轮热区：" + (over ? "进入 → 临时关穿透" : "离开 → 恢复穿透"));
        }

        /// R78：把缩放指令发给小地图页面（页面负责夹取 0.5–3、以玩家为锚重算视野、写回配置）。
        private void SendZoomToPage(int dir)
        {
            if (_web == null) return;
            try
            {
                _web.ExecuteScriptAsync("window.__tkMiniZoom && window.__tkMiniZoom(" + (dir >= 0 ? 1 : -1) + ")");
                // 页面异步渲染；稍后再刷新诊断/截图，避免拍到缩放前的旧帧。
                Task.Delay(300).ContinueWith(delegate
                {
                    try { BeginInvoke(new Action(RaiseStateChanged)); } catch { }
                });
            }
            catch (Exception ex) { Log.Write("__tkMiniZoom 调用失败：" + ex.Message); }
        }

        private void ShowNoActivate()
        {
            _hidden = false;
            ClampToVisible();
            Native.ShowWindow(Handle, Native.SW_SHOWNOACTIVATE);
            ApplyWindowStyles();
            ApplyLayout();
            RaiseStateChanged();
        }

        private void HideWindow()
        {
            _hidden = true;
            // R281：窗口隐藏时菜单必须一起收起，否则再显示时还停在「菜单打开、穿透关闭」的状态。
            _gearHover = false;
            _clickThrough = _full ? false : _cfg.ClickThrough;
            SendMenuToPage(false);
            CloseMenuState();
            Native.ShowWindow(Handle, Native.SW_HIDE);
            RaiseStateChanged();
        }

        private void OnConfigTick(object sender, EventArgs e)
        {
            HostConfig fresh = HostConfig.Read(_opt.ConfigDir);
            bool wasEnabled = _cfg.Enabled;

            if (!_opt.IgnoreEnabled && !fresh.Enabled)
            {
                if (_opt.ShellMode)
                {
                    // 壳内小地图不销毁：页面把开关关掉时只隐藏，热键/托盘仍能再打开。
                    if (!_hidden) HideWindow();
                }
                else
                {
                    Log.Write("配置里关掉了小浮窗，退出");
                    Close();
                    return;
                }
            }

            bool sizeChanged = fresh.Size != _cfg.Size || fresh.Corner != _cfg.Corner ||
                               fresh.OffsetX != _cfg.OffsetX || fresh.OffsetY != _cfg.OffsetY ||
                               Math.Abs(fresh.Scale - _cfg.Scale) > 0.0001 ||
                               fresh.SizeMode != _cfg.SizeMode;
            bool opacityChanged = Math.Abs(fresh.Opacity - _cfg.Opacity) > 0.001;
            bool clickChanged = fresh.ClickThrough != _cfg.ClickThrough;
            bool shapeChanged = fresh.Shape != _cfg.Shape;
            bool excludeChanged = fresh.ExcludeFromCapture != _cfg.ExcludeFromCapture;

            _cfg = fresh;
            if (sizeChanged) ApplyLayout();
            if (shapeChanged) ApplyShape();
            if (excludeChanged) ApplyDisplayAffinity();
            if (opacityChanged) ApplyOpacity();
            if (clickChanged && !_full && !_menuOpen && !_gearHover) SetClickThrough(_cfg.ClickThrough);
            if (_opt.ShellMode && !wasEnabled && fresh.Enabled && _hidden && !_full)
            {
                ShowNoActivate();
            }
        }

        private void OnTopmostTick(object sender, EventArgs e)
        {
            PinTopmost();
            EnsureChildTransparent();
        }

        private void ApplyWindowStyles()
        {
            if (!IsHandleCreated) return;
            IntPtr hwnd = Handle;
            int ex = (int)Native.GetStyle(hwnd, Native.GWL_EXSTYLE).ToInt64();
            ex |= Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE;
            if (_opt.Transparent) ex |= Native.WS_EX_LAYERED;
            else ex &= ~Native.WS_EX_LAYERED;
            if (_clickThrough) ex |= Native.WS_EX_TRANSPARENT;
            else ex &= ~Native.WS_EX_TRANSPARENT;
            Native.SetStyle(hwnd, Native.GWL_EXSTYLE, new IntPtr(ex));

            int style = (int)Native.GetStyle(hwnd, Native.GWL_STYLE).ToInt64();
            style &= ~(Native.WS_CAPTION | Native.WS_THICKFRAME | Native.WS_SYSMENU |
                       Native.WS_MINIMIZEBOX | Native.WS_MAXIMIZEBOX |
                       Native.WS_BORDER | Native.WS_DLGFRAME);
            style |= unchecked((int)0x80000000);
            Native.SetStyle(hwnd, Native.GWL_STYLE, new IntPtr(style));

            PinTopmost();
            ApplyOpacity();
            ApplyDisplayAffinity();
        }

        private void PinTopmost()
        {
            if (!IsHandleCreated) return;
            Native.SetWindowPos(Handle, Native.HWND_TOPMOST, 0, 0, 0, 0,
                Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
        }

        private void ApplyOpacity()
        {
            if (!IsHandleCreated) return;
            if (_opt.OpacityMode != "window" || !_opt.Transparent) return;
            byte alpha = (byte)Math.Round(Math.Max(0.0, Math.Min(1.0, _cfg.Opacity)) * 255.0);
            Native.SetLayeredWindowAttributes(Handle, 0, alpha, Native.LWA_ALPHA);
        }

        private void DisableDwmDecorations()
        {
            int disabled = Native.DWMNCRP_DISABLED;
            try { Native.DwmSetWindowAttribute(Handle, Native.DWMWA_NCRENDERING_POLICY, ref disabled, 4); } catch { }
            int noRound = Native.DWMWCP_DONOTROUND;
            try { Native.DwmSetWindowAttribute(Handle, Native.DWMWA_WINDOW_CORNER_PREFERENCE, ref noRound, 4); } catch { }
            int noBorder = unchecked((int)Native.DWMWA_COLOR_NONE);
            try { Native.DwmSetWindowAttribute(Handle, Native.DWMWA_BORDER_COLOR, ref noBorder, 4); } catch { }
        }

        private void SetClickThrough(bool enabled)
        {
            _clickThrough = enabled;
            ApplyWindowStyles();
            Log.Write("点击穿透=" + enabled);
            RaiseStateChanged();
        }

        private bool OnChildWindow(IntPtr hwnd, IntPtr lParam)
        {
            if (_applyingChildren) return true;
            _applyingChildren = true;
            try
            {
                int ex = (int)Native.GetStyle(hwnd, Native.GWL_EXSTYLE).ToInt64();
                // 只加不减：WebView2 的 RenderWidgetHost 在分层父窗口里需要这个样式才能正常合成；
                // 去掉它会让整块网页内容消失。点击穿透只由顶层窗口的样式控制。
                if ((ex & Native.WS_EX_TRANSPARENT) == 0)
                {
                    Native.SetStyle(hwnd, Native.GWL_EXSTYLE, new IntPtr(ex | Native.WS_EX_TRANSPARENT));
                }
                _children.Add(hwnd);
            }
            catch { }
            finally
            {
                _applyingChildren = false;
            }
            return true;
        }

        private void EnsureChildTransparent()
        {
            if (!IsHandleCreated) return;
            _children.Clear();
            Native.EnumChildWindows(Handle, _childProc, IntPtr.Zero);
        }

        private void ApplyLayout()
        {
            if (!IsHandleCreated) return;
            // R76：按窗口所在显示器的工作区计算（原来只取主屏 SPI_GETWORKAREA，副屏会越界）。
            Native.RECT work;
            if (!Native.GetMonitorWorkArea(Handle, out work) || work.Right <= work.Left)
            {
                Log.Write("拿不到工作区，保持当前尺寸");
                return;
            }
            int workW = work.Right - work.Left;
            int workH = work.Bottom - work.Top;

            int x, y, w, h;
            if (_full)
            {
                w = (int)Math.Round(_opt.FullWidth * _scale);
                h = (int)Math.Round(_opt.FullHeight * _scale);
                if (w > workW) w = workW;
                if (h > workH) h = workH;
                x = work.Left + (workW - w) / 2;
                y = work.Top + (workH - h) / 2;
            }
            else
            {
                int size = EffectiveSize(work);
                int margin = (int)Math.Round(16 * _scale);
                int ox = (int)Math.Round(_cfg.OffsetX * _scale);
                int oy = (int)Math.Round(_cfg.OffsetY * _scale);
                bool left = _cfg.Corner == "top-left" || _cfg.Corner == "bottom-left";
                bool top = _cfg.Corner == "top-left" || _cfg.Corner == "top-right";
                x = left ? work.Left + margin : work.Right - size - margin;
                y = top ? work.Top + margin : work.Bottom - size - margin;
                x += ox;
                y += oy;
                w = size;
                h = size;
            }

            // 多屏夹取：任何情况都不允许窗口落在工作区之外（跨屏 / 拔掉副屏 / 大偏移量）。
            if (x < work.Left) x = work.Left;
            if (y < work.Top) y = work.Top;
            if (x + w > work.Right) x = work.Right - w;
            if (y + h > work.Bottom) y = work.Bottom - h;
            if (x < work.Left) x = work.Left;
            if (y < work.Top) y = work.Top;

            Log.Write("布局 " + w + "x" + h + " @ (" + x + "," + y + ") dpiScale=" + _scale.ToString("0.###") +
                      " userScale=" + _cfg.Scale.ToString("0.###") + " mode=" + _cfg.SizeMode +
                      " work=[" + work.Left + "," + work.Top + "," + work.Right + "," + work.Bottom + "]" +
                      " full=" + _full);
            Native.SetWindowPos(Handle, Native.HWND_TOPMOST, x, y, w, h, Native.SWP_NOACTIVATE);
            if (_controller != null)
            {
                _controller.Bounds = new Rectangle(0, 0, w, h);
            }
            ApplyShape();
        }

        /// <summary>尺寸基准 = min(工作区宽,高) × 20% × 用户缩放(0.5–3)。不再沿用旧像素值。</summary>
        private int EffectiveSize(Native.RECT work)
        {
            int workW = work.Right - work.Left;
            int workH = work.Bottom - work.Top;
            int basePx = Math.Min(workW, workH);
            int size;
            if (_cfg.SizeMode == "fixed")
            {
                size = (int)Math.Round(_cfg.Size * _scale);
            }
            else
            {
                size = (int)Math.Round(basePx * 0.20 * _cfg.Scale);
            }
            return Math.Max(96, Math.Min(basePx, size));
        }

        /// <summary>收起/唤起前把窗口夹回它所在显示器的工作区，避免回到已被拔掉的副屏。</summary>
        private void ClampToVisible()
        {
            if (!IsHandleCreated) return;
            Native.RECT wr = new Native.RECT();
            Native.RECT work;
            if (!Native.GetWindowRect(Handle, out wr)) return;
            if (!Native.GetMonitorWorkArea(Handle, out work)) return;
            int w = wr.Right - wr.Left;
            int h = wr.Bottom - wr.Top;
            if (w <= 0 || h <= 0) return;
            int x = wr.Left;
            int y = wr.Top;
            if (x < work.Left) x = work.Left;
            if (y < work.Top) y = work.Top;
            if (x + w > work.Right) x = work.Right - w;
            if (y + h > work.Bottom) y = work.Bottom - h;
            if (x < work.Left) x = work.Left;
            if (y < work.Top) y = work.Top;
            if (x != wr.Left || y != wr.Top)
            {
                Log.Write("唤起前夹取 " + wr.Left + "," + wr.Top + " → " + x + "," + y);
                Native.SetWindowPos(Handle, Native.HWND_TOPMOST, x, y, w, h, Native.SWP_NOACTIVATE);
            }
        }

        private void ApplyShape()
        {
            if (!IsHandleCreated) return;
            // R281：菜单打开期间临时改回方形 —— 圆形窗口被 SetWindowRgn 裁成椭圆后，
            // 菜单四角会被裁掉，页面里的齿轮也在椭圆之外点不到。
            string shape = (_menuOpen || _cfg.Shape != "circle") ? "square" : "circle";
            if (shape == "circle")
            {
                int w = ClientSize.Width;
                int h = ClientSize.Height;
                if (w <= 0 || h <= 0) return;
                // 区域只作用于顶层窗；WebView2 的 Chrome_RenderWidgetHostHWND 不受影响。
                IntPtr rgn = Native.CreateEllipticRgn(0, 0, w + 1, h + 1);
                if (rgn != IntPtr.Zero)
                {
                    if (Native.SetWindowRgn(Handle, rgn, true) == 0)
                    {
                        Native.DeleteObject(rgn);   // 设置失败时区域仍归我们，必须释放
                    }
                }
            }
            else
            {
                Native.SetWindowRgn(Handle, IntPtr.Zero, true);   // 清除区域 → 方形
            }
            if (_shapeApplied != shape)
            {
                _shapeApplied = shape;
                Log.Write("小地图形状=" + shape + " client=" + ClientSize.Width + "x" + ClientSize.Height);
            }
        }

        private void ApplyDisplayAffinity()
        {
            if (!IsHandleCreated) return;
            uint want = _cfg.ExcludeFromCapture ? Native.WDA_EXCLUDEFROMCAPTURE : Native.WDA_NONE;
            bool ok = false;
            try
            {
                ok = Native.SetWindowDisplayAffinity(Handle, want);
                _excludeAffinityResult = want;
            }
            catch { }
            _excludeApplied = _cfg.ExcludeFromCapture && ok;
            Log.Write("SetWindowDisplayAffinity(" + (want == 0 ? "WDA_NONE" : "WDA_EXCLUDEFROMCAPTURE") + ")=" + ok);
        }

        private async void InitializeWebView()
        {
            try
            {
                // 壳模式下必须复用主窗口已经创建的 Environment / UDF；
                // 独立 MiniHost 模式才自己建（同一个 UDF 不能被两个进程同时持有）。
                CoreWebView2Environment env = _environment;
                if (env == null)
                {
                    Directory.CreateDirectory(_userDataDir);
                    env = await CoreWebView2Environment.CreateAsync(null, _userDataDir, null);
                }
                CoreWebView2Controller controller = await env.CreateCoreWebView2ControllerAsync(Handle);
                _controller = controller;
                controller.Bounds = new Rectangle(0, 0, ClientSize.Width, ClientSize.Height);
                if (_opt.Transparent)
                {
                    controller.DefaultBackgroundColor = Color.Transparent;
                }
                controller.IsVisible = true;
                _web = controller.CoreWebView2;
                _web.ProcessFailed += OnMiniProcessFailed;
                _web.Settings.AreDefaultContextMenusEnabled = false;
                _web.Settings.IsZoomControlEnabled = false;
                _web.Settings.IsStatusBarEnabled = false;
                _web.Settings.AreDevToolsEnabled = false;
                // R281：齿轮菜单的开合状态走页面 → 宿主的 WebMessage（"tk-mini-menu:1/0"）
                try { _web.Settings.IsWebMessageEnabled = true; } catch { }
                _web.WebMessageReceived += OnWebMessage;
                if (!String.IsNullOrEmpty(_opt.MapKey))
                {
                    string key = _opt.MapKey.Replace("\\", "\\\\").Replace("'", "\\'");
                    await _web.AddScriptToExecuteOnDocumentCreatedAsync(
                        "try{localStorage.setItem('eftmap.map','" + key + "')}catch(e){}");
                }
                if (_opt.DumpDom)
                {
                    await _web.AddScriptToExecuteOnDocumentCreatedAsync(
                        "window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message)+' @ '+e.filename+':'+e.lineno)});");
                    _web.NavigationCompleted += OnNavigationCompleted;
                }
                _web.Navigate(_opt.Url);
                _webReady = true;
                Log.Write("WebView2 就绪，导航：" + _opt.Url);
                BeginInvoke(new Action(delegate { EnsureChildTransparent(); }));
            }
            catch (Exception ex)
            {
                _webFailed = true;
                Log.Write("WebView2 初始化失败：" + ex.GetType().FullName + ": " + ex.Message);
                RaiseStateChanged();
            }
        }

        private bool _rebuilding;

        /// <summary>R76：渲染进程崩溃时重建 WebView2 控件，而不是留一块空白。</summary>
        private async void OnMiniProcessFailed(object sender, CoreWebView2ProcessFailedEventArgs e)
        {
            Log.Write("小地图 WebView2 进程异常：" + e.ProcessFailedKind);
            if (_rebuilding) return;
            _rebuilding = true;
            try
            {
                if (_controller != null) _controller.Close();
            }
            catch { }
            _controller = null;
            _web = null;
            _webReady = false;
            _webFailed = false;
            RaiseStateChanged();
            await Task.Delay(1200);
            _rebuilding = false;
            if (!IsDisposed && IsHandleCreated) InitializeWebView();
        }

        public bool WebFailed { get { return _webFailed; } }
        public bool WebReady { get { return _webReady; } }
        public bool IsMiniVisible { get { return !_hidden; } }
        public bool IsFullMode { get { return _full; } }

        public void ToggleMini()
        {
            ToggleVisible();
        }

        public void EnterFullMode()
        {
            EnterFull();
        }

        public void ExitFullMode()
        {
            ExitFull();
        }

        public void HideMini()
        {
            if (!_hidden) HideWindow();
        }

        public void ShowMini()
        {
            if (_hidden) ShowNoActivate();
        }

        public Dictionary<string, object> GetWindowState()
        {
            Dictionary<string, object> d = new Dictionary<string, object>();
            if (!IsHandleCreated)
            {
                d["created"] = false;
                return d;
            }
            Native.RECT wr = new Native.RECT();
            Native.RECT cr = new Native.RECT();
            Native.RECT work = new Native.RECT();
            Native.GetWindowRect(Handle, out wr);
            Native.GetClientRect(Handle, out cr);
            Native.GetMonitorWorkArea(Handle, out work);
            int style = (int)Native.GetStyle(Handle, Native.GWL_STYLE).ToInt64();
            int ex = (int)Native.GetStyle(Handle, Native.GWL_EXSTYLE).ToInt64();
            List<string> flags = new List<string>();
            if ((ex & Native.WS_EX_TOOLWINDOW) != 0) flags.Add("WS_EX_TOOLWINDOW");
            if ((ex & Native.WS_EX_NOACTIVATE) != 0) flags.Add("WS_EX_NOACTIVATE");
            if ((ex & Native.WS_EX_LAYERED) != 0) flags.Add("WS_EX_LAYERED");
            if ((ex & Native.WS_EX_TRANSPARENT) != 0) flags.Add("WS_EX_TRANSPARENT");
            if ((ex & Native.WS_EX_TOPMOST) != 0) flags.Add("WS_EX_TOPMOST");
            d["created"] = true;
            d["hwnd"] = Handle.ToInt64().ToString();
            d["title"] = Text;
            d["bounds"] = new Dictionary<string, object> {
                { "x", wr.Left }, { "y", wr.Top }, { "w", wr.Right - wr.Left }, { "h", wr.Bottom - wr.Top }
            };
            d["client"] = new Dictionary<string, object> {
                { "w", cr.Right - cr.Left }, { "h", cr.Bottom - cr.Top }
            };
            d["workArea"] = new Dictionary<string, object> {
                { "left", work.Left }, { "top", work.Top }, { "right", work.Right }, { "bottom", work.Bottom }
            };
            d["style"] = String.Format("0x{0:X8}", style);
            d["exStyle"] = String.Format("0x{0:X8}", ex);
            d["exStyleFlags"] = flags;
            d["visible"] = Native.IsWindowVisible(Handle);
            d["hidden"] = _hidden;
            d["full"] = _full;
            d["clickThrough"] = _clickThrough;
            d["menuOpen"] = _menuOpen;
            d["gearHover"] = _gearHover;
            d["topmost"] = (ex & Native.WS_EX_TOPMOST) != 0;
            d["showInTaskbar"] = false;
            d["scale"] = _scale;
            d["dpi"] = Native.GetWindowDpi(Handle);
            d["configuredSize"] = _cfg.Size;
            d["configuredSizeMode"] = _cfg.SizeMode;
            d["configuredScale"] = _cfg.Scale;
            d["effectiveSize"] = EffectiveSize(work);
            d["corner"] = _cfg.Corner;
            d["margin"] = 16;
            d["opacity"] = _cfg.Opacity;
            d["shape"] = _shapeApplied;
            d["sizeMode"] = _cfg.SizeMode;
            d["excludeFromCapture"] = _cfg.ExcludeFromCapture;
            d["excludeFromCaptureApplied"] = _excludeApplied;
            d["displayAffinity"] = _excludeAffinityResult;
            Native.RECT mb = new Native.RECT();
            Native.GetMonitorBounds(Handle, out mb);
            d["monitor"] = new Dictionary<string, object> {
                { "left", mb.Left }, { "top", mb.Top }, { "right", mb.Right }, { "bottom", mb.Bottom },
                { "w", mb.Right - mb.Left }, { "h", mb.Bottom - mb.Top }
            };
            d["hotkeyCount"] = _hotkeyCount;
            d["zoomHotkeyCount"] = _zoomHotkeyCount;
            d["focusRestoreCount"] = _focusRestoreCount;
            d["webReady"] = _webReady;
            d["webFailed"] = _webFailed;
            d["hotkeys"] = new Dictionary<string, object> {
                { _toggleSpec.Text, _hotkeyToggleOk },
                { _fullSpec.Text, _hotkeyFullOk },
                { "Esc", _hotkeyEscOk },
                { _zoomInSpec != null ? _zoomInSpec.Text : "Ctrl+Shift+Plus", _hotkeyZoomInOk },
                { _zoomOutSpec != null ? _zoomOutSpec.Text : "Ctrl+Shift+Minus", _hotkeyZoomOutOk }
            };
            return d;
        }

        public void WriteWindowJson(string path)
        {
            if (String.IsNullOrEmpty(path)) return;
            try
            {
                JavaScriptSerializer ser = new JavaScriptSerializer();
                string text = ser.Serialize(GetWindowState());
                string dir = Path.GetDirectoryName(Path.GetFullPath(path));
                if (!String.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                File.WriteAllText(path, text, Encoding.UTF8);
            }
            catch (Exception ex) { Log.Write("写窗口 JSON 失败：" + ex.Message); }
        }

        private void RaiseStateChanged()
        {
            EventHandler handler = StateChanged;
            if (handler != null)
            {
                try { handler(this, EventArgs.Empty); }
                catch (Exception ex) { Log.Write("StateChanged 回调失败：" + ex.Message); }
            }
        }

        private async void OnNavigationCompleted(object sender, CoreWebView2NavigationCompletedEventArgs e)
        {
            if (!_opt.DumpDom) return;
            for (int i = 0; i < 8; i++)
            {
                await Task.Delay(2000);
                await DumpOnce(i);
            }
        }

        private async Task DumpOnce(int round)
        {
            try
            {
                string script =
                    "(function(){var q=function(s){return document.querySelector(s)};" +
                    "var imgs=[];for(var i=0;i<document.images.length;i++){var im=document.images[i];" +
                    "imgs.push([im.getAttribute('src'),im.naturalWidth,im.naturalHeight,Math.round(im.getBoundingClientRect().width)]);}" +
                    "return JSON.stringify({title:document.title,body:document.body.className," +
                    "stage:q('#stage')?q('#stage').outerHTML.length:-1," +
                    "svg:q('#map-svg')?q('#map-svg').childElementCount:-1," +
                    "viewport:q('#viewport')?[Math.round(q('#viewport').getBoundingClientRect().width),Math.round(q('#viewport').getBoundingClientRect().height)]:null," +
                    "bodyBg:getComputedStyle(document.body).backgroundColor,htmlBg:getComputedStyle(document.documentElement).backgroundColor," +
                    "imgs:imgs.slice(0,20),errs:(window.__errs||[]).slice(0,10)," +
                    "error:q('#error')?String(q('#error').textContent).slice(0,240):null," +
                    "mapList:q('#map-list')?q('#map-list').childElementCount:-1," +
                    "full:document.body.getAttribute('data-mini-full')," +
                    "vpOpacity:q('#viewport')?getComputedStyle(q('#viewport')).opacity:null," +
                    "stageRect:q('#stage')?[Math.round(q('#stage').getBoundingClientRect().width),Math.round(q('#stage').getBoundingClientRect().height)]:null," +
                    "status:q('#status-map')?String(q('#status-map').textContent):null});})()";
                string json = await _web.ExecuteScriptAsync(script);
                Log.Write("DOM[" + round + "] " + (json.Length > 1800 ? json.Substring(0, 1800) : json));
            }
            catch (Exception ex) { Log.Write("DOM dump 失败：" + ex.Message); }
        }
    }

}
