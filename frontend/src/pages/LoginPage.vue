<script setup>
// Вход по логину и паролю. Учётки заводит администратор в «Справочники» -> «Пользователи».
// Слева — название и схема маршрута, справа — форма; на узком экране панель уходит наверх.
import { ref } from 'vue'

import { useAuth } from '../composables/useAuth.js'

const { login } = useAuth()

const loginName = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const busy = ref(false)

async function submit() {
  if (!loginName.value.trim() || !password.value) return
  busy.value = true
  error.value = ''
  try {
    await login(loginName.value.trim(), password.value)
  } catch (failure) {
    error.value = failure.message
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-screen">
    <div class="login-frame">
      <section class="brand" aria-hidden="true">
        <div class="brand-text">
          <span class="brand-mark">➤</span>
          <h1>Планирование выездов</h1>
          <p>Маршруты бригад на день</p>
        </div>

        <!-- схема маршрута: офис, заявки по порядку и путь между ними -->
        <svg class="route-art" viewBox="0 0 320 200" role="presentation">
          <path
            class="route-line"
            d="M40 160 C 80 150, 90 100, 130 104 S 190 150, 220 110 S 250 40, 290 46"
          />
          <rect class="office" x="30" y="150" width="20" height="20" rx="4" />
          <circle class="stop" cx="130" cy="104" r="9" />
          <circle class="stop" cx="220" cy="110" r="9" />
          <circle class="stop last" cx="290" cy="46" r="11" />
          <text x="130" y="108">1</text>
          <text x="220" y="114">2</text>
          <text x="290" y="50">3</text>
        </svg>
      </section>

      <form class="login-form" @submit.prevent="submit">
        <h2>Вход</h2>

        <label class="field">
          <span>Логин</span>
          <input
            v-model="loginName"
            autocomplete="username"
            autofocus
            spellcheck="false"
            :disabled="busy"
            @input="error = ''"
          />
        </label>

        <label class="field">
          <span>Пароль</span>
          <span class="password">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              :disabled="busy"
              @input="error = ''"
            />
            <button
              type="button"
              class="reveal"
              :title="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
              :aria-label="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
              @click="showPassword = !showPassword"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
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

        <p v-if="error" class="login-error" role="alert">{{ error }}</p>

        <button class="submit" type="submit" :disabled="busy || !loginName.trim() || !password">
          <span v-if="busy" class="spinner" aria-hidden="true"></span>
          {{ busy ? 'Вхожу…' : 'Войти' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 16px;
  background:
    radial-gradient(circle at 15% 20%, #dbeafe 0, transparent 45%),
    radial-gradient(circle at 85% 80%, #e0e7ff 0, transparent 40%),
    #f1f5f9;
}

.login-frame {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  width: min(820px, 100%);
  overflow: hidden;
  border-radius: 18px;
  background: #fff;
  box-shadow:
    0 24px 60px rgb(15 23 42 / 14%),
    0 2px 6px rgb(15 23 42 / 6%);
}

/* ---- левая панель ---- */
.brand {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 24px;
  padding: 36px 32px;
  background: linear-gradient(145deg, #1d4ed8 0%, #2563eb 55%, #3b82f6 100%);
  color: #fff;
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin-bottom: 16px;
  border-radius: 12px;
  background: rgb(255 255 255 / 18%);
  font-size: 18px;
}

.brand h1 {
  margin: 0;
  font-size: 24px;
  line-height: 1.25;
}

.brand p {
  margin: 8px 0 0;
  color: rgb(255 255 255 / 80%);
  font-size: 14px;
}

.route-art {
  width: 100%;
  height: auto;
}

.route-line {
  fill: none;
  stroke: rgb(255 255 255 / 85%);
  stroke-dasharray: 7 7;
  stroke-linecap: round;
  stroke-width: 3;
  animation: route-move 1.6s linear infinite;
}

.office {
  fill: #fff;
}

.stop {
  fill: #1d4ed8;
  stroke: #fff;
  stroke-width: 3;
}

.stop.last {
  fill: #fff;
  stroke: rgb(255 255 255 / 45%);
  stroke-width: 6;
}

.route-art text {
  fill: #fff;
  font-size: 10px;
  font-weight: 700;
  text-anchor: middle;
}

.route-art text:last-of-type {
  fill: #1d4ed8;
}

@keyframes route-move {
  to {
    stroke-dashoffset: -28;
  }
}

@media (prefers-reduced-motion: reduce) {
  .route-line {
    animation: none;
  }
}

/* ---- форма ---- */
.login-form {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 16px;
  padding: 40px 36px;
}

.login-form h2 {
  margin: 0 0 4px;
  color: #0f172a;
  font-size: 22px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #475569;
  font-size: 13px;
  font-weight: 600;
}

.field input {
  width: 100%;
  height: 42px;
  padding: 0 12px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #f8fafc;
  color: #0f172a;
  font-size: 15px;
  font-weight: 400;
  transition:
    border-color 0.15s,
    box-shadow 0.15s,
    background 0.15s;
}

.field input:focus {
  border-color: #2563eb;
  outline: none;
  background: #fff;
  box-shadow: 0 0 0 3px rgb(37 99 235 / 15%);
}

.password {
  position: relative;
  display: block;
}

.password input {
  padding-right: 44px;
}

.reveal {
  position: absolute;
  top: 50%;
  right: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: none;
  color: #64748b;
  transform: translateY(-50%);
}

.reveal:hover {
  background: #eef2f7;
  color: #1d4ed8;
}

.login-error {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
}

.submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 44px;
  margin-top: 4px;
  border: none;
  border-radius: 10px;
  background: #2563eb;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  transition: background 0.15s;
}

.submit:hover:not(:disabled) {
  background: #1d4ed8;
}

.submit:disabled {
  background: #93c5fd;
  cursor: default;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgb(255 255 255 / 45%);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* узкий экран: панель сверху, без схемы маршрута */
@media (max-width: 680px) {
  .login-frame {
    grid-template-columns: 1fr;
  }

  .brand {
    padding: 24px;
  }

  .route-art {
    display: none;
  }

  .login-form {
    padding: 28px 24px;
  }
}
</style>
