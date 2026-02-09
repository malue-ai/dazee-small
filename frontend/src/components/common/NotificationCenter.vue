<template>
  <Teleport to="body">
    <TransitionGroup
      tag="div"
      class="fixed top-4 right-4 z-[9999] flex flex-col gap-3 pointer-events-none"
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 translate-x-8 scale-95"
      enter-to-class="opacity-100 translate-x-0 scale-100"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-x-0 scale-100"
      leave-to-class="opacity-0 translate-x-8 scale-95"
    >
      <div
        v-for="item in visibleItems"
        :key="item.id"
        class="pointer-events-auto w-80 rounded-2xl border border-border bg-white/90 backdrop-blur-xl shadow-lg overflow-hidden"
      >
        <!-- Header -->
        <div class="flex items-center gap-3 px-4 pt-3.5 pb-2">
          <!-- Status icon -->
          <div
            class="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
            :class="iconBgClass(item.type)"
          >
            <Loader2 v-if="item.type === 'progress'" class="w-4 h-4 animate-spin" />
            <CheckCircle v-else-if="item.type === 'success'" class="w-4 h-4" />
            <AlertCircle v-else-if="item.type === 'error'" class="w-4 h-4" />
            <MessageSquare v-else-if="item.type === 'message'" class="w-4 h-4" />
            <Info v-else class="w-4 h-4" />
          </div>

          <!-- Text -->
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-foreground truncate">{{ item.title }}</p>
            <p v-if="item.message" class="text-xs text-muted-foreground truncate">{{ item.message }}</p>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-1 flex-shrink-0">
            <!-- Action button -->
            <button
              v-if="item.action"
              @click="handleAction(item)"
              class="px-2.5 py-1 text-xs font-medium rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors shadow-sm shadow-primary/20"
            >
              {{ item.action.label }}
            </button>
            <!-- Dismiss -->
            <button
              @click="handleDismiss(item.id)"
              class="p-1 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- Progress bar (type=progress only) -->
        <div v-if="item.type === 'progress' && item.progress" class="px-4 pb-3.5">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[11px] text-muted-foreground">{{ item.message }}</span>
            <span class="text-[11px] text-muted-foreground tabular-nums">
              {{ item.progress.step }}/{{ item.progress.total }}
            </span>
          </div>
          <div class="w-full h-1 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              :style="{ width: progressPercent(item.progress) }"
            />
          </div>
        </div>

        <!-- Bottom padding for non-progress types with no message -->
        <div v-else-if="!item.message" class="pb-1.5" />
      </div>
    </TransitionGroup>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Loader2,
  CheckCircle,
  AlertCircle,
  MessageSquare,
  Info,
  X,
} from 'lucide-vue-next'
import {
  useNotificationStore,
  type NotificationType,
  type NotificationItem,
  type NotificationProgress,
} from '@/stores/notification'

const router = useRouter()
const store = useNotificationStore()

const visibleItems = computed(() => store.visibleItems)

function iconBgClass(type: NotificationType): string {
  switch (type) {
    case 'progress':
      return 'bg-primary/10 text-primary'
    case 'success':
      return 'bg-success/10 text-success'
    case 'error':
      return 'bg-destructive/10 text-destructive'
    case 'message':
      return 'bg-primary/10 text-primary'
    case 'info':
      return 'bg-muted text-muted-foreground'
  }
}

function progressPercent(progress: NotificationProgress): string {
  if (progress.total === 0) return '0%'
  return `${Math.round((progress.step / progress.total) * 100)}%`
}

function handleAction(item: NotificationItem): void {
  if (!item.action) return
  if (item.action.handler) item.action.handler()
  if (item.action.route) router.push(item.action.route)
  store.dismiss(item.id)
}

function handleDismiss(id: string): void {
  store.dismiss(id)
}
</script>
