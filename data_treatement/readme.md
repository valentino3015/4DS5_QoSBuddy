📡 QoSBuddy — Network QoS Labeling & Dataset Fusion
📖 Overview

QoSBuddy is a data processing pipeline designed to:

📂 Load heterogeneous LTE network datasets (CSV)
🧹 Clean and normalize data
🏷️ Automatically generate QoS degradation labels
⚖️ Balance datasets for machine learning
📊 Export a final dataset ready for ML models

It consists of two main modules:

qosbuddy_labeler.py → Label generation engine
qosbuddy_merger.py → Multi-dataset fusion & preparation
⚙️ Features
🔹 Labeler (qosbuddy_labeler.py)
Supports multiple CSV formats (standard, tab-quoted, unit values)
Automatic column mapping (COLUMN_MAP)
Data cleaning (units removal, outlier filtering)
Generates multiple QoS labels:
Call drop risk
Low throughput
Handover issues
Coverage holes
Interference
Voice quality issues
PRB congestion
Adds:
any_degradation (binary label)
severity (OK / WARNING / CRITICAL)
recommendation (network optimization actions)
🔹 Merger (qosbuddy_merger.py)
Processes multiple CSV files
Applies labeling pipeline to each dataset
Merges datasets into a unified format
Displays statistics per source
Balances classes:
oversample (default)
undersample
none
Exports final dataset for ML
📦 Installation
pip install pandas numpy
🚀 Usage
🔹 1. Label a single dataset
python qosbuddy_labeler.py dataset.csv

👉 Output:

dataset_qosbuddy_labeled.csv
🔹 2. Merge multiple datasets
python qosbuddy_merger.py file1.csv file2.csv

OR using a folder:

python qosbuddy_merger.py --folder ./datasets/
🔹 3. Advanced options
python qosbuddy_merger.py --folder ./datasets/ \
  --output final.csv \
  --balance oversample \
  --ratio 0.3
🧠 Data Pipeline
Raw CSVs
   ↓
Format Detection
   ↓
Column Mapping
   ↓
Cleaning (NaN + outliers)
   ↓
Label Generation
   ↓
Merge Datasets
   ↓
Class Balancing
   ↓
Final ML Dataset
📊 Output Dataset
🔹 Features (ML inputs)
rsrp, sinr, rsrq, cqi
throughput_dl, throughput_ul
prb_utilization (if available)
🔹 Labels
label_call_drop_risk
label_low_throughput
label_handover_risk
label_coverage_hole
label_interference
label_voice_quality_risk
label_prb_congestion
🔹 Global target
any_degradation (binary classification)
🔹 Additional fields
severity
recommendation
source_file
⚖️ Class Balancing
Strategy	Description
oversample	Duplicate degraded samples (default)
undersample	Reduce normal samples
none	No balancing
🧪 ML Compatibility

The final dataset is ready for:

scikit-learn
XGBoost
PyTorch
TensorFlow
⚠️ Requirements

Minimum required columns:

rsrp
sinr

If missing → dataset is skipped.

💡 Notes
Handles messy real-world telecom datasets
Automatically adapts to different column names
Designed for LTE QoS analysis & ML training
Includes domain-based heuristics for labeling

👩‍💻 Author

QoSBuddy — Mariam Ben Abdallah