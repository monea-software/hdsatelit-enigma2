# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# CamInfo.py: ecranul „Informații despre decriptare” (meniul Acces condiționat; si tasta albastra din „Module de acces
# condiționat”, Screens/CamSetup.py).
#
# Arata modulul care ruleaza (numele scriptului <fel>.<x>, al unui modul sau al unui server de carduri), procesul care
# lucreaza (cel care tine socketul de decriptare, CamSetup.pid_de_aratat), memoria si firele lui din
# /proc/<pid>/status, spuse simplu (CamSetup.randuri_proces), si ce a scris modulul in /tmp/ecm.info despre canalul de acum; fara niciun modul pornit,
# ecm.info nu se arata (un fisier ramas de la un modul oprit nu spune nimic despre canalul de acum). Deschis din meniu,
# fara argumente, afla singur modulul pornit (Components/HdsModuleAcces), la deschidere si la fiecare citire. Citirile
# sunt fisiere mici, o data la 3 s, pe firul enigma2; pagina derulata cu sagetile ramane la fiecare citire.
# Tastele sunt toate tratate (WizardActions + ColorActions), ca jurnalul sa nu scrie „unknown action”.
import io
import time

from enigma import eTimer

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText

FISIER_ECM = "/tmp/ecm.info"
ECM_MAXIM = 4096           # octeti cititi din FISIER_ECM
CITIRE = 3000              # ms intre doua citiri


class CamInfo(Screen):
	skin = """
	<screen position="center,center" size="960,600" title="Informații despre decriptare">
		<widget name="text" position="40,30" size="880,480" font="Regular;22" />
		<widget source="key_red" render="Label" position="40,540" size="200,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="260,540" size="200,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session, daemon_name=None, pid=None):
		Screen.__init__(self, session)
		# fara nume (deschis din meniu): modulul pornit se afla la deschidere si la fiecare citire
		self.automat = daemon_name is None
		self.daemon_name = daemon_name
		self.daemon_pid = pid
		if self.automat:
			self.aflaEmulatorul()
		self.setTitle(_("Informații despre decriptare"))

		self["text"] = ScrollLabel("")
		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_("Actualizează"))

		self["actions"] = ActionMap(["WizardActions", "ColorActions"],
		{
			"ok": self.close,
			"back": self.close,
			"red": self.close,
			"green": self.refresh,
			"yellow": self.nimic,
			"blue": self.nimic,
			"up": self.paginaSus,
			"down": self.paginaJos,
			"left": self.paginaSus,
			"right": self.paginaJos,
		}, -1)

		self.pagina = 0            # cate pagini s-au derulat, puse la loc dupa fiecare citire (setText muta textul sus)

		self.timer = eTimer()
		self.timer.callback.append(self.refresh)
		self.onShown.append(self.startTimer)
		self.onClose.append(self.stopTimer)

	def nimic(self):
		pass

	def paginaSus(self):
		self.pagina = max(0, self.pagina - 1)
		self["text"].pageUp()

	def paginaJos(self):
		self.pagina = self._limita(self.pagina + 1)
		self["text"].pageDown()

	def _limita(self, pagina):
		"""cel mult ultima pagina a textului (ScrollLabel.pages: None = o singura pagina)"""
		w = self["text"]
		if not hasattr(w, "pages"):
			return pagina
		return max(0, min(pagina, (w.pages or 1) - 1))

	def startTimer(self):
		self.refresh()
		self.timer.start(CITIRE)

	def stopTimer(self):
		self.timer.stop()

	def aflaEmulatorul(self):
		"""numele si procesul modulului pornit, din Components/HdsModuleAcces (modulele obisnuite, apoi serverele de
		carduri; in fiecare, intai cel ales); procesul e cel care lucreaza (CamSetup.pid_de_aratat). Niciunul pornit:
		nume si proces None."""
		nume, pid = None, None
		try:
			from Components import HdsModuleAcces
			from .CamSetup import pid_de_aratat
			sistem = HdsModuleAcces.SistemAcces()
			for st in HdsModuleAcces.feluri_de_aratat(sistem):
				pornite = st.pornite()
				ales = st.ales_emulator()
				if ales is not None and ales.pids:
					pornite = [ales] + [e for e in pornite if e is not ales]
				if pornite:
					nume, pid = pornite[0].sufix, pid_de_aratat(sistem, pornite[0].pids)
					break
		except Exception as e:
			print("[CamInfo] modulul pornit nu s-a putut afla: %s" % e)
		self.daemon_name, self.daemon_pid = nume, pid

	def randuriProces(self):
		lines = []
		if self.daemon_name is None:
			lines.append(_("Niciun modul nu rulează."))
			return lines
		lines.append(_("Modulul: %s") % self.daemon_name)
		if self.daemon_pid:
			lines.append(_("Numărul procesului (PID): %s") % self.daemon_pid)
			try:
				with io.open("/proc/%d/status" % int(self.daemon_pid), "r", encoding="utf-8", errors="replace") as f:
					stare = f.read(4096).splitlines()
			except (IOError, OSError, ValueError):
				lines.append("  " + _("Procesul s-a oprit."))
			else:
				from .CamSetup import randuri_proces
				lines += ["  " + r for r in randuri_proces(stare)]
		return lines

	def randuriEcm(self):
		lines = [_("Ce decriptează acum (din %s):") % FISIER_ECM]
		try:
			with io.open(FISIER_ECM, "r", encoding="utf-8", errors="replace") as f:
				content = f.read(ECM_MAXIM).strip()
		except (IOError, OSError) as e:
			if getattr(e, "errno", None) == 2:
				lines.append("  " + _("Canalul de acum nu este criptat sau nu se decriptează."))
			else:
				lines.append("  " + _("Datele nu s-au putut citi: %s") % (getattr(e, "strerror", None) or e))
			return lines
		if content:
			for l in content.splitlines():
				lines.append("  " + l.strip())
		else:
			lines.append("  " + _("Modulul nu a scris încă nimic despre canalul de acum."))
		return lines

	def refresh(self):
		if self.automat:
			self.aflaEmulatorul()
		lines = self.randuriProces()
		if self.daemon_name is not None:
			lines.append("")
			lines += self.randuriEcm()
		lines.append("")
		lines.append(_("Citit la: %s") % time.strftime("%H:%M:%S", time.localtime()))
		w = self["text"]
		w.setText("\n".join(lines))
		self.pagina = self._limita(self.pagina)
		for _i in range(self.pagina):
			w.pageDown()
