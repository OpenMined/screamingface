# IFEval protocol-fidelity audit

Date: 2026-08-04
Baseline audited: Khoa's PR head `2315751d4ed53f222fe37d7af130f248b91b8521`
Scope: canonical IFEval, the proposed solo self-corrective Variant, and the LANL
verifying-ensemble Variant.

## Bottom line

The manifest refactor can preserve Khoa's current output-selection and scoring rules,
but **Khoa's baseline and the published LANL protocol are not execution-equivalent**.
It is therefore impossible to claim both "byte-for-byte Khoa behavior" and "exact LANL
protocol" without first correcting the baseline differences below.

| Variant | Fidelity conclusion |
| --- | --- |
| `canonical` | The one-answer/check flow and four IFEval metrics are substantially correct. One source-data row differs from the official harness, official case keys are renumbered, and crash handling deliberately differs. |
| `self-corrective` | This is an OpenMined/Khoa ablation, **not a protocol evaluated in either source paper**. It needs its own description and revision and must not be presented as LANL reproduction. |
| `verifying-ensemble` | The main roles are correct, but unconditional three-round execution, unconditional judge calls, supported member counts, and missing study configuration differ materially from LANL. |

## 1. Canonical IFEval contract

The original benchmark has 541 prompts, 25 verifier types, and one to three
instructions per prompt. The supplied official-source data contains 834 instruction
instances. One model response is produced for each prompt and checked by deterministic
programs. The four published metrics are:

1. prompt-level strict accuracy (all instructions in a prompt pass),
2. instruction-level strict accuracy,
3. prompt-level loose accuracy, and
4. instruction-level loose accuracy.

Loose evaluation accepts the identity response plus seven variants formed by removing
Markdown `*` markers and/or the first and last line. These definitions are explicit in
the [IFEval paper, sections 2.2 and 3](https://arxiv.org/abs/2311.07911) and the
[official evaluator](https://github.com/google-research/google-research/blob/master/instruction_following_eval/evaluation_lib.py#L119-L168).

Khoa's canonical program correctly invokes the Candidate once and the checker once per
case ([definition.py lines 42-77](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/definition.py#L42-L77)).
Its checker reproduces the official eight strict/loose inputs, and its reducer exposes
strict prompt accuracy as `score` plus the other three metrics
([grading.py lines 33-53 and 99-111](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/grading.py#L33-L111),
[aggregate.py lines 76-94](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/aggregate.py#L76-L94)).
The vendored verifier files match the supplied fork at commit
`0c495b2f95155e8b10acb919ae283bfb4d5be6e2` except for import packaging and source
banners.

### Canonical discrepancies

- **One prompt is not the official-harness prompt.** The pinned Hugging Face snapshot
  `google/IFEval@966cd89545d6b6acfd7638bc708b98261ca58e84` is normalized-identical to the
  supplied official harness data on 540/541 rows. For key `2785`, HF says "at least one
  placeholder" while its own checker kwargs require 3; the official Google/fork input
  says "at least 3 placeholders." See the
  [official data row](https://github.com/google-research/google-research/blob/master/instruction_following_eval/data/input_data.jsonl#L340).
  Exact canonical reproduction should use the official row or explicitly document a
  different pinned HF-data Variant.
- **Case identity changes.** `prepare.py` replaces the official `key` with sequential
  IDs `1..541`. Scores are unchanged, but per-case artifacts no longer join directly to
  official results. Preserve the official key as the public/report case ID.
- **Harness failures score differently.** Khoa converts verifier exceptions to a failed
  instruction and recordless rows to fail-all, whereas the official evaluator raises.
  This is a defensible production policy but an intentional protocol divergence that
  should be reported as harness status rather than silently treated as model failure.
- **The exact 2023 code revision is unknowable from the paper alone.** The paper links
  an unpinned repository; Khoa pins a later bug-fixed fork. The pin is reproducible, but
  "byte-identical 2023 harness" cannot be claimed without the authors' historical
  revision.
- **Known native randomness remains.** Invalid non-ASCII/special inputs to the official
  letter-frequency checker are replaced with a random ASCII letter. LANL explicitly
  retained this "Non-ASCII Roulette" behavior for comparability
  ([LANL paper, appendix A.4](https://openreview.net/pdf?id=XSIYfTm2h7)). Khoa preserves
  it, but rebuilding a failed-instruction description can choose a different random
  letter from the one actually checked. A run must record the effective constraint or
  RNG state if exact replay is required.

## 2. Self-corrective is an explicit extension

Neither Zhou et al. nor Skurikhin et al. evaluates a standalone model that writes a
draft, receives deterministic violations, authors feedback to itself in a separate
model call, and retries. Khoa's source itself calls this an ablation the LANL study
"never ran" ([iterative_correction.py lines 1-18](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L1-L18)).

Therefore `ifeval/self-corrective` is a valid product/research Variant, but its exact
protocol is **our** contract. If preserving Khoa's baseline, that contract is:

- three answer attempts,
- a strict and loose deterministic check after each answer,
- after attempts 1 and 2, one additional Candidate call authors self-feedback from the
  sanitized verifier descriptions,
- the next answer receives the previous answer plus that authored feedback,
- earliest strict pass determines the score, otherwise the last recorded attempt does.

Khoa currently executes all three attempts and both feedback calls even after an early
pass ([lines 111-164](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L111-L164)).
That must be described as "exactly three attempts" rather than "at most three," or changed
to early stopping as a deliberate new revision.

## 3. Published LANL verifying-ensemble protocol

For each of the same 541 IFEval prompts, the LANL paper specifies this state machine:

1. all ensemble members independently answer the same prompt;
2. the programmatic IFEval checker evaluates each answer;
3. if exactly one answer passes every constraint, that compliant answer is accepted;
4. if multiple answers pass, the SLM judge only tie-breaks among those compliant
   answers;
5. if no answer passes, the judge turns checker violations into targeted natural-language
   feedback for the members;
6. repeat for at most two corrective rounds, for **at most three attempts total**.

The paper separates generator, deterministic verifier, and judge responsibilities, and
does not describe the judge as rewriting the final answer
([LANL paper, section 2, pp. 1-2](https://openreview.net/pdf?id=XSIYfTm2h7)). Khoa's use
of the Fusion synthesizer as the judge is faithful because the paper treats the judge as
part of the ensemble under test and varies it independently. Returning the selected
member answer verbatim is also faithful and safely prevents a compliant answer from
being damaged during synthesis
([runtime.py lines 153-191](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/runtime.py#L153-L191)).

The paper does not literally name the loop's pass gate as `strict`; it says that an
answer "satisfies all constraints" and plots cumulative **strict** prompt accuracy over
attempts. Strict all-instructions gating is therefore the strongest source-supported
reading and matches Khoa. Loose prompt accuracy is reported as a complementary metric,
not described as a retry gate. This remains an inference until the authors' harness is
available.

### LANL discrepancies in Khoa's baseline

| Topic | LANL | Khoa baseline |
| --- | --- | --- |
| Stopping | At most 3; stop when a compliant output is available. | All 3 rounds always execute. Earliest-pass aggregation hides the extra work from the final score. |
| Judge selection | Called only to tie-break when multiple candidates pass. | Judge-pick is called every round, including zero- and one-passer rounds. |
| Judge feedback | Called only when no candidate passes and another attempt remains. | Called after rounds 1 and 2 regardless of pass state. |
| Member retries | Only after a no-pass round. | Every member retries in rounds 2 and 3 even after success. |
| Published member count | Every reported ensemble has exactly 2 members. | Accepts 2-4 members. This is a useful extension, not the published experiment. |
| Exact judge/retry prompts | Not published in the paper. | Locally authored prompts; fidelity cannot be independently confirmed. |
| Final all-fail selection | Paper does not fully specify the final fallback; it motivates maximal constraint satisfaction. | Judge letter selects an answer, with first-member fallback. |

The unconditional behavior is visible in the nested loops and unconditional judge calls
([iterative_correction.py lines 183-286](https://github.com/OpenMined/screamingface/blob/2315751d4ed53f222fe37d7af130f248b91b8521/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L183-L286)).
For a published two-member ensemble that obtains one passing answer on round 1, LANL
needs 2 generator calls and no judge call; Khoa performs 6 generator calls, 3 judge-pick
calls, and 2 judge-feedback calls. Accuracy may match, but cost, tokens, latency, and
goodput cannot match - and those are central reported outcomes of the LANL paper.

### Exact published configurations

All five LANL ensembles have two direct members (Table 1):

| Configuration | Judge | Members |
| --- | --- | --- |
| Ens-1 | `gemini-3.1-flash-lite-preview` | `gpt-5.4-mini`, `gemini-3.1-flash-lite-preview` |
| Ens-2 | `gpt-5.4-mini` | `gpt-5.4-mini`, `gemini-3.1-flash-lite-preview` |
| Ens-3 | `gpt-5.4-mini` | `gpt-5.4-mini`, `llama-4-scout` |
| Ens-4 | `gpt-5.4-mini` | `gpt-5.4-mini`, `claude-haiku-4-5` |
| Ens-5 | `gpt-5.4-mini` | `gpt-5.4-mini`, `mistral-small-4` |

The best reported result (97.34% strict prompt accuracy) is Ens-1. Each configuration
was run five times and reported as mean plus standard deviation
([LANL paper, section 3 and Table 1](https://openreview.net/pdf?id=XSIYfTm2h7)). Arbitrary
user-selected Fusions evaluate the same protocol but are not a reproduction of those
published configurations.

## 4. What "protocol exact" requires before merge

1. **Canonical data parity:** 541 official keys and prompts, 834 instruction instances,
   with key 2785 resolved to the official-harness wording.
2. **Canonical scorer parity:** golden-response comparison against the official evaluator
   for all four global metrics and all per-case strict/loose verdict vectors.
3. **Real LANL control flow:** test unique-pass round 1, multi-pass round 1, no-pass then
   pass round 2, and all-fail round 3; assert both selected text and exact generator/judge
   call counts.
4. **Role isolation:** the judge may choose only among compliant answers when passers
   exist; it writes feedback only when none pass; selected final text is always a member
   answer verbatim.
5. **Published-profile fixture:** provide the five exact two-member/judge recipes above.
   Keep support for 3-4 members clearly labelled as an extension.
6. **Study-level reproduction:** run each configuration five times and retain per-attempt
   outputs, verifier results, token classes, costs, timing, and instruction-category /
   constraint-count slices. A single aggregate `Report` does not reproduce the LANL
   tokenomics study.
7. **Author confirmation:** obtain the LANL source harness or at least its exact prompts,
   generation parameters, feedback payload shape, stopping code, and final all-fail rule.
   The paper alone does not expose enough detail to honestly certify 100% implementation
   identity.

The one-fetch family manifest, explicit Variants, and dynamic `$candidate_members`
binding are orthogonal to these semantics. They can replace `?members=N` without changing
the protocol, provided the URL4 implements the conditional state machine above rather
than merely preserving the baseline's unconditional unroll.

## Primary-source ledger

- [Zhou et al., *Instruction-Following Evaluation for Large Language Models*](https://arxiv.org/abs/2311.07911)
- [Official Google IFEval code and data](https://github.com/google-research/google-research/tree/master/instruction_following_eval)
- [Skurikhin et al., *Beyond Leaderboards: Tokenomics of Agentic Small Language Model Ensembles*](https://openreview.net/pdf?id=XSIYfTm2h7)
- Supplied source kit: `/Users/kj/Desktop/IFEval.zip` (HF dataset revision
  `966cd89545d6b6acfd7638bc708b98261ca58e84`; verifier fork revision
  `0c495b2f95155e8b10acb919ae283bfb4d5be6e2`)
- [Khoa PR baseline at commit `2315751d`](https://github.com/OpenMined/screamingface/tree/2315751d4ed53f222fe37d7af130f248b91b8521)
