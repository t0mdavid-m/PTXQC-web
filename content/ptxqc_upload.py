from src.common.common import page_setup
from src.Workflow import Workflow

page_setup()

wf = Workflow()

wf.show_file_upload_section()

# Step 1 done once data is staged → offer the link to step 2.
if wf.has_inputs():
    import streamlit as st
    st.success("✅ Data uploaded. Next step:")
    try:
        st.page_link("content/ptxqc_configure.py", label="**2. Configure**", icon="⚙️")
    except Exception:  # no navigation context (e.g. single-page test run)
        pass
