<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { renderAnswer } from '../markdown'
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

async function ask() {
  const q = question.value.trim()
  if (!q || asking.value) return
  asking.value = true
  askError.value = ''
  const defect = pickedDefect.value
  try {
    const res = await postFollowup(props.taskId, q, defect ? defect.index : null)
    followups.value = [
      {
        question: q,
        defect: defect?.defect?.title || '',
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

const SECTIONS = [
  ['sec-overview', '总览'],
  ['sec-scores', '分项分数'],
  ['sec-features', '功能点'],
  ['sec-defects', '缺陷清单'],
  ['sec-build', '编译运行'],
  ['sec-style', '规范创新'],
  ['sec-diff', '参考对比'],
  ['sec-tools', '工具过程'],
  ['followup-box', '追问'],
]
const activeSection = ref('sec-overview')
const shownTotal = ref(0)
const grown = ref(false)
const openDefects = ref(new Set())

function gradeClass(grade) {
  if (['优秀', '良好'].includes(grade)) return 'g-good'
  if (['中等', '及格'].includes(grade)) return 'g-mid'
  return 'g-bad'
}

function ratio(item) {
  if (item.score === null || item.score === undefined || !item.max) return 0
  return Math.round((item.score / item.max) * 100)
}

function toggleDefect(index) {
  const next = new Set(openDefects.value)
  next.has(index) ? next.delete(index) : next.add(index)
  openDefects.value = next
}

/** 目录跟随滚动高亮：取最后一个顶端已经越过视口上方 140px 的小节。 */
function onScroll() {
  let current = SECTIONS[0][0]
  for (const [id] of SECTIONS) {
    const el = document.getElementById(id)
    if (el && el.getBoundingClientRect().top < 140) current = id
  }
  activeSection.value = current
}

/** 打开报告时总分从 0 数上去、分项条展开，只播一次。 */
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  if (defects.value.length) openDefects.value = new Set([defects.value[0].index])
  const target = Number(props.report.score?.total) || 0
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduce) {
    shownTotal.value = target
    grown.value = true
    return
  }
  const t0 = performance.now()
  const step = (t) => {
    const p = Math.min(1, (t - t0) / 900)
    shownTotal.value = Math.round(target * (1 - (1 - p) ** 3))
    if (p < 1) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
  requestAnimationFrame(() => requestAnimationFrame(() => { grown.value = true }))
})
onUnmounted(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <div class="report">
    <nav class="toc" aria-label="报告目录">
      <button
        v-for="[id, label] in SECTIONS"
        :key="id"
        type="button"
        :class="{ on: activeSection === id }"
        @click="scrollToSection(id)"
      >
        {{ label }}
      </button>
    </nav>

    <div>
      <section id="sec-overview" class="hero block">
        <div>
          <div class="big">{{ shownTotal }}<small>/100</small></div>
          <span class="grade" :class="gradeClass(report.score.grade)">{{ report.score.grade }}</span>
        </div>
        <div>
          <h1>{{ report.project.name }}</h1>
          <div class="meta">
            <span>{{ report.model || '模型未记录' }} 评审</span>
            <span>{{ report.generated_at }}</span>
          </div>
          <p>{{ report.summary }}</p>
          <div class="btn-row">
            <a class="btn ghost" :href="exportHref(taskId, 'md')">导出 Markdown</a>
            <a class="btn ghost" :href="exportHref(taskId, 'json')">导出 JSON</a>
          </div>
        </div>
        <ScoreRadar :items="report.score.items" />
      </section>

      <section v-if="report.warnings?.length" class="warn-block">
        <h2>提示</h2>
        <ul class="plain-list">
          <li v-for="(warning, i) in report.warnings" :key="i">{{ warning }}</li>
        </ul>
      </section>

      <section id="sec-scores" class="block">
        <h2>分项分数</h2>
        <div class="bars">
          <div v-for="item in report.score.items" :key="item.key" class="bar">
            <b>{{ item.name }}</b>
            <div class="track"><i :style="{ width: grown ? ratio(item) + '%' : 0 }" /></div>
            <span class="v">{{ scoreText(item) }}</span>
            <ul v-if="item.reasons?.length">
              <li v-for="(reason, i) in item.reasons" :key="i">{{ reason }}</li>
            </ul>
          </div>
        </div>
      </section>

      <section id="sec-features" class="block">
        <h2>功能点</h2>
        <div class="feats">
          <div v-for="feature in report.features" :key="feature.feature_id" class="feat">
            <span class="st" :class="feature.status">{{ FEATURE_STATUS[feature.status] }}</span>
            <b>{{ FEATURE_NAMES[feature.feature_id] || feature.feature_id }}</b>
            <p>{{ feature.reason }}</p>
            <div>
              <button
                v-for="loc in feature.locations"
                :key="loc.path + loc.line"
                class="linkish"
                type="button"
                @click="openSource(loc.path, loc.line)"
              >
                {{ loc.path }}:{{ loc.line }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section id="sec-defects" class="block">
        <h2>缺陷清单<span class="count">{{ defects.length }} 条，点开看讲解和改法</span></h2>
        <p v-if="!defects.length" class="hint">没有发现缺陷。</p>
        <div class="defects">
          <article v-for="row in defects" :key="row.index" class="defect" :class="{ open: openDefects.has(row.index) }">
            <button class="head" type="button" :aria-expanded="openDefects.has(row.index)" @click="toggleDefect(row.index)">
              <span class="sev" :class="'s-' + row.defect.severity">{{ row.defect.severity }}</span>
              <span>{{ row.defect.title }}</span>
              <span class="loc">{{ row.defect.path }}:{{ row.defect.line }}</span>
              <svg class="arrow" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 3l5 5-5 5" /></svg>
            </button>
            <div class="body">
              <div>
                <div class="inner">
                  <p>{{ row.defect.description }}</p>
                  <div class="kp">
                    <b>知识点：{{ KNOWLEDGE_NAMES[row.defect.knowledge_category] || row.defect.knowledge_category }}</b><br />
                    {{ row.defect.knowledge }}
                  </div>
                  <p>建议：{{ row.defect.suggestion }}</p>
                  <div v-if="row.defect.before || row.defect.after" class="diff-cols">
                    <figure>
                      <figcaption>原来</figcaption>
                      <pre class="mono">{{ row.defect.before || '（无）' }}</pre>
                    </figure>
                    <figure class="after">
                      <figcaption>建议改成</figcaption>
                      <pre class="mono">{{ row.defect.after || '（无）' }}</pre>
                    </figure>
                  </div>
                  <div class="foot">
                    <span class="hint">{{ row.defect.type_name }}，来源 {{ row.defect.source }}<template v-if="row.defect.in_baseline_unchanged">，参考代码原有，不扣分</template><template v-else-if="row.defect.in_student_change">，出现在学生改动里</template></span>
                    <button class="linkish" type="button" @click="openSource(row.defect.path, row.defect.line)">看源码</button>
                    <button class="linkish" type="button" @click="pickDefect(row)">就这条追问</button>
                  </div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section id="sec-build" class="block">
        <h2>编译与运行</h2>
        <p v-if="fragment" class="hint">只提交了代码片段，没有编译运行。</p>
        <template v-else>
          <p v-if="report.build">
            编译<span class="badge" :class="report.build.status">{{ STATUS_LABEL[report.build.status] || report.build.status }}</span>
            警告 {{ report.build.warnings }} 条，错误 {{ report.build.errors }} 个
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
          <pre v-if="logOpen" class="mono" style="margin-top: 10px">{{ report.build.log_tail }}</pre>
          <template v-if="report.run">
            <p>
              运行<span class="badge" :class="report.run.status">{{ STATUS_LABEL[report.run.status] || report.run.status }}</span>
              <template v-if="report.run.shell_prompt">提示符 {{ report.run.shell_prompt }}</template>
            </p>
            <h3>启动输出</h3>
            <pre class="mono">{{ report.run.boot_output || '（无输出）' }}</pre>
            <template v-for="cmd in report.run.commands" :key="cmd.evidence_id">
              <h3>$ {{ cmd.command }}</h3>
              <pre class="mono">{{ cmd.output }}</pre>
            </template>
          </template>
        </template>
      </section>

      <section id="sec-style" class="block">
        <h2>规范与创新</h2>
        <p>规范：{{ STYLE_GRADE[report.style.grade] }}。{{ report.style.reason }}</p>
        <p>学生声称的创新：{{ report.innovation.claimed || '（无）' }}</p>
        <p>
          {{ report.innovation.found_in_code ? '代码中能找到对应实现。' : '代码中没找到对应实现。' }}
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

      <section id="sec-diff" class="block">
        <h2>参考代码对比</h2>
        <template v-if="report.diff && report.diff.status === 'passed'">
          <p>基线 {{ report.diff.baseline || '未选定' }}：相同 {{ report.diff.same }} 个，修改 {{ report.diff.modified }} 个，新增 {{ report.diff.added }} 个文件</p>
          <ul class="plain-list">
            <li v-for="file in changedFiles" :key="file.path">
              {{ file.change === 'added' ? '新增' : '修改' }} <span class="loc">{{ file.path }}</span>
              （+{{ file.added_lines }} / −{{ file.removed_lines }}）
            </li>
          </ul>
        </template>
        <p v-else class="hint">{{ report.diff?.note || '没有可用的参考代码对比' }}</p>
      </section>

      <section id="sec-tools" class="block">
        <h2>工具调用过程</h2>
        <ToolTimeline :events="report.tool_calls" />
        <div class="btn-row">
          <button class="btn ghost" type="button" @click="thoughtsOpen = !thoughtsOpen">
            {{ thoughtsOpen ? '收起智能体思考' : '展开智能体思考' }}
          </button>
        </div>
        <ol v-if="thoughtsOpen" class="thoughts" style="margin-top: 12px">
          <li v-for="thought in report.agent_thoughts" :key="thought.id">
            <strong>第 {{ thought.position }} 轮 {{ thought.tool || '思考' }}</strong>
            <p>{{ thought.thought || '（无）' }}</p>
            <p v-if="thought.observation" class="hint">观察：{{ thought.observation }}</p>
          </li>
        </ol>
      </section>

      <section id="followup-box" class="block">
        <h2>追问</h2>
        <p class="hint">
          可以就某条缺陷提问，也可以直接问。回答不会改分数。
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
            <span v-if="asking" class="spinner" aria-hidden="true" />{{ asking ? '智能体正在回答…' : '发送追问' }}
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
    </div>

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

