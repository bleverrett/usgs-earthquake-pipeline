import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

import analysis
import main
import pipeline


HEADER = "id,time,latitude,longitude,depth,mag,magType,place\n"


def csv_response(text):
    return Mock(status_code=200, text=text, content=text.encode("utf-8"))


@pytest.mark.parametrize("payload", ["", "<html>error</html>", "id,time\n"])
def test_missing_csv_headers_abort(payload):
    with pytest.raises(ValueError, match="missing required columns"):
        pipeline._parse_csv_chunk(payload, "test window")


def test_unclosed_csv_quote_is_reported():
    with pytest.raises(ValueError, match="malformed CSV"):
        pipeline._parse_csv_chunk(HEADER + '"unterminated', "test window")


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("evt,2026-10-31T00:00:00Z,1,2,3,4,ml,Place,extra", "malformed column count"),
        ("evt,2026-10-31T00:00:00Z,,2,3,4,ml,Place", "missing coordinates"),
        ("evt,2026-10-31T00:00:00Z,1,181,3,4,ml,Place", "longitude out of range"),
        ("evt,2026-10-31T00:00:00Z,1,2,inf,4,ml,Place", "number must be finite"),
    ],
)
def test_invalid_rows_have_explicit_rejection_reasons(row, reason):
    records, rejected = pipeline._parse_csv_chunk(HEADER + row + "\n", "test window")
    assert records == []
    assert rejected == {reason: 1}


def test_missing_optional_csv_columns_are_null():
    records, rejected = pipeline._parse_csv_chunk(
        "id,time,latitude,longitude\n"
        "evt,2026-10-31T00:00:00Z,1,2\n",
        "test window",
    )
    assert rejected == {}
    assert records[0][4:] == (None, None, None, "Unknown")


def test_naive_window_anchor_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        pipeline._build_time_windows(datetime(2026, 11, 1))


def test_timeout_recovers_with_bounded_backoff(monkeypatch):
    response = csv_response(HEADER)
    get = Mock(side_effect=[requests.Timeout("timeout"), response])
    sleep = Mock()
    monkeypatch.setattr(pipeline.requests, "get", get)
    monkeypatch.setattr(pipeline.time, "sleep", sleep)

    assert pipeline._fetch_window("2026-10-01", "2026-11-01") is response
    assert get.call_count == 2
    assert get.call_args.kwargs["timeout"] == 30
    sleep.assert_called_once_with(1)


def test_timeout_exhaustion_preserves_cause(monkeypatch):
    error = requests.Timeout("timeout")
    get = Mock(side_effect=error)
    monkeypatch.setattr(pipeline.requests, "get", get)

    with pytest.raises(RuntimeError, match="after 3 attempts") as failure:
        pipeline._fetch_window("2026-10-01", "2026-11-01")

    assert get.call_count == 3
    assert failure.value.__cause__ is error


def test_database_failure_rolls_back_every_insert(clean_db, monkeypatch):
    with closing(sqlite3.connect(clean_db)) as conn, conn:
        conn.execute(
            """
            CREATE TRIGGER reject_second_event BEFORE INSERT ON earthquakes
            WHEN NEW.event_id = 'second'
            BEGIN
                SELECT RAISE(ABORT, 'test database failure');
            END;
            """
        )
    response = csv_response(
        HEADER
        + "first,2026-10-31T00:00:00Z,1,2,3,4,ml,First Place\n"
        + "second,2026-10-31T00:00:00Z,1,2,3,4,ml,Second Place\n"
    )
    monkeypatch.setattr(pipeline.requests, "get", Mock(return_value=response))

    with pytest.raises(sqlite3.IntegrityError, match="test database failure"):
        pipeline.fetch_and_ingest_earthquakes()

    with closing(sqlite3.connect(clean_db)) as conn, conn:
        assert conn.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0


def test_offline_master_workflow_produces_reports(clean_db, tmp_path, monkeypatch):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = csv_response(
        HEADER + f"evt,{timestamp},35,-120,10,4,ml,Test Place\n"
    )
    monkeypatch.setattr(pipeline.requests, "get", Mock(return_value=response))

    main.main()

    with closing(sqlite3.connect(clean_db)) as conn, conn:
        assert conn.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0] == 1
    html = (tmp_path / "project_report.html").read_text(encoding="utf-8")
    assert "Test Place" in html
    assert "Depth/Magnitude Correlation: N/A" in html
    for name in ("earthquake_magnitude_distribution.png", "depth_vs_magnitude.png"):
        assert (tmp_path / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("failed_stage", ["setup_database", "fetch_and_ingest_earthquakes", "run_analysis"])
def test_master_workflow_failure_exits_nonzero(failed_stage, monkeypatch, capsys):
    stages = {
        name: Mock()
        for name in ("setup_database", "fetch_and_ingest_earthquakes", "run_analysis")
    }
    stages[failed_stage].side_effect = RuntimeError("test workflow failure")
    for name, stage in stages.items():
        monkeypatch.setattr(main, name, stage)

    with pytest.raises(SystemExit) as failure:
        main.main()

    assert failure.value.code == 1
    assert "test workflow failure" in capsys.readouterr().out
    names = list(stages)
    for name in names[names.index(failed_stage) + 1:]:
        stages[name].assert_not_called()


def test_empty_database_does_not_create_success_report(clean_db, tmp_path, capsys):
    analysis.run_analysis()
    assert "Database table is empty" in capsys.readouterr().out
    assert not (tmp_path / "project_report.html").exists()


def test_html_escapes_location_text_and_reports_browser_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        analysis.webbrowser, "open", Mock(side_effect=OSError("browser unavailable"))
    )
    analysis.write_html_report(
        tmp_path,
        pd.DataFrame({"place_name": ["<script>not markup</script>"]}),
        pd.DataFrame(),
        None,
    )
    html = (tmp_path / "project_report.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;not markup&lt;/script&gt;" in html
    assert "<script>not markup</script>" not in html
    assert "Could not open the report automatically" in capsys.readouterr().out
