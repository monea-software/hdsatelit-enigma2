# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Renaming a channel directly from the channel list (0.8.0, FX1; AS203, 25.11.2026: the rename was only in
MENU > Editor > MENU on a channel). ChannelContextMenu > "Redenumește canalul": one keyboard, OK, done. The web side
is the channel editor (/editor-canale, the same redenumeste / redenumeste_serviciu).

- In a user bouquet (userbouquet file): the name changes only in that bouquet (Sesiune.redenumeste, #DESCRIPTION),
  as "Numai în acest buchet" in the editor.
- In the image's own lists (satellites, providers, all channels): the receiver list name (Sesiune.redenumeste_serviciu,
  lamedb, with the flag that keeps it across scans), as "Peste tot" in the editor.
- Opened on a thread like Components/HdsRedenumireBuchet.py: deschide_fundal, save with backup and reload without
  restart, then close; a busy editor gives its own text.

No enigma2 import at load time: the PC test passes a fake editor via `editor=` (teste/test_fx1_redenumire_canal_080.py)."""

import builtins

from Components.HdsRedenumireBuchet import fisier_din_ref

# own id_client: with the same one, deschide_fundal would silently close the editor open on the TV
ID_CLIENT = "hds-redenumire-canal"


def _(text):
	tradu = getattr(builtins, "_", None)
	return tradu(text) if callable(tradu) else text


def _jurnal(text):
	print("[HdsRedenumireCanal] %s" % text)


def cheie_ref(ref_text):
	"""Comparable form of a service reference: the first ten fields in lower case, plus the stream address of an
	internet channel (the 11th field); the name after it does not count."""
	parti = (ref_text or "").split(":")
	baza = [p.lower() for p in parti[:10]]
	adresa = parti[10] if len(parti) > 10 else ""
	return ":".join(baza + [adresa])


def _editor():
	try:
		from Components import HdsEditorCanale as E
	except ImportError:
		import HdsEditorCanale as E
	return E


def _mesaj(e):
	f = getattr(e, "mesaj", None)
	if callable(f):
		try:
			return f() or ""
		except Exception:
			pass
	return str(e)


def redenumeste(ref_text, radacina_text, nume, la_gata=None, la_eroare=None, editor=None, director=None, sateliti=None):
	"""New name for channel `ref_text`, seen in the list whose root is `radacina_text`. la_gata(name) after saving or
	la_eroare(text), on the enigma2 thread. -> True when started."""
	E = editor if editor is not None else _editor()
	nume = (nume or "").strip()
	buchet = fisier_din_ref(radacina_text)

	def eroare(e):
		text = e if isinstance(e, str) else _mesaj(e)
		_jurnal("redenumirea %s: %r" % (ref_text, text))
		if la_eroare is not None:
			la_eroare(text)

	if not nume:
		eroare(_("Numele nu poate fi gol."))
		return False
	if not ref_text:
		eroare(_("Nu e ales niciun rând."))
		return False

	def inchide(s):
		try:
			s.inchide()
		except Exception as e:
			_jurnal("inchiderea sesiunii: %r" % (e,))

	def deschis(s):
		try:
			if buchet:
				cheie = cheie_ref(ref_text)
				indice = next((i for i, x in enumerate(s.intrari(buchet)) if cheie_ref(x.ref) == cheie), None)
				if indice is None:
					raise E.Eroare(_("Canalul nu mai există în lista receptorului."))
				rez = s.redenumeste(buchet, indice, nume)
			else:
				rez = s.redenumeste_serviciu(ref_text, nume)

			def salvat(copie):
				inchide(s)
				_jurnal("redenumit: %s" % ref_text)
				if la_gata is not None:
					la_gata(rez)

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
		E.deschide_fundal(E.TV, _("Redenumește canalul"), deschis, eroare, **k)
	except Exception as e:
		eroare(e)
		return False
	return True
