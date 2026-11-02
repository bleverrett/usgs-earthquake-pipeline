import sqlite3
from contextlib import closing
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parent
DB_NAME = str(PROJECT_ROOT / "earthquakes.db")
OUTPUT_DIR = PROJECT_ROOT
SIX_MONTH_FILTER = "datetime(e.time_timestamp) >= datetime('now', '-6 months')"

SEISMIC_ZONE_CASE = """
    CASE
        WHEN e.latitude IS NULL OR e.longitude IS NULL THEN 'Unknown coordinates'
        WHEN e.latitude BETWEEN 32 AND 42 AND e.longitude BETWEEN -125 AND -114
            THEN 'California Coast'
        WHEN e.latitude BETWEEN 51 AND 72 AND e.longitude BETWEEN -180 AND -129
            THEN 'Alaska and Aleutian Region'
        WHEN e.latitude BETWEEN 24 AND 46 AND e.longitude BETWEEN 122 AND 146
            THEN 'Japan Region'
        WHEN e.latitude BETWEEN -11 AND 7 AND e.longitude BETWEEN 95 AND 141
            THEN 'Indonesia Region'
        WHEN e.latitude BETWEEN 18 AND 23 AND e.longitude BETWEEN -161 AND -154
            THEN 'Hawaii Region'
        WHEN e.latitude BETWEEN 17 AND 20 AND e.longitude BETWEEN -68 AND -64
            THEN 'Puerto Rico Region'
        ELSE 'Other / Unclassified'
    END
"""


def write_html_report(
    output_dir: Path,
    q1_df: pd.DataFrame,
    q2_df: pd.DataFrame,
    corr_value: float | None,
):
    """Create an HTML summary page that includes the generated PNG figures and table results."""
    q1_table = q1_df.to_html(index=False, classes="dataframe", border=0) if not q1_df.empty else "<p>No data available.</p>"
    q2_table = q2_df.to_html(index=False, classes="dataframe", border=0) if not q2_df.empty else "<p>No data available.</p>"

    report_path = output_dir / "project_report.html"
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>USGS Earthquake Pipeline Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 32px; background: #f5f7fa; color: #1f2933; }}
            h1, h2 {{ color: #102a43; }}
            .panel {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
            .images {{ display: flex; flex-wrap: wrap; gap: 20px; }}
            .image-card {{ flex: 1 1 420px; background: white; padding: 12px; border-radius: 8px; border: 1px solid #d9e2ec; }}
            img {{ width: 100%; height: auto; border-radius: 6px; display: block; }}
            table {{ border-collapse: collapse; width: 100%; background: #fff; }}
            th, td {{ border: 1px solid #d9e2ec; padding: 10px; text-align: left; }}
            th {{ background: #eaf2f8; }}
            .metric {{ font-size: 1.1rem; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>USGS Earthquake Pipeline Report</h1>

        <div class="panel">
            <h2>Summary</h2>
            <p class="metric">Depth/Magnitude Correlation: {f"{corr_value:.2f}" if corr_value is not None else "N/A"}</p>
            <p>All analytics cover the latest six calendar months (UTC).</p>
        </div>

        <div class="panel">
            <h2>Top 5 Earthquakes by Magnitude (Latest Six Months)</h2>
            {q1_table}
        </div>

        <div class="panel">
            <h2>Seismic Activity by Approximate Geographic Region</h2>
            <p>Regions are approximate latitude/longitude bounding boxes, not authoritative tectonic plate or fault boundaries. Events outside these boxes are reported as other or unclassified.</p>
            {q2_table}
        </div>

        <div class="panel">
            <h2>Generated Visual Outputs</h2>
            <div class="images">
                <div class="image-card">
                    <h3>Magnitude Distribution</h3>
                    <img src="earthquake_magnitude_distribution.png" alt="Earthquake magnitude distribution">
                </div>
                <div class="image-card">
                    <h3>Depth vs. Magnitude</h3>
                    <img src="depth_vs_magnitude.png" alt="Earthquake depth vs magnitude scatter plot">
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    report_path.write_text(html, encoding="utf-8")
    print(f"[SUCCESS] HTML report created at '{report_path.name}'.")

    try:
        webbrowser.open(report_path.as_uri())
    except Exception as exc:
        print(f"[WARNING] Could not open the report automatically: {exc}")


def run_analysis():
    print("\nConnecting to database framework to isolate reporting metrics...")
    
    # Initialize placeholder DataFrames to safely prevent NameErrors during HTML compilation fallbacks
    q1_df = pd.DataFrame()
    q2_df = pd.DataFrame()
    corr_value = None

    with closing(sqlite3.connect(DB_NAME)) as conn:
        # Check database rows
        check_df = pd.read_sql_query("SELECT COUNT(*) as count FROM earthquakes;", conn)
        if check_df['count'].iloc[0] == 0:
            print("[CRITICAL ERROR] Database table is empty.")
            return

        # -----------------------------------------------------------------
        # Question 1 (Pure SQL): What Are The Top 5 Most Dangerous Earthquake Locations In The Last 6 Months
        # -----------------------------------------------------------------
        print("\n--- Question 1: What Are The Top 5 Most Dangerous Earthquake Locations In The Last 6 Months (Pure SQL) ---")
        sql_q1 = f"""
            SELECT l.place_name, e.mag, e.depth, e.time_timestamp
            FROM earthquakes e
            JOIN locations l ON e.location_id = l.location_id
            WHERE e.mag IS NOT NULL
                AND {SIX_MONTH_FILTER}
            ORDER BY e.mag DESC, e.time_timestamp DESC, e.event_id
            LIMIT 5;
        """
        q1_df = pd.read_sql_query(sql_q1, conn)
        print(q1_df.to_string(index=False))

        # -----------------------------------------------------------------
        # Question 2 (Pure SQL): Tectonic Boundary Zone Risk Analysis
        # -----------------------------------------------------------------
        print("\n--- Question 2: Seismic Concentration by Approximate Region (Pure SQL) ---")
        sql_q2 = f"""
            SELECT 
                {SEISMIC_ZONE_CASE} as seismic_zone,
                COUNT(e.event_id) as total_logged_events,
                ROUND(AVG(e.mag), 2) as average_magnitude,
                ROUND(MAX(e.mag), 1) as peak_magnitude
            FROM earthquakes e
            WHERE e.mag IS NOT NULL
                AND {SIX_MONTH_FILTER}
            GROUP BY seismic_zone
            ORDER BY total_logged_events DESC;
        """
        q2_df = pd.read_sql_query(sql_q2, conn)
        print(q2_df.to_string(index=False))

        # -----------------------------------------------------------------
        # Question 3 (Python Tooling): Overall Magnitude Frequency Distribution
        # -----------------------------------------------------------------
        print("\n--- Question 3: Plotting Overall Magnitude Frequency Distribution (Python Tooling) ---")
        df_q3 = pd.read_sql_query(
            f"SELECT mag FROM earthquakes e WHERE mag IS NOT NULL AND {SIX_MONTH_FILTER};",
            conn,
        )
        try:
            plt.figure(figsize=(10, 4))
            plt.hist(df_q3['mag'], bins=25, color='teal', edgecolor='black', alpha=0.8)
            plt.title("Frequency Distribution of Global Earthquake Magnitudes (Past 6 Months)")
            plt.xlabel("Magnitude Scale")
            plt.ylabel("Event Count")
            plt.grid(True, linestyle="--", alpha=0.5)
            plt.savefig(OUTPUT_DIR / 'earthquake_magnitude_distribution.png')
            plt.close()
            print("[SUCCESS] Distribution curve chart saved as 'earthquake_magnitude_distribution.png'.")
        finally:
            plt.close()

        # -----------------------------------------------------------------
        # Question 4 (Python Tooling): Seismic Depth vs. Magnitude Correlation
        # -----------------------------------------------------------------
        print("\n--- Question 4: Analyzing Event Depth vs. Magnitude Correlation (Python Tooling) ---")
        df_q4 = pd.read_sql_query(
            f"""
            SELECT depth, mag
            FROM earthquakes e
            WHERE depth IS NOT NULL
                AND mag IS NOT NULL
                AND {SIX_MONTH_FILTER};
            """,
            conn,
        )
        try:
            correlation = df_q4["depth"].corr(df_q4["mag"])
            plt.figure(figsize=(10, 5))
            plt.scatter(df_q4['depth'], df_q4['mag'], alpha=0.3, color='purple', s=8)
            plt.title("Seismic Event Depth vs. Resulting Magnitude")
            plt.xlabel("Depth (km)")
            plt.ylabel("Magnitude")
            plt.grid(True, linestyle="--", alpha=0.5)
            plt.savefig(OUTPUT_DIR / 'depth_vs_magnitude.png')
            plt.close()
            print("[SUCCESS] Scatter plot correlation asset saved as 'depth_vs_magnitude.png'.")
            
            corr_value = float(correlation) if pd.notna(correlation) else None
            result = f"{corr_value:.2f}" if corr_value is not None else "N/A"
            print(f"Calculated Depth/Magnitude Correlation: {result}")

        finally:
            plt.close()

    # Safely write the HTML report with everything correctly defined
    write_html_report(OUTPUT_DIR, q1_df, q2_df, corr_value)


if __name__ == "__main__":
    run_analysis()