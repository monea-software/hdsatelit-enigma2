# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsListeInternet.py: ecranul "Liste de canale de pe internet" (Meniu > Scanare > Liste implicite de canale, randul
# "Descarcă o listă de canale de pe internet"). Totul dintr-o privire, numai cu sagetile si tastele colorate:
#   - lista: autorul si satelitii fiecarei liste, data ultimei actualizari in dreapta (verde: potrivita antenei);
#   - STANGA / DREAPTA: satelitii (Toate, Un satelit, Doi sateliti, Mai multi sateliti, Motor), ales la deschidere
#     dupa antena receptorului;
#   - ALBASTRU: autorul (Toti autorii, apoi fiecare);
#   - OK / VERDE: instaleaza lista luminata, fara intrebare (lista de acum intra intai intr-o copie de siguranta);
#   - GALBEN: pune la loc lista de dinainte de ultima instalare;
#   - ROSU / EXIT: inapoi.
# Sub lista: satelitii si autorul alesi, apoi lista luminata (autor, sateliti, data). Starea (citirea, instalarea,
# rezultatul) pe randul de jos. Lucrul il face Components/HdsListeInternet.py, acelasi ca in pagina web
# /liste-internet. Fereastra: a ecranului HdsListeImplicite din tema HDSatelit (aceleasi nume), altfel skin_rezerva.

from Screens.Screen import Screen


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _nimic():
	pass


def _M():
	from Components import HdsListeInternet
	return HdsListeInternet


VERDE = 0x0034C759


class HdsListeInternet(Screen):

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components.ActionMap import ActionMap
		from Components.Label import Label
		from Components.Sources.List import List
		from Components.Sources.StaticText import StaticText
		from Screens.ScanerCablu import skin_rezerva, culoare_valoare, fonturi_texte, TASTE_RIDICATE
		self.skinName = ["HdsListeInternet", "HdsListeImplicite"]
		self.skin = skin_rezerva("HdsListeInternet", {"eticheta": 744})
		self._fonturi = fonturi_texte("HdsListeImplicite")
		self._culoare = culoare_valoare()
		M = _M()
		self._ant = M.antena()
		self._fel = M.fel_implicit(self._ant)
		self._autor = ""
		self._randuri = []
		self._lucrari = []
		self._deschis = True
		self["lista"] = List([], enableWrapAround=True)
		self["preview"] = Label("")
		self["stare"] = Label("")
		self["key_red"] = StaticText(_t("Înapoi"))
		self["key_green"] = StaticText(_t("Instalează"))
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText(_t("Autor"))
		taste = {
			"ok": self.instaleaza,
			"green": self.instaleaza,
			"yellow": self.puneLaLoc,
			"blue": self.autorUrmator,
			"cancel": self.close,
			"red": self.close,
			"up": self.sus,
			"down": self.jos,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"left": self.felInapoi,
			"right": self.felInainte,
			"menu": self.actualizareAutomata,
		}
		taste.update((nume, _nimic) for nume in TASTE_RIDICATE)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], taste, -1)
		self.setTitle(_t("Liste de canale de pe internet"))
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._inchis)

	# ------------------------------------------------------------ citirea si desenul

	def _porneste(self):
		M = _M()
		M.demareaza_automat()
		if self._deseneaza not in M._AUTO_ABONATI:
			M._AUTO_ABONATI.append(self._deseneaza)
		self._deseneaza()
		l = M.porneste_citirea(self._citit)
		if l is not None:
			self._lucrari.append(l)
			self._stare(_t("Se citesc listele de la autori..."))
		else:
			self._citit()

	def _inchis(self):
		# lucrarile raman in viata in modul (HdsListeInternet._VII) pana la capat; ecranul nu mai vrea raspunsul
		self._deschis = False
		self._lucrari = []
		M = _M()
		if self._deseneaza in M._AUTO_ABONATI:
			M._AUTO_ABONATI.remove(self._deseneaza)

	def _citit(self):
		if not self._deschis:
			return
		M = _M()
		self._deseneaza()
		erori = M.stare_publica(self._ant)["erori"]
		self._stare(" ".join(erori) if erori else (M.text_gol() if not self._randuri else M.text_ajutor()))

	def _deseneaza(self, pastreaza=True):
		M = _M()
		ales = self._idAles() if pastreaza else None
		self._randuri = M.filtreaza(M.stare()["liste"], self._fel, self._autor, self._ant)
		lista = []
		for l in self._randuri:
			potrivita = M.potrivire(l, self._ant) == 0 and bool(self._ant.get("pozitii") or self._ant.get("fel") == "motor")
			lista.append(("%s: %s" % (l["autor_nume"], l["nume"]), l["id"], l["data"],
				VERDE if potrivita else self._culoare))
		self["lista"].setList(lista)
		self["lista"].setIndex(0)
		if ales:
			for i, l in enumerate(self._randuri):
				if l["id"] == ales:
					self["lista"].setIndex(i)
					break
		self["key_yellow"].setText(_t("Pune la loc") if M.ultima_instalare()[0] else "")
		self._arataDescrierea()

	def _idAles(self):
		curent = self["lista"].getCurrent()
		return curent[1] if curent else None

	def _listaAleasa(self):
		ales = self._idAles()
		for l in self._randuri:
			if l["id"] == ales:
				return l
		return None

	def _arataDescrierea(self):
		M = _M()
		sus = _t("Sateliți: %s · Autor: %s") % (M.text_fel(self._fel), M.text_autor(self._autor))
		l = self._listaAleasa()
		jos = M.descriere(l, self._ant) if l else M.text_intro()
		instalata = M.text_instalata(M.ultima_instalare()[1])
		if instalata:
			jos += "\n" + instalata
		self["preview"].setText(sus + "\n" + jos + "\n" + M.text_automat())
		from Screens.ScanerCablu import potriveste_textul
		for nume in ("preview", "stare"):
			try:
				potriveste_textul(self[nume], *self._fonturi[nume])
			except Exception:
				pass

	def _stare(self, text):
		self["stare"].setText(text or "")

	# ------------------------------------------------------------ tastele

	def sus(self):
		self["lista"].selectPrevious()
		self._arataDescrierea()

	def jos(self):
		self["lista"].selectNext()
		self._arataDescrierea()

	def _schimbaFel(self, pas):
		M = _M()
		i = M.FELURI.index(self._fel) if self._fel in M.FELURI else 0
		self._fel = M.FELURI[(i + pas) % len(M.FELURI)]
		self._deseneaza(pastreaza=False)
		self._citit()

	def felInapoi(self):
		self._schimbaFel(-1)

	def felInainte(self):
		self._schimbaFel(1)

	def autorUrmator(self):
		M = _M()
		chei = [""] + [a["cheie"] for a in M.AUTORI]
		i = chei.index(self._autor) if self._autor in chei else 0
		self._autor = chei[(i + 1) % len(chei)]
		self._deseneaza(pastreaza=False)
		self._citit()

	def instaleaza(self):
		M = _M()
		l = self._listaAleasa()
		if l is None:
			return
		fel, lucrare = M.porneste_instalarea(l["id"], self._gata)
		if fel == "necunoscuta":
			citire = M.porneste_citirea(self._citit, fortat=True)
			if citire is not None:
				self._lucrari.append(citire)
			self._stare(M.text_schimbata())
		elif fel == "ocupat":
			self._stare(_t("Un import e deja în curs. Așteaptă să se termine."))
		elif fel == "pornit":
			self._lucrari.append(lucrare)
			self._stare(_t("Se descarcă și se instalează %s...") % ("%s: %s" % (l["autor_nume"], l["nume"])))

	def actualizareAutomata(self):
		M = _M()
		if not M.stare_publica(self._ant)["automat_incarcat"]:
			self._stare(_t("Se citește opțiunea de actualizare automată..."))
			return
		fel, lucrare = M.porneste_setare_automat(not M.stare_publica(self._ant)["automat"], self._gata)
		if fel == "ocupat":
			self._stare(_t("Un import e deja în curs. Așteaptă să se termine."))
		elif fel == "pornit":
			self._lucrari.append(lucrare)
			self._stare(_t("Se salvează alegerea..."))

	def puneLaLoc(self):
		M = _M()
		fel, lucrare = M.porneste_punerea_la_loc(self._gata)
		if fel == "nimic":
			self._stare(_t("Nu este nicio listă de pus la loc."))
		elif fel == "ocupat":
			self._stare(_t("Un import e deja în curs. Așteaptă să se termine."))
		else:
			self._lucrari.append(lucrare)
			self._stare(_t("Se pune la loc lista de dinainte..."))

	def _gata(self, rezultat):
		if not self._deschis:
			return
		mesaje = (rezultat or {}).get("mesaje") or []
		self._deseneaza()
		# primul mesaj spune ce s-a intamplat (al doilea, buchetele pastrate, cand sunt); restul sta in jurnal
		self._stare(" ".join(mesaje[:2 if any((rezultat or {}).get(k) for k in ("pastrate", "ct_pastrate", "baza_stricata")) else 1]))
