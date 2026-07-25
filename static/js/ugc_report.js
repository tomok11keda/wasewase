/**
 * UGC 通報: 理由選択 ActionSheet → POST → 成功フィードバック。
 * 投稿・プロフィール・コメント・出品の [data-report-open] を委譲で処理する。
 */
(function (window, document) {
  "use strict";

  var SUCCESS_MESSAGE = "通報しました";
  var SUCCESS_DETAIL = "ご報告ありがとうございました。運営が内容を確認します。";
  var REASONS = [
    { value: "inappropriate", label: "不適切なコンテンツ" },
    { value: "harassment", label: "嫌がらせ" },
    { value: "spam", label: "スパム" },
  ];

  var sheet = null;
  var form = null;
  var reasonInput = null;
  var statusEl = null;
  var actionsEl = null;
  var cancelBtn = null;
  var submitting = false;
  var bound = false;
  var toastTimer = null;

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute("content")) {
      return meta.getAttribute("content");
    }
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) {
      return input.value;
    }
    var match = document.cookie.match(
      /(?:^|; )csrftoken=([^;]*)/
    );
    return match ? decodeURIComponent(match[1]) : "";
  }

  function ensureSheet() {
    if (sheet) return sheet;

    sheet = document.createElement("div");
    sheet.id = "ugc-report-sheet";
    sheet.className = "ugc-modal ugc-report-sheet";
    sheet.hidden = true;
    sheet.setAttribute("aria-hidden", "true");
    sheet.innerHTML =
      '<div class="ugc-modal__backdrop" data-report-close></div>' +
      '<div class="ugc-modal__panel ugc-report-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="ugc-report-sheet-title">' +
      '<p class="ugc-modal__title" id="ugc-report-sheet-title">通報理由を選択</p>' +
      '<p class="ugc-modal__lead">運営が内容を確認します。虚偽の通報はお控えください。</p>' +
      '<form id="ugc-report-sheet-form" method="post" class="ugc-report-sheet__form">' +
      '<input type="hidden" name="csrfmiddlewaretoken" value="">' +
      '<input type="hidden" name="reason" id="ugc-report-sheet-reason" value="">' +
      '<input type="hidden" name="next" id="ugc-report-sheet-next" value="">' +
      '<div class="ugc-report-sheet__actions" id="ugc-report-sheet-actions"></div>' +
      "</form>" +
      '<p class="ugc-report-sheet__status" id="ugc-report-sheet-status" hidden></p>' +
      '<button type="button" class="ugc-report-sheet__cancel" data-report-close>キャンセル</button>' +
      "</div>";

    document.body.appendChild(sheet);
    form = sheet.querySelector("#ugc-report-sheet-form");
    reasonInput = sheet.querySelector("#ugc-report-sheet-reason");
    statusEl = sheet.querySelector("#ugc-report-sheet-status");
    actionsEl = sheet.querySelector("#ugc-report-sheet-actions");
    cancelBtn = sheet.querySelector(".ugc-report-sheet__cancel");

    REASONS.forEach(function (reason) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "ugc-report-sheet__reason";
      button.textContent = reason.label;
      button.setAttribute("data-report-reason", reason.value);
      actionsEl.appendChild(button);
    });

    sheet.addEventListener("click", function (event) {
      if (event.target.closest("[data-report-close]")) {
        event.preventDefault();
        closeSheet(true);
        return;
      }
      var reasonBtn = event.target.closest("[data-report-reason]");
      if (reasonBtn && !submitting) {
        event.preventDefault();
        submitReason(reasonBtn.getAttribute("data-report-reason"));
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sheet && !sheet.hidden) {
        closeSheet(true);
      }
    });

    return sheet;
  }

  function setCsrfToken() {
    var token = getCsrfToken();
    var input = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && token) {
      input.value = token;
    }
    return token;
  }

  function closeProfileSheetIfOpen() {
    var profileSheet = document.getElementById("profile-action-sheet");
    if (!profileSheet || profileSheet.hidden) return;
    profileSheet.hidden = true;
    profileSheet.setAttribute("aria-hidden", "true");
    document.querySelectorAll("[data-profile-more-open]").forEach(function (el) {
      el.setAttribute("aria-expanded", "false");
    });
  }

  function openSheet(trigger) {
    ensureSheet();
    submitting = false;
    var url = trigger.getAttribute("data-report-url") || "";
    if (!url) {
      showToast("通報先を取得できませんでした。ページを再読み込みしてください。", true);
      return;
    }
    setCsrfToken();
    form.action = url;
    reasonInput.value = "";
    var nextInput = sheet.querySelector("#ugc-report-sheet-next");
    if (nextInput) {
      nextInput.value = window.location.pathname + window.location.search;
    }
    statusEl.hidden = true;
    statusEl.textContent = "";
    statusEl.className = "ugc-report-sheet__status";
    actionsEl.hidden = false;
    if (cancelBtn) {
      cancelBtn.hidden = false;
      cancelBtn.textContent = "キャンセル";
    }
    sheet.hidden = false;
    sheet.classList.add("is-open");
    sheet.setAttribute("aria-hidden", "false");
    document.documentElement.classList.add("ugc-report-sheet-open");
  }

  function closeSheet(force) {
    if (!sheet) return;
    if (submitting && !force) return;
    submitting = false;
    sheet.hidden = true;
    sheet.classList.remove("is-open");
    sheet.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("ugc-report-sheet-open");
  }

  function showStatus(message, isError) {
    statusEl.hidden = false;
    statusEl.textContent = message;
    statusEl.className =
      "ugc-report-sheet__status" + (isError ? " is-error" : " is-success");
    actionsEl.hidden = true;
    if (cancelBtn) {
      cancelBtn.textContent = "閉じる";
    }
  }

  function ensureToast() {
    var el = document.getElementById("ugc-report-toast");
    if (el) return el;
    el = document.createElement("div");
    el.id = "ugc-report-toast";
    el.className = "ugc-report-toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.hidden = true;
    document.body.appendChild(el);
    return el;
  }

  function showToast(message, isError) {
    var el = ensureToast();
    el.textContent = message;
    el.classList.toggle("is-error", !!isError);
    el.hidden = false;
    el.classList.add("is-visible");
    if (toastTimer) {
      window.clearTimeout(toastTimer);
    }
    toastTimer = window.setTimeout(function () {
      el.classList.remove("is-visible");
      el.hidden = true;
    }, 2800);
  }

  function parseResponse(response) {
    var contentType = (response.headers.get("content-type") || "").toLowerCase();
    if (contentType.indexOf("application/json") >= 0) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, data: data || {} };
      });
    }
    return response.text().then(function () {
      // HTML リダイレクト等でも 2xx なら成功扱い
      return {
        ok: response.ok,
        status: response.status,
        data: {
          message: response.ok ? SUCCESS_MESSAGE : "通報に失敗しました。もう一度お試しください。",
        },
      };
    });
  }

  function submitReason(reason) {
    if (!form || !form.action || submitting) return;
    submitting = true;
    reasonInput.value = reason || "";
    var token = setCsrfToken();
    if (!token) {
      submitting = false;
      showStatus("セキュリティトークンを取得できませんでした。再読み込みしてください。", true);
      return;
    }

    var body = new FormData(form);
    var headers = {
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
      "X-CSRFToken": token,
    };

    fetch(form.action, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: headers,
    })
      .then(parseResponse)
      .then(function (result) {
        submitting = false;
        var message =
          (result.data && result.data.message) ||
          (result.ok
            ? SUCCESS_MESSAGE
            : "通報に失敗しました。もう一度お試しください。");
        if (result.ok) {
          showStatus(SUCCESS_MESSAGE + "\n" + SUCCESS_DETAIL, false);
          showToast(SUCCESS_MESSAGE, false);
          window.setTimeout(function () {
            closeSheet(true);
          }, 1200);
        } else {
          showStatus(message, true);
          showToast(message, true);
        }
      })
      .catch(function () {
        submitting = false;
        var message = "通報に失敗しました。通信環境をご確認ください。";
        showStatus(message, true);
        showToast(message, true);
      });
  }

  function onReportTriggerClick(event) {
    var trigger = event.target.closest("[data-report-open]");
    if (!trigger) return;

    // プロフィール「…」メニュー内の通報でも確実に拾う
    event.preventDefault();
    event.stopPropagation();

    closeProfileSheetIfOpen();

    // プロフィールシート非表示後に描画する（WKWebView のフォーカス競合回避）
    window.setTimeout(function () {
      openSheet(trigger);
    }, 0);
  }

  function bind() {
    if (bound) return;
    bound = true;
    // capture: 他ハンドラより先に確実に拾う
    document.addEventListener("click", onReportTriggerClick, true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }

  // 外部から再バインド可能に（動的 HTML 差し替え後など）
  window.WaseUgcReport = {
    open: openSheet,
    bind: bind,
  };
})(window, document);
