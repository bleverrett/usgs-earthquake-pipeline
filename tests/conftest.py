import gc

import pytest
import requests

import analysis
import pipeline


@pytest.fixture(autouse=True)
def offline_test_environment(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("Tests must mock HTTP requests; live network access is disabled.")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_request)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(analysis.webbrowser, "open", lambda url: True)
    yield
    gc.collect()


@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    database = str(tmp_path / "test_earthquakes.db")
    monkeypatch.setattr(pipeline, "DB_NAME", database)
    monkeypatch.setattr(analysis, "DB_NAME", database)
    monkeypatch.setattr(analysis, "OUTPUT_DIR", tmp_path)
    pipeline.setup_database()
    return database
