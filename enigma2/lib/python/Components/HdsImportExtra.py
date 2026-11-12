# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImportExtra.py: părțile importului de lângă canale (Components/HdsImportSurse.py), fără ecran și fără enigma2 la
# încărcare (probele de pe PC îl folosesc direct):
#   - locurile din copie: rădăcina copiei (dosarul de deasupra lui etc/enigma2), fișierele rețelei, dosarul picon,
#     listele pachetelor instalate (radacina_copiei, fel_extra, locuri_extra);
#   - setările sigure ale meniului: CHEI_SIGURE, chei care înseamnă același lucru în toate imaginile Enigma2; fiecare
#     se ia numai dacă există și aici și dacă valoarea e una dintre cele permise acum (context_setari, citit pe firul
#     enigma2 din arborele config; chei_sigure, pe firul importului). Modul video al altei imagini
#     (config.av.videomode.<ieșire> și config.av.videorate.<mod>) devine config.av.hds_videomode numai când televizorul
#     declară modul (videomode_preferred). Limba nu se ia: rămâne cea aleasă în asistent;
#   - piconurile: numai .png cu nume simplu, fără legături, cu limită de număr, de octeți și de spațiu (copiaza_piconuri);
#   - pluginurile: numele din lista pachetelor instalate a copiei (citeste_pachete), fără pachetele modulelor de acces
#     condiționat (pe acelea le pune singur importul, mai jos), potrivite cu sursele de pachete ale receptorului
#     (potriveste_pachete), pentru oferta de după import;
#   - modulele de acces condiționat (regula din 31.10.2026): fișierele lor din copie (LOCURI_ACCES) se copiază ca atare,
#     octet cu octet, fără să fie deschise, citite, filtrate, arătate sau trimise; în texte, jurnal, starea comună și web
#     ajunge cel mult numărul lor. Pachetele modulelor instalate în copie se instalează din nou din sursele de pachete
#     ale receptorului, după nume (reinstaleaza_acces), fișierele se pun iar peste ce a scris instalarea, iar modulul
#     ales în copie se alege și aici când scriptul lui există (modul_de_ales; alegerea, pe firul enigma2, în
#     HdsImportSurse.incheie_importul). Ce nu există în sursele de pachete se spune omului cu numele pachetului;
#     ce nu se poate instala acum (fără internet, opkg ocupat) intră în coada Components/HdsReinstalare.py, pentru
#     pornirea următoare. Fișierele de acum pe care copia le înlocuiește rămân în DOSAR_INAINTE_ACCES/<data> (ale
#     ultimelor PASTRATE_INAINTE importuri; în afara /etc/enigma2, deci nici copia setărilor, nici asistența nu le iau). În cod nu e scris niciun
#     nume de modul sau de fel: pachetele se recunosc după categorie (TIPAR_CATEGORIE_ACCES, ca HdsPachete), felurile
#     și scripturile după forma din etc/init.d (HdsCopieSetari.feluri_din_nume_acces), dosarele după lista pachetului;
#   - rețeaua: felul conexiunii pe cablu și pe Wi-Fi și rețeaua Wi-Fi, din etc/network/interfaces,
#     etc/wpa_supplicant*.conf și etc/resolv.conf ale copiei (citeste_retea). Parola rețelei stă numai în obiectul
#     ParolaWifi (repr fără ea), nu intră în texte, în jurnal, în starea comună sau în web. Aplicarea e în
#     Components/HdsImportRetea.py.

import os
import re
import shutil
import stat
import time

# ---------------------------------------------------------------- locurile din copie

SUB_ETC_ENIGMA2 = "etc/enigma2"
REL_INTERFACES = "etc/network/interfaces"
REL_RESOLV = "etc/resolv.conf"
TIPAR_REL_WPA = re.compile(r"^etc/wpa_supplicant(\.[A-Za-z0-9_-]{1,20})?\.conf$")
# listele pachetelor instalate pe care le lasă imaginile lângă copie sau în ea (text: un nume pe rând, „nume - versiune”
# sau „nume_versiune_arh.ipk”) și fișierul de stare al lui opkg dintr-o copie a rădăcinii
REL_LISTE_PACHETE = ("tmp/ExtraInstalledPlugins", "installed-list.txt", "autoinstall")
REL_STARE_OPKG = ("var/lib/opkg/status", "usr/lib/opkg/status")
TIPAR_AUTOINSTALL = re.compile(r"^autoinstall[0-9A-Fa-f:]{0,17}$")
REL_PICON = ("usr/share/enigma2/picon", "picon")
MAX_FISIER_RETEA = 64 * 1024
MAX_LISTA_PACHETE = 4 * 1024 * 1024

DEST_PICON = "/usr/share/enigma2/picon"
MAX_PICONURI = 6000
MAX_PICON_OCTETI = 256 * 1024
MAX_PICON_TOTAL = 64 * 1024 * 1024
REZERVA_PICON = 32 * 1024 * 1024     # spațiul lăsat liber în memoria receptorului după piconuri
TERMEN_PICON_S = 120.0
TIPAR_PICON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,119}\.png$")

PREFIX_PLUGIN = "enigma2-plugin-"
TIPAR_NUME_PACHET = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,120}$")
# categoriile care nu se oferă: skinurile altor imagini nu se potrivesc pe ecranele imaginii, listele de canale ar
# înlocui canalele aduse, driverele sunt ale imaginii; modulele de acces condiționat nu se oferă, fiindcă le pune singur
# importul (alegerea „acces”, reinstaleaza_acces)
CATEGORII_NEOFERITE = ("skins", "settings", "drivers")
TIPAR_CUVANT_ACCES = re.compile(r"cams?d?[0-9]*$")
# categoria pachetelor modulelor de acces (aceeași formă ca HdsPachete.TIPAR_CATEGORIE_ACCES)
TIPAR_CATEGORIE_ACCES = re.compile(r"^[a-z]+cams$")
# locurile fișierelor modulelor de acces sub rădăcina unei imagini: configurările (cu subdosarele lor) și cheile
LOCURI_ACCES = ("etc/tuxbox/config", "usr/keys", "var/keys")
DOSAR_CONFIG_ACCES = "etc/tuxbox/config"
MAX_FISIERE_ACCES = 1000
MAX_FISIER_ACCES = 4 * 1024 * 1024
MAX_TOTAL_ACCES = 32 * 1024 * 1024
REZERVA_ACCES = 2 * 1024 * 1024
TERMEN_ACCES_S = 120.0
# fișierele de acum pe care importul le-a înlocuit, sub rădăcina receptorului, câte un dosar cu data pe import (numai
# ale ultimelor PASTRATE_INAINTE importuri: un al doilea import nu șterge originalele păstrate de primul)
DOSAR_INAINTE_ACCES = "home/root/hds-restaurare/acces-inainte-de-import"
PASTRATE_INAINTE = 3
SUFIX_GOL_ACCES = "None"    # scriptul gol al unui fel (<fel>.None), ca HdsCopieSetari.SUFIX_GOL_ACCES
INFO_OPKG = "var/lib/opkg/info"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsImportExtra] %s" % text)


def _nume_de_modul(nume):
	"""Aceeași regulă ca HdsImportSurse._nume_de_modul (un test le compară): un cuvânt al numelui are forma numelor
	modulelor de acces condiționat."""
	return any(TIPAR_CUVANT_ACCES.search(c) for c in re.split(r"[^a-z0-9]+", (nume or "").lower()))


def radacina_copiei(dosar):
	"""Rădăcina copiei unei imagini când `dosar` (cale pe disc sau dosar dintr-o arhivă, cu „/”) e etc/enigma2 al ei:
	ce e deasupra („” pentru o arhivă cu etc/enigma2 direct); None pentru o copie plată."""
	d = (dosar or "").replace("\\", "/").rstrip("/")
	if d == SUB_ETC_ENIGMA2:
		return ""
	if d.endswith("/" + SUB_ETC_ENIGMA2):
		return d[:-len(SUB_ETC_ENIGMA2) - 1]
	return None


def fel_extra(rel):
	""""retea" sau "pachete" pentru calea unui fișier sub rădăcina copiei, altfel None."""
	if rel in (REL_INTERFACES, REL_RESOLV) or TIPAR_REL_WPA.match(rel or ""):
		return "retea"
	if rel in REL_LISTE_PACHETE or rel in REL_STARE_OPKG:
		return "pachete"
	return None


def _fisier_bun(cale, maxim):
	try:
		return (os.path.isfile(cale) and not os.path.islink(cale) and 0 < os.path.getsize(cale) <= maxim)
	except OSError:
		return False


def _are_png(dosar, cate=200):
	try:
		with os.scandir(dosar) as it:
			for i, e in enumerate(it):
				if i >= cate:
					break
				if TIPAR_PICON.match(e.name) and e.is_file(follow_symlinks=False):
					return True
	except OSError:
		pass
	return False


def locuri_extra(cale, fel, cale_arhiva="", radacina_pregatita=None):
	"""Unde stau în copie părțile de lângă canale: {"retea": {"interfaces", "resolv", "wpa": [căi]} sau None,
	"picon": dosar sau None, "pachete": [căi]}.
	- `fel` "dosar": `cale` e dosarul copiei pe mediu; rădăcina e deasupra lui etc/enigma2 (radacina_copiei), iar o copie
	  plată are numai picon/ și listele pachetelor în ea sau lângă ea;
	- `fel` "arhiva": fișierele scoase la pregătire stau sub `radacina_pregatita` (dosarul „extra” al pregătirii), cu
	  calea lor de sub rădăcina copiei; lângă arhivă, pe mediu, se caută listele pachetelor. Piconurile nu se iau din
	  arhive (un dosar picon trece de limita membrilor unei arhive de copie)."""
	rez = {"retea": None, "picon": None, "pachete": []}
	if fel == "arhiva":
		rad = radacina_pregatita
		langa = [os.path.dirname(cale_arhiva)] if cale_arhiva else []
	else:
		r = radacina_copiei(cale)
		rad = r if r else None
		if rad is None:
			langa = [cale, os.path.dirname(cale.rstrip("/\\"))]
			for n in ("picon",):
				d = os.path.join(cale, n)
				if os.path.isdir(d) and not os.path.islink(d) and _are_png(d):
					rez["picon"] = d
		else:
			langa = [os.path.dirname(rad.rstrip("/\\"))]
	if rad:
		interfaces = os.path.join(rad, *REL_INTERFACES.split("/"))
		resolv = os.path.join(rad, *REL_RESOLV.split("/"))
		wpa = []
		try:
			for n in sorted(os.listdir(os.path.join(rad, "etc"))):
				if TIPAR_REL_WPA.match("etc/" + n) and _fisier_bun(os.path.join(rad, "etc", n), MAX_FISIER_RETEA):
					wpa.append(os.path.join(rad, "etc", n))
		except OSError:
			pass
		if _fisier_bun(interfaces, MAX_FISIER_RETEA):
			rez["retea"] = {"interfaces": interfaces, "resolv": resolv if _fisier_bun(resolv, MAX_FISIER_RETEA) else None,
				"wpa": wpa, "radacina": rad}
		if fel != "arhiva":
			for rel in REL_PICON:
				d = os.path.join(rad, *rel.split("/"))
				if os.path.isdir(d) and not os.path.islink(d) and _are_png(d):
					rez["picon"] = d
					break
		for rel in REL_LISTE_PACHETE + REL_STARE_OPKG:
			c = os.path.join(rad, *rel.split("/"))
			if _fisier_bun(c, MAX_LISTA_PACHETE):
				rez["pachete"].append(c)
	for d in langa:
		if not d:
			continue
		nume = list(REL_LISTE_PACHETE[1:])
		try:
			# copia programată a unor imagini pune lista cu adresa MAC în nume: autoinstall<MAC>
			nume += sorted(n for n in os.listdir(d) if TIPAR_AUTOINSTALL.match(n))
		except OSError:
			pass
		for rel in nume:
			c = os.path.join(d, rel)
			if _fisier_bun(c, MAX_LISTA_PACHETE) and c not in rez["pachete"]:
				rez["pachete"].append(c)
	return rez


def cuprins_extra(cale, fel, cale_arhiva="", membri_extra=()):
	"""Câmpurile sursei pentru căutare: {"retea": bool, "picon": bool, "pachete": bool, "acces": bool}. La o arhivă
	`membri_extra` sunt căile de sub rădăcina copiei găsite în ea (fel_extra); fișierele modulelor dintr-o arhivă le
	numără căutarea (HdsImportSurse), deci aici "acces" e False. La un dosar: rădăcina copiei are fișiere în
	LOCURI_ACCES (numai după nume, oprit la primul)."""
	if fel == "arhiva":
		feluri = set(fel_extra(r) for r in membri_extra)
		loc = locuri_extra(cale, fel, cale_arhiva)
		return {"retea": REL_INTERFACES in membri_extra, "picon": False,
			"pachete": "pachete" in feluri or bool(loc["pachete"]), "acces": False}
	loc = locuri_extra(cale, fel)
	rad = radacina_copiei(cale)
	return {"retea": loc["retea"] is not None, "picon": loc["picon"] is not None, "pachete": bool(loc["pachete"]),
		"acces": bool(rad and fisiere_acces(rad, 1)[0])}


# ---------------------------------------------------------------- setările sigure ale meniului

# cheile care înseamnă același lucru în toate imaginile Enigma2 și nu schimbă ecranele imaginii
CHEI_SIGURE = (
	"config.timezone.area",
	"config.timezone.val",
	"config.av.aspect",
	"config.av.aspectratio",
	"config.av.policy_169",
	"config.av.policy_43",
	"config.usage.infobar_timeout",
	"config.usage.show_infobar_on_zap",
	"config.usage.show_infobar_on_skip",
	"config.usage.show_infobar_on_event_change",
	"config.usage.hdd_standby",
	"config.usage.on_movie_start",
	"config.usage.on_movie_stop",
	"config.usage.on_movie_eof",
	"config.usage.on_long_powerpress",
	"config.usage.on_short_powerpress",
	"config.usage.show_message_when_recording_starts",
	"config.usage.load_length_of_movies_in_moviellist",
)
CHEIE_MOD_VIDEO = "config.av.hds_videomode"
TIPAR_MOD_VIDEO = re.compile(r"^(\d{3,4})([ip])$")
TIPAR_RATA = re.compile(r"^(\d{2,3})\s*Hz$", re.I)
MIN_MODURI_TV = 3   # ca VideoOutput.TV_MIN_MODES: o listă mai scurtă vine de la un televizor stins


def _element(config, cheie):
	"""Elementul config pentru „config.a.b.c”, sau None (ConfigSubsection aruncă KeyError, ca în VideoOutput)."""
	nod = config
	for parte in cheie.split(".")[1:]:
		try:
			continut = getattr(nod, "content", None)
			items = getattr(continut, "items", None)
			nod = items[parte] if isinstance(items, dict) else getattr(nod, parte)
		except (KeyError, AttributeError, TypeError):
			return None
	return nod


def valori_permise(element):
	"""Valorile scrise în settings pe care elementul le primește acum, sau None (alt fel de element)."""
	if element is None:
		return None
	alegeri = getattr(element, "choices", None)
	if alegeri is not None and not isinstance(alegeri, (int, float)):
		try:
			return [str(x) for x in alegeri]
		except TypeError:
			return None
	if type(getattr(element, "value", None)) is bool:
		return ["true", "false"]
	return None


def context_setari(config=None, moduri_tv=None):
	"""Pe firul enigma2, înainte de firul importului: {"permise": {cheie: [valori]}, "moduri_tv": [moduri]}. Arborele
	config nu se citește de pe alt fir. `moduri_tv`: modurile declarate de televizor și oferite de driver
	(VideoOutput); implicit citite de aici, [] fără ieșire video sau cu o listă prea scurtă."""
	if config is None:
		from Components.config import config
	permise = {}
	for cheie in CHEI_SIGURE:
		v = valori_permise(_element(config, cheie))
		if v:
			permise[cheie] = v
	if moduri_tv is None:
		moduri_tv = []
		try:
			from Components import VideoOutput
			iesire = VideoOutput.videoOutput
			if iesire is not None and _element(config, CHEIE_MOD_VIDEO) is not None:
				oferite = list(iesire.choices.get("videomode") or [])
				tv = [m for m in (iesire.preferred or []) if m in oferite]
				moduri_tv = tv if len(tv) >= MIN_MODURI_TV else []
		except Exception as eroare:
			_jurnal("modurile video: %s" % eroare.__class__.__name__)
	return {"permise": permise, "moduri_tv": list(moduri_tv)}


def mod_video_din_copie(toate):
	"""Modul video al altei imagini, în numele driverului ("1080i50"), din config.av.videoport, config.av.videomode.<p>
	și config.av.videorate.<mod>; None fără ele."""
	port = toate.get("config.av.videoport", "HDMI").strip() or "HDMI"
	mod = (toate.get("config.av.videomode.%s" % port) or "").strip()
	m = TIPAR_MOD_VIDEO.match(mod)
	if not m:
		return None
	rata = (toate.get("config.av.videorate.%s" % mod) or "").strip()
	r = TIPAR_RATA.match(rata)
	if r:
		return mod + r.group(1)
	return mod


def chei_sigure(toate, context):
	"""({cheie: valoare}, câte au fost lăsate deoparte) din settings-ul copiei (`toate`), numai CHEI_SIGURE care există
	aici cu o valoare permisă acum (`context` din context_setari) și modul video când televizorul îl declară. Ce nu se
	potrivește se lasă deoparte, fără eroare."""
	context = context or {}
	permise = context.get("permise") or {}
	rez = {}
	lasate = 0
	for cheie in CHEI_SIGURE:
		if cheie not in toate:
			continue
		valoare = (toate[cheie] or "").split("\n", 1)[0].strip()
		if valoare in (permise.get(cheie) or ()):
			rez[cheie] = valoare
		else:
			lasate += 1
	mod = mod_video_din_copie(toate)
	if mod:
		tv = context.get("moduri_tv") or ()
		potrivit = mod if mod in tv else None
		if potrivit is None and mod[-1:] in ("i", "p"):
			# fără rată în copie: modul cu rata cea mai mică declarată de televizor (50 Hz în Europa)
			potrivite = sorted((m for m in tv if m.startswith(mod) and m[len(mod):].isdigit()), key=lambda m: int(m[len(mod):]))
			potrivit = potrivite[0] if potrivite else None
		if potrivit:
			rez[CHEIE_MOD_VIDEO] = potrivit
		else:
			lasate += 1
	return rez, lasate


# ---------------------------------------------------------------- piconurile

def _spatiu_liber(dosar):
	d = dosar
	while d and not os.path.isdir(d):
		d = os.path.dirname(d.rstrip("/\\"))
	try:
		st = os.statvfs(d or "/")
		return st.f_bavail * st.f_frsize
	except (AttributeError, OSError):
		return None


def copiaza_piconuri(sursa, dest=DEST_PICON, max_fisiere=MAX_PICONURI, max_octeti=MAX_PICON_OCTETI,
		max_total=MAX_PICON_TOTAL, rezerva=REZERVA_PICON, termen_s=TERMEN_PICON_S):
	"""Copiază piconurile din dosarul `sursa` în `dest`: numai fișierele obișnuite .png cu nume simplu (TIPAR_PICON),
	fiecare de cel mult `max_octeti`, cel mult `max_fisiere` și `max_total` octeți, lăsând `rezerva` liberă. Întoarce
	{"copiate", "sarite", "oprit": motiv sau ""}. Rulează pe firul importului."""
	rez = {"copiate": 0, "sarite": 0, "oprit": ""}
	termen = time.time() + termen_s
	try:
		intrari = sorted(os.listdir(sursa))
	except OSError:
		rez["oprit"] = "necitit"
		return rez
	alese = []
	total = 0
	for n in intrari:
		if len(alese) >= max_fisiere:
			rez["oprit"] = "limita"
			break
		if not TIPAR_PICON.match(n):
			continue
		c = os.path.join(sursa, n)
		try:
			if os.path.islink(c) or not os.path.isfile(c):
				continue
			m = os.path.getsize(c)
		except OSError:
			continue
		if not 0 < m <= max_octeti:
			rez["sarite"] += 1
			continue
		if total + m > max_total:
			rez["oprit"] = "limita"
			break
		total += m
		alese.append(n)
	liber = _spatiu_liber(dest)
	if liber is not None and liber - total < rezerva:
		rez["oprit"] = "spatiu"
		return rez
	try:
		os.makedirs(dest, exist_ok=True)
	except OSError:
		rez["oprit"] = "necitit"
		return rez
	for n in alese:
		if time.time() > termen:
			rez["oprit"] = "timp"
			break
		tinta = os.path.join(dest, n)
		if os.path.islink(tinta):
			rez["sarite"] += 1
			continue
		try:
			shutil.copyfile(os.path.join(sursa, n), tinta + ".nou")
			os.replace(tinta + ".nou", tinta)
			rez["copiate"] += 1
		except (OSError, IOError):
			rez["sarite"] += 1
			try:
				os.remove(tinta + ".nou")
			except OSError:
				pass
	return rez


# ---------------------------------------------------------------- pluginurile

def _categorie(nume):
	"""A treia parte a numelui (enigma2-plugin-<categorie>-...)."""
	parti = nume.split("-")
	return parti[2] if len(parti) > 3 else ""


def pachet_bun(nume):
	"""Un nume de plugin care se poate oferi: enigma2-plugin-..., nume valid, nu al unui modul de acces condiționat."""
	if not nume.startswith(PREFIX_PLUGIN) or not TIPAR_NUME_PACHET.match(nume):
		return False
	if _nume_de_modul(nume):
		return False
	return _categorie(nume) not in CATEGORII_NEOFERITE


def _din_text(text):
	nume = set()
	if "Package:" in text:
		pachet = None
		for rand in text.splitlines() + [""]:
			if rand.startswith("Package:"):
				pachet = rand.split(":", 1)[1].strip()
			elif rand.startswith("Status:") and pachet:
				if "installed" in rand.split() and "not-installed" not in rand:
					nume.add(pachet)
			elif not rand.strip():
				pachet = None
		return nume
	for rand in text.splitlines():
		rand = rand.strip()
		if not rand or rand.startswith("#"):
			continue
		cuvant = rand.split()[0]
		cuvant = os.path.basename(cuvant)
		if cuvant.endswith(".ipk"):
			cuvant = cuvant[:-4].split("_", 1)[0]
		nume.add(cuvant.lower())
	return nume


def citeste_pachete(cai):
	"""(pluginurile care se pot oferi, câte pluginuri avea copia) din fișierele listelor pachetelor instalate ale copiei.
	Pachetele modulelor de acces condiționat nu intră nici în număr; skinurile, listele de canale și driverele se
	numără, dar nu se oferă."""
	toate = set()
	for cale in cai or ():
		try:
			with open(cale, "r", encoding="utf-8", errors="replace") as f:
				toate |= _din_text(f.read(MAX_LISTA_PACHETE))
		except (OSError, IOError):
			continue
	pluginuri = sorted(n for n in toate if n.startswith(PREFIX_PLUGIN) and TIPAR_NUME_PACHET.match(n)
		and not _nume_de_modul(n))
	return [n for n in pluginuri if pachet_bun(n)], len(pluginuri)


def potriveste_pachete(nume, catalog):
	"""Pluginurile copiei față de sursele de pachete ale receptorului (HdsPachete.Catalog): {"oferite": [[nume, titlu]]
	(în surse și neinstalate), "instalate": câte sunt deja, "lipsa": câte nu sunt în surse, "fara_lista": True când
	receptorul nu are încă lista surselor}."""
	rez = {"oferite": [], "instalate": 0, "lipsa": 0, "fara_lista": False}
	pachete = getattr(catalog, "pachete", None) or {}
	if not getattr(catalog, "varsta_liste", 0):
		rez["fara_lista"] = True
	for n in nume:
		p = pachete.get(n)
		if p is None:
			rez["lipsa"] += 1
		elif p.instalat:
			rez["instalate"] += 1
		elif p.se_poate_instala and getattr(p, "categorie", "") != "acces":
			rez["oferite"].append([n, p.titlu or n])
		else:
			rez["lipsa"] += 1
	return rez


# ---------------------------------------------------------------- modulele de acces condiționat

def _reinstalare():
	try:
		from Components import HdsReinstalare as R
	except ImportError:  # probe pe PC: modulul de lângă acesta
		import HdsReinstalare as R
	return R


def _copie():
	try:
		from Components import HdsCopieSetari as C
	except ImportError:  # probe pe PC
		import HdsCopieSetari as C
	return C


def _c(rad, rel):
	return os.path.join(rad or "/", *rel.split("/"))


def este_pachet_acces(nume):
	"""enigma2-plugin-<categorie>-<nume>, cu categoria modulelor de acces (TIPAR_CATEGORIE_ACCES)."""
	nume = nume or ""
	return (nume.startswith(PREFIX_PLUGIN) and bool(TIPAR_NUME_PACHET.match(nume))
		and bool(TIPAR_CATEGORIE_ACCES.match(_categorie(nume))))


def nume_scurt(nume):
	"""Numele arătat al unui pachet: fără enigma2-plugin-<categorie>- (ca HdsReinstalare._scurt)."""
	if nume.startswith(PREFIX_PLUGIN):
		rest = nume[len(PREFIX_PLUGIN):]
		return rest.split("-", 1)[1] if "-" in rest else rest
	return nume


def este_loc_acces(rel):
	"""`rel` (cale sub rădăcina copiei, cu /) e sub unul din LOCURI_ACCES."""
	rel = (rel or "").replace("\\", "/").strip("/")
	return any(rel.startswith(loc + "/") for loc in LOCURI_ACCES)


def _cale_cu_legatura(rad, rel):
	"""Vreun nume din `rel` (de la rădăcina copiei în jos) e o legătură simbolică (/var/keys -> /usr/keys într-o
	rădăcină ar trimite la fișierele receptorului)."""
	cale = rad
	for parte in rel.split("/"):
		cale = os.path.join(cale, parte)
		if os.path.islink(cale):
			return True
	return False


def fisiere_acces(rad, max_fisiere=MAX_FISIERE_ACCES):
	"""([(rel, mărime)], tăiat): fișierele obișnuite din LOCURI_ACCES de sub rădăcina `rad`, aflate numai după nume și
	lstat (nimic nu se deschide), fără legături și fără dosare legate, cel mult `max_fisiere`."""
	rez = []
	if not rad:
		return rez, False
	for loc in LOCURI_ACCES:
		baza = _c(rad, loc)
		if not os.path.isdir(baza) or _cale_cu_legatura(rad, loc):
			continue
		for d, dosare, fisiere in os.walk(baza):
			dosare[:] = sorted(x for x in dosare if not os.path.islink(os.path.join(d, x)))
			for n in sorted(fisiere):
				c = os.path.join(d, n)
				try:
					st = os.lstat(c)
				except OSError:
					continue
				if not stat.S_ISREG(st.st_mode):
					continue
				rez.append((os.path.relpath(c, rad).replace("\\", "/"), st.st_size))
				if len(rez) >= max_fisiere:
					return rez, True
	return rez, False


def _spatiu_liber_acces(rad_sistem):
	return _spatiu_liber(_c(rad_sistem, "etc"))


def copiaza_acces(perechi, rad_sistem="/", inainte=None, termen_s=TERMEN_ACCES_S, max_fisier=MAX_FISIER_ACCES,
		max_total=MAX_TOTAL_ACCES, rezerva=REZERVA_ACCES):
	"""Copiază ca atare fișierele `perechi` [(cale sursă, rel țintă)] sub `rad_sistem`: shutil.copyfile (octet cu octet;
	nimic nu se deschide ca text), scris lângă țintă și mutat dintr-o bucată. Un fișier de acum identic (filecmp, octet
	cu octet) nu se rescrie; unul diferit se păstrează întâi în `inainte` (dacă e dat), cu aceeași cale. O țintă care e
	legătură sau dosar nu se atinge. Mod: al fișierului de acum, altfel 0755 / 0644 după sursă.
	Întoarce {"copiate", "la_fel", "pastrate", "sarite", "oprit": "" / "spatiu" / "limita" / "timp"}."""
	import filecmp
	rez = {"copiate": 0, "la_fel": 0, "pastrate": 0, "sarite": 0, "oprit": ""}
	termen = time.time() + termen_s
	alese = []
	total = 0
	for sursa, rel in perechi:
		try:
			marime = os.path.getsize(sursa)
		except OSError:
			rez["sarite"] += 1
			continue
		if marime > max_fisier:
			rez["sarite"] += 1
			continue
		if total + marime > max_total:
			rez["oprit"] = "limita"
			break
		total += marime
		alese.append((sursa, rel))
	liber = _spatiu_liber_acces(rad_sistem)
	if liber is not None and liber - total < rezerva:
		rez["oprit"] = "spatiu"
		return rez
	for sursa, rel in alese:
		if time.time() > termen:
			rez["oprit"] = "timp"
			break
		tinta = _c(rad_sistem, rel)
		try:
			if os.path.islink(tinta) or os.path.isdir(tinta):
				rez["sarite"] += 1
				continue
			exista = os.path.isfile(tinta)
			if exista and os.path.exists(sursa) and os.path.samefile(sursa, tinta):
				rez["la_fel"] += 1
				continue
			if exista and filecmp.cmp(sursa, tinta, shallow=False):
				rez["la_fel"] += 1
				continue
			if exista:
				mod = stat.S_IMODE(os.stat(tinta).st_mode)
				if inainte:
					pastrat = os.path.join(inainte, *rel.split("/"))
					os.makedirs(os.path.dirname(pastrat), mode=0o700, exist_ok=True)
					shutil.copyfile(tinta, pastrat)
					os.chmod(pastrat, 0o600)
					rez["pastrate"] += 1
			else:
				mod = 0o755 if os.stat(sursa).st_mode & 0o111 else 0o644
				os.makedirs(os.path.dirname(tinta), mode=0o755, exist_ok=True)
			nou = tinta + ".hds-nou"
			shutil.copyfile(sursa, nou)
			os.chmod(nou, mod)
			os.replace(nou, tinta)
			rez["copiate"] += 1
		except (OSError, IOError):
			rez["sarite"] += 1
			try:
				os.remove(tinta + ".hds-nou")
			except OSError:
				pass
	return rez


def pachete_acces_din_copie(cai):
	"""Pachetele modulelor de acces instalate în copie, din listele ei de pachete (aceleași ca la citeste_pachete, care
	le lasă deoparte); numai numele, ordonate."""
	toate = set()
	for cale in cai or ():
		try:
			with open(cale, "r", encoding="utf-8", errors="replace") as f:
				toate |= _din_text(f.read(MAX_LISTA_PACHETE))
		except (OSError, IOError):
			continue
	return sorted(n for n in toate if este_pachet_acces(n))


def _lista_pachetului(rad, nume):
	"""Căile (fără / la început) din var/lib/opkg/info/<nume>.list sub `rad` (lista fișierelor puse de opkg)."""
	try:
		with open(_c(rad, "%s/%s.list" % (INFO_OPKG, nume)), "r", encoding="utf-8", errors="replace") as f:
			text = f.read(4 * 1024 * 1024)
	except (OSError, IOError):
		return []
	return [r.split("\t", 1)[0].strip().lstrip("/") for r in text.splitlines() if r.strip()]


def dosare_config_pachet(rad, nume):
	"""Dosarele de sub etc/tuxbox/config (primul nivel: etc/tuxbox/config/<x>) puse de pachetul `nume` sub `rad`."""
	rez = []
	prefix = DOSAR_CONFIG_ACCES + "/"
	for c in _lista_pachetului(rad, nume):
		if c.startswith(prefix):
			d = prefix + c[len(prefix):].split("/", 1)[0]
			if d != prefix and d not in rez:
				rez.append(d)
	return rez


def _module_acces():
	try:
		from Components import HdsModuleAcces as M
	except ImportError:  # probe pe PC
		import HdsModuleAcces as M
	return M


def dosare_config_aici(rad, nume):
	"""Dosarele de configurare (etc/tuxbox/config/<x>) ale pachetului `nume` instalat sub `rad`: din lista lui opkg
	(dosare_config_pachet) sau, când lista nu are dosarul (opkg nu trece mereu dosarele în ea), din scriptul lui
	<fel>.<x> (argumentul -c / --config-dir al pornirii, HdsModuleAcces.dosar_configurare_din_script; se citește
	scriptul pachetului, nu fișierele omului)."""
	rez = dosare_config_pachet(rad, nume)
	if rez:
		return rez
	try:
		M = _module_acces()
		feluri = _copie().feluri_acces(rad)
	except Exception as eroare:
		_jurnal("dosarul modulului: %s" % eroare.__class__.__name__)
		return rez
	for _fel, script in scripturi_pachet(rad, nume, feluri):
		try:
			with open(_c(rad, "etc/init.d/" + script), "r", encoding="utf-8", errors="replace") as f:
				dosar = M.dosar_configurare_din_script(f.read(64 * 1024))
		except (OSError, IOError, ValueError):
			continue
		rel = (dosar or "").strip("/")
		if rel.startswith(DOSAR_CONFIG_ACCES + "/"):
			d = DOSAR_CONFIG_ACCES + "/" + rel[len(DOSAR_CONFIG_ACCES) + 1:].split("/", 1)[0]
			if d not in rez:
				rez.append(d)
	return rez


def scripturi_pachet(rad, nume, feluri):
	"""[(fel, script)]: scripturile <fel>.<x> din etc/init.d puse de pachetul `nume`, pentru felurile date."""
	rez = []
	for c in _lista_pachetului(rad, nume):
		if c.startswith("etc/init.d/"):
			script = c[len("etc/init.d/"):]
			fel, _p, sufix = script.partition(".")
			if fel in feluri and sufix and sufix != SUFIX_GOL_ACCES and "/" not in script:
				rez.append((fel, script))
	return rez


def alese_in_copie(rad):
	"""{fel: script}: modulul ales al fiecărui fel în etc/init.d al copiei (legătura <fel> -> <fel>.<x>, citită cu
	os.readlink: nu se urmează și nu se deschide nimic). Felurile după formă (HdsCopieSetari.feluri_din_nume_acces)."""
	initd = _c(rad, "etc/init.d")
	if not rad or not os.path.isdir(initd) or _cale_cu_legatura(rad, "etc/init.d"):
		return {}

	def legatura(n):
		c = os.path.join(initd, n)
		try:
			return os.readlink(c) if os.path.islink(c) else None
		except OSError:
			return None
	try:
		nume = os.listdir(initd)
	except OSError:
		return {}
	rez = {}
	for fel in _copie().feluri_din_nume_acces(nume, legatura):
		tinta = legatura(fel)
		if not tinta:
			continue
		script = os.path.basename(tinta)
		if script.startswith(fel + ".") and script != fel + "." + SUFIX_GOL_ACCES:
			rez[fel] = script
	return rez


def pachet_al_scriptului(rad, script, pachete):
	"""Pachetul (dintre `pachete`) care a pus etc/init.d/<script> sub `rad`, după listele opkg; None."""
	for p in pachete:
		if "etc/init.d/" + script in _lista_pachetului(rad, p):
			return p
	return None


def modul_de_ales(rad_copie, rad_sistem, pachete_copie, instalate_aici):
	"""Ce modul se alege după import: {"fel", "sufix", "nume" (pachetul, scurt), "reporneste"} sau None.
	- modulul ales în copie (alese_in_copie), când scriptul lui există aici, sau, cu alt nume, scriptul aceluiași pachet,
	  instalat aici;
	- copia fără legături (o arhivă de copie nu le are): când copia avea un singur pachet de modul, instalat acum aici,
	  iar felul lui nu are aici niciun modul ales.
	"reporneste": scriptul e deja cel ales aici (fișierele lui tocmai s-au schimbat, deci repornire, nu alegere)."""
	C = _copie()
	feluri = C.feluri_acces(rad_sistem)
	initd = _c(rad_sistem, "etc/init.d")

	def ales_aici(fel):
		try:
			t = os.readlink(os.path.join(initd, fel))
		except OSError:
			return None
		b = os.path.basename(t)
		return b if b.startswith(fel + ".") and b != fel + "." + SUFIX_GOL_ACCES else None

	def rezultat(fel, script, pachet):
		sufix = script[len(fel) + 1:]
		return {"fel": fel, "sufix": sufix, "nume": nume_scurt(pachet) if pachet else sufix,
			"reporneste": ales_aici(fel) == script}

	alese = alese_in_copie(rad_copie)
	for fel, script in sorted(alese.items()):
		if fel not in feluri:
			continue
		pachet = pachet_al_scriptului(rad_copie, script, pachete_copie)
		if os.path.isfile(os.path.join(initd, script)) and not os.path.islink(os.path.join(initd, script)):
			return rezultat(fel, script, pachet)
		if pachet and pachet in instalate_aici:
			for f, s in scripturi_pachet(rad_sistem, pachet, (fel,)):
				if os.path.isfile(os.path.join(initd, s)):
					return rezultat(f, s, pachet)
	if alese or len(pachete_copie) != 1 or pachete_copie[0] not in instalate_aici:
		return None
	pachet = pachete_copie[0]
	for f, s in scripturi_pachet(rad_sistem, pachet, feluri):
		if ales_aici(f) is None and os.path.isfile(os.path.join(initd, s)):
			return rezultat(f, s, pachet)
	return None


def reinstaleaza_acces(nume, rad_sistem="/", opkg=None):
	"""Pe firul importului: pachetele `nume` (ale modulelor din copie) puse din nou din sursele de pachete ale
	receptorului: opkg update o dată, apoi opkg install pe fiecare care lipsește (ca HdsReinstalare.lucreaza).
	Întoarce {"puse", "deja", "lipsa", "amanate"}: lipsa = nu există în sursele de pachete (spus numai după un update
	reușit); amanate = nu s-au putut instala acum (fără internet, opkg ocupat)."""
	R = _reinstalare()
	rez = {"puse": [], "deja": [], "lipsa": [], "amanate": []}
	acum = R.instalate(rad_sistem)
	de_pus = []
	for n in nume:
		(rez["deja"] if n in acum else de_pus).append(n)
	if not de_pus:
		return rez
	comanda = R._opkg(rad_sistem, opkg)
	actualizat = comanda is not None and R._ruleaza(comanda + ["update"], R.TERMEN_UPDATE_S) == 0
	disponibile = R._in_liste(rad_sistem)
	for n in de_pus:
		if n not in disponibile:
			rez["lipsa" if actualizat else "amanate"].append(n)
		elif comanda is not None and R._ruleaza(comanda + ["install", n], R.TERMEN_INSTALARE_S) == 0:
			rez["puse"].append(n)
		else:
			rez["amanate"].append(n)
	return rez


def _fisiere_dosar(rad, rel, recursiv=True):
	"""[(cale, rel_in_dosar)]: fișierele obișnuite din dosarul rel sub rad, fără legături."""
	baza = _c(rad, rel)
	rez = []
	if not os.path.isdir(baza) or _cale_cu_legatura(rad, rel):
		return rez
	for d, dosare, fisiere in os.walk(baza):
		dosare[:] = sorted(x for x in dosare if recursiv and not os.path.islink(os.path.join(d, x)))
		for n in sorted(fisiere):
			c = os.path.join(d, n)
			if os.path.isfile(c) and not os.path.islink(c):
				rez.append((c, os.path.relpath(c, baza).replace("\\", "/")))
	return rez


def dosar_din_copie(rad_copie, rad_sistem, pachet, dosar_aici, ocupate):
	"""Pentru un pachet instalat acum de import, al cărui dosar de configurare de aici (`dosar_aici`, etc/tuxbox/config/<x>)
	nu are pereche în copie: dosarul din copie în care imaginea veche ținea fișierele modulului, ca să fie copiate și în
	dosarul citit aici. Numai după nume: (1) dosarul pus de același pachet în copie (lista lui opkg); (2) singurul dosar
	al copiei de sub etc/tuxbox/config, neocupat de alt modul de aici (`ocupate`), care are fișiere cu aceleași nume ca
	cele puse acum de instalare în `dosar_aici`; (3) fișierele de pe primul nivel al lui etc/tuxbox/config din copie
	(imaginile vechi le țineau acolo), cu aceleași nume. Întoarce (rel, recursiv) sau None."""
	if _fisiere_dosar(rad_copie, dosar_aici):
		return None
	for d in dosare_config_pachet(rad_copie, pachet):
		if d not in ocupate and _fisiere_dosar(rad_copie, d):
			return d, True
	nume_aici = set(os.path.basename(c) for c, _r in _fisiere_dosar(rad_sistem, dosar_aici))
	if not nume_aici:
		return None
	config = _c(rad_copie, DOSAR_CONFIG_ACCES)
	potrivite = []
	try:
		intrari = sorted(os.listdir(config)) if not _cale_cu_legatura(rad_copie, DOSAR_CONFIG_ACCES) else []
	except OSError:
		intrari = []
	for n in intrari:
		rel = DOSAR_CONFIG_ACCES + "/" + n
		if rel in ocupate or not os.path.isdir(os.path.join(config, n)) or os.path.islink(os.path.join(config, n)):
			continue
		if nume_aici & set(os.path.basename(c) for c, _r in _fisiere_dosar(rad_copie, rel, False)):
			potrivite.append(rel)
	if len(potrivite) == 1:
		return potrivite[0], True
	if not potrivite and nume_aici & set(os.path.basename(c) for c, _r in _fisiere_dosar(rad_copie, DOSAR_CONFIG_ACCES,
			False)):
		return DOSAR_CONFIG_ACCES, False
	return None


def _dosar_inainte(rad_sistem):
	"""Dosarul acestui import pentru fișierele de acum înlocuite: DOSAR_INAINTE_ACCES/<data>[-n] (făcut numai când
	chiar se păstrează ceva, de copiaza_acces)."""
	baza = os.path.join(_c(rad_sistem, DOSAR_INAINTE_ACCES), time.strftime("%Y%m%d_%H%M%S"))
	d, n = baza, 1
	while os.path.exists(d):
		n += 1
		d = "%s-%d" % (baza, n)
	return d


def _curata_inainte(rad_sistem, pastrate=PASTRATE_INAINTE):
	"""Rămân numai fișierele înlocuite de ultimele `pastrate` importuri (numele dosarelor au data)."""
	baza = _c(rad_sistem, DOSAR_INAINTE_ACCES)
	try:
		dosare = sorted(n for n in os.listdir(baza) if os.path.isdir(os.path.join(baza, n))
			and not os.path.islink(os.path.join(baza, n)))
	except OSError:
		return
	for n in dosare[:max(0, len(dosare) - pastrate)]:
		shutil.rmtree(os.path.join(baza, n), ignore_errors=True)


def importa_acces(rad_copie, liste_pachete, rad_sistem="/", opkg=None, reinstalare=True):
	"""Tot lucrul cu modulele de acces al importului, pe firul lui: fișierele copiei copiate ca atare (cele de acum
	înlocuite păstrate în DOSAR_INAINTE_ACCES), pachetele reinstalate, fișierele puse iar peste ce a scris instalarea
	(și în dosarul citit aici, când imaginea veche le ținea în altul: dosar_din_copie), coada pentru pornirea următoare
	cu ce nu s-a putut instala acum, modulul de ales. Întoarce {"copiate", "pastrate", "oprit", "pachete", "puse",
	"deja", "lipsa", "amanate", "alege"}: numai numere și nume de pachete; nicio cale și niciun conținut."""
	rez = {"copiate": 0, "pastrate": 0, "oprit": "", "pachete": 0, "puse": [], "deja": [], "lipsa": [], "amanate": [],
		"alege": None}
	fisiere, taiat = fisiere_acces(rad_copie)
	perechi = [(_c(rad_copie, rel), rel) for rel, _m in fisiere]
	if perechi:
		inainte = _dosar_inainte(rad_sistem)
		r = copiaza_acces(perechi, rad_sistem, inainte)
		_curata_inainte(rad_sistem)
		rez["copiate"] = r["copiate"] + r["la_fel"]
		rez["pastrate"] = r["pastrate"]
		rez["oprit"] = r["oprit"] or ("limita" if taiat else "")
		_jurnal("modulele de acces: %d fisiere copiate ca atare (%d la fel), %d pastrate, %d sarite%s" % (r["copiate"],
			r["la_fel"], r["pastrate"], r["sarite"], (", oprit: " + rez["oprit"]) if rez["oprit"] else ""))
		if r["oprit"] == "spatiu":
			return rez
	pachete = pachete_acces_din_copie(liste_pachete)
	rez["pachete"] = len(pachete)
	if not pachete or not reinstalare:
		return rez
	try:
		inst = reinstaleaza_acces(pachete, rad_sistem, opkg)
	except Exception as eroare:
		_jurnal("instalarea modulelor: %s" % eroare.__class__.__name__)
		inst = {"puse": [], "deja": [], "lipsa": [], "amanate": list(pachete)}
	for k in ("puse", "deja", "lipsa", "amanate"):
		rez[k] = list(inst[k])
	if inst["puse"] and perechi:
		# instalarea poate scrie în fișierele modulului (configurarea de pornire): copia lor pusă iar, fără păstrare
		copiaza_acces(perechi, rad_sistem, None)
		ocupate = set()
		for p in set(inst["puse"]) | set(inst["deja"]):
			ocupate.update(dosare_config_aici(rad_sistem, p))
		for p in inst["puse"]:
			for d in dosare_config_aici(rad_sistem, p):
				gasit = dosar_din_copie(rad_copie, rad_sistem, p, d, ocupate - set([d]))
				if gasit:
					rel_copie, recursiv = gasit
					mutate = [(c, d + "/" + r) for c, r in _fisiere_dosar(rad_copie, rel_copie, recursiv)]
					m = copiaza_acces(mutate, rad_sistem, None)
					_jurnal("modulele de acces: %d fisiere puse si in dosarul citit de modulul instalat acum" %
						(m["copiate"] + m["la_fel"]))
	if inst["amanate"]:
		try:
			legaturi = {}
			for fel, script in alese_in_copie(rad_copie).items():
				if pachet_al_scriptului(rad_copie, script, inst["amanate"]):
					legaturi["etc/init.d/" + fel] = script
			_reinstalare().adauga(rad_sistem, [(n, "acces") for n in inst["amanate"]], legaturi)
		except Exception as eroare:
			_jurnal("coada modulelor: %s" % eroare.__class__.__name__)
	try:
		rez["alege"] = modul_de_ales(rad_copie, rad_sistem, pachete, set(inst["puse"]) | set(inst["deja"]))
	except Exception as eroare:
		_jurnal("modulul de ales: %s" % eroare.__class__.__name__)
	return rez


def texte_acces(r):
	"""Rândurile pentru om din rezultatul importa_acces (numere și numele scurte ale pachetelor)."""
	mesaje = []
	if r.get("oprit") == "spatiu":
		mesaje.append(_("Fișierele modulelor de acces nu încap în memoria receptorului; nu le-am copiat."))
	elif r.get("copiate"):
		mesaje.append(ngettext("Module de acces: %d fișier copiat așa cum era.",
			"Module de acces: %d fișiere copiate așa cum erau.", r["copiate"]) % r["copiate"])
		if r.get("oprit"):
			mesaje.append(_("Copia are mai multe fișiere ale modulelor decât încap în import; am copiat o parte."))
	if r.get("pastrate"):
		mesaje.append(ngettext("%d fișier al modulelor, înlocuit de copie, a rămas păstrat pe receptor.",
			"%d fișiere ale modulelor, înlocuite de copie, au rămas păstrate pe receptor.", r["pastrate"]) % r["pastrate"])
	if r.get("puse"):
		mesaje.append(_("Module de acces instalate din nou: %s.") % ", ".join(nume_scurt(n) for n in r["puse"]))
	if r.get("lipsa"):
		mesaje.append(_("Nu există în sursele de pachete ale imaginii: %s. Fișierele lor sunt copiate; alege alt modul "
			"din Meniu, Acces condiționat, Module de acces condiționat.") % ", ".join(nume_scurt(n) for n in r["lipsa"]))
	if r.get("amanate"):
		mesaje.append(_("Nu s-au putut instala acum (fără internet sau cu sursele de pachete ocupate): %s. Se instalează "
			"singure la următoarea pornire a receptorului.") % ", ".join(nume_scurt(n) for n in r["amanate"]))
	return mesaje


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext); fără pachetul Components (probele de pe PC), forma romanească:
	unu pentru n == 1, altfel multe. Numele e cel știut de xgettext."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		return unu if n == 1 else multe
	return plural(unu, multe, n)


# ---------------------------------------------------------------- rețeaua din copie

class ParolaWifi(object):
	"""Rețeaua Wi-Fi din copie: SSID (octeți), securitatea și parola. Parola nu apare în repr, în texte sau în jurnal."""

	__slots__ = ("ssid", "securitate", "parola", "ascunsa")

	def __init__(self, ssid, securitate, parola, ascunsa=False):
		self.ssid = ssid
		self.securitate = securitate
		self.parola = parola
		self.ascunsa = ascunsa

	def __repr__(self):
		return "<ParolaWifi>"

	__str__ = __repr__


def _ip(text):
	parti = (text or "").strip().split(".")
	if len(parti) != 4:
		return None
	try:
		n = [int(p) for p in parti]
	except ValueError:
		return None
	return n if all(0 <= x <= 255 for x in n) else None


def _masca(text):
	text = (text or "").strip()
	if text.isdigit() and 0 <= int(text) <= 32:
		biti = (0xFFFFFFFF << (32 - int(text))) & 0xFFFFFFFF
		return [(biti >> s) & 255 for s in (24, 16, 8, 0)]
	return _ip(text)


def este_wifi(placa):
	return (placa or "").startswith(("wlan", "ra", "wifi", "wl"))


def citeste_interfaces(text):
	"""{placa: {"auto": bool, "dhcp": bool, "ip", "masca", "poarta" (liste de 4 sau None), "wpa_conf": cale sau None,
	"dns": [liste de 4]}} din etc/network/interfaces (forma scrisă de imaginile Enigma2)."""
	placi = {}
	auto = set()
	curenta = None
	for rand in (text or "").splitlines():
		r = rand.split("#", 1)[0].strip()
		if not r:
			continue
		cuv = r.split()
		if cuv[0] in ("auto", "allow-hotplug"):
			auto.update(cuv[1:])
			curenta = None
		elif cuv[0] == "iface" and len(cuv) >= 4:
			curenta = None
			if cuv[2] != "inet" or cuv[1] == "lo":
				continue
			curenta = placi.setdefault(cuv[1], {"dhcp": cuv[3] == "dhcp", "ip": None, "masca": None, "poarta": None,
				"wpa_conf": None, "dns": [], "metoda": cuv[3]})
		elif curenta is not None and len(cuv) >= 2:
			if cuv[0] == "address":
				curenta["ip"] = _ip(cuv[1].split("/")[0])
				if "/" in cuv[1] and curenta["masca"] is None:
					curenta["masca"] = _masca(cuv[1].split("/", 1)[1])
			elif cuv[0] == "netmask":
				curenta["masca"] = _masca(cuv[1])
			elif cuv[0] == "gateway":
				curenta["poarta"] = _ip(cuv[1])
			elif cuv[0] == "dns-nameservers":
				curenta["dns"] += [x for x in (_ip(c) for c in cuv[1:]) if x]
			elif cuv[0] == "wpa-conf":
				curenta["wpa_conf"] = cuv[1]
			elif cuv[0] in ("pre-up", "up") and "wpa_supplicant" in r:
				m = re.search(r"-c\s*(\S+)", r)
				if m:
					curenta["wpa_conf"] = m.group(1)
	for nume, p in placi.items():
		p["auto"] = nume in auto
	return placi


def _valoare_conf(v):
	v = v.strip()
	if len(v) >= 2 and v[0] == "\"" and v[-1] == "\"":
		return v[1:-1], True
	return v, False


def retea_wifi_din_conf(text):
	"""Rețeaua Wi-Fi din wpa_supplicant.conf al copiei (prima pornită, cea cu prioritatea cea mai mare), ca ParolaWifi;
	(None, motiv) când nu e una pe care o poate folosi imaginea ("fara", "neacceptata")."""
	from Components import WlanTools
	retele = []
	for ssid, bloc in WlanTools.parseConf(text or "")[1]:
		if ssid is None:
			continue
		campuri = {}
		for rand in bloc.splitlines()[1:]:
			r = rand.strip()
			if "=" in r and not r.startswith("#"):
				k, v = r.split("=", 1)
				campuri[k.strip()] = v
		if campuri.get("disabled", "").strip() == "1":
			continue
		try:
			prioritate = int(campuri.get("priority", "0").strip())
		except ValueError:
			prioritate = 0
		retele.append((-prioritate, len(retele), ssid, campuri))
	if not retele:
		return None, "fara"
	retele.sort(key=lambda r: (r[0], r[1]))
	_p, _i, ssid, c = retele[0]
	mgmt = set((c.get("key_mgmt") or "WPA-PSK").replace("\"", "").split())
	psk, psk_text = _valoare_conf(c.get("psk", ""))
	sae, _sae_text = _valoare_conf(c.get("sae_password", ""))
	ascunsa = c.get("scan_ssid", "").strip() == "1"
	if mgmt == {"NONE"} and not c.get("wep_key0"):
		return ParolaWifi(ssid, WlanTools.SECURITY_OPEN, "", ascunsa), None
	if mgmt == {"OWE"}:
		return ParolaWifi(ssid, WlanTools.SECURITY_OWE, "", ascunsa), None
	if "SAE" in mgmt:
		parola = sae or (psk if psk_text else "")
		if not parola:
			return None, "neacceptata"
		fel = WlanTools.SECURITY_WPA2_WPA3 if mgmt & {"WPA-PSK", "WPA-PSK-SHA256"} else WlanTools.SECURITY_WPA3
		return ParolaWifi(ssid, fel, parola, ascunsa), None
	if mgmt & {"WPA-PSK", "WPA-PSK-SHA256"} and psk:
		return ParolaWifi(ssid, WlanTools.SECURITY_WPA2, psk, ascunsa), None
	return None, "neacceptata"


def _citeste_text(cale, maxim=MAX_FISIER_RETEA):
	try:
		if os.path.islink(cale):
			return None
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return f.read(maxim)
	except (OSError, IOError, TypeError):
		return None


def _dns_din_resolv(text):
	rez = []
	for rand in (text or "").splitlines():
		cuv = rand.split("#", 1)[0].split()
		if len(cuv) >= 2 and cuv[0] == "nameserver":
			ip = _ip(cuv[1])
			if ip and ip not in rez:
				rez.append(ip)
	return rez[:3]


def _wpa_pentru(placa, setari, loc):
	"""Calea în copie a lui wpa_supplicant pentru placa Wi-Fi: cea din interfaces (sub rădăcina copiei), altfel
	etc/wpa_supplicant.<placa>.conf, altfel etc/wpa_supplicant.conf."""
	rad = loc.get("radacina") or ""
	alese = []
	if setari.get("wpa_conf"):
		rel = setari["wpa_conf"].replace("\\", "/").lstrip("/")
		if ".." not in rel.split("/"):
			alese.append(os.path.join(rad, *rel.split("/")))
	pe_nume = dict((os.path.basename(c), c) for c in loc.get("wpa") or ())
	for n in ("wpa_supplicant.%s.conf" % placa, "wpa_supplicant.conf"):
		if n in pe_nume:
			alese.append(pe_nume[n])
	alese += list(loc.get("wpa") or ())
	for c in alese:
		if c in (loc.get("wpa") or ()) or _fisier_bun(c, MAX_FISIER_RETEA):
			return c
	return None


def citeste_retea(loc):
	"""Planul rețelei din copie (loc = locuri_extra(...)["retea"]): {"cablu": {"dhcp", "ip", "masca", "poarta"} sau
	None, "wifi": {"dhcp", "ip", "masca", "poarta", "retea": ParolaWifi, "nume": text} sau None, "dns": [ip],
	"note": [motive scurte]}. None fără fișierul interfaces."""
	if not loc:
		return None
	text = _citeste_text(loc.get("interfaces"))
	if text is None:
		return None
	placi = citeste_interfaces(text)
	plan = {"cablu": None, "wifi": None, "dns": [], "note": []}
	for nume in sorted(placi):
		p = placi[nume]
		if not p.get("auto") or p.get("metoda") not in ("dhcp", "static"):
			continue
		if not p["dhcp"] and not (p["ip"] and p["masca"]):
			continue
		date = {"dhcp": p["dhcp"], "ip": p["ip"] or [0, 0, 0, 0], "masca": p["masca"] or [255, 255, 255, 0],
			"poarta": p["poarta"], "placa_copie": nume}
		if este_wifi(nume):
			if plan["wifi"] is not None:
				continue
			cale = _wpa_pentru(nume, p, loc)
			retea, motiv = retea_wifi_din_conf(_citeste_text(cale) or "") if cale else (None, "fara")
			if retea is None:
				plan["note"].append("wifi-" + motiv)
				continue
			from Components import WlanTools
			date["retea"] = retea
			date["nume"] = WlanTools.ssidName(retea.ssid)
			plan["wifi"] = date
		elif plan["cablu"] is None:
			plan["cablu"] = date
		if not p["dhcp"] and p["dns"] and not plan["dns"]:
			plan["dns"] = p["dns"][:3]
	if not plan["dns"]:
		statice = [d for d in (plan["cablu"], plan["wifi"]) if d and not d["dhcp"]]
		if statice:
			plan["dns"] = _dns_din_resolv(_citeste_text(loc.get("resolv")) if loc.get("resolv") else "")
	if plan["cablu"] is None and plan["wifi"] is None:
		return None if not plan["note"] else plan
	return plan


def text_ip(ip):
	return ".".join(str(int(x)) for x in ip) if ip else ""


def descriere_retea(plan):
	"""Descrie interfețele importate, numele rețelei și adresarea DHCP sau fixă, fără parole."""
	rez = []
	for cheie, eticheta in (("cablu", _("cablu")), ("wifi", "Wi-Fi")):
		d = (plan or {}).get(cheie)
		if not d:
			continue
		fel = _("adresă automată (DHCP)") if d["dhcp"] else _("adresă fixă %s") % text_ip(d["ip"])
		if cheie == "wifi":
			rez.append("%s „%s”: %s" % (eticheta, d.get("nume", ""), fel))
		else:
			rez.append("%s: %s" % (eticheta, fel))
	return rez
