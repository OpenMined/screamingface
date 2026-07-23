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
      path: '/sdk',
      name: 'sdk',
      component: () => import('@/pages/sdk/Index.vue'),
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
