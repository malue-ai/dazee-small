<template>
  <div class="markdown-body">
    <MarkdownRender
      :content="content || ''"
      :enable-mermaid="true"
      :final="final"
      :max-live-nodes="0"
      :render-batch-size="16"
      :render-batch-delay="8"
    />
  </div>
</template>

<script setup lang="ts">
import MarkdownRender from 'markstream-vue'

withDefaults(defineProps<{
  /** Markdown 文本内容 */
  content: string
  /** 流式输出是否已结束（结束后设为 true，让渲染器正确处理未闭合语法） */
  final?: boolean
}>(), {
  final: false,
})
</script>

<style>
.markdown-body {
  line-height: 1.6;
  color: var(--color-foreground);
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
  color: var(--color-foreground);
}

.markdown-body h1 {
  font-size: 1.8em;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.3em;
}

.markdown-body h2 {
  font-size: 1.4em;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.3em;
}

.markdown-body p {
  margin-bottom: 16px;
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
  color: var(--color-muted-foreground);
  border-left: 0.25em solid var(--color-border);
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
  border: 1px solid var(--color-border);
}

.markdown-body table tr {
  background-color: transparent;
  border-top: 1px solid var(--color-border);
}

.markdown-body table tr:nth-child(2n) {
  background-color: var(--color-muted);
}

.markdown-body a {
  color: var(--color-primary);
  text-decoration: none;
  word-break: break-all;
}

.markdown-body a:hover {
  text-decoration: underline;
  color: var(--color-primary-hover);
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
</style>
