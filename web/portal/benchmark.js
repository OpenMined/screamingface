/* ScreamingFace Leaderboard Portal — benchmark (top-N) page.
 *
 * Reads ?id=<benchmark_id>, fetches /v1/leaderboard/{id}, and renders a
 * client-side sortable table. Default sort is accuracy DESC. The Rank column
 * always shows the backend-provided rank (best-per-spec), even when the user
 * sorts by another column — we only reorder rows for display, never recompute
 * the backend's best-per-spec selection (which breaks accuracy ties by newest
 * submission).
 */
(function (P) {
  "use strict";

  // Column definitions. `sort` null => not sortable. `dir` is the default
  // direction applied the first time a column is selected.
  var COLUMNS = [
    { key: "rank", label: "Rank", sort: "number", dir: "asc", cls: "num" },
    { key: "spec_id", label: "Spec", sort: "string", dir: "asc" },
    { key: "ran_with_providers", label: "Backends", sort: null },
    { key: "accuracy", label: "Accuracy", sort: "number", dir: "desc", cls: "num" },
    { key: "total_questions", label: "Questions", sort: "number", dir: "desc", cls: "num" },
    { key: "submitted_at", label: "Submitted", sort: "date", dir: "desc" },
    { key: "verified_by_openmined", label: "Verified", sort: "bool", dir: "desc" },
    { key: "__run", label: "Run Locally", sort: null, cls: "col-run" },
  ];

  var state = { entries: [], benchmarkId: null, sortKey: "accuracy", sortDir: "desc" };

  function compare(a, b, key, type, dir) {
    var av = a[key], bv = b[key], res = 0;
    if (type === "string") {
      res = String(av).localeCompare(String(bv));
    } else if (type === "bool") {
      res = (av === true ? 1 : 0) - (bv === true ? 1 : 0);
    } else if (type === "date") {
      res = new Date(av).getTime() - new Date(bv).getTime();
    } else { // number
      res = (av || 0) - (bv || 0);
    }
    return dir === "desc" ? -res : res;
  }

  function sortedEntries() {
    var col = COLUMNS.filter(function (c) { return c.key === state.sortKey; })[0];
    if (!col || !col.sort) return state.entries.slice();
    var copy = state.entries.slice();
    copy.sort(function (a, b) { return compare(a, b, state.sortKey, col.sort, state.sortDir); });
    return copy;
  }

  function renderHead(headNode) {
    P.clear(headNode);
    var tr = document.createElement("tr");
    COLUMNS.forEach(function (col) {
      var th = document.createElement("th");
      if (col.cls) th.className = col.cls;
      if (!col.sort) {
        th.textContent = col.label;
      } else {
        var active = col.key === state.sortKey;
        th.setAttribute("aria-sort", active ? (state.sortDir === "desc" ? "descending" : "ascending") : "none");
        var btn = P.el("button", "sort-button");
        btn.type = "button";
        btn.appendChild(document.createTextNode(col.label + " "));
        btn.appendChild(P.el("span", "arrow", active ? (state.sortDir === "desc" ? "▼" : "▲") : "↕"));
        btn.addEventListener("click", function () {
          if (state.sortKey === col.key) {
            state.sortDir = state.sortDir === "desc" ? "asc" : "desc";
          } else {
            state.sortKey = col.key;
            state.sortDir = col.dir;
          }
          renderHead(headNode);
          renderBody(document.getElementById("leaderboard-body"));
        });
        th.appendChild(btn);
      }
      tr.appendChild(th);
    });
    headNode.appendChild(tr);
  }

  // The brand's one story color: entries tied at the best accuracy are SOTA.
  function bestAccuracy(entries) {
    if (!entries.length) return null;
    return Math.max.apply(null, entries.map(function (e) { return e.accuracy; }));
  }

  function renderBody(bodyNode) {
    P.clear(bodyNode);
    var best = bestAccuracy(state.entries);
    sortedEntries().forEach(function (entry) {
      var tr = document.createElement("tr");
      var isSota = best !== null && entry.accuracy === best;
      if (isSota) tr.className = "sota";

      tr.appendChild(P.el("td", "num", entry.rank));

      var specTd = P.el("td", "cell-wrap");
      specTd.appendChild(P.link("mono", "spec.html?benchmark=" + encodeURIComponent(state.benchmarkId) + "&spec=" + encodeURIComponent(entry.spec_id), entry.spec_id));
      // Color must not be the only carrier of the sota meaning.
      if (isSota) specTd.appendChild(P.el("span", "sr-only", " (state of the art)"));
      tr.appendChild(specTd);

      tr.appendChild(P.el("td", null, P.formatProviders(entry.ran_with_providers)));
      tr.appendChild(P.el("td", "num", P.formatPercent(entry.accuracy)));
      tr.appendChild(P.el("td", "num", P.formatQuestions(entry.total_questions)));
      tr.appendChild(P.el("td", null, P.formatDate(entry.submitted_at)));

      var verTd = document.createElement("td");
      verTd.appendChild(P.createVerifiedBadge(entry.verified_by_openmined));
      tr.appendChild(verTd);

      var runTd = document.createElement("td");
      runTd.className = "col-run";
      // Guard like spec.js: a missing expression renders as absence, never as
      // a Copy button that would put "undefined" on the clipboard.
      if (entry.url4_expression) {
        runTd.appendChild(P.createCopyButton(entry.spec_id, entry.url4_expression, { compact: true }));
      } else {
        runTd.textContent = P.EM_DASH;
      }
      tr.appendChild(runTd);

      bodyNode.appendChild(tr);
    });
  }

  function renderSummary(entries) {
    var summaryNode = document.getElementById("leaderboard-summary");
    if (!summaryNode) return;
    if (!entries.length) {
      summaryNode.hidden = true;
      return;
    }

    var best = bestAccuracy(entries);
    var verified = entries.filter(function (entry) { return entry.verified_by_openmined === true; }).length;
    // Bare numbers: the .stats cell labels ("Specs shown", "Verified rows")
    // already carry the words.
    document.getElementById("summary-best").textContent = P.formatPercent(best);
    document.getElementById("summary-specs").textContent = entries.length.toLocaleString();
    document.getElementById("summary-verified").textContent = verified.toLocaleString();
    summaryNode.hidden = false;
  }

  // Climb accuracy bars (brand viz-a direction): one row per spec, best
  // accuracy carries the sota (gain) fill — same story color as tr.sota.
  // Purely visual: aria-hidden, the table is the accessible representation.
  function renderClimb(entries) {
    var section = document.getElementById("leaderboard-climb-section");
    var node = document.getElementById("leaderboard-climb");
    if (!section || !node) return;
    if (!entries.length) {
      section.hidden = true;
      return;
    }
    var best = bestAccuracy(entries);
    P.clear(node);
    entries
      .slice()
      .sort(function (a, b) { return b.accuracy - a.accuracy; })
      .forEach(function (entry) {
        var row = P.el("div", "row");
        row.appendChild(P.el("span", "lbl", entry.spec_id));
        var track = P.el("span", "track");
        var fill = P.el("span", "fill " + (entry.accuracy === best ? "sota" : "base"));
        fill.style.width = ((entry.accuracy * 100).toFixed(1) + "%").replace(".0%", "%");
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(P.el("span", "val", P.formatPercent(entry.accuracy)));
        node.appendChild(row);
      });
    section.hidden = false;
  }

  function init() {
    var statusNode = document.getElementById("leaderboard-status");
    var wrap = document.getElementById("leaderboard-wrap");
    var nameNode = document.getElementById("benchmark-name");
    var descNode = document.getElementById("benchmark-desc");

    var id;
    try {
      id = P.requireParam("id");
    } catch (e) {
      P.showError(statusNode, "No benchmark specified. Return to the benchmark list.");
      return;
    }
    state.benchmarkId = id;

    P.showLoading(statusNode, "Loading leaderboard…");
    wrap.hidden = true;

    P.fetchJson("/v1/leaderboard/" + encodeURIComponent(id) + "?top=50").then(
      function (data) {
        var b = data && data.benchmark;
        if (b) {
          nameNode.textContent = b.display_name || b.id;
          descNode.textContent = b.description || "";
          document.title = (b.display_name || b.id) + " — screamingface";
        }
        state.entries = (data && data.entries) || [];
        if (state.entries.length === 0) {
          P.showEmpty(statusNode, "No submissions yet. Be the first.");
          return;
        }
        renderSummary(state.entries);
        renderClimb(state.entries);
        renderHead(document.getElementById("leaderboard-head"));
        renderBody(document.getElementById("leaderboard-body"));
        P.setStatus(statusNode, null);
        wrap.hidden = false;
      },
      function (err) {
        P.showError(statusNode, P.describeError(err, {
          notFound: "Benchmark not found.",
          generic: "Could not load leaderboard — try again later.",
        }));
      }
    );
  }

  P.ready(init);
})(window.ScorePortal);
