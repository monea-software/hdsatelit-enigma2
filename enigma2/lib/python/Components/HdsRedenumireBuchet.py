# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Redenumirea unui buchet direct din lista buchetelor (0.7.6, RBC).

De ce (Pete29871, LinuxSat 164155 #970561, Octagon SF8008, 15.11.2026): redenumirea unui buchet era numai in
MENU > Editor > MENU pe buchet > Redenumește buchetul, greu de gasit. Acum: in lista buchetelor, MENU pe buchet >
Redenumește buchetul (Screens/ChannelSelection.py, ChannelContextMenu), tastatura cu numele de acum, OK, gata. In web:
butonul "Redenumește buchetul" de langa lista aleasa pe /canale (HdsWebControl/canale_web.py).

Cum merge (regula 1f: o tastatura, nimic de confirmat; numele nou vazut in lista e confirmarea):
- aceeasi functie ca editorul de canale: Components/HdsEditorCanale.Sesiune.redenumeste_buchet (numele curatat,
  semnul TV/Radio pastrat, Favorite ca in editor), deschisa pe un fir cu deschide_fundal, apoi salveaza_fundal
  (copia de siguranta, scrierea atomica, reincarcarea buchetelor fara repornire) si inchide; ca
  Components/HdsBucheteOrfane.pune_inapoi;
- numele neschimbat: nimic de salvat, sesiunea se inchide;
- buchetele refacute de alte module ale imaginii (automat): intrarea nu se arata, web-ul spune de ce;
- lista deschisa in editor (interfata web) sau editorul ocupat: textul editorului (Ocupat) ajunge la om, nimic
  schimbat.

Fisierul nu importa nimic din enigma2 la incarcare: proba de pe PC da un editor fals prin `editor=`
(teste/test_rbc_redenumire_buchet_075.py)."""

import builtins
import re

# id_client propriu: cu acelasi cine si id_client, deschide_fundal ar inchide pe tacute editorul deschis pe televizor
ID_CLIENT = "hds-redenumire-buchet"
_FROM = re.compile(r'FROM BOUQUET "([^"/]{1,250})"')
# acelasi nume ca editorul (HdsEditorCanaleDate._NUME_FISIER) si importul (HdsImportSurse.TIPAR_BUCHET, 0.7.7): numai
# buchetele omului, din fisiere userbouquet, si cu diacritice, spatiu sau & in nume (scrisa si aici: fisierul nu
# importa alte module la incarcare)
MAX_OCTETI_NUME = 250
_TIPAR_NUME = re.compile('^userbouquet\\.[^\\x00-\\x1f\\x7f-\\x9f/\\\\":%\\u2028\\u2029\\ud800-\\udfff]+'
	'\\.(tv|radio)\\Z')


class _NumeBuchet(object):
	"""_NUME: match(nume) ca la un tipar re (None sau potrivirea), cu lungimea numarata in octeti UTF-8."""

	def match(self, nume):
		if not isinstance(nume, str):
			return None
		m = _TIPAR_NUME.match(nume)
		if m is None or len(nume.encode("utf-8")) > MAX_OCTETI_NUME:
			return None
		return m


_NUME = _NumeBuchet()

# ultima redenumire (pentru pagina web, care intreaba din nou pana e gata): fel = lucreaza | gata | eroare
STARE = {"fel": "", "buchet": "", "nume": "", "mesaj": ""}


def _(text):
	"""Traducerea enigma2 (gettext pus in builtins la pornire); pe PC, in probe, textul romanesc."""
	tradu = getattr(builtins, "_", None)
	return tradu(text) if callable(tradu) else text


def _jurnal(text):
	print("[HdsRedenumireBuchet] %s" % text)


def fisier_din_ref(ref_text):
	"""Fisierul buchetului (userbouquet.x.tv) din referinta lui din lista buchetelor, sau "" pentru orice altceva
	(radacina bouquets.tv, sateliti, furnizori, randurile puse de imagine)."""
	m = _FROM.search(ref_text or "")
	if not m:
		return ""
	f = m.group(1)
	return f if _NUME.match(f) else ""


def _mesaj(e):
	f = getattr(e, "mesaj", None)
	if callable(f):
		try:
			return f() or ""
		except Exception:
			pass
	return str(e)


def _editor():
	try:
		from Components import HdsEditorCanale as E
	except ImportError:
		import HdsEditorCanale as E
	return E


def automat(fisier, editor=None):
	"""Textul editorului cand buchetul e refacut de alt modul al imaginii (DAB+ / DVB-T2, DVB-I, ultima scanare:
	HdsEditorCanale.buchet_automat), altfel "". Un nume nou s-ar pierde acolo: intrarea nu se arata, iar web-ul il spune."""
	try:
		E = editor if editor is not None else _editor()
		f = getattr(E, "buchet_automat", None)
		return (f(fisier) or "") if f is not None else ""
	except Exception as e:
		_jurnal("buchet_automat: %r" % (e,))
		return ""


def redenumeste(fisier, nume, la_gata=None, la_eroare=None, editor=None, director=None, sateliti=None):
	"""Numele nou al buchetului `fisier`, prin editorul de canale, pe un fir. la_gata(nume) dupa salvare (nume = None
	cand numele era acelasi si nu s-a scris nimic) sau la_eroare(text), pe firul enigma2. -> True daca a pornit, False
	daca editorul e ocupat sau cererea nu e buna (la_eroare a primit deja textul)."""
	E = editor if editor is not None else _editor()
	nume = (nume or "").strip()
	STARE.update(fel="lucreaza", buchet=fisier or "", nume=nume, mesaj="")

	def eroare(e):
		text = e if isinstance(e, str) else _mesaj(e)
		_jurnal("redenumirea %s: %r" % (fisier, text))
		STARE.update(fel="eroare", mesaj=text)
		if la_eroare is not None:
			la_eroare(text)

	def gata(rez):
		STARE.update(fel="gata", nume=rez or nume, mesaj="")
		if la_gata is not None:
			la_gata(rez)

	if not _NUME.match(fisier or ""):
		eroare(_("Buchetul nu e bun."))
		return False
	if not nume:
		eroare(_("Numele nu poate fi gol."))
		return False

	def inchide(s):
		try:
			s.inchide()
		except Exception as e:
			_jurnal("inchiderea sesiunii: %r" % (e,))

	def deschis(s):
		try:
			# buchetul sters intre timp: Eroare("Buchetul nu mai există.") din editor
			rez = s.redenumeste_buchet(fisier, nume)
			if rez is None:
				inchide(s)
				gata(None)
				return

			def salvat(copie):
				inchide(s)
				_jurnal("redenumit: %s" % fisier)
				gata(rez)

			def nesalvat(e):
				inchide(s)
				eroare(e)

			s.salveaza_fundal(salvat, nesalvat)
		except Exception as e:
			inchide(s)
			eroare(e)

	k = {"id_client": ID_CLIENT}
	if director is not None:
		k["director"] = director
	if sateliti is not None:
		k["sateliti"] = sateliti
	try:
		E.deschide_fundal(E.TV, _("Redenumește buchetul"), deschis, eroare, **k)
	except Exception as e:
		eroare(e)
		return False
	return True
