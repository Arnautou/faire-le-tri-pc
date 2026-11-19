"""
Extraction robuste de la date de prise de vue.
Chaîne : Pillow (rapide) -> ExifTool (fiable, tous formats) -> dates fichier (fallback).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import os
import shutil
import subprocess
import sys

from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

PHOTO_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.tif', '.tiff',
              '.webp', '.cr2', '.nef', '.arw', '.dng', '.raf', '.orf',
              '.rw2', '.pef', '.srw', '.bmp', '.gif'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.wmv', '.mpg', '.mts'}

TAG_DATETIME_ORIGINAL = 36867
TAG_DATETIME_DIGITIZED = 36868
TAG_DATETIME = 306
EXIF_IFD_POINTER = 0x8769

_DATETIME_FORMATS = (
    '%Y:%m:%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S',
    '%Y:%m:%d %H:%M:%S.%f',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M:%S.%f',
)

def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip().strip('\x00')
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

@dataclass
class DateResult:
    dt: Optional[datetime]
    tag: Optional[str]
    engine: str
    raw: Optional[str] = None

    @property
    def is_exif(self) -> bool:
        return self.engine in ('pillow', 'exiftool') and self.tag in (
            'DateTimeOriginal', 'DateTimeDigitized', 'CreateDate', 'DateTime')

    @property
    def confidence(self) -> str:
        if self.engine in ('pillow', 'exiftool'):
            if self.tag == 'DateTimeOriginal':
                return 'high'
            if self.tag in ('CreateDate', 'DateTimeDigitized'):
                return 'medium'
            return 'low'
        if self.engine == 'os':
            return 'very_low'
        return 'none'

def _try_pillow(path: Path) -> Optional[tuple[datetime, str, str]]:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            try:
                ifd = exif.get_ifd(EXIF_IFD_POINTER) or {}
            except Exception:
                ifd = {}
            for tag, name in (
                (TAG_DATETIME_ORIGINAL, 'DateTimeOriginal'),
                (TAG_DATETIME_DIGITIZED, 'CreateDate'),
                (TAG_DATETIME,         'DateTime'),
            ):
                raw = ifd.get(tag) or exif.get(tag)
                dt = _parse_dt(raw)
                if dt:
                    return dt, name, str(raw)
    except Exception:
        return None
    return None

EXIFTOOL_TAGS = ('DateTimeOriginal', 'CreateDate', 'DateTime', 'FileModifyDate')

# --- LA MAGIE EST ICI : On cherche exiftool.exe dans le dossier du script ---
def get_exiftool_cmd() -> Optional[str]:
    # 1. Est-ce qu'il est dans le même dossier que ce script ?
    script_dir = Path(__file__).parent.resolve()
    local_exiftool = script_dir / 'exiftool.exe'
    if local_exiftool.exists():
        return str(local_exiftool)
    
    # 2. Est-ce qu'il est installé dans Windows (PATH) ?
    et_path = shutil.which('exiftool')
    if et_path:
        return et_path
        
    return None

def _try_exiftool(path: Path, exiftool_cmd: str) -> Optional[tuple[datetime, str, str]]:
    try:
        out = subprocess.run(
            [exiftool_cmd, '-j', '-s', '-q', '-q',
             '-d', '%Y-%m-%dT%H:%M:%S',
             *[f'-{t}' for t in EXIFTOOL_TAGS],
             str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        data = json.loads(out.stdout)[0]
        for tag in EXIFTOOL_TAGS:
            if tag in data:
                dt = _parse_dt(data[tag])
                if dt:
                    return dt, tag, str(data[tag])
    except Exception:
        return None
    return None

def _try_file_dates(path: Path) -> Optional[tuple[datetime, str, str]]:
    try:
        st = path.stat()
    except OSError:
        return None
    candidates = [('mtime', st.st_mtime)]
    if hasattr(st, 'st_birthtime'):
        candidates.append(('btime', st.st_birthtime))
    if os.name == 'nt':
        candidates.append(('ctime', st.st_ctime))
    for name, ts in candidates:
        try:
            return datetime.fromtimestamp(ts), name, str(ts)
        except (OSError, ValueError, OverflowError):
            continue
    return None

def exiftool_available() -> bool:
    return get_exiftool_cmd() is not None

def extract_date(path: Path, prefer_exiftool: bool = False,
                 _exiftool_ok: Optional[bool] = None) -> DateResult:
    path = Path(path)
    
    exiftool_cmd = get_exiftool_cmd() if _exiftool_ok else None

    order = [('pillow', _try_pillow)]
    if exiftool_cmd:
        # On utilise une lambda pour passer la commande exiftool
        order.append(('exiftool', lambda p: _try_exiftool(p, exiftool_cmd)))
    if prefer_exiftool and exiftool_cmd:
        order.reverse()

    for engine, fn in order:
        r = fn(path)
        if r:
            dt, tag, raw = r
            return DateResult(dt=dt, tag=tag, engine=engine, raw=raw)

    r = _try_file_dates(path)
    if r:
        dt, tag, raw = r
        return DateResult(dt=dt, tag=tag, engine='os', raw=raw)

    return DateResult(dt=None, tag=None, engine='none')