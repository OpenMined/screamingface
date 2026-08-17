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
const pypiRuntime = `pip install "screamingface[runtime,notebook]"`

const verify = `import screamingface as sf

len(sf.__all__)   # 53`

const point = `import screamingface as sf

sf.configure(engine_url="${SF_ENGINE_URL}")`

const loginCode = `client = sf.Client(engine_url="${SF_ENGINE_URL}")
client.login()          # opens Cloudflare Access in your browser
client.authenticated    # True once the token arrives`

const connectCode = `sf.connect()   # the provider panel`

const prepare = `$ screamingface prepare draco
Benchmark assets ready at /Users/you/.screamingface/benchmark-assets`

const up = `$ screamingface up
ScreamingFace is ready.
  Gateway    http://127.0.0.1:9105
  Scoreboard http://127.0.0.1:9106
  Engine     http://127.0.0.1:9108
  Logs       /Users/you/.screamingface/runtime.log`

const status = `$ screamingface status
ScreamingFace: running
  gateway    UP    http://127.0.0.1:9105
  scoreboard UP    http://127.0.0.1:9106
  engine     UP    http://127.0.0.1:9108
  logs       /Users/you/.screamingface/runtime.log`

const down = `screamingface down`
const logs = `screamingface logs --tail 50`

const tavily = `export TAVILY_API_KEY="tvly-..."
screamingface up`

const searchCheck = `gpt = sf.models.get("openrouter/openai/gpt-5.5")
"web_search" in gpt.tools   # True when the provider searches for itself`

const localPoint = `sf.configure(engine_url="http://127.0.0.1:9108")`

const certs = `SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())") \\
  screamingface prepare draco`
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
        An <RouterLink to="/learn/engine"><strong>engine</strong></RouterLink
        >, which does the work. There are two ways to get one:
        <ul>
          <li>
            <strong>Option A</strong> runs one on your own machine, on your own keys. It ships in
            the same package, so this is a pip extra and one command, not a separate deployment.
          </li>
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
      <RouterLink to="/learn/url4"><code>url4</code></RouterLink
      >, resolves automatically.
    </p>

    <p>To run the engine yourself as well, add the <code>[runtime]</code> extra:</p>

    <CodeBlock :code="pypiRuntime" language="bash" />

    <p>
      <code>[runtime]</code> is what turns the client install into a working engine: it brings in
      the server stack the local runtime needs, and it installs the
      <code>screamingface</code> command used in Option A. It is a much heavier install than the
      client alone, so skip it if you are pointing at a hosted engine.
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
      login. With the <code>[runtime]</code> extra installed you need no clone and no compose file:
      three commands prepare the data, start the stack, and stop it again.
    </p>

    <h4>Prepare the benchmark data</h4>

    <p>
      The engine reads benchmark datasets from disk rather than downloading them mid-run, so a run
      cannot silently use a different revision than you expect. Fetch the one you intend to run,
      once:
    </p>

    <CodeBlock :code="prepare" language="bash" />

    <p>
      The argument is the benchmark family: <code>draco</code>, <code>ifeval</code> or
      <code>healthbench</code>. Pass <code>--all</code> instead of a name to fetch all three. Assets
      land under <code>~/.screamingface/benchmark-assets</code>, which you can relocate with
      <code>--data-dir</code> or <code>SCREAMINGFACE_DATA_DIR</code>. Naming both a benchmark and
      <code>--all</code> is refused rather than guessed at.
    </p>

    <Note>
      On macOS, if this fails with <code>CERTIFICATE_VERIFY_FAILED</code>, the one-line fix is in
      the FAQ below.
    </Note>

    <h4>Start the stack</h4>

    <CodeBlock :code="up" language="bash" />

    <p>
      One command, three services: the <strong>engine</strong> executes runs, the
      <strong>gateway</strong> holds your provider keys and calls the models, and the
      <strong>scoreboard</strong> serves the local leaderboard. All three bind loopback only, on
      ports 9105, 9106 and 9108, and <code>up</code> refuses to start if another process already
      holds one of them rather than half-starting the stack. It runs in the background; add
      <code>--foreground</code> to keep it attached to your terminal instead.
    </p>

    <Note>
      By default the client reads and writes the <strong>hosted</strong> leaderboard at
      <code>leaderboard.dev.screamingface.ai</code>, even when the rest of your stack is local.
      Override it the same way you set the engine — <code>sf.configure()</code> takes a
      <code>scoreboard_url</code> next to <code>engine_url</code>, so
      <code>sf.configure(engine_url="http://127.0.0.1:9108", scoreboard_url="http://127.0.0.1:9106")</code>
      points both at your local stack.
    </Note>

    <p>
      Set <code>AIGW_OPENROUTER_ENABLED=true</code> in that shell first if you plan to use
      OpenRouter. Provider plugins ship disabled, and the gateway reads the setting at startup, so a
      key for a disabled provider is refused however good the key is.
    </p>

    <h4>Check it, read it, stop it</h4>

    <CodeBlock :code="status" language="bash" />

    <p>
      <code>status</code> reports each service separately, because "the engine is up" and "the
      gateway is up" are different facts. It exits non-zero when anything is wrong, so it works in a
      script: <code>running</code> means all three answered, <code>partially healthy</code> means
      the runtime is alive but a service is not answering yet, <code>stopped</code> means nothing is
      running, and <code>foreign processes occupy runtime ports</code> means something that is not
      ScreamingFace holds one of the three ports.
    </p>

    <p>Everything the stack logs goes to one file, which <code>logs</code> follows:</p>

    <CodeBlock :code="logs" language="bash" />

    <p>And when you are done:</p>

    <CodeBlock :code="down" language="bash" />

    <h4>Give the engine a web-search key</h4>

    <p>
      Benchmarks like DRACO ask candidates to research an answer, which means the model needs to
      search the web. <strong>Most of the time this is handled for you:</strong> most providers
      search natively, and the engine just asks them to. The exception is providers that offer no
      web search of their own — <strong>Hugging Face</strong> routes in particular — where the engine
      falls back to a <strong>bounded tool loop it runs against Tavily</strong>. Only those routes
      need a key.
    </p>

    <p>
      This is why your own engine may occasionally need a Tavily key while a hosted one never asks
      you for one: on the hosted path we supply it. If you're running routes without native search,
      export it in the shell you start the runtime from, before <code>up</code>, because the engine
      reads it at startup:
    </p>

    <CodeBlock :code="tavily" language="bash" />

    <p>
      Without the key, web tools stay off. That is deliberate deny-by-default rather than a degraded
      mode, and the consequence is worth knowing: a candidate whose route depends on the Tavily loop
      <strong>fails before its first paid model request</strong>, instead of quietly answering a
      research question with no research behind it. A key you do not need costs nothing to omit, so
      it is only required when the providers you are actually running lack search of their own.
    </p>

    <p>
      To know which case you are in, ask the engine what a route supports. Anything advertising
      <code>web_search</code> can search for itself:
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="searchCheck" />
    </div>

    <p>
      Benchmarks that never search, such as <code>ifeval</code>, need no key at all: their
      candidates are asked to follow instructions, not to look anything up.
    </p>

    <h4>Point the client at it</h4>

    <div class="not-prose">
      <NbCell :count="2" :code="localPoint" />
    </div>

    <p>No login step: a local engine advertises no Cloudflare Access.</p>

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
      That is the whole hosted path, and it is enough to start running evaluations. The
      <RouterLink to="/sf-client/quickstartPage">Quickstart</RouterLink> takes it from here.
    </p>

    <h2>Frequently Asked Questions</h2>

    <Collapsible title='"Local runtime dependencies are missing" or command not found'>
      <p>
        The client is installed but the engine is not. The <code>screamingface</code> command and
        the server stack both come from the <code>[runtime]</code> extra:
      </p>
      <CodeBlock :code="pypiRuntime" language="bash" />
      <p>
        Reopen your shell afterwards if the command still is not found, so the new entry point is
        picked up.
      </p>
    </Collapsible>

    <Collapsible title="up refuses to start: a port is already in use">
      <p>
        The stack needs 9105, 9106 and 9108, and it names the occupied ones rather than starting
        halfway. Run <code>screamingface status</code>: if it says
        <code>foreign processes occupy runtime ports</code>, something unrelated holds them and you
        need to free it. If a previous stack is still up, <code>screamingface down</code> is enough.
      </p>
    </Collapsible>

    <Collapsible title="A valid provider key is rejected">
      <p>
        Provider plugins ship disabled, so the gateway refuses the key regardless of whether it is
        good. Export <code>AIGW_OPENROUTER_ENABLED=true</code> and restart the stack with
        <code>screamingface down &amp;&amp; screamingface up</code>.
      </p>
      <p>
        Worth knowing, because the error names the credential rather than the configuration. It is
        easy to spend a while checking a key that was never the problem.
      </p>
    </Collapsible>

    <Collapsible title="Do I need a Tavily key?">
      <p>
        Only when you run your own engine <em>and</em> the routes you evaluate cannot search the web
        themselves. A hosted engine supplies its own key, and benchmarks that never search, such as
        <code>ifeval</code>, do not need one either. See
        <em>Give the engine a web-search key</em> above.
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
