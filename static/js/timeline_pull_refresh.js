(function () {
  var list = document.getElementById("timeline-list");
  if (!list || !list.dataset.refreshUrl) {
    return;
  }

  var indicator = document.getElementById("timeline-ptr");
  if (!indicator) {
    return;
  }

  var refreshUrl = list.dataset.refreshUrl;
  var threshold = 72;
  var maxPull = 120;
  var startY = 0;
  var pullDistance = 0;
  var pulling = false;
  var refreshing = false;

  function isAtPageTop() {
    return (window.scrollY || document.documentElement.scrollTop || 0) <= 1;
  }

  function setIndicator(distance, state) {
    indicator.classList.toggle("is-visible", distance > 0 || state === "loading");
    indicator.classList.toggle("is-loading", state === "loading");
    indicator.style.setProperty("--ptr-pull", String(Math.min(distance, maxPull)) + "px");
    indicator.setAttribute("aria-hidden", distance > 0 || state === "loading" ? "false" : "true");
  }

  function ensureScrollFooter(hasMore) {
    var sentinel = document.getElementById("timeline-scroll-sentinel");
    var statusEl = document.getElementById("timeline-scroll-status");

    if (hasMore) {
      if (!sentinel) {
        sentinel = document.createElement("div");
        sentinel.id = "timeline-scroll-sentinel";
        sentinel.className = "timeline-scroll-sentinel";
        sentinel.setAttribute("aria-hidden", "true");
        list.appendChild(sentinel);
      }
      if (!statusEl) {
        statusEl = document.createElement("p");
        statusEl.id = "timeline-scroll-status";
        statusEl.className = "empty-message";
        statusEl.setAttribute("aria-live", "polite");
        list.appendChild(statusEl);
      }
    } else {
      if (sentinel) {
        sentinel.remove();
      }
      if (statusEl) {
        statusEl.remove();
      }
    }
  }

  function replaceTimelinePosts(html) {
    var sentinel = document.getElementById("timeline-scroll-sentinel");
    var statusEl = document.getElementById("timeline-scroll-status");

    while (list.firstChild) {
      list.removeChild(list.firstChild);
    }

    var wrapper = document.createElement("div");
    wrapper.innerHTML = html || "";
    while (wrapper.firstChild) {
      list.appendChild(wrapper.firstChild);
    }
  }

  function refreshTimeline() {
    if (refreshing) {
      return;
    }

    refreshing = true;
    setIndicator(maxPull, "loading");

    fetch(refreshUrl, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("timeline refresh failed");
        }
        return response.json();
      })
      .then(function (data) {
        replaceTimelinePosts(data.html);
        list.dataset.nextOffset = String(data.next_offset || 0);
        list.dataset.hasMore = data.has_more ? "true" : "false";
        ensureScrollFooter(Boolean(data.has_more));
        if (typeof window.initTimelineInfiniteScroll === "function") {
          window.initTimelineInfiniteScroll();
        }
      })
      .catch(function () {
        indicator.setAttribute("data-error", "更新に失敗しました");
        indicator.classList.add("is-error");
        window.setTimeout(function () {
          indicator.classList.remove("is-error");
          indicator.removeAttribute("data-error");
        }, 2000);
      })
      .finally(function () {
        refreshing = false;
        pullDistance = 0;
        setIndicator(0, "idle");
      });
  }

  document.addEventListener(
    "touchstart",
    function (event) {
      if (refreshing || event.touches.length !== 1 || !isAtPageTop()) {
        pulling = false;
        return;
      }
      startY = event.touches[0].clientY;
      pullDistance = 0;
      pulling = true;
    },
    { passive: true }
  );

  document.addEventListener(
    "touchmove",
    function (event) {
      if (!pulling || refreshing || event.touches.length !== 1) {
        return;
      }

      if (!isAtPageTop()) {
        pulling = false;
        pullDistance = 0;
        setIndicator(0, "idle");
        return;
      }

      var delta = event.touches[0].clientY - startY;
      if (delta <= 0) {
        pullDistance = 0;
        setIndicator(0, "idle");
        return;
      }

      pullDistance = Math.min(delta, maxPull);
      setIndicator(pullDistance, "pulling");
      if (pullDistance > 8) {
        event.preventDefault();
      }
    },
    { passive: false }
  );

  document.addEventListener(
    "touchend",
    function () {
      if (!pulling || refreshing) {
        return;
      }

      if (pullDistance >= threshold) {
        refreshTimeline();
      } else {
        pullDistance = 0;
        setIndicator(0, "idle");
      }
      pulling = false;
    },
    { passive: true }
  );
})();
