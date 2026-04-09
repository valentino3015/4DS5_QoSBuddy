# agent.py

import time

import pymysql

import config
from collector import collect_metrics
from db import INSERT_METRICS_SQL, metrics_values

# --- Configuration MySQL (shared with Flask app config.py) ---
DB_CONFIG = {
    "host": config.MYSQL_HOST,
    "user": config.MYSQL_USER,
    "password": config.MYSQL_PASSWORD,
    "database": config.MYSQL_DB,
    "port": config.MYSQL_PORT,
}

COLLECTION_INTERVAL = 0.1  # seconds (note: collection itself takes longer than this)


def connect_db():
    return pymysql.connect(**DB_CONFIG)


def store_metrics(connection, metrics):

    try:
        cursor = connection.cursor()
        try:
            cursor.execute(INSERT_METRICS_SQL, metrics_values(metrics))
        finally:
            cursor.close()

        connection.commit()

        print(f"[{metrics['timestamp']}] ✅ Metrics stored successfully")

    except Exception as e:
        print("❌ Database error:", e)


def run_agent():
    print("🚀 Network QoS Monitoring Agent Started")
    print(f"⏱ Collecting every {COLLECTION_INTERVAL} seconds...\n")

    connection = connect_db()
    try:
        while True:
            try:
                metrics = collect_metrics()

                if metrics:
                    store_metrics(connection, metrics)
                else:
                    print("⚠️ No metrics collected (possible network issue)")

            except Exception as e:
                print("❌ Error during collection:", e)

            time.sleep(COLLECTION_INTERVAL)
    finally:
        try:
            connection.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_agent()
