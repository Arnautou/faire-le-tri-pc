import streamlit.runtime.scriptrunner.magic_funcs
import streamlit.web.cli as stcli
import os, sys, webbrowser, time, threading

def resolve_path(path):
    if getattr(sys, "frozen", False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(__file__)
    return os.path.join(basedir, path)

def open_browser():
    # On attend 3 secondes que le serveur démarre, puis on ouvre le navigateur
    time.sleep(3)
    webbrowser.open("http://localhost:8501")

if __name__ == "__main__":
    # On lance l'ouverture du navigateur en arrière-plan
    threading.Thread(target=open_browser, daemon=True).start()

    sys.argv = [
        "streamlit",
        "run",
        resolve_path("app.py"),
        "--global.developmentMode=false",
        # J'ai supprimé "--server.headless=true"
    ]
    sys.exit(stcli.main())