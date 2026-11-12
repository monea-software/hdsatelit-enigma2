# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Setarile CI ca in enigma2 OE-Alliance: slot pornit/oprit, intarzierea DVB CI, intarzierea pornirii CI, codul PIN pastrat,
# mesajele CI, Relevant PIDs Routing, debitul extra_high. Din sursele GPL enigma2 (OE-Alliance), depozitul enigma2 al stratului,
# commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/python/Screens/Ci.py (InitCiConfig, CiMessageHandler, CiSelection),
# adaptate la ecranul nostru; alocarea canalelor (CiAssignment) e a noastra.
# CI+ (acelasi commit): „CI+ Helper” (config.cimisc.cihelperenabled, cand exista /usr/bin/ciplushelper), „Disable operator
# profiles” si „Descrambling options” (config.ci[n].disable_operator_profile, alternative_ca_handling; le citeste nucleul,
# lib/dvb_ci/dvbci.cpp). Certificatele aparatului (/etc/ciplus) NU vin cu imaginea: le pune omul (FTP sau pagina web).
import os
import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ActionMap import NumberActionMap
from Components.Label import Label

from Components.config import config, ConfigSubsection, ConfigSelection, ConfigSubList, getConfigListEntry, KEY_LEFT, KEY_RIGHT, KEY_0, ConfigNothing, ConfigPIN, ConfigYesNo, ConfigText
from Components.ConfigList import ConfigList

from Components.SystemInfo import SystemInfo

from enigma import eTimer, eDVBCI_UI, eDVBCIInterfaces

MAX_NUM_CI = 4
# un PIN pastrat trimis singur si cerut iar de modul in acest rastimp e probabil gresit: nu se mai trimite singur
# (cardul se poate bloca dupa cateva coduri gresite), se cere omului
PIN_REPETAT_SECUNDE = 60
_pinTrimisLa = {}

# CI+: fisierele aparatului pe care le cere autentificarea (lib/dvb_ci/dvbci_ccmgr_helper.cpp,
# ciplus_cert_param_files_exists); le emite CI Plus LLP producatorilor, deci imaginea nu le are
CIPLUS_DOSAR = "/etc/ciplus"
CIPLUS_FISIERE = ("param", "root.pem", "customer.pem", "device.pem")


def ciplusFisiereLipsa(dosar=None):
	"""Numele fisierelor CI+ care lipsesc (sau nu se pot citi) din /etc/ciplus; lista goala = CI+ poate porni."""
	dosar = dosar or CIPLUS_DOSAR
	return [nume for nume in CIPLUS_FISIERE if not os.access(os.path.join(dosar, nume), os.R_OK)]


def ciplusTextLipsa(lipsa=None):
	"""Mesajul limpede pentru om cand lipsesc certificatele (ecranul CI si pagina web)."""
	lipsa = ciplusFisiereLipsa() if lipsa is None else lipsa
	return "%s\n%s %s\n%s" % (
		_("Pentru CI+ sunt necesare certificatele aparatului în /etc/ciplus"),
		_("Lipsesc:"), ", ".join(lipsa),
		_("Pune cele patru fișiere (param, root.pem, customer.pem, device.pem) prin FTP în /etc/ciplus sau din pagina web Common Interface (http://IP-ul receptorului/common-interface). Până atunci modulul lucrează ca CI simplu, dacă poate."))


def resetModuleCiplus(motiv):
	"""Certificatele CI+ se citesc la pornirea modulului: modulele prezente se repornesc singure (dupa ce omul a pus
	sau a sters certificatele din web), ca sa nu fie nimic de repornit."""
	for slot in range(MAX_NUM_CI):
		try:
			if eDVBCI_UI.getInstance().getState(slot) in (1, 2):
				print("[Ci] %s: slotul %d reporneste modulul" % (motiv, slot))
				eDVBCI_UI.getInstance().setReset(slot)
		except Exception as e:
			print("[Ci] repornirea modulului %d: %r" % (slot, e))


_ciplusTimere = {}


def _resetSlotCiplus(slot):
	try:
		if eDVBCI_UI.getInstance().getState(slot) in (1, 2) and not ciplusFisiereLipsa():
			print("[Ci] optiunile CI+ schimbate: slotul %d reporneste modulul" % slot)
			eDVBCI_UI.getInstance().setReset(slot)
	except Exception as e:
		print("[Ci] repornirea modulului %d: %r" % (slot, e))


def setCIPlusOption(configElement):
	"""Profilurile operatorului si optiunile de decriptare: salvate pe disc (nucleul le citeste din settings), apoi
	modulul slotului repornit, ca alegerea sa lucreze fara repornirea receptorului."""
	try:
		configElement.save()
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		print("[Ci] salvarea optiunii CI+: %r" % (e,))
		return
	slot = getattr(configElement, "slotid", None)
	if slot is None or ciplusFisiereLipsa():
		return
	# o singura repornire a modulului dupa ultima apasare (stanga/dreapta prin alegeri nu-l reporneste la fiecare pas)
	if slot not in _ciplusTimere:
		_ciplusTimere[slot] = eTimer()
		_ciplusTimere[slot].callback.append(lambda s=slot: _resetSlotCiplus(s))
	_ciplusTimere[slot].start(3000, True)

def setCIBitrate(configElement):
	if configElement.value == "no":
		eDVBCI_UI.getInstance().setClockRate(configElement.slotid, eDVBCI_UI.rateNormal)
	elif configElement.value == "extra_high":
		eDVBCI_UI.getInstance().setClockRate(configElement.slotid, getattr(eDVBCI_UI, "rateExtraHigh", 2))
	else:
		eDVBCI_UI.getInstance().setClockRate(configElement.slotid, eDVBCI_UI.rateHigh)

def setCIEnabled(configElement):
	try:
		eDVBCI_UI.getInstance().setEnabled(configElement.slotid, configElement.value)
	except Exception as e:
		print("[Ci] slotul %d pornit/oprit: %r" % (configElement.slotid, e))

def _scrieNod(cale, text):
	try:
		with open(cale, "w") as fisier:
			fisier.write(text)
	except (IOError, OSError) as e:
		print("[Ci] %s: %r" % (cale, e))

def setdvbCiDelay(configElement):
	_scrieNod("/proc/stb/tsmux/rmx_delay", configElement.value)

def setRelevantPidsRouting(configElement):
	_scrieNod("/proc/stb/tsmux/ci%d_relevant_pids_routing" % configElement.slotid, "yes" if configElement.value else "no")

def _debitAlegeri(slot):
	alegeri = [("no", _("Normal")), ("yes", _("High"))]
	try:
		with open("/proc/stb/tsmux/ci%d_tsclk_choices" % slot) as fisier:
			if "extra_high" in fisier.read():
				alegeri.append(("extra_high", _("Extra High")))
	except (IOError, OSError):
		pass
	return alegeri

def InitCiConfig():
	config.ci = ConfigSubList()
	config.cimisc = ConfigSubsection()
	# intarzierea pornirii CI o citeste nucleul din /etc/enigma2/settings la pornire (lib/dvb_ci/dvbci.cpp)
	config.cimisc.bootDelay = ConfigSelection(default="5", choices=[(str(x), "%d s" % x) for x in range(16)])
	# CI+ Helper (OE-Alliance): programul extern /usr/bin/ciplushelper il porneste scriptul lui, dupa aceasta setare
	# (cere repornire); imaginea nu-l are, randul apare numai cand omul l-a pus
	config.cimisc.cihelperenabled = ConfigYesNo(default=True)
	if SystemInfo.get("CommonInterfaceCIDelay"):
		config.cimisc.dvbCiDelay = ConfigSelection(default="256", choices=[(x, x) for x in ("16", "32", "64", "128", "256")])
		config.cimisc.dvbCiDelay.addNotifier(setdvbCiDelay)
	for slot in range(MAX_NUM_CI):
		config.ci.append(ConfigSubsection())
		# pornit/oprit: nucleul il citeste singur la pornire, deci aici numai schimbarile (initial_call=False)
		config.ci[slot].enabled = ConfigYesNo(default=True)
		config.ci[slot].enabled.slotid = slot
		config.ci[slot].enabled.addNotifier(setCIEnabled, initial_call=False)
		config.ci[slot].canDescrambleMultipleServices = ConfigSelection(choices = [("auto", _("Auto")), ("no", _("No")), ("yes", _("Yes"))], default = "auto")
		config.ci[slot].use_static_pin = ConfigYesNo(default=True)
		config.ci[slot].static_pin = ConfigText(default="", fixed_size=False)
		config.ci[slot].show_ci_messages = ConfigYesNo(default=True)
		# CI+ (OE-Alliance): nucleul le citeste din /etc/enigma2/settings la pornirea modulului
		config.ci[slot].disable_operator_profile = ConfigYesNo(default=False)
		config.ci[slot].disable_operator_profile.slotid = slot
		config.ci[slot].disable_operator_profile.addNotifier(setCIPlusOption, initial_call=False)
		config.ci[slot].alternative_ca_handling = ConfigSelection(default="0", choices=[
			("0", _("Off")), ("1", _("Închide dispozitivul CA la sfârșitul programului")),
			("2", _("Indexul dispozitivului CA decalat")), ("3", _("Decalat și închis la sfârșit"))])
		config.ci[slot].alternative_ca_handling.slotid = slot
		config.ci[slot].alternative_ca_handling.addNotifier(setCIPlusOption, initial_call=False)
		if SystemInfo["CommonInterfaceSupportsHighBitrates"]:
			config.ci[slot].canHandleHighBitrates = ConfigSelection(choices = _debitAlegeri(slot), default = "no")
			config.ci[slot].canHandleHighBitrates.slotid = slot
			config.ci[slot].canHandleHighBitrates.addNotifier(setCIBitrate)
		if SystemInfo.get("CI%dRelevantPidsRoutingSupport" % slot):
			config.ci[slot].relevantPidsRouting = ConfigYesNo(default=False)
			config.ci[slot].relevantPidsRouting.slotid = slot
			config.ci[slot].relevantPidsRouting.addNotifier(setRelevantPidsRouting)
	_mutaSlotOprit()
	# alocarile salvate (/etc/enigma2/ci<slot>.xml) se dau modulelor la fiecare pornire
	try:
		from Tools.CIHelper import cihelper
		cihelper.load_ci_assignment()
	except Exception as e:
		print("[Ci] alocarile CI la pornire: %r" % (e,))

def _mutaSlotOprit():
	"""„Oprește slotul” vechi (regula goala, ci<slot>.oprit, 0.7.4 de proba) devine „CI pornit: Nu”, o singura data."""
	helper = _helper()
	if helper is None:
		return
	for slot in range(MAX_NUM_CI):
		try:
			if helper.slotOprit(slot):
				helper.opresteSlot(slot, False)
				config.ci[slot].enabled.value = False
				config.ci[slot].enabled.save()
				config.ci[slot].enabled.changed()
		except Exception as e:
			print("[Ci] slotul oprit vechi %d: %r" % (slot, e))

def _helper():
	"""Tools/CIHelper (alocarile), sau None cand nu se poate incarca."""
	try:
		from Tools import CIHelper
		return CIHelper
	except Exception as e:
		print("[Ci] CIHelper: %r" % (e,))
		return None

def _pasiDecriptare(slot, screen):
	"""Mesajul modulului ajunge si in pasii decriptarii (Components/HdsPasiDecriptare.py), numai cu setarea lor
	pornita. enigma2 da ecranul MMI o singura data (getMMIScreen), deci il primesc de aici, nu il cer a doua oara."""
	try:
		from Components import HdsPasiDecriptare
		HdsPasiDecriptare.mesaj_ci(slot, screen)
	except Exception as e:
		print("[Ci] pasii decriptarii: %s" % e)

def _pinPastrat(slot):
	try:
		setari = config.ci[slot]
		pin = str(setari.static_pin.value or "")
		return pin if setari.use_static_pin.value and pin.isdigit() else ""
	except Exception:
		return ""

def _pastreazaPin(slot, pin):
	"""Cu „Păstrează codul PIN” pornit, PIN-ul scris omului la cererea modulului se tine minte fara intrebare."""
	try:
		if config.ci[slot].use_static_pin.value and str(pin).isdigit():
			config.ci[slot].static_pin.value = str(pin)
			config.ci[slot].static_pin.save()
	except Exception as e:
		print("[Ci] PIN-ul pastrat %d: %r" % (slot, e))

def raspundeCuPinPastrat(slot, screen, handler):
	"""Cererea de PIN a modulului primeste singura PIN-ul pastrat. Nu cand PIN-ul are alta lungime decat cere modulul si
	nici cand modulul il cere iar la scurt timp dupa ce l-am trimis (probabil gresit): atunci se intreaba omul."""
	if not screen or screen[0][0] != "ENQ":
		return False
	cerere = [x for x in screen if x[0] == "PIN"]
	pin = _pinPastrat(slot)
	if not cerere or not pin:
		return False
	lungime = cerere[0][1] if len(cerere[0]) > 1 else 0
	if lungime and len(pin) != lungime:
		return False
	acum = time.time()
	if acum - _pinTrimisLa.get(slot, -PIN_REPETAT_SECUNDE - 1) < PIN_REPETAT_SECUNDE:
		_pinTrimisLa.pop(slot, None)
		print("[Ci] slotul %d cere iar PIN-ul: nu-l mai trimit singur" % slot)
		return False
	_pinTrimisLa[slot] = acum
	handler.answerEnq(slot, pin)
	return True

class MMIDialog(Screen):
	def __init__(self, session, slotid, action, handler = eDVBCI_UI.getInstance(), wait_text = _("wait for ci..."), screen_data = None):
		Screen.__init__(self, session)

		print("MMIDialog with action" + str(action))

		self.mmiclosed = False
		self.tag = None
		self.slotid = slotid
		self.screen_data = screen_data

		self.timer = eTimer()
		self.timer.callback.append(self.keyCancel)

		#else the skins fails
		self["title"] = Label("")
		self["subtitle"] = Label("")
		self["bottom"] = Label("")
		self["entries"] = ConfigList([ ])

		self["actions"] = NumberActionMap(["SetupActions"],
			{
				"ok": self.okbuttonClick,
				"cancel": self.keyCancel,
				#for PIN
				"left": self.keyLeft,
				"right": self.keyRight,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				"0": self.keyNumberGlobal
			}, -1)

		self.action = action

		self.handler = handler
		self.wait_text = wait_text

		if action == 2:		#start MMI
			handler.startMMI(self.slotid)
			self.showWait()
		elif action == 3:		#mmi already there (called from infobar)
			self.showScreen()

	def addEntry(self, list, entry):
		if entry[0] == "TEXT":		#handle every item (text / pin only?)
			list.append( (entry[1], ConfigNothing(), entry[2]) )
		if entry[0] == "PIN":
			pinlength = entry[1]
			if entry[3] == 1:
				# masked pins:
				x = ConfigPIN(0, len = pinlength)  # PIN-ul se vede cat il scrii
			else:
				# unmasked pins:
				x = ConfigPIN(0, len = pinlength)
			self["subtitle"].setText(entry[2])
			list.append( getConfigListEntry("", x) )
			self["bottom"].setText(_("please press OK when ready"))

	def okbuttonClick(self):
		self.timer.stop()
		if not self.tag:
			return
		if self.tag == "WAIT":
			print("do nothing - wait")
		elif self.tag == "MENU":
			print("answer MENU")
			cur = self["entries"].getCurrent()
			if cur:
				self.handler.answerMenu(self.slotid, cur[2])
			else:
				self.handler.answerMenu(self.slotid, 0)
			self.showWait()
		elif self.tag == "LIST":
			print("answer LIST")
			self.handler.answerMenu(self.slotid, 0)
			self.showWait()
		elif self.tag == "ENQ":
			cur = self["entries"].getCurrent()
			answer = str(cur[1].value)
			length = len(answer)
			while length < cur[1].getLength():
				answer = '0'+answer
				length+=1
			_pastreazaPin(self.slotid, answer)
			self.handler.answerEnq(self.slotid, answer)
			self.showWait()

	def closeMmi(self):
		self.timer.stop()
		self.close(self.slotid)

	def keyCancel(self):
		self.timer.stop()
		if not self.tag or self.mmiclosed:
			self.closeMmi()
		elif self.tag == "WAIT":
			self.handler.stopMMI(self.slotid)
			self.closeMmi()
		elif self.tag in ( "MENU", "LIST" ):
			print("cancel list")
			self.handler.answerMenu(self.slotid, 0)
			self.showWait()
		elif self.tag == "ENQ":
			print("cancel enq")
			self.handler.cancelEnq(self.slotid)
			self.showWait()
		else:
			print("give cancel action to ci")

	def keyConfigEntry(self, key):
		self.timer.stop()
		try:
			self["entries"].handleKey(key)
		except:
			pass

	def keyNumberGlobal(self, number):
		self.timer.stop()
		self.keyConfigEntry(KEY_0 + number)

	def keyLeft(self):
		self.timer.stop()
		self.keyConfigEntry(KEY_LEFT)

	def keyRight(self):
		self.timer.stop()
		self.keyConfigEntry(KEY_RIGHT)

	def updateList(self, list):
		List = self["entries"]
		try:
			List.instance.moveSelectionTo(0)
		except:
			pass
		List.l.setList(list)

	def showWait(self):
		self.tag = "WAIT"
		self["title"].setText("")
		self["subtitle"].setText("")
		self["bottom"].setText("")
		list = [ ]
		list.append( (self.wait_text, ConfigNothing()) )
		self.updateList(list)

	def showScreen(self):
		dinHandler = self.screen_data is not None
		if dinHandler:
			# ecranul deja luat de CiMessageHandler (getMMIScreen il da o singura data); acolo s-a hotarat deja daca
			# PIN-ul pastrat se trimite singur (cerut iar in 60 s = nu), deci aici nu se mai incearca
			screen, self.screen_data = self.screen_data, None
		else:
			screen = self.handler.getMMIScreen(self.slotid)
			_pasiDecriptare(self.slotid, screen)

		list = [ ]

		self.timer.stop()
		if not screen:
			return
		if not dinHandler and raspundeCuPinPastrat(self.slotid, screen, self.handler):
			self.showWait()
			return
		if len(screen) > 0 and screen[0][0] == "CLOSE":
			timeout = screen[0][1]
			self.mmiclosed = True
			if timeout > 0:
				self.timer.start(timeout*1000, True)
			else:
				self.keyCancel()
		else:
			self.mmiclosed = False
			self.tag = screen[0][0]
			for entry in screen:
				if entry[0] == "PIN":
					self.addEntry(list, entry)
				else:
					if entry[0] == "TITLE":
						self["title"].setText(entry[1])
					elif entry[0] == "SUBTITLE":
						self["subtitle"].setText(entry[1])
					elif entry[0] == "BOTTOM":
						self["bottom"].setText(entry[1])
					elif entry[0] == "TEXT":
						self.addEntry(list, entry)
			self.updateList(list)

	def ciStateChanged(self):
		do_close = False
		if self.action == 0:			#reset
			do_close = True
		if self.action == 1:			#init
			do_close = True

		#module still there ?
		if self.handler.getState(self.slotid) != 2:
			do_close = True

		#mmi session still active ?
		if self.handler.getMMIState(self.slotid) != 1:
			do_close = True

		if do_close:
			self.closeMmi()
		elif self.action > 1 and self.handler.availableMMI(self.slotid) == 1:
			self.showScreen()

		#FIXME: check for mmi-session closed

def _inStandby():
	try:
		import Screens.Standby
		return bool(Screens.Standby.inStandby)
	except Exception:
		return False

class CiMessageHandler:
	def __init__(self):
		self.session = None
		self.ci = { }
		self.dlgs = { }
		eDVBCI_UI.getInstance().ciStateChanged.get().append(self.ciStateChanged)
		SystemInfo["CommonInterface"] = eDVBCIInterfaces.getInstance().getNumOfSlots() > 0
		try:
			file = open("/proc/stb/tsmux/ci0_tsclk", "r")
			file.close()
			SystemInfo["CommonInterfaceSupportsHighBitrates"] = True
		except:
			SystemInfo["CommonInterfaceSupportsHighBitrates"] = False

	def setSession(self, session):
		self.session = session

	def ciStateChanged(self, slot):
		if slot in self.ci:
			self.ci[slot](slot)
		else:
			handler = eDVBCI_UI.getInstance()
			if slot in self.dlgs:
				self.dlgs[slot].ciStateChanged()
			elif handler.availableMMI(slot) == 1 and self.session:
				# ca in OE-Alliance: ecranul se ia o data; cererea de PIN primeste singura PIN-ul pastrat, iar cu
				# „Arată mesajele CI” oprit mesajele modulului nu mai sar pe ecran (cererea de PIN fara PIN pastrat da)
				screen = handler.getMMIScreen(slot)
				_pasiDecriptare(slot, screen)
				if not screen or screen[0][0] == "CLOSE":
					return
				if raspundeCuPinPastrat(slot, screen, handler):
					return
				arata = True
				try:
					arata = bool(config.ci[slot].show_ci_messages.value)
				except Exception:
					pass
				if screen[0][0] == "ENQ" and any(x[0] == "PIN" for x in screen):
					arata = True
				if arata and not _inStandby():
					self.dlgs[slot] = self.session.openWithCallback(self.dlgClosed, MMIDialog, slot, 3, screen_data=screen)

	def dlgClosed(self, slot):
		if slot in self.dlgs:
			del self.dlgs[slot]

	def registerCIMessageHandler(self, slot, func):
		self.unregisterCIMessageHandler(slot)
		self.ci[slot] = func

	def unregisterCIMessageHandler(self, slot):
		if slot in self.ci:
			del self.ci[slot]

CiHandler = CiMessageHandler()

class CiSelection(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self["actions"] = ActionMap(["OkCancelActions", "CiSelectionActions"],
			{
				"left": self.keyLeft,
				"right": self.keyRight,
				"ok": self.okbuttonClick,
				"cancel": self.cancel
			},-1)

		self.dlg = None
		self.state = { }
		self.list = [ ]
		self.appendCommon()
		for slot in range(MAX_NUM_CI):
			state = eDVBCI_UI.getInstance().getState(slot)
			if state != -1:
				self.appendEntries(slot, state)
				CiHandler.registerCIMessageHandler(slot, self.ciStateChanged)

		menuList = ConfigList(self.list)
		menuList.list = self.list
		menuList.l.setList(self.list)
		self["entries"] = menuList
		self["entries"].onSelectionChanged.append(self.selectionChanged)
		self["text"] = Label(_("Slot %d")%(1))

	def selectionChanged(self):
		cur = self["entries"].getCurrent()
		if not cur or len(cur) < 4:
			return
		if cur[3] is None:
			self["text"].setText(_("Setări comune"))
			return
		slot = cur[3]
		ajutor = {
			"pin": _("OK: scrii codul PIN al cardului; modulul îl primește singur când îl cere."),
			"pinsterge": _("OK: modulul va cere iar codul PIN pe ecran."),
			"ciplus": _("OK: ce face CI+ și de ce are nevoie."),
		}.get(cur[2])
		if ajutor:
			self["text"].setText(ajutor)
		elif self.state.get(slot) == 3:
			self["text"].setText(_("Slot %d") % (slot + 1) + " - " + _("modul oprit"))
		else:
			self["text"].setText(_("Slot %d") % (slot + 1))

	def keyConfigEntry(self, key):
		try:
			self["entries"].handleKey(key)
			element = self["entries"].getCurrent()[1]
			element.save()
		except:
			return
		# „Păstrează codul PIN” adauga sau scoate randurile PIN-ului: lista se reface pe loc
		if any(element is getattr(config.ci[s], "use_static_pin", None) for s in range(MAX_NUM_CI)):
			self.updateState()

	def keyLeft(self):
		self.keyConfigEntry(KEY_LEFT)

	def keyRight(self):
		self.keyConfigEntry(KEY_RIGHT)

	def appendCommon(self):
		"""Setarile comune tuturor sloturilor, sus, o singura data (ca „Setări comune” din OE-Alliance)."""
		if not any(eDVBCI_UI.getInstance().getState(slot) != -1 for slot in range(MAX_NUM_CI)):
			return
		if hasattr(config.cimisc, "dvbCiDelay"):
			self.list.append((_("Întârzierea DVB CI"), config.cimisc.dvbCiDelay, None, None))
		self.list.append((_("Întârzierea pornirii CI"), config.cimisc.bootDelay, None, None))
		if SystemInfo.get("CIPlusHelper"):
			self.list.append((_("Ajutorul CI+ (cere repornirea receptorului)"), config.cimisc.cihelperenabled, None, None))

	def appendEntries(self, slot, state):
		self.state[slot] = state
		titlu = _("Slot %d") % (slot + 1)
		if state == 3:
			titlu += " - " + _("modul oprit")
		self.list.append((titlu, ConfigNothing(), "titlu", slot))
		self.list.append((_("CI pornit"), config.ci[slot].enabled, None, slot))
		if state == 3:
			# slotul oprit: nucleul nu mai vorbeste cu modulul, deci restul randurilor n-ar face nimic
			return
		if not self.ciplushelper():
			self.list.append( (_("Reset"), ConfigNothing(), 0, slot) )
			self.list.append( (_("Init"), ConfigNothing(), 1, slot) )

		if self.state[slot] == 0:			#no module
			self.list.append( (_("no module found"), ConfigNothing(), 2, slot) )
		elif self.state[slot] == 1:		#module in init
			self.list.append( (_("init module"), ConfigNothing(), 2, slot) )
		elif self.state[slot] == 2:		#module ready
			#get appname
			appname = eDVBCI_UI.getInstance().getAppName(slot)
			self.list.append( (appname, ConfigNothing(), 2, slot) )
		# alocarile tin de slot, nu de modul: se pot schimba si cu modulul in initializare (un CI+ care
		# nu s-a autentificat ramane „init module”) sau scos; regulile se folosesc cand modulul e gata
		self.list.append((_("Alocă canale modulului"), ConfigNothing(), "alocare", slot))

		setari = config.ci[slot]
		self.list.append((_("Păstrează codul PIN"), setari.use_static_pin, None, slot))
		if setari.use_static_pin.value:
			self.list.append((_("Introdu codul PIN păstrat"), ConfigNothing(), "pin", slot))
			if _pinPastrat(slot):
				self.list.append((_("Șterge codul PIN păstrat"), ConfigNothing(), "pinsterge", slot))
		self.list.append((_("Arată mesajele CI"), setari.show_ci_messages, None, slot))
		# CI+: starea pe un rand; optiunile CI+ numai cand certificatele exista (fara ele n-ar schimba nimic)
		self.list.append((self.textCiplus(slot), ConfigNothing(), "ciplus", slot))
		if not ciplusFisiereLipsa():
			self.list.append((_("Dezactivează profilurile operatorului"), setari.disable_operator_profile, None, slot))
			self.list.append((_("Opțiunile de decriptare"), setari.alternative_ca_handling, None, slot))
		self.list.append((_("Multiple service support"), setari.canDescrambleMultipleServices, None, slot))
		if SystemInfo["CommonInterfaceSupportsHighBitrates"]:
			self.list.append((_("High bitrate support"), setari.canHandleHighBitrates, None, slot))
		if hasattr(setari, "relevantPidsRouting"):
			self.list.append((_("Relevant PIDs Routing"), setari.relevantPidsRouting, None, slot))

	@staticmethod
	def ciplushelper():
		"""Ca in OE-Alliance: cu ajutorul CI+ extern pornit, Reset si Init sunt ale lui, nu ale omului."""
		pornit = getattr(getattr(config, "cimisc", None), "cihelperenabled", None)
		return bool(SystemInfo.get("CIPlusHelper")) and (pornit is None or bool(pornit.value))

	def textCiplus(self, slot):
		"""Randul starii CI+ al slotului."""
		if ciplusFisiereLipsa():
			return _("CI+: lipsesc certificatele aparatului")
		try:
			stare = eDVBCI_UI.getInstance().getCIPlusState(slot)
		except Exception:
			stare = 0
		if stare == 2:
			return _("CI+: autentificat, descifrare CI+")
		if stare == 1:
			return _("CI+: autentificare în curs")
		return _("CI+: certificatele sunt puse; modulul lucrează ca CI simplu")

	def updateState(self, slot=None):
		lst = self["entries"]
		index = lst.getCurrentIndex()
		self.list = []
		self.appendCommon()
		for numar in range(MAX_NUM_CI):
			state = eDVBCI_UI.getInstance().getState(numar)
			if state != -1:
				self.appendEntries(numar, state)
		lst.list = self.list
		lst.l.setList(self.list)
		if getattr(lst, "instance", None) is not None:
			lst.instance.moveSelectionTo(min(index, max(0, len(self.list) - 1)))
		self.selectionChanged()

	def ciStateChanged(self, slot):
		if self.dlg:
			self.dlg.ciStateChanged()
		else:
			state = eDVBCI_UI.getInstance().getState(slot)
			if self.state.get(slot) != state:
				#print "something happens"
				self.state[slot] = state
				self.updateState(slot)

	def dlgClosed(self, slot):
		self.dlg = None

	def okbuttonClick(self):
		cur = self["entries"].getCurrent()
		if cur and len(cur) > 2:
			action = cur[2]
			slot = cur[3]
			if action is None:
				# un rand cu alegeri (si setarile comune): OK schimba alegerea, ca dreapta
				self.keyConfigEntry(KEY_RIGHT)
			elif slot is None:
				return
			elif action == 0:		#reset
				eDVBCI_UI.getInstance().setReset(slot)
				# ca in OE-Alliance: autentificarea CI+ tinuta minte se sterge la Reset
				try:
					os.remove("/etc/ciplus/ci_auth_slot_%d.bin" % slot)
				except OSError:
					pass
			elif action == 1:		#init
				eDVBCI_UI.getInstance().setInit(slot)
			elif action == "ciplus":
				from Screens.MessageBox import MessageBox
				lipsa = ciplusFisiereLipsa()
				if lipsa:
					text = ciplusTextLipsa(lipsa)
				else:
					text = "%s\n%s" % (self.textCiplus(slot), _("Certificatele aparatului sunt în /etc/ciplus. Un modul CI+ se autentifică singur după pornire; Reset șterge autentificarea ținută minte."))
				self.session.open(MessageBox, text, MessageBox.TYPE_INFO)
			elif action == "alocare" and eDVBCI_UI.getInstance().getState(slot) != -1:
				self.session.open(CiAssignment, slot)
			elif action == "pin":
				from Screens.InputBox import InputBox
				from Components.Input import Input
				self.session.openWithCallback(lambda text, s=slot: self.pinScris(s, text), InputBox,
					title=_("Codul PIN al cardului"), text="", maxSize=False, type=Input.NUMBER)
			elif action == "pinsterge":
				config.ci[slot].static_pin.value = ""
				config.ci[slot].static_pin.save()
				self.updateState()
				self["text"].setText(_("Codul PIN păstrat a fost șters."))
			elif action == 2 and self.state[slot] == 2:
				self.dlg = self.session.openWithCallback(self.dlgClosed, MMIDialog, slot, action)

	def pinScris(self, slot, text):
		if text is None:
			return
		text = text.strip()
		if not text.isdigit() or not 4 <= len(text) <= 8:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, _("Codul PIN are 4-8 cifre."), MessageBox.TYPE_ERROR)
			return
		config.ci[slot].static_pin.value = text
		config.ci[slot].static_pin.save()
		_pinTrimisLa.pop(slot, None)
		self.updateState()
		self["text"].setText(_("Codul PIN a fost păstrat."))

	def cancel(self):
		for slot in range(MAX_NUM_CI):
			state = eDVBCI_UI.getInstance().getState(slot)
			if state != -1:
				CiHandler.unregisterCIMessageHandler(slot)
		self.close()


class CiAssignment(Screen):
	skin = """<screen name="CiAssignment" position="center,center" size="950,590" title="Common Interface">
		<widget name="entries" position="20,20" size="910,440" scrollbarMode="showOnDemand" />
		<widget name="text" position="20,465" size="910,50" font="Regular;21" />
		<widget name="key_red" position="20,540" size="210,30" font="Regular;22" foregroundColor="#ff5555" />
		<widget name="key_green" position="250,540" size="210,30" font="Regular;22" foregroundColor="#55ff55" />
		<widget name="key_yellow" position="480,540" size="210,30" font="Regular;22" foregroundColor="#ffff55" />
	</screen>"""

	def __init__(self, session, slot):
		Screen.__init__(self, session)
		from Tools import CIHelper
		self.helper = CIHelper
		self.slot = slot
		self.setTitle(_("Alocă canale modulului") + " - " + (_("Slot %d") % (slot + 1)))
		self["entries"] = ConfigList([])
		self["text"] = Label(_("Verde salvează alocările. Decodările multiple se schimbă în setările slotului."))
		self["key_red"] = Label(_("Închide"))
		self["key_green"] = Label(_("Save"))
		self["key_yellow"] = Label(_("Delete"))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.alege, "cancel": self.close, "red": self.close,
			"green": self.salveaza, "yellow": self.sterge,
			"left": lambda: self.schimba(KEY_LEFT), "right": lambda: self.schimba(KEY_RIGHT)}, -1)
		self.revizie = None
		self.neaplicata = False
		self.schimbata = False
		try:
			stare = CIHelper.citesteEditor(slot)
			self.reguli, self.revizie = stare["reguli"], stare["revizie"]
			self.neaplicata = stare["neaplicata"]
			if self.neaplicata:
				self.arataNeaplicata()
		except Exception:
			self.reguli = None
			self["text"].setText(_("Alocările CI nu se pot citi. Fișierul existent a fost păstrat."))
		if self.reguli is not None and not self.neaplicata and self.slotOprit():
			# alocarile se pot pregati si cu slotul oprit; se folosesc dupa „Pornește slotul”
			self["text"].setText(_("Slot %d oprit: modulul nu primește niciun canal.") % (slot + 1))
		self.refa()

	def slotOprit(self):
		try:
			return bool(self.helper.slotOprit(self.slot))
		except Exception as e:
			print("[Ci] starea slotului %d: %r" % (self.slot, e))
			return False

	def refa(self):
		lista = []
		if self.reguli is not None:
			lista = [(_("Adaugă canal"), ConfigNothing(), "canal"),
				(_("Adaugă furnizor"), ConfigNothing(), "furnizor"),
				(_("Adaugă CAID"), ConfigNothing(), "caid")]
			for fel, eticheta in (("servicii", _("Channel")), ("furnizori", _("Provider")), ("caid", "CAID")):
				for index, valoare in enumerate(self.reguli[fel]):
					text = "%04X" % valoare if fel == "caid" else valoare["name"]
					if fel == "furnizori":
						text += " [%08X]" % valoare["namespace"]
					lista.append((eticheta + ": " + text, ConfigNothing(), fel, index))
		self["entries"].list = lista
		self["entries"].l.setList(lista)

	def schimba(self, tasta):
		self["entries"].handleKey(tasta)

	def alege(self):
		cur = self["entries"].getCurrent()
		if not cur or len(cur) < 3:
			return
		if cur[2] == "canal":
			from Screens.ChannelSelection import SimpleChannelSelection
			self.session.openWithCallback(self.canalAles, SimpleChannelSelection, _("Adaugă canal"))
		elif cur[2] == "furnizor":
			from Screens.ChannelSelection import SimpleChannelSelection
			class AlegeFurnizor(SimpleChannelSelection):
				def __init__(self, session, title):
					SimpleChannelSelection.__init__(self, session, title)
					self.skinName = ["HdsListaCanaleSimpla", "SimpleChannelSelection"]
					self.hdsPornesteCapul()

				def layoutFinished(self):
					self.setTvMode()
					self.showProviders()

				def setModeTv(self):
					self.setTvMode()
					self.showProviders()

				def setModeRadio(self):
					self.setRadioMode()
					self.showProviders()

				def channelSelected(self):
					ref = self.getCurrentSelection()
					if ref is None or not ref.valid():
						return
					if 'provider ==' in ref.getPath():
						self.close(ref)
					else:
						SimpleChannelSelection.channelSelected(self)
			self.session.openWithCallback(self.furnizorAles, AlegeFurnizor, _("Adaugă furnizor"))
		elif cur[2] == "caid":
			from Screens.ChoiceBox import ChoiceBox
			try:
				cunoscute = self.helper.caidCunoscute(self.slot)
			except Exception as e:
				print("[Ci] CAID-urile cunoscute: %r" % (e,))
				cunoscute = []
			if not cunoscute:
				self.caidAles((None, None))
				return
			lista = [(self.textCaid(c), c["caid"]) for c in cunoscute]
			lista.append((_("Scrie CAID (hexazecimal)"), None))
			self.session.openWithCallback(self.caidAles, ChoiceBox, title=_("Adaugă CAID"), list=lista)

	@staticmethod
	def textCaid(c):
		"""Randul unui CAID in lista de ales: numarul, sistemul si furnizorii, apoi de unde se stie."""
		text = "%04X - %s" % (c["caid"], c["name"]) if c.get("name") else "%04X" % c["caid"]
		semne = [t for t, da in ((_("modulul CI"), c.get("modul")), (_("canalul pornit"), c.get("acum"))) if da]
		return text + (" (%s)" % ", ".join(semne) if semne else "")

	def canalAles(self, ref):
		if ref is None:
			return
		from ServiceReference import ServiceReference
		try:
			self.adauga("servicii", {"ref": ref.toString(), "name": ServiceReference(ref).getServiceName() or ref.toString()})
		except ValueError:
			self.eroare(_("Alege un canal DVB pentru modulul CI."))

	def furnizorAles(self, ref):
		if ref is None:
			return
		from enigma import eServiceCenter, iServiceInformation
		centru = eServiceCenter.getInstance()
		if not (ref.flags & 1):  # eServiceReference.isDirectory
			# OK pe un canal (dintr-un buchet sau din „Toate”): furnizorul acelui canal
			info = centru.info(ref)
			nume = info.getInfoString(ref, iServiceInformation.sProvider) if info is not None else ""
			if not nume or ref.type != 1:
				self.eroare(_("Canalul ales nu are furnizor. Alege un furnizor din lista Furnizori."))
				return
			try:
				self.adauga("furnizori", {"name": nume, "namespace": ref.getUnsignedData(4)})
			except ValueError:
				self.eroare(_("Lista de alocări CI este plină sau conține date nevalide."))
			return
		lista = centru.list(ref)
		if lista is None:
			return
		try:
			while True:
				canal = lista.getNext()
				if not canal.valid():
					break
				info = centru.info(canal)
				nume = info.getInfoString(canal, iServiceInformation.sProvider) if info is not None else ""
				if nume:
					self.adauga("furnizori", {"name": nume, "namespace": canal.getUnsignedData(4)})
		except ValueError:
			self.eroare(_("Lista de alocări CI este plină sau conține date nevalide."))

	def caidAles(self, alegere):
		if alegere is None:
			return
		if alegere[1] is not None:
			try:
				self.adauga("caid", alegere[1])
			except ValueError:
				self.eroare(_("Lista de alocări CI este plină sau conține date nevalide."))
		else:
			from Screens.InputBox import InputBox
			# maxSize e da/nu in Input (lungime fixa, scrii peste): „0000” = patru pozitii; cifrele si A-F de pe tastele
			# telecomenzii (2 = A B C, 3 = D E F). Cu text gol si maxSize ramanea o singura pozitie (darog69, Vu+ Duo4K, 10.11.2026).
			self.session.openWithCallback(self.caidScris, InputBox, title=_("Scrie CAID (hexazecimal)"), text="0000",
				maxSize=True, useableChars="0123456789ABCDEF")

	def caidScris(self, text):
		if text is None:
			return
		try:
			self.adauga("caid", self.helper.caidDinText(text))
		except ValueError:
			self.eroare(_("CAID nevalid. Folosește 1-4 cifre hexazecimale, de exemplu 0B00."))

	def adauga(self, fel, valoare):
		reguli = {k: list(v) for k, v in self.reguli.items()}
		reguli[fel].append(valoare)
		self.reguli = self.helper.valideazaAlocarea(reguli)
		self.marcheazaCiorna()
		self.refa()

	def sterge(self):
		cur = self["entries"].getCurrent()
		if cur and len(cur) > 3 and cur[2] in self.reguli:
			del self.reguli[cur[2]][cur[3]]
			self.marcheazaCiorna()
			self.refa()

	def marcheazaCiorna(self):
		self.schimbata = True
		self["key_green"].setText(_("Save"))
		self["text"].setText(_("Verde salvează ciorna. Închide renunță numai la modificările nesalvate."))

	def arataNeaplicata(self):
		self["key_green"].setText(_("Reîncearcă"))
		self["text"].setText(_("Salvat, neaplicat. Verde reîncearcă aplicarea. Închide păstrează salvarea."))

	def eroare(self, text):
		from Screens.MessageBox import MessageBox
		self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)

	def salveaza(self):
		if self.reguli is None:
			return
		# alocarile tin de slot: se salveaza si cu modulul in initializare sau scos (se folosesc cand modulul e gata)
		if eDVBCI_UI.getInstance().getState(self.slot) == -1:
			self.eroare(_("Modulul CI nu mai este pregătit."))
			return
		try:
			if self.neaplicata and not self.schimbata:
				self.helper.reaplicaAlocarea(self.slot, self.revizie)
			else:
				self.helper.salveazaEditor(self.slot, self.reguli, self.revizie)
		except self.helper.AlocareSchimbata:
			self["text"].setText(_("Alocările CI s-au schimbat din alt ecran. Ciorna rămâne aici. Redeschide editorul pentru datele actuale."))
			return
		except self.helper.AlocareNeaplicata as eroare:
			self.revizie = eroare.revizie
			self.neaplicata, self.schimbata = True, False
			print("[Ci] aplicare alocari: %s" % eroare)
			self.arataNeaplicata()
			return
		except Exception as eroare:
			print("[Ci] salvare alocari: %s" % eroare)
			self.eroare(_("Alocările CI nu s-au putut aplica. Verifică modulul și încearcă din nou."))
			return
		self.close()
