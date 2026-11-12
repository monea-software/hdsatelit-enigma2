# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Temele (pachetele enigma2-plugin-skins-*) se instaleaza ca in imaginile OE-Alliance, cu --force-overwrite: unele aduc un
fisier pe care imaginea il are deja (de pilda Components/Converter/genre.py sau Components/Renderer/Pixmap.py), iar fara
optiune opkg refuza tema. Imaginea trebuie sa ramana intreaga dupa stergerea temei.

Ce face opkg (masurat pe receptorul de proba, opkg 0.10.0, 12.11.2026): cu --force-overwrite fisierul devine al temei
(randul lui dispare din <info>/enigma2-hdsatelit.list si apare in lista temei), iar la stergerea temei opkg il sterge.
De aceea, inainte de instalare, fisierele imaginii pe care le aduce tema se copiaza aici, impreuna cu randul lor din
lista pachetului imaginii; dupa orice lucrare opkg din Extensii si la fiecare pornire a interfetei (refa) se pun la loc
cele pe care nu le mai tine niciun pachet:
- tema le tine inca: raman ale ei;
- le tine iar pachetul imaginii (de pilda dupa o actualizare a imaginii): copia nu mai trebuie, se sterge;
- le tine alt pachet (alta tema instalata peste): copia trece la acel pachet, se pune la loc cand e sters si el;
- nu le tine nimeni (tema stearsa, din Extensii, din alt panou sau din linia de comanda): fisierul si randul din lista
  pachetului imaginii se pun la loc.
Fisierele temei care erau ale altei teme nu se copiaza (copia imaginii, daca e, sta la tema dinainte)."""

import json
import os
import shutil
import stat
import tarfile
import zlib

try:
	from Components import HdsPachete as P
except ImportError:          # probele de pe PC
	import HdsPachete as P

PREFIX = 'enigma2-plugin-skins-'
OPTIUNI_INSTALARE = ('--force-overwrite', '--force-reinstall')   # reinstall: resturile „half-installed” ale unei incercari vechi
OPTIUNI_ACTUALIZARE = ('--force-overwrite',)
DOSAR = '/var/lib/hds-teme-suprascrise'   # pe flash (/var/lib ramane la repornire; /var/volatile e in RAM)
NUME_LISTA = 'lista.json'
FISIERE_MAX = 20000          # membrii cititi dintr-un .ipk
MARIME_MAX = 64 * 1024 * 1024   # octetii dezarhivati cititi dintr-un .ipk (numai antetele; continutul se sare)

_ERORI = (tarfile.TarError, OSError, EOFError, ValueError, zlib.error)
try:
	import lzma
	_ERORI += (lzma.LZMAError,)
except ImportError:
	pass


def _jurnal(text):
	print('[HdsTemeSuprascrise] %s' % text)


def eTema(nume):
	"""numele unui pachet de tema (enigma2-plugin-skins-<nume>)"""
	return isinstance(nume, str) and nume.startswith(PREFIX) and len(nume) > len(PREFIX) and P.nume_valid(nume)


def _cale(radacina, p):
	return os.path.join(radacina, p.lstrip('/')) if radacina not in ('', '/') else p


def _dosarInfo(radacina):
	try:
		return _cale(radacina, P.citeste_configurarea(radacina).info_dir)
	except Exception:
		return _cale(radacina, P.DOSAR_INFO)


# ---------------------------------------------------------------- fisierele dintr-un .ipk

def _numeMembri(fh):
	"""caile fisierelor obisnuite din data.tar (absolute, ca in listele opkg); fara despachetare pe disc"""
	rez = []
	with tarfile.open(fileobj=fh, mode='r|*') as t:
		for m in t:
			if m.isfile():
				n = '/' + m.name.lstrip('./').lstrip('/')
				if '/../' not in n + '/':
					rez.append(n)
			if len(rez) >= FISIERE_MAX or m.offset_data > MARIME_MAX:
				break
	return rez


class _Bucata(object):
	"""un membru al arhivei ar citit pe rand (tarfile in mod flux citeste numai inainte)"""

	def __init__(self, fh, marime):
		self.fh = fh
		self.ramas = marime

	def read(self, n=-1):
		if self.ramas <= 0:
			return b''
		if n is None or n < 0 or n > self.ramas:
			n = self.ramas
		d = self.fh.read(n)
		self.ramas -= len(d)
		return d


def fisiereIpk(cale):
	"""(numele pachetului, [caile fisierelor]) dintr-un .ipk (ar ca la Debian sau tar.gz ca la opkg-build vechi);
	(nume, []) sau ('', []) daca nu se poate citi."""
	control = P.citeste_control_ipk(cale)
	nume = control.get('package', '')
	try:
		with open(cale, 'rb') as fh:
			if fh.read(8) == b'!<arch>\n':
				for _k in range(16):
					antet = fh.read(60)
					if len(antet) < 60:
						break
					n = antet[:16].strip().rstrip(b'/').decode('ascii', 'replace')
					marime = int(antet[48:58].strip() or b'0')
					if n.startswith('data.tar'):
						return nume, _numeMembri(_Bucata(fh, marime))
					fh.seek(marime + (marime % 2), 1)
				return nume, []
			fh.seek(0)
			with tarfile.open(fileobj=fh, mode='r:*') as t:
				for m in t:
					if m.isfile() and m.name.lstrip('./').startswith('data.tar'):
						date = t.extractfile(m)
						if date is not None:
							return nume, _numeMembri(date)
	except _ERORI as e:
		_jurnal('nu pot citi %s: %s' % (os.path.basename(cale), e))
	return nume, []


# ---------------------------------------------------------------- listele opkg

def _randuriLista(cale):
	try:
		with open(cale, 'rb') as f:
			return f.read().decode('utf-8', 'surrogateescape').splitlines()
	except (IOError, OSError):
		return []


def proprietari(cai, radacina='/'):
	"""{cale: (pachet, randul din lista lui)} pentru caile date, din toate <info>/*.list"""
	cai = set(cai)
	rez = {}
	if not cai:
		return rez
	dosar = _dosarInfo(radacina)
	try:
		nume = sorted(n for n in os.listdir(dosar) if n.endswith('.list'))
	except OSError:
		return rez
	for n in nume:
		for r in _randuriLista(os.path.join(dosar, n)):
			c = r.split('\t', 1)[0].rstrip('/')
			if c in cai:
				rez.setdefault(c, []).append((n[:-5], r))
	return rez


def _scrieAtomic(cale, octeti):
	tmp = cale + '.hds-tmp'
	with open(tmp, 'wb') as f:
		f.write(octeti)
		f.flush()
		os.fsync(f.fileno())
	os.replace(tmp, cale)


def _citesteLista(dosar_tema):
	try:
		with open(os.path.join(dosar_tema, NUME_LISTA), 'rb') as f:
			d = json.loads(f.read().decode('utf-8'))
		if isinstance(d, dict) and isinstance(d.get('fisiere'), dict):
			return d
	except (IOError, OSError, ValueError, UnicodeDecodeError):
		pass
	return {'v': 1, 'fisiere': {}}


def _scrieLista(dosar_tema, d):
	if not d['fisiere']:
		shutil.rmtree(dosar_tema, ignore_errors=True)
		return
	if not os.path.isdir(dosar_tema):
		os.makedirs(dosar_tema)
	_scrieAtomic(os.path.join(dosar_tema, NUME_LISTA), json.dumps(d, ensure_ascii=False, sort_keys=True, indent=1).encode('utf-8'))


def _copie(dosar_tema, cale):
	return os.path.join(dosar_tema, 'fisiere', cale.lstrip('/'))


def _dosarTema(tema, radacina):
	return os.path.join(_cale(radacina, DOSAR), tema)


# ---------------------------------------------------------------- inainte de instalare

def pastreaza(tema, fisiere, radacina='/'):
	"""Copiaza fisierele imaginii (ale altui pachet decat o tema) pe care tema `tema` le va suprascrie, cu randul lor din
	lista pachetului. O copie facuta deja (o actualizare a temei) ramane cea dintai. Intoarce caile copiate acum."""
	if not eTema(tema) or not fisiere:
		return []
	dosar_tema = _dosarTema(tema, radacina)
	d = _citesteLista(dosar_tema)
	noi = []
	for cale, lista in sorted(proprietari(fisiere, radacina).items()):
		if cale in d['fisiere']:
			continue
		ale_altora = [(p, r) for p, r in lista if p != tema]
		if not ale_altora or any(eTema(p) for p, _r in ale_altora):
			continue
		pachet, rand = ale_altora[0]
		real = _cale(radacina, cale)
		try:
			st = os.lstat(real)
		except OSError:
			continue
		if not stat.S_ISREG(st.st_mode):
			continue
		copie = _copie(dosar_tema, cale)
		try:
			if not os.path.isdir(os.path.dirname(copie)):
				os.makedirs(os.path.dirname(copie))
			shutil.copy2(real, copie)
		except (IOError, OSError) as e:
			_jurnal('copia lui %s: %s' % (cale, e))
			continue
		d['fisiere'][cale] = {'pachet': pachet, 'rand': rand}
		noi.append(cale)
	if noi:
		try:
			_scrieLista(dosar_tema, d)
		except (IOError, OSError) as e:
			_jurnal('lista copiilor %s: %s' % (tema, e))
			return []
		_jurnal('%s: copiate inainte de instalare %s' % (tema, ', '.join(noi)))
	return noi


def pastreazaDinIpk(cale_ipk, radacina='/'):
	"""pastreaza() pentru un .ipk de tema; altceva nu se atinge. Intoarce caile copiate."""
	nume, fisiere = fisiereIpk(cale_ipk)
	if not eTema(nume):
		return []
	return pastreaza(nume, fisiere, radacina)


# ---------------------------------------------------------------- dupa lucrare si la pornire

def _adaugaRand(radacina, pachet, rand):
	lista = os.path.join(_dosarInfo(radacina), pachet + '.list')
	randuri = _randuriLista(lista)
	if rand in randuri:
		return
	randuri.append(rand)
	_scrieAtomic(lista, ('\n'.join(randuri) + '\n').encode('utf-8', 'surrogateescape'))


def refa(radacina='/'):
	"""Pune la loc fisierele imaginii pe care nu le mai tine niciun pachet (vezi capul fisierului). Intoarce caile puse
	la loc. Fara copii (cazul obisnuit) nu citeste nimic altceva."""
	baza = _cale(radacina, DOSAR)
	try:
		teme = sorted(n for n in os.listdir(baza) if eTema(n))
	except OSError:
		return []
	puse = []
	dosar_info = _dosarInfo(radacina)
	for tema in teme:
		dosar_tema = os.path.join(baza, tema)
		d = _citesteLista(dosar_tema)
		acum = proprietari(d['fisiere'], radacina)
		for cale in sorted(d['fisiere']):
			e = d['fisiere'][cale]
			cine = [p for p, _r in acum.get(cale, ())]
			if tema in cine:
				continue                          # tema e inca instalata si il tine
			copie = _copie(dosar_tema, cale)
			if e.get('pachet') in cine or not os.path.exists(os.path.join(dosar_info, str(e.get('pachet')) + '.list')):
				pass                              # al imaginii din nou, sau pachetul imaginii nu mai e: copia nu mai trebuie
			elif cine:
				# alta tema l-a luat peste: copia trece la ea
				alta = cine[0]
				if eTema(alta):
					dosar_alta = os.path.join(baza, alta)
					da = _citesteLista(dosar_alta)
					if cale not in da['fisiere']:
						try:
							if not os.path.isdir(os.path.dirname(_copie(dosar_alta, cale))):
								os.makedirs(os.path.dirname(_copie(dosar_alta, cale)))
							shutil.copy2(copie, _copie(dosar_alta, cale))
							da['fisiere'][cale] = e
							_scrieLista(dosar_alta, da)
						except (IOError, OSError) as er:
							_jurnal('copia lui %s la %s: %s' % (cale, alta, er))
							continue
			else:
				real = _cale(radacina, cale)
				try:
					if not os.path.isdir(os.path.dirname(real)):
						os.makedirs(os.path.dirname(real))
					tmp = real + '.hds-tmp'
					shutil.copy2(copie, tmp)
					os.replace(tmp, real)
					_adaugaRand(radacina, e['pachet'], e['rand'])
				except (IOError, OSError, KeyError) as er:
					_jurnal('punerea la loc a lui %s: %s' % (cale, er))
					continue
				puse.append(cale)
			del d['fisiere'][cale]
		try:
			_scrieLista(dosar_tema, d)
		except (IOError, OSError) as er:
			_jurnal('lista copiilor %s: %s' % (tema, er))
	try:
		os.rmdir(baza)                            # gol: la pornire nu se mai porneste nimic
	except OSError:
		pass
	if puse:
		_jurnal('puse la loc dupa stergerea temelor: %s' % ', '.join(puse))
	return puse


def laPornire():
	"""refa() pe un fir separat, la pornirea interfetei (o tema stearsa din alt panou sau din linia de comanda)"""
	try:
		if not os.path.isdir(DOSAR):
			return
		import threading
		fir = threading.Thread(target=refa, name='HdsTemeSuprascrise')
		fir.daemon = True
		fir.start()
	except Exception as e:
		_jurnal('la pornire: %s' % e)
