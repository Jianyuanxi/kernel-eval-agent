/** 网页接口封装：一律用相对路径 /api，部署后由 nginx 同域转发。 */

export const ERROR_HINTS = {
  UPLOAD_TOO_LARGE: '上传或解压后超过大小限制（上传 20MB）',
  UPLOAD_BAD_TYPE: '只支持一个 .zip，或 1–50 个 .c/.h 文件',
  UPLOAD_BAD_ZIP: '压缩包损坏或已加密',
  UPLOAD_UNSAFE_PATH: '压缩包里有不安全的路径或符号链接',
  NO_SOURCE_FOUND: '解压后找不到任何 .c 文件',
  TASK_NOT_FOUND: '找不到这个任务，请重新上传',
  PROJECT_NOT_FOUND: '找不到选中的工程',
  TASK_STATE_CONFLICT: '任务当前状态不允许这个操作',
  REQUEST_INVALID: '请求参数不合法',
  PATH_INVALID: '源码路径无效',
  RESULT_NOT_READY: '报告还没生成',
  SANDBOX_ERROR: '评测沙箱出错',
  AGENT_ERROR: '智能体评测出错',
  AGENT_TIMEOUT: '智能体评测超时',
  AGENT_SKIPPED_TOOLS: '智能体未调用必需工具',
  REVIEW_INVALID: '智能体输出不符合约定',
  INTERNAL_ERROR: '服务器内部错误',
}

export function formatError(error, fallback = '请求失败') {
  if (!error) return fallback
  const hint = ERROR_HINTS[error.code]
  if (hint && error.message) return `${hint}（${error.message}）`
  return error.message || hint || fallback
}

async function parseBody(res) {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { error: { code: 'INTERNAL_ERROR', message: text.slice(0, 200) } }
  }
}

async function request(path, options = {}) {
  const res = await fetch(path, options)
  const data = await parseBody(res)
  if (!res.ok) {
    const err = data?.error || { code: 'INTERNAL_ERROR', message: `HTTP ${res.status}` }
    throw err
  }
  return data
}

export function createTask(files) {
  const body = new FormData()
  for (const f of files) body.append('files', f)
  return request('/api/tasks', { method: 'POST', body })
}

export function getTask(taskId) {
  return request(`/api/tasks/${encodeURIComponent(taskId)}`)
}

export function startTask(taskId, projectId) {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId }),
  })
}

export function getEvents(taskId, after = 0) {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/events?after=${after}`)
}

export function getReport(taskId) {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/report`)
}
