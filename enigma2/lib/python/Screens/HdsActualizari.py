# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsActualizari: ecranul "Actualizare software" (Meniu > Setări > Software & Firmware), actualizarile prin pachete de
# pe stb.hdsatelit.com. Logica si starea sunt in Components/HdsActualizari.py, aceleasi pentru pagina web
# /actualizari (HdsWebControl/actualizari_web.py); ecranul doar arata si porneste.
#
# Randurile ca la "Copia setărilor" (eticheta si valoarea, skinul de rezerva al scanerelor cand skinul nu are ecranul
# HdsActualizariScreen): versiunea instalata (0.3.2; imaginea de baza numai la avertizarea de imagine noua), canalul,
# versiunea de pe server, ce se instaleaza (cate un rand pe pachet, versiunea de acum si cea noua), verificarea
# zilnica. Sub lista: "Ce e nou" al actualizarii, sau de ce trebuie imagine noua, sau
# ce nu a mers. Tastele: ROSU inapoi, VERDE instaleaza (numai cand se poate, cu o intrebare inainte), GALBEN cauta din
# nou, ALBASTRU porneste sau opreste verificarea zilnica. Dupa instalare interfata se reporneste pe calea sigura
# (TryQuitMainloop 3, ca "Restart Interface" din meniu); pana atunci nimic altceva nu mai porneste de aici.
#
# "Ce e nou": noutatile tuturor versiunilor de la cea instalata pana la cea de pe server,
# grupate pe versiuni (Components/HdsActualizari.text_noutati), pot avea zeci de randuri. Textul de sub lista e un
# ScrollLabel (acelasi nume si loc, "preview", deci merge cu orice skin care are ecranul): STANGA/DREAPTA si CH+/CH-
# (si |<< >>|) dau pagina textului, SUS/JOS raman pe lista; bara de derulare apare cand textul nu incape, iar randul de
# stare spune pagina si tastele. Fontul textului nu se mai micsoreaza ca sa incapa (potriveste_textul numai pe stare);
# un text neschimbat nu se scrie din nou, ca pagina aleasa sa ramana la fiecare reimprospatare.

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from Components import HdsActualizari as A
from Components import HdsPachete as P
from Components.HdsCursorLista import pune_randurile

# coloana etichetei (440 la 1920, ca la scanere); valoarea are restul randului
COTE = {"eticheta": 440}


def _nimic():
	pass


def _ngettext(unu, multe, n):
	"""ngettext din traducerea enigma2 (Components/HdsImportSurse.ngettext, formele din Plural-Forms ale limbii); fara
	modul (probele de pe PC cu inlocuitori), regula romaneasca, fiindca msgid-urile sunt in romana."""
	try:
		from Components.HdsImportSurse import ngettext
	except ImportError:
		return unu if n == 1 else multe
	return ngettext(unu, multe, n)


def text_pachete(n, marime):
	"""Un pachet, 14 MB; 2 pachete, 14 MB; 20 pachete, 1 GB: pluralul dupa numar, cu formele limbii (inainte,
	randul „De instalat” si intrebarea instalarii scriau „1 pachete”)."""
	# numele ngettext: asa il cauta xgettext (po/Makefile.am)
	ngettext = _ngettext
	return ngettext("%d pachet, %s", "%d pachete, %s", n) % (n, marime)


TASTE = ("key_red", "key_green", "key_yellow", "key_blue")
# dupa textul unei taste si intre taste, cand se aseaza dupa texte (masurat in 13 limbi la 130%: franceza si poloneza
# au nevoie de aproape tot randul)
TASTA_DUPA_TEXT = 2
TASTE_SPATIU = 12


def locuri_taste(latimi, locuri, spatiu_minim, sfarsit=None):
	"""Unde stau tastele colorate pe randul lor. latimi = latimea de care are nevoie fiecare tasta (bara de culoare,
	distanta pana la text si textul), locuri = [(x, latime)] din skin, sfarsit = capatul randului (implicit capatul
	ultimului loc). Cand fiecare incape in locul ei: None (raman ca in skin). Altfel [(x, latime)] noi pe acelasi rand:
	fiecare tasta cat ii trebuie, restul impartit egal intre ele, cel putin `spatiu_minim`; cand nici asa nu incap
	toate (HdsActualizari._aseazaTastele micsoreaza intai literele), locul ramas se imparte in proportie cu nevoile."""
	if not locuri or len(latimi) != len(locuri) or all(w <= l for w, (_x, l) in zip(latimi, locuri)):
		return None
	inceput = locuri[0][0]
	if sfarsit is None:
		sfarsit = locuri[-1][0] + locuri[-1][1]
	n = len(locuri)
	loc = sfarsit - inceput
	total = sum(latimi)
	spatiu = (loc - total) // (n - 1) if n > 1 else 0
	if spatiu < spatiu_minim:
		spatiu = spatiu_minim if n > 1 else 0
		ramas = max(n, loc - spatiu * (n - 1))
		latimi = [max(1, w * ramas // max(1, total)) for w in latimi]
	rez, x = [], inceput
	for w in latimi:
		rez.append((x, w))
		x += w + spatiu
	return rez


class HdsActualizari(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		from Screens.ScanerCablu import skin_rezerva, culoare_valoare, _culoare_skin, fonturi_texte, \
			potriveste_textul, TASTE_RIDICATE
		self.skinName = ["HdsActualizariScreen"]
		self.skin = skin_rezerva("HdsActualizariScreen", COTE)
		self._fonturi = fonturi_texte("HdsActualizariScreen")
		self._potriveste = potriveste_textul
		self._culoare = culoare_valoare()
		self._culoare_stinsa = _culoare_skin("hdsLabel")
		self._culoare_nota = _culoare_skin("hdsAmber")
		if self._culoare_stinsa is None:
			self._culoare_stinsa = 0x8A93A6
		if self._culoare_nota is None:
			self._culoare_nota = 0xF5B83D
		self.a = A.actualizari
		self["lista"] = List([], enableWrapAround=True)
		self["preview"] = ScrollLabel("")
		self["stare"] = Label("")
		self._stare = ""
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText(_("Caută din nou"))
		self["key_blue"] = StaticText("")
		actiuni = {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.close,
			"green": self.instaleaza,
			"yellow": self.cauta,
			"blue": self.zilnic,
			"up": self.sus,
			"down": self.jos,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"left": self.paginaSus,
			"right": self.paginaJos,
			"leftRepeated": self.paginaSus,
			"rightRepeated": self.paginaJos,
		}
		actiuni.update((nume, _nimic) for nume in TASTE_RIDICATE)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -1)
		# CH+/CH- (si |<< >>|): contextul listei de canale, ca la Extensii; tastele colorate din el merg la aceleasi
		# functii ca in ColorActions (altfel jurnalul ar scrie "unknown action" la fiecare tasta colorata)
		self["pagini"] = ActionMap(["ChannelSelectBaseActions"], {
			"nextBouquet": self.paginaSus,
			"prevBouquet": self.paginaJos,
			"prevMarker": self.paginaSus,
			"nextMarker": self.paginaJos,
			"showAllServices": self.close,
			"showSatellites": self.instaleaza,
			"showProviders": self.cauta,
			"showFavourites": self.zilnic,
		}, -1)
		self.setTitle(_("Actualizare software"))
		self.a.ascultatori.append(self._arata)
		self.onClose.append(self._laInchidere)
		self.onFirstExecBegin.append(self._prima)
		self.onLayoutFinish.append(self._potrivesteTextele)
		self.onLayoutFinish.append(self._aseazaTastele)
		# paginile textului se stiu abia dupa asezarea ferestrei (ScrollLabel.applySkin)
		self.onLayoutFinish.append(self._scrieStarea)
		self._arata()

	def _laInchidere(self):
		if self._arata in self.a.ascultatori:
			self.a.ascultatori.remove(self._arata)

	def _prima(self):
		# la deschidere se cauta singur; nu si cand instalarea a terminat si asteapta repornirea
		if not self.a.ocupat() and not self.a.repornire:
			self.a.cauta()

	def _potrivesteTextele(self):
		# numai randul de stare: textul de sub lista se deruleaza, deci literele lui raman cat le-a ales omul
		font, marime = self._fonturi["stare"]
		self._potriveste(self["stare"], font, marime)

	# ---- textul de sub lista, pe pagini
	def _pagina(self):
		"""(pagina, pagini) a textului de sub lista, sau None cand incape intreg (ScrollLabel.pages e None atunci)"""
		p = self["preview"]
		total = getattr(p, "pages", None)
		if not total or total < 2:
			return None
		try:
			inaltime = p.pageHeight
			pagina = -p.long_text.position().y() // inaltime + 1 if inaltime > 0 else 1
		except Exception:
			pagina = getattr(p, "pagina", 1)
		return max(1, min(total, pagina)), total

	def _scrieStarea(self):
		text = self._stare
		pagina = self._pagina()
		if pagina:
			semn = _("Textul de mai sus: pagina %d din %d (Stânga/Dreapta sau CH+/CH-)") % pagina
			text = "%s\n%s" % (text, semn) if text else semn
		self["stare"].setText(text)
		self._potrivesteTextele()

	def paginaSus(self):
		self["preview"].pageUp()
		self._scrieStarea()

	def paginaJos(self):
		self["preview"].pageDown()
		self._scrieStarea()

	# ---- randurile
	def _randuri(self):
		st = self.a.stare_publica()
		r = st["rezultat"]
		img = st["imagine"]
		randuri = []

		def rand(eticheta, valoare, cheie, stins=False):
			from Screens.ScanerCablu import valoare_scurta
			randuri.append((eticheta, cheie, valoare_scurta(valoare, COTE), self._culoare_stinsa if stins else self._culoare))
		# omul vede numai versiunea (0.3.2); imaginea de baza (de pe stick) e un detaliu, aratat la avertizarea de imagine
		# noua, unde conteaza
		rand(_("Versiunea instalată"), st["imagine_text"] or _("necunoscută"), "imagine")
		if r.get("stare") == A.IMAGINE_NOUA and img["baza"]:
			rand(_("Imaginea de bază"), img["baza"], "baza", stins=True)
		canal = {"proba": _("Probă (numai receptoarele HD Satelit)"), "public": _("Public"),
			"proba-fara-cheie": _("Probă, fără parolă")}.get(st["canal"] or "", _("Fără sursă de actualizări"))
		rand(_("Canalul"), canal, "canal", stins=not st["canal"])
		server = r.get("server") or {}
		if r.get("stare") in (A.LA_ZI, A.DISPONIBILA, A.IMAGINE_NOUA, "instalata", "eroare-instalare"):
			# "actualizare" (numarul intern) 0 = feedul bazei fara pachete
			if server.get("actualizare"):
				pe_server = "%s (%s)" % (server.get("versiune") or "?", server.get("data") or "?")
			else:
				pe_server = _("nicio actualizare")
			rand(_("Pe server"), pe_server, "server")
		pachete = r.get("pachete") or []
		if pachete and r.get("stare") in (A.DISPONIBILA, A.IMAGINE_NOUA):
			rand(_("De instalat"), text_pachete(len(pachete), P.marime_text(r.get("marime")) or "?"), "total")
			for p in pachete:
				rand(p["titlu"], _("de la %s la %s") % (p["de_la_scurt"], p["la_scurt"]), "pachet:" + p["nume"], stins=True)
		rand(_("Verificare zilnică"), _("Pornită") if st["zilnic"] else _("Oprită"), "zilnic")
		return randuri, st

	def _arata(self):
		randuri, st = self._randuri()
		# cursorul ramane pe randul lui (dupa cheie) la OK pe "Verificare zilnică" si la reimprospatarile cautarii
		pune_randurile(self["lista"], randuri)
		r = st["rezultat"]
		# sub lista: ce e nou, sau de ce nu se instaleaza, sau ce nu a mers
		jos = []
		if st["mesaj"]:
			jos.append(st["mesaj"])
		if r.get("stare") == A.IMAGINE_NOUA:
			jos.extend(_(t) for t in r.get("texte_motive") or [])
			jos.append(_(A.TEXT_IMAGINE_NOUA))
		elif r.get("stare") in (A.DISPONIBILA, "instalata"):
			if r.get("nepotrivite"):
				jos.append(_("Lista pachetelor și starea de pe server nu sunt din aceeași publicare. Caută din nou."))
			ce = A.text_noutati(r.get("server") or {})
			if ce:
				jos.append(ce)
		elif st["text_stare"] and r.get("stare") != A.LA_ZI:
			jos.append(st["text_stare"])
			if r.get("eroare"):
				jos.append(r["eroare"])
		elif r.get("stare") == A.LA_ZI:
			jos.append(st["text_stare"])
		text = "\n".join(x for x in jos if x)
		# reimprospatarile (progresul, verificarea zilnica) nu duc textul inapoi la prima pagina
		if text != self["preview"].getText():
			self["preview"].setText(text)
		# randul de stare: pasul in lucru, sau ce urmeaza; dedesubt, pagina textului cand nu incape
		if st["faza"] != "liber":
			facut, total = st["progres"]
			text = st["pas"] or ""
			if st["faza"] == "instalez" and total:
				text = _("Pachete gata: %d din %d. %s") % (facut, total, text)
			self._stare = text
		elif st["repornire"]:
			self._stare = _("Repornește interfața ca să folosești actualizarea (VERDE).")
		elif r.get("stare") == A.DISPONIBILA and r.get("poate_instala"):
			self._stare = _("VERDE: instalează versiunea %s.") % (r.get("server") or {}).get("versiune", "")
		else:
			self._stare = ""
		self._scrieStarea()
		if st["repornire"]:
			self["key_green"].setText(_("Repornește"))
		elif st["faza"] == "liber" and r.get("poate_instala"):
			self["key_green"].setText(_("Instalează"))
		else:
			self["key_green"].setText("")
		self["key_yellow"].setText(_("Caută din nou") if st["faza"] == "liber" and not st["repornire"] else "")
		self["key_blue"].setText(_("Oprește verificarea") if st["zilnic"] else _("Pornește verificarea"))
		self._aseazaTastele()

	def _tasta(self, nume):
		"""(eticheta, bara) ale tastei `nume` din skin: eticheta e desenata din StaticText-ul ei, bara (FixedLabel cu
		ConditionalShowHide) din convertorul legat de el; None cand skinul nu le are."""
		sursa = self[nume]
		eticheta = bara = None
		for r in self.renderer:
			s = getattr(r, "source", None)
			if s is sursa:
				eticheta = r
			elif s is not None and getattr(s, "source", None) is sursa:
				bara = r
		return eticheta, bara

	def _aseazaTastele(self):
		"""Tastele colorate dupa lungimea textelor lor, cand unul nu incape in locul din skin (locuri_taste); altfel
		raman ca in skin. Randul merge pana la marginea cadrului. Literele raman la marimea din skin: cand nici asa nu
		incap, textul care nu incape deruleaza (lib/gui/elabel.h, eDerulare). Locurile si literele din skin se citesc o
		data, la prima asezare (literele micsorate de o versiune mai veche a ecranului revin la marimea din skin)."""
		if getattr(self, "instance", None) is None:
			return
		try:
			from enigma import ePoint, eSize
			taste = [self._tasta(n) for n in TASTE]
			if any(e is None or e.instance is None for e, _b in taste):
				return
			if getattr(self, "_locuriTaste", None) is None:
				locuri = []
				for e, b in taste:
					pe, me = e.instance.position(), e.instance.size()
					pb = b.instance.position() if b is not None and b.instance is not None else pe
					locuri.append((pb.x(), pe.x() + me.width() - pb.x(), pe.x() - pb.x(), pe.y(), me.height()))
				self._locuriTaste = locuri
				try:
					self._fonturiTaste = [(e.instance.getFont().family, int(e.instance.getFont().pointSize)) for e, _b in taste]
				except Exception:
					self._fonturiTaste = None
				self._tasteMicsorate = False
			locuri = self._locuriTaste
			inceput = locuri[0][0]
			sfarsit = max(locuri[-1][0] + locuri[-1][1], self.instance.size().width() - inceput)

			def masura():
				rez = []
				for i, ((e, _b), (_x, _l, pana_la_text, _y, _h)) in enumerate(zip(taste, locuri)):
					text = max(0, e.instance.calculateSize().width()) if self[TASTE[i]].getText() else 0
					rez.append(pana_la_text + text + TASTA_DUPA_TEXT)
				return rez

			def litere(procent):
				from enigma import gFont
				for (e, _b), (familie, marime) in zip(taste, self._fonturiTaste):
					e.instance.setFont(gFont(familie, max(10, marime * procent // 100)))

			if self._tasteMicsorate and self._fonturiTaste:
				litere(100)
				self._tasteMicsorate = False
			latimi = masura()
			noi = locuri_taste(latimi, [(x, l) for x, l, _p, _y, _h in locuri], TASTE_SPATIU, sfarsit)
			if noi is None:
				noi = [(x, l) for x, l, _p, _y, _h in locuri]
			for (e, b), (x, l), (_x0, _l0, pana_la_text, y, h) in zip(taste, noi, locuri):
				e.instance.move(ePoint(x + pana_la_text, y))
				e.instance.resize(eSize(max(1, l - pana_la_text), h))
				if b is not None and b.instance is not None:
					b.instance.move(ePoint(x, b.instance.position().y()))
		except Exception as e:
			print("[HdsActualizari] tastele: %r" % (e,))

	# ---- tastele
	def _cheie(self):
		c = self["lista"].getCurrent()
		return c[1] if c else ""

	def sus(self):
		self["lista"].selectPrevious()

	def jos(self):
		self["lista"].selectNext()

	def ok(self):
		if self._cheie() == "zilnic":
			self.zilnic()

	def zilnic(self):
		A.seteaza_zilnic(not A.zilnic_pornit())
		self._arata()

	def cauta(self):
		if self.a.repornire:
			return
		self.a.cauta()
		self._arata()

	def instaleaza(self):
		if self.a.repornire:
			return self._intreabaRepornirea()
		r = self.a.rezultat
		if self.a.ocupat() or not r.get("poate_instala"):
			return
		server = r.get("server") or {}
		text = _("Instalezi versiunea %s (%s)?") % (server.get("versiune", ""), text_pachete(len(r.get("pachete") or []),
			P.marime_text(r.get("marime")) or "?"))
		text += "\n" + _("La sfârșit interfața trebuie repornită.")
		self.session.openWithCallback(self._confirmat, MessageBox, text, MessageBox.TYPE_YESNO, default=True)

	def _confirmat(self, da):
		if not da:
			return
		vazuta = (self.a.rezultat.get("server") or {}).get("actualizare")
		# ascultatorul intai: sfarsitul instalarii trebuie prins si cand vine imediat
		self.a.ascultatori.append(self._dupaInstalare)
		if not self.a.instaleaza(vazuta) and self._dupaInstalare in self.a.ascultatori:
			self.a.ascultatori.remove(self._dupaInstalare)
		self._arata()

	def _dupaInstalare(self):
		if self.a.ocupat():
			return
		if self._dupaInstalare in self.a.ascultatori:
			self.a.ascultatori.remove(self._dupaInstalare)
		if self.a.repornire:
			self._intreabaRepornirea()

	def _intreabaRepornirea(self):
		# HDSatelit: o intrebare cu raspunsuri nu creste peste caseta de text din skin, iar mesajul instalarii
		# si intrebarea nu incapeau (ultimul rand taiat): la reusita doua randuri scurte; la eroare intai eroarea
		# intreaga (fereastra fara raspunsuri creste cat textul), apoi intrebarea
		if self.a.mesaj and (self.a.rezultat or {}).get("stare") != "instalata":
			self.session.openWithCallback(lambda *a: self._intreaba(""), MessageBox, self.a.mesaj, MessageBox.TYPE_ERROR)
			return
		self._intreaba(_("Actualizarea s-a instalat.") + "\n")

	def _intreaba(self, inainte):
		# HDSatelit: cu memoria decodorului farmitata (si fara inregistrare) se reporneste tot receptorul
		intrebare = _("Repornești receptorul acum?") if _codRepornire(self.session, False) == 2 else \
			_("Repornești interfața acum?")
		self.session.openWithCallback(self._reporneste, MessageBox, inainte + intrebare,
			MessageBox.TYPE_YESNO, default=True)

	def _reporneste(self, da):
		if not da:
			return
		# calea sigura, aceeasi ca "Restart Interface" din meniu (NU init 4/3); cu memoria decodorului farmitata si fara
		# inregistrare, TryQuitMainloop 2 (receptorul intreg, ca Repornire din meniu): Components/HdsMemorieDriver.py
		from Screens.Standby import TryQuitMainloop
		self.session.open(TryQuitMainloop, _codRepornire(self.session, True))


def _codRepornire(sesiune, jurnal):
	"""3 (interfata) sau 2 (receptorul intreg: memoria decodorului farmitata, nicio inregistrare). jurnal=False: numai
	intrebarea (fara randul din jurnalul paznicului). La orice eroare 3, ca inainte."""
	try:
		from Components import HdsMemorieDriver as M
		return M.codRepornireDupaActualizare(sesiune, jurnal=None if jurnal else (lambda text: None))
	except Exception as e:
		print("[HdsActualizari] memoria decodorului: %r" % (e,))
		return 3
