"""
Mise à jour incrémentale: télécharge les nouvelles passes disponibles.

À rouler plusieurs fois par jour (ex: cron toutes les 2h ou 4x/jour après
la publication de chaque passe). Le script vérifie quelles passes récentes
ne sont pas encore téléchargées et les télécharge.

Publication approximative des passes HRDPS sur le datamart:
    Passe 00Z → disponible ~03:00-04:00 UTC
    Passe 06Z → disponible ~09:00-10:00 UTC
    Passe 12Z → disponible ~15:00-16:00 UTC
    Passe 18Z → disponible ~21:00-22:00 UTC

Usage:
    python cmc_update.py
    python cmc_update.py --model hrdps_continental
    python cmc_update.py --lookback 48    # vérifier les 48 dernières heures
    python cmc_update.py --wait           # attendre la passe courante (HerbieWait)
    python cmc_update.py --wait --wait-for 30min --check-every 2min

Cron (exemple, toutes les 2 heures):
    0 */2 * * * cd /path/to/cmc && conda run -n cmc python cmc_update.py >> logs/update.log 2>&1
"""
import argparse
import logging
from pathlib import Path

import pandas as pd
from herbie import Herbie
from herbie.latest import HerbieWait

from cmc_config import MODEL_RUNS_UTC, MODELS
from cmc_fetch import download_run, is_already_downloaded

log = logging.getLogger(__name__)

# Délai minimal (heures) après l'heure de la passe avant de tenter le téléchargement.
# Donne le temps au datamart d'être complet.
PUBLICATION_DELAY_H = 3


def wait_for_run(
    run: pd.Timestamp,
    model_key: str,
    wait_for: str = "60min",
    check_interval: str = "2min",
) -> bool:
    """
    Attend qu'au moins un fichier d'une passe soit disponible sur le serveur.

    Pour les modèles NOAA (HRRR), délègue à HerbieWait.
    Pour les modèles CMC (HRDPS, WEonG), poll H.grib directement.

    Retourne True si la donnée est disponible, False si timeout.
    """
    cfg = MODELS[model_key]
    first_var, first_lev = cfg["variables"][0]
    first_fxx = cfg["fxx"][0]

    if cfg["api"] == "search":
        # NOAA — HerbieWait gère le polling
        log.info("  Attente données %s %s (HerbieWait, max %s)…", model_key, run, wait_for)
        try:
            HerbieWait(
                run=run,
                model=cfg["model"],
                fxx=first_fxx,
                wait_for=wait_for,
                check_interval=check_interval,
            )
            return True
        except TimeoutError:
            log.warning("  Timeout — données non disponibles après %s", wait_for)
            return False
    else:
        # CMC — poll manuel avec H.grib
        import time
        wait_s    = pd.Timedelta(wait_for).total_seconds()
        interval_s = pd.Timedelta(check_interval).total_seconds()
        t0 = pd.Timestamp("now")
        log.info("  Attente données %s %s (max %s, vérif. toutes les %s)…",
                 model_key, run, wait_for, check_interval)
        while True:
            H = Herbie(
                run,
                model=cfg["model"],
                product=cfg["product"],
                source=cfg["source"],
                fxx=first_fxx,
                variable=first_var,
                level=first_lev,
            )
            if H.grib is not None:
                log.info("  Données disponibles.")
                return True
            elapsed = (pd.Timestamp("now") - t0).total_seconds()
            if elapsed >= wait_s:
                log.warning("  Timeout — données non disponibles après %s", wait_for)
                return False
            log.info("  Pas encore disponible, nouvelle vérification dans %s…", check_interval)
            time.sleep(interval_s)


def get_pending_runs(lookback_hours: int = 36) -> list[pd.Timestamp]:
    """
    Retourne les passes qui devraient être disponibles mais ne sont pas encore
    téléchargées.
    """
    now = pd.Timestamp.now("UTC").tz_convert(None)  # tz-naive, requis par Herbie
    start = now - pd.Timedelta(hours=lookback_hours)

    pending = []
    t = start.floor("6h")
    while t <= now:
        if t.hour in MODEL_RUNS_UTC:
            hours_since_run = (now - t).total_seconds() / 3600
            if hours_since_run >= PUBLICATION_DELAY_H:
                pending.append(t)
        t += pd.Timedelta(hours=6)

    return pending


def update(
    model_keys: list[str],
    lookback_hours: int = 36,
    wait: bool = False,
    wait_for: str = "60min",
    check_interval: str = "2min",
) -> None:
    runs = get_pending_runs(lookback_hours)
    log.info("Passes candidates: %d (sur les %dh passées)", len(runs), lookback_hours)

    for model_key in model_keys:
        log.info("\n>>> Modèle: %s <<<", model_key)
        ok = failed = skipped = 0

        for i, run in enumerate(runs):
            run_key = run.strftime("%Y%m%d_%HZ")
            if is_already_downloaded(run_key, model_key):
                log.debug("  %s déjà téléchargé", run_key)
                skipped += 1
                continue

            # Pour la passe la plus récente, attendre si demandé
            if wait and i == len(runs) - 1:
                available = wait_for_run(run, model_key, wait_for, check_interval)
                if not available:
                    failed += 1
                    continue

            log.info("  Nouvelle passe: %s", run_key)
            try:
                result = download_run(run, model_key=model_key, skip_if_exists=False)
                if result is not None:
                    ok += 1
                else:
                    failed += 1
            except Exception as exc:
                log.error("  ERREUR %s: %s", run_key, exc)
                failed += 1

        log.info(
            ">>> %s: %d nouveau(x), %d ignoré(s), %d erreur(s) <<<",
            model_key, ok, skipped, failed,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mise à jour incrémentale des données HRDPS")
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()) + ["all"],
        default="all",
        help="Modèle à mettre à jour (défaut: all)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=36,
        help="Fenêtre de vérification en heures (défaut: 36)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Attendre la passe la plus récente si pas encore disponible (HerbieWait)",
    )
    parser.add_argument(
        "--wait-for",
        default="60min",
        help="Durée maximale d'attente, ex: '30min', '2h' (défaut: 60min)",
    )
    parser.add_argument(
        "--check-every",
        default="2min",
        help="Intervalle entre chaque vérification, ex: '1min', '30s' (défaut: 2min)",
    )
    args = parser.parse_args()

    # Créer le dossier de logs
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "cmc_update.log"),
        ],
    )

    model_keys = list(MODELS.keys()) if args.model == "all" else [args.model]
    update(
        model_keys,
        lookback_hours=args.lookback,
        wait=args.wait,
        wait_for=args.wait_for,
        check_interval=args.check_every,
    )


if __name__ == "__main__":
    main()
