"""Проверки аудита источников до какого-либо импорта в БД."""

import csv

from scripts.audit_anonymized import REGIONS, audit


def write_source(path, fields, records, *, office=None):
    with path.open("w", encoding="cp1251", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(records)
        if office is not None:
            writer.writerow({"Заявка": "Адрес офиса", "Тип заявки BK": office})


def test_audit_detects_pair_mismatch_without_exposing_addresses(tmp_path):
    synthetic = {
        "Заявка": "100",
        "Тип заявки BK": "Подключение",
        "Тип заявки HD": "Тест",
        "Начало": "17.08.2026 10:00",
        "Окончание": "17.08.2026 12:00",
        "Район": "Тестовый",
        "Адрес": "Секретная улица, д. 1",
    }
    control = {
        **synthetic,
        "Заявка": "200",
        "Адрес": "Секретная улица, д. 1, кв. 9",
        "Статус BK": "Выполнена",
        "Бригада": "Бригада 1",
    }
    for region in REGIONS:
        write_source(
            tmp_path / f"{region} Синтетические данные.csv",
            list(synthetic),
            [synthetic],
            office="Офис",
        )
        write_source(
            tmp_path / f"{region} Контрольное распределение.csv",
            list(control),
            [control],
        )

    valid = audit(tmp_path)
    assert not valid["ошибки"]
    assert valid["регионы"]["Восток"]["строки_совпадают"] is True
    assert "Секретная" not in str(valid)

    control["Окончание"] = "17.08.2026 09:00"
    write_source(
        tmp_path / f"{REGIONS[0]} Контрольное распределение.csv",
        list(control),
        [control],
    )
    invalid = audit(tmp_path)
    assert invalid["ошибки"]
    assert invalid["регионы"]["Восток"]["строки_совпадают"] is False
    assert "Секретная" not in str(invalid)
