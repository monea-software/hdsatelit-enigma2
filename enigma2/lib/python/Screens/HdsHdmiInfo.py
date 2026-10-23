# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranul „Informații HDMI" (MENU > Informații Sistem > Informații HDMI). Doar in imaginea HDSatelit.

Trei coloane pe intelesul oricui (iesirea, culoarea si imaginea decodata; legatura, protectia la copiere si
sunetul; televizorul) si o pagina pentru cunoscatori cu textul brut al driverului (tasta albastra; Stanga/Dreapta
schimba fisierul). Datele si textele sunt in Components/HdsHdmiDate.py, testate pe PC cu starea reala a
receptorului. Un singur eTimer (o bataie pe secunda): la doua batai se reciteste starea, la fiecare se scrie
varsta ei in randul de jos; se opreste la inchidere.
Coloanele se deruleaza pe pagini (Sus, Jos, CH+, CH-): randurile incep cu randul insusi, nu cu None, pentru ca eListbox
muta pagina numai pe randuri selectabile (ca in Screens/Information.py); valorile prea lungi se rup pe mai multe randuri
(HdsInformatiiTabel.rupt) in loc sa fie scurtate.
"""
import time

from enigma import eListboxPythonMultiContent, eTimer, getDesktop, RT_HALIGN_LEFT, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.ScrollLabel import ScrollLabel
from Components import HdsHdmiDate as D

BATAIE_MS = 1000
CITIRE_LA = 2            # batai intre doua citiri (2 s)

# culorile din skinul HDSatelit si rezerva pentru un alt skin (0xRRGGBB, opac)
CULORI = {
	'titlu': ('hdsBrandLight', 0x9FB4FF),
	'linie': ('hdsTrack', 0x2A3350),
	'eticheta': ('hdsLabel', 0xAEB9CC),
	D.NORMAL: ('hdsText', 0xF2F4F8),
	D.BUN: ('hdsGood', 0x4FD18B),
	D.ATENTIE: ('hdsAmber', 0xF5B83D),
	D.RAU: ('hdsBad', 0xFF6B5E),
	D.STINS: ('hdsDisabled', 0x667085),
}


def _jurnal(text):
	print('[HdsHdmiInfo] %s' % text)


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
	"""(gFont, inaltimea randului) din aliasul skinului (<alias name="HdsHdmi..."/>), altfel rezerva scalata."""
	try:
		import skin
		if alias in skin.fonts:
			v = skin.fonts[alias]
			return skin.parseFont(alias, ((1, 1), (1, 1))), v[2] or inaltime
	except Exception:
		pass
	# fara alias (alt skin): fontul pus din cod, cu Marimea textului si fontul HD Satelit (Components/HdsMarireText)
	f = _factor()
	from Components import HdsMarireText as MT
	return MT.fontCod(nume, int(marime * f)), MT.inaltimeCod(int(inaltime * f))


class HdsHdmiInfo(Screen, HelpableScreen):
	# rezerva pentru un skin fara acest ecran (skinul HDSatelit il are, cu aliasurile de fonturi HdsHdmi*)
	skin = """
	<screen name="HdsHdmiInfo" position="center,center" size="1240,690" title="Informații HDMI">
		<widget name="coloana1" position="10,10" size="393,612" itemHeight="34" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
		<widget name="coloana2" position="423,10" size="393,612" itemHeight="34" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
		<widget name="coloana3" position="836,10" size="393,612" itemHeight="34" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
		<widget name="brut" position="10,10" size="1220,612" font="Regular;18" zPosition="3" />
		<widget name="actualizat" position="10,624" size="1220,26" font="Regular;18" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget name="key_red" position="10,654" size="300,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_blue" position="930,654" size="300,30" font="Regular;19" backgroundColor="#003D7BE0" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, radacina='/'):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.setTitle(D.TITLU)
		self.radacina = radacina       # alt dosar doar la probe (emulatorul nu are /proc/msp)
		self.stare = None
		self.ultimaCitire = None       # time.monotonic() la ultima citire care a gasit ceva
		self.bataie = 0
		self.randuri = [None, None, None]
		self.latimi = [0, 0, 0]
		self.perPagina = 0
		self.brutVizibil = False
		self.paginaBruta = 0
		self.numarPagini = 0
		self.textBrut = None

		for i in (1, 2, 3):
			self['coloana%d' % i] = MenuList([], content=eListboxPythonMultiContent)
		self['brut'] = ScrollLabel('')
		self['actualizat'] = Label('')
		self['key_red'] = Label('Închide')
		self['key_blue'] = Label('Text brut')

		self['actiuni'] = HelpableActionMap(self, 'OkCancelActions', {
			'ok': (self.close, 'Închide'),
			'cancel': (self.close, 'Închide'),
		}, -1)
		self['culori'] = HelpableActionMap(self, 'ColorActions', {
			'red': (self.close, 'Închide'),
			'blue': (self.keyAlbastru, 'Textul brut al driverului sau rezumatul'),
		}, -1)
		self['directii'] = HelpableActionMap(self, 'DirectionActions', {
			'up': (self.keySus, 'Pagina de sus'),
			'down': (self.keyJos, 'Pagina de jos'),
			'left': (self.keyStanga, 'Fișierul anterior (text brut)'),
			'right': (self.keyDreapta, 'Fișierul următor (text brut)'),
			'upRepeated': self.keySus,
			'downRepeated': self.keyJos,
			'leftRepeated': self._nimic,         # tinuta apasat, Stanga/Dreapta nu sar peste fisiere
			'rightRepeated': self._nimic,
			# ridicarea tastei: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action"
			'upUp': self._nimic,
			'downUp': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
		}, -1)
		# CH+ si CH- (si |<< >>|) dau pagina: contextul listei de canale, ca in Screens/Information.py; tastele colorate
		# din el merg la aceleasi functii (altfel jurnalul scrie "unknown action")
		self['pagini'] = ActionMap(['ChannelSelectBaseActions'], {
			'nextBouquet': self.keySus,
			'prevBouquet': self.keyJos,
			'prevMarker': self.keySus,
			'nextMarker': self.keyJos,
			'showAllServices': self.close,
			'showSatellites': self._nimic,
			'showProviders': self._nimic,
			'showFavourites': self.keyAlbastru,
		}, -1)
		# PAGE+ si PAGE-, HOME si END ajungeau numai la listele din C++
		# (ListboxActions, context nativ): mutau numai prima coloana vazuta, iar randul de jos ramanea pe pagina veche.
		# Prinse aici, cu contextul Python HdsPaginiActions (data/keymap.xml), ca Screens/Information.py.
		self['listaTaste'] = ActionMap(['HdsPaginiActions'], {
			'pageUp': self.keySus,
			'pageDown': self.keyJos,
			'moveTop': self.keyInceput,
			'moveEnd': self.keySfarsit,
		}, -1)

		self.timer = eTimer()
		self.timer.callback.append(self._bate)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ pregatire si oprire

	def _pregateste(self):
		self.fontTitlu, self.inaltime = _font('HdsHdmiTitlu', 'Regular', 28, 42)
		self.fontEticheta, _h = _font('HdsHdmiEticheta', 'Regular', 26, 42)
		self.fontValoare, _h = _font('HdsHdmiValoare', 'Regular', 28, 42)
		# fontul si marimea de acum, pentru masurarea textelor (HdsInformatiiTabel.scurtat, ca in Screens/Information.py)
		self.masura = {}
		for i, (g, nume, marime) in enumerate(((self.fontTitlu, 'HdsBold', 28), (self.fontEticheta, 'HdsCond', 26),
				(self.fontValoare, 'HdsCond', 28))):
			try:
				self.masura[i] = (g.family, int(g.pointSize))
			except Exception:
				self.masura[i] = (nume, int(marime * _factor() * 1.3))
		self.c = dict((k, _culoare(k)) for k in CULORI)
		for i in range(3):
			lista = self['coloana%d' % (i + 1)]
			lista.l.setFont(0, self.fontTitlu)
			lista.l.setFont(1, self.fontEticheta)
			lista.l.setFont(2, self.fontValoare)
			lista.l.setItemHeight(self.inaltime)
			lista.selectionEnabled(False)
			try:
				self.latimi[i] = lista.instance.size().width()
			except Exception:
				self.latimi[i] = int(544 * _factor())
		# randurile unei pagini: inaltimea listei / inaltimea randului (atatea muta eListbox la o pagina)
		try:
			self.perPagina = max(1, self['coloana1'].instance.size().height() // self.inaltime)
		except Exception:
			self.perPagina = max(1, int(918 * _factor()) // self.inaltime)
		self['brut'].hide()
		self._citeste()
		self.timer.start(BATAIE_MS, False)

	def _laInchidere(self):
		self.timer.stop()
		try:
			self.timer.callback.remove(self._bate)
		except ValueError:
			pass

	# ------------------------------------------------------------ citirea, o data la 2 s

	def _bate(self):
		self.bataie += 1
		if self.bataie % CITIRE_LA == 0:
			self._citeste()
		else:
			self._arataVarsta()

	def _citeste(self):
		try:
			s = D.citeste(self.radacina, anterior=self.stare, brut=self.brutVizibil)
		except Exception as e:           # citeste() nu arunca; paza in plus, ecranul nu cade
			_jurnal('citire: %s' % e)
			s = None
		if s is not None and s.gasit:
			self.stare = s
			self.ultimaCitire = time.monotonic()
		elif self.stare is None:
			self.stare = s if s is not None else D.Stare()
		# altfel raman datele bune de data trecuta, iar randul de jos arata cat de vechi sunt
		self._deseneaza()
		self._arataVarsta()

	def _ales(self):
		"""modul ales in Setari > Video (config.av.hds_videomode din Components/VideoOutput.py), daca exista"""
		try:
			from Components.config import config
			el = config.av.content.items.get('hds_videomode')
			return el.value if el is not None else None
		except Exception:
			return None

	def _arataVarsta(self):
		varsta = None if self.ultimaCitire is None else time.monotonic() - self.ultimaCitire
		text = D.text_actualizat(varsta, CITIRE_LA * BATAIE_MS / 1000.0)
		if self.brutVizibil and self.numarPagini > 1:
			text = 'Stânga/Dreapta: alt fișier · Sus/Jos: derulare · ' + text
		elif not self.brutVizibil:
			pagina, pagini = self._pagina()
			if pagini > 1:
				text = 'Sus, Jos, CH+ și CH-: altă pagină (pagina %d din %d) · %s' % (pagina, pagini, text)
		self['actualizat'].setText(text)

	def _pagina(self):
		"""(pagina, pagini) a coloanelor: Sus si Jos muta cursorul listelor cu cate o pagina intreaga, deci pagina e
		cursorul / randurile unei pagini, pe coloana cea mai lunga."""
		n = max(1, self.perPagina)
		pagina, pagini = 1, 1
		for i in range(3):
			randuri = len(self.randuri[i] or [])
			pagini = max(pagini, (randuri + n - 1) // n)
			try:
				pagina = max(pagina, (self['coloana%d' % (i + 1)].getSelectionIndex() or 0) // n + 1)
			except Exception:
				pass
		return min(pagina, pagini), pagini

	# ------------------------------------------------------------ desenul

	def _deseneaza(self):
		try:
			coloane = D.coloane(self.stare, self._ales())
		except Exception as e:
			_jurnal('coloane: %s' % e)
			return
		for i in range(3):
			col = self._incapute(coloane[i] if i < len(coloane) else [], self.latimi[i])
			if col == self.randuri[i]:
				continue                   # nimic schimbat: lista nu se redeseneaza
			self.randuri[i] = col
			lista = self['coloana%d' % (i + 1)]
			try:
				idx = lista.getSelectionIndex() or 0
			except Exception:
				idx = 0
			lista.setList([self._intrare(r, self.latimi[i]) for r in col])
			if idx and col:
				lista.moveToIndex(min(idx, len(col) - 1))
		if self.brutVizibil:
			self._deseneazaBrut()

	def _incapute(self, col, w):
		"""Coloana cu textele prea lungi rupte pe mai multe randuri: eticheta si valoarea continua fiecare sub ea (sub cea
		mai scurta locul ramane gol), un titlu continua pe randul urmator (linia ramane sub ultimul rand); fiecare text
		cu masurile fontului lui (0 titlu, 1 eticheta, 2 valoare), ca in _intrare."""
		from Components import HdsInformatiiTabel as T
		if w <= 0:
			return col
		masura = getattr(self, 'masura', {})
		nume, marime = masura.get(2, ('HdsCond', 36))
		le = int(w * 0.44)
		rez = []
		for r in col:
			if r[0] == 'titlu':
				if len(r) == 2 and r[1]:
					rez.extend(T.rupt_titlu('titlu', r[1], w, masura.get(0, ('HdsCond', 36))))
				else:
					rez.append(r)
				continue
			if len(r) < 4:
				rez.append(r)
				continue
			tip, eticheta, valoare, ton = r
			for e, v in T.rupt_pereche(eticheta, valoare, le - 8, w - le, masura.get(1, ('HdsCond', 36)), (nume, marime)):
				rez.append((tip, e, v, ton))
		return rez

	def _intrare(self, r, w):
		# primul element e randul insusi, nu None: eListbox muta pagina numai pe randuri selectabile; selectia nu se
		# vede (selectionEnabled(False))
		c = self.c
		h = self.inaltime
		if r[0] == 'titlu':
			linie = max(2, h // 20)
			return [r,
				MultiContentEntryText(pos=(0, 0), size=(w, h - linie), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
					text=self._s(r[1], w, 0), color=c['titlu'], color_sel=c['titlu']),
				MultiContentEntryText(pos=(0, h - 2 * linie), size=(w, linie), font=0, text='',
					backcolor=c['linie'], backcolor_sel=c['linie']),
			]
		if r[0] == 'titlu_sus':
			# randurile de deasupra ale unui titlu rupt (_incapute), fara linia de sub titlu
			return [r, MultiContentEntryText(pos=(0, 0), size=(w, h), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=r[1], color=c['titlu'], color_sel=c['titlu'])]
		_tip, eticheta, valoare, ton = r
		le = int(w * 0.44)
		culoare = c.get(ton, c[D.NORMAL])
		return [r,
			MultiContentEntryText(pos=(0, 0), size=(le - 8, h), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=self._s(eticheta, le - 8, 1), color=c['eticheta'], color_sel=c['eticheta']),
			MultiContentEntryText(pos=(le, 0), size=(w - le, h), font=2, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=self._s(valoare, w - le, 2), color=culoare, color_sel=culoare),
		]

	def _s(self, text, latime, font):
		"""Textul unei celule, intreg: titlurile, etichetele si valorile prea lungi sunt rupte pe mai multe randuri de
		_incapute, deci nu mai e nimic de scurtat cu "..."."""
		return text

	def _deseneazaBrut(self, sus=False):
		pagini = D.pagini_brute(self.stare) if self.stare is not None else []
		self.numarPagini = len(pagini)
		if not pagini:
			self.setTitle('%s: text brut' % D.TITLU)
			text = 'Receptorul nu are fișierele driverului HDMI (/proc/msp/hdmi0 și celelalte).'
		else:
			self.paginaBruta %= len(pagini)
			_titlu, cale, text = pagini[self.paginaBruta]
			self.setTitle('%s: %s (%d din %d)' % (D.TITLU, cale, self.paginaBruta + 1, len(pagini)))
		if text == self.textBrut and not sus:
			return
		pagina = 0 if sus else self._paginaBruta()
		self.textBrut = text
		self['brut'].setText(text)
		for _i in range(pagina):
			self['brut'].pageDown()

	def _paginaBruta(self):
		"""pagina la care e derulat textul brut, ca improspatarea sa nu-l duca inapoi sus"""
		try:
			b = self['brut']
			return int(-b.long_text.position().y() // b.pageHeight) if b.pageHeight > 0 else 0
		except Exception:
			return 0

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def keyAlbastru(self):
		self.brutVizibil = not self.brutVizibil
		if self.brutVizibil:
			for i in (1, 2, 3):
				self['coloana%d' % i].hide()
			self['brut'].show()
			self['key_blue'].setText('Pe scurt')
			self.textBrut = None
			self._citeste()                # dosarele /proc/stb intregi, doar cat se vede pagina bruta
			self._deseneazaBrut(sus=True)
		else:
			self['brut'].hide()
			for i in (1, 2, 3):
				self['coloana%d' % i].show()
			self['key_blue'].setText('Text brut')
			self.setTitle(D.TITLU)
			self._arataVarsta()

	def keySus(self):
		if self.brutVizibil:
			self['brut'].pageUp()
		else:
			for i in (1, 2, 3):
				self['coloana%d' % i].pageUp()
			self._arataVarsta()

	def keyJos(self):
		if self.brutVizibil:
			self['brut'].pageDown()
		else:
			for i in (1, 2, 3):
				self['coloana%d' % i].pageDown()
			self._arataVarsta()

	def keyInceput(self):
		"""HOME: prima pagina (toate coloanele, sau textul brut)."""
		if self.brutVizibil:
			self['brut'].firstPage()
		else:
			for i in (1, 2, 3):
				self['coloana%d' % i].moveToIndex(0)
			self._arataVarsta()

	def keySfarsit(self):
		"""END: ultima pagina; fiecare coloana la ultimul ei rand (pagina e a celei mai lungi)."""
		if self.brutVizibil:
			self['brut'].lastPage()
		else:
			for i in (1, 2, 3):
				randuri = len(self.randuri[i - 1] or [])
				if randuri:
					self['coloana%d' % i].moveToIndex(randuri - 1)
			self._arataVarsta()

	def keyStanga(self):
		self._altFisier(-1)

	def keyDreapta(self):
		self._altFisier(1)

	def _altFisier(self, pas):
		if not self.brutVizibil:
			return
		self.paginaBruta += pas
		self._deseneazaBrut(sus=True)
		self._arataVarsta()
