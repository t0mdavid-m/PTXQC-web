from src.common.common import page_setup
from src.Workflow import Workflow

page_setup()

wf = Workflow()

wf.show_parameter_section()

# Configuration is optional — always offer the link to step 3.
import streamlit as st
st.divider()
try:
    st.page_link("content/ptxqc_run.py", label="Next: **3. Create Report**", icon="🚀")
except Exception:  # no navigation context (e.g. single-page test run)
    pass
