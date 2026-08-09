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
    members: Sequence[Recipe],
    *,
    name: str | None = None,
    synthesizer: str | None = None,
    prompt: str | None = None,
    params: Mapping[str, str | int | float | bool] | None = None,
)`

const fusionRun = `opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5", name="gpt-hot")

sf.Fusion([opus, gpt], synthesizer="openrouter/openai/gpt-5.5")`
const fusionRunOut = `Fusion(['claude-opus-4.8', 'gpt-hot'], synthesizer='openrouter/openai/gpt-5.5')`

const correctiveSig = `sf.CorrectiveEnsemble(
    members: Sequence[Model],
    *,
    judge: Model,
    name: str | None = None,
)`

const correctiveRun = `sf.CorrectiveEnsemble([opus, gpt], judge=opus)`
const correctiveRunOut = `CorrectiveEnsemble(['claude-opus-4.8', 'gpt-hot'], judge='claude-opus-4.8')`

const identity = `sf.Model("openrouter/openai/gpt-5.5") == sf.Model("openrouter/openai/gpt-5.5")`
const identityOut = `False`
</script>

<template>
  <DocLayout
    title="Recipes"
    description="Recipe, Model, Fusion and CorrectiveEnsemble: the things you evaluate."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A recipe describes how to produce one answer, and is what a benchmark grades. This page covers
      <code>Model</code> for a single model route, <code>Fusion</code> for several members combined
      by a synthesizer, <code>CorrectiveEnsemble</code> for members that check their own drafts
      against the benchmark's verifier, and <code>Recipe</code>, the abstract type the other three
      satisfy.
    </p>

    <p>
      All three constructible recipes are frozen and hold no client, so building one issues no
      network request and can be done before connecting to anything.
    </p>

    <Note>
      Recipes compare by identity, not by value. Two separately constructed recipes with identical
      arguments are not equal, so they cannot be used interchangeably as dictionary keys or in sets.
    </Note>

    <div class="not-prose">
      <NbCell :count="1" :code="identity"><NbTextOut :text="identityOut" /></NbCell>
    </div>

    <h2>Recipe</h2>

    <p>
      <code>Recipe</code> is the abstract base the other three inherit and cannot itself be
      instantiated. It exists so that a parameter accepting any recipe can be annotated, and so that
      a <code>Fusion</code> can hold a mixed sequence of members.
    </p>

    <p>Its only public attribute is <code>name</code>, a <code>str</code> every recipe carries.</p>

    <p>Calling <code>sf.Recipe()</code> raises:</p>

    <CodeBlock
      code="TypeError: Can't instantiate abstract class Recipe without an implementation for abstract method '_recipe_marker'"
      language="text"
    />

    <h2>Model</h2>

    <p>
      A <code>Model</code> is a single model route answering on its own. It is the simplest recipe,
      and the baseline every other recipe is measured against. See the
      <RouterLink to="/sf-client/guides/models">Models guide</RouterLink> for choosing a route.
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
            The provider route, such as <code>openrouter/openai/gpt-5.5</code>. Required and
            positional.
          </td>
        </tr>
        <tr>
          <td><code>name</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Label used in reports and on the leaderboard. Defaults to the segment of the route after
            the last <code>/</code>, so <code>openrouter/openai/gpt-5.5</code> becomes
            <code>gpt-5.5</code>.
          </td>
        </tr>
        <tr>
          <td><code>prompt</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            The instruction given to the model alongside the case. When omitted the SDK supplies its
            own default answer prompt, not the benchmark's.
          </td>
        </tr>
        <tr>
          <td><code>params</code></td>
          <td><code>Mapping&nbsp;|&nbsp;None</code></td>
          <td>
            Generation overrides such as <code>temperature</code>. Values must be <code>str</code>,
            <code>int</code>, <code>float</code> or <code>bool</code>, and floats must be finite. At
            execution time these are merged over the SDK defaults <code>reasoning="low"</code> and
            <code>max_output_tokens=4096</code>.
          </td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>model</code>, <code>name</code> and <code>prompt</code> read back what you passed.
      <code>params</code> returns a <code>mappingproxy</code>, so the overrides cannot be mutated
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
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="2" :code="modelRun"><NbTextOut :text="modelRunOut" /></NbCell>
    </div>

    <h2>Fusion</h2>

    <p>
      A <code>Fusion</code> combines two or more members: each answers, then a synthesizer model
      reads their answers and writes the final one. That final answer is what the benchmark grades.
      See the <RouterLink to="/sf-client/guides/fusions">Fusions guide</RouterLink> for the
      reasoning behind the design.
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
          <td><code>Sequence[Recipe]</code></td>
          <td>
            At least two <code>Model</code> or <code>Fusion</code> values, in order. A
            <code>Fusion</code> may hold another <code>Fusion</code>, so ensembles nest.
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
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            The route of the model that writes the final answer. Defaults to
            <code>openrouter/anthropic/claude-haiku-4.5</code>.
          </td>
        </tr>
        <tr>
          <td><code>prompt</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            The instruction for the synthesis turn, not for the members. When omitted the SDK
            supplies its own default synthesis prompt.
          </td>
        </tr>
        <tr>
          <td><code>params</code></td>
          <td><code>Mapping&nbsp;|&nbsp;None</code></td>
          <td>Generation overrides for the synthesis turn. Same value rules as on a Model.</td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>members</code> is a <code>tuple</code> in the order you gave it. <code>name</code>,
      <code>synthesizer</code>, <code>prompt</code> and <code>params</code> read back as on a Model.
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
          <td>Fewer than two members</td>
          <td><code>ValueError: a Fusion requires at least two members</code></td>
        </tr>
        <tr>
          <td>Two members share a name</td>
          <td><code>ValueError: duplicate Fusion member name '…'</code></td>
        </tr>
        <tr>
          <td>
            A member is not a <code>Model</code> or <code>Fusion</code>, including a
            <code>CorrectiveEnsemble</code>
          </td>
          <td><code>TypeError: Fusion members must be sf.Model or sf.Fusion values</code></td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="3" :code="fusionRun"><NbTextOut :text="fusionRunOut" /></NbCell>
    </div>

    <h2>CorrectiveEnsemble</h2>

    <p>
      A <code>CorrectiveEnsemble</code> runs its members in parallel and has the benchmark's own
      verifier check every draft. Each member then gets a bounded number of retries against the
      violations it caused, and a judge model picks between the drafts that passed. Nothing is
      blended: the winning draft is returned verbatim.
    </p>

    <Note>
      This recipe needs a benchmark that advertises <code>check</code>, <code>select</code> and
      <code>finalize</code> verifier actions, such as <code>ifeval</code>. Evaluating it against any
      other benchmark raises a <code>PlanningError</code> with code
      <code>benchmark_without_verifier</code>. The retry cap is three attempts per member.
    </Note>

    <CodeBlock :code="correctiveSig" language="python" />

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
          <td><code>Sequence[Model]</code></td>
          <td>
            Two to four Models. <code>Fusion</code> is rejected, because the verifier grades each
            member's raw draft and a synthesizer would hide those drafts.
          </td>
        </tr>
        <tr>
          <td><code>judge</code></td>
          <td><code>Model</code></td>
          <td>
            Required keyword argument. The model that picks between drafts that passed the verifier.
          </td>
        </tr>
        <tr>
          <td><code>name</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Defaults to the member names joined with <code>+</code> followed by
            <code>(corrective)</code>.
          </td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>members</code> is a <code>tuple[Model, ...]</code>, <code>judge</code> is the Model you
      passed, and <code>name</code> is the resolved label.
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
          <td>Fewer than two or more than four members</td>
          <td><code>ValueError: CorrectiveEnsemble needs 2-4 members, got N</code></td>
        </tr>
        <tr>
          <td>A member is not a <code>Model</code></td>
          <td><code>TypeError: CorrectiveEnsemble members must be sf.Model values</code></td>
        </tr>
        <tr>
          <td>The judge is not a <code>Model</code></td>
          <td><code>TypeError: CorrectiveEnsemble judge must be an sf.Model</code></td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="4" :code="correctiveRun"><NbTextOut :text="correctiveRunOut" /></NbCell>
    </div>
  </DocLayout>
</template>
