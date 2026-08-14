<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
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
</script>

<template>
  <DocLayout
    title="Pipelines"
    description="Chain recipes in series, so each stage refines the previous stage's answer."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>Pipeline</strong> runs stages one after another. The first stage answers the case,
      each later stage gets the <em>previous</em> stage's answer as input. A draft gets reviewed,
      then polished. The benchmark grades the last stage's answer, so a Pipeline competes with a
      solo <RouterLink to="/sf-client/guides/models">Model</RouterLink> or a
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

    <h3>2 · Build the same chain with <code>.then()</code></h3>

    <p>
      <code>.then()</code> is on every recipe. It appends a stage so chains read left to right.
      Builds the same canonical Pipeline as passing stages to the constructor.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="then"><NbTextOut :text="thenOut" /></NbCell>
    </div>

    <h3>3 · Flatten vs. nest</h3>

    <p>
      An <em>unnamed</em> Pipeline inside another Pipeline flattens into one sequence. Nesting for
      convenience never changes what runs.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="flatten"><NbTextOut :text="flattenOut" /></NbCell>
    </div>

    <p>
      Give the inner Pipeline a <code>name</code> and it is kept as a single stage instead, so a
      named chain stays a named, reusable unit.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="nestNamed"><NbTextOut :text="nestNamedOut" /></NbCell>
    </div>

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

    <p>
      Check the <RouterLink to="/sf-client/api/recipes">Recipes reference</RouterLink> for the full
      <code>Pipeline</code> signature, attributes, and errors.
    </p>

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
