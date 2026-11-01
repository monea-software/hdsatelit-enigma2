# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPornireMultipla.py: Porneste alte imagini (Meniu > Standby si repornire), fara ecran. Il folosesc ecranul de pe
# receptor (Screens/HdsPornireMultipla.py) si pagina web /alimentare (HdsWebControl/alimentare_web.py, cardul flash),
# deci amandoua arata aceleasi imagini si scriu la fel.
#
# Octagon SF8008 si SF8008 MINI au in memorie patru locuri de imagini: nucleul in linuxkernel1-4 (mmcblk0p12-p15) si
# sistemul in subdosarul linuxrootfs1-4 al partitiei userdata (mmcblk0p16). Incarcatorul citeste la pornire fisierul
# STARTUP de pe partitia bootoptions (FAT, mmcblk0p3, montata la /boot), langa care stau STARTUP_1..4 (locurile din
# memorie), STARTUP_5..6 (stickul) si STARTUP_RECOVERY, puse de producator. Alegerea unei imagini = STARTUP_N copiat
# octet cu octet peste STARTUP, apoi repornirea; nimic altceva nu se scrie (bootargs si p1-p11 raman neatinse).
#
# SIGURANTA (e pornirea receptorului):
# - se scrie numai un loc din memorie cu forma stiuta (boot emmcflash0.linuxkernelK '... root=userdata
#   rootsubdir=linuxrootfsK kernel=linuxkernelK ...', partitiile dupa NUMELE din blkdevparts, acelasi blkdevparts ca
#   in linia de comanda de acum), cu nucleu valid (antet uImage cu CRC bun, cat incape in partitie) si sistem cu
#   sbin/init; altfel locul se arata cu "nu poate porni" sau nu se arata deloc (locurile goale);
# - STARTUP vechi ramane in STARTUP.hds-inainte; scrierea: STARTUP.hds-nou, fsync, rename (os.replace) peste STARTUP, sync, apoi
#   citit inapoi si comparat; la o nepotrivire se pune la loc cel vechi;
# - directorul scris e numai partitia bootoptions dovedita in /proc/mounts (sau montata aici, apoi demontata);
# - locurile de pe stick sau card (usb0.sdaN) NU se scriu: pe SF8008 cardul apare ca /dev/sda, deci numele sdaN ale
#   stickului se pot muta si STARTUP-ul ar porni alt disc. Cand imaginea de acum ruleaza de pe stick se spune asta.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau `radacina` (un receptor fals) si
# `monteaza` (montarea partitiei userdata).

import os
import re
import struct
import subprocess
import zlib

MASINI = ("sf8008", "sf8008m")
FISIER_STARTUP = "STARTUP"
COPIE = "STARTUP.hds-inainte"
NOU = "STARTUP.hds-nou"
MAXIM_STARTUP = 4096
UIMAGE_MAGIC = 0x27051956
TINTA_EMMC = re.compile(r"^boot emmcflash0\.linuxkernel([1-9])$")
LINIE = re.compile(r"^boot (\S+) '([ -&(-~]*)'\n?$")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


TITLU = N_("Pornește alte imagini")
NOTA = N_("Alegi imaginea și apeși OK: receptorul repornește în ea. Lista arată imaginile instalate în memoria "
	"receptorului.")
CAUT = N_("Caut imaginile instalate...")
RAND = N_("Locul %(loc)s: %(imagine)s")
RAND_ACUM = N_("Locul %(loc)s: %(imagine)s, pornită acum")
RAND_STRICAT = N_("Locul %(loc)s: %(imagine)s, nu poate porni")
RAND_STICK = N_("Pe stick: %(imagine)s, pornită acum")
PE_STICK = N_("Imaginile de pe stick se aleg din meniul stickului.")
NICIUNA = N_("Nu am găsit alte imagini instalate în memoria receptorului.")
INTREBARE = N_("Receptorul repornește în imaginea %s. Continui?")
BUTON = N_("Pornește")
DEJA = N_("Aceasta e imaginea pornită acum.")
REFUZ = N_("Imaginea din locul %s nu poate porni (lipsește nucleul sau sistemul), deci nu o aleg.")
NEGASIT = N_("Locul ales nu mai e în listă. Deschide din nou lista.")
EROARE = N_("Nu am putut scrie alegerea, deci receptorul rămâne în imaginea de acum.")
FARA_NUME = N_("Imagine fără nume")


def _log(text):
	print("[HdsPornireMultipla] %s" % text)


def _cale(radacina, rel):
	return os.path.join(radacina or "/", rel.lstrip("/"))


def _citeste(cale, maxim=65536):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return None


def _text(cale, maxim=65536):
	d = _citeste(cale, maxim)
	return d.decode("utf-8", "replace") if d is not None else ""


# ------------------------------------------------------------------ linia de comanda si partitiile

def parametri(text):
	"""cheie=valoare din linia de comanda (prima aparitie castiga)."""
	p = {}
	for cuv in (text or "").split():
		k, semn, v = cuv.partition("=")
		if semn and k not in p:
			p[k] = v
	return p


def partitii(blkdevparts):
	"""blkdevparts=mmcblk0:1M(boot),...,-(userdata) -> ("mmcblk0", [(nume, marime_octeti sau None)])."""
	disc, semn, lista = (blkdevparts or "").partition(":")
	if not semn:
		return None, []
	rez = []
	for bucata in lista.split(","):
		m = re.match(r"^(-|\d+)([KMG]?)\(([A-Za-z0-9_]+)\)$", bucata.strip())
		if not m:
			return None, []
		if m.group(1) == "-":
			marime = None
		else:
			marime = int(m.group(1)) * {"": 1, "K": 1024, "M": 1024 * 1024, "G": 1024 * 1024 * 1024}[m.group(2)]
		rez.append((m.group(3), marime))
	return disc, rez


def dispozitivPartitie(blkdevparts, nume):
	"""(/dev/mmcblk0pN, marime) pentru partitia cu numele `nume`; (None, None) cand lipseste."""
	disc, lista = partitii(blkdevparts)
	for i, (n, marime) in enumerate(lista):
		if n == nume:
			return "/dev/%sp%d" % (disc, i + 1), marime
	return None, None


def linieComanda(radacina=None):
	return _text(_cale(radacina, "proc/cmdline"), 16384).strip()


def disponibil(radacina=None):
	"""True pe Octagon SF8008 si SF8008 MINI cu partitia bootoptions (nu cere /boot montat: libreader il monteaza mai
	tarziu). Pe celelalte receptoare randul din meniu nu apare."""
	try:
		from Components import HdsPlatforma
	except ImportError:
		import HdsPlatforma  # probele de pe PC
	masina = HdsPlatforma.masinaDinReguli(radacina) or HdsPlatforma.tipPlaca(radacina)
	if masina not in MASINI:
		return False
	dev, _m = dispozitivPartitie(parametri(linieComanda(radacina)).get("blkdevparts", ""), "bootoptions")
	return bool(dev) or os.path.exists(_cale(radacina, "dev/block/by-name/bootoptions"))


# ------------------------------------------------------------------ fisierele STARTUP

def citesteStartup(date):
	"""Octetii unui STARTUP_N -> {"tinta", "argumente", "p"} sau None cand nu are forma `boot TINTA '...'`."""
	if date is None or len(date) > MAXIM_STARTUP:
		return None
	try:
		text = date.decode("ascii")
	except UnicodeDecodeError:
		return None
	m = LINIE.match(text)
	if not m:
		return None
	return {"tinta": m.group(1), "argumente": m.group(2), "p": parametri(m.group(2))}


def verificaEmmc(st, cmd):
	"""Locul K din memorie, cu forma stiuta si aceleasi partitii ca acum -> (K, dispozitivul nucleului, marimea lui,
	dispozitivul radacinii, subdosarul); None altfel."""
	if not st:
		return None
	m = TINTA_EMMC.match("boot " + st["tinta"])
	if not m:
		return None
	k = m.group(1)
	p = st["p"]
	blk = p.get("blkdevparts", "")
	if not blk or blk != cmd.get("blkdevparts"):
		return None
	nucleu, marime = dispozitivPartitie(blk, "linuxkernel" + k)
	rad, _m = dispozitivPartitie(blk, "userdata")
	if not nucleu or not rad or p.get("kernel") != nucleu or p.get("root") != rad:
		return None
	if p.get("rootsubdir") != "linuxrootfs" + k or p.get("rootfstype", "ext4") != "ext4":
		return None
	return k, nucleu, marime, rad, p["rootsubdir"]


def nucleuValid(cale, marime_partitie):
	"""Antetul uImage al nucleului: magia, CRC-ul antetului, marimea care incape in partitie."""
	antet = _citeste(cale, 64)
	if not antet or len(antet) < 64:
		return False
	magie, hcrc, _t, marime = struct.unpack(">IIII", antet[:16])
	if magie != UIMAGE_MAGIC or marime <= 0:
		return False
	if zlib.crc32(antet[:4] + b"\0\0\0\0" + antet[8:]) & 0xffffffff != hcrc:
		return False
	return marime_partitie is None or marime + 64 <= marime_partitie


def radacinaValida(dosar):
	return os.path.lexists(os.path.join(dosar, "sbin", "init"))


def _cheiValori(text):
	d = {}
	for rand in text.splitlines():
		k, semn, v = rand.partition("=")
		if semn and k.strip() not in d:
			d[k.strip()] = v.strip()
	return d


def _versiuneOpkg(dosar, pachet):
	text = _text(os.path.join(dosar, "var", "lib", "opkg", "status"), 8 * 1024 * 1024)
	m = re.search(r"(?m)^Package: %s\r?\n(?:[^\n]+\n)*?Version: ([^\r\n]+)" % re.escape(pachet), text)
	if not m:
		return ""
	v = m.group(1).split(":")[-1]
	return v.split("+")[0].split("-")[0]


def numeImagine(dosar):
	"""Numele si versiunea imaginii dintr-o radacina (etc/image-version, etc/issue): "HD Satelit 0.6.18"."""
	iv = _cheiValori(_text(os.path.join(dosar, "etc", "image-version")))
	nume = iv.get("imagename") or iv.get("distro") or iv.get("creator") or ""
	versiune = iv.get("imageversion", "")
	if nume.lower() == "hdsatelit":
		nume = "HD Satelit"
		versiune = _versiuneOpkg(dosar, "enigma2-hdsatelit") or _cheiValori(
			_text(os.path.join(dosar, "etc", "hdsatelit-model"))).get("version", "")
	if not versiune and re.match(r"^\d+(\.\d+)+$", iv.get("version", "")):
		versiune = iv["version"]
	if not nume:
		rand = _text(os.path.join(dosar, "etc", "issue"), 4096).strip().splitlines()
		nume = re.sub(r"\\[a-zA-Z]|%[a-z]", "", rand[0] if rand else "").strip()
	nume = re.sub(r"[^\w .,:()+-]", "", nume, flags=re.UNICODE).strip()[:40]
	if versiune and versiune not in nume:
		nume = "%s %s" % (nume, versiune[:20])
	return nume.strip() or _(FARA_NUME)


def dosarBoot(radacina=None):
	"""Punctul de montare al partitiei bootoptions din /proc/mounts (vfat, rw), cu radacina; None cand nu e montata."""
	dev, _m = dispozitivPartitie(parametri(linieComanda(radacina)).get("blkdevparts", ""), "bootoptions")
	if not dev:
		return None
	tinta = os.path.realpath(_cale(radacina, dev))
	for rand in _text(_cale(radacina, "proc/mounts")).splitlines():
		c = rand.split()
		if len(c) < 4 or c[2] != "vfat" or "rw" not in c[3].split(","):
			continue
		if c[0] == dev or os.path.realpath(_cale(radacina, c[0])) == tinta:
			return _cale(radacina, c[1])
	return None


def _monteazaReal(dispozitiv, fel):
	"""Montarea simpla (ca la celelalte imagini: o a doua montare a lui p16 cu -o ro da EBUSY pe nucleul 4.4) intr-un
	dosar din /tmp -> (dosar, demonteaza) sau (None, None)."""
	import tempfile
	d = tempfile.mkdtemp(prefix="hds-pornire-", dir="/tmp")
	try:
		cod = subprocess.call(["mount", "-t", fel, dispozitiv, d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	except OSError:
		cod = -1
	if cod != 0:
		os.rmdir(d)
		return None, None

	def demonteaza():
		subprocess.call(["umount", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		try:
			os.rmdir(d)
		except OSError:
			pass
	return d, demonteaza


def _deschideBoot(radacina, monteaza):
	"""(dosarul bootoptions, demonteaza sau None); (None, None) cand nu se poate dovedi."""
	d = dosarBoot(radacina)
	if d:
		return d, None
	if radacina:
		return None, None
	dev, _m = dispozitivPartitie(parametri(linieComanda()).get("blkdevparts", ""), "bootoptions")
	if not dev:
		return None, None
	return (monteaza or _monteazaReal)(dev, "vfat")


def startupuri(dosar):
	"""[(N, octetii)] pentru STARTUP_<cifre>, in ordinea numerelor."""
	rez = []
	try:
		nume = os.listdir(dosar)
	except OSError:
		return rez
	for n in nume:
		if n.upper().startswith("STARTUP_") and n[8:].isdigit():
			date = _citeste(os.path.join(dosar, n), MAXIM_STARTUP + 1)
			if date is not None:
				rez.append((n[8:], n, date))
	rez.sort(key=lambda x: int(x[0]))
	return rez


# ------------------------------------------------------------------ lista locurilor

def locuri(radacina=None, monteaza=None):
	"""{"locuri": [...], "pe_stick": bool, "eroare": bool}. Fiecare loc: loc, imagine, acum, alegere (se poate scrie),
	fel (emmc / stick). Locurile goale (fara radacina) nu apar."""
	cmd = parametri(linieComanda(radacina))
	rez = {"locuri": [], "pe_stick": False, "eroare": False}
	pe_stick = cmd.get("root", "").startswith("/dev/sd") or cmd.get("root", "").startswith("/dev/mmcblk1")
	boot, demonteazaBoot = _deschideBoot(radacina, monteaza)
	if not boot:
		rez["eroare"] = True
		return rez
	try:
		fisiere = startupuri(boot)
	finally:
		if demonteazaBoot:
			demonteazaBoot()
	emmc = []
	for n, nume_fisier, date in fisiere:
		st = citesteStartup(date)
		e = verificaEmmc(st, cmd)
		if e:
			emmc.append((n, nume_fisier, date, e))
		elif pe_stick and st and st["p"].get("root") == cmd.get("root") and st["p"].get("kernel") == cmd.get("kernel"):
			rez["locuri"].append({"loc": n, "fel": "stick", "imagine": numeImagine(_cale(radacina, "/")), "acum": True,
				"alegere": False})
	if pe_stick:
		rez["pe_stick"] = True
		if not any(l["acum"] for l in rez["locuri"]):
			rez["locuri"].append({"loc": "", "fel": "stick", "imagine": numeImagine(_cale(radacina, "/")),
				"acum": True, "alegere": False})
	if not emmc:
		return rez
	montari = {}
	try:
		for n, nume_fisier, date, (k, nucleu, marime, rad, sub) in emmc:
			if rad not in montari:
				montari[rad] = (monteaza or _monteazaReal)(_cale(radacina, rad) if radacina else rad, "ext4")
			dosar_rad = montari[rad][0]
			if not dosar_rad:
				rez["eroare"] = True
				continue
			sistem = os.path.join(dosar_rad, sub)
			if not os.path.isdir(os.path.join(sistem, "etc")):
				continue  # loc gol
			acum = (cmd.get("root") == rad and cmd.get("rootsubdir") == sub and cmd.get("kernel") == nucleu)
			bun = radacinaValida(sistem) and nucleuValid(_cale(radacina, nucleu), marime)
			rez["locuri"].append({"loc": n, "fel": "emmc", "imagine": numeImagine(sistem), "acum": acum,
				"alegere": bool(bun and not acum), "strica": not bun, "fisier": nume_fisier, "date": date})
	finally:
		for d, demonteaza in montari.values():
			if demonteaza:
				demonteaza()
	return rez


def randuri(stare):
	"""Textele randurilor, in ordinea locurilor."""
	rez = []
	for l in stare.get("locuri", []):
		d = {"loc": l["loc"], "imagine": l["imagine"]}
		if l["fel"] == "stick":
			rez.append(_(RAND_STICK) % d)
		elif l["acum"]:
			rez.append(_(RAND_ACUM) % d)
		elif l.get("strica"):
			rez.append(_(RAND_STRICAT) % d)
		else:
			rez.append(_(RAND) % d)
	return rez


def nota(stare):
	"""Textul de sub lista."""
	text = [_(NOTA)]
	if not any(l["alegere"] for l in stare.get("locuri", [])):
		text = [_(NICIUNA)]
	if stare.get("pe_stick"):
		text.append(_(PE_STICK))
	return " ".join(text)


def publice(stare):
	"""Starea fara octetii fisierelor, pentru web."""
	return {"pe_stick": stare.get("pe_stick", False), "eroare": stare.get("eroare", False),
		"locuri": [{"loc": l["loc"], "imagine": l["imagine"], "acum": l["acum"], "alegere": l["alegere"],
			"fel": l["fel"], "strica": bool(l.get("strica"))} for l in stare.get("locuri", [])],
		"randuri": randuri(stare), "nota": nota(stare)}


# ------------------------------------------------------------------ scrierea

def _scrieAtomic(dosar, nume, date):
	"""nume.hds-nou (sau NOU pentru STARTUP), fsync, rename peste `nume`, sync; apoi citit inapoi. True daca e la fel."""
	temp = os.path.join(dosar, NOU if nume == FISIER_STARTUP else nume + ".nou")
	tinta = os.path.join(dosar, nume)
	with open(temp, "wb") as f:
		f.write(date)
		f.flush()
		os.fsync(f.fileno())
	os.replace(temp, tinta)   # rename(2) pe receptor; pe vfat intrarea STARTUP ramane aceeasi
	try:
		fd = os.open(dosar, os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except OSError:
		pass
	if hasattr(os, "sync"):
		os.sync()
	try:
		fd = os.open(tinta, os.O_RDONLY)
		try:
			os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
		finally:
			os.close(fd)
	except (AttributeError, OSError):
		pass
	return _citeste(tinta, MAXIM_STARTUP + 1) == date


def alege(loc, radacina=None, monteaza=None):
	"""Scrie STARTUP din STARTUP_<loc> dupa o verificare din nou a locului. (True, imaginea) sau (False, motivul)."""
	stare = locuri(radacina, monteaza)
	gasit = [l for l in stare["locuri"] if l["fel"] == "emmc" and l["loc"] == str(loc)]
	if not gasit:
		return False, _(NEGASIT)
	l = gasit[0]
	if l["acum"]:
		return False, _(DEJA)
	if not l["alegere"]:
		return False, _(REFUZ) % l["loc"]
	boot, demonteaza = _deschideBoot(radacina, monteaza)
	if not boot:
		return False, _(EROARE)
	try:
		date = _citeste(os.path.join(boot, l["fisier"]), MAXIM_STARTUP + 1)
		if date != l["date"] or not verificaEmmc(citesteStartup(date), parametri(linieComanda(radacina))):
			return False, _(EROARE)
		vechi = _citeste(os.path.join(boot, FISIER_STARTUP), MAXIM_STARTUP + 1)
		if vechi is not None and not _scrieAtomic(boot, COPIE, vechi):
			return False, _(EROARE)
		if not _scrieAtomic(boot, FISIER_STARTUP, date):
			if vechi is not None:
				_scrieAtomic(boot, FISIER_STARTUP, vechi)
			return False, _(EROARE)
		_log("STARTUP = %s (%s)" % (l["fisier"], l["imagine"]))
		return True, l["imagine"]
	except (IOError, OSError) as e:
		_log("scrierea: %r" % e)
		return False, _(EROARE)
	finally:
		if demonteaza:
			demonteaza()


def inapoi(radacina=None, monteaza=None):
	"""STARTUP inapoi din STARTUP.hds-inainte (repornirea a fost oprita pe ecran). True daca s-a pus la loc."""
	boot, demonteaza = _deschideBoot(radacina, monteaza)
	if not boot:
		return False
	try:
		vechi = _citeste(os.path.join(boot, COPIE), MAXIM_STARTUP + 1)
		if vechi is None or not citesteStartup(vechi):
			return False
		ok = _scrieAtomic(boot, FISIER_STARTUP, vechi)
		_log("STARTUP pus inapoi: %s" % ok)
		return ok
	except (IOError, OSError) as e:
		_log("inapoi: %r" % e)
		return False
	finally:
		if demonteaza:
			demonteaza()


def reporneste(sesiune, loc, dupa_ms=0, fabrica_ceas=None, radacina=None, monteaza=None, Standby=None):
	"""Scrie alegerea, apoi TryQuitMainloop(2) pe receptor (dupa `dupa_ms`). Daca omul spune Nu la intrebarea de pe
	ecran (o inregistrare, o lucrare), fereastra se inchide cu apel inapoi si STARTUP se pune la loc; la Da enigma2 iese
	si apelul nu mai vine. (True, imaginea) sau (False, motivul)."""
	if sesiune is None:
		return False, _(EROARE)
	ok, text = alege(loc, radacina, monteaza)
	if not ok:
		return ok, text

	def renuntat(*_a):
		inapoi(radacina, monteaza)

	def acum():
		try:
			S = Standby
			if S is None:
				from Screens import Standby as S
			sesiune.openWithCallback(renuntat, S.TryQuitMainloop, 2)
		except Exception as e:
			_log("repornirea: %r" % e)
			inapoi(radacina, monteaza)

	if dupa_ms <= 0:
		acum()
	else:
		from Components import HdsAlimentare
		HdsAlimentare.programeaza(acum, dupa_ms, fabrica_ceas, nume="pornire-multipla")
	return True, text
