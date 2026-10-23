# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Cautarea de canale din lista de canale (tasta TEXT, OK tinut, randul „Caută canal…”, MENU > Cauta canale). Doar in
imaginea HDSatelit.

Ecranul: randul „Nume" (tastele 0-9 ca la SMS, tastatura de pe ecran, tastatura USB), filtrele pe doua coloane (in
stanga grupurile cu optiuni scurte, in dreapta cele lungi; comutatoare alese cu Stanga/Dreapta si pornite/oprite cu OK;
Sus/Jos in aceeasi coloana, Stanga de pe prima optiune sau Dreapta de pe ultima trec in cealalta coloana), numarul de
canale gasite si lista de rezultate (OK porneste canalul). Pe un ecran ingust (alt skin) filtrele raman pe o coloana.
Datele si regulile filtrelor sunt in Components/HdsIndexCanale.py.

Tot aici: pornirea culegerii la vizionare (Components/HdsCulegereCanale.py: rezolutia exacta si codecul, accesul, pistele,
in baza unica Components/HdsBazaCanale.py), o singura data, din ChannelSelection.__init__ prin porneste_masuratori(session).

Randurile pistelor: „Are” (teletext, subtitrari DVB / teletext, HbbTV), „Format sunet”, „Sunet” (mono, stereo,
multicanal), „Piste sunet”, „Limbă sunet” si „Subtitrare”, din baza pistelor (Components/HdsPisteCanale.py), si MENU =
„Actualizeaza pistele” (trecerea prin transpondere, ecranul HdsActualizarePiste). Cand se cauta numai radio, randurile
imaginii (rezolutia, codarea video) se ascund. Fara palpaire: filtrele se redeseneaza rand cu rand (_puneFiltre),
rezultatele numai cand s-au schimbat; gol, numarul, titlul si textele se pun numai cand chiar se schimba.
„Actualizeaza pistele” se atinge si fara MENU: butonul din capatul randului „Nume” (Dreapta pe „Nume”, apoi OK).
O trecere oprita sau intrerupta in ultimele 24 de ore (starea din Components/HdsPisteCanale.py, CALE_STARE) se poate
continua: inaintea intrebarii obisnuite, „Continui de unde a rămas?” cu Continuă / De la capăt (si in pagina web).

Firul enigma2: indexul (citirea lamedb-ului si a buchetelor, cam 1-2 s pe receptor cu 8000 de canale) se face pe un
fir, iar masuratorile si pistele se aplica pe firul enigma2 in felii de cel mult FELIE_S (pregatirea in fundal, mai
jos); ecranul arata „Se pregătește lista de canale…” pana atunci, iar un index vechi din memorie se foloseste pe loc si
se inlocuieste cand vine cel nou. Dupa pornire indexul se pregateste singur, la INCALZIRE_MS. Cautarea dupa text ruleaza
cel mult o data la AMANARE_TEXT_MS: o litera noua o inlocuieste pe cea care astepta.

Memoria cautarii (cat merge interfata, una pentru lista TV si una pentru lista radio): textul, filtrele, randul cu
focus si canalul de sub cursor raman dupa inchiderea ecranului; la deschiderea urmatoare (TEXT, OK tinut, „Caută
canal…”) cautarea revine la fel, cu cursorul pe canalul pornit acum daca e printre rezultate. Dupa un canal pornit din
rezultate, lista de canale redeschide singura cautarea la deschiderea ei urmatoare (dupa_zap / de_redeschis, chemate din
ChannelSelection). Rosu („Șterge filtrele”) sterge si memoria: cautare noua, lista obisnuita.
"""
from enigma import eListboxPythonMultiContent, eTimer, eRCInput, getPrevAsciiCode, getDesktop, gFont, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components import HdsIndexCanale as X
from Components import HdsPisteCanale as P
from Components.HdsCampText import Masura
from Tools.BoundFunction import boundFunction
from Tools.NumericalTextInput import NumericalTextInput

TITLU = 'Căutare canale'
# titlul ecranului (1536 px, HdsBold 40): cam 80 de caractere. Titlul se scrie intreg, cu toate filtrele (un rand
# care nu incape deruleaza, lib/gui/elabel.h); MAX_TITLU si _incapeTitlu raman numai pentru masurare.
MAX_TITLU = 74
# pregatirea indexului in fundal (vezi mai jos); False: pe loc, ca inainte (probele de pe PC, fara bucla enigma2)
IN_FUNDAL = True
FELIE_S = 0.012            # cat lucreaza o chemare a ceasului pe firul enigma2 (masuratorile si pistele)
INCALZIRE_MS = 45000       # dupa pornirea interfetei: indexul gata inainte de prima cautare
AMANARE_TEXT_MS = 180      # cautarea dupa text, cel mult o data in atat; 0 = pe loc
MAX_RANDURI_GATA = 600     # randurile rezultatelor tinute gata construite (vezi HdsCautareCanale._randRezultat)
# cifrele: litere mici si cifra (numele se compara fara spatii si semne, deci nu e nevoie de spatiu); 0 si 1 scriu
# direct cifra
LITERE_SMS = ('0', '1', 'abc2', 'def3', 'ghi4', 'jkl5', 'mno6', 'pqrs7', 'tuv8', 'wxyz9')

# culorile din skinul HDSatelit si rezerva pentru un alt skin (0xRRGGBB, opac)
CULORI = {
	'text': ('hdsText', 0xF2F4F8),
	'text2': ('hdsText2', 0xC9D2E3),
	'eticheta': ('hdsLabel', 0xAEB9CC),
	'stins': ('hdsDisabled', 0x667085),
	'focus': ('hdsBrandLight', 0x9FB4FF),
	'ales': ('hdsMarked', 0xF5B83D),
	'alesText': ('hdsMarkedText', 0x10162A),
	'pista': ('hdsTrack', 0x2A3350),
	'bun': ('hdsGood', 0x4FD18B),
	'chihlimbar': ('hdsAmber', 0xF5B83D),
	'alb': ('white', 0xFFFFFF),
}


_NIMIC = object()          # „nimic pus inca pe ecran” (vezi HdsCautareCanale._pune)
ngettext = X.ngettext      # pluralele traduse (numele scurt, ca xgettext sa gaseasca apelurile)

# filtrele pe doua coloane (Components/HdsIndexCanale.py, aceleasi si in pagina /cautare): randul k are grupul k din
# stanga si grupul k din dreapta (dintre cele vizibile)
COLOANA_STANGA = X.COLOANA_STANGA
COLOANA_DREAPTA = X.COLOANA_DREAPTA
# sub aceasta latime a listei de filtre (la scara 1920) filtrele stau pe o singura coloana, ca inainte
LATIME_DOUA_COLOANE = 1300
# partea din latime a coloanei din stanga (1712 px in skinul HDSatelit: 800 in stanga, 896 in dreapta)
PARTE_STANGA = 800.0 / 1712


def _jurnal(text):
	print('[HdsCautareCanale] %s' % text)


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			# alfa FF ar fi citit de lista ca „culoare din sablon"; o culoare complet transparenta nu are rost aici
			return v & 0xFFFFFF if (v >> 24) == 0xFF else v
	except Exception:
		pass
	return implicit


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


def _font(alias, nume, marime, inaltime):
	"""(gFont, marimea, inaltimea randului) din aliasul skinului (<alias name="HdsCautare..."/>), altfel rezerva
	scalata dupa latimea ecranului. Marimea textului (config.osd.fontscale, skin._hds_scaleaza) se aplica la toate
	trei, ca la skin.getListFont: inainte se marea numai fontul, iar marimea si inaltimea randului ramaneau cele din
	skin, deci textul casutelor (asezat cu ele) cobora si se taia jos de la 110 %. La 100 % nu se schimba nimic."""
	try:
		import skin
		scaleaza = getattr(skin, "_hds_scaleaza", int)
		if alias in skin.fonts:
			_n, m, h = skin.fonts[alias]
			return skin.parseFont(alias, ((1, 1), (1, 1))), scaleaza(m), scaleaza(h or inaltime)
	except Exception:
		scaleaza = int
	f = _factor()
	return gFont(nume, scaleaza(int(marime * f))), scaleaza(int(marime * f)), scaleaza(int(inaltime * f))


# ---------------------------------------------------------------- culegerea la vizionare

_culegator = None


def porneste_masuratori(session):
	"""Pornita o singura data, din ChannelSelection.__init__ (numele ramane pentru apelantii de dinainte). Tot de aici
	pleaca pregatirea indexului dupa pornire (INCALZIRE_MS), ca prima cautare sa nu astepte."""
	porneste_culegator(session)
	_incalzeste()


def porneste_culegator(session):
	"""Culegerea unita (Components/HdsCulegereCanale.py): rezolutia si codecul, accesul, PID-urile si pistele
	canalului privit, in baza unica, cu ceasurile bazei. Daca nu porneste, ramane culegerea pistelor de dinainte."""
	global _culegator
	if _culegator is None:
		try:
			from Components import HdsCulegereCanale
			_culegator = HdsCulegereCanale.porneste(session)
		except Exception as e:
			_jurnal('culegerea unita nu a pornit: %s' % e)
			try:
				_culegator = P.Culegator(session.nav)
			except Exception as e2:
				_jurnal('culegerea pistelor nu a pornit: %s' % e2)


def index_cu_piste(fortat=False):
	"""Indexul cautarii cu masuratorile si cu pistele din baza (acelasi pentru ecran si pentru pagina web), facut pe
	loc, pe firul care cheama (pentru apelantii care il vor imediat, de ex. pagina Canale; ecranul si /cautare folosesc
	cere_index / index_pentru_web)."""
	b = P.baza()
	return X.incarca(X.DIRECTOR, _pozitii_feed(), masurari_curente(), fortat, piste=b.trasaturi(),
		versiune_piste=b.versiune, limba_receptor=P.limba_receptor(), nume_limba=P.nume_limba)


# ---------------------------------------------------------------- pregatirea indexului in fundal

def index_la_zi():
	"""Indexul din memorie, daca e la zi fata de fisiere, masuratori si piste; altfel None. Cateva os.stat si doua
	versiuni, deci se poate chema la fiecare deschidere a cautarii si la fiecare cerere web."""
	index = X.din_memorie(X.semnatura(X.DIRECTOR, _pozitii_feed()))
	if index is None:
		return None
	b = P.baza()
	if not index.la_zi(masurari_curente(), b.versiune, P.limba_receptor()):
		return None
	return index


class _Pregatire(object):
	"""Un index nou: citirea lamedb-ului si a buchetelor si Index(...) pe un fir (HdsIndexCanale.construieste, numai
	fisiere si obiecte noi); apoi, pe firul enigma2, masuratorile si pistele (priviri peste baza unica, care se citesc
	numai de aici) in felii de cel mult FELIE_S (Index.aplica_treptat). La sfarsit indexul intra in memorie si merge la
	ascultatori. Indexul vechi din memorie nu se atinge cat timp se pregateste cel nou."""

	def __init__(self, fir=None, ceas=None):
		self.ascultatori = []
		self.gata = False
		self._rez = {}
		self._lucru = None
		self._pozitii = _pozitii_feed()
		self._ceas = (ceas or eTimer)()
		self._ceas.callback.append(self._tic)
		t0 = _timp()
		self._inceput = t0
		(fir or _fir_implicit)(self._construieste)
		self._ceas.start(40, False)

	def _construieste(self):
		# pe fir: nimic din enigma2, nimic comun
		try:
			self._rez["index"] = X.construieste(X.DIRECTOR, self._pozitii, complet=False)
		except Exception as e:
			self._rez["eroare"] = e
		self._rez["gata"] = True

	def _tic(self):
		try:
			if self._lucru is None:
				if not self._rez.get("gata"):
					return
				if "eroare" in self._rez:
					raise self._rez["eroare"]
				self.sem, self.index = self._rez["index"]
				b = P.baza()
				self._lucru = self.index.aplica_treptat(masurari_curente(), b.trasaturi(), b.versiune,
					P.limba_receptor(), P.nume_limba)
				# feliile la cativa ms una de alta: intre ele bucla enigma2 ia tastele si deseneaza
				self._ceas.start(4, False)
			# cel putin o bucata pe bataie, apoi cat mai incape in FELIE_S
			capat = _timp() + FELIE_S
			while True:
				next(self._lucru)
				if _timp() >= capat:
					break
		except StopIteration:
			self._sfarsit(self.index)
		except Exception as e:
			_jurnal('pregatirea indexului: %s' % e)
			self._sfarsit(None)

	def _sfarsit(self, index):
		self._ceas.stop()
		self.gata = True
		if _pregatire[0] is self:
			_pregatire[0] = None
		if index is not None:
			X.pune_in_memorie(self.sem, index)
			_jurnal('index: %d canale pregatite in %.0f ms (piste stiute la %d)' % (len(index.canale),
				(_timp() - self._inceput) * 1000, index.canale_cu_piste()))
		ascultatori, self.ascultatori = self.ascultatori, []
		for f in ascultatori:
			try:
				f(index)
			except Exception as e:
				_jurnal('dupa pregatirea indexului: %s' % e)


_pregatire = [None]
_ceasIncalzire = []


def _timp():
	import time
	return time.time()


def _fir_implicit(functie):
	import threading
	t = threading.Thread(target=functie, name="HdsCautareIndex")
	t.daemon = True
	t.start()
	return t


def porneste_pregatirea(la_gata=None):
	"""Pregateste un index nou in fundal (o singura pregatire odata; cererile care vin intre timp o asteapta pe
	aceeasi). la_gata(index sau None) se cheama pe firul enigma2."""
	lucrare = _pregatire[0]
	if lucrare is None:
		lucrare = _pregatire[0] = _Pregatire()
	if la_gata is not None:
		lucrare.ascultatori.append(la_gata)
	return lucrare


def nu_mai_astepta(la_gata):
	lucrare = _pregatire[0]
	if lucrare is not None and la_gata in lucrare.ascultatori:
		lucrare.ascultatori.remove(la_gata)


def cere_index(la_gata):
	"""Indexul la zi pentru ecran: la_gata(index) pe loc daca indexul din memorie e la zi (sau fara pregatirea in
	fundal, IN_FUNDAL = False), altfel dupa pregatirea in fundal. -> indexul vechi din memorie, de folosit pana atunci,
	sau None (niciunul inca: „Se pregătește lista de canale…”)."""
	if not IN_FUNDAL:
		index = index_cu_piste()
		la_gata(index)
		return index
	index = index_la_zi()
	if index is not None:
		la_gata(index)
		return index
	porneste_pregatirea(la_gata)
	return X.din_memorie()


def index_pentru_web():
	"""Indexul pentru pagina /cautare: cel din memorie, pe loc (la zi sau vechi, iar cel vechi porneste pregatirea unuia
	nou); None cat inca nu exista niciunul (pagina intreaba din nou peste putin)."""
	if not IN_FUNDAL:
		return index_cu_piste()
	index = index_la_zi()
	if index is not None:
		return index
	porneste_pregatirea()
	return X.din_memorie()


def _incalzeste():
	if not IN_FUNDAL or _ceasIncalzire:
		return
	try:
		ceas = eTimer()
		ceas.callback.append(lambda: index_la_zi() is None and porneste_pregatirea())
		ceas.start(INCALZIRE_MS, True)
		_ceasIncalzire.append(ceas)
	except Exception as e:
		_jurnal('pregatirea indexului dupa pornire: %s' % e)


def canale_de_citit(canale):
	"""Numai canalele DVB (din lamedb): fluxurile nu au PMT de citit."""
	return [c for c in canale if P.transponder_din_ref(c.ref) is not None]


def fara_piste(c):
	"""Canalul nu are inregistrare in baza pistelor (un canal citit fara nicio pista nu mai e „fara piste”)."""
	return not c.stiut


def _protejat(ref):
	"""Canalul e sub controlul parental? Atunci „Actualizeaza” nu il porneste (Components/ParentalControl.py 143)."""
	try:
		from Components.config import config
		pc = config.ParentalControl
		if not (pc.configured.value and pc.servicepinactive.value):
			return False
	except Exception:
		return False
	try:
		from Components.ParentalControl import parentalControl
		from enigma import eServiceReference
		return parentalControl.getProtectionLevel(eServiceReference(ref).toCompareString()) != -1
	except Exception:
		return True


def _inregistrari(session):
	try:
		return bool(session.nav.getRecordings())
	except Exception:
		return False


# actualizarea in curs (una singura) si ultima stare, pentru pagina web
_actualizare = {'ecran': None, 'ultima': None}


def stare_actualizare():
	ecran = _actualizare['ecran']
	if ecran is not None and ecran.actualizare is not None:
		return ecran.actualizare.stare()
	return _actualizare['ultima']


def opreste_actualizare():
	ecran = _actualizare['ecran']
	if ecran is not None:
		ecran.keyOpreste()
		return True
	return False


def sari_pozitia_actualizare():
	"""„Sari peste satelitul acesta” (tasta GALBEN pe televizor, butonul din /cautare). -> textul pozitiei lasate, sau
	None (nicio trecere in lucru)."""
	ecran = _actualizare['ecran']
	if ecran is not None:
		return ecran.keySari()
	return None


def text_ramas(secunde):
	"""„mai durează cam N minute”, dupa timpii masurati; sub un minut, „mai e mai puțin de un minut”."""
	if secunde < 60:
		return _('mai e mai puțin de un minut')
	minute = (int(secunde) + 30) // 60
	return ngettext('mai durează cam %d minut', 'mai durează cam %d minute', minute) % minute


def porneste_actualizare(session, grupuri, motor=None, la_gata=None, facute=None, inainte=0, neprinse=None, lasate=None):
	"""Porneste trecerea prin transpondere, cu ecranul de progres pe televizor. -> None, sau textul pentru om cand nu se
	poate (merge deja, o inregistrare tine tunerul, nimic de citit). facute / inainte: reluarea unei treceri oprite
	(P.reluare): cheile transponderelor terminate atunci si cate sunt din planul de acum. neprinse: pozitiile fara
	semnal niciodata incercate la cererea omului; lasate: cele scoase din plan (Components/HdsIstoricSemnal.py)."""
	if _actualizare['ecran'] is not None:
		return _('Actualizarea pistelor merge deja.')
	if not grupuri:
		return _('Niciun canal de satelit, cablu sau terestru de citit.')
	if _inregistrari(session):
		return _('În timpul unei înregistrări nu se poate: tunerul e ocupat.')
	if motor is None:
		motor = P.are_motor()
	kw = {'facute': facute, 'inainte': inainte} if facute else {}
	if neprinse:
		kw['neprinse'] = neprinse
	if lasate:
		kw['lasate'] = lasate
	if la_gata is None:
		session.open(HdsActualizarePiste, grupuri, motor, **kw)
	else:
		session.openWithCallback(la_gata, HdsActualizarePiste, grupuri, motor, **kw)
	return None


_ceasuriDupaScanare = []
INTREBARE_DUPA_SCANARE_S = 30     # fara raspuns: „Nu” (de ex. scanarea pornita din web, cu nimeni la televizor)


def intreaba_dupa_scanare(session, intarziere_ms=500, scanat=None):
	"""Chemata de Screens/ServiceScan.py cand se inchide o scanare reusita. Nu face nimic pe loc:
	ecranul de scanare se inchide fara sa astepte. Dupa `intarziere_ms`, cand stiva de ecrane s-a asezat, indexul se
	citeste din nou (lamedb tocmai s-a scris) si, daca sunt canale fara piste stiute, omul e intrebat daca le citeste
	acum, cu aceeasi trecere ca "Actualizeaza". Orice eroare ramane aici (jurnal), nu ajunge la scanare.
	scanat: ce a trecut prin scanare (Components/ServiceScan.hdsCeAScanat): intrebarea cuprinde numai canalele de
	acolo (canale_dupa_scanare); None = tot indexul."""
	try:
		ceas = eTimer()
		_ceasuriDupaScanare.append(ceas)

		def acum():
			if ceas in _ceasuriDupaScanare:
				_ceasuriDupaScanare.remove(ceas)
			try:
				_intreabaDupaScanare(session, scanat)
			except Exception as e:
				_jurnal('dupa scanare: %s' % e)
		ceas.callback.append(acum)
		ceas.start(intarziere_ms, True)
	except Exception as e:
		_jurnal('dupa scanare: %s' % e)


def _noteazaScanarea(scanat):
	"""Transponderele care au dat tabele in scanare au avut semnal: intra in istoricul semnalului
	(Components/HdsIstoricSemnal.py; calitatea nu se stie aici)."""
	transpondere = (scanat or {}).get('transpondere')
	if not transpondere:
		return
	try:
		from Components import HdsIstoricSemnal as I
		ist = I.istoric()
		for ns, tsid, onid in transpondere:
			ist.noteaza(ns, tsid, onid)
		# o scanare intreaga = o scriere (numai cand a adus ceva nou fata de ce era scris)
		if ist.nou:
			ist.salveaza()
	except Exception as e:
		_jurnal('istoricul semnalului dupa scanare: %s' % e)


def _intreabaDupaScanare(session, scanat=None):
	_noteazaScanarea(scanat)
	if _actualizare['ecran'] is not None or _inregistrari(session):
		return
	# lamedb tocmai s-a scris: indexul nou se pregateste in fundal (1-2 s pe receptor), apoi intrebarea
	cere_index(lambda index: index is not None and _intreabaDupaScanareCu(session, index, scanat))


def din_scanare(c, scanat):
	"""Canalul a trecut prin scanarea `scanat`? Pozitia lui (din index: pozitia orbitala, "cablu", "terestru") e printre
	pozitiile scanarii si, cand nucleul a dat transponderele scanate, transponderul lui (namespace, tsid, onid) e unul
	dintre ele. scanat None: orice canal."""
	if scanat is None:
		return True
	pozitii = scanat.get('pozitii')
	if pozitii is not None and getattr(c, 'poz', None) not in pozitii:
		return False
	transpondere = scanat.get('transpondere')
	if transpondere:
		tp = P.transponder_din_ref(getattr(c, 'ref', ''))
		if tp is None or (tp[1] & 0xFFFFFFFF, tp[2], tp[3]) not in transpondere:
			return False
	return True


def canale_dupa_scanare(index, scanat=None):
	"""Canalele DVB fara piste stiute care au trecut prin scanarea `scanat` (pentru intrebarea de dupa scanare)."""
	return [c for c in canale_de_citit(index.canale) if fara_piste(c) and din_scanare(c, scanat)]


def are_motor_pentru(grupuri):
	"""Antena cu motor conteaza numai cand trecerea are si canale de satelit (cablul si terestrul nu o misca)."""
	return any(isinstance(g.poz, int) for g in grupuri) and P.are_motor()


def _intreabaDupaScanareCu(session, index, scanat=None):
	if _actualizare['ecran'] is not None or _inregistrari(session):
		return
	canale = canale_dupa_scanare(index, scanat)
	grupuri = P.transpondere_din_canale(canale)
	if not grupuri:
		return
	motor = are_motor_pentru(grupuri)
	n = len(canale)
	text = ngettext('%d canal nu are încă pistele citite (teletext, subtitrări, limbi, HbbTV).',
		'%d canale nu au încă pistele citite (teletext, subtitrări, limbi, HbbTV).', n) % n + ' ' + \
		P.text_confirmare(grupuri, motor)

	def raspuns(da):
		if da:
			eroare = porneste_actualizare(session, grupuri, motor)
			if eroare:
				session.open(MessageBox, eroare, MessageBox.TYPE_INFO, timeout=8)
	session.openWithCallback(raspuns, MessageBox, text, MessageBox.TYPE_YESNO, timeout=INTREBARE_DUPA_SCANARE_S,
		default=False)


class HdsActualizarePiste(Screen):
	"""Progresul trecerii prin transpondere („Actualizeaza pistele”). EXIT opreste si revine la canalul de dinainte.
	Sta jos pe ecran, peste imagine; skinul HDSatelit nu are ecranul, deci se foloseste cel de aici."""
	skin = """
	<screen name="HdsActualizarePiste" resolution="1920,1080" position="center,center" size="1100,190" title="Pistele canalelor" flags="wfNoBorder" backgroundColor="#1010162A">
		<widget name="titlu" position="24,12" size="1052,44" font="Regular;30" foregroundColor="#00F2F4F8" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="stare" position="24,60" size="1052,40" font="Regular;26" foregroundColor="#00F5B83D" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="detalii" position="24,104" size="1052,36" font="Regular;22" foregroundColor="#00C9D2E3" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="indiciu" position="24,146" size="1052,32" font="Regular;20" foregroundColor="#00AEB9CC" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
	</screen>"""

	def __init__(self, session, grupuri, motor=False, facute=None, inainte=0, neprinse=None, lasate=None):
		Screen.__init__(self, session)
		self.setTitle(_('Pistele canalelor'))
		self.grupuri = grupuri
		self.motor = motor
		self.facute = facute
		self.inainte = inainte
		self.neprinse = neprinse
		self.lasate = lasate
		self.actualizare = None
		self['titlu'] = Label(_('Se citesc pistele canalelor'))
		self['stare'] = Label('')
		self['detalii'] = Label('')
		self['indiciu'] = Label(_('EXIT oprește și revine la canalul de dinainte'))
		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions'], {'cancel': self.keyOpreste, 'ok': self._nimic,
			'yellow': self.keySari}, -1)
		# pornirea dupa ce ecranul se vede (nu din onLayoutFinish: o trecere fara nimic de facut s-ar inchide acolo)
		self.ceasPornire = eTimer()
		self.ceasPornire.callback.append(self._porneste)
		self.onLayoutFinish.append(self._laLayout)
		_actualizare['ecran'] = self

	def _nimic(self):
		pass

	def _laLayout(self):
		try:
			from enigma import ePoint
			d = getDesktop(0).size()
			s = self.instance.size()
			self.instance.move(ePoint((d.width() - s.width()) // 2, d.height() - s.height() - int(60 * _factor())))
		except Exception:
			pass
		self.ceasPornire.start(200, True)

	def _porneste(self):
		if _culegator is not None:
			_culegator.opreste_pentru(True)
		self.actualizare = P.Actualizare(self.session.nav, self.grupuri, motor=self.motor, protejat=_protejat,
			la_pas=self._pas, la_sfarsit=self._sfarsit, facute=self.facute, inainte=self.inainte, neprinse=self.neprinse,
			lasate=self.lasate)
		_jurnal('actualizarea pistelor: %d transpondere, motor %s, reluata dupa %d' % (len(self.grupuri), self.motor,
			self.inainte if self.facute else 0))
		self.actualizare.porneste()

	def _pas(self, stare):
		text = _('Transponderul %d din %d') % (stare['pas'], stare['total'])
		if stare.get('rotire') and stare['pozitie']:
			# numai cand nucleul spune ca motorul merge (P.Actualizare.stare); semnalul se asteapta abia dupa, deci nu e
			# o blocare
			text += ' · ' + _('Antena se rotește spre %s') % stare['pozitie']
		elif stare.get('astept_semnal'):
			# dupa comanda de mutare, fara dovada ca motorul merge, cat tunerul nu a prins inca semnal: numai ce se stie
			# sigur, frecventa si secundele ramase pana la transponderul urmator
			text += (' · ' + stare['pozitie'] if stare['pozitie'] else '') + ' · ' + P.text_asteptare_semnal(stare)
		else:
			text += (' · ' + stare['pozitie'] if stare['pozitie'] else '') + (' · ' + stare['canal'] if stare['canal'] else '')
		self['stare'].setText(text)
		# la zero alta fraza: text_numar(0) e „Niciun canal”, facut pentru inceput de rand
		detalii = _('Pistele citite la %s') % X.text_numar(stare['citite']) if stare['citite'] > 0 else 			_('Nicio pistă citită încă')
		if stare.get('ramas_s') is not None and stare.get('activ'):
			detalii += ' · ' + text_ramas(stare['ramas_s'])
		self['detalii'].setText(detalii)
		# GALBEN numai cand e ceva de sarit; pozitia lasata se spune pana la pasul urmator al altei pozitii
		indiciu = _('EXIT oprește și revine la canalul de dinainte')
		if stare.get('poate_sari') and stare.get('pozitie'):
			indiciu += ' · ' + (_('GALBEN: sari peste satelitul acesta') if stare.get('satelit') else
				_('GALBEN: sari peste %s') % stare['pozitie'])
		self['indiciu'].setText(indiciu)

	def _sfarsit(self, stare):
		if _culegator is not None:
			_culegator.opreste_pentru(False)
		_actualizare['ultima'] = stare
		_actualizare['ecran'] = None
		_jurnal('actualizarea pistelor gata: %s' % stare)
		self.close(stare)

	def keySari(self):
		"""GALBEN: transponderele ramase de pe pozitia de acum se lasa, trecerea merge la pozitia urmatoare."""
		if self.actualizare is None:
			return None
		return self.actualizare.sari_pozitia()

	def keyOpreste(self):
		if self.actualizare is not None:
			self.actualizare.opreste()
		else:
			self.ceasPornire.stop()
			self._sfarsit({'activ': False, 'oprit': True, 'pas': 0, 'total': len(self.grupuri), 'canal': '',
				'pozitie': '', 'citite': 0, 'fara_semnal': 0, 'sarite': 0})


def masurari_curente():
	"""Rezolutia si codecul masurate, {cheie: [inaltime, progresiv, cod]}, din baza unica (privire desfacuta la
	cerere; aceeasi baza pe care o scrie culegerea, deci ce s-a masurat acum se vede imediat)."""
	return X.masuratori().toate()


def _curata_id(feed_id):
	return ''.join(ch for ch in str(feed_id) if ch.isalnum() or ch in '_-.')[:64]


# buchetele DAB+ / DVB-T2 si semnul (adresa releului) care arata ca buchetul are cel putin un post
_BUCHETE_FEED = (('dab', 'userbouquet.hds_dab.radio', b'/dab/'), ('t2', 'userbouquet.hds_t2.tv', b'/t2/'))
# rezultatul ultimei citiri, tinut dupa semnatura buchetelor (mtime, marime): listele (zeci de KB de JSON) nu se mai
# citesc pe firul enigma2 la fiecare index_la_zi
_POZITII = {'semn': None, 'rez': {}}


def _semn_buchete():
	import os
	semn = []
	for tip, buchet, _prefix in _BUCHETE_FEED:
		try:
			st = os.stat(os.path.join(X.DIRECTOR, buchet))
			semn.append((tip, st.st_mtime, st.st_size))
		except OSError:
			semn.append((tip, None, None))
	return tuple(semn)


def _buchet_cu_posturi(cale, prefix):
	"""Buchetul are cel putin o intrare a releului (cateva KB, citit numai cand i s-a schimbat semnatura)."""
	try:
		with open(cale, 'rb') as f:
			return prefix in f.read(262144)
	except (IOError, OSError):
		return False


def _pozitii_feed():
	"""{('dab'|'t2', feed): pozitie} din listele DAB+ / DVB-T2, numai pentru buchetele care au posturi. Un buchet
	gol (pus la pornire, inainte de prima scanare) nu are pozitii de cautat, deci listele nu se citesc."""
	import os
	semn = _semn_buchete()
	if semn == _POZITII['semn']:
		return _POZITII['rez']
	rez = {}
	for tip, buchet, prefix in _BUCHETE_FEED:
		if not _buchet_cu_posturi(os.path.join(X.DIRECTOR, buchet), prefix):
			continue
		try:
			from Hds.DabT2 import liste
			for tp in liste.incarca(tip).get('transpondere', []):
				poz = tp.get('pozitie')
				if not isinstance(poz, int):
					continue
				for f in tp.get('feeduri', []):
					if f.get('id') is not None:
						rez[(tip, _curata_id(f.get('id')))] = poz
		except Exception as e:
			_jurnal('pozitiile %s: %s' % (tip, e))
	_POZITII['semn'], _POZITII['rez'] = semn, rez
	return rez


# ---------------------------------------------------------------- memoria cautarii

# {False: lista TV, True: lista radio} -> starea ecranului la inchidere (vezi HdsCautareCanale._tineMinte), plus
# „ales” (cheia canalului pornit din rezultate) si „redeschide” (pus de dupa_zap, consumat de de_redeschis)
_memorie = {}


def cheie_canal(ref):
	"""Cheia de comparat a unei referinte text: aceeasi pentru Canal.ref (hex cu litere mari, din lamedb) si pentru
	referinta canalului pornit (HdsIndexCanale.cheie_din_ref; o referinta pe care nu o intelege ramane ea insasi)."""
	if not ref:
		return None
	return X.cheie_din_ref(ref) or ref


def _cheie(canal):
	return canal.cheie_mas or cheie_canal(canal.ref)


def memoria(radio):
	"""Starea tinuta minte a cautarii listei TV (radio False) sau radio, ori None."""
	return _memorie.get(bool(radio))


def uita_cautarea(radio=None):
	"""Sterge memoria unei liste (sau a amandurora, radio None)."""
	if radio is None:
		_memorie.clear()
	else:
		_memorie.pop(bool(radio), None)


def _implicita(radio, g, valori):
	# alegerea cu care se deschide cautarea din lista radio (Radio + DAB+ in „Tip”) nu e un filtru pus de om
	return radio and g == 'tip' and set(valori) <= X.TIPURI_NUMAI_RADIO


def are_criterii(m, radio=False):
	"""Memoria are un nume cautat sau un filtru pus de om (altfel rezultatele sunt lista obisnuita)."""
	if not m:
		return False
	if m.get('text'):
		return True
	return any(v and not _implicita(radio, g, v) for g, v in m.get('selectie', {}).items())


def dupa_zap(radio, ref):
	"""Lista de canale a pornit canalul `ref`, ales in rezultatele cautarii ei: la deschiderea urmatoare a listei
	cautarea se redeschide (de_redeschis), cu cursorul pe el."""
	m = _memorie.get(bool(radio))
	if m is not None:
		m['redeschide'] = True
		m['ales'] = cheie_canal(ref)


def de_redeschis(radio, ref_curent):
	"""Chemata la fiecare deschidere a listei de canale. -> True o singura data dupa dupa_zap, daca memoria are
	criterii si canalul de acum e tot cel pornit din rezultate; dupa P+/P-, cifre sau ghid lista se deschide obisnuit,
	acolo unde e canalul de acum (TEXT aduce tot cautarea tinuta minte). Semnul se sterge oricum, deci intoarcerea in
	lista dupa inchiderea cautarii nu o mai redeschide."""
	m = _memorie.get(bool(radio))
	if not m or not m.get('redeschide'):
		return False
	m['redeschide'] = False
	cheie = cheie_canal(ref_curent)
	return bool(cheie) and cheie == m.get('ales') and are_criterii(m, radio)


# ---------------------------------------------------------------- ecranul

class HdsCautareCanale(Screen, HelpableScreen):
	# rezerva pentru un skin fara acest ecran (skinul HDSatelit il are, cu aliasurile de fonturi HdsCautare*)
	skin = """
	<screen name="HdsCautareCanale" position="center,center" size="1200,660" title="Căutare canale">
		<widget name="filtre" position="10,10" size="1180,231" itemHeight="33" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
		<widget name="indiciu" position="10,246" size="880,30" font="Regular;19" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget name="numar" position="890,246" size="300,30" font="Regular;22" foregroundColor="#00F5B83D" halign="right" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<eLabel position="10,280" size="1180,1" backgroundColor="#00AEB9CC" zPosition="1" />
		<widget name="rezultate" position="10,284" size="1180,333" itemHeight="37" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" transparent="1" zPosition="2" />
		<widget name="gol" position="10,320" size="1180,80" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="key_red" position="10,624" size="290,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="306,624" size="290,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="602,624" size="290,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
		<widget name="key_blue" position="898,624" size="292,30" font="Regular;19" backgroundColor="#003D7BE0" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, radio=False, refCurent=None, redeschisa=False):
		"""refCurent: referinta canalului pornit acum (cursorul merge pe el daca e printre rezultate); redeschisa: lista
		de canale redeschide cautarea dupa un canal pornit din ea (focusul in lista de rezultate)."""
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.setTitle(_(TITLU))

		self.index = None
		self.text = ''
		self.inAsteptare = ''          # litera SMS inca neconfirmata (se mai poate schimba cu aceeasi tasta)
		self.selectie = dict((g, set()) for g in X.GRUPURI)
		if radio:
			self.selectie['tip'] = set(('radio', 'dab'))
		self.radio = radio
		self.randuri = ['nume']    # „nume” si grupurile vizibile, in ordinea randurilor de pe ecran (stanga, dreapta)
		self.rand = 0              # focusul: pozitia grupului in self.randuri
		self.asezare = [('nume', None)]   # randurile de pe ecran: (grupul din stanga, grupul din dreapta sau None)
		self.locuri = {'nume': (0, 0)}    # grup -> (randul de pe ecran, coloana 0 stanga / 1 dreapta)
		self.parte = 0             # coloana in care se intra de pe „Nume” cu Jos
		self.douaColoane = False
		self.inLista = False
		self.coloana = dict((g, 0) for g in X.GRUPURI)
		self.decalaj = dict((g, 0) for g in X.GRUPURI)
		self.rezultate = []
		# cate canale ar ramane cu fiecare optiune bifata (Index.numara_fatetat), dupa filtrele alese si numele cautat;
		# None fara filtre si fara text.
		# Optiunea cu 0 se deseneaza estompata (ca in paginile web Canale si Cautare, unde se vede si numarul)
		self.fatete = None
		self.sms = NumericalTextInput(nextFunc=self._literaConfirmata)
		self.sms.mapping = list(LITERE_SMS)
		self.modTastatura = None
		self.peButon = False       # pe randul „Nume”, focusul pe butonul „Actualizează pistele canalelor”
		self.ceasText = None       # cautarea dupa text amanata (AMANARE_TEXT_MS)
		self.inchis = False
		self.reface = False        # dupa „Actualizeaza pistele”: indexul se pune din nou chiar daca e acelasi obiect
		self.intrariFiltre = []    # randurile de pe ecran (vezi _puneFiltre)
		self._randuriRez = {}      # randurile rezultatelor gata construite, pe canal (vezi _randRezultat)
		self._generatieRez = None  # indexul, masuratorile si pistele cu care s-au construit
		self.randuriRez = 7        # cate randuri de rezultate incap in lista din skin (vezi _pregateste)
		self.masuraNume = None     # latimea numelui scris (Components/HdsCampText.Masura), pusa in _pregateste
		self.masuraTitlu = None    # latimea titlului ferestrei, cu fontul lui din skin (vezi _incapeTitlu)
		self.latimeTitlu = 0
		self.randuriVazute = 7     # cate randuri de filtre incap in lista din skin (vezi _paginaFiltre)
		self._pagina = None        # (lista de pe ecran, pagina ei), vezi _paginaFiltre
		self._afisat = {}          # ce e deja pe ecran (texte, gol vizibil, selectia listei), vezi _pune
		self._focusDorit = None    # grupul cu focus din memorie, pus la primul index (_randuriDinIndex)
		# cheile canalelor pe care se pune cursorul la primul index, in ordine (canalul de acum, cel de sub cursor la
		# inchidere); se golesc cand unul a fost gasit (_puneIndex)
		self.tinte = (cheie_canal(refCurent),) if refCurent else ()
		self._dinMemorie(redeschisa)

		self['filtre'] = MenuList(self.intrariFiltre, content=eListboxPythonMultiContent)
		self['rezultate'] = MenuList([], content=eListboxPythonMultiContent)
		self['numar'] = Label('')
		self['indiciu'] = Label('')
		self['gol'] = Label('')
		self['key_red'] = Button(_('Șterge filtrele'))
		self['key_green'] = Button(_('Tastatură'))
		self['key_yellow'] = Button(_('Șterge litera'))
		self['key_blue'] = Button(_('La listă'))

		# textele de ajutor (tasta HELP) sunt scurte: lista de ajutor a imaginii taie randurile lungi
		self['actiuni'] = HelpableActionMap(self, 'OkCancelActions', {
			'ok': (self.keyOk, _('Pornește filtrul sau canalul')),
			'cancel': (self.keyCancel, _('Înapoi la lista de canale')),
		}, -1)
		self['directii'] = HelpableActionMap(self, 'DirectionActions', {
			'up': (self.keyUp, _('Rândul de sus')),
			'down': (self.keyDown, _('Rândul de jos')),
			'left': (self.keyLeft, _('Opțiunea din stânga')),
			'right': (self.keyRight, _('Opțiunea din dreapta')),
			'upRepeated': self.keyUp,
			'downRepeated': self.keyDown,
			# tinuta apasat, sageata parcurge optiunile randului, dar nu sare in cealalta coloana
			'leftRepeated': self.keyLeftRepetat,
			'rightRepeated': self.keyRightRepetat,
			# ridicarea tastei: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action"
			'upUp': self._nimic,
			'downUp': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
		}, -1)
		self['culori'] = HelpableActionMap(self, 'ColorActions', {
			'red': (self.keyRosu, _('Șterge filtrele și numele')),
			'green': (self.keyTastatura, _('Tastatura de pe ecran')),
			'yellow': (self.keyStergeLitera, _('Șterge ultima literă')),
			'blue': (self.keyAlbastru, _('Filtrele sau lista de canale')),
		}, -1)
		cifre = dict((str(i), boundFunction(self.keyCifra, i)) for i in range(10))
		cifre['2'] = (boundFunction(self.keyCifra, 2), _('Numele, cu tastele 0-9'))
		self['cifre'] = HelpableActionMap(self, 'NumberActions', cifre, -1)
		self['text'] = HelpableActionMap(self, 'HdsCautareActions', {
			'cautare': (self.keyTastatura, _('Tastatura de pe ecran')),
		}, -1)
		self['ascii'] = ActionMap(['InputAsciiActions'], {'gotAsciiCode': self.keyAscii}, -1)
		# Backspace de pe o tastatura USB sterge ultima litera (data/keymap.xml; consola nu trimite caracterul lui)
		self['sterge'] = ActionMap(['HdsTastaturaStergeActions'], {'deleteBackward': self.keyStergeLitera}, -1)
		self['meniu'] = HelpableActionMap(self, 'MenuActions', {
			'menu': (self.keyMeniu, _('Actualizează pistele canalelor')),
		}, -1)

		self.onLayoutFinish.append(self._pregateste)
		self.onExecBegin.append(self._modAscii)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ memoria

	def _dinMemorie(self, redeschisa):
		"""Starea de la inchiderea de dinainte (textul, filtrele, coloanele, focusul); filtrele care nu mai exista in
		index se scot la primul index (_randuriDinIndex). Redeschisa dupa un canal pornit din rezultate: focusul in
		lista, cursorul pe canalul pornit."""
		m = _memorie.get(bool(self.radio))
		if m is None:
			return
		self.text = m['text']
		for g in X.GRUPURI:
			self.selectie[g] = set(m['selectie'].get(g, ()))
		self.coloana.update(m['coloana'])
		self.decalaj.update(m['decalaj'])
		self.parte = m['parte']
		self._focusDorit = m['focus']
		self.inLista = bool(m['inLista'] or redeschisa)
		self.tinte = tuple(k for k in self.tinte + ((m.get('ales'),) if redeschisa else ()) + (m.get('cursor'),) if k)

	def _tineMinte(self):
		"""Starea de acum in memoria listei (la inchidere, si cand se inchide cu un canal ales). Fara nume si fara
		filtre puse de om memoria se sterge: deschiderea urmatoare e o cautare noua (in lista radio cu Radio + DAB+
		alese, ca inainte), nu una cu „Tip” golit de rosu."""
		vechi = _memorie.get(bool(self.radio)) or {}
		cur = self['rezultate'].getCurrent() if self.rezultate else None
		m = {
			'text': self.text,
			'selectie': dict((g, set(v)) for g, v in self.selectie.items()),
			'coloana': dict(self.coloana),
			'decalaj': dict(self.decalaj),
			'parte': self.parte,
			'focus': self._focusDorit or (self.randuri[self.rand] if 0 <= self.rand < len(self.randuri) else 'nume'),
			'inLista': self.inLista,
			'cursor': _cheie(cur[0]) if cur else vechi.get('cursor'),
			'ales': vechi.get('ales'),
			'redeschide': False,
		}
		if are_criterii(m, self.radio):
			_memorie[bool(self.radio)] = m
		else:
			_memorie.pop(bool(self.radio), None)

	def _laTinta(self, chei):
		"""Cursorul listei pe primul canal gasit dintre chei, in ordinea lor. -> True daca l-a gasit."""
		if not self.rezultate:
			return False
		pozitii = {}
		for i, c in enumerate(self.rezultate):
			pozitii.setdefault(_cheie(c), i)
		for k in chei:
			if k in pozitii:
				self['rezultate'].moveToIndex(pozitii[k])
				return True
		return False

	# ------------------------------------------------------------ pregatire

	def _pregateste(self):
		fontRand, self.marimeRand, self.inaltimeRand = _font('HdsCautareRand', 'Regular', 28, 50)
		fontNume, _m, self.inaltimeRez = _font('HdsCautareNume', 'Regular', 32, 56)
		fontMic, _m, _h = _font('HdsCautareMic', 'Regular', 25, 56)
		f = self['filtre']
		f.l.setFont(0, fontRand)
		f.l.setItemHeight(self.inaltimeRand)
		f.selectionEnabled(False)
		# latimea numelui scris, in fontul randurilor (casuta „Nume”: cand nu mai incape, se vede coada lui)
		self.masuraNume = Masura(getattr(self, 'instance', None), fontRand)
		# latimea reala a titlului ferestrei, cu fontul etichetei de titlu din skin (_incapeTitlu)
		eticheta = self._etichetaTitlului()
		if eticheta is not None:
			try:
				self.latimeTitlu = eticheta.size().width()
				self.masuraTitlu = Masura(getattr(self, 'instance', None), eticheta.getFont())
			except Exception as e:
				_jurnal('titlul: %s' % e)
		r = self['rezultate']
		r.l.setFont(0, fontNume)
		r.l.setFont(1, fontMic)
		r.l.setItemHeight(self.inaltimeRez)
		r.l.setBuildFunc(self._randRezultat)
		self._randuriIntregi(f, self.inaltimeRand)
		self._randuriIntregi(r, self.inaltimeRez)
		try:
			self.latimeFiltre = f.instance.size().width()
			self.latimeRez = r.instance.size().width()
			self.randuriVazute = max(1, f.instance.size().height() // max(1, self.inaltimeRand))
			self.randuriRez = max(1, r.instance.size().height() // max(1, self.inaltimeRez))
		except Exception:
			self.latimeFiltre = self.latimeRez = int(1712 * _factor())
		self.douaColoane = self.latimeFiltre >= int(LATIME_DOUA_COLOANE * _factor())
		# etichetele randurilor cu un font mai mic (loc pentru optiuni in doua coloane), aliasul HdsCautareEticheta
		fontEticheta, self.marimeEticheta, _h = _font('HdsCautareEticheta', 'Regular', 24, self.inaltimeRand)
		f.l.setFont(1, fontEticheta)
		self.c = dict((k, _culoare(k)) for k in CULORI)
		self._coloaneRez()
		# textul casutelor de sus, nu centrat dupa conturul literelor (altfel „HD 720p” sta mai sus decat „SD”): un y
		# socotit o data din marimea fontului
		self.susOptiune = max(0, (self.inaltimeRand - 2 * max(4, self.inaltimeRand // 10) - int(self.marimeRand * 1.2)) // 2)
		self.susEticheta = max(0, (self.inaltimeRand - int(self.marimeEticheta * 1.2)) // 2)
		self.index = None
		try:
			vechi = cere_index(self._indexGata)
		except Exception as e:
			_jurnal('nu am putut citi lista de canale: %s' % e)
			vechi = X.Index([])
		if self.index is None:
			if vechi is not None:
				# indexul din memorie, putin vechi (masuratori sau piste noi): pe loc; cel nou il inlocuieste
				self._puneIndex(vechi)
			else:
				self._arataPregatire()

	@staticmethod
	def _randuriIntregi(lista, inaltime):
		"""Cu textul marit (randul creste cu procentul, _font), lista din skin nu mai are un numar intreg de randuri, iar
		ultimul rand se vedea taiat pe jumatate: lista se scurteaza la randuri intregi. La 100 % nu se schimba nimic."""
		try:
			import skin
			if skin.getFontScalePercent() <= 100 or lista.instance is None or inaltime <= 0:
				return
			s = lista.instance.size()
			h = max(inaltime, s.height() // inaltime * inaltime)
			if h != s.height():
				from enigma import eSize
				lista.instance.resize(eSize(s.width(), h))
		except Exception as e:
			_jurnal('randurile intregi: %s' % e)

	def _indexGata(self, index):
		if self.inchis:
			return
		if index is None:
			if self.index is None:
				index = X.Index([])
			else:
				return
		self._puneIndex(index)

	def _puneIndex(self, index):
		"""Indexul (primul sau unul mai nou): randurile si rezultatele din el, cu filtrele, textul si focusul pastrate;
		in lista de rezultate cursorul ramane pe acelasi canal."""
		if index is self.index and not self.reface:
			return
		self.reface = False
		aleasa = None
		if self.inLista and self.rezultate:
			cur = self['rezultate'].getCurrent()
			aleasa = cur and _cheie(cur[0])
		self.index = index
		self._randuriDinIndex()
		self.rezultate = None
		self._filtreaza()
		# canalul de acum sau cel din memorie, pana cand e gasit o data; apoi cel de sub cursor
		if self.tinte and self._laTinta(self.tinte):
			self.tinte = ()
		elif aleasa:
			self._laTinta((aleasa,))

	def _arataPregatire(self):
		"""Inainte de primul index: numai randul „Nume” si textul de asteptare."""
		# alta valoare decat True / False: primul rezultat (si unul gol) pune textul lui peste cel de asteptare
		self._afisat['gol'] = 'pregatire'
		self['gol'].setText(_('Se pregătește lista de canale…'))
		self['gol'].show()
		self._deseneazaFiltre()
		self._focusLista()

	def _randuriDinIndex(self):
		"""Randurile de aratat, dupa optiunile care exista (fara cele ale imaginii cand se cauta numai radio); focusul
		ramane pe acelasi grup daca mai exista, altfel pe acelasi rand de pe ecran."""
		vechi = self.randuri[self.rand] if 0 <= self.rand < len(self.randuri) else 'nume'
		if self._focusDorit is not None:
			vechi, self._focusDorit = self._focusDorit, None
		randVechi = self.locuri.get(vechi, (0, 0))[0]
		# o optiune aleasa dinainte (radio) care nu exista in lista nu ramane ascunsa si activa
		for g in X.GRUPURI:
			existente = set(v for v, _e, _n in self.index.optiuni.get(g, ()))
			self.selectie[g] &= existente
		vizibile = self.index.grupuri_vizibile(fara_imagine=X.numai_radio(self.selectie))
		for g in X.GRUPURI:
			if g not in vizibile:
				self.selectie[g] = set()
		self._aseaza(vizibile)
		if vechi in self.randuri:
			self.rand = self.randuri.index(vechi)
		else:
			r = min(randVechi, len(self.asezare) - 1)
			self.rand = self.randuri.index(self._grupPeRand(r, self.parte))

	def _aseaza(self, vizibile):
		"""self.asezare, self.locuri si self.randuri din grupurile vizibile: doua coloane (COLOANA_STANGA / DREAPTA) sau,
		pe un ecran ingust, o coloana (fiecare grup pe randul lui, in ordinea din GRUPURI)."""
		if self.douaColoane:
			stanga = [g for g in COLOANA_STANGA if g in vizibile]
			dreapta = [g for g in COLOANA_DREAPTA if g in vizibile] + \
				[g for g in vizibile if g not in COLOANA_STANGA and g not in COLOANA_DREAPTA]
		else:
			stanga, dreapta = list(vizibile), []
		asezare = [('nume', None)]
		for k in range(max(len(stanga), len(dreapta))):
			asezare.append((stanga[k] if k < len(stanga) else None, dreapta[k] if k < len(dreapta) else None))
		self.asezare = asezare
		self.locuri = {}
		self.randuri = []
		for r, (s, d) in enumerate(asezare):
			for parte, g in ((0, s), (1, d)):
				if g is not None:
					self.locuri[g] = (r, parte)
					self.randuri.append(g)

	def _grupPeRand(self, r, parte):
		"""Grupul din randul r de pe ecran, in coloana dorita, altfel cel din cealalta coloana."""
		s, d = self.asezare[r]
		if parte == 1 and d is not None:
			return d
		return s if s is not None else d

	def _randCurent(self):
		return self.locuri.get(self.randuri[self.rand], (0, 0))[0]

	def _coloaneRez(self):
		# la dreapta raman ~48 px pentru bara de derulare (desenata peste rand, nu langa el)
		w = self.latimeRez
		f = w / 1712.0
		x = int(16 * f)
		self.colNume = (x, int(660 * f))
		self.colPoz = (int(700 * f), int(160 * f))
		self.colTip = (int(870 * f), int(130 * f))
		self.colRez = (int(1010 * f), int(140 * f))
		self.colCod = (int(1160 * f), int(130 * f))
		self.colAcces = (int(1300 * f), w - int(1300 * f) - int(56 * f))

	def _modAscii(self):
		try:
			rc = eRCInput.getInstance()
			if self.modTastatura is None:
				self.modTastatura = rc.getKeyboardMode()
			rc.setKeyboardMode(rc.kmAscii)
		except Exception:
			pass

	def _laInchidere(self):
		self.inchis = True
		for m in (self.masuraNume, self.masuraTitlu):
			if m is not None:
				m.inchide()
		nu_mai_astepta(self._indexGata)
		if self.ceasText is not None:
			self.ceasText.stop()
		self.sms.nextKey()         # litera SMS inca in asteptare intra in text, apoi in memorie
		try:
			self._tineMinte()
		except Exception as e:
			_jurnal('memoria cautarii: %s' % e)
		try:
			if self.modTastatura is not None:
				eRCInput.getInstance().setKeyboardMode(self.modTastatura)
		except Exception:
			pass

	# ------------------------------------------------------------ filtrare si desen

	def _textCautat(self):
		return self.text + self.inAsteptare

	def _pune(self, cheie, valoare, fa):
		"""Schimba ceva pe ecran numai daca difera de ce e deja acolo. Nucleul ignora si el un text sau o vizibilitate
		neschimbata (elabel.cpp 139, ewidget.cpp 105 si 146, elistbox.cpp 396, ewindow.cpp 44); garda de aici tine
		evidenta in Python, iar testul numara apelurile."""
		if self._afisat.get(cheie, _NIMIC) != valoare:
			self._afisat[cheie] = valoare
			fa(valoare)

	def _filtreaza(self):
		if self.index is None:
			return
		rezultate = self.index.filtreaza(self._textCautat(), self.selectie)
		# aceleasi canale (de ex. o litera SMS inca in asteptare care nu schimba nimic): lista ramane pe ecran
		# neatinsa, cu cursorul unde era; altfel setList o redeseneaza toata (vezi _puneFiltre)
		if rezultate != self.rezultate:
			self.rezultate = rezultate
			# randurile primei pagini se construiesc acum, nu in timpul desenului (vezi _randRezultat)
			self._pregatesteRanduri(0, self.randuriRez + 1)
			self['rezultate'].setList([(c,) for c in rezultate])
			if rezultate:
				self['rezultate'].moveToIndex(0)
		self._pune('numar', X.text_numar(len(self.rezultate)), self['numar'].setText)
		self._arataGol(not self.rezultate)
		if self.inLista and not self.rezultate:
			self.inLista = False
		self.fatete = self._fatete()
		self._titlu()
		self._deseneazaFiltre()
		self._focusLista()

	def _fatete(self):
		"""Numaratoarea „fatetata” a optiunilor cu filtrele alese (Components/HdsIndexCanale.Index.numara_fatetat):
		optiunea X din randul G = canalele care au X si trec de toate celelalte randuri alese; None fara filtre."""
		text = self._textCautat()
		q = X.normalizeaza(text)
		if self.index is None or (not any(self.selectie.values()) and not q):
			return None
		# numerele tin cont si de numele cautat: se numara numai canalele care se potrivesc cu el (o lista mai mica decat
		# tot indexul); _filtreaza, care le cere, vine cel mult o data in AMANARE_TEXT_MS cat se scrie
		cheie = (id(self.index), self.index.masurari_marcaj[1], self.index.piste_aplicate, q,
			tuple(sorted((g, tuple(sorted(map(str, v)))) for g, v in self.selectie.items() if v)))
		vechi = getattr(self, '_fateteMemorie', None)
		if vechi is not None and vechi[0] == cheie and vechi[1] is self.index:
			return vechi[2]
		try:
			rez = self.index.numara_fatetat(self.index.canale_pentru_text(text), self.selectie)
		except Exception as e:
			print('[HdsCautareCanale] numerele optiunilor: %s' % e)
			return None
		self._fateteMemorie = (cheie, self.index, rez)
		return rez

	def _optiuneGoala(self, g, v):
		"""Cu optiunea bifata nu ar ramane niciun canal (tinand cont de celelalte randuri alese)."""
		return self.fatete is not None and self.fatete.get(g, {}).get(v, 1) == 0

	def _filtreazaText(self):
		"""Textul cautat s-a schimbat: randul „Nume” se redeseneaza pe loc, cautarea cel mult o data in
		AMANARE_TEXT_MS (o litera noua amana din nou cautarea care astepta)."""
		if self.index is None:
			self._deseneazaFiltre()
			return
		if not AMANARE_TEXT_MS:
			self._filtreaza()
			return
		if self.ceasText is None:
			self.ceasText = eTimer()
			self.ceasText.callback.append(self._filtreaza)
		self.ceasText.start(AMANARE_TEXT_MS, True)
		self._titlu()
		self._deseneazaFiltre()

	def _arataGol(self, gol):
		"""Mesajul „niciun canal”: show/hide numai cand lista trece din goala in plina sau invers."""
		if self._afisat.get('gol') == gol:
			return
		self._afisat['gol'] = gol
		if gol:
			self['gol'].setText(_('Niciun canal nu se potrivește. Roșu șterge filtrele.'))
			self['gol'].show()
		else:
			self['gol'].setText('')
			self['gol'].hide()

	def _titlu(self):
		if self.index is None:
			return
		# titlul intreg, cu toate filtrele: cand nu incape pe un rand, deruleaza (lib/gui/elabel.h)
		titlu = X.titlu_cautare(_(TITLU), self._textCautat(), self.index.parti_titlu(self.selectie))
		self._pune('titlu', titlu, self.setTitle)

	def _etichetaTitlului(self):
		"""Eticheta din skin care arata titlul ferestrei (widget source="Title" render="Label"; cea mai lata, celelalte
		cu sursa Title sunt semnele colorate de langa taste), sau None (alt skin: titlul in rama ferestrei)."""
		try:
			sursa = self['Title']
		except Exception:
			return None
		bune = []
		for r in getattr(self, 'renderer', None) or ():
			inst = getattr(r, 'instance', None)
			if getattr(r, 'source', None) is sursa and r.__class__.__name__ == 'Label' and inst is not None:
				try:
					bune.append((inst.size().width(), inst))
				except Exception:
					pass
		return max(bune, key=lambda x: x[0])[1] if bune else None

	def _incapeTitlu(self):
		"""(text) -> True cand textul incape in eticheta de titlu (latimea masurata cu fontul ei: un titlu cu litere late,
		ca „Â”, se taie cu „…” inainte de capatul ei, deci nu ajunge langa CALITATE din tema Pro); None fara eticheta de
		masurat: atunci titlul se taie dupa numarul de semne (MAX_TITLU), ca inainte."""
		m = self.masuraTitlu
		if m is None or m.eticheta is None or self.latimeTitlu <= 0:
			return None
		latime = self.latimeTitlu

		def incape(text):
			l = m.latime(text)
			return len(text) <= MAX_TITLU if l is None else l <= latime
		return incape

	def _focusLista(self):
		self._pune('selectie', self.inLista, self['rezultate'].selectionEnabled)
		self._pune('albastru', _('La filtre') if self.inLista else _('La listă'), self['key_blue'].setText)
		if self.inLista:
			indiciu = _('OK pornește canalul · Stânga/Dreapta: pagina · Sus la filtre')
		elif self.index is None:
			indiciu = _('0-9 scrii numele, ca la SMS · OK tastatura')
		elif self.randuri[self.rand] == 'nume' and self.peButon:
			indiciu = _('OK alegi canalele ale căror piste se citesc acum · Stânga înapoi la nume')
		elif self.randuri[self.rand] == 'nume':
			indiciu = _('0-9 scrii numele, ca la SMS · OK tastatura · Dreapta: Actualizează pistele · Jos la filtre')
		elif self.randuri[self.rand] == 'msunet':
			# mono / stereo / multicanal: din PMT (la „Actualizeaza pistele”) si din EIT (la vizionare)
			n, toate = self.index.cu_optiuni.get('msunet', 0), len(self.index.canale)
			indiciu = X.semnPiste(_('Mono, stereo sau 5.1 se știe la %s din %d · se află privind canalele sau cu Actualizează pistele') %
				(X.text_numar(n), toate))
		elif self.randuri[self.rand] in X.GRUPURI_PISTE:
			cu_piste, toate = self.index.canale_cu_piste(), len(self.index.canale)
			# la zero alta fraza: „la niciun canal”, nu „la Niciun canal” (text_numar e facut pentru inceput de rand)
			if cu_piste > 0:
				text = _('Pistele se știu la %s din %d · butonul Actualizează pistele e sus, lângă Nume') % (
					X.text_numar(cu_piste), toate)
			else:
				text = _('Pistele nu se știu încă la niciun canal din %d · butonul Actualizează pistele e sus, lângă Nume') % toate
			indiciu = X.semnPiste(text)
		elif self.douaColoane:
			indiciu = _('Stânga/Dreapta alegi sau treci în cealaltă coloană · OK pornești sau oprești')
		else:
			indiciu = _('Stânga/Dreapta alegi · OK pornești sau oprești · Jos mai departe')
		self._pune('indiciu', indiciu, self['indiciu'].setText)

	def _latimeOptiune(self, text):
		return max(int(self.marimeRand * 3.2), int(len(text) * self.marimeRand * 0.56) + int(self.marimeRand * 1.2))

	def _geometrie(self):
		"""(x-ul etichetei, latimea ei, fontul ei, x-ul optiunilor fata de inceputul celulei, x-ul coloanei din dreapta,
		x-ul liniei dintre coloane), la scara listei (1712 px in skinul HDSatelit)."""
		w = self.latimeFiltre
		f = w / 1712.0
		if self.douaColoane:
			# eticheta de 168 px (15-16 litere mici, si in alte limbi); in stanga raman 594 px pentru optiuni, destul
			# pentru cel mai lat rand (Rezolutie: SD, HD 720p, Full HD 1080, 4K = 577 px)
			xs = int(w * PARTE_STANGA)
			return int(16 * f), int(168 * f), 1, int(190 * f), xs + int(16 * f), xs + int(7 * f)
		return int(20 * f), int(196 * f), 0, int(228 * f), w, w

	def _deseneazaFiltre(self):
		c = self.c
		h = self.inaltimeRand
		w = self.latimeFiltre
		f = w / 1712.0
		xEticheta, lEticheta, fontEticheta, xOptiuni, xDreapta, xLinie = self._geometrie()
		margine = max(4, h // 10)
		inaltimeCutie = h - 2 * margine
		chenar = max(2, int(3 * f))
		rand_focus = None if self.inLista else self.randuri[self.rand]
		intrari = []
		for stanga, dreapta in self.asezare:
			e = [None]
			if dreapta is not None or (self.douaColoane and stanga != 'nume'):
				# linia subtire dintre coloane, pe fiecare rand de filtre
				e.append(MultiContentEntryText(pos=(xLinie, margine), size=(max(1, int(2 * f)), inaltimeCutie), font=0,
					text='', backcolor=c['pista'], backcolor_sel=c['pista']))
			for x0, x1, g in ((0, xDreapta - int(16 * f) if xDreapta < w else w, stanga), (xDreapta, w, dreapta)):
				if g is None:
					continue
				focus = g == rand_focus
				if focus:
					e.append(MultiContentEntryText(pos=(x0, margine), size=(max(4, int(6 * f)), inaltimeCutie), font=0,
						text='', backcolor=c['focus'], backcolor_sel=c['focus']))
				eticheta = _('Nume') if g == 'nume' else X.titlu(g)
				sus = self.susEticheta if fontEticheta else self.susOptiune + margine
				e.append(MultiContentEntryText(pos=(x0 + xEticheta, sus), size=(lEticheta, h - sus), font=fontEticheta,
					flags=RT_HALIGN_LEFT, text=eticheta,
					color=c['focus'] if focus else c['eticheta'], color_sel=c['focus'] if focus else c['eticheta']))
				if g == 'nume':
					text = self._textCautat()
					focusText = focus and not self.peButon
					if text:
						arata, culoare = text + ('_' if focusText else ''), c['text']
					else:
						arata, culoare = ('_ ' if focusText else '') + _('Scrie cu tastele 0-9 sau apasă OK pentru tastatură'), c['stins']
					# butonul „Actualizează pistele canalelor” in capatul randului (Dreapta de pe „Nume”, OK)
					buton = _('Actualizează pistele canalelor') if self.index is not None else ''
					latButon = self._latimeOptiune(buton) if buton else 0
					xButon = w - int(16 * f) - latButon
					capatText = (xButon - int(12 * f)) if buton else (w - int(16 * f))
					latCaseta = capatText - xOptiuni
					chenarCaseta = c['alb'] if focusText else c['pista']
					if text and self._numePreaLung('  ' + arata, latCaseta - 2 * chenar):
						# numele nu mai incape: tot randul se muta spre stanga si se vede coada lui (ce scrii acum, cu
						# „_”), taiat la marginea casetei. Casuta cu chenarul, apoi textul aliniat la dreapta, cu o margine
						# cat cele doua spatii din stanga si de o parte si de alta (Components/HdsCampText.py)
						spatiu = max(chenar, int(self.marimeRand * 0.5))
						e.append(MultiContentEntryText(pos=(xOptiuni, margine), size=(latCaseta, inaltimeCutie), font=0,
							flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text='', backcolor=c['pista'], backcolor_sel=c['pista'],
							border_width=chenar, border_color=chenarCaseta))
						e.append(MultiContentEntryText(pos=(xOptiuni + chenar + spatiu, margine + chenar), size=(latCaseta -
							2 * (chenar + spatiu), inaltimeCutie - 2 * chenar), font=0, flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER,
							text=arata, color=culoare, color_sel=culoare, backcolor=c['pista'], backcolor_sel=c['pista']))
					else:
						e.append(MultiContentEntryText(pos=(xOptiuni, margine), size=(latCaseta, inaltimeCutie),
							font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text='  ' + arata, color=culoare, color_sel=culoare,
							backcolor=c['pista'], backcolor_sel=c['pista'], border_width=chenar, border_color=chenarCaseta))
					if buton:
						# casuta cu chenarul, apoi textul de sus, ca la optiuni
						peEl = focus and self.peButon
						e.append(MultiContentEntryText(pos=(xButon, margine), size=(latButon, inaltimeCutie), font=0,
							flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text='', backcolor=c['pista'],
							backcolor_sel=c['pista'], border_width=chenar, border_color=c['alb'] if peEl else c['pista']))
						e.append(MultiContentEntryText(pos=(xButon + chenar, margine + self.susOptiune), size=(latButon -
							2 * chenar, inaltimeCutie - self.susOptiune - chenar), font=0, flags=RT_HALIGN_CENTER,
							text=buton, color=c['text'], color_sel=c['text'], backcolor=c['pista'], backcolor_sel=c['pista']))
				else:
					self._randFiltru(e, g, focus, x0 + xOptiuni, x1 - int(16 * f), margine, inaltimeCutie, chenar)
			intrari.append(e)
		self._puneFiltre(intrari)
		self._paginaFiltre()

	def _numePreaLung(self, scris, latime):
		"""Numele scris (cum se deseneaza, cu spatiile din fata si „_”) nu incape in `latime` pixeli? Fara masurare
		(alt nucleu, probele de pe PC): False, adica desenul de pana acum."""
		m = self.masuraNume
		return m is not None and m.preaLat(scris, latime)

	def _puneFiltre(self, intrari):
		"""Pe ecran se redeseneaza numai randurile schimbate (la OK pe o optiune: un singur rand).

		Receptorul deseneaza direct in imaginea care se vede (fara a doua pagina): setList ar sterge toata lista
		si ar scrie randurile abia dupa, iar stergerea s-ar vedea ca o clipire neagra. invalidateEntry reface
		doar banda randului schimbat. Lista data la setList ramane acelasi obiect, schimbat pe loc."""
		vechi = self.intrariFiltre
		if len(vechi) != len(intrari) or self['filtre'].list is not vechi:
			self.intrariFiltre = intrari
			self['filtre'].setList(intrari)
			return
		for i, e in enumerate(intrari):
			if e != vechi[i]:
				vechi[i] = e
				self['filtre'].l.invalidateEntry(i)

	def _paginaFiltre(self):
		"""Randurile de filtre pot fi mai multe decat incap (pe o coloana, 13 cu pistele; skinul HDSatelit are loc de 7):
		lista trece la pagina randului cu focus, pagina cu pagina, ca orice lista enigma2 (moveSelectionTo, elistbox.cpp
		203-225); in aceeasi pagina nu se misca nimic. Dupa un setList (alta lista) pagina se pune din nou."""
		if self.inLista:
			return
		r = self._randCurent()
		pagina = (self['filtre'].list, r // max(1, self.randuriVazute))
		if self._pagina is None or self._pagina[0] is not pagina[0] or self._pagina[1] != pagina[1]:
			self._pagina = pagina
			self['filtre'].moveToIndex(r)

	def _randFiltru(self, e, g, focus, x0, x1, margine, h, chenar):
		c = self.c
		optiuni = self.index.optiuni.get(g, ())
		if not optiuni:
			return
		col = min(self.coloana[g], len(optiuni) - 1)
		self.coloana[g] = col
		spatiu = max(6, int(self.marimeRand * 0.45))
		sageata = int(self.marimeRand * 1.1)
		# decalajul: optiunea cu focus trebuie sa se vada
		start = min(self.decalaj[g], col)
		while True:
			x = x0 + (sageata if start > 0 else 0)
			ultima = start - 1
			for k in range(start, len(optiuni)):
				lat = self._latimeOptiune(optiuni[k][1])
				rezerva = sageata if k < len(optiuni) - 1 else 0
				if x + lat + rezerva > x1 and k > start:
					break
				x += lat + spatiu
				ultima = k
			if col <= ultima or start >= col:
				break
			start += 1
		self.decalaj[g] = start
		x = x0
		if start > 0:
			e.append(MultiContentEntryText(pos=(x, 0), size=(sageata, h + 2 * margine), font=0,
				flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text='<', color=c['eticheta'], color_sel=c['eticheta']))
			x += sageata
		for k in range(start, ultima + 1):
			v, eticheta, _n = optiuni[k]
			lat = self._latimeOptiune(eticheta)
			ales = v in self.selectie[g]
			cursor = focus and k == col
			fundal = c['ales'] if ales else c['pista']
			culoare = c['alesText'] if ales else (c['stins'] if self._optiuneGoala(g, v) else c['text'])
			# textul de sus, la acelasi y in toate casutele (centrat dupa conturul literelor, „HD 720p” ar sta mai sus
			# decat „SD”); chenarul ramane cel al casutei intregi
			e.append(MultiContentEntryText(pos=(x, margine), size=(lat, h), font=0,
				flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text='', backcolor=fundal, backcolor_sel=fundal,
				border_width=chenar, border_color=c['alb'] if cursor else fundal))
			e.append(MultiContentEntryText(pos=(x + chenar, margine + self.susOptiune), size=(lat - 2 * chenar,
				h - self.susOptiune - chenar), font=0, flags=RT_HALIGN_CENTER, text=eticheta, color=culoare,
				color_sel=culoare, backcolor=fundal, backcolor_sel=fundal))
			x += lat + spatiu
		if ultima < len(optiuni) - 1:
			e.append(MultiContentEntryText(pos=(x1 - sageata, 0), size=(sageata, h + 2 * margine), font=0,
				flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text='>', color=c['eticheta'], color_sel=c['eticheta']))

	def _generatie(self):
		i = self.index
		return None if i is None else (id(i), i.masurari_marcaj[1], i.piste_aplicate)

	def _randRezultat(self, canal):
		"""Randul unui canal din lista de rezultate (functia de constructie a listei), din memorie cand e gata.

		Nucleul o cheama in timpul desenului, dupa ce a sters banda randului; pe receptor desenul se vede pe loc, deci cat
		lucreaza Python-ul aici banda ramane goala (palpairea de la bifarea unui filtru). Randurile care urmeaza sa se
		vada se construiesc inainte (_pregatesteRanduri), iar aici raman citiri din memorie. Memoria se goleste la alt
		index sau cand s-au aplicat alte masuratori ori piste (alte etichete pe randuri)."""
		gen = self._generatie()
		if gen != self._generatieRez:
			self._generatieRez = gen
			self._randuriRez = {}
		r = self._randuriRez.get(id(canal))
		if r is None or r[0] is not canal:
			if len(self._randuriRez) >= MAX_RANDURI_GATA:
				self._randuriRez = {}
			r = self._randuriRez[id(canal)] = (canal, self._construiesteRand(canal))
		return r[1]

	def _pregatesteRanduri(self, de_la, pana_la):
		"""Randurile rezultatelor [de_la, pana_la) construite in memorie, inainte ca lista sa le deseneze."""
		for canal in (self.rezultate or ())[max(0, de_la):max(0, pana_la)]:
			self._randRezultat(canal)

	def _pregatesteInJurul(self, pas):
		"""Inainte de o miscare in lista de rezultate: randurile paginii in care poate ajunge cursorul (pas = cate
		randuri sare: 1 la Sus/Jos, o pagina la Stanga/Dreapta; negativ in sus)."""
		i = self['rezultate'].getSelectionIndex() or 0
		n = self.randuriRez + 1
		if pas > 0:
			self._pregatesteRanduri(i, i + pas + n)
		else:
			self._pregatesteRanduri(i + pas - n, i + 1)

	def _construiesteRand(self, canal):
		c = self.c
		h = self.inaltimeRez
		acces = canal.eticheta_acces()
		culoareAcces = c['bun'] if canal.acces == 'fta' else c['chihlimbar']
		culoareCod = c['text2'] if canal.cod_sigur else c['stins']
		rez, cod = canal.rez_eticheta, canal.eticheta_cod()
		culoareRez = c['text']
		if canal.radio and not cod:
			# un post de radio nu are imagine: in coloanele imaginii, sunetul (daca se stie), in culoarea felului
			# („Radio”), ca „MPEG” sa nu se citeasca drept codarea imaginii („MPEG-2” la canalele TV)
			rez, cod = X.eticheta_mod_sunet(canal), X.eticheta_format_sunet(canal)
			culoareCod = culoareRez = c['focus']
		colRez = self.colRez
		if not rez and not cod and getattr(canal, 'ansamblu', ''):
			# un post DAB+ / DVB-T2 din satelit fara date de sunet: ansamblul lui, pe coloanele imaginii si ale codarii
			rez = canal.ansamblu
			colRez = (self.colRez[0], self.colCod[0] + self.colCod[1] - self.colRez[0])
			culoareRez = c['text2']
		v = RT_VALIGN_CENTER
		return [None,
			MultiContentEntryText(pos=(self.colNume[0], 0), size=(self.colNume[1], h), font=0, flags=RT_HALIGN_LEFT | v,
				text=canal.nume_afisat(), color=c['stins'] if canal.fara_nume else c['text'], color_sel=c['alb']),
			MultiContentEntryText(pos=(self.colPoz[0], 0), size=(self.colPoz[1], h), font=1, flags=RT_HALIGN_LEFT | v,
				text=canal.eticheta_pozitie(), color=c['text2'], color_sel=c['alb']),
			MultiContentEntryText(pos=(self.colTip[0], 0), size=(self.colTip[1], h), font=1, flags=RT_HALIGN_LEFT | v,
				text=X.eticheta_tip(canal.tip), color=c['focus'], color_sel=c['alb']),
			MultiContentEntryText(pos=(colRez[0], 0), size=(colRez[1], h), font=1, flags=RT_HALIGN_LEFT | v,
				text=rez, color=culoareRez, color_sel=c['alb']),
			MultiContentEntryText(pos=(self.colCod[0], 0), size=(self.colCod[1], h), font=1, flags=RT_HALIGN_LEFT | v,
				text=cod, color=culoareCod, color_sel=c['alb']),
			MultiContentEntryText(pos=(self.colAcces[0], 0), size=(self.colAcces[1], h), font=1, flags=RT_HALIGN_RIGHT | v,
				text=acces, color=culoareAcces, color_sel=c['alb']),
		]

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def _focusPe(self, g):
		if g != 'nume':
			self.peButon = False
		self.rand = self.randuri.index(g)
		r, parte = self.locuri[g]
		if r > 0:
			self.parte = parte

	def keyUp(self):
		"""Randul de sus, in aceeasi coloana (in cealalta, daca aceasta nu are grup acolo); din lista, ultimul rand."""
		if self.index is None:
			return
		if self.inLista:
			if self['rezultate'].getSelectionIndex() > 0:
				self._pregatesteInJurul(-1)
				self['rezultate'].up()
				return
			self.inLista = False
			self._focusPe(self._grupPeRand(len(self.asezare) - 1, self.parte))
		else:
			r = self._randCurent()
			if r == 0:
				return
			self._focusPe(self._grupPeRand(r - 1, self.parte))
		self._deseneazaFiltre()
		self._focusLista()

	def keyDown(self):
		"""Randul de jos, in aceeasi coloana (de pe „Nume”, in coloana folosita ultima); de pe ultimul rand, lista."""
		if self.inLista:
			self._pregatesteInJurul(1)
			self['rezultate'].down()
			return
		if self.index is None:
			return
		r = self._randCurent()
		if r == 0 and self.peButon:
			# de pe buton, Jos intra in coloana din dreapta (butonul sta deasupra ei)
			self.peButon = False
			self.parte = 1
		if r < len(self.asezare) - 1:
			self._focusPe(self._grupPeRand(r + 1, self.parte))
		elif self.rezultate:
			self.inLista = True
		else:
			return
		self._deseneazaFiltre()
		self._focusLista()

	def keyLeft(self):
		self._muta(-1, True)

	def keyRight(self):
		self._muta(1, True)

	def keyLeftRepetat(self):
		self._muta(-1, False)

	def keyRightRepetat(self):
		self._muta(1, False)

	def _muta(self, pas, sare=False):
		"""Optiunea vecina din rand. La capatul randului, o apasare noua (sare) trece in cealalta coloana: Dreapta de pe
		ultima optiune din stanga duce pe prima optiune din dreapta, Stanga de pe prima din dreapta pe ultima din stanga."""
		if self.inLista:
			self._pregatesteInJurul(pas * self.randuriRez)
			if pas < 0:
				self['rezultate'].pageUp()
			else:
				self['rezultate'].pageDown()
			return
		g = self.randuri[self.rand]
		if g == 'nume':
			# pe „Nume”: Dreapta trece pe butonul „Actualizează pistele canalelor”, Stanga inapoi pe nume
			if self.index is not None and sare and self.peButon != (pas > 0):
				self.peButon = pas > 0
				self._deseneazaFiltre()
				self._focusLista()
			return
		n = len(self.index.optiuni.get(g, ()))
		col = self.coloana[g] + pas
		if 0 <= col < n:
			self.coloana[g] = col
			self._deseneazaFiltre()
			return
		if not sare:
			return
		r, parte = self.locuri[g]
		if parte + pas not in (0, 1):
			return
		vecin = self.asezare[r][parte + pas]
		if vecin is None:
			return
		m = len(self.index.optiuni.get(vecin, ()))
		self.coloana[vecin] = 0 if pas > 0 else max(0, m - 1)
		self._focusPe(vecin)
		self._deseneazaFiltre()
		self._focusLista()

	def keyOk(self):
		if self.inLista:
			cur = self['rezultate'].getCurrent()
			if cur:
				self.close(cur[0])
			return
		g = self.randuri[self.rand]
		if g == 'nume':
			if self.peButon:
				self.keyMeniu()
			else:
				self.keyTastatura()
			return
		if self.index is None:
			return
		optiuni = self.index.optiuni.get(g, ())
		if not optiuni:
			return
		v = optiuni[min(self.coloana[g], len(optiuni) - 1)][0]
		radio = X.numai_radio(self.selectie)
		if v in self.selectie[g]:
			self.selectie[g].discard(v)
		else:
			self.selectie[g].add(v)
		if X.numai_radio(self.selectie) != radio:
			# numai radio (sau nu mai): randurile imaginii se ascund sau apar
			self._randuriDinIndex()
		self._filtreaza()

	def keyCancel(self):
		self.close(None)

	# ------------------------------------------------------------ „Actualizeaza pistele” (MENU sau butonul de sus)

	def keyMeniu(self):
		if self.index is None:
			return
		toate = canale_de_citit(self.index.canale)
		gasite = canale_de_citit(self.rezultate or [])
		fara = [c for c in toate if fara_piste(c)]
		lista = []
		# randuri scurte, cu numarul la vedere (titlul alegerii spune ce se actualizeaza)
		if gasite and len(gasite) < len(toate):
			lista.append((_('Canalele găsite acum (%d)') % len(gasite), gasite))
		if fara:
			lista.append((_('Canalele fără piste știute (%d)') % len(fara), fara))
		if toate:
			lista.append((_('Toate canalele (%d)') % len(toate), toate))
		if not lista:
			self.session.open(MessageBox, _('Niciun canal de satelit, cablu sau terestru de citit.'), MessageBox.TYPE_INFO,
				timeout=8)
			return
		self.session.openWithCallback(self._aleasActualizare, ChoiceBox,
			title=X.semnPiste(_('Actualizează pistele: teletext, subtitrări, sunetul, HbbTV')), list=lista)

	def _aleasActualizare(self, alegere):
		if not alegere:
			return
		grupuri = P.transpondere_din_canale(alegere[1])
		if not grupuri:
			return
		if _inregistrari(self.session):
			self.session.open(MessageBox, _('În timpul unei înregistrări nu se poate: tunerul e ocupat.'),
				MessageBox.TYPE_INFO, timeout=8)
			return
		motor = P.are_motor()
		rel = P.reluare(grupuri, P.citeste_stare())
		if rel is None:
			self._intreaba(grupuri, motor)
			return
		ramase, n, facute = rel

		def ales(raspuns):
			if not raspuns:
				return
			if raspuns[1] == 'continua':
				self._intreaba(ramase, motor, facute, n)
			else:
				self._intreaba(grupuri, motor)
		self.session.openWithCallback(ales, ChoiceBox, title=P.text_reluare(n, len(grupuri)),
			list=[(_('Continuă'), 'continua'), (_('De la capăt'), 'capat')])

	def _intreaba(self, grupuri, motor, facute=None, inainte=0):
		# pozitiile pe care receptorul n-a prins niciodata semnal (Components/HdsIstoricSemnal.py): lasate, sau incercate
		# la alegere (atunci lasate dupa P.Actualizare.PRAG_NEPRINSA transpondere fara acord)
		neprinse = P.pozitii_neprinse(grupuri)
		fara = P.fara_pozitii(grupuri, neprinse)
		if neprinse and fara:
			# intai daca se incearca si ele (NU, implicit: lasate), apoi intrebarea obisnuita, cu durata planului ales
			def ales(da=None):
				if da:
					self._confirma(grupuri, motor, facute, inainte, neprinse=neprinse)
				else:
					self._confirma(fara, motor, facute, inainte, lasate=neprinse)
			self.session.openWithCallback(ales, MessageBox, P.text_intrebare_neprinse(neprinse), MessageBox.TYPE_YESNO,
				default=False)
			return
		self._confirma(grupuri, motor, facute, inainte)

	def _confirma(self, grupuri, motor, facute=None, inainte=0, neprinse=None, lasate=None):
		self.session.openWithCallback(lambda da=None: da and self._porneste(grupuri, motor, facute, inainte, neprinse,
			lasate), MessageBox, P.text_confirmare(grupuri, motor), MessageBox.TYPE_YESNO, default=not motor)

	def _porneste(self, grupuri, motor, facute=None, inainte=0, neprinse=None, lasate=None):
		eroare = porneste_actualizare(self.session, grupuri, motor, self._dupaActualizare, facute, inainte, neprinse,
			lasate)
		if eroare:
			self.session.open(MessageBox, eroare, MessageBox.TYPE_INFO, timeout=8)

	def _dupaActualizare(self, stare=None):
		"""Pistele noi intra in filtre: indexul nou (pregatit in fundal) inlocuieste pe cel de acum, randurile se refac
		(pot aparea randuri si limbi noi), rezultatele o data (_puneIndex)."""
		# acelasi obiect (indexul din memorie refacut pe loc) se pune si el din nou
		self.reface = True
		try:
			cere_index(self._indexGata)
		except Exception as e:
			_jurnal('dupa actualizare: %s' % e)
			return
		if stare:
			self.session.open(MessageBox, P.text_rezultat(stare), MessageBox.TYPE_INFO, timeout=10)

	def keyRosu(self):
		"""„Șterge filtrele”: cautare noua. Numele si toate filtrele sterse, memoria listei uitata (lista de canale nu
		mai redeschide cautarea), rezultatele = lista obisnuita (cursorul sus cand s-au schimbat), focusul pe „Nume”."""
		if self.index is None:
			return
		self.sms.nextKey()
		self.text, self.inAsteptare = '', ''
		uita_cautarea(self.radio)
		self.tinte = ()
		radio = X.numai_radio(self.selectie)
		for g in X.GRUPURI:
			self.selectie[g] = set()
		self.inLista = False
		self.peButon = False
		self._focusPe('nume')
		if radio:
			self._randuriDinIndex()
		self._filtreaza()

	def keyAlbastru(self):
		if self.inLista:
			self.inLista = False
		elif self.rezultate:
			self.inLista = True
		else:
			return
		self._deseneazaFiltre()
		self._focusLista()

	def keyStergeLitera(self):
		if self.inAsteptare:
			self.sms.nextKey()
			self.inAsteptare = ''
		elif self.text:
			self.text = self.text[:-1]
		else:
			return 1
		self._filtreazaText()
		return 1

	def keyCifra(self, n):
		litera = self.sms.getKey(n)      # alta tasta decat inainte: litera veche se confirma (_literaConfirmata)
		if litera is None:
			return
		self.inAsteptare = litera
		if len(LITERE_SMS[n]) == 1:      # 0 si 1: o singura valoare, se confirma pe loc
			self.sms.nextChar()
		self._filtreazaText()

	def _literaConfirmata(self):
		if self.inAsteptare:
			self.text += self.inAsteptare
			self.inAsteptare = ''
			if self.index is not None:
				self._deseneazaFiltre()

	def keyAscii(self):
		"""O tastatura USB (sau tastatura PC-ului in emulator). Ce nu e litera sau semn (Enter, Esc) nu se
		consuma (0), ca OK si EXIT sa ajunga la harta lor."""
		try:
			cod = getPrevAsciiCode()
		except Exception:
			return 0
		if cod in (8, 127):
			self.keyStergeLitera()
			return 1
		ch = chr(cod)
		if not ch.isprintable():
			return 0
		self.sms.nextKey()
		self.text += self.inAsteptare + ch
		self.inAsteptare = ''
		self._filtreazaText()
		return 1

	def keyTastatura(self):
		self.sms.nextKey()
		self.text += self.inAsteptare
		self.inAsteptare = ''
		self.session.openWithCallback(self._dinTastatura, VirtualKeyBoard, title=_('Numele canalului'), text=self.text)

	def _dinTastatura(self, text=None):
		if text is None:
			return
		self.text = text.strip()
		self.inAsteptare = ''
		self._filtreaza()
