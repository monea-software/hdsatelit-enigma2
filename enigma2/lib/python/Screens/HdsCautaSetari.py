# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""„Caută setări” pe televizor (MENU > Setări > Caută setări, sau tasta TEXT in orice meniu): cautarea in tot meniul
receptorului, ca la telefoanele Android. Doar in imaginea HDSatelit.

Ecranul: randul de cautare (tastele 0-9 ca la SMS, 0 = spatiu; tastatura de pe ecran cu TEXT sau Verde; tastatura USB),
numarul rezultatelor si lista lor: titlul (cu semnul starii, ca in meniu), valoarea de acum la setarile simple si,
dedesubt, drumul din meniu („Setări › Sunet și subtitrări”); sub lista, descrierea randului ales. Sus/Jos alegi,
Stanga/Dreapta trec cate o pagina, OK deschide ecranul cu cursorul pe randul gasit (Components/HdsCautaSetari.deschide);
EXIT inchide ecranul, MENU inchide si meniurile de sub el. La intoarcerea dintr-un ecran deschis de aici rezultatele raman,
cu valorile citite din nou. Rezultatele vin pe masura ce scrii (cautarea cel mult o data la AMANARE_MS: o litera noua o
amana pe cea care astepta). Ultimul text cautat ramane pana la repornirea interfetei.
Indexul, regulile si deschiderea sunt in Components/HdsCautaSetari.py (aceleasi si pentru pagina web /cauta-setari).
Lista de rezultate nu e transparenta (ca la cautarea de canale): pe receptor un element transparent redesenat la fiecare
litera face clipire neagra.
"""
from enigma import eListboxPythonMultiContent, eTimer, eRCInput, getPrevAsciiCode, getDesktop, gFont, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.Button import Button
from Components.Label import Label
from Components.HdsCampText import CampText
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components import HdsCautaSetari as C
from Tools.BoundFunction import boundFunction
from Tools.NumericalTextInput import NumericalTextInput

TITLU = 'Caută setări'
AMANARE_MS = 150           # cautarea dupa text, cel mult o data in atat; 0 = pe loc (probele de pe PC)
# cifrele ca la telefon: 0 scrie intai un spatiu (cuvintele se cauta fiecare), apoi cifra; 1 scrie cifra
LITERE_SMS = (' 0', '1', 'abc2', 'def3', 'ghi4', 'jkl5', 'mno6', 'pqrs7', 'tuv8', 'wxyz9')

# culorile din skinul HDSatelit si rezerva pentru un alt skin (0xRRGGBB)
CULORI = {
	'text': ('hdsText', 0xF2F4F8),
	'drum': ('hdsLabel', 0xAEB9CC),
	'valoare': ('hdsBrandLight', 0x9FB4FF),
	'alb': ('white', 0xFFFFFF),
	'alb2': ('hdsText2', 0xC9D2E3),
}

_memorie = {'text': ''}    # ultimul text cautat, cat merge interfata


def _jurnal(text):
	print('[HdsCautaSetari] %s' % text)


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
	"""(gFont, inaltimea randului) din aliasul skinului (<alias name="HdsCautaSetari..."/>), altfel rezerva scalata dupa
	latimea ecranului. Marimea textului (config.osd.fontscale, skin._hds_scaleaza) se aplica si randului, ca la
	skin.getListFont: cu fontul marit si randul de 88 px, titlul si drumul din meniu se taiau jos de la 115 %."""
	try:
		import skin
		scaleaza = getattr(skin, "_hds_scaleaza", int)
		if alias in skin.fonts:
			_n, _m, h = skin.fonts[alias]
			return skin.parseFont(alias, ((1, 1), (1, 1))), scaleaza(h or inaltime)
	except Exception:
		scaleaza = int
	f = _factor()
	return gFont(nume, scaleaza(int(marime * f))), scaleaza(int(inaltime * f))


class HdsCautaSetari(Screen, HelpableScreen):
	# rezerva pentru un skin fara acest ecran (skinul HDSatelit il are, cu aliasurile HdsCautaSetari*)
	skin = """
	<screen name="HdsCautaSetari" position="center,center" size="1200,660" title="Caută setări">
		<widget name="cautare" position="10,10" size="1180,44" font="Regular;28" backgroundColor="#002A3350" valign="center" noWrap="1" zPosition="2" />
		<widget name="indiciu" position="10,58" size="880,30" font="Regular;19" foregroundColor="#00AEB9CC" valign="center" noWrap="1" zPosition="2" />
		<widget name="numar" position="890,58" size="300,30" font="Regular;22" foregroundColor="#00F5B83D" halign="right" valign="center" noWrap="1" zPosition="2" />
		<eLabel position="10,92" size="1180,1" backgroundColor="#00AEB9CC" zPosition="1" />
		<widget name="rezultate" position="10,96" size="1180,448" itemHeight="64" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" zPosition="2" />
		<widget name="gol" position="10,150" size="1180,80" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="descriere" position="10,550" size="1180,66" font="Regular;19" foregroundColor="#00C9D2E3" zPosition="2" />
		<widget name="key_red" position="10,624" size="290,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="306,624" size="290,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="602,624" size="290,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, text=None):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.setTitle(_(TITLU))
		self.index = None
		self.text = (_memorie['text'] if text is None else text)[:C.MAX_TEXT]
		# textul cautarii de data trecuta se vede, cu rezultatele lui, dar prima litera scrisa incepe o cautare noua
		# (nu se adauga la el); Galben sau tastatura de pe ecran il pastreaza, ca sa poata fi schimbat
		self.vechi = text is None and bool(self.text)
		self.inAsteptare = ''      # litera SMS inca neconfirmata (se mai poate schimba cu aceeasi tasta)
		self.rezultate = []
		self.cautat = None         # textul pentru care sunt rezultatele de pe ecran
		self.inchis = False
		self.deschis = False       # a trecut prima pornire (onExecBegin); dupa ea, intoarcerea dintr-un ecran
		self.modTastatura = None
		self.ceasText = None
		self.sms = NumericalTextInput(nextFunc=self._literaConfirmata)
		self.sms.mapping = list(LITERE_SMS)
		self.c = dict((k, _culoare(k)) for k in CULORI)
		self.latime = int(1712 * _factor())
		self.inaltime = int(88 * _factor())

		# randul de cautare: cand textul nu mai incape, se vede coada lui, ce scrii acum (Components/HdsCampText.py)
		self['cautare'] = CampText('')
		self['indiciu'] = Label(_('0-9 scrii ca la SMS (0 e spațiul) · TEXT sau Verde: tastatura · OK deschide'))
		self['numar'] = Label('')
		self['rezultate'] = MenuList([], content=eListboxPythonMultiContent)
		self['rezultate'].onSelectionChanged.append(self._laSelectie)
		self['gol'] = Label('')
		self['descriere'] = Label('')
		self['key_red'] = Button(_('Șterge tot'))
		self['key_green'] = Button(_('Tastatură'))
		self['key_yellow'] = Button(_('Șterge litera'))

		# textele de ajutor (tasta HELP) sunt scurte: lista de ajutor a imaginii taie randurile lungi
		self['actiuni'] = HelpableActionMap(self, 'OkCancelActions', {
			'ok': (self.keyOk, _('Deschide setarea aleasă')),
			'cancel': (self.keyCancel, _('Înapoi')),
		}, -1)
		self['directii'] = HelpableActionMap(self, 'DirectionActions', {
			'up': (self.keyUp, _('Rezultatul de sus')),
			'down': (self.keyDown, _('Rezultatul de jos')),
			'left': (self.keyLeft, _('Pagina de sus')),
			'right': (self.keyRight, _('Pagina de jos')),
			'upRepeated': self.keyUp,
			'downRepeated': self.keyDown,
			'leftRepeated': self.keyLeft,
			'rightRepeated': self.keyRight,
			# ridicarea tastei: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action"
			'upUp': self._nimic,
			'downUp': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
		}, -1)
		self['culori'] = HelpableActionMap(self, 'ColorActions', {
			'red': (self.keyStergeTot, _('Șterge tot textul')),
			'green': (self.keyTastatura, _('Tastatura de pe ecran')),
			'yellow': (self.keyStergeLitera, _('Șterge ultima literă')),
		}, -1)
		cifre = dict((str(i), boundFunction(self.keyCifra, i)) for i in range(10))
		cifre['2'] = (boundFunction(self.keyCifra, 2), _('Numele setării, cu tastele 0-9'))
		self['cifre'] = HelpableActionMap(self, 'NumberActions', cifre, -1)
		self['text'] = HelpableActionMap(self, 'HdsCautareActions', {
			'cautare': (self.keyTastatura, _('Tastatura de pe ecran')),
		}, -1)
		self['ascii'] = ActionMap(['InputAsciiActions'], {'gotAsciiCode': self.keyAscii}, -1)
		# Backspace de pe o tastatura USB sterge ultima litera (data/keymap.xml; consola nu trimite caracterul lui)
		self['sterge'] = ActionMap(['HdsTastaturaStergeActions'], {'deleteBackward': self.keyStergeLitera}, -1)
		self['meniu'] = HelpableActionMap(self, 'MenuActions', {
			'menu': (self.keyMeniu, _('Închide și meniul')),
		}, -1)

		self.onLayoutFinish.append(self._pregateste)
		self.onExecBegin.append(self._laIntoarcere)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ indexul si lista

	def _pregateste(self):
		fontTitlu, self.inaltime = _font('HdsCautaSetariTitlu', 'Regular', 32, 88)
		fontMic, _h = _font('HdsCautaSetariMic', 'Regular', 26, 88)
		r = self['rezultate']
		r.l.setFont(0, fontTitlu)
		r.l.setFont(1, fontMic)
		r.l.setItemHeight(self.inaltime)
		try:
			import skin
			if skin.getFontScalePercent() > 100 and r.instance is not None:
				# cu randul marit, lista din skin se scurteaza la randuri intregi (ultimul se vedea taiat pe jumatate)
				from Components.HdsMarireText import randuriIntregi
				randuriIntregi(r.instance, self.inaltime)
		except Exception as e:
			_jurnal('randurile intregi: %s' % e)
		r.l.setBuildFunc(self._rand)
		try:
			self.latime = r.instance.size().width()
		except Exception:
			pass
		try:
			self.index = C.index()
		except Exception as e:
			_jurnal('indexul: %s' % e)
			self.index = C.Index([])
		self._arataText()
		self._cauta()

	def _textCautat(self):
		return self.text + self.inAsteptare

	def _cauta(self):
		"""Rezultatele pentru textul de acum; lista se reface numai cand s-au schimbat."""
		if self.index is None or self.inchis:
			return
		text = self._textCautat()
		rezultate = self.index.cauta(text)
		if rezultate != self.rezultate or text.strip() != (self.cautat or '').strip():
			self.rezultate = rezultate
			self['rezultate'].setList([(i,) for i in rezultate])
			if rezultate:
				self['rezultate'].moveToIndex(0)
		self.cautat = text
		self['numar'].setText(_('Rezultate: %d') % len(rezultate) if text.strip() else '')
		if not text.strip():
			self['gol'].setText(_('Scrie câteva litere din numele setării.'))
			self['gol'].show()
		elif not rezultate:
			self['gol'].setText(_('Nicio setare nu se potrivește. Galben șterge o literă.'))
			self['gol'].show()
		else:
			self['gol'].setText('')
			self['gol'].hide()
		self._laSelectie()

	def _cautaAmanat(self):
		"""Textul s-a schimbat: randul de cautare se scrie pe loc, cautarea cel mult o data in AMANARE_MS."""
		self._arataText()
		if not AMANARE_MS:
			self._cauta()
			return
		if self.ceasText is None:
			self.ceasText = eTimer()
			self.ceasText.callback.append(self._cauta)
		self.ceasText.start(AMANARE_MS, True)

	def _arataText(self):
		self['cautare'].setText('  ' + self._textCautat() + ('' if self.vechi else '_'))

	def _incepeNou(self):
		"""Prima litera scrisa peste textul de data trecuta: textul vechi pleaca."""
		if self.vechi:
			self.vechi = False
			self.text, self.inAsteptare = '', ''

	def _curenta(self):
		cur = self['rezultate'].getCurrent()
		if not cur or not self.rezultate:
			return None
		return cur[0]

	def _laSelectie(self):
		i = self._curenta()
		self['descriere'].setText(i.ajutor if i is not None and i.ajutor else '')

	def _rand(self, intrare):
		c = self.c
		w, h = self.latime, self.inaltime
		f = w / 1712.0
		x = int(16 * f)
		dreapta = w - int(56 * f)          # la dreapta ramane loc pentru bara de derulare
		sus = int(h * 0.55)
		val = C.valoare(intrare)
		latVal = int(520 * f) if val else 0
		e = [None,
			MultiContentEntryText(pos=(x, 0), size=(dreapta - x - latVal - int(16 * f), sus), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=intrare.titlu, color=c['text'], color_sel=c['alb']),
			MultiContentEntryText(pos=(x, sus), size=(dreapta - x, h - sus - int(6 * f)), font=1,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=intrare.drumText(_), color=c['drum'], color_sel=c['alb2'])]
		if val:
			e.append(MultiContentEntryText(pos=(dreapta - latVal, 0), size=(latVal, sus), font=1,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=val, color=c['valoare'], color_sel=c['alb']))
		return e

	# ------------------------------------------------------------ deschiderea

	def keyOk(self):
		self.sms.nextKey()
		self.text += self.inAsteptare
		self.inAsteptare = ''
		intrare = self._curenta()
		if intrare is None:
			self.keyTastatura()
			return
		_memorie['text'] = self.text
		try:
			C.deschide(self.session, intrare, laInchidere=self._dupaEcran)
		except Exception as e:
			_jurnal('deschiderea %s: %s' % (intrare.cheie, e))

	def _dupaEcran(self, *rezultat):
		"""Ecranul deschis de aici s-a inchis: cu MENU (rezultat True) se inchide si cautarea, ca un meniu."""
		if rezultat and rezultat[0]:
			self.close(True)

	def _laIntoarcere(self):
		self._modAscii()
		if not self.deschis:
			self.deschis = True        # prima pornire: lista e abia facuta (_pregateste)
			return
		if self.rezultate and self.index is not None:
			# valorile se citesc din nou (setarea s-a putut schimba in ecranul deschis); cursorul ramane pe loc
			i = self['rezultate'].getSelectionIndex()
			self['rezultate'].setList([(x,) for x in self.rezultate])
			self['rezultate'].moveToIndex(i)
			self._laSelectie()

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
		if self.ceasText is not None:
			self.ceasText.stop()
		self.sms.nextKey()
		_memorie['text'] = (self.text + self.inAsteptare)[:C.MAX_TEXT]
		try:
			if self.modTastatura is not None:
				eRCInput.getInstance().setKeyboardMode(self.modTastatura)
		except Exception:
			pass

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def keyCancel(self):
		self.close(False)

	def keyMeniu(self):
		self.close(True)

	def keyUp(self):
		if self.rezultate:
			self['rezultate'].up()

	def keyDown(self):
		if self.rezultate:
			self['rezultate'].down()

	def keyLeft(self):
		if self.rezultate:
			self['rezultate'].pageUp()

	def keyRight(self):
		if self.rezultate:
			self['rezultate'].pageDown()

	def keyStergeTot(self):
		self.vechi = False
		self.sms.nextKey()
		self.text, self.inAsteptare = '', ''
		_memorie['text'] = ''
		self._cautaAmanat()

	def keyStergeLitera(self):
		self.vechi = False
		if self.inAsteptare:
			self.sms.nextKey()
			self.inAsteptare = ''
		elif self.text:
			self.text = self.text[:-1]
		else:
			return 1
		self._cautaAmanat()
		return 1

	def keyCifra(self, n):
		self._incepeNou()
		if len(self.text) >= C.MAX_TEXT:
			return
		litera = self.sms.getKey(n)       # alta tasta decat inainte: litera veche se confirma (_literaConfirmata)
		if litera is None:
			return
		self.inAsteptare = litera
		if len(LITERE_SMS[n]) == 1:       # 1: o singura valoare, se confirma pe loc
			self.sms.nextChar()
		self._cautaAmanat()

	def _literaConfirmata(self):
		if self.inAsteptare:
			self.text = (self.text + self.inAsteptare)[:C.MAX_TEXT]
			self.inAsteptare = ''
			self._arataText()

	def keyAscii(self):
		"""O tastatura USB (sau tastatura PC-ului in emulator). Ce nu e litera sau semn (Enter, Esc) nu se consuma (0),
		ca OK si EXIT sa ajunga la harta lor."""
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
		self._incepeNou()
		self.text = (self.text + self.inAsteptare + ch)[:C.MAX_TEXT]
		self.inAsteptare = ''
		self._cautaAmanat()
		return 1

	def keyTastatura(self):
		self.vechi = False
		self.sms.nextKey()
		self.text += self.inAsteptare
		self.inAsteptare = ''
		self.session.openWithCallback(self._dinTastatura, VirtualKeyBoard, title=_(TITLU), text=self.text)

	def _dinTastatura(self, text=None):
		if text is None:
			return
		self.text = text.strip()[:C.MAX_TEXT]
		self.inAsteptare = ''
		self._arataText()
		self._cauta()
