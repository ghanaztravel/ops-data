#!/usr/bin/env python3
"""
Sync GHANAZ Travel's dashboard data into the public data files this repo serves
(data/packages.json for the customer page, data/partner-packages.json for the
partner portal).

Usage:
    python3 sync_dashboard.py dashboard_data.json

dashboard_data.json is the raw JSON from the dashboard artifact's
<script type="application/json" id="data"> tag (the "pub" / public copy — it
must NOT contain b2b/cost/dta fields; those stay encrypted in the dashboard's
vault and are never touched by this script).

Prints "CHANGED" if either output file's content changed, else "NOCHANGE".
Exits non-zero on error.
"""
import json
import sys
import os
from datetime import datetime, timezone, timedelta

MY_TZ = timezone(timedelta(hours=8))  # Asia/Kuala_Lumpur


def today_str():
    return datetime.now(MY_TZ).strftime("%Y-%m-%d")


def num(v):
    try:
        n = float(v) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0
    return int(n) if n == int(n) else n


def sold_for(dep_id, sales, skip_id=None):
    total = 0
    for s in sales:
        if s.get("cancel"):
            continue
        if s.get("depId") != dep_id:
            continue
        if skip_id and s.get("id") == skip_id:
            continue
        total += num(s.get("pax"))
    return total


def seat_state(dep, sales):
    seats = num(dep.get("seats"))
    sold = sold_for(dep.get("id"), sales)
    left = seats - sold
    low_threshold = max(3, -(-seats * 0.2 // 1))  # ceil(seats*0.2)
    if left <= 0:
        return "full"
    if left <= low_threshold:
        return "low"
    return "open"


def tour_code(t):
    return (t.get("tourCode") or "").strip()


def build_customer_trips(trips, deps, sales):
    now = today_str()
    out = []
    for t in trips:
        if t.get("active") is False:
            continue
        trip_deps = [
            {"date": d["date"], "st": seat_state(d, sales), "note": d.get("note") or ""}
            for d in deps
            if d.get("tripId") == t["id"] and d.get("date", "") >= now
        ]
        o = {
            "id": t["id"],
            "name": t["name"],
            "dir": t.get("dir", ""),
            "dest": t.get("dest") or "",
            "days": t.get("days") or "",
            "price": num(t.get("price")),
            "promo": num(t.get("promo")) or 0,
            "promoUntil": t.get("promoUntil") or "",
            "material": t.get("material") or "",
            "image": t.get("image") or "",
            "itin": t.get("itin") or [],
            "inc": t.get("inc") or [],
            "exc": t.get("exc") or [],
            "deps": trip_deps,
        }
        tc = tour_code(t)
        if tc:
            o["tourCode"] = tc
        out.append(o)
    return out


def build_partner_trips(trips, prev_trips):
    prev_by_id = {p["id"]: p for p in (prev_trips or [])}
    out = []
    for t in trips:
        prev = prev_by_id.get(t["id"], {})
        o = {
            "id": t["id"],
            "name": t["name"],
            "dir": t.get("dir", ""),
            "dest": t.get("dest") or "",
            "days": t.get("days") or "",
            "price": num(t.get("price")),
            "promo": num(t.get("promo")) or 0,
            "promoUntil": t.get("promoUntil") or "",
            "material": t.get("material") or "",
            "image": t.get("image") or "",
            "commission": num(prev.get("commission")) or 0,
            "active": t.get("active") is not False,
        }
        tc = tour_code(t)
        if tc:
            o["tourCode"] = tc
        out.append(o)
    return out


def main():
    if len(sys.argv) != 2:
        print("usage: sync_dashboard.py <dashboard_data.json>", file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1]) as f:
        dash = json.load(f)

    trips = dash.get("trips", [])
    deps = dash.get("deps", [])
    sales = dash.get("sales", [])

    repo_dir = os.path.dirname(os.path.abspath(__file__))
    cust_path = os.path.join(repo_dir, "data", "packages.json")
    part_path = os.path.join(repo_dir, "data", "partner-packages.json")

    changed = False

    with open(cust_path) as f:
        cust = json.load(f)
    cust_before = json.dumps(cust, sort_keys=True)
    cust.setdefault("config", {})
    cust["config"]["asOf"] = today_str()
    cust["trips"] = build_customer_trips(trips, deps, sales)
    cust_after = json.dumps(cust, sort_keys=True)
    if cust_before != cust_after:
        changed = True
    with open(cust_path, "w") as f:
        json.dump(cust, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(part_path) as f:
        part = json.load(f)
    part_before = json.dumps(part, sort_keys=True)
    part["trips"] = build_partner_trips(trips, part.get("trips"))
    part_after = json.dumps(part, sort_keys=True)
    if part_before != part_after:
        changed = True
    with open(part_path, "w") as f:
        json.dump(part, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("CHANGED" if changed else "NOCHANGE")


if __name__ == "__main__":
    main()
