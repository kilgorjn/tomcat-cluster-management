import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import Applications from '@/views/Applications.vue'
import Clusters from '@/views/Clusters.vue'
import Nodes from '@/views/Nodes.vue'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
  }
}

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: Dashboard, meta: { title: 'Dashboard' } },
  { path: '/applications', component: Applications, meta: { title: 'Applications' } },
  { path: '/clusters', component: Clusters, meta: { title: 'Clusters' } },
  { path: '/nodes', component: Nodes, meta: { title: 'Nodes' } },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `TCM — ${to.meta.title ?? 'Console'}`
})

export default router
