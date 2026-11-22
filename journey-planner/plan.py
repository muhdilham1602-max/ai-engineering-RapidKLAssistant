"""Find an earliest estimated arrival using the archived Rapid KL GTFS feeds."""

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile


DAY = 86400
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PROJECT = Path(__file__).resolve().parent
REPO_DATA = PROJECT.parent / "data" / "raw"
DATA = REPO_DATA if REPO_DATA.is_dir() else PROJECT / "data"


def seconds(value):
    hour, minute, second = map(int, value.split(":"))
    if hour < 0 or not (0 <= minute < 60 and 0 <= second < 60):
        raise ValueError(f"Invalid time: {value}")
    return hour * 3600 + minute * 60 + second


@dataclass(frozen=True)
class Ride:
    route: str
    trip: str
    board: str
    alight: str
    departure: int
    arrival: int
    estimated: bool


@dataclass(frozen=True)
class Walk:
    start: str
    end: str
    duration: int


def load_feed(path, prefix, travel_date):
    with ZipFile(path) as archive:
        def rows(name):
            if name not in archive.namelist():
                return []
            return list(csv.DictReader(archive.read(name).decode("utf-8-sig").splitlines()))

        stops = {f"{prefix}:{r['stop_id']}": r["stop_name"] for r in rows("stops.txt")}
        routes = {r["route_id"]: r["route_short_name"] or r["route_long_name"]
                  for r in rows("routes.txt")}
        trips = rows("trips.txt")
        calendars = rows("calendar.txt")
        exceptions = rows("calendar_dates.txt")
        stop_times = defaultdict(list)
        for r in rows("stop_times.txt"):
            stop_times[r["trip_id"]].append((
                int(r["stop_sequence"]), f"{prefix}:{r['stop_id']}",
                seconds(r["arrival_time"]), seconds(r["departure_time"]),
                r.get("pickup_type") != "1", r.get("drop_off_type") != "1",
            ))
        frequencies = defaultdict(list)
        for r in rows("frequencies.txt"):
            headway = int(r["headway_secs"])
            end, start = seconds(r["end_time"]), seconds(r["start_time"])
            if headway <= 0 or end <= start:
                raise ValueError(f"Invalid frequency window for {r['trip_id']}")
            frequencies[r["trip_id"]].append((start, end, headway, r.get("exact_times") != "1"))

    for times in stop_times.values():
        times.sort()
    patterns = []
    for offset in (-1, 0, 1):
        day = travel_date + timedelta(days=offset)
        ymd = day.strftime("%Y%m%d")
        active = {r["service_id"] for r in calendars
                  if r["start_date"] <= ymd <= r["end_date"] and r[DAYS[day.weekday()]] == "1"}
        for r in exceptions:
            if r["date"] == ymd:
                if r["exception_type"] == "1":
                    active.add(r["service_id"])
                else:
                    active.discard(r["service_id"])
        for trip in trips:
            trip_id = trip["trip_id"]
            times = stop_times.get(trip_id)
            if trip["service_id"] in active and times:
                route = routes[trip["route_id"]]
                windows = frequencies.get(trip_id, [(times[0][3], times[0][3] + 1, 1, False)])
                patterns.append((route, f"{prefix}:{trip_id}", times, windows, offset * DAY))
    return stops, patterns


def plan(patterns, links, start, end, departure, max_rides, buffer):
    """Scan each trip pattern once per boarding round. Earlier arrivals dominate."""
    best = {start: (departure, ())}
    frontier = best.copy()
    deadline = departure + DAY
    for _ in range(max_rides):
        ready = {stop: (when + (buffer if path else 0), path)
                 for stop, (when, path) in frontier.items()}
        for stop, (when, path) in frontier.items():
            if not path:
                continue
            for link in links.get(stop, ()):
                arrival = when + max(buffer, link.duration)
                if link.end not in ready or arrival < ready[link.end][0]:
                    ready[link.end] = (arrival, path + (link,))
        following = {}
        for route, trip, times, windows, offset in patterns:
            first_departure = times[0][3]
            for first, end_window, headway, estimated in windows:
                boarded = None
                for _, stop, arr, dep, pickup, dropoff in times:
                    if boarded and dropoff:
                        shift, board, board_time, path = boarded
                        arrival = arr + shift
                        known = following.get(stop, best.get(stop, (deadline + 1, ())))
                        if arrival <= deadline and arrival < known[0]:
                            ride = Ride(route, trip, board, stop, board_time, arrival, estimated)
                            following[stop] = (arrival, path + (ride,))
                    if pickup and stop in ready:
                        when, path = ready[stop]
                        relative = dep - first_departure
                        wait = when - (first + offset + relative)
                        index = max(0, (wait + headway - 1) // headway)
                        run = first + index * headway
                        shift = run + offset - first_departure
                        if run < end_window and (not boarded or shift < boarded[0]):
                            boarded = (shift, stop, dep + shift, path)
        if not following:
            break
        best.update(following)
        frontier = following
    return best.get(end)


def read_links(path, stops):
    links = defaultdict(list)
    if path:
        with path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                a, b = row["from_stop_id"], row["to_stop_id"]
                duration = int(row["walk_seconds"])
                if a not in stops or b not in stops or a == b or duration <= 0 or not row["evidence"].strip():
                    raise ValueError(f"Invalid transfer entry: {row}")
                links[a].append(Walk(a, b, duration))
    return links


def resolve(query, stops, label):
    if query in stops:
        return query
    normal = query.strip().casefold()
    if not normal:
        raise ValueError(f"Enter a {label} stop name or ID.")
    exact = [key for key, name in stops.items() if name.casefold() == normal]
    matches = exact or [key for key, name in stops.items() if normal in name.casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"No {label} stop found for {query!r}. Try part of its name.")
    options = "\n".join(f"  {key:<15} {stops[key]}" for key in matches[:25])
    raise ValueError(f"Multiple {label} stops match {query!r}. Use a stop ID:\n{options}")


def display_time(day, value):
    return (datetime.combine(day, datetime.min.time()) + timedelta(seconds=value)).strftime("%d %b %H:%M:%S")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", nargs="?", help="Stop name or bus:/rail: stop ID")
    parser.add_argument("destination", nargs="?", help="Stop name or bus:/rail: stop ID")
    parser.add_argument("date", nargs="?", type=date.fromisoformat, help="Travel date in YYYY-MM-DD")
    parser.add_argument("time", nargs="?", help="Local departure time in HH:MM")
    parser.add_argument("--max-rides", type=int, choices=range(1, 7), default=4)
    parser.add_argument("--transfers", type=Path, help="CSV of manually verified walking links")
    args = parser.parse_args()
    try:
        interactive = not any((args.origin, args.destination, args.date, args.time))
        if interactive:
            args.date = date.fromisoformat(input("Travel date (YYYY-MM-DD): ").strip())
            args.time = input("Depart after (HH:MM, Kuala Lumpur time): ").strip()
        elif not all((args.origin, args.destination, args.date, args.time)):
            parser.error("Supply all four trip inputs, or run without arguments for interactive mode.")
        departure = seconds(args.time + ":00")
        if departure >= DAY:
            raise ValueError("Enter a departure time between 00:00 and 23:59.")
        bus, bus_patterns = load_feed(DATA / "rapid-bus-kl-gtfs.zip", "bus", args.date)
        rail, rail_patterns = load_feed(DATA / "rapid-rail-kl-gtfs.zip", "rail", args.date)
        stops = bus | rail
        def choose(query, label):
            if not interactive:
                return resolve(query, stops, label)
            while True:
                try:
                    return resolve(input(f"{label.title()} stop name or ID: "), stops, label)
                except ValueError as error:
                    print(error)

        start = choose(args.origin, "origin")
        end = choose(args.destination, "destination")
        links = read_links(args.transfers, stops)
    except (OSError, KeyError, ValueError, EOFError) as error:
        parser.exit(2, f"{error}\n")
    if start == end:
        print(f"Already at {stops[start]} ({start}).")
        return
    result = plan(bus_patterns + rail_patterns, links, start, end, departure, args.max_rides, 180)
    print("Archived GTFS snapshot: 18 November 2026. Times are local to Kuala Lumpur.")
    if not result:
        print(f"No itinerary found within 24 hours and {args.max_rides} rides using available records and connections.")
        return
    arrival, legs = result
    print(f"{stops[start]} to {stops[end]}")
    for index, leg in enumerate(legs, 1):
        if isinstance(leg, Walk):
            print(f"{index}. Walk {leg.duration / 60:g} min from {stops[leg.start]} to {stops[leg.end]}")
            continue
        timing = "estimated from headway" if leg.estimated else "scheduled"
        print(f"{index}. {leg.route} ({timing}) [{leg.trip}]")
        print(f"   Board {display_time(args.date, leg.departure)} at {stops[leg.board]} ({leg.board})")
        print(f"   Alight {display_time(args.date, leg.arrival)} at {stops[leg.alight]} ({leg.alight})")
    timing = "Estimated arrival" if any(isinstance(x, Ride) and x.estimated for x in legs) else "Scheduled arrival"
    print(f"{timing}: {display_time(args.date, arrival)}")


if __name__ == "__main__":
    main()
