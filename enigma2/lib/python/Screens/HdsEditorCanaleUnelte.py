# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranele mici ale editorului de canale de pe televizor (Screens/HdsEditorCanale.py). Doar in imaginea HDSatelit.

- HdsEditorCanaleBife: o unealta cu grupe de randuri bifabile: canalele de test (numele gol sau numai semne; numele de
  test), dublurile, canalele care nu mai exista. Nimic nu e bifat singur si nimic nu se sterge fara alegerea omului; la
  fiecare rand pozitia, frecventa, polarizarea, SID-ul si daca are imagine / sunet. Datele: partea comuna
  (s.canale_test, s.dubluri, s.referinte_moarte), aceleasi grupe ca in pagina web.
- HdsEditorCanaleFiltre: filtrele bazei noastre pentru sursa (aceleasi grupe ca la cautarea de canale, din indexul ei).
- HdsEditorCanaleCopii: copiile de siguranta (aceleasi ca in web) si intoarcerea la una.
- HdsEditorCanaleFisier: alegerea de pe stick a listei de importat (arhiva, m3u sau dosarul unei liste) sau a dosarului
  in care se scrie lista (exportul).
- HdsEditorCanaleDetalii: detaliile unui canal, in cuvinte simple.
- HdsEditorCanaleAjutor: ajutorul editorului (tasta HELP)."""
import time

from enigma import eListboxPythonMultiContent, eTimer, getDesktop, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, \
	RT_HALIGN_CENTER, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.ScrollLabel import ScrollLabel
from Tools.BoundFunction import boundFunction
from Screens import HdsEditorCanaleLogica as L
from Screens import HdsEditorCanaleLegatura as G


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


def _jurnal(text):
	print('[HdsEditorCanaleUnelte] %s' % text)


def _g(obj, nume, implicit=None):
	return getattr(obj, nume, implicit) if obj is not None else implicit


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


def _culori():
	from Screens.HdsEditorCanale import CULORI, _culoare
	return dict((k, _culoare(k)) for k in CULORI)


def _font(alias, nume, marime, inaltime):
	from Screens.HdsEditorCanale import _font as f
	return f(alias, nume, marime, inaltime)


# ---------------------------------------------------------------- textele unui rand de canal

def text_imagine_sunet(video, sunet):
	"""„imagine și sunet”, „numai sunet”, „fără imagine și sunet”, „nu se știe”."""
	if video is None and sunet is None:
		return _('imagine / sunet: nu se știe')
	if video and sunet:
		return _('imagine și sunet')
	if video:
		return _('numai imagine')
	if sunet:
		return _('numai sunet')
	return _('fără imagine și sunet')


def nume_aratat(nume):
	"""Numele gol sau numai din semne se arata ca sa se vada ce e: „(fără nume)”, „.” intre ghilimele."""
	n = nume or ''
	if not n.strip():
		return _('(fără nume)')
	if not any(ch.isalnum() for ch in n):
		return u'„%s”' % n
	return n


def detalii_rand(r):
	"""Randul de sub nume: „19,2°E · 11494 H · SID 0x1234 · imagine și sunet · în 2 buchete”; la randurile care nu
	sunt canale (buchete, marcaje, transpondere, sigle) numai ce au (pozitia, buchetul, „înainte: ...”); la un canal
	care nu mai exista, canalul gasit la care se leaga („→ Pro TV”)."""
	parti = []
	poz = _g(r, 'poz_text')
	if poz:
		parti.append(poz)
	frecv = _g(r, 'frecv')
	if frecv:
		parti.append(('%d %s' % (frecv, _g(r, 'pol', '') or '')).strip())
	sid = _g(r, 'sid')
	if sid is not None:
		parti.append('SID 0x%04X' % int(sid))
		parti.append(text_imagine_sunet(_g(r, 'are_video'), _g(r, 'are_sunet')))
	n = _g(r, 'buchete')
	if n:
		parti.append(L.ngettext('în %d buchet', 'în %d buchete', n) % n)
	if _g(r, 'buchet_nume'):
		parti.append(_g(r, 'buchet_nume'))
	inl = _g(r, 'inlocuire')
	if inl is not None:
		parti.append(u'\u2192 %s' % nume_aratat(_g(inl, 'nume', '')))
	return u' · '.join(parti)


# ---------------------------------------------------------------- uneltele cu bife

# Actiunile uneltelor: id -> (textul tastei rosii, intrebarea cu numarul (singular, plural) sau None, metoda ecranului
# HdsEditorCanaleBife care o face pe randurile bifate ale grupei). Toate trec prin partea comuna (cu anulare, nimic scris
# pana la salvare), afara de stergerea siglelor, care sterge fisierele pe loc (o spune intrebarea).
ACTIUNI = {
	'sterge_servicii': (L.N_('Șterge din receptor'), True, '_faStergeServicii'),
	'scoate_randuri': (L.N_('Șterge din buchet'), True, '_faScoateRanduri'),
	'repara': (L.N_('Repară'), True, '_faRepara'),
	'sterge_marcaje': (L.N_('Șterge marcajele bifate'), True, '_faScoateRanduri'),
	'scoate_fluxuri': (L.N_('Șterge din buchet'), True, '_faScoateRanduri'),
	'sterge_buchete': (L.N_('Șterge buchetele bifate'), True, '_faStergeBuchete'),
	'sterge_transpondere': (L.N_('Șterge transponderele bifate'), True, '_faStergeTranspondere'),
	'sterge_sigle': (L.N_('Șterge siglele bifate'), True, '_faStergeSigle'),
	'buchet_nou': (L.N_('Buchet nou din cele bifate'), False, '_faBuchetNou'),
	'readu': (L.N_('Adu înapoi cele bifate'), False, '_faReadu'),
	'alege': (L.N_('Importă buchetele bifate'), False, '_faAlege'),
}


def text_intrebare(actiune, n):
	"""Intrebarea cu numarul de dinaintea unei actiuni care sterge (regula: o confirmare cu numarul)."""
	if actiune == 'sterge_servicii':
		t = L.ngettext('Ștergi %d canal din receptor? Dispare și din toate buchetele.',
			'Ștergi %d canale din receptor? Dispar și din toate buchetele.', n)
	elif actiune == 'scoate_randuri':
		t = L.ngettext('Ștergi %d rând dublat din buchete? Canalul rămâne în lista receptorului.',
			'Ștergi %d rânduri dublate din buchete? Canalele rămân în lista receptorului.', n)
	elif actiune == 'repara':
		t = L.ngettext('Repari %d rând? Cel cu un canal găsit se leagă la el, altfel se șterge din buchet.',
			'Repari %d rânduri? Cele cu un canal găsit se leagă la el, celelalte se șterg din buchet.', n)
	elif actiune == 'sterge_marcaje':
		t = L.ngettext('Ștergi %d marcaj? Canalele rămân în buchet.', 'Ștergi %d marcaje? Canalele rămân în buchete.', n)
	elif actiune == 'scoate_fluxuri':
		t = L.ngettext('Ștergi %d flux din buchete?', 'Ștergi %d fluxuri din buchete?', n)
	elif actiune == 'sterge_buchete':
		t = L.ngettext('Ștergi %d buchet gol?', 'Ștergi %d buchete goale?', n)
	elif actiune == 'sterge_transpondere':
		t = L.ngettext('Ștergi %d transponder fără canale?', 'Ștergi %d transpondere fără canale?', n)
	else:
		t = L.ngettext('Ștergi %d siglă de pe disc? Se șterge acum, nu la salvare, și nu se poate anula.',
			'Ștergi %d sigle de pe disc? Se șterg acum, nu la salvare, și nu se pot anula.', n)
	return t % n


def _grupe_unice(f):
	"""f(sesiunea partii comune) -> o grupa; unealta are o singura grupa."""
	return lambda s, extra=None: [f(s.s)]


UNELTE = {
	'test': {
		'titlu': N_('Canale de test'),
		'explicatie': N_('Alegi tu ce se șterge din receptor: nimic nu e bifat dinainte. Un canal cu „.” poate fi un '
			'flux care pornește uneori: uită-te la frecvență și la imagine / sunet.'),
		'gol': N_('Niciun canal fără nume și niciun canal de test.'),
		'cauta': 'canale_test',
		'actiuni': {'*': 'sterge_servicii'},
	},
	'dubluri': {
		'titlu': N_('Dubluri'),
		'explicatie': N_('Același canal de două ori în același buchet. Același nume pe alt satelit nu e dublură.'),
		'gol': N_('Nicio dublură în buchete.'),
		'cauta': 'dubluri',
		# acelasi nume pe aceeasi pozitie, alt SID: numai de vazut
		'actiuni': {'in_buchet': 'scoate_randuri'},
	},
	'moarte': {
		'titlu': N_('Canale care nu mai există'),
		'explicatie': N_('Rânduri din buchete fără canal în lista receptorului. Cele cu un canal găsit se leagă la el, '
			'celelalte se șterg din buchet.'),
		'gol': N_('Toate rândurile din buchete au canalul lor.'),
		'cauta': 'referinte_moarte',
		'actiuni': {'*': 'repara'},
	},
	'verifica': {
		'titlu': N_('Verifică lista'),
		'explicatie': N_('Ce s-ar scrie altfel decât se vede, canalele fără satelit în setări, marcajele goale, HD în nume '
			'cu tip SD, serviciile de date. Nimic nu se schimbă fără bifa ta.'),
		'gol': N_('Lista e în ordine.'),
		'cauta': lambda s, extra=None: s.s.verifica(),
		'actiuni': {'fara_satelit': 'sterge_servicii', 'date': 'sterge_servicii', 'marcaje_goale': 'sterge_marcaje'},
	},
	'goale': {
		'titlu': N_('Buchete goale'),
		'explicatie': N_('Buchete fără niciun rând.'),
		'gol': N_('Niciun buchet gol.'),
		'cauta': _grupe_unice(lambda s: G.unelte().buchete_goale(s)),
		'actiuni': {'*': 'sterge_buchete'},
	},
	'transpondere': {
		'titlu': N_('Transpondere fără canale'),
		'explicatie': N_('Transpondere din lista receptorului fără niciun canal (rămase după ștergeri sau după căutări pe '
			'frecvențe goale). Nu încurcă, dar se pot șterge.'),
		'gol': N_('Niciun transponder fără canale.'),
		'cauta': _grupe_unice(lambda s: G.unelte().transpondere_goale(s)),
		'actiuni': {'*': 'sterge_transpondere'},
	},
	'fluxuri': {
		'titlu': N_('Fluxuri care nu răspund'),
		'explicatie': N_('Adresele fluxurilor din buchete se încearcă acum, câteva secunde fiecare.'),
		'gol': N_('Toate fluxurile încercate răspund.'),
		'cauta': _grupe_unice(lambda s: G.unelte().fluxuri_care_nu_raspund(s)),
		'actiuni': {'*': 'scoate_fluxuri'},
	},
	'sigle': {
		'titlu': N_('Sigle nefolosite'),
		'explicatie': N_('Siglele din dosarele de sigle care nu se potrivesc cu niciun canal din listă (nici după '
			'referință, nici după nume). Nimic nu e bifat.'),
		'gol': N_('Toate siglele sunt folosite.'),
		'cauta': lambda s, extra=None: [grupa_sigle_nefolosite(s)],
		'actiuni': {'*': 'sterge_sigle'},
	},
	'compara': {
		'titlu': N_('Compară cu lista de acum'),
		'explicatie': N_('Ce e altfel în lista de acum față de copie. Din canalele noi faci un buchet; pe cele care nu mai '
			'sunt le aduci înapoi.'),
		'gol': N_('Lista de acum e la fel ca în copie.'),
		'cauta': lambda s, extra=None: s.s.compara(extra),
		'actiuni': {'canale_noi': 'buchet_nou', 'canale_scoase': 'readu'},
	},
	'compara_import': {
		'titlu': N_('Vezi ce se schimbă'),
		'explicatie': N_('Ce s-ar schimba dacă lista din arhivă ar înlocui lista de acum.'),
		'gol': N_('Lista din arhivă e la fel ca lista de acum.'),
		'cauta': lambda s, extra=None: G.unelte().compara_import(s.s, extra),
		'actiuni': {},
	},
	'buchete_arhiva': {
		'titlu': N_('Alege buchetele'),
		'explicatie': N_('Bifează buchetele din arhivă pe care le iei. Canalele lor se adaugă în listă; celelalte buchete '
			'ale tale rămân cum sunt.'),
		'gol': N_('În arhivă nu e niciun buchet.'),
		'cauta': lambda s, extra=None: [grupa_buchete_arhiva(extra)],
		'actiuni': {'*': 'alege'},
	},
}


def grupa_sigle_nefolosite(s):
	"""Grupa siglelor nefolosite (Components/HdsEditorSigle.nefolosite, ca in web): randul = numele fisierului, sub
	el dosarul; cheie = calea."""
	from Components import HdsEditorSigle as SG
	U = G.unelte()
	refs, nume = s.refs_si_nume()
	cai = SG.nefolosite(refs, nume)
	import os
	return U.Grupa('sigle_nefolosite', _('Sigle nefolosite'), '', [U.Rand(nume=os.path.basename(c),
		poz_text=os.path.dirname(c), cheie=c) for c in cai])


def grupa_buchete_arhiva(ce):
	"""Buchetele unei arhive (ce_are_arhiva: [(id, nume, n, radio)]) ca grupa bifabila."""
	U = G.unelte()
	randuri = []
	for bid, nume, n, radio in (ce or {}).get('buchete') or ():
		randuri.append(U.Rand(nume=nume, buchet_id=bid, buchet_nume=u'%s \u00b7 %s' % (_('Radio') if radio else 'TV',
			L.text_canale(n or 0))))
	return U.Grupa('buchete', _('Buchete'), '', randuri)


class HdsEditorCanaleBife(Screen):
	skin = """
	<screen name="HdsEditorCanaleBife" position="center,center" size="1240,700" title="Canale de test">
		<widget name="explicatie" position="10,10" size="1220,60" font="Regular;20" foregroundColor="#00C9D2E3" transparent="0" zPosition="2" />
		<widget name="lista" position="10,76" size="1220,540" itemHeight="60" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget name="gol" position="20,250" size="1200,120" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="indiciu" position="10,622" size="1220,32" font="Regular;19" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="key_red" position="10,662" size="300,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="316,662" size="300,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="622,662" size="300,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
		<widget name="key_blue" position="928,662" size="302,30" font="Regular;19" backgroundColor="#003D7BE0" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, s, fel, radio=False, extra=None):
		Screen.__init__(self, session)
		self.s = s
		self.fel = fel
		self.radio = radio
		self.extra = extra                  # copia comparata, dosarul arhivei, ce are arhiva
		self.alese = None                   # buchete_arhiva: ce s-a ales
		self.date = UNELTE[fel]
		self.setTitle(_(self.date['titlu']))
		self.grupe = []
		self.bife = set()             # (grupa_id, i)
		self.restranse = set()
		self.randuri = []
		self.schimbat = False
		self.lucru = _('Se caută…')
		self.c = _culori()
		self.f = _factor()
		self['explicatie'] = Label(_(self.date['explicatie']))
		self['lista'] = MenuList([], content=eListboxPythonMultiContent)
		self['gol'] = Label('')
		self['indiciu'] = Label(self.lucru)
		self['key_red'] = Button('')
		self['key_green'] = Button(_('Selectează toată grupa'))
		self['key_yellow'] = Button(_('Restrânge grupa'))
		self['key_blue'] = Button(_('Detalii'))
		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions', 'DirectionActions', 'HdsEditorCanaleActions'], {
			'ok': self.keyOk, 'cancel': self.keyExit,
			'red': self.keyActiune, 'green': self.keyGrupa, 'yellow': self.keyRestrange, 'blue': self.keyDetalii,
			'up': boundFunction(self._muta, 'up'), 'down': boundFunction(self._muta, 'down'),
			'left': boundFunction(self._muta, 'pageUp'), 'right': boundFunction(self._muta, 'pageDown'),
			'paginaSus': boundFunction(self._muta, 'pageUp'), 'paginaJos': boundFunction(self._muta, 'pageDown'),
			'info': self.keyDetalii,
			# tastele editorului care nu au ce face aici: legate, ca jurnalul sa nu scrie unknown action
			'anuleaza': self._nimic, 'reface': self._nimic, 'listaTv': self._nimic, 'listaRadio': self._nimic,
			'tastatura': self._nimic,
		}, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self._cauta)
		self.onLayoutFinish.append(self._pregateste)

	def _nimic(self):
		pass

	def _pregateste(self):
		font, _m, self.h = _font('HdsEditorRand', 'Regular', 30, 72)
		mic, _m, _h = _font('HdsEditorMic', 'Regular', 26, 72)
		self.h = max(self.h, int(80 * self.f))
		l = self['lista']
		l.l.setFont(0, font)
		l.l.setFont(1, mic)
		l.l.setItemHeight(self.h)
		l.l.setBuildFunc(self._rand)
		try:
			self.w = l.instance.size().width()
		except Exception:
			self.w = int(1712 * self.f)
		self['gol'].hide()
		self.ceas.start(30, True)

	def _cauta(self):
		cauta = self.date['cauta']
		if isinstance(cauta, str):
			# o unealta a partii comune: varianta ei pe fir, cand o are
			fundal = getattr(self.s.s, cauta + '_fundal', None)
			if fundal is not None:
				try:
					if cauta == 'canale_test':
						fundal(self._gasite, self._eroare, radio=self.radio)
					else:
						fundal(self._gasite, self._eroare)
					return
				except Exception as e:
					_jurnal('%s_fundal: %r' % (cauta, e))
			try:
				f = getattr(self.s, cauta)
				grupe = f(self.radio) if cauta == 'canale_test' else f()
			except Exception as e:
				self._eroare(e)
				return
			self._gasite(grupe)
			return
		# celelalte: pe firul uneltelor al partii comune (numai citesc), cand se poate
		self.s.unealta(lambda: cauta(self.s, self.extra), self._gasite, self._eroare)

	def _eroare(self, e):
		_jurnal('%s: %r' % (self.fel, e))
		self.lucru = ''
		self._gasite([])
		if isinstance(e, G.Eroare) and str(e):
			self['indiciu'].setText(str(e))

	def _gasite(self, grupe):
		self.lucru = ''
		self.grupe = [g for g in (grupe or []) if _g(g, 'randuri')]
		self.bife = set(b for b in self.bife if any(_g(g, 'id') == b[0] and b[1] < len(g.randuri) for g in self.grupe))
		self._refa()

	def _refa(self, i=None):
		if i is None:
			i = self['lista'].getSelectionIndex() or 0
		randuri = []
		for g in self.grupe:
			randuri.append(('grupa', g, None))
			if _g(g, 'id') not in self.restranse:
				for k, r in enumerate(g.randuri):
					randuri.append(('rand', g, k))
		self.randuri = randuri
		self['lista'].setList([(r,) for r in randuri])
		if randuri:
			self['lista'].moveToIndex(min(i, len(randuri) - 1))
			self['gol'].hide()
		else:
			self['gol'].setText(_(self.date['gol']))
			self['gol'].show()
		self._arata()

	def _muta(self, cum):
		"""Cursorul mutat; tasta rosie spune actiunea grupei in care a ajuns."""
		getattr(self['lista'], cum)()
		self._arata()

	def _actiune(self, g):
		"""Actiunea grupei (id din ACTIUNI) sau None: grupa e numai de vazut."""
		a = self.date.get('actiuni') or {}
		return a.get(_g(g, 'id'), a.get('*'))

	def _deVazut(self, g):
		return self._actiune(g) is None

	def _grupaActiunii(self):
		"""Grupa pe care lucreaza tasta rosie: a randului ales, cand are o actiune; altfel prima grupa cu bife."""
		r = self._curent()
		if r is not None and not self._deVazut(r[1]):
			return r[1]
		for g in self.grupe:
			if any(b[0] == _g(g, 'id') for b in self.bife):
				return g
		return None

	def _arata(self):
		g0 = self._grupaActiunii()
		n = len(self._alese(g0)) if g0 is not None else 0
		if g0 is not None:
			eticheta = _(ACTIUNI[self._actiune(g0)][0])
			self['key_red'].setText(eticheta + (' (%d)' % n if n else ''))
		else:
			self['key_red'].setText('')
		n = len(self.bife)
		r = self._curent()
		g = r[1] if r else None
		if g is not None and not self._deVazut(g):
			toate = all((_g(g, 'id'), k) in self.bife for k in range(len(g.randuri)))
			self['key_green'].setText(_('Deselectează grupa') if toate else _('Selectează toată grupa'))
		else:
			self['key_green'].setText('')
		self['key_yellow'].setText((_('Arată grupa') if g is not None and _g(g, 'id') in self.restranse else
			_('Restrânge grupa')) if g is not None else '')
		self['key_blue'].setText(_('Detalii') if r and r[0] == 'rand' else '')
		if self.lucru:
			self['indiciu'].setText(self.lucru)
		elif n:
			self['indiciu'].setText(L.text_bifate(n) + u' · ' + _('OK bifează sau debifează'))
		else:
			self['indiciu'].setText(_('OK bifează sau debifează · pe titlul grupei: toată grupa'))

	def _curent(self):
		if not self.randuri:
			return None
		i = self['lista'].getSelectionIndex() or 0
		return self.randuri[i] if 0 <= i < len(self.randuri) else None

	def _rand(self, r):
		fel, g, k = r
		c = self.c
		h, w = self.h, self.w
		f = self.f
		e = [None]
		x = int(16 * f)
		if fel == 'grupa':
			e.append(MultiContentEntryText(pos=(0, int(h * 0.12)), size=(w, int(h * 0.76)), font=0, text='',
				backcolor=c['celula'], backcolor_sel=c['brand']))
			n = len(g.randuri)
			titlu = u'%s (%d)' % (_g(g, 'titlu', '') or _g(g, 'id', ''), n)
			if _g(g, 'id') in self.restranse:
				titlu = '+ ' + titlu
			e.append(MultiContentEntryText(pos=(x, 0), size=(w // 2, h), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=titlu, color=c['chihlimbar'], color_sel=c['alb'], backcolor=c['celula'], backcolor_sel=c['brand']))
			expl = _g(g, 'explicatie', '') or ''
			if self._deVazut(g):
				expl = (expl + u' · ' if expl else '') + _('numai de văzut')
			e.append(MultiContentEntryText(pos=(w // 2, 0), size=(w // 2 - x, h), font=1,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=expl, color=c['text2'], color_sel=c['alb'],
				backcolor=c['celula'], backcolor_sel=c['brand']))
			return e
		rr = g.randuri[k]
		if not self._deVazut(g):
			bifat = (_g(g, 'id'), k) in self.bife
			m = int(h * 0.3)
			lat = h - 2 * m
			e.append(MultiContentEntryText(pos=(x, m), size=(lat, lat), font=0, text='', backcolor=c['text2'],
				backcolor_sel=c['alb']))
			gros = max(2, int(lat * 0.12))
			e.append(MultiContentEntryText(pos=(x + gros, m + gros), size=(lat - 2 * gros, lat - 2 * gros), font=0,
				text='', backcolor=c['ales'] if bifat else c['fundal'], backcolor_sel=c['ales'] if bifat else c['brand']))
			x += lat + int(20 * f)
		e.append(MultiContentEntryText(pos=(x, int(h * 0.06)), size=(w - x - int(16 * f), int(h * 0.5)), font=0,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=nume_aratat(_g(rr, 'nume', '')), color=c['text'],
			color_sel=c['alb']))
		e.append(MultiContentEntryText(pos=(x, int(h * 0.54)), size=(w - x - int(16 * f), int(h * 0.42)), font=1,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=detalii_rand(rr), color=c['eticheta'], color_sel=c['alb']))
		return e

	def keyOk(self):
		r = self._curent()
		if r is None or self.lucru:
			return
		fel, g, k = r
		if self._deVazut(g):
			return
		if fel == 'grupa':
			self.keyGrupa()
			return
		cheie = (_g(g, 'id'), k)
		if cheie in self.bife:
			self.bife.discard(cheie)
		else:
			self.bife.add(cheie)
		i = self['lista'].getSelectionIndex()
		self['lista'].l.invalidateEntry(i)
		self['lista'].down()
		self._arata()

	def keyGrupa(self):
		r = self._curent()
		if r is None or self.lucru or self._deVazut(r[1]):
			return
		g = r[1]
		chei = [(_g(g, 'id'), k) for k in range(len(g.randuri))]
		if all(c in self.bife for c in chei):
			self.bife.difference_update(chei)
		else:
			self.bife.update(chei)
		self['lista'].l.invalidate()
		self._arata()

	def keyRestrange(self):
		r = self._curent()
		if r is None:
			return
		gid = _g(r[1], 'id')
		if gid in self.restranse:
			self.restranse.discard(gid)
		else:
			self.restranse.add(gid)
		# cursorul pe titlul grupei
		i = 0
		for j, rr in enumerate(self.randuri):
			if rr[0] == 'grupa' and _g(rr[1], 'id') == gid:
				i = j
				break
		self._refa(i)

	def keyDetalii(self):
		r = self._curent()
		if r is None or r[0] != 'rand':
			return
		rr = r[1].randuri[r[2]]
		srv = None
		try:
			srv = self.s.serviciu(_g(rr, 'ref')) if _g(rr, 'ref') else None
		except Exception:
			srv = None
		self.session.open(HdsEditorCanaleDetalii, srv or rr, self.s)

	def _alese(self, grupa=None):
		"""Randurile bifate (numai ale grupei date, cand e data)."""
		alese = []
		for g in self.grupe:
			if grupa is not None and g is not grupa:
				continue
			for k, rr in enumerate(g.randuri):
				if (_g(g, 'id'), k) in self.bife:
					alese.append(rr)
		return alese

	def keyActiune(self):
		g = self._grupaActiunii()
		alese = self._alese(g) if g is not None else []
		n = len(alese)
		if not n or self.lucru:
			return
		actiune = self._actiune(g)
		eticheta, intreaba, metoda = ACTIUNI[actiune]
		if not intreaba:
			getattr(self, metoda)(alese)
			return
		text = text_intrebare(actiune, n)
		self.session.openWithCallback(boundFunction(self._raspuns, metoda, alese), MessageBox, text,
			MessageBox.TYPE_YESNO, default=False)

	def _raspuns(self, metoda, alese, da):
		if da:
			getattr(self, metoda)(alese)

	def _fa(self, functie, *a):
		"""O actiune pe partea comuna, apoi unealta cauta din nou (indicii randurilor s-au schimbat)."""
		try:
			functie(*a)
		except G.Eroare as e:
			self['indiciu'].setText(str(e) or _('Nu se poate.'))
			return False
		except Exception as e:
			_jurnal('%s: %r' % (self.fel, e))
			self['indiciu'].setText(_('Nu se poate.'))
			return False
		self.schimbat = True
		self.bife = set()
		self.lucru = _('Se caută…')
		self._arata()
		self.ceas.start(30, True)
		return True

	def _faStergeServicii(self, alese):
		self._fa(self.s.sterge_servicii, [_g(r, 'ref') for r in alese if _g(r, 'ref')])

	def _faRepara(self, alese):
		self._fa(self.s.repara_moarte, alese)

	def _faScoateRanduri(self, alese):
		"""Randuri din buchete (dubluri, marcaje goale, fluxuri): o singura scoatere pe buchet, cu indicii de acum
		(dupa id-ul randului, cand il are; altfel indicii de la cautare)."""
		pe_buchete = {}
		for r in alese:
			pe_buchete.setdefault(_g(r, 'buchet_id'), []).append(r)

		def fa():
			for bid, randuri in pe_buchete.items():
				if bid is None:
					continue
				ids = [_g(r, 'id_intrare') for r in randuri if _g(r, 'id_intrare') is not None]
				ind = self.s.indici(bid, ids) if ids and len(ids) == len(randuri) else \
					[_g(r, 'indice') for r in randuri if _g(r, 'indice') is not None]
				if ind:
					self.s.scoate(bid, sorted(ind))
		self._fa(fa)

	def _faStergeBuchete(self, alese):
		def fa():
			for r in alese:
				if _g(r, 'buchet_id'):
					self.s.sterge_buchet(_g(r, 'buchet_id'))
		self._fa(fa)

	def _faStergeTranspondere(self, alese):
		chei = []
		for r in alese:
			try:
				chei.append(tuple(int(p, 16) for p in (_g(r, 'cheie') or '').split(':')))
			except ValueError:
				pass
		self._fa(self.s.sterge_transpondere, chei)

	def _faStergeSigle(self, alese):
		def fa():
			from Components import HdsEditorSigle as SG
			SG.sterge_nefolosite([_g(r, 'cheie') for r in alese if _g(r, 'cheie')])
		self._fa(fa)

	def _faBuchetNou(self, alese):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(boundFunction(self._numeBuchetNou, alese), VirtualKeyBoard,
			title=_('Numele buchetului nou'), text='')

	def _numeBuchetNou(self, alese, nume=None):
		nume = (nume or '').strip()
		refs = [_g(r, 'ref') for r in alese if _g(r, 'ref')]
		if nume and refs:
			self._fa(lambda: self.s.buchet_nou(nume, radio=self.radio, refs=refs))

	def _faReadu(self, alese):
		self._fa(self.s.readu_din_copie, self.extra, [_g(r, 'cheie') for r in alese if _g(r, 'cheie')])

	def _faAlege(self, alese):
		self.alese = [_g(r, 'buchet_id') for r in alese if _g(r, 'buchet_id')]
		self.close(self.alese)

	def keyExit(self):
		self.close(None if self.fel == 'buchete_arhiva' else self.schimbat)


# ---------------------------------------------------------------- filtrele sursei

# grupul filtrelor editorului (starea canalului in lista), in plus fata de cele ale bazei noastre; cheia lui nu e a
# indexului cautarii (HdsEditorCanale._cautare il scoate inainte de Index.filtreaza)
FILTRU_EDITOR = L.FILTRU_EDITOR
FILTRE_EDITOR = (('noi', L.N_('Noi')), ('blocate', L.N_('Blocate')), ('ascunse', L.N_('Ascunse')),
	('nicaieri', L.N_('În niciun buchet')), ('fara_sigla', L.N_('Fără siglă')), ('hd_sd', L.N_('HD în nume, tip SD')))


class HdsEditorCanaleFiltre(Screen):
	"""Filtrele bazei noastre (Components/HdsIndexCanale: tip, rezolutie, acces, sistem, codare, pozitie, piste) si,
	primul rand, ale editorului (noi, blocate, ascunse, in niciun buchet, fara sigla, HD in nume cu tip SD), cate un
	rand pe grup: Stanga / Dreapta aleg optiunea, OK o porneste sau o opreste. Se intorc la iesire (EXIT sau verde), ca
	dictionar {grup: set(valori)}. numara(selectie) -> cate canale raman (editorul il da; altfel numai indexul)."""
	skin = """
	<screen name="HdsEditorCanaleFiltre" position="center,center" size="1240,700" title="Filtre">
		<widget name="lista" position="10,10" size="1220,600" itemHeight="50" selectionDisabled="1" scrollbarMode="showNever" transparent="0" zPosition="2" />
		<widget name="indiciu" position="10,622" size="900,32" font="Regular;19" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="numar" position="920,622" size="310,32" font="Regular;22" foregroundColor="#00F5B83D" halign="right" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="key_red" position="10,662" size="300,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="316,662" size="300,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, index, selectie, radio=False, numara=None):
		Screen.__init__(self, session)
		self.setTitle(_('Filtre'))
		self.index = index
		self.numara = numara
		self.selectie = dict((g, set(v)) for g, v in (selectie or {}).items())
		try:
			from Components import HdsIndexCanale as X
			self.X = X
			self.grupuri = [g for g in index.grupuri_vizibile() if index.optiuni.get(g)]
		except Exception as e:
			_jurnal('filtrele: %r' % (e,))
			self.X = None
			self.grupuri = []
		self.grupuri.insert(0, FILTRU_EDITOR)
		self.rand = 0
		self.coloana = dict((g, 0) for g in self.grupuri)
		self.c = _culori()
		self.f = _factor()
		self['lista'] = MenuList([], content=eListboxPythonMultiContent)
		self['indiciu'] = Label(_('Sus / Jos: grupul · Stânga / Dreapta: opțiunea · OK o pornește sau o oprește'))
		self['numar'] = Label('')
		self['key_red'] = Button(_('Șterge filtrele'))
		self['key_green'] = Button(_('Gata'))
		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions', 'DirectionActions'], {
			'ok': self.keyOk, 'cancel': self.keyGata, 'green': self.keyGata, 'red': self.keySterge,
			'up': boundFunction(self.keyRand, -1), 'down': boundFunction(self.keyRand, 1),
			'left': boundFunction(self.keyOptiune, -1), 'right': boundFunction(self.keyOptiune, 1),
			'upRepeated': boundFunction(self.keyRand, -1), 'downRepeated': boundFunction(self.keyRand, 1),
			'leftRepeated': boundFunction(self.keyOptiune, -1), 'rightRepeated': boundFunction(self.keyOptiune, 1),
		}, -1)
		self.onLayoutFinish.append(self._pregateste)

	def _pregateste(self):
		self.font, self.marime, self.h = _font('HdsCautareRand', 'Regular', 28, 50)
		self.fontEt, _m, _h = _font('HdsCautareEticheta', 'Regular', 24, 50)
		l = self['lista']
		l.l.setFont(0, self.font)
		l.l.setFont(1, self.fontEt)
		l.l.setItemHeight(self.h)
		try:
			l.selectionEnabled(False)
			self.w = l.instance.size().width()
		except Exception:
			self.w = int(1712 * self.f)
		self._deseneaza()

	def _eticheta(self, g, v, e):
		try:
			return self.index.eticheta_titlu(g, e) if g in ('lsunet', 'lsub') else e
		except Exception:
			return e

	def _optiuni(self, g):
		"""[(valoare, eticheta, numar)] ale unui grup: ale editorului sau ale indexului cautarii."""
		if g == FILTRU_EDITOR:
			return [(v, _(t), None) for v, t in FILTRE_EDITOR]
		return self.index.optiuni.get(g, ())

	def _titlu(self, g):
		if g == FILTRU_EDITOR:
			return _('În listă')
		try:
			return self.X.titlu(g)
		except Exception:
			return g

	def _deseneaza(self):
		c = self.c
		h = self.h
		f = self.f
		latTitlu = int(250 * f)
		randuri = []
		for k, g in enumerate(self.grupuri):
			e = [None]
			focus = k == self.rand
			titlu = self._titlu(g)
			e.append(MultiContentEntryText(pos=(0, 0), size=(latTitlu, h), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
				text=titlu, color=c['focus'] if focus else c['eticheta']))
			optiuni = self._optiuni(g)
			# fereastra de optiuni care se vede: cea cu focus mereu inauntru
			x = latTitlu
			lat = [int(self.marime * 0.55 * len(et) + 40 * f) for _v, et, _n in optiuni]
			start = 0
			col = self.coloana.get(g, 0)
			m2, m3, m5 = int(2 * f), int(3 * f), int(5 * f)
			while start < col and sum(lat[start:col + 1]) + 12 * f * (col - start) > self.w - latTitlu:
				start += 1
			for j in range(start, len(optiuni)):
				v, et, _n = optiuni[j]
				if x + lat[j] > self.w:
					break
				ales = v in self.selectie.get(g, ())
				pe = focus and j == col
				fundal = c['ales'] if ales else c['pista']
				culoare = c['alesText'] if ales else c['text']
				if pe:
					e.append(MultiContentEntryText(pos=(x, m2), size=(lat[j], h - 2 * m2), font=0, text='',
						backcolor=c['focus']))
					e.append(MultiContentEntryText(pos=(x + m3, m5), size=(lat[j] - 2 * m3, h - 2 * m5), font=0,
						flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=self._eticheta(g, v, et), color=culoare,
						backcolor=fundal))
				else:
					e.append(MultiContentEntryText(pos=(x, m5), size=(lat[j], h - 2 * m5), font=0,
						flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=self._eticheta(g, v, et), color=culoare,
						backcolor=fundal))
				x += lat[j] + int(12 * f)
			randuri.append(e)
		self['lista'].setList(randuri)
		if randuri:
			self['lista'].moveToIndex(self.rand)
		try:
			if self.numara is not None:
				n = self.numara(self._selectie())
			else:
				sel = dict((g, v) for g, v in self._selectie().items() if g != FILTRU_EDITOR)
				n = len(self.index.filtreaza('', sel))
			self['numar'].setText(L.text_canale(n))
		except Exception as e:
			_jurnal('numarul: %r' % (e,))

	def _selectie(self):
		return dict((g, set(v)) for g, v in self.selectie.items() if v)

	def keyRand(self, pas):
		if self.grupuri:
			self.rand = max(0, min(self.rand + pas, len(self.grupuri) - 1))
			self._deseneaza()

	def keyOptiune(self, pas):
		if not self.grupuri:
			return
		g = self.grupuri[self.rand]
		n = len(self._optiuni(g))
		self.coloana[g] = max(0, min(self.coloana.get(g, 0) + pas, n - 1))
		self._deseneaza()

	def keyOk(self):
		if not self.grupuri:
			return
		g = self.grupuri[self.rand]
		optiuni = self._optiuni(g)
		if not optiuni:
			return
		v = optiuni[min(self.coloana.get(g, 0), len(optiuni) - 1)][0]
		s = self.selectie.setdefault(g, set())
		if v in s:
			s.discard(v)
		else:
			s.add(v)
		self._deseneaza()

	def keySterge(self):
		self.selectie = {}
		self._deseneaza()

	def keyGata(self):
		self.close(self._selectie())


# ---------------------------------------------------------------- copiile de siguranta

class HdsEditorCanaleCopii(Screen):
	skin = """
	<screen name="HdsEditorCanaleCopii" position="center,center" size="1240,700" title="Copii de siguranță">
		<widget name="explicatie" position="10,10" size="1220,60" font="Regular;20" foregroundColor="#00C9D2E3" transparent="0" zPosition="2" />
		<widget name="lista" position="10,76" size="1220,540" itemHeight="60" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget name="gol" position="20,250" size="1200,120" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="3" />
		<widget name="indiciu" position="10,622" size="1220,32" font="Regular;19" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="0" zPosition="2" />
		<widget name="key_red" position="10,662" size="300,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="316,662" size="300,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="622,662" size="300,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, s):
		Screen.__init__(self, session)
		self.setTitle(_('Copii de siguranță'))
		self.s = s
		self.copii = []
		self.lucru = ''
		self.schimbat = False               # din comparatie: buchet nou sau canale aduse inapoi
		self.c = _culori()
		self.f = _factor()
		self['explicatie'] = Label(_('O copie se face singură înainte de fiecare salvare, aici și în interfața web. '
			'Întoarcerea pune întâi lista de acum într-o copie nouă.'))
		self['lista'] = MenuList([], content=eListboxPythonMultiContent)
		self['gol'] = Label('')
		self['indiciu'] = Label(_('OK: întoarce lista la copia aleasă'))
		self['key_red'] = Button(_('Înapoi'))
		self['key_green'] = Button(_('Întoarce la această copie'))
		self['key_yellow'] = Button(_('Compară cu lista de acum') if s.are('compara') else '')
		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions', 'DirectionActions'], {
			'ok': self.keyIntoarce, 'green': self.keyIntoarce, 'cancel': self.keyExit, 'red': self.keyExit,
			'yellow': self.keyCompara,
			'up': self['lista'].up, 'down': self['lista'].down, 'left': self['lista'].pageUp,
			'right': self['lista'].pageDown,
		}, -1)
		self.onLayoutFinish.append(self._pregateste)

	def _pregateste(self):
		font, _m, h = _font('HdsEditorRand', 'Regular', 30, 72)
		mic, _m, _h = _font('HdsEditorMic', 'Regular', 26, 72)
		self.h = max(h, int(80 * self.f))
		l = self['lista']
		l.l.setFont(0, font)
		l.l.setFont(1, mic)
		l.l.setItemHeight(self.h)
		try:
			self.w = l.instance.size().width()
		except Exception:
			self.w = int(1712 * self.f)
		try:
			self.copii = list(self.s.copii() or [])
		except Exception as e:
			_jurnal('copiile: %r' % (e,))
			self.copii = []
		c = self.c
		randuri = []
		for cp in self.copii:
			cand = _g(cp, 'cand')
			data = time.strftime('%d.%m.%Y %H:%M', time.localtime(cand)) if cand else ''
			marime = _g(cp, 'marime')
			jos = _g(cp, 'descriere', '') or ''
			if marime:
				jos = (jos + u' · ' if jos else '') + ('%d KB' % max(1, int(marime) // 1024))
			randuri.append([None,
				MultiContentEntryText(pos=(int(16 * self.f), int(self.h * 0.06)), size=(self.w, int(self.h * 0.5)), font=0,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=data, color=c['text'], color_sel=c['alb']),
				MultiContentEntryText(pos=(int(16 * self.f), int(self.h * 0.54)), size=(self.w - int(32 * self.f),
					int(self.h * 0.42)), font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=jos, color=c['eticheta'],
					color_sel=c['alb'])])
		l.setList(randuri)
		if randuri:
			self['gol'].hide()
		else:
			self['gol'].setText(_('Nicio copie încă: prima se face la prima salvare.'))
			self['key_green'].setText('')
			self['key_yellow'].setText('')

	def keyCompara(self):
		"""Galben: lista de acum fata de copia aleasa (canale noi, care nu mai sunt, redenumite; buchetele)."""
		if self.lucru or not self.copii or not self.s.are('compara'):
			return
		cp = self.copii[self['lista'].getSelectionIndex() or 0]
		self.session.openWithCallback(self._dupaCompara, HdsEditorCanaleBife, self.s, 'compara', False, _g(cp, 'id'))

	def _dupaCompara(self, schimbat=False):
		if schimbat:
			self.schimbat = True

	def keyIntoarce(self):
		if self.lucru or not self.copii:
			return
		cp = self.copii[self['lista'].getSelectionIndex() or 0]
		cand = _g(cp, 'cand')
		data = time.strftime('%d.%m %H:%M', time.localtime(cand)) if cand else ''
		self.session.openWithCallback(boundFunction(self._raspuns, cp), MessageBox,
			_('Întorci lista de canale la copia din %s? Lista de acum se pune întâi într-o copie.') % data,
			MessageBox.TYPE_YESNO, default=False)

	def _raspuns(self, cp, da):
		if not da:
			return
		self.lucru = _('Se întoarce lista la copia aleasă…')
		self['indiciu'].setText(self.lucru)
		self.s.intoarce_fundal(_g(cp, 'id'), self._gata, self._eroare)

	def _gata(self, *_a):
		self.lucru = ''
		self.close(True)

	def _eroare(self, e=None):
		self.lucru = ''
		_jurnal('intoarcerea: %r' % (e,))
		self['indiciu'].setText(str(e) if isinstance(e, G.Eroare) and str(e) else
			_('Lista nu s-a întors la copie. Lista de acum a rămas neatinsă.'))

	def keyExit(self):
		if not self.lucru:
			self.close('schimbat' if self.schimbat else False)


# ---------------------------------------------------------------- alegerea de pe stick

TIPAR_IMPORT = r'(?i)^.*\.(m3u|m3u8|zip|tar|tgz|gz|bz2|xz)$'


def are_lista(dosar):
	"""Dosarul are o lista de canale (lamedb, lamedb5 sau bouquets.tv)."""
	import os
	try:
		nume = set(os.listdir(dosar)) if dosar else set()
	except OSError:
		return False
	return bool(nume & set(('lamedb', 'lamedb5', 'bouquets.tv')))


class HdsEditorCanaleFisier(Screen):
	"""Navigatorul de fisiere al editorului. fel 'import': arhivele (zip, tar, tar.gz), fisierele m3u si dosarele;
	intoarce ('fisier', cale) sau ('dosar', cale) cand dosarul de acum are o lista (galben). fel 'dosar': numai
	dosarele; verde intoarce ('dosar', dosarul de acum) pentru scriere. EXIT intoarce None. Tasta galbena exista numai
	la import (cadrul skinului arata semnul unei taste numai cand ecranul o are)."""
	skin = """
	<screen name="HdsEditorCanaleFisier" position="center,center" size="1240,700" title="Editorul de canale">
		<widget name="hds_cale" position="10,10" size="1220,36" font="Regular;22" foregroundColor="#00ffcc66" noWrap="1" />
		<widget name="lista" position="10,52" size="1220,460" scrollbarMode="showOnDemand" />
		<widget name="hds_stare" position="10,52" size="1220,460" font="Regular;22" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget name="explicatie" position="10,520" size="1220,100" font="Regular;20" foregroundColor="#00C9D2E3" transparent="1" />
		<widget name="key_red" position="10,662" size="300,30" font="Regular;19" backgroundColor="#00E5484D" halign="center" valign="center" zPosition="2" />
		<widget name="key_green" position="316,662" size="300,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="622,662" size="300,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, fel='import'):
		Screen.__init__(self, session)
		from Components.FileList import FileList
		from Components.HdsNavigator import HdsPanouFisiere
		self.fel = fel
		if fel == 'dosar':
			self.setTitle(_('Unde scrii lista?'))
			self.lista = FileList(None, showFiles=False)
			explicatie = _('Alege dosarul de pe stick în care se scrie. OK intră în dosar, verde scrie aici.')
		else:
			self.setTitle(_('Importă de pe stick'))
			self.lista = FileList(None, matchingPattern=TIPAR_IMPORT)
			explicatie = _('Alege o arhivă (zip, tar, tar.gz) cu lista de canale sau un fișier m3u cu fluxuri. OK '
				'intră în dosar sau alege fișierul; galben ia lista din dosarul de acum.')
		self['lista'] = self.lista
		self.panou = HdsPanouFisiere(self, self.lista, details=False)
		self['explicatie'] = Label(explicatie)
		self['key_red'] = Button(_('Înapoi'))
		self['key_green'] = Button(_('Scrie aici') if fel == 'dosar' else _('Alege'))
		if fel == 'import':
			self['key_yellow'] = Button(_('Lista din acest dosar'))
		self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions'], {
			'ok': self.keyOk, 'green': self.keyVerde, 'yellow': self.keyGalben,
			'cancel': self.keyExit, 'red': self.keyExit,
		}, -1)

	def _spune(self, text):
		self['explicatie'].setText(text)

	def keyOk(self):
		if self.lista.canDescent():
			self.lista.descent()
			return
		if self.fel == 'import':
			self.keyVerde()

	def keyVerde(self):
		import os
		dosar = self.lista.getCurrentDirectory()
		if self.fel == 'dosar':
			if not dosar or not os.path.isdir(dosar):
				self._spune(_('Intră întâi într-un dosar (de pildă pe stick).'))
				return
			if not os.access(dosar, os.W_OK):
				self._spune(_('În acest dosar nu se poate scrie. Alege altul.'))
				return
			self.close(('dosar', dosar))
			return
		if self.lista.canDescent():
			self.lista.descent()
			return
		nume = self.lista.getFilename() or ''
		if not nume:
			return
		cale = nume if os.path.isabs(nume) else os.path.join(dosar or '', nume)
		if os.path.isfile(cale):
			self.close(('fisier', cale))

	def keyGalben(self):
		if self.fel != 'import':
			return
		dosar = self.lista.getCurrentDirectory()
		if are_lista(dosar):
			self.close(('dosar', dosar))
		else:
			self._spune(_('În acest dosar nu e o listă de canale. Intră în dosarul care are fișierele lamedb și '
				'bouquets.tv, sau alege o arhivă.'))

	def keyExit(self):
		self.close(None)


# ---------------------------------------------------------------- detaliile canalului

def text_detalii(srv, s=None):
	"""Detaliile unui canal (Serviciu sau randul unei unelte), rand cu rand, in cuvinte simple."""
	randuri = []

	def pune(eticheta, valoare):
		if valoare not in (None, ''):
			randuri.append(u'%s: %s' % (eticheta, valoare))
	pune(_('Nume'), nume_aratat(_g(srv, 'nume', '')))
	pune(_('Furnizor'), _g(srv, 'furnizor'))
	pune(_('Poziția'), _g(srv, 'poz_text'))
	tp = _g(srv, 'tp_text')
	if not tp and _g(srv, 'frecv'):
		tp = ('%d %s' % (_g(srv, 'frecv'), _g(srv, 'pol', '') or '')).strip()
	pune(_('Transponder'), tp)
	if _g(srv, 'sid') is not None:
		pune('SID', '0x%04X (%d)' % (int(_g(srv, 'sid')), int(_g(srv, 'sid'))))
	tip = {'tv': 'TV', 'radio': _('Radio'), 'date': _('date')}.get(_g(srv, 'tip'), _g(srv, 'tip'))
	pune(_('Fel'), u' '.join(x for x in (tip, _g(srv, 'hd', '')) if x))
	acces = _g(srv, 'acces')
	pune(_('Acces'), 'FTA' if acces == 'fta' else (_('criptat') if acces == 'criptat' else None))
	pune(_('Imagine și sunet'), text_imagine_sunet(_g(srv, 'are_video'), _g(srv, 'are_sunet')))
	stare = []
	if _g(srv, 'ascuns'):
		stare.append(_('ascuns în listă'))
	if _g(srv, 'blocat'):
		stare.append(_('blocat (control parental)'))
	if stare:
		pune(_('Stare'), ', '.join(stare))
	if s is not None and _g(srv, 'ref'):
		try:
			buchete = s.in_buchete(_g(srv, 'ref')) or []
			nume = []
			for bid in buchete:
				b = s.buchet(bid)
				nume.append(_g(b, 'nume', bid) or bid)
			pune(_('În buchete'), ', '.join(nume) if nume else _('în niciun buchet'))
		except Exception as e:
			_jurnal('in_buchete: %r' % (e,))
	pune(_('Referința'), _g(srv, 'ref'))
	# tot ce stie lamedb (partea comuna, s.detalii): numerele DVB, tipul, steagurile, PID-urile, CAID-urile
	if s is not None and _g(srv, 'ref') and _g(srv, 'sid') is not None and s.are('detalii'):
		try:
			d = s.detalii(_g(srv, 'ref')) or {}
		except Exception as e:
			_jurnal('detalii: %r' % (e,))
			d = {}
		if d:
			pune('TSID / ONID / namespace', u'0x%04X / 0x%04X / %s' % (int(d.get('tsid') or 0), int(d.get('onid') or 0),
				d.get('ns', '')))
			pune(_('Tipul serviciului'), d.get('tip'))
			st = int(d.get('steaguri') or 0)
			nume_st = [n for bit, n in ((2, _('ascuns')), (8, _('Păstrează numele la scanare')), (64, _('nou')))
				if st & bit]
			pune(_('Steagurile'), (u'0x%X' % st) + (u' (%s)' % u', '.join(nume_st) if nume_st else u''))
			pids = d.get('pids') or {}
			if pids:
				pune(_('PID-uri ținute minte (cod:valoare hex)'), u', '.join(u'%02d:%04x' % (int(k), int(v)) for k, v in
					sorted(pids.items())))
			if d.get('caids'):
				pune('CAID', u', '.join(d.get('caids')))
	return '\n'.join(randuri)


class HdsEditorCanaleDetalii(Screen):
	skin = """
	<screen name="HdsEditorCanaleDetalii" position="center,center" size="1000,640" title="Detalii">
		<widget name="text" position="20,20" size="960,600" font="Regular;24" transparent="1" />
	</screen>"""

	def __init__(self, session, srv, s=None):
		Screen.__init__(self, session)
		self.skinName = ['HdsEditorCanaleDetalii', 'HdsText']
		self.setTitle(_('Detalii'))
		self['text'] = ScrollLabel(text_detalii(srv, s))
		self['actiuni'] = ActionMap(['OkCancelActions', 'DirectionActions', 'HdsEditorCanaleActions'], {
			'ok': self.close, 'cancel': self.close, 'info': self.close,
			'up': self['text'].pageUp, 'down': self['text'].pageDown,
			'left': self['text'].pageUp, 'right': self['text'].pageDown,
			'paginaSus': self['text'].pageUp, 'paginaJos': self['text'].pageDown,
			# tastele editorului care nu au ce face aici: legate, ca jurnalul sa nu scrie unknown action
			'anuleaza': self._nimic, 'reface': self._nimic, 'listaTv': self._nimic, 'listaRadio': self._nimic,
			'tastatura': self._nimic,
		}, -1)

	def _nimic(self):
		pass


# ---------------------------------------------------------------- ajutorul

AJUTOR = (
	(N_('Cum arată'),
		N_('În stânga e SURSA: de unde iei canalele (toate, pe sateliți, pe furnizori, pe transpondere sau '
		'căutarea). În dreapta e BUCHETUL: lista buchetelor, iar cu OK pe unul, canalele lui. Sus vezi modul de acum '
		'(Răsfoire, Mută, Copiază, Selectează) și câte schimbări nu sunt salvate. Jos, fiecare tastă colorată are '
		'scris ce face acum.')),
	(N_('Adaugă canale'),
		N_('Stânga / Dreapta trec dintr-o coloană în alta. În sursă, OK pe un canal îl adaugă la sfârșitul '
		'buchetului din dreapta (pe un satelit sau furnizor, OK îl deschide). Cifrele scriu numele canalului ca la '
		'SMS; TEXT deschide tastatura de pe ecran. Albastru: filtrele (HD, FTA, limba sunetului, subtitrări...).')),
	(N_('Mută'),
		N_('În buchet, OK pe un rând îl ia: Sus / Jos îl duc, cifrele îl duc la poziția scrisă, OK îl lasă, EXIT îl '
		'pune înapoi. Galben îl duce la început sau la sfârșit, albastru în alt buchet.')),
	(N_('Mai multe deodată'),
		N_('Galben: Selectează. OK bifează rândul și trece mai jos; galben pe un marcaj bifează toată '
		'grupa lui. Tastele colorate lucrează apoi pe toate cele bifate: Șterge, Mută, Copiază în...')),
	(N_('Anulează și salvează'),
		N_('Tasta < anulează ultima schimbare, tasta > o reface (și din MENU). Nimic nu se scrie '
		'până nu salvezi: MENU > Salvează acum, sau la ieșire. Înainte de fiecare salvare se face singură o copie de '
		'siguranță; MENU > Copii de siguranță întoarce lista la oricare.')),
	(N_('Uneltele'),
		N_('MENU > Canale de test: canalele fără nume sau cu nume de test, alese de tine pentru ștergere. '
		'MENU > Dubluri și Canale care nu mai există curăță buchetele. Nimic nu se șterge fără bifa ta și fără o '
		'întrebare cu numărul.')),
	(N_('Alte unelte'), N_('MENU > Verifică lista, Buchete goale, Transpondere fără canale, Fluxuri care nu răspund, Sigle '
		'nefolosite și Curățenie (ascunse, blocate, semnul „nou”). În lista sateliților sau a furnizorilor, galben '
		'bifează mai mulți: MENU face câte un buchet din fiecare sau îi șterge din receptor. Copii de siguranță > galben '
		'compară o copie cu lista de acum: din canalele noi faci un buchet, pe cele dispărute le aduci înapoi.')),
	(N_('Căutarea și filtrele'), N_('Căutarea găsește după nume, furnizor, SID, frecvență sau referință; „*” și „?” se '
		'potrivesc pe tot numele („*sport” se termină cu sport); o literă greșită se iartă când nu găsește altceva. '
		'Albastru: filtrele, și cele ale listei (noi, blocate, ascunse, în niciun buchet, fără siglă, HD în nume cu '
		'tip SD).')),
	(N_('Stick'),
		N_('MENU > Importă de pe stick: o arhivă cu lista de canale (zip, tar, tar.gz, de la alt receptor sau din '
		'programele de pe calculator), un dosar cu lista sau un fișier m3u cu fluxuri; lista din arhivă înlocuiește '
		'lista de acum sau adaugă numai ce lipsește. MENU > Scrie lista pe stick face o arhivă tar.gz; în buchet, MENU > '
		'Scrie buchetul ca m3u. Ca orice schimbare, importul se poate anula și nu se scrie până nu salvezi.')),
	(N_('Mouse și tastatură'),
		N_('Clic alege rândul, dublu clic face OK, Ctrl + clic bifează, Shift + clic bifează până '
		'acolo, tras cu mouse-ul mută sau adaugă, rotița derulează. Tastatura: Ctrl+Z / Ctrl+Y anulează / refac, '
		'Ctrl+C / Ctrl+X / Ctrl+V copiază, taie, lipesc, Delete șterge, F2 redenumește, Ctrl+S salvează, Ctrl+A '
		'selectează tot; literele scrise în sursă caută.')),
)


def _config_sfaturi():
	"""config.misc.hds_editor_sfaturi: sfaturile de la prima deschidere au fost vazute (la valoarea din fabrica, nimic
	in settings)."""
	from Components.config import config, ConfigYesNo
	if 'hds_editor_sfaturi' not in config.misc.content.items:
		config.misc.hds_editor_sfaturi = ConfigYesNo(default=False)
	return config.misc.hds_editor_sfaturi


def sfaturi_vazute():
	"""True cand sfaturile s-au aratat o data (sau cand setarile nu se pot citi: atunci nu se arata)."""
	try:
		return bool(_config_sfaturi().value)
	except Exception as e:
		_jurnal('sfaturile: %r' % (e,))
		return True


def pune_sfaturi_vazute(da):
	"""Sfaturile vazute (da) sau de aratat din nou la urmatoarea deschidere (nu: valoarea din fabrica, scoasa din
	settings)."""
	try:
		c = _config_sfaturi()
		c.value = bool(da)
		c.save()
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal('sfaturile: %r' % (e,))


def text_ajutor():
	return '\n\n'.join(u'%s\n%s' % (_(t).upper(), _(c)) for t, c in AJUTOR)


class HdsEditorCanaleAjutor(Screen):
	skin = """
	<screen name="HdsEditorCanaleAjutor" position="center,center" size="1240,700" title="Ajutorul editorului">
		<widget name="text" position="10,10" size="1220,640" font="Regular;22" transparent="1" />
		<widget name="key_green" position="316,662" size="300,30" font="Regular;19" backgroundColor="#0046B06A" halign="center" valign="center" zPosition="2" />
		<widget name="key_yellow" position="622,662" size="300,30" font="Regular;19" backgroundColor="#00E8B93A" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_('Ajutorul editorului'))
		self['text'] = ScrollLabel(text_ajutor())
		self['key_green'] = Button(_('Lista tastelor'))
		self['key_yellow'] = Button(_('Sfaturile, din nou la deschidere') if sfaturi_vazute() else '')
		self['actiuni'] = ActionMap(['OkCancelActions', 'DirectionActions', 'ColorActions', 'HelpActions'], {
			'ok': self.keyExit, 'cancel': self.keyExit, 'green': self.keyTaste, 'displayHelp': self.keyExit,
			'yellow': self.keySfaturi,
			'up': self['text'].pageUp, 'down': self['text'].pageDown,
			'left': self['text'].pageUp, 'right': self['text'].pageDown,
		}, -1)

	def keySfaturi(self):
		"""Galben: sfaturile de la prima deschidere se arata din nou la urmatoarea deschidere a editorului."""
		if self['key_yellow'].getText():
			pune_sfaturi_vazute(False)
			self['key_yellow'].setText('')

	def keyTaste(self):
		self.close(True)

	def keyExit(self):
		self.close(False)
