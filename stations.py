"""
Gestion des points d'intérêt pour l'extraction de prévisions.

Source aéroports : OurAirports (https://ourairports.com)
  → CSV libre, ~74 000 aéroports mondiaux, mis à jour régulièrement.

Les coordonnées sont mises en cache localement (data/airports_cache.parquet)
pour éviter un téléchargement à chaque exécution.
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

OURAIRPORTS_URL = (
    "https://davidmegginson.github.io/ourairports-data/airports.csv"
)
CACHE_PATH = Path(__file__).parent / "data" / "airports_cache.parquet"


# ── Chargement des aéroports ──────────────────────────────────────────────────

def load_airports(
    countries: list[str] = ["CA", "US"],
    types: list[str] = ["large_airport", "medium_airport"],
    refresh: bool = False,
) -> pd.DataFrame:
    """
    Charge les aéroports depuis le cache local ou OurAirports.

    Paramètres
    ----------
    countries : liste de codes ISO-2 (ex: ["CA", "US"])
    types     : types d'aéroports OurAirports à inclure
                  "large_airport", "medium_airport", "small_airport"
    refresh   : force le re-téléchargement même si le cache existe

    Retourne
    --------
    DataFrame avec colonnes: stid (ICAO), iata, name, latitude, longitude,
                             country, type, elevation_ft
    """
    if CACHE_PATH.exists() and not refresh:
        df = pd.read_parquet(CACHE_PATH)
    else:
        log.info("Téléchargement OurAirports…")
        raw = pd.read_csv(OURAIRPORTS_URL, low_memory=False)
        df = _clean_ourairports(raw)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(CACHE_PATH, index=False)
        log.info("Cache sauvegardé: %s (%d aéroports)", CACHE_PATH, len(df))

    mask = (
        df["country"].isin(countries) &
        df["type"].isin(types) &
        df["latitude"].notna() &
        df["longitude"].notna()
    )
    result = df[mask].reset_index(drop=True)
    log.info("Aéroports chargés: %d (%s)", len(result), ", ".join(countries))
    return result


def _clean_ourairports(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes OurAirports."""
    return (
        raw[["ident", "iata_code", "name", "latitude_deg",
             "longitude_deg", "iso_country", "type", "elevation_ft"]]
        .rename(columns={
            "ident":         "stid",
            "iata_code":     "iata",
            "latitude_deg":  "latitude",
            "longitude_deg": "longitude",
            "iso_country":   "country",
        })
        .copy()
    )


# ── Filtres géographiques par domaine de modèle ───────────────────────────────

def filter_hrdps_domain(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtre les aéroports dans le domaine du HRDPS continental.
    Domaine approximatif: Canada de l'Est + Ontario + partie des Maritimes.
    """
    return df[
        (df["country"] == "CA") &
        (df["latitude"].between(41, 62)) &
        (df["longitude"].between(-100, -50))
    ].reset_index(drop=True)


def filter_hrrr_domain(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtre les aéroports dans le domaine du HRRR (CONUS + sud Canada).
    """
    return df[
        (df["latitude"].between(21, 53)) &
        (df["longitude"].between(-135, -60))
    ].reset_index(drop=True)


# ── Chargement depuis un CSV personnalisé ─────────────────────────────────────

def load_custom_csv(path: str | Path) -> pd.DataFrame:
    """
    Charge des stations depuis un CSV local (ex: 'Stations matrice scribe.csv').
    Attend les colonnes OACI/NOMSTN/LAT/LON ou stid/name/latitude/longitude.
    """
    df = pd.read_csv(path)
    rename = {
        "OACI": "stid", "NOMSTN": "name",
        "LAT":  "latitude", "LON": "longitude",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


# ── Accès rapide ──────────────────────────────────────────────────────────────

def canadian_airports(**kwargs) -> pd.DataFrame:
    return load_airports(countries=["CA"], **kwargs)


def us_airports(**kwargs) -> pd.DataFrame:
    return load_airports(countries=["US"], **kwargs)


def hrdps_airports(**kwargs) -> pd.DataFrame:
    return filter_hrdps_domain(load_airports(countries=["CA"], **kwargs))


def hrrr_airports(**kwargs) -> pd.DataFrame:
    return filter_hrrr_domain(load_airports(countries=["US"], **kwargs))
