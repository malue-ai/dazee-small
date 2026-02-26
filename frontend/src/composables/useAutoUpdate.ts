/**
 * 自动更新 composable
 *
 * 启动时静默检查 Tauri updater endpoint，发现新版本后
 * 通过响应式状态驱动 UI 弹窗，用户确认即下载安装并重启。
 */

import { ref, readonly } from 'vue'
import { check, type Update } from '@tauri-apps/plugin-updater'
import { relaunch } from '@tauri-apps/plugin-process'

export type UpdatePhase = 'idle' | 'checking' | 'found' | 'downloading' | 'installing' | 'error'

export function useAutoUpdate() {
  const phase = ref<UpdatePhase>('idle')
  const newVersion = ref('')
  const changelog = ref('')
  const downloadProgress = ref(0) // 0–100
  const errorMessage = ref('')

  let pendingUpdate: Update | null = null

  /**
   * 检查更新（静默模式不弹错误，手动模式会暴露错误）
   */
  async function checkForUpdates(silent = true): Promise<boolean> {
    if (phase.value === 'downloading' || phase.value === 'installing') return false

    phase.value = 'checking'
    errorMessage.value = ''

    try {
      const update = await check()

      if (update) {
        pendingUpdate = update
        newVersion.value = update.version
        changelog.value = update.body ?? ''
        phase.value = 'found'
        return true
      }

      phase.value = 'idle'
      return false
    } catch (err) {
      console.warn('[auto-update] check failed:', err)
      errorMessage.value = err instanceof Error ? err.message : String(err)
      phase.value = silent ? 'idle' : 'error'
      return false
    }
  }

  /**
   * 用户确认后执行下载 + 安装 + 重启
   */
  async function downloadAndInstall() {
    if (!pendingUpdate) return

    phase.value = 'downloading'
    downloadProgress.value = 0

    try {
      let totalBytes = 0
      let downloadedBytes = 0

      await pendingUpdate.downloadAndInstall((event) => {
        switch (event.event) {
          case 'Started':
            totalBytes = event.data.contentLength ?? 0
            break
          case 'Progress':
            downloadedBytes += event.data.chunkLength
            downloadProgress.value = totalBytes > 0
              ? Math.min(Math.round((downloadedBytes / totalBytes) * 100), 100)
              : 0
            break
          case 'Finished':
            downloadProgress.value = 100
            break
        }
      })

      phase.value = 'installing'
      await relaunch()
    } catch (err) {
      console.error('[auto-update] download/install failed:', err)
      errorMessage.value = err instanceof Error ? err.message : String(err)
      phase.value = 'error'
    }
  }

  function dismiss() {
    if (phase.value === 'downloading' || phase.value === 'installing') return
    phase.value = 'idle'
    pendingUpdate = null
  }

  return {
    phase: readonly(phase),
    newVersion: readonly(newVersion),
    changelog: readonly(changelog),
    downloadProgress: readonly(downloadProgress),
    errorMessage: readonly(errorMessage),

    checkForUpdates,
    downloadAndInstall,
    dismiss,
  }
}
