# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPortal.py: tasta PORTAL (KEY_WWW) din bara si starea HbbTV a canalului care ruleaza.
#
# 0.2.8: cand canalul are in AIT o aplicatie HbbTV de pornit, tasta o deschide DIRECT, ca
# ROSU (Components/HdsHbbtvPornire.apasaRosu, cu aceleasi mesaje: timeshift, inregistrare, memorie, carusel). Altfel
# (AIT-ul inca necitit, canal fara HbbTV, fara canal) tasta deschide lista extensiilor (Screens/PluginBrowser.py:
# managerul HdsExtensii pe fila extensiilor instalate), fara nicio intrebare, si pune peste ea, pentru TIMP_MESAJ_S
# secunde, ce stie receptorul despre HbbTV pe canalul care ruleaza. Mesajul se inchide singur (sau cu OK / EXIT) si
# lasa lista pe ecran. Cu HbbTV oprit din setari (config.plugins.hdsnavigator.hbbtv) nu porneste nicio aplicatie:
# lista si mesajul text_oprit().
#
# DE UNDE SE STIE: aceeasi sursa ca afisajul HbbTV din a doua bara si pagina web /piste,
# Components/Converter/HdsCommon.hbbtv_semnalat, pe acelasi HdsCommon.Reader: un nucleu care citeste AIT-ul
# (sHBBTVUrl) raspunde el; nucleul imaginii nu il citeste (lib/dvb/pmt.cpp nu parcurge stream_type 0x05 / descriptorul
# 0x6F), deci raspunsul vine din baza pistelor (Components/HdsPisteCanale.py, „hb”), scris din PMT-ul brut la
# „Actualizează pistele canalelor” sau cu treapta „Tot transponderul” a culegerii. Tasta nu deschide ea un filtru de
# demux: citirea bruta din Python nu e probata pe HiSilicon (blocari in dvb_demux_release in istoricul receptorului).
# Cand nucleul va spune dupa PMT daca exista AIT (stream_type 0x05 cu descriptorul 0x6F), hbbtv_semnalat il citeste
# intai, iar „nu se știe” ramane numai pana la citirea PMT-ului canalului.
#
# STARILE (stare_hbbtv):
#   STARE_DA          canalul anunta HbbTV (AIT in PMT sau URL-ul de la nucleu);
#   STARE_NU          PMT-ul canalului a fost citit si nu are AIT;
#   STARE_NU_STIU     canal DVB al carui PMT brut nu s-a citit inca;
#   STARE_FARA_DVB    serviciul nu e un canal DVB cu transponder in referinta (flux prin internet, fisier);
#   STARE_FARA_CANAL  nu ruleaza nimic (atunci tasta deschide numai lista).
# Aceleasi stari si aceleasi texte in pagina web: HdsWebControl/portal_web.py (GET /api/portal).
#
# FIRUL: totul ruleaza pe firul enigma2 la apasarea tastei: o citire din memoria bazei (un rand desfacut) si doua
# ecrane deschise, fara disc si fara retea. Partea de sus nu importa nimic din enigma2 (HdsCommon, navigatia si
# ecranele se iau tarziu), deci modulul se probeaza pe PC
# (test_portal.py).

from __future__ import absolute_import

STARE_DA = "da"
STARE_NU = "nu"
STARE_NU_STIU = "nu_stiu"
STARE_FARA_DVB = "fara_dvb"
STARE_FARA_CANAL = "fara_canal"
STARI = (STARE_DA, STARE_NU, STARE_NU_STIU, STARE_FARA_DVB, STARE_FARA_CANAL)

TIMP_MESAJ_S = 5
APLICATIE = "aplicatie"   # apasaPortal: aplicatia HbbTV a canalului s-a deschis (sau ROSU a spus de ce nu)


def _(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


def _jurnal(text):
	print("[HdsPortal] %s" % text)


def _hc(C=None):
	if C is not None:
		return C
	from Components.Converter import HdsCommon
	return HdsCommon


def _navigatia(nav=None):
	if nav is not None:
		return nav
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


class _Sursa(object):
	"""Ce asteapta HdsCommon.Reader de la o sursa: serviciul si referinta lui (Reader.sref o ia de aici cand
	sServiceref vine gol)."""
	__slots__ = ("service", "serviceref")

	def __init__(self, service, serviceref):
		self.service = service
		self.serviceref = serviceref


def serviciul(nav=None):
	"""(serviciul care ruleaza, referinta lui ca obiect, referinta ca text); None / None / "" cand lipsesc."""
	nav = _navigatia(nav)
	if nav is None:
		return None, None, ""
	try:
		service = nav.getCurrentService()
	except Exception:
		service = None
	try:
		ref = nav.getCurrentlyPlayingServiceReference()
	except Exception:
		ref = None
	text = ""
	if ref is not None:
		try:
			text = ref.toString() or ""
		except Exception:
			text = ""
	return service, ref, text


def este_dvb(ref_text):
	"""True pentru un canal DVB (satelit, cablu, antena): tipul 1, SID si transponder in referinta, fara cale. Aceeasi
	regula ca cheia bazei pistelor (HdsPisteCanale.transponder_din_ref)."""
	parti = (ref_text or "").split(":")
	if len(parti) < 10 or (len(parti) > 10 and parti[10]):
		return False
	try:
		if int(parti[0]) != 1:
			return False
		sid, tsid, onid, ns = [int(p or "0", 16) for p in parti[3:7]]
	except ValueError:
		return False
	return bool(sid and (tsid or onid or ns))


def stare_hbbtv(nav=None, C=None):
	"""Starea HbbTV a canalului care ruleaza -> (stare, hbbtv): hbbtv e True / False / None, ca la
	HdsCommon.hbbtv_semnalat. O eroare de citire da „nu se stie”, nu „nu”."""
	service, ref, ref_text = serviciul(nav)
	if service is None:
		return STARE_FARA_CANAL, None
	try:
		C = _hc(C)
		v = C.hbbtv_semnalat(C.Reader(_Sursa(service, ref), None))
	except Exception as e:
		_jurnal("starea HbbTV: %s" % e)
		v = None
	if v is True:
		return STARE_DA, True
	if v is False:
		return STARE_NU, False
	if ref_text and not este_dvb(ref_text):
		return STARE_FARA_DVB, None
	return STARE_NU_STIU, None


def text(stare):
	"""Mesajul de pe televizor (si din pagina web) pentru o stare."""
	if stare == STARE_DA:
		return _("Canalul are HbbTV. Apasă ROȘU sau Portal ca să pornești aplicația.")
	if stare == STARE_NU:
		return _("Canalul acesta nu are HbbTV.")
	if stare == STARE_FARA_DVB:
		return _("HbbTV există numai pe canalele din satelit, cablu sau antenă.")
	if stare == STARE_FARA_CANAL:
		return _("Nu rulează niciun canal.")
	# numai fraza simpla: caseta de mesaj nu are un al doilea text mai mic, iar citirea pistelor din lista de canale
	# („Actualizează pistele canalelor”) nu e inca probata pe receptor, deci mesajul nu trimite pe nimeni acolo
	return _("Încă nu știu dacă acest canal are HbbTV.")


def text_scurt(stare):
	"""Valoarea scurta pentru randul „HbbTV” din panoul web („Acum pe receptor”), cu litera mica, ca valorile vecine
	din panou („da”, „nu”)."""
	if stare == STARE_DA:
		return _("da")
	if stare == STARE_NU:
		return _("nu are")
	if stare == STARE_FARA_DVB:
		return _("numai pe satelit, cablu sau antenă")
	if stare == STARE_FARA_CANAL:
		return "-"
	return _("încă nu se știe")


def text_oprit():
	return _("HbbTV e oprit din setări (Setări navigator web).")


def hbbtv_pornit():
	"""Setarea principala „HbbTV” (Components/HdsHbbtv.hbbtv_pornit); fara ea, oprit."""
	try:
		try:
			from Components import HdsHbbtv as H
		except ImportError:
			import HdsHbbtv as H
		return H.hbbtv_pornit()
	except Exception:
		return False


def _porneste_aplicatia(ecran):
	"""Aplicatia HbbTV a canalului, ca ROSU: 1 daca a deschis-o (sau a spus de ce nu se poate), 0 cand canalul nu are
	acum o aplicatie de pornit (AIT necitit sau fara aplicatie)."""
	from Components import HdsHbbtvPornire
	return HdsHbbtvPornire.apasaRosu(ecran)


def apasaPortal(ecran, nav=None, C=None, porneste=None, pornit=None):
	"""Tasta PORTAL din bara: aplicatia HbbTV a canalului, daca are una de pornit (porneste, implicit
	_porneste_aplicatia; intoarce APLICATIE); altfel lista extensiilor, fara intrebare, apoi peste ea mesajul HbbTV al
	canalului, care se inchide singur dupa TIMP_MESAJ_S secunde. Fara canal, numai lista. Session.open prinde singur o
	cadere a ecranului (handleScreenCrash), deci mesajul apare si cand lista nu se poate deschide. pornit: setarea
	principala HbbTV (implicit hbbtv_pornit())."""
	session = ecran.session
	cu_hbbtv = hbbtv_pornit() if pornit is None else bool(pornit)
	if cu_hbbtv:
		try:
			if (porneste or _porneste_aplicatia)(ecran):
				return APLICATIE
		except Exception as e:
			_jurnal("aplicatia HbbTV: %s" % e)
	stare, _hb = stare_hbbtv(nav, C)
	try:
		from Screens.PluginBrowser import PluginBrowser
		session.open(PluginBrowser)
	except Exception as e:
		_jurnal("lista extensiilor: %s" % e)
	if stare == STARE_FARA_CANAL:
		return stare
	from Screens.MessageBox import MessageBox
	session.open(MessageBox, text(stare) if cu_hbbtv else text_oprit(), MessageBox.TYPE_INFO, timeout=TIMP_MESAJ_S)
	return stare
