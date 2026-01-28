/**
 * 前后端共享的类型定义
 * 
 * 在前端使用：import type { Item } from '@shared/types'
 * 在后端使用：import type { Item } from '../shared/types.js'
 */

// 示例类型 - 根据业务需求修改
export interface Item {
  id: string
  title: string
  status: 'pending' | 'completed'
  createdAt: string
}

export interface CreateItemDto {
  title: string
}

export interface UpdateItemDto {
  title?: string
  status?: 'pending' | 'completed'
}

// API 响应类型
export interface ApiResponse<T> {
  data: T
}

export interface ApiError {
  error: string
}