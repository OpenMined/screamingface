<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import Collapsible from '@/components/ui/Collapsible.vue'
import Note from '@/components/ui/Note.vue'
import NbCell from '@/components/nb/NbCell.vue'
import { SF_ENGINE_URL } from '@/lib/engine'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const pypiNotebook = `!pip install "screamingface[notebook]"`
const pypiTerminal = `uv pip install "screamingface[notebook]"`

const verify = `import screamingface as sf

len(sf.__all__)   # 36`

const point = `import screamingface as sf

sf.configure(engine_url="${SF_ENGINE_URL}")`

const loginCode = `client = sf.Client(engine_url="${SF_ENGINE_URL}")
client.login()          # opens Cloudflare Access in your browser
client.authenticated    # True once the token arrives`

const connectCode = `sf.connect()   # the provider panel`

const gateway = `cd apps/aigateway
uv sync
uv run aigateway migrate

AIGW_AUTH_MODE=disabled AIGW_OPENROUTER_ENABLED=true \\
  uv run uvicorn aigateway.main:app --port 9105`

const assets = `cd apps/url4-cloud
uv sync
uv run --with datasets python -m url4_cloud.benchmarks.ifeval.prepare \\
  --out /tmp/screamingface-benchmark-assets/ifeval`

const engine = `URL4_BENCHMARK_ASSETS=/tmp/screamingface-benchmark-assets \\
  uv run url4-cloud serve --local`

const localPoint = `sf.configure(engine_url="http://127.0.0.1:9108")`

const health = `curl -sf http://localhost:9105/healthz      # {"status":"ok"}
curl -s  http://localhost:9108/v1/benchmarks   # draco, ifeval`

const certs = `SSL_CERT_FILE=$(uv run --with certifi python -c "import certifi;print(certifi.where())") \\
  uv run --with datasets python -m url4_cloud.benchmarks.ifeval.prepare \\
  --out /tmp/screamingface-benchmark-assets/ifeval`
</script>

<template>
  <DocLayout
    title="Installation"
    description="Install the client, and point it at an engine you run yourself, or a hosted one."
    :navigation="navigation"
    :version="version"
  >
    <p>Installing has two parts:</p>

    <ul>
      <li>
        The <strong>client</strong>, a Python library. It never calls a model provider itself, so it
        always needs an engine to talk to.
      </li>
      <li>
        An <RouterLink to="/learn/engine"><strong>engine</strong></RouterLink>, which does the work.
        There are two ways to get one:
        <ul>
          <li><strong>Option A</strong> runs one on your own machine, on your own keys.</li>
          <li><strong>Option B</strong> points at a hosted engine someone else runs.</li>
        </ul>
      </li>
    </ul>

    <p>The client code is the same either way, so pick whichever you prefer.</p>

    <h2>1 · Install the client</h2>

    <p>Python <strong>3.12 or newer</strong>. In a notebook, one cell:</p>

    <div class="not-prose">
      <NbCell :count="1" :code="pypiNotebook" />
    </div>

    <p>Or from a terminal:</p>

    <CodeBlock :code="pypiTerminal" language="bash" />

    <p>
      Prefer to install from source? Install it the same way from the
      <a href="https://github.com/OpenMined/screamingface" target="_blank" rel="noopener"
        >source repository</a
      >.
    </p>

    <p>
      The <code>[notebook]</code> extra pulls ipywidgets and jupyterlab, which is what makes
      <code>sf.connect()</code> render a live panel instead of static text. Drop it if you are
      writing scripts. Everything else, including
      <RouterLink to="/learn/url4"><code>url4</code></RouterLink>, resolves automatically.
    </p>

    <p>A quick check that it worked:</p>

    <div class="not-prose">
      <NbCell :count="2" :code="verify" />
    </div>

    <h2>2 · Configure your engine</h2>

    <p>Choose one of the two options below.</p>

    <h3>Option A: Run your own engine</h3>

    <p>
      The local path runs everything on your machine, on your own keys, with no account and no
      login. Clone the
      <a href="https://github.com/OpenMined/screamingface" target="_blank" rel="noopener"
        >repository</a
      >, start two small services, and point the client at them.
    </p>

    <h4>AI Gateway</h4>

    <p>Holds your provider keys. One command starts it:</p>

    <CodeBlock :code="gateway" language="bash" />

    <h4>Benchmark assets</h4>

    <p>
      The Engine reads datasets from disk rather than downloading them at runtime, so a run cannot
      silently use a different revision than you expect. Prepare them once:
    </p>

    <Note>
      On macOS, if this fails with <code>CERTIFICATE_VERIFY_FAILED</code>, the one-line fix is in
      the FAQ below.
    </Note>

    <CodeBlock :code="assets" language="bash" />

    <h4>The Engine</h4>

    <p>Executes runs, serving on <code>127.0.0.1:9108</code>, loopback only.</p>

    <CodeBlock :code="engine" language="bash" />

    <h4>Point the client at it</h4>

    <div class="not-prose">
      <NbCell :count="1" :code="localPoint" />
    </div>

    <p>No login step: a local engine advertises no Cloudflare Access.</p>

    <h4>Check it works</h4>

    <CodeBlock :code="health" language="bash" />

    <h3>Option B: Reach a hosted engine</h3>

    <p>
      Prefer not to run anything yourself? Point the client at a hosted engine instead. Name it once
      and every later call uses it.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="point" />
    </div>

    <p>
      A hosted engine sits behind Cloudflare Access. There is no token to paste:
      <code>login()</code> opens your browser and collects it.
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="loginCode" />
    </div>

    <p>
      Then connect a model provider, so the engine has a credential to call models with. The
      <RouterLink to="/sf-client/guides/connections">Connections</RouterLink> guide covers the rest.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="connectCode" />
    </div>

    <p>
      That is the whole hosted path. Go and run the
      <RouterLink to="/sf-client/quickstartPage">Quickstart</RouterLink>.
    </p>

    <h2>Frequently Asked Questions</h2>

    <Collapsible title='AI Gateway crashes with "no such table: secret_master_keys"'>
      <p>
        It started before its migrations ran. A fresh install has no schema until you apply them.
        Stop it, run <code>uv run aigateway migrate</code>, and start it again.
      </p>
    </Collapsible>

    <Collapsible title="A valid provider key is rejected">
      <p>
        The OpenRouter plugin ships disabled, so AI Gateway refuses the key regardless of whether it
        is good. Restart with <code>AIGW_OPENROUTER_ENABLED=true</code>.
      </p>
      <p>
        Worth knowing, because the error names the credential rather than the configuration. It is
        easy to spend a while checking a key that was never the problem.
      </p>
    </Collapsible>

    <Collapsible title="CERTIFICATE_VERIFY_FAILED while preparing benchmark assets">
      <p>
        A macOS Python without a CA bundle, so the dataset download cannot verify TLS. Point that
        one command at certifi's bundle:
      </p>
      <CodeBlock :code="certs" language="bash" />
    </Collapsible>

    <Collapsible title="Do I have to run my own engine?">
      <p>
        No. Option B points at a hosted engine and skips the local setup entirely. Option A exists
        for people who want the whole stack on their own machine.
      </p>
    </Collapsible>
  </DocLayout>
</template>
