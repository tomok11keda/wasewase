/**
 * Wire classic ImagePickWidget buttons to the hidden file input.
 * Sets data-image-source so Capacitor can open camera vs photos.
 */
(function () {
  function findInput(fromEl) {
    var root = fromEl.closest(".image-pick-field");
    if (!root) return null;
    return root.querySelector('input[type="file"].image-pick__native');
  }

  document.addEventListener(
    "click",
    function (event) {
      var btn = event.target.closest("[data-image-pick-source]");
      if (!btn || btn.disabled) return;
      var input = findInput(btn);
      if (!input || input.disabled) return;

      event.preventDefault();
      var source = (btn.getAttribute("data-image-pick-source") || "").toLowerCase();
      if (source === "camera") {
        input.setAttribute("capture", "environment");
        input.setAttribute("data-image-source", "camera");
      } else {
        input.removeAttribute("capture");
        input.setAttribute("data-image-source", "photos");
      }
      input.click();
    },
    false
  );

  document.addEventListener(
    "change",
    function (event) {
      var input = event.target;
      if (
        !input ||
        !input.matches ||
        !input.matches('input[type="file"].image-pick__native')
      ) {
        return;
      }
      var root = input.closest(".image-pick-field");
      if (!root) return;
      var nameEl = root.querySelector("[data-image-pick-filename]");
      if (!nameEl) return;
      var file = input.files && input.files[0];
      if (file) {
        nameEl.textContent = file.name;
        nameEl.hidden = false;
      } else {
        nameEl.textContent = "";
        nameEl.hidden = true;
      }
    },
    false
  );
})();
