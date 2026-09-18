<script setup>
// Вкладка загрузки заявок из CSV: файл, шаблон и разбор ошибок по строкам.
import RequestsCsvImport from '../components/RequestsCsvImport.vue'
import { useRequestsImport } from '../composables/useRequestsImport.js'

const { saving, lastReport, errorMessage, errorDetails, noticeMessage, importCsv, downloadTemplate } =
  useRequestsImport()
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Загрузка CSV</h1>
      <p>Заявки из файла · время в файле без часового пояса считается московским</p>
    </header>

    <RequestsCsvImport :busy="saving" @import="importCsv" @download-template="downloadTemplate" />

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

    <p v-if="lastReport" class="muted">
      Последняя загрузка: добавлено {{ lastReport.created }}, обновлено {{ lastReport.updated }}.
      Заявки смотрите на вкладке «Заявки» — не забудьте выбрать нужный день.
    </p>

    <section class="format">
      <h2>Что должно быть в файле</h2>
      <ul>
        <li><strong>адрес, широта, долгота</strong> — обязательны;</li>
        <li><strong>тип_работ</strong> — из справочника нормативов; задаёт навык, а «длительность_мин» можно
          не заполнять: возьмётся норматив работы на месте;</li>
        <li><strong>окно_начало, окно_конец</strong> — «17.08.2026 10:00» или «2026-08-17T10:00»;</li>
        <li><strong>приоритет</strong> — «Обычная» или «Срочная» (можно номером);</li>
        <li><strong>транспорт</strong> — если для заявки нужен конкретный, иначе пусто;</li>
        <li><strong>активна</strong> — «да» или «нет»; пусто у новой заявки значит «да»;</li>
        <li><strong>оборудование</strong> — что и сколько привезти: «Роутер: 2, ТВ-приставка» (без количества —
          одна штука), пусто — ничего; нет колонки — у существующих заявок требование не меняется;</li>
        <li><strong>id</strong> — номер заявки из внешней системы; пусто — номер присвоится сам.</li>
      </ul>
      <p class="muted">Скачайте шаблон — в нём есть все колонки и две строки-примера.</p>
    </section>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.format h2 {
  margin: 0 0 6px;
  font-size: 15px;
}

.format ul {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.format p {
  margin: 8px 0 0;
}
</style>
