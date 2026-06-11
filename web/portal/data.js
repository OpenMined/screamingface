/* ScreamingFace Leaderboard Portal — published-data viewer.
 *
 * Reads ?file=<name>.jsonl, fetches it from the site root, and renders the
 * rows as a table. Exists because GitHub Pages serves .jsonl as
 * application/octet-stream (a forced download) with no way to customize
 * MIME types — this page is the human-readable view of the same bytes.
 *
 * Security posture matches the rest of the portal: the file name is
 * validated against a strict pattern (no slashes, no traversal — site-root
 * .jsonl files only) and every value reaches the DOM via textContent.
 */
(function (P) {
  "use strict";

  var FILE_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*\.jsonl$/;

  function cellValue(value) {
    if (value === null || value === undefined || value === "") return P.EM_DASH;
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  // Columns are the union of keys across rows, in first-appearance order.
  function render(rows) {
    var cols = [];
    rows.forEach(function (row) {
      Object.keys(row).forEach(function (key) {
        if (cols.indexOf(key) === -1) cols.push(key);
      });
    });

    var head = document.getElementById("data-head");
    P.clear(head);
    var headRow = document.createElement("tr");
    headRow.appendChild(P.el("th", "num", "#"));
    cols.forEach(function (col) { headRow.appendChild(P.el("th", null, col)); });
    head.appendChild(headRow);

    var body = document.getElementById("data-body");
    P.clear(body);
    rows.forEach(function (row, i) {
      var tr = document.createElement("tr");
      tr.appendChild(P.el("td", "num", i + 1));
      cols.forEach(function (col) {
        tr.appendChild(P.el("td", "cell-wrap", cellValue(row[col])));
      });
      body.appendChild(tr);
    });
    return cols.length;
  }

  function init() {
    var statusNode = document.getElementById("data-status");
    var wrap = document.getElementById("data-wrap");

    var file;
    try {
      file = P.requireParam("file");
    } catch (e) {
      P.showError(statusNode, "Missing “file” parameter.");
      return;
    }
    if (!FILE_RE.test(file)) {
      P.showError(statusNode, "Not a publishable data file name.");
      return;
    }

    document.getElementById("data-file").textContent = file;
    document.title = file + " — screamingface";
    document.getElementById("data-raw").setAttribute("href", "/" + file);
    document.getElementById("data-txt").setAttribute("href", "/" + file + ".txt");

    P.showLoading(statusNode, "Loading " + file + "…");
    wrap.hidden = true;

    fetch("/" + file)
      .then(function (resp) {
        if (!resp.ok) throw new Error("status " + resp.status);
        return resp.text();
      })
      .then(function (text) {
        var rows = text
          .split("\n")
          .filter(function (line) { return line.trim() !== ""; })
          .map(function (line) { return JSON.parse(line); });
        if (!rows.length) {
          P.showEmpty(statusNode, "The file is empty.");
          return;
        }
        var fields = render(rows);
        document.getElementById("data-meta").textContent =
          rows.length + (rows.length === 1 ? " row" : " rows") + " · " + fields + " fields";
        P.setStatus(statusNode, null);
        wrap.hidden = false;
      })
      .catch(function () {
        P.showError(statusNode, "Could not load " + file + " — it may not be published.");
      });
  }

  P.ready(init);
})(window.ScorePortal);
