# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# cadru_web.py: cadrul comun al paginilor interfetei web (HdsWebControl): antetul, meniul pe grupe, temele si culorile.
#
# UN SINGUR LOC. Paginile nu se schimba: _CerereHds.render (plugin.py) trece raspunsul fiecarei cereri prin
# imbracaRaspuns(). Se imbraca numai o pagina HTML intreaga (raspuns 200, text/html, fara Content-Disposition, care
# incepe cu <!DOCTYPE html>), ceruta cu GET de un browser care a trecut poarta (_verificaAcces: reteaua locala, apoi
# ?token= sau cookie-ul browserului asociat, sau browserul „liber” din casa cand codul nu se cere). Nu se ating: /api,
# rutele aplicatiilor de telefon, pagina de asociere, pagina de paza a modelului, raspunsurile NOT_DONE_YET (scrise pe
# bucati), JSON, imaginile, 403/401. O eroare aici lasa pagina neimbracata, ca inainte (jurnal, cel mult o data pe minut).
#
# ANTETUL: „HD Satelit” (duce la panou), calea (unde esti, numele de pe televizor), numele receptorului in retea si
# versiunea imaginii, starea pe scurt (canalul sau standby, din /api/statusinfo, o data la 15 s, oprita cat fila e
# ascunsa; pe panou o trimite chiar panoul, prin window.HDS_ANTET), ceasul si butonul Meniu.
#
# MENIUL PE GRUPE se face la rulare din data/menu.xml (meniu_web.arbore: aceleasi reguli ca televizorul, level=,
# requires=, weight=, numele traduse si semnele „(în lucru)” / „(netestat)”). La fiecare intrare: pagina ei (web=),
# pagina de setari (<setup id> -> /setari?id=), altfel, daca ecranul se poate deschide din web, legatura spre /meniu
# cu semnul TV (acolo e „Deschide pe televizor”); intrarile care nu se deschid din web (cod, oprire, repornire) nu se
# arata, iar o grupa fara nimic de aratat nu se arata deloc (ele raman in /meniu, cu motivul). In plus fata de
# televizor: grupa „Principal” (paginile tastelor telecomenzii: canale, ghid, radio, film, sunet, teletext, cautare),
# fiecare numai cand ruta ei exista, si la sfarsit „Alte pagini”: legaturile din registrul paginilor web
# (plugin._REGISTRU_PAGINI, fostul subsol „Toate paginile” al panoului, scos din pagina in 0.3.0; pe un plugin.py mai
# vechi, subsolul panoului) care nu sunt nici in menu.xml, nici in „Principal”.
#
# TEMELE (facute EXACT dupa ecranele Google Stitch aprobate: Pro si Clasic, cu valorile masurate din codul lor). Din
# Stitch se ia designul (culori,
# materiale, butoane, carduri, meniu, campuri, tabele, colturi, umbre, distante); a noastra raman geometria paginilor
# (locul si forma elementelor) si functiile.
# - Pro: densa; bara laterala mereu deschisa pe ecranele late (sigla in patrat, grupele cu MAJUSCULE mici, intrarea
#   aleasa plina, albastra), antetul de sticla cu numele receptorului, pastila starii si ceasul, cardurile de sticla cu
#   umbra si titlul cu linie dedesubt, butoanele mici cu colturi de 8 px, butonul principal albastru.
# - Clasic: ca meniul de pe televizor: fundal plin, „HD SATELIT | Meniu › ...” sus si butonul mare „Meniu” (meniul e un
#   sertar), titlul mare si subtire cu linie chihlimbarie pe toata latimea, randurile pline cu 3 px intre ele, randul
#   ales mai deschis cu text crem si bara chihlimbarie de 6 px, butoanele mari.
# - Pe telefon (ambele teme, ca in ecranele Stitch de telefon): bara de jos Telecomanda (panoul), Canale, Ghid TV,
#   Radio, Mai mult (deschide meniul), fiecare numai cand ruta exista.
# Fontul e al skinului (HdsRegular, HdsBold, HdsCond; Open Sans, OFL) in locul celor din Stitch (Plus Jakarta Sans,
# Outfit), servit de /cadru/<nume>.ttf; iconitele sunt SVG in pagina, desenate aici. Nimic de pe internet.
#
# CULORILE (alegerea de culori in web, independenta de televizor): „Ca pe televizor” (implicit) =
# blocul <colors> al skinului HDSatelit (skin.xml), pe care panoul skinului il rescrie la alegerea paletei; sau oricare
# din paletele de pe televizor (palete.txt din pluginul HdsSkinSetari, citit din fisierul instalat al skinului, cu
# derivarea lui, paleta.py). Alegerea din web NU scrie nimic in skin si nici in alegerea de pe televizor.
# Contrastul WCAG AA (4,5:1; 7:1 pentru textul de baza) se calculeaza si se impune la fiecare pereche text / fundal
# (PERECHI), pe orice paleta, inchisa sau luminoasa.
#
# ALEGEREA: in /setari, caseta „Aspectul interfeței web” (setari_web.py). Implicitele (tema si culorile) se tin pe
# receptor (config.plugins.hdswebcontrol.tema_web si culori_web, facute aici la nevoie); fiecare browser poate alege
# altceva (cookie-urile hds_tema si hds_culori), care au intaietate. Tema web si tema skinului de pe televizor sunt
# setari INDEPENDENTE.
#
# TEXTUL DE UN RAND CARE NU INCAPE (clasa hds-derulant: antetul, capul meniului, paginile) nu se taie cu "...": se
# deruleaza, ca pe televizor (SCRIPT_DERULANT si stilul lui: 2 s pe loc, 40 px/s spre stanga pana se vede capatul,
# 2 s, inapoi la inceput). Textul care incape nu se atinge. In liste, clasa hds-derulant-rand pe rand: se misca numai
# randul ales (.ales, aria-current, aria-selected), cel cu mouse-ul sau cu focusul; celelalte arata inceputul, taiat
# curat. Cu prefers-reduced-motion textul sta, taiat curat.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il incarca fara receptor.

import json
import os
import re
import time

TEME = ("clasic", "pro")
TEMA_IMPLICITA = "clasic"
COOKIE_TEMA = "hds_tema"
COOKIE_CULORI = "hds_culori"
CULORI_TV = "tv"            # „Ca pe televizor”: blocul <colors> al skinului
CULORI_SKIN = "implicit"    # paleta implicita a skinului (HD Satelit), ca pe televizor
_RE_ID_PALETA = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

# probele pun aici skin.xml, /etc/image-version si palete.txt
CALE_SKIN = None
CALE_VERSIUNE = "/etc/image-version"
CALE_PALETE = None
DOSAR_SKIN_SETARI = "/usr/lib/enigma2/python/Plugins/Extensions/HdsSkinSetari"

# fonturile skinului (data/fonts/Makefile.am le pune in /usr/share/fonts; pachetul skinului si in HDSatelit/fonts)
FONTURI = ("HdsRegular.ttf", "HdsBold.ttf", "HdsCond.ttf")
DOSARE_FONTURI = ("/usr/share/fonts", "/usr/share/enigma2/HDSatelit/fonts")

# culorile implicite ale skinului HDSatelit (blocul <colors> din HDSatelit/skin.xml, fara alfa), pentru receptorul fara
# skin sau cu skin.xml necitit
CULORI_IMPLICITE = {
	"hdsPanelSolid": "#10162a",
	"hdsText": "#f2f4f8",
	"hdsText2": "#c9d2e3",
	"hdsLabel": "#aeb9cc",
	"hdsBrand": "#374ea1",
	"hdsBrandLight": "#9fb4ff",
	"hdsAmber": "#f5b83d",
	"hdsGood": "#4fd18b",
	"hdsWarn": "#f1c40f",
	"hdsBad": "#ff6b5e",
	"hdsTrack": "#2a3350",
	"hdsCell": "#282d3f",
	"hdsCellNow": "#404555",
	"hdsDisabled": "#667085",
	"key_red": "#e5484d",
	"key_green": "#46b06a",
	"key_yellow": "#e8b93a",
	"key_blue": "#3d7be0",
}

# textul inchis pe butonul galben al paginilor (.b-galben{color:#241d00} in panou)
TEXT_PE_GALBEN = "#241d00"
ALB = "#ffffff"
NEGRU = "#000000"
PRAG_TEXT = 4.5      # WCAG 2.x AA, text obisnuit
PRAG_TEXT_MARE = 7.0  # textul de baza: ca skinul (paleta.py cere 7 pentru hdsText)
PRAG_CHENAR = 3.0    # WCAG 1.4.11, linii si chenare care spun ceva (linia titlului, pagina curenta)

# Perechile verificate (text, fundal, prag) pentru fiecare tema; aceleasi si in probe (test_web_meniu_teme_contrast).
# „#ffffff” si TEXT_PE_GALBEN sunt culorile scrise direct de pagini pe butoanele colorate.
PERECHI = (
	("--text", "--fundal", PRAG_TEXT_MARE), ("--text", "--panou", PRAG_TEXT_MARE), ("--text", "--panou-2", PRAG_TEXT),
	("--text", "--camp", PRAG_TEXT), ("--text", "--buton", PRAG_TEXT), ("--text", "--buton-peste", PRAG_TEXT),
	("--text", "--antet", PRAG_TEXT), ("--text", "--meniu-fundal", PRAG_TEXT), ("--text", "--rand", PRAG_TEXT),
	("--text-2", "--fundal", PRAG_TEXT), ("--text-2", "--panou", PRAG_TEXT), ("--text-2", "--meniu-fundal", PRAG_TEXT),
	("--text-2", "--rand", PRAG_TEXT),
	("--text-slab", "--fundal", PRAG_TEXT), ("--text-slab", "--panou", PRAG_TEXT), ("--text-slab", "--panou-2", PRAG_TEXT),
	("--text-slab", "--antet", PRAG_TEXT), ("--text-slab", "--meniu-fundal", PRAG_TEXT), ("--text-slab", "--rand", PRAG_TEXT),
	("--legatura", "--fundal", PRAG_TEXT), ("--legatura", "--panou", PRAG_TEXT), ("--legatura", "--panou-2", PRAG_TEXT),
	("--legatura", "--rand", PRAG_TEXT),
	("--marca", "--meniu-fundal", PRAG_TEXT), ("--marca", "--panou", PRAG_TEXT), ("--marca", "--marca-fond", PRAG_TEXT),
	("--eroare", "--fundal", PRAG_TEXT), ("--eroare", "--panou", PRAG_TEXT), ("--eroare", "--panou-2", PRAG_TEXT),
	("--eroare", "--pericol-fond", PRAG_TEXT),
	("--atentie", "--fundal", PRAG_TEXT), ("--atentie", "--panou", PRAG_TEXT), ("--atentie", "--panou-2", PRAG_TEXT),
	("--bine", "--fundal", PRAG_TEXT), ("--bine", "--panou", PRAG_TEXT), ("--bine", "--panou-2", PRAG_TEXT),
	("--bine", "--bine-fond", PRAG_TEXT),
	("--chihlimbar", "--fundal", PRAG_TEXT), ("--chihlimbar", "--panou", PRAG_TEXT), ("--chihlimbar", "--rand", PRAG_TEXT),
	("--ales-text", "--ales", PRAG_TEXT), ("--legatura", "--ales", PRAG_TEXT),
	("#ffffff", "--accent", PRAG_TEXT), ("#ffffff", "--rosu", PRAG_TEXT), ("#ffffff", "--verde", PRAG_TEXT),
	("#ffffff", "--albastru", PRAG_TEXT), (TEXT_PE_GALBEN, "--galben", PRAG_TEXT),
	("--chihlimbar", "--antet", PRAG_CHENAR), ("--chihlimbar", "--ales", PRAG_CHENAR),
)

# Culorile scrise direct in <style>-urile paginilor vechi, puse pe variabilele temei la servire (numai in paginile
# imbracate). SUPRAFETE: in orice proprietate (fundaluri, chenare). TEXT: numai in declaratiile „color:” (aceleasi
# culori folosite ca fundal pentru butoane sau benzi raman cum sunt: ele au textul lor inchis).
CULORI_SUPRAFETE = {
	"#14171c": "var(--fundal)",
	"#1c2129": "var(--panou)",
	"#181c23": "var(--panou-2)",
	"#171b22": "var(--panou-2)",
	"#0f1216": "var(--camp)",
	"#242a33": "var(--buton)",
	"#2a2f38": "var(--bordura)",
	"#3a424e": "var(--dezactivat)",
	"#22304a": "var(--ales)",
}
CULORI_TEXT = {
	"#e6e9ef": "var(--text)",
	"#8891a0": "var(--text-slab)",
	"#7fb8ff": "var(--legatura)",
	"#9fb4ff": "var(--legatura)",
	"#ffb4a8": "var(--eroare)",
	"#ff9a8f": "var(--eroare)",
	"#ff8f7f": "var(--eroare)",
	"#ff8a80": "var(--eroare)",
	"#ff7a6b": "var(--eroare)",
	"#ff6b5e": "var(--eroare)",
	"#ffd28a": "var(--atentie)",
	"#ffd27a": "var(--atentie)",
	"#ffd479": "var(--atentie)",
	"#ffd88a": "var(--atentie)",
	"#f0c674": "var(--atentie)",
	"#8fd19e": "var(--bine)",
	"#a8e6b4": "var(--bine)",
	"#7fdc9a": "var(--bine)",
	"#6fdc9a": "var(--bine)",
	"#8fe0b0": "var(--bine)",
	"#7ee0a8": "var(--bine)",
	"#4fd18b": "var(--bine)",
	"#f5b83d": "var(--chihlimbar)",
}


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


# grupa „Principal”: paginile pe care televizorul le deschide din taste, nu din MENU (OK, EPG, RADIO, PVR, AUDIO,
# TEXT); fiecare numai cand ruta exista pe receptor (de exemplu /teletext numai cu teletextul in imagine)
PRINCIPAL = (
	("/", N_("Panou")),
	("/canale", N_("Canale")),
	("/ghid", N_("Ghidul canalului")),
	("/radio", N_("Radio")),
	("/filme", N_("Filmul de acum")),
	("/piste", N_("Sunet și subtitrări")),
	("/teletext", N_("Teletext")),
	("/cautare", N_("Căutare canale")),
)
# bara de jos de pe telefon (ecranele Stitch de telefon): (cale, text, iconita); „Mai mult” deschide meniul
BARA_JOS = (
	("/", N_("Telecomandă"), "telecomanda"),
	("/canale", N_("Canale"), "canale"),
	("/ghid", N_("Ghid TV"), "ghid"),
	("/radio", N_("Radio"), "radio"),
)
# paginile deschise dintr-o alta pagina (nu din meniu): calea lor trece prin pagina-parinte
PARINTI = {
	"/interfete-cam": "/acces-conditionat",
	"/ocr-limbi": "/subtitrari",
	"/traducere-configurare": "/traducere-subtitrari",
	"/setari-din-copie": "/import",
	"/playlisturi": "/canale",
}
# rutele care nu sunt pagini (nu se imbraca niciodata, oricare ar fi raspunsul)
FARA_CADRU = ("api", "web", "picon", "file", "grab", "t", "asociere", "deconectare", "cadru", "favicon.ico",
	"paza-model")
MAX_PAGINA = 4 * 1024 * 1024
DURATA_CACHE_S = 60

# familiile paletelor, in ordinea si cu numele de pe televizor (HdsSkinSetari: fam_<id>)
FAMILII = (
	("bleumarin", N_("Bleumarin")),
	("negru", N_("Negru")),
	("grafit", N_("Grafit")),
	("albastru", N_("Albastru")),
	("turcoaz", N_("Turcoaz")),
	("verde", N_("Verde")),
	("rosu", N_("Roșu")),
	("mov", N_("Mov")),
	("maro", N_("Maro")),
	("luminos", N_("Luminos")),
	("contrast", N_("Contrast mare")),
	("daltonism", N_("Pentru daltonism")),
)


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _e(text):
	"""Text scapat pentru HTML (si in atribute intre ghilimele duble)."""
	return (u"%s" % (text or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_JURNAL = {"cand": -3600.0}


def _jurnal(text):
	"""Cel mult un rand pe minut: o pagina ceruta des nu umple jurnalul cu aceeasi eroare."""
	acum = time.monotonic()
	if acum - _JURNAL["cand"] >= 60:
		_JURNAL["cand"] = acum
		print("[HdsWebControl] cadru: %s" % text)


# ------------------------------------------------------------------ culori, contrast (WCAG 2.x)
def _rgb(culoare):
	h = culoare.lstrip("#")
	return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(r, g, b):
	return "#%02x%02x%02x" % (max(0, min(255, int(round(r)))), max(0, min(255, int(round(g)))),
		max(0, min(255, int(round(b)))))


def amesteca(a, b, t):
	"""Culoarea a spre b cu fractia t (0 = a, 1 = b)."""
	ra, ga, ba = _rgb(a)
	rb, gb, bb = _rgb(b)
	return _hex(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def luminanta(culoare):
	"""Luminanta relativa WCAG (0 negru, 1 alb)."""
	def canal(v):
		v = v / 255.0
		return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
	r, g, b = _rgb(culoare)
	return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contrast(a, b):
	"""Raportul de contrast WCAG intre doua culori (1 ... 21)."""
	la, lb = luminanta(a), luminanta(b)
	if la < lb:
		la, lb = lb, la
	return (la + 0.05) / (lb + 0.05)


def _capatOpus(fond):
	"""Albul sau negrul, cel care se vede mai bine pe fond."""
	return ALB if contrast(ALB, fond) >= contrast(NEGRU, fond) else NEGRU


def asigura(text, fonduri, prag=PRAG_TEXT, spre=None):
	"""Culoarea textului mutata in pasi mici spre `spre` (alb sau negru; implicit capatul opus primului fond) pana
	trece pragul pe toate fondurile date; cel mult 40 de pasi, apoi capatul insusi."""
	if isinstance(fonduri, str):
		fonduri = (fonduri,)
	if spre is None:
		spre = _capatOpus(fonduri[0])
	c = text
	for _i in range(40):
		if all(contrast(c, f) >= prag for f in fonduri):
			return c
		c = amesteca(c, spre, 0.08)
	return spre


def fondPentru(text, fond, prag=PRAG_TEXT):
	"""Fondul unui buton mutat in pasi mici departe de culoarea textului lui pana trece pragul."""
	spre = NEGRU if luminanta(text) > 0.5 else ALB
	c = fond
	for _i in range(40):
		if contrast(text, c) >= prag:
			return c
		c = amesteca(c, spre, 0.06)
	return spre


# ------------------------------------------------------------------ culorile skinului (blocul <colors> din skin.xml)
_SKIN = {"cale": None, "semn": None, "culori": None}
_RE_CULOARE = re.compile(r'<color\s+name="([A-Za-z0-9_]+)"\s+value="#([0-9A-Fa-f]{6,8})"\s*/>')
CITIRE_SKIN = 65536  # blocul <colors> e la inceputul fisierului (ca HdsSkinSetari/paleta.py, CITIRE_INCEPUT)


def _caleSkin():
	if CALE_SKIN:
		return CALE_SKIN
	try:
		from Tools.Directories import resolveFilename, SCOPE_SKIN
		cale = resolveFilename(SCOPE_SKIN, "HDSatelit/skin.xml")
		if os.path.isfile(cale):
			return cale
	except Exception:
		pass
	return "/usr/share/enigma2/HDSatelit/skin.xml"


def culoriDinText(text):
	"""{rol: "#rrggbb"} din blocul <colors> al unui skin.xml (valorile Enigma2 #AARRGGBB: alfa se scoate)."""
	a = text.find("<colors>")
	b = text.find("</colors>", a + 1)
	if a < 0 or b < 0:
		return {}
	rez = {}
	for nume, valoare in _RE_CULOARE.findall(text[a:b]):
		rez[nume] = "#" + valoare[-6:].lower()
	return rez


def culoriSkin():
	"""Culorile skinului, citite o data si recitite numai cand skin.xml se schimba (mtime); rolurile lipsa sau un
	skin necitit iau valorile implicite."""
	cale = _caleSkin()
	try:
		semn = os.path.getmtime(cale)
	except OSError:
		semn = None
	if _SKIN["culori"] is None or _SKIN["cale"] != cale or _SKIN["semn"] != semn:
		culori = dict(CULORI_IMPLICITE)
		if semn is not None:
			try:
				with open(cale, "rb") as f:
					text = f.read(CITIRE_SKIN).decode("utf-8", "replace")
				for nume, valoare in culoriDinText(text).items():
					if nume in culori:
						culori[nume] = valoare
			except (IOError, OSError) as eroare:
				_jurnal("nu pot citi %s: %s" % (cale, eroare))
		_SKIN.update(cale=cale, semn=semn, culori=culori)
	return dict(_SKIN["culori"])


# ------------------------------------------------------------------ paletele de pe televizor (HdsSkinSetari)
# palete.txt: „id|familie|mod|panou|text|brand|brandL|amber|good|warn|bad|taste” (culorile RRGGBB), facut de
# tools/fa_palete.py al skinului. Derivarea paletei intregi (rolurile skinului) e a skinului: paleta.deriva din
# acelasi dosar, incarcat dupa cale (fara importuri din enigma2); fara el, o derivare simpla din culorile de baza.
_PALETE = {"cale": None, "semn": None, "lista": [], "modul": None}
_TASTE_SIMPLE = {
	"n": ("#e5484d", "#46b06a", "#e8b93a", "#3d7be0"),
	"d": ("#d55e00", "#009e73", "#f0e442", "#0072b2"),
	"l": ("#c62828", "#2e7d32", "#b8860b", "#1565c0"),
}


def _calePalete():
	if CALE_PALETE:
		return CALE_PALETE
	try:
		from Tools.Directories import resolveFilename, SCOPE_PLUGINS
		cale = resolveFilename(SCOPE_PLUGINS, "Extensions/HdsSkinSetari/palete.txt")
		if os.path.isfile(cale):
			return cale
	except Exception:
		pass
	return os.path.join(DOSAR_SKIN_SETARI, "palete.txt")


def _modulPaleta(dosar):
	"""paleta.py al skinului (acelasi dosar cu palete.txt), incarcat dupa cale; None daca lipseste sau nu merge."""
	cale = os.path.join(dosar, "paleta.py")
	if not os.path.isfile(cale):
		return None
	try:
		import importlib.util
		spec = importlib.util.spec_from_file_location("hds_cadru_paleta_skin", cale)
		modul = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(modul)
		if not hasattr(modul, "deriva"):
			return None
		return modul
	except Exception as eroare:
		_jurnal("paleta.py al skinului: %s" % eroare)
		return None


def citestePalete(text):
	"""[(id, familie, baza)] din textul unui palete.txt; baza = {"mod", "panou", "text", "brand", "brandL", "amber",
	"good", "warn", "bad", "taste"} cu culorile „#rrggbb”. Randurile stricate si dublurile se sar."""
	rez = []
	vazute = set([CULORI_SKIN, CULORI_TV])
	for rand in text.splitlines():
		rand = rand.strip()
		if not rand or rand.startswith("#"):
			continue
		c = rand.split("|")
		if len(c) != 12 or c[0] in vazute or not _RE_ID_PALETA.match(c[0]) or c[2] not in ("d", "l"):
			continue
		if not all(re.match(r"^[0-9A-Fa-f]{6}$", x) for x in c[3:11]):
			continue
		baza = {"mod": c[2], "taste": c[11] if c[11] in _TASTE_SIMPLE else "n"}
		for cheie, valoare in zip(("panou", "text", "brand", "brandL", "amber", "good", "warn", "bad"), c[3:11]):
			baza[cheie] = "#" + valoare.lower()
		rez.append((c[0], c[1], baza))
		vazute.add(c[0])
	return rez


def palete():
	"""Paletele de pe televizor [(id, familie, baza)], recitite numai cand palete.txt se schimba; [] fara skin."""
	cale = _calePalete()
	try:
		semn = os.path.getmtime(cale)
	except OSError:
		semn = None
	if _PALETE["cale"] != cale or _PALETE["semn"] != semn:
		lista = []
		modul = None
		if semn is not None:
			try:
				with open(cale, "rb") as f:
					lista = citestePalete(f.read(256 * 1024).decode("utf-8", "replace"))
				modul = _modulPaleta(os.path.dirname(cale))
			except (IOError, OSError) as eroare:
				_jurnal("nu pot citi %s: %s" % (cale, eroare))
		_PALETE.update(cale=cale, semn=semn, lista=lista, modul=modul)
	return list(_PALETE["lista"])


def _rolHex(v):
	return "#%06x" % (v & 0xFFFFFF)


def culoriDinBaza(baza, modul=None):
	"""Culorile web (cheile din CULORI_IMPLICITE) ale unei palete: derivarea skinului (paleta.deriva) cand e
	incarcata, altfel una simpla din culorile de baza."""
	if modul is not None:
		try:
			b = {"mod": baza["mod"], "taste": baza.get("taste", "n")}
			for cheie in ("panou", "text", "brand", "brandL", "amber", "good", "warn", "bad"):
				b[cheie] = int(baza[cheie].lstrip("#"), 16)
			p = modul.deriva(b)
			return dict((k, _rolHex(p[k])) for k in CULORI_IMPLICITE if k in p)
		except Exception as eroare:
			_jurnal("derivarea paletei: %s" % eroare)
	panou, text = baza["panou"], baza["text"]
	r, g, y, b = _TASTE_SIMPLE.get(baza.get("taste", "n"), _TASTE_SIMPLE["n"])
	return {
		"hdsPanelSolid": panou, "hdsText": text, "hdsText2": amesteca(text, panou, 0.17),
		"hdsLabel": amesteca(text, panou, 0.27), "hdsBrand": baza["brand"], "hdsBrandLight": baza["brandL"],
		"hdsAmber": baza["amber"], "hdsGood": baza["good"], "hdsWarn": baza["warn"], "hdsBad": baza["bad"],
		"hdsTrack": amesteca(panou, text, 0.12), "hdsCell": amesteca(panou, text, 0.09),
		"hdsCellNow": amesteca(panou, text, 0.19), "hdsDisabled": amesteca(panou, text, 0.40),
		"key_red": r, "key_green": g, "key_yellow": y, "key_blue": b,
	}


def culoriPaleta(pid):
	"""Culorile web pentru alegerea `pid`: CULORI_TV = skin.xml (ca pe televizor), CULORI_SKIN = paleta implicita a
	skinului, altfel paleta cu acel id din palete.txt; None pentru un id necunoscut."""
	if pid == CULORI_TV:
		return culoriSkin()
	if pid == CULORI_SKIN:
		return dict(CULORI_IMPLICITE)
	for ident, _fam, baza in palete():
		if ident == pid:
			c = dict(CULORI_IMPLICITE)
			c.update(culoriDinBaza(baza, _PALETE["modul"]))
			return c
	return None


def culoareValida(pid):
	return pid in (CULORI_TV, CULORI_SKIN) or any(ident == pid for ident, _f, _b in palete())


def numeFamilie(fam):
	for ident, nume in FAMILII:
		if ident == fam:
			return _t(nume)
	return fam[:1].upper() + fam[1:]


def numePaleta(pid):
	"""„Bleumarin 03”, ca pe televizor; „HD Satelit” pentru paleta implicita a skinului."""
	if pid == CULORI_TV:
		return _t("Ca pe televizor")
	if pid == CULORI_SKIN:
		return "HD Satelit"
	fam, _s, nr = pid.rpartition("-")
	return "%s %s" % (numeFamilie(fam), nr) if fam and nr else pid


def _mostre(c):
	"""Patru culori pentru cartonasul paletei (ca in ecranul Stitch „Tema și culori”): fundalul, randul, accentul si
	culoarea de evidentiere."""
	plin = c["hdsPanelSolid"]
	return [amesteca(plin, NEGRU, 0.2) if luminanta(plin) < 0.35 else plin, amesteca(plin, c["hdsText"], 0.08),
		c["hdsBrand"], c["hdsBrandLight"]]


def listaCulori():
	"""Pentru /api/tema-web: „Ca pe televizor”, paleta skinului si familiile cu variantele lor, fiecare cu mostrele."""
	tv = culoriSkin()
	fam = {}
	ordine = []
	for ident, familie, baza in palete():
		if familie not in fam:
			fam[familie] = []
			ordine.append(familie)
		c = dict(CULORI_IMPLICITE)
		c.update(culoriDinBaza(baza, _PALETE["modul"]))
		fam[familie].append({"id": ident, "nume": numePaleta(ident), "mostre": _mostre(c), "luminos": baza["mod"] == "l"})
	cunoscute = [f for f, _n in FAMILII if f in fam]
	familii = [{"id": f, "nume": numeFamilie(f), "palete": fam[f]} for f in cunoscute + [f for f in ordine if f not in cunoscute]]
	return {"tv": {"id": CULORI_TV, "nume": _t("Ca pe televizor"), "mostre": _mostre(tv)},
		"skin": {"id": CULORI_SKIN, "nume": "HD Satelit", "mostre": _mostre(dict(CULORI_IMPLICITE))},
		"familii": familii}


# ------------------------------------------------------------------ implicitele web tinute pe receptor
def _configWeb():
	"""config.plugins.hdswebcontrol cu tema_web si culori_web (facute aici la prima nevoie); None pe PC sau inainte ca
	pluginul sa-si fi facut sectiunea (nu o facem noi: initConfigHdsWebControl din plugin.py o face cu tot ce trebuie)."""
	try:
		from Components.config import config, ConfigSelection, ConfigText
	except Exception:
		return None
	try:
		if "hdswebcontrol" not in config.plugins.content.items:
			return None
		s = config.plugins.hdswebcontrol
		if "tema_web" not in s.content.items:
			s.tema_web = ConfigSelection(choices=[("clasic", _t("Clasic")), ("pro", "Pro")], default=TEMA_IMPLICITA)
		if "culori_web" not in s.content.items:
			s.culori_web = ConfigText(default=CULORI_TV, fixed_size=False)
		return s
	except Exception as eroare:
		_jurnal("setarile temei web: %s" % eroare)
		return None


def implicite():
	"""(tema, culori) implicite pentru browserele fara alegere proprie, tinute pe receptor."""
	s = _configWeb()
	tema, culori = TEMA_IMPLICITA, CULORI_TV
	if s is not None:
		try:
			if s.tema_web.value in TEME:
				tema = s.tema_web.value
			if culoareValida(s.culori_web.value):
				culori = s.culori_web.value
		except Exception as eroare:
			_jurnal("implicitele temei web: %s" % eroare)
	return tema, culori


def seteazaImplicite(tema=None, culori=None):
	"""Schimba implicitele de pe receptor (numai interfata web; skinul si televizorul raman neatinse)."""
	if tema is not None and tema not in TEME:
		return {"result": False, "message": _t("Tema necunoscută.")}
	if culori is not None and not culoareValida(culori):
		return {"result": False, "message": _t("Schema de culori necunoscută.")}
	s = _configWeb()
	if s is None:
		return {"result": False, "message": _t("Setarea nu se poate salva acum.")}
	if tema is not None:
		s.tema_web.value = tema
		s.tema_web.save()
	if culori is not None:
		s.culori_web.value = culori
		s.culori_web.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as eroare:
		_jurnal("salvarea setarilor: %s" % eroare)
	t, c = implicite()
	return {"result": True, "message": _t("Salvat pe receptor. Browserele fără alegere proprie o folosesc de acum."),
		"tema_implicita": t, "culori_implicite": c}


# ------------------------------------------------------------------ variabilele temelor
# variabilele care sunt culori de text (in PERECHI, primul element); celelalte sunt fundaluri
TEXTE = ("--text", "--text-2", "--text-slab", "--legatura", "--marca", "--eroare", "--atentie", "--bine",
	"--chihlimbar", "--ales-text")
ORDINE = ("--fundal", "--panou", "--panou-2", "--rand", "--camp", "--buton", "--buton-peste", "--bordura",
	"--dezactivat", "--antet", "--meniu-fundal", "--ales", "--ales-text", "--marca-fond", "--bine-fond", "--pericol-fond",
	"--text", "--text-2", "--text-slab", "--legatura", "--marca", "--eroare", "--atentie", "--bine", "--chihlimbar",
	"--accent", "--rosu", "--verde", "--albastru", "--galben", "--bine-plin", "--atentie-plin")


def _repara(d, spre):
	"""Ultima trecere peste PERECHI: un text sub prag se muta spre `spre`; daca nici capatul nu ajunge, fundalul se muta
	departe de text. Pe o paleta obisnuita nu schimba nimic; pe una aleasa prost aduce totul la prag."""
	for _runda in range(8):
		stricat = False
		for a, b, prag in PERECHI:
			ca, cb = d.get(a, a), d.get(b, b)
			if contrast(ca, cb) + 1e-9 >= prag:
				continue
			stricat = True
			if a in TEXTE:
				d[a] = asigura(ca, cb, prag, spre)
				if contrast(d[a], cb) + 1e-9 < prag:
					d[b] = fondPentru(d[a], cb, prag + 0.2)
			else:
				d[b] = fondPentru(ca, cb, prag + 0.05)
		if not stricat:
			return


def variabile(tema, c=None):
	"""Lista ordonata (variabila CSS, valoare) a temei, din culorile date (skinul sau paleta aleasa in web); contrastul
	AA e impus aici (PERECHI). Amestecurile sunt potrivite asa incat, pe culorile implicite ale skinului, valorile sa
	cada pe cele masurate in ecranele Stitch (design-stitch-masurat.json; proba: test_web_meniu_teme_stitch).
	Directia se alege o data, dupa panoul skinului: pe un panou inchis textul merge spre alb si fundalurile spre negru,
	pe unul luminos invers; panoul insusi se muta daca nici textul cel mai departat nu ar trece de 8:1 pe el."""
	if c is None:
		c = dict(CULORI_IMPLICITE)
	plin = c["hdsPanelSolid"]
	luminos = luminanta(plin) > 0.35
	spre = NEGRU if luminos else ALB      # spre text
	adanc = ALB if luminos else NEGRU     # spre fundalul mai adanc
	plin = fondPentru(spre, plin, 8.0)
	text0 = asigura(c["hdsText"], plin, PRAG_TEXT_MARE, spre)
	brand, brand_l = c["hdsBrand"], c["hdsBrandLight"]
	if tema == "pro":
		# Stitch Pro: pagina #0e1323, bara laterala #161b2b, cardurile de sticla #151a2a, panourile din carduri #181d2e,
		# butoanele #25293a, antetul rgba(8,13,29,.8), intrarea aleasa rgba(55,78,161,.4) cu text #b7c4ff
		fundal = amesteca(plin, adanc, 0.12)
		antet = amesteca(plin, adanc, 0.40)
		meniu = amesteca(plin, text0, 0.025)
		panou = amesteca(plin, text0, 0.02)
		panou2 = amesteca(plin, text0, 0.045)
		rand = panou2
		camp = fundal
		buton = amesteca(plin, text0, 0.09)
		buton_peste = amesteca(plin, text0, 0.15)
		bordura = amesteca(plin, text0, 0.10)
		ales = amesteca(meniu, brand, 0.40)
		ales_text = amesteca(brand_l, spre, 0.20)
		text_baza = amesteca(text0, brand_l, 0.12)
		slab = amesteca(c["hdsLabel"], plin, 0.22)
		marca = amesteca(brand_l, spre, 0.20)
	else:
		# Stitch Clasic (ca meniul de pe televizor): pagina #10162a, randurile #1b2436, randul ales #3a4658 cu text
		# crem #f3e3c3, textul slab #8b96a8, butoanele #24314c cu chenar #38486b, campurile #242f44
		fundal = plin
		antet = amesteca(plin, adanc, 0.25)
		meniu = plin
		panou = amesteca(plin, text0, 0.05)
		panou2 = amesteca(plin, text0, 0.085)
		rand = amesteca(plin, text0, 0.05)
		camp = amesteca(plin, text0, 0.085)
		buton = amesteca(plin, brand_l, 0.15)
		buton_peste = amesteca(plin, brand_l, 0.22)
		bordura = amesteca(plin, brand_l, 0.25)
		ales = amesteca(plin, text0, 0.20)
		ales_text = amesteca(c["hdsAmber"], text0, 0.70)
		text_baza = amesteca(text0, spre, 0.5)
		slab = amesteca(c["hdsLabel"], plin, 0.25)
		marca = c["hdsAmber"]
	texte = (panou2, panou, fundal, rand)
	d = dict([
		("--fundal", fundal), ("--panou", panou), ("--panou-2", panou2), ("--rand", rand), ("--camp", camp),
		("--buton", buton), ("--buton-peste", buton_peste), ("--bordura", bordura),
		("--dezactivat", amesteca(plin, text0, 0.26)), ("--antet", antet), ("--meniu-fundal", meniu), ("--ales", ales),
		("--ales-text", asigura(ales_text, ales, PRAG_TEXT, spre)),
		("--marca-fond", amesteca(meniu, brand, 0.30)),
		("--bine-fond", amesteca(panou, c["hdsGood"], 0.14)),
		("--pericol-fond", amesteca(panou, c["hdsBad"], 0.16)),
		("--text", asigura(text_baza, (fundal, panou), PRAG_TEXT_MARE, spre)),
		("--text-2", asigura(c["hdsText2"], texte + (meniu,), PRAG_TEXT, spre)),
		("--text-slab", asigura(slab, texte + (antet, meniu), PRAG_TEXT, spre)),
		("--legatura", asigura(amesteca(brand_l, spre, 0.2), texte, PRAG_TEXT, spre)),
		("--marca", asigura(marca, (meniu, panou), PRAG_TEXT, spre)),
		("--eroare", asigura(amesteca(c["hdsBad"], spre, 0.4), texte, PRAG_TEXT, spre)),
		("--atentie", asigura(c["hdsWarn"], texte, PRAG_TEXT, spre)),
		("--bine", asigura(amesteca(c["hdsGood"], spre, 0.08), texte, PRAG_TEXT, spre)),
		("--chihlimbar", asigura(c["hdsAmber"], (panou, fundal, rand), PRAG_TEXT, spre)),
		("--accent", fondPentru(ALB, brand)),
		("--rosu", fondPentru(ALB, c["key_red"])), ("--verde", fondPentru(ALB, c["key_green"])),
		("--albastru", fondPentru(ALB, c["key_blue"])), ("--galben", fondPentru(TEXT_PE_GALBEN, c["key_yellow"])),
		("--bine-plin", c["hdsGood"]), ("--atentie-plin", c["hdsWarn"]),
	])
	_repara(d, spre)
	return [(nume, d[nume]) for nume in ORDINE]


def verificaContrast(v):
	"""[(text, fundal, raport, prag)] pentru perechile din PERECHI care nu trec pragul (lista goala = tot trece)."""
	d = dict(v)
	rez = []
	for a, b, prag in PERECHI:
		ca = d.get(a, a)
		cb = d.get(b, b)
		r = contrast(ca, cb)
		if r + 1e-9 < prag:
			rez.append((a, b, round(r, 2), prag))
	return rez


def _blocVariabile(tema, c):
	v = variabile(tema, c)
	luminos = luminanta(c["hdsPanelSolid"]) > 0.35
	return 'html.hds-cadru[data-tema="%s"]{color-scheme:%s;%s}' % (tema, "light" if luminos else "dark",
		"".join("%s:%s;" % (nume, valoare) for nume, valoare in v))


# ------------------------------------------------------------------ iconitele (SVG in pagina, linii de 24 x 24)
ICONITE = {
	"panou": "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
	"canale": "M3 5h18v12H3zM8 21h8M10.5 8.5v5l4-2.5z",
	"ghid": "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M8 14h2M12 14h2M8 17h2",
	"radio": "M4 9h16v11H4zM6 9l11-5M8.5 14.5a2 2 0 1 0 0.01 0M14 13h3M14 16.5h3",
	"filme": "M4 5h16v14H4zM8 5v14M16 5v14M4 9.5h4M4 14.5h4M16 9.5h4M16 14.5h4",
	"sunet": "M4 10v4h4l5 4V6L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11",
	"teletext": "M4 5h16v14H4zM7 9h10M7 12h10M7 15h6",
	"cautare": "M10.5 4a6.5 6.5 0 1 0 0.01 0M15.3 15.3L20 20",
	"scanare": "M12 4a8 8 0 1 0 8 8M12 8a4 4 0 1 0 4 4M12 12l6.5-6.5",
	"antena": "M5 14a8 8 0 0 0 10-10zM10 9l5-5M15 4h3M9 17l-2 4h8l-2-4",
	"informatii": "M12 4a8 8 0 1 0 0.01 0M12 11v5M12 8v.5",
	"setari": "M12 9a3 3 0 1 0 0.01 0M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1",
	"media": "M5 5h12v12H5zM9.5 8.5v5l4-2.5zM20 8v12H8",
	"temporizator": "M12 4a8 8 0 1 0 0.01 0M12 8v4l3 2",
	"aplicatii": "M5 5h6v6H5zM13 13h6v6h-6zM16 4v8M12 8h8M4 16h8M8 12v8",
	"alte": "M5 12h.5M12 12h.5M19 12h.5",
	"telecomanda": "M8.5 3h7v18h-7zM12 6.5v.5M10.5 10h3M10.5 13h3M10.5 16h3",
	"mai-mult": "M5 12h.5M12 12h.5M19 12h.5",
	"satelit": "M8.5 8.5l3 3M4 8l4-4 3.5 3.5-4 4zM12.5 12.5l4-4L20 12l-4 4zM9.5 14.5l1.5 1.5M5 17a3 3 0 0 0 3 3M4 13a7 7 0 0 0 7 7",
	"meniu": "M4 6h16M4 12h16M4 18h16",
	"inchide": "M6 6l12 12M18 6L6 18",
	"ceas": "M12 4a8 8 0 1 0 0.01 0M12 8v4l2.5 2",
}
# iconita grupei sau a intrarii de sus din meniu (dupa entryID / key din menu.xml si dupa calea paginii)
ICONITE_MENIU = {
	"/": "panou", "/canale": "canale", "/ghid": "ghid", "/radio": "radio", "/filme": "filme", "/piste": "sunet",
	"/teletext": "teletext", "/cautare": "cautare",
	"hds_scanare": "scanare", "hds_antena": "antena", "info_screen": "informatii", "setup_selection": "setari",
	"hds_media": "media", "timer_edit": "temporizator", "plugin_selection": "aplicatii",
}


def _simboluri():
	"""Iconitele o singura data in pagina (<symbol>), folosite apoi cu <use href="#hi-...">."""
	parti = []
	for nume in sorted(ICONITE):
		parti.append(u'<symbol id="hi-%s" viewBox="0 0 24 24"><path d="%s"/></symbol>' % (nume, ICONITE[nume]))
	return (u'<svg class="hds-simboluri" aria-hidden="true" focusable="false" width="0" height="0" fill="none" '
		u'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
		% u"".join(parti))


def _ic(nume, clasa="hds-ic"):
	if nume not in ICONITE:
		nume = "alte"
	return u'<svg class="%s" aria-hidden="true" focusable="false"><use href="#hi-%s"/></svg>' % (clasa, nume)


# ------------------------------------------------------------------ stilul cadrului
# Prefixele: P = html.hds-cadru[data-tema="pro"], C = html.hds-cadru[data-tema="clasic"]. Fiecare color-mix() are
# inainte o declaratie simpla a aceleiasi proprietati: un browser fara color-mix() o pastreaza pe aceea. Stilul cadrului vine dupa
# <style>-urile paginii, deci cu un selector cel putin la fel de tare castiga; regulile componentelor (butoane,
# carduri, campuri, randuri, tabele) au prefixul temei si bat regulile paginilor (h1, .card, button, .taste button).
STIL_COMUN = """
@font-face{font-family:"Hds";src:url("/cadru/HdsRegular.ttf") format("truetype");font-weight:300 500;font-display:swap;}
@font-face{font-family:"Hds";src:url("/cadru/HdsBold.ttf") format("truetype");font-weight:600 800;font-display:swap;}
@font-face{font-family:"HdsCond";src:url("/cadru/HdsCond.ttf") format("truetype");font-weight:400 700;font-display:swap;}
html.hds-cadru{--font:"Hds",system-ui,"Segoe UI",Roboto,sans-serif;--font-ingust:"HdsCond","Hds",system-ui,sans-serif;
  --lat-meniu:256px;--st:16px;--cadru-stanga:0px;--cadru-jos:0px;--h-antet:56px;}
html.hds-cadru body{font-family:var(--font);background:var(--fundal);color:var(--text);padding-top:0;
  padding-left:var(--st);padding-right:16px;}
/* :where(): specificitate mica, ca legaturile meniului si ale paginilor sa-si pastreze culoarea lor */
:where(html.hds-cadru) a{color:var(--legatura);}
html.hds-cadru :focus-visible{outline:2px solid var(--marca);outline-offset:2px;}
html.hds-cadru p:has(> a.inapoi[href="/"]:only-child),html.hds-cadru a.inapoi[href="/"]{display:none;}
html.hds-cadru .rand.ales,html.hds-cadru .intrare.ales{background:var(--ales);color:var(--ales-text);}
html.hds-cadru .nota,html.hds-cadru .ajutor,html.hds-cadru .rand .ajutor{color:var(--text-slab);}
html.hds-cadru .eroare{color:var(--eroare);}
.hds-simboluri{position:absolute;width:0;height:0;overflow:hidden;}
.hds-ic{width:20px;height:20px;flex:none;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;
  stroke-linejoin:round;}
.hds-antet{position:sticky;top:0;z-index:50;margin:0 -16px 20px calc(-1 * var(--st));background:var(--antet);
  border-bottom:1px solid var(--bordura);color:var(--text);font-family:var(--font);}
.hds-antet-bara{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;min-height:var(--h-antet);padding:6px 16px;}
.hds-dreapta{display:contents;}
.hds-buton-meniu{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;min-width:44px;
  padding:0 14px;border-radius:8px;border:1px solid var(--bordura);background:var(--buton);color:var(--text);
  font:inherit;font-weight:600;cursor:pointer;}
.hds-buton-meniu:hover{background:var(--buton-peste);}
.hds-marca{display:inline-flex;align-items:center;gap:10px;min-height:44px;font-weight:700;white-space:nowrap;
  color:var(--text) !important;text-decoration:none;}
.hds-marca-2{font-weight:700;}
.hds-sigla{display:inline-flex;align-items:center;justify-content:center;flex:none;width:36px;height:36px;
  border-radius:10px;background:var(--marca-fond);border:1px solid var(--bordura);color:var(--marca);}
.hds-sigla .hds-ic{width:22px;height:22px;}
.hds-sep{color:var(--text-slab);font-weight:300;}
.hds-cale{min-width:0;color:var(--text-slab);}
.hds-cale ol{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:2px 0;}
.hds-cale li{display:flex;align-items:center;min-height:31px;white-space:nowrap;max-width:100%;overflow:hidden;}
.hds-cale li+li::before{content:"\\203A";margin:0 8px;color:var(--text-slab);}
.hds-cale a{display:block;padding:6px 0;color:var(--text-slab) !important;text-decoration:none;}
.hds-cale a:hover{text-decoration:underline;}
.hds-cale [aria-current]{color:var(--text);font-weight:600;}
.hds-receptor{white-space:nowrap;overflow:hidden;min-width:0;}
.hds-stare{display:inline-flex;align-items:center;gap:8px;min-width:0;max-width:40vw;}
.hds-stare span:last-child{white-space:nowrap;overflow:hidden;}
.hds-punct{flex:none;width:9px;height:9px;border-radius:50%;background:var(--text-slab);}
.hds-punct.pornit{background:var(--bine-plin);box-shadow:0 0 8px 1px var(--bine-plin);}
.hds-punct.standby{background:var(--atentie-plin);}
.hds-ceas{white-space:nowrap;font-variant-numeric:tabular-nums;}
/* pictograma retelei (stare_retea_web.py): cablu sau Wi-Fi si internetul, desenul Stitch de 40x30 */
.hds-retea{display:inline-flex;align-items:center;flex:none;width:40px;height:30px;}
.hds-retea svg{display:block;width:40px;height:30px;}
.hds-retea[hidden]{display:none;}
.hds-umbra{position:fixed;inset:0;z-index:55;background:rgba(0,0,0,.55);}
.hds-umbra[hidden]{display:none;}
.hds-meniu{position:fixed;z-index:60;top:0;left:0;bottom:0;width:min(88vw,340px);overflow-y:auto;
  overscroll-behavior:contain;background:var(--meniu-fundal);color:var(--text);border-right:1px solid var(--bordura);
  font-family:var(--font);transform:translateX(-102%);visibility:hidden;transition:transform .2s ease,visibility .2s;
  padding:0 0 28px;}
html.hds-meniu-deschis .hds-meniu{transform:none;visibility:visible;}
.hds-meniu-cap{position:sticky;top:0;z-index:1;display:flex;align-items:center;gap:12px;padding:14px 12px 14px 20px;
  background:var(--meniu-fundal);border-bottom:1px solid var(--bordura);}
.hds-meniu-cap>div{min-width:0;}
.hds-meniu-cap strong{display:flex;align-items:center;gap:8px;font-size:1.15rem;font-weight:700;letter-spacing:-.01em;}
.hds-meniu-cap small{display:block;color:var(--text-slab);font-size:.72rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;white-space:nowrap;overflow:hidden;}
.hds-meniu-cap .hds-punct{background:var(--bine-plin);box-shadow:0 0 8px 1px var(--bine-plin);}
.hds-meniu-inchide{margin-left:auto;display:inline-flex;align-items:center;justify-content:center;min-height:44px;
  min-width:44px;border-radius:8px;border:1px solid var(--bordura);background:var(--buton);color:var(--text);
  cursor:pointer;}
.hds-cauta{display:flex;gap:6px;padding:12px 12px 6px;margin:0;}
.hds-cauta input{flex:1;min-width:0;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);
  background:var(--camp);color:var(--text);font:inherit;}
.hds-cauta button{min-height:44px;padding:0 12px;border-radius:8px;border:1px solid var(--bordura);
  background:var(--buton);color:var(--text);font:inherit;font-weight:600;cursor:pointer;}
.hds-meniu ul{list-style:none;margin:0;padding:0 0 4px;}
.hds-meniu details>summary{list-style:none;display:flex;align-items:center;gap:10px;min-height:44px;cursor:pointer;}
.hds-meniu details>summary::-webkit-details-marker{display:none;}
.hds-meniu details>summary::after{content:"";flex:none;margin-left:auto;width:6px;height:6px;
  border-right:2px solid var(--text-slab);border-bottom:2px solid var(--text-slab);transform:rotate(45deg);
  margin-top:-4px;}
.hds-meniu details[open]>summary::after{transform:rotate(-135deg);margin-top:3px;}
.hds-meniu a{display:flex;align-items:center;gap:10px;min-height:44px;color:var(--text-2);text-decoration:none;
  line-height:1.3;}
.hds-semn-tv{flex:none;margin-left:auto;font-size:.66rem;font-weight:700;letter-spacing:.06em;padding:1px 6px;
  border:1px solid var(--bordura);border-radius:4px;color:var(--text-slab);}
.hds-ascuns{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}
.hds-meniu-jos{padding:16px 20px 0;font-size:.85rem;color:var(--text-slab);line-height:1.45;}
.hds-meniu-jos a{display:inline-flex;min-height:44px;padding:0;border:0;color:var(--legatura);text-decoration:underline;}
.hds-meniu-jos a:hover{background:none;}
.hds-jos{display:none;}
/* bara de jos pe telefon (ambele teme, ca in ecranele Stitch de telefon) */
@media (max-width:759px){
  html.hds-cadru{--cadru-jos:68px;}
  /* locul barei de jos la capatul paginii (fara sa schimbe padding-ul de jos al paginilor) */
  html.hds-cadru body::after{content:"";display:block;height:var(--cadru-jos);}
  .hds-jos{display:flex;position:fixed;z-index:52;left:0;right:0;bottom:0;height:var(--cadru-jos);
    padding:6px 6px calc(6px + env(safe-area-inset-bottom,0px));background:var(--antet);
    border-top:1px solid var(--bordura);font-family:var(--font);}
  .hds-jos a,.hds-jos button{flex:1 1 0;min-width:0;display:flex;flex-direction:column;align-items:center;
    justify-content:center;gap:3px;border:0;background:none;color:var(--text-slab);font:inherit;font-size:.7rem;
    font-weight:700;letter-spacing:.02em;text-decoration:none;cursor:pointer;white-space:nowrap;}
  .hds-jos .hds-ic{width:22px;height:22px;}
  .hds-jos [aria-current="page"]{color:var(--ales-text);background:var(--ales);}
  .hds-buton-meniu{display:none;}
  .hds-receptor,.hds-sep,.hds-ceas{display:none;}
  .hds-cale{order:9;flex:1 0 100%;font-size:.82rem;}
  .hds-stare{margin-left:auto;font-size:.8rem;}
}
@media (prefers-reduced-motion:reduce){ .hds-meniu{transition:none;} }
/* textul de un rand care nu incape se deruleaza (SCRIPT_DERULANT), fara "..."; cat sta, e taiat curat la margine */
.hds-derulant{overflow:hidden;white-space:nowrap;text-overflow:clip;}
.hds-derulant>span.hds-derulant-in{display:inline-block;flex:none;width:auto;min-width:0;max-width:none;margin:0;padding:0;
  border:0;background:none;overflow:visible;white-space:nowrap;
  animation:var(--hds-der-k,none) var(--hds-der-t,0s) linear var(--hds-der-w,0s) infinite;}
/* in liste (hds-derulant-rand pe rand) se misca numai randul ales, cel cu mouse-ul sau cel cu focusul */
.hds-derulant-rand:not(:hover):not(:focus-within):not(.ales):not([aria-selected="true"]):not([aria-current="true"]):not([aria-current="page"])
  span.hds-derulant-in{animation:none;}
@media (prefers-reduced-motion:reduce){ .hds-derulant>span.hds-derulant-in{animation:none !important;} }
"""

STIL_PRO = """
html.hds-cadru[data-tema="pro"]{font-size:14px;--h-antet:56px;}
html.hds-cadru[data-tema="pro"] body{background:var(--fundal);}
/* antetul de sticla: numele receptorului, pastila starii, calea, ceasul */
html[data-tema="pro"] .hds-antet{background:var(--antet);background:color-mix(in srgb,var(--antet) 88%,transparent);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);}
html[data-tema="pro"] .hds-antet-bara{padding:6px 24px;gap:6px 16px;}
html[data-tema="pro"] .hds-marca{font-size:1.15rem;letter-spacing:-.02em;}
html[data-tema="pro"] .hds-marca-2{color:var(--text);}
html[data-tema="pro"] .hds-sep{display:none;}
html[data-tema="pro"] .hds-receptor{order:1;font-size:15px;font-weight:600;color:var(--text);}
html[data-tema="pro"] .hds-stare{order:2;padding:4px 12px;border-radius:999px;background:var(--bine-fond);
  border:1px solid var(--bordura);border:1px solid color-mix(in srgb,var(--bine) 30%,transparent);color:var(--bine);font-size:11px;font-weight:700;
  letter-spacing:.06em;}
html[data-tema="pro"] .hds-stare.standby{background:var(--panou-2);color:var(--atentie);border-color:var(--bordura);}
html[data-tema="pro"] .hds-cale{order:3;flex:1 1 auto;font-size:12px;font-weight:600;letter-spacing:.02em;}
html[data-tema="pro"] .hds-ceas{order:4;margin-left:auto;font-size:14px;font-weight:700;color:var(--text);}
html[data-tema="pro"] .hds-retea{order:4;margin-left:auto;}
html[data-tema="pro"] .hds-retea:not([hidden])+.hds-ceas{margin-left:0;}
/* pe telefon pictograma retelei sta langa pastila starii, in primul rand (nu pe un rand al ei, dupa cale) */
@media (max-width:759px){ html[data-tema="pro"] .hds-retea{order:2;margin-left:0;} }
html[data-tema="pro"] .hds-buton-meniu{order:0;font-size:12px;letter-spacing:.03em;}
html[data-tema="pro"] .hds-marca{order:0;}
/* bara laterala (sertar sub 960 px) */
html[data-tema="pro"] .hds-meniu{width:min(88vw,var(--lat-meniu));font-size:13px;
  box-shadow:0 0 0 0 transparent,0 25px 50px -12px rgba(0,0,0,.25);}
html[data-tema="pro"] .hds-meniu-cap{border-bottom:0;padding:18px 16px 10px 20px;}
html[data-tema="pro"] .hds-meniu-cap .hds-sigla{width:40px;height:40px;border-radius:12px;}
html[data-tema="pro"] .hds-meniu details>summary{min-height:36px;padding:12px 16px 4px 28px;font-size:10.5px;
  font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-slab);}
html[data-tema="pro"] .hds-meniu details>summary .hds-ic{display:none;}
html[data-tema="pro"] .hds-meniu .hds-subgrupa>summary{padding:6px 16px 6px 44px;min-height:34px;text-transform:none;
  letter-spacing:0;font-size:12.5px;font-weight:600;color:var(--text-2);}
html[data-tema="pro"] .hds-meniu a{margin:2px 12px 2px 16px;padding:8px 12px;min-height:44px;border-radius:8px;
  border-left:2px solid transparent;font-weight:600;letter-spacing:.02em;}
html[data-tema="pro"] .hds-meniu .hds-subgrupa a{padding-left:28px;}
html[data-tema="pro"] .hds-meniu .hds-subgrupa .hds-subgrupa a{padding-left:40px;}
html[data-tema="pro"] .hds-meniu a:hover{background:var(--buton);color:var(--text);}
html[data-tema="pro"] .hds-meniu a[aria-current="page"]{background:var(--ales);color:var(--ales-text);
  border-left-color:var(--ales-text);}
html[data-tema="pro"] .hds-meniu a.hds-sus{font-weight:700;}
html[data-tema="pro"] .hds-cauta{padding:8px 16px 6px;}
html[data-tema="pro"] .hds-cauta input,html[data-tema="pro"] .hds-cauta button{font-size:13px;}
/* componentele paginilor */
html.hds-cadru[data-tema="pro"] h1{font-size:24px;font-weight:700;
  letter-spacing:-.025em;line-height:1.25;margin-top:4px;color:var(--text);}
html.hds-cadru[data-tema="pro"] .card{background:var(--panou);background:color-mix(in srgb,var(--panou) 92%,transparent);
  border:1px solid var(--bordura);border-radius:12px;padding:20px;
  box-shadow:inset 0 1px 0 0 rgba(255,255,255,.07),0 8px 24px -4px rgba(0,0,0,.45);}
html.hds-cadru[data-tema="pro"] .card h2,html.hds-cadru[data-tema="pro"] .card>h2{font-size:15px;font-weight:700;
  text-transform:none;letter-spacing:0;color:var(--text);margin:0 0 14px;padding-bottom:10px;
  border-bottom:1px solid var(--bordura);}
html.hds-cadru[data-tema="pro"] h2{color:var(--text);}
html.hds-cadru[data-tema="pro"] button:not(.hds-b){background:var(--buton);color:var(--text);border:1px solid var(--bordura);
  border-radius:8px;font-family:inherit;font-weight:600;letter-spacing:.02em;}
html.hds-cadru[data-tema="pro"] button:not(.hds-b):hover:not(:disabled){background:var(--buton-peste);}
html.hds-cadru[data-tema="pro"] button.verde,html.hds-cadru[data-tema="pro"] button.principal,
html.hds-cadru[data-tema="pro"] .butoane button.principal,html.hds-cadru[data-tema="pro"] button.albastru{
  background:var(--accent);border-color:var(--accent);border-color:color-mix(in srgb,#fff 20%,var(--accent));color:#fff;
  box-shadow:0 0 12px 0 rgba(55,78,161,.45);box-shadow:0 0 12px 0 color-mix(in srgb,var(--accent) 45%,transparent);}
html.hds-cadru[data-tema="pro"] button.rosu{background:var(--pericol-fond);color:var(--eroare);
  border-color:var(--bordura);border-color:color-mix(in srgb,var(--eroare) 30%,transparent);}
html.hds-cadru[data-tema="pro"] select,html.hds-cadru[data-tema="pro"] textarea,
html.hds-cadru[data-tema="pro"] input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]){
  background:var(--camp);color:var(--text);border:1px solid var(--bordura);border-radius:8px;font-family:inherit;}
html.hds-cadru[data-tema="pro"] select:focus,html.hds-cadru[data-tema="pro"] input:focus{border-color:var(--marca);}
html.hds-cadru[data-tema="pro"] input[type=checkbox],html.hds-cadru[data-tema="pro"] input[type=radio],
html.hds-cadru[data-tema="pro"] input[type=range]{accent-color:var(--accent);}
html.hds-cadru[data-tema="pro"] .rand,html.hds-cadru[data-tema="pro"] .status-linie{border-bottom-color:var(--bordura);}
html.hds-cadru[data-tema="pro"] .rand label{font-weight:600;}
html.hds-cadru[data-tema="pro"] table{border-collapse:collapse;}
html.hds-cadru[data-tema="pro"] th{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  color:var(--text-slab);border-bottom:1px solid var(--bordura);background:none;}
html.hds-cadru[data-tema="pro"] td{border-bottom:1px solid var(--bordura);border-bottom:1px solid color-mix(in srgb,var(--bordura) 70%,transparent);}
html.hds-cadru[data-tema="pro"] tr:hover>td{background:var(--panou-2);background:color-mix(in srgb,var(--panou-2) 70%,transparent);}
html.hds-cadru[data-tema="pro"] details>summary{font-weight:600;}
html.hds-cadru[data-tema="pro"] .taste button,html.hds-cadru[data-tema="pro"] .taste-nr button,
html.hds-cadru[data-tema="pro"] .captura-butoane button{background:var(--buton);border:1px solid var(--bordura);
  border-radius:8px;font-weight:600;}
html.hds-cadru[data-tema="pro"] .taste button:nth-child(5){background:var(--accent);color:#fff;font-weight:700;
  border-color:var(--accent);border-color:color-mix(in srgb,#fff 30%,var(--accent));}
html.hds-cadru[data-tema="pro"] .culori button{border-radius:6px;font-weight:700;}
html.hds-cadru[data-tema="pro"] button.canal{background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
  font-weight:400;letter-spacing:0;}
html.hds-cadru[data-tema="pro"] button:not(.hds-b):active:not(:disabled){filter:brightness(1.3);}
html[data-tema="pro"] .hds-jos [aria-current="page"]{border-radius:12px;}
html.hds-cadru[data-tema="pro"] .status-linie>span:first-child,html.hds-cadru[data-tema="pro"] .eticheta{
  color:var(--text-slab);}
html.hds-cadru[data-tema="pro"] .captura-cutie{border:1px solid var(--bordura);border-radius:12px;}
/* ecranele late: bara laterala mereu deschisa, ca in ecranele Stitch Pro */
@media (min-width:960px){
  html.hds-cadru[data-tema="pro"]{--st:24px;--cadru-stanga:var(--lat-meniu);}
  html.hds-cadru[data-tema="pro"] body{padding-left:calc(var(--lat-meniu) + var(--st));padding-right:24px;}
  html.hds-cadru[data-tema="pro"] .hds-antet{margin-right:-24px;}
  html[data-tema="pro"] .hds-meniu{transform:none;visibility:visible;transition:none;width:var(--lat-meniu);}
  html[data-tema="pro"] .hds-buton-meniu,html[data-tema="pro"] .hds-meniu-inchide,
  html[data-tema="pro"] .hds-umbra,html[data-tema="pro"] .hds-marca{display:none;}
}
"""

STIL_CLASIC = """
html.hds-cadru[data-tema="clasic"]{font-size:17px;--h-antet:72px;}
@media (min-width:760px){ html.hds-cadru[data-tema="clasic"]{font-size:19px;} }
html.hds-cadru[data-tema="clasic"] body{background:var(--fundal);padding-left:32px;padding-right:32px;--st:32px;}
@media (max-width:759px){ html.hds-cadru[data-tema="clasic"] body{padding-left:16px;padding-right:16px;--st:16px;} }
/* antetul: HD SATELIT | Meniu › ... ; in dreapta receptorul cu starea, ceasul si butonul mare Meniu */
html[data-tema="clasic"] .hds-antet{background:var(--fundal);border-bottom:1px solid var(--rand);
  margin-right:calc(-1 * var(--st));}
html[data-tema="clasic"] .hds-antet-bara{padding:8px var(--st);gap:6px 18px;}
html[data-tema="clasic"] .hds-marca{order:1;font-size:1.3rem;text-transform:uppercase;letter-spacing:.06em;}
html[data-tema="clasic"] .hds-marca .hds-sigla{background:none;border:0;width:30px;height:30px;}
html[data-tema="clasic"] .hds-sep{order:2;font-size:1.2rem;color:var(--bordura);}
html[data-tema="clasic"] .hds-cale{order:3;flex:1 1 auto;font-size:1.05rem;}
html[data-tema="clasic"] .hds-cale [aria-current]{font-weight:500;}
html[data-tema="clasic"] .hds-stare{order:4;font-size:.95rem;color:var(--text);}
html[data-tema="clasic"] .hds-receptor{order:4;font-size:.95rem;color:var(--text-slab);}
html[data-tema="clasic"] .hds-receptor::after{content:" \\00B7";}
html[data-tema="clasic"] .hds-retea{order:5;}
html[data-tema="clasic"] .hds-ceas{order:5;font-size:1.1rem;font-weight:400;color:var(--text);padding-left:16px;
  border-left:1px solid var(--rand);}
html.hds-cadru[data-tema="clasic"] .hds-buton-meniu{order:6;min-height:48px;padding:0 26px;border-radius:4px;border:0;
  background:var(--accent);color:#fff;font-size:1rem;font-weight:500;}
html.hds-cadru[data-tema="clasic"] .hds-buton-meniu:hover{background:var(--accent);filter:brightness(1.12);}
/* sertarul meniului: randuri pline, ca meniul de pe televizor */
html[data-tema="clasic"] .hds-meniu{width:min(92vw,440px);font-size:1rem;background:var(--fundal);}
html[data-tema="clasic"] .hds-meniu-cap{padding:16px 16px 16px 24px;border-bottom:2px solid var(--chihlimbar);}
html[data-tema="clasic"] .hds-meniu-cap .hds-sigla{background:none;border:0;}
html[data-tema="clasic"] .hds-meniu-cap strong{text-transform:uppercase;letter-spacing:.06em;}
html[data-tema="clasic"] .hds-meniu .hds-grupa{margin:0 12px 3px;}
html[data-tema="clasic"] .hds-meniu details>summary{min-height:56px;padding:8px 20px;background:var(--rand);
  border-radius:4px;font-weight:500;color:var(--text);margin-bottom:3px;}
html[data-tema="clasic"] .hds-meniu details>summary .hds-ic{width:24px;height:24px;color:var(--text-2);}
html[data-tema="clasic"] .hds-meniu .hds-subgrupa>summary{padding-left:40px;min-height:50px;font-size:.92rem;
  color:var(--text-2);}
html[data-tema="clasic"] .hds-meniu a{min-height:52px;padding:8px 20px 8px 54px;margin-bottom:3px;
  background:var(--rand);background:color-mix(in srgb,var(--rand) 55%,var(--fundal));border-radius:4px;color:var(--text);font-size:.95rem;}
html[data-tema="clasic"] .hds-meniu .hds-subgrupa a{padding-left:70px;}
html[data-tema="clasic"] .hds-meniu a:has(> .hds-ic){padding-left:20px;}
html[data-tema="clasic"] .hds-meniu a .hds-ic{width:24px;height:24px;color:var(--text-2);}
html[data-tema="clasic"] .hds-meniu ul>li>a.hds-sus{padding-left:20px;background:var(--rand);font-weight:500;}
html[data-tema="clasic"] .hds-meniu a:hover,html[data-tema="clasic"] .hds-meniu details>summary:hover,
html[data-tema="clasic"] .hds-meniu a[aria-current="page"]{background:var(--ales);color:var(--ales-text);
  box-shadow:inset 6px 0 0 var(--chihlimbar);}
html[data-tema="clasic"] .hds-meniu>ul,html[data-tema="clasic"] .hds-cauta{margin:0 12px;}
html[data-tema="clasic"] .hds-cauta{padding:14px 0 10px;}
html[data-tema="clasic"] .hds-cauta input,html[data-tema="clasic"] .hds-cauta button{min-height:52px;}
/* componentele paginilor: titlul mare cu linia chihlimbarie, fara carduri, randuri pline cu 3 px intre ele */
html.hds-cadru[data-tema="clasic"] h1{font-size:2.6rem;
  font-weight:300;letter-spacing:-.025em;line-height:1.2;margin:8px 0 24px;padding-bottom:14px;
  border-bottom:2px solid var(--chihlimbar);color:var(--text);}
html.hds-cadru[data-tema="clasic"] .card{background:none;border:0;border-radius:0;padding:0;box-shadow:none;
  margin-bottom:26px;}
html.hds-cadru[data-tema="clasic"] .card h2,html.hds-cadru[data-tema="clasic"] .card>h2{font-size:.82rem;
  font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--text-slab);margin:0 0 10px;padding:0;
  border:0;}
html.hds-cadru[data-tema="clasic"] .status-linie,html.hds-cadru[data-tema="clasic"] .rand,
html.hds-cadru[data-tema="clasic"] ul.ecrane li{background:var(--rand);border:0;border-radius:4px;
  padding:14px 22px;margin:0 0 3px;min-height:56px;align-items:center;font-size:1.05rem;}
html.hds-cadru[data-tema="clasic"] .status-linie:last-child,html.hds-cadru[data-tema="clasic"] .rand:last-child{
  border-bottom:0;}
html.hds-cadru[data-tema="clasic"] .status-linie:hover,html.hds-cadru[data-tema="clasic"] .rand:hover,
html.hds-cadru[data-tema="clasic"] ul.ecrane li:hover,html.hds-cadru[data-tema="clasic"] .rand.ales{
  background:var(--ales);color:var(--ales-text);box-shadow:inset 6px 0 0 var(--chihlimbar);}
html.hds-cadru[data-tema="clasic"] .rand:hover label,html.hds-cadru[data-tema="clasic"] .status-linie:hover>span,
html.hds-cadru[data-tema="clasic"] ul.ecrane li:hover a{color:var(--ales-text);}
html.hds-cadru[data-tema="clasic"] .status-linie>span:first-child{color:var(--text);}
html.hds-cadru[data-tema="clasic"] ul.ecrane li a{color:var(--text);text-decoration:none;display:block;}
html.hds-cadru[data-tema="clasic"] button:not(.hds-b){min-height:48px;background:var(--buton);color:var(--text);
  border:1px solid var(--bordura);border-radius:8px;font-family:inherit;font-weight:500;}
html.hds-cadru[data-tema="clasic"] button:not(.hds-b):hover:not(:disabled){background:var(--buton-peste);}
html.hds-cadru[data-tema="clasic"] button.verde,html.hds-cadru[data-tema="clasic"] button.principal,
html.hds-cadru[data-tema="clasic"] .butoane button.principal,html.hds-cadru[data-tema="clasic"] button.albastru{
  background:var(--accent);border-color:var(--accent);color:#fff;border-radius:4px;padding-left:28px;
  padding-right:28px;}
html.hds-cadru[data-tema="clasic"] button.rosu{background:var(--pericol-fond);color:var(--eroare);
  border-color:var(--bordura);border-color:color-mix(in srgb,var(--eroare) 35%,transparent);}
html.hds-cadru[data-tema="clasic"] select,html.hds-cadru[data-tema="clasic"] textarea,
html.hds-cadru[data-tema="clasic"] input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]){
  min-height:48px;background:var(--camp);color:var(--text);border:1px solid var(--bordura);border-radius:8px;
  font-family:inherit;}
html.hds-cadru[data-tema="clasic"] select:focus,html.hds-cadru[data-tema="clasic"] input:focus{
  border-color:var(--chihlimbar);}
html.hds-cadru[data-tema="clasic"] input[type=checkbox],html.hds-cadru[data-tema="clasic"] input[type=radio],
html.hds-cadru[data-tema="clasic"] input[type=range]{accent-color:var(--chihlimbar);}
html.hds-cadru[data-tema="clasic"] table{border-collapse:separate;border-spacing:0 3px;}
html.hds-cadru[data-tema="clasic"] th{font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em;
  color:var(--text-slab);background:none;border:0;}
html.hds-cadru[data-tema="clasic"] td{background:var(--rand);border:0;}
html.hds-cadru[data-tema="clasic"] tr:hover>td{background:var(--ales);color:var(--ales-text);}
html.hds-cadru[data-tema="clasic"] details>summary{font-weight:500;}
html.hds-cadru[data-tema="clasic"] .taste button,html.hds-cadru[data-tema="clasic"] .taste-nr button,
html.hds-cadru[data-tema="clasic"] .captura-butoane button{background:var(--rand);border:1px solid var(--bordura);
  border-radius:4px;min-height:56px;font-size:1rem;}
html.hds-cadru[data-tema="clasic"] .taste button:nth-child(5){background:var(--accent);color:#fff;
  border:2px solid var(--chihlimbar);font-weight:700;}
html.hds-cadru[data-tema="clasic"] .culori button{border-radius:4px;min-height:56px;font-size:.95rem;
  box-shadow:inset 0 4px 0 rgba(255,255,255,.35);}
html.hds-cadru[data-tema="clasic"] .captura-cutie{border-radius:4px;}
html.hds-cadru[data-tema="clasic"] button.canal{background:var(--rand);border:0;border-radius:4px;min-height:60px;
  font-weight:400;}
html.hds-cadru[data-tema="clasic"] button.canal:hover{background:var(--ales);color:var(--ales-text);
  box-shadow:inset 6px 0 0 var(--chihlimbar);}
html.hds-cadru[data-tema="clasic"] button:not(.hds-b):active:not(:disabled){filter:brightness(1.3);}
html[data-tema="clasic"] .hds-jos{background:var(--antet);}
html[data-tema="clasic"] .hds-jos [aria-current="page"]{box-shadow:inset 0 3px 0 var(--chihlimbar);}
html.hds-cadru[data-tema="clasic"] .butoane{gap:12px;}
html.hds-cadru[data-tema="clasic"] .culori{gap:6px;}
/* tastele colorate ale telecomenzii din panou raman colorate in ambele teme (dupa regulile generale ale butoanelor) */
html.hds-cadru button.b-rosu:not(.hds-b){background:var(--rosu);border-color:var(--rosu);color:#fff;}
html.hds-cadru button.b-verde:not(.hds-b){background:var(--verde);border-color:var(--verde);color:#fff;}
html.hds-cadru button.b-galben:not(.hds-b){background:var(--galben);border-color:var(--galben);color:#241d00;}
html.hds-cadru button.b-albastru:not(.hds-b){background:var(--albastru);border-color:var(--albastru);color:#fff;}
/* telecomanda panoului (plugin._htmlTelecomanda; fisa Stitch "Panou Control & Telecomanda"), in ambele teme: tastele
   mici (nu de 48 px ca butoanele obisnuite din Clasic), cercul cu OK, sagetile, Power, culorile si comutatorul
   Compact | Toate tastele dupa regulile lor, peste regulile generale ale butoanelor si peste :hover. Ordinea conteaza:
   intai fundalul tastelor in fiecare tema, apoi tastele deosebite. */
html.hds-cadru[data-tema] .tl button.tl-t{min-height:var(--tl-h);padding:0 4px;font-size:13px;letter-spacing:0;}
html.hds-cadru[data-tema="pro"] .tl{background:var(--panou-2);box-shadow:inset 0 1px 0 0 rgba(255,255,255,.07),
  0 8px 24px -4px rgba(0,0,0,.45);}
html.hds-cadru[data-tema="clasic"] .tl,html.hds-cadru[data-tema="clasic"] .tl-rocker{border-radius:4px;}
html.hds-cadru[data-tema="clasic"] .tl button.tl-t{background:var(--rand);border-radius:4px;font-weight:500;}
html.hds-cadru[data-tema] .tl .tl-cifre button.tl-t{font-size:15px;}
html.hds-cadru[data-tema] .tl .tl-culori button.tl-t{min-height:30px;border-radius:999px;font-size:12px;}
html.hds-cadru[data-tema] .tl button.tl-power,html.hds-cadru[data-tema] .tl button.tl-power:hover:not(:disabled){
  background:var(--pericol-fond);color:var(--eroare);}
html.hds-cadru[data-tema] .tl button.tl-rec{color:var(--eroare);}
html.hds-cadru[data-tema] .tl button.tl-t.b-rosu,html.hds-cadru[data-tema] .tl button.tl-t.b-rosu:hover:not(:disabled){
  background:var(--rosu);border-color:var(--rosu);color:#fff;}
html.hds-cadru[data-tema] .tl button.tl-t.b-verde,html.hds-cadru[data-tema] .tl button.tl-t.b-verde:hover:not(:disabled){
  background:var(--verde);border-color:var(--verde);color:#fff;}
html.hds-cadru[data-tema] .tl button.tl-t.b-galben,html.hds-cadru[data-tema] .tl button.tl-t.b-galben:hover:not(:disabled){
  background:var(--galben);border-color:var(--galben);color:#241d00;}
html.hds-cadru[data-tema] .tl button.tl-t.b-albastru,
html.hds-cadru[data-tema] .tl button.tl-t.b-albastru:hover:not(:disabled){background:var(--albastru);
  border-color:var(--albastru);color:#fff;}
html.hds-cadru[data-tema] .tl .tl-dpad button.tl-sageata{width:44px;min-height:40px;background:transparent;
  border-color:transparent;}
html.hds-cadru[data-tema] .tl .tl-dpad button.tl-sageata:hover:not(:disabled){background:var(--buton-peste);}
html.hds-cadru[data-tema] .tl .tl-dpad button.tl-ok,html.hds-cadru[data-tema] .tl .tl-dpad button.tl-ok:hover:not(:disabled){
  min-height:60px;border-radius:50%;border-color:var(--accent);background:var(--accent);color:#fff;font-size:16px;
  font-weight:700;}
/* butoanele alese (optiunile din Cautare canale, filele cu aria-pressed): accentul temei, peste stilul obisnuit al
   butoanelor temei, care altfel le acoperea si nu se vedea ce e ales; steaua si comutatorul telecomenzii au stilul lor */
html.hds-cadru[data-tema] button.ales:not(.hds-b),html.hds-cadru[data-tema] button.ales:not(.hds-b):hover:not(:disabled),
html.hds-cadru[data-tema] button[aria-pressed="true"]:not(.hds-b):not(.stea),
html.hds-cadru[data-tema] button[aria-pressed="true"]:not(.hds-b):not(.stea):hover:not(:disabled){
  background:var(--accent);color:#fff;border-color:var(--accent);font-weight:700;}
html.hds-cadru[data-tema] .tl .tl-comutator button{min-height:32px;padding:0 10px;border:0;border-radius:6px;
  background:transparent;color:var(--text-slab);font-size:12px;}
html.hds-cadru[data-tema] .tl .tl-comutator button[aria-pressed="true"],
html.hds-cadru[data-tema] .tl .tl-comutator button[aria-pressed="true"]:hover:not(:disabled){background:var(--accent);
  color:#fff;}
html.hds-cadru[data-tema="pro"] .tl .tl-dpad button.tl-ok{box-shadow:0 0 12px 0 rgba(55,78,161,.45);
  box-shadow:0 0 12px 0 color-mix(in srgb,var(--accent) 45%,transparent);}
html.hds-cadru[data-tema="clasic"] .tl .tl-dpad button.tl-ok{border:2px solid var(--chihlimbar);}
html.hds-cadru[data-tema="clasic"] .tl .tl-comutator{border-radius:4px;}
"""

_STIL = {}


def stil(c=None):
	"""Tot stilul cadrului: fonturile, variabilele celor doua teme din culorile date si asezarea. Tinut minte pe
	culori (cel mult 16 seturi: fiecare browser isi poate alege paleta)."""
	if c is None:
		c = culoriSkin()
	cheie = tuple(sorted(c.items()))
	text = _STIL.get(cheie)
	if text is None:
		if len(_STIL) >= 16:
			_STIL.clear()
		text = "".join(_blocVariabile(t, c) for t in TEME) + STIL_COMUN + STIL_PRO + STIL_CLASIC
		_STIL[cheie] = text
	return text


# compatibil cu probele si paginile care citeau STIL_CADRU (asezarea, fara variabile)
STIL_CADRU = STIL_COMUN + STIL_PRO + STIL_CLASIC

_RE_STIL = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.S | re.I)
_RE_HEX = re.compile(r"(--[A-Za-z0-9_-]+\s*:\s*)?(#[0-9a-fA-F]{6})\b")
_RE_COLOR = re.compile(r"(^|[;{\s])(color\s*:\s*)(#[0-9a-fA-F]{6})\b")


def culoriPeTema(css):
	"""Culorile scrise direct de paginile vechi (CULORI_SUPRAFETE oriunde, CULORI_TEXT numai la „color:”) puse pe
	variabilele temei. Definitiile de variabile ale paginii (:root{--fundal:#14171c}) raman cum sunt: tema le
	redefineste ea, cu un selector mai tare (altfel ar iesi --fundal:var(--fundal), o variabila care se cere pe ea)."""
	css = _RE_COLOR.sub(lambda m: m.group(1) + m.group(2) + CULORI_TEXT.get(m.group(3).lower(), m.group(3)), css)
	return _RE_HEX.sub(lambda m: m.group(0) if m.group(1) else CULORI_SUPRAFETE.get(m.group(2).lower(), m.group(2)),
		css)


# ------------------------------------------------------------------ meniul pe grupe
def _cale(href):
	"""Calea fara fragment (pentru potrivirea cu pagina curenta); /setari?id= isi pastreaza id-ul."""
	return (href or "").split("#", 1)[0]


def _intrare(c):
	"""O intrare din meniu_web.arbore() -> {"text", "href", "tv", "id"} sau None (nu se deschide din web)."""
	if c.get("web"):
		return {"text": c["text"], "href": c["web"], "tv": False, "id": c.get("id") or ""}
	if c.get("setup"):
		return {"text": c["text"], "href": "/setari?id=" + c["setup"], "tv": False, "id": c.get("id") or ""}
	if c.get("televizor") and c.get("id"):
		return {"text": c["text"], "href": "/meniu#i-" + c["id"], "tv": True, "id": c["id"]}
	return None


def _grupa(g, adancime):
	"""O grupa din arbore -> {"text", "href", "copii", "id"} sau None cand nu are nimic de aratat."""
	copii = []
	for c in g.get("copii", []):
		if c.get("tip") == "grup":
			x = _grupa(c, adancime + 1)
		else:
			x = _intrare(c)
		if x is not None:
			copii.append(x)
	href = g.get("web") or ""
	if href and any(x.get("href") == href for x in copii):
		href = ""   # pagina grupei e deja la una dintre intrari (de exemplu Acces condiționat)
	if not copii and not href:
		return None
	return {"text": g.get("text") or "", "href": href, "copii": copii, "id": g.get("id") or ""}


def _toateCaile(lista, rez):
	"""Caile paginilor din meniu (fara intrarile TV, care duc numai la o ancora din /meniu)."""
	for x in lista:
		if x.get("href") and not x.get("tv"):
			rez.add(_cale(x["href"]).split("?", 1)[0])
		_toateCaile(x.get("copii", []), rez)
	return rez


def registru(panou):
	"""[(cale, text)] din registrul paginilor (primul <footer> al textului dat, dupa _legaturiDisponibile: numai
	paginile care exista, cu semnele de stare), in ordinea de acolo."""
	a = panou.find("<footer>")
	b = panou.find("</footer>", a + 1)
	if a < 0 or b < 0:
		return []
	return [(m.group(1), m.group(2)) for m in re.finditer(r'<a href="(/[^"#?]*)">([^<]+)</a>', panou[a:b])]


def meniu(arbore, legaturi, rute):
	"""Grupele meniului web: [{"text", "href", "copii", "fel"}]. `arbore` = meniu_web.arbore()["meniu"] (sau None),
	`legaturi` = registru(...), `rute` = numele rutelor de pe radacina (set de str), pentru grupa „Principal”."""
	grupe = []
	principal = []
	for href, text in PRINCIPAL:
		ruta = href.strip("/").split("/", 1)[0]
		if href == "/" or ruta in rute:
			principal.append({"text": _t(text), "href": href, "tv": False})
	grupe.append({"text": _t("Principal"), "href": "", "copii": principal, "fel": "principal"})
	tv = []
	if arbore:
		for c in arbore.get("copii", []):
			if c.get("tip") == "grup":
				x = _grupa(c, 1)
				if x is not None:
					x["fel"] = "grupa"
					tv.append(x)
			else:
				x = _intrare(c)
				if x is not None:
					x["fel"] = "intrare"
					tv.append(x)
	grupe.extend(tv)
	vazute = _toateCaile(grupe, set())
	alte = []
	for href, text in legaturi:
		if href not in vazute:
			vazute.add(href)
			alte.append({"text": text, "href": href, "tv": False})
	if alte:
		grupe.append({"text": _t("Alte pagini"), "href": "", "copii": alte, "fel": "alte"})
	return grupe


def _gaseste(lista, cale, parinti):
	"""Lantul de noduri (de la grupa de sus pana la intrarea cu href == cale), sau None; prima potrivire castiga."""
	for x in lista:
		if x.get("href") and not x.get("tv") and _cale(x["href"]) == cale:
			return parinti + [x]
		if x.get("copii"):
			gasit = _gaseste(x["copii"], cale, parinti + [x])
			if gasit is not None:
				return gasit
	return None


def drumPagina(grupe, cale, titlu=""):
	"""Calea din antet: [(text, href sau "")]. Pagina din meniu: „Meniu” sau „Panou”, grupele, pagina; altfel
	pagina-parinte (PARINTI) si titlul paginii."""
	if cale in ("/", "/panou"):
		return [(_t("Panou"), "")]
	lant = _gaseste(grupe, cale, [])
	if lant is None and "?" in cale:
		lant = _gaseste(grupe, cale.split("?", 1)[0], [])
	if lant is not None:
		rad = (_t("Panou"), "/") if lant[0].get("fel") in ("principal", "alte") else (_t("Meniu"), "/meniu")
		drum = [rad]
		for x in lant[1:-1] if lant[0].get("fel") in ("principal", "alte") else lant[:-1]:
			drum.append((x["text"], x.get("href") or ""))
		drum.append((lant[-1]["text"], ""))
		return drum
	parinte = PARINTI.get(cale.split("?", 1)[0])
	if parinte:
		drum = drumPagina(grupe, parinte)
		if drum and drum[-1][1] == "":
			drum[-1] = (drum[-1][0], parinte)
		return drum + [(titlu or cale, "")]
	return [(_t("Panou"), "/"), (titlu or cale, "")]


def _cuJeton(href, jeton):
	"""Adresa cu ?token= (modul jeton); HTML-ul o scapa abia la scriere."""
	if not jeton:
		return href
	from urllib.parse import quote
	parte, _sep, fragment = href.partition("#")
	parte = parte + ("&" if "?" in parte else "?") + "token=" + quote(jeton, safe="")
	return parte + ("#" + fragment if fragment else "")


def _iconita(x, sus):
	"""Iconita unei legaturi: numai pe randurile de sus (Principal si intrarile de sus); altfel nimic."""
	if not sus:
		return u""
	nume = ICONITE_MENIU.get(x.get("id") or "") or ICONITE_MENIU.get(_cale(x.get("href") or "")) or "alte"
	return _ic(nume)


def _legaturaHtml(x, cale, jeton, clasa="", sus=False):
	# o intrare TV duce la o ancora din /meniu: nu e pagina curenta nici cand esti pe /meniu
	curent = not x.get("tv") and _cale(x["href"]) == cale
	semn = ""
	if x.get("tv"):
		semn = (u'<span class="hds-semn-tv" aria-hidden="true">TV</span><span class="hds-ascuns"> (%s)</span>'
			% _e(_t("se deschide pe televizor")))
	return u'<li><a%s href="%s"%s>%s%s%s</a></li>' % (' class="%s"' % clasa if clasa else "",
		_e(_cuJeton(x["href"], jeton)), ' aria-current="page"' if curent else "", _iconita(x, sus), _e(x["text"]), semn)


def _contine(x, cale):
	if x.get("href") and not x.get("tv") and _cale(x["href"]) == cale:
		return True
	return any(_contine(y, cale) for y in x.get("copii", []))


def _grupaHtml(g, cale, jeton, clasa):
	deschis = g.get("fel") == "principal" or _contine(g, cale)
	sus = clasa == "hds-grupa"
	ic = _ic(ICONITE_MENIU.get(g.get("id") or "", "alte")) if sus and g.get("fel") == "grupa" else u""
	parti = [u'<details class="%s"%s><summary>%s%s</summary><ul>' % (clasa, " open" if deschis else "", ic,
		_e(g["text"]))]
	if g.get("href"):
		parti.append(_legaturaHtml({"text": g["text"], "href": g["href"]}, cale, jeton))
	for x in g.get("copii", []):
		if "copii" in x:
			parti.append(u"<li>" + _grupaHtml(x, cale, jeton, "hds-subgrupa") + u"</li>")
		else:
			parti.append(_legaturaHtml(x, cale, jeton, sus=g.get("fel") == "principal"))
	parti.append(u"</ul></details>")
	return u"".join(parti)


def meniuHtml(grupe, cale, jeton=""):
	"""Grupele ca <details> (fara JavaScript se deschid si se inchid singure), pagina curenta cu aria-current."""
	parti = []
	for g in grupe:
		if "copii" in g:
			parti.append(_grupaHtml(g, cale, jeton, "hds-grupa"))
		else:
			parti.append(u"<ul>%s</ul>" % _legaturaHtml(g, cale, jeton, "hds-sus", sus=True))
	return u"".join(parti)


def baraJosHtml(cale, rute, jeton=""):
	"""Bara de jos de pe telefon: paginile tastelor (numai cele cu ruta) si „Mai mult”, care deschide meniul."""
	parti = []
	for href, text, ic in BARA_JOS:
		ruta = href.strip("/").split("/", 1)[0]
		if href != "/" and ruta not in rute:
			continue
		curent = cale == href or (href == "/" and cale == "/panou")
		parti.append(u'<a href="%s"%s>%s<span>%s</span></a>' % (_e(_cuJeton(href, jeton)),
			' aria-current="page"' if curent else "", _ic(ic), _e(_t(text))))
	parti.append(u'<button type="button" class="hds-b" id="hdsJosMeniu" aria-controls="hdsMeniu" aria-expanded="false">%s<span>%s'
		u'</span></button>' % (_ic("mai-mult"), _e(_t("Mai mult"))))
	return u'<nav class="hds-jos" aria-label="%s">%s</nav>' % (_e(_t("Paginile principale")), u"".join(parti))


# Derularea textului de un rand care nu incape (clasa hds-derulant), pereche cu stilul din STIL_COMUN: numai textul
# care iese din cutie intra intr-un span interior (hds-derulant-in), mutat de un @keyframes facut aici pentru durata
# lui (opririle raman de 2 s la orice lungime). Se masoara dupa incarcare, la schimbarea textului (MutationObserver), a
# marimii (ResizeObserver) si dupa incarcarea fonturilor; o pagina care isi pune singura alt font cheama
# window.HDS_DERULANT.verifica(). Acelasi text pus din nou (starea din antet) continua derularea de unde era.
SCRIPT_DERULANT = u"""<script>
(function(){
  if(window.HDS_DERULANT || !window.requestAnimationFrame || !document.body){ return; }
  var VITEZA = 40, OPRIRE = 2, TOLERANTA = 1, C = "hds-derulant", IN = "hds-derulant-in";
  var ACTIV = ":hover,:focus-within,.ales,[aria-selected=true],[aria-current=true],[aria-current=page]";
  var coada = [], ceas = 0, foaie = null, facute = {}, MO = null, RO = null;
  // un @keyframes pentru fiecare durata a mersului, in pasi de 0,25 s: 2 s pe loc, mersul, 2 s la capat
  function cadre(pasi){
    var n = "hds-der-" + pasi;
    if(!facute[n]){
      facute[n] = 1;
      var t = 2 * OPRIRE + pasi / 4, a = (100 * OPRIRE / t).toFixed(3), b = (100 * (OPRIRE + pasi / 4) / t).toFixed(3);
      if(!foaie){ foaie = document.createElement("style"); foaie.id = "hdsDerulantCadre"; document.head.appendChild(foaie); }
      foaie.appendChild(document.createTextNode("@keyframes " + n + "{0%," + a + "%{transform:translateX(0)}" + b +
        "%,100%{transform:translateX(var(--hds-der-d))}}"));
    }
    return n;
  }
  function cere(el){
    if(!el._hdsDerC){ el._hdsDerC = 1; coada.push(el); }
    if(!ceas){ ceas = requestAnimationFrame(lucreaza); }
  }
  function interior(el){
    var x = el.firstChild;
    return x && x === el.lastChild && x.nodeType === 1 && x.classList.contains(IN) ? x : null;
  }
  function areVechi(el){
    for(var x = el.firstElementChild; x; x = x.nextElementSibling){ if(x.classList.contains(IN)){ return true; } }
    return false;
  }
  function desface(el, x){
    while(x.firstChild){ el.insertBefore(x.firstChild, x); }
    el.removeChild(x);
  }
  function activ(r){ try { return r.matches(ACTIV); } catch(e) { return true; } }
  function urmareste(el){
    if(el._hdsDerO){ return; }
    el._hdsDerO = 1;
    if(RO){ RO.observe(el); } else { cere(el); }
  }
  function cauta(n){
    if(n.nodeType !== 1){ return; }
    if(n.classList.contains(C)){ urmareste(n); }
    if(n.firstElementChild){
      var l = n.getElementsByClassName(C);
      for(var i = 0; i < l.length; i++){ urmareste(l[i]); }
    }
  }
  function schimbari(l){
    for(var i = 0; i < l.length; i++){
      var r = l[i], t = r.target.nodeType === 1 ? r.target : r.target.parentElement;
      var el = t && t.closest ? t.closest("." + C) : null;
      if(el){ urmareste(el); cere(el); }
      for(var j = 0; j < r.addedNodes.length; j++){ cauta(r.addedNodes[j]); }
    }
  }
  function lucreaza(){
    // schimbarile paginii de dinaintea acestui cadru (alte requestAnimationFrame) intra si ele acum
    if(MO){ schimbari(MO.takeRecords()); }
    ceas = 0;
    var lista = coada, noi = [], gata = [];
    coada = [];
    try {
      // intai citirile, fara scrieri intre ele: ce iese din cutie
      lista.forEach(function(el){
        el._hdsDerC = 0;
        if(!el.isConnected){ return; }
        var x = interior(el);
        if(x){ gata.push([el, x]); }
        else if(areVechi(el) || el.scrollWidth - el.clientWidth > TOLERANTA){ noi.push(el); }
      });
      // textul care nu incape (si cel cu un span ramas langa alt text) intra intr-un span interior nou
      noi.forEach(function(el){
        for(var v = el.firstElementChild, u; v; v = u){ u = v.nextElementSibling; if(v.classList.contains(IN)){ desface(el, v); } }
        var x = document.createElement("span");
        x.className = IN;
        while(el.firstChild){ x.appendChild(el.firstChild); }
        el.appendChild(x);
        gata.push([el, x]);
      });
      // cat iese din cutie: latimea textului minus locul lui (fara padding)
      var cat = gata.map(function(p){
        var s = getComputedStyle(p[0]);
        return {d: p[1].offsetWidth - (p[0].clientWidth - (parseFloat(s.paddingLeft) || 0) - (parseFloat(s.paddingRight) || 0)),
          rtl: s.direction === "rtl"};
      });
      gata.forEach(function(p, i){
        var el = p[0], x = p[1], d = cat[i].d;
        // incape (alt text, alta latime): totul inapoi cum era
        if(d <= TOLERANTA){ desface(el, x); el._hdsDer = null; return; }
        var pasi = Math.max(1, Math.round(d * 4 / VITEZA)), n = cadre(pasi), t = 2 * OPRIRE + pasi / 4;
        var semn = n + " " + d + (cat[i].rtl ? " r" : "");
        if(x._hdsDerSemn === semn){ return; }
        var v = el._hdsDer, acum = Date.now(), w = 0, text = x.textContent, r = el.closest(".hds-derulant-rand");
        if(v && v.semn === semn && v.text === text && (!r || activ(r))){ w = ((acum - v.t0) / 1000) % t; }
        else { el._hdsDer = {semn: semn, text: text, t0: acum}; }
        x._hdsDerSemn = semn;
        x.style.setProperty("--hds-der-d", (cat[i].rtl ? d : -d) + "px");
        x.style.setProperty("--hds-der-t", t + "s");
        x.style.setProperty("--hds-der-w", (w ? -w.toFixed(2) : 0) + "s");
        x.style.setProperty("--hds-der-k", n);
      });
    } finally {
      // schimbarile facute aici nu se mai urmaresc
      if(MO){ MO.takeRecords(); }
    }
  }
  function toate(){
    var l = document.getElementsByClassName(C);
    for(var i = 0; i < l.length; i++){ urmareste(l[i]); cere(l[i]); }
  }
  function porneste(){
    if(window.ResizeObserver){
      RO = new ResizeObserver(function(l){
        l.forEach(function(e){
          var el = e.target;
          if(!el.isConnected){ RO.unobserve(el); el._hdsDerO = 0; return; }
          cere(el);
        });
      });
    } else { window.addEventListener("resize", toate); }
    toate();
    if(window.MutationObserver){
      MO = new MutationObserver(schimbari);
      MO.observe(document.body, {childList: true, subtree: true, characterData: true});
    }
    if(document.fonts){
      if(document.fonts.addEventListener){ document.fonts.addEventListener("loadingdone", toate); }
      if(document.fonts.ready){ document.fonts.ready.then(toate); }
    }
  }
  window.HDS_DERULANT = {verifica: toate};
  if(document.readyState === "loading"){ document.addEventListener("DOMContentLoaded", porneste); } else { porneste(); }
})();
</script>"""


SCRIPT_CADRU = u"""<script>
(function(){
  var h = document.documentElement, A = document.getElementById("hdsAntet"), M = document.getElementById("hdsMeniu");
  var B = document.getElementById("hdsMeniuButon"), U = document.getElementById("hdsUmbra");
  var I = document.getElementById("hdsMeniuInchide"), J2 = document.getElementById("hdsJosMeniu");
  if(!A || !M || !B){ return; }
  var deschizator = B;
  function deschide(da){
    h.classList.toggle("hds-meniu-deschis", da);
    B.setAttribute("aria-expanded", da ? "true" : "false");
    if(J2){ J2.setAttribute("aria-expanded", da ? "true" : "false"); }
    if(U){ U.hidden = !da; }
    if(da){
      var x = M.querySelector("[aria-current=page]") || M.querySelector("input");
      if(x){ setTimeout(function(){ x.focus(); }, 30); }
    } else if(deschizator && deschizator.offsetParent !== null){ deschizator.focus(); }
  }
  B.addEventListener("click", function(){ deschizator = B; deschide(!h.classList.contains("hds-meniu-deschis")); });
  if(J2){ J2.addEventListener("click", function(){ deschizator = J2; deschide(!h.classList.contains("hds-meniu-deschis")); }); }
  if(I){ I.addEventListener("click", function(){ deschide(false); }); }
  if(U){ U.addEventListener("click", function(){ deschide(false); }); }
  document.addEventListener("keydown", function(e){
    if(e.key === "Escape" && h.classList.contains("hds-meniu-deschis")){ deschide(false); }
  });
  var C = document.getElementById("hdsCeas");
  function ceas(){
    if(!C){ return; }
    var d = new Date();
    C.textContent = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }
  ceas();
  setInterval(ceas, 15000);
  var T = document.getElementById("hdsStareText"), P = document.getElementById("hdsStarePunct");
  var S = document.getElementById("hdsStare");
  // ca paginile: ?token= in modul jeton, altfel antetul X-HDS-CSRF (fara el raspunsul ar fi forma pentru aplicatii)
  var J = A.getAttribute("data-jeton") || "", K = A.getAttribute("data-csrf") || "";
  function arata(d){
    if(!d || !T){ return; }
    var standby = !!d.in_standby, nume = d.currservice_name || "";
    T.textContent = standby ? A.getAttribute("data-t-standby") : (nume || A.getAttribute("data-t-fara"));
    if(P){ P.className = "hds-punct" + (standby ? " standby" : (nume ? " pornit" : "")); }
    if(S){ S.classList.toggle("standby", standby); }
  }
  window.HDS_ANTET = {stare: arata};
  // pictograma retelei (stare_retea_web.py): starea si titlul vin de la receptor, la 15 s, si pe paginile cu panou;
  // desenul e simbolul #hr-<cheie> din pagina (se schimba numai href-ul lui <use>)
  var R = document.getElementById("hdsRetea");
  function retea(){
    if(!R || document.hidden){ return; }
    fetch("/api/stare-retea" + (J ? "?token=" + encodeURIComponent(J) : ""),
      {cache: "no-store", credentials: "same-origin", headers: J ? {} : {"X-HDS-CSRF": K}})
      .then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
        if(!d || !d.result){ return; }
        R.hidden = d.aratata === false;
        var u = R.querySelector("use");
        if(u && d.pictograma && document.getElementById("hr-" + d.pictograma)){ u.setAttribute("href", "#hr-" + d.pictograma); }
        R.setAttribute("data-cod", d.cod || "");
        R.title = d.titlu || "";
        R.setAttribute("aria-label", d.titlu || "");
      }).catch(function(){});
  }
  if(R){
    setInterval(retea, 15000);
    document.addEventListener("visibilitychange", function(){ if(!document.hidden){ retea(); } });
    window.HDS_ANTET.retea = retea;
  }
  if(A.getAttribute("data-panou") === "1"){ return; }
  var ultima = 0;
  function cere(){
    if(document.hidden){ return; }
    ultima = Date.now();
    fetch("/api/statusinfo" + (J ? "?token=" + encodeURIComponent(J) : ""),
      {cache: "no-store", credentials: "same-origin", headers: J ? {} : {"X-HDS-CSRF": K}})
      .then(function(r){ return r.ok ? r.json() : null; }).then(arata).catch(function(){});
  }
  cere();
  setInterval(cere, 15000);
  document.addEventListener("visibilitychange", function(){ if(!document.hidden && Date.now() - ultima > 15000){ cere(); } });
})();
</script>"""


def _pictogramaRetea():
	"""Pictograma retelei din antet (stare_retea_web.py), cu starea de acum; "" la orice eroare."""
	try:
		from . import stare_retea_web
		return stare_retea_web.antet_html()
	except Exception as eroare:
		_jurnal("pictograma retelei: %s" % eroare)
		return u""


def antetHtml(ctx):
	"""Antetul, umbra, meniul (sertarul sau bara din stanga) si bara de jos de pe telefon, plus scriptul lor.
	`ctx` vine din context()."""
	jeton = ctx.get("jeton") or ""
	cale = ctx.get("cale") or "/"
	drum = ctx.get("drum") or []
	elemente = []
	for i, (text, href) in enumerate(drum):
		if i == len(drum) - 1:
			elemente.append(u'<li class="hds-derulant" aria-current="page">%s</li>' % _e(text))
		elif href:
			elemente.append(u'<li><a href="%s">%s</a></li>' % (_e(_cuJeton(href, jeton)), _e(text)))
		else:
			elemente.append(u"<li>%s</li>" % _e(text))
	receptor = _e(ctx.get("nume") or "")
	if ctx.get("versiune"):
		receptor = (receptor + u" · " if receptor else u"") + _e(ctx["versiune"])
	jeton_formular = u'<input type="hidden" name="token" value="%s">' % _e(jeton) if jeton else u""
	tema = ctx.get("tema") or TEMA_IMPLICITA
	nume_tema = _t("Pro") if tema == "pro" else _t("Clasic")
	rute = ctx.get("rute")
	if rute is None:
		rute = set(h.strip("/") for h, _t2, _i in BARA_JOS)
	return u"".join((
		_simboluri(),
		u'<header class="hds-antet" id="hdsAntet" data-jeton="%s" data-csrf="%s" data-panou="%s" data-t-standby="%s" '
		u'data-t-fara="%s">' % (_e(jeton), _e(ctx.get("csrf") or ""), "1" if cale in ("/", "/panou") else "0",
			_e(_t("Standby")), _e(_t("Niciun canal"))),
		u'<div class="hds-antet-bara">',
		u'<button type="button" class="hds-b hds-buton-meniu" id="hdsMeniuButon" aria-controls="hdsMeniu" aria-expanded="false">'
		u'%s<span>%s</span></button>' % (_ic("meniu"), _e(_t("Meniu"))),
		u'<a class="hds-marca" href="%s"><span class="hds-sigla">%s</span><span>HD <span class="hds-marca-2">Satelit</span></span></a>'
		% (_e(_cuJeton("/", jeton)), _ic("satelit")),
		u'<span class="hds-sep" aria-hidden="true">|</span>',
		u'<nav class="hds-cale" aria-label="%s"><ol>%s</ol></nav>' % (_e(_t("Unde ești")), u"".join(elemente)),
		u'<div class="hds-dreapta"><span class="hds-receptor hds-derulant">%s</span>' % receptor,
		u'<span class="hds-stare" id="hdsStare" role="status"><span class="hds-punct" id="hdsStarePunct"></span>'
		u'<span id="hdsStareText" class="hds-derulant">%s</span></span>' % _e(_t("Se citește starea...")),
		_pictogramaRetea(),
		u'<span class="hds-ceas" id="hdsCeas"></span></div>',
		u"</div></header>",
		u'<div class="hds-umbra" id="hdsUmbra" hidden></div>',
		u'<nav class="hds-meniu" id="hdsMeniu" aria-label="%s">' % _e(_t("Meniul receptorului")),
		u'<div class="hds-meniu-cap"><span class="hds-sigla">%s</span><div><strong>HD Satelit'
		u'<span class="hds-punct"></span></strong><small class="hds-derulant">%s</small></div>' % (_ic("satelit"), receptor),
		u'<button type="button" class="hds-b hds-meniu-inchide" id="hdsMeniuInchide" aria-label="%s">%s</button></div>'
		% (_e(_t("Închide meniul")), _ic("inchide")),
		u'<form class="hds-cauta" action="/cauta-setari" method="get" role="search">'
		u'<input type="search" name="q" maxlength="60" placeholder="%s" aria-label="%s" autocomplete="off">%s'
		u'<button type="submit" class="hds-b">%s</button></form>' % (_e(_t("Caută setări")), _e(_t("Caută setări")), jeton_formular,
			_e(_t("Caută"))),
		ctx.get("meniu_html") or u"",
		u'<p class="hds-meniu-jos">%s <a href="%s">%s</a></p>' % (_e(_t("Tema interfeței web: %s.") % nume_tema),
			_e(_cuJeton("/setari#aspectWeb", jeton)), _e(_t("Schimbă tema și culorile"))),
		u"</nav>",
		baraJosHtml(cale, rute, jeton),
		SCRIPT_CADRU,
		SCRIPT_DERULANT,
	))


_RE_HTML = re.compile(r"<html\b([^>]*)>", re.I)
_RE_BODY = re.compile(r"<body\b[^>]*>", re.I)
_RE_TITLU = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def titluPagina(html):
	m = _RE_TITLU.search(html)
	if not m:
		return ""
	return (m.group(1).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip())[:120]


def imbraca(html, ctx):
	"""Pagina cu cadrul: tema si culorile pe <html>, culorile vechi pe variabile, stilul inaintea lui </head>,
	antetul si meniul imediat dupa <body>. O pagina fara aceste repere se intoarce neschimbata."""
	m_html = _RE_HTML.search(html)
	a_head = html.find("</head>")
	m_body = _RE_BODY.search(html)
	if m_html is None or a_head < 0 or m_body is None or not (m_html.end() <= a_head < m_body.start()):
		return html
	if 'id="hdsAntet"' in html:
		return html
	tema = ctx.get("tema") if ctx.get("tema") in TEME else TEMA_IMPLICITA
	atribute = m_html.group(1)
	if "class=" in atribute:
		atribute = re.sub(r'class="([^"]*)"', lambda m: 'class="%s hds-cadru"' % m.group(1), atribute, count=1)
	else:
		atribute += ' class="hds-cadru"'
	atribute += ' data-tema="%s"' % tema
	if ctx.get("culori"):
		atribute += ' data-culori="%s"' % _e(ctx["culori"])
	cap = html[m_html.end():a_head]
	cap = _RE_STIL.sub(lambda m: m.group(1) + culoriPeTema(m.group(2)) + m.group(3), cap)
	stil_text = u'<style id="hdsCadruStil">%s</style>\n' % (ctx.get("stil") or stil())
	return u"".join((html[:m_html.start()], u"<html%s>" % atribute, cap, stil_text, html[a_head:m_body.end()],
		u"\n", antetHtml(ctx), u"\n", ctx.get("banda_nota") or u"", html[m_body.end():]))


# ------------------------------------------------------------------ contextul unei cereri pe receptor
_CACHE = {"cheie": None, "cand": 0.0, "grupe": None}
_VERSIUNE = {"semn": None, "text": ""}


def versiuneImagine(cale=None):
	""""0.2.8" din randul version= al /etc/image-version (16 cifre: felul, major, minor, revizia, data constructiei;
	19 cifre cand o parte are doua cifre: felul, apoi major, minor si revizia pe cate doua cifre, "0.3.10"); sir gol
	cand lipseste sau are alta forma. Recitit numai cand fisierul se schimba."""
	cale = cale or CALE_VERSIUNE
	try:
		semn = (cale, os.path.getmtime(cale))
	except OSError:
		return ""
	if _VERSIUNE["semn"] != semn:
		text = ""
		try:
			with open(cale, "rb") as f:
				for rand in f.read(4096).decode("utf-8", "replace").splitlines():
					cheie, _s, valoare = rand.partition("=")
					if cheie.strip() == "version":
						valoare = valoare.strip()
						if len(valoare) == 16 and valoare.isdigit():
							text = "%s.%s.%s" % (valoare[1], valoare[2], valoare[3])
						elif len(valoare) == 19 and valoare.isdigit() and valoare.isascii():
							text = "%d.%d.%d" % (int(valoare[1:3]), int(valoare[3:5]), int(valoare[5:7]))
						break
		except (IOError, OSError):
			text = ""
		_VERSIUNE.update(semn=semn, text=text)
	return _VERSIUNE["text"]


def numeReceptor():
	"""Numele receptorului in retea (cel dat routerului), ca in setarile de retea de pe televizor."""
	try:
		import socket
		nume = socket.gethostname().strip().split(".", 1)[0]
	except Exception:
		return ""
	if not nume or nume == "localhost":
		return ""
	return nume[:40]


def _cookie(request, nume):
	try:
		valoare = request.getCookie(nume.encode("ascii"))
	except Exception:
		valoare = None
	if isinstance(valoare, bytes):
		valoare = valoare.decode("ascii", "replace")
	return valoare


def temaDinCerere(request):
	"""Tema aleasa in acest browser (cookie-ul hds_tema), numai una din TEME; altfel cea implicita de pe receptor."""
	valoare = _cookie(request, COOKIE_TEMA)
	if valoare in TEME:
		return valoare
	return implicite()[0]


def culoriDinCerere(request):
	"""Schema de culori aleasa in acest browser (cookie-ul hds_culori): „tv”, „implicit” sau un id din palete.txt;
	altfel cea implicita de pe receptor."""
	valoare = _cookie(request, COOKIE_CULORI)
	if valoare and _RE_ID_PALETA.match(valoare) and culoareValida(valoare):
		return valoare
	return implicite()[1]


def caleCerere(request):
	"""Calea paginii, ca in href-urile meniului: /setari?id=<cheie> pastreaza id-ul, restul fara argumente."""
	cale = getattr(request, "path", b"/") or b"/"
	if isinstance(cale, bytes):
		cale = cale.decode("utf-8", "replace")
	cale = cale.split("?", 1)[0]
	if len(cale) > 1 and cale.endswith("/"):
		cale = cale[:-1]
	if cale == "/setari":
		ident = (getattr(request, "args", None) or {}).get(b"id")
		if ident:
			v = ident[0].decode("utf-8", "replace") if isinstance(ident[0], bytes) else str(ident[0])
			if re.match(r"^[A-Za-z0-9_.-]{1,64}$", v):
				return "/setari?id=" + v
	return cale or "/"


def _ruteRadacina(request):
	try:
		copii = request.site.resource.children
	except Exception:
		return set()
	rez = set()
	for nume in copii:
		rez.add(nume.decode("ascii", "replace") if isinstance(nume, bytes) else str(nume))
	return rez


def _cheieCache(rute, legaturi):
	from . import scanare_web
	try:
		semn = os.path.getmtime(scanare_web._caleMeniu())
	except OSError:
		semn = None
	try:
		from Components.config import config
		limba = config.osd.language.value
	except Exception:
		limba = ""
	return (semn, limba, scanare_web._nivelUtilizator(), tuple(sorted(rute)), legaturi)


def grupeMeniu(rute, legaturi):
	"""Grupele meniului, tinute minte cat nu se schimba menu.xml, limba, nivelul si rutele (cel mult DURATA_CACHE_S,
	ca semnele de stare si requires= sa se vada fara repornire). `legaturi`: registrul (lista) sau functia care il face,
	chemata numai cand grupele se refac (verifica accelerarea, procesorul, afisajul: nu la fiecare pagina)."""
	lista = None if callable(legaturi) else tuple(legaturi)
	cheie = _cheieCache(rute, lista)
	acum = time.monotonic()
	if _CACHE["grupe"] is not None and _CACHE["cheie"] == cheie and acum - _CACHE["cand"] < DURATA_CACHE_S:
		return _CACHE["grupe"]
	if lista is None:
		lista = tuple(legaturi())
	from . import meniu_web
	a = meniu_web.arbore()
	grupe = meniu(a.get("meniu") if a.get("result") else None, list(lista), rute)
	_CACHE.update(cheie=cheie, cand=acum, grupe=grupe)
	return grupe


def _registruPanou(P):
	try:
		# registrul cu numele traduse (plugin._registruTradus); pe un plugin.py mai vechi, ca inainte
		tradus = getattr(P, "_registruTradus", None)
		if tradus is not None:
			return registru(P._legaturiDisponibile(tradus()))
		return registru(P._legaturiDisponibile(getattr(P, "_REGISTRU_PAGINI", None) or P._PAGINA_PANOU))
	except Exception as eroare:
		_jurnal("registrul paginilor: %s" % eroare)
		return []


def context(request, html, P, jeton="", csrf=""):
	rute = _ruteRadacina(request)
	grupe = grupeMeniu(rute, lambda: _registruPanou(P))
	cale = caleCerere(request)
	culori = culoriDinCerere(request)
	c = culoriPaleta(culori) or culoriSkin()
	return {
		"tema": temaDinCerere(request),
		"culori": culori,
		"jeton": jeton,
		"csrf": csrf,
		"cale": cale,
		"rute": rute,
		"drum": drumPagina(grupe, cale, titluPagina(html)),
		"meniu_html": meniuHtml(grupe, cale, jeton),
		"nume": numeReceptor(),
		"versiune": versiuneImagine(),
		"stil": stil(c),
		"banda_nota": bandaNota(cale),
	}


def bandaNota(cale):
	"""Anuntul notei noi a beta testerilor (betatester_web.bandaNota), sus pe orice pagina afara de /beta-tester (care
	are caseta ei); "" fara nota veche sau la orice eroare."""
	if cale.rstrip("/") == "/beta-tester":
		return u""
	try:
		from .betatester_web import bandaNota as banda
		return banda() or u""
	except Exception as eroare:
		_jurnal("banda notei noi: %s" % eroare)
		return u""


def _antetRaspuns(request, nume):
	try:
		v = request.responseHeaders.getRawHeaders(nume)
	except Exception:
		return b""
	return (v or [b""])[-1] or b""


def deImbracat(request, corp):
	"""Raspunsul e o pagina HTML intreaga, de imbracat? (fara poarta: aceea se verifica in imbracaRaspuns)"""
	if not isinstance(corp, bytes) or not corp.startswith(b"<!DOCTYPE html>") or len(corp) > MAX_PAGINA:
		return False
	if getattr(request, "method", b"GET") not in (b"GET", b"HEAD"):
		return False
	if getattr(request, "code", 200) != 200:
		return False
	if not _antetRaspuns(request, b"content-type").lower().startswith(b"text/html"):
		return False
	if _antetRaspuns(request, b"content-disposition"):
		return False
	cale = getattr(request, "path", b"/") or b"/"
	if isinstance(cale, bytes):
		cale = cale.decode("utf-8", "replace")
	if cale.strip("/").split("/", 1)[0] in FARA_CADRU:
		return False
	return True


def imbracaRaspuns(request, corp):
	"""Pentru _CerereHds.render: corpul imbracat, sau acelasi corp cand nu e o pagina de imbracat, cand cererea n-a
	trecut poarta ori la orice eroare (pagina ramane cum era)."""
	try:
		if not deImbracat(request, corp):
			return corp
		from . import plugin as P
		if corp == P._PAGINA_ASOCIERE.encode("utf-8"):
			return corp
		mod, eroare = P._verificaAcces(request)
		if eroare is not None:
			return corp
		from . import paza_model_web
		if paza_model_web.inPaza():
			return corp
		jeton = P._jetonConfigurat() if mod == "jeton" else ""
		csrf = ""
		if not jeton:
			# acelasi token CSRF pe care il primesc paginile (CFG.csrf), pentru cererea de stare din antet
			secret, _browser = P._sesiuneDinCerere(request)
			csrf = P.csrfPentru(secret) if secret else ""
		html = corp.decode("utf-8", "surrogateescape")
		gata = imbraca(html, context(request, html, P, jeton, csrf))
		return gata.encode("utf-8", "surrogateescape")
	except Exception as eroare:
		_jurnal("pagina ramane fara cadru: %s" % eroare)
		return corp


# ------------------------------------------------------------------ fonturile (/cadru/<nume>.ttf)
_FONTURI_CITITE = {}


def caleFont(nume, dosare=None):
	if nume not in FONTURI:
		return None
	for dosar in dosare or DOSARE_FONTURI:
		cale = os.path.join(dosar, nume)
		if os.path.isfile(cale):
			return cale
	return None


def rute(resource):
	"""Resursa /cadru: numai cele trei fonturi ale skinului (FONTURI), fara poarta, ca /favicon.ico (antetul Host e
	verificat inainte, in _CerereHds.process); citite o data, tinute in memorie (~170 KB) si o saptamana in browser."""
	class CadruResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			nume = (getattr(request, "postpath", None) or [b""])[0]
			if isinstance(nume, bytes):
				nume = nume.decode("ascii", "replace")
			date = _FONTURI_CITITE.get(nume)
			if date is None:
				cale = caleFont(nume)
				if cale is not None:
					try:
						with open(cale, "rb") as f:
							date = f.read(512 * 1024)
						_FONTURI_CITITE[nume] = date
					except (IOError, OSError) as eroare:
						_jurnal("fontul %s: %s" % (nume, eroare))
			if date is None:
				request.setResponseCode(404)
				request.setHeader(b"content-type", b"text/plain; charset=utf-8")
				return b"nu exista"
			request.setHeader(b"content-type", b"font/ttf")
			request.setHeader(b"cache-control", b"public, max-age=604800")
			return date

	return CadruResource()


def stareJson():
	"""Pentru probe si depanare: implicitele, culorile skinului si perechile care nu trec (trebuie sa fie goale)."""
	c = culoriSkin()
	tema, culori = implicite()
	return json.dumps({"tema_implicita": tema, "culori_implicite": culori, "culori": c,
		"contrast": dict((t, verificaContrast(variabile(t, c))) for t in TEME)}, ensure_ascii=False)
