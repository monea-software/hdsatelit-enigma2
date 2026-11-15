# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPachetePornire: pachetele Python de care depinde pornirea interfetei si paza lor la instalare (0.7.5, CTU, TODO 15.11 07:08).
#
# De ce (Ustym 4K PRO, raportul 340957, 0.7.4): un pachet strain instalat cu opkg a inlocuit python3-attrs si twisted ale
# imaginii. enigma2 cadea la fiecare pornire in "import e2reactor" (mytest.py) cu attr.exceptions.UnannotatedAttributeError
# (o versiune veche de attrs, fara adnotarile amanate din Python 3.14), iar modul sigur nu ajuta: cade inainte de pluginuri.
# Un pachet scris numai in Python nu are module .so, deci refuzul pentru alt Python (HdsPython2.alt_python) nu-l prinde.
#
# Aici:
#   - PACHETE_PORNIRE si PREFIXE_PORNIRE: pachetele fara de care mytest.py nu trece de importul lui twisted (Python, attrs,
#     twisted si dependintele lor, ca in manifestul imaginii). Aceeasi lista sta in tools/hds-actualizare-intrerupta.py
#     (programul nu importa nimic din enigma2); proba test_ctu_lista_pornire_075 le compara.
#   - verifica(cale): un .ipk care ar inlocui unul dintre ele, instalat acum, se refuza (Components/HdsExtensiiLucru.py,
#     fila Din fisier pe televizor si in pagina web, si pachetele surselor straine dupa descarcare, cu dependintele lor):
#       nume       acelasi nume de pachet, dar fisierul nu e cel din listele feedului HD Satelit (suma SHA256 alta);
#       inlocuieste  alt nume, cu Replaces, Provides sau Conflicts pe unul dintre ele;
#       fisiere    alt nume, cu un fisier care e al unuia dintre ele (/var/lib/opkg/info/<pachet>.list).
#     Un pachet nou (python3-foo, cerut de un plugin) nu e oprit: sunt pazite numai pachetele pornirii instalate acum.
#
# Numai biblioteca standard si nimic din enigma2 la incarcare: probele de pe PC il folosesc direct. Nu se despacheteaza
# nimic pe disc si nu se ruleaza nimic din pachet.

import gzip
import hashlib
import io
import os
import tarfile

PACHETE_PORNIRE = frozenset((
	'python3', 'python3-core', 'python3-attrs', 'python3-automat', 'python3-cffi', 'python3-constantly',
	'python3-cryptography', 'python3-hyperlink', 'python3-idna', 'python3-incremental', 'python3-pyasn1',
	'python3-pyasn1-modules', 'python3-pyopenssl', 'python3-service-identity', 'python3-six', 'python3-typing-extensions',
	'python3-zopeinterface',
))
PREFIXE_PORNIRE = ('python3-twisted', 'libpython3')

STATUS = '/var/lib/opkg/status'
INFO = '/var/lib/opkg/info'
LISTE = '/var/lib/opkg/lists'
DOSAR_CONF = '/etc/opkg'
# sursele HD Satelit: /etc/opkg/hdsatelit-feed.conf (imaginea) si celelalte hdsatelit-*.conf (completari, drivere)
PREFIX_CONF = 'hdsatelit'

_AR = b'!<arch>\n'
_MAXIM_CONTROL = 1 << 20
_MAXIM_MEMBRI = 200000


def al_pornirii(nume):
	"""True pentru un pachet de care depinde pornirea interfetei"""
	return isinstance(nume, str) and (nume in PACHETE_PORNIRE or nume.startswith(PREFIXE_PORNIRE))


def _cale(radacina, cale):
	return os.path.join(radacina or '/', cale.lstrip('/'))


# ---------------------------------------------------------------- fisierul .ipk

class _Bucata(object):
	"""o bucata dintr-un fisier deschis, citita pe rand (tarfile in mod flux), fara sa fie copiata in memorie"""

	def __init__(self, fh, inceput, marime):
		self.fh = fh
		self.ramas = marime
		fh.seek(inceput)

	def read(self, n=-1):
		if self.ramas <= 0:
			return b''
		if n is None or n < 0 or n > self.ramas:
			n = self.ramas
		date = self.fh.read(n)
		self.ramas -= len(date)
		return date


def _membri_ar(fh):
	"""[(nume, inceput, marime)] ai unui .ipk in format ar"""
	rez = []
	fh.seek(len(_AR))
	for _k in range(16):
		antet = fh.read(60)
		if len(antet) < 60:
			break
		nume = antet[:16].strip().rstrip(b'/').decode('ascii', 'replace')
		try:
			marime = int(antet[48:58].strip() or b'0')
		except ValueError:
			break
		rez.append((nume, fh.tell(), marime))
		fh.seek(marime + (marime % 2), 1)
	return rez


def _control(text):
	d = {}
	cheie = None
	for rand in text.splitlines():
		if rand[:1] in (' ', '\t'):
			continue
		k, semn, v = rand.partition(':')
		if semn and k.strip():
			cheie = k.strip().lower()
			d[cheie] = v.strip()
		elif not rand.strip() and cheie:
			break
	return d


def _din_tar(t, control):
	"""(control, fisiere) din arhiva tar deschisa in mod flux"""
	fisiere = []
	ctrl = {}
	for n, m in enumerate(t):
		if n > _MAXIM_MEMBRI:
			break
		nume = '/' + m.name.lstrip('./')
		if control:
			if m.isfile() and nume == '/control' and m.size <= _MAXIM_CONTROL:
				f = t.extractfile(m)
				if f is not None:
					ctrl = _control(f.read().decode('utf-8', 'replace'))
					break
		elif not m.isdir() and nume != '/':
			fisiere.append(nume)
	return ctrl, fisiere


def citeste_ipk(cale):
	"""(control, fisiere) ale unui .ipk: campurile din control cu chei mici si caile fisierelor (fara dosare), cu / in
	fata; ({}, []) daca nu se poate citi"""
	control, fisiere = {}, []
	try:
		with open(cale, 'rb') as fh:
			if fh.read(8) != _AR:
				# opkg-build vechi: un tar.gz cu control.tar.gz si data.tar.gz inauntru
				fh.seek(0)
				with tarfile.open(fileobj=fh, mode='r:*') as t:
					for m in t:
						if m.isfile() and m.name.lstrip('./').startswith(('control.tar', 'data.tar')):
							f = t.extractfile(m)
							if f is None:
								continue
							with tarfile.open(fileobj=io.BytesIO(f.read()), mode='r:*') as s:
								if m.name.lstrip('./').startswith('control.tar'):
									control = _din_tar(s, True)[0]
								else:
									fisiere = _din_tar(s, False)[1]
				return control, fisiere
			for nume, inceput, marime in _membri_ar(fh):
				if nume.startswith('control.tar') and 0 < marime <= _MAXIM_CONTROL:
					with tarfile.open(fileobj=_Bucata(fh, inceput, marime), mode='r|*') as t:
						control = _din_tar(t, True)[0]
				elif nume.startswith('data.tar') and marime > 0:
					with tarfile.open(fileobj=_Bucata(fh, inceput, marime), mode='r|*') as t:
						fisiere = _din_tar(t, False)[1]
	except (tarfile.TarError, OSError, EOFError, ValueError, LookupError, MemoryError) as e:
		print('[HdsPachetePornire] %s nu se poate citi: %s' % (os.path.basename(cale or ''), e))
	except Exception as e:  # lzma, zlib, zstd: erorile modulelor de dezarhivare
		print('[HdsPachetePornire] %s nu se poate citi: %s' % (os.path.basename(cale or ''), e))
	return control, fisiere


# ---------------------------------------------------------------- ce e instalat

def instalate(radacina='/'):
	"""{nume: versiune} ale pachetelor instalate (status-ul opkg)"""
	rez = {}
	try:
		with open(_cale(radacina, STATUS), 'r', encoding='utf-8', errors='replace') as f:
			text = f.read()
	except (IOError, OSError):
		return rez
	for strofa in text.split('\n\n'):
		d = _control(strofa)
		st = d.get('status', '').split()
		if d.get('package') and 'installed' in st and 'not-installed' not in st:
			rez[d['package']] = d.get('version', '')
	return rez


def fisiere_pornire(radacina='/', inst=None):
	"""{cale: pachet} ale fisierelor pachetelor pornirii instalate"""
	rez = {}
	for nume in sorted(inst if inst is not None else instalate(radacina)):
		if not al_pornirii(nume):
			continue
		try:
			with open(_cale(radacina, '%s/%s.list' % (INFO, nume)), 'r', encoding='utf-8', errors='replace') as f:
				for rand in f:
					c = rand.rstrip('\n').split('\t', 1)[0].strip()
					if c.startswith('/'):
						rez.setdefault(c, nume)
		except (IOError, OSError):
			pass
	return rez


def sume_feed(radacina='/'):
	"""Sumele SHA256 ale pachetelor din listele surselor HD Satelit descarcate (/etc/opkg/hdsatelit*.conf)"""
	sume = set()
	try:
		confuri = sorted(n for n in os.listdir(_cale(radacina, DOSAR_CONF)) if n.startswith(PREFIX_CONF) and
			n.endswith('.conf'))
	except OSError:
		return sume
	for n in confuri:
		try:
			with open(_cale(radacina, '%s/%s' % (DOSAR_CONF, n)), 'r', encoding='utf-8', errors='replace') as f:
				surse = [r.split()[1] for r in f if r.split()[:1] in (['src'], ['src/gz']) and len(r.split()) >= 3]
		except (IOError, OSError):
			continue
		for s in surse:
			for cand in (s, s + '.gz'):
				cale = _cale(radacina, '%s/%s' % (LISTE, cand))
				if not os.path.isfile(cale):
					continue
				try:
					deschide = gzip.open if cand.endswith('.gz') else open
					with deschide(cale, 'rt', encoding='utf-8', errors='replace') as f:
						for rand in f:
							if rand.startswith('SHA256sum:'):
								sume.add(rand.split(':', 1)[1].strip().lower())
				except (IOError, OSError, EOFError, ValueError):
					pass
				break
	return sume


def _sha256(cale):
	h = hashlib.sha256()
	with open(cale, 'rb') as f:
		while True:
			b = f.read(1 << 16)
			if not b:
				break
			h.update(b)
	return h.hexdigest()


def _nume_din(camp):
	"""numele dintr-un camp Depends/Replaces/Provides/Conflicts (fara versiuni si alternative)"""
	rez = []
	for parte in (camp or '').replace('|', ',').split(','):
		n = parte.strip().split(' ', 1)[0].split('(', 1)[0].strip()
		if n:
			rez.append(n)
	return rez


# ---------------------------------------------------------------- hotararea

def verifica(cale, radacina='/', inst=None, sume=None):
	"""None cand pachetul nu atinge pachetele pornirii, altfel {fel, pachet, versiune, inlocuit, instalata, fisier}
	(fel: nume, inlocuieste sau fisiere; vezi antetul)"""
	inst = instalate(radacina) if inst is None else inst
	pazite = dict((n, v) for n, v in inst.items() if al_pornirii(n))
	if not pazite:
		return None
	control, fisiere = citeste_ipk(cale)
	nume = control.get('package', '')
	versiune = control.get('version', '')

	def al_nostru():
		try:
			return _sha256(cale) in (sume_feed(radacina) if sume is None else sume)
		except (IOError, OSError):
			return False

	rez = {'pachet': nume, 'versiune': versiune, 'fisier': ''}
	if nume in pazite:
		if al_nostru():
			return None
		rez.update(fel='nume', inlocuit=nume, instalata=pazite[nume])
		return rez
	for camp in ('replaces', 'provides', 'conflicts'):
		for n in _nume_din(control.get(camp)):
			if n in pazite and n != nume:
				if al_nostru():
					return None
				rez.update(fel='inlocuieste', inlocuit=n, instalata=pazite[n])
				return rez
	if fisiere:
		ale_lor = fisiere_pornire(radacina, pazite)
		for f in fisiere:
			p = ale_lor.get(f)
			if p and p != nume:
				if al_nostru():
					return None
				rez.update(fel='fisiere', inlocuit=p, instalata=pazite[p], fisier=f)
				return rez
	return None
