// EFT 互动地图 · 桌面壳（WinForms + WebView2）
//
// 主窗口加载本地 HTTP 站点；小地图是同一个进程里的第二个 MiniForm，
// 复用 MiniHost.cs 的无边框 / 置顶 / 点击穿透 / 热键逻辑。
//
// 运行期只访问 127.0.0.1 的本地服务；不加载外部网页、不启用 devtools、
// 不使用 file://、不使用 AddHostObjectToScript。
//
// 编译：Windows 自带 .NET Framework 4.8 的 csc.exe（见 build.ps1）。

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace EftMapMiniHost
{
    internal sealed class ShellOptions
    {
        public string Root;
        public string BackendMode = "auto";      // auto | exe | python | none
        public string PythonExe = "python.exe";
        public int Port;
        public string ConfigDir;
        public string UserDataDir;
        public string RuntimeDir;
        public string LogDir;
        public string LogPath;
        public string Url;                       // attach 模式：直接连已启动的服务
        public string DumpJson;
        public string CaptureDir;
        public string SmokeJson;
        public string FallbackJson;
        public string MiniParams;
        public double Scale;
        public int ExitAfterMs;
        public bool NoTray;
        public bool ShowMiniAtStart;
        public bool SimulateNoRuntime;
        public bool Smoke;
        public bool NoBackend;
        public bool CaptureTray;
        public bool CaptureSettings;

        public ShellOptions()
        {
            string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            ConfigDir = Path.Combine(appData, "EFTMap");
            UserDataDir = Path.Combine(local, "EFTMap", "WebView2");
            RuntimeDir = Path.Combine(local, "EFTMap", "run");
            LogDir = Path.Combine(local, "EFTMap", "logs");
            LogPath = Path.Combine(LogDir, "desktop.log");
            MiniParams = "mini=1&size=260&opacity=0.90&shape=square&labels=1&follow=1&ha=1";
        }

        public static ShellOptions Parse(string[] args)
        {
            ShellOptions o = new ShellOptions();
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                string v = (i + 1 < args.Length) ? args[i + 1] : null;
                if (a == "--root" && v != null) { o.Root = v; i++; }
                else if (a == "--backend-mode" && v != null) { o.BackendMode = v.ToLowerInvariant(); i++; }
                else if (a == "--python" && v != null) { o.PythonExe = v; i++; }
                else if (a == "--port" && v != null) { o.Port = int.Parse(v); i++; }
                else if (a == "--config-dir" && v != null) { o.ConfigDir = v; i++; }
                else if (a == "--user-data" && v != null) { o.UserDataDir = v; i++; }
                else if (a == "--runtime-dir" && v != null) { o.RuntimeDir = v; i++; }
                else if (a == "--log-dir" && v != null) { o.LogDir = v; i++; }
                else if (a == "--log" && v != null) { o.LogPath = v; i++; }
                else if (a == "--url" && v != null) { o.Url = v; o.NoBackend = true; i++; }
                else if (a == "--dump-json" && v != null) { o.DumpJson = v; i++; }
                else if (a == "--capture" && v != null) { o.CaptureDir = v; i++; }
                else if (a == "--smoke-json" && v != null) { o.SmokeJson = v; o.Smoke = true; i++; }
                else if (a == "--fallback-json" && v != null) { o.FallbackJson = v; i++; }
                else if (a == "--mini-params" && v != null) { o.MiniParams = v; i++; }
                else if (a == "--scale" && v != null)
                {
                    o.Scale = double.Parse(v, System.Globalization.CultureInfo.InvariantCulture);
                    i++;
                }
                else if (a == "--exit-after-ms" && v != null) { o.ExitAfterMs = int.Parse(v); i++; }
                else if (a == "--no-tray") { o.NoTray = true; }
                else if (a == "--mini") { o.ShowMiniAtStart = true; }
                else if (a == "--simulate-no-runtime") { o.SimulateNoRuntime = true; }
                else if (a == "--smoke") { o.Smoke = true; }
                else if (a == "--no-backend") { o.NoBackend = true; }
                else if (a == "--capture-tray") { o.CaptureTray = true; }
                else if (a == "--capture-settings") { o.CaptureSettings = true; }
            }
            o.Normalize();
            return o;
        }

        private void Normalize()
        {
            if (String.IsNullOrEmpty(Root)) Root = DetectRoot();
            Root = Path.GetFullPath(Root);
            ConfigDir = Path.GetFullPath(ConfigDir);
            UserDataDir = Path.GetFullPath(UserDataDir);
            RuntimeDir = Path.GetFullPath(RuntimeDir);
            LogDir = Path.GetFullPath(LogDir);
            LogPath = Path.GetFullPath(LogPath);
            if (String.IsNullOrEmpty(DumpJson)) DumpJson = Path.Combine(LogDir, "window-state.json");
            if (Smoke && String.IsNullOrEmpty(SmokeJson)) SmokeJson = Path.Combine(LogDir, "smoke.json");
            if (String.IsNullOrEmpty(FallbackJson)) FallbackJson = Path.Combine(LogDir, "fallback.json");
        }

        private static string DetectRoot()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string repo = Path.GetFullPath(Path.Combine(baseDir, "..", "..", ".."));
            if (File.Exists(Path.Combine(repo, "tools", "launcher.py"))) return repo;
            if (File.Exists(Path.Combine(baseDir, "EFTMap.exe"))) return baseDir;
            return Directory.GetCurrentDirectory();
        }
    }

    internal sealed class ShellConfig
    {
        public int MainLeft;
        public int MainTop;
        public int MainWidth = 1280;
        public int MainHeight = 720;
        public bool Maximized;
        public bool CloseToTray = true;
        public bool TrayEnabled = true;
        public string MiniToggleHotkey = "Ctrl+Shift+M";
        public string MiniFullHotkey = "Ctrl+Shift+F";

        private static string PathFor(string configDir)
        {
            return Path.Combine(configDir, "shell.json");
        }

        public static ShellConfig Load(string configDir)
        {
            ShellConfig cfg = new ShellConfig();
            string path = PathFor(configDir);
            try
            {
                if (!File.Exists(path)) return cfg;
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> root = ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
                if (root == null) return cfg;
                cfg.MainLeft = Int(root, "mainLeft", cfg.MainLeft);
                cfg.MainTop = Int(root, "mainTop", cfg.MainTop);
                cfg.MainWidth = Int(root, "mainWidth", cfg.MainWidth);
                cfg.MainHeight = Int(root, "mainHeight", cfg.MainHeight);
                cfg.Maximized = Bool(root, "maximized", cfg.Maximized);
                cfg.CloseToTray = Bool(root, "closeToTray", cfg.CloseToTray);
                cfg.TrayEnabled = Bool(root, "trayEnabled", cfg.TrayEnabled);
                cfg.MiniToggleHotkey = Text(root, "miniToggleHotkey", cfg.MiniToggleHotkey);
                cfg.MiniFullHotkey = Text(root, "miniFullHotkey", cfg.MiniFullHotkey);
                if (cfg.MainWidth < 800) cfg.MainWidth = 1280;
                if (cfg.MainHeight < 600) cfg.MainHeight = 720;
            }
            catch (Exception ex)
            {
                Log.Write("读 shell.json 失败，用默认窗口：" + ex.Message);
            }
            return cfg;
        }

        public void Save(string configDir)
        {
            try
            {
                Directory.CreateDirectory(configDir);
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["mainLeft"] = MainLeft;
                d["mainTop"] = MainTop;
                d["mainWidth"] = MainWidth;
                d["mainHeight"] = MainHeight;
                d["maximized"] = Maximized;
                d["closeToTray"] = CloseToTray;
                d["trayEnabled"] = TrayEnabled;
                d["miniToggleHotkey"] = MiniToggleHotkey;
                d["miniFullHotkey"] = MiniFullHotkey;
                JavaScriptSerializer ser = new JavaScriptSerializer();
                string text = ser.Serialize(d);
                string path = PathFor(configDir);
                string tmp = path + ".tmp";
                File.WriteAllText(tmp, text, Encoding.UTF8);
                if (File.Exists(path)) File.Delete(path);
                File.Move(tmp, path);
            }
            catch (Exception ex)
            {
                Log.Write("写 shell.json 失败：" + ex.Message);
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

        private static string Text(Dictionary<string, object> d, string key, string fallback)
        {
            if (!d.ContainsKey(key) || d[key] == null) return fallback;
            string value = Convert.ToString(d[key]);
            return String.IsNullOrEmpty(value) ? fallback : value;
        }

        private static int Int(Dictionary<string, object> d, string key, int fallback)
        {
            if (!d.ContainsKey(key)) return fallback;
            try { return Convert.ToInt32(d[key]); }
            catch { return fallback; }
        }
    }

    internal sealed class BackendRuntime
    {
        public string App;
        public string Version;
        public int Pid;
        public int Port;
        public string Url;
        public string Token;
        public string ConfigDir;
        public string LogFile;
        public long StartedAt;

        public static BackendRuntime Read(string path)
        {
            JavaScriptSerializer ser = new JavaScriptSerializer();
            Dictionary<string, object> d = ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
            if (d == null) throw new InvalidDataException("runtime JSON 为空");
            BackendRuntime r = new BackendRuntime();
            r.App = Text(d, "app");
            r.Version = Text(d, "version");
            r.Pid = Int(d, "pid");
            r.Port = Int(d, "port");
            r.Url = Text(d, "url");
            r.Token = Text(d, "token");
            r.ConfigDir = Text(d, "configDir");
            r.LogFile = Text(d, "logFile");
            r.StartedAt = Long(d, "startedAt");
            if (String.IsNullOrEmpty(r.Url)) throw new InvalidDataException("runtime JSON 缺少 url");
            return r;
        }

        private static string Text(Dictionary<string, object> d, string key)
        {
            return d.ContainsKey(key) && d[key] != null ? Convert.ToString(d[key]) : "";
        }

        private static int Int(Dictionary<string, object> d, string key)
        {
            try { return d.ContainsKey(key) ? Convert.ToInt32(d[key]) : 0; }
            catch { return 0; }
        }

        private static long Long(Dictionary<string, object> d, string key)
        {
            try { return d.ContainsKey(key) ? Convert.ToInt64(d[key]) : 0L; }
            catch { return 0L; }
        }
    }

    internal sealed class BackendProcess
    {
        private readonly ShellOptions _opt;
        private Process _process;
        private IntPtr _job;
        private bool _stopped;
        private string _runtimePath;
        private string _backendLog;

        public BackendRuntime Runtime;
        public string RuntimePath { get { return _runtimePath; } }
        public string BackendLog { get { return _backendLog; } }

        public BackendProcess(ShellOptions opt)
        {
            _opt = opt;
            _runtimePath = Path.Combine(opt.RuntimeDir, "desktop-" + Process.GetCurrentProcess().Id + ".json");
            _backendLog = Path.Combine(opt.LogDir, "backend-" + Process.GetCurrentProcess().Id + ".log");
        }

        public void Start()
        {
            Directory.CreateDirectory(_opt.RuntimeDir);
            Directory.CreateDirectory(_opt.LogDir);
            if (_opt.NoBackend || !String.IsNullOrEmpty(_opt.Url))
            {
                Runtime = new BackendRuntime();
                Runtime.Url = _opt.Url;
                Runtime.Pid = 0;
                Runtime.LogFile = "";
                if (String.IsNullOrEmpty(Runtime.Url)) throw new InvalidOperationException("没有 --url，且后端被禁用");
                Log.Write("attach 模式，直接使用 " + Runtime.Url);
                return;
            }

            string mode = _opt.BackendMode;
            if (mode == "none") throw new InvalidOperationException("backend-mode=none 但没有 --url");
            bool useExe = mode == "exe" || (mode == "auto" && File.Exists(Path.Combine(_opt.Root, "EFTMap.exe")));
            string fileName;
            string arguments;
            if (useExe)
            {
                fileName = Path.Combine(_opt.Root, "EFTMap.exe");
                if (!File.Exists(fileName)) throw new FileNotFoundException("找不到打包后端：" + fileName);
                arguments = BuildArgs("");
            }
            else
            {
                fileName = _opt.PythonExe;
                string launcher = Path.Combine(_opt.Root, "tools", "launcher.py");
                if (!File.Exists(launcher)) throw new FileNotFoundException("找不到 tools/launcher.py：" + launcher);
                arguments = "-u " + ShellUtil.Quote(launcher) + " " + BuildArgs("");
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = fileName;
            psi.Arguments = arguments;
            psi.WorkingDirectory = _opt.Root;
            psi.UseShellExecute = false;
            // R75：后端一律隐藏启动。CreateNoWindow 对应 CREATE_NO_WINDOW，
            // 不建控制台、不弹 conhost；stdout/stderr 改接管道并转进 desktop.log，
            // 这样既不会出现 cmd 窗口，也不会丢 PyInstaller 启动阶段的报错。
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.StandardErrorEncoding = Encoding.UTF8;
            Log.Write("启动后端：" + fileName + " " + arguments);
            _process = Process.Start(psi);
            if (_process == null) throw new InvalidOperationException("后端进程没有启动");
            _process.OutputDataReceived += delegate(object s, DataReceivedEventArgs e)
            {
                if (!String.IsNullOrEmpty(e.Data)) Log.Write("[backend:out] " + e.Data);
            };
            _process.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e)
            {
                if (!String.IsNullOrEmpty(e.Data)) Log.Write("[backend:err] " + e.Data);
            };
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
            AttachJob(_process);
            WaitReady();
        }

        private string BuildArgs(string extra)
        {
            return "--server-only --shell-mode --port " + _opt.Port +
                   " --config-dir " + ShellUtil.Quote(_opt.ConfigDir) +
                   " --runtime-file " + ShellUtil.Quote(_runtimePath) +
                   " --log-file " + ShellUtil.Quote(_backendLog) +
                   " --parent-pid " + Process.GetCurrentProcess().Id +
                   (String.IsNullOrEmpty(extra) ? "" : " " + extra);
        }

        private void WaitReady()
        {
            DateTime deadline = DateTime.UtcNow.AddSeconds(30);
            while (DateTime.UtcNow < deadline)
            {
                if (_process.HasExited)
                {
                    throw new InvalidOperationException("后端提前退出，exitcode=" + _process.ExitCode + "\n" + TailLog());
                }
                if (File.Exists(_runtimePath))
                {
                    try
                    {
                        Runtime = BackendRuntime.Read(_runtimePath);
                        if (Health(Runtime.Url))
                        {
                            Log.Write("后端就绪：" + Runtime.Url + " pid=" + Runtime.Pid);
                            return;
                        }
                    }
                    catch (Exception ex)
                    {
                        Log.Write("等待 runtime/health：" + ex.Message);
                    }
                }
                Thread.Sleep(250);
            }
            throw new TimeoutException("30 秒内后端没有就绪\n" + TailLog());
        }

        private static bool Health(string url)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url + "api/health");
                req.Proxy = null;
                req.Timeout = 3000;
                req.ReadWriteTimeout = 3000;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    JavaScriptSerializer ser = new JavaScriptSerializer();
                    Dictionary<string, object> d = ser.DeserializeObject(sr.ReadToEnd()) as Dictionary<string, object>;
                    return d != null && d.ContainsKey("ok") && Convert.ToBoolean(d["ok"]);
                }
            }
            catch
            {
                return false;
            }
        }

        public bool IsHealthy()
        {
            return Runtime != null && !String.IsNullOrEmpty(Runtime.Url) && Health(Runtime.Url);
        }

        /// <summary>R76 自愈：WebView2 崩溃恢复时，若后端已不可用则重启后端（同一个 runtime 文件）。</summary>
        public bool Restart()
        {
            try
            {
                Stop();
                _stopped = false;
                Runtime = null;
                Start();
                return true;
            }
            catch (Exception ex)
            {
                Log.Write("重启后端失败：" + ex.Message);
                return false;
            }
        }

        public void Stop()
        {
            if (_stopped) return;
            _stopped = true;
            if (_process != null && Runtime != null && !String.IsNullOrEmpty(Runtime.Token) && !String.IsNullOrEmpty(Runtime.Url))
            {
                try
                {
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(Runtime.Url + "api/shutdown");
                    req.Method = "POST";
                    req.Proxy = null;
                    req.Timeout = 3000;
                    req.ReadWriteTimeout = 3000;
                    req.ContentLength = 0;
                    req.Headers["X-EFTMap-Token"] = Runtime.Token;
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse()) { }
                    Log.Write("已请求后端 shutdown");
                }
                catch (Exception ex)
                {
                    Log.Write("请求后端 shutdown 失败（继续 Job Object 清理）：" + ex.Message);
                }
            }
            if (_process != null)
            {
                try
                {
                    // 后端 shutdown 后还要停截图/日志/配置监听线程，3 秒不够；
                    // 给 8 秒让它自己写 server-only exit 并删除 runtime，再兜底强杀。
                    if (!_process.WaitForExit(8000))
                    {
                        Log.Write("后端未在 8 秒内退出，强制结束 pid=" + _process.Id);
                        _process.Kill();
                        _process.WaitForExit(1000);
                    }
                }
                catch (Exception ex) { Log.Write("结束后端失败：" + ex.Message); }
                try { _process.Dispose(); } catch { }
                _process = null;
            }
            CloseJob();
            try { if (File.Exists(_runtimePath)) File.Delete(_runtimePath); } catch { }
        }

        public void Dispose()
        {
            Stop();
        }

        private string TailLog()
        {
            try
            {
                if (!File.Exists(_backendLog)) return "（后端日志不存在：" + _backendLog + "）";
                string text = File.ReadAllText(_backendLog, Encoding.UTF8);
                if (text.Length > 3000) text = text.Substring(text.Length - 3000);
                return "--- backend.log ---\n" + text;
            }
            catch (Exception ex) { return "（读后端日志失败：" + ex.Message + "）"; }
        }

        private void AttachJob(Process p)
        {
            try
            {
                _job = NativeJob.CreateJobObject(IntPtr.Zero, null);
                if (_job == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateJobObject");
                NativeJob.JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new NativeJob.JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
                info.BasicLimitInformation.LimitFlags = NativeJob.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                int length = Marshal.SizeOf(typeof(NativeJob.JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
                if (!NativeJob.SetInformationJobObject(_job, NativeJob.JobObjectExtendedLimitInformation, ref info, length))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "SetInformationJobObject");
                }
                if (!NativeJob.AssignProcessToJobObject(_job, p.Handle))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "AssignProcessToJobObject");
                }
                Log.Write("后端已加入 Job Object（壳退出即杀）");
            }
            catch (Exception ex)
            {
                Log.Write("Job Object 绑定失败（仍由 parent-pid 看门狗兜底）：" + ex.Message);
                if (_job != IntPtr.Zero) { try { NativeJob.CloseHandle(_job); } catch { } _job = IntPtr.Zero; }
            }
        }

        private void CloseJob()
        {
            if (_job == IntPtr.Zero) return;
            try { NativeJob.CloseHandle(_job); } catch { }
            _job = IntPtr.Zero;
        }
    }

    internal static class NativeJob
    {
        public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        public const int JobObjectExtendedLimitInformation = 9;

        [StructLayout(LayoutKind.Sequential)]
        public struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct IO_COUNTERS
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        public static extern IntPtr CreateJobObject(IntPtr attributes, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetInformationJobObject(IntPtr job, int infoClass,
            ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION info, int length);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool CloseHandle(IntPtr handle);
    }

    internal static class ShellUtil
    {
        public static void WriteJson(string path, Dictionary<string, object> payload)
        {
            try
            {
                JavaScriptSerializer ser = new JavaScriptSerializer();
                string text = ser.Serialize(payload);
                string dir = Path.GetDirectoryName(Path.GetFullPath(path));
                if (!String.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                File.WriteAllText(path, text, Encoding.UTF8);
            }
            catch (Exception ex) { Log.Write("写 JSON 失败：" + path + "：" + ex.Message); }
        }

        public static string Quote(string text)
        {
            if (String.IsNullOrEmpty(text)) return "\"\"";
            return "\"" + text.Replace("\"", "\\\"") + "\"";
        }

        public static void OpenExternal(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                Log.Write("交给系统打开：" + url);
            }
            catch (Exception ex) { Log.Write("打开外部地址失败：" + url + "：" + ex.Message); }
        }

        public static string OpenAppWindow(string url)
        {
            string[] candidates = new string[] {
                @"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                @"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                @"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                @"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                @"%LocalAppData%\Google\Chrome\Application\chrome.exe"
            };
            foreach (string raw in candidates)
            {
                string exe = Environment.ExpandEnvironmentVariables(raw);
                if (!File.Exists(exe)) continue;
                try
                {
                    Process.Start(new ProcessStartInfo(exe, "--app=" + url) { UseShellExecute = false });
                    Log.Write("回退到浏览器 app 模式：" + exe);
                    return "edge/chrome --app: " + exe;
                }
                catch (Exception ex) { Log.Write("app 模式启动失败：" + ex.Message); }
            }
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                Log.Write("回退到系统默认浏览器：" + url);
                return "default-browser";
            }
            catch (Exception ex)
            {
                Log.Write("系统浏览器也打不开：" + ex.Message);
                return "failed: " + ex.Message;
            }
        }
    }

    internal sealed class FallbackForm : Form
    {
        private readonly ShellOptions _opt;
        private readonly string _reason;
        private readonly string _url;
        private readonly System.Threading.Timer _exitTimer;

        public FallbackForm(ShellOptions opt, string reason, string url)
        {
            _opt = opt;
            _reason = reason;
            _url = url;
            Text = "EFT 互动地图 · 兼容模式";
            Width = 620;
            Height = 320;
            StartPosition = FormStartPosition.Manual;
            Rectangle work = Screen.PrimaryScreen.WorkingArea;
            Left = work.Left + (work.Width - Width) / 2;
            Top = work.Top + (work.Height - Height) / 2;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            TopMost = true;   // 提示窗口置前，用户能先看清缺失原因
            BackColor = Color.FromArgb(14, 16, 19);

            Label title = new Label();
            title.Text = "独立窗口不可用（未自动打开浏览器）";
            title.ForeColor = Color.White;
            title.Font = new Font("Microsoft YaHei UI", 12F, FontStyle.Bold);
            title.Left = 24;
            title.Top = 22;
            title.Width = 560;
            title.Height = 32;
            Controls.Add(title);

            Label body = new Label();
            body.Text = _reason + "\r\n\r\n" +
                        "不会自动打开浏览器：需要时可点击下方「用浏览器打开」自行选择。\r\n" +
                        "安装 WebView2 Runtime（https://go.microsoft.com/fwlink/p/?LinkId=2124703）" +
                        "后重启 EFTMapDesktop.exe 可获得完整客户端体验。\r\n\r\n" +
                        "服务地址：" + (_url ?? "（后端未就绪）") + "\r\n" +
                        "客户端日志：" + _opt.LogPath;
            body.ForeColor = Color.FromArgb(220, 220, 225);
            body.Left = 24;
            body.Top = 66;
            body.Width = 570;
            body.Height = 170;
            Controls.Add(body);

            Button open = new Button();
            open.Text = "用浏览器打开";
            open.Left = 360;
            open.Top = 248;
            open.Width = 110;
            open.Height = 28;
            open.Click += delegate { if (!String.IsNullOrEmpty(_url)) ShellUtil.OpenAppWindow(_url); };
            Controls.Add(open);

            Button close = new Button();
            close.Text = "退出";
            close.Left = 484;
            close.Top = 248;
            close.Width = 110;
            close.Height = 28;
            close.Click += delegate { Close(); };
            Controls.Add(close);

            Shown += delegate
            {
                // R71：不再在 Shown 里静默拉起浏览器。只有用户点「用浏览器打开」才开。
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["mode"] = "fallback";
                d["reason"] = _reason;
                d["url"] = _url;
                d["browser"] = "pending-user";
                d["log"] = _opt.LogPath;
                d["timestamp"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
                ShellUtil.WriteJson(_opt.FallbackJson, d);
                Log.Write("fallback（等待用户选择）：" + _reason + " url=" + _url);
                if (!String.IsNullOrEmpty(_opt.CaptureDir))
                {
                    // Shown 触发时窗口还没完成第一次绘制，延后 1 秒再截，否则会抓到白块。
                    Task.Delay(1200).ContinueWith(delegate
                    {
                        try { BeginInvoke(new Action(CaptureFallback)); }
                        catch { }
                    });
                }
            };

            if (_opt.ExitAfterMs > 0)
            {
                _exitTimer = new System.Threading.Timer(delegate
                {
                    try { BeginInvoke(new Action(delegate { Log.Write("fallback 定时退出"); Close(); })); }
                    catch { }
                }, null, _opt.ExitAfterMs, System.Threading.Timeout.Infinite);
            }
        }

        private void CaptureFallback()
        {
            try
            {
                Directory.CreateDirectory(_opt.CaptureDir);
                Native.RECT r = new Native.RECT();
                Native.GetWindowRect(Handle, out r);
                int w = r.Right - r.Left;
                int h = r.Bottom - r.Top;
                if (w <= 0 || h <= 0) return;
                using (Bitmap bmp = new Bitmap(w, h))
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.CopyFromScreen(r.Left, r.Top, 0, 0, new Size(w, h));
                    bmp.Save(Path.Combine(_opt.CaptureDir, "fallback.png"), ImageFormat.Png);
                }
                Log.Write("fallback 截图已写入");
            }
            catch (Exception ex) { Log.Write("fallback 截图失败：" + ex.Message); }
        }
    }

    internal sealed class SettingsForm : Form
    {
        private readonly ShellOptions _opt;
        private readonly ShellConfig _shell;
        private readonly string _path;
        private readonly Dictionary<string, object> _root;
        private TextBox _gameDir;
        private TextBox _shotsDir;
        private CheckBox _autoZoom;
        private CheckBox _autoCenter;
        private CheckBox _overlayEnabled;
        private TextBox _overlaySize;
        private TextBox _overlayOpacity;
        private ComboBox _overlayCorner;
        private CheckBox _overlayClickThrough;
        private ComboBox _overlaySizeMode;
        private TextBox _overlayScale;
        private ComboBox _overlayShape;
        private CheckBox _overlayExcludeCapture;
        private CheckBox _soundEnabled;
        private CheckBox _shotEnabled;
        private TextBox _shotInterval;
        private TextBox _shotKey;
        private CheckBox _shotDelete;
        private CheckBox _closeToTray;
        private TextBox _toggleHotkey;
        private TextBox _fullHotkey;

        public SettingsForm(ShellOptions opt, ShellConfig shellCfg)
        {
            _opt = opt;
            _shell = shellCfg;
            _path = Path.Combine(opt.ConfigDir, "eftmap.config.json");
            _root = LoadConfig(_path);

            Text = "EFT 互动地图 · 设置";
            Width = 820;
            Height = 880;
            StartPosition = FormStartPosition.CenterParent;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            BackColor = Color.FromArgb(28, 28, 34);
            ForeColor = Color.FromArgb(230, 230, 235);
            Font = new Font("Microsoft YaHei UI", 9F);
            AutoScaleMode = AutoScaleMode.Dpi;

            GroupBox dirs = Group("目录", 16, 12, 788, 112);
            _gameDir = AddText(dirs, "游戏目录（含 Logs）", 12, 24, 660);
            AddBrowse(dirs, 686, 42, delegate { _gameDir.Text = PickFolder(_gameDir.Text); });
            _shotsDir = AddText(dirs, "截图目录（实时定位）", 12, 58, 660);
            AddBrowse(dirs, 686, 76, delegate { _shotsDir.Text = PickFolder(_shotsDir.Text); });

            GroupBox map = Group("地图显示", 16, 132, 788, 72);
            _autoZoom = AddCheck(map, "定位自动缩放（沿用最近一次手动缩放）", 12, 22, 340, false);
            _autoCenter = AddCheck(map, "点位自动居中（跟随实时位置平移地图）", 12, 46, 360, false);

            GroupBox overlay = Group("游戏内小地图", 16, 212, 788, 238);
            _overlayEnabled = AddCheck(overlay, "启用小地图", 12, 22, 150, false);
            _overlayClickThrough = AddCheck(overlay, "默认点击穿透", 210, 22, 180, false);
            _overlayExcludeCapture = AddCheck(overlay, "截图/录屏中隐藏小地图（WDA_EXCLUDEFROMCAPTURE）", 430, 22, 340, false);
            _overlaySizeMode = AddCombo(overlay, "尺寸模式", 12, 52, 110, new string[] { "auto", "fixed" });
            _overlaySize = AddText(overlay, "固定尺寸 px（仅 fixed）", 150, 52, 110);
            _overlayScale = AddText(overlay, "缩放 0.5-3", 290, 52, 90);
            _overlayOpacity = AddText(overlay, "透明度 0.3-1", 410, 52, 90);
            _overlayCorner = AddCombo(overlay, "吸附角", 530, 52, 120);
            _overlayShape = AddCombo(overlay, "形状", 680, 52, 90, new string[] { "square", "circle" });

            Label overlayNote = new Label();
            overlayNote.Text = "尺寸基准 auto = min(工作区宽, 工作区高) × 20% × 缩放，换分辨率后自动重算；" +
                               "circle 用 SetWindowRgn 做圆形裁剪（只作用于小地图顶层窗）。\r\n" +
                               "「截图/录屏中隐藏」默认关闭：开启后本窗口不会出现在截图、录屏或直播画面里（Windows 10 2004+）。";
            overlayNote.ForeColor = Color.FromArgb(160, 160, 170);
            overlayNote.Left = 12;
            overlayNote.Top = 150;
            overlayNote.Width = 760;
            overlayNote.Height = 56;
            overlay.Controls.Add(overlayNote);

            GroupBox shot = Group("自动截图", 16, 460, 788, 150);
            _soundEnabled = AddCheck(shot, "启用声音提示", 12, 22, 150, false);
            _shotEnabled = AddCheck(shot, "启用自动截图", 12, 48, 150, false);
            _shotInterval = AddText(shot, "间隔 ms", 12, 78, 100);
            _shotKey = AddText(shot, "截图键", 210, 78, 100);
            _shotDelete = AddCheck(shot, "读取位置后删除旧截图", 400, 98, 220, false);

            GroupBox shellGroup = Group("壳与热键（修改后重启客户端生效）", 16, 622, 788, 132);
            _closeToTray = AddCheck(shellGroup, "关闭主窗收进托盘", 12, 22, 180, false);
            _toggleHotkey = AddText(shellGroup, "小地图显隐", 12, 52, 150);
            _fullHotkey = AddText(shellGroup, "小地图全图", 210, 52, 150);

            Button save = new Button();
            save.Text = "保存";
            save.Left = 580;
            save.Top = 776;
            save.Width = 96;
            save.Height = 30;
            save.Click += delegate { SaveAndClose(); };
            Controls.Add(save);

            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Left = 686;
            cancel.Top = 776;
            cancel.Width = 96;
            cancel.Height = 30;
            cancel.Click += delegate { Close(); };
            Controls.Add(cancel);

            Label note = new Label();
            note.Text = "说明：目录 / 自动截图 / 日志监控改动需要重启客户端；小地图尺寸、缩放、形状、透明度、热键均在保存后立即或重启后生效。";
            note.ForeColor = Color.FromArgb(160, 160, 170);
            note.Left = 16;
            note.Top = 818;
            note.Width = 788;
            note.Height = 36;
            Controls.Add(note);

            LoadValues();
        }

        private GroupBox Group(string text, int x, int y, int w, int h)
        {
            GroupBox g = new GroupBox();
            g.Text = " " + text + " ";
            g.Left = x;
            g.Top = y;
            g.Width = w;
            g.Height = h;
            g.ForeColor = Color.FromArgb(200, 200, 210);
            Controls.Add(g);
            return g;
        }

        private Label AddLabel(Control parent, string text, int x, int y, int w)
        {
            Label l = new Label();
            l.Text = text;
            l.Left = x;
            l.Top = y;
            l.Width = w;
            l.Height = 20;
            l.ForeColor = Color.FromArgb(220, 220, 228);
            parent.Controls.Add(l);
            return l;
        }

        private TextBox AddText(Control parent, string label, int x, int y, int width)
        {
            AddLabel(parent, label, x, y, width);
            TextBox t = new TextBox();
            t.Left = x;
            t.Top = y + 20;
            t.Width = width;
            t.BackColor = Color.FromArgb(40, 40, 46);
            t.ForeColor = Color.FromArgb(235, 235, 240);
            t.BorderStyle = BorderStyle.FixedSingle;
            parent.Controls.Add(t);
            return t;
        }

        private CheckBox AddCheck(Control parent, string text, int x, int y, int width, bool small)
        {
            CheckBox c = new CheckBox();
            c.Text = text;
            c.Left = x;
            c.Top = y;
            c.Width = width;
            c.Height = 22;
            c.ForeColor = Color.FromArgb(230, 230, 236);
            parent.Controls.Add(c);
            return c;
        }

        private ComboBox AddCombo(Control parent, string label, int x, int y, int width)
        {
            return AddCombo(parent, label, x, y, width,
                new string[] { "top-left", "top-right", "bottom-left", "bottom-right" });
        }

        private ComboBox AddCombo(Control parent, string label, int x, int y, int width, string[] items)
        {
            AddLabel(parent, label, x, y, width);
            ComboBox c = new ComboBox();
            c.Left = x;
            c.Top = y + 20;
            c.Width = width;
            c.DropDownStyle = ComboBoxStyle.DropDownList;
            c.Items.AddRange(items);
            c.BackColor = Color.FromArgb(40, 40, 46);
            c.ForeColor = Color.FromArgb(235, 235, 240);
            parent.Controls.Add(c);
            return c;
        }

        private void AddBrowse(Control parent, int x, int y, EventHandler click)
        {
            Button b = new Button();
            b.Text = "浏览…";
            b.Left = x;
            b.Top = y;
            b.Width = 90;
            b.Height = 24;
            b.Click += click;
            parent.Controls.Add(b);
        }

        private string PickFolder(string current)
        {
            using (FolderBrowserDialog dlg = new FolderBrowserDialog())
            {
                dlg.Description = "选择目录";
                if (!String.IsNullOrEmpty(current) && Directory.Exists(current)) dlg.SelectedPath = current;
                return dlg.ShowDialog(this) == DialogResult.OK ? dlg.SelectedPath : current;
            }
        }

        private void LoadValues()
        {
            _gameDir.Text = Str(_root, "game_dir");
            _shotsDir.Text = Str(_root, "screenshots_dir");
            _autoZoom.Checked = Bool(_root, "auto_zoom", false);
            _autoCenter.Checked = Bool(_root, "auto_center", true);

            Dictionary<string, object> overlay = Dict(_root, "overlay");
            _overlayEnabled.Checked = Bool(overlay, "enabled", false);
            _overlaySizeMode.SelectedItem = Str(overlay, "size_mode", "auto");
            _overlaySize.Text = Convert.ToString(Int(overlay, "size", 260));
            _overlayScale.Text = Convert.ToString(Double(overlay, "scale", 1.0));
            _overlayOpacity.Text = Convert.ToString(Double(overlay, "opacity", 0.9));
            _overlayCorner.SelectedItem = Str(overlay, "corner", "bottom-right");
            _overlayShape.SelectedItem = Str(overlay, "shape", "square");
            _overlayClickThrough.Checked = Bool(overlay, "click_through", true);
            _overlayExcludeCapture.Checked = Bool(overlay, "exclude_from_capture", false);

            Dictionary<string, object> sound = Dict(_root, "sound");
            _soundEnabled.Checked = Bool(sound, "enabled", false);
            Dictionary<string, object> shot = Dict(_root, "auto_screenshot");
            _shotEnabled.Checked = Bool(shot, "enabled", false);
            _shotInterval.Text = Convert.ToString(Int(shot, "interval_ms", 5000));
            _shotKey.Text = Str(shot, "key");
            _shotDelete.Checked = Bool(Dict(_root, "auto_delete"), "enabled", false);

            _closeToTray.Checked = _shell.CloseToTray;
            _toggleHotkey.Text = _shell.MiniToggleHotkey;
            _fullHotkey.Text = _shell.MiniFullHotkey;
        }

        private void SaveAndClose()
        {
            try
            {
                _root["game_dir"] = NullIfEmpty(_gameDir.Text);
                _root["screenshots_dir"] = NullIfEmpty(_shotsDir.Text);
                _root["auto_zoom"] = _autoZoom.Checked;
                _root["auto_center"] = _autoCenter.Checked;

                Dictionary<string, object> overlay = Dict(_root, "overlay");
                overlay["enabled"] = _overlayEnabled.Checked;
                overlay["size_mode"] = _overlaySizeMode.SelectedItem != null ? Convert.ToString(_overlaySizeMode.SelectedItem) : "auto";
                overlay["size"] = ClampInt(_overlaySize.Text, 260, 120, 1200);
                overlay["scale"] = ClampDouble(_overlayScale.Text, 1.0, 0.5, 3.0);
                overlay["opacity"] = ClampDouble(_overlayOpacity.Text, 0.9, 0.3, 1.0);
                overlay["corner"] = _overlayCorner.SelectedItem != null ? Convert.ToString(_overlayCorner.SelectedItem) : "bottom-right";
                overlay["shape"] = _overlayShape.SelectedItem != null ? Convert.ToString(_overlayShape.SelectedItem) : "square";
                overlay["click_through"] = _overlayClickThrough.Checked;
                overlay["exclude_from_capture"] = _overlayExcludeCapture.Checked;
                _root["overlay"] = overlay;

                Dictionary<string, object> sound = Dict(_root, "sound");
                sound["enabled"] = _soundEnabled.Checked;
                _root["sound"] = sound;

                Dictionary<string, object> shot = Dict(_root, "auto_screenshot");
                shot["enabled"] = _shotEnabled.Checked;
                shot["interval_ms"] = ClampInt(_shotInterval.Text, 5000, 200, 60000);
                shot["key"] = NullIfEmpty(_shotKey.Text);
                _root["auto_screenshot"] = shot;

                Dictionary<string, object> del = Dict(_root, "auto_delete");
                bool wasDelete = Bool(del, "enabled", false);
                del["enabled"] = _shotDelete.Checked;
                if (_shotDelete.Checked && !wasDelete) del["since"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                if (!_shotDelete.Checked) del["since"] = null;
                _root["auto_delete"] = del;

                _shell.CloseToTray = _closeToTray.Checked;
                if (HotkeySpec.Parse(_toggleHotkey.Text) != null) _shell.MiniToggleHotkey = _toggleHotkey.Text;
                if (HotkeySpec.Parse(_fullHotkey.Text) != null) _shell.MiniFullHotkey = _fullHotkey.Text;
                _shell.Save(_opt.ConfigDir);

                JavaScriptSerializer ser = new JavaScriptSerializer();
                string text = ser.Serialize(_root);
                Directory.CreateDirectory(_opt.ConfigDir);
                string tmp = _path + ".tmp";
                File.WriteAllText(tmp, text, Encoding.UTF8);
                if (File.Exists(_path)) File.Delete(_path);
                File.Move(tmp, _path);
                Log.Write("设置已保存：" + _path);
                MessageBox.Show(this, "设置已保存。\n目录/自动截图/日志监控与小地图热键改动在重启客户端后完全生效。",
                    "EFT 互动地图", MessageBoxButtons.OK, MessageBoxIcon.Information);
                Close();
            }
            catch (Exception ex)
            {
                Log.Write("保存设置失败：" + ex.Message);
                MessageBox.Show(this, "保存失败：" + ex.Message, "EFT 互动地图", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static Dictionary<string, object> LoadConfig(string path)
        {
            try
            {
                if (!File.Exists(path)) return new Dictionary<string, object>();
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> d = ser.DeserializeObject(File.ReadAllText(path, Encoding.UTF8)) as Dictionary<string, object>;
                return d ?? new Dictionary<string, object>();
            }
            catch { return new Dictionary<string, object>(); }
        }

        private static Dictionary<string, object> Dict(Dictionary<string, object> root, string key)
        {
            if (root.ContainsKey(key) && root[key] is Dictionary<string, object>) return (Dictionary<string, object>)root[key];
            return new Dictionary<string, object>();
        }

        private static string Str(Dictionary<string, object> d, string key)
        {
            return d.ContainsKey(key) && d[key] != null ? Convert.ToString(d[key]) : "";
        }

        private static bool Bool(Dictionary<string, object> d, string key, bool fallback)
        {
            if (!d.ContainsKey(key)) return fallback;
            object v = d[key];
            if (v is bool) return (bool)v;
            if (v is string) return ((string)v).ToLowerInvariant() == "true";
            return fallback;
        }

        private static int Int(Dictionary<string, object> d, string key, int fallback)
        {
            try { return d.ContainsKey(key) ? Convert.ToInt32(d[key]) : fallback; }
            catch { return fallback; }
        }

        private static double Double(Dictionary<string, object> d, string key, double fallback)
        {
            try { return d.ContainsKey(key) ? Convert.ToDouble(d[key]) : fallback; }
            catch { return fallback; }
        }

        private static string Str(Dictionary<string, object> d, string key, string fallback)
        {
            string s = Str(d, key);
            return String.IsNullOrEmpty(s) ? fallback : s;
        }

        private static string NullIfEmpty(string value)
        {
            value = (value ?? "").Trim();
            return value.Length == 0 ? null : value;
        }

        private static int ClampInt(string text, int fallback, int min, int max)
        {
            int n;
            if (!int.TryParse(text, out n)) n = fallback;
            return Math.Max(min, Math.Min(max, n));
        }

        private static double ClampDouble(string text, double fallback, double min, double max)
        {
            double n;
            if (!double.TryParse(text, out n)) n = fallback;
            return Math.Max(min, Math.Min(max, n));
        }
    }

    internal sealed class DesktopShellForm : Form
    {
        private readonly ShellOptions _opt;
        private readonly BackendProcess _backend;
        private readonly string _webviewVersion;
        private readonly EventWaitHandle _activation;

        private const int StatusHeight = 24;
        private const int ResizeBorder = 6;
        // R282：应用图标从 exe 资源里取（csc /win32icon + /resource，见 tools/host/build.ps1）
        private static Icon _appIcon;
        // R282：页面标题拖动（WebView2 子窗持有鼠标捕获，不能走 Native.BeginDrag）
        private bool _dragging;
        private Point _dragCursor;
        private Point _dragWindow;
        private System.Windows.Forms.Timer _dragTimer;

        private readonly ShellConfig _cfg;
        private readonly Label _status;
        private ContextMenuStrip _trayMenu;
        private CoreWebView2Environment _env;
        private CoreWebView2Controller _mainController;
        private CoreWebView2 _mainWeb;
        private MiniForm _mini;
        private NotifyIcon _tray;
        private System.Threading.Timer _exitTimer;
        private bool _exitRequested;
        private bool _mainReady;
        private bool _trayNoticeShown;
        private bool _pendingMaximize;
        private int _captureCounter;
        private Dictionary<string, object> _smokeResults;
        private bool _smokeDownloadHit;
        private bool _smokeNewWindowHit;
        private bool _smokeFileDialogHit;
        private string _smokeNewWindowUri;
        private string _smokeDownloadPath;
        private string _smokeFileDialogTitle;
        private string _pageState;
        private bool _recoveringMain;
        private CoreWebView2EnvironmentOptions _envOptions;
        private int _mainRecoverCount;
        private System.Windows.Forms.Timer _healthTimer;

        public DesktopShellForm(ShellOptions opt, BackendProcess backend, string webviewVersion,
                                EventWaitHandle activation)
        {
            _opt = opt;
            _backend = backend;
            _webviewVersion = webviewVersion;
            _activation = activation;
            Thread watcher = new Thread(delegate()
            {
                while (true)
                {
                    try
                    {
                        if (_activation.WaitOne(1000))
                        {
                            Log.Write("收到第二实例激活信号");
                            BeginInvoke(new Action(ShowMain));
                        }
                    }
                    catch { }
                }
            });
            watcher.IsBackground = true;
            watcher.Start();
            _cfg = ShellConfig.Load(opt.ConfigDir);
            if (opt.NoTray) _cfg.TrayEnabled = false;

            Text = "EFT 互动地图";
            FormBorderStyle = FormBorderStyle.None;
            // R76：对齐 kaedeori 主窗语义，主窗保留一个任务栏按钮；小地图仍 skipTaskbar。
            ShowInTaskbar = true;
            StartPosition = FormStartPosition.Manual;
            MinimumSize = new Size(1024, 640);
            AutoScaleMode = AutoScaleMode.Dpi;
            // 与页面 --bg (#0e1013) 一致：WebView2 首帧/圆角外露时不再看到近黑色底。
            BackColor = Color.FromArgb(14, 16, 19);
            Icon = AppIcon();

            ApplySavedBounds();

            // R282：彻底无边框。原来的 40px 自绘标题栏已删除，窗口控制改为页面内的
            // #win-controls（注入脚本见 FramelessChromeScript），页面从 y=0 铺满整窗；
            // 拖动走页面标题（#app-brand）→ WebMessage "shell:drag" → Native.BeginDrag。
            _status = new Label();
            _status.Dock = DockStyle.None;
            _status.Left = 0;
            _status.Top = 0;
            _status.Height = StatusHeight;
            _status.Text = "正在初始化 WebView2 与本地服务…";
            _status.TextAlign = ContentAlignment.MiddleLeft;
            _status.Padding = new Padding(4, 0, 0, 0);
            _status.BackColor = Color.FromArgb(28, 28, 32);
            _status.ForeColor = Color.FromArgb(230, 230, 235);
            _status.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            Controls.Add(_status);

            LayoutChrome();
            Resize += delegate { LayoutChrome(); ApplyWebViewBounds(); };
            FormClosing += OnFormClosing;
            FormClosed += OnFormClosed;
            Shown += delegate { BeginInitialize(); };
            if (_opt.ExitAfterMs > 0)
            {
                // 用线程定时器而不是 WinForms Timer：即使消息循环正忙（WebView2 加载大 SVG）
                // 也能按时触发退出，便于自动化验收壳的退出清理。
                _exitTimer = new System.Threading.Timer(delegate
                {
                    try { BeginInvoke(new Action(RequestExit)); }
                    catch { }
                }, null, _opt.ExitAfterMs, System.Threading.Timeout.Infinite);
            }
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                // FormBorderStyle=None 会去掉所有系统边框；补 WS_THICKFRAME 让 DWM 仍给阴影/圆角，
                // 同时保留我们自己的 WM_NCHITTEST 缩放命中。
                cp.Style |= Native.WS_THICKFRAME;
                cp.Style &= ~(Native.WS_CAPTION | Native.WS_SYSMENU |
                              Native.WS_MINIMIZEBOX | Native.WS_MAXIMIZEBOX |
                              Native.WS_BORDER | Native.WS_DLGFRAME);
                // R76：主窗要一个任务栏按钮（与 kaedeori 一致），显式去掉 TOOLWINDOW / 加 APPWINDOW。
                cp.ExStyle &= ~0x00000080;
                cp.ExStyle |= 0x00040000;
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            ApplyDwm();
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            ApplyMaximizedBounds();
            if (_pendingMaximize) WindowState = FormWindowState.Maximized;
        }

        /// <summary>
        /// 让最大化后的客户区正好等于工作区：MaximizedBounds 按工作区外扩一圈边框宽度。
        /// 直接把最大化矩形钉成 WorkingArea 会让 7px 透明缩放边框落在可见区域，
        /// 四周露出桌面底色（深色壁纸下就是用户看到的黑边）。
        /// </summary>
        private void ApplyMaximizedBounds()
        {
            Rectangle work = Screen.FromControl(this).WorkingArea;
            int padX = (Width - ClientSize.Width) / 2;
            int padY = (Height - ClientSize.Height) / 2;
            if (padX <= 0) padX = 7;
            if (padY <= 0) padY = 7;
            MaximizedBounds = new Rectangle(work.Left - padX, work.Top - padY,
                                            work.Width + padX * 2, work.Height + padY * 2);
        }

        private void ApplyDwm()
        {
            try
            {
                int enabled = Native.DWMNCRP_ENABLED;
                Native.DwmSetWindowAttribute(Handle, Native.DWMWA_NCRENDERING_POLICY, ref enabled, 4);
                int round = Native.DWMWCP_ROUND;
                Native.DwmSetWindowAttribute(Handle, Native.DWMWA_WINDOW_CORNER_PREFERENCE, ref round, 4);
                // R86：原先硬编码 0x00202020 的深色 DWM 边框，在 Win11 上就是「一圈黑边」的
                // 另一半来源。显式关闭 DWM 边框着色，圆角/阴影仍由系统绘制。
                int border = unchecked((int)Native.DWMWA_COLOR_NONE);
                Native.DwmSetWindowAttribute(Handle, Native.DWMWA_BORDER_COLOR, ref border, 4);
            }
            catch { }
        }

        private void LayoutChrome()
        {
            if (_status == null) return;
            _status.Left = 0;
            _status.Top = 0;
            _status.Width = Math.Max(1, ClientSize.Width);
            ApplyWebViewBounds();
        }

        private void ToggleMaximize()
        {
            if (WindowState == FormWindowState.Maximized)
            {
                WindowState = FormWindowState.Normal;
            }
            else
            {
                // R86：按工作区 + 边框宽度外扩再最大化，避免透明缩放边框露出一圈桌面底色。
                ApplyMaximizedBounds();
                WindowState = FormWindowState.Maximized;
            }
            LayoutChrome();
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_NCHITTEST)
            {
                long lp = m.LParam.ToInt64();
                Point p = PointToClient(new Point((int)(lp & 0xFFFF), (int)((lp >> 16) & 0xFFFF)));
                int b = ResizeBorder;
                bool left = p.X < b;
                bool right = p.X >= ClientSize.Width - b;
                bool top = p.Y < b;
                bool bottom = p.Y >= ClientSize.Height - b;
                if (WindowState != FormWindowState.Maximized)
                {
                    if (left && top) { m.Result = new IntPtr(Native.HTTOPLEFT); return; }
                    if (right && top) { m.Result = new IntPtr(Native.HTTOPRIGHT); return; }
                    if (left && bottom) { m.Result = new IntPtr(Native.HTBOTTOMLEFT); return; }
                    if (right && bottom) { m.Result = new IntPtr(Native.HTBOTTOMRIGHT); return; }
                    if (left) { m.Result = new IntPtr(Native.HTLEFT); return; }
                    if (right) { m.Result = new IntPtr(Native.HTRIGHT); return; }
                    if (top) { m.Result = new IntPtr(Native.HTTOP); return; }
                    if (bottom) { m.Result = new IntPtr(Native.HTBOTTOM); return; }
                }
                // R282：标题栏已删除，顶部不再返回 HTCAPTION —— 页面从 y=0 铺满，
                // 拖动由页面标题的 mousedown 经 WebMessage 触发 Native.BeginDrag。
            }
            base.WndProc(ref m);
        }

        private void ApplySavedBounds()
        {
            Rectangle work = Screen.PrimaryScreen.WorkingArea;
            int w = _cfg.MainWidth;
            int h = _cfg.MainHeight;
            int x = _cfg.MainLeft;
            int y = _cfg.MainTop;
            Rectangle wanted = new Rectangle(x, y, w, h);
            bool intersects = false;
            foreach (Screen s in Screen.AllScreens)
            {
                if (s.WorkingArea.IntersectsWith(wanted)) { intersects = true; break; }
            }
            if (!intersects)
            {
                x = work.Left + (work.Width - w) / 2;
                y = work.Top + (work.Height - h) / 2;
            }
            Bounds = new Rectangle(x, y, w, h);
            // R86：最大化推迟到 OnLoad（Handle 已创建，能量出真实边框宽度），
            // 先按工作区 + 边框宽度外扩再最大化，客户区才能正好铺满工作区。
            _pendingMaximize = _cfg.Maximized;
        }

        private async void BeginInitialize()
        {
            try
            {
                Directory.CreateDirectory(_opt.UserDataDir);
                _envOptions = new CoreWebView2EnvironmentOptions(
                    "--disable-background-networking --disable-component-update --disable-domain-reliability " +
                    "--disable-client-side-phishing-detection --disable-sync --disable-breakpad " +
                    "--autoplay-policy=no-user-gesture-required --disable-background-timer-throttling",
                    null, null, false, null);
                _env = await CoreWebView2Environment.CreateAsync(null, _opt.UserDataDir, _envOptions);
                Log.Write("WebView2 环境就绪：" + _webviewVersion + " UDF=" + _opt.UserDataDir);

                await CreateMainWeb(_env);
                _mainWeb.Navigate(_backend.Runtime.Url);
                Log.Write("主窗口导航：" + _backend.Runtime.Url);

                CreateMiniWindow();
            }
            catch (Exception ex)
            {
                Log.Write("WebView2 初始化失败：" + ex);
                _status.Text = "WebView2 初始化失败：" + ex.Message + "（可用托盘/菜单回退到浏览器）";
                _status.ForeColor = Color.FromArgb(255, 180, 120);
                CreateTray();
            }
        }

        private async Task CreateMainWeb(CoreWebView2Environment env)
        {
            _mainController = await env.CreateCoreWebView2ControllerAsync(Handle);
            _mainController.IsVisible = true;
            _mainController.DefaultBackgroundColor = Color.FromArgb(14, 16, 19);
            _mainWeb = _mainController.CoreWebView2;
            ConfigureMainWebView();
            ApplyWebViewBounds();
            // R282：注入「无边框窗口控制」放在这里而不是导航前一处——
            // WebView2 崩溃后的 BeginRecover 也会走 CreateMainWeb，恢复后按钮不能丢。
            try { await _mainWeb.AddScriptToExecuteOnDocumentCreatedAsync(FramelessChromeScript); }
            catch (Exception ex) { Log.Write("注入无边框控制失败：" + ex.Message); }
        }

        /// <summary>
        /// ProcessFailed 在 BrowserProcessExited 这类场景偶尔不投递（主窗实测漏过），
        /// 这里用 2 秒一次的轻量健康检查兜底：控制器一旦 COM 失效立即走恢复流程。
        /// </summary>
        private void StartHealthWatch()
        {
            if (_healthTimer != null) return;
            _healthTimer = new System.Windows.Forms.Timer();
            _healthTimer.Interval = 2000;
            _healthTimer.Tick += OnHealthTick;
            _healthTimer.Start();
        }

        private void OnHealthTick(object sender, EventArgs e)
        {
            if (_recoveringMain || IsDisposed) return;
            if (_mainController == null)
            {
                if (_mainReady)
                {
                    Log.Write("健康检查：控制器为空但页面标记为就绪，开始恢复");
                    BeginRecover("Watchdog");
                }
                return;
            }
            try
            {
                Rectangle bounds = _mainController.Bounds;   // 控制器已释放时这里抛 COMException
                _mainController.IsVisible = true;
                GC.KeepAlive(bounds);
            }
            catch (Exception ex)
            {
                Log.Write("健康检查发现主窗控制器失效：" + ex.Message);
                BeginRecover("Watchdog");
            }
        }

        private void ConfigureMainWebView()
        {
            _mainWeb.Settings.AreDefaultContextMenusEnabled = true;   // 页面右键卸装依赖它，必须保留
            _mainWeb.Settings.AreDevToolsEnabled = false;
            _mainWeb.Settings.IsStatusBarEnabled = false;
            _mainWeb.Settings.IsZoomControlEnabled = false;
            _mainWeb.Settings.AreBrowserAcceleratorKeysEnabled = true;

            _mainWeb.NavigationStarting += OnNavigationStarting;
            _mainWeb.NavigationCompleted += OnNavigationCompleted;
            _mainWeb.NewWindowRequested += OnNewWindowRequested;
            _mainWeb.DownloadStarting += OnDownloadStarting;
            _mainWeb.PermissionRequested += OnPermissionRequested;
            _mainWeb.ContainsFullScreenElementChanged += OnFullScreenChanged;
            _mainWeb.ProcessFailed += OnProcessFailed;
            StartHealthWatch();
            _mainWeb.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
            _mainWeb.WebResourceRequested += OnWebResourceRequested;
            _mainWeb.WebResourceResponseReceived += OnWebResourceResponseReceived;
            // R282：页面里的窗口按钮 / 拖动条通过 WebMessage 调壳（字符串协议 shell:*）
            try { _mainWeb.Settings.IsWebMessageEnabled = true; } catch { }
            _mainWeb.WebMessageReceived += OnMainWebMessage;
        }

        /// <summary>
        /// R282：无边框主窗的页面内窗口控制。注入在 document 创建时执行，
        /// DOMContentLoaded 后再装 DOM（保证 body / #app-menubar-right 已存在）。
        /// 只在主页面生效：?mini=1 的小地图窗口不注入（它有自己的齿轮菜单与无边框窗口）。
        /// </summary>
        private const string FramelessChromeScript = @"
(function () {
  function post(m) {
    try { if (window.chrome && window.chrome.webview) { window.chrome.webview.postMessage(m); } } catch (e) { }
  }
  function isMini() {
    try { return /(?:^|[?&])mini=(?:1|true)?(?:&|$|=)/.test(location.search); } catch (e) { return false; }
  }
  function install() {
    if (isMini() || !document.body) { return; }
    document.body.classList.add('tk-frameless');
    if (document.getElementById('win-controls')) { return; }
    var bar = document.getElementById('app-menubar-right') || document.body;
    var box = document.createElement('div');
    box.id = 'win-controls';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', '窗口控制');
    var items = [['min', '—', '最小化'], ['max', '□', '最大化'], ['close', '✕', '关闭']];
    items.forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'win-btn win-' + t[0];
      b.title = t[2];
      b.setAttribute('aria-label', t[2]);
      b.textContent = t[1];
      b.addEventListener('click', function (ev) {
        ev.preventDefault(); ev.stopPropagation(); post('shell:' + t[0]);
      });
      box.appendChild(b);
    });
    bar.appendChild(box);
    var brand = document.getElementById('app-brand');
    if (brand) {
      brand.addEventListener('mousedown', function (ev) {
        if (ev.button !== 0 || (ev.target && ev.target.closest && ev.target.closest('button'))) { return; }
        ev.preventDefault();
        post('shell:drag');
      });
      brand.addEventListener('dblclick', function (ev) {
        ev.preventDefault(); post('shell:max');
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(install, 0); });
  } else {
    setTimeout(install, 0);
  }
})();";

        private void OnMainWebMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string msg = null;
            try { msg = e.TryGetWebMessageAsString(); } catch { }
            if (String.IsNullOrEmpty(msg)) return;
            if (msg == "shell:min") { WindowState = FormWindowState.Minimized; return; }
            if (msg == "shell:max") { ToggleMaximize(); return; }
            if (msg == "shell:close") { Close(); return; }
            if (msg == "shell:drag")
            {
                BeginWindowDrag();
                return;
            }
        }

        /// <summary>
        /// R282：页面标题拖动。这里是**自己跟随光标移动窗口**，不能复用 Native.BeginDrag：
        /// 鼠标按下时捕获在 WebView2 子窗（甚至浏览器进程）手里，ReleaseCapture +
        /// WM_NCLBUTTONDOWN 进不了系统拖动循环，表现就是「标题按下去没反应」。
        /// 每 15ms 读一次光标与左键状态，左键松开即停止；指针移到窗口外也继续跟手。
        /// </summary>
        private void BeginWindowDrag()
        {
            if (_dragging || WindowState == FormWindowState.Maximized) return;
            Native.POINT pt;
            if (!Native.GetCursorPos(out pt)) return;
            _dragging = true;
            _dragCursor = new Point(pt.X, pt.Y);
            _dragWindow = new Point(Left, Top);
            if (_dragTimer == null)
            {
                _dragTimer = new System.Windows.Forms.Timer();
                _dragTimer.Interval = 15;
                _dragTimer.Tick += OnDragTick;
            }
            _dragTimer.Start();
            Log.Write("窗口拖动开始 @" + _dragWindow);
        }

        private void OnDragTick(object sender, EventArgs e)
        {
            if (!_dragging)
            {
                _dragTimer.Stop();
                return;
            }
            // 左键已松开（或窗口被销毁）：结束拖动
            if ((Native.GetAsyncKeyState(0x01) & 0x8000) == 0 || !IsHandleCreated)
            {
                _dragging = false;
                _dragTimer.Stop();
                Log.Write("窗口拖动结束 @" + new Point(Left, Top));
                return;
            }
            Native.POINT pt;
            if (!Native.GetCursorPos(out pt)) return;
            int x = _dragWindow.X + (pt.X - _dragCursor.X);
            int y = _dragWindow.Y + (pt.Y - _dragCursor.Y);
            Native.SetWindowPos(Handle, IntPtr.Zero, x, y, 0, 0,
                Native.SWP_NOSIZE | Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
        }

        private void ApplyWebViewBounds()
        {
            if (_mainController == null) return;
            // R282：没有标题栏了；只有状态条（初始化 / 报错）显示时才让出顶部 24px。
            int top = _status != null && _status.Visible ? _status.Height : 0;
            // R86：不再给 WebView2 留 ResizeBorder 边距。原先四周各留 6px，
            // 露出的窗体 BackColor 会在内容区外圈形成一圈近黑色边框（用户反馈的黑边）；
            // 缩放命中仍由 WS_THICKFRAME 的系统边框 + WM_NCHITTEST 保证，不需要内缩。
            int width = ClientSize.Width;
            int height = ClientSize.Height - top;
            if (width < 1 || height < 1) return;
            try
            {
                _mainController.Bounds = new Rectangle(0, top, width, height);
            }
            catch (Exception ex)
            {
                // 控制器已随浏览器进程销毁；交给健康检查 / ProcessFailed 走恢复。
                Log.Write("设置 WebView2 边界失败：" + ex.Message);
            }
        }

        private void OnNavigationStarting(object sender, CoreWebView2NavigationStartingEventArgs e)
        {
            if (!IsLocalUrl(e.Uri))
            {
                e.Cancel = true;
                Log.Write("拦下非本地导航：" + e.Uri);
                if (!_opt.Smoke) ShellUtil.OpenExternal(e.Uri);
            }
        }

        private void OnNavigationCompleted(object sender, CoreWebView2NavigationCompletedEventArgs e)
        {
            if (!e.IsSuccess)
            {
                _status.Text = "页面加载失败：" + e.WebErrorStatus;
                return;
            }
            _status.Visible = false;
            ApplyWebViewBounds();
            _mainReady = true;
            Log.Write("主页面加载完成");
            WriteDiagnostics();
            if (!String.IsNullOrEmpty(_opt.CaptureDir) || _opt.Smoke)
            {
                BeginPostReady();
            }
        }

        private async void BeginPostReady()
        {
            await Task.Delay(2500);
            await CollectPageState();
            CaptureAll();
            WriteDiagnostics();
            await Task.Delay(5000);
            await CollectPageState();
            CaptureAll();
            WriteDiagnostics();
            if (_opt.CaptureTray) await CaptureTrayMenu();
            if (_opt.CaptureSettings) await CaptureSettingsPanel();
            if (_opt.Smoke) await RunSmoke();
        }

        private async Task CollectPageState()
        {
            if (_mainWeb == null) return;
            try
            {
                string js =
                    "(function(){var svg=document.querySelector('#map-svg');" +
                    "var vp=document.querySelector('#viewport');" +
                    "var stage=document.querySelector('#stage');" +
                    "var err=document.querySelector('#error');" +
                    "var status=document.querySelector('#status-map');" +
                    "var res=performance.getEntriesByType('resource').filter(function(e){" +
                    "return e.name.indexOf('assets/maps')>=0||e.name.indexOf('/data/')>=0;})" +
                    ".slice(-12).map(function(e){return [e.name,e.transferSize,Math.round(e.duration)];});" +
                    "return JSON.stringify({title:document.title,bodyClass:document.body.className," +
                    "svgChildren:svg?svg.childElementCount:-1,svgViewBox:svg?svg.getAttribute('viewBox'):null," +
                    "svgInner:svg?svg.innerHTML.length:-1,svgOuter:svg?svg.outerHTML.slice(0,260):null," +
                    "svgImages:svg?svg.querySelectorAll('image').length:-1," +
                    "dpr:window.devicePixelRatio,inner:[window.innerWidth,window.innerHeight]," +
                    "visual:window.visualViewport?[Math.round(window.visualViewport.width),Math.round(window.visualViewport.height),window.visualViewport.scale]:null," +
                    "viewport:vp?[vp.clientWidth,vp.clientHeight]:null,stage:stage?[stage.clientWidth,stage.clientHeight]:null," +
                    "error:err?String(err.textContent).slice(0,240):null," +
                    "status:status?String(status.textContent):null,resources:res});})()";
                _pageState = await _mainWeb.ExecuteScriptAsync(js);
                Log.Write("页面状态：" + (_pageState.Length > 1600 ? _pageState.Substring(0, 1600) : _pageState));
            }
            catch (Exception ex) { Log.Write("采集页面状态失败：" + ex.Message); }
        }

        private void OnNewWindowRequested(object sender, CoreWebView2NewWindowRequestedEventArgs e)
        {
            e.Handled = true;
            _smokeNewWindowHit = true;
            _smokeNewWindowUri = e.Uri;
            Log.Write("window.open 请求：" + e.Uri);
            if (!_opt.Smoke) ShellUtil.OpenExternal(e.Uri);
        }

        private void OnDownloadStarting(object sender, CoreWebView2DownloadStartingEventArgs e)
        {
            _smokeDownloadHit = true;
            Log.Write("下载开始：" + (e.DownloadOperation != null ? e.DownloadOperation.Uri : "?"));
            if (_opt.Smoke)
            {
                if (String.IsNullOrEmpty(_smokeDownloadPath))
                {
                    string dir = Path.Combine(Path.GetTempPath(), "EFTMapSmoke");
                    Directory.CreateDirectory(dir);
                    _smokeDownloadPath = Path.Combine(dir, "eftmap-smoke.txt");
                }
                try { if (File.Exists(_smokeDownloadPath)) File.Delete(_smokeDownloadPath); } catch { }
                e.Handled = true;
                e.Cancel = false;
                e.ResultFilePath = _smokeDownloadPath;
                Log.Write("smoke 下载保存到：" + _smokeDownloadPath);
            }
        }

        private void OnPermissionRequested(object sender, CoreWebView2PermissionRequestedEventArgs e)
        {
            if (e.PermissionKind == CoreWebView2PermissionKind.ClipboardRead)
            {
                e.State = CoreWebView2PermissionState.Allow;
            }
            else
            {
                e.State = CoreWebView2PermissionState.Deny;
            }
        }

        private void OnFullScreenChanged(object sender, object e)
        {
            Log.Write("页面全屏元素状态发生变化");
        }

        private void OnProcessFailed(object sender, CoreWebView2ProcessFailedEventArgs e)
        {
            Log.Write("WebView2 进程异常：" + e.ProcessFailedKind);
            if (!_recoveringMain) BeginRecover(e.ProcessFailedKind.ToString());
        }

        /// <summary>
        /// R76 崩溃自愈：重建 WebView2 控件；后端 health 失败时一并重启；状态栏给非阻塞提示。
        /// 不整窗空白：恢复失败时仍保留状态栏文字与托盘「用浏览器打开」入口。
        /// </summary>
        private async void BeginRecover(string kind)
        {
            _recoveringMain = true;
            _mainReady = false;
            ShowStatus("页面进程异常（" + kind + "），正在自动恢复…", true);
            try { if (_mainController != null) _mainController.Close(); } catch { }
            _mainController = null;
            _mainWeb = null;
            try
            {
                if (_backend != null && !_backend.IsHealthy())
                {
                    Log.Write("后端 health 失败，尝试重启");
                    _backend.Restart();
                }
                await Task.Delay(1200);
                Exception firstError = null;
                try
                {
                    if (_env == null) throw new InvalidOperationException("环境为空");
                    await CreateMainWeb(_env);
                }
                catch (Exception ex)
                {
                    firstError = ex;
                }
                if (firstError != null)
                {
                    // Browser 进程整体退出后旧 Environment 已失效，换一个新的 Environment 再试一次。
                    Log.Write("旧 WebView2 环境不可用，重建环境：" + firstError.Message);
                    _env = await CoreWebView2Environment.CreateAsync(null, _opt.UserDataDir, _envOptions);
                    await CreateMainWeb(_env);
                }
                _mainWeb.Navigate(_backend.Runtime.Url);
                _mainRecoverCount++;
                Log.Write("WebView2 已重建并重新导航：" + _backend.Runtime.Url + " 次数=" + _mainRecoverCount);
            }
            catch (Exception ex)
            {
                Log.Write("WebView2 自动恢复失败：" + ex);
                ShowStatus("自动恢复失败：" + ex.Message + "，可从托盘「用浏览器打开」继续使用", true);
            }
            finally
            {
                _recoveringMain = false;
            }
        }

        private void ShowStatus(string text, bool warn)
        {
            _status.Text = text;
            _status.ForeColor = warn ? Color.FromArgb(255, 180, 120) : Color.FromArgb(230, 230, 235);
            _status.Visible = true;
            ApplyWebViewBounds();
        }

        private void OnWebResourceResponseReceived(object sender, CoreWebView2WebResourceResponseReceivedEventArgs e)
        {
            try
            {
                if (e.Response.StatusCode >= 400)
                {
                    Log.Write("资源 HTTP " + e.Response.StatusCode + "：" + e.Request.Uri);
                }
            }
            catch { }
        }

        private void OnWebResourceRequested(object sender, CoreWebView2WebResourceRequestedEventArgs e)
        {
            string uri = e.Request.Uri;
            if (IsLocalUrl(uri) || uri.StartsWith("data:", StringComparison.OrdinalIgnoreCase)
                || uri.StartsWith("blob:", StringComparison.OrdinalIgnoreCase)
                || uri.StartsWith("about:", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }
            try
            {
                e.Response = _env.CreateWebResourceResponse(null, 403, "Blocked by offline policy", "");
            }
            catch { }
            Log.Write("拦下外部子资源：" + uri);
        }

        private bool IsLocalUrl(string uri)
        {
            if (String.IsNullOrEmpty(uri) || _backend == null || _backend.Runtime == null) return false;
            string baseUrl = _backend.Runtime.Url;
            if (String.IsNullOrEmpty(baseUrl)) return false;
            if (uri.StartsWith(baseUrl, StringComparison.OrdinalIgnoreCase)) return true;
            string origin = baseUrl.TrimEnd('/');
            return uri.Equals(origin, StringComparison.OrdinalIgnoreCase);
        }

        private void CreateMiniWindow()
        {
            HostConfig hc = HostConfig.Read(_opt.ConfigDir);
            string query = _opt.MiniParams;
            if (String.IsNullOrEmpty(query)) query = "mini=1&size=260&opacity=0.90&shape=square&labels=1&follow=1&ha=1";
            // R106：把持久化的视野半径带进 URL，页面一开就按上次档位渲染（不必等 /api/config 回来）。
            query += "&radius=" + hc.MiniRadius.ToString(System.Globalization.CultureInfo.InvariantCulture);
            string url = _backend.Runtime.Url + "index.html?" + query;
            Options mopt = new Options();
            mopt.Url = url;
            mopt.ConfigDir = _opt.ConfigDir;
            mopt.LogPath = _opt.LogPath;
            mopt.Scale = _opt.Scale;
            mopt.ShellMode = true;
            mopt.StartHidden = !_opt.ShowMiniAtStart;
            mopt.Hotkeys = true;
            mopt.Transparent = true;
            mopt.ClickThrough = -1;
            mopt.OpacityMode = "window";
            mopt.ToggleHotkey = _cfg.MiniToggleHotkey;
            mopt.FullHotkey = _cfg.MiniFullHotkey;
            _mini = new MiniForm(mopt, _env);
            _mini.StateChanged += delegate
            {
                WriteDiagnostics();
                if (!String.IsNullOrEmpty(_opt.CaptureDir) && _mainReady)
                {
                    BeginInvoke(new Action(CaptureMiniState));
                }
            };
            _mini.Handle.ToString();   // 强制创建 HWND，注册全局热键
            IntPtr beforeMini = Native.GetForegroundWindow();
            if (hc.Enabled || _opt.ShowMiniAtStart)
            {
                _mini.ShowMini();
            }
            // R76：小地图首次 SW_SHOWNOACTIVATE 后，某些窗口组合下仍可能被系统置为前台；
            // 启动时若发生这种事，把前台还给之前的窗口（通常是主窗），不让小窗抢焦点。
            IntPtr afterMini = Native.GetForegroundWindow();
            if (afterMini != beforeMini && beforeMini != IntPtr.Zero)
            {
                Native.SetForegroundWindow(beforeMini);
                Log.Write("小地图首显抢前台，已还原 " + afterMini.ToInt64() + " → " + beforeMini.ToInt64());
            }
            Log.Write("小地图窗口已创建（同进程第二窗口），url=" + url);
            CreateTray();
            WriteDiagnostics();
        }

        /// <summary>R282：应用图标。优先用 exe 内嵌的多尺寸 ICO（csc /resource:AppIcon.ico），
        /// 缺资源时退回系统默认图标，保证壳在任何打包方式下都能启动。</summary>
        private static Icon AppIcon(int size = 0)
        {
            try
            {
                if (_appIcon == null)
                {
                    using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("AppIcon"))
                    {
                        if (stream != null) { _appIcon = new Icon(stream); }
                    }
                }
                if (_appIcon != null)
                {
                    return size > 0 ? new Icon(_appIcon, new Size(size, size)) : _appIcon;
                }
            }
            catch { }
            return SystemIcons.Application;
        }

        private void CreateTray()
        {
            if (_opt.NoTray || !_cfg.TrayEnabled || _tray != null) return;
            _tray = new NotifyIcon();
            _tray.Icon = AppIcon(16);
            _tray.Text = "EFT 互动地图";
            _tray.Visible = true;
            ContextMenuStrip menu = new ContextMenuStrip();
            menu.Items.Add("显示主窗口", null, delegate { ShowMain(); });
            menu.Items.Add("隐藏主窗口", null, delegate { Hide(); });
            menu.Items.Add("小地图 显示/隐藏", null, delegate { if (_mini != null) _mini.ToggleMini(); });
            menu.Items.Add("小地图 全图/收回", null, delegate { if (_mini != null) { if (_mini.IsFullMode) _mini.ExitFullMode(); else _mini.EnterFullMode(); } });
            menu.Items.Add("用浏览器打开", null, delegate { if (_backend != null && _backend.Runtime != null) ShellUtil.OpenExternal(_backend.Runtime.Url); });
            menu.Items.Add("设置…", null, delegate { OpenSettings(); });
            menu.Items.Add("高级设置 / 故障排查（tkinter）", null, delegate { OpenAdvancedSettings(); });
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("退出", null, delegate { RequestExit(); });
            _tray.ContextMenuStrip = menu;
            _trayMenu = menu;
            _tray.DoubleClick += delegate { ShowMain(); };
            Log.Write("托盘已创建");
        }

        private void OpenSettings()
        {
            using (SettingsForm form = new SettingsForm(_opt, _cfg))
            {
                form.ShowDialog(this);
            }
            // 小地图会轮询 eftmap.config.json；尺寸/透明度/吸附角可即时生效，热键重启后生效。
            LayoutChrome();
        }

        private void OpenAdvancedSettings()
        {
            try
            {
                string exe = Path.Combine(_opt.Root, "EFTMap.exe");
                string file;
                string args;
                if (File.Exists(exe))
                {
                    file = exe;
                    args = "--settings-only";
                }
                else
                {
                    string launcher = Path.Combine(_opt.Root, "tools", "launcher.py");
                    if (!File.Exists(launcher)) throw new FileNotFoundException("找不到 tools/launcher.py");
                    file = _opt.PythonExe;
                    args = "-u " + ShellUtil.Quote(launcher) + " --settings-only";
                }
                // R75：开发态回退会用 python.exe（控制台子系统），必须隐藏窗口，
                // 否则托盘「高级设置」会闪一个 cmd 窗口。
                ProcessStartInfo psi = new ProcessStartInfo(file, args);
                psi.UseShellExecute = false;
                psi.WorkingDirectory = _opt.Root;
                psi.CreateNoWindow = true;
                Process.Start(psi);
                Log.Write("打开高级设置：" + file + " " + args);
            }
            catch (Exception ex)
            {
                Log.Write("打开高级设置失败：" + ex.Message);
                MessageBox.Show(this, "打开高级设置失败：" + ex.Message, "EFT 互动地图", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void ShowMain()
        {
            Log.Write("显示主窗口");
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Show();
            Activate();
        }

        private void RequestExit()
        {
            Log.Write("RequestExit");
            _exitRequested = true;
            Close();
        }

        private void OnFormClosing(object sender, FormClosingEventArgs e)
        {
            Log.Write("FormClosing exitRequested=" + _exitRequested + " reason=" + e.CloseReason);
            SaveShellConfig();
            if (!_exitRequested && _cfg.CloseToTray && _tray != null &&
                e.CloseReason != CloseReason.WindowsShutDown &&
                e.CloseReason != CloseReason.ApplicationExitCall)
            {
                e.Cancel = true;
                Hide();
                if (!_trayNoticeShown)
                {
                    _trayNoticeShown = true;
                    try { _tray.ShowBalloonTip(1500, "EFT 互动地图", "已最小化到托盘；右键托盘图标可退出。", ToolTipIcon.Info); } catch { }
                }
                return;
            }
        }

        private void OnFormClosed(object sender, FormClosedEventArgs e)
        {
            Log.Write("FormClosed begin");
            if (_dragTimer != null)
            {
                _dragging = false;
                _dragTimer.Stop();
                _dragTimer.Dispose();
                _dragTimer = null;
            }
            if (_healthTimer != null)
            {
                _healthTimer.Stop();
                _healthTimer.Dispose();
                _healthTimer = null;
            }
            SaveShellConfig();
            if (_mini != null)
            {
                try { _mini.Close(); } catch { }
                try { _mini.Dispose(); } catch { }
                _mini = null;
            }
            if (_mainController != null)
            {
                try { _mainController.Close(); } catch { }
                _mainController = null;
            }
            if (_tray != null)
            {
                _tray.Visible = false;
                _tray.Dispose();
                _tray = null;
            }
            Log.Write("桌面壳退出");
        }

        private void SaveShellConfig()
        {
            Rectangle b = (WindowState == FormWindowState.Normal) ? Bounds : RestoreBounds;
            _cfg.MainLeft = b.Left;
            _cfg.MainTop = b.Top;
            _cfg.MainWidth = b.Width;
            _cfg.MainHeight = b.Height;
            _cfg.Maximized = WindowState == FormWindowState.Maximized;
            _cfg.TrayEnabled = _tray != null;
            _cfg.Save(_opt.ConfigDir);
        }

        private void WriteDiagnostics()
        {
            if (String.IsNullOrEmpty(_opt.DumpJson)) return;
            Dictionary<string, object> d = new Dictionary<string, object>();
            d["mode"] = "desktop-shell";
            d["timestamp"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            d["webview2Version"] = _webviewVersion;
            d["root"] = _opt.Root;
            d["configDir"] = _opt.ConfigDir;
            d["userDataDir"] = _opt.UserDataDir;
            if (_backend != null && _backend.Runtime != null)
            {
                Dictionary<string, object> b = new Dictionary<string, object>();
                b["pid"] = _backend.Runtime.Pid;
                b["url"] = _backend.Runtime.Url;
                b["log"] = _backend.BackendLog;
                d["backend"] = b;
            }
            Dictionary<string, object> main = new Dictionary<string, object>();
            if (IsHandleCreated)
            {
                Native.RECT wr = new Native.RECT();
                Native.RECT cr = new Native.RECT();
                Native.GetWindowRect(Handle, out wr);
                Native.GetClientRect(Handle, out cr);
                int style = (int)Native.GetStyle(Handle, Native.GWL_STYLE).ToInt64();
                int ex = (int)Native.GetStyle(Handle, Native.GWL_EXSTYLE).ToInt64();
                main["hwnd"] = Handle.ToInt64().ToString();
                main["title"] = Text;
                main["bounds"] = RectDict(wr);
                main["client"] = new Dictionary<string, object> { { "w", cr.Right - cr.Left }, { "h", cr.Bottom - cr.Top } };
                main["dpi"] = Native.GetWindowDpi(Handle);
                main["style"] = String.Format("0x{0:X8}", style);
                main["exStyle"] = String.Format("0x{0:X8}", ex);
                main["windowState"] = WindowState.ToString();
                main["visible"] = Native.IsWindowVisible(Handle);
                main["ready"] = _mainReady;
                main["showInTaskbar"] = ShowInTaskbar;
                main["webviewRecoverCount"] = _mainRecoverCount;
            }
            d["main"] = main;
            if (_mini != null) d["mini"] = _mini.GetWindowState();
            if (!String.IsNullOrEmpty(_pageState)) d["page"] = _pageState;
            if (_smokeResults != null) d["smoke"] = _smokeResults;
            ShellUtil.WriteJson(_opt.DumpJson, d);
        }

        private static Dictionary<string, object> RectDict(Native.RECT r)
        {
            return new Dictionary<string, object> {
                { "x", r.Left }, { "y", r.Top }, { "w", r.Right - r.Left }, { "h", r.Bottom - r.Top }
            };
        }

        private void CaptureAll()
        {
            if (String.IsNullOrEmpty(_opt.CaptureDir)) return;
            try
            {
                Directory.CreateDirectory(_opt.CaptureDir);
                CaptureWindow(this, Path.Combine(_opt.CaptureDir, "main.png"));
                if (_mini != null && _mini.IsMiniVisible)
                {
                    CaptureWindow(_mini, Path.Combine(_opt.CaptureDir, _mini.IsFullMode ? "mini-full.png" : "mini.png"));
                }
                Log.Write("截图已写入：" + _opt.CaptureDir);
            }
            catch (Exception ex) { Log.Write("截图失败：" + ex.Message); }
        }

        private void CaptureMiniState()
        {
            if (String.IsNullOrEmpty(_opt.CaptureDir) || _mini == null) return;
            try
            {
                _captureCounter++;
                Directory.CreateDirectory(_opt.CaptureDir);
                string name = String.Format("mini-state-{0}.png", _captureCounter);
                if (_mini.IsMiniVisible)
                {
                    CaptureWindow(_mini, Path.Combine(_opt.CaptureDir, name));
                }
                Log.Write("小地图状态截图：" + name + " full=" + _mini.IsFullMode + " visible=" + _mini.IsMiniVisible);
            }
            catch (Exception ex) { Log.Write("小地图状态截图失败：" + ex.Message); }
        }

        private static void CaptureWindow(Form form, string path)
        {
            CaptureHandle(form.Handle, path);
        }

        private static void CaptureHandle(IntPtr hwnd, string path)
        {
            Native.RECT r = new Native.RECT();
            if (!Native.GetWindowRect(hwnd, out r)) return;
            int w = r.Right - r.Left;
            int h = r.Bottom - r.Top;
            if (w <= 0 || h <= 0) return;
            using (Bitmap bmp = new Bitmap(w, h))
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(r.Left, r.Top, 0, 0, new Size(w, h));
                bmp.Save(path, ImageFormat.Png);
            }
        }

        private async Task CaptureSettingsPanel()
        {
            if (String.IsNullOrEmpty(_opt.CaptureDir)) return;
            try
            {
                Directory.CreateDirectory(_opt.CaptureDir);
                SettingsForm form = new SettingsForm(_opt, _cfg);
                form.Show(this);
                await Task.Delay(800);
                try
                {
                    CaptureHandle(form.Handle, Path.Combine(_opt.CaptureDir, "settings.png"));
                }
                catch
                {
                    // 无交互桌面时 CopyFromScreen 会报 “句柄无效”；原生设置面板可用 DrawToBitmap 直接渲染。
                    using (Bitmap bmp = new Bitmap(form.Width, form.Height))
                    {
                        form.DrawToBitmap(bmp, new Rectangle(0, 0, form.Width, form.Height));
                        bmp.Save(Path.Combine(_opt.CaptureDir, "settings.png"), ImageFormat.Png);
                    }
                }
                form.Close();
                Log.Write("设置页截图已写入");
            }
            catch (Exception ex) { Log.Write("设置页截图失败：" + ex.Message); }
        }

        private async Task CaptureTrayMenu()
        {
            if (_trayMenu == null || String.IsNullOrEmpty(_opt.CaptureDir)) return;
            try
            {
                Directory.CreateDirectory(_opt.CaptureDir);
                Rectangle work = Screen.PrimaryScreen.WorkingArea;
                _trayMenu.Show(new Point(work.Right - 260, work.Bottom - 320));
                await Task.Delay(600);
                CaptureHandle(_trayMenu.Handle, Path.Combine(_opt.CaptureDir, "tray-menu.png"));
                _trayMenu.Close();
                Log.Write("托盘菜单截图已写入");
            }
            catch (Exception ex) { Log.Write("托盘菜单截图失败：" + ex.Message); }
        }

        private async Task RunSmoke()
        {
            _smokeResults = new Dictionary<string, object>();
            Log.Write("开始冒烟：download / window.open / file chooser / clipboard");

            // 1) 下载：页面创建 Blob + a.download，由 DownloadStarting 接住并写临时文件。
            try
            {
                string js = "(function(){var b=new Blob(['eftmap smoke download'],{type:'text/plain'});" +
                            "var a=document.createElement('a');a.href=URL.createObjectURL(b);" +
                            "a.download='eftmap-smoke.txt';document.body.appendChild(a);a.click();" +
                            "setTimeout(function(){a.remove();},100);return 'triggered';})()";
                string raw = await _mainWeb.ExecuteScriptAsync(js);
                await Task.Delay(2500);
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["triggered"] = _smokeDownloadHit;
                d["path"] = _smokeDownloadPath;
                d["exists"] = !String.IsNullOrEmpty(_smokeDownloadPath) && File.Exists(_smokeDownloadPath);
                d["js"] = raw;
                _smokeResults["download"] = d;
                Log.Write("smoke download hit=" + _smokeDownloadHit + " exists=" + d["exists"]);
            }
            catch (Exception ex) { _smokeResults["download"] = new Dictionary<string, object> { { "error", ex.Message } }; }

            // 2) window.open：NewWindowRequested 接住；smoke 下不再真的弹系统浏览器。
            try
            {
                string js = "window.open('index.html?mini=1','_blank');'triggered'";
                string raw = await _mainWeb.ExecuteScriptAsync(js);
                await Task.Delay(1000);
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["triggered"] = _smokeNewWindowHit;
                d["uri"] = _smokeNewWindowUri;
                d["handled"] = "new-window-requested";
                d["js"] = raw;
                _smokeResults["windowOpen"] = d;
                Log.Write("smoke window.open hit=" + _smokeNewWindowHit + " uri=" + _smokeNewWindowUri);
            }
            catch (Exception ex) { _smokeResults["windowOpen"] = new Dictionary<string, object> { { "error", ex.Message } }; }

            // 3) 文件选择：本 SDK 没有 FileChooserRequested 事件，触发原生 Open 对话框后检测并关闭。
            try
            {
                string js = "(function(){var i=document.createElement('input');i.type='file';" +
                            "i.id='eftmap-smoke-file';document.body.appendChild(i);i.click();return 'clicked';})()";
                await _mainWeb.ExecuteScriptAsync(js);
                await Task.Delay(1500);
                IntPtr dlg = Native.FindWindow("#32770", null);
                _smokeFileDialogHit = dlg != IntPtr.Zero;
                _smokeFileDialogTitle = _smokeFileDialogHit ? Native.GetWindowTitle(dlg) : "";
                if (_smokeFileDialogHit)
                {
                    Native.PostMessageClose(dlg);
                }
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["dialogDetected"] = _smokeFileDialogHit;
                d["dialogTitle"] = _smokeFileDialogTitle;
                d["note"] = "WebView2 SDK 1.0.4258.31 未暴露 FileChooserRequested；本冒烟只验证原生文件对话框能打开并被关闭，未自动选择文件。";
                _smokeResults["fileChooser"] = d;
                Log.Write("smoke file dialog detected=" + _smokeFileDialogHit + " title=" + _smokeFileDialogTitle);
            }
            catch (Exception ex) { _smokeResults["fileChooser"] = new Dictionary<string, object> { { "error", ex.Message } }; }

            // 4) 剪贴板：ExecuteScriptAsync 对 Promise 只返回 {}，这里用全局变量 + 二次读取。
            //    文件对话框关闭后 WebView2 文档可能没有焦点，先显式把焦点交回主 WebView2。
            try
            {
                bool wasTopMost = TopMost;
                TopMost = true;
                Native.SetForegroundWindow(Handle);
                Activate();
                if (_mainController != null)
                {
                    _mainController.MoveFocus(CoreWebView2MoveFocusReason.Programmatic);
                }
                // 真实点一下主 WebView2：自动化没有用户手势，Chromium 会以 “Document is not focused”
                // 拒绝 navigator.clipboard.writeText；这里发一次原生鼠标点击补上焦点/激活态。
                // 同时临时置顶，避免 PowerShell/浏览器窗口盖在中间，点击落到别的窗口。
                Point center = PointToScreen(new Point(ClientSize.Width / 2, ClientSize.Height / 2));
                Native.MouseClickAt(center.X, center.Y);
                await Task.Delay(500);
                string focusRaw = await _mainWeb.ExecuteScriptAsync("document.hasFocus()");
                Log.Write("smoke clipboard focus=" + focusRaw);
                string js = "(function(){window.__eftSmokeClip='pending';" +
                            "navigator.clipboard.writeText('eftmap-smoke-clipboard').then(function(){" +
                            "window.__eftSmokeClip='ok';},function(e){window.__eftSmokeClip='err:'+" +
                            "((e&&e.name)||'')+':'+((e&&e.message)||'');});return 'started';})()";
                await _mainWeb.ExecuteScriptAsync(js);
                await Task.Delay(800);
                string raw = await _mainWeb.ExecuteScriptAsync("window.__eftSmokeClip || 'missing'");
                JavaScriptSerializer ser = new JavaScriptSerializer();
                object parsed = ser.DeserializeObject(raw);
                Dictionary<string, object> d = new Dictionary<string, object>();
                d["result"] = parsed != null ? Convert.ToString(parsed) : raw;
                d["raw"] = raw;
                _smokeResults["clipboard"] = d;
                Log.Write("smoke clipboard=" + d["result"]);
                TopMost = false;
            }
            catch (Exception ex)
            {
                TopMost = false;
                _smokeResults["clipboard"] = new Dictionary<string, object> { { "error", ex.Message } };
            }

            ShellUtil.WriteJson(_opt.SmokeJson, _smokeResults);
            WriteDiagnostics();
            Log.Write("冒烟完成：" + _opt.SmokeJson);
        }
    }

    internal static class DesktopProgram
    {
        [STAThread]
        private static int Main(string[] args)
        {
            try { Native.SetProcessDpiAwarenessContext(new IntPtr(-4)); }
            catch { try { Native.SetProcessDPIAware(); } catch { } }

            ShellOptions opt;
            try { opt = ShellOptions.Parse(args); }
            catch (Exception ex)
            {
                MessageBox.Show("参数错误：" + ex.Message, "EFT 互动地图", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 2;
            }
            Log.Init(opt.LogPath);
            Log.Write("桌面壳启动参数：" + String.Join(" ", args));

            bool created = false;
            Mutex mutex = new Mutex(true, @"Local\EFTMap.Desktop.Shell", out created);
            if (!created)
            {
                try
                {
                    EventWaitHandle activation = new EventWaitHandle(false, EventResetMode.AutoReset,
                        @"Local\EFTMap.Desktop.Activate");
                    activation.Set();
                }
                catch (Exception ex) { Log.Write("发送激活信号失败：" + ex.Message); }
                ActivateExisting();
                Log.Write("已有壳实例，激活后退出");
                return 0;
            }
            EventWaitHandle activateEvent = new EventWaitHandle(false, EventResetMode.AutoReset,
                @"Local\EFTMap.Desktop.Activate");

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += delegate(object sender, ThreadExceptionEventArgs e)
            {
                Log.Write("UI 线程异常：" + e.Exception);
            };
            AppDomain.CurrentDomain.UnhandledException += delegate(object sender, UnhandledExceptionEventArgs e)
            {
                Log.Write("未处理异常：" + e.ExceptionObject);
            };

            BackendProcess backend = new BackendProcess(opt);
            try
            {
                backend.Start();
            }
            catch (Exception ex)
            {
                Log.Write("后端启动失败：" + ex.Message);
                Application.Run(new FallbackForm(opt, "本地后端启动失败：" + ex.Message, opt.Url));
                backend.Dispose();
                mutex.ReleaseMutex();
                mutex.Dispose();
                return 1;
            }

            string version = null;
            if (!opt.SimulateNoRuntime)
            {
                try { version = CoreWebView2Environment.GetAvailableBrowserVersionString(); }
                catch (Exception ex) { Log.Write("检测 WebView2 Runtime 失败：" + ex.Message); }
            }
            if (String.IsNullOrEmpty(version))
            {
                string reason = opt.SimulateNoRuntime ? "模拟 WebView2 Runtime 缺失" : "未检测到 WebView2 Runtime";
                Log.Write(reason + "，进入浏览器回退路径");
                Application.Run(new FallbackForm(opt, reason, backend.Runtime != null ? backend.Runtime.Url : opt.Url));
                backend.Dispose();
                mutex.ReleaseMutex();
                mutex.Dispose();
                return 0;
            }

            Log.Write("WebView2 Runtime 版本：" + version);
            try
            {
                Application.Run(new DesktopShellForm(opt, backend, version, activateEvent));
            }
            finally
            {
                backend.Dispose();
                try { mutex.ReleaseMutex(); } catch { }
                mutex.Dispose();
            }
            return 0;
        }

        private static void ActivateExisting()
        {
            IntPtr hwnd = Native.FindWindow(null, "EFT 互动地图");
            if (hwnd == IntPtr.Zero) return;
            try
            {
                Native.ShowWindow(hwnd, Native.SW_RESTORE);
                Native.SetForegroundWindow(hwnd);
            }
            catch { }
        }
    }
}
