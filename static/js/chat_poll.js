(function () {
  var POLL_INTERVAL_MS = 15000;
  var area = document.getElementById("message-area");
  if (!area) {
    return;
  }

  var pollUrl = area.dataset.pollUrl;
  if (!pollUrl) {
    return;
  }

  var list = document.getElementById("message-list");
  var emptyEl = document.getElementById("empty-message");
  var input = document.getElementById("message-input");
  var latestId = parseInt(area.dataset.latestId || "0", 10);
  var polling = false;

  function ensureList() {
    if (list) {
      return list;
    }
    if (emptyEl) {
      emptyEl.remove();
      emptyEl = null;
    }
    list = document.createElement("ul");
    list.className = "message-list";
    list.id = "message-list";
    area.appendChild(list);
    return list;
  }

  function createMessageItem(msg) {
    var li = document.createElement("li");
    li.className = "chat-msg" + (msg.is_mine ? " is-mine" : "");
    li.dataset.messageId = String(msg.id);

    var meta = document.createElement("div");
    meta.className = "chat-msg-meta";
    meta.textContent = msg.sender_name + " \u00b7 " + msg.created_at;
    li.appendChild(meta);
    li.appendChild(document.createTextNode(msg.body));

    return li;
  }

  function isNearBottom(el) {
    return el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  }

  function scrollToBottom(el) {
    el.scrollTop = el.scrollHeight;
  }

  function captureInputState() {
    if (!input) {
      return null;
    }
    return {
      hadFocus: document.activeElement === input,
      value: input.value,
      selectionStart: input.selectionStart,
      selectionEnd: input.selectionEnd,
    };
  }

  function restoreInputState(state) {
    if (!input || !state) {
      return;
    }
    if (input.value !== state.value) {
      input.value = state.value;
    }
    if (state.hadFocus) {
      input.focus();
      if (
        typeof state.selectionStart === "number" &&
        typeof state.selectionEnd === "number"
      ) {
        input.setSelectionRange(state.selectionStart, state.selectionEnd);
      }
    }
  }

  function appendMessages(messages) {
    if (!messages.length) {
      return;
    }

    var inputState = captureInputState();
    var ul = ensureList();
    var stickToBottom = isNearBottom(ul);

    messages.forEach(function (msg) {
      if (ul.querySelector('[data-message-id="' + msg.id + '"]')) {
        return;
      }
      ul.appendChild(createMessageItem(msg));
    });

    if (stickToBottom) {
      scrollToBottom(ul);
    }

    restoreInputState(inputState);
  }

  function poll() {
    if (polling || document.hidden) {
      return;
    }

    polling = true;
    var url =
      pollUrl + (pollUrl.indexOf("?") >= 0 ? "&" : "?") + "after=" + latestId;

    fetch(url, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("poll failed");
        }
        return response.json();
      })
      .then(function (data) {
        if (typeof data.latest_id === "number") {
          latestId = data.latest_id;
          area.dataset.latestId = String(latestId);
        }
        if (Array.isArray(data.messages) && data.messages.length) {
          appendMessages(data.messages);
        }
      })
      .catch(function () {})
      .finally(function () {
        polling = false;
      });
  }

  if (list) {
    scrollToBottom(list);
  }

  setInterval(poll, POLL_INTERVAL_MS);
})();
