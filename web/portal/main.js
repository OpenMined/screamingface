/* ScreamingFace Leaderboard Portal — shared utilities + index page.
 *
 * One global namespace, no modules/build tooling. `main.js` owns generic
 * fetching/formatting/DOM/badge/deep-link helpers (the "port" that
 * `benchmark.js` and `spec.js` depend on) plus the index-page rendering.
 *
 * Security posture: every value that originates from the API is community
 * submitted and therefore untrusted. It is written to the DOM exclusively via
 * textContent / createTextNode and attribute setters — never innerHTML — so a
 * malicious spec_id / url4_expression / submitter cannot inject markup.
 */
window.ScorePortal = (function () {
  "use strict";

  var EM_DASH = "—";
  var PORTAL_LOCALE = "en-US";

  /* ---- API base resolution -------------------------------------------- */
  // 1. Build-time injection (deployed asset sets window.SCOREBOARD_API_BASE
  //    via an inline script before main.js loads — handled by D-SCORE-007).
  // 2. Local dev fallback.
  function getApiBase() {
    if (window.SCOREBOARD_API_BASE) {
      return String(window.SCOREBOARD_API_BASE).replace(/\/$/, "");
    }
    return "http://localhost:9106";
  }

  /* ---- fetch ----------------------------------------------------------- */
  // Throws an Error carrying `.status` (0 for network/parse failures) so each
  // page can map it to a specific user-facing message.
  function fetchJson(path) {
    var url = getApiBase() + path;
    return fetch(url, { headers: { Accept: "application/json" } }).then(
      function (response) {
        if (!response.ok) {
          var err = new Error("Request failed with status " + response.status);
          err.status = response.status;
          return response
            .text()
            .catch(function () { return ""; })
            .then(function (body) {
              err.body = body;
              throw err;
            });
        }
        return response.text().then(function (body) {
          if (!body) return null;
          try {
            return JSON.parse(body);
          } catch (e) {
            var perr = new Error("Invalid JSON response");
            perr.status = 0;
            throw perr;
          }
        });
      },
      function (networkErr) {
        var err = new Error(networkErr && networkErr.message ? networkErr.message : "Network error");
        err.status = 0;
        throw err;
      }
    );
  }

  /* ---- query params ---------------------------------------------------- */
  function getParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }
  function requireParam(name) {
    var value = getParam(name);
    if (value === null || value === "") {
      var err = new Error("Missing required query parameter: " + name);
      err.missingParam = name;
      throw err;
    }
    return value;
  }

  /* ---- DOM helpers ----------------------------------------------------- */
  function clear(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  // Create an element with an optional class and text content (text only).
  function el(tag, className, textValue) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (textValue !== undefined && textValue !== null) {
      node.textContent = String(textValue);
    }
    return node;
  }
  function link(className, href, label) {
    var a = document.createElement("a");
    if (className) a.className = className;
    a.setAttribute("href", href);
    a.textContent = String(label);
    return a;
  }
  // Returns a normalized http(s) URL string, or null for anything else.
  // Untrusted, API-provided absolute URLs (e.g. a benchmark's dataset_url) must
  // pass through this before becoming an anchor href, so a javascript:, data:,
  // or vbscript: URL can never be made clickable. Our own links are either
  // relative (…html?…, "/") or the hardcoded sf://run scheme, and do not use
  // this — only externally-sourced absolute URLs do.
  function httpUrlOrNull(value) {
    if (!value) return null;
    try {
      var u = new URL(String(value), window.location.href);
      return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
    } catch (e) {
      return null;
    }
  }

  /* ---- status / loading / error / empty -------------------------------- */
  // A status region is a single element that toggles between loading/error/
  // empty states. Passing kind === null hides it (data is ready to show).
  function setStatus(node, kind, message) {
    if (!node) return;
    if (kind === null) {
      node.hidden = true;
      node.className = "state";
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.className = "state state-" + kind;
    node.textContent = message;
    node.setAttribute("role", kind === "error" ? "alert" : "status");
  }
  function showLoading(node, message) { setStatus(node, "loading", message || "Loading…"); }
  function showError(node, message) { setStatus(node, "error", message || "Something went wrong."); }
  function showEmpty(node, message) { setStatus(node, "empty", message || "Nothing here yet."); }

  // Translate a fetch error into a page-appropriate message.
  function describeError(err, opts) {
    opts = opts || {};
    if (err && err.missingParam) return opts.missingParam || ("Missing “" + err.missingParam + "”.");
    if (err && err.status === 404) return opts.notFound || "Not found.";
    return opts.generic || "Could not load — try again later.";
  }

  /* ---- formatters ------------------------------------------------------ */
  function formatPercent(value) {
    if (typeof value !== "number" || isNaN(value)) return EM_DASH;
    return (value * 100).toFixed(1) + "%";
  }
  function formatQuestions(total) {
    if (typeof total !== "number" || isNaN(total)) return EM_DASH;
    return total.toLocaleString(PORTAL_LOCALE);
  }
  function formatDate(value) {
    if (!value) return EM_DASH;
    var d = new Date(value);
    if (isNaN(d.getTime())) return EM_DASH;
    return d.toLocaleString(PORTAL_LOCALE, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }
  function formatProviders(list) {
    if (!Array.isArray(list) || list.length === 0) return EM_DASH;
    return list.join(", ");
  }
  // Privacy note: a null submitter renders as an em dash. Never "Anonymous" —
  // let the absence speak for itself.
  function formatSubmitter(value) {
    if (value === null || value === undefined || value === "") return EM_DASH;
    return String(value);
  }
  function formatCount(value, singular, plural) {
    var count = typeof value === "number" && !isNaN(value) ? value : 0;
    return count.toLocaleString(PORTAL_LOCALE) + " " + (count === 1 ? singular : plural);
  }

  /* ---- badges & deep links -------------------------------------------- */
  // Returns a square gain-colored "verified" mark only when
  // verified_by_openmined === true; otherwise an em dash (no badge —
  // absence means unverified).
  function createVerifiedBadge(isVerified) {
    if (isVerified === true) return el("span", "badge-verified", "✓ verified");
    return document.createTextNode(EM_DASH);
  }
  // sf://run?spec=...&expression=... with each value URL-encoded separately.
  // Never concatenate a raw url4_expression — it can contain / ( ) ! $.
  function buildRunHref(specId, expression) {
    return (
      "sf://run?spec=" + encodeURIComponent(specId) +
      "&expression=" + encodeURIComponent(expression)
    );
  }
  // Copy-to-clipboard button for the sf://run link. A button (not an sf://
  // anchor) so it works in any browser regardless of whether the protocol
  // handler is registered; the copied URI still opens screamingface locally.
  function createCopyButton(specId, expression, opts) {
    opts = opts || {};
    var label = opts.label || "Copy";
    var btn = el("button", opts.compact ? "btn ghost" : "btn", label);
    btn.type = "button";
    btn.setAttribute("aria-label", "Copy the local run link for " + specId);
    btn.addEventListener("click", function () {
      function done(ok) {
        btn.textContent = ok ? "✓ copied" : "copy failed";
        setTimeout(function () { btn.textContent = label; }, 1600);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(buildRunHref(specId, expression)).then(
          function () { done(true); },
          function () { done(false); }
        );
      } else {
        done(false);
      }
    });
    return btn;
  }

  /* ---- ready ----------------------------------------------------------- */
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  /* ---- live index page -------------------------------------------------- */
  var LIVE_BENCHMARK_ID = "livetruth";

  function setLiveStatus(message, kind) {
    var node = document.getElementById("live-status");
    if (!node) return;
    node.className = "note" + (kind === "gain" ? " gain" : "");
    node.textContent = "";
    node.appendChild(el("span", "kicker", kind === "error" ? "scoreboard" : "live · scoreboard"));
    node.appendChild(document.createTextNode(message));
  }

  function liveFillWidth(accuracy) {
    if (typeof accuracy !== "number" || isNaN(accuracy)) return "0%";
    var pct = Math.max(0, Math.min(100, accuracy * 100));
    return (pct.toFixed(1) + "%").replace(".0%", "%");
  }

  function renderLiveChart(entries) {
    var node = document.getElementById("live-chart");
    if (!node) return;
    clear(node);
    entries.forEach(function (entry, index) {
      var row = el("div", "row");
      row.appendChild(el("span", "lbl", entry.spec_id));
      var track = el("span", "track");
      var fill = el("span", "fill " + (index === 0 ? "sota" : "ens"));
      fill.style.width = liveFillWidth(entry.accuracy);
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "val", formatPercent(entry.accuracy)));
      node.appendChild(row);
    });
  }

  function liveRunLink(entry) {
    if (!entry.url4_expression) return document.createTextNode(EM_DASH);
    return link("btn ghost", buildRunHref(entry.spec_id, entry.url4_expression), "▸ run");
  }

  function renderLiveTable(entries) {
    var host = document.getElementById("live-table");
    if (!host) return;
    clear(host);

    var table = document.createElement("table");
    table.setAttribute("aria-label", "LiveTruth leaderboard");
    var thead = document.createElement("thead");
    var headRow = document.createElement("tr");
    ["#", "configuration", "accuracy", "questions", "verified", ""].forEach(function (label, index) {
      headRow.appendChild(el("th", (index === 2 || index === 3) ? "num" : null, label));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    entries.forEach(function (entry, index) {
      var rank = typeof entry.rank === "number" ? entry.rank : index + 1;
      var tr = document.createElement("tr");
      if (rank === 1) tr.className = "sota";
      tr.appendChild(el("td", null, rank));
      var specTd = el("td", "cell-wrap", entry.spec_id);
      if (rank === 1) specTd.appendChild(el("span", "sr-only", " (state of the art)"));
      tr.appendChild(specTd);
      tr.appendChild(el("td", "num", formatPercent(entry.accuracy)));
      tr.appendChild(el("td", "num", formatQuestions(entry.total_questions)));
      tr.appendChild(el("td", null, entry.verified_by_openmined ? "✓ OpenMined" : EM_DASH));
      var runTd = document.createElement("td");
      runTd.appendChild(liveRunLink(entry));
      tr.appendChild(runTd);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    host.appendChild(table);
  }

  // Site-root data files (published by the deploy workflow) open in the
  // in-portal viewer instead of forcing a download — GitHub Pages serves
  // .jsonl as application/octet-stream with no MIME override available.
  function publishedDataFileName(href) {
    try {
      var u = new URL(href);
      if (u.hostname !== "screamingface.ai") return null;
      var m = u.pathname.match(/^\/([A-Za-z0-9][A-Za-z0-9._-]*\.jsonl)$/);
      return m ? m[1] : null;
    } catch (e) {
      return null;
    }
  }

  function benchmarkRow(b) {
    var tr = document.createElement("tr");
    tr.appendChild(el("td", null, b.display_name || b.id));
    tr.appendChild(el("td", "mono", b.id));
    tr.appendChild(el("td", "cell-wrap", b.description ? b.description : EM_DASH));

    // dataset_url is API-provided/untrusted: only render it when it is a real
    // http(s) URL, so a javascript:/data: scheme can never reach the href.
    var datasetTd = el("td");
    var datasetHref = httpUrlOrNull(b.dataset_url);
    if (datasetHref) {
      var viewerName = publishedDataFileName(datasetHref);
      if (viewerName) {
        datasetTd.appendChild(link("", "data.html?file=" + encodeURIComponent(viewerName), "Dataset"));
      } else {
        var dataset = link("", datasetHref, "Dataset");
        dataset.setAttribute("rel", "noopener noreferrer nofollow");
        datasetTd.appendChild(dataset);
      }
    } else {
      datasetTd.textContent = EM_DASH;
    }
    tr.appendChild(datasetTd);

    var lbTd = el("td");
    lbTd.appendChild(link("", "benchmark.html?id=" + encodeURIComponent(b.id), "Leaderboard →"));
    tr.appendChild(lbTd);
    return tr;
  }

  function initBenchmarkDirectory() {
    var statusNode = document.getElementById("benchmark-status");
    var listNode = document.getElementById("benchmark-list");
    var wrapNode = document.getElementById("benchmark-table-wrap");
    if (!statusNode || !listNode || !wrapNode) return;
    showLoading(statusNode, "Loading benchmarks…");
    wrapNode.hidden = true;

    fetchJson("/v1/benchmarks").then(
      function (data) {
        var benchmarks = (data && data.benchmarks) || [];
        if (benchmarks.length === 0) {
          showEmpty(statusNode, "No public benchmarks yet.");
          return;
        }
        clear(listNode);
        benchmarks.forEach(function (b) { listNode.appendChild(benchmarkRow(b)); });
        setStatus(statusNode, null);
        wrapNode.hidden = false;
      },
      function (err) {
        showError(statusNode, describeError(err, { generic: "Could not load benchmarks — try again later." }));
      }
    );
  }

  function initLiveIndex() {
    setLiveStatus("Fetching the latest runs…");
    fetchJson("/v1/leaderboard/" + encodeURIComponent(LIVE_BENCHMARK_ID) + "?top=50").then(
      function (data) {
        var entries = (data && data.entries) || [];
        if (entries.length === 0) {
          setLiveStatus("The scoreboard is live, but no runs are published for this benchmark yet.");
          return;
        }
        var best = Math.max.apply(null, entries.map(function (entry) { return entry.accuracy || 0; }));
        var now = new Date().toLocaleString(PORTAL_LOCALE, {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
        setLiveStatus(
          entries.length + " run" + (entries.length === 1 ? "" : "s") +
          " on LiveTruth · best " + formatPercent(best) +
          " · fetched " + now + " from scoreboard.screamingface.ai",
          "gain"
        );
        renderLiveChart(entries);
        renderLiveTable(entries);
      },
      function (err) {
        setLiveStatus(
          "Could not reach the scoreboard (" +
          (err && err.message ? err.message : "network") +
          "). It may be waking up — try a refresh.",
          "error"
        );
      }
    );
  }

  /* ---- public surface -------------------------------------------------- */
  var api = {
    getApiBase: getApiBase,
    fetchJson: fetchJson,
    getParam: getParam,
    requireParam: requireParam,
    clear: clear,
    el: el,
    link: link,
    httpUrlOrNull: httpUrlOrNull,
    setStatus: setStatus,
    showLoading: showLoading,
    showError: showError,
    showEmpty: showEmpty,
    describeError: describeError,
    formatPercent: formatPercent,
    formatQuestions: formatQuestions,
    formatDate: formatDate,
    formatProviders: formatProviders,
    formatSubmitter: formatSubmitter,
    formatCount: formatCount,
    createVerifiedBadge: createVerifiedBadge,
    buildRunHref: buildRunHref,
    createCopyButton: createCopyButton,
    ready: ready,
    EM_DASH: EM_DASH,
  };

  // Self-bootstrap the live index page when its container is present.
  ready(function () {
    if (document.getElementById("live-table")) initLiveIndex();
    if (document.getElementById("benchmark-list")) initBenchmarkDirectory();
  });

  return api;
})();
