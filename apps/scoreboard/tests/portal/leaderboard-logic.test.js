/* Tests for the leaderboard's pure ranking/SOTA decisions (OME-769, OME-866).
 *
 * Runs on Node's built-in runner — `node --test tests/portal/` — so it needs no
 * package.json, no dependency, and no new toolchain. Wiring it into
 * scoreboard-tests.yml + the sdlc card's gate list is deliberately a separate
 * unit of work; until that lands these run locally and in review.
 *
 * WHY these three functions are pure and live outside the DOM code: the board's
 * two load-bearing judgements — "which row, if any, earns the SOTA medal" and
 * "how long is the score bar" — decide what a public leaderboard *claims*.
 * They must be assertable without a browser.
 *
 * OME-866: entries carry a benchmark-native `score` (fractional for DRACO,
 * negative for HealthBench worst-30), not a 0..1 `accuracy` — the assertions on
 * negative and mixed ranges pin that the board renders them without a universal
 * percentage assumption.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const L = require("../../portal/leaderboard-logic.js");

// A leaderboard entry, trimmed to the fields these decisions actually read.
function entry(spec_id, score, verified) {
  return { spec_id, score, verified_by_screamingface: verified };
}

test("sotaScore: no entries means no SOTA", () => {
  assert.equal(L.sotaScore([]), null);
});

test("sotaScore: entries but none reproducible means no SOTA at all", () => {
  // INVARIANT: the medal never falls back to an unverified row. A board with
  // nothing reproduced shows no medal — it must not imply OpenMined reproduced
  // a self-reported score. This is the whole point of OME-769's "top
  // reproducible fusion" wording.
  const entries = [entry("a", 0.9, false), entry("b", 0.8, false)];
  assert.equal(L.sotaScore(entries), null);
});

test("sotaScore: picks the best score among reproducible entries", () => {
  const entries = [entry("a", 0.5, true), entry("b", 0.7, true)];
  assert.equal(L.sotaScore(entries), 0.7);
});

test("sotaScore: a higher-score unverified entry does NOT take the medal", () => {
  // The D2 invariant, stated as a test: 0.99 unverified must lose to 0.40
  // verified. Today's board (pre-OME-769) would wrongly mark the 0.99 row.
  const entries = [entry("cheater", 0.99, false), entry("honest", 0.4, true)];
  assert.equal(L.sotaScore(entries), 0.4);
});

test("sotaScore: all-negative reproducible entries still produce a SOTA", () => {
  // OME-866: on the HealthBench worst-30 board EVERY serious score is negative;
  // "best" is the least negative, and the medal logic must not treat a negative
  // number as falsy or missing.
  const entries = [entry("a", -1.143, true), entry("b", -0.4, true)];
  assert.equal(L.sotaScore(entries), -0.4);
});

test("isSota: true only for a reproducible entry at the SOTA score", () => {
  const sota = 0.7;
  assert.equal(L.isSota(entry("a", 0.7, true), sota), true);
  assert.equal(L.isSota(entry("b", 0.7, false), sota), false, "unverified at the same score");
  assert.equal(L.isSota(entry("c", 0.6, true), sota), false, "verified but below");
});

test("isSota: nothing is SOTA when there is no SOTA score", () => {
  assert.equal(L.isSota(entry("a", 0.9, true), null), false);
});

test("isSota: ties at the top all carry the medal", () => {
  // Deliberate: with a genuine tie there is no non-arbitrary single winner, so
  // both reproducible rows are marked rather than picking one by input order.
  const sota = 0.7;
  assert.equal(L.isSota(entry("a", 0.7, true), sota), true);
  assert.equal(L.isSota(entry("b", 0.7, true), sota), true);
});

test("orderRows: sorts by score descending", () => {
  const entries = [entry("mid", 0.5, false), entry("top", 0.9, false), entry("low", 0.1, false)];
  assert.deepEqual(
    L.orderRows(entries).map((e) => e.spec_id),
    ["top", "mid", "low"],
  );
});

test("orderRows: negative and mixed scores rank high-to-low too", () => {
  // OME-866: higher is always better within a benchmark, whatever the range.
  const entries = [entry("worst", -1.143, false), entry("best", 0.399, false), entry("mid", -0.2, false)];
  assert.deepEqual(
    L.orderRows(entries).map((e) => e.spec_id),
    ["best", "mid", "worst"],
  );
});

test("orderRows: ties keep their original relative order (stable)", () => {
  const entries = [entry("first", 0.5, false), entry("second", 0.5, false)];
  assert.deepEqual(
    L.orderRows(entries).map((e) => e.spec_id),
    ["first", "second"],
  );
});

test("orderRows: does not mutate its input", () => {
  const entries = [entry("mid", 0.5, false), entry("top", 0.9, false)];
  L.orderRows(entries);
  assert.deepEqual(
    entries.map((e) => e.spec_id),
    ["mid", "top"],
    "caller's array order must be untouched",
  );
});

test("barWidth: a classic 0..1 board keeps its absolute zero origin", () => {
  // The floor is min(0, minScore), so positive boards render exactly as they
  // did before OME-866 — the bar still means "share of the best on screen".
  assert.equal(L.barWidth(0.5, 0.1, 1), 50);
  assert.equal(L.barWidth(1, 0.1, 1), 100);
  assert.equal(L.barWidth(0.25, 0.25, 0.5), 50, "relative to the max shown, not to 100%");
});

test("barWidth: zero score on a positive board is a zero-width bar", () => {
  assert.equal(L.barWidth(0, 0, 0.8), 0);
});

test("barWidth: a zero maximum cannot divide by zero", () => {
  // Reachable: a benchmark where every submission scored 0.
  assert.equal(L.barWidth(0, 0, 0), 0);
});

test("barWidth: never exceeds 100 even if handed a value above the max", () => {
  assert.equal(L.barWidth(1.5, 0, 1), 100);
});

test("barWidth: negative scores shift the origin instead of rendering negative widths", () => {
  // OME-866: an all-negative HealthBench board spans floor..max. The lowest row
  // is 0-width, the best is full, and NOTHING is negative (a negative CSS width
  // is invalid and collapses the track).
  assert.equal(L.barWidth(-1.143, -1.143, 0.399), 0);
  assert.equal(L.barWidth(0.399, -1.143, 0.399), 100);
  const mid = L.barWidth(-0.372, -1.143, 0.399);
  assert.ok(mid > 49 && mid < 51, `midpoint of the span is ~50, got ${mid}`);
  assert.ok(L.barWidth(-0.4, -1.143, 0.399) >= 0);
});

test("barWidth: an all-equal negative board renders empty tracks, not negatives", () => {
  assert.equal(L.barWidth(-1.143, -1.143, -1.143), 0);
});

test("barWidth: a missing max is a zero-width bar, never NaN in CSS", () => {
  assert.equal(L.barWidth(0.5, undefined, undefined), 0);
  assert.equal(L.barWidth(NaN, 0, 1), 0);
});
