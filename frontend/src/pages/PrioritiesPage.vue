<script setup>
// Справочник «Приоритеты»: три уровня приоритета и уровень по умолчанию для каждого типа работ.
// Уровень по умолчанию подставляется новой заявке (в форме и при загрузке CSV без приоритета);
// в заявке его можно сменить. Меняет соответствие администратор, диспетчер только смотрит.
import { onMounted } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import { useAuth } from '../composables/useAuth.js'
import { usePriorities } from '../composables/usePriorities.js'
import { priorityBadgeClass, referenceName } from '../utils/referenceNames.js'

const { references, loading, savingId, errorMessage, errorDetails, noticeMessage, load, changePriority } =
  usePriorities()

const { isAdmin } = useAuth()

// что уровень значит для плана — коротко, одной строкой
const LEVEL_MEANING = {
  1: 'Берутся в план первыми. Новая аварийная заявка — повод пересчитать утверждённый план',
  2: 'Следом за аварийными',
  3: 'В оставшееся время бригад',
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Приоритеты</h1>
      <p>
        Уровни приоритета заявок и уровень по умолчанию для типа работ<template v-if="isAdmin">
          · правка меняет только подстановку в новых заявках</template
        >
      </p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю приоритеты…</p>

    <template v-else>
      <div class="levels">
        <div
          v-for="priority in references.priorities"
          :key="priority.id"
          :class="['level-card', `level-${priority.level}`]"
        >
          <span class="level-number">{{ priority.level }}</span>
          <div>
            <span :class="priorityBadgeClass(references, priority.id)">{{ priority.name }}</span>
            <p>{{ LEVEL_MEANING[priority.level] ?? '' }}</p>
          </div>
        </div>
      </div>

      <h2 class="section-title">Уровень по умолчанию для типа работ</h2>
      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col />
            <col style="width: 280px" />
            <col style="width: 200px" />
          </colgroup>
          <thead>
            <tr>
              <th>Тип работ</th>
              <th>Навык</th>
              <th>Уровень приоритета</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="workType in references.work_types" :key="workType.id">
              <td>{{ workType.name }}</td>
              <td>
                {{ referenceName(references, 'skills', workType.skill_id) }}
              </td>
              <td>
                <select
                  v-if="isAdmin"
                  :value="workType.priority_id"
                  :disabled="savingId !== null"
                  aria-label="уровень приоритета по умолчанию"
                  @change="changePriority(workType, $event.target.value)"
                >
                  <option v-for="priority in references.priorities" :key="priority.id" :value="priority.id">
                    {{ priority.level }} · {{ priority.name }}
                  </option>
                </select>
                <span v-else :class="priorityBadgeClass(references, workType.priority_id)">
                  {{ referenceName(references, 'priorities', workType.priority_id) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">
        {{ noticeMessage }}
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.section-title {
  margin: 18px 0 8px;
  font-size: 15px;
}

.levels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.level-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
}

.level-card.level-1 {
  border-left-color: #dc2626;
}

.level-card.level-2 {
  border-left-color: #f97316;
}

.level-number {
  color: #94a3b8;
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
}

.level-card p {
  margin: 6px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.4;
}

/* таблица короткая — общий минимум ширины широких таблиц ей не нужен */
.data-table.fixed-columns {
  min-width: 0;
}

select {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
}
</style>
