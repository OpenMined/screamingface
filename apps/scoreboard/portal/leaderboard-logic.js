/* Pure ranking / SOTA decisions for the leaderboard board (OME-769).
 *
 * FEATURE: the per-benchmark submissions board — ranked rows, accuracy bars, and
 * the SOTA medal on the best reproducible result.
 *
 * WHY this file exists separately from benchmark.js: these three functions decide
 * what the public board *claims* — which row (if any) is presented as
 * state-of-the-art, and how long each accuracy bar reads. Keeping them free of
 * the DOM makes them assertable in `tests/portal/leaderboard-logic.test.js`
 * without a browser, which the rest of the portal's rendering is not.
 *
 * Loaded as a plain <script> in the browser (exposing window.SFLeaderboardLogic)
 * and via require() in tests. No build step, matching the rest of the portal.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SFLeaderboardLogic = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // INVARIANT: only a reproducible entry may ever be presented as SOTA. Returns
  // null when nothing has been reproduced — the medal is then shown nowhere,
  // rather than falling back to the best self-reported score. A board that
  // badged an unverified claim would be asserting OpenMined reproduced a run it
  // never did, which is exactly what the page's own disclaimer denies.
  //
  // AIDEV-NOTE: `verified_by_openmined` is the only reproducibility signal the
  // Scoreboard API exposes today. OME-771 intends to source this from the SF
  // engine instead ("have we run this URL4 before" — i.e. a global-cache hit).
  // When that lands, change the predicate on the next line and nothing else:
  // the tests pin the invariant above, not the current source of the signal.
  function isReproducible(entry) {
    return entry.verified_by_openmined === true;
  }

  function sotaAccuracy(entries) {
    var best = null;
    (entries || []).forEach(function (entry) {
      if (!isReproducible(entry)) return;
      if (best === null || entry.accuracy > best) best = entry.accuracy;
    });
    return best;
  }

  // WHY exact equality is safe on a float here: `sota` is one of the very
  // `accuracy` values being compared, carried through unchanged — no arithmetic
  // is performed on it, so there is no rounding to drift past.
  function isSota(entry, sota) {
    if (sota === null || sota === undefined) return false;
    return isReproducible(entry) && entry.accuracy === sota;
  }

  // WHY a copy: callers hold the fetched array as page state and re-sort it on
  // header clicks; mutating it in place would make render order depend on how
  // many times the board had already been drawn.
  function orderRows(entries) {
    return (entries || []).slice().sort(function (a, b) {
      return b.accuracy - a.accuracy;
    });
  }

  // Bar length as a percentage of the best accuracy *on screen*, so the widest
  // bar is always full — a field of near-identical short bars carries no
  // comparison. Returns 0 rather than dividing when every entry scored 0, and
  // clamps so a value above the stated max cannot overflow its track.
  function barWidth(accuracy, maxAccuracy) {
    if (!maxAccuracy || maxAccuracy <= 0) return 0;
    var pct = (accuracy / maxAccuracy) * 100;
    if (pct < 0) return 0;
    return pct > 100 ? 100 : pct;
  }

  return {
    isReproducible: isReproducible,
    sotaAccuracy: sotaAccuracy,
    isSota: isSota,
    orderRows: orderRows,
    barWidth: barWidth,
  };
});
