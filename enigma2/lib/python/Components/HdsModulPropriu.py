# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsModulPropriu.py: the person's own access module program (an OSCam or NCam binary they built or downloaded, not a
# package) added to the list of access modules (0.8.0, FAA7MED, GigaBlue UHD TRIO 4K, forum 588 #3895 and #3966:
# "I have oscam in binary for how can i install it"). The list (Screens/CamSetup.py, web /acces-conditionat) shows only
# modules with a start script /etc/init.d/<kind>.<name>; a bare binary had no way in.
#
#   - candidati(): the files that look like such a program (name starting with oscam or ncam, an ELF for this receiver's
#     processor) on a stick or disk (two folders deep), in /tmp and in /usr/softcam, /usr/softcams, /usr/bin without a
#     start script. Network places are skipped (a share that does not answer would hold the search);
#   - adauga(cale): the program is copied to /usr/<kind>s/<name> (left in place when it is already there), made
#     executable, and gets a start script made like the scripts of our feed packages (start, stop, restart, status,
#     version; the configuration folder is the one that already has <oscam|ncam>.conf, otherwise
#     /etc/tuxbox/config/<oscam|ncam>). The module then shows in the list; Green chooses and starts it as any other.
#     Nothing is chosen or started here, nothing of the person's configuration is touched or deleted.
# Screen and web use the same functions; the copy runs off the enigma2 thread (Screens/CamSetup.py, CitirePeFir).
# Nothing from enigma is imported at load time (PC tests); RADACINA puts a folder in front of the system paths.
import os
import posixpath
import re
import shutil
import stat

RADACINA = ""
DOSAR_SCRIPTURI = "/etc/init.d"
LOCURI = ("/media", "/hdd", "/mnt", "/tmp")
DOSARE_PROGRAME = ("/usr/softcam", "/usr/softcams", "/usr/bin", "/usr/keys", "/var/bin")
ADANCIME = 2
MARIME_MIN = 64 * 1024
MARIME_MAX = 64 * 1024 * 1024
MAXIM = 30
FEL_IMPLICIT = "softcam"
DOSAR_CONFIG = "/etc/tuxbox/config"
_NUME = re.compile(r"^(oscam|ncam)", re.I)
_NUME_BUN = re.compile(r"[^A-Za-z0-9._+-]+")
# e_machine of the processor the receiver runs on, from os.uname (the same table as HdsBibliotecaLipsa)
_MASINI = (("aarch64", 183), ("arm", 40), ("mips", 8), ("x86_64", 62), ("i686", 3), ("i386", 3), ("sh4", 42))

SCRIPT = """#!/bin/sh
### BEGIN INIT INFO
# Provides:          @FEL@.@CAM@
# Short-Description: @TITLU@
# Description:       Start, stop and restart @TITLU@, added by the person from their own program file
#                    (HD Satelit image, Components/HdsModulPropriu.py). The module started at boot is the one
#                    selected through the link /etc/init.d/@FEL@.
### END INIT INFO

CAM=@CAM@
DAEMON=/usr/@FEL@s/$CAM
CONFDIR=@CONFDIR@
TMPDIR=/tmp/.$CAM
PIDFILE=/var/run/$CAM.pid

[ -x "$DAEMON" ] || { echo "$DAEMON is missing"; exit 1; }
EXE=$(readlink -f "$DAEMON" 2>/dev/null)
[ -n "$EXE" ] || EXE=$DAEMON

running() {
	for p in $(pidof "$CAM" 2>/dev/null); do
		[ "$(readlink /proc/$p/exe 2>/dev/null)" = "$EXE" ] && return 0
	done
	return 1
}

start() {
	if running; then
		echo "$CAM is already running"
		return 0
	fi
	[ -d "$CONFDIR" ] || mkdir -p "$CONFDIR"
	echo -n "Starting $CAM: "
	ulimit -s 1024
	"$DAEMON" --config-dir "$CONFDIR" --temp-dir "$TMPDIR" --daemon --pidfile "$PIDFILE" --restart 2
	n=0
	while [ $n -lt 10 ]; do
		running && { echo "OK"; return 0; }
		sleep 1
		n=$((n + 1))
	done
	echo "FAILED"
	return 1
}

stop() {
	echo -n "Stopping $CAM: "
	start-stop-daemon -K -q -x "$DAEMON" >/dev/null 2>&1
	n=0
	while [ $n -lt 10 ]; do
		running || break
		sleep 1
		n=$((n + 1))
	done
	if running; then
		start-stop-daemon -K -q -s KILL -x "$DAEMON" >/dev/null 2>&1
		sleep 1
	fi
	if running; then
		echo "FAILED"
		return 1
	fi
	rm -f "$PIDFILE"
	rm -rf "$TMPDIR"
	echo "OK"
	return 0
}

case "$1" in
	start)
		start
		exit $?
		;;
	stop)
		stop
		exit $?
		;;
	restart|reload)
		stop
		start
		exit $?
		;;
	status)
		if running; then echo "$CAM: running"; exit 0; fi
		echo "$CAM: stopped"
		exit 1
		;;
	version|info)
		"$DAEMON" -V 2>/dev/null | sed -n 's/^Version:[[:space:]]*//p' | head -n 1
		;;
	*)
		echo "Usage: $0 start|stop|restart|status|version"
		exit 1
		;;
esac
exit 0
"""


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	return text


def _jurnal(text):
	print("[HdsModulPropriu] %s" % text)


def _c(cale):
	return RADACINA + cale if RADACINA else cale


def masinaNoastra():
	try:
		m = os.uname()[4].lower()
	except (AttributeError, OSError):
		return None
	for prefix, cod in _MASINI:
		if m.startswith(prefix):
			return cod
	return None


def masinaElf(cale):
	"""e_machine of an ELF file (static or dynamic), or None when it is not an ELF"""
	try:
		with open(cale, "rb") as f:
			cap = f.read(20)
	except (OSError, IOError):
		return None
	if len(cap) < 20 or cap[:4] != b"\x7fELF":
		return None
	ordine = "little" if cap[5:6] == b"\x01" else "big"
	return int.from_bytes(cap[18:20], ordine)


def fel():
	"""the kind of the ordinary access modules on this receiver (HdsModuleAcces.feluri, the first), else softcam"""
	try:
		try:
			from Components import HdsModuleAcces
		except ImportError:
			import HdsModuleAcces
		f = HdsModuleAcces.feluri()
		if f:
			return f[0]
	except Exception as e:
		_jurnal("felurile: %r" % (e,))
	return FEL_IMPLICIT


def _retea():
	try:
		try:
			from Components import HdsPachete
		except ImportError:
			import HdsPachete
		return HdsPachete.locuri_retea()
	except Exception:
		return []


def _sub(cale, locuri):
	return any(cale == l or cale.startswith(l.rstrip("/") + "/") for l in locuri)


def _cu_script(fel_, rad_cale):
	"""the program paths named by the start scripts of fel_ (DAEMON lines and /usr/<kind>s/$CAM), real paths"""
	rez = set()
	# the same parser as the module list (every variable of every script), when it loads
	try:
		try:
			from Components import HdsInterfeteCam as IC
		except ImportError:
			import HdsInterfeteCam as IC
		for s in IC.citeste_scripturi(IC.Sistem(RADACINA or "/"), [fel_]).values():
			for c in list(s.cai) + list(s.cai.values()):
				if isinstance(c, str) and c.startswith("/"):
					rez.add(os.path.realpath(_c(c)))
	except Exception as e:
		_jurnal("scripturile modulelor: %r" % (e,))
	d = _c(DOSAR_SCRIPTURI)
	try:
		nume = os.listdir(d)
	except OSError:
		return rez
	for n in nume:
		if not n.startswith(fel_ + "."):
			continue
		sufix = n[len(fel_) + 1:]
		rez.add(os.path.realpath(_c("/usr/%ss/%s" % (fel_, sufix))))
		try:
			with open(os.path.join(d, n), encoding="utf-8", errors="replace") as f:
				text = f.read(65536)
		except (OSError, IOError):
			continue
		for m in re.finditer(r"(?m)^\s*(?:DAEMON|BINARY|BIN|EXEC|PROG)=[\"']?(/[^\s\"'$]+)", text):
			rez.add(os.path.realpath(_c(m.group(1))))
	return rez


def _semn(cale):
	"""(size, sha1 of the first 64 KB): the same program already added under another name is not offered again"""
	import hashlib
	try:
		with open(cale, "rb") as f:
			return os.path.getsize(cale), hashlib.sha1(f.read(65536)).hexdigest()
	except (OSError, IOError):
		return None


def _bun(cale_reala, noi):
	try:
		st = os.stat(cale_reala)
	except OSError:
		return False
	if not stat.S_ISREG(st.st_mode) or not (MARIME_MIN <= st.st_size <= MARIME_MAX):
		return False
	m = masinaElf(cale_reala)
	return m is not None and (noi is None or m == noi)


def candidati(masina=None):
	"""[{"cale", "nume", "marime", "loc"}]: the program files that can be added, at most MAXIM, first those in the program
	folders, then by path. masina: e_machine of the receiver (default: masinaNoastra())."""
	noi = masinaNoastra() if masina is None else masina
	f = fel()
	folosite = _cu_script(f, RADACINA)
	semne = set(s for s in (_semn(c) for c in folosite if os.path.isfile(c)) if s)
	sare = _retea()
	rez, vazute = [], set()

	def vezi(cale_interioara, cale_reala, loc):
		n = posixpath.basename(cale_interioara)
		if not _NUME.match(n) or n.lower().endswith((".ipk", ".tar", ".gz", ".zip", ".conf", ".txt", ".log", ".sh", ".deb")):
			return
		real = os.path.realpath(cale_reala)
		if real in vazute or real in folosite or not _bun(real, noi) or _semn(real) in semne:
			return
		vazute.add(real)
		rez.append({"cale": cale_interioara, "nume": n, "marime": os.path.getsize(real), "loc": loc})

	for d in DOSARE_PROGRAME:
		try:
			for e in os.scandir(_c(d)):
				if e.is_file(follow_symlinks=False):
					vezi(d + "/" + e.name, e.path, "program")
		except OSError:
			continue
	for loc in LOCURI:
		if _sub(loc, sare):
			continue
		coada = [(_c(loc), loc, 0)]
		while coada and len(rez) < MAXIM * 2:
			dosar, interior, nivel = coada.pop(0)
			try:
				intrari = list(os.scandir(dosar))
			except OSError:
				continue
			for e in intrari:
				if e.name.startswith("."):
					continue
				cale = interior.rstrip("/") + "/" + e.name
				if _sub(cale, sare):
					continue
				try:
					if e.is_dir(follow_symlinks=False):
						if nivel + 1 <= ADANCIME and loc != "/tmp":
							coada.append((e.path, cale, nivel + 1))
					elif e.is_file(follow_symlinks=False):
						vezi(cale, e.path, "stick")
				except OSError:
					continue
	rez.sort(key=lambda x: (x["loc"] != "program", x["cale"]))
	return rez[:MAXIM]


def _sufixNou(f, baza):
	"""<oscam|ncam>-own, then -own2...: a name free both in the program folder and among the scripts"""
	for i in range(1, 100):
		s = "%s-own%s" % (baza, "" if i == 1 else i)
		if not os.path.lexists(_c("%s/%s.%s" % (DOSAR_SCRIPTURI, f, s))) and not os.path.lexists(_c("/usr/%ss/%s" % (f, s))):
			return s
	return None


def dosarConfigurare(baza):
	"""the folder that already has <baza>.conf (the person's own configuration), else /etc/tuxbox/config/<baza>"""
	for d in (DOSAR_CONFIG + "/" + baza, DOSAR_CONFIG, "/etc/tuxbox/" + baza, "/var/tuxbox/config", "/usr/keys"):
		if os.path.isfile(_c(d + "/" + baza + ".conf")):
			return d
	return DOSAR_CONFIG + "/" + baza


def adauga(cale, masina=None):
	"""{"ok", "motiv", "fel", "sufix", "nume", "eroare"}; motivele: gata, nu_e_candidat, fara_nume, copiere, script.
	cale: one of candidati(). Runs off the enigma2 thread (a copy of up to 64 MB)."""
	rez = {"ok": False, "motiv": "", "fel": "", "sufix": "", "nume": posixpath.basename(cale or ""), "eroare": ""}
	gasit = None
	for x in candidati(masina):
		if x["cale"] == cale:
			gasit = x
			break
	if gasit is None:
		rez["motiv"] = "nu_e_candidat"
		return rez
	f = fel()
	baza = _NUME.match(gasit["nume"]).group(1).lower()
	sufix = _sufixNou(f, baza)
	if sufix is None:
		rez["motiv"] = "fara_nume"
		return rez
	rez["fel"], rez["sufix"] = f, sufix
	dosar = _c("/usr/%ss" % f)
	tinta = dosar + "/" + sufix
	try:
		os.makedirs(dosar, exist_ok=True)
		nou = tinta + ".hds-nou"
		shutil.copyfile(_c(cale), nou)
		os.chmod(nou, 0o755)
		os.replace(nou, tinta)
	except (OSError, IOError, shutil.Error) as e:
		rez["motiv"], rez["eroare"] = "copiere", str(e)
		try:
			os.remove(tinta + ".hds-nou")
		except OSError:
			pass
		return rez
	text = (SCRIPT.replace("@FEL@", f).replace("@CAM@", sufix).replace("@CONFDIR@", dosarConfigurare(baza))
		.replace("@TITLU@", "%s (%s)" % (gasit["nume"], baza.upper() if baza == "ncam" else "OSCam")))
	script = _c("%s/%s.%s" % (DOSAR_SCRIPTURI, f, sufix))
	try:
		with open(script + ".hds-nou", "w", encoding="utf-8", newline="\n") as fis:
			fis.write(text)
		os.chmod(script + ".hds-nou", 0o755)
		os.replace(script + ".hds-nou", script)
	except (OSError, IOError) as e:
		rez["motiv"], rez["eroare"] = "script", str(e)
		return rez
	try:
		try:
			from Components import HdsModuleAcces
		except ImportError:
			import HdsModuleAcces
		HdsModuleAcces.uita_felurile()
	except Exception:
		pass
	_jurnal("adaugat %s din %s ca %s.%s" % (gasit["nume"], cale, f, sufix))
	rez["ok"], rez["motiv"] = True, "gata"
	return rez


def textRezultat(r):
	"""the sentence for the person (screen and web)"""
	m = r.get("motiv")
	if m == "gata":
		return _("Am adăugat %s în listă. Alege-l și apasă Verde ca să pornească.") % r.get("sufix", "")
	if m == "nu_e_candidat":
		return _("Fișierul %s nu mai e acolo sau nu e un program pentru acest receptor.") % r.get("nume", "")
	if m == "fara_nume":
		return _("Sunt deja prea multe module adăugate de tine cu același nume.")
	if m in ("copiere", "script"):
		return _("Nu l-am putut adăuga: %s") % (r.get("eroare") or "-")
	return ""


TEXT_RAND = N_("Adaugă programul tău (OSCam sau NCam)")
TEXT_DETALII = N_("Pune fișierul programului (oscam sau ncam, făcut pentru procesorul acestui receptor) pe stick, pe disc, în /tmp sau în /usr/softcam. OK îl caută, îl copiază în lista modulelor și îi face scriptul de pornire. Configurarea ta rămâne unde e.")
TEXT_NIMIC = N_("N-am găsit niciun program OSCam sau NCam pentru acest receptor pe stick, pe disc, în /tmp sau în /usr/softcam.")
