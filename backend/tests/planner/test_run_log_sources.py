"""Подпись строки журнала расчёта: короткая и понятная, а не имя файла.

В журнале под источник отведена узкая колонка: «ortools_solver» в неё не влезает и
обрезается, поэтому у каждого решателя и службы своя короткая подпись.
"""

from src.services.planner.run_log import log_source


def test_solvers_are_named_by_solver():
    assert log_source("src.services.planner.ortools_solver") == "or-tools"
    assert log_source("src.services.planner.cuopt_solver") == "cuopt"
    assert log_source("cuopt") == "cuopt"
    assert log_source("src.services.planner.baseline_solver") == "базовый"


def test_services_are_named_by_service():
    assert log_source("src.services.travel.r5_access") == "r5"
    assert log_source("src.services.travel.valhalla_provider") == "valhalla"
    assert log_source("src.services.travel.travel_cache") == "кеш"


def test_other_modules_fall_back_to_their_service():
    """Новый модуль не должен показывать оператору имя файла."""
    assert log_source("src.services.planner.replan_service") == "planner"
    assert log_source("src.services.planner.window_suggestions") == "planner"
    assert log_source("src.services.travel.haversine_provider") == "travel"


def test_every_label_fits_the_column():
    """Колонка источника — 54 пикселя: подпись не длиннее восьми знаков."""
    from src.services.planner.run_log import LOG_SOURCES

    assert all(len(label) <= 8 for label in LOG_SOURCES.values())
