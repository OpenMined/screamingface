<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import Collapsible from '@/components/ui/Collapsible.vue'
import NbCell from '@/components/nb/NbCell.vue'
import { SF_ENGINE_URL } from '@/lib/engine'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const install = `pip install "screamingface[runtime,notebook]"`

const verify = `import screamingface as sf

len(sf.__all__)   # 36`

const point = `import screamingface as sf

sf.configure(engine_url="${SF_ENGINE_URL}")`

const loginCode = `client = sf.Client(engine_url="${SF_ENGINE_URL}")
client.login()          # opens Cloudflare Access in your browser
client.authenticated    # True once the token arrives`

const connectCode = `sf.connect()   # the provider panel`

const prepareDraco = `screamingface prepare draco`

const localPoint = `sf.configure(engine_url="http://127.0.0.1:9108")`

const engineUp = `screamingface up`

const engineStatus = `screamingface status`

const engineDown = `screamingface down`

const tavily = `export TAVILY_API_KEY="tvly-..."`
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

    <p>Python <strong>3.12 or newer</strong>. Install the client, local runtime, and notebook UI:</p>

    <CodeBlock :code="install" language="bash" />

    <p>
      Prefer to install from source? Install it the same way from the
      <a href="https://github.com/OpenMined/screamingface" target="_blank" rel="noopener"
        >source repository</a
      >.
    </p>

    <p>
      The <code>[runtime]</code> extra installs the local Engine and its helper commands. The
      <code>[notebook]</code> extra pulls ipywidgets and jupyterlab, which is what makes
      <code>sf.connect()</code> render a live panel instead of static text.
    </p>

    <p>A quick check that it worked:</p>

    <div class="not-prose">
      <NbCell :count="2" :code="verify" />
    </div>

    <h2>2 · Configure your engine</h2>

    <p>Choose one of the two options below.</p>

    <h3>Option A: Run your own engine</h3>

    <p>
      The local path runs the Engine on your machine, on your own keys, with no account and no
      login. You do not need a source checkout.
    </p>

    <h4>Prepare DRACO</h4>

    <p>
      DRACO uses fixed benchmark assets. Prepare them once before the first local run so the Engine
      does not download benchmark data while it is evaluating:
    </p>

    <CodeBlock :code="prepareDraco" language="bash" />

    <h4>Start the Engine</h4>

    <p>
      <code>screamingface up</code> starts the local Engine on
      <code>http://127.0.0.1:9108</code>. It also starts the local provider gateway that holds your
      keys.
    </p>

    <CodeBlock :code="engineUp" language="bash" />

    <h4>Check or stop it</h4>

    <p>Use the same command group to inspect or stop the local runtime:</p>

    <CodeBlock :code="engineStatus" language="bash" />

    <CodeBlock :code="engineDown" language="bash" />

    <h4>Point the client at it</h4>

    <div class="not-prose">
      <NbCell :count="1" :code="localPoint" />
    </div>

    <p>No login step: a local engine advertises no Cloudflare Access.</p>

    <h4>Web search for your own Engine</h4>

    <p>
      DRACO is a research benchmark, so some model calls need web search. If the provider routes you
      are using already include their own web-search tool, the Engine can use that. If they do not,
      give the Engine a Tavily key so it has a search backend to call:
    </p>

    <CodeBlock :code="tavily" language="bash" />

    <p>
      Put the key in the environment where <code>screamingface up</code> runs, or in the local
      Engine environment file if you use one. This is separate from model-provider credentials such
      as OpenRouter or Anthropic. Those keys pay for model calls; Tavily gives the Engine a web
      search tool when the chosen provider cannot do search itself.
    </p>

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

    <Collapsible title="The Engine is not reachable">
      <p>
        Run <code>screamingface status</code>. If it is stopped, start it with
        <code>screamingface up</code>. If it reports an unhealthy process, stop it with
        <code>screamingface down</code> and start it again.
      </p>
    </Collapsible>

    <Collapsible title="Do I need Tavily?">
      <p>
        Only if your chosen providers do not offer web search for the routes you are using. DRACO
        can ask models to do research. A route with native web search can handle that itself; a plain
        text-only route needs the Engine to call a separate search provider. Tavily fills that role.
      </p>
      <p>
        Hosted engines may already have search configured by the operator. For your own Engine, put
        <code>TAVILY_API_KEY</code> in the environment before <code>screamingface up</code> when you
        need that fallback.
      </p>
    </Collapsible>

    <Collapsible title="Do I have to run my own engine?">
      <p>
        No. Option B points at a hosted engine and skips the local setup entirely. Option A exists
        for people who want the whole stack on their own machine.
      </p>
    </Collapsible>
  </DocLayout>
</template>
