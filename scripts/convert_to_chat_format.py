import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLIT_DIR = ROOT / "data" / "finetune" / "splits"
OUT_DIR = ROOT / "data" / "finetune" / "chat_splits"

SYSTEM_PROMPT = (
    "You are a telecom QoS reporting assistant. "
    "Generate clear, structured, factual incident reports. "
    "Do not invent facts. "
    "Use exactly these sections: Executive Summary, Incident Overview, "
    "Top Root Causes, Recommended Actions, Business Impact, Next Steps."
)


def load_jsonl(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def save_jsonl(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def convert_row(row):
    user_content = f"{row['instruction']}\n\nInput:\n{row['input']}"
    assistant_content = row["output"]

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
        "metadata": row.get("metadata", {})
    }


def process_file(name):
    in_path = SPLIT_DIR / name
    out_path = OUT_DIR / name

    rows = load_jsonl(in_path)
    converted = [convert_row(r) for r in rows]
    save_jsonl(converted, out_path)

    print(f"{name}: {len(converted)} examples -> {out_path}")


def main():
    for fname in ["train.jsonl", "val.jsonl", "test.jsonl"]:
        process_file(fname)


if __name__ == "__main__":
    main()