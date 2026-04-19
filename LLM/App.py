# App.py
import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from inference import load_model, predict, build_inference_prompt

app = FastAPI()
tokenizer, model = load_model()  # loads ONCE when server starts

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
    prompt = build_inference_prompt(event.model_dump())
    response = predict(tokenizer, model, prompt)
    return {"response": response}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)