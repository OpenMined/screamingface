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

const listRun = `import screamingface as sf

client = sf.Client()
[(b.id, b.variant, b.case_count) for b in client.benchmarks.list()]`
const listRunOut = `[('draco', 'canonical', 100), ('draco/lite', 'lite', 2), ('ifeval', 'canonical', 541), ('ifeval/self-corrective', 'self-corrective', 541)]`

const modelsRun = `client.models.list()[0]`
const modelsRunOut = `ModelInfo('anthropic/claude-opus-4-8', provider='anthropic', parameters=9, tools=2)`

const detailsRun = `client.models.get("anthropic/claude-opus-4-8")`
const detailsRunOut = `ModelDetails('anthropic/claude-opus-4-8', provider='anthropic', scope='chat', parameters=9, tools=2, transport=3)`
</script>

<template>
  <DocLayout
    title="Benchmarks"
    description="Benchmark and the read-only values discovery returns."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A benchmark is a fixed set of cases, owned by the Engine and pinned by a revision. This page
      covers <code>Benchmark</code> itself, alongside <code>BenchmarkInfo</code> for the compact
      identity a report keeps of it, and <code>ModelInfo</code> for the model routes the Engine can
      run it against. See the
      <RouterLink to="/sf-client/guides/benchmarks">Benchmarks guide</RouterLink> for choosing which
      benchmark to run.
    </p>

    <p>
      A <RouterLink to="/sf-client/api/clients">Client</RouterLink> returns these values which are
      all read-only and assigning to a field raises
      <code>FrozenInstanceError: cannot assign to field 'provider'</code>. They also never refresh
      themselves and the Client needs to be called again when current data is desired.
    </p>

    <h2>Benchmark</h2>

    <p>
      A <code>Benchmark</code> is the Engine's record of one benchmark, carrying its identity, its
      size, and what it measures. <code>client.benchmarks.get(id)</code> returns a single benchmark
      and <code>client.benchmarks.list()</code> returns every benchmark the Engine offers. Protocol
      variants are separate entries with their own ids, so the list holds <code>ifeval</code> beside
      <code>ifeval/self-corrective</code>.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="listRun"><NbTextOut :text="listRunOut" /></NbCell>
    </div>

    <h3>Attributes</h3>

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
          <td>
            Stable identifier, such as <code>ifeval</code> or <code>draco/lite</code>. This is what
            you pass as <code>benchmark=</code> when evaluating.
          </td>
        </tr>
        <tr>
          <td><code>variant</code></td>
          <td><code>str</code></td>
          <td>
            Which protocol of the underlying benchmark this entry runs, such as
            <code>canonical</code>, <code>lite</code> or <code>self-corrective</code>. It names the
            protocol; the <code>id</code> is what selects it.
          </td>
        </tr>
        <tr>
          <td><code>title</code></td>
          <td><code>str</code></td>
          <td>Display name, such as <code>IFEval</code>.</td>
        </tr>
        <tr>
          <td><code>description</code></td>
          <td><code>str</code></td>
          <td>
            Prose describing what the benchmark measures. For benchmarks with more than one protocol
            it also states which method is the default and how the alternatives differ.
          </td>
        </tr>
        <tr>
          <td><code>revision</code></td>
          <td><code>str</code></td>
          <td>
            Opaque content hash of this benchmark's current state. Two reports are only comparable
            when their revisions match.
          </td>
        </tr>
        <tr>
          <td><code>case_count</code></td>
          <td><code>int</code></td>
          <td>How many cases the benchmark holds in total.</td>
        </tr>
      </tbody>
    </table>

    <Note>
      A <code>Benchmark</code> carries no case data. The client cannot page a benchmark's prompts,
      because the cases and their answer keys stay on the Engine. Case text becomes visible after a
      run, through the <code>CaseResult</code> values on
      <RouterLink to="/sf-client/api/reports">CandidateResult.cases</RouterLink>.
    </Note>

    <h2>BenchmarkInfo</h2>

    <p>
      A <code>BenchmarkInfo</code> is the pinned identity of a benchmark as it stood when a run took
      place. It is the value embedded in a
      <RouterLink to="/sf-client/api/reports">Report</RouterLink>, which is why it carries a
      revision but no title or description: its purpose is to make a result reproducible rather than
      to describe the benchmark.
    </p>

    <Note>
      <code>BenchmarkInfo.case_count</code> is the benchmark's full size, not the number of cases a
      run covered. The two differ: after evaluating with <code>limit=1</code>,
      <code>report.case_count</code> is <code>1</code> while
      <code>report.benchmark.case_count</code> remains <code>541</code>.
    </Note>

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
          <td>The benchmark identifier.</td>
        </tr>
        <tr>
          <td><code>revision</code></td>
          <td><code>str</code></td>
          <td>The revision the run was executed against.</td>
        </tr>
        <tr>
          <td><code>case_count</code></td>
          <td><code>int</code></td>
          <td>
            The benchmark's full size. For what the run covered, read
            <code>report.case_count</code>.
          </td>
        </tr>
      </tbody>
    </table>

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
      <NbCell :count="2" :code="modelsRun"><NbTextOut :text="modelsRunOut" /></NbCell>
    </div>

    <p>
      <code>client.models.get(id)</code> returns the fuller <code>ModelDetails</code> profile for
      one route: every parameter with its schema and whether the gateway currently projects it, the
      tool and transport capabilities, and whether the profile is stale or degraded. In a notebook
      it renders as a card.
    </p>

    <div class="not-prose">
      <NbCell :count="3" :code="detailsRun"><NbTextOut :text="detailsRunOut" /></NbCell>
    </div>

    <h2>Validation</h2>

    <p>
      All three types validate their arguments on construction, so a malformed value cannot exist.
      Blank strings raise <code>ValueError</code>, non-strings raise <code>TypeError</code>, and
      <code>case_count</code> rejects zero and negative values:
    </p>

    <CodeBlock
      code="ValueError: Benchmark case_count must be a positive integer
ValueError: Benchmark variant must be a non-empty string
ValueError: Model id must be a non-empty string"
      language="text"
    />
  </DocLayout>
</template>
