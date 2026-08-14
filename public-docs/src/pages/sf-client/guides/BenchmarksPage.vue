<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const listing = `import screamingface as sf

for b in sf.benchmarks.list():
    print(b.id, "|", b.case_count, "cases |", b.revision)`
const listingOut = `draco | 100 cases | 1c58b3085912e304
healthbench-worst30 | 157 cases | 6cd57aee171fbdc4
ifeval | 541 cases | 0b88a52b5f10a6d9`

const card = `ifeval = sf.benchmarks.get("ifeval")
ifeval`
const cardOut = `Benchmark(id='ifeval', title='IFEval',
description='The canonical 541-prompt instruction-following benchmark
(https://arxiv.org/abs/2311.07911), graded by deterministic strict and loose
verification. Each Case invokes the Candidate exactly once. Case ids are the
official IFEval keys; one pinned-dataset row (key 2785) is patched to the
official harness prompt, whose text matches its graded constraints.',
revision='0b88a52b5f10a6d9', case_count=541)`

const strategies = `model = sf.Model("openrouter/anthropic/claude-haiku-4.5")
corrective = sf.SelfCorrective(model, max_rounds=3)

plain = sf.evaluate(model, benchmark="ifeval", limit=3)
retried = sf.evaluate(corrective, benchmark="ifeval", limit=3)`
</script>

<template>
  <DocLayout
    title="Benchmarks"
    description="Discover the benchmarks an engine publishes and pick the protocol you want to run."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>benchmark</strong> is the exam. It is owned entirely by
      <RouterLink to="/learn/engine">the engine</RouterLink> and it owns everything about how
      candidates are judged: which cases exist, in what order they are asked, which judge model
      grades them, how grades become a score. Your candidate answers; it does not get a say in any
      of that.
    </p>

    <p>
      That split is the point. Because the exam is fixed and pinned, a solo Model and a
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink> evaluated against it are
      genuinely comparable.
    </p>

    <h2>What you can do with it</h2>

    <ul>
      <li>List the benchmarks this engine publishes.</li>
      <li>Read one's identity card: size, revision, and what it actually measures.</li>
      <li>Use <code>limit=</code> to rehearse on fewer cases without changing the protocol.</li>
      <li>Check that two results are comparable by comparing revisions.</li>
    </ul>

    <h2>Main APIs</h2>

    <table>
      <thead>
        <tr>
          <th>API</th>
          <th>What it does</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>sf.benchmarks.list()</code></td>
          <td>
            Lists every benchmark this engine publishes, a free discovery request that calls no
            model.
          </td>
        </tr>
        <tr>
          <td><code>sf.benchmarks.get(benchmark_id)</code></td>
          <td>Fetches one benchmark's identity card by its flat id.</td>
        </tr>
        <tr>
          <td>
            <code>sf.Benchmark</code> <code>.id</code> <code>.title</code> <code>.description</code>
            <code>.revision</code> <code>.case_count</code>
          </td>
          <td>
            The identity card itself: its id, what it measures, the opaque revision hash of the
            pinned protocol, and its size.
          </td>
        </tr>
        <tr>
          <td><code>sf.BenchmarkInfo</code></td>
          <td>
            The pinned subset a report carries, so an old result still names the exact revision it
            ran against.
          </td>
        </tr>
      </tbody>
    </table>

    <p>
      <strong>Discovery is free.</strong> Listing benchmarks and reading identity cards are plain
      engine requests; no model is called and nothing is charged. Only
      <RouterLink to="/sf-client/guides/running-an-evaluation">evaluation</RouterLink> spends.
    </p>

    <h2>How to</h2>

    <h3>1 · See what this engine publishes</h3>

    <div class="not-prose">
      <NbCell :count="1" :code="listing"><NbTextOut :text="listingOut" /></NbCell>
    </div>

    <p>
      Three benchmarks, each with one public identity, and they differ in what grading costs.
      <strong>DRACO</strong> is 100 deep-research tasks graded by a judge model
      (<code>openrouter/google/gemini-3.1-pro-preview</code>) with five independent passes per
      criterion. <strong>IFEval</strong> is 541 instruction-following prompts checked by a
      deterministic verifier, so its grading is <strong>free</strong> and only the answers cost
      anything. <strong>HealthBench</strong> exposes the worst-30% subset, rubric-graded by a judge.
    </p>

    <h3>2 · Read the identity card</h3>

    <div class="not-prose">
      <NbCell :count="2" :code="card"><NbTextOut :text="cardOut" /></NbCell>
    </div>

    <p>
      The <code>revision</code> is an opaque hash of the pinned protocol, and it is stamped into
      every report produced against it. That is what keeps old results attributable: if the public
      name later points at a newer snapshot, your report still names the revision it actually ran.
    </p>

    <h3>3 · Keep Candidate strategy separate</h3>

    <p>
      The benchmark remains the fixed exam. A Model, Fusion, Pipeline, SelfCorrective, or
      CorrectiveLoop is the Candidate strategy taking that exam. Changing the Recipe does not invent
      another benchmark id; the report records both the benchmark revision and the compiled
      Candidate topology explicitly.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="strategies" />
    </div>

    <p>
      Both runs use the same IFEval cases, checker, and aggregation. They differ only in how the
      Candidate produces one answer. Use <code>limit=</code> for a smaller rehearsal; it selects
      fewer cases but never weakens the benchmark's checking or scoring protocol.
    </p>

    <h3>4 · Know what discovery will not tell you</h3>

    <p>
      A <code>Benchmark</code> carries no case data, so the prompts cannot be paged before a run.
      Cases and their answer keys stay on the engine, and that separation is what makes a verified
      result meaningful rather than self-reported. The case text a candidate received, its answer,
      and the grade behind it all arrive with the report afterwards, on
      <RouterLink to="/sf-client/api/reports">CandidateResult.cases</RouterLink>.
    </p>

    <h2>Links</h2>

    <ul>
      <li>
        <a
          href="https://github.com/OpenMined/screamingface/blob/main/packages/screamingface/examples/07_ifeval_e2e.ipynb"
          target="_blank"
          rel="noopener"
          >Companion notebook: <code>07_ifeval_e2e.ipynb</code></a
        >
      </li>
    </ul>
  </DocLayout>
</template>
