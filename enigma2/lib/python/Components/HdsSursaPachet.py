# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Descarcarea sursei deschise a unui plugin din Extensii (0.6.6). Doar in imaginea
HDSatelit; folosit de ecranul de pe televizor (Screens/HdsExtensii.py, tasta albastra "Descarcă sursa") si de pagina web
/extensii (Plugins/Extensions/HdsWebControl/extensii_web.py, acelasi buton).

- Butonul apare NUMAI la un pachet care are in descriere randul "Source archive: <fisier>" (HdsPachete.arhiva_sursa) si
  vine dintr-o sursa cu adresa cunoscuta: arhiva sta langa pachet in feed, deci adresa ei e adresa sursei, plus dosarul
  din Filename (cand are), plus numele arhivei. Asa sunt pachetele feedului pluginurilor externe (moneasoftware.com);
  sursa nu se vede pe site, numai pe receptor.
- Intai marimea (cererea HEAD, Content-Length) si locul: STICK-ul USB are intaietate (daca are loc destul), discul numai
  fara stick sau cand stick-ul n-are loc; memoria interna a receptorului niciodata. Intrebarea arata marimea si locul.
- Apoi descarcarea (GET) in <loc>/surse/<fisier>.partial, cu progres, mutata in <fisier> numai intreaga (cat a spus
  serverul); la orice greseala (retea, loc, oprire) fisierul partial se sterge.
- Cand arhiva nu raspunde pe server (404, 403, fara retea, alt raspuns): un mesaj pe intelesul omului, fara cadere.
Toata reteaua si scrierea merg pe un fir separat; ecranul si pagina citesc starea (o singura descarcare odata in tot
procesul: ce porneste pagina vede si televizorul). Textele nu numesc pluginul altfel decat titlul lui din lista.
Modulul nu depinde de enigma, ca sa poata fi incercat si pe PC (radacina, mount-uri false, deschide)."""
import os
import re
import socket
import time
try:
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError, URLError
except ImportError:  # Python 2 (doar pentru teste vechi)
	from urllib2 import Request, urlopen, HTTPError, URLError
try:
	import _thread as _fire
except ImportError:  # Python 2 (doar pentru teste vechi)
	import thread as _fire

try:
	from Components import HdsPachete as P
except ImportError:  # probe pe PC: modulul incarcat singur, din dosarul Components
	import HdsPachete as P
try:
	from Components import HdsNavigator as N
except ImportError:
	import HdsNavigator as N

UA = 'hdsatelit-receptor/1'
DOSAR = 'surse'                    # <stick sau disc>/surse/<arhiva>
REZERVA = 4 * 1024 * 1024          # loc lasat liber pe stick sau disc peste marimea arhivei
REZERVA_FARA_MARIME = 256 * 1024 * 1024   # cand serverul nu spune marimea
TIMP_HEAD = 20
TIMP_CITIRE = 30
BUCATA = 64 * 1024
# locurile de stocare: montarile de sub /media si /run/media (stick, disc; imaginea monteaza stick-ul in
# /run/media/<eticheta>-sda1 si pune /media/hdd ca legatura spre el, Components/Harddisk.py); fara retea, fara memorie
# (tmpfs) si fara automontari. Numai puncte din /proc/mounts: un dosar /run/media ramas fara stick e pe memoria interna.
RADACINI_MONTARI = ('/media/', '/run/media/')
RADACINA_LEGATURI = '/media'
TIPURI_FARA = ('tmpfs', 'ramfs', 'devtmpfs', 'proc', 'sysfs', 'autofs', 'squashfs', 'overlay', 'iso9660', 'udf')

_DOSAR_FISIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+~\-]{0,120}(?:/[A-Za-z0-9][A-Za-z0-9._+~\-]{0,120}){0,4}\Z')


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print('[HdsSursaPachet] %s' % text)


TEXT_NEGASIT = N_('Sursa deschisă (open source) nu a fost găsită în acest feed pentru acest plugin.')


# ---------------------------------------------------------------- adresa arhivei

def adresa_arhivei(catalog, p):
	"""(adresa, fisier) ale arhivei sursei unui pachet, sau None (fara randul "Source archive:" sau fara sursa cu
	adresa http/https); butonul se arata numai cand nu e None"""
	if p is None or not getattr(p, 'arhiva', '') or not getattr(p, 'sursa', ''):
		return None
	baza = (catalog.configurare.adresa(p.sursa) or '').rstrip('/')
	if not baza.startswith(('https://', 'http://')) or '?' in baza or '#' in baza:
		return None
	f = getattr(p, 'fisier', '') or ''
	if '/' in f:
		dosar = f.rsplit('/', 1)[0]
		while dosar.startswith('./'):
			dosar = dosar[2:]
		if dosar:
			if not _DOSAR_FISIER.match(dosar) or '..' in dosar.split('/'):
				return None
			baza = baza + '/' + dosar
	return baza + '/' + p.arhiva, p.arhiva


# ---------------------------------------------------------------- locul

def _liber(cale):
	try:
		st = os.statvfs(cale)
		return st.f_bavail * st.f_frsize
	except (OSError, AttributeError):
		return None


def _legatura(punct, radacina=RADACINA_LEGATURI):
	"""numele de sub /media care duce la punct (/media/hdd -> /run/media/HD SATELIT-sda1), ca sa se arate omului; punct
	cand nu e niciunul"""
	try:
		real = os.path.realpath(punct)
		for n in sorted(os.listdir(radacina)):
			p = os.path.join(radacina, n)
			if os.path.islink(p) and os.path.realpath(p) == real:
				return p
	except OSError:
		pass
	return punct


def locuri(montari=None, liber=None, amovibil=None, legatura=None):
	"""[(punct, fel, liber_octeti)] ale stick-urilor si discurilor montate sub /media sau /run/media, stick-urile
	primele: fel 'stick' (/sys/block/<disc>/removable = 1) sau 'disc'; punct e numele de sub /media cand imaginea a pus o
	legatura spre montare. Fara montari de retea, de memorie sau numai de citire."""
	montari = N.readMountTable() if montari is None else montari
	liber = liber or _liber
	amovibil = amovibil or N.removableDisk
	legatura = legatura or _legatura
	rez = []
	for punct, (sursa, tip) in sorted(montari.items()):
		if not punct.startswith(RADACINI_MONTARI) or tip in TIPURI_FARA or tip in N.NETWORK_FS:
			continue
		if N.isNetworkSource(sursa, tip) or not sursa.startswith('/dev/'):
			continue
		if punct.startswith(('/media/net', '/media/autofs')):
			continue
		dispozitiv = sursa[5:]
		e_stick = amovibil(dispozitiv)
		fel = 'stick' if e_stick or (e_stick is None and N._usbDisk(dispozitiv) and punct.startswith('/media/usb')) else 'disc'
		rez.append((legatura(punct), fel, liber(punct)))
	rez.sort(key=lambda x: (x[1] != 'stick', x[0]))
	return rez


def alege_loc(marime, montari=None, liber=None, amovibil=None, scriere=None, legatura=None):
	"""(punct, fel) unde se salveaza arhiva de `marime` octeti (None = necunoscuta): primul stick cu loc destul, altfel
	primul disc cu loc destul; (None, None) cand niciunul (memoria interna nu se foloseste niciodata)"""
	nevoie = (marime + REZERVA) if marime else REZERVA_FARA_MARIME
	scriere = scriere or (lambda cale: os.access(cale, os.W_OK))
	for punct, fel, l in locuri(montari, liber, amovibil, legatura):
		if l is not None and l >= nevoie and scriere(punct):
			return punct, fel
	return None, None


# avertismentul marimii in intrebare: de la 100 MB "mare", de la 1 GB "foarte mare" (sub 100 MB niciunul)
MARE = 100 * 1024 * 1024
FOARTE_MARE = 1024 * 1024 * 1024
_SUFIX_DISPOZITIV = re.compile(r'-(?:sd[a-z]+[0-9]*|mmcblk[0-9]+p[0-9]+|nvme[0-9]+n[0-9]+p[0-9]+)\Z')


def eticheta_loc(punct):
	"""eticheta stick-ului sau a discului ("HD SATELIT"), din numele montarii /run/media/<eticheta>-sda1 (Harddisk.py);
	'' cand nu are"""
	try:
		nume = os.path.basename(os.path.realpath(punct or '').rstrip('/'))
	except (OSError, ValueError):
		return ''
	if not os.path.realpath(punct or '').startswith('/run/media/'):
		return ''
	eticheta = _SUFIX_DISPOZITIV.sub('', nume).strip()
	return '' if not eticheta or eticheta == nume and nume.startswith(('sd', 'mmcblk')) else eticheta


def text_loc(fel, eticheta=''):
	"""stick-ul HD SATELIT, discul X; fara eticheta: stick-ul USB, discul"""
	if eticheta:
		return (_t(N_('stick-ul %s')) if fel == 'stick' else _t(N_('discul %s'))) % eticheta
	return _t(N_('stick-ul USB')) if fel == 'stick' else _t(N_('disc'))


# ---------------------------------------------------------------- descarcarea

class Descarcare(object):
	"""O descarcare a sursei unui pachet, de la cererea marimii pana la fisierul de pe stick. Fazele:
	'marime' (HEAD pe fir) -> 'intrebare' (marimea si locul stiute) | 'negasit' (arhiva nu raspunde) | 'fara-loc';
	'intrebare' -> porneste() -> 'lucru' -> 'gata' | 'eroare' | 'oprit'. Campurile le scrie firul; `faza` ultima."""

	def __init__(self, adresa, fisier, titlu, feed, deschide=None, montari=None, liber=None, amovibil=None,
			scriere=None):
		self.adresa = adresa
		self.fisier = fisier
		self.titlu = titlu              # titlul pluginului, din lista
		self.feed = feed                # numele feedului, ca in Extensii
		self.deschide = deschide or urlopen
		self._loc = (montari, liber, amovibil, scriere)
		self.faza = 'marime'
		self.marime = None
		self.citit = 0
		self.punct = None
		self.fel = None
		self.cale = ''
		self.motiv = ''
		self.cod = None                 # raspunsul serverului la HEAD (pentru jurnal)
		self.eticheta = ''              # eticheta stick-ului sau a discului ("HD SATELIT"), cand are
		self.pornit = time.time()
		self._opreste = False

	# -- 1. marimea si locul

	def afla(self, pe_fir=True):
		if pe_fir:
			_fire.start_new_thread(self._afla, ())
		else:
			self._afla()
		return self

	def _afla(self):
		try:
			r = self.deschide(Request(self.adresa, headers={'User-Agent': UA, 'Cache-Control': 'no-cache'},
				method='HEAD'), timeout=TIMP_HEAD)
			try:
				self.cod = getattr(r, 'status', None) or r.getcode()
				lungime = r.headers.get('Content-Length')
			finally:
				try:
					r.close()
				except Exception:
					pass
			if self.cod != 200:
				raise ValueError('HTTP %s' % self.cod)
			try:
				self.marime = int(lungime) if lungime is not None else None
			except ValueError:
				self.marime = None
			if self.marime is not None and self.marime <= 0:
				raise ValueError('marime %s' % self.marime)
		except HTTPError as e:
			self.cod = e.code
			self._negasit('HTTP %s' % e.code)
			return
		except (URLError, socket.timeout, socket.error, OSError, ValueError) as e:
			self._negasit(str(getattr(e, 'reason', e)))
			return
		except Exception as e:
			self._negasit('%s: %s' % (e.__class__.__name__, e))
			return
		montari, liber, amovibil, scriere = self._loc
		self.punct, self.fel = alege_loc(self.marime, montari, liber, amovibil, scriere)
		self.eticheta = eticheta_loc(self.punct) if self.punct else ''
		if self.punct is None:
			self.faza = 'fara-loc'
			return
		self.cale = '%s/%s/%s' % (self.punct.rstrip('/'), DOSAR, self.fisier)
		self.faza = 'intrebare'

	def _negasit(self, detaliu):
		_jurnal('sursa negasita: %s (%s)' % (self.adresa, detaliu))
		self.motiv = detaliu
		self.faza = 'negasit'

	# -- 2. descarcarea

	def porneste(self, pe_fir=True):
		if self.faza != 'intrebare':
			return False
		self.faza = 'lucru'
		self.citit = 0
		self.pornit = time.time()
		if pe_fir:
			_fire.start_new_thread(self._descarca, ())
		else:
			self._descarca()
		return True

	def opreste(self):
		"""cerere de oprire: firul se opreste la bucata urmatoare si sterge fisierul partial"""
		if self.faza == 'lucru':
			self._opreste = True
			return True
		return False

	def _descarca(self):
		partial = self.cale + '.partial'
		try:
			os.makedirs(os.path.dirname(self.cale), exist_ok=True)
		except OSError as e:
			return self._eroare(e, partial)
		try:
			r = self.deschide(Request(self.adresa, headers={'User-Agent': UA, 'Cache-Control': 'no-cache'}),
				timeout=TIMP_CITIRE)
			try:
				cod = getattr(r, 'status', None) or r.getcode()
				if cod != 200:
					raise HTTPError(self.adresa, cod, 'HTTP %s' % cod, None, None)
				with open(partial, 'wb') as f:
					while True:
						if self._opreste:
							break
						bucata = r.read(BUCATA)
						if not bucata:
							break
						f.write(bucata)
						self.citit += len(bucata)
						if self.marime is not None and self.citit > self.marime:
							raise ValueError('mai mult decat a spus serverul')
					f.flush()
					os.fsync(f.fileno())
			finally:
				try:
					r.close()
				except Exception:
					pass
			if self._opreste:
				self._sterge(partial)
				self.faza = 'oprit'
				return
			if self.marime is not None and self.citit != self.marime:
				raise ValueError('descarcat %d din %d' % (self.citit, self.marime))
			os.replace(partial, self.cale)
		except HTTPError as e:
			return self._eroare('HTTP %s' % e.code, partial, negasit=True)
		except Exception as e:
			return self._eroare(e, partial)
		self.faza = 'gata'
		_jurnal('sursa descarcata: %s (%d octeti)' % (self.cale, self.citit))

	@staticmethod
	def _sterge(cale):
		try:
			os.remove(cale)
		except OSError:
			pass

	def _eroare(self, e, partial, negasit=False):
		self._sterge(partial)
		self.motiv = str(getattr(e, 'strerror', None) or getattr(e, 'reason', None) or e)
		_jurnal('descarcarea sursei: %s (%s)' % (self.adresa, self.motiv))
		if negasit:
			self.faza = 'negasit'
			return
		self.loc_plin = getattr(e, 'errno', None) == 28
		self.faza = 'eroare'

	# -- textele, aceleasi pe televizor si in pagina

	def procent(self):
		if not self.marime:
			return 0
		return max(0, min(100, int(self.citit * 100 // self.marime)))

	def text_negasit(self):
		return '%s\n%s' % (_t(TEXT_NEGASIT), _t('Feedul: %s · Pluginul: %s') % (self.feed, self.titlu))

	def text_fara_loc(self):
		return _t('Nu am găsit un stick USB sau un disc cu loc liber destul pentru sursa pluginului %s (%s). Pune un '
			'stick USB și încearcă din nou. În memoria receptorului nu se descarcă.') % (self.titlu, self.text_marime())

	def text_marime(self):
		return P.marime_text(self.marime) if self.marime else _t('mărime necunoscută')

	def loc_text(self):
		return text_loc(self.fel, self.eticheta)

	def intrebare(self):
		"""Descarci sursa Alfa 2.26.09-11968 (1,2 MB) pe stick-ul HD SATELIT?"""
		if self.marime:
			return _t('Descarci sursa %s (%s) pe %s?') % (self.titlu, self.text_marime(), self.loc_text())
		return _t('Descarci sursa %s pe %s?') % (self.titlu, self.loc_text())

	def randuri(self):
		"""[(eticheta, valoare)] ale intrebarii: arhiva, marimea, locul (stick-ul sau discul si calea), feedul"""
		return [(_t('Arhiva'), self.fisier), (_t('Mărimea'), self.text_marime()),
			(_t('Locul'), '%s: %s' % (self.loc_text(), self.cale)), (_t('Feedul'), self.feed)]

	def avertisment(self):
		"""numai pentru fisierele mari: de la 100 MB "mare", de la 1 GB "foarte mare"; altfel ''"""
		if self.marime and self.marime >= FOARTE_MARE:
			return _t('E un fișier foarte mare (%s); descărcarea poate dura mult.') % self.text_marime()
		if self.marime and self.marime >= MARE:
			return _t('E un fișier mare (%s).') % self.text_marime()
		return ''

	def detalii(self):
		"""randurile intrebarii in pagina web: aceleasi ca pe televizor, apoi avertismentul (numai la un fisier mare)"""
		a = self.avertisment()
		return ['%s: %s' % r for r in self.randuri()] + ([a] if a else [])

	def text_progres(self):
		if self.marime:
			return _t('%s din %s') % (P.marime_text(self.citit) or '0 B', P.marime_text(self.marime))
		return P.marime_text(self.citit) or '0 B'

	def text_sfarsit(self):
		if self.faza == 'gata':
			return _t('Gata. Sursa pluginului %s este în %s') % (self.titlu, self.cale)
		if self.faza == 'oprit':
			return _t('Descărcarea a fost oprită. Nu a rămas niciun fișier pe jumătate.')
		if self.faza == 'negasit':
			return self.text_negasit()
		if getattr(self, 'loc_plin', False):
			return _t('Nu mai este loc pe %s. Nu a rămas niciun fișier pe jumătate.') % self.loc_text()
		return _t('Descărcarea sursei nu a reușit. Verifică legătura la internet și încearcă din nou. Nu a rămas niciun '
			'fișier pe jumătate.')

	def stare(self):
		"""starea pentru pagina web (JSON)"""
		return {'faza': self.faza, 'titlu': self.titlu, 'feed': self.feed, 'fisier': self.fisier,
			'marime': self.marime, 'citit': self.citit, 'procent': self.procent(), 'progres': self.text_progres(),
			'cale': self.cale if self.faza == 'gata' else '', 'mesaj': self.text_sfarsit() if self.faza in
			('gata', 'oprit', 'negasit', 'eroare') else (self.text_fara_loc() if self.faza == 'fara-loc' else '')}


# descarcarea curenta a procesului (televizor si pagina web): cel mult una care lucreaza
_CURENTA = {'d': None}


def curenta():
	return _CURENTA['d']


def in_lucru():
	d = _CURENTA['d']
	return d is not None and d.faza in ('marime', 'lucru')


def noua(catalog, p, titlu, feed, **kw):
	"""(Descarcare, None) pornita cu aflarea marimii, sau (None, motiv) cand alta lucreaza sau pachetul nu are sursa"""
	if in_lucru():
		return None, _t('Se descarcă deja o sursă. Așteaptă să se termine.')
	a = adresa_arhivei(catalog, p)
	if a is None:
		return None, '%s\n%s' % (_t(TEXT_NEGASIT), _t('Feedul: %s · Pluginul: %s') % (feed, titlu))
	pe_fir = kw.pop('pe_fir', True)
	d = Descarcare(a[0], a[1], titlu, feed, **kw)
	_CURENTA['d'] = d
	d.afla(pe_fir)
	return d, None


def uita(d):
	"""o descarcare inca nepornita (marimea sau intrebarea), la care s-a raspuns Renunta sau s-a inchis fereastra, nu
	mai e cea curenta (cardul din pagina web nu mai ramane pe ea); una pornita sau terminata ramane"""
	if d is not None and _CURENTA['d'] is d and d.faza in ('marime', 'intrebare'):
		_CURENTA['d'] = None


def fisier_descarcat():
	"""calea arhivei descarcate ultima (pentru pagina web: fisierul dat browserului), sau None"""
	d = _CURENTA['d']
	if d is None or d.faza != 'gata' or not d.cale or not os.path.isfile(d.cale):
		return None
	return d.cale
