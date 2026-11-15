# Modificat de moneasoftware.com si hdsatelit.com, 2026
"""Ce lasa opkg remove in urma unui pachet cu fisiere .py (TODO 13.11 21:30).

opkg sterge numai fisierele din lista pachetului (info_dir/<pachet>.list). Fisierele compilate scrise la rulare nu sunt in
lista: <nume>.pyc / <nume>.pyo langa sursa (pe receptor stau langa .py), __pycache__/<nume>.cpython-*.pyc si originalele
.py2 ale traducatorului Python 2 (Components/HdsPython2Traducere.py). Raman ele si dosarul lor; pentru un plugin din
Plugins/Extensions, un plugin.pyc ramas face din dosarul gol un plugin care apare in lista (cu codul vechi) fara pachet.

O singura masura, in Components/Ipkg.py (IpkgComponent: Extensii, interfata web /api/extensii-sterge, temele, orice
opkg remove pornit din interfata):
  instantaneu(argumente)  inainte de opkg: fisierele .py ale pachetelor cerute (si, la --autoremove, ale pachetelor
                          instalate ca dependinte, Auto-Installed: yes), din listele lor, cat inca exista;
  curata(instantaneu)     dupa opkg, inainte de EVENT_DONE (deci inainte ca Extensiile sa reciteasca pluginurile):
                          pentru fiecare pachet care nu mai e instalat (lista lui a disparut) sterge compilatele
                          fisierelor lui .py si dosarele lor ramase goale.
Se ating numai fisierele care poarta numele unui .py al pachetului sters si numai dosarele in care pachetul avea .py
(niciodata dosarul parinte comun, de pilda Plugins/Extensions); un dosar se sterge numai gol (os.rmdir).
Pachetele sterse din consola (opkg remove fara interfata) le acopera clasa hds-pyc-curat din stratul imaginii.
"""
import os

# langa sursa: compilatele vechi si originalul pastrat de traducatorul Python 2
EXT_LANGA = ('.pyc', '.pyo', '.py2')
DOSAR_CACHE = '__pycache__'
# cate pachete dependinte (--autoremove) se citesc cel mult; restul nu se curata (opkg le sterge oricum)
MAX_PACHETE = 400


def _jurnal(text):
	print('[HdsPycRamase] %s' % text)


def _cale(radacina, p):
	if not radacina or radacina == '/':
		return p
	return os.path.join(radacina, p.lstrip('/'))


def _dosare_opkg(radacina='/'):
	"""(info_dir, status_file) din configurarea opkg, cu caile obisnuite cand nu se poate citi"""
	info, status = '/var/lib/opkg/info', '/var/lib/opkg/status'
	try:
		from Components import HdsPachete as P
		conf = P.citeste_configurarea(radacina)
		info, status = conf.info_dir or info, conf.status_file or status
	except Exception as e:
		_jurnal('configurarea opkg: %s' % e)
	return _cale(radacina, info), _cale(radacina, status)


def pachete_sterse(argumente):
	"""(pachetele, autoremove) pentru argumentele unui opkg remove (lista din Ipkg.opkgArguments), altfel None"""
	if not isinstance(argumente, (list, tuple)):
		return None
	optiuni = [a for a in argumente if isinstance(a, str) and a.startswith('-')]
	rest = [a for a in argumente if isinstance(a, str) and not a.startswith('-')]
	if not rest or rest[0] != 'remove' or len(rest) < 2:
		return None
	return rest[1:], '--autoremove' in optiuni


def _dependinte_automate(status):
	"""numele pachetelor instalate ca dependinte (Auto-Installed: yes): --autoremove le poate sterge si pe ele"""
	try:
		from Components import HdsPachete as P
		strofe = P.citeste_strofe(status)
	except Exception as e:
		_jurnal('starea pachetelor: %s' % e)
		return []
	rez = []
	for s in strofe:
		st = s.get('status', '').split()
		if 'installed' in st and 'not-installed' not in st and s.get('auto-installed', '').strip().lower() == 'yes':
			rez.append(s.get('package', ''))
	return [n for n in rez if n]


def fisiere_py(lista):
	"""caile fisierelor .py din lista unui pachet (randurile pot avea dupa tab tinta unei legaturi)"""
	rez = []
	try:
		with open(lista, 'r', encoding='utf-8', errors='replace') as fh:
			for r in fh:
				cale = r.split('\t', 1)[0].strip()
				if cale.endswith('.py') and cale.startswith('/'):
					rez.append(cale)
	except OSError:
		pass
	return rez


def instantaneu(argumente, radacina='/'):
	"""{pachet: [fisierele .py]} inainte de un opkg remove; None pentru orice alta comanda sau fara fisiere .py"""
	cerute = pachete_sterse(argumente)
	if cerute is None:
		return None
	pachete, autoremove = cerute
	info, status = _dosare_opkg(radacina)
	nume = list(pachete)
	if autoremove:
		nume += [n for n in _dependinte_automate(status) if n not in nume][:MAX_PACHETE]
	rez = {}
	for n in nume:
		if '/' in n or n.startswith('.'):
			continue  # un fisier .ipk sau un nume care nu e de pachet
		py = fisiere_py(os.path.join(info, n + '.list'))
		if py:
			rez[n] = py
	return rez or None


def _sterge(cale):
	try:
		if os.path.isfile(cale) or os.path.islink(cale):
			os.remove(cale)
			return True
	except OSError:
		pass
	return False


def _rmdir(cale):
	try:
		os.rmdir(cale)  # numai gol
		return True
	except OSError:
		return False


def curata_fisiere(py, radacina='/'):
	"""sterge compilatele ramase ale fisierelor .py date (care nu mai exista) si dosarele lor ramase goale;
	intoarce (fisiere sterse, dosare sterse)"""
	fisiere = 0
	dosare = set()
	for p in py:
		sursa = _cale(radacina, p)
		if os.path.exists(sursa):
			continue  # fisierul e inca acolo (al altui pachet sau readus): compilatele lui raman
		dosar, nume = os.path.split(os.path.normpath(sursa))
		baza = nume[:-3]
		dosare.add(dosar)
		for ext in EXT_LANGA:
			if _sterge(os.path.join(dosar, baza + ext)):
				fisiere += 1
		cache = os.path.join(dosar, DOSAR_CACHE)
		try:
			din_cache = os.listdir(cache)
		except OSError:
			din_cache = []
		for f in din_cache:
			# __pycache__/<nume>.<eticheta>[.opt-N].pyc
			if f.startswith(baza + '.') and f.endswith(('.pyc', '.pyo')) and f.count('.') >= 2:
				if _sterge(os.path.join(cache, f)):
					fisiere += 1
	sterse = 0
	# cele mai adanci intai: un subdosar gol lasa parintele gol
	for dosar in sorted(dosare, key=lambda d: d.count(os.sep), reverse=True):
		if _rmdir(os.path.join(dosar, DOSAR_CACHE)):
			sterse += 1
		if _rmdir(dosar):
			sterse += 1
	return fisiere, sterse


def curata(stare, radacina='/'):
	"""dupa opkg: pentru pachetele din instantaneu care nu mai sunt instalate, compilatele ramase si dosarele goale"""
	if not stare:
		return 0, 0
	info, _status = _dosare_opkg(radacina)
	fisiere = dosare = 0
	for n, py in stare.items():
		if os.path.exists(os.path.join(info, n + '.list')):
			continue  # inca instalat (opkg nu l-a sters)
		f, d = curata_fisiere(py, radacina)
		fisiere += f
		dosare += d
		if f or d:
			_jurnal('%s: %d fisiere compilate si %d dosare ramase dupa stergere, sterse' % (n, f, d))
	return fisiere, dosare
