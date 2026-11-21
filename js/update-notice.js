/* 启动时检查 GitHub 最新正式版；失败或离线不影响应用使用。 */
(function () {
  "use strict";

  if (new URLSearchParams(window.location.search).get("mini") === "1") { return; }
  var modal = document.getElementById("update-notice");
  if (!modal) { return; }
  var previousFocus = null;

  function close() {
    modal.hidden = true;
    if (previousFocus && typeof previousFocus.focus === "function") { previousFocus.focus(); }
  }

  function safeGithubUrl(value) {
    try {
      var url = new URL(value);
      return url.protocol === "https:" && url.hostname === "github.com" ? url.href : "";
    } catch (error) { return ""; }
  }

  function addNote(container, raw) {
    var line = String(raw || "").replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/, "").trim();
    if (!line) { return; }
    var paragraph = document.createElement("p");
    paragraph.textContent = line;
    container.appendChild(paragraph);
  }

  function sizeLabel(bytes) {
    var size = Number(bytes) || 0;
    return size > 0 ? " · " + (size / (1024 * 1024)).toFixed(1) + " MB" : "";
  }

  function show(data) {
    if (!data || !data.available || !data.latest_version) { return; }
    var title = document.getElementById("update-title");
    var version = document.getElementById("update-version-line");
    var notes = document.getElementById("update-notes");
    var downloads = document.getElementById("update-downloads");
    var releasePage = document.getElementById("update-release-page");
    if (!title || !version || !notes || !downloads || !releasePage) { return; }

    title.textContent = data.release_name || ("EFT 互动地图 " + data.latest_version);
    version.textContent = "当前 " + (data.current_version || "未知") + " → " + data.latest_version;
    notes.replaceChildren();
    String(data.notes || "此版本暂无更新说明。").split(/\r?\n/).forEach(function (line) {
      addNote(notes, line);
    });
    if (!notes.childElementCount) { addNote(notes, "此版本暂无更新说明。"); }

    downloads.replaceChildren();
    (Array.isArray(data.assets) ? data.assets : []).forEach(function (asset) {
      var href = safeGithubUrl(asset && asset.url);
      if (!href) { return; }
      var link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "下载 " + (asset.name || "更新包") + sizeLabel(asset.size);
      downloads.appendChild(link);
    });
    var releaseHref = safeGithubUrl(data.release_url);
    releasePage.href = releaseHref || "https://github.com/jjingith/eft-interactive-map/releases";
    previousFocus = document.activeElement;
    modal.hidden = false;
    var closeButton = modal.querySelector("[data-update-close]");
    if (closeButton) { closeButton.focus(); }
  }

  modal.addEventListener("click", function (event) {
    if (event.target === modal || (event.target.closest && event.target.closest("[data-update-close]"))) {
      close();
    }
  });
  document.addEventListener("keydown", function (event) {
    if (!modal.hidden && event.key === "Escape") {
      event.preventDefault();
      close();
    }
  });

  fetch("/api/update-check", { cache: "no-store" })
    .then(function (response) { return response.ok ? response.json() : null; })
    .then(show)
    .catch(function () { /* 离线时不弹错误，也不阻塞地图。 */ });
})();
