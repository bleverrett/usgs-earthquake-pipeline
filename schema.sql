-- schema.sql
-- 1. Dimension table tracking geographic text locations cleanly to avoid data redundancy
CREATE TABLE IF NOT EXISTS locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_name TEXT UNIQUE NOT NULL
);

-- 2. Fact table managing granular metrics and unique event signatures
CREATE TABLE IF NOT EXISTS earthquakes (
    event_id TEXT PRIMARY KEY,
    time_timestamp TEXT,
    latitude REAL,
    longitude REAL,
    depth REAL,
    mag REAL,
    mag_type TEXT,
    location_id INTEGER,
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);

-- 3. Optimization constraint to speed up analytical sorting lookups
CREATE INDEX IF NOT EXISTS idx_earthquake_mag ON earthquakes(mag);