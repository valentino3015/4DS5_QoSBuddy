# App.py
import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from inference import load_model, predict, build_inference_prompt
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] MistralAPI - %(message)s")
logger = logging.getLogger("App")

app = FastAPI()
logger.info("Initializing LLM API. Warming up Mistral v0.2 + LoRA Adapter...")
tokenizer, model = load_model()  # loads ONCE when server starts
logger.info("Mistral API successfully started and waiting for predictions.")

class RCAEvent(BaseModel):
    rca_event_id: str
    cell_id: str
    site_id: str
    region: str
    vendor: str
    nr_band: str
    network_slice: str
    timestamp: str
    anomaly_severity: str
    anomaly_score: float
    kpi_snapshot: dict
    rca: dict

@app.post("/predict")
def predict_endpoint(event: RCAEvent):
    start = time.time()
    logger.info(f"Incoming Request -> Processing Event [{event.rca_event_id}] for cell [{event.cell_id}]")
    prompt = build_inference_prompt(event.model_dump())
    logger.info(f"Generated prompt, injecting into Mistral model. Please wait...")
    
    response = predict(tokenizer, model, prompt)
    
    elapsed = round(time.time() - start, 2)
    logger.info(f"Prediction Complete! Returned structured JSON in {elapsed}s")
    
    return {"response": response}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)