# Modificat de moneasoftware.com si hdsatelit.com, 2026
import os

from Tools.HardwareInfo import HardwareInfo
from Tools.BoundFunction import boundFunction

from .config import config, ConfigSubsection, ConfigSelection, ConfigFloat, \
	ConfigSatlist, ConfigYesNo, ConfigInteger, ConfigSubList, ConfigNothing, \
	ConfigSubDict, ConfigOnOff, ConfigDateTime, ConfigText

from enigma import eDVBSatelliteEquipmentControl as secClass, \
	eDVBSatelliteLNBParameters as lnbParam, \
	eDVBSatelliteDiseqcParameters as diseqcParam, \
	eDVBSatelliteSwitchParameters as switchParam, \
	eDVBSatelliteRotorParameters as rotorParam, \
	eDVBResourceManager, eDVBDB, eEnv

from time import localtime, mktime
from datetime import datetime
from Tools.BoundFunction import boundFunction

from Tools import Directories
from Tools.Unicable import readUnicableProducts


def hdsAlegeriTunerPreferat(nimmgr):
	"""Sloturile cu sisteme de receptie acceptate, fara presupuneri dupa litere."""
	choices = [("-1", _("Automată"))]
	for slot in nimmgr.nim_slots:
		if not slot.empty and slot.isSupported() and any(slot.isCompatible(t) for t in ("DVB-S", "DVB-C", "DVB-T")):
			choices.append((str(slot.slot), slot.friendly_full_description))
	return choices


def hdsConfigTunerPreferat(nimmgr):
	"""Pastreaza vizibila preferinta disparuta, fara schimbare sau scriere."""
	choices = hdsAlegeriTunerPreferat(nimmgr)
	if "usage" not in config.content.items:
		config.usage = ConfigSubsection()
	if "frontend_priority" in config.usage.content.items:
		element = config.usage.frontend_priority
		value = element.value
	else:
		element = None
		value = config.usage.content.stored_values.get("frontend_priority", "-1")
	if value not in [c[0] for c in choices]:
		choices.append((value, _("Slot %s (indisponibil)") % value))
	if element is None:
		config.usage.frontend_priority = ConfigSelection(choices=choices, default="-1")
		element = config.usage.frontend_priority
	else:
		element.setChoices(choices, default="-1")
	return element


def hdsAplicaTunerPreferat():
	"""Aplica numai alegerea confirmata; pluginurile nu schimba valoarea salvata."""
	element = config.usage.frontend_priority
	value = element.default if element.saved_value is None else element.saved_value
	manager = eDVBResourceManager.getInstance()
	setter = getattr(manager, "setPreferredTuner", None)
	if setter is not None:
		try:
			setter(int(value))
		except (TypeError, ValueError, OverflowError):
			setter(-1)


def getUnicableConfig(section):
	if section.unicable.value == "unicable_user":
		return (section.satcrformat, section.satcruser,
			section.satcrvcouser, int(section.satcrpositions.value))
	if section.unicable.value == "unicable_matrix":
		manufacturer = section.unicableMatrix[
			section.unicableMatrixManufacturer.value]
	else:
		manufacturer = section.unicableLnb[
			section.unicableLnbManufacturer.value]
	product = manufacturer.product.value
	return (manufacturer.format[product], manufacturer.scr[product],
		manufacturer.vco[product], manufacturer.positions[product][0].value)


def updateUnicablePositionChoices(section):
	positions = getUnicableConfig(section)[3]
	choices = [("0", _("Auto"))]
	for position in range(1, positions + 1):
		label = ("A (1)" if position == 1 else
			"B (2)" if position == 2 else str(position))
		choices.append((str(position), label))
	section.satcrposition.setChoices(choices, default="0")


def initUnicableUser(section):
	# Cheile si primele opt frecvente raman cele vechi.
	section.satcrformat = ConfigSelection(
		[("EN50494", _("Unicable I (EN50494)")),
		 ("EN50607", _("Unicable II (JESS, EN50607)"))], "EN50494")
	max_bands = 32 if section.satcrformat.value == "EN50607" else 8
	max_positions = 64 if max_bands == 32 else 2
	section.satcrpositions = ConfigSelection(
		[str(n) for n in range(1, max_positions + 1)], "1")
	section.satcruser = ConfigSelection(
		[(str(n), "SCR %d" % n) for n in range(1, max_bands + 1)], "1")
	section.satcrvcouser = ConfigSubList()
	frequencies = [1284, 1400, 1516, 1632, 1748, 1864, 1980, 2096]
	for frequency in frequencies + [1210] * 24:
		section.satcrvcouser.append(
			ConfigInteger(default=frequency, limits=(950, 2150)))
	section.satcrpinEnabled = ConfigYesNo(default=False)
	section.satcrpin = ConfigInteger(default=0, limits=(0, 255))
	section.satcrposition = ConfigSelection(
		[str(n) for n in range(65)], "0")

	def formatChanged(element):
		bands = 32 if element.value == "EN50607" else 8
		positions = 64 if bands == 32 else 2
		section.satcruser.setChoices(
			[(str(n), "SCR %d" % n) for n in range(1, bands + 1)], "1")
		section.satcrpositions.setChoices(
			[str(n) for n in range(1, positions + 1)], "1")
		updateUnicablePositionChoices(section)

	section.satcrformat.addNotifier(formatChanged)
	section.satcrpositions.addNotifier(
		lambda element: updateUnicablePositionChoices(section))


def fillUnicableConf(sectionDict, products, vco_null_check):
	for name in products:
		names = sorted(products[name])
		# Adaugarea JESS nu schimba produsul implicit al listei vechi.
		legacy = [n for n in names if products[name][n]["format"] == "EN50494"]
		manufacturer = ConfigSubsection()
		manufacturer.product = ConfigSelection(
			names, legacy[0] if legacy else names[0])
		for key in ("scr", "vco", "positions", "lofl", "lofh", "loft", "format"):
			setattr(manufacturer, key, ConfigSubDict())
		for product in names:
			data = products[name][product]
			choices = []
			manufacturer.vco[product] = ConfigSubList()
			for band, frequency in enumerate(data["frequencies"], 1):
				label = "SCR %d" % band
				if not frequency and vco_null_check:
					label += " " + _("not used")
				choices.append((str(band), label))
				manufacturer.vco[product].append(ConfigInteger(
					default=frequency, limits=(frequency, frequency)))
			manufacturer.scr[product] = ConfigSelection(choices, choices[0][0])
			for key, source in (("positions", "positions"), ("lofl", "lofl"),
					("lofh", "lofh"), ("loft", "threshold")):
				value = data[source]
				getattr(manufacturer, key)[product] = ConfigSubList()
				getattr(manufacturer, key)[product].append(
					ConfigInteger(default=value, limits=(value, value)))
			label = (_("Unicable II (JESS, EN50607)")
				if data["format"] == "EN50607" else _("Unicable I (EN50494)"))
			manufacturer.format[product] = ConfigSelection(
				[(data["format"], label)], data["format"])
			# Datele produsului vin numai din catalog.
			manufacturer.format[product].save_disabled = True
		sectionDict[name] = manufacturer


def setupUnicable(sec, section):
	format_element, band, frequencies, positions = getUnicableConfig(section)
	sec.setLNBSatCRformat(1 if format_element.value == "EN50607" else 0)
	sec.setLNBSatCR(band.index)
	sec.setLNBSatCRvco(frequencies[band.index].value * 1000)
	sec.setLNBSatCRpositions(positions)
	sec.setLNBSatCRposition(int(section.satcrposition.value))
	sec.setLNBSatCRpin(section.satcrpin.value
		if section.satcrpinEnabled.value else -1)
	if section.unicable.value == "unicable_user":
		sec.setLNBLOFL(section.lofl.value * 1000)
		sec.setLNBLOFH(section.lofh.value * 1000)
		sec.setLNBThreshold(section.threshold.value * 1000)
		return
	if section.unicable.value == "unicable_matrix":
		config_manufacturer = section.unicableMatrixManufacturer
		manufacturer = section.unicableMatrix[config_manufacturer.value]
	else:
		config_manufacturer = section.unicableLnbManufacturer
		manufacturer = section.unicableLnb[config_manufacturer.value]
	product = manufacturer.product.value
	sec.setLNBLOFL(manufacturer.lofl[product][0].value * 1000)
	sec.setLNBLOFH(manufacturer.lofh[product][0].value * 1000)
	sec.setLNBThreshold(manufacturer.loft[product][0].value * 1000)
	config_manufacturer.save_forced = True
	manufacturer.product.save_forced = True
	frequencies[band.index].save_forced = True


def cancelUnicable(section):
	# Formatul si numarul de pozitii refac alegerile inaintea valorilor.
	for name in ("satcrformat", "satcrpositions", "satcrposition",
			"satcruser", "satcrpinEnabled", "satcrpin"):
		getattr(section, name).cancel()
	updateUnicablePositionChoices(section)
	for frequency in section.satcrvcouser:
		frequency.cancel()


def getConfigSatlist(orbpos, satlist):
	default_orbpos = None
	for x in satlist:
		if x[0] == orbpos:
			default_orbpos = orbpos
			break
	return ConfigSatlist(satlist, default_orbpos)

def tryOpen(filename):
	try:
		procFile = open(filename)
	except IOError:
		return None
	return procFile


def inputPowerSlotForNim(nim):
	"""Curentul LNB este citit de nucleu dupa numarul locului tunerului.
	Tunerele imaginii nu au o remapare a locurilor pentru aceasta masurare.
	"""
	return int(nim)


def canMeasureInputPowerForNim(slotid, nimmgr=None):
	"""Masurarea curentului motorului (rotirea vazuta dupa curentul LNB) se foloseste numai pe aparatele care il pot citi
	pentru tunerul acesta. Idee din OE-Alliance enigma2 (NimManager.canMeasureInputPowerForNim, GPL-2.0), cod nou: aceleasi
	surse ca eDVBFrontend::readInputpower (lib/dvb/frontend.cpp): /proc/stb/frontend/N/lnb_sense, /proc/stb/fp/lnb_senseN
	sau procesorul din fata /dev/dbox/fp0 (cand nucleul il poate citi). Fara ele readInputpower da -1, pornirea motorului nu
	se vede, iar secventa sare peste asteptare: primul acord pleaca cu antena inca in drum si cade fara semnal (Octagon
	SF8008, 14.11.2026: 19,2E -> 39,0E fara semnal dupa 7,7 s). Implicitul lui powerMeasurement e Da si ramane nescris
	cand motorul e pus din web, din asistent sau din setarile altei imagini, deci poarta sta aici, nu numai in Satconfig."""
	slot = inputPowerSlotForNim(slotid)
	for cale in ("/proc/stb/frontend/%d/lnb_sense" % slot, "/proc/stb/fp/lnb_sense%d" % slot):
		if os.path.exists(cale):
			return True
	if os.path.exists("/dev/dbox/fp0"):
		try:
			return bool(eDVBResourceManager.getInstance().canMeasureFrontendInputPower())
		except Exception:
			return False
	return False

class SecConfigure:
	def getConfiguredSats(self):
		return self.configuredSatellites

	def addSatellite(self, sec, orbpos):
		sec.addSatellite(orbpos)
		self.configuredSatellites.add(orbpos)

	def hdsLocStabilitCitit(self):
		"""locul antenei (Components/HdsLocul.py); daca nu se poate citi, e socotit nestabilit: motorul USALS nu porneste"""
		try:
			from Components import HdsLocul
			return HdsLocul.stabilit()
		except Exception as e:
			print("[NimManager] locul antenei nu se poate citi: %r" % (e,))
			return False

	def hdsFaraLoc(self, slotid, orbitale):
		"""Satelitii care cer calculul USALS, cu locul nestabilit: nu ajung la nucleu (niciun acord nu roteste antena dupa
		un loc inventat), dar raman in satelitii configurati, altfel Setari tuner ar propune stergerea canalelor lor."""
		for orbital in orbitale:
			self.configuredSatellites.add(orbital)
		if slotid not in self.hdsFaraLocSloturi:
			self.hdsFaraLocSloturi.append(slotid)
			print("[NimManager] locul antenei nu e stabilit: satelitii USALS ai tunerului %s nu se dau nucleului (antena nu se roteste)" % chr(ord("A") + slotid))

	def hdsLocCitit(self):
		"""(lat_mii, lon_mii) ale locului antenei (Components/HdsLocul.py) cand e stabilit, altfel None"""
		try:
			from Components import HdsLocul
			return HdsLocul.locul() if HdsLocul.stabilit() else None
		except Exception as e:
			print("[NimManager] locul antenei nu se poate citi: %r" % (e,))
			return None

	def hdsVizibil(self, orbital):
		"""False numai cand locul e stabilit si satelitul e sub orizont din el (Components/HdsLocul.vizibilDinLoc, acelasi
		calcul ca nucleul): spre el comanda USALS ar trimite antena spre capatul cursei (asistenta 681415, locul scris cu
		emisferele schimbate: "se misca mereu", fara semnal)"""
		if self.hdsLoc is None:
			return True
		try:
			from Components import HdsLocul
			return HdsLocul.vizibilDinLoc(orbital, self.hdsLoc)
		except Exception as e:
			print("[NimManager] vizibilitatea satelitului %s: %r" % (orbital, e))
			return True

	def hdsSubOrizont(self, slotid, orbitale):
		"""Satelitii USALS sub orizont din locul stabilit: nu ajung la nucleu (nicio comanda spre ei), dar raman in satelitii
		configurati (canalele lor nu se propun spre stergere); zap-ul pe ei spune de ce (Components/HdsEcranNegru.py)."""
		for orbital in orbitale:
			self.configuredSatellites.add(orbital)
		lista = self.hdsSubOrizontSloturi.setdefault(slotid, [])
		lista.extend(o for o in orbitale if o not in lista)

	def addLNBSimple(self, sec, slotid, diseqcmode, toneburstmode = diseqcParam.NO, diseqcpos = diseqcParam.SENDNO, orbpos = 0, longitude = 0, latitude = 0, loDirection = 0, laDirection = 0, turningSpeed = rotorParam.FAST, useInputPower=True, inputPowerDelta=50, fastDiSEqC = False, setVoltageTone = True, diseqc13V = False):
		if orbpos is None or orbpos == 3601:
			return
		#simple defaults
		sec.addLNB()
		tunermask = 1 << slotid
		if slotid in self.equal:
			for slot in self.equal[slotid]:
				tunermask |= (1 << slot)
		if slotid in self.linked:
			for slot in self.linked[slotid]:
				tunermask |= (1 << slot)
		sec.setLNBSatCR(-1)
		sec.setLNBNum(1)
		sec.setLNBLOFL(9750000)
		sec.setLNBLOFH(10600000)
		sec.setLNBThreshold(11700000)
		sec.setLNBIncreasedVoltage(lnbParam.OFF)
		sec.setRepeats(0)
		sec.setFastDiSEqC(fastDiSEqC)
		sec.setSeqRepeat(0)
		sec.setCommandOrder(0)

		#user values
		sec.setDiSEqCMode(diseqcmode)
		sec.setToneburst(toneburstmode)
		sec.setCommittedCommand(diseqcpos)
		sec.setUncommittedCommand(0) # SENDNO
		#print "set orbpos to:" + str(orbpos)

		if 0 <= diseqcmode < 3:
			self.addSatellite(sec, orbpos)
			if setVoltageTone:
				if diseqc13V:
					sec.setVoltageMode(switchParam.HV_13)
				else:
					sec.setVoltageMode(switchParam.HV)
				sec.setToneMode(switchParam.HILO)
			else:
				sec.setVoltageMode(switchParam._14V)
				sec.setToneMode(switchParam.OFF)
		elif (diseqcmode == 3): # diseqc 1.2
			if slotid in self.satposdepends:
				for slot in self.satposdepends[slotid]:
					tunermask |= (1 << slot)
			sec.setLatitude(latitude)
			sec.setLaDirection(laDirection)
			sec.setLongitude(longitude)
			sec.setLoDirection(loDirection)
			sec.setUseInputpower(useInputPower)
			sec.setInputpowerDelta(inputPowerDelta)
			sec.setRotorTurningSpeed(turningSpeed)

			for x in self.NimManager.satList:
				if not self.hdsVizibil(int(x[0])):
					# sub orizont din locul antenei: fara comanda USALS spre el (hdsSubOrizont); continue inaintea setarilor
					# de mai jos, care se aplica satelitului pus ultimul in nucleu
					self.hdsSubOrizont(slotid, [int(x[0])])
					continue
				print("Add sat " + str(x[0]))
				self.addSatellite(sec, int(x[0]))
				if diseqc13V:
					sec.setVoltageMode(switchParam.HV_13)
				else:
					sec.setVoltageMode(switchParam.HV)
				sec.setToneMode(switchParam.HILO)
				sec.setRotorPosNum(0) # USALS
		
		sec.setLNBSlotMask(tunermask)

	def setSatposDepends(self, sec, nim1, nim2):
		print("tuner", nim1, "depends on satpos of", nim2)
		sec.setTunerDepends(nim1, nim2)
		
	def linkInternally(self, slotid):
		nim = self.NimManager.getNim(slotid)
		if nim.internallyConnectableTo is not None:
			nim.setInternalLink()

	def linkNIMs(self, sec, nim1, nim2):
		print("link tuner", nim1, "to tuner", nim2)
		if nim2 == (nim1 - 1):
			self.linkInternally(nim1)
		legatura = sec.setTunerLinked(nim1, nim2)
		if legatura in (0, None):
			from Components.HdsFbc import ruteaza
			try:
				ruteaza(self.NimManager.nim_slots, nim1, self.getRoot(nim1, nim2))
			except (ValueError, KeyError, IndexError) as eroare:
				print("[HdsFbc] legatura %d spre %d nu are radacina valida: %s" %
					(nim1, nim2, eroare))
		
	def getRoot(self, slotid, connto):
		visited = []
		while (self.NimManager.getNimConfig(connto).configMode.value in ("satposdepends", "equal", "loopthrough")):
			connto = int(self.NimManager.getNimConfig(connto).connectedTo.value)
			if connto in visited: # prevent endless loop
				return slotid
			visited.append(connto)
		return connto

	def update(self):
		sec = secClass.getInstance()
		self.configuredSatellites = set()
		self.hdsLocStabilit = self.hdsLocStabilitCitit()
		self.hdsFaraLocSloturi = []
		self.hdsLoc = self.hdsLocCitit() if self.hdsLocStabilit else None
		self.hdsSubOrizontSloturi = {}
		for slotid in self.NimManager.getNimListOfType("DVB-S"):
			if self.NimManager.nimInternallyConnectableTo(slotid) is not None:
				self.NimManager.nimRemoveInternalLink(slotid)
		# HDSatelit: clear() uita si pozitia antenei cu motor; se da inapoi la sfarsit, daca setarile motorului sunt aceleasi
		from Components import HdsMotorPozitie
		hds_perechi = HdsMotorPozitie.inainteDeReconfigurare(self.NimManager.getNimListOfType("DVB-S"))
		sec.clear() ## this do unlinking NIMs too !!
		print("sec config cleared")

		self.linked = { }
		self.satposdepends = { }
		self.equal = { }

		nim_slots = self.NimManager.nim_slots
		from Components.HdsFbc import ruteazaIndependente
		ruteazaIndependente(nim_slots)

		used_nim_slots = [ ]

		for slot in nim_slots:
			if slot.type is not None:
				used_nim_slots.append((slot.slot, slot.description, slot.config.configMode.value != "nothing" and True or False, slot.isCompatible("DVB-S2"), slot.frontend_id is None and -1 or slot.frontend_id))
		try:
			eDVBResourceManager.getInstance().setFrontendSlotInformations(used_nim_slots)
		except Exception as e:
			print("[NimManager] %s" % e)
		hdsTrimiteTipuriAlese(nim_slots)

		for slot in nim_slots:
			x = slot.slot
			nim = slot.config
			if slot.isCompatible("DVB-S"):
				# save what nim we link to/are equal to/satposdepends to.
				# this is stored in the *value* (not index!) of the config list
				if nim.configMode.value == "equal":
					connto = self.getRoot(x, int(nim.connectedTo.value))
					if connto not in self.equal:
						self.equal[connto] = []
					self.equal[connto].append(x)
				elif nim.configMode.value == "loopthrough":
					self.linkNIMs(sec, x, int(nim.connectedTo.value))
					connto = self.getRoot(x, int(nim.connectedTo.value))
					if connto not in self.linked:
						self.linked[connto] = []
					self.linked[connto].append(x)
				elif nim.configMode.value == "satposdepends":
					self.setSatposDepends(sec, x, int(nim.connectedTo.value))
					connto = self.getRoot(x, int(nim.connectedTo.value))
					if connto not in self.satposdepends:
						self.satposdepends[connto] = []
					self.satposdepends[connto].append(x)

		for slot in nim_slots:
			x = slot.slot
			nim = slot.config
			hw = HardwareInfo()
			if slot.isCompatible("DVB-S"):
				print("slot: " + str(x) + " configmode: " + str(nim.configMode.value))
				if slot.isFBCLink() and nim.configMode.value == "advanced" and hdsEroareFbc(self.NimManager, x):
					continue
				if nim.configMode.value in ( "loopthrough", "satposdepends", "nothing" ):
					pass
				else:
					sec.setSlotNotLinked(x)
					if nim.configMode.value == "equal":
						pass
					elif nim.configMode.value == "simple":		#simple config
						print("diseqcmode: ", nim.diseqcMode.value)
						if nim.diseqcMode.value == "single":			#single
							if nim.simpleSingleSendDiSEqC.value:
								self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcA.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.AA, diseqc13V = nim.diseqc13V.value)
							else:
								self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcA.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.NONE, diseqcpos = diseqcParam.SENDNO, diseqc13V = nim.diseqc13V.value)
						elif nim.diseqcMode.value == "toneburst_a_b":		#Toneburst A/B
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcA.orbital_position, toneburstmode = diseqcParam.A, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.SENDNO, diseqc13V = nim.diseqc13V.value)
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcB.orbital_position, toneburstmode = diseqcParam.B, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.SENDNO, diseqc13V = nim.diseqc13V.value)
						elif nim.diseqcMode.value == "diseqc_a_b":		#DiSEqC A/B
							fastDiSEqC = nim.simpleDiSEqCOnlyOnSatChange.value
							setVoltageTone = nim.simpleDiSEqCSetVoltageTone.value
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcA.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.AA, fastDiSEqC = fastDiSEqC, setVoltageTone = setVoltageTone, diseqc13V = nim.diseqc13V.value)
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcB.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.AB, fastDiSEqC = fastDiSEqC, setVoltageTone = setVoltageTone, diseqc13V = nim.diseqc13V.value)
						elif nim.diseqcMode.value == "diseqc_a_b_c_d":		#DiSEqC A/B/C/D
							fastDiSEqC = nim.simpleDiSEqCOnlyOnSatChange.value
							setVoltageTone = nim.simpleDiSEqCSetVoltageTone.value
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcA.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.AA, fastDiSEqC = fastDiSEqC, setVoltageTone = setVoltageTone, diseqc13V = nim.diseqc13V.value)
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcB.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.AB, fastDiSEqC = fastDiSEqC, setVoltageTone = setVoltageTone, diseqc13V = nim.diseqc13V.value)
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcC.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.BA, fastDiSEqC = fastDiSEqC, setVoltageTone = setVoltageTone, diseqc13V = nim.diseqc13V.value)
							self.addLNBSimple(sec, slotid = x, orbpos = nim.diseqcD.orbital_position, toneburstmode = diseqcParam.NO, diseqcmode = diseqcParam.V1_0, diseqcpos = diseqcParam.BB, fastDiSEqC = fastDiSEqC, setVoltageTone = setVoltageTone, diseqc13V = nim.diseqc13V.value)
						elif nim.diseqcMode.value == "positioner":		#Positioner
							if not self.hdsLocStabilit:
								# locul antenei nestabilit (Components/HdsLocul.py): modul simplu cu motor e numai USALS
								self.hdsFaraLoc(x, [int(s[0]) for s in self.NimManager.satList])
								continue
							if nim.latitudeOrientation.value == "north":
								laValue = rotorParam.NORTH
							else:
								laValue = rotorParam.SOUTH
							if nim.longitudeOrientation.value == "east":
								loValue = rotorParam.EAST
							else:
								loValue = rotorParam.WEST
							inputPowerDelta=nim.powerThreshold.value
							useInputPower=False
							turning_speed=0
							if nim.powerMeasurement.value and canMeasureInputPowerForNim(x, self.NimManager):
								useInputPower=True
								turn_speed_dict = { "fast": rotorParam.FAST, "slow": rotorParam.SLOW }
								if nim.turningSpeed.value in turn_speed_dict:
									turning_speed = turn_speed_dict[nim.turningSpeed.value]
								else:
									beg_time = localtime(nim.fastTurningBegin.value)
									end_time = localtime(nim.fastTurningEnd.value)
									turning_speed = ((beg_time.tm_hour+1) * 60 + beg_time.tm_min + 1) << 16
									turning_speed |= (end_time.tm_hour+1) * 60 + end_time.tm_min + 1
							self.addLNBSimple(sec, slotid = x, diseqcmode = 3,
								longitude = nim.longitude.float,
								loDirection = loValue,
								latitude = nim.latitude.float,
								laDirection = laValue,
								turningSpeed = turning_speed,
								useInputPower = useInputPower,
								inputPowerDelta = inputPowerDelta,
								diseqc13V = nim.diseqc13V.value)
					elif nim.configMode.value == "advanced": #advanced config
						self.updateAdvanced(sec, x)
		HdsMotorPozitie.dupaReconfigurare(hds_perechi)
		# HDSatelit: setarile tunerelor in hds-tuner.log (Components/HdsJurnalTuner.py), numai cand s-au schimbat
		try:
			from Components import HdsJurnalTuner
			HdsJurnalTuner.configurare(self.NimManager)
		except Exception:
			pass
		for slotid, orbitale in sorted(self.hdsSubOrizontSloturi.items()):
			print("[NimManager] tunerul %s: %d sateliti USALS sub orizont din locul antenei nu se dau nucleului (%s)" % (
				chr(ord("A") + slotid), len(orbitale), " ".join(str(o) for o in sorted(orbitale)[:40])))
		print("sec config completed")

	def updateAdvanced(self, sec, slotid):
		try:
			if config.Nims[slotid].advanced.unicableconnected is not None:
				if config.Nims[slotid].advanced.unicableconnected.value == True:
					config.Nims[slotid].advanced.unicableconnectedTo.save_forced = True
					self.linkNIMs(sec, slotid, int(config.Nims[slotid].advanced.unicableconnectedTo.value))
					connto = self.getRoot(slotid, int(config.Nims[slotid].advanced.unicableconnectedTo.value))
					if connto not in self.linked:
						self.linked[connto] = []
					self.linked[connto].append(slotid)
				else:
					config.Nims[slotid].advanced.unicableconnectedTo.save_forced = False
		except:
			pass

		lnbSat = {}
		for x in range(1,37):
			lnbSat[x] = []

		#wildcard for all satellites ( for rotor )
		for x in range(3601, 3605):
			lnb = int(config.Nims[slotid].advanced.sat[x].lnb.value)
			if lnb != 0:
				for x in self.NimManager.satList:
					print("add", x[0], "to", lnb)
					lnbSat[lnb].append(x[0])

		for x in self.NimManager.satList:
			if x[0] not in config.Nims[slotid].advanced.sat:
				# satelit nou in satellites.xml fara intrare in setarile tunerului (reincarcare de pe PC): sarit, nu KeyError
				print("[NimManager] tunerul %s: pozitia %d nu are setari avansate, sarita" % (chr(ord("A") + slotid), x[0]))
				continue
			lnb = int(config.Nims[slotid].advanced.sat[x[0]].lnb.value)
			if lnb != 0:
				print("add", x[0], "to", lnb)
				lnbSat[lnb].append(x[0])

		for x in range(1,37):
			if len(lnbSat[x]) > 0:
				currLnb = config.Nims[slotid].advanced.lnb[x]
				sec.addLNB()

				if x < 33:
					sec.setLNBNum(x)

				tunermask = 1 << slotid
				if slotid in self.equal:
					for slot in self.equal[slotid]:
						tunermask |= (1 << slot)
				if slotid in self.linked:
					for slot in self.linked[slotid]:
						tunermask |= (1 << slot)

				if currLnb.lof.value != "unicable":
					sec.setLNBSatCR(-1)

				if currLnb.lof.value == "universal_lnb":
					sec.setLNBLOFL(9750000)
					sec.setLNBLOFH(10600000)
					sec.setLNBThreshold(11700000)
				elif currLnb.lof.value == "unicable":
					setupUnicable(sec, currLnb)
				elif currLnb.lof.value == "c_band":
					sec.setLNBLOFL(5150000)
					sec.setLNBLOFH(5150000)
					sec.setLNBThreshold(5150000)
				elif currLnb.lof.value == "c_band_5750":
					sec.setLNBLOFL(5750000)
					sec.setLNBLOFH(5750000)
					sec.setLNBThreshold(5750000)
				elif currLnb.lof.value == "user_defined":
					sec.setLNBLOFL(currLnb.lofl.value * 1000)
					sec.setLNBLOFH(currLnb.lofh.value * 1000)
					sec.setLNBThreshold(currLnb.threshold.value * 1000)

#				if currLnb.output_12v.value == "0V":
#					pass # nyi in drivers
#				elif currLnb.output_12v.value == "12V":
#					pass # nyi in drivers

				if currLnb.increased_voltage.value:
					sec.setLNBIncreasedVoltage(lnbParam.ON)
				else:
					sec.setLNBIncreasedVoltage(lnbParam.OFF)

				dm = currLnb.diseqcMode.value
				if dm == "none":
					sec.setDiSEqCMode(diseqcParam.NONE)
				elif dm == "1_0":
					sec.setDiSEqCMode(diseqcParam.V1_0)
				elif dm == "1_1":
					sec.setDiSEqCMode(diseqcParam.V1_1)
				elif dm == "1_2":
					sec.setDiSEqCMode(diseqcParam.V1_2)

					if slotid in self.satposdepends:
						for slot in self.satposdepends[slotid]:
							tunermask |= (1 << slot)

				if dm != "none":
					if currLnb.toneburst.value == "none":
						sec.setToneburst(diseqcParam.NO)
					elif currLnb.toneburst.value == "A":
						sec.setToneburst(diseqcParam.A)
					elif currLnb.toneburst.value == "B":
						sec.setToneburst(diseqcParam.B)

					# Committed Diseqc Command
					cdc = currLnb.commitedDiseqcCommand.value

					c = { "none": diseqcParam.SENDNO,
						"AA": diseqcParam.AA,
						"AB": diseqcParam.AB,
						"BA": diseqcParam.BA,
						"BB": diseqcParam.BB }

					if cdc in c:
						sec.setCommittedCommand(c[cdc])
					else:
						sec.setCommittedCommand(int(cdc))

					sec.setFastDiSEqC(currLnb.fastDiseqc.value)

					sec.setSeqRepeat(currLnb.sequenceRepeat.value)

					if currLnb.diseqcMode.value == "1_0":
						currCO = currLnb.commandOrder1_0.value
						sec.setRepeats(0)
					else:
						currCO = currLnb.commandOrder.value

						udc = int(currLnb.uncommittedDiseqcCommand.value)
						if udc > 0:
							sec.setUncommittedCommand(0xF0|(udc-1))
						else:
							sec.setUncommittedCommand(0) # SENDNO

						sec.setRepeats({"none": 0, "one": 1, "two": 2, "three": 3}[currLnb.diseqcRepeats.value])

					setCommandOrder = False

					# 0 "committed, toneburst",
					# 1 "toneburst, committed",
					# 2 "committed, uncommitted, toneburst",
					# 3 "toneburst, committed, uncommitted",
					# 4 "uncommitted, committed, toneburst"
					# 5 "toneburst, uncommitted, commmitted"
					order_map = {"ct": 0, "tc": 1, "cut": 2, "tcu": 3, "uct": 4, "tuc": 5}
					sec.setCommandOrder(order_map[currCO])

				if dm == "1_2":
					latitude = currLnb.latitude.float
					sec.setLatitude(latitude)
					longitude = currLnb.longitude.float
					sec.setLongitude(longitude)
					if currLnb.latitudeOrientation.value == "north":
						sec.setLaDirection(rotorParam.NORTH)
					else:
						sec.setLaDirection(rotorParam.SOUTH)
					if currLnb.longitudeOrientation.value == "east":
						sec.setLoDirection(rotorParam.EAST)
					else:
						sec.setLoDirection(rotorParam.WEST)

					if currLnb.powerMeasurement.value and canMeasureInputPowerForNim(slotid, self.NimManager):
						sec.setUseInputpower(True)
						sec.setInputpowerDelta(currLnb.powerThreshold.value)
						turn_speed_dict = { "fast": rotorParam.FAST, "slow": rotorParam.SLOW }
						if currLnb.turningSpeed.value in turn_speed_dict:
							turning_speed = turn_speed_dict[currLnb.turningSpeed.value]
						else:
							beg_time = localtime(currLnb.fastTurningBegin.value)
							end_time = localtime(currLnb.fastTurningEnd.value)
							turning_speed = ((beg_time.tm_hour + 1) * 60 + beg_time.tm_min + 1) << 16
							turning_speed |= (end_time.tm_hour + 1) * 60 + end_time.tm_min + 1
						sec.setRotorTurningSpeed(turning_speed)
					else:
						sec.setUseInputpower(False)

				sec.setLNBSlotMask(tunermask)

				sec.setLNBPrio(int(currLnb.prio.value))

				# finally add the orbital positions
				for y in lnbSat[x]:
					if x > 32:
						satpos = x > 32 and (3604-(36 - x)) or y
					else:
						satpos = y
					currSat = config.Nims[slotid].advanced.sat[satpos]
					if dm == "1_2" and not self.hdsLocStabilit and (currSat.usals.value or x >= 34):
						# calculul USALS cu locul nestabilit (Components/HdsLocul.py; aceeasi regula ca setRotorPosNum de mai
						# jos: LNB 33 fara usals si satelitii fara usals merg pe pozitia memorata). continue inaintea
						# setarilor de mai jos: ele se aplica satelitului pus ultimul in nucleu (sec.cpp, m_curSat), adica altuia
						self.hdsFaraLoc(slotid, [y])
						continue
					if dm == "1_2" and (currSat.usals.value or x >= 34) and not self.hdsVizibil(y):
						# sub orizont din locul stabilit: fara comanda USALS spre el (hdsSubOrizont), ca mai sus
						self.hdsSubOrizont(slotid, [y])
						continue
					self.addSatellite(sec, y)
					if currSat.voltage.value == "polarization":
						if config.Nims[slotid].diseqc13V.value:
							sec.setVoltageMode(switchParam.HV_13)
						else:
							sec.setVoltageMode(switchParam.HV)
					elif currSat.voltage.value == "13V":
						sec.setVoltageMode(switchParam._14V)
					elif currSat.voltage.value == "18V":
						sec.setVoltageMode(switchParam._18V)

					if currSat.tonemode.value == "band":
						sec.setToneMode(switchParam.HILO)
					elif currSat.tonemode.value == "on":
						sec.setToneMode(switchParam.ON)
					elif currSat.tonemode.value == "off":
						sec.setToneMode(switchParam.OFF)
						
					if not currSat.usals.value and x < 34:
						sec.setRotorPosNum(currSat.rotorposition.value)
					else:
						sec.setRotorPosNum(0) #USALS

	def __init__(self, nimmgr):
		self.NimManager = nimmgr
		self.configuredSatellites = set()
		self.update()

# tipuri raportate de nucleele noi, echivalate cu cele pe care le cunoaste motorul
NIM_TYPE_ALIASES = {
	"DVB-S2X": "DVB-S2",
	"DVB-T2": "DVB-T",
	"DVB-C/T": "DVB-C/T",
	"DVB-C/T2": "DVB-C/T",
	"DVB-C,T/T2": "DVB-C/T",
	"DVB-C,T": "DVB-C/T",
}

def normalizeNimType(type):
	return NIM_TYPE_ALIASES.get(type, type)

# HDSatelit (puntea vtuner, lib/dvb/hdsvtuner.cpp): tunerele DVB pe USB legate la pornirea interfetei, un rand pe tuner:
# "<frontend virtual pe adapter0>\t<frontend USB>\t<nume>\t<sisteme>". Lipseste cand nu e niciun tuner USB in mufa.
TUNERE_USB = "/tmp/hds_tunere_usb"

def tunereUsb(cale=None):
	"""{frontend virtual: (nume, [sisteme])} pentru tunerele USB legate de punte; {} fara ele sau la o lista stricata.
	Numele din /proc/bus/nim_sockets al unui frontend virtual il scrie driverul vtuner al placii (difera de la placa la
	placa, uneori numai "VTUNER"), deci numele adevarat al stickului si sistemele lui se iau de aici."""
	rezultat = {}
	try:
		with open(cale or TUNERE_USB) as f:
			for rand in f:
				campuri = rand.rstrip("\n").split("\t")
				if len(campuri) < 4:
					continue
				try:
					fe = int(campuri[0])
				except ValueError:
					continue
				sisteme = [x.strip() for x in campuri[3].split(",") if x.strip()]
				rezultat[fe] = (campuri[2].strip(), sisteme)
	except (IOError, OSError):
		pass
	return rezultat

def numeTunerUsb(nume, tip, sisteme):
	"""(numele aratat in Setari tunere, tipul) pentru un tuner USB: numele stickului cu „(USB)”; un stick cu cablu si
	terestru (de pilda Vu+ Turbo, DVB-T/C) devine combinat, „DVB-C/T”, ca tunerele combinate ale placii."""
	nume = (nume or "").strip()
	if not nume or nume.lower() == "usb frontend":  # stickul nu-si spune numele (hdsvtuner.cpp pune "USB frontend")
		nume = "USB"
	elif not nume.upper().endswith("(USB)"):
		nume = "%s (USB)" % nume
	cablu = "DVB-C" in sisteme
	terestru = "DVB-T" in sisteme or "DVB-T2" in sisteme
	if cablu and terestru and tip in ("DVB-C", "DVB-T"):
		tip = "DVB-C/T"
	return nume, tip

def hdsLegaturaImplicita(nimmgr, slot):
	"""Implicitul lui connectedTo ("equal to", "loopthrough to", "second cable of") pentru tunerul `slot`: la un tuner FBC,
	prima radacina a NIM-ului lui (acelasi fbc_set_id). Vu+ Ultimo 4K cu doua NIM-uri FBC de cate 8: J..P primesc I, nu A,
	care e pe alt NIM si alt cablu (legatura interna FBC e numai in acelasi NIM). Prima radacina insasi, tunerele obisnuite
	si cele FBC fara fbc_set_id raman cu None: primul tuner din lista, ca pana acum (pe primul NIM acela e chiar A)."""
	try:
		if not slot.isFBCTuner() or slot.fbc_set_id is None:
			return None
		radacini = sorted(t.slot for t in nimmgr.nim_slots
			if t.isFBCRoot() and t.fbc_set_id == slot.fbc_set_id and t.isCompatible("DVB-S"))
		if radacini and radacini[0] != slot.slot:
			return str(radacini[0])
	except Exception as e:
		print("[NimManager] legatura implicita %s: %s" % (getattr(slot, "slot", "?"), e))
	return None


def hdsTinteleFbc(manager, slotid):
	"""Physical inputs in the same FBC group, identified by driver capabilities."""
	slot = manager.nim_slots[slotid]
	if not slot.isFBCLink():
		return []
	return [n.slot for n in manager.nim_slots if n.isFBCRoot()
		and n.fbc_set_id == slot.fbc_set_id and n.isCompatible("DVB-S")
		and (slot.fbc_set_id is not None or (n.description or "").strip().lower() == (slot.description or "").strip().lower())]


def hdsAlegeriModTuner(manager, slotid):
	"""Shared TV/web choices. Advanced on a linked demodulator requires SCR."""
	slot = manager.nim_slots[slotid]
	if slot.isFBCLink():
		choices = {"nothing": _("not configured"), "advanced": _("Avansat (numai Unicable / JESS)")}
		if hdsTinteleFbc(manager, slotid):
			choices["equal"] = _("equal to")
			choices["loopthrough"] = _("loopthrough to")
		return choices
	choices = {"nothing": _("not configured"), "simple": _("simple"), "advanced": _("advanced")}
	for mode, targets, text in (("equal", manager.canEqualTo, _("equal to")),
			("satposdepends", manager.canDependOn, _("second cable of motorized LNB")),
			("loopthrough", manager.canConnectTo, _("loopthrough to"))):
		if targets(slotid):
			choices[mode] = text
	return choices


def hdsPastreazaAlegerea(element, choices):
	"""Keep a legacy invalid value visible without changing or saving it."""
	choices = dict(choices)
	if element.value not in choices:
		choices[element.value] = _("Configurație incompatibilă: %s") % element.value
	element.setChoices(choices, default=element.default)
	element._descr = None


def hdsEroareFbc(manager, slotid):
	"""Validate active settings only; never migrate the user's stored values."""
	slot = manager.nim_slots[slotid]
	if not slot.isFBCLink() or not slot.isCompatible("DVB-S"):
		return ""
	cfg = slot.config
	mode = cfg.configMode.value
	if mode == "nothing":
		return ""
	if mode in ("equal", "loopthrough"):
		if cfg.connectedTo.value in [str(n) for n in hdsTinteleFbc(manager, slotid)]:
			return ""
		return _("Alege o intrare cu mufă din același grup FBC.")
	if mode != "advanced":
		return _("Acest demodulator FBC nu are mufă. Leagă-l la o intrare cu mufă sau folosește modul avansat cu Unicable / JESS.")
	try:
		active = {sat[0] for sat in manager.satList} | set(range(3601, 3605))
		used = {int(s.lnb.value) for pos, s in cfg.advanced.sat.items() if pos in active and int(s.lnb.value)}
		if not used or any(cfg.advanced.lnb[n].lof.value != "unicable" for n in used):
			return _("Pe un demodulator FBC fără mufă, modul avansat cere Unicable / JESS la fiecare LNB folosit.")
		if any(cfg.advanced.lnb[n].diseqcMode.value == "1_2" for n in used):
			return _("Motorul se configurează pe intrarea FBC cu mufă. Demodulatorul legat nu trimite comenzi de motor.")
		if (getattr(cfg.advanced, "unicableconnected", None) is not None
				and cfg.advanced.unicableconnected.value
				and cfg.advanced.unicableconnectedTo.value not in [str(n) for n in hdsTinteleFbc(manager, slotid)]):
			return _("Alege o intrare cu mufă din același grup FBC.")
	except (AttributeError, KeyError, TypeError, ValueError):
		return _("Configurația avansată FBC este incompletă. Alege LNB-ul Unicable / JESS.")
	return ""


HDS_MODURI_SATELIT = ("simple", "advanced", "equal", "satposdepends", "loopthrough")  # configMode de satelit
HDS_MASCA_TIP = {"DVB-S": 1, "DVB-S2": 1, "DVB-C": 2, "DVB-T": 4, "DVB-C/T": 6}  # 1 << feSatellite/feCable/feTerrestrial


def hdsTrimiteTipuriAlese(nim_slots):
	"""DMV6: the C++ side only knows what the kernel can do (DTV_ENUM_DELSYS), so on a multi-system tuner without
	/proc/stb/frontend/N/mode (Dreambox DM900/DM920/DM7080, Si2169C/D) a terrestrial channel went to the first tuner, even
	the one set up for satellite. Tell it the type of each such tuner (the person's choice or the driver type, the same
	one the tuner setup and the scan use); every other tuner gets -1, the old choice. When no such tuner is set for cable
	or terrestrial, every tuner gets -1 too: an untouched receiver keeps playing cable/terrestrial channels as before.
	The enigma.py of an older image (a test package replaces only the binary) lacks the method: then it is taken from the
	binary module itself; an older binary without it is left as it was."""
	manager = eDVBResourceManager.getInstance()
	trimite = getattr(manager, "setHdsTipuriAlese", None)
	if trimite is None:
		try:
			import _enigma
			for nume in ("eDVBResourceManager_setHdsTipuriAlese", "eDVBResourceManagerPtr_setHdsTipuriAlese"):
				functie = getattr(_enigma, nume, None)
				if functie is not None:
					trimite = lambda slot, masca, _f=functie: _f(manager, slot, masca)
					break
		except Exception as e:
			print("[NimManager] tipurile tunerelor: %r" % (e,))
	if trimite is None:
		return
	masti = {}
	for slot in nim_slots:
		masca = -1
		try:
			if getattr(slot.config.multiType, "hds_dinamic", False):
				masca = HDS_MASCA_TIP.get(slot.getType(), -1)
		except (AttributeError, KeyError, IndexError):
			pass
		masti[slot.slot] = masca
	if not any(m > 0 and m & 6 for m in masti.values()):
		masti = dict((slot, -1) for slot in masti)
	print("[NimManager] tipurile tunerelor: %s" % masti)
	for slot, masca in sorted(masti.items()):
		try:
			trimite(slot, masca)
		except Exception as e:
			print("[NimManager] tipurile tunerului %s: %r" % (slot, e))


def hdsTipSalvatDeOm(manager, slotid):
	"""Called only by an explicit save (TV Satconfig.keySave, web tuner save), never by a change or a cancel: on a
	tuner without /proc/stb/frontend/N/mode the default follows the driver, so the saved choice is written even when it
	equals the current default. Returns the previous save_forced, for a rollback; None when nothing applies."""
	try:
		slot = manager.nim_slots[slotid]
		if not slot.isMultiType():
			return None
		element = slot.config.multiType
	except (AttributeError, KeyError, IndexError):
		return None
	if not getattr(element, "hds_dinamic", False):
		return None
	vechi = element.save_forced
	element.save_forced = True
	return vechi


def hdsAplicaTipTuner(manager, slotid, valoare):
	"""Use the same notifier and configuration rebuild for TV and web."""
	slot = manager.nim_slots[slotid]
	if not slot.isMultiType() or valoare not in slot.config.multiType.choices:
		raise ValueError(_("Tip de tuner necunoscut."))
	element = slot.config.multiType
	old = element.value
	# Materialize saved settings before InitNimManager replaces their elements.
	config.Nims.saved_value
	try:
		if old != valoare:
			element.value = valoare
		InitNimManager(manager)
	except Exception:
		try:
			element.value = old
			InitNimManager(manager)
		except Exception:
			raise RuntimeError(_("Tipul tunerului nu s-a putut restabili. Verifică setările tunerului."))
		raise


class NIM(object):
	def isFBCLink(self):
		return self.fbc_role == 2

	def isFBCRoot(self):
		return self.fbc_role == 1

	def isFBCTuner(self):
		return self.fbc_role != 0

	def canBeCompatible(self, what):
		return self.isCompatible(what)

	def __init__(self, slot, type, description, has_outputs = True, internally_connectable = None, multi_type = {}, frontend_id = None, i2c = None, is_empty = False, multistream = False, s2x = False):
		self.slot = slot
		# filtrul de flux (ISI) si PLS-ul DVB-S2: tunerele care se anunta „DVB-S2X" sau „Multistream: yes"
		self.multistream = bool(multistream)
		# tunerul se anunta "Type: DVB-S2X" in /proc/bus/nim_sockets (tipul ramane DVB-S2, ca in restul imaginii); numai
		# pentru ce arata Informatii > Tunere ("Poate primi")
		self.s2x = bool(s2x)

		if type not in ("DVB-S", "DVB-C", "DVB-T", "DVB-S2", "DVB-C/T", None):
			print("warning: unknown NIM type %s, not using." % type)
			type = None

		self.type = type
		self.description = description
		self.has_outputs = has_outputs
		self.internally_connectable = internally_connectable
		self.multi_type = multi_type
		self.i2c = i2c
		self.frontend_id = frontend_id
		self.__is_empty = is_empty
		self.fbc_role = 0
		self.fbc_set_id = None

	def isCompatible(self, what):
		if not self.isSupported():
			return False
		compatible = {
				None: (None,),
				"DVB-S": ("DVB-S", None),
				"DVB-C": ("DVB-C", None),
				"DVB-T": ("DVB-T", None),
				"DVB-S2": ("DVB-S", "DVB-S2", None),
				"DVB-C/T": ("DVB-C", "DVB-T", None),
			}
		return what in compatible[self.type]
	
	def getType(self):
		return self.type
	
	def connectableTo(self):
		connectable = {
				"DVB-S": ("DVB-S", "DVB-S2"),
				"DVB-C": ("DVB-C",),
				"DVB-T": ("DVB-T",),
				"DVB-S2": ("DVB-S", "DVB-S2"),
				"DVB-C/T": ("DVB-C", "DVB-T"),
			}
		return connectable[self.type]

	def getSlotName(self):
		# get a friendly description for a slot name.
		# we name them "Tuner A/B/C/...", because that's what's usually written on the back
		# of the device.
		return _("Tuner ") + chr(ord('A') + self.slot)

	slot_name = property(getSlotName)

	def getSlotID(self):
		return chr(ord('A') + self.slot)
	
	def getI2C(self):
		return self.i2c
	
	def hasOutputs(self):
		return self.has_outputs
	
	def internallyConnectableTo(self):
		return self.internally_connectable
	
	def setInternalLink(self):
		if self.internally_connectable is not None:
			print("setting internal link on frontend id", self.frontend_id)
			open("/proc/stb/frontend/%d/rf_switch" % self.frontend_id, "w").write("internal")
		
	def removeInternalLink(self):
		if self.internally_connectable is not None:
			print("removing internal link on frontend id", self.frontend_id)
			open("/proc/stb/frontend/%d/rf_switch" % self.frontend_id, "w").write("external")
	
	def isMultiType(self):
		return (len(self.multi_type) > 0)

	def isMultistream(self):
		"""Tunerul de satelit poate alege un flux (ISI) si secventa PLS a unui transponder DVB-S2 multistream."""
		return self.multistream and self.isCompatible("DVB-S2")

	@staticmethod
	def numeCuCabluSiTerestru(nume):
		"""True cand numele tunerului din /proc/bus/nim_sockets spune si cablu si terestru. Sistemele se iau din
		grupurile care incep cu "DVB-", despartite de "/" sau ",": "DVB-C,T/T2 NIM" (Viper 4K V20), "ATBM7821 DVB-T2/C"
		(tunerul combinat al Octagon SF8008 si SF8008 MINI), "MXL608 DVB-C/T/T2", "DVB-C/DVB-T2". Nu: "DVB-S2 NIM",
		"Si2166D", "Tuner DVB-T2", "DVB-C NIM".
		De ce: driverul acestor placi (hi-dvb.ko, proc_bus_nim_sockets_read) scrie la "Type:" numai primul sistem din
		lista lui (DVB-S2, DVB-S, DVB-T2, DVB-T, ..., DVB-C), deci tunerul combinat se anunta "Type: DVB-T2", iar
		cablul se vede numai din nume. In "DVB-T2/C" sirul "DVB-C" nu apare, iar proba veche de mai jos il pierdea."""
		import re
		cablu = terestru = False
		for grup in re.findall(r"DVB-([A-Z0-9]+(?:\s*[/,]\s*(?:DVB-)?[A-Z0-9]+)*)", (nume or "").upper()):
			for sistem in re.split(r"\s*[/,]\s*", grup):
				if sistem.startswith("DVB-"):
					sistem = sistem[4:]
				if sistem in ("C", "C2"):
					cablu = True
				elif sistem in ("T", "T2"):
					terestru = True
		return cablu and terestru

	def isEmpty(self):
		return self.__is_empty
	
	# empty tuners are supported!
	def isSupported(self):
		return (self.frontend_id is not None) or self.__is_empty
	
	# returns dict {<slotid>: <type>}
	def getMultiTypeList(self):
		return self.multi_type

	slot_id = property(getSlotID)

	def getFriendlyType(self):
		return {
			"DVB-S": "DVB-S", 
			"DVB-T": "DVB-T",
			"DVB-S2": "DVB-S2",
			"DVB-C": "DVB-C",
			"DVB-C/T": "DVB-C/T2",
			None: _("empty")
			}[self.type]

	friendly_type = property(getFriendlyType)

	def getFriendlyFullDescription(self):
		nim_text = self.slot_name + ": "
			
		if self.empty:
			nim_text += _("(empty)")
		elif not self.isSupported():
			nim_text += self.description + " (" + _("not supported") + ")"
		else:
			nim_text += self.description + " (" + self.friendly_type + ")"
		
		return nim_text

	friendly_full_description = property(getFriendlyFullDescription)
	config_mode = property(lambda self: config.Nims[self.slot].configMode.value)
	config = property(lambda self: config.Nims[self.slot])
	empty = property(lambda self: self.type is None)

class NimManager:
	def getConfiguredSats(self):
		return self.sec.getConfiguredSats()

	def getTransponders(self, pos):
		if pos in self.transponders:
			return self.transponders[pos]
		else:
			return []

	def getTranspondersCable(self, nim):
		nimConfig = config.Nims[nim]
		if nimConfig.configMode.value != "nothing" and nimConfig.cable.scan_type.value == "provider":
			return self.transponderscable[self.cablesList[nimConfig.cable.scan_provider.index][0]]
		return [ ]

	def getTranspondersTerrestrial(self, region):
		return self.transpondersterrestrial[region]

	# HDSatelit: numele cerut de scanarea terestra a altor imagini (TerrestrialScan, vazut pe un receptor): lista regiunilor din
	# terrestrial.xml, aceeasi pe care o citeste imaginea pentru setarile tunerului
	def getTerrestrialsList(self):
		return self.terrestrialsList
	
	def getCableDescription(self, nim):
		return self.cablesList[config.Nims[nim].scan_provider.index][0]

	def getCableFlags(self, nim):
		return self.cablesList[config.Nims[nim].scan_provider.index][1]

	def getTerrestrialDescription(self, nim):
		return self.terrestrialsList[config.Nims[nim].terrestrial.index][0]

	def getTerrestrialFlags(self, nim):
		return self.terrestrialsList[config.Nims[nim].terrestrial.index][1]

	def getSatDescription(self, pos):
		return self.satellites[pos]

	def sortFunc(self, x):
		orbpos = x[0]
		if orbpos > 1800:
			return orbpos - 3600
		else:
			return orbpos + 1800

	def readTransponders(self):
		# read initial networks from file. we only read files which we are interested in,
		# which means only these where a compatible tuner exists.
		self.satellites = { }
		self.transponders = { }
		self.transponderscable = { }
		self.transpondersterrestrial = { }
		db = eDVBDB.getInstance()
		if self.hasNimType("DVB-S"):
			# HDSatelit (SXP): un satellites.xml scurtat de o lista de canale straina primeste inapoi, din lista imaginii,
			# satelitii pe care omul are canale sau ii are la tunere (unire, nimic sters; Components/HdsSatelitiImagine.py)
			try:
				from Components.HdsSatelitiImagine import uneste_la_pornire
				uneste_la_pornire()
			except Exception as e:
				print("[NimManager] unirea cu lista satelitilor imaginii: %s" % e)
			print("Reading satellites.xml")
			db.readSatellites(self.satList, self.satellites, self.transponders)
			self.satList.sort(key = self.sortFunc) # sort by orbpos
			#print "SATLIST", self.satList
			#print "SATS", self.satellites
			#print "TRANSPONDERS", self.transponders

		if self.hasNimType("DVB-C"):
			print("Reading cables.xml")
			db.readCables(self.cablesList, self.transponderscable)
#			print "CABLIST", self.cablesList
#			print "TRANSPONDERS", self.transponders

		if self.hasNimType("DVB-T"):
			print("Reading terrestrial.xml")
			db.readTerrestrials(self.terrestrialsList, self.transpondersterrestrial)
#			print "TERLIST", self.terrestrialsList
#			print "TRANSPONDERS", self.transpondersterrestrial

	def enumerateNIMs(self):
		# enum available NIMs. This is currently very dreambox-centric and uses the /proc/bus/nim_sockets interface.
		# the result will be stored into nim_slots.
		# the content of /proc/bus/nim_sockets looks like:
		# NIM Socket 0:
		#          Type: DVB-S
		#          Name: BCM4501 DVB-S2 NIM (internal)
		# NIM Socket 1:
		#          Type: DVB-S
		#          Name: BCM4501 DVB-S2 NIM (internal)
		# NIM Socket 2:
		#          Type: DVB-T
		#          Name: Philips TU1216
		# NIM Socket 3:
		#          Type: DVB-S
		#          Name: Alps BSBE1 702A
		
		#
		# Type will be either "DVB-S", "DVB-S2", "DVB-T", "DVB-C" or None.

		# nim_slots is an array which has exactly one entry for each slot, even for empty ones.
		self.nim_slots = [ ]

		nimfile = tryOpen("/proc/bus/nim_sockets")

		if nimfile is None:
			return

		current_slot = None

		entries = {}
		for line in nimfile.readlines():
			if line == "":
				break
			if line.strip().startswith("NIM Socket"):
				parts = line.strip().split(" ")
				current_slot = int(parts[2][:-1])
				entries[current_slot] = {}
			elif line.strip().startswith("Type:"):
				tip = str(line.strip()[6:])
				entries[current_slot]["type"] = normalizeNimType(tip)
				entries[current_slot]["isempty"] = False
				if tip == "DVB-S2X":
					entries[current_slot]["multistream"] = True
					entries[current_slot]["s2x"] = True
			elif line.strip().startswith("Multistream:"):
				entries[current_slot]["multistream"] = line.strip()[len("Multistream:"):].strip().lower() == "yes"
			elif line.strip().startswith("Name:"):
				entries[current_slot]["name"] = str(line.strip()[6:])
				entries[current_slot]["isempty"] = False
			elif line.strip().startswith("Has_Outputs:"):
				input = str(line.strip()[len("Has_Outputs:") + 1:])
				entries[current_slot]["has_outputs"] = (input == "yes")
			elif line.strip().startswith("Internally_Connectable:"):
				input = int(line.strip()[len("Internally_Connectable:") + 1:])
				entries[current_slot]["internally_connectable"] = input
			elif line.strip().startswith("Frontend_Device:"):
				input = int(line.strip()[len("Frontend_Device:") + 1:])
				entries[current_slot]["frontend_device"] = input
			elif  line.strip().startswith("Mode"):
				# "Mode 0: DVB-T" -> ["Mode 0", " DVB-T"]
				split = line.strip().split(":")
				# "Mode 0" -> ["Mode, "0"]
				split2 = split[0].split(" ")
				modes = entries[current_slot].get("multi_type", {})
				modes[split2[1]] = normalizeNimType(split[1].strip())
				entries[current_slot]["multi_type"] = modes
			elif line.strip().startswith("I2C_Device:"):
				input = int(line.strip()[len("I2C_Device:") + 1:])
				entries[current_slot]["i2c"] = input
			elif line.strip().startswith("empty"):
				entries[current_slot]["type"] = None
				entries[current_slot]["name"] = _("N/A")
				entries[current_slot]["isempty"] = True
		nimfile.close()
		
		from os import path
		usb = tunereUsb()
		
		for id, entry in list(entries.items()):
			if not ("name" in entry and "type" in entry):
				entry["name"] =  _("N/A")
				entry["type"] = None
			if entry.get("type") is not None and entry.get("frontend_device") in usb:
				# tunerul DVB pe USB, prin puntea vtuner: numele stickului, nu cel pus de driverul vtuner
				nume_usb, sisteme_usb = usb[entry["frontend_device"]]
				entry["name"], entry["type"] = numeTunerUsb(nume_usb, entry["type"], sisteme_usb)
				print("[NimManager] tuner USB pe slotul %d: %s (%s)" % (id, entry["name"], entry["type"]))
			name = entry.get("name", "")
			# Vu+ Duo 4K Lite (driverele platform-util): tunerul terestru BCM3466 si cel de cablu BCM3148/BCM3158 nu se
			# anunta cu tipul lor; dupa nume primesc tipul si numele tunerelor Vu+ (aceleasi ca pe Duo 4K si Uno 4K SE)
			chip = next((c for c in ("3466", "3148", "3158") if c in name), None)
			if chip == "3466" and "DVB-T" in name:
				entry["type"], entry["name"] = "DVB-T", "Vuplus DVB-T NIM(BCM3466)"
				name = entry["name"]
			elif chip in ("3148", "3158") and "DVB-C" in name and "DVB-T" not in name and "T2" not in name:
				entry["type"], entry["name"] = "DVB-C", "Vuplus DVB-C NIM(BCM%s)" % chip
				name = entry["name"]
			if ("DVB-C" in name and ("DVB-T" in name or "T2" in name)) or ("DVB-C" in name and "T/T2" in name):
				entry["type"] = "DVB-C/T"
			elif entry["type"] in ("DVB-T", "DVB-C") and NIM.numeCuCabluSiTerestru(name):
				# SF8008 si SF8008 MINI: "Type: DVB-T2" + "Name: ATBM7821 DVB-T2/C" (vezi NIM.numeCuCabluSiTerestru)
				entry["type"] = "DVB-C/T"
			if not ("i2c" in entry):
				entry["i2c"] = None
			if not ("has_outputs" in entry):
				entry["has_outputs"] = True
			if "frontend_device" in entry: # check if internally connectable
				if path.exists("/proc/stb/frontend/%d/rf_switch" % entry["frontend_device"]):
					entry["internally_connectable"] = entry["frontend_device"] - 1
				else:
					entry["internally_connectable"] = None
			else:
				entry["frontend_device"] = entry["internally_connectable"] = None
			if not ("multi_type" in entry):
				entry["multi_type"] = {}
			self.nim_slots.append(NIM(slot = id, description = entry["name"], type = entry["type"], has_outputs = entry["has_outputs"], internally_connectable = entry["internally_connectable"], multi_type = entry["multi_type"], frontend_id = entry["frontend_device"], i2c = entry["i2c"], is_empty = entry["isempty"], multistream = entry.get("multistream", False), s2x = entry.get("s2x", False)))
		from Components.HdsFbc import descopera
		fbc = descopera(self.nim_slots)
		for tuner in self.nim_slots:
			tuner.fbc_role, tuner.fbc_set_id = fbc.get(tuner.frontend_id, (0, None))

	def hasNimType(self, chktype):
		for slot in self.nim_slots:
			if slot.isCompatible(chktype):
				return True
			for type in list(slot.getMultiTypeList().values()):
				if chktype == type:
					return True
		return False
	
	def getNimType(self, slotid):
		return self.nim_slots[slotid].type
	
	def getNimDescription(self, slotid):
		return self.nim_slots[slotid].friendly_full_description
	
	def getNimName(self, slotid):
		return self.nim_slots[slotid].description
	
	def getNim(self, slotid):
		return self.nim_slots[slotid]
	
	def getI2CDevice(self, slotid):
		return self.nim_slots[slotid].getI2C()

	def getNimListOfType(self, type, exception = -1):
		# returns a list of indexes for NIMs compatible to the given type, except for 'exception'
		list = []
		for x in self.nim_slots:
			if x.isCompatible(type) and x.slot != exception:
				list.append(x.slot)
		return list

	def __init__(self):
		self.satList = [ ]
		self.cablesList = []
		self.terrestrialsList = []
		self.enumerateNIMs()
		self.readTransponders()
		InitNimManager(self)	#init config stuff

	# get a list with the friendly full description
	def nimList(self):
		list = [ ]
		for slot in self.nim_slots:
			list.append(slot.friendly_full_description)
		return list
	
	def getSlotCount(self):
		return len(self.nim_slots)
	
	def hasOutputs(self, slotid):
		return self.nim_slots[slotid].hasOutputs()
	
	def nimInternallyConnectableTo(self, slotid):
		return self.nim_slots[slotid].internallyConnectableTo()
	
	def nimRemoveInternalLink(self, slotid):
		self.nim_slots[slotid].removeInternalLink()
	
	def canConnectTo(self, slotid):
		slots = []
		if self.nim_slots[slotid].internallyConnectableTo() is not None:
			slots.append(self.nim_slots[slotid].internallyConnectableTo())
		for type in self.nim_slots[slotid].connectableTo(): 
			for slot in self.getNimListOfType(type, exception = slotid):
				if self.hasOutputs(slot):
					slots.append(slot)
		# remove nims, that have a conntectedTo reference on
		for testnim in slots[:]:
			for nim in self.getNimListOfType("DVB-S", slotid):
				nimConfig = self.getNimConfig(nim)
				if "configMode" in nimConfig.content.items and nimConfig.configMode.value == "loopthrough" and int(nimConfig.connectedTo.value) == testnim:
					slots.remove(testnim)
					break 
		slots.sort()
		
		return slots
	
	def canEqualTo(self, slotid):
		type = self.getNimType(slotid)
		if type == "DVB-S2":
			type = "DVB-S"
		nimList = self.getNimListOfType(type, slotid)
		for nim in nimList[:]:
			mode = self.getNimConfig(nim)
			if mode.configMode.value == "loopthrough" or mode.configMode.value == "satposdepends":
				nimList.remove(nim)
		return nimList

	def canDependOn(self, slotid):
		type = self.getNimType(slotid)
		if type == "DVB-S2":
			type = "DVB-S"
		nimList = self.getNimListOfType(type, slotid)
		positionerList = []
		for nim in nimList[:]:
			mode = self.getNimConfig(nim)
			nimHaveRotor = mode.configMode.value == "simple" and mode.diseqcMode.value == "positioner"
			if not nimHaveRotor and mode.configMode.value == "advanced":
				for x in range(3601, 3605):
					lnb = int(mode.advanced.sat[x].lnb.value)
					if lnb != 0:
						nimHaveRotor = True
						break
				if not nimHaveRotor:
					for sat in list(mode.advanced.sat.values()):
						lnb_num = int(sat.lnb.value)
						diseqcmode = lnb_num and mode.advanced.lnb[lnb_num].diseqcMode.value or ""
						if diseqcmode == "1_2":
							nimHaveRotor = True
							break
			if nimHaveRotor:
				alreadyConnected = False
				for testnim in nimList:
					testmode = self.getNimConfig(testnim)
					if testmode.configMode.value == "satposdepends" and int(testmode.connectedTo.value) == int(nim):
						alreadyConnected = True
						break
				if not alreadyConnected:
					positionerList.append(nim)
		return positionerList
	
	def getNimConfig(self, slotid):
		return config.Nims[slotid]
	
	def getSatName(self, pos):
		for sat in self.satList:
			if sat[0] == pos:
				return sat[1]
		return _("N/A")

	def getSatList(self):
		return self.satList
	
	# returns True if something is configured to be connected to this nim
	# if slotid == -1, returns if something is connected to ANY nim
	def somethingConnected(self, slotid = -1):
		if (slotid == -1):
			connected = False
			for id in range(self.getSlotCount()):
				if self.somethingConnected(id):
					connected = True
			return connected
		else:
			nim = config.Nims[slotid]
			configMode = nim.configMode.value
		
			if self.nim_slots[slotid].isCompatible("DVB-S") or self.nim_slots[slotid].isCompatible("DVB-T") or self.nim_slots[slotid].isCompatible("DVB-C"):
				return not (configMode == "nothing")

	def getNimListForSat(self, orb_pos):
		"""Tunerele DVB-S (numerele lor) care au setat satelitul de la pozitia orb_pos (zecimi de grad); ca in OE-Alliance,
		cerut de pluginul FastScan (tunerul pe care se poate face cautarea rapida a unui operator)."""
		lista = []
		for nim in self.nim_slots:
			try:
				if nim.isCompatible("DVB-S") and orb_pos in [sat[0] for sat in self.getSatListForNim(nim.slot)]:
					lista.append(nim.slot)
			except Exception as e:
				print("[NimManager] getNimListForSat %s: %s" % (nim.slot, e))
		return lista

	def getSatListForNim(self, slotid):
		list = []
		if self.nim_slots[slotid].isCompatible("DVB-S"):
			nim = config.Nims[slotid]
			#print "slotid:", slotid

			#print "self.satellites:", self.satList[config.Nims[slotid].diseqcA.index]
			#print "diseqcA:", config.Nims[slotid].diseqcA.value
			configMode = nim.configMode.value

			if configMode == "equal":
				slotid = int(nim.connectedTo.value)
				nim = config.Nims[slotid]
				configMode = nim.configMode.value
			elif configMode == "loopthrough":
				slotid = self.sec.getRoot(slotid, int(nim.connectedTo.value))
				nim = config.Nims[slotid]
				configMode = nim.configMode.value

			if configMode == "simple":
				dm = nim.diseqcMode.value
				if dm in ("single", "toneburst_a_b", "diseqc_a_b", "diseqc_a_b_c_d"):
					if nim.diseqcA.orbital_position != 3601:
						list.append(self.satList[nim.diseqcA.index-1])
				if dm in ("toneburst_a_b", "diseqc_a_b", "diseqc_a_b_c_d"):
					if nim.diseqcB.orbital_position != 3601:
						list.append(self.satList[nim.diseqcB.index-1])
				if dm == "diseqc_a_b_c_d":
					if nim.diseqcC.orbital_position != 3601:
						list.append(self.satList[nim.diseqcC.index-1])
					if nim.diseqcD.orbital_position != 3601:
						list.append(self.satList[nim.diseqcD.index-1])
				if dm == "positioner":
					for x in self.satList:
						list.append(x)
			elif configMode == "advanced":
				for x in range(3601, 3605):
					if int(nim.advanced.sat[x].lnb.value) != 0:
						for x in self.satList:
							list.append(x)
				if not list:
					for x in self.satList:
						if int(nim.advanced.sat[x[0]].lnb.value) != 0:
							list.append(x)
		return list

	def getRotorSatListForNim(self, slotid):
		list = []
		if self.nim_slots[slotid].isCompatible("DVB-S"):
			#print "slotid:", slotid
			#print "self.satellites:", self.satList[config.Nims[slotid].diseqcA.value]
			#print "diseqcA:", config.Nims[slotid].diseqcA.value
			configMode = config.Nims[slotid].configMode.value
			if configMode == "simple":
				if config.Nims[slotid].diseqcMode.value == "positioner":
					for x in self.satList:
						list.append(x)
			elif configMode == "advanced":
				nim = config.Nims[slotid]
				for x in range(3601, 3605):
					if int(nim.advanced.sat[x].lnb.value) != 0:
						for x in self.satList:
							list.append(x)
				if not list:
					for x in self.satList:
						lnbnum = int(nim.advanced.sat[x[0]].lnb.value)
						if lnbnum != 0:
							lnb = nim.advanced.lnb[lnbnum]
							if lnb.diseqcMode.value == "1_2":
								list.append(x)
		return list

def InitSecParams():
	config.sec = ConfigSubsection()

	x = ConfigInteger(default=25, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_CONT_TONE_DISABLE_BEFORE_DISEQC, configElement.value))
	config.sec.delay_after_continuous_tone_disable_before_diseqc = x

	x = ConfigInteger(default=10, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_FINAL_CONT_TONE_CHANGE, configElement.value))
	config.sec.delay_after_final_continuous_tone_change = x

	x = ConfigInteger(default=10, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_FINAL_VOLTAGE_CHANGE, configElement.value))
	config.sec.delay_after_final_voltage_change = x

	x = ConfigInteger(default=120, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_BETWEEN_DISEQC_REPEATS, configElement.value))
	config.sec.delay_between_diseqc_repeats = x

	x = ConfigInteger(default=50, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_LAST_DISEQC_CMD, configElement.value))
	config.sec.delay_after_last_diseqc_command = x

	x = ConfigInteger(default=50, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_TONEBURST, configElement.value))
	config.sec.delay_after_toneburst = x

	x = ConfigInteger(default=20, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_SWITCH_CMDS, configElement.value))
	config.sec.delay_after_change_voltage_before_switch_command = x

	x = ConfigInteger(default=200, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_SWITCH_CMDS, configElement.value))
	config.sec.delay_after_enable_voltage_before_switch_command = x

	x = ConfigInteger(default=700, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_BETWEEN_SWITCH_AND_MOTOR_CMD, configElement.value))
	config.sec.delay_between_switch_and_motor_command = x

	x = ConfigInteger(default=500, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MEASURE_IDLE_INPUTPOWER, configElement.value))
	config.sec.delay_after_voltage_change_before_measure_idle_inputpower = x

	x = ConfigInteger(default=900, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_ENABLE_VOLTAGE_BEFORE_MOTOR_CMD, configElement.value))
	config.sec.delay_after_enable_voltage_before_motor_command = x

	x = ConfigInteger(default=500, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_MOTOR_STOP_CMD, configElement.value))
	config.sec.delay_after_motor_stop_command = x

	x = ConfigInteger(default=500, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_VOLTAGE_CHANGE_BEFORE_MOTOR_CMD, configElement.value))
	config.sec.delay_after_voltage_change_before_motor_command = x

	x = ConfigInteger(default=70, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_BEFORE_SEQUENCE_REPEAT, configElement.value))
	config.sec.delay_before_sequence_repeat = x

	x = ConfigInteger(default=360, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.MOTOR_RUNNING_TIMEOUT, configElement.value))
	config.sec.motor_running_timeout = x

	x = ConfigInteger(default=1, limits = (0, 5))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.MOTOR_COMMAND_RETRIES, configElement.value))
	config.sec.motor_command_retries = x

	x = ConfigInteger(default=50, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_DISEQC_RESET_CMD, configElement.value))
	config.sec.delay_after_diseqc_reset_cmd = x

	x = ConfigInteger(default=150, limits = (0, 9999))
	x.addNotifier(lambda configElement: secClass.setParam(secClass.DELAY_AFTER_DISEQC_PERIPHERIAL_POWERON_CMD, configElement.value))
	config.sec.delay_after_diseqc_peripherial_poweron_cmd = x

# TODO add support for satpos depending nims to advanced nim configuration
# so a second/third/fourth cable from a motorized lnb can used behind a
# diseqc 1.0 / diseqc 1.1 / toneburst switch
# the C(++) part should can handle this
# the configElement should be only visible when diseqc 1.2 is disabled

# tunerul combinat DVB-T2/C: alegerea implicita, din lista de canale (o data pe pornire)
_FEL_COMBINAT = []


def felCombinatImplicit(cale = "/etc/enigma2/lamedb"):
	"""'terestru' sau 'cablu' pentru tunerul combinat cand omul n-a ales: ce are lista de canale (randurile
	transponderelor terestre si de cablu din lamedb); la egalitate sau fara niciunul, terestru (antena, cum vine
	tunerul de la fabrica). Citit o singura data pe pornire."""
	if _FEL_COMBINAT:
		return _FEL_COMBINAT[0]
	ter = cab = 0
	try:
		with open(cale, "rb") as f:
			for rand in f:
				if rand.startswith(b"\tt "):
					ter += 1
				elif rand.startswith(b"\tc "):
					cab += 1
	except (IOError, OSError):
		pass
	fel = "cablu" if cab > ter else "terestru"
	_FEL_COMBINAT.append(fel)
	return fel


# satelitii primului tuner de satelit cand vine pornit singur (DiSEqC A si B), dupa tara receptorului (din limba
# meniurilor): A = pozitia celor mai multi operatori ai tarii din operatori-satelit.json (la egalitate, primul din
# fisier), B = 19,2E, sau 13,0E cand A e chiar 19,2E. Pentru Romania: Thor 0,8W si 19,2E. Fara operatori pentru tara:
# 19,2E si 13,0E, implicitele de dinainte ale modulului.
SATELITI_IMPLICITI = (192, 130)


def satelitiDupaTara(tara, operatori=None):
	"""(A, B): pozitiile orbitale (in zecimi de grad, vestul ca 3600 - x) pentru DiSEqC A si B ale tarii date."""
	if operatori is None:
		try:
			from Components import HdsOperatoriSatelit
			operatori = HdsOperatoriSatelit.incarca().get("operatori") or []
		except Exception as e:
			print("[NimManager] operatorii de satelit: %s" % e)
			operatori = []
	numar = {}
	ordine = []
	for op in operatori:
		try:
			poz = int(op.get("pozitie"))
		except (AttributeError, TypeError, ValueError):
			continue
		if tara and tara in (op.get("tari") or []):
			if poz not in numar:
				ordine.append(poz)
				numar[poz] = 0
			numar[poz] += 1
	if not ordine:
		return SATELITI_IMPLICITI
	a = sorted(ordine, key=lambda p: (-numar[p], ordine.index(p)))[0]
	return (a, 130 if a == 192 else 192)


def limbaReceptorului():
	"""Limba meniurilor ("ro_RO"): setarea, altfel cea scrisa in settings (setarea se face dupa NimManager), altfel
	limba activa."""
	try:
		return config.osd.language.value
	except Exception:
		pass
	try:
		limba = (config.content.stored_values.get("osd") or {}).get("language")
		if limba:
			return limba
	except Exception:
		pass
	try:
		from Components.Language import language
		return language.getLanguage()
	except Exception:
		return None


def taraReceptorului(limba=None):
	"""Codul de tara (doua litere) din limba meniurilor; "RO" cand nu se poate afla."""
	try:
		from Components import HdsOperatoriSatelit
		return HdsOperatoriSatelit.tara_din_limba(limba or limbaReceptorului()) or HdsOperatoriSatelit.TARA_IMPLICITA
	except Exception as e:
		print("[NimManager] tara receptorului: %s" % e)
		return "RO"


def satelitiReceptorului(satlist, limba=None):
	"""(A, B) dupa tara receptorului, numai cu sateliti din lista receptorului (altfel implicitele vechi)."""
	pozitii = set(x[0] for x in satlist)
	a, b = satelitiDupaTara(taraReceptorului(limba))
	if a not in pozitii or b not in pozitii:
		return SATELITI_IMPLICITI
	return (a, b)


# HDSatelit (0.7.5, 15.11.2026, TNB): satelitii salvati la tunere si lipsa din satellites.xml. Alegerile lui diseqcA..D
# (si intrarile modului avansat) se fac din nimmgr.satList; o pozitie salvata care nu e acolo la pornire era inlocuita tacut
# cu implicitul (ConfigSelection.setValue), iar la prima salvare disparea si din settings. kegnkiwi (GigaBlue Quad 4K Pro,
# SatWorld 3925 #5697): tunerul B fix pe 28,2E a ajuns sa arate numai 19,2E si 13,0E. Acum pozitia intra in satList cu un
# nume care spune ca lipseste din lista satelitilor: valoarea omului ramane si nucleul primeste satelitul.
# 0.7.7 (SAT, 16.11.2026, forum 1588 lme): pozitia nu se mai pastreaza (satelitul sters de om revenea in alegeri), ci
# portul ei devine "nimic conectat" / LNB nefolosit, cu un mesaj pe ecran (hdsSatelitiSalvatiLipsa); implicitul nu se pune.
def _hdsPozitie(valoare):
	try:
		pozitie = int(str(valoare).strip())
	except (TypeError, ValueError):
		return None
	return pozitie if 0 <= pozitie < 3600 else None


def _hdsNumeSatelit(pozitie):
	if pozitie > 1800:
		return "%d.%dW" % ((3600 - pozitie) // 10, (3600 - pozitie) % 10)
	return "%d.%dE" % (pozitie // 10, pozitie % 10)


def _hdsReferinte(salvate, mod_implicit="nothing"):
	"""[(cheie, pozitie)] folosite cu adevarat de tuner (Components/HdsSatelitiImagine.referinte_tuner: numai cheile
	active ale modului lui)."""
	try:
		from Components.HdsSatelitiImagine import referinte_tuner
	except ImportError:  # pe PC, in probe
		from HdsSatelitiImagine import referinte_tuner
	return referinte_tuner(salvate, mod_implicit)


def hdsPozitiiSalvate(salvate, mod_implicit="simple"):
	"""Pozitiile din valorile salvate ale unui tuner (stored_values din config.Nims[N]): porturile DiSEqC ale felului ales
	in modul simplu si satelitii cu LNB ales in modul avansat (0.7.7, SAT: numai cheile active; diseqcA/diseqcB scrise
	fortat la prima pornire raman in settings si dupa trecerea pe modul avansat, iar la lme aduceau inapoi 28,2E si
	19,2E). Valorile rele si "nimic conectat" (3601) nu conteaza."""
	return set(p for _cheie, p in _hdsReferinte(salvate, mod_implicit))


def hdsSatelitiSalvatiLipsa(nimmgr):
	"""0.7.7 (SAT, 16.11.2026; inlocuieste pastrarea TNB din 0.7.5): o pozitie folosita de un tuner de satelit (portul
	DiSEqC al felului ales, LNB-ul din modul avansat) care nu mai e in satellites.xml se scoate de la tuner, inaintea
	alegerilor din InitNimManager: portul devine "nimic conectat" (3601), LNB-ul satelitului nefolosit; restul tunerului
	ramane. Satelitul nu mai intra in satList (un satelit sters de om, din editor, de mana sau printr-o lista instalata,
	nu revine, ca in celelalte imagini), iar implicitul nu se mai pune tacut in locul lui (kegnkiwi, TNB). Cu satList
	gol (satellites.xml lipsa sau stricat) nu se atinge nimic. Ce s-a scos se spune pe ecran dupa pornire
	(_hdsSpuneScoase). Intoarce [(slot, cheie, pozitie)] scoase."""
	nimmgr.hdsPozitiiPastrate = []
	try:
		nims = config.Nims
	except Exception:
		return []
	if not nimmgr.satList:
		return []
	cunoscute = set(x[0] for x in nimmgr.satList)
	primul = None
	for slot in nimmgr.nim_slots:
		if slot.isCompatible("DVB-S"):
			primul = slot.slot
			break
	scoase = []
	for slot in nimmgr.nim_slots:
		try:
			if not slot.isCompatible("DVB-S"):
				continue
			salvate = nims[slot.slot].content.stored_values
			for cheie, pozitie in _hdsReferinte(salvate, "simple" if slot.slot == primul else "nothing"):
				if pozitie in cunoscute:
					continue
				if cheie.startswith("diseqc"):
					salvate[cheie] = "3601"
				else:
					salvate["advanced"]["sat"][cheie.split(".", 2)[2]].pop("lnb", None)
				scoase.append((slot.slot, cheie, pozitie))
				print("[NimManager] tunerul %d: %s = %d nu mai e in satellites.xml: scos (nimic conectat / LNB nefolosit)" %
					(slot.slot, cheie, pozitie))
		except Exception as e:
			print("[NimManager] satelitii salvati ai tunerului %s: %s" % (getattr(slot, "slot", "?"), e))
	if scoase:
		_hdsSpuneScoase(nimmgr, scoase)
	return scoase


def _hdsSpuneScoase(nimmgr, scoase):
	"""Mesajul scurt pe ecran, dupa pornire (coada Notifications, din bucla enigma2: la crearea NimManager ecranele nu
	sunt gata)."""
	nimmgr.hdsScoaseLaPornire = list(scoase)

	def spune():
		try:
			from Components.HdsSatelitiImagine import text_scoase
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			text = _("Sateliți care nu mai sunt în lista sateliților, scoși de la tunere: %s.") % text_scoase(scoase)
			Notifications.AddPopup(text, MessageBox.TYPE_INFO, 15, "HdsSatelitiScosi")
		except Exception as e:
			print("[NimManager] mesajul satelitilor scosi: %s" % e)
	try:
		from enigma import eTimer
		nimmgr.hdsCeasScoase = eTimer()
		nimmgr.hdsCeasScoase.callback.append(spune)
		nimmgr.hdsCeasScoase.start(8000, True)
	except Exception as e:
		print("[NimManager] mesajul satelitilor scosi: %s" % e)


def _hdsPunePozitii(nimmgr, pozitii):
	"""Pozitiile date, care nu sunt in satList, intra in satList (ordonat) si in nimmgr.satellites (getSatDescription)."""
	cunoscute = set(x[0] for x in nimmgr.satList)
	puse = [p for p in sorted(pozitii) if p not in cunoscute]
	descrieri = getattr(nimmgr, "satellites", None)
	for pozitie in puse:
		nume = _("%s (lipsește din lista sateliților)") % _hdsNumeSatelit(pozitie)
		nimmgr.satList.append((pozitie, nume, 0))
		if isinstance(descrieri, dict):
			descrieri.setdefault(pozitie, nume)
		print("[NimManager] satelitul %d e salvat la un tuner, dar lipseste din satellites.xml: pastrat" % pozitie)
	if puse:
		nimmgr.satList.sort(key=nimmgr.sortFunc)
	return puse


def hdsPunePozitiilePastrate(nimmgr):
	"""Dupa o recitire a satellites.xml pe loc (aplicatii_web, /web/servicelistreload?mode=3, prin
	hdsCompleteazaSatelitiAvansati): pozitiile pastrate la pornire se pun la loc. Alegerile tunerelor (facute la pornire)
	si getSatListForNim (dupa index in satList) raman potrivite."""
	return _hdsPunePozitii(nimmgr, getattr(nimmgr, "hdsPozitiiPastrate", None) or ())


def _limbaActiva():
	"""Limba tocmai aleasa (Components.Language), sau None."""
	try:
		from Components.Language import language
		return language.getLanguage()
	except Exception:
		return None


def _taraSchimbata(slot, implicite):
	"""Limba aleasa in asistentul primei porniri (dupa ce tunerul a primit satelitii): daca omul n-a schimbat inca
	nimic la tuner, satelitii A si B se iau dupa tara noii limbi. Dupa asistent o limba schimbata nu-i mai muta (un
	receptor din Romania cu meniul in engleza ramane pe Thor)."""
	try:
		if not config.misc.firstrun.value:
			return
		nim = config.Nims[slot]
		a, b = satelitiReceptorului([(int(v), d, 0) for v, d in nim.diseqcA.choices.choices], _limbaActiva())
		if (a, b) == tuple(implicite) or nim.configMode.value != "simple":
			return
		if (nim.diseqcA.orbital_position, nim.diseqcB.orbital_position) != tuple(implicite):
			return
		nim.diseqcA.default = nim.diseqcA.value = str(a)
		nim.diseqcB.default = nim.diseqcB.value = str(b)
		nim.diseqcA.save()
		nim.diseqcB.save()
		implicite[:] = [a, b]
		print("[NimManager] tunerul %d: satelitii dupa tara noii limbi: %d si %d" % (slot, a, b))
	except Exception as e:
		print("[NimManager] tunerul %d: satelitii dupa limba: %s" % (slot, e))


def InitNimManager(nimmgr):
	hw = HardwareInfo()
	addNimConfig = False
	try:
		config.Nims
	except:
		addNimConfig = True

	if addNimConfig:
		InitSecParams()
		config.Nims = ConfigSubList()
		for x in range(len(nimmgr.nim_slots)):
			config.Nims.append(ConfigSubsection())

	lnb_choices = {
		"universal_lnb": _("Universal LNB"),
		"unicable": _("Unicable"),
		"c_band": _("C-Band"),
		"c_band_5750": _("Banda C (5750)"),
		"user_defined": _("User defined")}

	lnb_choices_default = "universal_lnb"

	unicablelnbproducts, unicablematrixproducts = readUnicableProducts(
		eEnv.resolve("${datadir}/enigma2/unicable.xml"))

	UnicableLnbManufacturers = [*unicablelnbproducts.keys()]
	UnicableLnbManufacturers.sort()
	UnicableMatrixManufacturers = [*unicablematrixproducts.keys()]
	UnicableMatrixManufacturers.sort()

	unicable_choices = {
		"unicable_lnb": _("Unicable LNB"),
		"unicable_matrix": _("Unicable Martix"),
		"unicable_user": "Unicable "+_("User defined")}
	unicable_choices_default = "unicable_lnb"

	prio_list = [ ("-1", _("Auto")) ]
	prio_list += [(str(prio), str(prio)) for prio in [*range(65)]+[*range(14000,14065)]+[*range(19000,19065)]]

	advanced_lnb_csw_choices = [("none", _("None")), ("AA", _("AA")), ("AB", _("AB")), ("BA", _("BA")), ("BB", _("BB"))]
	advanced_lnb_csw_choices += [(str(0xF0|y), "Input " + str(y+1)) for y in range(0, 16)]

	advanced_lnb_ucsw_choices = [("0", _("None"))] + [(str(y), "Input " + str(y)) for y in range(1, 17)]

	diseqc_mode_choices = [
		("single", _("Single")), ("toneburst_a_b", _("Toneburst A/B")),
		("diseqc_a_b", _("DiSEqC A/B")), ("diseqc_a_b_c_d", _("DiSEqC A/B/C/D")),
		("positioner", _("Positioner"))]

	positioner_mode_choices = [("usals", _("USALS")), ("manual", _("manual"))]

	# HDSatelit: un satelit folosit de un tuner si lipsa din satellites.xml se scoate de la tuner (hdsSatelitiSalvatiLipsa, 0.7.7)
	hdsSatelitiSalvatiLipsa(nimmgr)
	diseqc_satlist_choices = [(3601, _('nothing connected'), 1)] + nimmgr.satList
	
	longitude_orientation_choices = [("east", _("East")), ("west", _("West"))]
	latitude_orientation_choices = [("north", _("North")), ("south", _("South"))]
	turning_speed_choices = [("fast", _("Fast")), ("slow", _("Slow")), ("fast epoch", _("Fast epoch"))]
	
	advanced_satlist_choices = nimmgr.satList + [
		(3601, _('All Satellites')+' 1', 1), (3602, _('All Satellites')+' 2', 1),
		(3603, _('All Satellites')+' 3', 1), (3604, _('All Satellites')+' 4', 1)]
	# HDSatelit: textul se traduce (modul avansat, randul LNB al unui satelit fara LNB ales)
	advanced_lnb_choices = [("0", _("not available"))] + [(str(y), "LNB " + str(y)) for y in range(1, 33)]
	advanced_voltage_choices = [("polarization", _("Polarization")), ("13V", _("13 V")), ("18V", _("18 V"))]
	advanced_tonemode_choices = [("band", _("Band")), ("on", _("On")), ("off", _("Off"))]
	advanced_lnb_toneburst_choices = [("none", _("None")), ("A", _("A")), ("B", _("B"))]
	advanced_lnb_allsat_diseqcmode_choices = [("1_2", _("1.2"))]
	advanced_lnb_diseqcmode_choices = [("none", _("None")), ("1_0", _("1.0")), ("1_1", _("1.1")), ("1_2", _("1.2"))]
	advanced_lnb_commandOrder1_0_choices = [("ct", "committed, toneburst"), ("tc", "toneburst, committed")]
	advanced_lnb_commandOrder_choices = [
		("ct", "committed, toneburst"), ("tc", "toneburst, committed"),
		("cut", "committed, uncommitted, toneburst"), ("tcu", "toneburst, committed, uncommitted"),
		("uct", "uncommitted, committed, toneburst"), ("tuc", "toneburst, uncommitted, commmitted")]
	advanced_lnb_diseqc_repeat_choices = [("none", _("None")), ("one", _("One")), ("two", _("Two")), ("three", _("Three"))]
	advanced_lnb_fast_turning_btime = mktime(datetime(1970, 1, 1, 7, 0).timetuple());
	advanced_lnb_fast_turning_etime = mktime(datetime(1970, 1, 1, 19, 0).timetuple());

	def configLOFChanged(configElement):
		if configElement.value == "unicable":
			x = configElement.slot_id
			lnb = configElement.lnb_id
			nim = config.Nims[x]
			lnbs = nim.advanced.lnb
			section = lnbs[lnb]
			if isinstance(section.unicable, ConfigNothing):
				if lnb == 1:
					section.unicable = ConfigSelection(unicable_choices, unicable_choices_default)
				elif lnb == 2:
					section.unicable = ConfigSelection(choices = {"unicable_matrix": _("Unicable Martix"),"unicable_user": "Unicable "+_("User defined")}, default = "unicable_matrix")
				else:
					section.unicable = ConfigSelection(choices = {"unicable_user": _("User defined")}, default = "unicable_user")

				if lnb < 3:
					print("MATRIX")
					section.unicableMatrix = ConfigSubDict()
					section.unicableMatrixManufacturer = ConfigSelection(UnicableMatrixManufacturers, UnicableMatrixManufacturers[0])
					fillUnicableConf(section.unicableMatrix, unicablematrixproducts, True)

				if lnb < 2:
					print("LNB")
					section.unicableLnb = ConfigSubDict()
					section.unicableLnbManufacturer = ConfigSelection(UnicableLnbManufacturers, UnicableLnbManufacturers[0])
					fillUnicableConf(section.unicableLnb, unicablelnbproducts, False)

				initUnicableUser(section)

				nim.advanced.unicableconnected = ConfigYesNo(default=False)
				nim.advanced.unicableconnectedTo = ConfigSelection([(str(id), nimmgr.getNimDescription(id)) for id in nimmgr.getNimListOfType("DVB-S") if id != x])
	
	def configDiSEqCModeChanged(configElement):
		section = configElement.section
		if configElement.value == "1_2" and isinstance(section.longitude, ConfigNothing):
			# locul antenei: implicitul e neutru, valorile le scrie numai Components/HdsLocul.py (locul unic)
			section.longitude = ConfigFloat(default = [0,0], limits = [(0,359),(0,999)])
			section.longitudeOrientation = ConfigSelection(longitude_orientation_choices, "east")
			section.latitude = ConfigFloat(default = [0,0], limits = [(0,359),(0,999)])
			section.latitudeOrientation = ConfigSelection(latitude_orientation_choices, "north")
			section.powerMeasurement = ConfigYesNo(default=True)
			section.powerThreshold = ConfigInteger(default=hw.get_device_name() == "dm7025" and 50 or 15, limits=(0, 100))
			section.turningSpeed = ConfigSelection(turning_speed_choices, "fast")
			section.fastTurningBegin = ConfigDateTime(default=advanced_lnb_fast_turning_btime, formatstring = _("%H:%M"), increment = 600)
			section.fastTurningEnd = ConfigDateTime(default=advanced_lnb_fast_turning_etime, formatstring = _("%H:%M"), increment = 600)
			# un LNB trecut acum pe DiSEqC 1.2 ia locul stabilit, daca nu are cheile lui in settings
			from Components import HdsLocul
			HdsLocul.umpleGrup(section)

	def configLNBChanged(configElement):
		x = configElement.slot_id
		nim = config.Nims[x]
		if isinstance(configElement.value, tuple):
			lnb = int(configElement.value[0])
		else:
			lnb = int(configElement.value)
		lnbs = nim.advanced.lnb
		if lnb and lnb not in lnbs:
			section = lnbs[lnb] = ConfigSubsection()
			# New linked-FBC LNBs start with SCR. Stored configurations retain every value.
			fresh_fbc = (nimmgr.nim_slots[x].isFBCLink() and not section.content.stored_values
				and configElement.saved_value != str(lnb))
			section.lofl = ConfigInteger(default=9750, limits = (0, 99999))
			section.lofh = ConfigInteger(default=10600, limits = (0, 99999))
			section.threshold = ConfigInteger(default=11700, limits = (0, 99999))
#			section.output_12v = ConfigSelection(choices = [("0V", _("0 V")), ("12V", _("12 V"))], default="0V")
			section.increased_voltage = ConfigYesNo(False)
			section.toneburst = ConfigSelection(advanced_lnb_toneburst_choices, "none")
			section.longitude = ConfigNothing()
			if lnb > 32 and not nimmgr.nim_slots[x].isFBCLink():
				tmp = ConfigSelection(advanced_lnb_allsat_diseqcmode_choices, "1_2")
				tmp.section = section
				configDiSEqCModeChanged(tmp)
			else:
				tmp = ConfigSelection(advanced_lnb_diseqcmode_choices, "1_2" if lnb > 32 and not fresh_fbc else "none")
				tmp.section = section
				tmp.addNotifier(configDiSEqCModeChanged)
			tmp.save_forced = fresh_fbc and lnb > 32
			section.diseqcMode = tmp
			section.commitedDiseqcCommand = ConfigSelection(advanced_lnb_csw_choices)
			section.fastDiseqc = ConfigYesNo(False)
			section.sequenceRepeat = ConfigYesNo(False)
			section.commandOrder1_0 = ConfigSelection(advanced_lnb_commandOrder1_0_choices, "ct")
			section.commandOrder = ConfigSelection(advanced_lnb_commandOrder_choices, "ct")
			section.uncommittedDiseqcCommand = ConfigSelection(advanced_lnb_ucsw_choices)
			section.diseqcRepeats = ConfigSelection(advanced_lnb_diseqc_repeat_choices, "none")
			section.prio = ConfigSelection(prio_list, "-1")
			section.unicable = ConfigNothing()
			tmp = ConfigSelection(lnb_choices, "unicable" if fresh_fbc else lnb_choices_default)
			tmp.save_forced = fresh_fbc
			tmp.slot_id = x
			tmp.lnb_id = lnb
			tmp.addNotifier(configLOFChanged, initial_call = False)
			section.lof = tmp
			if fresh_fbc:
				configLOFChanged(tmp)

	def hdsSatAvansat(slot_id):
		"""intrarea unui satelit in setarile avansate ale tunerului `slot_id` (aceeasi la crearea setarilor avansate si la
		satelitii adaugati dupa pornire, hdsCompleteazaSatelitiAvansati)"""
		tmp = ConfigSubsection()
		tmp.voltage = ConfigSelection(advanced_voltage_choices, "polarization")
		tmp.tonemode = ConfigSelection(advanced_tonemode_choices, "band")
		tmp.usals = ConfigYesNo(True)
		tmp.rotorposition = ConfigInteger(default=1, limits=(1, 255))
		lnb = ConfigSelection(advanced_lnb_choices, "0")
		lnb.slot_id = slot_id
		lnb.addNotifier(configLNBChanged, initial_call = False)
		tmp.lnb = lnb
		return tmp

	def hdsCompleteazaSatelitiAvansati():
		"""Dupa o reincarcare a satellites.xml cu pozitii noi (o lista de canale trimisa de pe PC si /web/servicelistreload?
		mode=3, HdsWebControl/aplicatii_web.py) fiecare tuner cu setari avansate primeste intrarea pozitiilor noi, ca Setari
		tuner (VERDE) si SecConfigure.updateAdvanced sa nu mai cada cu KeyError (asistenta 866218, Ustym 4K PRO, 14.11.2026:
		2310 = 129.0W din satellites.xml-ul adus de pe PC). Valorile scrise in settings pentru ele se iau ca la pornire.
		Intoarce cate intrari s-au adaugat."""
		# TNB: satelitii pastrati la pornire (salvati la tunere, lipsa din satellites.xml) se pun la loc dupa recitire
		hdsPunePozitiilePastrate(nimmgr)
		adaugate = 0
		for slot_id in range(len(nimmgr.nim_slots)):
			try:
				avansat = config.Nims[slot_id].advanced
			except Exception:
				continue
			if isinstance(avansat, ConfigNothing) or not hasattr(avansat, "sat"):
				continue
			for x in nimmgr.satList:
				if x[0] not in avansat.sat:
					avansat.sat[x[0]] = hdsSatAvansat(slot_id)
					adaugate += 1
		if adaugate:
			print("[NimManager] %d intrari noi in setarile avansate ale tunerelor (sateliti noi in satellites.xml)" % adaugate)
		return adaugate

	nimmgr.hdsCompleteazaSatelitiAvansati = hdsCompleteazaSatelitiAvansati

	def configModeChanged(configMode):
		slot_id = configMode.slot_id
		nim = config.Nims[slot_id]
		if configMode.value == "advanced" and isinstance(nim.advanced, ConfigNothing):
			# advanced config:
			nim.advanced = ConfigSubsection()
			nim.advanced.sat = ConfigSubDict()
			nim.advanced.sats = getConfigSatlist(192, advanced_satlist_choices)
			nim.advanced.lnb = ConfigSubDict()
			nim.advanced.lnb[0] = ConfigNothing()
			for x in nimmgr.satList:
				nim.advanced.sat[x[0]] = hdsSatAvansat(slot_id)
			for x in range(3601, 3605):
				tmp = ConfigSubsection()
				tmp.voltage = ConfigSelection(advanced_voltage_choices, "polarization")
				tmp.tonemode = ConfigSelection(advanced_tonemode_choices, "band")
				tmp.usals = ConfigYesNo(default=True)
				tmp.rotorposition = ConfigInteger(default=1, limits=(1, 255))
				lnbnum = 33+x-3601
				lnb = ConfigSelection([("0", _("not available")), (str(lnbnum), "LNB %d"%(lnbnum))], "0")
				lnb.slot_id = slot_id
				lnb.addNotifier(configLNBChanged, initial_call = False)
				tmp.lnb = lnb
				nim.advanced.sat[x] = tmp

	def toneAmplitudeChanged(configElement):
		fe_id = configElement.fe_id
		slot_id = configElement.slot_id
		if nimmgr.nim_slots[slot_id].description == 'Alps BSBE2':
			open("/proc/stb/frontend/%d/tone_amplitude" %(fe_id), "w").write(configElement.value)

	def tunerTypeChanged(nimmgr, configElement):
		fe_id = configElement.fe_id

		from os import path
		mode_file = "/proc/stb/frontend/%d/mode" % (fe_id)
		if not path.exists(mode_file):
			print("tunerTypeChanged: no %s available, handled dynamically" % mode_file)
			return

		cur_type = int(open(mode_file, "r").read())
		if cur_type != int(configElement.value):
			print("tunerTypeChanged feid %d from %d to mode %d" % (fe_id, cur_type, int(configElement.value)))

			try:
				oldvalue = open("/sys/module/dvb_core/parameters/dvb_shutdown_timeout", "r").readline()
				open("/sys/module/dvb_core/parameters/dvb_shutdown_timeout", "w").write("0")
			except:
				print("[info] no /sys/module/dvb_core/parameters/dvb_shutdown_timeout available")

			try:
				channel = eDVBResourceManager.getInstance().allocateRawChannel(fe_id)
				frontend = channel.getFrontend() if channel is not None else None
				if frontend is None:
					raise RuntimeError(_("Tunerul este ocupat. Încearcă după oprirea înregistrării sau a redării."))
				frontend.closeFrontend()
				try:
					with open(mode_file, "w") as f:
						f.write(configElement.value)
					frontend.reopenFrontend()
				except Exception:
					try:
						with open(mode_file, "w") as f:
							f.write(str(cur_type))
					finally:
						frontend.reopenFrontend()
					raise
			finally:
				if "oldvalue" in locals():
					try:
						with open("/sys/module/dvb_core/parameters/dvb_shutdown_timeout", "w") as f:
							f.write(oldvalue)
					except OSError:
						print("[info] optional DVB shutdown timeout could not be restored")
			nimmgr.enumerateNIMs()
		else:
			print("tuner type is already already %d" %cur_type)

	empty_slots = 0
	for slot in nimmgr.nim_slots:
		x = slot.slot
		nim = config.Nims[x]
		addMultiType = False
		try:
			nim.multiType
		except:
			addMultiType = True
		if slot.isMultiType() and addMultiType:
			typeList = []
			for id in [*slot.getMultiTypeList().keys()]:
				type = slot.getMultiTypeList()[id]
				typeList.append((id, type))
			# HDSatelit: tunerele cu mai multe sisteme fara /proc/stb/frontend/N/mode (Dreambox DM920/DM900/DM7080 cu
			# Si2169C/D: DVB-C si DVB-T2 pe acelasi frontend, ales de nucleu dupa canal) nu au un mod de scris; "Type:" din
			# nim_sockets e numai sistemul folosit ultima data (la pornire DVB-C pe DM920, AS78). Alegerea din Setari tuner
			# da tipul tunerului, iar implicitul e tipul spus acum de driver, deci un tuner neatins de om ramane exact
			# cum era. O alegere scrisa deja ramane scrisa (save_forced): implicitul se muta cu driverul, iar o valoare
			# egala cu el s-ar sterge din settings la prima salvare. Placile cu fisierul mode raman neschimbate.
			from os import path
			dinamic = not path.exists("/proc/stb/frontend/%d/mode" % (x - empty_slots))
			implicit = "0"
			if dinamic:
				implicit = next((id for id, tip in typeList if tip == slot.type), None)
				dinamic = implicit is not None
				implicit = implicit or "0"
				# DMV6: "Type:" e sistemul folosit ultima data, deci se poate muta singur (DM900, AS106: tunerul A cu
				# satelitul pus in Setari a pornit odata ca DVB-T si si-a pierdut satelitul). Un tuner neatins de om, cu o
				# configurare de satelit salvata, ramane pe satelit; fara ea, tot dupa driver, ca pana acum.
				if (dinamic and "multiType" not in nim.content.stored_values
						and nim.content.stored_values.get("configMode") in HDS_MODURI_SATELIT):
					implicit = next((id for id, tip in typeList if tip in ("DVB-S2", "DVB-S")), implicit)
			nim.multiType = ConfigSelection(typeList, implicit)
			nim.multiType.hds_dinamic = dinamic
			if dinamic and "multiType" in nim.content.stored_values:
				nim.multiType.save_forced = True

			nim.multiType.fe_id = x - empty_slots
			nim.multiType.addNotifier(boundFunction(tunerTypeChanged, nimmgr))

	# HDSatelit: tipul tunerelor dinamice dupa alegerea omului (si dupa schimbarea ei, prin hdsAplicaTipTuner, care
	# reface configuratia), pe lista curenta de tunere, inainte de setarile fiecarui tip de mai jos
	for slot in nimmgr.nim_slots:
		try:
			element = config.Nims[slot.slot].multiType
		except (AttributeError, KeyError, IndexError):
			continue
		if getattr(element, "hds_dinamic", False) and element.value in slot.getMultiTypeList():
			slot.type = slot.getMultiTypeList()[element.value]

	# HDSatelit: primul tuner de satelit vine pornit, in modul simplu (DiSEqC A/B, satelitii dupa tara receptorului,
	# satelitiReceptorului), ca scanarea si canalele sa mearga din prima, fara "Setari tuner". Pana acum implicit era "nothing"
	# (nimic conectat) si nimic din imagine nu-l schimba (asistentul de la prima pornire nu atinge tunerele), deci pe
	# un receptor nou scanarea nu vedea niciun tuner de satelit. Ceilalti tuneri de satelit raman opriti pana ii
	# porneste omul: unul fara cablu, pornit, ar fi ales pentru inregistrari si n-ar prinde nimic. Ce a ales omul
	# ramane: o valoare diferita de cea implicita se scrie in settings, deci si "nothing" pe primul tuner (Satconfig
	# pastreaza implicitul de aici, configMode.default).
	primul_satelit = None
	for slot in nimmgr.nim_slots:
		if slot.isCompatible("DVB-S"):
			primul_satelit = slot.slot
			break

	empty_slots = 0
	for slot in nimmgr.nim_slots:
		x = slot.slot
		nim = config.Nims[x]

		if slot.isCompatible("DVB-S"):
			nim.toneAmplitude = ConfigSelection([("11", "340mV"), ("10", "360mV"), ("9", "600mV"), ("8", "700mV"), ("7", "800mV"), ("6", "900mV"), ("5", "1100mV")], "7")
			nim.toneAmplitude.fe_id = x - empty_slots
			nim.toneAmplitude.slot_id = x
			nim.toneAmplitude.addNotifier(toneAmplitudeChanged)
			nim.diseqc13V = ConfigYesNo(False)
			nim.diseqcMode = ConfigSelection(diseqc_mode_choices, "diseqc_a_b")
			nim.connectedTo = ConfigSelection([(str(id), nimmgr.getNimDescription(id)) for id in nimmgr.getNimListOfType("DVB-S") if id != x],
				hdsLegaturaImplicita(nimmgr, slot))
			nim.simpleSingleSendDiSEqC = ConfigYesNo(False)
			nim.simpleDiSEqCSetVoltageTone = ConfigYesNo(True)
			nim.simpleDiSEqCOnlyOnSatChange = ConfigYesNo(False)
			# primul tuner de satelit, inca neconfigurat (settings fara configMode-ul lui: receptor nou): satelitii dupa
			# tara receptorului, scrisi in settings (mai jos, dupa configMode). Configurat deja:
			# implicitele de dinainte, ca un receptor care le folosea fara sa le fi scris sa ramana cum era.
			proaspat = x == primul_satelit and "configMode" not in nim.content.stored_values
			implicit_a, implicit_b = satelitiReceptorului(diseqc_satlist_choices) if proaspat else SATELITI_IMPLICITI
			nim.diseqcA = getConfigSatlist(implicit_a, diseqc_satlist_choices)
			nim.diseqcB = getConfigSatlist(implicit_b, diseqc_satlist_choices)
			if proaspat:
				nim.diseqcA.save_forced = nim.diseqcB.save_forced = True
				try:
					from Components.Language import language
					language.addCallback(boundFunction(_taraSchimbata, x, [implicit_a, implicit_b]))
				except Exception as e:
					print("[NimManager] limba: %s" % e)
			nim.diseqcC = ConfigSatlist(list = diseqc_satlist_choices)
			nim.diseqcD = ConfigSatlist(list = diseqc_satlist_choices)
			nim.positionerMode = ConfigSelection(positioner_mode_choices, "usals")
			# locul antenei: implicitul e neutru (pana la 0.2.4 era 45,300 N / 23,270 E, folosit tacut de USALS); valorile le
			# scrie numai Components/HdsLocul.py, din locul unic, iar migrarea pastreaza vechile valori unde era motor
			nim.longitude = ConfigFloat(default=[0,0], limits=[(0,359),(0,999)])
			nim.longitudeOrientation = ConfigSelection(longitude_orientation_choices, "east")
			nim.latitude = ConfigFloat(default=[0,0], limits=[(0,359),(0,999)])
			nim.latitudeOrientation = ConfigSelection(latitude_orientation_choices, "north")
			nim.powerMeasurement = ConfigYesNo(True)
			nim.powerThreshold = ConfigInteger(default=hw.get_device_name() == "dm8000" and 15 or 50, limits=(0, 100))
			nim.turningSpeed = ConfigSelection(turning_speed_choices, "fast")
			btime = datetime(1970, 1, 1, 7, 0);
			nim.fastTurningBegin = ConfigDateTime(default = mktime(btime.timetuple()), formatstring = _("%H:%M"), increment = 900)
			etime = datetime(1970, 1, 1, 19, 0);
			nim.fastTurningEnd = ConfigDateTime(default = mktime(etime.timetuple()), formatstring = _("%H:%M"), increment = 900)
			config_mode_choices = [ ("nothing", _("nothing connected")),
				("simple", _("simple")), ("advanced", _("advanced"))]
			if len(nimmgr.getNimListOfType(slot.type, exception = x)) > 0:
				config_mode_choices.append(("equal", _("equal to")))
				config_mode_choices.append(("satposdepends", _("second cable of motorized LNB")))
			if len(nimmgr.canConnectTo(x)) > 0:
				config_mode_choices.append(("loopthrough", _("loopthrough to")))
			nim.advanced = ConfigNothing()
			tmp = ConfigSelection(config_mode_choices, "simple" if x == primul_satelit else "nothing")
			# pe primul tuner modul se scrie mereu in settings, si cand e cel implicit: settings ramane ca pana acum
			# (config.Nims.0.configMode=simple), iar o copie sau o versiune mai veche, cu implicitul "nothing", il
			# citeste la fel
			tmp.save_forced = x == primul_satelit
			tmp.slot_id = x
			tmp.addNotifier(configModeChanged, initial_call = False)
			nim.configMode = tmp
			# tunerul B porneste singur daca are semnal (Components/HdsTunerB.py): starea probei automate
			# ("" neprobat, "jumatate" prins o data, "pornit", "esuat"), transponderul primei probe si semnul
			# ca omul a salvat el ceva pentru tuner (atunci proba nu-l mai atinge)
			nim.hdsAuto = ConfigText(default = "", fixed_size = False)
			nim.hdsTpProba = ConfigText(default = "", fixed_size = False)
			nim.hdsAlesDeOm = ConfigYesNo(False)
			if proaspat:
				# receptor nou: modul si satelitii intra in settings la prima scriere (oprirea interfetei, orice
				# setare salvata), deci la pornirea urmatoare tunerul nu mai e "nou" si satelitii nu se mai muta
				tmp.save()
				nim.diseqcA.save()
				nim.diseqcB.save()
		elif slot.isCompatible("DVB-C") or slot.isCompatible("DVB-T"):
			nim.configMode = ConfigSelection(
				choices = {
					"enabled": _("enabled"),
					"nothing": _("nothing connected"),
					},
				default = "enabled")
			if slot.isCompatible("DVB-C"):
				# HDSatelit: nu „list”: numele facea din list o variabila a lui InitNimManager, iar fillUnicableConf
				# (list(...) de mai sus) dadea NameError la pornire cu Unicable pe un LNB, deci enigma2 nu mai pornea.
				furnizori_cablu = [ ]
				n = 0
				for x in nimmgr.cablesList:
					furnizori_cablu.append((str(n), x[0]))
					n += 1
				nim.cable = ConfigSubsection()
				possible_scan_types = [("bands", _("Frequency bands")), ("steps", _("Frequency steps"))]
				if n:
					possible_scan_types.append(("provider", _("Provider")))
					nim.cable.scan_provider = ConfigSelection(default = "0", choices = furnizori_cablu)
				nim.cable.scan_type = ConfigSelection(default = "bands", choices = possible_scan_types)
				nim.cable.scan_band_EU_VHF_I = ConfigYesNo(default = True)
				nim.cable.scan_band_EU_MID = ConfigYesNo(default = True)
				nim.cable.scan_band_EU_VHF_III = ConfigYesNo(default = True)
				nim.cable.scan_band_EU_UHF_IV = ConfigYesNo(default = True)
				nim.cable.scan_band_EU_UHF_V = ConfigYesNo(default = True)
				nim.cable.scan_band_EU_SUPER = ConfigYesNo(default = True)
				nim.cable.scan_band_EU_HYPER = ConfigYesNo(default = True)
				nim.cable.scan_band_US_LOW = ConfigYesNo(default = False)
				nim.cable.scan_band_US_MID = ConfigYesNo(default = False)
				nim.cable.scan_band_US_HIGH = ConfigYesNo(default = False)
				nim.cable.scan_band_US_SUPER = ConfigYesNo(default = False)
				nim.cable.scan_band_US_HYPER = ConfigYesNo(default = False)
				nim.cable.scan_frequency_steps = ConfigInteger(default = 1000, limits = (1000, 10000))
				nim.cable.scan_mod_qam16 = ConfigYesNo(default = False)
				nim.cable.scan_mod_qam32 = ConfigYesNo(default = False)
				nim.cable.scan_mod_qam64 = ConfigYesNo(default = True)
				nim.cable.scan_mod_qam128 = ConfigYesNo(default = False)
				nim.cable.scan_mod_qam256 = ConfigYesNo(default = True)
				nim.cable.scan_sr_6900 = ConfigYesNo(default = True)
				nim.cable.scan_sr_6875 = ConfigYesNo(default = True)
				nim.cable.scan_sr_ext1 = ConfigInteger(default = 0, limits = (0, 7230))
				nim.cable.scan_sr_ext2 = ConfigInteger(default = 0, limits = (0, 7230))
			if slot.isCompatible("DVB-T"):
				regiuni_terestru = []
				n = 0
				for x in nimmgr.terrestrialsList:
					regiuni_terestru.append((str(n), x[0]))
					n += 1
				nim.terrestrial = ConfigSelection(choices = regiuni_terestru)
				nim.terrestrial_5V = ConfigOnOff()
			if slot.isCompatible("DVB-C") and slot.isCompatible("DVB-T"):
				# tunerul combinat (DVB-T2/C, o singura intrare): omul spune ce e legat la el, iar ecranul tunerului arata
				# setarile potrivite. Tunerul ramane bun pentru amandoua (scanarea, acordarea), deci nimic altceva nu
				# depinde de alegere. Implicit: ce are lista de canale (felCombinatImplicit).
				nim.hds_fel = ConfigSelection(choices = [
					("terestru", _("Antenă terestră (DVB-T/T2)")),
					("cablu", _("Cablu (DVB-C)"))],
					default = felCombinatImplicit())
				# Implicitul se poate schimba dupa scanare. Alegerea salvata ramane.
				nim.hds_fel.save_forced = True
		else:
			empty_slots += 1
			nim.configMode = ConfigSelection(choices = { "nothing": _("disabled") }, default="nothing");
			if slot.type is not None:
				print("pls add support for this frontend type!", slot.type)
#			assert False

	# locul antenei (motorul USALS): migrarea de o data, locul luat din coordonatele scrise ale unui tuner, copiile fara
	# chei; inainte de SecConfigure, care il citeste (Components/HdsLocul.py)
	try:
		from Components import HdsLocul
		HdsLocul.laPornire()
	except Exception as e:
		print("[NimManager] locul antenei: %r" % (e,))

	preferinta_noua = ("usage" not in config.content.items
		or "frontend_priority" not in config.usage.content.items)
	hdsConfigTunerPreferat(nimmgr)
	if preferinta_noua:
		hdsAplicaTunerPreferat()
	nimmgr.sec = SecConfigure(nimmgr)

nimmanager = NimManager()
# acelasi obiect, cu numele cerut de pluginurile straine (FastScan: from Components.NimManager import nimManager)
nimManager = nimmanager
