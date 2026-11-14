# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Un mesaj scurt, o singura data, despre „Caută în meniu” (Screens/HdsCautaSetari.py).

Eduard, 13.11.2026 21:36: oamenii nu gasesc setarile (de pilda subtitrarile), fiindca meniul e altfel decat la alte
imagini; la pornire imaginea trebuie sa le spuna ca exista cautarea setarilor.

Cum merge:
- mytest.py cheama porneste(session) imediat dupa „Ce e nou” (Screens/HdsJurnalVersiuni.arata_la_pornire), deci
  mesajul intra in coada de notificari dupa el si se deschide dupa asistentul de pornire, peste bara TV, nu peste el.
- Se tine minte in config.hdsatelit.cautaSetariAnuntat (Da/Nu). Cheia nu exista inainte de 0.7.5, deci mesajul apare o
  data la prima pornire dupa actualizarea la 0.7.5 si o data la prima pornire dupa o scriere noua a receptorului
  (setari noi); dupa OK sau EXIT nu mai apare. Fara setare de oprit si fara intrebare: omul apasa numai OK.
- Coada se goleste numai cand bara TV e activa: in standby mesajul asteapta trezirea. Paza in plus: daca la aratare
  receptorul e in standby sau dedesubt e un film, mesajul se inchide singur, nemarcat, si revine la pornirea urmatoare.
- Cand receptorul a pornit singur, de la ceas (o inregistrare programata), mesajul nu se pune deloc: fara timp de
  inchidere, ar tine coada pe loc si cererea de standby de dupa inregistrare ar astepta un OK. Apare la urmatoarea
  pornire facuta de om.
- Drumul din mesaj se scrie din numele traduse (MENU > Caută în meniu, primul rand din orice meniu, Screens/Menu.py),
  deci e corect in orice limba.
Pornirea receptorului nu depinde de modul: orice eroare ramane doar in jurnal."""

ID_NOTITA = 'hds_cauta_setari_anunt'
# ce intoarce mesajul cand s-a inchis singur (standby sau film dedesubt): nu se marcheaza ca vazut
AMANAT = 'amanat'


import builtins


def _(text):
	"""Traducerea enigma2 (gettext pus in builtins la pornire); pe PC, in probe, textul romanesc."""
	tradu = getattr(builtins, '_', None)
	return tradu(text) if callable(tradu) else text


def _jurnal(text):
	print('[HdsCautaSetariAnunt] %s' % text)


def _setare():
	"""config.hdsatelit.cautaSetariAnuntat, creata la prima cerere (ca in Components/HdsJurnalVersiuni._config_jurnal).
	None in afara interfetei (PC, teste)."""
	try:
		from Components.config import config, ConfigSubsection, ConfigYesNo
	except Exception:
		return None
	try:
		# hasattr() nu e sigur pe ConfigSubsection (arunca KeyError, nu AttributeError): se cauta in content.items
		if 'hdsatelit' not in config.content.items:
			config.hdsatelit = ConfigSubsection()
		if 'cautaSetariAnuntat' not in config.hdsatelit.content.items:
			config.hdsatelit.cautaSetariAnuntat = ConfigYesNo(default=False)
		return config.hdsatelit.cautaSetariAnuntat
	except Exception:
		return None


def drum():
	"""Drumul spre cautare, cu numele tradus: „MENU > Caută în meniu” (primul rand din orice meniu)."""
	return ' > '.join(('MENU', _('Caută în meniu')))


def texte():
	"""(titlul, textul, randul cu drumul) ale mesajului, in limba interfetei."""
	return (_('Nu găsești o setare?'),
		_('Scrie numele ei în „Caută în meniu”, de exemplu „subtitrări”, și ajungi direct la ea.'),
		_('%s (primul rând)') % drum())


def de_aratat(setare=None):
	"""True cat timp omul n-a vazut inca mesajul."""
	if setare is None:
		setare = _setare()
	if setare is None:
		return False
	try:
		return not setare.value
	except Exception:
		return False


def marcheaza(rezultat=None, setare=None):
	"""Chemata la inchiderea mesajului: il tine minte ca vazut (in afara de inchiderea singura, AMANAT)."""
	if rezultat == AMANAT:
		_jurnal('amanat pana la pornirea urmatoare (standby sau film)')
		return False
	if setare is None:
		setare = _setare()
	if setare is None:
		return False
	try:
		setare.value = True
		setare.save()
		# fara configfile.save(), o scoatere din priza ar arata mesajul a doua oara
		from Components.config import configfile
		configfile.save()
		return True
	except Exception as e:
		_jurnal('nu s-a putut tine minte: %s' % e)
		return False


def _nepotrivit(session):
	"""True daca acum nu e momentul: receptorul e in standby sau dedesubt e un film (playerul)."""
	try:
		from Screens import Standby
		if Standby.inStandby:
			return True
	except Exception:
		pass
	try:
		stiva = getattr(session, 'dialog_stack', None) or []
		dedesubt = stiva[-1][0] if stiva else None
		if dedesubt is not None and any(c.__name__ == 'MoviePlayer' for c in type(dedesubt).__mro__):
			return True
	except Exception:
		pass
	return False


def _ecran():
	"""Clasa mesajului: fereastra obisnuita a temei (MessageBox, felul informare), cu paza de standby si film."""
	from Screens.MessageBox import MessageBox
	from enigma import eTimer

	class HdsCautaSetariAnunt(MessageBox):
		def __init__(self, session):
			titlu, text, rand = texte()
			MessageBox.__init__(self, session, text, type=MessageBox.TYPE_INFO, titlu=titlu, puncte=[rand])
			self._amana = _nepotrivit(session)
			self._ceas = eTimer()
			self._ceas.callback.append(self._inchideAmanat)
			self.onShown.append(self._verifica)

		def _verifica(self):
			if self._amana:
				self._ceas.start(0, True)

		def _inchideAmanat(self):
			self.close(AMANAT)

	return HdsCautaSetariAnunt


def _trezitDeCeas():
	"""True cand receptorul a pornit singur, de la ceas (citirea pastrata de Navigation in Tools.StbHardware)."""
	try:
		from Tools.StbHardware import getFPWasTimerWakeup
		return bool(getFPWasTimerWakeup())
	except Exception:
		return False


def porneste(session):
	"""Pune mesajul in coada de notificari, daca omul nu l-a vazut inca. True daca l-a pus. Nu arunca niciodata."""
	try:
		if not de_aratat():
			return False
		if _trezitDeCeas():
			_jurnal('pornit de ceas (inregistrare programata): mesajul ramane pentru pornirea urmatoare')
			return False
		from Tools.Notifications import AddNotificationWithIDCallback
		AddNotificationWithIDCallback(marcheaza, ID_NOTITA, _ecran())
		return True
	except Exception as e:
		_jurnal('aratarea la pornire: %s' % e)
		return False
