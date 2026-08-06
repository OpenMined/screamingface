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
    print(b.id, "|", b.title, "|", b.case_count, "cases |", b.revision)`
const listingOut = `draco | DRACO | 100 cases | defbb6efdae69211
ifeval | IFEval | 541 cases | 22ca96fe77b0f7de`

const card = `ifeval = sf.benchmarks.get("ifeval")
ifeval`
const cardOut = `Benchmark(id='ifeval', title='IFEval', description="The 541-prompt
instruction-following benchmark (https://arxiv.org/abs/2311.07911) with
deterministic verification. Default method 'corrective' reproduces the protocol
of 'Beyond Leaderboards: Tokenomics of Agentic Small Language Model Ensembles'
(Skurikhin et al., Los Alamos National Laboratory) — a bounded 3-attempt retry
chain fed by the checker's violations (3x candidate calls; scores are NOT
comparable to published single-pass IFEval numbers). Select method 'single_pass'
for the paper-comparable protocol.", revision='22ca96fe77b0f7de',
case_count=541)`

const methods = `sf.benchmarks.get("ifeval").revision, sf.benchmarks.get("ifeval", method="single_pass").revision`
const methodsOut = `('22ca96fe77b0f7de', '047f1de449639c61')`

const cases = `for c in ifeval.cases(limit=2):
    print(c.id, "|", c.input[:120])`
const casesOut = `1 | Write a 300+ word summary of the wikipedia page "https://en.wikipedia.org/wiki/Raymond_III,_Count_of_Tripoli". Do not us …
2 | I am planning a trip to Japan, and I would like thee to write an itinerary for my journey in a Shakespearean style. You  …`
</script>

<template>
  <DocLayout
    title="Benchmarks"
    description="Discover Engine-owned benchmarks and read their cases before spending."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>benchmark</strong> is the exam. It is owned entirely by the engine and it owns
      everything about how candidates are judged: which cases exist, in what order they are asked,
      which judge model grades them, how grades become a score. Your candidate answers; it does not
      get a say in any of that.
    </p>

    <p>
      That split is the point. Because the exam is fixed and pinned, a solo Model and a
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink> evaluated against it are
      genuinely comparable.
    </p>

    <h2>What you can do with it</h2>

    <ul>
      <li>List the benchmarks this engine publishes.</li>
      <li>Read one's identity card — size, revision, and what it actually measures.</li>
      <li>Page its real prompts before spending anything.</li>
      <li>Select a protocol variant with <code>method</code>.</li>
    </ul>

    <h2>Main APIs</h2>

    <ul>
      <li><code>sf.benchmarks.list()</code> — every benchmark this engine publishes</li>
      <li>
        <code>sf.benchmarks.get(id, *, method=None)</code> — one benchmark's identity card, for a
        chosen protocol
      </li>
      <li>
        <code>sf.Benchmark</code> — that card: <code>.id</code> <code>.title</code>
        <code>.description</code> <code>.revision</code> <code>.case_count</code>
        <code>.cases(limit, offset)</code>
      </li>
      <li><code>sf.BenchmarkInfo</code> — the pinned subset a report carries</li>
      <li><code>sf.CaseInfo</code> — one case's <code>id</code> and <code>input</code></li>
    </ul>

    <p>
      <strong>All of this is free.</strong> Discovery and case browsing are plain engine requests;
      no model is called and nothing is charged. Only
      <RouterLink to="/sf-client/guides/running-an-evaluation">evaluation</RouterLink> spends.
    </p>

    <h2>How to</h2>

    <h3>See what this engine publishes</h3>

    <div class="not-prose">
      <NbCell :count="1" :code="listing"><NbTextOut :text="listingOut" /></NbCell>
    </div>

    <p>
      Two benchmarks, and they differ in what grading costs. <strong>DRACO</strong> is 100
      deep-research tasks graded by a judge model
      (<code>openrouter/google/gemini-3.1-pro-preview</code>) with five independent passes per
      criterion — the grading itself is the expensive part. <strong>IFEval</strong> is 541
      instruction-following prompts checked by a deterministic verifier, so its grading is
      <strong>free</strong>: only the answers cost anything.
    </p>

    <h3>Read the identity card</h3>

    <div class="not-prose">
      <NbCell :count="2" :code="card"><NbTextOut :text="cardOut" /></NbCell>
    </div>

    <p>
      The <code>revision</code> is an opaque hash of the pinned protocol, and it is stamped into
      every report produced against it. That is what keeps old results attributable: if the public
      name later points at a newer snapshot, your report still names the revision it actually ran.
    </p>

    <h3>Select a method</h3>

    <p>
      Some benchmarks publish more than one protocol. IFEval's default is <code>corrective</code> —
      a bounded three-attempt retry chain fed by the verifier's complaints.
      <code>single_pass</code> is one answer, one check, and it is the only variant comparable to
      published IFEval numbers.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="methods"><NbTextOut :text="methodsOut" /></NbCell>
    </div>

    <p>
      Notice the revisions differ. A method is not a flag on one exam — it is a
      <strong>different pinned protocol</strong>, with a different cost and a score that means
      something different. Comparing a corrective score against a single-pass one is a mistake the
      revisions let you catch.
    </p>

    <h3>Read the cases before you spend</h3>

    <p>
      <code>cases()</code> pages the real prompts, 50 at a time by default. For IFEval this is worth
      doing: each prompt carries its own constraints in its text — "300+ words", "no commas",
      "highlight three sections" — which is exactly what makes it machine-checkable.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="cases"><NbTextOut :text="casesOut" /></NbCell>
    </div>

    <p>
      A <code>CaseInfo</code> carries only its <code>id</code> and <code>input</code>. Grading
      criteria, rubrics and answer keys never cross the engine boundary — you can read the exam
      questions, not the marking scheme.
    </p>

    <h2>Links</h2>

    <ul>
      <li>
        <a
          href="https://github.com/OpenMined/screamingface/blob/OME-605-screamingface-client-v1/packages/screamingface/examples/07_ifeval_e2e.ipynb"
          target="_blank"
          rel="noopener"
          >Companion notebook — <code>07_ifeval_e2e.ipynb</code></a
        >
      </li>
    </ul>
  </DocLayout>
</template>
