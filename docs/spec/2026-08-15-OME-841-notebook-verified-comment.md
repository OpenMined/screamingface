# OME-841 — a removal's recorded reason must survive being checked

Status: approved (owner, 2026-08-15) · Stack: screamingface

## 1. Problem

`#601` removed the notebook view's `verified` chip and "verified only" filter. Beside the deletion it
records why:

> `verified_by_openmined` is **uniform** since `OME-820`, so **no row carries `data-verified=false`**
> and the control removed nothing.

That is a factual claim about the data, and it is false. `OME-820` explicitly forbids a backfill, so
every row created before it still holds `false`.

This matters more than a typo because of *where* the claim sits. It is the justification for deleting
a user-facing control. The next person to touch this area will read it, check it, find it untrue, and
reasonably conclude the deletion was unjustified — and restore the filter.

## 2. The real reason is stronger, not weaker

Established during the `#588` review and already recorded in `OME-820`, `OME-821` and
`apps/scoreboard/portal`:

`verified_by_openmined` **certifies nothing, whatever value it holds.** Nothing re-runs submissions
(`OME-414` unstarted) and nothing attests where a run executed.

So a "verified only" filter would not be harmlessly inert. It would partition rows by **whether they
predate the default change**, while presenting itself as a verification filter — measuring submission
date and looking like it measured trust. That is worse than filtering nothing, and it is why the
control was removed rather than relabelled.

Note the asymmetry the wrong wording introduced: "uniform" implies the control is *harmless* and could
come back any time. "Certifies nothing" implies it is *actively misleading* and must not come back
until `OME-821` gives the flag a meaning. The wrong word argued for the opposite conclusion to the one
the code took.

## 3. Contract

- **All three** occurrences stop claiming uniformity: `:63-64`, `:119-121`, and the `_row_chip`
  docstring. The third was found by the mechanical check below, not by reading — see §3a.
- Both state the real reason, in wording consistent with `OME-820` and the scoreboard portal, so the
  three copies cannot drift apart again.
- **Not** a mere deletion of the word: a removal with no recorded justification is how the control
  gets re-added.
- No executable line changes. The removal `#601` made was correct and is not revisited here.

### 3a Correction (2026-08-15) — three occurrences, and one is not a comment

Drafted as "two comments". Checking mechanically rather than by eye found a **third** in the
`_row_chip` docstring, which is a **string literal, not a comment** — so the acceptance criterion
"the diff touches comment lines only" was itself wrong.

Restated: the diff must touch **no executable statement**. Comment and docstring text may change.
Verified that the docstring is inert here — nothing in `src/`, `tests/` or `scripts/` reads
`__doc__`, there are no doctests, and `_row_chip` is private.

## 4. Out of scope

Restoring the chip or the filter, giving the flag a real signal, and re-emitting `data-verified` — all
`OME-821`. This ticket only makes the record true.

## 5. Acceptance

- No comment in the file claims the field is uniform.
- The recorded reason matches `OME-820` / `OME-821` / the scoreboard portal.
- The diff touches no executable statement, verified by comparing tokenized source rather than by
  reading the diff.
- Full gates green.
