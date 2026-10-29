<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getEvents, getReport, getTask, startTask, formatError } from '../api'
import ToolTimeline from '../components/ToolTimeline.vue'
import ReportView from './ReportView.vue'

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
let generation = 0

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

/** 只接收当前页面这轮加载的响应。 */
function isCurrent(version) {
  return version === generation
}

async function choose(projectId, version = generation) {
  if (starting.value || !isCurrent(version)) return
  starting.value = true
  error.value = ''
  try {
    const info = await startTask(props.id, projectId)
    if (!isCurrent(version)) return
    task.value = info
    poll(version)
  } catch (e) {
    if (isCurrent(version)) error.value = formatError(e)
  } finally {
    if (isCurrent(version)) starting.value = false
  }
}

/** 完成本次请求后才安排下一次轮询，避免慢请求重叠。 */
async function poll(version) {
  let finished = false
  try {
    const after = events.value.reduce((m, e) => Math.max(m, e.seq), 0)
    const data = await getEvents(props.id, after)
    if (!isCurrent(version)) return
    if (data.tool_calls?.length) {
      const seen = new Set(events.value.map((event) => event.seq))
      events.value = events.value.concat(data.tool_calls.filter((event) => !seen.has(event.seq)))
    }
    task.value.stage = data.stage
    task.value.progress = data.progress
    if (data.stage === 'done') {
      const result = await getReport(props.id)
      if (!isCurrent(version)) return
      report.value = result
      finished = true
    } else if (data.stage === 'failed') {
      const info = await getTask(props.id)
      if (!isCurrent(version)) return
      task.value = info
      finished = true
    }
    error.value = ''
  } catch (e) {
    if (isCurrent(version)) error.value = formatError(e)
  } finally {
    if (isCurrent(version) && !finished) timer = setTimeout(() => poll(version), 2000)
  }
}

function stop() {
  generation += 1
  clearTimeout(timer)
  timer = null
}

onUnmounted(stop)

async function bootstrap() {
  stop()
  const version = generation
  task.value = null
  events.value = []
  report.value = null
  error.value = ''
  starting.value = false
  try {
    const info = await getTask(props.id)
    if (!isCurrent(version)) return
    task.value = info
    if (info.stage === 'waiting_select') {
      if (info.projects.length === 1) await choose(info.projects[0].project_id, version)
    } else {
      poll(version)
    }
  } catch (e) {
    if (isCurrent(version)) error.value = formatError(e)
  }
}

onMounted(bootstrap)
watch(() => props.id, bootstrap)
</script>

<template>
  <section v-if="task && !showReport" class="card">
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

  </section>
  <section v-if="showReport && !report" class="card">
    <h1>{{ error ? '报告加载失败' : '正在加载报告…' }}</h1>
    <p class="lead"><span v-if="!error" class="spinner" aria-hidden="true" /> {{ error ? '正在自动重试，请稍候。' : '请稍候，正在读取评分结果。' }}</p>
  </section>
  <ReportView v-if="showReport && report" :key="id" :task-id="id" :report="report" />
  <div v-if="error" class="error">
    {{ error }}
    <button class="btn ghost" type="button" @click="bootstrap">重新加载</button>
  </div>
</template>
