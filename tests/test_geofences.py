import pytest
from app.config import GeofenceItem, AppConfig, load_config, save_config
from app.services.geofences import haversine_distance_m, matches_location_point


def test_haversine_distance():
    # Identical points
    assert haversine_distance_m(39.8535, -105.1493, 39.8535, -105.1493) == pytest.approx(0.0, abs=1e-3)
    
    # Missing coordinates
    assert haversine_distance_m(None, -105.1493, 39.8535, -105.1493) == float("inf")
    assert haversine_distance_m(39.8535, None, 39.8535, -105.1493) == float("inf")
    
    # Approx 100 meters north
    dist = haversine_distance_m(39.85350, -105.1493, 39.85440, -105.1493)
    assert 90.0 < dist < 110.0


def test_geofence_item_alias_parsing():
    # Comma-separated string
    g1 = GeofenceItem(
        name="Home",
        latitude=39.8536,
        longitude=-105.1497,
        radius_meters=350,
        address_aliases="Main Street, Elm Street, Oak Avenue"
    )
    assert g1.address_aliases == ["Main Street", "Elm Street", "Oak Avenue"]

    # List of strings
    g2 = GeofenceItem(
        name="Work",
        latitude=39.7564,
        longitude=-105.2214,
        radius_meters=400,
        address_aliases=["Jackson St", " 11th St "]
    )
    assert g2.address_aliases == ["Jackson St", "11th St"]


def test_matches_location_point_by_geofence_radius():
    home_geo = GeofenceItem(
        name="Home",
        latitude=39.8536,
        longitude=-105.1497,
        radius_meters=350,
        address_aliases=["87th Terrace"]
    )
    geofences = [home_geo]

    # Inside geofence radius (approx 100m away)
    matched = matches_location_point(
        target="Home",
        drive_lat=39.8540,
        drive_lon=-105.1495,
        drive_name="Random Street",
        drive_city="City",
        geofences=geofences
    )
    assert matched is True

    # Far away (e.g. 10km away)
    unmatched = matches_location_point(
        target="Home",
        drive_lat=39.7564,
        drive_lon=-105.2214,
        drive_name="Random Street",
        drive_city="City",
        geofences=geofences
    )
    assert unmatched is False


def test_matches_location_point_by_geofence_alias():
    work_geo = GeofenceItem(
        name="Office",
        latitude=39.7564,
        longitude=-105.2214,
        radius_meters=400,
        address_aliases=["11th Street", "Jackson Street", "Prospector's Alley"]
    )
    geofences = [work_geo]

    # Target is "Office", drive ended at "Jackson Street" even without GPS
    matched = matches_location_point(
        target="Office",
        drive_lat=None,
        drive_lon=None,
        drive_name="Jackson Street",
        drive_city="Town",
        geofences=geofences
    )
    assert matched is True

    # Target is "11th Street", drive has GPS inside Office geofence
    matched2 = matches_location_point(
        target="11th Street",
        drive_lat=39.7562,
        drive_lon=-105.2207,
        drive_name="Prospector's Alley",
        drive_city="Town",
        geofences=geofences
    )
    assert matched2 is True


def test_matches_location_point_by_address_cache():
    addr_cache = {
        "elm street": (39.8000, -105.1000),
        "elm street city": (39.8000, -105.1000)
    }

    # Drive parked 50m from Elm Street
    matched = matches_location_point(
        target="Elm Street",
        drive_lat=39.8003,
        drive_lon=-105.1002,
        drive_name="Oak Court",
        drive_city="City",
        geofences=[],
        addr_cache=addr_cache
    )
    assert matched is True

    # Drive parked 2km from Elm Street
    unmatched = matches_location_point(
        target="Elm Street",
        drive_lat=39.8200,
        drive_lon=-105.1000,
        drive_name="Oak Court",
        drive_city="City",
        geofences=[],
        addr_cache=addr_cache
    )
    assert unmatched is False


def test_geofences_config_roundtrip():
    cfg = load_config()
    orig_geofences = cfg.geofences

    test_geo = GeofenceItem(
        name="Test Area",
        latitude=40.0,
        longitude=-105.0,
        radius_meters=500,
        address_aliases=["Street A", "Street B"]
    )
    cfg.geofences = [test_geo]
    save_config(cfg)

    reloaded = load_config()
    assert len(reloaded.geofences) == 1
    assert reloaded.geofences[0].name == "Test Area"
    assert reloaded.geofences[0].latitude == 40.0
    assert reloaded.geofences[0].longitude == -105.0
    assert reloaded.geofences[0].radius_meters == 500
    assert reloaded.geofences[0].address_aliases == ["Street A", "Street B"]

    # Restore
    cfg.geofences = orig_geofences
    save_config(cfg)
