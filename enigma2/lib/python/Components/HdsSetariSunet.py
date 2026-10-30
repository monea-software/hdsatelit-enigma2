# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSetariSunet.py: volumul si intarzierea sunetului, prin driverul original al placii de sunet.
# Pe televizor: Meniu > Audio & Sound Tracks > „Volum și întârziere” (data/setup.xml, hds_setari_sunet); intarzierea
# pistei de acum si in ecranul AUDIO (Screens/AudioSelection.py). In web: /volum-intarziere (volum_intarziere_web.py). Toate
# folosesc numai functiile de aici.
#
# Ce face (verificat pe binarele receptorului):
# - pasul volumului (1..10): tastele de volum (Components/VolumeControl.py) urca si coboara cu el, pe calea obisnuita
#   a volumului (AUDIO_SET_MIXER, lib/dvb/volume.cpp);
# - cat sta bara volumului pe ecran dupa ultima apasare (1..10 s, 3 ca inainte), in Components/VolumeControl.py;
# - mutul tinut minte (config.audio.hds_mut, din VolumeControl): pus la loc la primul canal dupa pornire (mutLaPornire);
# - volumul tinut minte pe canal: la fiecare schimbare de volum (VolumeControl.volSave, si din web) volumul se noteaza
#   pentru canalul de acum; la pornirea unui canal (evStart, inainte sa porneasca sunetul lui) se pune volumul tinut
#   minte, daca are. Un canal fara volum tinut minte pastreaza volumul de acum. La prima pornire de canal dupa pornirea
#   receptorului se pune volumul salvat (config.audio.volume): altfel placa ramane pe 100 pana la prima apasare;
# - volumul egal intre canale: AVC-ul motorului de sunet al placii (comanda „avc” din /proc/msp/sound0), in doua trepte:
#   Usor (apropie incet volumul canalelor si al reclamelor) si Puternic (si diferenta dintre tare si incet mai mica).
#   Motorul acestui cip nu are alt compresor (DRC pe iesire lipseste), deci compresia ceruta e treapta Puternic;
# - intarzierea sunetului pe HDMI si pe optic: compensarea pe iesire a placii („HDMI0 delaycomps N”, „SPDIF0
#   delaycomps N”, 0..500 ms), la care se aduna intarzierea pistei de acum, tinuta minte pe canal si pe pista. Suma se
#   scrie numai cand difera de ce arata placa (DelayComps(Nms) in /proc/msp/sound0): la pornirea canalului, la
#   schimbarea pistei si a iesirii sunetului (trecerea AC3 neschimbata opreste si reporneste pista in placa), la
#   iesirea din standby si cand se schimba setarea.
# Balansul nu e aici: driverul nu il primeste pe nicio cale deschisa imaginii.
# Cu setarile din fabrica (pas 5, fara memorie, AVC oprit, intarzieri 0) nu se scrie nimic in placa.
#
# Partea de sus nu importa enigma: se probeaza pe PC cu un /proc fals (HDS_PROBA_SUNET = radacina lui, ca HdsSunet).

from __future__ import absolute_import

import json
import os
import re
import time

PLACA = "proc/msp/sound0"
MAX_OCTETI_PLACA = 65536
# iesirile reglate: (cheia setarii, numele iesirii in driver)
IESIRI = (("hdmi", "HDMI0"), ("optic", "SPDIF0"))
INTARZIERE_MAX = 500          # ms, limita driverului (ajutorul din modulul placii: 0~500, pas 1 ms)
INTARZIERE_PAS = 10
PISTA_MIN = -250              # intarzierea pistei se aduna la cea a iesirii; suma ramane in 0..500
PISTA_MAX = 250
PAS_MIN, PAS_MAX, PAS_IMPLICIT = 1, 10, 5
# cat sta bara volumului pe ecran dupa ultima apasare, in secunde (3 = cat statea mereu, Components/VolumeControl.py)
AFISARE_MIN, AFISARE_MAX, AFISARE_IMPLICIT = 1, 10, 3
VOLUM_EGAL = ("oprit", "usor", "puternic")
# atributele AVC pe trepte (limitele driverului: prag -40..-16 dB, castig 0..8 dB, limita -40..0 dB, atac si revenire
# 20..2000 ms). Ordinea scrierii: fiecare comanda schimba un atribut si le verifica pe toate, deci timpii intai, apoi
# castigul, pragul si limita (limita ramane mereu peste prag). Valorile sunt puncte de plecare, de potrivit la ascultare.
AVC = {
	"usor": (("attacktime", 200), ("releasetime", 2000), ("gain", 3), ("thrhd", -20), ("limit", -3)),
	"puternic": (("attacktime", 50), ("releasetime", 500), ("gain", 6), ("thrhd", -30), ("limit", -10)),
}
FISIER = "/etc/enigma2/hdsatelit/sunet-canale.json"
MAX_CANALE = 3000
MAX_OCTETI = 1024 * 1024
MAX_CHEIE = 200
PAUZA_SCRIERE_S = 3.0
# verificarile intarzierii dupa un eveniment (ms): placa reporneste pista putin dupa pornirea canalului
VERIFICARI_START = (400, 1500, 4000)
VERIFICARI_PISTA = (300, 1500)
VERIFICARI_IESIRE = (500, 2000, 5000)
VERIFICARI_STANDBY = (1000, 3000)
ASTEPTARE_NAVIGARE_MS = 2000
INCERCARI_NAVIGARE = 90

_STARE = {"memorie": None, "pornit": False, "nav": None, "ceas_nav": None, "incercari": 0, "ceas": None,
	"verificari": [], "volum_initial": False, "mut_initial": False, "ceas_volum": None, "ceas_scriere": None,
	"avc_scris": None, "erori": {}, "standby_legat": False}


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsSetariSunet] %s" % text)


# ---------------------------------------------------------------- randurile (televizor si web, aceleasi texte)

# (cheia web, atributul din config.hds_setari_sunet, eticheta, ajutorul scurt, cheia SystemInfo ceruta sau None)
RANDURI = (
	("pas", "pas_volum", N_("Pasul volumului"),
		N_("Cât crește sau scade volumul la o apăsare pe tastele de volum (volumul merge de la 0 la 100)."), None),
	("afisare", "afisare_volum", N_("Cât stă volumul pe ecran"),
		N_("Câte secunde rămâne bara volumului pe ecran după ultima apăsare pe tastele de volum."), None),
	("canal", "volum_pe_canal", N_("Volumul ținut minte pe canal"),
		N_("Da: fiecare canal pornește cu volumul la care l-ai lăsat. Un canal la care nu ai schimbat volumul îl păstrează pe cel de acum."), None),
	("egal", "volum_egal", N_("Volum egal între canale"),
		N_("Placa de sunet apropie singură volumul: canalele și reclamele tari se aud mai încet, cele încete mai tare. Puternic micșorează și diferența dintre tare și încet (bun noaptea). Nu lucrează când sunetul pleacă neschimbat spre televizor."),
		"HdsSunetAvc"),
	("hdmi", "intarziere_hdmi", N_("Întârzierea sunetului pe HDMI"),
		N_("Când buzele se mișcă după sunet, întârzie sunetul spre televizor. Sunetul se poate numai întârzia, nu grăbi."),
		"HdsSunetIntarziere"),
	("optic", "intarziere_optic", N_("Întârzierea sunetului pe optic"),
		N_("La fel, pentru bara de sunet sau amplificatorul legat la ieșirea optică a receptorului."),
		"HdsSunetIntarziere"),
)
NUME_VOLUM_EGAL = {"oprit": N_("Oprit"), "usor": N_("Ușor"), "puternic": N_("Puternic")}
ETICHETA_PISTA = N_("Întârzierea pistei pe acest canal")
AJUTOR_PISTA = N_("Se adună la întârzierea ieșirii, numai pentru pista de sunet de acum a canalului de acum. Se ține minte.")


def textMs(ms):
	"""„120 ms”, „+40 ms”, „−40 ms” (minus tipografic, se citeste bine de la 3 m)."""
	ms = int(ms)
	return (u"−%d ms" % -ms) if ms < 0 else u"%d ms" % ms


def textMsPista(ms):
	ms = int(ms)
	return (u"+%d ms" % ms) if ms > 0 else textMs(ms)


def alegeriIntarziere():
	return [(str(v), textMs(v)) for v in range(0, INTARZIERE_MAX + 1, INTARZIERE_PAS)]


def alegeriPista():
	return [(str(v), textMsPista(v)) for v in range(PISTA_MIN, PISTA_MAX + 1, INTARZIERE_PAS)]


def alegeriPas():
	return [(str(v), str(v)) for v in range(PAS_MIN, PAS_MAX + 1)]


def alegeriAfisare():
	"""„1 s” ... „10 s”: simbolul secundei, ca „ms” la intarzieri, la fel in orice limba si fara plural."""
	return [(str(v), "%d s" % v) for v in range(AFISARE_MIN, AFISARE_MAX + 1)]


# ---------------------------------------------------------------- placa de sunet (curat, fara enigma)

def radacina():
	return os.environ.get("HDS_PROBA_SUNET") or "/"


def _cale(rad, relativ):
	return os.path.join(rad or radacina(), relativ)


def limiteaza(v, jos, sus):
	"""Intregul cel mai apropiat, in jos..sus; textele rele (si „1e999”, „nan”) dau 0 adus in jos..sus."""
	try:
		v = int(round(float(v)))
	except (TypeError, ValueError, OverflowError):
		v = 0
	return jos if v < jos else (sus if v > sus else v)


_RAND_IESIRE = re.compile(r"^\s*([A-Z]+[0-9]+):\s*Status\(([^)]*)\)(.*)$")


def iesiriDinText(text):
	"""Randurile iesirilor din /proc/msp/sound0 -> {"HDMI0": {"stare", "mut", "volum", "intarziere"}, ...}; valorile
	lipsa raman None."""
	rez = {}
	for rand in (text or "").splitlines():
		m = _RAND_IESIRE.match(rand)
		if not m:
			continue
		rest = m.group(3)
		d = {"stare": m.group(2).strip(), "mut": None, "volum": None, "intarziere": None}
		x = re.search(r"\bMute\((on|off)\)", rest)
		if x:
			d["mut"] = x.group(1) == "on"
		x = re.search(r"\bVol\((\d+)", rest)
		if x:
			d["volum"] = int(x.group(1))
		x = re.search(r"\bDelayComps\((\d+)\s*ms\)", rest)
		if x:
			d["intarziere"] = int(x.group(1))
		rez[m.group(1)] = d
	return rez


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def _citestePlacaText(cale):
	try:
		with open(cale, "rb") as f:
			return f.read(MAX_OCTETI_PLACA).decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def citestePlaca(rad=None):
	"""Iesirile placii (iesiriDinText) sau None cand /proc/msp/sound0 lipseste (alt receptor, PC)."""
	text = _procFundal(_citestePlacaText, _cale(rad, PLACA))
	if text is None:
		return None
	return iesiriDinText(text)


def areIntarziere(rad=None):
	"""Placa arata compensarea pe iesire la HDMI sau la optic."""
	placa = citestePlaca(rad)
	return bool(placa) and any((placa.get(n) or {}).get("intarziere") is not None for k, n in IESIRI)


def areAvc(rad=None):
	"""Comanda „avc” e a aceluiasi driver (hi_aiao) care face /proc/msp/sound0 (tabelul comenzilor lui); o aplica
	motorul de sunet din software (hi_adsp, iMedia AVC)."""
	return bool(citestePlaca(rad))


def pePas(ms, jos=PISTA_MIN, sus=PISTA_MAX):
	"""Intarzierea adusa la cel mai apropiat multiplu de INTARZIERE_PAS, in jos..sus."""
	ms = limiteaza(ms, jos, sus)
	return limiteaza(int(round(ms / float(INTARZIERE_PAS))) * INTARZIERE_PAS, jos, sus)


def intarziereTotala(baza, adaos):
	return limiteaza(limiteaza(baza, 0, INTARZIERE_MAX) + limiteaza(adaos, PISTA_MIN, PISTA_MAX), 0, INTARZIERE_MAX)


def comenziIntarziere(dorit, placa):
	"""dorit = {"HDMI0": ms, ...}; placa = citestePlaca(). -> comenzile pentru iesirile care arata alta valoare. Fara
	placa (None) sau fara randul iesirii nu se scrie nimic: nu e acest driver."""
	rez = []
	if not placa:
		return rez
	for k, nume in IESIRI:
		if nume not in dorit:
			continue
		acum = (placa.get(nume) or {}).get("intarziere")
		if acum is None:
			continue
		ms = limiteaza(dorit[nume], 0, INTARZIERE_MAX)
		if acum != ms:
			rez.append("%s delaycomps %d" % (nume, ms))
	return rez


def comenziAvc(nivel):
	"""Comenzile pentru treapta AVC: oprit -> „avc off”; altfel atributele, apoi „avc on”."""
	if nivel not in AVC:
		return ["avc off"]
	return ["avc %s %d" % (nume, v) for nume, v in AVC[nivel]] + ["avc on"]


def scrieComenzi(comenzi, rad=None, cazute=None):
	"""Fiecare comanda intr-o scriere separata in /proc/msp/sound0 (driverul ia o comanda pe scriere). -> cate au mers.
	O comanda refuzata de driver da eroare la scriere (si „proc cmd is fault” in jurnalul nucleului); cu `cazute` (o
	lista), comenzile refuzate se adauga in ea."""
	bune = 0
	cale = _cale(rad, PLACA)
	for c in comenzi:
		try:
			with open(cale, "w", encoding="utf-8") as f:
				f.write(c + "\n")
			bune += 1
		except (IOError, OSError) as e:
			cheie = c.split(" ")[0] + " " + (c.split(" ")[1] if " " in c else "")
			n = _STARE["erori"].get(cheie, 0)
			if n < 3:
				_jurnal("placa a refuzat „%s”: %s" % (c, e))
			_STARE["erori"][cheie] = n + 1
			if cazute is not None:
				cazute.append(c)
	if comenzi:
		_jurnal("scris in placa: %s (%d din %d)" % ("; ".join(comenzi), bune, len(comenzi)))
	return bune


# ---------------------------------------------------------------- canalele si memoria lor (curat)

def cheieCanal(text):
	"""Referinta unui serviciu -> cheia canalului: DVB „sid:tsid:onid:spatiu” (hexazecimal, fara tipul serviciului),
	flux „url:” + adresa; fisierele (inregistrari, filme) nu au cheie (None)."""
	try:
		t = (text or u"").strip()
	except AttributeError:
		return None
	campuri = t.split(":")
	if len(campuri) < 10:
		return None
	cale = campuri[10] if len(campuri) > 10 else u""
	if cale:
		if cale.startswith("/"):
			return None
		return (u"url:" + cale)[:MAX_CHEIE]
	try:
		sid, tsid, onid, spatiu = [int(x or "0", 16) for x in campuri[3:7]]
	except ValueError:
		return None
	if not (sid or tsid or onid or spatiu):
		return None
	return u"%x:%x:%x:%x" % (sid, tsid, onid, spatiu)


def _curataIntrare(v):
	if not isinstance(v, dict):
		return None
	rez = {}
	vol = v.get("v")
	if isinstance(vol, int) and not isinstance(vol, bool) and 1 <= vol <= 100:
		rez["v"] = vol
	piste = v.get("i")
	if isinstance(piste, dict):
		i = {}
		for k, ms in list(piste.items())[:32]:
			if isinstance(k, str) and re.match(r"^-?\d{1,5}$", k) and isinstance(ms, int) and not isinstance(ms, bool):
				ms = pePas(ms)
				if ms:
					i[k] = ms
		if i:
			rez["i"] = i
	if not rez:
		return None
	t = v.get("t")
	rez["t"] = t if isinstance(t, int) and not isinstance(t, bool) else 0
	return rez


class MemorieCanale(object):
	"""Volumul si intarzierea pistelor tinute minte pe canal, in FISIER (JSON). Scrierea se amana PAUZA_SCRIERE_S dupa
	ultima schimbare (apasarile repetate nu scriu de fiecare data pe memoria receptorului): .nou + fsync + os.replace.
	Un fisier stricat nu opreste nimic (se porneste de la zero)."""

	def __init__(self, cale=FISIER, ceas=time.time, maxCanale=MAX_CANALE):
		self.cale = cale
		self.ceas = ceas
		self.maxCanale = maxCanale
		self.date = None
		self.de_scris_la = None

	def _incarca(self):
		if self.date is not None:
			return self.date
		self.date = {}
		try:
			if os.path.getsize(self.cale) > MAX_OCTETI:
				_jurnal("%s e prea mare: il ignor" % self.cale)
				return self.date
			with open(self.cale, "rb") as f:
				obiect = json.loads(f.read(MAX_OCTETI + 1).decode("utf-8"))
		except (IOError, OSError):
			return self.date
		except (ValueError, UnicodeDecodeError):
			_jurnal("%s nu se poate citi: pornesc de la zero" % self.cale)
			return self.date
		canale = obiect.get("canale") if isinstance(obiect, dict) else None
		if isinstance(canale, dict):
			for k, v in list(canale.items())[:self.maxCanale]:
				if isinstance(k, str) and 0 < len(k) <= MAX_CHEIE:
					c = _curataIntrare(v)
					if c:
						self.date[k] = c
		return self.date

	def _schimbat(self, cheie):
		d = self._incarca()
		if cheie in d:
			d[cheie]["t"] = int(self.ceas())
		while len(d) > self.maxCanale:
			vechi = min(d.items(), key=lambda kv: (kv[1].get("t", 0), kv[0]))[0]
			del d[vechi]
		self.de_scris_la = self.ceas() + PAUZA_SCRIERE_S

	def volum(self, cheie):
		if not cheie:
			return None
		return (self._incarca().get(cheie) or {}).get("v")

	def noteazaVolum(self, cheie, v):
		"""Volumul 1..100 pentru canal (0 nu se tine minte: e mutul facut din volum). -> True daca s-a schimbat."""
		if not cheie or len(cheie) > MAX_CHEIE:
			return False
		v = limiteaza(v, 0, 100)
		if v <= 0:
			return False
		d = self._incarca()
		intrare = d.setdefault(cheie, {"t": 0})
		if intrare.get("v") == v:
			return False
		intrare["v"] = v
		self._schimbat(cheie)
		return True

	def intarziere(self, cheie, pid):
		if not cheie or pid is None:
			return 0
		return ((self._incarca().get(cheie) or {}).get("i") or {}).get(str(int(pid)), 0)

	def noteazaIntarziere(self, cheie, pid, ms):
		"""Intarzierea pistei `pid` a canalului (ms, -250..250, din 10 in 10; 0 o uita). -> True daca s-a schimbat."""
		if not cheie or pid is None or len(cheie) > MAX_CHEIE:
			return False
		ms = pePas(ms)
		d = self._incarca()
		intrare = d.get(cheie) or {"t": 0}
		piste = dict(intrare.get("i") or {})
		k = str(int(pid))
		if piste.get(k, 0) == ms:
			return False
		if ms:
			piste[k] = ms
		else:
			piste.pop(k, None)
		if piste:
			intrare["i"] = piste
		else:
			intrare.pop("i", None)
		if "v" in intrare or "i" in intrare:
			d[cheie] = intrare
		else:
			d.pop(cheie, None)
		self._schimbat(cheie)
		return True

	def numarVolume(self):
		return sum(1 for v in self._incarca().values() if "v" in v)

	def numarPiste(self):
		return sum(len(v.get("i") or {}) for v in self._incarca().values())

	def uitaVolume(self):
		"""Uita volumele tuturor canalelor (intarzierile pistelor raman). -> cate s-au uitat."""
		d = self._incarca()
		n = 0
		for k in list(d.keys()):
			if "v" in d[k]:
				n += 1
				del d[k]["v"]
				if "i" not in d[k]:
					del d[k]
		if n:
			self.de_scris_la = self.ceas()
		return n

	def scrieDaca(self, fortat=False):
		"""Scrie fisierul daca a venit vremea (sau fortat si e ceva de scris). -> True daca s-a scris."""
		if self.de_scris_la is None or (not fortat and self.ceas() < self.de_scris_la):
			return False
		text = json.dumps({"versiune": 1, "canale": self._incarca()}, ensure_ascii=True, separators=(",", ":"),
			sort_keys=True)
		nou = self.cale + ".nou"
		try:
			dosar = os.path.dirname(self.cale)
			if dosar and not os.path.isdir(dosar):
				os.makedirs(dosar)
			with open(nou, "wb") as f:
				f.write(text.encode("ascii"))
				f.flush()
				os.fsync(f.fileno())
			os.replace(nou, self.cale)
		except (IOError, OSError) as e:
			_jurnal("%s nu s-a putut scrie: %s" % (self.cale, e))
			try:
				os.unlink(nou)
			except OSError:
				pass
			return False
		self.de_scris_la = None
		return True


def memorie():
	if _STARE["memorie"] is None:
		_STARE["memorie"] = MemorieCanale()
	return _STARE["memorie"]


# ---------------------------------------------------------------- setarile (cu enigma, importuri tarzii)

def initConfig():
	"""config.hds_setari_sunet si cheile SystemInfo; din Components/AVSwitch.InitAVSwitch, inaintea meniurilor."""
	from Components.config import config, ConfigSubsection, ConfigSelection, ConfigYesNo
	from Components.SystemInfo import SystemInfo
	if "hds_setari_sunet" not in config.content.items:
		config.hds_setari_sunet = ConfigSubsection()
		c = config.hds_setari_sunet
		# textele alegerilor raman netraduse aici (limba nu e inca pusa); ConfigSelection si web-ul le traduc la afisare
		c.pas_volum = ConfigSelection(choices=alegeriPas(), default=str(PAS_IMPLICIT))
		c.afisare_volum = ConfigSelection(choices=alegeriAfisare(), default=str(AFISARE_IMPLICIT))
		c.volum_pe_canal = ConfigYesNo(default=False)
		c.volum_egal = ConfigSelection(choices=[(k, NUME_VOLUM_EGAL[k]) for k in VOLUM_EGAL], default="oprit")
		c.intarziere_hdmi = ConfigSelection(choices=alegeriIntarziere(), default="0")
		c.intarziere_optic = ConfigSelection(choices=alegeriIntarziere(), default="0")
	SystemInfo["HdsSunetIntarziere"] = areIntarziere()
	SystemInfo["HdsSunetAvc"] = areAvc()


def _c():
	from Components.config import config
	return config.hds_setari_sunet


def _valoare(atribut, implicit=None):
	try:
		return getattr(_c(), atribut).value
	except Exception:
		return implicit


def pasVolum():
	"""Pasul tastelor de volum (1..10); 5 fara setari."""
	return limiteaza(_valoare("pas_volum", PAS_IMPLICIT), PAS_MIN, PAS_MAX)


def afisareVolumMs():
	"""Cat sta bara volumului pe ecran (Components/VolumeControl.py), in ms; 3000 fara setari."""
	return 1000 * limiteaza(_valoare("afisare_volum", AFISARE_IMPLICIT), AFISARE_MIN, AFISARE_MAX)


def volumPeCanal():
	return bool(_valoare("volum_pe_canal", False))


def intarziereIesire(cheie):
	return limiteaza(_valoare("intarziere_" + cheie, 0), 0, INTARZIERE_MAX)


# ---------------------------------------------------------------- canalul si pista de acum

def _nav():
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def canalAcum():
	"""(cheia, numele) canalului care merge, sau (None, "")."""
	nav = _nav()
	try:
		ref = nav.getCurrentlyPlayingServiceReference() if nav else None
	except Exception:
		ref = None
	if ref is None:
		return None, u""
	try:
		text = ref.toString()
	except Exception:
		text = u""
	nume = u""
	try:
		from ServiceReference import ServiceReference
		nume = ServiceReference(ref).getServiceName() or u""
	except Exception:
		pass
	return cheieCanal(text), nume


def pistaAcum():
	"""(pid, descrierea) pistei de sunet care merge, sau (None, "")."""
	nav = _nav()
	try:
		service = nav.getCurrentService() if nav else None
		audio = service and service.audioTracks()
		if not audio:
			return None, u""
		i = audio.getCurrentTrack()
		if i is None or i < 0 or i >= audio.getNumberOfTracks():
			return None, u""
		info = audio.getTrackInfo(i)
		pid = info.getPID()
		limba = (info.getLanguage() or u"").strip()
		text = (info.getDescription() or u"").strip()
		if limba:
			text = (u"%s, %s" % (text, limba)) if text else limba
		return (pid if isinstance(pid, int) and pid >= 0 else None), text
	except Exception:
		return None, u""


def intarzierePista():
	"""Pentru ecranul AUDIO si web: {"cheie", "canal", "pid", "pista", "ms"} sau None (fara canal DVB sau fara pista)."""
	cheie, nume = canalAcum()
	pid, text = pistaAcum()
	if not cheie or pid is None:
		return None
	return {"cheie": cheie, "canal": nume, "pid": pid, "pista": text, "ms": memorie().intarziere(cheie, pid)}


def seteazaIntarzierePista(ms, cheie=None, pid=None):
	"""Intarzierea pistei de acum (sau a celei date), tinuta minte, scrisa pe loc in placa. -> valoarea pusa sau None."""
	if cheie is None or pid is None:
		p = intarzierePista()
		if p is None:
			return None
		cheie, pid = p["cheie"], p["pid"]
	ms = pePas(ms)
	if memorie().noteazaIntarziere(cheie, pid, ms):
		_scrieMaiTarziu()
	verifica()
	return ms


# ---------------------------------------------------------------- aplicarea in placa

def intarzieriDorite(adaos=None):
	"""{"HDMI0": ms, "SPDIF0": ms} pentru pista de acum."""
	if adaos is None:
		p = intarzierePista()
		adaos = p["ms"] if p else 0
	return dict((nume, intarziereTotala(intarziereIesire(k), adaos)) for k, nume in IESIRI)


def verifica(rad=None):
	"""Pune intarzierile in placa unde difera. -> comenzile scrise."""
	try:
		from Components.SystemInfo import SystemInfo
		if not SystemInfo.get("HdsSunetIntarziere"):
			return []
	except Exception:
		pass
	placa = citestePlaca(rad)
	comenzi = comenziIntarziere(intarzieriDorite(), placa)
	if comenzi:
		scrieComenzi(comenzi, rad)
	return comenzi


def aplicaAvc(fortat=False, rad=None):
	"""Pune treapta AVC aleasa. Placa nu arata AVC in /proc, deci se scrie numai la schimbare, la pornire (cand nu e
	oprit: oprit e starea placii la pornire) si dupa standby (fortat)."""
	try:
		from Components.SystemInfo import SystemInfo
		if not SystemInfo.get("HdsSunetAvc"):
			return []
	except Exception:
		pass
	nivel = _valoare("volum_egal", "oprit")
	if nivel not in VOLUM_EGAL:
		nivel = "oprit"
	scris = _STARE["avc_scris"]
	if not fortat and (scris == nivel or (scris is None and nivel == "oprit")):
		_STARE["avc_scris"] = nivel
		return []
	if fortat and nivel == "oprit" and scris in (None, "oprit"):
		return []
	comenzi = comenziAvc(nivel)
	cazute = []
	scrieComenzi(comenzi, rad, cazute)
	if cazute:
		# un atribut refuzat din cauza celorlalte (verificate toate la fiecare schimbare) trece dupa ce s-au pus ele
		_jurnal("AVC: se scriu din nou %d comenzi refuzate" % len(cazute))
		scrieComenzi(cazute, rad)
	_STARE["avc_scris"] = nivel
	return comenzi


# ---------------------------------------------------------------- volumul

def _volumControl():
	try:
		from enigma import eDVBVolumecontrol
		return eDVBVolumecontrol.getInstance()
	except Exception:
		return None


def _volumSalvat():
	"""config.audio.volume (il face Components/VolumeControl.py la pornirea interfetei), sau None inca."""
	try:
		from Components.config import config
		return limiteaza(config.audio.volume.value, 0, 100)
	except Exception:
		return None


def _mutSalvat():
	"""Mutul tinut minte (config.audio.hds_mut, din Components/VolumeControl.py): (mut, scris), cu scris = setarea a fost
	salvata macar o data, adica volumul salvat e nivelul ales si cat sunetul e pe mut. Setarile de dinainte nu o au:
	acolo volumul 0 inseamna ca sunetul era pe mut, la un nivel care nu se mai stie. (False, False) fara setare."""
	try:
		from Components.config import config
		el = config.audio.hds_mut
	except Exception:
		return False, False
	return bool(el.value), el.saved_value is not None


def laVolumSalvat(vol):
	"""Din VolumeControl.volSave (taste, web): volumul se tine minte pe canalul de acum, cand setarea e pe Da. Volumul
	schimbat de om inainte de primul canal ramane cum l-a pus (nici volumul, nici mutul salvat nu mai vin peste el)."""
	_STARE["volum_initial"] = True
	_STARE["mut_initial"] = True
	if not volumPeCanal():
		return False
	cheie = canalAcum()[0]
	if cheie and memorie().noteazaVolum(cheie, vol):
		_scrieMaiTarziu()
		return True
	return False


def laMutSalvat():
	"""Din VolumeControl.volMute (tasta MUTE, web): mutul pus sau scos de om inainte de primul canal ramane cum l-a pus."""
	_STARE["mut_initial"] = True


def volumLaPornireaCanalului():
	"""Volumul de pus la pornirea canalului de acum: cel tinut minte pe canal (setarea pe Da), altfel, numai la primul
	canal dupa pornire, cel salvat; altfel None (volumul ramane)."""
	v = None
	if volumPeCanal():
		v = memorie().volum(canalAcum()[0])
	if v is None and not _STARE["volum_initial"]:
		v = _volumSalvat()
		if v is None:
			return None           # VolumeControl inca nefacut: se incearca din nou (_aplicaVolum)
		_STARE["volum_initial"] = True
		if v <= 0 and not _mutSalvat()[1]:
			# setari de dinainte de mutul tinut minte: volSave scria 0 cand sunetul era pe mut; pornit asa, receptorul
			# ar fi fara sunet si fara semnul de mut; ramane volumul placii, ca inainte
			return None
	return v


def mutLaPornire(v):
	"""La primul canal dupa pornirea receptorului (o singura data): (pune_mut, arata_semnul). Mutul tinut minte revine;
	un volum salvat 0 fara mut (pus asa din web) e tratat ca mut, ca receptorul sa nu porneasca tacut fara niciun semn.
	Semnul de mut se arata numai cand nivelul e peste 0 (la 0 tastele de volum il pun si ele fara semn). Cat
	receptorul e in standby nu se face nimic (standby-ul pune si scoate singur mutul): se incearca la canalul urmator.
	(False, False) cand nu e nimic de facut. `v` = volumul pus acum (None = ramane cel al placii)."""
	if _STARE["mut_initial"]:
		return False, False
	if _inStandby():
		return False, False
	_STARE["mut_initial"] = True
	mut, scris = _mutSalvat()
	if not scris:
		return False, False
	nivel = v if v is not None else _volumSalvat()
	if mut or nivel == 0:
		return True, bool(nivel)
	return False, False


def _inStandby():
	try:
		from Screens.Standby import inStandby
		return inStandby is not None
	except Exception:
		return False


def _aplicaVolum():
	v = volumLaPornireaCanalului()
	if v is None and not _STARE["volum_initial"]:
		_ceasVolum(2000)          # VolumeControl inca nefacut
		return None
	vc = _volumControl()
	if vc is None:
		return None
	try:
		if v is not None and vc.getVolume() != v:
			vc.setVolume(v, v)    # mutul ramane cum era (volume.cpp: setVolume nu atinge mutul)
			_jurnal("volumul canalului: %d" % v)
		pune, semn = mutLaPornire(v)
		if pune and not vc.isMuted():
			vc.volumeToggleMute()
			_jurnal("mutul tinut minte, pus la pornire")
		if v is None and not pune:
			return None
		try:
			from Components.VolumeControl import VolumeControl
			inst = VolumeControl.instance
			if inst is not None:
				inst.volumeDialog.setValue(0 if vc.isMuted() else vc.getVolume())
				if pune and semn:
					inst.muteDialog.show()
		except Exception:
			pass
	except Exception as e:
		_jurnal("volumul nu s-a pus: %s" % e)
		return None
	return v


def _ceasVolum(ms):
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _STARE["ceas_volum"] is None:
		_STARE["ceas_volum"] = eTimer()
		_STARE["ceas_volum"].callback.append(_aplicaVolum)
	_STARE["ceas_volum"].start(ms, True)


def uitaVolume():
	n = memorie().uitaVolume()
	if n:
		memorie().scrieDaca(fortat=True)
	return n


# ---------------------------------------------------------------- scrierea memoriei si verificarile amanate

def _scrieMaiTarziu():
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _STARE["ceas_scriere"] is None:
		_STARE["ceas_scriere"] = eTimer()
		_STARE["ceas_scriere"].callback.append(_laCeasScriere)
	_STARE["ceas_scriere"].start(int(PAUZA_SCRIERE_S * 1000) + 100, True)


def _laCeasScriere():
	mem = memorie()
	if not mem.scrieDaca() and mem.de_scris_la is not None:
		_scrieMaiTarziu()


def scrieAcum():
	return memorie().scrieDaca(fortat=True)


def programeaza(intarzieri_ms):
	"""Verificarile intarzierii peste `intarzieri_ms` (ms de acum), printr-un singur ceas enigma2."""
	try:
		from enigma import eTimer
	except ImportError:
		return
	acum = time.time()
	for ms in intarzieri_ms:
		_STARE["verificari"].append(acum + ms / 1000.0)
	_STARE["verificari"].sort()
	if _STARE["ceas"] is None:
		_STARE["ceas"] = eTimer()
		_STARE["ceas"].callback.append(_laCeasVerificare)
	_porneste_ceas()


def _porneste_ceas():
	if not _STARE["verificari"] or _STARE["ceas"] is None:
		return
	ms = max(0, int((_STARE["verificari"][0] - time.time()) * 1000))
	_STARE["ceas"].start(ms, True)


def _laCeasVerificare():
	acum = time.time() + 0.05
	_STARE["verificari"] = [t for t in _STARE["verificari"] if t > acum]
	try:
		verifica()
	except Exception as e:
		_jurnal("intarzierea: %s" % e)
	_porneste_ceas()


def laSchimbareaPistei():
	"""Din ecranul AUDIO, dupa alegerea altei piste."""
	programeaza(VERIFICARI_PISTA)


# ---------------------------------------------------------------- evenimentele

def _laEveniment(ev):
	try:
		from enigma import iPlayableService
	except Exception:
		return
	if ev == iPlayableService.evStart:
		try:
			_aplicaVolum()
		except Exception as e:
			_jurnal("volumul la pornirea canalului: %s" % e)
		_reverificaPlaca()
		programeaza(VERIFICARI_START)
	elif ev == getattr(iPlayableService, "evUpdatedInfo", -1):
		programeaza(VERIFICARI_PISTA)


def _reverificaPlaca():
	"""Placa (/proc/msp/sound0) apare cand showiframe deschide sunetul; daca la pornirea interfetei nu era inca,
	randurile ei se arata de la primul canal care o gaseste (si AVC-ul ales se pune atunci)."""
	try:
		from Components.SystemInfo import SystemInfo
	except Exception:
		return
	if not SystemInfo.get("HdsSunetIntarziere") and areIntarziere():
		SystemInfo["HdsSunetIntarziere"] = True
		_jurnal("placa de sunet gasita dupa pornire: intarzierea pe iesiri se poate regla")
	if not SystemInfo.get("HdsSunetAvc") and areAvc():
		SystemInfo["HdsSunetAvc"] = True
		aplicaAvc()


def _laSchimbareaIntarzierii(el):
	verifica()


def _laSchimbareaAvc(el):
	aplicaAvc()


def _laSchimbareaIesirii(el):
	# AC3 trimis neschimbat sau decodat: placa opreste si reporneste pista; intarzierea se verifica dupa
	programeaza(VERIFICARI_IESIRE)


def _laStandby(el):
	try:
		from Screens.Standby import inStandby
		if inStandby is not None and _dupaStandby not in inStandby.onClose:
			inStandby.onClose.append(_dupaStandby)
	except Exception as e:
		_jurnal("standby: %s" % e)


def _dupaStandby():
	try:
		aplicaAvc(fortat=True)
	except Exception as e:
		_jurnal("AVC dupa standby: %s" % e)
	programeaza(VERIFICARI_STANDBY)


def _legaNavigarea():
	nav = _nav()
	if nav is not None:
		if _laEveniment not in nav.event:
			nav.event.append(_laEveniment)
		_STARE["nav"] = nav
		# canalul de pornire a pornit inaintea legarii, deci evStart-ul lui s-a pierdut: volumul si mutul acum
		try:
			if nav.getCurrentlyPlayingServiceReference() is not None:
				_aplicaVolum()
		except Exception as e:
			_jurnal("volumul canalului de pornire: %s" % e)
		return
	_STARE["incercari"] += 1
	if _STARE["incercari"] < INCERCARI_NAVIGARE and _STARE["ceas_nav"] is not None:
		_STARE["ceas_nav"].start(ASTEPTARE_NAVIGARE_MS, True)
	else:
		_jurnal("fara Navigation dupa %d incercari" % _STARE["incercari"])


def porneste():
	"""Dupa initConfig (Components/AVSwitch.InitAVSwitch): notificatorii setarilor, AVC-ul ales (daca nu e oprit),
	legatura la pornirea canalelor si la iesirea din standby."""
	if _STARE["pornit"]:
		return
	_STARE["pornit"] = True
	c = _c()
	c.intarziere_hdmi.addNotifier(_laSchimbareaIntarzierii, initial_call=False)
	c.intarziere_optic.addNotifier(_laSchimbareaIntarzierii, initial_call=False)
	c.volum_egal.addNotifier(_laSchimbareaAvc, initial_call=True)
	from Components.config import config
	try:
		av = config.av.content.items     # o subsectiune lipsa da KeyError (ConfigSubsection.__getattr__)
	except Exception:
		av = {}
	for nume in ("hds_sunet_iesire", "downmix_ac3", "downmix_dts"):
		el = av.get(nume)
		if el is not None:
			el.addNotifier(_laSchimbareaIesirii, initial_call=False)
	try:
		config.misc.standbyCounter.addNotifier(_laStandby, initial_call=False)
		_STARE["standby_legat"] = True
	except Exception as e:
		_jurnal("fara legatura la standby: %s" % e)
	try:
		from enigma import eTimer
		_STARE["ceas_nav"] = eTimer()
		_STARE["ceas_nav"].callback.append(_legaNavigarea)
		_STARE["ceas_nav"].start(ASTEPTARE_NAVIGARE_MS, True)
	except ImportError:
		pass


# ---------------------------------------------------------------- starea, pentru web

def stare(rad=None):
	"""Setarile, ce arata placa, canalul si pista de acum, cate volume sunt tinute minte."""
	placa = citestePlaca(rad)
	rez = {"placa": None, "pista": intarzierePista(), "volume_tinute": memorie().numarVolume(),
		"piste_tinute": memorie().numarPiste(), "volum": None}
	if placa:
		rez["placa"] = dict((nume, (placa.get(nume) or {}).get("intarziere")) for k, nume in IESIRI)
	vc = _volumControl()
	if vc is not None:
		try:
			rez["volum"] = {"valoare": int(vc.getVolume()), "mut": bool(vc.isMuted())}
		except Exception:
			pass
	return rez
