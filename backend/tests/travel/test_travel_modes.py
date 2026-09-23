"""Чем помечено плечо маршрута: пешком, на велосипеде или по дороге.

По этой пометке интерфейс рисует участок, поэтому велосипед не должен выглядеть машиной —
ни когда маршрут строит Valhalla, ни когда маршрутизатор лёг и считает запасной провайдер.
"""

from src.schemas.travel import LEG_MODES, Point, TransportKind, TravelMode
from src.services.travel import haversine_provider

MOSCOW = [Point(latitude=55.75, longitude=37.62), Point(latitude=55.76, longitude=37.64)]


def test_each_transport_has_its_own_leg_mode():
    assert LEG_MODES[TransportKind.PEDESTRIAN] is TravelMode.WALK
    assert LEG_MODES[TransportKind.BICYCLE] is TravelMode.BIKE
    # машина и общественный транспорт своей пометки не имеют: дорога и режимы рейсов R5
    assert TransportKind.CAR not in LEG_MODES
    assert TransportKind.PUBLIC_TRANSPORT not in LEG_MODES


def test_fallback_legs_keep_the_mode():
    """Маршрутизатор лёг: плечи считает haversine — пометка всё равно правильная."""
    modes = {
        transport: haversine_provider.route_legs(MOSCOW, transport)[0].mode
        for transport in (TransportKind.CAR, TransportKind.PEDESTRIAN, TransportKind.BICYCLE)
    }

    assert modes[TransportKind.BICYCLE] is TravelMode.BIKE
    assert modes[TransportKind.PEDESTRIAN] is TravelMode.WALK
    assert modes[TransportKind.CAR] is TravelMode.ROAD


def test_bicycle_route_is_not_the_same_as_a_car_route():
    """Велосипед едет медленнее машины — и в запасном провайдере тоже."""
    bike = haversine_provider.route_legs(MOSCOW, TransportKind.BICYCLE)[0]
    car = haversine_provider.route_legs(MOSCOW, TransportKind.CAR)[0]

    assert bike.duration_min > car.duration_min
