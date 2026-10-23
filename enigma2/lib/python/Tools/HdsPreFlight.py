#!/usr/bin/env python3
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""
HDSatelit Pre-Flight Checker — rulat înainte de enigma2

Verifică TOATE fișierele .py din /usr/lib/enigma2/python/ recursiv.
Cache per-fișier (mtime + size): fișierele neschimbate sunt sărite automat.

Comportament la erori:
  - Fișiere critice corupte  → restaurare din backup automat
  - Plugin cu eroare          → dezactivat temporar (stub gol)
  - Helper de plugin corupt   → dezactivează întreg pluginul
  - Alt fișier core corupt    → restaurare din backup sau marcat critic

Exit codes: 0 = OK, 1 = erori critice fără recuperare
"""
import sys
import os
import py_compile
import shutil
import json
from pathlib import Path

ENIGMA2_PYTHON = "/usr/lib/enigma2/python"
PLUGINS_DIR    = os.path.join(ENIGMA2_PYTHON, "Plugins")
BACKUP_DIR     = "/etc/enigma2/hds_backup"
DISABLED_FILE  = "/tmp/hds_disabled_plugins.json"
CACHE_FILE     = "/etc/enigma2/hds_preflight_cache.json"
LOG_PREFIX     = "[HDSatelit PreFlight]"

# Fișiere verificate PRIORITAR (cu logging explicit + backup obligatoriu)
CRITICAL_FILES = [
    "mytest.py",
    "Components/config.py",
    "Components/UsageConfig.py",
    "Components/AVSwitch.py",
    "Components/ParentalControl.py",
    "Components/Timezones.py",
    "Screens/LogManager.py",
]

# Directoare și fișiere sărite complet
SKIP_DIRS  = {"__pycache__", ".git"}
SKIP_FILES = {"HdsPreFlight.py"}  # scriptul acesta nu se auto-validează

errors_critical  = []
disabled_plugins = []

# ── Cache ─────────────────────────────────────────────────────────────────────
def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass

def file_sig(path):
    try:
        st = os.stat(path)
        return [round(st.st_mtime, 3), st.st_size]
    except Exception:
        return [0, 0]

def is_cached_ok(cache, path):
    entry = cache.get(path)
    return bool(entry and entry.get("ok") and entry.get("sig") == file_sig(path))

def update_cache(cache, path, ok):
    cache[path] = {"sig": file_sig(path), "ok": bool(ok)}

# ── Utilitare ─────────────────────────────────────────────────────────────────
def log(msg):
    print(f"{LOG_PREFIX} {msg}", flush=True)

def check_syntax(filepath):
    try:
        py_compile.compile(filepath, doraise=True)
        return True, None
    except py_compile.PyCompileError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def save_backup(filepath):
    rel    = os.path.relpath(filepath, ENIGMA2_PYTHON)
    backup = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(backup), exist_ok=True)
    try:
        shutil.copy2(filepath, backup)
    except Exception:
        pass

def try_restore(filepath):
    rel    = os.path.relpath(filepath, ENIGMA2_PYTHON)
    backup = os.path.join(BACKUP_DIR, rel)
    if os.path.isfile(backup):
        try:
            shutil.copy2(backup, filepath)
            ok, _ = check_syntax(filepath)
            return ok
        except Exception:
            pass
    return False

def disable_plugin(plugin_dir, reason_file, err_msg, cache):
    """Dezactivează pluginul din plugin_dir scriind un stub gol."""
    plugin_py = plugin_dir / "plugin.py"
    if not plugin_py.exists():
        return
    stub = str(plugin_py) + ".disabled"
    if os.path.isfile(stub):
        return  # deja dezactivat
    try:
        os.rename(str(plugin_py), stub)
        with open(str(plugin_py), "w", encoding="utf-8") as f:
            f.write("# HDSatelit: dezactivat automat\n")
            f.write(f"# Fișier problematic: {reason_file}\n")
            f.write("def Plugins(**kwargs):\n    return []\n")
        name = str(plugin_dir.relative_to(PLUGINS_DIR))
        disabled_plugins.append({"plugin": name, "error": f"{reason_file}: {err_msg[:150]}"})
        log(f"    → Plugin dezactivat: {name}")
        update_cache(cache, str(plugin_py), False)
    except Exception as e2:
        log(f"    → Eroare dezactivare: {e2}")

# ── Main ──────────────────────────────────────────────────────────────────────
cache       = load_cache()
cache_hits  = 0
n_checked   = 0
n_errors    = 0

# ── PASUL 1: Fișiere critice (cu logging detaliat) ───────────────────────────
log("=== Fișiere critice ===")
for rel_path in CRITICAL_FILES:
    full = os.path.join(ENIGMA2_PYTHON, rel_path)
    if not os.path.isfile(full):
        log(f"  LIPSĂ: {rel_path}")
        errors_critical.append(f"Lipsă: {rel_path}")
        continue
    if is_cached_ok(cache, full):
        log(f"  SKIP: {rel_path}")
        cache_hits += 1
        continue
    n_checked += 1
    ok, err = check_syntax(full)
    if ok:
        log(f"  OK: {rel_path}")
        save_backup(full)
        update_cache(cache, full, True)
    else:
        log(f"  EROARE: {rel_path}")
        log(f"    → {err[:120]}")
        n_errors += 1
        update_cache(cache, full, False)
        if try_restore(full):
            log(f"  RESTAURAT ✓")
            update_cache(cache, full, True)
        else:
            errors_critical.append(rel_path)

# ── PASUL 2 + 3: TOATE celelalte fișiere .py din enigma2 python/ ─────────────
log("")
log("=== Scanare completă python/ (toate subdirectoarele) ===")

# Restaurăm plugin-uri dezactivate anterior dacă helper-ul s-a reparat
for stub in Path(PLUGINS_DIR).rglob("plugin.py.disabled"):
    ok_stub, _ = check_syntax(str(stub))
    if ok_stub:
        target = Path(str(stub)[:-len(".disabled")])
        try:
            if target.exists():
                os.remove(str(target))
            os.rename(str(stub), str(target))
            log(f"  RESTAURAT plugin: {target.parent.relative_to(PLUGINS_DIR)}")
            update_cache(cache, str(target), True)
        except Exception:
            pass

for py_file in sorted(Path(ENIGMA2_PYTHON).rglob("*.py")):
    # Sari directoare blacklistate
    if any(part in SKIP_DIRS for part in py_file.parts):
        continue
    # Sari fișiere blacklistate
    if py_file.name in SKIP_FILES:
        continue
    rel = str(py_file.relative_to(ENIGMA2_PYTHON))
    # Sari critice (deja verificate)
    if rel in CRITICAL_FILES:
        continue

    full = str(py_file)
    if is_cached_ok(cache, full):
        cache_hits += 1
        continue

    n_checked += 1
    ok, err = check_syntax(full)
    if ok:
        save_backup(full)
        update_cache(cache, full, True)
    else:
        log(f"  EROARE: {rel}")
        log(f"    → {err[:100]}")
        n_errors += 1
        update_cache(cache, full, False)

        is_plugin_file = "Plugins" in py_file.parts

        if is_plugin_file:
            # Găsim directorul rădăcină al pluginului (cel care conține plugin.py)
            plugin_root = py_file.parent
            while plugin_root != Path(PLUGINS_DIR) and not (plugin_root / "plugin.py").exists():
                plugin_root = plugin_root.parent
            if (plugin_root / "plugin.py").exists():
                disable_plugin(plugin_root, py_file.name, err, cache)
            else:
                log(f"    → Helper orfan — ignorat")
        else:
            # Fișier core non-plugin → restaurare din backup
            if try_restore(full):
                log(f"    → Restaurat din backup ✓")
                update_cache(cache, full, True)
            else:
                errors_critical.append(rel)

log(f"  Verificate: {n_checked} | Sărite (cache): {cache_hits} | Erori: {n_errors}")

# ── Salvare cache ─────────────────────────────────────────────────────────────
save_cache(cache)

# ── Plugin-uri dezactivate ────────────────────────────────────────────────────
if disabled_plugins:
    try:
        with open(DISABLED_FILE, "w") as f:
            json.dump(disabled_plugins, f, indent=2)
    except Exception:
        pass

# ── Raport final ──────────────────────────────────────────────────────────────
log("")
log("═══════════════════════════════════════════════")
if errors_critical:
    log("REZULTAT: ERORI CRITICE!")
    for e in errors_critical:
        log(f"  ✗ {e}")
    log("═══════════════════════════════════════════════")
    sys.exit(1)
else:
    log(f"REZULTAT: OK — enigma2 poate porni în siguranță")
    log(f"  Verificate: {n_checked} | Cache hit: {cache_hits}")
    if disabled_plugins:
        log(f"  ⚠ {len(disabled_plugins)} plugin(uri) dezactivat(e) temporar")
    log("═══════════════════════════════════════════════")
    sys.exit(0)
