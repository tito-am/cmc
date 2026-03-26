"""
Module central de téléchargement des prévisions météo.

Supporte deux types d'API Herbie:
  api="cmc"    → modèles ECCC (HRDPS, WEonG) : Herbie(variable=, level=)
  api="search" → modèles NOAA (HRRR, GFS)    : H.xarray(search_string)

Données sauvegardées en Parquet: data/{model_key}/{YYYYMMDD_HHz}.parquet
Chaque fichier = toutes les stations × toutes les heures de prévision (fxx).

Usage:
    from cmc_fetch import download_run, load_runs

    df = download_run("2026-03-25 00:00", model_key="hrdps_continental")
    df = download_run("2026-03-25 00:00", model_key="hrrr")
    all_data = load_runs("hrdps_continental", stids=["CYUL", "CYOW"])
"""
import json
import logging
from datetime import datetime, timezone

import pandas as pd
from herbie import Herbie

from cmc_config import DATA_DIR, GRIB_CACHE, LOG_FILE, MODELS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Journal des passes téléchargées ──────────────────────────────────────────

def load_download_log() -> dict:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return {}


def save_download_log(log_data: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log_data, indent=2, default=str))


def is_already_downloaded(run_key: str, model_key: str) -> bool:
    return load_download_log().get(model_key, {}).get(run_key, {}).get("status") == "ok"


def mark_downloaded(run_key: str, model_key: str, n_rows: int) -> None:
    dl = load_download_log()
    dl.setdefault(model_key, {})[run_key] = {
        "status": "ok",
        "n_rows": n_rows,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_download_log(dl)


def mark_failed(run_key: str, model_key: str, error: str) -> None:
    dl = load_download_log()
    dl.setdefault(model_key, {})[run_key] = {
        "status": "failed",
        "error": str(error)[:300],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_download_log(dl)


# ── Gestion du cache GRIB ────────────────────────────────────────────────────

def _handle_grib(H: "Herbie") -> None:
    """
    Supprime ou déplace le fichier GRIB local selon GRIB_CACHE.
    Appelé après chaque H.xarray() pour éviter l'accumulation dans ~/data/.
    """
    if GRIB_CACHE is None:
        return  # laisser herbie gérer son cache

    local = H.get_localFilePath()
    if not local.exists():
        return

    if GRIB_CACHE == "delete":
        local.unlink()
        log.debug("    GRIB supprimé: %s", local.name)
    else:
        # Déplacer vers le dossier d'archive défini par l'utilisateur
        dest_dir = GRIB_CACHE / H.model / f"{H.date:%Y%m%d}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / local.name
        if not dest.exists():
            local.rename(dest)
            log.debug("    GRIB archivé: %s", dest)
        else:
            local.unlink()  # doublon, supprimer


# ── Extraction d'une variable à un fxx ───────────────────────────────────────

def _fetch_cmc(
    init_time: pd.Timestamp,
    fxx: int,
    variable: str,
    level: str,
    model: str,
    product: str,
    source: str,
    stations: pd.DataFrame,
) -> pd.Series | None:
    """Modèles ECCC (HRDPS, WEonG) — variable et level passés en kwargs."""
    try:
        H = Herbie(
            init_time,
            model=model,
            product=product,
            source=source,
            fxx=fxx,
            variable=variable,
            level=level,
        )
        if H.grib is None:
            log.debug("    CMC %s/%s fxx=%03d: fichier absent du datamart", variable, level, fxx)
            return None
        ds = H.xarray()
        dsp = ds.herbie.pick_points(stations, method="nearest")
        df = dsp.compute().to_dataframe().reset_index()  # force la lecture avant suppression
        _handle_grib(H)

        # pick_points préfixe les colonnes stations avec "point_"
        if "point_stid" in df.columns:
            df = df.rename(columns={"point_stid": "stid"})

        skip = {"stid", "latitude", "longitude", "valid_time", "time", "step",
                "point", "point_grid_distance", "gribfile_projection",
                "heightAboveGround", "surface", "cloudBase",
                "meanSea", "lowCloudLayer", "atmosphereSingleLayer"}
        skip |= {c for c in df.columns if c.startswith("point_")}
        val_cols = [c for c in df.columns if c not in skip]
        if not val_cols:
            return None

        col_name = f"{variable}_{level}".replace(" ", "")
        return df.set_index("stid")[val_cols[0]].rename(col_name)

    except Exception as exc:
        log.warning("    CMC %s/%s fxx=%03d: %s", variable, level, fxx, exc)
        return None


def _fetch_search(
    init_time: pd.Timestamp,
    fxx: int,
    search: str,
    col_name: str,
    model: str,
    product: str,
    source: str,
    stations: pd.DataFrame,
) -> pd.Series | None:
    """Modèles NOAA (HRRR, GFS, NAM) — search string GRIB."""
    try:
        H = Herbie(
            init_time,
            model=model,
            product=product,
            source=source,
            fxx=fxx,
        )
        if H.grib is None:
            log.debug("    SEARCH %s fxx=%03d: fichier absent", search, fxx)
            return None
        ds = H.xarray(search)
        # xarray peut retourner un Dataset (plusieurs messages) — prendre le premier
        if hasattr(ds, "data_vars"):
            var = list(ds.data_vars)[0]
            ds = ds[var]

        dsp = ds.herbie.pick_points(stations, method="nearest")
        df = dsp.compute().to_dataframe().reset_index()  # force la lecture avant suppression
        _handle_grib(H)

        if "point_stid" in df.columns:
            df = df.rename(columns={"point_stid": "stid"})

        skip = {"stid", "latitude", "longitude", "valid_time", "time", "step",
                "point", "point_grid_distance", "gribfile_projection",
                "heightAboveGround", "surface", "cloudBase",
                "meanSea", "lowCloudLayer", "atmosphereSingleLayer"}
        skip |= {c for c in df.columns if c.startswith("point_")}
        val_cols = [c for c in df.columns if c not in skip]
        if not val_cols:
            return None

        return df.set_index("stid")[val_cols[0]].rename(col_name)

    except Exception as exc:
        log.warning("    SEARCH %s fxx=%03d: %s", search, fxx, exc)
        return None


# ── Téléchargement d'une passe complète ───────────────────────────────────────

def download_run(
    init_time: str | pd.Timestamp,
    model_key: str = "hrdps_continental",
    skip_if_exists: bool = True,
) -> pd.DataFrame | None:
    """
    Télécharge toutes les variables et heures de prévision d'une passe.

    Paramètres
    ----------
    init_time     : heure d'initialisation, ex: "2026-03-25 00:00"
    model_key     : "hrdps_continental", "hrdps_weong" ou "hrrr"
    skip_if_exists: ignore si déjà téléchargé avec succès

    Retourne
    --------
    DataFrame: init_time, valid_time, fxx, stid, latitude, longitude + variables
    Sauvegardé dans data/{model_key}/{YYYYMMDD_HHz}.parquet
    """
    init_time = pd.Timestamp(init_time)
    cfg = MODELS[model_key]

    model     = cfg["model"]
    product   = cfg["product"]
    source    = cfg["source"]
    api       = cfg["api"]
    variables = cfg["variables"]
    fxx_list  = cfg["fxx"]
    # "stations" peut être un callable (hrdps_airports, hrrr_airports) ou un DataFrame
    stations_cfg = cfg["stations"]
    stations = stations_cfg() if callable(stations_cfg) else stations_cfg

    run_key = init_time.strftime("%Y%m%d_%HZ")
    log.info("=== %s | %s | %d stations ===", model_key, run_key, len(stations))

    if skip_if_exists and is_already_downloaded(run_key, model_key):
        log.info("  Déjà téléchargé – ignoré.")
        return None

    rows = []
    for fxx in fxx_list:
        series_list = []

        for var_def in variables:
            if api == "cmc":
                variable, level = var_def
                s = _fetch_cmc(init_time, fxx, variable, level,
                               model, product, source, stations)
            else:  # search
                search, col_name = var_def
                s = _fetch_search(init_time, fxx, search, col_name,
                                  model, product, source, stations)

            if s is not None:
                series_list.append(s)

        if not series_list:
            log.warning("  fxx=%03d: aucune donnée", fxx)
            continue

        df_fxx = pd.concat(series_list, axis=1).reset_index()
        df_fxx = df_fxx.merge(
            stations[["stid", "latitude", "longitude"]], on="stid", how="left"
        )
        df_fxx["init_time"]  = init_time
        df_fxx["valid_time"] = init_time + pd.Timedelta(hours=fxx)
        df_fxx["fxx"]        = fxx
        rows.append(df_fxx)
        log.info("  fxx=%03d: %d stations, %d variables", fxx, len(df_fxx), len(series_list))

    if not rows:
        log.error("  Aucune donnée pour %s %s", model_key, run_key)
        mark_failed(run_key, model_key, "no data")
        return None

    df = pd.concat(rows, ignore_index=True)
    meta_cols = ["init_time", "valid_time", "fxx", "stid", "latitude", "longitude"]
    var_cols  = [c for c in df.columns if c not in meta_cols]
    df = df[meta_cols + var_cols].sort_values(["fxx", "stid"]).reset_index(drop=True)

    # Assurer des types datetime lisibles (évite l'entier ms dans les aperçus)
    df["init_time"]  = pd.to_datetime(df["init_time"]).dt.floor("s")
    df["valid_time"] = pd.to_datetime(df["valid_time"]).dt.floor("s")

    out_dir = DATA_DIR / model_key
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_key}.parquet"
    df.to_parquet(out_path, index=False)

    mark_downloaded(run_key, model_key, len(df))
    log.info("  → %s (%d lignes)", out_path.name, len(df))
    return df


# ── Lecture ───────────────────────────────────────────────────────────────────

def load_runs(
    model_key: str = "hrdps_continental",
    start: str | None = None,
    end: str | None = None,
    stids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Charge toutes les passes sauvegardées en mémoire.

    Paramètres
    ----------
    model_key    : modèle à charger
    start, end   : filtre sur init_time, ex: "2026-03-01", "2026-03-25"
    stids        : filtre sur stations, ex: ["CYUL", "KJFK"]
    """
    data_dir = DATA_DIR / model_key
    files = sorted(data_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Aucune donnée dans {data_dir}")

    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    if start:
        df = df[df["init_time"] >= pd.Timestamp(start)]
    if end:
        df = df[df["init_time"] <= pd.Timestamp(end)]
    if stids:
        df = df[df["stid"].isin(stids)]

    return df.sort_values(["init_time", "fxx", "stid"]).reset_index(drop=True)
