# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEditorSigle.py: siglele canalelor (piconurile) in editorul de canale: sigla pusa pe un canal (un fisier PNG ales
# sau sigla altui canal), sigla scoasa, siglele redenumite dupa referinta sau dupa nume si siglele care nu mai sunt ale
# niciunui canal din lista.
#
# CUM CAUTA IMAGINEA (Components/Renderer/Picon.py, cauta_sigla): numai dupa referinta. Numele fisierului e facut din
# primele zece campuri ale referintei unite cu "_" (<nume>.png); daca lipseste, cu tipul serviciului 1 (canalele HD 0x19
# au adesea sigla sub 1_0_1_...), iar la fluxuri (TIPURI_FLUX) si cu tipul referintei 1 (partea DVB). Dosarele: CAI_SIGLE
# din Picon.py cu "picon" (memoria interna, /media/hdd, /media/usb, /media/mmc, /media/cf, /picon), numai cele care
# exista; pentru fiecare nume se incearca toate dosarele, apoi numele urmator. Referinta vine din toString (tipul si
# steagurile in zecimal, celelalte campuri in hex mare, fara zerouri in fata), deci numele de aici se fac la fel, oricum
# ar fi scrisa referinta primita. picon_default*.png din aceleasi dosare e sigla lipsei: nu se atinge niciodata.
#
# DUPA NUME imaginea nu cauta. Numele de aici (nume_dupa_nume: litere si cifre mici, "&" -> "and", "+" -> "plus",
# "*" -> "star"; forma UTF-8 si forma ASCII fara diacritice) servesc la redenumire si la siglele nefolosite: o sigla cu
# numele unui canal din lista nu se socoteste nefolosita.
#
# SCRIEREA: <cale>.nou, fsync, os.replace (o sigla pe jumatate nu se vede niciodata). Sigla inlocuita sau scoasa ramane
# o data langa ea ca <nume>.png.vechi (prima; nu se scrie peste ea). O legatura simbolica (pachetele de sigle leaga multe
# referinte de un singur fisier) se inlocuieste ca legatura: fisierul comun ramane neatins. O referinta fara numerele
# DVB (SID, TSID, ONID si namespace 0, de pilda un flux fara ele) da acelasi nume pentru toate canalele de felul ei:
# pe ea nu se pune si nu se scoate nicio sigla.
#
# DUPA O SCHIMBARE: uita_memoria() (chemata de fiecare functie care schimba ceva pe disc) goleste siglele tinute minte
# de pagina /canale si de editorul web (canale_web._MEMORIE: lista gasita, ora ei, octetii cititi) si lista dosarelor din
# Picon.py (tinuta un minut), ca sigla noua sa se vada la urmatoarea cerere.
#
# Functiile lucreaza pe disc (un stick sau un disc adormit raspunde in cateva secunde): se cheama de pe un fir de lucru,
# nu de pe firul enigma2. Nimic din enigma2 la incarcare. Probele de pe PC pun DOSARE (dosare temporare).

import os
import re
import struct
import sys
import threading
import unicodedata
import zlib

try:
	from Components import HdsEditorCanale as _E
except ImportError:  # pe PC, in probe
	try:
		import HdsEditorCanale as _E
	except Exception:
		_E = None

# dosarele de sigle in ordinea cautarii; None = ale imaginii (Renderer/Picon.CAI_SIGLE cu DOSAR)
DOSARE = None
DOSAR = "picon"
# ca Picon.CAI_SIGLE, cand Picon.py nu se poate incarca (${datadir} = /usr/share)
CAI_IMAGINE = ("/usr/share/enigma2/%s/", "/media/hdd/%s/", "/media/usb/%s/", "/media/mmc/%s/", "/media/cf/%s/", "/%s/")
# ca Picon.TIPURI_FLUX: tipurile de referinta ale fluxurilor care poarta si partea DVB
TIPURI_FLUX = ("4097", "5001", "5002", "5003", "8193", "8739")

# marimea: aceeasi limita ca la citirea siglelor in interfata web (canale_web.MAX_SIGLA, aplicatii_web.MAX_SIGLA) si la
# importul lor (HdsImportExtra.MAX_PICON_OCTETI): o sigla mai mare nu s-ar vedea in pagina
MAX_OCTETI = 256 * 1024
MAX_LATURA = 1000
REZERVA_INTERNA = 32 * 1024 * 1024   # locul lasat liber in memoria interna (ca HdsImportExtra.REZERVA_PICON)
REZERVA = 1024 * 1024                # pe disc, stick, card
MAX_NUME = 100                       # litere in numele dupa nume
MAX_NUME_OCTETI = 200                # si octeti (UTF-8): numele fisierului are cel mult 255
MAX_LEGATURI = 16

REFERINTA = "referinta"
NUME = "nume"
VECHI = ".vechi"
NOU = ".nou"
SEMNATURA_PNG = b"\x89PNG\r\n\x1a\n"

_DOSAR_REF = 1     # eServiceReference.isDirectory
_MARCAJ = 64       # eServiceReference.isMarker
_ZEC = re.compile(r"^[0-9]{1,5}$")
_HEX = re.compile(r"^[0-9A-Fa-f]{0,8}$")
_INLOCUIRI = (("&", "and"), ("+", "plus"), ("*", "star"))
# modulele interfetei web care tin minte siglele (_MEMORIE)
MODULE_WEB = ("Plugins.Extensions.HdsWebControl.canale_web",)
MODUL_PICON = "Components.Renderer.Picon"

_ZAVOR = threading.RLock()


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsEditorSigle] %s" % text)


# ---------------------------------------------------------------- erorile

if _E is not None and hasattr(_E, "Eroare"):
	_Baza = _E.Eroare
else:
	class _Baza(Exception):
		def __init__(self, mesaj):
			Exception.__init__(self, mesaj)
			self.text = mesaj

		def mesaj(self):
			return self.text


class Eroare(_Baza):
	"""O schimbare de sigla care nu se poate face; mesaj() e textul pentru om (tradus). Aceeasi baza ca
	Components/HdsEditorCanale.Eroare, deci paginile editorului o arata ca pe celelalte erori."""


def _eroare_disc(dosar):
	return Eroare(_t("Nu s-a putut lucra cu siglele din %s.") % dosar)


# ---------------------------------------------------------------- numele

def _campuri(ref):
	"""Primele zece campuri ale referintei asa cum le scrie toString, sau None: mai putin de zece campuri, un camp care
	nu e numar, tipul 0, un dosar sau un marcaj."""
	if isinstance(ref, bytes):
		ref = ref.decode("utf-8", "replace")
	if not isinstance(ref, str):
		return None
	parti = ref.split(":")
	if len(parti) < 10:
		return None
	p = parti[:10]
	if not _ZEC.match(p[0]) or not _ZEC.match(p[1]) or not all(_HEX.match(x) for x in p[2:]):
		return None
	tip, steaguri = int(p[0]), int(p[1])
	if tip == 0 or steaguri & (_DOSAR_REF | _MARCAJ):
		return None
	return [str(tip), str(steaguri)] + ["%X" % int(x or "0", 16) for x in p[2:]]


def _fara_dvb(campuri):
	"""SID, TSID, ONID si namespace 0: acelasi nume de sigla pentru toate referintele de felul acesta."""
	return all(x == "0" for x in campuri[3:7])


def nume_incercate(ref):
	"""Numele de fisier (fara .png) pe care le incearca imaginea pentru referinta, in ordine (Picon.nume_sigle): exact,
	cu tipul serviciului 1, la fluxuri cu tipul referintei 1. Lista goala pentru ce nu e canal."""
	baza = _campuri(ref)
	if baza is None:
		return []
	nume = []

	def adauga(c):
		n = "_".join(c)
		if n not in nume:
			nume.append(n)
	adauga(baza)
	if baza[2] not in ("1", "0"):
		c = list(baza)
		c[2] = "1"
		adauga(c)
	if baza[0] in TIPURI_FLUX:
		c = list(baza)
		c[0] = "1"
		adauga(c)
		if c[2] not in ("1", "0"):
			c[2] = "1"
			adauga(c)
	return nume


def nume_dupa_referinta(ref):
	"""Numele fisierului (fara .png) dupa referinta, primul pe care il cauta imaginea; "" pentru ce nu e canal."""
	n = nume_incercate(ref)
	return n[0] if n else ""


def nume_dupa_nume(nume, utf8=True):
	"""Numele fisierului (fara .png) dupa numele canalului: litere si cifre mici, "&" -> "and", "+" -> "plus",
	"*" -> "star", restul scos. utf8=False: forma ASCII (diacriticele scoase; "" daca numele are litere fara forma
	ASCII). "" pentru un nume fara litere si cifre. Imaginea NU cauta dupa nume (vezi antetul)."""
	if isinstance(nume, bytes):
		nume = nume.decode("utf-8", "replace")
	if not nume or not isinstance(nume, str):
		return ""
	text = unicodedata.normalize("NFC" if utf8 else "NFKD", nume).lower()
	for a, b in _INLOCUIRI:
		text = text.replace(a, b)
	litere = []
	for ch in text:
		if utf8:
			if ch.isalnum():
				litere.append(ch)
		elif not unicodedata.combining(ch) and ch.isalnum():
			if ord(ch) >= 128:
				return ""
			litere.append(ch)
	rez = "".join(litere)[:MAX_NUME]
	while len(rez.encode("utf-8")) > MAX_NUME_OCTETI:
		rez = rez[:-1]
	return rez


def _nume_posibile(nume):
	rez = []
	for n in (nume_dupa_nume(nume, True), nume_dupa_nume(nume, False)):
		if n and n not in rez:
			rez.append(n)
	return rez


def _nume_de_scris(ref):
	"""Numele exact pentru o sigla pusa sau scoasa; Eroare pentru ce nu e canal sau pentru o referinta fara DVB."""
	c = _campuri(ref)
	if c is None:
		raise Eroare(_t("Rândul ales nu e un canal, deci nu poate avea siglă."))
	if _fara_dvb(c):
		raise Eroare(_t("Referința canalului nu are numerele DVB: sigla s-ar vedea la mai multe canale."))
	return nume_incercate(ref)[0]


# ---------------------------------------------------------------- dosarele

def dosare():
	"""Toate dosarele de sigle (si cele care nu exista), in ordinea cautarii imaginii, fiecare cu bara la capat."""
	if DOSARE is not None:
		return [os.path.join(d, "") for d in DOSARE]
	cai = None
	try:
		from Components.Renderer.Picon import CAI_SIGLE as cai
	except Exception:
		cai = None
	if not cai:
		cai = CAI_IMAGINE
	return [os.path.join(c % DOSAR, "") for c in cai]


def _cheie(cale):
	return os.path.normcase(os.path.realpath(cale))


def _cheie_fisier(cale):
	"""Fisierul (sau legatura) din dosarul lui adevarat, fara sa urmeze legatura insasi."""
	cale = os.path.normpath(cale)
	return os.path.normcase(os.path.join(os.path.realpath(os.path.dirname(cale)), os.path.basename(cale)))


def dosare_existente():
	"""Dosarele de sigle care exista acum, in ordinea imaginii; un dosar care e legatura spre altul din lista apare o
	singura data."""
	rez, vazute = [], set()
	for d in dosare():
		if os.path.isdir(d):
			k = _cheie(d)
			if k not in vazute:
				vazute.add(k)
				rez.append(d)
	return rez


def dosar_de_scris():
	"""Primul dosar de sigle care exista si se poate scrie, in ordinea imaginii; daca dosarul memoriei interne (primul)
	nu exista, se face. Eroare cand nu e niciunul."""
	toate = dosare()
	for d in toate:
		if os.path.isdir(d) and os.access(d, os.W_OK):
			return d
	if toate and not os.path.lexists(toate[0]):
		try:
			os.makedirs(toate[0], 0o755)
			return toate[0]
		except OSError as e:
			_jurnal("dosarul %s: %s" % (toate[0], e))
	raise Eroare(_t("Nu e niciun dosar de sigle în care să se poată scrie."))


def _gaseste(cai, nume, exista=os.path.lexists):
	for n in nume:
		for d in cai:
			p = os.path.join(d, n + ".png")
			if exista(p) and not os.path.isdir(p):
				return p
	return None


def sigla(ref, nume=""):
	"""Calea siglei pe care o arata imaginea pentru referinta (aceeasi cautare ca Picon.cauta_sigla), sau None. Cu
	`nume`, daca dupa referinta nu e niciuna: sigla dupa numele canalului (pe care televizorul NU o arata; se poate
	redenumi dupa referinta, redenumeste)."""
	cai = dosare_existente()
	cale = _gaseste(cai, nume_incercate(ref), os.path.isfile)
	if cale is None and nume:
		cale = _gaseste(cai, _nume_posibile(nume), os.path.isfile)
	return cale


# ---------------------------------------------------------------- PNG

def _antet_png(octeti):
	"""(latime, inaltime) din bucatile PNG: IHDR primul (13 octeti), fiecare bucata cu CRC bun, macar un IDAT, IEND la
	capat. None daca forma nu e a unui PNG intreg."""
	n = len(octeti)
	poz = len(SEMNATURA_PNG)
	latime = inaltime = None
	idat = False
	while poz + 12 <= n:
		lung = struct.unpack(">I", octeti[poz:poz + 4])[0]
		fel = octeti[poz + 4:poz + 8]
		sf = poz + 12 + lung
		if sf > n:
			return None
		date = octeti[poz + 8:poz + 8 + lung]
		crc = struct.unpack(">I", octeti[sf - 4:sf])[0]
		if zlib.crc32(date, zlib.crc32(fel)) & 0xFFFFFFFF != crc:
			return None
		if latime is None:
			if fel != b"IHDR" or lung != 13:
				return None
			latime, inaltime, adancime, culoare = struct.unpack(">IIBB", date[:10])
			if adancime not in (1, 2, 4, 8, 16) or culoare not in (0, 2, 3, 4, 6) or not latime or not inaltime:
				return None
		elif fel == b"IDAT":
			idat = True
		elif fel == b"IEND":
			return (latime, inaltime) if idat else None
		poz = sf
	return None


def verifica_png(octeti):
	"""(latime, inaltime) pentru o sigla buna; Eroare cu textul pentru om: nu e PNG sau e stricat, are peste MAX_OCTETI,
	are o latura peste MAX_LATURA pixeli."""
	if isinstance(octeti, (bytearray, memoryview)):
		octeti = bytes(octeti)
	if not isinstance(octeti, bytes) or not octeti.startswith(SEMNATURA_PNG):
		raise Eroare(_t("Fișierul nu e o imagine PNG bună. Alege o siglă în format PNG."))
	if len(octeti) > MAX_OCTETI:
		raise Eroare(_t("Fișierul are %d KB. O siglă poate avea cel mult %d KB.")
			% ((len(octeti) + 1023) // 1024, MAX_OCTETI // 1024))
	antet = _antet_png(octeti)
	if antet is None:
		raise Eroare(_t("Fișierul nu e o imagine PNG bună. Alege o siglă în format PNG."))
	latime, inaltime = antet
	if latime > MAX_LATURA or inaltime > MAX_LATURA:
		raise Eroare(_t("Imaginea are %d x %d pixeli. O siglă poate avea cel mult %d x %d pixeli.")
			% (latime, inaltime, MAX_LATURA, MAX_LATURA))
	return latime, inaltime


# ---------------------------------------------------------------- scrierea

def _scrie_sigur(cale, date):
	nou = cale + NOU
	try:
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except Exception:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _loc_liber(dosar):
	try:
		st = os.statvfs(dosar)
		return st.f_bavail * st.f_frsize
	except (OSError, AttributeError):
		return None


def _verifica_locul(dosar, marime):
	toate = dosare()
	interna = bool(toate) and _cheie(dosar) == _cheie(toate[0])
	liber = _loc_liber(dosar)
	if liber is not None and liber < marime + (REZERVA_INTERNA if interna else REZERVA):
		raise Eroare(_t("Nu e destul loc liber pentru siglă în %s.") % dosar)


def _pastreaza_vechi(cale):
	"""Sigla de la `cale` ramane langa ea ca <cale>.vechi, numai daca nu e deja una (prima se pastreaza)."""
	vechi = cale + VECHI
	if os.path.lexists(vechi):
		return
	if os.path.islink(cale):
		try:
			os.symlink(os.readlink(cale), vechi)
			return
		except (OSError, AttributeError, NotImplementedError):
			pass
	else:
		try:
			os.link(cale, vechi)
			return
		except (OSError, AttributeError, NotImplementedError):
			pass
	with open(cale, "rb") as f:
		date = f.read()
	_scrie_sigur(vechi, date)


def _tinta(nume):
	"""Unde se scrie sigla `nume`: peste cea existenta daca dosarul ei se poate scrie, altfel in dosar_de_scris(). Eroare
	daca o sigla cu acelasi nume dintr-un dosar care nu se poate scrie ar fi gasita de imagine inaintea celei noi."""
	cai = dosare_existente()
	existenta = None
	for i, d in enumerate(cai):
		p = os.path.join(d, nume + ".png")
		if os.path.lexists(p) and not os.path.isdir(p):
			existenta = (i, d, p)
			break
	if existenta is not None and os.access(existenta[1], os.W_OK):
		return existenta[2]
	d = dosar_de_scris()
	if existenta is not None:
		chei = [_cheie(x) for x in cai]
		k = _cheie(d)
		if k in chei and chei.index(k) > existenta[0]:
			raise Eroare(_t("Canalul are deja o siglă într-un dosar în care nu se poate scrie: %s") % existenta[1])
	return os.path.join(d, nume + ".png")


def pune(ref, octeti_png, nume=""):
	"""Sigla `octeti_png` (PNG) pe canalul `ref`, sub numele dupa referinta. Sigla de dinainte cu acelasi nume ramane
	ca .vechi (o singura data). `nume`: numele canalului (nu schimba unde se scrie: imaginea cauta numai dupa
	referinta). -> calea scrisa. Eroare cu textul pentru om."""
	n = _nume_de_scris(ref)
	if isinstance(octeti_png, (bytearray, memoryview)):
		octeti_png = bytes(octeti_png)
	verifica_png(octeti_png)
	with _ZAVOR:
		tinta = _tinta(n)
		dosar = os.path.dirname(tinta)
		_verifica_locul(dosar, len(octeti_png))
		try:
			if os.path.lexists(tinta):
				_pastreaza_vechi(tinta)
			_scrie_sigur(tinta, octeti_png)
		except OSError as e:
			_jurnal("scrierea %s: %s" % (tinta, e))
			raise _eroare_disc(dosar)
	uita_memoria()
	return tinta


def copiaza(ref_din, ref_la, nume_la="", nume_din=""):
	"""Sigla pe care o arata imaginea pentru `ref_din` (cu `nume_din`, si cea dupa numele lui) pusa si pe `ref_la`, ca
	pune(). -> calea siglei lui `ref_la`."""
	n_la = _nume_de_scris(ref_la)
	sursa = sigla(ref_din, nume_din)
	if sursa is None:
		raise Eroare(_t("Canalul de la care copiezi nu are siglă."))
	if os.path.basename(sursa) == n_la + ".png":
		return sursa
	try:
		with open(sursa, "rb") as f:
			date = f.read(MAX_OCTETI + 1)
	except OSError as e:
		_jurnal("citirea %s: %s" % (sursa, e))
		raise _eroare_disc(os.path.dirname(sursa))
	return pune(ref_la, date, nume_la)


def sterge(ref):
	"""Scoate sigla dupa referinta a canalului din toate dosarele (ramane .vechi, daca nu e deja una). O sigla comuna
	gasita prin numele cu tipul 1 (vezi antetul) ramane: e si a altor canale. -> cate s-au scos."""
	n = _nume_de_scris(ref)
	scoase, eroare = 0, None
	with _ZAVOR:
		for d in dosare_existente():
			p = os.path.join(d, n + ".png")
			if not os.path.lexists(p) or os.path.isdir(p):
				continue
			try:
				if os.path.lexists(p + VECHI):
					os.remove(p)
				else:
					os.rename(p, p + VECHI)
				scoase += 1
			except OSError as e:
				_jurnal("scoaterea %s: %s" % (p, e))
				eroare = eroare or d
	if scoase:
		uita_memoria()
	if eroare is not None:
		raise _eroare_disc(eroare)
	return scoase


# ---------------------------------------------------------------- siglele nefolosite

def _baza_buna(nume):
	return (nume.endswith(".png") and len(nume) > 4 and not nume.startswith(".")
		and not nume.lower().startswith("picon_default") and "/" not in nume and "\\" not in nume
		and "\x00" not in nume)


def _lant(cale):
	"""Cheile fisierelor la care duce legatura `cale` (si ale legaturilor de pe drum)."""
	rez = set()
	cur = cale
	for _i in range(MAX_LEGATURI):
		try:
			urm = os.readlink(cur)
		except (OSError, AttributeError, NotImplementedError):
			break
		if urm.startswith("\\\\?\\"):  # probele pe Windows: caile lungi
			urm = urm[4:]
		cur = os.path.join(os.path.dirname(cur), urm)
		rez.add(_cheie_fisier(cur))
		if not os.path.islink(cur):
			break
	return rez


def nefolosite(refs_existente, nume_existente=()):
	"""Siglele (.png) din dosarele de sigle care nu sunt ale niciunui serviciu din lista: nici dupa referinta (toate
	numele pe care le incearca imaginea, deci si sigla 1_0_1_... a unui canal HD; litere mari sau mici), nici dupa nume
	(UTF-8 sau ASCII). Raman si picon_default*.png si fisierele la care duce legatura unei sigle folosite. -> [cale], in
	ordinea dosarelor si a numelor."""
	folosite = set()
	for r in refs_existente or ():
		for n in nume_incercate(r):
			folosite.add(n.lower())
	for nm in nume_existente or ():
		folosite.update(_nume_posibile(nm))
	tinte = set()
	candidati = []
	for d in dosare_existente():
		try:
			with os.scandir(d) as it:
				intrari = sorted(it, key=lambda e: e.name)
		except OSError as e:
			_jurnal("dosarul %s: %s" % (d, e))
			continue
		real = os.path.realpath(d)
		for e in intrari:
			if not _baza_buna(e.name):
				continue
			try:
				if e.is_dir():
					continue
				leg = e.is_symlink()
			except OSError:
				continue
			if e.name[:-4].lower() in folosite:
				if leg:
					tinte.update(_lant(e.path))
				continue
			candidati.append((os.path.join(d, e.name), os.path.normcase(os.path.join(real, e.name))))
	return [cale for cale, k in candidati if k not in tinte]


def _cale_sigla(cale, chei_dosare, bune):
	"""Calea unei sigle din dosarele de sigle (fisier sau legatura .png direct in dosar, fara ".."), altfel None.
	`bune`: dosarul -> e sau nu dosar de sigle (o singura cautare a caii adevarate pe dosar)."""
	if not isinstance(cale, str) or not cale or "\x00" in cale:
		return None
	if ".." in re.split(r"[\\/]", cale):
		return None
	if not _baza_buna(os.path.basename(cale)):
		return None
	dosar = os.path.dirname(cale)
	if dosar not in bune:
		bune[dosar] = _cheie(dosar) in chei_dosare
	if not bune[dosar]:
		return None
	if not os.path.lexists(cale) or os.path.isdir(cale):
		return None
	if not (os.path.islink(cale) or os.path.isfile(cale)):
		return None
	return cale


def sterge_nefolosite(cai):
	"""Sterge siglele `cai` (de obicei cele din nefolosite()): numai fisiere sau legaturi .png aflate direct intr-un
	dosar de sigle; orice alta cale se lasa. -> cate s-au sters."""
	chei = set(_cheie(d) for d in dosare_existente())
	bune = {}
	sterse, eroare = 0, None
	with _ZAVOR:
		for cale in cai or ():
			c = _cale_sigla(cale, chei, bune)
			if c is None:
				_jurnal("cale lasata: %r" % (cale,))
				continue
			try:
				os.remove(c)
				sterse += 1
			except OSError as e:
				_jurnal("stergerea %s: %s" % (c, e))
				eroare = eroare or os.path.dirname(c)
	if sterse:
		uita_memoria()
	if eroare is not None:
		raise _eroare_disc(eroare)
	return sterse


# ---------------------------------------------------------------- redenumirea

def avertisment_nume():
	"""Textul de aratat inainte de redenumirea dupa nume."""
	return _t("Televizorul caută siglele numai după referință. După redenumirea după nume, nu le mai arată.")


def redenumeste(fel, perechi):
	"""fel REFERINTA: siglele dupa nume capata numele dupa referinta (televizorul le arata); fel NUME: invers.
	`perechi`: (ref, nume) ale canalelor. Numai unde tinta nu exista (in niciun dosar de sigle); sigla ramane in dosarul
	ei. Mai multe canale cu acelasi nume primesc fiecare sigla (copii; ultimul primeste fisierul insusi). -> cate s-au
	facut."""
	if fel not in (REFERINTA, NUME):
		raise Eroare(_t("Redenumirea se face după referință sau după nume."))
	facute, eroare = 0, None
	with _ZAVOR:
		cai = dosare_existente()
		plan, tinte = [], set()
		for pereche in perechi or ():
			try:
				ref, nume = pereche
			except (TypeError, ValueError):
				continue
			c = _campuri(ref)
			if c is None:
				continue
			if fel == REFERINTA:
				if _fara_dvb(c):
					continue
				n = nume_incercate(ref)[0]
				if _gaseste(cai, [n]) is not None:
					continue
				sursa = _gaseste(cai, _nume_posibile(nume))
			else:
				posibile = _nume_posibile(nume)
				if not posibile or _gaseste(cai, posibile) is not None:
					continue
				n = posibile[0]
				sursa = _gaseste(cai, nume_incercate(ref)[:1])
			if sursa is None:
				continue
			tinta = os.path.join(os.path.dirname(sursa), n + ".png")
			k = _cheie_fisier(tinta)
			if k in tinte:
				continue
			tinte.add(k)
			plan.append((sursa, tinta))
		ramase = {}
		for sursa, _tinta_ in plan:
			ks = _cheie_fisier(sursa)
			ramase[ks] = ramase.get(ks, 0) + 1
		for sursa, tinta in plan:
			ks = _cheie_fisier(sursa)
			ramase[ks] -= 1
			try:
				if os.path.lexists(tinta):
					continue
				if ramase[ks] == 0:
					os.rename(sursa, tinta)
				else:
					with open(sursa, "rb") as f:
						date = f.read()
					_scrie_sigur(tinta, date)
				facute += 1
			except OSError as e:
				_jurnal("redenumirea %s: %s" % (sursa, e))
				eroare = eroare or os.path.dirname(tinta)
	if facute:
		uita_memoria()
	if eroare is not None:
		raise _eroare_disc(eroare)
	return facute


# ---------------------------------------------------------------- memoria altor module

def uita_memoria():
	"""Uita siglele tinute minte in afara: lista gasita de pagina /canale (si de editorul web, care o foloseste),
	octetii cititi si lista dosarelor din Picon.py. Numai modulele deja incarcate (pe PC nu e niciunul)."""
	for nume in MODULE_WEB:
		try:
			m = sys.modules.get(nume)
			mem = getattr(m, "_MEMORIE", None) if m is not None else None
			if isinstance(mem, dict):
				# sigle_in_curs: o cautare pornita inainte de schimbare nu mai tine locul; urmatoarea cerere porneste
				# una noua, care vine (pe acelasi fir, in coada) dupa ea
				mem.update({"sigle": None, "sigle_ora": 0.0, "sigle_octeti": {}, "sigle_in_curs": False})
		except Exception as e:
			_jurnal("memoria %s: %r" % (nume, e))
	try:
		p = sys.modules.get(MODUL_PICON)
		d = getattr(p, "_dosare", None) if p is not None else None
		if isinstance(d, dict):
			d.clear()
	except Exception as e:
		_jurnal("memoria dosarelor: %r" % (e,))
