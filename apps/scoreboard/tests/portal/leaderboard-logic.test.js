/* Tests for the leaderboard's pure ranking/SOTA decisions (OME-769).
 *
 * Runs on Node's built-in runner — `node --test tests/portal/` — so it needs no
 * package.json, no dependency, and no new toolchain. Wiring it into
 * scoreboard-tests.yml + the sdlc card's gate list is deliberately a separate
 * unit of work; until that lands these run locally and in review.
 *
 * WHY these three functions are pure and live outside the DOM code: the board's
 * two load-bearing judgements — "which row, if any, earns the SOTA medal" and
 * "how long is the accuracy bar" — decide what a public leaderboard *claims*.
 * They must be assertable without a browser.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const L = require("../../portal/leaderboard-logic.js");

// A leaderboard entry, trimmed to the fields these decisions actually read.
function entry(spec_id, accuracy, verified) {
  return { spec_id, accuracy, verified_by_openmined: verified };
}

test("sotaAccuracy: no entries means no SOTA", () => {
  assert.equal(L.sotaAccuracy([]), null);
});

test("sotaAccuracy: entries but none reproducible means no SOTA at all", () => {
  // INVARIANT: the medal never falls back to an unverified row. A board with
  // nothing reproduced shows no medal — it must not imply OpenMined reproduced
  // a self-reported score. This is the whole point of OME-769's "top
  // reproducible fusion" wording.
  const entries = [entry("a", 0.9, false), entry("b", 0.8, false)];
  assert.equal(L.sotaAccuracy(entries), null);
});

test("sotaAccuracy: picks the best accuracy among reproducible entries", () => {
  const entries = [entry("a", 0.5, true), entry("b", 0.7, true)];
  assert.equal(L.sotaAccuracy(entries), 0.7);
});

test("sotaAccuracy: a higher-accuracy unverified entry does NOT take the medal", () => {
  // The D2 invariant, stated as a test: 0.99 unverified must lose to 0.40
  // verified. Today's board (pre-OME-769) would wrongly mark the 0.99 row.
  const entries = [entry("cheater", 0.99, false), entry("honest", 0.4, true)];
  assert.equal(L.sotaAccuracy(entries), 0.4);
});

test("isSota: true only for a reproducible entry at the SOTA accuracy", () => {
  const sota = 0.7;
  assert.equal(L.isSota(entry("a", 0.7, true), sota), true);
  assert.equal(L.isSota(entry("b", 0.7, false), sota), false, "unverified at the same accuracy");
  assert.equal(L.isSota(entry("c", 0.6, true), sota), false, "verified but below");
});

test("isSota: nothing is SOTA when there is no SOTA accuracy", () => {
  assert.equal(L.isSota(entry("a", 0.9, true), null), false);
});

test("isSota: ties at the top all carry the medal", () => {
  // Deliberate: with a genuine tie there is no non-arbitrary single winner, so
  // both reproducible rows are marked rather than picking one by input order.
  const sota = 0.7;
  assert.equal(L.isSota(entry("a", 0.7, true), sota), true);
  assert.equal(L.isSota(entry("b", 0.7, true), sota), true);
});

test("orderRows: sorts by accuracy descending", () => {
  const entries = [entry("mid", 0.5, false), entry("top", 0.9, false), entry("low", 0.1, false)];
  assert.deepEqual(
    L.orderRows(entries).map((e) => e.spec_id),
    ["top", "mid", "low"],
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

test("barWidth: scales accuracy against the best on screen", () => {
  assert.equal(L.barWidth(0.5, 1), 50);
  assert.equal(L.barWidth(1, 1), 100);
  assert.equal(L.barWidth(0.25, 0.5), 50, "relative to the max shown, not to 100%");
});

test("barWidth: zero accuracy is a zero-width bar", () => {
  assert.equal(L.barWidth(0, 0.8), 0);
});

test("barWidth: a zero maximum cannot divide by zero", () => {
  // Reachable: a benchmark where every submission scored 0.
  assert.equal(L.barWidth(0, 0), 0);
});

test("barWidth: never exceeds 100 even if handed a value above the max", () => {
  assert.equal(L.barWidth(1.5, 1), 100);
});
