/**
 * 前后端共享的常量定义
 * 
 * 在前端使用：import { COOKIE_NAME } from '@shared/const'
 * 在后端使用：import { COOKIE_NAME } from '../shared/const.js'
 */

/**
 * Cookie 名称 - 用于存储用户会话
 */
export const COOKIE_NAME = "session_token";

/**
 * 一年的毫秒数 - 常用于设置 Cookie 过期时间
 */
export const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;

/**
 * 一天的毫秒数
 */
export const ONE_DAY_MS = 24 * 60 * 60 * 1000;

/**
 * 一小时的毫秒数
 */
export const ONE_HOUR_MS = 60 * 60 * 1000;

/**
 * API 请求超时时间（毫秒）
 */
export const API_TIMEOUT_MS = 10000;

/**
 * 分页默认值
 */
export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;
