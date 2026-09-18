// Оборудование из формы -> в API: { номер: количество } -> [{ equipment_id, quantity }].
// Отмеченный тип с пустым или неверным количеством — одна штука: галочку ставили не зря.

export function equipmentPayload(quantities = {}) {
  return Object.entries(quantities).map(([equipmentId, quantity]) => ({
    equipment_id: Number(equipmentId),
    quantity: Number(quantity) >= 1 ? Math.floor(Number(quantity)) : 1,
  }))
}
