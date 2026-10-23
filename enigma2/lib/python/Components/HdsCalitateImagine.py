# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCalitateImagine.py: „Calitatea imaginii” si „Ieșire HDR”. O singura logica pentru ecranul de pe televizor
# (Screens/HdsCalitateImagine.py), pagina web (HdsWebControl/calitate_imagine_web.py) si probele de pe PC.
#
# BLOCUL DE CALITATE AL PLACII (HiSilicon, /proc/msp/pq). Driverul primeste comenzi text, cate una pe scriere, si arata
# starea la citire. Comenzile folosite aici, numai din lista alba (comandaPermisa):
#   bright|contrast|hue|satu <0..100>            culorile (luminozitate, contrast, nuanta, saturatie); 50 = din fabrica;
#                                                schimba si stratul grafic, adica si meniurile
#   sharp|tnr|snr|db|dm|dci|acm <0..100>         taria unui modul (dci = contrastul adaptiv, acm = culorile)
#   sharp|tnr|snr|db|dm|dci|acm enable|disable   modulul pornit sau oprit (alegerea e a tuturor canalelor)
#   sharp|tnr|snr|db|dci|acm demoon|demooff, all demooff, demomode fixr|fixl   comparatia pe jumatate de ecran
# Al doilea cuvant care nu e enable, disable, demoon sau demooff e citit de driver ca numar („tnr off” pune taria 0),
# iar scrierea intoarce succes si pentru o comanda respinsa: de aceea lista alba si citirea inapoi dupa scriere.
# Driverul nu pastreaza nimic peste o repornire (porneste cu 50 si cu modulele pornite), iar tariile sunt aceleasi
# pentru toate canalele: profilurile se scriu la fiecare schimbare a profilului (diferenta fata de ce e in driver).
# Placa alege singura, dupa latimea sursei, ce module lucreaza: pe SD toate; pe HD blocurile, contururile si zgomotul
# din cadru raman oprite oricat le-ai porni; pe 4K zgomotul in timp e nedovedit. Un modul oprit de placa se citeste
# „off” desi alegerea e „pornit”: citirea inapoi compara pornit/oprit numai la modulele pe care placa le lasa.
#
# PROFILURILE: clasa canalului dupa latimea video (<= 720 SD, <= 1920 HD, mai mare 4K, aceleasi praguri ca driverul) x
# felul imaginii trimise la televizor (SDR, HDR10, HLG: iesirea HDR aleasa, iar la „Automat” gama canalului). Profilul
# se alege la evVideoSizeChanged si evVideoGammaChanged (gama vine putin dupa) si se scrie numai cand se schimba. Fara
# imagine (radio) nu se scrie nimic. Cu „Reglajele după canal” pe Nu se scriu valorile din fabrica.
#
# IESIREA HDR (/proc/stb/video/hdmi_hdrtype): textul il citeste programul platformei la fiecare pornire de canal
# (auto = dupa canal, hdr10, hlg, none = SDR; gol sau alt text = SDR). Se scrie la pornire si la fiecare pornire de
# canal
# daca s-a schimbat (alt televizor, mod video SD), iar alegerea noua reporneste canalul si se intreaba pe televizor.
# Numai pe receptoarele unde fisierul exista fara lista de alegeri (pe celelalte, randul „HDR type” e in Setari > Video)
# si numai alegerile pe care televizorul le declara (/proc/msp/disp1, apoi /proc/msp/hdmi0_sink). hdmi_colorimetry nu se
# atinge (e a „Culorilor pe HDMI”, Components/VideoOutput.py).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il incarca fara receptor.

import os
import re
import time

CALE_PQ = "/proc/msp/pq"
CALE_HDR = "/proc/stb/video/hdmi_hdrtype"
CALE_HDR_ALEGERI = "/proc/stb/video/hdmi_hdrtype_choices"
CALE_DISP = "/proc/msp/disp1"
CALE_SINK = "/proc/msp/hdmi0_sink"
CALE_MOD_VIDEO = "/proc/stb/video/videomode"

MAX_COMANDA = 250          # driverul primeste sub 256 de octeti
FABRICA = 50
PAS = 5
VALORI = tuple(range(0, 101, PAS))
SECUNDE_COMPARATIE = 60    # comparatia pornita din web se opreste singura
SECUNDE_INCERCARE = 180    # valorile incercate din web, nepastrate, revin singure
SECUNDE_INTREBARE = 20     # intrebarea dupa o iesire HDR noua (ca in Setari > Video)

CULOARE = "culoare"
MODUL = "modul"


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# (cheia setarii, comanda driverului, sectiunea din /proc/msp/pq, fel, eticheta, descrierea)
REGLAJE = (
	("luminozitate", "bright", "brightness", CULOARE, N_("Luminozitate"),
		N_("Cât de luminoasă e imaginea. Schimbă și meniurile.")),
	("contrast", "contrast", "contrast", CULOARE, N_("Contrast"),
		N_("Diferența dintre părțile întunecate și cele luminoase. Schimbă și meniurile.")),
	("saturatie", "satu", "saturation", CULOARE, N_("Saturație"),
		N_("Cât de puternice sunt culorile. Schimbă și meniurile.")),
	("nuanta", "hue", "hue", CULOARE, N_("Nuanță"),
		N_("Mută culorile spre verde sau spre roșu, pentru fețe naturale. Schimbă și meniurile.")),
	("claritate", "sharp", "sharp", MODUL, N_("Claritate"),
		N_("Contururi mai precise după mărirea imaginii. Prea mult face margini albe în jurul obiectelor.")),
	("zgomot", "tnr", "tnr", MODUL, N_("Reducerea zgomotului"),
		N_("Liniștește purecii din imagine de la un cadru la altul. Prea mult lasă urme în spatele mișcării.")),
	("zgomot_cadru", "snr", "snr", MODUL, N_("Zgomotul din cadru"),
		N_("Netezește zonele plate ale fiecărui cadru. Prea mult face fețele și iarba ca de plastic.")),
	("blocuri", "db", "db", MODUL, N_("Pătrățelele compresiei"),
		N_("Șterge marginile pătrățelelor care apar pe canalele cu debit mic.")),
	("contururi", "dm", "dm", MODUL, N_("Zgomotul de pe contururi"),
		N_("Șterge tremurul din jurul literelor și al marginilor ascuțite.")),
	("contrast_adaptiv", "dci", "acc", MODUL, N_("Contrast adaptiv"),
		N_("Receptorul potrivește singur contrastul după fiecare scenă.")),
	("culori", "acm", "acm", MODUL, N_("Îmbunătățirea culorilor"),
		N_("Culori mai vii și pielea mai naturală.")),
)
CHEI = tuple(r[0] for r in REGLAJE)
REGLAJ = dict((r[0], r) for r in REGLAJE)
CULORI = tuple(r[0] for r in REGLAJE if r[3] == CULOARE)
MODULE = tuple(r[0] for r in REGLAJE if r[3] == MODUL)
# modulele care au comparatia pe jumatate de ecran in driver (contururile si culorile de baza nu au)
CU_COMPARATIE = ("claritate", "zgomot", "zgomot_cadru", "blocuri", "contrast_adaptiv", "culori")

CLASE = (("sd", N_("SD")), ("hd", N_("HD")), ("uhd", N_("4K")))
DINAMICI = (("sdr", "SDR"), ("hdr10", "HDR10"), ("hlg", "HLG"))
PROFILURI = tuple("%s_%s" % (c, d) for c, n in CLASE for d, m in DINAMICI)
# ce reglaje lucreaza pe fiecare clasa (citit pe receptor: pe HD placa tine db, dm si snr oprite)
PE_CLASA = {
	"sd": CHEI,
	"hd": CULORI + ("claritate", "zgomot", "contrast_adaptiv", "culori"),
	"uhd": CULORI + ("claritate", "contrast_adaptiv", "culori"),
}

IESIRI_HDR = (
	("auto", N_("Automat, după canal")),
	("hdr10", N_("Mereu HDR10")),
	("hlg", N_("Mereu HLG")),
	("none", N_("Oprită (SDR)")),
)
HDR_IMPLICIT = "auto"
# moduri video in care placa nu trimite HDR (afisajele SD)
MODURI_SD = ("576i", "576p", "480i", "480p", "pal", "ntsc")

_RX_COMANDA = re.compile(
	r"(?:(?:bright|contrast|hue|satu) (?:\d|[1-9]\d|100)"
	r"|(?:sharp|tnr|snr|db|dm|dci|acm) (?:\d|[1-9]\d|100|enable|disable)"
	r"|(?:sharp|tnr|snr|db|dci|acm|all) (?:demoon|demooff)"
	r"|demomode (?:fixr|fixl))")


def comandaPermisa(comanda):
	"""True numai pentru comenzile din lista alba (vezi capul fisierului), scrise exact."""
	return bool(comanda) and len(comanda) < MAX_COMANDA and _RX_COMANDA.fullmatch(comanda) is not None


def _jurnal(text):
	print("[HdsCalitateImagine] %s" % text)


def _citesteText(cale):
	try:
		with open(cale, "rb") as f:
			return f.read().decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def _scrieText(cale, text):
	try:
		with open(cale, "wb") as f:
			f.write(text.encode("ascii"))
		return True
	except (IOError, OSError, UnicodeError) as e:
		_jurnal("scrierea %r in %s a esuat: %s" % (text, cale, e))
		return False


# ---------------------------------------------------------------- citirea textelor driverului

def _camp(text, cheie):
	m = re.search(r"(?:^|\s)%s\s*:\s*(\S+)" % re.escape(cheie), text or "", re.M)
	return m.group(1) if m else None


def clasaDupaLatime(latime):
	"""sd / hd / uhd dupa latimea imaginii (pragurile driverului), None fara imagine."""
	try:
		latime = int(latime)
	except (TypeError, ValueError):
		return None
	if latime <= 0:
		return None
	if latime <= 720:
		return "sd"
	if latime <= 1920:
		return "hd"
	return "uhd"


def _clasaSursei(text):
	"""clasa din randul „Source : HD(1920*1080)” al driverului (latimea dintre paranteze), sau None"""
	m = re.search(r"Source\s*:\s*\w*\((\d+)\s*\*\s*(\d+)\)", text or "")
	return clasaDupaLatime(m.group(1)) if m else None


def citestePq(text):
	"""Starea din /proc/msp/pq: {"culori": {cheie: n}, "module": {cheie: {"pornit", "tarie", "demo"}}, "sursa": clasa},
	numai ce se gaseste in text; None fara text sau fara sectiunea algoritmilor."""
	if not text or "Algorithm Information" not in text:
		return None
	rez = {"culori": {}, "module": {}, "sursa": _clasaSursei(text)}
	for cheie, comanda, sectiune, fel, eticheta, descriere in REGLAJE:
		if fel == CULOARE:
			m = re.search(r"HD %s\s*:\s*(\d+)" % sectiune, text)
			if m:
				rez["culori"][cheie] = int(m.group(1))
			continue
		m = re.search(r"-{3,}\s*%s\s*-{3,}(.*?)(?=-{3,}\s*\w[\w ]*-{3,}|={5,}|$)" % re.escape(sectiune), text, re.S)
		if not m:
			continue
		bloc = m.group(1)
		stare = {}
		v = _camp(bloc, "module")
		if v is not None:
			stare["pornit"] = v.lower() == "on"
		v = _camp(bloc, "strength")
		if v is not None and v.isdigit():
			stare["tarie"] = int(v)
		v = _camp(bloc, "demo")
		if v is not None:
			stare["demo"] = v.lower() == "on"
		rez["module"][cheie] = stare
	return rez


def televizorHdr(text_disp, text_sink):
	"""Ce declara televizorul: {"stiut", "hdr10", "hlg"}. Intai /proc/msp/disp1 (bHdr10Support, bHlgSupport), apoi
	sectiunea HdrCap din /proc/msp/hdmi0_sink; stiut = False fara un EDID valid."""
	rez = {"stiut": False, "hdr10": False, "hlg": False}
	h10 = _camp(text_disp, "bHdr10Support")
	hlg = _camp(text_disp, "bHlgSupport")
	if text_sink and (_camp(text_sink, "CapIsValid") or "").upper() not in ("YES", "Y", "TRUE", "1"):
		return rez
	if h10 is not None or hlg is not None:
		rez.update(stiut=True, hdr10=(h10 or "").upper() == "Y", hlg=(hlg or "").upper() == "Y")
		return rez
	s1 = _camp(text_sink, "HdrEotfSt2084")
	s2 = _camp(text_sink, "HdrEotfHLG")
	if s1 is not None or s2 is not None:
		rez.update(stiut=True, hdr10=(s1 or "").upper() == "YES", hlg=(s2 or "").upper() == "YES")
	return rez


def alegeriHdr(tv):
	"""Valorile „Ieșire HDR” pe care televizorul le primeste: Automat numai cu HDR10 si HLG (programul platformei
	verifica doar HDR10, apoi trimite HLG pentru un canal HLG); „Oprită” mereu."""
	rez = []
	if tv.get("hdr10") and tv.get("hlg"):
		rez.append("auto")
	if tv.get("hdr10"):
		rez.append("hdr10")
	if tv.get("hlg"):
		rez.append("hlg")
	rez.append("none")
	return rez


def hdrDeScris(alegere, tv, mod_video):
	"""Textul scris in hdmi_hdrtype: none pe modurile SD; alegerea, cand televizorul o primeste sau nu se stie ce
	declara (televizor stins: ramane alegerea facuta pentru el); altfel none."""
	if (mod_video or "").strip() in MODURI_SD:
		return "none"
	if not tv.get("stiut"):
		return alegere if alegere in dict(IESIRI_HDR) else "none"
	return alegere if alegere in alegeriHdr(tv) else "none"


def dinamica(scris, gama):
	"""Felul imaginii trimise la televizor: dupa textul scris in hdmi_hdrtype (None = receptor fara aceasta iesire,
	atunci dupa canal) si gama canalului (0 SDR, 1 HDR, 2 HDR10, 3 HLG)."""
	if scris == "hdr10":
		return "hdr10"
	if scris == "hlg":
		return "hlg"
	if scris == "none":
		return "sdr"
	if gama in (1, 2):
		return "hdr10"
	if gama == 3:
		return "hlg"
	return "sdr"


def numeProfil(profil):
	"""„HD, SDR”, tradus."""
	clasa, din = profil.split("_", 1)
	return "%s, %s" % (_t(dict(CLASE)[clasa]), dict(DINAMICI)[din])


def numeIesireHdr(valoare):
	return _t(dict(IESIRI_HDR).get(valoare, valoare))


def textValoare(cheie, valoare):
	"""„Oprit” pentru 0 la un modul, altfel numarul."""
	if REGLAJ[cheie][3] == MODUL and int(valoare) == 0:
		return _t("Oprit")
	return "%d" % int(valoare)


def comenziPentru(dorit, avut):
	"""Comenzile care duc driverul de la `avut` (starea stiuta: {"culori": {}, "module": {cheie: {"pornit", "tarie"}}},
	sau None) la `dorit` ({cheie: 0..100}; la module 0 = oprit, taria ramane). Numai ce difera, in ordinea REGLAJE."""
	avut = avut or {"culori": {}, "module": {}}
	comenzi = []
	for cheie, comanda, sectiune, fel, eticheta, descriere in REGLAJE:
		if cheie not in dorit:
			continue
		v = max(0, min(100, int(dorit[cheie])))
		if fel == CULOARE:
			if avut["culori"].get(cheie) != v:
				comenzi.append("%s %d" % (comanda, v))
			continue
		a = avut["module"].get(cheie) or {}
		if v == 0:
			if a.get("pornit") is not False:
				comenzi.append("%s disable" % comanda)
			continue
		if a.get("pornit") is not True:
			comenzi.append("%s enable" % comanda)
		if a.get("tarie") != v:
			comenzi.append("%s %d" % (comanda, v))
	return comenzi


def _aplicaPeStare(stare, comanda):
	"""Starea stiuta dupa o comanda scrisa (pentru `avut` si pentru driverul simulat)."""
	cuv = comanda.split()
	inv = dict((r[1], r[0]) for r in REGLAJE)
	if cuv[0] in ("bright", "contrast", "hue", "satu"):
		stare["culori"][inv[cuv[0]]] = int(cuv[1])
		return
	if cuv[0] in inv:
		m = stare["module"].setdefault(inv[cuv[0]], {})
		if cuv[1] == "enable":
			m["pornit"] = True
		elif cuv[1] == "disable":
			m["pornit"] = False
		elif cuv[1] == "demoon":
			m["demo"] = True
		elif cuv[1] == "demooff":
			m["demo"] = False
		else:
			m["tarie"] = int(cuv[1])
		return
	if cuv[0] == "all" and cuv[1] == "demooff":
		for m in stare["module"].values():
			m["demo"] = False


def stareFabrica():
	return {"culori": dict((k, FABRICA) for k in CULORI),
		"module": dict((k, {"pornit": True, "tarie": FABRICA, "demo": False}) for k in MODULE)}


def valoriFabrica(clasa=None):
	chei = PE_CLASA.get(clasa, CHEI)
	return dict((k, FABRICA) for k in chei)


# ---------------------------------------------------------------- driverul (adevarat sau simulat)

class Driver(object):
	"""/proc/msp/pq: citeste() textul, scrie(comanda) o comanda (deschis, scris, inchis, ca echo)."""

	def __init__(self, cale=None):
		self.cale = cale or CALE_PQ

	def citeste(self):
		return _citesteText(self.cale)

	def scrie(self, comanda):
		return _scrieText(self.cale, comanda + "\n")


class DriverSimulat(object):
	"""Emulatorul de pe PC: comenzile se tin minte si se arata in acelasi format ca driverul, ca ecranul si pagina sa
	poata fi probate; nimic nu ajunge la o placa."""

	def __init__(self, latime=1920, inaltime=1080):
		self.stare = stareFabrica()
		self.latime = latime
		self.inaltime = inaltime
		self.scrise = []

	def scrie(self, comanda):
		self.scrise.append(comanda)
		_aplicaPeStare(self.stare, comanda)
		_jurnal("simulare: %s" % comanda)
		return True

	def citeste(self):
		clasa = clasaDupaLatime(self.latime)
		nume = {"sd": "SD", "hd": "HD", "uhd": "UHD"}.get(clasa, "HD")
		r = ["=== Picture Information ==="]
		for cheie, comanda, sectiune, fel, eticheta, descriere in REGLAJE:
			if fel == CULOARE:
				r.append("HD %-16s: %d" % (sectiune, self.stare["culori"][cheie]))
		r.append("Source              : %s(%d*%d)" % (nume, self.latime, self.inaltime))
		r.append("=== Algorithm Information ===")
		for cheie, comanda, sectiune, fel, eticheta, descriere in REGLAJE:
			if fel != MODUL:
				continue
			m = self.stare["module"][cheie]
			pornit = m.get("pornit") and cheie in PE_CLASA.get(clasa, CHEI)
			r.append("------------------------------------ %s ------------------------------------" % sectiune)
			r.append("bind to             : vdp                 module              : %s" % ("on" if pornit else "off"))
			r.append("strength            : %d                  demo                : %s" % (m.get("tarie", FABRICA),
				"on" if m.get("demo") else "off"))
		r.append("=" * 40)
		return "\n".join(r) + "\n"


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_calitate: pornit, iesire_hdr si cate o alegere pentru fiecare reglaj al fiecarui profil
	(<profil>_<reglaj>, numai reglajele clasei lui). Etichetele raman netraduse aici (configul se face inaintea limbii);
	ConfigSelection si pagina web le traduc la afisare."""
	from Components.config import config
	if "hds_calitate" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigSelection, ConfigYesNo
	config.hds_calitate = ConfigSubsection()
	config.hds_calitate.pornit = ConfigYesNo(default=True)
	config.hds_calitate.iesire_hdr = ConfigSelection(default=HDR_IMPLICIT, choices=list(IESIRI_HDR))
	for profil in PROFILURI:
		clasa = profil.split("_")[0]
		for cheie in PE_CLASA[clasa]:
			alegeri = [(str(v), N_("Oprit") if (v == 0 and REGLAJ[cheie][3] == MODUL) else str(v)) for v in VALORI]
			setattr(config.hds_calitate, "%s_%s" % (profil, cheie),
				ConfigSelection(default=str(FABRICA), choices=alegeri))


def element(profil, cheie):
	"""Setarea config a unui reglaj din profil, sau None (reglaj care nu e al clasei)."""
	from Components.config import config
	return config.hds_calitate.content.items.get("%s_%s" % (profil, cheie))


def elementeProfil(profil):
	clasa = profil.split("_")[0]
	return [(cheie, element(profil, cheie)) for cheie in PE_CLASA[clasa]]


def toateElementele():
	from Components.config import config
	rez = [config.hds_calitate.pornit, config.hds_calitate.iesire_hdr]
	for profil in PROFILURI:
		rez += [e for k, e in elementeProfil(profil)]
	return rez


def valoriProfil(profil, salvate=False):
	"""{cheie: n} ale profilului: valorile de acum ale setarilor (cele din ecran, chiar nesalvate) sau, cu salvate=True,
	cele salvate."""
	rez = {}
	for cheie, e in elementeProfil(profil):
		if salvate:
			v = e.saved_value if e.saved_value is not None else e.default
		else:
			v = e.value
		try:
			rez[cheie] = int(v)
		except (TypeError, ValueError):
			rez[cheie] = FABRICA
	return rez


# ---------------------------------------------------------------- starea si aplicarea

class Calitate(object):
	"""Starea pentru un enigma2 pornit. driver = Driver/DriverSimulat (probele dau altul); citeste/scrie = functiile
	pentru fisierele HDR (probele dau altele); ceas = time.monotonic; timer = fabrica de eTimer."""

	def __init__(self, driver=None, simulare=False, citeste=None, scrie=None, ceas=None, timer=None):
		self.simulare = simulare
		self.driver = driver if driver is not None else (DriverSimulat() if simulare else Driver())
		self.citesteFisier = citeste or _citesteText
		self.scrieFisier = scrie or _scrieText
		self.ceas = ceas or time.monotonic
		self.faTimer = timer
		self.avut = None            # starea driverului stiuta (citita la pornire, apoi dupa fiecare scriere)
		self.profilScris = None     # profilul scris ultima data ("fabrica" cu reglajele oprite)
		self.incercat = False       # in driver sunt valori incercate, nesalvate
		self.comparatie = None      # cheia reglajului cu comparatia pornita
		self.hdrScris = None        # ultimul text scris in hdmi_hdrtype
		self.latime = 0
		self.inaltime = 0
		self.gama = 0
		self.spuse = set()          # nepotrivirile spuse in jurnal (o data fiecare)
		self.timerComparatie = None
		self.timerIncercare = None
		self.intrebare = None       # {"valoare", "inainte", "termen"} cat se intreaba dupa o iesire HDR noua
		self.oferit = self.simulare or citestePq(self.driver.citeste()) is not None

	# ---- ce exista

	def hdrOferit(self):
		"""Fisierul HDR al programului platformei, fara lista de alegeri (cu lista, randul e in Setari > Video)."""
		if self.simulare:
			return True
		return os.path.exists(CALE_HDR) and not os.path.exists(CALE_HDR_ALEGERI) and os.path.exists(CALE_DISP)

	def tv(self):
		if self.simulare:
			return {"stiut": True, "hdr10": True, "hlg": True}
		return televizorHdr(self.citesteFisier(CALE_DISP), self.citesteFisier(CALE_SINK))

	def modVideo(self):
		if self.simulare:
			return "1080p50"
		return (self.citesteFisier(CALE_MOD_VIDEO) or "").strip()

	def alegeriHdr(self):
		"""Valorile randului „Ieșire HDR” pentru televizorul de acum; [] cand randul nu se arata."""
		if not self.hdrOferit():
			return []
		tv = self.tv()
		if not (tv.get("hdr10") or tv.get("hlg")):
			return []
		return alegeriHdr(tv)

	# ---- profilul de acum

	def clasa(self):
		return clasaDupaLatime(self.latime)

	def profilAcum(self):
		"""Profilul canalului de acum, sau None fara imagine."""
		c = self.clasa()
		if c is None:
			return None
		scris = self.hdrScris if self.hdrOferit() else None
		return "%s_%s" % (c, dinamica(scris, self.gama))

	def textAcum(self):
		"""Randul „Acum” al ecranului si al paginii."""
		p = self.profilAcum()
		if p is None:
			return _t("Acum nu e nicio imagine (radio sau niciun canal pornit).")
		return _t("Acum: canal %(clasa)s, %(latime)dx%(inaltime)d, imagine %(dinamica)s.") % {
			"clasa": _t(dict(CLASE)[p.split("_")[0]]), "latime": self.latime, "inaltime": self.inaltime,
			"dinamica": dict(DINAMICI)[p.split("_")[1]]}

	# ---- scrierea in driver

	def citesteStarea(self):
		"""Starea driverului dupa citire: culorile si tariile exact, pornit numai unde citirea spune „on” (un modul
		citit „off” poate fi oprit de placa pe sursa de acum, deci alegerea lui ramane nestiuta)."""
		s = citestePq(self.driver.citeste())
		if s is None:
			return None
		avut = {"culori": dict(s["culori"]), "module": {}}
		for cheie, m in s["module"].items():
			a = {}
			if "tarie" in m:
				a["tarie"] = m["tarie"]
			if m.get("pornit"):
				a["pornit"] = True
			avut["module"][cheie] = a
		return avut

	def _scrie(self, comenzi):
		scrise = 0
		for comanda in comenzi:
			if not comandaPermisa(comanda):
				_jurnal("comanda refuzata: %r" % comanda)
				continue
			if self.driver.scrie(comanda):
				scrise += 1
				if self.avut is not None:
					_aplicaPeStare(self.avut, comanda)
		return scrise

	def _verifica(self, dorit, eticheta):
		"""Citirea inapoi: taria si culorile exact; pornit/oprit numai la modulele pe care placa le lasa pe sursa de
		acum."""
		s = citestePq(self.driver.citeste())
		if s is None:
			return
		clasa = s.get("sursa")
		for cheie, v in dorit.items():
			if REGLAJ[cheie][3] == CULOARE:
				bun = s["culori"].get(cheie, v) == v
			else:
				m = s["module"].get(cheie, {})
				bun = v == 0 or m.get("tarie", v) == v
				if bun and clasa is not None and cheie in PE_CLASA.get(clasa, ()) and "pornit" in m:
					bun = m["pornit"] == (v != 0)
			semn = (eticheta, cheie)
			if not bun and semn not in self.spuse:
				self.spuse.add(semn)
				_jurnal("dupa %s, %s nu are valoarea scrisa (%d); driverul arata altceva" % (eticheta, cheie, v))

	def aplica(self, profil=None, valori=None, forteaza=False):
		"""Scrie in driver profilul (de acum, daca lipseste) cu valorile salvate, sau `valori` (incercare). Cu
		„Reglajele după canal” pe Nu, valorile din fabrica. Intoarce numarul de comenzi scrise."""
		if not self.oferit:
			return 0
		from Components.config import config
		if self.avut is None:
			self.avut = self.citesteStarea() or {"culori": {}, "module": {}}
		profil = profil or self.profilAcum()
		if profil is None:
			return 0
		if valori is None:
			if config.hds_calitate.pornit.value:
				valori = valoriProfil(profil, salvate=True)
				eticheta = profil
			else:
				# numai reglajele clasei: celelalte nu lucreaza pe sursa de acum si se scriu la canalul clasei lor
				valori = valoriFabrica(profil.split("_")[0])
				eticheta = "fabrica_" + profil.split("_")[0]
		else:
			eticheta = profil + " (incercare)"
		if not forteaza and eticheta == self.profilScris and not self.incercat:
			return 0
		n = self._scrie(comenziPentru(valori, self.avut))
		self.profilScris = eticheta
		if n:
			self._verifica(valori, eticheta)
		return n

	def incearca(self, profil, valori, web=False):
		"""Valorile din ecran sau din pagina, nesalvate, scrise pe loc daca profilul e al canalului de acum (altfel nu
		se pot vedea). web=True: revin singure dupa SECUNDE_INCERCARE fara „Păstrează”. True cand s-au scris."""
		if not self.oferit or profil != self.profilAcum():
			return False
		self.aplica(profil, valori)
		self.incercat = True
		if web:
			self._pornesteTimer("timerIncercare", SECUNDE_INCERCARE, self.renunta)
		return True

	def renunta(self):
		"""Inapoi la valorile salvate (dupa EXIT sau dupa „Renunță”)."""
		self._opresteTimer("timerIncercare")
		self.incercat = False
		self.profilScris = None
		self.aplica()

	def dupaSalvare(self):
		"""Dupa „Păstrează”: profilul de acum scris din nou cu valorile salvate."""
		self._opresteTimer("timerIncercare")
		self.incercat = False
		self.profilScris = None
		self.aplica()

	# ---- comparatia pe jumatate de ecran

	def comparatieOferita(self, cheie):
		return self.oferit and cheie in CU_COMPARATIE and cheie in PE_CLASA.get(self.clasa(), ())

	def pornesteComparatia(self, cheie, secunde=None):
		"""Jumatatea dreapta cu reglajul, cea stanga fara. secunde: se opreste singura (web)."""
		if not self.comparatieOferita(cheie):
			return False
		comanda = REGLAJ[cheie][1]
		self._scrie(["all demooff", "demomode fixr", "%s demoon" % comanda])
		self.comparatie = cheie
		if secunde:
			self._pornesteTimer("timerComparatie", secunde, self.opresteComparatia)
		return True

	def opresteComparatia(self):
		self._opresteTimer("timerComparatie")
		if self.comparatie is None:
			return False
		self._scrie(["all demooff", "demomode fixl"])
		self.comparatie = None
		return True

	# ---- iesirea HDR

	def scrieHdr(self, forteaza=False, alegere=None):
		"""Textul pentru televizorul si modul video de acum, scris numai cand difera de ultimul (sau forteaza)."""
		if not self.hdrOferit():
			return None
		if alegere is None:
			from Components.config import config
			alegere = config.hds_calitate.iesire_hdr.value
		text = hdrDeScris(alegere, self.tv(), self.modVideo())
		if text != self.hdrScris or forteaza:
			if self.simulare:
				_jurnal("simulare: %s = %s" % (CALE_HDR, text))
				ok = True
			else:
				ok = self.scrieFisier(CALE_HDR, text)
			if ok:
				if text != self.hdrScris:
					_jurnal("iesirea HDR: %s (alegerea %s)" % (text, alegere))
				self.hdrScris = text
		return self.hdrScris

	# ---- evenimentele serviciului

	def laEveniment(self, ev, nav=None):
		try:
			from enigma import iPlayableService, iServiceInformation
		except ImportError:
			return
		if ev == iPlayableService.evStart:
			self.latime = self.inaltime = 0
			self.gama = 0
			self.opresteComparatia()
			self.scrieHdr()
			return
		marime = ev == iPlayableService.evVideoSizeChanged
		gama = ev == getattr(iPlayableService, "evVideoGammaChanged", None)
		if not (marime or gama):
			return
		service = nav.getCurrentService() if nav is not None else None
		info = service and service.info()
		if not info:
			return
		self.latime = max(0, info.getInfo(iServiceInformation.sVideoWidth))
		self.inaltime = max(0, info.getInfo(iServiceInformation.sVideoHeight))
		s_gama = getattr(iServiceInformation, "sGamma", None)
		if s_gama is not None:
			g = info.getInfo(s_gama)
			self.gama = g if g in (0, 1, 2, 3) else 0
		if self.incercat:
			self.renunta()
		else:
			self.aplica()

	# ---- ceasurile

	def _pornesteTimer(self, nume, secunde, functie):
		if self.faTimer is None:
			return
		t = getattr(self, nume)
		if t is None:
			t = self.faTimer(functie)
			setattr(self, nume, t)
		t.start(int(secunde * 1000))

	def _opresteTimer(self, nume):
		t = getattr(self, nume)
		if t is not None:
			t.stop()


class _Timer(object):
	def __init__(self, functie):
		from enigma import eTimer
		self.t = eTimer()
		self.t.callback.append(functie)

	def start(self, ms):
		self.t.start(ms, True)

	def stop(self):
		self.t.stop()


_STARE = {"calitate": None, "sesiune": None}


def calitate():
	"""Starea receptorului (porneste), sau una facuta acum (ecranul deschis in probe fara pornire)."""
	if _STARE["calitate"] is None:
		_STARE["calitate"] = _faCalitate()
	return _STARE["calitate"]


def _faCalitate():
	simulare = False
	try:
		from Components.SystemInfo import SystemInfo
		simulare = bool(SystemInfo.get("HdsVideoSimulation")) and not os.path.exists(CALE_PQ)
	except ImportError:
		pass
	try:
		from enigma import eTimer
		timer = _Timer if eTimer is not None else None
	except ImportError:
		timer = None
	return Calitate(simulare=simulare, timer=timer)


def disponibil():
	return calitate().oferit


# randurile ecranului pentru „Caută setări” (Components/HdsCautaSetari.inregistreaza): textul randului, setarea, cuvinte
RANDURI_CAUTARE = (
	(N_("Reglajele după canal"), "config.hds_calitate.pornit", N_("calitate imagine profil")),
	(N_("Ieșire HDR"), "config.hds_calitate.iesire_hdr", "HDR HDR10 HLG SDR"),
	(N_("Claritate"), "", N_("claritate imagine ascuțire")),
	(N_("Reducerea zgomotului"), "", N_("zgomot purici")),
	(N_("Luminozitate"), "", ""),
	(N_("Contrast"), "", ""),
	(N_("Saturație"), "", N_("culori")),
)


def porneste(session):
	"""La pornirea interfetei, inaintea primului canal: setarile, SystemInfo, iesirea HDR si legatura la servicii."""
	initConfig()
	c = calitate()
	_STARE["sesiune"] = session
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsCalitateImagine"] = c.oferit
		if c.oferit and not c.simulare:
			# randul vechi „Picture Sharpness” (pep_scaler_sharpness) nu schimba nimic pe aceasta placa; claritatea e
			# aici
			SystemInfo["CanScalerSharpness"] = False
	except ImportError:
		pass
	if not c.oferit:
		_jurnal("blocul de calitate al placii lipseste: meniul nu se arata")
		return c
	try:
		from Components import HdsCautaSetari
		HdsCautaSetari.inregistreaza("hds_calitate_imagine", RANDURI_CAUTARE)
	except Exception as e:
		_jurnal("Caută setări: %s" % e)
	c.scrieHdr(forteaza=True)
	nav = getattr(session, "nav", None)
	if nav is not None:
		def eveniment(ev):
			try:
				c.laEveniment(ev, nav)
			except Exception as e:
				_jurnal("la evenimentul %s: %s" % (ev, e))
		nav.event.append(eveniment)
	return c


# ---------------------------------------------------------------- iesirea HDR aleasa (ecran si web)

def intrebareText(valoare):
	return _t("Imaginea se vede corect cu ieșirea HDR „%s”?") % numeIesireHdr(valoare)


def incearcaHdr(session, valoare, laSfarsit=None):
	"""Iesirea HDR noua: scrisa, canalul pornit din nou (programul platformei o citeste la pornirea canalului), apoi
	intrebarea pe televizor; Da = salvata, Nu sau fara raspuns in SECUNDE_INTREBARE = cea de dinainte, scrisa si cu
	canalul pornit din nou. laSfarsit(pastrat, mesaj) dupa raspuns. Intoarce (pornit, mesaj)."""
	from Components.config import config, configfile
	c = calitate()
	el = config.hds_calitate.iesire_hdr
	if valoare not in c.alegeriHdr():
		return False, _t("Televizorul acesta nu primește această ieșire HDR.")
	if c.intrebare is not None:
		return False, _t("Pe televizor așteaptă deja o întrebare.")
	inainte = el.saved_value if el.saved_value is not None else el.default
	if valoare == inainte:
		el.value = valoare
		c.scrieHdr()
		return True, _t("Ieșirea HDR era deja aceasta.")
	from Components import VideoOutput
	el.value = valoare
	c.scrieHdr()
	pe_ecran = VideoOutput.restartService(session.nav)
	c.intrebare = {"valoare": valoare, "inainte": inainte, "termen": c.ceas() + SECUNDE_INTREBARE}

	def raspuns(da):
		c.intrebare = None
		if da:
			el.value = valoare
			el.save()
			configfile.save()
			mesaj = _t("Păstrat: %s.") % numeIesireHdr(valoare)
		else:
			el.value = inainte
			el.save()
			c.scrieHdr()
			VideoOutput.restartService(session.nav)
			mesaj = _t("Ieșirea HDR nu a fost confirmată. A revenit cea de dinainte.")
		c.profilScris = None
		c.aplica()
		if laSfarsit is not None:
			laSfarsit(bool(da), mesaj)

	try:
		from Screens.MessageBox import MessageBox
		from Screens.VideoSetup import ModeQuestion
		text = intrebareText(valoare)
		if not pe_ecran:
			text = _t("Ieșirea HDR se folosește când pornește un canal. O păstrezi?")
		session.openWithCallback(raspuns, ModeQuestion, text, MessageBox.TYPE_YESNO, timeout=SECUNDE_INTREBARE,
			default=False)
	except Exception as e:
		_jurnal("intrebarea pe televizor: %s" % e)
		raspuns(False)
		return False, _t("Întrebarea nu s-a putut deschide pe televizor. A rămas ieșirea de dinainte.")
	return True, _t("Uită-te la televizor și răspunde la întrebare în %d de secunde.") % SECUNDE_INTREBARE


def implicite(profil=None):
	"""„Înapoi la implicite”: valorile din fabrica pentru un profil sau pentru toate (profil None), in setari
	nesalvate."""
	for p in (PROFILURI if profil is None else (profil,)):
		for cheie, e in elementeProfil(p):
			e.value = str(FABRICA)


def salveaza():
	"""Setarile modulului salvate in fisierul de setari (afara de iesirea HDR, care se pastreaza numai dupa intrebare),
	apoi profilul de acum scris din nou."""
	from Components.config import config, configfile
	schimbate = [e for e in toateElementele() if e is not config.hds_calitate.iesire_hdr and e.isChanged()]
	for e in schimbate:
		e.save()
	if schimbate:
		configfile.save()        # fara nicio schimbare, fisierul de setari (eMMC) nu se rescrie
	calitate().dupaSalvare()
	return len(schimbate)


def anuleaza():
	"""Setarile nesalvate puse la loc (afara de iesirea HDR, care trece prin intrebare) si driverul la valorile
	salvate."""
	from Components.config import config
	for e in toateElementele():
		if e is not config.hds_calitate.iesire_hdr:
			e.cancel()
	c = calitate()
	c.opresteComparatia()
	c.renunta()
