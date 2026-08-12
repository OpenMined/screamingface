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
    // The mark slot as its own column rather than a fixed-width span inside the
    // spec cell. OME-769 words this as "a spacer for non-SOTA rows so names stay
    // aligned" — a column satisfies that goal structurally instead of by hand.
    //
    // WHY it is not in the spec cell: the enhanced badge ("S" + <canvas> + "TA")
    // renders WIDER than its plain-text form, so an in-cell slot sized to the
    // text grew on the SOTA row once wave-mark.js upgraded it, shifting that
    // row's name ~64px right of every other row — the exact misalignment the
    // spacer was meant to prevent. It also stole width from `.cell-wrap`'s
    // 192px cap and wrapped long spec names onto a second line. A column cannot
    // drift for either reason. OME-770's frontier mark belongs here too.
    { key: "__mark", label: "", sort: null, cls: "col-mark" },
    // OME-769 asks for a "Name" column, but nothing in the payload names a
    // fusion — `spec_id` is the only identifier (the gap catalogued in OME-772).
    // The header stays "Spec" so it describes what the cell actually holds; the
    // SOTA mark slot leads this cell, which is the "mark leads the name" part.
    { key: "spec_id", label: "Spec", sort: "string", dir: "asc" },
    // Likewise "Models": `ran_with_providers` is provider names, not model
    // identities, and providers.length > 1 is not a valid fusion/solo test.
    // Keeping the honest label until a backend field exists.
    { key: "ran_with_providers", label: "Backends", sort: null },
    { key: "submitted_by", label: "Author", sort: "string", dir: "asc" },
    { key: "accuracy", label: "Accuracy", sort: "number", dir: "desc", cls: "num" },
    // WHY Questions is gone: OME-769's column list is #, Name, Models, Author,
    // Accuracy, Submitted, Run locally — Questions is not in it. Adding Author
    // and the mark column pushed the table past its container (1205px into
    // 958px), which put "Run Locally" — the url4 copy, the board's primary
    // action — behind a horizontal scroll. `total_questions` is still shown on
    // each spec's detail page, so no data is lost from the portal.
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
          enhanceSotaMark(document.getElementById("leaderboard-body"));
        });
        th.appendChild(btn);
      }
      tr.appendChild(th);
    });
    headNode.appendChild(tr);
  }

  var L = window.SFLeaderboardLogic;

  // The widest accuracy bar on screen. Deliberately the best accuracy of ALL
  // entries, verified or not — the bar is a like-for-like visual comparison of
  // the rows present, so scaling it to the reproducible-only maximum would let
  // an unverified row overflow its own track.
  function bestAccuracy(entries) {
    if (!entries.length) return null;
    return Math.max.apply(null, entries.map(function (e) { return e.accuracy; }));
  }

  // The SOTA mark cell. INVARIANT: rendered on EVERY row — badge on the SOTA
  // row, empty everywhere else — so the spec text starts at the same x on all
  // rows. OME-770 drops its frontier mark into this same cell.
  function renderMarkSlot(isSotaRow) {
    var slot = P.el("td", "col-mark");
    if (!isSotaRow) {
      return slot;
    }
    // Text baseline first (D4). enhanceSotaMark() upgrades the O to canvas only
    // once the texture decodes; if it never loads, this still reads "SOTA".
    var badge = P.el("span", "badge-sota");
    // WHY the badge is decorative: once enhanced its letters become
    // "S" + <canvas> + "TA", which a screen reader would announce as "S TA".
    // The sr-only sentence appended in renderBody is the accessible carrier of
    // this meaning, so the badge stays out of the accessibility tree in both its
    // text and its enhanced form.
    badge.setAttribute("aria-hidden", "true");
    badge.appendChild(P.el("span", "gt-flow", "SOTA"));
    slot.appendChild(badge);
    return slot;
  }

  var MARK_SRC = "assets/mark/sf-mark-wave.webp";

  // Progressive enhancement, deliberately not graceful degradation (D4). The
  // design system's badge markup is "S" + <canvas> + "TA", where the canvas IS
  // the letter O — so a canvas that never paints leaves "S TA" with a hole in
  // it. Rather than render that and hope, the badge ships as plain text and is
  // only rewritten AFTER the texture has decoded and the driver is present.
  //
  // WHY the image is preloaded here instead of trusting wave-mark.js: that
  // script swallows its own decode failure (`.catch(function () {})`), so it
  // cannot tell us whether the mark is safe to swap in. It does expose
  // window.SFWave.init() for canvases added later, which is exactly this case.
  function enhanceSotaMark(root) {
    var badges = (root || document).querySelectorAll(".badge-sota");
    if (!badges.length || !window.SFWave || typeof window.SFWave.init !== "function") return;
    var probe = new Image();
    probe.onerror = function () { /* texture unavailable — the text badge stands */ };
    probe.onload = function () {
      badges.forEach(function (badge) {
        if (badge.getAttribute("data-mark-enhanced")) return;
        badge.setAttribute("data-mark-enhanced", "1");
        P.clear(badge);
        badge.appendChild(P.el("span", "gt-flow", "S"));
        var cv = document.createElement("canvas");
        cv.className = "wave-mark gt-wave";
        cv.setAttribute("data-src", MARK_SRC);
        cv.setAttribute("aria-hidden", "true");
        badge.appendChild(cv);
        badge.appendChild(P.el("span", "gt-flow", "TA"));
      });
      window.SFWave.init(root || document);
    };
    probe.src = MARK_SRC;
  }

  // The vendored .score-cell recipe: the number plus a proportional track. Its
  // documented markup is
  //   <span class="score-cell"><span class="num">84.3</span>
  //     <span class="score-track"><span class="score-fill" style="width:88%"></span></span></span>
  // The track is decoration — the adjacent number is the accessible value, so it
  // carries aria-hidden rather than duplicating the figure to a screen reader.
  //
  // AIDEV-NOTE: the `.grad` fill variant animates; it is reserved for the single
  // hero win in the design system, so plain `.score-fill` is used per row here.
  function renderAccuracyCell(accuracy, barMax) {
    var td = P.el("td", "num");
    var cell = P.el("span", "score-cell");
    cell.appendChild(P.el("span", "num", P.formatPercent(accuracy)));
    var track = P.el("span", "score-track");
    track.setAttribute("aria-hidden", "true");
    var fill = P.el("span", "score-fill");
    fill.style.width = L.barWidth(accuracy, barMax).toFixed(1).replace(/\.0$/, "") + "%";
    track.appendChild(fill);
    cell.appendChild(track);
    td.appendChild(cell);
    return td;
  }

  function renderBody(bodyNode) {
    P.clear(bodyNode);
    var barMax = bestAccuracy(state.entries);
    // The medal is decided by the reproducible-only maximum, NOT barMax.
    var sota = L.sotaAccuracy(state.entries);
    sortedEntries().forEach(function (entry) {
      var tr = document.createElement("tr");
      var isSota = L.isSota(entry, sota);
      if (isSota) tr.className = "sota";

      tr.appendChild(P.el("td", "num", entry.rank));
      tr.appendChild(renderMarkSlot(isSota));

      var specTd = P.el("td", "cell-wrap");
      specTd.appendChild(P.link("mono", "spec.html?benchmark=" + encodeURIComponent(state.benchmarkId) + "&spec=" + encodeURIComponent(entry.spec_id), entry.spec_id));
      // Color must not be the only carrier of the sota meaning.
      if (isSota) specTd.appendChild(P.el("span", "sr-only", " (state of the art, independently reproduced)"));
      tr.appendChild(specTd);

      tr.appendChild(P.el("td", null, P.formatProviders(entry.ran_with_providers)));
      // formatSubmitter already renders an em-dash for a null/blank submitter.
      tr.appendChild(P.el("td", null, P.formatSubmitter(entry.submitted_by)));
      tr.appendChild(renderAccuracyCell(entry.accuracy, barMax));
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
    var sota = L.sotaAccuracy(entries);
    var verified = entries.filter(L.isReproducible).length;
    // Bare numbers: the .stats cell labels ("Specs shown", "Verified rows")
    // already carry the words.
    document.getElementById("summary-best").textContent = P.formatPercent(best);
    // An em-dash when nothing is reproduced yet — deliberately NOT "0%", which
    // would read as "the best reproduced run scored zero" rather than "there is
    // no reproduced run".
    document.getElementById("summary-sota").textContent = sota === null ? P.EM_DASH : P.formatPercent(sota);
    document.getElementById("summary-specs").textContent = entries.length.toLocaleString();
    document.getElementById("summary-verified").textContent = verified.toLocaleString();
    summaryNode.hidden = false;
  }

  // Climb accuracy bars (brand viz-a direction): one row per spec, the SOTA
  // entry carries the sota (gain) fill — same story color as tr.sota.
  // Purely visual: aria-hidden, the table is the accessible representation.
  //
  // WHY this changed with OME-769: the fill used to key off the raw maximum
  // accuracy, so once the table's medal became reproducible-only this chart
  // would have painted an unverified top row in the win color while the table
  // withheld the medal from it — the same story color asserting two different
  // things on one page. Both now read from L.isSota.
  function renderClimb(entries) {
    var section = document.getElementById("leaderboard-climb-section");
    var node = document.getElementById("leaderboard-climb");
    if (!section || !node) return;
    if (!entries.length) {
      section.hidden = true;
      return;
    }
    var sota = L.sotaAccuracy(entries);
    P.clear(node);
    L.orderRows(entries)
      .forEach(function (entry) {
        var row = P.el("div", "row");
        row.appendChild(P.el("span", "lbl", entry.spec_id));
        var track = P.el("span", "track");
        var fill = P.el("span", "fill " + (L.isSota(entry, sota) ? "sota" : "base"));
        fill.style.width = ((entry.accuracy * 100).toFixed(1) + "%").replace(".0%", "%");
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(P.el("span", "val", P.formatPercent(entry.accuracy)));
        node.appendChild(row);
      });
    section.hidden = false;
  }

  // Tab strip renders across all pages regardless of whether the current
  // `id` is valid — even a 404/missing-id state should let the reader jump
  // to a real benchmark, not dead-end.
  function initTabStrip(activeId) {
    var tabsNode = document.getElementById("benchmark-tabs");
    if (!tabsNode) return;
    P.fetchJson("/v1/benchmarks").then(
      function (data) { P.renderTabStrip(tabsNode, (data && data.benchmarks) || [], activeId); },
      function () { /* tab strip is a nav convenience, not load-bearing — fail silent */ }
    );
  }

  // D9: an unknown/missing benchmark id must not be a dead end — the status
  // region gets a real link back to the catalog, not just text.
  function showNotFound(statusNode, message) {
    P.setStatus(statusNode, "error", "");
    statusNode.appendChild(document.createTextNode(message + " "));
    statusNode.appendChild(P.link(null, "index.html", "Return to the benchmark list."));
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
      showNotFound(statusNode, "No benchmark specified.");
      initTabStrip(null);
      return;
    }
    state.benchmarkId = id;
    initTabStrip(id);

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
          // OME-768 asks this page for an "empty table structure", so the shell
          // has to render on the zero-entry path too — previously this returned
          // early with `wrap` still hidden, so a benchmark with no submissions
          // showed the message and no table at all. renderSummary/renderClimb
          // hide themselves when passed an empty list, so the reader gets the
          // column headers plus the empty-state line and nothing misleading.
          renderSummary(state.entries);
          renderClimb(state.entries);
          renderHead(document.getElementById("leaderboard-head"));
          P.clear(document.getElementById("leaderboard-body"));
          P.showEmpty(statusNode, "No submissions yet. Be the first.");
          wrap.hidden = false;
          return;
        }
        renderSummary(state.entries);
        renderClimb(state.entries);
        renderHead(document.getElementById("leaderboard-head"));
        renderBody(document.getElementById("leaderboard-body"));
        enhanceSotaMark(document.getElementById("leaderboard-body"));
        P.setStatus(statusNode, null);
        wrap.hidden = false;
      },
      function (err) {
        if (err && err.status === 404) {
          showNotFound(statusNode, "Benchmark not found.");
          return;
        }
        P.showError(statusNode, P.describeError(err, {
          generic: "Could not load leaderboard — try again later.",
        }));
      }
    );
  }

  P.ready(init);
})(window.ScorePortal);
