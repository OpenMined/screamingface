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
      component: () => import('@/pages/sf-client/Installation.vue'),
    },
    {
      path: '/sf-client/quickstartPage',
      name: 'sf-client-quickstart',
      component: () => import('@/pages/sf-client/QuickstartPage.vue'),
    },
    {
      path: '/sf-client/usage',
      name: 'sf-client-usage',
      component: () => import('@/pages/sf-client/Usage.vue'),
    },
    {
      path: '/sf-client/development',
      name: 'sf-client-development',
      component: () => import('@/pages/sf-client/Development.vue'),
    },
    {
      path: '/sdk',
      name: 'sdk',
      component: () => import('@/pages/sdk/Index.vue'),
    },
    {
      path: '/sdk/installation',
      name: 'sdk-installation',
      component: () => import('@/pages/sdk/Installation.vue'),
    },
    {
      path: '/sdk/quickstart',
      name: 'sdk-quickstart',
      component: () => import('@/pages/sdk/Quickstart.vue'),
    },
    {
      path: '/sdk/authentication',
      name: 'sdk-authentication',
      component: () => import('@/pages/sdk/Authentication.vue'),
    },
    {
      path: '/sdk/rag-chat',
      name: 'sdk-rag-chat',
      component: () => import('@/pages/sdk/RagChat.vue'),
    },
    {
      path: '/sdk/browsing-hub',
      name: 'sdk-browsing-hub',
      component: () => import('@/pages/sdk/BrowsingHub.vue'),
    },
    {
      path: '/sdk/managing-endpoints',
      name: 'sdk-managing-endpoints',
      component: () => import('@/pages/sdk/ManagingEndpoints.vue'),
    },
    {
      path: '/sdk/error-handling',
      name: 'sdk-error-handling',
      component: () => import('@/pages/sdk/ErrorHandling.vue'),
    },
    {
      path: '/sdk/reference',
      name: 'sdk-reference',
      component: () => import('@/pages/sdk/Reference.vue'),
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
