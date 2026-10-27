# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Datele gestionarului de extensii (Screens/HdsExtensii.py). Doar in imaginea HDSatelit.

Citeste direct, fara comenzi, fisierele pe care opkg le tine pe receptor:
  - configurarea (/etc/opkg/*.conf): sursele (src, src/gz), arhitecturile, dosarele, verificarea semnaturii;
  - listele descarcate de `opkg update` (un fisier Packages pe sursa, in lists_dir);
  - starea pachetelor instalate (status_file) si fisierele fiecarui pachet (info_dir/<pachet>.list).
Instalarea, stergerea si actualizarea le face tot opkg (Components/Ipkg.py, fara shell); aici nu se porneste nimic.

Siguranta: textele din liste (nume, descrieri) sunt doar afisate. Un pachet se poate instala numai daca numele lui
trece de nume_valid() si exista intr-o sursa configurata (a HD Satelit sau una adaugata de utilizator in
/etc/opkg/hds-surse-utilizator.conf, scrisa doar de aici, cu nume si adrese verificate); un fisier .ipk doar de pe
stick, disc, retea sau /tmp. Pachetele din afara sursei HD Satelit sunt aratate ca atare (sursa si adresa).
Modulul nu depinde de enigma, ca sa poata fi incercat si pe PC (parametrul radacina)."""
import os
import posixpath
import re
import tarfile
import io
import time
import zlib
try:
	from urllib.parse import urlsplit
except ImportError:  # Python 2 (doar pentru teste vechi)
	from urlparse import urlsplit
try:
	import _thread as _fire
except ImportError:  # Python 2 (doar pentru teste vechi)
	import thread as _fire

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text
# ceasul pentru durata cautarii: ora receptorului sare la pornire (TDT, NTP), iar „raspunde greu” nu trebuie sa apara
# din saritura (Python 2: time.time)
_ceas = getattr(time, 'monotonic', time.time)
try:
	from Components.HdsNavigator import readMountTable, NETWORK_FS
except ImportError:  # teste pe PC: modulul incarcat singur, din dosarul Components
	from HdsNavigator import readMountTable, NETWORK_FS
# pachetele numai pentru Python 2 (0.6.8): dupa lista feedului (Pachet.python2) si dupa fisier (FisierIpk.python2)
try:
	from Components import HdsPython2 as H
except ImportError:  # teste pe PC
	try:
		import HdsPython2 as H
	except ImportError:  # modulul incarcat singur, dintr-o cale: vecinul din acelasi dosar
		import importlib.util
		_spec = importlib.util.spec_from_file_location('HdsPython2',
			os.path.join(os.path.dirname(os.path.abspath(__file__)), 'HdsPython2.py'))
		H = importlib.util.module_from_spec(_spec)
		_spec.loader.exec_module(H)

PREFIX = 'enigma2-plugin-'

def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


# categoriile, in ordinea filelor; eticheta si icoana (skinul: liste/ext_<icoana>_<88|160>.png, HdsExtensiiImage)
CATEGORII = (
	('extensions', N_('Extensii'), 'extensii'),
	('systemplugins', N_('Setări de sistem'), 'sistem'),
	('skins', N_('Skinuri'), 'skinuri'),
	('acces', N_('Acces condiționat'), 'emulatoare'),
	('settings', N_('Liste de canale'), 'liste'),
	('picons', N_('Sigle canale'), 'sigle'),
	('drivers', N_('Drivere'), 'sistem'),
	('display', N_('Afișaj'), 'sistem'),
	('weblinks', N_('Legături web'), 'extensii'),
	('altele', N_('Altele'), 'altele'),
)
# categoria pachetelor modulelor de acces in feedurile enigma2: un cuvant (numai litere mici) care se termina in "cams"
TIPAR_CATEGORIE_ACCES = re.compile(r'^[a-z]+cams$')
ETICHETE = dict((c, e) for c, e, _i in CATEGORII)
ICOANE = dict((c, i) for c, _e, i in CATEGORII)
ORDINE = dict((c, n) for n, (c, _e, _i) in enumerate(CATEGORII))

# pachete care nu se arata (se instaleaza doar ca dependente): codul comun al pluginurilor HD Satelit
ASCUNSE = frozenset(('enigma2-plugin-extensions-hdsatelit-comun',))
SUFIXE_ASCUNSE = ('-dev', '-dbg', '-doc', '-src', '-staticdev', '-po', '-meta')

# un nume de pachet opkg: litere mici, cifre si + - . ; niciodata un inceput cu '-' (ar fi citit ca optiune)
# (acelasi tipar ca in Components/Ipkg.py, care il verifica din nou chiar inainte de pornirea opkg)
# \Z, nu $: $ lasa sa treaca un rand nou la sfarsit ("Package: x" urmat de un rand " ." in lista)
_NUME = re.compile(r'^[a-z0-9][a-z0-9+.\-]{0,120}\Z')

# sursele HD Satelit: adresa pe hdsatelit.com (sau un subdomeniu); celelalte sunt surse externe
DOMENIU_HDS = 'hdsatelit.com'
# fisierul cu sursele adaugate de utilizator (scris doar de gestionar)
FISIER_SURSE_UTILIZATOR = '/etc/opkg/hds-surse-utilizator.conf'
_NUME_SURSA = re.compile(r'^[a-z0-9][a-z0-9_.\-]{0,31}\Z')
_ADRESA_SURSA = re.compile(r'^https?://[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,252})(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~%/+\-]*)?\Z')
# de unde se poate instala un fisier .ipk (ca in Components/Ipkg.py: PACKAGE_FILE_ROOTS, fara dosarul imaginii)
RADACINI_FISIERE = ('/media', '/hdd', '/mnt', '/autofs', '/tmp')
# locurile de retea in care cautarea fisierelor .ipk nu intra singura (doar cand utilizatorul le deschide): cele
# obisnuite ale imaginilor enigma2 si orice montare de retea din /proc/mounts (tipurile din Components/HdsNavigator.py,
# plus autofs: o intrare in dosarul automontarii porneste montarea); o sursa //server/... e tot retea
LOCURI_RETEA = ('/media/net', '/media/autofs', '/autofs')
TIPURI_RETEA = tuple(NETWORK_FS) + ('autofs', 'ncpfs', 'fuse.rclone')

# un pachet e „din imagine" daca a fost instalat odata cu imaginea (in aceeasi fereastra de timp cu primul pachet)
FEREASTRA_IMAGINE = 6 * 3600


def nume_valid(nume):
	return isinstance(nume, str) and _NUME.match(nume) is not None


# ---------------------------------------------------------------- versiuni (algoritmul dpkg/opkg)

def _ordine(c):
	if c.isdigit():
		return 0
	if c.isascii() and c.isalpha():
		return ord(c)
	if c == '~':
		return -1
	return ord(c) + 256


def _verrevcmp(a, b):
	i = j = 0
	la, lb = len(a), len(b)
	while i < la or j < lb:
		while (i < la and not a[i].isdigit()) or (j < lb and not b[j].isdigit()):
			ac = _ordine(a[i]) if i < la and not a[i].isdigit() else 0
			bc = _ordine(b[j]) if j < lb and not b[j].isdigit() else 0
			if ac != bc:
				return -1 if ac < bc else 1
			if i < la and not a[i].isdigit():
				i += 1
			if j < lb and not b[j].isdigit():
				j += 1
		while i < la and a[i] == '0':
			i += 1
		while j < lb and b[j] == '0':
			j += 1
		diferenta = 0
		while i < la and a[i].isdigit() and j < lb and b[j].isdigit():
			if not diferenta:
				diferenta = ord(a[i]) - ord(b[j])
			i += 1
			j += 1
		if i < la and a[i].isdigit():
			return 1
		if j < lb and b[j].isdigit():
			return -1
		if diferenta:
			return -1 if diferenta < 0 else 1
	return 0


def _desparte(v):
	v = (v or '').strip()
	epoca = 0
	if ':' in v:
		e, v = v.split(':', 1)
		try:
			epoca = int(e)
		except ValueError:
			epoca = 0
	if '-' in v:
		v, rev = v.rsplit('-', 1)
	else:
		rev = ''
	return epoca, v, rev


def compara_versiuni(a, b):
	"""-1, 0 sau 1, ca `opkg compare-versions`."""
	ea, va, ra = _desparte(a)
	eb, vb, rb = _desparte(b)
	if ea != eb:
		return -1 if ea < eb else 1
	r = _verrevcmp(va, vb)
	if r:
		return r
	return _verrevcmp(ra, rb)


# ---------------------------------------------------------------- texte

def marime_text(octeti):
	"""34 KB, 1,2 MB, 2,3 GB (virgula romaneasca); '' daca nu se stie."""
	try:
		n = int(octeti)
	except (TypeError, ValueError):
		return ''
	if n <= 0:
		return ''
	if n < 1024:
		return '%d B' % n
	if n < 1024 * 1024:
		return '%d KB' % max(1, int(round(n / 1024.0)))
	mb = n / (1024.0 * 1024.0)
	if mb < 10:
		return ('%.1f MB' % mb).replace('.', ',')
	if mb < 1024:
		return '%d MB' % int(round(mb))
	gb = mb / 1024.0
	if gb < 10:
		return ('%.1f GB' % gb).replace('.', ',')
	return '%d GB' % int(round(gb))


_ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]')


def text_utf8(text):
	"""textul care se poate trimite interfetei: un nume de fisier care nu e UTF-8 (stick FAT montat fara utf8) vine
	din Python cu surogate (surrogateescape), pe care lista le-ar da mai departe ca NULL (elistboxcontent.cpp) si
	setText le refuza; aici devin '?'"""
	text = text or ''
	try:
		text.encode('utf-8')
		return text
	except UnicodeEncodeError:
		return text.encode('utf-8', 'replace').decode('utf-8')


def e_utf8(text):
	"""True daca textul (o cale) se poate da ca argument unui program: fara surogate"""
	try:
		text.encode('utf-8')
		return True
	except (UnicodeEncodeError, AttributeError):
		return False


def _curat(text, maxim=400):
	"""Textul din liste, doar pentru afisare: fara secvente de terminal si caractere de control, cel mult `maxim`
	caractere."""
	text = _ANSI.sub('', text_utf8(text))
	text = ''.join(ch if (ch == '\n' or (ch >= ' ' and ch != '\x7f')) else ' ' for ch in text)
	text = re.sub(r'[ \t]+', ' ', text).strip()
	if len(text) > maxim:
		text = text[:maxim - 1].rstrip() + '…'
	return text


def _functie_incape(incape):
	"""`incape`: numarul de semne care incap sau o functie(text) -> True cand textul incape (latimea masurata pe ecran)"""
	if callable(incape):
		return incape
	return lambda text: len(text) <= incape


def _cel_mai_lung(incape, k_maxim, fa):
	"""fa(k) cu cel mai mare k din 0..k_maxim care incape (latimea creste cu k); None cand nici fa(0) nu incape"""
	if not incape(fa(0)):
		return None
	jos, sus = 0, k_maxim
	while jos < sus:
		k = (jos + sus + 1) // 2
		if incape(fa(k)):
			jos = k
		else:
			sus = k - 1
	return fa(jos)


def scurt_sfarsit(text, incape):
	"""textul taiat la sfarsit cu „…” cat sa incapa (vezi _functie_incape)"""
	incape = _functie_incape(incape)
	text = text or ''
	if incape(text):
		return text
	rez = _cel_mai_lung(incape, len(text) - 1, lambda k: text[:k].rstrip() + '…')
	return rez if rez is not None else '…'


def scurt_la_cuvant(text, incape):
	"""textul taiat dupa ultimul cuvant intreg care incape, cu „…” (vezi _functie_incape); pentru un paragraf pe mai
	multe randuri, unde `incape` masoara inaltimea textului asezat. Virgula sau punctul si virgula de dinaintea taieturii
	nu raman langa „…”. Cand nici primul cuvant nu incape, taietura e ca in scurt_sfarsit."""
	incape = _functie_incape(incape)
	text = text or ''
	if incape(text):
		return text
	parti = re.findall(r'\S+\s*', text)
	rez = None
	if len(parti) > 1:
		rez = _cel_mai_lung(incape, len(parti) - 1, lambda k: ''.join(parti[:k]).rstrip().rstrip(',;:') + '…')
	if rez is None or rez == '…':
		return scurt_sfarsit(text, incape)
	return rez


def scurt_mijloc(text, incape):
	"""o cale scurtata cu „…” la mijloc cat sa incapa (vezi _functie_incape): numele fisierului ramane intreg si se taie
	dosarele dinaintea lui (/media/usb/Pach…/nume.ipk); cand nici numele nu incape, se vad inceputul caii si
	sfarsitul numelui, cu „…” intre ele"""
	incape = _functie_incape(incape)
	text = text or ''
	if incape(text):
		return text
	i = text.rfind('/')
	if i > 0:
		dosar, nume = text[:i], text[i:]
		rez = _cel_mai_lung(incape, len(dosar) - 1, lambda k: dosar[:k] + '…' + nume)
		if rez is not None:
			return rez
	n = len(text)
	rez = _cel_mai_lung(incape, n - 1, lambda k: text[:k // 3] + '…' + text[n - (k - k // 3):] if k else '…')
	return rez if rez is not None else '…'


def categorie_din_nume(nume):
	"""Categoria din numele pachetului (enigma2-plugin-<categorie>-<nume>). Categoria modulelor de acces se recunoaste
	dupa forma, fara numele ei in cod: un cuvant care se termina in "cams" (TIPAR_CATEGORIE_ACCES) da cheia 'acces'."""
	if not nume.startswith(PREFIX):
		return 'altele'
	rest = nume[len(PREFIX):]
	cat = rest.split('-', 1)[0]
	if cat in ETICHETE:
		return cat
	return 'acces' if TIPAR_CATEGORIE_ACCES.match(cat) else 'altele'


def nume_scurt(nume):
	if nume.startswith(PREFIX):
		rest = nume[len(PREFIX):]
		if '-' in rest:
			return rest.split('-', 1)[1]
		return rest
	return nume


def se_arata(nume):
	if not nume.startswith(PREFIX) or nume in ASCUNSE:
		return False
	if nume.endswith(SUFIXE_ASCUNSE) or '-locale-' in nume:
		return False
	return True


# ---------------------------------------------------------------- fisierele opkg

def _cale(radacina, p):
	if not radacina or radacina == '/':
		return p
	return os.path.join(radacina, p.lstrip('/'))


class Configurare(object):
	def __init__(self):
		self.surse = []                 # (nume, adresa)
		self.fisier_sursa = {}          # nume -> fisierul .conf in care e scrisa
		self.arhitecturi = {}           # arhitectura -> prioritate
		self.lists_dir = '/var/lib/opkg/lists'
		self.status_file = '/var/lib/opkg/status'
		self.info_dir = '/var/lib/opkg/info'
		self.cache_dir = '/var/cache/opkg'  # option cache_dir: pachetele descarcate (in RAM pe receptor)
		self.semnatura = False          # option check_signature 1

	def nume_surse(self):
		return [n for n, _a in self.surse]

	def adresa(self, nume):
		for n, a in self.surse:
			if n == nume:
				return a
		return ''

	def e_hdsatelit(self, nume):
		return sursa_hdsatelit(self.adresa(nume))

	def e_a_utilizatorului(self, nume):
		fisier = self.fisier_sursa.get(nume, '')
		return bool(fisier) and os.path.basename(fisier) == os.path.basename(FISIER_SURSE_UTILIZATOR)


def sursa_hdsatelit(adresa):
	"""adresa unei surse HD Satelit: pe hdsatelit.com sau pe un subdomeniu al lui"""
	try:
		parti = urlsplit(adresa or '')
		gazda = (parti.hostname or '').lower()
	except ValueError:
		return False
	# doar https: pe http lista si pachetele pot fi schimbate pe drum (router, retea), deci nu se arata ca verificate
	if parti.scheme != 'https':
		return False
	return gazda == DOMENIU_HDS or gazda.endswith('.' + DOMENIU_HDS)


def gazda(adresa):
	try:
		return (urlsplit(adresa or '').hostname or '').lower()
	except ValueError:
		return ''


def citeste_configurarea(radacina='/'):
	c = Configurare()
	fisiere = []
	principal = _cale(radacina, '/etc/opkg/opkg.conf')
	if os.path.isfile(principal):
		fisiere.append(principal)
	vechi = _cale(radacina, '/etc/opkg.conf')
	if os.path.isfile(vechi):
		fisiere.append(vechi)
	dosar = _cale(radacina, '/etc/opkg')
	try:
		for f in sorted(os.listdir(dosar)):
			p = os.path.join(dosar, f)
			if f.endswith('.conf') and p not in fisiere and os.path.isfile(p):
				fisiere.append(p)
	except OSError:
		pass
	vazute = set()
	for p in fisiere:
		try:
			with open(p, 'r', encoding='utf-8', errors='replace') as fh:
				randuri = fh.read().splitlines()
		except OSError:
			continue
		for r in randuri:
			parti = r.split()
			if not parti or parti[0].startswith('#'):
				continue
			cheie = parti[0]
			if cheie in ('src', 'src/gz') and len(parti) >= 3:
				if parti[1] not in vazute:
					vazute.add(parti[1])
					c.surse.append((parti[1], parti[2]))
					c.fisier_sursa[parti[1]] = p
			elif cheie == 'arch' and len(parti) >= 3:
				try:
					c.arhitecturi[parti[1]] = int(parti[2])
				except ValueError:
					pass
			elif cheie == 'option' and len(parti) >= 3:
				if parti[1] == 'lists_dir':
					c.lists_dir = parti[-1]
				elif parti[1] == 'status_file':
					c.status_file = parti[2]
				elif parti[1] == 'info_dir':
					c.info_dir = parti[2]
				elif parti[1] == 'cache_dir':
					c.cache_dir = parti[2]
				elif parti[1] == 'check_signature':
					c.semnatura = parti[2] not in ('0', 'false', 'no')
			elif cheie == 'lists_dir' and len(parti) >= 2:
				c.lists_dir = parti[-1]
	return c


def citeste_strofe(cale):
	"""Fisierele Packages / status / .control: cate un dict pe pachet (cheile cu litere mici). Randurile de
	continuare (care incep cu spatiu) se adauga la campul de dinainte; ' .' e un rand gol."""
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as fh:
			text = fh.read()
	except OSError:
		return []
	return strofe_din_text(text)


def strofe_din_text(text):
	rez = []
	cur = {}
	ultima = None
	for r in text.split('\n'):
		if not r.strip():
			if cur:
				rez.append(cur)
			cur = {}
			ultima = None
			continue
		if r[0] in ' \t':
			if ultima is not None:
				r2 = r.strip()
				cur[ultima] += '\n' + ('' if r2 == '.' else r2)
			continue
		if ':' not in r:
			continue
		k, v = r.split(':', 1)
		ultima = k.strip().lower()
		cur[ultima] = v.strip()
	if cur:
		rez.append(cur)
	return rez


def _int(v):
	try:
		return int(v)
	except (TypeError, ValueError):
		return 0


def _dependente(text):
	rez = []
	for parte in (text or '').split(','):
		for alt in parte.split('|'):
			n = alt.strip().split(' ', 1)[0].split('(', 1)[0].strip()
			if n and n not in rez:
				rez.append(n)
				break
	return rez


# ---------------------------------------------------------------- catalogul

class Pachet(object):
	__slots__ = ('nume', 'categorie', 'titlu', 'subtitlu', 'descriere', 'versiune', 'versiune_instalata',
		'marime', 'marime_instalat', 'sursa', 'depinde', 'din_imagine', 'arhitectura', 'dosar_plugin', 'fisier', 'arhiva',
		'python2')

	def __init__(self, nume):
		self.nume = nume
		self.categorie = categorie_din_nume(nume)
		self.titlu = nume_scurt(nume)
		self.subtitlu = ''
		self.descriere = ''
		self.versiune = ''              # cea mai noua versiune din surse ('' = nu e in nicio sursa)
		self.versiune_instalata = ''    # '' = nu e instalat
		self.marime = 0
		self.marime_instalat = 0
		self.sursa = ''
		self.depinde = []
		self.din_imagine = False
		self.arhitectura = ''
		self.dosar_plugin = ''
		self.fisier = ''                # Filename din lista sursei (calea pachetului fata de adresa sursei)
		self.arhiva = ''                # arhiva sursei de langa pachet (randul "Source archive:" din descriere)
		# versiunea din surse e numai pentru Python 2 (dupa Depends din lista, Components/HdsPython2.py): (cod, detaliu)
		# al motivului, altfel None. Un asemenea pachet nu se instaleaza si nu e o actualizare (0.6.8)
		self.python2 = None

	@property
	def instalat(self):
		return bool(self.versiune_instalata)

	@property
	def disponibil(self):
		return bool(self.versiune)

	@property
	def actualizare(self):
		return self.instalat and self.disponibil and not self.python2 and \
			compara_versiuni(self.versiune, self.versiune_instalata) > 0

	@property
	def se_poate_sterge(self):
		# si cele venite cu imaginea (confirmarea spune asta si daca se mai pot pune la loc)
		return self.instalat and nume_valid(self.nume)

	@property
	def se_poate_instala(self):
		return self.disponibil and nume_valid(self.nume) and not self.python2 and (not self.instalat or self.actualizare)

	def texte(self, rezumat, extins):
		"""Titlul (scurt, pentru lista), randul de sub titlu si descrierea din detalii."""
		rezumat = _curat(rezumat, 120)
		extins = _curat(extins, 600)
		if rezumat and len(rezumat) <= 34:
			self.titlu = rezumat
			self.subtitlu = extins.split('\n', 1)[0] if extins else ''
			self.descriere = extins
		else:
			scurt = nume_scurt(self.nume).replace('-', ' ')
			self.titlu = scurt[:1].upper() + scurt[1:]
			self.subtitlu = rezumat
			self.descriere = (rezumat + ('\n' + extins if extins else '')).strip()


# randul descrierii care numeste arhiva sursei, pusa langa pachet in feed (pachetele feedului pluginurilor externe:
# "Source archive: <nume>-<versiune>.tar.gz, next to this package in the feed."); numai un nume de fisier, fara dosare
_ARHIVA_SURSA = re.compile(r'(?:^|\n)[ \t]*Source archive:[ \t]*([A-Za-z0-9][A-Za-z0-9._+~\-]{0,200}?\.(?:tar\.gz|tar\.xz|tar\.bz2|tar\.zst|tgz|zip))(?=[\s,;]|\Z)')


def arhiva_sursa(descriere):
	"""numele arhivei sursei din descrierea unui pachet (randul "Source archive: <fisier>"), sau ''"""
	m = _ARHIVA_SURSA.search(descriere or '')
	return m.group(1) if m else ''


def _text_descriere(strofa):
	d = strofa.get('description', '')
	if '\n' in d:
		rezumat, extins = d.split('\n', 1)
	else:
		rezumat, extins = d, ''
	extins = '\n'.join(x for x in extins.split('\n')).strip()
	return rezumat, extins


class Catalog(object):
	def __init__(self):
		self.configurare = Configurare()
		self.pachete = {}               # nume -> Pachet (doar cele care se arata)
		self.dupa_dosar = {}            # dosarul pluginului (.../Plugins/Cat/Nume) -> numele pachetului
		self.varsta_liste = 0           # mtime-ul celei mai noi liste (0 = nicio lista)
		self.surse_cu_lista = []
		self.erori = []
		self._toate = {}                # si pachetele ascunse (dependentele), pentru textul confirmarii

	def categorii(self):
		"""Categoriile care au macar un pachet, in ordinea filelor, cu numarul lor."""
		numar = {}
		for p in self.pachete.values():
			numar[p.categorie] = numar.get(p.categorie, 0) + 1
		return [(c, _t(ETICHETE[c]), numar[c]) for c, _e, _i in CATEGORII if c in numar]

	def din_categoria(self, categorie):
		rez = [p for p in self.pachete.values() if p.categorie == categorie]
		rez.sort(key=lambda p: (p.titlu.lower(), p.nume))
		return rez

	def actualizari(self):
		rez = [p for p in self.pachete.values() if p.actualizare]
		rez.sort(key=lambda p: (p.titlu.lower(), p.nume))
		return rez

	def cauta(self, text):
		t = (text or '').strip().lower()
		if not t:
			return []
		rez = [p for p in self.pachete.values()
			if t in p.titlu.lower() or t in p.nume.lower() or t in p.subtitlu.lower()]
		rez.sort(key=lambda p: (not p.titlu.lower().startswith(t), p.titlu.lower(), p.nume))
		return rez

	def pachet_pentru_dosar(self, dosar):
		n = self.dupa_dosar.get((dosar or '').rstrip('/'))
		return self.pachete.get(n) if n else None

	def dependente_de_instalat(self, pachet):
		"""Dependentele din surse care nu sunt instalate (doar pentru textul confirmarii), cu nume afisabile."""
		rez = []
		for n in pachet.depinde:
			p = self._toate.get(n)
			if p is not None and not p.instalat and p.disponibil:
				rez.append(p)
		return rez


def _arhitectura_buna(arh, arhitecturi):
	if not arhitecturi:
		return True
	return arh in arhitecturi


def incarca(radacina='/'):
	"""Tot catalogul. Nu arunca exceptii: ce nu se poate citi ajunge in catalog.erori."""
	cat = Catalog()
	try:
		cat.configurare = citeste_configurarea(radacina)
	except Exception as e:
		cat.erori.append('configurare: %s' % e)
	conf = cat.configurare
	toate = {}

	# 1. listele din surse
	dosar_liste = _cale(radacina, conf.lists_dir)
	cu_python2 = set()               # sursele care au Python 2 insusi (python-core 2.x): feeduri ale imaginilor vechi
	for sursa, _adresa in conf.surse:
		f = os.path.join(dosar_liste, sursa)
		if not os.path.isfile(f):
			continue
		try:
			cat.varsta_liste = max(cat.varsta_liste, int(os.path.getmtime(f)))
		except OSError:
			pass
		cat.surse_cu_lista.append(sursa)
		for s in citeste_strofe(f):
			n = s.get('package', '')
			if not nume_valid(n) or not n.startswith(PREFIX):
				if H.e_python2_insusi(s):
					cu_python2.add(sursa)
				continue
			arh = s.get('architecture', '')
			if not _arhitectura_buna(arh, conf.arhitecturi):
				continue
			p = toate.get(n)
			v = s.get('version', '')
			if p is not None and p.versiune:
				r = compara_versiuni(v, p.versiune)
				# aceeasi versiune: arhitectura cu prioritatea mai mare (ca opkg)
				if r < 0 or (r == 0 and conf.arhitecturi.get(arh, 0) <= conf.arhitecturi.get(p.arhitectura, 0)):
					continue
			if p is None:
				p = toate[n] = Pachet(n)
			p.versiune = v
			p.arhitectura = arh
			p.marime = _int(s.get('size'))
			p.marime_instalat = _int(s.get('installed-size'))
			p.sursa = sursa
			p.depinde = _dependente(s.get('depends', ''))
			p.texte(*_text_descriere(s))
			p.fisier = s.get('filename', '')
			p.arhiva = arhiva_sursa(s.get('description', ''))
			# 0.6.8: dupa Depends (None = nu se stie, False = cere ceva din Python 3, altfel motivul Python 2)
			v2 = H.din_control(s)
			p.python2 = v2.motiv if v2.python2 else v2.python2

	# 1b. pachetele cu cod Python din feedurile imaginilor cu Python 2 (grupul sursei are python-core 2.x), care nu cer
	# nimic din Python 3: facute pentru Python 2 (0.6.8)
	if cu_python2:
		grupe = set(H.grup_sursa(conf.adresa(x)) for x in cu_python2)
		for p in toate.values():
			if p.python2 is None and p.sursa and p.categorie in H.FELURI_COD and \
					H.grup_sursa(conf.adresa(p.sursa)) in grupe:
				p.python2 = (H.FEED, p.sursa)

	# 2. pachetele instalate
	status = _cale(radacina, conf.status_file)
	instalate = []
	primul = 0
	for s in citeste_strofe(status):
		n = s.get('package', '')
		st = s.get('status', '')
		if not n or 'installed' not in st.split() or 'not-installed' in st:
			continue
		t = _int(s.get('installed-time'))
		if t and (not primul or t < primul):
			primul = t
		instalate.append((n, s, t))
	dosar_info = _cale(radacina, conf.info_dir)
	for n, s, t in instalate:
		if not n.startswith(PREFIX) or not nume_valid(n):
			continue
		p = toate.get(n)
		if p is None:
			p = toate[n] = Pachet(n)
			control = citeste_strofe(os.path.join(dosar_info, n + '.control'))
			sursa_text = control[0] if control else s
			p.texte(*_text_descriere(sursa_text))
			p.arhiva = arhiva_sursa(sursa_text.get('description', ''))
			p.marime_instalat = _int(sursa_text.get('installed-size'))
			p.depinde = _dependente(s.get('depends', ''))
		p.versiune_instalata = s.get('version', '') or '?'
		p.din_imagine = bool(primul and t and t - primul <= FEREASTRA_IMAGINE)

	# 3. ce plugin (dosar) tine fiecare pachet instalat
	for n, _s, _t in instalate:
		if not n.startswith('enigma2'):
			continue
		for r in _randuri(os.path.join(dosar_info, n + '.list')):
			r = r.split('\t', 1)[0].strip()
			if '/Plugins/' in r and (r.endswith('/plugin.py') or r.endswith('/plugin.pyc')):
				dosar = r.rsplit('/', 1)[0]
				cat.dupa_dosar[dosar] = n
				if n in toate:
					toate[n].dosar_plugin = dosar

	cat._toate = toate
	cat.pachete = dict((n, p) for n, p in toate.items() if se_arata(n))
	return cat


def _randuri(cale):
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as fh:
			return fh.read().splitlines()
	except OSError:
		return []


def text_varsta(momentul, acum=None):
	"""„azi, 14:32", „ieri, 09:10", „31.12, 18:00"."""
	if not momentul:
		return ''
	acum = acum or time.time()
	a = time.localtime(acum)
	m = time.localtime(momentul)
	if (a.tm_year, a.tm_yday) == (m.tm_year, m.tm_yday):
		zi = _t('azi')
	elif (acum - momentul) < 2 * 86400 and time.localtime(acum - 86400).tm_yday == m.tm_yday:
		zi = _t('ieri')
	else:
		zi = '%02d.%02d' % (m.tm_mday, m.tm_mon)
	return '%s, %02d:%02d' % (zi, m.tm_hour, m.tm_min)


# ---------------------------------------------------------------- sursele adaugate de utilizator

_FARA_DIACRITICE = dict(zip(map(ord, 'ăâîșşțţĂÂÎȘŞȚŢ'), 'aaissttAAISSTT'))


def curata_nume_sursa(text):
	"""din ce a scris utilizatorul: litere mici fara diacritice, spatiile devin '-', restul semnelor dispar"""
	text = (text or '').strip().translate(_FARA_DIACRITICE).lower()
	text = re.sub(r'\s+', '-', text)
	text = re.sub(r'[^a-z0-9_.\-]', '', text)
	return text.lstrip('-_.')[:32]


def verifica_sursa(nume, adresa, existente=()):
	"""None daca sursa se poate adauga, altfel motivul, pentru ecran. Opkg citeste fisierul pe cuvinte si randuri,
	deci un nume sau o adresa cu spatii, ghilimele sau randuri noi ar putea adauga optiuni: nu trec de tipare."""
	if not nume or not _NUME_SURSA.match(nume):
		return _t('Numele poate avea doar litere mici, cifre și semnele - _ . (cel mult 32).')
	if nume in existente:
		return _t('Există deja o sursă cu numele „%s”.') % nume
	if not adresa or len(adresa) > 300 or not _ADRESA_SURSA.match(adresa):
		return _t('Adresa trebuie să înceapă cu http:// sau https:// și să nu aibă spații sau semne speciale.')
	return None


def citeste_surse_utilizator(radacina='/'):
	"""[(nume, adresa)] din fisierul utilizatorului; un rand care nu trece verificarea e sarit"""
	rez = []
	for r in _randuri(_cale(radacina, FISIER_SURSE_UTILIZATOR)):
		parti = r.split()
		if len(parti) == 3 and parti[0] in ('src', 'src/gz') and verifica_sursa(parti[1], parti[2], [n for n, _a in rez]) is None:
			rez.append((parti[1], parti[2]))
	return rez


def scrie_surse_utilizator(surse, radacina='/'):
	"""scrie fisierul utilizatorului doar cu randuri `src/gz nume adresa` verificate; intai .nou, apoi rename.
	Intoarce None sau textul erorii."""
	randuri = ['# Surse de pachete adaugate din gestionarul de extensii HDSatelit. Nu sunt verificate de HD Satelit.']
	vazute = []
	for nume, adresa in surse:
		motiv = verifica_sursa(nume, adresa, vazute)
		if motiv:
			return motiv
		vazute.append(nume)
		randuri.append('src/gz %s %s' % (nume, adresa))
	cale = _cale(radacina, FISIER_SURSE_UTILIZATOR)
	nou = cale + '.nou'
	try:
		dosar = os.path.dirname(cale)
		if not os.path.isdir(dosar):
			os.makedirs(dosar)
		if not surse:
			if os.path.exists(cale):
				os.remove(cale)
			return None
		with open(nou, 'w', encoding='utf-8') as fh:
			fh.write('\n'.join(randuri) + '\n')
			fh.flush()
			os.fsync(fh.fileno())
		os.replace(nou, cale)       # ca rename pe receptor; si peste un fisier existent pe PC (probe)
	except (OSError, IOError) as e:
		try:
			os.remove(nou)
		except OSError:
			pass
		return _t('Fișierul surselor nu s-a putut scrie (%s).') % (getattr(e, 'strerror', None) or e)
	return None


# ---------------------------------------------------------------- cache-ul opkg

def curata_cache(radacina='/', lacat='/var/run/opkg.lock'):
	"""Sterge pachetele (.ipk) descarcate de opkg in cache_dir, dupa o instalare: pe receptor cache-ul e in RAM
	(/var/cache -> /var/volatile/cache) si opkg le tinea pana la repornire (0.6.6; un pachet al imaginii are ~20 MB).
	Numai cu lacatul lui opkg luat (lockf, fara asteptare): cat ruleaza alt opkg nu se atinge nimic (ar putea instala
	chiar un fisier de acolo). Listele din cache (*_Packages.gz) raman. Intoarce numarul fisierelor sterse, sau None
	cand ruleaza alt opkg."""
	conf = citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.cache_dir)
	try:
		nume = [n for n in os.listdir(dosar) if n.endswith('.ipk')]
	except OSError:
		return 0
	if not nume:
		return 0
	fd = None
	try:
		import fcntl
	except ImportError:            # probele de pe Windows: fara lacat
		fcntl = None
	if fcntl is not None:
		try:
			fd = os.open(_cale(radacina, lacat), os.O_RDWR | os.O_CREAT, 0o644)
		except OSError:
			return None
		try:
			fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
		except (IOError, OSError):
			os.close(fd)
			return None
	sterse = 0
	try:
		for n in nume:
			p = os.path.join(dosar, n)
			try:
				if os.path.isfile(p) and not os.path.islink(p):
					os.remove(p)
					sterse += 1
			except OSError:
				pass
	finally:
		if fd is not None:
			try:
				fcntl.lockf(fd, fcntl.LOCK_UN)
			except (IOError, OSError):
				pass
			os.close(fd)
	return sterse


# ---------------------------------------------------------------- pachetele neconfigurate si jurnalele pe disc

# starile din Status (opkg) ale unui pachet despachetat dar neconfigurat: scriptul lui de dupa instalare (postinst) a
# cazut sau instalarea s-a oprit la jumatate
STARI_NECONFIGURATE = ('unpacked', 'half-configured', 'half-installed')
# jurnalele care trebuie sa ramana dupa repornire stau in dosarul jurnalelor de pe memoria interna (il arata Jurnalele
# sistemului pe televizor si in interfata web); fiecare cel mult MARIME_JURNAL, plus o copie veche (<nume>.1)
DOSAR_JURNALE = '/home/root/logs'
MARIME_JURNAL = 128 * 1024
# numele si parola dintr-o adresa (https://nume:parola@gazda/...): opkg le scrie in "Downloading ..." si in erorile
# wget pentru sursele adaugate de om cu ele in adresa; in jurnalele de pe disc nu ajung
_PAROLA_IN_ADRESA = re.compile(r'(?i)\b((?:https?|ftps?)://)[^/\s@]+@')


def fara_parola(text):
	"""text fara numele si parola din adrese: https://nume:parola@gazda -> https://gazda"""
	return _PAROLA_IN_ADRESA.sub(r'\1', text if isinstance(text, str) else str(text))


def pachete_neconfigurate(radacina='/', conf=None):
	"""Numele pachetelor din status-ul opkg ramase neconfigurate (STARI_NECONFIGURATE), in ordine. opkg 0.8.0 incearca
	sa le configureze din nou la sfarsitul ORICAREI instalari (opkg_configure_packages) si iese cu 255 cand unul cade
	iar, chiar daca pachetele cerute s-au instalat bine."""
	conf = conf or citeste_configurarea(radacina)
	rez = []
	for s in citeste_strofe(_cale(radacina, conf.status_file)):
		n = s.get('package', '')
		stare = s.get('status', '').split()
		if n and any(x in stare for x in STARI_NECONFIGURATE):
			rez.append(n)
	return sorted(set(rez))


def scrie_jurnal_rotit(cale, text, maxim=MARIME_JURNAL, sincron=False):
	"""Adauga text la jurnalul `cale`. Cand ar trece de `maxim` octeti, jurnalul de pana acum trece in <cale>.1 (unul
	singur vechi; cel dinainte se pierde), deci pe disc stau cel mult 2 x maxim. Dosarul trebuie sa existe (pe receptor
	DOSAR_JURNALE il face paznicul la pornire; nu se face de aici, ca probele de pe PC sa nu scrie in afara dosarelor
	lor); fara legaturi simbolice (O_NOFOLLOW, si o legatura pusa in locul fisierului nu se urmeaza), fisier nou cu
	drepturile 0600. sincron: fsync dupa scriere (o repornire dura a receptorului, de pilda de la watchdogul HW, lasa
	altfel randurile din ultimul minut zerouri pe eMMC). False la orice eroare (nu arunca)."""
	date = (text if isinstance(text, str) else str(text)).encode('utf-8', 'replace')[:maxim]
	try:
		if not os.path.isdir(os.path.dirname(cale) or '.') or os.path.islink(cale):
			return False
		if os.path.isfile(cale) and os.path.getsize(cale) + len(date) > maxim:
			os.replace(cale, cale + '.1')
		fd = os.open(cale, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0) |
			getattr(os, 'O_BINARY', 0), 0o600)
		try:
			os.write(fd, date)
			if sincron:
				os.fsync(fd)
		finally:
			os.close(fd)
		return True
	except (IOError, OSError):
		return False


# ---------------------------------------------------------------- fisiere .ipk de pe stick, disc sau retea

def fisier_ipk_permis(cale, radacina='/'):
	"""calea reala a unui .ipk care se poate instala (existent, in RADACINI_FISIERE), altfel None"""
	if not isinstance(cale, str) or not cale.startswith('/') or not cale.lower().endswith('.ipk'):
		return None
	if any(ord(c) < 32 or c == '\x7f' for c in cale) or not e_utf8(cale):
		return None
	reala = os.path.realpath(_cale(radacina, cale))
	baza = os.path.realpath(radacina) if radacina and radacina != '/' else ''
	if baza:
		if not reala.startswith(baza + os.sep):
			return None
		interior = '/' + os.path.relpath(reala, baza).replace(os.sep, '/')
	else:
		interior = reala
	if not interior.lower().endswith('.ipk') or not os.path.isfile(reala):
		return None
	if not any(interior == r or interior.startswith(r + '/') for r in RADACINI_FISIERE):
		return None
	return interior


def locuri_retea():
	"""locurile de retea (cai fara '/' la sfarsit): LOCURI_RETEA si fiecare montare de retea din /proc/mounts
	(HDS_PROBA_MOUNTS la probe, prin Components/HdsNavigator.py readMountTable). Doar citeste tabelul, nu atinge
	montarile. Radacina sistemului nu e niciodata printre ele."""
	locuri = list(LOCURI_RETEA)
	for punct, (sursa, tip) in sorted(readMountTable().items()):
		if punct != '/' and punct.startswith('/') and (tip in TIPURI_RETEA or sursa.startswith('//')) and punct not in locuri:
			locuri.append(punct)
	return locuri


def _sub(cale, locuri):
	return any(cale == l or cale.startswith(l + '/') for l in locuri)


def _numele_exista(radacina, cale):
	"""cale exista, aflat din lista dosarului parinte (fara stat pe ea: poate fi o montare de retea care nu raspunde)"""
	parinte, nume = cale.rsplit('/', 1)
	try:
		return nume in os.listdir(_cale(radacina, parinte or '/'))
	except OSError:
		return False


def _tinta_radacinii(radacina, cale, sare):
	"""unde duce radacina `cale` cand e o legatura (in imaginea HDSatelit /hdd -> media/hdd si /mnt -> media), aflat
	textual cu os.readlink; cale cand nu e legatura. Pe o tinta care e loc de retea nu se mai face lstat."""
	for _k in range(8):
		if _sub(cale, sare):
			break
		try:
			if not os.path.islink(_cale(radacina, cale)):
				break
			t = os.readlink(_cale(radacina, cale)).replace(os.sep, '/')
		except OSError:
			break
		# o tinta absoluta e in imagine (radacina), una relativa fata de dosarul legaturii
		cale = posixpath.normpath(t if t.startswith('/') else posixpath.join(posixpath.dirname(cale), t))
	return cale


def cauta_fisiere_ipk(radacina='/', radacini=RADACINI_FISIERE, adancime=4, maxim=300, maxim_dosare=4000, info=None,
		maxim_nume=3000, retea=None):
	"""[(cale, marime, data)] ale fisierelor .ipk din radacini, cele mai noi primele. Nu urmeaza legaturile, sare
	peste dosarele ascunse si peste cele care nu se pot citi; se opreste la `maxim_nume` nume gasite sau `maxim_dosare`
	dosare si intoarce cele mai noi `maxim` (asa un dosar cu mii de .ipk vechi nu ascunde pachetul abia copiat).
	Locurile de retea (locuri_retea) nu se deschid: un dosar de retea care nu raspunde tinea cautarea zeci de secunde,
	iar o intrare in dosarul automontarii porneste montarea; nici stat nu se face pe ele (verificarea e pe nume,
	inainte de is_dir). O radacina care e legatura se verifica dupa tinta ei (/mnt -> media ar fi parcurs /media/net
	sub numele /mnt/net). Cele intalnite ajung in info['retea']. Cu `retea` (lista locurilor de retea deschise de
	utilizator, de obicei info['retea'] al cautarii de mai inainte) se cauta numai in ele, in afara locurilor de unde
	nu se poate instala (RADACINI_FISIERE).
	`info` (dict), daca e dat, primeste 'taiat': True cand s-au gasit mai multe decat se intorc, si 'retea'."""
	gasite = {}
	dosare = 0
	taiat = False
	intalnite = []
	if retea is None:
		sare = locuri_retea()
	else:
		sare = []
		permise = [r for r in retea if _sub(r, radacini)]
		# un loc cuprins in altul (/media/net si /media/net/nas) se parcurge o singura data
		radacini = [r for r in permise if not any(a != r and _sub(r, [a]) for a in permise)]
	toate = [x.rstrip('/') or '/' for x in radacini]
	for r in toate:
		sare_aici, tinta = sare, r
		if sare:
			tinta = _tinta_radacinii(radacina, r, sare)
			if _sub(tinta, sare):
				# un loc de retea sau o legatura spre unul (/hdd cand /media/hdd e o montare nfs); numele se cauta in
				# dosarul parinte doar cand nici acela nu e in retea
				if tinta not in intalnite and not _sub(posixpath.dirname(tinta), sare) and _numele_exista(radacina, tinta):
					intalnite.append(tinta)
				continue
			if tinta != r:
				if tinta in toate:
					continue          # /mnt -> media: /media se parcurge oricum, a doua trecere ar fi doar drum dublu
				# locurile de retea de sub tinta se sar si sub numele legaturii (/hdd/nas cand /media/hdd/nas e nfs)
				pre = tinta.rstrip('/')
				sare_aici = sare + [r + l[len(pre):] for l in sare if l.startswith(pre + '/')]
		start = _cale(radacina, r)
		if not os.path.isdir(start):
			continue
		coada = [(start, r, 0)]
		while coada and dosare < maxim_dosare and len(gasite) < maxim_nume:
			dosar, interior, nivel = coada.pop(0)
			dosare += 1
			try:
				intrari = list(os.scandir(dosar))
			except OSError:
				continue
			for e in intrari:
				try:
					if e.name.startswith('.'):
						continue
					cale = interior.rstrip('/') + '/' + e.name
					if sare_aici and _sub(cale, sare_aici):
						loc = tinta.rstrip('/') + cale[len(r):] if tinta != r else cale      # numele fara legatura
						if loc not in intalnite:
							intalnite.append(loc)
						continue
					if e.is_dir(follow_symlinks=False):
						if nivel + 1 <= adancime:
							coada.append((e.path, cale, nivel + 1))
					elif e.name.lower().endswith('.ipk') and e.is_file(follow_symlinks=False):
						reala = os.path.realpath(e.path)
						if reala in gasite:
							continue
						st = e.stat(follow_symlinks=False)
						gasite[reala] = (cale, st.st_size, int(st.st_mtime))
						if len(gasite) >= maxim_nume:
							taiat = True
							break
				except OSError:
					continue
		if coada and dosare >= maxim_dosare:
			taiat = True
	rez = list(gasite.values())
	rez.sort(key=lambda x: (-x[2], x[0]))
	if len(rez) > maxim:
		taiat = True
		rez = rez[:maxim]
	if info is not None:
		info['taiat'] = taiat
		info['retea'] = sorted(l for l in intalnite if _sub(l, RADACINI_FISIERE))
	return rez


class CautareIpk(object):
	"""O cautare de fisiere .ipk intr-un fir separat. Parcurgerea dosarelor si citirea lui control din fiecare fisier
	tineau pe loc firul interfetei (secunde pe un stick lent, zeci de secunde pe o retea care nu raspunde). Firul nu
	atinge nimic din interfata: la sfarsit completeaza campurile si pune `gata`, ultimul; ecranul (Screens/HdsExtensii.py)
	le citeste din firul principal, cu un eTimer. Firul porneste cu _thread.start_new_thread, ca in
	Hds/DabT2/fundal.py: nu se asteapta pornirea lui, iar un fir agatat pe o retea nu tine
	iesirea din enigma2."""

	def __init__(self, retea=None, radacina='/'):
		self.retea = retea            # None: stick, disc, memorie; altfel locurile de retea deschise de utilizator
		self.radacina = radacina
		self.pornit = _ceas()
		self.gata = False
		self.fisiere = []             # [FisierIpk], cele care se pot citi primele, apoi cele mai noi
		self.taiat = False
		self.locuri_retea = []        # locurile de retea intalnite si sarite (numai la cautarea fara retea)
		self.eroare = None
		self.durata = 0.0

	def porneste(self):
		_fire.start_new_thread(self._lucreaza, ())
		return self

	def _lucreaza(self):
		try:
			info = {}
			fisiere = [FisierIpk(c, m, d, retea=self.retea is not None, radacina=self.radacina)
				for c, m, d in cauta_fisiere_ipk(self.radacina, info=info, retea=self.retea)]
			fisiere.sort(key=lambda f: (not f.citit, -f.data, f.cale))
			# pachetele numai pentru Python 2 (0.6.8), tot pe fir: cele mai noi intai, cel mult TIMP_PYTHON2 secunde in
			# total; cele ramase se verifica la confirmarea instalarii (planFisier)
			for f in fisiere:
				ramas = TIMP_PYTHON2 - (_ceas() - self.pornit)
				if ramas <= 0.5:
					break
				if f.citit:
					f.verificaPython2(min(H.TIMP_MAXIM, ramas))
			self.fisiere, self.taiat, self.locuri_retea = fisiere, bool(info.get('taiat')), info.get('retea') or []
		except Exception as e:
			self.eroare = '%s: %s' % (e.__class__.__name__, e)
		self.durata = _ceas() - self.pornit
		self.gata = True


# cat timp (secunde, de la pornirea cautarii) se verifica pe fir fisierele gasite pentru Python 2
TIMP_PYTHON2 = 10.0

# cautarile in curs, cel mult una de fiecare fel (fara retea, in retea): un ecran redeschis se leaga de cea care ruleaza.
# Un fir agatat pe o retea care nu raspunde nu se poate opri; asa nu se mai porneste inca unul langa el.
_cautari = {}


def cautare_ipk(retea=None, radacina='/'):
	"""cautarea care ruleaza de felul cerut, altfel una noua, pornita acum"""
	fel = 'local' if retea is None else 'retea'
	c = _cautari.get(fel)
	if c is None or c.gata:
		c = _cautari[fel] = CautareIpk(retea, radacina).porneste()
	return c


def cautare_in_curs(retea=False):
	c = _cautari.get('retea' if retea else 'local')
	return c is not None and not c.gata


def ultima_cautare(retea=False):
	"""cautarea de felul cerut, in curs sau ultima terminata (pornita de ecran sau de pagina web), sau None"""
	return _cautari.get('retea' if retea else 'local')


_CONTROL_MAXIM = 1024 * 1024
# cat se dezarhiveaza cel mult dintr-un tar ca sa se ajunga la control: fara limita, un control.tar.gz de 1 MB plin
# cu acelasi octet (sau un .ipk vechi, tar.gz, cu date mari inaintea lui control) tinea interfata pe loc zeci de
# secunde, pentru fiecare fisier din fila Din fisier (getmembers() dezarhiva tot)
_TAR_MAXIM = 16 * 1024 * 1024
_ERORI_ARHIVA = (tarfile.TarError, OSError, EOFError, ValueError, zlib.error)
try:
	import lzma
	_ERORI_ARHIVA += (lzma.LZMAError,)
except ImportError:
	pass


def _membri(t):
	"""membrii unui tar, pe rand, pana la _TAR_MAXIM octeti dezarhivati"""
	for m in t:
		yield m
		if m.offset_data + max(0, m.size) > _TAR_MAXIM:
			return


def _control_din_tar(date):
	try:
		with tarfile.open(fileobj=io.BytesIO(date), mode='r:*') as t:
			for m in _membri(t):
				if m.isfile() and m.name.lstrip('./') == 'control' and m.size <= 65536:
					fh = t.extractfile(m)
					if fh is not None:
						text = fh.read().decode('utf-8', 'replace')
						strofe = strofe_din_text(text)
						return strofe[0] if strofe else {}
	except _ERORI_ARHIVA:
		pass
	return {}


def citeste_control_ipk(cale):
	"""campurile din control ale unui .ipk (ar ca la Debian sau tar.gz ca la opkg-build vechi), cheile cu litere
	mici; {} daca fisierul nu se poate citi. Nu se despacheteaza nimic pe disc si nu se ruleaza nimic din pachet."""
	try:
		with open(cale, 'rb') as fh:
			cap = fh.read(8)
			if cap == b'!<arch>\n':
				for _k in range(16):         # un .ipk are 3 membri; mii de antete intr-un fisier nu tin interfata pe loc
					antet = fh.read(60)
					if len(antet) < 60:
						break
					nume = antet[:16].strip().rstrip(b'/').decode('ascii', 'replace')
					try:
						marime = int(antet[48:58].strip() or b'0')
					except ValueError:
						break
					if nume.startswith('control.tar') and 0 < marime <= _CONTROL_MAXIM:
						return _control_din_tar(fh.read(marime))
					fh.seek(marime + (marime % 2), 1)
				return {}
			fh.seek(0)
			with tarfile.open(fileobj=fh, mode='r:*') as t:
				for m in _membri(t):
					if m.isfile() and m.name.lstrip('./').startswith('control.tar') and 0 < m.size <= _CONTROL_MAXIM:
						date = t.extractfile(m)
						if date is not None:
							return _control_din_tar(date.read())
	except _ERORI_ARHIVA:
		pass
	return {}


class FisierIpk(object):
	"""un pachet dintr-un fisier: calea, marimea si ce spune fisierul control (doar pentru afisare)"""

	def __init__(self, cale, marime=0, data=0, retea=False, radacina='/'):
		self.cale = cale                # calea adevarata (poate avea surogate, vezi utf8), pentru opkg
		self.marime = marime
		self.data = data
		self.retea = retea              # gasit intr-un loc de retea (cautarea ceruta de utilizator)
		# numele si calea pentru ecran; un nume care nu e UTF-8 nu se poate da nici interfetei, nici lui opkg
		self.utf8 = e_utf8(cale)
		self.nume_fisier = _curat(os.path.basename(cale), 255)
		self.cale_text = _curat(cale, 400)
		control = citeste_control_ipk(_cale(radacina, cale))
		nume = control.get('package', '')
		self.nume = nume if nume_valid(nume) else ''
		self.versiune = _curat(control.get('version', ''), 40)
		self.arhitectura = _curat(control.get('architecture', ''), 40)
		rezumat, extins = _text_descriere(control) if control else ('', '')
		self.rezumat = _curat(rezumat, 120)
		self.descriere = _curat(extins, 600)
		self.depinde = _dependente(control.get('depends', ''))
		self.citit = bool(self.nume)
		# pachet numai pentru Python 2 (0.6.8): Components/HdsPython2.Verdict, aflat pe firul cautarii (verificaPython2)
		# sau, daca n-a apucat, la confirmarea instalarii; None = neverificat inca
		self._citire = _cale(radacina, cale)
		self.verdict = None
		if control:
			v = H.din_control(control)
			if v.python2:
				self.verdict = v

	def verificaPython2(self, timp_maxim=H.TIMP_MAXIM, refa=False):
		"""verdictul dupa control si continut (o singura data; `refa`: inca o data cand prima citire s-a oprit la o
		limita fara un raspuns); numai citit, nimic rulat"""
		v = self.verdict
		if v is None or (refa and v.taiat and v.python2 is None):
			self.verdict = H.din_ipk(self._citire, timp_maxim=timp_maxim)
		return self.verdict

	@property
	def python2(self):
		"""(cod, detaliu) al motivului cand fisierul e numai pentru Python 2, altfel None (si cand nu s-a verificat)"""
		v = self.verdict
		return v.motiv if v is not None and v.python2 else None

	@property
	def titlu(self):
		if self.rezumat and len(self.rezumat) <= 40:
			return self.rezumat
		if self.nume:
			scurt = nume_scurt(self.nume).replace('-', ' ')
			return scurt[:1].upper() + scurt[1:]
		return self.nume_fisier

	@property
	def categorie(self):
		return categorie_din_nume(self.nume) if self.nume else 'altele'


# ---------------------------------------------------------------- iesirea opkg, pe romaneste

_RE_DESCARC = re.compile(r'^Downloading (\S+?)\.?$')
_RE_INSTALEZ = re.compile(r'^Installing (\S+) \(([^)]*)\)')
_RE_ACTUALIZEZ = re.compile(r'^Upgrading (\S+) (?:on \S+ )?from (\S+) to (\S+?)\.{0,3}$')
_RE_STERG = re.compile(r'^Removing (?:package )?(\S+)')
_RE_CONFIGUREZ = re.compile(r'^Configuring (\S+?)\.?$')
_RE_LA_ZI = re.compile(r'^Package (\S+) \(([^)]*)\) installed in \S+ is up to date')
_RE_DEPENDENT = re.compile(r'^\*\s*print_dependents_warning:\s+(\S+)$')
_RE_LISTA = re.compile(r'^(?:Updated source |Updated list of available packages in \S+/)\'?([A-Za-z0-9_.\-]+?)\'?\.?$')


def _baza_adresei(adresa):
	a = adresa.rstrip('/')
	return a.rsplit('/', 1)[-1] or a


def linie_jurnal(linie, titluri=None):
	"""(fel, text) pentru jurnalul scurt al progresului: fel 'pas', 'eroare' sau '' (rand fara rost aici).
	Textul din iesirea opkg e doar afisat (curatat de caractere de control). `titluri`: nume pachet -> titlul aratat
	in lista, ca jurnalul sa vorbeasca despre „DAB+ din satelit”, nu despre enigma2-plugin-extensions-hdsdab."""
	titluri = titluri or {}

	def t(nume):
		return titluri.get(nume) or nume_scurt(nume)
	l = _curat(linie, 200)
	if not l or l == 'Collected errors:':
		return '', ''
	# la o actualizare opkg scoate fisierele vechi pe care pachetul nou nu le mai are ("Removing obsolete file X."):
	# nu e stergerea unui pachet (randul ar fi fost "Se șterge obsolete")
	if l.startswith('Removing obsolete file'):
		return '', ''
	m = _RE_DESCARC.match(l)
	if m:
		fisier = _baza_adresei(m.group(1))
		nume = fisier.split('_', 1)[0]
		if fisier.endswith('.ipk') and nume in titluri:
			return 'pas', _t('Se descarcă %s') % titluri[nume]
		if fisier.startswith('Packages'):
			return 'pas', _t('Se descarcă lista de la %s') % (gazda(m.group(1)) or fisier)
		return 'pas', _t('Se descarcă %s') % fisier
	m = _RE_ACTUALIZEZ.match(l)
	if m:
		return 'pas', _t('Se actualizează %s de la %s la %s') % (t(m.group(1)), m.group(2), m.group(3))
	m = _RE_INSTALEZ.match(l)
	if m:
		return 'pas', _t('Se instalează %s %s') % (t(m.group(1)), m.group(2))
	m = _RE_STERG.match(l)
	if m:
		return 'pas', _t('Se șterge %s') % t(m.group(1).rstrip('.'))
	m = _RE_CONFIGUREZ.match(l)
	if m:
		return 'pas', _t('Se configurează %s') % t(m.group(1))
	m = _RE_LA_ZI.match(l)
	if m:
		return 'pas', _t('%s %s este deja la zi') % (t(m.group(1)), m.group(2))
	m = _RE_LISTA.match(l)
	if m:
		return 'pas', _t('Lista sursei %s este la zi') % m.group(1)
	if l.startswith('Signature check'):
		return 'pas', _t('Semnătura listei a fost verificată')
	# randurile care doar repeta eroarea spusa deja (motivul e pe randul de dinainte); textele lui opkg, in engleza
	# oricare ar fi limba meniurilor: se compara, nu se traduc (fara _t)
	for zgomot in ('Cannot install package', 'Failed to unpack data', 'These might cease to work', 'Force removal of',
			'force-removal-of-dependent', 'with --force', "Couldn't retrieve", 'No packages removed', 'Collected errors'):
		if zgomot in l:
			return '', ''
	m = _RE_DEPENDENT.match(l)
	if m:
		return 'eroare', _t('Are nevoie de el: %s') % t(m.group(1))
	motiv = motiv_eroare([l], implicit='', ceas=False)
	if motiv or l.startswith('*') or 'error' in l.lower() or 'fail' in l.lower():
		return 'eroare', motiv or l.lstrip('* ')
	return '', ''


def _ceas_scurt(linii):
	"""„Ceasul e în urmă” intr-un rand (Components/HdsCeasHttps.py) cand opkg nu a putut verifica certificatul sursei din
	cauza ceasului receptorului (opkg cu wget -q spune numai „wget returned 5”); altfel None."""
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.scurt(list(linii))
	except Exception:
		return None


def motiv_eroare(linii, implicit=N_('Operațiunea nu a reușit.'), ceas=True):
	"""cel mai probabil motiv al unei erori opkg, spus simplu. ceas: si „ceasul e în urmă” (randul de stare al
	ecranului); randurile jurnalului (linie_jurnal) nu il cer."""
	t = '\n'.join(linii).lower()
	if 'no space left' in t or 'only have' in t and 'available' in t:
		return _t('Nu mai este loc în memoria receptorului.')
	if 'could not obtain administrative lock' in t or 'could not lock' in t:
		return _t('Altă instalare rulează acum. Încearcă din nou peste un minut.')
	if ceas:
		m = _ceas_scurt(linii)
		if m:
			return m
	if 'is depended upon by' in t or 'dependent' in t and 'remove' in t:
		return _t('Alte extensii au nevoie de acest pachet. Șterge-le întâi pe ele.')
	if 'unknown package' in t or 'cannot find package' in t or 'no candidates to install' in t:
		return _t('Pachetul nu se mai află în sursă. Descarcă din nou lista (tasta albastră).')
	if 'incompatible with the architectures' in t or 'not compatible with' in t:
		return _t('Pachetul nu este făcut pentru acest receptor.')
	if 'signature' in t and ('fail' in t or 'invalid' in t or 'bad' in t):
		return _t('Semnătura sursei nu se potrivește. Pachetul nu a fost instalat.')
	if 'mismatch' in t:
		return _t('Fișierul descărcat este deteriorat. Încearcă din nou.')
	if 'failed to download' in t or 'wget' in t or 'curl' in t or 'download failed' in t or 'network is unreachable' in t \
			or 'bad address' in t or 'could not resolve' in t or 'timed out' in t or 'connection refused' in t:
		return _t('Nu s-a putut descărca. Verifică legătura la internet.')
	if 'clash' in t or 'file conflicts' in t:
		return _t('Pachetul ar scrie peste fișierele altui pachet. Nu a fost instalat.')
	if 'malformed' in t or 'error unpacking' in t or 'not a valid' in t or 'failed to extract' in t:
		return _t('Fișierul pachetului nu se poate citi.')
	if 'not installed' in t and 'remove' in t:
		return _t('Pachetul nu este instalat.')
	return _t(implicit)
