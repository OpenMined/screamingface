<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import { SF_ENGINE_URL } from '@/lib/engine'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

// The smallest complete run: name the engine, compose a Fusion, evaluate it
// beside its own member, read both scores. Every name here is shipped API.
const smallestExample = `import screamingface as sf

sf.configure(engine_url="${SF_ENGINE_URL}")

gpt = sf.Model("openrouter/openai/gpt-5.5")
flash = sf.Model("openrouter/google/gemini-3-flash-preview")
fusion = sf.Fusion([gpt, flash])

# Score the solo model beside the fusion, on the same cases.
report = sf.evaluate([gpt, fusion], benchmark="ifeval", limit=3)
{c.name: c.score for c in report.candidates}`

const smallestExampleOut = `{'gpt-5.5': 0.667, 'gpt-5.5+gemini-3-flash-preview': 1.0}`
</script>

<template>
  <DocLayout
    title="Overview"
    description="What ScreamingFace is, why a fusion can beat the best single model, and the smallest end-to-end run."
    :navigation="navigation"
    :version="version"
  >
    <p>
      ScreamingFace is an open-source Python client for building <strong>fusions</strong>: several
      models answering the same question, combined into one. You compose a fusion from providers you
      already have keys for, evaluate it against a real benchmark, and read how it did, in a
      notebook.
    </p>

    <p>
      Why bother? A fusion can score higher than any single model in it. In a reproduction of the
      <strong>DRACO</strong> deep-research benchmark, the strongest fusion reached
      <strong>68.6%</strong> against <strong>60.2%</strong> for the best single model, a
      <strong>+8.4-point</strong> gain, and five separate fusions beat every individual model (<a
        href="https://andrewtrask.substack.com/p/6-weeks-ago-frontier-ai-labs-lost"
        target="_blank"
        rel="noopener"
        >published results</a
      >). The effect appears in the literature too, such as
      <em>Beyond Leaderboards: Tokenomics of Agentic Small Language Model Ensembles</em> (Skurikhin
      et al., Los Alamos). It is not magic: the gains come from genuine diversity between models,
      and it can bring visible improvements and significant cost reductions.
    </p>

    <h2>How the stack helps you</h2>

    <ul>
      <li>
        <strong>One interface, every provider.</strong> Bring your own keys and compose across open
        and closed models.
      </li>
      <li>
        <strong>Honest measurement.</strong> Every run reports accuracy alongside its tokens, cost,
        and time, graded against a fixed benchmark so the comparison is fair.
      </li>
      <li>
        <strong>Reproducible from one line.</strong> Every run compiles to a single
        <RouterLink to="/learn/url4">url4</RouterLink> expression you can share.
      </li>
      <li>
        <strong>Cheap to repeat.</strong> Calls are cached, and a shared community cache makes
        re-running prior work nearly free.
      </li>
      <li>
        <strong>Build on what others did.</strong> Because anyone can reproduce a published run from
        its url4, you can start from someone else's result, iterate on it, and push the frontier
        further.
      </li>
    </ul>

    <h2>What url4 is</h2>

    <p>
      A <strong>url4</strong> is a one-line, human-readable expression that captures a whole run:
      the models, how they combine, and the benchmark, in a single shareable string. Hand someone
      the url4 and they reproduce the exact result. It is the receipt for a run.
    </p>

    <h2>Two ways to run</h2>

    <p>
      You point the client at an <RouterLink to="/learn/engine">engine</RouterLink>, the runtime
      that does the work. There are two ways to get one:
    </p>

    <ul>
      <li>
        <strong>Local.</strong> Run the engine on your own machine, on your own keys. There is no
        middleman on the local path.
      </li>
      <li>
        <strong>Hosted.</strong> Use an engine we operate, which adds subsidized compute for chosen
        cohorts and the shared cache.
      </li>
    </ul>

    <p>
      The client code is the same either way; only the engine URL changes. The
      <RouterLink to="/sf-client/installation">Installation</RouterLink> guide covers both.
    </p>

    <h2>The smallest example</h2>

    <div class="not-prose">
      <NbCell :count="1" :code="smallestExample"><NbTextOut :text="smallestExampleOut" /></NbCell>
    </div>

    <p>
      <code>score</code> is each candidate's accuracy on the same cases, and higher is always
      better. There is no separate baseline or gain. The comparison <em>is</em> putting the solo
      model and the fusion in one run and reading both numbers.
    </p>

    <h2>How it works</h2>

    <p>
      The client talks only to the <strong>ScreamingFace Engine</strong>, never to model providers
      directly. Each evaluation compiles to one <strong>url4</strong> expression, and that
      expression is the contract between them: the engine resolves it, and anyone holding it can
      reproduce the run.
    </p>
  </DocLayout>
</template>
