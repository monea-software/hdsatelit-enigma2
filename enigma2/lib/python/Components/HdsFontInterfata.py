# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFontInterfata: fontul interfetei, ales dintre fonturile livrate cu imaginea (toate sub SIL Open Font License 1.1,
# neschimbate, cu licenta langa ele in /usr/share/fonts). Aceeasi logica pentru ecranul de pe televizor
# (Screens/HdsFontInterfata.py) si pentru pagina web /font-interfata (HdsWebControl/font_interfata_web.py).
#
# Cum se schimba fontul: skinul inregistreaza la pornire numele HdsRegular, HdsBold, HdsCond (si Regular, Bold,
# RegularHD, Fixed) cu Open Sans. lib/gdi/font.cpp pune fiecare addFont in capul listei si cauta numele de la cap, deci
# un addFont nou cu acelasi nume castiga pentru tot ce se deseneaza dupa el: alegerea se aplica pe loc (ecranele
# deschise de acum) si la fiecare pornire, dupa skin (Screens/FontSetup.aplicaScalareFonturi, din
# Components/SetupDevices). O familie fara varianta ingusta lasa HdsCond pe Open Sans Condensed.
# Niciun fisier nu ajunge la addFont fara verificarea din Components/HdsFonturiGoogle.verificaFisierFont (un fisier
# care nu e font face eFatal in font.cpp).
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau addFont, verificarea si config.
import os

DIR_FONTURI = "/usr/share/fonts"
DIR_SKIN = "/usr/share/enigma2/HDSatelit/fonts"
IMPLICIT = "opensans"

# rolul fisierului -> numele din skin pe care le ia
NUME_SKIN = {
	"regular": ("HdsRegular", "Regular", "RegularHD"),
	"bold": ("HdsBold", "Bold"),
	"cond": ("HdsCond", "Fixed"),
}
ROLURI = ("regular", "bold", "cond")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


# Familiile, in ordinea din lista. `limbi` = limbile meniului ale caror litere le au TOATE fisierele familiei
# (unelte/acoperire_limbi.py, cu fontTools; proba test_ecrane_vechi_2_fonturi.py le verifica pe fisierele livrate).
# Araba se scrie oricum cu fontul de rezerva al skinului (HdsScripturi).
FAMILII = (
	{"id": "opensans", "nume": "Open Sans", "autor": "The Open Sans Project Authors",
	 "fisiere": {"regular": "HdsRegular.ttf", "bold": "HdsBold.ttf", "cond": "HdsCond.ttf"}, "licenta": "OFL.txt",
	 "descriere": N_("Fontul din fabrică: rotund și liniștit, cu toate literele imaginii, latine, chirilice și grecești."),
	 "limbi": "ca cs da de el en es et fi fr fy hr hu is it lt lv nl no pl pt ro ru sk sl sr sv tr uk"},
	{"id": "atkinson", "nume": "Atkinson Hyperlegible", "autor": "Braille Institute of America",
	 "fisiere": {"regular": "AtkinsonHyperlegible-Regular.ttf", "bold": "AtkinsonHyperlegible-Bold.ttf", "cond": None},
	 "licenta": "AtkinsonHyperlegible-OFL.txt",
	 "descriere": N_("Desenat ca literele să nu se încurce (I, l și 1, O și 0): cel mai ușor de citit de departe. "
		"Numai litere latine; textele mici rămân cu Open Sans îngust."),
	 "limbi": "ca cs da de en es et fi fr fy hr hu is it lt lv nl no pl pt ro sl sv"},
	{"id": "barlow", "nume": "Barlow", "autor": "The Barlow Project Authors",
	 "fisiere": {"regular": "Barlow-Regular.ttf", "bold": "Barlow-Bold.ttf", "cond": "BarlowSemiCondensed-Regular.ttf"},
	 "licenta": "Barlow-OFL.txt",
	 "descriere": N_("Litere înguste, cu colțuri rotunjite, ca pe indicatoarele rutiere: încape mult text pe un rând. "
		"Numai litere latine."),
	 "limbi": "ca cs da de en es et fi fr fy hr hu is it lt lv nl no pl pt ro sk sl sv tr"},
	{"id": "ptsans", "nume": "PT Sans", "autor": "ParaType",
	 "fisiere": {"regular": "PT_Sans-Web-Regular.ttf", "bold": "PT_Sans-Web-Bold.ttf", "cond": "PT_Sans-Narrow-Web-Regular.ttf"},
	 "licenta": "PT_Sans-OFL.txt",
	 "descriere": N_("Litere calde, ușor de citit, cu toate literele chirilice: potrivit și pentru meniurile în rusă, "
		"ucraineană și sârbă."),
	 "limbi": "ca cs da de en es et fi fr fy hr hu is it lt lv nl no pl pt ro ru sk sl sr sv tr uk"},
)
LIMBI_FARA_LITERE_PROPRII = ("ar",)


def familie(fid):
	for f in FAMILII:
		if f["id"] == fid:
			return f
	return None


def cale(fid, rol, dir_fonturi=DIR_FONTURI, dir_skin=DIR_SKIN):
	"""Fisierul familiei pentru rol; None cand familia nu are rolul (atunci ramane Open Sans). Open Sans se ia din
	dosarul skinului (cel inregistrat la pornire), altfel din /usr/share/fonts."""
	f = familie(fid)
	if f is None:
		return None
	nume = f["fisiere"].get(rol)
	if not nume:
		return None
	if fid == IMPLICIT:
		p = os.path.join(dir_skin, nume)
		if os.path.isfile(p):
			return p
	return os.path.join(dir_fonturi, nume)


def marime(fid, dir_fonturi=DIR_FONTURI, dir_skin=DIR_SKIN):
	"""Octetii fisierelor familiei de pe disc (0 cand lipsesc)."""
	total = 0
	for rol in ROLURI:
		p = cale(fid, rol, dir_fonturi, dir_skin)
		if p and os.path.isfile(p):
			total += os.path.getsize(p)
	return total


def _verificare():
	from Components.HdsFonturiGoogle import verificaFisierFont
	return verificaFisierFont


def disponibil(fid, dir_fonturi=DIR_FONTURI, dir_skin=DIR_SKIN, verifica=None):
	"""(True, "") daca fiecare fisier al familiei exista si e un font bun; altfel (False, motivul)."""
	f = familie(fid)
	if f is None:
		return False, N_("Fontul acesta nu există în imagine.")
	verifica = verifica or _verificare()
	for rol in ROLURI:
		p = cale(fid, rol, dir_fonturi, dir_skin)
		if p is None:
			continue
		if not os.path.isfile(p):
			return False, N_("Lipsește un fișier al fontului.")
		r = verifica(p)
		if not r.get("bun"):
			return False, N_("Un fișier al fontului e stricat.")
	return True, ""


def codLimba(config=None):
	"""Codul limbii meniului (ro din ro_RO)."""
	try:
		if config is None:
			from Components.config import config
		return str(config.osd.language.value).split("_")[0].lower()
	except Exception:
		return "ro"


def potrivit(fid, limba):
	"""True daca familia are toate literele limbii meniului."""
	f = familie(fid)
	if f is None:
		return False
	return limba in LIMBI_FARA_LITERE_PROPRII or limba in f["limbi"].split()


def initConfig(config=None):
	if config is None:
		from Components.config import config
	if "osd" not in config.content.items:
		from Components.config import ConfigSubsection
		config.osd = ConfigSubsection()
	if "hds_font_interfata" not in config.osd.content.items:
		from Components.config import ConfigSelection
		config.osd.hds_font_interfata = ConfigSelection(default=IMPLICIT, choices=[(f["id"], f["nume"]) for f in FAMILII])
	return config.osd.hds_font_interfata


def ales(config=None):
	v = initConfig(config).value
	return v if familie(v) is not None else IMPLICIT


def _addFont():
	from enigma import addFont
	return addFont


def inregistreaza(fid, addFont=None, verifica=None, dir_fonturi=DIR_FONTURI, dir_skin=DIR_SKIN):
	"""Da numele skinului (HdsRegular, HdsBold, HdsCond...) fisierelor familiei. Un rol fara fisier in familie ia
	Open Sans (ca la trecerea inapoi de la un font cu varianta ingusta la unul fara). (True, "") sau (False, motivul)."""
	bun, motiv = disponibil(fid, dir_fonturi, dir_skin, verifica)
	if not bun:
		return False, motiv
	addFont = addFont or _addFont()
	for rol in ROLURI:
		p = cale(fid, rol, dir_fonturi, dir_skin) or cale(IMPLICIT, rol, dir_fonturi, dir_skin)
		if p is None or not os.path.isfile(p):
			continue
		for nume in NUME_SKIN[rol]:
			addFont(p, nume, 100, False)
	print("[HdsFontInterfata] fontul interfetei: %s" % fid)
	return True, ""


_proba = {}


def aliasProba(fid, rol, addFont=None, verifica=None, dir_fonturi=DIR_FONTURI, dir_skin=DIR_SKIN):
	"""Un nume numai pentru proba (HdsProba_<familie>_<rol>), inregistrat o singura data, ca proba sa arate familia
	fara sa schimbe interfata. Un rol lipsa ia Open Sans; None daca fisierul nu e bun."""
	cheie = (fid, rol)
	if cheie in _proba:
		return _proba[cheie]
	p = cale(fid, rol, dir_fonturi, dir_skin) or cale(IMPLICIT, rol, dir_fonturi, dir_skin)
	verifica = verifica or _verificare()
	if p is None or not os.path.isfile(p) or not verifica(p).get("bun"):
		_proba[cheie] = None
		return None
	nume = "HdsProba_%s_%s" % (fid, rol)
	(addFont or _addFont())(p, nume, 100, False)
	_proba[cheie] = nume
	return nume


def aplicaLaPornire(config=None, addFont=None):
	"""Dupa skin: fontul ales, daca nu e cel din fabrica (acela l-a pus skinul)."""
	fid = ales(config)
	if fid == IMPLICIT:
		return False
	bun, motiv = inregistreaza(fid, addFont)
	if not bun:
		print("[HdsFontInterfata] %s nu se poate folosi (%s): ramane Open Sans" % (fid, motiv))
	return bun


def seteaza(fid, config=None, addFont=None, verifica=None, configfile=None, limba=None, dir_fonturi=DIR_FONTURI,
		dir_skin=DIR_SKIN):
	"""Alege fontul interfetei: verificat, salvat si pus pe loc. (True, numele) sau (False, motivul)."""
	f = familie(fid)
	if f is None:
		return False, N_("Fontul acesta nu există în imagine.")
	limba = limba or codLimba(config)
	if not potrivit(fid, limba):
		return False, N_("Fontul acesta nu are toate literele limbii meniului.")
	bun, motiv = inregistreaza(fid, addFont, verifica, dir_fonturi, dir_skin)
	if not bun:
		return False, motiv
	el = initConfig(config)
	el.value = fid
	el.save()
	if configfile is None:
		try:
			from Components.config import configfile
		except ImportError:
			configfile = None
	if configfile is not None:
		configfile.save()
	return True, f["nume"]


def textMarime(octeti):
	if octeti >= 1024 * 1024:
		return ("%.1f MB" % (octeti / 1048576.0)).replace(".", ",")
	return "%d KB" % max(1, int(round(octeti / 1024.0)))


def textLitere(fid, traducere=None):
	t = traducere or (lambda s: s)
	limbi = familie(fid)["limbi"].split()
	parti = [t(N_("latine"))]
	if "ru" in limbi:
		parti.append(t(N_("chirilice")))
	if "el" in limbi:
		parti.append(t(N_("grecești")))
	return ", ".join(parti)


def stare(config=None, traducere=None, limba=None, dir_fonturi=DIR_FONTURI, dir_skin=DIR_SKIN):
	"""Pentru pagina web: familiile, alegerea de acum si limba meniului."""
	t = traducere or (lambda s: s)
	limba = limba or codLimba(config)
	acum = ales(config)
	familii = []
	for f in FAMILII:
		familii.append({
			"id": f["id"], "nume": f["nume"], "autor": f["autor"], "descriere": t(f["descriere"]),
			"litere": textLitere(f["id"], t), "marime": textMarime(marime(f["id"], dir_fonturi, dir_skin)),
			"potrivit": potrivit(f["id"], limba), "ales": f["id"] == acum,
			"ingust": bool(f["fisiere"].get("cond")), "licenta": "SIL Open Font License 1.1",
		})
	return {"ales": acum, "limba": limba, "familii": familii}
