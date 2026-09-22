<script setup>
// Что не так с утверждённым планом — открывается по клику на «!» у его номера.
// Номера заявок кликабельны: ведут на вкладку «Заявки» к этой заявке.
import { computed } from 'vue'

import { usePlanFocus } from '../composables/usePlanFocus.js'
import { referenceName } from '../utils/referenceNames.js'
import { statusCode } from '../utils/requestStatuses.js'
import ErrorMessage from './ErrorMessage.vue'

const props = defineProps({
  summary: { type: Object, required: true },
  references: { type: Object, required: true },
})
defineEmits(['close'])

const { openRequest } = usePlanFocus()

const withdrawn = computed(() => props.summary.withdrawn_requests ?? [])
// аварийные — часть новых: показываем их первым пунктом и в остальных новых не повторяем
const emergency = computed(() => props.summary.urgent_request_ids ?? [])
const fresh = computed(() => (props.summary.new_request_ids ?? []).filter((id) => !emergency.value.includes(id)))
const atRisk = computed(() => props.summary.at_risk_request_ids ?? [])

// как сняли: отменили или вернули в «Новая» — ждёт нового расчёта
function howWithdrawn(item) {
  if (statusCode(props.references, item.status_id) === 'new') return 'возвращена в «Новая»'
  return referenceName(props.references, 'request_statuses', item.status_id).toLowerCase()
}
</script>

<template>
  <ErrorMessage :message="`План №${summary.id} стоит пересчитать`" @close="$emit('close')">
    <ul class="replan-reasons">
      <li v-if="emergency.length">
        Новые аварийные заявки — план их не видел, а их нужно выполнить в первую очередь:
        <span v-for="id in emergency" :key="id" class="replan-request">
          <button type="button" class="link" @click="openRequest(id)">№{{ id }}</button>
        </span>
      </li>
      <li v-if="atRisk.length">
        Бригады отстают от плана — к этим заявкам уже не успеть до конца окна:
        <span v-for="id in atRisk" :key="id" class="replan-request">
          <button type="button" class="link" @click="openRequest(id)">№{{ id }}</button>
        </span>
      </li>
      <li v-if="withdrawn.length">
        С утверждения сняты с плана — бригада к ним не поедет, их время в маршрутах пустует:
        <span v-for="item in withdrawn" :key="item.request_id" class="replan-request">
          <button type="button" class="link" @click="openRequest(item.request_id)">№{{ item.request_id }}</button>
          ({{ howWithdrawn(item) }})
        </span>
      </li>
      <li v-if="fresh.length">
        Новые заявки этого дня — план их не видел, в маршрутах их нет:
        <span v-for="id in fresh" :key="id" class="replan-request">
          <button type="button" class="link" @click="openRequest(id)">№{{ id }}</button>
        </span>
      </li>
    </ul>
    <!-- своей кнопки нет: пока плашка открыта, подсвечена кнопка «Пересчитать» у самого плана -->
    <p class="replan-how">
      Нажмите подсвеченную «Пересчитать»: выполненное и начатое останется за бригадами, остальное
      разложится заново — получится новый план, его утверждение заменит этот.
    </p>
  </ErrorMessage>
</template>

<style scoped>
.replan-reasons {
  margin: 6px 0 0;
  padding-left: 18px;
}

.replan-request {
  margin-left: 6px;
  white-space: nowrap;
}

.replan-request .link {
  color: #991b1b;
  font-weight: 600;
  text-decoration: underline;
}

.replan-how {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin: 8px 0 0;
  color: #7f1d1d;
}
</style>
