<template>
  <div class="mermaid-panel">
    <div v-if="charts.length === 0" class="empty-state">
      <div class="empty-icon">📊</div>
      <p>当前对话中没有图表</p>
      <p class="hint">使用 ```mermaid 代码块来创建流程图、时序图等</p>
    </div>
    
    <div v-else class="charts-container">
      <div 
        v-for="(chart, index) in charts" 
        :key="`chart-${index}-${chart.substring(0, 20)}`"
        class="chart-card"
        :class="{ active: activeIndex === index }"
        @click="activeIndex = index"
      >
        <div class="chart-header">
          <span class="chart-title">{{ getChartTitle(chart) }}</span>
          <span class="chart-index">#{{ index + 1 }}</span>
        </div>
        <div class="chart-body">
          <div 
            class="mermaid-render" 
            :ref="el => setChartRef(el, index)"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import mermaid from 'mermaid'

const props = defineProps({
  charts: {
    type: Array,
    default: () => []
  }
})

const activeIndex = ref(0)
const chartRefs = ref({})
const renderKey = ref(0)

// 初始化 Mermaid（只初始化一次）
let mermaidInitialized = false
function initMermaid() {
  if (mermaidInitialized) return
  mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: 'system-ui, -apple-system, sans-serif'
  })
  mermaidInitialized = true
}

// 设置 chart ref
function setChartRef(el, index) {
  if (el) {
    chartRefs.value[index] = el
  }
}

// 获取图表类型作为标题
function getChartTitle(code) {
  if (!code) return '图表'
  const firstLine = code.trim().split('\n')[0].toLowerCase()
  if (firstLine.includes('flowchart') || firstLine.includes('graph')) return '流程图'
  if (firstLine.includes('sequencediagram')) return '时序图'
  if (firstLine.includes('classdiagram')) return '类图'
  if (firstLine.includes('statediagram')) return '状态图'
  if (firstLine.includes('erdiagram')) return 'ER 图'
  if (firstLine.includes('gantt')) return '甘特图'
  if (firstLine.includes('pie')) return '饼图'
  if (firstLine.includes('mindmap')) return '思维导图'
  if (firstLine.includes('timeline')) return '时间线'
  if (firstLine.includes('gitgraph')) return 'Git 图'
  return '图表'
}

// 渲染单个图表
async function renderChart(index, code) {
  const element = chartRefs.value[index]
  if (!element || !code) return
  
  initMermaid()
  
  try {
    // 生成唯一 ID
    const id = `mermaid-panel-svg-${index}-${Date.now()}`
    
    // 使用 mermaid.render 生成 SVG
    const { svg } = await mermaid.render(id, code)
    element.innerHTML = svg
  } catch (error) {
    console.warn(`Mermaid 图表 ${index} 渲染失败:`, error)
    element.innerHTML = `
      <div class="render-error">
        <span class="error-icon">⚠️</span>
        <span class="error-text">图表渲染失败</span>
        <pre class="error-code">${escapeHtml(code.substring(0, 150))}${code.length > 150 ? '...' : ''}</pre>
      </div>
    `
  }
}

// HTML 转义
function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

// 渲染所有图表
async function renderAllCharts() {
  await nextTick()
  
  for (let i = 0; i < props.charts.length; i++) {
    await renderChart(i, props.charts[i])
  }
}

// 监听图表变化
watch(() => props.charts, async (newCharts, oldCharts) => {
  if (newCharts && newCharts.length > 0) {
    // 等待 DOM 更新
    await nextTick()
    // 再等一帧确保 ref 已设置
    requestAnimationFrame(async () => {
      await renderAllCharts()
    })
  }
}, { deep: true })

onMounted(async () => {
  if (props.charts.length > 0) {
    await nextTick()
    requestAnimationFrame(async () => {
      await renderAllCharts()
    })
  }
})
</script>

<style>
/* 不使用 scoped，让 mermaid SVG 样式生效 */
.mermaid-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.mermaid-panel .empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  padding: 24px;
  text-align: center;
}

.mermaid-panel .empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.mermaid-panel .empty-state p {
  margin: 4px 0;
}

.mermaid-panel .empty-state .hint {
  font-size: 12px;
  color: #d1d5db;
  margin-top: 8px;
}

.mermaid-panel .charts-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.mermaid-panel .chart-card {
  background: white;
  border-radius: 12px;
  margin-bottom: 12px;
  overflow: hidden;
  border: 2px solid transparent;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.mermaid-panel .chart-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.mermaid-panel .chart-card.active {
  border-color: #fbbf24;
}

.mermaid-panel .chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #f9fafb;
  border-bottom: 1px solid #f3f4f6;
}

.mermaid-panel .chart-title {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.mermaid-panel .chart-index {
  font-size: 11px;
  color: #9ca3af;
  background: #e5e7eb;
  padding: 2px 8px;
  border-radius: 10px;
}

.mermaid-panel .chart-body {
  padding: 16px;
  overflow: auto;
  min-height: 120px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #fafafa;
}

.mermaid-panel .mermaid-render {
  max-width: 100%;
  width: 100%;
}

.mermaid-panel .mermaid-render svg {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}

.mermaid-panel .render-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #ef4444;
  font-size: 13px;
  padding: 16px;
  text-align: center;
}

.mermaid-panel .error-icon {
  font-size: 24px;
}

.mermaid-panel .error-text {
  font-weight: 500;
}

.mermaid-panel .error-code {
  font-size: 11px;
  background: #fef2f2;
  padding: 8px 12px;
  border-radius: 6px;
  max-width: 100%;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: #991b1b;
  text-align: left;
  max-height: 100px;
}
</style>
