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
          <button type="button" class="ghost" @click="showPassword = !showPassword">
            {{ showPassword ? 'Скрыть' : 'Показать' }}
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
  display: flex;
  gap: 8px;
}

.password input {
  flex: 1;
  min-width: 0;
}

.error {
  margin: 0;
  color: #b91c1c;
  font-size: 14px;
}
</style>
