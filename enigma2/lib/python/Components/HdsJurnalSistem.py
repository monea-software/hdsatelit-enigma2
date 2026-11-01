# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnalSistem.py: jurnalul retelei (/home/root/logs/hds-retea.log) si al discurilor (/home/root/logs/hds-discuri.log),
# forma din Components/HdsJurnal.py. porneste() din mytest.py (o data, dupa pornirea interfetei): un ceas de PAUZA_S
# secunde citeste numai fisiere din /sys si /proc si scrie doar ce s-a schimbat:
# - reteaua: fiecare interfata (fara lo): legatura sus/jos, viteza si duplexul pe cablu, daca are adresa IPv4 (da/nu,
#   fara adresa), la Wi-Fi nivelul semnalului in dBm (scris la legatura noua si la o schimbare de cel putin PRAG_DBM),
#   numarul de reconectari. FARA adrese IP sau MAC, FARA numele retelei Wi-Fi.
# - discurile: montarea si demontarea sub /media si /run/media (dispozitivul, sistemul de fisiere, marimea, cat e
#   liber), spatiul sub PRAG_LIBER_PROCENTE (cel mult un rand pe ora pe disc). Numele dosarului de montare se scrie numai
#   daca e unul obisnuit (hdd, usb, usb1, sdcard, mmc, net...), altfel "eticheta".

import os
import re
import time

from Components import HdsJurnal

PAUZA_S = 30
PRAG_DBM = 10
PRAG_LIBER_PROCENTE = 5
FS_LOCALE = ("ext2", "ext3", "ext4", "vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "xfs", "btrfs",
	"f2fs", "hfsplus", "jfs", "reiserfs", "iso9660", "udf")
NUME_OBISNUITE = re.compile(r"^(hdd|usb\d*|sd[a-z]\d*|sdcard|mmc\d*|mmcblk\d+p\d+|net|autofs|cf|hdd\d*|usb_\w{1,4})$")

_ceas = [None]
_retea = {}
_reconectari = {}
_discuri = {}
_avertizat_liber = {}


def _citeste(cale, implicit=""):
	try:
		with open(cale) as f:
			return f.read().strip()
	except (IOError, OSError):
		return implicit


def _wifi_dbm(iface, proc="/proc/net/wireless"):
	text = _citeste(proc)
	for rand in text.splitlines()[2:]:
		p = rand.replace(":", " ").split()
		if len(p) >= 4 and p[0] == iface:
			try:
				return int(float(p[3].rstrip(".")))
			except ValueError:
				return None
	return None


def _are_ipv4(iface):
	"""da/nu: interfata are o adresa IPv4 (citita din /proc/net/route: o ruta pe ea)."""
	text = _citeste("/proc/net/route")
	return any(r.split()[0] == iface for r in text.splitlines()[1:] if r.split())


def stareRetea(sys_net="/sys/class/net"):
	stare = {}
	try:
		ifaces = sorted(os.listdir(sys_net))
	except OSError:
		return stare
	for i in ifaces:
		if i == "lo" or i.startswith(("sit", "ip6tnl", "tun", "dummy")):
			continue
		d = os.path.join(sys_net, i)
		wifi = os.path.isdir(os.path.join(d, "wireless"))
		sus = _citeste(os.path.join(d, "operstate")) == "up" or _citeste(os.path.join(d, "carrier")) == "1"
		s = {"wifi": wifi, "sus": sus}
		if sus and not wifi:
			s["viteza"] = _citeste(os.path.join(d, "speed"))
			s["duplex"] = _citeste(os.path.join(d, "duplex"))
		if sus:
			s["ipv4"] = _are_ipv4(i)
		if wifi and sus:
			s["dbm"] = _wifi_dbm(i)
		stare[i] = s
	return stare


def _text_iface(i, s):
	if not s["sus"]:
		return "%s legatura jos" % i
	parti = ["%s legatura sus" % i]
	if s.get("viteza") and s["viteza"] not in ("-1", ""):
		parti.append("%s Mb/s %s" % (s["viteza"], s.get("duplex") or ""))
	if s.get("dbm") is not None:
		parti.append("semnal %d dBm" % s["dbm"])
	parti.append("adresa IPv4 %s" % ("da" if s.get("ipv4") else "nu"))
	return " ".join(p.strip() for p in parti)


def verificaReteaua(stare=None):
	stare = stareRetea() if stare is None else stare
	for i, s in stare.items():
		v = _retea.get(i)
		if v is None:
			HdsJurnal.info("retea", "legatura", _text_iface(i, s) + " (la pornire)")
		elif v["sus"] != s["sus"]:
			if s["sus"]:
				_reconectari[i] = _reconectari.get(i, 0) + 1
				HdsJurnal.info("retea", "legatura", "%s (reconectarea %d)" % (_text_iface(i, s), _reconectari[i]))
			else:
				HdsJurnal.avert("retea", "legatura", _text_iface(i, s))
		elif s["sus"] and (v.get("ipv4") != s.get("ipv4") or v.get("viteza") != s.get("viteza")):
			HdsJurnal.info("retea", "legatura", _text_iface(i, s))
		elif s.get("dbm") is not None and v.get("dbm") is not None and abs(s["dbm"] - v["dbm"]) >= PRAG_DBM:
			HdsJurnal.info("retea", "wifi", "%s semnal %d dBm (era %d dBm)" % (i, s["dbm"], v["dbm"]))
		else:
			if s.get("dbm") is not None and v.get("dbm") is not None:
				s["dbm"] = v["dbm"]  # se compara cu ultimul scris
		_retea[i] = s
	for i in list(_retea):
		if i not in stare:
			HdsJurnal.avert("retea", "legatura", "%s interfata disparuta" % i)
			del _retea[i]


def _nume_montare(punct):
	b = os.path.basename(punct.rstrip("/"))
	return punct if NUME_OBISNUITE.match(b) else os.path.dirname(punct.rstrip("/")) + "/eticheta"


def stareDiscuri(mounts="/proc/mounts"):
	stare = {}
	for rand in _citeste(mounts).splitlines():
		p = rand.split()
		if len(p) < 3 or not p[1].startswith(("/media/", "/run/media/")):
			continue
		if p[2] in ("tmpfs", "autofs", "ramfs"):
			continue
		punct = p[1].replace("\\040", " ")
		total = liber = 0
		if p[2] not in FS_LOCALE:
			# un disc de retea cazut ar opri firul principal in statvfs: numai felul lui
			stare[punct] = {"dispozitiv": "retea", "fs": p[2], "total": 0, "liber": 0}
			continue
		try:
			st = os.statvfs(punct)
			total = st.f_blocks * st.f_frsize
			liber = st.f_bavail * st.f_frsize
		except (OSError, AttributeError):
			total = liber = 0
		stare[punct] = {"dispozitiv": os.path.basename(p[0]), "fs": p[2], "total": total, "liber": liber}
	return stare


def _gb(octeti):
	return "%.1f GB" % (octeti / 1e9)


def verificaDiscurile(stare=None, acum=None):
	stare = stareDiscuri() if stare is None else stare
	acum = time.time() if acum is None else acum
	for punct, d in stare.items():
		nume = _nume_montare(punct)
		if punct not in _discuri:
			HdsJurnal.info("discuri", "montare", "%s montat: %s %s, %s, liber %s" % (nume, d["dispozitiv"], d["fs"],
				_gb(d["total"]), _gb(d["liber"])))
		if d["total"] and d["liber"] * 100 < d["total"] * PRAG_LIBER_PROCENTE:
			if punct not in _avertizat_liber or acum - _avertizat_liber[punct] >= 3600:
				_avertizat_liber[punct] = acum
				HdsJurnal.avert("discuri", "spatiu", "%s aproape plin: liber %s din %s" % (nume, _gb(d["liber"]),
					_gb(d["total"])))
		_discuri[punct] = d
	for punct in list(_discuri):
		if punct not in stare:
			HdsJurnal.info("discuri", "montare", "%s demontat (%s)" % (_nume_montare(punct), _discuri[punct]["dispozitiv"]))
			del _discuri[punct]


def _tic():
	try:
		verificaReteaua()
	except Exception:
		pass
	try:
		verificaDiscurile()
	except Exception:
		pass


def porneste():
	if _ceas[0] is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		_ceas[0] = False
		return
	t = eTimer()
	t.callback.append(_tic)
	t.start(PAUZA_S * 1000, False)
	_ceas[0] = t
	_tic()
