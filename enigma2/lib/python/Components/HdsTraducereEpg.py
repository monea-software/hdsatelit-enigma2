# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTraducereEpg - traducerea automata a ghidului (EPG): titlurile si descrierile emisiunilor care sunt PE ECRAN
# acum, prin serviciul de traducere al subtitrarilor (Components/HdsTraducereSubtitrari.py: acelasi lant de servicii,
# aceleasi chei), cand setarea „Tradu EPG” (config.hds_traducere.epg) e pornita. Din fabrica e oprita: consuma cota.
#
# BARA DE JOS („Tradu bara de jos”, config.hds_traducere.bara, Da din fabrica): numai titlurile emisiunii de acum si
# urmatoare de pe bara de jos (sursele EventInfo din Screens/SessionGlobals.py: session.Event_Now / Event_Next), pe
# aceeasi cale (aceeasi memorie, coada, fir si contor), cat timp traducerea e pornita (config.hds_traducere.pornit).
# Cine cere un astfel de titlu da bara=True (Converter/EventName.py); descrierile, ghidurile si listele nu. Poarta
# (poartaDeschisa): „Tradu EPG” pornita = orice text; altfel numai titlurile barei, cu bara si traducerea pornite. Capul
# celei de-a doua bare foloseste aceleasi surse, deci arata acelasi titlu, din memorie. Cu numai bara pornita, detaliile
# emisiunii raman in original (INFO din bara = originalul), cu un rand care spune ca pe bara titlul e tradus
# (titluBara, fara cerere noua).
#
# CINE CERE (numai ce se deseneaza, cand se deseneaza):
#   Components/Converter/EventName.py          bara de jos (acum, urmeaza), capul celei de-a doua bare, panourile cu
#                                              emisiunea aleasa din ghid si din lista de canale
#   Components/Converter/HdsCommon.py, HdsInfo pagina ghidului din a doua bara (randurile vazute, emisiunea aleasa)
#   Components/EpgList.py                      randurile vazute ale ghidului (lista le construieste numai pe ele)
#   Screens/EventView.py, Screens/SecondInfoBar.py  detaliile emisiunii (titlu, descrierea scurta si lunga)
#   HdsWebControl/ghid_web.py                  pagina /ghid; canale_web.py numai din memorie (fara cereri noi)
# Fiecare apel text() intoarce pe loc traducerea din memorie sau originalul (desenarea nu asteapta niciodata); textul
# lipsa pleaca la traducere, iar cand vine, cine l-a cerut e chemat (metoda hdsTraducereEpg) si se redeseneaza: textul
# original e inlocuit cu traducerea, fara ecran gol.
#
# CE NU SE TRADUCE: textul deja in limba tinta (limbaProbabila: cuvinte si litere caracteristice; limba emisiunii nu e
# data de nucleu catre Python, eServiceEvent alege singur textul in limba meniului cand canalul il trimite), textul fara
# litere (ore, numere), textul pe care serviciul il intoarce neschimbat (tinut minte ca „acelasi”, nu se mai cere).
#
# MEMORIA: traducerea fiecarei bucati de text (titlul; descrierile impartite pe paragrafe si fraze, cel mult MAX_BUCATA
# semne), dupa serviciu, limba tinta si amprenta textului (sha1): o emisiune repetata sau acelasi titlu pe alt canal nu
# se cere a doua oara. In RAM (MEMORIE_INTRARI); PE DISC numai pe un mediu extern montat (stick, card, disc: dispozitiv
# bloc dupa /proc/mounts, nu o partitie a memoriei interne si nu o montare din retea), in
# <mediu>/hdsatelit/traducere-epg.json, marginit (DISC_INTRARI) si scris rar (cel mult o data la SCRIERE_S, numai daca
# s-a schimbat ceva, pe un fir): memoria interna a receptorului nu se scrie niciodata. Stickul cu imaginea de scris sau
# cu rezervele ei (amiko/, rezerva-*, fisierele unei imagini) e sarit (esteStickDeImagine). Fara mediu potrivit: numai RAM.
# La o pana de curent se pierde ce nu a apucat sa fie scris (cel mult SCRIERE_S).
# FISIERUL (VERSIUNE_DISC 2) e pe randuri: un rand antet {"versiune": 2}, apoi cate o intrare pe rand
# [serviciu, tinta, amprenta, traducere], de la cea mai veche la cea mai noua. Asa analiza nu e un singur apel
# json.loads pe tot fisierul (cod C care tine GIL-ul cat dureaza, deci si firul enigma2), ci cate un apel scurt pe rand,
# iar GIL-ul trece intre ele. Un fisier din versiunea veche (un singur JSON) se ignora: e numai o memorie, se reface.
# Pe firul enigma2 se face numai copia intrarilor (Memorie.intrariDeScris, in C); randurile JSON si marginea
# DISC_OCTETI se fac pe firul de scriere (octetiDin). Fisierul se citeste si se analizeaza pe un fir; intrarile se
# adauga in memorie pe firul enigma2, cate DISC_FELIE la o trezire, ca intrari mai vechi decat cele din RAM (nu le
# inlocuiesc). Cat se citeste, textele lipsa nu pleaca la traducere (ar putea fi in fisier): se deseneaza originalul,
# iar convertoarele care le-au desenat sunt chemate din nou la sfarsitul citirii; dupa DISC_CITIRE_MAX_S (un stick care
# nu mai raspunde) cererile pleaca oricum, iar intrarile venite mai tarziu intra tot ca mai vechi. O scriere cazuta
# (stickul scos) face ca mediul sa fie cautat din nou dupa CAUTA_MEDIU_S, iar memoria sa fie scrisa acolo.
#
# CERERILE: un singur fir, o cerere deodata; textele asteapta INTARZIERE_MS dupa ultima cerere (zap rapid, derulare),
# apoi pleaca cele mai noi intai, cel mult MAX_ELEMENTE_CERERE bucati si MAX_SEMNE_CERERE semne pe cerere (sub limitele
# tuturor serviciilor; la modelele de limbaj raspunsul incape in maxOutputTokens). Un text cerut de un convertor si
# inlocuit pe ecran inainte sa plece (alt canal, alta emisiune) nu mai pleaca. Coada e marginita (MAX_COADA).
# Subtitrarile au intaietate: cat traducatorul subtitrarilor are cereri in lucru, ghidul nu trimite nimic spre un
# server din casa; un serviciu care asteapta dupa o eroare a subtitrarilor e sarit si aici. La o eroare serviciul
# asteapta (HdsTraducereSubtitrari.durataBlocarii, cu refuzurile cheii numarate la rand: un singur refuz nu-l opreste)
# si cererea trece la urmatorul din lant; niciun mesaj pe televizor (ghidul ramane in original), eroarea apare in
# contor. La pornire prima cerere asteapta reteaua si ceasul (HdsTraducereSubtitrari.asteaptaPornirea).
#
# FIRELE: cererea HTTP pe firul ei; rezultatul trezeste firul enigma2 prin T.Trezire (pipe + eSocketNotifier); memoria,
# contorul si chemarea celor care asteapta numai pe firul enigma2.
#
# ORIGINALUL: arataOriginal(True) (INFO a doua oara in detaliile emisiunii) face ca toate textele sa se deseneze in
# original; detaliile il pun inapoi la inchidere.
#
# SETARILE SCHIMBATE (setariSchimbate): lantul se recalculeaza; cand se schimba un comutator (traducerea, „Tradu EPG”,
# „Tradu bara de jos”), cei care au desenat texte traduse se deseneaza din nou (oprit = originalul pe loc). Celelalte
# setari (serviciul rasfoit cu stanga/dreapta in ecranul setarilor) nu redeseneaza nimic, ca sa nu plece cereri spre
# un serviciu doar trecut in revista.
#
# API: activ(bara=False), text(fel, original, cine=None, bara=False), traducere(fel, original, cine=None, bara=False)
#   -> (text, stare), dinMemorie(fel, original), titluBara(original), poartaDeschisa(bara), arataOriginal(da),
#   esteOriginal(), setariSchimbate(element=None), instanta().stare()
#
# ALTE TEXTE: TraducatorEpg e folosit si pentru teletext si paginile HbbTV (Components/HdsTraducereTexte.py, o clasa
# derivata): felul textelor pentru modelele de limbaj (FEL), fisierul memoriei de pe mediul extern (NUME_FISIER), numele
# din jurnal (ETICHETA), poarta (_poartaDeschisa) si comutatoarele (_esteComutator) sunt ale fiecarei instante.

from __future__ import absolute_import

import hashlib
import io
import json
import os
import re
import threading
import time
import weakref
from collections import OrderedDict, deque

from Components import HdsTraducereSubtitrari as T

# ------------------------------------------------------------------ reglaje

FELURI = ("titlu", "scurta", "lunga")
MAX_BUCATA = 900              # semne pe bucata trimisa (o descriere lunga se imparte pe paragrafe si fraze)
MAX_ELEMENTE_CERERE = 24
MAX_SEMNE_CERERE = 3000       # sub limita oricarui serviciu; la Gemini raspunsul incape in maxOutputTokens (2048)
MAX_TEXT = 4000               # un text mai lung de atat se taie (descrierile EIT au de obicei sub 2400)
INTARZIERE_MS = 600
MAX_COADA = 80
TERMEN_S = 10.0
MEMORIE_INTRARI = 4000
MEMORIE_SEMNE = 800000
DISC_INTRARI = 3000
DISC_OCTETI = 1500000
SCRIERE_S = 600
CAUTA_MEDIU_S = 600           # fara mediu extern la prima cautare: se cauta din nou dupa atat (stick pus mai tarziu)
DISC_FELIE = 300              # intrarile citite de pe disc adaugate in memorie la o trezire a firului enigma2
DISC_CITIRE_MAX_S = 10.0      # cat asteapta cererile citirea fisierului; dupa, pleaca fara ea (stick care nu raspunde)
VERSIUNE_DISC = 2             # fisierul pe randuri (1 = un singur JSON, din 0.1.9: ignorat)
NUME_DOSAR = "hdsatelit"
NUME_FISIER = "traducere-epg.json"
ULTIMELE = 10
LANT_S = 2.0                  # setarile si cheile recitite cel mult o data la atat (text() e chemat la fiecare desenare)
MAX_CINE = 400                # cei tinuti minte (ce a cerut fiecare convertor); peste, cei disparuti se uita
_ACELASI = u""                 # in memorie: serviciul a intors textul neschimbat (sau e deja in limba tinta)

STARE_TRADUS, STARE_LUCRU, STARE_ORIGINAL, STARE_OPRIT, STARE_DEJA = "tradus", "lucru", "original", "oprit", "deja"


def _jurnal(text):
	print("[HdsTraducereEpg] %s" % text)


def _setare(s, nume, implicit):
	"""valoarea unei setari care poate lipsi (ConfigSubsection da KeyError, nu AttributeError)"""
	try:
		return getattr(s, nume).value
	except (KeyError, AttributeError):
		return implicit


def poartaDeschisa(bara=False, s=None):
	"""se poate traduce: „Tradu EPG” pornita (orice text), sau bara=True (un titlu de pe bara de jos) cu „Tradu bara de
	jos” si traducerea pornite"""
	try:
		s = s or T.initConfig()
		if s.epg.value:
			return True
		return bool(bara and s.pornit.value and _setare(s, "bara", False))
	except Exception:
		return False


def esteComutator(element, s=None):
	"""elementul de setare e un comutator al traducerii ghidului (pornit, „Tradu EPG”, „Tradu bara de jos”)"""
	if element is None:
		return False
	try:
		s = s or T.initConfig()
	except Exception:
		return False
	for nume in ("pornit", "epg", "bara"):
		try:
			if getattr(s, nume) is element:
				return True
		except (KeyError, AttributeError):
			pass
	return False


# ------------------------------------------------------------------ textul

_FRAZA = re.compile(u"(?<=[.!?…])\\s+")
_LITERA = re.compile(u"[^\\W\\d_]", re.U)


def normalizeaza(text):
	"""paragrafele textului, fiecare cu spatiile stranse; cel mult un rand gol intre ele (descrierea scurta si cea lunga
	raman despartite), niciunul la capete; taiat la MAX_TEXT"""
	if not text:
		return u""
	if not isinstance(text, type(u"")):
		try:
			text = text.decode("utf-8", "replace")
		except Exception:
			text = u"%s" % text
	rez = []
	for p in text[:MAX_TEXT].replace(u"\r\n", u"\n").replace(u"\r", u"\n").split(u"\n"):
		p = u" ".join(p.split())
		if p or (rez and rez[-1]):
			rez.append(p)
	while rez and not rez[-1]:
		rez.pop()
	return u"\n".join(rez)


def bucati(text):
	"""textul normalizat -> [(bucata, despartitor_dupa)], fiecare bucata pe un singur rand, cel mult MAX_BUCATA semne
	(paragraful lung se imparte pe fraze, fraza prea lunga pe cuvinte); lipite la loc dau textul"""
	rez = []
	paragrafe = text.split(u"\n")
	for i, p in enumerate(paragrafe):
		dupa_par = u"\n" if i < len(paragrafe) - 1 else u""
		if not p:
			if rez:
				rez[-1][1] += u"\n"		# randul gol dintre paragrafe ramane dupa bucata de dinainte
			continue
		if len(p) <= MAX_BUCATA:
			rez.append([p, dupa_par])
			continue
		fraze = []
		for f in _FRAZA.split(p):
			while len(f) > MAX_BUCATA:
				taiat = f.rfind(u" ", 0, MAX_BUCATA)
				taiat = taiat if taiat > MAX_BUCATA // 2 else MAX_BUCATA
				fraze.append(f[:taiat].strip())
				f = f[taiat:].strip()
			if f:
				fraze.append(f)
		# frazele scurte lipite pana la MAX_BUCATA (mai putine elemente in cerere)
		grup = []
		for f in fraze:
			if grup and len(u" ".join(grup)) + 1 + len(f) > MAX_BUCATA:
				rez.append([u" ".join(grup), u" "])
				grup = []
			grup.append(f)
		if grup:
			rez.append([u" ".join(grup), dupa_par])
	return [tuple(x) for x in rez if x[0]]


def amprenta(text):
	return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def areLitere(text):
	return len(_LITERA.findall(text or u"")) >= 2


# ------------------------------------------------------------------ limba textului (fara retea)

_CUVINTE = {
	"ro": u"si și in în de la cu pe din pentru este sunt un o care nu ce mai sau iar dar despre dupa după cum fost "
		u"acest aceasta această lui ei lor intre între catre către fara fără sa să se va vor au are noua nouă emisiune "
		u"stiri știri film serial",
	"en": u"the and of to in is for on with at by from this that are was his her their an as it be not or about "
		u"after new news film series episode live show",
	"de": u"der die das und ist im in den von zu mit für auf dem ein eine nicht sich des auch als bei aus nach wird "
		u"sie er es neue folge nachrichten",
	"fr": u"le la les et de des du en un une est dans pour sur au aux avec par pas qui que ce il elle ils son sa "
		u"ses nouveau épisode journal",
	"it": u"il lo la gli le e di del della dei delle in un una è per con su che non da al alla nel nella sono "
		u"puntata notizie",
	"es": u"el la los las y de del en un una es por para con que no se su al lo como más sobre episodio noticias",
	"pt": u"o a os as e de do da dos das em um uma é para com que não se por no na ao mais episódio notícias",
	"hu": u"a az és egy hogy nem is van meg de ez el ki be mint már csak volt lesz híradó film rész",
	"cs": u"a v je se na že to s z do o k ve pro jako ale by od po zprávy díl",
	"pl": u"i w na z się nie do to że jest o jak po co od za dla wiadomości odcinek",
	"nl": u"de het een en van in is op te dat met voor niet zijn aan er bij ook als nieuws aflevering",
	"tr": u"ve bir bu da de için ile ne çok olarak gibi daha sonra haber bölüm",
}
_SETURI = dict((l, frozenset(c.split())) for l, c in _CUVINTE.items())
_LITERE_TIPICE = {
	"ro": u"ăâîșțşţ", "de": u"äöüß", "hu": u"őű", "pl": u"łąęśźżń", "cs": u"řůěčšž", "tr": u"ğış", "es": u"ñ¿¡",
	"pt": u"ãõç", "fr": u"àèùêëœç",
}
_SCRIERI = (("ru", u"Ѐ", u"ӿ"), ("el", u"Ͱ", u"Ͽ"), ("ar", u"؀", u"ۿ"),
	("he", u"֐", u"׿"), ("th", u"฀", u"๿"), ("ko", u"가", u"힯"),
	("ja", u"぀", u"ヿ"), ("zh", u"一", u"鿿"))
_CUVANT = re.compile(u"[^\\W\\d_]+", re.U)


def limbaProbabila(text):
	"""codul limbii textului cand se vede limpede (cuvinte frecvente, litere tipice, scrierea), altfel "" """
	if not text:
		return ""
	litere = _LITERA.findall(text)
	if not litere:
		return ""
	for cod, a, b in _SCRIERI:
		n = sum(1 for c in litere if a <= c <= b)
		if n * 2 > len(litere):
			return cod
	mic = text.lower()
	cuvinte = _CUVANT.findall(mic)
	scor = {}
	for l, st in _SETURI.items():
		scor[l] = sum(1 for c in cuvinte if c in st) * 2.0
	for l, lit in _LITERE_TIPICE.items():
		n = sum(1 for c in mic if c in lit)
		if n:
			scor[l] = scor.get(l, 0) + min(n, 4) * 1.5
	ordine = sorted(scor.items(), key=lambda x: -x[1])
	if not ordine or ordine[0][1] < 3:
		return ""
	if len(ordine) > 1 and ordine[1][1] * 1.6 > ordine[0][1]:
		return ""
	return ordine[0][0]


# ------------------------------------------------------------------ memoria (RAM + disc)

def mediiExterne():
	"""punctele de montare ale mediilor externe: stick-urile si cardurile, apoi discurile, dupa /proc/mounts
	(Components/HdsImportSurse.medii). Numai dispozitive bloc cu un sistem de fisiere cunoscut: partitiile memoriei
	interne (acelasi disc ca radacina, si cand sunt montate la /media/hdd), montarile din retea (nfs, cifs) si cele
	„bind” ale unui dosar intern nu sunt medii externe si nu se ating (nici os.stat)."""
	try:
		from Components import HdsImportSurse
		return [m["punct"] for m in HdsImportSurse.medii() if m.get("fel") in ("stick", "disc")]
	except Exception as e:
		_jurnal("mediile externe nu s-au putut citi: %s" % e.__class__.__name__)
		return []


# un mediu cu o imagine de scris sau cu rezervele ei (stickul de flash): pe el nu se scrie nimic, ca o pana de curent
# in timpul unei scrieri sa nu lase volumul FAT32 nedemontat curat langa imaginea si rezerva de care depinde receptorul
DOSARE_IMAGINE = ("amiko",)
PREFIX_REZERVA = "rezerva-"
FISIERE_IMAGINE = ("rootfs.tar.bz2", "kernel.bin", "imageversion", "rootfs.ubi", "rootfs.tar.xz")
MAX_DOSARE_CITITE = 40            # cate dosare se citesc pe un nivel cand se cauta fisierele unei imagini
_SARITE_SPUSE = set()             # mediile sarite, spuse o singura data in jurnal (cautarea se repeta la CAUTA_MEDIU_S)


def _intrari(cale):
	"""(nume, e_dosar) din cale, fara legaturi simbolice urmarite; [] la eroare"""
	try:
		with os.scandir(cale) as it:
			return [(e.name, e.is_dir(follow_symlinks=False)) for e in it]
	except (OSError, AttributeError):
		try:
			return [(n, os.path.isdir(os.path.join(cale, n)) and not os.path.islink(os.path.join(cale, n)))
				for n in os.listdir(cale)]
		except OSError:
			return []


def esteStickDeImagine(punct):
	"""True cand mediul tine o imagine de scris pe receptor sau rezervele ei: dosarul amiko/ (Maintenance Mode),
	o intrare rezerva-* in radacina, sau fisierele unei imagini (rootfs, kernel, imageversion) in radacina ori cu
	cel mult doua dosare mai jos (de pilda <marca>/<model>/rootfs.tar.bz2)"""
	nivel = _intrari(punct)
	for nume, dosar in nivel:
		mic = nume.lower()
		if (dosar and mic in DOSARE_IMAGINE) or mic.startswith(PREFIX_REZERVA) or (not dosar and mic in FISIERE_IMAGINE):
			return True
	dosare = sorted(n for n, d in nivel if d and not n.startswith("."))[:MAX_DOSARE_CITITE]
	for d1 in dosare:
		sub = _intrari(os.path.join(punct, d1))
		if any(not d and n.lower() in FISIERE_IMAGINE for n, d in sub):
			return True
		for d2 in sorted(n for n, d in sub if d and not n.startswith("."))[:MAX_DOSARE_CITITE]:
			if any(not d and n.lower() in FISIERE_IMAGINE for n, d in _intrari(os.path.join(punct, d1, d2))):
				return True
	return False


def caleDisc(medii=None, nume=NUME_FISIER):
	"""fisierul `nume` al memoriei pe primul mediu extern pe care se poate scrie si care nu e stickul unei imagini
	(esteStickDeImagine), sau None (numai RAM)"""
	for punct in (mediiExterne() if medii is None else medii):
		if esteStickDeImagine(punct):
			if punct not in _SARITE_SPUSE:
				_SARITE_SPUSE.add(punct)
				_jurnal("mediul %s are o imagine sau rezervele ei: memoria traducerilor nu se scrie acolo" % punct)
			continue
		dosar = os.path.join(punct, NUME_DOSAR)
		try:
			if not os.path.isdir(dosar):
				os.makedirs(dosar)
			if os.access(dosar, os.W_OK):
				return os.path.join(dosar, nume)
		except OSError:
			continue
	return None


class Memorie(object):
	"""(serviciu, tinta, amprenta) -> traducere ("" = acelasi text); cele mai vechi folosite pleaca primele"""

	def __init__(self, intrari=MEMORIE_INTRARI, semne=MEMORIE_SEMNE):
		self.intrari, self.semne = intrari, semne
		self._d = OrderedDict()
		self._semne = 0
		self.schimbata = False

	def ia(self, cheie):
		v = self._d.get(cheie)
		if v is not None:
			self._d.move_to_end(cheie)
		return v

	def pune(self, cheie, valoare):
		if cheie in self._d:
			self._semne -= len(self._d.pop(cheie))
		self._d[cheie] = valoare
		self._semne += len(valoare)
		self.schimbata = True
		while self._d and (len(self._d) > self.intrari or self._semne > self.semne):
			k, v = self._d.popitem(last=False)
			self._semne -= len(v)

	def goleste(self):
		self._d.clear()
		self._semne = 0
		self.schimbata = True

	def __len__(self):
		return len(self._d)

	def intrariDeScris(self):
		"""copia celor mai noi DISC_INTRARI intrari, pentru firul de scriere (pe firul enigma2: o copie facuta in C)"""
		return list(self._d.items())[-DISC_INTRARI:]

	def octetiDisc(self):
		"""continutul fisierului de pe disc (octetiDin), ca octeti; pe firul enigma2 se cheama numai intrariDeScris"""
		return octetiDin(self.intrariDeScris())

	def incarca(self, date):
		"""citeste continutul fisierului (octeti); intrarile stricate se sar -> cate s-au citit"""
		n = self.adaugaVechi(intrariDisc(date))
		self.schimbata = False
		return n

	def adaugaVechi(self, intrari):
		"""intrarile citite de pe disc (de la cea mai veche la cea mai noua) puse ca mai vechi decat tot ce e in RAM; o
		cheie deja in RAM ramane cu valoarea ei; semnul „schimbata” nu se atinge -> cate s-au adaugat"""
		n = 0
		for cheie, valoare in reversed(intrari):
			if cheie in self._d:
				continue
			self._d[cheie] = valoare
			self._d.move_to_end(cheie, last=False)
			self._semne += len(valoare)
			n += 1
		while self._d and (len(self._d) > self.intrari or self._semne > self.semne):
			k, v = self._d.popitem(last=False)
			self._semne -= len(v)
		return n


def octetiDin(intrari):
	"""continutul fisierului din intrari [(cheie, traducere)] (de la cea mai veche): antetul, apoi cate o intrare JSON
	pe rand; cele mai noi intai, pana la DISC_OCTETI. Pe firul de scriere."""
	antet = json.dumps({"versiune": VERSIUNE_DISC}).encode("ascii") + b"\n"
	randuri = []
	marime = len(antet)
	for k, v in reversed(intrari):
		r = json.dumps([k[0], k[1], k[2], v], ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
		if marime + len(r) > DISC_OCTETI:
			break
		randuri.append(r)
		marime += len(r)
	randuri.reverse()
	return antet + b"".join(randuri)


def intrariDisc(sursa):
	"""continutul fisierului (octeti, sau fisierul deschis „rb”, citit rand cu rand) -> [((serviciu, tinta, amprenta),
	traducere)], de la cea mai veche, cel mult DISC_INTRARI; randurile stricate sarite, un fisier fara antetul
	versiunii de acum ignorat. Fara stare, deci se poate chema pe orice fir; un json.loads scurt pe fiecare rand (GIL-ul
	trece intre ele)."""
	randuri = io.BytesIO(sursa) if isinstance(sursa, bytes) else sursa
	rez = deque(maxlen=DISC_INTRARI)
	text = type(u"")
	antet = True
	try:
		for rand in randuri:
			rand = rand.strip()
			if not rand:
				continue
			if len(rand) > MAX_TEXT * 4 + 200:
				if antet:
					return []
				continue
			try:
				x = json.loads(rand.decode("utf-8"))
			except Exception:
				if antet:
					return []
				continue
			if antet:
				if not isinstance(x, dict) or x.get("versiune") != VERSIUNE_DISC:
					return []
				antet = False
				continue
			try:
				serv, tinta, amp, trad = x
			except (TypeError, ValueError):
				continue
			if isinstance(serv, text) and isinstance(tinta, text) and isinstance(trad, text) and isinstance(amp, text) and (
					len(amp) == 20 and len(trad) <= MAX_TEXT):
				rez.append(((serv, tinta, amp), trad))
	except (IOError, OSError, ValueError):
		pass
	return list(rez)


# ------------------------------------------------------------------ traducatorul ghidului

class _Bucata(object):
	"""un text de tradus: cheia memoriei (fara serviciu), textul, cine il asteapta"""

	def __init__(self, tinta, text, acum):
		self.tinta, self.text = tinta, text
		self.amp = amprenta(text)
		self.cheie = (tinta, self.amp)
		self.cerut = acum
		self.cine = set()			# id-urile celor care il asteapta (convertoare, liste); gol = nimeni nu-l mai vrea
		self.liber = False			# cerut de cineva fara identitate (lista ghidului, web): pleaca oricum


class TraducatorEpg(object):
	FEL = "epg"                  # felul textelor pentru modelele de limbaj (T.instructiuneModel)
	NUME_FISIER = NUME_FISIER    # memoria de pe mediul extern
	ETICHETA = "ghidului"        # in jurnal: memoria ghidului, firul ghidului
	MAX_COADA = MAX_COADA        # textele care asteapta (o pagina HbbTV are mai multe decat un ecran al ghidului)

	def __init__(self, acum=time.monotonic, trimite_=None, cu_trezire=True, medii=None, cu_disc=True):
		self._acum = acum
		self._trimite = trimite_
		self.memorie = Memorie()
		self.lacat = threading.Lock()
		self.coada = OrderedDict()			# cheie -> _Bucata (cele mai noi la sfarsit)
		self.in_zbor = set()				# cheile trimise acum
		self.fir = False
		self.rezultate = deque()
		self.blocat = {}					# serviciu -> pana_la (None = pana la schimbarea setarilor)
		self.caderi = {}
		self.refuzuri = {}					# serviciu -> refuzuri ale cheii la rand (T.durataBlocarii)
		self.original = False
		self._asteapta = weakref.WeakValueDictionary()	# id -> obiect care asteapta o traducere
		self._ale = {}						# id -> cheia ultimei bucati cerute de el (inlocuita = scoasa din coada)
		self._afisori = weakref.WeakValueDictionary()	# cine a desenat o traducere (la schimbarea originalului)
		self._ultima_cerere = 0.0
		self._medii = medii
		self._cu_disc = cu_disc
		self._disc = None					# calea fisierului, "" = fara mediu extern
		self._disc_cautat = -CAUTA_MEDIU_S	# cand s-a cautat ultima oara un mediu extern
		self._scris_la = acum()
		self._scrie_in_lucru = False
		self._scrie_cazut = False			# scrierea de pe fir a cazut (stickul scos): se cauta alt mediu
		self._disc_fir = False				# firul care citeste fisierul lucreaza (sub lacat)
		self._disc_gata = None				# intrarile citite de fir, de luat pe firul enigma2 (sub lacat)
		self._disc_rest = []				# intrarile citite, inca neadaugate in memorie (firul enigma2)
		self._disc_citite = 0
		self._disc_incarcare = False		# de la pornirea citirii pana la ultima felie adaugata
		self._disc_pornit = 0.0				# cand a pornit citirea (_acum), pentru DISC_CITIRE_MAX_S
		self._disc_termen_spus = False
		self._ceas_disc = None
		self._deja = set()
		self._lant_memo = (-100.0, None)	# (cand, lantul): citit cel mult o data la LANT_S pe firul enigma2
		self._lant_fir = []					# lantul dat firului (calculat pe firul enigma2)
		self.puneContorulLaZero()
		self.trezire = T.Trezire(self.proceseaza) if cu_trezire else None

	# ------------------------------------------------------------------ contorul
	def puneContorulLaZero(self):
		self.contor = {"cereri": 0, "bucati": 0, "semne": 0, "din_memorie": 0, "deja_in_limba": 0, "acelasi": 0,
			"sarite": 0, "erori": dict((f, 0) for f in T.FELURI_EROARE), "ultima_eroare": None, "pe_servicii": {},
			"pe_rezerva": 0, "ms_max": None, "ultimele": deque(maxlen=ULTIMELE), "de_la": time.time()}
		self._ms = deque(maxlen=50)
		self._deja = set()

	# ------------------------------------------------------------------ setarile
	def activ(self, bara=False):
		"""bara=True: pentru un titlu de pe bara de jos (poartaDeschisa)"""
		return bool(self._lantAcum(bara))

	def _lantAcum(self, bara=False):
		"""lantul serviciilor cu campurile complete (principalul primul, daca e complet), [] cand poarta e inchisa
		(„Tradu EPG” oprita si, pentru un titlu al barei, „Tradu bara de jos” sau traducerea oprite) sau niciun serviciu
		nu e completat; lantul tinut LANT_S (poarta se citeste la fiecare apel: doua setari din memorie)"""
		if not self._poartaDeschisa(bara):
			return []
		acum = self._acum()
		cand, lant = self._lant_memo
		if lant is None or not (0 <= acum - cand < LANT_S):
			try:
				lant = self._lant()
			except Exception as e:
				_jurnal("setarile: %s" % e.__class__.__name__)
				lant = []
			self._lant_memo = (acum, lant)
		return lant

	def _poartaDeschisa(self, bara=False):
		"""se poate traduce acum (setarile); clasele derivate au poarta lor"""
		return poartaDeschisa(bara)

	def _esteComutator(self, element):
		"""elementul de setare porneste sau opreste aceasta traducere"""
		return esteComutator(element)

	def setariSchimbate(self, element=None):
		self._lant_memo = (-100.0, None)
		with self.lacat:
			self.blocat.clear()
			self.caderi.clear()
			self.refuzuri.clear()
		if self._esteComutator(element):
			# un comutator: ce e pe ecran tradus se deseneaza din nou (oprit = originalul pe loc)
			self._cheama(list(self._afisori.values()))

	def arataOriginal(self, da):
		da = bool(da)
		if da == self.original:
			return
		self.original = da
		self._cheama(list(self._afisori.values()) + list(self._asteapta.values()))

	# ------------------------------------------------------------------ memoria pe disc
	def _incarcaDisc(self):
		if not self._cu_disc or (self._disc is not None and (self._disc or self._acum() - self._disc_cautat < CAUTA_MEDIU_S)):
			return
		self._disc_cautat = self._acum()
		cale = caleDisc(self._medii, self.NUME_FISIER)
		gasit_acum = self._disc is None
		self._disc = cale or ""
		if not cale:
			if gasit_acum:
				_jurnal("fara mediu extern: memoria %s numai in RAM" % self.ETICHETA)
			return
		if os.path.isfile(cale):
			self._pornesteCitirea(cale)
		self._pornesteCeasDisc()

	def _pornesteCitirea(self, cale):
		"""fisierul memoriei citit si analizat pe un fir; intrarile le ia proceseaza (firul enigma2), pe felii"""
		with self.lacat:
			if self._disc_fir:
				return
			self._disc_fir = True
		self._disc_incarcare = True
		self._disc_pornit = self._acum()
		self._disc_termen_spus = False

		def citeste():
			intrari = []
			try:
				if os.path.isfile(cale) and os.path.getsize(cale) <= DISC_OCTETI * 2:
					with io.open(cale, "rb") as f:
						intrari = intrariDisc(f)
			except Exception as e:
				_jurnal("memoria %s nu s-a citit: %s" % (self.ETICHETA, e.__class__.__name__))
			with self.lacat:
				self._disc_gata = intrari
				self._disc_fir = False
			if self.trezire is not None:
				self.trezire.trezeste()

		t = threading.Thread(target=citeste, name="HdsTraducereEpgCitire")
		t.daemon = True
		try:
			t.start()
		except Exception as e:
			_jurnal("memoria %s nu se poate citi: %s" % (self.ETICHETA, e.__class__.__name__))
			with self.lacat:
				self._disc_fir = False
			self._disc_incarcare = False
			return
		if self.trezire is not None:
			self.trezire.cereCeas(True)

	def _asteaptaDiscul(self):
		"""cererile asteapta citirea fisierului, dar cel mult DISC_CITIRE_MAX_S de la pornirea ei"""
		if not self._disc_incarcare:
			return False
		if 0 <= self._acum() - self._disc_pornit < DISC_CITIRE_MAX_S:
			return True
		if not self._disc_termen_spus:
			self._disc_termen_spus = True
			_jurnal("memoria %s: citirea de pe mediul extern dureaza; cererile pleaca fara ea" % self.ETICHETA)
		return False

	def _adaugaDinDisc(self):
		"""pe firul enigma2 (proceseaza): o felie din intrarile citite; dupa ultima, cine a desenat texte e chemat din
		nou (textele lipsa pot fi acum in memorie, altfel pleaca la traducere)"""
		with self.lacat:
			gata, self._disc_gata = self._disc_gata, None
			citeste = self._disc_fir
		if gata is not None:
			self._disc_rest = list(gata) + self._disc_rest
			self._disc_citite += len(gata)
		if self._disc_rest:
			felie = self._disc_rest[-DISC_FELIE:]
			del self._disc_rest[-DISC_FELIE:]
			self.memorie.adaugaVechi(felie)
			if self._disc_rest and self.trezire is not None:
				self.trezire.trezeste()
		if not citeste and not self._disc_rest:
			self._disc_incarcare = False
			_jurnal("memoria %s: %d traduceri citite de pe mediul extern" % (self.ETICHETA, self._disc_citite))
			self._disc_citite = 0
			self._cheama(list(self._afisori.values()) + list(self._asteapta.values()))

	def _pornesteCeasDisc(self):
		try:
			from enigma import eTimer
		except Exception:
			return
		if self._ceas_disc is None:
			self._ceas_disc = eTimer()
			self._ceas_disc.callback.append(self.scrieDaca)
		self._ceas_disc.start(60 * 1000, False)

	def scrieDaca(self, acum_=None, sincron=False):
		"""pe firul enigma2: memoria scrisa pe mediul extern daca s-a schimbat si au trecut SCRIERE_S de la ultima
		scriere; aici numai copia intrarilor, octetii (octetiDin) si scrierea pe un fir (.nou + os.replace) -> True
		daca a pornit o scriere"""
		cale = self._disc
		acum = self._acum() if acum_ is None else acum_
		if self._scrie_cazut and not self._scrie_in_lucru:
			# mediul nu mai e (stickul scos sau montat altundeva): memoria ramane de scris, mediul se cauta din nou dupa
			# CAUTA_MEDIU_S (_incarcaDisc), niciodata pe memoria interna
			self._scrie_cazut = False
			self.memorie.schimbata = True
			self._disc = ""
			self._disc_cautat = acum
			_jurnal("memoria %s: mediul extern nu mai e, il caut din nou mai tarziu" % self.ETICHETA)
			return False
		if not cale or not self.memorie.schimbata or self._scrie_in_lucru or acum - self._scris_la < SCRIERE_S:
			return False
		intrari = self.memorie.intrariDeScris()
		self.memorie.schimbata = False
		self._scris_la = acum
		self._scrie_in_lucru = True

		def scrie():
			try:
				date = octetiDin(intrari)
				nou = cale + ".nou"
				with io.open(nou, "wb") as f:
					f.write(date)
				os.replace(nou, cale)
			except Exception as e:
				_jurnal("memoria %s nu s-a scris: %s" % (self.ETICHETA, e.__class__.__name__))
				self._scrie_cazut = True
			self._scrie_in_lucru = False

		if sincron:
			scrie()
		else:
			t = threading.Thread(target=scrie, name="HdsTraducereEpgDisc")
			t.daemon = True
			t.start()
		return True

	# ------------------------------------------------------------------ cererea unui text (firul enigma2)
	def _lant(self):
		"""serviciile complete, in ordinea lantului (principalul fara cheie e sarit, lucreaza prima rezerva completa)"""
		lant = T.lantul()
		folosite = []
		for c in lant:
			if c["serviciu"] not in [x["serviciu"] for x in folosite] and not T.ceLipseste(c):
				folosite.append(c)
		return folosite

	def _dinMemorie(self, lant, tinta, amp):
		for c in lant:
			v = self.memorie.ia((T.cheieServiciu(c), tinta, amp))
			if v is not None:
				return v
		return None

	def traducere(self, fel, original, cine=None, cere=True, lant=None, inlocuieste=True, bara=False):
		"""-> (textul de desenat, stare): traducerea din memorie (STARE_TRADUS), originalul cat se traduce
		(STARE_LUCRU), originalul fara traducere (STARE_ORIGINAL = omul a cerut originalul, STARE_OPRIT = functia
		oprita, STARE_DEJA = deja in limba tinta sau intors neschimbat). cine: obiectul care se redeseneaza (metoda
		hdsTraducereEpg) cand vine traducerea; inlocuieste=True: cine arata un singur text deodata (un convertor), deci
		ce ceruse inainte si n-a plecat inca nu mai pleaca; False pentru cine arata mai multe (liste, detalii, pagini).
		cere=False: numai memoria, nicio cerere noua. bara=True: titlul vine de pe bara de jos (poartaDeschisa); se
		ia in seama numai pentru fel „titlu”."""
		if not original:
			return original, STARE_OPRIT
		if lant is None:
			lant = self._lantAcum(bara and fel == "titlu")
		if not lant:
			return original, STARE_OPRIT
		self._incarcaDisc()
		text = normalizeaza(original)
		if not text or not areLitere(text):
			return original, STARE_DEJA
		tinta = lant[0]["tinta"]
		if limbaProbabila(text) == tinta:
			if text not in self._deja and len(self._deja) < 5000:
				self._deja.add(text)
				self.contor["deja_in_limba"] += 1
			return original, STARE_DEJA
		parti = bucati(text)
		traduse = []
		lipsa = []
		for b, dupa in parti:
			amp = amprenta(b)
			v = self._dinMemorie(lant, tinta, amp)
			if v is None:
				lipsa.append(b)
			else:
				traduse.append((v or b) + dupa)
		if not lipsa:
			rezultat = u"".join(traduse).strip()
			acelasi = rezultat == text
			if cine is not None:
				self._afisori[id(cine)] = cine
			if self.original:
				return original, STARE_ORIGINAL
			if acelasi:
				return original, STARE_DEJA
			return rezultat, STARE_TRADUS
		if cine is not None:
			self._afisori[id(cine)] = cine
		if self.original:
			return original, STARE_ORIGINAL
		if cere and not self._asteaptaDiscul():			# cat se citeste fisierul, textul poate fi acolo
			self._lant_fir = lant
			self._cere(lipsa, tinta, cine, inlocuieste)
		return original, STARE_LUCRU

	def text(self, fel, original, cine=None, inlocuieste=True, bara=False):
		return self.traducere(fel, original, cine, inlocuieste=inlocuieste, bara=bara)[0]

	def dinMemorie(self, fel, original):
		"""traducerea numai din memorie (fara cerere noua), sau originalul"""
		return self.traducere(fel, original, None, cere=False)[0]

	def _cere(self, texte, tinta, cine, inlocuieste=True):
		acum = self._acum()
		cid = id(cine) if cine is not None and inlocuieste else None
		chei = []
		with self.lacat:
			for t in texte:
				b = _Bucata(tinta, t, acum)
				k = b.cheie
				chei.append(k)
				if k in self.in_zbor:
					continue
				vechi = self.coada.pop(k, None)
				if vechi is not None:
					b.cine, b.liber = vechi.cine, vechi.liber
				if cid is None:
					b.liber = True
				else:
					b.cine.add(cid)
				self.coada[k] = b
			if cid is not None:
				# ce ceruse inainte acelasi convertor si nu mai e pe ecran nu mai pleaca
				for k in self._ale.get(cid, ()):
					if k in chei:
						continue
					b = self.coada.get(k)
					if b is not None:
						b.cine.discard(cid)
						if not b.cine and not b.liber:
							del self.coada[k]
							self.contor["sarite"] += 1
				self._ale[cid] = tuple(chei)
				if len(self._ale) > MAX_CINE:
					for x in [x for x in self._ale if x not in self._asteapta]:
						self._ale.pop(x, None)
			if cine is not None:
				self._asteapta[id(cine)] = cine
			while len(self.coada) > self.MAX_COADA:
				self.coada.popitem(last=False)
				self.contor["sarite"] += 1
			self._ultima_cerere = acum
			porneste = not self.fir and bool(self.coada)
			if porneste:
				self.fir = True
		if porneste:
			t = threading.Thread(target=self._lucru, name="HdsTraducereEpg")
			t.daemon = True
			t.start()
		if self.trezire is not None:
			self.trezire.cereCeas(True)

	# ------------------------------------------------------------------ firul
	def _liber(self, serv, acum):
		b = self.blocat.get(serv, 0)
		return b is not None and acum >= b

	def _iaLot(self):
		"""sub lacat: cele mai noi bucati din coada, sub MAX_ELEMENTE_CERERE si MAX_SEMNE_CERERE, acelasi tinta"""
		lot = []
		semne = 0
		for k in reversed(list(self.coada.keys())):
			b = self.coada[k]
			if lot and (b.tinta != lot[0].tinta or len(lot) >= MAX_ELEMENTE_CERERE or semne + len(b.text) > MAX_SEMNE_CERERE):
				continue
			lot.append(b)
			semne += len(b.text)
		for b in lot:
			del self.coada[b.cheie]
			self.in_zbor.add(b.cheie)
		return lot

	def _subtitrarileOcupa(self, lant):
		"""subtitrarile au cereri in lucru si primul serviciu liber e un server din casa: ghidul asteapta"""
		try:
			ts = T._INSTANTA[0]
			if ts is None or not ts.ocupat():
				return False
			for c in lant:
				if self._liber(c["serviciu"], self._acum()):
					return T.serverDinCasa(c)
		except Exception:
			pass
		return False

	def _lucru(self):
		while True:
			lot = None
			iesire = None
			try:
				with self.lacat:
					if not self.coada:
						self.fir = False
						return
					ramas = self._ultima_cerere + INTARZIERE_MS / 1000.0 - self._acum()
				if ramas > 0:
					time.sleep(min(ramas, INTARZIERE_MS / 1000.0))
					continue
				lant = self._lantFir()
				if not lant:
					with self.lacat:
						self.contor["sarite"] += len(self.coada)
						self.coada.clear()
						self.fir = False
					return
				if self._subtitrarileOcupa(lant):
					time.sleep(0.3)
					continue
				# o data pe pornire: reteaua si ceasul, ca la subtitrari (T.asteaptaPornirea, cel mult cateva secunde)
				T.asteaptaPornirea()
				with self.lacat:
					lot = self._iaLot()
				if not lot:
					continue
				iesire = self._trimite_lot(lant, lot)
			except Exception as e:
				_jurnal("firul %s: %s" % (self.ETICHETA, e.__class__.__name__))
				if lot is None:
					with self.lacat:
						self.coada.clear()
						self.fir = False
					return
				iesire = (lot, None, None, T.EroareTraducere(T.E_RASPUNS, str(e)[:120]), 0, [])
			with self.lacat:
				self.rezultate.append(iesire)
			if self.trezire is not None:
				self.trezire.trezeste()

	def _lantFir(self):
		"""lantul serviciilor, calculat pe firul enigma2 la ultima cerere"""
		return list(self._lant_fir)

	def _trimite_lot(self, lant, lot):
		"""pe fir: lotul la primul serviciu liber din lant (si liber pentru subtitrari); la o eroare serviciul asteapta
		si se incearca urmatorul -> (lot, cfg, traducerile, eroare, ms, erori)"""
		texte = [b.text for b in lot]
		tinta = lot[0].tinta
		eroare = None
		erori = []
		ts = T._INSTANTA[0]
		for i, cfg in enumerate(lant):
			serv = cfg["serviciu"]
			with self.lacat:
				liber = self._liber(serv, self._acum())
			if not liber or (ts is not None and not ts.serviciuLiber(serv)):
				continue
			inceput = self._acum()
			try:
				rez = T.traduceAcum(cfg, texte, "", tinta, (), TERMEN_S, self._trimite, fel=self.FEL)
			except T.EroareTraducere as e:
				eroare = e
			except Exception as e:
				eroare = T.EroareTraducere(T.E_RASPUNS, str(e)[:120])
			else:
				with self.lacat:
					self.caderi.pop(serv, None)
					self.blocat.pop(serv, None)
					self.refuzuri.pop(serv, None)
				return (lot, cfg, rez, None, int((self._acum() - inceput) * 1000), erori)
			erori.append((cfg, eroare))
			with self.lacat:
				acum = self._acum()
				self.caderi[serv] = self.caderi.get(serv, 0) + 1
				refuzuri = 1
				if eroare.fel == T.E_CHEIE:
					refuzuri = self.refuzuri[serv] = self.refuzuri.get(serv, 0) + 1
				durata = T.durataBlocarii(eroare, serv, i < len(lant) - 1, self.caderi[serv], refuzuri)
				if durata is None:
					self.blocat[serv] = None
				elif durata > 0:
					self.blocat[serv] = acum + durata
		return (lot, None, None, eroare or T.EroareTraducere(T.E_LIPSA, u""), 0, erori)

	# ------------------------------------------------------------------ rezultatele (firul enigma2)
	def proceseaza(self):
		if self._disc_incarcare:
			self._adaugaDinDisc()
		chemati = []
		while True:
			with self.lacat:
				if not self.rezultate:
					gol = not self.coada and not self.fir and not self._disc_fir
					break
				lot, cfg, rez, eroare, ms, erori = self.rezultate.popleft()
				for b in lot:
					self.in_zbor.discard(b.cheie)
			for c, e in erori:
				self._numaraEroarea(c, e)
			if rez is not None and cfg is not None:
				self._reusita(lot, cfg, rez, ms)
				chemati.extend(self._asteptatori(lot))
		if chemati:
			self._cheama(chemati)
		if gol and not self._disc_incarcare and self.trezire is not None:
			self.trezire.cereCeas(False)
		self.scrieDaca()

	def asteapta(self, termen_s=5.0):
		"""probele: pana nu mai e nimic in lucru (si memoria de pe disc e toata adaugata), apoi proceseaza()"""
		sfarsit = time.monotonic() + termen_s
		while time.monotonic() < sfarsit:
			with self.lacat:
				gata = not self.coada and not self.fir and not self._disc_fir
			if gata and not self._disc_incarcare:
				break
			if gata:
				self.proceseaza()
			time.sleep(0.01)
		self.proceseaza()

	def _asteptatori(self, lot):
		"""cine se redeseneaza cand vine un lot: cine l-a cerut, apoi toti cei care au desenat texte ale ghidului (si
		ecranele ascunse care au acelasi text, cerut de altul, il iau din memorie)"""
		ids = set()
		for b in lot:
			ids.update(b.cine)
		rez = []
		for cid in ids:
			o = self._asteapta.get(cid)
			if o is not None:
				rez.append(o)
		vazute = set(id(o) for o in rez)
		for o in list(self._asteapta.values()) + list(self._afisori.values()):
			if id(o) not in vazute:
				vazute.add(id(o))
				rez.append(o)
		return rez

	def _cheama(self, obiecte):
		"""cheama hdsTraducereEpg al fiecaruia; cine cade (un ecran inchis care inca n-a fost sters din memorie) se uita"""
		vazute = set()
		for o in obiecte:
			if id(o) in vazute:
				continue
			vazute.add(id(o))
			f = getattr(o, "hdsTraducereEpg", None)
			if f is None:
				continue
			try:
				f()
			except Exception as e:
				_jurnal("redesenare %s: %s" % (o.__class__.__name__, e.__class__.__name__))
				self._afisori.pop(id(o), None)
				self._asteapta.pop(id(o), None)

	def _reusita(self, lot, cfg, rez, ms):
		sv = T.cheieServiciu(cfg)
		serv = cfg["serviciu"]
		self.contor["cereri"] += 1
		self.contor["bucati"] += len(lot)
		self.contor["semne"] += sum(len(b.text) for b in lot)
		ps = self.contor["pe_servicii"]
		ps[serv] = ps.get(serv, 0) + len(lot)
		try:
			principal = T.configuratia()["serviciu"]
		except Exception:
			principal = serv
		if serv != principal:
			self.contor["pe_rezerva"] += 1
		self._ms.append(ms)
		self.contor["ms_max"] = ms if self.contor["ms_max"] is None else max(self.contor["ms_max"], ms)
		for b, tr in zip(lot, rez):
			tr = normalizeaza(tr).replace(u"\n", u" ")
			if not tr or tr == b.text:
				self.contor["acelasi"] += 1
				tr = _ACELASI
			self.memorie.pune((sv, b.tinta, b.amp), tr)
			self.contor["ultimele"].append({"ora": time.strftime("%H:%M:%S"), "original": b.text[:200],
				"traducere": (tr or b.text)[:200], "serviciu": serv, "ms": ms})

	def _numaraEroarea(self, cfg, eroare):
		fel = eroare.fel if eroare.fel in T.FELURI_EROARE else T.E_RASPUNS
		self.contor["erori"][fel] += 1
		self.contor["ultima_eroare"] = {"fel": fel, "text": eroare.text, "cod": eroare.cod,
			"ora": time.strftime("%H:%M:%S"), "serviciu": cfg["serviciu"]}
		_jurnal("%s: eroare %s%s" % (cfg["serviciu"], fel, (" (HTTP %s)" % eroare.cod) if eroare.cod else ""))

	# ------------------------------------------------------------------ starea (ecranul, web)
	def stare(self):
		"""pornit = „Tradu EPG”; bara = setarea „Tradu bara de jos”; bara_activ = titlurile barei se traduc acum (prin
		bara sau prin „Tradu EPG”); traducere_pornita = traducerea subtitrarilor (bara lucreaza numai cu ea)"""
		c = self.contor
		ms = list(self._ms)
		try:
			s = T.initConfig()
			pornit = bool(s.epg.value)
			bara = bool(_setare(s, "bara", False))
			traducere_pornita = bool(s.pornit.value)
		except Exception:
			pornit = bara = traducere_pornita = False
		with self.lacat:
			in_coada = len(self.coada) + len(self.in_zbor)
		return {
			"pornit": pornit,
			"activ": self.activ(),
			"bara": bara,
			"bara_activ": self.activ(True),
			"traducere_pornita": traducere_pornita,
			"memorie": len(self.memorie),
			"pe_disc": bool(self._disc),
			"disc": self._disc or u"",
			"in_coada": in_coada,
			"original": self.original,
			"contor": {
				"cereri": c["cereri"], "bucati": c["bucati"], "semne": c["semne"], "deja_in_limba": c["deja_in_limba"],
				"acelasi": c["acelasi"], "sarite": c["sarite"], "erori": dict(c["erori"]),
				"ultima_eroare": c["ultima_eroare"], "pe_servicii": dict(c["pe_servicii"]), "pe_rezerva": c["pe_rezerva"],
				"ms_max": c["ms_max"], "ms_mediu": int(sum(ms) / len(ms)) if ms else None,
				"ultimele": list(c["ultimele"])[::-1], "de_la": c["de_la"],
			},
		}


_INSTANTA = [None]


def instanta():
	if _INSTANTA[0] is None:
		_INSTANTA[0] = TraducatorEpg()
	return _INSTANTA[0]


def activ(bara=False):
	"""bara=True: pentru un titlu de pe bara de jos"""
	try:
		return instanta().activ(bara)
	except Exception:
		return False


def text(fel, original, cine=None, inlocuieste=True, cere=True, bara=False):
	"""textul de desenat (traducerea din memorie sau originalul); cere=False: numai memoria (ecran ascuns); bara=True:
	un titlu de pe bara de jos; nu arunca"""
	try:
		return instanta().traducere(fel, original, cine, cere=cere, inlocuieste=inlocuieste, bara=bara)[0]
	except Exception as e:
		_jurnal("text: %s" % e.__class__.__name__)
		return original


def traducere(fel, original, cine=None, inlocuieste=True, bara=False):
	try:
		return instanta().traducere(fel, original, cine, inlocuieste=inlocuieste, bara=bara)
	except Exception as e:
		_jurnal("traducere: %s" % e.__class__.__name__)
		return original, STARE_OPRIT


def dinMemorie(fel, original):
	try:
		return instanta().dinMemorie(fel, original)
	except Exception:
		return original


def titluBara(original):
	"""traducerea titlului asa cum o arata bara de jos, numai din memorie (fara cerere noua), sau "" cand bara nu-l
	traduce (oprita, deja in limba ta, inca netradus, originalul cerut)"""
	try:
		text_, stare_ = instanta().traducere("titlu", original, None, cere=False, bara=True)
	except Exception:
		return u""
	return text_ if stare_ == STARE_TRADUS else u""


def arataOriginal(da):
	try:
		instanta().arataOriginal(da)
	except Exception as e:
		_jurnal("original: %s" % e.__class__.__name__)


def esteOriginal():
	return _INSTANTA[0] is not None and _INSTANTA[0].original


def setariSchimbate(element=None):
	if _INSTANTA[0] is not None:
		_INSTANTA[0].setariSchimbate(element)


def stare():
	return instanta().stare()
