<script setup lang="ts">
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

// The smallest complete run: configure an engine, compose a Fusion, evaluate it,
// read the comparison. Every name here is part of the shipped public API.
const smallestExample = `import screamingface as sf

sf.config(engine="http://127.0.0.1:4404")
members = ["openrouter/openai/gpt-5.5", "openrouter/google/gemini-3-flash-preview"]
fusion = sf.Fusion("pair", members=members, reducer=sf.reducers.MajorityVote())
report = sf.benchmarks.load("gpqa@1").evaluate(fusion, first=10)
print(report.score, report.baseline, report.gain)`
</script>

<template>
  <DocLayout
    title="Overview"
    description="Compose a fusion of frontier models, evaluate it against a benchmark, and see whether it beat its own best member."
    :navigation="navigation"
    :version="version"
  >
    <p>
      ScreamingFace is an open-source client for building <strong>fusions</strong> — several frontier
      models answering the same question, combined into one — and measuring them against real
      benchmarks. It runs locally, and every run reproduces from a single <code>url4</code>
      expression you can share.
    </p>

    <h2>The headline number</h2>

    <p>
      On <strong>DRACO</strong>, a 100-task deep-research benchmark, the strongest fusion scored
      <strong>68.6%</strong> against <strong>60.2%</strong> for the best single model —
      <strong>+8.4 points</strong>. Five separate fusions beat every individual model, so it is not
      one lucky pairing, and a fusion of three cheaper models reached 58.5%, ahead of Claude Opus
      4.8 alone at 51.8%.
    </p>

    <p>
      Source:
      <a
        href="https://andrewtrask.substack.com/p/6-weeks-ago-frontier-ai-labs-lost"
        target="_blank"
        rel="noopener"
        >~6 weeks ago… frontier AI labs lost the “deep research” frontier</a
      >, Andrew Trask. Scores are mean normalized score across completed tasks, judged by
      <code>gemini-3.1-pro-preview</code>.
    </p>

    <h2>The smallest example</h2>

    <CodeBlock :code="smallestExample" language="python" />

    <p>
      <code>score</code> is the fusion's accuracy, <code>baseline</code> is its strongest single
      member on the same cases, and <code>gain</code> is the difference between them. A positive
      gain means the fusion beat every model inside it.
    </p>

    <blockquote>
      <strong>Designed for notebooks.</strong> Scripts work, but you lose most of the feedback:
      <code>sf.connect()</code> renders an interactive provider panel, and models, fusions,
      benchmarks and reports each render a rich card. In a terminal those become plain text, so
      remember to <code>print()</code> anything you want to see.
    </blockquote>

    <h2>How it works</h2>

    <p>
      The client talks only to the <strong>ScreamingFace Engine</strong> — never to model providers
      directly. Each evaluation compiles to one <strong>url4</strong> expression, and that expression
      is the contract between them: the engine resolves it, and anyone holding it can reproduce the
      run.
    </p>
  </DocLayout>
</template>
