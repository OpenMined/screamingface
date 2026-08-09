<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import Note from '@/components/ui/Note.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const clientSig = `sf.Client(*, engine_url: str = "http://127.0.0.1:9108")`

const basic = `import screamingface as sf

client = sf.Client()
client.engine_url, client.closed, client.authenticated`
const basicOut = `('http://127.0.0.1:9108', False, False)`

const evaluateSig = `Client.evaluate(
    candidates: Recipe | Sequence[Recipe],
    *,
    benchmark: str,
    limit: int | None = None,
    method: str | None = None,
    on_event: Callable[[Event], None] | None = None,
    progress: bool | None = None,
) -> Report`

const withBlock = `with sf.Client() as client:
    report = client.evaluate(
        sf.Model("openrouter/anthropic/claude-haiku-4.5"),
        benchmark="ifeval",
        limit=1,
        method="single_pass",
    )`

const closed = `client.close()
client.connections.list()`
const closedOut = `RuntimeError: ScreamingFace Client is closed`

const asyncCode = `import asyncio
import screamingface as sf

async def main():
    async with sf.AsyncClient() as client:
        models = await client.models.list()
        return len(models), client.engine_url

asyncio.run(main())`
const asyncOut = `(29, 'http://127.0.0.1:9108')`

const connection = `client.connections.get("openrouter")`
const connectionOut = `Connection(provider='openrouter', display_name='OpenRouter', auth_methods=('api_key',), status='connected', auth_method='api_key', account_label=None)`

const panel = `client.connect()`
const panelOut = `ConnectionPanel(engine='http://127.0.0.1:9108', openrouter=connected)`
</script>

<template>
  <DocLayout
    title="Clients"
    description="Client, AsyncClient, and provider connections."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <code>Client</code> is the connection to one Engine, and the object that every other page in
      this reference depends on: recipes are passed to it, and benchmarks and reports come back from
      it. This page covers <code>Client</code> itself, alongside <code>AsyncClient</code> for the
      same interface over <code>await</code>, <code>Connection</code> for a provider's state on the
      Engine, and <code>ConnectionPanel</code> for the interactive view that
      <code>connect()</code> returns.
    </p>

    <h2>Client</h2>

    <CodeBlock :code="clientSig" language="python" />

    <p>
      Creating a <code>Client</code> opens no connection and makes no request. The first call that
      needs the Engine is the first one that talks to it.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="basic"><NbTextOut :text="basicOut" /></NbCell>
    </div>

    <Note>
      The default <code>engine_url</code> points at a local Engine on port 9108. For a hosted
      Engine, pass its address, or set <code>SCREAMINGFACE_ENGINE_URL</code> and use the
      module-level functions.
    </Note>

    <h3>Properties</h3>

    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>engine_url</code></td>
          <td><code>str</code></td>
          <td>The Engine origin this Client was built for. Fixed for the Client's life.</td>
        </tr>
        <tr>
          <td><code>closed</code></td>
          <td><code>bool</code></td>
          <td>Whether <code>close()</code> has run.</td>
        </tr>
        <tr>
          <td><code>authenticated</code></td>
          <td><code>bool</code></td>
          <td>Whether this process currently holds hosted caller credentials.</td>
        </tr>
        <tr>
          <td><code>authenticating</code></td>
          <td><code>bool</code></td>
          <td>Whether a login is in flight.</td>
        </tr>
        <tr>
          <td><code>models</code></td>
          <td>catalogue</td>
          <td>
            <code>models.list()</code> returns the
            <RouterLink to="/sf-client/api/benchmarks">ModelInfo</RouterLink> routes this Engine can
            reach.
          </td>
        </tr>
        <tr>
          <td><code>benchmarks</code></td>
          <td>catalogue</td>
          <td>
            <code>benchmarks.list()</code>, <code>benchmarks.get(id)</code> and
            <code>benchmarks.cases(id)</code>.
          </td>
        </tr>
        <tr>
          <td><code>connections</code></td>
          <td>catalogue</td>
          <td><code>connections.list()</code> and <code>connections.get(provider)</code>.</td>
        </tr>
      </tbody>
    </table>

    <h3>evaluate()</h3>

    <CodeBlock :code="evaluateSig" language="python" />

    <p>
      <code>evaluate()</code> runs one or more candidates against a benchmark and returns a
      <RouterLink to="/sf-client/api/reports">Report</RouterLink>. This is the call that costs
      money.
    </p>

    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>candidates</code></td>
          <td><code>Recipe</code> or sequence</td>
          <td>
            One <RouterLink to="/sf-client/api/recipes">recipe</RouterLink> or several. Several
            candidates run independently and share one report.
          </td>
        </tr>
        <tr>
          <td><code>benchmark</code></td>
          <td><code>str</code></td>
          <td>The benchmark id, such as <code>ifeval</code>. Required keyword argument.</td>
        </tr>
        <tr>
          <td><code>limit</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>
            Run only this many cases. <code>None</code> runs the whole benchmark. Use a small limit
            while you are still iterating.
          </td>
        </tr>
        <tr>
          <td><code>method</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Which protocol variant to run, such as ifeval's <code>single_pass</code>.
            <code>None</code> runs the benchmark's default. This changes the pinned revision, so it
            changes what the result is comparable to.
          </td>
        </tr>
        <tr>
          <td><code>on_event</code></td>
          <td>callable</td>
          <td>Called with each lifecycle event as the run proceeds.</td>
        </tr>
        <tr>
          <td><code>progress</code></td>
          <td><code>bool&nbsp;|&nbsp;None</code></td>
          <td>Force the progress display on or off instead of letting it decide.</td>
        </tr>
      </tbody>
    </table>

    <h3>connect() and disconnect()</h3>

    <p>
      <code>connect(provider, api_key=...)</code> stores a provider credential on the Engine and
      returns the resulting <code>Connection</code>. <code>connect()</code> with no arguments
      returns a <code>ConnectionPanel</code> instead. <code>disconnect(provider)</code> removes the
      credential and is safe to call repeatedly.
    </p>

    <p>
      Passing a key requires a secure origin: an <code>https</code> Engine, or a local one over
      <code>http</code>. Supplying <code>api_key</code> without a provider raises
      <code>TypeError</code>; a provider without <code>api_key</code> raises
      <code>ValueError</code>.
    </p>

    <h3>Lifecycle</h3>

    <p>
      <code>close()</code> releases the Client's transports and is idempotent. Using a closed Client
      raises:
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="closed"><NbTextOut :text="closedOut" /></NbCell>
    </div>

    <p>
      A <code>with</code> block closes it automatically, which is the form to prefer in a script:
    </p>

    <CodeBlock :code="withBlock" language="python" />

    <p>
      <code>login(timeout=300.0)</code> and <code>logout()</code> apply to hosted Engines that sit
      behind browser-based access. A local Engine needs neither.
    </p>

    <h2>AsyncClient</h2>

    <p>
      An <code>AsyncClient</code> offers the same interface over <code>await</code> and returns the
      same value types. It suits evaluations that run alongside other asynchronous work.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="asyncCode"><NbTextOut :text="asyncOut" /></NbCell>
    </div>

    <p>Three differences are worth knowing:</p>

    <table>
      <thead>
        <tr>
          <th>Client</th>
          <th>AsyncClient</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>close()</code></td>
          <td><code>await aclose()</code></td>
        </tr>
        <tr>
          <td><code>with</code></td>
          <td><code>async with</code></td>
        </tr>
        <tr>
          <td><code>connect()</code> may open a panel</td>
          <td><code>connect(provider, api_key=...)</code> always requires both</td>
        </tr>
      </tbody>
    </table>

    <p>
      <code>evaluate()</code>, <code>connect()</code>, <code>disconnect()</code>,
      <code>login()</code> and <code>logout()</code> are all awaited. The properties
      (<code>engine_url</code>, <code>closed</code>, <code>authenticated</code>) are not.
    </p>

    <h2>Connection</h2>

    <p>
      A <code>Connection</code> is sanitized provider state as the Engine reports it. It never
      carries the credential itself, so an API key cannot be read back out of one.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="connection"><NbTextOut :text="connectionOut" /></NbCell>
    </div>

    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>provider</code></td>
          <td><code>str</code></td>
          <td>Identifier, such as <code>openrouter</code>.</td>
        </tr>
        <tr>
          <td><code>display_name</code></td>
          <td><code>str</code></td>
          <td>Human-readable name, such as <code>OpenRouter</code>.</td>
        </tr>
        <tr>
          <td><code>auth_methods</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>
            What this provider supports: <code>api_key</code>, <code>oauth</code>, or both. Never
            empty.
          </td>
        </tr>
        <tr>
          <td><code>status</code></td>
          <td><code>str</code></td>
          <td>
            One of <code>not_connected</code>, <code>pending</code>, <code>connected</code>,
            <code>needs_reauth</code> or <code>error</code>.
          </td>
        </tr>
        <tr>
          <td><code>auth_method</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Which method is in use, or <code>None</code> when not connected. Always one of
            <code>auth_methods</code>.
          </td>
        </tr>
        <tr>
          <td><code>account_label</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>Which account, where the provider identifies one.</td>
        </tr>
      </tbody>
    </table>

    <h2>ConnectionPanel</h2>

    <p>
      A <code>ConnectionPanel</code> is what <code>client.connect()</code> returns when called with
      no arguments: a live view of every provider the Engine knows about. Within a notebook it
      renders as an interactive widget, allowing a key to be pasted without placing it in a cell.
      Outside a notebook it remains readable as a value.
    </p>

    <div class="not-prose">
      <NbCell :count="5" :code="panel"><NbTextOut :text="panelOut" /></NbCell>
    </div>

    <table>
      <thead>
        <tr>
          <th>Member</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>engine</code></td>
          <td>The Engine origin this panel is bound to.</td>
        </tr>
        <tr>
          <td><code>connections</code></td>
          <td>The <code>Connection</code> values as of the last refresh.</td>
        </tr>
        <tr>
          <td><code>authenticated</code> / <code>authenticating</code></td>
          <td>Mirror the Client's login state.</td>
        </tr>
        <tr>
          <td><code>refresh()</code></td>
          <td>Re-read connections from the Engine and return them.</td>
        </tr>
        <tr>
          <td><code>widget()</code></td>
          <td>The notebook widget, when you want to place it yourself.</td>
        </tr>
        <tr>
          <td><code>close()</code></td>
          <td>Release the panel's background work. It does not close the Client.</td>
        </tr>
      </tbody>
    </table>

    <p>
      See the <RouterLink to="/sf-client/guides/connections">Connections guide</RouterLink> for
      choosing between the panel and a direct <code>connect()</code> call.
    </p>
  </DocLayout>
</template>
