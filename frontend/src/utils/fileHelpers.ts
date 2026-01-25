/**
 * 文件处理工具函数
 */

import type { CodeLanguage } from '@/types'

/**
 * 根据 MIME 类型获取文件图标
 * @param mimeType - MIME 类型
 * @returns 图标 emoji
 */
export function getFileIcon(mimeType: string | undefined): string {
  if (!mimeType) return '📎'
  
  const type = mimeType.toLowerCase()
  
  if (type.startsWith('image/')) return '🖼️'
  if (type === 'application/pdf') return '📄'
  if (type.includes('text/')) return '📝'
  if (type.includes('json')) return '📋'
  if (type.includes('spreadsheet') || type.includes('excel') || type === 'text/csv') return '📊'
  if (type.includes('presentation') || type.includes('powerpoint')) return '📑'
  if (type.includes('word') || type.includes('document')) return '📄'
  if (type.includes('zip') || type.includes('compressed') || type.includes('archive')) return '📦'
  if (type.includes('video/')) return '🎬'
  if (type.includes('audio/')) return '🎵'
  
  return '📎'
}

/**
 * 根据 MIME 类型获取文件类型标签
 * @param mimeType - MIME 类型
 * @returns 类型标签
 */
export function getFileTypeLabel(mimeType: string | undefined): string {
  if (!mimeType) return 'File'
  
  const type = mimeType.toLowerCase()
  
  if (type.startsWith('image/')) {
    if (type.includes('png')) return 'PNG'
    if (type.includes('jpeg') || type.includes('jpg')) return 'JPEG'
    if (type.includes('gif')) return 'GIF'
    if (type.includes('webp')) return 'WebP'
    if (type.includes('svg')) return 'SVG'
    return 'Image'
  }
  
  if (type === 'application/pdf') return 'PDF'
  if (type === 'text/plain') return 'Text'
  if (type === 'text/markdown') return 'Markdown'
  if (type === 'text/csv') return 'CSV'
  if (type === 'text/html') return 'HTML'
  if (type.includes('json')) return 'JSON'
  if (type.includes('xml')) return 'XML'
  if (type.includes('javascript')) return 'JavaScript'
  if (type.includes('typescript')) return 'TypeScript'
  if (type.includes('python')) return 'Python'
  
  if (type.includes('spreadsheet') || type.includes('excel')) return 'Excel'
  if (type.includes('presentation') || type.includes('powerpoint')) return 'PPT'
  if (type.includes('word') || type.includes('document')) return 'Word'
  if (type.includes('zip')) return 'ZIP'
  
  return 'File'
}

/**
 * 判断是否为图片文件
 * @param mimeType - MIME 类型
 * @returns 是否为图片
 */
export function isImageFile(mimeType: string | undefined): boolean {
  if (!mimeType) return false
  return mimeType.toLowerCase().startsWith('image/')
}

/**
 * 判断是否为视频文件
 * @param mimeType - MIME 类型
 * @returns 是否为视频
 */
export function isVideoFile(mimeType: string | undefined): boolean {
  if (!mimeType) return false
  return mimeType.toLowerCase().startsWith('video/')
}

/**
 * 判断是否为音频文件
 * @param mimeType - MIME 类型
 * @returns 是否为音频
 */
export function isAudioFile(mimeType: string | undefined): boolean {
  if (!mimeType) return false
  return mimeType.toLowerCase().startsWith('audio/')
}

/**
 * 判断是否为文本文件（可预览）
 * @param mimeType - MIME 类型
 * @returns 是否为文本
 */
export function isTextFile(mimeType: string | undefined): boolean {
  if (!mimeType) return false
  
  const type = mimeType.toLowerCase()
  return (
    type.startsWith('text/') ||
    type.includes('json') ||
    type.includes('xml') ||
    type.includes('javascript') ||
    type.includes('typescript')
  )
}

/**
 * 根据文件扩展名获取 MIME 类型
 * @param filename - 文件名
 * @returns MIME 类型
 */
export function getMimeType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  
  const mimeMap: Record<string, string> = {
    // 图片
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'svg': 'image/svg+xml',
    'ico': 'image/x-icon',
    
    // 文档
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'ppt': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    
    // 文本
    'txt': 'text/plain',
    'md': 'text/markdown',
    'csv': 'text/csv',
    'html': 'text/html',
    'css': 'text/css',
    'xml': 'text/xml',
    
    // 代码
    'js': 'text/javascript',
    'ts': 'text/typescript',
    'jsx': 'text/javascript',
    'tsx': 'text/typescript',
    'vue': 'text/x-vue',
    'py': 'text/x-python',
    'java': 'text/x-java',
    'go': 'text/x-go',
    'rs': 'text/x-rust',
    'c': 'text/x-c',
    'cpp': 'text/x-c++',
    'h': 'text/x-c',
    'hpp': 'text/x-c++',
    'sh': 'text/x-shellscript',
    'sql': 'text/x-sql',
    
    // 数据
    'json': 'application/json',
    'yaml': 'text/yaml',
    'yml': 'text/yaml',
    
    // 压缩
    'zip': 'application/zip',
    'tar': 'application/x-tar',
    'gz': 'application/gzip',
    'rar': 'application/vnd.rar',
    
    // 视频
    'mp4': 'video/mp4',
    'webm': 'video/webm',
    'avi': 'video/x-msvideo',
    'mov': 'video/quicktime',
    
    // 音频
    'mp3': 'audio/mpeg',
    'wav': 'audio/wav',
    'ogg': 'audio/ogg',
    'm4a': 'audio/mp4'
  }
  
  return mimeMap[ext || ''] || 'application/octet-stream'
}

/**
 * 根据文件路径检测代码语言
 * @param filePath - 文件路径
 * @returns 代码语言
 */
export function detectLanguage(filePath: string | undefined | null): CodeLanguage {
  if (!filePath) return 'text'
  
  const ext = filePath.split('.').pop()?.toLowerCase()
  
  const languageMap: Record<string, CodeLanguage> = {
    'py': 'python',
    'js': 'javascript',
    'ts': 'typescript',
    'jsx': 'javascript',
    'tsx': 'typescript',
    'vue': 'vue',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'json': 'json',
    'md': 'markdown',
    'yaml': 'yaml',
    'yml': 'yaml',
    'sh': 'bash',
    'bash': 'bash',
    'sql': 'sql',
    'xml': 'xml',
    'java': 'java',
    'go': 'go',
    'rs': 'rust',
    'c': 'c',
    'cpp': 'cpp',
    'h': 'c',
    'hpp': 'cpp'
  }
  
  return languageMap[ext || ''] || 'text'
}

/**
 * 从路径中提取文件名
 * @param path - 文件路径
 * @returns 文件名
 */
export function getFileName(path: string): string {
  return path.split('/').pop() || path
}

/**
 * 从路径中提取目录路径
 * @param path - 文件路径
 * @returns 目录路径
 */
export function getDirPath(path: string): string {
  const parts = path.split('/')
  parts.pop()
  return parts.join('/') || '/'
}

/**
 * 获取文件扩展名
 * @param filename - 文件名
 * @returns 扩展名（不含点）
 */
export function getExtension(filename: string): string {
  const ext = filename.split('.').pop()
  return ext === filename ? '' : ext || ''
}

/**
 * 检查文件名是否有效
 * @param filename - 文件名
 * @returns 是否有效
 */
export function isValidFilename(filename: string): boolean {
  if (!filename || filename.length === 0) return false
  if (filename.length > 255) return false
  
  // 检查非法字符
  const invalidChars = /[<>:"/\\|?*\x00-\x1f]/
  if (invalidChars.test(filename)) return false
  
  // 检查保留名称（Windows）
  const reserved = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i
  if (reserved.test(filename.split('.')[0])) return false
  
  return true
}
