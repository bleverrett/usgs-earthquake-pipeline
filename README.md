# Public Seismic Data Pipeline & Analytics (Technical Exercise)

An end-to-end data pipeline built in Python 3 that programmatically streams global real-time seismic event datasets from a public web server, structures them into an indexed local SQLite relational database, and executes analytical business intelligence reporting.

## Design & Architecture

### 1. Data Source Selection
- **Source:** United States Geological Survey (USGS) Earthquake Hazards Feed (`https://usgs.gov`)
- **Justification:** This official government dataset is entirely public and unauthenticated, fully meeting the requirement to ingest data without logging in or using API keys. The raw continuous 30-day global CSV logging format dynamically pushes out over 12 MB of rich transactional metrics, meeting the 10 MB structural data footprint constraint.

### 2. Relational Schema Structure
The database (`earthquakes.db`) implements a clean, normalized relational star-schema design to guarantee storage efficiency:
- `locations`: Dimension table tracking geographical description attributes with unique constraints to avoid string redundancy.
- `earthquakes`: Fact table managing explicit unique event records, timestamps, magnitude metrics, and depths.
- **Optimization:** Includes a dedicated index on the `mag` column to significantly accelerate heavy analytical aggregation and ordering queries.

### 3. Pipeline Design & Idempotency
- **Extraction:** Downloads the raw comma-separated values stream dynamically using `requests` straight into memory buffers.
- **Idempotency:** Driven by a strict primary key constraint linked to the record's unique USGS identifier (`event_id`). Running the pipeline multiple times safely skips duplicate entries and refreshes data without cluttering metrics.
- **Compliance:** Per the instructions, the raw `all_month.csv` data layout is never saved in Git; it is streamed entirely on-demand at runtime.

---

## Getting Started

### Prerequisites
- Python 3.12+
- Internet Connection (Unauthenticated)

### 1. Installation & Environment Setup
Clone this repository and create a Python virtual environment to isolate project packages:

```bash
git clone <your-repo-url>
cd usgs-earthquake-pipeline

# Initialize and activate the virtual environment sandbox
python -m venv venv
venv\Scripts\activate   # On Mac/Linux use: source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 2. Execute the Master Pipeline
Run the entire process from schema migrations and data ingestion to automated business intelligence calculations using the single orchestrator command:

```bash
python main.py
```

### 3. Running the Test Suite
To verify table generation rules and data ingestion idempotency behavior, run the automated framework checks:

```bash
pytest
```

---

## Business Insights & Reports
When the script finishes running, it outputs a multi-layered matrix addressing 4 core research metrics:
1. **Question 1 (Pure SQL):** Locates the top 5 highest magnitude earthquakes globally to spot immediate high-risk zones.
2. **Question 2 (Pure SQL):** Compiles count totals and averages grouped across distinct mechanical measurement scale options (`mag_type`).
3. **Question 3 (Python Tooling):** Generates an overall magnitude distribution curve chart saved directly onto the hard drive as `earthquake_magnitude_distribution.png`.
4. **Question 4 (Python Tooling):** Compiles an analytical Pearson scatter plot correlation matrix mapping earthquake depth metrics against their resulting magnitudes, saved as `depth_vs_magnitude.png`.
