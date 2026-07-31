<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import Collapsible from '@/components/ui/Collapsible.vue'
import { sfClientNavigation as navigation } from '@/navigation/sf-client'

const configure = `import screamingface as sf

sf.config(engine="http://127.0.0.1:4404")`

const connect = `sf.connect()`

const compose = `ANSWER = "Answer this research prompt thoroughly, in prose, with specific evidence."
SYNTHESIS = "Combine the panel's answers into one unified prose answer. Add no new facts."

def answerer(route):
    return sf.Model(route, prompt=ANSWER, params={"temperature": 0, "max_tokens": 8192})

opus = answerer("openrouter/anthropic/claude-opus-4.8")
gpt = answerer("openrouter/openai/gpt-5.5")
gemini = answerer("openrouter/google/gemini-3.1-pro-preview")

frontier_trio = sf.Fusion(
    "frontier-trio",
    members=[opus, gpt, gemini],
    reducer=sf.reducers.Model(
        model="openrouter/anthropic/claude-opus-4.8",
        prompt=SYNTHESIS,
        params={"temperature": 0, "max_tokens": 8192},
    ),
)`

const lineup = `# Seven solo models answer on their own.
solos = [opus, gpt, gemini, fable, gemini_flash, kimi, deepseek]

# Nine Fusions combine them through a synthesis reducer. Reusing a Model object
# means that answer is computed once and shared, not requested twice.
fusions = [
    fable_plus_gpt,      # two frontier models
    frontier_trio,       # three frontier models
    opus_plus_gpt,
    opus_self_fusion,    # the same model sampled twice at temperature 0.7
    budget_trio,         # three cheaper models
    beat_runner_up,
    pareto_cross,
    pareto_lean,
    best_open_source,
]

candidates = (*solos, *fusions)   # 16 candidate roots, one shared case set`

const load = `draco = sf.benchmarks.load("draco-lite@1")`

const evaluate = `report = draco.evaluate(candidates)`

const read = `report.best                                  # highest-scoring candidate
report.candidates["frontier-trio"].score     # one candidate's score
report.candidates["frontier-trio"].coverage  # cases that produced a grade
report.url4                                  # the whole run, as one expression`
</script>

<template>
  <DocLayout
    title="Quickstart"
    description="Run DRACO-Lite end to end and compare seven solo models against nine ensembles built from them."
    :navigation="navigation"
  >
    <p>
      By the end you will have scored <strong>16 candidates</strong> — seven single models and nine
      ensembles assembled from those same models — against one research-grade rubric, and you will
      be able to read off which ensembles beat the models inside them.
    </p>

    <p>
      The whole study is
      <strong
        >one case, ten criteria, one judge pass per criterion, seven solo and nine Fusion
        candidates</strong
      >. It executes as a single request, so it is cheap enough to run while you are still learning
      the shape of the API.
    </p>

    <blockquote>
      You need the ScreamingFace Engine running and an OpenRouter connection first — see
      <RouterLink to="/sf-client/installation">Installation</RouterLink>. Every model below is an
      OpenRouter route, so one connection covers the whole study.
    </blockquote>

    <h2>1 · Point at an engine</h2>

    <CodeBlock :code="configure" language="python" />

    <p>
      The client never calls a model provider itself. It sends work to the engine, which owns
      credentials, datasets, and execution.
    </p>

    <h2>2 · Connect a provider</h2>

    <CodeBlock :code="connect" language="python" />

    <p>
      This renders a panel listing every provider the engine advertises. Paste an OpenRouter key
      into it. Credentials go to the engine, never into the notebook.
    </p>

    <h2>3 · Compose the candidates</h2>

    <CodeBlock :code="compose" language="python" />

    <p>
      A <code>Model</code> is one configured call. A <code>Fusion</code> combines members through an
      explicit reducer — here another model that synthesises the panel's answers. Both are built
      locally: constructing them makes no network request.
    </p>

    <Collapsible title="The full 16-candidate lineup">
      <CodeBlock :code="lineup" language="python" />
    </Collapsible>

    <h2>4 · Load the benchmark</h2>

    <CodeBlock :code="load" language="python" />

    <p>
      This reads the benchmark's manifest — its grader, judge model, and tool policy — from the
      engine. It does not download any cases.
    </p>

    <h2>5 · Evaluate</h2>

    <CodeBlock :code="evaluate" language="python" />

    <p>
      All 16 candidates are evaluated against the same case in one request. Requirements are checked
      up front, so a missing credential fails immediately rather than part-way through a paid run.
      Shared members are computed once, and a failure isolates to the candidates that depend on it.
    </p>

    <h2>6 · Read the study</h2>

    <CodeBlock :code="read" language="python" />

    <p>
      Each candidate carries its own score, coverage, and typed failures. Scores move between runs —
      one case graded by one judge pass is a fast integration check, not a measurement — so treat a
      single study as a shape to explore rather than a result to quote.
    </p>

    <p>
      <code>report.url4</code> is the entire run as one expression: the candidates, the case, the
      grader, and the aggregator. Anyone with that string and an engine can reproduce it exactly.
    </p>
  </DocLayout>
</template>
