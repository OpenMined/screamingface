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

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

pair = sf.Fusion([opus, gpt])
pair`
const basicOut = `Fusion(['claude-opus-4.8', 'gpt-5.5'])`

const inspect = `pair.name, [m.name for m in pair.members]`
const inspectOut = `('claude-opus-4.8+gpt-5.5', ['claude-opus-4.8', 'gpt-5.5'])`

const synth = `sf.Fusion(
    [opus, gpt],
    name="pair-gpt-synth",
    reducer=sf.reducers.Model(model="openrouter/openai/gpt-5.5"),
)`
const synthOut = `Fusion(['claude-opus-4.8', 'gpt-5.5'], name='pair-gpt-synth', reducer=Model(model='openrouter/openai/gpt-5.5'))`

const nested = `haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")

sf.Fusion([pair, haiku], name="nested")`
const nestedOut = `Fusion(['claude-opus-4.8+gpt-5.5', 'claude-haiku-4.5'], name='nested')`
</script>

<template>
  <DocLayout
    title="Fusions"
    description="Combine two or more members into one answer through a reducer."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>Fusion</strong> asks several members the same question, then a
      <strong>reducer</strong> reads their answers and produces the single final one. That final
      answer is what the benchmark grades, so a Fusion competes in exactly the same column as a solo
      <RouterLink to="/sf-client/guides/models">Model</RouterLink>.
    </p>

    <p>
      How the reducer decides is configurable. It can be a model, for example a judge that reads the
      candidate answers and writes the winner, or your own code that inspects the answers and decides
      how to pick or combine them.
    </p>

    <figure class="not-prose" style="margin: var(--space-8) 0">
      <svg
        viewBox="0 0 680 236"
        role="img"
        aria-label="A fusion sends one question to several members; a reducer combines their answers into the single answer the benchmark grades."
        style="width: 100%; height: auto; font-family: var(--f-mono); font-size: 12px"
      >
        <defs>
          <marker
            id="fx-arrow"
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
          marker-end="url(#fx-arrow)"
        >
          <path d="M112 118 H152" />
          <path d="M112 118 C 134 118, 134 44, 156 44" />
          <path d="M112 118 C 134 118, 134 192, 156 192" />
          <path d="M300 44 C 334 44, 334 118, 366 118" />
          <path d="M300 118 H366" />
          <path d="M300 192 C 334 192, 334 118, 366 118" />
          <path d="M520 118 H568" />
        </g>
        <g style="fill: var(--surface); stroke: var(--border-strong); stroke-width: 1">
          <rect x="16" y="98" width="96" height="40" />
          <rect x="160" y="22" width="140" height="44" />
          <rect x="160" y="96" width="140" height="44" />
          <rect x="160" y="170" width="140" height="44" />
          <rect x="572" y="96" width="96" height="44" />
        </g>
        <rect
          x="370"
          y="86"
          width="150"
          height="64"
          style="fill: none; stroke: var(--accent); stroke-width: 1.5"
        />
        <g text-anchor="middle" style="fill: var(--text)">
          <text x="64" y="122">question</text>
          <text x="230" y="48">member 1</text>
          <text x="230" y="122">member 2</text>
          <text x="230" y="196">member 3</text>
          <text x="445" y="114">reducer</text>
          <text x="620" y="122">answer</text>
        </g>
        <text x="445" y="132" text-anchor="middle" style="fill: var(--text-2); font-size: 10px">
          model · vote · code
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
        Members answer the same question; the reducer combines them into the one answer the benchmark
        grades.
      </figcaption>
    </figure>

    <p>Like a Model, a Fusion is immutable: building one makes no request.</p>

    <h2>What you can do with it</h2>

    <ul>
      <li>Combine two or more Models into one candidate.</li>
      <li>Choose the reducer, and how a model reducer is prompted.</li>
      <li>Nest a Fusion inside another Fusion.</li>
      <li>Read back the members and the resolved name.</li>
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
          <td><code>sf.Fusion(members, *, name=None, reducer=None)</code></td>
          <td>
            Combines at least two members behind a reducer that reads their answers and produces the
            single final answer the benchmark grades.
          </td>
        </tr>
        <tr>
          <td>
            <code>sf.reducers.Model(model, *, prompt=None, params=None)</code> ·
            <code>sf.reducers.MajorityVote()</code>
          </td>
          <td>
            The reducers you pass to <code>reducer=</code>: <code>Model</code> has a model synthesise
            the answer; <code>MajorityVote</code> picks by agreement, with no extra model call.
          </td>
        </tr>
        <tr>
          <td><code>.name</code> · <code>.members</code> · <code>.reducer</code></td>
          <td>Read back the resolved shape, including the members and the resolved name.</td>
        </tr>
        <tr>
          <td><code>sf.Recipe</code></td>
          <td>The shared base type of every candidate kind.</td>
        </tr>
      </tbody>
    </table>

    <h2>How to</h2>

    <h3>1 · Combine two models</h3>

    <p>Members come first and positionally.</p>

    <div class="not-prose">
      <NbCell :count="1" :code="basic"><NbTextOut :text="basicOut" /></NbCell>
    </div>

    <p>
      A Fusion needs <strong>at least two</strong> members and their names must be unique: one
      member is not a fusion, and two identically named ones could not be told apart in a report.
      Both raise immediately, at construction.
    </p>

    <h3>2 · Read the resolved name</h3>

    <p>
      Without an explicit <code>name</code>, the Fusion's name is its members' names joined with
      <code>+</code>. That is the label a report will show.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="inspect"><NbTextOut :text="inspectOut" /></NbCell>
    </div>

    <h3>3 · Choose the reducer</h3>

    <p>
      The <strong>reducer</strong> decides how the members' answers become one. Pass a reducer from
      <RouterLink to="/learn/engine"><code>sf.reducers</code></RouterLink>: <code>Model</code> has a
      model read the answers and write the final one, while <code>MajorityVote</code> picks the
      most-agreed answer with no extra model call. Swapping the reducer is the main lever a Fusion
      has: the same members with a different reducer is a different candidate, worth measuring as one.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="synth"><NbTextOut :text="synthOut" /></NbCell>
    </div>

    <p>
      A model reducer carries its own <code>prompt</code> and <code>params</code>
      (<code>sf.reducers.Model(model, prompt=…, params=…)</code>): they control how the final answer
      is written, separately from how the members answer. Give a member its own prompt by setting it
      on that Model.
    </p>

    <h3>4 · Nest a fusion</h3>

    <p>
      A member may itself be a Fusion, so a pair can become a member of a larger fusion. The inner
      Fusion appears under its own resolved name.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="nested"><NbTextOut :text="nestedOut" /></NbCell>
    </div>

    <p>
      Members must be Models or Fusions. A corrective ensemble cannot be a member: it grades its own
      members' raw drafts, which a surrounding reducer would have already replaced.
    </p>

    <h2>Links</h2>

    <ul>
      <li>
        <a
          href="https://github.com/OpenMined/screamingface/blob/OME-605-screamingface-client-v1/packages/screamingface/examples/00_quickstart.ipynb"
          target="_blank"
          rel="noopener"
          >Companion notebook: <code>00_quickstart.ipynb</code></a
        >
      </li>
    </ul>
  </DocLayout>
</template>
