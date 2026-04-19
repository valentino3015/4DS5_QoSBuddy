# QoSBuddy / QoS Mod

Projet de supervision QoS orienté reseau 5G avec detection d'anomalies, analyse de cause racine (RCA), recommandations de remediation et dashboard temps reel.

Ce README a ete redige a partir des fichiers presents dans le depot, pas seulement d'une hypothese d'architecture.

## Vue d'ensemble

La version actuelle du projet fonctionne autour de 2 composants principaux :

1. `agents/detection_agent.py`
   Script principal actuel.
   Il entraine puis execute un pipeline unifie de :
   - detection d'anomalies sur KPIs reseau
   - RCA inline sur les anomalies detectees
   - emission des evenements RCA dans `data/output/rca_feed.jsonl`

2. `agents/remediation_agent.py`
   Lit `data/output/rca_feed.jsonl`, construit une recommandation de remediation, ecrit `data/output/remediation_feed.jsonl` et alimente un dashboard HTML via WebSocket + HTTP.

En pratique, le pipeline actif est donc :

`time_series_kpi.csv` -> `DetectionAgent` -> `rca_feed.jsonl` -> `RemediationAgent` -> dashboard temps reel

## Structure du projet

### Dossiers actifs

- `agents/`
  Contient les scripts principaux.
- `dashboard/`
  Contient `index.html`, l'interface temps reel affichee par `remediation_agent.py`.
- `data/`
  Jeux de donnees CSV/JSON utilises pour l'entrainement et le streaming.
- `data/output/`
  Fichiers JSONL generes par les agents.
- `models/`
  Modeles entraines et artefacts de preprocessing.
- `logs/`
  Journaux d'execution des agents.

### Dossiers non actifs ou historiques

- `agents/Backup/`
  Ancienne version separee en 2 agents :
  - `anomaly_agent.py`
  - `rca_agent.py`
  Cette logique est aujourd'hui remplacee en pratique par `agents/detection_agent.py`.

- `OldSystem/`
  Ancien systeme base sur collecte reseau + stockage MySQL + dashboard Flask.
  Ce dossier n'est pas le pipeline principal actuel.

## Fichiers importants

### Agents actuels

- `agents/detection_agent.py`
  Agent principal actuel.
  Fonctions principales :
  - entrainement batch
  - streaming ligne par ligne du fichier `data/time_series_kpi.csv`
  - moteur de regles metier sur KPIs
  - detection par deep learning :
    - autoencoder LSTM
    - Temporal CNN
  - RCA inline via :
    - `RandomForestClassifier`
    - recherche de voisins similaires `k-NN`
  - prise en compte des cellules voisines via `data/cell_topology.csv`
  - emission dans `data/output/rca_feed.jsonl`

- `agents/remediation_agent.py`
  Agent de remediation et de visualisation.
  Fonctions principales :
  - lit `data/output/rca_feed.jsonl`
  - applique une base de connaissances de remediation
  - calcule score, priorite, effort, ETA et alternatives
  - genere `data/output/remediation_feed.jsonl`
  - expose un serveur WebSocket
  - expose un serveur HTTP local
  - injecte le port WebSocket dans `dashboard/index.html`

### Dashboard

- `dashboard/index.html`
  Dashboard front-end unique tres riche.
  Il affiche notamment :
  - vue overview
  - statistiques globales
  - cartes / etats de cellules
  - historique KPI
  - flux d'incidents
  - vue analytics
  - vue topology

### Donnees

- `data/time_series_kpi.csv`
  Gros jeu de donnees temporelles de KPIs 5G.
  Colonnes observees :
  `timestamp`, `cell_id`, `site_id`, `region`, `vendor`, `nr_band`, `network_slice`,
  puis des KPIs comme `RSRP_dBm`, `SINR_dB`, `PRB_util_DL_pct`, `latency_ms`, `MOS`, etc.
  Contient aussi `label` et `anomaly_score_0_10`.

- `data/labeled_incidents.csv`
  Base d'incidents labels pour l'entrainement RCA.
  Contient les causes racines, severites, metadonnees reseau, solutions recommandees et snapshots KPI.

- `data/cell_topology.csv`
  Topologie reseau des cellules.
  Utilisee par :
  - la correlation entre cellules voisines
  - le dashboard topology

- `data/rca_mapping.json`
  Mapping `cause -> solution` et `cause -> tags` charge par `detection_agent.py`.

### Sorties generees

- `data/output/rca_feed.jsonl`
  Flux des evenements RCA produits par l'agent de detection.

- `data/output/remediation_feed.jsonl`
  Flux enrichi avec recommandations de remediation.

### Modeles observes dans le depot

Le dossier `models/` contient deja des artefacts entraines :

- `lstm_ae.pt`
- `tcnn.pt`
- `scaler.joblib`
- `rca_rf_classifier.joblib`
- `rca_scaler.joblib`
- `rca_label_encoder.joblib`
- `rca_knn_index.joblib`
- `rca_incident_db.joblib`
- `rca_kpi_features.joblib`

## Fonctionnement detaille du pipeline actuel

### 1. Detection + RCA

`agents/detection_agent.py` supporte 3 modes :

- `--mode train`
  Entrainement des modeles sur les CSV historiques.
- `--mode stream`
  Recharge les modeles et rejoue le flux CSV comme un flux temps reel.
- `--mode all`
  Entrainement puis streaming.

Le script combine plusieurs signaux :

- regles metier sur seuils KPI
- score d'anomalie de l'autoencoder LSTM
- score de classification sequence du Temporal CNN
- correlation entre cellules voisines

Si une anomalie est retenue, il execute tout de suite la RCA :

- classification des causes probables
- override heuristique selon certaines combinaisons KPI
- recherche de cas similaires
- ajout de tags et d'une solution recommandee

### 2. Remediation + Dashboard

`agents/remediation_agent.py` :

- traite d'abord tout l'historique deja present dans `rca_feed.jsonl`
- passe ensuite en mode "live tail"
- enrichit chaque evenement avec une action principale et des alternatives
- met a jour l'etat du dashboard
- pousse les donnees aux clients via WebSocket

## Commandes utiles

### Lancer la detection/RCA actuelle

```powershell
python agents\detection_agent.py --mode all
```

Exemples :

```powershell
python agents\detection_agent.py --mode train
python agents\detection_agent.py --mode stream
python agents\detection_agent.py --mode stream --cell gNB_001_C1
python agents\detection_agent.py --mode stream --chunk-size 500
```

### Lancer remediation + dashboard

```powershell
python agents\remediation_agent.py
```

Exemples :

```powershell
python agents\remediation_agent.py --ws-port 9000 --http-port 9001
python agents\remediation_agent.py --no-browser
python agents\remediation_agent.py --tail-interval 0.5
```

## Dependances

Le fichier `requirements.txt` existe, mais il ne couvre pas toutes les dependances reelles des scripts actuels.

### Contenu actuel de `requirements.txt`

- `Flask`
- `flask-mysqldb`
- `mysqlclient`
- `psutil`
- `speedtest-cli`
- `ping3`
- `numpy`
- `pymysql`
- `requests`
- `collector`

### Dependances reellement importees par la version actuelle

Pour les agents actifs, il faut au minimum verifier la presence de :

- `numpy`
- `pandas`
- `scikit-learn`
- `joblib`
- `torch`
- `websockets`

Pour `OldSystem`, il faut en plus :

- `Flask`
- `flask-mysqldb`
- `mysqlclient` ou environnement MySQL compatible
- `psutil`
- `ping3`
- `pymysql`
- `requests`

## Observations importantes

- Il n'y avait pas de `README.md` dans le depot avant cette mise a jour.
- Le pipeline actif n'utilise pas directement `agents/Backup/`.
- `OldSystem/` correspond a une ancienne architecture separee.
- Le dashboard depend de `remediation_agent.py`, qui modifie `dashboard/index.html` pour y injecter le port WebSocket.
- Le projet contient deja de gros artefacts :
  - datasets volumineux dans `data/`
  - modeles preentranes dans `models/`
  - logs et sorties generees dans `logs/` et `data/output/`

## Ancien systeme (`OldSystem/`)

Le dossier `OldSystem/` contient une autre approche, plus classique :

- `OldSystem/network_monitor/collector.py`
  Collecte des metriques reseau locales :
  RTT, jitter, packet loss, throughput, disponibilite, etc.

- `OldSystem/network_monitor/agent.py`
  Boucle de collecte qui stocke les mesures en base MySQL.

- `OldSystem/network_monitor/app.py`
  Application Flask qui sert un dashboard et une API `/api/metrics`.

- `OldSystem/network_monitor/db.py`
  Helpers SQL d'insertion.

- `OldSystem/network_monitor/network_qos_db.sql`
  Dump SQL de la base `network_qos_db`.

- `OldSystem/Anomaly_detection/anomaly_agent.py`
  Ancien agent de detection d'anomalies base sur Z-score glissant et seuils absolus.

Cette partie peut servir de reference historique, mais elle ne semble pas etre la voie principale actuelle du projet.

## Recommandation de lecture du projet

Pour comprendre rapidement le depot, lire dans cet ordre :

1. `agents/detection_agent.py`
2. `agents/remediation_agent.py`
3. `dashboard/index.html`
4. `data/rca_mapping.json`
5. `agents/Backup/`
6. `OldSystem/`

## Etat actuel du depot

Le projet ressemble a une evolution d'un ancien systeme de monitoring vers une plateforme plus orientee IA/ML pour la QoS 5G, avec :

- apprentissage sur historiques CSV
- RCA inline
- recommandations contextualisees
- visualisation temps reel

Si tu veux, je peux maintenant faire une deuxieme passe et enrichir ce `README` avec :

- un schema d'architecture
- une section installation pas a pas
- une section "problemes connus"
- une section "ameliorations recommandees"

## QoSBuddy-LLM

Le projet contient maintenant une integration LLM legere autour de `QoSBuddy-LLM`.

### Fichiers ajoutes

- `qosbuddy_llm/build_dataset.py`
  Construit un dataset JSONL de fine-tuning depuis `data/labeled_incidents.csv`.
- `qosbuddy_llm/train.py`
  Lance un fine-tuning LoRA/QLoRA sur `Qwen/Qwen2.5-0.5B-Instruct`.
- `qosbuddy_llm/inference.py`
  Charge l'adapter fine-tune et genere une remediation en JSON.
- `qosbuddy_llm/prompting.py`
  Contient le prompt systeme et le parsing JSON.
- `qosbuddy_llm/remediation_kb.py`
  Contient la base de connaissances partagee.

### Flux LLM

1. `agents/detection_agent.py` produit `rca_feed.jsonl`
2. `agents/remediation_agent.py` produit toujours la remediation classique
3. `QoSBuddy-LLM` genere en plus :
   - `explanation`
   - `priority`
   - `recommended_action`
   - `steps`
4. La sortie est stockee dans `llm_remediation`
5. Le dashboard affiche aussi cette section

### Construire le dataset

```powershell
python qosbuddy_llm\build_dataset.py
```

### Entrainement de l'adapter

Installer d'abord la stack LLM :

```powershell
pip install -r requirements-llm.txt
```

Puis lancer l'entrainement :

```powershell
python qosbuddy_llm\train.py --load-in-4bit
```

Le projet est maintenant configure par defaut pour :

`Qwen/Qwen2.5-0.5B-Instruct`

Ce choix est plus adapte a une machine limitee ou sans GPU dedie.

L'adapter est sauvegarde par defaut dans :

`models/qosbuddy-llm-adapter`

### Lancer le pipeline avec QoSBuddy-LLM

```powershell
python agents\remediation_agent.py
```

Options utiles :

```powershell
python agents\remediation_agent.py --disable-llm
python agents\remediation_agent.py --llm-adapter-dir models\qosbuddy-llm-adapter
python agents\remediation_agent.py --llm-base-model Qwen/Qwen2.5-0.5B-Instruct
```

### Fallback

Si l'adapter n'est pas encore entraine, `remediation_agent.py` continue de fonctionner.
Dans ce cas, le bloc `llm_remediation` est rempli a partir de la base de connaissances classique.
