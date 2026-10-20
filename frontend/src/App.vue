<template>
  <div id="app" class="min-h-screen bg-white">
    <Header v-if="route.name !== 'ChatRecommend'" />
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
</template>

<script setup>
import Header from './components/Header.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

