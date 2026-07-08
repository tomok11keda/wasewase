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

  function createAvatar(msg) {
    var avatar = document.createElement("div");
    avatar.className = "chat-row__avatar";

    if (msg.avatar_url) {
      var img = document.createElement("img");
      img.className = "user-avatar user-avatar--image";
      img.src = msg.avatar_url;
      img.alt = msg.sender_name || "";
      img.width = 26;
      img.height = 26;
      img.loading = "lazy";
      avatar.appendChild(img);
      return avatar;
    }

    var initial = document.createElement("span");
    initial.className = "user-avatar user-avatar--initial";
    initial.setAttribute("aria-hidden", "true");
    initial.textContent = msg.sender_initial || "?";
    avatar.appendChild(initial);
    return avatar;
  }

  function createMessageItem(msg) {
    var li = document.createElement("li");
    li.className = "chat-row" + (msg.is_mine ? " is-mine" : "");
    li.dataset.messageId = String(msg.id);

    li.appendChild(createAvatar(msg));

    var main = document.createElement("div");
    main.className = "chat-row__main";

    var bubble = document.createElement("div");
    bubble.className = "chat-row__bubble";
    bubble.textContent = msg.body;
    main.appendChild(bubble);

    var time = document.createElement("time");
    time.className = "chat-row__time";
    time.textContent = msg.created_at;
    main.appendChild(time);

    li.appendChild(main);
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
