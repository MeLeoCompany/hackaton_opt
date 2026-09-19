<script setup>
// Справочник бригад офиса. Бригада работает в регионе своего офиса; её смена на день — строка
// во вкладке «Исполнители», где бригаду выбирают из этого справочника. Логин и пароль — вход
// бригады в мобильное приложение. Доступно администратору (офис — выбранный в боковой панели)
// и диспетчеру (свой офис).
import { onMounted } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import IconButton from '../components/IconButton.vue'
import { useAuth } from '../composables/useAuth.js'
import { NEW_BRIGADE, useBrigades } from '../composables/useBrigades.js'

const {
  brigades,
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
} = useBrigades()

const { currentOfficeName } = useAuth()

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Бригады</h1>
      <p>
        Офис «{{ currentOfficeName }}» · бригад {{ brigades.length }} · смены на день заводятся во вкладке
        «Исполнители» · логин и пароль — вход бригады в мобильное приложение
      </p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю бригады…</p>

    <template v-else>
      <div class="list-bar">
        <button class="primary" :disabled="editingId !== null" @click="startCreate">+ Добавить бригаду</button>
      </div>

      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 70px" />
            <col />
            <col style="width: 190px" />
            <col style="width: 190px" />
            <col style="width: 100px" />
            <col style="width: 100px" />
            <col style="width: 130px" />
          </colgroup>
          <thead>
            <tr>
              <th>№</th>
              <th>Название</th>
              <th>Логин в приложении</th>
              <th>Пароль</th>
              <th>Смен</th>
              <th>Активна</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="item in [...brigades, ...(editingId === NEW_BRIGADE ? [null] : [])]"
              :key="item?.id ?? 'new'"
            >
              <tr v-if="item === null || item.id === editingId" class="editing">
                <td class="number-cell">{{ item?.id ?? '—' }}</td>
                <td><input v-model="form.name" placeholder="Бригада Иванов" aria-label="название бригады" /></td>
                <td>
                  <input
                    v-model="form.login"
                    placeholder="без входа"
                    aria-label="логин бригады в приложении"
                    autocomplete="off"
                  />
                </td>
                <td>
                  <input
                    v-model="form.password"
                    type="password"
                    autocomplete="new-password"
                    :disabled="!form.login.trim()"
                    :placeholder="form.hasLogin ? 'оставить прежний' : form.login.trim() ? 'пароль' : 'сначала логин'"
                    aria-label="пароль бригады в приложении"
                  />
                </td>
                <td class="number-cell">{{ item?.shift_count ?? 0 }}</td>
                <td>
                  <label class="switch" title="Выключенной бригаде не заводят смен, в приложение она не входит">
                    <input v-model="form.is_active" type="checkbox" aria-label="бригада активна" />
                    <span class="slider"></span>
                  </label>
                </td>
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

              <tr v-else :class="{ muted: !item.is_active }">
                <td class="number-cell">{{ item.id }}</td>
                <td><strong>{{ item.name }}</strong></td>
                <td>
                  <template v-if="item.login">{{ item.login }}</template>
                  <span v-else class="muted" title="Бригада не входит в мобильное приложение">без входа</span>
                </td>
                <td class="muted">{{ item.login ? '••••' : '—' }}</td>
                <td class="number-cell">{{ item.shift_count }}</td>
                <td>
                  <label class="switch" :title="item.is_active ? 'Работает' : 'Выключена'">
                    <input type="checkbox" :checked="item.is_active" disabled aria-label="бригада активна" />
                    <span class="slider"></span>
                  </label>
                </td>
                <td>
                  <div class="row-actions">
                    <IconButton icon="edit" label="Изменить" :disabled="editingId !== null" @click="startEdit(item)" />
                    <IconButton
                      icon="delete"
                      variant="danger"
                      :label="
                        item.shift_count
                          ? `У бригады есть смены (${item.shift_count}) — удалить нельзя, выключите её`
                          : 'Удалить'
                      "
                      :disabled="editingId !== null || saving || item.shift_count > 0"
                      @click="remove(item)"
                    />
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!brigades.length && editingId !== NEW_BRIGADE">
              <td colspan="7" class="empty">В офисе ещё нет бригад</td>
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
