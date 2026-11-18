"""Launch with: python -m streamlit run app.py"""
import json
from pathlib import Path

import streamlit as st

from src.lookup import BusLookup

DATA = Path(__file__).resolve().parent / "data"


@st.cache_resource
def load_snapshot():
    manifest = json.loads((DATA / "week3_manifest.json").read_text(encoding="utf-8-sig"))
    return BusLookup(DATA / "processed" / "route_stop_lookup.csv.gz"), manifest


st.title("Rapid KL Bus Route Assistant")
try:
    buses, manifest = load_snapshot()
except (OSError, ValueError, KeyError) as error:
    st.error(f"Could not read the bus snapshot: {error}")
    st.stop()

st.caption(f"Static bus schedule · Snapshot {manifest['retrieved_at_local_date']} · Prasarana via data.gov.my")
st.caption("Some trips are missing from the feed. Live arrivals and disruptions require current operator information.")
task = st.radio("What would you like to look up?", ["Routes serving a stop", "Ordered stops on a trip"])
if task == "Routes serving a stop":
    query = st.text_input("Stop name or stop ID", placeholder="STESEN BRT SETIA JAYA")
    matches = buses.find_stops(query)
    if matches:
        stop = st.selectbox("Confirm the stop", matches, index=None,
                            format_func=lambda sid: f"{buses.stops[sid]} ({sid})")
        if stop:
            for rid, short, name in sorted(buses.routes_by_stop[stop]):
                st.write(f"{short} · {name} (route ID {rid})")
    elif query.strip():
        st.info("No matching stop found in this snapshot.")
else:
    trip = st.selectbox("Search by trip ID", sorted(buses.trips), index=None)
    if trip:
        st.table([{"Sequence": seq, "Stop ID": sid, "Stop": name}
                  for seq, sid, name in buses.trip_stops(trip)])

st.caption("Source tables: routes.txt, trips.txt, stops.txt and stop_times.txt")
