<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import NbCell from '@/components/nb/NbCell.vue'
import Note from '@/components/ui/Note.vue'
import {
  sfClientReferenceNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const fusionSig = `sf.Fusion(
    members: Sequence[str | Recipe],
    *,
    name: str | None = None,
    synthesizer: str | Recipe,
)`

const fusionExample = `fusion = sf.Fusion(
    ["openrouter/deepseek/deepseek-v4-pro", "openrouter/z-ai/glm-5.2"],
    synthesizer="openrouter/moonshotai/kimi-k3",
)
report = sf.evaluate(fusion, benchmark="ifeval", limit=1)`
</script>

<template>
  <DocLayout
    title="Fusion"
    description="Combine parallel members into one answer through a synthesizer."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A Fusion is a <RouterLink to="/sf-client/api/recipes">Recipe</RouterLink> that runs several
      members in parallel and combines their answers with an explicit synthesizer. Like every recipe
      it is frozen and holds no Client, so you can build it before connecting. The
      <RouterLink to="/sf-client/guides/fusions">Fusions guide</RouterLink> walks through building
      one.
    </p>

    <CodeBlock :code="fusionSig" language="python" />

    <table>
      <thead>
        <tr>
          <th>Attribute</th>
          <th>Type</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>name</code></td>
          <td><code>str</code></td>
          <td>
            The fusion's name. Inferred by joining member names with <code>+</code> unless you pass
            one.
          </td>
        </tr>
        <tr>
          <td><code>members</code></td>
          <td><code>tuple[Recipe, ...]</code></td>
          <td>The members that run in parallel. At least one.</td>
        </tr>
        <tr>
          <td><code>synthesizer</code></td>
          <td><code>Recipe</code></td>
          <td>The recipe that combines the members' answers into the single graded answer.</td>
        </tr>
      </tbody>
    </table>

    <Note>
      Members and the synthesizer are themselves recipes, so any of them can be a
      <code>Model</code>, another <code>Fusion</code>, or a
      <RouterLink to="/sf-client/api/pipelines">Pipeline</RouterLink>, nested in any combination.
      Only the synthesizer's final answer is graded.
    </Note>

    <div class="not-prose">
      <NbCell :count="1" :code="fusionExample" />
    </div>
  </DocLayout>
</template>
