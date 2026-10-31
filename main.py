import sys
from pipeline import setup_database, fetch_and_ingest_earthquakes
from analysis import run_analysis

def main():
    print("=" * 60)
    print("STARTING PUBLIC DATA PIPELINE & ANALYTICS WORKFLOW")
    print("=" * 60)

    try:
        setup_database()
        print("[SUCCESS] Database infrastructure initialized successfully.\n")

        print("Executing Anonymous Data Ingestion Pipeline...")
        fetch_and_ingest_earthquakes()
        print("[SUCCESS] Data pipeline execution finalized.\n")

        print("Running Intelligence Reporting & Analysis...")
        run_analysis()
        print("[SUCCESS] Process completed.")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Workflow execution failed: {e}")
        sys.exit(1)

    print("=" * 60)
    print("WORKFLOW EXECUTED END-TO-END COMPLETELY")
    print("=" * 60)

if __name__ == "__main__":
    main()