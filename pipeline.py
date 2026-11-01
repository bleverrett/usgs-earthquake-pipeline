import sqlite3
import pandas as pd
import requests
from io import StringIO
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_NAME = str(PROJECT_ROOT / "earthquakes.db")
BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"

def setup_database():
    """Reads schema.sql and prepares clean local SQLite tables."""
    print("Initializing database schema...")
    with sqlite3.connect(DB_NAME) as conn:
        with open(SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()

def fetch_and_ingest_earthquakes():
    """Loops through historical windows sequentially to dynamically compile a 10MB+ dataset."""
    print("Initiating historical data paging loop to clear the 10MB constraint...")
    
    # 6 distinct 30-day time brackets to stack data up to 12MB+ safely under server caps
    time_windows = [
        ("2026-09-30", "2026-10-30"),
        ("2026-08-30", "2026-09-30"),
        ("2026-07-30", "2026-08-30"),
        ("2026-06-30", "2026-07-30"),
        ("2026-05-30", "2026-06-30"),
        ("2026-04-30", "2026-05-30")
    ]
    
    all_chunks_text = []
    total_raw_bytes = 0
    
    for start_date, end_date in time_windows:
        print(f" -> Extracting raw ledger chunk between {start_date} and {end_date}...")
        
        # Build query parameters ensuring format is strictly CSV
        params = {
            'format': 'csv',
            'starttime': start_date,
            'endtime': end_date,
            'limit': '20000' # Stay safe under server single-query ceilings
        }
        
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            if response.status_code == 200:
                chunk_bytes = len(response.content)
                total_raw_bytes += chunk_bytes
                all_chunks_text.append(response.text)
            else:
                print(f"    [WARNING] Chunk failed with status: {response.status_code}")
        except Exception as e:
            print(f"    [WARNING] Connection glitch on chunk extraction: {e}")
            
        time.sleep(0.5) # Polite API rate-limiting buffer spacing

    print("\n" + "="*60)
    print("DYNAMIC NETWORK EXTRACTION LOOP COMPLETE")
    print(f"Combined Verifiable Raw Data Stream Size: {total_raw_bytes / (1024*1024):.2f} MB")
    print("="*60 + "\n")

    # Ingest each chunk into the database frames
    print("Commencing transactional database parsing allocations...")
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        total_inserted = 0

        for chunk_text in all_chunks_text:
            # Parse individual string segments safely
            df = pd.read_csv(StringIO(chunk_text), on_bad_lines='skip')
            
            for _, row in df.iterrows():
                event_id = str(row.get('id', '')).strip()
                place = str(row.get('place', 'Unknown')).strip()
                
                try:
                    mag = float(row.get('mag')) if pd.notna(row.get('mag')) else None
                    depth = float(row.get('depth')) if pd.notna(row.get('depth')) else None
                    lat = float(row.get('latitude')) if pd.notna(row.get('latitude')) else None
                    lon = float(row.get('longitude')) if pd.notna(row.get('longitude')) else None
                except (ValueError, TypeError):
                    continue

                if not event_id or event_id == 'nan' or event_id == 'id':
                    continue

                # Normalization dimension tracking mapping
                cursor.execute("INSERT OR IGNORE INTO locations (place_name) VALUES (?)", (place,))
                cursor.execute("SELECT location_id FROM locations WHERE place_name = ?", (place,))
                location_id = cursor.fetchone()[0]

                # Fact insertion driven by unique key idempotency
                cursor.execute("""
                    INSERT OR IGNORE INTO earthquakes 
                    (event_id, time_timestamp, latitude, longitude, depth, mag, mag_type, location_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, row.get('time'), lat, lon, depth, mag, row.get('magType'), location_id))
                
                total_inserted += 1

        conn.commit()
    print(f"[SUCCESS] Relational databanks populated completely. Total row events handled: {total_inserted}")

if __name__ == "__main__":
    setup_database()
    fetch_and_ingest_earthquakes()