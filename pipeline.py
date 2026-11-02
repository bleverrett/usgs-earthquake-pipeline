import csv
import math
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent
DB_NAME = str(PROJECT_ROOT / "earthquakes.db")
BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
WINDOW_DAYS = 30
WINDOW_COUNT = 6
REQUEST_LIMIT = 20000
MAX_REQUEST_ATTEMPTS = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
REQUIRED_CSV_COLUMNS = {"id", "time", "latitude", "longitude"}


def setup_database():
    """Reads schema.sql and prepares clean local SQLite tables."""
    print("Initializing database schema...")
    with closing(sqlite3.connect(DB_NAME)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with open(SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()


def _build_time_windows(as_of=None):
    """Build six adjacent 30-day UTC windows ending at the current time."""
    end_time = as_of or datetime.now(timezone.utc)
    if end_time.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    end_time = end_time.astimezone(timezone.utc).replace(microsecond=0)
    window_length = timedelta(days=WINDOW_DAYS)
    first_start = end_time - window_length * WINDOW_COUNT

    windows = []
    for index in range(WINDOW_COUNT):
        start = first_start + window_length * index
        end = start + window_length
        windows.append(
            (start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S"))
        )
    return windows


def _fetch_window(start_time, end_time):
    """Fetch one CSV window, retrying transient network and server failures."""
    params = {
        "format": "csv",
        "starttime": start_time,
        "endtime": end_time,
        "limit": str(REQUEST_LIMIT),
    }

    last_error = None
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_REQUEST_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
                continue
            break

        if response.status_code == 200:
            return response

        message = f"HTTP {response.status_code}"
        if response.status_code not in RETRYABLE_STATUS_CODES:
            raise RuntimeError(message)
        last_error = RuntimeError(message)
        if attempt < MAX_REQUEST_ATTEMPTS:
            time.sleep(2 ** (attempt - 1))

    raise RuntimeError(
        f"request failed after {MAX_REQUEST_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _normalize_event_time(value):
    """Parse a timezone-aware event time and return it in UTC with milliseconds."""
    parsed = datetime.fromisoformat(_clean_text(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event time must include a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _parse_optional_float(value):
    text = _clean_text(value)
    if not text:
        return None
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("number must be finite")
    return number


def _parse_csv_chunk(chunk_text, window):
    """Validate a CSV chunk and return usable rows plus rejected-row counts."""
    reader = csv.DictReader(StringIO(chunk_text), strict=True)
    if not reader.fieldnames or not REQUIRED_CSV_COLUMNS.issubset(reader.fieldnames):
        missing = REQUIRED_CSV_COLUMNS.difference(reader.fieldnames or [])
        raise ValueError(f"{window}: CSV is missing required columns: {sorted(missing)}")

    records = []
    rejected = {}
    rows_seen = 0
    try:
        for row in reader:
            rows_seen += 1
            if rows_seen >= REQUEST_LIMIT:
                raise ValueError(
                    f"{window}: response reached the {REQUEST_LIMIT}-record "
                    "limit; reduce the time-window size to verify completeness"
                )
            reason = None
            if None in row:
                reason = "malformed column count"
            else:
                event_id = _clean_text(row.get("id"))
                event_time = _clean_text(row.get("time"))
                if not event_id or event_id.lower() == "nan":
                    reason = "missing event id"
                elif not event_time:
                    reason = "missing event time"
                else:
                    try:
                        event_time = _normalize_event_time(event_time)
                    except ValueError:
                        reason = "invalid event time"

                    if not reason:
                        try:
                            latitude = _parse_optional_float(row.get("latitude"))
                            longitude = _parse_optional_float(row.get("longitude"))
                            depth = _parse_optional_float(row.get("depth"))
                            magnitude = _parse_optional_float(row.get("mag"))
                            if latitude is None or longitude is None:
                                raise ValueError("missing coordinates")
                            if not -90 <= latitude <= 90:
                                raise ValueError("latitude out of range")
                            if not -180 <= longitude <= 180:
                                raise ValueError("longitude out of range")
                        except (TypeError, ValueError, OverflowError) as exc:
                            reason = str(exc) or "invalid numeric value"

            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue

            records.append(
                (
                    event_id,
                    event_time,
                    latitude,
                    longitude,
                    depth,
                    magnitude,
                    _clean_text(row.get("magType")) or None,
                    _clean_text(row.get("place")) or "Unknown",
                )
            )
    except csv.Error as exc:
        raise ValueError(f"{window}: malformed CSV: {exc}") from exc

    return records, rejected


def fetch_and_ingest_earthquakes():
    """Fetch six recent windows and ingest them only after complete validation."""
    time_windows = _build_time_windows()
    all_chunks = []
    failed_windows = []
    total_raw_bytes = 0

    print(f"Fetching {len(time_windows)} recent {WINDOW_DAYS}-day USGS windows...")
    for index, (start_time, end_time) in enumerate(time_windows):
        window = f"{start_time} to {end_time}"
        print(f" -> Extracting window {index + 1}/{len(time_windows)}: {window}")
        try:
            response = _fetch_window(start_time, end_time)
            chunk_text = response.text
            total_raw_bytes += len(response.content)
            records, rejected = _parse_csv_chunk(chunk_text, window)
            all_chunks.append((records, rejected))
        except (RuntimeError, ValueError) as exc:
            failed_windows.append(str(exc))
        if index < len(time_windows) - 1:
            time.sleep(0.5)

    if failed_windows:
        details = "; ".join(failed_windows)
        raise RuntimeError(
            f"Ingestion aborted: {len(failed_windows)} of {len(time_windows)} "
            f"windows failed; no records were written. {details}"
        )

    print(f"All {len(time_windows)} windows fetched and parsed successfully.")
    print(f"Combined raw response size: {total_raw_bytes / (1024 * 1024):.2f} MB")

    total_inserted = 0
    total_duplicates = 0
    rejected_rows = {}
    with closing(sqlite3.connect(DB_NAME)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        for records, rejected in all_chunks:
            for reason, count in rejected.items():
                rejected_rows[reason] = rejected_rows.get(reason, 0) + count

            for record in records:
                place = record[7]
                cursor.execute(
                    "INSERT OR IGNORE INTO locations (place_name) VALUES (?)",
                    (place,),
                )
                cursor.execute(
                    "SELECT location_id FROM locations WHERE place_name = ?",
                    (place,),
                )
                location_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO earthquakes
                    (event_id, time_timestamp, latitude, longitude, depth, mag,
                     mag_type, location_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*record[:7], location_id),
                )
                if cursor.rowcount:
                    total_inserted += 1
                else:
                    total_duplicates += 1

        conn.commit()

    rejected_total = sum(rejected_rows.values())
    print(
        f"Ingestion complete: {total_inserted} inserted, "
        f"{total_duplicates} duplicates ignored, {rejected_total} rows rejected."
    )
    for reason, count in sorted(rejected_rows.items()):
        print(f" -> Rejected {count}: {reason}")


if __name__ == "__main__":
    setup_database()
    fetch_and_ingest_earthquakes()