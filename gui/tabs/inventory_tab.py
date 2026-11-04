"""Sightware GUI — Collection tab (inventory value from your own client)."""
from __future__ import annotations

import time

import tkinter as tk
from tkinter import ttk

from ..theme import (BG, CARD, LINE, TEAL, TEXT, TEXT_DIM, TEXT_FAINT, WIN, RED)
from ..widgets import (DataTable, Column, ScrollFrame, StatCard, section_title)


def _ago(ts) -> str:
    try:
        d = time.time() - int(ts)
    except (TypeError, ValueError):
        return "—"
    if d < 3600:
        return f"{max(1, round(d / 60))}m ago"
    if d < 86400:
        return f"{round(d / 3600)}h ago"
    return f"{round(d / 86400)}d ago"


class InventoryTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.core = app.core
        self._loaded_once = False

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 4))
        ttk.Button(top, text="⟳ Refresh", style="Ghost.TButton",
                   command=self.refresh).pack(side="left")
        self.updated_lbl = tk.Label(top, text="", bg=BG, fg=TEXT_FAINT,
                                    font=("Segoe UI", 8))
        self.updated_lbl.pack(side="left", padx=10)

        self.error_box = tk.Frame(self, bg=CARD, highlightbackground=LINE,
                                  highlightthickness=1, padx=14, pady=10)
        self.error_lbl = tk.Label(self.error_box, text="", bg=CARD, fg=TEXT_DIM,
                                  font=("Segoe UI", 9), justify="left",
                                  wraplength=900)
        self.error_lbl.pack(anchor="w")
        ttk.Button(self.error_box, text="Retry", style="Ghost.TButton",
                   command=self.refresh).pack(anchor="w", pady=(6, 0))

        self.cards = tk.Frame(self, bg=BG)
        self.cards.pack(fill="x", padx=16, pady=(8, 4))
        self.c_value = StatCard(self.cards, "collection value")
        self.c_usd = StatCard(self.cards, "approx. value")
        self.c_wallet = StatCard(self.cards, "wallet")
        self.c_counts = StatCard(self.cards, "owned items")
        self.c_earned = StatCard(self.cards, "earned skins")
        for c in (self.c_value, self.c_usd, self.c_wallet, self.c_counts,
                  self.c_earned):
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner

        splits = tk.Frame(body, bg=BG)
        splits.pack(fill="x", padx=16, pady=(8, 0))
        left = tk.Frame(splits, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(splits, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        section_title(left, "top skins by value").pack(anchor="w", pady=(0, 4))
        self.top_table = DataTable(left, [
            Column("name", "Skin", 220, stretch=True),
            Column("tier", "Tier", 90),
            Column("vp", "VP", 64, "e"),
        ], height=300, row_h=25)
        self.top_table.pack(fill="x")

        section_title(right, "by rarity").pack(anchor="w", pady=(0, 4))
        self.tier_table = DataTable(right, [
            Column("tier", "Tier", 120),
            Column("skins", "Skins", 60, "e"),
            Column("vp", "VP", 80, "e"),
        ], height=140, row_h=25)
        self.tier_table.pack(fill="x")

        section_title(right, "recent acquisitions").pack(anchor="w", pady=(10, 4))
        self.recent_table = DataTable(right, [
            Column("name", "Skin", 180, stretch=True),
            Column("tier", "Tier", 90),
            Column("vp", "VP", 64, "e"),
        ], height=130, row_h=25)
        self.recent_table.pack(fill="x")

        self.demo_note = tk.Label(
            body, justify="left", bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8),
            text="Demo data — your real collection is read locally from your own "
                 "VALORANT client once it is running.")
        self.demo_note.pack(anchor="w", padx=18, pady=(8, 12))

    def on_show(self) -> None:
        if not self._loaded_once:
            self.refresh()

    def refresh(self) -> None:
        def work():
            return self.core.inventory()
        self.app.run_bg(work, self._apply, self._error)

    def _error(self, err: str) -> None:
        self._show_error(f"Failed to read your collection: "
                         f"{err.splitlines()[-1]}")

    def _show_error(self, message: str) -> None:
        self.error_box.pack(fill="x", padx=16, pady=(8, 4))
        self.error_lbl.configure(text=message)
        self.cards.pack_forget()
        self.scroll.pack_forget()

    def _apply(self, data: dict) -> None:
        self._loaded_once = True
        if not data.get("available"):
            self._show_error(data.get("error") or "Collection unavailable.")
            return
        self.error_box.pack_forget()
        self.cards.pack(fill="x", padx=16, pady=(8, 4))
        self.scroll.pack(fill="both", expand=True)

        self.c_value.set(f"{data.get('totalVp', 0):,} VP", sub="priced skins owned")
        self.c_usd.set(f"~${data.get('usdApprox', 0):,}", sub="at Riot's VP pricing")
        wallet = data.get("wallet") or {}
        self.c_wallet.set(f"{wallet.get('vp', 0):,} VP",
                          sub=f"{wallet.get('rad', 0):,} Radianite · "
                              f"{wallet.get('kc', 0):,} KC")
        counts = data.get("counts") or {}
        self.c_counts.set(
            str(counts.get("skins", 0) + counts.get("earned", 0)),
            sub=f"{counts.get('buddies', '—')} buddies · {counts.get('cards', '—')} cards · "
                f"{counts.get('sprays', '—')} sprays · {counts.get('agents', '—')} agents")
        self.c_earned.set(str(counts.get("earned", 0)), sub="unpurchasable (earned)")
        self.updated_lbl.configure(
            text=("snapshot cached" if data.get("stale") else "up to date")
                 + (f" · {_ago(data.get('at'))}" if data.get("at") else ""))

        tier_rows = []
        for tier, bucket in sorted((data.get("tiers") or {}).items(),
                                   key=lambda kv: -kv[1]["vp"]):
            tier_rows.append({
                "cells": {"tier": tier.title(), "skins": str(bucket["skins"]),
                          "vp": f"{bucket['vp']:,}"},
            })
        self.tier_table.set_rows(tier_rows)

        def skin_rows(items):
            return [{
                "cells": {"name": s.get("name", "—"),
                          "tier": (s.get("tier") or "Other").title(),
                          "vp": f"{s.get('vp', 0):,}"},
            } for s in items or []]
        self.top_table.set_rows(skin_rows(data.get("top")))
        self.recent_table.set_rows(skin_rows(data.get("recent")))

        demo = bool(data.get("demo"))
        self.demo_note.pack(anchor="w", padx=18, pady=(8, 12)) if demo \
            else self.demo_note.pack_forget()
