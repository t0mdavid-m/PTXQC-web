import streamlit as st
from pathlib import Path
import json
# For some reason the windows version only works if this is imported here
import pyopenms

if "settings" not in st.session_state:
        with open("settings.json", "r") as f:
            st.session_state.settings = json.load(f)

if __name__ == '__main__':
    pages = {
        str(st.session_state.settings["app-name"]): [
            st.Page(Path("content", "ptxqc_upload.py"), title="1. Upload Data", icon="📁"),
            st.Page(Path("content", "ptxqc_configure.py"), title="2. Configure", icon="⚙️"),
            st.Page(Path("content", "ptxqc_run.py"), title="3. Create Report", icon="🚀"),
            st.Page(Path("content", "ptxqc_results.py"), title="4. Report", icon="📊"),
        ],
        "Info": [
            st.Page(Path("content", "help.py"), title="Help", icon="❓"),
            st.Page(Path("content", "about.py"), title="About", icon="ℹ️"),
        ],
    }

    # Hidden admin usage-log page, revealed via the ?logfile URL query
    # (parity with the original PTXQC-web app).
    if "logfile" in st.query_params:
        pages["Admin"] = [
            st.Page(Path("content", "logfile.py"), title="Logfile", icon="📦"),
        ]

    pg = st.navigation(pages)
    pg.run()
