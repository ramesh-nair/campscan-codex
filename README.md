# CampScan (Ontario Parks)

A small Streamlit app that scans Ontario Parks reservation result pages for campsite availability.

## Features

- Set arrival/departure dates.
- Set party size and equipment IDs required by the Ontario Parks search flow.
- Scan multiple campgrounds in one run (each campground is a name + Ontario Parks search URL).
- Export scraped availability rows to CSV.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m playwright install chromium
streamlit run src/campscan/app.py
```

Open the app, paste your campground lines in this format:

```text
Algonquin - Lake of Two Rivers | https://reservations.ontarioparks.ca/create-booking/results?resourceLocationId=-2147482628
Killbear - George Lake | https://reservations.ontarioparks.ca/create-booking/results?resourceLocationId=-2147482518
```

## Notes

- Ontario Parks can block automated requests. This app uses a real browser (Playwright) and inspects JSON responses + rendered text.
- If no rows are found, first verify your URL works manually in a browser and includes the correct park/campground identifiers.
