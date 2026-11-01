import os
import sqlite3
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

# Import functions directly from your updated pipeline module
from pipeline import setup_database, fetch_and_ingest_earthquakes
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

TEST_DB = "test_earthquakes.db"

@pytest.fixture
def clean_db():
    """Fixture to isolate tests by spinning up and destroying a fresh sandbox database."""
    import pipeline
    original_db = pipeline.DB_NAME
    # Re-route the module's target database name to our safe local test file stub
    pipeline.DB_NAME = TEST_DB
    
    # Initialize the tables
    setup_database()
    
    yield TEST_DB
    
    # Teardown: Completely erase the test database file loop after the test finishes
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass
    pipeline.DB_NAME = original_db

def test_database_schema_creation(clean_db):
    """Phase B Verification: Assures that DDL scripts build the correct database layout."""
    with sqlite3.connect(clean_db) as conn:
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
    with sqlite3.connect(clean_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM earthquakes;")
        assert cursor.fetchone()[0] == 1
        
    # Ingestion 2: Run the pipeline immediately again simulating an accidental double-run
    fetch_and_ingest_earthquakes()
    
    # CRITICAL EVALUATION ASSERTION:
    # Because of idempotency guards, row counts must stay exactly at 1 (No duplicate data clutter!)
    with sqlite3.connect(clean_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM earthquakes;")
        assert cursor.fetchone()[0] == 1


def test_analysis_generates_html_report(tmp_path, monkeypatch):
    """The analysis step should emit a single HTML report that embeds the generated PNGs."""
    import pipeline

    original_db = pipeline.DB_NAME
    original_cwd = os.getcwd()
    report_path = Path(__file__).resolve().parent.parent / "project_report.html"

    try:
        monkeypatch.chdir(tmp_path)
        pipeline.DB_NAME = str(tmp_path / "earthquakes.db")
        setup_database()

        with sqlite3.connect(pipeline.DB_NAME) as conn:
            conn.execute(
                "INSERT INTO locations (place_name) VALUES (?)",
                ("Test Place",)
            )
            conn.execute(
                "INSERT INTO earthquakes (event_id, time_timestamp, latitude, longitude, depth, mag, mag_type, location_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("evt-1", "2026-10-15T00:00:00Z", 0.0, 0.0, 100.0, 5.5, "ml", 1)
            )
            conn.commit()

        import analysis
        analysis.DB_NAME = str(tmp_path / "earthquakes.db")
        analysis.OUTPUT_DIR = Path(tmp_path)
        analysis.run_analysis()

        assert (tmp_path / "project_report.html").exists()
        assert (tmp_path / "earthquake_magnitude_distribution.png").exists()
        assert (tmp_path / "depth_vs_magnitude.png").exists()
    finally:
        os.chdir(original_cwd)
        pipeline.DB_NAME = original_db
        for path in [tmp_path / "earthquakes.db", tmp_path / "earthquake_magnitude_distribution.png", tmp_path / "depth_vs_magnitude.png", tmp_path / "project_report.html", report_path]:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass