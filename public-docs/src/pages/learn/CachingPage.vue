<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DocLayout from '@/components/layout/DocLayout.vue'
import { learnNavigation as navigation } from '@/navigation/learn'
</script>

<template>
  <DocLayout
    title="Caching and compute"
    description="Why runs, and especially reruns, stay cheap: call-level caching, a shared community cache, and where the compute comes from."
    :navigation="navigation"
  >
    <p>
      Evaluating a fusion means many model calls, and calls cost money and time. ScreamingFace keeps
      that cost low in two ways: it caches every call, and it gives you a choice of where the
      compute comes from.
    </p>

    <h2>Every call is cached</h2>

    <p>
      When the <RouterLink to="/learn/engine">engine</RouterLink> calls a model, it stores the
      response keyed by the exact request. Reuse the same model in another candidate, or run the
      same evaluation again, and the stored response is served instead of paying for it twice.
    </p>

    <ul>
      <li>
        <strong>Within a run:</strong> a model shared across several candidates is computed once, so
        a fusion that reuses its members is far cheaper than the number of candidates suggests.
      </li>
      <li>
        <strong>Across runs:</strong> re-running an evaluation only pays for calls that are new. If
        a run fails partway, restarting it charges you only for the work that had not completed.
      </li>
    </ul>

    <h2>The shared community cache</h2>

    <p>
      A hosted engine's cache is shared across the community. If anyone has already run the same
      model configuration against a benchmark, that call is a cache hit for you as well, at no cost.
      Verifying a published result, or building on someone else's fusion, usually costs a fraction
      of the original run, because the expensive part has already been paid for once.
    </p>

    <p>
      This is what makes reproduction practical. A published result carries its
      <RouterLink to="/learn/url4">url4</RouterLink>, and re-running that url4 mostly lands on
      cached calls, so checking the work takes minutes and pennies rather than repeating the whole
      run.
    </p>

    <h2>Where the compute comes from</h2>

    <p>There are two ways to run, and they differ only in who supplies the compute.</p>

    <ul>
      <li>
        <strong>Local.</strong> Run the engine on your own machine with your own provider keys. You
        pay your providers directly, and there is no middleman on the local path.
      </li>
      <li>
        <strong>Hosted.</strong> Use an engine we operate. It carries the shared cache, and we
        provide subsidized compute to chosen cohorts so that verifying and exploring stays cheap.
      </li>
    </ul>

    <p>
      The client code is identical either way; only the engine URL changes. The
      <RouterLink to="/sf-client/installation">Installation</RouterLink> guide walks through both.
    </p>
  </DocLayout>
</template>
