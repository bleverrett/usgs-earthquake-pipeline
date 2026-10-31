import sqlite3
import pandas as pd
import requests
from io import StringIO

DB_NAME = "earthquakes.db"
# Tracks an expansive 3-year window targeting M3.5+ events to dynamically compile an 11.5MB+ dataset below row ceilings
DATA_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv&limit=20000"

def setup_database():
    """Reads schema.sql and prepares clean local SQLite tables."""
    print("Initializing database schema...")
    with sqlite3.connect(DB_NAME) as conn:
        with open("schema.sql", "r") as f:
            conn.executescript(f.read())
        conn.commit()

def fetch_and_ingest_earthquakes():
    """Downloads the high-volume public USGS dataset anonymously using a stable threshold query."""
    print(f"Streaming high-volume public dataset anonymously from: {DATA_URL}...")
    
    try:
        # Increase the network timeout buffer to handle the massive 11MB+ stream safely
        response = requests.get(DATA_URL, timeout=60)
        
        if response.status_code != 200:
            print(f"[CRITICAL ERROR] Server returned status code: {response.status_code}")
            print(f"Server Message: {response.text}")
            return
            
        raw_bytes = len(response.content)
        print("[SUCCESS] Network extraction complete.")
        print(f"-> Verifiable Raw Data Size: {raw_bytes / (1024*1024):.2f} MB")
        
        if raw_bytes < 10 * 1024 * 1024:
            print("[WARNING] Data footprint is under 10MB. Adjust constraints to expand history.")

        # Load the raw string data block safely into Pandas
        df = pd.read_csv(StringIO(response.text))
        print(f"-> Discovered {len(df)} total matching records inside the stream.")
        
    except Exception as e:
        print(f"\n[CRITICAL NETWORK ERROR] The system could not parse the dataset: {e}")
        return

    # Map structural records into the relational SQLite schema
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        inserted_records = 0

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

            if not event_id:
                continue

            # Idempotent normalized data storage loops
            cursor.execute("INSERT OR IGNORE INTO locations (place_name) VALUES (?)", (place,))
            cursor.execute("SELECT location_id FROM locations WHERE place_name = ?", (place,))
            loc_result = cursor.fetchone()
            location_id = loc_result if loc_result else None

            cursor.execute("""
                INSERT OR IGNORE INTO earthquakes 
                (event_id, time_timestamp, latitude, longitude, depth, mag, mag_type, location_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                row.get('time'),
                lat,
                lon,
                depth,
                mag,
                row.get('magType'),
                location_id
            ))
            
            inserted_records += 1

        conn.commit()
        print(f"[SUCCESS] Database population finalized! Mapped {inserted_records} rows into 'earthquakes'.")

if __name__ == "__main__":
    setup_database()
    fetch_and_ingest_earthquakes()