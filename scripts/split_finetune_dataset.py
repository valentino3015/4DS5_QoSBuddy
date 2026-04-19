import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / "data" / "finetune" / "qosbuddy_sft.jsonl"
OUT_DIR = ROOT / "data" / "finetune" / "splits"

TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1
SEED = 42


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


def main():
    if not IN_FILE.exists():
        raise FileNotFoundError(f"Missing dataset: {IN_FILE}")

    rows = load_jsonl(IN_FILE)
    if not rows:
        raise ValueError("Dataset is empty.")

    random.seed(SEED)
    random.shuffle(rows)

    n = len(rows)
    train_end = int(n * TRAIN_RATIO)
    val_end = train_end + int(n * VAL_RATIO)

    train_rows = rows[:train_end]
    val_rows = rows[train_end:val_end]
    test_rows = rows[val_end:]

    save_jsonl(train_rows, OUT_DIR / "train.jsonl")
    save_jsonl(val_rows, OUT_DIR / "val.jsonl")
    save_jsonl(test_rows, OUT_DIR / "test.jsonl")

    print(f"Total examples: {n}")
    print(f"Train: {len(train_rows)}")
    print(f"Validation: {len(val_rows)}")
    print(f"Test: {len(test_rows)}")
    print(f"Saved splits to: {OUT_DIR}")


if __name__ == "__main__":
    main()