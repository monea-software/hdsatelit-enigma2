# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRezolutieTv: "Rezoluția interfeței" (Meniu > Interfata si aspect), Automată, 1080p sau 2K (2560x1440) pentru tema
# HD Satelit. Intrarea din meniu se arata numai cand placa poate 2K (SystemInfo HdsRezolutie2K, Components/HdsRezolutieTv.py).
# Trei randuri intr-o fereastra de alegere obisnuita (ChoiceBox, deci tema si tastele ei); OK alege, apoi intrebarea
# „Repornești interfața acum?”: Da reporneste pe calea sigura (TryQuitMainloop 3), Nu pastreaza pentru urmatoarea
# pornire. Automată (0.7.7, SK2) = 2K numai pe televizoarele 4K (iesirea 2160p), altfel 1080p; randul ales spune ce
# foloseste acum. Daca 2K nu porneste, interfata revine singura la 1080p si omul afla de ce. In web: /tema-tv
# (tema_tv_web.py).

from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Components import HdsRezolutieTv as R


def _randuri():
	ales = R.aleasa()
	acum = R.peEcran()
	return [(R.eticheta(v, ales, acum, _), v) for v in R.VALORI]


class HdsRezolutieTv(ChoiceBox):
	def __init__(self, session):
		ales = R.aleasa()
		# randul de sus al ferestrei are loc de o singura propozitie (proba pe receptorul de probe): ce face Automată, sau
		# motivul intoarcerii pe 1080p, cand e
		text = _(R.DESCRIERE[R.RAUTO])
		refuz = R.citesteRefuz()
		if refuz:
			text = R.textRefuz(refuz, _)
		ChoiceBox.__init__(self, session, title=text, list=_randuri(), selection=R.VALORI.index(ales),
			windowTitle=_("Rezoluția interfeței"))

	def goEntry(self, entry):
		valoare = entry[1] if len(entry) > 1 else None
		schimbat, mesaj = R.alege(valoare)
		if not schimbat:
			self.close(None)
			return
		self.session.openWithCallback(self._reporneste, MessageBox,
			_(mesaj) + "\n" + _("Repornești interfața acum?"), MessageBox.TYPE_YESNO)

	def _reporneste(self, da):
		if da:
			from Screens.Standby import TryQuitMainloop
			self.session.open(TryQuitMainloop, 3)
		else:
			self.close(None)
