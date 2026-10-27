<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { createTask, formatError } from '../api'

const router = useRouter()
const input = ref(null)
const files = ref([])
const drag = ref(false)
const loading = ref(false)
const error = ref('')

const MAX = 20 * 1024 * 1024

function setFiles(list) {
  files.value = Array.from(list || [])
  error.value = ''
}

function onDrop(e) {
  drag.value = false
  setFiles(e.dataTransfer.files)
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
  <section class="card">
    <h1>上传内核工程</h1>
    <p class="lead">拖入一个 zip 作业包，或选择若干 .c / .h 文件。单个上传不超过 20MB。</p>

    <div
      class="dropzone"
      :class="{ drag }"
      @dragenter.prevent="drag = true"
      @dragover.prevent="drag = true"
      @dragleave.prevent="drag = false"
      @drop.prevent="onDrop"
      @click="input.click()"
    >
      <strong>拖到此处，或点击选择文件</strong>
      <p class="hint">大小限制 20MB · 字段名 files</p>
      <input
        ref="input"
        type="file"
        multiple
        accept=".zip,.c,.h,application/zip"
        hidden
        @change="setFiles($event.target.files)"
      />
    </div>

    <ul v-if="files.length" class="file-list">
      <li v-for="f in files" :key="f.name">{{ f.name }}（{{ (f.size / 1024).toFixed(1) }} KB）</li>
    </ul>

    <div class="btn-row">
      <button class="btn" :disabled="loading" @click="submit">
        {{ loading ? '正在整理…' : '开始评测' }}
      </button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
  </section>
</template>
