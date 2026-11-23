# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDeschidereAmanata.py: un plugin strain care deschide un ecran chiar cand televizorul e intre doua ferestre nu mai cade;
# ecranul se deschide dupa o clipa, cand e iar un ecran modal deasupra.
#
# De ce (TODO 15.11 08:15, Vu+ Solo 4K, NeoBoot v10, agentul NBM, runda-0013): NeoBoot arata o fereastra "BOOTING" cand omul
# alege o imagine si porneste schimbarea; cand schimbarea iese cu eroare, pluginul inchide fereastra si, in acelasi apel,
# deschide mesajul cu eroarea. Session.close face execEnd pe loc (ecranul de dedesubt revine abia la processDelay, din
# ceasul de 0 ms), deci Session.open cadea cu "modal open are allowed only from a screen which is modal!": omul nu vedea
# de ce n-a pornit imaginea aleasa, iar raportul pluginului pleca la noi. Aceeasi cadere o are un plugin care deschide alt
# ecran din constructorul ecranului lui (atunci nu se deschidea nici ecranul pluginului).
#
# Ce face: Session.open si Session.openWithCallback intreaba deAmanat() numai cand ar fi aruncat eroarea (dialog_stack
# plin si in_exec fals). Daca apelul vine direct dintr-un plugin strain (primul cadru din afara lui mytest.py, de
# boundFunction si de codul rulat din text e in Plugins/Extensions sau Plugins/SystemPlugins si nu e al imaginii,
# HdsPluginExtern.pluginDinCale), deschiderea intra in
# coada si open intoarce None (ca la un ecran care nu s-a putut construi). Un ceas o deschide cand sesiunea are iar un ecran
# in executie si nicio inchidere in asteptare (in_exec si delay_timer oprit), cu callback-ul pluginului, in ordinea cererilor.
# Dupa INCERCARI pasi fara ecran modal, cererea trece in Notifications (se arata cand revine bara canalului), nu se pierde.
#
# Codul imaginii nu trece pe aici: el primeste eroarea ca inainte (de pilda pagina web de cautare o prinde si spune omului
# sa incerce din nou). Pluginul nu se schimba.

from __future__ import print_function

import os
import sys
from traceback import print_exc

PAS_MS = 50
INCERCARI = 100		# 5 s
# cadrele prin care se trece mai departe: sesiunea, modulul acesta si boundFunction (pluginurile cheama des
# boundFunction(self.session.open, Ecran, ...), care doar paseaza apelul)
FISIERE_SESIUNE = ("mytest.py", "mytest.pyc", "StartEnigma.py", "StartEnigma.pyc", "HdsDeschidereAmanata.py",
	"HdsDeschidereAmanata.pyc", "BoundFunction.py", "BoundFunction.pyc")
# cod rulat din text (exec): NeoBoot isi ruleaza plugin.py asa ("<string>" in stiva); se cauta mai departe cine l-a chemat,
# iar daca nu se gaseste niciun fisier de plugin, eroarea ramane ca inainte
FARA_FISIER = ("<string>",)

_coada = []
_ceas = [None]


def _jurnal(text):
	print("[HdsDeschidereAmanata] %s" % text)


def pluginApelant(cadru):
	"""(fel, nume) al pluginului strain din care vine apelul (primul cadru din afara sesiunii), sau None"""
	while cadru is not None:
		cale = cadru.f_code.co_filename or ""
		if cale not in FARA_FISIER and os.path.basename(cale.replace("\\", "/")) not in FISIERE_SESIUNE:
			try:
				from Components import HdsPluginExtern
				return HdsPluginExtern.pluginDinCale(cale)
			except Exception as e:
				_jurnal("pluginul apelant: %r" % (e,))
				return None
		cadru = cadru.f_back
	return None


def deAmanat(sesiune):
	"""numele pluginului strain care a cerut deschiderea, daca ea se poate amana; altfel None (eroarea ramane)"""
	try:
		p = pluginApelant(sys._getframe(1))
	except Exception as e:
		_jurnal("deAmanat: %r" % (e,))
		return None
	return p[1] if p else None


def numeEcran(screen):
	return getattr(screen, "__name__", None) or str(screen)


def eMesaj(screen):
	"""True pentru MessageBox si ecranele facute din el (numai textul lor se scrie in jurnal: alte ecrane primesc in
	text= de pilda valoarea de acum a unui camp, care poate fi o parola)"""
	return any(getattr(c, "__name__", "") == "MessageBox" for c in getattr(screen, "__mro__", ()))


def textCerut(screen, arguments, kwargs):
	"""Textul unui MessageBox cerut, pe un rand, intreg (REGULA 0, ASI7: si parolele, adresele si datele omului);
	"" la alt ecran, fara text sau cand curatarea nu se poate face. HDSatelit 0.7.7 (NBT, TODO 15.11 10:30 NBM): NeoBoot v10
	pune aici ultimul rand scris de switch_image.py cand schimbarea imaginii iese cu eroare; altundeva nu ramane (iesirea
	scriptului sta numai in memoria pluginului, nu intra in /tmp/neoboot-aurora-sync.log), iar cu amanarea nu mai pleaca
	nici raportul pluginului."""
	if not eMesaj(screen):
		return ""
	try:
		brut = _textFereastra(None, arguments, kwargs)
		if not brut:
			return ""
		# intreg, si cu adresele si parolele (REGULA 0, ASI7: in imagine nu se mascheaza nimic pana dupa 1.0)
		return _unRand("%s" % (brut,))
	except Exception:
		return ""


def _laPaznic(text):
	"""Randul in jurnalul paznicului (pleaca in fiecare pachet de tester, fara limita pe zi; jurnalul interfetei pleaca de
	cel mult 3 ori pe zi si numai ultimii 64 KB). Nu arunca."""
	try:
		from Components import HdsPaznic
		HdsPaznic.jurnalPaznic(text)
	except Exception as e:
		_jurnal("jurnalul paznicului: %r" % (e,))


def amana(sesiune, plugin, callback, screen, arguments, kwargs):
	"""pune deschiderea in coada; intoarce None (ecranul nu exista inca)"""
	text = textCerut(screen, arguments, kwargs)
	_coada.append({"sesiune": sesiune, "plugin": plugin, "callback": callback, "screen": screen,
		"arguments": tuple(arguments), "kwargs": dict(kwargs), "incercari": 0, "text": text})
	_jurnal("%s: %s cerut cand nu era niciun ecran modal (o fereastra se inchidea sau se construia); se deschide indata ce "
		"este%s" % (plugin, numeEcran(screen), ("; textul: " + text) if text else ""))
	if text:
		_laPaznic("plugin extern %s: %s deschis dupa o clipa (nu era niciun ecran modal); textul: %s" % (plugin,
			numeEcran(screen), text))
	_pornesteCeas(0)
	return None


def poateDeschide(sesiune):
	"""True cand un ecran e in executie si nicio inchidere nu mai asteapta (processDelay a trecut)"""
	if not getattr(sesiune, "in_exec", False) or getattr(sesiune, "current_dialog", None) is None:
		return False
	ceas = getattr(sesiune, "delay_timer", None)
	try:
		return not (ceas is not None and ceas.isActive())
	except Exception:
		return True


def _pornesteCeas(ms):
	if _ceas[0] is None:
		from enigma import eTimer
		_ceas[0] = eTimer()
		_ceas[0].callback.append(pas)
	_ceas[0].start(ms, True)


def _deschide(c):
	s = c["sesiune"]
	try:
		if c["callback"] is not None:
			s.openWithCallback(c["callback"], c["screen"], *c["arguments"], **c["kwargs"])
		else:
			s.open(c["screen"], *c["arguments"], **c["kwargs"])
		_jurnal("%s: %s deschis" % (c["plugin"], numeEcran(c["screen"])))
	except Exception:
		_jurnal("%s: %s nu s-a deschis:" % (c["plugin"], numeEcran(c["screen"])))
		print_exc(file=sys.stdout)


def _laNotificari(c):
	try:
		from Tools import Notifications
		if c["callback"] is not None:
			Notifications.AddNotificationWithCallback(c["callback"], c["screen"], *c["arguments"], **c["kwargs"])
		else:
			Notifications.AddNotification(c["screen"], *c["arguments"], **c["kwargs"])
		_jurnal("%s: %s tot fara ecran modal dupa %d ms; se arata cand revine bara canalului%s" % (c["plugin"],
			numeEcran(c["screen"]), PAS_MS * INCERCARI, ("; textul: " + c["text"]) if c.get("text") else ""))
	except Exception:
		_jurnal("%s: %s nu s-a putut pune nici in notificari:" % (c["plugin"], numeEcran(c["screen"])))
		print_exc(file=sys.stdout)


def pas():
	"""ceasul: deschide in ordine ce se poate; True daca mai ramane ceva in coada"""
	while _coada:
		c = _coada[0]
		if poateDeschide(c["sesiune"]):
			_coada.pop(0)
			_deschide(c)
			continue
		c["incercari"] += 1
		if c["incercari"] >= INCERCARI:
			_coada.pop(0)
			_laNotificari(c)
			continue
		break
	if _coada:
		_pornesteCeas(PAS_MS)
		return True
	return False


# ------------------------------------------------------------------ ferestrele deschise inaintea InfoBar-ului
# HDSatelit 0.7.6 (ASF, asistenta 222923, Octagon SF8008 0.7.5, TODO 15.11 10:58): un plugin deschide la pornirea sesiunii
# (sessionstart) o fereastra, de pilda MessageBox "Eroare", cand nu e inca niciun ecran. Deschiderea reuseste, apoi InfoBar
# se pune peste ea, iar fereastra ramane sub bara canalului la fiecare pornire: omul n-o vede si n-o poate inchide, iar
# echipa vedea in asistenta numai numele ei. Acum:
# (1) fiecare fereastra deschisa inaintea InfoBar-ului intra in jurnal cu ecranul, titlul, textul si fisierul (cu randul)
#     din care a fost deschisa (Session.open cheama laDeschidere);
# (2) dupa ce InfoBar a pornit si e ecranul de sus, fara nicio inchidere in asteptare, ferestrele aratate ramase sub el se
#     aduc deasupra, in ordinea lor (cea deschisa ultima sus), cu stiva rezumatelor (afisajul din fata) reasezata la fel
#     (runNextScreen cheama dupaInfoBar). Omul o vede si o inchide cu OK, ca pe orice fereastra.
# Ferestrele ascunse (shown fals) raman unde sunt: n-au fost facute sa se vada, iar deasupra ar lua tastele barei. Pluginul
# nu se schimba; open ii intoarce ecranul ca inainte (pluginurile care il tin minte si il inchid singure merg mai departe).

INAINTE_MAX = 20		# cate ferestre de dinaintea InfoBar-ului se tin minte (fara InfoBar, de pilda la paza de model)
RIDICA_PAS_MS = 500
RIDICA_INCERCARI = 1200	# 10 minute: la prima pornire dupa o actualizare InfoBar are deasupra Ce e nou si alte anunturi, pe care
						# omul le poate citi mult; asteptarea costa un ceas de 500 ms
TEXT_MAX = 300

_inainteInfoBar = []	# [(ecranul, descrierea)]
_infoBar = {"pornit": False, "ecran": None, "sesiune": None, "incercari": 0}
_ceasRidica = [None]


def _scurt(cale):
	cale = cale.replace("\\", "/")
	i = cale.find("/python/")
	return cale[i + len("/python/"):] if i >= 0 else cale


def apelant(cadru):
	"""fisierul si randul din care vine deschiderea (primul cadru din afara sesiunii), sau None cand o face sesiunea insasi
	(InfoBar, vrajitorii, modul sigur, din runNextScreen)"""
	while cadru is not None:
		cale = cadru.f_code.co_filename or ""
		if cale not in FARA_FISIER and os.path.basename(cale.replace("\\", "/")) not in FISIERE_SESIUNE:
			return "%s:%d" % (_scurt(cale), cadru.f_lineno)
		cadru = cadru.f_back
	return None


def _unRand(text):
	text = " ".join(("%s" % (text,)).split())
	return text if len(text) <= TEXT_MAX else text[:TEXT_MAX] + "..."


def _componenta(dlg, nume):
	try:
		comp = dlg[nume]
	except Exception:
		return None
	try:
		return comp.getText()
	except Exception:
		return getattr(comp, "text", None)


def _titlu(dlg, kwargs):
	for cheie in ("title", "windowTitle"):
		if kwargs.get(cheie):
			return kwargs[cheie]
	try:
		t = dlg.getTitle()
		if t:
			return t
	except Exception:
		pass
	return _componenta(dlg, "Title") or getattr(dlg, "screenTitle", None) or ""


def _textFereastra(dlg, arguments, kwargs):
	"""textul ferestrei: argumentul text (MessageBox), altfel componenta "text" a ecranului"""
	text = kwargs.get("text")
	if text is None and arguments and isinstance(arguments[0], str):
		text = arguments[0]
	if text is None:
		for nume in ("text", "Text"):
			text = _componenta(dlg, nume)
			if text:
				break
	return text or ""


def descriere(dlg, screen, arguments, kwargs, de_unde):
	"""MessageBox "Eroare": textul (deschisa din Plugins/Extensions/X/plugin.py:12)"""
	s = numeEcran(screen)
	try:
		titlu = _unRand(_titlu(dlg, kwargs))
		text = _unRand(_textFereastra(dlg, arguments, kwargs))
	except Exception as e:
		titlu, text = "", "(textul nu s-a putut citi: %r)" % (e,)
	if titlu:
		s += ' "%s"' % titlu
	if text:
		s += ": " + text
	return s + " (deschisa din %s)" % de_unde


def laDeschidere(sesiune, dlg, screen, arguments, kwargs):
	"""chemata de Session.open dupa ce ecranul a pornit: inaintea InfoBar-ului tine minte fereastra si cine a deschis-o,
	cu un rand in jurnal; dupa InfoBar nu face nimic"""
	if _infoBar["pornit"] or numeEcran(screen) == "InfoBar":
		return
	try:
		# deschisa peste InfoBar chiar cand pornea (Ce e nou din execBegin-ul lui): nu e dedesubt
		if any(type(el[0] if isinstance(el, tuple) else el).__name__ == "InfoBar" for el in sesiune.dialog_stack):
			return
		de_unde = apelant(sys._getframe(1))
		if de_unde is None:
			return
		d = descriere(dlg, screen, arguments, kwargs, de_unde)
		if len(_inainteInfoBar) < INAINTE_MAX:
			_inainteInfoBar.append((dlg, d))
		_jurnal("inaintea InfoBar-ului: %s" % d)
	except Exception as e:
		_jurnal("inaintea InfoBar-ului: %r" % (e,))


def dupaInfoBar(sesiune, infobar):
	"""chemata de runNextScreen dupa deschiderea InfoBar-ului: ferestrele aratate ramase sub el se aduc deasupra, cand
	InfoBar e ecranul de sus si nicio inchidere nu mai asteapta (ceasul ridica)"""
	_infoBar.update(pornit=True, ecran=infobar, sesiune=sesiune, incercari=0)
	if infobar is None or sesiune is None:
		return
	try:
		if _ceasRidica[0] is None:
			from enigma import eTimer
			_ceasRidica[0] = eTimer()
			_ceasRidica[0].callback.append(ridica)
		_ceasRidica[0].start(0, True)
	except Exception as e:
		_jurnal("dupa InfoBar: %r" % (e,))


def _descriereDin(dlg):
	for d, text in _inainteInfoBar:
		if d is dlg:
			return text
	return "%s (deschisa inaintea InfoBar-ului)" % type(dlg).__name__


def _gata():
	del _inainteInfoBar[:]
	_infoBar.update(ecran=None, sesiune=None)


def _aratata(el):
	return isinstance(el, tuple) and len(el) > 1 and bool(el[1])


def ridica():
	"""ceasul: ferestrele aratate de sub InfoBar aduse deasupra; True daca se mai asteapta"""
	s, infobar = _infoBar["sesiune"], _infoBar["ecran"]
	if s is None or infobar is None:
		return False
	try:
		if s.current_dialog is not infobar or not poateDeschide(s):
			_infoBar["incercari"] += 1
			if _infoBar["incercari"] >= RIDICA_INCERCARI:
				for el in list(s.dialog_stack):
					if el[0] is not infobar and _aratata(el):
						_jurnal("InfoBar n-a ajuns ecranul de sus in %d s; ramane dedesubt: %s" % (
							RIDICA_PAS_MS * RIDICA_INCERCARI // 1000, _descriereDin(el[0])))
				_gata()
				return False
			_ceasRidica[0].start(RIDICA_PAS_MS, True)
			return True
		stiva = list(s.dialog_stack)
		sus = [i for i, el in enumerate(stiva) if _aratata(el)]
		for el in stiva:
			if not _aratata(el):
				_jurnal("sub InfoBar ramane fereastra ascunsa: %s" % _descriereDin(el[0]))
		if sus:
			if len(s.summary_stack) != len(stiva) + 1:
				_jurnal("stiva rezumatelor nu se potriveste (%d, ecrane %d); raman sub InfoBar: %s" % (len(s.summary_stack),
					len(stiva), "; ".join(_descriereDin(stiva[i][0]) for i in sus)))
			else:
				_aduDeasupra(s, infobar, stiva, sus)
	except Exception:
		_jurnal("aducerea deasupra InfoBar-ului:")
		print_exc(file=sys.stdout)
	_gata()
	return False


def _aduDeasupra(s, infobar, stiva, sus):
	"""reaseaza stiva: cele ascunse, InfoBar, apoi cele aratate (ultima deschisa devine ecranul de sus); rezumatele la fel
	(summary_stack[i + 1] e rezumatul lui dialog_stack[i], session.summary al ecranului de sus)"""
	rezumate = list(s.summary_stack[1:])
	raman = [i for i in range(len(stiva)) if i not in sus]
	ecrane = [stiva[i] for i in raman] + [(infobar, bool(getattr(infobar, "shown", True)))] + [stiva[i] for i in sus]
	rez = [rezumate[i] for i in raman] + [s.summary] + [rezumate[i] for i in sus]
	# InfoBar pleaca de sus ca la deschiderea unui ecran peste el (Session.pushCurrent: tastele, ascunderea)
	s.execEnd(last=False)
	if s.summary is not None:
		s.summary.hide()
	s.dialog_stack[:] = ecrane[:-1]
	s.summary_stack[:] = s.summary_stack[:1] + rez[:-1]
	s.current_dialog = ecrane[-1][0]
	s.summary = rez[-1]
	if s.summary is not None:
		s.summary.show()
	for i in sus:
		_jurnal("adusa deasupra InfoBar-ului: %s" % _descriereDin(stiva[i][0]))
	s.execBegin(first=False, do_show=True)
