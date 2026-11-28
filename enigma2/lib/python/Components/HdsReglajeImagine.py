# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReglajeImagine.py: luminozitatea, contrastul, culorile, claritatea si zgomotul imaginii pe placile FARA blocul de
# calitate HiSilicon (/proc/msp/pq): Broadcom (Vu+ 4K, Dreambox DM900/DM920, GigaBlue), HiSilicon 3716MV430 (ZGEMMA
# H8.2H Plus) si orice placa al carei driver are fisierele /proc/stb/vmpeg/0/pep_*. Scris de la zero pentru 0.8.0
# (PQ2); pe placile cu /proc/msp/pq ramane ecranul cu profiluri din Components/HdsCalitateImagine.py.
#
# O SINGURA LOGICA pentru ecranul de pe televizor (Screens/HdsCalitateImagine.HdsReglajeImagine), pagina web
# (HdsWebControl/reglaje_imagine_web.py, la /calitate-imagine) si probele de pe PC.
#
# DRIVERUL: fiecare reglaj e un fisier cu un numar in hex (de ex. 00007fff); dupa scriere, „1” in pep_apply il pune in
# imagine. Citit pe ZGEMMA H8.2H Plus (26.11.2026): brightness, contrast, hue, saturation, sharpness = 7fff,
# pep_apply = 00000001. Pe Viper 4K V20 (HiSilicon 3798MV200) fisierele exista dar se citesc goale: acolo nu se ofera
# nimic de aici (are oricum /proc/msp/pq).
#
# Regulile, ca sa nu stricam imaginea pe o placa necitita la noi:
# - un reglaj se arata numai daca fisierul lui exista SI se citeste ca numar hex (gol sau text = ascuns);
# - valorile din fabrica sunt cele citite la prima pornire a interfetei dupa pornirea receptorului, inaintea oricarei
#   scrieri; se pastreaza in /tmp (CALE_FABRICA), deci o repornire a interfetei nu ia drept „fabrica” ce am scris noi;
# - la pornire si dupa schimbarea modului video se scriu NUMAI reglajele salvate altfel decat din fabrica; fara nimic
#   salvat nu se scrie nimic, nici pep_apply;
# - o scriere refuzata de driver lasa reglajul cum era si se spune pe ecran.
#
# Gama: reglajele „late” (luminozitate, contrast, saturatie, nuanta, claritate, contrast dinamic) au 0..ffff in
# driver, aratate ca 0..100 (50 = mijlocul: 8000 scris, 7fff citit, ca la pornire; vezi brutDinPozitie). Reglajele
# „mici” (blocuri, zgomotul contururilor, dungile, pielea, verde, albastru) au trepte 0..N scrise ca atare; „comutat”
# (liniile oblice) are 0 sau 1. pep_scaler_sharpness ramane al randului „Claritatea imaginii” (AVSwitch.py).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il incarca fara receptor.

import json
import os

RADACINA = "/proc/stb/vmpeg/0"
CALE_PQ = "/proc/msp/pq"
CALE_FABRICA = "/tmp/hds-reglaje-imagine-fabrica.json"
FISIER_APLICA = "pep_apply"
MAX_LAT = 0xffff
PAS_LAT = 2            # pe televizor si in web: 0, 2, 4 ... 100
INTARZIERE_MOD_MS = 1500   # dupa un mod video nou driverul are nevoie de putin timp pana primeste reglajele

LAT = "lat"
MIC = "mic"
COMUTAT = "comutat"


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


def _jurnal(text):
	print("[HdsReglajeImagine] %s" % text)


# (cheia, fisierul din RADACINA, fel, treapta maxima pentru MIC/COMUTAT, eticheta, descrierea)
REGLAJE = (
	("luminozitate", "pep_brightness", LAT, 0, N_("Luminozitate"),
		N_("Cât de luminoasă e imaginea.")),
	("contrast", "pep_contrast", LAT, 0, N_("Contrast"),
		N_("Diferența dintre părțile întunecate și cele luminoase.")),
	("saturatie", "pep_saturation", LAT, 0, N_("Saturație"),
		N_("Cât de puternice sunt culorile.")),
	("nuanta", "pep_hue", LAT, 0, N_("Nuanță"),
		N_("Mută culorile spre verde sau spre roșu, pentru fețe naturale.")),
	("claritate", "pep_sharpness", LAT, 0, N_("Claritate"),
		N_("Contururi mai precise după mărirea imaginii. Prea mult face margini albe în jurul obiectelor.")),
	("contrast_dinamic", "pep_dynamic_contrast", LAT, 0, N_("Contrast adaptiv"),
		N_("Receptorul potrivește singur contrastul după fiecare scenă.")),
	("blocuri", "pep_block_noise_reduction", MIC, 5, N_("Pătrățelele compresiei"),
		N_("Șterge marginile pătrățelelor care apar pe canalele cu debit mic.")),
	("contururi", "pep_mosquito_noise_reduction", MIC, 5, N_("Zgomotul de pe contururi"),
		N_("Șterge tremurul din jurul literelor și al marginilor ascuțite.")),
	("dungi", "pep_digital_contour_removal", MIC, 5, N_("Dungile de culoare"),
		N_("Netezește trecerile în trepte dintre culori, pe cer și pe pereți.")),
	("piele", "pep_auto_flesh", MIC, 4, N_("Îmbunătățirea culorilor"),
		N_("Culori mai vii și pielea mai naturală.")),
	("verde", "pep_green_boost", MIC, 4, N_("Verde mai viu"),
		N_("Face iarba și frunzele mai vii.")),
	("albastru", "pep_blue_boost", MIC, 4, N_("Albastru mai viu"),
		N_("Face cerul și apa mai vii.")),
	("linii_oblice", "pep_scaler_vertical_dejagging", COMUTAT, 1, N_("Liniile oblice"),
		N_("Netezește treptele de pe liniile oblice după mărirea imaginii.")),
)
CHEI = tuple(r[0] for r in REGLAJE)
REGLAJ = dict((r[0], r) for r in REGLAJE)


def numarHex(text):
	"""Textul driverului (de ex. „00007fff\\n”) -> numar, sau None daca nu e un numar hex intre 0 si ffffffff."""
	if text is None:
		return None
	t = text.strip().lower()
	if t.startswith("0x"):
		t = t[2:]
	if not t or len(t) > 8 or any(ch not in "0123456789abcdef" for ch in t):
		return None
	return int(t, 16)


def textHex(n):
	return "%08x" % n


def pozitii(cheie):
	"""Pozitiile aratate omului pentru reglaj: 0..100 din 2 in 2 (LAT) sau 0..N (MIC, COMUTAT)."""
	r = REGLAJ[cheie]
	if r[2] == LAT:
		return tuple(range(0, 101, PAS_LAT))
	return tuple(range(0, r[3] + 1))


def textPozitie(cheie, poz, traduce=True):
	"""Textul pozitiei; traduce=False pentru alegerile setarii (ConfigSelection le traduce la afisare)."""
	t = _t if traduce else N_
	r = REGLAJ[cheie]
	if r[2] == COMUTAT:
		return t("Pornit") if poz else t("Oprit")
	if r[2] == MIC and poz == 0:
		return t("Oprit")
	return str(poz)


def brutDinPozitie(cheie, poz, fabrica_brut=None):
	"""Pozitia -> numarul scris in driver. LAT: cel mai mic numar care da exact poz la suta in driverul care imparte la
	65536 si taie (masurat pe ZGEMMA .129: 7fff scris = 49 la suta, citit 7d70; 8000 = 50, citit 7fff, ca la pornire;
	b333 = 70, b332 = 69); peste ffff driverul tine ffff. Pe un driver cu 16 biti adevarati e acelasi numar, cu cel mult
	o unitate in plus. fabrica_brut ramane pentru chemarile vechi (nu schimba nimic)."""
	r = REGLAJ[cheie]
	if r[2] == LAT:
		return min(MAX_LAT, -(-int(poz) * 65536 // 100))
	return int(poz)


def pozitieDinBrut(cheie, brut):
	"""Numarul driverului -> cea mai apropiata pozitie aratata (7fff si 7d70 = 50 la suta din 2 in 2)."""
	r = REGLAJ[cheie]
	if r[2] == LAT:
		p = int(brut * 100.0 / MAX_LAT + 0.5)
		return max(0, min(100, int(p / float(PAS_LAT) + 0.5) * PAS_LAT))
	return max(0, min(r[3], int(brut)))


class Reglaje(object):
	"""Starea placii: ce reglaje are (citite o data), valorile din fabrica, ce s-a scris acum."""

	def __init__(self, radacina=RADACINA, cale_pq=CALE_PQ, cale_fabrica=CALE_FABRICA):
		self.radacina = radacina
		self.cale_pq = cale_pq
		self.cale_fabrica = cale_fabrica
		self.fabrica = {}      # cheie -> numarul driverului citit la pornire
		self.scris = {}        # cheie -> ultimul numar scris de noi (pentru renuntare)
		self.eroare = None     # textul ultimei scrieri refuzate, pentru ecran si web
		self._citesteFabrica()
		self.oferit = bool(self.fabrica) and not os.path.exists(self.cale_pq)

	# ---- driverul

	def cale(self, cheie):
		return os.path.join(self.radacina, REGLAJ[cheie][1])

	def _citesteFisier(self, cale):
		try:
			with open(cale) as f:
				return f.read(64)
		except (IOError, OSError):
			return None

	def citeste(self, cheie):
		return numarHex(self._citesteFisier(self.cale(cheie)))

	def _scrieFisier(self, cale, text):
		try:
			with open(cale, "w") as f:
				f.write(text)
			return True
		except (IOError, OSError) as e:
			_jurnal("%s <- %s: %s" % (cale, text, e))
			return False

	def _citesteFabrica(self):
		"""Valorile din fabrica: din /tmp daca interfata a mai pornit de la pornirea receptorului, altfel citite acum
		(inaintea oricarei scrieri) si pastrate in /tmp."""
		pastrate = None
		try:
			with open(self.cale_fabrica) as f:
				pastrate = json.load(f)
		except (IOError, OSError, ValueError):
			pastrate = None
		for cheie in CHEI:
			if not os.path.exists(self.cale(cheie)):
				continue
			acum = self.citeste(cheie)
			if acum is None:
				continue   # gol sau text: driverul nu-l lucreaza, nu se arata
			r = REGLAJ[cheie]
			if acum > (MAX_LAT if r[2] == LAT else r[3]):
				_jurnal("%s: %s e peste gama cunoscuta, nu se arata" % (r[1], hex(acum)))
				continue   # alta gama decat cea stiuta: mai bine ascuns decat scris gresit
			if isinstance(pastrate, dict) and isinstance(pastrate.get(cheie), int):
				self.fabrica[cheie] = pastrate[cheie]
			else:
				self.fabrica[cheie] = acum
		if self.fabrica and not isinstance(pastrate, dict):
			try:
				with open(self.cale_fabrica, "w") as f:
					json.dump(self.fabrica, f)
			except (IOError, OSError) as e:
				_jurnal("valorile din fabrica nu s-au pastrat: %s" % e)

	def chei(self):
		"""Reglajele placii, in ordinea din REGLAJE."""
		return [c for c in CHEI if c in self.fabrica]

	def pozitieFabrica(self, cheie):
		return pozitieDinBrut(cheie, self.fabrica[cheie])

	def scrie(self, valori):
		"""valori: {cheie: pozitie}. Scrie numerele, apoi o data pep_apply. Intoarce True daca driverul le-a primit pe
		toate; un refuz lasa self.eroare."""
		scrise = False
		bine = True
		self.eroare = None
		for cheie in self.chei():
			if cheie not in valori:
				continue
			brut = brutDinPozitie(cheie, int(valori[cheie]), self.fabrica[cheie])
			if self._scrieFisier(self.cale(cheie), textHex(brut)):
				self.scris[cheie] = brut
				scrise = True
			else:
				bine = False
				self.eroare = _t("Placa nu a primit această valoare.")
		if scrise:
			aplica = os.path.join(self.radacina, FISIER_APLICA)
			if os.path.exists(aplica):
				self._scrieFisier(aplica, "1")
		return bine


_STARE = {"reglaje": None, "timer": None}


def reglaje():
	if _STARE["reglaje"] is None:
		_STARE["reglaje"] = Reglaje()
	return _STARE["reglaje"]


def disponibil():
	return reglaje().oferit


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_reglaje.<cheie>: pozitia, cu valoarea din fabrica a placii drept implicita (deci in fisierul de
	setari ajung numai reglajele schimbate). Numai pentru reglajele placii; a doua chemare nu mai face nimic."""
	from Components.config import config, ConfigSubsection, ConfigSelection
	r = reglaje()
	try:
		sectiune = config.hds_reglaje
	except (AttributeError, KeyError):
		config.hds_reglaje = ConfigSubsection()
		sectiune = config.hds_reglaje
	for cheie in r.chei():
		if cheie in sectiune.dict():
			continue
		alegeri = [(str(p), textPozitie(cheie, p, traduce=False)) for p in pozitii(cheie)]
		setattr(sectiune, cheie, ConfigSelection(default=str(r.pozitieFabrica(cheie)), choices=alegeri))
	return sectiune


def element(cheie):
	from Components.config import config
	return getattr(config.hds_reglaje, cheie)


def valori(salvate=False):
	"""{cheie: pozitie}: cele din ecran (value) sau cele salvate."""
	rez = {}
	for cheie in reglaje().chei():
		e = element(cheie)
		v = e.saved_value if salvate and e.saved_value is not None else (e.default if salvate else e.value)
		rez[cheie] = int(v)
	return rez


def schimbate():
	"""{cheie: pozitie} numai pentru reglajele salvate altfel decat din fabrica."""
	r = reglaje()
	return dict((c, p) for c, p in valori(salvate=True).items() if p != r.pozitieFabrica(c))


def incearca(cheie=None, poz=None):
	"""Previzualizarea: reglajul (sau toate cele din ecran) scrise pe loc, nesalvate."""
	if cheie is not None:
		element(cheie).value = str(poz)
		return reglaje().scrie({cheie: int(poz)})
	# toate randurile din ecran sau din web: numai cele mutate de la fabrica sau scrise deja de noi
	r = reglaje()
	return r.scrie(dict((c, p) for c, p in valori().items() if c in r.scris or p != r.pozitieFabrica(c)))


def salveaza():
	from Components.config import configfile
	for cheie in reglaje().chei():
		element(cheie).save()
	configfile.save()
	return reglaje().scrie(dict((c, p) for c, p in valori().items() if c in reglaje().scris or
		p != reglaje().pozitieFabrica(c)))


def anuleaza():
	"""Pune la loc ce e salvat: ecranul revine la valorile salvate si driverul primeste numai ce am scris altfel."""
	r = reglaje()
	salvate = valori(salvate=True)
	for cheie in r.chei():
		element(cheie).value = str(salvate[cheie])
	deScris = dict((c, salvate[c]) for c in list(r.scris) if r.scris[c] != brutDinPozitie(c, salvate[c], r.fabrica[c]))
	if deScris:
		r.scrie(deScris)
	return True


def implicite(salveaza_acum=True):
	"""Valorile din fabrica: in ecran, salvate si scrise in driver (numai cele schimbate de noi)."""
	r = reglaje()
	for cheie in r.chei():
		element(cheie).value = str(r.pozitieFabrica(cheie))
	deScris = dict((c, r.pozitieFabrica(c)) for c in list(r.scris) if r.scris[c] != r.fabrica[c])
	if salveaza_acum:
		from Components.config import configfile
		for cheie in r.chei():
			element(cheie).save()
		configfile.save()
	if deScris:
		r.scrie(deScris)
	return True


def aplicaSalvate():
	"""La pornire si dupa un mod video nou: numai reglajele salvate altfel decat din fabrica."""
	if not disponibil():
		return False
	s = schimbate()
	if not s:
		return False
	reglaje().scrie(s)
	_jurnal("puse la loc: %s" % ", ".join("%s=%s" % (c, p) for c, p in sorted(s.items())))
	return True


def dupaModVideo():
	"""Chemat din VideoOutput.apply dupa un mod video primit de driver: reglajele se pun iar, dupa INTARZIERE_MOD_MS."""
	if _STARE["reglaje"] is None or not _STARE["reglaje"].oferit:
		return
	try:
		if not schimbate():
			return
	except Exception:
		return
	try:
		from enigma import eTimer
	except ImportError:
		aplicaSalvate()
		return
	if _STARE["timer"] is None:
		_STARE["timer"] = eTimer()
		_STARE["timer"].callback.append(aplicaSalvate)
	_STARE["timer"].start(INTARZIERE_MOD_MS, True)


def porneste():
	"""La pornirea interfetei: citirea placii (inaintea oricarei scrieri), SystemInfo, setarile, reglajele salvate."""
	r = reglaje()
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsReglajeImagine"] = r.oferit
	except ImportError:
		pass
	if not r.oferit:
		return r
	initConfig()
	try:
		from Components import HdsCautaSetari
		HdsCautaSetari.inregistreaza("hds_reglaje_imagine", RANDURI_CAUTARE)
	except Exception as e:
		_jurnal("Caută setări: %s" % e)
	aplicaSalvate()
	return r


# randurile ecranului pentru „Caută setări” (Components/HdsCautaSetari.inregistreaza): textul, setarea, cuvinte
RANDURI_CAUTARE = (
	(N_("Luminozitate"), "", ""),
	(N_("Contrast"), "", ""),
	(N_("Saturație"), "", N_("culori")),
	(N_("Claritate"), "", N_("claritate imagine ascuțire")),
	(N_("Reducerea zgomotului"), "", N_("zgomot purici")),
)
