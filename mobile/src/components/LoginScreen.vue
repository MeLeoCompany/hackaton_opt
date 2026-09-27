<script setup>
// Вход бригады: логин и пароль задаются в справочнике бригад диспетчерской.
import { ref } from 'vue'

import { useBrigade } from '../useBrigade.js'

const { signIn, busy, errorMessage } = useBrigade()
const loginName = ref('')
const password = ref('')
const showPassword = ref(false)
</script>

<template>
  <div class="login">
    <div class="brand">
      <span class="brand-mark">Б</span>
      <strong>Маршрут бригады</strong>
    </div>

    <form @submit.prevent="signIn(loginName.trim(), password)">
      <label>
        <span>Логин</span>
        <input v-model="loginName" autocomplete="username" autocapitalize="off" required />
      </label>
      <label>
        <span>Пароль</span>
        <span class="password">
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            required
          />
          <!-- глазок внутри поля: как на входе диспетчера, кнопка со словом ела полстроки -->
          <button
            type="button"
            class="reveal"
            :title="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
            :aria-label="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
            @click="showPassword = !showPassword"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path
                d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              />
              <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8" />
              <path v-if="showPassword" d="M4 4l16 16" stroke="currentColor" stroke-width="1.8" />
            </svg>
          </button>
        </span>
      </label>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <button type="submit" class="primary big" :disabled="busy">{{ busy ? 'Входим…' : 'Войти' }}</button>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  flex-direction: column;
  gap: 14px;
  justify-content: center;
  min-height: 100%;
  padding: 24px 20px;
  background: #111827;
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  font-size: 18px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: #fcd535;
  color: #111827;
  font-weight: 800;
}

form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 30px rgb(17 24 39 / 12%);
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #4b5563;
}

.password {
  position: relative;
  display: flex;
}

.password input {
  flex: 1;
  min-width: 0;
  /* место под глазок, иначе длинный пароль уезжает под кнопку */
  padding-right: 46px;
}

.reveal {
  position: absolute;
  top: 50%;
  right: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: none;
  color: #94a3b8;
  transform: translateY(-50%);
}

.reveal:active {
  color: #e5e7eb;
}

.error {
  margin: 0;
  color: #b91c1c;
  font-size: 14px;
}
</style>
