import streamlit.web.cli as stcli
import os, sys, time, threading, urllib.request, urllib.error

import webview


def resolve_path(path):
    if getattr(sys, "frozen", False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(__file__)
    return os.path.join(basedir, path)


def wait_for_server(url, timeout=30):
    """Attend que le serveur Streamlit réponde sur l'URL donnée."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_streamlit():
    """Lance Streamlit en mode headless (aucun navigateur ouvert)."""
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("app.py"),
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.port=8501",
    ]
    stcli.main()


if __name__ == "__main__":
    # 1. Lance Streamlit en arrière-plan (headless, sans navigateur)
    t = threading.Thread(target=run_streamlit, daemon=True)
    t.start()

    # 2. Attend que le serveur soit prêt avant d'ouvrir la fenêtre
    if not wait_for_server("http://localhost:8501", timeout=30):
        print("ERREUR : le serveur Streamlit n'a pas démarré dans le temps imparti.")
        sys.exit(1)

    # 3. Ouvre une vraie fenêtre Windows autonome avec pywebview (pas Chrome)
    # L'icône de l'exécutable est déjà définie via le .spec (icon=['Video_photo.ico'])
    window = webview.create_window(
        title="Mon Trieur de Photos",
        url="http://localhost:8501",
        width=1200,
        height=800,
        resizable=True,
    )
    webview.start()