<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const el = ref(null)
let chart = null
let echarts = null

function option() {
  const items = props.items.filter((item) => item.score !== null && item.score !== undefined)
  return {
    tooltip: {},
    radar: {
      indicator: items.map((item) => ({ name: item.name, max: 100 })),
      radius: '62%',
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            name: '得分率',
            value: items.map((item) => Math.round((item.score / item.max) * 1000) / 10),
            areaStyle: { color: 'rgba(31, 111, 100, 0.2)' },
            lineStyle: { color: '#1f6f64' },
            itemStyle: { color: '#1f6f64' },
          },
        ],
      },
    ],
  }
}

async function render() {
  if (!el.value) return
  const items = props.items.filter((item) => item.score !== null && item.score !== undefined)
  if (!items.length) {
    chart?.clear()
    return
  }
  if (!echarts) echarts = await import('echarts')
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(option(), true)
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
watch(() => props.items, render, { deep: true })
</script>

<template>
  <div ref="el" class="radar" role="img" aria-label="四项得分率雷达图" />
</template>
