import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { APP_ROUTE_DEFINITIONS } from '@/app/navigation'
import { PUBLIC_SITE } from '@/app/publicSite'

const routes: RouteRecordRaw[] = APP_ROUTE_DEFINITIONS.filter(route => !PUBLIC_SITE || !['TradeSignalReview', 'DataHealth'].includes(route.name)).map((route) => {
  const routeRecord: RouteRecordRaw = 'redirect' in route ? {
    path: route.path,
    name: route.name,
    redirect: route.redirect,
  } : {
    path: route.path,
    name: route.name,
    component: route.component,
  }
  if ('children' in route) routeRecord.children = route.children.map(child => ({ ...child }))
  if ('meta' in route) {
    routeRecord.meta = route.meta
  }
  return routeRecord
})

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
