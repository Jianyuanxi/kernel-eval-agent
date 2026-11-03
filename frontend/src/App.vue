<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const taskId = computed(() => (route.name === 'task' ? route.params.id : ''))
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <router-link to="/" class="brand">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <rect x="6" y="6" width="16" height="16" rx="2" />
          <rect x="10" y="10" width="8" height="8" fill="#2847d8" stroke="none" />
          <path d="M10 2v4M14 2v4M18 2v4M10 22v4M14 22v4M18 22v4M2 10h4M2 14h4M2 18h4M22 10h4M22 14h4M22 18h4" />
        </svg>
        内核代码评测
      </router-link>
      <span class="spacer" />
      <template v-if="taskId">
        <span class="task-id">{{ taskId }}</span>
        <router-link to="/" class="btn ghost">评测下一个内核</router-link>
      </template>
    </header>
    <main class="page">
      <router-view />
    </main>
  </div>
</template>
