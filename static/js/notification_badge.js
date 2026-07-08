(function () {
  "use strict";

  var POLL_INTERVAL_MS = 60000;
  var COUNT_URL = "/api/notifications/unread-count/";
  var MARK_READ_URL = "/api/notifications/mark-read/";

  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function isNotificationsPage() {
    return (
      window.WASE_MARK_NOTIFICATIONS_READ === true ||
      window.location.pathname === "/notifications/" ||
      window.location.pathname === "/notifications"
    );
  }

  function getBadgeElements() {
    return document.querySelectorAll("[data-notification-badge]");
  }

  function formatBadgeCount(count) {
    if (count > 99) {
      return "99+";
    }
    return String(count);
  }

  function renderBadge(count) {
    var badges = getBadgeElements();
    badges.forEach(function (badge) {
      if (count > 0) {
        badge.textContent = formatBadgeCount(count);
        badge.hidden = false;
        badge.setAttribute("aria-label", "未読通知 " + count + "件");
      } else {
        badge.textContent = "";
        badge.hidden = true;
        badge.removeAttribute("aria-label");
      }
    });
  }

  async function fetchUnreadCount() {
    var response = await fetch(COUNT_URL, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error("unread_count_failed");
    }
    var data = await response.json();
    return Number(data.unread_count) || 0;
  }

  async function refreshBadge() {
    try {
      var count = await fetchUnreadCount();
      renderBadge(count);
    } catch (error) {
      // ネットワーク障害時は直前の表示を維持する
    }
  }

  async function markAllRead() {
    renderBadge(0);
    try {
      await fetch(MARK_READ_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
      });
    } catch (error) {
      // サーバー側でも既読化しているため、失敗時は次回ポーリングで同期
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

  window.WaseNotifications = {
    refresh: refreshBadge,
    markAllRead: markAllRead,
  };

  if (isNotificationsPage()) {
    markAllRead();
    window.addEventListener("wase:push-received", refreshBadge);
  } else {
    startPolling();
  }
})();
