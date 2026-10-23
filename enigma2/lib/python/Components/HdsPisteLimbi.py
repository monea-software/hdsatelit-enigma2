# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPisteLimbi - pista audio si subtitrarea alese singure dupa limba, cu preferinte, iar ce alege
# omul de mana pe un canal se tine minte pe acel canal.
#
# Ce trebuie sa faca: subtitrarea sa porneasca singura in limba receptorului,
# iar daca nu exista subtitrare in limba aceea, sa nu porneasca nimic; sunetul sa porneasca in limba
# receptorului, altfel in engleza, altfel pista implicita a canalului; si un meniu cu cate 3 preferinte
# pentru sunet si pentru subtitrare, ca omul sa-si aleaga alta ordine, inclusiv „fara subtitrari
# niciodata". Ora 22:50: ce alege omul de mana pe un canal NU SE MAI SCHIMBA NICIODATA, se tine minte
# pe canal, si dupa repornire.
#
# ORDINEA, la fiecare pornire a unui canal (si la redarea unei inregistrari a acelui canal):
#   sunet:      1. alegerea de mana tinuta minte pe canal (recunoscuta dupa limba si fel, nu dupa PID,
#                  care se poate schimba); daca pista aceea nu mai exista, se trece mai departe
#               2. preferintele 1, 2, 3 (implicit: limba receptorului, engleza, pista implicita a canalului)
#               3. pista implicita a canalului: nu se schimba nimic, ramane ce a pornit nucleul
#   subtitrare: 1. alegerea de mana tinuta minte pe canal: o subtitrare anume, sau „fara subtitrare"
#               2. „Fara subtitrari niciodata" (din setari): nimic
#               3. preferintele 1, 2, 3 (implicit: limba receptorului, apoi nimic)
#               4. nimic
#   Alegerea de mana are intaietate si fata de „niciodata": omul a pornit-o singur pe canalul acela.
#
# CU TRADUCEREA SUBTITRARILOR PORNITA (Components/HdsTraducereSubtitrari.py),
# subtitrarea se alege la fiecare canal asa (alegeSubtitrareTradusa), dupa 1 (memoria) si 2
# („niciodata”), care raman mai tari:
#               a. o subtitrare in limba traducerii (fara traducere);
#               b. altfel, cu „Tradu automat din orice subtitrare disponibilă” = Da (din fabrica): teletextul (sau textul
#                  unui fisier) in alta limba, tradus; fara OCR;
#               c. altfel, tot cu Da: o subtitrare DVB in alta limba, citita cu OCR si tradusa, numai daca receptorul
#                  are modelul OCR al limbii ei (Components/HdsOcrSubtitrari.poateCiti) si OCR e pornit; o pista DVB fara
#                  limba stiuta nu se ia (modelul ar fi ghicit);
#               d. altfel preferintele 1, 2, 3, ca fara traducere (pe Nu, dupa a. vin direct acestea).
#   Intre mai multe limbi la b. si c.: limbile din preferinte (in ordinea lor), apoi engleza, apoi celelalte, apoi cele
#   fara limba stiuta; la aceeasi limba, subtitrarea obisnuita inaintea celei pentru surzi. Pe acelasi canal, o
#   subtitrare DVB pusa la c. se schimba o singura data pe teletext (b.) sau pe limba traducerii (a.) cand acestea apar
#   mai tarziu in lista (paginile de teletext gasite din mers); orice alta alegere pornita ramane.
#
# DE CE „PISTA IMPLICITA A CANALULUI" INSEAMNA „NU SE SCHIMBA NIMIC": selectTrack() din nucleu
# reporneste decodorul de sunet (se aude o intrerupere) si scrie PID-ul in lamedb (in intrarea formatului pistei).
# Pista pornita de nucleu tine deja cont de config.av.defaultac3 si de ce s-a ales ultima data
# (lib/dvb/pmt.cpp r. 616-648). De aceea selectTrack se cheama numai cand pista dorita e ALTA decat
# cea care merge, iar intre mai multe piste in aceeasi limba castiga cea care merge deja.
#
# LIMBA UNEI PISTE: getTrackInfo(i).getLanguage() da codul ISO 639 din PMT („deu", „rum", „deu/eng" la
# dual mono), DAR daca EIT-ul are textul componentei, da textul acela („Deutsch", „Originalton",
# „Audiodeskription") - lib/service/servicedvb.cpp r. 1824-1836. Deci se recunosc si codurile (cu
# variantele B/T: ron/rum/ro, deu/ger/de, fra/fre/fr), si numele limbilor (in engleza, in limba lor si
# cum le scrie televiziunea germana). Legatura dintre coduri vine din Tools/ISO639.py, nu dintr-un
# tabel scris de mana aici. Pistele cu descriere audio (pentru nevazatori) nu se aleg singure.
#
# SUBTITRARI PENTRU SURZI: nucleul nu le spune deocamdata Python-ului (DVB 0x20-0x23 ramane in
# structura din pmt.h, teletextul 0x05 se pierde la citirea PMT). Functia de alegere stie de ele (un
# al 6-lea camp in tuplul din getSubtitleList, daca il va da nucleul) si le pune dupa cele obisnuite
# in aceeasi limba. Schimbarea din nucleu nu e facuta inca.
#
# CE SE TINE MINTE: /etc/enigma2/hdsatelit/piste-alese.json, scris atomic (.nou + fsync + os.replace),
# pentru totdeauna: limitele (MAX_CANALE canale, MAX_OCTETI octeti) sunt peste tot ce poate prinde o antena
# si raman numai ca paza; un fisier stricat sau prea mare se ignora (se porneste de la zero, fara sa cada
# nimic). Alaturi, piste-parti.json: partea audio (stanga/dreapta) pusa singura la o pista dual mono, sau
# semnul ca omul a schimbat-o (vezi „dual mono” mai jos). Cheia unui canal: SID, TSID,
# ONID si spatiul de nume din referinta (nu tipul serviciului, care difera intre liste); la fluxurile
# din retea, adresa; la inregistrari, canalul de origine din .meta, deci alegerea facuta pe canal merge
# si la inregistrarile lui.
#
# PARTEA DE SUS A FISIERULUI E CURATA (nu cere enigma): alegerea se probeaza pe PC cu liste false de
# piste (teste/test_piste_limbi.py). Tot ce atinge serviciul sta in functiile de la sfarsit, cu
# importuri tarzii; ele sunt si API-ul pentru alte ecrane.

from __future__ import absolute_import

import json
import os
import re
import time
import unicodedata

try:
	from Tools.ISO639 import LanguageCodes
except Exception:  # fara tabel (nu se intampla pe receptor): macar limbile receptorului
	LanguageCodes = {}

# ------------------------------------------------------------------ locuri si limite
CALE_ALEGERI = "/etc/enigma2/hdsatelit/piste-alese.json"
CALE_PARTI = "/etc/enigma2/hdsatelit/piste-parti.json"
# „Pentru totdeauna” (inainte 500 de canale si 256 KB, iar
# cele vechi plecau): 20000 de canale, mai multe decat au la un loc satelitii pe care ii prinde o antena. O alegere
# tinuta minte are ~150-250 de octeti (cea mai mare, sunet si subtitrare cu texte lungi, ~240; proba o masoara),
# deci in 8 MB intra toate si limita de octeti nu taie inaintea celei de canale. Limitele raman numai ca paza
# pentru un fisier stricat sau umflat. Fisierul se citeste din nou numai cand i se schimba marimea sau ora; la
# cateva sute de canale are sub 100 KB.
MAX_CANALE = 20000
MAX_OCTETI = 8 * 1024 * 1024
MAX_TEXT = 40          # textul limbii tinut minte (codul sau numele din EIT)
MAX_CHEIE = 200        # cheia unui canal (adresa unui flux poate fi lunga)
MAX_PISTE = 32         # nu se citesc mai multe piste (un PMT normal are 1-8)

# valorile speciale din preferinte
PREF_RECEPTOR = "receptor"
PREF_CANAL = "canal"   # doar la sunet: pista implicita a canalului
PREF_NIMIC = "nimic"   # doar la subtitrari: loc nefolosit
OPRIT = "oprit"        # alegerea de mana tinuta minte: fara subtitrare pe canalul acesta

PREF_AUDIO_IMPLICITE = (PREF_RECEPTOR, "eng", PREF_CANAL)
PREF_SUBTITRARE_IMPLICITE = (PREF_RECEPTOR, PREF_NIMIC, PREF_NIMIC)

# motivele alegerii cu traducerea pornita (alegeSubtitrareTradusa)
MOTIV_TRADUCERE_TINTA = "traducere-tinta"          # subtitrare in limba traducerii
MOTIV_TRADUCERE_TEXT = "traducere-teletext"        # teletext (sau fisier) in alta limba, tradus
MOTIV_TRADUCERE_DVB = "traducere-dvb"              # DVB in alta limba, citita cu OCR si tradusa


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: numele limbilor se traduc la folosire."""
	return text


# limbile din meniu: limbile receptorului (Components/Language.py) plus bulgara (vecini, canale pe satelit);
# numele sunt msgid-urile din Language.py, deja traduse in po
LIMBI_MENIU = (
	("ron", N_("Romanian")), ("eng", N_("English")), ("deu", N_("German")), ("fra", N_("French")),
	("ita", N_("Italian")), ("spa", N_("Spanish")), ("por", N_("Portuguese")), ("hun", N_("Hungarian")),
	("bul", N_("Bulgarian")), ("srp", N_("Serbian")), ("hrv", N_("Croatian")), ("slv", N_("Slovenian")),
	("slk", N_("Slovakian")), ("ces", N_("Czech")), ("pol", N_("Polish")), ("rus", N_("Russian")),
	("ukr", N_("Ukrainian")), ("tur", N_("Turkish")), ("ell", N_("Greek")), ("nld", N_("Dutch")),
	("swe", N_("Swedish")), ("nor", N_("Norwegian")), ("dan", N_("Danish")), ("fin", N_("Finnish")),
	("ara", N_("Arabic")), ("cat", N_("Catalan")), ("est", N_("Estonian")), ("lit", N_("Lithuanian")),
	("lav", N_("Latvian")), ("isl", N_("Icelandic")), ("fry", N_("Frisian")),
)

# limbile de azi care nu sunt in LIMBI_MENIU, au canale pe satelitii din Europa (sau in diaspora lor) si in
# Tools/ISO639.py au un nume netradus sau vechi ("Gallegan", "Letzeburgesch", "Kirghiz", "Oriya", "Romany"): numele
# lor de acum, traduse in po (numeLimba); celelalte coduri de limbi vii raman cu numele din Tools/ISO639.py
LIMBI_ALTE = (
	("kaz", N_("Kazakh")), ("tuk", N_("Turkmen")), ("uzb", N_("Uzbek")), ("kir", N_("Kyrgyz")), ("tgk", N_("Tajik")),
	("aze", N_("Azerbaijani")), ("tat", N_("Tatar")), ("bak", N_("Bashkir")), ("che", N_("Chechen")),
	("kat", N_("Georgian")), ("hye", N_("Armenian")), ("ben", N_("Bengali")), ("urd", N_("Urdu")),
	("pan", N_("Punjabi")), ("guj", N_("Gujarati")), ("tam", N_("Tamil")), ("tel", N_("Telugu")),
	("mal", N_("Malayalam")), ("ori", N_("Odia")), ("sin", N_("Sinhala")), ("nep", N_("Nepali")), ("pus", N_("Pashto")),
	("amh", N_("Amharic")), ("tir", N_("Tigrinya")), ("som", N_("Somali")), ("swa", N_("Swahili")), ("hau", N_("Hausa")),
	("afr", N_("Afrikaans")), ("ber", N_("Berber")), ("kab", N_("Kabyle")), ("syr", N_("Syriac")),
	("glg", N_("Galician")), ("ltz", N_("Luxembourgish")), ("gla", N_("Scottish Gaelic")), ("rom", N_("Romani")),
	("yid", N_("Yiddish")), ("msa", N_("Malay")), ("tgl", N_("Tagalog")), ("mon", N_("Mongolian")), ("lat", N_("Latin")),
)
_NUME_ALTE = dict(LIMBI_ALTE)

# codurile ISO 639-2 care nu sunt limba unui canal de azi: limbile disparute, cele inventate, jargoanele si grupele de
# limbi ("... (Other)", "... languages"). Pe sateliti apar numai din greseala: subtitrari in greaca etichetate grc,
# o pagina de subtitrare teletext cu non, sunetul unor canale chinezesti cu chn, servicii de proba cu vol, ina, inc.
# Nu intra in filtrele cautarii (randurile "Limbă sunet" si "Subtitrare"); pistele canalului le arata mai departe.
# Raman limbile liturgice (latina, slavona, copta, sanscrita, pali), folosite si azi la emisiuni.
LIMBI_FARA_FILTRU = frozenset((
	# disparute sau vechi
	"akk", "ang", "ave", "chg", "dum", "egy", "elx", "enm", "frm", "fro", "gmh", "goh", "got", "grc", "hit", "kaw",
	"kho", "mga", "non", "ota", "pal", "peo", "pro", "sga", "sog", "sux", "uga",
	# inventate si jargoane
	"afh", "art", "chn", "ile", "ina", "vol",
	# grupele de limbi
	"afa", "alg", "apa", "ath", "aus", "bai", "bat", "bnt", "cai", "cau", "cel", "cmc", "cpe", "cpf", "cpp", "crp", "cus",
	"dra", "fiu", "gem", "inc", "ine", "ira", "iro", "khi", "map", "mkh", "mno", "mun", "myn", "nai", "nic", "nub", "oto",
	"paa", "phi", "pra", "roa", "sai", "sal", "sem", "sio", "sit", "sla", "smi", "ssa", "tai", "tut", "wak", "ypk",
))


def limbaInFiltre(cod):
	"""Codul canonic intra in filtrele cautarii dupa limba? Nu pentru LIMBI_FARA_FILTRU si nici pentru codurile care nu
	inseamna o limba (_FARA_LIMBA: nedeterminat, mai multe, fara vorbire)."""
	return bool(cod) and cod not in LIMBI_FARA_FILTRU and cod not in _FARA_LIMBA

# ------------------------------------------------------------------ tabelul limbilor

# codurile ISO 639-2/B (bibliografice); forma canonica e codul /T, cum il foloseste si ISO 639-3
_COD_B = frozenset(("alb", "arm", "baq", "bur", "chi", "cze", "dut", "fre", "geo", "ger", "gre", "ice",
	"mac", "mao", "may", "per", "rum", "scc", "scr", "slo", "tib", "wel"))
# coduri vechi sau variante care inseamna aceeasi limba pentru om
_ALIAS = {"mol": "ron", "mo": "ron", "nob": "nor", "nno": "nor", "nb": "nor", "nn": "nor",
	"iw": "heb", "ji": "yid", "in": "ind"}
# fara limba: nedeterminat, mai multe, fara vorbire, „original" (qaa-qtz sunt coduri locale, de obicei
# „versiunea originala" sau „descriere audio", fara o limba anume)
_FARA_LIMBA = frozenset(("", "und", "unk", "mis", "mul", "zxx", "xxx", "---", "orig", "original",
	"originalton", "ov", "vo", "vos", "omu", "nar"))
_LOCAL = re.compile(r"^q[a-t][a-z]$")

# numele limbilor cum apar in EIT sau in fisiere: in limba lor, in romana, in germana (ARD/ZDF/ORF),
# in franceza si italiana; fara diacritice, cu litere mici
_NUME_LOCALE = {
	"ron": ("romana", "romaneste", "rumanisch", "roumain", "rumeno", "rumano", "roman", "moldoveneasca"),
	"eng": ("english", "engleza", "englisch", "anglais", "inglese", "ingles", "angol", "angielski", "anglicky"),
	"deu": ("deutsch", "germana", "allemand", "tedesco", "aleman", "nemet", "niemiecki", "nemecky"),
	"fra": ("francais", "franceza", "franzosisch", "francese", "frances", "francia", "francuski"),
	"ita": ("italiano", "italiana", "italienisch", "italien", "olasz", "wloski"),
	"spa": ("espanol", "spaniola", "spanisch", "espagnol", "spagnolo", "castellano", "spanyol"),
	"por": ("portugues", "portugheza", "portugiesisch", "portugais", "portoghese"),
	"hun": ("magyar", "maghiara", "ungarisch", "hongrois", "ungherese"),
	"bul": ("bulgarski", "bulgara", "bulgarisch", "bulgare", "български"),
	"srp": ("srpski", "sarba", "serbisch", "serbe", "српски"),
	"hrv": ("hrvatski", "croata", "kroatisch", "croate"),
	"slv": ("slovenscina", "slovena", "slowenisch", "slovene"),
	"slk": ("slovencina", "slovaca", "slowakisch", "slovaque"),
	"ces": ("cestina", "ceha", "tschechisch", "tcheque"),
	"pol": ("polski", "poloneza", "polnisch", "polonais"),
	"rus": ("russkij", "rusa", "russisch", "russe", "russo", "ruso", "русский"),
	"ukr": ("ukrainska", "ucraineana", "ukrainisch", "ukrainien", "українська"),
	"tur": ("turkce", "turca", "turkisch", "turc", "turco"),
	"ell": ("ellinika", "greaca", "griechisch", "grec", "greco", "greek", "ελληνικα"),
	"nld": ("nederlands", "olandeza", "niederlandisch", "hollandisch", "neerlandais", "flamand", "vlaams"),
	"swe": ("svenska", "suedeza", "schwedisch", "suedois"),
	"nor": ("norsk", "norvegiana", "norwegisch", "norvegien"),
	"dan": ("dansk", "daneza", "danisch", "danois"),
	"fin": ("suomi", "finlandeza", "finnisch", "finnois"),
	"ara": ("arabisch", "araba", "arabe", "العربية"),
	"cat": ("catala", "catalana", "katalanisch"),
	"est": ("eesti", "estona", "estnisch"),
	"lit": ("lietuviu", "lituaniana", "litauisch"),
	"lav": ("latviesu", "letona", "lettisch"),
	"isl": ("islenska", "islandeza", "islandisch"),
	"fry": ("frysk", "frizona", "friesisch"),
}

# descrierea audio pentru nevazatori: se recunoaste dupa text (EIT) sau dupa cuvant
_DESCRIERE_AUDIO = ("audiodeskription", "audio description", "audiodescription", "audio-description",
	"audiodescriere", "descriere audio", "audiodescripcion", "audiodescrizione", "horfilm", "hoerfilm",
	"audio desc")
_DESCRIERE_CUVINTE = frozenset(("ad", "qad", "blind", "blinde"))
# "ohne Audiodeskription", "without audio description": pista spune ca NU e descriere audio
_FARA_DESCRIERE = re.compile(r"\b(?:ohne|without|sans|fara|no|non|senza|sin|bez)\s+(?:%s)" % "|".join(
	re.escape(s) for s in _DESCRIERE_AUDIO))


def _faraDiacritice(text):
	"""Litere mici, fara semne diacritice (ș, ț, ä, é devin s, t, a, e); chirilicul si greaca raman."""
	t = unicodedata.normalize("NFKD", text)
	t = u"".join(c for c in t if not unicodedata.combining(c))
	return t.lower().strip()


def _text(valoare):
	"""Orice valoare venita din nucleu (str, bytes, None) -> text."""
	if valoare is None:
		return u""
	if isinstance(valoare, bytes):
		try:
			return valoare.decode("utf-8")
		except UnicodeDecodeError:
			return valoare.decode("latin-1")
	return u"%s" % (valoare,)


def _construiesteTabele():
	coduri = {}
	nume = {}
	grupuri = {}
	for cod, valoare in LanguageCodes.items():
		try:
			englez = valoare[0]
		except Exception:
			continue
		grupuri.setdefault(englez, []).append(cod.lower())
	for englez, lista in grupuri.items():
		trei = sorted(c for c in lista if len(c) == 3 and c not in _COD_B)
		canonic = trei[0] if trei else sorted(lista, key=lambda c: (-len(c), c))[0]
		for cod in lista:
			coduri[cod] = canonic
		cheie = _faraDiacritice(englez)
		nume.setdefault(cheie, canonic)
		scurt = cheie.split(",")[0].split("(")[0].strip()   # „greek, modern (1453-)" -> „greek"
		if scurt:
			nume.setdefault(scurt, canonic)
	for vechi, nou in _ALIAS.items():
		coduri[vechi] = coduri.get(nou, nou)
	for canonic, lista in _NUME_LOCALE.items():
		coduri.setdefault(canonic, canonic)
		for n in lista:
			nume[_faraDiacritice(n)] = canonic
	# „norwegian bokmal/nynorsk" din tabel au alt tuplu: pentru om sunt norvegiana
	for n in ("norwegian bokmal", "norwegian nynorsk", "norwegian"):
		nume[n] = "nor"
	# printre cuvintele unui text lung („Deutsch Mehrkanal") se cauta numai limbile din meniu, in engleza
	# si in forma locala: tabelul ISO are si nume scurte care sunt si cuvinte obisnuite („Ga", „Tiv")
	cuvinte = {}
	for canonic, englez in LIMBI_MENIU:
		cuvinte[_faraDiacritice(englez)] = canonic
	for canonic, lista in _NUME_LOCALE.items():
		for n in lista:
			cuvinte[_faraDiacritice(n)] = canonic
	return coduri, nume, cuvinte


_CODURI, _NUME, _NUME_CUVANT = _construiesteTabele()
_CUVANT = re.compile(r"\w+", re.UNICODE)
_DESPARTIRE = re.compile(r"[/,;+&|]")


def _cod(parte):
	"""O bucata de text care e chiar un cod (2-3 litere) -> codul canonic, sau None."""
	if parte in _FARA_LIMBA or _LOCAL.match(parte):
		return None
	if 2 <= len(parte) <= 3 and parte.isalpha():
		return _CODURI.get(parte)
	return None


def limbiDinText(text):
	"""Textul limbii unei piste („rum", „deu/eng", „Deutsch", „Română", „und", „Originalton")
	-> lista codurilor canonice ISO 639-2/T, fara repetari, in ordinea din text. [] = limba nu se stie."""
	t = _faraDiacritice(_text(text))
	if not t:
		return []
	rezultat = []
	for parte in _DESPARTIRE.split(t):
		parte = parte.strip()
		if not parte or parte in _FARA_LIMBA:
			continue
		c = _cod(parte)
		if c is None:
			c = _NUME.get(parte)
		if c is not None:
			if c not in rezultat:
				rezultat.append(c)
			continue
		# „Deutsch Mehrkanal", „Original English": se cauta numele printre cuvinte (nu si codurile:
		# „ton" din „Originalton" ar fi tongana)
		for cuvant in _CUVANT.findall(parte):
			c = _NUME_CUVANT.get(cuvant)
			if c is not None and c not in rezultat:
				rezultat.append(c)
	return rezultat


def limbaCanonica(text):
	"""Un cod sau nume de limba -> codul canonic (ron, deu, fra, ...), sau None."""
	l = limbiDinText(text)
	return l[0] if l else None


def esteDescriereAudio(text):
	t = _FARA_DESCRIERE.sub(u" ", _faraDiacritice(_text(text)))
	if not t.strip():
		return False
	for semn in _DESCRIERE_AUDIO:
		if semn in t:
			return True
	return any(c in _DESCRIERE_CUVINTE for c in _CUVANT.findall(t))


def _scurt(text):
	return _text(text).strip()[:MAX_TEXT]


# ------------------------------------------------------------------ pistele, in forma comuna

def pistaAudio(index, limba, descriere=u"", pid=None):
	"""O pista audio in forma pe care o intelege alegerea:
	{"index", "pid", "fel" (codecul: MPEG, AC3, AAC, ...), "text" (limba asa cum vine), "limbi" (coduri
	canonice), "descriere" (True = descriere audio pentru nevazatori)}."""
	try:
		pid = int(pid) if pid is not None else None
	except (TypeError, ValueError):
		pid = None
	return {
		"index": int(index),
		"pid": pid,
		"fel": _text(descriere).strip().upper()[:16],
		"text": _scurt(limba),
		"limbi": limbiDinText(limba)[:4],
		"descriere": esteDescriereAudio(limba),
	}


FEL_SUBTITRARE = {0: "dvb", 1: "ttx", 2: "fisier"}
_ORDINE_FEL = {"dvb": 0, "fisier": 1, "ttx": 2}


def subtitrareDinTuplu(tuplu, index=0):
	"""Un tuplu din getSubtitleList() -> forma comuna, sau None daca tuplul nu e bun.
	DVB: (0, pid, pagina compozitie, pagina auxiliara, limba); teletext: (1, pid, pagina, magazin, limba);
	fisier: (2, index, fel, 0, limba). Un al 6-lea camp adevarat = pentru surzi (daca il da nucleul)."""
	if not isinstance(tuplu, (list, tuple)) or len(tuplu) < 4:
		return None
	try:
		tip, pid, a, b = int(tuplu[0]), int(tuplu[1]), int(tuplu[2]), int(tuplu[3])
	except (TypeError, ValueError):
		return None
	limba = tuplu[4] if len(tuplu) > 4 else u""
	pagina = ("%x%02x" % ((b & 7) or 8, a & 0xFF)) if tip == 1 else None
	return {
		"index": int(index),
		"fel": FEL_SUBTITRARE.get(tip, "alt"),
		"pid": pid,
		"pagina": pagina,
		"text": _scurt(limba),
		"limbi": limbiDinText(limba)[:4],
		"surzi": bool(len(tuplu) > 5 and tuplu[5]),
		"tuplu": tuple(tuplu),
	}


def aceeasiSubtitrare(a, b):
	"""Doua tupluri de subtitrare arata aceeasi subtitrare? (primele 4 campuri; getCachedSubtitle da 4,
	getSubtitleList 5 sau mai multe)"""
	try:
		return bool(a) and bool(b) and len(a) >= 4 and len(b) >= 4 and tuple(a[:4]) == tuple(b[:4])
	except TypeError:
		return False


# ------------------------------------------------------------------ alegerea (curata)

def _limbaPreferinta(pref, limbaReceptor):
	if pref == PREF_RECEPTOR:
		return limbaCanonica(limbaReceptor)
	if pref in (None, u"", PREF_CANAL, PREF_NIMIC):
		return None
	return limbaCanonica(pref)


def _acelasiSet(a, b):
	return set(a or ()) == set(b or ())


def potrivesteAudio(piste, memorat):
	"""Pista tinuta minte, regasita printre pistele de acum dupa limba si fel; None daca nu mai exista."""
	if not isinstance(memorat, dict) or not piste:
		return None
	limbi = memorat.get("limbi") or []
	fel = memorat.get("fel") or u""
	pid = memorat.get("pid")
	desc = bool(memorat.get("descriere"))
	text = _faraDiacritice(_text(memorat.get("text")))
	if limbi:
		acelasi = [p for p in piste if p["limbi"] and _acelasiSet(p["limbi"], limbi) and p["descriere"] == desc]
		trepte = (
			[p for p in acelasi if p["fel"] == fel and p["pid"] == pid],
			[p for p in acelasi if p["fel"] == fel],
			acelasi,
		)
	else:
		fara = [p for p in piste if not p["limbi"]]
		trepte = (
			[p for p in fara if text and _faraDiacritice(p["text"]) == text and p["fel"] == fel and p["pid"] == pid],
			[p for p in fara if text and _faraDiacritice(p["text"]) == text and p["fel"] == fel],
			[p for p in fara if p["fel"] == fel and pid is not None and p["pid"] == pid],
			[p for p in fara if text and _faraDiacritice(p["text"]) == text],
		)
	for treapta in trepte:
		if treapta:
			return treapta[0]
	return None


def potrivesteSubtitrare(subtitrari, memorat):
	"""Subtitrarea tinuta minte, regasita dupa limba si fel (si pagina/PID cand sunt mai multe)."""
	if not isinstance(memorat, dict) or not subtitrari:
		return None
	limbi = memorat.get("limbi") or []
	fel = memorat.get("fel")
	pid = memorat.get("pid")
	pagina = memorat.get("pagina")
	surzi = bool(memorat.get("surzi"))

	def acelasiLoc(s):
		return (s["pagina"] == pagina) if s["fel"] == "ttx" else (s["pid"] == pid)

	if limbi:
		acelasi = [s for s in subtitrari if s["limbi"] and _acelasiSet(s["limbi"], limbi)]
		trepte = (
			[s for s in acelasi if s["fel"] == fel and s["surzi"] == surzi and acelasiLoc(s)],
			[s for s in acelasi if s["fel"] == fel and s["surzi"] == surzi],
			[s for s in acelasi if s["fel"] == fel],
			[s for s in acelasi if s["surzi"] == surzi],
			acelasi,
		)
	else:
		# fara limba (pagini de teletext gasite din mers): numai acelasi fel si aceeasi pagina/PID
		trepte = ([s for s in subtitrari if not s["limbi"] and s["fel"] == fel and acelasiLoc(s)],)
	for treapta in trepte:
		if treapta:
			return treapta[0]
	return None


def _celMaiBunAudio(candidati, limba, curenta, preferaAC3):
	def cheie(p):
		return (
			0 if p["limbi"] and p["limbi"][0] == limba else 1,   # „eng" inaintea lui „deu/eng"
			0 if p["index"] == curenta else 1,                   # cea care merge deja: fara intrerupere
			1 if (preferaAC3 and p["fel"] == "MPEG") else 0,     # config.av.defaultac3
			p["index"],
		)
	return sorted(candidati, key=cheie)[0]


def alegePistaAudio(piste, preferinte=PREF_AUDIO_IMPLICITE, limbaReceptor="ro", curenta=None,
		memorat=None, preferaAC3=False):
	"""-> (indexul pistei de pornit, motiv). Indexul None = ramane pista pornita de nucleu (pista
	implicita a canalului). Motive: memorat, preferinta-1/2/3, canal, fara-piste."""
	if not piste:
		return (None, "fara-piste")
	if memorat:
		p = potrivesteAudio(piste, memorat)
		if p is not None:
			return (p["index"], "memorat")
	for nr, pref in enumerate(tuple(preferinte or ())[:3]):
		if pref == PREF_CANAL:
			return (None, "canal")
		limba = _limbaPreferinta(pref, limbaReceptor)
		if not limba:
			continue
		candidati = [p for p in piste if limba in p["limbi"] and not p["descriere"]]
		if candidati:
			return (_celMaiBunAudio(candidati, limba, curenta, preferaAC3)["index"], "preferinta-%d" % (nr + 1))
	return (None, "canal")


# ------------------------------------------------------------------ dual mono: partea audio (curata)
# O pista cu doua limbi pe un singur flux audio („deu/eng”, dual mono) aleasa dupa
# limba se auzea cu amandoua limbile. lib/dvb/pmt.cpp lipeste cu „/” limbile din descriptorul ISO 639 al fluxului,
# in ordinea lor: prima e pe canalul stang, a doua pe cel drept (EN 300 468, dual mono). Partea se pune prin
# iAudioChannelSelection (0 stanga, 1 stereo, 2 dreapta), ca in ecranul sunetului.
#
# Nucleul tine minte partea pe canal, in lamedb (cACHANNEL, lib/service/servicedvb.cpp selectChannel), si o pune la
# loc la fiecare pornire a canalului (updateDecoder), si dupa repornire. De aceea ce pune alegerea automata se tine
# minte si aici, in piste-parti.json, nu numai cat merge enigma2: cand canalul trece pe o pista obisnuita, partea
# pusa de noi se scoate (stereo), altfel pista obisnuita s-ar auzi numai pe o parte. Partea schimbata de om (din
# ecranul sunetului, din bara a doua, din web) nu se mai atinge pe canalul acela (PARTE_DE_MANA), pana la „Uită”;
# dupa „Uită” (PARTE_UITATA) alegerea automata o ia de la capat, de la partea care merge.
CANAL_STANGA, CANAL_STEREO, CANAL_DREAPTA = 0, 1, 2
PARTE_DE_MANA = -1
PARTE_UITATA = -2
_PARTI_TINUTE = (CANAL_STANGA, CANAL_DREAPTA, PARTE_DE_MANA, PARTE_UITATA)
_NUME_PARTE = {CANAL_STANGA: "stanga", CANAL_STEREO: "stereo", CANAL_DREAPTA: "dreapta"}


def _partiDualMono(text):
	"""„deu/eng” -> ["deu", "eng"] (codul canonic sau None pe fiecare parte); None daca pista nu e dual mono."""
	parti = [p.strip() for p in _text(text).split(u"/")]
	if len(parti) != 2 or not all(parti):
		return None
	return [limbaCanonica(p) for p in parti]


def canalDualMono(pista, limba):
	"""Pista dual mono si limba dorita -> CANAL_STANGA sau CANAL_DREAPTA; None pentru orice alta pista, pentru
	descrierea audio si cand limba e pe amandoua partile sau pe niciuna."""
	if not pista or not limba or pista.get("descriere"):
		return None
	parti = _partiDualMono(pista.get("text"))
	if not parti or parti[0] == parti[1]:
		return None
	if parti[0] == limba:
		return CANAL_STANGA
	if parti[1] == limba:
		return CANAL_DREAPTA
	return None


def canalPentruAlegere(piste, index, motiv, preferinte=PREF_AUDIO_IMPLICITE, limbaReceptor="ro", curenta=None):
	"""Dupa alegerea pistei (alegePistaAudio): partea audio dorita. CANAL_STANGA sau CANAL_DREAPTA la o pista dual
	mono aleasa dupa limba; CANAL_STEREO la o pista obisnuita si la dual mono fara limba potrivita (se scoate numai o
	parte pusa tot de alegerea automata, vezi decideParte); None = nu se atinge (dual mono aleasa de mana: partea o
	alege omul in ecranul sunetului)."""
	if motiv == "fara-piste" or not piste:
		return None
	i = index if index is not None else curenta
	pista = None
	for p in piste:
		if p["index"] == i:
			pista = p
			break
	if pista is None:
		return None
	if _partiDualMono(pista.get("text")) is None:
		return CANAL_STEREO
	if motiv == "memorat":
		return None
	limba = None
	if motiv and motiv.startswith("preferinta-"):
		try:
			limba = _limbaPreferinta(tuple(preferinte or ())[int(motiv.split("-")[1]) - 1], limbaReceptor)
		except (ValueError, IndexError):
			limba = None
	parte = canalDualMono(pista, limba)
	return CANAL_STEREO if parte is None else parte


def decideParte(dorit, acum, pus, pusInSesiune=False):
	"""Partea audio de pus acum si ce se tine minte pe canal (curata).
	dorit: din canalPentruAlegere; acum: partea care merge (None = serviciul nu are); pus: ce tine minte canalul
	(CANAL_STANGA/CANAL_DREAPTA = pusa de alegerea automata, PARTE_DE_MANA, PARTE_UITATA sau None); pusInSesiune:
	alegerea automata a pus-o de cand merge enigma2 (atunci nucleul n-a avut cum sa o piarda).
	-> (partea de pus acum sau None, ce se tine minte de acum: o parte, PARTE_DE_MANA, PARTE_UITATA sau None)"""
	if dorit is None or acum is None or pus == PARTE_DE_MANA:
		return (None, pus)
	laterala = dorit in (CANAL_STANGA, CANAL_DREAPTA)
	if pus == PARTE_UITATA:
		return (dorit if acum != dorit else None, dorit if laterala else None)
	if pus in (CANAL_STANGA, CANAL_DREAPTA) and acum != pus:
		if acum != CANAL_STEREO or pusInSesiune:
			return (None, PARTE_DE_MANA)          # schimbata de om dupa ce a pus-o alegerea automata
		pus = None                                 # nucleul a pierdut-o (oprit fara salvarea lamedb): de la capat
	if pus is None:
		if laterala and acum == CANAL_STEREO:
			return (dorit, dorit)
		return (None, None)                        # stereo, sau o parte pusa de altcineva: nu se atinge
	if dorit != pus:                               # partea noastra merge inca: alta parte, sau stereo
		return (dorit, dorit if laterala else None)
	return (None, pus)


def alegeSubtitrare(subtitrari, preferinte=PREF_SUBTITRARE_IMPLICITE, limbaReceptor="ro", niciodata=False,
		memorat=None):
	"""-> (subtitrarea de pornit in forma comuna, sau None pentru nicio subtitrare; motiv).
	Motive: memorat, memorat-oprit, niciodata, preferinta-1/2/3, fara-potrivire."""
	if memorat == OPRIT:
		return (None, "memorat-oprit")
	if memorat and subtitrari:
		s = potrivesteSubtitrare(subtitrari, memorat)
		if s is not None:
			return (s, "memorat")
	if niciodata:
		return (None, "niciodata")
	for nr, pref in enumerate(tuple(preferinte or ())[:3]):
		limba = _limbaPreferinta(pref, limbaReceptor)
		if not limba:
			continue
		candidati = [s for s in (subtitrari or ()) if limba in s["limbi"]]
		if candidati:
			ales = sorted(candidati, key=lambda s: (
				1 if s["surzi"] else 0,                           # cele obisnuite inaintea celor pentru surzi
				0 if s["limbi"][0] == limba else 1,
				_ORDINE_FEL.get(s["fel"], 9),                    # DVB, apoi fisier, apoi teletext
				s["index"],
			))[0]
			return (ales, "preferinta-%d" % (nr + 1))
	return (None, "fara-potrivire")


def _ordineLimbiTraducere(preferinte, limbaReceptor, tinta):
	"""Limbile din care se traduce cel mai bine, in ordine: cele din preferintele subtitrarii (fara limba traducerii),
	apoi engleza."""
	ordine = []
	for pref in tuple(preferinte or ())[:3]:
		limba = _limbaPreferinta(pref, limbaReceptor)
		if limba and limba != tinta and limba not in ordine:
			ordine.append(limba)
	if "eng" != tinta and "eng" not in ordine:
		ordine.append("eng")
	return ordine


def _cheieTraducere(s, ordine):
	"""Ordinea candidatilor din alta limba: limba (din `ordine`, apoi celelalte stiute, apoi fara limba), subtitrarea
	obisnuita inaintea celei pentru surzi, apoi ordinea din lista."""
	limba = s["limbi"][0] if s["limbi"] else None
	if limba is None:
		loc = len(ordine) + 1
	elif limba in ordine:
		loc = ordine.index(limba)
	else:
		loc = len(ordine)
	return (loc, 1 if s["surzi"] else 0, s["index"])


def alegeSubtitrareTradusa(subtitrari, tinta, preferinte=PREF_SUBTITRARE_IMPLICITE, limbaReceptor="ro",
		niciodata=False, memorat=None, traduOrice=True, poateCiti=None):
	"""Alegerea cu traducerea subtitrarilor pornita (vezi „CU TRADUCEREA” sus). tinta = limba traducerii (orice cod sau
	nume); poateCiti(limba) -> True daca o pista DVB in limba aceea se poate citi cu OCR acum (None = niciuna).
	-> (subtitrarea in forma comuna sau None; motiv). Motive: memorat, memorat-oprit, niciodata, traducere-tinta,
	traducere-teletext, traducere-dvb, apoi cele din alegeSubtitrare (preferinta-1/2/3, fara-potrivire)."""
	if memorat == OPRIT:
		return (None, "memorat-oprit")
	if memorat and subtitrari:
		s = potrivesteSubtitrare(subtitrari, memorat)
		if s is not None:
			return (s, "memorat")
	if niciodata:
		return (None, "niciodata")
	lista = list(subtitrari or ())
	t = limbaCanonica(tinta) if tinta else None
	if t:
		candidati = [s for s in lista if t in s["limbi"]]
		if candidati:
			ales = sorted(candidati, key=lambda s: (
				1 if s["surzi"] else 0,
				0 if s["limbi"][0] == t else 1,
				_ORDINE_FEL.get(s["fel"], 9),
				s["index"],
			))[0]
			return (ales, MOTIV_TRADUCERE_TINTA)
	if traduOrice and t:
		ordine = _ordineLimbiTraducere(preferinte, limbaReceptor, t)
		text = [s for s in lista if s["fel"] in ("ttx", "fisier")]
		if text:
			return (min(text, key=lambda s: _cheieTraducere(s, ordine)), MOTIV_TRADUCERE_TEXT)
		dvb = []
		for s in lista:
			if s["fel"] != "dvb" or not s["limbi"] or poateCiti is None:
				continue
			try:
				if poateCiti(s["limbi"][0]):
					dvb.append(s)
			except Exception:
				pass
		if dvb:
			return (min(dvb, key=lambda s: _cheieTraducere(s, ordine)), MOTIV_TRADUCERE_DVB)
	return alegeSubtitrare(lista, preferinte, limbaReceptor, False, None)


# ------------------------------------------------------------------ cheia unui canal (curata)

def cheieDinReferinta(text):
	"""Textul unei referinte de serviciu -> cheia canalului in fisierul alegerilor, sau None.
	DVB: „sid:tsid:onid:spatiu" in hexazecimal (fara tipul serviciului, care difera intre liste);
	flux din retea: „url:" + adresa; fisier (inregistrare, film): None - cheia o da canalul de origine."""
	t = _text(text).strip()
	if not t:
		return None
	campuri = t.split(":")
	if len(campuri) < 10:
		return None
	cale = campuri[10] if len(campuri) > 10 else u""
	if cale:
		if cale.startswith("/"):
			return None
		return (u"url:" + cale)[:MAX_CHEIE]
	try:
		sid, tsid, onid, spatiu = [int(x or "0", 16) for x in campuri[3:7]]
	except ValueError:
		return None
	if not (sid or tsid or onid or spatiu):
		return None
	return u"%x:%x:%x:%x" % (sid, tsid, onid, spatiu)


def referintaDinCheie(cheie, tip=1):
	"""Cheia unui canal DVB -> o referinta de serviciu cu care se poate cauta numele canalului (pagina web).
	Tipul serviciului nu e in cheie: se da `tip` (1 = TV SD; 0x19, 0x16, 0x1f = TV HD; 2 = radio). None la
	fluxuri si la chei rele."""
	campuri = _text(cheie).split(":")
	if len(campuri) != 4:
		return None
	try:
		sid, tsid, onid, spatiu = [int(x, 16) for x in campuri]
	except ValueError:
		return None
	return u"1:0:%X:%X:%X:%X:%X:0:0:0:" % (tip, sid, tsid, onid, spatiu)


# ------------------------------------------------------------------ ce se tine minte

def amprentaAudio(pista):
	"""Ce se scrie in fisier pentru o pista audio aleasa de mana."""
	return {
		"limbi": list(pista.get("limbi") or [])[:4],
		"text": _scurt(pista.get("text")),
		"fel": _text(pista.get("fel")).strip().upper()[:16],
		"pid": pista.get("pid") if isinstance(pista.get("pid"), int) else None,
		"descriere": bool(pista.get("descriere")),
	}


def amprentaSubtitrare(sub):
	"""Ce se scrie in fisier pentru o subtitrare aleasa de mana (None -> OPRIT)."""
	if not sub:
		return OPRIT
	return {
		"limbi": list(sub.get("limbi") or [])[:4],
		"text": _scurt(sub.get("text")),
		"fel": sub.get("fel") if sub.get("fel") in ("dvb", "ttx", "fisier", "alt") else "alt",
		"pid": sub.get("pid") if isinstance(sub.get("pid"), int) else None,
		"pagina": _scurt(sub.get("pagina"))[:4] if sub.get("pagina") else None,
		"surzi": bool(sub.get("surzi")),
	}


_COD_LIMBA = re.compile(r"^[a-z]{2,3}$")


def _curataLimbi(valoare):
	if not isinstance(valoare, list):
		return []
	return [x for x in valoare if isinstance(x, str) and _COD_LIMBA.match(x)][:4]


def _curataIntreg(valoare):
	return valoare if isinstance(valoare, int) and not isinstance(valoare, bool) and 0 <= valoare < 0x10000 else None


def _curataAudio(v):
	if not isinstance(v, dict):
		return None
	return {
		"limbi": _curataLimbi(v.get("limbi")),
		"text": _scurt(v.get("text")) if isinstance(v.get("text"), str) else u"",
		"fel": v.get("fel").strip().upper()[:16] if isinstance(v.get("fel"), str) else u"",
		"pid": _curataIntreg(v.get("pid")),
		"descriere": v.get("descriere") is True,
	}


def _curataSub(v):
	if v == OPRIT:
		return OPRIT
	if not isinstance(v, dict):
		return None
	fel = v.get("fel")
	pagina = v.get("pagina")
	return {
		"limbi": _curataLimbi(v.get("limbi")),
		"text": _scurt(v.get("text")) if isinstance(v.get("text"), str) else u"",
		"fel": fel if fel in ("dvb", "ttx", "fisier", "alt") else "alt",
		"pid": _curataIntreg(v.get("pid")),
		"pagina": pagina[:4] if isinstance(pagina, str) and re.match(r"^[0-9a-f]{3}$", pagina[:4]) else None,
		"surzi": v.get("surzi") is True,
	}


def _curataDate(obiect, maxCanale):
	"""Continutul citit din fisier -> {cheie: {"a": ..., "s": ..., "t": ...}}; orice nu e cum trebuie pleaca."""
	if not isinstance(obiect, dict) or obiect.get("versiune") != 1 or not isinstance(obiect.get("canale"), dict):
		return None
	date = {}
	for cheie, valoare in obiect["canale"].items():
		if not isinstance(cheie, str) or not cheie or len(cheie) > MAX_CHEIE or not isinstance(valoare, dict):
			continue
		intrare = {}
		a = _curataAudio(valoare.get("a")) if "a" in valoare else None
		s = _curataSub(valoare.get("s")) if "s" in valoare else None
		if a is not None:
			intrare["a"] = a
		if s is not None:
			intrare["s"] = s
		if not intrare:
			continue
		t = valoare.get("t")
		intrare["t"] = int(t) if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 else 0
		date[cheie] = intrare
	return _taieVechi(date, maxCanale)


def _taieVechi(date, maxCanale):
	if len(date) <= maxCanale:
		return date
	pastrate = sorted(date.items(), key=lambda kv: (kv[1].get("t", 0), kv[0]), reverse=True)[:maxCanale]
	return dict(pastrate)


class MemorieAlegeri(object):
	"""Alegerile de mana tinute minte pe canal, in fisierul CALE_ALEGERI.
	Citirea se face la fiecare cerere, dar fisierul se parseaza doar cand i s-a schimbat marimea sau ora
	(o zapare costa un os.stat). Scrierea: .nou + fsync + os.replace; un fisier stricat nu opreste nimic."""
	_curata = staticmethod(_curataDate)

	def __init__(self, cale=CALE_ALEGERI, maxCanale=MAX_CANALE, maxOcteti=MAX_OCTETI, ceas=None):
		self.cale = cale
		self.maxCanale = maxCanale
		self.maxOcteti = maxOcteti
		self.ceas = ceas or time.time
		self._date = {}
		self._semn = None

	def _citeste(self):
		try:
			st = os.stat(self.cale)
		except OSError:
			self._date = {}
			self._semn = None
			return self._date
		semn = (getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)), st.st_size)
		if semn == self._semn:
			return self._date
		self._semn = semn
		self._date = {}
		if st.st_size > self.maxOcteti:
			print("[HdsPisteLimbi] %s are %d octeti, peste limita de %d: nu il folosesc" % (self.cale, st.st_size, self.maxOcteti))
			return self._date
		try:
			with open(self.cale, "rb") as f:
				obiect = json.loads(f.read(self.maxOcteti + 1).decode("utf-8"))
		except (OSError, IOError, ValueError, UnicodeDecodeError):
			print("[HdsPisteLimbi] %s nu se poate citi: il ignor si pornesc de la zero" % self.cale)
			return self._date
		date = self._curata(obiect, self.maxCanale)
		if date is None:
			print("[HdsPisteLimbi] %s nu are forma asteptata: il ignor si pornesc de la zero" % self.cale)
			return self._date
		self._date = date
		return self._date

	def _scrie(self, date):
		date = _taieVechi(date, self.maxCanale)
		text = json.dumps({"versiune": 1, "canale": date}, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
		while len(text) > self.maxOcteti and date:
			cel_vechi = min(date.items(), key=lambda kv: (kv[1].get("t", 0), kv[0]))[0]
			del date[cel_vechi]
			text = json.dumps({"versiune": 1, "canale": date}, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
		nou = self.cale + ".nou"
		try:
			dosar = os.path.dirname(self.cale)
			if dosar and not os.path.isdir(dosar):
				os.makedirs(dosar)
			with open(nou, "wb") as f:
				f.write(text.encode("ascii"))
				f.flush()
				os.fsync(f.fileno())
			for incercare in range(3):
				try:
					os.replace(nou, self.cale)
					break
				except OSError:
					if incercare == 2:
						raise
					time.sleep(0.05)
		except (OSError, IOError) as e:
			print("[HdsPisteLimbi] alegerea nu s-a putut scrie in %s: %s" % (self.cale, e))
			try:
				os.unlink(nou)
			except OSError:
				pass
			return False
		self._date = date
		try:
			st = os.stat(self.cale)
			self._semn = (getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)), st.st_size)
		except OSError:
			self._semn = None
		return True

	def alegere(self, cheie):
		"""{"a": amprenta audio, "s": amprenta subtitrare sau OPRIT} pentru canal ({} daca nimic)."""
		if not cheie:
			return {}
		intrare = self._citeste().get(cheie)
		return dict(intrare) if intrare else {}

	def noteazaAudio(self, cheie, amprenta):
		return self._noteaza(cheie, "a", _curataAudio(amprenta))

	def noteazaSubtitrare(self, cheie, amprenta):
		return self._noteaza(cheie, "s", _curataSub(amprenta))

	def _noteaza(self, cheie, camp, valoare):
		if not cheie or len(cheie) > MAX_CHEIE or valoare is None:
			return False
		date = dict(self._citeste())
		intrare = dict(date.get(cheie) or {})
		intrare[camp] = valoare
		intrare["t"] = int(self.ceas())
		date[cheie] = intrare
		return self._scrie(date)

	def uita(self, cheie=None):
		"""Sterge alegerile unui canal (sau ale tuturor, cheie=None). Intoarce cate canale s-au sters."""
		date = dict(self._citeste())
		if cheie is None:
			numar = len(date)
			if not numar and not os.path.exists(self.cale):
				return 0
			return numar if self._scrie({}) else 0
		if cheie not in date:
			return 0
		del date[cheie]
		return 1 if self._scrie(date) else 0

	def numar(self):
		return len(self._citeste())

	def toate(self):
		"""Copie a tuturor alegerilor: {cheie: {"a", "s", "t"}} (pentru pagina web)."""
		return dict((cheie, dict(intrare)) for cheie, intrare in self._citeste().items())


_MEMORIE = None


def memorie():
	global _MEMORIE
	if _MEMORIE is None:
		_MEMORIE = MemorieAlegeri()
	return _MEMORIE


def _curataParti(obiect, maxCanale):
	"""Continutul lui piste-parti.json -> {cheie: {"p": parte, "t": ora}}; orice nu e cum trebuie pleaca."""
	if not isinstance(obiect, dict) or obiect.get("versiune") != 1 or not isinstance(obiect.get("canale"), dict):
		return None
	date = {}
	for cheie, valoare in obiect["canale"].items():
		if not isinstance(cheie, str) or not cheie or len(cheie) > MAX_CHEIE or not isinstance(valoare, dict):
			continue
		p = valoare.get("p")
		if not isinstance(p, int) or isinstance(p, bool) or p not in _PARTI_TINUTE:
			continue
		t = valoare.get("t")
		date[cheie] = {"p": p, "t": int(t) if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 else 0}
	return _taieVechi(date, maxCanale)


class MemoriePartiAudio(MemorieAlegeri):
	"""piste-parti.json: pe fiecare canal, partea audio pusa de alegerea automata la o pista dual mono, sau
	PARTE_DE_MANA / PARTE_UITATA. Acelasi fel de fisier ca al alegerilor: atomic, limitat, stricat = ignorat."""
	_curata = staticmethod(_curataParti)

	def __init__(self, cale=CALE_PARTI, maxCanale=MAX_CANALE, maxOcteti=MAX_OCTETI, ceas=None):
		MemorieAlegeri.__init__(self, cale, maxCanale, maxOcteti, ceas)

	def parte(self, cheie):
		intrare = self._citeste().get(cheie) if cheie else None
		return intrare["p"] if intrare else None

	def pune(self, cheie, parte):
		"""parte None = se sterge. -> True daca fisierul are ce trebuie (se scrie numai la o schimbare)."""
		if not cheie or len(cheie) > MAX_CHEIE or isinstance(parte, bool) or (parte is not None and parte not in _PARTI_TINUTE):
			return False
		date = dict(self._citeste())
		if parte is None:
			if cheie not in date:
				return True
			del date[cheie]
		else:
			if (date.get(cheie) or {}).get("p") == parte:
				return True
			date[cheie] = {"p": parte, "t": int(self.ceas())}
		return self._scrie(date)

	def deMana(self):
		"""Cheile canalelor pe care omul a schimbat partea audio."""
		return set(k for k, v in self._citeste().items() if v.get("p") == PARTE_DE_MANA)

	def uitaDeMana(self, cheie=None):
		"""„Uită”: partea schimbata de om (pe un canal sau pe toate) trece iar la alegerea automata (PARTE_UITATA).
		Partile puse de alegerea automata raman tinute minte, ca sa poata fi scoase. -> cate canale."""
		date = dict(self._citeste())
		chei = [k for k, v in date.items() if v.get("p") == PARTE_DE_MANA and (cheie is None or k == cheie)]
		if not chei:
			return 0
		acum = int(self.ceas())
		for k in chei:
			date[k] = {"p": PARTE_UITATA, "t": acum}
		return len(chei) if self._scrie(date) else 0


_MEMORIE_PARTI = None


def memoriePartilor():
	global _MEMORIE_PARTI
	if _MEMORIE_PARTI is None:
		_MEMORIE_PARTI = MemoriePartiAudio()
	return _MEMORIE_PARTI


# ------------------------------------------------------------------ setarile (config)

def initConfig():
	"""config.hds_piste: cate 3 preferinte pentru sunet si subtitrare, plus „fara subtitrari niciodata".
	Se poate chema de oricate ori."""
	from Components.config import config, ConfigSubsection, ConfigSelection, ConfigYesNo
	if "hds_piste" in config.content.items:
		c = config.hds_piste
		if "tradu_orice" not in c.content.items:
			c.tradu_orice = ConfigYesNo(default=True)
		return c
	limbi = sorted(((cod, _(nume)) for cod, nume in LIMBI_MENIU), key=lambda x: _faraDiacritice(x[1]))
	receptor = (PREF_RECEPTOR, _("Limba receptorului"))
	alegeriAudio = [receptor, (PREF_CANAL, _("Pista implicită a canalului"))] + limbi
	alegeriSub = [receptor, (PREF_NIMIC, _("Nimic"))] + limbi
	config.hds_piste = ConfigSubsection()
	config.hds_piste.audio1 = ConfigSelection(choices=alegeriAudio, default=PREF_AUDIO_IMPLICITE[0])
	config.hds_piste.audio2 = ConfigSelection(choices=alegeriAudio, default=PREF_AUDIO_IMPLICITE[1])
	config.hds_piste.audio3 = ConfigSelection(choices=alegeriAudio, default=PREF_AUDIO_IMPLICITE[2])
	config.hds_piste.sub1 = ConfigSelection(choices=alegeriSub, default=PREF_SUBTITRARE_IMPLICITE[0])
	config.hds_piste.sub2 = ConfigSelection(choices=alegeriSub, default=PREF_SUBTITRARE_IMPLICITE[1])
	config.hds_piste.sub3 = ConfigSelection(choices=alegeriSub, default=PREF_SUBTITRARE_IMPLICITE[2])
	config.hds_piste.fara_subtitrari = ConfigYesNo(default=False)
	# cu traducerea subtitrarilor pornita: Da = se alege si o subtitrare in alta limba (teletext, apoi DVB cu OCR), ca sa
	# fie tradusa; Nu = numai una in limba traducerii, apoi preferintele de mai sus
	config.hds_piste.tradu_orice = ConfigYesNo(default=True)
	return config.hds_piste


def preferinteAudio():
	c = initConfig()
	return (c.audio1.value, c.audio2.value, c.audio3.value)


def preferinteSubtitrare():
	c = initConfig()
	return (c.sub1.value, c.sub2.value, c.sub3.value)


def faraSubtitrariNiciodata():
	return bool(initConfig().fara_subtitrari.value)


def traduOrice():
	"""„Tradu automat din orice subtitrare disponibilă” (Da din fabrica)."""
	return bool(initConfig().tradu_orice.value)


def limbaTraducerii():
	"""Codul canonic al limbii traducerii („ron”) cand traducerea subtitrarilor e pornita, altfel None
	(Components/HdsTraducereSubtitrari.py: config.hds_traducere.pornit, limbaTinta())."""
	try:
		from Components import HdsTraducereSubtitrari as T
		s = T.initConfig()
		if not s.pornit.value:
			return None
		return limbaCanonica(T.limbaTinta(s)) or None
	except Exception as e:
		print("[HdsPisteLimbi] limba traducerii nu se poate citi: %s" % e)
		return None


def _ocrPoateCiti(limba):
	"""Components/HdsOcrSubtitrari.poateCiti: o pista DVB in limba `limba` se poate citi ca text acum."""
	try:
		from Components import HdsOcrSubtitrari
		return bool(HdsOcrSubtitrari.poateCiti(limba))
	except Exception as e:
		print("[HdsPisteLimbi] OCR: %s" % e)
		return False


def textTraducere():
	"""Fraza despre traducere de sub preferinte (ecranul si pagina web): ce face „Tradu automat din orice subtitrare
	disponibilă” acum."""
	tinta = limbaTraducerii()
	if not tinta:
		return _("Cu traducerea subtitrărilor pornită, „Tradu automat din orice subtitrare disponibilă” alege singură "
			"și o subtitrare în altă limbă, ca să fie tradusă.")
	if traduOrice():
		return _("Traducerea subtitrărilor e pornită (în %s): dacă nu există subtitrare în limba aceasta, se alege "
			"singură una în altă limbă, întâi teletextul, apoi DVB citită ca text, și se traduce.") % numeLimba(tinta)
	return _("Traducerea subtitrărilor e pornită (în %s): se alege numai o subtitrare în limba aceasta, apoi "
		"preferințele de mai sus.") % numeLimba(tinta)


def alegeAcum(lista, memorat):
	"""Alegerea subtitrarii unui canal: cu traducerea pornita alegeSubtitrareTradusa, altfel alegeSubtitrare."""
	tinta = limbaTraducerii()
	if tinta:
		return alegeSubtitrareTradusa(lista, tinta, preferinteSubtitrare(), limbaReceptor(), faraSubtitrariNiciodata(),
			memorat, traduOrice(), _ocrPoateCiti)
	return alegeSubtitrare(lista, preferinteSubtitrare(), limbaReceptor(), faraSubtitrariNiciodata(), memorat)


def limbaReceptor():
	"""Limba meniului receptorului, cod canonic („ron" pentru ro_RO)."""
	valoare = u""
	try:
		from Components.config import config
		valoare = _text(config.osd.language.value)
	except Exception:
		valoare = u""
	if not valoare:
		try:
			from Components.Language import language
			valoare = _text(language.getLanguage())
		except Exception:
			valoare = u""
	return limbaCanonica(valoare[:2]) or "eng"


def preferaAC3():
	try:
		from Components.config import config
		return bool(config.av.defaultac3.value)
	except Exception:
		return False


def _pista51(piste, index, curenta, motiv):
	"""Components/HdsSunet.py: cand AC3 pleaca neschimbat spre televizor, pista AC3 / AC3+ in aceeasi limba."""
	try:
		from Components import HdsSunet
	except ImportError:
		return index
	try:
		return HdsSunet.pistaPreferata(piste, index, curenta, motiv)
	except Exception as e:
		print("[HdsPisteLimbi] pista AC3: %s" % e)
		return index


def numeLimba(cod):
	"""Codul canonic -> numele limbii, tradus („ron" -> „Română")."""
	for c, nume in LIMBI_MENIU:
		if c == cod:
			return _(nume)
	if cod in _NUME_ALTE:
		return _(_NUME_ALTE[cod])
	valoare = LanguageCodes.get(cod or u"")
	return _(valoare[0]) if valoare else (cod or u"")


_TEXT_MOTIV = {
	"memorat": "aleasă de mână pe canalul acesta",
	"memorat-oprit": "oprită de mână pe canalul acesta",
	"niciodata": "oprite din setări",
	"canal": "pista implicită a canalului",
	"fara-potrivire": "nu există în limbile alese",
	"fara-piste": "",
	MOTIV_TRADUCERE_TINTA: N_("în limba traducerii"),
	MOTIV_TRADUCERE_TEXT: N_("teletext tradus automat"),
	MOTIV_TRADUCERE_DVB: N_("DVB citită ca text și tradusă automat"),
}


def textMotiv(motiv):
	"""Motivul alegerii, pentru om („după preferința 1", „aleasă de mână pe canalul acesta")."""
	if motiv and motiv.startswith("preferinta-"):
		return _("după preferința %s") % motiv.split("-")[1]
	text = _TEXT_MOTIV.get(motiv or u"", u"")
	return _(text) if text else u""


# ------------------------------------------------------------------ legatura cu serviciul (enigma)

# ultima alegere facuta pe serviciul care merge, pentru ecranele care arata pistele (pagina cu PID-uri)
_ULTIMA = {"audio": None, "subtitrare": None}


def ultimaAlegere():
	"""{"audio": {"cheie", "index", "motiv"} sau None, "subtitrare": {"cheie", "tuplu", "motiv"} sau None}"""
	return {"audio": dict(_ULTIMA["audio"]) if _ULTIMA["audio"] else None,
		"subtitrare": dict(_ULTIMA["subtitrare"]) if _ULTIMA["subtitrare"] else None}


def _refText(ref):
	try:
		return _text(ref.toString()) if ref is not None else u""
	except Exception:
		return u""


def cheieCanal(ref):
	"""Referinta serviciului care merge -> cheia canalului. La o inregistrare, canalul de origine (.meta)."""
	if ref is None:
		return None
	text = _refText(ref)
	try:
		cale = _text(ref.getPath())
	except Exception:
		cale = u""
	if cale.startswith("/"):
		try:
			from enigma import eServiceCenter, iServiceInformation
			info = eServiceCenter.getInstance().info(ref)
			origine = info and info.getInfoString(ref, iServiceInformation.sServiceref)
		except Exception:
			origine = None
		return cheieDinReferinta(origine) if origine else None
	return cheieDinReferinta(text)


def pisteAudio(service):
	"""Serviciul care merge -> (lista pistelor audio in forma comuna, indexul celei pornite sau -1)."""
	audio = service and service.audioTracks()
	if not audio:
		return ([], -1)
	try:
		n = int(audio.getNumberOfTracks() or 0)
	except Exception:
		n = 0
	piste = []
	for i in range(min(n, MAX_PISTE)):
		info = audio.getTrackInfo(i)
		if info is None:
			piste.append(pistaAudio(i, u"", u"", None))
			continue
		pid = None
		try:
			pid = info.getPID()
		except Exception:
			pid = None
		piste.append(pistaAudio(i, info.getLanguage(), info.getDescription(), pid))
	try:
		curenta = int(audio.getCurrentTrack())
	except Exception:
		curenta = -1
	return (piste, curenta)


def subtitrari(sursa):
	"""Serviciul care merge, sau ecranul InfoBar -> lista subtitrarilor in forma comuna (fiecare cu tuplul
	original in "tuplu"), plus campurile cerute de afisajul interactiv: "tip" (dvb/ttx/fisier), "limba" (numele
	pentru om), "pid_sau_pagina" si "pornita"."""
	if sursa is not None and hasattr(sursa, "subtitle_window") and hasattr(sursa, "session"):
		infobar = sursa
		service = infobar.session.nav.getCurrentService()
	else:
		infobar = None
		service = sursa
	sub = service and service.subtitle()
	lista = (sub and sub.getSubtitleList()) or []
	pornita = subtitrare_pornita(infobar if infobar is not None else infobarActiv())
	rezultat = []
	for tuplu in list(lista)[:MAX_PISTE]:
		s = subtitrareDinTuplu(tuplu, len(rezultat))
		if s is not None:
			s["tip"] = s["fel"]
			s["limba"] = numeLimba(s["limbi"][0]) if s["limbi"] else s["text"]
			s["pid_sau_pagina"] = s["pagina"] if s["fel"] == "ttx" else s["pid"]
			s["pornita"] = aceeasiSubtitrare(s["tuplu"], pornita)
			rezultat.append(s)
	return rezultat


def aplicaAudio(session, semn=None):
	"""Chemat la evUpdatedInfo: alege pista audio dupa memorie si preferinte. Intoarce semnul pistelor
	(referinta + PID-uri + codecuri); cat timp semnul nu se schimba, nu se mai face nimic."""
	service = session.nav.getCurrentService()
	piste, curenta = pisteAudio(service)
	if not piste:
		return semn
	ref = session.nav.getCurrentlyPlayingServiceReference()
	semnNou = (_refText(ref), tuple((p["pid"], p["fel"]) for p in piste))
	if semnNou == semn:
		return semn
	cheie = cheieCanal(ref)
	if len(piste) == 1 and _partiDualMono(piste[0]["text"]) is None:
		try:
			_puneCanalAudio(service, ref, CANAL_STEREO, cheie)
		except Exception as e:
			print("[HdsPisteLimbi] partea audio nu s-a putut pune: %s" % e)
		_ULTIMA["audio"] = {"cheie": cheie, "index": 0, "motiv": "canal"}
		return semnNou
	memorat = memorie().alegere(cheie).get("a") if cheie else None
	preferinte, limba = preferinteAudio(), limbaReceptor()
	index, motiv = alegePistaAudio(piste, preferinte, limba, curenta, memorat, preferaAC3())
	index = _pista51(piste, index, curenta, motiv)
	if index is not None and index != curenta:
		audio = service.audioTracks()
		audio.selectTrack(index)
		print("[HdsPisteLimbi] sunet: pista %d din %d (%s, %s), %s" % (index + 1, len(piste),
			piste[index]["text"] or "-", piste[index]["fel"] or "-", motiv))
	try:
		_puneCanalAudio(service, ref, canalPentruAlegere(piste, index, motiv, preferinte, limba, curenta), cheie)
	except Exception as e:
		print("[HdsPisteLimbi] partea audio nu s-a putut pune: %s" % e)
	_ULTIMA["audio"] = {"cheie": cheie, "index": index if index is not None else curenta, "motiv": motiv}
	return semnNou


# partea audio (dual mono, vezi decideParte), tinuta minte pe ce o tine si nucleul (cACHANNEL, servicedvb.cpp):
# - canal din lamedb (referinta fara cale): nucleul o tine pe serviciul din lamedb, deci si noi in piste-parti.json,
#   dupa cheia canalului;
# - inregistrare: nucleul o tine in .meta-ul ei (scris la oprirea redarii, ~eDVBServicePlay), alt loc decat canalul
#   viu; flux din retea: deloc, fiecare pornire incepe pe stereo; film din MediaPlayer: nu e DVB. Pentru toate acestea
#   partea se tine minte numai cat merge enigma2, in _PARTI_FARA_CHEIE, dupa referinta.
# _CANAL_PUS: partile puse de alegerea automata de cand merge enigma2, tot dupa referinta. Numai la canalele din
# lamedb inseamna „nucleul n-a avut cum sa o piarda” (la un flux o pierde la fiecare pornire).
_CANAL_PUS = {}
_PARTI_FARA_CHEIE = {}


def _cheieSesiune(ref):
	return u"ref:" + _refText(ref)


def _eViu(ref):
	"""Referinta fara cale: un canal DVB din lamedb (nu inregistrare, nu flux, nu fisier)."""
	try:
		return ref is not None and not _text(ref.getPath())
	except Exception:
		return False


def _partePusa(cheie, ref):
	"""Ce se tine minte despre partea audio pe serviciul `ref` (cheie = cheia canalului sau None)."""
	if cheie and _eViu(ref):
		return memoriePartilor().parte(cheie)
	return _PARTI_FARA_CHEIE.get(_cheieSesiune(ref))


def _selecteazaParte(service, n):
	canal = service and service.audioChannel()
	if not canal:
		return False
	canal.selectChannel(n)
	return True


def _puneCanalAudio(service, ref, dorit, cheie=None):
	if dorit is None:
		return
	acum = canal_audio(service)
	if acum is None:
		return
	k = _cheieSesiune(ref)
	cheieFisier = cheie if (cheie and _eViu(ref)) else None
	pus = _partePusa(cheie, ref)
	dePus, tinut = decideParte(dorit, acum, pus, cheieFisier is not None and k in _CANAL_PUS)
	if dePus is not None and _selecteazaParte(service, dePus):
		print("[HdsPisteLimbi] sunet: partea audio %s" % _NUME_PARTE.get(dePus, dePus))
	if tinut in (CANAL_STANGA, CANAL_DREAPTA):
		if dePus is not None:
			_CANAL_PUS[k] = tinut
	else:
		_CANAL_PUS.pop(k, None)
	if tinut != pus:
		if tinut == PARTE_DE_MANA:
			print("[HdsPisteLimbi] sunet: partea audio schimbata de om, nu o mai ating pe canalul acesta")
		if cheieFisier:
			memoriePartilor().pune(cheieFisier, tinut)
		elif tinut is None:
			_PARTI_FARA_CHEIE.pop(k, None)
		else:
			_PARTI_FARA_CHEIE[k] = tinut


def _tineParteDeMana(cheie, ref):
	k = _cheieSesiune(ref)
	_CANAL_PUS.pop(k, None)
	if cheie and _eViu(ref):
		return memoriePartilor().pune(cheie, PARTE_DE_MANA)
	_PARTI_FARA_CHEIE[k] = PARTE_DE_MANA
	return True


def aplicaSubtitrare(infobar, semn=None):
	"""Chemat la evUpdatedInfo din InfoBarSubtitleSupport: porneste sau opreste subtitrarea dupa memorie,
	„niciodata" si preferinte. Intoarce semnul listei (referinta + subtitrarile); cat timp nu se schimba,
	nu se mai face nimic (deci nu se lupta cu ce porneste omul din meniu)."""
	_urmaresteTraducerea()
	session = infobar.session
	service = session.nav.getCurrentService()
	lista = subtitrari(service)
	ref = session.nav.getCurrentlyPlayingServiceReference()
	semnNou = (_refText(ref), tuple(tuple(s["tuplu"][:4]) for s in lista))
	if semnNou == semn:
		return semn
	# Subtitrarile nu apareau pe imagine, nici automat, nici alese de mana (pe 0.1.1 mergeau):
	# pe acelasi canal lista creste cat nucleul descopera paginile de teletext, deci semnul se schimba si alegerea se
	# reaplica: subtitrarea pornita (si cea aleasa de om) era oprita si pornita din nou la fiecare crestere si nu mai
	# apuca sa se deseneze, iar pe un canal fara subtitrare in limba receptorului era oprita de tot. Acum alegerea se
	# face o data pe canal (prima lista nevida); dupa aceea, pe acelasi canal, modulul NU mai opreste si NU mai
	# schimba o subtitrare pornita; poate doar porni una, daca nu merge nimic si preferintele o cer.
	# La un film din fisier (MKV, MP4, AVI) alegerea asteapta lista subtitrarilor de langa film (cautate pe un fir de
	# Components/HdsSubtitrariFilm.py, cel mult cateva secunde): altfel o pista din film pornita inainte n-ar mai fi
	# inlocuita de fisierul in aceeasi limba. Semnul ramane cel vechi, deci evenimentul urmator reia alegerea.
	film = _filmSubtitrari(ref)
	if film is not None and not film.pregatit(session):
		return semn
	if film is None:
		# o subtitrare de pe internet tinuta minte pentru acest canal (aceeasi emisiune) sau aceasta inregistrare revine
		# singura, o data pe serviciu (Components/HdsSubtitrariInternet/tv.py, reia)
		_reiaSubtitrareaDeInternet(session)
	if film is None and infobar.subtitles_enabled and esteFisierPeCanal(infobar.selected_subtitle):
		# o subtitrare de pe internet pornita pe un canal sau pe o inregistrare (Components/HdsSubtitrariInternet/tv.py):
		# alegerea automata n-o opreste si n-o schimba cand lista canalului se schimba
		return semnNou
	acelasiCanal = semn is not None and semn[0] == semnNou[0] and bool(semn[1])
	cheie = cheieCanal(ref)
	if acelasiCanal and infobar.subtitles_enabled:
		# cu traducerea: o subtitrare DVB pusa automat (citita cu OCR) se schimba o data pe teletext sau pe limba
		# traducerii, cand acestea apar mai tarziu in lista; orice alta subtitrare pornita ramane
		ultima = _ULTIMA["subtitrare"]
		if film is not None or not ultima or ultima.get("motiv") != MOTIV_TRADUCERE_DVB or ultima.get("cheie") != cheie \
				or not aceeasiSubtitrare(infobar.selected_subtitle, ultima.get("tuplu")):
			return semnNou
		try:
			ales, motiv = alegeAcum(lista, memorie().alegere(cheie).get("s") if cheie else None)
		except Exception as e:
			print("[HdsPisteLimbi] subtitrarea tradusa: %s" % e)
			return semnNou
		if ales is None or motiv not in (MOTIV_TRADUCERE_TINTA, MOTIV_TRADUCERE_TEXT):
			return semnNou
		_pune(infobar, ales["tuplu"])
		print("[HdsPisteLimbi] subtitrare: %s %s, %s (in locul celei DVB)" % (ales["text"] or "-", ales["fel"], motiv))
		_ULTIMA["subtitrare"] = {"cheie": cheie, "tuplu": ales["tuplu"], "motiv": motiv}
		return semnNou
	ales = None
	if film is not None:
		# filmul are memoria lui (pe fisierul filmului, nu pe canal), fisierul de langa film trece inaintea pistei din
		# film la aceeasi limba, iar o subtitrare „forced” se alege dupa limba sunetului
		try:
			ales, motiv = film.alege(lista, preferinteSubtitrare(), limbaReceptor(), faraSubtitrariNiciodata(), session)
		except Exception as e:
			print("[HdsPisteLimbi] subtitrarea filmului: %s" % e)
			film = None
	if film is None:
		memorat = memorie().alegere(cheie).get("s") if cheie else None
		ales, motiv = alegeAcum(lista, memorat)
	dorita = ales["tuplu"] if ales else None
	if acelasiCanal and dorita is None:
		return semnNou
	_pune(infobar, dorita)
	if ales is not None:
		print("[HdsPisteLimbi] subtitrare: %s %s, %s" % (ales["text"] or "-", ales["fel"], motiv))
	elif motiv == "memorat-oprit":
		print("[HdsPisteLimbi] subtitrare: niciuna, %s" % motiv)
	_ULTIMA["subtitrare"] = {"cheie": cheie, "tuplu": dorita, "motiv": motiv}
	return semnNou


_URMARIT_TRADUCERE = [False]


def _urmaresteTraducerea():
	"""Traducerea pornita sau oprita, ori limba ei schimbata (televizor, web): subtitrarea canalului care merge se
	alege din nou pe loc (ca reaplicaAcum). Notificarile se pun o singura data."""
	if _URMARIT_TRADUCERE[0]:
		return
	_URMARIT_TRADUCERE[0] = True
	try:
		from Components import HdsTraducereSubtitrari as T
		s = T.initConfig()
		for element in (s.pornit, s.limba):
			element.addNotifier(_traducereSchimbata, initial_call=False)
	except Exception as e:
		print("[HdsPisteLimbi] setarile traducerii nu se pot urmari: %s" % e)


def _traducereSchimbata(element=None):
	infobar = infobarActiv()
	if infobar is not None and hasattr(infobar, "subtitle_window"):
		try:
			aplicaSubtitrare(infobar, None)
		except Exception as e:
			print("[HdsPisteLimbi] subtitrarea nu s-a putut alege dupa schimbarea traducerii: %s" % e)


def _filmSubtitrari(ref):
	"""Modulul Components.HdsSubtitrariFilm cand `ref` e un film redat din fisier (MKV, MP4, AVI, ...), altfel None
	(canal, inregistrare .ts, flux, sau modulul lipseste). Un film dintr-un loc din retea redat prin adresa
	(Components/HdsStocareRetea) e film, cu subtitrarile descarcate langa calea lui virtuala."""
	try:
		cale = _text(ref.getPath()) if ref is not None else u""
	except Exception:
		return None
	if not cale.startswith("/") and not cale.startswith("http"):
		return None
	try:
		from Components import HdsSubtitrariFilm
	except ImportError:
		return None
	except Exception as e:
		print("[HdsPisteLimbi] Components/HdsSubtitrariFilm.py nu se poate incarca: %s" % e)
		return None
	try:
		return HdsSubtitrariFilm if HdsSubtitrariFilm.esteFilm(cale) else None
	except Exception:
		return None


def _pune(infobar, dorita):
	"""Porneste subtitrarea dorita (tuplu) sau opreste orice subtitrare (None), prin proprietatile
	din InfoBarSubtitleSupport."""
	pornita = infobar.subtitles_enabled
	if dorita is None:
		if pornita:
			infobar.subtitles_enabled = False
		return
	if pornita and aceeasiSubtitrare(infobar.selected_subtitle, dorita):
		return
	if pornita:
		infobar.subtitles_enabled = False
	infobar.selected_subtitle = dorita
	infobar.subtitles_enabled = True


def infobarActiv(session=None):
	"""Ecranul InfoBar care primeste acum evenimentele serviciului (InfoBar, playerul de inregistrari,
	MediaPlayer), cel care are fereastra subtitrarilor."""
	try:
		from Components.ServiceEventTracker import ServiceEventTracker
		for ecran in reversed(ServiceEventTracker.InfoBarStack[:ServiceEventTracker.InfoBarStackSize]):
			if hasattr(ecran, "subtitle_window"):
				return ecran
	except Exception:
		pass
	try:
		from Screens.InfoBar import InfoBar
		return InfoBar.instance
	except Exception:
		return None


def noteazaAudio(session, index):
	"""Omul a ales de mana pista audio `index` pe serviciul care merge: se tine minte pe canal."""
	service = session.nav.getCurrentService()
	piste, curenta = pisteAudio(service)
	if not (0 <= index < len(piste)):
		return False
	ref = session.nav.getCurrentlyPlayingServiceReference()
	cheie = cheieCanal(ref)
	_ULTIMA["audio"] = {"cheie": cheie, "index": index, "motiv": "memorat"}
	_parteDupaPistaDeMana(service, ref, cheie, piste[index])
	if not cheie:
		return False
	return memorie().noteazaAudio(cheie, amprentaAudio(piste[index]))


def _parteDupaPistaDeMana(service, ref, cheie, pista):
	"""O pista obisnuita aleasa de om: partea pusa de alegerea automata la dual mono se scoate pe loc (una pusa
	de om ramane). La o pista dual mono aleasa de om partea nu se atinge: o alege omul."""
	if pista is None or _partiDualMono(pista.get("text")) is not None:
		return
	try:
		_puneCanalAudio(service, ref, CANAL_STEREO, cheie)
	except Exception as e:
		print("[HdsPisteLimbi] partea audio nu s-a putut pune: %s" % e)


def _subtitrariInternetTv():
	"""Modulul subtitrarilor de pe internet pe canal (Components/HdsSubtitrariInternet/tv.py), numai daca e deja
	incarcat: fara el nu e nimic tinut minte, deci nu se incarca degeaba la fiecare canal."""
	import sys
	return sys.modules.get("Components.HdsSubtitrariInternet.tv")


def _reiaSubtitrareaDeInternet(session):
	tv = _subtitrariInternetTv()
	if tv is None:
		return
	try:
		tv.reia(session)
	except Exception as e:
		print("[HdsPisteLimbi] subtitrarea de pe internet nu a revenit: %s" % e)


def esteFisierPeCanal(tuplu):
	"""Un fisier de subtitrare pus pe un serviciu DVB (canal sau inregistrare .ts) de Components/HdsSubtitrariInternet/
	tv.py: (2, 100 + i, ...). La un film din fisier aceleasi numere sunt fisierele de langa film (cine intreaba stie
	ca nu e un film)."""
	try:
		return bool(tuplu) and len(tuplu) > 1 and int(tuplu[0]) == 2 and int(tuplu[1]) >= 100
	except (TypeError, ValueError):
		return False


def noteazaSubtitrare(session, tuplu):
	"""Omul a pornit de mana subtitrarea `tuplu` (sau a oprit-o: None) pe serviciul care merge."""
	ref = session.nav.getCurrentlyPlayingServiceReference()
	cheie = cheieCanal(ref)
	if cheie and esteFisierPeCanal(tuplu) and _filmSubtitrari(ref) is None:
		# subtitrarea de pe internet a unui film de pe canal nu e alegerea canalului: la urmatorul film de pe el nu
		# exista (lista canalului nu o mai are), deci nu se tine minte
		_ULTIMA["subtitrare"] = {"cheie": cheie, "tuplu": tuple(tuplu), "motiv": "internet"}
		return False
	if ref is not None and not esteFisierPeCanal(tuplu) and _filmSubtitrari(ref) is None:
		# alta subtitrare (sau niciuna) aleasa de mana pe canal sau pe inregistrare: cea de pe internet nu mai revine la
		# intoarcere
		tv = _subtitrariInternetTv()
		if tv is not None:
			tv.uitaRef(ref)
	if tuplu:
		s = None
		for x in subtitrari(session.nav.getCurrentService()):
			if aceeasiSubtitrare(x["tuplu"], tuplu):
				s = x
				break
		if s is None:
			s = subtitrareDinTuplu(tuplu)
		amprenta = amprentaSubtitrare(s)
		_ULTIMA["subtitrare"] = {"cheie": cheie, "tuplu": tuple(tuplu), "motiv": "memorat"}
	else:
		amprenta = OPRIT
		_ULTIMA["subtitrare"] = {"cheie": cheie, "tuplu": None, "motiv": "memorat-oprit"}
	if not cheie:
		# un film din fisier nu are canal: alegerea se tine minte pe film (Components/HdsSubtitrariFilm.py)
		film = _filmSubtitrari(ref)
		if film is not None:
			try:
				return film.noteazaAlegere(session, tuple(tuplu) if tuplu else None)
			except Exception as e:
				print("[HdsPisteLimbi] alegerea la film nu s-a tinut minte: %s" % e)
				return False
	if not cheie or amprenta is None:
		return False
	return memorie().noteazaSubtitrare(cheie, amprenta)


def noteazaParteDeMana(session):
	"""Omul a schimbat partea audio (stanga, stereo, dreapta) pe serviciul care merge, din ecranul sunetului: pe
	canalul acesta alegerea automata nu o mai atinge, pana la „Uită”."""
	ref = session.nav.getCurrentlyPlayingServiceReference()
	return _tineParteDeMana(cheieCanal(ref), ref)


def alegeAudioDeMana(session, index):
	"""Pentru alte ecrane (pagina cu PID-uri): porneste pista `index` si o tine minte pe canal."""
	service = session.nav.getCurrentService()
	audio = service and service.audioTracks()
	if not audio:
		return False
	try:
		n = int(audio.getNumberOfTracks() or 0)
		curenta = int(audio.getCurrentTrack())
	except Exception:
		return False
	if not (0 <= index < n):
		return False
	if index != curenta:
		audio.selectTrack(index)
	noteazaAudio(session, index)
	return True


def alegeSubtitrareDeMana(session, tuplu, infobar=None):
	"""Pentru alte ecrane: porneste subtitrarea `tuplu` (din getSubtitleList) sau le opreste pe toate
	(None) si tine minte alegerea pe canal."""
	infobar = infobar or infobarActiv(session)
	if infobar is None or not hasattr(infobar, "subtitle_window"):
		return False
	_pune(infobar, tuple(tuplu) if tuplu else None)
	noteazaSubtitrare(session, tuplu)
	return True


def stareCanal(session):
	"""Pentru ecrane: ce e tinut minte pe canalul care merge, ultima alegere automata si partea audio („parte”:
	PARTE_DE_MANA daca omul a schimbat-o, partea pusa de alegerea automata, PARTE_UITATA sau None)."""
	ref = session.nav.getCurrentlyPlayingServiceReference()
	cheie = cheieCanal(ref)
	return {"cheie": cheie, "memorat": memorie().alegere(cheie) if cheie else {}, "ultima": ultimaAlegere(),
		"parte": _partePusa(cheie, ref)}


def numarAlegeri():
	"""Cate canale au ceva ales de mana: sunetul, subtitrarea sau partea audio."""
	return len(set(memorie().toate()) | memoriePartilor().deMana())


def uitaAlegeri(session=None, toate=False):
	"""Sterge alegerile de mana: ale canalului care merge (session) sau ale tuturor (toate=True); partea audio
	schimbata de om trece iar la alegerea automata. Intoarce cate canale s-au uitat."""
	if toate:
		alegeri, parti = set(memorie().toate()), memoriePartilor().deMana()
		uitate = set()
		if alegeri and memorie().uita(None):
			uitate |= alegeri
		if parti and memoriePartilor().uitaDeMana(None):
			uitate |= parti
		return len(uitate)
	if session is None:
		return 0
	return uitaCheie(cheieCanal(session.nav.getCurrentlyPlayingServiceReference()))


def uitaCheie(cheie):
	"""Pentru pagina web: uita alegerile de mana ale canalului `cheie` (si partea audio aleasa de mana). -> 0 sau 1"""
	if not cheie:
		return 0
	sterse = memorie().uita(cheie)
	parti = memoriePartilor().uitaDeMana(cheie)
	return 1 if (sterse or parti) else 0


def canaleCuAlegeri():
	"""Pentru pagina web: {cheie: {"a": ..., "s": ... sau OPRIT, "t": secunde, "parte_de_mana": True/False}}, pe
	toate canalele cu ceva ales de mana (sunet, subtitrare sau partea audio)."""
	canale = memorie().toate()
	deMana = memoriePartilor().deMana()
	for cheie in deMana:
		canale.setdefault(cheie, {"t": 0})
	for cheie, intrare in canale.items():
		intrare["parte_de_mana"] = cheie in deMana
	return canale


# ------------------------------------------------------------------ numele cerute de afisajul interactiv
# Afisajul interactiv al skinului (bara a doua, pagina cu PID-uri) cheama modulul cu aceste nume. Ele doar aleg si
# intorc rezultatul; redesenarea o cere afisajul.
# manual=True = alegere facuta de om: se tine minte pe canal pentru totdeauna (si None = fara subtitrare).

def _refServiciu(service):
	"""Referinta canalului pentru serviciul dat: din service.info(); daca lipseste, serviciul care merge."""
	ref = None
	try:
		from enigma import iServiceInformation, eServiceReference
		info = service and service.info()
		text = info and info.getInfoString(iServiceInformation.sServiceref)
		if text:
			ref = eServiceReference(text)
	except Exception:
		ref = None
	if ref is None:
		try:
			import NavigationInstance
			ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
		except Exception:
			ref = None
	return ref


def piste_audio(service):
	"""-> lista de {index, codec, limba, pid, pornita} (plus campurile formei comune: fel, text, limbi, descriere)."""
	piste, curenta = pisteAudio(service)
	for p in piste:
		p["codec"] = p["fel"]
		p["limba"] = numeLimba(p["limbi"][0]) if p["limbi"] else p["text"]
		p["pornita"] = p["index"] == curenta
	return piste


def alege_audio(service, index, manual=True):
	"""Porneste pista audio `index`; manual=True o tine minte pe canal. -> True/False"""
	audio = service and service.audioTracks()
	if not audio:
		return False
	try:
		n = int(audio.getNumberOfTracks() or 0)
		curenta = int(audio.getCurrentTrack())
	except Exception:
		return False
	if not (0 <= index < n):
		return False
	if index != curenta:
		audio.selectTrack(index)
	if manual:
		ref = _refServiciu(service)
		cheie = cheieCanal(ref)
		_ULTIMA["audio"] = {"cheie": cheie, "index": index, "motiv": "memorat"}
		piste = pisteAudio(service)[0]
		if index < len(piste):
			_parteDupaPistaDeMana(service, ref, cheie, piste[index])
			if cheie:
				memorie().noteazaAudio(cheie, amprentaAudio(piste[index]))
	return True


def alege_subtitrare(infobar, tuplu, manual=True):
	"""Porneste subtitrarea `tuplu` sau le opreste pe toate (None); manual=True tine minte pe canal. -> True/False"""
	if infobar is None or not hasattr(infobar, "subtitle_window"):
		return False
	_pune(infobar, tuple(tuplu) if tuplu else None)
	if manual:
		noteazaSubtitrare(infobar.session, tuplu)
	return True


def subtitrare_pornita(infobar):
	"""Tuplul subtitrarii pornite pe ecranul InfoBar, sau None."""
	try:
		if infobar is not None and infobar.subtitles_enabled and infobar.selected_subtitle:
			return tuple(infobar.selected_subtitle)
	except Exception:
		pass
	return None


def canal_audio(service):
	"""Canalul audio: 0 stanga, 1 stereo, 2 dreapta; None daca serviciul nu il are."""
	canal = service and service.audioChannel()
	if not canal:
		return None
	try:
		return int(canal.getCurrentChannel())
	except Exception:
		return None


def alege_canal_audio(service, n, manual=True):
	"""Pune canalul audio (0 stanga, 1 stereo, 2 dreapta); manual=True: alegere facuta de om, alegerea automata nu
	o mai atinge pe canalul acesta, pana la „Uită”. -> True/False"""
	if isinstance(n, bool) or n not in (0, 1, 2) or not _selecteazaParte(service, n):
		return False
	if manual:
		ref = _refServiciu(service)
		_tineParteDeMana(cheieCanal(ref), ref)
	return True


def reaplicaAcum(session):
	"""Dupa o schimbare in setari: aplica pe loc memoria si preferintele pe canalul care merge."""
	try:
		aplicaAudio(session, None)
	except Exception as e:
		print("[HdsPisteLimbi] sunetul nu s-a putut alege acum: %s" % e)
	infobar = infobarActiv(session)
	if infobar is not None and hasattr(infobar, "subtitle_window"):
		try:
			aplicaSubtitrare(infobar, None)
		except Exception as e:
			print("[HdsPisteLimbi] subtitrarea nu s-a putut alege acum: %s" % e)
