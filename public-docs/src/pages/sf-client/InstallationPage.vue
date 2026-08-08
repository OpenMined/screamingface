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

const SOURCE =
  'git+https://github.com/OpenMined/screamingface' +
  '@OME-605-screamingface-client-v1#subdirectory=packages/screamingface'

const pypiNotebook = `!pip install "screamingface[notebook]"`
const pypiTerminal = `uv pip install "screamingface[notebook]"`

const sourceNotebook = `!pip install "screamingface[notebook] @ ${SOURCE}"`
const sourceTerminal = `uv venv --python 3.12
uv pip install "screamingface[notebook] @ ${SOURCE}"`

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
    description="Install the client, and point it at an engine: hosted, or one you run yourself."
    :navigation="navigation"
    :version="version"
  >
    <p>
      Two things are needed to successfully complete the installation: the <strong>client</strong>,
      a Python library, and an <strong>engine</strong>, which does the work. The client never calls
      a model provider itself, so it always needs an engine to talk to.
    </p>

    <p>
      You can reach a <strong>hosted</strong> engine that someone else runs, or run a
      <strong>self-hosted</strong> one yourself. The first takes a few lines while the second is
      described in the rest of this page.
    </p>

    <h2>1 · Install the client</h2>

    <p>Python <strong>3.12 or newer</strong>. In a notebook, one cell:</p>

    <div class="not-prose">
      <NbCell :count="1" :code="pypiNotebook" />
    </div>

    <p>Or from a terminal:</p>

    <CodeBlock :code="pypiTerminal" language="bash" />

    <blockquote>
      <strong>Not on PyPI yet.</strong> Until it is published, install from source instead. The
      commands below are the same, with the repository as the package's origin.
    </blockquote>

    <p>In a notebook:</p>

    <div class="not-prose">
      <NbCell :count="1" :code="sourceNotebook" />
    </div>

    <p>From a terminal:</p>

    <CodeBlock :code="sourceTerminal" language="bash" />

    <p>
      The <code>[notebook]</code> extra pulls ipywidgets and jupyterlab, which is what makes
      <code>sf.connect()</code> render a live panel instead of static text. Drop it if you are
      writing scripts. Everything else, including <code>url4</code>, resolves automatically.
    </p>

    <p>A quick check that it worked:</p>

    <div class="not-prose">
      <NbCell :count="2" :code="verify" />
    </div>

    <h2>2 · Reach a hosted engine</h2>

    <p>
      Name the engine once and every later call uses it. Without this the client looks on your own
      machine, finds nothing, and fails.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="point" />
    </div>

    <p>
      A hosted engine sits behind Cloudflare Access. There is no token to paste.
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

    <h2>3 · Run your own engine</h2>

    <p>
      Self-hosting means running two services: <strong>AI Gateway</strong>, which holds provider
      credentials, and the <strong>Engine</strong>, which executes runs. Both live in the
      repository, so start from a checkout.
    </p>

    <h3>AI Gateway</h3>

    <p>
      A fresh install has no database schema, so migrate before the first start, otherwise it
      crashes on boot. Two environment variables matter: local mode expects anonymous callers, and
      the OpenRouter plugin ships <strong>disabled</strong>, so a valid key is refused until you
      turn it on.
    </p>

    <CodeBlock :code="gateway" language="bash" />

    <h3>Benchmark assets</h3>

    <p>
      The Engine never downloads datasets at runtime. That is deliberate: a run cannot silently
      execute against a different revision of a benchmark than you think. Prepare them once:
    </p>

    <Note>
      On macOS this download often fails TLS verification, because the system Python ships without a
      CA bundle. If you see <code>CERTIFICATE_VERIFY_FAILED</code>, the fix is in the FAQ below.
    </Note>

    <CodeBlock :code="assets" language="bash" />

    <h3>The Engine</h3>

    <CodeBlock :code="engine" language="bash" />

    <p>
      It serves on <code>127.0.0.1:9108</code>, loopback only. Point the client at it, and skip the
      login step. A local engine advertises no Cloudflare Access.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="localPoint" />
    </div>

    <h2>Check it works</h2>

    <CodeBlock :code="health" language="bash" />

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
        No. Reaching a hosted one is the shorter path, and everything in section 3 exists for people
        who want the whole stack inside their own walls.
      </p>
    </Collapsible>
  </DocLayout>
</template>
