# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Editorul de canale pe televizor: buchetele si canalele lor, cu telecomanda, cu mouse-ul si cu tastatura puse in
receptor. Doar in imaginea HDSatelit. Datele, operatiile, anularea, salvarea si copia de siguranta sunt ale partii
comune (Components/HdsEditorCanale*.py, aceleasi ca in pagina web /editor-canale), prin Screens/HdsEditorCanaleLegatura.py;
logica modurilor si a tastelor, fara enigma, e in Screens/HdsEditorCanaleLogica.py.

Ecranul: doua coloane, SURSA (stanga: toate canalele, satelitii, furnizorii, cautarea cu filtrele bazei noastre) si
BUCHETUL (dreapta: lista buchetelor, apoi intrarile unui buchet: canale, marcaje, sub-buchete). Deasupra, randul
modurilor (Rasfoire, Muta, Copiaza, Selecteaza: cel de acum in banda colorata) si cate schimbari nu sunt salvate;
dedesubt, indiciul (ce fac acum OK, sagetile si cifrele) si tastele colorate, cu textul lor dupa mod si coloana.

Tastele: Sus/Jos randul; Stanga/Dreapta coloana (in Muta/Copiaza: o pagina); CH+/CH- o pagina; OK: in sursa adauga
canalul in buchet dupa randul ales acolo (pe un dosar: il deschide), in buchet ia randul pentru mutare; cifrele: in
buchet pozitia (blocul tinut merge acolo), in sursa numele ca la SMS (cautarea); < / > anuleaza / reface; EXIT urca un
nivel, pune inapoi ce e in mana, iar la radacina iese (cu intrebarea pentru schimbarile nesalvate); MENU restul; HELP
ajutorul; TV / RADIO lista cealalta; TEXT tastatura de pe ecran pentru numele cautat.

Mouse-ul (Components/HdsMouseEcran.py da gestul ecranului prin hdsGestMouse): clic = randul si coloana, Ctrl/Shift +
clic = bife, dublu clic = OK, tras = mutare in buchet sau adaugare din sursa, rotita = derularea coloanei de sub mouse.
Tastatura (legarea pe toate tastele, _tastaBruta): Ctrl+C/X/V, Ctrl+Z/Y, Ctrl+A, Ctrl+S, Delete, Tab, Page Up/Down,
Home/End, Shift+sageti (bife), Ctrl+sageti (mutare), F2 (redenumire), literele scrise direct in sursa (cautarea).

Liste mari (~8300 de canale): randurile se construiesc numai cand se vad (setBuildFunc), cu o memorie mica a randurilor
gata facute, ca la cautarea de canale. Elementele listelor (sursa, buchet, indiciu, moduri) NU sunt transparente: pe
receptor un element transparent isi sterge intai toata zona (clipire neagra)."""
from enigma import eListboxPythonMultiContent, eTimer, getDesktop, gFont, gRGB, getPrevAsciiCode, RT_HALIGN_LEFT, \
	RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
try:
	from Components.MultiContent import MultiContentEntryPixmapAlphaBlend
except ImportError:
	MultiContentEntryPixmapAlphaBlend = None
from Tools.BoundFunction import boundFunction
from Tools.NumericalTextInput import NumericalTextInput
from Screens import HdsEditorCanaleLogica as L
from Screens import HdsEditorCanaleLegatura as G


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


TITLU = 'Editorul de canale'
SURSE = ('toate', 'sateliti', 'furnizori', 'transpondere', 'buchete', 'cautare')
NUME_SURSA = {'toate': N_('Toate canalele'), 'sateliti': N_('Sateliți'), 'furnizori': N_('Furnizori'), 'transpondere': N_('Transpondere'),
	'buchete': N_('Buchete'), 'cautare': N_('Căutare')}
# filtrele alese in sursa raman pentru urmatoarea deschidere a editorului (pana la repornirea interfetei)
_FILTRE_TINUTE = {}
MAX_RANDURI_GATA = 400      # randurile tinute gata construite, pe coloana
MAX_SIGLE = 240             # siglele (piconurile) mici tinute in memorie, decodate o data
MAX_CAI_SIGLE = 4000        # caile siglelor gasite (sau lipsa lor), dupa referinta
LITERE_SMS = ('0', '1', 'abc2', 'def3', 'ghi4', 'jkl5', 'mno6', 'pqrs7', 'tuv8', 'wxyz9')
PAUZA_INDICIU_MS = 6000     # cat ramane un mesaj („Scos din buchet: ...”) in randul indiciului
MARGINE_TRAS = 1            # la tras, randul de sus / de jos al listei deruleaza lista
DX_NOU = 64                 # steagul canalului nou gasit la scanare (dxNewFound)

CULORI = {
	'text': ('hdsText', 0xF2F4F8),
	'text2': ('hdsText2', 0xC9D2E3),
	'eticheta': ('hdsLabel', 0xAEB9CC),
	'stins': ('hdsDisabled', 0x667085),
	'focus': ('hdsBrandLight', 0x9FB4FF),
	'brand': ('hdsBrand', 0x374EA1),
	'pista': ('hdsTrack', 0x2A3350),
	'celula': ('hdsCell', 0x282D3F),
	'ales': ('hdsMarked', 0xF5B83D),
	'alesText': ('hdsMarkedText', 0x10162A),
	'alesSel': ('hdsMarkedSel', 0xC98F1E),
	'bun': ('hdsGood', 0x4FD18B),
	'rau': ('hdsBad', 0xFF6B5E),
	'chihlimbar': ('hdsAmber', 0xF5B83D),
	'alb': ('white', 0xFFFFFF),
	'fundal': ('hdsPanelSolid', 0x10162A),
}


def _jurnal(text):
	print('[HdsEditorCanale] %s' % text)


def _scrie(cale, date):
	"""Fisierul scris intreg pe stick (.nou, apoi redenumit peste cel vechi). -> cale."""
	import os
	nou = cale + '.nou'
	with open(nou, 'wb') as f:
		f.write(date)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)
	return cale


def _numeFisier(nume):
	"""Numele unui buchet ca nume de fisier (fara diacritice si semne): „Știri și sport” -> „Stiri_si_sport”."""
	import re
	import unicodedata
	t = u''.join(c for c in unicodedata.normalize('NFKD', nume or u'') if not unicodedata.combining(c))
	return re.sub(r'[^A-Za-z0-9.-]+', '_', t).strip('_.')[:60] or 'buchet'


def _ipReceptor():
	"""Adresa receptorului in reteaua locala (pentru adresele m3u ale canalelor, serverul de flux de pe 8001)."""
	import socket
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.connect(('10.255.255.255', 1))      # UDP: nimic nu pleaca, se alege numai interfata
			return s.getsockname()[0]
		finally:
			s.close()
	except Exception:
		return ''


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
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
	"""(gFont, marimea, inaltimea randului) din aliasul skinului, altfel rezerva scalata; marimea textului
	(skin._hds_scaleaza) se aplica la toate trei, ca la cautarea de canale."""
	try:
		import skin
		scaleaza = getattr(skin, '_hds_scaleaza', int)
		if alias in skin.fonts:
			_n, m, h = skin.fonts[alias]
			return skin.parseFont(alias, ((1, 1), (1, 1))), scaleaza(m), scaleaza(h or inaltime)
	except Exception:
		scaleaza = int
	f = _factor()
	return gFont(nume, scaleaza(int(marime * f))), scaleaza(int(marime * f)), scaleaza(int(inaltime * f))


def _rc():
	try:
		from enigma import eRCInput
		return eRCInput.getInstance()
	except Exception:
		return None


def _dinTastatura():
	try:
		from Components.HdsTastaturaUsb import dinTastatura
		return dinTastatura()
	except Exception:
		return False


def _normal(text):
	try:
		from Components.HdsIndexCanale import normalizeaza
		return normalizeaza(text)
	except Exception:
		return (text or '').lower()


def _g(obj, nume, implicit=None):
	return getattr(obj, nume, implicit) if obj is not None else implicit


class TastaturiNucleu(object):
	"""Ctrl si Shift apasate acum pe tastaturile puse in receptor, citite din nucleu (ioctl EVIOCGKEY pe dispozitivele
	cu „kbd” din /proc/bus/input/devices; citirea nu ia tastele nimanui). -> multimea codurilor apasate dintre
	MODIFICATORI, sau None cand nu e niciun dispozitiv de citit (emulatorul: atunci se tin minte apasarile)."""
	MODIFICATORI = (29, 97, 42, 54)
	OCTETI = 96

	def __init__(self):
		self.fd = None
		self.cautat = 0.0

	def _cauta(self):
		import os
		import re
		import time
		self.inchide()
		self.cautat = time.time()
		self.fd = []
		try:
			with open('/proc/bus/input/devices') as f:
				text = f.read()
		except (IOError, OSError):
			return
		for bloc in text.split(chr(10) * 2):
			m = re.search(r'^H: Handlers=(.*)$', bloc, re.M)
			if not m or 'kbd' not in m.group(1).split():
				continue
			ev = [h for h in m.group(1).split() if h.startswith('event')]
			for h in ev:
				try:
					self.fd.append(os.open('/dev/input/' + h, os.O_RDONLY | os.O_NONBLOCK))
				except OSError:
					pass

	def __call__(self):
		import time
		if self.fd is None or (not self.fd and time.time() - self.cautat > 5):
			self._cauta()
		if not self.fd:
			return None
		import array
		import fcntl
		cerere = (2 << 30) | (self.OCTETI << 16) | (ord('E') << 8) | 0x18   # EVIOCGKEY(OCTETI)
		apasate = set()
		bune = 0
		for fd in self.fd:
			buf = array.array('B', [0] * self.OCTETI)
			try:
				fcntl.ioctl(fd, cerere, buf, True)
			except (IOError, OSError):
				continue
			bune += 1
			for cod in self.MODIFICATORI:
				if buf[cod // 8] & (1 << (cod % 8)):
					apasate.add(cod)
		if not bune:
			self.fd = []      # dispozitivele au disparut (scoase la cald): se cauta din nou peste 5 s
			return None
		return apasate

	def inchide(self):
		import os
		for fd in self.fd or ():
			try:
				os.close(fd)
			except OSError:
				pass
		self.fd = None


def _areLitere(nume):
	return any(ch.isalnum() for ch in (nume or ''))


def _numeVazut(nume):
	"""Numele gol sau numai din semne („.”, „-”) se arata ca sa se vada ce e (canalele de test)."""
	if not (nume or '').strip():
		return _('(fără nume)')
	if not _areLitere(nume):
		return u'„%s”' % nume
	return nume


def _cheieDinRef(ref):
	"""Cheia (sid:ns:tsid:onid) a unei referinte de canal, ca in indexul cautarii; None cand nu e canal DVB."""
	try:
		from Components.HdsIndexCanale import cheie_din_ref
		return cheie_din_ref(ref or '') or None
	except Exception:
		return None


def _cheieIndex(canal):
	"""Cheia unui canal din indexul cautarii (aceeasi cu Serviciu.cheie a partii comune)."""
	try:
		from Components.HdsIndexCanale import cheie_din_ref
		k = cheie_din_ref(_g(canal, 'ref', ''))
		if k:
			return k
	except Exception:
		pass
	return _g(canal, 'cheie_mas')


class Sigle(object):
	"""Siglele canalelor (piconurile) mici pe randurile editorului: aceeasi cautare ca pe televizor
	(Components/Renderer/Picon.cauta_sigla: referinta, apoi tipul 1, la fluxuri partea DVB), cu setarea „Siglele
	canalelor” (config.usage.hds_piconuri). Fisierele se decodeaza micsorate cu un singur ePicLoad, pe firul lui, una
	dupa alta (coada), numai pentru randurile care se vad; ultimele raman in memorie (MAX_SIGLE). Cand vine una,
	`ceas` (pornit scurt) redeseneaza listele o data pentru toate cele venite intre timp."""

	def __init__(self, latime, inaltime, ceas, incarcator, cauta):
		self.latime, self.inaltime = latime, inaltime
		self.ceas = ceas
		self.incarcator = incarcator
		self.cauta = cauta                  # ref -> calea siglei sau ''
		self.cai = {}                       # ref -> cale sau ''
		self.pix = {}                       # cale -> pixmap
		self.rele = set()                   # caile care nu s-au putut decoda (nu se mai incearca)
		self.ordine = []
		self.coada = []
		self.lucru = None
		self.oprit = False
		self._leaga()

	@staticmethod
	def porneste(inaltimeRand, ceas):
		"""Sigle pentru randuri inalte de inaltimeRand px, sau None: setarea oprita, niciun dosar de sigle, sau fara
		ePicLoad / fara intrarea de lista cu poza (alt nucleu)."""
		if MultiContentEntryPixmapAlphaBlend is None:
			return None
		try:
			from Components.Renderer.Picon import sigle_pornite, dosare_sigle, cauta_sigla
			from enigma import ePicLoad
		except Exception as e:
			_jurnal('siglele: %r' % (e,))
			return None
		if not sigle_pornite() or not dosare_sigle():
			return None
		inaltime = max(16, int(inaltimeRand * 0.78))
		latime = int(round(inaltime * 5 / 3.0))     # piconurile au 5:3 (220x132)
		try:
			incarcator = ePicLoad()
			# latime, inaltime, aspectul (doua numere), memorie, felul micsorarii, fundal transparent
			incarcator.setPara((latime, inaltime, 1, 1, False, 1, '#00000000'))
		except Exception as e:
			_jurnal('siglele: %r' % (e,))
			return None
		return Sigle(latime, inaltime, ceas, incarcator, cauta_sigla)

	def _leaga(self):
		try:
			self.incarcator.PictureData.get().append(self._gata)
		except AttributeError:
			self._legatura = self.incarcator.PictureData.connect(self._gata)

	def sigla(self, ref):
		"""Pixmap-ul siglei, sau None (nu are sigla sau se decodeaza acum: randul se redeseneaza cand e gata)."""
		if not ref:
			return None
		cale = self.cai.get(ref)
		if cale is None:
			if len(self.cai) >= MAX_CAI_SIGLE:
				self.cai.clear()
			try:
				cale = self.cauta(ref) or ''
			except Exception:
				cale = ''
			self.cai[ref] = cale
		if not cale or cale in self.rele:
			return None
		ptr = self.pix.get(cale)
		if ptr is None and cale not in self.coada and cale != self.lucru:
			self.coada.append(cale)
			if self.lucru is None:
				self._urmatoarea()
		return ptr

	def _urmatoarea(self):
		while self.coada and not self.oprit:
			cale = self.coada.pop()            # ultima ceruta intai: randurile care se vad acum
			self.lucru = cale
			try:
				if self.incarcator.startDecode(cale) == 0:
					return
			except Exception as e:
				_jurnal('sigla %s: %r' % (cale, e))
			self.rele.add(cale)
		self.lucru = None

	def _gata(self, info=''):
		if self.oprit:
			return
		cale, self.lucru = self.lucru, None
		try:
			ptr = self.incarcator.getData()
		except Exception:
			ptr = None
		if cale is not None and ptr is not None:
			if cale not in self.pix:
				self.ordine.append(cale)
			self.pix[cale] = ptr
			while len(self.ordine) > MAX_SIGLE:
				self.pix.pop(self.ordine.pop(0), None)
			if not self.ceas.isActive():
				self.ceas.start(80, True)
		elif cale is not None:
			self.rele.add(cale)
		# coada lunga (o pagina noua): numai ultimele randuri cerute
		del self.coada[:-2 * MAX_SIGLE]
		self._urmatoarea()

	def opreste(self):
		self.oprit = True
		self.coada = []
		self.pix = {}

	def uita(self):
		"""Siglele tinute minte uitate (dupa o stergere de sigle de pe disc): se cauta si se decodeaza din nou."""
		self.cai.clear()
		self.pix.clear()
		self.ordine = []
		self.rele.clear()
		try:
			from Components.Renderer import Picon
			Picon._dosare.clear()
		except Exception:
			pass


class HdsEditorCanale(Screen, HelpableScreen):
	# rezerva pentru un skin fara acest ecran (skinul HDSatelit il are)
	skin = """
	<screen name="HdsEditorCanale" position="center,center" size="1240,700" title="Editorul de canale">
		<widget name="moduri" position="10,10" size="1220,36" itemHeight="36" selectionDisabled="1" scrollbarMode="showNever" transparent="0" zPosition="2" />
		<widget name="capSursa" position="10,52" size="600,32" font="Regular;22" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="capBuchet" position="630,52" size="600,32" font="Regular;22" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="sursa" position="10,88" size="600,532" itemHeight="38" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget name="buchet" position="630,88" size="600,532" itemHeight="38" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget name="golSursa" position="20,200" size="580,120" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="golBuchet" position="640,200" size="580,120" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="indiciu" position="10,626" size="1220,30" font="Regular;19" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="key_red" position="10,662" size="300,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="316,662" size="300,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="622,662" size="300,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
		<widget name="key_blue" position="928,662" size="302,30" font="Regular;19" backgroundColor="#003D7BE0" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, radio=False, buchetRef=None, canalRef=None):
		"""buchetRef / canalRef: buchetul si canalul listei de canale de unde s-a deschis (editorul se deschide pe ele)."""
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.radio = bool(radio)
		self.s = None
		self.inchis = False
		self.salvat = False                 # s-a salvat macar o data (lista de pe TV se improspateaza la iesire)
		self.focus = L.SURSA
		self.mod = L.RASFOIRE
		self.bife = {L.SURSA: L.Bife(), L.BUCHET: L.Bife()}
		self.sursaFel = 'toate'
		self.sursaDosar = None              # None sau (fel, cheie, nume): satelitul / furnizorul deschis in sursa
		self.cautareText = ''
		# filtrele (Components/HdsIndexCanale: {grup: set(valori)}, plus grupul editorului), ca la deschiderea de dinainte
		self.cautareSelectie = dict((g, set(v)) for g, v in (_FILTRE_TINUTE.get('sel') or {}).items())
		self.inAsteptare = ''               # litera SMS inca neconfirmata
		self.scrieText = False              # se scrie la tastatura in cautare (modul ASCII)
		self.cale = []                      # [(buchet_id, nume)]: [] = lista buchetelor
		self.mana = None                    # blocul tinut (MUTA / COPIAZA), vezi _ia
		self.cifre = L.Cifre()
		self.tastaturi = TastaturiNucleu()
		self.modif = L.Modificatori(self.tastaturi)
		self.clip = L.Clipboard()
		self.randuri = {L.SURSA: [], L.BUCHET: []}
		self.baza = []                      # intrarile buchetului deschis (sau buchetele), fara blocul din mana
		self.nCanale = 0                    # cate canale are buchetul deschis (fara marcaje)
		self._afisat = {}                   # ce e deja pe ecran (texte, randul modurilor), vezi _pune
		self._gata = {L.SURSA: {}, L.BUCHET: {}}
		self._mesaj = None                  # textul de aratat in indiciu in locul celui obisnuit
		self._tras = None                   # trasul cu mouse-ul (vezi hdsGestMouse)
		self._legat = False
		self._ascult = False
		self.lucru = ''                     # citirea / salvarea in fundal: textul aratat; tastele asteapta
		self.refsBuchet = frozenset()       # referintele buchetului deschis (semnul „în buchet” din sursa)
		self._radacinaInitiala = (buchetRef, canalRef)
		self.c = dict((k, _culoare(k)) for k in CULORI)
		self.sms = NumericalTextInput(nextFunc=self._literaConfirmata)
		self.sms.mapping = list(LITERE_SMS)
		self.setTitle(self._titlu())

		self['moduri'] = MenuList([], content=eListboxPythonMultiContent)
		self['capSursa'] = Label('')
		self['capBuchet'] = Label('')
		self['sursa'] = MenuList([], content=eListboxPythonMultiContent)
		self['buchet'] = MenuList([], content=eListboxPythonMultiContent)
		self['golSursa'] = Label('')
		self['golBuchet'] = Label('')
		self['indiciu'] = Label('')
		self['key_red'] = Button('')
		self['key_green'] = Button('')
		self['key_yellow'] = Button('')
		self['key_blue'] = Button('')

		# textele de ajutor (lista tastelor de la HELP, a doua oara) sunt scurte: lista de ajutor taie randurile lungi
		self['actiuni'] = HelpableActionMap(self, 'OkCancelActions', {
			'ok': (self.keyOk, _('Adaugă, ia, lasă sau deschide')),
			'cancel': (self.keyExit, _('Înapoi, pune înapoi sau ieși')),
		}, -1)
		self['directii'] = HelpableActionMap(self, 'DirectionActions', {
			'up': (self.keyUp, _('Rândul de sus')),
			'down': (self.keyDown, _('Rândul de jos')),
			'left': (self.keyLeft, _('Coloana din stânga')),
			'right': (self.keyRight, _('Coloana din dreapta')),
			'upRepeated': self.keyUp,
			'downRepeated': self.keyDown,
			'leftRepeated': self._nimic,
			'rightRepeated': self._nimic,
			'upUp': self._nimic,
			'downUp': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
		}, -1)
		self['culori'] = HelpableActionMap(self, 'ColorActions', {
			'red': (boundFunction(self.keyCuloare, 0), _('Tasta roșie (scrisă jos)')),
			'green': (boundFunction(self.keyCuloare, 1), _('Tasta verde (scrisă jos)')),
			'yellow': (boundFunction(self.keyCuloare, 2), _('Tasta galbenă (scrisă jos)')),
			'blue': (boundFunction(self.keyCuloare, 3), _('Tasta albastră (scrisă jos)')),
		}, -1)
		cifre = dict((str(i), boundFunction(self.keyCifra, i)) for i in range(10))
		cifre['1'] = (boundFunction(self.keyCifra, 1), _('Poziția în buchet sau numele'))
		self['cifre'] = HelpableActionMap(self, 'NumberActions', cifre, -1)
		self['meniu'] = HelpableActionMap(self, 'MenuActions', {
			'menu': (self.keyMeniu, _('Restul acțiunilor')),
		}, -1)
		self['editor'] = HelpableActionMap(self, 'HdsEditorCanaleActions', {
			'anuleaza': (self.keyAnuleaza, _('Anulează ultima schimbare')),
			'reface': (self.keyReface, _('Reface schimbarea anulată')),
			'paginaSus': (boundFunction(self.keyPagina, -1), _('O pagină în sus')),
			'paginaJos': (boundFunction(self.keyPagina, 1), _('O pagină în jos')),
			'listaTv': (boundFunction(self.keyLista, False), _('Lista TV')),
			'listaRadio': (boundFunction(self.keyLista, True), _('Lista radio')),
			'tastatura': (self.keyTastatura, _('Numele, cu tastatura de pe ecran')),
			'info': (self.keyInfo, _('Detaliile canalului')),
		}, -1)
		# HELP: ajutorul editorului (de acolo, verde = lista tastelor, cea de mai sus)
		self['helpActions'] = ActionMap(['HelpActions'], {'displayHelp': self.keyAjutor}, -1)
		self['ascii'] = ActionMap(['InputAsciiActions'], {'gotAsciiCode': self.keyAscii}, -1)
		self['ascii'].setEnabled(False)

		self.ceasCifre = eTimer()
		self.ceasCifre.callback.append(self._cifreGata)
		self.ceasMesaj = eTimer()
		self.ceasMesaj.callback.append(self._mesajGata)
		self.ceasPornire = eTimer()
		self.ceasPornire.callback.append(self._deschideSesiunea)
		self.ceasSigle = eTimer()
		self.ceasSigle.callback.append(self._sigleGata)
		self.ceasFir = eTimer()
		self.fir = G.Fir(self.ceasFir)          # stick: despachetarea arhivei, scrierea listei
		self.ceasPas = eTimer()
		self.ceasPas.callback.append(self._pasAmanat)
		self._amanat = None
		self._bandaAmanata = None           # banda problemelor gasita cat alt ecran (sfaturile) era deasupra
		self.sigle = None                   # Sigle (piconurile pe randuri) sau None cand sunt oprite / lipsesc

		self.onLayoutFinish.append(self._pregateste)
		self.onExecBegin.append(self._laExecBegin)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ pregatirea

	def _titlu(self):
		return '%s · %s' % (_(TITLU), _('Radio') if self.radio else 'TV')

	def _pregateste(self):
		self.fontRand, self.marimeRand, self.inaltimeRand = _font('HdsEditorRand', 'Regular', 30, 54)
		self.fontMic, _m, _h = _font('HdsEditorMic', 'Regular', 26, 54)
		self.fontMod, _m, self.inaltimeMod = _font('HdsEditorMod', 'Regular', 26, 48)
		for nume in ('sursa', 'buchet'):
			l = self[nume]
			l.l.setFont(0, self.fontRand)
			l.l.setFont(1, self.fontMic)
			l.l.setItemHeight(self.inaltimeRand)
			l.l.setBuildFunc(boundFunction(self._rand, L.SURSA if nume == 'sursa' else L.BUCHET))
		m = self['moduri']
		m.l.setFont(0, self.fontMod)
		m.l.setItemHeight(self.inaltimeMod)
		try:
			m.selectionEnabled(False)
		except Exception:
			pass
		f = _factor()
		try:
			# bara de derulare a listei (elistbox.cpp: latimea/16, intre 18 si 22 px, plus 5 px) nu acopera semnele din dreapta
			self.latimeLista = {L.SURSA: self['sursa'].instance.size().width(),
				L.BUCHET: self['buchet'].instance.size().width()}
			self.latime = dict((col, w - min(max(w // 16, 18), 22) - 8) for col, w in self.latimeLista.items())
			self.latimeModuri = m.instance.size().width()
			self.randuriPagina = max(1, self['buchet'].instance.size().height() // max(1, self.inaltimeRand))
		except Exception:
			self.latimeLista = {L.SURSA: int(836 * f), L.BUCHET: int(836 * f)}
			self.latime = {L.SURSA: int(806 * f), L.BUCHET: int(806 * f)}
			self.latimeModuri = int(1712 * f)
			self.randuriPagina = 12
		self.f = f
		self.sigle = Sigle.porneste(self.inaltimeRand, self.ceasSigle)
		self._seteazaFocus()
		self._arataGol(L.SURSA, _('Se pregătește lista de canale…'))
		self._arataGol(L.BUCHET, '')
		self._arata()
		# citirea listei dupa ce ecranul s-a desenat (textul de asteptare se vede)
		self.ceasPornire.start(30, True)

	def _deschideSesiunea(self):
		if self.inchis:
			return
		self.lucru = _('Se citește lista de canale…')
		G.deschide_fundal(self._sesiuneGata, self._sesiuneEroare, cine='tv', nume=_('televizorul'))

	def _sesiuneGata(self, s):
		self.lucru = ''
		if self.inchis:
			s.inchide()
			return
		self.s = s
		self._legaTastatura(True)
		if not self._ascult:
			G.asculta(self._eveniment, True)
			self._ascult = True
		self._incarcaSursa()
		self._pozitieInitiala()
		self._arata()
		self._cautaProbleme()
		self._sfaturi()

	def _sfaturi(self):
		"""Sfaturile scurte la prima deschidere a editorului pe acest receptor (o singura data; HELP le are pe toate,
		iar din ajutor, galben le arata din nou la urmatoarea deschidere)."""
		from Screens import HdsEditorCanaleUnelte as UN
		if UN.sfaturi_vazute():
			return
		self.session.openWithCallback(self._sfaturiVazute, MessageBox, _('Sfaturi: în stânga sunt canalele, în '
			'dreapta buchetul; Stânga / Dreapta trec dintr-o parte în alta. OK adaugă canalul sau ia rândul ca să-l muți, '
			'galben bifează mai multe. Jos scrie ce face fiecare tastă colorată, MENU are restul. Nimic nu se scrie până '
			'nu salvezi, iar tasta < anulează. HELP: ajutorul.'), MessageBox.TYPE_INFO)

	def _sfaturiVazute(self, *_a):
		from Screens import HdsEditorCanaleUnelte as UN
		UN.pune_sfaturi_vazute(True)

	def _cautaProbleme(self):
		"""Banda „Am găsit în listă: ...” la deschidere (partea comuna, pe firul uneltelor)."""
		if self.s is None or not self.s.are('probleme_fundal'):
			return
		try:
			self.s.probleme_fundal(self._problemeGasite, lambda e: _jurnal('probleme: %r' % (e,)))
		except Exception as e:
			_jurnal('probleme: %r' % (e,))

	def _problemeGasite(self, p):
		if self.inchis or not p:
			return
		texte = {
			'fara_nume': lambda n: L.ngettext('%d canal fără nume', '%d canale fără nume', n),
			'test': lambda n: L.ngettext('%d canal cu nume de test', '%d canale cu nume de test', n),
			'in_buchet': lambda n: L.ngettext('%d rând dublat', '%d rânduri dublate', n),
			'moarte': lambda n: L.ngettext('%d canal care nu mai există', '%d canale care nu mai există', n),
			'buchete_goale': lambda n: L.ngettext('%d buchet gol', '%d buchete goale', n),
			'nelegate': lambda n: L.ngettext('%d buchet găsit pe disc', '%d buchete găsite pe disc', n),
		}
		parti = [texte[k](n) % n for k, n in sorted(p.items()) if k in texte and n]
		if not parti:
			return
		text = u'%s %s. %s' % (_('Am găsit în listă:'), u', '.join(parti), _('Le vezi în MENU.'))
		deasupra = getattr(self.session, 'current_dialog', None)
		if deasupra is not None and deasupra is not self:
			# alt ecran deasupra (sfaturile de la prima deschidere, o intrebare): banda ar trece nevazuta pe sub el;
			# se arata cand editorul revine in fata (_laExecBegin)
			self._bandaAmanata = text
			return
		self._spune(text, 15000)

	def _sesiuneEroare(self, e):
		self.lucru = ''
		if self.inchis:
			return
		if isinstance(e, G.Ocupat) and not e.acum:
			# lista e deschisa in interfata web: o singura intrebare, Da = editarea trece aici
			text = e.mesaj or _('Lista de canale e deschisă acum pentru editare în interfața web.')
			if e.nesalvate:
				text += ' ' + L.ngettext('Acolo e %d schimbare nesalvată, care se pierde.',
					'Acolo sunt %d schimbări nesalvate, care se pierd.', e.nesalvate) % e.nesalvate
			self.session.openWithCallback(self._raspunsPreia, MessageBox, text + '\n' + _('Editezi aici, pe televizor?'),
				MessageBox.TYPE_YESNO, default=False)
			return
		_jurnal('sesiunea nu s-a deschis: %r' % (e,))
		self.session.openWithCallback(self._inchideFaraIntrebare, MessageBox,
			_('Editorul de canale nu se poate deschide acum.'), MessageBox.TYPE_INFO, timeout=10)

	def _raspunsPreia(self, da):
		if not da or self.inchis:
			self.close(False)
			return
		if not G.preia('tv', _('televizorul')):
			self.session.openWithCallback(self._inchideFaraIntrebare, MessageBox,
				_('Editorul de canale nu se poate deschide acum.'), MessageBox.TYPE_INFO, timeout=10)
			return
		self._deschideSesiunea()

	def _eveniment(self, fel, date=None):
		"""Ascultatorul partii comune: sesiunea preluata de interfata web inchide editorul de aici."""
		_jurnal('evenimentul partii comune: %s %r' % (fel, date if fel != 'salvat' else ''))
		if self.inchis:
			return
		if fel == 'preluat' and self.s is not None and not self.s.valida():
			self.s = None
			self.session.openWithCallback(self._inchideFaraIntrebare, MessageBox,
				_('Editarea a trecut în interfața web. Editorul de aici se închide.'), MessageBox.TYPE_INFO, timeout=10)

	def _pozitieInitiala(self):
		"""Buchetul listei de canale de unde s-a deschis editorul, cu cursorul pe canalul de acum; deschis de pe un
		satelit, un furnizor sau din toate canalele: sursa arata acelasi loc, cu cursorul pe canalul de acum, iar in
		dreapta lista buchetelor."""
		buchetRef, canalRef = self._radacinaInitiala
		loc = L.loc_din_radacina(buchetRef) if buchetRef else None
		fisier = loc[1] if loc is not None and loc[0] == 'buchet' else None
		buchete = self._buchete()
		if fisier and any(_g(b, 'id') == fisier for b in buchete):
			nume = [_g(b, 'nume', '') for b in buchete if _g(b, 'id') == fisier][0]
			self.cale = [(fisier, nume)]
			self._incarcaBuchet()
			if canalRef:
				for i, (fel, obj, _l) in enumerate(self.randuri[L.BUCHET]):
					if fel == 'intrare' and _g(obj, 'ref') == canalRef:
						self['buchet'].moveToIndex(i)
						break
			self.focus = L.BUCHET
		else:
			self.cale = []
			self._incarcaBuchet()
			if loc is not None and loc[0] != 'buchet':
				try:
					self._sursaDinLista(loc, canalRef)
				except Exception as e:
					_jurnal('locul listei de canale %r: %r' % (loc, e))
		self._seteazaFocus()

	def _sursaDinLista(self, loc, canalRef):
		"""Sursa pe locul listei de canale: satelitul sau furnizorul deschis acolo (dosarul lui), lista satelitilor sau
		a furnizorilor (cursorul pe dosarul ales acolo), ori toate canalele (cursorul pe canalul de acum)."""
		fel = loc[0]
		dosar = None
		if fel == 'satelit':
			poz = L.pozitie_din_ns(loc[1])
			for p, text, _n in self.s.sateliti(self.radio):
				if p == poz:
					dosar = ('satelit', p, self._textSatelit(p, text))
					break
			sursa = 'sateliti'
		elif fel == 'furnizor':
			furnizori = [nume for nume, _n in self.s.furnizori(self.radio)]
			nume = loc[1]
			if nume not in furnizori and nume == 'Unknown' and '' in furnizori:
				nume = ''        # lista nucleului numeste „Unknown” furnizorul gol
			if nume in furnizori:
				dosar = ('furnizor', nume, nume)
			sursa = 'furnizori'
		else:
			sursa = fel if fel in ('sateliti', 'furnizori') else 'toate'
		self.sursaFel = sursa
		self.sursaDosar = dosar
		self._incarcaSursa(pastreaza=False)
		tinta = None
		if dosar is None and sursa in ('sateliti', 'furnizori'):
			# randul ales in lista satelitilor / furnizorilor e un dosar: cursorul pe dosarul lui
			sub = L.loc_din_radacina(canalRef) if canalRef else None
			if sub is not None and sub[0] == 'satelit':
				tinta = ('dosar', 'satelit', L.pozitie_din_ns(sub[1]))
			elif sub is not None and sub[0] == 'furnizor':
				tinta = ('dosar', 'furnizor', sub[1])
		elif canalRef:
			# cheia canalului (sid:ns:tsid:onid), fara tipul serviciului, care poate diferi intre lista si lamedb
			try:
				srv = self.s.serviciu(canalRef)
			except Exception:
				srv = None
			tinta = _g(srv, 'cheie') or _cheieDinRef(canalRef)
		if tinta is not None:
			for i, r in enumerate(self.randuri[L.SURSA]):
				if (r[0] == 'dosar' and self._cheieRand(r) == tinta) or \
						(r[0] == 'canal' and (_g(r[1], 'cheie') or _cheieIndex(r[1])) == tinta):
					self['sursa'].moveToIndex(i)
					break
		self.focus = L.SURSA

	def _inchideFaraIntrebare(self, *_a):
		self.close(False)

	def close(self, *rez):
		# urma inchiderii in jurnal (cine a inchis editorul: tasta, intrebarea, partea comuna), apoi ca de obicei
		try:
			import traceback
			sir = [f[2] for f in traceback.extract_stack(limit=5)[:-1]]
			_jurnal('inchis (%s)' % ' < '.join(reversed(sir)))
		except Exception:
			pass
		Screen.close(self, *rez)

	def _laExecBegin(self):
		self._puneModTastatura()
		if self._bandaAmanata and not self.inchis:
			text, self._bandaAmanata = self._bandaAmanata, None
			self._spune(text, 15000)

	def execEnd(self):
		# Screen nu are onExecEnd: alt ecran deasupra (meniu, tastatura de pe ecran) = execEnd
		self._laExecEnd()
		Screen.execEnd(self)

	def _laExecEnd(self):
		# alt ecran deasupra (meniu, tastatura de pe ecran): tastatura receptorului inapoi in modul obisnuit, iar Ctrl /
		# Shift tinute nu mai sunt sigure (eliberarea poate ajunge la alt ecran)
		rc = _rc()
		if rc is not None and self.scrieText:
			rc.setKeyboardMode(rc.kmNone)
		self.modif.goleste()

	def _laInchidere(self):
		self.inchis = True
		self.ceasCifre.stop()
		self.ceasMesaj.stop()
		self.ceasPornire.stop()
		self.ceasSigle.stop()
		self.ceasPas.stop()
		self.fir.opreste()
		if self.sigle is not None:
			self.sigle.opreste()
			self.sigle = None
		self._legaTastatura(False)
		self.tastaturi.inchide()
		if self._ascult:
			G.asculta(self._eveniment, False)
			self._ascult = False
		rc = _rc()
		if rc is not None:
			rc.setKeyboardMode(rc.kmNone)
		if self.s is not None:
			self.s.inchide()
			self.s = None

	# ------------------------------------------------------------ tastatura (modul ASCII cat se scrie in cautare)

	def _puneModTastatura(self):
		rc = _rc()
		if rc is None:
			return
		rc.setKeyboardMode(rc.kmAscii if self.scrieText else rc.kmNone)
		self['ascii'].setEnabled(bool(self.scrieText))

	def _incepeScrisul(self):
		if not self.scrieText:
			self.scrieText = True
			self._puneModTastatura()

	def _opresteScrisul(self):
		if self.scrieText:
			self.scrieText = False
			self._puneModTastatura()

	def _legaTastatura(self, da):
		"""Legarea pe toate tastele (prioritatea cea mai buna): Ctrl / Shift si scurtaturile tastaturii."""
		if da == self._legat:
			return
		try:
			from enigma import eActionMap
			if da:
				eActionMap.getInstance().bindAction('', -0x7FFFFFFF, self._tastaBruta)
			else:
				eActionMap.getInstance().unbindAction('', self._tastaBruta)
			self._legat = da
		except Exception as e:
			_jurnal('legarea tastaturii: %r' % (e,))

	def _tastaBruta(self, cod, flag):
		"""Fiecare tasta, inaintea hartilor de actiuni. -> 1 cand editorul a folosit-o (nu mai merge mai departe)."""
		if not self.execing or self.s is None or self.lucru:
			return 0
		if cod == L.KEY_HELP:
			# HELP = ajutorul editorului (cu lista tastelor), inaintea legarii globale a tastei (ajutorul receptorului,
			# care are prioritatea imediat dupa aceasta); ridicarea si repetarea ei nu mai merg mai departe
			if flag == L.FLAG_APASAT:
				self._helpPrins = True
				self.keyAjutor()
				return 1
			return 1 if getattr(self, '_helpPrins', False) else 0
		if self.modif.tasta(cod, flag):
			return 0
		if flag not in (L.FLAG_APASAT, L.FLAG_REPETAT):
			return 0
		try:
			if self.scrieText and cod == L.KEY_BACKSPACE:
				self.keyStergeLitera()
				return 1
			act = L.scurtatura(cod, self.modif.are_ctrl, self.modif.are_shift)
			if flag == L.FLAG_APASAT:
				self.modif.consuma()
			if act is not None:
				if self.scrieText:
					self._opresteScrisul()
				self._scurtatura(act)
				return 1
			if flag == L.FLAG_APASAT and cod == L.KEY_GREEN and _dinTastatura() and self.mod == L.RASFOIRE:
				# F2 (tradusa in VERDE de eRCMapper): redenumirea, ca pe PC
				self.keyRedenumeste()
				return 1
			if flag == L.FLAG_APASAT and not self.modif.are_ctrl and not self.scrieText:
				ch = L.litera(cod)
				if ch and self.focus == L.SURSA and self.mod in (L.RASFOIRE, L.SELECTEAZA):
					self._incepeScrisul()
					self._scrieInCautare(ch)
					return 1
		except Exception as e:
			_jurnal('tasta %d: %r' % (cod, e))
			return 1
		return 0

	def _scurtatura(self, act):
		f = {
			'copiaza': self.keyCopiazaClip, 'taie': self.keyTaieClip, 'lipeste': self.keyLipesteClip,
			'anuleaza': self.keyAnuleaza, 'reface': self.keyReface, 'bifeaza_tot': self.keyBifeazaTot,
			'salveaza': self.keySalveaza, 'muta_sus': boundFunction(self.keyMutaPas, -1),
			'muta_jos': boundFunction(self.keyMutaPas, 1), 'bifeaza_sus': boundFunction(self.keyBifeazaPas, -1),
			'bifeaza_jos': boundFunction(self.keyBifeazaPas, 1), 'scoate': self.keySterge, 'coloana': self.keyColoana,
			'pagina_sus': boundFunction(self.keyPagina, -1), 'pagina_jos': boundFunction(self.keyPagina, 1),
			'inceput': boundFunction(self.keyCapat, -1), 'sfarsit': boundFunction(self.keyCapat, 1),
		}.get(act)
		if f is not None:
			f()

	# ------------------------------------------------------------ datele

	def _buchete(self):
		try:
			return self.s.buchete(self.radio) if self.s is not None else []
		except Exception as e:
			_jurnal('buchetele: %r' % (e,))
			return []

	def _buchetCurent(self):
		return self.cale[-1][0] if self.cale else None

	def _laRadacina(self):
		return not self.cale

	def _listaSursei(self):
		"""Randurile sursei: (fel, obiect, luat) cu fel 'dosar' (satelit / furnizor) sau 'canal' (Serviciu)."""
		s = self.s
		if s is None:
			return []
		if self.sursaFel == 'sateliti' and self.sursaDosar is None:
			return [('dosar', ('satelit', poz, self._textSatelit(poz, text), n), False) for poz, text, n in s.sateliti(self.radio)]
		if self.sursaFel == 'furnizori' and self.sursaDosar is None:
			return [('dosar', ('furnizor', nume, nume, n), False) for nume, n in s.furnizori(self.radio)]
		if self.sursaFel == 'transpondere' and self.sursaDosar is None:
			return [('dosar', ('transponder',) + self._tp(tp), False) for tp in s.transpondere(self.radio)]
		if self.sursaFel == 'buchete' and self.sursaDosar is None:
			return [('dosar', ('buchet', _g(b, 'id'), _g(b, 'nume', '') or _g(b, 'id'), _g(b, 'n', 0)), False)
				for b in s.buchete(self.radio)]
		if self.sursaDosar is not None:
			canale = self._dinDosar(self.sursaDosar[0], self.sursaDosar[1])
		elif self.sursaFel == 'cautare':
			canale = self._cautare()
		else:
			canale = s.toate(self.radio)
		return [('canal', c, False) for c in canale]

	def _textSatelit(self, poz, text):
		"""„19,2°E Astra 1N”: pozitia si, cand se stie, numele din satellites.xml."""
		nume = self.s.nume_satelit(poz) if isinstance(poz, int) else ''
		# satellites.xml pune adesea pozitia si in nume („30.0W Hispasat 30W-5”): ea se scoate, ramane numele
		import re
		nume = re.sub(r'^\s*\d+(?:[.,]\d+)?\s*[EWew](?![A-Za-z])[\s:-]*', '', nume or '').strip()
		return u'%s %s' % (text, nume) if nume and nume not in text else text

	@staticmethod
	def _tp(tp):
		"""(cheia, textul, cate canale) ale unui transponder al partii comune."""
		cheie = _g(tp, 'cheie', None) or _g(tp, 'tp_cheie', None)
		text = _g(tp, 'text', None) or _g(tp, 'tp_text', None) or str(cheie)
		poz = _g(tp, 'poz_text', '')
		if poz and poz not in text:
			text = u'%s \u00b7 %s' % (poz, text)
		return cheie, text, _g(tp, 'n', None)

	def _dinDosar(self, fel, cheie):
		s = self.s
		if fel == 'satelit':
			return s.din_satelit(cheie, self.radio)
		if fel == 'furnizor':
			return s.din_furnizor(cheie, self.radio)
		if fel == 'buchet':
			# alt buchet ca sursa: canalele lui (cu datele din lista) si fluxurile lui, in ordinea din buchet
			rez = []
			for i in s.intrari(cheie):
				fi = _g(i, 'fel')
				if fi == 'canal' and _g(i, 'serviciu') is not None:
					rez.append(_g(i, 'serviciu'))
				elif fi == 'flux':
					rez.append(i)
			return rez
		return [c for c in s.din_transponder(cheie) if bool(_g(c, 'tip') == 'radio') == self.radio]

	def _cautare(self):
		"""Canalele cautarii: numele (fara diacritice, spatii si semne, ca la cautarea de canale) si filtrele bazei
		noastre (indexul cautarii de canale, Index.filtreaza); se pastreaza numai canalele care exista in sesiune."""
		text = (self.cautareText + self.inAsteptare).strip()
		return self._filtreaza(text, self.cautareSelectie)

	def _filtreaza(self, text, selectie):
		"""Canalele listei (TV / radio) care trec de text si de filtre: cele ale bazei (indexul cautarii) si ale
		editorului (FILTRU_EDITOR: noi, blocate, ascunse, in niciun buchet, fara sigla, HD in nume cu tip SD)."""
		editor = set((selectie or {}).get(L.FILTRU_EDITOR) or ())
		selectie = dict((g, set(v)) for g, v in (selectie or {}).items() if v and g != L.FILTRU_EDITOR)
		chei = None
		if selectie:
			index = self._index()
			if index is None:
				return []
			chei = set()
			for c in index.filtreaza('', selectie):
				k = _cheieIndex(c)
				if k:
					chei.add(k)
		if not text:
			toate = self.s.toate(self.radio)
			rez = toate if chei is None else [c for c in toate if _g(c, 'cheie') in chei]
		else:
			try:
				# numele, furnizorul, SID-ul (hexa sau zecimal), frecventa, referinta, * ?, o greseala (ca in web)
				rez = self.s.cauta(text, self.radio, chei)
			except Exception as e:
				_jurnal('cauta: %r' % (e,))
				q = _normal(text)
				rez = [c for c in self.s.toate(self.radio) if q in _normal(_g(c, 'nume', '')) and
					(chei is None or _g(c, 'cheie') in chei)]
		if editor:
			rez = self._filtreEditor(rez, editor)
		return rez

	def _filtreEditor(self, canale, alese):
		"""Numai canalele care au toate starile alese (FILTRE_EDITOR)."""
		hd = None
		if 'hd_sd' in alese:
			U = G.unelte()
			hd = getattr(U, 'hd_in_nume_sd', None) if U is not None else None
		sigle = self._sigleExistente() if 'fara_sigla' in alese else None
		rez = []
		for c in canale:
			if 'noi' in alese and not (_g(c, 'steaguri', 0) or 0) & DX_NOU:
				continue
			if 'blocate' in alese and not _g(c, 'blocat'):
				continue
			if 'ascunse' in alese and not _g(c, 'ascuns'):
				continue
			if 'nicaieri' in alese:
				try:
					if self.s.in_buchete(_g(c, 'ref')):
						continue
				except Exception:
					continue
			if hd is not None and not hd(_g(c, 'nume', ''), _g(c, 'stype')):
				continue
			if sigle is not None:
				nume, existente = sigle
				if any(n in existente for n in nume(_g(c, 'ref', ''))):
					continue
			rez.append(c)
		return rez

	@staticmethod
	def _sigleExistente():
		"""(nume_sigle, multimea numelor de sigle de pe disc): o singura citire a dosarelor pentru tot filtrul."""
		import os
		try:
			from Components.Renderer.Picon import dosare_sigle, nume_sigle
		except Exception:
			return (lambda ref: [], set())
		nume = set()
		for d in dosare_sigle():
			try:
				for f in os.listdir(d):
					if f.lower().endswith('.png'):
						nume.add(f[:-4])
			except OSError:
				pass
		return nume_sigle, nume

	def _index(self):
		"""Indexul cautarii de canale (Screens/HdsCautareCanale.cere_index), din memorie; cand vine unul nou,
		sursa se reface."""
		try:
			from Screens import HdsCautareCanale as C
		except Exception as e:
			_jurnal('indexul cautarii: %r' % (e,))
			return None
		gasit = []

		def gata(index):
			if gasit:
				if not self.inchis and self.sursaFel == 'cautare':
					self._incarcaSursa()
			else:
				gasit.append(index)
		vechi = C.cere_index(gata)
		gasit.append(True)
		return vechi

	def _incarcaSursa(self, pastreaza=True):
		cheie = self._cheieCurenta(L.SURSA) if pastreaza else None
		try:
			self.randuri[L.SURSA] = self._listaSursei()
		except Exception as e:
			_jurnal('sursa: %r' % (e,))
			self.randuri[L.SURSA] = []
		self._gata[L.SURSA] = {}
		self.bife[L.SURSA].pastreaza(self._chei(L.SURSA))
		self['sursa'].setList([(r, i) for i, r in enumerate(self.randuri[L.SURSA])])
		self._laCheie(L.SURSA, cheie)
		if not self.randuri[L.SURSA]:
			if self.sursaFel == 'cautare':
				self._arataGol(L.SURSA, _('Niciun canal găsit. Scrie alt nume sau schimbă filtrele (albastru).'))
			else:
				self._arataGol(L.SURSA, _('Lista de canale e goală. Caută canale din meniul Scanare.'))
		else:
			self._arataGol(L.SURSA, '')

	def _listaBuchetului(self):
		s = self.s
		if s is None:
			return []
		if self._laRadacina():
			return [('buchet', b, False) for b in s.buchete(self.radio)]
		return [('intrare', i, False) for i in s.intrari(self._buchetCurent())]

	def _incarcaBuchet(self, pastreaza=True, index=None):
		i_vechi = self['buchet'].getSelectionIndex() if pastreaza else 0
		try:
			baza = self._listaBuchetului()
		except Exception as e:
			_jurnal('buchetul: %r' % (e,))
			baza = []
		self.baza = baza
		self.refsBuchet = frozenset(_g(obj, 'ref') for fel, obj, _l in baza if fel == 'intrare') \
			if not self._laRadacina() else frozenset()
		if self.randuri[L.SURSA]:
			self._invalideaza(L.SURSA)
		self.nCanale = sum(1 for fel, obj, _l in baza if fel == 'intrare' and _g(obj, 'fel', 'canal') in ('canal', 'flux'))
		self._puneRanduriBuchet(baza)
		self.bife[L.BUCHET].pastreaza(range(len(baza)))
		n = len(self.randuri[L.BUCHET])
		if n:
			self['buchet'].moveToIndex(max(0, min(i_vechi if index is None else index, n - 1)))
		if not baza and self.mana is None:
			if self._laRadacina():
				self._arataGol(L.BUCHET, _('Niciun buchet. Albastru: buchet nou.'))
			else:
				self._arataGol(L.BUCHET, _('Buchetul e gol. Adaugă canale din stânga: OK pe un canal.'))
		else:
			self._arataGol(L.BUCHET, '')

	def _puneRanduriBuchet(self, baza):
		"""Randurile de pe ecran ale buchetului; cu un bloc in mana, ordinea arata blocul la locul lui de acum."""
		m = self.mana
		if m is None or m['tinta'] != self._buchetCurent_sau_radacina():
			randuri = list(baza)
		elif not m['copie'] and m['din'] == m['tinta']:
			ordine = L.ordine_cu_bloc(len(baza), m['indici'], m['la'])
			luate = set(m['indici'])
			randuri = [(baza[i][0], baza[i][1], i in luate) for i in ordine]
		else:
			bloc = [(fel, obj, True) for fel, obj in m['randuri']]
			la = max(0, min(m['la'], len(baza)))
			randuri = list(baza[:la]) + bloc + list(baza[la:])
		self.randuri[L.BUCHET] = randuri
		self._gata[L.BUCHET] = {}
		self['buchet'].setList([(r, i) for i, r in enumerate(randuri)])

	def _chei(self, col):
		"""Cheile randurilor (bifele): in sursa referinta (sau dosarul), in buchet indicele randului."""
		if col == L.BUCHET:
			return list(range(len(self.randuri[L.BUCHET])))
		return [self._cheieRand(r) for r in self.randuri[L.SURSA]]

	@staticmethod
	def _cheieRand(r):
		fel, obj, _l = r
		if fel == 'dosar':
			return ('dosar',) + tuple(obj[:2])
		return _g(obj, 'ref')

	def _cheieCurenta(self, col):
		r = self._curent(col)
		return None if r is None else (self._cheieRand(r) if col == L.SURSA else self[self._numeLista(col)].getSelectionIndex())

	def _laCheie(self, col, cheie):
		if cheie is None:
			return
		if col == L.SURSA:
			for i, r in enumerate(self.randuri[L.SURSA]):
				if self._cheieRand(r) == cheie:
					self['sursa'].moveToIndex(i)
					return
		elif isinstance(cheie, int) and self.randuri[col]:
			self[self._numeLista(col)].moveToIndex(min(cheie, len(self.randuri[col]) - 1))

	@staticmethod
	def _numeLista(col):
		return 'sursa' if col == L.SURSA else 'buchet'

	def _curent(self, col=None):
		col = self.focus if col is None else col
		randuri = self.randuri[col]
		if not randuri:
			return None
		i = self[self._numeLista(col)].getSelectionIndex() or 0
		return randuri[i] if 0 <= i < len(randuri) else None

	def _index_curent(self, col=None):
		col = self.focus if col is None else col
		return self[self._numeLista(col)].getSelectionIndex() or 0

	# ------------------------------------------------------------ desenul randurilor

	def _rand(self, col, r, i):
		"""Functia de constructie a listei (cheamata de nucleu cand randul se vede), din memorie cand e gata."""
		gata = self._gata[col]
		k = id(r)
		v = gata.get(k)
		if v is None or v[0] is not r:
			if len(gata) >= MAX_RANDURI_GATA:
				gata.clear()
			v = gata[k] = (r, self._construieste(col, r, i))
		return v[1]

	def _invalideaza(self, col=None):
		for c in ((L.SURSA, L.BUCHET) if col is None else (col,)):
			self._gata[c] = {}
			try:
				self[self._numeLista(c)].l.invalidate()
			except Exception:
				pass

	def _bifa(self, e, x, h, bifat, cuFocus=True):
		"""Casuta de bifa desenata din dreptunghiuri (fonturile interfetei nu au semnul de bifa)."""
		c = self.c
		m = int(h * 0.26)
		lat = h - 2 * m
		e.append(MultiContentEntryText(pos=(x, m), size=(lat, lat), font=0, text='', backcolor=c['text2'],
			backcolor_sel=c['alb']))
		gros = max(2, int(lat * 0.12))
		umplut = c['ales'] if bifat else c['fundal']
		e.append(MultiContentEntryText(pos=(x + gros, m + gros), size=(lat - 2 * gros, lat - 2 * gros), font=0, text='',
			backcolor=umplut, backcolor_sel=umplut if bifat else (c['brand'] if cuFocus else c['pista'])))
		return lat

	def _construieste(self, col, r, i):
		fel, obj, luat = r
		c = self.c
		h = self.inaltimeRand
		w = self.latime[col]
		v = RT_VALIGN_CENTER
		e = [None]
		if luat:
			# randul tinut in mana (MUTA / COPIAZA): banda chihlimbar pe tot randul
			e.append(MultiContentEntryText(pos=(0, 0), size=(self.latimeLista[col], h), font=0, text='',
				backcolor=c['ales'], backcolor_sel=c['alesSel']))
		culoareText = c['alesText'] if luat else c['text']
		culoareSel = c['alesText'] if luat else c['alb']
		x = int(12 * self.f)
		if fel == 'intrare':
			fi = _g(obj, 'fel', 'canal')
			if fi == 'spatiu':
				e.append(MultiContentEntryText(pos=(x, 0), size=(w - 2 * x, h), font=1, flags=RT_HALIGN_CENTER | v,
					text=_('rând gol'), color=culoareText if luat else c['stins'], color_sel=culoareSel))
				return e
			if fi == 'marcaj':
				# marcajul (separatorul): numele la mijloc, intre doua linii (fara fundal sub nume: randul ales isi
				# pastreaza banda)
				t = _g(obj, 'nume', '') or _('Marcaj')
				lat = min(w - 4 * x, int(self.marimeRand * 0.62 * (len(t) + 2)))
				st, dr = (w - lat) // 2, (w + lat) // 2
				culoareLinie = culoareText if luat else c['eticheta']
				grosime = max(1, int(round(2 * self.f)))
				for a, b in ((x, st - x), (dr, w - x)):
					if b - a > 4:
						e.append(MultiContentEntryText(pos=(a, int(h * 0.48)), size=(b - a, grosime), font=0, text='',
							backcolor=culoareLinie, backcolor_sel=culoareSel))
				e.append(MultiContentEntryText(pos=(st, 0), size=(lat, h), font=0, flags=RT_HALIGN_CENTER | v, text=t,
					color=culoareText if luat else c['chihlimbar'], color_sel=culoareSel))
				return e
			numar = _g(obj, 'numar')
			latNr = int(84 * self.f)
			if numar is not None and not luat:
				e.append(MultiContentEntryText(pos=(0, 0), size=(latNr, h), font=1, flags=RT_HALIGN_RIGHT | v,
					text=str(numar), color=culoareText if luat else c['eticheta'], color_sel=culoareSel))
			x = latNr + int(16 * self.f)
		if self._arataBifa(col, r, i):
			x += self._bifa(e, x, h, self._bifat(col, r, i), col == self.focus) + int(12 * self.f)
		sg = self.sigle
		if sg is not None and (fel == 'canal' or (fel == 'intrare' and _g(obj, 'fel', 'canal') in ('canal', 'flux'))):
			# sigla canalului (piconul) in caseta ei, langa nume; fara sigla caseta ramane goala (numele aliniate)
			ptr = sg.sigla(_g(obj, 'ref'))
			if ptr is not None and MultiContentEntryPixmapAlphaBlend is not None:
				e.append(MultiContentEntryPixmapAlphaBlend(pos=(x, (h - sg.inaltime) // 2), size=(sg.latime, sg.inaltime),
					png=ptr))
			x += sg.latime + int(12 * self.f)
		dreapta = self._dreapta(col, r)
		latDreapta = int(sum(lat for _t, lat, _c in dreapta) * self.f) if dreapta else 0
		nume, stins, dosar = self._nume(col, r)
		culoareNume = culoareText if luat else (c['stins'] if stins else (c['focus'] if dosar else c['text']))
		e.append(MultiContentEntryText(pos=(x, 0), size=(max(10, w - x - latDreapta - int(12 * self.f)), h), font=0,
			flags=RT_HALIGN_LEFT | v, text=nume, color=culoareNume, color_sel=culoareSel))
		if dreapta:
			xd = w - latDreapta - int(8 * self.f)
			for text, latime, culoare in dreapta:
				lat = int(latime * self.f)
				e.append(MultiContentEntryText(pos=(xd, 0), size=(lat, h), font=1, flags=RT_HALIGN_RIGHT | v, text=text,
					color=culoareText if luat else culoare, color_sel=culoareSel))
				xd += lat
		return e

	def _sigleGata(self):
		"""Siglele decodate intre timp: randurile se deseneaza din nou (o data pentru mai multe sigle)."""
		if not self.inchis:
			self._invalideaza()

	def _arataBifa(self, col, r, i):
		fel, obj, luat = r
		if luat:
			return False
		return self.mod == L.SELECTEAZA and self.focus == col or self._bifat(col, r, i)

	def _bifat(self, col, r, i):
		if col == L.SURSA:
			return self._cheieRand(r) in self.bife[col]
		return i in self.bife[col]

	def _nume(self, col, r):
		"""(numele de pe rand, stins, dosar)."""
		fel, obj, _l = r
		if fel == 'dosar':
			return u'%s  ›' % obj[2], False, True
		if fel == 'buchet':
			t = _g(obj, 'nume', '') or _g(obj, 'id', '')
			return u'%s  ›' % t, bool(_g(obj, 'ascuns')), True
		if fel == 'intrare':
			fi = _g(obj, 'fel', 'canal')
			t = _g(obj, 'nume', '')
			if fi in ('subbuchet', 'alternative'):
				return u'%s  ›' % (t or _('Fără nume')), False, True
			return _numeVazut(t), bool(_g(obj, 'ascuns') or _g(obj, 'mort') or not _areLitere(t)), False
		t = _g(obj, 'nume', '')
		return _numeVazut(t), bool(_g(obj, 'ascuns') or not _areLitere(t)), False

	def _dreapta(self, col, r):
		"""Coloanele din dreapta randului: [(text, latime la 1920, culoare)], cel mult 330 px."""
		fel, obj, _l = r
		c = self.c
		if fel == 'dosar':
			return [(L.text_canale(obj[3] or 0), 170, c['eticheta'])]
		if fel == 'buchet':
			# buchetul blocat sau ascuns: scris pe rand (nu numai stins), ca la canale
			if _g(obj, 'blocat'):
				return [(_('blocat'), 150, c['chihlimbar']), (L.text_canale(_g(obj, 'n', 0) or 0), 180, c['eticheta'])]
			if _g(obj, 'ascuns'):
				return [(_('ascuns'), 150, c['eticheta']), (L.text_canale(_g(obj, 'n', 0) or 0), 180, c['eticheta'])]
			return [(L.text_canale(_g(obj, 'n', 0) or 0), 330, c['eticheta'])]
		if fel == 'intrare':
			fi = _g(obj, 'fel', 'canal')
			if fi in ('subbuchet', 'alternative'):
				n = _g(obj, 'n')
				return [(L.text_canale(n), 330, c['eticheta'])] if n is not None else []
			semn = ''
			culoare = c['eticheta']
			if _g(obj, 'mort'):
				semn, culoare = _('nu mai e în listă'), c['rau']
			elif _g(obj, 'blocat'):
				semn, culoare = _('blocat'), c['chihlimbar']
			elif _g(obj, 'ascuns'):
				semn = _('ascuns')
			srv = _g(obj, 'serviciu')
			if not semn and (_g(srv, 'steaguri', 0) or 0) & DX_NOU:
				semn, culoare = _('nou'), c['bun']
			poz = _g(srv, 'poz_text', '') or _g(obj, 'poz_text', '')
			# pozitia la marginea din dreapta, SD / HD / UHD langa ea; semnul (cand e) inaintea lor; fara semn numele
			# are tot locul (un nume prea lung pentru loc se deruleaza pe randul ales)
			return ([(semn, 180, culoare)] if semn else []) + [(_g(srv, 'hd', '') or '', 70, c['focus']),
				(poz, 130, c['text2'])]
		srv = obj
		acces = _g(srv, 'acces')
		semn = _('ascuns') if _g(srv, 'ascuns') else (_('blocat') if _g(srv, 'blocat') else '')
		if not semn and (_g(srv, 'steaguri', 0) or 0) & DX_NOU:
			semn = _('nou')
		if _g(srv, 'ref') in self.refsBuchet:
			# canalul e deja in buchetul din dreapta
			return [(_g(srv, 'poz_text', '') or '', 130, c['text2']), (_g(srv, 'hd', '') or '', 70, c['focus']),
				(_('în buchet'), 130, c['bun'])]
		if not semn and self.mod == L.RASFOIRE:
			# in cate buchete e (numai la randurile care se vad: functia de constructie)
			try:
				nb = len(self.s.in_buchete(_g(srv, 'ref')) or ())
			except Exception:
				nb = 0
			if nb:
				return [(_g(srv, 'poz_text', '') or '', 130, c['text2']), (_g(srv, 'hd', '') or '', 70, c['focus']),
					(L.ngettext('în %d buchet', 'în %d buchete', nb) % nb, 130, c['eticheta'])]
		return [(_g(srv, 'poz_text', '') or '', 130, c['text2']), (_g(srv, 'hd', '') or '', 70, c['focus']),
			(semn or ('FTA' if acces == 'fta' else (_('criptat') if acces == 'criptat' else '')), 130,
				c['eticheta'] if semn else (c['bun'] if acces == 'fta' else c['chihlimbar']))]

	# ------------------------------------------------------------ ce se vede in jur

	def _seteazaFocus(self):
		"""Coloana cu focus: banda aleasa in culoarea imaginii; in cealalta, banda stinsa (se vede unde e cursorul)."""
		for col in (L.SURSA, L.BUCHET):
			lista = self[self._numeLista(col)]
			try:
				culoare = self.c['brand'] if col == self.focus else self.c['pista']
				lista.instance.setBackgroundColorSelected(gRGB(culoare))
			except Exception:
				pass
		self._invalideaza()

	def _arataGol(self, col, text):
		w = self['golSursa' if col == L.SURSA else 'golBuchet']
		w.setText(text)
		if text:
			w.show()
		else:
			w.hide()

	def _arata(self):
		"""Randul modurilor, capetele coloanelor, indiciul si tastele colorate, dupa starea de acum."""
		self._deseneazaModuri()
		self._pune('capSursa', self._capSursa())
		self._pune('capBuchet', self._capBuchet())
		if self._afisat.get('focusCap') != self.focus:
			self._afisat['focusCap'] = self.focus
			try:
				for col, nume in ((L.SURSA, 'capSursa'), (L.BUCHET, 'capBuchet')):
					culoare = self.c['focus'] if col == self.focus else self.c['eticheta']
					self[nume].instance.setForegroundColor(gRGB(culoare))
					self[nume].instance.invalidate()
			except Exception:
				pass
		if self.lucru:
			self._pune('indiciu', self.lucru)
		elif self.cifre.text:
			self._pune('indiciu', L.text_cifre(self.cifre.text))
		elif self._mesaj:
			self._pune('indiciu', self._mesaj)
		else:
			r = self._curent()
			pe_dosar = r is not None and (r[0] in ('dosar', 'buchet') or (r[0] == 'intrare' and
				_g(r[1], 'fel') in ('subbuchet', 'alternative')))
			self._pune('indiciu', _(L.indiciu(self.mod, self.focus, pe_dosar, self._laRadacina())))
		taste = L.taste_colorate(self.mod, self.focus, self._laRadacina())
		self.actiuniCulori = [a for a, _t in taste]
		for nume, (_a, text) in zip(('key_red', 'key_green', 'key_yellow', 'key_blue'), taste):
			self._pune(nume, _(text) if text else '')

	def _pune(self, nume, text):
		"""Textul unui element, numai cand se schimba (fara redesen si fara palpaire la fiecare sageata)."""
		if self._afisat.get(nume) != text:
			self._afisat[nume] = text
			self[nume].setText(text)

	def _deseneazaModuri(self):
		c = self.c
		h = self.inaltimeMod
		f = self.f
		e = [None]
		x = 0
		lat = int(220 * f)
		pas = int(12 * f)
		for mod in L.MODURI:
			ales = mod == self.mod
			fundal = c['brand'] if ales else c['pista']
			e.append(MultiContentEntryText(pos=(x, 0), size=(lat, h), font=0, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER,
				text=_(L.NUME_MOD[mod]).upper() if ales else _(L.NUME_MOD[mod]), color=c['alb'] if ales else c['text2'],
				color_sel=c['alb'], backcolor=fundal, backcolor_sel=fundal))
			x += lat + pas
		stare = []
		n = self.s.nesalvate() if self.s is not None else 0
		if n:
			stare.append(L.text_nesalvate(n))
		nb = len(self.bife[self.focus])
		if nb:
			stare.append(L.text_bifate(nb))
		if self.mana is not None:
			stare.append(_('în mână: %d') % len(self.mana['randuri']))
		text = u' · '.join(stare)
		cheie = (self.mod, text, n > 0)
		if self._afisat.get('moduri') == cheie:
			return
		self._afisat['moduri'] = cheie
		e.append(MultiContentEntryText(pos=(x, 0), size=(max(10, self.latimeModuri - x), h), font=0,
			flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=text,
			color=c['chihlimbar'] if n else c['eticheta'], color_sel=c['chihlimbar']))
		self['moduri'].setList([e])

	def _capSursa(self):
		parti = [_('SURSA'), _(NUME_SURSA[self.sursaFel])]
		if self.sursaDosar is not None:
			parti.append(self.sursaDosar[2])
		if self.sursaFel == 'cautare':
			text = self.cautareText + self.inAsteptare
			if text:
				parti.append(u'„%s%s”' % (text, '_' if self.scrieText or self.inAsteptare else ''))
			nf = sum(len(v) for v in self.cautareSelectie.values())
			if nf:
				parti.append(L.ngettext('%d filtru', '%d filtre', nf) % nf)
		n = len(self.randuri[L.SURSA])
		if self.s is not None:
			if self.sursaDosar is not None or self.sursaFel in ('toate', 'cautare'):
				parti.append(L.text_canale(n))
			elif self.sursaFel == 'sateliti':
				parti.append(L.ngettext('%d poziție', '%d poziții', n) % n)
			elif self.sursaFel == 'furnizori':
				parti.append(L.ngettext('%d furnizor', '%d furnizori', n) % n)
			elif self.sursaFel == 'buchete':
				parti.append(L.ngettext('%d buchet', '%d buchete', n) % n)
			else:
				parti.append(L.ngettext('%d transponder', '%d transpondere', n) % n)
		return u' · '.join(parti)

	def _capBuchet(self):
		if self._laRadacina():
			n = len(self.baza)
			return u' · '.join((_('BUCHETELE'), _('Radio') if self.radio else 'TV',
				L.ngettext('%d buchet', '%d buchete', n) % n))
		nume = u' › '.join(n for _i, n in self.cale)
		parti = [_('BUCHETUL'), nume, L.text_canale(self.nCanale)]
		if G.buchet_automat(self._buchetCurent()):
			parti.append(_('refăcut automat'))
		return u' · '.join(parti)

	def _dupaSchimbare(self, text=None):
		"""Dupa o schimbare: „Anulează” mereu la vedere, cu numele schimbarii (regula de simplitate 5)."""
		nume = None
		try:
			nume = self.s.de_anulat() if self.s is not None else None
		except Exception:
			pass
		# numele schimbarii spune deja ce s-a facut („Adăugat: Pro TV”): textul ecranului numai fara el
		self._spune(_('< Anulează: %s') % nume if nume else (text or ''))

	def _spune(self, text, ms=PAUZA_INDICIU_MS):
		"""Un mesaj scurt in randul indiciului (dupa o schimbare), cat PAUZA_INDICIU_MS (sau ms)."""
		self._mesaj = text
		self.ceasMesaj.start(ms, True)
		self._arata()

	def _mesajGata(self):
		self._mesaj = None
		if not self.inchis:
			self._arata()

	# ------------------------------------------------------------ tastele: sus, jos, stanga, dreapta, pagina

	def _nimic(self):
		pass

	def keyUp(self):
		self._mutaCursor(-1)

	def keyDown(self):
		self._mutaCursor(1)

	def _mutaCursor(self, pas, pagina=False):
		if self._asteapta():
			return
		if self.scrieText:
			self._opresteScrisul()
			self._arata()
		self._mesaj = None
		if self.mana is not None:
			k = len(self.mana['randuri'])
			n = len(self.baza)
			self.mana['la'] = L.muta_loc(self.mana['la'], pas * (self.randuriPagina if pagina else 1), n, k,
				self.mana['copie'] or self.mana['din'] != self.mana['tinta'])
			self._arataMana()
			return
		lista = self[self._numeLista(self.focus)]
		if not self.randuri[self.focus]:
			return
		if pagina:
			if pas < 0:
				lista.pageUp()
			else:
				lista.pageDown()
		elif pas < 0:
			lista.up()
		else:
			lista.down()
		self._arata()

	def keyLeft(self):
		if self.mana is not None:
			self._mutaCursor(-1, True)
			return
		self._schimbaColoana(L.SURSA)

	def keyRight(self):
		if self.mana is not None:
			self._mutaCursor(1, True)
			return
		self._schimbaColoana(L.BUCHET)

	def keyColoana(self):
		if self.mana is None:
			self._schimbaColoana(L.BUCHET if self.focus == L.SURSA else L.SURSA)

	def _schimbaColoana(self, col):
		if col == self.focus or self.s is None:
			return
		self._opresteScrisul()
		self._golesteCifrele()
		if self.mod == L.SELECTEAZA:
			# bifele sunt ale unei coloane: trecerea in cealalta inchide selectia
			self.bife[self.focus].goleste()
			self.mod = L.RASFOIRE
		self.focus = col
		self._mesaj = None
		self._seteazaFocus()
		self._arata()

	def keyPagina(self, pas):
		self._mutaCursor(pas, True)

	def keyCapat(self, pas):
		if self.s is None:
			return
		if self.mana is not None:
			k = len(self.mana['randuri'])
			copie = self.mana['copie'] or self.mana['din'] != self.mana['tinta']
			self.mana['la'] = 0 if pas < 0 else L.maxim_loc(len(self.baza), k, copie)
			self._arataMana()
			return
		n = len(self.randuri[self.focus])
		if n:
			self[self._numeLista(self.focus)].moveToIndex(0 if pas < 0 else n - 1)
			self._arata()

	# ------------------------------------------------------------ OK si EXIT

	def _asteapta(self):
		"""True cat partea comuna lucreaza in fundal (citirea, salvarea, intoarcerea la o copie): tastele asteapta."""
		if self.lucru:
			self._pune('indiciu', self.lucru)
			return True
		return self.s is None

	def keyOk(self):
		if self._asteapta():
			return
		if self.cifre.text:
			self._cifreGata()
			return
		if self.scrieText:
			self._opresteScrisul()
			self._arata()
			return
		if self.mana is not None:
			self._lasa()
			return
		r = self._curent()
		if r is None:
			return
		if self.mod == L.SELECTEAZA:
			i = self._index_curent()
			if self.focus == L.BUCHET and self._eMarcaj(r):
				# OK pe un marcaj: toata grupa lui (bifata sau debifata deodata)
				grupa = self._grupaMarcajului(i)
				da = i not in self.bife[L.BUCHET]
				for j in grupa:
					self.bife[L.BUCHET].pune(j, da)
				self._invalideaza(L.BUCHET)
				self._arata()
				return
			self._comutaBifa(self.focus, i)
			self._mutaCursor(1)
			return
		fel, obj, _l = r
		if self.focus == L.SURSA:
			if fel == 'dosar':
				self.sursaDosar = obj[:3]
				self._incarcaSursa(pastreaza=False)
				self['sursa'].moveToIndex(0)
				self._arata()
			else:
				self._adaugaDinSursa([r])
			return
		if fel == 'buchet':
			self._intraInBuchet(_g(obj, 'id'), _g(obj, 'nume', ''))
			return
		fi = _g(obj, 'fel', 'canal')
		if fi in ('subbuchet', 'alternative'):
			self._intraInBuchet(_g(obj, 'buchet_id'), _g(obj, 'nume', ''))
			return
		self._ia(copie=False)

	def _intraInBuchet(self, buchet_id, nume):
		if not buchet_id:
			return
		self.cale.append((buchet_id, nume))
		self.bife[L.BUCHET].goleste()
		self._incarcaBuchet(pastreaza=False, index=0)
		self._arata()
		self._notaAutomat()

	def _notaAutomat(self):
		"""Buchetul deschis e refacut de alt modul (DAB+ / DVB-T2 din satelit, DVB-I, ultima scanare): se spune."""
		nota = G.buchet_automat(self._buchetCurent())
		if nota:
			self._spune(nota, 15000)

	def _urcaBuchet(self):
		if not self.cale:
			return False
		iesit = self.cale.pop()
		self.bife[L.BUCHET].goleste()
		self._incarcaBuchet(pastreaza=False)
		# cursorul pe buchetul (sau sub-buchetul) din care s-a iesit
		for i, (fel, obj, _l) in enumerate(self.randuri[L.BUCHET]):
			if _g(obj, 'id') == iesit[0] or _g(obj, 'buchet_id') == iesit[0]:
				self['buchet'].moveToIndex(i)
				break
		self._arata()
		return True

	def keyExit(self):
		if self.lucru:
			self._pune('indiciu', self.lucru)
			return
		if self.s is None:
			self.close(False)
			return
		if self.cifre.text:
			self._golesteCifrele()
			self._arata()
			return
		if self.scrieText:
			self._opresteScrisul()
			self._arata()
			return
		if self.mana is not None:
			self._puneInapoi()
			return
		if self.mod == L.SELECTEAZA:
			self._gataSelectia()
			return
		if self.focus == L.SURSA:
			if self.sursaDosar is not None:
				vechi = ('dosar',) + tuple(self.sursaDosar[:2])
				self.sursaDosar = None
				self._incarcaSursa(pastreaza=False)
				self._laCheie(L.SURSA, vechi)
				self._arata()
				return
			if self.sursaFel == 'cautare' and (self.cautareText or self.inAsteptare):
				self.cautareText = self.inAsteptare = ''
				self._incarcaSursa()
				self._arata()
				return
		elif self._urcaBuchet():
			return
		self._iesire()

	def _iesire(self):
		n = self.s.nesalvate() if self.s is not None else 0
		if not n:
			self.close(self.salvat)
			return
		titlu = _('Ai %s. Salvezi?') % L.text_nesalvate(n)
		rezumat = self._rezumatSchimbari()
		if rezumat:
			titlu = u'%s\n%s' % (titlu, rezumat)
		self.session.openWithCallback(self._raspunsIesire, ChoiceBox, title=titlu,
			list=[(_('Salvează'), 'salveaza'), (_('Renunță'), 'renunta'), (_('Rămâi'), 'raman')])

	def _rezumatSchimbari(self):
		"""Ce se scrie la salvare, pe scurt: buchetele schimbate (numele, cel mult 4) si canalele sterse din receptor."""
		sch = self.s.schimbari() if self.s is not None else {}
		randuri = []
		nume = []
		for bid in sch.get('buchete') or ():
			if bid in ('bouquets.tv', 'bouquets.radio'):
				continue
			try:
				b = self.s.buchet(bid)
			except Exception:
				b = None
			if b is not None and _g(b, 'nume'):
				nume.append(_g(b, 'nume'))
		if nume:
			randuri.append(_('Buchete schimbate: %s') % (u', '.join(nume[:4]) + (u', …' if len(nume) > 4 else u'')))
		k = sch.get('servicii_noi') or 0
		if k:
			randuri.append(L.ngettext('%d canal nou în receptor', '%d canale noi în receptor', k) % k)
		k = sch.get('servicii_sterse') or 0
		if k:
			randuri.append(L.ngettext('%d canal șters din receptor', '%d canale șterse din receptor', k) % k)
		k = sch.get('servicii_schimbate') or 0
		if k:
			randuri.append(L.ngettext('%d canal schimbat în receptor', '%d canale schimbate în receptor', k) % k)
		return u'\n'.join(randuri)

	def _raspunsIesire(self, ales):
		if not ales or ales[1] == 'raman':
			return
		if ales[1] == 'salveaza':
			self._salveaza(iesire=True)
			return
		self.close(self.salvat)

	# ------------------------------------------------------------ tastele colorate

	def keyCuloare(self, k):
		if self._asteapta():
			return
		act = self.actiuniCulori[k] if k < len(getattr(self, 'actiuniCulori', ())) else ''
		if not act:
			return
		self._opresteScrisul()
		f = {
			'sursa': self.keyAlegeSursa, 'adauga': self.keyAdauga, 'selecteaza': self.keySelecteaza,
			'filtre': self.keyFiltre, 'scoate': self.keySterge, 'muta': boundFunction(self._ia, False),
			'buchetele': self.keyBuchetele, 'sterge_buchet': self.keySterge, 'buchet_nou': self.keyBuchetNou,
			'debifeaza_tot': self.keyDebifeazaTot, 'bifeaza_tot': self.keyBifeazaTot, 'gata': self._gataSelectia,
			'copiaza': boundFunction(self._ia, True), 'pune_inapoi': self._puneInapoi, 'lasa': self._lasa,
			'capat': self.keyCapatMana, 'alt_buchet': self.keyAltBuchet,
		}.get(act)
		if f is not None:
			f()

	def keyAlegeSursa(self):
		lista = [(_(NUME_SURSA[f]), f) for f in SURSE]
		ales = SURSE.index(self.sursaFel)
		self.session.openWithCallback(self._sursaAleasa, ChoiceBox, title=_('De unde iei canalele?'), list=lista,
			selection=ales)

	def _sursaAleasa(self, ales):
		if not ales:
			return
		self.sursaFel = ales[1]
		self.sursaDosar = None
		self.bife[L.SURSA].goleste()
		self._incarcaSursa(pastreaza=False)
		if self.randuri[L.SURSA]:
			self['sursa'].moveToIndex(0)
		self.focus = L.SURSA
		self._seteazaFocus()
		self._arata()
		if self.sursaFel == 'cautare' and not self.cautareText and not self.cautareSelectie:
			self.keyTastatura()

	def keyFiltre(self):
		from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleFiltre
		index = self._index()
		if index is None:
			self._spune(_('Se pregătește lista de canale…'))
			return
		self.session.openWithCallback(self._filtreAlese, HdsEditorCanaleFiltre, index, self.cautareSelectie,
			self.radio, lambda sel: len(self._filtreaza('', sel)))

	def _filtreAlese(self, selectie=None):
		if selectie is None:
			return
		self.cautareSelectie = selectie
		_FILTRE_TINUTE['sel'] = dict((g, set(v)) for g, v in selectie.items())
		self.sursaFel = 'cautare'
		self.sursaDosar = None
		self._incarcaSursa(pastreaza=False)
		if self.randuri[L.SURSA]:
			self['sursa'].moveToIndex(0)
		self.focus = L.SURSA
		self._seteazaFocus()
		self._arata()

	def keySelecteaza(self):
		if self.mod == L.SELECTEAZA:
			self._gataSelectia()
			return
		self.mod = L.SELECTEAZA
		r = self._curent()
		if self.focus == L.BUCHET and self._eMarcaj(r) and not len(self.bife[L.BUCHET]):
			# galben pe un marcaj: toata grupa lui, ca sa se mute deodata
			for j in self._grupaMarcajului(self._index_curent()):
				self.bife[L.BUCHET].pune(j, True)
		elif r is not None and self._bifabil(r) and not len(self.bife[self.focus]):
			self._comutaBifa(self.focus, self._index_curent())
		self._invalideaza(self.focus)
		self._arata()

	def _grupaMarcajului(self, i):
		"""Indicii grupei unui marcaj: marcajul si randurile de sub el, pana la marcajul urmator."""
		randuri = self.randuri[L.BUCHET]
		ind = [i]
		for j in range(i + 1, len(randuri)):
			if randuri[j][0] == 'intrare' and _g(randuri[j][1], 'fel') == 'marcaj':
				break
			ind.append(j)
		return ind

	def _eMarcaj(self, r):
		return r is not None and r[0] == 'intrare' and _g(r[1], 'fel') == 'marcaj'

	def _gataSelectia(self):
		self.mod = L.RASFOIRE
		self.bife[self.focus].goleste()
		self._invalideaza()
		self._arata()

	@staticmethod
	def _bifabil(r):
		"""Randul se poate bifa: orice rand care nu e „in mana”; in sursa si dosarele (satelitii, furnizorii,
		transponderele, buchetele: MENU lucreaza pe cele bifate)."""
		fel, obj, luat = r
		return not luat

	def _comutaBifa(self, col, i):
		randuri = self.randuri[col]
		if not 0 <= i < len(randuri) or not self._bifabil(randuri[i]):
			return
		cheie = self._cheieRand(randuri[i]) if col == L.SURSA else i
		self.bife[col].comuta(cheie)
		self._gata[col].pop(id(randuri[i]), None)
		try:
			self[self._numeLista(col)].l.invalidateEntry(i)
		except Exception:
			self._invalideaza(col)
		self._arata()

	def keyBifeazaTot(self):
		if self.s is None or self.mana is not None:
			return
		col = self.focus
		chei = [k for k, r in zip(self._chei(col), self.randuri[col]) if self._bifabil(r)]
		self.bife[col].toate(chei)
		self.mod = L.SELECTEAZA
		self._invalideaza(col)
		self._arata()

	def keyDebifeazaTot(self):
		self.bife[self.focus].goleste()
		self._invalideaza(self.focus)
		self._arata()

	def keyBifeazaPas(self, pas):
		"""Shift + Sus / Jos: bifeaza randul de acum si pe cel urmator (selectia se largeste)."""
		if self.s is None or self.mana is not None:
			return
		col = self.focus
		if self.mod != L.SELECTEAZA:
			self.mod = L.SELECTEAZA
		i = self._index_curent()
		randuri = self.randuri[col]
		chei = self._chei(col)
		for j in (i, i + pas):
			if 0 <= j < len(randuri) and self._bifabil(randuri[j]):
				self.bife[col].pune(chei[j], True)
		self._mutaCursor(pas)
		self._invalideaza(col)
		self._arata()

	def keyBuchetele(self):
		while self.cale:
			self.cale.pop()
		self.bife[L.BUCHET].goleste()
		self._incarcaBuchet(pastreaza=False)
		self._arata()

	def keyBuchetNou(self):
		self.session.openWithCallback(self._numeBuchetNou, VirtualKeyBoard, title=_('Numele buchetului nou'), text='')

	def _numeBuchetNou(self, nume=None):
		nume = (nume or '').strip()
		if not nume:
			return
		la = self._index_curent(L.BUCHET) + 1 if self._laRadacina() and self.randuri[L.BUCHET] else None
		parinte = None if self._laRadacina() else self._buchetCurent()
		if not self._fa(self.s.buchet_nou, nume, radio=self.radio, parinte=parinte, la=la):
			return
		self._incarcaBuchet()
		for i, (fel, obj, _l) in enumerate(self.randuri[L.BUCHET]):
			if _g(obj, 'nume') == nume:
				self['buchet'].moveToIndex(i)
		self.focus = L.BUCHET
		self._seteazaFocus()
		self._dupaSchimbare(_('Buchet nou: %s') % nume)

	# ------------------------------------------------------------ operatiile

	def _fa(self, functie, *a, **k):
		"""O operatie a partii comune; o eroare pentru om apare in indiciu. -> rezultatul sau None (si False la eroare)."""
		try:
			rez = functie(*a, **k)
			return True if rez is None else rez
		except G.Ocupat as e:
			# sesiunea insasi lucreaza (o unealta, citirea): textul partii comune; altfel e deschisa in web
			self._spune((e.mesaj or _('Nu se poate.')) if e.acum else
				_('Lista e deschisă acum în interfața web: aici doar o poți privi.'))
		except G.Eroare as e:
			self._spune(str(e) or _('Nu se poate.'))
		except Exception as e:
			_jurnal('operatia %s: %r' % (getattr(functie, '__name__', '?'), e))
			self._spune(_('Nu se poate.'))
		return False

	def _refa(self):
		"""Dupa o schimbare (sau anulare): amandoua coloanele din nou, cu cursorul pe acelasi loc."""
		self._incarcaSursa()
		self._incarcaBuchet()
		self._arata()

	def _refsAlese(self, col):
		"""Referintele de lucrat: cele bifate (in ordinea listei) sau randul de sub cursor."""
		randuri = self.randuri[col]
		chei = self._chei(col)
		ind = self.bife[col].indici(chei) if len(self.bife[col]) else [self._index_curent(col)]
		alese = [randuri[i] for i in ind if 0 <= i < len(randuri) and self._bifabil(randuri[i])]
		return alese, ind

	def keyAdauga(self):
		if self.focus != L.SURSA:
			return
		alese, _i = self._refsAlese(L.SURSA)
		r = self._curent(L.SURSA)
		if not len(self.bife[L.SURSA]) and r is not None and r[0] == 'dosar':
			self._adaugaDosar(r)
			return
		dosare = [x for x in alese if x[0] == 'dosar']
		if dosare and len(dosare) == len(alese):
			# satelitii / furnizorii / buchetele bifate: toate canalele lor (o intrebare cu numarul)
			canale = []
			vazute = set()
			for x in dosare:
				for c in self._dinDosar(x[1][0], x[1][1]):
					k = _g(c, 'ref')
					if k and k not in vazute:
						vazute.add(k)
						canale.append(c)
			if not canale:
				return
			nume = u', '.join(x[1][2] for x in dosare[:3]) + (u', …' if len(dosare) > 3 else u'')
			self.session.openWithCallback(boundFunction(self._raspunsDosar, [('canal', c, False) for c in canale]),
				MessageBox, _('Adaugi toate cele %d canale din %s în buchet?') % (len(canale), nume),
				MessageBox.TYPE_YESNO)
			return
		self._adaugaDinSursa(alese)

	def _adaugaDosar(self, r):
		fel, cheie, text, n = r[1]
		canale = self._dinDosar(fel, cheie)
		if not canale:
			return
		self.session.openWithCallback(boundFunction(self._raspunsDosar, [('canal', c, False) for c in canale]),
			MessageBox, _('Adaugi toate cele %d canale din %s în buchet?') % (len(canale), text), MessageBox.TYPE_YESNO)

	def _raspunsDosar(self, randuri, da):
		if da:
			self._adaugaDinSursa(randuri)

	def _adaugaDinSursa(self, randuri, la=None, buchet_id=None, dupaRand=False):
		"""Canalele sursei in buchetul din dreapta: la sfarsit (sau, cu dupaRand, dupa randul ales acolo; sau la locul
		dat). Fara buchet deschis, intai alegerea buchetului. Canalele deja in buchet se sar (partea comuna)."""
		refs = [_g(obj, 'ref') for fel, obj, _l in randuri if fel == 'canal' and _g(obj, 'ref')]
		if not refs:
			return
		buchet_id = buchet_id or (self._buchetCurent() if not self._laRadacina() else None)
		if buchet_id is None:
			self._alegeBuchet(_('În ce buchet pui canalele?'), boundFunction(self._adaugaInAles, refs))
			return
		if la is None:
			la = self._index_curent(L.BUCHET) + 1 if dupaRand and self.randuri[L.BUCHET] else len(self.baza)
		pus = self._fa(self.s.adauga, buchet_id, refs, la=la)
		if pus is False:
			return
		pus = len(refs) if pus is True else int(pus or 0)
		self.bife[L.SURSA].goleste()
		if self.mod == L.SELECTEAZA:
			self.mod = L.RASFOIRE
		if buchet_id == self._buchetCurent():
			self._incarcaBuchet(index=la + max(pus, 1) - 1)
		self._invalideaza(L.SURSA)
		if not pus:
			self._spune(_('Era deja în buchet.') if len(refs) == 1 else _('Erau deja în buchet.'))
			return
		nume = _g(randuri[0][1], 'nume', '')
		self._dupaSchimbare(_('Adăugat: %s') % nume if pus == 1 and len(refs) == 1 else
			L.ngettext('Adăugat %d canal', 'Adăugate %d canale', pus) % pus)

	def _adaugaInAles(self, refs, buchet):
		if buchet is None:
			return
		bid, nume = buchet
		self.cale = [(bid, nume)]
		self._incarcaBuchet(pastreaza=False)
		la = len(self.baza)
		if self._fa(self.s.adauga, bid, refs, la=la):
			self._incarcaBuchet(index=la + len(refs) - 1)
			self.bife[L.SURSA].goleste()
			if self.mod == L.SELECTEAZA:
				self.mod = L.RASFOIRE
			self._invalideaza(L.SURSA)
			self._spune(L.ngettext('Adăugat %d canal', 'Adăugate %d canale', len(refs)) % len(refs))

	def _alegeBuchet(self, titlu, la_ales, fara=None):
		buchete = [b for b in self._buchete() if _g(b, 'id') != fara]
		if not buchete:
			self._spune(_('Niciun buchet. Albastru: buchet nou.'))
			return
		lista = [(_g(b, 'nume', '') or _g(b, 'id', ''), (_g(b, 'id'), _g(b, 'nume', ''))) for b in buchete]

		def ales(rez):
			la_ales(rez[1] if rez else None)
		self.session.openWithCallback(ales, ChoiceBox, title=titlu, list=lista)

	def keySterge(self):
		"""Rosu / Delete: in buchet scoate randurile alese (fara intrebare: se poate anula); la radacina sterge
		buchetul, cu intrebare."""
		if self.s is None or self.mana is not None or self.focus != L.BUCHET:
			return
		if self._laRadacina():
			r = self._curent(L.BUCHET)
			if r is None:
				return
			b = r[1]
			self.session.openWithCallback(boundFunction(self._raspunsStergeBuchet, _g(b, 'id'), _g(b, 'nume', '')),
				MessageBox, _('Ștergi buchetul %s (%s)? Canalele rămân în lista receptorului.') % (_g(b, 'nume', ''),
				L.text_canale(_g(b, 'n', 0) or 0)), MessageBox.TYPE_YESNO, default=False)
			return
		alese, ind = self._refsAlese(L.BUCHET)
		ind = [i for i in ind if 0 <= i < len(self.randuri[L.BUCHET])]
		if not ind:
			return
		nume = _g(self.randuri[L.BUCHET][ind[0]][1], 'nume', '')
		buchet = self.cale[-1][1]
		if len(ind) == 1:
			text = _('Ștergi %s din buchetul %s? Canalul rămâne în lista receptorului.') % (nume, buchet)
		else:
			text = L.ngettext('Ștergi %d rând din buchetul %s? Canalele rămân în lista receptorului.',
				'Ștergi %d rânduri din buchetul %s? Canalele rămân în lista receptorului.', len(ind)) % (len(ind), buchet)
		self.session.openWithCallback(boundFunction(self._raspunsScoate, ind), MessageBox, text, MessageBox.TYPE_YESNO)

	def _raspunsScoate(self, ind, da):
		if not da or self.s is None:
			return
		if not self._fa(self.s.scoate, self._buchetCurent(), ind):
			return
		self.bife[L.BUCHET].goleste()
		self.mod = L.RASFOIRE
		self._incarcaBuchet(index=ind[0])
		self._dupaSchimbare()

	def _raspunsStergeBuchet(self, bid, nume, da):
		if not da:
			return
		if self._fa(self.s.sterge_buchet, bid):
			self._incarcaBuchet()
			self._dupaSchimbare()

	# ------------------------------------------------------------ blocul in mana (MUTA / COPIAZA)

	def _ia(self, copie=False, randuri_sursa=None):
		"""Ia randurile alese (bifate sau cel de sub cursor) din buchet: MUTA (copie=False) sau COPIAZA. Din sursa
		(randuri_sursa): COPIAZA in buchetul din dreapta."""
		if self.s is None:
			return
		if randuri_sursa is not None:
			refs = [r for r in randuri_sursa if r[0] == 'canal']
			if not refs or self._laRadacina():
				return
			self.mana = {'copie': True, 'din': None, 'tinta': self._buchetCurent(), 'indici': [],
				'randuri': [(fel, obj) for fel, obj, _l in refs], 'la': self._index_curent(L.BUCHET) + 1 if self.baza else 0}
		else:
			if self.focus != L.BUCHET or not self.randuri[L.BUCHET]:
				return
			alese, ind = self._refsAlese(L.BUCHET)
			ind = [i for i in ind if 0 <= i < len(self.baza)]
			if not ind:
				i = self._index_curent(L.BUCHET)
				if not 0 <= i < len(self.baza):
					return
				ind = [i]
			ind = sorted(ind)
			bid = self._buchetCurent() if not self._laRadacina() else self._radacinaId()
			self.mana = {'copie': bool(copie), 'din': bid, 'tinta': bid, 'indici': ind,
				'randuri': [(self.baza[i][0], self.baza[i][1]) for i in ind],
				'la': L.loc_initial(ind) if not copie else ind[-1] + 1}
		self.mana['cale'] = list(self.cale)
		self.mod = L.COPIAZA if self.mana['copie'] else L.MUTA
		self.bife[L.BUCHET].goleste()
		if self.focus != L.BUCHET:
			self.focus = L.BUCHET
			self._seteazaFocus()
		self._arataMana()

	def _radacinaId(self):
		return self.s.radacina(self.radio)

	def _buchetCurent_sau_radacina(self):
		return self._buchetCurent() if not self._laRadacina() else self._radacinaId()

	def _arataMana(self):
		m = self.mana
		self._puneRanduriBuchet(self.baza)
		if m['tinta'] == self._buchetCurent_sau_radacina():
			self['buchet'].moveToIndex(max(0, min(m['la'], len(self.randuri[L.BUCHET]) - 1)))
		self._arataGol(L.BUCHET, '')
		self._arata()

	def keyCapatMana(self):
		m = self.mana
		if m is None:
			return
		copie = m['copie'] or m['din'] != m['tinta']
		m['la'] = L.loc_capat(m['la'], len(self.baza), len(m['randuri']), copie)
		self._arataMana()

	def keyAltBuchet(self):
		m = self.mana
		if m is None:
			return
		self._alegeBuchet(_('În ce buchet duci rândurile?'), self._altBuchetAles)

	def _altBuchetAles(self, buchet):
		m = self.mana
		if buchet is None or m is None:
			return
		bid, nume = buchet
		m['tinta'] = bid
		self.cale = [(bid, nume)]
		self._incarcaBuchet(pastreaza=False)
		m['la'] = len(self.baza) if bid != m['din'] or m['copie'] else L.loc_initial(m['indici'])
		self._arataMana()

	def _lasa(self):
		"""OK in MUTA / COPIAZA: randurile se pun la locul aratat (o singura schimbare, cu anulare)."""
		m = self.mana
		if m is None:
			return
		k = len(m['randuri'])
		tinta = m['tinta']
		la = m['la']
		ok = True
		if m['din'] is None:
			refs = [_g(obj, 'ref') for fel, obj in m['randuri']]
			ok = self._fa(self.s.adauga, tinta, refs, la=la)
			text = L.ngettext('Adăugat %d canal', 'Adăugate %d canale', k) % k
		elif m['copie']:
			ok = self._fa(self.s.copiaza, m['din'], m['indici'], tinta, la)
			text = L.ngettext('Copiat %d rând', 'Copiate %d rânduri', k) % k
		elif m['din'] != tinta:
			ok = self._fa(self.s.muta_in, m['din'], m['indici'], tinta, la)
			text = L.ngettext('Mutat %d rând în alt buchet', 'Mutate %d rânduri în alt buchet', k) % k
		else:
			if not L.schimbat(len(self.baza), m['indici'], la, False):
				self.mana = None
				self.mod = L.RASFOIRE
				self._incarcaBuchet(index=m['indici'][0])
				self._arata()
				return
			ok = self._fa(self.s.muta, tinta, m['indici'], la)
			text = L.ngettext('Mutat %d rând', 'Mutate %d rânduri', k) % k
		if not ok:
			return
		self.mana = None
		self.mod = L.RASFOIRE
		self._incarcaBuchet(index=la)
		self._dupaSchimbare(text)

	def _puneInapoi(self):
		m = self.mana
		if m is None:
			return
		self.mana = None
		self.mod = L.RASFOIRE
		if m['din'] is not None and self._buchetCurent_sau_radacina() != m['din']:
			self.cale = m['cale']
		self._incarcaBuchet(pastreaza=False, index=m['indici'][0] if m['indici'] else 0)
		if m['din'] is None:
			self.focus = L.SURSA
			self._seteazaFocus()
		self._arata()

	def keyMutaPas(self, pas):
		"""Ctrl + Sus / Jos: randul (sau bifatele) cu un rand mai sus / jos, pe loc (o schimbare)."""
		if self.s is None or self.focus != L.BUCHET or self.mana is not None or not self.baza:
			return
		alese, ind = self._refsAlese(L.BUCHET)
		ind = sorted(i for i in ind if 0 <= i < len(self.baza))
		if not ind:
			return
		la = L.muta_loc(L.loc_initial(ind), pas, len(self.baza), len(ind), False)
		if not L.schimbat(len(self.baza), ind, la, False):
			return
		bifate = len(self.bife[L.BUCHET]) > 0
		if not self._fa(self.s.muta, self._buchetCurent_sau_radacina(), ind, la):
			return
		self._incarcaBuchet(index=la + (self._index_curent(L.BUCHET) - ind[0] if not bifate else 0))
		if bifate:
			self.bife[L.BUCHET].goleste()
			for j in range(la, la + len(ind)):
				self.bife[L.BUCHET].pune(j, True)
			self['buchet'].moveToIndex(la)
		self._invalideaza(L.BUCHET)
		self._arata()

	# ------------------------------------------------------------ cifrele

	def keyCifra(self, n):
		if self._asteapta():
			return
		if self.focus == L.SURSA and self.mana is None:
			if _dinTastatura():
				self._scrieInCautare(str(n))
				return
			litera = self.sms.getKey(n)
			if litera is None:
				return
			self.inAsteptare = litera
			if len(LITERE_SMS[n]) == 1:
				self.sms.nextChar()
			self._cautareSchimbata()
			return
		self.cifre.apasa(n)
		self.ceasCifre.start(L.PAUZA_CIFRE_MS, True)
		self._arata()

	def _golesteCifrele(self):
		self.cifre.goleste()
		self.ceasCifre.stop()

	def _cifreGata(self):
		self.ceasCifre.stop()
		poz = self.cifre.ia()
		if poz is None or self.inchis:
			self._arata()
			return
		if self.mana is not None:
			m = self.mana
			copie = m['copie'] or m['din'] != m['tinta']
			m['la'] = L.loc_din_pozitie(poz, len(self.baza), len(m['randuri']), copie)
			self._arataMana()
			return
		if self.focus == L.BUCHET:
			# pozitia = numarul canalului din buchet (marcajele nu au numar); fara numere, randul
			tinta = None
			for i, (fel, obj, _l) in enumerate(self.randuri[L.BUCHET]):
				if _g(obj, 'numar') == poz:
					tinta = i
					break
			if tinta is None:
				tinta = L.pozitie_in_lista(poz, len(self.randuri[L.BUCHET]))
			if tinta is not None:
				self['buchet'].moveToIndex(tinta)
		self._arata()

	# ------------------------------------------------------------ cautarea (sursa)

	def _scrieInCautare(self, ch):
		if self.sursaFel != 'cautare':
			self.sursaFel = 'cautare'
			self.sursaDosar = None
			self.cautareText = ''
		self.sms.nextKey()
		self.cautareText += self.inAsteptare + ch
		self.inAsteptare = ''
		self._cautareSchimbata()

	def _literaConfirmata(self):
		if self.inAsteptare:
			self.cautareText += self.inAsteptare
			self.inAsteptare = ''
			if not self.inchis:
				self._arata()

	def _cautareSchimbata(self):
		if self.sursaFel != 'cautare':
			self.sursaFel = 'cautare'
			self.sursaDosar = None
		self._incarcaSursa(pastreaza=False)
		if self.randuri[L.SURSA]:
			self['sursa'].moveToIndex(0)
		self._arata()

	def keyStergeLitera(self):
		if self.inAsteptare:
			self.sms.nextKey()
			self.inAsteptare = ''
		elif self.cautareText:
			self.cautareText = self.cautareText[:-1]
		else:
			return
		self._cautareSchimbata()

	def keyAscii(self):
		"""Literele tastaturii in modul text (dupa prima litera scrisa direct in sursa)."""
		# numele global getPrevAsciiCode: tastatura din pagina web (HdsMouseEcran.scrieAscii) il inlocuieste cat scrie
		try:
			cod = getPrevAsciiCode()
		except Exception:
			return 0
		if cod in (8, 127):
			self.keyStergeLitera()
			return 1
		try:
			ch = chr(cod)
		except Exception:
			return 0
		if not ch.isprintable():
			return 0
		self._scrieInCautare(ch)
		return 1

	def keyTastatura(self):
		if self.s is None or self.mana is not None:
			return
		self._opresteScrisul()
		self.sms.nextKey()
		self.cautareText += self.inAsteptare
		self.inAsteptare = ''
		self.session.openWithCallback(self._dinTastaturaEcran, VirtualKeyBoard, title=_('Numele canalului căutat'),
			text=self.cautareText)

	def _dinTastaturaEcran(self, text=None):
		if text is None:
			return
		self.cautareText = text.strip()
		self.inAsteptare = ''
		self.focus = L.SURSA
		self._seteazaFocus()
		self._cautareSchimbata()

	# ------------------------------------------------------------ anularea, salvarea

	def keyAnuleaza(self):
		if self.s is None or self.mana is not None:
			return
		nume = self._fa(self.s.anuleaza)
		if nume is True or nume is False or not nume:
			if nume is not False:
				self._spune(_('Nimic de anulat.'))
			return
		self._refa()
		self._spune(_('Anulat: %s') % nume + u' · ' + _('> refă'))

	def keyReface(self):
		if self.s is None or self.mana is not None:
			return
		nume = self._fa(self.s.reface)
		if nume is True or nume is False or not nume:
			if nume is not False:
				self._spune(_('Nimic de refăcut.'))
			return
		self._refa()
		self._spune(_('Refăcut: %s') % nume)

	def keySalveaza(self):
		if self._asteapta() or self.mana is not None:
			return
		self._salveaza()

	def _salveaza(self, iesire=False):
		"""Copia de siguranta, scrierea si reincarcarea listelor (partea comuna, pe firul ei); la sfarsit, cu iesire,
		editorul se inchide."""
		if self.s is None or self.lucru:
			return
		self.lucru = _('Se salvează…')
		self._arata()
		self.s.salveaza_fundal(boundFunction(self._salvat, iesire), self._salvareEsuata)

	def _salvat(self, iesire, copie=None):
		self.lucru = ''
		self.salvat = True
		if self.inchis:
			return
		if iesire:
			self.close(True)
			return
		cand = _g(copie, 'cand')
		if cand:
			import time
			text = _('Salvat. Copia de siguranță: %s') % time.strftime('%d.%m %H:%M', time.localtime(cand))
		else:
			text = _('Salvat.')
		avert = _g(copie, 'avertismente')
		if avert:
			text += u' \u00b7 ' + (avert[0] if isinstance(avert, (list, tuple)) else str(avert))
		self._refa()
		self._spune(text)

	def _salvareEsuata(self, e=None):
		self.lucru = ''
		if self.inchis:
			return
		_jurnal('salvarea: %r' % (e,))
		mesaj = str(e) if isinstance(e, G.Eroare) and str(e) else _('Lista nu s-a salvat. Schimbările au rămas aici: încearcă din nou.')
		self._spune(mesaj)

	# ------------------------------------------------------------ redenumirea, ascunderea, blocarea

	def keyRedenumeste(self):
		r = self._curent()
		if r is None or self.mana is not None:
			return
		fel, obj, _l = r
		if fel == 'dosar':
			return
		self.session.openWithCallback(boundFunction(self._numeNou, self.focus, self._index_curent(), r), VirtualKeyBoard,
			title=_('Numele nou'), text=_g(obj, 'nume', '') or '')

	def _numeNou(self, col, i, r, nume=None):
		nume = (nume or '').strip()
		if not nume:
			return
		fel, obj, _l = r
		if col == L.SURSA:
			ok = self._fa(self.s.redenumeste_serviciu, _g(obj, 'ref'), nume)
		elif fel == 'buchet':
			ok = self._fa(self.s.redenumeste_buchet, _g(obj, 'id'), nume)
		elif _g(obj, 'fel', 'canal') == 'canal' and _g(obj, 'ref'):
			# un canal din buchet: o singura intrebare, numai aici sau peste tot (numele din lista receptorului)
			self.session.openWithCallback(boundFunction(self._undeRedenumesc, i, obj, nume), ChoiceBox,
				title=_('Unde se schimbă numele „%s”?') % nume,
				list=[(_('Numai în acest buchet'), 'buchet'), (_('Peste tot'), 'peste_tot')])
			return
		else:
			ok = self._fa(self.s.redenumeste, self._buchetCurent(), i, nume)
		if ok:
			self._refa()
			self._dupaSchimbare()

	def _undeRedenumesc(self, i, obj, nume, ales):
		if not ales:
			return
		if ales[1] == 'peste_tot':
			ok = self._fa(self.s.redenumeste_serviciu, _g(obj, 'ref'), nume)
		else:
			ok = self._fa(self.s.redenumeste, self._buchetCurent(), i, nume)
		if ok:
			self._refa()
			self._dupaSchimbare()

	def _refsCanale(self, col):
		alese, _i = self._refsAlese(col)
		refs = []
		for fel, obj, _l in alese:
			if fel == 'canal':
				refs.append(_g(obj, 'ref'))
			elif fel == 'intrare' and _g(obj, 'fel', 'canal') in ('canal', 'flux'):
				refs.append(_g(obj, 'ref'))
		return [x for x in refs if x]

	def _ascunde(self, da):
		refs = self._refsCanale(self.focus)
		if refs and self._fa(self.s.ascunde, refs, da):
			self._refa()
			self._dupaSchimbare()

	def _blocheaza(self, da):
		refs = self._refsCanale(self.focus)
		if not refs:
			return
		if da:
			self._faBlocare(refs, True)
			return
		# deblocarea cere PIN-ul de canal, daca controlul parental e pornit
		try:
			from Components.config import config
			if config.ParentalControl.configured.value:
				from Screens.InputBox import PinInput
				self.session.openWithCallback(boundFunction(self._pinDeblocare, refs), PinInput,
					pinList=[config.ParentalControl.servicepin[0].value],
					triesEntry=config.ParentalControl.retries.servicepin, title=_('Enter the service pin'),
					windowTitle=_('Change pin code'))
				return
		except Exception as e:
			_jurnal('PIN: %r' % (e,))
		self._faBlocare(refs, False)

	def _pinDeblocare(self, refs, bun):
		if bun:
			self._faBlocare(refs, False)
		elif bun is not None:
			self.session.open(MessageBox, _('The pin code you entered is wrong.'), MessageBox.TYPE_ERROR, timeout=8)

	def _faBlocare(self, refs, da):
		if self._fa(self.s.blocheaza, refs, da):
			self._refa()
			self._dupaSchimbare()

	# ------------------------------------------------------------ clipboardul (tastatura)

	def keyCopiazaClip(self):
		self._clip(False)

	def keyTaieClip(self):
		self._clip(True)

	def _clip(self, taiere):
		if self.s is None or self.mana is not None:
			return
		col = self.focus
		alese, ind = self._refsAlese(col)
		if col == L.SURSA:
			refs = [_g(obj, 'ref') for fel, obj, _l in alese if fel == 'canal']
			self.clip.pune(refs)
		else:
			if self._laRadacina():
				return
			ind = [i for i in ind if 0 <= i < len(self.baza)]
			refs = [_g(self.baza[i][1], 'ref') for i in ind]
			self.clip.pune(refs, self._buchetCurent(), ind, taiere)
		n = len(self.clip.refs)
		if n:
			self._spune((L.ngettext('Tăiat %d rând', 'Tăiate %d rânduri', n) if self.clip.taiere else
				L.ngettext('Copiat %d rând', 'Copiate %d rânduri', n)) % n + u' · ' + _('Ctrl+V îl pune'))

	def keyLipesteClip(self):
		if self.s is None or self.mana is not None or self.clip.gol() or self._laRadacina():
			return
		tinta = self._buchetCurent()
		la = self._index_curent(L.BUCHET) + 1 if self.baza else 0
		c = self.clip
		if c.taiere and c.din_buchet is not None:
			# randurile taiate trebuie sa fie tot acolo (altfel, dupa alte schimbari, se lipeste o copie)
			try:
				din = self.baza if c.din_buchet == tinta else [('intrare', i, False) for i in self.s.intrari(c.din_buchet)]
				la_loc = [_g(din[i][1], 'ref') if 0 <= i < len(din) else None for i in c.indici] == c.refs
			except Exception:
				la_loc = False
			if not la_loc:
				c.taiere = False
		if c.taiere and c.din_buchet is not None:
			if c.din_buchet == tinta:
				la = L.muta_loc(sum(1 for i in range(la) if i not in set(c.indici)), 0, len(self.baza), len(c.indici), False)
				ok = self._fa(self.s.muta, tinta, c.indici, la)
			else:
				ok = self._fa(self.s.muta_in, c.din_buchet, c.indici, tinta, la)
		else:
			ok = self._fa(self.s.adauga, tinta, c.refs, la=la)
		if not ok:
			return
		n = len(c.refs)
		c.dupa_lipire()
		self._incarcaBuchet(index=la)
		self._dupaSchimbare(L.ngettext('Pus %d rând', 'Puse %d rânduri', n) % n)

	# ------------------------------------------------------------ MENU

	def keyMeniu(self):
		if self._asteapta() or self.mana is not None:
			return
		self._opresteScrisul()
		r = self._curent()
		lista = []
		are = self.s.are
		da = self.s.de_anulat()
		if da:
			lista.append((_('Anulează: %s') % da, 'anuleaza'))
		dr = self.s.de_refacut()
		if dr:
			lista.append((_('Refă: %s') % dr, 'reface'))
		if self.s.nesalvate():
			lista.append((_('Salvează acum'), 'salveaza'))
			if are('schimbari'):
				lista.append((_('Ce s-a schimbat de la ultima salvare'), 'schimbari'))
		fel = r[0] if r is not None else None
		obj = r[1] if r is not None else None
		canal = fel == 'canal' or (fel == 'intrare' and _g(obj, 'fel', 'canal') in ('canal', 'flux'))
		fi = _g(obj, 'fel', 'canal') if fel == 'intrare' else None
		if self.focus == L.BUCHET:
			if self._laRadacina():
				lista.append((_('Buchet nou'), 'buchet_nou'))
				if r is not None:
					b = r[1]
					lista.append((_('Redenumește buchetul'), 'redenumeste'))
					lista.append((_('Mută buchetul'), 'muta'))
					if are('copiaza_buchet'):
						lista.append((_('Copiază buchetul'), 'copiaza_b'))
					if are('ascunde_buchet'):
						lista.append((_('Arată buchetul') if _g(b, 'ascuns') else _('Ascunde buchetul'),
							'arata_b' if _g(b, 'ascuns') else 'ascunde_b'))
					lista.append((_('Deblochează buchetul') if _g(b, 'blocat') else _('Blochează buchetul'),
						'deblocheaza_b' if _g(b, 'blocat') else 'blocheaza_b'))
					lista.append((_('Șterge buchetul'), 'sterge'))
				if len(self.bife[L.BUCHET]) and are('sorteaza_buchete'):
					lista.append((_('Sortează buchetele alese'), 'sorteaza_buchete'))
				# buchetele gasite pe disc, care nu sunt in lista: puse inapoi in lista, sau sterse de pe disc
				for nb in self._nelegate():
					nume = _g(nb, 'nume') or _g(nb, 'id')
					lista.append((u'%s: %s' % (_('Pune în listă'), nume), ('leaga', _g(nb, 'id'))))
					if are('sterge_nelegat'):
						lista.append((u'%s: %s' % (_('Șterge de pe disc'), nume), ('sterge_nelegat', _g(nb, 'id'),
							nume, _g(nb, 'n', 0) or 0)))
			else:
				if r is not None and fel == 'intrare':
					lista.append((_('Redenumește'), 'redenumeste'))
					lista.append((_('Mută la poziția…'), 'pozitie'))
					lista.append((_('Mută la început'), 'inceput'))
					lista.append((_('Mută la sfârșit'), 'sfarsit'))
					lista.append((_('Mută în…'), 'muta_alt'))
					lista.append((_('Copiază în…'), 'copiaza'))
					if fi == 'flux' and are('schimba_flux'):
						lista.append((_('Editează fluxul'), 'editeaza_flux'))
					if fi == 'alternative' and are('alternative_desface'):
						lista.append((_('Desface alternativele'), 'alt_desface'))
					if canal:
						lista.append((_('Detalii'), 'detalii'))
						if self._inBuchete(L.BUCHET) > 1:
							lista.append((_('Șterge din toate buchetele'), 'scoate_toate'))
							if are('scoate_canale'):
								lista.append((_('Scoate dintr-un buchet...'), 'scoate_din'))
				if are('alternative_noi') and self._canaleAlese(L.BUCHET):
					lista.append((_('Unește ca alternative (același canal din alte locuri)'), 'alt_noi'))
				lista.append((_('Marcaj nou'), 'marcaj'))
				if self.s.are_flux_nou():
					lista.append((_('Flux nou (adresă de internet)'), 'flux'))
				lista.append((_('Rând gol (spațiu)'), 'spatiu'))
				lista.append((_('Sub-buchet nou'), 'subbuchet'))
				lista.append((_('Sortează…'), 'sorteaza'))
				if are('aranjeaza_dupa') and len(self._buchete()) > 1:
					lista.append((_('Aranjează după alt buchet...'), 'aranjeaza'))
				if any(f == 'intrare' and _g(o, 'fel') == 'marcaj' for f, o, _l in self.baza):
					lista.append((_('Scoate marcajele din buchet'), 'scoate_marcaje'))
		else:
			dosare = self._dosareAlese()
			if dosare:
				felDosar = dosare[0][0]
				if felDosar in ('satelit', 'furnizor') and are('buchete_din'):
					lista.append((_('Fă câte un buchet din fiecare ales'), 'buchete_din'))
				if felDosar == 'satelit' and are('sterge_sateliti'):
					lista.append((_('Șterge din receptor'), 'sterge_sateliti'))
					lista.append((_('Păstrează numai cei bifați'), 'pastreaza_sateliti'))
				if felDosar == 'transponder' and are('sterge_transpondere'):
					lista.append((_('Șterge transponderele bifate'), 'sterge_tp_bifate'))
			elif r is not None and fel == 'dosar':
				lista.append((_('Adaugă tot în buchet'), 'adauga'))
				if r[1][0] in ('satelit', 'furnizor', 'transponder'):
					lista.append((_('Buchet nou din %s') % r[1][2], 'buchet_din'))
				if r[1][0] in ('satelit', 'transponder'):
					lista.append((_('Șterge din receptor: %s') % r[1][2], 'sterge_dosar'))
			if canal:
				lista.append((_('Adaugă după rândul ales din buchet'), 'adauga_aici'))
				lista.append((_('Adaugă înaintea rândului ales din buchet'), 'adauga_inainte'))
				lista.append((_('Adaugă la începutul buchetului'), 'adauga_inceput'))
				if self._altDinDreapta() is not None and are('alternative_adauga'):
					lista.append((_('Pune în alternativele din dreapta'), 'alt_pune'))
				lista.append((_('Detalii'), 'detalii'))
				lista.append((_('Redenumește canalul'), 'redenumeste'))
				if self._inBuchete(L.SURSA):
					lista.append((_('Șterge din toate buchetele'), 'scoate_toate'))
					if are('scoate_canale'):
						lista.append((_('Scoate dintr-un buchet...'), 'scoate_din'))
				lista.append((_('Șterge din receptor'), 'sterge_receptor'))
			if self.sursaFel == 'cautare' and self.randuri[L.SURSA] and self.sursaDosar is None:
				lista.append((_('Buchet nou din rezultatele căutării'), 'buchet_cautare'))
		if canal:
			ascuns = _g(obj, 'ascuns') or _g(_g(obj, 'serviciu'), 'ascuns')
			blocat = _g(obj, 'blocat') or _g(_g(obj, 'serviciu'), 'blocat')
			lista.append((_('Arată canalul în listă') if ascuns else _('Ascunde canalul în listă'),
				'arata' if ascuns else 'ascunde'))
			lista.append((_('Deblochează canalul') if blocat else _('Blochează canalul (control parental)'),
				'deblocheaza' if blocat else 'blocheaza'))
			if are('scoate_nou') and self._refsNoi():
				lista.append((_('Scoate semnul „nou”'), 'scoate_nou'))
		if self.mod != L.SELECTEAZA:
			lista.append((_('Selectează tot'), 'bifeaza_tot'))
		else:
			lista.append((_('Deselectează tot'), 'debifeaza_tot'))
		lista.append((_('Canale de test'), 'test'))
		lista.append((_('Dubluri'), 'dubluri'))
		lista.append((_('Canale care nu mai există'), 'moarte'))
		if are('verifica'):
			lista.append((_('Verifică lista'), 'verifica'))
		if G.unelte() is not None and are('sterge_transpondere'):
			lista.append((_('Buchete goale'), 'goale'))
			lista.append((_('Transpondere fără canale'), 'transpondere'))
			lista.append((_('Fluxuri care nu răspund'), 'fluxuri'))
		if self._areSigle():
			lista.append((_('Sigle nefolosite'), 'sigle'))
		if are('curata_steaguri'):
			lista.append((_('Curățenie'), 'curatenie'))
		if self.s.are_import():
			lista.append((_('Importă de pe stick…'), 'importa'))
		if self.s.are_export():
			lista.append((_('Scrie lista pe stick…'), 'exporta'))
			if self.focus == L.BUCHET and not self._laRadacina() and are('exporta_m3u'):
				lista.append((_('Scrie buchetul ca m3u pe stick…'), 'exporta_m3u'))
		lista.append((_('Copii de siguranță'), 'copii'))
		lista.append((_('Lista radio') if not self.radio else _('Lista TV'), 'lista'))
		lista.append((_('Ajutorul editorului'), 'ajutor'))
		self.session.openWithCallback(self._meniuAles, ChoiceBox, title=_('Editorul de canale'), list=lista)

	def _meniuAles(self, ales):
		if not ales or self.s is None:
			return
		a = ales[1]
		if self._actiuneNoua(a):
			return
		if a == 'anuleaza':
			self.keyAnuleaza()
		elif a == 'reface':
			self.keyReface()
		elif a == 'salveaza':
			self._salveaza()
		elif a == 'buchet_nou':
			self.keyBuchetNou()
		elif a == 'redenumeste':
			self.keyRedenumeste()
		elif a == 'muta':
			self._ia(copie=False)
		elif a == 'sterge':
			self.keySterge()
		elif a == 'copiaza':
			self._ia(copie=True)
			self.keyAltBuchet()
		elif a == 'muta_alt':
			self._ia(copie=False)
			self.keyAltBuchet()
		elif a in ('inceput', 'sfarsit'):
			self._ia(copie=False)
			if self.mana is not None:
				self.keyCapat(-1 if a == 'inceput' else 1)
				self._lasa()
		elif a in ('marcaj', 'marcaj_nr'):
			self.session.openWithCallback(boundFunction(self._numeMarcaj, a == 'marcaj_nr'), VirtualKeyBoard,
				title=_('Numele marcajului'), text='')
		elif a == 'detalii':
			self.keyInfo()
		elif a == 'adauga_aici':
			alese, _i = self._refsAlese(L.SURSA)
			self._adaugaDinSursa(alese, dupaRand=True)
		elif a == 'sterge_receptor':
			self._stergeDinReceptor([_g(obj2, 'ref') for fel2, obj2, _l in self._refsAlese(L.SURSA)[0]
				if fel2 == 'canal'])
		elif a == 'buchet_cautare':
			self.session.openWithCallback(self._numeBuchetCautare, VirtualKeyBoard, title=_('Numele buchetului nou'),
				text=self.cautareText)
		elif a == 'flux':
			self.session.openWithCallback(self._adresaFlux, VirtualKeyBoard, title=_('Adresa fluxului (http://...)'),
				text='http://')
		elif a == 'spatiu':
			la = self._index_curent(L.BUCHET) + 1 if self.baza else 0
			if self._fa(self.s.spatiu_nou, self._buchetCurent(), la) is not False:
				self._incarcaBuchet(index=la)
				self._dupaSchimbare()
		elif a == 'pozitie':
			self._ia(copie=False)
			if self.mana is not None:
				self._spune(_('Scrie poziția cu cifrele, apoi OK.'))
		elif a in ('blocheaza_b', 'deblocheaza_b'):
			r = self._curent(L.BUCHET)
			if r is not None and self._fa(self.s.blocheaza_buchet, _g(r[1], 'id'), a == 'blocheaza_b') is not False:
				self._incarcaBuchet()
				self._dupaSchimbare()
		elif a == 'buchet_din':
			r = self._curent(L.SURSA)
			if r is not None and r[0] == 'dosar':
				bid = self._fa(self.s.buchet_din, r[1][0], r[1][1], radio=self.radio, nume=r[1][2])
				if bid and bid is not True:
					self.cale = [(bid, r[1][2])]
					self._incarcaBuchet(pastreaza=False)
					self._dupaSchimbare(_('Buchet nou: %s') % r[1][2])
		elif a == 'copiaza_b':
			r = self._curent(L.BUCHET)
			if r is not None and r[0] == 'buchet':
				bid = self._fa(self.s.copiaza_buchet, _g(r[1], 'id'))
				if bid is not False:
					self._incarcaBuchet()
					self._laCheieBuchet(bid)
					self._dupaSchimbare()
		elif a in ('ascunde_b', 'arata_b'):
			r = self._curent(L.BUCHET)
			if r is not None and r[0] == 'buchet' and \
					self._fa(self.s.ascunde_buchet, _g(r[1], 'id'), a == 'ascunde_b') is not False:
				self._incarcaBuchet()
				self._dupaSchimbare()
		elif isinstance(a, tuple) and a[0] == 'leaga':
			if self._fa(self.s.leaga_buchet, a[1]) is not False:
				self._incarcaBuchet()
				self._laCheieBuchet(a[1])
				self._dupaSchimbare()
		elif a == 'scoate_toate':
			self._scoateDinToate(self._refsCanale(self.focus))
		elif a == 'debifeaza_tot':
			self.keyDebifeazaTot()
		elif a == 'subbuchet':
			self.keyBuchetNou()
		elif a == 'adauga':
			self.keyAdauga()
		elif a in ('ascunde', 'arata'):
			self._ascunde(a == 'ascunde')
		elif a in ('blocheaza', 'deblocheaza'):
			self._blocheaza(a == 'blocheaza')
		elif a == 'bifeaza_tot':
			self.keyBifeazaTot()
		elif a in ('test', 'dubluri', 'moarte'):
			self._unealta(a)
		elif a == 'importa':
			from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleFisier
			self.session.openWithCallback(self._fisierImport, HdsEditorCanaleFisier, 'import')
		elif a in ('exporta', 'exporta_m3u'):
			from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleFisier
			self.session.openWithCallback(boundFunction(self._dosarExport, a), HdsEditorCanaleFisier, 'dosar')
		elif a == 'copii':
			self._copii()
		elif a == 'lista':
			self.keyLista(not self.radio)
		elif a == 'ajutor':
			self.keyAjutor()

	# ------------------------------------------------------------ actiunile MENU ale tabelului functiilor

	ORDINI = ((L.N_('nume'), 'nume'), (L.N_('Satelit și frecvență'), 'pozitie'), (L.N_('Satelit, apoi nume'), 'pozitie_nume'),
		(L.N_('furnizor'), 'furnizor'), (L.N_('Furnizor, apoi nume'), 'furnizor_nume'), (L.N_('frecvență'), 'frecventa'),
		('SID', 'sid'))

	def _actiuneNoua(self, a):
		"""Randurile MENU adaugate dupa tabelul functiilor; True cand a fost unul dintre ele."""
		cheie = a[0] if isinstance(a, tuple) else a
		f = {
			'schimbari': self._arataSchimbari,
			'sorteaza': lambda a: self._alegeOrdinea('buchet'),
			'sorteaza_buchete': lambda a: self._alegeOrdinea('buchete'),
			'sterge_nelegat': self._stergeNelegat,
			'editeaza_flux': self._editeazaFlux,
			'alt_noi': self._altNoi,
			'alt_desface': self._altDesface,
			'alt_pune': self._altPune,
			'scoate_din': self._scoateDin,
			'aranjeaza': self._aranjeaza,
			'scoate_marcaje': self._scoateMarcaje,
			'buchete_din': self._bucheteDin,
			'sterge_sateliti': lambda a: self._stergeSateliti(False),
			'pastreaza_sateliti': lambda a: self._stergeSateliti(True),
			'sterge_tp_bifate': self._stergeTpBifate,
			'sterge_dosar': self._stergeDosar,
			'adauga_inainte': lambda a: self._adaugaLa(False),
			'adauga_inceput': lambda a: self._adaugaLa(True),
			'scoate_nou': self._scoateNou,
			'verifica': lambda a: self._unealta('verifica'),
			'goale': lambda a: self._unealta('goale'),
			'transpondere': lambda a: self._unealta('transpondere'),
			'fluxuri': lambda a: self._unealta('fluxuri'),
			'sigle': lambda a: self._unealta('sigle'),
			'curatenie': self._curatenie,
		}.get(cheie)
		if f is None:
			return False
		f(a)
		return True

	def _faBrut(self, functie, *a, **k):
		"""Ca _fa, dar cu rezultatul asa cum vine (None = nimic schimbat): (True, rezultat) sau (False, None)."""
		try:
			return True, functie(*a, **k)
		except G.Ocupat:
			self._spune(_('Lista e deschisă acum în interfața web: aici doar o poți privi.'))
		except G.Eroare as e:
			self._spune(str(e) or _('Nu se poate.'))
		except Exception as e:
			_jurnal('operatia %s: %r' % (getattr(functie, '__name__', '?'), e))
			self._spune(_('Nu se poate.'))
		return False, None

	def _gataSchimbarea(self, index=None, text=None):
		"""Dupa o operatie pe mai multe randuri: bifele golite, Rasfoire, coloanele din nou, „< Anulează”."""
		for b in self.bife.values():
			b.goleste()
		self.mod = L.RASFOIRE
		self._incarcaSursa()
		self._incarcaBuchet(index=index)
		self._dupaSchimbare(text)

	def _cuPin(self, functie):
		"""functie() dupa PIN-ul de canal, cand controlul parental e pornit (deblocarea)."""
		try:
			from Components.config import config
			if config.ParentalControl.configured.value:
				from Screens.InputBox import PinInput
				self.session.openWithCallback(boundFunction(self._pinBun, functie), PinInput,
					pinList=[config.ParentalControl.servicepin[0].value],
					triesEntry=config.ParentalControl.retries.servicepin, title=_('Enter the service pin'),
					windowTitle=_('Change pin code'))
				return
		except Exception as e:
			_jurnal('PIN: %r' % (e,))
		functie()

	def _pinBun(self, functie, bun):
		if bun:
			functie()
		elif bun is not None:
			self.session.open(MessageBox, _('The pin code you entered is wrong.'), MessageBox.TYPE_ERROR, timeout=8)

	# --- ce s-a schimbat

	def _arataSchimbari(self, a=None):
		text = self._rezumatSchimbari() or _('Nicio schimbare de la ultima salvare.')
		self.session.open(MessageBox, text, MessageBox.TYPE_INFO)

	# --- sortarea (un buchet, sau buchetele bifate din lista buchetelor)

	def _alegeOrdinea(self, ce, invers=False):
		lista = [(t if t == 'SID' else _(t), (ce, dupa, invers)) for t, dupa in self.ORDINI]
		if not invers:
			lista.append((_('În ordine inversă'), (ce, None, True)))
		if ce == 'buchete':
			titlu = _('Sortează buchetele alese')
		else:
			titlu = _('Sortează după') + u' · ' + (_('numai rândurile bifate') if len(self.bife[L.BUCHET]) else
				_('fiecare grupă între marcaje'))
		if invers:
			titlu += u' · ' + _('În ordine inversă')
		self.session.openWithCallback(self._ordineAleasa, ChoiceBox, title=titlu, list=lista)

	def _ordineAleasa(self, ales):
		if not ales or self.s is None:
			return
		ce, dupa, invers = ales[1]
		if dupa is None:
			self._alegeOrdinea(ce, True)
			return
		if ce == 'buchet':
			self._sorteaza(dupa, invers)
			return
		ids = [_g(self.randuri[L.BUCHET][i][1], 'id') for i in self.bife[L.BUCHET].indici(self._chei(L.BUCHET))
			if 0 <= i < len(self.randuri[L.BUCHET]) and self.randuri[L.BUCHET][i][0] == 'buchet']
		ok, n = self._faBrut(self.s.sorteaza_buchete, ids, dupa=dupa, invers=invers)
		if not ok:
			return
		if not n:
			self._spune(_('Buchetele erau deja în această ordine.'))
			return
		self._gataSchimbarea()

	# --- buchetele gasite pe disc

	def _stergeNelegat(self, a):
		_k, bid, nume, n = a
		self.session.openWithCallback(boundFunction(self._raspunsNelegat, bid), MessageBox,
			_('Ștergi buchetul %s (%s)? Canalele rămân în lista receptorului.') % (nume, L.text_canale(n)),
			MessageBox.TYPE_YESNO, default=False)

	def _raspunsNelegat(self, bid, da):
		if da and self._fa(self.s.sterge_nelegat, bid) is not False:
			self._gataSchimbarea()

	# --- fluxurile

	def _canalSursa(self):
		"""Canalul DVB ales in sursa (pentru legarea unui flux la el), sau None."""
		r = self._curent(L.SURSA)
		if r is None or r[0] != 'canal':
			return None
		obj = r[1]
		k5 = _g(obj, 'k5')
		if k5 is None or _g(obj, 'sid') is None:
			return None
		return obj

	def _editeazaFlux(self, a=None):
		i = self._index_curent(L.BUCHET)
		lista = [(_('Adresa fluxului (http://...)'), 'adresa'), (_('Tipul fluxului'), 'tip')]
		src = self._canalSursa()
		if src is not None:
			lista.append((_('Leagă de canalul ales în stânga (siglă și ghid): %s') % _numeVazut(_g(src, 'nume', '')),
				'dvb'))
		self.session.openWithCallback(boundFunction(self._fluxAles, i), ChoiceBox, title=_('Editează fluxul'), list=lista)

	def _fluxAles(self, i, ales):
		if not ales or self.s is None or not 0 <= i < len(self.baza):
			return
		ref = _g(self.baza[i][1], 'ref', '') or ''
		parti = ref.split(':')
		if ales[1] == 'adresa':
			adresa = L.decodeaza(parti[10]) if len(parti) > 10 else ''
			self.session.openWithCallback(boundFunction(self._fluxSchimba, i, 'adresa'), VirtualKeyBoard,
				title=_('Adresa fluxului (http://...)'), text=adresa)
		elif ales[1] == 'tip':
			acum = parti[0] if parti else ''
			lista = [((u'✓ ' if t == acum else u'') + t, t) for t in ('4097', '5001', '5002', '1')]
			self.session.openWithCallback(boundFunction(self._fluxSchimbaTip, i), ChoiceBox, title=_('Tipul fluxului'),
				list=lista)
		elif ales[1] == 'dvb':
			src = self._canalSursa()
			if src is not None:
				sid, ns, tsid, onid = _g(src, 'k5')[:4]
				self._fluxFa(i, sid=sid, tsid=tsid, onid=onid, ns=ns)

	def _fluxSchimbaTip(self, i, ales):
		if ales:
			self._fluxFa(i, tip=int(ales[1]))

	def _fluxSchimba(self, i, camp, valoare=None):
		valoare = (valoare or '').strip()
		if valoare:
			self._fluxFa(i, **{camp: valoare})

	def _fluxFa(self, i, **k):
		ok, rez = self._faBrut(self.s.schimba_flux, self._buchetCurent(), i, **k)
		if ok:
			self._incarcaBuchet(index=i)
			self._dupaSchimbare()

	# --- alternativele

	def _canaleAlese(self, col):
		"""[(indice, rand)] ale canalelor bifate in buchet (sau al celui ales, fara bife)."""
		if col != L.BUCHET or self._laRadacina():
			return []
		randuri = self.randuri[L.BUCHET]
		ind = self.bife[L.BUCHET].indici(self._chei(L.BUCHET)) if len(self.bife[L.BUCHET]) else \
			[self._index_curent(L.BUCHET)]
		return [(i, randuri[i]) for i in ind if 0 <= i < len(randuri) and randuri[i][0] == 'intrare' and
			_g(randuri[i][1], 'fel') == 'canal']

	def _altDinDreapta(self):
		"""Indicele grupei de alternative alese in buchetul din dreapta, sau None."""
		if self._laRadacina():
			return None
		r = self._curent(L.BUCHET)
		if r is not None and r[0] == 'intrare' and _g(r[1], 'fel') == 'alternative':
			return self._index_curent(L.BUCHET)
		return None

	def _altNoi(self, a=None):
		alese = self._canaleAlese(L.BUCHET)
		if not alese:
			return
		self.session.openWithCallback(boundFunction(self._altNume, [i for i, _r in alese]), VirtualKeyBoard,
			title=_('Numele nou'), text=_g(alese[0][1][1], 'nume', '') or '')

	def _altNume(self, ind, nume=None):
		nume = (nume or '').strip()
		if not nume or self.s is None:
			return
		ok, i = self._faBrut(self.s.alternative_noi, self._buchetCurent(), ind, nume)
		if ok:
			self._gataSchimbarea(index=i)

	def _altDesface(self, a=None):
		i = self._index_curent(L.BUCHET)
		if self._fa(self.s.alternative_desface, self._buchetCurent(), i) is not False:
			self._gataSchimbarea(index=i)

	def _altPune(self, a=None):
		i = self._altDinDreapta()
		refs = [_g(obj, 'ref') for fel, obj, _l in self._refsAlese(L.SURSA)[0] if fel == 'canal' and _g(obj, 'ref')]
		if i is None or not refs:
			return
		ok, n = self._faBrut(self.s.alternative_adauga, self._buchetCurent(), i, refs)
		if not ok:
			return
		if not n:
			self._spune(_('Era deja în buchet.') if len(refs) == 1 else _('Erau deja în buchet.'))
			return
		self._gataSchimbarea(index=i)

	# --- scoaterea dintr-un buchet ales, aranjarea dupa alt buchet, marcajele

	def _scoateDin(self, a=None):
		refs = self._refsCanale(self.focus)
		ids = set()
		for ref in refs[:2000]:
			try:
				ids.update(self.s.in_buchete(ref) or ())
			except Exception:
				pass
		lista = []
		for b in self._buchete():
			if _g(b, 'id') in ids:
				lista.append((_g(b, 'nume', '') or _g(b, 'id'), (_g(b, 'id'), _g(b, 'nume', ''))))
		if lista:
			self.session.openWithCallback(boundFunction(self._scoateDinAles, refs), ChoiceBox,
				title=_('Din ce buchet le scoți?'), list=lista)

	def _scoateDinAles(self, refs, ales):
		if not ales:
			return
		bid, nume = ales[1]
		n = len(refs)
		if n == 1:
			text = _('Ștergi %s din buchetul %s? Canalul rămâne în lista receptorului.') % (
				_numeVazut(self._numeRef(refs[0])), nume)
		else:
			text = L.ngettext('Ștergi %d rând din buchetul %s? Canalele rămân în lista receptorului.',
				'Ștergi %d rânduri din buchetul %s? Canalele rămân în lista receptorului.', n) % (n, nume)
		self.session.openWithCallback(boundFunction(self._raspunsScoateDin, bid, refs), MessageBox, text,
			MessageBox.TYPE_YESNO, default=False)

	def _raspunsScoateDin(self, bid, refs, da):
		if da and self._fa(self.s.scoate_canale, bid, refs) is not False:
			self._gataSchimbarea()

	def _numeRef(self, ref):
		try:
			return _g(self.s.serviciu(ref), 'nume', '') or ''
		except Exception:
			return ''

	def _aranjeaza(self, a=None):
		self._alegeBuchet(_('Aranjează după alt buchet...'), self._aranjeazaDupa, fara=self._buchetCurent())

	def _aranjeazaDupa(self, buchet):
		if buchet is None or self.s is None:
			return
		ok, rez = self._faBrut(self.s.aranjeaza_dupa, self._buchetCurent(), buchet[0])
		if not ok:
			return
		if not rez:
			self._spune(_('Buchetul era deja în această ordine.'))
			return
		self._gataSchimbarea()

	def _scoateMarcaje(self, a=None):
		ind = [i for i, (f, o, _l) in enumerate(self.baza) if f == 'intrare' and _g(o, 'fel') == 'marcaj']
		if not ind:
			return
		from Screens.HdsEditorCanaleUnelte import text_intrebare
		self.session.openWithCallback(boundFunction(self._raspunsScoate, ind), MessageBox,
			text_intrebare('sterge_marcaje', len(ind)), MessageBox.TYPE_YESNO, default=False)

	# --- satelitii, furnizorii si transponderele bifate in sursa

	def _dosareAlese(self):
		"""Dosarele bifate in sursa (lista satelitilor, furnizorilor, transponderelor sau buchetelor): [(fel, cheie,
		text)]."""
		if self.focus != L.SURSA or not len(self.bife[L.SURSA]):
			return []
		return [r[1][:3] for r in self.randuri[L.SURSA] if r[0] == 'dosar' and self._cheieRand(r) in self.bife[L.SURSA]]

	def _bucheteDin(self, a=None):
		ds = self._dosareAlese()
		if not ds:
			return
		fel = ds[0][0]
		ok, ids = self._faBrut(self.s.buchete_din, fel, [d[1] for d in ds if d[0] == fel], self.radio)
		if not ok:
			return
		self.cale = []
		self._gataSchimbarea()
		if ids:
			self._laCheieBuchet(ids[0])

	def _stergeSateliti(self, pastreaza):
		ds = [d for d in self._dosareAlese() if d[0] == 'satelit']
		if not ds:
			return
		n = len(ds)
		if pastreaza:
			text = L.ngettext('Păstrezi numai %d satelit? Canalele și transponderele tuturor celorlalți (și cablul, '
				'terestrul) dispar din receptor și din buchete.', 'Păstrezi numai %d sateliți? Canalele și transponderele '
				'tuturor celorlalți (și cablul, terestrul) dispar din receptor și din buchete.', n) % n
		else:
			text = L.ngettext('Ștergi %d satelit din receptor, cu toate canalele lui (TV, radio, date) și '
				'transponderele? Dispar și din buchete.', 'Ștergi %d sateliți din receptor, cu toate canalele lor (TV, '
				'radio, date) și transponderele? Dispar și din buchete.', n) % n
		self.session.openWithCallback(boundFunction(self._raspunsSateliti, [d[1] for d in ds], pastreaza), MessageBox,
			text, MessageBox.TYPE_YESNO, default=False)

	def _raspunsSateliti(self, pozitii, pastreaza, da):
		if da and self._fa(self.s.sterge_sateliti, pozitii, pastreaza=pastreaza) is not False:
			self.sursaDosar = None
			self._gataSchimbarea()

	def _stergeTpBifate(self, a=None):
		ds = [d for d in self._dosareAlese() if d[0] == 'transponder']
		if not ds:
			return
		n = len(ds)
		text = L.ngettext('Ștergi %d transponder din receptor, cu canalele lui? Dispar și din buchete.',
			'Ștergi %d transpondere din receptor, cu canalele lor? Dispar și din buchete.', n) % n
		self.session.openWithCallback(boundFunction(self._raspunsTp, [d[1] for d in ds]), MessageBox, text,
			MessageBox.TYPE_YESNO, default=False)

	def _raspunsTp(self, chei, da):
		if da and self._fa(self.s.sterge_transpondere, chei) is not False:
			self.sursaDosar = None
			self._gataSchimbarea()

	def _stergeDosar(self, a=None):
		"""„Șterge din receptor: <satelit / transponder>”: satelitul sau transponderul cu toate canalele lui (TV, radio,
		date), din receptor si din buchete, cand partea comuna stie; altfel canalele listei, ca inainte."""
		r = self._curent(L.SURSA)
		if r is None or r[0] != 'dosar':
			return
		fel, cheie, text = r[1][:3]
		if fel == 'satelit' and self.s.are('sterge_sateliti'):
			n = len(self.s.din_satelit(cheie, None) or ())
			intrebare = L.ngettext('Ștergi %d canal (TV, radio și date) și transponderele satelitului? Dispar și din '
				'buchete.', 'Ștergi %d canale (TV, radio și date) și transponderele satelitului? Dispar și din buchete.',
				n) % n
			self.session.openWithCallback(boundFunction(self._raspunsSateliti, [cheie], False), MessageBox,
				u'%s\n%s' % (text, intrebare), MessageBox.TYPE_YESNO, default=False)
		elif fel == 'transponder' and self.s.are('sterge_transpondere'):
			n = len(self.s.din_transponder(cheie) or ())
			intrebare = L.ngettext('Ștergi transponderul și %d canal de pe el? Dispare și din buchete.',
				'Ștergi transponderul și cele %d canale de pe el? Dispar și din buchete.', n) % n
			self.session.openWithCallback(boundFunction(self._raspunsTp, [cheie]), MessageBox,
				u'%s\n%s' % (text, intrebare), MessageBox.TYPE_YESNO, default=False)
		else:
			self._stergeDinReceptor([_g(c, 'ref') for c in self._dinDosar(fel, cheie)], text)

	# --- adaugarea inaintea randului ales sau la inceput

	def _adaugaLa(self, inceput):
		alese, _i = self._refsAlese(L.SURSA)
		if self._laRadacina():
			self._adaugaDinSursa(alese)
			return
		la = 0 if inceput or not self.randuri[L.BUCHET] else self._index_curent(L.BUCHET)
		self._adaugaDinSursa(alese, la=la)

	# --- semnul „nou” (canalele noi gasite la scanare)

	def _refsNoi(self):
		"""Referintele canalelor alese (bifate sau cel ales) care au semnul „nou”."""
		rez = []
		for fel, obj, _l in self._refsAlese(self.focus)[0]:
			srv = obj if fel == 'canal' else (_g(obj, 'serviciu') if fel == 'intrare' else None)
			if srv is not None and (_g(srv, 'steaguri', 0) or 0) & DX_NOU:
				rez.append(_g(srv, 'ref'))
		return rez

	def _scoateNou(self, a=None):
		refs = self._refsNoi()
		if refs and self._fa(self.s.scoate_nou, refs) is not False:
			self._gataSchimbarea()

	# --- curatenia

	def _curatenie(self, a=None):
		lista = [(_('Arată toate canalele ascunse'), 'ascunse'), (_('Deblochează toate canalele'), 'blocate'),
			(_('Scoate semnul „nou” de pe toate canalele'), 'noi')]
		self.session.openWithCallback(self._curatenieAleasa, ChoiceBox, title=_('Curățenie'), list=lista)

	def _curatenieAleasa(self, ales):
		if not ales:
			return
		if ales[1] == 'blocate':
			self._cuPin(boundFunction(self._faCuratenie, 'blocate'))
		else:
			self._faCuratenie(ales[1])

	def _faCuratenie(self, fel):
		ok, n = self._faBrut(self.s.curata_steaguri, fel)
		if not ok:
			return
		if not n:
			self._spune(_('Nimic de schimbat.'))
			return
		self._gataSchimbarea()

	def _areSigle(self):
		"""Exista dosare de sigle (atunci are rost „Sigle nefolosite”)."""
		try:
			from Components import HdsEditorSigle as SG
			return bool(SG.dosare_existente())
		except Exception:
			return False

	# ------------------------------------------------------------ stick: importul si exportul

	def _lucreaza(self, text):
		self.lucru = text
		self._arata()

	def _gataLucrul(self):
		self.lucru = ''
		if not self.inchis:
			self._arata()

	def _amana(self, functie):
		"""functie() dupa ce textul lucrului s-a desenat (o operatie lunga pe firul enigma2: importul unei liste)."""
		self._amanat = functie
		self.ceasPas.start(60, True)

	def _pasAmanat(self):
		f, self._amanat = self._amanat, None
		if f is not None and not self.inchis:
			f()

	def _fisierImport(self, ales=None):
		"""Ce s-a ales pe stick: un m3u (fluxuri -> buchet nou), o arhiva sau un dosar cu o lista (intrebarea cu
		numerele: inlocuieste lista sau adauga numai ce lipseste)."""
		if not ales or self.s is None:
			return
		import os
		fel, cale = ales
		if fel == 'fisier' and G.e_m3u(cale):
			try:
				text = G.citeste_m3u(cale)
			except Exception as e:
				_jurnal('m3u %s: %r' % (cale, e))
				self._spune(_('Fișierul nu se poate citi.'))
				return
			nume = os.path.splitext(os.path.basename(cale))[0]
			self.session.openWithCallback(boundFunction(self._felM3u, text, nume), ChoiceBox,
				title=_('Fluxurile din %s') % os.path.basename(cale),
				list=[(_('Un buchet, cu marcaje pe grupe'), False), (_('Câte un buchet pe fiecare grupă'), True)])
			return
		self._lucreaza(_('Se citește lista de pe stick…'))
		if fel == 'fisier':
			def citeste():
				rad = G.despacheteaza(cale)
				return rad, (G.ce_are(rad) if rad else None)
		else:
			def citeste():
				rad = G.gaseste_lista(cale) or cale
				return rad, G.ce_are(rad)
		self.fir.porneste(citeste, boundFunction(self._listaCitita, cale), self._importEsuat)

	def _felM3u(self, text, nume, ales=None):
		if not ales:
			return
		self.session.openWithCallback(boundFunction(self._numeM3u, text, ales[1]), VirtualKeyBoard,
			title=_('Numele buchetului nou'), text=nume)

	def _numeM3u(self, text, pe_grupe, nume=None):
		nume = (nume or '').strip()
		if not nume or self.s is None:
			return
		bid = self._fa(self.s.importa_m3u, text, nume, self.radio, pe_grupe)
		if bid is False:
			return
		self._dupaImport(bid if bid is not True else None)

	def _listaCitita(self, cale, rez):
		self._gataLucrul()
		rad, ce = rez
		if not rad or not ce or not (ce.get('servicii') or ce.get('buchete')):
			G.curata_importul()
			self._spune(_('În arhivă nu e nicio listă de canale (lamedb sau bouquets.tv).'))
			return
		self._importAcum = (cale, rad, ce)
		self._intrebareImport()

	def _titluImport(self):
		import os
		cale, rad, ce = self._importAcum
		nb = len(ce.get('buchete') or ())
		return u'%s\n%s \u00b7 %s' % (os.path.basename(cale.rstrip('/')) or cale, L.text_canale(ce.get('servicii') or 0),
			L.ngettext('%d buchet', '%d buchete', nb) % nb)

	def _intrebareImport(self, *_a):
		"""Ce faci cu lista citita: o inlocuiesti, adaugi numai ce lipseste, vezi intai ce se schimba, sau iei numai
		buchetele alese."""
		cale, rad, ce = self._importAcum
		lista = [(_('Înlocuiește lista de acum'), 'inlocuieste'), (_('Adaugă numai ce lipsește'), 'uneste')]
		U = G.unelte()
		if U is not None and hasattr(U, 'compara_import'):
			lista.append((_('Vezi ce se schimbă'), 'vezi'))
		if ce.get('buchete'):
			lista.append((_('Alege buchetele…'), 'alege'))
		self.session.openWithCallback(boundFunction(self._modImport, rad), ChoiceBox, title=self._titluImport(),
			list=lista)

	def _modImport(self, rad, ales=None):
		if not ales or self.s is None:
			G.curata_importul()
			return
		if ales[1] in ('vezi', 'alege'):
			from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleBife
			if ales[1] == 'vezi':
				self.session.openWithCallback(self._intrebareImport, HdsEditorCanaleBife, self.s, 'compara_import',
					self.radio, rad)
			else:
				self.session.openWithCallback(self._bucheteAlese, HdsEditorCanaleBife, self.s, 'buchete_arhiva',
					self.radio, self._importAcum[2])
			return
		self._lucreaza(_('Se importă lista…'))
		self._amana(boundFunction(self._importa, rad, ales[1]))

	def _bucheteAlese(self, alese=None):
		"""Buchetele bifate din arhiva: se pun (inlocuite sau unite cu cele cu acelasi fisier), iar canalele lor care
		lipsesc intra in lista; restul listei ramane cum e."""
		if not alese:
			self._intrebareImport()
			return
		rad = self._importAcum[1]
		n = len(alese)
		titlu = L.ngettext('%d buchet ales: canalele lui care lipsesc intră în listă, restul listei rămâne.',
			'%d buchete alese: canalele lor care lipsesc intră în listă, restul listei rămâne.', n) % n
		self.session.openWithCallback(boundFunction(self._modAlese, rad, alese), ChoiceBox, title=titlu,
			list=[(_('Înlocuiește aceste buchete'), 'inlocuieste'), (_('Adaugă numai ce lipsește'), 'uneste')])

	def _modAlese(self, rad, alese, ales=None):
		if not ales or self.s is None:
			G.curata_importul()
			return
		self._lucreaza(_('Se importă lista…'))
		self._amana(boundFunction(self._importaAlese, rad, alese, ales[1]))

	def _importaAlese(self, rad, alese, mod):
		try:
			rez = self._fa(self.s.importa_alese, rad, alese, mod)
		finally:
			G.curata_importul()
			self.lucru = ''
		if rez is False:
			self._arata()
			return
		self._dupaImport()

	def _importa(self, rad, mod):
		try:
			rez = self._fa(self.s.importa_dosar, rad, mod)
		finally:
			G.curata_importul()
			self.lucru = ''
		if rez is False:
			self._arata()
			return
		self._dupaImport()

	def _importEsuat(self, e=None):
		self._gataLucrul()
		G.curata_importul()
		_jurnal('importul: %r' % (e,))
		self._spune(str(e) if isinstance(e, G.Eroare) and str(e) else _('Lista de pe stick nu se poate citi.'))

	def _dupaImport(self, bid=None):
		"""Dupa un import (o singura schimbare, cu anulare): lista buchetelor, cursorul pe buchetul nou."""
		for b in self.bife.values():
			b.goleste()
		self.mod = L.RASFOIRE
		self.sursaDosar = None
		self.cale = []
		self._incarcaSursa()
		self._incarcaBuchet(pastreaza=False)
		if bid:
			self._laCheieBuchet(bid)
		self.focus = L.BUCHET
		self._seteazaFocus()
		self._dupaSchimbare()

	def _dosarExport(self, fel, ales=None):
		"""Lista de acum (cu schimbarile nesalvate) ca arhiva tar.gz, sau buchetul deschis ca m3u, scrise pe stick pe un
		fir; numele fisierului are data si ora."""
		if not ales or self.s is None:
			return
		import os
		import time
		dosar = ales[1]
		if fel == 'exporta_m3u':
			bid = self._buchetCurent()
			text = self._fa(self.s.exporta_m3u, bid, _ipReceptor()) if bid else False
			if text is False or text is True:
				return
			cale = os.path.join(dosar, _numeFisier(self.cale[-1][1] or bid) + '.m3u')
			date = text.encode('utf-8')
			self._lucreaza(_('Se scrie pe stick…'))
			self.fir.porneste(lambda: _scrie(cale, date), self._scris, self._scriereEsuata)
			return
		s = self.s
		cale = os.path.join(dosar, 'lista-canale-%s.tar.gz' % time.strftime('%Y%m%d-%H%M'))
		self._lucreaza(_('Se scrie pe stick…'))
		self.fir.porneste(lambda: _scrie(cale, s.arhiva('tar.gz')), self._scris, self._scriereEsuata)

	def _scris(self, cale):
		self._gataLucrul()
		self._spune(_('Scris pe stick: %s') % cale)

	def _scriereEsuata(self, e=None):
		self._gataLucrul()
		_jurnal('scrierea pe stick: %r' % (e,))
		self._spune(_('Nu s-a putut scrie pe stick.'))

	def _numeMarcaj(self, numerotat, nume=None):
		nume = (nume or '').strip()
		if not nume or self._laRadacina():
			return
		la = self._index_curent(L.BUCHET) + 1 if self.baza else 0
		if self._fa(self.s.marcaj_nou, self._buchetCurent(), la, nume, numerotat=numerotat) is not False:
			self._incarcaBuchet(index=la)
			self._dupaSchimbare()

	def _nelegate(self):
		"""Buchetele de felul listei (TV / radio) gasite pe disc, care nu sunt in nicio lista."""
		if self.s is None or not self.s.are('nelegate'):
			return []
		try:
			return list(self.s.nelegate(self.radio) or ())
		except Exception as e:
			_jurnal('nelegate: %r' % (e,))
			return []

	def _inBuchete(self, col):
		"""In cate buchete (laolalta) sunt canalele alese (bifate sau cel de sub cursor); 0 fara scoate_din_toate."""
		if self.s is None or not self.s.are('scoate_din_toate'):
			return 0
		buchete = set()
		for ref in self._refsCanale(col)[:2000]:
			try:
				buchete.update(self.s.in_buchete(ref) or ())
			except Exception:
				pass
		return len(buchete)

	def _laCheieBuchet(self, bid):
		"""Cursorul pe randul buchetului bid (in lista buchetelor)."""
		for i, r in enumerate(self.randuri[L.BUCHET]):
			if r[0] == 'buchet' and _g(r[1], 'id') == bid:
				self['buchet'].moveToIndex(i)
				return

	def _scoateDinToate(self, refs):
		"""„Șterge din toate buchetele”: canalele raman in lista receptorului; intrebarea cu numarul (regula 6)."""
		refs = [x for x in refs if x]
		if not refs:
			return
		n = len(refs)
		text = L.ngettext('Ștergi %d canal din toate buchetele? Rămâne în lista receptorului.',
			'Ștergi %d canale din toate buchetele? Rămân în lista receptorului.', n) % n
		self.session.openWithCallback(boundFunction(self._raspunsScoateDinToate, refs), MessageBox, text,
			MessageBox.TYPE_YESNO, default=False)

	def _raspunsScoateDinToate(self, refs, da):
		if da and self._fa(self.s.scoate_din_toate, refs) is not False:
			for col in (L.SURSA, L.BUCHET):
				self.bife[col].goleste()
			self.mod = L.RASFOIRE
			self._refa()
			self._dupaSchimbare()

	def _stergeDinReceptor(self, refs, nume=None):
		"""„Șterge din receptor”: din lista receptorului si din toate buchetele, cu intrebarea cu numarul."""
		refs = [x for x in refs if x]
		if not refs:
			return
		n = len(refs)
		text = L.ngettext('Ștergi %d canal din receptor? Dispare și din toate buchetele.',
			'Ștergi %d canale din receptor? Dispar și din toate buchetele.', n) % n
		if nume:
			text = u'%s\n%s' % (nume, text)
		self.session.openWithCallback(boundFunction(self._raspunsStergeReceptor, refs), MessageBox, text,
			MessageBox.TYPE_YESNO, default=False)

	def _raspunsStergeReceptor(self, refs, da):
		if da and self._fa(self.s.sterge_servicii, refs) is not False:
			self.bife[L.SURSA].goleste()
			self.mod = L.RASFOIRE
			self._refa()
			self._dupaSchimbare()

	def _numeBuchetCautare(self, nume=None):
		nume = (nume or '').strip()
		refs = [_g(obj, 'ref') for fel, obj, _l in self.randuri[L.SURSA] if fel == 'canal']
		if not nume or not refs:
			return
		bid = self._fa(self.s.buchet_nou, nume, radio=self.radio, refs=refs)
		if bid and bid is not True:
			self.cale = [(bid, nume)]
			self._incarcaBuchet(pastreaza=False)
			self._dupaSchimbare(_('Buchet nou: %s') % nume)

	def _adresaFlux(self, adresa=None):
		adresa = (adresa or '').strip()
		if not adresa or adresa in ('http://', 'https://') or self._laRadacina():
			return
		self.session.openWithCallback(boundFunction(self._numeFlux, adresa), VirtualKeyBoard,
			title=_('Numele fluxului'), text='')

	def _numeFlux(self, adresa, nume=None):
		nume = (nume or '').strip()
		if not nume:
			return
		la = self._index_curent(L.BUCHET) + 1 if self.baza else 0
		if self._fa(self.s.flux_nou, self._buchetCurent(), la, adresa, nume) is not False:
			self._incarcaBuchet(index=la)
			self._dupaSchimbare()

	def keyInfo(self):
		"""INFO: detaliile canalului de sub cursor, in cuvinte simple."""
		if self._asteapta():
			return
		r = self._curent()
		if r is None:
			return
		fel, obj, _l = r
		srv = obj if fel == 'canal' else (_g(obj, 'serviciu') if fel == 'intrare' else None)
		if srv is None:
			return
		from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleDetalii
		self.session.open(HdsEditorCanaleDetalii, srv, self.s)

	def _sortAles(self, ales):
		if ales:
			self._sorteaza(*ales[1])

	def _sorteaza(self, dupa, invers=False):
		if self._laRadacina():
			return
		ind = self.bife[L.BUCHET].indici(self._chei(L.BUCHET)) or None
		if self._fa(self.s.sorteaza, self._buchetCurent(), dupa=dupa, indici=ind, invers=invers):
			self.bife[L.BUCHET].goleste()
			self.mod = L.RASFOIRE
			self._incarcaBuchet()
			self._dupaSchimbare()

	def _unealta(self, fel, extra=None):
		from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleBife
		self.session.openWithCallback(self._dupaUnealta, HdsEditorCanaleBife, self.s, fel, self.radio, extra)

	def _dupaUnealta(self, schimbat=False):
		if schimbat:
			# siglele sterse de pe disc nu mai raman in memoria randurilor
			if self.sigle is not None:
				self.sigle.uita()
			self._refa()

	def _copii(self):
		from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleCopii
		self.session.openWithCallback(self._dupaCopie, HdsEditorCanaleCopii, self.s)

	def _dupaCopie(self, intors=False):
		if intors == 'schimbat':
			# din comparatia cu o copie: un buchet nou sau canale aduse inapoi
			self._refa()
			self._dupaSchimbare()
			return
		if intors:
			self.salvat = True
			self.cale = [x for x in self.cale if any(_g(b, 'id') == x[0] for b in self._buchete())][:1]
			self._refa()
			self._spune(_('Lista s-a întors la copia aleasă.'))

	def keyLista(self, radio):
		if self.s is None or self.mana is not None or bool(radio) == self.radio:
			return
		self.radio = bool(radio)
		self.setTitle(self._titlu())
		self.sursaDosar = None
		self.cale = []
		for b in self.bife.values():
			b.goleste()
		self.mod = L.RASFOIRE
		self._incarcaSursa(pastreaza=False)
		self._incarcaBuchet(pastreaza=False)
		self._arata()

	def keyAjutor(self):
		from Screens.HdsEditorCanaleUnelte import HdsEditorCanaleAjutor
		self.session.openWithCallback(self._dupaAjutor, HdsEditorCanaleAjutor)

	def _dupaAjutor(self, listaTastelor=False):
		if listaTastelor:
			self.showHelp()

	# ------------------------------------------------------------ mouse-ul (Components/HdsMouseEcran.py)

	def _listaSub(self, x, y):
		"""(coloana, randul de sub mouse sau None, pe bara de derulare) cand (x, y) cade pe una din liste; altfel None."""
		if x is None or y is None:
			return None
		for col in (L.SURSA, L.BUCHET):
			inst = getattr(self[self._numeLista(col)], 'instance', None)
			if inst is None:
				continue
			try:
				p = inst.getAbsolutePosition()
				s = inst.size()
				lx, ly, lw, lh = p.x(), p.y(), s.width(), s.height()
			except Exception:
				continue
			if lx <= x < lx + lw and ly <= y < ly + lh:
				n = len(self.randuri[col])
				pagina = max(1, lh // max(1, self.inaltimeRand))
				bara = n > pagina and x >= lx + lw - min(max(lw // 16, 18), 22) - 5
				i = inst.getTopIndex() + (y - ly) // max(1, self.inaltimeRand)
				return col, (i if 0 <= i < n else None), bara, (ly, lh)
		return None

	def hdsGestMouse(self, fel, x=None, y=None, clicuri=1, pasi=0, x0=None, y0=None, nou=False, text='', mod=None):
		"""Gestul mouse-ului pe editor (cheamat de HdsMouseEcran.MouseEcran.gest). -> dictionarul raspunsului, sau None
		cand gestul nu cade pe liste (atunci il face MouseEcran: butoanele colorate, clic dreapta, MENU). mod: Ctrl /
		Shift tinute in pagina web ({'ctrl', 'shift'}); None = cele de la tastatura pusa in receptor."""
		if self.s is None:
			return None
		if fel in ('clic', 'dublu'):
			return self._clicMouse(x, y, 2 if fel == 'dublu' else clicuri, mod)
		if fel == 'drag':
			return self._trasMouse(x, y, x0, y0, nou)
		if fel == 'dragend':
			return self._trasGata(x, y)
		if fel == 'rotita':
			return self._rotitaMouse(x, y, pasi)
		if fel == 'pagina':
			self.keyPagina(1 if pasi > 0 else -1)
			return {'facut': 'derulare', 'ecran': self.__class__.__name__}
		if fel == 'capat':
			self.keyCapat(1 if pasi > 0 else -1)
			return {'facut': 'derulare', 'ecran': self.__class__.__name__}
		if fel == 'text':
			return self._textMouse(text)
		return None

	def _textMouse(self, text):
		"""Semnele scrise la tastatura paginii web (Ecranul receptorului) cu sursa aleasa: cautarea, ca literele
		tastaturii puse in receptor („\\b” sterge o litera). In buchet sau intr-o mutare le face MouseEcran (None)."""
		if self.lucru or self.mana is not None or self.focus != L.SURSA or self.mod not in (L.RASFOIRE, L.SELECTEAZA):
			return None
		semne = 0
		for ch in (text or u'')[:64]:
			if ch == u'\b':
				if self.inAsteptare:
					self.sms.nextKey()
					self.inAsteptare = ''
				else:
					self.cautareText = self.cautareText[:-1]
				semne += 1
			elif ch >= u' ' and ch.isprintable():
				if self.sursaFel != 'cautare':
					self.sursaFel = 'cautare'
					self.sursaDosar = None
					self.cautareText = ''
				self.sms.nextKey()
				self.cautareText += self.inAsteptare + ch
				self.inAsteptare = ''
				semne += 1
		if not semne:
			return None
		self._incepeScrisul()
		self._cautareSchimbata()
		return {'facut': 'text', 'ecran': self.__class__.__name__, 'semne': semne}

	def _rez(self, facut, col=None, rand=None):
		rez = {'facut': facut, 'ecran': self.__class__.__name__}
		if col is not None:
			rez['lista'] = self._numeLista(col)
			rez['rand'] = rand
		return rez

	def _clicMouse(self, x, y, clicuri, mod=None):
		sub = self._listaSub(x, y)
		if sub is None:
			return None
		col, i, bara, _g2 = sub
		if bara:
			return None   # bara de derulare: MouseEcran
		if self.mana is not None:
			if col == L.BUCHET and i is not None:
				m = self.mana
				copie = m['copie'] or m['din'] != m['tinta']
				m['la'] = max(0, min(i, L.maxim_loc(len(self.baza), len(m['randuri']), copie)))
				self._arataMana()
				if clicuri >= 2:
					self._lasa()
			return self._rez('selectie', col, i)
		if i is None:
			return self._rez('nimic', col)
		if col != self.focus:
			self._schimbaColoana(col)
		lista = self[self._numeLista(col)]
		if mod is not None:
			ctrl, shift = 'ctrl' in mod, 'shift' in mod
		else:
			ctrl, shift = self.modif.are_ctrl, self.modif.are_shift
		self.modif.consuma()
		if ctrl:
			lista.moveToIndex(i)
			if self.mod != L.SELECTEAZA:
				self.mod = L.SELECTEAZA
			self._comutaBifa(col, i)
			self._invalideaza(col)
			self._arata()
			return self._rez('bifa', col, i)
		if shift:
			chei = self._chei(col)
			ancora = self.bife[col].ancora
			ia = chei.index(ancora) if ancora in chei else self._index_curent(col)
			self.bife[col].interval([k if self._bifabil(r) else None for k, r in zip(chei, self.randuri[col])], ia, i)
			self.bife[col].chei.discard(None)
			self.mod = L.SELECTEAZA
			lista.moveToIndex(i)
			self._invalideaza(col)
			self._arata()
			return self._rez('bifa', col, i)
		lista.moveToIndex(i)
		if clicuri >= 2:
			self.keyOk()
			return self._rez('ok', col, i)
		self._mesaj = None
		self._arata()
		return self._rez('selectie', col, i)

	def _trasMouse(self, x, y, x0, y0, nou):
		if nou or self._tras is None:
			self._tras = None
			if self.mana is not None:
				return None
			sub = self._listaSub(x0, y0)
			if sub is None:
				return None
			col, i, bara, _g2 = sub
			if bara or i is None:
				return None   # bara de derulare: MouseEcran
			r = self.randuri[col][i]
			if col == L.SURSA:
				if r[0] != 'canal' or self._laRadacina():
					self._tras = ('nimic',)
					return self._rez('nimic', col, i)
				cheie = self._cheieRand(r)
				randuri = [rr for rr in self.randuri[L.SURSA] if self._cheieRand(rr) in self.bife[L.SURSA]] \
					if cheie in self.bife[L.SURSA] else [r]
				self._ia(copie=True, randuri_sursa=randuri)
			else:
				if not self._bifabil(r) and r[0] != 'buchet':
					pass
				if i not in self.bife[L.BUCHET]:
					self.bife[L.BUCHET].goleste()
				if col != self.focus:
					self._schimbaColoana(col)
				self['buchet'].moveToIndex(i)
				self._ia(copie=False)
			self._tras = ('mana',)
		if self._tras[0] != 'mana' or self.mana is None:
			return self._rez('nimic')
		sub = self._listaSub(x, y)
		if sub is not None and sub[0] == L.BUCHET:
			col, i, bara, (ly, lh) = sub
			m = self.mana
			copie = m['copie'] or m['din'] != m['tinta']
			inst = self['buchet'].instance
			sus = inst.getTopIndex()
			pagina = max(1, lh // max(1, self.inaltimeRand))
			rand = sus + max(0, (y - ly)) // max(1, self.inaltimeRand)
			# langa marginea de sus / de jos lista deruleaza (blocul merge mai departe)
			if (y - ly) < self.inaltimeRand * MARGINE_TRAS:
				rand = sus - 1
			elif (ly + lh - y) < self.inaltimeRand * MARGINE_TRAS:
				rand = sus + pagina
			m['la'] = max(0, min(rand, L.maxim_loc(len(self.baza), len(m['randuri']), copie)))
			self._arataMana()
		return self._rez('tras', L.BUCHET, self.mana['la'] if self.mana else None)

	def _trasGata(self, x, y):
		tras, self._tras = self._tras, None
		if tras is None:
			return None
		if tras[0] != 'mana' or self.mana is None:
			return self._rez('nimic')
		sub = self._listaSub(x, y)
		if sub is not None and sub[0] == L.BUCHET:
			self._lasa()
			return self._rez('lasat', L.BUCHET)
		self._puneInapoi()
		return self._rez('pus_inapoi')

	def _rotitaMouse(self, x, y, pasi):
		sub = self._listaSub(x, y)
		if sub is None or not pasi:
			return None
		col = sub[0]
		if self.mana is not None:
			if col == L.BUCHET:
				self._mutaCursor(1 if pasi > 0 else -1, abs(pasi) >= 3)
			return self._rez('derulare', col)
		if col != self.focus:
			self._schimbaColoana(col)
		self._mutaCursor(1 if pasi > 0 else -1, abs(pasi) >= 3)
		return self._rez('derulare', col, self._index_curent(col))
