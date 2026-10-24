# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImportSetari: ecranul „Import canale și setări” (meniul Scanare, din data/menu.xml). Aduce canalele, buchetele,
# înregistrările programate, setările antenei, rețeaua și Wi-Fi-ul, piconurile și setările generale sigure dintr-o
# copie și oferă pluginurile ei aflate în sursele receptorului (instaleaza_pluginuri, câte unul, cu confirmarea de la
# Extensii și aplicații); skinul nu. Copia vine: de pe un stick sau un disc (dosarul etc/enigma2 al
# altei imagini, o copie plată, o arhivă .tar.gz), din altă partiție a memoriei interne sau dintr-o copie de siguranță
# a receptorului. Sursele, dezarhivarea și importul stau în Components/HdsImportSurse.py, folosit și de pagina web
# /import (HdsWebControl/scanare_import_web.py).
#
# Ecranul: rândurile ca la scanere (sursa List, două coloane: eticheta și valoarea), în skinul HDSatelit ecranul
# HdsImportSetariScreen, pe alte skinuri skinul de rezervă al scanerelor (Screens/ScanerCablu.skin_rezerva). Sursa se
# alege cu stânga / dreapta sau cu OK dintr-o listă (AlegereDinLista, cu titlul fiecărui mediu); „Importă acum” și
# „Caută din nou” sunt și rânduri, deci totul merge numai cu săgețile și OK. Căutarea surselor și dezarhivarea merg pe
# un fir separat (un stick poate fi lent); importul (câteva fișiere mici și reîncărcarea listei) pe firul enigma2.
# Înainte de import: confirmarea, cu „Nu” ales, și copia de siguranță a fișierelor de acum (HdsImportSurse.importa).
# Setările nu se scriu în settings cât enigma2 rulează: merg în settings.din-copie (Components/HdsSetariDinCopie.py)
# și intră la următoarea pornire a interfeței.

import threading

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox

from Components import HdsImportSurse as surse_import
from Components import HdsSetariDinCopie

ALEGERI = surse_import.ALEGERI
alegeri_efective = surse_import.alegeri_efective
# coloana etichetei (480 la 1920, ca în skin.xml); valoarea are 632 px (HdsBold 30)
COTE = {"eticheta": 480}
LATIME_SURSA = 632


eticheta_alegere = surse_import.eticheta_alegere
ajutor_alegere = surse_import.ajutor_alegere


def _nota_surse(catalog):
	"""Nota despre sursele pachetelor din confirmare (ca pe pagina web a extensiilor)."""
	from Components import HdsExtensiiLucru as L

	def nota(pachete):
		externe = ["%s (%s)" % (n, a) if a else n for n, a in L.surseExterne(catalog, pachete)]
		if not externe:
			return _("Verificat de HD Satelit.") if L.culoareNota(catalog, pachete) == "bun" else ""
		if len(externe) == 1:
			return _("Nu este verificat de HD Satelit. Vine din sursa %s.") % externe[0]
		return _("Nu sunt verificate de HD Satelit. Vin din sursele %s.") % ", ".join(externe)
	return nota


def instaleaza_pluginuri(session, nume, la_sfarsit=None):
	"""Pluginurile `nume` (din copie, aflate în sursele receptorului), câte unul, fiecare cu confirmarea și lucrarea de
	la Extensii și aplicații (Screens/HdsExtensii.HdsExtensiiActiune); la_sfarsit() după ultimul. Catalogul se citește
	pe un fir (fișierele opkg pot avea câțiva MB)."""
	from Components import HdsExtensiiLucru as L
	from Components import HdsPachete as P
	from Components.Ipkg import opkgArguments
	ramase = list(nume or [])
	pastrat = []

	def sfarsit():
		del pastrat[:]
		if la_sfarsit is not None:
			la_sfarsit()

	def urmatorul(catalog, *_a):
		while ramase:
			p = catalog.pachete.get(ramase.pop(0))
			if p is None or p.instalat or not p.se_poate_instala:
				continue
			if L.motivOcupat() is not None:
				break
			plan, _eroare = L.planInstalare(catalog, p, opkgArguments, _nota_surse(catalog))
			if plan is None:
				continue
			plan.setdefault("titluri", L.titluri(catalog))
			from Screens.HdsExtensii import HdsExtensiiActiune
			session.openWithCallback(lambda *_r: urmatorul(catalog), HdsExtensiiActiune, plan)
			return
		sfarsit()

	def citit(catalog, eroare):
		if catalog is None:
			print("[HdsImportSetari] catalogul pachetelor: %s" % eroare)
			sfarsit()
			return
		urmatorul(catalog)

	pastrat.append(surse_import.Lucrare(P.incarca, citit))


def scurt(text, latime=LATIME_SURSA):
	"""Valoarea din rândul „Sursa”, după lățimea măsurată (Components/HdsLatimeText.py, HdsBold 30): întreagă dacă
	încape, altfel fără paranteza de la sfârșit, apoi numai ultimul nume din cale, apoi tăiată la dreapta cu „…”
	(începutul numelui copiei rămâne); textul întreg e în descrierea de sub listă."""
	from Components.HdsLatimeText import incape, scurteaza
	if incape(text, latime, "HdsBold", 30):
		return text
	if text.endswith(")") and " (" in text:
		return scurt(text[:text.rindex(" (")], latime)
	if "/" in text.rstrip("/"):
		return scurt(text.rstrip("/").rsplit("/", 1)[1], latime)
	return scurteaza(text, latime, "HdsBold", 30)


def _nimic():
	pass


class HdsImportSetariScreen(Screen):
	"""Rândurile: Sursa, cele șapte alegeri (ALEGERI: Da / Nu, sau „lipsește din copie”), „Importă acum”,
	„Instalează pluginurile din copie” (după un import cu pluginuri de oferit), „Caută din nou”."""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Screens.ScanerCablu import (skin_rezerva, culoare_valoare, _culoare_skin, fonturi_texte, potriveste_textul,
			TASTE_RIDICATE)
		self.skin = skin_rezerva("HdsImportSetariScreen", COTE)
		self._fonturi = fonturi_texte("HdsImportSetariScreen")
		self._potriveste = potriveste_textul
		self._culoare = culoare_valoare()
		self._culoare_stinsa = _culoare_skin("hdsLabel")
		self._culoare_nota = _culoare_skin("hdsAmber")
		if self._culoare_stinsa is None:
			self._culoare_stinsa = 0x8A93A6
		if self._culoare_nota is None:
			self._culoare_nota = 0xF5B83D
		self.alegeri = dict(surse_import.ALEGERI_IMPLICITE)
		st = surse_import.stare()
		self.surse = list(st["surse"] or [])
		self.id_sursa = self.surse[0]["id"] if self.surse else None
		self._cand = st["cand"]
		self._cauta = True
		self._lucrare = None     # importul pornit de pe acest ecran, până la capătul lui
		self._anulat = None      # threading.Event al acelui import: pus la închiderea ecranului
		self._importat = False
		self._inchis = False
		self._stare_setari = {}
		self._rezultat = []    # mesajele ultimului import, arătate sub listă până la următoarea schimbare
		self._oferite = []     # pluginurile copiei aflate în sursele receptorului, după import
		self["lista"] = List([], enableWrapAround=True)
		self["preview"] = Label("")
		self["stare"] = Label("")
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText(_("Caută din nou"))
		self["key_blue"] = StaticText("")
		actiuni = {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.close,
			"green": self.importa,
			"yellow": self.cautaDinNou,
			"up": self.sus,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"leftRepeated": self.stanga,
			"rightRepeated": self.dreapta,
		}
		actiuni.update((nume, _nimic) for nume in TASTE_RIDICATE)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -1)
		self.setTitle(_("Import canale și setări"))
		self._arata()
		from enigma import eTimer
		self._ceas = eTimer()
		try:
			self._legatura = self._ceas.timeout.connect(self._verificaCautarea)
		except AttributeError:
			self._ceas.callback.append(self._verificaCautarea)
		self.onClose.append(self._laInchidere)
		self.onFirstExecBegin.append(self.cautaDinNou)
		self.onLayoutFinish.append(self._potrivesteTextele)

	# ---- sursele ----
	def cautaDinNou(self):
		"""Pornește căutarea (dacă nu merge deja una, de exemplu din web) și urmărește starea comună."""
		if self._lucrare is not None:
			return
		self._cauta = True
		self._rezultat = []
		surse_import.porneste_cautarea()
		self._arata()
		self._ceas.start(300, False)

	def _verificaCautarea(self):
		st = surse_import.stare()
		if st["cauta"]:
			return
		self._ceas.stop()
		self._cauta = False
		self.surse = list(st["surse"] or [])
		self._cand = st["cand"]
		if surse_import.sursa_dupa_id(self.id_sursa, self.surse) is None:
			self.id_sursa = self.surse[0]["id"] if self.surse else None
		self._arata()

	def sursa(self):
		return surse_import.sursa_dupa_id(self.id_sursa, self.surse)

	# ---- desenul ----
	def _randuri(self):
		s = self.sursa()
		if s is not None:
			# intreaga: un rand care nu incape deruleaza (lib/gui/elabel.h)
			valoare, culoare = surse_import.text_sursa(s), self._culoare
		elif self._cauta:
			valoare, culoare = _("Se caută…"), self._culoare_stinsa
		else:
			valoare, culoare = _("nicio copie găsită"), self._culoare_nota
		randuri = [(_("Sursa"), "sursa", valoare, culoare)]
		for cheie, camp in ALEGERI:
			if s is not None and not s.get(camp):
				randuri.append((eticheta_alegere(cheie), cheie, _("lipsește din copie"), self._culoare_stinsa))
			else:
				randuri.append((eticheta_alegere(cheie), cheie, _("Yes") if self.alegeri[cheie] else _("No"),
					self._culoare))
		randuri.append((_("Importă acum"), "importa", "", self._culoare))
		if self._oferite:
			randuri.append((_("Instalează pluginurile din copie"), "pluginuri", str(len(self._oferite)), self._culoare))
		randuri.append((_("Caută din nou"), "cauta", "", self._culoare))
		if self._stare_setari.get("asteapta"):
			randuri.append((_("Repornește interfața acum"), "reporneste", "", self._culoare))
		return randuri

	def _citesteStareaSetarilor(self):
		"""Setările importate care intră abia la repornirea interfeței (settings.din-copie), citite o dată pe desen."""
		try:
			self._stare_setari = HdsSetariDinCopie.stare()
		except Exception as eroare:
			print("[HdsImportSetari] setarile importate: %s" % eroare)
			self._stare_setari = {}

	def _textPreview(self):
		"""Textul de sub listă; citește și starea setărilor importate (o dată pe desen, pentru rândul repornirii)."""
		self._citesteStareaSetarilor()
		if self._rezultat:
			return "\n".join(self._rezultat)
		s = self.sursa()
		if s is not None:
			text = surse_import.descriere_sursa(s)
		elif self._cauta:
			text = _("Se caută copiile pe stick-uri, discuri și în memoria receptorului…")
		else:
			text = surse_import.text_fara_surse()
		try:
			randuri = HdsSetariDinCopie.texteStare(self._stare_setari) if self._stare_setari else []
		except Exception as eroare:
			print("[HdsImportSetari] starea setarilor importate: %s" % eroare)
			randuri = []
		return "\n".join([text] + randuri)

	def _ajutor(self):
		"""Rândul de stare: ce înseamnă rândul luminat și ce fac tastele."""
		if self._cauta and not self.surse:
			return _("Se caută…")
		if not self.surse:
			return _("Pune stick-ul cu copia și alege „Caută din nou”.")
		cheie = self._cheie()
		if ajutor_alegere(cheie):
			return ajutor_alegere(cheie)
		if cheie == "pluginuri":
			return _("Câte unul, cu întrebarea de la Extensii și aplicații.")
		if cheie == "reporneste":
			return _("Setările importate intră după repornirea interfeței: câteva secunde, apoi canalul pornește iar.")
		if len(self.surse) > 1:
			return _("%d copii găsite. Alege cu OK, stânga sau dreapta; importă cu „Importă acum”.") % len(self.surse)
		return _("Schimbă cu OK, stânga sau dreapta; importă cu „Importă acum”.")

	def _arata(self, stare=None):
		text = self._textPreview()
		lista = self["lista"]
		index = lista.getIndex() if lista.list else 0
		lista.setList(self._randuri())
		lista.setIndex(index or 0)
		self["preview"].setText(text)
		self["stare"].setText(stare or self._ajutor())
		self._potrivesteTextele()
		self["key_green"].setText(_("Importă") if self.sursa() is not None else "")

	# ---- tastele ----
	def _cheie(self):
		curent = self["lista"].getCurrent()
		return curent[1] if curent else None

	def _potrivesteTextele(self, nume=("preview", "stare")):
		"""Cu fonturile mărite (Mărime fonturi OSD peste 100 %), textul care nu mai încape se scrie mai mic."""
		for n in nume:
			self._potriveste(self[n], *self._fonturi[n])

	def sus(self):
		self["lista"].selectPrevious()
		self["stare"].setText(self._ajutor())
		self._potrivesteTextele(("stare",))

	def jos(self):
		self["lista"].selectNext()
		self["stare"].setText(self._ajutor())
		self._potrivesteTextele(("stare",))

	def _schimba(self, pas):
		self._rezultat = []
		cheie = self._cheie()
		if cheie == "sursa":
			ids = [s["id"] for s in self.surse]
			if not ids:
				return
			i = ids.index(self.id_sursa) if self.id_sursa in ids else -1
			self.id_sursa = ids[(i + pas) % len(ids)]
			self._arata()
		elif cheie in self.alegeri:
			s = self.sursa()
			camp = dict(ALEGERI)[cheie]
			if s is not None and not s.get(camp):
				self._arata(_("Copia aleasă nu are așa ceva."))
				return
			self.alegeri[cheie] = not self.alegeri[cheie]
			self._arata()

	def stanga(self):
		self._schimba(-1)

	def dreapta(self):
		self._schimba(1)

	def ok(self):
		cheie = self._cheie()
		if cheie == "sursa":
			if not self.surse:
				self.cautaDinNou()
				return
			from Screens.ScanerCablu import AlegereDinLista
			randuri = surse_import.alegeri_surse(self.surse)
			poz = [i for i, r in enumerate(randuri) if r[1] == self.id_sursa]
			self.session.openWithCallback(self._dupaAlegere, AlegereDinLista, title=_("Sursa"), list=randuri,
				selection=poz[0] if poz else 1)
		elif cheie in self.alegeri:
			self._schimba(1)
		elif cheie == "importa":
			self.importa()
		elif cheie == "cauta":
			self.cautaDinNou()
		elif cheie == "pluginuri":
			nume = [p[0] for p in self._oferite]
			self._oferite = []
			self._arata()
			instaleaza_pluginuri(self.session, nume)
		elif cheie == "reporneste":
			self.session.openWithCallback(self._dupaIntrebareRepornire, MessageBox,
				_("Interfața repornește acum, ca să intre setările importate. Continui?"), MessageBox.TYPE_YESNO,
				default=False)

	def _dupaIntrebareRepornire(self, da=False):
		if da:
			from Screens.Standby import TryQuitMainloop
			self.session.open(TryQuitMainloop, 3)

	def _dupaAlegere(self, rand=None):
		self._rezultat = []
		if rand and rand[1] is not None and surse_import.sursa_dupa_id(rand[1], self.surse) is not None:
			self.id_sursa = rand[1]
		self._arata()

	# ---- importul ----
	def importa(self):
		s = self.sursa()
		if s is None:
			self._arata(_("Nu am găsit nicio copie."))
			return
		if not any(alegeri_efective(self.alegeri, s).values()):
			self._arata(_("Alege cel puțin un lucru de importat."))
			return
		if self._lucrare is not None or surse_import.ocupat():
			self._arata(_("Un import e deja în curs. Așteaptă să se termine."))
			return
		# caseta de mesaj are loc pentru trei rânduri: numele scurt al copiei, calea întreagă e sub listă
		text = _("Canalele și setările alese se înlocuiesc cu cele din „%s”. Cele de acum rămân într-o copie de "
			"siguranță pe receptor. Continui?") % scurt(surse_import.text_sursa(s))
		if alegeri_efective(self.alegeri, s).get("retea"):
			text += "\n" + _("Rețeaua se schimbă: legătura poate cădea câteva secunde.")
		self.session.openWithCallback(self._dupaConfirmare, MessageBox, text, MessageBox.TYPE_YESNO, default=False)

	def _dupaConfirmare(self, da=False):
		s = self.sursa()
		if not da or s is None:
			return
		alegeri = alegeri_efective(self.alegeri, s)
		self._anulat = threading.Event()
		# pregătirea, copia de siguranță și scrierea fișierelor merg pe firul importului; aici rămân textul settings
		# de acum (înainte) și reîncărcarea listei de canale (după), în HdsImportSurse.porneste_importul
		self._importat = False
		lucrare = surse_import.porneste_importul(s, alegeri, self._dupaImport, self._anulat)
		if lucrare is None:
			self._arata(_("Un import e deja în curs. Așteaptă să se termine."))
		elif not self._importat:
			self._lucrare = lucrare
			self._arata(_("Se pregătește copia…"))

	def _dupaImport(self, rezultat):
		"""Pe firul enigma2, la capătul importului (zăvorul e deja dat înapoi). Un ecran închis între timp nu mai
		desenează nimic; rezultatul rămâne în starea comună (și în /import)."""
		self._importat = True
		self._lucrare = None
		if self._inchis:
			return
		# mesajele (copia de siguranță, fișierele, setările) nu încap într-o casetă de mesaj: rămân sub listă
		self._rezultat = list(rezultat.get("mesaje") or [])
		self._oferite = list((rezultat.get("pachete") or {}).get("oferite") or [])
		if (rezultat.get("pachete") or {}).get("fara_lista"):
			self._rezultat.append(_("Lista surselor de pachete nu e descărcată încă: o descarci din Meniu, Extensii și "
				"aplicații."))
		self._arata(_("Import terminat.") if rezultat.get("ok") else _("Importul nu s-a făcut."))

	def _laInchidere(self):
		"""Firul importului nu se oprește la jumătate: dacă încă pregătea copia, nu mai scrie nimic pe receptor
		(anulat); dacă scria deja, termină. Zăvorul îl dă înapoi capătul firului (porneste_importul)."""
		self._inchis = True
		self._ceas.stop()
		if self._anulat is not None:
			self._anulat.set()


def main(session, **kwargs):
	session.open(HdsImportSetariScreen)


def Plugins(**kwargs):
	"""0.2.6: ecranul e al imaginii si se deschide numai din meniu, Scanare > „Import
	canale și setări” (data/menu.xml, entryID hds_import_setari, prin Screens/HdsImportSetari.py; in web /import).
	Fara descriptori: nu mai apare in lista de extensii, la tasta albastra si nici agatat de meniul „scan”."""
	return []
