# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranul „Ce e nou" (MENU > Informații Sistem > Ce e nou).

Sus, ce e nou: versiunile nevăzute încă de utilizator (după o scriere nouă a receptorului, cu setări noi, versiunea
care rulează); când le-a văzut pe toate, tot versiunea care rulează. Dedesubt, „Versiunile de dinainte", de la cea
mai nouă la cea mai veche, fără cele de sus. Intrările sunt colorate după fel (nou, reparat, îmbunătățit), iar numele
felului e în limba interfeței. Datele și socotelile sunt în Components/HdsJurnalVersiuni.py (sectiuni), aceeași sursă
ca interfața web; ecranul nu citește fișierul singur.

Lista are o singură înălțime de rând pentru toate rândurile (eListbox::setItemHeight), deci un text lung nu poate
primi un rând mai înalt: textul se rupe aici, în Python, pe cuvinte, după lățimea măsurată a literelor în fontul
listei (o etichetă ascunsă, calculateSize), și fiecare rând rupt e un rând de listă. Primul rând al unei intrări e
selectabil, titlurile și rândurile de continuare nu sunt, așa că Sus/Jos sar din intrare în intrare, iar
Stânga/Dreapta schimbă pagina. Rândurile de continuare ale intrării alese primesc și ele fondul cursorului.

eListbox mută pagina numai cu câte o pagină întreagă (lib/gui/elistbox.cpp), deci paginile sunt fixe. O intrare
care nu mai încape pe pagină începe pe pagina următoare (rânduri goale până la marginea paginii), la fel antetul
unei versiuni împreună cu prima ei intrare: nicio pagină nu începe cu jumătatea unei intrări.

La închidere se ține minte versiunea care rulează, ca „ce e nou" să fie gol până la actualizarea următoare.
"""
from enigma import eListboxPythonMultiContent, eSize, getDesktop, gFont, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Components.ActionMap import HelpableActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components import HdsJurnalVersiuni as J

# id-ul cu care ecranul intra in coada de notificari (chemat o singura data, din mytest.py)
ID_NOTITA = 'hds_jurnal_versiuni'

# cat de lat e, in medie, un semn fata de marimea fontului, cand latimea literelor nu se poate masura (rezerva):
# masurat pe jurnal cu fontul skinului, randurile rupte asa umplu ~88% din coloana si niciunul nu iese din ea
LATIME_SEMN = 0.5

# culorile din skinul HDSatelit si rezerva pentru un alt skin (0xRRGGBB, opac)
CULORI = {
	'titlu': ('hdsBrandLight', 0x9FB4FF),
	'linie': ('hdsTrack', 0x2A3350),
	'eticheta': ('hdsLabel', 0xAEB9CC),
	'text': ('hdsText', 0xF2F4F8),
	'nou': ('hdsGood', 0x4FD18B),
	'reparat': ('hdsAmber', 0xF5B83D),
	'imbunatatit': ('hdsBrandLight', 0x9FB4FF),
	# fondul randului ales (acelasi cu al cursorului listei) si scrisul de pe el
	'cursor': ('hdsBrand', 0x374EA1),
	'pe_cursor': ('white', 0xFFFFFF),
}

# fereastra: skinul HDSatelit nu are (inca) un <screen name="HdsJurnalVersiuni">, deci acesta e cel folosit.
# Numerele vin din _skinImplicit(), socotite din marimea ecranului. „masura” e eticheta ascunsa cu care se masoara
# latimea literelor (fara rupere de rand, deci marimea ei nu conteaza).
SKIN = """
	<screen name="HdsJurnalVersiuni" position="%d,%d" size="%d,%d">
		<widget name="lista" position="%d,%d" size="%d,%d" itemHeight="40" scrollbarMode="showOnDemand" transparent="1" zPosition="2" />
		<widget name="stare" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget name="key_red" position="%d,%d" size="%d,%d" font="Regular;%d" backgroundColor="#009F1313" foregroundColor="#00FFFFFF" halign="center" valign="center" zPosition="2" />
		<widget name="ajutor" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget name="masura" position="0,0" size="1,1" noWrap="1" transparent="1" zPosition="0" />
	</screen>"""


def _jurnal(text):
	print('[HdsJurnalVersiuni] %s' % text)


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


def _ecran():
	try:
		d = getDesktop(0).size()
		return d.width(), d.height()
	except Exception:
		return 1920, 1080


def _factor():
	return _ecran()[0] / 1920.0


def _font(alias, marime):
	"""(gFont, marimea lui in pixeli) din aliasul skinului, daca skinul il are, altfel marimea de aici scalata.
	Trece prin skin.parseFont, ca sa se aplice si marirea de fonturi aleasa de utilizator."""
	try:
		import skin
		procent = skin.getFontScalePercent()
		if alias in skin.fonts:
			f = skin.parseFont(alias, ((1, 1), (1, 1)))
			return f, max(1, skin.fonts[alias][1] * procent // 100)
		m = max(1, int(marime * _factor()))
		# fontul HDSatelit si sub alt skin ales (skin.fontHds; cu HDSatelit ales ramane "Regular")
		return skin.parseFont('%s;%d' % (skin.fontHds('Regular'), m), ((1, 1), (1, 1))), max(1, m * procent // 100)
	except Exception:
		m = max(1, int(marime * _factor()))
		return gFont('Regular', m), m


def _limba():
	"""„ro" cand interfata e in romana, altfel „en" (intrarile jurnalului au textele in cele doua limbi)."""
	try:
		from Components.Language import language
		return 'ro' if str(language.getLanguage() or '').startswith('ro') else 'en'
	except Exception:
		return 'ro'


def _rupe(text, semne, latime_text=None, loc=0):
	"""Textul rupt pe cuvinte in randuri. Cu latime_text (functie: text -> pixeli) si loc (pixeli): cat incape
	masurat; altfel cel mult `semne` semne pe rand. Un cuvant mai lung decat un rand se taie."""
	if latime_text is not None and loc > 0:
		return _rupeMasurat(text, latime_text, loc)
	semne = max(8, int(semne))
	randuri = []
	rand = ''
	for cuvant in text.split():
		while len(cuvant) > semne:
			if rand:
				randuri.append(rand)
				rand = ''
			randuri.append(cuvant[:semne])
			cuvant = cuvant[semne:]
		if not rand:
			rand = cuvant
		elif len(rand) + 1 + len(cuvant) <= semne:
			rand = '%s %s' % (rand, cuvant)
		else:
			randuri.append(rand)
			rand = cuvant
	if rand:
		randuri.append(rand)
	return randuri or ['']


def _rupeMasurat(text, latime_text, loc):
	spatiu = latime_text(' ')
	randuri = []
	rand, lat = '', 0
	for cuvant in text.split():
		w = latime_text(cuvant)
		while w > loc:
			# un cuvant mai lat decat randul: se taie cat incape
			if rand:
				randuri.append(rand)
				rand, lat = '', 0
			n = len(cuvant)
			while n > 1 and latime_text(cuvant[:n]) > loc:
				n -= 1
			randuri.append(cuvant[:n])
			cuvant = cuvant[n:]
			w = latime_text(cuvant)
		if not rand:
			rand, lat = cuvant, w
		elif lat + spatiu + w <= loc:
			rand, lat = '%s %s' % (rand, cuvant), lat + spatiu + w
		else:
			randuri.append(rand)
			rand, lat = cuvant, w
	if rand:
		randuri.append(rand)
	return randuri or ['']


def arata_la_pornire(session):
	"""Pune ecranul in coada de notificari a enigma2, daca utilizatorul are ceva nou de vazut. Chemata din
	mytest.py, imediat dupa ce se face sesiunea. Coada e golita de interfata (InfoBarNotifications), deci ecranul
	apare abia dupa ce interfata a pornit si nu se aseaza peste asistentul de pornire.
	Intoarce True daca a pus ceva in coada. Nu arunca niciodata: pornirea receptorului nu depinde de el."""
	try:
		if not J.build_curent():
			return False           # nu se stie ce build ruleaza: nu avem fata de ce sa aratam ce e nou
		# Si la prima pornire dupa o scriere noua a receptorului (setari noi, firstrun): ecranul intra in coada,
		# iar interfata il deschide dupa asistentul de pornire. Cu setari noi nu se stie ce versiune a vazut omul,
		# deci „nou" e numai versiunea care ruleaza (HdsJurnalVersiuni.versiuni_noi).
		# vazut= se da mereu: fara el s-ar numara ca nou tot jurnalul, la fiecare pornire.
		if J.numar_intrari_noi(vazut=J.ultima_vazuta()) == 0:
			return False
		from Tools.Notifications import AddNotificationWithID
		AddNotificationWithID(ID_NOTITA, HdsJurnalVersiuni)
		return True
	except Exception as e:
		_jurnal('aratarea la pornire: %s' % e)
		return False


class HdsJurnalVersiuni(Screen, HelpableScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.skin = self._skinImplicit()
		self.setTitle(_('Ce e nou'))
		self.limba = _limba()
		self.randuri = []
		self.latime = 0
		self.pePagina = 0
		self._randuri = []              # randurile desenate, in ordinea din lista
		self._continuari = {}           # randul intai al unei intrari -> [(randul, fel, text)] ale continuarii
		self._luminata = None           # randul intai al intrarii ale carei continuari au fondul cursorului
		self._semne = {}                # latimea masurata a fiecarui semn, in pixeli

		self['lista'] = MenuList([], content=eListboxPythonMultiContent)
		self['stare'] = Label('')
		self['ajutor'] = Label(_('Sus/Jos: intrarea următoare · Stânga/Dreapta: pagina · OK sau EXIT: închide'))
		self['key_red'] = Label(_('Închide'))
		self['masura'] = Label('')

		self['actiuni'] = HelpableActionMap(self, 'OkCancelActions', {
			'ok': (self.close, _('Închide')),
			'cancel': (self.close, _('Închide')),
		}, -1)
		self['culori'] = HelpableActionMap(self, 'ColorActions', {
			'red': (self.close, _('Închide')),
		}, -1)
		self['directii'] = HelpableActionMap(self, 'DirectionActions', {
			'up': (self.keySus, _('Intrarea anterioară')),
			'down': (self.keyJos, _('Intrarea următoare')),
			'left': (self.keyStanga, _('Pagina anterioară')),
			'right': (self.keyDreapta, _('Pagina următoare')),
			'upRepeated': self.keySus,
			'downRepeated': self.keyJos,
			'leftRepeated': self.keyStanga,
			'rightRepeated': self.keyDreapta,
			# ridicarea tastei: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action"
			'upUp': self._nimic,
			'downUp': self._nimic,
			'leftUp': self._nimic,
			'rightUp': self._nimic,
		}, -1)

		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ skinul scris aici

	def _skinImplicit(self):
		"""Skinul HDSatelit nu are (inca) un <screen name="HdsJurnalVersiuni">, deci acesta e cel folosit.
		Numerele se socotesc din marimea ecranului, ca fereastra sa arate la fel si pe 1280x720. Sub tasta rosie
		ramane aceeasi margine ca sus (patru spatii p: sus, lista-stare, stare-tasta, sub tasta)."""
		l, i = _ecran()
		f = _factor()
		# marginea de sus e mai mare decat cea de jos: bara cu titlul se deseneaza DEASUPRA ferestrei
		x, y = max(16, int(l * 0.0375)), max(24, int(i * 0.056))
		L, I = l - 2 * x, i - 2 * y
		p = max(8, int(L * 0.009))
		mMic, mButon = max(14, int(24 * f)), max(14, int(26 * f))
		hStare, hButon = max(24, int(40 * f)), max(28, int(52 * f))
		hLista = I - 4 * p - hStare - hButon
		lButon = max(180, int(L * 0.16))
		yJos = p + hLista + p + hStare + p
		return SKIN % (
			x, y, L, I,
			p, p, L - 2 * p, hLista,
			p, p + hLista + p, L - 2 * p, hStare, mMic,
			p, yJos, lButon, hButon, mButon,
			p + lButon + p, yJos, L - 3 * p - lButon, hButon, mMic,
		)

	# ------------------------------------------------------------ pregatire si oprire

	def _pregateste(self):
		self.fontTitlu, mTitlu = _font('HdsJurnalTitlu', 30)
		self.fontVersiune, _m = _font('HdsJurnalVersiune', 28)
		self.fontEticheta, mEticheta = _font('HdsJurnalEticheta', 24)
		self.fontText, mText = _font('HdsJurnalText', 26)
		self.c = dict((k, _culoare(k)) for k in CULORI)
		self['masura'].hide()
		lista = self['lista']
		lista.l.setFont(0, self.fontTitlu)
		lista.l.setFont(1, self.fontVersiune)
		lista.l.setFont(2, self.fontEticheta)
		lista.l.setFont(3, self.fontText)
		self.inaltime = max(24, int(max(mTitlu, mText) * 1.45))
		lista.l.setItemHeight(self.inaltime)
		# cursorul se vede: fara el Sus/Jos ar parea taste moarte (pagina se schimba abia cand cursorul
		# nevazut iese din ea). Titlurile si randurile de continuare nu sunt selectabile, deci sar singure.
		lista.selectionEnabled(True)
		try:
			self.latime = lista.instance.size().width()
			self._randuriIntregi(lista)
			self.pePagina = lista.instance.size().height() // self.inaltime
		except Exception as e:
			_jurnal('marimea listei: %s' % e)
			self.latime = int(1744 * _factor())
			self.pePagina = 0
		# bara de derulare si marginea ei nu fac parte din latimea scrisului
		self.latime = max(200, self.latime - max(24, int(40 * _factor())))
		self.xEticheta = max(4, int(8 * _factor()))
		# coloana felului: incape cel mai lung nume de fel in limba interfetei
		etichete = [J.eticheta_tradusa(fel) for fel in J.FELURI]
		masurate = [self._latimeText(e, self.fontEticheta) for e in etichete]
		if None in masurate:
			masurate = [int(len(e) * LATIME_SEMN * mEticheta) for e in etichete]
		self.lEticheta = max(90, int(self.latime * 0.125), max(masurate) + max(8, int(16 * _factor())))
		self.xText = self.xEticheta + self.lEticheta + max(6, int(12 * _factor()))
		self.semne = max(20, int((self.latime - self.xText) / (LATIME_SEMN * max(1, mText))))
		self.semneTitlu = max(16, int(self.latime / (LATIME_SEMN * max(1, mTitlu))))
		try:
			lista.onSelectionChanged.append(self._laSchimbareaCursorului)
		except Exception as e:
			_jurnal('urmarirea cursorului: %s' % e)
		self._construieste()

	def _randuriIntregi(self, lista):
		"""Lista se scurteaza la un numar intreg de randuri: altfel eListbox deseneaza si randul care nu mai
		incape, taiat pe jumatate la marginea de jos."""
		marime = lista.instance.size()
		cate = marime.height() // self.inaltime
		if cate > 0 and cate * self.inaltime != marime.height():
			lista.instance.resize(eSize(marime.width(), cate * self.inaltime))

	def _latimeText(self, text, font):
		"""Latimea unui text in fontul dat, in pixeli, masurata cu eticheta ascunsa; None daca nu se poate."""
		if font is None:
			return None
		try:
			w = self['masura']
			w.instance.setFont(font)
			w.setText(text)
			return w.instance.calculateSize().width()
		except Exception:
			return None

	def _masuraSemnele(self, texte, font):
		"""Latimea fiecarui semn din texte (o data pe semn): latimea lui „x<semn>x” minus a lui „xx”, adica exact
		cat inainteaza semnul, si pentru spatiu. Intoarce functia text -> pixeli, sau None daca eticheta nu poate
		masura (atunci se rupe dupa numarul de semne)."""
		baza = self._latimeText('xx', font)
		if not baza:
			return None
		semne = self._semne
		for text in texte:
			for s in text:
				if s not in semne:
					w = self._latimeText('x%sx' % s, font)
					if w is None:
						return None
					semne[s] = max(0, w - baza)
		medie = max(1, int(LATIME_SEMN * 26 * _factor()))

		def latime_text(t):
			return sum(semne.get(s, medie) for s in t)
		return latime_text

	def _laInchidere(self):
		# si deschis din meniu, si aratat singur la pornire: dupa ce l-a vazut, „ce e nou" pleaca de la versiunea
		# care ruleaza acum
		try:
			J.retine_vazuta()
		except Exception as e:
			_jurnal('retinerea versiunii vazute: %s' % e)
		try:
			self['lista'].onSelectionChanged.remove(self._laSchimbareaCursorului)
		except Exception:
			pass

	# ------------------------------------------------------------ randurile

	def _construieste(self):
		versiuni = J.versiuni()
		curent = J.build_curent()
		vazut = J.ultima_vazuta()
		ruleaza = J.versiunea_care_ruleaza(versiuni, curent)
		noi = J.intrari_noi(versiuni, vazut, curent)
		sus, jos = J.sectiuni(versiuni, vazut, curent)
		r = []
		if not sus:
			r.append(('titlu', _('Jurnalul versiunilor nu este disponibil.')))
			r.append(('text', _('Fișierul cu ce s-a schimbat lipsește din această instalare.')))
		else:
			if len(sus) == 1:
				# titlul spune deja versiunea: data ei sta pe acelasi rand, fara un rand „0.1.6” dedesubt
				r.append(('titlu', _('Ce e nou în versiunea %s') % sus[0]['versiune'], sus[0].get('data') or ''))
				for x in sus[0]['intrari']:
					r.append(('intrare', x))
			else:
				r.append(('titlu', _('Ce e nou de la ultima actualizare')))
				for v in sus:
					r.append(('versiune', v))
					for x in v['intrari']:
						r.append(('intrare', x))
			if jos:
				r.append(('gol',))
				r.append(('titlu', _('Versiunile de dinainte')))
				for v in jos:
					r.append(('versiune', v))
					for x in v['intrari']:
						r.append(('intrare', x))
		self.randuri = r
		texte = [J.text(x[1], self.limba) for x in r if x[0] == 'intrare'] + [x[1] for x in r if x[0] == 'text']
		self._latimeIntrare = self._masuraSemnele(texte, getattr(self, 'fontText', None))
		self._latimeTitlu = None
		if self._latimeIntrare is not None:
			self._latimeTitlu = self._masuraSemnele([x[1] for x in r if x[0] == 'titlu'], getattr(self, 'fontTitlu', None))
		self._randuri = self._listaDesenata(r)
		self._luminata = None
		self['lista'].setList(self._randuri)
		self._laSchimbareaCursorului()
		self['stare'].setText(self._textStare(ruleaza, curent, len(noi)))

	def _textStare(self, ruleaza, curent, cateNoi):
		if ruleaza is not None:
			stare = _('Versiunea instalată: %s') % ruleaza['versiune']
			if ruleaza.get('data'):
				stare = '%s (%s)' % (stare, ruleaza['data'])
		elif curent:
			stare = _('Versiunea instalată nu este în jurnal.')
		else:
			stare = _('Versiunea instalată nu se poate citi.')
		if cateNoi:
			from Components.HdsImportSurse import ngettext
			noi = ngettext('%d intrare nouă pentru tine', '%d intrări noi pentru tine', cateNoi) % cateNoi
			stare = '%s · %s' % (stare, noi)
		return stare

	def _rupeText(self, text):
		return _rupe(text, self.semne, getattr(self, '_latimeIntrare', None), self.latime - self.xText)

	def _rupeTitlu(self, text, loc):
		tot = max(1, self.latime - self.xEticheta)
		return _rupe(text, self.semneTitlu * min(1.0, loc / float(tot)), getattr(self, '_latimeTitlu', None), loc)

	def _blocuri(self, randuri):
		"""Randurile grupate in blocuri care nu se rup intre pagini: [(fel, [randuri desenate], continuari)].
		Antetul unei versiuni sta in acelasi bloc cu prima ei intrare; titlul mare, cu primul bloc de sub el."""
		blocuri = []
		lipit = []           # randuri care asteapta sa fie lipite de blocul urmator (titluri, antetul versiunii)
		for r in randuri:
			fel = r[0]
			if fel == 'gol':
				blocuri.append(('gol', [[None]], []))
			elif fel == 'titlu':
				data = r[2] if len(r) > 2 else ''
				loc = self.latime - self.xEticheta
				if data:
					loc = int(loc * 0.78)
				linii = self._rupeTitlu(r[1], loc)
				for i, linie in enumerate(linii):
					lipit.append(self._randTitlu(linie, i == len(linii) - 1, data if i == 0 else ''))
			elif fel == 'versiune':
				lipit.append(self._randVersiune(r[1]))
			elif fel == 'text':
				desenate = [self._randText(linie) for linie in self._rupeText(r[1])]
				blocuri.append(('text', lipit + desenate, []))
				lipit = []
			else:
				intrare = r[1]
				linii = self._rupeText(J.text(intrare, self.limba))
				desenate = [self._randIntrare(intrare['fel'], linie, i == 0) for i, linie in enumerate(linii)]
				continuari = [(i, intrare['fel'], linie) for i, linie in enumerate(linii) if i > 0]
				blocuri.append(('intrare', lipit + desenate, (len(lipit), continuari)))
				lipit = []
		if lipit:
			blocuri.append(('titlu', lipit, []))
		return blocuri

	def _listaDesenata(self, randuri):
		"""Randurile listei; continuarile fiecarei intrari raman in self._continuari. Cu pagina cunoscuta, un bloc
		care nu mai incape pe pagina incepe pe pagina urmatoare; randul gol dintre parti nu se pune la inceput de
		pagina."""
		rez = []
		continuari = {}
		n = getattr(self, 'pePagina', 0)
		for fel, desenate, extra in self._blocuri(randuri):
			if fel == 'gol':
				if n and len(rez) % n == 0:
					continue
				rez.extend(desenate)
				continue
			if n and len(desenate) <= n and (len(rez) % n) + len(desenate) > n:
				rez.extend([[None]] * (n - len(rez) % n))
			if fel == 'intrare':
				inainte, cont = extra
				prim = len(rez) + inainte
				if cont:
					continuari[prim] = [(prim + i, f, t) for i, f, t in cont]
			rez.extend(desenate)
		self._continuari = continuari
		return rez

	def _randTitlu(self, text, ultim, data=''):
		c, h, w = self.c, self.inaltime, self.latime
		linie = max(2, h // 20)
		rand = [None, MultiContentEntryText(pos=(self.xEticheta, 0), size=(w - self.xEticheta, h - 2 * linie),
			font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=text, color=c['titlu'], color_sel=c['titlu'])]
		if data:
			rand.append(MultiContentEntryText(pos=(int(w * 0.6), 0), size=(w - int(w * 0.6) - self.xEticheta,
				h - 2 * linie), font=2, flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=data,
				color=c['eticheta'], color_sel=c['eticheta']))
		if ultim:
			rand.append(MultiContentEntryText(pos=(self.xEticheta, h - 2 * linie), size=(w - self.xEticheta, linie),
				font=0, text='', backcolor=c['linie'], backcolor_sel=c['linie']))
		return rand

	def _randVersiune(self, v):
		c, h, w = self.c, self.inaltime, self.latime
		lStanga = int(w * 0.6)
		return [None,
			MultiContentEntryText(pos=(self.xEticheta, 0), size=(lStanga, h), font=1,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=v['versiune'],
				color=c['titlu'], color_sel=c['titlu']),
			MultiContentEntryText(pos=(lStanga, 0), size=(w - lStanga - self.xEticheta, h), font=2,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=v.get('data') or '',
				color=c['eticheta'], color_sel=c['eticheta']),
		]

	def _randText(self, text):
		"""o insemnare de sine statatoare (nu o intrare): incepe de la marginea din stanga, sub titlu, nu din
		coloana textului intrarilor"""
		c, h, w = self.c, self.inaltime, self.latime
		return [None, MultiContentEntryText(pos=(self.xEticheta, 0), size=(w - self.xEticheta, h), font=3,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=text, color=c['text'], color_sel=c['text'])]

	def _randIntrare(self, fel, text, prima, luminat=False):
		"""Un rand al unei intrari. Pe randul ales (cursorul, fondul #374EA1) eticheta si textul se scriu alb;
		continuarile intrarii alese (luminat=True) primesc acelasi fond, ca intrarea sa se vada intreaga."""
		c, h, w = self.c, self.inaltime, self.latime
		culoare = c.get(fel, c['text'])
		# primul rand al unei intrari nu incepe cu None, deci e selectabil; continuarile si titlurile da, deci
		# Sus/Jos sar din intrare in intrare, nu din rand in rand
		rand = [fel if prima else None]
		scris = c['pe_cursor'] if luminat else c['text']
		if luminat:
			rand.append(MultiContentEntryText(pos=(0, 0), size=(w + max(24, int(40 * _factor())), h), font=3,
				text='', backcolor=c['cursor'], backcolor_sel=c['cursor']))
		if prima:
			rand.append(MultiContentEntryText(pos=(self.xEticheta, 0), size=(self.lEticheta, h), font=2,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=J.eticheta_tradusa(fel),
				color=culoare, color_sel=c['pe_cursor']))
		rand.append(MultiContentEntryText(pos=(self.xText, 0), size=(w - self.xText, h), font=3,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=text, color=scris, color_sel=c['pe_cursor']))
		return rand

	def _laSchimbareaCursorului(self):
		"""Continuarile intrarii alese primesc fondul cursorului; ale celei de dinainte, fondul obisnuit. Randurile
		se inlocuiesc pe loc in lista si se redeseneaza numai ele (invalidateEntry)."""
		lista = self['lista']
		try:
			ales = lista.getSelectionIndex()
		except Exception:
			return
		if ales == self._luminata:
			return
		schimbate = []
		for prim, luminat in ((self._luminata, False), (ales, True)):
			for i, fel, text in self._continuari.get(prim, []):
				if 0 <= i < len(self._randuri):
					self._randuri[i] = self._randIntrare(fel, text, False, luminat)
					schimbate.append(i)
		self._luminata = ales
		for i in schimbate:
			try:
				lista.l.invalidateEntry(i)
			except Exception as e:
				_jurnal('redesenarea randului %d: %s' % (i, e))
				break

	# ------------------------------------------------------------ taste

	def _nimic(self):
		pass

	def keySus(self):
		self['lista'].up()

	def keyJos(self):
		self['lista'].down()

	def keyStanga(self):
		self['lista'].pageUp()

	def keyDreapta(self):
		self['lista'].pageDown()
