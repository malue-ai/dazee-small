/**
 * 文档浏览 API
 */

import api from './index'

/**
 * 文档文件
 */
export interface DocFile {
  name: string
  path: string
  title: string
}

/**
 * 文档分类
 */
export interface DocCategory {
  id: string
  name: string
  icon: string
  description: string
  files: DocFile[]
}

/**
 * 文档结构
 */
export interface DocsStructure {
  categories: DocCategory[]
  total_files: number
}

/**
 * 文档内容
 */
export interface DocContent {
  path: string
  title: string
  content: string
  category: string
}

/**
 * 获取文档目录结构
 */
export async function getDocsStructure(): Promise<DocsStructure> {
  const response = await api.get<{ success: boolean; data: DocsStructure }>('/v1/docs/structure')
  return response.data.data
}

/**
 * 获取文档内容
 * @param docPath - 文档路径
 */
export async function getDocContent(docPath: string): Promise<DocContent> {
  const response = await api.get<{ success: boolean; data: DocContent }>(`/v1/docs/content/${docPath}`)
  return response.data.data
}
