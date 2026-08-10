<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import Collapsible from '@/components/ui/Collapsible.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbStateCarousel from '@/components/nb/NbStateCarousel.vue'
import ProviderConnections from '@/components/nb/ProviderConnections.vue'
import type { Provider } from '@/components/nb/ProviderConnections.vue'
import EvaluationReport from '@/components/nb/EvaluationReport.vue'
import CandidateScores from '@/components/nb/CandidateScores.vue'
import type { NbCheckItem, NbRowForm, NbStat } from '@/components/nb/types'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

// Every provider the development engine advertises, read from its registry.
const providers: Provider[] = [
  { id: 'codex', name: 'OpenAI Codex', status: 'disconnected' },
  { id: 'gemini', name: 'Google Gemini', status: 'disconnected' },
  { id: 'anthropic', name: 'Anthropic', status: 'disconnected' },
  { id: 'openrouter', name: 'OpenRouter', status: 'disconnected' },
  { id: 'huggingface', name: 'Hugging Face', status: 'disconnected' },
  { id: 'tavily', name: 'Tavily', status: 'disconnected' },
]

const connected = (id: string): Provider[] =>
  providers.map((p) => (p.id === id ? { ...p, status: 'connected' } : p))

// The connection flow, one state per step. Each is a plain prop set: the row
// holds no state of its own, so the sequence is readable in one place.
const connectSteps: { caption: string; providers: Provider[]; forms: Record<string, NbRowForm> }[] =
  [
    {
      caption:
        'Every provider the engine advertises, with its live status. Nothing is connected yet.',
      providers,
      forms: {},
    },
    {
      caption: 'Press Connect and the row offers the methods that provider supports.',
      providers,
      forms: { openrouter: { kind: 'options', choices: ['API key'], cancel: 'Cancel' } },
    },
    {
      caption: 'Choosing API key opens a field. The key travels to the engine, never to the page.',
      providers,
      forms: {
        openrouter: { kind: 'entry', placeholder: 'API key', confirm: 'Save', cancel: 'Cancel' },
      },
    },
    {
      caption: 'Paste the key. It is masked as you type and cleared after the attempt.',
      providers,
      forms: {
        openrouter: {
          kind: 'entry',
          value: 'sk-or-v1-0000000000',
          secret: true,
          focused: true,
          confirm: 'Save',
          cancel: 'Cancel',
        },
      },
    },
    {
      caption: 'Saving hands the key to the engine, which validates it before storing.',
      providers: providers.map((p) => (p.id === 'openrouter' ? { ...p, status: 'pending' } : p)),
      forms: {},
    },
    {
      caption:
        'OpenRouter is connected. One engine-scoped key covers every model route in this study.',
      providers: connected('openrouter'),
      forms: {},
    },
  ]

// Ten distinct researched model nodes, nine synthesis reducers, 16 candidate roots.
const runStats: NbStat[] = [
  { label: 'Models', value: '10/10' },
  { label: 'Synthesis', value: '9/9' },
  { label: 'Scoring', value: '16/16' },
  { label: 'Results', value: '16/16' },
]

const runRecent: NbCheckItem[] = [
  { label: 'Finalized best-open-source (1/1 cases scored)' },
  { label: 'Finalized pareto-lean (1/1 cases scored)' },
  { label: 'Finalized pareto-cross (1/1 cases scored)' },
]

// Scores from a real draco-lite@1 run: one case, ten criteria, one judge pass.
const studyCandidates = [
  { id: 'claude-fable-5', name: 'claude-fable-5', score: 88.0, casesScored: 1, casesTotal: 1 },
  { id: 'claude-opus-4.8', name: 'claude-opus-4.8', score: 100.0, casesScored: 1, casesTotal: 1 },
  { id: 'gpt-5.5', name: 'gpt-5.5', score: 88.0, casesScored: 1, casesTotal: 1 },
  {
    id: 'gemini-3.1-pro',
    name: 'gemini-3.1-pro-preview',
    score: 78.3,
    casesScored: 1,
    casesTotal: 1,
  },
  {
    id: 'gemini-3-flash',
    name: 'gemini-3-flash-preview',
    score: 88.0,
    casesScored: 1,
    casesTotal: 1,
  },
  { id: 'kimi-k2.5', name: 'kimi-k2.5', score: 75.9, casesScored: 1, casesTotal: 1 },
  { id: 'deepseek-v4-pro', name: 'deepseek-v4-pro', score: 88.0, casesScored: 1, casesTotal: 1 },
  { id: 'fable-plus-gpt', name: 'fable-plus-gpt', score: 88.0, casesScored: 1, casesTotal: 1 },
  { id: 'frontier-trio', name: 'frontier-trio', score: 100.0, casesScored: 1, casesTotal: 1 },
  { id: 'opus-plus-gpt', name: 'opus-plus-gpt', score: 100.0, casesScored: 1, casesTotal: 1 },
  { id: 'opus-self-fusion', name: 'opus-self-fusion', score: 78.3, casesScored: 1, casesTotal: 1 },
  { id: 'budget-trio', name: 'budget-trio', score: 100.0, casesScored: 1, casesTotal: 1 },
  { id: 'beat-runner-up', name: 'beat-runner-up', score: 100.0, casesScored: 1, casesTotal: 1 },
  { id: 'pareto-cross', name: 'pareto-cross', score: 88.0, casesScored: 1, casesTotal: 1 },
  { id: 'pareto-lean', name: 'pareto-lean', score: 75.9, casesScored: 1, casesTotal: 1 },
  { id: 'best-open-source', name: 'best-open-source', score: 75.9, casesScored: 1, casesTotal: 1 },
]

// The published full-benchmark result, not output from the code on this page.
// Three solo models did not complete every task; their coverage is shown as-is.
const publishedDraco = [
  { id: 'fable-gpt', name: 'Fable 5 + GPT-5.5', score: 68.6, casesScored: 100, casesTotal: 100 },
  {
    id: 'opus-gpt-ds',
    name: 'Opus + GPT-5.5 + DeepSeek',
    score: 67.0,
    casesScored: 100,
    casesTotal: 100,
  },
  {
    id: 'opus-gpt-gem',
    name: 'Opus 4.8 + GPT-5.5 + Gemini 3.1 Pro',
    score: 65.7,
    casesScored: 100,
    casesTotal: 100,
  },
  { id: 'opus-gpt', name: 'Opus 4.8 + GPT-5.5', score: 64.2, casesScored: 100, casesTotal: 100 },
  {
    id: 'ds-kimi-gpt',
    name: 'DeepSeek + Kimi + GPT-5.5',
    score: 61.9,
    casesScored: 100,
    casesTotal: 100,
  },
  { id: 'gpt-solo', name: 'GPT-5.5 (solo)', score: 60.2, casesScored: 100, casesTotal: 100 },
  { id: 'opus-opus', name: 'Opus 4.8 + Opus 4.8', score: 58.5, casesScored: 100, casesTotal: 100 },
  {
    id: 'budget-trio',
    name: 'Gemini 3 Flash + Kimi + DeepSeek',
    score: 58.5,
    casesScored: 100,
    casesTotal: 100,
  },
  {
    id: 'fable-solo',
    name: 'Claude Fable 5 (solo)',
    score: 57.8,
    casesScored: 92,
    casesTotal: 100,
    coverage: 92,
  },
  {
    id: 'ds-kimi-qwen',
    name: 'DeepSeek + Kimi + Qwen',
    score: 56.6,
    casesScored: 100,
    casesTotal: 100,
  },
  { id: 'ds-kimi', name: 'DeepSeek + Kimi', score: 54.3, casesScored: 100, casesTotal: 100 },
  {
    id: 'opus-solo',
    name: 'Claude Opus 4.8 (solo)',
    score: 51.8,
    casesScored: 100,
    casesTotal: 100,
  },
  {
    id: 'gemini-pro-solo',
    name: 'Gemini 3.1 Pro (solo)',
    score: 50.9,
    casesScored: 47,
    casesTotal: 100,
    coverage: 47,
  },
  { id: 'ds-solo', name: 'DeepSeek V4 Pro (solo)', score: 49.3, casesScored: 100, casesTotal: 100 },
  {
    id: 'flash-solo',
    name: 'Gemini 3 Flash (solo)',
    score: 35.9,
    casesScored: 100,
    casesTotal: 100,
  },
  {
    id: 'kimi-solo',
    name: 'Kimi K2.6 (solo)',
    score: 34.0,
    casesScored: 89,
    casesTotal: 100,
    coverage: 89,
  },
]

const configure = `import screamingface as sf

sf.config(engine="http://127.0.0.1:4404")`

const connect = `sf.connect()`

const connectScript = `import os

sf.connect("openrouter", api_key=os.environ["OPENROUTER_API_KEY"])
sf.connections.list()        # the same status the panel shows
sf.disconnect("openrouter")  # remove it again`

const connectOauth = `flow = sf.connect("codex", method="oauth")
flow.authorize_url           # open this in a browser
connection = flow.wait()     # blocks until you authorize, or the flow expires`

const compose = `ANSWER = "Answer this research prompt thoroughly, in prose, with specific evidence."
SYNTHESIS = "Combine the panel's answers into one unified prose answer. Add no new facts."

opus = sf.Model("openrouter/anthropic/claude-opus-4.8", prompt=ANSWER)
gpt = sf.Model("openrouter/openai/gpt-5.5", prompt=ANSWER)
gemini = sf.Model("openrouter/google/gemini-3.1-pro-preview", prompt=ANSWER, params={"temperature": 0, "max_tokens": 8192})

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
</script>

<template>
  <DocLayout
    title="Quickstart"
    description="Run DRACO-Lite end to end and compare seven solo models against nine fusions built from them."
    :navigation="navigation"
    :version="version"
  >
    <p>
      By the end you will have a scored comparison of <strong>16 candidates</strong>, seven single
      models and nine fusions built from those same models, on one DRACO case, with ten criteria and
      one judge pass each. It runs as a single request of roughly 80–85 provider calls.
    </p>

    <blockquote>
      You need the <RouterLink to="/learn/engine">ScreamingFace Engine</RouterLink> running and an
      OpenRouter connection first. See
      <RouterLink to="/sf-client/installation">Installation</RouterLink>. Every model below is an
      OpenRouter route, so one connection covers the whole study.
    </blockquote>

    <h2>1 · Point at an engine</h2>

    <p>
      The client is a thin wrapper that never calls a model provider itself. All work goes to the
      <strong>ScreamingFace Engine</strong>, a separate process that owns credentials, datasets, and
      execution. This first step tells the client where that engine is listening.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="configure" />
    </div>

    <p>
      That is the whole of setup. <code>sf.config()</code> validates and stores the URL without a
      network request, so a wrong address fails later, not here. It defaults to
      <code>http://127.0.0.1:4404</code> (the local engine), so you can omit the argument while
      working locally.
    </p>

    <p>
      <strong>If the engine is not running</strong>, the first call that needs it raises
      <code>EngineConnectionError</code>. A health check with
      <code>curl http://127.0.0.1:4404/healthz</code> can validate it before going further. A remote
      engine must be served over HTTPS. Provider credentials are refused over plain HTTP outside
      loopback.
    </p>

    <h2>2 · Connect a provider</h2>

    <p>
      The engine holds the credentials, so it needs at least one provider connected before it can
      call a model. <code>sf.connect()</code> with no arguments renders a panel of every provider
      this engine advertises. The example below connects <strong>OpenRouter</strong> with an API
      key, stepping through the six states of the whole auth flow.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="connect">
        <NbStateCarousel :steps="connectSteps" label="Connecting a provider">
          <template #default="{ step }">
            <ProviderConnections
              :providers="step.providers"
              :forms="step.forms"
              :busy="step.providers.some((p) => p.status === 'pending') ? ['openrouter'] : []"
              engine-url="http://127.0.0.1:4404"
            >
              <strong>Note:</strong> Dataset access is separate and <code>HF_TOKEN</code> belongs in
              the engine <code>.env</code> file, not in a provider connection.
            </ProviderConnections>
          </template>
        </NbStateCarousel>
      </NbCell>
    </div>

    <h3>Reading the panel</h3>

    <p>
      Each row is one provider: display name, its <strong>live status</strong>, and the available
      action. The status is read from the engine at render, not remembered, and is one of
      <code>NOT CONNECTED</code>, <code>CONNECTING</code>, <code>CONNECTED</code>,
      <code>NEEDS REAUTH</code>, or <code>ERROR</code>. The header names the engine handling the
      request, so you cannot connect a key to the wrong one by accident.
    </p>

    <blockquote>
      We chose OpenRouter for simplicity. You can compose fusions with models coming from any of
      these providers, and we're actively working to expand the local or third-party providers
      supported.
    </blockquote>

    <h3>Configure OpenRouter via script</h3>

    <p>
      Scripts connect without the panel: name the provider and pass its key directly. Read the key
      from the environment rather than writing it into source.
    </p>

    <CodeBlock :code="connectScript" language="python" />

    <p>
      <code>sf.connect(...)</code> returns a <code>Connection</code> with the validated status, so a
      bad key fails here, not at evaluation time. <code>sf.connections.list()</code> returns one per
      provider (the panel's data), and <code>sf.disconnect(...)</code> is safe even if never
      connected.
    </p>

    <p>
      Providers that authenticate by OAuth rather than an API key, namely Codex and Anthropic,
      return an <code>OAuthFlow</code> instead, which you complete in a browser:
    </p>

    <CodeBlock :code="connectOauth" language="python" />

    <p>
      The flow expires, so <code>flow.wait()</code> raises rather than blocking forever;
      <code>flow.expired</code> tells you whether that has happened and
      <code>flow.cancel()</code> abandons the attempt. Note that connection calls are refused over
      plain HTTP unless the engine is on loopback. A remote engine must be HTTPS.
    </p>

    <h2>3 · Compose the candidates</h2>

    <p>A <strong>candidate</strong> is a model or a fusion submitted for scoring.</p>

    <ul>
      <li>
        <code>sf.Model</code>: one configured call: a route, a prompt, and parameters. On its own it
        is a solo candidate.
      </li>
      <li>
        <code>sf.Fusion</code>: several members combined by an explicit <strong>reducer</strong>.
        Here the reducer is another model that synthesises the members' answers into one.
      </li>
    </ul>

    <div class="not-prose">
      <NbCell :count="3" :code="compose" />
    </div>

    <h3>Caching keeps reruns cheap</h3>

    <p>
      Every model call is cached. When a fusion reuses the same model, its response is served from
      the cache instead of being paid for again, so a run gets cheaper the more its candidates
      share. The cache is also shared across the community: if anyone has already run the same model
      configuration against a benchmark, that call is a cache hit for you as well, at no cost.
    </p>

    <p>
      One detail worth understanding before the next steps:
      <strong>reusing a Model object means its answer is computed once and shared</strong> across
      every candidate that contains it. That is what makes 16 candidates affordable and it is why a
      single failing model can only affect the candidates that depend on it.
    </p>

    <Collapsible title="The full 16-candidate lineup">
      <CodeBlock :code="lineup" language="python" />
    </Collapsible>

    <p>The lineup covers three patterns, each answering a different question:</p>

    <ul>
      <li>
        <strong>Pairs and trios of frontier models</strong>: does adding another strong model help?
      </li>
      <li>
        <strong><code>opus-self-fusion</code></strong
        >: one model fused with a second sample of itself at a higher temperature. Does a fusion
        help without adding a second model?
      </li>
      <li>
        <strong><code>budget-trio</code></strong
        >: three cheaper models. Can they reach a frontier model's score at lower cost?
      </li>
    </ul>

    <h2>4 · Load the benchmark</h2>

    <p>
      A benchmark lives on the engine, not in the client. Loading it fetches the
      <strong>manifest</strong>, which describes how the run will be scored: the grader, the judge
      model, the aggregator, and the tool policy. The client sees these rules before the run starts.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="load" />
    </div>

    <p>
      It does <strong>not</strong> download any questions. Cases are loaded engine-side at evaluation
      time, so a gated dataset is read with the <code>HF_TOKEN</code> in the
      <strong>engine's</strong> environment, not the client's. Provide it where the engine runs:
    </p>

    <ul>
      <li>
        <strong>Your own engine:</strong> put <code>HF_TOKEN=hf_…</code> in the engine's
        <code>.env</code> file, or <code>export</code> it before starting the engine, then restart.
        See <RouterLink to="/sf-client/installation">Installation</RouterLink> for the start command.
      </li>
      <li>
        <strong>A hosted engine:</strong> the operator sets the token, so gated datasets work only if
        they have configured one. There is nothing to pass from the client.
      </li>
    </ul>

    <p>
      <code>sf.benchmarks.list()</code> shows what this engine advertises.
      <code>draco-lite@1</code> appears only when its pinned judge model is in the gateway's
      catalog; if it is missing, check the engine's configuration.
    </p>

    <p>
      <code>draco-lite@1</code> is a trimmed-down version of the full benchmark: one pinned case,
      ten criteria spanning all four rubric sections, and one judge pass per criterion. It runs the
      same protocol as <code>draco@1</code>, which covers all 100 cases with five judge passes per
      criterion, so you can rehearse the full run at a fraction of the cost before committing to it.
    </p>

    <h2>5 · Evaluate</h2>

    <p>One call sends all 16 candidates as a <strong>single request</strong>.</p>

    <div class="not-prose">
      <NbCell :count="5" :code="evaluate">
        <EvaluationReport
          title="16 candidates"
          benchmark="draco-lite@1"
          phase="complete"
          elapsed="4M 51S"
          :done="16"
          :total="16"
          :stats="runStats"
          :recent="runRecent"
          recent-extra="+1 MORE"
          caption="Operation-level progress · model output appears when each call completes"
        />
      </NbCell>
    </div>

    <p>
      Before the first model call, the client verifies the run: the benchmark manifest still matches
      the engine (<code>EngineProtocolError</code>), every model route exists
      (<code>UnknownModelError</code>), members support the benchmark's tools
      (<code>UnsupportedToolError</code>), reducers are advertised
      (<code>UnsupportedReducerError</code>), required providers are connected
      (<code>ConnectionRequiredError</code>), and the compiled request fits the engine's size limit
      (<code>EngineRequestTooLargeError</code>). It all runs before anything is spent, so a
      misconfigured run costs nothing.
    </p>

    <p>
      The panel is live while the run proceeds. <code>MODELS</code> counts the distinct answering
      calls, ten, not sixteen, because shared members are computed once.
      <code>SYNTHESIS</code> counts the nine reducers, <code>SCORING</code> the graded candidates,
      and <code>RESULTS</code> the finalised ones. Progress advances on real grader results, never
      on a timer, so a stalled counter means work genuinely stalled.
    </p>

    <blockquote>
      <strong>This step costs money.</strong> Expect roughly 80–85 provider calls: ten answers, nine
      syntheses, and ten judge passes per graded candidate. It is minutes and cents rather than
      hours and dollars, but it is not free, and <code>draco@1</code> at 100 cases is a completely
      different order of spend.
    </blockquote>

    <p>
      If a model fails, only the candidates that depend on it are affected; the rest still score. A
      failure lowers that candidate's coverage rather than counting as a zero, so a partial result
      is visibly partial. Because every completed call is cached, re-running after a failure is free
      for the work that already succeeded: you are charged only for the new, uncached calls.
    </p>

    <h2>6 · Read the study</h2>

    <p>
      Displaying the report renders each candidate in the order you declared them, with its score,
      and marks the highest. Nine are shown here; the remaining seven are summarised as
      <code>+7 MORE</code>.
    </p>

    <div class="not-prose">
      <NbCell :count="6" code="report">
        <CandidateScores
          :candidates="studyCandidates"
          benchmark="draco-lite@1"
          case-label="1 case"
          :limit="9"
        />
      </NbCell>
    </div>

    <h3>What each column means</h3>

    <ul>
      <li>
        <strong>Score</strong>: the candidate's normalized rubric score. Ten criteria are judged, so
        values land on a coarse grid rather than anywhere in 0–100%.
      </li>
      <li>
        <strong>Coverage</strong>: how much of the case set produced a grade. Below 100% means
        something failed, and the score covers only what completed.
      </li>
      <li>
        <strong>BEST</strong>: marks the top scorer. Ties resolve to the first in declared order.
      </li>
    </ul>

    <h3>Reading it in code</h3>

    <ul>
      <li><code>report.best</code>: the highest-scoring candidate.</li>
      <li><code>report.candidates["frontier-trio"].score</code>: one candidate's score.</li>
      <li>
        <code>report.candidates["frontier-trio"].coverage</code>: cases that produced a grade.
      </li>
      <li><code>report.url4</code>: the whole run, as one expression.</li>
      <li><code>report.to_dict()</code>: everything above as plain JSON-compatible values.</li>
    </ul>

    <blockquote>
      <strong>Do not over-read a single run.</strong> One case judged once is an integration check,
      not a measurement: run it twice and the winner can change. Treat it as a shape to explore.
    </blockquote>

    <h2>What the full benchmark shows</h2>

    <p>
      The claim is demonstrated on all 100 DRACO tasks, not on this one-case sample. These are
      published figures, not output from the code above. Expect your own numbers to differ.
    </p>

    <div class="not-prose">
      <CandidateScores
        :candidates="publishedDraco"
        title="Published DRACO result"
        benchmark="draco@1"
        case-label="100 tasks"
        section-label="Score by candidate"
        :limit="8"
      />
    </div>

    <p>
      The strongest fusion beat the best single model by <strong>8.4 points</strong>, and five
      fusions beat every individual model. Three solo models did not complete every task, Gemini 3.1
      Pro finished only 47 of 100, so their scores are means over completed tasks and are not
      directly comparable. Full chart and method:
      <a
        href="https://andrewtrask.substack.com/p/6-weeks-ago-frontier-ai-labs-lost"
        target="_blank"
        rel="noopener"
        >published results</a
      >.
    </p>
  </DocLayout>
</template>
