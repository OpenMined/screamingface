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

const equality = `a = sf.Model("openrouter/openai/gpt-5.5")
b = sf.Model("openrouter/openai/gpt-5.5")

a == b`
const equalityOut = `True`
</script>

<template>
  <DocLayout
    title="Recipes"
    description="The abstract Recipe base every candidate shares, and where each concrete type is documented."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A recipe tells ScreamingFace how to produce one answer — that's what a benchmark grades. This
      page documents <code>Recipe</code>, the abstract base every candidate shares. The three
      concrete types each have their own home: a single model route in
      <RouterLink to="/sf-client/api/models">Models</RouterLink>, several members combined by a
      synthesizer in the <RouterLink to="/sf-client/guides/fusions">Fusions guide</RouterLink>, and
      stages chained in series in the
      <RouterLink to="/sf-client/guides/pipelines">Pipelines guide</RouterLink>.
    </p>

    <p>
      Every constructible recipe is frozen and holds no client. Building one makes no network
      requests, so you can compose them before connecting to anything. Recipes nest: a
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
      <code>Recipe</code> is the abstract base the concrete types inherit from. You can't instantiate
      it directly. It exists for type annotations and so a <code>Fusion</code> or
      <code>Pipeline</code> can hold a mixed list of members.
    </p>

    <p>
      Every recipe has one public attribute: <code>name</code> (a <code>str</code>). It also
      provides <code>.then()</code>, which appends a stage and returns a
      <RouterLink to="/sf-client/guides/pipelines">Pipeline</RouterLink>.
    </p>

    <p>Calling <code>sf.Recipe()</code> directly raises:</p>

    <CodeBlock
      code="TypeError: Can't instantiate abstract class Recipe without an implementation for abstract method '_recipe_marker'"
      language="text"
    />

    <h2>Where each type is documented</h2>

    <ul>
      <li>
        <strong><RouterLink to="/sf-client/api/models">Model</RouterLink></strong> — a single model
        route. Its constructor, parameters, attributes, and errors live on the Models page.
      </li>
      <li>
        <strong><RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink></strong> — members
        combined by a synthesizer. The Fusions guide carries its full reference.
      </li>
      <li>
        <strong><RouterLink to="/sf-client/guides/pipelines">Pipeline</RouterLink></strong> — stages
        chained in series. The Pipelines guide carries its full reference.
      </li>
    </ul>
  </DocLayout>
</template>
