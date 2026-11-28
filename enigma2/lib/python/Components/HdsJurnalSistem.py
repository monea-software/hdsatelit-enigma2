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
# Ceasul e pe firul principal, dar citirile merg pe un fir separat (FRD, pachetul 2186: listdir pe /sys/class/net a tinut
# interfata 3,7 s; citirile retelei din /sys asteapta lacatul retelei din nucleu cat lucreaza driverul, iar statvfs un
# disc care se trezeste). O verificare noua nu porneste cat cea de dinainte inca lucreaza. HdsJurnal scrie din orice fir.

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
_lucreaza = [False]
_retea = {}
_reconectari = {}
_discuri = {}
_avertizat_liber = {}
_paza_cazuta = [False]


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
				nivel = int(float(p[3].rstrip(".")))
				if 128 <= nivel <= 255:
					nivel -= 256
				return nivel if -120 <= nivel < 0 else None
			except ValueError:
				return None
	return None


def _wifi_calitate(iface, proc="/proc/net/wireless"):
	"""Calitatea data de driver, fara conversie presupusa in dBm."""
	for rand in _citeste(proc).splitlines()[2:]:
		p = rand.replace(":", " ").split()
		if len(p) >= 3 and p[0] == iface:
			try:
				v = int(float(p[2].rstrip(".")))
				return v if 0 <= v <= 100 else None
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
			modul = os.path.basename(os.path.realpath(os.path.join(d, "device/driver/module"))).lower()
			if modul in ("mt7601usta", "mt7650u_sta"):
				s["calitate"] = _wifi_calitate(i)
			else:
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
	if s.get("calitate") is not None:
		parti.append("calitate Wi-Fi %d%%" % s["calitate"])
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
		elif s.get("calitate") is not None and v.get("calitate") is not None and abs(s["calitate"] - v["calitate"]) >= 10:
			HdsJurnal.info("retea", "wifi", "%s calitate Wi-Fi %d%% (era %d%%)" % (i, s["calitate"], v["calitate"]))
		else:
			if s.get("dbm") is not None and v.get("dbm") is not None:
				s["dbm"] = v["dbm"]  # se compara cu ultimul scris
			if s.get("calitate") is not None and v.get("calitate") is not None:
				s["calitate"] = v["calitate"]
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


# Memoria interna (/): sub PRAG_LIBER_PROCENTE sau sub LIBER_MINIM_MB liberi, omul vede un anunt (o data pe zi si la
# pornire) pe ecran si o banda in web, cu cat e liber si ce ocupa locul. Fara intrebari si fara stergeri singure
# (AS198, 25.11.2026: / plin 95% si nimic pe ecran; cererea din 13.11: mesaj pe ecran cand / e aproape plin).
LIBER_MINIM_MB = 50
DURATA_ANUNT_MS = 15000


def N_(text):
	"""Numai marcajul pentru traduceri; textul se traduce la afisare (_t)."""
	return text


# locurile pe care omul le poate curata singur, cu numele lor pentru anunt (cele mai mari trei intra in text)
LOCURI_MARI = (
	("/usr/lib/enigma2/python/Plugins/Extensions", N_("pluginurile")),
	("/usr/share/enigma2/picon", N_("siglele canalelor")),
	("/picon", N_("siglele canalelor")),
	("/home/root", N_("fișierele din /home/root")),
	("/var/cache/opkg", N_("pachetele descărcate")),
)
TEXT_ANUNT_SPATIU = N_("Memoria internă a receptorului e aproape plină: mai sunt liberi %s din %s.")
TEXT_ANUNT_OCUPA = N_("Ocupă cel mai mult: %s.")
TEXT_ANUNT_STERGE = N_("Șterge ce nu mai folosești (pluginurile din Meniu > Extensii, sigle sau fișiere vechi), ca receptorul să meargă bine.")
_spatiu_intern = {"zi": None, "de_aratat": None, "text": None, "avertizat": 0}


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _mb(octeti):
	return ("%.0f MB" % (octeti / 1e6)) if octeti < 1e9 else ("%.1f GB" % (octeti / 1e9))


def _marimeDosar(cale, maxim=200000):
	"""Octetii fisierelor de sub cale, fara legaturi si fara alte montari (un stick legat in /picon nu se numara)."""
	total = 0
	vazute = 0
	if os.path.islink(cale) or not os.path.isdir(cale) or os.path.ismount(cale):
		return 0
	for rad, dosare, fisiere in os.walk(cale):
		dosare[:] = [d for d in dosare if not os.path.islink(os.path.join(rad, d)) and
			not os.path.ismount(os.path.join(rad, d))]
		for f in fisiere:
			vazute += 1
			if vazute > maxim:
				return total
			try:
				st = os.lstat(os.path.join(rad, f))
				total += st.st_size
			except OSError:
				pass
	return total


def textAnuntSpatiu(liber, total, locuri):
	"""locuri = [(nume tradus, octeti)], cele mai mari intai."""
	text = _t(TEXT_ANUNT_SPATIU) % (_mb(liber), _mb(total))
	mari = ["%s %s" % (nume, _mb(oct_)) for nume, oct_ in locuri[:3] if oct_ >= 1e6]
	if mari:
		text += " " + _t(TEXT_ANUNT_OCUPA) % ", ".join(mari)
	return text + " " + _t(TEXT_ANUNT_STERGE)


def verificaMemoriaInterna(acum=None, statvfs=None, marime=None, punct="/"):
	"""Pe firul verificarii (nu pe firul interfetei): statvfs pe /; sub prag, randul de jurnal (cel mult unul pe ora) si,
	o data pe zi, anuntul pus deoparte pentru firul interfetei (anuntSpatiuDeAratat). -> textul anuntului sau None."""
	acum = time.time() if acum is None else acum
	statvfs = statvfs or os.statvfs
	marime = marime or _marimeDosar
	try:
		st = statvfs(punct)
		total = st.f_blocks * st.f_frsize
		liber = st.f_bavail * st.f_frsize
	except (OSError, AttributeError):
		return None
	if not total or (liber * 100 >= total * PRAG_LIBER_PROCENTE and liber >= LIBER_MINIM_MB * 1000000):
		_spatiu_intern["text"] = None
		_spatiu_intern["de_aratat"] = None
		return None
	if acum - _spatiu_intern["avertizat"] >= 3600:
		_spatiu_intern["avertizat"] = acum
		HdsJurnal.avert("discuri", "spatiu", "memoria interna (/) aproape plina: liber %s din %s" % (_mb(liber), _mb(total)))
	zi = time.strftime("%Y-%m-%d", time.localtime(acum))
	if _spatiu_intern["zi"] == zi and _spatiu_intern["text"]:
		return None
	locuri = {}
	for cale, nume in LOCURI_MARI:
		locuri[nume] = locuri.get(nume, 0) + marime(cale)
	ordonate = sorted(((_t(n), o) for n, o in locuri.items()), key=lambda x: -x[1])
	text = textAnuntSpatiu(liber, total, ordonate)
	if _spatiu_intern["zi"] == zi:
		# azi a fost deja pe ecran (locul s-a eliberat si s-a umplut iar): numai banda din web
		_spatiu_intern["text"] = text
		return None
	_spatiu_intern.update(zi=zi, text=text, de_aratat=text)
	return text


def anuntSpatiu():
	"""Textul anuntului cat / e sub prag (banda din web, fara citiri de disc: starea verificarii de la 30 s), altfel ""."""
	return _spatiu_intern["text"] or ""


def anuntSpatiuDeAratat():
	"""Pe firul interfetei: anuntul datorat azi (o singura data), apoi None."""
	text = _spatiu_intern["de_aratat"]
	_spatiu_intern["de_aratat"] = None
	return text


def _arataAnuntSpatiu():
	"""Din ceasul firului principal: anuntul pe ecran, ca anunturile retelei (Screens/HdsAnuntRetea), nu in standby."""
	if not _spatiu_intern["de_aratat"]:
		return
	try:
		from Screens import Standby
		if Standby.inStandby is not None:
			return
		from Screens.InfoBar import InfoBar
		if InfoBar.instance is None:
			return
		text = anuntSpatiuDeAratat()
		from Screens import HdsAnuntRetea
		HdsAnuntRetea.arata(InfoBar.instance.session, text, "", DURATA_ANUNT_MS)
	except Exception as e:
		HdsJurnal.avert("discuri", "spatiu", "anuntul memoriei interne: %r" % (e,))


def _tic():
	stare = None
	try:
		stare = stareRetea()
		verificaReteaua(stare)
	except Exception:
		pass
	# paznicul Wi-Fi (Components/HdsPazaWifi.py): o placa Wi-Fi USB ramasa fara legatura isi porneste cipul din nou; cu
	# starea citita deja aici, pe acest fir
	if stare is not None:
		try:
			from Components import HdsPazaWifi
			HdsPazaWifi.tic(stare)
		except Exception as e:
			# o data: un paznic stricat nu trebuie sa arate in jurnal la fel ca unul care nu are nimic de facut
			if not _paza_cazuta[0]:
				_paza_cazuta[0] = True
				HdsJurnal.avert("retea", "wifi", "paznicul Wi-Fi a cazut: %r" % (e,))
	try:
		verificaDiscurile()
	except Exception:
		pass
	try:
		verificaMemoriaInterna()
	except Exception:
		pass


def _porneste_fir(tinta):
	"""Un fir nou, fara asteptarea pornirii lui (ca Hds/DabT2/fundal.py). Probele il pot inlocui."""
	try:
		import _thread as fire
	except ImportError:  # Python 2.7
		import thread as fire
	fire.start_new_thread(tinta, ())


def _verificare():
	try:
		_tic()
	finally:
		_lucreaza[0] = False


def _tic_in_fundal():
	"""Din ceasul firului principal: verificarea pe un fir; nimic, daca cea de dinainte inca lucreaza. Anuntul
	memoriei interne pus deoparte de verificarea de dinainte se arata aici, pe firul interfetei."""
	_arataAnuntSpatiu()
	if _lucreaza[0]:
		return
	_lucreaza[0] = True
	try:
		_porneste_fir(_verificare)
	except Exception:
		_lucreaza[0] = False


def porneste():
	if _ceas[0] is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		_ceas[0] = False
		return
	t = eTimer()
	t.callback.append(_tic_in_fundal)
	t.start(PAUZA_S * 1000, False)
	_ceas[0] = t
	_tic_in_fundal()
