from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from multiprocessing import get_context
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class ScanRequest:
    name: str
    search_url: str


@dataclass
class SearchSettings:
    start_date: date
    end_date: date
    party_size: int
    equipment_id: str
    sub_equipment_id: str
    nights: int | None = None


@dataclass
class AvailabilityRecord:
    campground: str
    source: str
    unit_name: str
    status: str
    details: str


def _configure_windows_event_loop_policy() -> None:
    """Ensure Playwright can spawn subprocesses when running on Windows."""
    if sys.platform != "win32":
        return

    policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_cls is None:
        return

    current_policy = asyncio.get_event_loop_policy()
    if not isinstance(current_policy, policy_cls):
        asyncio.set_event_loop_policy(policy_cls())


def _deep_iter(data: Any) -> Iterable[Any]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _deep_iter(value)
    elif isinstance(data, list):
        for item in data:
            yield from _deep_iter(item)


def build_search_url(base_url: str, settings: SearchSettings) -> str:
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)

    query["startDate"] = [settings.start_date.isoformat()]
    query["endDate"] = [settings.end_date.isoformat()]
    query["partySize"] = [str(settings.party_size)]
    query["equipmentId"] = [settings.equipment_id]
    query["subEquipmentId"] = [settings.sub_equipment_id]
    if settings.nights is not None:
        query["nights"] = [str(settings.nights)]

    encoded = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=encoded))


def _extract_from_json_blob(blob: Any, campground: str, source: str) -> list[AvailabilityRecord]:
    records: list[AvailabilityRecord] = []

    for node in _deep_iter(blob):
        keys = {key.lower() for key in node.keys()}

        has_name = any(k in keys for k in ("name", "unitname", "site", "sitename"))
        has_status = any(k in keys for k in ("status", "availability", "available", "isavailable"))
        if not (has_name and has_status):
            continue

        unit_name = str(
            node.get("unitName")
            or node.get("siteName")
            or node.get("site")
            or node.get("name")
            or "Unknown"
        )

        raw_status = (
            node.get("status")
            if "status" in node
            else node.get("availability")
            if "availability" in node
            else node.get("available")
            if "available" in node
            else node.get("isAvailable")
        )

        status = str(raw_status)
        details = json.dumps(node, ensure_ascii=False)[:400]

        records.append(
            AvailabilityRecord(
                campground=campground,
                source=source,
                unit_name=unit_name,
                status=status,
                details=details,
            )
        )

    return records


def _extract_from_page_text(page_text: str, campground: str) -> list[AvailabilityRecord]:
    records: list[AvailabilityRecord] = []
    pattern = re.compile(r"(Site\s*\w+[^\n]{0,40})\s+(Available|Sold\s*out|Not\s+available)", re.IGNORECASE)
    for match in pattern.finditer(page_text):
        unit, status = match.groups()
        records.append(
            AvailabilityRecord(
                campground=campground,
                source="page_text",
                unit_name=unit.strip(),
                status=status.strip(),
                details="Matched from rendered page text.",
            )
        )
    return records


def _scan_availability_impl(requests: list[ScanRequest], settings: SearchSettings, timeout_ms: int) -> list[AvailabilityRecord]:
    all_records: list[AvailabilityRecord] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        )

        for request in requests:
            page = context.new_page()
            api_records: list[AvailabilityRecord] = []

            def handle_response(response):
                url_lower = response.url.lower()
                if not any(token in url_lower for token in ("avail", "camp", "inventory", "site", "unit")):
                    return
                content_type = response.headers.get("content-type", "")
                if "application/json" not in content_type:
                    return
                try:
                    payload = response.json()
                except Exception:
                    return

                extracted = _extract_from_json_blob(payload, request.name, response.url)
                api_records.extend(extracted)

            page.on("response", handle_response)

            target_url = build_search_url(request.search_url, settings)
            try:
                page.goto(target_url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(3_000)

            unique_records: dict[tuple[str, str], AvailabilityRecord] = {}
            for record in api_records:
                key = (record.unit_name, record.status)
                unique_records[key] = record

            if unique_records:
                all_records.extend(unique_records.values())
            else:
                text = page.inner_text("body")
                all_records.extend(_extract_from_page_text(text, request.name))

            page.close()

        browser.close()

    return all_records


def _scan_worker(payload: dict[str, Any], queue) -> None:
    try:
        _configure_windows_event_loop_policy()
        requests = [ScanRequest(**item) for item in payload["requests"]]
        settings_data = payload["settings"]
        settings_data["start_date"] = date.fromisoformat(settings_data["start_date"])
        settings_data["end_date"] = date.fromisoformat(settings_data["end_date"])
        settings = SearchSettings(**settings_data)
        records = _scan_availability_impl(requests, settings, payload["timeout_ms"])
        queue.put({"records": [asdict(record) for record in records]})
    except Exception as exc:  # noqa: BLE001
        queue.put({"error": f"{type(exc).__name__}: {exc}"})


def _scan_availability_windows_subprocess(
    requests: list[ScanRequest], settings: SearchSettings, timeout_ms: int = 45_000
) -> list[AvailabilityRecord]:
    ctx = get_context("spawn")
    queue = ctx.Queue()

    payload = {
        "requests": [asdict(request) for request in requests],
        "settings": {
            **asdict(settings),
            "start_date": settings.start_date.isoformat(),
            "end_date": settings.end_date.isoformat(),
        },
        "timeout_ms": timeout_ms,
    }

    process = ctx.Process(target=_scan_worker, args=(payload, queue))
    process.start()
    process.join(120)

    if process.is_alive():
        process.terminate()
        process.join()
        raise RuntimeError("Playwright scan timed out in Windows worker process.")

    result = queue.get() if not queue.empty() else {"error": "No scanner result returned."}
    if "error" in result:
        raise RuntimeError(
            "Playwright failed on Windows. "
            "Confirm browser binaries are installed with `python -m playwright install chromium`. "
            f"Details: {result['error']}"
        )

    return [AvailabilityRecord(**item) for item in result["records"]]


def scan_availability(requests: list[ScanRequest], settings: SearchSettings, timeout_ms: int = 45_000) -> list[AvailabilityRecord]:
    if sys.platform == "win32":
        return _scan_availability_windows_subprocess(requests, settings, timeout_ms)

    _configure_windows_event_loop_policy()
    return _scan_availability_impl(requests, settings, timeout_ms)
