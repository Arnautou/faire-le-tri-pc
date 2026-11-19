import argparse
import shutil
import time
import hashlib
from pathlib import Path
from collections import defaultdict
from exif_extract import extract_date, exiftool_available, PHOTO_EXTS, VIDEO_EXTS

IGNORED_FOLDER_NAMES = {
    'dcim', 'photos', 'pictures', 'camera', 'images', 'img', '100apple', 
    'whatsapp', 'photos partagées', 'photos pas faite sur papier'
}

def get_file_hash(filepath, chunk_size=8192):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_folder_title(file_path, src_root):
    parent = file_path.parent
    if parent == src_root:
        return None
    name = parent.name.strip()
    if name.lower() in IGNORED_FOLDER_NAMES or name.isdigit() or len(name) < 4:
        return None
    return name

def organize(src: Path, dst: Path, apply: bool, include_videos: bool, keep_titles: bool):
    src = Path(src).resolve()
    dst = Path(dst).resolve()
    exts = PHOTO_EXTS | (VIDEO_EXTS if include_videos else set())
    
    et_ok = exiftool_available()
    print("Recherche des fichiers en cours (cela peut prendre un peu de temps sur un gros disque)...")
    files = [p for p in src.rglob('*') if p.is_file() and p.suffix.lower() in exts]
    
    print(f"Source          : {src}")
    print(f"Destination     : {dst}")
    print(f"Mode            : {'🚀 COPIE RÉELLE' if apply else '👀 SIMULATION (dry-run)'}")
    print(f"Titres dossiers : {'OUI (fusion avec le mois)' if keep_titles else 'NON'}")
    print(f"Fichiers à traiter : {len(files)}\n")

    if not files:
        print("Aucun fichier trouvé.")
        return

    stats = defaultdict(int)
    errors = []
    seen_hashes = set()
    t0 = time.time()
    examples_shown = 0
    
    for i, p in enumerate(files, 1):
        try:
            r = extract_date(p, _exiftool_ok=et_ok)
            
            if r.dt:
                year_str = f"{r.dt.year:04d}"
                month_str = f"{r.dt.month:02d}"
            else:
                year_str = "_sans_exif"
                month_str = ""
                
            title = get_folder_title(p, src) if keep_titles else None
            
            if title and r.dt:
                folder_name = f"{month_str}_{title}"
                target_dir = dst / year_str / folder_name
            elif r.dt:
                target_dir = dst / year_str / month_str
            else:
                target_dir = dst / year_str
            
            rel_path = target_dir.relative_to(dst)
            
            if examples_shown < 5:
                print(f"  [EXEMPLE] {p.name} -> {rel_path}")
                examples_shown += 1

            if apply:
                file_hash = get_file_hash(p)
                if file_hash in seen_hashes:
                    stats["_doublons_ignores"] += 1
                    continue
                seen_hashes.add(file_hash)
                
            stats[str(rel_path)] += 1
                
            target_file = target_dir / p.name
            counter = 1
            while apply and target_file.exists():
                target_file = target_dir / f"{p.stem}_{counter}{p.suffix}"
                counter += 1

            if apply:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target_file)

        except Exception as e:
            # Si un fichier pose problème (chemin trop long, accès refusé...), on l'enregistre et on continue
            errors.append(f"{p} : {e}")
            stats["_erreurs"] += 1
            
        if i % 1000 == 0 or i == len(files):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            print(f"  {i}/{len(files)}  ({rate:5.1f} f/s)")

    print("\n=== RÉSUMÉ ===")
    for folder in sorted(stats.keys()):
        print(f"  {folder:45s} : {stats[folder]:5d} fichiers")
    
    if errors:
        err_file = dst / "_erreurs_copie.txt"
        with open(err_file, "w", encoding="utf-8") as f:
            f.write("\n".join(errors))
        print(f"\n⚠️ {len(errors)} erreurs rencontrées. Détails dans : {err_file}")

    print(f"\nDurée : {time.time()-t0:.1f}s")
    if not apply:
        print("\n💡 Ceci était une simulation. Relance avec --apply pour copier réellement.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src', help="Dossier source à scanner")
    ap.add_argument('dst', help="Nouveau dossier propre")
    ap.add_argument('--apply', action='store_true', help="Exécuter la copie")
    ap.add_argument('--videos', action='store_true', help="Inclure les vidéos")
    ap.add_argument('--no-titles', action='store_true', help="Ne pas garder les noms des dossiers d'origine")
    args = ap.parse_args()
    
    organize(
        src=Path(args.src), 
        dst=Path(args.dst), 
        apply=args.apply, 
        include_videos=args.videos,
        keep_titles=not args.no_titles
    )

if __name__ == "__main__":
    main()