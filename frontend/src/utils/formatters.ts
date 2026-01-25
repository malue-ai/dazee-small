/**
 * 格式化工具函数
 */

/**
 * 格式化文件大小
 * @param bytes - 文件大小（字节）
 * @returns 格式化后的字符串
 */
export function formatFileSize(bytes: number | undefined | null): string {
  if (!bytes || bytes === 0) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

/**
 * 格式化短时间（用于会话列表）
 * @param dateStr - 日期字符串或 Date 对象
 * @returns 格式化后的相对时间
 */
export function formatShortTime(dateStr: string | Date | undefined | null): string {
  if (!dateStr) return ''
  
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  // 小于 1 分钟
  if (diff < 60000) return '刚刚'
  // 小于 1 小时
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm'
  // 小于 24 小时
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h'
  // 小于 7 天
  if (diff < 604800000) return Math.floor(diff / 86400000) + 'd'
  // 超过 7 天显示日期
  return (date.getMonth() + 1) + '/' + date.getDate()
}

/**
 * 格式化完整时间
 * @param dateStr - 日期字符串或 Date 对象
 * @returns 格式化后的完整时间
 */
export function formatFullTime(dateStr: string | Date | undefined | null): string {
  if (!dateStr) return ''
  
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr
  
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

/**
 * 格式化相对时间
 * @param dateStr - 日期字符串或 Date 对象
 * @returns 相对时间描述
 */
export function formatRelativeTime(dateStr: string | Date | undefined | null): string {
  if (!dateStr) return ''
  
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  const weeks = Math.floor(days / 7)
  const months = Math.floor(days / 30)
  
  if (seconds < 60) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  if (weeks < 4) return `${weeks} 周前`
  if (months < 12) return `${months} 个月前`
  
  return formatFullTime(date)
}

/**
 * 格式化 JSON 数据
 * @param data - 要格式化的数据
 * @param indent - 缩进空格数
 * @returns 格式化后的 JSON 字符串
 */
export function formatJson(data: unknown, indent = 2): string {
  if (data === null || data === undefined) return ''
  
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data)
      return JSON.stringify(parsed, null, indent)
    } catch {
      return data
    }
  }
  
  try {
    return JSON.stringify(data, null, indent)
  } catch {
    return String(data)
  }
}

/**
 * 截断文本
 * @param text - 原文本
 * @param maxLength - 最大长度
 * @param suffix - 后缀
 * @returns 截断后的文本
 */
export function truncateText(text: string, maxLength: number, suffix = '...'): string {
  if (!text || text.length <= maxLength) return text || ''
  return text.slice(0, maxLength - suffix.length) + suffix
}

/**
 * 格式化持续时间
 * @param ms - 毫秒数
 * @returns 格式化后的持续时间
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  }
  return `${seconds}s`
}

/**
 * 格式化数字（添加千分位）
 * @param num - 数字
 * @returns 格式化后的数字字符串
 */
export function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN')
}

/**
 * 格式化百分比
 * @param value - 小数值
 * @param decimals - 小数位数
 * @returns 格式化后的百分比
 */
export function formatPercent(value: number, decimals = 1): string {
  return (value * 100).toFixed(decimals) + '%'
}
