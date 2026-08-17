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

const basic = `import screamingface as sf

draft = sf.Model("openrouter/openai/gpt-5.5")
review = sf.Model("openrouter/anthropic/claude-opus-4.8")

chain = sf.Pipeline([draft, review], name="review-chain")
chain`
const basicOut = `Pipeline(['gpt-5.5', 'claude-opus-4.8'], name='review-chain')`

const then = `final = sf.Model("openrouter/openai/gpt-5.5", name="polish")

draft.then(review).then(final)`
const thenOut = `Pipeline(['gpt-5.5', 'claude-opus-4.8', 'polish'])`

const flatten = `constructed = sf.Pipeline([draft, sf.Pipeline([review, final])])

[stage.name for stage in constructed.stages]`
const flattenOut = `['gpt-5.5', 'claude-opus-4.8', 'polish']`

const nestNamed = `named = sf.Pipeline([review, final], name="polish-pass")

[stage.name for stage in draft.then(named).stages]`
const nestNamedOut = `['gpt-5.5', 'polish-pass']`

const recursive = `judge = sf.Model("openrouter/anthropic/claude-opus-4.8", name="judge")
writer = sf.Model("openrouter/openai/gpt-5.5", name="writer")

sf.Fusion(
    [draft.then(review), sf.Model("openrouter/google/gemini-3.1-pro-preview")],
    synthesizer=sf.Pipeline([judge, writer]),
)`
const recursiveOut = `Fusion(['gpt-5.5->claude-opus-4.8', 'gemini-3.1-pro-preview'], synthesizer=Pipeline(['judge', 'writer']))`

const pipelineSig = `sf.Pipeline(
    stages: Sequence[str | Recipe],
    *,
    name: str | None = None,
)`
</script>

<template>
  <DocLayout
    title="Pipelines"
    description="Chain recipes in series, so each stage refines the previous stage's answer."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>Pipeline</strong> is a recipe composed of an ordered list of
      <strong>stages</strong>. It doesn't run anything by itself — like every recipe, building one
      makes no requests. The stages run only during an
      <RouterLink to="/sf-client/guides/running-an-evaluation">evaluation</RouterLink>: the first
      stage answers the case, and each later stage takes the <em>previous</em> stage's answer as its
      input (a draft gets reviewed, then polished). The benchmark grades only the last stage's
      answer, so a Pipeline competes head-to-head with a solo
      <RouterLink to="/sf-client/guides/models">Model</RouterLink> or a
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink>.
    </p>

    <p>
      A stage can be any recipe: a <code>Model</code>, a <code>Fusion</code>, or another
      <code>Pipeline</code>. Refine, review, or re-rank as many times as your experiment needs. Like
      all recipes, a Pipeline is immutable. Building one makes no requests.
    </p>

    <figure class="not-prose" style="margin: var(--space-8) 0">
      <svg
        viewBox="0 0 680 120"
        role="img"
        aria-label="A pipeline passes the question through ordered stages; each stage receives the previous stage's answer, and the last stage's answer is what the benchmark grades."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker
            id="pl-arrow"
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
        <g
          style="stroke: var(--text-2); stroke-width: 1.25; fill: none"
          marker-end="url(#pl-arrow)"
        >
          <path d="M104 60 H136" />
          <path d="M248 60 H280" />
          <path d="M392 60 H424" />
          <path d="M536 60 H568" />
        </g>
        <g style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1">
          <rect x="8" y="40" width="96" height="40" />
          <rect x="136" y="38" width="112" height="44" />
          <rect x="280" y="38" width="112" height="44" />
          <rect x="568" y="38" width="96" height="44" />
        </g>
        <rect
          x="424"
          y="38"
          width="112"
          height="44"
          style="fill: none; stroke: var(--accent); stroke-width: 1.5"
        />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="56" y="64">question</text>
          <text x="192" y="64">stage 1</text>
          <text x="336" y="64">stage 2</text>
          <text x="480" y="64">final stage</text>
          <text x="616" y="64">answer</text>
        </g>
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
        Each stage receives the previous stage's answer; the final stage's answer is what the
        benchmark grades.
      </figcaption>
    </figure>

    <h2>What you can do</h2>

    <ul>
      <li>Chain two or more recipes so each stage refines the previous answer.</li>
      <li>Build the same chain with <code>.then()</code> for a fluent API.</li>
      <li>Nest a Pipeline inside a Fusion, or vice versa.</li>
      <li>Read back the ordered stages and see the resolved name.</li>
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
          <td><code>sf.Pipeline(stages, *, name=None)</code></td>
          <td>
            Runs stages one after another. Each stage gets the previous stage's answer, and the last
            stage's answer is what the benchmark grades.
          </td>
        </tr>
        <tr>
          <td><code>recipe.then(next)</code></td>
          <td>
            Builder method on every recipe: appends a stage and returns a new Pipeline.
            <code>a.then(b).then(c)</code> reads left to right.
          </td>
        </tr>
        <tr>
          <td><code>.name</code> · <code>.stages</code></td>
          <td>Read back the resolved name and the ordered stages (as a tuple).</td>
        </tr>
        <tr>
          <td><code>sf.Recipe</code></td>
          <td>The shared base type of every candidate kind.</td>
        </tr>
      </tbody>
    </table>

    <h2>How to</h2>

    <h3>1 · Chain two recipes</h3>

    <p>
      Stages come first (positional), in the order they run. The Pipeline's name defaults to stage
      names joined with <code>-&gt;</code>. Give it an explicit <code>name</code> for a custom label
      in reports.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="basic"><NbTextOut :text="basicOut" /></NbCell>
    </div>

    <figure class="not-prose" style="margin: var(--space-6) 0">
      <svg
        viewBox="0 0 480 92"
        role="img"
        aria-label="review-chain runs draft then review in series; the review stage's answer is graded."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker id="pl-a1" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" style="fill: var(--text-2)" />
          </marker>
        </defs>
        <text x="240" y="16" text-anchor="middle" style="fill: var(--text-2)">review-chain</text>
        <g style="stroke: var(--text-2); stroke-width: 1.25; fill: none" marker-end="url(#pl-a1)">
          <path d="M186 52 H290" />
        </g>
        <rect x="16" y="30" width="170" height="44" style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1" />
        <rect x="294" y="30" width="170" height="44" style="fill: none; stroke: var(--accent); stroke-width: 1.5" />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="101" y="56">draft</text>
          <text x="379" y="56">review · graded</text>
        </g>
      </svg>
      <figcaption
        style="font-family: var(--f-mono); font-size: var(--text-label); text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-2); margin-top: var(--space-3)"
      >
        Two stages in series; the review stage's answer is what the benchmark grades.
      </figcaption>
    </figure>

    <h3>2 · Build the same chain with <code>.then()</code></h3>

    <p>
      <code>.then()</code> is on every recipe. It appends a stage so chains read left to right.
      Builds the same canonical Pipeline as passing stages to the constructor.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="then"><NbTextOut :text="thenOut" /></NbCell>
    </div>

    <figure class="not-prose" style="margin: var(--space-6) 0">
      <svg
        viewBox="0 0 560 84"
        role="img"
        aria-label="draft.then(review).then(final) chains three stages in series, left to right."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker id="pl-a2" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" style="fill: var(--text-2)" />
          </marker>
        </defs>
        <g style="stroke: var(--text-2); stroke-width: 1.25; fill: none" marker-end="url(#pl-a2)">
          <path d="M166 44 H201" />
          <path d="M355 44 H390" />
        </g>
        <g style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1">
          <rect x="16" y="22" width="150" height="44" />
          <rect x="205" y="22" width="150" height="44" />
        </g>
        <rect x="394" y="22" width="150" height="44" style="fill: none; stroke: var(--accent); stroke-width: 1.5" />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="91" y="48">draft</text>
          <text x="280" y="48">review</text>
          <text x="469" y="48">final · graded</text>
        </g>
      </svg>
      <figcaption
        style="font-family: var(--f-mono); font-size: var(--text-label); text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-2); margin-top: var(--space-3)"
      >
        <code>.then()</code> builds the same three-stage chain, read left to right.
      </figcaption>
    </figure>

    <h3>3 · Flatten vs. nest</h3>

    <p>
      An <em>unnamed</em> Pipeline inside another Pipeline flattens into one sequence. Nesting for
      convenience never changes what runs.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="flatten"><NbTextOut :text="flattenOut" /></NbCell>
    </div>

    <figure class="not-prose" style="margin: var(--space-6) 0">
      <svg
        viewBox="0 0 620 132"
        role="img"
        aria-label="An unnamed inner Pipeline flattens: draft, review and final run as one sequence."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker id="pl-a3" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" style="fill: var(--text-2)" />
          </marker>
        </defs>
        <g style="stroke: var(--text-2); stroke-width: 1.25; fill: none" marker-end="url(#pl-a3)">
          <path d="M146 68 H192" />
          <path d="M370 76 H426" />
        </g>
        <rect
          x="196"
          y="20"
          width="408"
          height="96"
          style="fill: none; stroke: var(--border-strong); stroke-width: 1; stroke-dasharray: 4 4"
        />
        <text x="206" y="38" style="fill: var(--text-2); font-size: 11px">Pipeline (unnamed)</text>
        <rect x="16" y="46" width="130" height="44" style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1" />
        <rect x="220" y="54" width="150" height="44" style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1" />
        <rect x="430" y="54" width="150" height="44" style="fill: none; stroke: var(--accent); stroke-width: 1.5" />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="81" y="72">draft</text>
          <text x="295" y="80">review</text>
          <text x="505" y="80">final · graded</text>
        </g>
      </svg>
      <figcaption
        style="font-family: var(--f-mono); font-size: var(--text-label); text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-2); margin-top: var(--space-3)"
      >
        The unnamed inner Pipeline flattens — draft → review → final runs as one sequence.
      </figcaption>
    </figure>

    <p>
      Give the inner Pipeline a <code>name</code> and it is kept as a single stage instead, so a
      named chain stays a named, reusable unit.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="nestNamed"><NbTextOut :text="nestNamedOut" /></NbCell>
    </div>

    <figure class="not-prose" style="margin: var(--space-6) 0">
      <svg
        viewBox="0 0 620 132"
        role="img"
        aria-label="A named inner Pipeline (polish-pass) stays a single stage: draft then polish-pass, which itself is review then final."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker id="pl-a4" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" style="fill: var(--text-2)" />
          </marker>
        </defs>
        <g style="stroke: var(--text-2); stroke-width: 1.25; fill: none" marker-end="url(#pl-a4)">
          <path d="M146 68 H192" />
          <path d="M370 76 H426" />
        </g>
        <rect
          x="196"
          y="20"
          width="408"
          height="96"
          style="fill: none; stroke: var(--border-strong); stroke-width: 1.25"
        />
        <text x="206" y="38" style="fill: var(--text-2); font-size: 11px">polish-pass (named · one stage)</text>
        <rect x="16" y="46" width="130" height="44" style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1" />
        <rect x="220" y="54" width="150" height="44" style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1" />
        <rect x="430" y="54" width="150" height="44" style="fill: none; stroke: var(--accent); stroke-width: 1.5" />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="81" y="72">draft</text>
          <text x="295" y="80">review</text>
          <text x="505" y="80">final · graded</text>
        </g>
      </svg>
      <figcaption
        style="font-family: var(--f-mono); font-size: var(--text-label); text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-2); margin-top: var(--space-3)"
      >
        A named inner Pipeline is kept as one stage: draft → polish-pass (itself review → final).
      </figcaption>
    </figure>

    <h3>4 · Compose recursively</h3>

    <p>
      Because a stage is any recipe and a
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink>'s members and synthesizer are
      any recipe, the two compose freely: a Fusion of Pipelines, a Pipeline of Fusions, or a Fusion
      whose synthesizer is itself a Pipeline.
    </p>

    <div class="not-prose">
      <NbCell :count="5" :code="recursive"><NbTextOut :text="recursiveOut" /></NbCell>
    </div>

    <figure class="not-prose" style="margin: var(--space-6) 0">
      <svg
        viewBox="0 0 720 196"
        role="img"
        aria-label="A Fusion of two members — a draft-then-review pipeline and gemini — combined by a synthesizer that is itself a judge-then-writer pipeline."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker id="pl-a5" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" style="fill: var(--text-2)" />
          </marker>
        </defs>
        <text x="16" y="16" style="fill: var(--text-2)">Fusion · members</text>
        <g style="stroke: var(--text-2); stroke-width: 1.25; fill: none" marker-end="url(#pl-a5)">
          <path d="M136 48 H168" />
          <path d="M292 48 C372 48 372 98 448 98" />
          <path d="M136 128 C300 128 372 98 448 98" />
          <path d="M572 104 H590" />
        </g>
        <g style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1">
          <rect x="16" y="28" width="120" height="40" />
          <rect x="172" y="28" width="120" height="40" />
          <rect x="16" y="108" width="120" height="40" />
          <rect x="464" y="86" width="108" height="36" />
        </g>
        <rect
          x="452"
          y="58"
          width="252"
          height="80"
          style="fill: none; stroke: var(--border-strong); stroke-width: 1.25"
        />
        <text x="462" y="76" style="fill: var(--text-2); font-size: 11px">synthesizer · Pipeline</text>
        <rect x="596" y="86" width="96" height="36" style="fill: none; stroke: var(--accent); stroke-width: 1.5" />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="76" y="52">draft</text>
          <text x="232" y="52">review</text>
          <text x="76" y="132">gemini</text>
          <text x="518" y="108">judge</text>
          <text x="644" y="108">writer</text>
        </g>
      </svg>
      <figcaption
        style="font-family: var(--f-mono); font-size: var(--text-label); text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-2); margin-top: var(--space-3)"
      >
        A Fusion of two members (the draft → review pipeline and gemini), combined by a synthesizer
        that is itself a judge → writer pipeline. The synthesizer's last stage (writer) is graded.
      </figcaption>
    </figure>

    <h2>The <code>Pipeline</code> class</h2>

    <CodeBlock :code="pipelineSig" language="python" />

    <h3>Parameters</h3>

    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>stages</code></td>
          <td><code>Sequence[str&nbsp;|&nbsp;Recipe]</code></td>
          <td>
            One or more stages, in order. Each can be a route string or any recipe. An
            <em>unnamed</em> nested <code>Pipeline</code> flattens into the surrounding sequence; a
            <em>named</em> one stays as a single stage.
          </td>
        </tr>
        <tr>
          <td><code>name</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Defaults to the stage names joined with <code>-&gt;</code>, for example
            <code>gpt-5.5-&gt;claude-opus-4.8</code>.
          </td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>stages</code> is a <code>tuple</code> in canonical order. <code>name</code> is the
      resolved label. <code>recipe.then(next)</code>, available on every recipe, appends a stage and
      returns a new <code>Pipeline</code>.
    </p>

    <h3>Raises</h3>

    <table>
      <thead>
        <tr>
          <th>When</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>The stages are empty</td>
          <td><code>ValueError: a Pipeline requires at least one stage</code></td>
        </tr>
        <tr>
          <td><code>stages</code> is not an ordered sequence (for example a bare route string)</td>
          <td>
            <code
              >TypeError: Pipeline stages must be an ordered sequence of model routes or
              Recipes</code
            >
          </td>
        </tr>
        <tr>
          <td><code>.then()</code> is given something other than a route string or recipe</td>
          <td><code>TypeError: Pipeline stage must be …</code></td>
        </tr>
      </tbody>
    </table>

    <h2>Links</h2>

    <ul>
      <li>
        <a
          href="https://github.com/OpenMined/screamingface/blob/main/packages/screamingface/README.md"
          target="_blank"
          rel="noopener"
          >Recipe composition in the package README</a
        >
      </li>
    </ul>
  </DocLayout>
</template>
