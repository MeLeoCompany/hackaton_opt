<script setup>
// Ячейки строки таблицы заявок в режиме редактирования (всё, кроме номера заявки).
// form — объект формы из useRequestsTable, поля ввода меняют его напрямую.
defineProps({
  form: { type: Object, required: true },
  references: { type: Object, required: true },
  saving: { type: Boolean, required: true },
})
defineEmits(['save', 'cancel'])
</script>

<template>
  <td>
    <input v-model="form.is_active" type="checkbox" class="active-checkbox" title="Учитывать при планировании" />
  </td>
  <td>
    <input v-model="form.address" class="wide-input" placeholder="Город Москва, ул. …" />
  </td>
  <td>
    <input v-model="form.latitude" type="number" step="any" placeholder="55.7400" />
  </td>
  <td>
    <input v-model="form.longitude" type="number" step="any" placeholder="37.6580" />
  </td>
  <td>
    <input v-model="form.duration_minutes" type="number" min="1" class="short-input" />
  </td>
  <td>
    <div class="stacked-inputs">
      <input v-model="form.window_start" type="datetime-local" />
      <input v-model="form.window_end" type="datetime-local" />
    </div>
  </td>
  <td>
    <select v-model="form.priority_id">
      <option v-for="item in references.priorities" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </td>
  <td>
    <select v-model="form.skill_id">
      <option v-for="item in references.skills" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </td>
  <td>
    <select v-model="form.transport_id">
      <option value="">— не важен</option>
      <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </td>
  <td>
    <div class="row-actions">
      <button class="primary" :disabled="saving" @click="$emit('save')">
        {{ saving ? 'Сохраняю…' : 'Сохранить' }}
      </button>
      <button :disabled="saving" @click="$emit('cancel')">Отмена</button>
    </div>
  </td>
</template>

<style scoped>
input.active-checkbox {
  width: 16px;
  min-width: 0;
  height: 16px;
  padding: 0;
}

.stacked-inputs {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
