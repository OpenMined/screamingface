<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const get = `plan = report.candidates.only.url4
len(plan)`
const getOut = `1402`

const audit = `print("candidate slots :", plan.count("/candidate("))
print("checker calls   :", plan.count("/check("))
print("revision pinned :", report.benchmark.revision in plan)`
const auditOut = `candidate slots : 3
checker calls   : 3
revision pinned : True`

const ops = `c = report.candidates.only
len(c.operations), [o.kind for o in c.operations]`
const opsOut = `(1, ['model'])`

const runId = `c.run_id`
const runIdOut = `'z4DrOL5qGcURcfEVB6evxPDlHyg0T2Cwjso10dJ1p5O4TocWXK5FLcYgdbPcnSnQ'`

const share = `report.to_dict()   # schema: screamingface.report.v1
report.to_json()   # the same, as one string`
</script>

<template>
  <DocLayout
    title="Reproduce &amp; share (URL4)"
    description="Read the exact plan a run executed, and hand it to someone else."
    :navigation="navigation"
    :version="version"
  >
    <p>
      Every candidate result carries a <code>url4</code> string: the complete expression the engine
      executed. Not a summary of it, not a log of it — the plan itself, the thing that ran. Your
      candidate, the benchmark's routes, the retry prompts, and the pinned protocol revision, all in
      one line of text you can read, diff, and send to someone.
    </p>

    <p>
      This is what makes a result auditable. A score on its own is a claim; a score with its URL4
      shows exactly what produced it.
    </p>

    <h2>What you can do with it</h2>

    <ul>
      <li>Read what actually executed, including defaults you never set.</li>
      <li>Confirm which benchmark revision the run was pinned to.</li>
      <li>Inspect the operation graph a candidate compiled to.</li>
      <li>Serialise a whole report and hand it over.</li>
    </ul>

    <h2>Main APIs</h2>

    <ul>
      <li><code>CandidateResult.url4</code> — the expression that executed</li>
      <li>
        <code>CandidateResult.operations</code> — the same plan as an
        <code>sf.OperationInfo</code> DAG
      </li>
      <li><code>CandidateResult.run_id</code> — the engine's identifier for this run</li>
      <li><code>Report.benchmark.revision</code> — the pinned protocol the run used</li>
      <li>
        <code>Report.to_dict()</code> · <code>Report.to_json()</code> — the whole report, serialised
      </li>
    </ul>

    <h2>How to</h2>

    <h3>Get the plan</h3>

    <div class="not-prose">
      <NbCell :count="1" :code="get"><NbTextOut :text="getOut" /></NbCell>
    </div>

    <p>
      Fourteen hundred characters for a three-case run of one model. That length is the point: it
      spells out the resolved answer prompt, the generation parameters, every benchmark route, and
      the retry chain — including everything the SDK filled in on your behalf.
    </p>

    <h3>Audit it without reading all of it</h3>

    <p>It is a string, so plain string operations answer real questions about what ran.</p>

    <div class="not-prose">
      <NbCell :count="2" :code="audit"><NbTextOut :text="auditOut" /></NbCell>
    </div>

    <p>
      Three candidate slots and three checker calls, from a run over three cases with IFEval's
      corrective method — the retry chain is <em>unrolled</em> into the expression rather than being
      a loop the engine hides. Every attempt is visible before anything executes, which is also why
      every attempt is paid for even when the first one passes.
    </p>

    <p>
      <code>revision pinned : True</code> is the important one. The benchmark's protocol revision
      appears inside the routes, so the expression cannot silently execute against a newer version
      of the exam.
    </p>

    <h3>Inspect the operation graph</h3>

    <p>
      <code>operations</code> is the same plan as structured data — a directed acyclic graph of
      <code>OperationInfo</code> values, each with an <code>id</code>, a <code>kind</code>, a
      <code>label</code> and its <code>depends_on</code> edges.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="ops"><NbTextOut :text="opsOut" /></NbCell>
    </div>

    <p>
      A solo model is one operation. A
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink>
      contributes one per member plus the synthesis step, so this is where you read a fusion's shape
      rather than inferring it from its name.
    </p>

    <h3>Identify the run</h3>

    <div class="not-prose">
      <NbCell :count="4" :code="runId"><NbTextOut :text="runIdOut" /></NbCell>
    </div>

    <h3>Share the whole report</h3>

    <div class="not-prose">
      <NbCell :count="5" :code="share" />
    </div>

    <p>
      The dict carries a <code>schema</code> field — <code>screamingface.report.v1</code> — so a
      consumer can tell what shape it is reading. Every candidate's <code>url4</code>, scores,
      metrics, usage and the pinned benchmark revision travel with it.
    </p>

    <h2>What "reproduce" means here</h2>

    <p>
      A URL4 pins the run's <strong>definition</strong>, not its outputs. Re-executing the same
      expression asks the same models the same questions under the same protocol — and models are
      not deterministic, so the scores will move. What is reproducible is the experiment, not the
      number.
    </p>

    <p>
      That is the useful guarantee. When two results differ, the URL4 tells you whether the
      <em>setup</em> differed, which is the question you actually need answered before comparing
      them.
    </p>

    <h2>Links</h2>

    <ul>
      <li>
        <a
          href="https://github.com/OpenMined/screamingface/blob/OME-605-screamingface-client-v1/packages/screamingface/examples/07_ifeval_e2e.ipynb"
          target="_blank"
          rel="noopener"
          >Companion notebook — <code>07_ifeval_e2e.ipynb</code></a
        >, which prints a full expression
      </li>
    </ul>
  </DocLayout>
</template>
