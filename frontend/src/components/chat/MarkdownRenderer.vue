<template>
  <div class="markdown-body" ref="markdownRef" v-html="renderedHtml"></div>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import mermaid from 'mermaid'

const props = defineProps({
  content: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['mermaid-detected'])

const markdownRef = ref(null)

// 初始化 Mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'system-ui, -apple-system, sans-serif'
})

// 自定义 marked renderer 处理 mermaid 代码块
const renderer = new marked.Renderer()

// marked v5+ 使用对象参数 { text, lang }，旧版本使用 (code, language)
renderer.code = function(codeOrObj, language) {
  // 兼容新旧版本的 marked
  const code = typeof codeOrObj === 'object' ? codeOrObj.text : codeOrObj
  const lang = typeof codeOrObj === 'object' ? codeOrObj.lang : language
  
  if (lang === 'mermaid') {
    // 返回一个带有特殊类的 div，稍后会被 mermaid 渲染
    const id = 'mermaid-' + Math.random().toString(36).substr(2, 9)
    return `<div class="mermaid-container"><pre class="mermaid" id="${id}">${code}</pre></div>`
  }
  
  // 普通代码高亮
  if (lang && hljs.getLanguage(lang)) {
    try {
      return `<pre><code class="hljs language-${lang}">${hljs.highlight(code, { language: lang }).value}</code></pre>`
    } catch (err) {}
  }
  return `<pre><code class="hljs">${hljs.highlightAuto(code).value}</code></pre>`
}

marked.setOptions({
  renderer,
  breaks: true,
  gfm: true
})

const renderedHtml = computed(() => {
  try {
    return marked(props.content || '')
  } catch (error) {
    return props.content
  }
})

// 提取 mermaid 代码（使用更健壮的正则）
function extractMermaidCode(content) {
  if (!content) return []
  
  // 匹配 ```mermaid 代码块，支持 \n 或 \r\n
  const regex = /```mermaid\s*[\r\n]+([\s\S]*?)```/gi
  const matches = []
  let match
  
  while ((match = regex.exec(content)) !== null) {
    const code = match[1].trim()
    if (code) {
      matches.push(code)
    }
  }
  
  return matches
}

// 渲染 Mermaid 图表
async function renderMermaid() {
  await nextTick()
  if (!markdownRef.value) return
  
  const mermaidElements = markdownRef.value.querySelectorAll('.mermaid')
  if (mermaidElements.length === 0) return
  
  try {
    await mermaid.run({
      nodes: mermaidElements
    })
  } catch (error) {
    console.warn('Mermaid 渲染失败:', error)
  }
}

// 检测并通知 mermaid 图表
function detectAndEmitMermaid() {
  const charts = extractMermaidCode(props.content)
  if (charts.length > 0) {
    emit('mermaid-detected', charts)
  }
}

// 监听内容变化，重新渲染 mermaid
watch(() => props.content, async (newContent, oldContent) => {
  // 只有当内容实际变化且有值时才处理
  if (!newContent) return
  
  await renderMermaid()
  detectAndEmitMermaid()
}, { immediate: true })

onMounted(async () => {
  if (props.content) {
    await renderMermaid()
    detectAndEmitMermaid()
  }
})
</script>

<style>
/* 导入 highlight.js 浅色主题 */
@import 'highlight.js/styles/github.css';

.markdown-body {
  line-height: 1.6;
  color: #374151;
  font-size: 15px;
  max-width: 100%;
  overflow-wrap: break-word;
  word-break: break-word;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4,
.markdown-body h5,
.markdown-body h6 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
  color: #111827;
}

.markdown-body h1 {
  font-size: 1.8em;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 0.3em;
}

.markdown-body h2 {
  font-size: 1.4em;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 0.3em;
}

.markdown-body p {
  margin-bottom: 16px;
}

.markdown-body code {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 85%;
  background-color: #f3f4f6;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  color: #1f2937;
}

.markdown-body pre {
  padding: 16px;
  overflow-x: auto;
  overflow-y: hidden;
  font-size: 85%;
  line-height: 1.45;
  background-color: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  margin-bottom: 16px;
  max-width: 100%;
}

.markdown-body pre code {
  display: inline;
  padding: 0;
  margin: 0;
  overflow: visible;
  line-height: inherit;
  word-wrap: normal;
  background-color: transparent;
  border: 0;
}

.markdown-body ul,
.markdown-body ol {
  padding-left: 2em;
  margin-bottom: 16px;
}

.markdown-body li {
  margin-bottom: 4px;
}

.markdown-body blockquote {
  padding: 0 1em;
  color: #6b7280;
  border-left: 0.25em solid #e5e7eb;
  margin: 0 0 16px 0;
}

.markdown-body table {
  border-spacing: 0;
  border-collapse: collapse;
  margin-bottom: 16px;
  width: 100%;
}

.markdown-body table th,
.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid #e5e7eb;
}

.markdown-body table tr {
  background-color: #fff;
  border-top: 1px solid #e5e7eb;
}

.markdown-body table tr:nth-child(2n) {
  background-color: #f9fafb;
}

.markdown-body a {
  color: #2563eb;
  text-decoration: none;
  word-break: break-all;
}

.markdown-body a:hover {
  text-decoration: underline;
}

/* 长文本/URL 强制换行 */
.markdown-body p,
.markdown-body li,
.markdown-body td {
  word-break: break-word;
  overflow-wrap: anywhere;
}

.markdown-body img {
  max-width: 100%;
  box-sizing: content-box;
  border-radius: 6px;
}

/* Mermaid 容器样式 */
.mermaid-container {
  margin: 16px 0;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  overflow-x: auto;
}

.mermaid-container .mermaid {
  display: flex;
  justify-content: center;
}

.mermaid-container svg {
  max-width: 100%;
  height: auto;
}
</style>
