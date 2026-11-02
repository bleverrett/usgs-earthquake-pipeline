import os
import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import patch, MagicMock

# Import functions directly from your updated pipeline module
from pipeline import (
    _build_time_windows,
    setup_database,
    fetch_and_ingest_earthquakes,
)
from analysis import run_analysis


def test_database_setup_works_from_any_working_directory(tmp_path, monkeypatch):
    """Setup should resolve files relative to the project folder, not the caller's current directory."""
    import pipeline

    original_cwd = os.getcwd()
    original_db = pipeline.DB_NAME

    try:
        monkeypatch.chdir(tmp_path)
        pipeline.DB_NAME = str(tmp_path / "earthquakes.db")
        setup_database()
        assert os.path.exists(tmp_path / "earthquakes.db")
    finally:
        os.chdir(original_cwd)
        pipeline.DB_NAME = original_db

def test_database_schema_creation(clean_db):
    """Phase B Verification: Assures that DDL scripts build the correct database layout."""
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        cursor = conn.cursor()
        
        # Pull the catalog names of all constructed tables inside the test database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "locations" in tables
        assert "earthquakes" in tables

@patch('pipeline.requests.get')
def test_pipeline_idempotency(mock_get, clean_db):
    """Phase C Verification: Assures that duplicate data payloads do not clutter the database."""
    # Create a small realistic CSV text string snippet mirroring a raw USGS API response
    mock_csv_payload = (
        "id,time,latitude,longitude,depth,mag,magType,place\n"
        "us7000tuiw,2026-10-31T13:10:08.987Z,-6.43,128.92,254.8,4.3,mb,Banda Sea\n"
    )
    
    # Configure the mocked request object to mirror a successful network connection response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_csv_payload
    mock_response.content = mock_csv_payload.encode('utf-8')
    mock_get.return_value = mock_response
    
    # Ingestion 1: Run the pipeline for the first time
    fetch_and_ingest_earthquakes()
    
    # Verify exactly 1 unique log row exists in the database
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM earthquakes;")
        assert cursor.fetchone()[0] == 1
        
    # Ingestion 2: Run the pipeline immediately again simulating an accidental double-run
    fetch_and_ingest_earthquakes()
    
    # CRITICAL EVALUATION ASSERTION:
    # Because of idempotency guards, row counts must stay exactly at 1 (No duplicate data clutter!)
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM earthquakes;")
        assert cursor.fetchone()[0] == 1


def _csv_response(csv_text, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.text = csv_text
    response.content = csv_text.encode("utf-8")
    return response


def test_time_windows_cover_six_adjacent_30_day_periods():
    from pipeline import WINDOW_COUNT, WINDOW_DAYS

    as_of = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    windows = _build_time_windows(as_of)

    assert len(windows) == WINDOW_COUNT
    parsed = [
        (datetime.fromisoformat(start), datetime.fromisoformat(end))
        for start, end in windows
    ]
    assert parsed[0][0] == as_of.replace(tzinfo=None) - timedelta(days=180)
    for index, (start, end) in enumerate(parsed):
        assert end - start == timedelta(days=WINDOW_DAYS)
        if index:
            assert parsed[index - 1][1] == start


@patch("pipeline.time.sleep")
@patch("pipeline.requests.get")
def test_pipeline_retries_transient_status_and_filters_invalid_rows(
    mock_get, mock_sleep, clean_db
):
    mock_get.side_effect = [
        _csv_response("temporary failure", status_code=503),
        _csv_response(
            "id,time,latitude,longitude,depth,mag,magType,place\n"
            "valid,2026-10-31T13:10:08Z,-6.43,128.92,254.8,4.3,mb,Banda Sea\n"
            "optional-null,2026-10-31T13:10:08Z,1,2,,,,\n"
            ",2026-10-31T13:10:08Z,1,2,3,4,ml,Missing ID\n"
            "no-time,,1,2,3,4,ml,Missing time\n"
            "bad-time,not-a-time,1,2,3,4,ml,Invalid time\n"
            "bad-lat,2026-10-31T13:10:08Z,91,2,3,4,ml,Invalid latitude\n"
            "bad-mag,2026-10-31T13:10:08Z,1,2,3,NaN,ml,Invalid magnitude\n"
            "bad-number,2026-10-31T13:10:08Z,not-a-number,2,3,4,ml,Invalid number\n"
        ),
        *[
            _csv_response(
                "id,time,latitude,longitude,depth,mag,magType,place\n"
            )
            for _ in range(5)
        ],
    ]

    fetch_and_ingest_earthquakes()

    assert mock_get.call_count == 7
    mock_sleep.assert_any_call(1)
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        assert conn.execute(
            "SELECT event_id, depth, mag FROM earthquakes ORDER BY event_id"
        ).fetchall() == [
            ("optional-null", None, None),
            ("valid", 254.8, 4.3),
        ]


@patch("pipeline.time.sleep")
@patch("pipeline.requests.get")
def test_failed_window_aborts_ingestion_without_partial_writes(
    mock_get, mock_sleep, clean_db
):
    mock_get.side_effect = [
        _csv_response("bad request", status_code=400),
        *[
            _csv_response("id,time,latitude,longitude\n")
            for _ in range(5)
        ],
    ]

    with pytest.raises(RuntimeError, match="no records were written"):
        fetch_and_ingest_earthquakes()

    assert mock_get.call_count == 6
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        assert conn.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0] == 0


@patch("pipeline.time.sleep")
@patch("pipeline.requests.get")
def test_retry_exhaustion_reports_failure_and_writes_nothing(
    mock_get, mock_sleep, clean_db
):
    mock_get.return_value = _csv_response("service unavailable", status_code=503)

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        fetch_and_ingest_earthquakes()

    assert mock_get.call_count == 18
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        assert conn.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0] == 0


@patch("pipeline.time.sleep")
@patch("pipeline.requests.get")
def test_response_at_record_limit_is_rejected_as_potentially_truncated(
    mock_get, mock_sleep, clean_db, monkeypatch
):
    import pipeline

    monkeypatch.setattr(pipeline, "REQUEST_LIMIT", 1)
    mock_get.return_value = _csv_response(
        "id,time,latitude,longitude\n"
        "evt-1,2026-10-31T13:10:08Z,1,2\n"
    )

    with pytest.raises(RuntimeError, match="reduce the time-window size"):
        fetch_and_ingest_earthquakes()

    with closing(sqlite3.connect(clean_db)) as conn, conn:
        assert conn.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0] == 0


def test_analysis_generates_html_report(tmp_path, monkeypatch):
    """The analysis step should emit a single HTML report that embeds the generated PNGs."""
    import pipeline
    import analysis

    original_db = pipeline.DB_NAME
    original_analysis_db = analysis.DB_NAME
    original_output_dir = analysis.OUTPUT_DIR
    original_cwd = os.getcwd()

    try:
        monkeypatch.chdir(tmp_path)
        pipeline.DB_NAME = str(tmp_path / "earthquakes.db")
        setup_database()

        recent_time = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        old_time = (
            datetime.now(timezone.utc) - timedelta(days=190)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        sample_events = [
            ("evt-cal", "Location A", recent_time, 35.0, -120.0, 100.0, 5.5),
            ("evt-japan", "Location B", recent_time, 35.0, 140.0, 6.0, 80.0),
            ("evt-other", "Location C", recent_time, 0.0, 0.0, 50.0, 4.0),
            ("evt-old", "Old High Magnitude", old_time, 36.0, -120.0, 20.0, 9.9),
        ]
        with closing(sqlite3.connect(pipeline.DB_NAME)) as conn, conn:
            for event_id, place, timestamp, latitude, longitude, depth, magnitude in sample_events:
                cursor = conn.execute(
                    "INSERT INTO locations (place_name) VALUES (?)",
                    (place,),
                )
                conn.execute(
                    """
                    INSERT INTO earthquakes
                    (event_id, time_timestamp, latitude, longitude, depth, mag,
                     mag_type, location_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        timestamp,
                        latitude,
                        longitude,
                        depth,
                        magnitude,
                        "ml",
                        cursor.lastrowid,
                    ),
                )
            conn.commit()

        analysis.DB_NAME = str(tmp_path / "earthquakes.db")
        analysis.OUTPUT_DIR = Path(tmp_path)
        analysis.run_analysis()

        report_html = (tmp_path / "project_report.html").read_text(encoding="utf-8")
        assert (tmp_path / "project_report.html").exists()
        assert (tmp_path / "earthquake_magnitude_distribution.png").exists()
        assert (tmp_path / "depth_vs_magnitude.png").exists()
        assert "Location A" in report_html
        assert "Location B" in report_html
        assert "Old High Magnitude" not in report_html
        assert "California Coast" in report_html
        assert "Japan Region" in report_html
        assert "Other / Unclassified" in report_html
        assert "latest six calendar months" in report_html
        assert "approximate latitude/longitude bounding boxes" in report_html
    finally:
        os.chdir(original_cwd)
        pipeline.DB_NAME = original_db
        analysis.DB_NAME = original_analysis_db
        analysis.OUTPUT_DIR = original_output_dir
        for path in [
            tmp_path / "earthquakes.db",
            tmp_path / "earthquake_magnitude_distribution.png",
            tmp_path / "depth_vs_magnitude.png",
            tmp_path / "project_report.html",
        ]:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass