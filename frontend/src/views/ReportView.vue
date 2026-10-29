<script setup>
import { computed, ref } from 'vue'
import { marked } from 'marked'
import { exportHref, formatError, getSource, postFollowup } from '../api'
import ScoreRadar from '../components/ScoreRadar.vue'
import SourceDrawer from '../components/SourceDrawer.vue'
import ToolTimeline from '../components/ToolTimeline.vue'
import {
  FEATURE_NAMES,
  FEATURE_STATUS,
  KNOWLEDGE_NAMES,
  SEVERITY_RANK,
  STATUS_LABEL,
  STYLE_GRADE,
} from '../labels'

const props = defineProps({
  taskId: { type: String, required: true },
  report: { type: Object, required: true },
})

const logOpen = ref(false)
const thoughtsOpen = ref(false)
const pickedDefect = ref(null)
const question = ref('')
const asking = ref(false)
const askError = ref('')
const followups = ref([])
const drawerOpen = ref(false)
const slice = ref(null)
const highlight = ref(0)
const sourcePath = ref('')
const sourceLoading = ref(false)
const sourceError = ref('')

const fragment = computed(() => props.report.mode === 'fragment' || props.report.score.mode === 'fragment')
const defects = computed(() =>
  props.report.defects
    .map((defect, index) => ({ defect, index }))
    .sort((a, b) => (SEVERITY_RANK[a.defect.severity] ?? 9) - (SEVERITY_RANK[b.defect.severity] ?? 9) || a.index - b.index),
)
const changedFiles = computed(() => (props.report.diff?.files || []).filter((file) => file.change !== 'same'))

function scoreText(item) {
  if (item.score === null || item.score === undefined) return '不计分'
  return `${item.score}/${item.max}`
}

async function loadSource(path, start, line) {
  drawerOpen.value = true
  sourceLoading.value = true
  sourceError.value = ''
  sourcePath.value = path
  highlight.value = line
  const safeStart = Math.max(1, start)
  try {
    slice.value = await getSource(props.taskId, path, safeStart, safeStart + 199)
  } catch (error) {
    slice.value = null
    sourceError.value = formatError(error, '读不到源码')
  } finally {
    sourceLoading.value = false
  }
}

function openSource(path, line) {
  loadSource(path, Math.max(1, (line || 1) - 20), line || 0)
}

function turnPage(delta) {
  if (!slice.value) return
  loadSource(sourcePath.value, Math.max(1, slice.value.start_line + delta), highlight.value)
}

function pickDefect(row) {
  pickedDefect.value = row
  document.getElementById('followup-box')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function renderAnswer(text) {
  return marked.parse(text || '', { breaks: true, gfm: true })
}

async function ask() {
  const q = question.value.trim()
  if (!q || asking.value) return
  asking.value = true
  askError.value = ''
  try {
    const res = await postFollowup(props.taskId, q, pickedDefect.value ? pickedDefect.value.index : null)
    followups.value = [
      {
        question: q,
        defect: pickedDefect.value?.defect?.title || '',
        answer: res.answer,
        html: renderAnswer(res.answer),
        tool_calls: res.tool_calls || [],
      },
      ...followups.value,
    ]
    question.value = ''
  } catch (error) {
    askError.value = error?.name === 'AbortError' ? '追问超时，请稍后再试' : formatError(error)
  } finally {
    asking.value = false
  }
}
function scrollToSection(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <div class="report">
    <nav class="report-nav card" aria-label="报告目录">
      <button type="button" class="nav-link" @click="scrollToSection('sec-scores')">分项分数</button>
      <button type="button" class="nav-link" @click="scrollToSection('sec-build')">编译运行</button>
      <button type="button" class="nav-link" @click="scrollToSection('sec-features')">功能点</button>
      <button type="button" class="nav-link" @click="scrollToSection('sec-defects')">缺陷清单</button>
      <button type="button" class="nav-link" @click="scrollToSection('sec-style')">规范创新</button>
      <button type="button" class="nav-link" @click="scrollToSection('sec-diff')">参考对比</button>
      <button type="button" class="nav-link" @click="scrollToSection('sec-tools')">工具过程</button>
      <button type="button" class="nav-link" @click="scrollToSection('followup-box')">追问</button>
    </nav>

    <section class="card hero">
      <div>
        <p class="hint">任务 {{ report.task_id }}</p>
        <div class="score-hero">
          <span class="num">{{ report.score.total }}</span>
          <span class="grade">{{ report.score.grade }}</span>
        </div>
        <p class="lead">
          {{ report.project.name }} · {{ report.model || '模型未记录' }} · {{ report.generated_at }}
        </p>
        <p>{{ report.summary }}</p>
        <div class="btn-row">
          <a class="btn" :href="exportHref(taskId, 'json')">导出 JSON</a>
          <a class="btn ghost" :href="exportHref(taskId, 'md')">导出 Markdown</a>
        </div>
      </div>
      <ScoreRadar :items="report.score.items" />
    </section>

    <section id="sec-scores" class="card">
      <h2>分项分数</h2>
      <div class="item-grid">
        <article v-for="item in report.score.items" :key="item.key" class="item-card">
          <h3>{{ item.name }}</h3>
          <p class="score-line">{{ scoreText(item) }}</p>
          <ul>
            <li v-for="(reason, i) in item.reasons" :key="i">{{ reason }}</li>
          </ul>
        </article>
      </div>
    </section>

    <section id="sec-build" class="card">
      <h2>编译与运行</h2>
      <p v-if="fragment">只提交了代码片段</p>
      <template v-else>
        <p v-if="report.build">
          编译 {{ STATUS_LABEL[report.build.status] || report.build.status }}
          · 警告 {{ report.build.warnings }} 条
          · 错误 {{ report.build.errors }} 个
        </p>
        <ul v-if="report.build?.diagnostics?.length" class="diag">
          <li v-for="d in report.build.diagnostics" :key="d.evidence_id">
            <span class="badge" :class="d.severity">{{ d.severity }}</span>
            {{ d.path || '（工程外）' }}<template v-if="d.line">:{{ d.line }}</template>
            {{ d.message }}
          </li>
        </ul>
        <button v-if="report.build?.log_tail" class="btn ghost" type="button" @click="logOpen = !logOpen">
          {{ logOpen ? '收起构建日志' : '展开构建日志' }}
        </button>
        <pre v-if="logOpen" class="mono">{{ report.build.log_tail }}</pre>
        <template v-if="report.run">
          <p>运行 {{ STATUS_LABEL[report.run.status] || report.run.status }}<template v-if="report.run.shell_prompt"> · 提示符 {{ report.run.shell_prompt }}</template></p>
          <h3>启动输出</h3>
          <pre class="mono">{{ report.run.boot_output || '（无输出）' }}</pre>
          <article v-for="cmd in report.run.commands" :key="cmd.evidence_id">
            <h3>$ {{ cmd.command }}</h3>
            <pre class="mono">{{ cmd.output }}</pre>
          </article>
        </template>
      </template>
    </section>

    <section id="sec-features" class="card">
      <h2>功能点</h2>
      <ul class="feature-list">
        <li v-for="feature in report.features" :key="feature.feature_id">
          <span class="badge" :class="feature.status">{{ FEATURE_STATUS[feature.status] }}</span>
          <strong>{{ FEATURE_NAMES[feature.feature_id] }}</strong>
          <span>{{ feature.reason }}</span>
          <button
            v-for="loc in feature.locations"
            :key="loc.path + loc.line"
            class="linkish"
            type="button"
            @click="openSource(loc.path, loc.line)"
          >
            {{ loc.path }}:{{ loc.line }}
          </button>
        </li>
      </ul>
    </section>

    <section id="sec-defects" class="card">
      <h2>缺陷清单</h2>
      <article v-for="row in defects" :key="row.index" class="defect">
        <header>
          <span class="badge" :class="'sev-' + row.defect.severity">{{ row.defect.severity }}</span>
          <strong>{{ row.defect.type_name }}</strong>
          <button class="linkish" type="button" @click="openSource(row.defect.path, row.defect.line)">
            {{ row.defect.path }}:{{ row.defect.line }}
          </button>
        </header>
        <h3>{{ row.defect.title }}</h3>
        <p>{{ row.defect.description }}</p>
        <p class="hint">来源 {{ row.defect.source }} · {{ KNOWLEDGE_NAMES[row.defect.knowledge_category] }}</p>
        <p>{{ row.defect.knowledge }}</p>
        <p>建议：{{ row.defect.suggestion }}</p>
        <div class="diff-cols">
          <div>
            <p class="hint">改前</p>
            <pre class="mono">{{ row.defect.before || '（无）' }}</pre>
          </div>
          <div>
            <p class="hint">改后</p>
            <pre class="mono">{{ row.defect.after || '（无）' }}</pre>
          </div>
        </div>
        <p v-if="row.defect.in_baseline_unchanged" class="hint">参考代码原有，不扣分</p>
        <p v-else-if="row.defect.in_student_change" class="hint">学生改动</p>
        <button class="btn ghost" type="button" @click="pickDefect(row)">追问</button>
      </article>
    </section>

    <section id="sec-style" class="card">
      <h2>规范与创新</h2>
      <p>规范：{{ STYLE_GRADE[report.style.grade] }}。{{ report.style.reason }}</p>
      <p>学生声称：{{ report.innovation.claimed || '（无）' }}</p>
      <p>
        {{ report.innovation.found_in_code ? '代码中能找到对应实现。' : '代码中未找到对应实现。' }}
        {{ report.innovation.comment }}
      </p>
      <p>
        <button
          v-for="loc in report.innovation.locations"
          :key="loc.path + loc.line"
          class="linkish"
          type="button"
          @click="openSource(loc.path, loc.line)"
        >
          {{ loc.path }}:{{ loc.line }}
        </button>
      </p>
    </section>

    <section id="sec-diff" class="card">
      <h2>参考代码对比</h2>
      <template v-if="report.diff && report.diff.status === 'passed'">
        <p>
          基线 {{ report.diff.baseline || '未选定' }}
          · 相同 {{ report.diff.same }}
          · 修改 {{ report.diff.modified }}
          · 新增 {{ report.diff.added }}
        </p>
        <ul>
          <li v-for="file in changedFiles" :key="file.path">
            {{ file.change === 'added' ? '新增' : '修改' }} {{ file.path }}
            （+{{ file.added_lines }} / −{{ file.removed_lines }}）
          </li>
        </ul>
      </template>
      <p v-else class="hint">{{ report.diff?.note || '没有可用的参考代码对比' }}</p>
    </section>

    <section id="sec-tools" class="card">
      <h2>工具调用过程</h2>
      <ToolTimeline :events="report.tool_calls" />
      <button class="btn ghost" type="button" @click="thoughtsOpen = !thoughtsOpen">
        {{ thoughtsOpen ? '收起智能体思考' : '展开智能体思考' }}
      </button>
      <ol v-if="thoughtsOpen" class="thoughts">
        <li v-for="thought in report.agent_thoughts" :key="thought.id">
          <strong>#{{ thought.position }} {{ thought.tool || '思考' }}</strong>
          <p>{{ thought.thought || '（无）' }}</p>
          <p v-if="thought.observation" class="hint">观察：{{ thought.observation }}</p>
        </li>
      </ol>
    </section>

    <section v-if="report.warnings?.length" id="sec-warnings" class="card warn-card">
      <h2>提示</h2>
      <ul>
        <li v-for="(warning, i) in report.warnings" :key="i">{{ warning }}</li>
      </ul>
    </section>

    <section id="followup-box" class="card">
      <h2>追问</h2>
      <p class="hint">
        可以针对某条缺陷提问，也可以直接问。回答不会改分数。
        <template v-if="pickedDefect">当前缺陷：{{ pickedDefect.defect.title }}</template>
      </p>
      <textarea
        v-model="question"
        class="ask-box"
        rows="3"
        maxlength="1000"
        :disabled="asking"
        placeholder="例如：这段代码在中断里跑会出什么问题？"
        @keydown.meta.enter="ask"
        @keydown.ctrl.enter="ask"
      />
      <div class="btn-row">
        <button class="btn" type="button" :disabled="asking || !question.trim()" @click="ask">
          {{ asking ? '正在询问智能体…' : '发送' }}
        </button>
        <button v-if="pickedDefect" class="btn ghost" type="button" :disabled="asking" @click="pickedDefect = null">
          改为自由提问
        </button>
      </div>
      <div v-if="askError" class="error">{{ askError }}</div>
      <article v-for="(item, i) in followups" :key="i" class="followup-item">
        <p class="hint">问：{{ item.question }}<template v-if="item.defect">（{{ item.defect }}）</template></p>
        <div class="md" v-html="item.html" />
        <ToolTimeline v-if="item.tool_calls.length" :events="item.tool_calls" />
      </article>
    </section>

    <SourceDrawer
      :open="drawerOpen"
      :slice="slice"
      :highlight="highlight"
      :loading="sourceLoading"
      :error="sourceError"
      @close="drawerOpen = false"
      @page="turnPage"
    />
  </div>
</template>
