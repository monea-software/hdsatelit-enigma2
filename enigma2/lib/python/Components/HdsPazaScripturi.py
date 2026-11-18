# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Scripturile de pornire ale modulelor de acces instalate din pachete se pun singure la loc cand le sterge altcineva (0.7.7).
Doar in imaginea HDSatelit.

De ce: unele pachete de module ale altor autori sterg la scoatere, cu un tipar larg, si scripturile altor module (de pilda
`rm -rf /etc/init.d/softcam.oscam*` in scriptul de dupa scoatere al unui pachet OSCam). Dupa scoaterea unui astfel de pachet,
modulele din feedul nostru ramaneau instalate (opkg le stie, programele lor sunt la locul lor), dar fara script: nu mai apareau
in Acces conditionat si nu mai porneau la pornirea receptorului, iar omul nu stia de ce.

Cum: pentru fiecare pachet instalat din categoria modulelor de acces (HdsPachete.categorie_din_nume), scripturile <fel>.<x> din
/etc/init.d scrise in lista lui de fisiere (<info_dir>/<pachet>.list) se copiaza in COPII cat exista (si din nou cand se schimba,
la o actualizare). Cand un astfel de script lipseste, desi pachetul e tot instalat si il tine in lista, se pune la loc din copie,
cu acelasi continut, executabil. Nimic nu se instaleaza si nu se descarca; legatura alegerii nu se atinge (cu scriptul la loc,
alegerea de dinainte merge iar). Cat timp opkg lucreaza (lacatul lui e tinut, se vede in /proc/locks), nu se pune nimic la loc:
o actualizare poate scoate si pune fisiere. Copiile pachetelor scoase se sterg.

Scripturile sterse inainte de prima copie (pachetul altuia scos pe o versiune fara paza) raman in LIPSA_FARA_COPIE si pachetele
lor se REINSTALEAZA SINGURE din feedul nostru (porneste_reinstalarea): opkg update, apoi `opkg install --force-reinstall` pe
fiecare pachet al carui script lipseste, numai daca cea mai noua versiune a lui e intr-un feed HD Satelit
(HdsModuleLipsa.provenienta), pe un fir separat, fara nimic pe ecran (greseala e a noastra, omul nu are ce face). O singura
incercare pe pornirea receptorului (semnul INCERCARE, in /tmp), numai cand opkg nu lucreaza si receptorul are ruta implicita
(RUTE), numai pe receptor (radacina /) si de pe firul enigma2; fiecare pas un rand in jurnal. Pachetele noastre repornesc singure
modulul ales la reinstalare (scriptul lor de dupa instalare); dupa aceea se mai uita o data si HdsModuleAcces
(dupa_pornirea_interfetei), care nu porneste modulul oprit de om.
Se cheama din HdsModuleAcces (inainte de lista aratata si dupa pornirea interfetei). Merge si pe PC (probele: `sistem` cu o
radacina de proba). Nu arunca."""
import os
import posixpath
import threading

try:
	from Components.HdsInterfeteCam import CATEGORIE_ACCES, DOSAR_SCRIPTURI, SCRIPT_MAXIM, Sistem, e_script_modul, feluri
	from Components.HdsPachete import categorie_din_nume, citeste_configurarea, nume_valid, strofe_din_text
except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
	from HdsInterfeteCam import CATEGORIE_ACCES, DOSAR_SCRIPTURI, SCRIPT_MAXIM, Sistem, e_script_modul, feluri
	from HdsPachete import categorie_din_nume, citeste_configurarea, nume_valid, strofe_din_text

COPII = '/var/lib/hds-scripturi-module'
LACAT_OPKG = '/run/opkg.lock'
LACATE = '/proc/locks'
LISTA_MAXIM = 1024 * 1024
STARE_MAXIM = 8 * 1024 * 1024
_lacat = threading.Lock()
_memorie = {'cheie': None, 'pachete': {}}    # starea opkg citita ultima data: (mtime, marime) -> {pachet: [cale script]}
# scripturile tinute de un pachet instalat care lipsesc fara sa avem copie (sterse inainte de prima copie); la fiecare sincronizare
LIPSA_FARA_COPIE = set()
INCERCARE = '/tmp/.hds-scripturi-reinstalare'   # tmpfs: o singura reinstalare pe pornirea receptorului
RUTE = '/proc/net/route'
TERMEN_UPDATE_S = 300
TERMEN_INSTALARE_S = 600
_reinstalare = {'lucrare': None}


def _jurnal(text):
	print("[HdsPazaScripturi] %s" % text)


def _cheie_stare(sistem, fisier):
	try:
		st = os.stat(sistem.cale(fisier))
	except OSError:
		return None
	return (st.st_mtime, st.st_size)


def scripturile_pachetelor(sistem, conf=None):
	"""{pachet: [cale <fel>.<x> din DOSAR_SCRIPTURI]} pentru pachetele instalate din categoria modulelor de acces, din starea
	opkg si listele lor de fisiere; citite din nou numai cand fisierul de stare s-a schimbat."""
	conf = conf or citeste_configurarea(sistem.radacina)
	cheie = (sistem.radacina, _cheie_stare(sistem, conf.status_file))
	if cheie[1] is not None and _memorie['cheie'] == cheie:
		return _memorie['pachete']
	feluri_ = feluri(sistem)
	rez = {}
	try:
		text = sistem.citeste(conf.status_file, STARE_MAXIM)
	except (OSError, IOError):
		text = ''
	for s in strofe_din_text(text):
		n = s.get('package', '')
		st = s.get('status', '').split()
		if not nume_valid(n) or 'installed' not in st or 'not-installed' in st or categorie_din_nume(n) != CATEGORIE_ACCES:
			continue
		try:
			randuri = sistem.citeste(posixpath.join(conf.info_dir, n + '.list'), LISTA_MAXIM).splitlines()
		except (OSError, IOError):
			continue
		for r in randuri:
			cale = r.split('\t', 1)[0].strip()
			if posixpath.dirname(cale) == DOSAR_SCRIPTURI and e_script_modul(posixpath.basename(cale), feluri_):
				rez.setdefault(n, []).append(cale)
	_memorie.update(cheie=cheie, pachete=rez)
	return rez


def opkg_lucreaza(sistem):
	"""True cand cineva tine lacatul opkg (LACAT_OPKG, cautat dupa inode in LACATE)."""
	try:
		ino = os.stat(sistem.cale(LACAT_OPKG)).st_ino
	except OSError:
		return False
	try:
		text = sistem.citeste(LACATE, 256 * 1024)
	except (OSError, IOError):
		return False
	for r in text.splitlines():
		parti = r.split()
		for p in parti:
			if p.count(':') == 2 and p.rsplit(':', 1)[1] == str(ino):
				return True
	return False


def _scrie(cale, date):
	dosar, nume = os.path.split(cale)
	if not os.path.isdir(dosar):
		os.makedirs(dosar)
	nou = os.path.join(dosar, '.%s.hds-%d' % (nume, os.getpid()))
	try:
		with open(nou, 'wb') as fh:
			fh.write(date)
		os.chmod(nou, 0o755)
		os.replace(nou, cale)
	except (OSError, IOError):
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _citeste_octeti(cale):
	with open(cale, 'rb') as fh:
		return fh.read(SCRIPT_MAXIM + 1)


def _sincronizeaza(sistem):
	pachete = scripturile_pachetelor(sistem)
	copii = sistem.cale(COPII)
	ocupat = None
	facute = []
	pastrate = set()
	lipsa = set()
	for pachet in sorted(pachete):
		for cale in pachete[pachet]:
			nume = posixpath.basename(cale)
			copie = os.path.join(copii, pachet, nume)
			pastrate.add((pachet, nume))
			real = sistem.cale(cale)
			if os.path.lexists(real):
				if os.path.islink(real) or not os.path.isfile(real):
					continue
				st = os.stat(real)
				try:
					sc = os.stat(copie)
					if (sc.st_size, sc.st_mtime_ns) == (st.st_size, st.st_mtime_ns):
						continue   # copia are marimea si ora scriptului: nu se mai citeste nimic
				except OSError:
					pass
				date = _citeste_octeti(real)
				if len(date) > SCRIPT_MAXIM:
					continue
				try:
					vechi = _citeste_octeti(copie)
				except (OSError, IOError):
					vechi = None
				if vechi != date:
					_scrie(copie, date)
					facute.append(('copiat', cale))
				try:
					os.utime(copie, ns=(st.st_atime_ns, st.st_mtime_ns))
				except OSError:
					pass
				continue
			if not os.path.isfile(copie):
				# sters inainte de prima noastra copie (de pilda pe o versiune fara paza): nu avem ce pune la loc; ramane in
				# LIPSA_FARA_COPIE (de folosit de ecran) si se scrie in jurnal o singura data
				lipsa.add(cale)
				if cale not in LIPSA_FARA_COPIE:
					facute.append(('lipsa fara copie', cale))
				continue
			if ocupat is None:
				ocupat = opkg_lucreaza(sistem)
			if ocupat:
				continue
			_scrie(real, _citeste_octeti(copie))
			facute.append(('pus la loc', cale))
	LIPSA_FARA_COPIE.clear()
	LIPSA_FARA_COPIE.update(lipsa)
	try:
		dosare = sorted(os.listdir(copii))
	except OSError:
		dosare = []
	for pachet in dosare:
		d = os.path.join(copii, pachet)
		try:
			fisiere = sorted(os.listdir(d))
		except OSError:
			continue
		for nume in fisiere:
			if (pachet, nume) not in pastrate and not nume.startswith('.'):
				os.remove(os.path.join(d, nume))
				facute.append(('copie stearsa', pachet + '/' + nume))
		try:
			if not os.listdir(d):
				os.rmdir(d)
		except OSError:
			pass
	return facute


def pachete_de_reinstalat(sistem):
	"""[pachet] instalate al caror script <fel>.<x> e in LIPSA_FARA_COPIE (dupa ultima sincronizare)"""
	pachete = scripturile_pachetelor(sistem)
	return sorted(p for p, cai in pachete.items() if any(c in LIPSA_FARA_COPIE for c in cai))


def are_retea(sistem):
	"""True cand receptorul are ruta implicita (destinatia 00000000 in RUTE)"""
	try:
		text = sistem.citeste(RUTE, 64 * 1024)
	except (OSError, IOError):
		return False
	for r in text.splitlines()[1:]:
		parti = r.split()
		if len(parti) > 3 and parti[1] == '00000000':
			try:
				if int(parti[3], 16) & 1:
					return True
			except ValueError:
				continue
	return False


def reinstaleaza(rad, pachete, ruleaza=None, al_nostru=None, opkg=None):
	"""Pe firul lucrarii: opkg update, apoi `install --force-reinstall` pe fiecare pachet din feedul nostru. [(pachet, rezultat)];
	rezultat: 'gata', 'strain' (nu e din feedul nostru), 'fara opkg' sau 'cod <n>: <ultimele randuri>'."""
	try:
		from Components import HdsModulNepornit as N
		from Components import HdsReinstalare as R
	except ImportError:  # probe pe PC
		import HdsModulNepornit as N
		import HdsReinstalare as R
	ruleaza = ruleaza or N._ruleaza
	al_nostru = al_nostru or N._al_nostru
	comanda = R._opkg(rad, opkg)
	if comanda is None:
		return [(p, 'fara opkg') for p in pachete]
	cod, iesire = ruleaza(comanda + ['update'], TERMEN_UPDATE_S)
	if cod != 0:
		_jurnal("opkg update: cod %s (%s)" % (cod, N._scurt(iesire)))
	rez = []
	for p in pachete:
		if not al_nostru(p):
			rez.append((p, 'strain'))
			continue
		cod, iesire = ruleaza(comanda + ['install', '--force-reinstall', p], TERMEN_INSTALARE_S)
		rez.append((p, 'gata' if cod == 0 else 'cod %s: %s' % (cod, N._scurt(iesire))))
	return rez


def _dupa_reinstalare(rezultat, eroare, sistem=None, dupa=None):
	"""Pe firul enigma2: randurile in jurnal, copiile scripturilor puse la loc, apoi HdsModuleAcces porneste modulul ales care
	nu ruleaza (fara cel oprit de om)."""
	_reinstalare['lucrare'] = None
	if eroare:
		_jurnal("reinstalarea: %s" % eroare)
	for p, r in rezultat or []:
		_jurnal("reinstalarea %s: %s" % (p, r))
	sincronizeaza(sistem)
	try:
		if dupa is None:
			try:
				from Components import HdsModuleAcces as H
			except ImportError:
				import HdsModuleAcces as H
			dupa = H.dupa_pornirea_interfetei
		dupa()
	except Exception as e:
		_jurnal("dupa reinstalare: %r" % (e,))


def porneste_reinstalarea(sistem, lucrare=None, ruleaza=None, al_nostru=None, opkg=None, dupa=None):
	"""Reinstalarea automata a pachetelor cu scripturi sterse fara copie (vezi sus). Intoarce pachetele trimise la reinstalare,
	sau [] cand nu e cazul acum (nimic lipsa, incercarea pe pornirea asta s-a facut deja, una in lucru, opkg lucreaza, fara
	retea). `lucrare(functie, la_sfarsit)` (HdsImportSurse.Lucrare), `ruleaza`, `al_nostru`, `opkg` si `dupa` se dau la probe.
	Nu arunca."""
	try:
		if _reinstalare['lucrare'] is not None or sistem.exista(INCERCARE):
			return []
		pachete = pachete_de_reinstalat(sistem)
		if not pachete or opkg_lucreaza(sistem) or not are_retea(sistem):
			return []
		with open(sistem.cale(INCERCARE), 'w') as fh:
			fh.write(' '.join(pachete) + '\n')
		_jurnal("scripturi sterse fara copie (%s): reinstalez din feedul HD Satelit %s" % (
			', '.join(sorted(LIPSA_FARA_COPIE)), ', '.join(pachete)))
		if lucrare is None:
			from Components.HdsImportSurse import Lucrare as lucrare
		rad = sistem.radacina
		_reinstalare['lucrare'] = True    # ocupat inainte de fir: o lucrare care termina pe loc il elibereaza ea insasi
		obiect = lucrare(lambda: reinstaleaza(rad, pachete, ruleaza, al_nostru, opkg),
			lambda r, e: _dupa_reinstalare(r, e, sistem, dupa))
		if _reinstalare['lucrare'] is True:
			_reinstalare['lucrare'] = obiect   # tinut in viata pana la sfarsit (eTimer-ul lucrarii)
		return pachete
	except Exception as e:
		_reinstalare['lucrare'] = None
		_jurnal("porneste_reinstalarea: %r" % (e,))
		return []


def _automat(sistem):
	"""reinstalarea automata merge numai pe receptor (radacina /) si de pe firul enigma2 (eTimer-ul lucrarii)"""
	return sistem.radacina in ('/', '') and threading.current_thread() is threading.main_thread()


def sincronizeaza(sistem=None):
	"""Copiaza scripturile modulelor instalate si le pune la loc pe cele sterse (vezi sus). [(fapta, cale)]: ('copiat', ...),
	('pus la loc', ...), ('copie stearsa', <pachet>/<nume>), ('lipsa fara copie', ...) (o data, cand apare). Nu arunca."""
	sistem = sistem or Sistem()
	try:
		with _lacat:
			facute = _sincronizeaza(sistem)
	except Exception as e:
		_jurnal("sincronizarea: %r" % (e,))
		return []
	for fapta, cale in facute:
		if fapta != 'copiat':
			_jurnal("%s %s" % (fapta, cale))
	try:
		if LIPSA_FARA_COPIE and _automat(sistem):
			porneste_reinstalarea(sistem)
	except Exception as e:
		_jurnal("reinstalarea: %r" % (e,))
	return facute
