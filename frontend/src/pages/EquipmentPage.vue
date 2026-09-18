<script setup>
// Справочник оборудования: что техник привозит на заявку. Требование ставится в заявке
// (колонка «Тип работ» на вкладке заявок). Тип, который требуют заявки, не удалить.
import { onMounted } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import IconButton from '../components/IconButton.vue'
import { useAuth } from '../composables/useAuth.js'
import { NEW_EQUIPMENT, useEquipment } from '../composables/useEquipment.js'

const {
  equipment,
  loading,
  saving,
  errorMessage,
  errorDetails,
  noticeMessage,
  editingId,
  form,
  load,
  startCreate,
  startEdit,
  cancelEdit,
  saveForm,
  remove,
} = useEquipment()

// справочник правит администратор; диспетчер его только смотрит
const { isAdmin } = useAuth()

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Оборудование</h1>
      <p>Всего {{ equipment.length }} · что техник привозит на заявку</p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю оборудование…</p>

    <template v-else>
      <div v-if="isAdmin" class="list-bar">
        <button class="primary" :disabled="editingId !== null" @click="startCreate">+ Добавить оборудование</button>
      </div>

      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 70px" />
            <col style="width: 220px" />
            <col />
            <col style="width: 110px" />
            <col style="width: 110px" />
            <col style="width: 110px" />
          </colgroup>
          <thead>
            <tr>
              <th>№</th>
              <th>Название</th>
              <th>Описание</th>
              <th>Заявок</th>
              <th>У бригад</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="item in [...equipment, ...(editingId === NEW_EQUIPMENT ? [null] : [])]"
              :key="item?.id ?? 'new'"
            >
              <tr v-if="item === null || item.id === editingId" class="editing">
                <td class="number-cell">{{ item?.id ?? '—' }}</td>
                <td><input v-model="form.name" placeholder="Роутер" aria-label="название оборудования" /></td>
                <td>
                  <input v-model="form.description" placeholder="для чего нужно" aria-label="описание оборудования" />
                </td>
                <td class="number-cell">{{ item?.request_count ?? 0 }}</td>
                <td class="number-cell">{{ item?.engineer_count ?? 0 }}</td>
                <td>
                  <div class="row-actions">
                    <IconButton
                      icon="save"
                      :label="saving ? 'Сохраняю…' : 'Сохранить'"
                      variant="primary"
                      :disabled="saving"
                      @click="saveForm"
                    />
                    <IconButton icon="cancel" label="Отмена" :disabled="saving" @click="cancelEdit" />
                  </div>
                </td>
              </tr>

              <tr v-else>
                <td class="number-cell">{{ item.id }}</td>
                <td><strong>{{ item.name }}</strong></td>
                <td class="muted">{{ item.description || '—' }}</td>
                <td class="number-cell">{{ item.request_count }}</td>
                <td class="number-cell">{{ item.engineer_count }}</td>
                <td>
                  <div v-if="isAdmin" class="row-actions">
                    <IconButton icon="edit" label="Изменить" :disabled="editingId !== null" @click="startEdit(item)" />
                    <IconButton
                      icon="delete"
                      variant="danger"
                      :label="item.request_count || item.engineer_count ? `Есть в заявках (${item.request_count}) и у бригад (${item.engineer_count}) — не удалить` : 'Удалить'"
                      :disabled="editingId !== null || saving || item.request_count > 0 || item.engineer_count > 0"
                      @click="remove(item)"
                    />
                  </div>
                </td>
              </tr>
            </template>

            <tr v-if="!equipment.length && editingId !== NEW_EQUIPMENT">
              <td colspan="6" class="empty">Оборудования в справочнике нет</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>
