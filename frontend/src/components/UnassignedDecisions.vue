<script setup>
// Заявки, на которые не успеваем: что предложил второй расчёт и что ответил клиент.
// Решения живут в useUnassignedDecisions — здесь только их поля.
import { moscowTimeOf } from '../utils/moscowTime.js'
import TimeInput from './TimeInput.vue'

defineProps({
  title: { type: String, required: true },
  problems: { type: Array, required: true },
  decisions: { type: Object, required: true },
  tolerance: { type: Number, required: true },
  disabled: { type: Boolean, default: false },
})
</script>

<template>
  <section class="problems">
    <h4>{{ title }}</h4>
    <p class="hint"><slot /></p>
    <article v-for="problem in problems" :key="problem.request_id" class="problem">
      <div class="problem-head">
        <strong>№{{ problem.request_id }}</strong>
        <span>{{ problem.address }}</span>
        <span class="muted">окно {{ moscowTimeOf(problem.window_start) }}–{{ moscowTimeOf(problem.window_end) }}</span>
        <span v-if="problem.expired" class="chip">окно закрылось</span>
      </div>
      <p class="problem-reason">{{ problem.reason }}</p>
      <p v-if="problem.suggested_start" class="problem-offer">
        {{ problem.suggested_engineer }} приедет в {{ moscowTimeOf(problem.suggested_start) }} —
        предложите клиенту {{ moscowTimeOf(problem.suggested_start) }}–{{ moscowTimeOf(problem.suggested_end) }}
        (допуск {{ tolerance }} мин)
      </p>
      <p v-else class="problem-offer muted">Сегодня не успеть ни при каком окне</p>
      <fieldset class="problem-actions" :disabled="disabled">
        <select
          v-model="decisions[problem.request_id].action"
          :aria-label="`что ответил клиент по заявке №${problem.request_id}`"
        >
          <option value="agree" :disabled="!problem.suggested_start">Согласен на предложенное окно</option>
          <option value="move">Сегодня не может — перенести</option>
          <option value="cancel">Работа не нужна</option>
          <option value="no_answer">Не дозвонились</option>
        </select>
        <template v-if="decisions[problem.request_id].action === 'move'">
          <input v-model="decisions[problem.request_id].date" type="date" aria-label="день нового окна" />
          <TimeInput v-model="decisions[problem.request_id].from" aria-label="начало нового окна" />
          <span>–</span>
          <TimeInput v-model="decisions[problem.request_id].to" aria-label="конец нового окна" />
        </template>
        <input
          v-if="decisions[problem.request_id].action === 'cancel'"
          v-model="decisions[problem.request_id].reason"
          class="reason"
          placeholder="причина отмены"
          :aria-label="`причина отмены заявки №${problem.request_id}`"
        />
        <span v-if="decisions[problem.request_id].action === 'no_answer'" class="muted">
          отменим с отметкой «требует уточнения»
        </span>
      </fieldset>
    </article>
  </section>
</template>

<style scoped>
.problems {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
}

.problems h4 {
  margin: 0;
  color: #991b1b;
  font-size: 14px;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.problem {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
}

.problem-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
}

.problem-reason {
  margin: 0;
  color: #b91c1c;
  font-size: 12px;
}

.problem-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0;
  border: 0;
}

.problem-actions select {
  width: auto;
}

.problem-actions input[type='date'] {
  width: 150px;
}

.problem-actions .reason {
  width: 220px;
}

.problem-offer {
  margin: 0;
  color: #166534;
  font-size: 12px;
}

.muted {
  color: #64748b;
}

.chip {
  padding: 1px 6px;
  border-radius: 999px;
  background: #fee2e2;
  color: #991b1b;
  font-size: 11px;
}
</style>
