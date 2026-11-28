# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NextEvent.py: randatorul cu emisiunea care urmeaza pe canalul ales, cu numele pe care il cer temele scrise pentru
# OE-Alliance (render="NextEvent", de obicei cu source="ServiceEvent", in lista de canale, sub descrierea emisiunii).
# Scris de HD Satelit de la zero pe 24.11.2026 (TODO 24.11 17:35), in locul fisierului adus pe 12.11, care avea o licenta
# necomerciala (vezi doc/REMOVED-FILES). Tema vede aceeasi purtare: o eticheta (eLabel) cu atributele obisnuite si textul
#   Urmează: 21:30  45 min
#   Titlul emisiunii
# iar cand ghidul nu are emisiunea urmatoare, textul e gol. Fara exceptii: o sursa fara serviciu, un serviciu fara ghid,
# radioul, fluxurile si o sursa nepotrivita dau text gol. In plus: merge si cu serviciul care ruleaza
# (source="session.CurrentService"). Grupurile de alternative din favorite le rezolva ghidul (handleGroup din epgcache.cpp).
import time

from enigma import eEPGCache, eLabel, iServiceInformation

from Components.Renderer.Renderer import Renderer
from Components.VariableText import VariableText

# lookupEvent: tipul 1 = prima emisiune care incepe dupa momentul dat (deci cea de dupa emisiunea de acum, sau cea care vine
# dupa o pauza din ghid); momentul -1 = acum
_URMATOAREA = 1
_ACUM = -1


def referintaSursei(sursa):
	"""Referinta serviciului din sursa, ca sir, sau "" cand sursa nu are un serviciu bun pentru ghid."""
	try:
		serviciu = getattr(sursa, "service", None)
		if not serviciu:
			return ""
		if hasattr(serviciu, "toString"):
			# referinta (ServiceEvent, lista de canale); la ServiceEvent info None = serviciu necunoscut
			if hasattr(sursa, "info") and getattr(sursa, "info") is None:
				return ""
			return serviciu.toString() or ""
		# serviciul care ruleaza (session.CurrentService): referinta se cere informatiei lui
		info = serviciu.info() if callable(getattr(serviciu, "info", None)) else None
		if info is None:
			return ""
		return info.getInfoString(iServiceInformation.sServiceref) or ""
	except Exception:
		return ""


def textUrmatoare(inceput, durata, titlu):
	"""Cele doua randuri pentru emisiunea urmatoare sau "" cand lipseste ceva (titlul, ora sau durata)."""
	titlu = (titlu or "").strip()
	if not titlu or inceput is None or durata is None:
		return ""
	try:
		ora = time.strftime("%H:%M", time.localtime(int(inceput)))
		minute = max(0, int(durata)) // 60
	except (TypeError, ValueError, OverflowError, OSError):
		return ""
	return "%s %s  %d min\n%s" % (_("It follows:"), ora, minute, titlu)


def urmatoareaDinGhid(ref):
	"""(inceput, durata, titlu) pentru emisiunea de dupa cea de acum, sau None."""
	if not ref:
		return None
	try:
		gasite = eEPGCache.getInstance().lookupEvent(["BDT", (ref, _URMATOAREA, _ACUM)])
	except Exception:
		return None
	for rand in gasite or ():
		if rand and len(rand) >= 3:
			return rand[0], rand[1], rand[2]
	return None


class NextEvent(Renderer, VariableText):
	GUI_WIDGET = eLabel

	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)

	def changed(self, what):
		if what and what[0] == self.CHANGED_CLEAR:
			self.text = ""
			return
		gasita = urmatoareaDinGhid(referintaSursei(self.source))
		self.text = textUrmatoare(*gasita) if gasita else ""
