(function () {
  "use strict";

  function openModal(modal, targetType, targetId) {
    var form = modal.querySelector("#ugc-report-form");
    var error = modal.querySelector("#ugc-report-error");
    var nextInput = modal.querySelector("#ugc-report-next");
    modal.querySelector("#ugc-report-target-type").value = targetType;
    modal.querySelector("#ugc-report-target-id").value = String(targetId);
    form.reset();
    modal.querySelector("#ugc-report-target-type").value = targetType;
    modal.querySelector("#ugc-report-target-id").value = String(targetId);
    if (nextInput) {
      nextInput.value = window.location.pathname + window.location.search;
    }
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeModal(modal) {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var modal = document.getElementById("ugc-report-modal");
    if (!modal) {
      return;
    }

    document.addEventListener("click", function (event) {
      var trigger = event.target.closest("[data-ugc-report]");
      if (!trigger) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      var targetType = trigger.getAttribute("data-report-type");
      var targetId = trigger.getAttribute("data-report-id");
      if (!targetType || !targetId) {
        return;
      }
      openModal(modal, targetType, targetId);
    });

    modal.querySelectorAll("[data-ugc-modal-close]").forEach(function (el) {
      el.addEventListener("click", function () {
        closeModal(modal);
      });
    });

    var form = modal.querySelector("#ugc-report-form");
    if (!form) {
      return;
    }

    form.addEventListener("submit", function (event) {
      var reason = form.querySelector('input[name="reason"]:checked');
      var error = modal.querySelector("#ugc-report-error");
      if (!reason) {
        event.preventDefault();
        if (error) {
          error.hidden = false;
          error.textContent = "通報理由を選択してください。";
        }
        return;
      }
      var submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "送信中…";
      }
    });
  });
})();
