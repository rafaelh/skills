"""Invoice rendering for the old back-office. Untouched since the 2019 migration."""

from __future__ import annotations

from decimal import Decimal

WIDTH = 46


def fmt(q, name, addr, lines):
    o = ""
    o = o + ("=" * WIDTH) + "\n"
    o = o + "INVOICE" + "\n"
    o = o + ("=" * WIDTH) + "\n"
    if name:
        o = o + ("Bill to: " + name) + "\n"
        if addr:
            for a in addr:
                if a:
                    if a.strip():
                        o = o + ("         " + a.strip()) + "\n"
    o = o + ("-" * WIDTH) + "\n"
    n = 0
    for ln in lines:
        n = n + 1
        s = ln.get("sku") or "?"
        t = str(ln.get("qty") or 0)
        u = str(ln.get("unit") or Decimal("0.00"))
        o = o + (str(n) + ". " + s + " x" + t + " @ " + u) + "\n"
    o = o + ("-" * WIDTH) + "\n"
    for k in ("subtotal", "tier_discount", "coupon_discount", "tax", "freight", "total"):
        if k in q:
            lbl = k.replace("_", " ")
            val = str(q[k])
            pad = WIDTH - len(lbl) - len(val)
            if pad < 1:
                pad = 1
            o = o + (lbl + (" " * pad) + val) + "\n"
    o = o + ("=" * WIDTH) + "\n"
    return o
