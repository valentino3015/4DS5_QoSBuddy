import json
import os

class QoSExplainEngine:

    def __init__(self, json_path=None):
        if json_path is None:
            base_dir = os.path.dirname(__file__)
            json_path = os.path.join(base_dir, "kpi_mapping.json")

        with open(json_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)

    def get_root_cause(self, window):
        last = window[-1]
        causes = []

        for problem in self.rules:
            for trigger in problem["kpi_triggers"]:
                kpi = trigger["kpi"]

                if kpi not in last:
                    continue

                value = last[kpi]
                desc = trigger.get("description", kpi)

                if isinstance(value, (int, float)):

                    if "plage_critique" in trigger and self._check(value, trigger["plage_critique"]):
                        causes.append(f"[CRITICAL] {desc}")

                    elif "plage_warning" in trigger and self._check(value, trigger["plage_warning"]):
                        causes.append(f"[WARNING] {desc}")

        return causes if causes else ["No major issue detected"]

    def _check(self, value, rule):
        rule = rule.replace("dB", "").replace("%", "").strip()

        try:
            if "<" in rule:
                return value < float(rule.replace("<", "").strip())

            if ">" in rule:
                return value > float(rule.replace(">", "").strip())

            if "à" in rule:
                low, high = rule.split("à")
                return float(low) <= value <= float(high)

        except:
            return False

        return False