# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Dead opkg sources and the opkg lock (OPK1, 0.8.0, AS217).

Why: opkg 0.10.0 of the image downloads with `wget -q -Y --dns-timeout=10 --connect-timeout=30` (fixed in libopkg,
no option). A source whose server never answers (a feed written by a foreign plugin manager, a host blocked by the
network of the user) costs 30 s per address and try: 360 s for GitHub Pages (4 IPv4 addresses x 3 tries). During
that time opkg holds /run/opkg.lock, Software update looks frozen and every install fails with "Could not lock".
OE-Alliance does not probe the sources and does not wait for the lock (Components/Opkg.py only reports
EVENT_OPKG_IN_USE and the network error afterwards).

What this module does:
- before an `opkg update` started by the image, every foreign source in /etc/opkg/*.conf is probed once, all in
  parallel, with wget itself (--spider --tries=1, short timeouts, so the same IPv4 preference and DNS path as opkg);
- a source that gives no answer at all (wget exit 4, or still running at the deadline) is skipped for this run only:
  opkg gets `-f /tmp/hds-opkg-update.conf`, one file with the content of every /etc/opkg/*.conf in the order opkg
  reads them, with the src line of that source commented out. The files of the user are never changed.
  Proven on the receiver: `opkg -f FILE` (or --conf) loads only the given files, not /etc/opkg/*.conf, and an
  update that skips a source keeps the list already downloaded from it (/var/lib/opkg/lists/<name>);
- any HTTP answer (404, 405, 5xx), a TLS or certificate error counts as alive: opkg fails fast there, it does not hang;
- our sources (hdsatelit.com, moneasoftware.com) are never probed and never skipped. One of ours is probed only as a
  reference: when it does not answer either (no internet, DNS down), nothing is skipped and no note names a foreign
  source; without a default route nothing is probed;
- results are kept PASTRARE_S seconds (Extensii and Software update one after the other probe once).

No enigma import: the functions run on the PC tests with a root directory (radacina)."""
import os
import subprocess
import time

try:
	from urllib.parse import urlsplit
except ImportError:  # Python 2 (old tests only)
	from urlparse import urlsplit

TERMEN_PROBA_S = 5          # wget --dns-timeout / --connect-timeout / --read-timeout of one probe
TERMEN_TOTAL_S = 7          # all probes run together; still running at this point = no answer
PASTRARE_S = 120            # a probe result is reused for this long
CONF_TEMPORAR = '/tmp/hds-opkg-update.conf'
DOSAR_CONF = '/etc/opkg'
DOMENII_NOASTRE = ('hdsatelit.com', 'moneasoftware.com')
SCHEME_PROBATE = ('http', 'https', 'ftp')
# wget exit codes: 4 = network failure (connect timeout, unreachable, DNS); everything else means some answer
COD_FARA_RASPUNS = 4
WGET = ('/usr/bin/wget', '/bin/wget')
# lines the image adds to the opkg output (IpkgComponent EVENT_LINE): already translated, shown as they are
PREFIX_NOTA = '[HDS] '
# opkg lock: how long an image command waits for another opkg (Software update, SSH, a plugin) before it runs anyway
ZAVOR_ASTEPTARE_S = 20 * 60
ZAVOR_PAS_S = 1.0
ZAVOR_ASTEPTARE_FIR_S = 5 * 60   # argumente_update (workers with a subprocess opkg): shorter, they have own deadlines
ZAVOR_REINCERCARI = 5      # "Could not lock" right after the lock looked free (race): wait again, at most this often

# tests replace these
PROBA = None                # function([url, ...], termen) -> {url: True/False}
OCUPAT = None               # function(radacina) -> bool
RETEA = None                # function(radacina) -> bool (True = there is a default route)

_cache = {}                 # url -> (time, alive)


def _t(text):
	"""enigma2 translation (_ from builtins), or the text itself on the PC tests"""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _cale(radacina, cale):
	if not radacina or radacina == '/':
		return cale
	return os.path.join(radacina, cale.lstrip('/'))


def _jurnal(text):
	print('[HdsSurseOpkg] %s' % text)


def este_nota(linie):
	return isinstance(linie, str) and linie.startswith(PREFIX_NOTA)


def text_nota(linie):
	return linie[len(PREFIX_NOTA):] if este_nota(linie) else linie


def nota(text):
	return PREFIX_NOTA + text


def gazda(adresa):
	try:
		return (urlsplit(adresa or '').hostname or '').lower()
	except ValueError:
		return ''


def a_noastra(adresa):
	"""a source of HD Satelit / Monea Software (any scheme): never probed, never skipped"""
	g = gazda(adresa)
	return any(g == d or g.endswith('.' + d) for d in DOMENII_NOASTRE)


def fisiere_conf(radacina='/'):
	"""the files opkg 0.10 reads without -f: /etc/opkg/*.conf, sorted (glob order)"""
	dosar = _cale(radacina, DOSAR_CONF)
	try:
		nume = sorted(os.listdir(dosar))
	except OSError:
		return []
	return [os.path.join(dosar, n) for n in nume if n.endswith('.conf') and os.path.isfile(os.path.join(dosar, n))]


def _citeste(cale):
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as f:
			return f.read()
	except (IOError, OSError):
		return None


def surse(radacina='/'):
	"""[(name, url, gz, file)] of the active src / src/gz lines, first declaration of a name only (as opkg)"""
	rez, vazute = [], set()
	for cale in fisiere_conf(radacina):
		text = _citeste(cale)
		if text is None:
			continue
		for rand in text.splitlines():
			p = rand.split()
			if len(p) >= 3 and p[0] in ('src', 'src/gz') and p[1] not in vazute:
				vazute.add(p[1])
				rez.append((p[1], p[2], p[0] == 'src/gz', cale))
	return rez


def _probata(adresa):
	try:
		return urlsplit(adresa).scheme.lower() in SCHEME_PROBATE
	except ValueError:
		return False


def adresa_probei(adresa, gz):
	return adresa.rstrip('/') + ('/Packages.gz' if gz else '/Packages')


def _wget():
	for p in WGET:
		if os.path.isfile(p) and os.access(p, os.X_OK):
			return p
	return None


def proba_wget(adrese, termen=TERMEN_PROBA_S, total=TERMEN_TOTAL_S):
	"""{url: alive} for all urls at once; one request each, no retries. Without wget everything counts as alive."""
	program = _wget()
	if program is None:
		return dict((a, True) for a in adrese)
	procese = {}
	for a in adrese:
		try:
			procese[a] = subprocess.Popen([program, '-q', '--spider', '--tries=1', '--dns-timeout=%d' % termen,
				'--connect-timeout=%d' % termen, '--read-timeout=%d' % termen, '-O', '/dev/null', a],
				stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
		except (OSError, ValueError):
			procese[a] = None
	rez = {}
	sfarsit = time.time() + total
	while True:
		for a, p in procese.items():
			if a in rez:
				continue
			if p is None:
				rez[a] = True
				continue
			cod = p.poll()
			if cod is not None:
				rez[a] = cod != COD_FARA_RASPUNS
		if len(rez) == len(procese) or time.time() >= sfarsit:
			break
		time.sleep(0.1)
	for a, p in procese.items():
		if a not in rez:
			rez[a] = False
			try:
				p.kill()
				p.wait()
			except OSError:
				pass
	return rez


def _proba(adrese):
	acum = time.time()
	rez, de_probat = {}, []
	for a in adrese:
		c = _cache.get(a)
		if c is not None and acum - c[0] < PASTRARE_S:
			rez[a] = c[1]
		else:
			de_probat.append(a)
	if de_probat:
		noi = (PROBA or proba_wget)(de_probat, TERMEN_PROBA_S)
		for a in de_probat:
			rez[a] = bool(noi.get(a, True))
			_cache[a] = (acum, rez[a])
	return rez


def uita_probele():
	_cache.clear()


def are_retea(radacina='/'):
	"""False only when there is no default route at all (Components/HdsActualizari.fara_retea)"""
	if RETEA is not None:
		return bool(RETEA(radacina))
	try:
		try:
			from Components.HdsActualizari import fara_retea
		except ImportError:
			from HdsActualizari import fara_retea
		return not fara_retea(radacina)
	except Exception:
		return True


def de_probat(radacina='/'):
	"""True when an update has a foreign http(s)/ftp source to probe (otherwise opkg starts at once, as before)"""
	return any(_probata(a) and not a_noastra(a) for _n, a, _g, _f in surse(radacina))


class Pregatire(object):
	"""prefix: arguments before the opkg command (['-f', file] or []); sarite: [(name, url, file)]; note: texts for
	the screen (already translated)"""
	def __init__(self, prefix=None, sarite=None, note=None):
		self.prefix = prefix or []
		self.sarite = sarite or []
		self.note = note or []


def pregateste_update(radacina='/'):
	"""Probes the foreign sources (blocking, at most TERMEN_TOTAL_S) and returns a Pregatire. Call it off the UI
	thread (IpkgComponent does) or from a worker."""
	lista = surse(radacina)
	straine = [(n, a, g, f) for n, a, g, f in lista if _probata(a) and not a_noastra(a)]
	if not straine or not are_retea(radacina):
		return Pregatire()
	referinta = [adresa_probei(a, g) for _n, a, g, _f in lista if a_noastra(a) and _probata(a)][:1]
	adrese = [adresa_probei(a, g) for _n, a, g, _f in straine]
	vii = _proba(adrese + referinta)
	if referinta and not vii.get(referinta[0], True):
		_jurnal('our source %s gives no answer either: nothing skipped (network problem)' % gazda(referinta[0]))
		return Pregatire()
	moarte = [(n, a, f) for n, a, g, f in straine if not vii.get(adresa_probei(a, g), True)]
	if not moarte:
		return Pregatire()
	cale = scrie_conf_temporar(radacina, set(n for n, _a, _f in moarte))
	if cale is None:
		return Pregatire()
	note = []
	for n, a, f in moarte:
		_jurnal('source %s (%s, %s) gives no answer in %d s: skipped for this opkg update' % (
			n, a, os.path.basename(f), TERMEN_TOTAL_S))
		note.append(nota(_t('Sursa de pachete „%s” (%s) nu răspunde; o sar de data asta.') % (n, gazda(a) or a)))
	return Pregatire(['-f', CONF_TEMPORAR if not radacina or radacina == '/' else cale], moarte, note)


def scrie_conf_temporar(radacina, sarite):
	"""CONF_TEMPORAR: every /etc/opkg/*.conf in opkg order, the src lines of `sarite` commented out; None on error"""
	parti = []
	for cale in fisiere_conf(radacina):
		text = _citeste(cale)
		if text is None:
			continue
		randuri = ['# %s' % cale]
		for rand in text.splitlines():
			p = rand.split()
			if len(p) >= 3 and p[0] in ('src', 'src/gz') and p[1] in sarite:
				rand = '# hds: no answer, skipped for this update: ' + rand
			randuri.append(rand)
		parti.append('\n'.join(randuri))
	tinta = _cale(radacina, CONF_TEMPORAR)
	temporar = tinta + '.%d' % os.getpid()
	try:
		dosar = os.path.dirname(tinta)
		if not os.path.isdir(dosar):
			os.makedirs(dosar)
		with open(temporar, 'w', encoding='utf-8') as f:
			f.write('\n'.join(parti) + '\n')
		os.replace(temporar, tinta)
		return tinta
	except (IOError, OSError) as e:
		_jurnal('%s: %s' % (tinta, e))
		try:
			os.unlink(temporar)
		except OSError:
			pass
		return None


def argumente_update(radacina='/'):
	"""For the callers that run opkg themselves (subprocess, on a worker): the arguments after the program,
	['-f', CONF_TEMPORAR, 'update'] when a foreign source is skipped, else ['update']. Blocking: first waits up to
	ZAVOR_ASTEPTARE_FIR_S for another opkg (the update and the install that usually follows it would get 255)."""
	try:
		if not asteapta_zavorul(radacina, ZAVOR_ASTEPTARE_FIR_S):
			_jurnal('another opkg still holds the lock after %d s; running anyway' % ZAVOR_ASTEPTARE_FIR_S)
		return pregateste_update(radacina).prefix + ['update']
	except Exception as e:
		_jurnal('probe: %r' % (e,))
		return ['update']


# ---------------------------------------------------------------- the opkg lock

def zavor_ocupat(radacina='/'):
	"""another opkg holds /run/opkg.lock (Components/HdsActualizari.opkg_ocupat, read from /proc/locks)"""
	if OCUPAT is not None:
		return bool(OCUPAT(radacina))
	try:
		try:
			from Components.HdsActualizari import opkg_ocupat
		except ImportError:
			from HdsActualizari import opkg_ocupat
		return bool(opkg_ocupat(radacina))
	except Exception:
		return False


def text_asteptare():
	return nota(_t('Aștept să termine altă operație cu pachetele...'))


def zavor_prins(linie):
	"""the lines opkg 0.10 writes when another opkg holds the lock (seen on the receiver, exit 255):
	"error: opkg_lock: Could not lock /run/opkg.lock: Resource temporarily unavailable."
	"error: opkg_cmd_exec: Command failed to capture privilege lock: Resource temporarily unavailable." """
	return isinstance(linie, str) and ('Could not lock' in linie or 'capture privilege lock' in linie)


def asteapta_zavorul(radacina='/', termen=ZAVOR_ASTEPTARE_S, pas=ZAVOR_PAS_S):
	"""blocking (workers only): True when the lock is free, False after `termen` seconds"""
	sfarsit = time.time() + termen
	while zavor_ocupat(radacina):
		if time.time() >= sfarsit:
			return False
		time.sleep(pas)
	return True
