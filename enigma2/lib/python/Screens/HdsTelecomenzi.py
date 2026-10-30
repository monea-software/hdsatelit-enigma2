# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranul „Telecomenzi”: cititorul de coduri, proba tastelor și asocierea altei telecomenzi, buton cu buton.
Doar în imaginea HDSatelit.

Tastele vin din C++ (eRCMapper, lib/driver/rcmapper.h): fiecare tastă, de pe orice dispozitiv, cu numele
dispozitivului, codul, felul și codul Viper în care se traduce. Datele și regulile (fișierul de asocieri, pașii
asocierii, proba) sunt în Components/HdsTelecomenziDate.py, probate pe PC (teste/test_telecomenzi.py).

Modurile:
- pagina de start: lista (cititor, probă, asociere, telecomenzile asociate, ștergerea tuturor);
- cititorul și proba: captura oprește toate tastele (captureAll). Ieșirea o face C++, nu ecranul: EXIT, MENU sau
  ESC de două ori în 2 secunde, pe orice telecomandă, sau orice tastă ținută 3 secunde; plus 30 de secunde fără
  taste și 2 minute în total. Secundele rămase se arată jos;
- asocierea: captura oprește numai celelalte dispozitive; telecomanda receptorului merge normal (ROȘU Înapoi,
  VERDE Gata, GALBEN Sari, EXIT Anulează). Se poate face și numai de pe telecomanda nouă: codul folosit pentru alt
  buton se mută apăsându-l încă o dată, iar o tastă ținută 2 secunde înseamnă Sari. Gata merge după pasul MENU, iar
  tastele neasociate ale unei telecomenzi „se opresc” numai cu OK, săgețile, EXIT și MENU asociate, ca omul să aibă
  mereu drum spre meniu de pe ea; rezumatul spune ce se întâmplă cu ele. Asocierea spune de la început că o
  telecomandă cu infraroșu, alta decât a receptorului, nu se poate asocia încă și arată semnul IR, ca cititorul
 .
Cât e deschis, ecranul pune tastatura în modul kmNone (fără text), ca literele și cifrele unei tastaturi USB să
ajungă la cititor; la închidere pune la loc modul de dinainte și oprește captura. Semnul de viață (touch) se dă la
o secundă: dacă ecranul dispare fără să oprească captura, C++ o oprește singur după 20 de secunde.

Ecranul și pagina web (revizia, P23): captura din C++ e una singură. Ecranul dă semnul de viață, citește tastele și
oprește captura numai dacă a pornit-o el (`captura_mea`); nu pornește nimic cât lucrează pagina web și nu schimbă
asocierile cât asociază ea. Fișierul de asocieri se citește din nou dacă l-a schimbat pagina web.
Proba tastelor se păstrează cât e deschis ecranul și se reia de unde a rămas (revizia, P28).
"""
import builtins
import os
import sys
import time

from enigma import eListboxPythonMultiContent, eRCInput, eRCMapper, eTimer, RT_HALIGN_LEFT, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.Pixmap import Pixmap
from Components.Sources.CanvasSource import CanvasSource
from Components import HdsTelecomenziDate as D
from Components import HdsMarireText as MT
from Tools.Directories import resolveFilename, SCOPE_SKIN_IMAGE
from Tools.LoadPixmap import LoadPixmap

START, CITITOR, PROBA, ASOCIERE, TASTE = 'start', 'cititor', 'proba', 'asociere', 'taste'
RAND_CITITOR, RAND_PROBA, RAND_PROBA_NOUA, RAND_ASOCIERE = 'cititor', 'proba', 'proba-noua', 'asociere'
RAND_STERGE_TOT = 'sterge-tot'
CALE_IR = '/proc/hisi/msp/ir'

TRANSPARENT = 0xFF000000
APRINS = 0x38FFB23C          # chihlimbar, pe jumătate transparent (octetul de sus = transparența, 0 = opac)
CERUT_TARE = 0x20FFB23C
CERUT_SLAB = 0x98FFB23C
VERIFICAT = 0x0035D07A       # semnul verde al butoanelor verificate sau asociate
CONTUR_SEMN = 0x00101318
RAZA_SEMN = 5.0


def _(text):
	"""Traducerea pusă de Components/Language.py în builtins (gettext.install); pe PC, textul neschimbat."""
	f = builtins.__dict__.get('_')
	if f is not None and f is not _:
		try:
			return f(text)
		except Exception:
			pass
	return text


def _jurnal(text):
	print('[HdsTelecomenzi] %s' % text)


def _factorEcran():
	"""(fx, fy, ff): ecranul fata de 1920x1080 (skin.factorHds), (1.0, 1.0, 1.0) pe 1920x1080."""
	try:
		import skin
		return skin.factorHds()
	except Exception:
		return 1.0, 1.0, 1.0


def _fontHds(nume):
	"""Fontul randurilor: al skinului HDSatelit si sub alt skin ales (skin.fontHds), acelasi nume cu HDSatelit ales."""
	try:
		import skin
		return skin.fontHds(nume)
	except Exception:
		return nume


def _ori(v, f):
	"""v (scris pe 1920) pe ecranul de acum, intreg; neschimbat pe 1920x1080."""
	return v if f == 1.0 else max(1, int(round(v * f)))


def _k(v, f):
	"""o coordonata a desenului (cu zecimale) pe ecranul de acum; neschimbata pe 1920x1080."""
	return v if f == 1.0 else v * f


def _pozaScalata(cale, fx, fy):
	"""desenul telecomenzii la marimea lui inmultita cu factorul ecranului (skin.incarcaPixmapScalat), sau None."""
	try:
		import skin
		m = skin.marimeImagine(cale)
		if m:
			return skin.incarcaPixmapScalat(cale, max(1, int(round(m[0] * fx))), max(1, int(round(m[1] * fy))))
	except Exception as e:
		_jurnal('desenul telecomenzii ramane la marimea lui (%s)' % e)
	return None


def _adresa_web():
	"""Adresa paginii /telecomenzi (IP și portul serverului web), sau '' dacă serverul nu merge ori pagina nu există
	încă (revizia, P21). Pluginul web se ia numai dacă e deja încărcat; nu se importă de aici."""
	return D.adresa_pagina_web(sys.modules.get(D.MODUL_WEB))


def _semn_fisier(cale):
	"""(mtime, mărime) al fișierului de asocieri, ca să se vadă când l-a schimbat pagina web; None dacă lipsește."""
	try:
		s = os.stat(cale)
		return (s.st_mtime_ns, s.st_size)
	except OSError:
		return None


def _nume_taste():
	"""{nume: cod} din keyids.py, pentru cititor (numele tastelor care nu sunt pe telecomanda receptorului)."""
	try:
		from keyids import KEYIDS
		return KEYIDS
	except Exception:
		return {}


class HdsTelecomenzi(Screen):
	skin = """
	<screen name="HdsTelecomenzi" resolution="1920,1080" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#00101318" title="Telecomenzi">
		<widget name="titlu" position="400,28" size="1460,64" font="Regular;46" foregroundColor="#00F2F4F8" backgroundColor="#00101318" valign="center" noWrap="1" transparent="1" />
		<widget name="telecomanda" position="80,84" size="256,976" alphatest="blend" zPosition="1" />
		<widget source="aprinse" render="Canvas" position="80,84" size="256,976" alphatest="blend" transparent="1" zPosition="2" />
		<widget name="lista" position="400,110" size="1460,784" itemHeight="56" scrollbarMode="showOnDemand" backgroundColor="#00101318" transparent="1" zPosition="1" />
		<widget name="mare" position="400,104" size="1460,160" font="Regular;60" foregroundColor="#00FFD27A" backgroundColor="#00101318" halign="left" valign="center" transparent="1" zPosition="1" />
		<widget name="detalii" position="400,270" size="1460,300" font="Regular;32" foregroundColor="#00F2F4F8" backgroundColor="#00101318" transparent="1" zPosition="1" />
		<widget name="istoric" position="400,580" size="1460,310" font="Regular;25" foregroundColor="#00AEB9CC" backgroundColor="#00101318" transparent="1" zPosition="1" />
		<widget name="ajutor" position="400,898" size="1460,96" font="Regular;26" foregroundColor="#00F5B83D" backgroundColor="#00101318" valign="center" transparent="1" zPosition="1" />
		<widget name="key_red" position="400,1000" size="345,52" font="Regular;26" foregroundColor="#00FFFFFF" backgroundColor="#00C8363A" halign="center" valign="center" zPosition="1" />
		<widget name="key_green" position="772,1000" size="345,52" font="Regular;26" foregroundColor="#00FFFFFF" backgroundColor="#0019955C" halign="center" valign="center" zPosition="1" />
		<widget name="key_yellow" position="1144,1000" size="345,52" font="Regular;26" foregroundColor="#00202020" backgroundColor="#00E0B820" halign="center" valign="center" zPosition="1" />
		<widget name="key_blue" position="1516,1000" size="345,52" font="Regular;26" foregroundColor="#00FFFFFF" backgroundColor="#002E6FD0" halign="center" valign="center" zPosition="1" />
	</screen>"""

	def __init__(self, session, cale_asocieri=None, cale_desen=None, cale_ir=CALE_IR):
		Screen.__init__(self, session)
		self.setTitle(_('Telecomenzi'))
		self.cale = cale_asocieri or D.CALE_ASOCIERI
		self.cale_desen = cale_desen or resolveFilename(SCOPE_SKIN_IMAGE, 'telecomanda-viper.json')
		self.cale_ir = cale_ir
		self.mapper = eRCMapper.getInstance()
		self.mesaj_fisier = ('', None)   # (șablon, argument): tradus abia când se arată
		self._citeste_fisierul()
		self.semn_fisier = _semn_fisier(self.cale)
		self.desen = D.incarca_desen(self.cale_desen)
		self.keyids = _nume_taste()
		self.mod = START
		self.ultimul = 0            # numărul ultimului eveniment citit din C++
		self.istoric = []
		self.ancora = None
		self.aprinse = set()        # butoanele Viper ținute acum
		self.semne = set()          # butoanele cu semn verde (verificate sau asociate)
		self.cerut = None           # butonul care pulsează la asociere
		self.puls = False
		self.proba = None
		self.asociere = None
		self.inainte_de_asociere = None
		self.contor_ir = None
		self.ir_aratat = 0          # câte semnale IR străine scrie acum cititorul
		self.ev_cititor = None      # ultima tastă arătată în cititor
		self.asteapta_continuare = False
		self.intrebare_proba = False
		self.intrebare_deschisa = False
		self.telecomanda_taste = None
		self.mod_tastatura = None
		self.legat = False
		self.captura_mea = False    # captura din C++ e pornită de ecran (nu de pagina web)
		self.adresa_web = ''

		self['titlu'] = Label(_('Telecomenzi'))
		self['telecomanda'] = Pixmap()
		self['aprinse'] = CanvasSource()
		# skinul e scris pe 1920x1080 (resolution=), deci pe alt ecran skin.py il scaleaza; randurile listei, desenul
		# telecomenzii si semnele de pe el se scaleaza aici cu acelasi factor (1 pe 1920x1080)
		self.fx, self.fy, self.ff = _factorEcran()
		self['lista'] = MenuList([], content=eListboxPythonMultiContent)
		# fontul randurilor e pus din cod: urmeaza Marimea textului (Components/HdsMarireText), iar cu textul marit
		# randul creste odata cu el (la 100 % aceleasi numere)
		self.rand = MT.inaltimeCod(_ori(56, self.fy))
		self['lista'].l.setFont(0, MT.fontCod(_fontHds('Regular'), _ori(32, self.ff)))
		self['lista'].l.setItemHeight(self.rand)
		self['lista'].onSelectionChanged.append(self._selectie)
		self['mare'] = Label('')
		self['detalii'] = Label('')
		self['istoric'] = Label('')
		self['ajutor'] = Label('')
		self['key_red'] = Label('')
		self['key_green'] = Label('')
		self['key_yellow'] = Label('')
		self['key_blue'] = Label('')

		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions'], {
			'ok': self.keyOk,
			'cancel': self.keyExit,
			'red': self.keyRosu,
			'green': self.keyVerde,
			'yellow': self.keyGalben,
			'blue': self.keyAlbastru,
		}, -1)

		self.timer = eTimer()
		self.timer.callback.append(self._bate)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------------ pornire, oprire

	def _pregateste(self):
		# itemHeight din skin (56) ar pune randul inapoi: cu textul marit ramane cel socotit in __init__
		MT.randuriCod(self['lista'], self.rand)
		try:
			cale = self.cale_desen[:-5] + '.png'
			poza = None
			if (self.fx, self.fy) != (1.0, 1.0):
				poza = _pozaScalata(cale, self.fx, self.fy)
			self['telecomanda'].instance.setPixmap(poza or LoadPixmap(cale))
		except Exception as e:
			_jurnal('desenul telecomenzii nu se poate încărca (%s)' % e)
		try:
			ki = eRCInput.getInstance()
			self.mod_tastatura = ki.getKeyboardMode()
			ki.setKeyboardMode(eRCInput.kmNone)
		except Exception as e:
			_jurnal('modul tastaturii rămâne neschimbat (%s)' % e)
		if self.mapper is not None:
			self.mapper.rawKey.get().append(self._taste)
			self.mapper.captureEnded.get().append(self._capturaOprita)
			self.legat = True
		self.timer.start(1000, False)
		self.arataStart()

	def _laInchidere(self):
		self.timer.stop()
		if self.mapper is not None:
			# întâi funcțiile scoase din semnale (nu se cheamă din interiorul unui semnal), apoi captura oprită, dacă
			# e a ecranului: una pornită de pagina web rămâne a ei (revizia, P23)
			if self.legat:
				for semnal, f in ((self.mapper.rawKey, self._taste), (self.mapper.captureEnded, self._capturaOprita)):
					lista = semnal.get()
					if f in lista:
						lista.remove(f)
				self.legat = False
			self._opreste_captura()
		if self.mod_tastatura is not None:
			try:
				eRCInput.getInstance().setKeyboardMode(self.mod_tastatura)
			except Exception:
				pass

	def _salveaza(self):
		eroare = D.salveaza(self.date, self.cale)
		if eroare:
			_jurnal('asocierile nu s-au putut scrie (%s)' % eroare)
		self.semn_fisier = _semn_fisier(self.cale)
		if self.mapper is not None:
			D.incarca_in_mapper(self.mapper, self.date)
			self.mapper.apply()
		return not eroare

	def _captura_web(self):
		"""Modul capturii pornite de pagina web (captureListen sau captureOthers), sau captureOff."""
		if self.mapper is None or self.captura_mea:
			return eRCMapper.captureOff
		return self.mapper.getCaptureMode()

	def _nu_se_poate_schimba(self):
		"""True dacă ecranul nu are voie să schimbe acum asocierile: pagina web asociază o telecomandă (ar scrie peste
		ea; pe ecran, de ce), sau fișierul tocmai a fost schimbat de pagina web (lista se arată din nou, ca omul să
		vadă ce e acum înainte să schimbe ceva)."""
		if self._captura_web() == eRCMapper.captureOthers:
			self['ajutor'].setText(_('Pagina web folosește acum telecomenzile.'))
			return True
		if self._reincarca():
			self._arata_din_nou()
			return True
		return False

	def _arata_din_nou(self):
		"""Lista de acum după ce s-a citit din nou fișierul."""
		t = self.telecomanda_taste
		if self.mod == TASTE and t is not None and D.gaseste(self.date, t['id']) is not None:
			self.arataTaste(t['id'])
		else:
			self.arataStart(self._curent() if self.mod == START else None)

	def _porneste_captura(self, mod, total):
		if self.mapper is None:
			return False
		if self._captura_web() != eRCMapper.captureOff:
			return False            # pagina web ascultă sau asociază: ecranul nu îi ia captura (revizia, P23)
		self.ultimul = self.mapper.getLastSequence()
		ok = self.mapper.setCapture(mod, D.TERMEN_FARA_TASTE, total, D.TERMEN_SEMN_VIATA)
		if not ok:
			_jurnal('captura nu a pornit')
		self.captura_mea = bool(ok)
		return bool(ok)

	def _nu_porneste(self, text):
		"""Captura refuzată: de ce, pe rândul de jos."""
		if self._captura_web() != eRCMapper.captureOff:
			text = _('Pagina web folosește acum telecomenzile.')
		self['ajutor'].setText(text)

	def _opreste_captura(self):
		"""Oprește numai captura pornită de ecran."""
		if self.mapper is not None and self.captura_mea:
			self.mapper.setCapture(eRCMapper.captureOff, 0, 0, 0)
		self.captura_mea = False

	def _reincarca(self):
		"""Fișierul de asocieri schimbat din afara ecranului (pagina web): se citește din nou. Întoarce True dacă
		s-a citit."""
		semn = _semn_fisier(self.cale)
		if semn == self.semn_fisier:
			return False
		self.semn_fisier = semn
		self._citeste_fisierul()
		return True

	def _citeste_fisierul(self):
		"""Asocierile din fișier. Mesajul despre un fișier stricat merge în jurnal în română și rămâne pentru pagina
		de start ca șablon, tradus abia acolo."""
		self.date, sablon, argument = D.incarca_cu_sablon(self.cale)
		if sablon:
			_jurnal(D.text_mesaj(sablon, argument))
			self.mesaj_fisier = (sablon, argument)

	# ------------------------------------------------------------------ desenul

	def _deseneaza(self):
		c = self['aprinse']
		c.clear()
		if self.desen is None:
			c.flush()
			return
		latime, inaltime, butoane = self.desen
		fx, fy, ff = self.fx, self.fy, self.ff
		c.fill(0, 0, _ori(latime, fx), _ori(inaltime, fy), TRANSPARENT)
		straturi = [(i, APRINS) for i in sorted(self.aprinse)]
		if self.cerut is not None:
			straturi.append((self.cerut, CERUT_TARE if self.puls else CERUT_SLAB))
		for ident, culoare in straturi:
			b = butoane.get(ident)
			if b is None:
				continue
			if 'cerc' in b:
				c.fillCircle(_k(b['cerc'][0], fx), _k(b['cerc'][1], fy), _k(b['cerc'][2], ff), culoare)
			else:
				c.fillPolygon([(p[0] * fx, p[1] * fy) for p in b['poligon']] if fx != 1.0 or fy != 1.0 else b['poligon'],
					culoare)
		for ident in sorted(self.semne):
			b = butoane.get(ident)
			if b is None:
				continue
			if b['forma'] == 'segment':
				# segmentele săgeților: semnul în mijlocul lor, nu în colțul cutiei (care e în afara formei)
				x = sum(p[0] for p in b['poligon']) / len(b['poligon'])
				y = sum(p[1] for p in b['poligon']) / len(b['poligon'])
			else:
				x, y = b['x'] + b['w'] - 3, b['y'] + 3
			c.fillCircle(_k(x, fx), _k(y, fy), _k(RAZA_SEMN + 2, ff), CONTUR_SEMN)
			c.fillCircle(_k(x, fx), _k(y, fy), _k(RAZA_SEMN, ff), VERIFICAT)
		c.flush()

	# ------------------------------------------------------------------ afișaj

	def _culori(self, rosu='', verde='', galben='', albastru=''):
		"""Butoanele colorate de jos; cele fără rost acum nu se arată."""
		for nume, text in (('key_red', rosu), ('key_green', verde), ('key_yellow', galben), ('key_blue', albastru)):
			self[nume].setText(text)
			if text:
				self[nume].show()
			else:
				self[nume].hide()

	def _vizibil(self, lista):
		for nume in ('lista', 'mare', 'detalii', 'istoric'):
			if (nume == 'lista') == lista:
				self[nume].show()
			else:
				self[nume].hide()

	def _rand(self, cheie, text, culoare=0xF2F4F8):
		return [cheie, MultiContentEntryText(pos=(_ori(16, self.fx), 0), size=(_ori(1420, self.fx), self.rand), font=0,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=text, color=culoare, color_sel=culoare)]

	def _text_telecomanda(self, t):
		fel = _('USB') if t['fel'] == 'usb' else _('IR')
		n = len(set(t['taste'].values()))
		stare = _('activă') if t['activa'] else _('oprită')
		if n == 1:
			taste = _('o tastă asociată')
		else:
			taste = _('%d taste asociate') % n
		return '%s (%s), %s, %s' % (t['nume'], fel, taste, stare)

	def arataStart(self, selectie=None):
		self.mod = START
		self.aprinse, self.semne, self.cerut = set(), set(), None
		self.asteapta_continuare = self.intrebare_proba = False
		self.contor_ir = None
		self['titlu'].setText(_('Telecomenzi'))
		randuri = [self._rand(RAND_CITITOR, _('Cititor de coduri'))]
		if self.proba is not None and self.proba.verificate:
			# proba începută se reia de unde a rămas; „Începe din nou” o pornește de la zero (revizia, P28)
			randuri.append(self._rand(RAND_PROBA, '%s: %s' % (_('Proba tastelor'),
				_('%d din %d de butoane verificate') % (len(self.proba.verificate), D.NUMAR_BUTOANE))))
			randuri.append(self._rand(RAND_PROBA_NOUA, _('Începe din nou')))
		else:
			randuri.append(self._rand(RAND_PROBA, _('Proba tastelor')))
		randuri.append(self._rand(RAND_ASOCIERE, _('Asociază o telecomandă nouă')))
		for t in self.date['telecomenzi']:
			randuri.append(self._rand(t['id'], self._text_telecomanda(t), 0xF2F4F8 if t['activa'] else 0x8A94A6))
		if self.date['telecomenzi']:
			randuri.append(self._rand(RAND_STERGE_TOT, _('Șterge toate asocierile'), 0xFF8A80))
		self['lista'].setList(randuri)
		self._vizibil(True)
		if selectie is not None:
			for i, r in enumerate(randuri):
				if r[0] == selectie:
					self['lista'].moveToIndex(i)
					break
		self.adresa_web = _adresa_web()
		self._selectie()
		self._deseneaza()

	def _ajutor_start(self, t=None):
		"""Rândul de jos al paginii de start: drumul prin pagina web, numai cu adresa ei adevărată și numai dacă
		pagina există (revizia, P21); mesajul fișierului stricat; pentru telecomanda aleasă, când tastele ei
		neasociate încă trec (revizia, P20)."""
		ajutor = []
		if self.adresa_web:
			ajutor.append(_('Dacă telecomanda receptorului nu merge, asociază din pagina web: %s') % self.adresa_web)
		if self.mesaj_fisier[0]:
			ajutor.append(D.text_mesaj(self.mesaj_fisier[0], self.mesaj_fisier[1], _))
		if t is not None and t['fel'] == 'usb' and t.get('neasociate') == 'opresc' and not D.navigare_completa(t):
			ajutor.append(_('Tastele neasociate se opresc numai după ce sunt asociate OK, săgețile, EXIT și MENU.'))
		self['ajutor'].setText('\n'.join(ajutor))

	def _curent(self):
		c = self['lista'].getCurrent()
		return c[0] if c else None

	def _selectie(self):
		if self.mod == START:
			t = D.gaseste(self.date, self._curent() or '')
			self._ajutor_start(t)
			if t is None:
				self._culori()
			else:
				self._culori(_('Șterge telecomanda'), _('Pornește') if not t['activa'] else _('Oprește'), _('Redenumește'),
					_('Tastele neasociate: se opresc') if t.get('neasociate') == 'opresc' else _('Tastele neasociate: trec'))
		elif self.mod == TASTE:
			cod = self._curent()
			t = self.telecomanda_taste
			self.aprinse = set()
			if t is not None and cod in t['taste']:
				b = D.DUPA_COD.get(t['taste'][cod])
				if b is not None:
					self.aprinse = {b[0]}
			self._deseneaza()

	def _secunde(self):
		if self.mapper is None or self.mapper.getCaptureMode() == eRCMapper.captureOff:
			return ''
		n = self.mapper.getCaptureSecondsLeft()
		if n < 0:
			return ''
		return _('Mai sunt %d secunde') % n

	def _ajutor_captura(self):
		iesire = _('Ieșire: EXIT sau MENU de două ori, sau orice tastă ținută 3 secunde.')
		self['ajutor'].setText('%s %s' % (iesire, self._secunde()))

	# ------------------------------------------------------------------ cititorul și proba

	def porniCititor(self):
		if not self._porneste_captura(eRCMapper.captureAll, D.TERMEN_TOTAL_CITITOR):
			self._nu_porneste(_('Cititorul nu poate porni acum.'))
			return
		self.mod = CITITOR
		self.istoric = []
		self.ancora = None          # ceasul istoricului, luat la prima tastă
		self.aprinse = set()
		self.contor_ir = D.ContorIR(D.CREDIT_TASTA_PORNIRE) if os.path.exists(self.cale_ir) else None
		self.ir_aratat = 0
		self.ev_cititor = None
		self['titlu'].setText(_('Cititor de coduri'))
		self['mare'].setText(_('Apasă orice buton.'))
		self['detalii'].setText(_('Tastele nu fac nimic cât e deschis cititorul; se arată numai codul lor.'))
		self['istoric'].setText('')
		self._vizibil(False)
		self._culori()
		self._ajutor_captura()
		self._deseneaza()

	def porniProba(self, noua=False):
		"""Proba se reia de unde a rămas cât e deschis ecranul; `noua` o începe de la zero (revizia, P28)."""
		if not self._porneste_captura(eRCMapper.captureAll, D.TERMEN_TOTAL_CITITOR):
			self._nu_porneste(_('Proba nu poate porni acum.'))
			return
		self.mod = PROBA
		if noua or self.proba is None:
			self.proba = D.Proba()
		self.aprinse = set()
		self.semne = set(self.proba.verificate)
		self['titlu'].setText(_('Proba tastelor'))
		self._vizibil(False)
		self['istoric'].setText('')
		self._culori()
		self._arataProba(None)
		self._ajutor_captura()
		self._deseneaza()

	def _arataProba(self, ev):
		p = self.proba
		if p.gata():
			self['mare'].setText(_('Toate butoanele merg.'))
		else:
			self['mare'].setText(_('%d din %d de butoane verificate') % (len(p.verificate), D.NUMAR_BUTOANE))
		randuri = []
		ramase = p.ramase()
		if ramase:
			randuri.append(_('Încă neapăsate: %s') % ', '.join(_(D.DUPA_ID[i][1]) for i in ramase))
		if ev is not None and ev['dispozitiv'] != D.NATIV:
			randuri.append(_('de pe: %s, cod %d') % (ev['dispozitiv'], ev['cod']))
		self['detalii'].setText('\n'.join(randuri))

	def _buton_ev(self, ev):
		"""Butonul Viper al unui eveniment: cel în care se traduce sau, de pe telecomanda receptorului, el însuși."""
		return D.DUPA_COD.get(ev['tinta'] if ev['tinta'] >= 0 else (ev['cod'] if ev['dispozitiv'] == D.NATIV else -1))

	def _scrie_detalii_cititor(self):
		"""Rândurile cititorului: ultima tastă (dacă a venit vreuna) și semnul IR străin. Semnul se scrie și fără
		nicio tastă, din bătaia de o secundă: o telecomandă IR străină nu dă taste (revizia, P22)."""
		randuri = []
		ev = self.ev_cititor
		if ev is not None:
			b = self._buton_ev(ev)
			disp = ev['dispozitiv']
			randuri.append(_('Dispozitiv: %s') % (_('telecomanda receptorului') + ' (%s)' % disp if disp == D.NATIV else disp))
			if ev['fel'] != D.ASCII:
				randuri.append(_('Cod: %d (0x%X) %s') % (ev['cod'], ev['cod'], D.nume_tasta(ev['cod'], self.keyids)))
			randuri.append(_('Felul: %s') % _(D.FELURI.get(ev['fel'], '')))
			if ev['scan'] >= 0:
				randuri.append(_('Cod brut USB (HID): 0x%X') % ev['scan'])
			if b is not None and disp != D.NATIV:
				randuri.append(_('Merge ca butonul %s al telecomenzii receptorului') % _(b[1]))
			if disp == D.NATIV and b is not None:
				randuri.append(_('IR: NEC, adresa 0x02 0xCD, comanda 0x%02X, KeyId 0x%08X') % (b[4], D.keyid_viper(b[4])))
		elif not self.ir_aratat:
			randuri.append(_('Tastele nu fac nimic cât e deschis cititorul; se arată numai codul lor.'))
		if self.ir_aratat:
			randuri.append(_('Semnale IR pe care receptorul nu le folosește: %d') % self.ir_aratat)
			randuri.append(_('Receptorul a primit un semnal de la altă telecomandă, dar nu îl poate citi încă.'))
		self['detalii'].setText('\n'.join(randuri))

	def _eveniment_cititor(self, ev):
		b = self._buton_ev(ev)
		if ev['fel'] == D.ASCII:
			mare = _('caracterul %s') % (repr(chr(ev['cod'])) if 0 < ev['cod'] < 0x110000 else ev['cod'])
		elif b is not None:
			mare = _(b[1])
		else:
			mare = D.nume_tasta(ev['cod'], self.keyids) or (_('cod %d') % ev['cod'])
		self['mare'].setText(mare)
		self.ev_cititor = ev
		self._scrie_detalii_cititor()
		# în istoric: apăsarea și apăsarea lungă; „ținut” și eliberarea nu sunt apăsări noi
		if self.ancora is None:
			self.ancora = D.ancora_ceas(ev)
		if ev['fel'] in (D.APASAT, D.LUNG, D.ASCII):
			self.istoric.append(D.rand_istoric(ev, keyids=self.keyids, ancora=self.ancora))
			self.istoric = self.istoric[-D.NUMAR_ISTORIC:]
			self['istoric'].setText('\n'.join(reversed(self.istoric)))
		self._aprinde(ev, b)

	def _aprinde(self, ev, b):
		if b is None:
			return
		if ev['fel'] == D.ELIBERAT:
			self.aprinse.discard(b[0])
		elif ev['fel'] in (D.APASAT, D.TINUT, D.LUNG):
			self.aprinse = {b[0]}
		self._deseneaza()

	def _eveniment_proba(self, ev):
		ident = self.proba.primeste(ev)
		b = self._buton_ev(ev)
		if ident is not None:
			self.semne.add(ident)
		self._arataProba(ev if b is not None else None)
		self._aprinde(ev, b)

	# ------------------------------------------------------------------ asocierea

	def porniAsociere(self):
		if self._captura_web() == eRCMapper.captureOff:
			self._reincarca()
		self.inainte_de_asociere = D.curata(D.de_scris(self.date))
		self.asociere = D.Asociere(self.date)
		if not self._porneste_captura(eRCMapper.captureOthers, D.TERMEN_TOTAL_ASOCIERE):
			self._nu_porneste(_('Asocierea nu poate porni acum.'))
			self.asociere = None
			return
		self.mod = ASOCIERE
		self.aprinse, self.semne, self.cerut = set(), set(), None
		# semnalele IR pe care receptorul nu le folosește, cât se așteaptă prima tastă
		self.contor_ir = D.ContorIR(D.CREDIT_TASTA_PORNIRE) if os.path.exists(self.cale_ir) else None
		self.ir_aratat = 0
		self['titlu'].setText(_('Asociază o telecomandă nouă'))
		self._vizibil(False)
		self['istoric'].setText('')
		self['mare'].setText(_('Apasă orice buton pe telecomanda nouă.'))
		self._scrie_detalii_alege()
		self._culori()
		self['ajutor'].setText(_('EXIT = Anulează.'))
		self._deseneaza()

	def _scrie_detalii_alege(self):
		"""Pasul întâi al asocierii: ce se poate asocia și, dacă receptorul primește semnale IR pe care nu le folosește,
		semnul lor. O telecomandă cu infraroșu, alta decât a receptorului, nu dă taste în enigma2, deci
		nu se poate asocia; ecranul o spune de la început, nu abia după 30 de secunde."""
		randuri = [_('O telecomandă USB (sau o tastatură) se bagă în receptor înainte; se vede imediat.'),
			_('O telecomandă cu infraroșu, alta decât a receptorului, nu se poate asocia încă.')]
		if self.ir_aratat:
			randuri.append(_('Receptorul primește semnalul unei telecomenzi cu infraroșu, dar nu îl poate folosi încă.'))
		self['detalii'].setText('\n'.join(randuri))

	def _citeste_ir(self):
		"""O fereastră a contorului IR (bătaia de o secundă). True dacă s-a schimbat numărul arătat."""
		if self.contor_ir is None:
			return False
		text = _procFundal(_citesteIrText, self.cale_ir)
		if text is None:
			self.contor_ir = None
			return False
		n = self.contor_ir.fereastra(text)
		if n == self.ir_aratat:
			return False
		self.ir_aratat = n
		return True

	def _arataPas(self, rezultat=None):
		a = self.asociere
		t = D.gaseste(self.date, a.ident) if a.ident else None
		if a.stare == a.GATA:
			self._arataGata()
			return
		b = a.buton_curent()
		self.cerut = b[0] if b is not None else None
		self.semne = set(a.asociate)
		randuri = []
		if rezultat == 'refacere' and t is not None:
			randuri.append(_('Telecomanda aceasta e deja asociată ca „%s”. O refaci buton cu buton.') % t['nume'])
		elif rezultat in ('ales', 'refacere') and t is not None:
			randuri.append(_('Telecomanda nouă: %s') % t['dispozitiv'])
		elif rezultat == 'asociat' and self._ultim is not None:
			bu, cod = self._ultim
			randuri.append(_('%s = cod %d (0x%X)') % (_(bu[1]), cod, cod))
		elif rezultat == 'sarit' and self._ultim_sarit is not None:
			randuri.append(_('Sărit: %s') % _(self._ultim_sarit[1]))
		elif rezultat == 'alt_dispozitiv':
			randuri.append(_('Butonul a venit de pe alt dispozitiv; apasă pe telecomanda aleasă.'))
		if a.confirma is not None:
			vechi = D.DUPA_COD.get(a.confirma[1])
			randuri.append(_('Codul acesta e deja folosit pentru %s. Apasă-l încă o dată ca să-l muți la %s, sau alt buton.') %
				(_(vechi[1]) if vechi else '?', _(b[1]) if b else '?'))
		if b is not None and b[0] == 'power':
			randuri.append(_('Din standby adânc receptorul pornește numai cu telecomanda lui.'))
		if a.de_baza_facute():
			randuri.append(_('Pe telecomanda nouă: ține apăsat 2 secunde = Sari; ține apăsat EXIT = Gata.'))
		elif a.lipsa_pentru_gata():
			# dupa pasul MENU, Gata nu mai vine daca OK, o sageata sau EXIT au fost sarite; se spune
			# ce lipseste, nu „Gata merge după MENU”
			randuri.append(_('Pe telecomanda nouă: ține apăsat 2 secunde = Sari.'))
			randuri.append(_('Gata cere și butoanele sărite: %s. Cu ROȘU (Înapoi) te întorci la ele.') %
				', '.join(_(D.DUPA_ID[i][1]) for i in a.lipsa_pentru_gata()))
		else:
			# până la pasul MENU, EXIT ținut înseamnă și el Sari
			randuri.append(_('Pe telecomanda nouă: ține apăsat 2 secunde = Sari. Gata merge după MENU.'))
		if b is not None:
			self['mare'].setText(_('Apasă pe telecomanda nouă butonul pentru: %s') % _(b[1]))
		self['detalii'].setText('\n'.join(randuri))
		n = len(a.asociate)
		self['istoric'].setText(_('Asociate %d, sărite %d.') % (n, len(a.sarite)))
		self._culori(_('Înapoi'), _('Gata') if a.de_baza_facute() else '', _('Sari'), '')
		self['ajutor'].setText('%s %s' % (_('EXIT = Anulează.'), self._secunde()))
		self._deseneaza()

	def _arataGata(self):
		a = self.asociere
		asociate, sarite = a.rezumat()
		self.cerut = None
		self.semne = set(a.asociate)
		self._opreste_captura()
		self.mod = ASOCIERE
		self.intrebare_proba = True
		self['mare'].setText(_('Asociate %d, sărite %d.') % (asociate, sarite))
		randuri = []
		t = D.gaseste(self.date, a.ident) if a.ident else None
		if t is not None and t['fel'] == 'usb':
			# ce se întâmplă cu butoanele ei neasociate
			if D.opreste_neasociate(t):
				randuri.append(_('Tastele neasociate ale telecomenzii noi nu mai merg. În listă, ALBASTRU le lasă să treacă.'))
			elif t.get('neasociate') == 'opresc':
				randuri.append(_('Tastele neasociate se opresc numai după ce sunt asociate OK, săgețile, EXIT și MENU.'))
			else:
				randuri.append(_('Tastele neasociate ale telecomenzii noi merg ca înainte.'))
		randuri.append(_('Le probezi acum?'))
		randuri.append(_('OK = da, EXIT = nu'))
		self['detalii'].setText('\n'.join(randuri))
		self['istoric'].setText('')
		self._culori()
		self['ajutor'].setText('')
		self._deseneaza()

	def _eveniment_asociere(self, ev):
		a = self.asociere
		if a is None or self.intrebare_proba or self.intrebare_deschisa:
			return
		b_inainte = a.buton_curent()
		rezultat = a.primeste(ev)
		self._ultim = None
		self._ultim_sarit = None
		if rezultat in ('asociat', 'gata') and b_inainte is not None and ev['fel'] == D.ELIBERAT:
			self._ultim = (b_inainte, ev['cod'])
		if rezultat == 'sarit':
			self._ultim_sarit = b_inainte
		if a.schimbat:
			self._salveaza()
		if rezultat == 'propriu':
			self['detalii'].setText(_('Aceasta e telecomanda receptorului. Apasă un buton pe cealaltă telecomandă.'))
			return
		if rezultat == 'nimic':
			return
		self._arataPas(rezultat)

	_ultim = None
	_ultim_sarit = None

	def _anuleazaAsocierea(self, pastreaza):
		self.intrebare_deschisa = False
		if not pastreaza and self.inainte_de_asociere is not None:
			self.date = self.inainte_de_asociere
			self._salveaza()
		self.asociere = None
		self._opreste_captura()
		self.arataStart()

	# ------------------------------------------------------------------ din C++

	def _taste(self, numar):
		"""rawKey: rulează în keyEvent(), deci nimic de aici nu are voie să arunce (o excepție scăpată în C++ oprește
		interfața)."""
		try:
			if self.mapper is None or not self.captura_mea:
				return                  # tastele capturii pornite de pagina web sunt ale ei
			for t in self.mapper.getEvents(self.ultimul):
				ev = D.eveniment(t)
				if ev is None:
					continue
				self.ultimul = max(self.ultimul, ev['numar'])
				if self.contor_ir is not None:
					self.contor_ir.nativ(ev)
				if self.mod == CITITOR:
					self._eveniment_cititor(ev)
				elif self.mod == PROBA:
					self._eveniment_proba(ev)
				elif self.mod == ASOCIERE:
					self._eveniment_asociere(ev)
		except Exception as e:
			_jurnal('tasta %r nu a putut fi arătată: %s' % (numar, e))

	def _capturaOprita(self, motiv):
		try:
			if not self.captura_mea:
				return                  # s-a oprit captura paginii web; fișierul îl vede _bate
			self.captura_mea = False
			if self.mod in (CITITOR, PROBA):
				self.arataStart(RAND_CITITOR if self.mod == CITITOR else RAND_PROBA)
			elif self.mod == ASOCIERE and self.asociere is not None and not self.intrebare_proba:
				if motiv in (D.OPRIRE_FARA_TASTE, D.OPRIRE_TERMEN, D.OPRIRE_SEMN_VIATA):
					self.asteapta_continuare = True
					self.cerut = None
					if self.asociere.stare == self.asociere.ALEGE:
						# nicio tastă: dacă au venit semnale IR, se spune că le-a primit, nu că n-a primit nimic (V2)
						self._citeste_ir()
						if self.ir_aratat:
							self['mare'].setText(_('Am primit numai semnal infraroșu. Apasă OK ca să continui.'))
						else:
							self['mare'].setText(_('Nu am primit nimic de la telecomanda nouă. Apasă OK ca să continui.'))
						self._scrie_detalii_alege()
					else:
						self['mare'].setText(_('Nu am primit nimic de la telecomanda nouă. Apasă OK ca să continui.'))
					self['ajutor'].setText(_('EXIT = Anulează.'))
					self._deseneaza()
		except Exception as e:
			_jurnal('oprirea capturii nu a putut fi arătată: %s' % e)

	def _bate(self):
		try:
			# semnul de viață numai pentru captura ecranului: una pornită de pagina web se oprește singură la 20 s
			# după închiderea browserului, chiar dacă ecranul e deschis (revizia, P23)
			if self.mapper is not None and self.captura_mea and self.mapper.getCaptureMode() != eRCMapper.captureOff:
				self.mapper.touch()
			if self.mod in (CITITOR, PROBA):
				self._ajutor_captura()
				if self.mod == CITITOR and self._citeste_ir():
					self._scrie_detalii_cititor()
			elif self.mod in (START, TASTE) and not self.captura_mea:
				# asocierile schimbate din pagina web se văd pe televizor
				if self._reincarca():
					self._arata_din_nou()
			elif self.mod == ASOCIERE and self.asociere is not None and not self.intrebare_proba and not self.asteapta_continuare:
				self.puls = not self.puls
				if self.cerut is not None:
					self._deseneaza()
				if self.asociere.stare == self.asociere.PAS:
					self['ajutor'].setText('%s %s' % (_('EXIT = Anulează.'), self._secunde()))
				elif self.asociere.stare == self.asociere.ALEGE and self.captura_mea and self._citeste_ir():
					self._scrie_detalii_alege()
		except Exception as e:
			_jurnal('bătaia ecranului: %s' % e)

	# ------------------------------------------------------------------ tastele ecranului

	def keyOk(self):
		if self.mod == START:
			c = self._curent()
			if c == RAND_CITITOR:
				self.porniCititor()
			elif c == RAND_PROBA:
				self.porniProba()
			elif c == RAND_PROBA_NOUA:
				self.porniProba(noua=True)
			elif c == RAND_ASOCIERE:
				self.porniAsociere()
			elif c == RAND_STERGE_TOT:
				if not self._nu_se_poate_schimba():
					self.session.openWithCallback(self._stergeTot, MessageBox, _('Ștergi toate asocierile?'),
						MessageBox.TYPE_YESNO, default=False)
			elif c is not None:
				self.arataTaste(c)
		elif self.mod == ASOCIERE:
			if self.intrebare_proba:
				# o telecomandă abia asociată se probează de la zero
				self.asociere = None
				self.porniProba(noua=True)
			elif self.asteapta_continuare:
				if self._porneste_captura(eRCMapper.captureOthers, D.TERMEN_TOTAL_ASOCIERE):
					self.asteapta_continuare = False
					if self.asociere.stare == self.asociere.ALEGE:
						if self.contor_ir is not None:
							self.contor_ir.reia(D.CREDIT_TASTA_PORNIRE)   # tastele din pauză nu s-au numărat; OK-ul acesta (V5)
						self['mare'].setText(_('Apasă orice buton pe telecomanda nouă.'))
						self._scrie_detalii_alege()
					else:
						self._arataPas()
				else:
					self._nu_porneste(_('Asocierea nu poate porni acum.'))

	def keyExit(self):
		if self.mod == START:
			self.close()
		elif self.mod == TASTE:
			self.arataStart(self.telecomanda_taste['id'] if self.telecomanda_taste else None)
		elif self.mod == ASOCIERE:
			if self.intrebare_proba:
				ident = self.asociere.ident if self.asociere is not None else None
				self.asociere = None
				self.arataStart(ident)
			elif self.asociere is not None and self.asociere.ident is not None:
				# cât e deschisă întrebarea, tastele telecomenzii noi nu mai trec la pasul următor
				self.intrebare_deschisa = True
				self.session.openWithCallback(self._anuleazaAsocierea, MessageBox, _('Păstrezi ce ai asociat până acum?'),
					MessageBox.TYPE_YESNO)
			else:
				self._anuleazaAsocierea(False)
		else:
			# cititorul și proba: tastele nu ajung aici (le oprește C++); rămâne doar ca siguranță
			self._opreste_captura()
			self.arataStart()

	def keyRosu(self):
		if self.mod == START:
			if self._nu_se_poate_schimba():
				return
			t = D.gaseste(self.date, self._curent() or '')
			if t is not None:
				self.session.openWithCallback(lambda da: self._stergeTelecomanda(da, t['id']), MessageBox,
					_('Ștergi telecomanda „%s”?') % t['nume'], MessageBox.TYPE_YESNO, default=False)
		elif self.mod == TASTE:
			if self.telecomanda_taste is None or self._nu_se_poate_schimba():
				return
			ident = self.telecomanda_taste['id']
			cod = self._curent()
			if cod is not None and D.sterge_tasta(self.date, ident, cod):
				self._salveaza()
			if D.gaseste(self.date, ident) is not None:
				self.arataTaste(ident)
			else:
				self.arataStart()
		elif self.mod == ASOCIERE and self.asociere is not None and not self.intrebare_proba:
			if self.asociere.inapoi():
				if self.asociere.schimbat:
					self._salveaza()
				self._arataPas()

	def keyVerde(self):
		if self.mod == START:
			if self._nu_se_poate_schimba():
				return
			t = D.gaseste(self.date, self._curent() or '')
			if t is not None:
				D.comuta_activa(self.date, t['id'])
				self._salveaza()
				self.arataStart(t['id'])
		elif self.mod == ASOCIERE and self.asociere is not None and not self.intrebare_proba:
			if self.asociere.termina():
				self._arataGata()

	def keyGalben(self):
		if self.mod == START:
			if self._nu_se_poate_schimba():
				return
			t = D.gaseste(self.date, self._curent() or '')
			if t is not None:
				self.session.openWithCallback(lambda nume: self._redenumeste(nume, t['id']), VirtualKeyBoard,
					title=_('Numele telecomenzii'), text=t['nume'])
		elif self.mod == ASOCIERE and self.asociere is not None and not self.intrebare_proba:
			self._ultim_sarit = self.asociere.buton_curent()
			r = self.asociere.sari()
			if r != 'nimic':
				self._arataPas('sarit')

	def keyAlbastru(self):
		if self.mod == START:
			if self._nu_se_poate_schimba():
				return
			t = D.gaseste(self.date, self._curent() or '')
			if t is not None and D.comuta_neasociate(self.date, t['id']) is not None:
				self._salveaza()
				self.arataStart(t['id'])

	# ------------------------------------------------------------------ lista tastelor unei telecomenzi, ștergeri

	def arataTaste(self, ident):
		t = D.gaseste(self.date, ident)
		if t is None:
			return
		self.mod = TASTE
		self.telecomanda_taste = t
		self['titlu'].setText(t['nume'])
		randuri = []
		for cod, tinta in sorted(t['taste'].items(), key=lambda kv: D.ORDINE_ASOCIERE.index(D.DUPA_COD[kv[1]][0])):
			b = D.DUPA_COD[tinta]
			sursa = D.text_cod(cod, self.keyids) if t['fel'] == 'usb' else '0x%X' % cod
			randuri.append(self._rand(cod, '%s = %s' % (_(b[1]), sursa)))
		if not randuri:
			randuri.append(self._rand(None, _('Nicio tastă asociată.'), 0x8A94A6))
		self['lista'].setList(randuri)
		self._vizibil(True)
		self.semne = set(D.DUPA_COD[v][0] for v in t['taste'].values())
		self._culori(_('Șterge asocierea tastei') if t['taste'] else '')
		self['ajutor'].setText(_('EXIT = înapoi la listă'))
		self._selectie()

	# după fereastra de întrebare se verifică din nou: pagina web putea porni între timp o asociere
	def _stergeTelecomanda(self, da, ident):
		if not da or self._nu_se_poate_schimba():
			return
		if D.sterge_telecomanda(self.date, ident):
			self._salveaza()
		self.arataStart()

	def _stergeTot(self, da):
		if not da or self._nu_se_poate_schimba():
			return
		D.sterge_tot(self.date)
		self._salveaza()
		self.arataStart()

	def _redenumeste(self, nume, ident):
		if not nume or self._nu_se_poate_schimba():
			return
		if D.redenumeste(self.date, ident, nume):
			self._salveaza()
		self.arataStart(ident)


def _citesteIrText(cale):
	try:
		with open(cale) as f:
			return f.read(8192)
	except OSError:
		return None


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)
