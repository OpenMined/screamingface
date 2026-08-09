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
    synthesizer="openrouter/openai/gpt-5.5",
)`
const synthOut = `Fusion(['claude-opus-4.8', 'gpt-5.5'], name='pair-gpt-synth', synthesizer='openrouter/openai/gpt-5.5')`

const nested = `haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")

sf.Fusion([pair, haiku], name="nested")`
const nestedOut = `Fusion(['claude-opus-4.8+gpt-5.5', 'claude-haiku-4.5'], name='nested')`
</script>

<template>
  <DocLayout
    title="Fusions"
    description="Combine two or more members into one answer through a synthesizer."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>Fusion</strong> asks several members the same question and then has one more model,
      the <strong>synthesizer</strong>, read their answers and produce a single final one. That
      final answer is what the benchmark grades, so a Fusion competes in exactly the same column as
      a solo <RouterLink to="/sf-client/guides/models">Model</RouterLink>.
    </p>

    <p>
      It is worth stating plainly what a fusion is <em>not</em>: there is no vote, no averaging, no
      score-merging. Members produce candidate answers, and a model decides.
    </p>

    <p>Like a Model, a Fusion is immutable and network-free, so building one makes no request.</p>

    <h2>What you can do with it</h2>

    <ul>
      <li>Combine two or more Models into one candidate.</li>
      <li>Choose which model does the synthesising, and how it is prompted.</li>
      <li>Nest a Fusion inside another Fusion.</li>
      <li>Read back the members and the resolved name.</li>
    </ul>

    <h2>Main APIs</h2>

    <ul>
      <li>
        <code>sf.Fusion(members, *, name=None, synthesizer=None, prompt=None, params=None)</code>:
        combine members behind a synthesizer
      </li>
      <li>
        <code>.name</code> · <code>.members</code> · <code>.synthesizer</code> ·
        <code>.prompt</code> · <code>.params</code>: read back the resolved shape
      </li>
      <li><code>sf.Recipe</code>: the shared base type of every candidate kind</li>
    </ul>

    <h2>How to</h2>

    <h3>Combine two models</h3>

    <p>
      Members come first and positionally. Nothing else is required: the engine declares a default
      synthesizer (<code>openrouter/anthropic/claude-haiku-4.5</code>) and the SDK supplies a
      constraint-aware synthesis prompt, so a two-line Fusion is complete.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="basic"><NbTextOut :text="basicOut" /></NbCell>
    </div>

    <p>
      A Fusion needs <strong>at least two</strong> members and their names must be unique: one
      member is not a fusion, and two identically named ones could not be told apart in a report.
      Both raise immediately, at construction.
    </p>

    <h3>Read the resolved name</h3>

    <p>
      Without an explicit <code>name</code>, the Fusion's name is its members' names joined with
      <code>+</code>. That is the label a report will show.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="inspect"><NbTextOut :text="inspectOut" /></NbCell>
    </div>

    <h3>Choose the synthesizer</h3>

    <p>
      The synthesizer is a <strong>model route string</strong>, not a Model object, because the
      engine resolves it. Swapping it is the main lever a Fusion has: the same members with a
      stronger synthesizer is a different candidate, and worth measuring as one.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="synth"><NbTextOut :text="synthOut" /></NbCell>
    </div>

    <p>
      <code>prompt</code> and <code>params</code> work the same way here as on a Model, but they
      apply to the <em>synthesis</em> step, governing how the final answer is written rather than
      how members answer. Give a member its own prompt by setting it on that Model.
    </p>

    <h3>Nest a fusion</h3>

    <p>
      A member may itself be a Fusion, so a pair can become a member of a larger fusion. The inner
      Fusion appears under its own resolved name.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="nested"><NbTextOut :text="nestedOut" /></NbCell>
    </div>

    <p>
      Members must be Models or Fusions. A corrective ensemble cannot be a member, because it grades
      its own members' raw drafts, which a surrounding synthesizer would have already replaced.
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
