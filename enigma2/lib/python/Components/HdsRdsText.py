# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRdsText.py: textul radio (RDS RadioText) si piesa (RT+) ale postului care merge, pentru ecranul radio, pagina web
# si ecranele vechi ale RDS (Screens/RdsDisplay.py, Components/Converter/RdsInfo.py).
#
# Doua paze, fiecare suficienta singura:
# 1. Sursa: un text se ia numai dupa ce decodorul RDS al nucleului (lib/dvb/radiotext.cpp) a anuntat un mesaj bun
#    (CRC verificat) pentru serviciul care merge: evUpdatedRadioText pentru textul radio, evUpdatedRtpText pentru piesa.
#    La evStart si evEnd starea se sterge. Nucleul citeste RDS din datele auxiliare ale cadrelor MPEG, de pe un PID
#    separat si, la posturile AAC (LATM / LOAS, ADTS), din elementele DSE ale cadrelor; un post care nu trimite RDS nu
#    da niciun eveniment, deci nu se arata nimic, orice ar fi in memoria decodorului. Ascultatorul se pune PRIMUL in
#    Navigation.event (inaintea ServiceEventTracker), ca ecranele care citesc textul la acelasi eveniment sa gaseasca
#    starea pusa.
# 2. Textul: octetii se decodeaza in setul de caractere potrivit si textul se verifica inainte de afisare; ce nu arata
#    a text scris de om (caractere de control, simboluri fara sens, prea putine litere) nu se arata.
#
# Octetii: getText() din servicedvb.cpp trece octetii prin convertLatin1UTF8, deci fiecare octet devine caracterul cu
# acelasi cod (0-255) si octetii se refac exact cu encode("latin-1"). Un text cu caractere peste 255 e deja decodat.
#
# Seturile de caractere: RDS scrie textul in setul EBU Latin (IEC 62106, anexa E), dar unele codoare trimit ISO-8859-1,
# ISO-8859-15, ISO-8859-2 sau UTF-8; cu BOM, si UTF-16. Alegerea: BOM -> UTF-16; UTF-8 valid cu litere peste ASCII ->
# UTF-8; altfel fiecare set posibil primeste un punctaj dupa literele pe care le da (literele obisnuite in limbile
# europene castiga, simbolurile rare si caracterele de control pierd) si castiga cel mai bun. Octetii 0x80-0x9F sunt
# caractere de control in ISO-8859, dar litere mici in EBU Latin (ä ö ü é ...), deci un text EBU iese EBU.
#
# Randurile: 0x0A (rand nou dorit), 0x0B si tab devin spatiu; 0x0D (sfarsitul mesajului) taie textul; 0x1F (despartire
# in silabe dorita) dispare; spatiile repetate se strang.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct. Merge si pe Python 2.

import unicodedata

try:
	unicode
except NameError:  # Python 3
	unicode = str
	unichr = chr

# ---------------------------------------------------------------- setul EBU Latin (IEC 62106, anexa E, 0x80-0xFF)

_EBU_RANDURI = (
	u"áàéèíìóòúùÑÇŞß¡Ĳ",  # 0x80
	u"âäêëîïôöûüñçşğıĳ",  # 0x90
	u"ªα©‰Ǧěňőπ€£$←↑→↓",        # 0xA0
	u"º¹²³±İńűµ¿÷°¼½¾§",  # 0xB0
	u"ÁÀÉÈÍÌÓÒÚÙŘČŠŽĐĿ",  # 0xC0
	u"ÂÄÊËÎÏÔÖÛÜřčšžđŀ",  # 0xD0
	u"ÃÅÆŒŷÝÕØÞŊŔĆŚŹŦð",  # 0xE0
	u"ãåæœŵýõøþŋŕćśźŧ�",  # 0xF0
)
EBU_LATIN = u"".join(_EBU_RANDURI)
# in partea de jos, tabelul EBU Latin are alte semne decat ASCII numai pe trei coduri (0x5E, 0x60, 0x7E); „$” (0x24)
# e in tabel „¤”, dar codoarele trimit acolo semnul dolarului, deci ramane „$”
_EBU_JOS = {0x5E: u"―", 0x60: u"‖", 0x7E: u"¯"}

MAX_TEXT = 128     # RadioText are 64 de caractere; piesa (RT+, „titlu (artist)”) cel mult cam tot atat


def _ebu(octeti):
	rez = []
	for o in bytearray(octeti):
		if o >= 0x80:
			rez.append(EBU_LATIN[o - 0x80])
		else:
			rez.append(_EBU_JOS.get(o) or unichr(o))
	return u"".join(rez)


# ---------------------------------------------------------------- punctajul unui text decodat

# litere obisnuite in textele posturilor europene (germana, franceza, spaniola, italiana, portugheza, olandeza,
# limbile nordice): +2
_LITERE_DES = frozenset(u"äöüßÄÖÜéèêëàâáíìîïóòôõúùûñçãåæøœÉÈÊÀÂÁÍÎÓÔÚÇÑÅÆØ")
# litere din Europa Centrala si de Est si din turca (romana, ceha, polona, maghiara, slovaca, croata): +1
_LITERE_EST = frozenset(u"ăâîșțşţĂÂÎȘȚŞŢčšžřěůýćńśźżłąęőűğıČŠŽŘĚŮÝĆŃŚŹŻŁĄĘŐŰĞİđĐ")
# semne obisnuite in texte (si „|”, pus de multe posturi intre artist si titlu): neutre
_SEMNE_BUNE = frozenset(u" .,;:!?-+/&'\"()[]*#%@_=|€£$°«»„“”‘’–—…•·§")


def _punctaj_caracter(c):
	if c in _SEMNE_BUNE:
		return 0
	if u"0" <= c <= u"9" or u"a" <= c <= u"z" or u"A" <= c <= u"Z":
		return 1
	if c in _LITERE_DES:
		return 2
	if c in _LITERE_EST:
		return 1
	cat = unicodedata.category(c)
	if cat[0] == u"C" or c == u"�":
		return -6          # control, nefolosit, privat: nu e text
	if cat[0] == u"L":
		return -1          # litera rara (ŀ, ŷ, ŧ, Ŋ, α ...)
	return -3              # simbol rar (¤, ¿, ³, ‰, sageti ...)


def punctaj(text):
	return sum(_punctaj_caracter(c) for c in text)


# ---------------------------------------------------------------- decodarea

def _utf8_cu_litere(octeti):
	"""Textul UTF-8 daca octetii sunt UTF-8 valid si au macar un caracter peste ASCII, altfel None."""
	try:
		t = bytes(octeti).decode("utf-8")
	except (UnicodeDecodeError, ValueError):
		return None
	return t if any(ord(c) > 0x7F for c in t) else None


def _candidati(octeti):
	"""[(nume, text)] in ordinea preferintei la punctaj egal."""
	rez = [("ebu", _ebu(octeti))]
	for nume in ("iso-8859-15", "iso-8859-1", "iso-8859-2"):
		try:
			rez.append((nume, bytes(octeti).decode(nume)))
		except (UnicodeDecodeError, LookupError):
			pass
	return rez


def decodeaza_octeti(octeti):
	"""(textul decodat, setul ales) pentru octetii unui mesaj RDS, inainte de curatare si verificare."""
	octeti = bytes(bytearray(octeti))
	if octeti[:2] in (b"\xfe\xff", b"\xff\xfe"):
		try:
			return octeti.decode("utf-16"), "utf-16"
		except (UnicodeDecodeError, ValueError):
			return u"", "utf-16"
	# textul se termina la primul octet 0 (bufferele C sunt umplute cu 0)
	zero = octeti.find(b"\x00")
	if zero >= 0:
		octeti = octeti[:zero]
	if not octeti:
		return u"", "gol"
	if all(o < 0x80 and o not in _EBU_JOS for o in bytearray(octeti)):
		return octeti.decode("ascii"), "ascii"
	t = _utf8_cu_litere(octeti)
	if t is not None:
		return t, "utf-8"
	bun = None
	for nume, text in _candidati(octeti):
		p = punctaj(text)
		if bun is None or p > bun[0]:
			bun = (p, text, nume)
	return bun[1], bun[2]


def curata(text):
	"""Randurile si spatiile: 0x0D taie, 0x0A / 0x0B / tab devin spatiu, 0x1F si semnele de evidentiere DVB dispar."""
	if not text:
		return u""
	cr = text.find(u"\r")
	if cr >= 0:
		text = text[:cr]
	for c in (u"\n", u"\x0b", u"\t", u"\u2028", u"\u2029"):
		text = text.replace(c, u" ")
	for c in (u"\x1f", u"\u00ad", u"\u0086", u"\u0087"):
		text = text.replace(c, u"")
	return u" ".join(text.split())


def e_text_valid(text):
	"""True daca textul (curatat) arata a text scris de om: fara caractere de control, cu destule litere si cifre
	(din orice alfabet: latin, chirilic, grec ...), fara prea multe semne rare (¤ ¿ ³ ‰ sageti, simboluri)."""
	if not text or len(text) > MAX_TEXT:
		return False
	vizibile = [c for c in text if c != u" "]
	if not vizibile:
		return False
	litere = 0
	rare = 0
	for c in vizibile:
		cat = unicodedata.category(c)
		if cat[0] == u"C" or c == u"�":
			return False
		if cat[0] == u"L" or cat == u"Nd":
			litere += 1
		elif c not in _SEMNE_BUNE:
			rare += 1
	if litere < 2:
		return False
	# cel putin jumatate din semnele vizibile sunt litere sau cifre; cel mult unul din zece e rar
	return litere * 2 >= len(vizibile) and rare * 10 <= len(vizibile)


def din_octeti(octeti):
	"""Octetii unui mesaj RDS -> textul gata de aratat, sau u"" daca nu e un text valid."""
	text, _set = decodeaza_octeti(octeti)
	text = curata(text)
	return text if e_text_valid(text) else u""


def din_nucleu(valoare):
	"""Ce da iRdsDecoder.getText() (str / bytes / None) -> textul gata de aratat, sau u""."""
	if valoare is None:
		return u""
	if isinstance(valoare, bytes):
		return din_octeti(valoare)
	try:
		valoare = unicode(valoare)
	except Exception:
		return u""
	if not valoare:
		return u""
	if all(ord(c) < 0x100 for c in valoare):
		return din_octeti(valoare.encode("latin-1"))
	text = curata(valoare)
	return text if e_text_valid(text) else u""


# ---------------------------------------------------------------- paza sursei (evenimentele nucleului)

TEXT = "text"      # RadioText
PIESA = "piesa"    # RT+

_STARE = {"urmarit": False, TEXT: False, PIESA: False}
_EV = {}


def _asculta(ev):
	if ev == _EV.get("start") or ev == _EV.get("sfarsit"):
		_STARE[TEXT] = False
		_STARE[PIESA] = False
	elif ev == _EV.get("text"):
		_STARE[TEXT] = True
	elif ev == _EV.get("piesa"):
		_STARE[PIESA] = True


def urmareste(nav, iPlayableService=None):
	"""Porneste paza sursei pe navigatia enigma2 (o singura data). `iPlayableService` il dau probele de pe PC."""
	if _STARE["urmarit"] or nav is None:
		return _STARE["urmarit"]
	lista = getattr(nav, "event", None)
	if not isinstance(lista, list):
		return False
	if iPlayableService is None:
		try:
			from enigma import iPlayableService
		except ImportError:
			return False
	_EV.update({"start": iPlayableService.evStart, "sfarsit": iPlayableService.evEnd,
		"text": iPlayableService.evUpdatedRadioText, "piesa": iPlayableService.evUpdatedRtpText})
	if _asculta not in lista:
		lista.insert(0, _asculta)
	# serviciul care merge deja (paza pornita dupa evStart) nu are inca niciun mesaj vazut: textul vine la urmatorul
	# eveniment al decodorului (textul radio se repeta la cateva secunde)
	_STARE[TEXT] = False
	_STARE[PIESA] = False
	_STARE["urmarit"] = True
	return True


def venit(fel):
	"""True / False daca decodorul a anuntat un mesaj `fel` (TEXT sau PIESA) pentru serviciul care merge; None cand
	paza nu e pornita (atunci ramane numai verificarea textului)."""
	if not _STARE["urmarit"]:
		return None
	return bool(_STARE.get(fel))


def opreste_paza():
	"""Pentru probe: paza inapoi la inceput."""
	_STARE.update({"urmarit": False, TEXT: False, PIESA: False})
	_EV.clear()


def text_decodor(decodor, fel, iRdsDecoder=None):
	"""Textul `fel` (TEXT / PIESA) din decodorul RDS al serviciului, cu ambele paze; u"" cand nu e."""
	if decodor is None or venit(fel) is False:
		return u""
	if iRdsDecoder is None:
		try:
			from enigma import iRdsDecoder
		except ImportError:
			return u""
	try:
		v = decodor.getText(iRdsDecoder.RadioText if fel == TEXT else iRdsDecoder.RtpText)
	except Exception:
		return u""
	return din_nucleu(v)
