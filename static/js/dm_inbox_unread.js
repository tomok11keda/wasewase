(function () {
  "use strict";

  var POLL_INTERVAL_MS = 30000;
  var root = document.querySelector("[data-dm-inbox]");
  if (!root) {
    return;
  }

  var summaryUrl = root.dataset.dmUnreadUrl;
  if (!summaryUrl) {
    return;
  }

  function formatCount(count) {
    if (count > 99) {
      return "99+";
    }
    return String(count);
  }

  function updateRow(roomPk, unreadCount) {
    var item = root.querySelector('[data-dm-room-pk="' + roomPk + '"]');
    if (!item) {
      return;
    }

    var badge = item.querySelector("[data-dm-unread-badge]");
    item.classList.toggle("has-unread", unreadCount > 0);

    if (!badge) {
      return;
    }

    if (unreadCount > 0) {
      badge.textContent = formatCount(unreadCount);
      badge.hidden = false;
      badge.setAttribute("aria-label", "未読 " + unreadCount + "件");
    } else {
      badge.textContent = "";
      badge.hidden = true;
      badge.removeAttribute("aria-label");
    }
  }

  function applySummary(payload) {
    var unreadByRoom = {};
    (payload.rooms || []).forEach(function (room) {
      unreadByRoom[String(room.room_pk)] = Number(room.unread_count) || 0;
    });

    root.querySelectorAll("[data-dm-room-pk]").forEach(function (item) {
      var roomPk = item.getAttribute("data-dm-room-pk");
      updateRow(roomPk, unreadByRoom[roomPk] || 0);
    });
  }

  function refreshUnreadSummary() {
    return fetch(summaryUrl, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("dm_unread_summary_failed");
        }
        return response.json();
      })
      .then(applySummary)
      .catch(function () {});
  }

  refreshUnreadSummary();
  window.setInterval(refreshUnreadSummary, POLL_INTERVAL_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      refreshUnreadSummary();
    }
  });
  window.addEventListener("pageshow", refreshUnreadSummary);
  window.addEventListener("wase:push-received", refreshUnreadSummary);
})();
