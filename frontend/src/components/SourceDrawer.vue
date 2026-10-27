<script setup>
import { computed } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  slice: { type: Object, default: null },
  highlight: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['close', 'page'])

const lines = computed(() => {
  if (!props.slice?.text) return []
  return props.slice.text.split('\n').map((row) => {
    const cut = row.indexOf('|')
    const no = Number(row.slice(0, cut).trim())
    return { no, text: cut >= 0 ? row.slice(cut + 1) : row }
  })
})

const canPrev = computed(() => props.slice && props.slice.start_line > 1)
const canNext = computed(() => props.slice && props.slice.end_line < props.slice.total_lines)
</script>

<template>
  <div v-if="open" class="drawer-mask" @click.self="emit('close')">
    <aside class="drawer" role="dialog" aria-label="源码">
      <header class="drawer-head">
        <div>
          <strong>{{ slice?.path || '源码' }}</strong>
          <p v-if="slice" class="hint">
            第 {{ slice.start_line }}–{{ slice.end_line }} 行，共 {{ slice.total_lines }} 行（每次最多 200 行）
          </p>
        </div>
        <button class="btn ghost" type="button" @click="emit('close')">关闭</button>
      </header>
      <p v-if="loading" class="hint">正在读取源码…</p>
      <p v-else-if="error" class="error">{{ error }}</p>
      <pre v-else class="mono source"><code><span
        v-for="line in lines"
        :key="line.no"
        class="src-line"
        :class="{ hit: line.no === highlight }"
      >{{ String(line.no).padStart(5, ' ') }} | {{ line.text }}
</span></code></pre>
      <div class="btn-row">
        <button class="btn ghost" type="button" :disabled="!canPrev || loading" @click="emit('page', -200)">上一页</button>
        <button class="btn ghost" type="button" :disabled="!canNext || loading" @click="emit('page', 200)">下一页</button>
      </div>
    </aside>
  </div>
</template>
