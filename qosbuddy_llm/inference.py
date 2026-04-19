"""Runtime inference wrapper for QoSBuddy-LLM."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from qosbuddy_llm.prompting import SYSTEM_PROMPT, build_llm_payload, build_user_prompt, parse_llm_response


def _fallback_output(remediation: dict, reason: str, model_name: str) -> dict:
    action = remediation.get("primary_action", {})
    return {
        "model": model_name,
        "status": "fallback",
        "source": "rule_engine",
        "reason": reason,
        "explanation": action.get("summary", "Manual remediation summary not available."),
        "priority": action.get("priority", "Medium"),
        "recommended_action": action.get("action", "Manual investigation required"),
        "steps": list(action.get("steps", [])),
        "raw_text": "",
    }


class QoSBuddyLLM:
    """Loads a fine-tuned adapter when available and falls back gracefully otherwise."""

    def __init__(
        self,
        root_dir: str | Path,
        base_model: str = "Qwen/Qwen2.5-0.5B-Instruct",
        adapter_dir: str | Path | None = None,
        device: str = "auto",
        max_new_tokens: int = 256,
        logger: logging.Logger | None = None,
    ):
        self.root_dir = Path(root_dir)
        self.base_model = base_model
        self.adapter_dir = Path(adapter_dir) if adapter_dir else self.root_dir / "models" / "qosbuddy-llm-adapter"
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.log = logger or logging.getLogger("QoSBuddyLLM")
        self.model_name = "QoSBuddy-LLM"
        self.enabled = False
        self.disable_reason = ""
        self.model = None
        self.tokenizer = None
        self._load_runtime()

    def _load_runtime(self):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            self.disable_reason = f"transformers runtime unavailable: {exc}"
            self.log.warning(self.disable_reason)
            return

        if not self.adapter_dir.exists():
            self.disable_reason = f"adapter not found at {self.adapter_dir}"
            self.log.info("QoSBuddy-LLM disabled: %s", self.disable_reason)
            return

        try:
            try:
                from peft import PeftModel
            except ImportError as exc:
                self.disable_reason = f"peft unavailable: {exc}"
                self.log.warning(self.disable_reason)
                return

            torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            model = AutoModelForCausalLM.from_pretrained(
                self.base_model,
                torch_dtype=torch_dtype,
                device_map=self.device,
            )
            tokenizer = AutoTokenizer.from_pretrained(self.base_model, use_fast=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            model = PeftModel.from_pretrained(model, str(self.adapter_dir))
            model.eval()

            self.model = model
            self.tokenizer = tokenizer
            self.enabled = True
            self.log.info("QoSBuddy-LLM loaded from %s", self.adapter_dir)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            self.disable_reason = f"failed to load model: {exc}"
            self.log.exception("QoSBuddy-LLM load failed")

    def generate(self, rca_event: dict, remediation: dict) -> dict:
        if not self.enabled or self.model is None or self.tokenizer is None:
            return _fallback_output(remediation, self.disable_reason or "model disabled", self.model_name)

        try:
            payload = build_llm_payload(rca_event, remediation)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(payload)},
            ]
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = self.tokenizer(prompt, return_tensors="pt")
            model_device = next(self.model.parameters()).device
            inputs = {key: value.to(model_device) for key, value in inputs.items()}

            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
            generated = output_ids[0][inputs["input_ids"].shape[1] :]
            text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
            parsed = parse_llm_response(text)
            if not parsed:
                return _fallback_output(remediation, "invalid JSON output", self.model_name) | {"raw_text": text}

            return {
                "model": self.model_name,
                "status": "ok",
                "source": "adapter",
                "reason": "",
                "explanation": parsed["explanation"],
                "priority": parsed["priority"],
                "recommended_action": parsed["recommended_action"],
                "steps": parsed["steps"],
                "raw_text": text,
            }
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            self.log.exception("QoSBuddy-LLM generation failed")
            return _fallback_output(remediation, f"generation error: {exc}", self.model_name)
