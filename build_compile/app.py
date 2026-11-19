import streamlit as st
from pathlib import Path
from collections import defaultdict
import time
import hashlib
import shutil
import os
import subprocess
import sys
import tempfile
from PIL import Image 

# --- INJECTION CSS POUR TES COULEURS ET L'ERGONOMIE ---
st.markdown("""
    <style>
    /* 1. Fond du panneau principal (droite) en beige clair */
    [data-testid="stAppViewContainer"] {
        background-color: #f3f1e2 !important;
    }

    /* 2. Fond de la barre latérale (gauche) en vert très clair */
    section[data-testid="stSidebar"], 
    section[data-testid="stSidebar"] div {
        background-color: #eaf7f0 !important;
    }
    
    /* 3. Les blocs déroulants (expander) dans la sidebar */
    section[data-testid="stSidebar"] .stExpander {
        background-color: rgba(255, 255, 255, 0.4) !important; 
        border: 1px solid #d0ebd9 !important;
    }

    /* 4. Boutons en bleu clair */
    div.stButton > button {
        background-color: #d0e7ff !important;  
        color: #000000 !important;             
        border: 1px solid #a6ccff !important;
        border-radius: 5px !important;
    }
    div.stButton > button:hover {
        background-color: #b3d7ff !important;  
    }

    /* 5. Rendre le texte des cases à cocher de la sidebar rouge et gras (surtout pour la suppression) */
    section[data-testid="stSidebar"] div[data-testid="stCheckbox"] p {
        color: #d32f2f !important;
        font-weight: bold !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- CORRECTION DE L'ERREUR "DECOMPRESSION BOMB" ---
Image.MAX_IMAGE_PIXELS = None

from exif_extract import extract_date, exiftool_available, PHOTO_EXTS, VIDEO_EXTS

# --- FONCTION POUR L'EXPLORATEUR WINDOWS ---
def get_folder_via_subprocess(initial_dir):
    if not initial_dir or not os.path.isdir(initial_dir):
        initial_dir = "C:\\"
    init_dir_win = os.path.abspath(initial_dir).replace('/', '\\\\')
    
    script = f'''
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
folder_path = filedialog.askdirectory(initialdir=r"{{init_dir_win}}", title="Choisir un dossier", mustexist=True)
print(folder_path)
'''
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.py', encoding='utf-8') as f:
        f.write(script)
        temp_name = f.name

    try:
        res = subprocess.run([sys.executable, temp_name], capture_output=True, text=True)
        return res.stdout.strip()
    except Exception:
        return ""
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)

def browse_src():
    path = get_folder_via_subprocess(st.session_state.src_path)
    if path: st.session_state.src_path = path

def browse_dst():
    path = get_folder_via_subprocess(st.session_state.dst_path)
    if path: st.session_state.dst_path = path

# --- FONCTION POUR CREER UNE MINIATURE ---
def get_thumbnail(path, max_size=400):
    try:
        with Image.open(path) as img:
            img.thumbnail((max_size, max_size))
            return img.copy()
    except Exception:
        return None

# --- FONCTIONS DE CALLBACK ---
def delete_folder(folder_path, parent_path, current_month):
    try:
        all_months = [d.name for d in parent_path.iterdir() if d.is_dir()]
        all_months.sort()
        next_month = None
        if current_month in all_months:
            idx = all_months.index(current_month)
            if idx < len(all_months) - 1:
                next_month = all_months[idx + 1]
            elif idx > 0:
                next_month = all_months[idx - 1]
        shutil.rmtree(folder_path)
        if next_month:
            st.session_state.selected_month = next_month
        elif 'selected_month' in st.session_state:
            del st.session_state.selected_month
        st.toast("Dossier supprimé !")
    except Exception as e:
        st.error(f"Erreur : {e}")

def rename_folder(folder_path, new_name):
    try:
        new_path = folder_path.parent / new_name
        if new_path.exists():
            st.error("Un dossier avec ce nom existe déjà !")
        else:
            folder_path.rename(new_path)
            st.session_state.selected_month = new_name
            st.toast("Dossier renommé !")
    except Exception as e:
        st.error(f"Erreur : {e}")

def move_photos(file_list, dest_folder_name, current_dir):
    try:
        current_dir = Path(current_dir).resolve()
        
        if Path(dest_folder_name).is_absolute():
            dest = Path(dest_folder_name)
        else:
            dest = current_dir.parent / dest_folder_name
            
        if not dest.exists():
            dest.mkdir(parents=True, exist_ok=True)
            
        for p in file_list:
            shutil.move(str(p), str(dest / p.name))
            
        st.session_state.photos_selectionnees = []
        st.toast(f"{len(file_list)} fichiers déplacés dans {dest.name} !")
    except Exception as e:
        st.error(f"Erreur lors du déplacement : {e}")

def clear_photo_search():
    st.session_state.photo_search = ""

# --- CONFIGURATION DE LA PAGE ---
icon_path = "Video_photo.ico" if os.path.exists("Video_photo.ico") else "📸"
st.set_page_config(page_title="Tri Photo Jean-Mi", page_icon=icon_path, layout="wide", initial_sidebar_state="expanded")

# --- CSS DE BASE ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display:none !important;}
            [data-testid="stAppDeployButton"] {display: none !important;}
            
            html, body, [class*="css"] { font-size: 18px !important; }
            p, label, .stMarkdown { font-size: 18px !important; }
            div.stButton > button { font-size: 18px !important; font-weight: bold !important; }
            
            .block-container { padding-top: 3rem !important; padding-bottom: 0rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
            div[data-testid="stVerticalBlock"] > div { gap: 0.2rem !important; }
            h1, h2, h3 { margin-top: 0rem !important; margin-bottom: 0.1rem !important; padding: 0 !important;}
            hr { margin-top: 0.2rem !important; margin-bottom: 0.2rem !important; }
            
            .stImage { margin-bottom: 0px !important; }
            div[data-testid="stImage"] { margin-bottom: -10px; }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- INITIALISATION DE LA MÉMOIRE ---
if "src_path" not in st.session_state: st.session_state.src_path = "G:\\"
if "dst_path" not in st.session_state: st.session_state.dst_path = "D:\\Tri_Global_Photos"
if "photo_search" not in st.session_state: st.session_state.photo_search = ""

# --- BARRE LATÉRALE (Réorganisée) ---
with st.sidebar:
        # Trouver le logo, même dans le .exe
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    logo_path = os.path.join(base_dir, "logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=200)
        
    # 1. NAVIGATION EN PREMIER
    with st.expander("🗂️ Navigation", expanded=True):
        def clear_global_search():
            st.session_state.global_search_input = ""
            clear_photo_search()
            
        global_search = st.text_input("🔍 Recherche globale :", placeholder="Ex: volcan, 2022...", key="global_search_input")
        if global_search:
            st.button("❌ Effacer la recherche", on_click=clear_global_search, use_container_width=True)

        dst_dir = Path(st.session_state.dst_path)
        selected_year = None
        selected_month = None

        if dst_dir.exists() and not global_search:
            years = [d.name for d in dst_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
            years.sort(reverse=True)
            
            if years:
                if 'selected_year' not in st.session_state or st.session_state.selected_year not in years:
                    st.session_state.selected_year = years[0]
                selected_year = st.selectbox("Année :", years, key="selected_year")
                
                year_path = dst_dir / selected_year
                months = [d.name for d in year_path.iterdir() if d.is_dir()]
                months.sort()
                
                if months:
                    if 'selected_month' not in st.session_state or st.session_state.selected_month not in months:
                        st.session_state.selected_month = months[0]
                    selected_month = st.selectbox("Dossier (Mois) :", months, key="selected_month")

    # 2. OUTILS DOSSIER
    if selected_year and selected_month:
        month_path = dst_dir / selected_year / selected_month
        if month_path.exists():
            with st.expander("🛠️ Outils Dossier", expanded=False):
                st.info(f"Actuel : {selected_year} / {selected_month}")
                new_name = st.text_input("Nouveau nom :", value=selected_month, key=f"rename_input_{selected_month}")
                st.button("Renommer le dossier", on_click=rename_folder, args=(month_path, new_name), use_container_width=True)
                
                st.markdown("---")
                confirm_del = st.checkbox("⚠️ Confirmer la suppression", key=f"confirm_del_{selected_month}")
                st.button("🗑️ SUPPRIMER LE DOSSIER", type="primary", disabled=not confirm_del, on_click=delete_folder, args=(month_path, month_path.parent, selected_month), use_container_width=True)

    # 3. PARAMÈTRES DU SCAN EN DERNIER
    with st.expander("⚙️ Paramètres du scan", expanded=False):
        st.markdown("**Dossier Source :**")
        col_src1, col_src2 = st.columns([3, 1])
        with col_src1: st.text_input("Source", key="src_path", label_visibility="collapsed")
        with col_src2: st.button("📁", on_click=browse_src, use_container_width=True, key="btn_src")

        st.markdown("**Dossier Destination :**")
        col_dst1, col_dst2 = st.columns([3, 1])
        with col_dst1: st.text_input("Destination", key="dst_path", label_visibility="collapsed")
        with col_dst2: st.button("📁", on_click=browse_dst, use_container_width=True, key="btn_dst")

        include_videos = st.checkbox("Inclure les vidéos", value=True)
        keep_titles = st.checkbox("Garder les noms de dossiers", value=True)
        real_copy = st.checkbox("🚀 Mode COPIE RÉELLE", value=False)

    st.divider()
    st.markdown("<p style='color: #002060; font-weight: bold; font-size: 16px; text-align: center;'>📌 Mise à jour = F5</p>", unsafe_allow_html=True)


# --- ZONE PRINCIPALE ---
src_path = st.session_state.src_path
dst_path = st.session_state.dst_path

# --- ONGLETS ---
tab1, tab2 = st.tabs(["🚀 Trier les fichiers", "🖼️ Gérer et visualiser"])

# ==========================================
# ONGLET 1 : LE TRIEUR
# ==========================================
with tab1:
    st.title("Trieur de Photos et Vidéos")
    start_btn = st.button("Lancer le tri", type="primary")

    if start_btn:
        src = Path(src_path).resolve()
        dst = Path(dst_path).resolve()
        
        if not src.exists():
            st.error("Le dossier source n'existe pas !")
        else:
            dst.mkdir(parents=True, exist_ok=True)
            st.info(f"Recherche des fichiers dans {src}...")
            
            exts = PHOTO_EXTS | (VIDEO_EXTS if include_videos else set())
            files = []
            for p in src.rglob('*'):
                if p.is_file() and p.suffix.lower() in exts:
                    if dst in p.parents or p == dst: continue
                    files.append(p)
            
            nb_photos = sum(1 for f in files if f.suffix.lower() in PHOTO_EXTS)
            nb_videos = sum(1 for f in files if f.suffix.lower() in VIDEO_EXTS)
            st.success(f"Trouvé : **{len(files)} fichiers** (soit {nb_photos} photos et {nb_videos} vidéos).")
            
            if len(files) > 0:
                progress_bar = st.progress(0)
                status_text = st.empty()
                preview_area = st.empty()
                et_ok = exiftool_available()
                stats = defaultdict(int)
                previews = []
                seen_hashes = set()
                start_time = time.time()
                
                for i, p in enumerate(files, 1):
                    try:
                        r = extract_date(p, _exiftool_ok=et_ok)
                        if r.dt:
                            year_str = f"{r.dt.year:04d}"
                            month_str = f"{r.dt.month:02d}"
                        else:
                            year_str = "_sans_exif"
                            month_str = ""
                            
                        title = None
                        if keep_titles:
                            parent = p.parent
                            if parent != src:
                                name = parent.name.strip()
                                if not (name.lower() in {'dcim', 'photos', 'pictures', 'camera', 'images', 'img', '100apple', 'whatsapp', 'thumbnails'} or name.isdigit() or len(name) < 4):
                                    title = name
                        
                        if title and r.dt:
                            target_dir = dst / year_str / f"{month_str}_{title}"
                        elif r.dt:
                            target_dir = dst / year_str / month_str
                        else:
                            target_dir = dst / year_str
                            
                        rel_path = target_dir.relative_to(dst)
                        
                        is_duplicate = False
                        if real_copy:
                            hasher = hashlib.sha256()
                            with open(p, 'rb') as f:
                                while chunk := f.read(8192): hasher.update(chunk)
                            file_hash = hasher.hexdigest()
                            if file_hash in seen_hashes:
                                stats["_doublons_ignores"] += 1
                                is_duplicate = True
                            else:
                                seen_hashes.add(file_hash)
                        
                        if not is_duplicate:
                            stats[str(rel_path)] += 1
                            if len(previews) < 5:
                                previews.append(f"`{p.name}` ➡️ `{rel_path}`")
                                preview_area.markdown("**Aperçu :**\n" + "\n".join(previews))
                            
                            if real_copy:
                                target_dir.mkdir(parents=True, exist_ok=True)
                                target_file = target_dir / p.name
                                counter = 1
                                while target_file.exists():
                                    target_file = target_dir / f"{p.stem}_{counter}{p.suffix}"
                                    counter += 1
                                shutil.copy2(p, target_file)
                    except Exception as e:
                        stats["_erreurs"] += 1
                    
                    if i % 100 == 0 or i == len(files):
                        progress = i / len(files)
                        progress_bar.progress(progress)
                        elapsed = time.time() - start_time
                        rate = i / elapsed if elapsed else 0
                        status_text.text(f"Analyse : {i} / {len(files)} ({int(progress*100)}%) - {rate:.1f} fichiers/sec")
                        
                status_text.text("✅ Scan terminé !")
                st.balloons()
                st.subheader("📊 Résumé du tri")
                col1, col2 = st.columns(2)
                with col1:
                    for folder in sorted(stats.keys()):
                        if not folder.startswith('_'):
                            st.write(f"- {folder} : {stats[folder]} fichiers")
                with col2:
                    if stats["_doublons_ignores"] > 0: st.write(f"- 🗑️ Doublons ignorés : {stats['_doublons_ignores']}")
                    if stats["_erreurs"] > 0: st.write(f"- ⚠️ Erreurs : {stats['_erreurs']}")


# ==========================================
# ONGLET 2 : GESTION ET VISUALISATION
# ==========================================
with tab2:
    # --- RESULTATS DE LA RECHERCHE GLOBALE ---
    if global_search:
        matches = []
        for y_dir in dst_dir.iterdir():
            if y_dir.is_dir() and not y_dir.name.startswith('_'):
                for m_dir in y_dir.iterdir():
                    if m_dir.is_dir():
                        if global_search.lower() in m_dir.name.lower() or global_search.lower() in y_dir.name:
                            matches.append((y_dir.name, m_dir.name))
        matches.sort(reverse=True)
        
        if matches:
            options = [f"{y} / {m}" for y, m in matches]
            
            col_search1, col_search2 = st.columns([4, 1])
            with col_search1:
                chosen = st.selectbox("Résultats de la recherche :", options, key="global_result_select")
            with col_search2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📂 Ouvrir ce dossier", use_container_width=True):
                    clear_photo_search()
                    st.rerun()

            selected_year, selected_month = chosen.split(" / ", 1)
        else:
            st.warning("Aucun dossier trouvé avec ce nom.")

    # --- AFFICHAGE DU DOSSIER SELECTIONNE ---
    if selected_year and selected_month:
        month_path = dst_dir / selected_year / selected_month
        
        if 'current_folder' not in st.session_state or st.session_state.current_folder != str(month_path.resolve()):
            st.session_state.current_page = 0
            st.session_state.current_folder = str(month_path.resolve())
            st.session_state.photos_selectionnees = []
            st.session_state.zoom_img = None
        
        col_titre, col_rech_photo = st.columns([1, 2])
        with col_titre:
            st.markdown(f"### 📂 {selected_month}")
        with col_rech_photo:
            search_query = st.text_input("Rechercher un fichier :", placeholder="Taper le nom...", label_visibility="collapsed", key="photo_search")

        # --- AFFICHAGE EN GRAND (PHOTO OU VIDEO) ---
        if 'zoom_img' in st.session_state and st.session_state.zoom_img:
            col_zoom1, col_zoom2 = st.columns([4, 1])
            
            is_video = Path(st.session_state.zoom_img).suffix.lower() in VIDEO_EXTS
            
            with col_zoom1: 
                st.info(f"Affichage en grand : {Path(st.session_state.zoom_img).name}")
            with col_zoom2:
                if st.button("❌ Fermer l'aperçu", use_container_width=True):
                    st.session_state.zoom_img = None
                    st.rerun()
            
            if is_video:
                st.video(st.session_state.zoom_img)
            else:
                zoom_img = get_thumbnail(st.session_state.zoom_img, max_size=2000)
                if zoom_img:
                    st.image(zoom_img, width=1200)
                else:
                    st.error("Impossible d'afficher cette image (format non supporté ou corrompue).")
                
            st.divider()

        # --- RECHERCHE DE FICHIERS (PHOTOS + VIDEOS) ---
        all_media_files = [f for f in month_path.iterdir() if f.suffix.lower() in (PHOTO_EXTS | VIDEO_EXTS)]
        if search_query: 
            all_media_files = [f for f in all_media_files if search_query.lower() in f.name.lower()]
        
        all_media_files.sort(key=lambda x: x.name)
        
        if all_media_files:
            photos_par_page = 3 
            total_pages = (len(all_media_files) + photos_par_page - 1) // photos_par_page
            if st.session_state.current_page >= total_pages: st.session_state.current_page = 0

            if 'photos_selectionnees' not in st.session_state: st.session_state.photos_selectionnees = []

            col_pag1, col_pag2, col_pag3, col_pag4, col_pag5 = st.columns([1, 1.5, 3, 1.5, 1])

            with col_pag1:
                if st.button("⬅️ Précédent") and st.session_state.current_page > 0:
                    st.session_state.current_page -= 1
                    st.rerun()
            
            with col_pag2:
                st.markdown(f"<div style='text-align: right; padding-top: 5px; font-size: 18px;'><b>Page {st.session_state.current_page + 1}/{total_pages}</b></div>", unsafe_allow_html=True)

            with col_pag3:
                if st.session_state.photos_selectionnees:
                    st.warning(f"⚠️ {len(st.session_state.photos_selectionnees)} fichier(s) sélectionné(s)")
                    
                    col_act1, col_act2 = st.columns(2)
                    
                    with col_act1:
                        if st.button("🗑️ SUPPRIMER", type="primary", use_container_width=True):
                            for p in st.session_state.photos_selectionnees:
                                try: os.remove(p)
                                except Exception as e: st.error(f"Erreur {p.name} : {e}")
                            st.session_state.photos_selectionnees = []
                            st.rerun()
                    
                    with col_act2:
                        st.markdown("**Dossier de destination :**")
                        all_existing_folders = [d.name for d in month_path.parent.iterdir() if d.is_dir()]
                        all_existing_folders.sort()
                        
                        options = ["-- Choisir un dossier existant --"] + all_existing_folders
                        selected_dest = st.selectbox("Dossier existant :", options, key="select_dest_folder", label_visibility="collapsed")
                        
                        new_dest_name = st.text_input("Ou créer un nouveau dossier (taper le nom ici) :", key="new_dest_name")
                        
                        final_dest = ""
                        if new_dest_name.strip():
                            final_dest = new_dest_name.strip()
                        elif selected_dest != "-- Choisir un dossier existant --":
                            final_dest = selected_dest

                        if final_dest:
                            if st.button(f"🚀 DÉPLACER VERS : {final_dest}", use_container_width=True):
                                move_photos(st.session_state.photos_selectionnees, final_dest, month_path)
                                st.rerun()

                else:
                    num_photos = len([f for f in all_media_files if f.suffix.lower() in PHOTO_EXTS])
                    num_videos = len([f for f in all_media_files if f.suffix.lower() in VIDEO_EXTS])
                    
                    texte_photos = f"{num_photos} Photos" if num_photos > 0 else ""
                    texte_videos = f"{num_videos} Vidéos" if num_videos > 0 else ""
                    separateur = " et " if num_photos > 0 and num_videos > 0 else ""
                    
                    st.markdown(f"<div style='text-align: center; font-size: 26px; font-weight: 900; color: #d32f2f;'>{texte_photos}{separateur}{texte_videos}</div>", unsafe_allow_html=True)

            with col_pag5:
                if st.button("Suivant ➡️") and st.session_state.current_page < total_pages - 1:
                    st.session_state.current_page += 1
                    st.rerun()
            st.markdown("---")

            debut = st.session_state.current_page * photos_par_page
            fin = min(debut + photos_par_page, len(all_media_files))
            media_page = all_media_files[debut:fin]

            col_img1, col_img2, col_img3 = st.columns(3)
            cols = [col_img1, col_img2, col_img3]
            
            for index, media_path in enumerate(media_page):
                with cols[index % 3]:
                    
                    is_video = media_path.suffix.lower() in VIDEO_EXTS

                    if is_video:
                        st.markdown("<h1 style='text-align: center; font-size: 80px; margin: 0;'>🎥</h1>", unsafe_allow_html=True)
                        st.markdown(f"<p style='text-align: center; font-weight: bold;'>{media_path.name}</p>", unsafe_allow_html=True)
                    else:
                        thumb = get_thumbnail(media_path)
                        if thumb:
                            st.image(thumb, caption=media_path.name, width=300)
                        else:
                            st.warning(f"Image illisible : {media_path.name}")
                    
                    col_action1, col_action2 = st.columns(2)
                    with col_action1:
                        label_bouton = "▶️ Lire" if is_video else "🔍 Agrandir"
                        if st.button(label_bouton, key=f"zoom_{media_path.name}", use_container_width=True):
                            st.session_state.zoom_img = str(media_path)
                            st.rerun()
                    with col_action2:
                        is_checked = st.checkbox(
                            "Sélectionner", 
                            key=f"sel_{media_path.name}",
                            value=media_path in st.session_state.photos_selectionnees
                        )
                    
                    if is_checked and media_path not in st.session_state.photos_selectionnees:
                        st.session_state.photos_selectionnees.append(media_path)
                    elif not is_checked and media_path in st.session_state.photos_selectionnees:
                        st.session_state.photos_selectionnees.remove(media_path)
                        
        else:
            if not search_query: st.info("Ce dossier ne contient pas de photos ni de vidéos.")
            else: st.info("Aucun fichier trouvé avec ce nom.")