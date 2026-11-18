# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Lista de canale orfana: buchetele de pe disc care nu mai sunt in bouquets.tv / bouquets.radio, puse inapoi cu un OK.

De ce (asistenta 289712, 14.11.2026): pe un receptor erau ~1.330 de userbouquet pe disc, dar bouquets.tv avea numai
Favorite si DVB-I, deci lista omului nu se mai vedea. Nucleul (lib/dvb/db.cpp, eDVBDB::loadBouquet) reface bouquets.tv
gol cand nu-l poate deschide (o lista urcata prin FTP fara el, un instalator de liste care il sterge, apoi o repornire
a interfetei); reloadBouquets pune apoi numai Favorite la loc. Fisierele buchetelor raman pe disc, nelegate.

Cum merge (regula 1f: o singura fereastra, nimic de scris):
- la pornirea interfetei, mytest.py cheama porneste(session) dupa mesajul despre Caută în meniu;
- cautarea e ieftina pe un receptor sanatos: se citesc numai cele doua radacini si numele din /etc/enigma2. Daca in
  radacina e macar un buchet al omului, nu se intreaba nimic (un buchet scos de om din lista ramane pe disc, iar
  editorul de canale il arata oricum). Numai cand radacina e (aproape) goala, adica are numai buchetele imaginii
  (Favorite, DVB-I, DAB+, IPTV, ultima scanare, locurile extensiilor), si pe disc sunt buchete nelegate, se pune
  intrebarea: Am găsit N liste de canale care nu se văd. Le pun înapoi?;
- Da: punerea inapoi trece prin editorul de canale (Components/HdsEditorCanale.py, leaga_toate si salveaza_fundal):
  copia de siguranta a listei, scrierea atomica, reincarcarea buchetelor fara repornire (eDVBDB.reloadBouquets);
- Nu sau EXIT: se tine minte multimea gasita (in hds_buchete_orfane.json, langa liste) si nu se mai intreaba pentru
  ea; se intreaba din nou numai daca alta data lipsesc alte liste. Editorul de canale (pe televizor si in web) are
  oricand butonul Pune înapoi toate;
- ordinea: cea din cea mai noua copie a listei (copiile editorului, hds-copii-canale, sau bouquets.tv.bak de la alte
  unelte) in care apar buchetele gasite; ce nu e acolo vine dupa, dupa numele fisierului;
- buchetele imaginii ramase nelegate (DAB+ cand e oprit, DVB-I, IPTV) nu se numara si nu se pun: le leaga modulele lor.

Paza buchetelor imaginii dupa o lista straina (0.7.7, pazeste mai jos): un program de liste (AutoSetting, liste urcate
prin FTP) sterge *.tv si *.radio si pune lista lui; DVB-T2 si DAB+ din satelit, Abertis 30W si DVB-I radio nu se mai
legau singure. Cand dintr-odata nu mai e legat niciunul din ele si s-a schimbat si restul listei, se leaga la loc, cu
fisierele puse inapoi din copia lor; cand omul scoate unul sau mai multe (restul listei neatins), raman scoase.

Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau dosarul prin parametri
(teste/test_orf_lista_orfana_075.py, teste/test_ast2_buchete_imagine_dupa_lista_straina_077.py)."""

import builtins
import hashlib
import json
import os
import re
import sys
import tarfile
import time

DIRECTOR = "/etc/enigma2"
FISIER_STARE = "hds_buchete_orfane.json"
DOSAR_COPII = "hds-copii-canale"
DOSAR_LOCURI = "hds_locuri"
COPII_RADACINA = ("bouquets.tv.bak", "bouquets.radio.bak", "bouquets.tv.orig", "bouquets.radio.orig",
	"bouquets.tv~", "bouquets.radio~")
ID_NOTITA = "hds_buchete_orfane"
ID_CLIENT = "hds-orfane"
MAX_COPII_CITITE = 10

# buchetele facute si legate de imagine (fiecare modul le leaga singur cand e pornit; ramase pe dinafara nu sunt pierderi)
PROPRII = frozenset(("userbouquet.favourites.tv", "userbouquet.favourites.radio",
	"userbouquet.LastScanned.tv", "userbouquet.LastScanned.radio"))
PREFIX_PROPRII = "userbouquet.hds"           # hdsdvbi, hds_dvbi, hds_dab, hds_abertis, hds_t2, hdsiptv

_FROM = re.compile(r'FROM BOUQUET "([^"/]{1,250})"')
# buchetele imaginii (urmarit, paza de mai jos): nume ASCII. Ce se propune omului (cauta, ale_omului) se judeca din
# 0.7.7 (UTF) cu regula importului si a editorului (_nume_sigur, mai jos): si numele cu diacritice, spatiu sau &, pe
# care editorul le citeste acum.
_NUME = re.compile(r"^userbouquet\.[A-Za-z0-9_.\-]{1,108}\.(tv|radio)\Z")


def _(text):
	"""Traducerea enigma2 (gettext pus in builtins la pornire); pe PC, in probe, textul romanesc."""
	tradu = getattr(builtins, "_", None)
	return tradu(text) if callable(tradu) else text


class _FormaSimpla(str):
	"""Pluralul fara Components/HdsPlural (pe PC): % pune numarul numai unde forma il are."""

	def __mod__(self, n):
		return self.replace("%d", str(n))


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural, ca in HdsEditorCanale); numele e cel stiut de xgettext."""
	try:
		try:
			from Components import HdsPlural as P
		except ImportError:
			import HdsPlural as P
		return P.ngettext(unu, multe, n)
	except Exception:
		return _FormaSimpla(unu if n == 1 else multe)


def _jurnal(text):
	print("[HdsBucheteOrfane] %s" % text)


def _citeste(cale):
	try:
		with open(cale, "rb") as f:
			return f.read().decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def trimiteri(text):
	"""Fisierele buchetelor spre care trimite un buchet (randurile #SERVICE cu FROM BOUQUET), in ordinea lor."""
	rez = []
	for rand in (text or "").splitlines():
		if rand.startswith("#SERVICE"):
			m = _FROM.search(rand)
			if m:
				rez.append(m.group(1))
	return rez


def _locuri_extensii(director):
	"""Buchetele si prefixele locurilor extensiilor (Components/HdsLocuriLista: le leaga extensia la pornire)."""
	buchete, prefixe = set(), []
	dosar = os.path.join(director, DOSAR_LOCURI)
	try:
		nume = os.listdir(dosar)
	except OSError:
		return buchete, prefixe
	for f in nume:
		if not f.endswith(".json"):
			continue
		try:
			d = json.loads(_citeste(os.path.join(dosar, f)) or "{}")
		except ValueError:
			continue
		if isinstance(d, dict):
			if isinstance(d.get("buchet"), str):
				buchete.add(d["buchet"])
			if isinstance(d.get("prefix"), str) and d["prefix"]:
				prefixe.append(d["prefix"])
	return buchete, prefixe


def e_propriu(fisier, locuri=None):
	"""True pentru buchetele imaginii si ale locurilor extensiilor (nu se numara, nu se pun inapoi de aici)."""
	if fisier in PROPRII or fisier.startswith(PREFIX_PROPRII):
		return True
	if locuri:
		buchete, prefixe = locuri
		if fisier in buchete or any(fisier.startswith(p) for p in prefixe):
			return True
	return False


def cauta(director=DIRECTOR):
	"""Ce lipseste din lista. -> dict: orfane (lista fisierelor in ordinea de pus), goale (radacinile, tv / radio, care au
	numai buchetele imaginii), aproape_gol (macar una e asa), legate_om (cate buchete ale omului sunt in radacini).
	Fiecare radacina se judeca singura: un instalator care a sters numai bouquets.tv lasa radio intreg, iar buchetele
	TV pierdute trebuie gasite oricum. Pe un receptor sanatos se opreste dupa radacini si numele din dosar."""
	locuri = _locuri_extensii(director)
	radacini = {}
	for mod in ("tv", "radio"):
		radacini[mod] = trimiteri(_citeste(os.path.join(director, "bouquets." + mod)))
	legate = set(radacini["tv"]) | set(radacini["radio"])

	def ale_omului(refs):
		return [f for f in refs if f.startswith("userbouquet.") and not e_propriu(f, locuri)]

	goale = [mod for mod in ("tv", "radio") if not ale_omului(radacini[mod])]
	rez = {"orfane": [], "goale": goale, "aproape_gol": bool(goale), "legate_om": len(set(ale_omului(legate)))}
	if not goale:
		return rez
	try:
		nume = sorted(os.listdir(director))
	except OSError:
		return rez
	candidati = [f for f in nume if _nume_sigur(f) and f not in legate and not e_propriu(f, locuri)
		and f.rsplit(".", 1)[1] in goale]
	if not candidati:
		return rez
	# un buchet trimis dintr-un buchet legat (sub-buchet) se vede; unul trimis din alt candidat vine odata cu el
	vazute, coada = set(), list(legate)
	while coada:
		f = coada.pop()
		if f in vazute:
			continue
		vazute.add(f)
		coada.extend(trimiteri(_citeste(os.path.join(director, f))))
	ramasi = [f for f in candidati if f not in vazute]
	copii = set()
	for f in ramasi:
		for t in trimiteri(_citeste(os.path.join(director, f))):
			if t != f:
				copii.add(t)
	orfane = [f for f in ramasi if f not in copii]
	rez["orfane"] = ordine(orfane, director)
	return rez


def _copii_radacina(director):
	"""Textele radacinilor din copii, de la cea mai noua: [(text bouquets.tv, text bouquets.radio)]."""
	surse = []
	for f in COPII_RADACINA:
		cale = os.path.join(director, f)
		try:
			surse.append((os.path.getmtime(cale), "fisier", cale))
		except OSError:
			pass
	dosar = os.path.join(director, DOSAR_COPII)
	try:
		for f in os.listdir(dosar):
			if f.endswith(".tar.gz"):
				cale = os.path.join(dosar, f)
				surse.append((os.path.getmtime(cale), "tar", cale))
	except OSError:
		pass
	surse.sort(key=lambda s: s[0], reverse=True)
	for _cand, fel, cale in surse[:MAX_COPII_CITITE]:
		if fel == "fisier":
			yield _citeste(cale) or ""
			continue
		try:
			with tarfile.open(cale, "r:gz") as t:
				texte = []
				for m in ("bouquets.tv", "bouquets.radio"):
					try:
						fo = t.extractfile(m)
						texte.append(fo.read().decode("utf-8", "replace") if fo else "")
					except KeyError:
						texte.append("")
				yield "\n".join(texte)
		except Exception as e:
			_jurnal("copia %s: %s" % (os.path.basename(cale), e))


def ordine(fisiere, director=DIRECTOR):
	"""Fisierele in ordinea din cea mai noua copie a listei in care apare macar unul; restul dupa nume. TV inainte de
	radio nu conteaza: fiecare intra in radacina lui."""
	fisiere = list(fisiere)
	de_pus = set(fisiere)
	if not de_pus:
		return []
	for text in _copii_radacina(director):
		inainte = [f for f in trimiteri(text) if f in de_pus]
		if inainte:
			vazute = set()
			rez = []
			for f in inainte:
				if f not in vazute:
					vazute.add(f)
					rez.append(f)
			return rez + sorted(f for f in fisiere if f not in vazute)
	return sorted(fisiere)


def ale_omului(nelegate_ids, director=DIRECTOR):
	"""Pentru butonul Pune înapoi toate din editor: din buchetele nelegate ale sesiunii raman numai userbouquet-urile
	omului (fara ale imaginii si fara sub-buchete). Ieftin (numai hds_locuri): bun pentru numarul de pe buton."""
	locuri = _locuri_extensii(director)
	return [f for f in nelegate_ids if _nume_sigur(f) and not e_propriu(f, locuri)]


def din_editor(nelegate_ids, director=DIRECTOR):
	"""ale_omului, in ordinea din copii (citeste copiile: numai la punerea inapoi, nu la fiecare desenare)."""
	return ordine(ale_omului(nelegate_ids, director), director)


# ---------------------------------------------------------------- tinut minte

def semnatura(fisiere):
	return hashlib.sha1("\n".join(sorted(fisiere)).encode("utf-8")).hexdigest()


def refuzat(fisiere, director=DIRECTOR):
	"""True daca omul a spus deja Nu pentru exact aceste liste."""
	try:
		d = json.loads(_citeste(os.path.join(director, FISIER_STARE)) or "{}")
	except ValueError:
		return False
	return isinstance(d, dict) and d.get("refuzat") == semnatura(fisiere)


def tine_minte_refuzul(fisiere, director=DIRECTOR):
	cale = os.path.join(director, FISIER_STARE)
	nou = cale + ".nou"
	try:
		with open(nou, "w") as f:
			json.dump({"refuzat": semnatura(fisiere), "cate": len(fisiere)}, f)
		os.replace(nou, cale)
		return True
	except (IOError, OSError) as e:
		_jurnal("nu s-a putut tine minte: %s" % e)
		return False


def de_propus(director=DIRECTOR):
	"""Lista de pus inapoi, daca trebuie intrebat omul acum; altfel []."""
	rez = cauta(director)
	orfane = rez["orfane"]
	if not orfane or not rez["aproape_gol"] or refuzat(orfane, director):
		return []
	return orfane


# ---------------------------------------------------------------- punerea inapoi (prin editorul de canale)

def pune_inapoi(fisiere, la_gata=None, la_eroare=None, director=DIRECTOR, sateliti=None):
	"""Deschide sesiunea editorului pe un fir, leaga buchetele intr-un singur pas, salveaza (copie, scriere,
	reincarcare). la_gata(n) / la_eroare(text) pe firul enigma2. False daca editorul e ocupat (nimic schimbat)."""
	try:
		from Components import HdsEditorCanale as E
	except ImportError:
		import HdsEditorCanale as E

	def eroare(e):
		_jurnal("punerea inapoi: %r" % (e,))
		if la_eroare is not None:
			la_eroare(str(e))

	def deschis(s):
		try:
			nelegate = set(b.id for b in s.nelegate())
			ids = [f for f in fisiere if f in nelegate]
			n = s.leaga_toate(ids)
			if not n:
				s.inchide()
				if la_gata is not None:
					la_gata(0)
				return

			def salvat(copie):
				try:
					s.inchide()
				except Exception as e:
					_jurnal("inchiderea sesiunii: %r" % (e,))
				_jurnal("puse inapoi: %d" % n)
				if la_gata is not None:
					la_gata(n)

			def nesalvat(e):
				try:
					s.inchide()
				except Exception:
					pass
				eroare(e)

			s.salveaza_fundal(salvat, nesalvat, _("înainte de punerea înapoi a listelor"))
		except Exception as e:
			try:
				s.inchide()
			except Exception:
				pass
			eroare(e)

	try:
		# id_client propriu: cu acelasi cine si id_client, deschide_fundal ar inchide pe tacute editorul deschis pe televizor
		E.deschide_fundal(E.TV, _("Liste regăsite"), deschis, eroare, id_client=ID_CLIENT, director=director,
			sateliti=sateliti)
	except E.Ocupat as e:
		_jurnal("editorul e ocupat: %s" % e)
		return False
	return True


# ---------------------------------------------------------------- fereastra de la pornire

def texte(n):
	"""(titlul, intrebarea) in limba interfetei."""
	return (_("Liste de canale care nu se văd"),
		ngettext("Am găsit %d listă de canale care nu se vede. O pun înapoi?",
			"Am găsit %d liste de canale care nu se văd. Le pun înapoi?", n) % n)


def _nepotrivit(session):
	"""True daca acum nu e momentul: standby sau un film dedesubt (ca in Components/HdsCautaSetariAnunt)."""
	try:
		from Screens import Standby
		if Standby.inStandby:
			return True
	except Exception:
		pass
	try:
		stiva = getattr(session, "dialog_stack", None) or []
		dedesubt = stiva[-1][0] if stiva else None
		if dedesubt is not None and any(c.__name__ == "MoviePlayer" for c in type(dedesubt).__mro__):
			return True
	except Exception:
		pass
	return False


def _trezitDeCeas():
	try:
		from Tools.StbHardware import getFPWasTimerWakeup
		return bool(getFPWasTimerWakeup())
	except Exception:
		return False


AMANAT = "amanat"


def _ecran(fisiere):
	from Screens.MessageBox import MessageBox
	from enigma import eTimer

	class HdsBucheteOrfane(MessageBox):
		def __init__(self, session):
			titlu, text = texte(len(fisiere))
			MessageBox.__init__(self, session, text, type=MessageBox.TYPE_YESNO, titlu=titlu)
			self._amana = _nepotrivit(session)
			self._ceas = eTimer()
			self._ceas.callback.append(self._inchideAmanat)
			self.onShown.append(self._verifica)

		def _verifica(self):
			if self._amana:
				self._ceas.start(0, True)

		def _inchideAmanat(self):
			self.close(AMANAT)

	return HdsBucheteOrfane


def _rezultat(fisiere, raspuns, director=DIRECTOR):
	"""Inchiderea ferestrei: Da = punerea inapoi; Nu / EXIT = tinut minte; amanat = intrebat la pornirea urmatoare."""
	if raspuns == AMANAT:
		_jurnal("amanat pana la pornirea urmatoare (standby sau film)")
		return
	if not raspuns:
		tine_minte_refuzul(fisiere, director)
		return

	def gata(n):
		try:
			from Tools.Notifications import AddNotification
			from Screens.MessageBox import MessageBox
			AddNotification(MessageBox, ngettext("Am pus înapoi %d listă de canale.",
				"Am pus înapoi %d liste de canale.", n) % n, type=MessageBox.TYPE_INFO, timeout=6)
		except Exception as e:
			_jurnal("mesajul de gata: %s" % e)

	def eroare(text):
		try:
			from Tools.Notifications import AddNotification
			from Screens.MessageBox import MessageBox
			AddNotification(MessageBox, _("Listele nu s-au putut pune înapoi: %s") % text, type=MessageBox.TYPE_ERROR)
		except Exception as e:
			_jurnal("mesajul de eroare: %s" % e)

	if not pune_inapoi(fisiere, gata, eroare, director):
		_jurnal("editorul de canale e deschis: intrebarea ramane pentru pornirea urmatoare")


def porneste(session, director=DIRECTOR):
	"""Pune intrebarea in coada de notificari, daca e cazul. True daca a pus-o. Nu arunca niciodata. Porneste si paza
	buchetelor imaginii (pornestePaza) si impaca intai indexul cu fisierele (impaca_indexul)."""
	pornestePaza(director)
	impaca_indexul(director)
	try:
		fisiere = de_propus(director)
		if not fisiere:
			return False
		_jurnal("liste nelegate gasite: %d" % len(fisiere))
		if _trezitDeCeas():
			_jurnal("pornit de ceas (inregistrare programata): intrebarea ramane pentru pornirea urmatoare")
			return False
		from Tools.Notifications import AddNotificationWithIDCallback
		AddNotificationWithIDCallback(lambda r: _rezultat(fisiere, r, director), ID_NOTITA, _ecran(fisiere))
		return True
	except Exception as e:
		_jurnal("verificarea la pornire: %s" % e)
		return False


# ---------------------------------------------------------------- paza buchetelor imaginii dupa o lista straina
# 0.7.7 (AST2): o lista de canale pusa de alt program sterge /etc/enigma2/*.tv si *.radio si pastreaza cel mult
# buchetele cu 'http'. IPTV-ul se pune singur la loc (Components/HdsIptvLucru.pazaListei), DVB-I TV si Radio online la
# pornirea interfetei (HdsDvbI, HdsLocuriLista); DVB-T2 si DAB+ din satelit, Abertis 30W si DVB-I radio nu, iar regula
# lor ramane: un buchet scos de om nu revine. Semnul unei liste straine: dintr-odata nu mai e legat niciunul din
# buchetele urmarite SI s-a schimbat si restul listei (lipseste si un buchet care se pune singur, sau randurile celelalte
# nu mai sunt cele de la privirea trecuta); atunci se leaga toate la loc, la coada radacinii lor (si DVB-I TV, Radio
# online, daca lipsesc), cu fisierele lipsa puse inapoi din copia tinuta aici. Omul care scoate buchete ale imaginii
# (oricare, oricate, din orice meniu) nu atinge restul listei: ramane cum a ales. Editorul de canale sau importul
# vazute lucrand intre doua priviri: tot alegerea omului.
DOSAR_PAZA = "hds_buchete_imagine"   # langa liste; nu e *.tv / *.radio, deci o lista straina nu il sterge
FISIER_PAZA = "stare.json"
INDEXURI = ("bouquets.tv", "bouquets.radio")
SINGURE = frozenset(("userbouquet.hdsiptv.tv", "userbouquet.hdsdvbi.tv"))   # se leaga singure la loc (vezi sus)
FARA_COPIE = frozenset(("userbouquet.hdsiptv.tv",))   # IPTV se reface din canalele lui, nu dintr-o copie
LINISTE_S = 30           # radacinile neschimbate de atat: lista straina s-a terminat de scris
PAS_PAZA_S = 60
MAX_COPIE = 4 * 1024 * 1024
MAX_LA_RAND = 3          # legari la loc in priviri la rand, sau erori la rand: un program care rescrie lista mereu, memoria
                         # plina; ceasul se opreste pana la repornire
_PAZA = {"ceas": None, "director": DIRECTOR, "ultima": None, "omul": False, "la_rand": 0, "erori": 0}


def urmarit(fisier):
	"""Buchetele imaginii care nu se pun singure la loc: semnul listei straine si ce se leaga la loc."""
	return fisier.startswith(PREFIX_PROPRII) and fisier not in SINGURE and bool(_NUME.match(fisier))


def randuri_legate(director=DIRECTOR):
	"""{(radacina, fisier): randul #SERVICE} pentru toate trimiterile din bouquets.tv si bouquets.radio."""
	rez = {}
	for index in INDEXURI:
		for rand in (_citeste(os.path.join(director, index)) or "").splitlines():
			if rand.startswith("#SERVICE"):
				m = _FROM.search(rand)
				if m:
					rez.setdefault((index, m.group(1)), rand.rstrip("\r\n"))
	return rez


def citeste_paza(director=DIRECTOR):
	try:
		d = json.loads(_citeste(os.path.join(director, DOSAR_PAZA, FISIER_PAZA)) or "")
	except ValueError:
		return {}
	return d if isinstance(d, dict) else {}


def _scrie_atomic(cale, octeti):
	nou = cale + ".nou"
	with open(nou, "wb") as f:
		f.write(octeti)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


def _semn(cale):
	try:
		st = os.stat(cale)
	except OSError:
		return None
	return [st.st_size, st.st_mtime_ns]


def _tine_minte(director, legate, vechi, acum):
	"""Starea de acum: randurile buchetelor urmarite si ale celor care se pun singure, si copia fiecarui fisier al lor
	(scrisa numai cand fisierul s-a schimbat). Pe disc numai cand ceva s-a schimbat. -> True daca a scris."""
	locuri = _locuri_extensii(director)[0]
	urm, sing, altele = [], [], []
	for (index, f), rand in legate.items():          # in ordinea din radacini: asa se si leaga la loc
		if urmarit(f) or f in SINGURE or f in locuri:
			if not os.path.isfile(os.path.join(director, f)):
				continue
			(urm if urmarit(f) else sing).append([index, f, rand])
		else:
			altele.append([index, f])
	altele.sort()
	dosar = os.path.join(director, DOSAR_PAZA)
	semne_vechi = vechi.get("semne") or {}
	semne = {}
	scris = False
	for _index, f, _rand in urm + sing:
		if f in FARA_COPIE or f in semne:
			continue
		cale = os.path.join(director, f)
		semn = _semn(cale)
		if semn is None or semn[0] > MAX_COPIE:
			continue
		semne[f] = semn
		copie = os.path.join(dosar, f)
		if semne_vechi.get(f) != semn or not os.path.isfile(copie):
			with open(cale, "rb") as g:
				date = g.read()
			os.makedirs(dosar, exist_ok=True)
			_scrie_atomic(copie, date)
			scris = True
	for f in semne_vechi:
		if f not in semne:
			try:
				os.remove(os.path.join(dosar, f))
				scris = True
			except OSError:
				pass
	nou = {"urmarite": urm, "singure": sing, "altele": altele, "semne": semne}
	if not scris and all(vechi.get(k) == v for k, v in nou.items()):
		return False
	nou["cand"] = acum
	os.makedirs(dosar, exist_ok=True)
	_scrie_atomic(os.path.join(dosar, FISIER_PAZA), json.dumps(nou, ensure_ascii=False, sort_keys=True).encode("utf-8"))
	return True


def _leaga_la_loc(director, randuri):
	"""randuri: [[radacina, fisier, rand]]. Fisierul lipsa vine din copie; randul lipsa se adauga la coada radacinii lui,
	cu sfarsitul de rand al ei. -> fisierele legate acum."""
	dosar = os.path.join(director, DOSAR_PAZA)
	de_adaugat = {}
	for index, f, rand in randuri:
		cale = os.path.join(director, f)
		if not os.path.isfile(cale):
			try:
				with open(os.path.join(dosar, f), "rb") as g:
					_scrie_atomic(cale, g.read())
			except (IOError, OSError):
				_jurnal("%s lipseste si nu are copie: nu se leaga" % f)
				continue
		de_adaugat.setdefault(index, []).append((f, rand))
	puse = []
	for index in INDEXURI:
		lista = de_adaugat.get(index)
		if not lista:
			continue
		cale = os.path.join(director, index)
		text = _citeste(cale)
		if text is None:
			text = "#NAME %s\n" % ("Bouquets (Radio)" if index.endswith(".radio") else "Bouquets (TV)")
		are = set(trimiteri(text))
		lipsa = [(f, rand) for f, rand in lista if f not in are]
		if not lipsa:
			continue
		capat = "\r\n" if "\r\n" in text else "\n"
		if text and not text.endswith("\n"):
			text += capat
		text += "".join(rand + capat for _f, rand in lipsa)
		_scrie_atomic(cale, text.encode("utf-8"))
		puse.extend(f for f, _rand in lipsa)
	return puse


def editorul_a_salvat_dupa(cand, director=DIRECTOR):
	"""Editorul de canale face o copie a listei la fiecare salvare (Components/HdsEditorCanale.fa_copie): e una mai noua
	decat `cand`?"""
	if cand is None:
		return False
	dosar = os.path.join(director, DOSAR_COPII)
	try:
		nume = os.listdir(dosar)
	except OSError:
		return False
	for n in nume:
		try:
			if os.stat(os.path.join(dosar, n)).st_mtime > cand:
				return True
		except OSError:
			continue
	return False


def pazeste(director=DIRECTOR, acum=None, omul=False):
	"""O privire (pe firul enigma2, din ceasul de un minut). omul: editorul sau importul au lucrat de la privirea
	trecuta. -> (rezultat, fisierele legate): "asteapta" (lista inca in scriere), "pus" (lista straina: legate la loc),
	"omul" sau "unul" (lipsa ramane, starea noua tinuta minte), "" (nimic de facut)."""
	acum = time.time() if acum is None else acum
	for index in INDEXURI:
		semn = _semn(os.path.join(director, index))
		if semn is not None and acum - semn[1] / 1e9 < LINISTE_S:
			return "asteapta", []
	legate = randuri_legate(director)
	vechi = citeste_paza(director)
	urm = [r for r in (vechi.get("urmarite") or []) if isinstance(r, list) and len(r) == 3]
	rezultat, puse = "", []
	if urm and not any((r[0], r[1]) in legate for r in urm):
		sing_lipsa = [r for r in (vechi.get("singure") or []) if isinstance(r, list) and len(r) == 3
			and (r[0], r[1]) not in legate]
		locuri = _locuri_extensii(director)[0]
		altele = sorted([i, f] for (i, f) in legate if not (urmarit(f) or f in SINGURE or f in locuri))
		restul_schimbat = bool(sing_lipsa) or ("altele" in vechi and vechi.get("altele") != altele)
		if omul:
			rezultat = "omul"
		elif not restul_schimbat:
			rezultat = "unul"
		else:
			puse = _leaga_la_loc(director, urm + [r for r in sing_lipsa if r[1] not in FARA_COPIE])
			rezultat = "pus" if puse else "unul"
			legate = randuri_legate(director)
	_tine_minte(director, legate, vechi, acum)
	return rezultat, puse


def _ocupat():
	"""Importul imaginii (si listele de pe internet, prin zavorul lui) sau editorul de canale lucreaza acum. Numai
	modulele deja incarcate: fara ele nu poate lucra niciunul."""
	imp = sys.modules.get("Components.HdsImportSurse")
	try:
		if imp is not None and imp.ocupat():
			return True
	except Exception:
		pass
	ed = sys.modules.get("Components.HdsEditorCanale")
	try:
		if ed is not None and ed.sesiune() is not None:
			return True
	except Exception:
		pass
	ib = sys.modules.get("Screens.InfoBar")
	try:
		sesiune = ib.InfoBar.instance.session
		ecrane = [sesiune.current_dialog] + [d[0] for d in sesiune.dialog_stack]
		return any(type(e).__name__.startswith("HdsEditorCanale") for e in ecrane if e is not None)
	except Exception:
		return False


def laMinut():
	"""Ceasul pazei: asteapta cat lucreaza importul sau editorul (si tine minte ca omul a lucrat), apoi pazeste."""
	director = _PAZA["director"]
	try:
		if _ocupat():
			_PAZA["omul"] = True
			return ""
		acum = time.time()
		omul = _PAZA["omul"] or editorul_a_salvat_dupa(_PAZA["ultima"], director)
		rezultat, puse = pazeste(director, acum, omul)
		_PAZA["erori"] = 0
		if rezultat == "asteapta":
			return rezultat
		_PAZA["omul"] = False
		_PAZA["ultima"] = acum
		_PAZA["la_rand"] = _PAZA["la_rand"] + 1 if rezultat == "pus" else 0
		if rezultat == "pus":
			_jurnal("lista de canale schimbata de alt program: buchetele imaginii legate la loc: %s" % ", ".join(puse))
			try:
				from enigma import eDVBDB
				eDVBDB.getInstance().reloadBouquets()
			except ImportError:
				pass
			if _PAZA["la_rand"] >= MAX_LA_RAND:
				_opresteCeasul("alt program rescrie lista in fiecare minut")
		return rezultat
	except Exception as e:
		_jurnal("paza buchetelor imaginii: %s" % e)
		_PAZA["erori"] += 1
		if _PAZA["erori"] >= MAX_LA_RAND:
			_opresteCeasul("erori la rand")
		return ""


def _opresteCeasul(motiv):
	_jurnal("paza buchetelor imaginii oprita pana la repornire: %s" % motiv)
	try:
		if _PAZA["ceas"] is not None:
			_PAZA["ceas"].stop()
	except Exception:
		pass


def pornestePaza(director=DIRECTOR):
	"""Ceasul de un minut al pazei, o singura data. Nu arunca."""
	_PAZA["director"] = director
	if _PAZA["ceas"] is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	try:
		_PAZA["ceas"] = eTimer()
		_PAZA["ceas"].callback.append(laMinut)
		_PAZA["ceas"].start(PAS_PAZA_S * 1000, False)
	except Exception as e:
		_jurnal("ceasul pazei: %s" % e)


# ---------------------------------------------------------------- randurile fara fisier din index (0.7.7, BQN)
# Importul de pana la 0.7.7 (si listele de pe internet, prin el) lua numai buchetele cu nume ASCII: cele cu diacritice,
# spatiu sau & in numele fisierului (Türksat 42E, TurkmenÄlem 52E, CiefpSettings IPTV Bosna, Amos 3 & Dror 1) ramaneau
# pe dinafara, iar randul lor ramanea in bouquets.tv, fara fisier (asistenta 365893). La fiecare pornire a interfetei
# (porneste) indexul se impaca cu fisierele, numai pentru randurile care trimit la un userbouquet fara fisier:
# - daca pe disc e un singur fisier nelegat nicaieri cu acelasi nume scris altfel (NFC sau NFD, UTF-8 citit ca cp437 sau
#   latin-1, octeti latin-1), fisierul ia numele din rand: buchetul revine in locul lui din lista;
# - altfel randul se scoate, numai cand numele lui e unul pe care importul vechi nu-l lua (semnul greselii); un rand ASCII
#   fara fisier poate fi al unui plugin care isi scrie fisierul mai tarziu, deci ramane.
# Un fisier nelegat fara rand care sa-l ceara ramane cum e: asa il lasa importul pentru lista de dinainte si editorul pentru
# ce scoate omul. Buchetele imaginii si ale locurilor extensiilor nu se ating; nici cat lucreaza importul sau editorul, nici
# cat un index e inca in scriere (LINISTE_S).
_NUME_VECHI = re.compile(r"^userbouquet\.[A-Za-z0-9_.@+-]{1,120}\.(tv|radio)$")    # importul pana la 0.7.6
# aceeasi regula ca HdsImportSurse.TIPAR_BUCHET (scrisa si aici: fisierul nu importa alte module la incarcare)
_NUME_SIGUR = re.compile('^userbouquet\\.[^\\x00-\\x1f\\x7f-\\x9f/\\\\":%\\u2028\\u2029\\ud800-\\udfff]+'
	'\\.(tv|radio)\\Z')
MAX_OCTETI_NUME = 250
_FROM_RAND = re.compile(r'FROM BOUQUET "([^"]*)"')


def _t(text):
	"""Textul bun de pus in jurnal: octetii care nu sunt UTF-8 (surogatele) scrisi cu backslashreplace, nu o eroare."""
	return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _nume_sigur(nume):
	return bool(_NUME_SIGUR.match(nume)) and len(nume.encode("utf-8")) <= MAX_OCTETI_NUME


def forma_numelui(nume):
	"""Numele adus la o singura scriere: octetii care nu sunt UTF-8 cititi ca latin-1, UTF-8 citit gresit ca cp437 sau
	latin-1 intors la loc, apoi NFC. Doua nume cu aceeasi forma sunt acelasi nume scris altfel."""
	import unicodedata
	b = nume.encode("utf-8", "surrogateescape")
	try:
		s = b.decode("utf-8")
	except UnicodeDecodeError:
		s = b.decode("latin-1")
	for cod in ("cp437", "latin-1"):
		try:
			intors = s.encode(cod).decode("utf-8")
		except (UnicodeEncodeError, UnicodeDecodeError):
			continue
		if intors != s:
			s = intors
			break
	return unicodedata.normalize("NFC", s)


def _nume_rand(rand):
	if not rand.startswith("#SERVICE"):
		return None
	m = _FROM_RAND.search(rand)
	return m.group(1) if m else None


def _exista(director, nume):
	"""Fisierul exista, cu numele din rand sau decodat ca la nucleu (%xx, lib/service/service.cpp)."""
	if os.path.isfile(os.path.join(director, nume)):
		return True
	if "%" in nume:
		decodat = re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), nume)
		return os.path.isfile(os.path.join(director, decodat))
	return False


def _legate_toate(director, radacini):
	"""Toate fisierele spre care trimite ceva legat: radacinile si, din aproape in aproape, buchetele din ele."""
	vazute, coada = set(), list(radacini)
	while coada:
		f = coada.pop()
		if f in vazute or "/" in f:
			continue
		vazute.add(f)
		coada.extend(trimiteri(_citeste(os.path.join(director, f))))
	return vazute


def impaca_indexul(director=DIRECTOR, acum=None):
	"""Randurile din bouquets.tv / bouquets.radio care trimit la un userbouquet fara fisier (vezi mai sus). -> (legate,
	scoase): numele fisierelor puse la loc (redenumite dupa rand) si ale randurilor scoase. Dupa o schimbare, lista se
	reincarca fara repornire (eDVBDB.reloadBouquets). Nu arunca."""
	try:
		return _impaca(director, time.time() if acum is None else acum)
	except Exception as e:
		_jurnal("impacarea indexului: %r" % (e,))
		return [], []


def _impaca(director, acum):
	for index in INDEXURI:
		semn = _semn(os.path.join(director, index))
		if semn is not None and acum - semn[1] / 1e9 < LINISTE_S:
			_jurnal("un index e inca in scriere: impacarea ramane pentru pornirea urmatoare")
			return [], []
	if _ocupat():
		return [], []
	locuri = _locuri_extensii(director)
	texte, lipsa, radacini = {}, [], []
	for index in INDEXURI:
		try:
			with open(os.path.join(director, index), "rb") as f:
				text = f.read().decode("utf-8", "surrogateescape")
		except (IOError, OSError):
			continue
		texte[index] = text
		for rand in text.split("\n"):
			nume = _nume_rand(rand)
			if not nume:
				continue
			radacini.append(nume)
			if (nume.startswith("userbouquet.") and "/" not in nume and not e_propriu(nume, locuri)
					and (index, nume) not in lipsa and not _exista(director, nume)):
				lipsa.append((index, nume))
	if not lipsa:
		return [], []
	# fisierele de pe disc dupa forma numelui (numai numele: ieftin)
	pe_forma = {}
	try:
		nume_disc = os.listdir(director)
	except OSError:
		nume_disc = []
	for f in nume_disc:
		if f.startswith("userbouquet.") and f.endswith((".tv", ".radio")) and not e_propriu(f, locuri):
			pe_forma.setdefault(forma_numelui(f), []).append(f)
	legate_toate = None
	de_legat, de_scos = [], {}
	for index, nume in lipsa:
		candidati = [f for f in pe_forma.get(forma_numelui(nume), []) if f != nume
			and os.path.isfile(os.path.join(director, f))]
		if candidati and legate_toate is None:
			legate_toate = _legate_toate(director, radacini)
		candidati = [f for f in candidati if f not in (legate_toate or ())]
		if len(candidati) == 1 and _nume_sigur(nume):
			de_legat.append((candidati[0], nume))
		elif len(candidati) > 1:
			_jurnal("%s: mai multe fisiere cu acelasi nume scris altfel (%s), randul ramane" % (_t(nume), _t(", ".join(candidati))))
		elif not _NUME_VECHI.match(nume):
			de_scos.setdefault(index, set()).add(nume)
	legate = []
	for vechi, nou in de_legat:
		if nou in legate or os.path.exists(os.path.join(director, nou)):
			continue
		try:
			os.rename(os.path.join(director, vechi), os.path.join(director, nou))
			legate.append(nou)
		except OSError as e:
			_jurnal("%s nu s-a putut pune la loc: %s" % (_t(nou), _t(str(e))))
	scoase = []
	for index, nume_scoase in de_scos.items():
		randuri = texte[index].split("\n")
		ramase = [r for r in randuri if _nume_rand(r) not in nume_scoase]
		if len(ramase) == len(randuri):
			continue
		try:
			_scrie_atomic(os.path.join(director, index), "\n".join(ramase).encode("utf-8", "surrogateescape"))
			scoase.extend(sorted(nume_scoase))
		except (IOError, OSError) as e:
			_jurnal("%s: %s" % (index, e))
	if legate:
		_jurnal("buchete puse la loc (fisierul avea numele scris altfel): %s" % _t(", ".join(legate)))
	if scoase:
		_jurnal("randuri scoase din index (buchetul nu are fisier, importul vechi nu-l lua): %s" % _t(", ".join(scoase)))
	if legate or scoase:
		try:
			from enigma import eDVBDB
			eDVBDB.getInstance().reloadBouquets()
		except ImportError:
			pass
	return legate, scoase
