<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const read = `opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

opus.url4                     # a single model's plan
sf.Fusion([opus, gpt]).url4   # a fusion's plan`

const remix = `plan = report.candidates["frontier-trio"].url4   # or any url4 string you were given
candidate = sf.from_url4(plan)                    # rebuild it as a runnable candidate
sf.evaluate([candidate], benchmark="draco-lite@1")`

const ops = `c = report.candidates.only
len(c.operations), [o.kind for o in c.operations]`
const opsOut = `(1, ['model'])`

const runId = `c.run_id`
const runIdOut = `'z4DrOL5qGcURcfEVB6evxPDlHyg0T2Cwjso10dJ1p5O4TocWXK5FLcYgdbPcnSnQ'`

const share = `report.to_dict()   # schema: screamingface.report.v1
report.to_json()   # the same, as one string`

const readable = `(member_1:0.0:/openrouter/anthropic/claude-opus-4.8?temperature=0&max_tokens=8192&q=($question)!'You are answering a research-quality prompt. …', recipe_result:0.0:{schema: 'screamingface.recipe-result.v1', members: {member_1: {model: 'openrouter/anthropic/claude-opus-4.8', answer: '$member_1'}}, answer: '$member_1'})!'$recipe_result'`
</script>

<template>
  <DocLayout
    title="Reproduce &amp; share (url4)"
    description="Read the exact plan a run executed, and hand it to someone else."
    :navigation="navigation"
    :version="version"
  >
    <p>
      Every candidate result carries a <RouterLink to="/learn/url4"><code>url4</code></RouterLink>
      string: the complete expression <RouterLink to="/learn/engine">the engine</RouterLink>
      executed. Not a summary of it, not a log of it: the plan itself, the thing that ran. Your
      candidate, the benchmark's routes, the retry prompts, and the pinned protocol revision, all in
      one line of text you can read, diff, and send to someone.
    </p>

    <p>
      The shape is always <code>(sources)!intent</code>: the inputs in parentheses, then what to do
      with them after the <code>!</code>. A source can itself be another url4, so the format is
      recursive, which makes fusions easy to compose.
    </p>

    <figure class="not-prose" style="margin: var(--space-8) 0">
      <svg
        viewBox="0 0 680 196"
        role="img"
        aria-label="A url4 has the shape (sources)!intent: sources in parentheses, then an intent after the bang. A source can itself be another url4, so expressions nest."
        style="width: 100%; height: auto; font-family: var(--f-mono)"
      >
        <defs>
          <marker
            id="u4-arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="6"
            markerHeight="6"
            orient="auto"
          >
            <path d="M0 0 L8 4 L0 8 z" style="fill: var(--text-2)" />
          </marker>
        </defs>
        <g style="stroke: var(--text-2); stroke-width: 1; fill: none">
          <path d="M44 74 V60 H340 V74" />
          <path d="M392 74 V60 H600 V74" />
        </g>
        <g
          text-anchor="middle"
          style="
            fill: var(--text-2);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
          "
        >
          <text x="192" y="50">the inputs</text>
          <text x="496" y="50">what to do with them</text>
        </g>
        <text x="22" y="116" style="fill: var(--text-2); font-size: 26px">(</text>
        <rect
          x="44"
          y="82"
          width="296"
          height="56"
          style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1"
        />
        <text x="192" y="108" text-anchor="middle" style="fill: var(--text); font-size: 14px">
          sources
        </text>
        <text x="192" y="126" text-anchor="middle" style="fill: var(--text-2); font-size: 10px">
          models · data · nested url4
        </text>
        <text x="346" y="116" style="fill: var(--text-2); font-size: 26px">)</text>
        <text x="371" y="117" style="fill: var(--accent); font-size: 26px; font-weight: 600">!</text>
        <rect
          x="392"
          y="82"
          width="208"
          height="56"
          style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1"
        />
        <text x="496" y="108" text-anchor="middle" style="fill: var(--text); font-size: 14px">
          intent
        </text>
        <text x="496" y="126" text-anchor="middle" style="fill: var(--text-2); font-size: 10px">
          a prompt, or code
        </text>
        <path
          d="M120 138 C 120 172, 150 172, 176 172"
          style="stroke: var(--text-2); stroke-width: 1; fill: none"
          marker-end="url(#u4-arrow)"
        />
        <text x="188" y="176" style="fill: var(--text-2); font-size: 11px">
          a source can be another url4, so expressions nest
        </text>
      </svg>
      <figcaption
        style="
          font-family: var(--f-mono);
          font-size: var(--text-label);
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-2);
          margin-top: var(--space-3);
        "
      >
        Every url4 is sources in parentheses, then an intent after the bang.
      </figcaption>
    </figure>

    <p>
      Here is a real one, a single
      <RouterLink to="/sf-client/guides/models">Model</RouterLink> answering one DRACO case (its
      long answer prompt trimmed to <code>…</code>):
    </p>

    <CodeBlock :code="readable" language="text" />

    <p>Read it outside-in:</p>

    <ul>
      <li>
        The outer <code>( … )!'$recipe_result'</code> is the whole run: named sources inside the
        parentheses, and a final intent that returns <code>$recipe_result</code>.
      </li>
      <li>
        <code>member_1</code> is the first source: a call to the model route
        <code>/openrouter/anthropic/claude-opus-4.8</code> with its parameters
        (<code>temperature</code>, <code>max_tokens</code>), the benchmark <code>$question</code>
        bound as <code>q</code>, and its own intent, the answer prompt. The <code>0.0</code> after
        the name is its weight.
      </li>
      <li>
        <code>recipe_result</code> is the second source: a structured value that collects the
        members and names the final answer, here just <code>$member_1</code>.
      </li>
    </ul>

    <p>
      A <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink> reads the same way, with more
      members (<code>member_2</code>, <code>member_3</code>, …) and a <code>recipe_answer</code>
      step, the reducer that reads the members and writes the synthesis, before
      <code>recipe_result</code>. Nothing is hidden: the routes, parameters, prompts, and the pinned
      protocol are all in the line. See <RouterLink to="/learn/url4">url4</RouterLink> for the full
      grammar and protocol.
    </p>

    <p>
      This is what makes a result auditable. A score on its own is a claim; a score with its url4
      shows exactly what produced it. And because the expression is also an address the engine
      resolves, that same string reruns the evaluation, or calls the fusion like a single model, in
      any workflow you drop it into. See <RouterLink to="/learn/url4">url4</RouterLink> for the
      protocol itself.
    </p>

    <h2>What you can do with it</h2>

    <ul>
      <li>Read the <code>url4</code> of any model or fusion, before or after a run.</li>
      <li>Create a new candidate from a <code>url4</code> string, then run or remix it.</li>
      <li>Read what actually executed, including defaults you never set.</li>
      <li>Confirm which benchmark revision the run was pinned to.</li>
      <li>Inspect the operation graph a candidate compiled to.</li>
      <li>Serialise a whole report and hand it over.</li>
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
          <td><code>Model.url4</code> · <code>Fusion.url4</code></td>
          <td>The plan a candidate compiles to, available before any run and free to inspect.</td>
        </tr>
        <tr>
          <td><code>sf.from_url4(url4)</code></td>
          <td>
            Rebuild a runnable candidate from a url4 string, so a shared expression becomes a Model
            or Fusion you can evaluate or remix.
          </td>
        </tr>
        <tr>
          <td><code>CandidateResult.url4</code></td>
          <td>
            The complete expression the engine executed, a string you can read, diff, and rerun.
          </td>
        </tr>
        <tr>
          <td><code>CandidateResult.operations</code></td>
          <td>
            The same plan as structured data: a DAG of <code>sf.OperationInfo</code> values, each
            with an <code>id</code>, <code>kind</code>, <code>label</code> and
            <code>depends_on</code> edges.
          </td>
        </tr>
        <tr>
          <td><code>CandidateResult.run_id</code></td>
          <td>The engine's identifier for this run.</td>
        </tr>
        <tr>
          <td><code>Report.benchmark.revision</code></td>
          <td>The pinned protocol revision the run used, which appears inside the url4's routes.</td>
        </tr>
        <tr>
          <td><code>Report.to_dict()</code> · <code>Report.to_json()</code></td>
          <td>
            Serialise the whole report, as a dict or one JSON string, carrying schema
            <code>screamingface.report.v1</code>.
          </td>
        </tr>
      </tbody>
    </table>

    <h2>How to</h2>

    <h3>1 · Read a url4</h3>

    <p>
      Every candidate has a <code>url4</code>. A constructed Model or Fusion already carries its
      plan, before any run and free to inspect, and a completed run carries the exact expression
      that executed as <code>report.candidates[name].url4</code>.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="read" />
    </div>

    <p>
      Each returns the full expression, the shape annotated above: the routes, the parameters, the
      answer prompt, and, after a run, the pinned benchmark revision. It can run to a few thousand
      characters even for a small run, because it spells out everything the SDK filled in for you,
      but all of it is readable.
    </p>

    <h3>2 · Create a candidate from a url4</h3>

    <p>
      Because a <code>url4</code> is a complete plan, you can turn one back into a runnable
      candidate. <code>sf.from_url4()</code> rebuilds a Model or Fusion from any url4 string, whether
      you read it off your own run or someone handed it to you, so you can rerun it, or change one
      thing and remix it into the next attempt.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="remix" />
    </div>

    <h3>3 · Inspect the operation graph</h3>

    <p>
      <code>operations</code> is the same plan as structured data: a directed acyclic graph of
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

    <h3>4 · Identify the run</h3>

    <div class="not-prose">
      <NbCell :count="4" :code="runId"><NbTextOut :text="runIdOut" /></NbCell>
    </div>

    <h3>5 · Share the whole report</h3>

    <div class="not-prose">
      <NbCell :count="5" :code="share" />
    </div>

    <p>
      The dict carries a <code>schema</code> field, <code>screamingface.report.v1</code>, so a
      consumer can tell what shape it is reading. Every candidate's <code>url4</code>, scores,
      metrics, usage and the pinned benchmark revision travel with it.
    </p>

    <h2>What "reproduce" means here</h2>

    <p>
      A url4 pins the run's <strong>definition</strong>, not its outputs. Re-executing the same
      expression asks the same models the same questions under the same protocol, and models are not
      deterministic, so the scores will move. What is reproducible is the experiment, not the
      number.
    </p>

    <p>
      That is the useful guarantee. When two results differ, the url4 tells you whether the
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
          >Companion notebook: <code>07_ifeval_e2e.ipynb</code></a
        >, which prints a full expression
      </li>
    </ul>
  </DocLayout>
</template>
