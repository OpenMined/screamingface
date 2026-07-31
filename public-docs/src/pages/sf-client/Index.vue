<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import { sfClientNavigation as navigation } from '@/navigation/sf-client'

// The smallest complete run: configure an engine, compose a Fusion, evaluate it,
// read the comparison. Every name here is part of the shipped public API.
const smallestExample = `import screamingface as sf

sf.config(engine="http://127.0.0.1:4404")
members = ["openrouter/openai/gpt-5.5", "openrouter/google/gemini-3-flash-preview"]
fusion = sf.Fusion("pair", members=members, reducer=sf.reducers.MajorityVote())
report = sf.benchmarks.load("gpqa@1").evaluate(fusion, first=10)
report.score, report.baseline, report.gain`
</script>

<template>
  <DocLayout
    title="Overview"
    description="Compose an ensemble of frontier models, evaluate it against a benchmark, and see whether it beat its own best member."
    :navigation="navigation"
  >
    <p>
      ScreamingFace is an open-source client for building <strong>model ensembles</strong> — several
      frontier models answering the same question, combined into one answer — and measuring them
      against real benchmarks. It runs locally, and every run is reproducible from a single
      expression you can share.
    </p>

    <h2>The headline number</h2>

    <blockquote>
      <strong>Pending a verified run.</strong> A quotable gain figure needs a full
      <code>draco@1</code> evaluation — 100 cases with five independent judge passes per criterion.
      Single-case <code>draco-lite</code> runs move too much between runs to publish, so no number
      is claimed here yet.
    </blockquote>

    <h2>The smallest example</h2>

    <CodeBlock :code="smallestExample" language="python" />

    <p>
      <code>score</code> is the ensemble's accuracy, <code>baseline</code> is its strongest single
      member on the same cases, and <code>gain</code> is the difference between them. A positive
      gain means the ensemble beat every model inside it.
    </p>

    <h2>How it works</h2>

    <p>
      The client talks only to the <strong>ScreamingFace Engine</strong> — never to model providers
      directly. Each evaluation compiles to one <strong>URL4</strong> expression, and that
      expression is the contract between them: the engine resolves it, and anyone holding it can
      reproduce the run.
    </p>

    <h2>Where next</h2>

    <ul>
      <li>
        <RouterLink to="/sf-client/quickstartPage">Quickstart</RouterLink> — run a benchmark end to
        end and read the comparison.
      </li>
      <li>
        <RouterLink to="/sf-client/installation">Installation</RouterLink> — install the library and
        start the engine.
      </li>
      <li>
        <strong>User guides</strong> — connections, composing models and fusions, benchmarks, and
        reports. Coming soon.
      </li>
    </ul>
  </DocLayout>
</template>
