<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getEvents, getReport, getTask, startTask, formatError } from '../api'
import ToolTimeline from '../components/ToolTimeline.vue'

const props = defineProps({ id: { type: String, required: true } })

const STAGES = [
  { key: 'building', label: '编译' },
  { key: 'running', label: '运行' },
  { key: 'scanning', label: '扫描' },
  { key: 'diffing', label: '对比' },
  { key: 'reviewing', label: '智能体评审' },
  { key: 'scoring', label: '评分' },
]

const task = ref(null)
const events = ref([])
const report = ref(null)
const error = ref('')
const starting = ref(false)
let timer = null

const stage = computed(() => task.value?.stage || '')
const showSelect = computed(() => stage.value === 'waiting_select')
const showProgress = computed(() =>
  ['queued', 'building', 'running', 'scanning', 'diffing', 'reviewing', 'scoring', 'uploaded'].includes(stage.value)
    || stage.value === 'failed',
)
const showReport = computed(() => stage.value === 'done')

function stageClass(key) {
  const current = stage.value
  const order = STAGES.map((s) => s.key)
  if (current === 'failed') return 'failed'
  if (current === 'done') return 'done'
  const ci = order.indexOf(current)
  const ki = order.indexOf(key)
  if (ci < 0) return ''
  if (ki < ci) return 'done'
  if (ki === ci) return 'current'
  return ''
}

async function loadTask() {
  task.value = await getTask(props.id)
}

async function autoStartIfNeeded() {
  if (!task.value || task.value.stage !== 'waiting_select') return
  if (task.value.projects.length !== 1) return
  await choose(task.value.projects[0].project_id)
}

async function choose(projectId) {
  starting.value = true
  error.value = ''
  try {
    task.value = await startTask(props.id, projectId)
    startPolling()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    starting.value = false
  }
}

async function poll() {
  try {
    const after = events.value.reduce((m, e) => Math.max(m, e.seq), 0)
    const data = await getEvents(props.id, after)
    if (data.tool_calls?.length) events.value = events.value.concat(data.tool_calls)
    if (task.value) {
      task.value.stage = data.stage
      task.value.progress = data.progress
    }
    if (data.stage === 'done') {
      report.value = await getReport(props.id)
      stop()
    } else if (data.stage === 'failed') {
      await loadTask()
      stop()
    }
  } catch (e) {
    error.value = formatError(e)
  }
}

function startPolling() {
  stop()
  poll()
  timer = setInterval(poll, 2000)
}

function stop() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(async () => {
  try {
    await loadTask()
    await autoStartIfNeeded()
    if (task.value.stage === 'done') {
      report.value = await getReport(props.id)
    } else if (task.value.stage !== 'waiting_select') {
      startPolling()
    }
  } catch (e) {
    error.value = formatError(e)
  }
})

onUnmounted(stop)
watch(() => props.id, () => {
  events.value = []
  report.value = null
})
</script>

<template>
  <section v-if="task" class="card">
    <p class="hint">任务 {{ task.task_id }} · {{ task.upload_name }}</p>

    <template v-if="showSelect">
      <h1>选择要评测的工程</h1>
      <p class="lead">识别出 {{ task.projects.length }} 个工程。只有一个时会自动开始。</p>
      <div class="project-grid">
        <article v-for="p in task.projects" :key="p.project_id" class="project">
          <div>
            <h3>{{ p.name }}</h3>
            <div class="meta">
              <span>{{ p.kind === 'full' ? '完整工程' : '代码片段' }}</span>
              <span>{{ p.arch }}</span>
              <span>{{ p.file_count }} 个文件 / {{ p.c_files }} 个 .c</span>
              <span>{{ p.buildable ? '可编译' : '不能编译' }}</span>
            </div>
            <p v-if="p.note" class="hint">{{ p.note }}</p>
          </div>
          <button class="btn" :disabled="starting" @click="choose(p.project_id)">评测这个</button>
        </article>
      </div>
    </template>

    <template v-if="showProgress">
      <h1>{{ stage === 'failed' ? '评测失败' : '评测进行中' }}</h1>
      <p class="lead">{{ task.progress || '正在准备…' }}</p>
      <div class="stages">
        <span v-for="s in STAGES" :key="s.key" class="stage" :class="stageClass(s.key)">{{ s.label }}</span>
      </div>
      <h2>工具调用时间线</h2>
      <ToolTimeline :events="events" />
      <div v-if="task.error" class="error">{{ formatError(task.error) }}</div>
    </template>

    <template v-if="showReport && report">
      <h1>评测完成</h1>
      <div class="score-hero">
        <span class="num">{{ report.score.total }}</span>
        <span class="grade">{{ report.score.grade }}</span>
      </div>
      <p class="lead">
        {{ report.project.name }} · {{ report.model || '模型未记录' }} · {{ report.generated_at }}
      </p>
      <p class="hint">完整报告页（雷达图、缺陷清单、源码查看、导出）在阶段 2 实现。刷新本页可恢复任务。</p>
      <ToolTimeline :events="report.tool_calls" />
    </template>
  </section>
  <div v-if="error" class="error">{{ error }}</div>
</template>
