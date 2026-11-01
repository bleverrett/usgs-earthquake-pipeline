import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parent
DB_NAME = str(PROJECT_ROOT / "earthquakes.db")
OUTPUT_DIR = PROJECT_ROOT


def write_html_report(output_dir: Path, q1_df: pd.DataFrame, q2_df: pd.DataFrame, corr_value: float):
    """Create an HTML summary page that includes the generated PNG figures and table results."""
    q1_table = q1_df.to_html(index=False, classes="dataframe", border=0)
    q2_table = q2_df.to_html(index=False, classes="dataframe", border=0)

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
            <p class="metric">Depth/Magnitude Correlation: {corr_value:.2f}</p>
            <p>This report combines the database queries and generated chart outputs for the latest earthquake dataset loaded by the pipeline.</p>
        </div>

        <div class="panel">
            <h2>Most Dangerous Earthquakes</h2>
            {q1_table}
        </div>

        <div class="panel">
            <h2>Magnitude Type Summary</h2>
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
    
    with sqlite3.connect(DB_NAME) as conn:
        # Check database rows
        check_df = pd.read_sql_query("SELECT COUNT(*) as count FROM earthquakes;", conn)
        if check_df['count'].iloc[0] == 0:
            print("[CRITICAL ERROR] Database table is empty.")
            return

        # -----------------------------------------------------------------
        # Question 1 (Pure SQL): What Are The Top 5 Most Dangerous Earthquake Locations In The Last 6 Months
        # -----------------------------------------------------------------
        print("\n--- Question 1: What Are The Top 5 Most Dangerous Earthquake Locations In The Last 6 Months (Pure SQL) ---")
        sql_q1 = """
            SELECT l.place_name, e.mag, e.depth, e.time_timestamp
            FROM earthquakes e
            JOIN locations l ON e.location_id = l.location_id
            WHERE e.mag IS NOT NULL
            ORDER BY e.mag DESC
            LIMIT 5;
        """
        q1_df = pd.read_sql_query(sql_q1, conn)
        print(q1_df.to_string(index=False))

        # -----------------------------------------------------------------
        # Question 2 (Pure SQL): Counts and Averages by Magnitude Type
        # -----------------------------------------------------------------
        print("\n--- Question 2: Seismic Activity Summary by Measurement Scale Type (Pure SQL) ---")
        sql_q2 = """
            SELECT mag_type, COUNT(*) as total_events, ROUND(AVG(mag), 2) as average_magnitude
            FROM earthquakes
            WHERE mag_type IS NOT NULL AND mag_type != ''
            GROUP BY mag_type
            ORDER BY total_events DESC
            LIMIT 5;
        """
        q2_df = pd.read_sql_query(sql_q2, conn)
        print(q2_df.to_string(index=False))

        # -----------------------------------------------------------------
        # Question 3 (Python Tooling): Overall Magnitude Frequency Distribution
        # -----------------------------------------------------------------
        print("\n--- Question 3: Plotting Overall Magnitude Frequency Distribution (Python Tooling) ---")
        try:
            df_q3 = pd.read_sql_query("SELECT mag FROM earthquakes WHERE mag IS NOT NULL;", conn)
            plt.figure(figsize=(10, 4))
            plt.hist(df_q3['mag'], bins=25, color='teal', edgecolor='black', alpha=0.8)
            plt.title("Frequency Distribution of Global Earthquake Magnitudes (Past 6 Months)")
            plt.xlabel("Magnitude Scale")
            plt.ylabel("Event Count")
            plt.grid(True, linestyle="--", alpha=0.5)
            plt.savefig(OUTPUT_DIR / 'earthquake_magnitude_distribution.png')
            plt.close()
            print("[SUCCESS] Distribution curve chart saved as 'earthquake_magnitude_distribution.png'.")
        except Exception as e:
            print(f"[ERROR] Plotting Question 3 failed: {e}")

        # -----------------------------------------------------------------
        # Question 4 (Python Tooling): Seismic Depth vs. Magnitude Correlation
        # -----------------------------------------------------------------
        print("\n--- Question 4: Analyzing Event Depth vs. Magnitude Correlation (Python Tooling) ---")
        try:
            df_q4 = pd.read_sql_query("SELECT depth, mag FROM earthquakes WHERE depth IS NOT NULL AND mag IS NOT NULL;", conn)
            corr_value = df_q4['depth'].corr(df_q4['mag'])
            plt.figure(figsize=(10, 5))
            plt.scatter(df_q4['depth'], df_q4['mag'], alpha=0.3, color='purple', s=8)
            plt.title("Seismic Event Depth vs. Resulting Magnitude")
            plt.xlabel("Depth (km)")
            plt.ylabel("Magnitude")
            plt.grid(True, linestyle="--", alpha=0.5)
            plt.savefig(OUTPUT_DIR / 'depth_vs_magnitude.png')
            plt.close()
            print("[SUCCESS] Scatter plot correlation asset saved as 'depth_vs_magnitude.png'.")
            
            corr_value = float(corr_value) if pd.notna(corr_value) else 0.0
            print(f"Calculated Depth/Magnitude Correlation: {corr_value:.2f}")

            write_html_report(OUTPUT_DIR, q1_df, q2_df, corr_value)
        except Exception as e:
            print(f"[ERROR] Plotting Question 4 failed: {e}")

if __name__ == "__main__":
    run_analysis()