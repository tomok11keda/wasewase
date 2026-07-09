(function () {
  "use strict";

  var POLL_INTERVAL_MS = 30000;
  var SUMMARY_URL = "/api/dm/unread-summary/";

  function getBadgeElements() {
    return document.querySelectorAll("[data-dm-nav-badge]");
  }

  function formatBadgeCount(count) {
    if (count > 99) {
      return "99+";
    }
    return String(count);
  }

  function renderBadge(count) {
    getBadgeElements().forEach(function (badge) {
      if (count > 0) {
        badge.textContent = formatBadgeCount(count);
        badge.hidden = false;
        badge.setAttribute("aria-label", "未読メッセージ " + count + "件");
      } else {
        badge.textContent = "";
        badge.hidden = true;
        badge.removeAttribute("aria-label");
      }
    });
  }

  async function fetchUnreadCount() {
    var response = await fetch(SUMMARY_URL, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error("dm_unread_summary_failed");
    }
    var data = await response.json();
    return Number(data.total_unread) || 0;
  }

  async function refreshBadge() {
    try {
      var count = await fetchUnreadCount();
      renderBadge(count);
    } catch (error) {
      // ネットワーク障害時は直前の表示を維持する
    }
  }

  function startPolling() {
    refreshBadge();
    window.setInterval(refreshBadge, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        refreshBadge();
      }
    });
    window.addEventListener("pageshow", refreshBadge);
    window.addEventListener("focus", refreshBadge);
    window.addEventListener("wase:push-received", refreshBadge);
  }

  window.WaseDmBadge = {
    refresh: refreshBadge,
  };

  startPolling();
})();
