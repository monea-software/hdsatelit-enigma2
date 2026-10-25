# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Gestionarul de extensii HDSatelit (meniul principal > Extensii; Software > Extensii). Doar in imaginea HDSatelit.

Un singur ecran, ca magazinul de aplicatii al unui televizor:
 - file sus (Stanga/Dreapta): Pe receptor (extensiile instalate; OK le deschide, ca vechiul PluginBrowser),
   Actualizari (doar cand sunt), cate o fila pentru fiecare categorie care chiar are pachete in surse, Din fisier
   (.ipk de pe stick, disc sau retea) si Surse (feedurile HD Satelit si Pluginuri externe, cate un rand fiecare, si
   sursele adaugate de utilizator);
 - lista (Sus/Jos, P+/P- pe pagini): icoana, nume, descriere scurta, sursa, versiune, marime, insigne;
 - detaliile randului ales, mereu in dreapta;
 - OK = actiunea principala (Deschide, Instaleaza, Actualizeaza), rosu Sterge, verde actiunea principala (in fila
   Actualizari: Actualizeaza tot), galben Cauta dupa nume, albastru Descarca lista; EXIT un pas inapoi (iese din
   cautare, apoi inchide ecranul).
Instalarea, stergerea, actualizarea: HdsExtensiiActiune (confirmare cu sursa, versiunea si marimea, apoi progres pe
loc: un semn care se misca si un jurnal scurt). opkg porneste doar prin Components/Ipkg.py (lista de argumente, nume
verificate, fara shell). Datele: Components/HdsPachete.py, citite direct din fisierele opkg.
Aspectul: skinul (ecranele HdsExtensii si HdsExtensiiActiune, aliasurile HdsExtensii*, icoanele din
<hdsparameters> HdsExtensiiImage); culorile randurilor din culorile skinului, cu rezerva de mai jos."""
import os
import re
import time

from enigma import eListboxPythonMultiContent, eTimer, ePoint, eSize, gRGB, getDesktop, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Components.PluginComponent import plugins
from Components.Ipkg import IpkgComponent, opkgArguments, opkgProgram
from Components import HdsPachete as P
try:
	# logica comuna cu pagina web /extensii: randurile, planurile, sursele, descarcarea listei, lucrarea opkg
	from Components import HdsExtensiiLucru as L
except ImportError:  # probe pe PC: dosarul Components in sys.path
	import HdsExtensiiLucru as L
# descarcarea sursei unui plugin (0.6.6): modulul luat prin HdsExtensiiLucru (acelasi si pentru pagina web)
S = L.S
from Plugins.Plugin import PluginDescriptor
from Tools.Directories import resolveFilename, SCOPE_PLUGINS, SCOPE_SKIN_IMAGE

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la afisare, cu _t."""
	return text


TITLU = N_('Extensii')
JURNAL_OPKG = L.JURNAL_OPKG
DESCARCARE_AUTOMATA = 3600          # lista se descarca singura cel mult o data pe ora, la deschiderea ecranului
PAS_CAUTARE = 100                   # ms: cat de des se uita ecranul daca a terminat cautarea fisierelor .ipk (in fundal)
PAS_SCHIMBARI = 2000                # ms: cat de des se uita ecranul daca fisierele opkg s-au schimbat (pagina web)
CAUTARE_LENTA = 10                  # s: dupa atat, textul spune ca un stick, un disc sau o retea raspunde greu
MESAJ_CAUTA_FISIERE = N_('Căutarea fișierelor rulează încă.')
MESAJ_CAUTA_RETEA = N_('Se caută deja în rețea.')
# descrierea care nu incape in panoul din dreapta se arata intreaga pe pagini care se schimba singure (sagetile sunt
# ale listei si ale filelor, deci nu raman taste pentru derulare): o pagina care nu e ultima se termina cu „…”, una
# care nu e prima incepe cu „…”; o pagina sta pe ecran cat sa se poata citi (PAGINA_SEMNE_PE_S), intre cele doua
# limite, apoi urmeaza cealalta; dupa ultima vine iar prima
CONTINUARE = '…'
PAGINA_SEMNE_PE_S = 15
PAGINA_MIN_MS = 6000
PAGINA_MAX_MS = 20000

# culorile din skinul HDSatelit si rezerva pentru un alt skin (0xRRGGBB, opac)
CULORI = {
	'text': ('hdsText', 0xF2F4F8),
	'text2': ('hdsText2', 0xC9D2E3),
	'eticheta': ('hdsLabel', 0xAEB9CC),
	'stins': ('hdsDisabled', 0x667085),
	'brand': ('hdsBrand', 0x374EA1),
	'focus': ('hdsBrandLight', 0x9FB4FF),
	'pista': ('hdsTrack', 0x2A3350),
	'celula': ('hdsCell', 0x282D3F),
	'bun': ('hdsGood', 0x4FD18B),
	'chihlimbar': ('hdsAmber', 0xF5B83D),
	'rau': ('hdsBad', 0xFF6B5E),
	'intunecat': ('hdsMarkedText', 0x10162A),
	'alb': ('white', 0xFFFFFF),
}

ICOANA_INSTALATE = 'extensii'

# descarcarile listei (opkg update) se tin in Components/HdsExtensiiLucru.py pana se termina (si dupa inchiderea
# ecranului), ca sa le vada si pagina web; altfel colectorul de cicluri putea sterge IpkgComponent, iar destructorul
# lui eConsoleAppContainer omora opkg la jumatatea listei
_pastreazaPanaLaSfarsit = L.pastreazaPanaLaSfarsit


def _textModSigur():
	"""Fraza modului sigur pentru extensii (Components/HdsModSigur.textPentruExtensii), "" in afara lui."""
	try:
		from Components import HdsModSigur
		return HdsModSigur.textPentruExtensii()
	except Exception:
		return ''


def _descarcareRamasa():
	return L.descarcareInCurs()


def _jurnal(text):
	print('[HdsExtensii] %s' % text)


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			# alfa FF ar fi citit de lista ca „culoare din sablon"
			return v & 0xFFFFFF if (v >> 24) == 0xFF else v
	except Exception:
		pass
	return implicit


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


def _font(alias, nume, marime, inaltime=None):
	"""(gFont, inaltimea randului) din aliasul skinului (<alias name="HdsExtensii..."/>), altfel rezerva scalata"""
	try:
		from skin import getListFont
		f = _factor()
		font, h = getListFont(alias, (nume, int(marime * f), inaltime and int(inaltime * f) or 0))
		return font, h or (inaltime and int(inaltime * f)) or int(marime * f * 1.5)
	except Exception:
		from enigma import gFont
		return gFont(nume, marime), inaltime or int(marime * 1.5)


_icoane = {}


def icoana(cheie, marime):
	"""icoana unei categorii (liste/ext_<cheie>_<marime>.png din skin, prin <hdsparameters> HdsExtensiiImage);
	altfel icoana veche a pluginurilor"""
	k = (cheie, marime)
	if k not in _icoane:
		ptr = None
		try:
			from skin import getListPixmap
			ptr = getListPixmap('HdsExtensiiImage', '%s_%d' % (cheie, marime),
				resolveFilename(SCOPE_SKIN_IMAGE, 'skin_default/icons/plugin.png'))[0]
		except Exception as e:
			_jurnal('icoana %s: %s' % (cheie, e))
		_icoane[k] = ptr
	return _icoane[k]


def _marime_pixmap(ptr):
	try:
		s = ptr.size()
		return s.width(), s.height()
	except Exception:
		return 0, 0


# de unde e un fisier .ipk (stick, disc, retea, memoria receptorului), textele scurtate: in Components/HdsExtensiiLucru.py
_eticheta_loc = L.etichetaLoc
_scurt = L.scurt
_de_unde = L.deUnde


def _incape(eticheta):
	"""functia text -> True cand textul incape pe un rand in Label-ul `eticheta` (cu noWrap), masurat cu fontul lui:
	eLabel.calculateSize fara RS_WRAP da latimea intregului rand (lib/gui/elabel.cpp). None cand nu se poate masura."""
	inst = getattr(eticheta, 'instance', None)
	try:
		latime = inst.size().width()
		inst.calculateSize()
	except Exception:
		return None
	if latime <= 0:
		return None

	def incape(text):
		inst.setText(text)
		return inst.calculateSize().width() <= latime
	return incape


def _valoriPotrivite(eticheta, valori, rezerva):
	"""valorile pentru un Label cu cate un rand pe valoare, fiecare scurtata cu „…” cat sa incapa in latimea lui (inainte
	erau taiate la marginea widget-ului, fara semn): o cale (randul „Fișierul”, locurile de retea) la mijloc, ca sa
	ramana numele fisierului, restul la sfarsit. `rezerva`: cate semne incap, cand widget-ul nu se poate masura."""
	incape = _incape(eticheta) or rezerva
	rez = []
	for v in valori:
		v = P._curat(v, 400).replace('\n', ' ')
		rez.append(P.scurt_mijloc(v, incape) if v.startswith('/') else P.scurt_sfarsit(v, incape))
	return '\n'.join(rez)


_categorie_plugin = L.categoriePlugin


def _pastila(e, x, y, w, h, text, fundal, culoare, chenar_culoare=None, chenar=3):
	"""o pastila (fila, buton): chenarul e un dreptunghi plin dedesubt, nu border_width (acela muta textul in sus)"""
	if chenar_culoare is not None:
		e.append(MultiContentEntryText(pos=(x, y), size=(w, h), font=0, text='', backcolor=chenar_culoare,
			backcolor_sel=chenar_culoare))
		x, y, w, h = x + chenar, y + chenar, w - 2 * chenar, h - 2 * chenar
	e.append(MultiContentEntryText(pos=(x, y), size=(w, h), font=0, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER,
		text=text, color=culoare, color_sel=culoare, backcolor=fundal, backcolor_sel=fundal))


def _paginaDescriere(rest, incape, prima):
	"""(pagina, restul): cele mai multe cuvinte intregi de la inceputul lui `rest` care incap (incape(text) -> bool).
	O pagina care nu e ultima se termina cu „…”, una care nu e prima incepe cu „…”; semnele de punctuatie raman (nimic
	din text nu se pierde). Un cuvant singur prea lung se imparte intre pagini. Restul gol = ultima pagina."""
	inceput = '' if prima else CONTINUARE
	rest = rest if prima else rest.lstrip()
	if not rest:
		return '', ''
	if incape(inceput + rest):
		return inceput + rest, ''
	parti = re.findall(r'\S+\s*', rest)
	pagina = lambda k: inceput + ''.join(parti[:k]).rstrip() + CONTINUARE
	jos, sus = 0, len(parti) - 1
	while jos < sus:
		k = (jos + sus + 1) // 2
		if incape(pagina(k)):
			jos = k
		else:
			sus = k - 1
	if jos > 0:
		return pagina(jos), ''.join(parti[jos:])
	# nici primul cuvant nu incape: se taie la un semn
	jos, sus = 0, len(rest) - 1
	while jos < sus:
		k = (jos + sus + 1) // 2
		if incape(inceput + rest[:k] + CONTINUARE):
			jos = k
		else:
			sus = k - 1
	if jos == 0:
		return inceput + rest, ''
	return inceput + rest[:jos] + CONTINUARE, rest[jos:]


def _timpPagina(pagina):
	"""cat sta o pagina a descrierii pe ecran (ms), dupa lungimea ei"""
	return max(PAGINA_MIN_MS, min(PAGINA_MAX_MS, len(pagina) * 1000 // PAGINA_SEMNE_PE_S))


_text_versiuni = L.textVersiuni


class HdsExtensii(Screen, HelpableScreen):
	# rezerva pentru un skin fara ecranul HdsExtensii (skinul HDSatelit are unul complet)
	skin = """
	<screen name="HdsExtensii" position="center,center" size="1200,660" title="Extensii">
		<widget name="file" position="10,10" size="1180,44" itemHeight="44" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
		<widget name="stare" position="10,58" size="700,28" font="Regular;18" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget name="pista" position="720,70" size="200,4" backgroundColor="#002A3350" zPosition="2" />
		<widget name="semn" position="720,70" size="50,4" backgroundColor="#00F5B83D" zPosition="3" />
		<widget name="lista" position="10,92" size="760,520" itemHeight="64" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" transparent="1" zPosition="2" />
		<widget name="gol" position="10,200" size="760,120" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="dIcoana" position="790,96" size="160,160" alphatest="blend" zPosition="2" />
		<widget name="dTitlu" position="790,264" size="400,36" font="Regular;26" noWrap="1" transparent="1" zPosition="2" />
		<widget name="dInsigna" position="790,302" size="400,28" font="Regular;20" noWrap="1" transparent="1" zPosition="2" />
		<widget name="dEtichete" position="790,336" size="120,120" font="Regular;18" foregroundColor="#00AEB9CC" noWrap="1" transparent="1" zPosition="2" />
		<widget name="dValori" position="910,336" size="280,120" font="Regular;18" noWrap="1" transparent="1" zPosition="2" />
		<widget name="dDescriere" position="790,460" size="400,120" font="Regular;18" transparent="1" zPosition="2" />
		<widget name="dIndiciu" position="790,584" size="400,28" font="Regular;18" foregroundColor="#00F5B83D" noWrap="1" transparent="1" zPosition="2" />
		<widget name="key_red" position="10,624" size="290,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="306,624" size="290,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="602,624" size="290,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
		<widget name="key_blue" position="898,624" size="292,30" font="Regular;19" backgroundColor="#003D7BE0" halign="center" valign="center" zPosition="2" />
	</screen>"""

	# ultima descarcare a listei (automata, cu albastru sau din pagina web), pentru toata sesiunea:
	# HdsExtensiiLucru.STARE['ultima_descarcare']

	def __init__(self, session, fila='instalate'):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		# si PluginBrowser / PluginDownloadBrowser (subclase) folosesc acelasi ecran din skin
		self.skinName = 'HdsExtensii'
		self.setTitle(_t(TITLU))

		self.filaInitiala = fila
		self.catalog = P.Catalog()
		self.pluginuri = []
		self.fisiere = None            # [FisierIpk] de pe stick, disc, memorie: cautate in fundal la intrarea in fila Din fisier
		self.fisiereTaiate = False     # s-au gasit mai multe decat se arata (cele mai noi 300)
		self.fisiereRetea = None       # [FisierIpk] din locurile de retea, numai dupa ce utilizatorul cere cautarea acolo
		self.locuriRetea = []          # locurile de retea sarite de cautarea obisnuita (/media/net, montarile cifs/nfs...)
		self.cautareFisiere = None     # HdsPachete.CautareIpk asteptata (fara retea), cat ruleaza
		self.cautareRetea = None       # la fel, in retea
		self.anuntatLent = False
		self.file = []                 # [(id, eticheta, numar)]
		self.fila = 0
		self.decalajFile = 0
		self.pozitii = {}              # id fila -> randul ales ultima oara
		self.randuri = []
		self.cautare = ''
		self.filaDinaintea = None
		self.descarca = None           # IpkgComponent al descarcarii listei, cat ruleaza
		self.liniiDescarcare = []
		self.mesajStare = ''
		self.culoareStare = 'eticheta'

		self['file'] = MenuList([], content=eListboxPythonMultiContent)
		self['lista'] = MenuList([], content=eListboxPythonMultiContent)
		self['stare'] = Label('')
		self['pista'] = Label('')
		self['semn'] = Label('')
		self['gol'] = Label('')
		self['dIcoana'] = Pixmap()
		self['dTitlu'] = Label('')
		self['dInsigna'] = Label('')
		self['dEtichete'] = Label('')
		self['dValori'] = Label('')
		self['dDescriere'] = Label('')
		self['dIndiciu'] = Label('')
		self['key_red'] = Button('')
		self['key_green'] = Button('')
		self['key_yellow'] = Button(_t('Caută'))
		self['key_blue'] = Button(_t('Descarcă lista'))

		self['actiuni'] = HelpableActionMap(self, 'OkCancelActions', {
			'ok': (self.keyOk, 'Deschide, instalează sau actualizează'),
			'cancel': (self.keyCancel, 'Înapoi'),
		}, -1)
		self['directii'] = HelpableActionMap(self, 'DirectionActions', {
			'up': (self.keyUp, 'Rândul de sus'),
			'down': (self.keyDown, 'Rândul de jos'),
			'left': (self.keyLeft, 'Fila din stânga'),
			'right': (self.keyRight, 'Fila din dreapta'),
			'upRepeated': self.keyUp,
			'downRepeated': self.keyDown,
			'leftRepeated': self.keyLeft,
			'rightRepeated': self.keyRight,
			'upUp': self._nimic,
			'downUp': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
		}, -1)
		self['culori'] = HelpableActionMap(self, 'ColorActions', {
			'red': (self.keyRosu, 'Șterge extensia sau sursa'),
			'green': (self.keyVerde, 'Acțiunea principală'),
			'yellow': (self.keyGalben, 'Caută după nume'),
			'blue': (self.keyAlbastru, 'Descarcă lista de pachete'),
		}, -1)
		# P+/P- (si |<< >>|) pe pagini: contextul listei de canale; tastele colorate din el merg la aceleasi functii
		# MENU (0.6.6): Actualizeaza toate (0.6.6), din orice fila, cand sunt actualizari (mouse: clic pe rotita)
		self['pagini'] = ActionMap(['ChannelSelectBaseActions', 'MenuActions'], {
			'menu': self.keyMeniu,
			'nextBouquet': self.keyPaginaSus,
			'prevBouquet': self.keyPaginaJos,
			'nextMarker': self.keyPaginaJos,
			'prevMarker': self.keyPaginaSus,
			'showAllServices': self.keyRosu,
			'showSatellites': self.keyVerde,
			'showProviders': self.keyGalben,
			'showFavourites': self.keyAlbastru,
		}, -1)

		self.timerSemn = eTimer()
		self.timerSemn.callback.append(self._miscaSemn)
		self.pasSemn = 0
		# rezultatul cautarii fisierelor .ipk (fir separat) se ia de aici, din firul principal
		self.timerCautare = eTimer()
		self.timerCautare.callback.append(self._verificaCautari)
		# o instalare, o stergere, o sursa sau o lista facute din pagina web (sau de alt program) schimba fisierele opkg:
		# ecranul se uita din cand in cand la semnul lor si, la intoarcerea in el, imediat (_verificaSchimbari)
		self.semnCatalog = None
		self.timerSchimbari = eTimer()
		self.timerSchimbari.callback.append(self._verificaSchimbari)
		self.timerIntoarcere = eTimer()
		self.timerIntoarcere.callback.append(self._verificaSchimbari)

		self.onLayoutFinish.append(self._pregateste)
		self.onFirstExecBegin.append(self._avertismente)
		self.onShow.append(self._laAratare)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ pregatire

	def _pregateste(self):
		self.c = dict((k, _culoare(k)) for k in CULORI)
		fontTitlu, self.inaltime = _font('HdsExtensiiTitlu', 'Regular', 32, 96)
		fontText = _font('HdsExtensiiText', 'Regular', 26)[0]
		fontInsigna = _font('HdsExtensiiInsigna', 'Regular', 22)[0]
		fontMic = _font('HdsExtensiiMic', 'Regular', 24)[0]
		fontFila, self.inaltimeFile = _font('HdsExtensiiFila', 'Regular', 28, 64)
		self.marimeFila = int(28 * _factor())
		try:
			import skin
			if 'HdsExtensiiFila' in skin.fonts:
				self.marimeFila = skin.fonts['HdsExtensiiFila'][1]
		except Exception:
			pass
		l = self['lista']
		l.l.setFont(0, fontTitlu)
		l.l.setFont(1, fontText)
		l.l.setFont(2, fontInsigna)
		l.l.setFont(3, fontMic)
		l.l.setItemHeight(self.inaltime)
		l.l.setBuildFunc(self._rand)
		l.onSelectionChanged.append(self._laSchimbare)
		f = self['file']
		f.l.setFont(0, fontFila)
		f.l.setItemHeight(self.inaltimeFile)
		f.selectionEnabled(False)
		try:
			self.latime = l.instance.size().width()
			self.latimeFile = f.instance.size().width()
		except Exception:
			self.latime, self.latimeFile = int(1100 * _factor()), int(1712 * _factor())
		try:
			self.pozSemn = self['semn'].instance.position()
			self.latimePista = self['pista'].instance.size().width()
			self.latimeSemn = self['semn'].instance.size().width()
		except Exception:
			self.pozSemn = None
		# descrierea din dreapta: locul ei din skin (cel mai de jos) si inceputul randurilor de detalii de deasupra ei,
		# ca sa urce sub ultimul rand aratat (_asazaDescrierea)
		try:
			d, e = self['dDescriere'].instance, self['dEtichete'].instance
			self.locDescriere = (d.position().x(), d.position().y(), d.size().width(), d.size().height(), e.position().y())
		except Exception:
			self.locDescriere = None
		self['semn'].hide()
		self['pista'].hide()
		self._incarca()
		ids = [i for i, _e, _n in self.file]
		if self.filaInitiala in ids:
			self.fila = ids.index(self.filaInitiala)
		self._arataFila()
		self._descarcaAutomat()
		self.timerSchimbari.start(PAS_SCHIMBARI, False)

	def _avertismente(self):
		if plugins.warnings:
			text = _t('Unele extensii nu au putut porni:') + '\n'
			for (nume, eroare) in plugins.warnings[:6]:
				text += '%s (%s)\n' % (nume, P._curat(str(eroare), 80))
			plugins.resetWarnings()
			self.session.open(MessageBox, text=text.strip(), type=MessageBox.TYPE_WARNING)

	def _laInchidere(self):
		self.timerSemn.stop()
		self.timerSchimbari.stop()
		self.timerIntoarcere.stop()
		self._opresteDescrierea()
		# o cautare de fisiere neterminata isi termina firul singura (HdsPachete._cautari); rezultatul ei nu mai e asteptat
		self.timerCautare.stop()
		self.cautareFisiere = self.cautareRetea = None
		d, self.descarca = self.descarca, None
		if d is not None:
			d.removeCallback(self._evenimentDescarcare)
			if d.isRunning():
				_pastreazaPanaLaSfarsit(d)

	# ------------------------------------------------------------ date

	def _incarca(self):
		t = time.time()
		try:
			self.catalog = P.incarca()
		except Exception as e:
			_jurnal('catalogul nu s-a putut citi: %s' % e)
			self.catalog = P.Catalog()
		self.pluginuri = list(plugins.getPlugins(PluginDescriptor.WHERE_PLUGINMENU))
		_jurnal('catalog: %d pachete, %d surse (%d cu lista), %d pluginuri, %.0f ms' % (len(self.catalog.pachete),
			len(self.catalog.configurare.surse), len(self.catalog.surse_cu_lista), len(self.pluginuri), (time.time() - t) * 1000))
		self.semnCatalog = self._semnCatalog()
		self._construiesteFile()

	def _semnCatalog(self):
		try:
			return L.semnCatalog(self.catalog)
		except Exception as e:
			_jurnal('semnul fisierelor opkg: %s' % e)
			return None

	def _laAratare(self):
		"""La intoarcerea in ecran (dupa o extensie deschisa, o tastatura, o intrebare): ce s-a schimbat intre timp se
		vede pe loc. Prin ceas (0 ms): cand se inchide ecranul instalarii, raspunsul lui (_dupaActiune) vine dupa aratare
		si reciteste el catalogul, deci ceasul nu-l mai citeste a doua oara."""
		if self.semnCatalog is not None:
			self.timerIntoarcere.start(0, True)

	def _verificaSchimbari(self):
		"""Din firul principal (eTimer): daca fisierele opkg s-au schimbat de cand s-a citit catalogul (o instalare, o
		stergere, o sursa sau o lista facute din pagina web sau de alt program), catalogul se citeste din nou; fila si randul
		raman. Nu cat ruleaza o lucrare opkg sau o descarcare a listei (fisierele sunt pe jumatate scrise, iar sfarsitul
		lor schimba semnul inca o data) si nici cat alt ecran e deasupra (atunci la intoarcere, _laAratare)."""
		if self.semnCatalog is None or getattr(self.session, 'current_dialog', self) is not self:
			return
		if self.descarca is not None or L.lucrareInCurs() or L.descarcareInCurs():
			return
		semn = self._semnCatalog()
		if semn is None or semn == self.semnCatalog:
			return
		_jurnal('fisierele opkg s-au schimbat (pagina web sau alt program): catalogul se citeste din nou')
		# un mesaj de asteptare ("Altă instalare rulează acum") nu mai e adevarat
		self.mesajStare = ''
		self._incarca()
		self._arataFila()

	def _construiesteFile(self):
		idCurent = self.file[self.fila][0] if self.file and self.fila < len(self.file) else None
		file = []
		if self.cautare:
			file.append(('cautare', '„%s”' % self.cautare, len(self._randuriCautare())))
		file += L.file(self.catalog, len(self.pluginuri) + len(self._dupaRepornire()))
		file.append(('fisiere', _t('Din fișier'), len(self.fisiere) + len(self.fisiereRetea or ()) if self.fisiere is not None else None))
		file.append(L.filaSurse(self.catalog))
		self.file = file
		ids = [i for i, _e, _n in file]
		if idCurent in ids:
			self.fila = ids.index(idCurent)
		else:
			self.fila = min(self.fila, len(file) - 1)

	def _idFila(self):
		return self.file[self.fila][0] if self.file else 'instalate'

	def _pachetPlugin(self, plugin):
		return L.pachetPlugin(self.catalog, plugin)

	def _randuriCautare(self):
		return L.randuriCautare(self.catalog, self.pluginuri, self.cautare)

	def _randuriFila(self, fila):
		if fila == 'fisiere':
			if self.fisiere is None and self.cautareFisiere is None:
				self._cautaFisiere()
			# cele de pe stick si disc, apoi cele din retea, apoi randul care porneste cautarea in retea
			rez = [('fisier', f, None) for f in (self.fisiere or []) + (self.fisiereRetea or [])]
			if self.locuriRetea:
				rez.append(('retea', None, None))
			return rez
		return L.randuri(self.catalog, fila, self.pluginuri, plugins, self.cautare)

	def _dupaRepornire(self):
		"""pachetele instalate care au un plugin inca neincarcat (instalat acum, porneste dupa repornirea interfetei)"""
		return L.dupaRepornire(self.catalog, plugins)

	# ------------------------------------------------------------ fisierele .ipk, cautate in fundal

	def _cautaFisiere(self, retea=False):
		"""porneste cautarea fisierelor .ipk intr-un fir separat (sau se leaga de cea care ruleaza deja); inainte rula
		in firul interfetei, care statea pe loc cat citea stickul, discul si dosarele de retea. Rezultatul il ia
		_verificaCautari. Fara retea, locurile de retea sunt sarite; `retea`: numai in ele, cerut de utilizator."""
		if retea:
			if self.cautareRetea is None:
				self.cautareRetea = P.cautare_ipk(list(self.locuriRetea))
		elif self.cautareFisiere is None:
			self.cautareFisiere = P.cautare_ipk()
		self.anuntatLent = False
		if not self.timerCautare.isActive():
			self.timerCautare.start(PAS_CAUTARE, False)
		self._semn()

	def _verificaCautari(self):
		"""din firul principal (eTimer), cat timp se asteapta o cautare: ia rezultatul cand firul a terminat"""
		gata = False
		c = self.cautareFisiere
		if c is not None and c.gata:
			self.cautareFisiere = None
			self.fisiere, self.fisiereTaiate, self.locuriRetea = c.fisiere, c.taiat, c.locuri_retea
			_jurnal('fisiere .ipk: %d%s in %.0f ms (fir separat); locuri de retea sarite: %s%s' % (len(c.fisiere),
				' (taiate)' if c.taiat else '', c.durata * 1000, ', '.join(c.locuri_retea) or 'niciunul',
				'; eroare: %s' % c.eroare if c.eroare else ''))
			gata = True
		c = self.cautareRetea
		if c is not None and c.gata:
			self.cautareRetea = None
			self.fisiereRetea = c.fisiere
			_jurnal('fisiere .ipk in retea (%s): %d in %.0f ms%s' % (', '.join(c.retea or ()), len(c.fisiere),
				c.durata * 1000, '; eroare: %s' % c.eroare if c.eroare else ''))
			gata = True
		asteptate = [c for c in (self.cautareFisiere, self.cautareRetea) if c is not None]
		if not asteptate:
			self.timerCautare.stop()
		elif not self.anuntatLent and any(P._ceas() - c.pornit > CAUTARE_LENTA for c in asteptate):
			# textele spun acum ca un loc raspunde greu
			self.anuntatLent = True
			gata = True
		if gata:
			if self.mesajStare == _t(MESAJ_CAUTA_FISIERE) and self.cautareFisiere is None or \
					self.mesajStare == _t(MESAJ_CAUTA_RETEA) and self.cautareRetea is None:
				self.mesajStare = ''          # cautarea de care vorbea s-a terminat
			self._arataFisiereGasite()

	def _arataFisiereGasite(self):
		self._semn()
		fel, obj, _x = self._selectat() if self._idFila() == 'fisiere' else (None, None, None)
		self._construiesteFile()
		if self._idFila() != 'fisiere':
			# doar numarul de pe fila; randul ales in fila deschisa nu se misca
			self._deseneazaFile()
			return
		randuri = self._randuriFila('fisiere')
		i = None
		if fel == 'retea' and self.fisiereRetea and self.cautareRetea is None:
			# cautarea in retea s-a terminat cu randul ei ales: primul fisier gasit acolo
			i = next((k for k, r in enumerate(randuri) if r[0] == 'fisier' and r[1].retea), None)
		elif fel == 'retea':
			i = next((k for k, r in enumerate(randuri) if r[0] == 'retea'), None)
		elif fel == 'fisier':
			# acelasi fisier, dupa o cautare din nou (albastru, dupa o instalare)
			i = next((k for k, r in enumerate(randuri) if r[0] == 'fisier' and r[1].cale == obj.cale), None)
		if i is not None:
			self.pozitii['fisiere'] = i
		self._arataFila()

	def _sursa(self, nume):
		"""(eticheta scurta, adresa, e HD Satelit) a unei surse din configurare"""
		return L.sursa(self.catalog, nume)

	def _sursaPachet(self, p):
		return L.sursaPachet(self.catalog, p)

	# ------------------------------------------------------------ desen: file

	def _latimeFila(self, text):
		m = self.marimeFila
		return max(int(m * 4), int(len(text) * m * 0.56) + int(m * 1.6))

	def _deseneazaFile(self):
		c = self.c
		h = self.inaltimeFile
		w = self.latimeFile
		margine = max(4, h // 8)
		hp = h - 2 * margine
		chenar = max(2, int(3 * _factor()))
		spatiu = max(8, int(self.marimeFila * 0.45))
		sageata = int(self.marimeFila * 1.2)
		texte = []
		for fid, eticheta, numar in self.file:
			texte.append(eticheta if numar is None or fid == 'cautare' else '%s  %d' % (eticheta, numar))
		# decalajul: fila aleasa trebuie sa se vada intreaga
		start = min(self.decalajFile, self.fila)
		while True:
			x = sageata if start > 0 else 0
			ultima = start - 1
			for k in range(start, len(texte)):
				lat = self._latimeFila(texte[k])
				rezerva = sageata if k < len(texte) - 1 else 0
				if x + lat + rezerva > w and k > start:
					break
				x += lat + spatiu
				ultima = k
			if self.fila <= ultima or start >= self.fila:
				break
			start += 1
		self.decalajFile = start
		e = [None]
		x = 0
		if start > 0:
			e.append(MultiContentEntryText(pos=(0, 0), size=(sageata, h), font=0, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER,
				text='<', color=c['eticheta'], color_sel=c['eticheta']))
			x = sageata
		for k in range(start, ultima + 1):
			lat = self._latimeFila(texte[k])
			activa = k == self.fila
			cautare = self.file[k][0] == 'cautare'
			fundal = c['brand'] if activa else (c['celula'] if cautare else c['pista'])
			culoare = c['alb'] if activa else (c['chihlimbar'] if cautare else c['text2'])
			_pastila(e, x, margine, lat, hp, texte[k], fundal, culoare, c['alb'] if activa else None, chenar)
			x += lat + spatiu
		if ultima < len(texte) - 1:
			e.append(MultiContentEntryText(pos=(w - sageata, 0), size=(sageata, h), font=0, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER,
				text='>', color=c['eticheta'], color_sel=c['eticheta']))
		self['file'].setList([e])

	# ------------------------------------------------------------ desen: lista

	def _descriereRand(self, fel, obj, extra):
		"""(icoana, titlu, subtitlu, insigna, (fundal, text) insignei, textul mic din dreapta); randul retelei tine de
		cautarea acestui ecran, celelalte vin din Components/HdsExtensiiLucru.py (aceleasi si in pagina web)"""
		c = self.c
		if fel == 'retea':
			if self.cautareRetea is not None:
				sub = _t('Un dosar de rețea răspunde greu.') + ' ' if self.anuntatLent else ''
				return ('fisier', _t('Se caută în rețea'), sub + _t('Lista se poate folosi între timp.'), _t('Se caută'),
					(c['chihlimbar'], c['intunecat']), '')
			if self.fisiereRetea is not None:
				n = len(self.fisiereRetea)
				if not n:
					sub = _t('Niciun fișier .ipk în rețea')
				elif n == 1:
					sub = _t('Un fișier găsit în rețea')
				else:
					sub = _t('%d fișiere găsite în rețea') % n
				return ('fisier', _t('Caută din nou în rețea'), sub, None, None, '')
			return ('fisier', _t('Caută și în rețea'), _t('Dosarele de rețea nu se caută singure: pot răspunde greu.'), None, None, '')
		ic, titlu, subtitlu, insigna, culoare, mic = L.descriereRand(self.catalog, fel, obj, extra)
		return (ic, titlu, subtitlu, insigna, (c[culoare], c['intunecat']) if culoare else None, mic)

	def _rand(self, fel, obj, extra):
		c = self.c
		W = self.latime
		H = self.inaltime
		f = W / 1100.0
		cutie = min(int(88 * _factor()), H - 8)
		xIc = int(12 * f)
		xT = xIc + cutie + int(20 * f)
		dreapta = int(40 * f)          # bara de derulare se deseneaza peste marginea din dreapta a randului
		latDreapta = int(330 * f)
		latT = max(40, W - xT - latDreapta - dreapta - int(12 * f))
		ic, titlu, subtitlu, insigna, culori, mic = self._descriereRand(fel, obj, extra)
		e = [None]
		png = icoana(ic, 88)
		if png is not None:
			pw, ph = _marime_pixmap(png)
			pw, ph = min(pw, cutie), min(ph, H)
			e.append(MultiContentEntryPixmapAlphaBlend(pos=(xIc + max(0, (cutie - pw) // 2), max(0, (H - ph) // 2)),
				size=(pw, ph), png=png))
		v = RT_VALIGN_CENTER
		e.append(MultiContentEntryText(pos=(xT, int(H * 0.08)), size=(latT + (latDreapta if not insigna else 0), int(H * 0.46)), font=0,
			flags=RT_HALIGN_LEFT | v, text=titlu, color=c['text'], color_sel=c['alb']))
		e.append(MultiContentEntryText(pos=(xT, int(H * 0.54)), size=(latT + (latDreapta if not mic else 0), int(H * 0.38)), font=1,
			flags=RT_HALIGN_LEFT | v, text=subtitlu, color=c['text2'], color_sel=c['alb']))
		xD = W - dreapta - latDreapta
		if insigna:
			latI = min(latDreapta, int(len(insigna) * 13 * f) + int(36 * f))
			fundal, text = culori
			e.append(MultiContentEntryText(pos=(W - dreapta - latI, int(H * 0.14)), size=(latI, int(H * 0.36)), font=2,
				flags=RT_HALIGN_CENTER | v, text=insigna, color=text, color_sel=text, backcolor=fundal, backcolor_sel=fundal))
		if mic:
			e.append(MultiContentEntryText(pos=(xD, int(H * 0.56)), size=(latDreapta, int(H * 0.34)), font=3,
				flags=RT_HALIGN_RIGHT | v, text=mic, color=c['eticheta'], color_sel=c['alb']))
		return e

	# ------------------------------------------------------------ fila curenta

	def _arataFila(self, pastreaza=True):
		fid = self._idFila()
		# randul tinut minte se citeste inainte de setList: setList anunta o schimbare de selectie (_laSchimbare), care
		# scria in pozitii[fila noua] randul ales in fila de dinainte (prima intrare intr-o fila nu incepea sus)
		i = self.pozitii.get(fid, 0) if pastreaza else 0
		self.randuri = self._randuriFila(fid)
		self['lista'].setList(list(self.randuri))
		self._deseneazaFile()
		if self.randuri:
			i = max(0, min(i, len(self.randuri) - 1))
			self['lista'].moveToIndex(i)
			self['gol'].hide()
		else:
			self['gol'].setText(self._textGol(fid))
			self['gol'].show()
		self._laSchimbare()

	def _textGol(self, fid):
		surse = self.catalog.configurare.surse
		if fid == 'instalate':
			# 0.2.6: aici sunt numai extensiile puse de om; functiile imaginii sunt in meniu
			return _('Nu ai extensii instalate. Funcțiile imaginii sunt în meniu; extensii noi adaugi din celelalte file, cu '
				'Stânga și Dreapta.')
		if fid == 'cautare':
			return _t('Nimic nu se potrivește cu „%s”. Galben: altă căutare. EXIT: înapoi.') % self.cautare
		if fid == 'fisiere':
			if self.cautareFisiere is not None:
				return _t('Se caută fișiere .ipk pe stick și disc.') + ('\n' + _t('Un stick sau un disc răspunde greu.') if self.anuntatLent else '')
			return _t('Niciun fișier .ipk pe stick sau disc.\nCopiază pachetul pe un stick USB, apoi apasă albastru.')
		if not surse:
			return _t('Nicio sursă de pachete. Adaugă una în fila Surse.')
		return _t('Nimic aici.')

	def _selectat(self):
		cur = self['lista'].getCurrent()
		if not cur:
			return None, None, None
		return cur[0], cur[1], cur[2]

	def _laSchimbare(self):
		fid = self._idFila()
		if self.randuri:
			self.pozitii[fid] = self['lista'].getSelectionIndex()
		fel, obj, extra = self._selectat()
		self._detalii(fel, obj, extra)
		self._taste(fel, obj, extra)
		self._stare()

	def _setCuloare(self, nume, cheie):
		try:
			self[nume].instance.setForegroundColor(gRGB(self.c[cheie]))
		except Exception:
			pass

	def _detalii(self, fel, obj, extra):
		if fel == 'retea':
			# randul retelei tine de cautarea acestui ecran; celelalte vin din Components/HdsExtensiiLucru.py
			d = {'icoana': None, 'titlu': '', 'insigna': '', 'culoare': 'eticheta', 'etichete': [], 'valori': [],
				'descriere': '', 'indiciu': ''}
			locuri = self.locuriRetea[:4]
			d['etichete'] = [_t('Locul')] + [''] * (len(locuri) - 1)
			d['valori'] = locuri
			titlu, sub = self._descriereRand(fel, obj, extra)[1:3]
			if self.cautareRetea is not None:
				d.update(insigna=_t('Se caută acum'), culoare='chihlimbar', indiciu=_t('Stânga și Dreapta schimbă fila'))
			else:
				d.update(insigna=sub if self.fisiereRetea is not None else _t('Dosare de rețea'), culoare='eticheta',
					indiciu=_t('OK caută în rețea'))
			d.update(icoana='fisier', titlu=titlu, descriere=_t('Dosarele de rețea (un calculator sau un NAS) nu se caută '
				'singure: unul care nu răspunde ar ține lista pe loc. Cu OK se caută și în ele, iar lista se poate '
				'folosi între timp.'))
		else:
			d = L.detalii(self.catalog, fel, obj, extra)
		ptr = icoana(d['icoana'], 160) if d['icoana'] else None
		try:
			if ptr is not None:
				self['dIcoana'].instance.setPixmap(ptr)
				self['dIcoana'].show()
			else:
				self['dIcoana'].hide()
		except Exception:
			pass
		self['dTitlu'].setText(d['titlu'])
		# insigna are un singur rand (noWrap): intreaga, deruleaza cand nu incape (lib/gui/elabel.h)
		self['dInsigna'].setText(P._curat(d['insigna'], 400).replace('\n', ' '))
		self._setCuloare('dInsigna', d['culoare'])
		self['dEtichete'].setText('\n'.join(d['etichete']))
		self['dValori'].setText(_valoriPotrivite(self['dValori'], d['valori'], 30))
		self._asazaDescrierea(P._curat(d['descriere'], 1500))
		self['dIndiciu'].setText(d['indiciu'])

	def _asazaDescrierea(self, text):
		"""Descrierea din dreapta urca sub ultimul rand de detalii aratat (cu mai putine randuri incap mai multe randuri de
		text). Daca tot nu incape, descrierea intreaga se vede pe pagini care se schimba singure (_paginaDescriere,
		_paginaUrmatoare): prima se asaza acum, urmatoarea abia cand ii vine randul, deci o mutare a cursorului costa
		cat o singura pagina. Inaltimea se masoara cu fontul widget-ului (eLabel.calculateSize, cu randurile rupte ca pe
		ecran)."""
		w = self['dDescriere']
		inst = getattr(w, 'instance', None)
		loc = getattr(self, 'locDescriere', None)
		self._opresteDescrierea()
		if inst is None or loc is None:
			w.setText(text)
			return
		x, y, latime, inaltime, yEtichete = loc
		jos = y + inaltime
		sus = y
		try:
			sus = min(y, self._josDetalii(yEtichete))
			inst.move(ePoint(x, sus))
			inst.resize(eSize(latime, jos - sus))
		except Exception as eroare:
			print('[HdsExtensii] locul descrierii: %s' % eroare)
			sus = y

		# calculateSize da marimea literelor asezate, fara golul de deasupra primului rand: o marja mica, ca literele cu
		# coada ale ultimului rand sa nu fie taiate
		marja = max(4, int(8 * _factor()))

		def incape(t):
			inst.setText(t)
			return inst.calculateSize().height() <= jos - sus - marja
		try:
			pagina, rest = _paginaDescriere(text, incape, True)
		except Exception as eroare:
			print('[HdsExtensii] descrierea: %s' % eroare)
			pagina, rest = text, ''
		w.setText(pagina)
		if rest:
			self.paginiDescriere = [pagina]
			self.restDescriere = rest
			self.paginaDescriere = 0
			self.incapeDescriere = incape
			self._timerDescriere().start(_timpPagina(pagina), True)

	def _josDetalii(self, yEtichete):
		"""y-ul de sub randurile de detalii (etichetele si valorile lor), cu spatiul de dinaintea descrierii; fara randuri,
		inceputul lor. calculateSize da numai cutia literelor, deci un rand gol de la coada nu se numara: coloana
		etichetelor poate avea mai putine randuri cu litere decat a valorilor (locurile de retea: „Locul” si apoi
		etichete goale), de aceea se masoara amandoua si se ia marginea de jos cea mai mare."""
		if not self['dEtichete'].getText():
			return yEtichete
		jos = yEtichete + self['dEtichete'].instance.calculateSize().height()
		try:
			v = self['dValori']
			if v.getText() and v.instance is not None:
				jos = max(jos, v.instance.position().y() + v.instance.calculateSize().height())
		except (KeyError, AttributeError) as eroare:
			print('[HdsExtensii] valorile detaliilor: %s' % eroare)
		return jos + max(8, int(18 * _factor()))

	def _timerDescriere(self):
		t = getattr(self, 'timerPagini', None)
		if t is None:
			t = eTimer()
			t.callback.append(self._paginaUrmatoare)
			self.timerPagini = t
		return t

	def _opresteDescrierea(self):
		t = getattr(self, 'timerPagini', None)
		if t is not None:
			t.stop()
		self.paginiDescriere = []
		self.restDescriere = ''
		self.paginaDescriere = 0
		self.incapeDescriere = None

	def _paginaUrmatoare(self):
		"""pagina urmatoare a descrierii (din ceas): una deja asezata sau, prima data, asezata acum; dupa ultima, prima"""
		pagini = getattr(self, 'paginiDescriere', None)
		if not pagini:
			return
		k = self.paginaDescriere + 1
		if k >= len(pagini):
			if self.restDescriere and self.incapeDescriere is not None:
				try:
					pagina, self.restDescriere = _paginaDescriere(self.restDescriere, self.incapeDescriere, False)
				except Exception as eroare:
					print('[HdsExtensii] pagina descrierii: %s' % eroare)
					pagina, self.restDescriere = '', ''
				if pagina:
					pagini.append(pagina)
				else:
					k = 0
			else:
				k = 0
		if k >= len(pagini):
			k = 0
		self.paginaDescriere = k
		self['dDescriere'].setText(pagini[k])
		self._timerDescriere().start(_timpPagina(pagini[k]), True)

	def _varstaLista(self, nume):
		return L.varstaLista(self.catalog, nume)

	def _taste(self, fel, obj, extra):
		if fel == 'retea':
			rosu, verde = '', N_('Caută în rețea') if self.cautareRetea is None else ''
		else:
			rosu, verde = L.taste(self.catalog, fel, obj, extra, self.pluginuri)
		if self._idFila() == 'actualizari' and self.randuri:
			verde = N_('Actualizează toate')
		# numele tastelor raman chei (L.taste); se traduc la afisare
		self['key_red'].setText(_t(rosu))
		self['key_green'].setText(_t(verde))
		albastru = L.tastaAlbastra(self.catalog, fel, obj, extra) if fel != 'retea' else ''
		self['key_blue'].setText(_t('Caută fișiere') if self._idFila() == 'fisiere' else _t(albastru or 'Descarcă lista'))

	def _stare(self):
		if self.descarca is not None:
			return
		if self.mesajStare:
			self['stare'].setText(self.mesajStare)
			self._setCuloare('stare', self.culoareStare)
			return
		conf = self.catalog.configurare
		fid = self._idFila()
		# modul sigur (Components/HdsModSigur): pe fila extensiilor de pe receptor, fraza despre cele oprite, singura,
		# ca sa nu fie taiata (randul are noWrap)
		if fid == 'instalate':
			mod_sigur = _textModSigur()
			if mod_sigur:
				self['stare'].setText(mod_sigur)
				self._setCuloare('stare', 'chihlimbar')
				return
		parti = []
		culoare = 'eticheta'
		if fid == 'fisiere':
			if self.cautareFisiere is not None:
				parti.append(_t('Se caută fișiere .ipk pe stick și disc'))
				culoare = 'chihlimbar'
			elif self.cautareRetea is not None:
				parti.append(_t('Se caută fișiere .ipk în rețea'))
				culoare = 'chihlimbar'
			else:
				parti.append(_t('Fișiere .ipk de pe stick și disc') + (' ' + _t('și din rețea') if self.fisiereRetea is not None else ''))
			if self.anuntatLent and culoare == 'chihlimbar':
				parti.append(_t('un loc răspunde greu'))
			elif self.fisiereTaiate:
				parti.append(_t('cele mai noi %d') % len(self.fisiere or ()))
		elif fid == 'surse':
			n = L.numarSurse(self.catalog)
			parti.append(_t('%d surse') % n if n != 1 else _t('o sursă'))
		elif fid == 'cautare':
			parti.append(_t('Rezultatele căutării'))
		n_act = len(self.catalog.actualizari())
		if n_act >= 2 and fid != 'actualizari':
			parti.append(_t('MENU actualizează toate (%d)') % n_act)
		if fid not in ('fisiere',):
			if not conf.surse:
				parti.append(_t('nicio sursă de pachete'))
			elif not self.catalog.surse_cu_lista:
				parti.append(_t('lista nu a fost descărcată: albastru o descarcă'))
			else:
				parti.append(_t('lista din %s') % P.text_varsta(self.catalog.varsta_liste))
		if not opkgProgram():
			parti.append(_t('instalarea nu este disponibilă în această imagine'))
		elif getattr(plugins, 'restartRequired', False):
			self['stare'].setText(' · '.join(['Extensiile noi apar după repornirea interfeței'] + parti))
			self._setCuloare('stare', 'chihlimbar')
			return
		self['stare'].setText(' · '.join(parti))
		self._setCuloare('stare', culoare)

	# ------------------------------------------------------------ descarcarea listei (opkg update), in fundal

	def _descarcaAutomat(self):
		if not self.catalog.configurare.surse or not opkgProgram():
			return
		acum = time.time()
		# cel mult o data pe ora, si cand nu exista inca nicio lista: fara retea, altfel fiecare deschidere pornea din
		# nou opkg update si instalarea de pe stick astepta de fiecare data sfarsitul lui (albastru o porneste oricand)
		ultima = L.STARE['ultima_descarcare']
		if ultima and 0 <= acum - ultima < DESCARCARE_AUTOMATA:
			return
		self._descarcaLista(cerut=False)

	def _descarcaLista(self, cerut=True):
		if self.descarca is not None:
			return
		# ceruta de om (OK sau albastru): la sfarsit, ce contine lista (0.6.6); cea automata de la deschidere, nu
		self.descarcareCeruta = cerut
		self.inainteDescarcare = L.instantaneu(self.catalog)
		if _descarcareRamasa():
			self._mesaj(_t('Lista se descarcă deja. Încearcă din nou peste un minut.'), 'chihlimbar')
			return
		if not self.catalog.configurare.surse:
			self._mesaj(_t('Nicio sursă de pachete. Adaugă una în fila Surse.'), 'chihlimbar')
			return
		if not opkgProgram():
			self._mesaj(_t('Instalarea pachetelor nu este disponibilă în această imagine.'), 'chihlimbar')
			return
		self.mesajStare = ''
		self.liniiDescarcare = []
		self.descarca = IpkgComponent()
		self.descarca.addCallback(self._evenimentDescarcare)
		self['stare'].setText(_t('Se descarcă lista de pachete'))
		self._setCuloare('stare', 'chihlimbar')
		self._semn()
		# pornita si tinuta in Components/HdsExtensiiLucru.py (ora ultimei descarcari, jurnalul, pagina web o vede)
		L.pornesteDescarcarea(self.descarca, inainte=self.inainteDescarcare)

	def _evenimentDescarcare(self, eveniment, parametru):
		if eveniment == IpkgComponent.EVENT_LINE:
			self.liniiDescarcare.append(parametru)
		elif eveniment == IpkgComponent.EVENT_DONE:
			d, self.descarca = self.descarca, None
			if d is not None:
				d.removeCallback(self._evenimentDescarcare)
			self._semn()
			fid = self._idFila()
			self._incarca()
			ids = [i for i, _e, _n in self.file]
			if fid in ids:
				self.fila = ids.index(fid)
			if parametru == 0:
				self.mesajStare = ''
			else:
				motiv = P.motiv_eroare(self.liniiDescarcare)
				if self.catalog.surse_cu_lista:
					motiv += ' ' + _t('Se folosește lista din %s.') % P.text_varsta(self.catalog.varsta_liste)
				self._mesaj(motiv, 'chihlimbar')
			self._arataFila()
			if getattr(self, 'descarcareCeruta', False):
				self.descarcareCeruta = False
				stare = {'cod': parametru, 'motiv': '' if parametru == 0 else P.motiv_eroare(self.liniiDescarcare)}
				self.session.open(MessageBox, L.textDescarcare(self.catalog, stare, self.inainteDescarcare),
					type=MessageBox.TYPE_INFO if parametru == 0 else MessageBox.TYPE_WARNING)

	def _mesaj(self, text, culoare='eticheta'):
		self.mesajStare = text
		self.culoareStare = culoare
		self['stare'].setText(text)
		self._setCuloare('stare', culoare)

	def _semn(self):
		"""semnul care se misca sub linia de stare: cat se descarca lista sau se cauta fisiere .ipk"""
		if self.descarca is not None or self.cautareFisiere is not None or self.cautareRetea is not None:
			if not self.timerSemn.isActive():
				self._pornesteSemn()
		else:
			self._opresteSemn()

	def _pornesteSemn(self):
		if self.pozSemn is None:
			return
		self.pasSemn = 0
		self['pista'].show()
		self['semn'].show()
		self.timerSemn.start(40, False)

	def _opresteSemn(self):
		self.timerSemn.stop()
		self['semn'].hide()
		self['pista'].hide()

	def _miscaSemn(self):
		self.pasSemn += 1
		import math
		t = (1 - math.cos(self.pasSemn * math.pi / 30.0)) / 2.0     # du-te vino lin, 2,4 s
		cale = max(0, self.latimePista - self.latimeSemn)
		try:
			self['semn'].instance.move(ePoint(self.pozSemn.x() + int(cale * t), self.pozSemn.y()))
		except Exception:
			self.timerSemn.stop()

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def _muta(self, miscare):
		# mesajul din linia de stare (un refuz, un motiv) tine de randul pe care a aparut: se sterge cand alegi alt rand
		# (inainte ramanea pana la schimbarea filei). Doar la tastele de mutare: setList anunta si el o schimbare de
		# selectie (randul 0, apoi cel tinut minte), iar un mesaj pus chiar atunci (sfarsitul descarcarii) trebuie sa ramana.
		inainte = self['lista'].getSelectionIndex()
		miscare()
		if self.mesajStare and self['lista'].getSelectionIndex() != inainte:
			self.mesajStare = ''
			self._stare()

	def keyUp(self):
		self._muta(self['lista'].up)

	def keyDown(self):
		self._muta(self['lista'].down)

	def keyPaginaSus(self):
		self._muta(self['lista'].pageUp)

	def keyPaginaJos(self):
		self._muta(self['lista'].pageDown)

	def _mutaFila(self, pas):
		n = len(self.file)
		if not n:
			return
		self.fila = (self.fila + pas) % n
		self.mesajStare = ''
		self._arataFila()

	def keyLeft(self):
		self._mutaFila(-1)

	def keyRight(self):
		self._mutaFila(1)

	def keyCancel(self):
		if self._idFila() == 'cautare' or self.cautare:
			self._iesiDinCautare()
			return
		self.close()

	def keyOk(self):
		fel, obj, extra = self._selectat()
		if fel == 'plugin':
			self._pornestePlugin(obj)
		elif fel == 'pachet':
			if extra == 'repornire':
				self._reporneste()
			elif obj.actualizare:
				self._planActualizare([obj])
			elif not obj.instalat and obj.se_poate_instala:
				self._planInstalare(obj)
			elif obj.instalat:
				plugin = self._pluginPentru(obj)
				if plugin is not None:
					self._pornestePlugin(plugin)
				elif obj.dosar_plugin and getattr(plugins, 'restartRequired', False):
					self._mesaj(_t('%s pornește după repornirea interfeței.') % obj.titlu, 'chihlimbar')
				else:
					self._mesaj(_t('%s este instalat și la zi.') % obj.titlu, 'bun')
		elif fel == 'fisier':
			self._planFisier(obj)
		elif fel == 'retea':
			self._cautaInRetea()
		elif fel == 'adauga':
			self._adaugaSursa()
		elif fel in ('sursa', 'feed'):
			self._descarcaLista()

	def keyVerde(self):
		fel, obj, extra = self._selectat()
		if self._idFila() == 'actualizari' and self.randuri:
			self._planActualizare([o for f, o, _x in self.randuri if f == 'pachet' and o.actualizare])
		elif fel == 'plugin' and extra is not None and extra.actualizare:
			self._planActualizare([extra])
		else:
			self.keyOk()

	def _reporneste(self):
		# din lista (OK sau verde pe un rand „După repornire”) se intreaba intai: TryQuitMainloop intreaba doar cand
		# se inregistreaza ceva, altfel o apasare pe OK oprea televizorul pe loc
		self.session.openWithCallback(self._reporneste2, MessageBox,
			_t('Repornești interfața acum?\nExtensiile noi apar după repornire. Imaginea revine în mai puțin de un minut.'),
			type=MessageBox.TYPE_YESNO, default=False)

	def _reporneste2(self, da):
		if da:
			from Screens.Standby import TryQuitMainloop
			self.session.open(TryQuitMainloop, 3)

	def keyRosu(self):
		fel, obj, extra = self._selectat()
		if fel == 'plugin' and extra is not None and extra.se_poate_sterge:
			self._planStergere(extra)
		elif fel == 'pachet' and obj.se_poate_sterge:
			self._planStergere(obj)
		elif fel == 'sursa' and self.catalog.configurare.e_a_utilizatorului(obj[0]):
			self._stergeSursa(obj[0])

	def keyMeniu(self):
		"""Actualizeaza toate: toate pachetele instalate cu versiune noua, din orice feed; la unul singur, actualizarea
		lui (ca din randul lui)"""
		pachete = self.catalog.actualizari()
		if not pachete:
			self._mesaj(_t('Nicio actualizare de instalat.'), 'bun')
			return
		self._planActualizare(pachete)

	def keyGalben(self):
		self.session.openWithCallback(self._dupaCautare, VirtualKeyBoard, title=_t('Caută o extensie după nume'), text=self.cautare)

	def keyAlbastru(self):
		if self._idFila() == 'fisiere':
			# din nou, in fundal; lista de pana acum ramane pe ecran pana vine cea noua. Reteaua se cauta din nou doar
			# daca a fost deschisa aici
			if self.cautareFisiere is not None:
				self._mesaj(_t(MESAJ_CAUTA_FISIERE), 'chihlimbar')
				return
			self._cautaFisiere()
			if self.fisiereRetea is not None and self.cautareRetea is None and self.locuriRetea:
				self._cautaFisiere(retea=True)
			self._arataFila()
			return
		fel, obj, extra = self._selectat()
		if L.pachetCuSursa(self.catalog, fel, obj, extra) is not None:
			self._descarcaSursa(fel, obj, extra)
			return
		self._descarcaLista()

	def _descarcaSursa(self, fel, obj, extra):
		"""tasta albastra pe un pachet cu arhiva sursei (0.6.6): fereastra descarcarii (marimea si locul, intrebarea,
		progresul); o descarcare pornita deja (si din pagina web) se arata in loc de una noua"""
		d = S.curenta()
		if d is not None and S.in_lucru():
			self.session.open(HdsSursaDescarcare, d)
			return
		d, motiv = L.descarcareSursa(self.catalog, fel, obj, extra)
		if d is None:
			self._mesaj(motiv.replace('\n', ' '), 'chihlimbar')
			return
		p = L.pachetCuSursa(self.catalog, fel, obj, extra)
		self.session.open(HdsSursaDescarcare, d, P.ICOANE.get(p.categorie, 'altele') if p is not None else 'altele')

	def _cautaInRetea(self):
		if self.cautareRetea is not None:
			self._mesaj(_t(MESAJ_CAUTA_RETEA), 'chihlimbar')
			return
		self._cautaFisiere(retea=True)
		self._arataFila()

	# ------------------------------------------------------------ cautare

	def _dupaCautare(self, text):
		if text is None:
			return
		text = P._curat(text, 40).replace('\n', ' ').strip()
		if not text:
			self._iesiDinCautare()
			return
		if not self.cautare:
			self.filaDinaintea = self._idFila()
		self.cautare = text
		self.pozitii['cautare'] = 0
		self._construiesteFile()
		self.fila = 0
		self._arataFila()

	def _iesiDinCautare(self):
		self.cautare = ''
		self._construiesteFile()
		ids = [i for i, _e, _n in self.file]
		self.fila = ids.index(self.filaDinaintea) if self.filaDinaintea in ids else 0
		self.filaDinaintea = None
		self._arataFila()

	# ------------------------------------------------------------ pluginuri

	def _pluginPentru(self, p):
		return L.pluginPentru(self.pluginuri, p)

	def _pornestePlugin(self, plugin):
		try:
			plugin(session=self.session)
		except Exception as e:
			import traceback
			traceback.print_exc()
			self.session.open(MessageBox, 'Extensia „%s” nu a putut porni.\n%s' % (plugin.name, P._curat(str(e), 200)),
				type=MessageBox.TYPE_ERROR)

	# ------------------------------------------------------------ planurile pentru HdsExtensiiActiune
	# (Components/HdsExtensiiLucru.py: aceleasi planuri si pentru pagina web; ecranul da functiile lui opkgArguments
	# si opkgProgram, pe care probele le inlocuiesc)

	def _poateLucra(self):
		motiv = L.motivOcupat(self.descarca, opkgProgram)
		if motiv is not None:
			self._mesaj(*motiv)
			return False
		return True

	def _randSursa(self, p):
		return L.randSursa(self.catalog, p)

	def _notaExterne(self, pachete):
		# adresa scurtata: nota are doua randuri, iar o adresa lunga (pana la 300 de semne) impingea afara fraza
		# „Nu este verificat de HD Satelit”, care acum e si prima
		externe = ['„%s” (%s)' % (n, a) if a else '„%s”' % n for n, a in L.surseExterne(self.catalog, pachete)]
		if not externe:
			nota = L.notaFeedExtern(self.catalog, pachete)
			if nota:
				return nota
			return _t('Verificat de HD Satelit.') if self._culoareNota(pachete) == 'bun' else ''
		if len(externe) == 1:
			return _t('Nu este verificat de HD Satelit. Vine din sursa %s.') % externe[0]
		return _t('Nu sunt verificate de HD Satelit. Vin din sursele %s.') % ', '.join(externe)

	def _culoareNota(self, pachete):
		"""verde cand totul vine din sursa HD Satelit, altfel chihlimbar"""
		return L.culoareNota(self.catalog, pachete)

	def _deschide(self, plan):
		_jurnal('plan %s: %s' % (plan['fel'], plan['argumente']))
		# titlurile din lista, ca jurnalul instalarii sa spuna „DAB+ din satelit”, nu numele pachetului
		plan.setdefault('titluri', L.titluri(self.catalog))
		self.session.openWithCallback(self._dupaActiune, HdsExtensiiActiune, plan)

	def _dinPlan(self, rezultat):
		plan, eroare = rezultat
		if plan is not None:
			self._deschide(plan)
		elif eroare is not None:
			self._mesaj(*eroare)

	def _planInstalare(self, p):
		if not self._poateLucra():
			return
		self._dinPlan(L.planInstalare(self.catalog, p, opkgArguments, self._notaExterne))

	def _planActualizare(self, pachete):
		pachete = [p for p in pachete if p.actualizare and P.nume_valid(p.nume)]
		if not pachete or not self._poateLucra():
			return
		self._dinPlan(L.planActualizare(self.catalog, pachete, opkgArguments, self._notaExterne))

	def _planStergere(self, p):
		if not self._poateLucra():
			return
		self._dinPlan(L.planStergere(self.catalog, p, opkgArguments))

	def _planFisier(self, f):
		if not f.utf8:
			self._mesaj(_t('Numele fișierului nu se poate citi pe receptor. Redenumește-l fără diacritice.'), 'rau')
			return
		if not self._poateLucra():
			return
		self._dinPlan(L.planFisier(f, opkgArguments))

	def _dupaActiune(self, schimbat=False):
		if not schimbat:
			return
		# pluginurile le-a recitit deja HdsExtensiiActiune (reincarcaPluginuri), cand s-a terminat opkg; fisierele de pe
		# stick si disc se cauta din nou, in fundal (cele din retea raman: reteaua se deschide doar la cerere)
		if self.fisiere is not None:
			self._cautaFisiere()
		self.mesajStare = ''
		self._incarca()
		self._arataFila()
		if plugins.warnings:
			self._avertismente()

	# ------------------------------------------------------------ surse

	def _adaugaSursa(self):
		self.session.openWithCallback(self._numeSursa, VirtualKeyBoard,
			title=_t('Numele sursei: litere mici, cifre și -'), text='')

	def _numeSursa(self, text):
		if text is None:
			return
		nume = P.curata_nume_sursa(text)
		if not nume:
			self._mesaj(_t('Numele sursei nu poate fi gol.'), 'chihlimbar')
			return
		self.numeSursaNoua = nume
		self.session.openWithCallback(self._adresaSursa, VirtualKeyBoard,
			title=_t('Adresa sursei „%s” (http:// sau https://)') % nume, text='https://')

	def _adresaSursa(self, text):
		if text is None:
			return
		adresa = (text or '').strip()
		nume = self.numeSursaNoua
		motiv = P.verifica_sursa(nume, adresa, self.catalog.configurare.nume_surse())
		if motiv:
			self.session.open(MessageBox, motiv, type=MessageBox.TYPE_INFO)
			return
		self.adresaSursaNoua = adresa
		self.session.openWithCallback(self._confirmaSursa, MessageBox,
			_t('Adaugi sursa „%s”?\n%s\nPachetele din ea nu sunt verificate de HD Satelit.') % (nume, adresa),
			type=MessageBox.TYPE_YESNO)

	def _confirmaSursa(self, da):
		if not da:
			return
		eroare = L.adaugaSursa(self.catalog, self.numeSursaNoua, self.adresaSursaNoua)
		if eroare:
			self.session.open(MessageBox, eroare, type=MessageBox.TYPE_ERROR)
			return
		self._incarca()
		self._arataFila()
		self._descarcaLista()

	def _stergeSursa(self, nume):
		self.sursaDeSters = nume
		self.session.openWithCallback(self._confirmaStergereSursa, MessageBox,
			_t('Ștergi sursa „%s”?\nExtensiile instalate din ea rămân pe receptor.') % nume, type=MessageBox.TYPE_YESNO, default=False)

	def _confirmaStergereSursa(self, da):
		if not da:
			return
		# scoasa din fisierul utilizatorului, cu lista ei descarcata (Components/HdsExtensiiLucru.py, ca in pagina web)
		eroare = L.stergeSursa(self.catalog, self.sursaDeSters)
		if eroare:
			self.session.open(MessageBox, eroare, type=MessageBox.TYPE_ERROR)
			return
		self._incarca()
		self._arataFila()


def reincarcaPluginuri():
	"""dupa opkg: pluginurile sterse dispar imediat; cele noi apar imediat doar daca nu cer repornire (in imaginea
	aceasta, un plugin nou fara needsRestart=False apare dupa repornirea interfetei: plugins.restartRequired).
	Components/HdsExtensiiLucru.reincarcaPluginuri, cu lista pluginurilor a ecranului."""
	return L.reincarcaPluginuri(plugins)


# iesirea opkg, intreaga, pentru service: /tmp/hds-extensii.log (Components/HdsExtensiiLucru.scrieJurnal)
_scrieJurnal = L.scrieJurnal


class HdsExtensiiActiune(Screen):
	"""Confirmarea (sursa, versiunea, marimea, ce se mai instaleaza) si apoi progresul pe loc: un semn care se misca,
	pasul curent si un jurnal scurt; la sfarsit rezultatul, spus simplu. Inchiderea intoarce True daca s-a schimbat
	ceva pe receptor. Lucrarea opkg (jurnalul, raspunsul N, reincarcarea pluginurilor, textele de la sfarsit, oprirea
	dupa un minut fara raspuns) e Components/HdsExtensiiLucru.Lucrare, aceeasi si pentru pagina web; aici e numai
	desenul ei."""
	skin = """
	<screen name="HdsExtensiiActiune" position="center,center" size="900,560" title="Extensii">
		<widget name="icoana" position="20,20" size="160,160" alphatest="blend" zPosition="2" />
		<widget name="titlu" position="200,24" size="680,40" font="Regular;28" noWrap="1" transparent="1" zPosition="2" />
		<widget name="subtitlu" position="200,68" size="680,60" font="Regular;20" transparent="1" zPosition="2" />
		<widget name="etichete" position="20,190" size="220,140" font="Regular;20" foregroundColor="#00AEB9CC" noWrap="1" transparent="1" zPosition="2" />
		<widget name="valori" position="250,190" size="630,140" font="Regular;20" noWrap="1" transparent="1" zPosition="2" />
		<widget name="nota" position="20,336" size="860,56" font="Regular;20" foregroundColor="#00F5B83D" transparent="1" zPosition="2" />
		<widget name="stare" position="20,336" size="860,32" font="Regular;22" noWrap="1" transparent="1" zPosition="3" />
		<widget name="pista" position="20,374" size="860,6" backgroundColor="#002A3350" zPosition="2" />
		<widget name="semn" position="20,374" size="160,6" backgroundColor="#00F5B83D" zPosition="3" />
		<widget name="jurnal" position="20,388" size="860,100" itemHeight="25" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
		<widget name="butoane" position="20,496" size="860,56" itemHeight="56" selectionDisabled="1" scrollbarMode="showNever" transparent="1" zPosition="2" />
	</screen>"""

	def __init__(self, session, plan):
		Screen.__init__(self, session)
		self.plan = plan
		self.setTitle(plan.get('nume') or _t(TITLU))
		self.faza = 'confirmare'
		self.butoane = []
		self.buton = 0
		self.randuriJurnal = 5

		self['icoana'] = Pixmap()
		self['titlu'] = Label(plan.get('titlu', ''))
		self['subtitlu'] = Label(P._curat(plan.get('subtitlu', ''), 130))       # doua randuri
		self['etichete'] = Label('\n'.join(a for a, _b in plan.get('randuri', ())))
		self['valori'] = Label('\n'.join(P._curat(b, 80) for _a, b in plan.get('randuri', ())))
		self['nota'] = Label(plan.get('nota', ''))
		self['stare'] = Label('')
		self['pista'] = Label('')
		self['semn'] = Label('')
		self['jurnal'] = MenuList([], content=eListboxPythonMultiContent)
		self['butoane'] = MenuList([], content=eListboxPythonMultiContent)

		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions', 'DirectionActions'], {
			'ok': self.keyOk,
			'cancel': self.keyCancel,
			'green': self.keyVerde,
			'red': self.keyCancel,
			'left': self.keyLeft,
			'right': self.keyRight,
			'leftRepeated': self._nimic,
			'rightRepeated': self._nimic,
			'upRepeated': self._nimic,
			'downRepeated': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
			'upUp': self._nimic,
			'downUp': self._nimic,
			'up': self._nimic,
			'down': self._nimic,
		}, -1)

		self.lucrare = L.Lucrare(plan, program=opkgProgram, plugins=plugins, din_web=False)
		self.lucrare.asculta(self._dinLucrare)
		self.timer = eTimer()
		self.timer.callback.append(self._misca)
		self.pas = 0

		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)

	def _pregateste(self):
		self.c = dict((k, _culoare(k)) for k in CULORI)
		fontButon, self.inaltimeButoane = _font('HdsExtensiiButon', 'Regular', 30, 72)
		fontJurnal, self.inaltimeJurnal = _font('HdsExtensiiJurnal', 'Regular', 24, 34)
		self.marimeButon = int(30 * _factor())
		try:
			import skin
			if 'HdsExtensiiButon' in skin.fonts:
				self.marimeButon = skin.fonts['HdsExtensiiButon'][1]
		except Exception:
			pass
		b = self['butoane']
		b.l.setFont(0, fontButon)
		b.l.setItemHeight(self.inaltimeButoane)
		b.selectionEnabled(False)
		j = self['jurnal']
		j.l.setFont(0, fontJurnal)
		j.l.setItemHeight(self.inaltimeJurnal)
		j.selectionEnabled(False)
		try:
			self.latimeButoane = b.instance.size().width()
			self.latimeJurnal = j.instance.size().width()
			self.randuriJurnal = max(1, j.instance.size().height() // max(1, self.inaltimeJurnal))
			self.pozSemn = self['semn'].instance.position()
			self.latimePista = self['pista'].instance.size().width()
			self.latimeSemn = self['semn'].instance.size().width()
		except Exception:
			self.latimeButoane, self.latimeJurnal, self.pozSemn = 1160, 1160, None
		ptr = icoana(self.plan.get('icoana') or 'altele', 160)
		if ptr is not None:
			try:
				self['icoana'].instance.setPixmap(ptr)
			except Exception:
				pass
		if self.plan.get('nota'):
			self._setCuloare('nota', self.plan.get('notaCuloare') or 'chihlimbar')
		# valorile, acum masurate pe latimea widget-ului (in __init__ nu exista inca): randul „Fișierul” era taiat la margine
		self['valori'].setText(_valoriPotrivite(self['valori'], [b for _a, b in self.plan.get('randuri', ())], 60))
		for w in ('stare', 'pista', 'semn', 'jurnal'):
			self[w].hide()
		self._butoane([self.plan.get('buton', N_('Da')), N_('Renunță')], 1 if self.plan.get('implicitRenunta') else 0)

	def _setCuloare(self, nume, cheie):
		try:
			self[nume].instance.setForegroundColor(gRGB(self.c[cheie]))
		except Exception:
			pass

	def _butoane(self, texte, ales=0):
		self.butoane = texte
		self.buton = ales
		c = self.c
		h = self.inaltimeButoane
		m = self.marimeButon
		spatiu = int(m * 0.8)
		margine = max(4, h // 10)
		chenar = max(2, int(3 * _factor()))
		e = [None]
		x = 0
		for k, text in enumerate(texte):
			# butoanele sunt chei romanesti (comparate in keyOk / keyVerde), traduse numai la desenare
			text = _t(text)
			lat = max(int(m * 7), int(len(text) * m * 0.58) + int(m * 2.4))
			ales_ = k == self.buton
			principal = k == 0 and self.faza == 'confirmare' and not self.plan.get('implicitRenunta')
			fundal = c['brand'] if ales_ else c['pista']
			culoare = c['alb'] if ales_ else (c['text'] if principal else c['text2'])
			_pastila(e, x, margine, lat, h - 2 * margine, text, fundal, culoare, c['alb'] if ales_ else None, chenar)
			x += lat + spatiu
		self['butoane'].setList([e])
		self['butoane'].show()

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def keyLeft(self):
		if self.butoane and self.faza != 'lucru':
			self._butoane(self.butoane, max(0, self.buton - 1))

	def keyRight(self):
		if self.butoane and self.faza != 'lucru':
			self._butoane(self.butoane, min(len(self.butoane) - 1, self.buton + 1))

	def keyOk(self):
		if self.faza == 'confirmare':
			if self.buton == 0:
				self._porneste()
			else:
				self.close(False)
		elif self.faza == 'gata':
			if self.butoane and self.butoane[self.buton] == 'Repornește interfața':
				self._reporneste()
			else:
				self.close(self.lucrare.schimbat)
		else:
			self._inLucru()

	def keyVerde(self):
		if self.faza == 'confirmare':
			self._porneste()
		elif self.faza == 'gata' and 'Repornește interfața' in self.butoane:
			self._reporneste()
		elif self.faza == 'gata':
			self.close(self.lucrare.schimbat)

	def keyCancel(self):
		if self.faza == 'confirmare':
			self.close(False)
		elif self.faza == 'gata':
			self.close(self.lucrare.schimbat)
		else:
			self._inLucru()

	def _inLucru(self):
		# opkg nu se opreste la jumatatea unei instalari (starea pachetelor ar ramane amestecata); doar daca nu mai
		# scrie nimic de un minut (retea blocata), a doua apasare pe EXIT il opreste. Oprirea scrie intai randul din
		# jurnal, apoi stop() anunta sfarsitul (EVENT_DONE), deci fereastra trece in 'gata' si EXIT sau OK o inchid
		raspuns = self.lucrare.cerereOprire()
		if raspuns == 'oprit':
			return
		if raspuns == 'intreaba':
			self['stare'].setText(_t('Nu mai răspunde de un minut. Apasă EXIT încă o dată ca să oprești.'))
			self._setCuloare('stare', 'chihlimbar')
			return
		self['stare'].setText(_t('Așteaptă să se termine. Nu opri receptorul.'))
		self._setCuloare('stare', 'chihlimbar')

	def _reporneste(self):
		from Screens.Standby import TryQuitMainloop
		self.session.open(TryQuitMainloop, 3)

	# ------------------------------------------------------------ lucrul

	def _porneste(self):
		if L.lucrareInCurs():
			# o lucrare pornita din pagina web: opkg ruleaza o singura data (ar refuza oricum, cu lacatul lui)
			self['nota'].setText(_t('Altă instalare rulează acum. Așteaptă să se termine, apoi încearcă din nou.'))
			self._setCuloare('nota', 'chihlimbar')
			return
		self.faza = 'lucru'
		self['titlu'].setText(self.lucrare.titluLucru())
		self['nota'].hide()
		self['butoane'].hide()
		for w in ('stare', 'pista', 'semn', 'jurnal'):
			self[w].show()
		self['stare'].setText(_t('Pornește'))
		self._setCuloare('stare', 'chihlimbar')
		if self.pozSemn is not None:
			self.timer.start(40, False)
		self.lucrare.porneste()

	def _misca(self):
		self.pas += 1
		import math
		t = (1 - math.cos(self.pas * math.pi / 30.0)) / 2.0
		cale = max(0, self.latimePista - self.latimeSemn)
		try:
			self['semn'].instance.move(ePoint(self.pozSemn.x() + int(cale * t), self.pozSemn.y()))
		except Exception:
			self.timer.stop()

	def _dinLucrare(self, ce, *date):
		"""vestile lucrarii: ('jurnal', fel, text) si ('gata', cod)"""
		if ce == 'jurnal':
			self._adaugaJurnal(*date)
		elif ce == 'gata':
			self._gata(*date)

	def _adaugaJurnal(self, fel, text):
		"""randul nou din jurnalul scurt al lucrarii (fara repetari, cel mult 40)"""
		c = self.c
		h = self.inaltimeJurnal
		randuri = []
		# lista nu se deruleaza singura (fara selectie): se arata doar ultimele randuri care incap
		for f, t in self.lucrare.jurnal[-self.randuriJurnal:]:
			culoare = c['rau'] if f == 'eroare' else (c['bun'] if f == 'bun' else c['text2'])
			randuri.append([None, MultiContentEntryText(pos=(0, 0), size=(self.latimeJurnal, h), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=t, color=culoare, color_sel=culoare)])
		self['jurnal'].setList(randuri)
		if fel == 'pas' and self.faza == 'lucru':
			self['stare'].setText(text)
			self._setCuloare('stare', 'chihlimbar')

	def _gata(self, cod):
		self.timer.stop()
		self['semn'].hide()
		self['pista'].hide()
		self.faza = 'gata'
		# textele de la sfarsit (aceleasi si in pagina web): Components/HdsExtensiiLucru.Lucrare._gata
		r = self.lucrare.rezultat
		self['titlu'].setText(r['titlu'])
		self['stare'].setText(r['stare'])
		self._setCuloare('stare', r['culoare'])
		# dupa o instalare care cere repornire e ales Mai tarziu: un OK apasat in timpul instalarii (ca sa vezi daca
		# s-a terminat) nu reporneste interfata; repornirea ramane la Stanga + OK sau la verde
		self._butoane(r['butoane'], r['ales'])

	def _laInchidere(self):
		self.timer.stop()
		self.lucrare.lasa(self._dinLucrare)


class HdsSursaDescarcare(Screen):
	"""Descarcarea sursei deschise a unui plugin (tasta albastra "Descarcă sursa", 0.6.6): intai
	marimea si locul (pe un fir), apoi intrebarea cu marimea si locul (stick-ul are intaietate), apoi progresul (bara pe
	pista ferestrei), la sfarsit calea fisierului. Desenul e al ferestrei HdsExtensiiActiune (acelasi skin, aceleasi
	widget-uri); lucrul e Components/HdsSursaPachet.Descarcare, acelasi si pentru pagina web. EXIT in timpul descarcarii
	intreaba, apoi o opreste (fisierul partial se sterge); EXIT inainte sau dupa inchide."""
	skin = HdsExtensiiActiune.skin.replace('name="HdsExtensiiActiune"', 'name="HdsSursaDescarcare"')

	def __init__(self, session, descarcare, icoana_='altele'):
		Screen.__init__(self, session)
		self.skinName = ['HdsSursaDescarcare', 'HdsExtensiiActiune']
		self.d = descarcare
		self.icoana = icoana_
		self.setTitle(_t('Sursa pluginului %s') % descarcare.titlu)
		self.faza = None
		self.butoane = []
		self.buton = 0
		self.intrebatOprire = False

		self['icoana'] = Pixmap()
		self['titlu'] = Label('')
		self['subtitlu'] = Label('')
		self['etichete'] = Label('')
		self['valori'] = Label('')
		self['nota'] = Label('')
		self['stare'] = Label('')
		self['pista'] = Label('')
		self['semn'] = Label('')
		self['jurnal'] = MenuList([], content=eListboxPythonMultiContent)
		self['butoane'] = MenuList([], content=eListboxPythonMultiContent)

		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions', 'DirectionActions'], {
			'ok': self.keyOk,
			'cancel': self.keyCancel,
			'green': self.keyVerde,
			'red': self.keyCancel,
			'left': self.keyLeft,
			'right': self.keyRight,
			'leftRepeated': self._nimic,
			'rightRepeated': self._nimic,
			'upRepeated': self._nimic,
			'downRepeated': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
			'upUp': self._nimic,
			'downUp': self._nimic,
			'up': self._nimic,
			'down': self._nimic,
		}, -1)
		self.timer = eTimer()
		self.timer.callback.append(self._verifica)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self.timer.stop)
		# inchisa inainte de pornire (Renunta, EXIT): descarcarea nu mai e cea curenta
		self.onClose.append(lambda: S.uita(self.d))

	def _pregateste(self):
		self.c = dict((k, _culoare(k)) for k in CULORI)
		fontButon, self.inaltimeButoane = _font('HdsExtensiiButon', 'Regular', 30, 72)
		self.marimeButon = int(30 * _factor())
		try:
			import skin
			if 'HdsExtensiiButon' in skin.fonts:
				self.marimeButon = skin.fonts['HdsExtensiiButon'][1]
		except Exception:
			pass
		b = self['butoane']
		b.l.setFont(0, fontButon)
		b.l.setItemHeight(self.inaltimeButoane)
		b.selectionEnabled(False)
		try:
			self.pozSemn = self['pista'].instance.position()
			self.marimePista = self['pista'].instance.size()
		except Exception:
			self.pozSemn = self.marimePista = None
		ptr = icoana(self.icoana or 'altele', 160)
		if ptr is not None:
			try:
				self['icoana'].instance.setPixmap(ptr)
			except Exception:
				pass
		self['subtitlu'].setText(_t('Feedul: %s') % self.d.feed)
		# nota (mesajele lungi, pe mai multe randuri) creste pana la butoane: jurnalul nu se foloseste aici
		try:
			n, b = self['nota'].instance, self['butoane'].instance
			inaltime = b.position().y() - n.position().y() - max(4, int(8 * _factor()))
			if inaltime > n.size().height():
				n.resize(eSize(n.size().width(), inaltime))
		except Exception as eroare:
			print('[HdsExtensii] nota sursei: %s' % eroare)
		for w in ('jurnal', 'pista', 'semn', 'nota'):
			self[w].hide()
		self._verifica()
		self.timer.start(250, False)

	def _setCuloare(self, nume, cheie):
		try:
			self[nume].instance.setForegroundColor(gRGB(self.c[cheie]))
		except Exception:
			pass

	_butoane = HdsExtensiiActiune.__dict__['_butoane']

	@property
	def plan(self):
		# _butoane (luat din HdsExtensiiActiune) citeste plan.get('implicitRenunta')
		return {}

	def _randuri(self, randuri):
		self['etichete'].setText('\n'.join(a for a, _b in randuri))
		self['valori'].setText(_valoriPotrivite(self['valori'], [b for _a, b in randuri], 60))

	def _verifica(self):
		d = self.d
		f = d.faza
		if f != self.faza:
			self._arata(f)
		if f == 'lucru':
			if not self.intrebatOprire:
				self['stare'].setText(_t('Se descarcă: %s') % d.text_progres())
			self._bara(d.procent())

	def _bara(self, procent):
		if self.pozSemn is None or self.marimePista is None:
			return
		try:
			w = max(1, int(self.marimePista.width() * procent / 100))
			self['semn'].instance.move(ePoint(self.pozSemn.x(), self.pozSemn.y()))
			self['semn'].instance.resize(eSize(w, self.marimePista.height()))
		except Exception:
			pass

	def _nota(self, text, culoare):
		"""un mesaj lung (intrebarea, sfarsitul): in nota, pe mai multe randuri; randul de stare se ascunde"""
		self['stare'].hide()
		self['nota'].setText(text)
		self._setCuloare('nota', culoare)
		self['nota'].show()

	def _arata(self, f):
		d = self.d
		self.faza = f
		if f == 'marime':
			self['titlu'].setText(_t('Sursa pluginului %s') % d.titlu)
			self._randuri([(_t('Arhiva'), d.fisier)])
			self['stare'].setText(_t('Se află mărimea sursei și locul unde se salvează...'))
			self._setCuloare('stare', 'chihlimbar')
			self['butoane'].hide()
		elif f == 'intrebare':
			# intrebarea intreaga (cu marimea si stick-ul) in nota, pe mai multe randuri; avertismentul numai la un
			# fisier mare (de la 100 MB)
			self['titlu'].setText(_t('Sursa pluginului %s') % d.titlu)
			self._randuri(d.randuri())
			a = d.avertisment()
			self._nota(d.intrebare() + (('\n' + a) if a else ''), 'chihlimbar' if a else 'text')
			self._butoane([N_('Descarcă'), N_('Renunță')], 0)
		elif f == 'lucru':
			self['titlu'].setText(_t('Se descarcă sursa pluginului %s') % d.titlu)
			self['butoane'].hide()
			self['nota'].hide()
			self['stare'].show()
			self['pista'].show()
			self['semn'].show()
			self._setCuloare('stare', 'chihlimbar')
			self._bara(0)
		else:
			# negasit, fara-loc, gata, oprit, eroare
			self['pista'].hide()
			self['semn'].hide()
			if f == 'gata':
				self['titlu'].setText(_t('Sursa pluginului %s s-a descărcat') % d.titlu)
				self._randuri([(_t('Arhiva'), d.fisier), (_t('Mărimea'), P.marime_text(d.citit)), (_t('Locul'), d.cale)])
			text = d.text_fara_loc() if f == 'fara-loc' else d.text_sfarsit()
			self._nota(text, 'bun' if f == 'gata' else 'chihlimbar')
			self.timer.stop()
			self._butoane([N_('Închide')], 0)

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def keyLeft(self):
		if self.butoane and self.faza == 'intrebare':
			self._butoane(self.butoane, max(0, self.buton - 1))

	def keyRight(self):
		if self.butoane and self.faza == 'intrebare':
			self._butoane(self.butoane, min(len(self.butoane) - 1, self.buton + 1))

	def keyOk(self):
		if self.faza == 'intrebare':
			if self.buton == 0:
				self.d.porneste()
				self._verifica()
			else:
				self.close()
		elif self.faza == 'lucru':
			self.keyCancel()
		elif self.faza != 'marime':
			self.close()

	def keyVerde(self):
		if self.faza == 'intrebare':
			self.d.porneste()
			self._verifica()
		elif self.faza not in ('marime', 'lucru'):
			self.close()

	def keyCancel(self):
		if self.faza == 'lucru':
			if self.intrebatOprire:
				self.d.opreste()
				return
			self.intrebatOprire = True
			self['stare'].setText(_t('Apasă EXIT încă o dată ca să oprești descărcarea.'))
			self._setCuloare('stare', 'chihlimbar')
			return
		self.close()
