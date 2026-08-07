(function () {
  "use strict";

  function loginUrlWithNext() {
    var next = window.location.pathname + window.location.search;
    return "/login/?next=" + encodeURIComponent(next || "/");
  }

  function openLoginRequiredDialog() {
    var dialog = document.getElementById("login-required-dialog");
    var link = document.getElementById("login-required-login-link");
    if (link) {
      link.setAttribute("href", loginUrlWithNext());
    }
    if (dialog && typeof dialog.showModal === "function") {
      if (!dialog.open) {
        dialog.showModal();
      }
      return;
    }
    window.location.href = loginUrlWithNext();
  }

  document.addEventListener(
    "click",
    function (event) {
      var target = event.target;
      if (!target || !target.closest) {
        return;
      }
      var trigger = target.closest("[data-requires-login]");
      if (!trigger) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      openLoginRequiredDialog();
    },
    true
  );

  window.waseOpenLoginRequired = openLoginRequiredDialog;
})();
