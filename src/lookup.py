"""Read the prepared bus snapshot and look up stops, routes and trips."""
import csv
import gzip
from collections import defaultdict
from pathlib import Path


class BusLookup:
    def __init__(self, path: Path):
        self.stops = {}
        self.routes_by_stop = defaultdict(set)
        self.trips = defaultdict(list)
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                stop_id = row["stop_id"]
                self.stops[stop_id] = row["stop_name"]
                route = (row["route_id"], row["route_short_name"], row["route_long_name"])
                self.routes_by_stop[stop_id].add(route)
                self.trips[row["trip_id"]].append(
                    (int(row["stop_sequence"]), stop_id, row["stop_name"])
                )

    def find_stops(self, query):
        term = " ".join(query.casefold().split())
        if not term:
            return []
        if query.strip() in self.stops:
            return [query.strip()]
        return sorted(
            (sid for sid, name in self.stops.items()
             if term in " ".join(name.casefold().split())),
            key=lambda sid: (self.stops[sid], sid),
        )

    def trip_stops(self, trip_id):
        return sorted(self.trips.get(trip_id, ()))
