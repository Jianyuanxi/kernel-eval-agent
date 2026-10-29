import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import { ref, computed } from 'vue'
import * as labels from '../src/labels.js'
import { renderAnswer } from '../src/markdown.js'

/** 编译真实组件脚本，替换接口和计时器以复现慢请求及乱序响应。 */
function setupView(name, props, overrides = {}) {
  const { descriptor } = parse(readFileSync(new URL(`../src/views/${name}.vue`, import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'review-test', genDefaultAs: 'component' }).content
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*$/gm, '')
  const timers = new Map()
  let timerId = 0
  const deps = {
    ref, computed, onMounted() {}, onUnmounted() {}, watch() {},
    setTimeout(callback) { timers.set(++timerId, callback); return timerId },
    clearTimeout(id) { timers.delete(id) },
    getTask: async () => ({ stage: 'queued', projects: [] }),
    getEvents: async () => ({ stage: 'building', tool_calls: [] }),
    getReport: async () => ({ task_id: props.id }),
    startTask: async () => ({ stage: 'queued', projects: [] }),
    formatError: (error) => error.message,
    ToolTimeline: {}, ReportView: {}, ScoreRadar: {}, SourceDrawer: {},
    exportHref() {}, getSource() {}, postFollowup() {}, renderAnswer,
    ...labels, ...overrides,
  }
  const component = new Function(...Object.keys(deps), `${script}; return component`)(...Object.values(deps))
  return { view: component.setup(props, { expose() {} }), timers }
}

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

/** 等待异步接口及其后续状态更新完成。 */
async function flush() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

test('Markdown 转义原始 HTML，拒绝危险链接和图片，同时保留安全格式', () => {
  const html = renderAnswer('<img src=x onerror=alert(1)>\n\n[x](javascript:alert%281%29)\n\n![x](data:text/html,evil)')
  assert.ok(html.includes('&lt;img'))
  assert.ok(!html.includes('<img'))
  assert.ok(!html.includes('href='))
  for (const href of ['JaVaScRiPt:alert(1)', 'javascript&#58;alert(1)', 'java&#x73;cript:alert(1)', 'vbscript:evil', 'file:///tmp/x']) {
    assert.ok(!renderAnswer(`[x](${href})`).includes('href='), href)
  }
  const safe = renderAnswer('**说明** [文档](https://example.com/?a=1&b=2)\n\n```c\n<img onerror=evil>\n```')
  assert.ok(safe.includes('<strong>说明</strong>'))
  assert.ok(safe.includes('href="https://example.com/?a=1&amp;b=2"'))
  assert.ok(safe.includes('&lt;img onerror=evil&gt;'))
})

test('单工程自动开始只请求一次事件，慢请求完成后才安排下次轮询', async () => {
  const response = deferred()
  let calls = 0
  const { view, timers } = setupView('TaskView', { id: 'task-a' }, {
    getTask: async () => ({ stage: 'waiting_select', projects: [{ project_id: 'p1' }] }),
    getEvents: () => { calls += 1; return response.promise },
  })
  await view.bootstrap()
  assert.equal(calls, 1)
  assert.equal(timers.size, 0)
  response.resolve({ stage: 'building', tool_calls: [{ seq: 1 }] })
  await flush()
  assert.equal(timers.size, 1)
  assert.deepEqual(view.events.value.map((event) => event.seq), [1])
})

test('切换任务后忽略旧事件响应，防止旧任务覆盖新任务', async () => {
  const old = deferred()
  const props = { id: 'task-a' }
  const { view, timers } = setupView('TaskView', props, {
    getEvents: (id) => id === 'task-a' ? old.promise : Promise.resolve({ stage: 'reviewing', tool_calls: [{ seq: 2 }] }),
  })
  await view.bootstrap()
  props.id = 'task-b'
  await view.bootstrap()
  await flush()
  old.resolve({ stage: 'building', tool_calls: [{ seq: 1 }] })
  await flush()
  assert.equal(view.task.value.stage, 'reviewing')
  assert.deepEqual(view.events.value.map((event) => event.seq), [2])
  assert.equal(timers.size, 1)
})

test('已完成任务报告加载失败后自动重试，成功后清除错误并停止轮询', async () => {
  let attempts = 0
  const { view, timers } = setupView('TaskView', { id: 'task-a' }, {
    getTask: async () => ({ stage: 'done', projects: [] }),
    getEvents: async () => ({ stage: 'done', tool_calls: [] }),
    getReport: async () => {
      if (++attempts === 1) throw new Error('临时网络错误')
      return { task_id: 'task-a' }
    },
  })
  await view.bootstrap()
  await flush()
  assert.equal(view.error.value, '临时网络错误')
  assert.equal(timers.size, 1)
  const [id, retry] = [...timers][0]
  timers.delete(id)
  await retry()
  assert.equal(view.report.value.task_id, 'task-a')
  assert.equal(view.error.value, '')
  assert.equal(timers.size, 0)
})

test('卸载后在途请求不会写入页面或重新创建计时器', async () => {
  const response = deferred()
  const { view, timers } = setupView('TaskView', { id: 'task-a' }, { getEvents: () => response.promise })
  await view.bootstrap()
  view.stop()
  response.resolve({ stage: 'done', tool_calls: [{ seq: 1 }] })
  await flush()
  assert.equal(view.report.value, null)
  assert.equal(view.events.value.length, 0)
  assert.equal(timers.size, 0)
})

test('追问期间切换缺陷，回答仍保留发送时的缺陷标题和索引', async () => {
  const response = deferred()
  let sent
  const { view } = setupView('ReportView', { taskId: 'task-a', report: {} }, {
    postFollowup: (...args) => { sent = args; return response.promise },
  })
  view.pickedDefect.value = { index: 0, defect: { title: '缺陷 A' } }
  view.question.value = '如何修复？'
  const pending = view.ask()
  view.pickedDefect.value = { index: 1, defect: { title: '缺陷 B' } }
  response.resolve({ answer: '**回答**', tool_calls: [] })
  await pending
  assert.deepEqual(sent, ['task-a', '如何修复？', 0])
  assert.equal(view.followups.value[0].defect, '缺陷 A')
})
