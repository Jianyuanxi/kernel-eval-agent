<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  events: { type: Array, default: () => [] },
  /** 评测进行中：末尾显示闪烁光标和等待提示 */
  live: { type: Boolean, default: false },
  waiting: { type: String, default: '' },
})

const sourceLabel = { pipeline: '流水线', agent: '智能体', followup: '追问' }
const statusLabel = {
  passed: '完成',
  failed: '失败',
  timeout: '超时',
  skipped: '跳过',
  unsupported: '不支持',
  error: '出错',
}
const opened = ref(new Set())

/** 流水线连续的 read_source 预读合成一行，点开再看每一段。 */
const rows = computed(() => {
  const out = []
  for (const ev of props.events) {
    const prev = out[out.length - 1]
    if (ev.source === 'pipeline' && ev.tool === 'read_source') {
      if (prev?.group) prev.items.push(ev)
      else out.push({ group: true, key: `g${ev.seq}`, first: ev, items: [ev] })
    } else {
      out.push({ group: false, key: `e${ev.seq}`, first: ev })
    }
  }
  return out
})

const t0 = computed(() => Date.parse(props.events[0]?.started_at || '') || 0)

function clock(ev) {
  const t = Date.parse(ev.started_at || '')
  if (!t0.value || !t) return ''
  const s = Math.max(0, Math.round((t - t0.value) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** 0 ms 的多是直接用了流水线已算好的结果，显示“完成”而不是误导人的 0 ms。 */
function result(ev) {
  if (ev.status !== 'passed') return statusLabel[ev.status] || ev.status
  if (ev.duration_ms >= 100) return `${(ev.duration_ms / 1000).toFixed(1)} s`
  return '完成'
}

function toggle(key) {
  const next = new Set(opened.value)
  next.has(key) ? next.delete(key) : next.add(key)
  opened.value = next
}
</script>

<template>
  <ol class="console" :class="{ live }">
    <template v-for="row in rows" :key="row.key">
      <li v-if="row.group" class="ln group" role="button" tabindex="0" :aria-expanded="opened.has(row.key)"
          @click="toggle(row.key)" @keydown.enter.prevent="toggle(row.key)">
        <span class="t">{{ clock(row.first) }}</span>
        <span class="what"><span class="who">流水线</span>　<span class="tool">预读源码 {{ row.items.length }} 段</span>有告警的、新增和修改的文件，一次交给智能体（{{ opened.has(row.key) ? '收起' : '点开看明细' }}）</span>
        <span class="res">完成</span>
      </li>
      <template v-if="row.group && opened.has(row.key)">
        <li v-for="ev in row.items" :key="ev.seq" class="sub">{{ ev.summary }}</li>
      </template>
      <li v-if="!row.group" class="ln">
        <span class="t">{{ clock(row.first) }}</span>
        <span class="what"><span class="who" :class="row.first.source">{{ sourceLabel[row.first.source] || row.first.source }}</span>　<span class="tool">{{ row.first.tool }}</span>{{ row.first.summary }}</span>
        <span class="res" :class="{ bad: row.first.status !== 'passed' }">{{ result(row.first) }}</span>
      </li>
    </template>
    <li v-if="live" class="ln wait">
      <span />
      <span class="what">{{ waiting || '等待下一步' }}… <span class="cursor" aria-hidden="true" /></span>
      <span />
    </li>
    <li v-else-if="!events.length" class="wait">没有工具调用记录</li>
  </ol>
</template>
