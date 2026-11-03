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
      axisName: { color: '#56636f', fontSize: 12 },
      splitLine: { lineStyle: { color: '#cfd7df' } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#cfd7df' } },
    },
    animationDuration: 900,
    animationEasing: 'cubicOut',
    series: [
      {
        type: 'radar',
        data: [
          {
            name: '得分率',
            value: items.map((item) => Math.round((item.score / item.max) * 1000) / 10),
            areaStyle: { color: 'rgba(40, 71, 216, 0.18)' },
            lineStyle: { color: '#2847d8', width: 2 },
            itemStyle: { color: '#2847d8' },
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
