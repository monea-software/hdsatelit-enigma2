# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Logica editorului de canale de pe televizor (Screens/HdsEditorCanale.py), fara nimic din enigma: se probeaza pe PC
(teste/test_editor_canale_tv_logica.py).

Ecranul are doua coloane: SURSA (in stanga: toate canalele, satelitii, furnizorii, cautarea) si BUCHET (in dreapta:
lista buchetelor, apoi intrarile unui buchet). Patru moduri, aratate mereu pe ecran:
  RASFOIRE   - sagetile aleg randul; OK ia canalul (in buchet: pentru mutare; in sursa: il adauga in buchet);
  SELECTEAZA - OK bifeaza / debifeaza randul si coboara; tastele colorate lucreaza pe cele bifate;
  MUTA       - randurile luate („in mana”) se plimba prin buchet cu sagetile, CH+/CH- si cifrele; OK le lasa, EXIT le
               pune inapoi; pe ecran se vede ordinea noua inainte sa fie facuta (o singura schimbare la lasare);
  COPIAZA    - la fel, dar randurile luate sunt copii (din sursa sau din alt buchet), iar originalul ramane.

Aici: tabelul tastelor colorate dupa mod si coloana, textul indiciului, cifrele pentru pozitie (ca la schimbarea
canalului: se aduna si se aplica dupa o pauza sau la OK), ordinea cu blocul mutat, bifele (si bifarea pe un interval,
pentru Shift), tastele unei tastaturi puse in receptor (Ctrl si Shift tinute minte, scurtaturile ca in editorul web) si
literele pentru scrisul direct in cautare."""

RASFOIRE = 'rasfoire'
MUTA = 'muta'
COPIAZA = 'copiaza'
SELECTEAZA = 'selecteaza'
# ordinea din randul modurilor de pe ecran
MODURI = (RASFOIRE, MUTA, COPIAZA, SELECTEAZA)
SURSA = 0
BUCHET = 1


def _(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, in teste, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get('_')
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


def N_(text):
	"""Text de tradus mai tarziu (msgid gasit de xgettext), intors asa cum e."""
	return text


NUME_MOD = {
	RASFOIRE: N_('Răsfoire'),
	MUTA: N_('Mută'),
	COPIAZA: N_('Copiază'),
	SELECTEAZA: N_('Selectează'),
}

# ---------------------------------------------------------------- tastele colorate

# (actiunea, textul) pentru rosu, verde, galben, albastru; actiunea o leaga ecranul de functia lui. Cuvintele sunt
# aceleasi ca in editorul web (API.md, „Numele actiunilor”): Adauga, Muta, Muta in..., Copiaza in..., Sterge, Selecteaza
# tot / Deselecteaza tot.
_TASTE_MUTA = (('pune_inapoi', N_('Pune înapoi')), ('lasa', N_('Lasă aici')),
	('capat', N_('La început / la sfârșit')), ('alt_buchet', N_('Mută în…')))
_TASTE_COPIAZA = (('pune_inapoi', N_('Renunță')), ('lasa', N_('Lasă aici')),
	('capat', N_('La început / la sfârșit')), ('alt_buchet', N_('Copiază în…')))
_TASTE_SELECTIE_SURSA = (('debifeaza_tot', N_('Deselectează tot')), ('adauga', N_('Adaugă')),
	('gata', N_('Gata cu selecția')), ('bifeaza_tot', N_('Selectează tot')))
_TASTE_SELECTIE_BUCHET = (('scoate', N_('Șterge')), ('muta', N_('Mută')),
	('gata', N_('Gata cu selecția')), ('copiaza', N_('Copiază în…')))
_TASTE_SURSA = (('sursa', N_('Sursa')), ('adauga', N_('Adaugă')),
	('selecteaza', N_('Selectează')), ('filtre', N_('Filtre')))
_TASTE_RADACINA = (('sterge_buchet', N_('Șterge')), ('muta', N_('Mută')),
	('selecteaza', N_('Selectează')), ('buchet_nou', N_('Buchet nou')))
_TASTE_BUCHET = (('scoate', N_('Șterge')), ('muta', N_('Mută')),
	('selecteaza', N_('Selectează')), ('buchetele', N_('Buchetele')))
_TASTE_CITIRE = (('', ''), ('', ''), ('', ''), ('', ''))


def taste_colorate(mod, coloana, radacina=False, numai_citire=False):
	"""(actiune, msgid) pentru cele patru taste colorate, dupa mod si coloana. radacina: coloana buchetului arata lista
	buchetelor. numai_citire: lista e deschisa in alta parte (interfata web) si nu se schimba nimic; raman numai
	tastele care nu schimba (sursa, filtrele)."""
	if mod == MUTA:
		return _TASTE_MUTA
	if mod == COPIAZA:
		return _TASTE_COPIAZA
	if mod == SELECTEAZA:
		return _TASTE_SELECTIE_SURSA if coloana == SURSA else _TASTE_SELECTIE_BUCHET
	if coloana == SURSA:
		if numai_citire:
			return (_TASTE_SURSA[0], ('', ''), ('', ''), _TASTE_SURSA[3])
		return _TASTE_SURSA
	if numai_citire:
		return _TASTE_CITIRE
	return _TASTE_RADACINA if radacina else _TASTE_BUCHET


def indiciu(mod, coloana, pe_dosar=False, radacina=False, cifre='', numai_citire=False):
	"""Randul de indiciu de sub coloane: ce fac acum OK, sagetile si cifrele (msgid, netradus)."""
	if cifre:
		return None   # ecranul arata pozitia scrisa (text_cifre)
	if numai_citire:
		return N_('Lista e deschisă acum în interfața web: aici doar o poți privi.')
	if mod == MUTA:
		return N_('Sus / Jos mută rândurile · cifrele: poziția · OK le lasă aici · EXIT le pune înapoi')
	if mod == COPIAZA:
		return N_('Sus / Jos alege locul · cifrele: poziția · OK pune copia aici · EXIT renunță')
	if mod == SELECTEAZA:
		return N_('OK bifează și trece mai jos · tastele colorate lucrează pe rândurile bifate')
	if coloana == SURSA:
		if pe_dosar:
			return N_('OK deschide · Stânga / Dreapta: coloana · cifrele scriu numele · HELP ajutor')
		return N_('OK adaugă canalul în buchetul din dreapta · cifrele scriu numele · HELP ajutor')
	if radacina:
		return N_('OK deschide buchetul · Stânga / Dreapta: coloana · < anulează · > refă · HELP ajutor')
	if pe_dosar:
		return N_('OK deschide · cifrele: poziția · < anulează · > refă · HELP ajutor')
	return N_('OK ia rândul ca să-l muți · cifrele: poziția · < anulează · > refă · HELP ajutor')


# ---------------------------------------------------------------- cifrele pentru pozitie

CIFRE_MAXIM = 5
PAUZA_CIFRE_MS = 1500


class Cifre(object):
	"""Pozitia scrisa cu cifrele, ca la schimbarea canalului: cifrele se aduna (cel mult CIFRE_MAXIM) si se aplica dupa
	PAUZA_CIFRE_MS fara alta cifra sau la OK. „0” singur nu e o pozitie (pozitiile incep de la 1)."""

	def __init__(self):
		self.text = ''

	def apasa(self, cifra):
		"""Adauga cifra (0-9). -> textul de acum."""
		c = str(int(cifra) % 10)
		if not self.text and c == '0':
			return self.text
		if len(self.text) < CIFRE_MAXIM:
			self.text += c
		return self.text

	def ia(self):
		"""Pozitia scrisa (de la 1) si golirea, sau None cand nu e scris nimic."""
		t, self.text = self.text, ''
		return int(t) if t else None

	def goleste(self):
		self.text = ''


def text_cifre(cifre):
	"""Textul aratat cat se scrie pozitia (msgid cu %s)."""
	return _('Poziția: %s') % (cifre + '_')


def pozitie_in_lista(pozitie, n):
	"""Pozitia scrisa de om (de la 1) -> indicele randului (de la 0), cel mult ultimul; None pentru o lista goala."""
	if n <= 0 or pozitie is None:
		return None
	return max(0, min(int(pozitie) - 1, n - 1))


# ---------------------------------------------------------------- blocul tinut in mana (MUTA, COPIAZA)

def ordine_cu_bloc(n, bloc, la):
	"""MUTA: ordinea randurilor de pe ecran (indicii vechi) cu blocul pus la locul `la`. n = cate randuri are lista;
	bloc = indicii luati (in ordinea lor din lista); la = cate randuri ramase stau inaintea blocului (0 .. n-len(bloc))."""
	luate = set(bloc)
	rest = [i for i in range(n) if i not in luate]
	la = max(0, min(int(la), len(rest)))
	return rest[:la] + sorted(luate) + rest[la:]


def loc_initial(bloc):
	"""MUTA: locul de pornire al blocului = cate randuri neluate stau inaintea primului rand luat (blocul pare ca
	ramane pe loc pana la prima sageata)."""
	if not bloc:
		return 0
	prim = min(bloc)
	luate = set(bloc)
	return sum(1 for i in range(prim) if i not in luate)


def maxim_loc(n, k, copie):
	"""Cel mai mare loc al blocului: la MUTA dupa cele n-k randuri ramase, la COPIAZA dupa toate n randurile."""
	return n if copie else max(0, n - k)


def muta_loc(la, pas, n, k, copie):
	"""Locul blocului dupa un pas (+/-1 sau o pagina), intre 0 si maxim_loc."""
	return max(0, min(int(la) + int(pas), maxim_loc(n, k, copie)))


def loc_capat(la, n, k, copie):
	"""Tasta galbena in MUTA / COPIAZA: la inceput; daca e deja acolo, la sfarsit."""
	return maxim_loc(n, k, copie) if la == 0 else 0


def loc_din_pozitie(pozitie, n, k, copie):
	"""Pozitia scrisa (de la 1) a primului rand al blocului -> locul blocului."""
	if pozitie is None:
		return None
	return max(0, min(int(pozitie) - 1, maxim_loc(n, k, copie)))


def tinta_operatie(n, bloc, la, copie):
	"""Locul de dat partii comune la lasare: indicele randului din lista de dinainte inaintea caruia se pun randurile.
	La COPIAZA lista nu pierde nimic, deci locul e chiar `la`. La MUTA locul e in lista fara randurile luate."""
	return int(la)


def schimbat(n, bloc, la, copie):
	"""False cand lasarea nu schimba nimic (MUTA cu blocul la locul lui, si randurile luate erau la rand)."""
	if copie:
		return bool(bloc)
	return ordine_cu_bloc(n, bloc, la) != list(range(n))


# ---------------------------------------------------------------- bifele

class Bife(object):
	"""Randurile bifate ale unei coloane, dupa cheia lor (aceeasi cheie ramane bifata si dupa o filtrare). ancora: randul
	de la care pleaca bifarea pe interval (Shift + clic, Shift + sageata)."""

	def __init__(self):
		self.chei = set()
		self.ordine = []    # ordinea bifarii (pentru blocul luat: ordinea din lista, nu asta)
		self.ancora = None

	def __len__(self):
		return len(self.chei)

	def __contains__(self, cheie):
		return cheie in self.chei

	def comuta(self, cheie):
		"""Bifeaza sau debifeaza. -> True daca acum e bifat."""
		self.ancora = cheie
		if cheie in self.chei:
			self.chei.discard(cheie)
			self.ordine = [c for c in self.ordine if c != cheie]
			return False
		self.chei.add(cheie)
		self.ordine.append(cheie)
		return True

	def pune(self, cheie, da=True):
		if da and cheie not in self.chei:
			self.chei.add(cheie)
			self.ordine.append(cheie)
		elif not da and cheie in self.chei:
			self.chei.discard(cheie)
			self.ordine = [c for c in self.ordine if c != cheie]

	def interval(self, chei_lista, i_ancora, i):
		"""Bifeaza randurile dintre ancora si i (inclusiv), din cheile listei de pe ecran."""
		if i_ancora is None:
			i_ancora = i
		a, b = sorted((i_ancora, i))
		for c in chei_lista[a:b + 1]:
			self.pune(c, True)

	def toate(self, chei_lista):
		for c in chei_lista:
			self.pune(c, True)

	def goleste(self):
		self.chei = set()
		self.ordine = []
		self.ancora = None

	def pastreaza(self, chei_existente):
		"""Scoate bifele randurilor care nu mai exista (dupa o schimbare sau o anulare)."""
		ex = set(chei_existente)
		self.chei &= ex
		self.ordine = [c for c in self.ordine if c in ex]
		if self.ancora not in ex:
			self.ancora = None

	def indici(self, chei_lista):
		"""Indicii randurilor bifate, in ordinea listei."""
		return [i for i, c in enumerate(chei_lista) if c in self.chei]


# ---------------------------------------------------------------- tastatura pusa in receptor

# codurile Linux (linux/input.h); eRCMapper traduce inainte Enter = OK, Esc = IESIRE, F1-F4 = culorile, F5 = MENU
KEY_ESC, KEY_BACKSPACE, KEY_TAB, KEY_ENTER, KEY_SPACE = 1, 14, 15, 28, 57
KEY_LEFTCTRL, KEY_RIGHTCTRL, KEY_LEFTSHIFT, KEY_RIGHTSHIFT, KEY_LEFTALT, KEY_RIGHTALT = 29, 97, 42, 54, 56, 100
KEY_HOME, KEY_UP, KEY_PAGEUP, KEY_LEFT, KEY_RIGHT, KEY_END, KEY_DOWN, KEY_PAGEDOWN = 102, 103, 104, 105, 106, 107, 108, 109
KEY_INSERT, KEY_DELETE = 110, 111
KEY_A, KEY_C, KEY_S, KEY_V, KEY_X, KEY_Y, KEY_Z = 30, 46, 31, 47, 45, 21, 44
KEY_GREEN = 399
KEY_HELP = 138
FLAG_APASAT, FLAG_ELIBERAT, FLAG_REPETAT = 0, 1, 2
CTRL = frozenset((KEY_LEFTCTRL, KEY_RIGHTCTRL))
SHIFT = frozenset((KEY_LEFTSHIFT, KEY_RIGHTSHIFT))

# litera fiecarei taste (asezarea obisnuita, QWERTY), pentru prima litera scrisa direct in cautare: dupa ea tastatura
# trece in modul text si literele vin cu asezarea aleasa a tastaturii
LITERE = {16: 'q', 17: 'w', 18: 'e', 19: 'r', 20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p', 30: 'a', 31: 's',
	32: 'd', 33: 'f', 34: 'g', 35: 'h', 36: 'j', 37: 'k', 38: 'l', 44: 'z', 45: 'x', 46: 'c', 47: 'v', 48: 'b', 49: 'n',
	50: 'm'}


class Modificatori(object):
	"""Ctrl si Shift tinute apasat. eActionMap pierde eliberarea lui Ctrl cand intre apasare si eliberare a venit alta
	tasta (action.cpp: eliberarea unei taste se trimite numai daca ea a fost ultima apasata), deci starea adevarata se
	citeste, cand se poate, din nucleu (citeste() -> multimea codurilor apasate acum pe tastaturi, sau None); fara ea
	(emulatorul, tastele trimise din program) Ctrl / Shift tin numai pana la urmatoarea tasta (consuma())."""

	def __init__(self, citeste=None):
		self.ctrl = set()
		self.shift = set()
		self.citeste = citeste

	def tasta(self, cod, flag):
		"""-> True daca tasta e Ctrl sau Shift (tinuta minte aici, nu are alt sens)."""
		for grup, multime in ((CTRL, self.ctrl), (SHIFT, self.shift)):
			if cod in grup:
				if flag == FLAG_ELIBERAT:
					multime.discard(cod)
				else:
					multime.add(cod)
				return True
		return False

	def _apasate(self):
		if self.citeste is None:
			return None
		try:
			return self.citeste()
		except Exception:
			return None

	@property
	def are_ctrl(self):
		a = self._apasate()
		return bool(a & CTRL) if a is not None else bool(self.ctrl)

	@property
	def are_shift(self):
		a = self._apasate()
		return bool(a & SHIFT) if a is not None else bool(self.shift)

	def consuma(self):
		"""Dupa o tasta (sau un clic) care a folosit modificatorii: fara starea nucleului, ei nu mai tin."""
		if self._apasate() is None:
			self.goleste()

	def goleste(self):
		self.ctrl = set()
		self.shift = set()


def scurtatura(cod, ctrl=False, shift=False):
	"""Actiunea unei taste de tastatura in editor (aceleasi ca in editorul web), sau None (tasta merge mai departe la
	hartile de actiuni, ca de pe telecomanda: sagetile fara modificatori, cifrele, Enter = OK, Esc = IESIRE)."""
	if ctrl:
		return {
			KEY_C: 'copiaza', KEY_X: 'taie', KEY_V: 'lipeste', KEY_Z: 'reface' if shift else 'anuleaza',
			KEY_Y: 'reface', KEY_A: 'bifeaza_tot', KEY_S: 'salveaza', KEY_UP: 'muta_sus', KEY_DOWN: 'muta_jos',
			KEY_HOME: 'inceput', KEY_END: 'sfarsit',
		}.get(cod)
	if shift:
		return {KEY_UP: 'bifeaza_sus', KEY_DOWN: 'bifeaza_jos', KEY_TAB: 'coloana', KEY_DELETE: 'scoate'}.get(cod)
	return {
		KEY_DELETE: 'scoate', KEY_TAB: 'coloana', KEY_PAGEUP: 'pagina_sus', KEY_PAGEDOWN: 'pagina_jos',
		KEY_HOME: 'inceput', KEY_END: 'sfarsit',
	}.get(cod)


def litera(cod):
	"""Litera unei taste (fara modificatori), pentru scrisul direct in cautare, sau None."""
	return LITERE.get(cod)


# ---------------------------------------------------------------- clipboardul (Ctrl+C / Ctrl+X / Ctrl+V)

class Clipboard(object):
	"""Ce s-a copiat sau taiat cu tastatura: referintele (din sursa sau din buchet), buchetul de unde vin si daca e o
	taiere (la lipire randurile se muta din buchetul lor, nu se copiaza). Ramane cat e deschis editorul."""

	def __init__(self):
		self.refs = []
		self.din_buchet = None
		self.indici = []
		self.taiere = False

	def pune(self, refs, din_buchet=None, indici=(), taiere=False):
		self.refs = list(refs)
		self.din_buchet = din_buchet
		self.indici = list(indici)
		self.taiere = bool(taiere and din_buchet is not None)

	def gol(self):
		return not self.refs

	def dupa_lipire(self):
		"""Dupa o lipire a unei taieri, ce a fost taiat nu se mai lipeste o data (randurile s-au mutat)."""
		if self.taiere:
			self.refs = []
			self.indici = []
			self.din_buchet = None
			self.taiere = False


# ---------------------------------------------------------------- textele de stare

def _forma_ro(unu, multe, n):
	try:
		import builtins
		f = getattr(getattr(builtins.__dict__.get('_'), '__self__', None), 'ngettext', None)
		if f is not None:
			return f(unu, multe, n)
	except Exception:
		pass
	return unu if n == 1 else multe


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural: in ro.po singularul cu litere, „o schimbare”, si pluralul fara „de”);
	pe PC, forma romaneasca. Numele e cel stiut de xgettext."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		return _forma_ro(unu, multe, n)
	return plural(unu, multe, n)


def text_nesalvate(n):
	"""„3 schimbări nesalvate”; gol la 0."""
	if not n:
		return ''
	return ngettext('%d schimbare nesalvată', '%d schimbări nesalvate', n) % n


def text_bifate(n):
	"""„2 rânduri bifate”; gol la 0."""
	if not n:
		return ''
	return ngettext('%d rând bifat', '%d rânduri bifate', n) % n


def text_canale(n):
	"""„24 canale” (numarul unui buchet sau al unei surse)."""
	return ngettext('%d canal', '%d canale', n) % n


# ---------------------------------------------------------------- locul listei de canale de unde se deschide editorul

# pozitia din referintele cablului si ale terestrului (namespace >> 16), cu numele lor din partea comuna
POZITII_SPECIALE = {0xFFFF: 'cablu', 0xEEEE: 'terestru'}


def loc_din_radacina(cale):
	"""Locul listei de canale (radacina ei, ca text de referinta) in editor: ('buchet', fisier), ('furnizor', nume),
	('satelit', pozitie), ('sateliti',), ('furnizori',), ('toate',) sau None. pozitie = namespace >> 16, ca in
	cererile listei (0..3599; 0xFFFF cablul, 0xEEEE terestrul). Furnizorii unui satelit (dosarul lui) dau satelitul."""
	import re
	t = cale or ''
	m = re.search(r'FROM BOUQUET "([^"]+)"', t)
	if m:
		return ('buchet', m.group(1))
	m = re.search(r'\(provider == "((?:[^"\\]|\\.)*)"\)', t)
	if m:
		return ('furnizor', m.group(1))
	m = re.search(r'\(satellitePosition == (-?\d+)\)', t)
	if m:
		return ('satelit', int(m.group(1)))
	if 'FROM SATELLITES' in t:
		return ('sateliti',)
	if 'FROM PROVIDERS' in t:
		return ('furnizori',)
	if '(type ==' in t and 'ORDER BY' in t:
		return ('toate',)
	return None


def pozitie_din_ns(n):
	"""Pozitia din referinta (namespace >> 16) -> pozitia partii comune (int sau „cablu” / „terestru”)."""
	return POZITII_SPECIALE.get(n, n)


# ---------------------------------------------------------------- ordinea rezultatelor cautarii

# grupul filtrelor editorului in selectia filtrelor (Screens/HdsEditorCanaleUnelte.FILTRE_EDITOR); nu e un grup al
# indexului cautarii
FILTRU_EDITOR = 'hds_editor'


def cuvinte_simple(text):
	"""Cuvintele unui nume pentru comparare: litere mici, fara diacritice, numai litere, cifre si „+”."""
	import re
	import unicodedata
	t = u''.join(c for c in unicodedata.normalize('NFKD', text or u'') if not unicodedata.combining(c)).lower()
	return re.sub(r'[^0-9a-z+]+', ' ', t).split()


def decodeaza(text):
	"""%xx dintr-o referinta (adresa unui flux), ca eServiceReference::decode."""
	import re
	return re.sub(r'%([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), text or '')


def e_referinta(text):
	"""Textul e o referinta de serviciu (1:0:19:2B66:3F3:1:C00000:0:0:0:), nu un nume."""
	import re
	return bool(re.match(r'^\d+:\d+:[0-9A-Fa-f]+(:[0-9A-Fa-f]*){7}:', (text or '').strip()))


def _simplu_tipar(text):
	import re
	import unicodedata
	t = u''.join(c for c in unicodedata.normalize('NFKD', text or u'') if not unicodedata.combining(c)).lower()
	return u' '.join(re.sub(r'[^0-9a-z+*?]+', ' ', t).split())


def potrivire_tipar(nume, tipar):
	"""„*” = oricate semne, „?” = unul, pe tot numele (fara diacritice si majuscule): „*sport” = se termina cu sport,
	„pro*” = incepe cu pro, „?tv” = trei semne cu tv la sfarsit."""
	import fnmatch
	return fnmatch.fnmatchcase(u' '.join(cuvinte_simple(nume)), _simplu_tipar(tipar))


def aproape(a, b):
	"""Doua cuvinte la o singura greseala: o litera schimbata, lipsa, in plus sau doua vecine schimbate intre ele."""
	if a == b:
		return True
	la, lb = len(a), len(b)
	if abs(la - lb) > 1:
		return False
	if la == lb:
		dif = [i for i in range(la) if a[i] != b[i]]
		if len(dif) == 1:
			return True
		return len(dif) == 2 and dif[1] == dif[0] + 1 and a[dif[0]] == b[dif[1]] and a[dif[1]] == b[dif[0]]
	if la > lb:
		a, b = b, a
	# b are o litera in plus
	i = 0
	while i < len(a) and a[i] == b[i]:
		i += 1
	return a[i:] == b[i + 1:]


MIN_TOLERANT = 4            # cuvintele mai scurte se cauta exact


def _aproape_in(w, text):
	"""O bucata din text (numele lipit, fara spatii) la o singura greseala de cuvantul w: „sprot” in „eurosport”."""
	n = len(w)
	for lung in (n, n - 1, n + 1):
		if lung < 1:
			continue
		for i in range(0, len(text) - lung + 1):
			bucata = text[i:i + lung]
			# prima litera e cea scrisa (sau primele doua schimbate intre ele): fara ea, „sprot” ar gasi „prot” din Pro TV
			if (bucata[0] == w[0] or bucata[:2] == w[1::-1]) and aproape(w, bucata):
				return True
	return False


def cauta_tolerant(canale, text, nume=lambda c: getattr(c, 'nume', '')):
	"""Canalele ale caror nume au fiecare cuvant cautat, cu o greseala in cuvintele de MIN_TOLERANT+ litere, oriunde in
	nume („sprot” gaseste „Sport 1” si „Eurosport”, „eurosprt” gaseste „Eurosport”)."""
	q = cuvinte_simple(text)
	if not q:
		return []
	rez = []
	for c in canale:
		cuv = cuvinte_simple(nume(c))
		if not cuv:
			continue
		lipit = u''.join(cuv)
		bun = True
		for w in q:
			if w in lipit:
				continue
			if len(w) < MIN_TOLERANT:
				bun = False
				break
			if not _aproape_in(w, lipit):
				bun = False
				break
		if bun:
			rez.append(c)
	return rez


def ordine_cautare(canale, text, nume=lambda c: getattr(c, 'nume', '')):
	"""Rezultatele cautarii cu numele care incep cu textul intai, apoi cele cu un cuvant care incepe cu el, apoi
	restul (numele care doar il contin, furnizorul, SID-ul, frecventa); in fiecare grupa ordinea primita ramane."""
	q = cuvinte_simple(text)
	if not q:
		return list(canale)
	lipit = u''.join(q)

	def rang(c):
		cuv = cuvinte_simple(nume(c))
		if u''.join(cuv).startswith(lipit):
			return 0
		if any(w.startswith(q[0]) for w in cuv):
			return 1
		return 2
	return sorted(canale, key=rang)
