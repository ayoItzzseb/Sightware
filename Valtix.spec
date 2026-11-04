# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Valtix GUI Edition.
# Build with:  pyinstaller Valtix.spec --noconfirm
# The backend modules are imported flat (run.py puts backend/ on sys.path),
# so they must be listed as hidden imports for the static analyzer.

a = Analysis(
    ["run.py"],
    pathex=[".", "backend"],
    binaries=[],
    datas=[("VERSION", "."), ("valtix.ico", "."),
           ("assets/valtix-brand-256.png", "assets")],
    hiddenimports=[
        # backend domain modules (flat imports, some inside functions)
        "live_match", "valapi", "sample_match", "sample_data", "history",
        "encounter_log", "session_tracker", "inventory", "match_meta",
        "party_detector", "pick_advisor", "assistant",
        "settings", "riot_client", "agents", "vconstants", "valtixlog",
        # crosshair overlay (flat backend modules)
        "crosshair_store", "crosshair_render", "crosshair_overlay",
        "crosshair_codes",
        "crosshair_input",
        # chromadesk display engine (flat backend module)
        "display_engine",
        # gui package
        "gui", "gui.core", "gui.theme", "gui.widgets", "gui.dialogs",
        "gui.queue_monitor", "gui.platform_win", "gui.update_check",
        "gui.tabs.live_tab", "gui.tabs.performance_tab",
        "gui.tabs.encounters_tab", "gui.tabs.sessions_tab",
        "gui.tabs.inventory_tab", "gui.tabs.crosshair_tab",
        "gui.tabs.display_tab",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Valtix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="valtix.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Valtix",
)
