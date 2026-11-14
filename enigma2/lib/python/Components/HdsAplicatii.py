# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAplicatii: meniul „Aplicații” (0.7.5), ca pe televizoarele smart: o grila de carduri; fiecare card e o aplicatie.
# Ecranul e Screens/HdsAplicatii.py, perechea web HdsWebControl/aplicatii_tv_web.py (/aplicatii-tv). Aici stau partile
# fara ecran (lista, ordinea, ascunderea, mutarea in grila, harta tastelor, linia de comanda), ca probele de pe PC sa
# le foloseasca direct. Modulul nu importa nimic din enigma2 la incarcare.
#
# O aplicatie de acum e o SCURTATURA: un sit pentru televizor deschis pe tot ecranul in navigatorul imaginii
# (Plugins/Extensions/HdsNavigator, modul lansator.MOD_APLICATIE). Campurile unei scurtaturi:
#   id        numele scurt (litere mici, cifre, liniuta): ordinea, ascunderea, dosarul profilului;
#   titlu     ce scrie pe card (numele serviciului, netradus);
#   descriere un rand pentru banda de sub grila (tradus la afisare, N_ aici);
#   url       adresa deschisa;
#   agent     agentul de utilizator INTREG, sau "tv" = al televizorului ales in setari (agentTv); se da (--agent) numai
#             cand programul motorului stie optiunea;
#   adaos     text pus la coada agentului motorului (--agent-adaugat) cand agentul intreg nu se poate da;
#   script    scriptul tastelor pus in pagina (--script), numai cand programul il stie si fisierul exista;
#   taste     harta tastelor (HARTI_TASTE), tradusa de enigma2 inainte sa ajunga la navigator;
#   motor     "wpe" (hds-navigator, in imagine) sau "chromium" (hds-chromium, pachetul separat, cand exista);
#             fara programul cerut, aplicatia porneste pe "wpe". Omul nu alege motorul: e al scurtaturii.
#   culoare   fondul cardului (#RRGGBB); poster = imagine optionala in DOSAR_POSTERE/<id>.png.
# Numai servicii legale, fara DRM comercial: fara Widevine/PlayReady nu se pot reda, deci nu primesc card.
#
# Un pachet poate pune in DOSAR_PACHETE un fisier <id>.json cu aceleasi campuri (scurtatura) sau cu campurile unei
# aplicatii instalabile (mai jos); cardul apare singur, iar la stergerea pachetului dispare.
#
# MAGAZINUL (runda 2, Eduard 13.11.2026 08:54: Kodi, HD Satelit Browser si navigatorul nostru „ca aplicatii”, cu
# Instaleaza / Actualizeaza / Dezinstaleaza / Porneste). O aplicatie instalabila (fel "pachet") e un plugin enigma2 din
# feedul nostru; starea NU se tine separat: se citeste la deschidere din catalogul opkg al imaginii
# (Components/HdsPachete, acelasi cu Extensiile: versiunea instalata, cea din feed, marimea) si din dosarul pluginului,
# deci aplicatia apare in grila oricum ar fi instalata (din card, din Extensii, dintr-un fisier .ipk). Instalarea,
# actualizarea si stergerea trec prin calea obisnuita a imaginii (Components/HdsExtensiiLucru: planul, fereastra
# HdsExtensiiActiune cu confirmarea si progresul, jurnalul hds-extensii.log; in web, rutele /api/extensii-*).
# Campurile unei aplicatii instalabile:
#   id, titlu, descriere, culoare   ca la scurtaturi (titlu_tradus "1": titlul trece prin traducere);
#   pachet    numele opkg (enigma2-plugin-*: catalogul imaginii arata numai pluginurile);
#   dosar     dosarul pluginului sub Plugins/ (de pilda "Extensions/HdsMediaCenter"): plugin.py acolo = instalat;
#   pornire   "modul:functie" chemata cu sesiunea (de pilda "Plugins.Extensions.HdsMediaCenter.plugin:porneste");
#   poza      numele pozei din dosarul pluginului (cand e instalat); altfel <id>.png din DOSAR_POSTERE (din imagine).
# Aplicatiile din imagine (fel "imagine", de pilda navigatorul) au numai „Porneste”.
# De ce lista e in imagine si nu un fisier semnat descarcat din feed (regula 1f): catalogul opkg vine deja din feed
# (versiuni, marimi, actualizari), fara descarcare noua, fara semnatura noua si fara rezerva cand reteaua lipseste;
# o aplicatie noua fara imagine noua vine ca pachet care pune <id>.json aici.
#
# Harta tastelor (modul MOD_APLICATIE): navigatorul nu apuca telecomanda, iar legatura pe toate tastele a enigma2 o
# trimite navigatorului prin harta. Pe aplicatiile de televizor (harta "tv"): Inapoi/RECALL ajunge ca Escape (asa merge
# „inapoi” in YouTube pentru televizor; pagina de dinainte din istoric ar iesi din aplicatie), culorile, MENU, INFO si
# TEXT nu ajung la navigator (ar deschide bara de adresa, favoritele, meniul navigatorului), volumul si sunetul oprit
# raman la enigma2 (TASTE_ENIGMA2), EXIT inchide aplicatia si intoarce grila.

import json
import os
import re

DOSAR_PACHETE = "/usr/share/enigma2/hds-aplicatii"
DOSAR_POSTERE = "/usr/share/enigma2/hds-aplicatii"     # pozele cardurilor (data/hds-aplicatii din imagine)
DOSAR_PLUGINURI = "/usr/lib/enigma2/python/Plugins"
DOSAR_DATE = "/home/root/.local/share/hds-aplicatii"
DOSAR_CACHE = "/tmp/hds-aplicatii-cache"

PROGRAME = {"wpe": "/usr/bin/hds-navigator", "chromium": "/usr/bin/hds-chromium"}
MOTOR_IMPLICIT = "wpe"

COLOANE = 4
RANDURI_VIZIBILE = 2

# codurile Linux (input-event-codes.h)
KEY_ESC = 1
KEY_MUTE = 113
KEY_VOLUMEDOWN = 114
KEY_VOLUMEUP = 115
KEY_POWER = 116
KEY_MENU = 139
KEY_BACK = 158
KEY_EXIT = 174
KEY_INFO = 358
KEY_TEXT = 388
KEY_RED = 398
KEY_GREEN = 399
KEY_YELLOW = 400
KEY_BLUE = 401
KEY_LAST = 405
KEY_PREVIOUS = 412

# tastele care raman la enigma2 cat aplicatia e pe ecran (legatura intoarce 0, deci merg la harta globala)
TASTE_ENIGMA2 = frozenset((KEY_VOLUMEUP, KEY_VOLUMEDOWN, KEY_MUTE))
OPRITA = None   # tasta nu ajunge nicaieri

HARTI_TASTE = {
	# aplicatiile facute pentru televizor (YouTube TV si altele ca el): Inapoi = Escape
	"tv": {
		KEY_BACK: KEY_ESC, KEY_LAST: KEY_ESC, KEY_PREVIOUS: KEY_ESC,
		KEY_RED: OPRITA, KEY_GREEN: OPRITA, KEY_YELLOW: OPRITA, KEY_BLUE: OPRITA,
		KEY_MENU: OPRITA, KEY_INFO: OPRITA, KEY_TEXT: OPRITA,
	},
	# siturile obisnuite (pagini cu legaturi): Inapoi = pagina de dinainte, ALBASTRU = indicatorul (ca in navigator)
	"pagina": {
		KEY_RED: OPRITA, KEY_GREEN: OPRITA, KEY_YELLOW: OPRITA,
		KEY_MENU: OPRITA, KEY_INFO: OPRITA, KEY_TEXT: OPRITA,
	},
}


def N_(text):
	return text


# Scurtaturile din imagine. Altele noi se adauga aici (sau ca pachet, DOSAR_PACHETE), numai cu adrese verificate.
SCURTATURI_IMAGINE = (
	{
		"id": "youtube",
		"titlu": "YouTube",
		"descriere": N_("YouTube pentru televizor. Te conectezi cu telefonul, la yt.be/activate."),
		"url": "https://www.youtube.com/tv",
		"agent": "tv",          # agentul televizorului ales in setarile navigatorului (implicit: adaosul de mai jos)
		"adaos": "SMART-TV",
		"script": "",
		"taste": "tv",
		"motor": "wpe",
		"culoare": "#C4302B",
	},
	# Site-urile noastre in modul TV (Eduard, 13.11.2026 09:06): acelasi site, gata pentru telecomanda (litere mari, focalizarea
	# vizibila, fara reclame) prin ?tv=1 si adaosul HDS-TV la agent; navigarea din taste o face tv-mod.js al site-ului (sursa:
	# depozitul de unelte, unelte/mod-tv/). Harta "pagina": Inapoi = pagina de dinainte, facuta de navigator (merge si pe un site
	# strain deschis dintr-o legatura; de pe prima pagina inchide aplicatia); OK pe o caseta = tastatura enigma2 (proba pe receptorul de probe).
	{
		"id": "hdsatelit",
		"titlu": "HD Satelit",
		"descriere": N_("Știrile HD Satelit pe televizor: satelit, cablu, operatori, receptoare."),
		"url": "https://www.hdsatelit.com/?tv=1",
		"agent": "",
		"adaos": "HDS-TV",
		"script": "",
		"taste": "pagina",
		"motor": "wpe",
		"culoare": "#374EA1",
	},
	{
		"id": "satbase",
		"titlu": "SatBase",
		"descriere": N_("Frecvențele și canalele sateliților. Cauți cu tastatura de pe ecran."),
		"url": "https://satbase.hdsatelit.com/?tv=1",
		"agent": "",
		"adaos": "HDS-TV",
		"script": "",
		"taste": "pagina",
		"motor": "wpe",
		"culoare": "#0E8A7E",
	},
	{
		"id": "stb",
		"titlu": "HD Satelit E2",
		"descriere": N_("Imaginea HD Satelit: receptoarele, noutățile, ajutorul și forumul."),
		"url": "https://stb.hdsatelit.com/?tv=1",
		"agent": "",
		"adaos": "HDS-TV",
		"script": "",
		"taste": "pagina",
		"motor": "wpe",
		"culoare": "#6E4BD8",
	},
)

# Serviciile cu DRM (Eduard, 13.11.2026, prin coordonator la 09:13: Widevine DA, modulul il aduce receptorul omului de la
# Google, cu licenta aratata si acceptata). "drm": "widevine" = numai cu motorul Chromium (WPE nu are Widevine) si cu
# modulul pe receptor; fara modul, cardul ofera „Instalează modulul Widevine” (INSTALATOR_WIDEVINE). Cardurile sunt
# ASCUNSE ("vizibil": "0") pana la proba buna pe receptor; le arata un pachet din feed care pune VIZIBILE (fara imagine
# noua). Agentul: Chrome pentru PC (siturile lor nu dau redarea pentru agentii de televizor fara aplicatia lor).
# Prime Video si filmele platite din YouTube NU primesc card (cu L3 dau numai calitate SD).
AGENT_CHROME_PC = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
	"Safari/537.36")
SCURTATURI_DRM = (
	{"id": "netflix", "titlu": "Netflix", "url": "https://www.netflix.com/browse", "drm": "widevine", "vizibil": "0",
		"descriere": N_("Contul tău Netflix, în navigatorul HD Satelit Browser, cu modulul Widevine. Cel mult 720p."),
		"agent": AGENT_CHROME_PC, "taste": "pagina", "motor": "chromium", "culoare": "#B20710"},
	{"id": "disney-plus", "titlu": "Disney+", "url": "https://www.disneyplus.com/", "drm": "widevine", "vizibil": "0",
		"descriere": N_("Contul tău Disney+, în navigatorul HD Satelit Browser, cu modulul Widevine. Cel mult 720p."),
		"agent": AGENT_CHROME_PC, "taste": "pagina", "motor": "chromium", "culoare": "#0B2C6B"},
	{"id": "hbo-max", "titlu": "HBO Max", "url": "https://play.hbomax.com/", "drm": "widevine", "vizibil": "0",
		"descriere": N_("Contul tău HBO Max, în navigatorul HD Satelit Browser, cu modulul Widevine. Cel mult 720p."),
		"agent": AGENT_CHROME_PC, "taste": "pagina", "motor": "chromium", "culoare": "#2A1B7A"},
)
# Modulul Widevine si instalatorul lui (coordonatorul, 13.11.2026 09:30): O SINGURA cale, comuna pentru HD Satelit Browser
# (--widevine-cdm-path) si Media Center (legatura din dosarul lui cdm, facuta de pachetul KOD); instalatorul e
# Components/HdsWidevine.instaleaza(session, gata=None) (licenta Google aratata si acceptata, apoi descarcarea; il scrie KOD).
WIDEVINE_CAI = ("/home/root/.local/share/widevine/libwidevinecdm.so",)
INSTALATOR_WIDEVINE = "Components.HdsWidevine:instaleaza"     # functie(session, gata) care arata licenta si descarca
VIZIBILE = DOSAR_PACHETE + "/vizibile.json"                    # {"netflix": true, ...} pus de un pachet din feed
CERE_WIDEVINE = "widevine"     # starea cardului: serviciul cere modulul, care lipseste
TEXT_CERE_WIDEVINE = N_("Cere modulul Widevine")
TEXT_FARA_INSTALATOR_WIDEVINE = N_("Modulul Widevine nu se poate instala încă din acest receptor. Urmărește noutățile de pe forum.")


def widevinePrezent(exista=os.path.exists):
	return any(exista(c) for c in WIDEVINE_CAI)


def vizibilePrinFeed(fisier=None):
	"""Id-urile aratate de pachetul din feed (VIZIBILE); {} fara fisier sau cu fisier stricat."""
	try:
		with open(fisier or VIZIBILE, "rb") as f:
			d = json.loads(f.read(16 * 1024).decode("utf-8"))
	except (IOError, OSError, ValueError, UnicodeDecodeError):
		return {}
	return dict((k, bool(v)) for k, v in d.items() if isinstance(k, str)) if isinstance(d, dict) else {}


def instaleazaWidevine(session, gata=None, importa=None):
	"""Porneste instalarea modulului (INSTALATOR_WIDEVINE: licenta, acceptul, descarcarea); None daca a pornit, altfel
	textul pentru om."""
	modul, functie = INSTALATOR_WIDEVINE.split(":", 1)
	try:
		if importa is None:
			import importlib
			importa = importlib.import_module
		f = getattr(importa(modul), functie)
	except Exception:
		return TEXT_FARA_INSTALATOR_WIDEVINE
	f(session, gata)
	return None


# Textul de sub card cand redarea video lipseste din motor (WPE-ul imaginii e construit fara video pana la lotul care
# il aduce): interfata merge, filmele nu. Se arata numai pe aplicatiile care au nevoie de video.
CER_VIDEO = frozenset(("youtube",))
STARE_FARA_VIDEO = N_("Fără filme încă")    # sub card (scurt, incape)
TEXT_FARA_VIDEO = N_("Filmele nu pornesc încă: redarea video vine cu actualizarea navigatorului.")   # in banda de jos

_ID_BUN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_CULOARE_BUNA = re.compile(r"^#[0-9a-fA-F]{6}$")
CAMPURI = ("id", "titlu", "descriere", "url", "agent", "adaos", "script", "taste", "motor", "culoare", "drm", "vizibil",
	"dupa")


def scurtaturaBuna(s):
	"""Scurtatura curatata (dict nou) sau None daca nu se poate folosi: id curat, adresa http(s), fara semne de control
	in texte (merg pe linia de comanda a navigatorului)."""
	if not isinstance(s, dict):
		return None
	r = {}
	for k in CAMPURI:
		v = s.get(k, "")
		if v is None:
			v = ""
		if not isinstance(v, str):
			return None
		if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in v):
			return None
		r[k] = v.strip()
	if not _ID_BUN.match(r["id"]) or not r["titlu"]:
		return None
	if not (r["url"].startswith("https://") or r["url"].startswith("http://")):
		return None
	if r["taste"] not in HARTI_TASTE:
		r["taste"] = "tv"
	if r["motor"] not in PROGRAME:
		r["motor"] = MOTOR_IMPLICIT
	if not _CULOARE_BUNA.match(r["culoare"]):
		r["culoare"] = "#374EA1"
	if r["drm"] not in ("", "widevine"):
		return None
	r["vizibil"] = "0" if r["vizibil"] == "0" else "1"
	if r["script"] and ("/" in r["script"] or r["script"].startswith(".")):
		r["script"] = ""   # numai un nume de fisier din dosarul scripturilor, nu o cale
	return r


def aplicatiiDinPachete(dosar=None):
	"""Scurtaturile puse de pachetele din feed (cate un <id>.json); cele stricate se sar."""
	dosar = dosar or DOSAR_PACHETE
	r = []
	try:
		nume = sorted(os.listdir(dosar))
	except OSError:
		return r
	for n in nume:
		if not n.endswith(".json"):
			continue
		try:
			with open(os.path.join(dosar, n), "rb") as f:
				date = json.loads(f.read(64 * 1024).decode("utf-8"))
		except (IOError, OSError, ValueError, UnicodeDecodeError):
			continue
		s = magazinBun(date) if isinstance(date, dict) and date.get("pachet") else scurtaturaBuna(date)
		if s is not None:
			s["din_pachet"] = "1"
			r.append(s)
	return r


def toate(dosar=None):
	"""Toate aplicatiile cunoscute, in ordinea de fabrica: scurtaturile din imagine, aplicatiile din imagine si cele
	instalabile, apoi cele din pachete (fara dubluri)."""
	r, vazute = [], set()
	din_imagine = ([scurtaturaBuna(x) for x in SCURTATURI_IMAGINE] + [magazinBun(x) for x in MAGAZIN_IMAGINE] +
		[scurtaturaBuna(x) for x in SCURTATURI_DRM])
	for s in din_imagine + aplicatiiDinPachete(dosar):
		if s is not None and s["id"] not in vazute:
			vazute.add(s["id"])
			r.append(s)
	return r


# ------------------------------------------------------------ magazinul: aplicatiile instalabile

FEL_SCURTATURA, FEL_PACHET, FEL_IMAGINE = "scurtatura", "pachet", "imagine"
# starile din magazin; None = cardul nu se arata (nici instalat, nici in feed)
INSTALAT, ACTUALIZARE, DISPONIBIL = "instalat", "actualizare", "disponibil"
TEXTE_STARE = {
	"widevine": N_("Cere modulul Widevine"),
	INSTALAT: N_("Instalat"),
	ACTUALIZARE: N_("Actualizare disponibilă"),
	DISPONIBIL: N_("Disponibil"),
}

MAGAZIN_IMAGINE = (
	{
		"id": "navigator",
		"fel": FEL_IMAGINE,
		"titlu": N_("Navigator web"),
		"titlu_tradus": "1",
		"descriere": N_("Navigatorul imaginii: orice pagină web, cu telecomanda. EXIT te întoarce aici."),
		"pornire": "Plugins.Extensions.HdsNavigator.plugin:deschideNavigator",
		"program": "/usr/bin/hds-navigator",
		"culoare": "#2D5BA8",
	},
	{
		"id": "hdsatelit-browser",
		"fel": FEL_PACHET,
		"titlu": "HD Satelit Browser",
		"descriere": N_("Navigatorul HD Satelit construit din sursele Chromium, pe tot ecranul, cu telecomanda."),
		"pachet": "enigma2-plugin-extensions-hdsatelit-browser",
		"dosar": "Extensions/HdsatelitBrowser",
		"pornire": "Plugins.Extensions.HdsatelitBrowser.plugin:porneste",
		"poza": "plugin_mare.png",
		"culoare": "#0E7C86",
	},
	{
		"id": "media-center",
		"fel": FEL_PACHET,
		# Politica marcii Kodi (kodi.wiki, Official:Distribution_Policy): versiunile modificate fara aprobarea XBMC
		# Foundation nu folosesc sigla. Eduard (13.11, prin coordonator 09:13): numele „Media Center”, poza noastra
		# neutra, „Powered by Kodi” in descriere, cu nota marcii (ceruta de politica la prima folosire).
		"titlu": "Media Center",
		"descriere": N_("Filme, muzică și poze de pe stick, disc sau din rețea, pe tot ecranul."),
		"dupa": "Powered by Kodi®. Kodi® is a registered trademark of the XBMC Foundation.",
		"pachet": "enigma2-plugin-extensions-hdsmediacenter",
		"dosar": "Extensions/HdsMediaCenter",
		"pornire": "Plugins.Extensions.HdsMediaCenter.plugin:porneste",
		"culoare": "#1F3A5F",
	},
)

_PORNIRE_BUNA = re.compile(r"^Plugins(\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$")
_DOSAR_BUN = re.compile(r"^(Extensions|SystemPlugins)/[A-Za-z0-9_]+$")
_NUME_PACHET_BUN = re.compile(r"^enigma2-plugin-[a-z0-9][a-z0-9.+-]*$")
_POZA_BUNA = re.compile(r"^[A-Za-z0-9_.-]+\.(png|jpg)$")


def magazinBun(s):
	"""Aplicatia din magazin curatata (dict nou) sau None: id curat, pornirea un modul din Plugins, pachetul un plugin
	enigma2, dosarul si poza fara cai."""
	if not isinstance(s, dict):
		return None
	r = {}
	for k in ("id", "titlu", "descriere", "culoare", "fel", "pachet", "dosar", "pornire", "poza", "program", "titlu_tradus",
			"dupa", "vizibil"):
		v = s.get(k, "")
		if v is None:
			v = ""
		if not isinstance(v, str) or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in v):
			return None
		r[k] = v.strip()
	r["fel"] = r["fel"] if r["fel"] in (FEL_PACHET, FEL_IMAGINE) else FEL_PACHET
	if not _ID_BUN.match(r["id"]) or not r["titlu"] or not _PORNIRE_BUNA.match(r["pornire"]):
		return None
	if r["fel"] == FEL_PACHET and not (_NUME_PACHET_BUN.match(r["pachet"]) and _DOSAR_BUN.match(r["dosar"])):
		return None
	if r["poza"] and not _POZA_BUNA.match(r["poza"]):
		r["poza"] = ""
	if not _CULOARE_BUNA.match(r["culoare"]):
		r["culoare"] = "#374EA1"
	return r


def fel(a):
	return a.get("fel") or FEL_SCURTATURA


def pluginInstalat(a, exista=os.path.exists, si_pyc=True):
	"""Dosarul pluginului aplicatiei are plugin.py (sau plugin.pyc, cand si_pyc): pluginul e pe receptor. Atentie:
	enigma2 lasa plugin.pyc in dosar dupa ce opkg scoate pachetul (fisierul compilat nu e al pachetului), deci .pyc
	conteaza numai cand catalogul opkg nu e citit inca."""
	if not a.get("dosar"):
		return False
	baza = DOSAR_PLUGINURI + "/" + a["dosar"] + "/plugin."
	return exista(baza + "py") or (si_pyc and exista(baza + "pyc"))


def stareMagazin(a, catalog=None, exista=os.path.exists):
	"""INSTALAT / ACTUALIZARE / DISPONIBIL, sau None cand cardul nu se arata. Scurtaturile sunt mereu INSTALAT.
	`catalog`: Components/HdsPachete.Catalog (None cat nu e citit: atunci numai ce se vede pe disc)."""
	f = fel(a)
	if a.get("vizibil") == "0" and not vizibilePrinFeed().get(a.get("id")):
		return None
	if f == FEL_SCURTATURA:
		if a.get("drm") == "widevine":
			if not exista(PROGRAME["chromium"]):
				return None          # WPE nu are Widevine: fara HD Satelit Browser nu se arata
			if not widevinePrezent(exista):
				return CERE_WIDEVINE
		return INSTALAT
	if f == FEL_IMAGINE:
		return INSTALAT if (not a.get("program") or exista(a["program"])) else None
	p = catalog.pachete.get(a["pachet"]) if catalog is not None else None
	if p is not None and p.actualizare:
		return ACTUALIZARE
	# cu catalogul citit, opkg hotaraste (instalat din card, din Extensii sau dintr-un .ipk: toate trec prin opkg);
	# dosarul conteaza numai pentru un plugin pus de mana (necunoscut opkg-ului) si numai dupa plugin.py
	if p is not None:
		instalat = p.instalat
	elif catalog is not None:
		instalat = pluginInstalat(a, exista, si_pyc=False)
	else:
		instalat = pluginInstalat(a, exista)
	if instalat:
		return INSTALAT
	if p is not None and p.se_poate_instala:
		return DISPONIBIL
	return None


def pachetDinCatalog(a, catalog):
	return catalog.pachete.get(a.get("pachet") or "") if catalog is not None else None


def pozaPentru(a, exista=os.path.exists):
	"""Calea pozei cardului: `poza` din dosarul pluginului (cand e instalat, poza pachetului), apoi <id>.png din
	DOSAR_POSTERE (poza din imagine, si pentru aplicatiile inca neinstalate); None = cardul colorat cu numele."""
	if a.get("id") is None:
		return None
	locuri = []
	if a.get("dosar") and a.get("poza"):
		locuri.append(DOSAR_PLUGINURI + "/" + a["dosar"] + "/" + a["poza"])
	locuri.append(DOSAR_POSTERE + "/" + a["id"] + ".png")
	for c in locuri:
		if exista(c):
			return c
	return None


def actiuni(a, stare_):
	"""Ce se poate face cu aplicatia (in ordinea din MENU; prima e cea de pe OK)."""
	f = fel(a)
	if stare_ == CERE_WIDEVINE:
		return ["instaleaza-widevine"]
	if f != FEL_PACHET:
		return ["porneste"]
	if stare_ == DISPONIBIL:
		return ["instaleaza"]
	if stare_ == ACTUALIZARE:
		return ["porneste", "actualizeaza", "dezinstaleaza"]
	if stare_ == INSTALAT:
		return ["porneste", "dezinstaleaza"]
	return []


def porneste(session, a, importa=None):
	"""Porneste aplicatia: scurtatura in navigator (modul aplicatie) sau functia de pornire a pluginului. Intoarce None
	daca a pornit, altfel textul pentru om (pluginul lipseste sau a cazut la pornire)."""
	if fel(a) == FEL_SCURTATURA:
		from Plugins.Extensions.HdsNavigator.plugin import deschideAplicatie
		deschideAplicatie(session, a)
		return None
	modul, functie = a["pornire"].split(":", 1)
	try:
		if importa is None:
			import importlib
			importa = importlib.import_module
		f = getattr(importa(modul), functie)
	except Exception as e:
		print("[HdsAplicatii] %s nu se poate porni: %s" % (a["id"], e.__class__.__name__))
		return TEXT_NU_PORNESTE
	try:
		f(session)
	except Exception as e:
		print("[HdsAplicatii] %s a cazut la pornire: %s" % (a["id"], e))
		return TEXT_NU_PORNESTE
	return None


TEXT_NU_PORNESTE = N_("Aplicația e instalată, dar nu pornește. Reinstaleaz-o din MENU sau din Extensii.")


# catalogul opkg citit pe un fir (HdsExtensiiLucru il tine minte, acelasi cu Extensiile si cu pagina web)
_fir_catalog = [None]


def catalogAcum():
	"""Catalogul tinut minte daca e la zi, altfel None (si porneste citirea pe un fir: catalogGata() spune cand e)."""
	try:
		from Components import HdsExtensiiLucru as L
	except ImportError:
		return None
	c = L.catalogLaZi()
	if c is not None:
		return c
	t = _fir_catalog[0]
	if t is None or not t.is_alive():
		import threading
		t = threading.Thread(target=_citesteCatalog, name="HdsAplicatiiCatalog")
		t.daemon = True
		_fir_catalog[0] = t
		t.start()
	return None


def _citesteCatalog():
	try:
		from Components import HdsExtensiiLucru as L
		L.incarcaCatalog()
	except Exception as e:
		print("[HdsAplicatii] catalogul: %s" % e)


def catalogInLucru():
	t = _fir_catalog[0]
	return t is not None and t.is_alive()


# ------------------------------------------------------------ ordinea si ascunderea (doua siruri de id-uri)

def listaId(text):
	return [x for x in (text or "").split(",") if _ID_BUN.match(x)]


def textId(ids):
	return ",".join(ids)


def ordonate(aplicatii, ordine):
	"""Aplicatiile in ordinea omului; cele noi (necunoscute in ordine) vin la coada, in ordinea de fabrica."""
	dupa_id = dict((a["id"], a) for a in aplicatii)
	r = [dupa_id[i] for i in listaId(ordine) if i in dupa_id]
	puse = set(a["id"] for a in r)
	return r + [a for a in aplicatii if a["id"] not in puse]


def vizibile(aplicatii, ordine, ascunse):
	a = set(listaId(ascunse))
	return [x for x in ordonate(aplicatii, ordine) if x["id"] not in a]


def muta(aplicatii, ordine, id_, pas):
	"""Noua ordine (text) dupa mutarea aplicatiei `id_` cu `pas` locuri (-1 inainte, +1 dupa) intre toate."""
	ids = [a["id"] for a in ordonate(aplicatii, ordine)]
	if id_ not in ids:
		return textId(ids)
	i = ids.index(id_)
	j = max(0, min(len(ids) - 1, i + pas))
	ids.insert(j, ids.pop(i))
	return textId(ids)


def ascunde(ascunse, id_, da=True):
	ids = [x for x in listaId(ascunse) if x != id_]
	if da:
		ids.append(id_)
	return textId(ids)


# ------------------------------------------------------------ mutarea in grila (COLOANE pe rand)

def misca(i, n, directie, coloane=COLOANE):
	"""Indicele nou dupa o sageata ("sus", "jos", "stanga", "dreapta") intr-o grila de n carduri. Stanga/dreapta trec
	pe randul vecin; jos pe ultimul rand incomplet merge pe ultimul card; la margini ramane pe loc."""
	if n <= 0:
		return 0
	i = max(0, min(n - 1, i))
	if directie == "dreapta":
		return min(n - 1, i + 1)
	if directie == "stanga":
		return max(0, i - 1)
	if directie == "jos":
		if i + coloane < n:
			return i + coloane
		ultimul_rand = (n - 1) // coloane
		return n - 1 if i // coloane < ultimul_rand else i
	if directie == "sus":
		return i - coloane if i >= coloane else i
	return i


def primulRandVazut(i, inceput, coloane=COLOANE, vizibile_=RANDURI_VIZIBILE):
	"""Primul rand aratat pe ecran, ca randul cardului ales sa fie vazut (fereastra se muta cate un rand)."""
	rand = i // coloane
	if rand < inceput:
		return rand
	if rand >= inceput + vizibile_:
		return rand - vizibile_ + 1
	return inceput


# ------------------------------------------------------------ pornirea

def tastaPentruNavigator(harta, cod):
	"""Ce face legatura enigma2 cu tasta `cod` cat aplicatia e pe ecran: ("enigma2", None) = o lasa enigma2 (volumul),
	("oprita", None) = nu ajunge nicaieri, ("navigator", cod_nou) = merge la navigator."""
	if cod in TASTE_ENIGMA2:
		return "enigma2", None
	h = HARTI_TASTE.get(harta) if isinstance(harta, str) else harta
	h = h or {}
	if cod in h:
		nou = h[cod]
		if nou is OPRITA:
			return "oprita", None
		return "navigator", nou
	return "navigator", cod


_optiuni_program = {}


def optiuniProgram(cale, citeste=None):
	"""Optiunile noi pe care le stie programul motorului ("agent", "script"), aflate o data din sirurile binarului
	(numele optiunilor GOption/getopt stau acolo ca siruri C intregi). Un program care nu stie o optiune s-ar opri la
	pornire, deci fara dovada nu se dau."""
	if cale in _optiuni_program:
		return _optiuni_program[cale]
	r = set()
	# numele optiunii ca sir intreg sau textul ei de ajutor din hds-navigator 0.7.5: linkerul poate pastra un nume scurt
	# numai ca sfarsit al altui sir (de pilda "script" in "AVERTISMENT script"), deci numele singur poate lipsi
	semne = {"agent": (b"\x00agent\x00", b"User-Agent-ul intreg"),
		"script": (b"\x00script\x00", b"harta tastelor unei aplicatii"),
		# hds-chromium (CRM): dosarul modulului Widevine; fara optiune ia singur WIDEVINE_CAI (coordonatorul 09:46)
		"widevine-cdm-path": (b"\x00widevine-cdm-path\x00",)}
	try:
		if citeste is not None:
			date = citeste(cale)
			r.update(n for n, ss in semne.items() if any(s in date for s in ss))
		else:
			# mmap, nu read: programul Chromium are ~95 MB, iar receptorul poate avea ~200 MB liberi
			import mmap
			with open(cale, "rb") as f:
				m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
				try:
					r.update(n for n, ss in semne.items() if any(m.find(s) >= 0 for s in ss))
				finally:
					m.close()
	except (IOError, OSError, ValueError):
		pass
	_optiuni_program[cale] = frozenset(r)
	return _optiuni_program[cale]


def program(scurtatura, exista=os.path.exists):
	"""(motorul folosit, calea programului): motorul scurtaturii daca programul lui exista, altfel "wpe"."""
	motor = scurtatura.get("motor") or MOTOR_IMPLICIT
	cale = PROGRAME.get(motor)
	if cale and exista(cale):
		return motor, cale
	return MOTOR_IMPLICIT, PROGRAME[MOTOR_IMPLICIT]


DOSAR_SCRIPTURI = "/usr/share/hds-navigator/aplicatii"

# Agentul televizorului pentru aplicatiile cu agent "tv" (YouTube; Eduard, 31.10.2026 14:35-14:38: „pui agent de LG sau
# Samsung cum face toată lumea”, o setare in setarile navigatorului, lista intr-un fisier din feed). Setarea e
# config.plugins.hdsnavigator.agent_tv (HdsNavigator/setari.py), pe televizor si in /navigator. „implicit” = agentul
# navigatorului cu adaosul scurtaturii (probat pe receptorul de probe, 13.11.2026). LG si Samsung: probate pe PC (WebKit, 13.11.2026:
# interfata TV si Escape = inapoi); doi agenti de tip Chrome fara semn de televizor (Hisense, RDK) au fost trimisi la
# youtube.com pentru PC, de aceea lista se poate schimba fara imagine noua: un pachet din feed pune FISIER_AGENTI
# ([{"id", "nume", "agent"}, ...]), care inlocuieste lista de mai jos (afara de „implicit”, care ramane primul).
FISIER_AGENTI = DOSAR_PACHETE + "/agenti-tv.json"
AGENT_IMPLICIT = "implicit"
AGENTI_TV = (
	{"id": "lg", "nume": "LG (webOS)",
		"agent": "Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 WebAppManager"},
	{"id": "samsung", "nume": "Samsung (Tizen)",
		"agent": "Mozilla/5.0 (SMART-TV; LINUX; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) 76.0.3809.146/6.0 TV Safari/537.36"},
)
TEXT_AGENT_IMPLICIT = N_("Navigatorul imaginii (recomandat)")


def agentiTv(fisier=None):
	"""Agentii televizoarelor: din FISIER_AGENTI daca exista si e bun, altfel AGENTI_TV (fara „implicit”)."""
	try:
		with open(fisier or FISIER_AGENTI, "rb") as f:
			date = json.loads(f.read(64 * 1024).decode("utf-8"))
		r = []
		for x in date if isinstance(date, list) else []:
			if not isinstance(x, dict):
				continue
			id_, nume, agent = x.get("id"), x.get("nume"), x.get("agent")
			if (isinstance(id_, str) and _ID_BUN.match(id_) and id_ != AGENT_IMPLICIT and isinstance(nume, str) and nume
					and isinstance(agent, str) and agent and not any(ord(ch) < 0x20 for ch in agent + nume)):
				r.append({"id": id_, "nume": nume[:40], "agent": agent[:400]})
		if r:
			return r
	except (IOError, OSError, ValueError, UnicodeDecodeError):
		pass
	return [dict(x) for x in AGENTI_TV]


def alegeriAgentTv(traducere=None):
	"""Alegerile setarii (valoarea, textul de pe ecran): intai „implicit”, apoi televizoarele."""
	t = traducere or (lambda s: s)
	return [(AGENT_IMPLICIT, t(TEXT_AGENT_IMPLICIT))] + [(x["id"], x["nume"]) for x in agentiTv()]


def agentTv(ales):
	"""Agentul intreg al televizorului ales; "" pentru „implicit” sau pentru unul care nu mai e in lista."""
	for x in agentiTv():
		if x["id"] == ales:
			return x["agent"]
	return ""


def argumenteAplicatie(scurtatura, optiuni, exista=os.path.exists, agent_tv=AGENT_IMPLICIT):
	"""Argumentele proprii aplicatiei (agentul si scriptul), dupa ce stie programul (optiuniProgram). Agentul "tv" al
	scurtaturii inseamna agentul televizorului ales in setari (`agent_tv`); cu „implicit”, sau cand programul nu stie
	--agent, ramane adaosul."""
	a = []
	agent = scurtatura.get("agent") or ""
	if agent == "tv":
		agent = agentTv(agent_tv) if agent_tv and agent_tv != AGENT_IMPLICIT else ""
	adaos = scurtatura.get("adaos") or ""
	if agent and "agent" in optiuni:
		a += ["--agent", agent]
	elif adaos:
		a += ["--agent-adaugat", adaos]
	script = scurtatura.get("script") or ""
	if script and "script" in optiuni:
		cale = DOSAR_SCRIPTURI + "/" + script
		if exista(cale):
			a += ["--script", cale]
	if scurtatura.get("drm") == "widevine" and "widevine-cdm-path" in optiuni:
		a += ["--widevine-cdm-path", WIDEVINE_CAI[0].rsplit("/", 1)[0]]
	return a


def dosareProfil(id_):
	"""Profilul aplicatiei (conectarea ramane si dupa „Șterge datele” navigatorului) si cache-ul ei, in memorie."""
	return DOSAR_DATE + "/" + id_, DOSAR_CACHE + "/" + id_


def areVideo():
	"""True cand WebKit-ul imaginii are redarea video: raspunsul lotului video al navigatorului
	(Components/HdsDecodorWeb.webkit_cu_video, numai ce e deja stiut, fara cautare pe firul enigma2); fara modulul
	acela (imaginile de pana la lotul video) WebKit-ul e construit fara video, deci False."""
	try:
		from Components.HdsDecodorWeb import webkit_cu_video
	except ImportError:
		return False
	try:
		return bool(webkit_cu_video(numai_stiut=True))
	except Exception:
		return False


def stare(scurtatura, video=None):
	"""Textul scurt de sub card: "" = „Instalat” (din imagine sau pachet); pe aplicatiile cu filme, fara video,
	STARE_FARA_VIDEO."""
	if scurtatura.get("id") in CER_VIDEO and video is False:
		return STARE_FARA_VIDEO
	return ""


def descriereIntreaga(a, traducere=None, video=None):
	"""Textul benzii de jos si al paginii web: descrierea tradusa, apoi „dupa” (netradus, de pilda nota marcii), apoi
	nota despre video."""
	t = traducere or (lambda s: s)
	parti = [t(a["descriere"]) if a.get("descriere") else t(a["titlu"]) if a.get("titlu_tradus") else a["titlu"]]
	if a.get("dupa"):
		parti.append(a["dupa"])
	nota = notaVideo(a, video)
	if nota:
		parti.append(t(nota))
	return "  ".join(parti)


def notaVideo(scurtatura, video=None):
	"""Explicatia pusa dupa descriere (banda de sub grila, pagina web) cand aplicatia are nevoie de video si nu are."""
	if scurtatura.get("id") in CER_VIDEO and video is False:
		return TEXT_FARA_VIDEO
	return ""


# ------------------------------------------------------------ setarile (config.plugins.hdsaplicatii)

_config = [None]


def initConfig(config=None):
	"""config.plugins.hdsaplicatii: ordinea si cele ascunse (siruri de id-uri), create o singura data."""
	if _config[0] is not None:
		return _config[0]
	from Components.config import ConfigSubsection, ConfigText
	if config is None:
		from Components.config import config
	c = ConfigSubsection()
	c.ordine = ConfigText(default="", fixed_size=False)
	c.ascunse = ConfigText(default="", fixed_size=False)
	config.plugins.hdsaplicatii = c
	_config[0] = c
	return c


def listaPentruOm(cu_ascunse=False, catalog=None, exista=os.path.exists):
	"""Aplicatiile in ordinea omului (din setari); cu_ascunse=True le da si pe cele ascunse (meniul MENU, pagina web).
	Fiecare primeste "stare" (stareMagazin); cele fara stare (nici instalate, nici in feed) nu apar."""
	c = initConfig()
	lista = ordonate(toate(), c.ordine.value) if cu_ascunse else vizibile(toate(), c.ordine.value, c.ascunse.value)
	r = []
	for a in lista:
		s = stareMagazin(a, catalog, exista)
		if s is not None:
			a = dict(a, stare=s)
			r.append(a)
	return r


def gaseste(id_):
	for s in toate():
		if s["id"] == id_:
			return s
	return None


def mutaSiSalveaza(id_, pas):
	c = initConfig()
	c.ordine.value = muta(toate(), c.ordine.value, id_, pas)
	c.ordine.save()


def schimba(aplicatii, ordine, id_, vecin):
	"""Noua ordine (text) dupa schimbul locurilor lui `id_` si `vecin` (vecinul vazut in grila: intre ei pot sta
	aplicatii ascunse sau care nu se arata acum, care raman pe locul lor)."""
	ids = [a["id"] for a in ordonate(aplicatii, ordine)]
	if id_ in ids and vecin in ids:
		i, j = ids.index(id_), ids.index(vecin)
		ids[i], ids[j] = ids[j], ids[i]
	return textId(ids)


def schimbaSiSalveaza(id_, vecin):
	c = initConfig()
	c.ordine.value = schimba(toate(), c.ordine.value, id_, vecin)
	c.ordine.save()


def ascundeSiSalveaza(id_, da=True):
	c = initConfig()
	c.ascunse.value = ascunde(c.ascunse.value, id_, da)
	c.ascunse.save()


def esteAscunsa(id_):
	return id_ in listaId(initConfig().ascunse.value)


def arataToate():
	c = initConfig()
	c.ascunse.value = ""
	c.ascunse.save()
