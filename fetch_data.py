"""
ESIOS data fetcher for the Doran Iberian Energy Dashboard.

Reads config.json, pulls each indicator from the ESIOS API,
and saves results as JSON files in the data/ directory.

Usage:
    py fetch_data.py --mode frequent    # market-hours refresh
    py fetch_data.py --mode daily       # once-daily capacity refresh
    py fetch_data.py --mode all         # both (initial seed)

Env var:
    ESIOS_TOKEN — your ESIOS API token
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ESIOS_TOKEN = os.environ.get("ESIOS_TOKEN", "")

HEADERS = {
    "Accept": "application/json; application/vnd.esios-api-v2+json",
    "Content-Type": "application/json",
    "x-api-key": ESIOS_TOKEN,
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_indicator(base_url, indicator_id, start, end):
    url = f"{base_url}/{indicator_id}"
    params = {
        "start_date": start,
        "end_date": end,
    }
    r = requests.get(url, headers=HEADERS, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def get_date_range(mode):
    """Return (start, end) ISO strings for the fetch window."""
    now = datetime.now(timezone.utc)

    if mode == "daily":
        # Capacity: last 365 days (slow-moving data)
        start = now - timedelta(days=365)
    else:
        # Frequent: last 7 days gives enough for comparisons
        start = now - timedelta(days=7)

    return (
        start.strftime("%Y-%m-%dT%H:%M"),
        now.strftime("%Y-%m-%dT%H:%M"),
    )


def collect_indicator_ids(config, mode):
    """Gather all indicator IDs and names for the given mode."""
    ids = {}

    if mode in ("frequent", "all"):
        for section_key, section in config.get("frequent", {}).items():
            if section_key.startswith("_"):
                continue
            for ind_id, name in section.items():
                ids[ind_id] = name

    if mode in ("daily", "all"):
        for section_key, section in config.get("daily", {}).items():
            if section_key.startswith("_"):
                continue
            for ind_id, name in section.items():
                ids[ind_id] = name

    return ids


def main():
    mode = "frequent"
    if len(sys.argv) > 2 and sys.argv[1] == "--mode":
        mode = sys.argv[2]

    if not ESIOS_TOKEN:
        print("ERROR: ESIOS_TOKEN environment variable not set.")
        sys.exit(1)

    config = load_config()
    base_url = config["esios_base_url"]
    indicators = collect_indicator_ids(config, mode)

    os.makedirs(DATA_DIR, exist_ok=True)

    start, end = get_date_range(mode)

    print(f"Mode: {mode}")
    print(f"Fetching {len(indicators)} indicators")
    print(f"Range: {start} -> {end}")
    print("-" * 60)

    success = 0
    errors = 0

    for ind_id, name in indicators.items():
        try:
            print(f"  {ind_id} — {name}...", end=" ", flush=True)
            data = fetch_indicator(base_url, ind_id, start, end)

            # Extract just the values array + metadata we need
            indicator = data.get("indicator", {})
            output = {
                "id": ind_id,
                "name": indicator.get("name", name),
                "short_name": indicator.get("short_name", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "start": start,
                "end": end,
                "values": indicator.get("values", []),
            }

            out_path = os.path.join(DATA_DIR, f"{ind_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False)

            print(f"OK ({len(output['values'])} values)")
            success += 1

        except Exception as e:
            print(f"FAILED — {e}")
            errors += 1

    # Write a metadata file so the dashboard knows when data was last refreshed
    meta = {
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "indicators_fetched": success,
        "errors": errors,
    }
    with open(os.path.join(DATA_DIR, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"Done. {success} OK, {errors} failed.")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
