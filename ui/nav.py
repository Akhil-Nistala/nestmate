"""Registry of the pages available in the current run, so pages can link to each
other (st.switch_page needs the Page object). Filled by app.py every run."""
PAGES = {}


def go(name):
    import streamlit as st
    st.switch_page(PAGES[name])
