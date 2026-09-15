"""Раздел 5: целевая функция.

    min  W1 * sum_i w_i * z_i  +  W2 * sum_k u_k  +  W3 * sum_k sum_uv d_uv * x^k_uv

Лексикографический порядок приоритетов задаётся разрывом в весах:
назначить как можно больше заявок (срочные — в первую очередь) → задействовать меньше
инженеров → сократить пробег. Веса — параметры, а не константы в коде: их придётся
крутить на демо-данных.
"""

from dataclasses import dataclass

import numpy as np

from src.services.planner.planner_variables import VariableLayout


@dataclass(frozen=True)
class ObjectiveWeights:
    unassigned: float = 1e6  # W1 — штраф за неназначенную заявку
    engineer_used: float = 1e3  # W2 — плата за задействование инженера
    distance_km: float = 1.0  # W3 — цена километра


def build(layout: VariableLayout, weights: ObjectiveWeights) -> np.ndarray:
    instance = layout.instance
    costs = np.zeros(layout.n_variables, dtype=np.float64)

    arc_distance = np.array(
        [
            instance.distance_for(
                int(layout.arc_engineer[a]), int(layout.arc_from[a]), int(layout.arc_to[a])
            )
            for a in range(layout.n_arcs)
        ],
        dtype=np.float64,
    )
    costs[layout.arc_offset : layout.arc_offset + layout.n_arcs] = (
        weights.distance_km * arc_distance
    )

    usage_slice = slice(layout.usage_offset, layout.usage_offset + instance.n_engineers)
    costs[usage_slice] = weights.engineer_used

    priority = np.array([r.priority_weight for r in instance.requests], dtype=np.float64)
    unassigned_slice = slice(
        layout.unassigned_offset, layout.unassigned_offset + instance.n_requests
    )
    costs[unassigned_slice] = weights.unassigned * priority

    # y^k_i и tau_i в целевой функции не участвуют
    return costs
