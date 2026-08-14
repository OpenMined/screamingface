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
  // 1. Explicit override for local smoke tests or alternate deployments.
  // 2. Same-origin when served by the scoreboard app.
  // 3. Local dev fallback for file:// usage.
  function getApiBase() {
    if (window.SCOREBOARD_API_BASE) {
      return String(window.SCOREBOARD_API_BASE).replace(/\/$/, "");
    }
    if (window.location.protocol === "http:" || window.location.protocol === "https:") {
      return window.location.origin;
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
  // or vbscript: URL can never be made clickable. Our own links are relative
  // (…html?…, "/") and do not use this — only externally-sourced absolute
  // URLs do.
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
  //
  // AIDEV-NOTE: NOTHING CALLS THIS as of OME-820. verified_by_openmined now defaults to
  // true for every submission, as a placeholder that asserts nothing — no service
  // re-runs submissions (OME-414) and nothing attests where a run executed. A badge on
  // 100% of rows is not a trust signal, so the benchmark board, the spec history and the
  // "Verified rows" stat all dropped it rather than relabel it. Kept, unused and
  // deliberately untouched, because OME-821 restores the distinction and will want this
  // back. Do not re-wire it before then.
  function createVerifiedBadge(isVerified) {
    if (isVerified === true) return el("span", "badge-verified", "✓ verified");
    return document.createTextNode(EM_DASH);
  }
  // Copy-to-clipboard button that places the RAW url4_expression on the
  // clipboard — the exact string pasted into the desktop app's Eval Studio
  // "URL4 expression" field. We copy it verbatim (no encoding, no sf://run
  // wrapper): a url4 spec can contain / ( ) ! $ # : and must survive intact.
  function createCopyButton(specId, expression, opts) {
    opts = opts || {};
    var label = opts.label || "Copy";
    var btn = el("button", opts.compact ? "btn ghost" : "btn", label);
    btn.type = "button";
    btn.setAttribute("aria-label", "Copy the URL4 expression for " + specId);
    btn.addEventListener("click", function () {
      function done(ok) {
        btn.textContent = ok ? "✓ copied" : "copy failed";
        setTimeout(function () { btn.textContent = label; }, 1600);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(expression).then(
          function () { done(true); },
          function () { done(false); }
        );
      } else {
        done(false);
      }
    });
    return btn;
  }

  /* ---- benchmark tab strip (shared by benchmark.html) ------------------ */
  // Renders whatever the catalog actually returns — never hardcodes specific
  // benchmark ids (spec OME-768 D6).
  function renderTabStrip(container, benchmarks, activeId) {
    if (!container) return;
    clear(container);
    benchmarks.forEach(function (b) {
      var a = link(null, "benchmark.html?id=" + encodeURIComponent(b.id), b.display_name || b.id);
      if (b.id === activeId) a.setAttribute("aria-current", "page");
      container.appendChild(a);
    });
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
  // Site-root data files (published by the deploy workflow) open in the
  // in-portal viewer instead of forcing a download — GitHub Pages serves
  // .jsonl as application/octet-stream with no MIME override available.
  function publishedDataFileName(href) {
    try {
      var u = new URL(href);
      if (u.hostname !== "scoreboard.screamingface.ai") return null;
      var m = u.pathname.match(/^\/([A-Za-z0-9][A-Za-z0-9._-]*\.jsonl)$/);
      if (!m) return null;
      return ["livetruth-latest.jsonl", "livetruth-masking.dataset.jsonl"].indexOf(m[1]) === -1 ? null : m[1];
    } catch (e) {
      return null;
    }
  }

  // "Subtitle" isn't an explicit field on Benchmark — using `description`
  // provisionally (flagged to Irina on OME-768; easy to swap if she says
  // otherwise, this is the one place it's read).
  function benchmarkSubtitle(b) {
    return b.description || null;
  }

  function benchmarkRow(b, submissionCount) {
    var tr = document.createElement("tr");

    var nameTd = el("td", "cell-wrap");
    nameTd.appendChild(el("div", null, b.display_name || b.id));
    var subtitle = benchmarkSubtitle(b);
    if (subtitle) nameTd.appendChild(el("div", "faint", subtitle));
    nameTd.appendChild(el("span", "mono faint", b.id));
    tr.appendChild(nameTd);

    tr.appendChild(el("td", "num mono", typeof submissionCount === "number" ? submissionCount.toLocaleString(PORTAL_LOCALE) : EM_DASH));

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

  function formatDateOnly(value) {
    if (!value) return EM_DASH;
    var d = new Date(value);
    if (isNaN(d.getTime())) return EM_DASH;
    return d.toLocaleDateString(PORTAL_LOCALE, { year: "numeric", month: "short", day: "numeric" });
  }

  function updateIndexStats(benchmarks) {
    var counts = {
      "stat-benchmarks": String(benchmarks.length),
      "stat-datasets": String(benchmarks.filter(function (b) { return httpUrlOrNull(b.dataset_url) !== null; }).length),
      "stat-newest": formatDateOnly(
        benchmarks.map(function (b) { return b.created_at; }).filter(Boolean).sort().pop()
      ),
    };
    Object.keys(counts).forEach(function (id) {
      var node = document.getElementById(id);
      if (node) node.textContent = counts[id];
    });
  }

  // D11: no aggregate "submission count" endpoint exists yet (OME-772). One
  // extra fetch per benchmark is an acceptable N+1 at today's benchmark count
  // (a handful) — revisit if the catalog grows past that. `/v1/leaderboard`
  // returns best-per-spec entries (not every raw submission), so this reads
  // as a fusion/spec count, matching OME-769's own "fusion count" term — the
  // closest honest proxy for "# submissions" without a dedicated endpoint.
  // top=200 is the route's own MAX_LEADERBOARD_TOP — the true ceiling, not a
  // number picked here.
  function fetchSubmissionCount(benchmarkId) {
    return fetchJson("/v1/leaderboard/" + encodeURIComponent(benchmarkId) + "?top=200").then(
      function (data) { return (data && data.entries && data.entries.length) || 0; },
      function () { return null; } // count unknown, not zero — row still renders
    );
  }

  function initIndex() {
    var statusNode = document.getElementById("benchmark-status");
    var listNode = document.getElementById("benchmark-list");
    var wrapNode = document.getElementById("benchmark-table-wrap");
    showLoading(statusNode, "Loading benchmarks…");
    wrapNode.hidden = true;

    fetchJson("/v1/benchmarks").then(
      function (data) {
        var benchmarks = (data && data.benchmarks) || [];
        updateIndexStats(benchmarks);
        if (benchmarks.length === 0) {
          showEmpty(statusNode, "No public benchmarks yet. The API is live; rows will appear here as soon as benchmark specs are registered.");
          return;
        }
        return Promise.all(benchmarks.map(function (b) { return fetchSubmissionCount(b.id); })).then(
          function (counts) {
            clear(listNode);
            benchmarks.forEach(function (b, i) { listNode.appendChild(benchmarkRow(b, counts[i])); });
            setStatus(statusNode, null);
            wrapNode.hidden = false;
          }
        );
      },
      function (err) {
        showError(statusNode, describeError(err, { generic: "Could not load benchmarks — try again later." }));
      }
    ).catch(function (err) {
      // WHY: the handler above is the second argument to the *first* `.then`, so it
      // only sees a `/v1/benchmarks` rejection. Anything thrown later — a malformed
      // benchmark entry, a DOM failure, a rejection inside the Promise.all
      // continuation — would otherwise become an unhandled rejection and leave the
      // page stuck on "Loading benchmarks…" with the table hidden and no error state.
      showError(statusNode, describeError(err, { generic: "Could not load benchmarks — try again later." }));
    });
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
    createCopyButton: createCopyButton,
    renderTabStrip: renderTabStrip,
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
