from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from campscan.scanner import ScanRequest, SearchSettings, scan_availability

st.set_page_config(page_title="Ontario Parks Campground Scanner", layout="wide")
st.title("🏕️ Ontario Parks Campground Availability Scanner")
st.caption(
    "Provide one search URL per campground from reservations.ontarioparks.ca. "
    "The app updates date + party settings and scrapes availability signals from the rendered page/API responses."
)

with st.sidebar:
    st.header("Search settings")
    start_date = st.date_input("Arrival date", date.today() + timedelta(days=14))
    end_date = st.date_input("Departure date", date.today() + timedelta(days=16))
    party_size = st.number_input("Party size", min_value=1, max_value=12, value=2)
    equipment_id = st.text_input("Equipment ID", value="-32768", help="Use value seen in Ontario Parks search URL.")
    sub_equipment_id = st.text_input(
        "Sub-equipment ID", value="-32765", help="Use value seen in Ontario Parks search URL."
    )

st.subheader("Campgrounds to scan")
st.markdown(
    "Paste one campground per line in the format: `Display Name | https://reservations.ontarioparks.ca/...`"
)

campgrounds_input = st.text_area(
    "Campground list",
    value=(
        "Algonquin - Lake of Two Rivers | "
        "https://reservations.ontarioparks.ca/create-booking/results?resourceLocationId=-2147482628\n"
        "Killbear - George Lake | "
        "https://reservations.ontarioparks.ca/create-booking/results?resourceLocationId=-2147482518"
    ),
    height=160,
)

scan_button = st.button("Scan availability", type="primary")


def parse_requests(raw: str) -> list[ScanRequest]:
    requests: list[ScanRequest] = []
    for line in [item.strip() for item in raw.splitlines() if item.strip()]:
        if "|" not in line:
            continue
        name, url = [part.strip() for part in line.split("|", maxsplit=1)]
        if name and url:
            requests.append(ScanRequest(name=name, search_url=url))
    return requests


if scan_button:
    if end_date <= start_date:
        st.error("Departure date must be after arrival date.")
        st.stop()

    requests = parse_requests(campgrounds_input)
    if not requests:
        st.error("Please provide at least one valid `Name | URL` campground entry.")
        st.stop()

    settings = SearchSettings(
        start_date=start_date,
        end_date=end_date,
        party_size=int(party_size),
        equipment_id=equipment_id,
        sub_equipment_id=sub_equipment_id,
        nights=(end_date - start_date).days,
    )

    with st.spinner("Scanning Ontario Parks search pages..."):
        records = scan_availability(requests, settings)

    if not records:
        st.warning(
            "No availability records were detected. This can happen when the site blocks automation or changes response formats."
        )
    else:
        df = pd.DataFrame([record.__dict__ for record in records])
        st.success(f"Found {len(df)} availability records.")
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "Download results CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="ontario_parks_availability.csv",
            mime="text/csv",
        )
