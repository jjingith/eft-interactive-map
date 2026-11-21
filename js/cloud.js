/* 云账号：注册 / 登录 / 低频增量同步。
   所有网络请求都发往本机 BFF（/api/cloud/*），由 Python 侧做证书钉扎；
   页面本身不直连云端，也不在后台轮询。?mini=1 时整体跳过。 */
(function () {
  "use strict";

  var params = new URLSearchParams(window.location.search);
  if (params.get("mini") === "1") { return; }

  var LS_AUTOSYNC = "eftmap.cloud.autosync";
  var MODE_KEYS = ["regular", "pve", "pvps"];
  // R233：预设也走同一个 /v1/sync/* 通用 KV（服务端零改动）。键名必须匹配
  // 云端 SYNC_KEY_RE=^[a-z0-9][a-z0-9._-]{0,63}$，单值上限 256KB。
  var PRESET_KINDS = ["weapon", "loadout"];
  var PRESET_SYNC_SCHEMA = 1;
  var PRESET_MAX_CHARS = 240000;   // 留 16KB 余量给服务端 256KB 上限
  var presetSyncNote = "";         // 本次同步里被跳过的预设（不静默丢数据，要显示出来）
  var DEBOUNCE_MS = 3000;        // 任务进度保存后等 3 秒再同步（合并连续操作）
  var MIN_INTERVAL_MS = 15000;   // 两次自动同步至少隔 15 秒，避免连点造成请求风暴

  var view = document.getElementById("cloud-view");
  var menuButton = document.getElementById("am-cloud");
  if (!view || !menuButton) { return; }

  // 档位以云端 /v1/redeem/tiers 为准；离线时用这份兜底，保证面板仍能展示价格。
  var FALLBACK_TIERS = [
    { tier: "d1", label: "1 天", days: 1, price: 1 },
    { tier: "m1", label: "1 个月", days: 30, price: 12 },
    { tier: "m3", label: "3 个月", days: 90, price: 30 },
    { tier: "m6", label: "6 个月", days: 180, price: 60 },
    { tier: "y1", label: "12 个月", days: 365, price: 108 }
  ];

  var state = {
    loggedIn: false,
    email: "",
    sync: {},
    mode: "login",       // login | register | reset
    phaseEmail: "",
    password: "",        // 只留在内存，用于「新设备」第二段重发验证码
    challenge: "",       // 密码验证通过后服务端签发的一次性凭据
    sending: false,
    syncing: false,
    syncUnavailable: false,  // 服务端还没有 /v1/sync（旧版部署）：直接停用，不再重试
    autoSync: (function () {
      try { return localStorage.getItem(LS_AUTOSYNC) !== "0"; } catch (e) { return true; }
    })(),
    member: false,           // 云同步是会员功能；默认按非会员锁住
    memberStatus: "none",    // none | active | permanent | expired
    memberPlan: null,
    memberExpiresAt: null,
    redeemTiers: FALLBACK_TIERS.slice(),
    redeemCode: "",
    redeemShopUrl: "",    // 爱发电店铺链接由云端下发；为空则不显示购买入口
    rememberPassword: false,
    autoLogin: false,
    pendingRemember: false,
    pendingAutoLogin: false,
    autoLoginAttempted: false
  };
  var cooldownTimer = 0;
  var cooldownUntil = 0;
  var lastMeAt = 0;
  var lastSyncAt = 0;
  var syncTimer = 0;
  var applyingRemote = false;

  // ---------------------------------------------------------------- 网络

  function api(path, options) {
    var init = {
      method: (options && options.method) || "GET",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    };
    if (options && options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    return fetch(path, init).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok || (data && data.ok === false)) {
          var error = new Error((data && data.error) || ("请求失败（" + response.status + "）"));
          error.status = response.status;
          error.code = data && data.code;
          error.retryAfter = data && data.retry_after;
          // 403 membership_required 时服务端会带回当前会员状态（如 expired）
          error.memberStatus = data && data.member_status;
          throw error;
        }
        return data;
      });
    }).catch(function (error) {
      if (error && error.status) { throw error; }
      var wrapped = new Error("无法连接本机云服务，请用桌面客户端打开");
      wrapped.code = "local_offline";
      throw wrapped;
    });
  }

  // ---------------------------------------------------------------- 小工具

  function clearNode(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function setMsg(text, isError) {
    var el = view.querySelector("[data-role='msg']");
    if (!el) { return; }
    el.textContent = text || "";
    el.classList.toggle("is-error", !!isError);
  }

  function validEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  function formatTime(seconds) {
    if (!seconds) { return "从未"; }
    try {
      return new Date(seconds * 1000).toLocaleString();
    } catch (e) { return "从未"; }
  }

  function formatIso(value) {
    if (!value) { return "未知"; }
    var date = new Date(value);
    if (isNaN(date.getTime())) { return String(value); }
    return date.toLocaleString();
  }

  /** 二级栏徽标用的紧凑日期：**必须带年份**。
   *
   *  用户实测踩坑（2026-11-15）：之前只输出「MM-DD HH:mm」，一年后的到期时间
   *  （2027-11-14）显示成「11-14 13:59」，看起来像昨天就过期了 → 误以为会员已到期。
   *  到期日是「哪一天」的核心信息，省掉年份等于把信息变成错的。 */
  function formatExpire(value) {
    if (!value) { return ""; }
    var d = new Date(value);
    if (isNaN(d.getTime())) { return ""; }
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  /** 距到期还有几天（向上取整；已过期或算不出返回 null）。 */
  function daysLeft(value) {
    if (!value) { return null; }
    var d = new Date(value);
    if (isNaN(d.getTime())) { return null; }
    var left = d.getTime() - Date.now();
    if (left <= 0) { return 0; }
    return Math.ceil(left / 86400000);
  }

  /** 一级栏「云账号：XX版」+ 二级栏会员到期，始终由同一份会员快照驱动。 */
  function updateMemberBadges() {
    var isMember = state.member === true;
    menuButton.textContent = "云账号：" + (isMember ? "会员版" : "免费版");
    var badge = document.getElementById("vt-member-expire");
    if (!badge) { return; }
    var text, tone, tip;
    if (state.memberStatus === "expired") {
      text = "会员已过期"; tone = "expired"; tip = "会员已过期，续费后恢复会员权益";
    } else if (!isMember) {
      text = "会员未开通"; tone = "free"; tip = "当前为免费版，会员权益未开通";
    } else if (state.memberStatus === "permanent" ||
               (state.memberStatus !== "trial" && !state.memberExpiresAt)) {
      text = "会员到期：永久"; tone = "member"; tip = "永久会员，无到期时间";
    } else {
      var short = formatExpire(state.memberExpiresAt);
      var left = daysLeft(state.memberExpiresAt);
      text = short
        ? ("会员到期：" + short + (left === null ? "" : "（剩 " + left + " 天）"))
        : "会员到期：未知";
      tone = "member";
      tip = "会员到期时间：" + formatIso(state.memberExpiresAt) +
            (left === null ? "" : "（剩 " + left + " 天）") +
            (state.memberStatus === "trial" ? "（新注册赠送）" : "");
    }
    badge.textContent = text;
    badge.dataset.tone = tone;
    badge.title = tip;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
    });
  }

  // ---------------------------------------------------------------- 未登录界面

  function primaryLabel(mode) {
    if (mode === "register") { return "注册并发送验证码"; }
    if (mode === "reset") { return "发送重置验证码"; }
    return "登录";
  }

  function codeLabel(mode) {
    if (mode === "register") { return "验证并完成注册"; }
    if (mode === "reset") { return "重置密码"; }
    return "验证并登录";
  }

  // ------------------------------------------------- 会员充值（激活码档位）

  function redeemHtml() {
    return [
      '<p class="cloud-section-title">会员充值 · 激活码</p>',
      '<div class="rd-tiers" data-role="rd-tiers" role="radiogroup" aria-label="会员档位"></div>',
      '<p class="cloud-note rd-hint" data-role="rd-hint"></p>',
      '<button type="button" class="acc-btn rd-buy" data-action="redeem-buy" hidden>前往爱发电购买</button>',
      '<div class="rd-form">',
      '  <input type="text" data-role="rd-code" maxlength="24" spellcheck="false"',
      '         autocomplete="off" placeholder="XXXX-XXXX-XXXX-XXXX" aria-label="激活码">',
      '  <button type="button" class="acc-btn rd-submit" data-action="redeem">立即兑换</button>',
      '</div>',
      '<p class="cloud-msg rd-msg" data-role="rd-msg" role="status" aria-live="polite"></p>'
    ].join("");
  }

  function updateRedeemHint() {
    var el = view.querySelector("[data-role='rd-hint']");
    if (!el) { return; }
    // 兑换以激活码自带的天数为准，卡片只是爱发电商品页的型号价目。
    el.textContent = "激活码自带天数，兑换时不用选档位；下方是商品页的型号价目，" +
      "购买时在爱发电选对应型号下单即可。";
  }

  function renderRedeemTiers() {
    var host = view.querySelector("[data-role='rd-tiers']");
    if (!host) { return; }
    clearNode(host);
    state.redeemTiers.forEach(function (t) {
      // 纯展示卡片：不设选中态、不可点，避免误以为「必须选对档位才能兑换」。
      var card = document.createElement("div");
      card.className = "rd-tier";
      card.setAttribute("data-tier", t.tier);
      var name = document.createElement("span");
      name.className = "rd-tier-label";
      name.textContent = t.label;
      var price = document.createElement("span");
      price.className = "rd-tier-price";
      price.textContent = "¥" + t.price;
      card.appendChild(name);
      card.appendChild(price);
      host.appendChild(card);
    });
    updateRedeemHint();
    updateRedeemBuyButton();
  }

  /** 店铺链接由云端下发（EFT_AFDIAN_SHOP_URL），为空则隐藏购买入口。 */
  function updateRedeemBuyButton() {
    var btn = view.querySelector("[data-action='redeem-buy']");
    if (!btn) { return; }
    if (state.redeemShopUrl) {
      btn.hidden = false;
      btn.textContent = "前往爱发电购买";
      btn.title = "在新浏览器打开爱发电商品页，选择型号并付款，激活码会自动发到你的爱发电账号";
    } else {
      btn.hidden = true;
    }
  }

  function mountRedeem() {
    var old = view.querySelector("[data-role='redeem-area']");
    if (old && old.parentNode) { old.parentNode.removeChild(old); }
    var section = document.createElement("section");
    section.className = "cloud-redeem";
    section.setAttribute("data-role", "redeem-area");
    section.innerHTML = redeemHtml();
    // 已登录时充值入口紧跟会员状态，避免被「已绑定设备 / 修改密码」挤到面板底部。
    var syncArea = view.querySelector("[data-role='sync-area']");
    if (syncArea) { view.insertBefore(section, syncArea); }
    else { view.appendChild(section); }
    var input = section.querySelector("[data-role='rd-code']");
    if (input) { input.value = state.redeemCode || ""; }
    renderRedeemTiers();
  }

  function loadRedeemTiers() {
    api("/api/cloud/redeem/tiers").then(function (data) {
      state.redeemShopUrl = data && typeof data.shop_url === "string" ? data.shop_url : "";
      if (!data || !Array.isArray(data.tiers) || !data.tiers.length) {
        updateRedeemBuyButton();
        return;
      }
      var tiers = data.tiers.filter(function (t) {
        return t && typeof t.tier === "string" && typeof t.label === "string";
      }).map(function (t) {
        return { tier: t.tier, label: t.label,
                 days: Number(t.days) || 0, price: Number(t.price) || 0 };
      });
      if (!tiers.length) { return; }
      state.redeemTiers = tiers;
      renderRedeemTiers();
    }).catch(function () { /* 离线时保留兜底档位 */ });
  }

  function setRedeemMsg(text, isError) {
    var el = view.querySelector("[data-role='rd-msg']");
    if (!el) { return; }
    el.textContent = text || "";
    el.classList.toggle("is-error", !!isError);
  }

  function redeemErrorMessage(error) {
    var code = error && error.code;
    if (code === "code_not_found") { return "激活码不存在，请核对后重试"; }
    if (code === "code_used") { return "该激活码已被使用"; }
    if (code === "code_disabled") { return "该激活码已停用，请联系管理员"; }
    if (code === "code_expired") { return "该激活码已过期"; }
    if (code === "invalid_code") { return "激活码格式不正确（XXXX-XXXX-XXXX-XXXX）"; }
    if (code === "already_permanent") { return "当前是永久会员，无需兑换"; }
    if (code === "too_many_attempts") { return "尝试次数过多，请稍后再试"; }
    if (code === "unauthorized") { return "登录状态已失效，请重新登录"; }
    if (code === "local_offline" || code === "network") { return "暂时连不上云端，请稍后再试"; }
    return (error && error.message) || "兑换失败，请稍后再试";
  }

  function submitRedeem() {
    var input = view.querySelector("[data-role='rd-code']");
    var code = input ? input.value.trim() : "";
    state.redeemCode = code;
    if (!code) { setRedeemMsg("请输入激活码", true); return; }
    if (!state.loggedIn) { setRedeemMsg("请先登录云账号，再兑换激活码", true); return; }
    var button = view.querySelector("[data-action='redeem']");
    if (button) { button.disabled = true; }
    setRedeemMsg("正在兑换…");
    api("/api/cloud/redeem", { method: "POST", body: { code: code } })
      .then(function (result) {
        state.redeemCode = "";
        if (input) { input.value = ""; }
        applyMember(result);
        notifyMemberChanged();
        setRedeemMsg("兑换成功：" + (result.label || "") + "，增加 " +
          (result.added_days || 0) + " 天，会员到期 " + formatIso(result.member_expires_at));
        return api("/api/cloud/me").then(applyMember).catch(function () { /* 缓存已是最新 */ });
      })
      .catch(function (error) { setRedeemMsg(redeemErrorMessage(error), true); })
      .then(function () {
        var btn = view.querySelector("[data-action='redeem']");
        if (btn) { btn.disabled = false; }
      });
  }

  function renderGuest(message) {
    if (cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = 0; }
    state.loggedIn = false;
    // 退出 / 登录失效时同步区本来就不显示，同时清掉会员快照，避免换号后误按会员态解锁
    state.member = false;
    state.memberStatus = "none";
    state.memberPlan = null;
    state.memberExpiresAt = null;
    updateMemberBadges();
    clearNode(view);
    var reset = state.mode === "reset";
    view.innerHTML = [
      '<p class="cloud-title">云账号</p>',
      '<p class="cloud-note">' + (reset
        ? "输入邮箱获取 6 位验证码，验证后设置新密码；所有设备会退出登录。"
        : "邮箱 + 密码登录。首次登录、注销后再登录或长时间未登录时，需要邮箱验证码。") + '</p>',
      reset ? "" : [
        '<div class="cloud-tabs" role="tablist">',
        '  <button type="button" class="cloud-tab' + (state.mode === "login" ? " is-active" : "") +
          '" data-mode="login" role="tab" aria-selected="' + (state.mode === "login") + '">登录</button>',
        '  <button type="button" class="cloud-tab' + (state.mode === "register" ? " is-active" : "") +
          '" data-mode="register" role="tab" aria-selected="' + (state.mode === "register") + '">注册</button>',
        '</div>'
      ].join(""),
      '<label class="cloud-field"><span>邮箱</span>',
      '  <input type="email" data-role="email" autocomplete="email" spellcheck="false" placeholder="you@example.com">',
      '</label>',
      '<label class="cloud-field" data-role="password-field"' + (reset ? " hidden" : "") + '><span>密码</span>',
      '  <div class="cloud-password">',
      '    <input type="password" data-role="password" autocomplete="' +
        (state.mode === "register" ? "new-password" : "current-password") + '"',
      '           placeholder="' + (state.mode === "register" ? "设置密码（仅要求非空）" : "输入密码") + '">',
      '    <button type="button" class="cloud-eye" data-action="toggle-password" aria-label="显示密码">显示</button>',
      '  </div>',
      '</label>',
      state.mode === "login" ? [
        '<div class="cloud-login-options">',
        '  <label><input type="checkbox" data-role="remember-password"> 记住密码</label>',
        '  <label><input type="checkbox" data-role="auto-login"> 自动登录</label>',
        '</div>'
      ].join("") : "",
      '<p class="cloud-strength" data-role="strength" aria-live="polite"></p>',
      '<button type="button" class="acc-btn cloud-primary" data-action="primary">' +
        primaryLabel(state.mode) + '</button>',
      '<button type="button" class="cloud-link" data-action="forgot">' +
        (reset ? "返回登录" : "忘记密码？") + '</button>',
      '<label class="cloud-field" data-role="code-field" hidden><span>6 位验证码</span>',
      '  <input type="text" data-role="code" inputmode="numeric" maxlength="6"',
      '         autocomplete="one-time-code" placeholder="000000">',
      '</label>',
      '<button type="button" class="acc-btn cloud-primary" data-action="submit" hidden>' +
        codeLabel(state.mode) + '</button>',
      '<button type="button" class="cloud-link" data-action="resend" hidden>重新发送</button>',
      '<p class="cloud-msg" data-role="msg" role="status" aria-live="polite"></p>'
    ].join("");
    setMsg(message || "");
    if (state.email) {
      var emailInput = view.querySelector("[data-role='email']");
      if (emailInput) { emailInput.value = state.email; }
    }
    var rememberToggle = view.querySelector("[data-role='remember-password']");
    var autoToggle = view.querySelector("[data-role='auto-login']");
    if (rememberToggle) { rememberToggle.checked = state.rememberPassword; }
    if (autoToggle) { autoToggle.checked = state.autoLogin; }
    if (reset) {
      var resetPw = view.querySelector("[data-role='password']");
      if (resetPw) { resetPw.autocomplete = "new-password"; }
    }
    mountRedeem();
  }

  function setMode(mode) {
    state.mode = mode;
    state.phaseEmail = "";
    state.password = "";
    state.challenge = "";
    renderGuest(mode === "register" ? "注册后邮箱会收到 6 位验证码。" : "");
  }

  function showCodeStep(seconds, submitLabel) {
    var codeField = view.querySelector("[data-role='code-field']");
    var submit = view.querySelector("[data-action='submit']");
    var primary = view.querySelector("[data-action='primary']");
    var emailInput = view.querySelector("[data-role='email']");
    var passwordField = view.querySelector("[data-role='password-field']");
    if (codeField) { codeField.hidden = false; }
    if (submit) { submit.hidden = false; submit.textContent = submitLabel || codeLabel(state.mode); }
    if (primary) { primary.hidden = true; }
    if (emailInput) { emailInput.readOnly = true; }
    if (state.mode === "reset" && passwordField) {
      passwordField.hidden = false;
      var label = passwordField.querySelector("span");
      if (label) { label.textContent = "新密码"; }
      var pw = view.querySelector("[data-role='password']");
      if (pw) { pw.value = ""; pw.placeholder = "设置新密码（仅要求非空）"; pw.autocomplete = "new-password"; }
    } else if (passwordField) {
      passwordField.hidden = true;
    }
    startCooldown(seconds);
    var code = view.querySelector("[data-role='code']");
    if (code) { code.focus(); }
  }

  function startCooldown(seconds) {
    var resend = view.querySelector("[data-action='resend']");
    if (!resend) { return; }
    cooldownUntil = Date.now() + Math.max(0, Number(seconds) || 0) * 1000;
    resend.hidden = false;
    if (cooldownTimer) { clearInterval(cooldownTimer); }
    function tick() {
      var left = Math.ceil((cooldownUntil - Date.now()) / 1000);
      if (left <= 0) {
        clearInterval(cooldownTimer);
        cooldownTimer = 0;
        resend.disabled = false;
        resend.textContent = "重新发送";
        return;
      }
      resend.disabled = true;
      resend.textContent = "重新发送（" + left + " 秒）";
    }
    tick();
    cooldownTimer = setInterval(tick, 1000);
  }

  function busy(flag) {
    state.sending = flag;
    var buttons = view.querySelectorAll(
      "[data-action='primary'], [data-action='submit'], [data-action='resend']," +
      "[data-action='change-start'], [data-action='change-submit']"
    );
    for (var i = 0; i < buttons.length; i++) { buttons[i].disabled = flag; }
  }

  function handleError(error) {
    if (error && error.code === "membership_required") {
      // 非会员 / 过期：只刷新成「锁定」状态，不弹报错、不重试
      handleMembershipRequired(error);
      return;
    }
    var text = (error && error.message) || "操作失败";
    setMsg(text, true);
    if (error && error.code === "local_offline") {
      // BFF 不可用：不做任何重试，等用户下次操作
      return;
    }
    if (error && error.status === 401 && state.loggedIn) {
      state.loggedIn = false;
      renderGuest("登录已失效，请重新登录");
    }
  }

  function updateStrength(value) {
    var el = view.querySelector("[data-role='strength']");
    if (!el) { return; }
    if (!value) { el.textContent = ""; return; }
    var score = 0;
    if (value.length >= 8) { score++; }
    if (/[A-Za-z]/.test(value)) { score++; }
    if (/\d/.test(value)) { score++; }
    if (/[^A-Za-z0-9]/.test(value)) { score++; }
    var labels = ["弱", "一般", "较强", "强"];
    el.textContent = "密码强度：" + labels[Math.max(0, Math.min(3, score - 1))] +
      "（仅提示，不限制登录）";
  }

  function readEmail() {
    var input = view.querySelector("[data-role='email']");
    return input ? input.value.trim() : "";
  }

  function readPassword() {
    var input = view.querySelector("[data-role='password']");
    return input ? input.value : "";
  }

  function showLoginNotice(lastLogin) {
    if (!lastLogin || !lastLogin.at) { return; }   // 首次登录没有上次记录，不弹
    var when = formatIso(lastLogin.at);
    var parts = ["上次登录：" + when];
    if (lastLogin.ip) { parts.push("IP " + lastLogin.ip); }
    if (lastLogin.location) { parts.push(lastLogin.location); }
    var el = document.createElement("div");
    el.className = "cloud-toast";
    el.setAttribute("role", "status");
    el.textContent = parts.join(" · ");
    document.body.appendChild(el);
    setTimeout(function () {
      if (el.parentNode) { el.parentNode.removeChild(el); }
    }, 10000);   // 10 秒后自动消失，只提示不拦截
  }

  /** 会员态可能变化：通知页面重拉 /api/config，让会员入口按服务端状态刷新。 */
  function notifyMemberChanged() {
    try { window.dispatchEvent(new window.CustomEvent("eftmap:member-changed")); }
    catch (err) { /* 忽略：环境没有 CustomEvent 时保持旧状态 */ }
  }

  function memberLabel(me) {
    if (!me || me.member !== true) {
      return me && me.member_status === "expired" ? "会员已过期" : "非会员";
    }
    if (me.member_status === "permanent" ||
        (me.member_status !== "trial" && !me.member_expires_at)) { return "永久会员"; }
    return "会员（到期 " + formatIso(me.member_expires_at) + "）";
  }

  /** 写入服务端下发的会员快照；true 才解锁同步，过期按非会员处理。 */
  function applyMember(payload) {
    var raw = payload || {};
    var status = raw.member_status;
    if (status !== "none" && status !== "active" && status !== "permanent" &&
        status !== "expired" && status !== "trial") {
      status = raw.member === true ? "permanent" : "none";
    }
    // trial = 云端为「新注册赠送」写入的会员态（已包含在账号的 member_expires_at
    // 里，换设备也有效）；权益与 active 完全一致，只在文案上区分来源。
    state.member = raw.member === true &&
      (status === "active" || status === "permanent" || status === "trial");
    state.memberStatus = status;
    state.memberPlan = raw.member_plan || null;
    state.memberExpiresAt = raw.member_expires_at || null;
    updateMemberBadges();
    applyMemberControls();
  }

  function memberText() {
    if (state.member) {
      return memberLabel({
        member: true,
        member_status: state.memberStatus,
        member_expires_at: state.memberExpiresAt
      });
    }
    if (state.memberStatus === "expired") { return "会员已过期：续费后恢复云同步"; }
    return "非会员：云同步是会员功能，开通后可用";
  }

  /** 非会员 / 过期时整块锁住同步区（沿用 .is-member-locked 的禁用态与伪元素提示）。 */
  function applyMemberControls() {
    var memberEl = view.querySelector("[data-role='member']");
    if (memberEl) { memberEl.textContent = memberText(); }
    var area = view.querySelector("[data-role='sync-area']");
    if (!area) { return; }
    var locked = !state.member;
    area.classList.toggle("is-member-locked", locked);
    if (state.memberStatus === "expired") { area.setAttribute("data-lock-reason", "expired"); }
    else { area.removeAttribute("data-lock-reason"); }
    var box = view.querySelector("[data-role='autosync']");
    if (box) { box.disabled = locked; }
    var syncButton = view.querySelector("[data-action='sync']");
    if (syncButton) { syncButton.disabled = locked; }
    var forceButton = view.querySelector("[data-action='force']");
    if (forceButton && locked) { forceButton.hidden = true; }
  }

  function stopAutoSync() {
    if (syncTimer) { clearTimeout(syncTimer); syncTimer = 0; }
  }

  /** 403 membership_required：视同非会员——停自动同步、清会员缓存、刷新面板，不重试。 */
  function handleMembershipRequired(error) {
    stopAutoSync();
    applyMember({ member: false, member_status: (error && error.memberStatus) || "none" });
    notifyMemberChanged();
    if (state.loggedIn) {
      renderAccount(memberText());
    } else {
      setMsg(memberText());
    }
  }

  function afterLogin(result, fallbackEmail) {
    if (state.mode === "login") {
      var remember = state.pendingRemember;
      var autoLogin = state.pendingAutoLogin;
      api("/api/cloud/login-preferences", { method: "POST", body: {
        remember_password: remember, auto_login: autoLogin,
        email: (result && result.email) || fallbackEmail || state.phaseEmail,
        password: remember ? state.password : ""
      } }).catch(function () {});
    }
    state.loggedIn = true;
    state.email = (result && result.email) || fallbackEmail || state.phaseEmail;
    state.password = "";
    state.challenge = "";
    renderAccount("登录成功");
    showLoginNotice(result && result.last_login);
    verifyMe(true);   // 立即核对服务端会员态；新开通的账号登录后无需重启即可同步
    notifyMemberChanged();
    if (state.autoSync && state.member) { syncNow(); }
  }

  function submitCredentials() {
    var email = readEmail();
    var password = readPassword();
    if (!validEmail(email)) { setMsg("请输入有效邮箱", true); return; }
    if (state.mode !== "reset" && !password.trim()) { setMsg("请输入密码", true); return; }
    if (state.sending) { return; }
    state.phaseEmail = email;
    state.password = password;
    if (state.mode === "login") {
      var rememberToggle = view.querySelector("[data-role='remember-password']");
      var autoToggle = view.querySelector("[data-role='auto-login']");
      state.pendingRemember = !!(rememberToggle && rememberToggle.checked) || !!(autoToggle && autoToggle.checked);
      state.pendingAutoLogin = !!(autoToggle && autoToggle.checked);
    }
    busy(true);

    if (state.mode === "reset") {
      setMsg("正在发送重置验证码…");
      api("/api/cloud/password/reset-request", { method: "POST", body: { email: email } })
        .then(function (result) {
          showCodeStep(serverCooldown(result), "重置密码");
          setMsg("如果该邮箱可用，重置验证码已发送；请输入验证码并设置新密码。");
        })
        .catch(function (error) {
          if (error && error.retryAfter) { startCooldown(error.retryAfter); }
          handleError(error);
        })
        .finally(function () { busy(false); });
      return;
    }

    if (state.mode === "register") {
      setMsg("正在创建账号并发送验证码…");
      api("/api/cloud/register", { method: "POST", body: { email: email, password: password } })
        .then(function (result) {
          showCodeStep(serverCooldown(result), codeLabel("register"));
          setMsg("验证码已发送。输入邮件里的 6 位码，完成注册并自动登录。");
        })
        .catch(function (error) {
          if (error && error.retryAfter) { startCooldown(error.retryAfter); }
          handleError(error);
        })
        .finally(function () { busy(false); });
      return;
    }

    // 登录第一段：已识别设备直接进账号；新设备/异常则进入邮箱码步骤
    setMsg("正在验证密码…");
    api("/api/cloud/login", { method: "POST", body: { email: email, password: password } })
      .then(function (result) {
        if (result && result.status === "verification_required") {
          state.challenge = result.challenge || "";
          showCodeStep(serverCooldown(result), codeLabel("login"));
          setMsg((result.message || "需要邮箱验证码确认。") + " 验证码 10 分钟内有效。");
          return;
        }
        afterLogin(result, email);
      })
      .catch(function (error) {
        if (error && error.retryAfter) { startCooldown(error.retryAfter); }
        handleError(error);
      })
      .finally(function () { busy(false); });
  }

  function serverCooldown(result) {
    // 服务端下发真实剩余秒数，不写死 60
    return Math.max(0, Number(result && result.retry_after) || 0);
  }

  function submitCode() {
    var codeInput = view.querySelector("[data-role='code']");
    var code = codeInput ? codeInput.value.replace(/\s+/g, "") : "";
    if (!/^\d{6}$/.test(code)) { setMsg("请输入 6 位数字验证码", true); return; }
    if (!state.phaseEmail) { setMsg("请先输入邮箱和密码", true); return; }
    if (state.sending) { return; }
    busy(true);
    setMsg("正在验证…");

    if (state.mode === "reset") {
      var next = readPassword();
      if (!next.trim()) { busy(false); setMsg("请设置新密码", true); return; }
      api("/api/cloud/password/reset", {
        method: "POST",
        body: { email: state.phaseEmail, code: code, password: next }
      }).then(function () {
        state.mode = "login";
        state.phaseEmail = "";
        state.password = "";
        renderGuest("密码已重置，所有设备已退出登录，请用新密码登录。");
      }).catch(handleError).finally(function () { busy(false); });
      return;
    }

    var path = state.mode === "register" ? "/api/cloud/register/verify" : "/api/cloud/login/verify";
    var body = state.mode === "register"
      ? { email: state.phaseEmail, code: code }
      : { email: state.phaseEmail, code: code, challenge: state.challenge };
    api(path, { method: "POST", body: body }).then(function (result) {
      afterLogin(result, state.phaseEmail);
    }).catch(handleError).finally(function () { busy(false); });
  }

  function resendCode() {
    if (state.sending) { return; }
    busy(true);
    if (state.mode === "register") {
      api("/api/cloud/resend-verification", { method: "POST", body: { email: state.phaseEmail } })
        .then(function (result) { startCooldown(serverCooldown(result)); setMsg("验证码已重新发送。"); })
        .catch(function (error) {
          if (error && error.retryAfter) { startCooldown(error.retryAfter); }
          handleError(error);
        })
        .finally(function () { busy(false); });
      return;
    }
    if (state.mode === "reset") {
      api("/api/cloud/password/reset-request", { method: "POST", body: { email: state.phaseEmail } })
        .then(function (result) { startCooldown(serverCooldown(result)); setMsg("重置验证码已重新发送。"); })
        .catch(function (error) {
          if (error && error.retryAfter) { startCooldown(error.retryAfter); }
          handleError(error);
        })
        .finally(function () { busy(false); });
      return;
    }
    // 登录：重新走第一段（服务端会作废旧码并重发）
    api("/api/cloud/login", {
      method: "POST",
      body: { email: state.phaseEmail, password: state.password }
    }).then(function (result) {
      if (result && result.status === "verification_required") {
        state.challenge = result.challenge || "";
        startCooldown(serverCooldown(result));
        setMsg("新的验证码已发送。");
      } else {
        afterLogin(result, state.phaseEmail);
      }
    }).catch(function (error) {
      if (error && error.retryAfter) { startCooldown(error.retryAfter); }
      handleError(error);
    }).finally(function () { busy(false); });
  }

  function submitCodeOrResend(action) {
    if (action === "resend") { resendCode(); } else { submitCode(); }
  }

  // ---------------------------------------------------------------- 已登录界面

  function renderAccount(message) {
    if (cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = 0; }
    clearNode(view);
    view.innerHTML = [
      '<p class="cloud-title">云账号</p>',
      '<p class="cloud-email" data-role="email"></p>',
      '<p class="cloud-note" data-role="member"></p>',
      '<section class="cloud-sync" data-role="sync-area">',
      '  <p class="cloud-note" data-role="sync-meta"></p>',
      '  <label class="cloud-check"><input type="checkbox" data-role="autosync"> 任务进度变化后自动同步</label>',
      '  <button type="button" class="acc-btn cloud-sync-btn" data-action="sync">立即同步</button>',
      '  <button type="button" class="cloud-link" data-action="force" hidden>冲突：以本地为准</button>',
      '</section>',
      '<div class="cloud-actions">',
      '  <button type="button" class="acc-btn" data-action="logout">退出登录</button>',
      '</div>',
      '<section class="cloud-devices">',
      '  <p class="cloud-section-title">已绑定设备 <span data-role="device-count"></span></p>',
      '  <p class="cloud-note">最多绑定 3 台，同一时刻最多 2 台在线；第 3 台登入会挤掉最早活跃的一台。</p>',
      '  <ul class="cloud-device-list" data-role="device-list">',
      '    <li class="cloud-note">正在读取设备列表…</li>',
      '  </ul>',
      '</section>',
      '<section class="cloud-password-change">',
      '  <p class="cloud-section-title">修改密码</p>',
      '  <p class="cloud-note">验证码会发到当前账号邮箱；修改后所有设备都需要重新登录。</p>',
      '  <button type="button" class="acc-btn" data-action="change-start">发送验证码</button>',
      '  <div data-role="change-box" hidden>',
      '    <label class="cloud-field"><span>新密码</span>',
      '      <div class="cloud-password">',
      '        <input type="password" data-role="new-password" autocomplete="new-password"',
      '               placeholder="设置新密码（仅要求非空）">',
      '        <button type="button" class="cloud-eye" data-action="toggle-new-password" aria-label="显示密码">显示</button>',
      '      </div>',
      '    </label>',
      '    <label class="cloud-field"><span>6 位验证码</span>',
      '      <input type="text" data-role="change-code" inputmode="numeric" maxlength="6"',
      '             autocomplete="one-time-code" placeholder="000000">',
      '    </label>',
      '    <button type="button" class="acc-btn" data-action="change-submit">确认修改</button>',
      '  </div>',
      '</section>',
      '<p class="cloud-msg" data-role="msg" role="status" aria-live="polite"></p>'
    ].join("");
    var emailEl = view.querySelector("[data-role='email']");
    if (emailEl) { emailEl.textContent = state.email || "(未获取到邮箱)"; }
    var box = view.querySelector("[data-role='autosync']");
    if (box) {
      box.checked = state.autoSync;
      box.addEventListener("change", function () {
        state.autoSync = box.checked;
        try { localStorage.setItem(LS_AUTOSYNC, box.checked ? "1" : "0"); } catch (e) { /* ignore */ }
        setMsg(box.checked ? "已开启自动同步（仅在你的任务进度变化后触发）" : "已暂停自动同步");
      });
    }
    applyMemberControls();
    refreshSyncMeta();
    setMsg(message || "");
    loadDevices();
    mountRedeem();
  }

  function loadDevices() {
    api("/api/cloud/devices").then(function (data) {
      renderDeviceList(data);
    }).catch(function (error) {
      var list = view.querySelector("[data-role='device-list']");
      if (list) { list.innerHTML = '<li class="cloud-note">设备列表暂时读取不到，稍后打开面板再试</li>'; }
      if (error && error.status === 401) { handleError(error); }
    });
  }

  function renderDeviceList(data) {
    var list = view.querySelector("[data-role='device-list']");
    if (!list) { return; }
    var devices = (data && data.devices) || [];
    var count = view.querySelector("[data-role='device-count']");
    if (count) {
      count.textContent = devices.length + " / " + ((data && data.max_devices) || 3);
    }
    clearNode(list);
    if (!devices.length) {
      var empty = document.createElement("li");
      empty.className = "cloud-note";
      empty.textContent = "当前没有已绑定的设备";
      list.appendChild(empty);
      return;
    }
    devices.forEach(function (device) {
      var item = document.createElement("li");
      item.className = "cloud-device";
      var meta = [
        "首次绑定 " + formatIso(device.first_seen_at),
        "最后活跃 " + formatIso(device.last_active_at)
      ];
      var extra = [];
      if (device.last_ip) { extra.push("IP " + device.last_ip); }
      if (device.fingerprint) { extra.push("指纹 " + device.fingerprint); }
      item.innerHTML = [
        '<div class="cloud-device-head">',
        '  <span class="cloud-device-name">' + escapeHtml(device.name || "未命名设备") + '</span>',
        device.current ? '  <span class="cloud-device-tag">本机</span>' : "",
        '</div>',
        '<p class="cloud-device-meta">' + escapeHtml(meta.join(" · ")) + '</p>',
        extra.length ? '<p class="cloud-device-meta">' + escapeHtml(extra.join(" · ")) + '</p>' : "",
        '<button type="button" class="cloud-link is-danger" data-action="device-remove"',
        '        data-device="' + escapeHtml(device.device_id) + '">移除</button>'
      ].join("");
      list.appendChild(item);
    });
  }

  function removeDevice(deviceId) {
    if (!deviceId) { return; }
    var confirmed = window.confirm(
      "移除后这台设备需要重新通过邮箱验证才能登录。移除本机会立即退出登录。继续？"
    );
    if (!confirmed) { return; }
    setMsg("正在移除设备…");
    api("/api/cloud/devices/remove", { method: "POST", body: { device_id: deviceId } })
      .then(function (result) {
        if (result && result.current) {
          state.loggedIn = false;
          state.email = "";
          state.sync = {};
          renderGuest("本机已移除，需要重新通过邮箱验证登录");
          return;
        }
        setMsg("已移除该设备");
        loadDevices();
      })
      .catch(handleError);
  }

  function submitChangePassword() {
    var codeEl = view.querySelector("[data-role='change-code']");
    var passwordEl = view.querySelector("[data-role='new-password']");
    var code = codeEl ? codeEl.value.replace(/\s+/g, "") : "";
    var password = passwordEl ? passwordEl.value : "";
    if (!/^\d{6}$/.test(code)) { setMsg("请输入 6 位数字验证码", true); return; }
    if (!password.trim()) { setMsg("请设置新密码", true); return; }
    setMsg("正在修改密码…");
    busy(true);
    api("/api/cloud/password/change", { method: "POST", body: { code: code, password: password } })
      .then(function () {
        state.loggedIn = false;
        state.email = "";
        state.sync = {};
        renderGuest("密码已修改，所有设备已退出登录，请用新密码登录。");
      })
      .catch(handleError)
      .finally(function () { busy(false); });
  }

  function requestChangeCode() {
    setMsg("正在发送验证码…");
    busy(true);
    api("/api/cloud/password/change-request", { method: "POST", body: {} })
      .then(function () {
        var box = view.querySelector("[data-role='change-box']");
        if (box) { box.hidden = false; }
        var btn = view.querySelector("[data-action='change-start']");
        if (btn) { btn.hidden = true; }
        setMsg("验证码已发送到当前账号邮箱，10 分钟内有效。");
      })
      .catch(handleError)
      .finally(function () { busy(false); });
  }

  function refreshSyncMeta(extra) {
    var el = view.querySelector("[data-role='sync-meta']");
    if (!el) { return; }
    var parts = [];
    if (state.sync && state.sync.last_sync_at) {
      parts.push("上次同步 " + formatTime(state.sync.last_sync_at));
    } else {
      parts.push("尚未同步");
    }
    if (state.sync && state.sync.rev) { parts.push("rev " + state.sync.rev); }
    if (extra) { parts.push(extra); }
    el.textContent = parts.join(" · ");
  }

  function logout() {
    api("/api/cloud/logout", { method: "POST", body: {} }).then(function () {
      state.loggedIn = false;
      state.email = "";
      state.sync = {};
      state.autoLogin = false;
      state.rememberPassword = !!state.pendingRemember;
      renderGuest("已退出登录；下次登录需要邮箱验证码。");
      api("/api/cloud/login-preferences").then(function (prefs) {
        state.rememberPassword = !!(prefs && prefs.remember_password);
        state.autoLogin = false;
        renderGuest("已退出登录；下次登录需要邮箱验证码。");
        var emailInput = view.querySelector("[data-role='email']");
        var passwordInput = view.querySelector("[data-role='password']");
        var rememberToggle = view.querySelector("[data-role='remember-password']");
        if (emailInput) { emailInput.value = prefs.email || ""; }
        if (passwordInput) { passwordInput.value = prefs.password || ""; }
        if (rememberToggle) { rememberToggle.checked = state.rememberPassword; }
      }).catch(function () {});
      notifyMemberChanged();
    }).catch(handleError);
  }

  // ---------------------------------------------------------------- 增量同步

  /** R233：读一类本地预设整包。读不到就返回 null，不阻塞任务进度同步，
   *  也绝不拿空数组冒充本地数据去覆盖云端。 */
  function readPresetPack(kind) {
    return api("/api/presets?kind=" + encodeURIComponent(kind)).then(function (pack) {
      if (!pack || !pack.ok || !Array.isArray(pack.presets)) { return null; }
      return JSON.stringify({ schema: PRESET_SYNC_SCHEMA, presets: pack.presets });
    }).catch(function () { return null; });
  }

  /** 全部同步键 → 本地值。预设是异步读的，所以整体返回 Promise。 */
  function collectValues() {
    var values = {};
    var tasks = window.GWTasks;
    if (tasks && typeof tasks.progress === "function") {
      var doc = tasks.progress();
      if (doc && doc.modes) {
        for (var i = 0; i < MODE_KEYS.length; i++) {
          values["progress." + MODE_KEYS[i]] = JSON.stringify(doc.modes[MODE_KEYS[i]] || {});
        }
      }
    }
    presetSyncNote = "";
    return Promise.all(PRESET_KINDS.map(readPresetPack)).then(function (packs) {
      var skipped = [];
      for (var j = 0; j < packs.length; j++) {
        var value = packs[j];
        if (value === null) { continue; }
        if (value.length > PRESET_MAX_CHARS) {
          skipped.push(PRESET_KINDS[j]);
          continue;
        }
        values["preset." + PRESET_KINDS[j]] = value;
      }
      if (skipped.length) {
        presetSyncNote = "预设 " + skipped.join(" / ") +
          " 超过云端单值上限，已跳过（仍完整保存在本地）";
      }
      return Object.keys(values).length ? values : null;
    });
  }

  /** 任务进度部分：保持原有「坏值不覆盖本地」语义。 */
  function applyProgressRemote(remote) {
    var tasks = window.GWTasks;
    if (!remote || !tasks || typeof tasks.importProgress !== "function") { return 0; }
    var doc = tasks.progress();
    if (!doc || !doc.modes) { return 0; }
    var changed = 0;
    Object.keys(remote).forEach(function (key) {
      if (key.indexOf("progress.") !== 0) { return; }
      var mode = key.slice("progress.".length);
      if (MODE_KEYS.indexOf(mode) < 0) { return; }
      try {
        doc.modes[mode] = JSON.parse(remote[key]);
        changed++;
      } catch (e) { /* 坏值不覆盖本地 */ }
    });
    if (changed) {
      applyingRemote = true;
      try {
        tasks.importProgress(JSON.stringify({
          kind: "eftmap-task-progress",
          schema: 1,
          modes: doc.modes,
          exportedAt: new Date().toISOString()
        }));
      } finally {
        setTimeout(function () { applyingRemote = false; }, 1000);
      }
    }
    return changed;
  }

  /** R233：远端预设整包 → POST /api/presets action=replace 写回本地文件。
   *  走后端既有的逐条归一化 + 原子写；写成功才通知页面刷新缓存。 */
  function applyPresetRemote(remote) {
    var jobs = [];
    Object.keys(remote || {}).forEach(function (key) {
      if (key.indexOf("preset.") !== 0) { return; }
      var kind = key.slice("preset.".length);
      if (PRESET_KINDS.indexOf(kind) < 0) { return; }
      var pack;
      try { pack = JSON.parse(remote[key]); } catch (e) { return; }
      if (!pack || pack.schema !== PRESET_SYNC_SCHEMA || !Array.isArray(pack.presets)) { return; }
      jobs.push(api("/api/presets", {
        method: "POST",
        body: { kind: kind, action: "replace", presets: pack.presets }
      }).then(function (res) { return (res && res.ok) ? kind : null; })
        .catch(function () { return null; }));
    });
    return Promise.all(jobs).then(function (kinds) {
      var done = kinds.filter(Boolean);
      done.forEach(function (kind) {
        try {
          window.dispatchEvent(new window.CustomEvent("eftmap:presets-remote-applied",
            { detail: { kind: kind } }));
        } catch (e) { /* 忽略：环境没有 CustomEvent */ }
      });
      return done;
    });
  }

  function applyRemote(remote) {
    var progressChanged = applyProgressRemote(remote);
    return applyPresetRemote(remote).then(function (presets) {
      return { progress: progressChanged, presets: presets };
    });
  }

  function syncNow(force) {
    if (state.syncing || !state.loggedIn || state.syncUnavailable) { return; }
    if (!state.member) { return; }   // 免费版一个 /v1/sync/* 请求都不发
    state.syncing = true;
    setMsg("正在同步…");
    collectValues().then(function (values) {
      if (!values) { setMsg("本地还没有可同步的数据，稍后再试", true); return null; }
      return api("/api/cloud/sync", {
        method: "POST", body: { values: values, force: !!force }
      }).then(function (result) {
        return applyRemote(result.remote).then(function (applied) {
          var parts = [];
          if (result.uploaded) { parts.push("上传 " + result.uploaded + " 项"); }
          if (result.download) { parts.push("下载 " + result.download + " 项"); }
          if (!parts.length) { parts.push("无变化，未占用带宽"); }
          var conflicts = Object.keys(result.conflicts || {}).length;
          if (conflicts) { parts.push("冲突 " + conflicts + " 项（已保留本地）"); }
          if (presetSyncNote) { parts.push(presetSyncNote); }
          setMsg(parts.join(" · "));
          var forceButton = view.querySelector("[data-action='force']");
          if (forceButton) { forceButton.hidden = !conflicts; }
          state.sync = state.sync || {};
          state.sync.rev = result.rev;
          state.sync.last_sync_at = Math.floor(Date.now() / 1000);
          var extras = [];
          if (applied.progress) { extras.push("已应用远端进度"); }
          if (applied.presets.length) {
            extras.push("已写入远端预设 " + applied.presets.join(" / "));
          }
          refreshSyncMeta(extras.join(" · "));
          lastSyncAt = Date.now();
        });
      });
    }).catch(function (error) {
      // 旧版服务端没有 /v1/sync：一次判定后停用自动同步，避免每次存盘都白跑一趟
      if (error && (error.status === 404 || error.status === 501)) {
        state.syncUnavailable = true;
        setMsg("当前云端版本还没有同步接口，本机进度照常保存", true);
        return;
      }
      handleError(error);
    }).finally(function () { state.syncing = false; });
  }

  function scheduleSync() {
    if (!state.loggedIn || !state.member || !state.autoSync ||
        applyingRemote || state.syncUnavailable) { return; }
    if (syncTimer) { clearTimeout(syncTimer); }
    var wait = Math.max(DEBOUNCE_MS, lastSyncAt + MIN_INTERVAL_MS - Date.now());
    syncTimer = setTimeout(function () {
      syncTimer = 0;
      syncNow();
    }, wait);
  }

  // ---------------------------------------------------------------- 状态刷新

  function refreshStatus() {
    api("/api/cloud/status").then(function (data) {
      state.loggedIn = !!data.logged_in;
      state.email = data.email || "";
      state.sync = data.sync || {};
      // 面板一打开就按服务端快照渲染：非会员 / 过期时同步区直接锁住
      applyMember(data && data.member);
      if (state.loggedIn) {
        renderAccount();
        verifyMe();
      } else {
        renderGuest();
        if (!state.autoLoginAttempted) {
          state.autoLoginAttempted = true;
          api("/api/cloud/login-preferences").then(function (prefs) {
            state.rememberPassword = !!(prefs && prefs.remember_password);
            state.autoLogin = !!(prefs && prefs.auto_login);
            renderGuest(state.autoLogin ? "正在使用已保存的账号登录…" : "");
            var emailInput = view.querySelector("[data-role='email']");
            var passwordInput = view.querySelector("[data-role='password']");
            if (emailInput) { emailInput.value = prefs.email || ""; }
            if (passwordInput) { passwordInput.value = state.rememberPassword ? (prefs.password || "") : ""; }
            var rememberToggle = view.querySelector("[data-role='remember-password']");
            var autoToggle = view.querySelector("[data-role='auto-login']");
            if (rememberToggle) { rememberToggle.checked = state.rememberPassword; }
            if (autoToggle) { autoToggle.checked = state.autoLogin; }
            if (state.autoLogin && prefs.email && prefs.password) { submitCredentials(); }
          }).catch(function () {});
        }
      }
    }).catch(function (error) {
      renderGuest(error && error.message ? error.message : "无法读取登录状态");
    });
  }

  function verifyMe(force) {
    // 打开面板时最多每 60 秒核对一次服务端会话；不是轮询
    if (!force && Date.now() - lastMeAt < 60000) { return; }
    var wasLocked = !state.member;
    lastMeAt = Date.now();
    api("/api/cloud/me").then(function (me) {
      applyMember(me);
      var el = view.querySelector("[data-role='sync-meta']");
      if (el && me && me.email) {
        var flags = [me.email_verified ? "邮箱已验证" : "邮箱未验证"];
        flags.push(me.has_password ? "密码已设置" : "未设置密码");
        refreshSyncMeta(flags.join(" · "));
      }
      notifyMemberChanged();
      // 服务端刚确认会员（例如续费后）：无需重启，自动恢复同步
      if (state.member && wasLocked && state.autoSync) { scheduleSync(); }
    }).catch(function (error) {
      if (error && error.status === 401) {
        state.loggedIn = false;
        renderGuest("登录已失效，请重新登录");
      }
    });
  }

  // ---------------------------------------------------------------- 事件绑定

  function togglePassword(action) {
    var selector = action === "toggle-new-password"
      ? "[data-role='new-password']" : "[data-role='password']";
    var input = view.querySelector(selector);
    if (!input) { return; }
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    var button = view.querySelector("[data-action='" + action + "']");
    if (button) {
      button.textContent = show ? "隐藏" : "显示";
      button.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
    }
  }

  view.addEventListener("click", function (event) {
    var tab = event.target.closest ? event.target.closest("[data-mode]") : null;
    if (tab) {
      var mode = tab.getAttribute("data-mode");
      if (mode && mode !== state.mode) { setMode(mode); }
      return;
    }
    var button = event.target.closest ? event.target.closest("[data-action]") : null;
    if (!button) { return; }
    var action = button.getAttribute("data-action");
    if (action === "primary") { submitCredentials(); }
    else if (action === "submit" || action === "resend") { submitCodeOrResend(action); }
    else if (action === "forgot") {
      setMode(state.mode === "reset" ? "login" : "reset");
    }
    else if (action === "toggle-password" || action === "toggle-new-password") {
      togglePassword(action);
    }
    else if (action === "sync") { syncNow(false); }
    else if (action === "force") { syncNow(true); }
    else if (action === "logout") { logout(); }
    else if (action === "device-remove") { removeDevice(button.getAttribute("data-device")); }
    else if (action === "change-start") { requestChangeCode(); }
    else if (action === "change-submit") { submitChangePassword(); }
    else if (action === "redeem-buy") {
      // 用系统默认浏览器购买，登录/支付/验证码都交给爱发电自己处理
      if (state.redeemShopUrl) { window.open(state.redeemShopUrl, "_blank", "noopener"); }
    }
    else if (action === "redeem") { submitRedeem(); }
  });

  view.addEventListener("change", function (event) {
    var role = event.target && event.target.getAttribute
      ? event.target.getAttribute("data-role") : null;
    if (role === "auto-login" && event.target.checked) {
      var remember = view.querySelector("[data-role='remember-password']");
      if (remember) { remember.checked = true; }
    }
  });

  view.addEventListener("input", function (event) {
    var role = event.target && event.target.getAttribute
      ? event.target.getAttribute("data-role") : null;
    if (role === "password") { updateStrength(event.target.value); }
    else if (role === "rd-code") { state.redeemCode = event.target.value; }
  });

  view.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") { return; }
    var role = event.target && event.target.getAttribute ? event.target.getAttribute("data-role") : null;
    if (role === "email" || role === "password") { event.preventDefault(); submitCredentials(); }
    else if (role === "code") { event.preventDefault(); submitCodeOrResend("submit"); }
    else if (role === "change-code" || role === "new-password") {
      event.preventDefault();
      submitChangePassword();
    }
    else if (role === "rd-code") { event.preventDefault(); submitRedeem(); }
  });

  menuButton.addEventListener("click", function () {
    // 菜单的 aria-expanded 可能由另一个监听器在本次点击里才切换，
    // 放到下一个任务再读，避免首开时误判为「已关闭」。
    setTimeout(function () {
      if (menuButton.getAttribute("aria-expanded") === "true") { refreshStatus(); }
    }, 0);
  });

  // 任务进度保存（tasks.js 派发）→ 合并 3 秒后再决定是否同步
  document.addEventListener("gw:progress-saved", scheduleSync);
  // R233：用户保存 / 删除 / 导入预设（app.js 派发）→ 同一套 debounce 触发会员云同步。
  // 免费版在 scheduleSync 里第一行就被挡住，不会发任何云端请求。
  document.addEventListener("gw:presets-saved", scheduleSync);

  var loading = document.getElementById("cloud-loading");
  if (loading) { loading.textContent = "打开面板后才会连接云服务。"; }

  // R273：二级栏的会员到期徽标要常显，不能等用户点开云账号面板才拉状态。
  // /api/member 是本机只读接口（不触发云请求），失败时保持 HTML 里的「会员未开通」。
  function refreshMemberBadge() {
    api("/api/member").then(applyMember).catch(function () { updateMemberBadges(); });
  }
  refreshMemberBadge();
  window.addEventListener("eftmap:member-changed", refreshMemberBadge);
  loadRedeemTiers();
})();
