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
[(b.id, b.case_count) for b in client.benchmarks.list()]`
const listRunOut = `[('draco', 100), ('ifeval', 541)]`

const casesSig = `Benchmark.cases(limit: int = 50, offset: int = 0)`

const casesRun = `ifeval = client.benchmarks.get("ifeval")
ifeval.cases(limit=3)`
const casesRunOut = `Cases(3 of 541, offset=0)`

const caseRun = `case = ifeval.cases(limit=1)[0]
case.id, case.input[:60]`
const caseRunOut = `(1, 'Write a 300+ word summary of the wikipedia page "https://en.')`

const modelsRun = `client.models.list()[0]`
const modelsRunOut = `ModelInfo(id='anthropic/claude-opus-4-8', provider='anthropic')`
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
      covers <code>Benchmark</code> itself, alongside <code>CaseInfo</code> for a single case inside
      it, <code>BenchmarkInfo</code> for the compact identity a report keeps of it, and
      <code>ModelInfo</code> for the model routes the Engine can run it against. See the
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
      size, and access to its public cases. <code>client.benchmarks.get(id)</code> returns a single
      benchmark and <code>client.benchmarks.list()</code> returns every benchmark the Engine offers.
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
            Stable identifier, such as <code>ifeval</code>. This is what you pass as
            <code>benchmark=</code> when evaluating.
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

    <h3>cases()</h3>

    <CodeBlock :code="casesSig" language="python" />

    <p>
      This method fetches one page of the benchmark's public cases from the Engine and returns them
      as a sequence of <code>CaseInfo</code> values supporting indexing, slicing, iteration and
      <code>len()</code>. Within a notebook the sequence renders as a table, and as a searchable
      table where the <code>notebook</code> extra is installed.
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
          <td><code>limit</code></td>
          <td><code>int</code></td>
          <td>How many cases to fetch. Defaults to 50.</td>
        </tr>
        <tr>
          <td><code>offset</code></td>
          <td><code>int</code></td>
          <td>How many cases to skip first. Defaults to 0.</td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="2" :code="casesRun"><NbTextOut :text="casesRunOut" /></NbCell>
    </div>

    <p>
      This is a live call, so it raises <code>PlanningError</code> when the Engine cannot serve the
      benchmark's case data.
    </p>

    <h2>CaseInfo</h2>

    <p>
      A <code>CaseInfo</code> is one public case from a benchmark, carrying its identifier and the
      exact text a candidate receives. Nothing further crosses the Engine boundary: grading criteria
      and rubrics remain on the Engine, so a case's answer key cannot be read through this value.
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
          <td><code>int</code></td>
          <td>Position within the benchmark, counting from 1.</td>
        </tr>
        <tr>
          <td><code>input</code></td>
          <td><code>str</code></td>
          <td>The prompt text for this case.</td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="3" :code="caseRun"><NbTextOut :text="caseRunOut" /></NbCell>
    </div>

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
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="4" :code="modelsRun"><NbTextOut :text="modelsRunOut" /></NbCell>
    </div>

    <h2>Validation</h2>

    <p>
      All four types validate their arguments on construction, so a malformed value cannot exist.
      Blank strings raise <code>ValueError</code>, non-strings raise <code>TypeError</code>, and the
      integer fields reject zero and negative values, which is why <code>case_count</code> and a
      case <code>id</code> are always positive:
    </p>

    <CodeBlock
      code="ValueError: Case id must be a positive integer
ValueError: Case input must be a non-empty string
ValueError: Benchmark case_count must be a positive integer
ValueError: Model id must be a non-empty string"
      language="text"
    />
  </DocLayout>
</template>
