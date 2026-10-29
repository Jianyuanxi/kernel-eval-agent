import { Marked } from 'marked'

/** 转义文本和属性，避免回答中的 HTML 被浏览器执行。 */
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char])
}

/** 只允许网页和邮件链接，拒绝脚本、data 和其他协议。 */
function safeUrl(href) {
  if (!/^(https?:|mailto:)/i.test(href)) return null
  try {
    return new URL(href).href
  } catch {
    return null
  }
}

const markdown = new Marked({
  breaks: true,
  gfm: true,
  renderer: {
    html({ text }) { return escapeHtml(text) },
    link({ href, tokens }) {
      const label = this.parser.parseInline(tokens)
      const url = safeUrl(href)
      return url ? `<a href="${escapeHtml(url)}">${label}</a>` : label
    },
    image({ href, text }) {
      const url = safeUrl(href)
      return url && /^https?:/i.test(url)
        ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(text)}">`
        : escapeHtml(text)
    },
  },
})

/** 将追问回答渲染为仅含受控 Markdown 标签的 HTML。 */
export function renderAnswer(text) {
  return markdown.parse(text || '')
}
