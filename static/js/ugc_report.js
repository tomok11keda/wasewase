(function () {
  "use strict";

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function openModal(modal, targetType, targetId) {
    var form = modal.querySelector("#ugc-report-form");
    var success = modal.querySelector("#ugc-report-success");
    var error = modal.querySelector("#ugc-report-error");
    modal.querySelector("#ugc-report-target-type").value = targetType;
    modal.querySelector("#ugc-report-target-id").value = String(targetId);
    form.reset();
    modal.querySelector("#ugc-report-target-type").value = targetType;
    modal.querySelector("#ugc-report-target-id").value = String(targetId);
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
    form.hidden = false;
    success.hidden = true;
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
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var error = modal.querySelector("#ugc-report-error");
      var success = modal.querySelector("#ugc-report-success");
      var submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;

      fetch(form.action, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: new FormData(form),
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          if (!result.ok && !result.data.ok) {
            throw new Error(
              (result.data && (result.data.message || JSON.stringify(result.data.errors))) ||
                "通報に失敗しました。"
            );
          }
          form.hidden = true;
          success.hidden = false;
          success.querySelector(".ugc-report-success__message").textContent =
            result.data.message || "通報を受け付けました。";
        })
        .catch(function (err) {
          error.hidden = false;
          error.textContent = err.message || "通報に失敗しました。時間をおいて再度お試しください。";
        })
        .finally(function () {
          submitBtn.disabled = false;
        });
    });
  });
})();
