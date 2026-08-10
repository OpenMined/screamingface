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
opus`
const basicOut = `Model('openrouter/anthropic/claude-opus-4.8')`

const named = `sf.Model("openrouter/openai/gpt-5.5", name="gpt-run-2")`
const namedOut = `Model('openrouter/openai/gpt-5.5', name='gpt-run-2')`

const policy = `sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt="Answer concisely.",
    params={"reasoning": "high"},
)`
const policyOut = `Model('openrouter/openai/gpt-5.5', prompt='Answer concisely.', params={'reasoning': 'high'})`

const listing = `sf.models.list()`
const listingOut = `ModelInfo(id='anthropic/claude-opus-4-8', provider='anthropic')
ModelInfo(id='anthropic/claude-haiku-4-5', provider='anthropic')
ModelInfo(id='codex/gpt-5.5', provider='codex')
ModelInfo(id='gemini-cli/gemini-2.5-pro', provider='gemini-cli')
ModelInfo(id='huggingface/deepseek-ai/DeepSeek-R1:novita', provider='huggingface')
ModelInfo(id='openrouter/anthropic/claude-opus-4.8', provider='openrouter')
ModelInfo(id='openrouter/openai/gpt-5.5', provider='openrouter')
ModelInfo(id='openrouter/google/gemini-3.1-pro-preview', provider='openrouter')
…   # 29 entries across 6 providers on this engine`
</script>

<template>
  <DocLayout
    title="Models"
    description="Select a model route and set the answer policy a candidate owns."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <strong>Model</strong> names one model route and, optionally, the answer policy that route
      should use. It is the smallest thing you can evaluate, and the building block every
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink> is made of.
    </p>

    <p>
      A Model is <strong>immutable</strong>. Constructing one makes no request and needs no
      connection: it is a value describing what to ask for. Nothing happens until you pass it to an
      evaluation.
    </p>

    <h2>What you can do with it</h2>

    <ul>
      <li>Select a route to evaluate.</li>
      <li>Name a Model so two samples of the same route stay distinguishable.</li>
      <li>Override the answer prompt and generation parameters.</li>
      <li>List the routes this engine can actually reach.</li>
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
          <td><code>sf.Model(model, *, name=None, prompt=None, params=None)</code></td>
          <td>
            Selects one model route as the smallest thing you can evaluate, optionally overriding
            its answer policy with a prompt and generation parameters.
          </td>
        </tr>
        <tr>
          <td><code>sf.models.list()</code></td>
          <td>
            Lists the routes this engine can reach as <code>sf.ModelInfo</code> values, spanning
            every provider the engine knows.
          </td>
        </tr>
        <tr>
          <td><code>.name</code> · <code>.model</code> · <code>.prompt</code> · <code>.params</code></td>
          <td>Read back what a Model resolved to, including its inferred or explicit name.</td>
        </tr>
      </tbody>
    </table>

    <h2>How to</h2>

    <h3>Select a route</h3>

    <p>
      The route is the only required argument. The Model's <code>name</code> is inferred from its
      last segment, which is what appears in a report.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="basic"><NbTextOut :text="basicOut" /></NbCell>
    </div>

    <h3>Name an independent sample</h3>

    <p>
      Two Models on the same route with the same policy are the <em>same</em> candidate:
      <RouterLink to="/learn/engine">the engine</RouterLink> deduplicates them by content inside one
      compiled graph. An explicit <code>name</code> is how
      you say you meant two independent samples, and it is the name the report uses.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="named"><NbTextOut :text="namedOut" /></NbCell>
    </div>

    <h3>Override the answer policy</h3>

    <p>
      The SDK supplies a general answer prompt, so a bare Model works. When an experiment needs
      something specific, <code>prompt</code> and <code>params</code> replace it.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="policy"><NbTextOut :text="policyOut" /></NbCell>
    </div>

    <p>
      These are <strong>candidate-owned</strong> settings: they change how your candidate answers,
      and they can never touch benchmark-owned cases, judge models, grading or aggregation. That
      separation is what keeps two candidates comparable on the same benchmark. Whatever you set is
      resolved and embedded in the run's <RouterLink to="/learn/url4">URL4</RouterLink>, so a report
      records the policy that actually ran.
    </p>

    <h3>See what the engine can reach</h3>

    <div class="not-prose">
      <NbCell :count="4" :code="listing"><NbTextOut :text="listingOut" /></NbCell>
    </div>

    <p>
      Two things to note. The catalogue spans <strong>every provider the engine knows</strong>, not
      only the ones you have connected: a route you have no credential for will fail at evaluation,
      not here. And ID shapes differ per provider: <code>anthropic/claude-opus-4-8</code> against
      <code>openrouter/anthropic/claude-opus-4.8</code>. Copy the <code>id</code> rather than
      retyping it.
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
