# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# teletext_web.py: teletextul in interfata web (HdsWebControl); perechea ecranului de pe tasta TEXT din bara
# (Screens/HdsTeletext.py) si a meniului lui (copiile salvate, teletextul clasic sau neted, conturul literelor, umbra
# literelor, formele in relief, copia automata).
#
# Aceeasi memorie a nucleului (lib/dvb/hdsteletext.cpp, eHdsTeletext) si acelasi modul comun (Components/HdsTeletext.py)
# ca pe televizor: numarul paginii, paginile vecine dintre cele primite, subpaginile (tinute sau lasate sa mearga),
# tintele tastelor colorate (FastText, altfel TOP, altfel -1 / +1 / +100 / pagina de pornire) si ce e ascuns, la cerere.
# Sursa paginilor: canalul care merge (eHdsTeletext.getInstance()) sau copia salvata a unui canal (Components/
# HdsTeletextCopie.py), incarcata in locul 1 al nucleului (eHdsTeletext.copie(1), al paginii web; locul 0 e al
# televizorului), fara tuner. Copia se reincarca numai cand se cere alt canal sau cand copia s-a refacut (alta data).
# Browserul deseneaza pagina pe un canvas, din celule (25 de randuri a cate 40). Textul fix al paginii si al paginii
# descarcate e in limba receptorului (ETICHETE si TEXTE_JS, traduse la fiecare cerere, ca la celelalte pagini traduse).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/teletext?pagina=N&sub=S&ascuns=0|1&copie=<ref>   pagina N (100-899), subpagina S (-1 = cea mai noua),
#            ce e ascuns (1 = se arata), copia canalului <ref> (fara: canalul de acum); fara ?pagina: pagina de pe
#            televizor cand ecranul e deschis, altfel pagina de pornire a serviciului
#   GET  /api/teletext-copii[?canale=1]       copiile, dosarul, spatiul, urmaritorul, setarile; cu canale=1 si canalele
#            care au teletext (din lamedb; lista poate fi mare)
#   POST /api/teletext-salveaza               copia canalului de acum
#   POST /api/teletext-sterge?ref=            sterge copia unui canal
#   POST /api/teletext-reimprospateaza?ref=   zap pe canal, o trecere completa a caruselului, copia, inapoi la canalul
#            de dinainte; raspunde pe loc, starea se vede apoi in /api/teletext-copii (urmaritor.reimprospatare)
#   POST /api/teletext-setari?hd=0|1&contur=0|1&umbra=0|1&relief=0|1&copie_automata=0|1&spatiu=N   setarile (hd =
#            teletextul neted; o valoare gresita nu schimba nimic)
#   GET  /api/teletext-descarca?ref=<ref>&fel=html|date   copia (fara ref: canalul de acum): fel=date fisierul .ttx
#            (comprimat zlib, ca pe disc), fel=html o singura pagina HTML care se citeste fara receptor (toate paginile
#            si subpaginile, desenatorul, navigarea; nicio cerere spre retea)
#   GET  /teletext                            pagina
#
# Desenatorul (DESENATOR, JavaScript) e unul singur, pentru /teletext si pentru pagina descarcata, clasic si neted
# (numele intern: hd), dupa compunerea din nucleu (lib/dvb/hdsteletext.cpp, compune cu a.hd): la neted fundalurile si
# mozaicul legat netezite pe toata grila de sextante 80 x 75 cu aceeasi logica (ttxStratHd, stratul HD din nucleu:
# laturi drepte, scarile ca linii oblice, colturile reale rotunjite) si blocurile separate rotunjite. Optiunile, ca pe
# televizor si oprite din fabrica: conturul de 1 px numai la literele deschise la culoare, umbra moale a literelor si,
# numai la neted, formele in relief.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. O pagina se randeaza de doua ori cel mult (a doua oara cu
# pozitia subpaginii in antet); lista copiilor citeste index.json. Pagina descarcata randeaza toate subpaginile: pe
# receptor pe felii de cel mult BUGET_S, cu un eTimer pus din nou dupa fiecare felie (intre felii se citesc tastele si
# soclurile, ca la canale_web.py), iar raspunsul pleaca la sfarsit (NOT_DONE_YET); fara NOT_DONE_YET (probele de pe PC)
# dintr-o bucata. Fisierul nu importa nimic din enigma2 la incarcare: probele dau modulele, nucleele, setarile,
# urmaritorul si dosarul lor (Mediu).
import json
import re
import time

MAX_TEXT = 12
MAX_REF = 512
SUBCOD_MAX = 0xFFFF
CIFRE = "0123456789"
LOC_WEB = 1               # locul paginii web in eHdsTeletext.copie(); 0 e al televizorului
BUGET_S = 0.04            # o felie a paginii descarcate
PAUZA_MS = 2              # intre felii
FELIE = 8                 # subpagini intre doua verificari ale bugetului
MAX_LUCRARI = 2           # pagini descarcate in lucru deodata
LUCRARI = set()
_INCARCATA = {"ref": None, "data": None, "nucleu": None}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele paginii se traduc la folosire."""
	return text


def _limba():
	"""Limba receptorului pentru <html lang> (de pilda "de" din "de_DE"); "ro" fara limba citibila (probele de pe PC)."""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


# Textul fix al paginii /teletext si al paginii descarcate, in limba receptorului (ca la celelalte pagini traduse, de
# pilda calitate_imagine_web.py): etichetele __T_<CHEIE>__ din sabloane, traduse si scapate pentru HTML, si textele
# scriptului, traduse si date paginii ca JSON (TXT; %s si %d se inlocuiesc in ordine, cu fmt).
ETICHETE = {
	"T_TITLU": N_("Teletext"),
	"T_SURSA": N_("Sursa"),
	"T_CANAL_ACUM": N_("Canalul de acum"),
	"T_CLASIC": N_("Clasic"),
	"T_NETED": N_("Neted"),
	"T_ECRAN": N_("Pagina de teletext"),
	"T_CITESTE": N_("Se citește teletextul..."),
	"T_PAGINA": N_("Pagina"),
	"T_MERGI": N_("Mergi"),
	"T_PAG_INAPOI": N_("Pagina dinainte"),
	"T_PAG_INAINTE": N_("Pagina următoare"),
	"T_SUB_INAPOI": N_("Subpagina dinainte"),
	"T_SUB_INAINTE": N_("Subpagina următoare"),
	"T_TINE": N_("Ține subpagina"),
	"T_ARATA_ASCUNS": N_("Arată ce e ascuns"),
	"T_TEXT_PAGINA": N_("Textul paginii, pentru copiere"),
	"T_COPII": N_("Copiile de teletext"),
	"T_SALVEAZA": N_("Salvează acum copia canalului de acum"),
	"T_TELETEXT_ACUM": N_("Teletextul canalului de acum:"),
	"T_DESCARCA_PAGINA": N_("Descarcă pagina"),
	"T_DESCARCA_DATE": N_("Descarcă datele"),
	"T_NOTA_REIMPROSPATARE": N_("Reîmprospătează: receptorul trece pe canal, motorul se rotește dacă trebuie, așteaptă o "
		"trecere completă a teletextului, apoi se întoarce la canalul de dinainte. O copie se deschide și fără semnal, de "
		"pildă când antena e pe alt satelit."),
	"T_NOTA_DESCARCA": N_("Descarcă pagina: un singur fișier HTML, cu toate paginile, care se citește în browser și fără "
		"receptor. Descarcă datele: fișierul copiei (.ttx), așa cum e pe receptor."),
	"T_CANALE": N_("Canalele cu teletext"),
	"T_NUME_CANAL": N_("Numele canalului"),
	"T_CAUTA_CANAL": N_("Caută un canal cu teletext"),
	"T_CAUTA": N_("Caută"),
	"T_SETARI": N_("Setări teletext"),
	"T_SET_NETED": N_("Teletext neted"),
	"T_SET_CONTUR": N_("Contur litere"),
	"T_SET_UMBRA": N_("Umbra literelor"),
	"T_SET_RELIEF": N_("Forme în relief"),
	"T_SET_AUTOMATA": N_("Copia automată"),
	"T_SET_SPATIU": N_("Spațiul pentru copii"),
	"T_DA": N_("Da"),
	"T_NU": N_("Nu"),
	"T_NOTA_NETED": N_("Teletext neted: desenele și casetele din pătrățele au linii drepte și colțuri rotunjite; Teletext "
		"clasic le arată în trepte, ca la emisie. Ce alegi aici se vede pe televizor și, până alegi altfel cu Clasic sau "
		"Neted, și în pagina asta."),
	"T_NOTA_OPTIUNI": N_("Contur litere: un contur negru subțire numai la literele deschise la culoare (albe, galbene și "
		"cele foarte deschise); peste imagine, și în jurul desenelor deschise. Umbra literelor: o umbră moale spre "
		"dreapta-jos. Forme în relief, numai la Teletext neted: desenele și casetele colorate au o margine mai închisă spre "
		"dreapta-jos, ca niște forme ridicate. Toate trei sunt oprite din fabrică."),
	"T_NOTA_AUTOMATA": N_("Copia automată: când teletextul canalului s-a strâns tot, receptorul îl salvează singur (o dată "
		"la 6 ore pe canal). Când spațiul se umple, pleacă întâi copiile cele mai vechi."),
	"T_PE_TV": N_("Pe televizor: tasta TEXT."),
	"T_NOTA_DESCARCATA": N_("Teletextul salvat de receptorul HD Satelit. Se citește fără receptor. Tastele: săgețile sus și "
		"jos schimbă pagina, stânga și dreapta subpagina."),
}

TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"rosu": N_("Roșu"),
	"verde": N_("Verde"),
	"galben": N_("Galben"),
	"albastru": N_("Albastru"),
	"tasta_pagina": N_("%s: pagina %s"),
	"tasta_fara": N_("%s: fără pagină"),
	"pe_tv": N_("pe televizor: pagina %s"),
	"copia": N_("Copia: %s, %s"),
	"lasa": N_("Lasă subpaginile să meargă"),
	"tine": N_("Ține subpagina"),
	"tinuta": N_("ținută"),
	"ascunde": N_("Ascunde din nou"),
	"arata_ascuns": N_("Arată ce e ascuns"),
	"necitit": N_("Receptorul nu a putut citi teletextul."),
	"nu_raspunde_retea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"numar": N_("Scrie un număr de pagină de la 100 la 899."),
	"din_copie": N_("Paginile vin din copia salvată, fără tuner."),
	"canal_acum": N_("Canalul de acum"),
	"pagini": N_("pagini: %s"),
	"nicio_copie": N_("Nu ai încă nicio copie de teletext."),
	"deschide": N_("Deschide"),
	"descarca_pagina": N_("Descarcă pagina"),
	"descarca_date": N_("Descarcă datele"),
	"reimprospateaza": N_("Reîmprospătează"),
	"sterge": N_("Șterge"),
	"intreaba_sterge": N_("Ștergi copia de teletext a canalului %s?"),
	"spatiu": N_("Spațiul folosit: %s din %s MB, în %s."),
	"urmaritor_oprit": N_("Urmăritorul teletextului nu merge acum."),
	"carusel_complet": N_("Canalul de acum (%s): caruselul complet, subpagini: %s."),
	"se_strang": N_("Canalul de acum (%s): se strâng paginile, subpagini: %s, %s s."),
	"se_reimprospateaza": N_("Se reîmprospătează %s..."),
	"la_zi": N_("Copia canalului %s e la zi."),
	"nereimprospatata": N_("Copia nu s-a putut reîmprospăta."),
	"se_trimite": N_("Se trimite..."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"niciun_canal": N_("Niciun canal cu teletext nu se potrivește."),
	"are_copie": N_("are copie"),
	"fara_copie": N_("fără copie"),
	"inca_canale": N_("Încă %s canale: scrie mai mult din nume."),
	"lipsa_copie": N_("Pagina %d nu e în copie"),
}


def _texte_pagina():
	"""{CHEIE: text}: etichetele traduse si scapate pentru HTML (si pentru atribute), LIMBA si TEXTE_JS (JSON)."""
	import html
	valori = dict((cheie, html.escape(_t(text), quote=True)) for cheie, text in ETICHETE.items())
	valori["LIMBA"] = _limba()
	valori["TEXTE_JS"] = _json_in_script(dict((cheie, _t(text)) for cheie, text in TEXTE_JS.items()))
	return valori


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsTeletext
	return HdsTeletext


class Mediu(object):
	"""Ce foloseste pagina. None = ce e pe receptor (enigma2); probele de pe PC dau modulul comun (M), modulul copiilor
	(K), nucleul viu si pe cel al copiei, setarile, urmaritorul, dosarul copiilor, configfile si ceasul lor."""

	def __init__(self, M=None, K=None, nucleu=None, nucleu_copie=None, setari=None, urmaritor=None, dosar=None,
			configfile=None, ceas=None):
		self._M = M
		self._K = K
		self.nucleu = nucleu            # None = canalul care merge (modulul comun il ia singur)
		self._nucleu_copie = nucleu_copie
		self._setari = setari
		self._urmaritor = urmaritor
		self._dosar = dosar
		self._configfile = configfile
		self.ceas = ceas or time.time

	def M(self):
		return _m(self._M)

	def K(self):
		if self._K is not None:
			return self._K
		from Components import HdsTeletextCopie
		return HdsTeletextCopie

	def nucleu_viu(self):
		return self.nucleu if self.nucleu is not None else self.M().nucleu()

	def nucleu_copie(self):
		"""eHdsTeletext.copie(1), tinut minte: SWIG da un obiect Python nou la fiecare chemare, iar _copie() compara
		nucleul dupa identitate (altfel copia s-ar reincarca la fiecare cerere)."""
		if self._nucleu_copie is None:
			try:
				from enigma import eHdsTeletext
				self._nucleu_copie = eHdsTeletext.copie(LOC_WEB)
			except Exception:
				return None
		return self._nucleu_copie

	def setari(self):
		if self._setari is not None:
			return self._setari
		try:
			return self.K().setari()
		except Exception:
			return None

	def urmaritor(self):
		if self._urmaritor is not None:
			return self._urmaritor
		try:
			return self.K().urmaritor()
		except Exception:
			return None

	def dosar(self):
		return self._dosar if self._dosar is not None else self.K().dosar()

	def configfile(self):
		if self._configfile is not None:
			return self._configfile
		try:
			from Components.config import configfile
			return configfile
		except Exception:
			return None


# ---------------------------------------------------------------- celulele

def _litera(cod):
	"""Litera unei celule ca sir; codurile de control, surogatele si ce nu e punct Unicode raman spatiu."""
	try:
		cod = int(cod)
	except (TypeError, ValueError):
		return " "
	if cod < 0x20 or 0x7F <= cod < 0xA0 or 0xD800 <= cod <= 0xDFFF or cod > 0x10FFFF:
		return " "
	return chr(cod)


def _celule(M, randuri, arata_ascuns):
	"""Randurile din M.decodeaza -> (25 de randuri de [text, culoare, fundal, mozaic, atribute], are_ascuns). Celulele de
	sub sau din dreapta unei litere duble si cele ascunse (fara ascuns=1) raman numai cu fundalul; are_ascuns = pagina are
	ceva ascuns (o litera sau un mozaic, nu doar spatii)."""
	jumatate = M.A_JUMATATE_JOS | M.A_JUMATATE_DREAPTA
	iesire = []
	are_ascuns = False
	for rand in randuri:
		r = []
		for cod, mozaic, fata, fundal, atribute in rand:
			text = " " if mozaic else _litera(cod)
			if atribute & M.A_ASCUNS and not atribute & jumatate and ((mozaic & 0x3F) or text != " "):
				are_ascuns = True
			if atribute & jumatate or (atribute & M.A_ASCUNS and not arata_ascuns):
				r.append([" ", fata, fundal, 0, atribute])
			else:
				r.append([text, fata, fundal, mozaic, atribute])
		iesire.append(r)
	return iesire, are_ascuns


def _goale(M):
	"""Pagina fara nimic: spatii albe pe negru."""
	return [[(0x20, 0, 7, 0, 0)] * M.COLOANE for _ in range(M.RANDURI)]


def _compact(M, randuri):
	"""O subpagina pentru pagina descarcata: [text (1000 de litere, mozaicul si jumatatile ca spatiu, ce e ascuns
	ramane), [n, culoare, fundal, mozaic, atribute, ...] (fugi de celule cu aceleasi atribute)]."""
	jumatate = M.A_JUMATATE_JOS | M.A_JUMATATE_DREAPTA
	text = []
	fugi = []
	prec = None
	cate = 0
	for rand in randuri:
		for cod, mozaic, fata, fundal, atribute in rand:
			text.append(" " if mozaic or atribute & jumatate else _litera(cod))
			cheie = (fata, fundal, mozaic, atribute)
			if cheie == prec:
				cate += 1
			else:
				if prec is not None:
					fugi.extend((cate,) + prec)
				prec, cate = cheie, 1
	if prec is not None:
		fugi.extend((cate,) + prec)
	return ["".join(text), fugi]


# ---------------------------------------------------------------- argumentele

def _numar(M, text):
	"""Numarul paginii din adresa: trei cifre, 100-899; altfel None."""
	text = (text or "").strip()
	if len(text) != 3 or any(c not in CIFRE for c in text):
		return None
	return M.normalizeaza(text)


def _subcod(text):
	"""Subpagina din adresa: -1 (sau nimic) = cea mai noua, altfel subcodul (0-65535); None = gresit."""
	text = (text or "").strip()
	if text in ("", "-1"):
		return -1
	if len(text) > 5 or any(c not in CIFRE for c in text):
		return None
	n = int(text)
	return n if n <= SUBCOD_MAX else None


def _gresit(mesaj):
	return {"result": False, "message": mesaj}


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = ("pagina", "sub", "ascuns", "copie", "ref", "fel", "canale", "hd", "contur", "umbra", "relief", "copie_automata",
		"spatiu")
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_REF if cheie in ("copie", "ref") else MAX_TEXT].strip()
	return rez


# ---------------------------------------------------------------- copiile si setarile

def _copie(E, ref):
	"""Copia canalului `ref` in locul paginii web: (informatiile copiei, nucleul) sau (None, None). Se reincarca numai la
	alt canal, la alta data a copiei sau la alt nucleu."""
	K = E.K()
	d = E.dosar()
	info = K.copia(ref, d)
	n = E.nucleu_copie()
	if info is None or n is None:
		return None, None
	if _INCARCATA["ref"] != ref or _INCARCATA["data"] != info.get("data") or _INCARCATA["nucleu"] is not n:
		_INCARCATA.update(ref=None, data=None, nucleu=None)
		if K.incarca(ref, LOC_WEB, d, n) is None:
			return None, None
		_INCARCATA.update(ref=ref, data=info.get("data"), nucleu=n)
	return info, n


def _info_copie(K, c):
	return {"ref": c["ref"], "nume": c.get("nume") or "", "data": c.get("data", 0), "data_text": K.data_text(c.get("data")),
		"pagini": c.get("pagini", 0), "subpagini": c.get("subpagini", 0), "octeti": c.get("octeti", 0)}


def _valoare(s, cheie, implicit):
	try:
		return getattr(s, cheie).value
	except Exception:
		return implicit


def _hd(E):
	return bool(_valoare(E.setari(), "hd", False))     # neted oprit din fabrica (0.3.0)


OPTIUNI = ("contur", "umbra", "relief")     # oprite din fabrica


def _optiuni(E):
	"""Conturul, umbra si relieful, ca pe televizor: {nume: bool}."""
	s = E.setari()
	return dict((nume, bool(_valoare(s, nume, False))) for nume in OPTIUNI)


def _setari_text(E):
	K = E.K()
	s = E.setari()
	rez = {"hd": bool(_valoare(s, "hd", False)), "copie_automata": bool(_valoare(s, "copie_automata", True)),
		"spatiu": str(_valoare(s, "spatiu", K.SPATIU_IMPLICIT_MB)), "spatii": list(K.SPATII_MB), "pot_schimba": s is not None}
	rez.update(_optiuni(E))
	return rez


def _text_rezultat(rezultat, K):
	try:
		text = K.text_rezultat(rezultat, _t)
	except Exception:
		text = ""
	if text:
		return text
	if rezultat.get("motiv") == "inregistrare":
		return _t("Acum se înregistrează, deci canalul nu se schimbă. Încearcă după înregistrare.")
	return _t("Copia nu s-a putut reîmprospăta.")


def _stare_urmaritor(u, K=None):
	if u is None:
		return None
	try:
		st = u.stare()
	except Exception:
		return None
	r = st.get("reimprospatare")
	if r:
		r = dict((k, r[k]) for k in ("ref", "inapoi", "inceput", "gata", "rezultat") if k in r)
		if isinstance(r.get("rezultat"), dict) and not r["rezultat"].get("ok"):
			# motivul pentru om (ce s-a intamplat, cate pagini s-au strans), acelasi text ca pe televizor
			r["rezultat"] = dict(r["rezultat"])
			r["rezultat"]["text"] = _text_rezultat(r["rezultat"], K)
	return {"ref": st.get("ref"), "nume": st.get("nume") or "", "complet": bool(st.get("complet")),
		"subpagini": st.get("subpagini", 0), "secunde": st.get("secunde", 0), "reimprospatare": r}


def copii(argumente, E=None):
	"""GET /api/teletext-copii: numai citire."""
	E = E or Mediu()
	K = E.K()
	d = E.dosar()
	lista = [_info_copie(K, c) for c in K.copii(d)]
	s = _setari_text(E)
	try:
		ales_mb = int(s["spatiu"])
	except (TypeError, ValueError):
		ales_mb = int(K.SPATIU_IMPLICIT_MB)
	rez = {"result": True, "copii": lista, "dosar": d, "spatiu_folosit": sum(c["octeti"] for c in lista),
		"spatiu_ales_mb": ales_mb, "urmaritor": _stare_urmaritor(E.urmaritor(), K), "setari": s}
	if argumente.get("canale") == "1":
		rez["canale_cu_teletext"] = [[r, n] for r, n in K.canale_cu_teletext()]
	return rez


def _cu_copii(E, reusit, mesaj, **altele):
	rez = copii({}, E)
	rez.update(altele)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def salveaza(argumente, E=None):
	"""POST /api/teletext-salveaza: copia canalului de acum, ca "Salveaza acum copia canalului" de pe televizor."""
	E = E or Mediu()
	K = E.K()
	u = E.urmaritor()
	ref, nume = u._ref_acum() if u is not None else (None, "")
	if not ref:
		return _cu_copii(E, False, _t("Copia nu s-a putut salva."))
	if not K.ref_salvabila(ref):
		return _cu_copii(E, False, _t("Copiile se fac numai pentru canale, nu pentru înregistrări."))
	rez = K.salveaza(ref, nume, E.nucleu, E.dosar())
	if rez is None:
		return _cu_copii(E, False, _t("Canalul de acum nu are încă pagini de teletext."))
	_INCARCATA.update(ref=None, data=None, nucleu=None)
	return _cu_copii(E, True, _t("Copia s-a salvat: %d de pagini") % rez.get("pagini", 0), copie=_info_copie(K, rez))


def sterge(argumente, E=None):
	"""POST /api/teletext-sterge?ref=: sterge copia unui canal."""
	E = E or Mediu()
	ref = argumente.get("ref", "")
	if not ref or not E.K().sterge(ref, E.dosar()):
		return _cu_copii(E, False, _t("Copia aceasta nu există."))
	if _INCARCATA["ref"] == ref:
		_INCARCATA.update(ref=None, data=None, nucleu=None)
	return _cu_copii(E, True, _t("Copia s-a șters."))


def reimprospateaza(argumente, E=None):
	"""POST /api/teletext-reimprospateaza?ref=: porneste reimprospatarea si raspunde pe loc."""
	E = E or Mediu()
	ref = argumente.get("ref", "")
	if not ref or not E.K().ref_salvabila(ref):
		return _cu_copii(E, False, _t("Canalul acesta nu se poate reîmprospăta."))
	u = E.urmaritor()
	if u is None:
		return _cu_copii(E, False, _t("Urmăritorul teletextului nu merge pe receptor."))
	r = getattr(u, "reimprospatare", None)
	if r and not r.get("gata"):
		return _cu_copii(E, False, _t("O reîmprospătare e deja în lucru."))
	if not u.reimprospateaza(ref, None):
		motiv = ((getattr(u, "reimprospatare", None) or {}).get("rezultat") or {}).get("motiv")
		if motiv == "inregistrare":
			return _cu_copii(E, False, _t("Acum se înregistrează, deci canalul nu se schimbă. Încearcă după înregistrare."))
		return _cu_copii(E, False, _t("Copia nu s-a putut reîmprospăta."))
	return _cu_copii(E, True, _t("Reîmprospătarea a pornit: receptorul trece pe canal, așteaptă o trecere completă a "
		"teletextului, apoi se întoarce la canalul de dinainte."))


def seteaza(argumente, E=None):
	"""POST /api/teletext-setari: hd (teletextul neted), contur, umbra, relief, copie_automata, spatiu; o valoare
	gresita nu schimba nimic."""
	E = E or Mediu()
	s = E.setari()
	if s is None:
		return _cu_copii(E, False, _t("Setările teletextului nu sunt pe receptorul acesta."))
	schimbari = []
	for cheie in ("hd",) + OPTIUNI + ("copie_automata",):
		if cheie in argumente:
			if argumente[cheie] not in ("0", "1"):
				return _cu_copii(E, False, _t("Valoarea aceasta nu există."))
			schimbari.append((getattr(s, cheie), argumente[cheie] == "1"))
	if "spatiu" in argumente:
		if argumente["spatiu"] not in E.K().SPATII_MB:
			return _cu_copii(E, False, _t("Valoarea aceasta nu există."))
		schimbari.append((s.spatiu, argumente["spatiu"]))
	if not schimbari:
		return _cu_copii(E, False, _t("Nu s-a trimis nicio setare."))
	for element, valoare in schimbari:
		element.value = valoare
		element.save()
	cf = E.configfile()
	if cf is not None:
		cf.save()
	return _cu_copii(E, True, _t("Setările s-au salvat."))


# ---------------------------------------------------------------- pagina

def stare(argumente, E=None):
	"""GET /api/teletext: numai citire. `argumente` ca la argumente(request)."""
	E = E or Mediu()
	M = E.M()
	ref_copie = argumente.get("copie", "")
	ascuns = argumente.get("ascuns", "") == "1"
	sub = -1
	if ref_copie:
		tv_numar, tv_subcod = None, -1
	else:
		tv_numar, tv_subcod = M.pagina_televizor()
		tv_numar = M.normalizeaza(tv_numar)
	if argumente.get("pagina", ""):
		numar = _numar(M, argumente["pagina"])
		if numar is None:
			return _gresit(_t("Pagina se scrie cu trei cifre, de la 100 la 899."))
	else:
		numar = tv_numar
		if numar is not None:
			try:
				sub = int(tv_subcod)
			except (TypeError, ValueError):
				sub = -1
	if "sub" in argumente:
		sub = _subcod(argumente["sub"])
		if sub is None:
			return _gresit(_t("Subpagina se scrie ca număr; -1 este cea mai nouă."))
	nucleu = E.nucleu
	info = None
	if ref_copie:
		info, nucleu = _copie(E, ref_copie)
		if info is None:
			return _gresit(_t("Copia nu se poate citi."))
	st = M.stare(nucleu)
	if numar is None:
		numar = M.normalizeaza(st["initiala"]) or M.PAGINA_IMPLICITA
	goale = _goale(M)
	randuri = _celule(M, goale, ascuns)[0]
	rez = {"result": True, "sursa": "copie" if info else "direct", "copie": _info_copie(E.K(), info) if info else None,
		"hd": _hd(E), "optiuni": _optiuni(E), "are_teletext": bool(st["are_teletext"]), "nucleu": bool(st.get("nucleu")),
		"pid": st["pid"],
		"nume": st["nume"] or "", "pagini_in_memorie": st["pagini"], "subpagini_in_memorie": st["subpagini"],
		"pagina": numar, "subcod": -1, "gasita": False, "subpagini": [], "pozitie": "", "televizor": tv_numar,
		"taste": {"fel": "simplu", "tinte": [0, 0, 0, 0]}, "vecine": [numar, numar], "ascuns": ascuns,
		"are_ascuns": False, "randuri": randuri, "text": M.text_randuri(goale, ascuns), "mesaj": ""}
	if not rez["nucleu"]:
		rez["mesaj"] = _t("Imaginea de pe receptor nu are încă teletextul.")
	elif not rez["are_teletext"]:
		rez["mesaj"] = _t("Canalul de acum nu are teletext.")
	else:
		toate = M.subpagini(numar, nucleu_dat=nucleu)
		if sub >= 0 and sub not in toate:
			sub = -1     # subpagina tinuta a iesit din memorie: cea mai noua
		text_antet = M.text_stare(numar)
		pg = M.pagina(numar, sub, text_antet, cu_antet=True, nucleu_dat=nucleu)
		if pg is not None:
			poz = M.subcod_text(pg["subcod"], toate) if pg["gasita"] else ""
			if poz and len(text_antet) + 1 + len(poz) <= 8:
				pg = M.pagina(numar, pg["subcod"], text_antet + " " + poz, cu_antet=True, nucleu_dat=nucleu) or pg
			randuri, are_ascuns = _celule(M, pg["randuri"], ascuns)
			gasita = bool(pg["gasita"])
			rez.update({"subcod": pg["subcod"] if gasita else -1, "gasita": gasita, "subpagini": toate if gasita else [],
				"pozitie": poz, "randuri": randuri, "text": M.text_randuri(pg["randuri"], ascuns),
				"are_ascuns": are_ascuns})
		if not rez["gasita"]:
			rez["mesaj"] = (_t("Pagina %d nu e în copie") if info else _t("Pagina %d se caută")) % numar
	rez["taste"] = M.taste_colorate(numar, rez["subcod"], nucleu_dat=nucleu, initiala=st["initiala"])
	existente = M.pagini_existente(nucleu_dat=nucleu)
	rez["vecine"] = [M.vecina(numar, -1, existente), M.vecina(numar, 1, existente)]
	return rez


# ---------------------------------------------------------------- descarcarea

def nume_fisier(nume, data, extensie):
	"""teletext-<canal>-<AAAA-LL-ZZ-HHMM>.<extensie>, numai litere ASCII, cifre si cratime."""
	import unicodedata
	s = unicodedata.normalize("NFKD", nume or "").encode("ascii", "ignore").decode("ascii").lower()
	s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "canal"
	try:
		z = time.strftime("%Y-%m-%d-%H%M", time.localtime(int(data or 0)))
	except (TypeError, ValueError, OverflowError):
		z = "0"
	return "teletext-%s-%s.%s" % (s, z, extensie)


def _sursa_descarcare(argumente, E):
	"""(eroare, nucleu, nume, data, info copie). Fara ref: canalul de acum."""
	M = E.M()
	ref = argumente.get("ref", "")
	if ref:
		info, n = _copie(E, ref)
		if info is None:
			return _gresit(_t("Copia nu se poate citi.")), None, "", 0, None
		return None, n, info.get("nume") or ref, info.get("data", 0), info
	n = E.nucleu_viu()
	if n is None or not M.stare(n)["are_teletext"]:
		return _gresit(_t("Canalul de acum nu are teletext.")), None, "", 0, None
	u = E.urmaritor()
	nume = ""
	if u is not None:
		try:
			nume = u._ref_acum()[1]
		except Exception:
			nume = ""
	return None, n, nume or M.stare(n)["nume"], int(E.ceas()), None


def descarca_date(argumente, E=None):
	"""fel=date: (nume fisier, tip, octeti) sau eroarea. Copia asa cum e pe disc; canalul de acum comprimat la fel."""
	import os
	import zlib
	E = E or Mediu()
	eroare, n, nume, data, info = _sursa_descarcare(argumente, E)
	if eroare is not None:
		return eroare
	if info is not None:
		try:
			with open(os.path.join(E.dosar(), E.K().copia(info["ref"], E.dosar())["fisier"]), "rb") as f:
				octeti = f.read()
		except (IOError, OSError, KeyError, TypeError):
			return _gresit(_t("Copia nu se poate citi."))
	else:
		octeti = zlib.compress(n.exporta(), 6)
	return nume_fisier(nume, data, "ttx"), b"application/octet-stream", octeti


def _json_in_script(obiect):
	text = json.dumps(obiect, ensure_ascii=False, separators=(",", ":"))
	return (text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
		.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _html(text):
	return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def gen_descarcare_html(argumente, E=None):
	"""fel=html, ca generator: cedeaza dupa fiecare FELIE subpagini; la sfarsit intoarce (nume fisier, tip, octeti) sau
	eroarea. Fiecare subpagina: textul si fugile celulelor (_compact) si tintele tastelor colorate (FastText ale
	subpaginii, altfel TOP sau -1 / +1 / +100 / pornire, o data pe pagina)."""
	E = E or Mediu()
	M = E.M()
	K = E.K()
	eroare, n, nume, data, info = _sursa_descarcare(argumente, E)
	if eroare is not None:
		return eroare
	ref = info["ref"] if info else ""
	st = M.stare(n)
	initiala = st["initiala"]
	date = {"nume": nume, "data_text": K.data_text(data), "sursa": "copie" if info else "direct", "initiala": initiala,
		"hd": _hd(E), "optiuni": _optiuni(E), "pagini": {}}
	simple = {}
	facute = 0
	for numar in M.pagini_existente(nucleu_dat=n):
		lista = []
		toate = M.subpagini(numar, nucleu_dat=n)
		for sc in toate:
			text_antet = M.text_stare(numar)
			poz = M.subcod_text(sc, toate)
			if poz and len(text_antet) + 1 + len(poz) <= 8:
				text_antet += " " + poz
			pg = M.pagina(numar, sc, text_antet, cu_antet=True, nucleu_dat=n)
			if pg is None or not pg["gasita"]:
				continue
			leg = n.legaturi(numar, sc)
			if leg and any(leg[:4]):
				tinte = [int(x) for x in leg[:4]]
			else:
				if numar not in simple:
					simple[numar] = M.taste_colorate(numar, sc, nucleu_dat=n, initiala=initiala)["tinte"]
				tinte = simple[numar]
			lista.append(_compact(M, pg["randuri"]) + [tinte, sc])
			facute += 1
			if facute % FELIE == 0:
				yield
				if ref:
					# intre felii pagina /teletext poate fi incarcat alta copie in acelasi loc: se pune la loc
					info2, n = _copie(E, ref)
					if info2 is None:
						return _gresit(_t("Copia nu se poate citi."))
		if lista:
			date["pagini"][str(numar)] = lista
	titlu = "Teletext %s, %s" % (nume, date["data_text"]) if date["data_text"] else "Teletext %s" % nume
	html = pagina_descarcata(titlu, date)
	return nume_fisier(nume, data, "html"), b"text/html; charset=utf-8", html.encode("utf-8", "replace")


def pagina_descarcata(titlu, date):
	"""Fisierul HTML al paginii descarcate: titlul, datele copiei si textul fix in limba receptorului."""
	valori = _texte_pagina()
	valori.update({"TITLU": _html(titlu), "DESENATOR": _traducePagina(DESENATOR, "js"), "DATE": _json_in_script(date)})
	return inlocuieste(_traducePagina(PAGINA_DESCARCATA), valori)


def pana_la_capat(gen):
	"""Un generator de felii rulat dintr-o bucata (probele, sau fara NOT_DONE_YET)."""
	try:
		while True:
			next(gen)
	except StopIteration as sfarsit:
		return sfarsit.value


class PeFelii(object):
	"""Generatorul pe firul enigma2: o felie (cel mult BUGET_S) la o bataie de eTimer, apoi ceasul se pune din nou la
	PAUZA_MS, ca intre felii bucla enigma2 sa citeasca tastele si soclurile. `gata(rezultat)` la sfarsit."""

	def __init__(self, gen, gata):
		from enigma import eTimer
		self.gen = gen
		self.gata = gata
		self.oprit = False
		self.ceas = eTimer()
		self.ceas.callback.append(self.pas)

	def porneste(self):
		LUCRARI.add(self)
		self.ceas.start(PAUZA_MS, True)

	def opreste(self, *_a):
		self.oprit = True
		self.ceas.stop()
		LUCRARI.discard(self)

	def pas(self):
		if self.oprit:
			return
		inceput = time.time()
		try:
			while True:            # cel putin un pas pe felie, apoi cat tine bugetul
				next(self.gen)
				if time.time() - inceput >= BUGET_S:
					break
		except StopIteration as sfarsit:
			self.opreste()
			self.gata(sfarsit.value)
			return
		except Exception as eroare:
			self.opreste()
			self.gata(_gresit(_t("Eroare pe receptor: %s") % eroare))
			return
		self.ceas.start(PAUZA_MS, True)


# ---------------------------------------------------------------- resursele

def rute(baza, resource, NOT_DONE_YET=None, mediu=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `resource` e
	twisted.web.resource; cu NOT_DONE_YET (twisted.web.server) pagina descarcata se face pe felii. `mediu` numai pentru
	probe."""
	E = mediu or Mediu()

	class TeletextResource(baza):
		"""GET /api/teletext: numai citire."""

		def render_GET(self, request):
			try:
				rez = stare(argumente(request), E)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			return self._raspunde(request, rez, 200 if rez["result"] else 400)

	class CopiiResource(baza):
		"""GET /api/teletext-copii: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, copii(argumente(request), E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SalveazaResource(_Schimba):
		lucru = staticmethod(salveaza)

	class StergeResource(_Schimba):
		lucru = staticmethod(sterge)

	class ReimprospateazaResource(_Schimba):
		lucru = staticmethod(reimprospateaza)

	class SetariResource(_Schimba):
		lucru = staticmethod(seteaza)

	class DescarcaResource(baza):
		"""GET /api/teletext-descarca: fisierul (attachment); erorile in JSON."""

		def _fisier(self, request, rez):
			if isinstance(rez, dict):
				return self._raspunde(request, rez, 200 if rez.get("result") else 400)
			nume, tip, octeti = rez
			request.setResponseCode(200)
			request.setHeader(b"content-type", tip)
			request.setHeader(b"content-disposition", ('attachment; filename="%s"' % nume).encode("ascii", "replace"))
			request.setHeader(b"cache-control", b"no-store")
			request.setHeader(b"x-content-type-options", b"nosniff")
			return octeti

		def render_GET(self, request):
			try:
				a = argumente(request)
				fel = a.get("fel", "html")
				if fel == "date":
					return self._fisier(request, descarca_date(a, E))
				if fel != "html":
					return self._eroare(request, _t("Valoarea aceasta nu există."), 400)
				if NOT_DONE_YET is None:
					return self._fisier(request, pana_la_capat(gen_descarcare_html(a, E)))
				if len(LUCRARI) >= MAX_LUCRARI:
					return self._eroare(request, _t("Receptorul are prea multe cereri în lucru. Încearcă din nou."), 503)
				resursa = self

				def gata(rez):
					try:
						request.write(resursa._fisier(request, rez))
						request.finish()
					except Exception:
						pass

				lucru = PeFelii(gen_descarcare_html(a, E), gata)
				try:
					request.notifyFinish().addErrback(lucru.opreste)
				except Exception:
					pass
				lucru.porneste()
				return NOT_DONE_YET
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /teletext: pagina Teletext."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"teletext": TeletextResource(),
		b"teletext-copii": CopiiResource(),
		b"teletext-salveaza": SalveazaResource(),
		b"teletext-sterge": StergeResource(),
		b"teletext-reimprospateaza": ReimprospateazaResource(),
		b"teletext-setari": SetariResource(),
		b"teletext-descarca": DescarcaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /piste si /subtitrari-film."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def inlocuieste(sablon, valori):
	"""__NUME__ -> valori["NUME"], dintr-o singura trecere (ce se pune nu mai e cautat din nou)."""
	return re.sub(r"__([A-Z_]+?)__", lambda m: valori.get(m.group(1), m.group(0)), sablon)


def pagina_text(stil, config_pagina):
	valori = _texte_pagina()
	valori.update({"STIL_COMUN": stil, "DESENATOR": _traducePagina(DESENATOR, "js"), "CONFIG": config_pagina})
	return inlocuieste(_traducePagina(PAGINA), valori)


# Desenatorul, comun pentru /teletext si pentru pagina descarcata. ttxDeseneaza(canvas, randuri, {hd, contur, umbra,
# relief, faza, ascuns}) -> {intermitente, ms}; randuri = 25 x 40 de [text, culoare, fundal, mozaic, atribute]; hd =
# teletextul neted.
# Canvasul are celule intregi de l x i pixeli, cu l = 5k si i = 6k: 40 x l pe 25 x i e exact 4:3 si nu raman rosturi
# intre celule; k vine din latimea pe ecran inmultita cu densitatea pixelilor (cel mult 2). Ordinea, ca in nucleu:
# fundalurile si mozaicul legat (neted: cu relieful, daca e pornit), literele (cu umbra si conturul, daca sunt
# pornite), mozaicul separat. Litera fontului monospatiat e mai ingusta decat celula: se lateste (M adus la 84% din
# celula, intre 1 si 1,6). Impartirea mozaicului in sextante si rostul separatului (o treime din bloc, in stanga si jos)
# sunt cele din nucleu. Neted: separatul cu colturi rotunde (raza 0,6 din jumatatea laturii mici); fundalurile si
# mozaicul legat din ttxStratHd, aceeasi logica pas cu pas ca stratul HD din lib/dvb/hdsteletext.cpp (stratHd: grila de
# culori 80 x 75, lanturile granitelor, poligonul fiecarui lant cu scarile ca linii oblice si colturile reale rotunjite,
# apoi numai diferenta fata de sextante, cu acoperirea exacta a pixelilor), comparata pixel cu pixel cu nucleul
# (teste/test_teletext_hd_2_web.py). Umbra literelor deplasata max(1, i / 20), estompata max(1, i / 12) (shadowBlur =
# 2 sigma; o medie pe 2r + 1 are sigma de cam r / 1,73), opacitate 0,75. Conturul de 1 px numai la literele deschise
# la culoare (luminanta Rec. 709 de cel putin TTX_PRAG_DESCHIS, ca PRAG_DESCHIS din nucleu).
DESENATOR = r"""
var TTX_CULORI = ["#000000", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff"];
var TTX_RGB = [[0, 0, 0], [255, 0, 0], [0, 255, 0], [255, 255, 0], [0, 0, 255], [255, 0, 255], [0, 255, 255], [255, 255, 255]];
var A_DUBLA_INALTIME = 1, A_DUBLA_LATIME = 2, A_SEPARAT = 4, A_ASCUNS = 8, A_INTERMITENT = 16, A_JUMATATE_JOS = 64, A_JUMATATE_DREAPTA = 128;
// luminanta relativa (Rec. 709, x 256) si pragul de la care o culoare e deschisa si primeste contur, ca in nucleu
var TTX_PRAG_DESCHIS = 128;
function ttxLuminanta(r, g, b){ return (54 * r + 183 * g + 19 * b + 128) >> 8; }
var TTX_DESCHISA = TTX_RGB.map(function(c){ return ttxLuminanta(c[0], c[1], c[2]) >= TTX_PRAG_DESCHIS; });
function ttxAcum(){ return (window.performance && performance.now) ? performance.now() : Date.now(); }
function ttxMarime(cv){
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var k = Math.max(1, Math.round((cv.clientWidth || 800) * dpr / 200));
  var l = 5 * k, i = 6 * k;
  if(cv.width !== 40 * l || cv.height !== 25 * i){ cv.width = 40 * l; cv.height = 25 * i; }
  return {l: l, i: i};
}
function ttxSeVede(ce, opt){
  var a = ce[4];
  if(a & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA)){ return false; }
  if((a & A_INTERMITENT) && opt.faza){ return false; }
  if((a & A_ASCUNS) && !opt.ascuns){ return false; }
  return true;
}
function ttxRotund(ctx, x0, y0, x1, y1){
  var r = Math.min((x1 - x0) / 2, (y1 - y0) / 2) * 0.6;
  ctx.beginPath();
  ctx.moveTo(x0 + r, y0);
  ctx.lineTo(x1 - r, y0);
  ctx.arcTo(x1, y0, x1, y0 + r, r);
  ctx.lineTo(x1, y1 - r);
  ctx.arcTo(x1, y1, x1 - r, y1, r);
  ctx.lineTo(x0 + r, y1);
  ctx.arcTo(x0, y1, x0, y1 - r, r);
  ctx.lineTo(x0, y0 + r);
  ctx.arcTo(x0, y0, x0 + r, y0, r);
  ctx.closePath();
  ctx.fill();
}
function ttxBlocuri(ctx, ce, x, y, w, h, hd){
  var s = ce[3] & 63, sep = (ce[4] & A_SEPARAT) !== 0;
  var xs = [0, (w + 1) >> 1, w], ys = [0, Math.floor((h + 1) / 3), Math.floor((2 * h + 1) / 3), h];
  ctx.fillStyle = TTX_CULORI[ce[1] & 7];
  for(var k = 0; k < 6; k++){
    if((s & (1 << k)) === 0){ continue; }
    var cx = k & 1, cy = k >> 1, bx0 = xs[cx], bx1 = xs[cx + 1], by0 = ys[cy], by1 = ys[cy + 1];
    if(sep){
      var gx = Math.floor((bx1 - bx0) / 3), gy = Math.floor((by1 - by0) / 3);
      bx0 += gx > 0 ? gx : 1;
      by1 -= gy > 0 ? gy : 1;
    }
    if(hd && sep){ ttxRotund(ctx, x + bx0, y + by0, x + bx1, y + by1); }
    else { ctx.fillRect(x + bx0, y + by0, bx1 - bx0, by1 - by0); }
  }
}
var TTX_GW = 80, TTX_GH = 75, TTX_TREAPTA_LUNGA = 6, TTX_TREAPTA_SCURTA = 2, TTX_SIMPLIFICARE_PX = 0.4;
var TTX_DX = [1, 0, -1, 0], TTX_DY = [0, 1, 0, -1];
function ttxHartaHd(l, i){
  var x = new Int32Array(TTX_GW + 1), y = new Int32Array(TTX_GH + 1), g, k;
  for(g = 0; g <= TTX_GW; g++){ x[g] = Math.floor(g / 2) * l + ((g % 2) ? Math.floor((l + 1) / 2) : 0); }
  for(g = 0; g <= TTX_GH; g++){
    k = g % 3;
    y[g] = Math.floor(g / 3) * i + (k === 0 ? 0 : (k === 1 ? Math.floor((i + 1) / 3) : Math.floor((2 * i + 1) / 3)));
  }
  function px(v){ var q = Math.floor(v); if(q < 0){ q = 0; } if(q > TTX_GW - 1){ q = TTX_GW - 1; } return x[q] + (v - q) * (x[q + 1] - x[q]); }
  function py(v){ var q = Math.floor(v); if(q < 0){ q = 0; } if(q > TTX_GH - 1){ q = TTX_GH - 1; } return y[q] + (v - q) * (y[q + 1] - y[q]); }
  return {x: x, y: y, px: px, py: py};
}
function ttxGrilaHd(R, opt){
  var c = new Uint8Array(TTX_GW * TTX_GH), m = new Uint8Array(TTX_GW * TTX_GH), r, col, k, aprinse = false;
  for(r = 0; r < 25; r++){
    for(col = 0; col < 40; col++){
      for(k = 0; k < 3; k++){ c[(3 * r + k) * TTX_GW + 2 * col] = R[r][col][2] & 7; c[(3 * r + k) * TTX_GW + 2 * col + 1] = R[r][col][2] & 7; }
    }
  }
  for(r = 0; r < 25; r++){
    for(col = 0; col < 40; col++){
      var ce = R[r][col], a = ce[4], s;
      if(a & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA)){ continue; }
      if((a & A_INTERMITENT) && opt.faza){ continue; }
      if((a & A_ASCUNS) && !opt.ascuns){ continue; }
      if(ce[3]){ if(a & A_SEPARAT){ continue; } s = ce[3] & 63; }
      else if(ce[0] === "■"){ s = 63; }
      else { continue; }
      if(!s){ continue; }
      aprinse = true;
      var dl = (a & A_DUBLA_LATIME) ? 1 : 0, di = (a & A_DUBLA_INALTIME) ? 1 : 0, fata = ce[1] & 7, fundal = ce[2] & 7;
      for(k = 0; k < 6; k++){
        var ap = (s >> k) & 1, cx = k & 1, cy = k >> 1;
        var gx0 = 2 * col + (dl ? 2 * cx : cx), gx1 = gx0 + (dl ? 2 : 1), gy0 = 3 * r + (di ? 2 * cy : cy), gy1 = gy0 + (di ? 2 : 1);
        for(var gy = gy0; gy < gy1 && gy < TTX_GH; gy++){
          for(var gx = gx0; gx < gx1 && gx < TTX_GW; gx++){ c[gy * TTX_GW + gx] = ap ? fata : fundal; m[gy * TTX_GW + gx] = ap; }
        }
      }
    }
  }
  return {c: c, m: m, aprinse: aprinse};
}
function ttxUrmaritorHd(g){
  // in afara paginii culoarea 0 (negru, transparent peste imagine), ca pe ecran; laturile: H (y 0..GH, x 0..GW-1),
  // V (y 0..GH-1, x 0..GW)
  var W = TTX_GW, c = g.c, m = g.m, H = new Uint8Array((TTX_GH + 1) * TTX_GW), V = new Uint8Array(TTX_GH * (TTX_GW + 1)), aLegat = true;
  var PA = [3, 2, 1, 0], PB = [1, 0, 3, 2], WV = TTX_GW + 1;
  function cul(x, y){ return (x >= 0 && x < TTX_GW && y >= 0 && y < TTX_GH) ? c[y * W + x] : 0; }
  function aprins(x, y){ return x >= 0 && x < TTX_GW && y >= 0 && y < TTX_GH && m[y * W + x] ? true : false; }
  function latura(x, y, d){
    if(d === 0){ return x < TTX_GW && cul(x, y - 1) !== cul(x, y); }
    if(d === 1){ return y < TTX_GH && cul(x - 1, y) !== cul(x, y); }
    if(d === 2){ return x >= 1 && cul(x - 1, y - 1) !== cul(x - 1, y); }
    return y >= 1 && cul(x - 1, y - 1) !== cul(x, y - 1);
  }
  function parcursa(x, y, d){ return d === 0 ? H[y * W + x] : (d === 1 ? V[y * WV + x] : (d === 2 ? H[y * W + x - 1] : V[(y - 1) * WV + x])); }
  function marcheaza(x, y, d){ if(d === 0){ H[y * W + x] = 1; } else if(d === 1){ V[y * WV + x] = 1; } else if(d === 2){ H[y * W + x - 1] = 1; } else { V[(y - 1) * WV + x] = 1; } }
  function culori(x, y, d){
    if(d === 0){ return [cul(x, y - 1), cul(x, y)]; }
    if(d === 1){ return [cul(x, y), cul(x - 1, y)]; }
    if(d === 2){ return [cul(x - 1, y), cul(x - 1, y - 1)]; }
    return [cul(x - 1, y - 1), cul(x, y - 1)];
  }
  function tip(x, y){
    var n = 0, d;
    for(d = 0; d < 4; d++){ if(latura(x, y, d)){ n++; } }
    aLegat = true;
    if(n === 2){ return 1; }
    if(n !== 4){ return 0; }
    var nv = cul(x - 1, y - 1), ne = cul(x, y - 1), sv = cul(x - 1, y), se = cul(x, y);
    if(nv !== se || ne !== sv){ return 0; }
    var fa = aprins(x - 1, y - 1) && aprins(x, y), fb = aprins(x, y - 1) && aprins(x - 1, y);
    if(fa !== fb){ aLegat = fa; }
    else {
      var na = 0, nb = 0;
      for(var yy = y - 2; yy <= y + 1; yy++){
        for(var xx = x - 2; xx <= x + 1; xx++){ var v = cul(xx, yy); if(v === nv){ na++; } else if(v === ne){ nb++; } }
      }
      aLegat = na <= nb;
    }
    return 2;
  }
  function urmatoarea(x, y, d){
    var venit = (d + 2) & 3, t = tip(x, y);
    if(t === 1){ for(var s = 0; s < 4; s++){ if(s !== venit && latura(x, y, s)){ return s; } } return -1; }
    if(t === 2){ return aLegat ? PA[venit] : PB[venit]; }
    return -1;
  }
  function celula(x, y){ return (x >= 0 && x < TTX_GW && y >= 0 && y < TTX_GH) ? y * TTX_GW + x : -1; }
  function celule(x, y, d){
    if(d === 0){ return [celula(x, y - 1), celula(x, y)]; }
    if(d === 1){ return [celula(x, y), celula(x - 1, y)]; }
    if(d === 2){ return [celula(x - 1, y), celula(x - 1, y - 1)]; }
    return [celula(x - 1, y - 1), celula(x, y - 1)];
  }
  function urmareste(x0, y0, d0){
    var cul = culori(x0, y0, d0), cel = celule(x0, y0, d0), v = [x0 + y0 * (TTX_GW + 1)], x = x0, y = y0, d = d0, inchis = false;
    for(;;){
      marcheaza(x, y, d);
      x += TTX_DX[d];
      y += TTX_DY[d];
      var nd = urmatoarea(x, y, d);
      if(nd < 0){ v.push(x + y * (TTX_GW + 1)); break; }
      if(parcursa(x, y, nd)){ inchis = true; break; }
      v.push(x + y * (TTX_GW + 1));
      d = nd;
    }
    return {v: v, inchis: inchis, st: cul[0], dr: cul[1], cst: cel[0], cdr: cel[1]};
  }
  function lanturi(){
    var L = [], x, y, d;
    for(y = 0; y <= TTX_GH; y++){
      for(x = 0; x <= TTX_GW; x++){
        if(tip(x, y) !== 0){ continue; }
        for(d = 0; d < 4; d++){ if(latura(x, y, d) && !parcursa(x, y, d)){ L.push(urmareste(x, y, d)); } }
      }
    }
    for(y = 0; y <= TTX_GH; y++){ for(x = 0; x < TTX_GW; x++){ if(latura(x, y, 0) && !parcursa(x, y, 0)){ L.push(urmareste(x, y, 0)); } } }
    for(y = 0; y < TTX_GH; y++){ for(x = 0; x <= TTX_GW; x++){ if(latura(x, y, 1) && !parcursa(x, y, 1)){ L.push(urmareste(x, y, 1)); } } }
    return L;
  }
  function netezit(x, y){
    for(var yy = y - 1; yy <= y; yy++){
      for(var xx = x - 1; xx <= x; xx++){ if(yy >= 0 && yy < TTX_GH && xx >= 0 && xx < TTX_GW && m[yy * W + xx]){ return true; } }
    }
    return false;
  }
  return {lanturi: lanturi, netezit: netezit};
}
function ttxLantHd(Lt, u, h, raza, iesire, niv){
  var N = Lt.v.length, L1 = TTX_GW + 1, k, inchis = Lt.inchis, v = Lt.v.slice();
  if(N < 2){ return; }
  if(inchis){
    var start = -1;
    for(k = 0; k < N && start < 0; k++){ if(v[k] - v[(k + N - 1) % N] !== v[(k + 1) % N] - v[k]){ start = k; } }
    if(start < 0){ return; }
    v = v.slice(start).concat(v.slice(0, start));
  }
  var F = [], laturi = inchis ? N : N - 1;
  for(k = 0; k < laturi; k++){
    var a = v[k], b = v[(k + 1) % N], dx = b % L1 - a % L1, dy = Math.floor(b / L1) - Math.floor(a / L1);
    if(F.length && F[F.length - 1].dx === dx && F[F.length - 1].dy === dy){ F[F.length - 1].L++; }
    else { F.push({x: a % L1, y: Math.floor(a / L1), dx: dx, dy: dy, L: 1}); }
  }
  var NF = F.length;
  function prec(q){ return inchis ? (q + NF - 1) % NF : q - 1; }
  function urm(q){ return inchis ? (q + 1) % NF : (q + 1 < NF ? q + 1 : -1); }
  var sens = new Int32Array(NF), net = new Uint8Array(NF), vreuna = false;
  for(k = 0; k < NF; k++){
    if(urm(k) < 0){ continue; }
    var fa = F[k], fb = F[urm(k)];
    sens[k] = fa.dx * fb.dy - fa.dy * fb.dx;
    net[k] = u.netezit(fa.x + fa.dx * fa.L, fa.y + fa.dy * fa.L) ? 1 : 0;
    if(net[k]){ vreuna = true; }
  }
  if(!vreuna){ return; }
  function inceputFix(q){ var p = prec(q); return p < 0 || !net[p]; }
  function sfarsitFix(q){ return urm(q) < 0 || !net[q]; }
  var zc = new Uint8Array(NF), z = new Uint8Array(NF), s0 = -1, q, e, t;
  for(k = 0; k < NF; k++){
    zc[k] = (!inceputFix(k) && !sfarsitFix(k) && sens[prec(k)] !== sens[k] && F[k].L <= TTX_TREAPTA_LUNGA) ? 1 : 0;
    if(inchis && !zc[k] && s0 < 0){ s0 = k; }
  }
  if(s0 < 0){ s0 = 0; }
  for(q = 0; q < NF;){
    if(!zc[(s0 + q) % NF]){ q++; continue; }
    var lung = 0;
    for(e = q; e < NF && zc[(s0 + e) % NF]; e++){ if(F[(s0 + e) % NF].L > lung){ lung = F[(s0 + e) % NF].L; } }
    if(e - q >= 3 || (e - q === 2 && lung <= TTX_TREAPTA_SCURTA)){ for(t = q; t < e; t++){ z[(s0 + t) % NF] = 1; } }
    q = e;
  }
  var ci = new Float64Array(NF), cs = new Float64Array(NF);
  for(k = 0; k < NF; k++){
    if(z[k]){ continue; }
    var A = 0, B = 0;
    if(!inceputFix(k) && z[prec(k)]){ var pp0 = prec(prec(k)); A = ((pp0 >= 0 && z[pp0]) ? F[pp0].L : 2) * 0.5; }
    if(!sfarsitFix(k) && z[urm(k)]){ var nn0 = urm(urm(k)); B = ((nn0 >= 0 && z[nn0]) ? F[nn0].L : 2) * 0.5; }
    if(A + B > F[k].L){ var sc = F[k].L / (A + B); A *= sc; B = F[k].L - A; }
    ci[k] = A;
    cs[k] = B;
  }
  var P = [];
  function pune(f, d, fel){ P.push({gx: F[f].x + F[f].dx * d, gy: F[f].y + F[f].dy * d, fel: fel, fuga: f, capat: d >= F[f].L}); }
  if(!inchis){ pune(0, 0, 0); }
  for(k = 0; k < NF; k++){
    if(z[k]){ pune(k, F[k].L * 0.5, 2); }
    else {
      var a1 = ci[k], b1 = F[k].L - cs[k];
      if(a1 > 0){ pune(k, a1, 2); }
      if(cs[k] > 0 && b1 > a1 + 1e-9){ pune(k, b1, 2); }
    }
    if(urm(k) >= 0){
      if(!net[k]){ pune(k, F[k].L, 0); }
      else if(!z[k] && !z[urm(k)]){ pune(k, F[k].L, 1); }
    }
  }
  if(!inchis){ pune(NF - 1, F[NF - 1].L, 0); }
  function peTrepte(j1, j2){ if(P[j1].fuga === P[j2].fuga){ return true; } return P[j1].capat && P[j2].fuga === urm(P[j1].fuga); }
  // punctele coliniare din mijlocul scarilor (cel mult TTX_SIMPLIFICARE_PX de dreapta care le inlocuieste) se scot
  var M = P.length, j;
  if(M >= 4){
    var X = [], Y = [], scos = new Uint8Array(M), capete = 0;
    for(j = 0; j < M; j++){ X.push(h.px(P[j].gx)); Y.push(h.py(P[j].gy)); }
    for(j = 0; j < M; j++){
      var jp0 = inchis ? (j + M - 1) % M : j - 1, jn0 = inchis ? (j + 1) % M : j + 1;
      var poate = jp0 >= 0 && jn0 < M && P[j].fel === 2 && !peTrepte(jp0, j) && !peTrepte(j, jn0);
      scos[j] = poate ? 1 : 0;
      if(!poate){ capete++; }
    }
    if(capete){
      var st = 0;
      while(scos[st]){ st++; }
      var pastrat = new Uint8Array(M), kk = st, facuti = 0;
      pastrat[st] = 1;
      while(facuti < M){
        var bun = (kk + 1) % M, pas = 1;
        if(!inchis && kk === M - 1){ break; }
        for(var mm = 2; mm < M; mm++){
          var tt = (kk + mm) % M;
          if(!inchis && kk + mm >= M){ break; }
          if(!scos[(kk + mm - 1) % M]){ break; }
          var ax0 = X[kk], ay0 = Y[kk], bx0 = X[tt] - ax0, by0 = Y[tt] - ay0, lg = Math.sqrt(bx0 * bx0 + by0 * by0), aproape = true;
          if(lg < 1e-9){ break; }
          for(var qq = 1; qq < mm && aproape; qq++){
            var w = (kk + qq) % M, dd = ((X[w] - ax0) * by0 - (Y[w] - ay0) * bx0) / lg;
            aproape = dd < TTX_SIMPLIFICARE_PX && dd > -TTX_SIMPLIFICARE_PX;
          }
          if(!aproape){ break; }
          bun = tt;
          pas = mm;
          if(inchis && tt === st){ break; }
        }
        facuti += pas;
        kk = bun;
        if(inchis && kk === st){ break; }
        pastrat[kk] = 1;
      }
      var P2 = [];
      for(j = 0; j < M; j++){ if(pastrat[j]){ P2.push(P[j]); } }
      P = P2;
      M = P.length;
    }
  }
  // racordurile: Bezier patratic de la intrare la iesire, cu varful ca punct de control
  var px = [], py = [], inx = [], iny = [], outx = [], outy = [], arc = [];
  for(j = 0; j < M; j++){ px.push(h.px(P[j].gx)); py.push(h.py(P[j].gy)); }
  for(j = 0; j < M; j++){
    inx.push(px[j]); iny.push(py[j]); outx.push(px[j]); outy.push(py[j]); arc.push([]);
    if(P[j].fel === 0){ continue; }
    var jp = inchis ? (j + M - 1) % M : j - 1, jn = inchis ? (j + 1) % M : j + 1;
    if(jp < 0 || jn >= M){ continue; }
    var ux = px[j] - px[jp], uy = py[j] - py[jp], vx = px[jn] - px[j], vy = py[jn] - py[j];
    var l1 = Math.sqrt(ux * ux + uy * uy), l2 = Math.sqrt(vx * vx + vy * vy);
    if(l1 < 1e-9 || l2 < 1e-9){ continue; }
    ux /= l1; uy /= l1; vx /= l2; vy /= l2;
    var cosu = ux * vx + uy * vy;
    if(cosu > 1 - 1e-12){ continue; }
    if(cosu < -1){ cosu = -1; }
    var t1 = l1 * 0.5, t2 = l2 * 0.5, p1 = peTrepte(jp, j), p2 = peTrepte(j, jn);
    if(P[j].fel === 1 || p1 || p2){
      var tm = t1 < t2 ? t1 : t2;
      if(cosu > -1 + 1e-12){
        var rz = P[j].fel === 1 ? raza : 2 * raza, tc = rz * Math.sqrt((1 - cosu) / (1 + cosu));
        if(tc < tm){ tm = tc; }
      }
      t1 = tm;
      t2 = tm;
    }
    inx[j] = px[j] - ux * t1; iny[j] = py[j] - uy * t1; outx[j] = px[j] + vx * t2; outy[j] = py[j] + vy * t2;
    var mx = (inx[j] + outx[j]) * 0.5 - px[j], my = (iny[j] + outy[j]) * 0.5 - py[j];
    var n = Math.ceil(Math.sqrt(5 * Math.sqrt(mx * mx + my * my)));
    if(n < 2){ n = 2; }
    if(n > 12){ n = 12; }
    for(var s2 = 1; s2 < n; s2++){
      var qv = s2 / n, w0 = (1 - qv) * (1 - qv), w1 = 2 * qv * (1 - qv), w2 = qv * qv;
      arc[j].push(w0 * inx[j] + w1 * px[j] + w2 * outx[j], w0 * iny[j] + w1 * py[j] + w2 * outy[j]);
    }
  }
  var jc = [TTX_RGB[Lt.st][0] - TTX_RGB[Lt.dr][0], TTX_RGB[Lt.st][1] - TTX_RGB[Lt.dr][1], TTX_RGB[Lt.st][2] - TTX_RGB[Lt.dr][2]];
  // relieful: nivelurile regiunilor de o parte si de alta (ca in nucleu, NetezitorHd::lant)
  var ns = (niv && Lt.cst >= 0) ? niv[Lt.cst] : 0, nd = (niv && Lt.cdr >= 0) ? niv[Lt.cdr] : 0;
  var n1 = (ns >= 1 ? 1 : 0) - (nd >= 1 ? 1 : 0), n2 = (ns >= 2 ? 1 : 0) - (nd >= 2 ? 1 : 0);
  function capat(f){ var o = F[f]; return [h.x[o.x + o.dx * o.L], h.y[o.y + o.dy * o.L]]; }
  function emite(pts){
    var x0 = pts[0], x1 = pts[0], y0 = pts[1], y1 = pts[1];
    for(var q2 = 2; q2 < pts.length; q2 += 2){
      if(pts[q2] < x0){ x0 = pts[q2]; }
      if(pts[q2] > x1){ x1 = pts[q2]; }
      if(pts[q2 + 1] < y0){ y0 = pts[q2 + 1]; }
      if(pts[q2 + 1] > y1){ y1 = pts[q2 + 1]; }
    }
    if(x1 - x0 < 1e-9 || y1 - y0 < 1e-9){ return; }
    iesire.push({p: pts, j: jc, n1: n1, n2: n2, x0: x0, y0: y0, x1: x1, y1: y1});
  }
  function fugaComuna(j1, j2){ return P[j1].fuga === P[j2].fuga ? P[j1].fuga : P[j2].fuga; }
  if(M < 2){ return; }
  var NS = inchis ? M : M - 1, prima = -1, despartiri = 0, pts;
  for(j = 0; j < NS; j++){ if(peTrepte(j, (j + 1) % M)){ if(prima < 0){ prima = j; } despartiri++; } }
  if(prima < 0){
    if(!inchis){ return; }
    // bucla fara niciun loc comun: toata curba si toata bucla de trepte, inapoi
    pts = [];
    for(j = 0; j < M; j++){ pts.push(inx[j], iny[j]); Array.prototype.push.apply(pts, arc[j]); pts.push(outx[j], outy[j]); }
    pts.push(inx[0], iny[0]);
    pts.push(h.x[v[0] % L1], h.y[Math.floor(v[0] / L1)]);
    for(k = v.length - 1; k >= 0; k--){ pts.push(h.x[v[k] % L1], h.y[Math.floor(v[k] / L1)]); }
    emite(pts);
    return;
  }
  var ocol = inchis && despartiri === 1;
  j = (prima + 1) % M;
  var rs = fugaComuna(prima, j), Sx = inx[j], Sy = iny[j], curba = [Sx, Sy];
  var pasi = inchis ? M : M - 1 - prima;
  for(var q3 = 0; q3 < pasi; q3++, j = (j + 1) % M){
    Array.prototype.push.apply(curba, arc[j]);
    curba.push(outx[j], outy[j]);
    var ultim = !inchis && j === M - 1, k2 = (j + 1) % M;
    if(ultim || peTrepte(j, k2)){
      var re = ultim ? P[j].fuga : fugaComuna(j, k2);
      if(!(curba.length <= 4 && rs === re && !ocol)){
        var tr = [Sx, Sy];
        if(rs !== re || ocol){ var f2 = rs; do { Array.prototype.push.apply(tr, capat(f2)); f2 = urm(f2); } while(f2 !== re && f2 >= 0); }
        tr.push(outx[j], outy[j]);
        pts = curba.slice();
        for(var q4 = tr.length - 2; q4 >= 0; q4 -= 2){ pts.push(tr[q4], tr[q4 + 1]); }
        emite(pts);
      }
      if(ultim){ break; }
      Sx = inx[k2];
      Sy = iny[k2];
      rs = re;
      curba = [Sx, Sy];
    }
    else { curba.push(inx[k2], iny[k2]); }
  }
}
function ttxPrimitivaHd(s, lo, hi){
  if(s <= lo){ return 0; }
  if(s >= hi){ return (hi - lo) * (s - (lo + hi) * 0.5); }
  return (s - lo) * (s - lo) * 0.5;
}
function ttxOctetHd(v){ return v <= 0 ? 0 : (v >= 255 ? 255 : Math.floor(v + 0.5)); }
// o bucata de diferenta: aria cu semn a conturului ei, pe randuri de pixeli, apoi culoarea schimbata cu saltul x acoperirea
function ttxBucataHd(b, d, W, H, tamp){
  ttxParcurgeHd(b, W, 0, H, tamp, function(x, y, s){
    var q = (y * W + x) * 4;
    d[q] = ttxOctetHd(d[q] + b.j[0] * s);
    d[q + 1] = ttxOctetHd(d[q + 1] + b.j[1] * s);
    d[q + 2] = ttxOctetHd(d[q + 2] + b.j[2] * s);
  });
}
// relieful: aceeasi bucata pe mastile de nivel (m1 = nivel >= 1, m2 = nivel 2), cu saltul de nivel x 255, ca in nucleu
function ttxMascaHd(b, m1, m2, W, H, tamp){
  var j1 = b.n1 * 255, j2 = b.n2 * 255;
  ttxParcurgeHd(b, W, 0, H, tamp, function(x, y, s){
    var q = y * W + x;
    if(j1 !== 0){ m1[q] = ttxOctetHd(m1[q] + j1 * s); }
    if(j2 !== 0){ m2[q] = ttxOctetHd(m2[q] + j2 * s); }
  });
}
// aria cu semn a conturului bucatii, pe randurile de pixeli [Y0, Y1); aplica(x, y, acoperirea) pentru fiecare pixel atins
function ttxParcurgeHd(b, W, Y0, Y1, tamp, aplica){
  var bx0 = Math.floor(b.x0) - 1, bx1 = Math.ceil(b.x1) + 2, by0 = Math.floor(b.y0), by1 = Math.ceil(b.y1);
  if(by0 < Y0){ by0 = Y0; }
  if(by1 > Y1){ by1 = Y1; }
  if(by1 <= by0){ return; }
  var bw = bx1 - bx0 + 1, bh = by1 - by0, n = bw * bh, k, y, c;
  if(tamp.buf.length < n){ tamp.buf = new Float64Array(n); }
  var buf = tamp.buf, mn = new Int32Array(bh), mx = new Int32Array(bh);
  for(y = 0; y < bh; y++){ mn[y] = bw; mx[y] = -1; }
  var p = b.p, np = p.length / 2;
  for(k = 0; k < np; k++){
    var k1 = (k + 1) % np, x0 = p[2 * k] - bx0, y0 = p[2 * k + 1] - by0, x1 = p[2 * k1] - bx0, y1 = p[2 * k1 + 1] - by0;
    if(y0 === y1){ continue; }
    var sens = 1, tmp;
    if(y0 > y1){ tmp = x0; x0 = x1; x1 = tmp; tmp = y0; y0 = y1; y1 = tmp; sens = -1; }
    var dxdy = (x1 - x0) / (y1 - y0), ya = Math.floor(y0), yb = Math.ceil(y1);
    if(ya < 0){ ya = 0; }
    if(yb > bh){ yb = bh; }
    for(y = ya; y < yb; y++){
      var sy0 = y0 > y ? y0 : y, sy1 = y1 < y + 1 ? y1 : y + 1, dy = sy1 - sy0;
      if(dy <= 0){ continue; }
      var xa = x0 + (sy0 - y0) * dxdy, xb = x0 + (sy1 - y0) * dxdy, lo = xa < xb ? xa : xb, hi = xa < xb ? xb : xa;
      var c0 = Math.floor(lo), c1 = Math.floor(hi) + 1;
      if(c0 < 0){ c0 = 0; }
      if(c1 > bw - 1){ c1 = bw - 1; }
      var r0 = y * bw, f = sens * dy, inainte = 0, val;
      if(hi - lo < 1e-12){
        for(c = c0; c <= c1; c++){ var uu = c + 1 - lo; val = f * (uu <= 0 ? 0 : (uu >= 1 ? 1 : uu)); buf[r0 + c] += val - inainte; inainte = val; }
      }
      else {
        var kf = f / (hi - lo);
        for(c = c0; c <= c1; c++){ val = kf * (ttxPrimitivaHd(c + 1, lo, hi) - ttxPrimitivaHd(c, lo, hi)); buf[r0 + c] += val - inainte; inainte = val; }
      }
      if(c0 < mn[y]){ mn[y] = c0; }
      if(c1 > mx[y]){ mx[y] = c1; }
    }
  }
  for(y = 0; y < bh; y++){
    if(mx[y] < mn[y]){ continue; }
    var s = 0, rr = y * bw;
    for(c = mn[y]; c <= mx[y]; c++){
      s += buf[rr + c];
      buf[rr + c] = 0;
      if(s > -1 / 1024 && s < 1 / 1024){ continue; }
      var x = bx0 + c;
      if(x >= 0 && x < W){ aplica(x, by0 + y, s); }
    }
  }
}
// relieful: nivelul regiunii fiecarui sextant (2 = mozaic aprins colorat, 1 = alta culoare decat negrul, 0 = negru),
// cel mai mare din regiunea de aceeasi culoare (vecinii pe 8 directii), ca niveluriHd din nucleu
function ttxNiveluriHd(g){
  var GW = TTX_GW, GH = TTX_GH, niv = new Uint8Array(GW * GH), vazut = new Uint8Array(GW * GH), x0, y0, d;
  var VX = [1, -1, 0, 0, 1, 1, -1, -1], VY = [0, 0, 1, -1, 1, -1, 1, -1];
  for(y0 = 0; y0 < GH; y0++){
    for(x0 = 0; x0 < GW; x0++){
      if(vazut[y0 * GW + x0]){ continue; }
      var c = g.c[y0 * GW + x0], regiune = [], stiva = [y0 * GW + x0], maxim = 0;
      vazut[y0 * GW + x0] = 1;
      while(stiva.length){
        var p = stiva.pop(), x = p % GW, y = Math.floor(p / GW);
        regiune.push(p);
        var n = c === 0 ? 0 : (g.m[p] ? 2 : 1);
        if(n > maxim){ maxim = n; }
        for(d = 0; d < 8; d++){
          var xx = x + VX[d], yy = y + VY[d];
          if(xx < 0 || xx >= GW || yy < 0 || yy >= GH || vazut[yy * GW + xx] || g.c[yy * GW + xx] !== c){ continue; }
          vazut[yy * GW + xx] = 1;
          stiva.push(yy * GW + xx);
        }
      }
      for(var k = 0; k < regiune.length; k++){ niv[regiune[k]] = maxim; }
    }
  }
  return niv;
}
// Formele in relief (numai la neted), ca reliefHd din nucleu: mastile nivelurilor (sextantele, apoi bucatile netezite
// cu salturile de nivel), apoi fata laterala spre dreapta-jos pe D pixeli, in nuanta mai inchisa a culorii formei (0,70
// langa forma, 0,50 la capat), numai pe ce e mai jos si in spatele formei; aceleasi numere intregi ca in nucleu
function ttxReliefHd(g, niv, bucati, h, l, i, d, tamp){
  var W = 40 * l, H = 25 * i, D = Math.max(2, Math.floor((i + 4) / 9)), m1 = new Uint8Array(W * H), m2 = new Uint8Array(W * H);
  var gx, gy, x, y, k;
  for(gy = 0; gy < TTX_GH; gy++){
    for(y = h.y[gy]; y < h.y[gy + 1]; y++){
      for(gx = 0; gx < TTX_GW; gx++){
        var n = niv[gy * TTX_GW + gx];
        for(x = h.x[gx]; x < h.x[gx + 1]; x++){ m1[y * W + x] = n >= 1 ? 255 : 0; m2[y * W + x] = n >= 2 ? 255 : 0; }
      }
    }
  }
  for(k = 0; k < bucati.length; k++){ if(bucati[k].n1 || bucati[k].n2){ ttxMascaHd(bucati[k], m1, m2, W, H, tamp); } }
  var sx = new Int16Array(W), sy = new Int16Array(H);
  for(gx = 0; gx < TTX_GW; gx++){ for(x = h.x[gx]; x < h.x[gx + 1]; x++){ sx[x] = gx; } }
  for(gy = 0; gy < TTX_GH; gy++){ for(y = h.y[gy]; y < h.y[gy + 1]; y++){ sy[y] = gy; } }
  function sursa(L, x, y){
    for(var s = 0; s < D + 3 && x - s >= 0 && y - s >= 0; s++){
      var c = sy[y - s] * TTX_GW + sx[x - s];
      if(niv[c] >= L){ return g.c[c]; }
    }
    return -1;
  }
  function nuanta(k){ return 179 - Math.floor((k - 1) * 51 / (D - 1)); }
  for(y = 0; y < H; y++){
    var kmax = y < D ? y : D;
    if(kmax <= 0){ continue; }
    for(x = 0; x < W; x++){
      var c1 = m1[y * W + x], c2 = m2[y * W + x];
      if(c2 === 255){ continue; }
      var f1 = 0, k1 = 0, f2 = 0, k2 = 0, km = x < kmax ? x : kmax;
      for(k = 1; k <= km; k++){
        var q = (y - k) * W + (x - k);
        if(m2[q] > f2){ f2 = m2[q]; k2 = k; }
        if(m1[q] > f1){ f1 = m1[q]; k1 = k; }
      }
      var a2 = f2 > c2 ? f2 : 0, a1 = f1 > c1 ? f1 : 0, v2 = a2 ? sursa(2, x - k2, y - k2) : -1, v1 = -1;
      if(v2 < 0){ a2 = 0; }
      a1 = a1 > a2 ? a1 - a2 : 0;
      if(a1){ v1 = sursa(1, x - k1, y - k1); if(v1 < 0){ a1 = 0; } }
      if(!a2 && !a1){ continue; }
      if(v1 < 0){ v1 = v2; }
      if(v2 < 0){ v2 = v1; }
      var n2 = a2 ? nuanta(k2) : 0, n1 = a1 ? nuanta(k1) : 0, o = (y * W + x) * 4;
      for(var ch = 0; ch < 3; ch++){
        var P = d[o + ch], S2 = TTX_RGB[v2][ch], S1 = TTX_RGB[v1][ch], F2 = (S2 * n2 + 128) >> 8, F1 = (S1 * n1 + 128) >> 8;
        var L2 = c2 * S2, L1 = L2 + (c1 > c2 ? c1 - c2 : 0) * S1;
        var v = L2 * 255 + (255 - a2) * (P * 255 - L2) + a2 * (255 - c2) * F2 + a1 * ((255 - c1) * F1 - (P * 255 - L1));
        d[o + ch] = v <= 0 ? 0 : Math.min(255, Math.floor((v + 32512) / 65025));
      }
    }
  }
}
// Stratul HD: fundalurile, mozaicul legat si blocul plin, netezite, in d (RGBA, 40l x 25i), ca stratHd din nucleu.
function ttxStratHd(R, l, i, opt, d){
  var W = 40 * l, H = 25 * i, h = ttxHartaHd(l, i), g = ttxGrilaHd(R, opt), gy, gx, y, x;
  for(gy = 0; gy < TTX_GH; gy++){
    for(y = h.y[gy]; y < h.y[gy + 1]; y++){
      for(gx = 0; gx < TTX_GW; gx++){
        var rgb = TTX_RGB[g.c[gy * TTX_GW + gx]];
        for(x = h.x[gx]; x < h.x[gx + 1]; x++){ var q = (y * W + x) * 4; d[q] = rgb[0]; d[q + 1] = rgb[1]; d[q + 2] = rgb[2]; d[q + 3] = 255; }
      }
    }
  }
  var niv = opt.relief ? ttxNiveluriHd(g) : null, bucati = [], tamp = {buf: new Float64Array(0)}, k;
  if(g.aprinse){
    var u = ttxUrmaritorHd(g), L = u.lanturi(), raza = 0.5 * Math.min(l * 0.5, i / 3);
    for(k = 0; k < L.length; k++){ ttxLantHd(L[k], u, h, raza, bucati, niv); }
    for(k = 0; k < bucati.length; k++){ ttxBucataHd(bucati[k], d, W, H, tamp); }
  }
  if(opt.relief){ ttxReliefHd(g, niv, bucati, h, l, i, d, tamp); }
}
function ttxLitere(ctx, R, l, i, opt){
  ctx.font = "bold " + Math.round(i * 0.9) + "px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  var latire = Math.min(1.6, Math.max(1, l * 0.84 / Math.max(1, ctx.measureText("M").width)));
  var ud = Math.max(1, Math.floor(i / 20)), raza = Math.max(1, Math.floor(i / 12));
  for(var r = 0; r < 25; r++){
    for(var c = 0; c < 40; c++){
      var ce = R[r][c], t = ce[0];
      if((ce[3] & 63) || t === " " || t === "" || !ttxSeVede(ce, opt)){ continue; }
      if(opt.hd && t === "\u25a0" && !ce[3]){ continue; }   // HD: blocul plin e in strat, ca mozaicul
      var a = ce[4], sx = (a & A_DUBLA_LATIME) ? 2 : 1, sy = (a & A_DUBLA_INALTIME) ? 2 : 1;
      ctx.save();
      ctx.translate(c * l + l * sx / 2, r * i + i * sy / 2);
      ctx.scale(sx * latire, sy);
      ctx.fillStyle = TTX_CULORI[ce[1] & 7];
      if(opt.umbra){
        ctx.shadowColor = "rgba(0, 0, 0, 0.75)";
        ctx.shadowOffsetX = ud;
        ctx.shadowOffsetY = ud;
        ctx.shadowBlur = raza * 1.15;
        ctx.fillText(t, 0, i * 0.04);
        ctx.shadowColor = "rgba(0, 0, 0, 0)";
      }
      if(opt.contur && TTX_DESCHISA[ce[1] & 7]){   // conturul numai la literele deschise (cele negre nu se ingroasa)
        ctx.lineWidth = 2 / Math.max(sx * latire, sy);
        ctx.strokeStyle = "#000000";
        ctx.strokeText(t, 0, i * 0.04);
      }
      ctx.fillText(t, 0, i * 0.04);
      ctx.restore();
    }
  }
}
// relieful mozaicului separat (blocurile rotunjite, desenate pe canvas, nu in strat), ca reliefSeparatHd din nucleu: fata
// laterala a fiecarui bloc colorat, blocul deplasat cu (k, k), de la k = D (cel mai inchis) la k = 1, sub litere si blocuri
function ttxReliefSeparat(ctx, R, l, i, opt){
  var D = Math.max(2, Math.floor((i + 4) / 9)), r, c, k, q;
  for(r = 0; r < 25; r++){
    for(c = 0; c < 40; c++){
      var ce = R[r][c], s = ce[3] & 63;
      if(!s || (ce[4] & A_SEPARAT) === 0 || (ce[1] & 7) === 0 || !ttxSeVede(ce, opt)){ continue; }
      var w = l * ((ce[4] & A_DUBLA_LATIME) ? 2 : 1), h = i * ((ce[4] & A_DUBLA_INALTIME) ? 2 : 1), x = c * l, y = r * i;
      var xs = [0, (w + 1) >> 1, w], ys = [0, Math.floor((h + 1) / 3), Math.floor((2 * h + 1) / 3), h], rgb = TTX_RGB[ce[1] & 7];
      for(q = D; q >= 1; q--){
        var n = 179 - Math.floor((q - 1) * 51 / (D - 1));
        ctx.fillStyle = "rgb(" + ((rgb[0] * n + 128) >> 8) + "," + ((rgb[1] * n + 128) >> 8) + "," + ((rgb[2] * n + 128) >> 8) + ")";
        for(k = 0; k < 6; k++){
          if((s & (1 << k)) === 0){ continue; }
          var cx = k & 1, cy = k >> 1, bx0 = xs[cx], bx1 = xs[cx + 1], by0 = ys[cy], by1 = ys[cy + 1];
          var gx = Math.floor((bx1 - bx0) / 3), gy = Math.floor((by1 - by0) / 3);
          bx0 += gx > 0 ? gx : 1;
          by1 -= gy > 0 ? gy : 1;
          ttxRotund(ctx, x + bx0 + q, y + by0 + q, x + bx1 + q, y + by1 + q);
        }
      }
    }
  }
}
function ttxDeseneaza(cv, R, opt){
  var t0 = ttxAcum(), m = ttxMarime(cv), l = m.l, i = m.i, ctx = cv.getContext("2d"), interm = false, r, c, ce;
  opt = opt || {};
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = TTX_CULORI[0];
  ctx.fillRect(0, 0, cv.width, cv.height);
  if(R){
    if(opt.hd){
      var img = ctx.createImageData(cv.width, cv.height);
      ttxStratHd(R, l, i, opt, img.data);
      ctx.putImageData(img, 0, 0);
    }
    for(r = 0; r < 25; r++){
      for(c = 0; c < 40; c++){
        ce = R[r][c];
        if(ce[2] && !opt.hd){ ctx.fillStyle = TTX_CULORI[ce[2] & 7]; ctx.fillRect(c * l, r * i, l, i); }
        if((ce[4] & A_INTERMITENT) && ((ce[3] & 63) || ce[0] !== " ")){ interm = true; }
      }
    }
    if(opt.hd && opt.relief){ ttxReliefSeparat(ctx, R, l, i, opt); }
    ttxLitere(ctx, R, l, i, opt);
    for(r = 0; r < 25; r++){
      for(c = 0; c < 40; c++){
        ce = R[r][c];
        if((ce[3] & 63) === 0 || !ttxSeVede(ce, opt)){ continue; }
        if(opt.hd && (ce[4] & A_SEPARAT) === 0){ continue; }
        ttxBlocuri(ctx, ce, c * l, r * i, l * ((ce[4] & A_DUBLA_LATIME) ? 2 : 1), i * ((ce[4] & A_DUBLA_INALTIME) ? 2 : 1), opt.hd);
      }
    }
  }
  return {intermitente: interm, ms: ttxAcum() - t0};
}
"""

PAGINA = r"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:960px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 4px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .sus{color:var(--text-slab);font-size:.92rem;margin:0 0 12px;line-height:1.45;min-height:1.3em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:12px;margin:0 0 12px;}
  canvas.ecran{display:block;width:100%;height:auto;aspect-ratio:4/3;background:#000;border-radius:6px;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center;}
  .culori{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px;}
  label{color:var(--text-slab);}
  input,select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  input#numar{width:5.5em;font-size:1.1rem;text-align:center;}
  select{max-width:100%;}
  input#cautaCanal{flex:1 1 12em;min-width:0;}
  button,a.buton{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;}
  button:disabled{opacity:.45;cursor:default;}
  button.tinut,button.activ{border-color:var(--verde);color:var(--verde);font-weight:bold;}
  .culori button{font-weight:bold;font-size:1.05rem;color:#fff;justify-content:center;}
  .culori .rosu{background:var(--rosu);border-color:var(--rosu);}
  .culori .verde{background:var(--verde);border-color:var(--verde);}
  .culori .galben{background:var(--galben);border-color:var(--galben);color:#111;}
  .culori .albastru{background:var(--albastru);border-color:var(--albastru);}
  .pozitie{min-width:3.5em;text-align:center;color:var(--text-slab);}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.95rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:8px 0 0;line-height:1.45;}
  .rand{padding:10px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .titlu{font-size:.98rem;word-break:break-word;}
  .detalii{color:var(--text-slab);font-size:.85rem;margin-top:2px;}
  .setare{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:6px 0;}
  details{margin-top:10px;}
  summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--text-slab);}
  pre{margin:6px 0 0;padding:10px;max-width:100%;background:#0f1216;border:1px solid var(--bordura);border-radius:8px;overflow-x:auto;font-size:.8rem;line-height:1.25;}
  .ascuns{display:none;}
  @media (max-width:560px){ .card{padding:8px;} button,a.buton{padding:8px 10px;} }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="sus"><span id="serviciu"></span> <a href="#" id="spreTv" class="ascuns"></a></p>
<section class="card">
  <div class="butoane" style="margin-top:0">
    <label for="sursa">__T_SURSA__</label>
    <select id="sursa"><option value="">__T_CANAL_ACUM__</option></select>
    <button type="button" id="modClasic" aria-pressed="false">__T_CLASIC__</button>
    <button type="button" id="modHd" aria-pressed="false">__T_NETED__</button>
  </div>
  <p class="nota" id="despreSursa"></p>
  <canvas id="ecran" class="ecran" width="800" height="600" aria-label="__T_ECRAN__" style="margin-top:10px"></canvas>
  <p class="mesaj" id="mesaj">__T_CITESTE__</p>
  <div class="butoane">
    <label for="numar">__T_PAGINA__</label>
    <input id="numar" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="3" autocomplete="off" enterkeyhint="go">
    <button type="button" id="mergi">__T_MERGI__</button>
    <button type="button" id="inapoi">__T_PAG_INAPOI__</button>
    <button type="button" id="inainte">__T_PAG_INAINTE__</button>
  </div>
  <div class="butoane">
    <button type="button" id="subInapoi">__T_SUB_INAPOI__</button>
    <span class="pozitie" id="pozitie"></span>
    <button type="button" id="subInainte">__T_SUB_INAINTE__</button>
    <button type="button" id="tine">__T_TINE__</button>
  </div>
  <div class="culori">
    <button type="button" class="rosu" data-tasta="0">---</button>
    <button type="button" class="verde" data-tasta="1">---</button>
    <button type="button" class="galben" data-tasta="2">---</button>
    <button type="button" class="albastru" data-tasta="3">---</button>
  </div>
  <div class="butoane">
    <button type="button" id="arataAscuns">__T_ARATA_ASCUNS__</button>
  </div>
  <details>
    <summary>__T_TEXT_PAGINA__</summary>
    <pre id="textPagina"></pre>
  </details>
</section>
<section class="card">
  <h2>__T_COPII__</h2>
  <p class="nota" id="urmaritor"></p>
  <p class="nota" id="reimprospatare"></p>
  <div class="butoane">
    <button type="button" id="salveaza">__T_SALVEAZA__</button>
  </div>
  <div class="butoane">
    <span class="nota" style="margin:0">__T_TELETEXT_ACUM__</span>
    <a class="buton" id="acumHtml" href="#">__T_DESCARCA_PAGINA__</a>
    <a class="buton" id="acumDate" href="#">__T_DESCARCA_DATE__</a>
  </div>
  <div id="listaCopii"></div>
  <p class="nota" id="spatiu"></p>
  <p class="nota">__T_NOTA_REIMPROSPATARE__</p>
  <p class="nota">__T_NOTA_DESCARCA__</p>
  <h2 style="margin-top:14px">__T_CANALE__</h2>
  <div class="butoane">
    <input id="cautaCanal" type="search" placeholder="__T_NUME_CANAL__" autocomplete="off" aria-label="__T_CAUTA_CANAL__">
    <button type="button" id="cauta">__T_CAUTA__</button>
  </div>
  <div id="listaCanale"></div>
</section>
<section class="card">
  <h2>__T_SETARI__</h2>
  <div class="setare"><label for="setHd">__T_SET_NETED__</label><select id="setHd"><option value="1">__T_DA__</option><option value="0">__T_NU__</option></select></div>
  <div class="setare"><label for="setContur">__T_SET_CONTUR__</label><select id="setContur"><option value="1">__T_DA__</option><option value="0">__T_NU__</option></select></div>
  <div class="setare"><label for="setUmbra">__T_SET_UMBRA__</label><select id="setUmbra"><option value="1">__T_DA__</option><option value="0">__T_NU__</option></select></div>
  <div class="setare"><label for="setRelief">__T_SET_RELIEF__</label><select id="setRelief"><option value="1">__T_DA__</option><option value="0">__T_NU__</option></select></div>
  <div class="setare"><label for="setAutomata">__T_SET_AUTOMATA__</label><select id="setAutomata"><option value="1">__T_DA__</option><option value="0">__T_NU__</option></select></div>
  <div class="setare"><label for="setSpatiu">__T_SET_SPATIU__</label><select id="setSpatiu"></select></div>
  <p class="nota">__T_NOTA_NETED__</p>
  <p class="nota">__T_NOTA_OPTIUNI__</p>
  <p class="nota">__T_NOTA_AUTOMATA__</p>
  <p class="mesaj" id="mesajSetari"></p>
</section>
<p class="nota">__T_PE_TV__</p>
</main>
<script>
__DESENATOR__
var CFG = __CONFIG__;
var TXT = __TEXTE_JS__;
// %s si %d din textele traduse se inlocuiesc in ordine
function fmt(t){ var a = Array.prototype.slice.call(arguments, 1); return String(t).replace(/%[sd]/g, function(){ return a.length ? String(a.shift()) : ""; }); }
var NUME_TASTE = [TXT.rosu, TXT.verde, TXT.galben, TXT.albastru];
var DATE = null, COPII = null, CANALE = null;
var ALES = {pagina: 0, sub: -1, tinut: false, ascuns: false, copie: ""};
var HD = null;
var NR = 0, IN_LUCRU = false, FAZA = false, INTERMITENTE = false;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: fmt(TXT.neasteptat, r.status)}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function hdAles(){ return HD !== null ? HD : !!(DATE && DATE.hd); }
function arataMod(){
  var hd = hdAles();
  $("modClasic").classList.toggle("activ", hd === false);
  $("modHd").classList.toggle("activ", hd);
  $("modClasic").setAttribute("aria-pressed", hd ? "false" : "true");
  $("modHd").setAttribute("aria-pressed", hd ? "true" : "false");
}
function puneHd(v){
  HD = v;
  try { localStorage.setItem("hds-teletext-hd", v ? "1" : "0"); } catch(e){}
  arataMod();
  deseneaza();
}
try { var hdTinut = localStorage.getItem("hds-teletext-hd"); if(hdTinut === "1" || hdTinut === "0"){ HD = hdTinut === "1"; } } catch(e){}
function deseneaza(){
  var o = (DATE && DATE.optiuni) || {};
  var r = ttxDeseneaza($("ecran"), DATE ? DATE.randuri : null, {hd: hdAles(), contur: !!o.contur, umbra: !!o.umbra, relief: !!o.relief, faza: FAZA, ascuns: ALES.ascuns});
  INTERMITENTE = r.intermitente;
  window.TTX_MS = r.ms;
}
function arata(d){
  DATE = d;
  ALES.pagina = d.pagina;
  if(ALES.tinut){
    if(d.subcod >= 0){ ALES.sub = d.subcod; } else { ALES.tinut = false; ALES.sub = -1; }
  }
  $("serviciu").textContent = d.copie ? fmt(TXT.copia, d.copie.nume || d.copie.ref, d.copie.data_text) : (d.nume || "");
  var tv = $("spreTv");
  if(d.televizor){ tv.textContent = fmt(TXT.pe_tv, d.televizor); tv.classList.remove("ascuns"); }
  else { tv.textContent = ""; tv.classList.add("ascuns"); }
  if(document.activeElement !== $("numar")){ $("numar").value = String(d.pagina); }
  mesaj(d.mesaj, false);
  var s = d.subpagini || [];
  $("subInapoi").disabled = s.length < 2;
  $("subInainte").disabled = s.length < 2;
  $("tine").disabled = d.subcod < 0 && ALES.tinut === false;
  $("tine").textContent = ALES.tinut ? TXT.lasa : TXT.tine;
  $("tine").classList.toggle("tinut", ALES.tinut);
  var poz = d.pozitie || "";
  if(ALES.tinut){ poz = poz ? poz + ", " + TXT.tinuta : TXT.tinuta; }
  $("pozitie").textContent = poz;
  var tinte = (d.taste && d.taste.tinte) || [0, 0, 0, 0];
  Array.prototype.forEach.call(document.querySelectorAll("button[data-tasta]"), function(b){
    var k = parseInt(b.getAttribute("data-tasta"), 10), p = tinte[k] || 0;
    b.textContent = p ? String(p) : "---";
    b.disabled = p === 0;
    b.setAttribute("aria-label", p ? fmt(TXT.tasta_pagina, NUME_TASTE[k], p) : fmt(TXT.tasta_fara, NUME_TASTE[k]));
  });
  $("arataAscuns").textContent = ALES.ascuns ? TXT.ascunde : TXT.arata_ascuns;
  $("arataAscuns").disabled = d.are_ascuns === false && ALES.ascuns === false;
  $("textPagina").textContent = (d.text || []).join("\n");
  arataMod();
  deseneaza();
}
function citeste(din_ceas){
  if(din_ceas && (IN_LUCRU || document.hidden || ALES.copie)){ return; }
  var q = [];
  if(ALES.pagina){ q.push("pagina=" + ALES.pagina); }
  if(ALES.tinut && ALES.sub >= 0){ q.push("sub=" + ALES.sub); }
  if(ALES.ascuns){ q.push("ascuns=1"); }
  if(ALES.copie){ q.push("copie=" + encodeURIComponent(ALES.copie)); }
  var nr = ++NR;
  IN_LUCRU = true;
  return cerere("/api/teletext" + (q.length ? "?" + q.join("&") : "")).then(function(d){
    if(nr !== NR){ return; }
    IN_LUCRU = false;
    if(!d.result){
      mesaj(d.message || TXT.necitit, true);
      if(ALES.copie){ ALES.copie = ""; ALES.pagina = 0; $("sursa").value = ""; }
      return;
    }
    arata(d);
  }).catch(function(){
    if(nr !== NR){ return; }
    IN_LUCRU = false;
    mesaj(TXT.nu_raspunde_retea, true);
  });
}
function mergiLa(p){
  var t = String(p === undefined || p === null ? "" : p).trim();
  if(/^[1-8][0-9][0-9]$/.test(t) === false){ mesaj(TXT.numar, true); return; }
  ALES.pagina = parseInt(t, 10);
  ALES.sub = -1;
  ALES.tinut = false;
  $("numar").value = t;
  citeste(false);
}
function subpagina(pas){
  if(!DATE){ return; }
  var s = DATE.subpagini || [];
  if(s.length < 2){ return; }
  var k = s.indexOf(DATE.subcod);
  if(k < 0){ k = 0; }
  ALES.sub = s[(k + pas + s.length) % s.length];
  ALES.tinut = true;
  citeste(false);
}
function tine(){
  if(!DATE){ return; }
  if(ALES.tinut){ ALES.tinut = false; ALES.sub = -1; }
  else if(DATE.subcod >= 0){ ALES.tinut = true; ALES.sub = DATE.subcod; }
  citeste(false);
}
function alegeSursa(ref){
  ALES.copie = ref || "";
  ALES.pagina = 0;
  ALES.sub = -1;
  ALES.tinut = false;
  $("sursa").value = ALES.copie;
  $("despreSursa").textContent = ALES.copie ? TXT.din_copie : "";
  citeste(false);
}
// ---------------------------------------------------------------- copiile
function marime(o){
  if(o >= 1048576){ return (o / 1048576).toFixed(1).replace(".", ",") + " MB"; }
  return Math.max(1, Math.round(o / 1024)) + " KB";
}
function legatura(ref, fel){
  return adresa("/api/teletext-descarca?" + (ref ? "ref=" + encodeURIComponent(ref) + "&" : "") + "fel=" + fel);
}
function numeCanal(ref){
  var i;
  for(i = 0; COPII && i < COPII.copii.length; i++){ if(COPII.copii[i].ref === ref){ return COPII.copii[i].nume || ref; } }
  for(i = 0; CANALE && i < CANALE.length; i++){ if(CANALE[i][0] === ref){ return CANALE[i][1] || ref; } }
  return ref;
}
function buton(text, fa){ var b = document.createElement("button"); b.type = "button"; b.textContent = text; b.addEventListener("click", fa); return b; }
function legaturaButon(text, href){ var a = document.createElement("a"); a.className = "buton"; a.textContent = text; a.href = href; return a; }
function trimite(cale, valori, unde){
  var q = new URLSearchParams();
  Object.keys(valori || {}).forEach(function(k){ q.set(k, valori[k]); });
  var m = unde || $("reimprospatare");
  m.textContent = TXT.se_trimite;
  return cerere(cale, "POST", q).then(function(d){
    m.textContent = d.message || "";
    m.classList.toggle("eroare", !d.result);
    if(d.copii !== undefined){ arataCopii(d); }
    return d;
  }).catch(function(){ m.textContent = TXT.nu_raspunde; m.classList.add("eroare"); });
}
function arataCopii(d){
  if(!d || !d.result || !d.copii){ return; }
  COPII = d;
  var sel = $("sursa");
  if(document.activeElement !== sel){
    sel.textContent = "";
    var o = document.createElement("option"); o.value = ""; o.textContent = TXT.canal_acum; sel.appendChild(o);
    d.copii.forEach(function(c){
      var e = document.createElement("option"); e.value = c.ref; e.textContent = (c.nume || c.ref) + ", " + c.data_text; sel.appendChild(e);
    });
    sel.value = ALES.copie;
  }
  var l = $("listaCopii");
  l.textContent = "";
  if(!d.copii.length){
    var p = document.createElement("p"); p.className = "nota"; p.textContent = TXT.nicio_copie; l.appendChild(p);
  }
  d.copii.forEach(function(c){
    var r = document.createElement("div"); r.className = "rand";
    var t = document.createElement("div"); t.className = "titlu"; t.textContent = c.nume || c.ref;
    var det = document.createElement("div"); det.className = "detalii";
    det.textContent = c.data_text + ", " + fmt(TXT.pagini, c.pagini) + ", " + marime(c.octeti);
    var b = document.createElement("div"); b.className = "butoane";
    b.appendChild(buton(TXT.deschide, function(){ alegeSursa(c.ref); window.scrollTo(0, 0); }));
    b.appendChild(legaturaButon(TXT.descarca_pagina, legatura(c.ref, "html")));
    b.appendChild(legaturaButon(TXT.descarca_date, legatura(c.ref, "date")));
    b.appendChild(buton(TXT.reimprospateaza, function(){ trimite("/api/teletext-reimprospateaza", {ref: c.ref}); }));
    b.appendChild(buton(TXT.sterge, function(){
      if(window.confirm(fmt(TXT.intreaba_sterge, c.nume || c.ref))){
        if(ALES.copie === c.ref){ alegeSursa(""); }
        trimite("/api/teletext-sterge", {ref: c.ref});
      }
    }));
    r.appendChild(t); r.appendChild(det); r.appendChild(b); l.appendChild(r);
  });
  $("spatiu").textContent = fmt(TXT.spatiu, marime(d.spatiu_folosit), d.spatiu_ales_mb, d.dosar);
  var u = d.urmaritor;
  if(!u){ $("urmaritor").textContent = TXT.urmaritor_oprit; }
  else if(!u.ref){ $("urmaritor").textContent = ""; }
  else if(u.complet){ $("urmaritor").textContent = fmt(TXT.carusel_complet, u.nume || u.ref, u.subpagini); }
  else { $("urmaritor").textContent = fmt(TXT.se_strang, u.nume || u.ref, u.subpagini, u.secunde); }
  var ri = u && u.reimprospatare, rt = $("reimprospatare");
  if(ri && !ri.gata){ rt.textContent = fmt(TXT.se_reimprospateaza, numeCanal(ri.ref)); rt.classList.remove("eroare"); }
  else if(ri && ri.rezultat){
    rt.textContent = ri.rezultat.ok ? fmt(TXT.la_zi, numeCanal(ri.ref)) : (numeCanal(ri.ref) + ": " + (ri.rezultat.text || TXT.nereimprospatata));
    rt.classList.toggle("eroare", !ri.rezultat.ok);
  }
  var s = d.setari;
  if(s){
    if(document.activeElement !== $("setHd")){ $("setHd").value = s.hd ? "1" : "0"; }
    [["setContur", "contur"], ["setUmbra", "umbra"], ["setRelief", "relief"]].forEach(function(p){
      if(document.activeElement !== $(p[0])){ $(p[0]).value = s[p[1]] ? "1" : "0"; }
    });
    if(document.activeElement !== $("setAutomata")){ $("setAutomata").value = s.copie_automata ? "1" : "0"; }
    var sp = $("setSpatiu");
    if(document.activeElement !== sp){
      sp.textContent = "";
      (s.spatii || []).forEach(function(v){ var e = document.createElement("option"); e.value = v; e.textContent = v + " MB"; sp.appendChild(e); });
      sp.value = s.spatiu;
    }
    ["setHd", "setContur", "setUmbra", "setRelief", "setAutomata", "setSpatiu"].forEach(function(id){ $(id).disabled = !s.pot_schimba; });
  }
  arataCanale();
}
function citesteCopii(cu_canale){
  if(document.hidden && !cu_canale){ return; }
  return cerere("/api/teletext-copii" + (cu_canale ? "?canale=1" : "")).then(function(d){
    if(cu_canale && d && d.canale_cu_teletext){ CANALE = d.canale_cu_teletext; }
    arataCopii(d);
  }).catch(function(){});
}
function faraSemne(t){ return (t || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }
function arataCanale(){
  var l = $("listaCanale");
  if(!CANALE){ return; }
  l.textContent = "";
  var cauta = faraSemne($("cautaCanal").value.trim()), gasite = [];
  CANALE.forEach(function(c){ if(!cauta || faraSemne(c[1]).indexOf(cauta) !== -1){ gasite.push(c); } });
  if(!gasite.length){ var p = document.createElement("p"); p.className = "nota"; p.textContent = TXT.niciun_canal; l.appendChild(p); return; }
  gasite.slice(0, 30).forEach(function(c){
    var r = document.createElement("div"); r.className = "rand";
    var t = document.createElement("div"); t.className = "titlu"; t.textContent = c[1] || c[0];
    var areCopie = COPII && COPII.copii.some(function(x){ return x.ref === c[0]; });
    var det = document.createElement("div"); det.className = "detalii"; det.textContent = areCopie ? TXT.are_copie : TXT.fara_copie;
    var b = document.createElement("div"); b.className = "butoane";
    b.appendChild(buton(TXT.reimprospateaza, function(){ trimite("/api/teletext-reimprospateaza", {ref: c[0]}); }));
    r.appendChild(t); r.appendChild(det); r.appendChild(b); l.appendChild(r);
  });
  if(gasite.length > 30){ var n = document.createElement("p"); n.className = "nota"; n.textContent = fmt(TXT.inca_canale, gasite.length - 30); l.appendChild(n); }
}
function seteaza(cheie, valoare){
  var v = {}; v[cheie] = valoare;
  trimite("/api/teletext-setari", v, $("mesajSetari")).then(function(d){
    // pagina se redeseneaza cu setarea noua: felul (daca nu e ales altfel aici) si optiunile
    if(d && d.result && ((cheie === "hd" && HD === null) || ["contur", "umbra", "relief"].indexOf(cheie) !== -1)){ citeste(false); }
  });
}
$("numar").addEventListener("keydown", function(e){
  if(e.key === "Enter"){ e.preventDefault(); mergiLa($("numar").value); }
});
$("mergi").addEventListener("click", function(){ mergiLa($("numar").value); });
$("inapoi").addEventListener("click", function(){ if(DATE){ mergiLa(DATE.vecine[0]); } });
$("inainte").addEventListener("click", function(){ if(DATE){ mergiLa(DATE.vecine[1]); } });
$("subInapoi").addEventListener("click", function(){ subpagina(-1); });
$("subInainte").addEventListener("click", function(){ subpagina(1); });
$("tine").addEventListener("click", tine);
Array.prototype.forEach.call(document.querySelectorAll("button[data-tasta]"), function(b){
  b.addEventListener("click", function(){
    var p = DATE && DATE.taste ? DATE.taste.tinte[parseInt(b.getAttribute("data-tasta"), 10)] : 0;
    if(p){ mergiLa(p); }
  });
});
$("arataAscuns").addEventListener("click", function(){ ALES.ascuns = !ALES.ascuns; citeste(false); });
$("spreTv").addEventListener("click", function(e){ e.preventDefault(); if(DATE && DATE.televizor){ mergiLa(DATE.televizor); } });
$("sursa").addEventListener("change", function(){ alegeSursa($("sursa").value); });
$("modClasic").addEventListener("click", function(){ puneHd(false); });
$("modHd").addEventListener("click", function(){ puneHd(true); });
$("salveaza").addEventListener("click", function(){ trimite("/api/teletext-salveaza", {}); });
$("acumHtml").href = legatura("", "html");
$("acumDate").href = legatura("", "date");
$("cauta").addEventListener("click", function(){ if(CANALE){ arataCanale(); } else { citesteCopii(true); } });
$("cautaCanal").addEventListener("keydown", function(e){ if(e.key === "Enter"){ e.preventDefault(); $("cauta").click(); } });
$("setHd").addEventListener("change", function(){ seteaza("hd", $("setHd").value); });
$("setContur").addEventListener("change", function(){ seteaza("contur", $("setContur").value); });
$("setUmbra").addEventListener("change", function(){ seteaza("umbra", $("setUmbra").value); });
$("setRelief").addEventListener("change", function(){ seteaza("relief", $("setRelief").value); });
$("setAutomata").addEventListener("change", function(){ seteaza("copie_automata", $("setAutomata").value); });
$("setSpatiu").addEventListener("change", function(){ seteaza("spatiu", $("setSpatiu").value); });
window.addEventListener("resize", deseneaza);
setInterval(function(){ citeste(true); }, 2000);
setInterval(function(){ citesteCopii(false); }, 5000);
setInterval(function(){ if(INTERMITENTE){ FAZA = !FAZA; deseneaza(); } else { FAZA = false; } }, 500);
arataMod();
deseneaza();
citeste(false);
citesteCopii(false);
</script>
</body>
</html>
"""

# Pagina descarcata: un singur fisier, fara receptor si fara retea. DATE = {nume, data_text, sursa, initiala, hd,
# optiuni: {contur, umbra, relief}, pagini: {"100": [[text, fugi, tinte, subcod], ...]}}; desenatorul e acelasi ca in
# /teletext, cu setarile receptorului din momentul descarcarii.
PAGINA_DESCARCATA = r"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLU__</title>
<style>
  :root{--fundal:#14171c;--panou:#1c2129;--text:#e6e9ef;--text-slab:#8891a0;--verde:#2f8f5b;--rosu:#c0392b;--galben:#c9a227;--albastru:#2f6fa8;--bordura:#2a2f38;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--fundal);color:var(--text);font-family:system-ui,Segoe UI,Roboto,sans-serif;padding:16px;}
  main{max-width:960px;margin:0 auto;}
  h1{font-size:1.15rem;margin:0 0 12px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:12px;}
  canvas.ecran{display:block;width:100%;height:auto;aspect-ratio:4/3;background:#000;border-radius:6px;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center;}
  .culori{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px;}
  label{color:var(--text-slab);}
  input{min-height:44px;width:5.5em;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;font-size:1.1rem;text-align:center;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button:disabled{opacity:.45;cursor:default;}
  button.activ{border-color:var(--verde);color:var(--verde);font-weight:bold;}
  .culori button{font-weight:bold;font-size:1.05rem;color:#fff;}
  .culori .rosu{background:var(--rosu);border-color:var(--rosu);}
  .culori .verde{background:var(--verde);border-color:var(--verde);}
  .culori .galben{background:var(--galben);border-color:var(--galben);color:#111;}
  .culori .albastru{background:var(--albastru);border-color:var(--albastru);}
  .pozitie{min-width:3.5em;text-align:center;color:var(--text-slab);}
  .mesaj{margin:10px 0 0;line-height:1.45;min-height:1.3em;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:10px 0 0;line-height:1.45;}
  @media (max-width:560px){ .card{padding:8px;} button{padding:8px 10px;} }
</style>
</head>
<body>
<main>
<h1>__TITLU__</h1>
<section class="card">
  <div class="butoane" style="margin-top:0">
    <button type="button" id="modClasic" aria-pressed="false">__T_CLASIC__</button>
    <button type="button" id="modHd" aria-pressed="false">__T_NETED__</button>
  </div>
  <canvas id="ecran" class="ecran" width="800" height="600" aria-label="__T_ECRAN__" style="margin-top:10px"></canvas>
  <p class="mesaj" id="mesaj"></p>
  <div class="butoane">
    <label for="numar">__T_PAGINA__</label>
    <input id="numar" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="3" autocomplete="off" enterkeyhint="go">
    <button type="button" id="mergi">__T_MERGI__</button>
    <button type="button" id="inapoi">__T_PAG_INAPOI__</button>
    <button type="button" id="inainte">__T_PAG_INAINTE__</button>
  </div>
  <div class="butoane">
    <button type="button" id="subInapoi">__T_SUB_INAPOI__</button>
    <span class="pozitie" id="pozitie"></span>
    <button type="button" id="subInainte">__T_SUB_INAINTE__</button>
  </div>
  <div class="culori">
    <button type="button" class="rosu" data-tasta="0">---</button>
    <button type="button" class="verde" data-tasta="1">---</button>
    <button type="button" class="galben" data-tasta="2">---</button>
    <button type="button" class="albastru" data-tasta="3">---</button>
  </div>
  <div class="butoane">
    <button type="button" id="arataAscuns">__T_ARATA_ASCUNS__</button>
  </div>
</section>
<p class="nota">__T_NOTA_DESCARCATA__</p>
</main>
<script>
__DESENATOR__
var TXT = __TEXTE_JS__;
// %s si %d din textele traduse se inlocuiesc in ordine
function fmt(t){ var a = Array.prototype.slice.call(arguments, 1); return String(t).replace(/%[sd]/g, function(){ return a.length ? String(a.shift()) : ""; }); }
var DATE = __DATE__;
var NUMERE = Object.keys(DATE.pagini).map(function(x){ return parseInt(x, 10); }).sort(function(a, b){ return a - b; });
var ALES = {pagina: 0, k: 0, ascuns: false};
var HD = null, FAZA = false, INTERMITENTE = false, RANDURI = null;
function $(id){ return document.getElementById(id); }
try { var hdTinut = localStorage.getItem("hds-teletext-hd"); if(hdTinut === "1" || hdTinut === "0"){ HD = hdTinut === "1"; } } catch(e){}
function hdAles(){ return HD !== null ? HD : !!DATE.hd; }
function decodeaza(sp){
  var litere = Array.from(sp[0]), fugi = sp[1], randuri = [], rand = [], i = 0;
  for(var j = 0; j < fugi.length; j += 5){
    for(var n = 0; n < fugi[j]; n++){
      var t = litere[i] || " ";
      rand.push([t, fugi[j + 1], fugi[j + 2], fugi[j + 3], fugi[j + 4]]);
      i++;
      if(rand.length === 40){ randuri.push(rand); rand = []; }
    }
  }
  while(randuri.length < 25){ var gol = []; for(var c = 0; c < 40; c++){ gol.push([" ", 7, 0, 0, 0]); } randuri.push(gol); }
  return randuri;
}
function areAscuns(R){
  for(var r = 0; r < 25; r++){ for(var c = 0; c < 40; c++){ var ce = R[r][c]; if((ce[4] & A_ASCUNS) && ((ce[3] & 63) || ce[0] !== " ")){ return true; } } }
  return false;
}
function deseneaza(){
  var o = DATE.optiuni || {};
  var r = ttxDeseneaza($("ecran"), RANDURI, {hd: hdAles(), contur: !!o.contur, umbra: !!o.umbra, relief: !!o.relief, faza: FAZA, ascuns: ALES.ascuns});
  INTERMITENTE = r.intermitente;
  window.TTX_MS = r.ms;
}
function arata(){
  var lista = DATE.pagini[String(ALES.pagina)] || null;
  $("numar").value = String(ALES.pagina);
  if(lista === null){
    RANDURI = null;
    $("mesaj").textContent = fmt(TXT.lipsa_copie, ALES.pagina) + ".";
    $("pozitie").textContent = "";
    $("subInapoi").disabled = true;
    $("subInainte").disabled = true;
    $("arataAscuns").disabled = true;
  } else {
    if(ALES.k >= lista.length){ ALES.k = 0; }
    var sp = lista[ALES.k];
    RANDURI = decodeaza(sp);
    $("mesaj").textContent = "";
    $("pozitie").textContent = lista.length > 1 ? (ALES.k + 1) + "/" + lista.length : "";
    $("subInapoi").disabled = lista.length < 2;
    $("subInainte").disabled = lista.length < 2;
    $("arataAscuns").disabled = areAscuns(RANDURI) === false;
    var tinte = sp[2] || [0, 0, 0, 0];
    Array.prototype.forEach.call(document.querySelectorAll("button[data-tasta]"), function(b){
      var p = tinte[parseInt(b.getAttribute("data-tasta"), 10)] || 0;
      b.textContent = p ? String(p) : "---";
      b.disabled = p === 0;
    });
  }
  $("arataAscuns").textContent = ALES.ascuns ? TXT.ascunde : TXT.arata_ascuns;
  $("modClasic").classList.toggle("activ", hdAles() === false);
  $("modHd").classList.toggle("activ", hdAles());
  $("modClasic").setAttribute("aria-pressed", hdAles() ? "false" : "true");
  $("modHd").setAttribute("aria-pressed", hdAles() ? "true" : "false");
  deseneaza();
}
function mergiLa(p){
  var t = String(p).trim();
  if(/^[1-8][0-9][0-9]$/.test(t) === false){ $("mesaj").textContent = TXT.numar; return; }
  ALES.pagina = parseInt(t, 10);
  ALES.k = 0;
  arata();
}
function vecina(pas){
  if(!NUMERE.length){ return; }
  var p = ALES.pagina, alese;
  if(pas > 0){ alese = NUMERE.filter(function(x){ return x > p; }); mergiLa(alese.length ? alese[0] : NUMERE[0]); }
  else { alese = NUMERE.filter(function(x){ return x < p; }); mergiLa(alese.length ? alese[alese.length - 1] : NUMERE[NUMERE.length - 1]); }
}
function subpagina(pas){
  var lista = DATE.pagini[String(ALES.pagina)] || [];
  if(lista.length < 2){ return; }
  ALES.k = (ALES.k + pas + lista.length) % lista.length;
  arata();
}
function puneHd(v){
  HD = v;
  try { localStorage.setItem("hds-teletext-hd", v ? "1" : "0"); } catch(e){}
  arata();
}
$("numar").addEventListener("keydown", function(e){ if(e.key === "Enter"){ e.preventDefault(); mergiLa($("numar").value); } });
$("mergi").addEventListener("click", function(){ mergiLa($("numar").value); });
$("inapoi").addEventListener("click", function(){ vecina(-1); });
$("inainte").addEventListener("click", function(){ vecina(1); });
$("subInapoi").addEventListener("click", function(){ subpagina(-1); });
$("subInainte").addEventListener("click", function(){ subpagina(1); });
$("arataAscuns").addEventListener("click", function(){ ALES.ascuns = !ALES.ascuns; arata(); });
$("modClasic").addEventListener("click", function(){ puneHd(false); });
$("modHd").addEventListener("click", function(){ puneHd(true); });
Array.prototype.forEach.call(document.querySelectorAll("button[data-tasta]"), function(b){
  b.addEventListener("click", function(){
    var lista = DATE.pagini[String(ALES.pagina)];
    var p = lista ? (lista[ALES.k][2] || [])[parseInt(b.getAttribute("data-tasta"), 10)] : 0;
    if(p){ mergiLa(p); }
  });
});
document.addEventListener("keydown", function(e){
  if(e.target && e.target.tagName === "INPUT"){ return; }
  if(e.key === "ArrowUp"){ e.preventDefault(); vecina(1); }
  else if(e.key === "ArrowDown"){ e.preventDefault(); vecina(-1); }
  else if(e.key === "ArrowRight"){ e.preventDefault(); subpagina(1); }
  else if(e.key === "ArrowLeft"){ e.preventDefault(); subpagina(-1); }
});
window.addEventListener("resize", deseneaza);
setInterval(function(){ if(INTERMITENTE){ FAZA = !FAZA; deseneaza(); } else { FAZA = false; } }, 500);
ALES.pagina = DATE.pagini[String(DATE.initiala)] ? DATE.initiala : (NUMERE.length ? NUMERE[0] : DATE.initiala);
arata();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
	),
	"js": (
		N_("browser deconectat"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
