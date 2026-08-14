<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import Note from '@/components/ui/Note.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const modelSig = `sf.Model(
    model: str,
    *,
    name: str | None = None,
    prompt: str | None = None,
    params: Mapping[str, str | int | float | bool] | None = None,
)`

const modelRun = `import screamingface as sf

sf.Model("openrouter/openai/gpt-5.5", name="gpt-hot", params={"temperature": 0.9})`
const modelRunOut = `Model('openrouter/openai/gpt-5.5', name='gpt-hot', params={'temperature': 0.9})`

const fusionSig = `sf.Fusion(
    members: Sequence[str | Recipe],
    *,
    name: str | None = None,
    synthesizer: str | Recipe,
)`

const fusionRun = `opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5", name="gpt-hot")

sf.Fusion([opus, gpt], synthesizer="openrouter/openai/gpt-5.5")`
const fusionRunOut = `Fusion(['claude-opus-4.8', 'gpt-hot'], synthesizer=Model('openrouter/openai/gpt-5.5'))`

const pipelineSig = `sf.Pipeline(
    stages: Sequence[str | Recipe],
    *,
    name: str | None = None,
)`

const pipelineRun = `draft = sf.Model("openrouter/openai/gpt-5.5")
review = sf.Model("openrouter/anthropic/claude-opus-4.8")

sf.Pipeline([draft, review], name="review-chain")`
const pipelineRunOut = `Pipeline(['gpt-5.5', 'claude-opus-4.8'], name='review-chain')`

const thenRun = `draft.then(review)`
const thenRunOut = `Pipeline(['gpt-5.5', 'claude-opus-4.8'])`

const equality = `a = sf.Model("openrouter/openai/gpt-5.5")
b = sf.Model("openrouter/openai/gpt-5.5")

a == b`
const equalityOut = `True`
</script>

<template>
  <DocLayout
    title="Recipes"
    description="Recipe, Model, Fusion and Pipeline: the things you evaluate."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A recipe tells ScreamingFace how to produce one answer. That's what a benchmark grades. This
      page covers <code>Model</code> (a single model route), <code>Fusion</code> (several members
      combined by a synthesizer), <code>Pipeline</code> (members chained in series), and
      <code>Recipe</code> (the abstract type all three inherit from).
    </p>

    <p>
      All three constructible recipes are frozen and hold no client. Building one makes no network
      requests. You can compose them before connecting to anything. Recipes nest: a
      <code>Fusion</code> or <code>Pipeline</code> can contain a <code>Model</code>, another
      <code>Fusion</code>, or another <code>Pipeline</code>, in any combination.
    </p>

    <Note>
      Recipes compare by value. Two recipes built with identical arguments are equal, and
      <RouterLink to="/learn/engine">the engine</RouterLink> treats them as one candidate. Give a
      <code>Model</code> an explicit <code>name</code> for an independent sample. Recipes are
      unhashable: you can't use them as dict keys or put them in sets.
    </Note>

    <div class="not-prose">
      <NbCell :count="1" :code="equality"><NbTextOut :text="equalityOut" /></NbCell>
    </div>

    <h2>Recipe</h2>

    <p>
      <code>Recipe</code> is the abstract base the other three inherit from. You can't instantiate
      it directly. It exists for type annotations and so a <code>Fusion</code> or
      <code>Pipeline</code> can hold a mixed list of members.
    </p>

    <p>
      Every recipe has one public attribute: <code>name</code> (a <code>str</code>). It also
      provides <code>.then()</code>, which appends a stage and returns a <code>Pipeline</code> (see
      <a href="#pipeline">Pipeline</a> below).
    </p>

    <p>Calling <code>sf.Recipe()</code> directly raises:</p>

    <CodeBlock
      code="TypeError: Can't instantiate abstract class Recipe without an implementation for abstract method '_recipe_marker'"
      language="text"
    />

    <h2>Model</h2>

    <p>
      A <code>Model</code> is a single model route answering on its own. The simplest recipe, and
      the baseline for everything else. See the
      <RouterLink to="/sf-client/guides/models">Models guide</RouterLink> for help picking a route.
    </p>

    <CodeBlock :code="modelSig" language="python" />

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
          <td><code>model</code></td>
          <td><code>str</code></td>
          <td>
            The provider route, like <code>openrouter/openai/gpt-5.5</code>. Required, positional.
          </td>
        </tr>
        <tr>
          <td><code>name</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Label that shows up in reports and on the leaderboard. Defaults to everything after the
            last <code>/</code> in the route, so <code>openrouter/openai/gpt-5.5</code> becomes
            <code>gpt-5.5</code>. Setting an explicit name also marks this Model as an independent
            sample.
          </td>
        </tr>
        <tr>
          <td><code>prompt</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            The instruction given to the model alongside the case. Leave it out and the SDK uses its
            own default prompt (not the benchmark's).
          </td>
        </tr>
        <tr>
          <td><code>params</code></td>
          <td><code>Mapping&nbsp;|&nbsp;None</code></td>
          <td>
            Generation overrides like <code>temperature</code>. Values must be <code>str</code>,
            <code>int</code>, <code>float</code>, or <code>bool</code> (floats have to be finite).
            Only the params you set get sent, since the SDK adds no defaults. Transport, tool, and
            benchmark-protocol names (like <code>model</code>, <code>messages</code>,
            <code>tools</code>, <code>web_search</code>) are reserved and will be rejected.
          </td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>model</code>, <code>name</code>, and <code>prompt</code> give you back what you passed
      in. <code>params</code> returns a <code>mappingproxy</code>, so you can't mutate the overrides
      after construction.
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
          <td>The route or name is not a string</td>
          <td><code>TypeError</code></td>
        </tr>
        <tr>
          <td>The route or name is empty or only whitespace</td>
          <td><code>ValueError: model route must not be empty</code></td>
        </tr>
        <tr>
          <td>The route or name contains control characters</td>
          <td><code>ValueError</code></td>
        </tr>
        <tr>
          <td>A <code>params</code> value is not a scalar, or a float is not finite</td>
          <td><code>TypeError</code> / <code>ValueError</code></td>
        </tr>
        <tr>
          <td>A <code>params</code> name is reserved, or a name or value cannot be encoded</td>
          <td><code>ValueError</code></td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="2" :code="modelRun"><NbTextOut :text="modelRunOut" /></NbCell>
    </div>

    <h2>Fusion</h2>

    <p>
      A <code>Fusion</code> combines members: each member answers in parallel, then a
      <strong>synthesizer</strong> reads those answers and produces one final answer. The benchmark
      grades that final answer. See the
      <RouterLink to="/sf-client/guides/fusions">Fusions guide</RouterLink> for the reasoning.
    </p>

    <CodeBlock :code="fusionSig" language="python" />

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
          <td><code>members</code></td>
          <td><code>Sequence[str&nbsp;|&nbsp;Recipe]</code></td>
          <td>
            One or more members, in order. Each can be a route string, <code>Model</code>,
            <code>Fusion</code>, or <code>Pipeline</code>. Ensembles nest.
          </td>
        </tr>
        <tr>
          <td><code>name</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Defaults to the member names joined with <code>+</code>, for example
            <code>claude-opus-4.8+gpt-hot</code>.
          </td>
        </tr>
        <tr>
          <td><code>synthesizer</code></td>
          <td><code>str&nbsp;|&nbsp;Recipe</code></td>
          <td>
            <strong>Required, keyword-only.</strong> A route string or any recipe (a
            <code>Model</code>, <code>Fusion</code>, or <code>Pipeline</code>) that reads the
            members' answers and writes the final one. No default.
          </td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>members</code> is a <code>tuple</code> in the order you gave. <code>name</code> is the
      resolved label. <code>synthesizer</code> is the recipe you passed (route strings normalize to
      <code>Model</code>). No <code>reducer</code> attribute.
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
          <td>No <code>synthesizer</code> is given</td>
          <td><code>TypeError: missing a required keyword-only argument: 'synthesizer'</code></td>
        </tr>
        <tr>
          <td>The members are empty</td>
          <td><code>ValueError: a Fusion requires at least one member</code></td>
        </tr>
        <tr>
          <td><code>members</code> is not an ordered sequence (for example a bare route string)</td>
          <td>
            <code
              >TypeError: Fusion members must be an ordered sequence of model routes or
              Recipes</code
            >
          </td>
        </tr>
        <tr>
          <td>A member or the synthesizer is not a route string or a supported recipe</td>
          <td>
            <code>TypeError: … must be a model route or sf.Model, sf.Fusion, or sf.Pipeline</code>
          </td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="3" :code="fusionRun"><NbTextOut :text="fusionRunOut" /></NbCell>
    </div>

    <h2 id="pipeline">Pipeline</h2>

    <p>
      A <code>Pipeline</code> runs stages in series: the first stage answers the case, each later
      stage gets the previous stage's answer as input. The benchmark grades the last stage's answer.
      See the <RouterLink to="/sf-client/guides/pipelines">Pipelines guide</RouterLink> for serial
      and recursive composition.
    </p>

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

    <div class="not-prose">
      <NbCell :count="4" :code="pipelineRun"><NbTextOut :text="pipelineRunOut" /></NbCell>
      <NbCell :count="5" :code="thenRun"><NbTextOut :text="thenRunOut" /></NbCell>
    </div>
  </DocLayout>
</template>
