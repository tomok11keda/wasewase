(function () {
  var list = document.getElementById("timeline-list");
  if (!list || list.dataset.hasMore !== "true") {
    return;
  }

  var sentinel = document.getElementById("timeline-scroll-sentinel");
  var statusEl = document.getElementById("timeline-scroll-status");
  var feedUrl = list.dataset.feedUrl;
  var offset = parseInt(list.dataset.nextOffset || "0", 10);
  var loading = false;
  var hasMore = true;

  function setStatus(message) {
    if (statusEl) {
      statusEl.textContent = message || "";
    }
  }

  function appendPosts(html) {
    if (!html) {
      return;
    }
    var wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    while (wrapper.firstChild) {
      if (sentinel && sentinel.parentNode === list) {
        list.insertBefore(wrapper.firstChild, sentinel);
      } else {
        list.appendChild(wrapper.firstChild);
      }
    }
  }

  function loadMore() {
    if (loading || !hasMore) {
      return;
    }

    loading = true;
    setStatus("読み込み中...");

    var url = new URL(feedUrl, window.location.origin);
    url.searchParams.set("offset", String(offset));

    fetch(url.toString(), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("timeline feed failed");
        }
        return response.json();
      })
      .then(function (data) {
        appendPosts(data.html);
        offset = data.next_offset || offset;
        hasMore = Boolean(data.has_more);
        list.dataset.nextOffset = String(offset);
        list.dataset.hasMore = hasMore ? "true" : "false";
        if (!hasMore) {
          setStatus("");
          if (sentinel) {
            sentinel.remove();
          }
        } else {
          setStatus("");
        }
      })
      .catch(function () {
        setStatus("投稿の読み込みに失敗しました。");
      })
      .finally(function () {
        loading = false;
      });
  }

  if (!sentinel || !("IntersectionObserver" in window)) {
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          loadMore();
        }
      });
    },
    { root: null, rootMargin: "240px 0px", threshold: 0 }
  );

  observer.observe(sentinel);
})();
