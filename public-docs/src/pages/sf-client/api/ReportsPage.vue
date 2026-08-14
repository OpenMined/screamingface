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

const runIt = `import screamingface as sf

client = sf.Client()
report = client.evaluate(
    sf.Model("openrouter/anthropic/claude-haiku-4.5"),
    benchmark="ifeval",
    limit=1,
)
report`
const runItOut = `Report(benchmark='ifeval', candidates=['claude-haiku-4.5'], ok=True)`

const summary = `report.ok, report.case_count, report.duration_ms`
const summaryOut = `(True, 1, 5248)`

const usage = `report.usage`
const usageOut = `Usage(input_tokens=103, output_tokens=398, cache_read_tokens=0, cache_creation_tokens=0, reasoning_tokens=0, cost_usd=Decimal('0'))`

const only = `candidate = report.candidates.only
candidate.name, candidate.kind, candidate.score, candidate.coverage`
const onlyOut = `('claude-haiku-4.5', 'model', 1.0, 1.0)`

const byName = `report.candidates["claude-haiku-4.5"] is candidate`
const byNameOut = `True`

const metrics = `dict(candidate.metrics)`
const metricsOut = `{'inst_level_strict_accuracy': 1.0, 'prompt_level_loose_accuracy': 1.0, 'inst_level_loose_accuracy': 1.0, 'pass_rate': 1.0}`

const cases = `case = candidate.cases[0]
case.status, case.grade.score, case.output[:40]`
const casesOut = `('scored', 1.0, 'Raymond III, Count of Tripoli (c. 1140 –')`

const ops = `candidate.operations`
const opsOut = `(OperationInfo(id='op_model_1', kind='model', label='claude-haiku-4.5 answer', depends_on=()),)`

const dict = `sorted(report.to_dict())`
const dictOut = `['benchmark', 'candidates', 'completed_at', 'schema', 'started_at', 'usage']`

const bench = `report.benchmark`
const benchOut = `BenchmarkInfo(id='ifeval', revision='047f1de449639c61', case_count=541)`
</script>

<template>
  <DocLayout
    title="Reports"
    description="Report and everything it carries."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <code>Report</code> is what an evaluation returns, and it is the only thing worth keeping:
      it carries the scores, what was spent, what failed, and the exact expression that ran. This
      page covers <code>Report</code> itself, alongside <code>CandidateResult</code> for one
      candidate's outcome, <code>MemberResult</code> for one member of a fusion,
      <code>OperationInfo</code> for a step that ran, <code>Usage</code> for token and cost
      accounting, and <code>Failure</code> for anything that went wrong. See the
      <RouterLink to="/sf-client/guides/running-an-evaluation">evaluation guide</RouterLink> for
      running one.
    </p>

    <div class="not-prose">
      <NbCell :count="1" :code="runIt"><NbTextOut :text="runItOut" /></NbCell>
    </div>

    <p>
      Every example below reads from that report. The six types nest: a <code>Report</code> holds
      <code>CandidateResult</code> values, each of which may hold <code>MemberResult</code> values,
      while <code>OperationInfo</code>, <code>Usage</code> and <code>Failure</code> appear at more
      than one level.
    </p>

    <h2>Report</h2>

    <p>
      A <code>Report</code> represents one evaluation. Its constructor is public, but in normal use
      a <RouterLink to="/sf-client/api/clients">Client</RouterLink> returns it and it is never
      constructed directly.
    </p>

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
          <td><code>benchmark</code></td>
          <td><code>BenchmarkInfo</code></td>
          <td>Which benchmark, at which revision, this ran against.</td>
        </tr>
        <tr>
          <td><code>case_count</code></td>
          <td><code>int</code></td>
          <td>How many cases this run actually covered.</td>
        </tr>
        <tr>
          <td><code>candidates</code></td>
          <td>sequence of <code>CandidateResult</code></td>
          <td>One entry per candidate you evaluated, in the order you passed them.</td>
        </tr>
        <tr>
          <td><code>ok</code></td>
          <td><code>bool</code></td>
          <td>
            <code>True</code> when nothing failed anywhere in the run, at candidate or member level.
          </td>
        </tr>
        <tr>
          <td><code>failures</code></td>
          <td><code>tuple[Failure, ...]</code></td>
          <td>Every failure from every candidate and every member, flattened into one tuple.</td>
        </tr>
        <tr>
          <td><code>usage</code></td>
          <td><code>Usage</code></td>
          <td>The whole run's accounting, summed across candidates.</td>
        </tr>
        <tr>
          <td><code>started_at</code> / <code>completed_at</code></td>
          <td><code>datetime</code></td>
          <td>Earliest start and latest finish across candidates. Always timezone-aware.</td>
        </tr>
        <tr>
          <td><code>duration_ms</code></td>
          <td><code>int</code></td>
          <td>Wall-clock milliseconds between those two.</td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="2" :code="summary"><NbTextOut :text="summaryOut" /></NbCell>
    </div>

    <Note>
      <code>report.case_count</code> and <code>report.benchmark.case_count</code> are different
      numbers. The first is what this run covered; the second is the benchmark's full size.
    </Note>

    <div class="not-prose">
      <NbCell :count="3" :code="bench"><NbTextOut :text="benchOut" /></NbCell>
    </div>

    <p>
      Each protocol variant is a benchmark id of its own, so <code>ifeval</code> and
      <code>ifeval/self-corrective</code> pin different revisions. Two reports are only comparable
      when both the id and the revision match.
    </p>

    <h3>candidates</h3>

    <p>
      <code>report.candidates</code> is a read-only sequence supporting iteration, positional
      indexing and slicing. It also indexes by candidate name, and offers <code>.only</code> for the
      common case of a single candidate.
    </p>

    <div class="not-prose">
      <NbCell :count="4" :code="only"><NbTextOut :text="onlyOut" /></NbCell>
      <NbCell :count="5" :code="byName"><NbTextOut :text="byNameOut" /></NbCell>
    </div>

    <p>
      <code>.only</code> raises <code>ValueError</code> when the report holds more than one
      candidate, and indexing by an unknown name raises <code>KeyError</code>. Candidate names are
      unique within a report.
    </p>

    <h3>Serialisation</h3>

    <p>
      <code>to_dict()</code> returns a plain JSON-compatible dictionary and
      <code>to_json()</code> returns it as a compact string. Both carry a <code>schema</code> field,
      <code>screamingface.report.v1</code>, so a consumer can tell what it is reading.
      <code>export(path="report.json")</code> writes that same document to disk, creating parent
      directories and replacing an existing file, and returns the path it wrote.
    </p>

    <div class="not-prose">
      <NbCell :count="6" :code="dict"><NbTextOut :text="dictOut" /></NbCell>
    </div>

    <h2>CandidateResult</h2>

    <p>
      A <code>CandidateResult</code> is one candidate's outcome. A higher <code>score</code> is
      always better, whatever the benchmark measures.
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
          <td>The recipe's name, unique within the report.</td>
        </tr>
        <tr>
          <td><code>kind</code></td>
          <td><code>str</code></td>
          <td>One of <code>model</code>, <code>fusion</code> or <code>pipeline</code>.</td>
        </tr>
        <tr>
          <td><code>score</code></td>
          <td><code>float&nbsp;|&nbsp;None</code></td>
          <td>
            The headline number, or <code>None</code> when the candidate failed or was not scored.
          </td>
        </tr>
        <tr>
          <td><code>coverage</code></td>
          <td><code>float</code></td>
          <td>
            How much of the selected case set the score was computed from, between 0 and 1. Below
            <code>1.0</code> the Engine excluded ungraded cases and the score is a partial result
            over the rest.
          </td>
        </tr>
        <tr>
          <td><code>metrics</code></td>
          <td><code>Mapping[str, float]</code></td>
          <td>
            The benchmark's individual measures. Empty when <code>score</code> is <code>None</code>:
            an unscored candidate cannot carry metrics. Never contains a <code>coverage</code> key,
            which is the field above instead.
          </td>
        </tr>
        <tr>
          <td><code>benchmark</code></td>
          <td><code>BenchmarkInfo</code></td>
          <td>
            The benchmark identity this candidate ran against, pinned to its revision. The report
            carries the same value.
          </td>
        </tr>
        <tr>
          <td><code>cases</code></td>
          <td>sequence of <code>CaseResult</code></td>
          <td>
            One entry per selected case, carrying its status, the prompt, the answer, and the grade.
          </td>
        </tr>
        <tr>
          <td><code>url4</code></td>
          <td><code>Url4</code></td>
          <td>
            The complete expression that executed, as a <code>str</code> subclass whose
            <code>to_python()</code> returns editable client code. See the
            <RouterLink to="/sf-client/guides/reproduce-and-share">url4 guide</RouterLink>.
          </td>
        </tr>
        <tr>
          <td><code>models</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>Every distinct model route this candidate used. Unique, and never empty.</td>
        </tr>
        <tr>
          <td><code>operations</code></td>
          <td><code>tuple[OperationInfo, ...]</code></td>
          <td>The steps that ran, as an acyclic graph. Never empty.</td>
        </tr>
        <tr>
          <td><code>members</code></td>
          <td><code>tuple[MemberResult, ...]</code></td>
          <td>
            Direct members, for a fusion. Always empty for a <code>model</code> or
            <code>pipeline</code> candidate, and at least one entry for a fusion.
          </td>
        </tr>
        <tr>
          <td><code>failures</code></td>
          <td><code>tuple[Failure, ...]</code></td>
          <td>
            This candidate's own failures. A scored candidate can carry them: the run finished with
            warnings worth reading. None of them names a case, since a candidate-level failure is
            never case-specific.
          </td>
        </tr>
        <tr>
          <td><code>usage</code></td>
          <td><code>Usage</code></td>
          <td>This candidate's accounting.</td>
        </tr>
        <tr>
          <td><code>run_id</code></td>
          <td><code>str</code></td>
          <td>Engine-assigned identifier for this candidate's execution.</td>
        </tr>
        <tr>
          <td><code>started_at</code> / <code>completed_at</code> / <code>duration_ms</code></td>
          <td><code>datetime</code> / <code>int</code></td>
          <td>When it ran and for how long.</td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="7" :code="metrics"><NbTextOut :text="metricsOut" /></NbCell>
    </div>

    <p>
      <code>score</code> and <code>coverage</code> together describe four outcomes, and the notebook
      card labels each one: a score at full coverage and no failures is complete; a score with
      failures completed with warnings; a score at coverage below <code>1.0</code> is partial; and
      no score at all means no aggregate was available.
    </p>

    <h3>cases</h3>

    <p>
      <code>candidate.cases</code> is a read-only sequence of <code>CaseResult</code> values, one
      per selected case. Each carries a <code>status</code> of <code>scored</code>,
      <code>refused</code> or <code>failed</code>, the case <code>input</code>, the candidate's
      <code>output</code>, and a <code>CaseGrade</code> holding the individual checks behind the
      score. A refused case is still graded, so a provider refusal is measured rather than dropped.
    </p>

    <div class="not-prose">
      <NbCell :count="8" :code="cases"><NbTextOut :text="casesOut" /></NbCell>
    </div>

    <h2>MemberResult</h2>

    <p>
      A <code>MemberResult</code> is one direct member of a fusion, held as a compact view: enough
      to see what the member cost and whether it failed, without repeating the full candidate
      structure. Members carry no score, because only the fusion's final answer is graded.
    </p>

    <p>
      Its runtime fields are <code>None</code> until the Engine attributes work to the member's
      operation id. That is a different statement from an empty value: <code>None</code> means the
      attribution was unavailable, while an empty tuple means it arrived and reported nothing.
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
          <td>
            The member recipe's display name. Two siblings can share one, for instance the same
            model reached through two providers, so identity is <code>operation_id</code> rather
            than this.
          </td>
        </tr>
        <tr>
          <td><code>kind</code></td>
          <td><code>str</code></td>
          <td>One of <code>model</code>, <code>fusion</code> or <code>pipeline</code>.</td>
        </tr>
        <tr>
          <td><code>models</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>The routes this member used.</td>
        </tr>
        <tr>
          <td><code>operation_id</code></td>
          <td><code>str</code></td>
          <td>Links this member to an entry in the candidate's <code>operations</code>.</td>
        </tr>
        <tr>
          <td><code>failures</code></td>
          <td><code>tuple[Failure, ...]&nbsp;|&nbsp;None</code></td>
          <td>
            This member's failures, which also appear in <code>report.failures</code>.
            <code>None</code> when the Engine attributed nothing to this member.
          </td>
        </tr>
        <tr>
          <td><code>duration_ms</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>How long the member took, when the Engine reported it.</td>
        </tr>
        <tr>
          <td><code>usage</code></td>
          <td><code>Usage&nbsp;|&nbsp;None</code></td>
          <td>This member's accounting, or <code>None</code> when it was not attributed.</td>
        </tr>
      </tbody>
    </table>

    <h2>OperationInfo</h2>

    <p>
      An <code>OperationInfo</code> is one step in a candidate's compiled graph. Reading
      <code>operations</code> shows what actually ran and in what order, which is how a fusion's
      members can be seen executing before its synthesis.
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
          <td>Unique within the candidate. This is what <code>depends_on</code> refers to.</td>
        </tr>
        <tr>
          <td><code>kind</code></td>
          <td><code>str</code></td>
          <td>What sort of step it was, for example <code>model</code>.</td>
        </tr>
        <tr>
          <td><code>label</code></td>
          <td><code>str</code></td>
          <td>Human-readable description, such as <code>claude-haiku-4.5 answer</code>.</td>
        </tr>
        <tr>
          <td><code>depends_on</code></td>
          <td><code>tuple[str, ...]</code></td>
          <td>
            Ids of the steps that had to finish first. Empty for a step with no prerequisites.
          </td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="9" :code="ops"><NbTextOut :text="opsOut" /></NbCell>
    </div>

    <p>
      The operations of a candidate form an acyclic graph: ids are unique, every dependency names a
      step that exists, and no step can depend on itself.
    </p>

    <h2>Usage</h2>

    <p>
      A <code>Usage</code> holds the token and cost accounting for one subtree of a run. Every field
      is optional, because a provider that does not report a number leaves it as
      <code>None</code> rather than guessing zero.
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
          <td><code>input_tokens</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>Tokens sent.</td>
        </tr>
        <tr>
          <td><code>output_tokens</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>Tokens generated.</td>
        </tr>
        <tr>
          <td><code>cache_read_tokens</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>Tokens served from a provider cache.</td>
        </tr>
        <tr>
          <td><code>cache_creation_tokens</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>Tokens written into a provider cache.</td>
        </tr>
        <tr>
          <td><code>reasoning_tokens</code></td>
          <td><code>int&nbsp;|&nbsp;None</code></td>
          <td>Tokens spent on reasoning, where the provider separates them.</td>
        </tr>
        <tr>
          <td><code>cost_usd</code></td>
          <td><code>Decimal&nbsp;|&nbsp;None</code></td>
          <td>
            Money, as a <code>Decimal</code> so it never loses precision. Accepts a string or a
            <code>Decimal</code> on construction.
          </td>
        </tr>
      </tbody>
    </table>

    <div class="not-prose">
      <NbCell :count="10" :code="usage"><NbTextOut :text="usageOut" /></NbCell>
    </div>

    <p>
      Summing follows a strict rule: <code>report.usage</code> adds a field across candidates only
      when <em>every</em> candidate reported it. If one candidate leaves <code>cost_usd</code> as
      <code>None</code>, the report's <code>cost_usd</code> is <code>None</code> too, rather than a
      total that silently omits part of the run.
    </p>

    <p>
      <code>to_dict()</code> drops fields that are <code>None</code> and renders
      <code>cost_usd</code> as a string.
    </p>

    <h2>Failure</h2>

    <p>
      A <code>Failure</code> is one typed failure held inside an otherwise valid report. A report
      with failures is still a report, so what succeeded can be read alongside what did not.
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
          <td><code>stage</code></td>
          <td><code>str</code></td>
          <td>
            Where it happened: <code>candidate</code>, <code>grading</code> or
            <code>aggregation</code>.
          </td>
        </tr>
        <tr>
          <td><code>code</code></td>
          <td><code>str</code></td>
          <td>
            Stable machine-readable identifier in lowercase snake_case, such as
            <code>provider_timeout</code>. Match on this rather than on the message.
          </td>
        </tr>
        <tr>
          <td><code>message</code></td>
          <td><code>str</code></td>
          <td>Human-readable explanation. Not stable across versions.</td>
        </tr>
        <tr>
          <td><code>retryable</code></td>
          <td><code>bool&nbsp;|&nbsp;None</code></td>
          <td>
            Whether running the same thing again could plausibly succeed, or <code>None</code> when
            the Engine did not say.
          </td>
        </tr>
        <tr>
          <td><code>operation_id</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>
            Which step failed, matching an <code>OperationInfo.id</code>. <code>None</code> for a
            failure no single step owns.
          </td>
        </tr>
        <tr>
          <td><code>case_id</code></td>
          <td><code>str&nbsp;|&nbsp;None</code></td>
          <td>Which case failed, when the failure was specific to one.</td>
        </tr>
        <tr>
          <td><code>metadata</code></td>
          <td><code>Mapping[str, object]</code></td>
          <td>
            Whatever else the Engine attached to this failure. Empty when it attached nothing.
          </td>
        </tr>
      </tbody>
    </table>

    <p>A failure reads like this:</p>

    <CodeBlock
      code="Failure(stage='candidate', code='provider_timeout', message='Upstream timed out', retryable=True, operation_id='op-1', case_id='7')"
      language="python"
    />
  </DocLayout>
</template>
