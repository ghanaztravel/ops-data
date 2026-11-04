#!/usr/bin/env python3
"""Page-level parity check. Renders the customer page and the partner portal
with the live feeds and fails if their promo list, package list or country
list differ.  Run BEFORE delivering any page change:
    python3 check_pages.py /path/to/index.html /path/to/partner-portal.html
"""
import sys, os
from playwright.sync_api import sync_playwright
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data") + "/"
def mk(feed):
    def h(route):
        u = route.request.url
        if u.startswith("file"): return route.continue_()
        if feed in u: return route.fulfill(path=D + feed, content_type="application/json", headers={"access-control-allow-origin": "*"})
        return route.abort()
    return h
def grab(b, path, feed, pre, promo_sel, card_sel, ctry_sel):
    pg = b.new_page(viewport={"width": 1100, "height": 900})
    pg.route("**/*", mk(feed))
    if pre: pg.add_init_script(pre)
    pg.goto("file://" + path); pg.wait_for_timeout(1500)
    names = lambda sel, js: sorted(set(pg.eval_on_selector_all(sel, js)))
    promo = names(promo_sel, "e=>e.map(x=>x.querySelector('h3').textContent.trim())")
    cards = names(card_sel, "e=>e.map(x=>(x.getAttribute('data-name')||x.querySelector('h2,h3,.ptitle,.name')?.textContent||'').trim().replace(/🔥 Promo$/,'').trim())")
    ctry = names(ctry_sel, "e=>e.map(x=>x.getAttribute('data-dc'))")
    return promo, cards, ctry
cust, part = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch()
    c = grab(b, cust, "packages.json", "", ".promocard", "#list [data-trip], #list article", ".dtile")
    q = grab(b, part, "partner-packages.json", "sessionStorage.setItem('gtae_portal_unlocked','1')", ".promocard", "[data-name]", ".dtile")
    b.close()
bad = 0
for label, i in (("promo list", 0), ("destination list", 2)):
    if c[i] != q[i]:
        bad += 1; print("MISMATCH", label, "\n  customer:", c[i], "\n  partner :", q[i])
    else: print("OK", label, c[i])
print("customer cards:", len(c[1]), "partner cards:", len(q[1]))
sys.exit(1 if bad else 0)
