# Archive de prévisions météo — CMC & HRRR

Construction d'une base de données de prévisions numériques aux aéroports canadiens et américains, à partir des modèles d'Environnement Canada (ECCC) et de NOAA.

---

## Modèles disponibles

| Clé | Modèle | Résolution | Source | Rétention |
|---|---|---|---|---|
| `hrdps_continental` | HRDPS continental (brut) | 2.5 km | Datamart ECCC | ~30 jours |
| `hrdps_weong` | HRDPS-WEonG (post-traité) | 2.5 km | Datamart ECCC | ~30 jours |
| `hrrr` | HRRR (continental US) | 3 km | AWS NOAA | depuis ~2014 |

**HRDPS-WEonG** contient des variables essentielles pour l'aviation absentes du HRDPS brut : `VISIFG` (visibilité en brouillard givrant) et `VISLFG` (visibilité en brouillard léger).

---

## Installation

```bash
conda env create -f environment.yml
conda activate cmc
```

---

## Structure des fichiers

```
cmc/
├── stations.py          # Points d'intérêt (aéroports via OurAirports)
├── cmc_config.py        # Modèles, variables, stations
├── cmc_fetch.py         # Téléchargement + lecture des données
├── cmc_backfill.py      # Archive historique (one-shot)
├── cmc_update.py        # Mise à jour incrémentale (cron)
├── cmc_explorer.ipynb   # Visualisation interactive
└── data/
    ├── airports_cache.parquet     # Cache OurAirports (auto-généré)
    ├── downloaded_runs.json       # Journal des passes téléchargées
    ├── hrdps_continental/         # Fichiers Parquet par passe
    ├── hrdps_weong/
    └── hrrr/
```

Les données sont stockées au format **Parquet** : un fichier par passe d'initialisation (ex: `20260325_12Z.parquet`), contenant toutes les stations × toutes les heures de prévision × toutes les variables.

---

## 1. Construire l'archive initiale

### ECCC — HRDPS (datamart, ~30 jours disponibles)

```bash
# Télécharger les 30 derniers jours (toutes les passes 00/06/12/18Z)
python cmc_backfill.py --model hrdps_continental --days 30
python cmc_backfill.py --model hrdps_weong --days 30

# Ou les deux en même temps
python cmc_backfill.py --model all --days 30
```

> **Note** : Le datamart ECCC conserve environ 30 jours. Au-delà, les fichiers ne sont plus disponibles.

### HRRR — Archive AWS (depuis ~2014)

Le bucket AWS de NOAA contient plusieurs années d'archives HRRR. L'archive n'est pas complète (lacunes possibles, surtout avant 2018) — le script tolère les erreurs et continue.

```bash
# Une année complète
python cmc_backfill.py --model hrrr --start 2023-01-01 --end 2023-12-31

# Depuis 2020 jusqu'à aujourd'hui
python cmc_backfill.py --model hrrr --start 2020-01-01

# Seulement les passes 00Z et 12Z (plus rapide)
python cmc_backfill.py --model hrrr --start 2022-01-01 --end 2022-12-31 --runs 0 12
```

> **Attention** : Télécharger plusieurs années est long (des milliers de passes). Prévoir plusieurs heures/jours selon la connexion. Les erreurs dues aux lacunes d'archive sont loggées dans `logs/cmc_backfill.log` et n'interrompent pas le téléchargement.

---

## 2. Mise à jour quotidienne (crontab)

Le script `cmc_update.py` vérifie quelles passes récentes ne sont pas encore téléchargées et les télécharge. À rouler plusieurs fois par jour, après la publication de chaque passe.

### Heures de publication approximatives (UTC)

| Passe | Disponible sur le datamart |
|---|---|
| 00Z | ~03h00–04h00 UTC |
| 06Z | ~09h00–10h00 UTC |
| 12Z | ~15h00–16h00 UTC |
| 18Z | ~21h00–22h00 UTC |

### Configuration du crontab

```bash
# Ouvrir le crontab
crontab -e
```

Ajouter les lignes suivantes (adapter le chemin) :

```cron
# Mise à jour ECCC — 4 fois par jour, 1h après chaque publication
0 5  * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_continental >> logs/update.log 2>&1
0 11 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_continental >> logs/update.log 2>&1
0 17 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_continental >> logs/update.log 2>&1
0 23 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_continental >> logs/update.log 2>&1

# Même chose pour WEonG
0 5  * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_weong >> logs/update.log 2>&1
0 11 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_weong >> logs/update.log 2>&1
0 17 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_weong >> logs/update.log 2>&1
0 23 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_weong >> logs/update.log 2>&1

# HRRR — toutes les 6h (AWS est généralement disponible rapidement)
0 */6 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrrr >> logs/update.log 2>&1
```

**Option `--wait`** : si tu roules le script exactement à l'heure de publication et que la donnée n'est pas encore arrivée, ajoute `--wait` pour qu'il attende :

```cron
# Attendre jusqu'à 90 minutes que la passe 12Z soit disponible
0 15 * * * cd /Users/tito/Documents/Projets_Perso/cmc && conda run -n cmc python cmc_update.py --model hrdps_continental --wait --wait-for 90min --check-every 5min >> logs/update.log 2>&1
```

---

## 3. Utilisation en Python

### Télécharger une passe manuellement

```python
from cmc_fetch import download_run
import pandas as pd

# Dernière passe disponible
recent = pd.Timestamp.now("UTC").tz_convert(None).floor("6h") - pd.Timedelta("6h")

df = download_run(recent, model_key="hrdps_continental")
df = download_run(recent, model_key="hrdps_weong")
df = download_run(recent, model_key="hrrr")
```

### Charger l'archive en mémoire

```python
from cmc_fetch import load_runs

# Tout l'archive
df = load_runs("hrdps_continental")

# Filtré par période et stations
df = load_runs(
    "hrdps_continental",
    start="2026-03-01",
    end="2026-03-25",
    stids=["CYUL", "CYOW", "CYQB"],
)
```

### Structure d'un fichier Parquet

| Colonne | Description |
|---|---|
| `init_time` | Heure d'initialisation de la passe |
| `valid_time` | Heure de validité de la prévision |
| `fxx` | Horizon de prévision (heures) |
| `stid` | Code ICAO de l'aéroport |
| `latitude` | Latitude de l'aéroport |
| `longitude` | Longitude de l'aéroport |
| `UGRD_AGL-10m` | Composante U du vent à 10m (m/s) |
| `VGRD_AGL-10m` | Composante V du vent à 10m (m/s) |
| `TMP_AGL-2m` | Température à 2m (K) |
| `VISIFG_Sfc` | Visibilité brouillard givrant (m) — WEonG seulement |
| `VISLFG_Sfc` | Visibilité brouillard léger (m) — WEonG seulement |
| ... | Voir `cmc_config.py` pour la liste complète |

---

## 4. Ajouter des stations

Les stations sont chargées automatiquement depuis [OurAirports](https://ourairports.com) et mises en cache dans `data/airports_cache.parquet`.

Pour ajouter des stations personnalisées (ex: stations météo terrestres) :

```python
# stations.py — fonction load_custom_csv
from stations import load_custom_csv
mes_stations = load_custom_csv("Stations matrice scribe.csv")
# mes_stations doit avoir les colonnes: stid, latitude, longitude
```

Pour forcer le rechargement du cache OurAirports :

```python
from stations import load_airports
load_airports(refresh=True)
```

---

## 5. Vérifier l'état de l'archive

```bash
# Voir les passes téléchargées avec succès
python -c "
import json
log = json.load(open('data/downloaded_runs.json'))
for model, runs in log.items():
    ok = sum(1 for r in runs.values() if r['status'] == 'ok')
    fail = sum(1 for r in runs.values() if r['status'] == 'failed')
    print(f'{model}: {ok} OK, {fail} erreurs')
"
```

---

## Variables disponibles

### HRDPS continental (brut)

| Variable | Niveau | Description |
|---|---|---|
| UGRD | AGL-10m | Composante U du vent (m/s) |
| VGRD | AGL-10m | Composante V du vent (m/s) |
| WIND | AGL-10m | Vitesse du vent scalaire (m/s) |
| WDIR | AGL-10m | Direction du vent (degrés) |
| GUST | AGL-10m | Rafale de vent (m/s) |
| GUST-Min/Max | AGL-10m | Min/Max de rafale |
| TMP | AGL-2m | Température (K) |
| DPT | AGL-2m | Point de rosée (K) |
| RH | AGL-2m | Humidité relative (%) |
| PRATE | Sfc | Taux de précipitation (kg/m²/s) |
| APCP | Sfc | Précipitation accumulée (kg/m²) |
| TCDC | Sfc | Couverture nuageuse totale (%) |
| CAPE | Sfc | CAPE (J/kg) |
| PRMSL | MSL | Pression au niveau de la mer (Pa) |

### HRDPS-WEonG (post-traité, aviation)

Mêmes variables que le HRDPS + :

| Variable | Niveau | Description |
|---|---|---|
| VISIFG | Sfc | Visibilité dans le brouillard givrant/glace (m) |
| VISLFG | Sfc | Visibilité dans le brouillard léger (m) |
| SPFH | AGL-2m | Humidité spécifique (kg/kg) |
| PTYPE | Sfc | Type de précipitation |

### HRRR (AWS)

| Variable | Description |
|---|---|
| UGRD_10m | Composante U du vent (m/s) |
| VGRD_10m | Composante V du vent (m/s) |
| GUST_Sfc | Rafale de vent (m/s) |
| TMP_2m | Température (K) |
| DPT_2m | Point de rosée (K) |
| PRATE_Sfc | Taux de précipitation |
| APCP_Sfc | Précipitation accumulée |
| VIS_Sfc | Visibilité (m) |
| TCDC_atm | Couverture nuageuse (%) |
| CAPE_Sfc | CAPE (J/kg) |
| PRMSL_MSL | Pression au niveau de la mer (Pa) |
