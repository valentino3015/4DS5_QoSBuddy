# 📡 QoSBuddy — Network QoS Labeling & Dataset Fusion

## 📖 Overview

**QoSBuddy** is a professional-grade data engineering pipeline designed to transform raw, heterogeneous LTE network logs into high-quality, labeled datasets for Machine Learning. It automates the tedious process of cleaning telecom data and applies domain-specific heuristics to identify network degradations.

The project is structured into two core modules:
* **`qosbuddy_labeler.py`**: The logic engine that maps columns, cleans RF values, and generates diagnostic labels.
* **`qosbuddy_merger.py`**: A utility for fusing multiple sources, handling class imbalances, and preparing the final training set.

---

## 🛠 Feature Specifications & Data Dictionary

The pipeline processes physical layer measurements and network performance indicators. Below is the technical breakdown of the features included in the final output.

### 1. RF Measurements (Model Inputs)
These metrics represent the physical radio environment.

| Feature | Dataset Type | Real-World Unit | Description |
| :--- | :--- | :--- | :--- |
| **`rsrp`** | Float | **dBm** | *Reference Signal Received Power*: Measures the signal strength. Values range from -140 (no signal) to -44 (excellent). |
| **`sinr`** | Float | **dB** | *Signal to Interference plus Noise Ratio*: Measures signal quality. Higher values indicate cleaner signals with less noise. |
| **`rsrq`** | Float | **dB** | *Reference Signal Received Quality*: A ratio that helps determine handover and cell reselection. |
| **`throughput_dl`**| Float | **kbps / Mbps** | *Downlink Throughput*: The data rate delivered to the user. |
| **`throughput_ul`**| Float | **kbps / Mbps** | *Uplink Throughput*: The data rate sent by the user to the network. |

### 2. Spatio-Temporal & Metadata
| Feature | Dataset Type | Description |
| :--- | :--- | :--- |
| **`timestamp`** | DateTime | Precise date and time of the measurement. |
| **`lat` / `lon`** | Float | GPS coordinates (Latitude/Longitude) for geospatial analysis. |
| **`source_file`** | String | Tracking the origin of the data for auditing and debugging. |

### 3. Diagnostic Labels (Model Targets)
The pipeline generates Boolean flags based on telecom standards (3GPP) and heuristic thresholds.

| Label | Type | Condition Identified |
| :--- | :--- | :--- |
| **`label_call_drop_risk`** | Boolean | High probability of session termination due to poor RF. |
| **`label_low_throughput`**| Boolean | Identified bottleneck in data delivery. |
| **`label_handover_risk`**| Boolean | High risk of failure when switching between cells. |
| **`label_coverage_hole`** | Boolean | Identified "dead zone" with insufficient RSRP. |
| **`label_interference`** | Boolean | Poor SINR despite high RSRP, indicating frequency overlap. |
| **`label_voice_quality_risk`**| Boolean | Risk of packet loss affecting VoLTE/VoNR calls. |
| **`label_prb_congestion`**| Boolean | Resource block saturation at the eNodeB level. |

### 4. Expert System Output
| Feature | Type | Description |
| :--- | :--- | :--- |
| **`any_degradation`** | Integer | Binary flag (0 or 1). Master label for classification tasks. |
| **`severity`** | String | Categorical ranking: `OK`, `WARNING`, or `CRITICAL`. |
| **`recommendation`** | String | Human-readable optimization action (e.g., "PCI Cleaning", "Tilt adjustment"). |

---

## ⚙️ Core Functionalities

### 🔹 Data Labeling
* **Intelligent Mapping**: Uses a `COLUMN_MAP` to automatically recognize variations in column naming (e.g., "RSRP_dBm" vs "rsrp").
* **Sanitization**: Automatically strips units (like "dBm") from strings and converts them to floats.
* **Outlier Filtering**: Removes nonsensical values to prevent model skewing.

### 🔹 Dataset Fusion & Balancing
Mobile network data is notoriously imbalanced (most samples are "OK"). QoSBuddy addresses this with:
* **Oversampling**: Duplicates minority degradation classes (Default).
* **Undersampling**: Reduces majority "OK" classes to match the minority.
* **Ratio Control**: Configurable sampling ratios for fine-tuning.

---

## 🚀 Usage Guide

### 1. Label a single dataset
```bash
python qosbuddy_labeler.py input_logs.csv
```

### 2. Merge and balance a directory of logs
```bash
python qosbuddy_merger.py --folder ./raw_data/ --balance oversample --output training_set.csv
```

---

## 🏗 Data Pipeline Architecture

1.  **Ingestion**: Detects CSV format and delimiters.
2.  **Mapping**: Aligns heterogeneous columns to the QoSBuddy schema.
3.  **Cleaning**: Handles missing values (NaN) and performs outlier rejection.
4.  **Labeling**: Runs the heuristic engine to generate the 7+ QoS labels.
5.  **Integration**: Merges all processed files into a single master dataframe.
6.  **Balancing**: Applies class-balancing strategies for ML readiness.

---

## 🧪 Compatibility
The final output is fully compatible with:
* **Scikit-Learn** (Random Forest, SVM)
* **XGBoost / LightGBM** (Gradient Boosting)
* **PyTorch / TensorFlow** (Deep Learning)

---

## 👩‍💻 Author
**Mariam Ben Abdallah**
