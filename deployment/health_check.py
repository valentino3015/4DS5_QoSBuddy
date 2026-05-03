# deployment/health_check.py

import os
from deployment.config import BASE_DIR, DATA_DIR, MODEL_DIR, LOG_DIR

def check_path(name, path):
    if os.path.exists(path):
        return {
            "component": name,
            "status": "OK",
            "message": f"{name} found."
        }
    else:
        return {
            "component": name,
            "status": "MISSING",
            "message": f"{name} not found at {path}"
        }

def run_health_check():
    checks = []

    checks.append(check_path("Agents folder", os.path.join(BASE_DIR, "agents")))
    checks.append(check_path("Dashboard folder", os.path.join(BASE_DIR, "dashboard")))
    checks.append(check_path("Prediction folder", os.path.join(BASE_DIR, "prediction")))
    checks.append(check_path("Models folder", MODEL_DIR))
    checks.append(check_path("Data folder", DATA_DIR))
    checks.append(check_path("Logs folder", LOG_DIR))
    checks.append(check_path("Requirements file", os.path.join(BASE_DIR, "requirements.txt")))

    return checks

if __name__ == "__main__":
    results = run_health_check()

    print("\nQoSBuddy Deployment Health Check\n")

    for result in results:
        print(f"[{result['status']}] {result['component']} - {result['message']}")