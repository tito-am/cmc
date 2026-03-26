"""
Configuration pour l'archive de données météo canadiennes et américaines.

Modèles:
  hrdps_continental  HRDPS 2.5km brut         Canada Est  (api: cmc)
  hrdps_weong        HRDPS-WEonG post-traité   Canada Est  (api: cmc)
  hrrr               HRRR 3km                  USA CONUS   (api: search)

api="cmc"    → variables sous forme (variable, level), kwargs Herbie
api="search" → variables sous forme (search_string, col_name), .xarray(search)
"""
from pathlib import Path

from stations import hrdps_airports, hrrr_airports

DATA_DIR = Path(__file__).parent / "data"
LOG_FILE = DATA_DIR / "downloaded_runs.json"

# ── Gestion du cache GRIB ─────────────────────────────────────────────────────
# Après extraction des points, que faire du fichier GRIB téléchargé?
#
#   None              → laisser dans le cache herbie (~~/data/{model}/) — défaut herbie
#   "delete"          → supprimer immédiatement (économise l'espace disque)
#   Path("/mon/dossier/gribs") → déplacer vers ce dossier (archive GRIB complète)
#
# Exemple pour archiver les GRIB:
#   GRIB_CACHE = Path("/Volumes/MonDisque/archive_grib")
GRIB_CACHE = "delete"

# ── Variables ─────────────────────────────────────────────────────────────────

# Format CMC : (variable, level)  — noms du datamart ECCC
VARIABLES_HRDPS = [
    ("UGRD",     "AGL-10m"),
    ("VGRD",     "AGL-10m"),
    ("WIND",     "AGL-10m"),
    ("WDIR",     "AGL-10m"),
    ("GUST",     "AGL-10m"),
    ("GUST-Min", "AGL-10m"),
    ("GUST-Max", "AGL-10m"),
    ("TMP",      "AGL-2m"),
    ("DPT",      "AGL-2m"),
    ("RH",       "AGL-2m"),
    ("PRATE",    "Sfc"),
    ("APCP",     "Sfc"),
    ("TCDC",     "Sfc"),
    ("CAPE",     "Sfc"),
    ("PRMSL",    "MSL"),
]

VARIABLES_WEONG = [
    ("VISIFG",   "Sfc"),      # Visibilité brouillard givrant / glace
    ("VISLFG",   "Sfc"),      # Visibilité brouillard léger
    ("UGRD",     "AGL-10m"),
    ("VGRD",     "AGL-10m"),
    ("WIND",     "AGL-10m"),
    ("WDIR",     "AGL-10m"),
    ("GUST",     "AGL-10m"),
    ("TMP",      "AGL-2m"),
    ("DPT",      "AGL-2m"),
    ("SPFH",     "AGL-2m"),
    ("PRATE",    "Sfc"),
    ("PTYPE",    "Sfc"),
    ("TCDC",     "Sfc"),
    ("CAPE",     "Sfc"),
]

# Format NOAA/HRRR : (search_string, col_name)  — regex GRIB
VARIABLES_HRRR = [
    (":UGRD:10 m above ground:",    "UGRD_10m"),
    (":VGRD:10 m above ground:",    "VGRD_10m"),
    (":GUST:surface:",              "GUST_Sfc"),
    (":TMP:2 m above ground:",      "TMP_2m"),
    (":DPT:2 m above ground:",      "DPT_2m"),
    (":PRATE:surface:",             "PRATE_Sfc"),
    (":APCP:surface:",              "APCP_Sfc"),
    (":VIS:surface:",               "VIS_Sfc"),
    (":TCDC:entire atmosphere:",    "TCDC_atm"),
    (":CAPE:surface:",              "CAPE_Sfc"),
    (":PRMSL:mean sea level:",      "PRMSL_MSL"),
]

# ── Paramètres du modèle ──────────────────────────────────────────────────────

MODEL_RUNS_UTC = [0, 6, 12, 18]   # commun aux trois modèles

MODELS = {
    "hrdps_continental": {
        "model":      "hrdps",
        "product":    "continental",
        "source":     "msc",
        "api":        "cmc",          # variable+level kwargs
        "variables":  VARIABLES_HRDPS,
        "fxx":        list(range(1, 48)),
        "stations":   hrdps_airports,     # callable → évalué au moment du run
    },
    "hrdps_weong": {
        "model":      "hrdps",
        "product":    "continental",
        "source":     "msc-WEonG",
        "api":        "cmc",
        "variables":  VARIABLES_WEONG,
        "fxx":        list(range(1, 49)),
        "stations":   hrdps_airports,
    },
    "hrrr": {
        "model":      "hrrr",
        "product":    "sfc",
        "source":     "aws",          # HRRR dispo sur AWS
        "api":        "search",       # search strings GRIB
        "variables":  VARIABLES_HRRR,
        "fxx":        list(range(1, 19)),  # 1–18h disponible sur toutes les passes
        "stations":   hrrr_airports,
    },
}
