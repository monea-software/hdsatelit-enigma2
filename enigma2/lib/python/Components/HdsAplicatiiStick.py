# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
#
# NAV8 (0.8.0, Eduard 26.11.2026 07:50: „Pai nu poate sa instaleze pe stick sau hdd extern?”): aplicatiile mari (acum navigatorul
# web) se instaleaza pe un stick sau pe un disc USB cand nu incap in memoria interna (ZGEMMA H8: rootfs-ul are ~173 MB liberi,
# navigatorul cere ~170). Cum fac si imaginile OE-Alliance la „install to USB”: opkg cu o destinatie a lui (opkg install -d),
# apoi legaturi din memoria interna spre fisierele de pe stick (ca ipkg-link / GNU stow), ca programul sa porneasca de unde il
# cauta (/usr/bin, /usr/lib, /usr/libexec, /usr/share). Stickul trebuie sa aiba un sistem de fisiere cu legaturi si drepturi
# (ext2/3/4 si celelalte de Linux); pe FAT32, exFAT sau NTFS pachetele nu se pot desface.
#
# Totul trece printr-o SINGURA legatura stabila in memoria interna, RADACINA (/etc/hds-stick/radacina -> <stick>/hds-aplicatii):
# destinatia opkg, listele pachetelor si toate legaturile din /usr numesc calea stabila, deci un stick montat altundeva data
# viitoare (/media/usb in loc de /media/hdd; /media e tmpfs pe multe imagini) se leaga iar schimband numai acea legatura.
# Stickul e recunoscut dupa fisierul hds/id (acelasi numar si in /etc/hds-stick/id). Fara stick, legaturile raman fara tinta
# (Enigma2 nu le foloseste; navigatorul e un proces separat) si destinatia opkg se scoate, ca actualizarile sa nu scrie nimic.
# Separat de partea a doua a lui Vu+ Solo SE (Components/HdsParteaDoua: alta destinatie, alt inventar, alte fisiere).
import os
import posixpath
import re
import subprocess
import time

DOSAR = "etc/hds-stick"
RADACINA = "etc/hds-stick/radacina"          # legatura stabila spre <stick>/hds-aplicatii
FISIER_ID = "etc/hds-stick/id"
FISIER_LEGATURI = "etc/hds-stick/legaturi"
OPKG_CONF = "etc/opkg/hds-stick.conf"
DEST = "hdsstick"
DOSAR_STICK = "hds-aplicatii"
# sistemele de fisiere pe care opkg poate desface pachetele (legaturile bibliotecilor, bitul de executie)
FS_BUNE = ("ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "jfs", "reiserfs", "nilfs2")
FS_FARA_LEGATURI = ("vfat", "msdos", "exfat", "fuseblk", "ntfs", "ntfs3")
DISPOZITIV_USB = r"^/dev/sd[a-z]+[0-9]*$"
# numai aceste radacini se leaga; /etc numai fisierele care nu exista (configurarea bazei ramane a bazei)
RADACINI = ("usr/", "etc/")
REZERVA_STICK_MIB = 64
# in memoria interna ramane loc pentru setari, lista de canale, ghid si actualizari (H8: „lasam loc pentru setari”)
REZERVA_INTERN_MIB = 64
# unde merge instalarea (planLoc)
INTERN, STICK, FARA_STICK, STICK_LIPSA = "intern", "stick", "fara-stick", "stick-lipsa"


def _c(rad, rel):
	return os.path.join(rad or "/", *rel.split("/"))


def _caleStabila():
	return "/" + RADACINA


def _decodeaza(text):
	return text.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def montari(rad=None):
	rez = []
	try:
		with open(_c(rad, "proc/mounts"), encoding="utf-8", errors="replace") as f:
			for rand in f:
				p = rand.split()
				if len(p) >= 4:
					rez.append((_decodeaza(p[0]), _decodeaza(p[1]), p[2], p[3]))
	except (IOError, OSError):
		pass
	return rez


def liberMib(cale):
	try:
		s = os.statvfs(cale)
	except (OSError, AttributeError):
		return -1
	return s.f_bavail * s.f_frsize // (1024 * 1024)


def _stocari(rad=None):
	"""[(dispozitiv, punct, fs, rw)]: stickurile si discurile USB/SATA externe montate in /media sau /run/media, o data pe
	dispozitiv (punctul din /media intai: /media/hdd e numele vazut de om)"""
	pe_disp = {}
	for disp, punct, fs, opt in montari(rad):
		if not re.match(os.environ.get("HDS_STICK_DISPOZITIV") or DISPOZITIV_USB, disp):
			continue
		if not (punct.startswith("/media/") or punct.startswith("/run/media/")):
			continue
		rw = "ro" not in opt.split(",")
		vechi = pe_disp.get(disp)
		if vechi is None or (vechi[1].startswith("/run/") and punct.startswith("/media/")):
			pe_disp[disp] = (disp, punct, fs, rw)
	return sorted(pe_disp.values(), key=lambda x: x[1])


def locuri(rad=None, liber=None):
	"""Stocarile pe care se poate instala: [{punct, fs, liber_mib, dispozitiv}], cel mai mult loc intai. `liber` (teste)
	inlocuieste statvfs."""
	rez = []
	for disp, punct, fs, rw in _stocari(rad):
		if fs not in FS_BUNE or not rw:
			continue
		cale = _c(rad, punct.lstrip("/"))
		l = liber(cale) if liber else liberMib(cale)
		if l < 0:
			continue
		rez.append({"punct": punct, "fs": fs, "liber_mib": l, "dispozitiv": disp})
	rez.sort(key=lambda x: -x["liber_mib"])
	return rez


def numeFs(fs):
	"""numele sistemului de fisiere asa cum il stie omul"""
	return {"vfat": "FAT32", "msdos": "FAT", "exfat": "exFAT", "fuseblk": "NTFS", "ntfs": "NTFS", "ntfs3": "NTFS"}.get(fs, fs)


def stocariFaraLegaturi(rad=None):
	"""Stickurile puse care nu se pot folosi pentru aplicatii (FAT32, exFAT, NTFS): [{punct, fs}]"""
	return [{"punct": p, "fs": fs} for _d, p, fs, _rw in _stocari(rad) if fs in FS_FARA_LEGATURI]


def _citeste(cale):
	try:
		with open(cale, encoding="utf-8") as f:
			return f.read().strip()
	except (IOError, OSError):
		return ""


def idLegat(rad=None):
	v = _citeste(_c(rad, FISIER_ID))
	return v if re.match(r"^[A-Za-z0-9-]{8,64}$", v) else ""


def gasesteStick(rad=None):
	"""Punctul de montare al stickului legat (cel cu hds-aplicatii/hds/id = /etc/hds-stick/id), sau "" """
	ident = idLegat(rad)
	if not ident:
		return ""
	for _d, punct, _fs, _rw in _stocari(rad):
		if _citeste(os.path.join(_c(rad, punct.lstrip("/")), DOSAR_STICK, "hds", "id")) == ident:
			return punct
	return ""


def _scrieAtomic(cale, text):
	os.makedirs(os.path.dirname(cale), exist_ok=True)
	nou = cale + ".nou"
	with open(nou, "w", encoding="utf-8", newline="\n") as f:
		f.write(text)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


def _scrieDacaAltfel(cale, text):
	if _citeste(cale) == text.strip():
		return False
	_scrieAtomic(cale, text)
	return True


def _legaturaStabila(rad, punct):
	"""RADACINA -> <punct>/hds-aplicatii (schimbata numai cand e alta; atomic, prin rename)"""
	cale = _c(rad, RADACINA)
	# relativa (../../media/hdd/hds-aplicatii): duce la acelasi loc si intr-o radacina de proba sau de copie
	tinta = posixpath.relpath(punct.rstrip("/") + "/" + DOSAR_STICK, "/" + posixpath.dirname(RADACINA))
	try:
		if os.readlink(cale) == tinta:
			return False
	except OSError:
		pass
	os.makedirs(os.path.dirname(cale), exist_ok=True)
	nou = cale + ".nou"
	if os.path.lexists(nou):
		os.remove(nou)
	os.symlink(tinta, nou)
	os.replace(nou, cale)
	return True


def puneDestinatiaOpkg(rad, pornita):
	cale = _c(rad, OPKG_CONF)
	if pornita:
		return _scrieDacaAltfel(cale, "# HD Satelit: aplicatiile instalate pe stick (numai cat stickul e pus)\n"
			"dest %s %s\n" % (DEST, _caleStabila()))
	if os.path.lexists(cale):
		os.remove(cale)
		return True
	return False


def _idNou():
	try:
		with open("/proc/sys/kernel/random/uuid") as f:
			return f.read().strip()
	except (IOError, OSError):
		import random
		return "%08x-%04x-%04x" % (random.getrandbits(32), random.getrandbits(16), random.getrandbits(16))


def leaga(punct, rad=None):
	"""Pregateste stickul de la `punct` (dosarul hds-aplicatii si numarul lui) si il leaga de receptor. Daca un stick e deja
	legat si e pus, il pastreaza pe acela. (bine, punct sau mesaj)"""
	vechi = gasesteStick(rad)
	if vechi:
		_legaturaStabila(rad, vechi)
		puneDestinatiaOpkg(rad, True)
		return True, vechi
	if not any(l["punct"] == punct for l in locuri(rad)):
		return False, "stocarea %s nu se poate folosi (lipseste, e numai pentru citire sau nu are legaturi)" % punct
	d = os.path.join(_c(rad, punct.lstrip("/")), DOSAR_STICK)
	ident = _citeste(os.path.join(d, "hds", "id"))
	if not re.match(r"^[A-Za-z0-9-]{8,64}$", ident):
		ident = _idNou()
		_scrieAtomic(os.path.join(d, "hds", "id"), ident + "\n")
	_scrieAtomic(_c(rad, FISIER_ID), ident + "\n")
	_legaturaStabila(rad, punct)
	puneDestinatiaOpkg(rad, True)
	return True, punct


# ---------------------------------------------------------------- pachetele de pe stick si legaturile

def _dosarOpkg(rad):
	return os.path.join(_c(rad, RADACINA), "var", "lib", "opkg")


def instalate(rad=None):
	"""{nume: versiune} din status-ul destinatiei de pe stick (gol fara stick)"""
	rez = {}
	try:
		with open(os.path.join(_dosarOpkg(rad), "status"), encoding="utf-8", errors="replace") as f:
			strofe = f.read().split("\n\n")
	except (IOError, OSError):
		return rez
	for s in strofe:
		d = {}
		for rand in s.splitlines():
			k, _sep, v = rand.partition(":")
			if _sep and not rand.startswith(" "):
				d[k.strip().lower()] = v.strip()
		st = d.get("status", "").split()
		if d.get("package") and "installed" in st and "not-installed" not in st:
			rez[d["package"]] = d.get("version", "")
	return rez


def fisiereDestinatie(rad=None):
	"""{cale relativa: pachet} pentru fisierele (si legaturile) pachetelor de pe stick, numai sub RADACINI"""
	info = os.path.join(_dosarOpkg(rad), "info")
	rez = {}
	try:
		nume = sorted(n for n in os.listdir(info) if n.endswith(".list"))
	except OSError:
		return rez
	prefix = _caleStabila().rstrip("/") + "/"
	baza = _c(rad, RADACINA)
	for n in nume:
		try:
			with open(os.path.join(info, n), encoding="utf-8", errors="replace") as f:
				randuri = f.read().splitlines()
		except (IOError, OSError):
			continue
		for r in randuri:
			r = r.split("\t", 1)[0].strip()
			if not r.startswith(prefix):
				continue
			r = r[len(prefix):]
			if not r or ".." in r.split("/") or not r.startswith(RADACINI):
				continue
			p = os.path.join(baza, *r.split("/"))
			if os.path.isdir(p) and not os.path.islink(p):
				continue
			rez.setdefault(r, n[:-5])
	return rez


def _tinta(rel):
	return _caleStabila().rstrip("/") + "/" + rel


def _aNoastra(cale, tinta):
	try:
		return os.path.islink(cale) and os.readlink(cale) == tinta
	except OSError:
		return False


def _peStick(cale, rad=None):
	"""True cand `cale` (o cale din memoria interna) duce, prin legaturi, in dosarul de pe stick"""
	try:
		r = os.path.realpath(cale)
		s = os.path.realpath(_c(rad, RADACINA))
	except OSError:
		return False
	return r == s or r.startswith(s.rstrip("/") + "/")


def citesteInventar(rad=None):
	rez = {}
	try:
		with open(_c(rad, FISIER_LEGATURI), encoding="utf-8") as f:
			for rand in f:
				p = rand.rstrip("\n").split("\t")
				if len(p) == 2 and p[0] and p[1]:
					rez[p[0]] = p[1]
	except (IOError, OSError):
		pass
	return rez


def _scrieInventar(rad, inv):
	_scrieDacaAltfel(_c(rad, FISIER_LEGATURI), "".join("%s\t%s\n" % (k, inv[k]) for k in sorted(inv)))


def legaturiDorite(rad=None, inventar=None):
	"""({cale: tinta}, [conflicte]): pentru fiecare fisier de pe stick, cel mai inalt dosar care nu exista in memoria interna
	(sau e deja legatura noastra); cand toti parintii exista ca dosare ale bazei, fisierul insusi. O cale ocupata de baza
	(fisier sau legatura straina) e conflict: fisierul bazei ramane, nu il acopar."""
	inventar = inventar or {}
	dorite, conflicte = {}, []
	for rel in sorted(fisiereDestinatie(rad)):
		parti = rel.split("/")
		for i in range(2, len(parti) + 1):
			p = "/".join(parti[:i])
			if p in dorite:
				break
			full = _c(rad, p)
			t = _tinta(p)
			if not os.path.lexists(full) or _aNoastra(full, t) or (p in inventar and _aNoastra(full, inventar[p])):
				dorite[p] = t
				break
			if i < len(parti) and os.path.isdir(full) and not _peStick(full, rad):
				continue
			conflicte.append(p)
			break
	return dorite, sorted(set(conflicte))


def reconciliaza(rad=None, numai_scoate=False):
	"""Aduce legaturile din memoria interna la listele pachetelor de pe stick. Scoate numai legaturile din inventar care
	sunt inca ale noastre. {"puse", "scoase", "conflicte"}"""
	inv = citesteInventar(rad)
	dorite, conflicte = ({}, []) if numai_scoate else legaturiDorite(rad, inv)
	puse, scoase = [], []
	for rel in sorted(inv, key=lambda x: -x.count("/")):
		if dorite.get(rel) == inv[rel]:
			continue
		full = _c(rad, rel)
		if _aNoastra(full, inv[rel]):
			os.remove(full)
			scoase.append(rel)
		del inv[rel]
	for rel in sorted(dorite, key=lambda x: x.count("/")):
		full = _c(rad, rel)
		if _aNoastra(full, dorite[rel]):
			inv[rel] = dorite[rel]
			continue
		parinte = os.path.dirname(full)
		if os.path.lexists(full) or not os.path.isdir(parinte) or _peStick(parinte, rad):
			conflicte.append(rel)
			continue
		os.symlink(dorite[rel], full)
		inv[rel] = dorite[rel]
		puse.append(rel)
	_scrieInventar(rad, inv)
	return {"puse": puse, "scoase": scoase, "conflicte": sorted(set(conflicte))}


def _ruleaza(argv, timp=120):
	try:
		return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timp).returncode
	except (OSError, subprocess.SubprocessError):
		return -1


def dupaInstalare(rad=None):
	"""Dupa opkg install -d: legaturile, apoi cache-ul bibliotecilor si al fonturilor (scripturile pachetelor au rulat
	inainte ca legaturile sa existe)"""
	r = reconciliaza(rad)
	if not rad or rad == "/":
		if os.access("/sbin/ldconfig", os.X_OK):
			_ruleaza(["/sbin/ldconfig"], 120)
		if os.access("/usr/bin/fc-cache", os.X_OK):
			_ruleaza(["/usr/bin/fc-cache", "-s"], 300)
	return r


def repara(rad=None):
	"""La pornirea interfetei si la fiecare stick pus sau scos: leaga stickul cu aplicatii (oriunde e montat acum), pune
	destinatia opkg si legaturile; fara stick scoate destinatia opkg. Intoarce FARA (nimic pe stick), STICK sau STICK_LIPSA.
	Nu arunca."""
	try:
		if not idLegat(rad):
			puneDestinatiaOpkg(rad, False)
			return "fara"
		punct = gasesteStick(rad)
		if not punct:
			puneDestinatiaOpkg(rad, False)
			return STICK_LIPSA
		_legaturaStabila(rad, punct)
		puneDestinatiaOpkg(rad, True)
		reconciliaza(rad)
		return STICK
	except Exception as e:
		print("[HdsAplicatiiStick] repara: %r" % (e,))
		return "eroare"


def peStickLipsa(pachet, rad=None):
	"""True cand `pachet` a fost instalat pe stickul legat, iar stickul nu e pus acum (legaturile lui duc nicaieri)"""
	if not idLegat(rad) or gasesteStick(rad):
		return False
	# inventarul legaturilor ramane in memoria interna: programul (usr/bin/<pachet>) e o legatura noastra spre stick
	rel = "usr/bin/" + pachet
	return citesteInventar(rad).get(rel, "").startswith(_caleStabila() + "/")


def gbNecesari(trebuie_octeti):
	"""Cati GB cel putin trebuie sa aiba stickul (rotunjit in sus, minim 1)"""
	mib = trebuie_octeti // (1024 * 1024) + REZERVA_STICK_MIB
	return max(1, (mib + 1023) // 1024)


def planLoc(trebuie_octeti, rad=None, liber_intern=None, liber=None):
	"""Unde se instaleaza o aplicatie de `trebuie_octeti` (desfacuta): {"unde": INTERN / STICK / FARA_STICK / STICK_LIPSA,
	"punct": stickul ales, "liber_intern_mib", "liber_stick_mib", "trebuie_mib", "gb": GB necesari pe stick, "fara_legaturi":
	stickurile FAT32/NTFS puse}. Acelasi raspuns pentru cardul de pe televizor, pagina web si instalare."""
	trebuie_mib = trebuie_octeti // (1024 * 1024) + 1
	if liber_intern is None:
		liber_intern = liberMib(_c(rad, ""))
	d = {"unde": FARA_STICK, "punct": "", "liber_intern_mib": liber_intern, "liber_stick_mib": -1,
		"trebuie_mib": trebuie_mib, "gb": gbNecesari(trebuie_octeti), "fara_legaturi": stocariFaraLegaturi(rad)}
	if idLegat(rad):
		# aplicatiile merg pe acelasi stick cu cele de dinainte (unul singur, ca legaturile sa ramana simple)
		punct = gasesteStick(rad)
		if not punct:
			d["unde"] = STICK_LIPSA
			return d
		l = liber(_c(rad, punct.lstrip("/"))) if liber else liberMib(_c(rad, punct.lstrip("/")))
		d.update(punct=punct, liber_stick_mib=l)
		d["unde"] = STICK if l >= trebuie_mib + REZERVA_STICK_MIB else FARA_STICK
		return d
	if liber_intern < 0 or liber_intern >= trebuie_mib + REZERVA_INTERN_MIB:
		d["unde"] = INTERN
		return d
	for l in locuri(rad, liber):
		if l["liber_mib"] >= trebuie_mib + REZERVA_STICK_MIB:
			d.update(unde=STICK, punct=l["punct"], liber_stick_mib=l["liber_mib"])
			return d
	return d
