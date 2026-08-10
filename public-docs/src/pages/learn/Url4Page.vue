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
    description="The open, lowercase expression that packages sources and an intent into one line, so a fusion runs, reproduces, and can be reused like a model call."
    :navigation="navigation"
  >
    <p>
      <strong>url4</strong> is a small grammar for saying <em>given these sources, do this</em>. It
      packages a set of sources, an intent, and the metadata to run them into a single line of text:
      <code>(data)!intent</code>. That line is also an <strong>address</strong>: hand it to the
      <RouterLink to="/learn/engine">Engine</RouterLink> and it resolves. So everything you build in
      the <RouterLink to="/sf-client">Client</RouterLink>, a single model, a
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink>, or a whole benchmark run,
      compiles to one url4 string. You can log it, diff it, share it, reproduce it, and call it again
      exactly like a single model. That reuse is the point: a Fusion you like is not a one-off, its
      url4 is a callable, reproducible artifact you can drop into any workflow.
    </p>

    <p>Like <code>http</code>, it is always written lowercase.</p>

    <h2>Two layers</h2>

    <p>
      A url4 string has two layers. The <strong>grammar</strong>, <code>(data)!intent</code>, is
      what you write and what a node parses: sources in parentheses, an intent after the
      <code>!</code>. The <strong>protocol</strong> is how any conforming node, such as the Engine,
      resolves each source, runs the intent, and returns a result. You write the grammar; the
      protocol is what makes the same string runnable anywhere.
    </p>

    <h2>The shape</h2>

    <p>
      Sources go in parentheses; the intent comes after the <code>!</code>. The simplest expression
      is a single source and an intent:
    </p>

    <CodeBlock code="(a=https://x, tone='formal')!'Summarize $a in a $tone tone'" language="text" />

    <p>
      A source can be a URI, a literal value, or a nested url4 expression. Sources can be named
      (<code>a=…</code>), referenced by name (<code>$a</code>) or position (<code>$1</code>),
      weighted and budgeted, iterated over, and expanded. Because a source can itself be another
      url4 expression, an expression composes recursively into an arbitrary graph. A few real
      shapes, drawn from the grammar's own test suite:
    </p>

    <CodeBlock :code="examples" language="text" />

    <h2>Two ways to run it</h2>

    <p>The same grammar drives two execution modes, and one expression can mix them freely.</p>

    <p>
      <strong>Model mode</strong> (the spec's <em>LLM mode</em>). Sources are context and the intent
      is a natural-language prompt. The Engine feeds the resolved sources to a model, or to a
      <RouterLink to="/sf-client/guides/fusions">Fusion</RouterLink> of models, and synthesizes one
      answer. This is the mode the Client uses: a Fusion is a url4 expression in model mode.
    </p>

    <p>
      <strong>Compute mode</strong> (the spec's <em>remote data science</em>, or <em>RDS</em>,
      mode). Sources are structured inputs and the intent points at code, a script or a notebook.
      The Engine binds the inputs to the code's contract and runs it, so computation can run next to
      data that never has to move. A single expression can chain the two: a compute step that
      prepares data, feeding a model step that summarizes it. The whole chain stays one addressable
      url4.
    </p>

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

    <h2>An address, not just a string</h2>

    <p>
      Because the whole request lives in one URI, the Engine treats a url4 expression the way
      <code>http</code> treats a URL: as an address it resolves. The call is idempotent and
      cacheable, since the same expression always describes the same work, and that is exactly what
      lets you <em>reuse</em> it. Save a Fusion's url4, hand it to an
      <RouterLink to="/learn/engine">Engine</RouterLink>, and it runs like any other model call. A
      source inside one expression can be the result of another expression on another node, so
      fusions compose into larger pipelines without anyone unpacking them.
    </p>

    <p>
      This is why the request is a URI and not out-of-band configuration. Standard HTTP
      infrastructure, gateways, caches, and logs, can route and trace the request without
      understanding the grammar, and the attribution and governance metadata travels
      <em>with</em> the request rather than alongside it. To serve and call a url4 node yourself,
      see the <RouterLink to="/learn/url4-sdk">url4 SDK</RouterLink>, which exposes the same shape
      the Engine does.
    </p>

    <h2>Why it exists</h2>

    <p>
      Every run compiles to one canonical url4 string: loggable, inspectable, and re-runnable. It is
      the audit trail: import a url4 and you hold the whole system and its benchmark run, not a
      description of it. Model outputs still vary between runs, so the numbers will not match to the
      decimal; the expression pins down the <em>definition</em> of the run, not its results.
      Stability is the promise: a url4 written today is meant to run tomorrow.
    </p>

    <blockquote>
      url4 is deliberately unbranded: a commons artifact, not a product feature. The open web works
      because open protocols arrived early; url4 aims to be that early, open layer for describing
      composed intelligence.
    </blockquote>

    <h2>In code</h2>

    <p>
      To parse, build, and execute url4 from Python, see the
      <RouterLink to="/learn/url4-sdk">url4 SDK</RouterLink>. The grammar, parser, and DAG live in
      <a :href="`${GH_TREE}/packages/url4`" target="_blank" rel="noopener"
        ><code>packages/url4</code></a
      >: the recursive-descent parser in
      <a :href="`${GH_BLOB}/packages/url4/src/url4/core/grammar.py`" target="_blank" rel="noopener"
        ><code>core/grammar.py</code></a
      >, the canonical renderer in
      <a :href="`${GH_BLOB}/packages/url4/src/url4/core/render.py`" target="_blank" rel="noopener"
        ><code>core/render.py</code></a
      >, and the executor in
      <a :href="`${GH_TREE}/packages/url4/src/url4/dag`" target="_blank" rel="noopener"
        ><code>src/url4/dag</code></a
      >.
    </p>
  </DocLayout>
</template>
