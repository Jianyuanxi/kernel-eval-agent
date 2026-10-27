import { createRouter, createWebHashHistory } from 'vue-router'
import UploadView from './views/UploadView.vue'
import TaskView from './views/TaskView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'upload', component: UploadView },
    { path: '/task/:id', name: 'task', component: TaskView, props: true },
  ],
})

export default router
