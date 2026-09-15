import pytest

from milp_test_helpers import CAR, WALK, engineer, make_instance, request


@pytest.fixture
def basic_instance():
    """Два инженера, три заявки. Ожидаемый ответ очевиден:

    инженер 1 (авто, навык 1):   заявка 10 в 10:00, потом заявка 11 в 15:00
    инженер 2 (пешком, навык 2): заявка 12 в 10:00
    """
    return make_instance(
        engineers=[
            engineer(1, transport=CAR),
            engineer(2, transport=WALK),
        ],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("15:00", "17:00")),
            request(12, skill=2, window=("10:00", "12:00")),
        ],
        skills={1: {1}, 2: {2}},
    )
