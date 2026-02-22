# agent.py

import time
import pymysql
import config
from collector import collect_metrics
from db import INSERT_METRICS_SQL, metrics_values

import psutil
import socket

# --- Configuration MySQL (shared with Flask app config.py) ---
DB_CONFIG = {
    "host": config.MYSQL_HOST,
    "user": config.MYSQL_USER,
    "password": config.MYSQL_PASSWORD,
    "database": config.MYSQL_DB,
}

COLLECTION_INTERVAL = 5  # seconds

# --- Database helpers ---
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

# --- Network helpers ---
def get_active_targets_local():
    """
    Return a set of active applications on this PC that have established network connections.
    Each target is a tuple: (process_name, local_ip, local_port, remote_ip, remote_port)
    """
    targets = set()

    for conn in psutil.net_connections(kind='inet'):  # TCP + UDP
        if conn.status != psutil.CONN_ESTABLISHED:
            continue  # Only care about active connections

        try:
            proc = psutil.Process(conn.pid) if conn.pid else None
            proc_name = proc.name() if proc else "Unknown"

            local_ip, local_port = conn.laddr
            remote_ip, remote_port = conn.raddr if conn.raddr else ("-", "-")

            targets.add((proc_name, local_ip, local_port, remote_ip, remote_port))

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return targets

# --- Main agent loop ---
def run_agent():
    print("🚀 Network QoS Monitoring Agent Started")
    print(f"⏱ Collecting every {COLLECTION_INTERVAL} seconds...\n")

    connection = connect_db()
    try:
        while True:
            try:
                targets = get_active_targets_local()
                if not targets:
                    print("⚠️ No active local network connections found")
                else:
                    print("🔍 Active local network connections:")
                    for t in targets:
                        proc_name, local_ip, local_port, remote_ip, remote_port = t
                        print(f"  ✅ {proc_name}: {local_ip}:{local_port} -> {remote_ip}:{remote_port}")

                # Only send process names to metrics collector
                metrics_list = collect_metrics([t[0] for t in targets])

                for metrics in metrics_list:
                    store_metrics(connection, metrics)

                if not metrics_list:
                    print("⚠️ No metrics collected")

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