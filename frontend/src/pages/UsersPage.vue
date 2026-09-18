<script setup>
// Учётки администраторов и диспетчеров. Диспетчер привязан к офису и работает только с ним.
import { onMounted } from 'vue'

import IconButton from '../components/IconButton.vue'
import { useAuth } from '../composables/useAuth.js'
import { NEW_USER, ROLES, useUsers } from '../composables/useUsers.js'
import { referenceName } from '../utils/referenceNames.js'

const {
  users,
  offices,
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
} = useUsers()

const { user: currentUser } = useAuth()

function roleLabel(role) {
  return ROLES.find((item) => item.value === role)?.label ?? role
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Пользователи</h1>
      <p>Всего {{ users.length }} · диспетчер видит только свой офис</p>
    </header>

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

    <p v-if="loading" class="muted">Загружаю учётки…</p>

    <template v-else>
      <div class="list-bar">
        <button class="primary" :disabled="editingId !== null" @click="startCreate">+ Добавить учётку</button>
      </div>

      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 70px" />
            <col style="width: 170px" />
            <col />
            <col style="width: 170px" />
            <col style="width: 190px" />
            <col style="width: 100px" />
            <col style="width: 170px" />
            <col style="width: 110px" />
          </colgroup>
          <thead>
            <tr>
              <th>№</th>
              <th>Логин</th>
              <th>Имя</th>
              <th>Роль</th>
              <th>Офис</th>
              <th>Активна</th>
              <th>Пароль</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="item in [...users, ...(editingId === NEW_USER ? [null] : [])]" :key="item?.id ?? 'new'">
              <tr v-if="item === null || item.id === editingId" class="editing">
                <td class="number-cell">{{ item?.id ?? '—' }}</td>
                <td><input v-model="form.login" placeholder="ivanov" aria-label="логин" autocomplete="off" /></td>
                <td><input v-model="form.name" placeholder="Иванов Иван" aria-label="имя" /></td>
                <td>
                  <select v-model="form.role" aria-label="роль">
                    <option v-for="role in ROLES" :key="role.value" :value="role.value">{{ role.label }}</option>
                  </select>
                </td>
                <td>
                  <select
                    v-model="form.office_id"
                    :disabled="form.role === 'admin'"
                    aria-label="офис"
                    :title="form.role === 'admin' ? 'Администратор выбирает офис сам' : ''"
                  >
                    <option v-if="form.role === 'admin'" value="">любой</option>
                    <option v-for="office in offices" :key="office.id" :value="office.id">«{{ office.name }}»</option>
                  </select>
                </td>
                <td>
                  <label class="switch" title="Выключенная учётка не может войти">
                    <input v-model="form.is_active" type="checkbox" aria-label="учётка активна" />
                    <span class="slider"></span>
                  </label>
                </td>
                <td>
                  <input
                    v-model="form.password"
                    type="password"
                    autocomplete="new-password"
                    :placeholder="item === null ? 'пароль' : 'оставить прежний'"
                    aria-label="пароль"
                  />
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
                <td><strong>{{ item.login }}</strong></td>
                <td>{{ item.name }}</td>
                <td>{{ roleLabel(item.role) }}</td>
                <td>{{ item.office_id ? `«${referenceName({ offices }, 'offices', item.office_id)}»` : 'любой' }}</td>
                <td>
                  <label class="switch" :title="item.is_active ? 'Может войти' : 'Выключена: войти не может'">
                    <input type="checkbox" :checked="item.is_active" disabled aria-label="учётка активна" />
                    <span class="slider"></span>
                  </label>
                </td>
                <td class="muted">••••</td>
                <td>
                  <div class="row-actions">
                    <IconButton icon="edit" label="Изменить" :disabled="editingId !== null" @click="startEdit(item)" />
                    <IconButton
                      icon="delete"
                      variant="danger"
                      :label="item.id === currentUser.id ? 'Себя удалить нельзя' : 'Удалить'"
                      :disabled="editingId !== null || saving || item.id === currentUser.id"
                      @click="remove(item)"
                    />
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>
