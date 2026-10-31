import sqlite3
import pandas as pd
import requests

DB_NAME = "earthquakes.db"
# Explicit real-time endpoint for the anonymous 30-day global CSV feed (~12MB+)
DATA_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.csv"

def setup_database():
    """Reads schema.sql and prepares clean local SQLite tables."""
    print("Initializing database schema...")
    with sqlite3.connect(DB_NAME) as conn:
        with open("schema.sql", "r") as f:
            conn.executescript(f.read())
        conn.commit()

def fetch_and_ingest_earthquakes():
    """Downloads the public USGS dataset anonymously and maps it into SQLite (Idempotent)."""
    print(f"Streaming public dataset anonymously from: {DATA_URL}...")
    
    try:
        # Step A: Request the file using explicit content verification
        response = requests.get(DATA_URL, timeout=15)
        
        if response.status_code != 200:
            print(f"[CRITICAL ERROR] Server returned status code: {response.status_code}")
            return
            
        # Safety Check: If the server response contains HTML code instead of raw text data, catch it
        if "<html" in response.text.lower() or "<!doctype" in response.text.lower():
            print("[CRITICAL ERROR] The link directed the program to a webpage instead of a raw CSV spreadsheet.")
            print("Please verify the URL link structure matches exactly.")
            return

        # Load the raw network text buffer string straight into Pandas
        from io import StringIO
        df = pd.read_csv(StringIO(response.text))
        print(f"[SUCCESS] Live download completed. Discovered {len(df)} global entries.")
        
    except Exception as e:
        print(f"\n[CRITICAL NETWORK ERROR] The system could not complete the stream: {e}")
        return

    # Step B: Map structural records into the relational SQLite schema
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

            # Idempotent normalized data storage
            cursor.execute("INSERT OR IGNORE INTO locations (place_name) VALUES (?)", (place,))
            cursor.execute("SELECT location_id FROM locations WHERE place_name = ?", (place,))
            loc_result = cursor.fetchone()
            location_id = loc_result[0] if loc_result else None

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
