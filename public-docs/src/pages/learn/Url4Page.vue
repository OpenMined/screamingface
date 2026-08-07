<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import { learnNavigation as navigation } from '@/navigation/learn'

const GH_TREE = 'https://github.com/OpenMined/screamingface/tree/main'
const GH_BLOB = 'https://github.com/OpenMined/screamingface/blob/main'

const examples = `https://x!summarize                         # fetch a source, then apply an intent
(article=https://x)!use $article            # bind a source to a name, reference it as $article
(https://x, https://y)!first=$1 second=$2    # two parallel sources, referenced by position
claude:0.6:/claude(x)!go                     # a named source with a weight, calling another expression
(a, b)*('row: $item')!'per row'              # iterate a body over a collection, then reduce`

const roundtrip = `import url4

node = url4.build("(https://a, https://b)!'summarize both'")
url4.render(node)   # -> "(https://a, https://b)!'summarize both'"   (lossless round-trip)`
</script>

<template>
  <DocLayout
    title="url4"
    description="The open, lowercase expression that describes — and reproduces — a whole AI system in one line."
    :navigation="navigation"
  >
    <p>
      <strong>url4</strong> is a small grammar for saying <em>given these sources, do this</em>. A
      url4 string names some sources and an intent, and compiles to a typed graph of operations that
      fans out across models and reduces to a single answer. It is the contract the
      <RouterLink to="/learn/engine">Engine</RouterLink> resolves and the artifact the
      <RouterLink to="/sf-client">Client</RouterLink> shares — the whole reason a result can be
      trusted is that its url4 can be rerun by anyone.
    </p>

    <p>Like <code>http</code>, it is always written lowercase.</p>

    <h2>The shape</h2>

    <p>
      Sources go in parentheses; the intent comes after the <code>!</code>. The simplest expression
      is a single source and an intent:
    </p>

    <CodeBlock code="(a=https://x, tone='formal')!'Summarize $a in a $tone tone'" language="text" />

    <p>
      Sources can be named (<code>a=…</code>), referenced by name (<code>$a</code>) or position
      (<code>$1</code>), weighted and budgeted, iterated over, and expanded. A source can itself be
      another url4 expression, so an expression composes recursively into an arbitrary graph. A few
      real shapes, drawn from the grammar's own test suite:
    </p>

    <CodeBlock :code="examples" language="text" />

    <h2>How it runs</h2>

    <p>
      A url4 string is parsed by a recursive-descent parser into a frozen syntax tree, then lowered
      to a <strong>typed DAG</strong>. Independent nodes run in parallel; named and positional
      references become the edges between them; iteration compiles to map nodes and a reduce. The
      graph is demand-driven, so only the nodes a result depends on are ever scheduled.
    </p>

    <p>
      The text form and the tree are two views of the same thing: rendering a tree back to text is
      the certified inverse of parsing it, so <code>url4.build(url4.render(node))</code> returns the
      original tree. That round-trip is what lets a run be logged, shared, and replayed exactly.
    </p>

    <CodeBlock :code="roundtrip" language="python" />

    <h2>Why it exists</h2>

    <p>
      Every run compiles to one canonical url4 string — loggable, inspectable, and re-runnable. It is
      the audit trail: import a url4 and you hold the whole system and its benchmark run, not a
      description of it. Model outputs still vary between runs, so the numbers will not match to the
      decimal; the expression pins down the <em>definition</em> of the run, not its results.
      Stability is the promise — a url4 written today is meant to run tomorrow.
    </p>

    <blockquote>
      url4 is deliberately unbranded — a commons artifact, not a product feature. The open web works
      because open protocols arrived early; url4 aims to be that early, open layer for describing
      composed intelligence.
    </blockquote>

    <h2>In code</h2>

    <p>
      To parse, build, and execute url4 from Python, see the
      <RouterLink to="/learn/url4-sdk">url4 SDK</RouterLink>. The grammar, parser, and DAG live in
      <a :href="`${GH_TREE}/packages/url4`" target="_blank" rel="noopener"><code>packages/url4</code></a>:
      the recursive-descent parser in
      <a :href="`${GH_BLOB}/packages/url4/src/url4/core/grammar.py`" target="_blank" rel="noopener"><code>core/grammar.py</code></a>,
      the canonical renderer in
      <a :href="`${GH_BLOB}/packages/url4/src/url4/core/render.py`" target="_blank" rel="noopener"><code>core/render.py</code></a>,
      and the executor in
      <a :href="`${GH_TREE}/packages/url4/src/url4/dag`" target="_blank" rel="noopener"><code>src/url4/dag</code></a>.
    </p>
  </DocLayout>
</template>
