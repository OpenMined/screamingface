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
    return total.toLocaleString();
  }
  function formatDate(value) {
    if (!value) return EM_DASH;
    var d = new Date(value);
    if (isNaN(d.getTime())) return EM_DASH;
    return d.toLocaleString(undefined, {
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
    return count.toLocaleString() + " " + (count === 1 ? singular : plural);
  }

  /* ---- badges & deep links -------------------------------------------- */
  // Returns a green "Verified" pill only when verified_by_openmined === true;
  // otherwise an empty text node (no badge — absence means unverified).
  function createVerifiedBadge(isVerified) {
    if (isVerified === true) return el("span", "badge-verified", "✓ Verified");
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
  function createRunLink(specId, expression, opts) {
    opts = opts || {};
    var a = link((opts.compact ? "run-link compact" : "run-link"), buildRunHref(specId, expression), opts.label || "Run Locally");
    a.setAttribute("aria-label", "Run " + specId + " locally in ScreamingFace");
    return a;
  }

  /* ---- ready ----------------------------------------------------------- */
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  /* ---- index page ------------------------------------------------------ */
  function benchmarkCard(b) {
    var card = el("article", "card");
    card.appendChild(el("h2", "card-title", b.display_name || b.id));
    card.appendChild(el("p", "card-id mono", b.id));

    if (b.description) {
      card.appendChild(el("p", "card-meta", b.description));
    } else {
      card.appendChild(el("p", "card-meta empty", "No description."));
    }

    var links = el("div", "card-links");
    links.appendChild(link("", "benchmark.html?id=" + encodeURIComponent(b.id), "View leaderboard →"));
    // dataset_url is API-provided/untrusted: only render it when it is a real
    // http(s) URL, so a javascript:/data: scheme can never reach the href.
    var datasetHref = httpUrlOrNull(b.dataset_url);
    if (datasetHref) {
      var dataset = link("", datasetHref, "Dataset");
      dataset.setAttribute("rel", "noopener noreferrer nofollow");
      links.appendChild(dataset);
    }
    card.appendChild(links);
    return card;
  }

  function updateBenchmarkCount(count) {
    var countNode = document.getElementById("benchmark-count");
    var labelNode = document.getElementById("benchmark-count-label");
    if (!countNode || !labelNode) return;
    countNode.textContent = String(count);
    labelNode.textContent = count === 1 ? "benchmark indexed" : "benchmarks indexed";
  }

  function initIndex() {
    var statusNode = document.getElementById("benchmark-status");
    var listNode = document.getElementById("benchmark-list");
    showLoading(statusNode, "Loading benchmarks…");
    listNode.hidden = true;

    fetchJson("/v1/benchmarks").then(
      function (data) {
        var benchmarks = (data && data.benchmarks) || [];
        updateBenchmarkCount(benchmarks.length);
        if (benchmarks.length === 0) {
          showEmpty(statusNode, "No public benchmarks yet. The API is live; rows will appear here as soon as benchmark specs are registered.");
          return;
        }
        clear(listNode);
        benchmarks.forEach(function (b) { listNode.appendChild(benchmarkCard(b)); });
        setStatus(statusNode, null);
        listNode.hidden = false;
      },
      function (err) {
        showError(statusNode, describeError(err, { generic: "Could not load benchmarks — try again later." }));
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
    createRunLink: createRunLink,
    ready: ready,
    EM_DASH: EM_DASH,
  };

  // Self-bootstrap the index page when its container is present. benchmark.html
  // and spec.html have no #benchmark-list, so this is a no-op there.
  ready(function () {
    if (document.getElementById("benchmark-list")) initIndex();
  });

  return api;
})();
