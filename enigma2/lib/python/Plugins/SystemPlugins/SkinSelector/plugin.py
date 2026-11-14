# -*- coding: utf-8 -*-
# (c) 2006 Stephan Reichholf
# This Software is Free, use it where you want, when you want for whatever you want and modify it if you want but don't remove my copyright!
# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen
from Screens.Standby import TryQuitMainloop
from Screens.MessageBox import MessageBox
from Components.ActionMap import NumberActionMap
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.MenuList import MenuList
from Components.config import config, configfile
# the list, the preview, the choice, the safe start and the menu layout are shared with the web interface (/skin):
# Components/HdsSkinuri.py
from Components import HdsSkinuri
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from enigma import eEnv

class SkinSelector(Screen):
	# for i18n:
	# _("Choose your Skin")
	skinlist = []
	root = eEnv.resolve("${datadir}/enigma2/")

	def __init__(self, session, args = None):

		Screen.__init__(self, session)
		# HDSatelit: titlul ferestrei = numele intrarii din meniu (data/menu.xml, skin_setup) si al paginii web /skin
		self.setTitle(_("Aspectul ecranelor"))

		self.previewPath = ""
		# HDSatelit 0.7.5: la coada listei, temele incomplete (dosare ramase fara skin.xml, Components/HdsTemaStergere.py),
		# cu semnul „incompletă”; se pot numai sterge
		self.incomplete = {}
		self.skinlist = self._lista()

		# HDSatelit 0.7.5: ROSU sterge tema selectata (ca in Extensii); inchiderea ramane pe EXIT. Eticheta e goala pe temele
		# care nu se pot sterge (tema imaginii, cele de care depinde alt pachet); motivul se spune la apasare
		# (Components/HdsTemaStergere.py, aceeasi hotarare ca pagina web /skin)
		self["key_red"] = StaticText("")
		self.planuriStergere = {}
		# Actiuni explicite: OK/VERDE aplica acum; ALBASTRU pastreaza pentru pornirea urmatoare.
		self["key_green"] = StaticText(_("Aplică acum"))
		self["key_blue"] = StaticText(_("La următoarea pornire"))
		# HDSatelit: skinul ales se incarca la pornirea urmatoare (skin.py, Components/HdsSkinuri.py); daca n-a pornit,
		# motivul intoarcerii pe HDSatelit sta aici pana la o alegere noua
		refuz = HdsSkinuri.refuzDeSpus()
		if refuz:
			self["introduction"] = StaticText(HdsSkinuri.textRefuz(refuz, _))
		else:
			# tema externa de pe ecran: ce nu merge din ea, cat timp e ceva de spus
			self["introduction"] = StaticText(HdsSkinuri.textStareTema(_) or _("Aplică acum repornește interfața. La următoarea pornire păstrează alegerea fără repornire."))
		self["SkinList"] = MenuList(self.skinlist)
		self["Preview"] = Pixmap()
		# HDSatelit: aspectul meniului (lista sau dale) pe tasta galbena; meniul ramane deocamdata lista (Screens/Menu.py)
		self["key_yellow"] = StaticText("")
		self._actualizeazaAspectMeniu()

		self["actions"] = NumberActionMap(["WizardActions", "InputActions", "EPGSelectActions", "ColorActions"],
		{
			"ok": self.ok,
			"green": self.ok,
			"blue": self.laPornire,
			"back": self.close,
			"red": self.sterge,
			"yellow": self.comutaAspectMeniu,
			"up": self.up,
			"down": self.down,
			"left": self.left,
			"right": self.right,
			"info": self.info,
		}, -1)

		self.onLayoutFinish.append(self.layoutFinished)

	def _lista(self):
		lista = HdsSkinuri.lista(self.root)
		self.incomplete = {}
		try:
			from Components import HdsTemaStergere
			for nume in HdsTemaStergere.incomplete(self.root):
				eticheta = HdsTemaStergere.etichetaIncompleta(nume, _)
				self.incomplete[eticheta] = nume
				lista.append(eticheta)
		except Exception as e:
			print("[SkinSelector] temele incomplete: %s" % e)
		return lista

	def _curent(self):
		"""(dosarul temei de pe randul ales, e incompleta)"""
		x = self["SkinList"].getCurrent()
		if x in self.incomplete:
			return self.incomplete[x], True
		return x, False

	def _actualizeazaAspectMeniu(self):
		eticheta = _("Dale") if HdsSkinuri.aspect(config) == "dale" else _("Listă")
		self["key_yellow"].setText(_("Aspect meniu") + ": " + eticheta)

	def comutaAspectMeniu(self):
		HdsSkinuri.comutaAspect(config)
		self._actualizeazaAspectMeniu()

	def layoutFinished(self):
		tmp = HdsSkinuri.curent(config)
		if tmp is not None:
			idx = 0
			for skin in self.skinlist:
				if skin == tmp:
					break
				idx += 1
			if idx < len(self.skinlist):
				self["SkinList"].moveToIndex(idx)
		self._planuriStergere()
		self.loadPreview()

	# ------------------------------------------------------------ stergerea temei (HDSatelit 0.7.5)

	def _planuriStergere(self):
		try:
			from Components import HdsTemaStergere
			self.planuriStergere = HdsTemaStergere.planuri([self.incomplete.get(x, x) for x in self.skinlist], self.root, "/",
				HdsSkinuri.numeDinValoare(HdsSkinuri.skinPornit()) or HdsSkinuri.DOSAR_IMAGINE, HdsSkinuri.curent(config), _)
		except Exception as e:
			print("[SkinSelector] stergerea temelor: %s" % e)
			self.planuriStergere = {}

	def _actualizeazaRosu(self):
		p = self.planuriStergere.get(self._curent()[0])
		self["key_red"].setText(_("Șterge") if p and p["poate"] else "")

	def sterge(self):
		nume = self._curent()[0]
		if not nume:
			return
		from Components import HdsTemaStergere
		# planul se face din nou acum: intre timp tema poate fi fost stearsa sau aleasa din pagina web
		p = HdsTemaStergere.planCurent(nume, config, self.root, _)
		if not p["poate"]:
			self["introduction"].setText(p["motiv"])
			return
		self.deSters = p
		if p["fel"] == HdsTemaStergere.FEL_PACHET and not p["pe_ecran"]:
			# tema din pachet: confirmarea si progresul Extensiilor (opkg remove), intr-o singura fereastra
			from Components import HdsExtensiiLucru as L
			from Components.Ipkg import opkgArguments
			motiv = L.motivOcupat(None)
			if motiv is not None:
				self["introduction"].setText(motiv[0])
				return
			plan, eroare = HdsTemaStergere.planPachet(p, argumente=opkgArguments, traducere=_)
			if plan is None:
				self["introduction"].setText(eroare[0])
				return
			from Screens.HdsExtensii import HdsExtensiiActiune
			plan.setdefault("titluri", L.titluri(L.catalogLaZi() or L.incarcaCatalog()))
			self.session.openWithCallback(self._dupaPachet, HdsExtensiiActiune, plan)
			return
		text = "\n".join([p["intrebare"]] + p["detalii"])
		self.session.openWithCallback(self._confirmaStergerea, MessageBox, text, MessageBox.TYPE_YESNO, default=False)

	def _confirmaStergerea(self, da=False):
		p = getattr(self, "deSters", None)
		if da is not True or not p:
			return
		from Components import HdsTemaStergere
		if p["pe_ecran"]:
			# tema de pe ecran: interfata trece pe tema urmatoare, iar tema se sterge la pornire (HdsTemaStergere.laPornire)
			if not HdsTemaStergere.programeaza(p, config):
				self["introduction"].setText(HdsSkinuri.textMotiv(HdsSkinuri.MOTIV_SCRIERE, "", _))
				return
			configfile.save()
			self.session.open(TryQuitMainloop, 3)
			return
		bun, mesaj = HdsTemaStergere.stergeDosarAles(p, config, self.root, _)
		if bun:
			configfile.save()
		self._dupaStergere(mesaj)

	def _dupaPachet(self, schimbat=False):
		p = getattr(self, "deSters", None)
		if not p:
			return
		from Components import HdsTemaStergere
		if HdsTemaStergere.dupaPachet(p["nume"], config, self.root):
			configfile.save()
			self._dupaStergere(_("Tema %s a fost ștearsă.") % p["nume"])
		elif schimbat:
			self._dupaStergere("")

	def _dupaStergere(self, mesaj):
		"""lista se reface, selectia trece pe randul vecin"""
		idx = self["SkinList"].getSelectionIndex()
		self.skinlist = self._lista()
		self["SkinList"].setList(self.skinlist)
		if self.skinlist:
			self["SkinList"].moveToIndex(max(0, min(idx, len(self.skinlist) - 1)))
		self._planuriStergere()
		self.loadPreview()
		if mesaj:
			self["introduction"].setText(mesaj)

	def up(self):
		self["SkinList"].up()
		self.loadPreview()

	def down(self):
		self["SkinList"].down()
		self.loadPreview()

	def left(self):
		self["SkinList"].pageUp()
		self.loadPreview()

	def right(self):
		self["SkinList"].pageDown()
		self.loadPreview()

	def info(self):
		aboutbox = self.session.open(MessageBox,_("Enigma2 Skinselector\n\nIf you experience any problems please contact\nstephan@reichholf.net\n\n© 2006 - Stephan Reichholf"), MessageBox.TYPE_INFO)
		aboutbox.setTitle(_("About..."))


	def ok(self, acum=True):
		nume = self["SkinList"].getCurrent()
		if not nume:
			return
		incomplete = getattr(self, "incomplete", None) or {}
		if nume in incomplete:
			self["introduction"].setText(_("Tema %s e incompletă: lipsește skin.xml, deci nu se mai poate folosi. Tasta "
				"roșie șterge ce a rămas din ea.") % incomplete[nume])
			return
		print("Skinselector: Selected Skin: " + self.root + HdsSkinuri.fisier(nume))
		bun, mesaj, avertisment = HdsSkinuri.alege(nume, config, self.root, _)
		if not bun:
			self.session.open(MessageBox, mesaj, MessageBox.TYPE_ERROR)
			return
		configfile.save()
		text = _("Skinul %s este păstrat pentru următoarea pornire a interfeței.") % nume
		self["introduction"].setText((avertisment + "\n" + text) if avertisment else text)
		if acum:
			self.restartGUI(True)

	def laPornire(self):
		self.ok(acum=False)

	def loadPreview(self):
		self._actualizeazaRosu()
		pngpath = HdsSkinuri.previzualizare(self.root, self._curent()[0],
			resolveFilename(SCOPE_PLUGINS, HdsSkinuri.POZA_LIPSA))

		if self.previewPath != pngpath:
			self.previewPath = pngpath

		# HDSatelit: pe un ecran care nu e 1920x1080 (alt skin ales), poza la marimea ei inmultita cu factorul ecranului,
		# ca fereastra scalata de skin.py (skin.factorHds); pe 1920x1080 ca inainte
		poza = None
		try:
			import skin
			fx, fy, _ff = skin.factorHds()
			m = skin.marimeImagine(self.previewPath) if (fx, fy) != (1.0, 1.0) else None
			if m:
				poza = skin.incarcaPixmapScalat(self.previewPath, max(1, int(round(m[0] * fx))), max(1, int(round(m[1] * fy))))
		except Exception as e:
			print("[SkinSelector] poza skinului ramane la marimea ei: %s" % e)
		if poza is not None:
			self["Preview"].instance.setPixmap(poza)
		else:
			self["Preview"].instance.setPixmapFromFile(self.previewPath)

	def restartGUI(self, answer = False):
		# HDSatelit: intrebarea inchisa fara raspuns (de pilda de o proba) = Nu, fara TypeError in callback
		if answer is True:
			self.session.open(TryQuitMainloop, 3)

def SkinSelMain(session, **kwargs):
	session.open(SkinSelector)


class _Pornire(object):
	ceas = None


def _pornireReusita():
	_Pornire.ceas = None
	HdsSkinuri.pornireReusita()
	# interfata 2K a temei HD Satelit a mers: semnul probei se sterge (Components/HdsRezolutieTv.py)
	try:
		from Components import HdsRezolutieTv
		HdsRezolutieTv.pornireReusita()
	except Exception as eroare:
		print("[SkinSelector] proba 2K: %s" % eroare)
	# tema externa: raportul si mesajul pentru ce nu s-a putut din ea, o singura data pe versiune de tema
	try:
		valoare = HdsSkinuri.skinPornit()
		if valoare != HdsSkinuri.SKIN_IMAGINE:
			import skin
			from Components import HdsTemaExterna
			HdsTemaExterna.dupaProba(HdsSkinuri.numeDinValoare(valoare) or valoare, skin.raportTema, skin.warnings)
	except Exception as eroare:
		print("[SkinSelector] raportul temei: %s" % eroare)


def laPornireaSesiunii(reason, session = None, **kwargs):
	"""HDSatelit: dupa pornirea interfetei. Daca skin.py s-a intors pe HDSatelit, setarea se salveaza (configfile) si
	omul afla o data de ce; dupa HdsSkinuri.PROBA_S secunde de mers, semnul probei skinului ales se sterge (pornirea cu
	el a reusit)."""
	if reason != 0:
		return
	# o tema stearsa din alt panou sau din linia de comanda: fisierele imaginii pe care le suprascrisese se pun la loc
	# (Components/HdsTemeSuprascrise.py; pe un fir, numai daca exista copii)
	try:
		from Components import HdsTemeSuprascrise
		HdsTemeSuprascrise.laPornire()
	except Exception as eroare:
		print("[SkinSelector] fisierele imaginii suprascrise de teme: %s" % eroare)
	# tema stearsa cand era pe ecran: interfata a pornit cu alta tema, acum se sterge (Components/HdsTemaStergere.py)
	try:
		from Components import HdsTemaStergere
		HdsTemaStergere.laPornire(traducere=_)
	except Exception as eroare:
		print("[SkinSelector] stergerea temei la pornire: %s" % eroare)
	try:
		refuz = HdsSkinuri.deAratat()
		if refuz:
			from Components.config import configfile
			configfile.save()
			# echipa afla de tema retrasa; omul vede motivul si raspunsul serverului intr-un singur mesaj
			from Components import HdsTemaExterna
			HdsTemaExterna.dupaRefuz(refuz, HdsSkinuri.textRefuz(refuz, _))
	except Exception as eroare:
		print("[SkinSelector] mesajul skinului: %s" % eroare)
	# interfata 2K intoarsa singura pe 1080p (placa a refuzat-o, driverul vechi, o oprire la pornire): o data, de ce
	try:
		from Components import HdsRezolutieTv
		HdsRezolutieTv.laPornireaSesiunii(_)
	except Exception as eroare:
		print("[SkinSelector] mesajul rezolutiei: %s" % eroare)
	try:
		from enigma import eTimer
		_Pornire.ceas = eTimer()
		_Pornire.ceas.callback.append(_pornireReusita)
		_Pornire.ceas.start(HdsSkinuri.PROBA_S * 1000, True)
	except Exception as eroare:
		print("[SkinSelector] ceasul probei: %s" % eroare)


def Plugins(**kwargs):
	# 0.2.6: alegerea skinului e in meniu, Setari > Interfata si aspect (data/menu.xml,
	# prin Screens/SkinSelector.py). Carligul vechi WHERE_MENU cerea meniul "system", care nu exista in menu.xml-ul
	# imaginii, deci nu aparea nicaieri. Aici ramane numai pornirea sesiunii (pornirea sigura cu skinul ales).
	from Plugins.Plugin import PluginDescriptor
	return [PluginDescriptor(name = "SkinSelector", where = PluginDescriptor.WHERE_SESSIONSTART, fnc = laPornireaSesiunii)]
