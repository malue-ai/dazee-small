<template>
  <section class="stats">
    <div class="stat-item" v-for="stat in stats" :key="stat.label">
      <div class="stat-number">{{ stat.value }}</div>
      <div class="stat-label">{{ stat.label }}</div>
    </div>
  </section>
</template>

<script setup>
const stats = [
  { value: '14,209', label: '档案总数' },
  { value: '98.7%', label: '数字化比例' },
  { value: '156', label: '合作机构' }
]
</script>

<style scoped>
.stats {
  display: flex;
  justify-content: center;
  gap: 80px;
  padding: 60px 20px;
}
.stat-item { text-align: center; }
.stat-number {
  font-size: 3rem;
  font-family: 'SF Mono', monospace;
  color: #d4af37;
}
.stat-label {
  font-size: 0.9rem;
  opacity: 0.6;
  margin-top: 10px;
}
</style>
