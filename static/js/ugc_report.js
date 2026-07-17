/**
 * UGC 通報: 即時送信せず、理由選択の ActionSheet を表示してから POST する。
 */
(function (window, document) {
  "use strict";

  var SUCCESS_MESSAGE = "ご報告ありがとうございました";
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
  var submitting = false;

  function getCookie(name) {
    var match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
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
        closeSheet();
        return;
      }
      var reasonBtn = event.target.closest("[data-report-reason]");
      if (reasonBtn && !submitting) {
        submitReason(reasonBtn.getAttribute("data-report-reason"));
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sheet && !sheet.hidden) {
        closeSheet();
      }
    });

    return sheet;
  }

  function setCsrfToken() {
    var token = getCookie("csrftoken");
    var input = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && token) {
      input.value = token;
    }
  }

  function openSheet(trigger) {
    ensureSheet();
    submitting = false;
    setCsrfToken();
    form.action = trigger.getAttribute("data-report-url") || "";
    reasonInput.value = "";
    var nextInput = sheet.querySelector("#ugc-report-sheet-next");
    if (nextInput) {
      nextInput.value = window.location.pathname + window.location.search;
    }
    statusEl.hidden = true;
    statusEl.textContent = "";
    statusEl.className = "ugc-report-sheet__status";
    actionsEl.hidden = false;
    sheet.querySelector(".ugc-report-sheet__cancel").hidden = false;
    sheet.hidden = false;
    sheet.setAttribute("aria-hidden", "false");
    document.documentElement.classList.add("ugc-report-sheet-open");
  }

  function closeSheet() {
    if (!sheet || submitting) return;
    sheet.hidden = true;
    sheet.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("ugc-report-sheet-open");
  }

  function showStatus(message, isError) {
    statusEl.hidden = false;
    statusEl.textContent = message;
    statusEl.className =
      "ugc-report-sheet__status" + (isError ? " is-error" : " is-success");
    actionsEl.hidden = true;
    sheet.querySelector(".ugc-report-sheet__cancel").textContent = "閉じる";
  }

  function submitReason(reason) {
    if (!form || !form.action || submitting) return;
    submitting = true;
    reasonInput.value = reason;
    setCsrfToken();

    var body = new FormData(form);
    fetch(form.action, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data || {} };
        });
      })
      .then(function (result) {
        submitting = false;
        var message =
          (result.data && result.data.message) ||
          (result.ok ? SUCCESS_MESSAGE : "通報に失敗しました。もう一度お試しください。");
        if (result.ok) {
          showStatus(SUCCESS_MESSAGE, false);
          window.setTimeout(function () {
            submitting = false;
            closeSheet();
          }, 1400);
        } else {
          showStatus(message, true);
        }
      })
      .catch(function () {
        submitting = false;
        showStatus("通報に失敗しました。通信環境をご確認ください。", true);
      });
  }

  document.addEventListener(
    "click",
    function (event) {
      var trigger = event.target.closest("[data-report-open]");
      if (!trigger) return;
      event.preventDefault();
      event.stopPropagation();

      // プロフィールの「…」シートが開いていれば先に閉じる
      var profileSheet = document.getElementById("profile-action-sheet");
      if (profileSheet && !profileSheet.hidden) {
        profileSheet.hidden = true;
        profileSheet.setAttribute("aria-hidden", "true");
        var moreTrigger = document.getElementById("profile-more-trigger");
        if (moreTrigger) moreTrigger.setAttribute("aria-expanded", "false");
      }

      openSheet(trigger);
    },
    true
  );
})(window, document);
