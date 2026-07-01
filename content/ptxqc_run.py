from src.common.common import page_setup
from src.Workflow import Workflow

page_setup()

wf = Workflow()

wf.show_execution_section()

# Once a report exists, link to step 4 to view it.
if wf.has_report():
    import streamlit as st
    st.success("✅ Report ready. Next step:")
    try:
        st.page_link("content/ptxqc_results.py", label="**4. Report**", icon="📊")
    except Exception:  # no navigation context (e.g. single-page test run)
        pass
