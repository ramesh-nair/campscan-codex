from datetime import date

import campscan.scanner as scanner
from campscan.scanner import SearchSettings, _extract_from_json_blob, build_search_url


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


def test_configure_windows_event_loop_policy_updates_policy(monkeypatch):
    class FakePolicy:
        pass

    class FakeProactorPolicy(FakePolicy):
        pass

    tracker = {"value": FakePolicy()}

    monkeypatch.setattr(scanner.sys, "platform", "win32")
    monkeypatch.setattr(scanner.asyncio, "WindowsProactorEventLoopPolicy", FakeProactorPolicy, raising=False)
    monkeypatch.setattr(scanner.asyncio, "get_event_loop_policy", lambda: tracker["value"])
    monkeypatch.setattr(scanner.asyncio, "set_event_loop_policy", lambda value: tracker.update(value=value))

    scanner._configure_windows_event_loop_policy()

    assert isinstance(tracker["value"], FakeProactorPolicy)


def test_scan_availability_uses_windows_subprocess(monkeypatch):
    sentinel = [scanner.AvailabilityRecord("A", "B", "C", "D", "E")]

    monkeypatch.setattr(scanner.sys, "platform", "win32")
    monkeypatch.setattr(scanner, "_scan_availability_windows_subprocess", lambda requests, settings, timeout_ms: sentinel)

    result = scanner.scan_availability([], SearchSettings(date(2026, 1, 1), date(2026, 1, 2), 2, "1", "2"))

    assert result == sentinel
