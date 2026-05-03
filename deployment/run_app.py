# deployment/run_app.py

import subprocess
import sys
import os
import time
from deployment.health_check import run_health_check
from deployment.config import BASE_DIR

DETECTION_MODE = "all"
WS_PORT = "9000"
HTTP_PORT = "9001"

def show_health_check():
    print("\nRunning QoSBuddy health check...\n")
    results = run_health_check()

    has_error = False

    for result in results:
        print(f"[{result['status']}] {result['component']} - {result['message']}")

        if result["status"] == "MISSING":
            has_error = True

    return not has_error

def start_process(name, command):
    print(f"\nStarting {name}...")
    print("Command:", " ".join(command))
    return subprocess.Popen(command)

def start_qosbuddy_deployment():
    detection_file = os.path.join(BASE_DIR, "agents", "detection_agent.py")
    remediation_file = os.path.join(BASE_DIR, "agents", "remediation_agent.py")

    if not os.path.exists(detection_file):
        print("ERROR: agents/detection_agent.py not found.")
        return

    if not os.path.exists(remediation_file):
        print("ERROR: agents/remediation_agent.py not found.")
        return

    detection_process = start_process(
        "Detection Agent",
        [
            sys.executable,
            detection_file,
            "--mode",
            DETECTION_MODE
        ]
    )

    print("\nWaiting for Detection Agent to initialize...")
    time.sleep(5)

    remediation_process = start_process(
        "Remediation Agent + Live Dashboard",
        [
            sys.executable,
            remediation_file,
            "--ws-port",
            WS_PORT,
            "--http-port",
            HTTP_PORT
        ]
    )

    print("\nQoSBuddy deployment started successfully.")
    print(f"Dashboard URL: http://127.0.0.1:{HTTP_PORT}")
    print("\nPress CTRL + C to stop the deployment.")

    try:
        detection_process.wait()
        remediation_process.wait()

    except KeyboardInterrupt:
        print("\nStopping QoSBuddy deployment...")

        detection_process.terminate()
        remediation_process.terminate()

        detection_process.wait()
        remediation_process.wait()

        print("QoSBuddy deployment stopped.")

if __name__ == "__main__":
    print("QoSBuddy Deployment Launcher")
    print("---------------------------")

    system_ready = show_health_check()

    if system_ready:
        start_qosbuddy_deployment()
    else:
        print("\nDeployment stopped because some components are missing.")