import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

DB_NAME = "earthquakes.db"

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
        print(pd.read_sql_query(sql_q1, conn).to_string(index=False))

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
        print(pd.read_sql_query(sql_q2, conn).to_string(index=False))

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
            plt.savefig('earthquake_magnitude_distribution.png')
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
            plt.figure(figsize=(10, 5))
            plt.scatter(df_q4['depth'], df_q4['mag'], alpha=0.3, color='purple', s=8)
            plt.title("Seismic Event Depth vs. Resulting Magnitude")
            plt.xlabel("Depth (km)")
            plt.ylabel("Magnitude")
            plt.grid(True, linestyle="--", alpha=0.5)
            plt.savefig('depth_vs_magnitude.png')
            plt.close()
            print("[SUCCESS] Scatter plot correlation asset saved as 'depth_vs_magnitude.png'.")
            
            print(f"Calculated Depth/Magnitude Correlation: {df_q4['depth'].corr(df_q4['mag']):.2f}")
        except Exception as e:
            print(f"[ERROR] Plotting Question 4 failed: {e}")

if __name__ == "__main__":
    run_analysis()