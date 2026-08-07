import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/pages/HomePage.vue'),
    },
    {
      path: '/sf-client',
      name: 'sf-client',
      component: () => import('@/pages/sf-client/Index.vue'),
    },
    {
      path: '/sf-client/installation',
      name: 'sf-client-installation',
      component: () => import('@/pages/sf-client/InstallationPage.vue'),
    },
    {
      path: '/sf-client/quickstartPage',
      name: 'sf-client-quickstart',
      component: () => import('@/pages/sf-client/QuickstartPage.vue'),
    },
    {
      path: '/sf-client/guides/connections',
      name: 'sf-client-guides-connections',
      component: () => import('@/pages/sf-client/guides/ConnectionsPage.vue'),
    },
    {
      path: '/sf-client/guides/models',
      name: 'sf-client-guides-models',
      component: () => import('@/pages/sf-client/guides/ModelsPage.vue'),
    },
    {
      path: '/sf-client/guides/fusions',
      name: 'sf-client-guides-fusions',
      component: () => import('@/pages/sf-client/guides/FusionsPage.vue'),
    },
    {
      path: '/sf-client/guides/benchmarks',
      name: 'sf-client-guides-benchmarks',
      component: () => import('@/pages/sf-client/guides/BenchmarksPage.vue'),
    },
    {
      path: '/sf-client/guides/running-an-evaluation',
      name: 'sf-client-guides-evaluation',
      component: () => import('@/pages/sf-client/guides/EvaluationPage.vue'),
    },
    {
      path: '/sf-client/guides/reproduce-and-share',
      name: 'sf-client-guides-url4',
      component: () => import('@/pages/sf-client/guides/Url4Page.vue'),
    },
    {
      path: '/learn',
      name: 'learn',
      component: () => import('@/pages/learn/ArchitecturePage.vue'),
    },
    {
      path: '/learn/url4',
      name: 'learn-url4',
      component: () => import('@/pages/learn/Url4Page.vue'),
    },
    {
      path: '/learn/engine',
      name: 'learn-engine',
      component: () => import('@/pages/learn/EnginePage.vue'),
    },
    {
      path: '/learn/url4-sdk',
      name: 'learn-url4-sdk',
      component: () => import('@/pages/learn/Url4SdkPage.vue'),
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
