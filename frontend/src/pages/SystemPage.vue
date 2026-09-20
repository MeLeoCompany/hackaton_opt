<script setup>
// Параметры системы: к чему подключён бэкенд, что сейчас настроено и сколько чего заведено.
// Только для администратора; данные приходят одним запросом и обновляются по кнопке.
import { computed, onMounted } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import { useSystemInfo } from '../composables/useSystemInfo.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import { formatDay, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'

const { info, loading, errorMessage, errorDetails, load } = useSystemInfo()
const { now, shifted } = useSystemTime()

function moment(isoString) {
  return isoString ? `${formatDay(moscowDateOf(isoString))} ${moscowTimeOf(isoString)}` : '—'
}

const clock = computed(() => moment(now.value.toISOString()))
const realClock = computed(() => moment(info.value?.time.real_now))

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Система</h1>
      <p>Подключения, настройки и объёмы данных · время московское</p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading && !info" class="muted">Загружаю параметры…</p>

    <template v-else-if="info">
      <section class="cards">
        <article class="card">
          <h2>Приложение</h2>
          <dl>
            <div><dt>Название</dt><dd>{{ info.app_name }}</dd></div>
            <div><dt>Версия</dt><dd>{{ info.version }}</dd></div>
            <div><dt>Python</dt><dd>{{ info.python_version }}</dd></div>
          </dl>
        </article>

        <article :class="['card', { warn: shifted }]">
          <h2>Системное время</h2>
          <dl>
            <div><dt>Сейчас в системе</dt><dd>{{ clock }}</dd></div>
            <div><dt>Настоящее время</dt><dd>{{ realClock }}</dd></div>
            <div v-if="shifted"><dt>Перемотал</dt><dd>{{ info.time.updated_by ?? '—' }}</dd></div>
          </dl>
          <p class="note">
            <template v-if="shifted">Время перемотано для демонстрации — часы вверху жёлтые.</template>
            <template v-else>Время настоящее. Перемотать можно кликом по часам в правом верхнем углу.</template>
          </p>
        </article>
      </section>

      <h2 class="section-title">Подключения</h2>
      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 260px" />
            <col />
            <col style="width: 320px" />
          </colgroup>
          <thead>
            <tr><th>Служба</th><th>Адрес</th><th>Состояние</th></tr>
          </thead>
          <tbody>
            <tr v-for="service in info.services" :key="service.name">
              <td>{{ service.name }}</td>
              <td class="target">{{ service.target }}</td>
              <td>
                <span :class="['badge', service.ok ? 'ok' : 'fail']">{{ service.ok ? 'работает' : 'не отвечает' }}</span>
                <span class="detail">{{ service.detail }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 class="section-title">Настройки расчёта</h2>
      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 320px" />
            <col />
          </colgroup>
          <thead>
            <tr><th>Параметр</th><th>Значение</th></tr>
          </thead>
          <tbody>
            <tr v-for="(value, name) in info.settings" :key="name">
              <td>{{ name }}</td>
              <td class="target">{{ value }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 class="section-title">Данные</h2>
      <div class="counts">
        <article v-for="(count, name) in info.data" :key="name" class="count">
          <strong>{{ count }}</strong>
          <span>{{ name }}</span>
        </article>
      </div>

      <p class="muted">
        <button class="link" :disabled="loading" @click="load">{{ loading ? 'Обновляю…' : 'Обновить' }}</button>
      </p>
    </template>
  </div>
</template>

<style scoped>
/* рабочая область — колонка flex: таблицы иначе сжимаются и обрезают строки */
.table-scroll {
  flex: none;
}

/* таблицы короткие: общий минимум ширины широких таблиц им не нужен */
.data-table.fixed-columns {
  min-width: 0;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.card {
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.card.warn {
  border-color: #fcd34d;
  background: #fffbeb;
}

.card h2,
.section-title {
  margin: 0 0 8px;
  font-size: 15px;
}

.section-title {
  margin-top: 18px;
}

dl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  font-size: 14px;
}

dl > div {
  display: flex;
  gap: 10px;
}

dt {
  flex-shrink: 0;
  width: 150px;
  color: #64748b;
}

dd {
  margin: 0;
}

.note {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 12px;
}

.target {
  color: #334155;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  white-space: normal;
  word-break: break-all;
}

.badge.ok {
  background: #dcfce7;
  color: #166534;
}

.badge.fail {
  background: #fee2e2;
  color: #b91c1c;
}

.detail {
  margin-left: 8px;
  color: #64748b;
  font-size: 12px;
}

.counts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.count {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.count strong {
  font-size: 20px;
}

.count span {
  color: #64748b;
  font-size: 12px;
}
</style>
