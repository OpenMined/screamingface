<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import NbCell from '@/components/nb/NbCell.vue'
import NbTextOut from '@/components/nb/NbTextOut.vue'
import {
  sfClientNavigation as navigation,
  sfClientVersion as version,
} from '@/navigation/sf-client'

const metrics = `dict(candidate.metrics)`
const metricsOut = `{'inst_level_strict_accuracy': 1.0, 'prompt_level_loose_accuracy': 1.0, 'inst_level_loose_accuracy': 1.0, 'pass_rate': 1.0}`

const cases = `case = candidate.cases[0]
case.status, case.grade.score, case.output[:40]`
const casesOut = `('scored', 1.0, 'Raymond III, Count of Tripoli (c. 1140 –')`

const ops = `candidate.operations`
const opsOut = `(OperationInfo(id='op_model_1', kind='model', label='claude-haiku-4.5 answer', depends_on=()),)`
</script>

<template>
  <DocLayout
    title="CandidateResult"
    description="One candidate's outcome, and the values it carries: MemberResult, OperationInfo, CaseResult."
    :navigation="navigation"
    :version="version"
  >
    <p>
      A <code>CandidateResult</code> is one candidate's outcome inside a
      <RouterLink to="/sf-client/api/reports">Report</RouterLink>. The candidate is whatever
      <RouterLink to="/sf-client/api/recipes">recipe</RouterLink> you evaluated — a Model, a Fusion,
      or a Pipeline. This page covers <code>CandidateResult</code> itself, alongside
      <code>MemberResult</code> for one member of a fusion, <code>OperationInfo</code> for a step
      that ran, and <code>CaseResult</code> for one graded case. Every example below reads from a
      <code>candidate</code> pulled off a report with <code>report.candidates.only</code>.
    </p>

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
      members can be seen executing before its synthesis. See the
      <RouterLink to="/sf-client/guides/reproduce-and-share">url4 guide</RouterLink> for reading the
      same plan as a url4 expression.
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
  </DocLayout>
</template>
