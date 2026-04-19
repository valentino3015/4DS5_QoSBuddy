from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import Trainer, TrainingArguments

# Load model
model_name = "models/phi-2"
tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(model_name)

# Load dataset
dataset = load_dataset("json", data_files="train.jsonl")

def tokenize(example):
    return tokenizer(example["text"], truncation=True, padding="max_length", max_length=512)

dataset = dataset.map(tokenize)

# LoRA config
lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["Wqkv", "fc1", "fc2"],
    lora_dropout=0.1,
    bias="none"
)

model = get_peft_model(model, lora_config)

# Training config
training_args = TrainingArguments(
    output_dir="./lora-anomaly-model",
    per_device_train_batch_size=2,
    num_train_epochs=3,
    logging_steps=10,
    save_steps=50
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"]
)

trainer.train()

# Save model
model.save_pretrained("lora-anomaly-model")
tokenizer.save_pretrained("lora-anomaly-model")