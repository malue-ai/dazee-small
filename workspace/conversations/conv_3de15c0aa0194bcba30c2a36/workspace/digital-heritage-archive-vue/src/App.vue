<template>
  <div class="app">
    <Header />
    <main>
      <StatsSection />
    </main>
  </div>
</template>

<script setup>
import Header from './components/Header.vue'
import StatsSection from './components/StatsSection.vue'
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Noto Serif SC', serif;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  min-height: 100vh;
  color: #e5e5e5;
}
</style>

