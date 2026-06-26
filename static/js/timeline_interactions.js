(function () {
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-toggle-comments]");
    if (!button) {
      return;
    }
    var main = button.closest(".tweet-main");
    if (!main) {
      return;
    }
    var details = main.querySelector(".timeline-comments");
    if (!details) {
      return;
    }
    details.open = !details.open;
    button.setAttribute("aria-expanded", details.open ? "true" : "false");
    if (details.open) {
      var input = details.querySelector(".comment-form input");
      if (input) {
        input.focus();
      }
    }
  });

  if (location.hash && location.hash.indexOf("#post-") === 0) {
    var target = document.querySelector(location.hash);
    if (target) {
      requestAnimationFrame(function () {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("tweet-card--highlight");
        setTimeout(function () {
          target.classList.remove("tweet-card--highlight");
        }, 2000);
      });
    }
  }
})();
