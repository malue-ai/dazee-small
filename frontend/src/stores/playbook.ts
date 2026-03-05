import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PlaybookEntry, PlaybookStatus, PlaybookCreateRequest, PlaybookUpdateRequest } from '@/types'
import {
  getPlaybooks,
  getPlaybook,
  createPlaybook,
  updatePlaybook,
  deletePlaybook,
  playbookAction,
  rebuildPlaybookIndex,
} from '@/api/playbook'

export const usePlaybookStore = defineStore('playbook', () => {
  const entries = ref<PlaybookEntry[]>([])
  const selectedEntry = ref<PlaybookEntry | null>(null)
  const statusFilter = ref<PlaybookStatus | 'all'>('all')
  const loading = ref(false)
  const actionLoading = ref(false)
  const stats = ref<Record<string, unknown>>({})

  const filteredEntries = computed(() => {
    if (statusFilter.value === 'all') return entries.value
    return entries.value.filter(e => e.status === statusFilter.value)
  })

  const isEmpty = computed(() => filteredEntries.value.length === 0 && !loading.value)

  const statusCounts = computed(() => {
    const counts: Record<string, number> = { all: entries.value.length }
    for (const e of entries.value) {
      counts[e.status] = (counts[e.status] || 0) + 1
    }
    return counts
  })

  async function fetchEntries() {
    loading.value = true
    try {
      const data = await getPlaybooks()
      entries.value = data.entries
      stats.value = data.stats
    } catch (e) {
      console.error('Failed to fetch playbooks:', e)
    } finally {
      loading.value = false
    }
  }

  async function selectEntry(entry: PlaybookEntry | null) {
    if (!entry) {
      selectedEntry.value = null
      return
    }
    try {
      selectedEntry.value = await getPlaybook(entry.id)
    } catch {
      selectedEntry.value = entry
    }
  }

  async function addEntry(data: PlaybookCreateRequest): Promise<PlaybookEntry | null> {
    actionLoading.value = true
    try {
      const entry = await createPlaybook(data)
      await fetchEntries()
      return entry
    } catch (e) {
      console.error('Failed to create playbook:', e)
      return null
    } finally {
      actionLoading.value = false
    }
  }

  async function editEntry(id: string, data: PlaybookUpdateRequest): Promise<boolean> {
    actionLoading.value = true
    try {
      const updated = await updatePlaybook(id, data)
      await fetchEntries()
      if (selectedEntry.value?.id === id) {
        selectedEntry.value = updated
      }
      return true
    } catch (e) {
      console.error('Failed to update playbook:', e)
      return false
    } finally {
      actionLoading.value = false
    }
  }

  async function removeEntry(id: string): Promise<boolean> {
    actionLoading.value = true
    try {
      await deletePlaybook(id)
      if (selectedEntry.value?.id === id) selectedEntry.value = null
      await fetchEntries()
      return true
    } catch (e) {
      console.error('Failed to delete playbook:', e)
      return false
    } finally {
      actionLoading.value = false
    }
  }

  async function changeStatus(
    id: string,
    action: 'approve' | 'reject' | 'dismiss' | 'deprecate',
    notes?: string
  ): Promise<boolean> {
    actionLoading.value = true
    try {
      await playbookAction(id, action, notes)
      await fetchEntries()
      if (selectedEntry.value?.id === id) {
        if (action === 'dismiss') {
          selectedEntry.value = null
        } else {
          try { selectedEntry.value = await getPlaybook(id) } catch { selectedEntry.value = null }
        }
      }
      return true
    } catch (e) {
      console.error(`Failed to ${action} playbook:`, e)
      return false
    } finally {
      actionLoading.value = false
    }
  }

  async function rebuildIndex(): Promise<{ cleared: number; indexed: number } | null> {
    actionLoading.value = true
    try {
      const result = await rebuildPlaybookIndex()
      return { cleared: result.cleared, indexed: result.indexed }
    } catch (e) {
      console.error('Failed to rebuild index:', e)
      return null
    } finally {
      actionLoading.value = false
    }
  }

  function setStatusFilter(status: PlaybookStatus | 'all') {
    statusFilter.value = status
  }

  return {
    entries,
    selectedEntry,
    statusFilter,
    loading,
    actionLoading,
    stats,
    filteredEntries,
    isEmpty,
    statusCounts,
    fetchEntries,
    selectEntry,
    addEntry,
    editEntry,
    removeEntry,
    changeStatus,
    rebuildIndex,
    setStatusFilter,
  }
})
