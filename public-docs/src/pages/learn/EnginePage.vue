<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import { learnNavigation as navigation } from '@/navigation/learn'

const GH_TREE = 'https://github.com/OpenMined/screamingface/tree/main'

const point = `import screamingface as sf

sf.config(engine="http://127.0.0.1:4404")   # the Client talks only to an Engine`

const health = `curl http://127.0.0.1:4404/healthz`
</script>

<template>
  <DocLayout
    title="ScreamingFace Engine"
    description="The runtime that turns a url4 expression into a result — and the trust boundary that holds the keys."
    :navigation="navigation"
  >
    <p>
      The Engine is the execution runtime for
      <RouterLink to="/learn/url4">url4</RouterLink>. The
      <RouterLink to="/sf-client">Client</RouterLink> never calls a model provider itself — it hands
      a url4 expression to an Engine, and the Engine does the work: it schedules the graph, reaches
      the providers, and streams back usage and the result. Because it sits between you and the
      providers, it is also the system's <strong>trust boundary</strong>.
    </p>

    <h2>How it executes</h2>

    <p>
      At its core is a <strong>demand-driven, memoized DAG executor</strong>. It walks the graph from
      the result backwards, so only the nodes a result needs are scheduled. Each node runs as one
      task keyed by identity, so a value shared by several branches is computed exactly once.
      Independent nodes run concurrently inside a single task group; the first failure cancels its
      siblings rather than letting a broken run drift on, and overall concurrency is bounded so a
      wide fan-out can't overwhelm the providers.
    </p>

    <p>
      The executor lives in
      <a :href="`${GH_TREE}/packages/url4/src/url4/dag`" target="_blank" rel="noopener"><code>packages/url4/…/dag</code></a>;
      the cloud service that wraps it — control plane, one-shot runner, and the streaming wire
      protocol — is
      <a :href="`${GH_TREE}/apps/url4-cloud`" target="_blank" rel="noopener"><code>apps/url4-cloud</code></a>.
    </p>

    <h2>The trust boundary</h2>

    <p>
      The Engine owns what must not leak. Provider credentials are handed to it once and stored
      encrypted at rest (AES-256-GCM) by the AI gateway's credential store; they are never returned
      to the client. Benchmark answer keys and grading stay engine-side too — prompts cross the
      boundary to the models, answers and rubrics do not. That separation is what makes a verified
      result meaningful rather than self-reported.
    </p>

    <ul>
      <li>
        <strong>Credentials</strong> — encrypted <code>credential_blobs</code> in the
        <a :href="`${GH_TREE}/apps/aigateway`" target="_blank" rel="noopener">AI gateway</a>; the
        master key <code>AIGATEWAY_SECRET_KEY</code> is never stored with the data or logged.
      </li>
      <li>
        <strong>One endpoint, every provider</strong> — the Engine fans out to open and closed
        providers alike through the LiteLLM-based gateway, so a fusion can mix models from different
        vendors behind a single connection.
      </li>
      <li>
        <strong>Full usage accounting</strong> — it streams per-node events as the graph runs:
        tokens, cost, latency, and structured spans, so a run is observable while it happens.
      </li>
    </ul>

    <h2>Running one</h2>

    <p>
      Point the Client at an Engine with one call. The Client's local default is
      <code>http://127.0.0.1:4404</code>, so you can omit the argument while working locally:
    </p>

    <CodeBlock :code="point" language="python" />

    <p>A health check confirms it is up before you spend anything:</p>

    <CodeBlock :code="health" language="bash" />

    <p>
      The same code runs three ways: <strong>bundled</strong> invisibly inside the Client and
      <RouterLink to="/learn/url4-sdk">SDK</RouterLink>, <strong>self-hosted</strong> for a team that
      wants the whole system inside its own walls, or <strong>hosted</strong> for shared,
      subsidised capacity. The cloud deployment (Kubernetes Jobs, a streaming event bus, a Helm
      chart) lives in
      <a :href="`${GH_TREE}/apps/url4-cloud`" target="_blank" rel="noopener"><code>apps/url4-cloud</code></a>;
      a local run needs none of it.
    </p>

    <blockquote>
      The Engine is not a router — a router picks one model per call, the Engine composes many into a
      graph. It is not open compute either: hosted capacity is subsidised for chosen cohorts, and
      self-hosting is on your own hardware.
    </blockquote>

    <h2>Where the code lives</h2>

    <ul>
      <li>
        <a :href="`${GH_TREE}/apps/url4-cloud`" target="_blank" rel="noopener"><code>apps/url4-cloud</code></a>
        — the Engine service (backend, runner, shared wire protocol).
      </li>
      <li>
        <a :href="`${GH_TREE}/packages/url4/src/url4/dag`" target="_blank" rel="noopener"><code>packages/url4/…/dag</code></a>
        — the DAG executor it drives.
      </li>
      <li>
        <a :href="`${GH_TREE}/apps/aigateway`" target="_blank" rel="noopener"><code>apps/aigateway</code></a>
        — the credential store and provider gateway.
      </li>
    </ul>
  </DocLayout>
</template>
