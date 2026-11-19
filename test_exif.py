"""
Teste l'extraction EXIF sur un dossier (récursif).
Génère un CSV détaillé + un aperçu de l'arborescence cible. Ne copie AUCUN fichier.
"""
import argparse
import csv
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from exif_extract import (
    extract_date, exiftool_available, PHOTO_EXTS, VIDEO_EXTS,
)

def scan(src: Path, out_dir: Path, prefer_exiftool: bool,
         include_videos: bool, sample: int | None):
    src = Path(src)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exts = PHOTO_EXTS | (VIDEO_EXTS if include_videos else set())
    files: list[Path] = []
    for p in src.rglob('*'):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
            if sample and len(files) >= sample:
                break

    et_ok = exiftool_available()
    print(f"Dossier         : {src}")
    print(f"Fichiers trouvés: {len(files)}")
    print(f"ExifTool        : {'OK' if et_ok else 'ABSENT (fallback Pillow + dates fichier)'}")
    print(f"Mode            : {'ExifTool prioritaire' if prefer_exiftool else 'Pillow prioritaire'}")
    print()

    by_source = defaultdict(int)
    by_engine = defaultdict(int)
    preview_exif = defaultdict(int)
    preview_all = defaultdict(int)
    no_exif_files: list[Path] = []

    csv_path = out_dir / 'exif_report.csv'
    t0 = time.time()
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['path', 'size', 'ext', 'datetime', 'tag',
                    'engine', 'confidence', 'raw'])
        for i, p in enumerate(files, 1):
            r = extract_date(p, prefer_exiftool=prefer_exiftool, _exiftool_ok=et_ok)
            key = f"{r.engine}:{r.tag}" if r.tag else 'unknown'
            by_source[key] += 1
            by_engine[r.engine] += 1

            if r.dt:
                ym = f"{r.dt.year}/{r.dt.month:02d}"
                preview_all[ym] += 1
                if r.is_exif:
                    preview_exif[ym] += 1
                else:
                    no_exif_files.append(p)
            else:
                preview_all['_unknown'] += 1
                preview_exif['_unknown'] += 1
                no_exif_files.append(p)

            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            w.writerow([str(p), size, p.suffix.lower(),
                        r.dt.isoformat() if r.dt else '',
                        r.tag or '', r.engine, r.confidence, r.raw or ''])

            if i % 100 == 0 or i == len(files):
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed else 0
                print(f"  {i}/{len(files)}  ({rate:5.1f} f/s)  dernier: {key}")

    # --- Résumé ---
    total = len(files) or 1
    total_exif = sum(v for k, v in by_source.items()
                     if k.startswith(('pillow:', 'exiftool:')))

    print("\n=== SOURCES DE LA DATE ===")
    for k in sorted(by_source, key=lambda x: -by_source[x]):
        print(f"  {k:35s} {by_source[k]:6d}")

    print("\n=== PAR MOTEUR ===")
    for k in sorted(by_engine, key=lambda x: -by_engine[x]):
        print(f"  {k:35s} {by_engine[k]:6d}")

    print(f"\nEXIF trouvé : {total_exif}/{total} ({100*total_exif/total:5.1f}%)")
    print(f"Sans EXIF   : {total - total_exif}  (fallback dates fichier)")
    print(f"Durée       : {time.time()-t0:.1f}s")

    print("\n=== APERÇU ARBORESCENCE CIBLE (AAAA/MM) ===")
    print(f"{'Dossier':15s} {'EXIF seul':>10s} {'Avec fallback':>15s}")
    for k in sorted(preview_all):
        print(f"{k:15s} {preview_exif.get(k,0):>10d} {preview_all[k]:>15d}")

    if no_exif_files:
        nf = out_dir / 'no_exif.txt'
        with open(nf, 'w', encoding='utf-8') as f:
            for p in no_exif_files:
                f.write(str(p) + '\n')
        print(f"\nListe des fichiers sans EXIF : {nf}")

    print(f"Rapport CSV complet         : {csv_path}")


def main():
    ap = argparse.ArgumentParser(description="Testeur d'extraction EXIF")
    ap.add_argument('src', help="Dossier à scanner (récursif)")
    ap.add_argument('-o', '--out', default='./exif_test_out')
    ap.add_argument('--prefer-exiftool', action='store_true')
    ap.add_argument('--videos', action='store_true')
    ap.add_argument('--sample', type=int, default=None,
                    help="Limiter à N fichiers (test rapide, ex: 50)")
    args = ap.parse_args()
    scan(Path(args.src), Path(args.out), args.prefer_exiftool,
         args.videos, args.sample)


if __name__ == '__main__':
    main()