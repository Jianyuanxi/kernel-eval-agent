<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createTask, formatError } from '../api'

const router = useRouter()
const input = ref(null)
const files = ref([])
const drag = ref(false)
const loading = ref(false)
const error = ref('')

const MAX = 20 * 1024 * 1024

const pickedName = computed(() =>
  files.value.length === 1 ? files.value[0].name : `${files.value.length} 个源文件`,
)
const pickedSize = computed(() => {
  const kb = files.value.reduce((s, f) => s + f.size, 0) / 1024
  return kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(1)} KB`
})
const pickedKind = computed(() => (files.value.length === 1 && /\.zip$/i.test(files.value[0].name) ? 'ZIP' : 'C'))

function setFiles(list) {
  files.value = Array.from(list || [])
  error.value = validate(files.value)
  if (error.value) files.value = []
}

function onDrop(e) {
  drag.value = false
  setFiles(e.dataTransfer.files)
}

/** 清空已选文件，回到拖放框；同时重置 input，再选同一个文件也会触发 change。 */
function reset() {
  files.value = []
  error.value = ''
  if (input.value) input.value.value = ''
}

function validate(list) {
  if (!list.length) return '请选择一个 .zip，或多个 .c/.h 文件'
  const names = list.map((f) => f.name.toLowerCase())
  const zip = names.length === 1 && names[0].endsWith('.zip')
  const sources = names.every((n) => n.endsWith('.c') || n.endsWith('.h'))
  if (!zip && !sources) return '只支持一个 .zip，或 1–50 个 .c/.h 文件'
  if (!zip && names.length > 50) return '零散源文件最多 50 个'
  const total = list.reduce((s, f) => s + f.size, 0)
  if (total > MAX) return '上传文件超过 20MB'
  return ''
}

async function submit() {
  const msg = validate(files.value)
  if (msg) {
    error.value = msg
    return
  }
  loading.value = true
  error.value = ''
  try {
    const task = await createTask(files.value)
    if (task.stage === 'failed') {
      error.value = formatError(task.error, '上传失败')
      return
    }
    router.push({ name: 'task', params: { id: task.task_id } })
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="upload">
    <div>
      <h1>上传一份内核作业，<br />几分钟后拿到评测报告</h1>
      <p class="lead">支持整份 zip 作业包，也可以只选几个 .c / .h 文件。系统会在沙箱里编译、在 QEMU 里启动，再交给智能体逐行评审。</p>

      <input ref="input" type="file" multiple accept=".zip,.c,.h,application/zip" hidden @change="setFiles($event.target.files)" />
      <div
        v-if="!files.length"
        class="dropzone"
        :class="{ drag }"
        role="button"
        tabindex="0"
        @dragenter.prevent="drag = true"
        @dragover.prevent="drag = true"
        @dragleave.prevent="drag = false"
        @drop.prevent="onDrop"
        @click="input.click()"
        @keydown.enter.prevent="input.click()"
        @keydown.space.prevent="input.click()"
      >
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="#56636f" stroke-width="2" aria-hidden="true">
          <path d="M20 26V8M12 15l8-8 8 8" /><path d="M6 26v6h28v-6" />
        </svg>
        <strong>把 zip 拖到这里，或点击选择</strong>
        <span>一个 zip，或 1–50 个 .c/.h 文件，总共不超过 20MB</span>
      </div>
      <div v-else class="picked">
        <svg width="34" height="40" viewBox="0 0 34 40" aria-hidden="true">
          <path d="M2 2h20l10 10v26H2z" fill="#dfe5fb" stroke="#2847d8" stroke-width="2" />
          <text x="17" y="30" text-anchor="middle" font-size="9" font-weight="700" fill="#2847d8">{{ pickedKind }}</text>
        </svg>
        <div class="grow">
          <div class="name">{{ pickedName }}</div>
          <div class="size">{{ pickedSize }}，选好了，点下面开始</div>
        </div>
        <button class="change" type="button" :disabled="loading" @click="reset">换一个</button>
      </div>

      <div class="actions">
        <button class="btn" :disabled="loading || !files.length" @click="submit">
          <span v-if="loading" class="spinner" aria-hidden="true" />{{ loading ? '正在上传…' : '开始评测' }}
        </button>
        <span class="note">{{ files.length ? '通常需要 2–4 分钟' : '先选择文件' }}</span>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <ol class="steps">
      <li><b>编译并启动</b><span>按工程自带的 CMake 编译，在 QEMU 里跑 20 秒，自动输入 shell 命令</span></li>
      <li><b>静态扫描</b><span>clang 静态分析，并和参考代码逐文件对比，找出改了哪些地方</span></li>
      <li><b>智能体评审</b><span>读源码、查操作系统知识库，给出缺陷、讲解和修改建议</span></li>
      <li><b>按规则打分</b><span>编译运行、功能、可靠性、规范四项，总分 100</span></li>
    </ol>
  </section>
</template>
