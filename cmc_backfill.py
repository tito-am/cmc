"""
Backfill: télécharge un historique de prévisions météo.

Deux cas d'usage:

1. ECCC (hrdps_continental, hrdps_weong)
   Le datamart MSC conserve ~30 jours. Utiliser --days pour spécifier
   combien de jours en arrière récupérer.

   python cmc_backfill.py --model hrdps_continental --days 30

2. HRRR (AWS)
   Le bucket AWS de NOAA contient plusieurs années d'archives HRRR
   (depuis ~2014), avec des lacunes possibles. Utiliser --start et --end
   pour spécifier une plage de dates. Les erreurs sont tolérées et
   loggées — le script continue sur la passe suivante.

   python cmc_backfill.py --model hrrr --start 2022-01-01 --end 2022-12-31

Options:
    --model     Modèle: hrdps_continental, hrdps_weong, hrrr, all
    --days      Nombre de jours en arrière depuis aujourd'hui (ECCC)
    --start     Date de début, format YYYY-MM-DD (HRRR ou ECCC)
    --end       Date de fin, format YYYY-MM-DD (défaut: aujourd'hui)
    --no-skip   Re-télécharger même les passes déjà présentes
    --runs      Passes UTC à inclure: 0 6 12 18 (défaut: toutes)
"""
import argparse
import logging
from pathlib import Path

import pandas as pd

from cmc_config import MODEL_RUNS_UTC, MODELS
from cmc_fetch import download_run

log = logging.getLogger(__name__)


def iter_runs(
    start: pd.Timestamp,
    end: pd.Timestamp,
    runs_utc: list[int] = MODEL_RUNS_UTC,
) -> list[pd.Timestamp]:
    """Génère toutes les heures d'initialisation entre start et end."""
    result = []
    t = start.floor("6h")
    while t <= end:
        if t.hour in runs_utc:
            result.append(t)
        t += pd.Timedelta(hours=6)
    return result


def backfill(
    model_keys: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    runs_utc: list[int] = MODEL_RUNS_UTC,
    skip_existing: bool = True,
) -> None:
    runs = iter_runs(start, end, runs_utc)
    if not runs:
        log.warning("Aucune passe dans la plage %s → %s", start, end)
        return

    log.info("Passes à télécharger: %d  (%s → %s)", len(runs), runs[0], runs[-1])

    for model_key in model_keys:
        log.info("\n>>> Modèle: %s <<<", model_key)
        ok = failed = skipped = 0

        for run in runs:
            try:
                result = download_run(
                    run,
                    model_key=model_key,
                    skip_if_exists=skip_existing,
                )
                if result is None:
                    skipped += 1
                else:
                    ok += 1
            except Exception as exc:
                # Tolérer les lacunes d'archive (surtout HRRR sur AWS)
                log.warning("  Passe ignorée %s: %s", run.strftime("%Y%m%d_%HZ"), exc)
                failed += 1

        log.info(
            ">>> %s terminé: %d OK, %d ignoré(s)/déjà présent(s), %d erreur(s) <<<",
            model_key, ok, skipped, failed,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill de prévisions météo (ECCC / HRRR AWS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()) + ["all"],
        default="hrdps_continental",
        help="Modèle (défaut: hrdps_continental)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Jours en arrière depuis aujourd'hui (raccourci pour --start)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Date de début YYYY-MM-DD (ex: 2022-01-01)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Date de fin YYYY-MM-DD (défaut: aujourd'hui)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        nargs="+",
        default=MODEL_RUNS_UTC,
        metavar="HH",
        help="Passes UTC à inclure (défaut: 0 6 12 18)",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-télécharger même les passes déjà présentes",
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
            logging.FileHandler(log_dir / "cmc_backfill.log"),
        ],
    )

    # Résoudre les dates
    now = pd.Timestamp.now("UTC").tz_convert(None)
    end = pd.Timestamp(args.end) if args.end else now - pd.Timedelta(hours=3)

    if args.days:
        start = now - pd.Timedelta(days=args.days)
    elif args.start:
        start = pd.Timestamp(args.start)
    else:
        # Défaut: 30 jours pour ECCC, erreur pour HRRR sans --start
        if args.model == "hrrr":
            parser.error("--start est requis pour le modèle hrrr (ex: --start 2022-01-01)")
        start = now - pd.Timedelta(days=30)

    model_keys = list(MODELS.keys()) if args.model == "all" else [args.model]

    backfill(
        model_keys,
        start=start,
        end=end,
        runs_utc=args.runs,
        skip_existing=not args.no_skip,
    )


if __name__ == "__main__":
    main()
