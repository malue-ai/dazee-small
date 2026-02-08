<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="show"
        class="fixed inset-0 bg-foreground/50 backdrop-blur-sm z-[9999] flex items-center justify-center p-6"
        @click.self="handleCancel"
      >
        <div class="bg-card rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden animate-in slide-in-from-bottom-4 duration-200">
          <!-- 图标 + 内容 -->
          <div class="px-6 pt-6 pb-4 text-center">
            <!-- 警告图标 -->
            <div
              v-if="type === 'warning' || type === 'confirm'"
              class="w-12 h-12 mx-auto mb-4 rounded-full flex items-center justify-center"
              :class="type === 'warning' ? 'bg-red-50' : 'bg-amber-50'"
            >
              <AlertTriangle
                class="w-6 h-6"
                :class="type === 'warning' ? 'text-red-500' : 'text-amber-500'"
              />
            </div>
            <!-- 信息图标 -->
            <div v-else-if="type === 'info'" class="w-12 h-12 mx-auto mb-4 rounded-full bg-primary/10 flex items-center justify-center">
              <Info class="w-6 h-6 text-primary" />
            </div>
            <!-- 错误图标 -->
            <div v-else-if="type === 'error'" class="w-12 h-12 mx-auto mb-4 rounded-full bg-red-50 flex items-center justify-center">
              <XCircle class="w-6 h-6 text-red-500" />
            </div>

            <h3 class="text-base font-semibold text-foreground mb-2">{{ title }}</h3>
            <p class="text-sm text-muted-foreground leading-relaxed">{{ message }}</p>
          </div>

          <!-- 按钮 -->
          <div class="px-6 pb-6 flex gap-3" :class="showCancel ? 'justify-between' : 'justify-center'">
            <button
              v-if="showCancel"
              @click="handleCancel"
              class="flex-1 px-4 py-2.5 text-sm font-medium text-muted-foreground bg-muted rounded-xl hover:bg-muted/80 transition-colors"
            >
              {{ cancelText }}
            </button>
            <button
              @click="handleConfirm"
              class="flex-1 px-4 py-2.5 text-sm font-medium text-white rounded-xl transition-colors"
              :class="confirmButtonClass"
            >
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, Info, XCircle } from 'lucide-vue-next'

interface Props {
  show: boolean
  title?: string
  message: string
  type?: 'confirm' | 'warning' | 'info' | 'error'
  confirmText?: string
  cancelText?: string
  showCancel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '确认操作',
  type: 'confirm',
  confirmText: '确定',
  cancelText: '取消',
  showCancel: true,
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const confirmButtonClass = computed(() => {
  switch (props.type) {
    case 'warning':
    case 'error':
      return 'bg-red-500 hover:bg-red-600'
    default:
      return 'bg-primary hover:bg-primary-hover'
  }
})

function handleConfirm() {
  emit('confirm')
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
