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

Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau dosarul prin parametri
(teste/test_orf_lista_orfana_075.py)."""

import builtins
import hashlib
import json
import os
import re
import tarfile

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

_FROM = re.compile(r'FROM BOUQUET "([^"/]{1,200})"')
# acelasi nume ca editorul (HdsEditorCanaleDate._NUME_FISIER): ce nu poate citi editorul nu se propune
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
	candidati = [f for f in nume if _NUME.match(f) and f not in legate and not e_propriu(f, locuri)
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
	return [f for f in nelegate_ids if _NUME.match(f) and not e_propriu(f, locuri)]


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
	"""Pune intrebarea in coada de notificari, daca e cazul. True daca a pus-o. Nu arunca niciodata."""
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
