# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Motorul comun pentru limbile suplimentare pe stick.
# Baza ramane in NAND. Nu sterge fisierele omului si nu muta /usr.
# Feedul, indexurile si toate pachetele se verifica inainte de opkg.
import json
import hashlib
import os
import random
import re
import subprocess
import sys
import time
import threading
import io
import tarfile

def N_(text):
	return text


CONF = "etc/hdsatelit-partea-doua.conf"
DOSAR_NAND = "etc/hdsatelit-partea-doua"
FISIER_ID = "id"
FISIER_LEGATURI = "legaturi"
OPKG_CONF = "etc/opkg/hdsatelit-partea-doua.conf"
STARE = "tmp/hdsatelit-partea-doua.stare"
FISIER = "hdsatelit-partea-doua.img"
DEST = "partea2"
MONTARE_IMPLICIT = "media/hds-partea-doua"
# numai aceste radacini se leaga (baza: programele, bibliotecile, datele, Enigma2); /etc ramane al bazei in
# faza 1
RADACINI = ("usr/",)
REZERVA_MIB = 64
FS_STICK = ("vfat", "msdos", "exfat", "fuseblk", "ext2", "ext3", "ext4", "ntfs", "ntfs3")
# discurile USB (si SATA extern) apar ca /dev/sdX; memoria interna e mtd/ubi sau mmcblk, deci nu intra
# niciodata
DISPOZITIV_USB = r"^/dev/sd[a-z]+[0-9]*$"
# starile (STARE, citite de Enigma2 si de web)
NEDESCRIS = "nedescris"      # modelul nu are descrierea partii a doua: componenta nu face nimic
NELEGAT = "nelegat"          # niciun stick legat (ca pana acum)
LEGAT = "legat"              # stickul legat e montat si legaturile sunt la zi
LIPSESTE = "lipseste"        # e un stick legat, dar nu l-am gasit la pornire
STRICAT = "stricat"          # fisierul de pe stick nu trece de e2fsck sau nu se monteaza
REFUZURI = "refuzuri.json"
MESAJ_LIPSA = N_("Stickul cu partea a doua lipseste. Limbile de pe el nu sunt disponibile acum. Pune stickul si reporneste receptorul.")
MESAJ_LIMITA = N_("Acum sunt disponibile limbile. Navigatorul si recunoasterea textului nu sunt inca disponibile pentru acest model.")


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def radacinaNand(radacina=None):
	"""Numai o radacina NAND cunoscuta poate primi extensia pe stick."""
	try:
		from Components.HdsRadacinaUsb import radacinaNand as verifica
	except ImportError:
		from HdsRadacinaUsb import radacinaNand as verifica
	return verifica(radacina or "/")


def _cale(radacina, rel):
	return os.path.join(radacina or "/", rel)


def radacinaImplicita():
	return os.environ.get("HDS_PARTEA_DOUA_RADACINA") or "/"


def citesteConf(radacina=None):
	"""Descrierea modelului ({cheie: valoare}) sau None cand modelul nu o are (componenta nu face nimic)"""
	try:
		with open(_cale(radacina, CONF), encoding="utf-8") as f:
			text = f.read()
	except (IOError, OSError):
		return None
	c = {}
	for rand in text.splitlines():
		rand = rand.strip()
		if not rand or rand.startswith("#") or "=" not in rand:
			continue
		k, v = rand.split("=", 1)
		c[k.strip()] = v.strip()
	for k, implicit in (("PRAG_MIB", "150"), ("MARIME_MIB", "1024"), ("ASTEAPTA_S", "10"), ("MONTARE", "/" + MONTARE_IMPLICIT)):
		c.setdefault(k, implicit)
	if not c.get("PACHET") or not c.get("SABLON"):
		return None
	return c


def _int(v, implicit=0):
	try:
		return int(v)
	except (TypeError, ValueError):
		return implicit


def montare(conf):
	return (conf or {}).get("MONTARE") or "/" + MONTARE_IMPLICIT


def _relMontare(conf):
	return montare(conf).lstrip("/")


# ---------------------------------------------------------------- memoria interna si stickurile

def liberMib(cale):
	try:
		s = os.statvfs(cale)
	except (OSError, AttributeError):
		return -1
	return s.f_bavail * s.f_frsize // (1024 * 1024)


def _decodeazaMount(text):
	return text.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def montari(radacina=None):
	"""[(dispozitiv, punct, fs, optiuni)] din /proc/mounts"""
	rez = []
	try:
		with open(_cale(radacina, "proc/mounts"), encoding="utf-8", errors="replace") as f:
			for rand in f:
				p = rand.split()
				if len(p) >= 4:
					rez.append((_decodeazaMount(p[0]), _decodeazaMount(p[1]), p[2], p[3]))
	except (IOError, OSError):
		pass
	return rez


def candidati(radacina=None, conf=None, exclus=(), liber=None):
	"""Stickurile pe care se poate pune partea a doua: montate sub /media dintr-un dispozitiv USB de tip disc (/dev/sdX),
	cu scriere, cu sistem de fisiere cunoscut, cu loc liber >= MARIME_MIB + REZERVA_MIB, fara fisierul partii a doua deja
	(nu se suprascrie nimic) si fara punctele din `exclus` (de pilda dosarul inregistrarilor). `liber` (teste) inlocuieste
	statvfs. [{punct, liber_mib, fs, dispozitiv}] dupa locul liber, cel mai mare intai."""
	conf = conf or citesteConf(radacina) or {}
	if not radacinaNand(radacina):
		return []
	nevoie = _int(conf.get("MARIME_MIB"), 1024) + REZERVA_MIB
	m = montare(conf)
	rez = []
	vazute = set()
	for disp, punct, fs, opt in montari(radacina):
		if not punct.startswith("/media/") or punct.rstrip("/") == m.rstrip("/") or punct in vazute:
			continue
		# HDS_PARTEA_DOUA_DISPOZITIV: numai pentru proba din container, unde "stickul" e un fisier loop
		if not re.match(os.environ.get("HDS_PARTEA_DOUA_DISPOZITIV") or DISPOZITIV_USB, disp) or fs not in FS_STICK:
			continue
		if not os.environ.get("HDS_PARTEA_DOUA_DISPOZITIV") and not dispozitivUsb(disp, radacina):
			continue
		if "ro" in opt.split(","):
			continue
		if any(punct.rstrip("/") == e.rstrip("/") or punct.startswith(e.rstrip("/") + "/") or
				e.startswith(punct.rstrip("/") + "/") for e in exclus if e):
			continue
		cale = _cale(radacina, punct.lstrip("/"))
		if os.path.lexists(os.path.join(cale, FISIER)):
			continue
		l = liber(cale) if liber else liberMib(cale)
		if l < nevoie:
			continue
		vazute.add(punct)
		cod, ident = _ruleaza(["blkid", "-s", "UUID", "-o", "value", disp], 5)
		if cod != 0 or not re.match(r"^[A-Za-z0-9-]{4,64}$", ident.strip()):
			continue
		rez.append({"punct": punct, "liber_mib": l, "fs": fs,
			"dispozitiv": disp, "ident": ident.strip()})
	rez.sort(key=lambda x: -x["liber_mib"])
	return rez


def dispozitivUsb(disp, radacina=None):
	if not re.match(DISPOZITIV_USB, disp):
		return False
	cale = _cale(radacina, "sys/class/block/" + os.path.basename(disp))
	return any(re.match(r"usb[0-9]+$", p) for p in os.path.realpath(cale).replace("\\", "/").split("/"))


def fisiereGasite(radacina=None, conf=None):
	"""Caile (cu radacina) ale fisierelor hdsatelit-partea-doua.img de pe stickurile montate"""
	m = montare(conf)
	rez = []
	for disp, punct, fs, opt in montari(radacina):
		if not punct.startswith("/media/") or punct.rstrip("/") == m.rstrip("/"):
			continue
		if not dispozitivUsb(disp, radacina) and not os.environ.get("HDS_PARTEA_DOUA_DISPOZITIV"):
			continue
		c = os.path.join(_cale(radacina, punct.lstrip("/")), FISIER)
		if os.path.isfile(c) and c not in rez:
			rez.append(c)
	return rez


# ---------------------------------------------------------------- starea in memoria interna

def idLegat(radacina=None):
	try:
		with open(os.path.join(_cale(radacina, DOSAR_NAND), FISIER_ID), encoding="utf-8") as f:
			v = f.read().strip()
	except (IOError, OSError):
		return ""
	return v if re.match(r"^[A-Za-z0-9-]{8,64}$", v) else ""


def _scrieAtomic(cale, text):
	os.makedirs(os.path.dirname(cale), exist_ok=True)
	nou = cale + ".nou"
	with open(nou, "w", encoding="utf-8", newline="\n") as f:
		f.write(text)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


def _scrieDacaAltfel(cale, text):
	"""Scrie numai daca s-a schimbat (memoria NAND: fara scrieri la fiecare pornire)"""
	try:
		with open(cale, encoding="utf-8") as f:
			if f.read() == text:
				return False
	except (IOError, OSError):
		pass
	_scrieAtomic(cale, text)
	return True


def scrieStare(radacina, stare, **detalii):
	d = dict(detalii, stare=stare, ora=int(time.time()))
	try:
		_scrieAtomic(_cale(radacina, STARE), json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
	except (IOError, OSError):
		pass
	return d


def citesteStare(radacina=None):
	try:
		with open(_cale(radacina, STARE), encoding="utf-8") as f:
			d = json.loads(f.read())
		return d if isinstance(d, dict) else {}
	except (IOError, OSError, ValueError):
		return {}


def esteMontat(radacina=None, conf=None):
	m = montare(conf).rstrip("/")
	return any(p.rstrip("/") == m for _d, p, _f, _o in montari(radacina))


def puneDestinatiaOpkg(radacina, conf, pornita):
	"""Destinatia opkg numai cat fisierul e montat; altfel o scoate (opkg nu are unde scrie in NAND)"""
	cale = _cale(radacina, OPKG_CONF)
	if pornita:
		return _scrieDacaAltfel(cale, "# HD Satelit: partea a doua a imaginii, pe stick (numai cat e montata)\n"
			"dest %s %s\n" % (DEST, montare(conf)))
	if os.path.lexists(cale):
		os.remove(cale)
		return True
	return False


# ---------------------------------------------------------------- legaturile (ca GNU stow)

def fisiereDestinatie(radacina, conf):
	"""Caile relative (fara montare) ale fisierelor pachetelor din destinatie, din listele opkg ale ei, numai sub
	RADACINI; {cale: pachet}"""
	rm = _relMontare(conf)
	dinfo = os.path.join(_cale(radacina, rm), "var", "lib", "opkg", "info")
	rez = {}
	try:
		nume = sorted(n for n in os.listdir(dinfo) if n.endswith(".list"))
	except OSError:
		return rez
	prefix = "/" + rm.rstrip("/") + "/"
	for n in nume:
		try:
			with open(os.path.join(dinfo, n), encoding="utf-8", errors="replace") as f:
				randuri = f.read().splitlines()
		except (IOError, OSError):
			continue
		for r in randuri:
			r = r.split("\t", 1)[0].strip()
			if r.startswith(prefix):
				r = r[len(prefix):]
			else:
				r = r.lstrip("/")
			if not r or ".." in r.split("/") or not r.startswith(RADACINI):
				continue
			# numai fisierele (si legaturile) din destinatie; dosarele vin singure
			p = os.path.join(_cale(radacina, rm), r)
			if os.path.isdir(p) and not os.path.islink(p):
				continue
			rez.setdefault(r, n[:-5])
	return rez


def _tinta(conf, rel):
	return montare(conf).rstrip("/") + "/" + rel


def _inMontare(cale, conf):
	"""True cand `cale` duce (prin legaturi) in punctul de montare al partii a doua"""
	try:
		r = os.path.realpath(cale)
	except OSError:
		return False
	m = montare(conf).rstrip("/")
	return r == m or r.startswith(m + "/") or ("/" + _relMontare(conf).rstrip("/") + "/") in (r + "/")


def _esteANoastra(cale, tinta):
	try:
		return os.path.islink(cale) and os.readlink(cale) == tinta
	except OSError:
		return False


def legaturiDorite(radacina, conf, inventar=None):
	"""({cale relativa: tinta}, [conflicte]): pentru fiecare fisier din destinatie, cel mai inalt dosar (sub
	RADACINI, niciodata o radacina insasi) care nu exista in memoria interna sau e deja legatura noastra; daca toti
	parintii exista ca dosare adevarate, fisierul insusi. O cale ocupata de baza (fisier, dosar pus de altcineva sau
	legatura straina) e conflict."""
	inventar = inventar or {}
	dorite = {}
	conflicte = []
	for rel in sorted(fisiereDestinatie(radacina, conf)):
		parti = rel.split("/")
		gasit = None
		for i in range(2, len(parti) + 1):
			p = "/".join(parti[:i])
			if p in dorite:
				gasit = p
				break
			full = _cale(radacina, p)
			t = _tinta(conf, p)
			if not os.path.lexists(full) or _esteANoastra(full, t) or (p in inventar and _esteANoastra(full, inventar[p])):
				gasit = p
				break
			# un dosar al bazei (si o legatura a bazei spre un dosar din memoria interna): se coboara in el
			if i < len(parti) and os.path.isdir(full) and not _inMontare(full, conf):
				continue
			conflicte.append(p)
			break
		if gasit:
			dorite[gasit] = _tinta(conf, gasit)
	return dorite, sorted(set(conflicte))


def citesteInventar(radacina=None):
	rez = {}
	try:
		with open(os.path.join(_cale(radacina, DOSAR_NAND), FISIER_LEGATURI), encoding="utf-8") as f:
			for rand in f:
				p = rand.rstrip("\n").split("\t")
				if len(p) == 2 and p[0] and p[1]:
					rez[p[0]] = p[1]
	except (IOError, OSError):
		pass
	return rez


def _scrieInventar(radacina, inv):
	text = "".join("%s\t%s\n" % (k, inv[k]) for k in sorted(inv))
	_scrieDacaAltfel(os.path.join(_cale(radacina, DOSAR_NAND), FISIER_LEGATURI), text)


def reconciliaza(radacina=None, conf=None, numai_scoate=False):
	"""Aduce legaturile din memoria interna la listele opkg ale destinatiei (stickul trebuie sa fie montat; numai_scoate:
	le scoate pe toate, la dezlegare). Scoate numai legaturile din inventar care sunt inca legaturi spre tinta noastra.
	Intoarce {"puse": [...], "scoase": [...], "conflicte": [...]}"""
	radacina = radacina or radacinaImplicita()
	conf = conf or citesteConf(radacina)
	inv = citesteInventar(radacina)
	if numai_scoate:
		dorite, conflicte = {}, []
	else:
		dorite, conflicte = legaturiDorite(radacina, conf, inv)
		if conflicte:
			return {"puse": [], "scoase": [], "conflicte": conflicte}
	scoase = []
	puse = []
	# intai scoaterea (o legatura pe dosar poate fi inlocuita de legaturi mai adanci, sau invers)
	for rel in sorted(inv, key=lambda x: -x.count("/")):
		if dorite.get(rel) == inv[rel]:
			continue
		full = _cale(radacina, rel)
		if _esteANoastra(full, inv[rel]):
			os.remove(full)
			scoase.append(rel)
		del inv[rel]
	for rel in sorted(dorite, key=lambda x: x.count("/")):
		full = _cale(radacina, rel)
		if _esteANoastra(full, dorite[rel]):
			inv[rel] = dorite[rel]
			continue
		if os.path.lexists(full):
			conflicte.append(rel)
			continue
		parinte = os.path.dirname(full)
		if not os.path.isdir(parinte) or _inMontare(parinte, conf):
			conflicte.append(rel)
			continue
		os.symlink(dorite[rel], full)
		inv[rel] = dorite[rel]
		puse.append(rel)
	_scrieInventar(radacina, inv)
	return {"puse": puse, "scoase": scoase, "conflicte": sorted(set(conflicte))}


# ---------------------------------------------------------------- comenzile sistemului

def _ruleaza(argv, timp=600):
	"""(cod, iesirea); cod 127 cand programul lipseste"""
	try:
		r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timp)
		return r.returncode, r.stdout.decode("utf-8", "replace")
	except FileNotFoundError:
		return 127, "%s lipseste" % argv[0]
	except subprocess.TimeoutExpired:
		return 124, "%s: timpul a expirat" % argv[0]


def ocupaOperatia(radacina=None):
	"""Lacat pe intreaga operatie, inclusiv intre procesele CLI si Enigma2."""
	cale = _cale(radacina, "var/run/hds-partea-doua.lock")
	f = None
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		f = open(cale, "a+b")
		try:
			import fcntl
			fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
		except ImportError:
			import msvcrt
			if os.fstat(f.fileno()).st_size == 0:
				f.write(b"0")
				f.flush()
			f.seek(0)
			msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
		return f
	except OSError:
		if f is not None:
			f.close()
		return None


def elibereazaOperatia(lacat):
	if lacat is None:
		return
	try:
		try:
			import fcntl
			fcntl.flock(lacat.fileno(), fcntl.LOCK_UN)
		except ImportError:
			import msvcrt
			lacat.seek(0)
			msvcrt.locking(lacat.fileno(), msvcrt.LK_UNLCK, 1)
	finally:
		lacat.close()


def _citesteId(radacina, conf):
	try:
		with open(os.path.join(_cale(radacina, _relMontare(conf)), "hds", "model"), encoding="utf-8") as f:
			if not conf.get("MODEL") or f.read().strip() != conf["MODEL"]:
				return ""
		with open(os.path.join(_cale(radacina, _relMontare(conf)), "hds", "id"), encoding="utf-8") as f:
			return f.read().strip()
	except (IOError, OSError):
		return ""


def verificaFisier(cale):
	"""e2fsck -p pe fisierul nemontat: 0/1/2 = bun (2: reparat; pe un fisier loop nu cere repornire), altfel stricat"""
	cod, iesire = _ruleaza(["e2fsck", "-p", cale], 300)
	return cod in (0, 1, 2), cod, iesire


def monteaza(cale, radacina=None, conf=None):
	m = _cale(radacina, _relMontare(conf))
	os.makedirs(m, exist_ok=True)
	cod, iesire = _ruleaza(["mount", "-t", "ext4", "-o", "loop,noatime", cale, m], 120)
	return cod == 0, iesire


def demonteaza(radacina=None, conf=None):
	if not esteMontat(radacina, conf):
		return True
	cod, _i = _ruleaza(["umount", _cale(radacina, _relMontare(conf))], 120)
	return cod == 0


# ---------------------------------------------------------------- pornirea, pregatirea, instalarea

def porneste(radacina=None, asteapta=None, dormi=time.sleep):
	"""La pornire, inainte de Enigma2: monteaza stickul legat si reconciliaza legaturile. Nu arunca."""
	radacina = radacina or radacinaImplicita()
	conf = citesteConf(radacina)
	if conf is None or not radacinaNand(radacina):
		puneDestinatiaOpkg(radacina, conf, False)
		return scrieStare(radacina, NEDESCRIS)
	ident = idLegat(radacina)
	if not ident:
		puneDestinatiaOpkg(radacina, conf, False)
		return scrieStare(radacina, NELEGAT, liber_intern_mib=liberMib(radacina))
	if esteMontat(radacina, conf) and _citesteId(radacina, conf) == ident:
		puneDestinatiaOpkg(radacina, conf, True)
		r = reconciliaza(radacina, conf)
		return scrieStare(radacina, LEGAT, conflicte=r["conflicte"])
	pana = time.time() + (_int(conf.get("ASTEAPTA_S"), 10) if asteapta is None else asteapta)
	vazute = set()
	ultima = ""
	while True:
		for c in fisiereGasite(radacina, conf):
			if c in vazute:
				continue
			vazute.add(c)
			bun, cod, iesire = verificaFisier(c)
			if not bun:
				ultima = "e2fsck %d: %s" % (cod, iesire.strip()[-200:])
				continue
			ok, iesire = monteaza(c, radacina, conf)
			if not ok:
				ultima = "mount: %s" % iesire.strip()[-200:]
				continue
			if _citesteId(radacina, conf) != ident:
				demonteaza(radacina, conf)
				continue
			puneDestinatiaOpkg(radacina, conf, True)
			r = reconciliaza(radacina, conf)
			return scrieStare(radacina, LEGAT, fisier=c, conflicte=r["conflicte"])
		if time.time() >= pana:
			break
		dormi(1)
	puneDestinatiaOpkg(radacina, conf, False)
	if ultima:
		return scrieStare(radacina, STRICAT, eroare=ultima)
	return scrieStare(radacina, LIPSESTE)


def _idNou():
	try:
		with open("/proc/sys/kernel/random/uuid") as f:
			return f.read().strip()
	except (IOError, OSError):
		return "%08x-%04x-%04x" % (random.getrandbits(32), random.getrandbits(16), random.getrandbits(16))


def pregateste(punct, radacina=None, progres=None):
	radacina = radacina or radacinaImplicita()
	lacat = ocupaOperatia(radacina)
	if lacat is None:
		return False, _t("Alta operatie este in lucru sau interfata trebuie repornita.")
	try:
		return _pregateste(punct, radacina, progres)
	finally:
		elibereazaOperatia(lacat)


def _pregateste(punct, radacina=None, progres=None):
	"""Face fisierul ext4 pe stickul montat la `punct` (din sablon, fara sa stearga ceva), il verifica, il monteaza si
	il leaga de receptor. (bine, mesaj)"""
	radacina = radacina or radacinaImplicita()
	conf = citesteConf(radacina)
	if conf is None:
		return False, _t("modelul nu are descrierea partii a doua")
	if not radacinaNand(radacina):
		return False, _t("Imaginea ruleaza deja de pe disc. Partea a doua nu este necesara.")
	progres = progres or (lambda t: None)
	if idLegat(radacina):
		return False, _t("Un stick este deja legat. Pune acel stick si reporneste receptorul.")
	if punct not in [c["punct"] for c in candidati(radacina, conf, exclus=exclusInregistrari())]:
		return False, _t("Stickul ales nu mai este disponibil sau nu are loc.")
	p = _cale(radacina, punct.lstrip("/"))
	final = os.path.join(p, FISIER)
	if os.path.lexists(final):
		return False, _t("pe stick exista deja %s; nu il suprascriu") % FISIER
	nevoie = _int(conf.get("MARIME_MIB"), 1024) + REZERVA_MIB
	if liberMib(p) < nevoie:
		return False, _t("pe stick nu sunt %d MiB liberi") % nevoie
	# Deschiderea exclusiva nu poate trunchia un fisier existent pe FAT/exFAT.
	creat = False
	progres(_t("scriu fisierul pe stick"))
	try:
		with open(final, "xb") as f:
			creat = True
			r = subprocess.run(["unxz", "-c", _cale(radacina, conf["SABLON"].lstrip("/"))], stdout=f,
				stderr=subprocess.PIPE, timeout=1800)
			f.flush()
			os.fsync(f.fileno())
		if r.returncode:
			raise OSError("unxz: %s" % r.stderr.decode("utf-8", "replace")[-200:])
		progres(_t("verific fisierul"))
		bun, cod, iesire = verificaFisier(final)
		if not bun:
			raise OSError("e2fsck %d: %s" % (cod, iesire[-200:]))
	except (OSError, subprocess.SubprocessError) as e:
		try:
			if creat:
				os.remove(final)
		except OSError:
			pass
		return False, _t("fisierul nu s-a putut face: %s") % e
	progres(_t("leg stickul"))
	ok, iesire = monteaza(final, radacina, conf)
	if not ok:
		return False, _t("fisierul nu se monteaza: %s") % iesire.strip()[-200:]
	ident = _idNou()
	m = _cale(radacina, _relMontare(conf))
	_scrieAtomic(os.path.join(m, "hds", "id"), ident + "\n")
	_scrieAtomic(os.path.join(m, "hds", "model"), "%s\n" % (conf.get("MODEL") or ""))
	_scrieAtomic(os.path.join(_cale(radacina, DOSAR_NAND), FISIER_ID), ident + "\n")
	puneDestinatiaOpkg(radacina, conf, True)
	scrieStare(radacina, LEGAT, fisier=final)
	return True, _t("stickul e pregatit")


def instaleaza(fisiere, radacina=None, intrari=None, configurare=None):
	"""Instaleaza in destinatia de pe stick pachetele date (fisiere .ipk deja verificate), apoi reconciliaza. Numai cu
	stickul legat si montat. (bine, iesirea opkg, rezultatul legarii)"""
	radacina = radacina or radacinaImplicita()
	if not intrari or not configurare or len(fisiere) != len(intrari):
		return False, _t("Pachetele locale trebuie verificate din starea semnata."), None
	for cale, intrare in zip(fisiere, intrari):
		if not verificaPachet(cale, intrare):
			return False, _t("Un pachet nu este cel semnat. Nu se instaleaza."), None
	conf = citesteConf(radacina)
	if conf is None or not idLegat(radacina) or not esteMontat(radacina, conf) or \
			_citesteId(radacina, conf) != idLegat(radacina):
		return False, _t("stickul partii a doua nu e montat"), None
	argv = ["opkg", "-f", configurare, "--noaction", "install", "-d", DEST] + list(fisiere)
	cod, iesire = _ruleaza(argv, 600)
	if cod:
		return False, iesire, None
	# Configurarea privata nu are surse. Opkg primeste numai fisierele verificate.
	argv.remove("--noaction")
	cod, iesire = _ruleaza(argv, 3600)
	A = _actualizari()
	status = os.path.join(_cale(radacina, _relMontare(conf)), "var/lib/opkg/status")
	inst = {s.get("package"): s.get("version") for s in A.P.citeste_strofe(status)
		if "installed" in s.get("status", "").split()}
	ramase = [x["nume"] for x in intrari if inst.get(x["nume"]) != x["versiune"]]
	if ramase:
		iesire += "\nPachete neinstalate complet: " + ", ".join(ramase)
	r = reconciliaza(radacina, conf)
	return cod == 0 and not ramase, iesire, r


def stare(radacina=None):
	"""Ce stie Enigma2 si pagina web: starea de la pornire, descrierea modelului, memoria libera, stickurile bune"""
	radacina = radacina or radacinaImplicita()
	conf = citesteConf(radacina)
	d = citesteStare(radacina)
	d["descris"] = conf is not None
	d["nand"] = radacinaNand(radacina)
	d["descris"] = d["descris"] and d["nand"]
	d["legat"] = bool(idLegat(radacina))
	d["montat"] = bool(conf) and esteMontat(radacina, conf)
	d["liber_intern_mib"] = liberMib(radacina)
	if conf:
		d["prag_mib"] = _int(conf.get("PRAG_MIB"), 150)
		d["marime_mib"] = _int(conf.get("MARIME_MIB"), 1024)
		d["candidati"] = [] if d["legat"] else candidati(radacina, conf, exclus=exclusInregistrari())
	return d


def trebuieIntrebat(d, refuzat_la=0, acum=None, zile=30):
	"""Fereastra de la pornire: modelul e descris, memoria interna libera e sub prag, niciun stick legat, e pus un stick
	bun si omul n-a spus "Nu acum" in ultimele `zile` zile"""
	acum = time.time() if acum is None else acum
	if not d.get("descris") or not d.get("nand") or d.get("legat") or not d.get("candidati"):
		return False
	if d.get("liber_intern_mib", -1) < 0 or d["liber_intern_mib"] >= d.get("prag_mib", 150):
		return False
	return not refuzat_la or acum - refuzat_la >= zile * 86400


def exclusInregistrari():
	try:
		from Components.config import config
		return (config.usage.default_path.value.rstrip("/"),)
	except (ImportError, AttributeError, KeyError):
		return ()


def refuzuri(radacina=None):
	try:
		with open(os.path.join(_cale(radacina, DOSAR_NAND), REFUZURI), encoding="utf-8") as f:
			d = json.load(f)
		return d if isinstance(d, dict) else {}
	except (OSError, ValueError):
		return {}


def refuza(candidati_alesi, radacina=None, acum=None):
	d = refuzuri(radacina)
	acum = int(time.time() if acum is None else acum)
	d = {k: v for k, v in d.items() if isinstance(v, int) and acum - v < 30 * 86400}
	for c in candidati_alesi:
		if c.get("ident"):
			d[c["ident"]] = acum
	_scrieAtomic(os.path.join(_cale(radacina, DOSAR_NAND), REFUZURI), json.dumps(d))


def oferta(radacina=None, acum=None):
	d = dict(stare(radacina))
	r = refuzuri(radacina)
	d["candidati"] = [c for c in d.get("candidati", [])
		if trebuieIntrebat(dict(d, candidati=[c]), r.get(c.get("ident"), 0), acum)]
	return d


def _actualizari():
	try:
		from Components import HdsActualizari as A
	except ImportError:
		import HdsActualizari as A
	return A


def planContinut(feed, instalate, cerute, A=None):
	"""Inchiderea dependintelor din indexuri semnate. Lipsurile opresc instalarea."""
	A = A or _actualizari()
	plan = {}
	def satisface(n, op, v, versiuni):
		return n in versiuni and (not op or A._satisface(versiuni[n], op, v))
	def adauga(n, op="", v="", obligatoriu=False):
		s = feed.get(n)
		if not obligatoriu and satisface(n, op, v, instalate):
			return
		if n in plan:
			if not satisface(n, op, v, {n: plan[n]["version"]}):
				raise ValueError(_t("Dependinte incompatibile: ") + n)
			return
		if s is None or (op and not A._satisface(s.get("version", ""), op, v)):
			raise ValueError(_t("Pachetul lipseste din feedul semnat: ") + n)
		if n in instalate and A.P.compara_versiuni(instalate[n], s["version"]) >= 0:
			return
		# In aceasta faza sunt auditate numai metapachetele si cataloagele.
		if n != "hdsatelit-partea-doua-continut" and not n.startswith("enigma2-hdsatelit-po-"):
			raise ValueError(_t("Pachetul nu este inca auditat pentru stick: ") + n)
		plan[n] = s
		for grup in A._dependinte(s.get("depends")) + A._dependinte(s.get("pre-depends")):
			ales = next((x for x in grup if satisface(*x, instalate)), None)
			if ales:
				continue
			ales = next((x for x in grup if x[0] in feed and
				(not x[1] or A._satisface(feed[x[0]]["version"], x[1], x[2]))), None)
			if not ales:
				raise ValueError(_t("Dependinta lipseste: ") + n)
			adauga(*ales)
	for n in cerute:
		adauga(n, obligatoriu=True)
	return [{"nume": n, "la": s["version"], "arhitectura": s["architecture"]}
		for n, s in sorted(plan.items())]


def verificaPachet(cale, intrare):
	A = _actualizari()
	try:
		return A._sha256_fisier(cale) == (intrare["sha256"], intrare["marime"])
	except (OSError, KeyError):
		return False


def faraScripturi(cale):
	"""Citeste controlul IPK fara extractie. Orice script cere audit separat."""
	with open(cale, "rb") as f:
		if f.read(8) != b"!<arch>\n":
			raise ValueError(_t("Format IPK necunoscut"))
		while True:
			h = f.read(60)
			if not h:
				break
			if len(h) != 60 or h[-2:] != b"`\n":
				raise ValueError(_t("Arhiva IPK stricata"))
			n = int(h[48:58].strip())
			nume = h[:16].strip().rstrip(b"/")
			if nume.startswith(b"control.tar"):
				if n > 4 * 1024 * 1024:
					raise ValueError(_t("Control IPK prea mare"))
				with tarfile.open(fileobj=io.BytesIO(f.read(n)), mode="r:*") as t:
					for x in t:
						if x.name.lstrip("./") not in ("", "control", "conffiles", "md5sums"):
							raise ValueError(_t("IPK cu script sau control neauditat: ") + x.name)
				return
			f.seek(n + n % 2, 1)
	raise ValueError(_t("Controlul IPK lipseste"))


def _localDeschide(dosar, adresa_baza):
	"""Aceeasi verificare a semnaturii pentru dosarul copiat de pe PC."""
	def deschide(cerere, timeout=None):
		adresa = cerere.full_url
		prefix = adresa_baza.rstrip("/") + "/"
		if not adresa.startswith(prefix):
			raise OSError(_t("Adresa din afara dosarului offline"))
		rel = adresa[len(prefix):]
		if any(not re.match(r"^[A-Za-z0-9+._~-]+$", p) or p in (".", "..") for p in rel.split("/")):
			raise OSError(_t("Cale offline nepermisa"))
		return open(os.path.join(dosar, *rel.split("/")), "rb")
	return deschide


def actualizeazaContinut(radacina=None, progres=None, offline=None, lacat=None, cerute=()):
	radacina = radacina or radacinaImplicita()
	propriu = lacat is None
	lacat = lacat if lacat is not None else ocupaOperatia(radacina)
	if lacat is None:
		return False, _t("Alta operatie este in lucru sau interfata trebuie repornita.")
	try:
		return _actualizeazaContinut(radacina, progres, offline, cerute)
	finally:
		if propriu:
			elibereazaOperatia(lacat)


def _actualizeazaContinut(radacina=None, progres=None, offline=None, cerute=()):
	"""Semnatura, indexuri, plan, SHA256, proba opkg, instalare fara surse, legaturi."""
	radacina = radacina or radacinaImplicita()
	progres = progres or (lambda text: None)
	conf = citesteConf(radacina)
	if not conf or not radacinaNand(radacina) or not esteMontat(radacina, conf) or \
			_citesteId(radacina, conf) != idLegat(radacina) or not idLegat(radacina):
		return False, _t("Stickul partii a doua nu este montat. Pune-l si reporneste receptorul.")
	A = _actualizari()
	pc = A.P.citeste_configurarea(radacina)
	canal, surse, baza = A.canalul(radacina, pc)
	if canal not in ("public", "proba") or not surse or baza != A.baza_receptorului(radacina):
		return False, _t("Sursa partii a doua lipseste sau cere o alta imagine.")
	adresa = A.adresa_stare(canal, baza).rsplit("/", 1)[0]
	deschide = _localDeschide(offline, adresa) if offline else None
	credentiale = A.citeste_netrc(radacina) if canal == "proba" and not offline else None
	dosar = os.path.join(_cale(radacina, _relMontare(conf)), "hds", "descarcare")
	try:
		progres(_t("Verific semnatura feedului..."))
		server, eroare = A.descarca_stare(adresa + "/stare.json", credentiale, deschide=deschide)
		if eroare:
			raise ValueError(_t("Feedul nu poate fi verificat: ") + server.get("eroare", eroare))
		if server.get("baza") != baza or server.get("imagine_noua") or \
				A.P.compara_versiuni(server.get("imagine_minima", ""), baza) > 0 or \
				server.get("canal", canal) != canal:
			raise ValueError(_t("Continutul cere o alta imagine sau alt canal."))
		feed = {}
		for arh in sorted(set(s[2] for s in surse)):
			if arh not in pc.arhitecturi:
				continue
			x = (server.get("indexuri") or {}).get(arh) or {}
			corp, e = A._cere(adresa + "/" + arh + "/Packages", credentiale,
				deschide=deschide, maxim=32 * 1024 * 1024, accept="text/plain")
			if e or not corp or len(corp) != x.get("marime") or hashlib.sha256(corp).hexdigest() != x.get("sha256"):
				raise ValueError(_t("Indexul pachetelor nu este cel semnat: ") + arh)
			for s in A.P.strofe_din_text(corp.decode("utf-8")):
				n = s.get("package", "")
				if not A.P.nume_valid(n) or s.get("architecture") != arh:
					continue
				vechi = feed.get(n)
				if vechi is None or A.P.compara_versiuni(s.get("version", ""), vechi["version"]) > 0 or \
						(s.get("version") == vechi["version"] and pc.arhitecturi[arh] > pc.arhitecturi[vechi["architecture"]]):
					feed[n] = s
		inst = A.instalate(radacina, pc)
		usb = A.P.citeste_strofe(os.path.join(_cale(radacina, _relMontare(conf)), "var/lib/opkg/status"))
		pe_stick = {s["package"]: s.get("version", "") for s in usb if "installed" in s.get("status", "").split()}
		inst.update(pe_stick)
		plan = planContinut(feed, inst,
			[conf["PACHET"]] + sorted(pe_stick) + list(cerute), A)
		if not plan:
			r = reconciliaza(radacina, conf)
			return not r["conflicte"], _t("Continutul este la zi.") if not r["conflicte"] else _t("Conflict cu fisierele bazei.")
		intrari, e = A.pachete_semnate({"stare": server}, {"server": server, "pachete": plan})
		if e or A.pachete_straine(intrari, pc.arhitecturi):
			raise ValueError(e or _t("Pachete pentru alt model"))
		progres(_t("Descarc si verific pachetele pe stick..."))
		cai, e = A.descarca_pachete(intrari, adresa, credentiale, dosar, deschide)
		if e:
			raise ValueError(_t("Pachet neverificat sau descarcare oprita: ") + e[1])
		for cale in cai:
			faraScripturi(cale)
		info = os.path.join(_cale(radacina, _relMontare(conf)), "var/lib/opkg/info")
		if os.path.isdir(info) and any(n.endswith((".preinst", ".postinst", ".prerm", ".postrm"))
				for n in os.listdir(info)):
			raise ValueError(_t("Stickul contine scripturi de pachet care nu sunt auditate."))
		configurare = os.path.join(dosar, "opkg.conf")
		# Starea bazei este numai o copie, fara scripturi si fara cai spre NAND.
		baza_virtuala = os.path.join(dosar, "baza")
		copie = []
		for s in A.P.citeste_strofe(A._cale(radacina, pc.status_file)):
			if s.get("status", "").split()[-1:] == ["installed"]:
				copie.append("\n".join(k + ": " + v.replace("\n", "\n ") for k, v in s.items()))
		_scrieAtomic(os.path.join(baza_virtuala, "var/lib/opkg/status"), "\n\n".join(copie) + "\n\n")
		text = "dest baza %s\ndest %s %s\n" % (baza_virtuala, DEST, montare(conf))
		text += "".join("arch %s %d\n" % x for x in sorted(pc.arhitecturi.items()))
		text += "option lists_dir %s\n" % os.path.join(dosar, "liste-goale")
		_scrieAtomic(configurare, text)
		progres(_t("Instalez pachetele verificate..."))
		ok, iesire, r = instaleaza(cai, radacina, intrari, configurare)
		if not ok:
			raise ValueError(A.curata(iesire)[-300:])
		if r and r["conflicte"]:
			raise ValueError(_t("Continutul este pe stick, dar exista un conflict cu baza: ") + ", ".join(r["conflicte"][:3]))
		scrieStare(radacina, LEGAT, actualizare=server.get("actualizare"))
		return True, _t("Limbile sunt pe stick. Lasa stickul in receptor. Reporneste interfata pentru a le vedea.")
	except (OSError, ValueError, KeyError, tarfile.TarError) as e:
		return False, str(e)
	finally:
		A.goleste_dosarul(dosar)


def detaseazaPentruBaza(radacina=None):
	"""Baza se actualizeaza fara a urma legaturile spre stick."""
	radacina = radacina or radacinaImplicita()
	if not citesteConf(radacina) or not radacinaNand(radacina):
		return False
	reconciliaza(radacina, numai_scoate=True)
	return bool(idLegat(radacina))


def dupaActualizareaBazei(radacina=None, actualizeaza=True, lacat=None):
	radacina = radacina or radacinaImplicita()
	conf = citesteConf(radacina)
	if not conf or not radacinaNand(radacina) or not idLegat(radacina):
		return True, ""
	if not esteMontat(radacina, conf):
		return False, MESAJ_LIPSA
	try:
		if actualizeaza:
			return actualizeazaContinut(radacina, lacat=lacat)
		return True, ""
	finally:
		reconciliaza(radacina, conf)


class Lucrare:
	"""Aceeasi lucrare pentru ecran si web. Firul nu atinge interfata Enigma2."""
	def __init__(self):
		self.ocupat = False
		self.mesaj = ""
		self.bine = None
		self.lacat = threading.Lock()

	def porneste(self, punct=None):
		with self.lacat:
			A = _actualizari()
			if self.ocupat or A.opkg_ocupat() or getattr(A.actualizari, "faza", "liber") != "liber":
				return False
			if A.actualizari.repornire:
				self.mesaj = _t("Reporneste interfata dupa actualizarea bazei.")
				return False
			self.ocupat, self.bine = True, None
		def progres(text):
			self.mesaj = _t(text)
		def lucru():
			try:
				if punct:
					ok, mesaj = pregateste(punct, progres=progres)
					if not ok:
						self.bine, self.mesaj = False, mesaj
						return
				offline = None
				for _d, p, _f, _o in montari():
					c = os.path.join(p, "hdsatelit-partea-doua")
					if p.startswith("/media/") and os.path.isfile(os.path.join(c, "stare.json")):
						offline = c
						break
				self.bine, self.mesaj = actualizeazaContinut(progres=progres, offline=offline)
			except Exception as e:
				self.bine, self.mesaj = False, _t("Operatia s-a oprit: %s") % e
			finally:
				self.ocupat = False
		threading.Thread(target=lucru, name="hds-partea-doua", daemon=True).start()
		return True


lucrare = Lucrare()


def starePublica():
	d = stare()
	d.update(ocupat=lucrare.ocupat, mesaj=_t(lucrare.mesaj), bine=lucrare.bine, limita=_t(MESAJ_LIMITA))
	if d.get("legat") and not d.get("montat"):
		d["mesaj"] = _t(MESAJ_LIPSA)
	if not d.get("descris"):
		d["mesaj"] = _t("Partea a doua se foloseste numai cu imaginea de baza in memoria interna mica.")
		d["limita"] = ""
	return d


def main(argv):
	rad = radacinaImplicita()
	if not argv:
		print("folosire: stare | porneste | candidati | pregateste <dosar> | leaga | actualizeaza [dosar-offline]")
		return 2
	c = argv[0]
	if c == "stare":
		print(json.dumps(stare(rad), ensure_ascii=False, sort_keys=True))
		return 0
	if c == "porneste":
		lacat = ocupaOperatia(rad)
		if lacat is None:
			print(_t("Alta operatie este in lucru sau interfata trebuie repornita."))
			return 1
		try:
			d = porneste(rad)
			print(d.get("stare"))
			return 0
		finally:
			elibereazaOperatia(lacat)
	if c == "candidati":
		print(json.dumps(candidati(rad), ensure_ascii=False))
		return 0
	if c == "actualizeaza" and len(argv) <= 2:
		ok, mesaj = actualizeazaContinut(rad, progres=lambda t: print(t, flush=True),
			offline=argv[1] if len(argv) == 2 else None)
		print(mesaj)
		return 0 if ok else 1
	if c == "pregateste" and len(argv) == 2:
		ok, mesaj = pregateste(argv[1], rad, progres=lambda t: print(t, flush=True))
		print(mesaj)
		return 0 if ok else 1
	if c == "leaga":
		lacat = ocupaOperatia(rad)
		if lacat is None:
			print(_t("Alta operatie este in lucru sau interfata trebuie repornita."))
			return 1
		try:
			conf = citesteConf(rad)
			if conf is None or not esteMontat(rad, conf) or not radacinaNand(rad):
				print("stickul nu e montat")
				return 1
			print(json.dumps(reconciliaza(rad, conf), ensure_ascii=False))
			return 0
		finally:
			elibereazaOperatia(lacat)
	if c == "instaleaza" and len(argv) >= 2:
		ok, iesire, r = instaleaza(argv[1:], rad)
		print(iesire)
		print(json.dumps(r, ensure_ascii=False))
		return 0 if ok else 1
	print("comanda necunoscuta: %s" % c)
	return 2


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
