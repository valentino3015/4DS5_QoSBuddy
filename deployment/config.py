# deployment/config.py

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 5000

DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
LOG_DIR = os.path.join(BASE_DIR, "logs")

DETECTION_AGENT_PATH = os.path.join(BASE_DIR, "agents", "detection_agent.py")
PREDICTION_DIR = os.path.join(BASE_DIR, "prediction")

APP_NAME = "QoSBuddy Deployment"
APP_VERSION = "1.0.0"