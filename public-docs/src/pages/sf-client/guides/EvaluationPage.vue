<script setup lang="ts">
import DocLayout from '@/components/layout/DocLayout.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const run = `import screamingface as sf

haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")
report = sf.evaluate(haiku, benchmark="ifeval", limit=3)
report`
const runOut = `Report(benchmark='ifeval', candidates=['claude-haiku-4.5'], ok=True)`

const score = `c = report.candidates.only
c.name, c.score, report.case_count, report.benchmark`
const scoreOut = `('claude-haiku-4.5', 1.0, 3, BenchmarkInfo(id='ifeval', revision='22ca96fe77b0f7de', case_count=541))`

const metrics = `dict(c.metrics)`
const metricsOut = `{'inst_level_strict_accuracy': 1.0,
 'prompt_level_loose_accuracy': 1.0,
 'inst_level_loose_accuracy': 1.0,
 'pass_at_1': 1.0,
 'pass_at_2': 1.0,
 'pass_at_3': 1.0,
 'corrected_cases': 0.0,
 'cases_checked': 3.0,
 'cases_fallback': 0.0}`

const many = `opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

sf.evaluate([opus, gpt, sf.Fusion([opus, gpt])], benchmark="draco", limit=1)`

const compare = `corr = sf.evaluate(haiku, benchmark="ifeval", limit=3)
base = sf.evaluate(haiku, benchmark="ifeval", limit=3, method="single_pass")

{"corrective":  {"score": corr.candidates.only.score, "tokens": corr.usage.output_tokens},
 "single_pass": {"score": base.candidates.only.score, "tokens": base.usage.output_tokens}}`
const compareOut = `{'corrective': {'score': 1.0, 'tokens': 3686},
 'single_pass': {'score': 1.0, 'tokens': 1167}}`

const usage = `report.usage`
const usageOut = `Usage(input_tokens=3691, output_tokens=3686, cache_read_tokens=0,
      cache_creation_tokens=0, reasoning_tokens=0, cost_usd=Decimal('0'))`

const watch = `def observe(event: sf.Event) -> None:
    print(event.kind)

sf.evaluate(haiku, benchmark="ifeval", limit=1, on_event=observe, progress=False)`

const clients = `client = sf.Client(engine_url="https://engine.example.com")
report = client.evaluate(haiku, benchmark="ifeval", limit=3)
client.close()

# or module-level, once, for every later call
sf.configure(engine_url="https://engine.example.com")
sf.close()`
</script>

<template>
  <DocLayout
    title="Running an evaluation"
    description="Evaluate one or many candidates against a benchmark and get one Report."
    :navigation="navigation"
    :version="version"
  >
    <p>
      <code>sf.evaluate()</code> is the one call that spends money. You hand it candidates and a
      benchmark id; it compiles each candidate against that benchmark's pinned protocol, runs them
      concurrently on the engine, and returns a single <code>Report</code>.
    </p>

    <p>
      Everything expensive is on the far side of this call. Validation happens first and entirely —
      an unknown benchmark, an unreachable route, a malformed candidate all fail
      <strong>before the first paid request</strong>.
    </p>

    <h2>What you can do with it</h2>

    <ul>
      <li>Evaluate one candidate, or several in one run.</li>
      <li>Cap how many cases run with <code>limit</code>.</li>
      <li>Choose a protocol variant with <code>method</code>.</li>
      <li>Watch the run as it happens, or silence the progress display.</li>
      <li>Run against an explicit client, synchronously or with <code>await</code>.</li>
    </ul>

    <h2>Main APIs</h2>

    <ul>
      <li>
        <code
          >sf.evaluate(candidates, *, benchmark, limit=None, method=None, on_event=None,
          progress=None)</code
        >
        — run candidates against a benchmark, returns <code>sf.Report</code>
      </li>
      <li>
        <code>sf.Client.evaluate(...)</code> · <code>await sf.AsyncClient.evaluate(...)</code> — the
        same call on an explicit client
      </li>
      <li><code>sf.configure(engine_url=…)</code> — repoint the shared client</li>
      <li><code>sf.close()</code> — release the shared client</li>
    </ul>

    <h2>How to</h2>

    <h3>Evaluate one candidate</h3>

    <p>
      The benchmark id is <strong>required</strong> — there is no default and no implicit choice.
      <code>limit</code> caps the case count, and it is your main cost control.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="run"><NbTextOut :text="runOut" /></NbCell>
    </div>

    <p>
      The repr is a summary: which benchmark, which candidates, and whether anything failed.
      <code>ok</code> is <code>True</code> only when no candidate and no member recorded a failure.
    </p>

    <h3>Read the score</h3>

    <p>
      Scores live on candidates, not on the report — a report may hold several. With one candidate,
      <code>.only</code> is the direct way to it.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="score"><NbTextOut :text="scoreOut" /></NbCell>
    </div>

    <p>
      Note the two case counts. <code>report.case_count</code> is how many cases <em>ran</em>;
      <code>report.benchmark.case_count</code> is how many the benchmark has. Running 3 of 541 is a
      smoke test, and the report says so rather than letting you forget.
    </p>

    <p>
      <code>score</code> is always higher-is-better and may be <code>None</code> if a candidate
      failed. Benchmark-specific diagnostics live under <code>metrics</code>:
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="metrics"><NbTextOut :text="metricsOut" /></NbCell>
    </div>

    <h3>Evaluate several at once</h3>

    <p>
      Pass a list. Every candidate runs against the same pinned exam in the same call, which is what
      makes the comparison fair — and it is the only way to compare, because a report has no
      "baseline" or "gain" field. You put the solo model and the ensemble in one run and read both
      scores.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="many" />
    </div>

    <p>
      Results come back in declared order. Mind the cost here: this is DRACO, where every criterion
      is graded by five judge passes, so even <code>limit=1</code> is a real spend.
    </p>

    <h3>Compare two protocols</h3>

    <p>
      Because a <code>method</code> is a different pinned protocol, comparing them is two runs. This
      is IFEval's retry chain against its single-pass baseline, on the same three cases:
    </p>

    <div class="not-prose">
      <NbCell :count="5" :code="compare"><NbTextOut :text="compareOut" /></NbCell>
    </div>

    <p>
      An honest result: identical scores, <strong>3.2× the output tokens</strong>. On this slice the
      retry loop bought nothing — <code>corrected_cases</code> above is <code>0.0</code>, meaning no
      case failed first and passed later. That is what a three-case sample of a capable model looks
      like, and it is the reason to run more cases before concluding anything.
    </p>

    <h3>Read what it cost</h3>

    <div class="not-prose">
      <NbCell :count="6" :code="usage"><NbTextOut :text="usageOut" /></NbCell>
    </div>

    <p>
      <code>cost_usd</code> is <code>Decimal('0')</code> here because this engine has no pricing
      data — a zero means "not reported", not "free". Token counts are the reliable measure. Any
      field is <code>None</code> if even one candidate run failed to report it, rather than being
      silently summed as a partial total.
    </p>

    <h3>Watch a run</h3>

    <p>
      <code>on_event</code> receives typed events in sequence as the run executes, and
      <code>progress=False</code> silences the default display. If your callback raises, the client
      cancels every active run and re-raises your exception.
    </p>

    <div class="not-prose">
      <NbCell :count="7" :code="watch" />
    </div>

    <h3>Use an explicit client</h3>

    <p>
      The module-level functions share one lazily built client pointed at
      <code>http://127.0.0.1:9108</code>. Construct your own to talk to a different engine, or call
      <code>sf.configure()</code> once to repoint the shared one. <code>sf.AsyncClient</code> has
      the same interface with <code>await</code>.
    </p>

    <div class="not-prose">
      <NbCell :count="8" :code="clients" />
    </div>

    <h2>When it fails</h2>

    <p>
      <code>PlanningError</code> means the run never started — change the candidate, benchmark or
      configuration. <code>ExecutionError</code> means it reached the engine and ended without a
      valid report. <code>EngineUnavailableError</code> means the engine was not reachable at all.
      Each carries a stable <code>code</code> and a <code>hint</code>.
    </p>

    <h2>Links</h2>

    <ul>
      <li>
        <a
          href="https://github.com/OpenMined/screamingface/blob/OME-605-screamingface-client-v1/packages/screamingface/examples/05_draco_e2e.ipynb"
          target="_blank"
          rel="noopener"
          >Companion notebook — <code>05_draco_e2e.ipynb</code></a
        >
      </li>
    </ul>
  </DocLayout>
</template>
