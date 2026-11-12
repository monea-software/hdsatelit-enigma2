# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSwap.py: fisierul de swap (memorie virtuala) pe un disc montat. O singura logica pentru ecranul de pe televizor
# (Screens/SwapManager.py, Meniu > Setari > Inregistrari & Stocare > Swap File) si pentru pagina web /swap
# (Plugins/Extensions/HdsWebControl/disc_web.py).
#
# - discuriMontate(): discurile montate din harddiskmanager.getMountedPartitions(), fara / si /boot, numai cele al caror
#   punct de montare e un dosar; nimic detectat aici.
# - swapuriActive(): /proc/swaps, cu spatiile din cai decodate (\040, unescapeMountPath), altfel un swap activ de pe un
#   stick cu spatiu in eticheta ar parea inactiv.
# - activeaza(punct): pe discul ales, fisierul CALE_SWAPFILE de MARIME_MB_IMPLICITA MB: fallocate, iar daca nu merge (de
#   exemplu pe FAT) dd din /dev/zero; apoi drepturile 600, mkswap si swapon. opreste(punct): swapoff pe acel fisier.
#   Comenzile merg cu Components.Console, ca liste de argumente (program, argv0, argumente), fara shell, una dupa alta,
#   pe firul enigma2, fara sa-l opreasca. Cel mult o lucrare deodata (televizorul si pagina web impart aceeasi stare).
# - stareLucru(): ce se lucreaza acum sau ce s-a terminat ultima data (pagina web o arata, ecranul isi reincarca lista).
#
# 0.7.4 (Ozgur, Vu+ Solo SE pe stickul chkroot, 11.11.2026: celelalte imagini pornesc singure partitia swap de pe stick,
# la noi ecranul nu vedea nici stickul, fiindca Components/Harddisk.py tine tot discul sistemului deoparte):
# - porneste() (din mytest.py): la 20 s si la 90 s dupa pornire, pe un fir, daca nu e niciun swap pornit (zram nu
#   conteaza), pornesteSingur() da swapon pe prima partitie TYPE="swap" (blkid) de pe un disc extern /dev/sd*, intai cea
#   de pe discul imaginii; daca nu e niciuna, pe un swapfile.hds facut din ecran (pe discul imaginii sau pe o partitie
#   montata a unui disc extern). Numai swapon: fara mkswap, fara stergeri, fara scrieri in fstab. Aceeasi regula pentru
#   partitie si fisier, fara nicio setare: swap-ul gasit porneste singur la fiecare pornire a receptorului (o data,
#   semnul din /tmp: nu si la o repornire a interfetei); oprit din ecran, ramane oprit pana la urmatoarea pornire
#   (textPornire(), pe televizor si in web).
# - discul de pe care merge imaginea (radacina pe USB, Components/HdsRadacinaUsb.descrieRadacina) apare in lista ca loc
#   pentru swapfile.hds, cu nume propriu (harddiskmanager ii zice "Internal Flash"); memoria interna niciodata.
# - o partitie swap pornita apare in lista (fel="partitie") si se poate opri: altfel formatarea discului ar cere oprirea
#   ei (HdsDiscuri.folosire) dintr-un ecran care nu o vede.
# - activeaza() verifica intai locul liber (fisierul si o rezerva de MARJA_MB).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau managerul de discuri si consola lor.

import os
import re
import time

CALE_SWAPFILE = "swapfile.hds"  # numele fisierului, facut in radacina discului ales
MARIME_MB_IMPLICITA = 512
MARJA_MB = 64  # ce ramane liber pe disc dupa fisierul de swap
CALE_SWAPS = "/proc/swaps"
CALE_MOUNTS = "/proc/mounts"
EXCLUSE = ("/", "/boot")
FEL_FISIER = "fisier"
FEL_PARTITIE = "partitie"
# partitiile (sau discurile intregi) de pe un disc extern USB/SATA; memoria interna (mmcblk, mtd), zram si loop nu
_PARTITIE_RX = re.compile(r"/dev/sd[a-z]+[0-9]*\Z")
_CAMP_BLKID_RX = re.compile(r'\b([A-Z0-9_]+)="([^"\n]*)"')
# sisteme de fisiere pe care nu se cauta swapfile.hds la pornire (in memorie, prin retea, prin fuse)
_FS_FARA_SWAP = ("tmpfs", "ramfs", "devtmpfs", "autofs", "nfs", "nfs4", "cifs", "smbfs", "smb3", "fuse", "fuseblk",
	"squashfs", "overlay", "proc", "sysfs")
INTARZIERI_PORNIRE_S = (20, 90)


LUCRU_IN_LUCRU = "in_lucru"
LUCRU_GATA = "gata"
LUCRU_EROARE = "eroare"
ACTIVEAZA = "activeaza"
OPRESTE = "opreste"

_OCTAL = re.compile(r"\\([0-7]{3})")

_stare = {"lucru": None}
_consola = [None]
_inventar = {"cauta": False, "discuri": [], "active": [], "semn": None, "eroare": False}
_citire = None
_revizie_inventar = 0


def semnDiscuri(hm=None):
	"""Lista managerului din memorie; nu verifica punctele de montare."""
	manager = _hm(hm)
	return (id(manager), tuple((id(p), p.mountpoint, getattr(p, "device", None))
		for p in manager.partitions), _revizie_inventar)


def cereInventar(hm=None, reface=False):
	"""Citeste o data la deschidere, dupa hotplug sau dupa comanda, pe fir separat."""
	global _citire
	semn = semnDiscuri(hm)
	if _inventar["cauta"] or inLucru():
		return _inventar
	if not reface and _inventar["semn"] == semn:
		return _inventar
	_inventar.update(cauta=True, eroare=False)

	def citeste():
		active = swapuriActive()
		return discuri(hm, active), active

	def gata(rez, eroare):
		global _citire
		_citire = None
		_inventar.update(cauta=False, semn=semn, eroare=bool(eroare))
		if not eroare and rez is not None:
			_inventar.update(discuri=rez[0], active=rez[1])

	try:
		from Components.HdsImportSurse import Lucrare
		_citire = Lucrare(citeste, gata)
	except Exception:
		_inventar["cauta"] = False
		raise
	return _inventar


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _decodeaza(cale):
	"""\\040 si celelalte coduri octale din /proc/swaps si /proc/mounts (ca Components/Harddisk.unescapeMountPath)."""
	return _OCTAL.sub(lambda m: chr(int(m.group(1), 8)), cale)


def swapuriActive(cale_swaps=None):
	"""Fisierele si partitiile de swap active acum, din /proc/swaps (fara nicio comanda)."""
	active = []
	try:
		with open(cale_swaps or CALE_SWAPS, encoding="utf-8", errors="surrogateescape") as f:
			for linie in f.readlines()[1:]:
				parti = linie.split()
				if parti:
					active.append(_decodeaza(parti[0]))
	except OSError:
		pass
	return active


def _hm(hm=None):
	if hm is not None:
		return hm
	from Components.Harddisk import harddiskmanager
	return harddiskmanager


_radacina = {}


def _radacinaUsb():
	"""Unde merge imaginea (Components/HdsRadacinaUsb.descrieRadacina: {"fel": "usb", "disc": "sda", ...}, "nand" sau
	"necunoscut"), citit o data: radacina nu se muta cat merge interfata. Numai /proc si /sys, fara comenzi."""
	if "rez" not in _radacina:
		try:
			from Components.HdsRadacinaUsb import descrieRadacina
			_radacina["rez"] = descrieRadacina()
		except Exception as eroare:
			print("[HdsSwap] radacina: %s" % eroare)
			_radacina["rez"] = {"fel": "necunoscut"}
	return _radacina["rez"]


def _dispozitiv(cale):
	return os.stat(cale).st_dev


def _liber(cale):
	"""Octetii liberi pe discul lui `cale`, sau None cand nu se pot citi (atunci hotaraste comanda)."""
	try:
		import shutil
		return shutil.disk_usage(cale).free
	except (OSError, ValueError, AttributeError):
		return None


class _DiscImagine(object):
	"""Randul discului de pe care merge imaginea (radacina pe USB), cu numele lui."""

	def __init__(self):
		self.mountpoint = "/"
		self.description = _("Discul USB al imaginii")


def _radacinaInLista(parti):
	"""Partitia imaginii e montata si in alt loc din lista (de pilda /media/hdd)? Atunci ramane numai acolo."""
	try:
		radacina = _dispozitiv("/")
	except OSError:
		return False
	for p in parti:
		try:
			if _dispozitiv(p.mountpoint) == radacina:
				return True
		except OSError:
			continue
	return False


def discuriMontate(hm=None, radacina=None):
	"""Partitiile montate pe care se poate face swap: fara / si /boot, numai cu punctul de montare un dosar. Cand
	imaginea merge de pe un stick sau un disc USB (chkroot), si discul ei, primul, ca "/" (radacina, fisierul ajunge
	pe stick); memoria interna (NAND, eMMC) niciodata."""
	rezultat = []
	for partitie in _hm(hm).getMountedPartitions():
		if partitie.mountpoint and partitie.mountpoint not in EXCLUSE and os.path.isdir(partitie.mountpoint):
			rezultat.append(partitie)
	radacina = _radacinaUsb() if radacina is None else radacina
	if radacina.get("fel") == "usb" and not _radacinaInLista(rezultat):
		rezultat.insert(0, _DiscImagine())
	return rezultat


def estePartitie(punct):
	return bool(_PARTITIE_RX.match(punct or ""))


def caleSwap(punct):
	if estePartitie(punct):
		return punct
	return os.path.join(punct, CALE_SWAPFILE)


def numeDisc(partitie):
	return partitie.description or os.path.basename(partitie.mountpoint.rstrip("/")) or partitie.mountpoint


def _neluat(swap):
	"""Swap-ul din memorie (zram) nu tine locul unui swap pe disc."""
	return os.path.basename(swap).startswith("zram")


def partitiiActive(active=None):
	"""Partitiile de swap pornite acum de pe un disc extern (din /proc/swaps): se vad in lista si se pot opri."""
	active = swapuriActive() if active is None else active
	return [a for a in active if estePartitie(a)]


def discuri(hm=None, active=None):
	"""[{punct, nume, cale, activ, fel}] pentru discurile montate, in ordinea ecranului, apoi partitiile de swap
	pornite (punct = dispozitivul, de pilda /dev/sda3)."""
	active = swapuriActive() if active is None else active
	rez = []
	for p in discuriMontate(hm):
		cale = caleSwap(p.mountpoint)
		rez.append({"punct": p.mountpoint, "nume": numeDisc(p), "cale": cale, "activ": cale in active,
			"fel": FEL_FISIER})
	for dev in partitiiActive(active):
		rez.append({"punct": dev, "nume": _("Partiția de swap %s") % os.path.basename(dev), "cale": dev, "activ": True,
			"fel": FEL_PARTITIE})
	return rez


def textRand(d):
	"""Randul din lista ecranului: numele, punctul de montare, ACTIV sau inactiv."""
	return "%s (%s): %s" % (d["nume"], d["punct"], _("ACTIV") if d["activ"] else _("inactiv"))


def textActive(active=None):
	active = swapuriActive() if active is None else active
	return _("Swap-uri active în acest moment: %s") % (", ".join(active) if active else _("niciunul"))


def textPornire():
	"""Ce spun ecranul si pagina /swap despre pornirea singura (acelasi msgid in TEXTE_PAGINA din disc_web.py)."""
	return _("O partiție de swap de pe un stick sau un disc și fișierul de swap făcut aici pornesc singure la fiecare "
		"pornire a receptorului, dacă nu e alt swap pornit. Oprit de aici, swap-ul rămâne oprit până la următoarea "
		"pornire.")


# ------------------------------------------------------------------ lucrarea

def stareLucru():
	return _stare["lucru"]


def inLucru():
	l = _stare["lucru"]
	return l is not None and l["stare"] == LUCRU_IN_LUCRU


def textLucru(lucru):
	"""Fraza pentru o lucrare: in curs (aceeasi ca pe televizor), terminata bine sau cu eroare."""
	if lucru is None:
		return ""
	punct = lucru["punct"]
	if lucru["stare"] == LUCRU_IN_LUCRU:
		if lucru["fel"] == ACTIVEAZA:
			return _("Se creează fișierul de swap pe %s ...") % punct
		return _("Se oprește swap-ul de pe %s ...") % punct
	if lucru["fel"] == ACTIVEAZA:
		if lucru["stare"] == LUCRU_GATA:
			return _("Swap-ul de pe %s e pornit.") % punct
		return _("Swap-ul nu a pornit pe %s (%s, codul %d).") % (punct, lucru.get("pas") or "", lucru.get("cod") or 0)
	if lucru["stare"] == LUCRU_GATA:
		return _("Swap-ul de pe %s s-a oprit.") % punct
	return _("Swap-ul de pe %s nu s-a oprit (codul %d).") % (punct, lucru.get("cod") or 0)


def _cons(consola=None):
	if consola is not None:
		return consola
	if _consola[0] is None:
		from Components.Console import Console
		_consola[0] = Console()
	return _consola[0]


def _incepe(fel, punct, gata):
	_stare["lucru"] = {"fel": fel, "punct": punct, "stare": LUCRU_IN_LUCRU, "pas": "", "cod": 0, "timp": time.time()}
	_stare["gata"] = gata


def _termina(stare, pas="", cod=0):
	global _revizie_inventar
	lucru = dict(_stare["lucru"], stare=stare, pas=pas, cod=cod)
	_stare["lucru"] = lucru
	_inventar["semn"] = None
	_revizie_inventar += 1
	gata = _stare.pop("gata", None)
	if gata is not None:
		try:
			gata(lucru)
		except Exception as eroare:
			print("[HdsSwap] dupa lucrare: %s" % eroare)


def _discBun(punct, hm=None):
	return any(p.mountpoint == punct for p in discuriMontate(hm))


def _real(cale):
	try:
		return os.path.realpath(cale)
	except (OSError, ValueError):
		return cale


def esteActiv(cale, active=None):
	"""True cand fisierul de swap `cale` e pornit (in /proc/swaps), si sub alt nume al aceleiasi cai: punctul de montare
	din harddiskmanager poate fi un alias al locului scris in /proc/swaps."""
	active = swapuriActive() if active is None else active
	real = _real(cale)
	return any(x == cale or _real(x) == real for x in active)


def motivRefuz(cale, active=None, lstat=None):
	"""De ce nu se face fisierul de swap `cale` acum, sau None. Un swap pornit nu se rescrie: pe kernelul receptorului
	(4.4) fallocate da ETXTBSY, iar dd ar scrie zerouri peste swap-ul in folosinta. Un nume care exista si nu e un
	fisier obisnuit (dosar, legatura simbolica, dispozitiv) nu se atinge: dd ar scrie prin legatura in alta parte."""
	import stat
	if esteActiv(cale, active):
		return _("Swap-ul e deja pornit pe acest disc.")
	try:
		st = (lstat or os.lstat)(cale)
	except OSError:
		return None
	if not stat.S_ISREG(st.st_mode):
		return _("Pe disc există deja %s și nu e un fișier obișnuit. Swap-ul nu se pornește.") % CALE_SWAPFILE
	return None


def activeaza(punct, gata=None, consola=None, hm=None, chmod=None, lstat=None):
	"""Porneste lucrarea pe discul `punct` (numai un disc din discuriMontate). (True, text) daca a pornit, altfel
	(False, motivul). `gata(lucru)` se cheama la sfarsit, pe firul enigma2. Nu porneste peste un swap deja pornit si
	nici peste un swapfile.hds care nu e un fisier obisnuit (motivRefuz)."""
	if inLucru():
		return False, _("Se lucrează deja la un fișier de swap. Așteaptă să se termine.")
	if estePartitie(punct):
		# o partitie nu se formateaza niciodata de aici; pornita, e deja in lista; oprita, porneste la pornire
		if punct in partitiiActive():
			return False, _("Swap-ul e deja pornit pe acest disc.")
		return False, _("Partiția de swap pornește singură la următoarea pornire a receptorului.")
	if not _discBun(punct, hm):
		return False, _("Discul ales nu mai este montat. Alege din nou.")
	cale = caleSwap(punct)
	motiv = motivRefuz(cale, lstat=lstat)
	if motiv:
		return False, motiv
	nevoie = (MARIME_MB_IMPLICITA + MARJA_MB) * 1024 * 1024
	liber = None if os.path.isfile(cale) else _liber(punct)
	if liber is not None and liber < nevoie:
		return False, _("Pe disc nu e destul loc pentru swap: trebuie %d MB liberi.") % (MARIME_MB_IMPLICITA + MARJA_MB)
	cons = _cons(consola)
	chmod = chmod or os.chmod
	_incepe(ACTIVEAZA, punct, gata)

	def dupaSwapon(_date, cod, _extra=None):
		_termina(LUCRU_GATA if cod == 0 else LUCRU_EROARE, "swapon", cod)

	def dupaMkswap(_date, cod, _extra=None):
		if cod != 0:
			_termina(LUCRU_EROARE, "mkswap", cod)
			return
		cons.ePopen(("swapon", "swapon", cale), dupaSwapon)

	def drepturi():
		try:
			chmod(cale, 0o600)
		except OSError:
			_termina(LUCRU_EROARE, "chmod", 1)
			return
		cons.ePopen(("mkswap", "mkswap", cale), dupaMkswap)

	def dupaDd(_date, cod, _extra=None):
		# ca "fallocate ... || dd ...; chmod 600 ... && mkswap ... && swapon ...": drepturile se pun oricum
		drepturi()

	def dupaFallocate(_date, cod, _extra=None):
		if cod == 0:
			drepturi()
			return
		# fallocate lipseste sau nu merge pe acest sistem de fisiere (FAT): dd e mai lent, dar merge oriunde
		cons.ePopen(("dd", "dd", "if=/dev/zero", "of=" + cale, "bs=1M", "count=%d" % MARIME_MB_IMPLICITA), dupaDd)

	cons.ePopen(("fallocate", "fallocate", "-l", "%dM" % MARIME_MB_IMPLICITA, cale), dupaFallocate)
	return True, textLucru(_stare["lucru"])


def opreste(punct, gata=None, consola=None, hm=None):
	"""swapoff pe fisierul de swap al discului `punct` (numai un disc din discuriMontate) sau pe partitia de swap
	`punct` (/dev/sd..., numai una pornita acum). (True, text) sau (False, motivul)."""
	if inLucru():
		return False, _("Se lucrează deja la un fișier de swap. Așteaptă să se termine.")
	if estePartitie(punct):
		# numai o partitie de swap pornita acum (din /proc/swaps)
		if punct not in partitiiActive():
			return False, _("Swap-ul de pe acest disc nu mai e pornit.")
	elif not _discBun(punct, hm):
		return False, _("Discul ales nu mai este montat. Alege din nou.")
	cons = _cons(consola)
	_incepe(OPRESTE, punct, gata)

	def dupaSwapoff(_date, cod, _extra=None):
		_termina(LUCRU_GATA if cod == 0 else LUCRU_EROARE, "swapoff", cod)

	cons.ePopen(("swapoff", "swapoff", caleSwap(punct)), dupaSwapoff)
	return True, textLucru(_stare["lucru"])


# ------------------------------------------------------------------ pornirea singura (0.7.4, Ozgur)

def _ruleaza(args):
	"""Comanda ca lista de argumente, fara shell, cu termen (numai pe firul de lucru)."""
	import subprocess
	p = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
		check=False)
	return p.returncode, p.stdout.decode("utf-8", "replace")


def partitiiSwap(text, disc_radacina=None):
	"""Din iesirea lui blkid: partitiile cu TYPE="swap" de pe un disc extern (/dev/sd*), intai cele de pe discul
	imaginii (disc_radacina, de pilda "sda"), apoi in ordinea numelor. O hibernare de PC (swsuspend), zram, loop, mtd si
	memoria interna (mmcblk) nu se iau."""
	gasite = []
	for linie in (text or "").splitlines():
		sursa, sep, date = linie.partition(":")
		sursa = sursa.strip()
		if not sep or not estePartitie(sursa):
			continue
		if dict(_CAMP_BLKID_RX.findall(date)).get("TYPE") != "swap" or sursa in gasite:
			continue
		gasite.append(sursa)
	return sorted(gasite, key=lambda dev: (re.match(r"/dev/(sd[a-z]+)", dev).group(1) != disc_radacina, dev))


def fisiereSwap(radacina=None, cale_mounts=None, lstat=None):
	"""swapfile.hds facute din ecran, de pornit la pornire: pe discul imaginii (radacina pe USB), apoi pe partitiile
	montate ale discurilor externe /dev/sd* (din /proc/mounts, oriunde ar fi montate: /media/..., /run/media/... al
	montarii de la pornire), fara / si /boot. Numai fisiere obisnuite (nu legaturi, nu dosare)."""
	import stat
	lstat = lstat or os.lstat
	puncte = []
	if (radacina or {}).get("fel") == "usb":
		puncte.append("/")
	try:
		with open(cale_mounts or CALE_MOUNTS, encoding="utf-8", errors="surrogateescape") as f:
			for linie in f:
				p = linie.split()
				if len(p) < 3 or p[2] in _FS_FARA_SWAP or p[2].startswith("fuse.") or not estePartitie(p[0]):
					continue
				punct = _decodeaza(p[1])
				if punct not in EXCLUSE:
					puncte.append(punct)
	except OSError:
		pass
	rez = []
	for punct in puncte:
		cale = caleSwap(punct)
		try:
			if stat.S_ISREG(lstat(cale).st_mode) and cale not in rez:
				rez.append(cale)
		except OSError:
			continue
	return rez


def pornesteSingur(ruleaza=None, cale_swaps=None, radacina=None, cale_mounts=None, lstat=None):
	"""Pe firul de lucru: daca nu e niciun swap pornit, swapon pe prima partitie de swap care merge, apoi pe un
	swapfile.hds. {"stare": "deja" | "pornit" | "nimic", "swap": ..., "radacina": felul radacinii, "candidati": [...],
	"erori": [...]} (tot in jurnalul interfetei, ca un raport de la tester sa spuna ce a gasit). Numai swapon."""
	active = [a for a in swapuriActive(cale_swaps) if not _neluat(a)]
	if active:
		return {"stare": "deja", "swap": active[0]}
	ruleaza = ruleaza or _ruleaza
	radacina = _radacinaUsb() if radacina is None else radacina
	disc = radacina.get("disc") if radacina.get("fel") == "usb" else None
	try:
		cod, text = ruleaza(["blkid"])
	except Exception as eroare:
		cod, text = -1, str(eroare)
	erori = []
	# blkid da 2 cand nu gaseste nimic
	candidati = partitiiSwap(text, disc) if cod == 0 else []
	if cod not in (0, 2):
		erori.append("blkid %s" % cod)
	candidati += fisiereSwap(radacina, cale_mounts, lstat)
	urma = {"radacina": radacina.get("fel"), "candidati": list(candidati)}
	for swap in candidati:
		try:
			cod, text = ruleaza(["swapon", swap])
		except Exception as eroare:
			cod, text = -1, str(eroare)
		if cod == 0:
			return dict(urma, stare="pornit", swap=swap, fel=FEL_PARTITIE if estePartitie(swap) else FEL_FISIER,
				erori=erori)
		erori.append("swapon %s: %s %s" % (swap, cod, (text or "").strip()[:120]))
	return dict(urma, stare="nimic", erori=erori)


_pornire = {"ceas": None, "lucru": None, "pas": 0}
# semnul din /tmp (in memorie, sters la repornirea receptorului): incercarile s-au facut la aceasta pornire, deci o
# repornire a interfetei nu mai porneste un swap oprit din ecran (ramane oprit pana la urmatoarea pornire)
CALE_SEMN_PORNIRE = "/tmp/hds-swap-pornire-facuta"


def porneste():
	"""Chemat din mytest.py: la INTARZIERI_PORNIRE_S dupa pornire (a doua oara pentru discurile care apar mai tarziu),
	pornesteSingur pe un fir; o data pe pornirea receptorului (CALE_SEMN_PORNIRE), nu la fiecare repornire a
	interfetei. Pe firul enigma2 numai un ceas; nimic pe ecran, rezultatul in jurnal."""
	if os.path.exists(CALE_SEMN_PORNIRE):
		print("[HdsSwap] pornirea singura s-a facut deja la aceasta pornire a receptorului")
		return
	from enigma import eTimer
	ceas = eTimer()
	try:
		_pornire["legatura"] = ceas.timeout.connect(_incearca)
	except AttributeError:
		ceas.callback.append(_incearca)
	_pornire.update(ceas=ceas, pas=0)
	ceas.start(INTARZIERI_PORNIRE_S[0] * 1000, True)


def _incearca():
	if inLucru() or _pornire["lucru"] is not None:
		_dupaIncercare({"stare": "amanat"}, None)
		return
	from Components.HdsImportSurse import Lucrare
	_pornire["lucru"] = Lucrare(pornesteSingur, _dupaIncercare)


def _dupaIncercare(rez, eroare):
	global _revizie_inventar
	_pornire["lucru"] = None
	print("[HdsSwap] pornirea singura: %s" % (eroare or rez))
	if rez and rez.get("stare") == "pornit":
		# ecranul si pagina recitesc lista
		_inventar["semn"] = None
		_revizie_inventar += 1
	_pornire["pas"] += 1
	pas = _pornire["pas"]
	if (eroare or not rez or rez.get("stare") not in ("pornit", "deja")) and pas < len(INTARZIERI_PORNIRE_S):
		_pornire["ceas"].start((INTARZIERI_PORNIRE_S[pas] - INTARZIERI_PORNIRE_S[pas - 1]) * 1000, True)
		return
	try:
		with open(CALE_SEMN_PORNIRE, "w") as f:
			f.write("%s\n" % (rez or {}).get("stare", "eroare"))
	except OSError as e:
		print("[HdsSwap] semnul pornirii: %s" % e)
