# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Transfer local de surse IPTV, fara acces la retea."""
import io
import tarfile
import hashlib
import json
import os
import re
import stat
import tempfile
import errno
import shutil
import base64
import secrets
import threading
from bisect import bisect_right
from collections import Counter
from itertools import islice
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
from Components import HdsIptvSurse as I

MAX_FISIER = 4 * 1024 * 1024
MAX_PLAYLIST = 64 * 1024 * 1024
MAX_RANDURI = 10000
MAGIC_TRANSFER = b'HDSIPTV1 '
MAGIC_ARHIVA = b'HDSIPTV2\n'
MAX_ARHIVA = 20 * 1024 * 1024 * 1024
MAX_META = 16 * 1024
MAX_BUCATA = 512 * 1024
_WEB_LACAT = threading.RLock()
_WEB_TRANSFER = None
_IMPORT_LACAT = threading.RLock()
ANTETE = ('user_agent', 'referer', 'x_user_agent', 'stb_type')
CAMPURI_XTREAM = ('baza', 'format')
OPTIUNI = ('player', 'piconuri', 'ascunse', 'ordine')
_MAC = re.compile(r'(?<!\w)(?:[0-9a-fA-F]{2}(?:[:.-][0-9a-fA-F]{2}){5}|[0-9a-fA-F]{4}(?:\.[0-9a-fA-F]{4}){2}|[0-9a-fA-F]{12})(?!\w)')
_URL = re.compile(r'''(?ai)(?:[a-z][a-z0-9+.-]{0,23}://[^\s]+|(?<![\w@./-])(?:[a-z0-9][a-z0-9-]{0,62}\.)+(?:[a-z]{2,24}|[0-9]{1,3})(?::[0-9]{1,5})?(?:/[^\s]*)?)''')
_LABEL = re.compile(r'(?i)(?:^|(?<![\s;|,])(?:[;|,]+[^\S\r\n]+|[^\S\r\n]+(?:[;|,]+[^\S\r\n]+)?))(portal|url|server|host|mac|username|user|utilizator|nume utilizator|password|pass|parola|parolă|name|nume)\s*[:=][^\S\r\n]*')


def N_(text):
	return text


T_REZUMAT = N_('Găsite: %d. Deja prezente sau repetate: %d. De adăugat: %d. Rânduri necitibile: %d.')
T_RANDURI = N_('Rândurile necitibile: %s.')
T_LIMITA = N_('Ai %d surse din %d posibile. Nu mai încap: %d.')
T_ADAUGATE = N_('Surse adăugate: %d. Deschide o sursă sau apasă Actualizează pe ea ca să te conectezi.')
T_MARE = N_('Fișierul e prea mare. Alege un fișier de cel mult 4 MB și 10000 de rânduri.')
T_CITIRE = N_('Fișierul nu s-a putut citi. Alege un fișier text UTF-8 sau JSON de pe stick ori disc.')
T_SURSE_CITIRE = N_('Sursele salvate nu se pot citi. Nu s-a schimbat nimic.')
T_NEACCEPTAT = N_('Rândul %d: nu se poate adăuga încă: %s')
T_PROTOCOL = N_('Protocolul sau tipul listei nu este acceptat de player.')
T_DRM = N_('Sursa cere un sistem DRM care nu este disponibil.')
T_EPG = N_('XMLTV conține numai programul TV. Se folosește ca adresă de ghid într-un playlist, nu ca sursă de canale.')
T_DETERIORATA = N_('Copia e deteriorată. Nu s-a schimbat nimic. Exportă din nou copia de pe receptorul de origine.')
T_LOCAL = N_('Lista locală nu este disponibilă pentru export. Pune fișierul original în import.')


def _fel(s):
	return s.get('fel', 'stalker')


def _lista(text, nume=''):
	return dict(fel='m3u', continut=text, nume=I.numeCurat(nume))


def _adresaImport(url):
	# In import, o bara literala se protejeaza pentru playerul existent.
	if '|' in url and not re.search(r'\|(?:[^|]*&)?(?:User-Agent|Referer|Referrer)=', url, re.I):
		url = url.replace('|', '%7C')
	return url


def _flux(url, nume=''):
	url = _adresaImport(url)
	return _lista('#EXTM3U\n#EXTINF:-1,' + I.numeCurat(nume, I.gazdaAdresei(url)) + '\n' + url + '\n', nume)


def _optiuni(s):
	"""Aceeasi forma implicita la import, export si comparare."""
	rez = dict(player=I.playerSursa(s), piconuri=s.get('piconuri') is True)
	for k in ('ascunse', 'ordine'):
		v = s.get(k)
		rez[k] = [x for x in v if isinstance(x, str) and I.textBun(x)] if isinstance(v, (list, _OptiuniTransfer)) else []
	return rez


def _curata(d):
	if not isinstance(d, dict):
		return None
	fel = _fel(d)
	nume = I.numeCurat(d.get('nume', '')) if isinstance(d.get('nume', ''), str) else ''
	if fel == 'stalker':
		portal, mac = d.get('portal', d.get('url', '')), I.macCurat(d.get('mac'))
		if not isinstance(portal, str) or not I.desparteServer(portal) or not mac:
			return None
		s = dict(portal=portal.strip(), mac=mac, nume=nume)
	elif fel == 'xtream':
		server, user, parola = (d.get(k, '') for k in ('server', 'utilizator', 'parola'))
		if not all(isinstance(v, str) and v and I.textBun(v) for v in (server, user, parola)) or not I.desparteServer(server):
			return None
		s = dict(fel=fel, server=server.strip(), utilizator=user, parola=parola, nume=nume)
	elif fel == 'm3u':
		continut, adresa = d.get('continut'), d.get('adresa', '')
		if continut is not None:
			if not isinstance(continut, str) or len(continut.encode('utf-8')) > MAX_FISIER or not continut.startswith('#EXTM3U'):
				return None
			s = _lista(continut, nume)
		elif isinstance(adresa, str) and adresa.startswith(('http://', 'https://')) and I.adresaListaBuna(adresa):
			s = dict(fel=fel, adresa=adresa, nume=nume)
		else:
			return None
	elif fel == 'demo':
		s = dict(fel=fel, nume=nume)
	else:
		return None
	for k in ANTETE + (CAMPURI_XTREAM if fel == 'xtream' else ()):
		v = d.get(k, '')
		if not isinstance(v, str) or not I.textBun(v, 2048):
			continue
		if v:
			s[k] = v
	s.update({k:v for k,v in _optiuni(d).items() if k in d})
	return s


def _adresa(url, nume=''):
	# Limita precede orice despartire sau decodare a parametrilor.
	if not I.textBun(url, I.MAX_ADRESA):
		return 'nu', T_PROTOCOL
	if '://' not in url:
		url = 'http://' + url
	try:
		p = urlsplit(url)
		p.port
	except ValueError:
		return 'nu', T_PROTOCOL
	cale = p.path.lower().rstrip('/')
	if 'xmltv' in cale or cale.endswith(('.xml', '.xml.gz', '.xml.xz', '.xmltv')):
		return 'nu', T_EPG
	if cale.endswith(('/get.php', '/player_api.php')):
		try:
			q = parse_qs(p.query, max_num_fields=256)
		except ValueError:
			return 'nu', T_PROTOCOL
		if p.scheme in ('http', 'https') and q.get('username') and q.get('password'):
			server = urlunsplit((p.scheme, p.netloc, p.path.rsplit('/', 1)[0], '', ''))
			return 'sursa', _curata(dict(fel='xtream', server=server, utilizator=q['username'][0], parola=q['password'][0], nume=nume))
		return 'nu', T_PROTOCOL
	if p.scheme not in I.SCHEME_FLUX or not I.fluxBun(url):
		return 'nu', T_PROTOCOL
	if cale.endswith(('.pls', '.xspf', '.strm')):
		return 'nu', T_PROTOCOL
	if p.scheme in ('http', 'https') and cale.endswith(('.m3u', '.m3u8', '.tv')):
		return 'sursa', dict(fel='m3u', adresa=url, nume=I.numeCurat(nume))
	if p.scheme in ('http', 'https') and (not cale or cale.endswith(('/c', '/stalker_portal', '/portal.php')) or '/stalker_portal/' in cale):
		return 'portal', url
	return 'sursa', _flux(url, nume)


def _urlDinProza(rand, potrivire):
	"""Numai o pereche explicita de delimitatori poate inchide o adresa."""
	url = potrivire[0]
	if potrivire.start():
		inchide = {'"':'"', "'":"'", '`':'`', '“':'”', '„':'”', '‘':'’', '<':'>', '(' : ')', '[':']', '{':'}'}.get(rand[potrivire.start()-1])
		if inchide and url.endswith(inchide):
			return url[:-1]
	return url


class _AdresaGasita:
	"""Interval fara copierea prefixului randului."""
	def __init__(self, rand, start, end):
		self.rand, self.inceput, self.sfarsit = rand, start, end
	def start(self): return self.inceput
	def end(self): return self.sfarsit
	def __getitem__(self, index):
		if index != 0:
			raise IndexError(index)
		return self.rand[self.inceput:self.sfarsit]


def _adrese(rand):
	"""Separatoarele dintre portal si un MAC complet sunt sintaxa de tabel.

	In parametri si fragmente, orice asemenea secventa ramane in adresa.
	"""
	for m in _URL.finditer(rand):
		url = m[0]
		end = m.end()
		# CSV: ghilimelele si separatorul inchid campul, nu adresa.
		if m.start() and rand[m.start()-1] == '"':
			stop = rand.find('"', m.start())
			if stop >= 0 and (stop + 1 == len(rand) or rand[stop+1] in ',;\t'):
				url, end = rand[m.start():stop], stop
		if len(url) <= I.MAX_ADRESA and '?' not in url and '#' not in url:
			coada = len(url.rstrip(',;|'))
			for mac in reversed(list(_MAC.finditer(url))):
				if mac.end() != coada or not mac.start() or url[mac.start()-1] not in ',;|':
					break
				coada = len(url[:mac.start()].rstrip(',;|'))
				end = m.start() + coada
		yield _AdresaGasita(rand, m.start(), end)


def _valoareEticheta(text, cheie=''):
	"""Punctuatia finala apartine valorii; ghilimelele pereche sunt sintaxa."""
	text = text.strip()
	if len(text) >= 2 and (text[0], text[-1]) in (('"', '"'), ("'", "'"), ('“', '”'), ('„', '”'), ('‘', '’')):
		return text[1:-1]
	return text


def _m3uCanale(canale, epg=''):
	"""Formatele locale devin playlisturi native, cu nume si antete pastrate."""
	randuri = ['#EXTM3U' + (' url-tvg="%s"' % epg.replace('"', '') if epg else '')]
	octeti = len(randuri[0].encode('utf-8')) + 1
	for c in canale:
		if not I.fluxBun(c.get('adresa')):
			continue
		atribute = []
		for k, camp in (('tvg-id', 'tvg_id'), ('group-title', 'grupa'), ('tvg-logo', 'logo')):
			v = str(c.get(camp) or '').replace('\n', '').replace('\r', '').replace('"', '')
			if v:
				atribute.append('%s="%s"' % (k, v))
		noi = ['#EXTINF:-1 %s,%s' % (' '.join(atribute), I.numeCurat(c.get('nume'), I.gazdaAdresei(c['adresa'])))]
		if c.get('antete'):
			noi.append('#EXTHTTP:' + json.dumps(c['antete'], ensure_ascii=False))
		noi.append(c['adresa'])
		octeti += sum(len(r.encode('utf-8')) + 1 for r in noi)
		if octeti > MAX_FISIER:
			raise _Limita()
		randuri.extend(noi)
	return '\n'.join(randuri) + '\n'


def _verificaText(text):
	if len(text) > MAX_FISIER or len(text.encode('utf-8', 'replace')) > MAX_FISIER:
		raise _Limita()
	if sum(1 for _ in islice(re.finditer(r'\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]', text), MAX_RANDURI)) >= MAX_RANDURI:
		raise _Limita()


def _refuzuriM3U(text):
	from Components import HdsIptvClient as C
	if re.search(r'(?im)^[^\S\r\n]*#KODIPROP:.*(?:license|drm)', text):
		yield 1, T_DRM
		return
	for nr, rand in enumerate(text.splitlines(), 1):
		rand = rand.strip().lstrip('\ufeff')
		if rand.startswith('#SERVICE '):
			parti = rand[9:].split(':', 11)
			if len(parti) > 10 and parti[1] != '64' and (parti[10] or parti[0] in ('4097', '5001', '5002')) and not C.citesteBuchet(rand)[0]:
				yield nr, T_PROTOCOL
		elif rand and not rand.startswith('#') and not I.fluxBun(rand):
			yield nr, T_PROTOCOL


def _canaleM3U(text, transfer=False):
	import io
	from Components import HdsIptvClient as C
	if not transfer:
		_verificaText(text)
	if text.lstrip().startswith(('#NAME ', '#SERVICE ')):
		canale, _, _ = C.citesteBuchet(text)
		return canale, {}
	info = {}
	text = '\n'.join(r if r.startswith('#') else _adresaImport(r) for r in text.splitlines())
	canale = list(islice(C._m3u(io.BytesIO(text.encode('utf-8')), info), I.MAX_CANALE + I.MAX_FILME_SURSA + 1))
	if len(canale) > I.MAX_CANALE + I.MAX_FILME_SURSA:
		raise _Limita()
	return canale, info


def _randuriJson(text, date):
	"""Parcurgere liniara pentru pozitiile obiectelor, fara copierea valorilor."""
	linii = [m.start() for m in re.finditer('\n', text)]
	rez, dec = {}, json.JSONDecoder()
	def spatii(pos):
		while pos < len(text) and text[pos].isspace():
			pos += 1
		return pos
	def trece(d, pos, nivel=0):
		if nivel > 32:
			raise ValueError()
		pos = spatii(pos)
		rez[id(d)] = bisect_right(linii, pos) + 1
		if isinstance(d, dict):
			pos += 1
			for v in d.values():
				pos = spatii(pos)
				if text[pos] == ',':
					pos = spatii(pos + 1)
				_, pos = dec.raw_decode(text, pos)
				pos = trece(v, spatii(pos) + 1, nivel + 1)
			return spatii(pos) + 1
		if isinstance(d, list):
			pos += 1
			for v in d:
				pos = spatii(pos)
				if text[pos] == ',':
					pos += 1
				pos = trece(v, pos, nivel + 1)
			return spatii(pos) + 1
		return dec.raw_decode(text, pos)[1]
	trece(date, 0)
	return rez


class _Limita(ValueError):
	pass


def _verificaJson(text):
	"""Limite inainte de json.loads, inclusiv pentru obiecte fara surse."""
	adancime = elemente = 0
	sir = escape = atom = False
	for c in text:
		if sir:
			if escape:
				escape = False
			elif c == '\\':
				escape = True
			elif c == '"':
				sir = False
			continue
		if c in '{["' or (c not in ' \t\r\n,:}]' and not atom):
			elemente += 1
			if elemente > MAX_RANDURI + 1:
				raise _Limita()
		if c == '"':
			sir = True
		elif c in '{[':
			adancime += 1
			if adancime > 32:
				raise _Limita()
		elif c in '}]':
			adancime -= 1
		atom = c not in ' \t\r\n,:{}[]"'


def citeste(text, nume=''):
	try:
		return _citeste(text, nume)
	except _Limita:
		return dict(surse=[], rele=[], incomplete=[], neacceptate=[], eroare=T_DETERIORATA if _semnContainer(text, nume) else T_MARE)


def _semnContainer(text, nume=''):
	"""Reserved native fields must never reach the foreign playlist reader."""
	b = text.encode('utf-8', errors='replace') if isinstance(text, str) else text
	return str(nume).lower().endswith('.hdsiptv') or (isinstance(b, bytes) and (
		b'HDSIPTV' in b or re.search(rb'"(?:hdsiptv|container|versiune|registru|liste|sha256|octeti|parti)"\s*:|(?m:^[1-9][0-9]{0,7} [0-9a-f]{64}\r?$)', b) is not None))


def _citeste(text, nume=''):
	"""Sursele si datele incomplete sunt private; rezumatul are numai numere."""
	rez = dict(surse=[], rele=[], incomplete=[], neacceptate=[])
	if isinstance(text, bytes):
		if text.startswith(MAGIC_EXACT):
			return _citesteExact(io.BytesIO(text), text)
		if _semnContainer(text, nume) and not text.lstrip(b'\xef\xbb\xbf \r\n\t').startswith(b'{'):
			return dict(rez, eroare=T_DETERIORATA)
		if len(text) > MAX_FISIER:
			return dict(rez, eroare=T_DETERIORATA if _semnContainer(text, nume) else T_MARE)
		try:
			text = text.decode('utf-8-sig')
		except UnicodeError:
			return dict(rez, eroare=T_DETERIORATA if _semnContainer(text, nume) else T_CITIRE)
	if not isinstance(text, str):
		return dict(rez, eroare=T_CITIRE)
	_verificaText(text)
	if re.search(r'"hdsiptv"\s*:', text):
		try:
			_verificaJson(text)
			envelope = json.loads(text)
			if isinstance(envelope, dict) and 'hdsiptv' in envelope:
				if type(envelope['hdsiptv']) is not int or envelope['hdsiptv'] != 3 or not isinstance(envelope.get('container'), str):
					raise ValueError()
				b = base64.b64decode(envelope['container'], validate=True)
				return _citesteExact(io.BytesIO(b), b)
		except (ValueError, TypeError, RecursionError):
			return dict(rez, eroare=T_DETERIORATA)
	if _semnContainer(text, nume):
		return dict(rez, eroare=T_DETERIORATA)
	text = text.lstrip('\ufeff')
	if sum(1 for _ in islice(re.finditer(r'\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]', text), MAX_RANDURI)) >= MAX_RANDURI:
		raise _Limita()
	for tipar in (_LABEL, _MAC, _URL):
		if sum(1 for _ in islice(tipar.finditer(text), 2 * MAX_RANDURI + 1)) > 2 * MAX_RANDURI:
			raise _Limita()
	brute, consumate, randuri_json, conturi_json = text.splitlines(), set(), {}, []

	def nu(nr, motiv):
		limita()
		rez['neacceptate'].append(dict(rand=nr, motiv=motiv))

	def lipsa(nr, portal='', mac=''):
		limita()
		rez['rele'].append(nr)
		rez['incomplete'].append(dict(rand=nr, portal=portal, mac=mac))
		conturi_json.append(dict(rand=nr, portal=portal, mac=mac, complet=False))

	def pune(s):
		if s:
			limita()
			rez['surse'].append(s)

	def limita():
		if len(rez['surse']) + len(rez['incomplete']) + len(rez['neacceptate']) >= MAX_RANDURI:
			raise _Limita()

	def jsonDate(d, nr=1, nivel=0):
		nr = randuri_json.get(id(d), nr)
		if nivel > 32:
			raise ValueError()
		if isinstance(d, list):
			if all(isinstance(v, str) for v in d):
				mic = citeste('\n'.join(d))
				if mic.get('eroare'):
					raise _Limita()
				harta = [randuri_json.get(id(v), nr) for v in d for _ in range(1 + len(re.findall(r'\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]', v)))]
				for s in mic['surse']:
					pune(s)
				for x in mic.get('incomplete', []):
					lipsa(harta[x['rand']-1], x['portal'], x['mac'])
				for x in mic.get('neacceptate', []):
					nu(harta[x['rand']-1], x['motiv'])
				return
			for v in d:
				jsonDate(v, nr, nivel + 1)
			return
		if not isinstance(d, dict):
			return
		a = {str(k).lower(): v for k, v in d.items()}
		den = a.get('nume', a.get('name', a.get('title', '')))
		url = next((a[k] for k in ('portal', 'server', 'host', 'adresa', 'url', 'stream_url', 'stream', 'link', 'playlist_url') if isinstance(a.get(k), str)), '')
		if any(a.get(k) for k in ('drm', 'drm_scheme', 'license_url', 'license_key')):
			nu(nr, T_DRM)
			return
		if a.get('fel') == 'demo':
			pune(_curata(a))
			return
		if a.get('fel') == 'm3u' and 'continut' in a:
			if isinstance(a['continut'], str):
				_verificaText(a['continut'])
				refuzuri = list(_refuzuriM3U(a['continut']))
				for _, motiv in refuzuri:
					nu(nr, motiv)
				if any(motiv == T_DRM for _, motiv in refuzuri):
					return
			canale, info = _canaleM3U(a['continut']) if isinstance(a['continut'], str) else ([], {})
			if canale:
				pune(_curata(dict(a, continut=_m3uCanale(canale, info.get('epg_url', '')))))
			elif not isinstance(a['continut'], str) or not refuzuri:
				nu(nr, T_PROTOCOL)
			return
		if a.get('fel') in ('m3u', 'xtream'):
			if a['fel'] == 'm3u':
				s = _curata(dict(a, adresa=a.get('adresa', url), nume=den))
			else:
				s = _curata(dict(a, server=url, utilizator=a.get('utilizator', a.get('username', a.get('user', ''))),
					parola=a.get('parola', a.get('password', a.get('pass', ''))), nume=den))
			pune(s) if s else nu(nr, T_PROTOCOL)
			return
		# Un tip nativ recunoscut are prioritate fata de metadatele MAC.
		user = a.get('utilizator', a.get('username', a.get('user', '')))
		parola = a.get('parola', a.get('password', a.get('pass', '')))
		if a.get('fel') != 'stalker' and (user or parola):
			s = _curata(dict(a, fel='xtream', server=url, utilizator=user, parola=parola, nume=den))
			pune(s) if s else nu(nr, T_PROTOCOL)
			return
		if a.get('fel') != 'stalker' and url:
			tip, v = _adresa(url, den)
			if tip == 'sursa' and v:
				pune(_curata(dict(v, **{k:a[k] for k in ANTETE if k in a})))
				return
		macuri = a.get('macs', a.get('mac', []))
		if not isinstance(macuri, list):
			macuri = [macuri]
		if a.get('fel', 'stalker') == 'stalker' and (macuri or 'portal' in a or a.get('fel') == 'stalker'):
			for mac in macuri or ['']:
				s = _curata(dict(a, fel='stalker', portal=url, mac=mac, nume=den))
				if s:
					pune(s)
					conturi_json.append(dict(rand=nr, portal=s['portal'], mac=s['mac'], complet=True))
				else:
					lipsa(nr, url if I.desparteServer(url) else '', I.macCurat(mac) or '')
			return
		user = a.get('utilizator', a.get('username', a.get('user', '')))
		parola = a.get('parola', a.get('password', a.get('pass', '')))
		if user or parola:
			s = _curata(dict(a, fel='xtream', server=url, utilizator=user, parola=parola, nume=den))
			if s:
				pune(s)
			else:
				nu(nr, T_PROTOCOL)
			return
		if url:
			tip, v = _adresa(url, den)
			if tip == 'portal':
				if any(k in a for k in ('stream_url', 'stream')):
					pune(_flux(v, den))
				else:
					lipsa(nr, v)
			elif tip == 'sursa':
				pune(_curata(dict(v, **{k:a[k] for k in ANTETE if k in a}))) if v else nu(nr, T_PROTOCOL)
			else:
				nu(nr, v)
			return
		texte = []
		for v in d.values():
			if isinstance(v, (list, dict)):
				jsonDate(v, nr, nivel + 1)
			elif isinstance(v, str) and ('://' in v or _MAC.search(v)):
				texte.append(v)
		if texte:
			jsonDate(texte, nr, nivel + 1)

	inceput = text.lstrip()
	if inceput.startswith(('[', '{')) and not inceput.lower().startswith('[playlist]'):
		try:
			_verificaJson(text)
			date = json.loads(text)
			randuri_json.update(_randuriJson(text, date))
			jsonDate(date)
			# Si obiectele JSON separate pot contine doar portalul sau doar MAC-ul.
			daca = [d for d in conturi_json if not d['complet']]
			if any(d['portal'] for d in daca) and any(d['mac'] for d in daca) or (daca and any(d['complet'] for d in conturi_json)):
				rez['rele'], rez['incomplete'] = [], []
				portal, pending = None, []
				def emite(d, mac):
					pune(_curata(dict(portal=d['portal'], mac=mac)))
					d['folosit'] = True
				for d in conturi_json:
					if d['portal']:
						if portal and not portal['folosit']:
							rez['incomplete'].append({k:portal[k] for k in ('rand', 'portal', 'mac')})
						portal = dict(d, folosit=d['complet'])
						for m in pending:
							emite(portal, m['mac'])
						pending.clear()
					elif d['mac']:
						if portal:
							emite(portal, d['mac'])
						else:
							pending.append(d)
					else:
						rez['incomplete'].append({k:d[k] for k in ('rand', 'portal', 'mac')})
				if portal and not portal['folosit']:
					rez['incomplete'].append({k:portal[k] for k in ('rand', 'portal', 'mac')})
				rez['incomplete'].extend({k:d[k] for k in ('rand', 'portal', 'mac')} for d in pending)
				rez['rele'] = sorted({d['rand'] for d in rez['incomplete']})
		except _Limita:
			raise
		except (ValueError, TypeError, RecursionError, AttributeError):
			return dict(surse=[], rele=[1], incomplete=[], neacceptate=[])
		return rez

	if re.search(r'<(?:\w+:)?(?:playlist|tv)\b', text, re.I):
		if text.count('<') > MAX_RANDURI:
			raise _Limita()
		if re.search(r'<!ENTITY|<!DOCTYPE[^>]*\[', text, re.I):
			nu(1, T_PROTOCOL)
			return rez
		try:
			root = ET.fromstring(text)
		except (ET.ParseError, ValueError):
			nu(1, T_PROTOCOL)
			return rez
		if root.tag.rsplit('}', 1)[-1] == 'tv':
			nu(1, T_EPG)
			return rez
		canale = []
		for track in root.iter():
			if track.tag.rsplit('}', 1)[-1] == 'track':
				if len(canale) >= MAX_RANDURI:
					raise _Limita()
				v = {e.tag.rsplit('}', 1)[-1]: e.text or '' for e in track}
				url = v.get('location', '').strip()
				if I.fluxBun(url):
					canale.append(dict(adresa=url, nume=v.get('title', '')))
				else:
					nu(1, T_PROTOCOL)
		if canale:
			pune(_lista(_m3uCanale(canale), nume))
		return rez

	if re.search(r'(?im)^[^\S\r\n]*\[playlist\]', text):
		fisiere, titluri = {}, {}
		for nr, rand in enumerate(brute, 1):
			m = re.match(r'(?i)\s*(File|Title)(\d+)\s*=\s*(.*)', rand)
			if m:
				(fisiere if m[1].lower() == 'file' else titluri)[m[2]] = (m[3], nr)
		canale = []
		for k, (url, nr) in fisiere.items():
			if len(canale) >= MAX_RANDURI:
				raise _Limita()
			if I.fluxBun(url):
				canale.append(dict(adresa=url, nume=titluri.get(k, ('', 0))[0]))
			else:
				nu(nr, T_PROTOCOL)
		if canale:
			pune(_lista(_m3uCanale(canale), nume))
		return rez

	if re.search(r'(?m)^[^\S\r\n]*#(?:EXTM3U|EXTINF|NAME |SERVICE )', text):
		from Components import HdsIptvClient as C
		refuzuri = list(_refuzuriM3U(text))
		for nr, motiv in refuzuri:
			nu(nr, motiv)
		if any(motiv == T_DRM for _, motiv in refuzuri):
			return rez
		e_buchet = bool(re.search(r'(?m)^#(?:NAME |SERVICE )', text))
		if e_buchet:
			canale, _, _ = C.citesteBuchet(text)
			info = {}
		else:
			canale, info = _canaleM3U(text)
		if canale:
			pune(_lista(_m3uCanale(canale, info.get('epg_url', '')), nume))
			for nr, rand in enumerate(brute, 1):
				if rand.strip() and not rand.lstrip().startswith('#'):
					consumate.add(nr)
				elif e_buchet or rand.lstrip().upper().startswith(('#EXTM3U', '#EXTINF', '#EXTHTTP', '#EXTVLCOPT', '#EXTGRP')):
					consumate.add(nr)
		elif not any(_MAC.search(r) for r in brute):
			if not rez['neacceptate']:
				nu(1, T_PROTOCOL)
			return rez

	# Conturile Xtream cu etichete si blocurile simple de trei randuri.
	for start, brut in enumerate(brute):
		if start + 1 in consumate:
			continue
		m = list(_LABEL.finditer(brut))
		valori, folosite = {}, []
		if m and any(x[1].lower() in ('server', 'host', 'url') for x in m):
			primul = start
			while primul > 0 and primul > start - 12 and primul not in consumate:
				et = list(_LABEL.finditer(brute[primul-1]))
				if not et or any(x[1].lower() in ('server', 'host', 'portal', 'url', 'mac') for x in et):
					break
				primul -= 1
			for j in range(primul, min(len(brute), start + 12)):
				et = list(_LABEL.finditer(brute[j]))
				if j > start and any(x[1].lower() in ('server', 'host', 'portal', 'url') for x in et):
					break
				for k, x in enumerate(et):
					cheie = {'host':'server', 'url':'server', 'username':'utilizator', 'user':'utilizator', 'nume utilizator':'utilizator', 'password':'parola', 'pass':'parola', 'parolă':'parola', 'name':'nume'}.get(x[1].lower(), x[1].lower())
					valori[cheie] = _valoareEticheta(brute[j][x.end():et[k+1].start() if k+1 < len(et) else len(brute[j])], cheie)
				if et:
					folosite.append(j + 1)
			if valori.get('server') and valori.get('utilizator') and valori.get('parola'):
				s = _curata(dict(valori, fel='xtream'))
				if s:
					pune(s)
					consumate.update(folosite)
		elif start + 2 < len(brute) and _URL.fullmatch(brut.strip()):
			u, p = (x.strip() for x in brute[start+1:start+3])
			if u and p and not _URL.search(u) and not _URL.search(p) and not _MAC.search(u) and not _MAC.search(p) and not _LABEL.search(u + ' ' + p) and ' ' not in u:
				tip, server = _adresa(brut.strip())
				if tip == 'portal' or (tip == 'sursa' and I.desparteServer(brut.strip()) and '?' not in brut):
					pune(_curata(dict(fel='xtream', server=brut.strip(), utilizator=u, parola=p)))
					consumate.update((start+1, start+2, start+3))

	# Urmatorul element de cont poate fi pe alt rand, dincolo de etichete.
	urmator, semn = {}, ''
	for nr in range(len(brute), 0, -1):
		urmator[nr] = semn
		if nr in consumate:
			continue
		rand = brute[nr-1]
		if _MAC.search(rand):
			semn = 'mac'
		elif _URL.search(rand):
			semn = 'url'
	portal, pendinte, nume_bloc = None, [], ''
	def inchide():
		if portal and not portal['folosit']:
			lipsa(portal['rand'], portal['url'])

	for nr, brut in enumerate(brute, 1):
		if nr in consumate:
			continue
		rand = brut
		if not rand.strip():
			nume_bloc = ''
			if portal:
				portal['separat'] = True
		et = list(_LABEL.finditer(rand))
		for j, m in enumerate(et):
			if m[1].lower() in ('name', 'nume'):
				nume_bloc = I.numeCurat(_valoareEticheta(rand[m.end():et[j+1].start() if j+1 < len(et) else len(rand)], 'nume'))
				if portal and portal['folosit'] and not portal.get('separat'):
					for s in rez['surse'][portal['inceput']:]:
						if _fel(s) == 'stalker' and s.get('portal') == portal['url']:
							s['nume'] = nume_bloc
		macuri_brute = list(islice(_MAC.finditer(rand), 2 * MAX_RANDURI + 1))
		urluri_brute = list(islice(_adrese(rand), 2 * MAX_RANDURI + 1))
		if max(len(macuri_brute), len(urluri_brute)) > 2 * MAX_RANDURI:
			raise _Limita()
		def inIntervale(pos, inceputuri, intervale):
			i = bisect_right(inceputuri, pos) - 1
			return i >= 0 and pos < intervale[i].end()
		mac_inceput = [m.start() for m in macuri_brute]
		urluri = [u for u in urluri_brute if not inIntervale(u.start(), mac_inceput, macuri_brute)]
		url_inceput = [u.start() for u in urluri]
		macuri = [m for m in macuri_brute if not inIntervale(m.start(), url_inceput, urluri)]
		if macuri and urluri and macuri[0].start() < urluri[0].start():
			inchide()
			portal = None
		for _, tip, m in sorted([(u.start(), 'url', u) for u in urluri] + [(m.start(), 'mac', m) for m in macuri]):
			if tip == 'mac':
				mac = I.macCurat(m[0])
				if portal:
					pune(_curata(dict(portal=portal['url'], mac=mac, nume=nume_bloc or portal['nume'])))
					portal['folosit'] = True
				else:
					pendinte.append((nr, mac))
				continue
			den = nume_bloc
			if not macuri and len(urluri) == 1:
				den = den or I.numeCurat((rand[:m.start()] + ' ' + rand[m.end():]).strip(' \t|;,\'"-#'))
			url = _urlDinProza(rand, m)
			categorie, v = _adresa(url, den)
			if (macuri or pendinte or urmator[nr] == 'mac' or any(x[1].lower() == 'portal' for x in et)) and I.desparteServer(url) and '?' not in url:
				categorie, v = 'portal', url
			if categorie == 'portal' and nume.lower().endswith('.strm'):
				categorie, v = 'sursa', _flux(v, den)
			if categorie == 'portal':
				inchide()
				portal = dict(url=v, rand=nr, folosit=False, nume=den, inceput=len(rez['surse']))
				for rn, mac in pendinte:
					pune(_curata(dict(portal=v, mac=mac, nume=nume_bloc)))
					portal['folosit'] = True
				pendinte.clear()
			elif categorie == 'sursa':
				pune(v)
			else:
				nu(nr, v)
		if not urluri and not macuri and any(m[1].lower() == 'mac' for m in et) and portal and not portal['folosit']:
			lipsa(nr, portal['url'])
			portal['folosit'] = True
	inchide()
	for nr, mac in pendinte:
		lipsa(nr, mac=mac)
	rez['rele'] = sorted(set(rez['rele']))
	if nume.lower().endswith(('.strm', '.pls', '.xspf', '.m3u', '.m3u8', '.tv')) and text.strip() and not any(rez[k] for k in ('surse', 'rele', 'neacceptate')):
		nu(1, T_PROTOCOL)
	return rez


def completeaza(p, text):
	"""Corecturi numai pentru datele nepereche, fara atingerea surselor gasite."""
	try:
		if isinstance(text, str):
			_verificaText(text)
			_verificaJson(text)
		date = json.loads(text) if isinstance(text, str) else text
		if not isinstance(date, list) or len(date) > MAX_RANDURI:
			return p
	except (ValueError, TypeError, RecursionError):
		return p
	corecturi = {d.get('rand'): d for d in date if isinstance(d, dict) and isinstance(d.get('rand'), int)}
	pe_indice = {d.get('indice'): d for d in date if isinstance(d, dict) and isinstance(d.get('indice'), int)}
	numere = Counter(d['rand'] for d in p.get('incomplete', []))
	rez = dict(p, surse=list(p['surse']), rele=[], incomplete=[])
	for i, d in enumerate(p.get('incomplete', [])):
		indice = d.get('indice', i)
		corectie = pe_indice.get(indice, corecturi.get(d['rand'], {}) if numere[d['rand']] == 1 and not pe_indice else {})
		s = _curata(dict(d, **{k:v for k, v in corectie.items() if k in ('portal', 'mac')}))
		if s:
			rez['surse'].append(s)
		else:
			rez['incomplete'].append(dict(d, indice=indice))
			rez['rele'].append(d['rand'])
	rez['rele'].extend(n for n in p['rele'] if n not in numere)
	return rez


def citesteFisier(cale):
	try:
		fd = os.open(cale, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
		with os.fdopen(fd, 'rb') as f:
			if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				return dict(surse=[], rele=[], eroare=T_CITIRE)
			if f.read(len(MAGIC_EXACT)) == MAGIC_EXACT:
				f.seek(0)
				return _citesteExact(f, cale)
			f.seek(0)
			if f.read(len(MAGIC_ARHIVA)) == MAGIC_ARHIVA:
				f.seek(0)
				p = _citesteArhiva(f, cale)
				return dict(p, eroare=T_DETERIORATA) if p.get('eroare') else p
			f.seek(0)
			if f.read(len(MAGIC_TRANSFER)) == MAGIC_TRANSFER:
				f.seek(0)
				p = _citesteTransfer(f, cale)
				return dict(p, eroare=T_DETERIORATA) if p.get('eroare') else p
			f.seek(0)
			return citeste(f.read(MAX_FISIER + 1), os.path.basename(cale))
	except (OSError, ValueError):
		return dict(surse=[], rele=[], eroare=T_CITIRE)


def _caleImport(digest, sursa=None):
	setari = _setariIdentitate(sursa or {})
	sufix = '-' + hashlib.sha256(json.dumps(setari, ensure_ascii=False).encode('utf-8')).hexdigest() if setari != _setariIdentitate({}) else ''
	return os.path.join(I.dosarListe(), 'import-' + digest + sufix + '.m3u')


def _caleLista(text, sursa=None):
	return _caleImport(hashlib.sha256(text.encode('utf-8')).hexdigest(), sursa)


def _scrieNou(cale, date):
	"""Publica numai fisierul complet, fara inlocuire la o cursa externa."""
	fd, temporar = tempfile.mkstemp(prefix='.hds-transfer-', dir=os.path.dirname(cale))
	try:
		with os.fdopen(fd, 'wb') as f:
			if isinstance(date, (_ListaTransfer, _FisierExact)):
				date.copiaza(f)
			else:
				f.write(date)
			f.flush()
			os.fsync(f.fileno())
		try:
			os.link(temporar, cale)
		except FileExistsError:
			if isinstance(date, (_ListaTransfer, _FisierExact)):
				with _deschideLocal(cale) as f:
					identic = os.fstat(f.fileno()).st_size == date.octeti and _hashFlux(f, date.octeti) == date.digest
			else:
				identic = _citesteLocal(cale) == date
			if not identic:
				raise OSError('Local import file conflict') from None
			return False
		return os.stat(temporar)
	finally:
		os.unlink(temporar)


@contextmanager
def _deschideLocal(cale):
	"""Nu urmeaza legaturi si nu ramane blocat pe FIFO/dispozitive."""
	st = os.lstat(cale)
	if not stat.S_ISREG(st.st_mode):
		raise OSError('Not a regular playlist')
	fd = os.open(cale, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
	with os.fdopen(fd, 'rb') as f:
		st2 = os.fstat(f.fileno())
		if not stat.S_ISREG(st2.st_mode) or (st.st_dev, st.st_ino) != (st2.st_dev, st2.st_ino):
			raise OSError('Playlist changed')
		if st2.st_size > MAX_PLAYLIST:
			raise OSError('Playlist too large')
		yield f
		st3 = os.fstat(f.fileno())
		if (st2.st_size, st2.st_mtime_ns) != (st3.st_size, st3.st_mtime_ns):
			raise OSError('Playlist changed')


def _citesteLocal(cale):
	with _deschideLocal(cale) as f:
		date = f.read(MAX_FISIER + 1)
		if len(date) > MAX_FISIER:
			raise OSError('Playlist too large')
		return date


def _hashFlux(f, n, out=None):
	"""Hash cu tampon fix, fara decodare si fara lista de canale."""
	h = hashlib.sha256()
	while n:
		b = f.read(min(n, 65536))
		if not b:
			raise OSError('Truncated playlist')
		h.update(b)
		if out is not None:
			out.write(b)
		n -= len(b)
	return h.hexdigest()


def _cheieCanale(canale, epg=''):
	from Components import HdsIptvClient as C
	# Ordinea, repetarile, ghidul si metadatele sunt continut primit de om.
	h = hashlib.sha256(json.dumps(epg, ensure_ascii=False).encode('utf-8'))
	for c in canale:
		d = dict(adresa=c['adresa'], antete=C.anteteCurate(c.get('antete')),
			**{k:c.get(k) or '' for k in ('nume', 'grupa', 'tvg_id', 'logo')})
		h.update(b'\n')
		h.update(json.dumps(d, ensure_ascii=False, sort_keys=True).encode('utf-8'))
	return 'content2:' + h.hexdigest()


def _verificaListaFlux(f, n, refuzuri=None):
	"""Transferurile native mari pastreaza octetii, fara normalizare in RAM."""
	from Components import HdsIptvClient as C
	from Components.HdsIptvCitire import randuri
	start = f.tell()
	digest = _hashFlux(f, n)
	f.seek(start)
	mic = n <= MAX_FISIER
	if mic:
		text = C._text(f.read(n))
		try:
			_verificaText(text)
		except _Limita:
			mic = False
	if mic:
		if refuzuri is not None:
			refuzuri.extend(_refuzuriM3U(text))
		canale, info = _canaleM3U(text)
		if not canale:
			raise ValueError('Empty playlist')
		return digest, _cheieCanale(canale, info.get('epg_url', ''))
	class Bucata:
		def __init__(self): self.ramas = n
		def read(self, size):
			b = f.read(min(size, self.ramas))
			self.ramas -= len(b)
			return b
	f.seek(start)
	inceput = f.read(min(n, 256)).decode('utf-8-sig', 'replace').lstrip()
	f.seek(start)
	if inceput.startswith(('#NAME ', '#SERVICE ')):
		bun = False
		for b in randuri(Bucata()):
			if b.lstrip().startswith(b'#SERVICE ') and C.citesteBuchet(C._text(b))[0]:
				bun = True
				break
	else:
		bun = next(C._m3u(Bucata(), {}), None) is not None
	if not bun:
		raise ValueError('Empty playlist')
	if refuzuri is not None:
		f.seek(start)
		for nr, b in enumerate(randuri(Bucata()), 1):
			for _, motiv in _refuzuriM3U(C._text(b)):
				if len(refuzuri) >= MAX_RANDURI:
					raise _Limita()
				refuzuri.append((nr, motiv))
	f.seek(start + n)
	return digest, 'raw:' + digest


def _setariIdentitate(s):
	# Digest incremental: previzualizarea nu pastreaza toate valorile in tupluri.
	rez = tuple((k, s.get(k) or '') for k in ANTETE)
	rez += (('player', I.playerSursa(s)), ('piconuri', s.get('piconuri') is True))
	for camp in ('ascunse', 'ordine'):
		h = hashlib.sha256()
		valori = s.get(camp)
		for v in valori if isinstance(valori, (list, _OptiuniTransfer)) else ():
			if isinstance(v, str) and I.textBun(v):
				b = v.encode('utf-8')
				h.update(len(b).to_bytes(4, 'big'))
				h.update(b)
		rez += ((camp, h.hexdigest()),)
	return rez


def _identitate(s):
	"""Identitatea transferului, comuna citirii, dublurilor si restaurarii.

	Nu este ID-ul stabil al Favoritelor: acela supravietuieste editarilor.
	"""
	fel = _fel(s)
	antete = _setariIdentitate(s)
	if fel == 'stalker':
		return fel, I.identitatePortal(s.get('portal')), I.macCurat(s.get('mac')), antete
	if fel == 'xtream':
		return fel, I.identitatePortal(s.get('server')), s.get('utilizator'), s.get('parola'), antete, tuple(s.get(k) or '' for k in CAMPURI_XTREAM)
	if fel == 'm3u':
		if isinstance(s.get('_local'), _ListaTransfer):
			return fel, 'local', s['_local'].cheie, antete
		if os.path.isabs(s.get('adresa', '')):
			try:
				with _deschideLocal(s['adresa']) as f:
					_, cheie = _verificaListaFlux(f, os.fstat(f.fileno()).st_size)
					return fel, 'local', cheie, antete
			except (OSError, ValueError):
				pass
		if 'continut' in s:
			canale, info = _canaleM3U(s['continut'], transfer=True)
			cheie = _cheieCanale(canale, info.get('epg_url', ''))
			return fel, 'local', cheie, antete
		return fel, 'online', s.get('adresa') or '', antete
	return fel, antete


def _surse():
	"""Nu inlocuieste un depozit deteriorat cu lista aparent goala."""
	try:
		with open(I._caleSurse(), encoding='utf-8') as f:
			date = json.load(f)
	except FileNotFoundError:
		return []
	except (ValueError, RecursionError):
		raise OSError('Invalid source store') from None
	surse = date.get('surse') if isinstance(date, dict) else None
	if not isinstance(surse, list) or any(not isinstance(s, dict) or s.get('fel') not in I.FELURI or not I._ID_SURSA.fullmatch(str(s.get('id', ''))) for s in surse):
		raise OSError('Invalid source store')
	return surse


def _pregateste(p, surse, chei=None):
	feluri = {_fel(s) for s in p['surse']}
	if feluri.intersection(('m3u', 'xtream')):
		feluri.update(('m3u', 'xtream'))
	identitate = _identitate if chei is None else lambda s: chei[id(s)]
	vazute = {identitate(s) for s in surse if _fel(s) in feluri}
	noi, existente = [], 0
	for s in p['surse']:
		cheie = identitate(s)
		if cheie in vazute:
			existente += 1
		else:
			vazute.add(cheie)
			noi.append(s)
	libere = max(0, I.MAX_SURSE - len(surse))
	rez = dict(gasite=len(p['surse']), existente=existente, noi=min(len(noi), libere), rele=list(p['rele']),
		peste=max(0, len(noi) - libere), total=len(surse), maxim=I.MAX_SURSE, neacceptate=list(p.get('neacceptate', [])))
	if p.get('eroare'):
		rez['eroare'] = p['eroare']
	return rez, noi[:libere]


def _stareSurse():
	try:
		st = os.stat(I._caleSurse())
		return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns
	except FileNotFoundError:
		return None


@contextmanager
def _instantaneu(p):
	"""Citirile de playlist sunt libere; validarea finala este scurta si atomica."""
	feluri = {_fel(s) for s in p['surse']}
	if feluri.intersection(('m3u', 'xtream')):
		feluri.update(('m3u', 'xtream'))
	while True:
		with I._LACAT:
			surse = _surse()
			stare = _stareSurse()
		chei = {id(s): _identitate(s) for s in surse if _fel(s) in feluri}
		chei.update((id(s), _identitate(s)) for s in p['surse'])
		with I._LACAT:
			if _stareSurse() != stare:
				continue
			yield surse, chei
			return


def rezumat(p):
	try:
		if '_exact' in p:
			with I._LACAT:
				return _rezumatExact(p, _surse())[0]
		with _instantaneu(p) as (surse, chei):
			return _pregateste(p, surse, chei)[0]
	except OSError:
		if '_exact' in p:
			return dict(gasite=len(p['surse']), existente=0, noi=0, rele=[], peste=0, total=0, maxim=I.MAX_SURSE, neacceptate=[], eroare=T_SURSE_CITIRE)
		return dict(_pregateste(p, [])[0], noi=0, eroare=T_SURSE_CITIRE)


def adauga(p):
	"""Copii in afara lacatului surselor, apoi recalcul si salvare atomica."""
	if '_exact' in p:
		return _adaugaExact(p)
	with _IMPORT_LACAT:
		pregatite, create = {}, []
		try:
			while True:
				with _instantaneu(p) as (surse, chei):
					rez, noi = _pregateste(p, surse, chei)
					if p.get('eroare'):
						return dict(rez, adaugate=0)
					lipsa = [s for s in noi if id(s) not in pregatite and ('continut' in s or isinstance(s.get('_local'), _ListaTransfer)
						or any(isinstance(s.get(camp), _OptiuniTransfer) for camp in ('ascunse', 'ordine')))]
					if not lipsa:
						ocupate = {s['id'] for s in surse}
						identitati = I._identitatiPlaylist() if noi else {}
						for date in noi:
							s = dict(date, fel=_fel(date), neconectata=True)
							s.pop('_local', None)
							s.pop('continut', None)
							s.update(pregatite.get(id(date), {}))
							fel = s['fel']
							if fel == 'stalker':
								sid = identitati.get(I._amprentaStalker(s['portal'], s['mac'])) or I.idSursa(fel, s['portal'], s['mac'])
								baza = dict(id=sid, nume=I.gazdaAdresei(s['portal']))
							elif fel == 'xtream':
								baza = I.sursaNouaXtream(s['server'], s['utilizator'], s['parola'], s['nume'])
							elif fel == 'm3u':
								sid = identitati.get(I._amprentaPlaylist(s['adresa'])) or I.idSursa(fel, s['adresa'])
								baza = dict(id=sid, nume='' if 'continut' in date else I.gazdaAdresei(s['adresa']))
							else:
								baza = I.sursaDemo()
							sid, n = baza['id'], 0
							while sid in ocupate:
								n += 1
								sid = I.idSursa(fel, repr(chei[id(date)]), str(n))
							ocupate.add(sid)
							s = dict(baza, **s)
							s['id'], s['nume'] = sid, s['nume'] or baza['nume']
							surse.append(s)
						if noi:
							I.scrieSurse(surse)
						return dict(rez, adaugate=len(noi))
				for date in lipsa:
					optiuni = {camp: list(date[camp]) for camp in ('ascunse', 'ordine') if isinstance(date.get(camp), _OptiuniTransfer)}
					local = date.get('_local')
					if isinstance(local, _ListaTransfer):
						adresa = _caleImport(local.digest, date)
						cheie = local.cheie
						continut = local
					elif 'continut' in date:
						adresa = _caleLista(date['continut'], date)
						cheie = _identitate(date)[2]
						continut = date['continut'].encode('utf-8')
					else:
						pregatite[id(date)] = optiuni
						continue
					os.makedirs(I.dosarListe(), mode=0o700, exist_ok=True)
					scris = _scrieNou(adresa, continut)
					if scris:
						create.append((adresa, scris))
					pregatite[id(date)] = dict(optiuni, adresa=adresa, import_cheie=cheie)
		finally:
			if create:
				with I._LACAT:
					# O sursa adaugata intre timp poate folosi aceeasi copie.
					try:
						folosite = {s.get('adresa') for s in _surse()}
					except OSError:
						# La un depozit necitibil nu stergem copii posibil folosite.
						folosite = {cale for cale, _ in create}
					for cale, original in create:
						if cale in folosite:
							continue
						try:
							acum = os.lstat(cale)
							if (acum.st_dev, acum.st_ino) == (original.st_dev, original.st_ino):
								os.unlink(cale)
						except OSError:
							pass


def textRezumat(rez, traduce=lambda x: x):
	if rez.get('eroare'):
		return traduce(rez['eroare'])
	text = traduce(T_REZUMAT) % (rez['gasite'], rez['existente'], rez['noi'], len(rez['rele']))
	if rez['rele']:
		text += '\n' + traduce(T_RANDURI) % ', '.join(map(str, rez['rele']))
	for d in rez.get('neacceptate', []):
		text += '\n' + traduce(T_NEACCEPTAT) % (d['rand'], traduce(d['motiv']))
	if rez['peste']:
		text += '\n' + traduce(T_LIMITA) % (rez['total'], rez['maxim'], rez['peste'])
	if 'adaugate' in rez:
		text += '\n' + traduce(T_ADAUGATE) % rez['adaugate']
	return text


# Native v3 keeps source values and playlist bytes outside the foreign reader.
MAGIC_EXACT = b'HDSIPTV3\n'
MAX_REGISTRU = MAX_ARHIVA - 2 * MAX_FISIER


def _registruBrut():
	try:
		with open(I._caleSurse(), 'rb') as f:
			if os.fstat(f.fileno()).st_size > MAX_REGISTRU:
				raise OSError(T_MARE)
			b = f.read()
	except FileNotFoundError:
		b = b'{"surse": []}'
	_dateRegistru(b)
	return b


def _dateRegistru(b):
	if len(b) > MAX_REGISTRU:
		raise OSError(T_MARE)
	try:
		d = json.loads(b)
		surse = d['surse']
		if not isinstance(surse, list) or len(surse) > I.MAX_SURSE:
			raise ValueError()
		ids = set()
		for s in surse:
			if not isinstance(s, dict) or s.get('fel') not in I.FELURI or not I._ID_SURSA.fullmatch(str(s.get('id', ''))) or s['id'] in ids:
				raise ValueError()
			ids.add(s['id'])
		return d
	except (ValueError, TypeError, KeyError, RecursionError):
		raise OSError(T_SURSE_CITIRE) from None


def _caiExacte(surse):
	cai = list(dict.fromkeys(s['adresa'] for s in surse if s.get('fel') == 'm3u' and isinstance(s.get('adresa'), str) and os.path.isabs(s['adresa'])))
	if any(not cale.lower().endswith(I.EXTENSII_LISTA) for cale in cai):
		raise OSError(T_LOCAL)
	return cai


def _caleExacta(cale):
	# Only the channel cache of a validated source ID is an allowed JSON file.
	name = os.path.basename(cale) if isinstance(cale, str) else ''
	if name.startswith('canale-') and name.endswith('.json') and I._ID_SURSA.fullmatch(name[7:-5]) and cale == I._caleCanale(name[7:-5]):
		return os.path.realpath(os.path.dirname(cale))
	# A backup cannot write arbitrary system paths or traverse symbolic links.
	if not isinstance(cale, str) or not os.path.isabs(cale) or '..' in cale.replace('\\', '/').split('/') or not cale.lower().endswith(I.EXTENSII_LISTA):
		raise OSError(T_LOCAL)
	if os.name != 'nt' and I.adresaListaBuna(cale) is None:
		raise OSError(T_LOCAL)
	roots = (I.DIRECTOR, I.dosarListe()) if os.name == 'nt' else tuple(I.RADACINI_STICK) + I.locuriListeLocale()
	parent = os.path.realpath(os.path.dirname(cale))
	if not any(os.path.splitdrive(parent)[0] == os.path.splitdrive(os.path.realpath(root))[0] and os.path.commonpath((parent, os.path.realpath(root))) == os.path.realpath(root) for root in roots):
		raise OSError(T_LOCAL)
	return parent


def _partiExacte(f, src, n):
	while n:
		b = src.read(min(n, MAX_FISIER))
		if not b:
			raise OSError(T_CITIRE)
		f.write(('%d %s\n' % (len(b), hashlib.sha256(b).hexdigest())).encode('ascii'))
		f.write(b)
		n -= len(b)


def scrieTransfer(f):
	"""Versioned exact container, split into bounded checksummed parts."""
	# The registry writer replaces the file atomically; one descriptor is a snapshot.
	registru = _registruBrut()
	surse = _dateRegistru(registru)['surse']
	liste = []
	for cale in _caiExacte(surse):
		_caleExacta(cale)
		with _deschideLocal(cale) as src:
			n = os.fstat(src.fileno()).st_size
			liste.append(dict(cale=cale, octeti=n, sha256=_hashFlux(src, n)))
	canale = []
	for sursa in surse:
		cale = I._caleCanale(sursa['id'])
		try:
			with _deschideLocal(cale) as src:
				n = os.fstat(src.fileno()).st_size
				canale.append(dict(sursa=sursa['id'], octeti=n, sha256=_hashFlux(src, n)))
		except FileNotFoundError:
			pass
	manifest = dict(versiune=3, registru=dict(octeti=len(registru), sha256=hashlib.sha256(registru).hexdigest()), liste=liste)
	if canale:
		manifest['canale'] = canale
	meta = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
	if len(meta) > MAX_FISIER or sum(x['octeti'] for x in liste + canale) + len(registru) > MAX_ARHIVA - MAX_FISIER * 2:
		raise OSError(T_MARE)
	f.write(MAGIC_EXACT)
	f.write(('%d %s\n' % (len(meta), hashlib.sha256(meta).hexdigest())).encode('ascii'))
	f.write(meta)
	_partiExacte(f, io.BytesIO(registru), len(registru))
	for d in liste + [dict(x, cale=I._caleCanale(x['sursa'])) for x in canale]:
		with _deschideLocal(d['cale']) as src:
			if os.fstat(src.fileno()).st_size != d['octeti'] or _hashFlux(src, d['octeti']) != d['sha256']:
				raise OSError(T_LOCAL)
			src.seek(0)
			_partiExacte(f, src, d['octeti'])
			src.seek(0)
			if _hashFlux(src, d['octeti']) != d['sha256']:
				raise OSError(T_LOCAL)
	f.write(b'END\n')
	f.flush()
	try:
		os.fsync(f.fileno())
	except io.UnsupportedOperation:
		pass
	f.seek(0)


class _FisierExact:
	"""Checked bounded slices of an immutable byte string or private file."""
	def __init__(self, source, parts, n, digest):
		self.source, self.parts, self.octeti, self.digest = source, parts, n, digest

	def copiaza(self, out):
		if isinstance(self.source, bytes):
			f = io.BytesIO(self.source)
		else:
			fd = os.open(self.source, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
			f = os.fdopen(fd, 'rb')
		with f:
			if not isinstance(self.source, bytes) and not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				raise OSError(T_CITIRE)
			h = hashlib.sha256()
			for start, n, digest in self.parts:
				f.seek(start)
				part_hash = hashlib.sha256()
				left = n
				while left:
					b = f.read(min(left, 65536))
					if not b:
						raise OSError(T_CITIRE)
					part_hash.update(b)
					h.update(b)
					out.write(b)
					left -= len(b)
				if part_hash.hexdigest() != digest:
					raise OSError(T_CITIRE)
			if len(self.parts) == 1 and self.parts[0][0] == 0 and f.read(1):
				raise OSError(T_CITIRE)
			if h.hexdigest() != self.digest:
				raise OSError(T_CITIRE)


def _blocExact(f):
	line = f.readline(100)
	m = re.fullmatch(rb'([1-9][0-9]{0,7}) ([0-9a-f]{64})\n', line)
	if not m or not 0 < int(m[1]) <= MAX_FISIER:
		raise ValueError()
	n, digest = int(m[1]), m[2].decode('ascii')
	start = f.tell()
	b = f.read(n)
	if len(b) != n or hashlib.sha256(b).hexdigest() != digest:
		raise ValueError()
	return b, (start, n, digest)


def _citesteExact(f, source):
	try:
		if not isinstance(source, bytes) and os.fstat(f.fileno()).st_size > MAX_ARHIVA:
			raise ValueError()
		if f.read(len(MAGIC_EXACT)) != MAGIC_EXACT:
			raise ValueError()
		meta, _ = _blocExact(f)
		d = json.loads(meta)
		if not isinstance(d, dict) or type(d.get('versiune')) is not int or d['versiune'] != 3 or not isinstance(d.get('liste'), list) or len(d['liste']) > I.MAX_SURSE:
			raise ValueError()
		caches = d.get('canale', [])
		if not isinstance(caches, list) or len(caches) > I.MAX_SURSE:
			raise ValueError()
		files, registru, total, cache_ids = [], None, 0, set()
		for index, desc in enumerate([d['registru']] + d['liste'] + caches):
			if not isinstance(desc, dict) or type(desc.get('octeti')) is not int or not 0 <= desc['octeti'] <= (MAX_REGISTRU if index == 0 else MAX_PLAYLIST) or not re.fullmatch('[0-9a-f]{64}', str(desc.get('sha256', ''))):
				raise ValueError()
			total += desc['octeti']
			if total > MAX_ARHIVA:
				raise ValueError()
			left, parts, chunks, h = desc['octeti'], [], [], hashlib.sha256()
			while left:
				b, part = _blocExact(f)
				if len(b) != min(left, MAX_FISIER):
					raise ValueError()
				h.update(b)
				parts.append(part)
				if index == 0:
					chunks.append(b)
				left -= len(b)
			if h.hexdigest() != desc['sha256']:
				raise ValueError()
			if index == 0:
				registru = b''.join(chunks)
				surse = _dateRegistru(registru)['surse']
			else:
				if index > len(d['liste']):
					sid = desc.get('sursa')
					if not isinstance(sid, str) or sid not in {s['id'] for s in surse} or sid in cache_ids:
						raise ValueError()
					cache_ids.add(sid)
					cale = I._caleCanale(sid)
				else:
					cale = desc['cale']
				_caleExacta(cale)
				files.append((cale, _FisierExact(source, parts, desc['octeti'], desc['sha256'])))
		if f.read(5) != b'END\n' or [p for p, _ in files[:len(d['liste'])]] != _caiExacte(surse):
			raise ValueError()
		n = f.tell()
		f.seek(0)
		digest = _hashFlux(f, n)
		return dict(surse=surse, rele=[], incomplete=[], neacceptate=[], _exact=(registru, files, source, n, digest))
	except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
		return dict(surse=[], rele=[], incomplete=[], neacceptate=[], eroare=T_DETERIORATA)


def exporta():
	"""Small text envelope of the same exact binary container."""
	with tempfile.TemporaryFile('w+b') as f:
		scrieTransfer(f)
		b = f.read(MAX_FISIER + 1)
		if len(b) > (MAX_FISIER - 64) * 3 // 4:
			raise OSError(T_MARE)
		return json.dumps(dict(hdsiptv=3, container=base64.b64encode(b).decode('ascii')), separators=(',', ':')) + '\n'


def _rezumatExact(p, surse):
	vazute = {s['id']: s for s in surse}
	noi, existente = [], 0
	for s in p['surse']:
		old = vazute.get(s['id'])
		if old is not None:
			if json.dumps(old, sort_keys=True, ensure_ascii=True) != json.dumps(s, sort_keys=True, ensure_ascii=True):
				raise OSError(T_SURSE_CITIRE)
			existente += 1
		else:
			noi.append(s)
	libere = max(0, I.MAX_SURSE - len(surse))
	return dict(gasite=len(p['surse']), existente=existente, noi=min(len(noi), libere), rele=[], peste=max(0, len(noi)-libere), total=len(surse), maxim=I.MAX_SURSE, neacceptate=[]), noi[:libere]


def _scrieExact(cale, obj):
	"""Publish relative to a pinned directory; never follow destination links."""
	if os.name == 'nt':
		return _scrieNou(cale, obj)
	parent = _caleExacta(cale)
	fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
	try:
		for part in parent.strip('/').split('/'):
			if not part:
				continue
			try:
				child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
			except FileNotFoundError:
				os.mkdir(part, 0o700, dir_fd=fd)
				child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
			os.close(fd)
			fd = child
		name = '.hds-transfer-' + secrets.token_hex(16)
		tmpfd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
		try:
			with os.fdopen(tmpfd, 'wb') as out:
				obj.copiaza(out)
				out.flush()
				os.fsync(out.fileno())
			base = os.path.basename(cale)
			try:
				os.link(name, base, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
			except OSError as e:
				if e.errno in (errno.EPERM, errno.EXDEV, errno.ENOTSUP, errno.EACCES):
					# FAT has no hard links: reserve the final name exclusively.
					try:
						newfd = os.open(base, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
					except FileExistsError:
						newfd = None
					if newfd is not None:
						created = os.fstat(newfd)
						try:
							with os.fdopen(newfd, 'wb') as out:
								obj.copiaza(out)
								out.flush()
								os.fsync(out.fileno())
							return created
						except BaseException:
							current = os.stat(base, dir_fd=fd, follow_symlinks=False)
							if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
								os.unlink(base, dir_fd=fd)
							raise
				elif not isinstance(e, FileExistsError):
					raise
				existing = os.open(base, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
				with os.fdopen(existing, 'rb') as src:
					st = os.fstat(src.fileno())
					if not stat.S_ISREG(st.st_mode) or st.st_size != obj.octeti or _hashFlux(src, obj.octeti) != obj.digest:
						raise OSError(T_LOCAL)
				return False
			return os.stat(name, dir_fd=fd, follow_symlinks=False)
		finally:
			os.unlink(name, dir_fd=fd)
	finally:
		os.close(fd)


def _adaugaExact(p):
	registru, files, source, size, digest = p['_exact']
	created = []
	with _IMPORT_LACAT:
		try:
			class Sink:
				def write(self, b): pass
			_FisierExact(source, [(0, size, digest)], size, digest).copiaza(Sink())
			with I._LACAT:
				_rezumatExact(p, _surse())
			# Validate all slices again before any filesystem publication.
			for _, obj in files:
				obj.copiaza(Sink())
			for cale, obj in files:
				parent = _caleExacta(cale)
				if os.name == 'nt' and not os.path.isdir(parent):
					os.makedirs(parent, mode=0o700, exist_ok=True)
				# Publish through a resolved parent, preserving the recorded path.
				target = os.path.join(parent, os.path.basename(cale))
				written = _scrieExact(target, obj)
				if written:
					created.append((target, written))
			with I._LACAT:
				current = _registruBrut()
				d = _dateRegistru(current)
				rez, noi = _rezumatExact(p, d['surse'])
				if rez['peste']:
					raise OSError(T_MARE)
				if noi or not d['surse']:
					raw = registru if not d['surse'] else json.dumps(dict(d, surse=d['surse'] + noi), ensure_ascii=False).encode('utf-8')
					I._asiguraDosar()
					I._scrie(I._caleSurse(), raw, 0o600)
					I._stare_piconuri = I._starePiconuri(d['surse'] + noi)
					I._versiune_piconuri += 1
				return dict(rez, adaugate=len(noi))
		finally:
			with I._LACAT:
				try:
					current_sources = _surse()
					used = {os.path.realpath(s['adresa']) for s in current_sources if isinstance(s.get('adresa'), str) and os.path.isabs(s['adresa'])}
					used.update(os.path.realpath(I._caleCanale(s['id'])) for s in current_sources)
				except OSError:
					used = {p for p, _ in created}
				for path, original in created:
					if path in used:
						continue
					try:
						now = os.lstat(path)
						if (now.st_dev, now.st_ino) == (original.st_dev, original.st_ino):
							os.unlink(path)
					except OSError:
						pass


def _citesteArhiva(f, cale):
	"""No path extraction and no oversized JSON parts."""
	if f.read(len(MAGIC_EXACT)) == MAGIC_EXACT:
		f.seek(0)
		return _citesteExact(f, cale)
	f.seek(0)
	p = dict(surse=[], rele=[], incomplete=[], neacceptate=[])
	try:
		if os.fstat(f.fileno()).st_size > MAX_ARHIVA:
			raise ValueError()
		if f.read(len(MAGIC_ARHIVA)) != MAGIC_ARHIVA:
			raise ValueError()
		numar, index, curenta, lista = 0, -1, None, None
		while True:
			header = f.read(512)
			if header == b'\0' * 512:
				coada = f.read(10241)
				if len(coada) > 10240 or any(coada):
					raise ValueError()
				break
			if len(header) != 512:
				raise ValueError()
			t = tarfile.TarInfo.frombuf(header, 'ascii', 'strict')
			debut = f.tell()
			numar += 1
			if not t.isfile() or t.name != '%06d.%s' % (numar, 'm3u' if lista else 'json'):
				raise ValueError()
			if lista:
				if t.size != lista['octeti'] or not 0 < t.size <= MAX_PLAYLIST:
					raise ValueError()
				start = debut
				refuzuri = []
				digest, cheie = _verificaListaFlux(f, t.size, refuzuri)
				if digest != lista['sha256']:
					raise ValueError()
				if len(p['neacceptate']) + len(refuzuri) > MAX_RANDURI:
					raise _Limita()
				p['neacceptate'].extend(dict(rand=index+1, motiv=motiv) for _, motiv in refuzuri)
				if any(motiv == T_DRM for _, motiv in refuzuri):
					p['surse'].remove(curenta)
				curenta.pop('adresa', None)
				curenta['_local'] = _ListaTransfer(cale, start, t.size, digest, cheie)
				lista = None
				f.seek(debut + ((t.size + 511) // 512) * 512)
				continue
			if not 0 < t.size <= MAX_FISIER:
				raise ValueError()
			text = f.read(t.size).decode('utf-8')
			_verificaText(text)
			_verificaJson(text)
			d = json.loads(text)
			if not isinstance(d, dict) or type(d.get('sursa')) is not int:
				raise ValueError()
			if 'date' in d:
				if d['sursa'] != index + 1 or index + 1 >= I.MAX_SURSE:
					raise ValueError()
				if curenta and curenta.pop('_asteapta_local', False):
					raise ValueError()
				curenta = _curata(d['date'])
				if not curenta:
					raise ValueError()
				curenta.update(ascunse=_OptiuniTransfer(cale), ordine=_OptiuniTransfer(cale))
				if d.get('local'):
					curenta['_asteapta_local'] = True
				p['surse'].append(curenta)
				index = d['sursa']
			elif not curenta or d['sursa'] != index:
				raise ValueError()
			elif 'camp' in d:
				if d['camp'] not in ('ascunse', 'ordine') or not isinstance(d.get('valori'), list) or not all(isinstance(v, str) and I.textBun(v) for v in d['valori']):
					raise ValueError()
				curenta[d['camp']].pune(debut, t.size, text.encode('utf-8'), 'valori', len(d['valori']))
			elif curenta.pop('_asteapta_local', False) and type(d.get('octeti')) is int:
				lista = d
			else:
				raise ValueError()
			f.seek(debut + ((t.size + 511) // 512) * 512)
		if lista or (curenta and curenta.pop('_asteapta_local', False)):
			raise ValueError()
		return p
	except (OSError, ValueError, TypeError, KeyError, UnicodeError, tarfile.TarError):
		return dict(surse=[], rele=[], incomplete=[], neacceptate=[], eroare=T_CITIRE)


def _scrieMeta(f, d):
	meta = json.dumps(d, ensure_ascii=False).encode('utf-8') + b'\n'
	if len(meta) > MAX_META:
		raise OSError(T_MARE)
	try:
		_verificaJson(meta.decode('utf-8'))
	except _Limita:
		raise OSError(T_MARE) from None
	f.write(meta)


class _OptiuniTransfer:
	"""Metadate pe disc: cititorul nu aduna listele tuturor partilor in RAM."""
	def __init__(self, cale):
		self.cale, self.parti, self.total = cale, [], 0

	def pune(self, start, n, date, camp, cate):
		self.parti.append((start, n, hashlib.sha256(date).hexdigest(), camp))
		self.total += cate

	def __len__(self):
		return self.total

	def __iter__(self):
		if not self.parti:
			return
		fd = os.open(self.cale, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
		with os.fdopen(fd, 'rb') as f:
			if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				raise OSError(T_CITIRE)
			for start, n, digest, camp in self.parti:
				f.seek(start)
				date = f.read(n)
				if hashlib.sha256(date).hexdigest() != digest:
					raise OSError(T_CITIRE)
				text = date.decode('utf-8')
				_verificaText(text)
				_verificaJson(text)
				yield from json.loads(text)[camp]


class _ListaTransfer:
	"""Referinta privata la o bucata verificata, niciodata luata din JSON."""
	def __init__(self, cale, start, octeti, digest, cheie):
		self.cale, self.start, self.octeti = cale, start, octeti
		self.digest, self.cheie = digest, cheie

	def citeste(self):
		if self.octeti > MAX_FISIER:
			raise OSError(T_MARE)
		fd = os.open(self.cale, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
		with os.fdopen(fd, 'rb') as f:
			if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				raise OSError(T_CITIRE)
			f.seek(self.start)
			date = f.read(self.octeti)
		if hashlib.sha256(date).hexdigest() != self.digest:
			raise OSError(T_CITIRE)
		return date.decode('utf-8')

	def copiaza(self, out):
		fd = os.open(self.cale, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
		with os.fdopen(fd, 'rb') as f:
			if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				raise OSError(T_CITIRE)
			f.seek(self.start)
			if _hashFlux(f, self.octeti, out) != self.digest:
				raise OSError(T_CITIRE)


def _citesteTransfer(f, cale):
	try:
		nr = int(f.readline(32)[len(MAGIC_TRANSFER):])
		if not 0 <= nr <= I.MAX_SURSE:
			raise ValueError()
		p = dict(surse=[], rele=[], incomplete=[], neacceptate=[])
		for _ in range(nr):
			meta = f.readline(MAX_META + 1)
			if len(meta) > MAX_META or not meta.endswith(b'\n'):
				raise ValueError()
			_verificaJson(meta.decode('utf-8'))
			d = json.loads(meta)
			optiuni = {}
			if isinstance(d, dict):
				for camp in ('ascunse', 'ordine'):
					valori = d.pop(camp, [])
					if not isinstance(valori, list) or not all(isinstance(v, str) and I.textBun(v) for v in valori):
						raise ValueError()
					optiuni[camp] = _OptiuniTransfer(cale)
					if valori:
						optiuni[camp].pune(f.tell()-len(meta), len(meta), meta, camp, len(valori))
			if not isinstance(d, dict):
				raise ValueError()
			n = d.get('octeti')
			if type(n) is not int or not 0 <= n <= MAX_PLAYLIST:
				raise ValueError()
			start = f.tell()
			refuzuri = []
			if n:
				if d.get('fel') != 'm3u':
					raise ValueError()
				digest, cheie = _verificaListaFlux(f, n, refuzuri)
				if digest != d.get('sha256'):
					raise ValueError()
				s = _curata(dict(d, adresa='https://transfer.invalid/lista.m3u'))
				if not s:
					raise ValueError()
				s.pop('adresa')
				s['_local'] = _ListaTransfer(cale, start, n, d['sha256'], cheie)
			else:
				if d.get('sha256') != hashlib.sha256(b'').hexdigest():
					raise ValueError()
				s = _curata(d)
			if f.read(1) != b'\n':
				raise ValueError()
			if not s:
				raise ValueError()
			s.update(optiuni)
			if len(p['neacceptate']) + len(refuzuri) > MAX_RANDURI:
				raise _Limita()
			p['neacceptate'].extend(dict(rand=nr, motiv=motiv) for nr, motiv in refuzuri)
			if not any(motiv == T_DRM for _, motiv in refuzuri):
				p['surse'].append(s)
		if f.read(1):
			raise ValueError()
		return p
	except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
		return dict(surse=[], rele=[], incomplete=[], neacceptate=[], eroare=T_CITIRE)


def _inchideTransferWeb(jeton):
	global _WEB_TRANSFER
	with _WEB_LACAT:
		s = _WEB_TRANSFER
		if s and secrets.compare_digest(s['jeton'], jeton):
			_WEB_TRANSFER = None
			s['ceas'].cancel()
			try:
				s['fisier'].close()
			finally:
				try:
					os.unlink(s['cale'])
				except FileNotFoundError:
					pass


def primesteBucata(arg, traduce=lambda x: x):
	"""Un transfer privat limitat pe disc, expirat automat dupa zece minute."""
	global _WEB_TRANSFER
	with _WEB_LACAT:
		jeton = arg.get('jeton', '')
		s = None
		pastreaza = False
		try:
			if jeton:
				if not _WEB_TRANSFER or not isinstance(jeton, str) or not secrets.compare_digest(_WEB_TRANSFER['jeton'], jeton):
					raise ValueError()
				s = _WEB_TRANSFER
				if arg.get('pas') == 'anuleaza':
					_inchideTransferWeb(jeton)
					return dict(result=True)
			else:
				if _WEB_TRANSFER is not None:
					return dict(result=False, ocupat=True)
				meta = arg.get('meta', '')
				if not isinstance(meta, str) or len(meta.encode('utf-8')) > MAX_META:
					raise ValueError()
				_verificaJson(meta)
				d = json.loads(meta)
				if not isinstance(d, dict) or d.get('fel') not in ('m3u', 'arhiva') or type(d.get('octeti')) is not int or not 0 < d['octeti'] <= (MAX_ARHIVA if d['fel'] == 'arhiva' else MAX_PLAYLIST) or (d['fel'] != 'arhiva' and not re.fullmatch('[0-9a-f]{64}', str(d.get('sha256', '')))):
					raise ValueError()
				jeton = secrets.token_hex(24)
				os.makedirs(I.dosarListe(), mode=0o700, exist_ok=True)
				fd, cale = tempfile.mkstemp(prefix='.hds-iptv-transfer-', dir=I.dosarListe())
				f = os.fdopen(fd, 'w+b')
				ceas = threading.Timer(600, _inchideTransferWeb, args=(jeton,))
				ceas.daemon = True
				s = dict(jeton=jeton, meta=d, cale=cale, fisier=f, primit=0, ceas=ceas)
				_WEB_TRANSFER = s
				ceas.start()
				if d['fel'] != 'arhiva':
					f.write(MAGIC_TRANSFER + b'1\n')
					_scrieMeta(f, d)
			text = arg.get('text', '')
			if not isinstance(text, str) or len(text) > (MAX_BUCATA + 2) // 3 * 4 or arg.get('pozitie') != str(s['primit']):
				raise ValueError()
			b = base64.b64decode(text, validate=True)
			if not b or len(b) > MAX_BUCATA or s['primit'] + len(b) > s['meta']['octeti']:
				raise ValueError()
			s['fisier'].write(b)
			s['primit'] += len(b)
			if s['primit'] < s['meta']['octeti']:
				pastreaza = True
				return dict(result=True, jeton=jeton)
			if s['meta']['fel'] != 'arhiva':
				s['fisier'].write(b'\n')
			s['fisier'].flush()
			s['fisier'].seek(0)
			p = (_citesteArhiva if s['meta']['fel'] == 'arhiva' else _citesteTransfer)(s['fisier'], s['cale'])
			if p.get('eroare'):
				return dict(result=False, message=traduce(T_DETERIORATA if s['meta']['fel'] == 'arhiva' else p['eroare']))
			rez = adauga(p) if arg.get('pas') == 'adauga' else rezumat(p)
			return dict(result=not rez.get('eroare'), import_stalker=rez, message=textRezumat(rez, traduce), incomplete=[],
				amprenta_transfer=p['_exact'][4] if '_exact' in p else hashlib.sha256(repr(_identitate(p['surse'][0])).encode('utf-8')).hexdigest() if p['surse'] else '')
		except (OSError, ValueError, TypeError, RecursionError):
			return dict(result=False, message=traduce(T_CITIRE))
		finally:
			if s and not pastreaza:
				_inchideTransferWeb(jeton)


def exportaFisier(dosar):
	"""Nume liber, fara a inlocui vreun fisier al omului, nici o legatura."""
	extensie = '.hdsiptv'
	fd, temporar = tempfile.mkstemp(prefix='.hds-transfer-', dir=dosar)
	try:
		with os.fdopen(fd, 'w+b') as f:
			scrieTransfer(f)
		for n in range(10000):
			cale = os.path.join(dosar, 'surse-iptv%s%s' % ('-%d' % n if n else '', extensie))
			try:
				os.link(temporar, cale)
			except FileExistsError:
				continue
			except OSError as e:
				if e.errno not in (errno.EPERM, errno.EXDEV, errno.ENOTSUP, errno.EACCES):
					raise
				# FAT nu are legaturi; numele exclusiv ramane protejat de inlocuire.
				try:
					fd = os.open(cale, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
				except FileExistsError:
					continue
				try:
					with os.fdopen(fd, 'wb') as out, open(temporar, 'rb') as src:
						shutil.copyfileobj(src, out, 64 * 1024)
						out.flush()
						os.fsync(out.fileno())
				except BaseException:
					os.unlink(cale)
					raise
			return cale
		raise OSError('No free export filename')
	finally:
		os.unlink(temporar)
