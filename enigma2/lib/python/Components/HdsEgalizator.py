# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEgalizator.py: setarile egalizatorului din procesor si legatura lor cu motorul din nucleu (eHdsEgalizator,
# lib/service/hdsegalizator.cpp). Ecranul: Meniu > Audio > Egalizator (Screens/HdsEgalizator.py); web: /egalizator
# (Plugins/Extensions/HdsWebControl/egalizator_web.py). Amandoua folosesc numai functiile de aici.
#
# Setarile (config.hds_egalizator): pornit (global), presetarea, cele 10 benzi (text „b0,b1,...,b9” in dB, -12..+12),
# modul Noapte, nivelul (potrivirea tariei fata de sunetul placii, -12..+12 dB), volumul (automat / in egalizator / pe
# placa) si placa ALSA (implicit „default”). Presetarile pun benzile si modul Noapte; o banda schimbata de mana face
# presetarea „manual”.
#
# Pe post: un post poate avea setarile lui (presetarea, benzile, Noapte, nivelul), tinute in FISIER_POSTURI (JSON, cel
# mult MAX_POSTURI de posturi, scris numai dupa o schimbare, cu PAUZA_SCRIERE_S intre schimbare si scriere, ca apasarile
# repetate sa nu scrie de fiecare data pe eMMC). La pornirea fiecarui serviciu (evStart, inainte ca PMT-ul sa aleaga
# pista) motorul primeste setarile postului, sau pe cele globale.
#
# Ce spune ecranul (textStare): din starea motorului si motivul pentru postul de acum (post: da, oprit, pauza, tv,
# inregistrare, format, fara-decodor-aac...), cu trecerea spre bara de sunet (HdsSunet.stare) pentru AC3/DTS. Felul
# pistei se citeste din /proc cel mult o data la FEL_MAX_S sau la schimbarea serviciului (felPistei), nu la fiecare
# improspatare a ecranului. Datele tehnice (randuriTehnice) sunt pe grupe, in cuvinte; numele elementelor GStreamer si
# textul brut raman numai in „Text brut” din web.
#
# „Pentru acest post” pe Nu: postul uita reglajele lui si foloseste reglajele obisnuite, pe care ecranul si web-ul le
# arata din acel moment (comutaPePost); reglajele obisnuite se schimba numai daca omul le schimba dupa aceea.
#
# Canalele TV: egalizatorul merge si la canalele TV cu sunet MPEG, tinut dupa ceasul imaginii in
# motor (hdsegalizator.h). Setarile tv (Da din fabrica) si potrivire_tv (sunetul mai tarziu sau mai devreme fata de
# imagine, -300..300 ms) sunt in web, la „Pentru probe și potriviri”, ca volumul si placa ALSA.
#
# Fara motor (nucleu fara eHdsEgalizator, PC) totul merge mai departe fara efect: setarile se tin, iar textul spune ca
# egalizatorul lipseste din programul receptorului. Partea de sus nu importa enigma: se probeaza pe PC.

from __future__ import absolute_import

import io
import json
import os
import time

BENZI = 10
FRECVENTE = (31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
ETICHETE = ("31 Hz", "63 Hz", "125 Hz", "250 Hz", "500 Hz", "1 kHz", "2 kHz", "4 kHz", "8 kHz", "16 kHz")
DB_MIN = -12
DB_MAX = 12
NIVEL_MIN = -12
NIVEL_MAX = 12
FISIER_POSTURI = "/etc/enigma2/hds-egalizator-posturi.json"
MAX_POSTURI = 300
PAUZA_SCRIERE_S = 3.0
MANUAL = "manual"
FEL_MAX_S = 10.0
VOLUM_ALEGERI = ("auto", "aici", "placa")
POTRIVIRE_TV_MIN = -300
POTRIVIRE_TV_MAX = 300
POTRIVIRE_TV_PAS = 10
VOLUM_MOTOR = {"auto": 0, "aici": 1, "placa": 2}


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# cheia, numele, cele 10 benzi (dB), modul Noapte. Valorile sunt puncte de plecare, de potrivit la ascultare.
PRESETARI = (
	("normal", N_("Normal"), (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), False),
	("voce", N_("Voce și știri"), (-6, -4, -2, 0, 2, 4, 4, 3, 0, -2), False),
	("pop", N_("Pop"), (2, 3, 2, 0, -1, -1, 0, 2, 3, 3), False),
	("rock", N_("Rock"), (5, 4, 2, -1, -2, -1, 1, 3, 4, 4), False),
	("clasica", N_("Clasică"), (0, 0, 0, 0, 0, 0, 0, 1, 2, 3), False),
	("bas", N_("Bas mai mult"), (7, 6, 4, 1, 0, 0, 0, 0, 0, 0), False),
	("noapte", N_("Noapte"), (-4, -3, -1, 0, 1, 2, 2, 1, 0, -1), True),
)
NUME_MANUAL = N_("Reglat de tine")
CHEI_PRESETARI = tuple(p[0] for p in PRESETARI)

# ce se intampla cu postul de acum (motivul dat de motor) -> textul pe ecran
TEXTE_POST = {
	"oprit": N_("Egalizatorul e oprit. Sunetul merge ca de obicei, prin placa de sunet."),
	"pauza": N_("Pauză. Sunetul revine cu egalizator când pornești din nou."),
	"tv": N_("La canalele TV egalizatorul e oprit din setări. Sunetul merge prin placa de sunet."),
	"inregistrare": N_("La înregistrări și la pauza cu reluare (timeshift) egalizatorul nu lucrează. Sunetul merge prin placa de sunet."),
	"format": N_("Postul acesta are sunet %s. Egalizatorul lucrează la posturile cu sunet MPEG (MP2)."),
	"trecere": N_("Sunetul pleacă neschimbat spre bara de sunet: egalizatorul, volumul și modul de noapte le reglezi din bara de sunet."),
	# posturile AAC: decodorul AAC nu e in imagine din cauza brevetelor; sunetul merge prin placa
	"fara-decodor-aac": N_("La acest post (AAC) egalizatorul nu e disponibil din motive de licențiere a brevetelor AAC."),
	"fara-decodor-mpeg": N_("Egalizatorul nu poate porni: receptorul nu are decodorul MPEG audio."),
	"fara-gstreamer": N_("Egalizatorul nu poate porni: lipsește decodarea sunetului în procesor (GStreamer)."),
	"fara-alsa": N_("Egalizatorul nu poate porni: placa de sunet nu se poate folosi din procesor."),
	"fara-sunet": N_("Postul acesta nu are sunet."),
	"nimic": N_("Nu merge niciun post acum. Setările se aplică la următorul post de radio."),
	"fara-motor": N_("Egalizatorul lipsește din programul acestui receptor. Setările se păstrează, dar nu se aud."),
}
TEXTE_MOTIV = {
	"fara-date-la-pornire": N_("nu au venit date de sunet de la post"),
	"demux-refuzat": N_("fluxul postului nu s-a putut citi"),
	"alsa-refuzat": N_("placa de sunet nu a primit sunetul"),
	"alsa-cazut": N_("placa de sunet s-a oprit"),
	"placa-oprita": N_("ieșirea plăcii de sunet pentru procesor e oprită"),
	"eroare-decodare": N_("sunetul nu s-a putut decoda"),
	"eroare-gstreamer": N_("decodorul nu a pornit"),
	"fara-decodor-aac": N_("receptorul nu are decodor AAC"),
	"fara-decodor-mpeg": N_("receptorul nu are decodorul MPEG audio"),
	"fara-gstreamer": N_("lipsește decodarea sunetului în procesor"),
	"fara-alsa": N_("placa de sunet nu se poate folosi din procesor"),
	"latm-nesuportat": N_("felul acesta de AAC nu se poate decoda încă"),
	"format-necunoscut": N_("felul sunetului nu s-a recunoscut"),
	"fisier-lipsa": N_("fișierul probei nu există"),
	"wav-refuzat": N_("fișierul probei nu s-a putut scrie"),
	"tv-fara-ceas": N_("receptorul nu a dat ceasul imaginii"),
	"tv-nepotrivit": N_("sunetul nu s-a putut potrivi cu imaginea"),
}
MOTIV_NECUNOSCUT = N_("o eroare neașteptată")
TEXT_ESUAT = N_("Egalizatorul nu a putut porni la acest post (%s). Sunetul merge prin placa de sunet.")
TEXT_MERGE = N_("Se aude cu egalizator: %s.")
TEXT_PROBA = N_("Probă din fișier, cu egalizator: %s.")
TEXT_PROBA_OPRIT = N_("Probă din fișier, cu egalizator: %s. Proba merge și cu egalizatorul oprit.")
TEXT_DEBIT_CAM = N_("cam %d kbit/s")
TEXT_PORNESTE = N_("Pornește egalizatorul la acest post...")
TEXT_FARA_DATE = N_("Postul nu mai trimite sunet. Egalizatorul așteaptă.")

_STARE = {"memorie": None, "nav": None, "ceas": None, "incercari": 0, "pornit": False, "ascultatori": [],
	"post": None, "legat_motor": False}
_FEL = {"ref": None, "t": 0.0, "val": (None, None)}


def _jurnal(text):
	print("[HdsEgalizator] %s" % text)


# ---------------------------------------------------------------- benzile ca text

def limiteaza(v, jos, sus):
	try:
		v = int(round(float(v)))
	except (TypeError, ValueError, OverflowError):   # si „1e999” / „Infinity” scrise de mana
		return 0
	return jos if v < jos else (sus if v > sus else v)


def benziDinText(text):
	"""„0,2,-3,...” -> lista de 10 intregi in -12..+12; lipsurile si gunoiul devin 0."""
	parti = (text or "").replace(";", ",").split(",")
	rez = []
	for i in range(BENZI):
		rez.append(limiteaza(parti[i], DB_MIN, DB_MAX) if i < len(parti) and parti[i].strip() else 0)
	return rez


def textDinBenzi(benzi):
	return ",".join(str(limiteaza(b, DB_MIN, DB_MAX)) for b in list(benzi)[:BENZI])


def presetare(cheie):
	for p in PRESETARI:
		if p[0] == cheie:
			return p
	return None


def presetareDupaBenzi(benzi, noapte):
	"""Presetarea care are exact aceste benzi si acest mod Noapte, sau MANUAL."""
	b = [limiteaza(x, DB_MIN, DB_MAX) for x in benzi]
	for p in PRESETARI:
		if list(p[2]) == b and bool(p[3]) == bool(noapte):
			return p[0]
	return MANUAL


def numePresetare(cheie):
	p = presetare(cheie)
	return _t(p[1]) if p else _t(NUME_MANUAL)


def alegeriPresetare():
	return [(p[0], _t(p[1])) for p in PRESETARI] + [(MANUAL, _t(NUME_MANUAL))]


def textDb(v):
	"""+3 dB / 0 dB / −3 dB (minus tipografic, se citeste bine de la 3 m)."""
	v = int(v)
	if v > 0:
		return u"+%d dB" % v
	if v < 0:
		return u"−%d dB" % (-v)
	return u"0 dB"


# ---------------------------------------------------------------- setarile

def initConfig():
	from Components.config import config
	if "hds_egalizator" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigText
	config.hds_egalizator = ConfigSubsection()
	c = config.hds_egalizator
	c.pornit = ConfigYesNo(default=False)
	c.presetare = ConfigSelection(default="normal", choices=alegeriPresetare())
	c.benzi = ConfigText(default=textDinBenzi([0] * BENZI), fixed_size=False)
	c.noapte = ConfigYesNo(default=False)
	# nivelul ca text („-3”): ConfigSelection cu alegerile lui, citit si scris numai prin limiteaza()/str()
	c.nivel = ConfigSelection(default="0", choices=[(str(v), textDb(v)) for v in range(NIVEL_MIN, NIVEL_MAX + 1)])
	c.volum = ConfigSelection(default="auto", choices=[
		("auto", _t("Automat")), ("aici", _t("În egalizator")), ("placa", _t("Pe placa de sunet"))])
	c.placa = ConfigText(default="default", fixed_size=False)
	# canalele TV: egalizatorul si la ele (sunetul tinut dupa imagine), cu potrivirea fata de imagine
	c.tv = ConfigYesNo(default=True)
	c.potrivire_tv = ConfigSelection(default="0", choices=alegeriPotrivireTv())


def textMsSemn(v):
	"""+40 ms / 0 ms / −40 ms (minus tipografic)."""
	v = int(v)
	if v > 0:
		return u"+%d ms" % v
	if v < 0:
		return u"−%d ms" % (-v)
	return u"0 ms"


def alegeriPotrivireTv():
	return [(str(v), textMsSemn(v)) for v in range(POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX + 1, POTRIVIRE_TV_PAS)]


def setariGlobale():
	from Components.config import config
	c = config.hds_egalizator
	benzi = benziDinText(c.benzi.value)
	return {"presetare": c.presetare.value, "benzi": benzi, "noapte": bool(c.noapte.value),
		"nivel": limiteaza(c.nivel.value, NIVEL_MIN, NIVEL_MAX)}


def _curataSetari(d):
	"""Un dictionar de setari venit din fisier sau din web -> numai cheile stiute, cu valori bune."""
	if not isinstance(d, dict):
		return None
	benzi = d.get("benzi")
	if isinstance(benzi, (list, tuple)):
		benzi = [limiteaza(x, DB_MIN, DB_MAX) for x in list(benzi)[:BENZI]] + [0] * max(0, BENZI - len(benzi))
	else:
		benzi = benziDinText(benzi if isinstance(benzi, str) else "")
	noapte = bool(d.get("noapte"))
	cheie = d.get("presetare")
	if cheie not in CHEI_PRESETARI and cheie != MANUAL:
		cheie = presetareDupaBenzi(benzi, noapte)
	return {"presetare": cheie, "benzi": benzi, "noapte": noapte,
		"nivel": limiteaza(d.get("nivel", 0), NIVEL_MIN, NIVEL_MAX)}


# ---------------------------------------------------------------- posturile cu setarile lor

def cheiePost(ref):
	"""Cheia unui post: primele 10 campuri ale referintei (fara nume si cale), cu litere mici; None la fisiere si
	fluxuri (setarile pe post sunt numai pentru posturi)."""
	if ref is None:
		return None
	text = ref if isinstance(ref, str) else ref.toString()
	parti = text.split(":")
	if len(parti) < 10 or not parti[0].isdigit():
		return None
	if len(parti) > 10 and parti[10].strip():
		return None             # redare din fisier sau flux
	return ":".join(p.lower() for p in parti[:10]) + ":"


class MemoriePosturi(object):
	"""Setarile tinute minte pe post, in FISIER_POSTURI; scrierea se amana PAUZA_SCRIERE_S (ceasul dat de afara)."""

	def __init__(self, cale=FISIER_POSTURI, ceas=time.time):
		self.cale = cale
		self.ceas = ceas
		self.date = None
		self.de_scris_la = None

	def _incarca(self):
		if self.date is not None:
			return
		self.date = {}
		try:
			with io.open(self.cale, "r", encoding="utf-8") as f:
				brut = json.load(f)
		except (IOError, OSError, ValueError):
			return
		posturi = brut.get("posturi") if isinstance(brut, dict) else None
		if not isinstance(posturi, dict):
			return
		for cheie, v in list(posturi.items())[:MAX_POSTURI]:
			s = _curataSetari(v)
			if s is not None and cheiePost(cheie) == cheie:
				s["pus"] = v.get("pus", 0) if isinstance(v.get("pus", 0), (int, float)) else 0
				self.date[cheie] = s

	def ia(self, cheie):
		self._incarca()
		d = self.date.get(cheie) if cheie else None
		return dict(d) if d else None

	def pune(self, cheie, setari):
		if not cheie:
			return False
		self._incarca()
		s = _curataSetari(setari)
		if s is None:
			return False
		s["pus"] = int(self.ceas())
		self.date[cheie] = s
		if len(self.date) > MAX_POSTURI:
			for vechi in sorted(self.date, key=lambda k: self.date[k].get("pus", 0))[:len(self.date) - MAX_POSTURI]:
				del self.date[vechi]
		self.de_scris_la = self.ceas() + PAUZA_SCRIERE_S
		return True

	def sterge(self, cheie):
		self._incarca()
		if cheie in self.date:
			del self.date[cheie]
			self.de_scris_la = self.ceas() + PAUZA_SCRIERE_S
			return True
		return False

	def numar(self):
		self._incarca()
		return len(self.date)

	def scrieDaca(self, fortat=False):
		"""Scrie fisierul daca a trecut pauza de la ultima schimbare (sau acum, cu fortat). -> True daca a scris."""
		if self.de_scris_la is None or (not fortat and self.ceas() < self.de_scris_la):
			return False
		self.de_scris_la = None
		text = json.dumps({"versiune": 1, "posturi": self.date}, ensure_ascii=False, sort_keys=True, indent=0)
		nou = self.cale + ".nou"
		try:
			with io.open(nou, "w", encoding="utf-8") as f:
				f.write(text)
			os.replace(nou, self.cale)
			return True
		except (IOError, OSError) as e:
			_jurnal("fisierul posturilor nu s-a scris: %s" % e)
			return False


def memorie():
	if _STARE["memorie"] is None:
		_STARE["memorie"] = MemoriePosturi()
	return _STARE["memorie"]


# ---------------------------------------------------------------- motorul

def motor():
	"""eHdsEgalizator din nucleu, sau None (imagine fara el, PC)."""
	try:
		from enigma import eHdsEgalizator
	except ImportError:
		return None
	try:
		return eHdsEgalizator.getInstance()
	except Exception as e:
		_jurnal("motorul nu raspunde: %s" % e)
		return None


def _refAcum():
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		return nav.getCurrentlyPlayingServiceReference() if nav else None
	except Exception:
		return None


def postAcum():
	"""(cheia, numele, referinta ca text) postului care merge, sau (None, "", "")."""
	ref = _refAcum()
	if ref is None:
		return None, u"", u""
	nume = u""
	try:
		from ServiceReference import ServiceReference
		nume = ServiceReference(ref).getServiceName() or u""
	except Exception:
		pass
	try:
		text = ref.toString()
	except Exception:
		text = u""
	return cheiePost(text), nume, text


def comutaPePost(v, pePost):
	"""Ce arata ecranul si web-ul dupa „Pentru acest post” comutat: pe Nu, reglajele obisnuite (postul le va uita pe
	ale lui la Pastreaza, iar ce se schimba de acum schimba reglajele obisnuite); pe Da, reglajele de acum raman si devin
	ale postului. `v` = {presetare, benzi, noapte, nivel, ...}; -> dictionar nou, cu „pe_post”."""
	rez = dict(v, benzi=list(v.get("benzi") or [0] * BENZI))
	if not pePost:
		g = setariGlobale()
		rez.update(presetare=g["presetare"], benzi=list(g["benzi"]), noapte=g["noapte"], nivel=g["nivel"])
	rez["pe_post"] = bool(pePost)
	return rez


def setariEfective(cheie=None):
	"""Setarile postului `cheie` daca le are, altfel cele globale; cu „pe_post” True/False."""
	d = memorie().ia(cheie) if cheie else None
	if d:
		d["pe_post"] = True
		return d
	g = setariGlobale()
	g["pe_post"] = False
	return g


def trimiteLaMotor(setari, m=None):
	"""Benzile, Noapte, nivelul, volumul si placa -> motor (fara „pornit”)."""
	m = m if m is not None else motor()
	if m is None:
		return False
	from Components.config import config
	c = config.hds_egalizator
	for i, v in enumerate(setari["benzi"]):
		m.setBanda(i, float(v))
	m.setNoapte(1 if setari["noapte"] else 0)
	m.setNivel(float(setari["nivel"]))
	m.setVolumAici(VOLUM_MOTOR.get(c.volum.value, 0))
	m.setPlacaAlsa(c.placa.value or "default")
	# un motor mai vechi (fara canalele TV) nu are aceste doua functii
	if hasattr(m, "setPotrivireTv"):
		m.setPotrivireTv(limiteaza(c.potrivire_tv.value, POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX))
	if hasattr(m, "setTv"):
		m.setTv(1 if c.tv.value else 0)
	return True


def aplica(cheie=None, faraPost=False):
	"""Pune in motor setarile postului de acum (sau `cheie`) si „pornit”. Se cheama la pornire, la evStart si dupa
	orice schimbare."""
	initConfig()
	m = motor()
	if m is None:
		return False
	_legaMotorul(m)
	if cheie is None and not faraPost:
		cheie = postAcum()[0]
	from Components.config import config
	trimiteLaMotor(setariEfective(cheie), m)
	m.setPornit(1 if config.hds_egalizator.pornit.value else 0)
	return True


# ---------------------------------------------------------------- schimbarile (ecranul si web-ul)

def seteaza(pornit=None, presetare_=None, benzi=None, noapte=None, nivel=None, pePost=None, volum=None, placa=None,
		salveaza=True, cheie=None, tv=None, potrivireTv=None):
	"""Schimba setarile; ce nu e dat ramane. `pePost` True = setarile se tin pentru postul de acum (cheie), False =
	postul uita setarile lui (merg cele globale). O presetare pune benzile si Noapte; benzile date de mana fac
	presetarea „manual” (sau presetarea care se potriveste). -> setarile efective de dupa."""
	initConfig()
	from Components.config import config, configfile
	c = config.hds_egalizator
	if cheie is None:
		cheie = postAcum()[0]
	mem = memorie()
	peste_post = mem.ia(cheie) is not None if cheie else False
	if pePost is not None and cheie:
		peste_post = bool(pePost)
	# pe Nu se pleaca de la reglajele obisnuite: ale postului nu devin ale tuturor posturilor (numai ce e dat aici)
	s = setariGlobale() if (pePost is False and cheie) else setariEfective(cheie)
	s.pop("pe_post", None)
	if presetare_ is not None and presetare(presetare_):
		p = presetare(presetare_)
		s["presetare"] = p[0]
		s["benzi"] = list(p[2])
		s["noapte"] = bool(p[3])
	if benzi is not None:
		s["benzi"] = [limiteaza(x, DB_MIN, DB_MAX) for x in list(benzi)[:BENZI]] + [0] * max(0, BENZI - len(benzi))
		s["presetare"] = presetareDupaBenzi(s["benzi"], s["noapte"])
	if noapte is not None:
		s["noapte"] = bool(noapte)
		s["presetare"] = presetareDupaBenzi(s["benzi"], s["noapte"])
	if nivel is not None:
		s["nivel"] = limiteaza(nivel, NIVEL_MIN, NIVEL_MAX)
	if pornit is not None:
		c.pornit.value = bool(pornit)
	if volum is not None and volum in VOLUM_ALEGERI:
		c.volum.value = volum
	if placa is not None:
		placa = placa.strip()
		if placa and len(placa) <= 64 and all(ch.isalnum() or ch in ":,_-." for ch in placa):
			c.placa.value = placa
	if tv is not None:
		c.tv.value = bool(tv)
	if potrivireTv is not None:
		p = limiteaza(potrivireTv, POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX)
		c.potrivire_tv.value = str(p - p % POTRIVIRE_TV_PAS if p >= 0 else -((-p) - (-p) % POTRIVIRE_TV_PAS))
	if peste_post and cheie:
		mem.pune(cheie, s)
	else:
		if cheie and pePost is False:
			mem.sterge(cheie)
		c.presetare.value = s["presetare"]
		c.benzi.value = textDinBenzi(s["benzi"])
		c.noapte.value = s["noapte"]
		c.nivel.value = str(s["nivel"])
	if salveaza:
		for el in (c.pornit, c.presetare, c.benzi, c.noapte, c.nivel, c.volum, c.placa, c.tv, c.potrivire_tv):
			el.save()
		configfile.save()
		_scrieMaiTarziu()
	m = motor()
	if m is not None:
		_legaMotorul(m)
		trimiteLaMotor(s, m)
		m.setPornit(1 if c.pornit.value else 0)
	rez = dict(s)
	rez["pe_post"] = bool(peste_post and cheie)
	return rez


def incearca(benzi=None, noapte=None, nivel=None, presetare_=None, pornit=None):
	"""Numai pentru ascultare (ecranul si web-ul, cat reglezi): motorul primeste valorile, nimic nu se salveaza."""
	m = motor()
	if m is None:
		return
	_legaMotorul(m)
	s = setariEfective(postAcum()[0])
	if presetare_ is not None and presetare(presetare_):
		p = presetare(presetare_)
		s["benzi"], s["noapte"] = list(p[2]), bool(p[3])
	if benzi is not None:
		s["benzi"] = list(benzi)
	if noapte is not None:
		s["noapte"] = bool(noapte)
	if nivel is not None:
		s["nivel"] = nivel
	trimiteLaMotor(s, m)
	if pornit is not None:
		m.setPornit(1 if pornit else 0)


def pornesteOpreste(pornit):
	"""Numai „pornit” (salvat), de exemplu din tasta de pe ecranul radio."""
	return seteaza(pornit=bool(pornit))


def _scrieMaiTarziu():
	"""Fisierul posturilor se scrie dupa PAUZA_SCRIERE_S, printr-un ceas enigma2 (pe PC: pe loc, la scrieAcum)."""
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _STARE["ceas"] is None:
		_STARE["ceas"] = eTimer()
		_STARE["ceas"].callback.append(_laCeas)
	_STARE["ceas"].start(int(PAUZA_SCRIERE_S * 1000) + 100, True)


def _laCeas():
	mem = memorie()
	if not mem.scrieDaca():
		if mem.de_scris_la is not None:
			_scrieMaiTarziu()


def scrieAcum():
	return memorie().scrieDaca(fortat=True)


# ---------------------------------------------------------------- starea in cuvinte

def _felPistei():
	try:
		import NavigationInstance
		service = NavigationInstance.instance.getCurrentService()
	except Exception:
		service = None
	if service is None:
		return None, None
	try:
		from Components import HdsSunet
		s = HdsSunet.stare(service=service)
		return s.get("format"), s.get("trimis")
	except Exception:
		return None, None


def felPistei():
	"""(formatul, trimis spre bara de sunet) pistei de acum. HdsSunet.stare citeste /proc/stb/audio: aici cel mult o
	data la FEL_MAX_S pe acelasi serviciu (schimbarea serviciului si evUpdatedInfo o cer din nou)."""
	ref = _refAcum()
	try:
		text = ref.toString() if ref is not None else None
	except Exception:
		text = None
	acum = time.time()
	if text is not None and _FEL["ref"] == text and 0 <= acum - _FEL["t"] < FEL_MAX_S:
		return _FEL["val"]
	val = _felPistei()
	_FEL.update(ref=text, t=acum, val=val)
	return val


def stareMotor():
	m = motor()
	if m is None:
		return None
	try:
		return m.stare()
	except Exception as e:
		_jurnal("starea motorului: %s" % e)
		return None


def textStare(st=None, format_pistei=None, trimis=None):
	"""-> (textul mare, bine: True/False/None, detaliul tehnic mic). `st` = stareMotor() (sau None: fara motor)."""
	if st is None:
		return _t(TEXTE_POST["fara-motor"]), None, u""
	post = st.get("post") or "nimic"
	# un post AAC fara decodor (direct, sau ca motiv al intoarcerii pe placa): acelasi text; un motiv ramas de la o
	# incercare veche langa starea „merge” nu il aduce
	if post == "fara-decodor-aac" or (st.get("motiv") == "fara-decodor-aac" and (post == "esuat" or st.get("stare") == "eroare")):
		return _t(TEXTE_POST["fara-decodor-aac"]), False, u""
	stare = st.get("stare") or "oprit"
	if post in ("da", "proba"):
		if stare == "merge":
			sunet = st.get("codec") or u"MPEG"
			if st.get("debit"):
				sunet += u", " + (_t(TEXT_DEBIT_CAM) % st.get("debit") if st.get("debit_aprox") else u"%d kbit/s" % st.get("debit"))
			if post == "proba":
				text = TEXT_PROBA if st.get("pornit", 1) else TEXT_PROBA_OPRIT
			else:
				text = TEXT_MERGE
			return _t(text) % sunet, True, detaliuTehnic(st)
		if stare == "fara-date":
			return _t(TEXT_FARA_DATE), False, detaliuTehnic(st)
		if stare == "eroare":
			return _t(TEXT_ESUAT) % textMotiv(st.get("motiv")), False, u""
		return _t(TEXT_PORNESTE), None, u""
	if post == "esuat":
		return _t(TEXT_ESUAT) % textMotiv(st.get("motiv")), False, u""
	if post == "format":
		if trimis:
			return _t(TEXTE_POST["trecere"]), False, u""
		return _t(TEXTE_POST["format"]) % (format_pistei or u"AC3"), False, u""
	text = TEXTE_POST.get(post)
	if text is None:
		return _t(TEXT_ESUAT) % _t(MOTIV_NECUNOSCUT), False, u""
	return _t(text), (None if post in ("oprit", "nimic", "pauza") else False), u""


def textMotiv(motiv):
	"""Motivul intoarcerii pe placa, in cuvinte (codul brut ramane numai in „Text brut”)."""
	return _t(TEXTE_MOTIV.get(motiv) or MOTIV_NECUNOSCUT)


def _virgula(v, zecimale=1):
	return (u"%%.%df" % zecimale % v).replace(".", ",")


def detaliuTehnic(st):
	"""Randul mic de sub text: unde se decodeaza, esantionarea, procesorul, intarzierea (fara numele elementelor)."""
	parti = []
	if st.get("decodor"):
		parti.append(_t("decodat în procesor"))
	if st.get("esantionare"):
		parti.append(u"%s kHz" % _virgula(st.get("esantionare") / 1000.0, 1).replace(",0", ""))
	if st.get("procesor") is not None:
		parti.append(_t("procesor %s%% dintr-un nucleu") % _virgula(st.get("procesor", 0.0)))
	if st.get("tampon_ms"):
		parti.append(_t("întârziere %d ms") % int(st.get("tampon_ms", 0) + 100))
	return u", ".join(parti)


# numele pe intelesul oricui al elementelor GStreamer (cele brute raman in „Text brut”)
NUME_DECODOR = {"mpg123audiodec": u"decodor MPEG audio", "avdec_mp2float": u"decodor MPEG audio", "faad": u"decodor AAC",
	"avdec_aac": u"decodor AAC", "avdec_aac_latm": u"decodor AAC", "fdkaacdec": u"decodor AAC"}
NUME_STARE = {"oprit": u"Oprit", "porneste": u"Pornește", "merge": u"Merge", "fara-date": u"Așteaptă sunet de la post",
	"eroare": u"Sunetul s-a întors pe placa de sunet", "proba-gata": u"Proba s-a terminat"}


def _nr(v, zecimale=1):
	return _virgula(v, zecimale).replace("-", u"−")


def randuriTehnice(st, posturi_tinute=0):
	"""Datele tehnice pentru web („Pentru probe și potriviri”), pe randuri [eticheta, valoarea], in cuvinte si unitati;
	pagina e numai in romana, ca celelalte pagini noi."""
	m = st or {}
	rez = []

	def rand(eticheta, valoare):
		if valoare not in (None, u"", ""):
			rez.append([eticheta, valoare])
	stare = m.get("stare")
	rand(u"Starea", NUME_STARE.get(stare, stare))
	if stare == "eroare" and m.get("motiv"):
		rand(u"De ce", textMotiv(m.get("motiv")))
	if m.get("codec"):
		debit = u""
		if m.get("debit"):
			debit = (u", cam %d kbit/s" if m.get("debit_aprox") else u", %d kbit/s") % m.get("debit")
		rand(u"Sunetul postului", m.get("codec") + debit)
	if m.get("decodor"):
		rand(u"Decodorul", NUME_DECODOR.get(m.get("decodor"), u"decodor audio") +
			(u", cadrele LATM trecute prin ADTS" if m.get("latm_prin_adts") else u""))
	if m.get("esantionare"):
		canale = m.get("canale") or 0
		rand(u"Eșantionarea", u"%s kHz, %s" % (_virgula(m["esantionare"] / 1000.0, 1).replace(",0", ""),
			u"mono" if canale == 1 else (u"stereo" if canale == 2 else u"%d canale" % canale)))
	if m.get("procesor") is not None:
		rand(u"Procesorul folosit", u"%s%% dintr-un nucleu" % _nr(m.get("procesor", 0.0)))
	if m.get("tampon_ms"):
		rand(u"Tamponul din fața plăcii", u"%d ms" % int(round(m["tampon_ms"])))
	if m.get("abatere_ppm") is not None and m.get("codec"):
		rand(u"Potrivirea ceasului", u"%s milionimi" % _nr(m["abatere_ppm"], 0))
	if m.get("goluri") is not None and m.get("codec"):
		rand(u"Goluri de sunet", u"%d" % m["goluri"])
	if m.get("castig_inainte_db") is not None and m.get("codec"):
		rand(u"Câștigul scăzut înainte", u"%s dB" % _nr(m["castig_inainte_db"]))
	iesire = m.get("iesire") or u""
	if iesire == u"alsa:default":
		rand(u"Ieșirea", u"placa de sunet a receptorului")
	elif iesire.startswith(u"alsa:"):
		rand(u"Ieșirea", u"placa de sunet „%s” (probă)" % iesire[5:])
	elif iesire.startswith(u"wav:"):
		rand(u"Ieșirea", u"fișier WAV (probă)")
	if m.get("sesiune_tv"):
		rand(u"Sincronul cu imaginea", u"%s ms" % _nr(m.get("sincron_tv_ms", 0.0), 0))
		rand(u"Ceasul imaginii", {1: u"citit de la decodor, în ms", 90: u"citit de la decodor, la 90 kHz"}.get(
			m.get("ceas_imagine"), u"încă necitit"))
		rand(u"Tăceri și aruncări la potrivire", u"%d, %d" % (m.get("taceri_tv", 0), m.get("aruncari_tv", 0)))
	if m.get("ceas_tv"):
		rand(u"Ceasul imaginii la TV (STC)", {u"da": u"driverul îl dă", u"nu": u"driverul nu îl dă"}.get(
			m["ceas_tv"], u"nu s-a putut citi"))
	rand(u"Posturi cu reglaje proprii", u"%d" % (posturi_tinute or 0))
	return rez


def stareCompleta():
	"""Tot ce arata ecranul si web-ul: setarile efective si cele obisnuite, postul, textele, starea motorului."""
	initConfig()
	from Components.config import config
	c = config.hds_egalizator
	cheie, nume, ref = postAcum()
	s = setariEfective(cheie)
	st = stareMotor()
	fmt, trimis = (None, None)
	if st is not None and st.get("post") == "format":
		fmt, trimis = felPistei()
	text, bine, detaliu = textStare(st, fmt, trimis)
	decodoare = None
	m = motor()
	if m is not None:
		try:
			decodoare = m.decodoare()
		except Exception:
			decodoare = None
	g = setariGlobale()
	tinute = memorie().numar()
	return {
		"pornit": bool(c.pornit.value), "presetare": s["presetare"], "nume_presetare": numePresetare(s["presetare"]),
		"benzi": s["benzi"], "noapte": s["noapte"], "nivel": s["nivel"], "pe_post": s["pe_post"],
		"globale": {"presetare": g["presetare"], "benzi": g["benzi"], "noapte": g["noapte"], "nivel": g["nivel"]},
		"volum": c.volum.value, "placa": c.placa.value, "tv": bool(c.tv.value),
		"potrivire_tv": limiteaza(c.potrivire_tv.value, POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX),
		"post": {"cheie": cheie, "nume": nume, "ref": ref},
		"text": text, "bine": bine, "detaliu": detaliu, "motor": st, "decodoare": decodoare,
		"tehnic": randuriTehnice(st, tinute), "posturi_tinute": tinute,
	}


def geometriePanzei(W, H):
	"""Asezarea desenului din ecranul Egalizator (Screens/HdsEgalizator.py) pe o panza W x H: casetele de sus, coloanele,
	randul valorilor (sus .. sus + h_text) si al etichetelor (y_eticheta .. H). Butonul rotund (raza) sta intre ele si
	la +12 / -12 dB nu intra in texte."""
	mare = H >= 500
	g = {"mare": mare, "f_mic": 24 if mare else 17, "f_val": 30 if mare else 20, "f_eticheta": 26 if mare else 18,
		"f_bold": 26 if mare else 18, "h_caseta": 84 if mare else 60, "spatiu": 16, "raza": 17 if mare else 12,
		"w_scala": 84 if mare else 56, "h_text": 40 if mare else 28}
	g["w_caseta"] = (W - 3 * g["spatiu"]) // 4
	g["sus"] = g["h_caseta"] + (24 if mare else 14)
	g["w_col"] = (W - g["w_scala"]) // (BENZI + 1)
	g["y_sus"] = g["sus"] + g["h_text"] + g["raza"] + 4
	g["y_eticheta"] = H - g["h_text"]
	g["y_jos"] = g["y_eticheta"] - g["raza"] - 4
	g["y_zero"] = (g["y_sus"] + g["y_jos"]) // 2
	return g


# ---------------------------------------------------------------- pornirea si evenimentele

def asculta(functie):
	"""functie(cod) la fiecare schimbare de stare a motorului (1 merge, 2 oprit, 3 inapoi pe placa, 4 fara date)."""
	if functie not in _STARE["ascultatori"]:
		_STARE["ascultatori"].append(functie)


def nuMaiAsculta(functie):
	if functie in _STARE["ascultatori"]:
		_STARE["ascultatori"].remove(functie)


def _laSchimbareMotor(cod):
	if cod == 3:
		st = stareMotor() or {}
		_jurnal("sunetul s-a intors pe placa: %s" % st.get("motiv"))
	for f in list(_STARE["ascultatori"]):
		try:
			f(cod)
		except Exception as e:
			_jurnal("ascultator: %s" % e)


def _legaMotorul(m):
	if _STARE["legat_motor"]:
		return
	try:
		m.schimbare.get().append(_laSchimbareMotor)
		_STARE["legat_motor"] = True
	except Exception as e:
		_jurnal("semnalul motorului: %s" % e)


def _laEveniment(ev):
	"""La pornirea fiecarui serviciu (inainte ca PMT-ul sa aleaga pista), motorul primeste setarile postului. La
	evStart si evUpdatedInfo felul pistei se citeste din nou (felPistei)."""
	try:
		from enigma import iPlayableService
		if ev in (iPlayableService.evStart, getattr(iPlayableService, "evUpdatedInfo", iPlayableService.evStart)):
			_FEL["ref"] = None
		if ev != iPlayableService.evStart:
			return
	except Exception:
		return
	try:
		cheie = postAcum()[0]
		if cheie != _STARE["post"]:
			_STARE["post"] = cheie
			m = motor()
			if m is not None:
				trimiteLaMotor(setariEfective(cheie), m)
	except Exception as e:
		_jurnal("la pornirea serviciului: %s" % e)


def _legaNavigarea():
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
	except Exception:
		nav = None
	if nav is not None:
		if _laEveniment not in nav.event:
			nav.event.append(_laEveniment)
		_STARE["nav"] = nav
		return
	_STARE["incercari"] += 1
	if _STARE["incercari"] < 90 and _STARE.get("ceas_nav") is not None:
		_STARE["ceas_nav"].start(2000, True)


def porneste():
	"""La pornirea interfetei (dupa config si inainte de primul serviciu): setarile in motor, legatura la servicii."""
	if _STARE["pornit"]:
		return
	_STARE["pornit"] = True
	initConfig()
	aplica(faraPost=True)
	try:
		from enigma import eTimer
		_STARE["ceas_nav"] = eTimer()
		_STARE["ceas_nav"].callback.append(_legaNavigarea)
		_legaNavigarea()
	except ImportError:
		pass
