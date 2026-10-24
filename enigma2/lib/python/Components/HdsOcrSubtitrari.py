# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsOcrSubtitrari - legatura enigma2 cu serviciul hds-ocr: textul citit din pozele subtitrarilor DVB.
#
# Subtitrarile DVB sunt poze cu paleta (720x576 sau marimea din DDS). Cand „Mărirea subtitrărilor DVB" = OCR
# (config.subtitles.hds_marire_dvb), literele sunt recunoscute si desenate cu fontul si stilul din „Aspectul
# subtitrărilor" (Components/HdsSubtitrariAspect.py); cand recunoasterea e nesigura sau intarzie, ramane poza.
#
# CINE FACE CE
#   - hds-ocr (/usr/bin/hds-ocr, reteta hds-ocr din stratul meta-local): proces separat,
#     legat de libtesseract (Apache-2.0, care nu se poate lega de enigma2, GPL-2.0-only). Primeste pe socketul unix
#     /tmp/hds-ocr.sock o regiune de subtitrare (indici de 8 biti + paleta), intoarce randurile: text, dreptunghi,
#     linia de baza, culorile, increderea pe cuvant. Modelele: /usr/share/hds-ocr/tessdata (reteta hds-ocr-modele, numai
#     limbile cu cele mai multe subtitrari DVB) si modelele descarcate la cerere (Components/HdsOcrModele.py: memoria
#     interna, sau stick ori disc prin legaturile din /tmp/hds-ocr-modele), date serviciului cu --tessdata-extra.
#   - fisierul acesta: clientul (protocolul din hds_ocr_protocol.h, scris aici din nou), pornirea serviciului la cerere,
#     modelul dupa limba pistei, decizia „text sau poza", memoria paginilor, contorul si pauza dupa caderi.
#   - nucleul (lib/gui/esubtitle.cpp, eSubtitleWidget): da paginile DVB functiei puse cu setOcrHandler, o data cand
#     pagina soseste (inainte de momentul afisarii, daca serviciul DVB o anunta cu prefetchPage) sau la afisare, si
#     deseneaza randurile primite cu setOcrText ca teletextul, sau poza (showOcrBitmap).
#   - legaturile: Screens/SubtitleDisplay.py cheama legaNucleul() (functia pusa sau scoasa dupa setare si la fiecare
#     schimbare a ei); Screens/InfoBarGenerics.py cheama pistaAleasa/pistaOprita cand porneste sau se opreste o
#     subtitrare si urmaresteOprirea() (serviciul oprit la standby si la iesirea din enigma2).
#   - traducerea subtitrarilor (Components/HdsTraducereSubtitrari.py): cand e pornita si pentru subtitrarile DVB,
#     esteOcrPornit() e adevarat si fara „Mărirea subtitrărilor DVB” = OCR; textul unei pagini, de cum e citit, merge
#     la traducere (inainte()), iar limba pistei alese ii spune din ce limba se traduce.
#
# NU BLOCHEAZA FIRUL INTERFETEI: socketul e neblocant si e citit/scris din bucla enigma2 (eSocketNotifier; daca nu
# exista, un ceas de 20 ms), iar serviciul porneste cu Popen (se intoarce imediat) si e cules cu un ceas. Rezultatul
# unei pagini vine prin functia data (laRezultat), tot pe firul enigma2. Singurul lucru facut pe loc e amprenta paginii
# (blake2b peste pixeli, in C) si cautarea ei in memorie.
#
# TIMPUL
#   - Cererea pleaca atunci cand nucleul da pagina: la sosire (intarziere_ms = cat mai e pana la afisare) sau la
#     afisare (intarziere_ms < 0). Termenul trimis serviciului = cat timp mai foloseste raspunsul: pana la afisare plus
#     DURATA_UTILA_MS (textul poate inlocui poza cat timp pagina e pe ecran). Serviciul socoteste singur, dupa numarul
#     si latimea randurilor si viteza masurata pe receptor, cat are voie sa lucreze la pagina (hds-ocr.cpp), iar
#     timpul petrecut in coada nu intra in el.
#   - Clientul mai asteapta MARJA_MS peste termen; apoi pagina ramane poza, cu motivul „termen".
#   - Nu se foloseste FLAG_SUPERSEDE: paginile trimise din timp sunt afisate in ordinea sosirii, deci o pagina noua
#     nu face inutila una mai veche; o pagina ramasa fara folos se opreste singura la termen.
#
# REGIUNILE TAIATE: unele posturi impart pagina in fasii (ZDFinfo HD: DDS 1280x720, patru regiuni de 1280x28 una sub
# alta, iar un rand de litere are ~56 px), deci literele unui rand sunt in doua regiuni. Trimise separat, serviciul ar
# citi jumatati de litere (masurat pe receptor: 0 pagini text din 62, cuvinte ca „Rıınkar” sau „TTTT”). De aceea
# regiunile care se ating sau se suprapun (pe verticala cel mult UNIRE_GOL_PX intre ele, pe orizontala macar un pixel
# comun) se lipesc intr-o singura cerere (unesteRegiunile), cu golurile pe o intrare transparenta; cu palete diferite,
# paleta cererii e reuniunea lor (cel mult 256 de culori, altfel regiunile raman separate).
#
# MEMORIA: pagina e cunoscuta dupa amprenta (pozitia, marimea, paleta si pixelii fiecarei regiuni, plus modelul). O
# pagina deja hotarata (text sau poza din cauza increderii / a lipsei de text; si o pagina aflata in lucru la doua
# caderi ale serviciului) se rezolva pe loc, fara serviciu: DVB retrimite des aceeasi pagina. O pagina identica cu una
# aflata inca la serviciu nu se trimite a doua oara, ci asteapta acelasi raspuns. Serviciul are si el memoria paginilor
# si a randurilor: o pagina sau un rand deja citit primeste raspunsul pe loc, fara coada.
#
# REVENIREA LA POZA (laRezultat primeste None si motivul; contorul tine si felul): serviciul sau modelul lipsesc,
# conexiunea cade, raspunsul nu vine la timp, starea nu e OK, modelul folosit nu e cel cerut, un rand gol sau taiat de
# timp, un cuvant cu litere sub PRAG_INCREDERE (70, masurat pe paginile de proba)
# sau un semn fara litere sub PRAG_SEMNE.
#
# CADERILE: dupa CADERI_MAXIME caderi ale serviciului in CADERI_FEREASTRA_S secunde, OCR face o pauza (PAUZA_S, apoi
# dublu la fiecare pauza noua, cel mult PAUZA_MAXIMA_S); dupa pauza incearca din nou singur. O pista aleasa din nou sau
# contorul pus la zero opresc pauza pe loc; o pagina citita ca text sterge sirul pauzelor.
#
# LIMBA: modelul se alege din limba pistei (codurile ISO 639-2 B si T, 639-1, si numele din EIT prin
# HdsPisteLimbi.limbaCanonica). O limba fara model pe receptor = poza (si, o singura data, intrebarea daca se descarca
# modelul: HdsOcrModele.propune). Un model descarcat intre timp se foloseste de la pagina urmatoare
# (HdsOcrModele.generatie), fara repornirea serviciului.
# PISTA FARA LIMBA ("und", "qaa", gol): limba se ghiceste dupa
# canal (Components/HdsOcrLimbaGhicita.py: ghidul TV, limba sunetului, celelalte canale de pe transponder) si se
# citeste cu modelul ei, intocmai ca o limba declarata (in imagine, descarcat, sau intrebarea de descarcare). Pe
# televizor vine o data un mesaj scurt ca limba e ghicita (avertizeazaGhicirea), iar contorul (televizor si web) o
# spune si el. Fara nicio sursa: poza (IMPLICIT_FARA_LIMBA = None), nu romana ca inainte: un model gresit scrie
# diacriticele gresit si greseste ~5,6 % din litere (masurat pe pagini reale).
#
# API (pentru nucleu, ecrane si pagina web):
#   o = instanta()
#   o.activ()                         OCR ales in setari, serviciul si cel putin un model instalate, fara pauza
#   o.pistaAleasa(pista)              tuplul din getSubtitleList() sau textul limbii; porneste serviciul si incarca
#                                     modelul dinainte (o pagina mica de incalzire). Intoarce modelul sau None
#   o.pistaOprita()                   subtitrarea DVB s-a oprit (serviciul iese singur dupa IDLE_EXIT_S)
#   o.cerePagina(gen, regiuni, laRezultat, limba=None, intarziere_ms=-1)
#                                     False = fara OCR, poza se arata acum. True = laRezultat(gen, linii, motiv) vine
#                                     o singura data, poate chiar in timpul apelului (pagina din memorie): linii = lista
#                                     de randuri (dict, coordonatele paginii) sau None (poza). regiuni: dict cu x, y,
#                                     latime, inaltime, pixeli (bytes, cate un indice pe pixel), pas (optional, octeti
#                                     pe rand), paleta (ARGB, A = opacitate) sau paleta_enigma (r, g, b, transparenta)
#   o.stare()                         dict pentru pagina web / jurnal (cu contorul)
#   o.opreste()                       inchide conexiunea si opreste serviciul (standby, iesire)
#   pentruNucleu(widget)              functia de dat nucleului (eSubtitleWidget)
#   esteOcrPornit(), cerutDeTraducere(), legaNucleul(), pistaAleasa(pista), pistaOprita(), urmaresteOprirea(), opreste()
#   contor(), puneContorulLaZero(), textContorScurt(), textContorDetalii()
#                                     contorul pentru „Aspectul subtitrărilor" si pagina web /subtitrari
#   textGhicire(s)                    fraza despre limba unei piste DVB fara limba (ghicita sau nu), si in
#                                     textContorDetalii; stare() are fara_limba, limba_ghicita, sursa_ghicire

from __future__ import absolute_import

import errno
import hashlib
import json
import os
import signal
import socket
import struct
import subprocess
import time
from collections import OrderedDict, deque

# ------------------------------------------------------------------ protocolul (hds_ocr_protocol.h, versiunea 1)

MAGIC = b"HOCR"
VERSIUNE_PROTOCOL = 1
ANTET = 12
MAX_CORP = 8 * 1024 * 1024
MAX_DIM = 4096
MAX_PIXELI = 4 * 1024 * 1024
RECOGNIZE_FIX = 28
RESULT_FIX = 28
LINIE_FIX = 36
CUVANT_FIX = 12

MSG_RECOGNIZE = 1
MSG_PING = 2
MSG_RESULT = 0x81
MSG_PONG = 0x82

FLAG_SUPERSEDE = 1
FLAG_NO_CACHE = 2
FLAG_KEEP_CEDILLA = 4
FLAG_NO_WORDS = 8

ST_OK, ST_TIMEOUT, ST_CANCELLED, ST_BAD_REQUEST, ST_NO_MODEL, ST_BUSY, ST_ERROR = range(7)
NUME_STARE = {ST_OK: "OK", ST_TIMEOUT: "TIMEOUT", ST_CANCELLED: "CANCELLED", ST_BAD_REQUEST: "BAD_REQUEST",
	ST_NO_MODEL: "NO_MODEL", ST_BUSY: "BUSY", ST_ERROR: "ERROR"}

LF_CACHED, LF_TIMEOUT, LF_LOW_CONF, LF_INVERTED = 1, 2, 4, 8

# ------------------------------------------------------------------ locuri si reglaje

BINAR = "/usr/bin/hds-ocr"
SOCKET = "/tmp/hds-ocr.sock"
TESSDATA = "/usr/share/hds-ocr/tessdata"
IDLE_EXIT_S = 300          # serviciul iese singur dupa atatea secunde fara cereri (tine ~40-60 MB cu un model)
NICE = 10
DURATA_UTILA_MS = 5000     # dupa afisare, cat timp textul mai poate inlocui poza (o subtitrare sta de obicei 1-6 s)
TIMP_CERERE_MS = DURATA_UTILA_MS   # termenul unei pagini trimise la afisare
TERMEN_MAXIM_MS = 10000    # limita protocolului (timeout_ms)
MARJA_MS = 1000            # peste termen: daca raspunsul tot nu vine, pagina ramane poza
TIMP_PORNIRE_MS = 3000     # cat se asteapta socketul dupa pornirea serviciului
PAS_CONECTARE_MS = 50
PRAG_INCREDERE = 70        # cuvintele cu litere sau cifre
PRAG_SEMNE = 40            # cuvintele fara litere si cifre (liniuta de dialog, paranteze, puncte de suspensie)
ALFA_TRANSPARENT = 48      # ca in hds-ocr.cpp: sub atata opacitate intrarea din paleta e fundal
CADERI_MAXIME = 3
CADERI_FEREASTRA_S = 120
PAUZA_S = 30
PAUZA_MAXIMA_S = 600
MAX_IN_ZBOR = 4            # pagini trimise si nerezolvate (serviciul are coada de 8 cereri)
MEMORIE_PAGINI = 64        # pagini hotarate tinute minte (amprenta -> text sau poza)
ULTIMELE = 20              # paginile aratate in pagina web
UNIRE_GOL_PX = 2           # regiuni una sub alta cu cel mult atatia pixeli intre ele se lipesc (vezi REGIUNILE TAIATE)

# felurile revenirii la poza (contorul); textul lor e in _TEXT_MOTIV
M_TERMEN, M_INCREDERE, M_MODEL, M_SERVICIU, M_OCUPAT, M_FARA_TEXT, M_ALTELE = (
	"termen", "incredere", "model", "serviciu", "ocupat", "fara_text", "altele")
FELURI_MOTIV = (M_TERMEN, M_INCREDERE, M_MODEL, M_SERVICIU, M_OCUPAT, M_FARA_TEXT, M_ALTELE)
# se tin minte numai hotararile care nu depind de clipa (o pagina nesigura ramane nesigura; un termen nu). Lipsa
# modelului nu: un pachet de model instalat intre timp o schimba.
_MOTIVE_STABILE = frozenset((M_INCREDERE, M_FARA_TEXT))
# o pagina in lucru la doua caderi ale serviciului se tine minte ca poza (sa nu-l doboare din nou cand DVB o
# retrimite); o singura cadere poate fi iesirea obisnuita (--idle-exit) sau o oprire, deci nu ajunge
CADERI_ACEEASI_PAGINA = 2
MAX_PAGINI_CAZUTE = 16


def _jurnal(text):
	print("[HdsOcrSubtitrari] %s" % text)


def N_(text):
	"""marcaj pentru xgettext (--keyword=N_), fara efect; textul se traduce la folosire cu _()"""
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


class EroareProtocol(ValueError):
	pass


def argbDinEnigma(r, g, b, transparenta):
	"""culoare gRGB din enigma2 (a = TRANSPARENTA) -> ARGB cu A = OPACITATE (argb_from_enigma2 din protocol)"""
	return ((255 - (int(transparenta) & 255)) << 24) | ((int(r) & 255) << 16) | ((int(g) & 255) << 8) | (int(b) & 255)


def culoareEnigma(argb):
	"""ARGB (A = opacitate) -> (r, g, b, transparenta) pentru gRGB"""
	return ((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, 255 - ((argb >> 24) & 255))


def antet(tip, lungime):
	return MAGIC + struct.pack("<HHI", VERSIUNE_PROTOCOL, tip, lungime)


def codeazaPing():
	return antet(MSG_PING, 0)


def _cod_limba(limba):
	b = (limba or "").encode("ascii", "replace")[:4]
	return b + b"\0" * (4 - len(b))


def codeazaCerere(request_id, generatie, latime, inaltime, paleta, pixeli, limba="", flags=0, timeout_ms=0, x=0, y=0):
	"""o cerere RECOGNIZE intreaga (antet + corp); ValueError daca nu respecta limitele protocolului"""
	n = len(paleta)
	if not 1 <= n <= 256:
		raise ValueError("paleta trebuie sa aiba 1..256 intrari (are %d)" % n)
	if not (1 <= latime <= MAX_DIM and 1 <= inaltime <= MAX_DIM) or latime * inaltime > MAX_PIXELI:
		raise ValueError("dimensiuni gresite %dx%d" % (latime, inaltime))
	if len(pixeli) != latime * inaltime:
		raise ValueError("pixeli %d != %dx%d" % (len(pixeli), latime, inaltime))
	if not (-32768 <= x <= 32767 and -32768 <= y <= 32767):
		raise ValueError("pozitie gresita %d,%d" % (x, y))
	corp = struct.pack("<IIIH4shhHHH", request_id & 0xFFFFFFFF, generatie & 0xFFFFFFFF, flags & 0xFFFFFFFF,
		max(0, min(TERMEN_MAXIM_MS, int(timeout_ms))), _cod_limba(limba), x, y, latime, inaltime, n)
	corp += struct.pack("<%dI" % n, *[int(c) & 0xFFFFFFFF for c in paleta])
	corp += bytes(pixeli)
	if len(corp) > MAX_CORP:
		raise ValueError("cerere prea mare")
	return antet(MSG_RECOGNIZE, len(corp)) + corp


def decodeazaRezultat(corp):
	"""corpul unui RESULT -> dict (ca decode_result din protocol); EroareProtocol daca e stricat"""
	if len(corp) < RESULT_FIX:
		raise EroareProtocol("rezultat prea scurt")
	rid, gen, stare, nl, timp, model, loviri, _r = struct.unpack_from("<IIHHI8sHH", corp, 0)
	o = RESULT_FIX
	linii = []
	for _i in range(nl):
		if o + LINIE_FIX > len(corp):
			raise EroareProtocol("rand taiat")
		(x, y, w, h, baza, xh, asc, desc, fill, contur, caseta, cpx, incr, steag, _rez, tl, nw) = \
			struct.unpack_from("<hhHHhHHHIIIBBBBHH", corp, o)
		o += LINIE_FIX
		if o + tl > len(corp):
			raise EroareProtocol("text taiat")
		text = corp[o:o + tl].decode("utf-8", "replace")
		o += tl
		cuvinte = []
		for _k in range(nw):
			if o + CUVANT_FIX > len(corp):
				raise EroareProtocol("cuvant taiat")
			wx, wy, ww, wh, wc, wf, wl = struct.unpack_from("<hhHHBBH", corp, o)
			o += CUVANT_FIX
			if o + wl > len(corp):
				raise EroareProtocol("text de cuvant taiat")
			cuvinte.append({"x": wx, "y": wy, "latime": ww, "inaltime": wh, "incredere": wc,
				"text": corp[o:o + wl].decode("utf-8", "replace")})
			o += wl
		linii.append({"x": x, "y": y, "latime": w, "inaltime": h, "baza": baza, "x_height": xh, "ascender": asc,
			"descender": desc, "fill": fill, "contur": contur, "caseta": caseta, "contur_px": cpx, "incredere": incr,
			"steaguri": steag, "text": text, "cuvinte": cuvinte})
	if o != len(corp):
		raise EroareProtocol("octeti in plus la sfarsit (%d != %d)" % (o, len(corp)))
	return {"request_id": rid, "generatie": gen, "stare": stare, "timp_us": timp,
		"model": model.rstrip(b"\0").decode("ascii", "replace"), "din_memorie": loviri, "linii": linii}


class Cititor(object):
	"""aduna octetii primiti si scoate mesajele intregi (tip, corp); EroareProtocol la un antet stricat"""

	def __init__(self):
		self.buf = b""

	def adauga(self, date):
		self.buf += date
		mesaje = []
		while len(self.buf) >= ANTET:
			if self.buf[:4] != MAGIC:
				raise EroareProtocol("antet gresit")
			ver, tip, ln = struct.unpack_from("<HHI", self.buf, 4)
			if ver != VERSIUNE_PROTOCOL or ln > MAX_CORP:
				raise EroareProtocol("versiune %d / lungime %d" % (ver, ln))
			if len(self.buf) < ANTET + ln:
				break
			mesaje.append((tip, self.buf[ANTET:ANTET + ln]))
			self.buf = self.buf[ANTET + ln:]
		return mesaje


# ------------------------------------------------------------------ limba pistei -> modelul

# ca LANG_MAP din hds-ocr.cpp; numele de limbi (EIT) trec intai prin HdsPisteLimbi.limbaCanonica
LIMBA_MODEL = {
	"rum": "ron", "ron": "ron", "mol": "ron", "ro": "ron",
	"eng": "eng", "en": "eng",
	"ger": "deu", "deu": "deu", "de": "deu",
	"fre": "fra", "fra": "fra", "fr": "fra",
	"ita": "ita", "it": "ita",
	"spa": "spa", "esl": "spa", "es": "spa",
	"hun": "hun", "hu": "hun",
	"pol": "pol", "pl": "pol",
	"cze": "ces", "ces": "ces", "cs": "ces",
	"dut": "nld", "nld": "nld", "nla": "nld", "nl": "nld",
	"por": "por", "pt": "por",
	"rus": "rus", "ru": "rus",
	"tur": "tur", "tr": "tur",
	"slo": "slk", "slk": "slk", "sk": "slk",
	"hrv": "hrv", "scr": "hrv", "hr": "hrv",
	"srp": "srp", "scc": "srp", "sr": "srp",
	"slv": "slv", "sl": "slv",
	"bul": "bul", "bg": "bul",
	"gre": "ell", "ell": "ell", "el": "ell",
	"ukr": "ukr", "uk": "ukr",
	"swe": "swe", "sv": "swe",
	"dan": "dan", "da": "dan",
	"nor": "nor", "nob": "nor", "nno": "nor", "no": "nor",
	"fin": "fin", "fi": "fin",
	"cat": "cat", "ca": "cat",
	"alb": "sqi", "sqi": "sqi", "sq": "sqi",
	"lit": "lit", "lt": "lit",
	"lav": "lav", "lv": "lav",
	"est": "est", "et": "est",
	"mac": "mkd", "mkd": "mkd", "mk": "mkd",
	"bel": "bel", "be": "bel",
	"bos": "bos", "bs": "bos",
	"bre": "bre", "br": "bre",
	"cos": "cos", "co": "cos",
	"wel": "cym", "cym": "cym", "cy": "cym",
	"baq": "eus", "eus": "eus", "eu": "eus",
	"fao": "fao", "fo": "fao",
	"fry": "fry", "fy": "fry",
	"gla": "gla", "gd": "gla",
	"gle": "gle", "ga": "gle",
	"glg": "glg", "gl": "glg",
	"ice": "isl", "isl": "isl", "is": "isl",
	"ltz": "ltz", "lb": "ltz",
	"mlt": "mlt", "mt": "mlt",
	"oci": "oci", "oc": "oci",
	"ara": "ara", "ar": "ara",
	"heb": "heb", "he": "heb", "iw": "heb",
	"per": "fas", "fas": "fas", "fa": "fas",
	"kur": "kmr", "kmr": "kmr", "ku": "kmr",
}
# o limba cu mai multe modele: primul care e pe receptor; pentru propunerea de descarcare, primul din lista. Sarba de
# pe canalele regionale (filme, seriale) e de obicei cu litere latine, iar cea a televiziunii publice cu chirilice.
VARIANTE = {"srp": ("srp_latn", "srp")}
# codul trimis serviciului cand numele modelului nu incape in cele 4 litere ale protocolului (LANG_MAP din hds-ocr.cpp)
COD_PROTOCOL = {"srp_latn": "srpl"}
FARA_LIMBA = frozenset(("", "und", "unk", "mis", "mul", "zxx", "xxx", "---", "nar", "orig", "original", "ov", "vo"))
# modelul pentru o pista fara limba cand limba nu se poate ghici dupa canal: niciunul (poza). Inainte era
# romana; acum limba ghicita (OcrSubtitrari.limba_ghicita) se da ca `implicit` functiilor de mai jos.
IMPLICIT_FARA_LIMBA = None


def esteFaraLimba(limba):
	"""Pista nu are limba declarata: gol, "und", "mul", "qaa".."qtz" (codurile locale) si celelalte din FARA_LIMBA"""
	if isinstance(limba, bytes):
		limba = limba.decode("utf-8", "replace")
	t = (limba or u"").strip().lower()
	for sep in ("/", ",", ";", "+", "&", "|"):
		t = t.split(sep)[0].strip()
	return not t or t in FARA_LIMBA or (len(t) == 3 and t[0] == "q" and "a" <= t[1] <= "t")


# pistele versiunii originale: subtitrarea e de obicei in limba originala a filmului, nu in a dublajului, deci limba
# sunetului sau a celorlalte canale ar da limba gresita; se crede numai ghidul TV care spune limba subtitrarii
VERSIUNE_ORIGINALA = frozenset(("orig", "original", "ov", "vo", "qaa"))


def esteVersiuneOriginala(limba):
	if isinstance(limba, bytes):
		limba = limba.decode("utf-8", "replace")
	t = (limba or u"").strip().lower()
	for sep in ("/", ",", ";", "+", "&", "|"):
		t = t.split(sep)[0].strip()
	return t in VERSIUNE_ORIGINALA


def modeleDisponibile(dosar=TESSDATA):
	"""modelele din dosar (numele fisierelor .traineddata fara extensie)"""
	try:
		return frozenset(f[:-len(".traineddata")] for f in os.listdir(dosar)
			if f.endswith(".traineddata") and not f.startswith("."))
	except OSError:
		return frozenset()


def codProtocol(model):
	"""codul de 4 litere trimis serviciului pentru model (numele modelului, sau COD_PROTOCOL)"""
	return COD_PROTOCOL.get(model, model or "")


def _canonic(limba):
	try:
		from Components.HdsPisteLimbi import limbaCanonica
		return limbaCanonica(limba)
	except Exception:
		return None


def _modeleLimbii(limba, implicit=IMPLICIT_FARA_LIMBA):
	"""textul limbii pistei -> modelele potrivite, in ordinea preferintei (de obicei unul); () = limba necunoscuta"""
	if isinstance(limba, bytes):
		limba = limba.decode("utf-8", "replace")
	t = (limba or u"").strip().lower()
	for sep in ("/", ",", ";", "+", "&", "|"):
		t = t.split(sep)[0].strip()             # „deu/eng" (dual) -> prima
	cod = None
	if t in LIMBA_MODEL:
		cod = LIMBA_MODEL[t]
	elif t and t not in FARA_LIMBA and not (len(t) == 3 and t[0] == "q" and "a" <= t[1] <= "t"):
		canonic = _canonic(limba)
		if canonic:
			cod = LIMBA_MODEL.get(canonic, canonic)
	if cod is None and (t in FARA_LIMBA or (len(t) == 3 and t[0] == "q" and "a" <= t[1] <= "t") or not t):
		cod = LIMBA_MODEL.get(implicit, implicit)
	if not cod:
		return ()
	return VARIANTE.get(cod, (cod,))


def modelPentruLimba(limba, disponibile, implicit=IMPLICIT_FARA_LIMBA):
	"""textul limbii pistei -> modelul tessdata de folosit, sau None (fara OCR: poza).
	O limba cunoscuta fara model pe receptor -> None (nu se incearca alt model: textul ar iesi fara sens)."""
	for m in _modeleLimbii(limba, implicit):
		if m in disponibile:
			return m
	return None


def modelNecesar(limba, implicit=IMPLICIT_FARA_LIMBA):
	"""modelul care ar trebui descarcat pentru limba pistei (primul din VARIANTE), sau None daca limba nu se stie"""
	m = _modeleLimbii(limba, implicit)
	return m[0] if m else None


# Pistele playerului de filme (lib/service/servicemp3.cpp, getSubtitleList): (2, index, tip, 0, limba[, ...]), tipul dupa
# subtype_t din lib/service/servicemp3.h. Cele desenate ca poza (stVOB = 5: DVD VobSub; stPGS = 6: Blu-ray PGS; din film
# sau dintr-un fisier .idx/.sup de langa el) ajung la widget ca pagini DVB (paginaDvb), deci se citesc la fel, cu limba
# pistei; cele text sunt deja text.
FEL_FILM = 2
TIPURI_POZA_FILM = (5, 6)


def estePozaFilm(pista):
	"""tuplul unei piste de film desenate ca poza (VobSub, PGS), care se poate citi ca text"""
	if not isinstance(pista, (list, tuple)) or len(pista) < 3:
		return False
	try:
		return int(pista[0]) == FEL_FILM and int(pista[2]) in TIPURI_POZA_FILM
	except (TypeError, ValueError):
		return False


def limbaDinPista(pista):
	"""tuplul din getSubtitleList() (fel, pid, pagina, magazin, limba[, ...]) sau textul limbii -> (fel, limba);
	fel 0 = DVB, 1 = teletext, 2 = pista sau fisierul unui film (estePozaFilm: poza), None = necunoscut (s-a dat
	numai limba)"""
	if isinstance(pista, (list, tuple)):
		fel = None
		try:
			fel = int(pista[0])
		except (TypeError, ValueError, IndexError):
			pass
		return fel, (pista[4] if len(pista) > 4 else u"")
	return None, pista


# ------------------------------------------------------------------ decizia: text sau poza

def randuriPagina(rezultate):
	"""rezultatele regiunilor unei pagini -> randurile, de sus in jos (fara cele goale)"""
	linii = []
	for r in rezultate:
		linii.extend(l for l in r["linii"] if l["text"].strip())
	linii.sort(key=lambda l: (l["y"], l["x"]))
	return linii


def _areLitere(text):
	return any(c.isalnum() for c in text)


def decizie(rezultate, model, prag=PRAG_INCREDERE, prag_semne=PRAG_SEMNE):
	"""(foloseste_textul, fel, motiv). Felul e unul din FELURI_MOTIV (gol cand textul e bun), motivul e pentru jurnal.
	Pragul se aplica pe cuvant: cuvintele cu litere sau cifre la `prag`, semnele singure (liniuta de dialog,
	paranteze, puncte) la `prag_semne`. Steagul LF_LOW_CONF al serviciului (un cuvant sub 50) nu se mai ia ca atare:
	cuvintele lui sunt verificate aici, dupa felul lor."""
	if not rezultate:
		return False, M_TERMEN, "fara raspuns"
	for r in rezultate:
		st = r["stare"]
		if st != ST_OK:
			fel = {ST_TIMEOUT: M_TERMEN, ST_NO_MODEL: M_MODEL, ST_BUSY: M_OCUPAT}.get(st, M_ALTELE)
			return False, fel, "stare %s" % NUME_STARE.get(st, st)
		if model and r["model"] != model:
			return False, M_MODEL, "model %s in loc de %s" % (r["model"], model)
		for l in r["linii"]:
			if l["steaguri"] & LF_TIMEOUT:
				return False, M_TERMEN, "rand taiat de timp"
			if not l["text"].strip():
				return False, M_INCREDERE, "rand gol"
			if not l["cuvinte"] and l["steaguri"] & LF_LOW_CONF:
				return False, M_INCREDERE, "rand nesigur (steaguri %d)" % l["steaguri"]
			for c in l["cuvinte"]:
				limita = prag if _areLitere(c["text"]) else prag_semne
				if c["incredere"] < limita:
					return False, M_INCREDERE, "cuvant sub %d: %d (%s)" % (limita, c["incredere"], c["text"][:20])
	if not randuriPagina(rezultate):
		return False, M_FARA_TEXT, "fara text"
	return True, "", ""


def decideTextSauPoza(rezultate, model, prag=PRAG_INCREDERE):
	"""(foloseste_textul, motiv). Motivul e gol cand textul e bun."""
	ok, _fel, motiv = decizie(rezultate, model, prag)
	return ok, motiv


# ------------------------------------------------------------------ contorul

class Contor(object):
	"""cate pagini s-au citit ca text si cate au ramas poza (si de ce), timpii; numai in memorie"""

	def __init__(self, ceas=time.time):
		self.acum = ceas
		self.zero()

	def zero(self):
		self.pagini = 0
		self.text = 0
		self.poza = 0
		self.din_memorie = 0
		self.motive = dict((f, 0) for f in FELURI_MOTIV)
		self.timp_ms = 0.0           # suma timpilor paginilor recunoscute de serviciu (cerere -> raspuns)
		self.timp_n = 0
		self.timp_max_ms = 0.0
		self.serviciu_ms = 0.0       # suma timpilor raportati de serviciu (elapsed_us)
		self.serviciu_n = 0
		self.avans_ms = 0.0          # cu cat timp inainte de afisare au venit paginile trimise din timp
		self.avans_n = 0
		self.la_timp = 0             # text gata cel tarziu la afisare
		self.dupa_afisare = 0        # text gata dupa afisare
		self.caractere = 0
		self.ultimul_motiv = ""
		self.ultimele = deque(maxlen=ULTIMELE)
		self.de_la = self.acum()

	def pagina(self, rezultat, fel=u"", motiv=u"", ms=None, serviciu_ms=None, din_memorie=False, avans_ms=None,
			dupa_afisare_ms=None, linii=None, incredere_min=None):
		"""o pagina hotarata. rezultat: "text" sau "poza"."""
		self.pagini += 1
		if rezultat == "text":
			self.text += 1
		else:
			self.poza += 1
			self.motive[fel if fel in self.motive else M_ALTELE] += 1
			self.ultimul_motiv = motiv
		if din_memorie:
			self.din_memorie += 1
		elif ms is not None:
			self.timp_ms += ms
			self.timp_n += 1
			self.timp_max_ms = max(self.timp_max_ms, ms)
		if serviciu_ms is not None and not din_memorie:
			self.serviciu_ms += serviciu_ms
			self.serviciu_n += 1
		if avans_ms is not None and avans_ms >= 0:
			self.avans_ms += avans_ms
			self.avans_n += 1
		if rezultat == "text" and dupa_afisare_ms is not None:
			if dupa_afisare_ms <= 0:
				self.la_timp += 1
			else:
				self.dupa_afisare += 1
		text = u" / ".join(l["text"] for l in (linii or []))
		self.caractere += len(text)
		self.ultimele.appendleft({
			"ora": time.strftime("%H:%M:%S", time.localtime(self.acum())),
			"rezultat": rezultat, "fel": fel, "motiv": motiv,
			"ms": None if ms is None else int(round(ms)),
			"serviciu_ms": None if serviciu_ms is None else int(round(serviciu_ms)),
			"avans_ms": None if avans_ms is None or avans_ms < 0 else int(round(avans_ms)),
			"din_memorie": bool(din_memorie), "caractere": len(text), "incredere_min": incredere_min,
			"text": text[:120],
		})

	def dict(self):
		return {
			"pagini": self.pagini, "text": self.text, "poza": self.poza, "din_memorie": self.din_memorie,
			"motive": dict(self.motive),
			"timp_mediu_ms": int(round(self.timp_ms / self.timp_n)) if self.timp_n else None,
			"timp_max_ms": int(round(self.timp_max_ms)) if self.timp_n else None,
			"serviciu_mediu_ms": int(round(self.serviciu_ms / self.serviciu_n)) if self.serviciu_n else None,
			"avans_mediu_ms": int(round(self.avans_ms / self.avans_n)) if self.avans_n else None,
			"pagini_din_timp": self.avans_n, "la_timp": self.la_timp, "dupa_afisare": self.dupa_afisare,
			"ultimul_motiv": self.ultimul_motiv, "ultimele": list(self.ultimele),
			"de_la": time.strftime("%H:%M:%S", time.localtime(self.de_la)),
		}


def _incredereMinima(rezultate):
	v = [c["incredere"] for r in rezultate for l in r["linii"] for c in l["cuvinte"]]
	return min(v) if v else None


# ------------------------------------------------------------------ bucla (enigma2 sau select, pentru probe)

POLLIN, POLLOUT = 1, 4


class BuclaEnigma(object):
	"""eSocketNotifier + eTimer; fara eSocketNotifier in Python, un ceas de 20 ms citeste/scrie socketul neblocant"""

	def ceas(self, functie):
		from enigma import eTimer
		t = eTimer()
		t.callback.append(functie)
		return t

	def notificator(self, fd, functie, evenimente):
		try:
			from enigma import eSocketNotifier
			n = eSocketNotifier(fd, evenimente)
			n.callback.append(functie)
			return n
		except Exception:
			return _NotificatorCeas(self, fd, functie, evenimente)


class _NotificatorCeas(object):
	"""inlocuitorul lui eSocketNotifier: la fiecare 20 ms se cheama functia cu evenimentele cerute"""

	def __init__(self, bucla, fd, functie, evenimente):
		self.fd, self.functie, self.cerute = fd, functie, evenimente
		self.t = bucla.ceas(self._bate)
		self.t.start(20, False)

	def _bate(self):
		self.functie(self.cerute)

	def setRequested(self, evenimente):
		self.cerute = evenimente

	def stop(self):
		self.t.stop()


# ------------------------------------------------------------------ serviciul

class Serviciu(object):
	"""pornirea (Popen, fara sa astepte) si oprirea procesului hds-ocr"""

	def __init__(self, binar=BINAR, cale_socket=SOCKET, tessdata=TESSDATA, idle_exit_s=IDLE_EXIT_S, extra=None):
		self.binar, self.cale_socket, self.tessdata = binar, cale_socket, tessdata
		self.idle_exit_s = idle_exit_s
		self.extra = list(extra or [])
		self.dosare_extra = []           # dosarele modelelor descarcate (--tessdata-extra), puse de OcrSubtitrari
		self.proces = None
		self.porniri = 0

	def instalat(self):
		return os.access(self.binar, os.X_OK)

	def porneste(self):
		"""True daca procesul a fost lansat (sau merge deja al nostru)"""
		if self.proces is not None and self.proces.poll() is None:
			return True
		if not self.instalat():
			return False
		cmd = [self.binar, "--socket", self.cale_socket, "--tessdata", self.tessdata,
			"--idle-exit", str(self.idle_exit_s), "--nice", str(NICE)]
		for d in self.dosare_extra:
			cmd += ["--tessdata-extra", d]
		cmd += self.extra
		try:
			self.proces = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
		except (OSError, ValueError) as e:
			_jurnal("nu pot porni %s: %s" % (self.binar, e))
			self.proces = None
			return False
		self.porniri += 1
		_jurnal("serviciul pornit (pid %d)" % self.proces.pid)
		return True

	def culege(self):
		"""procesul nostru s-a terminat? (il culege, fara sa astepte). Intoarce codul de iesire sau None."""
		if self.proces is None:
			return None
		cod = self.proces.poll()
		if cod is not None:
			self.proces = None
		return cod

	def pid(self):
		return self.proces.pid if self.proces is not None and self.proces.poll() is None else None

	def _pideStraine(self):
		"""un hds-ocr pornit de alta instanta enigma2 (inainte de o repornire) pe acelasi socket"""
		pide = []
		try:
			intrari = os.listdir("/proc")
		except OSError:
			return pide
		for p in intrari:
			if not p.isdigit():
				continue
			try:
				with open("/proc/%s/cmdline" % p, "rb") as f:
					args = f.read().split(b"\0")
			except (IOError, OSError):
				continue
			if args and os.path.basename(args[0]) == os.path.basename(self.binar).encode() and \
					self.cale_socket.encode() in args:
				pide.append(int(p))
		return pide

	def opreste(self):
		"""SIGTERM (serviciul iese curat si sterge socketul); nu asteapta"""
		pide = set(self._pideStraine())
		if self.proces is not None and self.proces.poll() is None:
			pide.add(self.proces.pid)
		for p in pide:
			try:
				os.kill(p, signal.SIGTERM)
			except OSError:
				pass
		return sorted(pide)


# ------------------------------------------------------------------ clientul

class _Pagina(object):
	def __init__(self, generatie, model, laRezultat, ids):
		self.generatie = generatie
		self.model = model
		self.laRezultat = laRezultat
		self.asteptate = set(ids)
		self.rezultate = []
		self.gata = False
		self.termen = 0.0
		self.trimisa = 0.0


class ClientOcr(object):
	"""conexiunea cu serviciul: neblocanta, cu reconectare, pornirea serviciului la cerere si pauza dupa caderi.
	laRezultat al unei pagini primeste (generatie, linii sau None, motiv, fel, rezultate)."""

	def __init__(self, bucla, serviciu, cale_socket=SOCKET, ceas=time.time):
		self.bucla = bucla
		self.serviciu = serviciu
		self.cale_socket = cale_socket
		self.acum = ceas
		self.sock = None
		self.notif = None
		self.cititor = Cititor()
		self.iesire = b""
		self.conectat = False
		self.in_asteptare = []       # cadre de trimis dupa conectare
		self.pagini = {}             # request_id -> _Pagina
		self.urmatorul_id = 1
		self.pong = None
		self.caderi = []
		self.caderi_total = 0
		self.pauza_pana = 0.0        # pana cand OCR sta (dupa CADERI_MAXIME caderi)
		self.pauze = 0               # pauzele la rand (fiecare de doua ori mai lunga)
		self.t_conectare = self.bucla.ceas(self._incearcaConectarea)
		self.t_limita = self.bucla.ceas(self._verificaLimite)
		self.t_culege = self.bucla.ceas(self._culege)
		self.inceput_conectare = None

	# ---- pauza
	@property
	def oprit(self):
		"""True cat timp dureaza pauza de dupa caderi (se termina singura)"""
		return self.acum() < self.pauza_pana

	def pauzaRamasa(self):
		return max(0.0, self.pauza_pana - self.acum())

	def gataPauza(self, si_sirul=False):
		self.pauza_pana = 0.0
		self.caderi = []
		if si_sirul:
			self.pauze = 0

	# ---- conectarea
	def conecteaza(self):
		"""incepe conectarea (si pornirea serviciului daca trebuie); nu asteapta"""
		if self.conectat or self.oprit:
			return
		if self.inceput_conectare is None:
			self.inceput_conectare = self.acum()
			if not self._conecteazaAcum():
				if not self.serviciu.porneste():
					self._esec("serviciul nu poate porni")
					return
				self.t_culege.start(1000, False)
				self.t_conectare.start(PAS_CONECTARE_MS, False)

	def _conecteazaAcum(self):
		s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		s.setblocking(False)
		try:
			s.connect(self.cale_socket)
		except (OSError, socket.error) as e:
			s.close()
			if getattr(e, "errno", None) not in (errno.ENOENT, errno.ECONNREFUSED, errno.EAGAIN, errno.EWOULDBLOCK):
				_jurnal("conectare: %s" % e)
			return False
		self.sock = s
		self.conectat = True
		self.inceput_conectare = None
		self.t_conectare.stop()
		self.cititor = Cititor()
		self.iesire = b""
		self.notif = self.bucla.notificator(s.fileno(), self._eveniment, POLLIN)
		self._trimite(codeazaPing())
		for cadru in self.in_asteptare:
			self._trimite(cadru)
		self.in_asteptare = []
		return True

	def _incearcaConectarea(self):
		if self.conectat:
			self.t_conectare.stop()
			return
		if self._conecteazaAcum():
			return
		if self.acum() - (self.inceput_conectare or self.acum()) > TIMP_PORNIRE_MS / 1000.0:
			self.t_conectare.stop()
			self.inceput_conectare = None
			self._esec("serviciul nu raspunde pe %s" % self.cale_socket)

	def _culege(self):
		"""culege procesul pornit de noi cand iese (fara zombi); caderea se numara la conexiune, nu aici"""
		cod = self.serviciu.culege()
		if cod is not None or self.serviciu.proces is None:
			if cod is not None:
				_jurnal("serviciul a iesit cu codul %s" % cod)
			self.t_culege.stop()

	# ---- scrierea si citirea
	def _trimite(self, cadru):
		self.iesire += cadru
		self._scrie()

	def _scrie(self):
		while self.iesire and self.sock is not None:
			try:
				n = self.sock.send(self.iesire)
			except (OSError, socket.error) as e:
				if getattr(e, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
					break
				self._inchide("scriere: %s" % e)
				return
			self.iesire = self.iesire[n:]
		if self.notif is not None:
			self.notif.setRequested(POLLIN | (POLLOUT if self.iesire else 0))

	def _eveniment(self, evenimente):
		if self.sock is None:
			return
		if evenimente & POLLOUT:
			self._scrie()
		for _k in range(64):
			if self.sock is None:
				return
			try:
				date = self.sock.recv(65536)
			except (OSError, socket.error) as e:
				if getattr(e, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
					return
				self._inchide("citire: %s" % e)
				return
			if not date:
				self._inchide("serviciul a inchis conexiunea")
				return
			try:
				mesaje = self.cititor.adauga(date)
			except EroareProtocol as e:
				self._inchide("raspuns stricat: %s" % e)
				return
			for tip, corp in mesaje:
				self._mesaj(tip, corp)

	def _mesaj(self, tip, corp):
		if tip == MSG_PONG:
			try:
				self.pong = json.loads(corp.decode("utf-8"))
			except ValueError:
				self.pong = {"brut": corp[:200].decode("utf-8", "replace")}
			return
		if tip != MSG_RESULT:
			self._inchide("mesaj necunoscut %d" % tip)
			return
		try:
			r = decodeazaRezultat(corp)
		except EroareProtocol as e:
			self._inchide("rezultat stricat: %s" % e)
			return
		pagina = self.pagini.pop(r["request_id"], None)
		if pagina is None or pagina.gata:
			return                          # incalzire, sau o pagina deja rezolvata (termen)
		pagina.asteptate.discard(r["request_id"])
		pagina.rezultate.append(r)
		if r["stare"] != ST_OK or not pagina.asteptate:
			self._rezolva(pagina)

	# ---- paginile
	def cere(self, generatie, cereri, model, laRezultat, termen_ms=None):
		"""cereri: lista de dict pentru codeazaCerere (fara request_id); trimise ca o pagina. termen_ms = cat mai
		foloseste raspunsul (timeout_ms-ul cererilor); clientul mai asteapta MARJA_MS peste el."""
		ids = []
		cadre = []
		if termen_ms is None:
			termen_ms = max([int(c.get("timeout_ms") or TIMP_CERERE_MS) for c in cereri] or [TIMP_CERERE_MS])
		for c in cereri:
			rid = self.urmatorul_id
			self.urmatorul_id = (self.urmatorul_id % 0xFFFFFFFE) + 1
			ids.append(rid)
			cadre.append(codeazaCerere(rid, generatie, **c))
		pagina = _Pagina(generatie, model, laRezultat, ids)
		pagina.trimisa = self.acum()
		pagina.termen = pagina.trimisa + (termen_ms + MARJA_MS) / 1000.0
		for rid in ids:
			self.pagini[rid] = pagina
		if self.conectat:
			for cadru in cadre:
				self._trimite(cadru)
		else:
			self.in_asteptare.extend(cadre)
			self.conecteaza()
		if not self.t_limita.isActive():
			self.t_limita.start(100, False)
		return pagina

	def incalzeste(self, model):
		"""o regiune mica (o bara de 2x12) ca serviciul sa incarce modelul inainte de prima subtitrare"""
		if self.oprit:
			return
		px = bytearray(8 * 16)
		for y in range(2, 14):
			px[y * 8 + 3] = 1
			px[y * 8 + 4] = 1
		rid = self.urmatorul_id
		self.urmatorul_id = (self.urmatorul_id % 0xFFFFFFFE) + 1
		cadru = codeazaCerere(rid, 0, 8, 16, [0, 0xFFFFFFFF], bytes(px), limba=codProtocol(model), flags=FLAG_NO_CACHE,
			timeout_ms=TERMEN_MAXIM_MS)
		if self.conectat:
			self._trimite(cadru)
		else:
			self.in_asteptare.append(cadru)
			self.conecteaza()

	def in_zbor(self):
		return len(set(id(p) for p in self.pagini.values() if not p.gata))

	def _rezolva(self, pagina, motiv=None, fel=None):
		if pagina.gata:
			return
		pagina.gata = True
		for rid in list(pagina.asteptate):
			self.pagini.pop(rid, None)
		if motiv is None:
			ok, fel, motiv = decizie(pagina.rezultate, pagina.model)
			linii = randuriPagina(pagina.rezultate) if ok else None
		else:
			linii = None
			fel = fel or M_ALTELE
		if linii is not None:
			self.pauze = 0                   # serviciul merge: pauza urmatoare incepe iar de la PAUZA_S
		try:
			pagina.laRezultat(pagina.generatie, linii, motiv, fel, pagina.rezultate)
		except Exception as e:
			_jurnal("laRezultat: %s" % e)

	def _verificaLimite(self):
		acum = self.acum()
		for p in list(set(self.pagini.values())):
			if not p.gata and acum > p.termen:
				self._rezolva(p, "fara raspuns in %d ms" % int(round((p.termen - p.trimisa) * 1000)), M_TERMEN)
		if not self.pagini:
			self.t_limita.stop()

	def _esec(self, motiv):
		"""conectarea nu a reusit: toate paginile pe poza"""
		_jurnal(motiv)
		self.in_asteptare = []
		for p in list(set(self.pagini.values())):
			self._rezolva(p, motiv, M_SERVICIU)
		self.pagini = {}
		self._cadere(motiv)

	def _cadere(self, motiv):
		acum = self.acum()
		self.caderi = [t for t in self.caderi if acum - t < CADERI_FEREASTRA_S] + [acum]
		self.caderi_total += 1
		if len(self.caderi) >= CADERI_MAXIME and not self.oprit:
			durata = min(PAUZA_MAXIMA_S, PAUZA_S * (2 ** self.pauze))
			self.pauze += 1
			self.pauza_pana = acum + durata
			self.caderi = []
			_jurnal("%d caderi in %d s: OCR face o pauza de %d s (%s)" % (CADERI_MAXIME, CADERI_FEREASTRA_S, durata,
				motiv))

	def _inchide(self, motiv):
		_jurnal("conexiunea s-a inchis: %s" % motiv)
		if self.notif is not None:
			self.notif.stop()
			self.notif = None
		if self.sock is not None:
			try:
				self.sock.close()
			except OSError:
				pass
		self.sock = None
		self.conectat = False
		self.iesire = b""
		# fara pagini in lucru, un EOF e iesirea obisnuita a serviciului (--idle-exit): nu e o cadere
		in_lucru = [p for p in set(self.pagini.values()) if not p.gata]
		for p in in_lucru:
			self._rezolva(p, motiv, M_SERVICIU)
		self.pagini = {}
		if motiv != "oprit" and (in_lucru or not motiv.startswith("serviciul a inchis")):
			self._cadere(motiv)

	def inchide(self):
		self.t_conectare.stop()
		self.t_limita.stop()
		self.inceput_conectare = None
		self.in_asteptare = []
		if self.conectat:
			self._inchide("oprit")
		else:
			for p in list(set(self.pagini.values())):
				self._rezolva(p, "oprit", M_SERVICIU)
			self.pagini = {}


# ------------------------------------------------------------------ fatada

def _setareOcr():
	"""„Mărirea subtitrărilor DVB" = OCR? (config.subtitles.hds_marire_dvb)"""
	try:
		from Components.HdsSubtitrariAspect import initConfig
		return initConfig().hds_marire_dvb.value == "ocr"
	except Exception:
		return False


def _tvStins():
	"""Components/HdsStandbyTv.tvStins (televizorul stins, dupa driverul HDMI); fara modul, False"""
	try:
		from Components import HdsStandbyTv
		return bool(HdsStandbyTv.tvStins())
	except Exception:
		return False


# aceeasi fraza ca in Components/HdsTraducereSubtitrari.py (TEXT_TV_STINS): cu televizorul stins nimic nu se citeste si
# nimic nu se traduce; se arata numai in contor (ecranul Aspectul subtitrarilor si pagina web), niciodata ca fereastra
TEXT_TV_STINS = N_("Televizorul e stins sau în standby: subtitrările nu se citesc și nu se traduc până se aprinde.")


def ocrDeFolos():
	"""Pagina DVB citita acum ar folosi cuiva? Nu cand televizorul e stins (HdsStandbyTv.tvStins) si nici cand OCR-ul
	e cerut numai de traducere (fara "Mărirea subtitrărilor DVB" = OCR), iar traducerea nu traduce pista de acum (e deja
	in limba tinta: HdsTraducereSubtitrari.traduceDvbAcum). Atunci pagina ramane poza si serviciul hds-ocr nu lucreaza
	(iese singur dupa IDLE_EXIT_S fara cereri)."""
	if _tvStins():
		return False
	if _setareOcr():
		return True
	return bool(_traducere("traduceDvbAcum"))


def _tabelVizibil(paleta):
	t = bytearray(256)
	for i, c in enumerate(paleta[:256]):
		if ((c >> 24) & 255) >= ALFA_TRANSPARENT:
			t[i] = 1
	return bytes(t)


def _amprenta(model, cereri):
	"""amprenta paginii: modelul si, pentru fiecare regiune, pozitia, marimea, paleta si pixelii"""
	h = hashlib.blake2b(digest_size=16)
	h.update((model or "").encode("ascii", "replace"))
	for c in cereri:
		h.update(struct.pack("<hhHHH", c["x"], c["y"], c["latime"], c["inaltime"], len(c["paleta"])))
		h.update(struct.pack("<%dI" % len(c["paleta"]), *c["paleta"]))
		h.update(c["pixeli"])
	return h.digest()


def _seAting(a, b, gol=UNIRE_GOL_PX):
	"""doua dreptunghiuri (cereri) care se suprapun sau se ating pe verticala (cel mult `gol` px intre ele) si au macar
	o coloana comuna"""
	return (a["x"] < b["x"] + b["latime"] and b["x"] < a["x"] + a["latime"] and
		a["y"] <= b["y"] + b["inaltime"] + gol and b["y"] <= a["y"] + a["inaltime"] + gol)


def _lipeste(grup):
	"""cererile unui grup -> o singura cerere pe dreptunghiul lor, sau None cand nu se poate (prea mare pentru protocol,
	ori culorile tuturor, plus o intrare transparenta pentru goluri, nu incap in 256). Cu aceeasi paleta peste tot
	(ZDF) pixelii se copiaza ca atare; altfel paleta e reuniunea culorilor, iar indicii fiecarei regiuni se traduc."""
	x0 = min(c["x"] for c in grup)
	y0 = min(c["y"] for c in grup)
	x1 = max(c["x"] + c["latime"] for c in grup)
	y1 = max(c["y"] + c["inaltime"] for c in grup)
	w, h = x1 - x0, y1 - y0
	if w > MAX_DIM or h > MAX_DIM or w * h > MAX_PIXELI:
		return None
	paleta = list(grup[0]["paleta"])
	la_fel = all(c["paleta"] == paleta for c in grup)
	if not la_fel:
		loc = {}
		for i, culoare in enumerate(paleta):
			loc.setdefault(culoare, i)
		for c in grup[1:]:
			for culoare in c["paleta"]:
				if culoare not in loc:
					if len(paleta) >= 256:
						return None
					loc[culoare] = len(paleta)
					paleta.append(culoare)
	acoperit = sum(c["latime"] * c["inaltime"] for c in grup)
	gol = 0
	if not la_fel or acoperit < w * h or any(_seAting(a, b, gol=-1) for i, a in enumerate(grup) for b in grup[i + 1:]):
		# goluri intre regiuni (sau suprapuneri, cand suma ariilor nu spune nimic), ori indici din afara paletei unei
		# regiuni: fundalul = o intrare transparenta
		gol = next((i for i, c in enumerate(paleta) if ((c >> 24) & 255) < ALFA_TRANSPARENT), None)
		if gol is None:
			if len(paleta) >= 256:
				return None
			paleta.append(0)
			gol = len(paleta) - 1
	px = bytearray([gol]) * (w * h)
	for c in grup:
		cw = c["latime"]
		date = c["pixeli"]
		if not la_fel:
			# indicele regiunii -> indicele in paleta reunita; un indice din afara paletei ei ramane fundal (transparent)
			tabel = bytearray([gol]) * 256
			for i, culoare in enumerate(c["paleta"][:256]):
				tabel[i] = loc[culoare]
			date = bytes(date).translate(bytes(tabel))
		for y in range(c["inaltime"]):
			o = (c["y"] - y0 + y) * w + (c["x"] - x0)
			px[o:o + cw] = date[y * cw:(y + 1) * cw]
	u = dict(grup[0])
	u.update({"x": x0, "y": y0, "latime": w, "inaltime": h, "paleta": paleta, "pixeli": bytes(px)})
	return u


def unesteRegiunile(cereri, gol=UNIRE_GOL_PX):
	"""Cererile unei pagini (cate una pe regiune, ca din OcrSubtitrari._cerere) -> cererile de trimis: regiunile care se
	ating sau se suprapun (un rand de litere taiat in fasii) lipite intr-una singura, de sus in jos; celelalte raman cum
	sunt (si cele care nu se pot lipi, vezi _lipeste). Ordinea pixelilor la suprapunere: regiunea de mai jos in lista
	paginii deasupra."""
	if len(cereri) < 2:
		return list(cereri)
	grupe = []      # liste de indici in cereri
	for k, c in enumerate(cereri):
		legate = [g for g in grupe if any(_seAting(c, cereri[j], gol) for j in g)]
		nou = [k]
		for g in legate:
			grupe.remove(g)
			nou.extend(g)
		grupe.append(sorted(nou))
	iesire = []
	for g in grupe:
		if len(g) == 1:
			iesire.append(cereri[g[0]])
			continue
		g = [cereri[j] for j in g]
		u = _lipeste(g)
		if u is None:
			iesire.extend(g)
		else:
			iesire.append(u)
	iesire.sort(key=lambda c: (c["y"], c["x"]))
	return iesire


def _deTinutMinte(linii, fel):
	"""hotararile care nu depind de clipa: textul bun, increderea mica, pagina fara litere"""
	return linii is not None or fel in _MOTIVE_STABILE


def _cadereCuPagina(fel, motiv):
	"""conexiunea s-a inchis cu pagina in lucru (poate chiar din cauza ei)"""
	return fel == M_SERVICIU and (motiv.startswith("serviciul a inchis") or motiv.startswith("citire:"))


class _Asteptare(object):
	"""o pagina trimisa la serviciu si paginile identice venite intre timp (fiecare cu generatia si functia ei)"""

	def __init__(self, cheie, trimisa):
		self.cheie = cheie
		self.trimisa = trimisa
		self.cei = []          # (generatie, laRezultat, clipa afisarii in secunde, avansul in ms sau None)


def _depozitReceptor():
	"""Components.HdsOcrModele.depozit() (modelele descarcate), sau None daca modulul lipseste"""
	try:
		from Components import HdsOcrModele
		return HdsOcrModele.depozit()
	except Exception as e:
		_jurnal("modelele descarcate nu se pot citi: %s" % e)
		return None


def _ghicitor():
	"""Components/HdsOcrLimbaGhicita (ghicirea limbii unei piste fara limba), sau None daca lipseste"""
	try:
		from Components import HdsOcrLimbaGhicita as G
		return G
	except Exception:
		try:
			import HdsOcrLimbaGhicita as G
			return G
		except Exception as e:
			_jurnal("ghicirea limbii nu se poate incarca: %s" % e)
			return None


def _dateCanal():
	"""datele canalului de acum pentru ghicire (HdsOcrLimbaGhicita.dateCanalDeAcum); {} fara modul sau fara canal"""
	G = _ghicitor()
	if G is None:
		return {}
	try:
		return G.dateCanalDeAcum() or {}
	except Exception as e:
		_jurnal("datele canalului: %s" % e)
		return {}


class OcrSubtitrari(object):
	def __init__(self, bucla=None, serviciu=None, tessdata=TESSDATA, cale_socket=SOCKET, setare=None, ceas=time.time,
			depozit=None, date_canal=None, de_folos=None):
		self.bucla = bucla or BuclaEnigma()
		self.serviciu = serviciu or Serviciu(cale_socket=cale_socket, tessdata=tessdata)
		self.tessdata = tessdata
		# OCR ales la „Mărirea subtitrărilor DVB” sau cerut de traducerea subtitrarilor (esteOcrPornit)
		self.setare = setare or esteOcrPornit
		# o pagina citita acum ar folosi cuiva (ocrDeFolos); probele care dau `setare` nu au aceasta verificare
		self.deFolos = de_folos if de_folos is not None else (ocrDeFolos if setare is None else None)
		self.acum = ceas
		self.client = ClientOcr(self.bucla, self.serviciu, cale_socket=cale_socket, ceas=ceas)
		# modelele descarcate: depozitul receptorului numai pentru dosarul modelelor al imaginii (probele dau altul)
		self.depozit = depozit if depozit is not None else (_depozitReceptor() if tessdata == TESSDATA else None)
		if self.depozit is not None and hasattr(self.serviciu, "dosare_extra"):
			self.serviciu.dosare_extra = [d for d in self.depozit.dosareServiciu() if d != tessdata]
		self._generatie = None
		self.model = None
		self.limba = u""
		self.fel = None
		# pista DVB fara limba: limba ghicita dupa canal (cod canonic), sursa ei (HdsOcrLimbaGhicita.SURSE) si canalul;
		# fara_limba = pista de acum e DVB fara limba (ghicita sau nu)
		self.dateCanal = date_canal or _dateCanal
		self.limba_ghicita = None
		self.sursa_ghicire = None
		self.ref_ghicire = u""
		self.fara_limba = False
		# pista de acum e o poza dintr-un film (estePozaFilm): se citeste cu limba ei, fara ghicirea dupa canal
		self.poza_film = False
		self._modele = None
		self.pastreaza_sedila = False
		self.contor = Contor(ceas)
		self.memorie = OrderedDict()     # amprenta -> (linii relative la nimic: coordonatele paginii, fel, motiv)
		self.asteptari = {}              # amprenta -> _Asteptare
		self.cazute = OrderedDict()      # amprenta -> de cate ori a fost in lucru la o cadere a serviciului

	def modele(self):
		"""modelele de pe receptor: dosarul imaginii si cele descarcate. Se citesc din nou cand depozitul spune ca s-a
		schimbat ceva (o descarcare, o stergere); atunci si modelul pistei de acum se alege din nou."""
		gen = self.depozit.generatie() if self.depozit is not None else None
		if self._modele is None or gen != self._generatie:
			schimbare = self._modele is not None
			self._generatie = gen
			modele = set(modeleDisponibile(self.tessdata))
			if self.depozit is not None:
				try:
					instalate = self.depozit.modeleInstalate()
					self.depozit.puneLegaturi(instalate)
					modele |= set(instalate)
				except Exception as e:
					_jurnal("modelele descarcate: %s" % e)
			self._modele = frozenset(modele)
			if schimbare and (self.fel == 0 or self.poza_film) and self.model is None:
				self.model = modelPentruLimba(self.limba, self._modele, implicit=self.limba_ghicita)
				if self.model:
					_jurnal("model nou pentru pista de acum: %s" % self.model)
		return self._modele

	def activ(self):
		return bool(self.setare()) and not self.client.oprit and self.serviciu.instalat() and bool(self.modele())

	def pistaAleasa(self, pista):
		fel, limba = limbaDinPista(pista)
		self.limba = limba
		self.fel = fel
		self._modele = None                  # se recitesc (un pachet de model instalat intre timp)
		self.client.gataPauza()              # o pista aleasa de om: se incearca din nou pe loc
		self._uitaGhicirea()
		self.poza_film = estePozaFilm(pista)
		if fel not in (None, 0) and not self.poza_film:
			self.model = None                # teletextul si textul filmelor sunt deja text
			return None
		if esteFaraLimba(limba) and not self.poza_film:
			# un film nu are canal dupa care sa se ghiceasca limba: fara limba ramane poza
			self.fara_limba = True
			self._ghiceste(limba)
		self.model = modelPentruLimba(limba, self.modele(), implicit=self.limba_ghicita)
		if self.model and self.activ() and (self.deFolos is None or self.deFolos()):
			self.client.incalzeste(self.model)
		return self.model

	def _uitaGhicirea(self):
		self.limba_ghicita = None
		self.sursa_ghicire = None
		self.ref_ghicire = u""
		self.fara_limba = False

	def _ghiceste(self, limba_pistei=u""):
		"""limba pistei DVB fara limba, ghicita dupa canalul de acum (Components/HdsOcrLimbaGhicita.py); la versiunea
		originala numai dupa ghidul TV al subtitrarii (VERSIUNE_ORIGINALA)"""
		G = _ghicitor()
		if G is None:
			return None
		try:
			date = self.dateCanal() or {}
			if esteVersiuneOriginala(limba_pistei):
				l = G.dinComponenteSubtitrare(date.get("componente"))
				limba, sursa = (l, G.SURSA_GHID) if l else (None, None)
			else:
				limba, sursa = G.ghiceste(date.get("componente"), date.get("audio"), date.get("transponder"))
		except Exception as e:
			_jurnal("ghicirea limbii: %s" % e)
			return None
		self.limba_ghicita, self.sursa_ghicire = limba, sursa
		self.ref_ghicire = date.get("ref") or u""
		_jurnal("pista fara limba: %s" % ("limba ghicita %s, dupa %s" % (limba, sursa) if limba else
			"limba nu se poate ghici, ramane poza"))
		return limba

	def pistaOprita(self):
		self.model = None
		self.fel = None
		self.poza_film = False
		self.limba = u""
		self._uitaGhicirea()

	# ---- o pagina
	def _numara(self, rezultat, fel=u"", motiv=u"", **kw):
		try:
			self.contor.pagina(rezultat, fel, motiv, **kw)
		except Exception as e:
			_jurnal("contor: %s" % e)

	def cerePagina(self, generatie, regiuni, laRezultat, limba=None, intarziere_ms=-1):
		"""False = fara OCR pentru pagina asta (poza se arata acum); True = laRezultat vine o data (poate chiar in
		timpul apelului, pentru o pagina din memorie). intarziere_ms >= 0: pagina e trimisa din timp si se afiseaza
		peste atatea milisecunde; < 0: pagina se afiseaza acum."""
		if not bool(self.setare()) or not self.serviciu.instalat() or not self.modele():
			return False
		if self.deFolos is not None and not self.deFolos():
			return False                     # textul nu ar folosi nimanui (ocrDeFolos): poza, serviciul nu lucreaza
		if self.client.oprit:
			self._numara("poza", M_SERVICIU, "pauza dupa caderi (%d s ramase)" % int(self.client.pauzaRamasa()))
			return False
		model = modelPentruLimba(limba, self.modele(), implicit=self.limba_ghicita) if limba is not None else self.model
		if not model:
			if limba is None and self.fara_limba and not self.limba_ghicita:
				self._numara("poza", M_MODEL, "limba nedeclarata, nu se poate ghici")
			else:
				self._numara("poza", M_MODEL, "fara model pentru limba %s" % (limba if limba is not None else
					(self.limba_ghicita or self.limba)))
			return False
		cereri = []
		for r in regiuni:
			try:
				c = self._cerere(r, model)
			except (KeyError, TypeError, ValueError) as e:
				_jurnal("regiune gresita: %s" % e)
				self._numara("poza", M_ALTELE, "regiune gresita")
				return False
			if c is not None:
				cereri.append(c)
		if not cereri:
			# nimic vizibil: poza (transparenta) e tot ce trebuie; se numara, ca o pagina cu regiuni goale (de exemplu
			# un obiect pe care parserul nu l-a putut desena) sa se vada in contor, nu „nicio pagină încă”
			self._numara("poza", M_FARA_TEXT, "nimic vizibil in regiuni")
			return False
		# un rand de litere taiat in fasii (regiuni lipite una de alta) se trimite intreg (vezi REGIUNILE TAIATE)
		cereri = unesteRegiunile(cereri)
		acum = self.acum()
		intarziere_ms = int(intarziere_ms) if intarziere_ms is not None else -1
		afisare = acum + intarziere_ms / 1000.0 if intarziere_ms >= 0 else acum
		avans = intarziere_ms if intarziere_ms >= 0 else None
		try:
			cheie = _amprenta(model, cereri)
		except Exception as e:
			_jurnal("amprenta: %s" % e)
			cheie = None
		# o pagina deja hotarata: raspunsul pe loc
		if cheie is not None and cheie in self.memorie:
			linii, fel, motiv = self.memorie[cheie]
			self.memorie.move_to_end(cheie)
			self._numara("text" if linii is not None else "poza", fel, motiv, din_memorie=True, avans_ms=avans,
				dupa_afisare_ms=0, linii=linii)
			self._cheama(laRezultat, generatie, linii, motiv)
			return True
		# identica cu una aflata la serviciu: acelasi raspuns
		if cheie is not None and cheie in self.asteptari:
			self.asteptari[cheie].cei.append((generatie, laRezultat, afisare, avans))
			return True
		if self.client.in_zbor() >= MAX_IN_ZBOR:
			self._numara("poza", M_OCUPAT, "%d pagini in lucru" % MAX_IN_ZBOR)
			return False                     # serviciul nu tine pasul: poza, fara coada
		if intarziere_ms >= 0:
			termen_ms = min(TERMEN_MAXIM_MS, intarziere_ms + DURATA_UTILA_MS)
		else:
			termen_ms = min(TERMEN_MAXIM_MS, TIMP_CERERE_MS)
		for c in cereri:
			c["timeout_ms"] = termen_ms
		a = _Asteptare(cheie, acum)
		a.cei.append((generatie, laRezultat, afisare, avans))
		if cheie is not None:
			self.asteptari[cheie] = a
		try:
			self.client.cere(generatie, cereri, model,
				lambda gen, linii, motiv, fel, rezultate: self._gata(a, linii, motiv, fel, rezultate), termen_ms)
		except ValueError as e:
			self.asteptari.pop(cheie, None)
			_jurnal("cerere gresita: %s" % e)
			self._numara("poza", M_ALTELE, "cerere gresita")
			return False
		return True

	@staticmethod
	def _cheama(laRezultat, generatie, linii, motiv):
		try:
			laRezultat(generatie, linii, motiv)
		except Exception as e:
			_jurnal("laRezultat: %s" % e)

	def _gata(self, a, linii, motiv, fel, rezultate):
		"""raspunsul serviciului pentru o pagina (si copiile ei venite intre timp)"""
		if a.cheie is not None and self.asteptari.get(a.cheie) is a:
			del self.asteptari[a.cheie]
		acum = self.acum()
		tine = a.cheie is not None and _deTinutMinte(linii, fel)
		if a.cheie is not None and not tine and _cadereCuPagina(fel, motiv):
			n = self.cazute.pop(a.cheie, 0) + 1
			self.cazute[a.cheie] = n
			while len(self.cazute) > MAX_PAGINI_CAZUTE:
				self.cazute.popitem(last=False)
			tine = n >= CADERI_ACEEASI_PAGINA
		if tine:
			self.memorie[a.cheie] = (linii, fel if linii is None else u"", motiv)
			self.memorie.move_to_end(a.cheie)
			while len(self.memorie) > MEMORIE_PAGINI:
				self.memorie.popitem(last=False)
		ms = (acum - a.trimisa) * 1000.0
		serviciu_ms = None
		if rezultate:
			serviciu_ms = max(r["timp_us"] for r in rezultate) / 1000.0
		incr = _incredereMinima(rezultate) if rezultate else None
		for k, (generatie, laRezultat, afisare, avans) in enumerate(a.cei):
			self._numara("text" if linii is not None else "poza", fel if linii is None else u"", motiv,
				ms=ms if k == 0 else None, serviciu_ms=serviciu_ms if k == 0 else None, din_memorie=k > 0,
				avans_ms=avans, dupa_afisare_ms=(acum - afisare) * 1000.0, linii=linii, incredere_min=incr)
			self._cheama(laRezultat, generatie, linii, motiv)

	def _cerere(self, r, model):
		w, h = int(r["latime"]), int(r["inaltime"])
		if "paleta" in r:
			paleta = [int(c) & 0xFFFFFFFF for c in r["paleta"]]
		else:
			paleta = [argbDinEnigma(*c) for c in r["paleta_enigma"]]
		px = r["pixeli"]
		pas = int(r.get("pas") or w)
		if pas != w:
			px = b"".join(bytes(px[y * pas:y * pas + w]) for y in range(h))
		else:
			px = bytes(px[:w * h])
		if len(px) != w * h:
			raise ValueError("pixeli %d != %dx%d" % (len(px), w, h))
		if not px.translate(_tabelVizibil(paleta)).count(b"\x01"):
			return None
		flags = FLAG_KEEP_CEDILLA if self.pastreaza_sedila else 0
		return {"latime": w, "inaltime": h, "paleta": paleta, "pixeli": px, "limba": codProtocol(model), "flags": flags,
			"timeout_ms": TIMP_CERERE_MS, "x": int(r.get("x", 0)), "y": int(r.get("y", 0))}

	def stare(self):
		s = {"activ": self.activ(), "setare": bool(self.setare()), "instalat": self.serviciu.instalat(),
			"modele": sorted(self.modele()), "limba": self.limba, "model": self.model, "fel": self.fel,
			"fara_limba": self.fara_limba, "limba_ghicita": self.limba_ghicita, "sursa_ghicire": self.sursa_ghicire,
			"poza_film": self.poza_film,
			"conectat": self.client.conectat,
			"pid": self.serviciu.pid(), "porniri": self.serviciu.porniri, "oprit_dupa_caderi": self.client.oprit,
			"pauza_s": int(round(self.client.pauzaRamasa())), "caderi": self.client.caderi_total,
			"in_lucru": self.client.in_zbor(), "memorie": len(self.memorie), "serviciu": self.client.pong,
			"contor": self.contor.dict(),
			# televizorul stins: paginile raman poza fara sa se numere (ocrDeFolos), deci contorul sta
			"tv_stins": _tvStins()}
		# numele vechi (pagina web si jurnalul le citesc)
		c = s["contor"]
		s.update({"pagini": c["pagini"], "text": c["text"], "poza": c["poza"], "motiv": c["ultimul_motiv"]})
		return s

	def puneContorulLaZero(self):
		self.contor.zero()
		self.client.gataPauza(si_sirul=True)

	def ping(self):
		"""cere starea serviciului (vine in stare()["serviciu"])"""
		if self.client.conectat:
			self.client._trimite(codeazaPing())

	def opreste(self):
		self.client.inchide()
		return self.serviciu.opreste()


def pentruNucleu(widget, ocr=None):
	"""Functia pe care nucleul o cheama la fiecare pagina DVB, cand „Mărirea subtitrărilor DVB" = OCR (lib/gui/
	esubtitle.h: setOcrHandler, setOcrText, showOcrBitmap). eSubtitleWidget e facut de serviciu (enableSubtitles), nu
	de Python, deci `widget` e chiar clasa eSubtitleWidget, cu functii statice care gasesc pagina dupa generatie (un
	numar unic pentru toate widgeturile, niciodata 0):
	    eSubtitleWidget.setOcrHandler(pentruNucleu(eSubtitleWidget))
	    laPagina(generatie, regiuni[, intarziere_ms]) -> True: raspunsul vine prin widget.setOcrText(generatie, linii)
	                                         sau widget.showOcrBitmap(generatie), mai tarziu sau chiar in timpul
	                                         apelului (pagina din memorie)
	                                  False: fara OCR pentru pagina asta; nucleul arata poza (nu vine nimic)
	    regiuni: lista de tupluri (x, y, latime, inaltime, pas, paleta, pixeli), paleta = lista de (r, g, b, transparenta)
	             ca gRGB, pixeli = bytes (pas octeti pe rand)
	    intarziere_ms: >= 0 cand pagina e data la sosire (prefetchPage), cat mai e pana la afisare; -1 la afisare
	    linii:   lista de tupluri (text, x, y, latime, inaltime, baza, culoare ARGB a literelor), de sus in jos, in
	             coordonatele paginii DVB (720x576 sau marimea din DDS)"""
	o = ocr or instanta()

	def laPagina(generatie, regiuni, intarziere_ms=-1):
		def gata(gen, linii, motiv):
			try:
				if linii is None:
					widget.showOcrBitmap(gen)
				else:
					# traducerea (Components/HdsTraducereSubtitrari.py): cererea pleaca acum, de obicei inainte de afisare
					_traducere("inainte", [l["text"] for l in linii])
					widget.setOcrText(gen, [(l["text"], l["x"], l["y"], l["latime"], l["inaltime"], l["baza"], l["fill"])
						for l in linii])
			except Exception as e:
				_jurnal("pagina %s: %s" % (gen, e))
		try:
			reg = [{"x": r[0], "y": r[1], "latime": r[2], "inaltime": r[3], "pas": r[4], "paleta_enigma": r[5],
				"pixeli": r[6]} for r in regiuni]
			return bool(o.cerePagina(generatie, reg, gata, intarziere_ms=intarziere_ms))
		except Exception as e:
			_jurnal("pagina %s: %s" % (generatie, e))
			return False
	return laPagina


_INSTANTA = [None]


def instanta():
	if _INSTANTA[0] is None:
		_INSTANTA[0] = OcrSubtitrari()
	return _INSTANTA[0]


# ------------------------------------------------------------------ contorul, pentru ecran si pagina web

_TEXT_MOTIV = {
	M_TERMEN: N_("%d prea târziu"),
	M_INCREDERE: N_("%d text nesigur"),
	M_MODEL: N_("%d fără model pentru limbă"),
	M_SERVICIU: N_("%d serviciul oprit"),
	M_OCUPAT: N_("%d prea multe deodată"),
	M_FARA_TEXT: N_("%d fără litere"),
	M_ALTELE: N_("%d alte motive"),
}


def _secunde(ms):
	"""milisecunde -> „0,42 s" (virgula zecimala)"""
	return (u"%.2f s" % (ms / 1000.0)).replace(".", ",")


def contor():
	"""contorul de acum (dict), fara sa porneasca serviciul; None cand OCR nu a fost folosit de la pornire"""
	o = _INSTANTA[0]
	if o is None:
		return None
	return o.stare()


def puneContorulLaZero():
	o = _INSTANTA[0]
	if o is not None:
		o.puneContorulLaZero()
	return True


def textContorScurt(s=None):
	"""valoarea randului „Recunoașterea textului": „12 ca text, 3 ca imagine" sau „nicio pagină încă" """
	s = s or contor()
	c = s.get("contor") if s else None
	if not c or not c.get("pagini"):
		return _t("nicio pagină încă")
	return _t("%d ca text, %d ca imagine") % (c["text"], c["poza"])


def textContorDetalii(s=None, cuOk=True):
	"""fraza de sub lista: cate pagini, de ce au ramas imagine, timpul mediu; pe televizor (cuOk) si ca OK pune
	contorul la zero (in web e un buton). La o pista DVB fara limba, si fraza despre limba ghicita (textGhicire)."""
	s = s or contor()
	c = s.get("contor") if s else None
	ghicire = textGhicire(s) if s else u""
	# televizorul stins (0.6.2): paginile nu se citesc si nu se numara; fraza spune de ce contorul sta
	tv = _t(TEXT_TV_STINS) if s and s.get("tv_stins") else u""
	if not c or not c.get("pagini"):
		text = _t("Aici se numără paginile subtitrărilor DVB citite ca text și cele rămase imagine, cu motivul. "
			"Nu a venit încă nicio pagină.")
		return u" ".join(x for x in (tv, text, ghicire) if x)
	parti = ([tv] if tv else []) + [_t("Citite ca text: %d din %d.") % (c["text"], c["pagini"])]
	if ghicire:
		parti.append(ghicire)
	motive = [_t(_TEXT_MOTIV[f]) % c["motive"][f] for f in FELURI_MOTIV if c["motive"].get(f)]
	if motive:
		parti.append(_t("Rămase imagine: %s.") % u", ".join(motive))
	if c.get("timp_mediu_ms") is not None:
		parti.append(_t("Timp mediu pe pagină: %s.") % _secunde(c["timp_mediu_ms"]))
	if c.get("avans_mediu_ms") is not None:
		parti.append(_t("Paginile vin cu %s înainte.") % _secunde(c["avans_mediu_ms"]))
	if c.get("din_memorie"):
		parti.append(_t("Din memorie: %d.") % c["din_memorie"])
	if s.get("pauza_s"):
		parti.append(_t("Pauză după erori: încă %d s.") % s["pauza_s"])
	if cuOk:
		parti.append(_t("OK pune contorul la zero."))
	return u" ".join(parti)


# ------------------------------------------------------------------ limba ghicita: textele (televizor si web)

# o fraza pentru fiecare sursa a ghicirii (Components/HdsOcrLimbaGhicita.SURSE); %s = numele limbii. Aceleasi fraze in
# mesajul scurt de pe televizor, in ajutorul randului "Recunoașterea textului" si in pagina web /subtitrari.
_TEXT_GHICIRE = {
	"ghid": N_("Postul nu a declarat limba subtitrării. Limba ghicită după ghidul TV: %s."),
	"sunet": N_("Postul nu a declarat limba subtitrării. Limba ghicită după sunet: %s."),
	"transponder": N_("Postul nu a declarat limba subtitrării. Limba ghicită după celelalte canale de pe "
		"transponder: %s."),
}
_TEXT_GHICIRE["ghid_sunet"] = _TEXT_GHICIRE["ghid"]
TEXT_NEGHICITA = N_("Postul nu a declarat limba subtitrării și nu se poate ghici după canal. Subtitrarea rămâne "
	"imagine.")
SECUNDE_AVERTISMENT = 6
_AVERTIZATE = set()      # (canal, limba) pentru care mesajul a venit deja de la pornirea interfetei


def numeLimba(cod):
	"""codul canonic al limbii ghicite -> numele ei, tradus: numele modelului OCR al limbii (HdsOcrModele.numeModel; asa
	"esl" si "spa" dau amandoua Spaniolă), altfel Components/HdsPisteLimbi.numeLimba, altfel codul"""
	if not cod:
		return u""
	model = modelNecesar(u"", implicit=cod)
	if model:
		try:
			from Components.HdsOcrModele import NUME, numeModel
			if model in NUME:
				return numeModel(model)
		except Exception:
			pass
	try:
		from Components.HdsPisteLimbi import numeLimba as nume
		return nume(cod) or cod
	except Exception:
		return cod


def textGhicire(s=None):
	"""Fraza despre limba unei piste DVB fara limba: ghicita (si dupa ce) sau imposibil de ghicit; "" cand pista de acum
	are limba sau nu e DVB. s = stare() (sau contor())."""
	s = s if s is not None else contor()
	if not s or not s.get("fara_limba"):
		return u""
	cod = s.get("limba_ghicita")
	if not cod:
		return _t(TEXT_NEGHICITA)
	return _t(_TEXT_GHICIRE.get(s.get("sursa_ghicire")) or _TEXT_GHICIRE["ghid"]) % numeLimba(cod)


def _arata(text):
	"""mesajul scurt peste imagine (ca la subtitrarile din fisiere si din internet), SECUNDE_AVERTISMENT secunde"""
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, SECUNDE_AVERTISMENT, "HdsOcrLimbaGhicita")
		return True
	except Exception as e:
		_jurnal("mesajul despre limba: %s" % e)
		return False


def avertizeazaGhicirea(o):
	"""Pe televizor, o singura data pe canal si limba de la pornirea interfetei: limba subtitrarii e ghicita (si dupa
	ce), sau nu se poate ghici. Intoarce True daca mesajul a plecat."""
	if not getattr(o, "fara_limba", False):
		return False
	limba = getattr(o, "limba_ghicita", None)
	cheie = (getattr(o, "ref_ghicire", u""), limba)
	if cheie in _AVERTIZATE:
		return False
	text = textGhicire({"fara_limba": True, "limba_ghicita": limba, "sursa_ghicire": getattr(o, "sursa_ghicire", None)})
	if not text:
		return False
	_AVERTIZATE.add(cheie)
	return bool(_arata(text))


def _dupaAlegere(o, model):
	"""Dupa alegerea unei piste DVB cu OCR pornit (`model` = ce a intors o.pistaAleasa): limba fara model pe receptor =
	intrebarea de descarcare (o data; la o limba ghicita intrebarea spune asta); pista fara limba citita cu modelul
	limbii ghicite, sau ramasa poza fiindca limba nu se poate ghici = mesajul scurt. O limba ghicita fara model si fara
	intrebare (intrebata deja, "Nu mai întreba") ramane poza fara mesaj, ca o limba declarata fara model. La o poza
	dintr-un film (VobSub, PGS) numai intrebarea de descarcare, pentru limba declarata a pistei."""
	if getattr(o, "fel", None) != 0 and not getattr(o, "poza_film", False):
		return
	ghicita = getattr(o, "limba_ghicita", None)
	if model is None and o.serviciu.instalat():
		necesar = modelNecesar(o.limba, implicit=ghicita)
		if necesar:
			if ghicita:
				_propune(necesar, ghicita=True)
			else:
				_propune(necesar)
			return
	if getattr(o, "fara_limba", False) and (model is not None or not ghicita):
		avertizeazaGhicirea(o)


# ------------------------------------------------------------------ legaturile cu nucleul si cu ecranele

# cat nu se arata nimic cat se asteapta textul unei pagini afisate (eSubtitleWidget.setOcrWait); apoi poza, iar
# textul, daca mai vine, ii ia locul. O pagina trimisa din timp si gata la afisare nu asteapta deloc.
ASTEPTARE_TEXT_MS = 500

_PISTA = [None]          # subtitrarea pornita acum (tuplul din getSubtitleList); None = niciuna
_URMARIT = {"setare": False, "oprire": False}


def esteOcrPornit():
	"""„Mărirea subtitrărilor DVB" = „Recunoașterea textului (OCR)" (config.subtitles.hds_marire_dvb == "ocr"), sau
	traducerea subtitrarilor pornita si pentru subtitrarile DVB (Components/HdsTraducereSubtitrari.cereOcr)"""
	return bool(_setareOcr()) or cerutDeTraducere()


def cerutDeTraducere():
	"""OCR-ul e cerut de traducerea subtitrarilor (pornita si pentru subtitrarile DVB), oricare ar fi marirea DVB"""
	return bool(_traducere("cereOcr"))


def _traducere(nume, *argumente):
	"""Components/HdsTraducereSubtitrari.py (traducerea textului citit); fara modul, nimic"""
	try:
		from Components import HdsTraducereSubtitrari
		return getattr(HdsTraducereSubtitrari, nume)(*argumente)
	except Exception as e:
		_jurnal("traducerea, %s: %s" % (nume, e))
		return None


def _clasaNucleu():
	from enigma import eSubtitleWidget
	return eSubtitleWidget


def puneLegatura(widget=None):
	"""Pune functia in nucleu (OCR ales, serviciul si modelele instalate) sau o scoate (altfel; serviciul se opreste).
	Intoarce True daca OCR e legat. Nu arunca."""
	try:
		w = widget if widget is not None else _clasaNucleu()
	except Exception as e:
		_jurnal("eSubtitleWidget nu se poate incarca: %s" % e)
		return False
	pune = getattr(w, "setOcrHandler", None)
	if pune is None:
		_jurnal("enigma2 fara eSubtitleWidget.setOcrHandler: subtitrarile DVB raman poze")
		return False
	try:
		if esteOcrPornit():
			o = instanta()
			if o.serviciu.instalat() and o.modele():
				asteapta = getattr(w, "setOcrWait", None)
				if asteapta is not None:
					asteapta(ASTEPTARE_TEXT_MS)
				pune(pentruNucleu(w, o))
				_jurnal("pornit (modele: %s)" % " ".join(sorted(o.modele())))
				_cereStareaModelelor(o)
				if _PISTA[0] is not None:
					# pista pornita inainte ca OCR sa fie ales: aceeasi alegere, aceeasi propunere si acelasi mesaj
					# despre limba ghicita ca la pistaAleasa
					_dupaAlegere(o, o.pistaAleasa(_PISTA[0]))
				return True
			_jurnal("ales, dar %s: subtitrarile DVB raman poze" % ("fara modele in %s" % o.tessdata
				if o.serviciu.instalat() else "serviciul %s lipseste" % o.serviciu.binar))
		pune(None)
		if _INSTANTA[0] is not None:
			_INSTANTA[0].opreste()
	except Exception as e:
		_jurnal("legatura cu nucleul: %s" % e)
		try:
			pune(None)
		except Exception:
			pass
	return False


def _cereStareaModelelor(o):
	"""starea stickurilor citita pe fir (Components/HdsOcrModele.py) cand OCR se leaga: un model copiat de mana pe un
	stick intra in index inainte de prima pista, deci receptorul nu propune descarcarea unui model pe care il are"""
	try:
		dep = getattr(o, "depozit", None)
		if dep is not None:
			dep.cereStare()
	except Exception as e:
		_jurnal("starea modelelor: %s" % e)


def _laSchimbareSetare(element=None):
	puneLegatura()


def legaNucleul():
	"""Din Screens/SubtitleDisplay.py, la pornire: functia pusa sau scoasa dupa setare, si din nou la fiecare schimbare
	a setarii (notificarea se pune o singura data). Intoarce True daca OCR e legat."""
	if not _URMARIT["setare"]:
		try:
			from Components.HdsSubtitrariAspect import initConfig
			initConfig().hds_marire_dvb.addNotifier(_laSchimbareSetare, initial_call=False)
			_URMARIT["setare"] = True
		except Exception as e:
			_jurnal("setarea nu se poate urmari: %s" % e)
	return puneLegatura()


def pistaAleasa(pista):
	"""Screens/InfoBarGenerics.py, dupa enableSubtitles: limba pistei (sau, la o pista DVB fara limba, limba ghicita
	dupa canal) -> modelul, incarcat dinainte (serviciul pornit); apoi intrebarea de descarcare sau mesajul despre limba
	ghicita (_dupaAlegere). Pista se tine minte si cand OCR nu e ales (pentru cand se alege). Intoarce modelul sau
	None."""
	_PISTA[0] = pista
	_traducere("pistaAleasa", pista)
	try:
		if esteOcrPornit():
			o = instanta()
			model = o.pistaAleasa(pista)
			_dupaAlegere(o, model)
			return model
	except Exception as e:
		_jurnal("pista aleasa: %s" % e)
	return None


def poateCiti(limba):
	"""Components/HdsPisteLimbi.py (alegerea automata cu traducerea pornita): o pista DVB in limba `limba` poate fi
	citita ca text acum? OCR pornit (esteOcrPornit), serviciul instalat si modelul limbii pe receptor. O limba
	necunoscuta sau fara model: False (fara modelul implicit pentru pistele fara limba). Nu porneste serviciul."""
	try:
		if not limba or not esteOcrPornit():
			return False
		o = instanta()
		if not o.serviciu.instalat():
			return False
		return modelPentruLimba(limba, o.modele(), implicit=None) is not None
	except Exception as e:
		_jurnal("poateCiti: %s" % e)
		return False


def _propune(model, ghicita=False):
	"""limba pistei DVB nu are model pe receptor: intrebarea daca se descarca (o data; Components/HdsOcrModele.py);
	ghicita = limba e ghicita dupa canal (intrebarea o spune)"""
	if not model:
		return False
	try:
		from Components import HdsOcrModele
		if ghicita:
			return HdsOcrModele.propune(model, ghicita=True)
		return HdsOcrModele.propune(model)
	except Exception as e:
		_jurnal("propunerea de descarcare: %s" % e)
		return False


def pistaOprita():
	"""Screens/InfoBarGenerics.py: subtitrarea s-a oprit (serviciul iese singur dupa IDLE_EXIT_S)."""
	_PISTA[0] = None
	_traducere("pistaOprita")
	try:
		if _INSTANTA[0] is not None:
			_INSTANTA[0].pistaOprita()
	except Exception as e:
		_jurnal("pista oprita: %s" % e)


def opreste(*argumente):
	"""Serviciul oprit (standby, iesirea din enigma2); OCR ramane ales si porneste din nou la prima pagina."""
	try:
		if _INSTANTA[0] is not None:
			return _INSTANTA[0].opreste()
	except Exception as e:
		_jurnal("oprire: %s" % e)
	return []


def urmaresteOprirea():
	"""Screens/InfoBarGenerics.py (InfoBarSubtitleSupport): la standby (config.misc.standbyCounter) si la iesirea din
	enigma2 (atexit) serviciul se opreste. Se pune o singura data, oricate ecrane ar avea subtitrari."""
	if _URMARIT["oprire"]:
		return
	_URMARIT["oprire"] = True
	try:
		from Components.config import config
		config.misc.standbyCounter.addNotifier(opreste, initial_call=False)
	except Exception as e:
		_jurnal("standby nu se poate urmari: %s" % e)
	try:
		import atexit
		atexit.register(opreste)
	except Exception as e:
		_jurnal("iesirea nu se poate urmari: %s" % e)
