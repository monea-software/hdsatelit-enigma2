# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen

from Components.ActionMap import ActionMap
from Components.Language import language
from Components.config import config
from Components.Sources.List import List
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.language_cache import LANG_TEXT

def _cached(x):
	cod = config.osd.language.value
	if cod not in language.lang:
		# limba salvata e ascunsa (Components/Language.py, LIMBI_COMPLETE): textele limbii in care sunt meniurile
		cod = language.getLanguage()
	return LANG_TEXT.get(cod, {}).get(x, "")

from Screens.Rc import Rc

from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN

from Tools.LoadPixmap import LoadPixmap

def LanguageEntryComponent(file, name, index):
	png = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "countries/" + file + ".png"))
	if png == None:
		png = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "countries/missing.png"))
	res = (index, name, png)
	return res

class LanguageSelection(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)

		self.oldActiveLanguage = language.getActiveLanguage()

		self.list = []
		self["languages"] = List(self.list)
		self["languages"].onSelectionChanged.append(self.changed)
		# HDSatelit: textul de ajutor de sub lista (widgetul "description" al skinului), in limba de pe randul ales,
		# ca titlul (LANG_TEXT din Components/language_cache.py, schimbat in changed)
		self["description"] = Label(_cached("T1"))

		self.updateList()
		self.onLayoutFinish.append(self.selectActiveLanguage)

		self["actions"] = ActionMap(["OkCancelActions"], 
		{
			"ok": self.save,
			"cancel": self.cancel,
		}, -1)

	def selectActiveLanguage(self):
		activeLanguage = language.getActiveLanguage()
		pos = 0
		for x in self.list:
			if x[0] == activeLanguage:
				self["languages"].index = pos
				break
			pos += 1

	def save(self):
		cod = self["languages"].getCurrent()[0]
		if cod not in language.lang:
			from Components.Language import limbiPeStick
			from Screens.MessageBox import MessageBox
			if not limbiPeStick():
				# limba din feed (imaginea mica): se salveaza ca oricare, meniurile raman in engleza pana vine, iar
				# receptorul o descarca si o instaleaza singur, fara intrebare (Components/HdsLimbaRestaurare.py)
				self.run()
				from Components import HdsLimbaRestaurare
				try:
					HdsLimbaRestaurare.cereAcum(self.session, spus=True)
				except Exception as e:
					print("[LanguageSelection] descarcarea limbii: %r" % (e,))
				date = language.toate.get(cod)
				nume = (date and _cached("%s_%s" % date[1:3])) or (date[0] if date else cod)
				self.session.openWithCallback(lambda *args: self.close(), MessageBox,
					HdsLimbaRestaurare.textSeDescarca(nume), type=MessageBox.TYPE_INFO, timeout=10)
				return
			def raspuns(da):
				if da:
					from Screens.HdsParteaDoua import HdsParteaDoua
					self.session.openWithCallback(lambda *args: self._dupaInstalareaLimbii(cod), HdsParteaDoua)
			self.session.openWithCallback(raspuns, MessageBox,
				_("Limba aleasa lipseste din baza. Deschid instalarea limbilor pe stick?"),
				type=MessageBox.TYPE_YESNO, default=False)
			return
		self.run()
		self.close()

	def _dupaInstalareaLimbii(self, cod):
		self.updateList()
		if cod in language.lang:
			for i, x in enumerate(self.list):
				if x[0] == cod:
					self["languages"].index = i
					self.run()
					self.close()
					return

	def cancel(self):
		# HDSatelit: EXIT anuleaza si limba salvata: mutarea cursorului o schimba numai in memorie (run, justlocal), deci
		# fara asta limba pe care a stat cursorul ultima data se scria la iesirea enigma2 si venea la pornirea urmatoare
		config.osd.language.cancel()
		language.activateLanguage(self.oldActiveLanguage)
		self.close()

	def run(self, justlocal = False):
		print("updating language...")
		lang = self["languages"].getCurrent()[0]
		config.osd.language.value = lang
		self.setTitle(_cached("T2"))
		
		if justlocal:
			return

		config.osd.language.save()

		language.activateLanguage(lang)
		config.misc.languageselected.value = 0
		config.misc.languageselected.save()
		# ca pagina web (limba_interfata_web): alegerea ramane si dupa o oprire fara iesire curata
		from Components.config import configfile
		configfile.save()
		print("ok")

	def updateList(self):
		first_time = not self.list

		languageList = language.getLanguageList(suplimentare=not isinstance(self, LanguageWizard))
		if not languageList: # no language available => display only english
			list = [ LanguageEntryComponent("en", _cached("en_EN"), "en_EN") ]
		else:
			from Components.Language import etichetaFaraCatalog
			eticheta = etichetaFaraCatalog()
			list = [LanguageEntryComponent(file=x[1][2].lower(),
				name=(_cached("%s_%s" % x[1][1:3]) or x[1][0]) +
				(" " + eticheta if x[0] not in language.lang else ""), index=x[0]) for x in languageList]
		self.list = list

		#list.sort(key=lambda x: x[1][7])

		print("updateList")
		if first_time:
			self["languages"].list = list
		else:
			self["languages"].updateList(list)
		print("done")

	def changed(self):
		self.run(justlocal = True)
		self.updateList()
		self["description"].setText(_cached("T1"))

class LanguageWizard(LanguageSelection, Rc):
	def __init__(self, session):
		LanguageSelection.__init__(self, session)
		Rc.__init__(self)
		self.onLayoutFinish.append(self.selectKeys)
				
		self["wizard"] = Pixmap()
		self["text"] = Label()
		# HDSatelit: in asistent ajutorul e textul de sus (setText), nu si randul de jos
		self["description"].setText("")
		self.setText()
		
	def selectKeys(self):
		self.clearSelectedKeys()
		self.selectKey("UP")
		self.selectKey("DOWN")
		
	def changed(self):
		self.run(justlocal = True)
		self.updateList()
		self.setText()
		
	def setText(self):
		
		self["text"].setText(_cached("T1"))
