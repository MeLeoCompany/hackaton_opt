<script setup>
// Приложение бригады. На телефоне — во весь экран; на компьютере (для показа) — в рамке
// телефона посередине страницы.
import { onMounted } from 'vue'

import LoginScreen from './components/LoginScreen.vue'
import RouteScreen from './components/RouteScreen.vue'
import { useBrigade } from './useBrigade.js'

const { user, noticeMessage, restore } = useBrigade()

onMounted(restore)
</script>

<template>
  <div class="stage">
    <div class="phone">
      <div class="phone-screen">
        <RouteScreen v-if="user" />
        <LoginScreen v-else />
        <Transition name="toast">
          <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stage {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: radial-gradient(circle at 30% 20%, #374151, #111827 70%);
}

/* рамка телефона — только на широком экране, на самом телефоне приложение во весь экран */
.phone {
  width: 390px;
  height: min(844px, calc(100vh - 40px));
  padding: 12px;
  border-radius: 48px;
  background: #0b0f17;
  box-shadow:
    0 0 0 2px #374151,
    0 30px 80px rgb(0 0 0 / 55%);
}

.phone-screen {
  position: relative;
  height: 100%;
  overflow: auto;
  border-radius: 36px;
  background: #f3f4f6;
}

@media (max-width: 500px) {
  .stage {
    display: block;
    background: #f3f4f6;
  }

  .phone {
    width: auto;
    height: 100vh;
    padding: 0;
    border-radius: 0;
    background: none;
    box-shadow: none;
  }

  .phone-screen {
    border-radius: 0;
  }
}

.toast {
  position: sticky;
  bottom: 16px;
  z-index: 30;
  margin: 0 16px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #111827;
  color: #fff;
  font-size: 14px;
  text-align: center;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
}
</style>
