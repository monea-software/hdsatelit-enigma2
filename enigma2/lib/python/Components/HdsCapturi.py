# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCapturi.py: capturile de ecran ale receptorului (tasta de captura, galeria, forumul receptorului, pagina web).
#
# Locurile:
# - "stick": o partitie montata de pe o stocare externa (stick, cititor de carduri sau disc USB), scrisa si locala:
#   nu in RAM, nu din retea, nu pe memoria interna (discul radacinii). Stick-ul are intaietate fata de un disc. Capturile
#   stau in <punct>/hds-capturi/;
# - "memorie": memoria receptorului, DOSAR_MEMORIE, cu o limita mica (MEMORIE_MAX_CAPTURI si MEMORIE_MAX_OCTETI; cele
#   mai vechi se sterg) si fara scriere cand ar ramane sub LIBER_MINIM octeti liberi.
# Numele: captura-AAAA-LL-ZZ-HHMMSS.jpg (ora locala; doua capturi in aceeasi secunda primesc -2, -3...). Pozele urcate
# din web pot fi si PNG: captura-...png. Numai numele de felul acesta se citesc, se dau si se sterg (lista alba).
#
# Captura (fa): grab, JPEG, toata rezolutia. Imaginea canalului intra numai cand decodorul e gata, dupa paza capturilor
# din interfata web (Plugins/Extensions/HdsWebControl/captura_sigura.py); altfel, sau fara paza, numai meniurile
# (grab -o). Nimic in standby. fa() asteapta grab-ul (cel mult TIMP_GRAB_S, apoi procesul e oprit): se cheama pe un
# fir; LucrareCaptura (faPeFir) e firul gata facut.
#
# Tasta de captura (porneste, din mytest.py): legare globala a tastelor, ca tasta HELP (Components/HdsAjutor.py):
# KEY_CONTEXT_MENU (a treia tasta cu desen de ecran de pe telecomanda Viper) si KEY_SYSRQ (Print Screen pe o tastatura
# USB), oriunde in afara de standby. Dupa captura, un mesaj mic sus in dreapta (Screens/HdsForumReceptor.py,
# HdsCapturaSalvata), care nu ia tastele; mesajul de dinainte se ascunde inainte de captura, ca sa nu intre in ea.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct (_proba schimba sursele).

import os
import re
import shutil
import stat
import subprocess
import threading
import time

NUME_DOSAR = "hds-capturi"
DOSAR_MEMORIE = "/home/root/hds-capturi"
MEMORIE_MAX_CAPTURI = 15
MEMORIE_MAX_OCTETI = 20 * 1024 * 1024
LIBER_MINIM = 50 * 1024 * 1024
# loc liber cerut pe stick peste marimea capturii
LIBER_STICK = 1024 * 1024
# o poza adaugata din web: cat primeste forumul pe o poza (25 de bucati de 160 KB)
ADAUGA_MAX = 25 * 160 * 1024
CALITATE_JPEG = 85
TIMP_GRAB_S = 10
OPRIRE_GRAB_S = 2
CAPTURA_MINIMA = 1024

STICK = "stick"
MEMORIE = "memorie"

# locurile in care se monteaza stocarea externa (numele stabile si montarile udev)
PREFIXE = ("/media/", "/run/media/", "/mnt/")
# dispozitivele de stocare locala (fara retea: sursa unei partajari nu incepe cu /dev/)
_DISPOZITIV = re.compile(r"\A/dev/(sd[a-z]+|mmcblk[0-9]+|nvme[0-9]+n[0-9]+|hd[a-z]+|vd[a-z]+)p?[0-9]*\Z")
_NUME = re.compile(r"\Acaptura-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}(?:-[0-9]{1,3})?\.(?:jpg|png)\Z")
_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"

# sursele citite, schimbate de probele de pe PC: montarile, /sys/block, /proc/cmdline, statvfs, realpath, dispozitivul
# radacinii, starea de standby si comanda de captura
_proba = {}

_lacat = threading.RLock()


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _t(text):
	"""Traducerea enigma2, sau textul insusi (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsCapturi] %s" % text)


def _stocare():
	from Components import HdsStocare
	return HdsStocare


# ------------------------------------------------------------------ locurile

def _montari():
	m = _proba.get("montari")
	if m is not None:
		return m
	return _stocare()._montari()


def _discul(dispozitiv):
	"""/dev/sda1 -> sda, /dev/mmcblk1p1 -> mmcblk1; "" pentru altceva."""
	m = _DISPOZITIV.match(dispozitiv or "")
	return m.group(1) if m else ""


def discRadacina(montari=None):
	"""Discul memoriei interne (al radacinii '/'): din montari, apoi din root= din /proc/cmdline; "" daca nu se stie."""
	disc = ""
	for punct, _fel, disp in (montari if montari is not None else _montari()):
		if punct == "/":
			d = disp
			if d == "/dev/root":
				try:
					d = (_proba.get("realpath") or os.path.realpath)(d)
				except (OSError, ValueError):
					pass
			disc = _discul(d) or disc
	if disc:
		return disc
	try:
		with open(_proba.get("cmdline", "/proc/cmdline"), "r", encoding="utf-8", errors="replace") as f:
			m = re.search(r"(?:^|\s)root=(\S+)", f.read())
		if m:
			return _discul(m.group(1))
	except (OSError, IOError):
		pass
	return ""


def _amovibil(disc):
	try:
		with open(os.path.join(_proba.get("sys_block", "/sys/block"), disc, "removable"), "r", encoding="utf-8",
				errors="replace") as f:
			return f.read().strip() == "1"
	except (OSError, IOError):
		return False


def _stick():
	"""(punct, amovibil) pentru stocarea externa folosita acum, sau None. Stick-ul (removable = 1) are intaietate;
	la egalitate, primul montat sub /media/."""
	montari = _montari()
	radacina = discRadacina(montari) or "mmcblk0"
	S = _stocare()
	vazute = set()
	gasite = []
	for punct, fel, disp in montari:
		if not (punct + "/").startswith(PREFIXE) or fel in S.FS_IN_MEMORIE:
			continue
		disc = _discul(disp)
		if not disc or disc == radacina or disp in vazute:
			continue
		try:
			bun, _motiv = S.verificaDisc(punct, montari, _proba.get("dev_radacina"), _proba.get("statvfs"),
				_proba.get("realpath"))
		except Exception as e:
			_jurnal("locul %s: %s" % (punct, e))
			bun = False
		if not bun:
			continue
		vazute.add(disp)
		gasite.append((0 if _amovibil(disc) else 1, 0 if punct.startswith(PREFIXE[0]) else 1, len(gasite), punct))
	if not gasite:
		return None
	gasite.sort()
	return gasite[0][3], gasite[0][0] == 0


def locuri():
	"""[{cheie, nume, dosar, disponibil}]: intai stick-ul (sau discul USB), apoi memoria receptorului."""
	s = _stick()
	if s is None:
		stick = {"cheie": STICK, "nume": _t("Stick USB"), "dosar": "", "disponibil": False, "amovibil": True}
	else:
		stick = {"cheie": STICK, "nume": _t("Stick USB") if s[1] else _t("Disc USB"),
			"dosar": s[0].rstrip("/") + "/" + NUME_DOSAR, "disponibil": True, "amovibil": s[1]}
	memorie = {"cheie": MEMORIE, "nume": _t("Memoria receptorului"), "dosar": _proba.get("memorie", DOSAR_MEMORIE),
		"disponibil": True, "amovibil": False}
	return [stick, memorie]


def _loc(cheie, lista_locuri=None):
	for l in (lista_locuri if lista_locuri is not None else locuri()):
		if l["cheie"] == cheie:
			return l
	return None


def locImplicit(lista_locuri=None):
	"""Unde merge o captura noua: pe stick cand e, altfel in memoria receptorului."""
	lista_locuri = lista_locuri if lista_locuri is not None else locuri()
	s = _loc(STICK, lista_locuri)
	return s if s and s["disponibil"] else _loc(MEMORIE, lista_locuri)


# ------------------------------------------------------------------ lista, calea, stergerea

def numeValid(nume):
	return isinstance(nume, str) and bool(_NUME.match(nume))


def _fisiere(dosar):
	"""[(nume, cale, cand, marime)] ale capturilor din dosar (numai fisiere obisnuite cu nume din lista alba)."""
	rez = []
	try:
		nume = os.listdir(dosar)
	except (OSError, IOError):
		return rez
	for n in nume:
		if not numeValid(n):
			continue
		c = os.path.join(dosar, n)
		try:
			s = os.lstat(c)
		except OSError:
			continue
		if not stat.S_ISREG(s.st_mode):
			continue
		rez.append((n, c, int(s.st_mtime), int(s.st_size)))
	return rez


def lista(cheie=None):
	"""[{nume, cale, loc, cand (secunde UNIX), marime}] din locul `cheie` (sau din amandoua), cele mai noi primele."""
	rez = []
	for l in locuri():
		if (cheie is not None and l["cheie"] != cheie) or not l["disponibil"] or not l["dosar"]:
			continue
		for n, c, cand, marime in _fisiere(l["dosar"]):
			rez.append({"nume": n, "cale": c, "loc": l["cheie"], "cand": cand, "marime": marime})
	rez.sort(key=lambda x: (x["cand"], x["nume"]), reverse=True)
	return rez


def cale(nume, loc):
	"""Calea sigura a capturii `nume` din locul `loc`, sau None (nume din afara listei albe, loc lipsa, fisier lipsa
	sau care nu e fisier obisnuit)."""
	if not numeValid(nume):
		return None
	l = _loc(loc)
	if l is None or not l["disponibil"] or not l["dosar"]:
		return None
	c = os.path.join(l["dosar"], nume)
	try:
		if not stat.S_ISREG(os.lstat(c).st_mode):
			return None
	except OSError:
		return None
	return c


def sterge(nume, loc):
	"""-> (reusit, mesaj)."""
	c = cale(nume, loc)
	if c is None:
		return False, _t("Captura nu mai există.")
	with _lacat:
		try:
			os.remove(c)
		except OSError as e:
			_jurnal("stergerea %s: %s" % (nume, e))
			return False, _t("Captura nu s-a putut șterge.")
	return True, ""


# ------------------------------------------------------------------ scrierea

def _liber(dosar):
	f = _proba.get("liber")
	if f is not None:
		return f(dosar)
	try:
		return int(shutil.disk_usage(dosar).free)
	except (OSError, ValueError):
		return None


def _numeNou(dosar, extensie, acum=None):
	baza = time.strftime("captura-%Y-%m-%d-%H%M%S", time.localtime(time.time() if acum is None else acum))
	n = "%s.%s" % (baza, extensie)
	k = 2
	while os.path.lexists(os.path.join(dosar, n)) and k < 1000:
		n = "%s-%d.%s" % (baza, k, extensie)
		k += 1
	return n


def _scrie(cale_fisier, octeti):
	"""Fisier .nou langa cel final, fsync, os.replace (o cadere nu lasa o captura pe jumatate)."""
	nou = cale_fisier + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale_fisier)
	except BaseException:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def limiteazaMemoria(dosar=None):
	"""In memoria receptorului: cel mult MEMORIE_MAX_CAPTURI si MEMORIE_MAX_OCTETI; cele mai vechi se sterg."""
	dosar = dosar or _proba.get("memorie", DOSAR_MEMORIE)
	with _lacat:
		f = sorted(_fisiere(dosar), key=lambda x: (x[2], x[0]))
		total = sum(x[3] for x in f)
		while f and (len(f) > MEMORIE_MAX_CAPTURI or total > MEMORIE_MAX_OCTETI):
			n, c, _cand, marime = f.pop(0)
			try:
				os.remove(c)
			except OSError as e:
				_jurnal("limita memoriei, %s: %s" % (n, e))
			total -= marime


def _salveaza(octeti, extensie, l, acum=None):
	"""Scrie poza in locul `l` -> (reusit, cale_sau_mesaj)."""
	dosar = l["dosar"]
	with _lacat:
		try:
			os.makedirs(dosar, exist_ok=True)
		except OSError as e:
			_jurnal("dosarul %s: %s" % (dosar, e))
			return False, _t("Captura nu s-a putut salva.")
		liber = _liber(dosar)
		if l["cheie"] == MEMORIE:
			if liber is not None and liber - len(octeti) < LIBER_MINIM:
				return False, _t("Nu mai e loc în memoria receptorului pentru capturi. Pune un stick USB.")
		elif liber is not None and liber < len(octeti) + LIBER_STICK:
			return False, _t("Nu mai e loc pe stick pentru capturi.")
		n = _numeNou(dosar, extensie, acum)
		c = os.path.join(dosar, n)
		try:
			_scrie(c, octeti)
		except (OSError, IOError) as e:
			_jurnal("scrierea %s: %s" % (c, e))
			return False, _t("Captura nu s-a putut salva.")
		if l["cheie"] == MEMORIE:
			limiteazaMemoria(dosar)
	return True, c


def inStandby():
	f = _proba.get("standby")
	if f is not None:
		return bool(f())
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


def _paza():
	"""Paza capturilor din interfata web (cand intra imaginea canalului), sau None."""
	try:
		from Plugins.Extensions.HdsWebControl import captura_sigura
		return captura_sigura
	except Exception:
		return None


def imagineaCanalului():
	"""True cand captura poate lua si imaginea canalului (decodorul e gata, nu in standby); altfel numai meniurile.
	Pe firul enigma2 (citeste starea receptorului)."""
	f = _proba.get("imagine")
	if f is not None:
		return bool(f())
	cs = _paza()
	if cs is None:
		return False
	try:
		ce, _motiv = cs.decide("all")
	except Exception as e:
		_jurnal("paza capturii: %s" % e)
		return False
	return ce == "da"


def _comandaGrab(cu_imagine):
	return ["grab", "-q", "-s", "-j", str(CALITATE_JPEG)] + ([] if cu_imagine else ["-o"])


def _ruleaza(comanda):
	"""(cod, octeti) ai lui grab; (None, b"") cand lipseste sau nu termina in TIMP_GRAB_S. Dupa kill() asteptarea e
	marginita (un grab blocat in driver nu tine firul pe loc)."""
	f = _proba.get("grab")
	if f is not None:
		return f(comanda)
	try:
		p = subprocess.Popen(comanda, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
	except (OSError, ValueError) as e:
		_jurnal("grab: %s" % e)
		return None, b""
	try:
		iesire, _erori = p.communicate(timeout=TIMP_GRAB_S)
		return p.returncode, iesire or b""
	except subprocess.TimeoutExpired:
		_jurnal("grab nu a terminat in %d s" % TIMP_GRAB_S)
		try:
			p.kill()
		except OSError:
			pass
		try:
			p.communicate(timeout=OPRIRE_GRAB_S)
		except subprocess.TimeoutExpired:
			for flux in (p.stdout,):
				try:
					flux.close()
				except Exception:
					pass
		return None, b""


def _fa(cu_imagine=None, loc=None):
	"""fa(), plus daca stick-ul e amovibil (pentru mesajul de dupa captura) -> (reusit, cale_sau_mesaj, loc, amovibil)."""
	lista_locuri = locuri()
	l = _loc(loc, lista_locuri) if loc else locImplicit(lista_locuri)
	cheie = l["cheie"] if l else (loc or MEMORIE)
	amovibil = bool(l and l.get("amovibil"))
	if l is None or not l["disponibil"]:
		return False, _t("Stick-ul nu mai e conectat."), cheie, amovibil
	if inStandby():
		return False, _t("Receptorul e în standby: captura nu se face."), cheie, amovibil
	if cu_imagine is None:
		cu_imagine = imagineaCanalului()
	if cu_imagine:
		cs = _paza()
		if cs is not None:
			try:
				cs.incepeVideo()
			except Exception:
				pass
	cod, date = _ruleaza(_comandaGrab(cu_imagine))
	if cod != 0 or not date.startswith(_JPEG) or len(date) < CAPTURA_MINIMA:
		_jurnal("grab: cod %s, %d octeti" % (cod, len(date or b"")))
		return False, _t("Captura nu s-a putut face."), cheie, amovibil
	ok, rez = _salveaza(date, "jpg", l)
	return ok, rez, cheie, amovibil


def fa(cu_imagine=None, loc=None):
	"""Captura de acum -> (reusit, cale_sau_mesaj, loc). cu_imagine: True cu imaginea canalului, False numai meniurile,
	None dupa paza (imagineaCanalului, citita aici). loc: "stick", "memorie" sau None (stick-ul cand e). Asteapta
	grab-ul (cel mult TIMP_GRAB_S): se cheama pe un fir (sau faPeFir)."""
	return _fa(cu_imagine, loc)[:3]


def felPoza(octeti):
	""""jpg", "png" sau "" dupa primii octeti."""
	if octeti[:3] == _JPEG:
		return "jpg"
	if octeti[:8] == _PNG:
		return "png"
	return ""


def adauga(octeti, loc=None):
	"""O poza urcata din web pusa intre capturi -> (reusit, nume_sau_mesaj). Numai JPEG sau PNG (dupa primii octeti),
	cel mult ADAUGA_MAX."""
	if not isinstance(octeti, (bytes, bytearray)) or not octeti:
		return False, _t("Poza trebuie să fie JPG sau PNG.")
	fel = felPoza(octeti)
	if not fel:
		return False, _t("Poza trebuie să fie JPG sau PNG.")
	if len(octeti) > ADAUGA_MAX:
		return False, _t("Poza e prea mare: cel mult %d MB.") % int(round(ADAUGA_MAX / 1000000.0))
	lista_locuri = locuri()
	l = _loc(loc, lista_locuri) if loc else locImplicit(lista_locuri)
	if l is None or not l["disponibil"]:
		return False, _t("Stick-ul nu mai e conectat.")
	ok, rez = _salveaza(bytes(octeti), fel, l)
	return (True, os.path.basename(rez)) if ok else (False, rez)


# ------------------------------------------------------------------ captura pe un fir

class LucrareCaptura(threading.Thread):
	"""fa() pe un fir: .gata, .reusit, .cale (sau ""), .mesaj (text pentru om la nereusita), .loc, .amovibil."""

	def __init__(self, cu_imagine, loc=None):
		threading.Thread.__init__(self, name="hds-captura")
		self.daemon = True
		self.cu_imagine = cu_imagine
		self.loc_cerut = loc
		self.gata = False
		self.reusit = False
		self.cale = ""
		self.mesaj = ""
		self.loc = loc or ""
		self.amovibil = True

	def run(self):
		try:
			ok, rez, self.loc, self.amovibil = _fa(self.cu_imagine, self.loc_cerut)
			self.reusit = ok
			if ok:
				self.cale = rez
			else:
				self.mesaj = rez
		except Exception as e:
			_jurnal("captura: %s" % e)
			self.mesaj = _t("Captura nu s-a putut face.")
		self.gata = True


def faPeFir(cu_imagine=None, loc=None):
	"""Porneste captura pe un fir si o intoarce (LucrareCaptura). Paza imaginii se citeste aici, pe firul care cheama
	(firul enigma2)."""
	if cu_imagine is None:
		cu_imagine = imagineaCanalului()
	t = LucrareCaptura(cu_imagine, loc)
	t.start()
	return t


def textSalvata(loc, amovibil=True):
	"""Primul rand al mesajului de dupa captura."""
	if loc == MEMORIE:
		return _t("Captură salvată în memoria receptorului")
	return _t("Captură salvată pe stick") if amovibil else _t("Captură salvată pe disc")


# ------------------------------------------------------------------ tasta de captura

PRIORITATE_TASTE = -0x7FFFFFFE
KEY_CONTEXT_MENU = 438
KEY_SYSRQ = 99
TASTE = (KEY_CONTEXT_MENU, KEY_SYSRQ)
FLAG_MAKE = 0
PAS_MS = 200
# dupa ascunderea mesajului de dinainte, o clipa pentru redesenarea ecranului inainte de grab
ASTEPTARE_ASCUNDERE_MS = 150
MESAJ_S = 3

_stare = {"sesiune": None, "lucru": None, "ceas": None, "mesaj": None, "ceas_mesaj": None, "pornire": None}
# cine vrea sa afle de o captura noua facuta cu tasta (galeria deschisa): functie(cale), pe firul enigma2
_ascultatori = []


def asculta(functie):
	if functie not in _ascultatori:
		_ascultatori.append(functie)


def nuMaiAsculta(functie):
	if functie in _ascultatori:
		_ascultatori.remove(functie)


def _ceas(functie):
	from enigma import eTimer
	t = eTimer()
	t.callback.append(functie)
	return t


def captureaza(sesiune=None):
	"""Captura ceruta de om (tasta sau o tasta colorata tinuta apasata): pe firul enigma2, fara sa astepte. -> True
	cand a pornit."""
	sesiune = sesiune or _stare.get("sesiune")
	if sesiune is None or _stare.get("lucru") is not None or _stare.get("pornire") is not None:
		return False
	if inStandby():
		return False
	_stare["sesiune"] = sesiune
	ascuns = _ascundeMesajul()
	try:
		if ascuns:
			t = _stare.get("pornire") or _ceas(_pornesteLucrul)
			_stare["pornire"] = t
			t.start(ASTEPTARE_ASCUNDERE_MS, True)
		else:
			_pornesteLucrul()
	except Exception as e:
		_jurnal("pornirea capturii: %s" % e)
		_stare["pornire"] = None
		return False
	return True


def _pornesteLucrul():
	_stare["pornire"] = None
	try:
		_stare["lucru"] = faPeFir()
		c = _stare.get("ceas") or _ceas(_asteapta)
		_stare["ceas"] = c
		c.start(PAS_MS, False)
	except Exception as e:
		_jurnal("captura: %s" % e)
		_stare["lucru"] = None


def _asteapta():
	lucru = _stare.get("lucru")
	if lucru is None:
		_stare["ceas"].stop()
		return
	if not lucru.gata:
		return
	_stare["ceas"].stop()
	_stare["lucru"] = None
	if lucru.reusit:
		titlu = textSalvata(lucru.loc, lucru.amovibil)
		detaliu = os.path.basename(lucru.cale)
		if lucru.loc == STICK:
			detaliu = "%s · %s" % (NUME_DOSAR, detaliu)
		_arataMesajul(titlu, detaliu)
		for f in list(_ascultatori):
			try:
				f(lucru.cale)
			except Exception as e:
				_jurnal("dupa captura: %s" % e)
	else:
		_arataMesajul(lucru.mesaj or _t("Captura nu s-a putut face."), "")


def _arataMesajul(titlu, detaliu):
	sesiune = _stare.get("sesiune")
	try:
		m = _stare.get("mesaj")
		if m is None:
			from Screens.HdsForumReceptor import HdsCapturaSalvata
			m = sesiune.instantiateDialog(HdsCapturaSalvata)
			_stare["mesaj"] = m
		m.arata(titlu, detaliu)
		m.show()
		c = _stare.get("ceas_mesaj") or _ceas(_ascundeMesajul)
		_stare["ceas_mesaj"] = c
		c.start(MESAJ_S * 1000, True)
	except Exception as e:
		_jurnal("mesajul capturii: %s" % e)


def _ascundeMesajul():
	"""Ascunde mesajul de dupa captura -> True daca era pe ecran."""
	m = _stare.get("mesaj")
	c = _stare.get("ceas_mesaj")
	if c is not None:
		c.stop()
	if m is None:
		return False
	try:
		vizibil = bool(m.shown)
		m.hide()
		return vizibil
	except Exception:
		return False


class _Tasta(object):
	"""Legarea globala a tastelor de captura: apasarea face captura; ridicarea si repetarea tastei prinse nu mai merg la
	ecranele de dedesubt."""

	def __init__(self, sesiune):
		self.sesiune = sesiune
		self.prinsa = False

	def __call__(self, cod, steag):
		if cod not in TASTE:
			return 0
		if steag != FLAG_MAKE:
			return 1 if self.prinsa else 0
		self.prinsa = False
		try:
			if inStandby():
				return 0
			captureaza(self.sesiune)
			self.prinsa = True
			return 1
		except Exception as e:
			_jurnal("tasta de captura: %s" % e)
			return 0


_legata = [None]


def porneste(sesiune):
	"""Leaga tastele de captura pentru toate ecranele (o data, din mytest.py). Nu citeste nimic de pe disc."""
	if _legata[0] is not None:
		return
	from enigma import eActionMap
	t = _Tasta(sesiune)
	eActionMap.getInstance().bindAction("", PRIORITATE_TASTE, t)
	_legata[0] = t
	_stare["sesiune"] = sesiune
