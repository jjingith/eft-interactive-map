"""客户端云账号 BFF：TLS 钉扎 + 会话持久化 + 增量同步（纯标准库）。

浏览器（WebView2）不能自定义 TLS 证书校验，所以云账号的所有 HTTPS 请求都
由本模块代发。页面只访问 `127.0.0.1`，服务器地址、根 CA 与证书指纹全部内置，
用户不需要填服务器地址，也不需要手动安装证书。

流量策略（详见 docs/cloud-service-plan.md）：
- 不设定时器：token 只在「发请求前发现快过期」时才刷新；
- 不轮询：只在用户操作或显式同步时发请求；
- 增量同步：只上传变化键的哈希与值，服务端未变化直接 304；
- 单条 HTTPS 连接复用；响应 gzip；幂等 GET 才做退避重试。
"""

from __future__ import annotations

import hashlib
import base64
import http.client
import json
import os
import socket
import ssl
import threading
import time
import uuid
from typing import Any, Callable
from urllib.parse import quote

import config
import price_cache

CLOUD_HOST = "47.96.68.209"
CLOUD_PORT = 8443
CLOUD_BASE = "/v1"

# 服务器证书（叶子）SHA-256 指纹；与根 CA 验链、IP SAN 校验同时生效。
LEAF_SHA256 = "3EC4A0C76EBC2DCDBCC36EE6F95FD7D0A77CD99242366D77FA7F5D8BA2537D5E"

SESSION_NAME = "cloud-session.json"
SYNC_NAME = "cloud-sync.json"
# 设备 ID 持久化在这里：首次生成后不再变化，随账号同步使用。
DEVICE_NAME = "cloud-device.json"
LOGIN_PREFS_NAME = "cloud-login-prefs.json"

ACCESS_REFRESH_MARGIN = 60      # 距过期小于该秒数才刷新，避免周期性刷新
REQUEST_TIMEOUT = 12
CONNECT_RETRIES = 2             # 仅幂等 GET：最多重试 2 次
RETRY_SLEEPS = (1.0, 3.0)
OFFLINE_FAILURES = 3            # 连续失败 3 次进入冷却
OFFLINE_COOLDOWN = 60
GZIP_REQUEST_MIN = 512          # 同步上行载荷超过此字节数才压缩（小请求压不动）


def _normalize_fingerprint(value: str) -> str:
    return value.replace(":", "").replace(" ", "").upper()


def _hash_value(value: str) -> str:
    """用 16 位十六进制（64 bit）作为内容指纹；个人进度数据碰撞概率可忽略。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _hash_component(value: str | None) -> str | None:
    """硬件标识只以 SHA-256 形式离开本机；原始值不落盘、不上传。"""
    if not value:
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _default_device_name() -> str:
    name = os.environ.get("COMPUTERNAME") or "Windows 设备"
    return " ".join(str(name).split())[:64] or "Windows 设备"


def _machine_guid() -> str | None:
    """Windows 注册表 MachineGuid：系统安装时生成，重装系统会变。"""
    try:
        import winreg

        flags = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, flags
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MachineGuid")
        return str(value) if value else None
    except (ImportError, OSError, ValueError):
        return None


def _volume_serial() -> str | None:
    """系统盘卷序列号；格式化/换盘会变，不需要管理员权限。"""
    try:
        import ctypes
        from ctypes import wintypes

        drive = (os.environ.get("SystemDrive") or "C:") + "\\"
        serial = wintypes.DWORD()
        max_component = wintypes.DWORD()
        file_flags = wintypes.DWORD()
        volume_name = ctypes.create_unicode_buffer(261)
        fs_name = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive),
            volume_name,
            261,
            ctypes.byref(serial),
            ctypes.byref(max_component),
            ctypes.byref(file_flags),
            fs_name,
            261,
        )
        return format(serial.value, "08X") if ok else None
    except Exception:  # noqa: BLE001 - 采集失败就按缺失处理，不影响登录
        return None


_VIRTUAL_NIC_HINTS = (
    "loopback",
    "virtual",
    "vmware",
    "vbox",
    "virtualbox",
    "vethernet",
    "hyper-v",
    "wsl",
    "tap",
    "tun",
    "docker",
    "tailscale",
    "zerotier",
)


def _primary_mac() -> str | None:
    """首个物理网卡 MAC，尽量排除虚拟网卡；采集不到就返回 None。"""
    try:
        import psutil

        stats = psutil.net_if_stats()
        for name, addresses in psutil.net_if_addrs().items():
            lowered = name.lower()
            if any(hint in lowered for hint in _VIRTUAL_NIC_HINTS):
                continue
            stat = stats.get(name)
            if stat is None or not stat.isup:
                continue
            for address in addresses:
                if getattr(address, "family", None) != psutil.AF_LINK:
                    continue
                mac = str(getattr(address, "address", "") or "")
                if mac and mac.lower() not in ("00:00:00:00:00:00", ""):
                    return mac
    except Exception:  # noqa: BLE001 - 没有 psutil 时退回到 uuid.getnode
        pass
    try:
        node = uuid.getnode()
        # uuid.getnode() 在拿不到物理 MAC 时返回随机值（首字节组播位置 1）
        if (node >> 40) & 1:
            return None
        return ":".join("%02x" % node[i : i + 2] for i in range(0, 12, 2))
    except Exception:  # noqa: BLE001
        return None


class PinningError(Exception):
    """证书指纹与内置值不符，绝不回退到不校验模式。"""


class CloudError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None,
                 member_status: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after
        # 403 membership_required 时服务端会带上当前会员状态，页面据此显示「已过期」等提示
        self.member_status = member_status
        # 429 / 配额类错误会带 quota / next_allowed_at / reset_at，界面直接展示。
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        payload = {"ok": False, "error": self.message, "code": self.code}
        if self.retry_after:
            payload["retry_after"] = self.retry_after
        if self.member_status:
            payload["member_status"] = self.member_status
        for key in ("quota", "next_allowed_at", "reset_at", "delay_seconds"):
            if key in self.details:
                payload[key] = self.details[key]
        return payload


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, *, context: ssl.SSLContext,
                 timeout: float = REQUEST_TIMEOUT):
        super().__init__(host, port, timeout=timeout, context=context)
        expected = _normalize_fingerprint(LEAF_SHA256)

    def connect(self) -> None:  # type: ignore[override]
        super().connect()
        der = self.sock.getpeercert(binary_form=True)
        actual = _normalize_fingerprint(
            ":".join("%02X" % byte for byte in hashlib.sha256(der).digest())
        )
        if actual != _normalize_fingerprint(LEAF_SHA256):
            self.close()
            raise PinningError("服务器证书指纹不匹配")


class CloudClient:
    """所有方法都面向本地 BFF；不产生任何后台定时请求。"""

    def __init__(self, app_dir: str, ca_path: str):
        self.app_dir = os.path.abspath(app_dir)
        self.ca_path = os.path.abspath(ca_path)
        self._lock = threading.RLock()
        self._conn: _PinnedHTTPSConnection | None = None
        self._failures = 0
        self._offline_until = 0.0
        self._session = self._load(SESSION_NAME) or {}
        self._sync = self._load(SYNC_NAME) or {}
        self._device = self._load(DEVICE_NAME) or {}
        self._login_prefs = self._load(LOGIN_PREFS_NAME) or {}
        # 显式选择关闭自动登录后，下次启动不复用本地会话。
        if "auto_login" in self._login_prefs and not self._login_prefs.get("auto_login"):
            if self._session.get("access_token"):
                self._clear_session()
        self._fingerprints: dict | None = None
        # 启动时先用上一次服务端响应缓存着的会员快照；收到 me / 登录 / 刷新后覆盖。
        # 2026-11-15 起会员态只认服务端：注册赠送已写进账号的 member_expires_at，
        # 客户端不再维护 local-trial.json（旧文件保留但不再读取）。
        config.set_member_state(self._session.get("member"))

    # -- 本地文件 -----------------------------------------------------------

    def _path(self, name: str) -> str:
        return os.path.join(self.app_dir, name)

    def _load(self, name: str) -> dict | None:
        try:
            with open(self._path(name), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _save(self, name: str, data: dict) -> None:
        os.makedirs(self.app_dir, exist_ok=True)
        temp = self._path(name + ".tmp")
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self._path(name))

    @staticmethod
    def _protect_password(password: str) -> str:
        """Windows DPAPI：凭据仅可由当前 Windows 用户解密。"""
        if os.name != "nt":
            raise CloudError(400, "secure_storage_unavailable", "当前系统不支持安全保存密码")
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = password.encode("utf-8")
        source = ctypes.create_string_buffer(raw)
        blob_in = DATA_BLOB(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), ctypes.c_wchar_p("EFT Map login"), None, None, None, 0x1,
            ctypes.byref(blob_out),
        ):
            raise OSError("Windows 无法加密登录密码")
        try:
            encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            return base64.b64encode(encrypted).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))

    @staticmethod
    def _unprotect_password(value: str) -> str:
        if os.name != "nt":
            return ""
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        try:
            encrypted = base64.b64decode(value, validate=True)
            source = ctypes.create_string_buffer(encrypted)
            blob_in = DATA_BLOB(len(encrypted), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
            blob_out = DATA_BLOB()
            if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out),
            ):
                return ""
            try:
                return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
            finally:
                ctypes.windll.kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))
        except (ValueError, OSError, UnicodeDecodeError):
            return ""

    def login_preferences(self) -> dict:
        with self._lock:
            remember = bool(self._login_prefs.get("remember_password"))
            password = self._unprotect_password(str(self._login_prefs.get("password_dpapi") or "")) if remember else ""
            return {"remember_password": remember and bool(password),
                    "auto_login": bool(self._login_prefs.get("auto_login")) and bool(password),
                    "email": str(self._login_prefs.get("email") or "") if remember else "",
                    "password": password}

    def set_login_preferences(self, remember: bool, auto_login: bool, email: str = "",
                              password: str = "") -> dict:
        with self._lock:
            if remember and password:
                self._login_prefs = {"remember_password": True,
                                     "auto_login": bool(auto_login),
                                     "email": str(email).strip(),
                                     "password_dpapi": self._protect_password(password)}
            else:
                self._login_prefs = {"remember_password": False, "auto_login": False,
                                     "email": "", "password_dpapi": ""}
            self._save(LOGIN_PREFS_NAME, self._login_prefs)
            return {"remember_password": bool(self._login_prefs["remember_password"]),
                    "auto_login": bool(self._login_prefs["auto_login"])}

    # -- 连接 ---------------------------------------------------------------

    def _context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(cafile=self.ca_path)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    def _connection(self) -> _PinnedHTTPSConnection:
        if self._conn is None:
            # host 传 IP：握手时按证书里的 IP SAN 校验，而不是 SNI 域名
            self._conn = _PinnedHTTPSConnection(
                CLOUD_HOST, CLOUD_PORT, context=self._context()
            )
        return self._conn

    def _close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None

    def _record_ok(self) -> None:
        self._failures = 0
        self._offline_until = 0.0

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= OFFLINE_FAILURES:
            self._offline_until = time.monotonic() + OFFLINE_COOLDOWN

    # -- HTTP ----------------------------------------------------------------

    def _request_once(
        self,
        method: str,
        path: str,
        payload: dict | None,
        token: str | None,
        timeout: float | None = None,
    ) -> tuple[int, dict | None, dict[str, str]]:
        one_off = timeout is not None and float(timeout) != float(REQUEST_TIMEOUT)
        conn = (
            _PinnedHTTPSConnection(CLOUD_HOST, CLOUD_PORT,
                                   context=self._context(), timeout=float(timeout))
            if one_off else self._connection()
        )
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "EFTMap-Client/cloud",
            "Connection": "keep-alive",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
            # 同步接口的上行载荷最大；只对这些路径做请求体压缩。
            # 认证接口请求体都很小（<512B），压缩收益为零。
            if len(body) >= GZIP_REQUEST_MIN and path.startswith(CLOUD_BASE + "/sync/"):
                import gzip

                body = gzip.compress(body, 6)
                headers["Content-Encoding"] = "gzip"
        if token:
            headers["Authorization"] = "Bearer " + token

        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            try:
                raw = response.read()
            except AttributeError as exc:
                # keep-alive 连接被服务端提前关掉时，http.client 内部 fp 已是 None，
                # read() 会抛 AttributeError。按网络断连处理并丢弃这条连接，
                # 由 _request 决定是否重试，避免异常冒到 BFF 变成 500/502。
                self._close()
                raise http.client.HTTPException("响应读取时连接已关闭") from exc
            if response.getheader("Content-Encoding") == "gzip":
                import gzip

                raw = gzip.decompress(raw)
            status = response.status
            if status == 304:
                return status, None, {}
            data: dict | None = None
            if raw:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                    data = parsed if isinstance(parsed, dict) else None
                except (UnicodeDecodeError, json.JSONDecodeError):
                    data = None
            return status, data, {}
        finally:
            # 短超时的一次性连接不进 keep-alive 池：它在 HTTP 头里仍写 keep-alive，
            # 用完必须主动关，否则服务端会一直挂着这条连接。
            if one_off:
                try:
                    conn.close()
                except OSError:
                    pass

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        token: str | None = None,
        retryable: bool = False,
        timeout: float | None = None,
    ) -> tuple[int, dict | None]:
        if self._offline_until and time.monotonic() < self._offline_until:
            remaining = int(self._offline_until - time.monotonic()) + 1
            raise CloudError(0, "offline", "云端暂时不可达，请稍后再试", remaining)

        attempts = CONNECT_RETRIES if retryable else 0
        while True:
            try:
                status, data, _headers = self._request_once(
                    method, path, payload, token,
                    **({"timeout": timeout} if timeout is not None else {}),
                )
                self._record_ok()
                if status >= 400:
                    error = (data or {}).get("error") or {}
                    retry = error.get("retry_after")
                    raise CloudError(
                        status,
                        str(error.get("code") or "http_%d" % status),
                        str(error.get("message") or "请求失败"),
                        int(retry) if retry else None,
                        str((data or {}).get("member_status") or error.get("member_status") or "") or None,
                        details={key: value for key, value in error.items()
                                 if key not in ("code", "message")},
                    )
                return status, data
            except PinningError as exc:
                self._close()
                raise CloudError(0, "pinning", "证书校验失败，已阻止连接") from exc
            except CloudError:
                raise
            except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
                self._close()
                if attempts > 0:
                    delay = RETRY_SLEEPS[min(len(RETRY_SLEEPS) - 1, CONNECT_RETRIES - attempts)]
                    attempts -= 1
                    time.sleep(delay)
                    continue
                self._record_failure()
                raise CloudError(0, "network", "无法连接云服务：%s" % exc) from exc

    # -- 会话 ----------------------------------------------------------------

    @property
    def session(self) -> dict:
        return self._session

    def _store_session(self, tokens: dict, email: str, member: dict | None = None) -> None:
        now = time.time()
        session = {
            "email": email,
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "access_expires_at": now + int(tokens.get("expires_in") or 0),
            "refresh_expires_at": now + int(tokens.get("refresh_expires_in") or 0),
        }
        # 会员快照只来自服务端响应，写入会话缓存供离线展示；
        # 真正的授权判定仍以 /v1/auth/me 为准（见 config.is_member）。
        if isinstance(member, dict) and "member_status" in member:
            session["member"] = {
                "member": member.get("member") is True,
                "member_status": member.get("member_status"),
                "member_plan": member.get("member_plan"),
                "member_since": member.get("member_since"),
                "member_expires_at": member.get("member_expires_at"),
            }
        self._session = session
        self._save(SESSION_NAME, self._session)
        config.set_member_state(session.get("member"))

    def _clear_session(self) -> None:
        self._session = {}
        self._save(SESSION_NAME, {})
        config.set_member_state(None)
        # R279：会员数据缓存只在会员期内有效——退出登录/凭据失效一律清干净。
        price_cache.purge(self.app_dir, reason="clear-session")

    def _mark_not_member(self, member_status: str | None = None) -> None:
        """服务端说「已不是会员」：保留登录会话，只把会员快照改写为非会员。

        403 `membership_required` 表示授权已失效（过期/撤销），不是网络问题；
        这里立即清掉本地会员缓存，避免页面继续按会员态尝试同步。
        """
        snapshot = {"member": False, "member_status": member_status or "none"}
        if self._session.get("access_token"):
            self._session["member"] = snapshot
            self._save(SESSION_NAME, self._session)
        config.set_member_state(snapshot)
        # R279：会员过期 = 云端价格缓存立刻作废（用户明确要求）。
        price_cache.purge(self.app_dir, reason="membership-expired")

    def _refresh(self) -> None:
        refresh_token = self._session.get("refresh_token")
        if not refresh_token:
            raise CloudError(401, "unauthorized", "登录状态已失效，请重新登录")
        try:
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/refresh",
                payload={
                    "refresh_token": refresh_token,
                    "device_id": self._device_context()["device_id"],
                },
            )
        except CloudError as exc:
            if exc.status in (400, 401):
                self._clear_session()
                raise CloudError(401, "unauthorized", "登录状态已失效，请重新登录") from exc
            raise
        if status != 200 or not data:
            self._clear_session()
            raise CloudError(401, "unauthorized", "登录状态已失效，请重新登录")
        self._store_session(data, self._session.get("email") or "", data)

    def _access_token(self, *, force_refresh: bool = False) -> str:
        access = self._session.get("access_token")
        if not access:
            raise CloudError(401, "unauthorized", "请先登录")
        expires = float(self._session.get("access_expires_at") or 0)
        if force_refresh or expires - time.time() <= ACCESS_REFRESH_MARGIN:
            self._refresh()
            access = self._session.get("access_token") or ""
        return access

    def _authorized(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        retryable: bool = False,
        timeout: float | None = None,
    ) -> tuple[int, dict | None]:
        with self._lock:
            token = self._access_token()
            extra = {"timeout": timeout} if timeout is not None else {}
            try:
                return self._request(
                    method, path, payload=payload, token=token, retryable=retryable,
                    **extra,
                )
            except CloudError as exc:
                if exc.status == 403 and exc.code == "membership_required":
                    # 同步接口的会员门槛：立刻降级为非会员，不重试（403 不是限流）
                    self._mark_not_member(exc.member_status)
                    raise
                if exc.status != 401:
                    raise
                # access token 过期/被吊销：只刷新一次并重试，随后失败就要求重登
                token = self._access_token(force_refresh=True)
                try:
                    return self._request(
                        method, path, payload=payload, token=token, **extra
                    )
                except CloudError as retry_exc:
                    if retry_exc.status == 403 and retry_exc.code == "membership_required":
                        self._mark_not_member(retry_exc.member_status)
                    if retry_exc.status == 401:
                        self._clear_session()
                        raise CloudError(
                            401, "unauthorized", "登录状态已失效，请重新登录"
                        ) from retry_exc
                    raise

    # -- 账号 API -----------------------------------------------------------

    def _device_context(self) -> dict:
        """设备 ID + 名字 + 三项硬件标识哈希；设备 ID 首次生成后持久化。"""
        if not self._device.get("device_id"):
            self._device = {
                "device_id": uuid.uuid4().hex,
                "device_name": _default_device_name(),
            }
            self._save(DEVICE_NAME, self._device)
        if self._fingerprints is None:
            self._fingerprints = {
                "machine": _hash_component(_machine_guid()),
                "volume": _hash_component(_volume_serial()),
                "mac": _hash_component(_primary_mac()),
            }
        return {
            "device_id": str(self._device["device_id"]),
            "device_name": str(self._device.get("device_name") or _default_device_name()),
            "fingerprint": dict(self._fingerprints),
        }

    def device_info(self) -> dict:
        with self._lock:
            ctx = self._device_context()
        parts = [value for value in ctx["fingerprint"].values() if value]
        label = hashlib.sha256("|".join(sorted(parts)).encode("utf-8")).hexdigest()[:8]
        return {
            "device_id": ctx["device_id"],
            "device_name": ctx["device_name"],
            "fingerprint": label if parts else None,
        }

    def register(self, email: str, password: str) -> dict:
        with self._lock:
            ctx = self._device_context()
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/register",
                payload={
                    "email": email,
                    "password": password,
                    "device_id": ctx["device_id"],
                },
            )
        return data or {"status": "pending_verification"}

    def resend_verification(self, email: str) -> dict:
        with self._lock:
            ctx = self._device_context()
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/resend-verification",
                payload={"email": email, "device_id": ctx["device_id"]},
            )
        return data or {"status": "pending_verification"}

    def verify_register(self, email: str, code: str) -> dict:
        with self._lock:
            ctx = self._device_context()
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/verify-email",
                payload={
                    "email": email,
                    "code": code,
                    "device_id": ctx["device_id"],
                    "device_name": ctx["device_name"],
                    "fingerprint": ctx["fingerprint"],
                },
            )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        session = data.get("session") or {}
        if not session.get("access_token"):
            raise CloudError(500, "invalid_response", "邮箱已验证，但没有拿到登录会话")
        self._store_session(session, email, data)
        # 注册赠送的会员时长由**云端直接写进账号**（服务端 EFT_REGISTER_FREE_DAYS，
        # 见 eft-cloud 的 verify_email → _grant_register_free_days）。客户端不再写
        # local-trial.json：那套「本机试用」与账号是两本账，换台机器就没了，还会让
        # 「账号显示已到期、本机却能用会员功能」这种矛盾状态看起来像漏洞。
        return {"email": email, "last_login": data.get("last_login")}

    def login(self, email: str, password: str) -> dict:
        with self._lock:
            ctx = self._device_context()
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/login",
                payload={
                    "email": email,
                    "password": password,
                    "device_id": ctx["device_id"],
                    "device_name": ctx["device_name"],
                    "fingerprint": ctx["fingerprint"],
                },
            )
        data = data or {}
        if data.get("status") == "verification_required":
            return {
                "status": "verification_required",
                "reason": data.get("reason"),
                "challenge": data.get("challenge"),
                "expires_in": data.get("expires_in"),
                "message": data.get("message"),
            }
        session = data.get("session") or {}
        if not session.get("access_token"):
            raise CloudError(500, "invalid_response", "云服务返回异常")
        self._store_session(session, email, data)
        prefs = self._login_prefs
        if prefs.get("remember_password"):
            self.set_login_preferences(True, bool(prefs.get("auto_login")), email, password)
        return {
            "email": email,
            "new_device": bool(data.get("new_device")),
            "last_login": data.get("last_login"),
        }

    def verify_login(self, email: str, code: str, challenge: str) -> dict:
        with self._lock:
            ctx = self._device_context()
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/login/verify",
                payload={
                    "email": email,
                    "code": code,
                    "challenge": challenge,
                    "device_id": ctx["device_id"],
                    "device_name": ctx["device_name"],
                    "fingerprint": ctx["fingerprint"],
                },
            )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        session = data.get("session") or {}
        if not session.get("access_token"):
            raise CloudError(500, "invalid_response", "云服务返回异常")
        self._store_session(session, email, data)
        return {
            "email": email,
            "new_device": bool(data.get("new_device")),
            "last_login": data.get("last_login"),
        }

    def request_password_reset(self, email: str) -> dict:
        with self._lock:
            ctx = self._device_context()
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/password/reset-request",
                payload={"email": email, "device_id": ctx["device_id"]},
            )
        return data or {"status": "pending_reset"}

    def reset_password(self, email: str, code: str, password: str) -> dict:
        with self._lock:
            status, data = self._request(
                "POST",
                CLOUD_BASE + "/auth/password/reset",
                payload={"email": email, "code": code, "password": password},
            )
            self._clear_session()
        return data or {"status": "reset"}

    def request_password_change(self) -> dict:
        status, data = self._authorized(
            "POST", CLOUD_BASE + "/auth/password/change-request", payload={}
        )
        return data or {"status": "queued"}

    def change_password(self, code: str, password: str) -> dict:
        status, data = self._authorized(
            "POST",
            CLOUD_BASE + "/auth/password/change",
            payload={"code": code, "password": password},
        )
        with self._lock:
            self._clear_session()
        return data or {"status": "changed"}

    def me(self) -> dict:
        status, data = self._authorized("GET", CLOUD_BASE + "/auth/me", retryable=True)
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        # 服务端是会员态的唯一权威：顺手把快照写进会话缓存，供离线展示与门槛判断
        with self._lock:
            if self._session.get("access_token"):
                self._session["member"] = {
                    "member": data.get("member") is True,
                    "member_status": data.get("member_status"),
                    "member_plan": data.get("member_plan"),
                    "member_since": data.get("member_since"),
                    "member_expires_at": data.get("member_expires_at"),
                }
                self._save(SESSION_NAME, self._session)
                config.set_member_state(self._session["member"])
        return data

    def redeem_tiers(self) -> dict:
        """公开档位表；离线时由前端用内置兜底价展示。"""
        status, data = self._request(
            "GET", CLOUD_BASE + "/redeem/tiers", retryable=True
        )
        if not data or not isinstance(data.get("tiers"), list):
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data

    def redeem(self, code: str) -> dict:
        """用卡密兑换会员时长；成功响应里带服务端会员快照，顺手刷新本机缓存。"""
        status, data = self._authorized(
            "POST", CLOUD_BASE + "/redeem", payload={"code": code}
        )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        with self._lock:
            if self._session.get("access_token"):
                self._session["member"] = {
                    "member": data.get("member") is True,
                    "member_status": data.get("member_status"),
                    "member_plan": data.get("member_plan"),
                    "member_since": data.get("member_since"),
                    "member_expires_at": data.get("member_expires_at"),
                }
                self._save(SESSION_NAME, self._session)
                config.set_member_state(self._session["member"])
        return data

    def devices(self) -> dict:
        status, data = self._authorized(
            "GET", CLOUD_BASE + "/auth/devices", retryable=True
        )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data

    # -- 行情 API（会员） ----------------------------------------------------

    def prices(self, mode: str) -> dict:
        """`GET /v1/prices?mode=...` 最新行情。

        免费或未登录时服务端返回 403 `membership_required`，`_authorized`
        会顺手把本地会员快照降级，调用方据此回退内置快照。
        """
        mode = str(mode or "").strip().lower()
        if not mode:
            raise CloudError(400, "invalid_request", "缺少 mode")
        status, data = self._authorized(
            "GET", CLOUD_BASE + "/prices?mode=" + quote(mode), retryable=True
        )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data

    def prices_market(self, mode: str) -> dict:
        """`GET /v1/prices/market?mode=...` 免费 / 会员共用的行情快照。

        服务端按账号扣配额并执行 CD：会员 30 秒、免费 59:59 且数据延迟 12 小时。
        CD 命中由服务端返回 `status="cd"` + 上次数据；配额用尽返回 429
        `quota_exhausted`，调用方读本地缓存并显示下次可用时间。
        """
        mode = str(mode or "").strip().lower()
        if not mode:
            raise CloudError(400, "invalid_request", "缺少 mode")
        status, data = self._authorized(
            "GET", CLOUD_BASE + "/prices/market?mode=" + quote(mode),
            retryable=True, timeout=20.0,
        )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data

    def prices_history(self, mode: str, basis: str = "7d") -> dict:
        """`GET /v1/prices/history?mode=...&basis=24h|7d` 均价。"""
        mode = str(mode or "").strip().lower()
        basis = str(basis or "").strip().lower()
        if not mode:
            raise CloudError(400, "invalid_request", "缺少 mode")
        if basis not in ("24h", "7d"):
            raise CloudError(400, "invalid_request", "basis 只能是 24h 或 7d")
        status, data = self._authorized(
            "GET",
            CLOUD_BASE + "/prices/history?mode=" + quote(mode) + "&basis=" + quote(basis),
            retryable=True,
        )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data


    def prices_series(self, mode: str, item_ids, days: int = 7) -> dict:
        """`GET /v1/prices/series?mode=&itemIds=&days=` 单物品价格曲线（会员）。

        和 `prices_history` 的日锚点均价不同，这里返回的是**采集机每 30 分钟
        上传的那份快照**里该物品的价格序列——所以新装的客户端不用自己先攒
        几天快照，连上云端就能画出整条曲线。

        这个接口会被「打开物品详情」这条交互路径直接调用，所以用 4 秒短超时：
        云端不可达时快速失败，由调用方回退本机快照，不让图表卡住。
        """
        mode = str(mode or "").strip().lower()
        if not mode:
            raise CloudError(400, "invalid_request", "缺少 mode")
        if isinstance(item_ids, str):
            ids = [part.strip() for part in item_ids.split(",") if part.strip()]
        else:
            ids = [str(part).strip() for part in (item_ids or []) if str(part).strip()]
        if not ids:
            raise CloudError(400, "invalid_request", "缺少 itemId")
        try:
            days = max(1, min(int(days), 90))
        except (TypeError, ValueError):
            days = 7
        path = (
            CLOUD_BASE + "/prices/series?mode=" + quote(mode)
            + "&days=" + str(days)
            + "&itemIds=" + quote(",".join(ids[:12]), safe=",")
        )
        status, data = self._authorized("GET", path, retryable=False, timeout=4.0)
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data

    def prices_cache(self, mode: str, since: str | None = None) -> dict:
        """`GET /v1/prices/cache?mode=&since=` 整包 / 增量价格缓存（会员）。

        登录后整包拉一次（`since=None`），之后带上次返回的 `cursor` 只取新快照。
        整包约 2–3 MB（gzip 后），所以超时给到 60 秒；增量是小请求，同一个
        超时够用。403 由调用方翻译成「会员已过期 → 清本地缓存」。
        """
        mode = str(mode or "").strip().lower()
        if not mode:
            raise CloudError(400, "invalid_request", "缺少 mode")
        path = CLOUD_BASE + "/prices/cache?mode=" + quote(mode)
        if since:
            path += "&since=" + quote(str(since), safe="")
        status, data = self._authorized("GET", path, retryable=False, timeout=60.0)
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        return data


    def revoke_device(self, device_id: str) -> dict:
        status, data = self._authorized(
            "POST", CLOUD_BASE + "/auth/devices/remove", payload={"device_id": device_id}
        )
        if not data:
            raise CloudError(500, "invalid_response", "云服务返回异常")
        if data.get("current"):
            with self._lock:
                self._clear_session()
        return data

    def logout(self) -> dict:
        with self._lock:
            refresh_token = self._session.get("refresh_token")
            if self._session.get("access_token"):
                try:
                    self._authorized(
                        "POST",
                        CLOUD_BASE + "/auth/logout",
                        payload={"refresh_token": refresh_token},
                    )
                except CloudError:
                    pass  # 本地一定要退出，服务端吊销失败不阻塞
            self._clear_session()
            if self._login_prefs.get("remember_password"):
                self._login_prefs["auto_login"] = False
                self._save(LOGIN_PREFS_NAME, self._login_prefs)
        return {"ok": True}

    def clear_login_preferences(self) -> dict:
        return self.set_login_preferences(False, False)

    def status(self) -> dict:
        with self._lock:
            session = self._session
            # 会员快照让面板一打开就能按会员态渲染同步区，不用等 /auth/me
            member = config.member_state()
            if not session.get("access_token"):
                return {"ok": True, "logged_in": False, "sync": self._sync_summary(),
                        "member": member}
            return {
                "ok": True,
                "logged_in": True,
                "email": session.get("email"),
                "access_expires_in": max(
                    0, int(float(session.get("access_expires_at") or 0) - time.time())
                ),
                "sync": self._sync_summary(),
                "member": member,
            }

    # -- 增量同步 -----------------------------------------------------------

    def _sync_meta(self, email: str) -> dict:
        if self._sync.get("account") != email:
            self._sync = {"account": email, "rev": 0, "hashes": {}, "last_sync_at": None}
        return self._sync

    def _sync_summary(self) -> dict:
        return {
            "rev": int(self._sync.get("rev") or 0),
            "last_sync_at": self._sync.get("last_sync_at"),
            "conflicts": self._sync.get("conflicts") or {},
        }

    def sync(self, values: dict, *, force: bool = False) -> dict:
        """values 是「全部同步键 → 本地值」。只有与服务端不同的键才会发出。"""
        if not isinstance(values, dict):
            raise CloudError(400, "invalid_request", "values 必须是对象")
        with self._lock:
            email = self._session.get("email")
            if not email:
                raise CloudError(401, "unauthorized", "请先登录")
            # 云同步是会员功能：本地已经知道不是会员时，连一个 /v1/sync/* 请求都不发。
            # 真正的授权仍由服务端判定；这里只是让「免费账号点不动」在 BFF 层也成立。
            if not config.is_member(self.app_dir):
                raise CloudError(
                    403, "membership_required", "云同步是会员功能，请开通会员后再使用",
                    member_status=config.member_state().get("member_status"),
                )
            normalized: dict[str, str] = {}
            for key, value in values.items():
                if isinstance(value, str):
                    normalized[str(key)] = value
            meta = self._sync_meta(email)
            local_hashes = {key: _hash_value(value) for key, value in normalized.items()}
            changed = {
                key: value
                for key, value in normalized.items()
                if local_hashes[key] != (meta.get("hashes") or {}).get(key)
            }

            remote: dict[str, str] = {}
            conflicts: dict[str, str] = {}
            if changed:
                status, data = self._authorized(
                    "POST",
                    CLOUD_BASE + "/sync/push",
                    payload={
                        "base_rev": int(meta.get("rev") or 0),
                        "force": bool(force),
                        "changes": {
                            key: {"hash": local_hashes[key], "value": value}
                            for key, value in changed.items()
                        },
                    },
                )
                if not data:
                    raise CloudError(500, "invalid_response", "云服务返回异常")
                meta["rev"] = int(data.get("rev") or meta.get("rev") or 0)
                conflicts = data.get("conflicts") or {}
                remote = data.get("remote") or {}
                hashes = meta.setdefault("hashes", {})
                for key in changed:
                    if key not in conflicts:
                        hashes[key] = local_hashes[key]
            else:
                status, data = self._authorized(
                    "GET",
                    CLOUD_BASE + "/sync/state?since=%d" % int(meta.get("rev") or 0),
                    retryable=True,
                )
                if status != 304 and data:
                    meta["rev"] = int(data.get("rev") or meta.get("rev") or 0)
                    remote = data.get("keys") or {}

            hashes = meta.setdefault("hashes", {})
            # 远端「没变」的键直接对齐哈希；变了的键先记下，下面按需拉值
            for key, digest in remote.items():
                if digest == local_hashes.get(key):
                    hashes[key] = digest

            need_fetch = [key for key, digest in remote.items()
                          if digest != local_hashes.get(key) and key not in conflicts]
            fetched: dict[str, str] = {}
            if need_fetch:
                status, data = self._authorized(
                    "POST", CLOUD_BASE + "/sync/fetch", payload={"keys": need_fetch}
                )
                for key, item in ((data or {}).get("keys") or {}).items():
                    if isinstance(item, dict):
                        hashes[key] = item.get("hash")
                        fetched[key] = item.get("value") or ""

            meta["conflicts"] = conflicts
            meta["last_sync_at"] = int(time.time())
            self._sync = meta
            self._save(SYNC_NAME, self._sync)
            return {
                "ok": True,
                "rev": int(meta.get("rev") or 0),
                "uploaded": len(changed),
                "download": len(fetched),
                "conflicts": conflicts,
                "remote": fetched,
            }
