import api from './index'
import type { ApiResponse, LoginRequest, LoginResponse, User } from '@/types'

/**
 * 用户登录
 */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await api.post<LoginResponse>('/v1/auth/login', data)
  return response.data
}

/**
 * 获取当前用户信息
 */
export async function getCurrentUser(): Promise<User> {
  const response = await api.get<User>('/v1/auth/me')
  return response.data
}

/**
 * 用户登出
 */
export async function logout(): Promise<void> {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

