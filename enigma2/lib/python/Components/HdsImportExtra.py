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
#     condiționat, potrivite cu sursele de pachete ale receptorului (potriveste_pachete);
#   - rețeaua: felul conexiunii pe cablu și pe Wi-Fi și rețeaua Wi-Fi, din etc/network/interfaces,
#     etc/wpa_supplicant*.conf și etc/resolv.conf ale copiei (citeste_retea). Parola rețelei stă numai în obiectul
#     ParolaWifi (repr fără ea), nu intră în texte, în jurnal, în starea comună sau în web. Aplicarea e în
#     Components/HdsImportRetea.py.

import os
import re
import shutil
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
# înlocui canalele aduse, driverele sunt ale imaginii; modulele de acces condiționat niciodată
CATEGORII_NEOFERITE = ("skins", "settings", "drivers")
TIPAR_CUVANT_ACCES = re.compile(r"cams?d?[0-9]*$")


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
	"""Câmpurile sursei pentru căutare: {"retea": bool, "picon": bool, "pachete": bool}. La o arhivă `membri_extra` sunt
	căile de sub rădăcina copiei găsite în ea (fel_extra)."""
	if fel == "arhiva":
		feluri = set(fel_extra(r) for r in membri_extra)
		loc = locuri_extra(cale, fel, cale_arhiva)
		return {"retea": REL_INTERFACES in membri_extra, "picon": False,
			"pachete": "pachete" in feluri or bool(loc["pachete"])}
	loc = locuri_extra(cale, fel)
	return {"retea": loc["retea"] is not None, "picon": loc["picon"] is not None, "pachete": bool(loc["pachete"])}


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
	"""Texte scurte despre ce aduce planul, fără parolă: ["cablu: DHCP", "Wi-Fi „Acasa”: 192.168.1.50"]."""
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
