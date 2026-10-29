# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Legatura ecranelor editorului de canale de pe televizor (Screens/HdsEditorCanale*.py) cu partea comuna a editorului
(Components/HdsEditorCanale*.py: datele, operatiile, anularea, copia de siguranta, salvarea; aceeasi si pentru pagina
web). Ecranele cheama numai metodele de aici; numele lor sunt cele din cereri-tv.md, iar fiecare trece la functia partii
comune care face acelasi lucru. Modulul nu importa enigma: se probeaza pe PC cu o parte comuna falsa
(teste/test_editor_canale_tv_*.py, prin `foloseste(modul)`)."""

_MODUL = {}


def _jurnal(text):
	print('[HdsEditorCanaleLegatura] %s' % text)


def foloseste(modul):
	"""Partea comuna data de mana (probele de pe PC)."""
	_MODUL['m'] = modul


def nucleu():
	"""Modulul partii comune, sau None cand lipseste (atunci intrarile editorului nu se arata)."""
	if 'm' in _MODUL:
		return _MODUL['m']
	try:
		from Components import HdsEditorCanale as m
	except ImportError as e:
		_jurnal('partea comuna lipseste: %s' % e)
		m = None
	_MODUL['m'] = m
	return m


def disponibil():
	return nucleu() is not None


def buchet_automat(buchet_id):
	"""Textul pentru om cand buchetul e refacut automat de alt modul al imaginii (DAB+ / DVB-T2 din satelit, DVB-I,
	ultima scanare), altfel ''."""
	m = nucleu()
	f = getattr(m, 'buchet_automat', None) if m is not None else None
	if f is None or not buchet_id:
		return ''
	try:
		return f(buchet_id) or ''
	except Exception as e:
		_jurnal('buchet_automat: %r' % (e,))
		return ''


def _mesaj(e):
	f = getattr(e, 'mesaj', None)
	if callable(f):
		try:
			return f()
		except Exception:
			pass
	return str(e)


class Ocupat(Exception):
	"""Lista e deschisa pentru editare in alta parte (interfata web), sau sesiunea lucreaza acum (citire, salvare).
	mesaj: textul pentru om; nesalvate: cate schimbari nesalvate are cealalta sesiune; acum: e chiar sesiunea asta,
	ocupata cu un lucru in fundal (citirea, salvarea)."""

	def __init__(self, cine=None, mesaj='', nesalvate=0, acum=False):
		Exception.__init__(self, mesaj)
		self.cine = cine
		self.mesaj = mesaj
		self.nesalvate = nesalvate
		self.acum = acum


class Eroare(Exception):
	"""O operatie care nu se poate face; mesajul e pentru om (tradus)."""


class Preluat(Eroare):
	"""Sesiunea a fost preluata de interfata web: ecranul se inchide."""


def _ridica(e):
	"""Exceptiile partii comune -> Ocupat / Preluat / Eroare (ale ecranelor)."""
	m = nucleu()
	if m is not None:
		if isinstance(e, getattr(m, 'Ocupat', ()) or ()):
			cine = getattr(e, 'cine', None)
			# cine e "tv" / "web" cand lista e deschisa in cealalta parte (televizor sau web); altfel editorul de aici
			# lucreaza acum in fundal
			acum = not isinstance(cine, str)
			raise Ocupat(None if acum else cine, _mesaj(e), getattr(e, 'nesalvate', 0) or 0, acum=acum)
		if isinstance(e, getattr(m, 'Preluat', ()) or ()):
			raise Preluat(_mesaj(e))
		if isinstance(e, getattr(m, 'Eroare', ()) or ()):
			raise Eroare(_mesaj(e))
	raise e


def _transforma(e):
	try:
		_ridica(e)
	except Exception as x:
		return x
	return e


def unelte():
	"""Modulul uneltelor partii comune (Components/HdsEditorCanaleUnelte: arhivele, m3u), sau None."""
	m = nucleu()
	u = getattr(m, 'U', None) if m is not None else None
	if u is not None:
		return u
	try:
		from Components import HdsEditorCanaleUnelte as u
	except ImportError:
		u = None
	return u


# ---------------------------------------------------------------- importul si exportul de pe stick

DOSAR_IMPORT = '/tmp/hds-editor-tv-import'
MAX_M3U = 8 * 1024 * 1024          # octetii unui fisier m3u citit de pe stick
EXTENSII_M3U = ('.m3u', '.m3u8')


def e_m3u(cale):
	return (cale or '').lower().endswith(EXTENSII_M3U)


def citeste_m3u(cale):
	"""Textul unui m3u de pe stick (octeti; partea comuna il decodeaza); ValueError cand e prea mare."""
	import os
	if os.path.getsize(cale) > MAX_M3U:
		raise ValueError('m3u prea mare')
	with open(cale, 'rb') as f:
		return f.read()


def despacheteaza(cale):
	"""Arhiva de pe stick despachetata in DOSAR_IMPORT (golit intai). -> dosarul cu lista (lamedb sau bouquets.tv)
	sau None. Ridica Eroare cand arhiva nu se poate citi. Pe un fir (nu atinge sesiunea)."""
	import os
	import shutil
	u = unelte()
	if u is None:
		raise Eroare('')
	limita = getattr(u, 'MAX_ARHIVA', 64 * 1024 * 1024)
	shutil.rmtree(DOSAR_IMPORT, True)
	os.makedirs(DOSAR_IMPORT)
	try:
		if os.path.getsize(cale) > limita:
			raise ValueError('arhiva prea mare')
		with open(cale, 'rb') as f:
			date = f.read()
		rad = u.despacheteaza_arhiva(date, DOSAR_IMPORT)
	except Exception as e:
		_jurnal('arhiva %s: %r' % (cale, e))
		shutil.rmtree(DOSAR_IMPORT, True)
		raise Eroare(_t('Arhiva nu se poate citi (merg zip, tar și tar.gz).'))
	if rad is None:
		shutil.rmtree(DOSAR_IMPORT, True)
	return rad


def ce_are(director):
	"""{servicii, transpondere, buchete: [(id, nume, n, radio)]} al unei liste dintr-un dosar (pe un fir)."""
	u = unelte()
	if u is None:
		raise Eroare('')
	return u.ce_are_arhiva(director)


def gaseste_lista(director):
	"""Dosarul cu lista (lamedb sau bouquets.tv) din `director` sau de sub el, ori None."""
	u = unelte()
	return u.gaseste_lista(director) if u is not None else None


def curata_importul():
	import shutil
	shutil.rmtree(DOSAR_IMPORT, True)


def _t(text):
	try:
		import builtins
		f = builtins.__dict__.get('_')
		return f(text) if f is not None else text
	except Exception:
		return text


class Fir(object):
	"""O functie pe un fir separat (despachetarea unei arhive, scrierea pe stick); rezultatul vine pe firul enigma2 prin
	`ceas` (eTimer al ecranului, privit la 100 ms). sincron=True (probele de pe PC): pe loc."""

	def __init__(self, ceas, sincron=False):
		self.ceas = ceas
		self.sincron = sincron
		self.rez = None
		self.la = None
		ceas.callback.append(self._vezi)

	def merge(self):
		return self.la is not None

	def porneste(self, functie, la_gata, la_eroare):
		self.rez = None
		self.la = (la_gata, la_eroare)

		def lucreaza():
			try:
				self.rez = ('gata', functie())
			except Exception as e:
				self.rez = ('eroare', e)
		if self.sincron:
			lucreaza()
			self._vezi()
			return
		import threading
		t = threading.Thread(target=lucreaza)
		t.daemon = True
		t.start()
		self.ceas.start(100, False)

	def _vezi(self):
		if self.rez is None or self.la is None:
			return
		self.ceas.stop()
		(fel, v), self.rez = self.rez, None
		la, self.la = self.la, None
		(la[0] if fel == 'gata' else la[1])(v)

	def opreste(self):
		self.ceas.stop()
		self.la = None


def deschide_fundal(la_gata, la_eroare, cine='tv', nume=''):
	"""Sesiunea de editare, cu citirea listei pe un fir al partii comune: la_gata(Sesiune) sau la_eroare(Ocupat /
	Eroare), amandoua pe firul enigma2."""
	m = nucleu()
	if m is None:
		la_eroare(Eroare(''))
		return

	def gata(s):
		la_gata(Sesiune(s))

	def eroare(e):
		la_eroare(_transforma(e))
	try:
		m.deschide_fundal(cine=cine, nume=nume, la_gata=gata, la_eroare=eroare)
	except Exception as e:
		la_eroare(_transforma(e))


def deschide(cine='tv', nume=''):
	"""Varianta pe loc (probele de pe PC). -> Sesiune; ridica Ocupat cand interfata web editeaza acum."""
	m = nucleu()
	if m is None:
		raise Eroare('')
	try:
		return Sesiune(m.deschide(cine=cine, nume=nume))
	except Exception as e:
		_ridica(e)


def preia(cine='tv', nume=''):
	"""Ia sesiunea interfetei web (dupa intrebarea omului); apoi se deschide din nou cu deschide_fundal."""
	m = nucleu()
	if m is None:
		return False
	try:
		m.preia(cine=cine, nume=nume)
		return True
	except Exception as e:
		_jurnal('preia: %r' % (e,))
		return False


def ocupat_de():
	m = nucleu()
	try:
		return m.ocupat_de() if m is not None else None
	except Exception as e:
		_jurnal('ocupat_de: %r' % (e,))
		return None


def asculta(functie, da=True):
	"""functie(fel, date) dupa "salvat", "intors", "preluat" (partea comuna, E.asculta)."""
	m = nucleu()
	if m is None:
		return
	try:
		if da:
			m.asculta(functie)
		else:
			m.nu_mai_asculta(functie)
	except Exception as e:
		_jurnal('asculta: %r' % (e,))


class Sesiune(object):
	"""Sesiunea partii comune vazuta de ecrane. Fiecare metoda e o trecere; exceptiile partii comune ies ca Eroare sau
	Ocupat."""

	def __init__(self, s):
		self.s = s

	def _f(self, nume, *a, **k):
		try:
			return getattr(self.s, nume)(*a, **k)
		except (Ocupat, Eroare):
			raise
		except Exception as e:
			_ridica(e)

	def __getattr__(self, nume):
		"""Celelalte operatii ale partii comune (alternativele, satelitii, steagurile, detaliile, comparatia...), cu
		exceptiile ei facute Eroare / Ocupat; o operatie pe care partea comuna n-o are ridica AttributeError (ecranele
		intreaba intai `are`)."""
		if nume.startswith('_'):
			raise AttributeError(nume)
		f = getattr(self.s, nume)
		if not callable(f):
			return f

		def trecere(*a, **k):
			return self._f(nume, *a, **k)
		return trecere

	def unealta(self, functie, la_gata, la_eroare):
		"""functie() (o unealta care numai citeste lista) pe firul uneltelor al partii comune, cand il are; rezultatul
		vine pe firul enigma2. Fara el, pe loc."""
		fundal = getattr(self.s, '_unealta_fundal', None)
		if fundal is not None:
			try:
				fundal(functie, la_gata, lambda e: la_eroare(_transforma(e)))
				return
			except Exception as e:
				la_eroare(_transforma(e))
				return
		try:
			rez = functie()
		except Exception as e:
			la_eroare(_transforma(e))
			return
		la_gata(rez)

	def refs_si_nume(self):
		"""Referintele (canalele si fluxurile din buchete) si numele canalelor din lista, pentru siglele nefolosite."""
		d = getattr(self.s, 'd', None)
		if d is not None:
			refs = [sv.ref for sv in d.lamedb.servicii.values()]
			for b in d.buchete.values():
				refs.extend(i.ref for i in b.intrari if i.fel == 'flux')
			return refs, [sv.nume for sv in d.lamedb.servicii.values()]
		canale = self._f('toate', None)
		return [c.ref for c in canale], [c.nume for c in canale]

	# ------------------------------------------------------------ sesiunea
	def inchide(self):
		try:
			self.s.inchide()
		except Exception as e:
			_jurnal('inchide: %r' % (e,))

	def lucreaza(self):
		f = getattr(self.s, 'lucreaza', None)
		try:
			return bool(f()) if f is not None else False
		except Exception:
			return False

	def valida(self):
		f = getattr(self.s, 'valida', None)
		if f is None:
			return True
		try:
			return bool(f())
		except Exception:
			return False

	# ------------------------------------------------------------ buchetele si intrarile
	def radacina(self, radio=False):
		"""Id-ul listei buchetelor (bouquets.tv / bouquets.radio), tratata ca un buchet ale carui intrari sunt buchetele."""
		f = getattr(self.s, 'radacina', None)
		if f is not None:
			return self._f('radacina', radio)
		return 'bouquets.radio' if radio else 'bouquets.tv'

	def buchete(self, radio=False):
		return self._f('buchete', radio)

	def intrari(self, buchet_id):
		return self._f('intrari', buchet_id)

	def buchet(self, buchet_id):
		return self._f('buchet', buchet_id)

	def nelegate(self, radio=None):
		return self._f('nelegate', radio)

	def in_buchete(self, ref):
		return self._f('in_buchete', ref)

	# ------------------------------------------------------------ sursele
	def toate(self, radio=False):
		return self._f('toate', radio)

	def sateliti(self, radio=False):
		return self._f('sateliti', radio)

	def nume_satelit(self, poz):
		"""Numele satelitului din satellites.xml („Astra 1N”), sau '' cand nu se stie."""
		f = getattr(self.s, 'nume_satelit', None)
		try:
			return (f(poz) or '') if f is not None else ''
		except Exception:
			return ''

	def din_satelit(self, poz, radio=False):
		return self._f('din_satelit', poz, radio)

	def furnizori(self, radio=False):
		return self._f('furnizori', radio)

	def din_furnizor(self, nume, radio=False):
		return self._f('din_furnizor', nume, radio)

	def serviciu(self, ref):
		return self._f('serviciu', ref)

	def transpondere(self, radio=False):
		"""Transponderele cu canale de felul listei (TV / radio), de la vest la est si dupa frecventa."""
		return [t for t in self._f('transpondere', None, radio) if getattr(t, 'n', 1)]

	def din_transponder(self, tp_cheie):
		return self._f('din_transponder', tp_cheie)

	def cauta(self, text, radio=False, chei=None):
		"""Numele, furnizorul, SID-ul si frecventa (partea comuna, ca in web); chei = numai aceste servicii. Ca in web
		si: o referinta (1:0:19:...) da canalul ei; „*” si „?” se potrivesc pe tot numele („*sport” = se termina cu
		sport); cand nu se gaseste nimic, o litera gresita, lipsa, in plus sau doua vecine schimbate in cuvintele de 4+
		litere. Numele care incep cu textul vin intai (HdsEditorCanaleLogica.ordine_cautare)."""
		from Screens import HdsEditorCanaleLogica as L
		t = (text or '').strip()
		if L.e_referinta(t):
			c = self._f('serviciu', t)
			return [c] if c is not None and (radio is None or (getattr(c, 'tip', '') == 'radio') == bool(radio)) else []
		if '*' in t or '?' in t:
			canale = [c for c in self._f('toate', radio) if chei is None or getattr(c, 'cheie', None) in chei]
			return L.ordine_cautare([c for c in canale if L.potrivire_tipar(getattr(c, 'nume', ''), t)], t.strip('*?'))
		rez = self._f('cauta', text, radio, chei)
		if not rez and L.cuvinte_simple(t):
			canale = [c for c in self._f('toate', radio) if chei is None or getattr(c, 'cheie', None) in chei]
			rez = L.cauta_tolerant(canale, t)
		return L.ordine_cautare(rez, text)

	def are_flux_nou(self):
		return hasattr(self.s, 'flux_nou')

	def flux_nou(self, buchet_id, la, adresa, nume):
		return self._f('flux_nou', buchet_id, la, adresa, nume)

	# ------------------------------------------------------------ operatiile (fiecare cu anulare)
	def adauga(self, buchet_id, refs, la=None):
		return self._f('adauga', buchet_id, list(refs), la=la)

	def muta(self, buchet_id, indici, la):
		return self._f('muta', buchet_id, list(indici), la)

	def muta_in(self, din_id, indici, in_id, la=None):
		return self._f('muta_in', din_id, list(indici), in_id, la=la)

	def copiaza(self, din_id, indici, in_id, la=None):
		return self._f('copiaza', din_id, list(indici), in_id, la=la)

	def scoate(self, buchet_id, indici):
		return self._f('scoate', buchet_id, list(indici))

	def redenumeste(self, buchet_id, indice, nume):
		return self._f('redenumeste', buchet_id, indice, nume)

	def redenumeste_serviciu(self, ref, nume):
		return self._f('redenumeste_serviciu', ref, nume)

	def redenumeste_buchet(self, buchet_id, nume):
		return self._f('redenumeste_buchet', buchet_id, nume)

	def ascunde(self, refs, da=True):
		return self._f('ascunde', list(refs), da)

	def blocheaza(self, refs, da=True):
		return self._f('blocheaza', list(refs), da)

	def blocheaza_buchet(self, buchet_id, da=True):
		return self._f('blocheaza_buchet', buchet_id, da)

	def marcaj_nou(self, buchet_id, la, nume, numerotat=False):
		return self._f('marcaj_nou', buchet_id, la, nume, numerotat=numerotat)

	def spatiu_nou(self, buchet_id, la):
		return self._f('spatiu_nou', buchet_id, la)

	def buchet_nou(self, nume, radio=False, parinte=None, la=None, refs=None):
		return self._f('buchet_nou', nume, radio=radio, parinte=parinte, la=la, refs=refs)

	def buchet_din(self, fel, valoare, radio=False, nume=None):
		return self._f('buchet_din', fel, valoare, radio=radio, nume=nume)

	def leaga_buchet(self, buchet_id, parinte=None, la=None):
		return self._f('leaga_buchet', buchet_id, parinte=parinte, la=la)

	def sterge_buchet(self, buchet_id):
		return self._f('sterge_buchet', buchet_id)

	def sorteaza(self, buchet_id, dupa='nume', indici=None, invers=False):
		return self._f('sorteaza', buchet_id, dupa=dupa, indici=indici, invers=invers)

	def sterge_servicii(self, refs):
		return self._f('sterge_servicii', list(refs))

	def are(self, nume):
		"""Partea comuna are operatia (randurile din MENU apar numai atunci)."""
		return hasattr(self.s, nume)

	def scoate_din_toate(self, refs):
		"""Canalele scoase din toate buchetele (raman in lista receptorului) -> cate randuri."""
		return self._f('scoate_din_toate', list(refs))

	def copiaza_buchet(self, buchet_id, nume=None):
		return self._f('copiaza_buchet', buchet_id, nume)

	def ascunde_buchet(self, buchet_id, da=True):
		return self._f('ascunde_buchet', buchet_id, da)

	def are_import(self):
		"""Importul de pe stick (m3u, arhiva, dosar) e in partea comuna."""
		return hasattr(self.s, 'importa_m3u') and hasattr(self.s, 'importa_dosar') and unelte() is not None

	def are_export(self):
		u = unelte()
		return hasattr(self.s, 'text_fisiere') and u is not None and hasattr(u, 'arhiva_listei')

	def importa_m3u(self, text, nume, radio=False, pe_grupe=False):
		return self._f('importa_m3u', text, nume, radio, pe_grupe)

	def importa_alese(self, director, buchete, mod='uneste'):
		"""Numai buchetele alese ale unei liste: canalele lor care lipsesc adaugate (lamedb unit, nimic sters) si
		buchetele puse (mod „inlocuieste”: ca in arhiva; „uneste”: numai randurile care lipsesc). Doi pasi ai partii
		comune; daca al doilea nu merge, primul se anuleaza (lista ramane cum era)."""
		inainte = self._f('nesalvate'), self._f('de_anulat')
		self._f('importa_dosar', director, ('lamedb',), None, 'uneste')
		facut = (self._f('nesalvate'), self._f('de_anulat')) != inainte
		try:
			return self._f('importa_dosar', director, ('buchete',), list(buchete), mod)
		except Exception:
			if facut:
				self._f('anuleaza')
			raise

	def importa_dosar(self, director, mod='inlocuieste'):
		"""Lista din dosar (lamedb si buchetele): mod „inlocuieste” sau „uneste” (numai ce lipseste) -> {servicii,
		transpondere, buchete}."""
		return self._f('importa_dosar', director, ('lamedb', 'buchete'), None, mod)

	def arhiva(self, fel='tar.gz'):
		"""Lista de acum (cu schimbarile nesalvate) ca arhiva etc/enigma2 + etc/tuxbox, ca la exportul din web."""
		try:
			return unelte().arhiva_listei(self.s, fel)
		except Exception as e:
			_ridica(e)

	def exporta_m3u(self, buchet_id, gazda='', port=8001):
		return self._f('exporta_m3u', buchet_id, gazda, port)

	def schimbari(self):
		"""Rezumatul de dinaintea salvarii ({} cand partea comuna nu-l are sau cade)."""
		f = getattr(self.s, 'schimbari', None)
		try:
			return (f() or {}) if f is not None else {}
		except Exception as e:
			_jurnal('schimbari: %r' % (e,))
			return {}

	def anuleaza(self):
		return self._f('anuleaza')

	def reface(self):
		return self._f('reface')

	def de_anulat(self):
		return self._f('de_anulat')

	def de_refacut(self):
		return self._f('de_refacut')

	def nesalvate(self):
		try:
			return int(self.s.nesalvate() or 0)
		except Exception as e:
			_jurnal('nesalvate: %r' % (e,))
			return 0

	# ------------------------------------------------------------ salvarea si copiile
	def salveaza_fundal(self, la_gata, la_eroare):
		"""Copia de siguranta, scrierea, reincarcarea listelor (si a listei de pe TV) pe un fir al partii comune;
		la_gata(Copie) / la_eroare(Eroare) pe firul enigma2."""
		try:
			self.s.salveaza_fundal(la_gata, lambda e: la_eroare(_transforma(e)))
		except Exception as e:
			la_eroare(_transforma(e))

	def salveaza(self):
		return self._f('salveaza')

	def copii(self):
		return self._f('copii')

	def intoarce_fundal(self, copie_id, la_gata, la_eroare):
		try:
			self.s.intoarce_fundal(copie_id, la_gata, lambda e: la_eroare(_transforma(e)))
		except Exception as e:
			la_eroare(_transforma(e))

	# ------------------------------------------------------------ uneltele
	def canale_test(self, radio=None):
		return self._f('canale_test', radio)

	def dubluri(self):
		return self._f('dubluri')

	def referinte_moarte(self):
		return self._f('referinte_moarte')

	def repara_moarte(self, randuri):
		return self._f('repara_moarte', list(randuri))
