from datetime import date

from campscan.scanner import SearchSettings, build_search_url, _extract_from_json_blob


def test_build_search_url_overrides_query_values():
    url = "https://reservations.ontarioparks.ca/create-booking/results?resourceLocationId=123&partySize=1"
    settings = SearchSettings(
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 12),
        party_size=4,
        equipment_id="-32768",
        sub_equipment_id="-32765",
        nights=2,
    )

    built = build_search_url(url, settings)

    assert "startDate=2026-07-10" in built
    assert "endDate=2026-07-12" in built
    assert "partySize=4" in built
    assert "equipmentId=-32768" in built
    assert "subEquipmentId=-32765" in built
    assert "resourceLocationId=123" in built


def test_extract_from_json_blob_detects_availability_shapes():
    payload = {
        "units": [
            {"unitName": "Site 101", "available": True, "loop": "A"},
            {"siteName": "Site 202", "status": "Sold Out", "loop": "B"},
        ]
    }

    records = _extract_from_json_blob(payload, "Algonquin", "https://example.test/api")

    assert len(records) == 2
    assert records[0].campground == "Algonquin"
    assert records[0].unit_name == "Site 101"
    assert records[1].status == "Sold Out"
