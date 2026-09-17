"""Метро и пеший вариант в расчёте общественного транспорта."""

from src.schemas.travel import (
    Point,
    TransportKind,
    TravelLeg,
    TravelMatrix,
    TravelMode,
    TravelProvider,
)
from src.services.travel import transit_provider

# Строгино и Марьино: по краям города, наземным через полгорода, метро напрямую
STROGINO = Point(latitude=55.802, longitude=37.402)
MARYINO = Point(latitude=55.650, longitude=37.744)
# соседние дома в центре: полкилометра, ехать бессмысленно
TVERSKAYA = Point(latitude=55.7645, longitude=37.6059)
NEXT_DOOR = Point(latitude=55.7620, longitude=37.6120)
# Домодедово: метро рядом нет
DOMODEDOVO = Point(latitude=55.395, longitude=37.735)
DOMODEDOVO_NEARBY = Point(latitude=55.431, longitude=37.560)


def matrix_of(points: list[Point], minutes: float, kilometres: float) -> TravelMatrix:
    """Матрица наземного транспорта из одинаковых пар — заготовка для проверок."""
    size = len(points)
    return TravelMatrix(
        transport=TransportKind.PUBLIC_TRANSPORT,
        provider=TravelProvider.VALHALLA,
        points=points,
        distances_km=[
            [0.0 if row == column else kilometres for column in range(size)] for row in range(size)
        ],
        durations_min=[
            [0.0 if row == column else minutes for column in range(size)] for row in range(size)
        ],
    )


def test_metro_replaces_slow_surface_ride_across_the_city():
    surface = matrix_of([STROGINO, MARYINO], minutes=120.0, kilometres=53.0)

    result = transit_provider.matrix_with_transit(surface)

    assert result.durations_min[0][1] < 90
    assert result.distances_km[0][1] < 53.0


def test_fast_surface_ride_is_kept():
    surface = matrix_of([STROGINO, MARYINO], minutes=20.0, kilometres=53.0)

    result = transit_provider.matrix_with_transit(surface)

    assert result.durations_min[0][1] == 20.0
    assert result.distances_km[0][1] == 53.0


def test_pair_without_road_gets_metro():
    surface = matrix_of([STROGINO, MARYINO], minutes=120.0, kilometres=53.0)
    surface.durations_min[0][1] = None
    surface.distances_km[0][1] = None

    result = transit_provider.matrix_with_transit(surface)

    assert result.durations_min[0][1] is not None
    assert result.distances_km[0][1] is not None


def test_short_hop_is_walked_not_ridden():
    trip = transit_provider.fastest_trip(TVERSKAYA, NEXT_DOOR)

    assert trip is not None
    # пешком: без станций в середине и без ожидания поезда
    assert trip.stations == []
    assert trip.duration_min < 15


def test_place_without_metro_keeps_surface_transport():
    surface = matrix_of([DOMODEDOVO, DOMODEDOVO_NEARBY], minutes=60.0, kilometres=20.0)

    result = transit_provider.matrix_with_transit(surface)

    assert result.durations_min[0][1] == 60.0


def test_other_transport_is_not_touched():
    surface = matrix_of([STROGINO, MARYINO], minutes=120.0, kilometres=53.0)
    car = surface.model_copy(update={"transport": TransportKind.CAR})

    assert transit_provider.matrix_with_transit(car).durations_min[0][1] == 120.0


def test_replaced_leg_gets_its_own_geometry():
    legs = [TravelLeg(distance_km=53.0, duration_min=120.0, geometry="road")]

    result = transit_provider.legs_with_transit([STROGINO, MARYINO], legs)

    assert result[0].geometry != "road"
    assert result[0].duration_min < 120.0


def test_slow_metro_does_not_replace_fast_leg():
    legs = [TravelLeg(distance_km=53.0, duration_min=20.0, geometry="road")]

    result = transit_provider.legs_with_transit([STROGINO, MARYINO], legs)

    assert result[0].geometry == "road"


def test_replaced_legs_say_how_the_person_travels():
    legs = [TravelLeg(distance_km=53.0, duration_min=120.0, geometry="road")]

    metro_leg = transit_provider.legs_with_transit([STROGINO, MARYINO], legs)[0]
    walk_leg = transit_provider.legs_with_transit([TVERSKAYA, NEXT_DOOR], legs)[0]

    assert metro_leg.mode is TravelMode.METRO
    assert walk_leg.mode is TravelMode.WALK
    # наземный участок остаётся как был
    assert transit_provider.legs_with_transit(
        [STROGINO, MARYINO], [TravelLeg(distance_km=53.0, duration_min=20.0)]
    )[0].mode is TravelMode.ROAD
