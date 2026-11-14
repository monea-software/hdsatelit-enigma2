# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvLucru: aduce listele in fundal si le pune in lista de canale, fara repornire. Aceeasi coada pentru ecranul de pe
# televizor (Screens/IptvSetup.py), pentru pagina web /iptv si pentru improspatarea zilnica.
#
# FIRELE: un singur fir de lucru, cate o sursa pe rand: reteaua, citirea listei si scrierea fisierelor. Pe firul enigma2 ramane
# numai legarea in bouquets.tv si reincarcarea buchetelor, la capat, cerute de un eTimer care se uita la rezultat (tragere:
# reactor.callFromThread nu trezeste prompt bucla imaginii). Lista veche ramane cat timp cea noua nu e gata; o eroare nu sterge
# nimic. Buchetele se reincarca numai daca s-a schimbat ceva si nu cat timp e deschis Editorul de canale.
#
# Fara enigma2 (probele de pe PC) lucrarile se pot rula direct cu lucreaza().

import threading
import time

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C

INTERVAL_S = 24 * 3600
PRIMA_DUPA_PORNIRE_S = 90
PAS_S = 60              # de cat ori se uita ceasul zilnic daca a venit vremea, in secunde (ceasul receptorului poate sari)
PAUZE_DUPA_ESEC_S = (15 * 60, 3600, 3 * 3600)   # o improspatare cazuta se reia dupa atat (prima, a doua, apoi mereu a treia), nu peste 24 h:
                                                # serverele mari mai tac cateva zeci de secunde, iar lista si ghidul ramaneau vechi zile intregi
_REFACERE = "*refacere"  # in coada: numai buchetele din nou, dupa o stergere

_lacat = threading.Lock()
_coada = []             # [(sursa_id, tacut)]
_fir = None
_in_lucru = None
_rezultate = []         # [(sursa_id, mesaj sau "", schimbat)]
_ultimele = {}          # sursa_id -> mesajul ultimei incercari ("" = a mers): pagina web il citeste dupa ce s-a terminat
_de_incarcat = False
_ascultatori = []
_ceas = None
_ceas_zilnic = None
_erori_redare = []
_pornit = None          # time.monotonic() la porneste(): ghidul se cere o data dupa fiecare pornire a interfetei
_ghid_cerut = set()     # sursele al caror ghid s-a cerut de la pornire (direct sau dupa lista)


def eroareRedare(sid, mesaj, al_sursei=True):
	"""Omul afla de ce n-a pornit canalul; pe cartela sursei ramane numai ce e al sursei, un canal scos nu strica toata lista."""
	if al_sursei:
		I.actualizeazaSursa(sid, eroare=mesaj)
	with _lacat:
		if mesaj not in _erori_redare:
			_erori_redare.append(mesaj)


def _jurnal(text):
	print("[HdsIptvLucru] %s" % text)


def lucreaza(sursa_id):
	"""O lucrare: aduce canalele sursei si scrie fisierele. Ruleaza pe firul de lucru, nu pe firul enigma2. -> (mesaj de eroare
	sau "", s-au schimbat buchetele)."""
	if sursa_id == _REFACERE:
		return "", I.scrieBuchete()
	s = I.sursa(sursa_id)
	if s is None:
		return "", False
	try:
		canale, info = C.aduce(s)
	except C.EroareIptv as e:
		_jurnal("sursa %s: %s" % (sursa_id, type(e).__name__))
		return _aEsuat(s, e.pentruOm(), e.expira)
	except Exception as e:
		# felul, nu textul: textul poate cuprinde adresa
		_jurnal("sursa %s: %s" % (sursa_id, type(e).__name__))
		return _aEsuat(s, C.E_NU_RASPUNDE)
	I.scrieCanale(sursa_id, I.pastreazaDinBuchete(sursa_id, canale))
	del canale
	catalog = info.pop("catalog", None)
	if catalog is not None:
		I.scrieCatalog(sursa_id, catalog)
	I.actualizeazaSursa(sursa_id, eroare="", ora=I.acum(), ora_incercare=I.acum(), nou=False, esecuri=0, **info)
	return "", I.scrieBuchete()


def _aEsuat(s, mesaj, expira=0):
	"""O sursa abia scrisa care n-a mers niciodata nu ramane in lista: omul vede de ce si corecteaza. Una care a mers isi pastreaza
	canalele si arata eroarea."""
	if s.get("nou"):
		I.stergeSursa(s["id"])
		return mesaj, False
	info = {"expira": expira} if expira else {}
	esecuri = int(s.get("esecuri") or 0) + 1
	pauza = PAUZE_DUPA_ESEC_S[min(esecuri, len(PAUZE_DUPA_ESEC_S)) - 1]
	# ceasul zilnic reia sursa cand ora_incercare are INTERVAL_S in urma; o punem asa incat sa vina dupa pauza
	I.actualizeazaSursa(s["id"], eroare=mesaj, ora_incercare=I.acum() - INTERVAL_S + pauza, esecuri=esecuri, **info)
	return mesaj, False


def _bucla():
	global _fir, _in_lucru, _de_incarcat
	while True:
		with _lacat:
			if not _coada:
				_fir = None
				_in_lucru = None
				return
			_in_lucru = _coada.pop(0)
		mesaj, schimbat = lucreaza(_in_lucru)
		if not mesaj and _in_lucru != _REFACERE:
			s = I.sursa(_in_lucru)
			if s:
				try:
					from Components import HdsIptvEpg, HdsIptvSigle
					HdsIptvEpg.cere(s, None)
					HdsIptvSigle.cere(s, I.citesteCanale(s["id"]))
				except Exception as e:
					_jurnal("sigle/ghid: %s" % type(e).__name__)
		with _lacat:
			_rezultate.append((_in_lucru, mesaj, schimbat))
			_ultimele[_in_lucru] = mesaj
			if schimbat:
				_de_incarcat = True


def _pornesteFirul():
	global _fir
	with _lacat:
		if _fir is not None:
			return
		_fir = threading.Thread(target=_bucla, name="HdsIptvLucru")
		_fir.daemon = True
		_fir.start()


def inLucru(sursa_id=None):
	"""Se lucreaza acum (la sursa data, sau la oricare)."""
	with _lacat:
		if sursa_id is None:
			return _in_lucru is not None or bool(_coada)
		return _in_lucru == sursa_id or sursa_id in _coada


def cere(sursa_id, din_nou=False):
	"""Sursa intra in coada, o singura data. Rezultatul il afla ascultatorii. din_nou: si daca tocmai se lucreaza la ea, fiindca ce se aduce
	acum a pornit cu setarile de dinainte."""
	with _lacat:
		if (din_nou or sursa_id != _in_lucru) and sursa_id not in _coada:
			_coada.append(sursa_id)
	_pornesteFirul()
	_pornesteCeasul()


def ultimulMesaj(sursa_id):
	return _ultimele.get(sursa_id, "")


def adaugaSiCere(s):
	"""Sursa scrisa de om: in lista, iar firul de lucru aduce canalele. -> sursa, sau None cand lista e plina."""
	if I.sursa(s["id"]) is None:
		s = dict(s, nou=True)
	rez = I.adaugaSursa(s)
	if rez is not None:
		pornesteCeasulZilnic()
		cere(rez["id"])
	return rez


def cereToate():
	for s in I.citesteSurse():
		cere(s["id"])


def asculta(functie):
	if functie not in _ascultatori:
		_ascultatori.append(functie)


def nuAsculta(functie):
	if functie in _ascultatori:
		_ascultatori.remove(functie)


# ------------------------------------------------------------------ pe firul enigma2

def _editorDeschis():
	"""Editorul de canale tine in memorie buchetele citite: o reincarcare acum i-ar strica lista. Se asteapta inchiderea lui."""
	try:
		from Screens.InfoBar import InfoBar
		sesiune = InfoBar.instance.session
		ecrane = [sesiune.current_dialog] + [d[0] for d in sesiune.dialog_stack]
		return any(type(e).__name__.startswith("HdsEditorCanale") for e in ecrane if e is not None)
	except Exception:
		return False


def reincarca():
	"""Buchetele din nou in nucleu si indexul cautarii la zi. Pe firul enigma2."""
	try:
		I.leagaIndex()
		from enigma import eDVBDB
		inceput = time.monotonic()
		eDVBDB.getInstance().reloadBouquets()
		_jurnal("buchetele reincarcate, %d ms" % ((time.monotonic() - inceput) * 1000))
	except Exception as e:
		_jurnal("reincarcarea: %s" % type(e).__name__)


def _laTic():
	global _de_incarcat
	try:
		from Components import HdsIptvEpg
		HdsIptvEpg.notifica()
	except (ImportError, AttributeError):
		pass
	with _lacat:
		erori = list(_erori_redare)
		del _erori_redare[:]
		rezultate = list(_rezultate)
		del _rezultate[:]
		incarc = _de_incarcat and not _editorDeschis()
		if incarc:
			_de_incarcat = False
		gata = _in_lucru is None and not _coada and not _de_incarcat
	if incarc:
		reincarca()
	if erori:
		try:
			from Screens.InfoBar import InfoBar
			from Screens.MessageBox import MessageBox
			InfoBar.instance.session.open(MessageBox, _(erori[0]), MessageBox.TYPE_ERROR, timeout=12)
		except Exception:
			pass
	if rezultate:
		try:
			from Components import HdsIptvAdrese
			if I.areSurse():
				HdsIptvAdrese.porneste()
		except Exception as e:
			_jurnal("adresa locala: %s" % type(e).__name__)
	for sursa_id, mesaj, schimbat in rezultate:
		for f in list(_ascultatori):
			try:
				f(sursa_id, mesaj, schimbat)
			except Exception as e:
				_jurnal("ascultator: %s" % type(e).__name__)
	if gata and not rezultate and _ceas is not None and not I.areSurse():
		_ceas.stop()


def _pornesteCeasul():
	global _ceas
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _ceas is None:
		_ceas = eTimer()
		_ceas.callback.append(_laTic)
	_ceas.start(400, False)


def stergeSiReface(sursa_id):
	"""Sterge o sursa si reface buchetele pe firul de lucru; canalele ei dispar din 'IPTV'. -> True daca era."""
	if not I.stergeSursa(sursa_id):
		return False
	cere(_REFACERE)
	return True


def aplicaAscunse(sursa_id, ascunse):
	"""Omul a ales ce grupe se vad: lista de canale se reface pe loc din ce e pe disc, apoi, daca reapare ceva sau daca lista fusese
	taiata la plafon, se aduce din nou, ca sa intre ce nu era acolo."""
	s = I.sursa(sursa_id)
	if s is None:
		return False
	vechi = set(s.get("ascunse") or ())
	ascunse = set(ascunse)
	if ascunse == vechi:
		return True
	I.actualizeazaSursa(sursa_id, ascunse=sorted(ascunse))
	cere(_REFACERE, True)
	if vechi - ascunse or s.get("taiate"):
		cere(sursa_id, True)
	return True


def _zilnic():
	"""Fiecare sursa o data pe zi, dupa ceasul receptorului (se uita o data pe minut). Ghidul TV sta in memoria interfetei si nu
	trece de o repornire a ei, iar el vine numai dupa lista: cand lista nu e de adus, ghidul se cere singur, o data, la
	PRIMA_DUPA_PORNIRE_S dupa pornire (altfel ramanea gol pana la improspatarea de a doua zi)."""
	acum = time.time()
	for s in I.citesteSurse():
		ultima = s.get("ora_incercare") or 0
		if not 0 <= acum - ultima < INTERVAL_S:
			cere(s["id"])
			_ghid_cerut.add(s["id"])
		elif s["id"] not in _ghid_cerut and _pornit is not None and time.monotonic() - _pornit >= PRIMA_DUPA_PORNIRE_S:
			_ghid_cerut.add(s["id"])
			if not I.optiune("ghid_pornire"):
				continue
			try:
				from Components import HdsIptvEpg
				HdsIptvEpg.cere(s, None)
			except Exception as e:
				_jurnal("ghid: %s" % type(e).__name__)
	# timpii de pornire tinuti in memorie: pe disc cel mult o data la HdsIptvSurse.SCRIERE_PORNIRI_S
	I.scriePorniri()
	# cautarea canalelor 4K reale, o data pe saptamana, cand omul nu se uita la un canal de internet (Components/HdsIptv4K.py)
	if _pornit is not None and time.monotonic() - _pornit >= 2 * PRIMA_DUPA_PORNIRE_S:
		try:
			from Components import HdsIptv4K as K
			if not _in_lucru and not _coada and K.deRulat() and not K.omulSeUita():
				K.porneste()
		except Exception as e:
			_jurnal("4K: %s" % type(e).__name__)


def porneste():
	"""La pornirea receptorului, numai cu surse: adresa locala si ceasul zilnic. Fara surse nu costa nimic."""
	global _ceas_zilnic, _pornit
	_pornit = time.monotonic()
	try:
		I.scoateSetarileVechi()
	except Exception as e:
		_jurnal("setarile vechi: %s" % type(e).__name__)
	# adresele puse de om in /etc/enigma2/iptv.txt (prin FTP) se iau singure, si cand nu e inca nicio sursa
	try:
		from Components import HdsIptvFisier
		HdsIptvFisier.porneste()
	except Exception as e:
		_jurnal("fisierul cu adrese: %s" % type(e).__name__)
	if not I.areSurse():
		return
	try:
		I.reparaDrepturi()
	except OSError as e:
		_jurnal("drepturile dosarului: %s" % type(e).__name__)
	from Components import HdsIptvAdrese
	HdsIptvAdrese.porneste()
	_pornesteCeasul()
	pornesteCeasulZilnic()


def pornesteCeasulZilnic():
	global _ceas_zilnic
	if _ceas_zilnic is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	_ceas_zilnic = eTimer()
	_ceas_zilnic.callback.append(_zilnic)
	_ceas_zilnic.start(PAS_S * 1000, False)
