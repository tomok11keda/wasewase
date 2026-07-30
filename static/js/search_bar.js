/**
 * 共通 SearchBar: Enter / 虫眼鏡で /api/search/ を呼び出し、結果を表示する。
 * 親へは CustomEvent "wase:search" でクエリを渡す。
 */
(function (window, document) {
  "use strict";

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function findRoot(form) {
    var root = form.closest("[data-search-root]");
    if (root) {
      return root;
    }
    return form.parentElement;
  }

  function setLoading(form, panel, statusEl, isLoading) {
    form.classList.toggle("is-loading", isLoading);
    var submit = form.querySelector("[data-search-submit]");
    if (submit) {
      submit.disabled = isLoading;
    }
    if (!panel || !statusEl) {
      return;
    }
    if (isLoading) {
      panel.hidden = false;
      statusEl.hidden = false;
      statusEl.className = "wase-search-status is-loading";
      statusEl.textContent = "検索中…";
    }
  }

  function showDefaultContent(root, show) {
    if (!root) {
      return;
    }
    root.querySelectorAll("[data-search-default-content]").forEach(function (el) {
      el.hidden = !show;
    });
  }

  function renderResults(panel, statusEl, listEl, payload) {
    var results = (payload && payload.results) || [];
    var count = Number(payload && payload.count) || results.length;
    var q = (payload && payload.q) || "";

    panel.hidden = false;
    listEl.innerHTML = "";

    if (!q) {
      panel.hidden = true;
      return;
    }

    if (!count) {
      statusEl.hidden = false;
      statusEl.className = "wase-search-status is-empty";
      statusEl.textContent = "該当する結果がありませんでした";
      return;
    }

    statusEl.hidden = false;
    statusEl.className = "wase-search-status";
    statusEl.textContent = "「" + q + "」の検索結果（" + count + "件）";

    results.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "wase-search-result";
      var metaHtml = item.meta
        ? '<p class="wase-search-result__meta">' + escapeHtml(item.meta) + "</p>"
        : "";
      li.innerHTML =
        '<a href="' +
        escapeHtml(item.url || "#") +
        '">' +
        '<p class="wase-search-result__title">' +
        escapeHtml(item.title || "") +
        "</p>" +
        '<p class="wase-search-result__subtitle">' +
        escapeHtml(item.subtitle || "") +
        "</p>" +
        metaHtml +
        "</a>";
      listEl.appendChild(li);
    });
  }

  async function runSearch(form) {
    var input = form.querySelector("[data-search-input]");
    var root = findRoot(form);
    var panel = root ? root.querySelector("[data-search-panel]") : null;
    var statusEl = root ? root.querySelector("[data-search-status]") : null;
    var listEl = root ? root.querySelector("[data-search-results]") : null;
    if (!input || !panel || !statusEl || !listEl) {
      return;
    }

    var q = (input.value || "").trim();
    var scope = form.getAttribute("data-search-scope") || "home";
    var faculty = form.getAttribute("data-search-faculty") || "";
    var apiUrl = form.getAttribute("data-search-api") || "/api/search/";

    form.dispatchEvent(
      new CustomEvent("wase:search", {
        bubbles: true,
        detail: { q: q, scope: scope, faculty: faculty },
      })
    );

    if (!q) {
      panel.hidden = true;
      listEl.innerHTML = "";
      showDefaultContent(root, true);
      return;
    }

    showDefaultContent(root, false);
    setLoading(form, panel, statusEl, true);
    listEl.innerHTML = "";

    var params = new URLSearchParams();
    params.set("q", q);
    params.set("scope", scope);
    if (faculty) {
      params.set("faculty", faculty);
    }

    try {
      var response = await fetch(apiUrl + "?" + params.toString(), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error("search_failed");
      }
      var payload = await response.json();
      renderResults(panel, statusEl, listEl, payload);
      showDefaultContent(root, false);
    } catch (error) {
      panel.hidden = false;
      statusEl.hidden = false;
      statusEl.className = "wase-search-status is-empty";
      statusEl.textContent = "検索に失敗しました。時間をおいて再度お試しください。";
      listEl.innerHTML = "";
    } finally {
      form.classList.remove("is-loading");
      var submit = form.querySelector("[data-search-submit]");
      if (submit) {
        submit.disabled = false;
      }
    }
  }

  function bindForm(form) {
    if (form.getAttribute("data-search-bound") === "1") {
      return;
    }
    form.setAttribute("data-search-bound", "1");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      runSearch(form);
    });
  }

  function init() {
    document.querySelectorAll("[data-search-bar]").forEach(bindForm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.WaseSearchBar = { init: init, runSearch: runSearch };
})(window, document);
