<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
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
</script>

<template>
  <DocLayout
    title="Models"
    description="The discovery types model routes come back as: ModelInfo, ModelDetails, and their fields."
    :navigation="navigation"
    :version="version"
  >
    <p>
      These are the read-only values model discovery returns.
      <code>client.models.list()</code> hands back a <code>ModelInfo</code> for every route the
      configured Engine can currently reach, and <code>client.models.get(id)</code> returns the
      fuller <code>ModelDetails</code> profile for one route. Consulting them before naming a route
      in a <RouterLink to="/sf-client/api/recipes">Model</RouterLink> is worthwhile: a route the
      Engine does not carry raises a <code>PlanningError</code> at evaluation time rather than at
      construction time.
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
      naming a route in a <RouterLink to="/sf-client/api/recipes">Model</RouterLink> is worthwhile:
      a route the Engine does not carry raises a <code>PlanningError</code> at evaluation time
      rather than at construction time.
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
