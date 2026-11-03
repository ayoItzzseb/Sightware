"""Valtix GUI — Display tab (ChromaDesk integrated).

ChromaDesk's display workspace inside Valtix: per-display resolution modes
with favorites and Windows' own 15-second revert, NVIDIA Digital Vibrance,
whole-desktop saturation (Magnification API), and manual display profiles.
Engine: backend.display_engine (Windows display APIs + NVAPI only — never
touches game processes).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import display_engine as deng
from ..theme import (AMBER, BG, BG_RAISED, CARD, CARD_HI, LINE, RED, RED_SOFT,
                   TEAL, TEAL_DIM, TEXT, TEXT_DIM, TEXT_FAINT)
from ..widgets import ScrollFrame, Switch, ValtixSlider, card, section_title

REVERT_SECONDS = 15


class DisplayTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._favorites = self._load_favorites()
        self._pending_mode = None          # (mode, device, deadline_job) while revert counts down
        self._dvc = None
        self._dvc_error = None
        self._sat = None
        self._sat_error = None

        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner

        top = tk.Frame(body, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 2))
        section_title(top, "chromadesk display workspace").pack(side="left")
        hint = tk.Label(top, text="Windows display APIs + NVIDIA driver only — never touches game processes.",
                        bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8))
        hint.pack(side="right")

        self._build_overview(body)
        self._build_resolution(body)
        self._build_vibrance(body)
        self._build_saturation(body)
        self._build_profiles(body)

        self.refresh_all()

    # ── overview ───────────────────────────────────────────────
    def _build_overview(self, parent):
        c = card(parent)
        c.pack(fill="x", padx=16, pady=(8, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=14, pady=12)

        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="Display", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        self.device_cb = ttk.Combobox(row, state="readonly", width=42)
        self.device_cb.pack(side="left")
        self.device_cb.bind("<<ComboboxSelected>>", self._on_device_selected)
        ttk.Button(row, text="⟳ Refresh", style="Ghost.TButton",
                   command=self.refresh_all).pack(side="left", padx=8)
        ttk.Button(row, text="Restore everything", style="Danger.TButton",
                   command=self._restore_all).pack(side="right")

        self.chips = tk.Frame(f, bg=CARD)
        self.chips.pack(fill="x", pady=(10, 0))
        self.mode_chip = self._chip(self.chips, "—")
        self.gpu_chip = self._chip(self.chips, "NVIDIA: —")
        self.sat_chip = self._chip(self.chips, "Saturation: —")

    def _chip(self, parent, text):
        lbl = tk.Label(parent, text=text, bg=BG_RAISED, fg=TEXT_DIM,
                       font=("Consolas", 8, "bold"), padx=10, pady=4)
        lbl.pack(side="left", padx=(0, 6))
        return lbl

    # ── resolution modes ───────────────────────────────────────
    def _build_resolution(self, parent):
        section_title(parent, "resolution modes").pack(anchor="w", padx=16, pady=(8, 3))
        c = card(parent)
        c.pack(fill="x", padx=16, pady=(0, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=14, pady=12)

        bar = tk.Frame(f, bg=CARD)
        bar.pack(fill="x")
        self.mode_search = tk.StringVar()
        ent = tk.Entry(bar, textvariable=self.mode_search, width=26, bd=0,
                       bg=BG_RAISED, fg=TEXT, insertbackground=RED,
                       highlightthickness=1, highlightbackground=LINE,
                       highlightcolor=RED)
        ent.pack(side="left", ipady=5)
        ent.bind("<KeyRelease>", lambda e: self._fill_modes())
        ttk.Button(bar, text="★ Favorite", style="Ghost.TButton",
                   command=self._toggle_favorite).pack(side="left", padx=6)
        ttk.Button(bar, text="Apply", style="Accent.TButton",
                   command=self._apply_mode).pack(side="right")
        ttk.Button(bar, text="Restore original", style="Ghost.TButton",
                   command=self._restore_mode).pack(side="right", padx=4)

        self.mode_box = tk.Listbox(f, bg=BG_RAISED, fg=TEXT, height=8, bd=0,
                                   highlightthickness=1, highlightbackground=LINE,
                                   highlightcolor=RED, selectbackground=RED,
                                   selectforeground="#FFFFFF", activestyle="none",
                                   font=("Consolas", 9))
        self.mode_box.pack(fill="x", pady=(8, 0))
        self.mode_box.bind("<Double-Button-1>", lambda e: self._apply_mode())

        self.mode_status = tk.Label(f, text="", bg=CARD, fg=TEXT_DIM,
                                    font=("Segoe UI", 9))
        self.mode_status.pack(side="left", anchor="w", pady=(6, 0))
        self.keep_btn = ttk.Button(f, text="Keep this mode", style="Success.TButton",
                                   command=self._cancel_revert, state="disabled")
        self.keep_btn.pack(side="right", anchor="e", pady=(6, 0))

    # ── NVIDIA vibrance ────────────────────────────────────────
    def _build_vibrance(self, parent):
        section_title(parent, "nvidia digital vibrance").pack(anchor="w", padx=16, pady=(8, 3))
        c = card(parent)
        c.pack(fill="x", padx=16, pady=(0, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=14, pady=12)

        self.dvc_value = tk.Label(f, text="—", bg=CARD, fg=TEXT,
                                  font=("Consolas", 16, "bold"))
        self.dvc_value.pack(side="right")
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x")
        self.dvc_scale = ValtixSlider(row, from_=0, to=100, value=0, resolution=1,
                                      length=380, bg=CARD, state="disabled",
                                      command=lambda v: self._defer("_apply_vibrance"))
        self.dvc_scale.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=8)
        btns = tk.Frame(f, bg=CARD)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Restore original", style="Ghost.TButton",
                   command=self._restore_vibrance).pack(side="left")
        self.dvc_status = tk.Label(btns, text="", bg=CARD, fg=TEXT_FAINT,
                                   font=("Segoe UI", 8))
        self.dvc_status.pack(side="left", padx=10)

    # ── desktop saturation ─────────────────────────────────────
    def _build_saturation(self, parent):
        section_title(parent, "desktop saturation (magnification api)").pack(
            anchor="w", padx=16, pady=(8, 3))
        c = card(parent)
        c.pack(fill="x", padx=16, pady=(0, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=14, pady=12)

        self.sat_value = tk.Label(f, text="—", bg=CARD, fg=TEXT,
                                  font=("Consolas", 16, "bold"))
        self.sat_value.pack(side="right")
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x")
        self.sat_scale = ValtixSlider(row, from_=0, to=300, value=100, resolution=5,
                                      length=380, bg=CARD, state="disabled",
                                      command=lambda v: self._defer("_apply_saturation"))
        self.sat_scale.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=8)
        btns = tk.Frame(f, bg=CARD)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Restore neutral", style="Ghost.TButton",
                   command=self._restore_saturation).pack(side="left")
        self.sat_status = tk.Label(btns, text="", bg=CARD, fg=TEXT_FAINT,
                                   font=("Segoe UI", 8))
        self.sat_status.pack(side="left", padx=10)

    # ── profiles ───────────────────────────────────────────────
    def _build_profiles(self, parent):
        section_title(parent, "display profiles").pack(anchor="w", padx=16, pady=(8, 3))
        c = card(parent)
        c.pack(fill="x", padx=16, pady=(0, 16))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=14, pady=12)

        bar = tk.Frame(f, bg=CARD)
        bar.pack(fill="x")
        ttk.Button(bar, text="Save current as…", style="Success.TButton",
                   command=self._save_profile).pack(side="left")
        ttk.Button(bar, text="Apply selected", style="Accent.TButton",
                   command=self._apply_profile).pack(side="left", padx=6)
        ttk.Button(bar, text="Update selected", style="Ghost.TButton",
                   command=self._update_profile).pack(side="left")
        ttk.Button(bar, text="Delete selected", style="Danger.TButton",
                   command=self._delete_profile).pack(side="left", padx=6)

        self.profile_box = tk.Listbox(f, bg=BG_RAISED, fg=TEXT, height=6, bd=0,
                                      highlightthickness=1, highlightbackground=LINE,
                                      highlightcolor=RED, selectbackground=RED,
                                      selectforeground="#FFFFFF", activestyle="none",
                                      font=("Segoe UI", 9))
        self.profile_box.pack(fill="x", pady=(8, 0))

    # ── engine wiring ──────────────────────────────────────────
    def _defer(self, method_name, ms=180):
        """Slider drags fire continuously — debounce the driver calls."""
        job_attr = f"_defer_{method_name}"
        if getattr(self, job_attr, None):
            try:
                self.after_cancel(getattr(self, job_attr))
            except Exception:
                pass
        setattr(self, job_attr, self.after(ms, lambda: self._run_deferred(method_name, job_attr)))

    def _run_deferred(self, method_name, job_attr):
        setattr(self, job_attr, None)
        getattr(self, method_name)()

    def _ensure_engines(self):
        if not hasattr(self, "display"):
            self.display = deng.WindowsDisplay()
        if self._dvc is None and self._dvc_error is None:
            try:
                self._dvc = deng.NvidiaDVC(self.display.device)
            except Exception as exc:
                self._dvc_error = str(exc)
        if self._sat is None and self._sat_error is None:
            self._sat = deng.get_saturation()
            if self._sat is None:
                self._sat_error = deng.saturation_error()

    def refresh_all(self):
        try:
            self._ensure_engines()
            self.display.refresh(self.display.device)
            self._engine_error = None
        except Exception as exc:
            self._engine_error = str(exc)

        if getattr(self, "_engine_error", None):
            self.mode_chip.configure(text="display: unavailable", fg=RED_SOFT)
            self.mode_status.configure(text=self._engine_error, fg=RED_SOFT)
            return

        # display selector
        labels = []
        for info in self.display.devices:
            label = f"{info['monitor']}  ({'Primary' if info['primary'] else info['adapter']})"
            labels.append(label)
            info["label"] = label
        self.device_cb.configure(values=labels)
        current = next((i for i in self.display.devices if i["name"] == self.display.device), None)
        if current:
            self.device_cb.set(current["label"])

        self._fill_modes()
        self._update_chips()
        self._init_dvc_ui()
        self._init_saturation_ui()
        self._fill_profiles()

    def _on_device_selected(self, _e=None):
        label = self.device_cb.get()
        info = next((i for i in self.display.devices if i.get("label") == label), None)
        if not info:
            return
        try:
            self.display.select_device(info["name"])
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))
            return
        if isinstance(self._dvc, deng.NvidiaDVC):
            try:
                self._dvc.select_display(info["name"])
                self._init_dvc_ui(reset=True)
            except Exception:
                self._init_dvc_ui(reset=True)
        self._fill_modes()
        self._update_chips()
        self._cancel_revert(show=False)

    def _update_chips(self):
        d = self.display
        w, h, hz = d.current
        self.mode_chip.configure(text=f"{w}×{h} @ {hz or '?'} Hz · {len(d.modes)} modes", fg=TEXT_DIM)
        if isinstance(self._dvc, deng.NvidiaDVC):
            try:
                info = self._dvc.read()
                self.gpu_chip.configure(text=f"NVIDIA DVC: {int(info.currentLevel)} (range {int(info.minLevel)}–{int(info.maxLevel)})", fg=TEAL)
            except Exception:
                self.gpu_chip.configure(text="NVIDIA: not available", fg=TEXT_FAINT)
        else:
            self.gpu_chip.configure(text=f"NVIDIA: {self._dvc_error or 'not available'}", fg=TEXT_FAINT)
        if isinstance(self._sat, deng.MagnifierSaturation):
            state = f"Saturation: {self._sat.percent}%" if self._sat.active else "Saturation: neutral"
            self.sat_chip.configure(text=state, fg=TEAL if self._sat.active else TEXT_FAINT)
        else:
            self.sat_chip.configure(text="Saturation: unavailable", fg=TEXT_FAINT)

    # ── modes ──────────────────────────────────────────────────
    def _load_favorites(self) -> dict:
        try:
            import json
            from pathlib import Path
            path = Path(deng._DATA_DIR) / "display" / "favorites.json"
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except Exception:
            return {}

    def _save_favorites(self):
        try:
            import json
            from pathlib import Path
            path = Path(deng._DATA_DIR) / "display" / "favorites.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._favorites, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _fill_modes(self):
        self.mode_box.delete(0, tk.END)
        query = self.mode_search.get().strip().lower()
        favs = set(self._favorites.get(self.display.device, []))
        rows = []
        for mode in self.display.modes:
            label = deng.mode_label(mode)
            if query and query not in label.lower().replace(" ", "").replace("·", ""):
                continue
            rows.append((mode, label))
        rows.sort(key=lambda r: (r[0] not in favs, -r[0][0], -r[0][2]))
        self._mode_rows = rows
        for mode, label in rows:
            tag = ""
            if mode == self.display.current:
                tag = "  ● CURRENT"
            elif mode in favs:
                tag = "  ★"
            self.mode_box.insert("end", label + tag)
            if mode == self.display.current:
                self.mode_box.itemconfigure("end", fg=TEAL)

    def _selected_mode(self):
        sel = self.mode_box.curselection()
        if not sel:
            return None
        idx = sel[0]
        return self._mode_rows[idx][0] if idx < len(self._mode_rows) else None

    def _toggle_favorite(self):
        mode = self._selected_mode()
        if not mode:
            return
        favs = self._favorites.setdefault(self.display.device, [])
        if mode in favs:
            favs.remove(mode)
        else:
            favs.append(mode)
        self._save_favorites()
        self._fill_modes()

    def _apply_mode(self):
        mode = self._selected_mode()
        if not mode or self._pending_mode:
            return
        if mode == self.display.current:
            self.mode_status.configure(text="That mode is already active.", fg=TEXT_DIM)
            return
        try:
            result = self.display.set_mode(mode, test=True)
            if result != deng.DISP_CHANGE_SUCCESSFUL:
                self.mode_status.configure(text="Windows rejected that mode for this display.", fg=RED_SOFT)
                return
            result = self.display.set_mode(mode)
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))
            return
        if result != deng.DISP_CHANGE_SUCCESSFUL:
            self.mode_status.configure(text="Windows could not apply that mode.", fg=RED_SOFT)
            return
        self.display.refresh(self.display.device)
        self._fill_modes()
        self._update_chips()
        self._start_revert_countdown(mode)

    def _start_revert_countdown(self, mode):
        """Confirm-within-15s flow: keep the change, or revert automatically."""
        self._pending_mode = mode
        self._countdown = REVERT_SECONDS
        self.keep_btn.configure(state="normal", command=self._cancel_revert)
        self._revert_tick()

    def _revert_tick(self):
        if not self._pending_mode:
            return
        if self._countdown <= 0:
            self._auto_revert()
            return
        self.mode_status.configure(
            text=f"Mode changed to {deng.mode_label(self._pending_mode)} — "
                 f"reverting in {self._countdown}s…", fg=AMBER)
        self._countdown -= 1
        self._revert_job = self.after(1000, self._revert_tick)

    def _auto_revert(self):
        """Windows-style safety: undo the mode change the user never confirmed."""
        mode = self._pending_mode
        self._pending_mode = None
        self.keep_btn.configure(state="disabled")
        try:
            device = self.display.device
            original = self.display.original_modes.get(device)
            vib_error = None
            if original:
                result = self.display.set_mode(original)
                self.display.refresh(device)
                self._fill_modes()
                self._update_chips()
            if isinstance(self._dvc, deng.NvidiaDVC) and self._dvc.modified:
                try:
                    self._dvc.restore()
                    self._init_dvc_ui(reset=True)
                except Exception as exc:
                    vib_error = exc
        except Exception as exc:
            self.mode_status.configure(text=f"Automatic revert failed: {exc}", fg=RED_SOFT)
            return
        self.mode_status.configure(text="Reverted — the mode change was not confirmed.",
                                   fg=TEXT_DIM)

    def _cancel_revert(self, show=True):
        mode = self._pending_mode
        self._pending_mode = None
        if getattr(self, "_revert_job", None):
            try:
                self.after_cancel(self._revert_job)
            except Exception:
                pass
            self._revert_job = None
        self.keep_btn.configure(state="disabled")
        if show and mode:
            self.mode_status.configure(
                text=f"Kept {deng.mode_label(mode)}.", fg=TEAL)
        elif mode is None and show:
            self.mode_status.configure(text="", fg=TEXT_DIM)

    def _confirm_revert(self):
        """Called from UI: keep the mode (used by the keep button-less flow)."""
        self._cancel_revert(show=True)

    def _restore_mode(self):
        self._cancel_revert(show=False)
        try:
            device = self.display.device
            original = self.display.original_modes.get(device)
            if not original:
                return
            result = self.display.set_mode(original)
            if result != deng.DISP_CHANGE_SUCCESSFUL:
                messagebox.showerror("Valtix", "Windows could not restore the previous mode.")
                return
            self.display.refresh(device)
            self._fill_modes()
            self._update_chips()
            self.mode_status.configure(text="Restored the original Windows mode.", fg=TEAL)
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))

    # ── vibrance ───────────────────────────────────────────────
    def _init_dvc_ui(self, reset=False):
        if isinstance(self._dvc, deng.NvidiaDVC) and self._dvc.display_handle:
            try:
                info = self._dvc.read()
                self.dvc_scale.configure(from_=int(info.minLevel), to=int(info.maxLevel),
                                         state="normal")
                self.dvc_scale.set(int(info.currentLevel))
                self.dvc_value.configure(text=str(int(info.currentLevel)))
                self.dvc_status.configure(
                    text=f"{self.display.device_info['monitor']} — original "
                         f"{self._dvc.original_levels.get(self._dvc.device_name, '?')}",
                    fg=TEXT_FAINT)
                return
            except Exception:
                pass
        self.dvc_scale.configure(state="disabled")
        self.dvc_value.configure(text="—")
        self.dvc_status.configure(text=self._dvc_error or "NVIDIA control not available for this display.",
                                  fg=TEXT_FAINT)

    def _apply_vibrance(self):
        if not (isinstance(self._dvc, deng.NvidiaDVC) and self._dvc.display_handle):
            return
        try:
            level = self._dvc.set(self.dvc_scale.get())
            self.dvc_value.configure(text=str(level))
            self._update_chips()
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))

    def _restore_vibrance(self):
        if not isinstance(self._dvc, deng.NvidiaDVC):
            return
        try:
            level = self._dvc.restore_current()
            self.dvc_scale.set(level)
            self.dvc_value.configure(text=str(level))
            self._update_chips()
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))

    # ── saturation ─────────────────────────────────────────────
    def _init_saturation_ui(self):
        if isinstance(self._sat, deng.MagnifierSaturation) and not self._sat.has_existing_effect:
            self.sat_scale.configure(state="normal")
            self.sat_scale.set(self._sat.percent)
            self.sat_value.configure(text=f"{self._sat.percent}%")
            self.sat_status.configure(text="Live whole-desktop color filter.", fg=TEXT_FAINT)
        elif isinstance(self._sat, deng.MagnifierSaturation):
            self.sat_scale.configure(state="disabled")
            self.sat_value.configure(text="locked")
            self.sat_status.configure(text="A non-neutral Windows color effect is already active — left untouched.",
                                      fg=AMBER)
        else:
            self.sat_status.configure(text=self._sat_error or "Magnification API unavailable.",
                                      fg=TEXT_FAINT)

    def _apply_saturation(self):
        if not isinstance(self._sat, deng.MagnifierSaturation):
            return
        try:
            percent = self._sat.set_percent(self.sat_scale.get())
            self.sat_value.configure(text=f"{percent}%")
            self._update_chips()
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))
            self._init_saturation_ui()

    def _restore_saturation(self):
        if not isinstance(self._sat, deng.MagnifierSaturation):
            return
        try:
            self._sat.restore()
            self._init_saturation_ui()
            self._update_chips()
        except Exception as exc:
            messagebox.showerror("Valtix", str(exc))

    # ── profiles ───────────────────────────────────────────────
    def _current_profile(self) -> dict:
        try:
            info = self._dvc.read() if isinstance(self._dvc, deng.NvidiaDVC) and self._dvc.display_handle else None
        except Exception:
            info = None
        return {
            "monitor_device": self.display.device,
            "resolution": list(self.display.current),
            "vibrance": int(info.currentLevel) if info else None,
            "saturation": int(self._sat.percent) if isinstance(self._sat, deng.MagnifierSaturation) and self._sat.active else None,
        }

    def _fill_profiles(self):
        self.profile_box.delete(0, tk.END)
        profiles = deng.read_profiles()
        self._profile_rows = sorted(profiles, key=str.lower)
        if not self._profile_rows:
            self.profile_box.insert("end", "No profiles saved yet")
            return
        for name in self._profile_rows:
            p = profiles.get(name, {})
            res = p.get("resolution")
            suffix = f"  ·  {res[0]}×{res[1]}" if isinstance(res, list) else ""
            self.profile_box.insert("end", f"{name}{suffix}")

    def _selected_profile(self):
        sel = self.profile_box.curselection()
        if not sel or sel[0] >= len(self._profile_rows):
            return None
        return self._profile_rows[sel[0]]

    def _save_profile(self):
        name = self._ask_name()
        if not name:
            return
        profiles = deng.read_profiles()
        base = name
        i = 2
        while name in profiles:
            name = f"{base} ({i})"
            i += 1
        profiles[name] = self._current_profile()
        deng.write_profiles(profiles)
        self._fill_profiles()
        self.app.toast.show(f'Saved display profile "{name}".', kind="ok")

    def _ask_name(self):
        dlg = tk.Toplevel(self)
        dlg.title("Save display profile")
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Label(dlg, text="Name this display profile", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(padx=16, pady=(14, 6))
        var = tk.StringVar(value="My setup")
        ent = ttk.Entry(dlg, textvariable=var, width=30)
        ent.pack(padx=16, pady=(0, 12))
        ent.selection_range(0, "end")
        ent.focus_set()
        out = {"name": None}

        def ok(_e=None):
            out["name"] = var.get().strip() or None
            dlg.destroy()
        ent.bind("<Return>", ok)
        row = tk.Frame(dlg, bg=BG)
        row.pack(pady=(0, 14))
        ttk.Button(row, text="Save", style="Accent.TButton", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", style="Ghost.TButton",
                   command=dlg.destroy).pack(side="left", padx=4)
        self.wait_window(dlg)
        return out["name"]

    def _apply_profile(self):
        name = self._selected_profile()
        if not name:
            return
        profile = deng.read_profiles().get(name, {})
        errors = []
        device = profile.get("monitor_device")
        try:
            if device and device != self.display.device:
                self.display.select_device(device)
                self._on_device_selected()
        except Exception as exc:
            errors.append(str(exc))
        res = profile.get("resolution")
        if isinstance(res, list) and len(res) >= 2:
            try:
                mode = tuple(res[:3]) if len(res) >= 3 else (res[0], res[1], 0)
                if self.display.set_mode(mode, test=True) == deng.DISP_CHANGE_SUCCESSFUL:
                    self.display.set_mode(mode)
                    self.display.refresh(self.display.device)
                    self._fill_modes()
                    self._update_chips()
                    self._start_revert_countdown(mode)
                else:
                    errors.append("Windows rejected the profile's resolution.")
            except Exception as exc:
                errors.append(str(exc))
        vib = profile.get("vibrance")
        if vib is not None and isinstance(self._dvc, deng.NvidiaDVC) and self._dvc.display_handle:
            try:
                level = self._dvc.set(vib)
                self.dvc_scale.set(level)
                self.dvc_value.configure(text=str(level))
            except Exception as exc:
                errors.append(str(exc))
        sat = profile.get("saturation")
        if sat is not None and isinstance(self._sat, deng.MagnifierSaturation) \
                and not self._sat.has_existing_effect:
            try:
                self._sat.set_percent(sat)
                self.sat_scale.set(sat)
                self.sat_value.configure(text=f"{sat}%")
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            messagebox.showerror("Valtix", "Profile applied with issues:\n" + "\n".join(errors))
        else:
            self.app.toast.show(f'Applied "{name}".', kind="ok")

    def _update_profile(self):
        name = self._selected_profile()
        if not name:
            return
        profiles = deng.read_profiles()
        profiles[name] = self._current_profile()
        deng.write_profiles(profiles)
        self._fill_profiles()
        self.app.toast.show(f'Updated "{name}".', kind="ok")

    def _delete_profile(self):
        name = self._selected_profile()
        if not name:
            return
        if not messagebox.askyesno("Valtix", f'Delete display profile "{name}"?'):
            return
        profiles = deng.read_profiles()
        profiles.pop(name, None)
        deng.write_profiles(profiles)
        self._fill_profiles()

    # ── restore-everything / shutdown ──────────────────────────
    def _restore_all(self):
        errors = []
        self._cancel_revert(show=False)
        try:
            self._restore_mode()
        except Exception as exc:
            errors.append(str(exc))
        if isinstance(self._dvc, deng.NvidiaDVC):
            try:
                self._dvc.restore()
                self._init_dvc_ui(reset=True)
                self._update_chips()
            except Exception as exc:
                errors.append(str(exc))
        if isinstance(self._sat, deng.MagnifierSaturation):
            try:
                self._sat.restore()
                self._init_saturation_ui()
                self._update_chips()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            messagebox.showerror("Valtix", "Restore finished with issues:\n" + "\n".join(errors))
        else:
            self.app.toast.show("Display changes restored.", kind="ok")

    def shutdown(self):
        """Called by ValtixApp on quit: revert pending mode, restore DVC + saturation."""
        self._cancel_revert(show=False)
        if getattr(self, "_dvc", None) is not None:
            try:
                self._dvc.restore()
            except Exception:
                pass
        if getattr(self, "_sat", None) is not None:
            try:
                self._sat.shutdown()
            except Exception:
                pass

    def on_show(self):
        self.refresh_all()
