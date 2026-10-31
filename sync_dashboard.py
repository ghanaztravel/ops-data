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


def tier_num(t, key_my, key_nonmy, legacy_key=None):
    """Read a MY/NonMY paired field, falling back to a shared legacy field
    (e.g. old 'price') for trips the dashboard hasn't migrated in-place yet."""
    my = t.get(key_my)
    nonmy = t.get(key_nonmy)
    if my is None and legacy_key is not None:
        my = t.get(legacy_key)
    if nonmy is None and legacy_key is not None:
        nonmy = t.get(legacy_key)
    return num(my), num(nonmy)


def seat_state(dep, sales):
    if dep.get("closed"):
        return "full"
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


def build_trip_deps(trip_id, deps, sales, show_left=True):
    now = today_str()
    trip_deps = []
    for d in deps:
        if d.get("tripId") != trip_id or d.get("date", "") < now:
            continue
        st = seat_state(d, sales)
        entry = {"date": d["date"], "st": st, "note": d.get("note") or ""}
        # Optional price for this specific departure (flight costs differ by
        # date). Only the selling price is ever copied — never the date's cost.
        for k in ("priceMY", "priceNonMY"):
            if num(d.get(k)) > 0:
                entry[k] = num(d.get(k))
        # Only reveal a seat count once it's scarce (low/full) — viewers see
        # "available" with no number when there's no urgency to show. The
        # public customer feed never carries the number (show_left=False): the
        # customer page only shows an "Almost full" signal, and exact seats are
        # confirmed by the freelance agent / office. The partner feed keeps it.
        if st != "open" and show_left:
            seats = num(d.get("seats"))
            sold = sold_for(d.get("id"), sales)
            entry["left"] = max(0, int(seats - sold))
        trip_deps.append(entry)
    trip_deps.sort(key=lambda x: x["date"])
    return trip_deps


def build_customer_trips(trips, deps, sales):
    out = []
    for t in trips:
        if t.get("active") is False:
            continue
        trip_deps = build_trip_deps(t["id"], deps, sales, show_left=False)
        price_my, price_nonmy = tier_num(t, "priceMY", "priceNonMY", "price")
        promo_my, promo_nonmy = tier_num(t, "promoMY", "promoNonMY", "promo")
        child_my, child_nonmy = tier_num(t, "priceChildMY", "priceChildNonMY")
        senior_my, senior_nonmy = tier_num(t, "priceSeniorMY", "priceSeniorNonMY")
        o = {
            "id": t["id"],
            "name": t["name"],
            "dir": t.get("dir", ""),
            "country": (t.get("country") or "").strip(),
            "dest": t.get("dest") or "",
            "days": t.get("days") or "",
            "priceMY": price_my,
            "priceNonMY": price_nonmy,
            "priceChildMY": child_my,
            "priceChildNonMY": child_nonmy,
            "priceSeniorMY": senior_my,
            "priceSeniorNonMY": senior_nonmy,
            "promoMY": promo_my,
            "promoNonMY": promo_nonmy,
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


def build_partner_trips(trips, deps, sales, prev_trips):
    # Commission now lives in the dashboard itself (not encrypted, a plain
    # per-trip field the agency owner fills in directly) so it syncs
    # automatically just like price, promo and photo. prev_trips is no
    # longer consulted for commission; kept as a parameter for compatibility.
    out = []
    for t in trips:
        price_my, price_nonmy = tier_num(t, "priceMY", "priceNonMY", "price")
        promo_my, promo_nonmy = tier_num(t, "promoMY", "promoNonMY", "promo")
        comm_my, comm_nonmy = tier_num(t, "commissionMY", "commissionNonMY", "commission")
        child_my, child_nonmy = tier_num(t, "priceChildMY", "priceChildNonMY")
        senior_my, senior_nonmy = tier_num(t, "priceSeniorMY", "priceSeniorNonMY")
        o = {
            "id": t["id"],
            "name": t["name"],
            "dir": t.get("dir", ""),
            "country": (t.get("country") or "").strip(),
            "dest": t.get("dest") or "",
            "days": t.get("days") or "",
            "priceMY": price_my,
            "priceNonMY": price_nonmy,
            "priceChildMY": child_my,
            "priceChildNonMY": child_nonmy,
            "priceSeniorMY": senior_my,
            "priceSeniorNonMY": senior_nonmy,
            "promoMY": promo_my,
            "promoNonMY": promo_nonmy,
            "promoUntil": t.get("promoUntil") or "",
            "material": t.get("material") or "",
            "image": t.get("image") or "",
            "commissionMY": comm_my,
            "commissionNonMY": comm_nonmy,
            "deposit": (t.get("deposit") or "").strip(),
            "active": t.get("active") is not False,
            "deps": build_trip_deps(t["id"], deps, sales),
        }
        tc = tour_code(t)
        if tc:
            o["tourCode"] = tc
        out.append(o)
    return out


INCENTIVE_ICONS = {"\U0001F381", "\U0001F4B0", "\U0001F39F️", "✈️",
                    "\U0001F3E8", "\U0001F6CD️", "\U0001F3C6"}  # gift/cash/voucher/trip/hotel/shopping/trophy


def build_incentive(inc):
    """The office's agent incentive ladder (e.g. "1 pax: RM50 bonus, 5 pax:
    RM150 bonus, 10 pax: free stay in Singapore"). Partner-portal-only —
    never sent to the customer feed. Auto-expires once its "until" date has
    passed. inc["tiers"] is a list of {pax, reward, icon}, sorted ascending
    by pax; icon falls back to the gift emoji if missing/unrecognised."""
    if not inc or not inc.get("tiers"):
        return None
    until = (inc.get("until") or "").strip()
    if until and until < today_str():
        return None
    tiers = []
    for t in inc.get("tiers") or []:
        pax = num(t.get("pax"))
        reward = (t.get("reward") or "").strip()
        icon = (t.get("icon") or "").strip()
        if icon not in INCENTIVE_ICONS:
            icon = "\U0001F381"
        if pax > 0 and reward:
            tiers.append({"pax": pax, "reward": reward, "icon": icon})
    if not tiers:
        return None
    tiers.sort(key=lambda t: t["pax"])
    return {"tiers": tiers, "until": until}


def build_featured_push(fp_list, trips):
    """Every package+date NAZ picked in the dashboard's "Push" tab (any number).
    Carried into the partner feed so agents can copy/paste each one themselves
    (the dashboard no longer sends WhatsApp messages directly). Accepts the old
    single-object shape too, for data saved before this became a list."""
    if not fp_list:
        return []
    if isinstance(fp_list, dict):
        fp_list = [fp_list]
    out = []
    for fp in fp_list:
        if not fp or not fp.get("tripId"):
            continue
        t = next((x for x in trips if x.get("id") == fp["tripId"]), None)
        if not t or t.get("active") is False:
            continue
        out.append({
            "tripId": t["id"],
            "tripName": t["name"],
            "depDate": fp.get("depDate") or "",
            "caption": fp.get("caption") or "",
            "savedAt": fp.get("savedAt") or "",
        })
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
    # The office's picked "push this date" list (from the dashboard's Push
    # tab) is used by the customer site to highlight that exact departure in
    # the top promo strip, instead of always defaulting to the soonest one.
    cust["featuredPush"] = build_featured_push(dash.get("pushFeatured"), trips)
    cust_after = json.dumps(cust, sort_keys=True)
    if cust_before != cust_after:
        changed = True
    with open(cust_path, "w") as f:
        json.dump(cust, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(part_path) as f:
        part = json.load(f)
    part_before = json.dumps(part, sort_keys=True)
    part["trips"] = build_partner_trips(trips, deps, sales, part.get("trips"))
    part["featuredPush"] = build_featured_push(dash.get("pushFeatured"), trips)
    part["incentive"] = build_incentive(dash.get("incentive"))
    part_after = json.dumps(part, sort_keys=True)
    if part_before != part_after:
        changed = True
    with open(part_path, "w") as f:
        json.dump(part, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("CHANGED" if changed else "NOCHANGE")


if __name__ == "__main__":
    main()
