<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const modelsRun = `import screamingface as sf

client = sf.Client()
client.models.list()[0]`
const modelsRunOut = `ModelInfo('anthropic/claude-opus-4-8', provider='anthropic', parameters=9, tools=2)`

const detailsRun = `client.models.get("anthropic/claude-opus-4-8")`
const detailsRunOut = `ModelDetails('anthropic/claude-opus-4-8', provider='anthropic', scope='chat', parameters=9, tools=2, transport=3)`

const modelSig = `sf.Model(
    model: str,
    *,
    name: str | None = None,
    prompt: str | None = None,
    params: Mapping[str, str | int | float | bool] | None = None,
)`
</script>

<template>
  <DocLayout
    title="Models"
    description="The Model recipe class you build, and the discovery types routes come back as: ModelInfo, ModelDetails, and their fields."
    :navigation="navigation"
    :version="version"
  >
    <p>
      This page documents the <code>Model</code> recipe class you build, and the read-only
      <strong>discovery types</strong> the Engine returns when you inspect what a route supports.
    </p>

    <h2 id="model">Model</h2>

    <p>
      A <code>Model</code> is a single model route answering on its own — the simplest recipe, and
      the building block every <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink> and
      <RouterLink to="/sf-client/guides/pipelines">Pipeline</RouterLink> is made of. See the
      <RouterLink to="/sf-client/guides/models">Models guide</RouterLink> for help picking a route.
    </p>

    <CodeBlock :code="modelSig" language="python" />

    <h3>Parameters</h3>

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
          <td><code>model</code></td>
          <td><code>str</code></td>
          <td>
            The provider route, like <code>openrouter/openai/gpt-5.5</code>. Required, positional.
          </td>
        </tr>
        <tr>
          <td><code>name</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Label that shows up in reports and on the leaderboard. Defaults to everything after the
            last <code>/</code> in the route, so <code>openrouter/openai/gpt-5.5</code> becomes
            <code>gpt-5.5</code>. Setting an explicit name also marks this Model as an independent
            sample.
          </td>
        </tr>
        <tr>
          <td><code>prompt</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            The instruction given to the model alongside the case. Leave it out and the SDK uses its
            own default prompt (not the benchmark's).
          </td>
        </tr>
        <tr>
          <td><code>params</code></td>
          <td><code>Mapping&nbsp;|&nbsp;None</code></td>
          <td>
            Generation overrides like <code>temperature</code>. Values must be <code>str</code>,
            <code>int</code>, <code>float</code>, or <code>bool</code> (floats have to be finite).
            Only the params you set get sent, since the SDK adds no defaults. Transport, tool, and
            benchmark-protocol names (like <code>model</code>, <code>messages</code>,
            <code>tools</code>, <code>web_search</code>) are reserved and will be rejected.
          </td>
        </tr>
      </tbody>
    </table>

    <h3>Attributes</h3>

    <p>
      <code>model</code>, <code>name</code>, and <code>prompt</code> give you back what you passed
      in. <code>params</code> returns a <code>mappingproxy</code>, so you can't mutate the overrides
      after construction.
    </p>

    <h3>Raises</h3>

    <table>
      <thead>
        <tr>
          <th>When</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>The route or name is not a string</td>
          <td><code>TypeError</code></td>
        </tr>
        <tr>
          <td>The route or name is empty or only whitespace</td>
          <td><code>ValueError: model route must not be empty</code></td>
        </tr>
        <tr>
          <td>The route or name contains control characters</td>
          <td><code>ValueError</code></td>
        </tr>
        <tr>
          <td>A <code>params</code> value is not a scalar, or a float is not finite</td>
          <td><code>TypeError</code> / <code>ValueError</code></td>
        </tr>
        <tr>
          <td>A <code>params</code> name is reserved, or a name or value cannot be encoded</td>
          <td><code>ValueError</code></td>
        </tr>
      </tbody>
    </table>

    <h2>Discovery types</h2>

    <p>
      These are the read-only values model discovery returns.
      <code>client.models.list()</code> hands back a <code>ModelInfo</code> for every route the
      configured Engine can currently reach, and <code>client.models.get(id)</code> returns the
      fuller <code>ModelDetails</code> profile for one route. Consulting them before naming a route
      in a <a href="#model">Model</a> is worthwhile: a route the Engine does not carry raises a
      <code>PlanningError</code> at evaluation time rather than at construction time.
    </p>

    <p>
      Everything here is read-only and assigning to a field raises
      <code>FrozenInstanceError: cannot assign to field 'provider'</code>. These values also never
      refresh themselves and the Client needs to be called again when current data is desired.
    </p>

    <h2>ModelInfo</h2>

    <p>
      A <code>ModelInfo</code> is one model route the configured Engine can currently reach.
      <code>client.models.list()</code> returns every addressable route, and consulting it before
      naming a route in a <a href="#model">Model</a> is worthwhile: a route the Engine does not
      carry raises a <code>PlanningError</code> at evaluation time rather than at construction time.
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
          <td><code>id</code></td>
          <td><code>str</code></td>
          <td>The route, which is what you pass to <code>sf.Model()</code>.</td>
        </tr>
        <tr>
          <td><code>provider</code></td>
          <td><code>str</code></td>
          <td>Which provider serves the route.</td>
        </tr>
        <tr>
          <td><code>supported_parameters</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>
            Which request parameters this route accepts, such as <code>temperature</code>. Passing
            one it does not accept fails before the run.
          </td>
        </tr>
        <tr>
          <td><code>supported_tools</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>Which tools it can use, such as <code>web_search</code>.</td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="1" :code="modelsRun"><NbTextOut :text="modelsRunOut" /></NbCell>
    </div>

    <h2>ModelDetails</h2>

    <p>
      <code>client.models.get(id)</code> returns the fuller <code>ModelDetails</code> profile for
      one route: every parameter with its schema and whether the gateway currently projects it, the
      tool and transport capabilities, and whether the profile is stale or degraded. In a notebook
      it renders as a card.
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
          <td><code>id</code></td>
          <td><code>str</code></td>
          <td>The route, which is what you pass to <code>sf.Model()</code>.</td>
        </tr>
        <tr>
          <td><code>provider</code></td>
          <td><code>str</code></td>
          <td>Which provider serves the route.</td>
        </tr>
        <tr>
          <td><code>scope</code></td>
          <td><code>str</code></td>
          <td>What the route does, such as <code>chat</code>.</td>
        </tr>
        <tr>
          <td><code>parameters</code></td>
          <td><code>Mapping[str, ModelParameter]</code></td>
          <td>Each request parameter the route exposes, keyed by name.</td>
        </tr>
        <tr>
          <td><code>tools</code></td>
          <td><code>Mapping[str, ModelCapability]</code></td>
          <td>Each tool capability, such as <code>web_search</code>, keyed by name.</td>
        </tr>
        <tr>
          <td><code>transport</code></td>
          <td><code>Mapping[str, ModelCapability]</code></td>
          <td>Each transport capability, keyed by name.</td>
        </tr>
      </tbody>
    </table>

    <p>
      Its repr shows counts rather than the full mappings, so the shape stays legible at a glance:
    </p>

    <div class="not-prose">
      <NbCell :count="2" :code="detailsRun"><NbTextOut :text="detailsRunOut" /></NbCell>
    </div>

    <h2>ModelParameter</h2>

    <p>
      A <code>ModelParameter</code> describes one request parameter a route exposes: what it is
      called, how the gateway treats it, and where the description came from. The values in
      <code>ModelDetails.parameters</code> are these.
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
          <td><code>name</code></td>
          <td><code>str</code></td>
          <td>The parameter name, such as <code>temperature</code>.</td>
        </tr>
        <tr>
          <td><code>request_path</code></td>
          <td><code>str</code></td>
          <td>Where the value lands in the request the gateway sends upstream.</td>
        </tr>
        <tr>
          <td><code>schema</code></td>
          <td><code>ModelParameterSchema&nbsp;|&nbsp;None</code></td>
          <td>
            The value's type and bounds, when the provider published one. <code>None</code> when no
            schema is known.
          </td>
        </tr>
        <tr>
          <td><code>provider_support</code></td>
          <td><code>str</code></td>
          <td>Whether the provider supports the parameter.</td>
        </tr>
        <tr>
          <td><code>provider_source</code></td>
          <td><code>str</code></td>
          <td>Where the provider description came from.</td>
        </tr>
        <tr>
          <td><code>provider_stale</code></td>
          <td><code>bool</code></td>
          <td>Whether the provider description is out of date.</td>
        </tr>
        <tr>
          <td><code>provider_deprecated</code></td>
          <td><code>bool</code></td>
          <td>Whether the provider has deprecated the parameter.</td>
        </tr>
        <tr>
          <td><code>gateway_status</code></td>
          <td><code>str</code></td>
          <td>
            Whether the gateway forwards the parameter: <code>"enabled"</code> or
            <code>"disabled"</code>.
          </td>
        </tr>
        <tr>
          <td><code>gateway_projection</code></td>
          <td><code>str</code></td>
          <td>How the gateway projects the value onto the request it sends.</td>
        </tr>
        <tr>
          <td><code>gateway_reason</code></td>
          <td><code>str</code></td>
          <td>Why the gateway is in that state, when it has a reason to give.</td>
        </tr>
        <tr>
          <td><code>cache_behavior</code></td>
          <td><code>str</code></td>
          <td>How this parameter participates in caching.</td>
        </tr>
        <tr>
          <td><code>applicable_auth_modes</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>Which authentication modes the parameter applies under.</td>
        </tr>
      </tbody>
    </table>

    <p>
      It also carries one read-only property, <code>enabled</code>, which is <code>True</code> when
      <code>gateway_status == "enabled"</code>.
    </p>

    <h2>ModelCapability</h2>

    <p>
      A <code>ModelCapability</code> describes one tool or transport capability. The values in
      <code>ModelDetails.tools</code> and <code>ModelDetails.transport</code> are these.
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
          <td><code>provider_support</code></td>
          <td><code>str</code></td>
          <td>Whether the provider supports the capability.</td>
        </tr>
        <tr>
          <td><code>gateway_status</code></td>
          <td><code>str</code></td>
          <td>
            Whether the gateway exposes the capability: <code>"enabled"</code> or
            <code>"disabled"</code>.
          </td>
        </tr>
        <tr>
          <td><code>reason</code></td>
          <td><code>str</code></td>
          <td>Why the capability is in that state, when there is a reason to give.</td>
        </tr>
      </tbody>
    </table>
  </DocLayout>
</template>
