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

import os
import sys
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
_ceas_surse = None
_surse_prezente = False
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
	if s.get("neconectata"):
		# Numai o cerere explicita pentru aceasta sursa activeaza actualizarea zilnica.
		I.actualizeazaSursa(sursa_id, neconectata=False)
		s["neconectata"] = False
	try:
		canale, info = C.aduce(s)
	except C.EroareIptv as e:
		_jurnal("sursa %s: %s" % (sursa_id, type(e).__name__))
		with I._LACAT:
			return (None, False) if _portalSchimbat(s) else _aEsuat(s, e.pentruOm(), e.expira)
	except Exception as e:
		# felul, nu textul: textul poate cuprinde adresa
		_jurnal("sursa %s: %s" % (sursa_id, type(e).__name__))
		with I._LACAT:
			return (None, False) if _portalSchimbat(s) else _aEsuat(s, C.E_NU_RASPUNDE)
	with I._LACAT:
		if _portalSchimbat(s):
			return None, False
		I.scrieCanale(sursa_id, I.pastreazaDinBuchete(sursa_id, canale))
		del canale
		C.cerePiconuri(s)
		catalog = info.pop("catalog", None)
		if catalog is not None:
			I.scrieCatalog(sursa_id, catalog)
		I.actualizeazaSursa(sursa_id, eroare="", ora=I.acum(), ora_incercare=I.acum(), nou=False, esecuri=0, **info)
	return "", I.scrieBuchete()


def _portalSchimbat(s):
	"""Raspunsul inceput cu alte date nu rescrie canalele sau eroarea contului nou."""
	if s.get("fel") != "stalker":
		return False
	acum = I.sursa(s["id"]) or {}
	return _datePortal(s) != _datePortal(acum)


def _datePortal(s):
	return tuple(s.get(k) or "" for k in ("portal", "mac", "user_agent", "referer", "x_user_agent", "stb_type"))


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
		inceput = I.sursa(_in_lucru)
		mesaj, schimbat = lucreaza(_in_lucru)
		if mesaj is None:
			continue
		with I._LACAT:
			acum = I.sursa(_in_lucru)
			if inceput and acum and _portalSchimbat(inceput):
				with _lacat:
					_de_incarcat = _de_incarcat or schimbat
				continue
			with _lacat:
				_rezultate.append((_in_lucru, mesaj, schimbat))
				_ultimele[_in_lucru] = mesaj
				if schimbat:
					_de_incarcat = True
		if not mesaj and _in_lucru != _REFACERE:
			s = I.sursa(_in_lucru)
			if s:
				try:
					from Components import HdsIptvEpg, HdsIptvSigle
					HdsIptvEpg.cere(s, None)
					HdsIptvSigle.cere(s, I.citesteCanale(s["id"]))
				except Exception as e:
					_jurnal("sigle/ghid: %s" % type(e).__name__)


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
	with I._LACAT:
		veche = I.sursa(s["id"])
		portal_schimbat = bool(veche and s.get("fel") == "stalker" and _datePortal(veche) != _datePortal(s))
		if veche is None:
			s = dict(s, nou=True)
		rez = I.adaugaSursa(s)
		if rez is not None:
			C.reiaPortal(s)
			if portal_schimbat:
				with _lacat:
					_rezultate[:] = [r for r in _rezultate if r[0] != rez["id"]]
					_ultimele.pop(rez["id"], None)
	if rez is not None:
		pornesteCeasulZilnic()
		if portal_schimbat:
			cere(rez["id"], din_nou=True)
		else:
			cere(rez["id"])
	return rez


def cereToate():
	for s in I.citesteSurse():
		if not s.get("neconectata"):
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


def timpCitire(text):
	"""Cat sta fereastra de eroare: 12 s, sau mai mult la un text lung (cam 15 semne pe secunda), cel mult 25 s."""
	return max(12, min(25, len(text or "") // 15))


def _laTic():
	global _de_incarcat, _surse_prezente
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
			text = _(erori[0])
			# 0.7.7 (IPX): textul lung (de pilda conexiunile ocupate, ~300 de semne) sta mai mult, ca sa se poata citi; OK il inchide oricand
			InfoBar.instance.session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=timpCitire(text))
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
		_surse_prezente = False
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
	if _ceas_zilnic is None and I.areSurse():
		pornesteCeasulZilnic()


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
		if s.get("neconectata"):
			continue
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
	try:
		pazaListei()
	except Exception as e:
		_jurnal("paza listei: %s" % type(e).__name__)


# 0.7.7 (AST): o lista de canale pusa de alt program (pluginuri de liste ca AutoSetting, un FTP de pe calculator) sterge
# /etc/enigma2/*.tv si pastreaza cel mult buchetele cu 'http': radacina 'IPTV' cu grupe dispare cu totul, iar cea cu o
# singura grupa ramane pe disc, dar nu mai e in bouquets.tv. Regula modulului ramane aceeasi (cat sunt surse, IPTV e in
# lista: HdsIptvSurse.leagaIndex), numai ca nu mai asteapta improspatarea zilnica: la minutul urmator radacina si grupele
# se refac din canale-<sursa>.json (fara retea) si se leaga la coada listei.
LINISTE_S = 30           # bouquets.tv neschimbat de atat: lista straina s-a terminat de scris
MAX_INCERCARI = 3        # refaceri sau legari dupa care IPTV tot lipseste (memoria plina): nu se mai incearca pana la repornire
_paza = {}


def _modul(nume):
	"""Un modul al imaginii numai daca e deja incarcat (importul sau editorul nu pot lucra fara el); nimic nou incarcat."""
	return sys.modules.get(nume)


def _listaInLucru():
	"""Importul imaginii (si listele de pe internet, prin zavorul lui) sau editorul de canale, pe televizor sau in web."""
	imp = _modul("Components.HdsImportSurse")
	try:
		if imp is not None and imp.ocupat():
			return True
	except Exception:
		pass
	ed = _modul("Components.HdsEditorCanale")
	try:
		if ed is not None and ed.sesiune() is not None:
			return True
	except Exception:
		pass
	return _editorDeschis()


def pazaListei():
	"""Pe firul enigma2, din ceasul de un minut. -> "refacere", "legare" sau "" (nimic de facut ori de asteptat)."""
	global _de_incarcat
	if not I.areSurse():
		_paza.clear()
		return ""
	with _lacat:
		if _in_lucru is not None or _coada or _de_incarcat:
			return ""
	radacina = os.path.join(I.DIRECTOR, I.BUCHET_RADACINA)
	index = os.path.join(I.DIRECTOR, "bouquets.tv")
	try:
		with open(index, encoding="utf-8", errors="surrogateescape") as f:
			legata = ('FROM BOUQUET "%s"' % I.BUCHET_RADACINA) in f.read()
		liniste = time.time() - os.stat(index).st_mtime >= LINISTE_S
	except (IOError, OSError):
		legata, liniste = False, True
	exista = os.path.isfile(radacina)
	if exista and legata:
		_paza.clear()
		return ""
	if not liniste or _listaInLucru() or not I.citesteSurse():
		return ""
	n = _paza.get("incercari", 0)
	if n >= MAX_INCERCARI:
		if not _paza.get("spus"):
			_paza["spus"] = True
			_jurnal("IPTV tot lipseste din lista dupa %d incercari: nu mai incerc pana la repornire" % n)
		return ""
	_paza["incercari"] = n + 1
	if exista:
		_jurnal("radacina IPTV nu mai era in bouquets.tv (lista de canale schimbata de alt program): legata la loc")
		with _lacat:
			_de_incarcat = True
		_pornesteCeasul()
		return "legare"
	_jurnal("radacina IPTV lipsea (lista de canale schimbata de alt program): buchetele refacute din disc")
	cere(_REFACERE)
	return "refacere"


def porneste():
	"""Memoria buchetelor; cu surse, si adresa locala si ceasul zilnic."""
	global _ceas_zilnic, _pornit, _surse_prezente
	_pornesteCeasulSurse()
	_pornit = time.monotonic()
	I.pornesteMemoriaOm()
	C.pornestePiconuri()
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
	if not I.areSurse(verifica=True):
		return
	try:
		I.reparaDrepturi()
	except OSError as e:
		_jurnal("drepturile dosarului: %s" % type(e).__name__)
	from Components import HdsIptvAdrese
	HdsIptvAdrese.porneste()
	_pornesteCeasul()
	pornesteCeasulZilnic()
	_surse_prezente = True


def _verificaSurse():
	"""Descopera si un fisier pus din afara dupa pornirea fara surse."""
	I.verificaSurseFundal()
	_aplicaPrezentaSurse()


def _aplicaPrezentaSurse():
	global _surse_prezente
	prezente = I.areSurse()
	if prezente and not _surse_prezente:
		try:
			from Components import HdsIptvAdrese
			HdsIptvAdrese.porneste()
			_pornesteCeasul()
			pornesteCeasulZilnic()
		except Exception as e:
			_jurnal("prezenta surselor: %s" % type(e).__name__)
			return
	_surse_prezente = prezente


def _pornesteCeasulSurse():
	global _ceas_surse
	if _ceas_surse is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	_ceas_surse = eTimer()
	_ceas_surse.callback.append(_verificaSurse)
	_ceas_surse.start(30000, False)


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
