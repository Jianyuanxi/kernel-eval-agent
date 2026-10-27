<script setup>
defineProps({
  events: { type: Array, default: () => [] },
})

const sourceLabel = { pipeline: '流水线', agent: '智能体', followup: '追问' }
const statusLabel = {
  passed: '成功',
  failed: '失败',
  timeout: '超时',
  skipped: '跳过',
  unsupported: '不支持',
  error: '出错',
}
</script>

<template>
  <ol class="timeline">
    <li v-for="ev in events" :key="ev.seq" class="event" :class="ev.source">
      <div class="row">
        <span>
          #{{ ev.seq }}
          <strong>{{ sourceLabel[ev.source] || ev.source }}</strong>
          · {{ ev.tool }}
        </span>
        <span>
          <span class="badge" :class="ev.status">{{ statusLabel[ev.status] || ev.status }}</span>
          {{ ev.duration_ms }} ms
        </span>
      </div>
      <div class="summary">{{ ev.summary }}</div>
    </li>
    <li v-if="!events.length" class="hint">等待工具调用记录…</li>
  </ol>
</template>
