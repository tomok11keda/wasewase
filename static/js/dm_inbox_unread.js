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

  function updateBadge(item, unreadCount) {
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
    var unreadDm = {};
    var unreadGroup = {};
    (payload.rooms || []).forEach(function (room) {
      var count = Number(room.unread_count) || 0;
      if (room.kind === "group") {
        unreadGroup[String(room.room_pk)] = count;
      } else {
        unreadDm[String(room.room_pk)] = count;
      }
    });

    root.querySelectorAll(".dm-inbox-item[data-dm-room-pk]").forEach(function (item) {
      var roomPk = item.getAttribute("data-dm-room-pk");
      if (roomPk) {
        updateBadge(item, unreadDm[roomPk] || 0);
      }
    });

    root.querySelectorAll(".dm-inbox-item[data-group-room-pk]").forEach(function (item) {
      var roomPk = item.getAttribute("data-group-room-pk");
      if (roomPk) {
        updateBadge(item, unreadGroup[roomPk] || 0);
      }
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
