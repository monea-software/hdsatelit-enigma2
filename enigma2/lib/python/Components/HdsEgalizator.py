# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEgalizator.py: setarile egalizatorului din procesor si legatura lor cu motorul din nucleu (eHdsEgalizator,
# lib/service/hdsegalizator.cpp). Ecranul: Meniu > Audio > Egalizator (Screens/HdsEgalizator.py); web: /egalizator
# (Plugins/Extensions/HdsWebControl/egalizator_web.py). Amandoua folosesc numai functiile de aici.
#
# Setarile (config.hds_egalizator): pornit (global), presetarea, cele 10 benzi (text "b0,b1,...,b9" in dB, -24..+18),
# modul Noapte, nivelul (potrivirea tariei fata de sunetul placii, -12..+12 dB), volumul (automat / in egalizator / pe
# placa) si placa ALSA (implicit „default”). Presetarile pun benzile si modul Noapte; o banda schimbata de mana face
# presetarea manual. Presetarea Manual se tine separat (benzi, nivel, comprimare si efect), ca sa poata fi rechemata
# dupa incercarea altei presetari. Setarile vechi fara aceasta memorie pornesc de la valorile active, fara pierderi.
#
# Efectele speciale (implicit fara) folosesc acelasi motor; o presetare standard le opreste, Manual le rechema.
# Pe post: un post poate avea setarile lui (presetarea, benzile, Noapte, nivelul, efectul), tinute in FISIER_POSTURI (JSON, cel
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
# Prin placa (numai HiSilicon, sectiunea "egalizatorul placii" de mai jos): cu tv_placa (Nu din fabrica) la canalele TV benzile
# (adunate in 5) le aplica egalizatorul placii de sunet, fara intarziere; motorul nu mai ia sunetul TV (setTv 0), iar
# efectele si comprimarea nu se aud la TV. Egalizatorul placii se opreste la radio, IPTV, filme, la oprirea
# egalizatorului, in standby si la pornirea interfetei (aducerea la zero, ca nimic sa nu ramana pus dupa o cadere).
# Dupa o intoarcere pe placa cu tv-fara-ceas pe HiSilicon, daca imaginea merge dar sunetul placii nu (placa a ramas
# fara pista), serviciul porneste din nou o singura data (reporneste sunetul placii).
#
# Fara motor (nucleu fara eHdsEgalizator, PC) totul merge mai departe fara efect: setarile se tin, iar textul spune ca
# egalizatorul lipseste din programul receptorului. Partea de sus nu importa enigma: se probeaza pe PC.

from __future__ import absolute_import

import io
import json
import os
import re
import threading
import time

BENZI = 10
FRECVENTE = (31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
ETICHETE = ("31 Hz", "63 Hz", "125 Hz", "250 Hz", "500 Hz", "1 kHz", "2 kHz", "4 kHz", "8 kHz", "16 kHz")
DB_MIN = -24
DB_MAX = 18
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
	("noapte", N_("Mod de noapte"), (-4, -3, -1, 0, 1, 2, 2, 1, 0, -1), True),
)
NUME_MANUAL = N_("Manual")
CHEI_PRESETARI = tuple(p[0] for p in PRESETARI)

# Ordinea este aceeasi cu identificatorii numerici din hdsegalizator_dsp.h.
EFECTE = (
	("fara", N_("Fără efecte")), ("ecou", N_("Ecou")), ("ping-pong", N_("Ecou dublu (ping-pong)")),
	("camera", N_("Reverb cameră")), ("sala", N_("Reverb sală")), ("catedrala", N_("Reverb catedrală")),
	("stadion", N_("Stadion")), ("chorus", N_("Cor (chorus)")), ("flanger", N_("Flanger")),
	("phaser", N_("Phaser")), ("tremolo", N_("Tremolo")), ("vibrato", N_("Vibrato")),
	("stereo", N_("Stereo lărgit")), ("radio", N_("Radio vechi")), ("telefon", N_("Telefon")),
	("karaoke", N_("Fără voce (karaoke)")),
)
CHEI_EFECTE = tuple(e[0] for e in EFECTE)


def curataEfect(cheie):
	return cheie if isinstance(cheie, str) and cheie in CHEI_EFECTE else "fara"


def numeEfecte():
	return [(cheie, _t(nume)) for cheie, nume in EFECTE]


def numeEfect(cheie):
	return _t(EFECTE[CHEI_EFECTE.index(curataEfect(cheie))][1])

# ce se intampla cu postul de acum (motivul dat de motor) -> textul pe ecran
TEXTE_POST = {
	"oprit": N_("Egalizatorul e oprit. Sunetul merge ca de obicei, prin placa de sunet."),
	"pauza": N_("Pauză. Sunetul revine cu egalizator când pornești din nou."),
	"tv": N_("La canalele TV egalizatorul e oprit din setări. Sunetul merge prin placa de sunet."),
	"tv-oprit-pornire": N_("Proba egalizatorului la TV a eșuat pe acest model. Sunetul merge prin placa de sunet. Nu mai încearcă până la repornirea interfeței."),
	"inregistrare": N_("La înregistrări și la pauza cu reluare (timeshift) egalizatorul nu lucrează. Sunetul merge prin placa de sunet."),
	"format": N_("Postul acesta are sunet %s. Egalizatorul lucrează la posturile cu sunet MPEG (MP2)."),
	"trecere": N_("Sunetul pleacă neschimbat spre bara de sunet: egalizatorul, volumul și modul de noapte le reglezi din bara de sunet."),
	# posturile AAC pe receptoarele fara decodorul AAC (faad, numai unde e libfaad2 pentru DAB+); sunetul merge prin placa
	"fara-decodor-aac": N_("La acest post (AAC) egalizatorul nu e disponibil din motive de licențiere a brevetelor AAC."),
	# posturile cu HE-AAC semnalat (SBR/PS): decodorul din imagine e aprobat numai pentru AAC-LC; sunetul merge prin placa
	"aac-he": N_("La acest post (HE-AAC) egalizatorul nu e disponibil din motive de licențiere a brevetelor HE-AAC."),
	"fara-decodor-mpeg": N_("Egalizatorul nu poate porni: receptorul nu are decodorul MPEG audio."),
	"fara-gstreamer": N_("Egalizatorul nu poate porni: lipsește decodarea sunetului în procesor (GStreamer)."),
	"fara-alsa": N_("Egalizatorul nu poate porni: placa de sunet nu se poate folosi din procesor."),
	# placile fara ceasul placii HiSilicon (Broadcom, Vu+): drumul din procesor nu se aude acolo, deci radioul si fluxurile
	# raman pe placa (hdsegalizator.cpp, procesorNeprobat); acelasi text ca fara-alsa, deja tradus
	"placa-neprobata": N_("Egalizatorul nu poate porni: placa de sunet nu se poate folosi din procesor."),
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
	"aac-he": N_("postul folosește HE-AAC"),
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
# canal TV: placa canta sunetul din primul cadru pana preia egalizatorul (stare: preluat 0; lib/service/hdsegalizator.h)
TEXT_TV_PE_PLACA = N_("Canal TV: sunetul pornește pe placa de sunet, fără întârziere, și trece în egalizator după o clipă.")
TEXT_FARA_DATE = N_("Postul nu mai trimite sunet. Egalizatorul așteaptă.")
TEXT_PRIN_PLACA = N_("La canalele TV egalizatorul îl aplică placa de sunet, la fiecare canal și fără întârziere, în 5 benzi. Efectele speciale și comprimarea se aud numai la radio.")

_STARE = {"memorie": None, "nav": None, "ceas": None, "incercari": 0, "pornit": False, "ascultatori": [],
	"post": None, "legat_motor": False, "placa": None, "placa_exista": None, "proba": None, "repornit_ref": None,
	"verifica_muta": None, "standby": False}
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
	"""Textul "0,2,-3,..." -> lista de 10 intregi in -24..+18; lipsurile si gunoiul devin 0."""
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
	c.efect = ConfigSelection(default="fara", choices=numeEfecte())
	# Memoria presetarii omului este separata de reglajele active; JSON gol = setari vechi.
	c.manual = ConfigText(default="", fixed_size=False)
	# nivelul ca text („-3”): ConfigSelection cu alegerile lui, citit si scris numai prin limiteaza()/str()
	c.nivel = ConfigSelection(default="0", choices=[(str(v), textDb(v)) for v in range(NIVEL_MIN, NIVEL_MAX + 1)])
	c.volum = ConfigSelection(default="auto", choices=[
		("auto", _t("Automat")), ("aici", _t("În egalizator")), ("placa", _t("Pe placa de sunet"))])
	c.placa = ConfigText(default="default", fixed_size=False)
	# canalele TV: egalizatorul si la ele (sunetul tinut dupa imagine), cu potrivirea fata de imagine
	c.tv = ConfigYesNo(default=True)
	c.potrivire_tv = ConfigSelection(default="0", choices=alegeriPotrivireTv())
	# HiSilicon: la canalele TV egalizatorul placii (5 benzi, fara intarziere) in locul drumului prin procesor
	c.tv_placa = ConfigYesNo(default=False)


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
		"nivel": limiteaza(c.nivel.value, NIVEL_MIN, NIVEL_MAX), "efect": curataEfect(c.efect.value)}


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
	rez = {"presetare": cheie, "benzi": benzi, "noapte": noapte,
		"nivel": limiteaza(d.get("nivel", 0), NIVEL_MIN, NIVEL_MAX), "efect": curataEfect(d.get("efect"))}
	if rez["efect"] != "fara":
		rez["presetare"] = MANUAL
	if isinstance(d.get("manual"), dict):
		m = d["manual"]
		rez["manual"] = _curataSetari({k: m[k] for k in ("benzi", "noapte", "nivel", "efect") if k in m})
	return rez


def reglajManual(pePost=False, cheie=None):
	"""Presetarea omului pentru domeniul ales; la setari vechi se pastreaza toate valorile active."""
	from Components.config import config
	if pePost:
		s = memorie().ia(cheie if cheie is not None else postAcum()[0])
		if s:
			return _curataSetari(s.get("manual") or s)
	try:
		m = json.loads(config.hds_egalizator.manual.value)
	except (TypeError, ValueError):
		m = None
	return _curataSetari(m) if isinstance(m, dict) else setariGlobale()


# ---------------------------------------------------------------- posturile cu setarile lor

def cheiePost(ref):
	"""Cheia unui post: primele 10 campuri ale referintei (fara nume si cale), cu litere mici; None la fisiere si
	fluxuri (setarile pe post sunt numai pentru posturi). Un post de radio pe flux cu numere proprii (locurile adaugate de extensii)
	e un post; un rand facut de mana, cu numerele zero, nu: toate ar avea aceeasi cheie."""
	if ref is None:
		return None
	text = ref if isinstance(ref, str) else ref.toString()
	parti = text.split(":")
	if len(parti) < 10 or not parti[0].isdigit():
		return None
	if len(parti) > 10 and parti[10].strip():
		if parti[2].lower() != "2" or not any(p.strip("0") for p in parti[3:7]):
			return None         # redare din fisier sau flux
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
		rez.update(presetare=g["presetare"], benzi=list(g["benzi"]), noapte=g["noapte"], nivel=g["nivel"], efect=g["efect"])
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
	"""Benzile, Noapte, nivelul, efectul, volumul si placa -> motor (fara pornit)."""
	m = m if m is not None else motor()
	if m is None:
		return False
	from Components.config import config
	c = config.hds_egalizator
	for i, v in enumerate(setari["benzi"]):
		m.setBanda(i, float(v))
	m.setNoapte(1 if setari["noapte"] else 0)
	m.setNivel(float(setari["nivel"]))
	if hasattr(m, "setEfect"):
		m.setEfect(CHEI_EFECTE.index(curataEfect(setari.get("efect"))))
	m.setVolumAici(VOLUM_MOTOR.get(c.volum.value, 0))
	m.setPlacaAlsa(c.placa.value or "default")
	# un motor mai vechi (fara canalele TV) nu are aceste doua functii
	if hasattr(m, "setPotrivireTv"):
		m.setPotrivireTv(limiteaza(c.potrivire_tv.value, POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX))
	if hasattr(m, "setTv"):
		# setari["tv"]: proba de pe ecran (incearca), altfel setarea salvata
		tv = setari.get("tv")
		tv = c.tv.value if tv is None else tv
		if _prinPlaca(setari):
			tv = False
		m.setTv(1 if tv else 0)
	return True


# ---------------------------------------------------------------- egalizatorul placii: comenzile si firul
#
# De ce: la canalele TV pe HiSilicon sunetul ajunge in procesor numai cu -60..+40 ms inaintea imaginii aratate (placa isi
# porneste sunetul cu ~50 ms in tampon), iar drumul prin decodare, ALSA si placa cere peste 100 ms; asa egalizatorul din
# procesor se prinde numai la o parte din schimbarile de canal (masurat pe SF8008, lucrarea EGZ7). Placa are insa un
# egalizator parametric pe fiecare iesire (PEQ, 5 benzi), aplicat direct sunetului ei: fara intarziere si fara sincron.
#
# Cum: cele 10 benzi ale omului se aduna in 5 (perechi de benzi alaturate: raft jos, trei clopote, raft sus, +/-15 dB;
# toata curba coboara cu cea mai mare ridicare, ca sunetul sa nu se taie), apoi se scriu pe iesirile HDMI0, DAC0 si
# SPDIF0 prin comenzile textului /proc/msp/sound0 ("HDMI0 peq band0 freq 125", "... gain -3.500", "HDMI0 peq on") si se
# citesc inapoi din acelasi fisier. Scrierile le face un fir separat (Lucrator); firul interfetei numai cere starea
# dorita (cere()), ultima cerere castiga. "Oprit" pune benzile din fabrica si opreste PEQ, ca nimic sa nu ramana pus.

PEQ_PROC = "/proc/msp/sound0"
PEQ_SYNC = "/proc/msp/sync00"
PEQ_PORTURI = ("HDMI0", "DAC0", "SPDIF0")
PEQ_BENZI = 5
PEQ_CASTIG_MAX = 15.0
# benzile din fabrica ale driverului (citite pe SF8008): clopote, Q 2.0, 0 dB
PEQ_FABRICA = (("PK", 120, 2.0, 0.0), ("PK", 500, 2.0, 0.0), ("PK", 1500, 2.0, 0.0), ("PK", 5000, 2.0, 0.0),
	("PK", 10000, 2.0, 0.0))
# cele 10 benzi ale egalizatorului (31 Hz .. 16 kHz) in perechi -> (tip, frecventa, Q) pe placa
PEQ_PERECHI = (("LS", 63, 0.7), ("PK", 177, 0.7), ("PK", 707, 0.7), ("PK", 2828, 0.7), ("HS", 8000, 0.7))


def peqExista(proc=PEQ_PROC, sync=PEQ_SYNC):
	"""Receptor HiSilicon cu egalizatorul placii: sincronul placii si fisierul sunetului."""
	return os.path.exists(sync) and os.path.exists(proc)


def peqBenzi(benzi):
	"""10 benzi (dB) -> 5 benzi de placa [(tip, frecventa, Q, castig dB)]: media fiecarei perechi, toata curba coborata
	cu cea mai mare ridicare (fara taiere), apoi in +/-PEQ_CASTIG_MAX."""
	b = [float(x) for x in list(benzi)[:10]] + [0.0] * max(0, 10 - len(benzi))
	medii = [(b[2 * i] + b[2 * i + 1]) / 2.0 for i in range(PEQ_BENZI)]
	sus = max(0.0, max(medii))
	rez = []
	for i, (tip, f, q) in enumerate(PEQ_PERECHI):
		g = max(-PEQ_CASTIG_MAX, min(PEQ_CASTIG_MAX, medii[i] - sus))
		rez.append((tip, f, q, round(g * 2.0) / 2.0))
	return rez


def peqTextCastig(g):
	"""Castigul cum il citeste driverul: intreg si exact trei zecimale (5 -> "5.000", -3.5 -> "-3.500")."""
	m = int(round(abs(g) * 1000.0))
	return u"%s%d.%03d" % (u"-" if g < 0 and m else u"", m // 1000, m % 1000)


def peqComenzi(benzi5):
	"""Comenzile pentru o stare: benzi5 = lista de 5 sau None (oprit: benzile din fabrica, apoi PEQ oprit). Frecventa si Q
	inaintea tipului, ca limitele tipului (raftul jos pana la 4 kHz, cel sus de la 4 kHz) sa fie respectate."""
	rez = []
	tinta = benzi5 if benzi5 is not None else PEQ_FABRICA
	for port in PEQ_PORTURI:
		for i, (tip, f, q, g) in enumerate(tinta):
			rez.append(u"%s peq band%d type PK" % (port, i))
			rez.append(u"%s peq band%d freq %d" % (port, i, int(f)))
			rez.append(u"%s peq band%d Q %.1f" % (port, i, float(q)))
			rez.append(u"%s peq band%d type %s" % (port, i, tip))
			rez.append(u"%s peq band%d gain %s" % (port, i, peqTextCastig(g)))
		rez.append(u"%s peq %s" % (port, u"on" if benzi5 is not None else u"off"))
	return rez


_PEQ_BANDA = re.compile(r"Band(\d)\((\w+),(\d+)Hz,(-?\d+)\.(-?\d+)dB,(\d+)\.(\d)Q\)")


def peqCitesteInapoi(text):
	"""Textul lui /proc/msp/sound0 -> {port: [(tip, frecventa, Q, castig)] sau None (PEQ oprit pe port)}. Driverul scrie
	castigul negativ ca "-7.-500dB"."""
	rez = {}
	port = None
	for rand in text.splitlines():
		m = re.match(r"^(\w+): Status", rand)
		if m:
			port = m.group(1)
			if port in PEQ_PORTURI:
				rez[port] = None
			continue
		if port in PEQ_PORTURI and ("PEQ Attr" in rand or rez.get(port) is not None):
			for b in _PEQ_BANDA.finditer(rand):
				if rez.get(port) is None:
					rez[port] = []
				intreg, mii = int(b.group(4)), abs(int(b.group(5)))
				neg = b.group(4).startswith("-") or b.group(5).startswith("-")
				g = abs(intreg) + mii / 1000.0
				rez[port].append((b.group(2), int(b.group(3)), int(b.group(6)) + int(b.group(7)) / 10.0, -g if neg else g))
	return rez


def peqPotrivit(citit, benzi5):
	"""Citirea inapoi arata exact starea ceruta pe toate porturile."""
	for port in PEQ_PORTURI:
		v = citit.get(port, "lipsa")
		if benzi5 is None:
			if v is not None:
				return False
		elif v is None or v == "lipsa" or len(v) != len(benzi5):
			return False
		else:
			for (t1, f1, q1, g1), (t2, f2, q2, g2) in zip(v, benzi5):
				if t1 != t2 or f1 != int(f2) or abs(q1 - q2) > 0.05 or abs(g1 - g2) > 0.01:
					return False
	return True


def peqCitesteFisier(proc=PEQ_PROC):
	try:
		with open(proc) as f:
			return peqCitesteInapoi(f.read())
	except (IOError, OSError):
		return {}


def peqScrie(benzi5, proc=PEQ_PROC):
	"""Scrie starea (benzi5 sau None) si o citeste inapoi. -> (potrivit, comenzi refuzate)."""
	refuzate = 0
	for c in peqComenzi(benzi5):
		try:
			with open(proc, "w") as f:
				f.write(c + "\n")
		except (IOError, OSError):
			refuzate += 1
	try:
		with open(proc) as f:
			text = f.read()
	except (IOError, OSError):
		text = ""
	return peqPotrivit(peqCitesteInapoi(text), benzi5), refuzate


class LucratorPlaca(object):
	"""Firul care scrie in placa. cere(benzi5 sau None): starea dorita; ultima cerere castiga, aceeasi stare nu se scrie
	din nou. `jurnal(text)` primeste rezultatul fiecarei scrieri."""

	def __init__(self, proc=PEQ_PROC, jurnal=None, scriitor=None):
		self.proc = proc
		self.jurnal = jurnal or (lambda t: None)
		self.scriitor = scriitor or peqScrie
		self.cv = threading.Condition()
		self.dorit = None
		self.are_cerere = False
		self.scris = "nimic"
		self.fir = None
		self.cerute = 0
		self.facute = 0

	def cere(self, benzi5, fortat=False):
		with self.cv:
			stare = None if benzi5 is None else tuple(benzi5)
			if not fortat and stare == self.scris and not self.are_cerere:
				return
			self.dorit = stare
			self.are_cerere = True
			self.cerute += 1
			if self.fir is None:
				self.fir = threading.Thread(target=self._bucla, name="hds-egal-placa")
				self.fir.daemon = True
				self.fir.start()
			self.cv.notify()

	def curataLaPornire(self):
		"""La pornirea interfetei: daca placa a ramas cu PEQ pornit (dupa o cadere), il aduce la zero; altfel nu scrie."""
		with self.cv:
			self.dorit = "curata"
			self.are_cerere = True
			self.cerute += 1
			if self.fir is None:
				self.fir = threading.Thread(target=self._bucla, name="hds-egal-placa")
				self.fir.daemon = True
				self.fir.start()
			self.cv.notify()

	def asteapta(self, timp=5.0):
		"""Numai pentru probe: pana se scrie ultima cerere."""
		with self.cv:
			if self.facute < self.cerute:
				self.cv.wait_for(lambda: self.facute >= self.cerute, timp)

	def _bucla(self):
		while True:
			with self.cv:
				while not self.are_cerere:
					self.cv.wait()
				stare = self.dorit
				self.are_cerere = False
				numar = self.cerute
			if stare == "curata":
				stare = None
				citit = peqCitesteFisier(self.proc)
				# numai un port cu PEQ pornit se curata; un port care lipseste inca din fisier nu e pus
				if not any(citit.get(p) for p in PEQ_PORTURI):
					with self.cv:
						self.scris = None
						self.facute = numar
						self.cv.notify_all()
					continue
			ok, refuzate = self.scriitor(None if stare is None else list(stare), self.proc)
			with self.cv:
				self.scris = stare
				self.facute = numar
				self.cv.notify_all()
			if stare is None:
				self.jurnal("egalizatorul placii oprit (benzile din fabrica)%s" % ("" if ok else ", citirea inapoi nu se potriveste"))
			else:
				self.jurnal("egalizatorul placii: %s%s%s" % (", ".join("%s %d Hz %s dB" % (t, f, peqTextCastig(g)) for t, f, q, g in stare),
					"" if ok else "; citirea inapoi nu se potriveste", "; %d comenzi refuzate" % refuzate if refuzate else ""))


def peqPlacaMuta(sync=PEQ_SYNC):
	"""Dupa intoarcerea pe placa: imaginea merge (VidLocalTime > 0) dar sunetul placii nu (AudLocalTime <= 0)."""
	try:
		with open(sync) as f:
			t = f.read()
	except (IOError, OSError):
		return False
	v = re.search(r"VidLocalTime\s*:(-?\d+)", t)
	a = re.search(r"AudLocalTime\s*:(-?\d+)", t)
	return bool(v and a and int(v.group(1)) > 0 and int(a.group(1)) <= 0)


# ---------------------------------------------------------------- egalizatorul placii (HiSilicon, canalele TV)

def placaExista():
	"""Receptor HiSilicon cu egalizatorul placii pe iesiri (citit o singura data)."""
	if _STARE["placa_exista"] is None:
		_STARE["placa_exista"] = peqExista()
	return _STARE["placa_exista"]


def _prinPlaca(setari=None):
	"""Optiunea "prin placa" e aleasa (sau incercata pe ecran) pe un receptor care o are."""
	from Components.config import config
	c = config.hds_egalizator
	v = (setari or {}).get("tv_placa")
	return bool(placaExista() and (c.tv_placa.value if v is None else v))


def _tvDirect(ref=None):
	"""Postul de acum e un canal TV din tuner (nu radio, nu IPTV, nu film sau inregistrare)."""
	ref = _refAcum() if ref is None else ref
	if ref is None:
		return False
	try:
		parti = ref.toString().split(":")
		tip, fel = int(parti[0]), int(parti[2], 16)
		cale = parti[10] if len(parti) > 10 else ""
	except Exception:
		return False
	return tip == 1 and fel not in (2, 10) and not cale


def _eRadio(ref):
	try:
		parti = ref.toString().split(":")
		return int(parti[0]) == 1 and int(parti[2], 16) in (2, 10)
	except Exception:
		return False


def _lucratorPlaca():
	if _STARE["placa"] is None:
		_STARE["placa"] = LucratorPlaca(jurnal=_jurnal)
	return _STARE["placa"]


def actualizeazaPlaca(setari=None, pornit=None, fortat=False):
	"""Egalizatorul placii: pus cu benzile efective cand egalizatorul e pornit, optiunea "prin placa" aleasa si merge un
	canal TV din tuner (nu in standby); altfel oprit. Scrierile le face firul Lucrator."""
	if not placaExista():
		return
	from Components.config import config
	c = config.hds_egalizator
	setari = setari if setari is not None else (_STARE["proba"] or setariEfective(postAcum()[0]))
	pornit = c.pornit.value if pornit is None else pornit
	pus = bool(pornit and _prinPlaca(setari) and _tvDirect() and not _STARE["standby"])
	l = _lucratorPlaca()
	if not pus and ((l.scris in (None, "nimic") and not l.are_cerere) or (l.are_cerere and l.dorit == "curata")):
		# oprit deja, niciodata pus sau curatarea de la pornire inca in asteptare (ea hotaraste daca e ceva de oprit):
		# cu optiunea pe Nu placa nu primeste nicio scriere
		return
	l.cere(peqBenzi(setari["benzi"]) if pus else None, fortat=fortat)


def renuntaLaProba():
	"""Ecranul sau web-ul renunta la proba nesalvata: egalizatorul placii revine la setarile pastrate."""
	_STARE["proba"] = None
	actualizeazaPlaca()


def _laStandby(intra):
	_STARE["standby"] = bool(intra)
	actualizeazaPlaca()


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
	_STARE["proba"] = None
	trimiteLaMotor(setariEfective(cheie), m)
	m.setPornit(1 if config.hds_egalizator.pornit.value else 0)
	actualizeazaPlaca(setariEfective(cheie))
	return True


# ---------------------------------------------------------------- schimbarile (ecranul si web-ul)

def seteaza(pornit=None, presetare_=None, benzi=None, noapte=None, nivel=None, pePost=None, volum=None, placa=None,
		salveaza=True, cheie=None, tv=None, potrivireTv=None, salveazaManual=False, efect=None, tvPlaca=None):
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
	# Inainte de schimbarea presetarii se retine si un reglaj manual din formatul vechi.
	manual = reglajManual(peste_post, cheie)
	if presetare_ == MANUAL and benzi is None:
		s.update(presetare=MANUAL, benzi=list(manual["benzi"]), noapte=manual["noapte"], nivel=manual["nivel"], efect=manual["efect"])
	if presetare_ is not None and presetare(presetare_):
		p = presetare(presetare_)
		s["presetare"] = p[0]
		s["benzi"] = list(p[2])
		s["noapte"] = bool(p[3])
		s["efect"] = "fara"
	if benzi is not None:
		s["benzi"] = [limiteaza(x, DB_MIN, DB_MAX) for x in list(benzi)[:BENZI]] + [0] * max(0, BENZI - len(benzi))
		s["presetare"] = presetareDupaBenzi(s["benzi"], s["noapte"])
	if noapte is not None:
		s["noapte"] = bool(noapte)
		s["presetare"] = presetareDupaBenzi(s["benzi"], s["noapte"])
	if nivel is not None:
		s["nivel"] = limiteaza(nivel, NIVEL_MIN, NIVEL_MAX)
	if efect is not None:
		nou = curataEfect(efect)
		if nou != s["efect"]:
			s["presetare"] = MANUAL
		s["efect"] = nou
	# Un efect ales ramane un reglaj Manual si dupa mutarea unei benzi.
	if s["efect"] != "fara":
		s["presetare"] = MANUAL
	if salveazaManual or (presetare_ == MANUAL and benzi is not None):
		s["presetare"] = MANUAL
	if salveazaManual or (s["presetare"] == MANUAL and (benzi is not None or noapte is not None or nivel is not None or efect is not None)):
		manual = {k: s[k] for k in ("presetare", "benzi", "noapte", "nivel", "efect")}
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
	if tvPlaca is not None:
		c.tv_placa.value = bool(tvPlaca)
	if potrivireTv is not None:
		p = limiteaza(potrivireTv, POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX)
		c.potrivire_tv.value = str(p - p % POTRIVIRE_TV_PAS if p >= 0 else -((-p) - (-p) % POTRIVIRE_TV_PAS))
	if peste_post and cheie:
		s["manual"] = manual
		mem.pune(cheie, s)
	else:
		if cheie and pePost is False:
			mem.sterge(cheie)
		c.presetare.value = s["presetare"]
		c.benzi.value = textDinBenzi(s["benzi"])
		c.noapte.value = s["noapte"]
		c.nivel.value = str(s["nivel"])
		c.efect.value = s["efect"]
		c.manual.value = json.dumps(manual, ensure_ascii=False, sort_keys=True)
	if salveaza:
		for el in (c.pornit, c.presetare, c.benzi, c.noapte, c.nivel, c.efect, c.manual, c.volum, c.placa, c.tv, c.potrivire_tv,
				c.tv_placa):
			el.save()
		configfile.save()
		_scrieMaiTarziu()
	_STARE["proba"] = None
	m = motor()
	if m is not None:
		_legaMotorul(m)
		trimiteLaMotor(s, m)
		m.setPornit(1 if c.pornit.value else 0)
	actualizeazaPlaca(s)
	rez = dict(s)
	rez["pe_post"] = bool(peste_post and cheie)
	return rez


def incearca(benzi=None, noapte=None, nivel=None, presetare_=None, pornit=None, pePost=None, efect=None, tv=None,
		tvPlaca=None):
	"""Numai pentru ascultare (ecranul si web-ul, cat reglezi): motorul primeste valorile, nimic nu se salveaza.
	tv: egalizatorul si la canalele TV (caseta La canalele TV de pe ecran), tot numai pentru ascultare."""
	m = motor()
	if m is None:
		return
	_legaMotorul(m)
	s = setariEfective(postAcum()[0])
	if presetare_ == MANUAL:
		s.update(reglajManual(s["pe_post"] if pePost is None else pePost))
	if presetare_ is not None and presetare(presetare_):
		p = presetare(presetare_)
		s["benzi"], s["noapte"] = list(p[2]), bool(p[3])
		s["efect"] = "fara"
	if benzi is not None:
		s["benzi"] = list(benzi)
	if noapte is not None:
		s["noapte"] = bool(noapte)
	if nivel is not None:
		s["nivel"] = nivel
	if efect is not None:
		s["efect"] = curataEfect(efect)
	if tv is not None:
		s["tv"] = bool(tv)
	if tvPlaca is not None:
		s["tv_placa"] = bool(tvPlaca)
	_STARE["proba"] = s
	trimiteLaMotor(s, m)
	if pornit is not None:
		m.setPornit(1 if pornit else 0)
	from Components.config import config
	actualizeazaPlaca(s, config.hds_egalizator.pornit.value if pornit is None else pornit)


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


def _textStare(st=None, format_pistei=None, trimis=None):
	"""-> (textul mare, bine: True/False/None, detaliul tehnic mic). `st` = stareMotor() (sau None: fara motor)."""
	if st is None:
		return _t(TEXTE_POST["fara-motor"]), None, u""
	post = st.get("post") or "nimic"
	# un post AAC fara decodor (direct, sau ca motiv al intoarcerii pe placa): acelasi text; un motiv ramas de la o
	# incercare veche langa starea „merge” nu il aduce
	if post == "fara-decodor-aac" or (st.get("motiv") == "fara-decodor-aac" and (post == "esuat" or st.get("stare") == "eroare")):
		return _t(TEXTE_POST["fara-decodor-aac"]), False, u""
	# HE-AAC semnalat (motorul il refuza inainte de decodare sau cand postul trece pe el): textul lui, la fel
	if st.get("motiv") == "aac-he" and (post == "esuat" or st.get("stare") == "eroare"):
		return _t(TEXTE_POST["aac-he"]), False, u""
	stare = st.get("stare") or "oprit"
	if post in ("da", "proba"):
		if stare == "merge" and st.get("sesiune_tv") and st.get("preluat") == 0:
			return _t(TEXT_TV_PE_PLACA), None, detaliuTehnic(st)
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


def textStare(st=None, format_pistei=None, trimis=None):
	st_ = stareMotor() if st is None else st
	if st_ and st_.get("post") == "tv" and _prinPlacaActiv():
		return _t(TEXT_PRIN_PLACA), True, u""
	text, bine, detaliu = _textStare(st, format_pistei, trimis)
	if bine is not True:
		text += u" " + _t("Efectele speciale nu se aud aici.")
	return text, bine, detaliu


def textMotiv(motiv):
	"""Motivul intoarcerii pe placa, in cuvinte (codul brut ramane numai in „Text brut”)."""
	return _t(TEXTE_MOTIV.get(motiv) or MOTIV_NECUNOSCUT)


def _prinPlacaActiv():
	"""Egalizatorul pornit, optiunea "prin placa" aleasa si un canal TV din tuner: sunetul TV il egalizeaza placa."""
	try:
		from Components.config import config
		return bool(config.hds_egalizator.pornit.value and _prinPlaca() and _tvDirect())
	except Exception:
		return False


def avertizareTv(st=None):
	"""Aceeasi explicatie pe televizor si in web, fara schimbarea alegerii omului."""
	st = stareMotor() if st is None else st
	if st and st.get("tv_de_proba"):
		return _t("Pe acest model, egalizatorul la TV este de probă. La primul eșec, sunetul revine imediat pe placa de sunet și proba se oprește până la repornirea interfeței.")
	return ""


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
		if m.get("ceas_imagine_sursa") == "placa":
			# HiSilicon: ceasul imaginii aratate din sincronul placii; PTS-ul decodorului ramane numai pentru comparatie
			rand(u"Ceasul imaginii", u"din sincronul plăcii, în ms" if m.get("ceas_imagine") else u"încă necitit")
			if m.get("ceas_decodor_fata_de_placa_ms") is not None:
				rand(u"PTS-ul decodorului față de imagine", u"%s ms" % _nr(m["ceas_decodor_fata_de_placa_ms"], 0))
		else:
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
	from Components.HdsRadioDate import ref_publica
	ref = ref_publica(ref)
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
		"efect": s["efect"], "nume_efect": numeEfect(s["efect"]), "efecte": numeEfecte(),
		"manual": reglajManual(s["pe_post"], cheie), "manual_global": reglajManual(False),
		"globale": {"presetare": g["presetare"], "benzi": g["benzi"], "noapte": g["noapte"], "nivel": g["nivel"], "efect": g["efect"]},
		"volum": c.volum.value, "placa": c.placa.value, "tv": bool(c.tv.value),
		"tv_placa": bool(c.tv_placa.value), "placa_peq": placaExista(),
		"potrivire_tv": limiteaza(c.potrivire_tv.value, POTRIVIRE_TV_MIN, POTRIVIRE_TV_MAX),
		"post": {"cheie": cheie, "nume": nume, "ref": ref},
		"text": text, "bine": bine, "detaliu": detaliu, "motor": st, "decodoare": decodoare,
		"avertizare_tv": avertizareTv(st),
		"tehnic": randuriTehnice(st, tinute), "posturi_tinute": tinute,
	}


CASETE = 6


def geometriePanzei(W, H):
	"""Asezarea desenului din ecranul Egalizator (Screens/HdsEgalizator.py) pe o panza W x H: casetele de sus, coloanele,
	randul valorilor (sus .. sus + h_text) si al etichetelor (y_eticheta .. H). Butonul rotund (raza) sta intre ele si
	la capetele benzilor (-24 / +18 dB) si ale Nivelului (-12 / +12 dB) nu intra in texte."""
	mare = H >= 500
	g = {"mare": mare, "f_mic": 24 if mare else 17, "f_val": 30 if mare else 20, "f_eticheta": 26 if mare else 18,
		"f_bold": 26 if mare else 18, "h_caseta": 84 if mare else 60, "spatiu": 16, "raza": 17 if mare else 12,
		"w_scala": 84 if mare else 56, "h_text": 40 if mare else 28}
	# sase casete: Egalizator, Presetare, Reglaj manual, Pentru acest post, Efecte speciale, La canalele TV
	g["w_caseta"] = (W - (CASETE - 1) * g["spatiu"]) // CASETE
	g["sus"] = g["h_caseta"] + (24 if mare else 14)
	g["w_col"] = (W - g["w_scala"]) // (BENZI + 1)
	g["y_sus"] = g["sus"] + g["h_text"] + g["raza"] + 4
	g["y_eticheta"] = H - g["h_text"]
	g["y_jos"] = g["y_eticheta"] - g["raza"] - 4
	inalt = g["y_jos"] - g["y_sus"]
	g["y_zero"] = g["y_sus"] + int(round(DB_MAX * inalt / float(DB_MAX - DB_MIN)))
	g["y_nivel_zero"] = g["y_sus"] + int(round(NIVEL_MAX * inalt / float(NIVEL_MAX - NIVEL_MIN)))
	return g


# ---------------------------------------------------------------- pornirea si evenimentele

def asculta(functie):
	"""functie(cod) la fiecare schimbare de stare a motorului (1 merge, 2 oprit, 3 inapoi pe placa, 4 fara date, 5 proba gata,
	6 canal TV: sunetul a trecut de pe placa in egalizator)."""
	if functie not in _STARE["ascultatori"]:
		_STARE["ascultatori"].append(functie)


def nuMaiAsculta(functie):
	if functie in _STARE["ascultatori"]:
		_STARE["ascultatori"].remove(functie)


def _laSchimbareMotor(cod):
	if cod == 3:
		st = stareMotor() or {}
		_jurnal("sunetul s-a intors pe placa: %s" % st.get("motiv"))
		if st.get("motiv") == "tv-fara-ceas":
			_verificaPlacaMuta()
	for f in list(_STARE["ascultatori"]):
		try:
			f(cod)
		except Exception as e:
			_jurnal("ascultator: %s" % e)


def _verificaPlacaMuta():
	"""Dupa tv-fara-ceas pe HiSilicon: daca peste o secunda imaginea merge, dar sunetul placii nu (placa a ramas fara
	pista cat ALSA era deschis), serviciul porneste din nou, o singura data pentru acelasi post. Citirea sincronului placii
	o face un fir; firul interfetei numai porneste serviciul."""
	if not placaExista():
		return
	ref = _refAcum()
	if ref is None:
		return
	text = ref.toString()
	if _STARE["repornit_ref"] == text:
		return
	import threading
	rez = {}

	def citeste():
		# imaginea poate porni abia dupa cateva sute de ms: se asteapta pana la 5 s; placa e muta numai daca dupa
		# inca o secunda sunetul ei tot lipseste (o pornire normala a sunetului nu se ia drept placa muta)
		for _i in range(10):
			time.sleep(0.5)
			if peqPlacaMuta():
				time.sleep(1.0)
				rez["muta"] = peqPlacaMuta()
				return
		rez["muta"] = False

	fir = threading.Thread(target=citeste, name="hds-egal-muta")
	fir.daemon = True
	fir.start()
	try:
		from enigma import eTimer
	except ImportError:
		return
	ceas = eTimer()

	def laCeas():
		if fir.is_alive():
			ceas.start(200, True)
			return
		_STARE["verifica_muta"] = None
		r = _refAcum()
		if not rez.get("muta") or r is None or r.toString() != text:
			return
		_STARE["repornit_ref"] = text
		_jurnal("placa a ramas fara sunet dupa tv-fara-ceas: canalul porneste din nou, o data")
		try:
			import NavigationInstance
			NavigationInstance.instance.playService(r, checkParentalControl=False, forceRestart=True)
		except Exception as e:
			_jurnal("pornirea din nou a canalului: %s" % e)

	ceas.callback.append(laCeas)
	_STARE["verifica_muta"] = ceas
	ceas.start(1000, True)


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
		ref = _refAcum()
		if ref is not None and _STARE["repornit_ref"] not in (None, ref.toString()):
			_STARE["repornit_ref"] = None
		# radio -> TV: ALSA-ul radioului se inchide abia dupa ce decodorul placii a primit canalul TV (masurat pe SF8008);
		# fara a doua pista a placii, canalul ar ramane mut, deci la primul canal TV de dupa radio placa se verifica
		din_radio = _STARE.get("ultim_radio")
		_STARE["ultim_radio"] = bool(ref is not None and _eRadio(ref))
		if din_radio and _tvDirect(ref):
			from Components.config import config
			if config.hds_egalizator.pornit.value:
				_verificaPlacaMuta()
		# la fiecare serviciu nou, scris din nou (placa nu e lasata sa poarte nimic de la serviciul de dinainte)
		actualizeazaPlaca(setariEfective(cheie), fortat=True)
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


def _laIntrareStandby(_cfg=None):
	"""La intrarea in standby egalizatorul placii se opreste; la iesire (Standby.onClose) se pune din nou."""
	_laStandby(True)
	try:
		import Screens.Standby
		inst = Screens.Standby.inStandby
		if inst is not None and _laIesireStandby not in inst.onClose:
			inst.onClose.append(_laIesireStandby)
	except Exception:
		pass


def _laIesireStandby():
	_laStandby(False)


def porneste():
	"""La pornirea interfetei (dupa config si inainte de primul serviciu): setarile in motor, legatura la servicii."""
	if _STARE["pornit"]:
		return
	_STARE["pornit"] = True
	initConfig()
	if placaExista():
		# la pornirea interfetei egalizatorul placii se aduce la zero (sa nu ramana pus dupa o cadere)
		_lucratorPlaca().curataLaPornire()
		try:
			from Components.config import config
			config.misc.standbyCounter.addNotifier(_laIntrareStandby, initial_call=False)
		except Exception as e:
			_jurnal("standby: %s" % e)
	aplica(faraPost=True)
	try:
		from enigma import eTimer
		_STARE["ceas_nav"] = eTimer()
		_STARE["ceas_nav"].callback.append(_legaNavigarea)
		_legaNavigarea()
	except ImportError:
		pass
