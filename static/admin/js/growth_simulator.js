/**
 * Admin Growth Simulator — client-side what-if math only.
 * Does not POST, persist, call APIs, or change ad budgets.
 *
 * remaining = max(target - current, 0)
 * paid_per_day = daily_ad_spend / cac
 * total_per_day = paid_per_day + organic_per_day
 * exact_days = remaining / total_per_day
 * display_days = ceil(exact_days)
 * estimated_ad_spend = daily_ad_spend * exact_days
 *   (fractional last day; not ceil(days) * daily budget)
 */
(function () {
  "use strict";

  var MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  var MAX_DISPLAY_DAYS = 36500;

  function $(id) {
    return document.getElementById(id);
  }

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function parseISODate(iso) {
    var p = String(iso).split("-");
    return { y: Number(p[0]), m: Number(p[1]), d: Number(p[2]) };
  }

  function isoFromParts(y, m, d) {
    var dt = new Date(Date.UTC(y, m - 1, d));
    return (
      dt.getUTCFullYear() +
      "-" +
      pad(dt.getUTCMonth() + 1) +
      "-" +
      pad(dt.getUTCDate())
    );
  }

  function addDaysISO(iso, days) {
    var p = parseISODate(iso);
    return isoFromParts(p.y, p.m, p.d + days);
  }

  function formatLongDate(iso) {
    var p = parseISODate(iso);
    return MONTHS[p.m - 1] + " " + p.d + ", " + p.y;
  }

  function daysBetweenISO(fromISO, toISO) {
    var a = parseISODate(fromISO);
    var b = parseISODate(toISO);
    return Math.round(
      (Date.UTC(b.y, b.m - 1, b.d) - Date.UTC(a.y, a.m - 1, a.d)) / 86400000
    );
  }

  function formatInt(n) {
    return Math.round(n).toLocaleString("en-US");
  }

  function formatYen(n) {
    return "¥" + formatInt(n);
  }

  function formatRate(n) {
    return (Math.round(n * 10) / 10).toFixed(1);
  }

  function finiteNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function readNumber(el, fallback) {
    if (!el) return fallback;
    var v = parseFloat(String(el.value).replace(/,/g, ""));
    return finiteNumber(v) ? v : NaN;
  }

  function simulate(input) {
    var current = input.current;
    var target = input.target;
    var cac = input.cac;
    var spend = input.dailyAdSpend;
    var organic = input.organicPerDay;

    if (!finiteNumber(target) || target <= 0) {
      return { ok: false, error: "invalid_input" };
    }
    if (!finiteNumber(cac) || cac <= 0) {
      return { ok: false, error: "invalid_input" };
    }
    if (!finiteNumber(spend) || spend < 0) {
      return { ok: false, error: "invalid_input" };
    }
    if (!finiteNumber(organic) || organic < 0) {
      return { ok: false, error: "invalid_input" };
    }

    var remaining = Math.max(target - current, 0);
    var paidPerDay = spend / cac;
    var totalPerDay = paidPerDay + organic;

    if (remaining === 0) {
      return {
        ok: true,
        status: "already_reached",
        remaining: 0,
        paidPerDay: paidPerDay,
        organicPerDay: organic,
        totalPerDay: totalPerDay,
        exactDays: 0,
        displayDays: 0,
        arrivalISO: input.today,
        adSpend: 0,
      };
    }

    if (totalPerDay <= 0) {
      return {
        ok: true,
        status: "no_growth",
        remaining: remaining,
        paidPerDay: paidPerDay,
        organicPerDay: organic,
        totalPerDay: 0,
        exactDays: null,
        displayDays: null,
        arrivalISO: null,
        adSpend: 0,
      };
    }

    var exactDays = remaining / totalPerDay;
    var displayDays = Math.ceil(exactDays - 1e-12);
    if (displayDays < 0 || !isFinite(displayDays)) {
      return { ok: false, error: "invalid_input" };
    }
    var arrivalISO = null;
    if (displayDays <= MAX_DISPLAY_DAYS) {
      arrivalISO = addDaysISO(input.today, displayDays);
    }
    return {
      ok: true,
      status: "ok",
      remaining: remaining,
      paidPerDay: paidPerDay,
      organicPerDay: organic,
      totalPerDay: totalPerDay,
      exactDays: exactDays,
      displayDays: displayDays,
      arrivalISO: arrivalISO,
      adSpend: spend * exactDays,
    };
  }

  function deadlineResult(arrivalISO, monthEndISO) {
    if (!arrivalISO || !monthEndISO) return null;
    if (arrivalISO < monthEndISO) return "before";
    if (arrivalISO === monthEndISO) return "on";
    return "after";
  }

  function projectMonths(current, totalPerDay, today, goals) {
    var todayParts = parseISODate(today);
    var currentKey = todayParts.y * 100 + todayParts.m;
    var rows = [];
    for (var i = 0; i < goals.length; i++) {
      var g = goals[i];
      var key = g.year * 100 + g.month;
      if (key < currentKey) continue;
      var days = Math.max(0, daysBetweenISO(today, g.month_end));
      var projected = current + totalPerDay * days;
      rows.push({
        label: MONTHS[g.month - 1].slice(0, 3) + " " + g.year,
        goal: g.target,
        projected: projected,
        difference: projected - g.target,
      });
    }
    return rows;
  }

  function selectedGoal(selectEl, goals) {
    var val = selectEl.value;
    if (val === "custom") return null;
    var target = Number(val);
    for (var i = 0; i < goals.length; i++) {
      if (goals[i].target === target) return goals[i];
    }
    return null;
  }

  function setText(id, text) {
    var el = $(id);
    if (el) el.textContent = text;
  }

  function show(id, visible) {
    var el = $(id);
    if (!el) return;
    el.hidden = !visible;
  }

  function render(data) {
    var current = data.current_users;
    var today = data.today;
    var goals = data.goals || [];
    var targetSelect = $("growth-sim-target");
    var customWrap = $("growth-sim-custom-wrap");
    var customInput = $("growth-sim-custom");
    var cacInput = $("growth-sim-cac");
    var spendInput = $("growth-sim-spend");
    var organicInput = $("growth-sim-organic");
    var cacSlider = $("growth-sim-cac-slider");
    var spendSlider = $("growth-sim-spend-slider");

    var goal = selectedGoal(targetSelect, goals);
    show("growth-sim-custom-wrap", targetSelect.value === "custom");

    var target =
      targetSelect.value === "custom"
        ? readNumber(customInput, NaN)
        : Number(targetSelect.value);

    var cac = readNumber(cacInput, NaN);
    var spend = readNumber(spendInput, NaN);
    var organic = readNumber(organicInput, NaN);

    if (cacSlider && finiteNumber(cac) && cac >= 50 && cac <= 500) {
      cacSlider.value = String(cac);
    }
    if (spendSlider && finiteNumber(spend) && spend >= 0 && spend <= 20000) {
      spendSlider.value = String(spend);
    }

    setText("growth-sim-current", formatInt(current));
    setText(
      "growth-sim-target-out",
      finiteNumber(target) ? formatInt(target) : "—"
    );

    var result = simulate({
      current: current,
      target: target,
      cac: cac,
      dailyAdSpend: spend,
      organicPerDay: organic,
      today: today,
    });

    if (!result.ok) {
      show("growth-sim-ok", false);
      show("growth-sim-message", true);
      setText(
        "growth-sim-message",
        "Enter a valid CAC (≥ ¥1), non-negative daily ad spend, and non-negative organic users / day."
      );
      show("growth-sim-deadline", false);
    } else if (result.status === "already_reached") {
      show("growth-sim-ok", true);
      show("growth-sim-message", true);
      setText("growth-sim-message", "Target already reached");
      setText("growth-sim-remaining", "0");
      setText("growth-sim-paid", formatRate(result.paidPerDay) + " / day");
      setText("growth-sim-organic-out", formatRate(result.organicPerDay) + " / day");
      setText("growth-sim-total", formatRate(result.totalPerDay) + " / day");
      setText("growth-sim-days", "0 days");
      setText("growth-sim-arrival", formatLongDate(today));
      setText("growth-sim-spend-out", "¥0");
      show("growth-sim-deadline", false);
    } else if (result.status === "no_growth") {
      show("growth-sim-ok", true);
      show("growth-sim-message", true);
      setText("growth-sim-message", "No growth under current assumptions");
      setText("growth-sim-remaining", formatInt(result.remaining));
      setText("growth-sim-paid", "0.0 / day");
      setText("growth-sim-organic-out", "0.0 / day");
      setText("growth-sim-total", "0.0 / day");
      setText("growth-sim-days", "—");
      setText("growth-sim-arrival", "—");
      setText("growth-sim-spend-out", "¥0");
      show("growth-sim-deadline", false);
    } else {
      show("growth-sim-ok", true);
      setText("growth-sim-message", "");
      show("growth-sim-message", false);
      setText("growth-sim-remaining", formatInt(result.remaining));
      setText("growth-sim-paid", formatRate(result.paidPerDay) + " / day");
      setText("growth-sim-organic-out", formatRate(result.organicPerDay) + " / day");
      setText("growth-sim-total", formatRate(result.totalPerDay) + " / day");
      if (result.arrivalISO) {
        setText("growth-sim-days", formatInt(result.displayDays) + " days");
        setText("growth-sim-arrival", formatLongDate(result.arrivalISO));
      } else {
        setText("growth-sim-days", "More than 100 years");
        setText("growth-sim-arrival", "—");
      }
      setText("growth-sim-spend-out", formatYen(result.adSpend));

      if (goal && result.arrivalISO) {
        var cmp = deadlineResult(result.arrivalISO, goal.month_end);
        show("growth-sim-deadline", true);
        setText("growth-sim-deadline-target", goal.label);
        setText("growth-sim-deadline-arrival", formatLongDate(result.arrivalISO));
        setText("growth-sim-deadline-end", formatLongDate(goal.month_end));
        var label =
          cmp === "before"
            ? "Projected before target month-end"
            : cmp === "on"
              ? "On month-end target"
              : "Projected after target month-end";
        setText("growth-sim-deadline-result", label);
      } else {
        show("growth-sim-deadline", false);
      }
    }

    var eomBody = $("growth-sim-eom-body");
    if (!eomBody) return;
    while (eomBody.firstChild) {
      eomBody.removeChild(eomBody.firstChild);
    }
    var totalForProj =
      result.ok && result.status !== "invalid_input" ? result.totalPerDay : 0;
    if (!finiteNumber(totalForProj) || result.status === "no_growth") {
      totalForProj = 0;
    }
    var rows = projectMonths(current, totalForProj || 0, today, goals);
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r];
      var tr = document.createElement("tr");
      var diff = row.difference;
      var diffText = (diff >= 0 ? "+" : "") + formatInt(diff);
      var cells = [row.label, formatInt(row.goal), formatInt(row.projected), diffText];
      for (var c = 0; c < cells.length; c++) {
        var td = document.createElement("td");
        td.textContent = cells[c];
        tr.appendChild(td);
      }
      eomBody.appendChild(tr);
    }
  }

  function applyDefaults(data) {
    var defaults = data.defaults || {};
    var targetSelect = $("growth-sim-target");
    var customInput = $("growth-sim-custom");
    var defaultTarget = defaults.target;
    var matched = false;
    if (defaultTarget != null) {
      for (var i = 0; i < targetSelect.options.length; i++) {
        if (Number(targetSelect.options[i].value) === defaultTarget) {
          targetSelect.selectedIndex = i;
          matched = true;
          break;
        }
      }
    }
    if (!matched) {
      targetSelect.value = "custom";
      customInput.value = defaultTarget != null ? String(defaultTarget) : "";
    }
    $("growth-sim-cac").value = String(defaults.cac);
    $("growth-sim-spend").value = String(defaults.daily_ad_spend);
    $("growth-sim-organic").value = String(defaults.organic_per_day);
    var cacSlider = $("growth-sim-cac-slider");
    var spendSlider = $("growth-sim-spend-slider");
    if (cacSlider) cacSlider.value = String(defaults.cac);
    if (spendSlider) spendSlider.value = String(defaults.daily_ad_spend);
  }

  function init() {
    var node = $("growth-simulator-data");
    if (!node) return;
    var data;
    try {
      data = JSON.parse(node.textContent);
    } catch (err) {
      return;
    }
    if (!data) return;

    applyDefaults(data);

    var form = $("growth-simulator-form");
    if (!form) return;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
    });

    ["change", "input"].forEach(function (evt) {
      form.addEventListener(evt, function () {
        render(data);
      });
    });

    var cacSliderEl = $("growth-sim-cac-slider");
    var spendSliderEl = $("growth-sim-spend-slider");
    var resetEl = $("growth-sim-reset");
    if (cacSliderEl) {
      cacSliderEl.addEventListener("input", function () {
        $("growth-sim-cac").value = cacSliderEl.value;
        render(data);
      });
    }
    if (spendSliderEl) {
      spendSliderEl.addEventListener("input", function () {
        $("growth-sim-spend").value = spendSliderEl.value;
        render(data);
      });
    }
    if (resetEl) {
      resetEl.addEventListener("click", function () {
        applyDefaults(data);
        render(data);
      });
    }

    render(data);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
