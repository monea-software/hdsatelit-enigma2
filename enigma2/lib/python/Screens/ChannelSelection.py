# Modificat de moneasoftware.com si hdsatelit.com, 2026
import os
import time
from Tools.Profile import profile

from .Screen import Screen
from Components.Button import Button
from Components.ServiceList import ServiceList
from Components.ActionMap import NumberActionMap, ActionMap, HelpableActionMap
from Components.MenuList import MenuList
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
profile("ChannelSelection.py 1")
from .EpgSelection import EPGSelection
from enigma import eServiceReference, eEPGCache, eServiceCenter, eRCInput, eTimer, eDVBDB, iPlayableService, iServiceInformation, getPrevAsciiCode, eEnv
from Components.config import config, ConfigSubsection, ConfigText
from Tools.NumericalTextInput import NumericalTextInput
profile("ChannelSelection.py 2")
from Components.NimManager import nimmanager
profile("ChannelSelection.py 2.1")
from Components.Sources.RdsDecoder import RdsDecoder
profile("ChannelSelection.py 2.2")
from Components.Sources.ServiceEvent import ServiceEvent
from Components.Sources.StaticText import StaticText
profile("ChannelSelection.py 2.3")
from Components.Input import Input
profile("ChannelSelection.py 3")
from Components.ChoiceList import ChoiceList, ChoiceEntryComponent
from Components.SystemInfo import SystemInfo
from Screens.InputBox import InputBox, PinInput
from Screens.MessageBox import MessageBox
from Screens.ServiceInfo import ServiceInfo
profile("ChannelSelection.py 4")
from Screens.PictureInPicture import PictureInPicture
from Screens.RdsDisplay import RassInteractive
from ServiceReference import ServiceReference
from Tools.BoundFunction import boundFunction
from os import remove
try:
	# capul listelor de canale (fila TV | Radio, randul „Caută canal…”, OK tinut apasat); fara el listele merg ca inainte
	from Components import HdsCapLista
except ImportError as e:
	HdsCapLista = None
	print("[ChannelSelection] capul listei lipseste: %s" % e)
try:
	# canalul ales pus in Favorite (sau scos) dintr-o apasare: tasta FAV si MENU; fara modul lista merge ca inainte
	from Components import HdsFavorite
except ImportError as e:
	HdsFavorite = None
	print("[ChannelSelection] Favorite dintr-o apasare lipseste: %s" % e)
try:
	# retelele citite la scanare (numele, numerele canalelor date de operator): lista retelei in ordinea numerelor
	from Components import HdsRetele
except ImportError as e:
	HdsRetele = None
	print("[ChannelSelection] retelele scanate lipsesc: %s" % e)
profile("ChannelSelection.py after imports")

FLAG_SERVICE_NEW_FOUND = 64 #define in lib/dvb/idvb.h as dxNewFound = 64

class BouquetSelector(Screen):
	def __init__(self, session, bouquets, selectedFunc, enableWrapAround=False):
		Screen.__init__(self, session)
		self.setTitle(_("Choose bouquet") if _("Choose bouquet") != "Choose bouquet" else "Alegere buchet")

		self.selectedFunc=selectedFunc

		self["actions"] = ActionMap(["OkCancelActions"],
			{
				"ok": self.okbuttonClick,
				"cancel": self.cancelClick
			})
		entrys = [ (x[0], x[1]) for x in bouquets ]
		self["menu"] = MenuList(entrys, enableWrapAround)

	def getCurrent(self):
		cur = self["menu"].getCurrent()
		return cur and cur[1]

	def okbuttonClick(self):
		self.selectedFunc(self.getCurrent())

	def up(self):
		self["menu"].up()

	def down(self):
		self["menu"].down()

	def cancelClick(self):
		self.close(False)

class SilentBouquetSelector:
	def __init__(self, bouquets, enableWrapAround=False, current=0):
		self.bouquets = [b[1] for b in bouquets]
		self.pos = current
		self.count = len(bouquets)
		self.enableWrapAround = enableWrapAround

	def up(self):
		if self.pos > 0 or self.enableWrapAround:
			self.pos = (self.pos - 1) % self.count

	def down(self):
		if self.pos < (self.count - 1) or self.enableWrapAround:
			self.pos = (self.pos + 1) % self.count

	def getCurrent(self):
		return self.bouquets[self.pos]

# csel.bouquet_mark_edit values
OFF = 0
EDIT_BOUQUET = 1
EDIT_ALTERNATIVES = 2

def primaMare(text):
	"""Randul meniului listei cu prima litera mare: traducerile vechi ale randurilor incep cu litera mica in multe limbi
	(ro, en, fr, es, ru, tr...), iar randurile noi ale imaginii cu mare. In turca i mic devine I cu punct."""
	if not text or not text[0].islower():
		return text
	if text[0] == "i":
		try:
			from Components.Language import language
			if language.getLanguage()[:2] == "tr":
				return u"İ" + text[1:]
		except Exception:
			pass
	return text[0].upper() + text[1:]

def append_when_current_valid(current, menu, args, level = 0, key = ""):
	if current and current.valid() and level <= config.usage.setup_level.index:
		menu.append(ChoiceEntryComponent(key, (primaMare(args[0]),) + tuple(args[1:])))

class ChannelContextMenu(Screen):
	def __init__(self, session, csel):

		Screen.__init__(self, session)
		self.setTitle(_("Channel list menu") if _("Channel list menu") != "Channel list menu" else "Meniu listă canale")
		#raise Exception("we need a better summary screen here")
		self.csel = csel
		self.bsel = None

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "NumberActions"],
			{
				"ok": self.okbuttonClick,
				"cancel": self.cancelClick,
				"blue": self.showServiceInPiP
			})
		menu = [ ]

		self.pipAvailable = False
		current = csel.getCurrentSelection()
		if getattr(csel, "hdsEsteRandulToate", None) is not None and csel.hdsEsteRandulToate(current):
			# primul rand al listei pe sateliti nu e nici canal, nici dosar: meniul fara randurile lor
			current = eServiceReference()
		current_root = csel.getRoot()
		current_sel_path = current.getPath()
		current_sel_flags = current.flags
		inBouquetRootList = current_root and current_root.getPath().find('FROM BOUQUET "bouquets.') != -1 #FIXME HACK
		inBouquet = csel.getMutableList() is not None
		haveBouquets = config.usage.multibouquet.value

		# cautarea de canale (ca tasta TEXT sau OK tinut apasat in lista) si trecerea pe lista cealalta (ca tastele
		# TV / RADIO), primele randuri: meniul listei le da si fara taste dedicate
		fav = ""
		if csel.bouquet_mark_edit == OFF and not csel.movemode:
			menu.append(ChoiceEntryComponent(text = (_("Caută canale"), self.hdsCautare)))
			if getattr(csel, "hdsCapPornit", False):
				if csel.mode == MODE_RADIO:
					menu.append(ChoiceEntryComponent(text = (_("Treci la lista TV"), self.hdsComuta)))
				else:
					menu.append(ChoiceEntryComponent(text = (_("Treci la lista radio"), self.hdsComuta)))
			# canalul ales in Favorite sau scos de acolo, ca tasta FAV (randul lipseste pe un dosar sau un marcaj)
			fav = csel.hdsFavText() if hasattr(csel, "hdsFavText") else ""
			if fav:
				menu.append(ChoiceEntryComponent(text = (fav, self.hdsFavorit)))

		if not (current_sel_path or current_sel_flags & (eServiceReference.isDirectory|eServiceReference.isMarker)):
			append_when_current_valid(current, menu, (_("show transponder info"), self.showServiceInformations), level = 2)
		if csel.bouquet_mark_edit == OFF and not csel.movemode:
			if not inBouquetRootList:
				isPlayable = not (current_sel_flags & (eServiceReference.isMarker|eServiceReference.isDirectory))
				if isPlayable:
					if config.ParentalControl.configured.value:
						from Components.ParentalControl import parentalControl
						if parentalControl.getProtectionLevel(csel.getCurrentSelection().toCompareString()) == -1:
							append_when_current_valid(current, menu, (_("add to parental protection"), boundFunction(self.addParentalProtection, csel.getCurrentSelection())), level = 0)
						else:
							append_when_current_valid(current, menu, (_("remove from parental protection"), boundFunction(self.removeParentalProtection, csel.getCurrentSelection())), level = 0)
					if haveBouquets:
						bouquets = self.csel.getBouquetList()
						if bouquets is None:
							bouquetCnt = 0
						else:
							bouquetCnt = len(bouquets)
						if not inBouquet or bouquetCnt > 1:
							append_when_current_valid(current, menu, (_("add service to bouquet"), self.addServiceToBouquetSelected), level = 0)
					else:
						# fara buchete multiple, "add service to favourites" face ce face randul FAV de sus ("Adaugă la
						# Favorite"): un singur rand, cel de sus; acesta ramane numai cand randul FAV lipseste
						if not inBouquet and not fav:
							append_when_current_valid(current, menu, (_("add service to favourites"), self.addServiceToBouquetSelected), level = 0)
				else:
					# HDSatelit: dosarul listei unei retele (numerele operatorului) nu e un satelit: nu se sterge si nu
					# se copiaza ca buchet (cererea nucleului din spatele lui are toate canalele locului)
					dosarRetea = HdsRetele is not None and HdsRetele.e_cale_de_retea(current_sel_path)
					if current_root.getPath().find('FROM SATELLITES') != -1 and not dosarRetea:
						append_when_current_valid(current, menu, (_("remove selected satellite"), self.removeSatelliteServices), level = 0)
					if haveBouquets:
						if not inBouquet and current_sel_path.find("PROVIDERS") == -1 and not dosarRetea:
							append_when_current_valid(current, menu, (_("copy to bouquets"), self.copyCurrentToBouquetList), level = 0)
					if current_sel_path.find("flags == %d" %(FLAG_SERVICE_NEW_FOUND)) != -1:
						append_when_current_valid(current, menu, (_("remove all new found flags"), self.removeAllNewFoundFlags), level = 0)
				if inBouquet:
					append_when_current_valid(current, menu, (_("remove entry"), self.removeCurrentService), level = 0)
				if current_root and current_root.getPath().find("flags == %d" %(FLAG_SERVICE_NEW_FOUND)) != -1:
					append_when_current_valid(current, menu, (_("remove new found flag"), self.removeNewFoundFlag), level = 0)
				if isPlayable and SystemInfo.get("NumVideoDecoders", 1) > 1:
					append_when_current_valid(current, menu, (_("Activate Picture in Picture"), self.showServiceInPiP), level = 0, key = "blue")
					self.pipAvailable = True
			else:
					menu.append(ChoiceEntryComponent(text = (primaMare(_("add bouquet")), self.showBouquetInputBox)))
					append_when_current_valid(current, menu, (_("remove entry"), self.removeBouquet), level = 0)

		if inBouquet: # current list is editable?
			if csel.bouquet_mark_edit == OFF:
				if not csel.movemode:
					append_when_current_valid(current, menu, (_("enable move mode"), self.toggleMoveMode), level = 1)
					if not inBouquetRootList and current_root and not (current_root.flags & eServiceReference.isGroup):
						menu.append(ChoiceEntryComponent(text = (primaMare(_("add marker")), self.showMarkerInputBox)))
						if haveBouquets:
							append_when_current_valid(current, menu, (_("enable bouquet edit"), self.bouquetMarkStart), level = 0)
						else:
							append_when_current_valid(current, menu, (_("enable favourite edit"), self.bouquetMarkStart), level = 0)
						if current_sel_flags & eServiceReference.isGroup:
							append_when_current_valid(current, menu, (_("edit alternatives"), self.editAlternativeServices), level = 2)
							append_when_current_valid(current, menu, (_("show alternatives"), self.showAlternativeServices), level = 2)
							append_when_current_valid(current, menu, (_("remove all alternatives"), self.removeAlternativeServices), level = 2)
						elif not current_sel_flags & eServiceReference.isMarker:
							append_when_current_valid(current, menu, (_("add alternatives"), self.addAlternativeServices), level = 2)
				else:
					append_when_current_valid(current, menu, (_("disable move mode"), self.toggleMoveMode), level = 0)
			else:
				if csel.bouquet_mark_edit == EDIT_BOUQUET:
					if haveBouquets:
						append_when_current_valid(current, menu, (_("end bouquet edit"), self.bouquetMarkEnd), level = 0)
						append_when_current_valid(current, menu, (_("abort bouquet edit"), self.bouquetMarkAbort), level = 0)
					else:
						append_when_current_valid(current, menu, (_("end favourites edit"), self.bouquetMarkEnd), level = 0)
						append_when_current_valid(current, menu, (_("abort favourites edit"), self.bouquetMarkAbort), level = 0)
				else:
						append_when_current_valid(current, menu, (_("end alternatives edit"), self.bouquetMarkEnd), level = 0)
						append_when_current_valid(current, menu, (_("abort alternatives edit"), self.bouquetMarkAbort), level = 0)

		menu.append(ChoiceEntryComponent(text = (primaMare(_("back")), self.cancelClick)))
		self["menu"] = ChoiceList(menu)

	def okbuttonClick(self):
		self["menu"].getCurrent()[0][1]()

	def cancelClick(self):
		self.close(False)

	def hdsCautare(self):
		# meniul se inchide intai; lista deschide cautarea din exitContext (o fereastra se inchide intarziat)
		self.close(("hdsCautare",))

	def hdsComuta(self):
		# la fel: lista trece pe cealalta (TV <-> Radio) abia dupa ce meniul s-a inchis
		self.close(("hdsComuta",))

	def hdsFavorit(self):
		# la fel: canalul in Favorite (sau intrebarea de scoatere) abia dupa ce meniul s-a inchis
		self.close(("hdsFavorit",))

	def showServiceInformations(self):
		self.session.open( ServiceInfo, self.csel.getCurrentSelection() )

	def showBouquetInputBox(self):
		self.session.openWithCallback(self.bouquetInputCallback, InputBox, title=_("Please enter a name for the new bouquet"), text="bouquetname", maxSize=False, visible_width = 56, type=Input.TEXT)

	def bouquetInputCallback(self, bouquet):
		if bouquet is not None:
			self.csel.addBouquet(bouquet, None)
		self.close()

	def addParentalProtection(self, service):
		from Components.ParentalControl import parentalControl
		parentalControl.protectService(service.toCompareString())
		self.close()

	def removeParentalProtection(self, service):
		self.session.openWithCallback(boundFunction(self.pinEntered, service.toCompareString()), PinInput, pinList = [config.ParentalControl.servicepin[0].value], triesEntry = config.ParentalControl.retries.servicepin, title = _("Enter the service pin"), windowTitle = _("Change pin code"))

	def pinEntered(self, service, result):
		if result:
			from Components.ParentalControl import parentalControl
			parentalControl.unProtectService(service)
			self.close()
		else:
			self.session.openWithCallback(self.close, MessageBox, _("The pin code you entered is wrong."), MessageBox.TYPE_ERROR)
			
	def showServiceInPiP(self):
		if not self.pipAvailable:
			return
		if self.session.pipshown:
			del self.session.pip
		self.session.pip = self.session.instantiateDialog(PictureInPicture)
		self.session.pip.show()
		newservice = self.csel.servicelist.getCurrent()
		if self.session.pip.playService(newservice):
			self.session.pipshown = True
			self.session.pip.servicePath = self.csel.getCurrentServicePath()
			self.close(True)
		else:
			self.session.pipshown = False
			del self.session.pip
			self.session.openWithCallback(self.close, MessageBox, _("Could not open Picture in Picture"), MessageBox.TYPE_ERROR)

	def addServiceToBouquetSelected(self):
		bouquets = self.csel.getBouquetList()
		if bouquets is None:
			cnt = 0
		else:
			cnt = len(bouquets)
		if cnt > 1: # show bouquet list
			self.bsel = self.session.openWithCallback(self.bouquetSelClosed, BouquetSelector, bouquets, self.addCurrentServiceToBouquet)
		elif cnt == 1: # add to only one existing bouquet
			self.addCurrentServiceToBouquet(bouquets[0][1], closeBouquetSelection = False)

	def bouquetSelClosed(self, recursive):
		self.bsel = None
		if recursive:
			self.close(False)

	def removeSatelliteServices(self):
		curpath = self.csel.getCurrentSelection().getPath()
		idx = curpath.find("satellitePosition == ")
		if idx != -1:
			tmp = curpath[idx+21:]
			idx = tmp.find(')')
			if idx != -1:
				satpos = int(tmp[:idx])
				eDVBDB.getInstance().removeServices(-1, -1, -1, satpos)
				# numerele de pe antetele listei pe sateliti si lista insasi, fara satelitul scos
				hds_uita_numerele()
				if self.csel.hdsPeRadacinaSateliti():
					self.csel.hdsRefaSateliti()
		self.close()

	def copyCurrentToBouquetList(self):
		self.csel.copyCurrentToBouquetList()
		self.close()

	def removeBouquet(self):
		self.csel.removeBouquet()
		self.close()

	def showMarkerInputBox(self):
		self.session.openWithCallback(self.markerInputCallback, InputBox, title=_("Please enter a name for the new marker"), text="markername", maxSize=False, visible_width = 56, type=Input.TEXT)

	def markerInputCallback(self, marker):
		if marker is not None:
			self.csel.addMarker(marker)
		self.close()

	def addCurrentServiceToBouquet(self, dest, closeBouquetSelection = True):
		self.csel.addServiceToBouquet(dest)
		if self.bsel is not None:
			self.bsel.close(True)
		else:
			self.close(closeBouquetSelection) # close bouquet selection

	def removeCurrentService(self):
		self.csel.removeCurrentService()
		self.close()

	def toggleMoveMode(self):
		self.csel.toggleMoveMode()
		self.close()

	def bouquetMarkStart(self):
		self.csel.startMarkedEdit(EDIT_BOUQUET)
		self.close()

	def bouquetMarkEnd(self):
		self.csel.endMarkedEdit(abort=False)
		self.close()

	def bouquetMarkAbort(self):
		self.csel.endMarkedEdit(abort=True)
		self.close()

	def removeNewFoundFlag(self):
		eDVBDB.getInstance().removeFlag(self.csel.getCurrentSelection(), FLAG_SERVICE_NEW_FOUND)
		self.close()

	def removeAllNewFoundFlags(self):
		curpath = self.csel.getCurrentSelection().getPath()
		idx = curpath.find("satellitePosition == ")
		if idx != -1:
			tmp = curpath[idx+21:]
			idx = tmp.find(')')
			if idx != -1:
				satpos = int(tmp[:idx])
				eDVBDB.getInstance().removeFlags(FLAG_SERVICE_NEW_FOUND, -1, -1, -1, satpos)
		self.close()

	def editAlternativeServices(self):
		self.csel.startMarkedEdit(EDIT_ALTERNATIVES)
		self.close()

	def showAlternativeServices(self):
		self.csel.enterPath(self.csel.getCurrentSelection())
		self.close()

	def removeAlternativeServices(self):
		self.csel.removeAlternativeServices()
		self.close()

	def addAlternativeServices(self):
		self.csel.addAlternativeServices()
		self.csel.startMarkedEdit(EDIT_ALTERNATIVES)
		self.close()

class SelectionEventInfo:
	def __init__(self):
		self["ServiceEvent"] = ServiceEvent()
		self["Service"] = ServiceEvent()
		self["Event"] = ServiceEvent()
		self.servicelist.connectSelChanged(self.__selectionChanged)
		self.timer = eTimer()
		self.timer.callback.append(self.updateEventInfo)
		self.onShown.append(self.updateEventInfo)

	def __selectionChanged(self):
		if self.execing:
			self.timer.start(30, True)

	def updateEventInfo(self):
		cur = self.getCurrentSelection()
		self["ServiceEvent"].newService(cur)
		self["Service"].newService(cur)
		self["Event"].newService(cur)
		if getattr(self, "hdsCapPornit", False):
			self.hdsPuneFelul(cur)
		if getattr(self, "hdsFavPornit", False):
			self.hdsFavEticheta(cur)

class ChannelSelectionEPG:
	def __init__(self):
		self["ChannelSelectEPGActions"] = ActionMap(["ChannelSelectEPGActions"],
			{
				"showEPGList": self.showEPGList,
			})

	def showEPGList(self):
		hdsCapLaLista(self)
		ref=self.getCurrentSelection()
		if ref:
			self.savedService = ref
			self.session.openWithCallback(self.SingleServiceEPGClosed, EPGSelection, ref, serviceChangeCB=self.changeServiceCB)

	def SingleServiceEPGClosed(self, ret=False):
		self.setCurrentSelection(self.savedService)

	def changeServiceCB(self, direction, epg):
		beg = self.getCurrentSelection()
		while True:
			if direction > 0:
				self.moveDown()
			else:
				self.moveUp()
			cur = self.getCurrentSelection()
			if cur == beg or not (cur.flags & eServiceReference.isMarker):
				break
		epg.setService(ServiceReference(self.getCurrentSelection()))

class ChannelSelectionEdit:
	def __init__(self):
		self.entry_marked = False
		self.movemode = False
		self.bouquet_mark_edit = OFF
		self.mutableList = None
		self.__marked = [ ]
		self.saved_title = None
		self.saved_root = None

		class ChannelSelectionEditActionMap(ActionMap):
			def __init__(self, csel, contexts = [ ], actions = { }, prio=0):
				ActionMap.__init__(self, contexts, actions, prio)
				self.csel = csel

			def action(self, contexts, action):
				if action == "cancel":
					self.csel.handleEditCancel()
					return 0 # fall-trough
				elif action == "ok":
					return 0 # fall-trough
				else:
					return ActionMap.action(self, contexts, action)

		self["ChannelSelectEditActions"] = ChannelSelectionEditActionMap(self, ["ChannelSelectEditActions", "OkCancelActions"],
			{
				"contextMenu": self.doContext,
			})

	def getMutableList(self, root=eServiceReference()):
		if not self.mutableList is None:
			return self.mutableList
		serviceHandler = eServiceCenter.getInstance()
		if not root.valid():
			root=self.getRoot()
		list = root and serviceHandler.list(root)
		if list is not None:
			return list.startEdit()
		return None

	def buildBouquetID(self, str):
		tmp = str.lower()
		name = ''
		for c in tmp:
			if (c >= 'a' and c <= 'z') or (c >= '0' and c <= '9'):
				name += c
			else:
				name += '_'
		return name

	def addMarker(self, name):
		current = self.servicelist.getCurrent()
		mutableList = self.getMutableList()
		cnt = 0
		while mutableList:
			str = '1:64:%d:0:0:0:0:0:0:0::%s'%(cnt, name)
			ref = eServiceReference(str)
			if current and current.valid():
				if not mutableList.addService(ref, current):
					self.servicelist.addService(ref, True)
					mutableList.flushChanges()
					break
			elif not mutableList.addService(ref):
				self.servicelist.addService(ref, True)
				mutableList.flushChanges()
				break
			cnt+=1

	def addAlternativeServices(self):
		cur_service = ServiceReference(self.getCurrentSelection())
		root = self.getRoot()
		cur_root = root and ServiceReference(root)
		mutableBouquet = cur_root.list().startEdit()
		if mutableBouquet:
			name = cur_service.getServiceName()
			print("NAME", name)
			if self.mode == MODE_TV:
				str = '1:134:1:0:0:0:0:0:0:0:FROM BOUQUET \"alternatives.%s.tv\" ORDER BY bouquet'%(self.buildBouquetID(name))
			else:
				str = '1:134:2:0:0:0:0:0:0:0:FROM BOUQUET \"alternatives.%s.radio\" ORDER BY bouquet'%(self.buildBouquetID(name))
			new_ref = ServiceReference(str)
			if not mutableBouquet.addService(new_ref.ref, cur_service.ref):
				mutableBouquet.removeService(cur_service.ref)
				mutableBouquet.flushChanges()
				eDVBDB.getInstance().reloadBouquets()
				mutableAlternatives = new_ref.list().startEdit()
				if mutableAlternatives:
					mutableAlternatives.setListName(name)
					if mutableAlternatives.addService(cur_service.ref):
						print("add", cur_service.ref.toString(), "to new alternatives failed")
					mutableAlternatives.flushChanges()
					self.servicelist.addService(new_ref.ref, True)
					self.servicelist.removeCurrent()
					self.servicelist.moveUp()
				else:
					print("get mutable list for new created alternatives failed")
			else:
				print("add", str, "to", cur_root.getServiceName(), "failed")
		else:
			print("bouquetlist is not editable")

	def addBouquet(self, bName, services):
		serviceHandler = eServiceCenter.getInstance()
		mutableBouquetList = serviceHandler.list(self.bouquet_root).startEdit()
		if mutableBouquetList:
			if self.mode == MODE_TV:
				bName += " (TV)"
				str = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"userbouquet.%s.tv\" ORDER BY bouquet'%(self.buildBouquetID(bName))
			else:
				bName += " (Radio)"
				str = '1:7:2:0:0:0:0:0:0:0:FROM BOUQUET \"userbouquet.%s.radio\" ORDER BY bouquet'%(self.buildBouquetID(bName))
			new_bouquet_ref = eServiceReference(str)
			if not mutableBouquetList.addService(new_bouquet_ref):
				mutableBouquetList.flushChanges()
				eDVBDB.getInstance().reloadBouquets()
				mutableBouquet = serviceHandler.list(new_bouquet_ref).startEdit()
				if mutableBouquet:
					mutableBouquet.setListName(bName)
					if services is not None:
						for service in services:
							if mutableBouquet.addService(service):
								print("add", service.toString(), "to new bouquet failed")
					mutableBouquet.flushChanges()
				else:
					print("get mutable list for new created bouquet failed")
				# do some voodoo to check if current_root is equal to bouquet_root
				cur_root = self.getRoot();
				str1 = cur_root and cur_root.toString()
				pos1 = str1 and str1.find("FROM BOUQUET") or -1
				pos2 = self.bouquet_rootstr.find("FROM BOUQUET")
				if pos1 != -1 and pos2 != -1 and str1[pos1:] == self.bouquet_rootstr[pos2:]:
					self.servicelist.addService(new_bouquet_ref)
			else:
				print("add", str, "to bouquets failed")
		else:
			print("bouquetlist is not editable")

	def copyCurrentToBouquetList(self):
		provider = ServiceReference(self.getCurrentSelection())
		providerName = provider.getServiceName()
		serviceHandler = eServiceCenter.getInstance()
		services = serviceHandler.list(provider.ref)
		self.addBouquet(providerName, services and services.getContent('R', True))

	def removeAlternativeServices(self):
		cur_service = ServiceReference(self.getCurrentSelection())
		root = self.getRoot()
		cur_root = root and ServiceReference(root)
		list = cur_service.list()
		first_in_alternative = list and list.getNext()
		if first_in_alternative:
			edit_root = cur_root and cur_root.list().startEdit()
			if edit_root:
				if not edit_root.addService(first_in_alternative, cur_service.ref):
					self.servicelist.addService(first_in_alternative, True)
				else:
					print("couldn't add first alternative service to current root")
			else:
				print("couldn't edit current root!!")
		else:
			print("remove empty alternative list !!")
		self.removeBouquet()
		self.servicelist.moveUp()

	def removeBouquet(self):
		refstr = self.getCurrentSelection().toString()
		print("removeBouquet", refstr)
		self.bouquetNumOffsetCache = { }
		pos = refstr.find('FROM BOUQUET "')
		filename = None
		if pos != -1:
			refstr = refstr[pos+14:]
			pos = refstr.find('"')
			if pos != -1:
				filename = eEnv.resolve('${sysconfdir}/enigma2/') + refstr[:pos]
		self.removeCurrentService()
		try:
			if filename is not None:
				remove(filename)
		except OSError:
			print("error during remove of", filename)

#  multiple marked entry stuff ( edit mode, later multiepg selection )
	def startMarkedEdit(self, type):
		self.savedPath = self.servicePath[:]
		if type == EDIT_ALTERNATIVES:
			self.enterPath(self.getCurrentSelection())
		self.mutableList = self.getMutableList()
		# add all services from the current list to internal marked set in listboxservicecontent
		self.clearMarks() # this clears the internal marked set in the listboxservicecontent
		self.saved_title = self.getTitle()
		pos = self.saved_title.find(')')
		new_title = self.saved_title[:pos+1]
		if type == EDIT_ALTERNATIVES:
			self.bouquet_mark_edit = EDIT_ALTERNATIVES
			new_title += ' ' + _("[alternative edit]")
		else:
			self.bouquet_mark_edit = EDIT_BOUQUET
			if config.usage.multibouquet.value:
				new_title += ' ' + _("[bouquet edit]")
			else:
				new_title += ' ' + _("[favourite edit]")
		self.setTitle(new_title)
		self.__marked = self.servicelist.getRootServices()
		for x in self.__marked:
			self.servicelist.addMarked(eServiceReference(x))
		self.showAllServices()
		hdsFavReface(self)  # in editare tasta FAV nu face nimic: tasta desenata dispare

	def endMarkedEdit(self, abort):
		if not abort and self.mutableList is not None:
			self.bouquetNumOffsetCache = { }
			new_marked = set(self.servicelist.getMarked())
			old_marked = set(self.__marked)
			removed = old_marked - new_marked
			added = new_marked - old_marked
			changed = False
			for x in removed:
				changed = True
				self.mutableList.removeService(eServiceReference(x))
			for x in added:
				changed = True
				self.mutableList.addService(eServiceReference(x))
			if changed:
				self.mutableList.flushChanges()
		self.__marked = []
		self.clearMarks()
		self.bouquet_mark_edit = OFF
		self.mutableList = None
		self.setTitle(self.saved_title)
		self.saved_title = None
		# self.servicePath is just a reference to servicePathTv or Radio...
		# so we never ever do use the asignment operator in self.servicePath
		del self.servicePath[:] # remove all elements
		self.servicePath += self.savedPath # add saved elements
		del self.savedPath
		self.setRoot(self.servicePath[-1])
		hdsFavReface(self)

	def clearMarks(self):
		self.servicelist.clearMarks()

	def doMark(self):
		ref = self.servicelist.getCurrent()
		if self.servicelist.isMarked(ref):
			self.servicelist.removeMarked(ref)
		else:
			self.servicelist.addMarked(ref)

	def removeCurrentService(self):
		ref = self.servicelist.getCurrent()
		mutableList = self.getMutableList()
		if ref.valid() and mutableList is not None:
			if not mutableList.removeService(ref):
				self.bouquetNumOffsetCache = { }
				mutableList.flushChanges() #FIXME dont flush on each single removed service
				self.servicelist.removeCurrent()

	def addServiceToBouquet(self, dest, service=None):
		mutableList = self.getMutableList(dest)
		if not mutableList is None:
			if service is None: #use current selected service
				service = self.servicelist.getCurrent()
			if not mutableList.addService(service):
				self.bouquetNumOffsetCache = { }
				mutableList.flushChanges()
				# do some voodoo to check if current_root is equal to dest
				cur_root = self.getRoot();
				str1 = cur_root and cur_root.toString() or -1
				str2 = dest.toString()
				pos1 = str1.find("FROM BOUQUET")
				pos2 = str2.find("FROM BOUQUET")
				if pos1 != -1 and pos2 != -1 and str1[pos1:] == str2[pos2:]:
					self.servicelist.addService(service)

	def toggleMoveMode(self):
		if self.movemode:
			if self.entry_marked:
				self.toggleMoveMarked() # unmark current entry
			self.movemode = False
			self.pathChangeDisabled = False # re-enable path change
			self.mutableList.flushChanges() # FIXME add check if changes was made
			self.mutableList = None
			self.setTitle(self.saved_title)
			self.saved_title = None
			cur_root = self.getRoot()
			if cur_root and cur_root == self.bouquet_root:
				self.bouquetNumOffsetCache = { }
		else:
			self.mutableList = self.getMutableList()
			self.movemode = True
			self.pathChangeDisabled = True # no path change allowed in movemode
			self.saved_title = self.getTitle()
			new_title = self.saved_title
			pos = self.saved_title.find(')')
			new_title = self.saved_title[:pos+1] + ' ' + _("[move mode]") + self.saved_title[pos+1:]
			self.setTitle(new_title);
		if getattr(self, "hdsCapPornit", False):
			# in mutare capul listei nu se foloseste si nu se arata (hdsDeseneazaCapul)
			self.hdsCapInLista()
		hdsFavReface(self)  # in mutare tasta FAV nu face nimic: tasta desenata dispare

	def handleEditCancel(self):
		if self.movemode: #movemode active?
			self.channelSelected() # unmark
			self.toggleMoveMode() # disable move mode
		elif self.bouquet_mark_edit != OFF:
			self.endMarkedEdit(True) # abort edit mode

	def toggleMoveMarked(self):
		if self.entry_marked:
			self.servicelist.setCurrentMarked(False)
			self.entry_marked = False
		else:
			self.servicelist.setCurrentMarked(True)
			self.entry_marked = True

	def doContext(self):
		# meniul lucreaza pe canalul ales: focusul trece intai in lista, cu selectia aratata
		hdsCapLaLista(self)
		self.session.openWithCallback(self.exitContext, ChannelContextMenu, self)
		
	def exitContext(self, close = False):
		if close == ("hdsCautare",):
			self.hdsCautare()
			return
		if close == ("hdsComuta",):
			self.hdsComutaLista(False)
			return
		if close == ("hdsFavorit",):
			self.hdsFavComuta()
			return
		if close:
			self.cancel()

MODE_TV = 0
MODE_RADIO = 1

# type 1 = digital television service
# type 4 = nvod reference service (NYI)
# type 17 = MPEG-2 HD digital television service
# type 22 = advanced codec SD digital television
# type 24 = advanced codec SD NVOD reference service (NYI)
# type 25 = advanced codec HD digital television
# type 27 = advanced codec HD NVOD reference service (NYI)
# type 31 = HEVC digital television service (0x1F)
# type 32 = HEVC UHD digital television service (0x20)
# type 2 = digital radio sound service
# type 10 = advanced codec digital radio sound service

service_types_tv = '1:7:1:0:0:0:0:0:0:0:(type == 1) || (type == 17) || (type == 22) || (type == 25) || (type == 31) || (type == 32) || (type == 134) || (type == 195)'
service_types_radio = '1:7:2:0:0:0:0:0:0:0:(type == 2) || (type == 10)'

# HDSatelit:
# lista de canale nu se mai deschide goala. Cand locul tinut minte (config.tv.lastroot / config.radio.lastroot) e gol,
# nu mai exista sau duce la o lista fara canale (de ex. Favorite goale dupa flash), se deschide lista „Sateliți" pe
# satelitul canalului curent; in ea cablul si terestrul stau primele, sus, apoi satelitii de la vest la est.
# Hotararile sunt functiile de mai jos, fara nimic din enigma in ele, ca sa se poata proba pe PC
# (test_lista_canale_pornire.py).
HDS_POZ_CABLU = 0xFFFF
HDS_POZ_TERESTRU = 0xEEEE


def hds_cheie_satelit(poz):
	"""Locul unui rand din lista „Sateliți" dupa pozitia lui (namespace >> 16, fara semn): cablul primul, apoi
	terestrul, apoi satelitii dupa pozitie, ca in nucleu (vestul ca negativ: 30,0W, ..., 0,8W, 4,8E, ..., 42,0E)."""
	if poz == HDS_POZ_CABLU:
		return (0, 0)
	if poz == HDS_POZ_TERESTRU:
		return (1, 0)
	if poz > 1800:
		poz -= 3600
	return (2, poz)


def hds_ordoneaza_sateliti(intrari):
	"""intrari: [(poz, rand)] in ordinea data de nucleu -> randurile in ordinea listei „Sateliți". Sortarea e stabila,
	deci „Canale / Furnizori / Nou" ale aceluiasi loc raman impreuna si in aceeasi ordine."""
	return [rand for poz, rand in sorted(intrari, key=lambda x: hds_cheie_satelit(x[0]))]


def hds_lista_are_canale(serviceHandler, ref, adancime=1):
	"""True daca lista data de ref are macar un canal (serviciu, nu marcaj si nu dosar). Un dosar (buchet, satelit)
	se deschide cel mult `adancime` niveluri. Se opreste la primul canal gasit, deci si pe „Toate" (17.000 de canale)
	citeste doar inceputul listei."""
	if ref is None or not ref.valid():
		return False
	cale = ref.getPath()
	if "FROM" in cale and not ("BOUQUET" in cale or "SATELLITES" in cale or "PROVIDERS" in cale):
		# eDVBDB::startQuery opreste enigma2 (eFatal) pe o cerere pe care nu o cunoaste
		return False
	lista = serviceHandler.list(ref)
	if lista is None:
		return False
	while True:
		s = lista.getNext()
		if not s.valid():
			return False
		if s.flags & eServiceReference.isMarker:
			continue
		if s.flags & eServiceReference.isDirectory:
			if adancime > 0 and hds_lista_are_canale(serviceHandler, s, adancime - 1):
				return True
			continue
		return True


def hds_cale_de_pornire(locul, are_canale):
	"""locul: textul din config.tv.lastroot / config.radio.lastroot (referinte despartite prin ';').
	-> referintele (text) de refacut, sau None cand lista s-ar deschide goala: loc gol, loc care nu mai exista sau
	lista fara canale. are_canale(ref_text) spune daca lista de la capatul caii are ce arata."""
	cale = [x for x in (locul or "").split(";") if x != ""]
	if not cale or not are_canale(cale[-1]):
		return None
	return cale


# HDSatelit: lista „Sateliți” e o singura lista pe grupe. Primul rand
# deschide (sau inchide) toate grupele; fiecare loc (cablul, terestrul, apoi satelitii de la vest la est) are un
# rand-antet, inchis („+”) sau deschis („−”), cu numarul de canale; sub un antet deschis stau canalele locului, in
# ordinea dupa nume a dosarului lui. La fiecare deschidere a listei e deschis numai locul canalului de acum, cu cursorul
# pe canal; cautarea (HdsCautareCanale) cauta in toate canalele, oricare ar fi deschise. Antetul e dosarul „Canale” al
# locului, cu numele schimbat; furnizorii si canalele noi ale locului nu mai au rand aici (Furnizori are tasta galbena).
# Fonturile interfetei nu au triunghiuri, dar au „+” si „−” (U+2212). Hotararile fara enigma de mai jos se probeaza pe PC
# (test_lista_sateliti.py).
HDS_SEMN_INCHIS = "+"
HDS_SEMN_DESCHIS = u"\u2212"
# primul rand al listei pe sateliti: un marcaj cu nume (nu se intra in el si nucleul nu il citeste niciodata ca lista)
HDS_REF_TOATE = "1:64:0:0:0:0:0:0:0:0:"
HDS_LAMEDB = "/etc/enigma2/lamedb"


def hds_text_antet(nume, n, deschis, text_numar, neprins=False):
	"""Numele randului-antet al unui loc: semnul starii, numele locului si cate canale are; la o pozitie pe care acest
	receptor n-a prins niciodata semnal (Components/HdsIstoricSemnal.py), un semn scurt la sfarsit."""
	text = u"%s %s \u00b7 %s" % (HDS_SEMN_DESCHIS if deschis else HDS_SEMN_INCHIS, nume, text_numar(n))
	return text + u" \u00b7 " + _("niciodată recepționat") if neprins else text


def hds_pozitii_neprinse(pozitii):
	"""Dintre locurile date (namespace >> 16, fara semn), pozitiile de satelit pe care acest receptor n-a prins niciodata
	semnal. Multime goala cand istoricul e gol sau nu se poate citi (nimic nu se semneaza din nestiinta)."""
	try:
		from Components import HdsIstoricSemnal
		ist = HdsIstoricSemnal.istoric()
		return set(p for p in pozitii if ist.prinsa(p) is False)
	except Exception as e:
		print("[ChannelSelection] istoricul semnalului: %s" % e)
		return set()


def hds_poz_din_text(text):
	"""Locul (namespace >> 16, fara semn) din textul unei referinte DVB (toString), sau None."""
	parti = (text or "").split(":")
	if len(parti) < 7:
		return None
	try:
		return int(parti[6] or "0", 16) >> 16
	except ValueError:
		return None


def hds_numara_pe_pozitii(texte):
	"""[referinte ca text] -> {loc: cate canale}: numarul de pe antetele inchise, dintr-o singura cerere la nucleu."""
	numere = {}
	for t in texte:
		poz = hds_poz_din_text(t)
		if poz is not None:
			numere[poz] = numere.get(poz, 0) + 1
	return numere


def hds_pas_in_bloc(i, prim, ultim, directie):
	"""Randul de dupa (directie > 0) sau dinaintea lui i in blocul de canale [prim, ultim] al unui loc deschis, cu
	trecere de la un capat la celalalt (P+ / P- raman in satelitul canalului); None cand i nu e in bloc."""
	if prim > ultim or not prim <= i <= ultim:
		return None
	if directie > 0:
		return prim if i >= ultim else i + 1
	return ultim if i <= prim else i - 1


def hds_antet_vecin(antete, i, directie):
	"""CH+ / CH- in lista pe sateliti: antetul de dupa / dinaintea randului i (indicii antetelor, crescator), cu trecere
	de la capat la capat; None fara antete."""
	if not antete:
		return None
	if directie > 0:
		for a in antete:
			if a > i:
				return a
		return antete[0]
	for a in reversed(antete):
		if a < i:
			return a
	return antete[-1]


def hds_trece_peste_capat(pas, sus_inainte, sus_dupa, index, la_sfarsit):
	"""STANGA (pas -1) / DREAPTA (pas 1) in lista, dupa pagina mutata de lista: pagina de pe ecran nu s-a schimbat si
	cursorul a ajuns la capat, deci prima / ultima pagina era deja pe ecran: lista trece la celalalt capat."""
	if sus_inainte != sus_dupa:
		return False
	return index == 0 if pas < 0 else bool(la_sfarsit)


def hds_e_loc_de_satelit(cale):
	"""Calea unui dosar care tine de un loc din „Sateliți” (canalele, furnizorii sau canalele noi ale unui satelit):
	un loc tinut minte de dinainte de lista pe grupe se deschide acum in lista pe grupe. Lista unei retele (in ordinea
	numerelor operatorului, Components/HdsRetele.py) nu e un loc: se redeschide ea."""
	if HdsRetele is not None and HdsRetele.e_cale_de_retea(cale):
		return False
	return "satellitePosition ==" in (cale or "")


# randurile 'Furnizori' si 'Nou' ale unui loc din 'Sateliți' (setarea config.usage.hds_lista_furnizori_nou), in ordinea
# lor sub antet
HDS_FURNIZORI = "furnizori"
HDS_NOU = "nou"
HDS_ORDINE_EXTRA = (HDS_FURNIZORI, HDS_NOU)


def hds_fel_extra(cale):
	"""Felul unui dosar din lista nucleului 'FROM SATELLITES': HDS_FURNIZORI (furnizorii locului), HDS_NOU (canalele
	noi ale locului) sau None (dosarul 'Canale', care devine antetul locului)."""
	cale = cale or ""
	if "FROM PROVIDER" in cale:
		return HDS_FURNIZORI
	if ("flags == %d" % FLAG_SERVICE_NEW_FOUND) in cale:
		return HDS_NOU
	return None


def hds_randuri_extra(extra):
	"""[(fel, dosar)] ale unui loc -> aceleasi, intai furnizorii, apoi canalele noi (cate unul din fiecare)."""
	rez = []
	for fel in HDS_ORDINE_EXTRA:
		for f, dosar in extra:
			if f == fel:
				rez.append((f, dosar))
				break
	return rez


def hds_nume_extra(nume_loc, fel):
	"""Numele randului: '19,2°E Astra 1N - Furnizori' / '... - Nou' (aceleasi texte ca lista de dinainte)."""
	return u"%s - %s" % (nume_loc, _("Providers") if fel == HDS_FURNIZORI else _("New"))


_hds_numere = {}


def hds_semnatura_lamedb(cale=HDS_LAMEDB):
	try:
		st = os.stat(cale)
		return (st.st_mtime, st.st_size)
	except OSError:
		return None


def hds_uita_numerele():
	_hds_numere.clear()


def hds_ecran_radio_dupa_ok():
	"""OK pe un post in lista: ecranul radio al barei (Screens/HdsEcranRadio.py, okDinLista) se arata pe tot ecranul
	daca merge un post de radio, si daca fusese ascuns cu EXIT. Un canal TV nu il schimba. Fara bara sau fara ecranul
	radio nu face nimic."""
	try:
		from Screens.InfoBar import InfoBar
		leg = getattr(InfoBar.instance, "hdsRadio", None)
		if leg is not None:
			leg.okDinLista()
	except Exception as e:
		print("[ChannelSelection] ecranul radio dupa OK: %s" % e)


def hds_dupa_inchidere(functie):
	"""functie(infobar) imediat ce bara revine in fata, dupa ce lista de canale se inchide. Lista TV si lista radio
	(cu „mod radio separat” oprit) sunt ecrane diferite, deschise de bara (InfoBar.showTv / showRadio); o lista nu o
	deschide direct pe cealalta, ca EXIT din a doua sa duca tot la bara.
	Functia se pune PRIMA in InfoBar.onExecBegin, o singura data: Screen.execBegin opreste sirul dupa primul ecran
	deschis din el, iar alte functii ale barii pot deschide unul (de ex. un mesaj in asteptare, ca eroarea de zap);
	onFirstExecBegin ruleaza abia dupa ele si s-ar pierde. Mesajul ramane in asteptare si se arata la intoarcerea in
	bara. -> False fara bara."""
	try:
		from Screens.InfoBar import InfoBar
	except ImportError:
		return False
	infobar = InfoBar.instance
	if infobar is None:
		return False
	cerut = time.time()

	def dupa():
		try:
			infobar.onExecBegin.remove(dupa)
		except ValueError:
			pass
		# numai la intoarcerea de acum; bara revenita in fata mult mai tarziu (lista nu era chiar deasupra ei) nu
		# mai deschide nimic
		if abs(time.time() - cerut) < 3:
			functie(infobar)
	infobar.onExecBegin.insert(0, dupa)
	return True


class HdsTacutActionMap(ActionMap):
	"""ActionMap fara randul „action -> ...” din jurnal: harta capului listei (prioritatea -1) vede fiecare sageata si
	fiecare repetare inaintea listei si pe cele mai multe le lasa listei (intoarce 0); un rand in jurnal la fiecare ar fi
	numai zgomot pe eMMC. Actiunea necunoscuta se scrie in continuare."""
	def action(self, context, action):
		if action in self.actions:
			res = self.actions[action]()
			if res is not None:
				return res
			return 1
		print("unknown action %s/%s! typo in keymap?" % (context, action))
		return 0


# randul capului pe care se deschide lista urmatoare: FILA cand s-a trecut pe ea din fila celeilalte liste
# (o singura data, cel mult cateva secunde dupa cerere)
_hds_cap_urmator = [None, 0.0]


def hds_cap_urmator_pune(rand):
	_hds_cap_urmator[0] = rand
	_hds_cap_urmator[1] = time.time()


def hds_cap_urmator_ia():
	rand, cand = _hds_cap_urmator
	_hds_cap_urmator[0] = None
	if rand is not None and abs(time.time() - cand) < 5:
		return rand
	return None

def hdsCapLaLista(ecran):
	"""Tastele care lucreaza pe canalul ales in lista (MENU, INFO, EPG, cifrele, marcajele): cu focusul in capul listei
	selectia e stinsa, deci focusul trece intai in lista, ca omul sa vada canalul pe care lucreaza tasta."""
	cap = getattr(ecran, "hdsCap", None)
	if getattr(ecran, "hdsCapPornit", False) and cap is not None and cap.focus is not HdsCapLista.LISTA:
		ecran.hdsCapInLista()


def hdsFavReface(ecran):
	"""Tasta FAV desenata jos in lista, dupa starea de acum (canalul ales, mutarea, editarea); nimic fara Favorite."""
	if getattr(ecran, "hdsFavPornit", False):
		ecran.hdsFavEticheta()


# numarul pastilelor randului grupelor din capul listei (Components/HdsCapLista.GRUPE_LISTEI)
HDS_CAP_GRUPE = 5


class ChannelSelectionBase(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Channel Selection") if _("Channel Selection") != "Channel Selection" else "Selectare canale")

		self["key_red"] = Button(_("All"))
		self["key_green"] = Button(_("Satellites"))
		self["key_yellow"] = Button(_("Provider"))
		self["key_blue"] = Button(_("Favourites"))
		# HDSatelit: cautarea de canale (Screens/HdsCautareCanale.py), in bara de jos a skinului HDSatelit
		self["key_text"] = StaticText("TEXT  Căutare")
		self["HdsCautareActions"] = ActionMap(["HdsCautareActions"],
			{
				"cautare": self.hdsCautare,
			})

		self["list"] = ServiceList()
		self.servicelist = self["list"]

		self.numericalTextInput = NumericalTextInput()
		self.numericalTextInput.setUseableChars('1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ')

		self.servicePathTV = [ ]
		self.servicePathRadio = [ ]
		self.servicePath = [ ]
		self.rootChanged = False

		self.mode = MODE_TV

		self.pathChangeDisabled = False

		self.bouquetNumOffsetCache = { }

		# HDSatelit: lista „Sateliți” pe grupe (hdsUmpleSateliti). hdsIntrariSateliti: [(loc,
		# antet)] din ultima umplere; hdsBlocuri: [(loc, randul antetului, primul canal, ultimul canal)]; hdsDeschise:
		# locurile deschise; hdsProaspata: lista s-a inchis de la ultima folosire, deci la urmatoarea (deschiderea sau
		# sagetile si P+/P- de pe bara) e deschis iar numai locul canalului de acum (hdsNormalizeaza)
		self.hdsIntrariSateliti = [ ]
		self.hdsIntrariFluxuri = { }
		self.hdsBlocuri = [ ]
		self.hdsDeschise = set()
		self.hdsRandToate = None
		self.hdsSemnUmplere = None
		self.hdsProaspata = True

		# capul listei (hdsPornesteCapul): oprit pana il porneste una din listele imaginii
		self.hdsCapPornit = False
		self.hdsCapVazut = False
		self.hdsComutare = False
		# Favorite dintr-o apasare (hdsPornesteFavorite): numai lista TV si lista radio ale imaginii
		self.hdsFavPornit = False
		# lista unei retele (hdsReteaLaZi): hdsGeneratieRetea = versiunea fisierului retelelor de la umplere; cat lista e
		# in fata, fisierul se priveste la fiecare HDS_VEGHE_RETEA_MS (o scanare noua, un fisier pus de mana)
		self.hdsGeneratieRetea = None
		self.hdsCeasRetea = eTimer()
		self.hdsCeasRetea.callback.append(self.hdsVegheRetea)
		self.onExecBegin.append(self.hdsPornesteVeghea)

		self["ChannelSelectBaseActions"] = NumberActionMap(["ChannelSelectBaseActions", "NumberActions", "InputAsciiActions"],
			{
				"showFavourites": self.showFavourites,
				"showAllServices": self.showAllServices,
				"showProviders": self.showProviders,
				"showSatellites": self.showSatellites,
				"nextBouquet": self.nextBouquet,
				"prevBouquet": self.prevBouquet,
				"nextMarker": self.nextMarker,
				"prevMarker": self.prevMarker,
				"gotAsciiCode": self.keyAsciiCode,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				"0": self.keyNumber0
			})
		self.recallBouquetMode()

	def getBouquetNumOffset(self, bouquet):
		if not config.usage.multibouquet.value:
			return 0
		str = bouquet.toString()
		offsetCount = 0
		if str not in self.bouquetNumOffsetCache:
			serviceHandler = eServiceCenter.getInstance()
			bouquetlist = serviceHandler.list(self.bouquet_root)
			if not bouquetlist is None:
				while True:
					bouquetIterator = bouquetlist.getNext()
					if not bouquetIterator.valid(): #end of list
						break
					self.bouquetNumOffsetCache[bouquetIterator.toString()]=offsetCount
					if not (bouquetIterator.flags & eServiceReference.isDirectory):
						continue
					servicelist = serviceHandler.list(bouquetIterator)
					if not servicelist is None:
						while True:
							serviceIterator = servicelist.getNext()
							if not serviceIterator.valid(): #check if end of list
								break
							playable = not (serviceIterator.flags & (eServiceReference.isDirectory|eServiceReference.isMarker))
							if playable:
								offsetCount += 1
		return self.bouquetNumOffsetCache.get(str, offsetCount)

	def recallBouquetMode(self):
		if self.mode == MODE_TV:
			self.service_types = service_types_tv
			if config.usage.multibouquet.value:
				self.bouquet_rootstr = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet'
			else:
				self.bouquet_rootstr = '%s FROM BOUQUET "userbouquet.favourites.tv" ORDER BY bouquet'%(self.service_types)
		else:
			self.service_types = service_types_radio
			if config.usage.multibouquet.value:
				self.bouquet_rootstr = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.radio" ORDER BY bouquet'
			else:
				self.bouquet_rootstr = '%s FROM BOUQUET "userbouquet.favourites.radio" ORDER BY bouquet'%(self.service_types)
		self.bouquet_root = eServiceReference(self.bouquet_rootstr)

	def setTvMode(self):
		self.mode = MODE_TV
		self.servicePath = self.servicePathTV
		self.recallBouquetMode()
		title = self.getTitle()
		pos = title.find(" (")
		if pos != -1:
			title = title[:pos]
		title += " (TV)"
		self.setTitle(title)
		if self.hdsCapPornit:
			self.hdsDeseneazaCapul()

	def setRadioMode(self):
		self.mode = MODE_RADIO
		self.servicePath = self.servicePathRadio
		self.recallBouquetMode()
		title = self.getTitle()
		pos = title.find(" (")
		if pos != -1:
			title = title[:pos]
		title += " (Radio)"
		self.setTitle(title)
		if self.hdsCapPornit:
			self.hdsDeseneazaCapul()

	def setRoot(self, root, justSet=False):
		path = root.getPath()
		inBouquetRootList = path.find('FROM BOUQUET "bouquets.') != -1 #FIXME HACK
		pos = path.find('FROM BOUQUET')
		isBouquet = (pos != -1) and (root.flags & eServiceReference.isDirectory)
		# versiunea fisierului retelelor INAINTEA umplerii (si cand reteaua nu mai e in fisier: poate reveni)
		self.hdsGeneratieRetea = self.hdsGeneratieRetelei(root)
		retea = self.hdsReteaRadacinii(root)
		self.hdsNumereRetea = {}
		if retea is not None:
			# HDSatelit: lista unei retele (cablul operatorului): canalele in ordinea numerelor operatorului, cu numarul
			# lui in coloana numarului; nucleul nu stie ordinea, deci lista se umple aici (hdsUmpleRetea)
			self.servicelist.setMode(ServiceList.MODE_FAVOURITES)
			self.servicelist.setNumberOffset(0)
			self.servicelist.setRoot(root, True)
			self.hdsUmpleRetea(retea)
		else:
			if hasattr(self.servicelist, "hdsNumereOperator"):
				self.servicelist.hdsNumereOperator(None)
			if not inBouquetRootList and isBouquet:
				self.servicelist.setMode(ServiceList.MODE_FAVOURITES)
				self.servicelist.setNumberOffset(self.getBouquetNumOffset(root))
			else:
				self.servicelist.setMode(ServiceList.MODE_NORMAL)
			self.servicelist.setRoot(root, justSet)
		self.rootChanged = True
		self.buildTitleString()
		self.hdsPuneListaGoala(root)
		if getattr(self, "hdsCapPornit", False) and not self.hdsComutare:
			# alta lista (tastele colorate, FAV, CH+/-, intrarea intr-un dosar): cursorul e iar in ea
			self.hdsCapInLista()

	def removeModeStr(self, str):
		if self.mode == MODE_TV:
			pos = str.find(' (TV)')
		else:
			pos = str.find(' (Radio)')
		if pos != -1:
			return str[:pos]
		return str

	def getServiceName(self, ref):
		# HDSatelit: lista unei retele are numele retelei din semnal (titlul: "Sateliți/Cablu Targu Jiu")
		retea = self.hdsReteaRadacinii(ref)
		if retea is not None:
			r = HdsRetele.retea(retea)
			return (r or {}).get("nume") or ref.getName() or _("Cable")
		# HDSatelit: o radacina fara nume care nu e buchet (Sateliți, Toate, Furnizori) nu se mai cere
		# nucleului: eServiceFactoryDVB::info o trimite la informatia de buchet, care nu o gaseste, scrie in jurnal
		# „getBouquet failed" si intoarce un nume gol; numele vine oricum din randurile de mai jos
		if (ref.flags & eServiceReference.canDescent) and not ref.getName() and 'FROM BOUQUET' not in ref.getPath():
			str = ""
		else:
			str = self.removeModeStr(ServiceReference(ref).getServiceName())
		if not str:
			pathstr = ref.getPath()
			if 'FROM PROVIDERS' in pathstr:
				return _("Provider")
			if 'FROM SATELLITES' in pathstr:
				return _("Satellites")
			if ') ORDER BY name' in pathstr:
				return _("All")
		elif str == "Favourites":
			return _("Favourites")
		return str

	def buildTitleString(self):
		titleStr = self.getTitle()
		pos = titleStr.find(']')
		if pos == -1:
			pos = titleStr.find(')')
		if pos != -1:
			titleStr = titleStr[:pos+1]
			Len = len(self.servicePath)
			if Len > 0:
				base_ref = self.servicePath[0]
				base_name = self.getServiceName(base_ref)
				if Len > 1:
					end_ref = self.servicePath[Len-1]
					end_name = self.getServiceName(end_ref)
					path_str = getattr(base_ref, 'getPath', lambda: '')() or ''
					if base_name in ("Bouquets", "bouquets") or 'FROM BOUQUET "bouquets.' in path_str:
						if Len > 2:
							titleStr += ' .../' + end_name
						else:
							titleStr += ' ' + end_name
					else:
						titleStr += ' ' + base_name + ('/../' if Len > 2 else '/') + end_name
				else:
					titleStr += ' ' + base_name
				self.setTitle(titleStr)

	def moveUp(self):
		self.servicelist.moveUp()

	def moveDown(self):
		self.servicelist.moveDown()

	def clearPath(self):
		del self.servicePath[:]

	def enterPath(self, ref, justSet=False):
		self.servicePath.append(ref)
		self.setRoot(ref, justSet)

	def pathUp(self, justSet=False):
		prev = self.servicePath.pop()
		if self.servicePath:
			current = self.servicePath[-1]
			self.setRoot(current, justSet)
			if not justSet:
				self.setCurrentSelection(prev)
		return prev

	def isBasePathEqual(self, ref):
		if len(self.servicePath) > 1 and self.servicePath[0] == ref:
			return True
		return False

	def isPrevPathEqual(self, ref):
		length = len(self.servicePath)
		if length > 1 and self.servicePath[length-2] == ref:
			return True
		return False

	def preEnterPath(self, refstr):
		return False

	def showAllServices(self):
		self.hdsAlesDeOm = time.time()  # lista aleasa de om (FAV, culori): se arata si goala
		if not self.pathChangeDisabled:
			refstr = '%s ORDER BY name'%(self.service_types)
			if not self.preEnterPath(refstr):
				ref = eServiceReference(refstr)
				currentRoot = self.getRoot()
				if currentRoot is None or currentRoot != ref:
					self.clearPath()
					self.enterPath(ref)

	def showSatellites(self):
		"""Tasta VERDE si pastila „Sateliți” din capul listei: lista clasica a satelitilor, toti inchisi (si cel al
		canalului de acum), cu cursorul pe randul satelitului canalului de acum; OK deschide unul. Deschiderea listei
		si intoarcerea dintr-un dosar raman cu satelitul canalului de acum deschis (hdsArataSateliti)."""
		self.hdsArataSateliti(inchise=True)

	def hdsArataSateliti(self, inchise=False):
		self.hdsAlesDeOm = time.time()  # lista aleasa de om (FAV, culori): se arata si goala
		if inchise and self.hdsPeRadacinaSateliti():
			# deja in lista pe sateliti: se inchid toate, cursorul pe randul satelitului canalului de acum
			self.hdsDeschise = set()
			self.hdsRefaSateliti()
			return
		if not self.pathChangeDisabled:
			refstr = self.hdsSatelitiRefStr()
			if not self.preEnterPath(refstr):
				ref = eServiceReference(refstr)
				justSet=False
				prev = None

				if self.isBasePathEqual(ref):
					if self.isPrevPathEqual(ref):
						justSet=True
					prev = self.pathUp(justSet)
				else:
					currentRoot = self.getRoot()
					if currentRoot is None or currentRoot != ref:
						justSet=True
						self.clearPath()
						self.enterPath(ref, True)
				if justSet:
					self.hdsUmpleSateliti(ref, prev, inchise=inchise)

	# HDSatelit: lista „Sateliți" cu cablul si terestrul sus si pe satelitul canalului curent; locul tinut
	# minte gol, disparut sau fara canale deschide „Sateliți" in loc de o lista goala (vezi hds_cale_de_pornire)
	def hdsSatelitiRefStr(self):
		return '%s FROM SATELLITES ORDER BY satellitePosition'%(self.service_types)

	def hdsUmpleSateliti(self, ref, prev=None, canonic=None, cursor=None, canal=None, inchise=False):
		"""Umple lista „Sateliți” (radacina ref, pusa cu justSet), lista pe grupe: primul rand („Deschide toate
		canalele pe toți sateliții” / „Închide ceilalți sateliți”, cand sunt cel putin doua locuri), apoi cate un antet
		pe loc (cablul, terestrul, satelitii dupa pozitie), cu canalele locurilor deschise sub antet, apoi dosarele
		DAB+ / DVB-T2 din satelit si „Transponder curent”. Ordinea se pune aici: finishFill() ar sorta din nou in nucleu.
		canonic (implicit cand nu e prev): deschis numai locul canalului de acum; altfel raman locurile deschise de om.
		Cursorul: pe cursor, daca e in lista; altfel pe prev (intoarcerea dintr-un dosar); altfel pe canal (implicit
		canalul de acum), sau pe randul locului lui."""
		inceput = time.time()
		if canonic is None:
			canonic = prev is None
		if canal is None:
			canal = self.hdsCanalulCurent()
		intrari = [ ]
		cu_extra = self.hdsFurnizoriNou()
		extra = { }
		serviceHandler = eServiceCenter.getInstance()
		servicelist = serviceHandler.list(ref)
		if servicelist is not None:
			while True:
				service = servicelist.getNext()
				if not service.valid(): #check if end of list
					break
				fel = hds_fel_extra(service.getPath())
				if fel is not None:
					# furnizorii si canalele noi ale locului: fara setare, un singur rand pe loc (furnizorii: tasta
					# galbena); cu setarea, randuri sub antetul locului
					if cu_extra:
						extra.setdefault(service.getUnsignedData(4) >> 16, [ ]).append((fel, service))
					continue
				unsigned_orbpos = service.getUnsignedData(4) >> 16
				intrari.append((unsigned_orbpos, (unsigned_orbpos, service, self.hdsNumeLoc(service))))
		grupe = hds_ordoneaza_sateliti(intrari)
		self.hdsIntrariSateliti = [(poz, service) for poz, service, nume in grupe]
		if inchise:
			# VERDE: lista clasica, toti satelitii inchisi
			self.hdsDeschise = set()
		elif canonic:
			self.hdsDeschise = self.hdsDeschiseCanonic(canal)
		numere = self.hdsNumerePeLocuri() if grupe else {}
		neprinse = hds_pozitii_neprinse([poz for poz, service, nume in grupe])
		self.hdsBlocuri = [ ]
		self.hdsRandToate = None
		n = 0
		if len(grupe) > 1:
			toate = all(poz in self.hdsDeschise for poz, service, nume in grupe)
			rand = eServiceReference(HDS_REF_TOATE)
			rand.setName(_("Închide ceilalți sateliți") if toate else _("Deschide toate canalele pe toți sateliții"))
			self.servicelist.addService(rand)
			self.hdsRandToate = rand
			n += 1
		for poz, service, nume in grupe:
			deschis = poz in self.hdsDeschise
			canale = self.hdsCanaleLoc(service) if deschis else [ ]
			numar = len(canale) if deschis else numere.get(poz, 0)
			service.setName(hds_text_antet(nume, numar, deschis, self.hdsTextNumar, poz in neprinse))
			self.servicelist.addService(service)
			randuri_extra = hds_randuri_extra(extra.get(poz, [ ]))
			for fel, dosar in randuri_extra:
				dosar.setName(hds_nume_extra(nume, fel))
				self.servicelist.addService(dosar)
			# listele retelelor locului (cablul: reteaua operatorului), in ordinea numerelor operatorului, sub antet
			randuri_retele = self.hdsDosareRetele(poz)
			for dosar in randuri_retele:
				self.servicelist.addService(dosar)
			k = len(randuri_extra) + len(randuri_retele)
			for c in canale:
				self.servicelist.addService(c)
			self.hdsBlocuri.append((poz, n, n + 1 + k, n + k + len(canale)))
			n += 1 + k + len(canale)
		# DAB+ / DVB-T2 din satelit: dosarul buchetului (posturile nu sunt in lamedb, deci nu au satelit aici)
		self.hdsIntrariFluxuri = self.hdsAdaugaBucheteFluxuri()
		cur_ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if cur_ref:
			pos = self.service_types.rfind(':')
			refstr = '%s (channelID == %08x%04x%04x) && %s ORDER BY name' %(self.service_types[:pos+1],
				cur_ref.getUnsignedData(4), # NAMESPACE
				cur_ref.getUnsignedData(2), # TSID
				cur_ref.getUnsignedData(3), # ONID
				self.service_types[pos+1:])
			tp = eServiceReference(refstr)
			tp.setName(_("Current Transponder"))
			self.servicelist.addService(tp)
		# FillFinished fara sort(): ordinea de mai sus ramane (finishFill = FillFinished + sortarea din nucleu)
		self.servicelist.l.FillFinished()
		# etichetele DVB-I ale canalelor puse mai sus (ServiceList.hdsEticheteDvbI)
		if hasattr(self.servicelist, "hdsEticheteDvbI"):
			self.servicelist.hdsEticheteDvbI()
		self.hdsSemnUmplere = self.hdsSemnaturaUmplerii()
		if cursor is not None and self.hdsInLista(cursor) and self.hdsPuneCursorul(cursor):
			pass
		elif prev is not None:
			self.setCurrentSelection(prev)
		else:
			self.hdsCursorPeCanal(canal)
		durata = (time.time() - inceput) * 1000
		if durata >= 100:
			print("[ChannelSelection] lista pe sateliti: %d randuri, %d locuri deschise, %.0f ms" % (n,
				len(self.hdsDeschise), durata))

	def hdsFurnizoriNou(self):
		"""Setarea 'Furnizori și Nou la fiecare satelit' (config.usage.hds_lista_furnizori_nou, oprita din fabrica)."""
		setare = getattr(getattr(config, "usage", None), "hds_lista_furnizori_nou", None)
		return bool(setare is not None and setare.value)

	def hdsSemnaturaUmplerii(self):
		"""Ce schimba lista pe sateliti fara ca omul sa o atinga: lamedb, setarea randurilor 'Furnizori' / 'Nou' si
		fisierul retelelor (dosarele listelor retelelor, hdsDosareRetele)."""
		generatie = None
		if HdsRetele is not None:
			try:
				generatie = HdsRetele.generatie()
			except Exception as e:
				print("[ChannelSelection] fisierul retelelor: %s" % e)
		return (hds_semnatura_lamedb(), self.hdsFurnizoriNou(), generatie)

	def hdsNumeLoc(self, service):
		"""Numele locului unui dosar din „Sateliți”: satelitul din lista tunerelor, „Cablu”, „Terestru”, sau pozitia."""
		unsigned_orbpos = service.getUnsignedData(4) >> 16
		orbpos = service.getData(4) >> 16
		if orbpos < 0:
			orbpos += 3600
		try:
			nume = str(nimmanager.getSatDescription(orbpos))
		except:
			nume = None
		if nume is not None:
			# numele cu pozitia in fata, scrisa ca in restul imaginii (Components/HdsGrade.numeSatelit): '19.2E Astra
			# 1N/1P' din satellites.xml devine '19,2°E Astra 1N/1P'; pozitia din nume, cand numele o are
			try:
				from Components.HdsGrade import numeSatelit
				return numeSatelit(orbpos, nume) or nume
			except ImportError:
				return nume
		else:
			if unsigned_orbpos == 0xFFFF: #Cable
				return _("Cable")
			elif unsigned_orbpos == 0xEEEE: #Terrestrial
				return _("Terrestrial")
			# pozitia in limba meniului, ca in restul imaginii (Components/HdsGrade.py)
			try:
				from Components.HdsGrade import pozitieOrbitala
				return pozitieOrbitala(orbpos) or str(orbpos)
			except ImportError:
				return str(orbpos)

	def hdsTextNumar(self, n):
		try:
			from Components.HdsIndexCanale import text_numar
			return text_numar(n)
		except Exception:
			return str(n)

	def hdsNumerePeLocuri(self):
		"""{loc: cate canale} pentru antetele inchise, din lista „Toate” a modului (o singura cerere la nucleu, apoi
		numai textele referintelor); tinute minte pana se schimba lamedb (data si marimea fisierului)."""
		sem = hds_semnatura_lamedb()
		cheie = (self.service_types, sem)
		if sem is not None and cheie in _hds_numere:
			return _hds_numere[cheie]
		inceput = time.time()
		texte = [ ]
		try:
			lista = eServiceCenter.getInstance().list(eServiceReference("%s ORDER BY name" % self.service_types))
			if lista is not None:
				texte = lista.getContent("S", False) or [ ]
		except Exception as e:
			print("[ChannelSelection] numerele locurilor: %s" % e)
		numere = hds_numara_pe_pozitii(texte)
		if sem is not None:
			for k in [k for k in _hds_numere if k[1] != sem]:
				del _hds_numere[k]
			_hds_numere[cheie] = numere
		durata = (time.time() - inceput) * 1000
		if durata >= 100:
			print("[ChannelSelection] numerele locurilor: %d canale in %.0f ms" % (len(texte), durata))
		return numere

	def hdsCanaleLoc(self, service):
		"""Canalele unui loc deschis, in ordinea dupa nume a dosarului lui (ca dupa OK pe dosar, inainte)."""
		try:
			lista = eServiceCenter.getInstance().list(service)
			return (lista.getContent("R", True) or [ ]) if lista is not None else [ ]
		except Exception as e:
			print("[ChannelSelection] canalele locului: %s" % e)
			return [ ]

	def hdsPozCanal(self, canal):
		"""Locul unui canal DVB din lamedb (namespace >> 16), sau None (dosar, marcaj, flux, post DAB+ / DVB-T2)."""
		if canal is None or not canal.valid() or canal.type != 1 or canal.getPath():
			return None
		if canal.flags & (eServiceReference.isDirectory | eServiceReference.isMarker):
			return None
		return canal.getUnsignedData(4) >> 16

	def hdsDeschiseCanonic(self, canal=None):
		"""Starea de la deschiderea listei: deschis numai locul canalului (implicit cel de acum; niciunul pentru un
		canal fara loc)."""
		poz = self.hdsPozCanal(canal if canal is not None else self.hdsCanalulCurent())
		if poz is not None and any(p == poz for p, intrare in self.hdsIntrariSateliti):
			return set([poz])
		return set()

	def hdsPuneCursorul(self, ref):
		"""Cursorul pe ref, daca e in lista. setCurrent pe o referinta lipsa muta cursorul la capatul listei, deci se
		verifica. -> True daca cursorul e pe ref."""
		if ref is None or not ref.valid():
			return False
		self.servicelist.setCurrent(ref)
		return self.getCurrentSelection() == ref

	def hdsInLista(self, ref):
		"""ref poate fi in lista pe sateliti de acum: un rand fix (primul rand, un antet, un dosar) sau un canal al unui
		loc deschis (fara asta setCurrent ar muta cursorul la capatul listei)."""
		if ref is None or not ref.valid():
			return False
		if ref.flags & (eServiceReference.isDirectory | eServiceReference.isMarker):
			return True
		poz = self.hdsPozCanal(ref)
		return poz is not None and poz in self.hdsDeschise

	def hdsCursorPeCanal(self, canal):
		"""Cursorul pe canal, daca locul lui e deschis; altfel pe randul locului lui (antetul, dosarul DAB+ / DVB-T2),
		altfel pe primul rand."""
		poz = self.hdsPozCanal(canal)
		if poz is not None and poz in self.hdsDeschise and self.hdsPuneCursorul(canal):
			return
		intrare = self.hdsIntrareSatelit(canal)
		if intrare is not None:
			self.setCurrentSelection(intrare)
		else:
			self.hdsMutaLaRand(0)

	def hdsMutaLaRand(self, i):
		try:
			self.servicelist.moveToIndex(i)
		except Exception as e:
			print("[ChannelSelection] cursorul pe randul %d: %s" % (i, e))

	def hdsIndexCurent(self):
		try:
			return self.servicelist.getCurrentIndex()
		except Exception:
			return -1

	def hdsRefaSateliti(self, cursor=None):
		"""Lista pe sateliti refacuta pe loc (dupa OK pe un antet sau pe primul rand), cu locurile deschise de acum."""
		ref = eServiceReference(self.hdsSatelitiRefStr())
		self.servicelist.setRoot(ref, True)
		self.hdsUmpleSateliti(ref, canonic=False, cursor=cursor)
		self.hdsReimprospateazaAles()

	def hdsReimprospateazaAles(self):
		"""Panoul din dreapta dupa refacerea listei: antetul ales are alt nume (semnul starii, numarul), dar aceeasi
		referinta, iar sursele ServiceEvent nu anunta o referinta egala cu cea de dinainte; cu cursorul pe acelasi rand
		lista nici nu anunta o selectie noua."""
		for nume in ("ServiceEvent", "Service", "Event"):
			sursa = self.get(nume)
			if sursa is not None and hasattr(sursa, "newService"):
				sursa.newService(None)
		actualizeaza = getattr(self, "updateEventInfo", None)
		if actualizeaza is not None and getattr(self, "execing", False):
			actualizeaza()

	def hdsEsteRandulToate(self, ref):
		"""ref e primul rand al listei pe sateliti („Deschide toate canalele pe toți sateliții”)."""
		if ref is None or self.hdsRandToate is None or not ref.valid() or not (ref.flags & eServiceReference.isMarker):
			return False
		return ref == self.hdsRandToate and self.hdsPeRadacinaSateliti()

	def hdsLocAntet(self, ref):
		"""Locul al carui antet e ref, in lista pe sateliti; altfel None."""
		if ref is None or not ref.valid() or not (ref.flags & eServiceReference.isDirectory):
			return None
		if not self.hdsPeRadacinaSateliti():
			return None
		for poz, intrare in self.hdsIntrariSateliti:
			if intrare == ref:
				return poz
		return None

	def hdsOkPeSateliti(self):
		"""OK in lista pe sateliti: pe un antet deschide sau inchide locul, pe primul rand le deschide pe toate (sau le
		inchide pe celelalte); cursorul ramane pe randul apasat. -> True daca OK a facut asta (nu porneste nimic)."""
		if getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return False
		cur = self.getCurrentSelection()
		if self.hdsEsteRandulToate(cur):
			locuri = set(poz for poz, intrare in self.hdsIntrariSateliti)
			if locuri and locuri <= self.hdsDeschise:
				self.hdsDeschise = self.hdsDeschiseCanonic()
			else:
				self.hdsDeschise = locuri
			self.hdsRefaSateliti(cursor=cur)
			return True
		poz = self.hdsLocAntet(cur)
		if poz is None:
			return False
		if poz in self.hdsDeschise:
			self.hdsDeschise.discard(poz)
		else:
			self.hdsDeschise.add(poz)
		self.hdsRefaSateliti(cursor=cur)
		return True

	def hdsArataCanalul(self, canal):
		"""Lista pe sateliti: locul canalului deschis (daca era inchis) si cursorul pe canal. -> True daca a ajuns."""
		poz = self.hdsPozCanal(canal)
		if poz is None or not self.hdsPeRadacinaSateliti() or not any(p == poz for p, i in self.hdsIntrariSateliti):
			return False
		if poz not in self.hdsDeschise:
			self.hdsDeschise.add(poz)
			self.hdsRefaSateliti(cursor=canal)
			return self.getCurrentSelection() == canal
		if self.hdsPuneCursorul(canal):
			return True
		# canalul lipseste din locul deschis (de pilda adaugat dupa umplere): cursorul pe antetul locului
		intrare = self.hdsIntrareSatelit(canal)
		if intrare is not None:
			self.setCurrentSelection(intrare)
		return False

	def hdsNormalizeaza(self):
		"""Prima folosire dupa inchiderea listei (deschiderea ei, sagetile si P+/P- de pe bara): pe lista pe sateliti
		ramane deschis numai locul canalului de acum, cu cursorul pe canal (lista se reface numai daca altceva era
		deschis sau s-a schimbat lamedb). Intoarcerea dintr-un ecran deschis peste lista nu schimba nimic."""
		if not self.hdsProaspata:
			return
		self.hdsProaspata = False
		if not self.hdsPeRadacinaSateliti() or getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return
		canal = self.hdsCanalulCurent()
		canonic = self.hdsDeschiseCanonic()
		if canonic != self.hdsDeschise or self.hdsSemnUmplere != self.hdsSemnaturaUmplerii():
			self.hdsDeschise = canonic
			self.hdsRefaSateliti(cursor=canal)
		else:
			self.hdsCursorPeCanal(canal)

	def hdsMutaInBloc(self, directie):
		"""Lista inchisa pe sateliti (sagetile si P+/P- de pe bara): canalul urmator / anterior in locul de sub cursor,
		cu trecere de la ultimul la primul. -> True daca s-a mutat."""
		i = self.hdsIndexCurent()
		for poz, antet, prim, ultim in self.hdsBlocuri:
			j = hds_pas_in_bloc(i, prim, ultim, directie)
			if j is not None:
				self.hdsMutaLaRand(j)
				return True
		return False

	def hdsSariLaAntet(self, directie):
		"""CH+ / CH- in lista pe sateliti: cursorul pe antetul locului urmator / anterior."""
		a = hds_antet_vecin([antet for poz, antet, prim, ultim in self.hdsBlocuri], self.hdsIndexCurent(), directie)
		if a is not None:
			self.hdsMutaLaRand(a)

	def close(self, *retval):
		# lista s-a inchis: la urmatoarea folosire e deschis iar numai locul canalului de acum (hdsNormalizeaza)
		self.hdsProaspata = True
		Screen.close(self, *retval)

	def hdsCanalulCurent(self):
		"""Canalul dupa care se alege satelitul in „Sateliți": cel pornit acum, altfel ultimul tinut minte."""
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is not None and ref.valid():
			return ref
		ultimul = getattr(self, "lastservice", None)
		if ultimul is not None and ultimul.value:
			ref = eServiceReference(ultimul.value)
			if ref.valid():
				return ref
		return None

	def hdsIntrareSatelit(self, canal):
		"""Randul „<satelit> - Canale" al locului canalului (cablul si terestrul au cate unul) din ultima umplere a
		listei „Sateliți"; None pentru un canal fara loc in ea (de ex. un flux de internet)."""
		if canal is None or not canal.valid():
			return None
		if HdsCapLista is not None:
			# un post DAB+ / DVB-T2 din satelit: dosarul buchetului lui din „Sateliți” (hdsAdaugaBucheteFluxuri)
			fel = HdsCapLista.felul(canal.type, canal.flags, canal.getUnsignedData(0), canal.getPath())
			if fel in ("dab", "t2"):
				return getattr(self, "hdsIntrariFluxuri", {}).get(fel)
		poz = self.hdsPozCanal(canal)
		for p, intrare in self.hdsIntrariSateliti:
			if poz is not None and p == poz:
				return intrare
		return None

	def hdsPeRadacinaSateliti(self):
		return len(self.servicePath) == 1 and self.servicePath[0] == eServiceReference(self.hdsSatelitiRefStr())

	def hdsAreCanale(self, ref):
		try:
			return hds_lista_are_canale(eServiceCenter.getInstance(), ref)
		except Exception as e:
			print("[ChannelSelection] nu am putut citi lista %s: %s" % (ref is not None and ref.toString(), e))
			return False

	def hdsAreCanaleText(self, refstr):
		return self.hdsAreCanale(eServiceReference(refstr))

	def hdsDeschideSateliti(self, canal=None):
		"""Lista „Sateliți” (lista pe grupe) cu locul canalului deschis (implicit al celui de acum) si cursorul pe el.
		Locul tinut minte nu se schimba: ramane cel vechi pana alege omul un canal (zap -> saveRoot)."""
		ref = eServiceReference(self.hdsSatelitiRefStr())
		self.clearPath()
		self.enterPath(ref, True)
		self.hdsUmpleSateliti(ref, canal=canal)

	def hdsRefaLocul(self, locul):
		"""restoreRoot (TV si radio): locul tinut minte, daca lista de la capatul lui are canale; altfel „Sateliți"."""
		self.clearPath()
		cale = hds_cale_de_pornire(locul, self.hdsAreCanaleText)
		sateliti = eServiceReference(self.hdsSatelitiRefStr())
		# un loc din „Sateliți” tinut minte de lista dinainte („Sateliți;<satelit> - Canale;”, si furnizorii
		# sau canalele noi ale satelitului) deschide lista pe grupe, cu locul canalului deschis; dosarele DAB+ / DVB-T2
		# din satelit si „Transponder curent” raman drumuri pe doua niveluri
		if cale is None or eServiceReference(cale[-1]) == sateliti or 				(eServiceReference(cale[0]) == sateliti and any(hds_e_loc_de_satelit(eServiceReference(c).getPath()) for c in cale[1:])):
			if cale is None:
				print("[ChannelSelection] locul tinut minte e gol, lipseste sau nu are canale: deschid Sateliti")
			self.hdsDeschideSateliti()
			return
		for i in cale:
			self.servicePath.append(eServiceReference(i))
		path = self.servicePath.pop()
		self.enterPath(path)

	def hdsSelecteazaCanalul(self, ref):
		"""Cursorul pe canal. Pe lista pe sateliti locul canalului se deschide (daca era inchis); un canal fara loc in
		ea (un flux, un post DAB+ / DVB-T2) lasa cursorul pe randul pus la umplere: setCurrent pe o referinta care nu e
		in lista pune cursorul pe primul rand (Components/ServiceList.py)."""
		if ref is None or not ref.valid():
			return
		if self.hdsPeRadacinaSateliti():
			self.hdsArataCanalul(ref)
			return
		self.setCurrentSelection(ref)

	def showProviders(self):
		self.hdsAlesDeOm = time.time()  # lista aleasa de om (FAV, culori): se arata si goala
		if not self.pathChangeDisabled:
			refstr = '%s FROM PROVIDERS ORDER BY name'%(self.service_types)
			if not self.preEnterPath(refstr):
				ref = eServiceReference(refstr)
				if self.isBasePathEqual(ref):
					self.pathUp()
				else:
					currentRoot = self.getRoot()
					if currentRoot is None or currentRoot != ref:
						self.clearPath()
						self.enterPath(ref)

	def changeBouquet(self, direction):
		if not self.pathChangeDisabled:
			if self.hdsPeRadacinaSateliti() and self.hdsBlocuri:
				# lista pe sateliti: antetul locului urmator / anterior
				self.hdsSariLaAntet(direction)
				return
			if len(self.servicePath) > 1:
				#when enter satellite root list we must do some magic stuff..
				ref = eServiceReference('%s FROM SATELLITES ORDER BY satellitePosition'%(self.service_types))
				if self.isBasePathEqual(ref):
					# dintr-un dosar al listei pe sateliti (DAB+, DVB-T2, transponderul curent): inapoi in lista, pe
					# dosar; randul vecin poate fi un antet sau un canal, in care nu se intra
					self.hdsArataSateliti()
					return
				else:
					self.pathUp()
				if direction < 0:
					self.moveUp()
				else:
					self.moveDown()
				ref = self.getCurrentSelection()
				self.enterPath(ref)

	def inBouquet(self):
		if self.servicePath and self.servicePath[0] == self.bouquet_root:
			return True
		return False

	def atBegin(self):
		return self.servicelist.atBegin()

	def atEnd(self):
		return self.servicelist.atEnd()

	def nextBouquet(self):
		self.changeBouquet(+1)

	def prevBouquet(self):
		self.changeBouquet(-1)

	def showFavourites(self):
		self.hdsAlesDeOm = time.time()  # lista aleasa de om (FAV, culori): se arata si goala
		if not self.pathChangeDisabled:
			if not self.preEnterPath(self.bouquet_rootstr):
				if self.isBasePathEqual(self.bouquet_root):
					self.pathUp()
				else:
					currentRoot = self.getRoot()
					if currentRoot is None or currentRoot != self.bouquet_root:
						self.clearPath()
						self.enterPath(self.bouquet_root)

	def keyNumberGlobal(self, number):
		hdsCapLaLista(self)
		# lista retelei: numerele fisierului de acum, nu cele de la umplere (o scanare sau un fisier pus intre timp)
		self.hdsReteaLaZi()
		if getattr(self, "hdsNumereRetea", None):
			# lista unei retele: cifrele duc cursorul la numarul operatorului (2, apoi 3 = 23), nu la o litera
			self.hdsCifraRetea(number)
			return
		unichar = self.numericalTextInput.getKey(number)
		if len(unichar.encode("utf-8")) == 1:
			self.servicelist.moveToChar(unichar)

	def keyAsciiCode(self):
		hdsCapLaLista(self)
		unichar = chr(getPrevAsciiCode())
		if len(unichar.encode("utf-8")) == 1:
			self.servicelist.moveToChar(unichar)

	def getRoot(self):
		return self.servicelist.getRoot()

	def getCurrentSelection(self):
		return self.servicelist.getCurrent()

	def setCurrentSelection(self, service):
		self.servicelist.setCurrent(service)

	def getBouquetList(self):
		bouquets = [ ]
		serviceHandler = eServiceCenter.getInstance()
		if config.usage.multibouquet.value:
			list = serviceHandler.list(self.bouquet_root)
			if list:
				while True:
					s = list.getNext()
					if not s.valid():
						break
					if s.flags & eServiceReference.isDirectory:
						info = serviceHandler.info(s)
						if info:
							bouquets.append((info.getName(s), s))
				return bouquets
		else:
			info = serviceHandler.info(self.bouquet_root)
			if info:
				bouquets.append((info.getName(self.bouquet_root), self.bouquet_root))
			return bouquets
		return None

	HDS_CIFRE_MS = 1500     # cat se asteapta cifra urmatoare a unui numar de operator in lista retelei

	def hdsCifraRetea(self, cifra):
		"""O cifra in lista retelei: numarul tastat pana acum (cel mult 4 cifre, cat au posturile de radio) duce cursorul la
		canalul cu acel numar al operatorului; o cifra care nu continua un numar existent incepe unul nou. Dupa
		HDS_CIFRE_MS fara cifra, numarul se uita."""
		text = (getattr(self, "hdsCifreText", "") + str(cifra))[-4:]
		ref = self.hdsNumarInRetea(int(text))
		if ref is None and len(text) > 1:
			text = str(cifra)
			ref = self.hdsNumarInRetea(cifra)
		self.hdsCifreText = text
		if ref is not None:
			self.setCurrentSelection(ref)
		ceas = getattr(self, "hdsCeasCifre", None)
		if ceas is None:
			ceas = self.hdsCeasCifre = eTimer()
			ceas.callback.append(self.hdsUitaCifrele)
		ceas.start(self.HDS_CIFRE_MS, True)

	def hdsUitaCifrele(self):
		self.hdsCifreText = ""

	def keyNumber0(self, num):
		hdsCapLaLista(self)
		self.hdsReteaLaZi()
		if getattr(self, "hdsNumereRetea", None) and getattr(self, "hdsCifreText", ""):
			# lista retelei: 0 dupa alta cifra face parte din numar (10, 20, 1001)
			self.hdsCifraRetea(0)
			return
		if len(self.servicePath) > 1:
			self.keyGoUp()
		else:
			self.keyNumberGlobal(num)

	def keyGoUp(self):
		if len(self.servicePath) > 1:
			if self.isBasePathEqual(self.bouquet_root):
				self.showFavourites()
			else:
				ref = eServiceReference('%s FROM SATELLITES ORDER BY satellitePosition'%(self.service_types))
				if self.isBasePathEqual(ref):
					self.hdsArataSateliti()
				else:
					ref = eServiceReference('%s FROM PROVIDERS ORDER BY name'%(self.service_types))
					if self.isBasePathEqual(ref):
						self.showProviders()
					else:
						self.showAllServices()

	def nextMarker(self):
		hdsCapLaLista(self)
		self.servicelist.moveToNextMarker()

	def prevMarker(self):
		hdsCapLaLista(self)
		self.servicelist.moveToPrevMarker()

	# HDSatelit: cautarea de canale (tasta TEXT sau MENU > Cautare canale)
	# Cautarea tine minte textul, filtrele si cursorul (memoria din Screens/HdsCautareCanale.py, una pentru lista TV si
	# una pentru lista radio). Dupa un canal pornit din rezultate, deschiderea urmatoare a listei redeschide cautarea
	# (hdsRedeschideCautarea), cu cursorul pe canal; EXIT din ea duce in lista obisnuita, cu filtrele pastrate pentru TEXT.
	def hdsCautare(self, redeschisa=False):
		if getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return
		from Screens.HdsCautareCanale import HdsCautareCanale
		# in lista radio bara mica a radioului (RadioInfoBar, self.info) ar ramane desenata peste partea de jos a
		# cautarii: se ascunde cat e deschisa cautarea si revine la intoarcere, ca la RassInteractive
		info = getattr(self, "info", None)
		self.hdsInfoAscuns = isinstance(info, RadioInfoBar) and info.shown
		if self.hdsInfoAscuns:
			info.hide()
		self.session.openWithCallback(self.hdsCautareGata, HdsCautareCanale, self.mode == MODE_RADIO,
			refCurent=self.hdsRefPornita(), redeschisa=redeschisa)

	def hdsCautareGata(self, canal=None):
		if getattr(self, "hdsInfoAscuns", False):
			self.hdsInfoAscuns = False
			self.info.show()
		if canal is not None:
			self.hdsTineMinteZapul(canal)
			self.hdsLaCanal(canal)
		# cautarea redeschisa de hdsRedeschideCautarea s-a deschis inainte ca lista sa se arate, iar Session.popCurrent
		# reda la intoarcere starea de atunci (ascunsa): dupa EXIT din cautare lista se arata aici. O lista care tocmai
		# s-a inchis (canalul ales) nu mai e in executie.
		if getattr(self, "execing", False) and not getattr(self, "shown", True):
			self.show()

	def hdsRefPornita(self):
		"""Referinta (text) a canalului pornit acum, sau None."""
		try:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			return ref.toString() if ref is not None and ref.valid() else None
		except Exception:
			return None

	def hdsTineMinteZapul(self, canal):
		"""Canalul ales in rezultatele cautarii porneste si lista se inchide: la deschiderea ei urmatoare cautarea se
		redeschide (Screens/HdsCautareCanale.dupa_zap). Nu in alegerea simpla a canalului (timer: nu porneste nimic),
		nu in mutare sau in editarea buchetelor (hdsLaCanal nu face nimic atunci) si nu pentru un canal TV ales in
		cautarea listei radio (omul trece la televizor, lista radio nu mai e locul lui)."""
		if not hasattr(self, "doContext") or getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return
		radio = self.mode == MODE_RADIO
		if radio and not getattr(canal, "radio", True):
			return
		if not eServiceReference(canal.ref).valid():
			return
		try:
			from Screens.HdsCautareCanale import dupa_zap
		except ImportError:
			return
		dupa_zap(radio, canal.ref)

	def hdsRedeschideCautarea(self, alesDeOm=False):
		"""La deschiderea listei (onExecBegin), dupa un canal pornit din rezultatele cautarii: cautarea se redeschide
		peste lista, cu aceleasi filtre si cursorul pe canal; lista nu se mai arata intre timp (Session.execBegin nu o
		arata cand execBegin al ei a deschis alt ecran). de_redeschis sterge semnul la prima intrebare, deci intoarcerea
		in lista dupa EXIT din cautare nu o mai redeschide. Nu cand omul a cerut chiar atunci o grupa a listei (FAV,
		tastele colorate de pe bara), in mutare sau in editarea buchetelor.
		Ruleaza din onExecBegin (Session.execBegin): o exceptie de aici ar iesi din execBegin si ar opri interfata, deci
		orice eroare se scrie in jurnal, memoria cautarii se uita (nu se mai incearca la deschiderea urmatoare) si lista
		ramane deschisa ca de obicei."""
		try:
			from Screens.HdsCautareCanale import de_redeschis
		except Exception as e:
			# nu numai ImportError: orice eroare la incarcarea modulului ar iesi tot din execBegin
			if not isinstance(e, ImportError):
				print("[ChannelSelection] redeschiderea cautarii: %s: %s" % (e.__class__.__name__, e))
			return
		radio = self.mode == MODE_RADIO
		try:
			if not de_redeschis(radio, self.hdsRefPornita()) or alesDeOm or not self.hdsPoateCauta():
				return
			self.hdsCautare(redeschisa=True)
		except Exception as e:
			print("[ChannelSelection] redeschiderea cautarii: %s: %s" % (e.__class__.__name__, e))
			try:
				from Screens.HdsCautareCanale import uita_cautarea
				uita_cautarea(radio)
			except Exception:
				pass

	def hdsPunePeLista(self, ref, canal):
		"""Pune lista pe canalul gasit: in lista curenta daca e acolo (de ex. in favorite), altfel in buchetul
		fluxului (T2 / DAB+ / internet) sau in satelitul lui din „Sateliți" („Toate" doar pentru un canal fara loc
		acolo), ca sus/jos din InfoBar sa mearga de acolo mai departe.
		Un canal pe care nicio lista nu-l arata (de ex. un tip de serviciu lipsa din service_types) lasa lista
		neatinsa. -> True daca lista a ajuns pe canal."""
		# setCurrent muta cursorul la sfarsitul listei cand nu gaseste referinta: cursorul vechi se pune la loc
		vechi = self.getCurrentSelection()
		self.servicelist.setCurrent(ref)
		if self.getCurrentSelection() == ref:
			return True
		if canal.buchet and config.usage.multibouquet.value and canal.buchet.endswith(".radio") == (self.mode == MODE_RADIO):
			bref = eServiceReference('1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (2 if canal.buchet.endswith(".radio") else 1, canal.buchet))
			self.clearPath()
			self.enterPath(self.bouquet_root)
			self.enterPath(bref)
		elif canal.buchet and canal.buchet.endswith(".radio") == (self.mode == MODE_RADIO) and self.hdsBuchetInSateliti(canal.buchet):
			# „mai multe buchete” oprit: buchetul DAB+ / DVB-T2 din satelit sta ca dosar in „Sateliți”
			self.hdsDeschideSateliti()
			intrare = self.hdsIntrareSatelit(ref)
			if intrare is None:
				return False
			self.enterPath(intrare)
		elif not canal.buchet and ("(type == %d)" % canal.stype) in self.service_types:
			# HDSatelit: in lista „Sateliți”, cu locul canalului deschis (satelit, cablu sau
			# terestru), nu in „Toate”: lista se tine minte la zap, iar sageata jos o redeschide acolo
			self.hdsDeschideSateliti(canal=ref)
			if self.getCurrentSelection() == ref:
				return True
			if self.hdsIntrareSatelit(ref) is None:
				self.showAllServices()
		else:
			if vechi is not None and vechi.valid():
				self.servicelist.setCurrent(vechi)
			return False
		self.servicelist.setCurrent(ref)
		return self.getCurrentSelection() == ref

	def hdsLaCanal(self, canal):
		ref = eServiceReference(canal.ref)
		if ref.valid():
			self.hdsPunePeLista(ref, canal)

	def hdsBuchetInSateliti(self, fisier):
		"""Buchetul DAB+ / DVB-T2 din satelit `fisier` are dosar in „Sateliți” (exista si e in bouquets.*)."""
		try:
			from Components import HdsIndexCanale as X
			lista = "radio" if fisier.endswith(".radio") else "tv"
			return any(f == fisier for _fel, f in X.buchete_fluxuri(lista))
		except Exception:
			return False

	# ---------------------------------------------------------------- capul listei (Components/HdsCapLista.py)
	# Fila „TV | Radio”, randul grupelor listei (Toate, Sateliți, Furnizori, Favorite, Meniu) si randul „Caută canal…”
	# deasupra listei, plus OK tinut apasat = cautarea. Il pornesc numai ChannelSelection, ChannelSelectionRadio si
	# SimpleChannelSelection (hdsPornesteCapul, cu aceeasi garda `type(self) is ...` ca skinName), nu si clasele
	# pluginurilor facute din ele sau din ChannelSelectionBase: harta tastelor de aici ia OK inaintea hartilor lor.
	# Capul se vede numai in ecranele skinului imaginii (HdsListaCanale*, cerute primele prin skinName); cu un skin
	# fara ele nu il deseneaza nimic (hdsCapInSkin): sagetile raman ale listei, OK tinut apasat deschide tot cautarea.
	# Capul e facut din surse de text (StaticText), nu din etichete: o componenta GUI lipsa din skin primeste totusi o
	# instanta si scrie in jurnal „skin is missing element” (Components/GUISkin.py), iar o a doua lista (eListbox) si-ar
	# lega singura sagetile (ListboxActions, lib/gui/elistbox.cpp) si prima creata le-ar lua si pe ale listei de canale.
	# Sursele au text numai cand elementul lor se vede (ConditionalShowHide in skin): hdsCapFond = fundalurile capului
	# (goale in mutare si in editarea buchetelor, cand capul nu se foloseste), hdsCapFocus* = randul cu focus,
	# hdsCap<Tv|Radio>Ales = pastila listei de acum, hdsCap<Tv|Radio> = pastila celeilalte, hdsCapG<i> = pastila unei
	# grupe, hdsCapG<i>Ales = pastila grupei listei de acum (cu „‹ ” in fata cand lista e intr-un dosar al ei: OK
	# urca), hdsCapG<i>Cursor = linia de sub pastila pe care e cursorul randului grupelor.

	# cate trei surse pentru fiecare din cele HDS_CAP_GRUPE pastile ale randului grupelor (hdsCapG<i>, ...Ales, ...Cursor);
	# fundalul ultimei (Meniu) are sursa lui, hdsCapG4Fond: alegerea simpla a canalului nu are meniul listei
	CAP_SURSE = ("hdsCapFond", "hdsCapFocusFila", "hdsCapFocusGrupe", "hdsCapFocusCauta", "hdsCapTv", "hdsCapTvAles",
		"hdsCapRadio", "hdsCapRadioAles", "hdsCapCauta", "hdsCapIndiciu",
		"hdsCapG0", "hdsCapG0Ales", "hdsCapG0Cursor", "hdsCapG1", "hdsCapG1Ales", "hdsCapG1Cursor",
		"hdsCapG2", "hdsCapG2Ales", "hdsCapG2Cursor", "hdsCapG3", "hdsCapG3Ales", "hdsCapG3Cursor",
		"hdsCapG4", "hdsCapG4Ales", "hdsCapG4Cursor", "hdsCapG4Fond")

	def hdsPornesteCapul(self):
		if HdsCapLista is None:
			return
		self.hdsCap = HdsCapLista.Cap()
		# alegerea simpla a canalului (SimpleChannelSelection) nu are meniul listei: fara ultima pastila
		self.hdsCap.grupe = HDS_CAP_GRUPE if hasattr(self, "doContext") else HDS_CAP_GRUPE - 1
		self.hdsCapDesenat = None
		for nume in self.CAP_SURSE:
			self[nume] = StaticText("")
		self["hdsCapCauta"].setText(_("Caută canal…"))
		self["hdsCapIndiciu"].setText(_("TEXT sau OK ținut apăsat"))
		self["hdsFelAles"] = StaticText("")
		self["hdsAcumEticheta"] = StaticText("")
		self["hdsAcumNume"] = StaticText("")
		# buchetele DAB+ / DVB-T2 din satelit: textul peste lista cand buchetul e gol si textul dosarului lor in panoul
		# din dreapta (in locul emisiunii, pe care un dosar nu o are)
		self["hdsListaGoala"] = StaticText("")
		self["hdsDespreAles"] = StaticText("")
		self["hdsDespreAles2"] = StaticText("")
		self["HdsCapActions"] = HdsTacutActionMap(["HdsListaCanaleActions"],
			{
				"okApasat": self.hdsCapOkApasat,
				"okLung": self.hdsCapOkLung,
				"okEliberat": self.hdsCapOkEliberat,
				"sus": self.hdsCapSus,
				"jos": self.hdsCapJos,
				"stanga": self.hdsCapStanga,
				"dreapta": self.hdsCapDreapta,
				"repetat": self.hdsCapRepetat,
			}, -1)
		self.hdsCapPornit = True
		self.onLayoutFinish.append(self.hdsCapLaLayout)

	def hdsCapLaLayout(self):
		self.hdsCapVazut = self.hdsCapInSkin() and self.servicelist.instance is not None
		self.hdsDeseneazaCapul()

	def hdsCapInSkin(self):
		"""Skinul ecranului deseneaza capul (are un element legat de sursa randului de cautare)."""
		sursa = self["hdsCapCauta"]
		return any(getattr(r, "source", None) is sursa for r in self.renderer)

	def hdsCapActiv(self):
		"""Sagetile si OK ajung la cap: capul se vede, iar lista nu e in mutare sau in editarea buchetelor."""
		return self.hdsCapVazut and self.hdsPoateCauta()

	def hdsPoateCauta(self):
		return not getattr(self, "movemode", False) and getattr(self, "bouquet_mark_edit", OFF) == OFF

	def hdsCapEtichete(self):
		"""Textele pastilelor randului grupelor, ca tastele colorate (aceleasi traduceri), apoi meniul listei."""
		etichete = [_("All"), _("Satellites"), _("Provider"), _("Favourites"), _("Menu")]
		return etichete[:self.hdsCap.grupe]

	def hdsGrupaCurenta(self):
		"""Grupa in care e lista acum (indicele din HdsCapLista.GRUPE_LISTEI, dupa radacina drumului), sau None."""
		if not self.servicePath:
			return None
		baza = self.servicePath[0]
		if baza == self.bouquet_root:
			return HdsCapLista.GRUPE_LISTEI.index("showFavourites")
		cale = baza.getPath() or ""
		if "FROM SATELLITES" in cale:
			return HdsCapLista.GRUPE_LISTEI.index("showSatellites")
		if "FROM PROVIDERS" in cale:
			return HdsCapLista.GRUPE_LISTEI.index("showProviders")
		if baza == eServiceReference("%s ORDER BY name" % self.service_types):
			return HdsCapLista.GRUPE_LISTEI.index("showAllServices")
		return None

	def hdsDeseneazaCapul(self):
		"""Randul cu focus (bara colorata), fila listei de acum, pastilele grupelor si selectia listei (stinsa cat
		focusul e in cap). In mutare si in editarea buchetelor capul nu se foloseste: toate sursele goale."""
		if not self.hdsCapVazut:
			return
		vazut = self.hdsPoateCauta()
		focus = self.hdsCap.focus if vazut else HdsCapLista.LISTA
		radio = self.mode == MODE_RADIO
		curenta = self.hdsGrupaCurenta()
		inDosar = len(self.servicePath) > 1
		# in lista unei retele indiciul spune ce fac cifrele (numarul operatorului), nu cum se cauta
		retea = bool(getattr(self, "hdsNumereRetea", None))
		stare = (vazut, focus, radio, curenta, inDosar, self.hdsCap.grupa, retea)
		if stare == self.hdsCapDesenat:
			return
		self.hdsCapDesenat = stare
		texte = {}
		if vazut:
			tv, rd = _("TV"), _("Radio")
			indiciu = _("Cifrele: numărul operatorului") if retea else _("TEXT sau OK ținut apăsat")
			texte.update({"hdsCapFond": "1", "hdsCapCauta": _("Caută canal…"), "hdsCapIndiciu": indiciu,
				"hdsCapG4Fond": "1" if self.hdsCap.grupe > 4 else "",
				"hdsCapFocusFila": "1" if focus == HdsCapLista.FILA else "",
				"hdsCapFocusGrupe": "1" if focus == HdsCapLista.GRUPE else "",
				"hdsCapFocusCauta": "1" if focus == HdsCapLista.CAUTA else "",
				"hdsCapTvAles": "" if radio else tv, "hdsCapTv": tv if radio else "",
				"hdsCapRadioAles": rd if radio else "", "hdsCapRadio": "" if radio else rd})
			for i, eticheta in enumerate(self.hdsCapEtichete()):
				if i == curenta:
					texte["hdsCapG%dAles" % i] = ("‹ " + eticheta) if inDosar else eticheta
				else:
					texte["hdsCapG%d" % i] = eticheta
				if focus == HdsCapLista.GRUPE and i == self.hdsCap.grupa:
					texte["hdsCapG%dCursor" % i] = "1"
		for nume in self.CAP_SURSE:
			text = texte.get(nume, "")
			if self[nume].getText() != text:
				self[nume].setText(text)
		self.servicelist.instance.setSelectionEnable(1 if focus is HdsCapLista.LISTA else 0)

	def hdsCapInLista(self):
		self.hdsCap.inLista()
		self.hdsDeseneazaCapul()

	def hdsCapLaDeschidere(self):
		"""Lista se deschide cu cursorul in ea, sau pe fila cand s-a ajuns aici din fila celeilalte liste."""
		self.hdsCap.inLista()
		self.hdsCap.okApasat = False
		if hds_cap_urmator_ia() == HdsCapLista.FILA and self.hdsCapActiv():
			self.hdsCap.focus = HdsCapLista.FILA
		self.hdsDeseneazaCapul()
		self.hdsActualizeazaAcum()

	def hdsCapLaInceput(self):
		try:
			return self.servicelist.getCurrentIndex() <= 0
		except Exception:
			return False

	def hdsCapFapta(self, fapta):
		"""Face ce a hotarat capul. -> 0 cand tasta ramane a listei (harta de prioritate -1 o lasa mai departe)."""
		if fapta == HdsCapLista.TRECE:
			return 0
		if fapta == HdsCapLista.MUTAT:
			self.hdsDeseneazaCapul()
		elif fapta == HdsCapLista.COMUTA:
			self.hdsComutaLista()
		elif fapta == HdsCapLista.CAUTARE:
			self.hdsCautare()
		elif fapta == HdsCapLista.GRUPA:
			self.hdsAlegeGrupa(self.hdsCap.grupa)
		elif fapta == HdsCapLista.OK_LISTA:
			self.hdsDeseneazaCapul()
			self.channelSelected()
		return 1

	def hdsAlegeGrupa(self, i):
		"""OK pe o pastila a randului grupelor: grupa aleasa (ca tasta colorata), meniul listei (ca MENU), sau, pe grupa
		in care e deja lista si dintr-un dosar al ei (un satelit, un furnizor, un buchet), urcarea inapoi in grupa (ca
		tasta 0). Dupa alegere cursorul e in lista."""
		if i == HdsCapLista.MENIU:
			if hasattr(self, "doContext"):
				self.doContext()
			return
		if i == self.hdsGrupaCurenta() and len(self.servicePath) > 1:
			self.keyGoUp()
		else:
			getattr(self, HdsCapLista.GRUPE_LISTEI[i])()
		self.hdsCapInLista()

	def hdsCapSus(self):
		return self.hdsCapFapta(self.hdsCap.sus(self.hdsCapActiv(), self.hdsCapLaInceput(), self.hdsGrupaCurenta()))

	def hdsCapJos(self):
		return self.hdsCapFapta(self.hdsCap.jos(self.hdsCapActiv(), self.hdsGrupaCurenta()))

	def hdsCapStanga(self):
		fapta = self.hdsCap.lateral(self.hdsCapActiv(), -1)
		if fapta == HdsCapLista.TRECE and self.hdsPaginaPesteCapat(-1):
			return 1
		return self.hdsCapFapta(fapta)

	def hdsCapDreapta(self):
		fapta = self.hdsCap.lateral(self.hdsCapActiv(), 1)
		if fapta == HdsCapLista.TRECE and self.hdsPaginaPesteCapat(1):
			return 1
		return self.hdsCapFapta(fapta)

	def hdsPaginaPesteCapat(self, pas):
		"""HDSatelit (cererea de la 16:35): STANGA / DREAPTA in lista (focusul in ea) dau pagina sus / jos,
		iar de pe prima pagina STANGA trece la ultima (cursorul pe ultimul rand) si de pe ultima DREAPTA trece la prima
		(cursorul pe primul rand), ca SUS / JOS de pe primul / ultimul rand. Numai la apasare: tasta tinuta apasat
		(„repetat”) ramane a listei, care se opreste la capat, deci trecerea se face o data pe apasare.
		-> True daca pagina s-a mutat aici (lista nu mai primeste tasta)."""
		if self.hdsCap.focus is not HdsCapLista.LISTA or not self.hdsPoateCauta():
			return False
		inst = getattr(self.servicelist, "instance", None)
		if inst is None:
			return False
		try:
			sus = inst.getTopIndex()
		except AttributeError:
			sus = None
		try:
			if sus is None:
				# un enigma2 fara getTopIndex: numai de pe primul / ultimul rand
				if (pas < 0 and inst.getCurrentIndex() == 0) or (pas > 0 and inst.atEnd()):
					inst.moveSelection(inst.moveEnd if pas < 0 else inst.moveTop)
					return True
				return False
			inst.moveSelection(inst.pageUp if pas < 0 else inst.pageDown)
			if hds_trece_peste_capat(pas, sus, inst.getTopIndex(), inst.getCurrentIndex(), inst.atEnd()):
				inst.moveSelection(inst.moveEnd if pas < 0 else inst.moveTop)
			return True
		except AttributeError as e:
			print("[ChannelSelection] pagina peste capat: %s" % e)
			return False

	def hdsCapLateral(self):
		"""STANGA / DREAPTA fara directie (pe fila comuta oricum): ca DREAPTA."""
		return self.hdsCapDreapta()

	def hdsCapRepetat(self):
		return self.hdsCapFapta(self.hdsCap.repetat(self.hdsCapActiv()))

	def hdsCapOkApasat(self):
		self.hdsCap.okApasare()
		return 1

	def hdsCapOkLung(self):
		return self.hdsCapFapta(self.hdsCap.okTinut(self.hdsPoateCauta()))

	def hdsCapOkEliberat(self):
		return self.hdsCapFapta(self.hdsCap.okEliberare(self.hdsCapActiv()))

	def hdsOkDirect(self):
		"""OK din OkCancelActions: ENTER de la o tastatura (tasta OK a telecomenzii trece prin HdsCapActions)."""
		if self.hdsCapPornit:
			self.hdsCapFapta(self.hdsCap.ok(self.hdsCapActiv()))
		else:
			self.channelSelected()

	def hdsComutaLista(self, dinFila=True):
		"""Lista cealalta (TV <-> Radio) in acelasi ecran, cu focusul pastrat (pe fila, daca de acolo s-a cerut).
		dinFila: cerut din fila capului (altfel din meniul listei)."""
		self.hdsComutare = True
		try:
			if self.mode == MODE_RADIO:
				self.setModeTv()
			else:
				self.setModeRadio()
		finally:
			self.hdsComutare = False
		self.hdsDeseneazaCapul()

	def hdsPuneFelul(self, ref):
		"""Sub numele canalului ales, in panoul din dreapta: felul lui (nu al celui pornit)."""
		fel = None
		dosar, despre, despre2 = "", "", ""
		if ref is not None and ref.valid():
			fel = HdsCapLista.felul(ref.type, ref.flags, ref.getUnsignedData(0), ref.getPath())
			if fel is None and self.hdsPeRadacinaSateliti():
				# lista pe sateliti: ce face OK pe un antet sau pe primul rand
				dosar = self.hdsIndiciuSateliti(ref)
			if fel is None and not dosar and ref.flags & eServiceReference.isDirectory:
				dosar, despre, despre2 = self.hdsDespreDosar(ref)
		text = {"tv": _("Canal TV"), "radio": _("Post de radio"), "flux": _("Flux de internet"),
			"date": _("Serviciu de date"), "dab": _("Post DAB+ din satelit"),
			"t2": _("Program DVB-T2 din satelit")}.get(fel, dosar)
		if self["hdsFelAles"].getText() != text:
			self["hdsFelAles"].setText(text)
		if self["hdsDespreAles"].getText() != despre:
			self["hdsDespreAles"].setText(despre)
		if self["hdsDespreAles2"].getText() != despre2:
			self["hdsDespreAles2"].setText(despre2)

	def hdsIndiciuSateliti(self, ref):
		"""Sub numele randului ales in lista pe sateliti: ce face OK pe un antet sau pe primul rand; "" altfel."""
		if self.hdsEsteRandulToate(ref):
			return _("OK deschide sau închide toți sateliții")
		poz = self.hdsLocAntet(ref)
		if poz is None:
			return ""
		return _("OK ascunde canalele") if poz in self.hdsDeschise else _("OK arată canalele")

	# ---------------------------------------------------------------- buchetele DAB+ / DVB-T2 din satelit
	# Posturile lor nu sunt in lamedb, deci nu au loc in „Toate”, „Sateliți” sau „Furnizori”, iar cu „mai multe buchete”
	# oprit (implicit) nici buchetul nu se vede. „Sateliți” le primeste dosarul (hdsAdaugaBucheteFluxuri), numai pentru
	# buchetele care exista si sunt trecute in bouquets.tv / bouquets.radio (Components/HdsIndexCanale.buchete_fluxuri).
	# Un buchet gol arata peste lista ce e si cum se umple, iar OK in el porneste cautarea (hdsOkPeBuchetGol).

	def hdsNumaraCanale(self, ref):
		n = 0
		lista = eServiceCenter.getInstance().list(ref)
		if lista is None:
			return 0
		while True:
			s = lista.getNext()
			if not s.valid():
				return n
			if not (s.flags & (eServiceReference.isMarker | eServiceReference.isDirectory)):
				n += 1

	def hdsDespreDosar(self, ref):
		"""(felul, textul de sus, textul de jos) pentru dosarul unui buchet DAB+ / DVB-T2 din satelit; ("", "", "")
		pentru orice alt dosar. Cele doua texte stau deasupra si dedesubtul barii emisiunii din panoul din dreapta."""
		try:
			from Components import HdsIndexCanale as X
			fel = X.fel_buchet_flux(ref.getPath())
			if fel is None:
				return "", "", ""
			sus, jos = X.texte_dosar(fel, self.hdsNumaraCanale(ref))
			return X.fel_dosar_text(fel), sus, jos
		except Exception as e:
			print("[ChannelSelection] dosarul DAB+ / DVB-T2: %s" % e)
			return "", "", ""

	def hdsFelBuchetGol(self, root=None):
		"""'dab' / 't2' cand lista de acum e buchetul DAB+ / DVB-T2 din satelit si nu are niciun post, altfel None."""
		if root is None:
			root = self.getRoot()
		if root is None or not root.valid():
			return None
		try:
			from Components import HdsIndexCanale as X
			fel = X.fel_buchet_flux(root.getPath())
		except Exception:
			return None
		if fel is None or self.hdsAreCanale(root):
			return None
		return fel

	def hdsPuneListaGoala(self, root=None):
		"""Textul peste lista: ce e buchetul DAB+ / DVB-T2 si cum se umple, numai cat e gol."""
		if not getattr(self, "hdsCapPornit", False):
			return
		fel = self.hdsFelBuchetGol(root)
		text = ""
		if fel is not None:
			from Components import HdsIndexCanale as X
			text = X.text_buchet_gol(fel)
		if self["hdsListaGoala"].getText() != text:
			self["hdsListaGoala"].setText(text)

	def hdsOkPeBuchetGol(self):
		"""OK intr-un buchet DAB+ / DVB-T2 din satelit gol: cautarea posturilor (Screens/ScanerSatelit.py), in locul
		pornirii ultimului canal. -> True daca a deschis cautarea."""
		if getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return False
		cur = self.getCurrentSelection()
		if cur is not None and cur.valid():
			return False
		fel = self.hdsFelBuchetGol()
		if fel is None:
			return False
		if fel == "dvbi":
			# buchetul "Canale de pe internet (DVB-I)" gol: alegerea tarii, nu o cautare
			from Screens.HdsDvbI import HdsDvbISetup
			self.session.openWithCallback(self.hdsDupaCautareFluxuri, HdsDvbISetup)
			return True
		from Screens.ScanerSatelit import ScanerSatelit
		self.session.openWithCallback(self.hdsDupaCautareFluxuri, ScanerSatelit, "dab" if fel == "dab" else "dvbt2")
		return True

	def hdsDupaCautareFluxuri(self, *rezultat):
		"""Dupa cautare buchetul poate avea posturi (buchetele se reincarca la salvare): lista se citeste din nou, cu
		cursorul pe postul pornit, daca e in ea."""
		root = self.getRoot()
		if root is None or not root.valid():
			return
		self.setRoot(root)
		acum = self.session.nav.getCurrentlyPlayingServiceReference()
		if acum is not None and acum.valid():
			self.setCurrentSelection(acum)

	# HDSatelit: listele retelelor citite la scanare (Components/HdsRetele.py): fiecare retea cu numerele canalelor date de
	# operator are un dosar sub antetul locului ei in "Sateliți" (cablul: "Cablu Targu Jiu · 178 de canale, după numerele
	# operatorului"). In ea canalele stau in ordinea numerelor, cu numarul operatorului in coloana numarului, iar cifrele
	# (in lista si pe bara, InfoBarGenerics.zapToNumber) duc la numarul operatorului. Listele omului nu se ating.

	def hdsReteaRadacinii(self, ref):
		"""Cheia retelei a carei lista e `ref` (eServiceReference), sau None."""
		if HdsRetele is None or ref is None:
			return None
		try:
			return HdsRetele.retea_din_cale(ref.getPath())
		except Exception as e:
			print("[ChannelSelection] lista retelei: %s" % e)
			return None

	def hdsDosareRetele(self, poz):
		"""Dosarele listelor retelelor locului `poz` (namespace >> 16: cablul 0xFFFF, terestrul 0xEEEE, pozitia
		orbitala), pentru modul de acum (TV sau radio); fara canale de felul modului, fara dosar."""
		if HdsRetele is None:
			return []
		loc = "cablu" if poz == HDS_POZ_CABLU else "terestru" if poz == HDS_POZ_TERESTRU else poz % 3600
		rez = []
		try:
			radio = self.mode == MODE_RADIO
			HdsRetele.generatie()      # fisierul de acum, nu cel privit cu pana la 2 s inainte (hdsSemnaturaUmplerii)
			for r in HdsRetele.retele_cu_lista(loc):
				numerotate = [x for x in self.hdsRanduriRetea(r["cheie"], radio) if x[0]]
				if not numerotate:
					continue
				dosar = eServiceReference(HdsRetele.cale_lista(r, self.service_types))
				nume = r.get("nume") or _("Rețeaua %d") % r.get("nid", 0)
				dosar.setName(u"%s · %s" % (nume, _("%s, după numerele operatorului") % self.hdsTextNumar(len(numerotate))))
				rez.append(dosar)
		except Exception as e:
			print("[ChannelSelection] listele retelelor in Sateliti: %s" % e)
		return rez

	def hdsRanduriRetea(self, cheie, radio):
		"""Randurile listei retelei (Components/HdsRetele.randuri_lista) care sunt in lamedb: [(numar sau 0, referinta)].
		Un canal citit la scanare si scos apoi din lista de canale nu apare (nici in numarul de pe dosar)."""
		centru = eServiceCenter.getInstance()
		rez = []
		for numar, refstr, _nume in HdsRetele.randuri_lista(cheie, radio):
			ref = eServiceReference(refstr)
			info = centru.info(ref)
			if info is not None and info.getName(ref):
				rez.append((numar, ref))
		return rez

	def hdsUmpleRetea(self, cheie):
		"""Lista retelei `cheie` (radacina pusa cu justSet): canalele cu numar in ordinea numerelor operatorului, apoi
		cele ale retelei fara numar (dupa nume); numai canalele care sunt in lamedb (o scanare de dupa le poate fi
		scos). Numerele merg in coloana numarului (ServiceList.hdsNumereOperator) si in self.hdsNumereRetea (cifrele)."""
		numere, adaugate = [], 0
		for numar, ref in self.hdsRanduriRetea(cheie, self.mode == MODE_RADIO):
			self.servicelist.addService(ref)
			adaugate += 1
			if numar:
				numere.append((ref, numar))
				self.hdsNumereRetea.setdefault(numar, ref)
		# FillFinished fara sort(): ordinea numerelor ramane (finishFill ar sorta dupa nume in nucleu)
		self.servicelist.l.FillFinished()
		if hasattr(self.servicelist, "hdsNumereOperator"):
			self.servicelist.hdsNumereOperator(numere)
		canal = self.hdsCanalulCurent()
		if canal is not None and canal.valid():
			self.servicelist.setCurrent(canal)
			if self.getCurrentSelection() != canal:
				self.hdsMutaLaRand(0)
		print("[ChannelSelection] lista retelei %s: %d canale, %d cu numar" % (cheie, adaugate, len(numere)))

	def hdsNumarInRetea(self, numar):
		"""Canalul cu numarul operatorului `numar` din lista retelei de acum, sau None (alta lista, numar lipsa)."""
		return getattr(self, "hdsNumereRetea", {}).get(int(numar))

	HDS_VEGHE_RETEA_MS = 2000   # cat de des se priveste fisierul retelelor cat lista e in fata

	def hdsGeneratieRetelei(self, root):
		"""Versiunea fisierului retelelor (Components/HdsRetele.generatie, privit chiar acum) cand `root` e lista unei
		retele, chiar daca reteaua nu mai e in fisier; altfel None."""
		if HdsRetele is None or root is None:
			return None
		try:
			if HdsRetele.e_cale_de_retea(root.getPath()):
				return HdsRetele.generatie()
		except Exception as e:
			print("[ChannelSelection] fisierul retelelor: %s" % e)
		return None

	def hdsReteaLaZi(self):
		"""Lista unei retele umpluta din alt fisier al retelelor decat cel de acum (o scanare noua, un fisier pus de
		mana, unul sters): se umple din nou (randurile, numerele din coloana numarului, cifrele), cu cursorul pe acelasi
		canal cand e inca in lista si cu focusul unde era (in cap sau in lista). Se cheama inaintea folosirii numerelor:
		la deschiderea listei, la cifre (in lista si pe bara), la CH+/CH- de pe bara si, cat lista e in fata, din
		hdsVegheRetea. Fara iesire din dosar si fara repornire. -> True daca lista s-a umplut din nou."""
		try:
			root = self.getRoot()
			generatie = self.hdsGeneratieRetelei(root)
			if generatie is None or generatie == self.hdsGeneratieRetea:
				return False
			ales = self.getCurrentSelection()
			comutare = self.hdsComutare
			self.hdsComutare = True       # setRoot nu muta focusul din cap in lista
			try:
				self.setRoot(root)
			finally:
				self.hdsComutare = comutare
			if ales is not None and ales.valid():
				pus = self.getCurrentSelection()
				self.servicelist.setCurrent(ales)
				if self.getCurrentSelection() != ales and pus is not None and pus.valid():
					self.servicelist.setCurrent(pus)
			print("[ChannelSelection] fisierul retelelor s-a schimbat: lista retelei umpluta din nou")
			return True
		except Exception as e:
			print("[ChannelSelection] lista retelei la zi: %s" % e)
			return False

	def hdsPornesteVeghea(self):
		"""La fiecare intrare a listei in fata (onExecBegin): ceasul care tine lista retelei la zi cat lista e in fata."""
		self.hdsCeasRetea.start(self.HDS_VEGHE_RETEA_MS, False)

	def hdsVegheRetea(self):
		"""Ceasul listei: cat lista e in fata, lista retelei se umple din nou cand fisierul retelelor s-a schimbat; cu
		lista inchisa sau cu alt ecran peste ea ceasul se opreste (porneste din nou la deschidere)."""
		if not self.execing:
			self.hdsCeasRetea.stop()
			return
		self.hdsReteaLaZi()

	def hdsAdaugaBucheteFluxuri(self):
		"""Dosarele buchetelor DAB+ (lista radio) / DVB-T2 (lista TV) din satelit, la coada listei „Sateliți”.
		-> {fel: referinta dosarului}."""
		rez = {}
		try:
			from Components import HdsIndexCanale as X
			for fel, fisier in X.buchete_fluxuri("radio" if self.mode == MODE_RADIO else "tv"):
				ref = eServiceReference(X.ref_buchet_flux(fisier))
				ref.setName(X.nume_buchet_flux(fel))
				self.servicelist.addService(ref)
				rez[fel] = ref
		except Exception as e:
			print("[ChannelSelection] buchetele DAB+ / DVB-T2 in Sateliti: %s" % e)
		return rez

	def hdsActualizeazaAcum(self, oprit=False):
		"""Fereastra video a listei arata canalul PORNIT; cu un post de radio pornit, in locul imaginii scrie „Acum pe
		receptor” si numele postului, ca sa nu para felul canalului ales in lista. oprit: la evEnd (nimic pornit)."""
		if not self.hdsCapPornit:
			return
		ref = None if oprit else self.hdsRefPornit()
		pornit = ref is not None and ref.valid()
		radio = pornit and HdsCapLista.e_radio(ref.type, ref.getUnsignedData(0))
		eticheta = _("Acum pe receptor") if radio else ""
		nume = ServiceReference(ref).getServiceName() if radio else ""
		if not pornit and self.mode == MODE_RADIO:
			# lista radio fara niciun post pornit (ultimul post lipseste): fereastra spune asta, nu ramane goala
			nume = _("Niciun post pornit")
		if self["hdsAcumEticheta"].getText() != eticheta:
			self["hdsAcumEticheta"].setText(eticheta)
		if self["hdsAcumNume"].getText() != nume:
			self["hdsAcumNume"].setText(nume)

	def hdsRefPornit(self):
		"""Referinta serviciului pornit. La evStart Navigation.playService nu a pus-o inca in
		currentlyPlayingServiceReference (o pune dupa ce pnav.playService se intoarce), deci se citeste din serviciu."""
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		if info:
			refstr = info.getInfoString(iServiceInformation.sServiceref)
			if refstr:
				return eServiceReference(refstr)
		return self.session.nav.getCurrentlyPlayingServiceReference()

	# ---------------------------------------------------------------- Favorite dintr-o apasare (Components/HdsFavorite.py)
	# In lista nu se vedea niciun buton pentru Favorite (numai MENU > „adauga in
	# favorite”). Tasta FAV, numai in lista TV si in lista radio ale imaginii (nu in alegerea simpla a canalului, de pilda
	# pentru un timer): scurt = canalul ales intra in Favorite (TV sau radio, dupa lista), iar daca e deja acolo o
	# intrebare scurta il scoate; tinut apasat = alege buchetul (cu „mai multe buchete” pornit si cel putin doua buchete
	# proprii, altfel ca apasarea scurta). Apasarea scurta lucreaza la eliberare: la apasare nu se stie inca daca va fi
	# lunga (flagLong vine dupa 4 repetari, main/enigma.cpp). MENU are acelasi rand, primul dupa cautare.
	# Jos, langa „TEXT  Căutare”, tasta desenata spune ce face FAV pe canalul ales (sursa hdsFavTasta: goala pe un dosar,
	# pe un marcaj, in mutare si in editare, cand FAV nu face nimic). Dupa schimbare, o fasie peste partea de jos a listei
	# (hdsFavMesaj) spune ce s-a facut si dispare dupa 2,5 s fara sa opreasca tastele; cu un skin fara fasie, o fereastra
	# care se inchide singura dupa 2 s sau la orice tasta.
	# Cand lista sta chiar pe buchetul schimbat, se citeste din nou (canalul scos dispare, cursorul trece pe urmatorul);
	# la fel lista barii dupa o schimbare facuta din web sau cu FAV tinut apasat pe bara (HdsFavorite.asculta).

	def hdsPornesteFavorite(self):
		if HdsFavorite is None:
			return
		self["hdsFavTasta"] = StaticText("")
		self["hdsFavMesaj"] = StaticText("")
		self.hdsFavLung = False
		self.hdsFavVazut = False
		self.hdsFavDinLista = False
		self.hdsFavCeas = eTimer()
		self.hdsFavCeas.callback.append(self.hdsFavStingeMesajul)
		self["HdsFavoriteActions"] = HdsTacutActionMap(["HdsListaFavoriteActions"],
			{
				"favApasat": self.hdsFavApasat,
				"favLung": self.hdsFavTinut,
				"favEliberat": self.hdsFavEliberat,
			}, -1)
		self.hdsFavPornit = True
		self.onLayoutFinish.append(self.hdsFavLaLayout)
		HdsFavorite.asculta(self.hdsFavAltaSchimbare)
		self.onClose.append(self.hdsFavLaInchidere)

	def hdsFavLaLayout(self):
		# fasia mesajului e in skin (un element legat de sursa ei); altfel mesajul e o fereastra
		sursa = self["hdsFavMesaj"]
		self.hdsFavVazut = any(getattr(r, "source", None) is sursa for r in getattr(self, "renderer", ()))
		self.hdsFavTastaMarita()
		self.hdsFavEticheta()

	def hdsFavTastaMarita(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): caseta tastei FAV (fundalul si textul)
		se lateste spre stanga cat sa incapa cel mai lung dintre cele doua texte (la 115 % "FAV  Adauga la Favorite" iesea
		din caseta de 272 px, la 130 % se pierdeau prima si ultima litera); la stanga e loc liber pana la tastele colorate.
		La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as M
			if not M.marit():
				return
			from enigma import ePoint, eSize
			sursa = self["hdsFavTasta"]

			def dela(r):
				# fundalul are convertorul ConditionalShowHide intre el si sursa: se urca pe lantul surselor
				s = getattr(r, "source", None)
				for _i in range(3):
					if s is sursa:
						return True
					s = getattr(s, "source", None)
				return False
			ale = [r for r in getattr(self, "renderer", ()) if dela(r) and getattr(r, "instance", None) is not None]
			text = [r.instance for r in ale if r.__class__.__name__ == "Label"]
			ale = [r.instance for r in ale]
			if not text:
				return
			et = text[0]
			lat = 0
			for t in (_("Adaugă la Favorite"), _("Scoate din Favorite")):
				et.setText("FAV  " + t)
				lat = max(lat, M.latimeText(et))
			et.setText(sursa.getText())
			p, s = et.position(), et.size()
			dx = min(120, lat + 24 - s.width())
			if dx <= 0:
				return
			for i in ale:
				q, z = i.position(), i.size()
				i.move(ePoint(q.x() - dx, q.y()))
				i.resize(eSize(z.width() + dx, z.height()))
		except Exception as e:
			print("[ChannelSelection] tasta FAV marita: %s" % e)

	def hdsFavLaInchidere(self):
		HdsFavorite.nu_mai_asculta(self.hdsFavAltaSchimbare)
		self.hdsFavCeas.stop()

	def hdsFavTip(self):
		return HdsFavorite.RADIO if self.mode == MODE_RADIO else HdsFavorite.TV

	def hdsFavCanal(self, ref=None):
		"""Textul referintei canalului ales, cand FAV are ce face pe el; altfel None (dosar, marcaj, mutare, editare)."""
		if not self.hdsFavPornit or getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return None
		if ref is None:
			ref = self.getCurrentSelection()
		if ref is None or not ref.valid() or ref.flags & (eServiceReference.isDirectory | eServiceReference.isMarker):
			return None
		text = ref.toString()
		return text if HdsFavorite.se_poate(text) else None

	def hdsFavText(self, ref=None):
		"""„Adaugă la Favorite” / „Scoate din Favorite” pentru canalul ales, sau "" cand FAV nu are ce face."""
		text = self.hdsFavCanal(ref)
		if text is None:
			return ""
		try:
			inauntru = HdsFavorite.este_in(text, tip=self.hdsFavTip())
		except Exception as e:
			print("[ChannelSelection] Favorite: %s" % e)
			return ""
		return _("Scoate din Favorite") if inauntru else _("Adaugă la Favorite")

	def hdsFavEticheta(self, ref=None):
		if not self.hdsFavPornit:
			return
		text = self.hdsFavText(ref)
		if text:
			text = "FAV  " + text
		if self["hdsFavTasta"].getText() != text:
			self["hdsFavTasta"].setText(text)

	def hdsFavNume(self, ref=None):
		if ref is None:
			ref = self.getCurrentSelection()
		try:
			return ServiceReference(ref).getServiceName() or ref.getName() or ""
		except Exception:
			return ""

	def hdsFavApasat(self):
		self.hdsFavLung = False
		return 1

	def hdsFavTinut(self):
		self.hdsFavLung = True
		self.hdsFavAlegeBuchet()
		return 1

	def hdsFavEliberat(self):
		if self.hdsFavLung:
			# apasarea lunga a lucrat deja
			self.hdsFavLung = False
			return 1
		self.hdsFavComuta()
		return 1

	def hdsFavComuta(self, ref_b=None):
		"""FAV scurt si MENU: canalul ales in buchet (Favorite, cand nu se da altul); e deja acolo: intrebarea scurta
		„Scoți ... din ...?”, cu Da ales (OK il scoate)."""
		hdsCapLaLista(self)
		text = self.hdsFavCanal()
		if text is None:
			return
		tip = self.hdsFavTip()
		if ref_b is None:
			ref_b = HdsFavorite.ref_favorite(tip)
		nume = self.hdsFavNume()
		if HdsFavorite.este_in(text, ref_b):
			def raspuns(da=False):
				if da:
					self.hdsFavFa(HdsFavorite.scoate, text, ref_b, tip, nume)
			self.session.openWithCallback(raspuns, MessageBox, HdsFavorite.intrebare_scoatere(nume, ref_b),
				MessageBox.TYPE_YESNO)
			return
		self.hdsFavFa(HdsFavorite.adauga, text, ref_b, tip, nume)

	def hdsFavAlegeBuchet(self):
		"""FAV tinut apasat: buchetul in care intra (sau din care iese) canalul ales. Un singur buchet: ca FAV scurt."""
		hdsCapLaLista(self)
		text = self.hdsFavCanal()
		if text is None:
			return
		buchete = HdsFavorite.buchete_proprii(self.hdsFavTip())
		if len(buchete) < 2:
			self.hdsFavComuta()
			return
		lista = []
		for ref_b, nume_b in buchete:
			eticheta = _("%s: scoate") if HdsFavorite.este_in(text, ref_b) else _("%s: adaugă")
			lista.append((eticheta % nume_b, ref_b))
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(self.hdsFavBuchetAles, ChoiceBox,
			title=_("Alege buchetul pentru %s") % self.hdsFavNume(), list=lista)

	def hdsFavBuchetAles(self, ales=None):
		if ales:
			self.hdsFavComuta(ales[1])

	def hdsFavFa(self, functie, text, ref_b, tip, nume):
		"""Schimbarea (HdsFavorite.adauga / scoate), apoi lista, tasta desenata si mesajul."""
		self.hdsFavDinLista = True
		try:
			rez = functie(text, ref_b, tip, nume)
		except Exception as e:
			print("[ChannelSelection] Favorite: %s: %s" % (e.__class__.__name__, e))
			rez = HdsFavorite.Rezultat(False, canal=nume)
		finally:
			self.hdsFavDinLista = False
		if rez.ok and rez.fapta is not None:
			self.bouquetNumOffsetCache = { }
			self.hdsFavReimprospateaza(rez.fisier, rez.ref if rez.fapta == HdsFavorite.SCOS else None)
		self.hdsFavDupaLista()
		self.hdsFavArata(rez.mesaj())
		return rez

	def hdsFavDupaLista(self):
		"""Panoul din dreapta (canalul si emisiunea alese) si tasta desenata, dupa lista citita din nou: cand iese
		ultimul canal al listei, selectia nu mai anunta schimbarea si panoul ar ramane pe canalul scos."""
		actualizeaza = getattr(self, "updateEventInfo", None)
		if actualizeaza is not None:
			actualizeaza()
		else:
			self.hdsFavEticheta()

	def hdsFavReimprospateaza(self, fisier, scos=None):
		"""Lista se citeste din nou cand sta chiar pe buchetul `fisier`. Canalul scos de sub cursor dispare cu
		removeCurrent (cursorul ramane pe locul lui, adica pe canalul urmator); altfel cursorul ramane pe canalul ales.
		-> True daca lista era pe buchet."""
		root = self.getRoot()
		if root is None or not root.valid() or not fisier or HdsFavorite.fisier_din_ref(root.getPath()) != fisier:
			return False
		cur = self.getCurrentSelection()
		if scos is not None and cur is not None and cur.valid() and HdsFavorite.cheie(cur.toString()) == HdsFavorite.cheie(scos):
			self.servicelist.removeCurrent()
		else:
			self.setRoot(root)
			if cur is not None and cur.valid():
				self.servicelist.setCurrent(cur)
		return True

	def hdsFavAltaSchimbare(self, fisier, scos=None):
		"""Un buchet schimbat in alta parte (alta lista, bara, pagina web): lista se citeste din nou daca sta pe el.
		Nu in mutare si nu in editare: acolo lista tine buchetul deschis pentru schimbarile ei."""
		if self.hdsFavDinLista or getattr(self, "movemode", False) or getattr(self, "bouquet_mark_edit", OFF) != OFF:
			return
		self.bouquetNumOffsetCache = { }
		if self.hdsFavReimprospateaza(fisier, scos):
			self.hdsFavDupaLista()
		else:
			self.hdsFavEticheta()

	def hdsFavArata(self, text):
		if not text:
			return
		if self.hdsFavVazut:
			self["hdsFavMesaj"].setText(text)
			self.hdsFavCeas.start(2500, True)
		else:
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=2, close_on_any_key=True)

	def hdsFavStingeMesajul(self):
		if self["hdsFavMesaj"].getText():
			self["hdsFavMesaj"].setText("")

HISTORYSIZE = 20

#config for lastservice
config.tv = ConfigSubsection()
config.tv.lastservice = ConfigText()
config.tv.lastroot = ConfigText()
config.radio = ConfigSubsection()
config.radio.lastservice = ConfigText()
config.radio.lastroot = ConfigText()
config.servicelist = ConfigSubsection()
config.servicelist.lastmode = ConfigText(default = "tv")

class ChannelSelection(ChannelSelectionBase, ChannelSelectionEdit, ChannelSelectionEPG, SelectionEventInfo):
	def __init__(self, session):
		ChannelSelectionBase.__init__(self,session)
		ChannelSelectionEdit.__init__(self)
		ChannelSelectionEPG.__init__(self)
		SelectionEventInfo.__init__(self)
		if type(self) is ChannelSelection:
			# ecranul skinului imaginii (cu capul listei), apoi cel obisnuit al oricarui skin
			self.skinName = ["HdsListaCanale", "ChannelSelection"]
			self.hdsPornesteCapul()
			self.hdsPornesteFavorite()

		# keyRadio: setModeRadio schimba lista numai cu „mod radio separat” pornit; altfel radioul are ecranul lui,
		# deschis de bara (hdsTastaRadio)
		# HdsListaCanaleTastaturaActions: Backspace de pe o tastatura USB iese din lista, ca Esc (data/keymap.xml)
		self["actions"] = ActionMap(["OkCancelActions", "TvRadioActions", "HdsListaCanaleTastaturaActions"],
			{
				"cancel": self.cancel,
				"ok": self.hdsOkDirect,
				"keyRadio": self.hdsTastaRadio,
				"keyTV": self.setModeTv,
			})

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.__evServiceStart,
				iPlayableService.evEnd: self.__evServiceEnd
			})

		self.lastChannelRootTimer = eTimer()
		self.lastChannelRootTimer.callback.append(self.__onCreate)
		self.lastChannelRootTimer.start(100,True)

		self.history_tv = [ ]
		self.history_radio = [ ]
		self.history = self.history_tv
		self.history_pos = 0

		self.lastservice = config.tv.lastservice
		self.lastroot = config.tv.lastroot
		self.revertMode = None
		config.usage.multibouquet.addNotifier(self.multibouquet_config_changed)
		self.new_service_played = False
		self.onExecBegin.append(self.asciiOn)
		# HDSatelit: lista primeste radacina la prima deschidere (vezi hdsAsiguraRadacina)
		self.onExecBegin.append(self.hdsLaDeschidere)
		# HDSatelit: setModeTv/setModeRadio au rulat macar o data (vezi hdsAsiguraRadacina)
		self.hdsModPus = False
		# HDSatelit: rezolutia exacta si codecul canalelor privite, pentru filtrele cautarii de canale
		try:
			from Screens.HdsCautareCanale import porneste_masuratori
			porneste_masuratori(session)
		except Exception as e:
			print("[ChannelSelection] masuratorile cautarii de canale nu au pornit: %s" % e)

	# HDSatelit: la pornirea pe „ultimul canal" InfoBarGenerics suprima __onCreate (hds_startup_suprimat),
	# deci lista nu primea nicio radacina: sageata jos/sus, OK sau P+/P- dadeau peste o lista goala (vazut in emulator).
	# Radacina se pune acum la prima folosire.
	# Nu ajunge o radacina oarecare: tasta FAV (InfoBar.hdsFavorite), tastele cu cifre (zapToNumber) si ghidul
	# (zapToService) pun radacina fara mod, deci fara „(TV)" in titlu si pe alta cale decat servicePathTV. Se verifica
	# semnul pus de setModeTv/setModeRadio; FAV si tastele colorate trec pe aici din preEnterPath.
	def hdsAsiguraRadacina(self):
		if getattr(self, "hdsModPus", False) and self.getRoot() is not None:
			# o radacina care exista, dar fara canale (pornire pe Favorite goale dupa flash
			# sau dupa importul setarilor), deschidea tot lista goala; atunci se trece pe „Sateliți”.
			# Lista aleasa chiar atunci de om (semnul pus de show* cu cel mult 2 s inainte: FAV deschide lista imediat) se
			# arata asa cum e, si goala. Lantul de pornire alege si el Favorite, dar cu mult inaintea primei sageti.
			if time.time() - (getattr(self, "hdsAlesDeOm", 0) or 0) < 2 or self.hdsPeRadacinaSateliti() or self.hdsAreCanale(self.getRoot()):
				return
			print("[ChannelSelection] radacina fara canale: deschid Sateliti")
			self.hdsDeschideSateliti()
			return
		print("[ChannelSelection] lista fara mod sau fara radacina: pun modul si refac locul tinut minte")
		if config.usage.e1like_radio_mode.value and config.servicelist.lastmode.value == "radio":
			self.setModeRadio()
		else:
			self.setModeTv()

	def hdsLaDeschidere(self):
		# o grupa ceruta de om chiar acum (FAV, tastele colorate de pe bara): lista ei, nu cautarea redeschisa
		alesDeOm = time.time() - (getattr(self, "hdsAlesDeOm", 0) or 0) < 2
		self.hdsAsiguraRadacina()
		# lista retelei deschisa din nou: cu numerele fisierului de acum (o scanare sau un fisier pus intre timp)
		self.hdsReteaLaZi()
		# lista pe sateliti deschisa din nou: numai locul canalului de acum, cursorul pe canal
		self.hdsNormalizeaza()
		self.hdsAlesDeOm = 0
		if self.hdsCapPornit:
			self.hdsCapLaDeschidere()
		# ultimul pas: deschiderea cautarii opreste aici sirul onExecBegin (Screen.execBegin)
		self.hdsRedeschideCautarea(alesDeOm)

	def hdsTastaRadio(self):
		"""Tasta RADIO in lista TV (si fila „Radio”, si meniul listei): lista radio. Cu „mod radio separat” pornit e
		aceeasi lista (setModeRadio). Oprit (implicit), radioul are ecranul lui (ChannelSelectionRadio, deschis de
		InfoBar.showRadio), iar setModeRadio nu schimba nimic: lista TV se inchide ca la EXIT si bara deschide radioul
		imediat ce revine in fata."""
		if config.usage.e1like_radio_mode.value:
			self.setModeRadio()
			return
		if self.movemode or self.bouquet_mark_edit != OFF:
			return
		if hds_dupa_inchidere(lambda infobar: infobar.showRadio()):
			self.cancel()

	def hdsComutaLista(self, dinFila=True):
		if config.usage.e1like_radio_mode.value:
			ChannelSelectionBase.hdsComutaLista(self, dinFila)
			return
		if dinFila:
			hds_cap_urmator_pune(HdsCapLista.FILA)
		self.hdsTastaRadio()

	def hdsTineCursorul(self, directie):
		"""Sus/jos venite din InfoBar (lista inchisa: sagetile care deschid lista si P+/P-) cand lista sta pe
		„Sateliți”: lista e intai cea de la deschidere (numai locul canalului de acum, cursorul pe canal), apoi cursorul
		trece pe canalul urmator / anterior din acelasi loc, cu trecere de la ultimul la primul (antetele sunt marginile
		locului). Un post DAB+ / DVB-T2 din satelit: lista intra in buchetul lui, ca dupa OK pe dosar, si sageata merge
		acolo. -> True daca s-a facut aici."""
		self.hdsAsiguraRadacina()
		if self.execing or not self.hdsPeRadacinaSateliti():
			return False
		self.hdsNormalizeaza()
		canal = self.hdsCanalulCurent()
		intrare = self.hdsIntrareSatelit(canal)
		if intrare is not None and any(intrare == f for f in self.hdsIntrariFluxuri.values()):
			self.enterPath(intrare)
			self.setCurrentSelection(canal)
			return False
		self.hdsMutaInBloc(directie)
		return True

	def moveUp(self):
		self.hdsReteaLaZi()   # lista retelei: canalul vecin dupa numerele fisierului de acum
		if not self.hdsTineCursorul(-1):
			ChannelSelectionBase.moveUp(self)

	def moveDown(self):
		self.hdsReteaLaZi()
		if not self.hdsTineCursorul(+1):
			ChannelSelectionBase.moveDown(self)

	def inBouquet(self):
		self.hdsAsiguraRadacina()
		return ChannelSelectionBase.inBouquet(self)

	def hdsIntraInSatelitulCanalului(self, canal):
		"""Canalul pornit din zap() cu lista pe „Sateliți” (de pilda ultimul canal, de la tasta TV sau RADIO): locul
		lui se deschide in lista pe grupe si cursorul trece pe el; un post DAB+ / DVB-T2 din satelit duce lista in
		buchetul lui, ca dupa OK pe dosar. Un canal fara loc (un flux de internet) lasa lista cum e."""
		if not self.hdsPeRadacinaSateliti():
			return
		if self.hdsArataCanalul(canal):
			return
		intrare = self.hdsIntrareSatelit(canal)
		if intrare is not None and any(intrare == f for f in self.hdsIntrariFluxuri.values()):
			self.enterPath(intrare)
			self.setCurrentSelection(canal)

	def asciiOn(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmAscii)

	def asciiOff(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmNone)

	def execEnd(self):
		# HDSatelit: ecranele deschise peste lista (meniul listei, alegerea buchetului, ghidul) nu scriu text, deci
		# tastatura USB iese din modul ASCII cat lista nu e in fata: acolo Backspace = Iesire si cifrele din dreapta =
		# cifre, ca in restul ecranelor fara text. Un ecran cu text isi pune singur modul ASCII (dupa acest pas), iar
		# lista il pune la loc cand revine in fata (asciiOn, la execBegin).
		self.asciiOff()
		ChannelSelectionBase.execEnd(self)

	def multibouquet_config_changed(self, val):
		self.recallBouquetMode()

	def __evServiceStart(self):
		self.hdsAlesDeOm = 0  # lantul de pornire: Favorite goale nu mai raman lista
		service = self.session.nav.getCurrentService()
		if service:
			info = service.info()
			if info:
				refstr = info.getInfoString(iServiceInformation.sServiceref)
				self.servicelist.setPlayableIgnoreService(eServiceReference(refstr))
		self.hdsRedeseneazaDupaCanalVechi()
		if self.execing:
			self.hdsActualizeazaAcum()

	def hdsRedeseneazaDupaCanalVechi(self):
		"""Dupa un zap nucleul tine canalul de dinainte inca 3 s (lib/dvb/dvb.cpp, m_releaseCachedChannelTimer); cat il
		tine, canalele de pe alte transpondere nu se pot porni si lista le deseneaza gri. O singura redesenare dupa ce
		canalul vechi a fost lasat, ca randurile sa nu ramana gri pana la schimbarea paginii."""
		ceas = getattr(self, "hdsCeasGri", None)
		if ceas is None:
			ceas = self.hdsCeasGri = eTimer()
			ceas.callback.append(self.hdsRedeseneazaGri)
		ceas.start(3500, True)

	def hdsRedeseneazaGri(self):
		# acelasi serviciu de ignorat, pus din nou: lista se redeseneaza toata (setIgnoreService)
		ref = eServiceReference()
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		if info:
			ref = eServiceReference(info.getInfoString(iServiceInformation.sServiceref))
		self.servicelist.setPlayableIgnoreService(ref)

	def __evServiceEnd(self):
		self.servicelist.setPlayableIgnoreService(eServiceReference())
		if self.execing:
			self.hdsActualizeazaAcum(oprit=True)

	def setMode(self):
		self.rootChanged = True
		self.restoreRoot()
		lastservice=eServiceReference(self.lastservice.value)
		if lastservice.valid():
			self.hdsSelecteazaCanalul(lastservice)

	def setModeTv(self):
		self.hdsModPus = True
		if self.revertMode is None and config.servicelist.lastmode.value == "radio":
			self.revertMode = MODE_RADIO
		self.history = self.history_tv
		self.lastservice = config.tv.lastservice
		self.lastroot = config.tv.lastroot
		config.servicelist.lastmode.value = "tv"
		self.setTvMode()
		self.setMode()

	def setModeRadio(self):
		if self.revertMode is None and config.servicelist.lastmode.value == "tv":
			self.revertMode = MODE_TV
		if config.usage.e1like_radio_mode.value:
			self.hdsModPus = True
			self.history = self.history_radio
			self.lastservice = config.radio.lastservice
			self.lastroot = config.radio.lastroot
			config.servicelist.lastmode.value = "radio"
			self.setRadioMode()
			self.setMode()

	def __onCreate(self):
		# bug corectat a doua oara dupa o captura
		# reala care arata "Favorite" gol chiar si cand jurnalul lantului de pornire spunea clar ca a
		# gasit continut (Sateliti/Toate): garda era pusa DUPA setModeTv()/setModeRadio(), deci doar
		# zap()-ul intern era suprimat -- setModeTv() insusi tot rula si, prin setTvMode() ->
		# recallBouquetMode()/restoreRoot(), reseta radacina inapoi la config.tv.lastroot (Favorite),
		# calcand peste radacina corecta pusa cu o clipa inainte de startupService(). Verificat direct:
		# `__onCreate` se declanseaza in mijlocul lantului (intre incercarea "allsat" si "toate" in
		# jurnal), deci cursa chiar se intampla la fiecare pornire, nu doar teoretic. Garda trebuie sa
		# opreasca TOT __onCreate (nu doar partea de zap), caci startupService()/_hdsIncercarePornire()
		# isi cheama singur setModeTv()/setModeRadio() pentru fiecare incercare -- acest mecanism vechi
		# chiar trebuie suprimat complet cand HDSatelit controleaza pornirea, nu doar pe jumatate.
		if getattr(self, "hds_startup_suprimat", False):
			print("[ChannelSelection] __onCreate: suprimat complet (startupService are controlul)")
			return
		if config.usage.e1like_radio_mode.value:
			if config.servicelist.lastmode.value == "tv":
				self.setModeTv()
			else:
				self.setModeRadio()
		else:
			self.setModeTv()
		lastservice=eServiceReference(self.lastservice.value)
		if lastservice.valid():
			print("[ChannelSelection] __onCreate: zap intern NESUPRIMAT, pornesc pe lastservice=%r" % self.lastservice.value)
			self.zap()

	def channelSelected(self):
		if self.hdsOkPeSateliti() or self.hdsOkPeBuchetGol():
			return
		ref = self.getCurrentSelection()
		if self.movemode:
			self.toggleMoveMarked()
		elif (ref.flags & 7) == 7:
			self.enterPath(ref)
		elif self.bouquet_mark_edit != OFF:
			if not (self.bouquet_mark_edit == EDIT_ALTERNATIVES and ref.flags & eServiceReference.isGroup):
				self.doMark()
		elif not (ref.flags & eServiceReference.isMarker): # no marker
			root = self.getRoot()
			if not root or not (root.flags & eServiceReference.isGroup):
				self.zap()
				self.asciiOff()
				# un post de radio (si cel care merge deja) apare pe tot ecranul, cu ecranul radio
				hds_ecran_radio_dupa_ok()
				self.close(ref)

	#called from infoBar and channelSelected
	def zap(self):
		self.revertMode=None
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		nref = self.getCurrentSelection()
		if nref is not None and nref.valid() and (nref.flags & (eServiceReference.isDirectory|eServiceReference.isMarker)):
			# HDSatelit: un dosar (satelit, buchet), un antet sau primul rand al listei pe sateliti si un
			# marcaj nu se pornesc: se merge la „ultimul canal”, ca la HEAD (tasta TV, tasta RADIO in modul e1like, P+
			# cu un flux pornit); garda ref != nref de mai jos nu reporneste canalul care ruleaza.
			nref = None
		if (nref is None or not nref.valid()) and self.lastservice.value:
			lastservice = eServiceReference(self.lastservice.value)
			if lastservice.valid():
				nref = lastservice
		if nref is not None and nref.valid() and (ref is None or ref != nref):
			self.hdsIntraInSatelitulCanalului(nref)
			self.new_service_played = True
			self.session.nav.playService(nref)
			self.saveRoot()
			self.saveChannel(nref)
			config.servicelist.lastmode.save()
			self.addToHistory(nref)

	def hdsLaCanal(self, canal):
		"""Canalul ales in cautare: lista se pune pe el, apoi ca zap() + channelSelected(), dar cu referinta aleasa
		(zap() citeste selectia din lista, iar un canal din alt mod sau alt buchet poate lipsi din ea)."""
		ref = eServiceReference(canal.ref)
		if not ref.valid() or self.movemode or self.bouquet_mark_edit != OFF:
			return
		self.hdsPornesteGasit(canal, ref)
		self.asciiOff()
		hds_ecran_radio_dupa_ok()
		self.close(ref)

	def hdsPornesteGasit(self, canal, ref=None):
		"""Porneste canalul gasit in cautare, fara sa inchida lista (lista radio o cere pentru un canal TV gasit in
		cautarea ei, cu lista TV inchisa)."""
		if ref is None:
			ref = eServiceReference(canal.ref)
		if not ref.valid():
			return
		playing = self.session.nav.getCurrentlyPlayingServiceReference()
		if canal.radio and not config.usage.e1like_radio_mode.value:
			# radio din lista TV, cand radioul are lista lui (tasta RADIO): postul porneste, dar nu devine
			# „ultimul canal TV" (altfel la pornirea urmatoare receptorul ar incepe pe un post de radio in modul TV)
			if playing is None or playing != ref:
				self.session.nav.playService(ref)
			return
		if canal.radio:
			if self.mode != MODE_RADIO:
				self.setModeRadio()
		elif self.mode != MODE_TV:
			self.setModeTv()
		self.hdsPunePeLista(ref, canal)
		self.revertMode = None
		if playing is None or playing != ref:
			self.new_service_played = True
			self.session.nav.playService(ref)
			self.saveRoot()
			self.saveChannel(ref)
			config.servicelist.lastmode.save()
			self.addToHistory(ref)

	def newServicePlayed(self):
		ret = self.new_service_played
		self.new_service_played = False
		return ret

	def addToHistory(self, ref):
		if self.servicePath is not None:
			tmp=self.servicePath[:]
			tmp.append(ref)
			try:
				del self.history[self.history_pos+1:]
			except:
				pass
			self.history.append(tmp)
			hlen = len(self.history)
			if hlen > HISTORYSIZE:
				del self.history[0]
				hlen -= 1
			self.history_pos = hlen-1

	def historyBack(self):
		hlen = len(self.history)
		if hlen > 1 and self.history_pos > 0:
			self.history_pos -= 1
			self.setHistoryPath()

	def historyNext(self):
		hlen = len(self.history)
		if hlen > 1 and self.history_pos < (hlen-1):
			self.history_pos += 1
			self.setHistoryPath()

	def setHistoryPath(self):
		path = self.history[self.history_pos][:]
		ref = path.pop()
		del self.servicePath[:]
		self.servicePath += path
		self.saveRoot()
		root = path[-1]
		cur_root = self.getRoot()
		# HDSatelit: „Sateliți" se umple cu numele si ordinea ei (hdsUmpleSateliti); setRoot ar lua-o din
		# nucleu, cu randuri fara nume si cablul la coada (acolo ramane in istoric un canal fara satelit, de ex. un flux)
		sateliti = self.hdsPeRadacinaSateliti()
		if cur_root and cur_root != root and not sateliti:
			self.setRoot(root)
		self.session.nav.playService(ref)
		if sateliti:
			if cur_root is None or cur_root != root:
				self.hdsDeschideSateliti(canal=ref)
			else:
				# canalul din istoric (de obicei cu lista inchisa): ca la o deschidere noua, numai locul lui deschis
				self.hdsProaspata = True
				self.hdsNormalizeaza()
		else:
			self.setCurrentSelection(ref)
		self.saveChannel(ref)

	def saveRoot(self):
		path = ''
		for i in self.servicePath:
			path += i.toString()
			path += ';'
		if path and path != self.lastroot.value:
			self.lastroot.value = path
			self.lastroot.save()

	def restoreRoot(self):
		tmp = [x for x in self.lastroot.value.split(';') if x != '']
		current = [x.toString() for x in self.servicePath]
		if tmp != current or self.rootChanged or not self.hdsAreCanale(self.getRoot()):
			self.hdsRefaLocul(self.lastroot.value)
			self.rootChanged = False

	def preEnterPath(self, refstr):
		# HDSatelit: FAV si tastele colorate pun intai modul (vezi hdsAsiguraRadacina); locul tinut minte
		# sub tasta se reface doar daca are canale, altfel tasta arata ce cere (ALBASTRU: lista buchetelor sau
		# Favorite), nu „Sateliți", unde ar duce restoreRoot
		self.hdsAsiguraRadacina()
		if self.servicePath and self.servicePath[0] != eServiceReference(refstr):
			pathstr = self.lastroot.value
			if pathstr is not None and pathstr.find(refstr) == 0 and hds_cale_de_pornire(pathstr, self.hdsAreCanaleText) is not None:
				self.restoreRoot()
				lastservice=eServiceReference(self.lastservice.value)
				if lastservice.valid():
					self.hdsSelecteazaCanalul(lastservice)
				return True
		return False

	def saveChannel(self, ref):
		if ref is not None:
			refstr = ref.toString()
		else:
			refstr = ""
		if refstr != self.lastservice.value:
			self.lastservice.value = refstr
			self.lastservice.save()
			# HDSatelit: canalul, in fisierul lui mic, dupa ce a ramas un minut pe ecran (o singura scriere pentru mai
			# multe zap-uri), ca si o oprire fara iesire curata (paznicul, curentul) sa porneasca pe canalul la care te
			# uitai (Components/HdsCanalTinut.py)
			try:
				from Components.HdsCanalTinut import programeaza_scrierea
				programeaza_scrierea()
			except Exception as e:
				print("[ChannelSelection] HdsCanalTinut: %r" % (e,))

	def setCurrentServicePath(self, path):
		if self.history:
			self.history[self.history_pos] = path
		else:
			self.history.append(path)
		self.setHistoryPath()

	def getCurrentServicePath(self):
		if self.history:
			return self.history[self.history_pos]
		return None

	def recallPrevService(self):
		hlen = len(self.history)
		if hlen > 1:
			if self.history_pos == hlen-1:
				tmp = self.history[self.history_pos]
				self.history[self.history_pos] = self.history[self.history_pos-1]
				self.history[self.history_pos-1] = tmp
			else:
				tmp = self.history[self.history_pos+1]
				self.history[self.history_pos+1] = self.history[self.history_pos]
				self.history[self.history_pos] = tmp
			self.setHistoryPath()

	def cancel(self):
		if self.revertMode is None:
			self.restoreRoot()
			lastservice=eServiceReference(self.lastservice.value)
			if lastservice.valid() and self.getCurrentSelection() != lastservice:
				self.hdsSelecteazaCanalul(lastservice)
		elif self.revertMode == MODE_TV:
			self.setModeTv()
		elif self.revertMode == MODE_RADIO:
			self.setModeRadio()
		self.revertMode = None
		self.asciiOff()
		self.close(None)

class RadioInfoBar(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self["RdsDecoder"] = RdsDecoder(self.session.nav)

class ChannelSelectionRadio(ChannelSelectionBase, ChannelSelectionEdit, ChannelSelectionEPG, SelectionEventInfo, InfoBarBase):
	ALLOW_SUSPEND = True

	def __init__(self, session, infobar, faraPornire=False):
		ChannelSelectionBase.__init__(self, session)
		ChannelSelectionEdit.__init__(self)
		ChannelSelectionEPG.__init__(self)
		SelectionEventInfo.__init__(self)
		InfoBarBase.__init__(self)
		self.infobar = infobar
		# faraPornire: numai lista (sageata sus pe bara TV); serviciul de acum merge pana se alege un post cu OK
		self.hdsFaraPornire = faraPornire
		# un serviciu a pornit cat lista era in varful stivei barelor (__evServiceStart): la inchidere bara alege pistele
		self.hdsPornitInLista = False
		if type(self) is ChannelSelectionRadio:
			self.skinName = ["HdsListaCanaleRadio", "ChannelSelectionRadio"]
			self.hdsPornesteCapul()
			self.hdsPornesteFavorite()
		self.onLayoutFinish.append(self.onCreate)
		# lista radio e un ecran nou la fiecare deschidere: cautarea redeschisa dupa un post pornit din ea, la prima
		# executie (dupa onCreate, cand postul de pornit a pornit deja)
		self.onExecBegin.append(self.hdsRedeschideCautarea)

		self.info = session.instantiateDialog(RadioInfoBar) # our simple infobar

		# TV = lista TV (hdsTastaTV), ca RADIO in lista TV; RADIO ramane in lista radio (cursorul pe postul pornit);
		# EXIT inchide lista si lasa postul de radio pornit (__onClose)
		self["actions"] = ActionMap(["OkCancelActions", "TvRadioActions"],
			{
				"keyTV": self.hdsTastaTV,
				"keyRadio": self.hdsTastaRadio,
				"cancel": self.cancel,
				"ok": self.hdsOkDirect,
			})

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.__evServiceStart,
				iPlayableService.evEnd: self.__evServiceEnd
			})

########## RDS Radiotext / Rass Support BEGIN
		self.infobar = infobar # reference to real infobar (the one and only)
		self["RdsDecoder"] = self.info["RdsDecoder"]
		self["RdsActions"] = HelpableActionMap(self, "InfobarRdsActions",
		{
			"startRassInteractive": (self.startRassInteractive, _("View Rass interactive..."))
		},-1)
		self["RdsActions"].setEnabled(False)
		infobar.rds_display.onRassInteractivePossibilityChanged.append(self.RassInteractivePossibilityChanged)
		self.onClose.append(self.__onClose)

	def __onClose(self):
		# EXIT lasa postul de radio pornit: nu se mai porneste canalul TV de dinainte (antena nu se misca). TV porneste
		# numai cand omul il alege: tasta TV, fila „TV” si „Treci la lista TV” (hdsTastaTV: bara deschide lista TV cu
		# InfoBar.showTv, care porneste ultimul canal TV) sau un canal TV ales in cautare (hdsLaCanal).
		# InfoBarBase.__close (chemat inainte, din acelasi onClose) a scos lista din stiva ServiceEventTracker si a
		# notat postul pornit drept serviciu vechi: evenimentele lui nu ar mai ajunge la bara. Postul ramane acum al
		# barii (aceeasi unealta ca la playerul de filme inchis de un canal). evStart-ul si lista pistelor
		# (evUpdatedInfo) ale serviciilor pornite cat lista era deschisa le-a primit lista, care nu alege pistele: bara
		# alege acum sunetul si subtitrarea, ca dupa un zap. Altfel postul ramanea pe pista implicita (nu pe cea aleasa
		# de mana si tinuta minte), iar un canal TV pornit din web peste lista ramanea fara subtitrare, pana la zapul
		# urmator.
		ServiceEventTracker.hdsPreiaServiciul()
		if self.hdsPornitInLista:
			alege = getattr(self.infobar, "hdsAlegeDinNou", None)
			if alege is not None:
				try:
					alege()
				except Exception as e:
					print("[ChannelSelectionRadio] pistele dupa lista radio: %s" % e)
		# Bara mica (RadioInfoBar) e facuta cu instantiateDialog, deci o inchide numai lista. Fara deleteDialog,
		# fereastra ei dispare odata cu lista, dar elementele ei (sigla, numele postului) raman legate la sursele
		# comune (CurrentService): la urmatorul post pornit ele deseneaza intr-un widget fara parinte si enigma2 se
		# opreste (ASSERT in ewidget.cpp). Sursa RdsDecoder e si a listei (self["RdsDecoder"]) si o distruge lista
		# in doClose, deci se scoate intai din bara, ca sa nu fie distrusa de doua ori.
		info = self.info
		if info is not None:
			self.info = None
			if isinstance(info, dict) and "RdsDecoder" in info:
				del info["RdsDecoder"]
			self.session.deleteDialog(info)

	def hdsBaraMicaPesteLista(self):
		"""Bara mica a radioului (RadioInfoBar) se arata peste lista radio numai cu un skin fara ecranul imaginii: in
		HdsListaCanaleRadio ar acoperi randul tastelor colorate si ultimele randuri ale listei, iar postul pornit,
		emisiunea si textul RDS sunt in fereastra din dreapta."""
		return not self.hdsCapVazut

	def startRassInteractive(self):
		self.info.hide();
		self.infobar.rass_interactive = self.session.openWithCallback(self.RassInteractiveClosed, RassInteractive)

	def RassInteractiveClosed(self):
		if self.hdsBaraMicaPesteLista():
			self.info.show()
		self.infobar.rass_interactive = None
		self.infobar.RassSlidePicChanged()

	def RassInteractivePossibilityChanged(self, state):
		self["RdsActions"].setEnabled(state)
########## RDS Radiotext / Rass Support END

	def cancel(self):
		self.infobar.rds_display.onRassInteractivePossibilityChanged.remove(self.RassInteractivePossibilityChanged)
		self.info.hide()
		#set previous tv service
		self.close(None)

	def __evServiceStart(self):
		self.hdsAlesDeOm = 0  # lantul de pornire: Favorite goale nu mai raman lista
		self.hdsPornitInLista = True
		service = self.session.nav.getCurrentService()
		if service:
			info = service.info()
			if info:
				refstr = info.getInfoString(iServiceInformation.sServiceref)
				self.servicelist.setPlayableIgnoreService(eServiceReference(refstr))
		self.hdsRedeseneazaDupaCanalVechi()
		if self.execing:
			self.hdsActualizeazaAcum()

	def hdsRedeseneazaDupaCanalVechi(self):
		"""Dupa un zap nucleul tine canalul de dinainte inca 3 s (lib/dvb/dvb.cpp, m_releaseCachedChannelTimer); cat il
		tine, canalele de pe alte transpondere nu se pot porni si lista le deseneaza gri. O singura redesenare dupa ce
		canalul vechi a fost lasat, ca randurile sa nu ramana gri pana la schimbarea paginii."""
		ceas = getattr(self, "hdsCeasGri", None)
		if ceas is None:
			ceas = self.hdsCeasGri = eTimer()
			ceas.callback.append(self.hdsRedeseneazaGri)
		ceas.start(3500, True)

	def hdsRedeseneazaGri(self):
		# acelasi serviciu de ignorat, pus din nou: lista se redeseneaza toata (setIgnoreService)
		ref = eServiceReference()
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		if info:
			ref = eServiceReference(info.getInfoString(iServiceInformation.sServiceref))
		self.servicelist.setPlayableIgnoreService(ref)

	def __evServiceEnd(self):
		self.servicelist.setPlayableIgnoreService(eServiceReference())
		if self.execing:
			self.hdsActualizeazaAcum(oprit=True)

	def saveRoot(self):
		path = ''
		for i in self.servicePathRadio:
			path += i.toString()
			path += ';'
		if path and path != config.radio.lastroot.value:
			config.radio.lastroot.value = path
			config.radio.lastroot.save()

	def restoreRoot(self):
		tmp = [x for x in config.radio.lastroot.value.split(';') if x != '']
		current = [x.toString() for x in self.servicePath]
		if tmp != current or self.rootChanged or not self.hdsAreCanale(self.getRoot()):
			self.hdsRefaLocul(config.radio.lastroot.value)
			self.rootChanged = False

	def hdsCanalulCurent(self):
		# in lista radio, satelitul ultimului post de radio; fara el, al canalului pornit acum
		ref = eServiceReference(config.radio.lastservice.value)
		if ref.valid():
			return ref
		return ChannelSelectionBase.hdsCanalulCurent(self)

	def preEnterPath(self, refstr):
		if self.servicePathRadio and self.servicePathRadio[0] != eServiceReference(refstr):
			pathstr = config.radio.lastroot.value
			# HDSatelit: ca in ChannelSelection.preEnterPath, locul tinut minte doar daca are canale
			if pathstr is not None and pathstr.find(refstr) == 0 and hds_cale_de_pornire(pathstr, self.hdsAreCanaleText) is not None:
				self.restoreRoot()
				lastservice=eServiceReference(config.radio.lastservice.value)
				if lastservice.valid():
					self.hdsSelecteazaCanalul(lastservice)
				return True
		return False

	def onCreate(self):
		self.setRadioMode()
		self.restoreRoot()
		lastservice=eServiceReference(config.radio.lastservice.value)
		if self.hdsFaraPornire:
			# cursorul pe ultimul post de radio, fara pornire si fara oprire: EXIT lasa canalul de acum neatins
			if lastservice.valid():
				self.hdsSelecteazaCanalul(lastservice)
		elif lastservice.valid():
			self.hdsSelecteazaCanalul(lastservice)
			self.session.nav.playService(lastservice)
		else:
			self.session.nav.stopService()
		if self.hdsBaraMicaPesteLista():
			self.info.show()
		if self.hdsCapPornit:
			self.hdsCapLaDeschidere()

	def hdsTastaTV(self):
		"""Tasta TV (si fila „TV”, si meniul listei) in lista radio: lista TV. Lista radio se inchide, iar bara deschide
		lista TV imediat ce revine in fata (InfoBar.showTv porneste ultimul canal TV). Fara bara (nu se poate deschide
		lista TV), canalul TV de dinainte porneste aici, ca omul sa ajunga totusi la televizor."""
		if self.movemode or self.bouquet_mark_edit != OFF:
			return
		if not hds_dupa_inchidere(lambda infobar: infobar.showTv()):
			tv = eServiceReference(config.tv.lastservice.value)
			if tv.valid():
				self.session.nav.playService(tv)
		self.cancel()

	def hdsTastaRadio(self):
		"""Tasta RADIO in lista radio: lista ramane (radioul nu se opreste); cursorul merge pe postul pornit, ca tasta
		TV in lista TV."""
		if self.movemode or self.bouquet_mark_edit != OFF:
			return
		hdsCapLaLista(self)
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is None or not ref.valid() or not self.hdsEPostRadio(ref):
			# nimic pornit sau un canal TV (lista deschisa cu sageata sus de pe bara TV): ultimul post de radio
			ref = eServiceReference(config.radio.lastservice.value)
		if not ref.valid():
			return
		if self.hdsPeRadacinaSateliti():
			# pe lista pe sateliti: locul postului deschis si cursorul pe post; un post fara loc (DAB+ din satelit):
			# cursorul pe dosarul lui
			if not self.hdsArataCanalul(ref):
				intrare = self.hdsIntrareSatelit(ref)
				if intrare is not None:
					self.setCurrentSelection(intrare)
		elif self.getCurrentSelection() != ref:
			self.hdsSelecteazaCanalul(ref)

	def hdsComutaLista(self, dinFila=True):
		if dinFila:
			hds_cap_urmator_pune(HdsCapLista.FILA)
		self.hdsTastaTV()

	def hdsEPostRadio(self, ref):
		if HdsCapLista is None:
			return True
		return HdsCapLista.e_radio(ref.type, ref.getUnsignedData(0))

	def channelSelected(self): # just return selected service
		if self.hdsOkPeSateliti() or self.hdsOkPeBuchetGol():
			return
		ref = self.getCurrentSelection()
		if self.movemode:
			self.toggleMoveMarked()
		elif (ref.flags & 7) == 7:
			self.enterPath(ref)
		elif self.bouquet_mark_edit != OFF:
			if not (self.bouquet_mark_edit == EDIT_ALTERNATIVES and ref.flags & eServiceReference.isGroup):
				self.doMark()
		elif not (ref.flags & eServiceReference.isMarker): # no marker
			cur_root = self.getRoot()
			if not cur_root or not (cur_root.flags & eServiceReference.isGroup):
				playingref = self.session.nav.getCurrentlyPlayingServiceReference()
				if playingref is None or playingref != ref:
					self.session.nav.playService(ref)
					config.radio.lastservice.value = ref.toString()
					config.radio.lastservice.save()
				self.saveRoot()
				# OK pe un post (si pe cel care merge deja): lista se inchide si postul ramane pe tot ecranul, cu ecranul
				# radio, ca OK in lista TV; inainte lista ramanea deschisa si OK parea ca nu face nimic
				hds_ecran_radio_dupa_ok()
				self.cancel()

	def hdsLaCanal(self, canal):
		# un post gasit in cautare: ca OK in lista (se pune pe el, il porneste, lista se inchide, ecranul radio)
		ref = eServiceReference(canal.ref)
		if not ref.valid() or self.movemode or self.bouquet_mark_edit != OFF:
			return
		if not getattr(canal, "radio", True):
			# un canal TV ales in cautarea din lista radio: omul a ales TV. Lista radio se inchide, iar lista TV a
			# barii il porneste ca pe un canal gasit acolo (ultimul canal TV, locul in lista, istoricul); postul de
			# radio nu devine ultimul post cu un canal TV
			if hds_dupa_inchidere(lambda infobar: infobar.servicelist.hdsPornesteGasit(canal)):
				self.cancel()
			return
		self.hdsPunePeLista(ref, canal)
		playingref = self.session.nav.getCurrentlyPlayingServiceReference()
		if playingref is None or playingref != ref:
			self.session.nav.playService(ref)
			config.radio.lastservice.value = ref.toString()
			config.radio.lastservice.save()
		self.saveRoot()
		hds_ecran_radio_dupa_ok()
		self.cancel()

class SimpleChannelSelection(ChannelSelectionBase, SelectionEventInfo):
	def __init__(self, session, title):
		ChannelSelectionBase.__init__(self, session)
		SelectionEventInfo.__init__(self)
		if type(self) is SimpleChannelSelection:
			self.skinName = ["HdsListaCanaleSimpla", "SimpleChannelSelection"]
			self.hdsPornesteCapul()
		self["actions"] = ActionMap(["OkCancelActions", "TvRadioActions"],
			{
				"cancel": self.close,
				"ok": self.hdsOkDirect,
				"keyRadio": self.setModeRadio,
				"keyTV": self.setModeTv,
			})
		self.title = title
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setModeTv()
		if self.hdsCapPornit:
			self.hdsCapLaDeschidere()

	def channelSelected(self): # just return selected service
		if self.hdsOkPeSateliti():
			return
		ref = self.getCurrentSelection()
		if (ref.flags & 7) == 7:
			self.enterPath(ref)
		elif not (ref.flags & eServiceReference.isMarker):
			ref = self.getCurrentSelection()
			self.close(ref)

	def hdsLaCanal(self, canal):
		# alegerea unui canal (de ex. pentru un timer): canalul gasit se intoarce direct
		ref = eServiceReference(canal.ref)
		if ref.valid():
			self.close(ref)

	def setModeTv(self):
		self.setTvMode()
		self.showFavourites()
		self.hdsFaraListaGoala()

	def setModeRadio(self):
		self.setRadioMode()
		self.showFavourites()
		self.hdsFaraListaGoala()

	def hdsFaraListaGoala(self):
		# HDSatelit: alegerea unui canal (de ex. pentru un timer) nu mai incepe pe Favorite goale
		if not self.hdsAreCanale(self.getRoot()):
			self.hdsDeschideSateliti()
