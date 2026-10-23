# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.config import config, ConfigSubsection, ConfigSelection, ConfigPIN, ConfigText, ConfigYesNo, ConfigSubList, ConfigInteger
#from Screens.ChannelSelection import service_types_tv
from Screens.InputBox import PinInput
from Screens.MessageBox import MessageBox
from Tools.BoundFunction import boundFunction
from ServiceReference import ServiceReference
from Tools import Notifications
from Tools.Directories import resolveFilename, SCOPE_CONFIG
from enigma import eTimer
import os
import time

TYPE_SERVICE = "SERVICE"
TYPE_BOUQUETSERVICE = "BOUQUETSERVICE"
TYPE_BOUQUET = "BOUQUET"
LIST_BLACKLIST = "blacklist"
LIST_WHITELIST = "whitelist"

IMG_WHITESERVICE = LIST_WHITELIST + "-" + TYPE_SERVICE
IMG_WHITEBOUQUET = LIST_WHITELIST + "-" + TYPE_BOUQUET
IMG_BLACKSERVICE = LIST_BLACKLIST + "-" + TYPE_SERVICE
IMG_BLACKBOUQUET = LIST_BLACKLIST + "-" + TYPE_BOUQUET

def InitParentalControl():
	global parentalControl
	parentalControl = ParentalControl()
	config.ParentalControl = ConfigSubsection()
	config.ParentalControl.configured = ConfigYesNo(default = False)
	config.ParentalControl.mode = ConfigSelection(default = "simple", choices = [("simple", _("simple")), ("complex", _("complex"))])
	config.ParentalControl.storeservicepin = ConfigSelection(default = "never", choices = [("never", _("never")), ("5", _("5 minutes")), ("30", _("30 minutes")), ("60", _("60 minutes")), ("standby", _("until standby/restart"))])
	config.ParentalControl.storeservicepincancel = ConfigSelection(default = "never", choices = [("never", _("never")), ("5", _("5 minutes")), ("30", _("30 minutes")), ("60", _("60 minutes")), ("standby", _("until standby/restart"))])
	config.ParentalControl.servicepinactive = ConfigYesNo(default = False)
	config.ParentalControl.setuppinactive = ConfigYesNo(default = False)
	config.ParentalControl.type = ConfigSelection(default = "blacklist", choices = [(LIST_WHITELIST, _("whitelist")), (LIST_BLACKLIST, _("blacklist"))])
	config.ParentalControl.setuppin = ConfigPIN(default = -1)
	
	config.ParentalControl.retries = ConfigSubsection()
	config.ParentalControl.retries.setuppin = ConfigSubsection()
	config.ParentalControl.retries.setuppin.tries = ConfigInteger(default = 3)
	config.ParentalControl.retries.setuppin.time = ConfigInteger(default = 3)	
	config.ParentalControl.retries.servicepin = ConfigSubsection()
	config.ParentalControl.retries.servicepin.tries = ConfigInteger(default = 3)
	config.ParentalControl.retries.servicepin.time = ConfigInteger(default = 3)
#	config.ParentalControl.configured = configElement("config.ParentalControl.configured", configSelection, 1, (("yes", _("yes")), ("no", _("no"))))
	#config.ParentalControl.mode = configElement("config.ParentalControl.mode", configSelection, 0, (("simple", _("simple")), ("complex", _("complex"))))
	#config.ParentalControl.storeservicepin = configElement("config.ParentalControl.storeservicepin", configSelection, 0, (("never", _("never")), ("5_minutes", _("5 minutes")), ("30_minutes", _("30 minutes")), ("60_minutes", _("60 minutes")), ("restart", _("until restart"))))
	#config.ParentalControl.servicepinactive = configElement("config.ParentalControl.servicepinactive", configSelection, 1, (("yes", _("yes")), ("no", _("no"))))
	#config.ParentalControl.setuppinactive = configElement("config.ParentalControl.setuppinactive", configSelection, 1, (("yes", _("yes")), ("no", _("no"))))
	#config.ParentalControl.type = configElement("config.ParentalControl.type", configSelection, 0, (("whitelist", _("whitelist")), ("blacklist", _("blacklist"))))
	#config.ParentalControl.setuppin = configElement("config.ParentalControl.setuppin", configSequence, "0000", configSequenceArg().get("PINCODE", (4, "")))

	config.ParentalControl.servicepin = ConfigSubList()

	for i in (0, 1, 2):
		config.ParentalControl.servicepin.append(ConfigPIN(default = -1))
		#config.ParentalControl.servicepin.append(configElement("config.ParentalControl.servicepin.level" + str(i), configSequence, "0000", configSequenceArg().get("PINCODE", (4, ""))))

class ParentalControl:
	def __init__(self):
		#Do not call open on init, because bouquets are not ready at that moment 
		self.open()
		self.serviceLevel = {}
		#Instead: Use Flags to see, if we already initialized config and called open
		self.configInitialized = False
		#This is the timer that is used to see, if the time for caching the pin is over
		#Of course we could also work without a timer and compare the times every
		#time we call isServicePlayable. But this might probably slow down zapping, 
		#That's why I decided to use a timer
		self.sessionPinTimer = eTimer()
		self.sessionPinTimer.callback.append(self.resetSessionPin)
	
	def serviceMethodWrapper(self, service, method, *args):
		#This method is used to call all functions that need a service as Parameter: 
		#It takes either a Service- Reference or a Bouquet- Reference and passes 
		#Either the service or all services contained in the bouquet to the method given
		#That way all other functions do not need to distinguish between service and bouquet. 
		if "FROM BOUQUET" in service:
			method( service , TYPE_BOUQUET , *args )
			servicelist = self.readServicesFromBouquet(service,"C")
			for ref in servicelist:
				sRef = str(ref[0])
				method( sRef , TYPE_BOUQUETSERVICE , *args )
		else:
			ref = ServiceReference(service)
			sRef = str(ref)
			method( sRef , TYPE_SERVICE , *args )
	
	def setServiceLevel(self, service, type, level):
		self.serviceLevel[service] = level

	def isServicePlayable(self, ref, callback):
		if not config.ParentalControl.configured.value or not config.ParentalControl.servicepinactive.value:
			return True
		#Check if configuration has already been read or if the significant values have changed.
		#If true: read the configuration 
		if self.configInitialized == False or self.storeServicePin != config.ParentalControl.storeservicepin.value or self.storeServicePinCancel != config.ParentalControl.storeservicepincancel.value:
			self.getConfigValues()
		service = ref.toCompareString()
		if (config.ParentalControl.type.value == LIST_WHITELIST and service not in self.whitelist) or (config.ParentalControl.type.value == LIST_BLACKLIST and service in self.blacklist):
			#Check if the session pin is cached and return the cached value, if it is.
			if self.sessionPinCached == True:
				#As we can cache successful pin- entries as well as canceled pin- entries,
				#We give back the last action 
				return self.sessionPinCachedValue
			self.callback = callback
			#Someone started to implement different levels of protection. Seems they were never completed
			#I did not throw out this code, although it is of no use at the moment
			levelNeeded = 0
			if service in self.serviceLevel:
				levelNeeded = self.serviceLevel[service]
			pinList = self.getPinList()[:levelNeeded + 1]
			Notifications.AddNotificationWithCallback(boundFunction(self.servicePinEntered, ref), PinInput, triesEntry = config.ParentalControl.retries.servicepin, pinList = pinList, service = ServiceReference(ref).getServiceName(), title = _("this service is protected by a parental control pin"), windowTitle = _("Parental control"))
			return False
		else:
			return True
		
	def protectService(self, service):
		if config.ParentalControl.type.value == LIST_WHITELIST:
			if service in self.whitelist:
				self.serviceMethodWrapper(service, self.removeServiceFromList, self.whitelist)
				#self.deleteWhitelistService(service)
		else: # blacklist
			if service not in self.blacklist:
				self.serviceMethodWrapper(service, self.addServiceToList, self.blacklist)
				#self.addBlacklistService(service)
		#print "whitelist:", self.whitelist
		#print "blacklist:", self.blacklist

	def unProtectService(self, service):
		#print "unprotect"
		#print "config.ParentalControl.type.value:", config.ParentalControl.type.value
		if config.ParentalControl.type.value == LIST_WHITELIST:
			if service not in self.whitelist:
				self.serviceMethodWrapper(service, self.addServiceToList, self.whitelist)
				#self.addWhitelistService(service)
		else: # blacklist
			if service in self.blacklist:
				self.serviceMethodWrapper(service, self.removeServiceFromList, self.blacklist)
				#self.deleteBlacklistService(service)
		#print "whitelist:", self.whitelist
		#print "blacklist:", self.blacklist

	def getProtectionLevel(self, service):
		if (config.ParentalControl.type.value == LIST_WHITELIST and service not in self.whitelist) or (config.ParentalControl.type.value == LIST_BLACKLIST and service in self.blacklist):
			if service in self.serviceLevel:
				return self.serviceLevel[service]
			else:
				return 0
		else:
			return -1

	def getProtectionType(self, service):
		#New method used in ParentalControlList: This method does not only return
		#if a service is protected or not, it also returns, why (whitelist or blacklist, service or bouquet)
		sImage = ""
		if (config.ParentalControl.type.value == LIST_WHITELIST):
			if service in self.whitelist:
				if TYPE_SERVICE in self.whitelist[service]:
					sImage = IMG_WHITESERVICE
				else:
					sImage = IMG_WHITEBOUQUET
		elif (config.ParentalControl.type.value == LIST_BLACKLIST):
			if service in self.blacklist:
				if TYPE_SERVICE in self.blacklist[service]:
					sImage = IMG_BLACKSERVICE
				else:
					sImage = IMG_BLACKBOUQUET
		bLocked = self.getProtectionLevel(service) != -1
		return (bLocked,sImage)
	
	def getConfigValues(self):	
		#Read all values from configuration 
		self.checkPinInterval = False
		self.checkPinIntervalCancel = False
		self.checkSessionPin = False
		self.checkSessionPinCancel = False
		
		self.sessionPinCached = False
		self.pinIntervalSeconds = 0
		self.pinIntervalSecondsCancel = 0

		self.storeServicePin = config.ParentalControl.storeservicepin.value
		self.storeServicePinCancel = config.ParentalControl.storeservicepincancel.value
		
		if self.storeServicePin == "never":
			pass
		elif self.storeServicePin == "standby":
			self.checkSessionPin = True
		else:
			self.checkPinInterval = True
			iMinutes = float(self.storeServicePin)
			iSeconds = iMinutes*60
			self.pinIntervalSeconds = iSeconds
	
		if self.storeServicePinCancel == "never":
			pass
		elif self.storeServicePinCancel == "standby":
			self.checkSessionPinCancel = True
		else:
			self.checkPinIntervalCancel = True
			iMinutes = float(self.storeServicePinCancel)
			iSeconds = iMinutes*60
			self.pinIntervalSecondsCancel = iSeconds
	
		self.configInitialized = True
		# Reset PIN cache on standby: Use StandbyCounter- Config- Callback
		config.misc.standbyCounter.addNotifier(self.standbyCounterCallback, initial_call = False)

	def standbyCounterCallback(self, configElement):
		self.resetSessionPin()
		
	def resetSessionPin(self):
		#Reset the session pin, stop the timer
		self.sessionPinCached = False
		self.sessionPinTimer.stop()

	def getCurrentTimeStamp(self):
		return time.time()

	def getPinList(self):
		return [ x.value for x in config.ParentalControl.servicepin ]
		
	def servicePinEntered(self, service, result):

		if result is not None and result:
			#This is the new function of caching the service pin
			#save last session and time of last entered pin...
			if self.checkSessionPin == True:
				self.sessionPinCached = True
				self.sessionPinCachedValue = True
			if self.checkPinInterval == True:
				self.sessionPinCached = True
				self.sessionPinCachedValue = True
				self.sessionPinTimer.start(self.pinIntervalSeconds*1000,1)
			self.callback(ref = service)
		else:
			#This is the new function of caching cancelling of service pin
			if result is not None:
				Notifications.AddNotification(MessageBox,  _("The pin code you entered is wrong."), MessageBox.TYPE_ERROR)
			else:
				if self.checkSessionPinCancel == True:
					self.sessionPinCached = True
					self.sessionPinCachedValue = False
				if self.checkPinIntervalCancel == True:
					self.sessionPinCached = True
					self.sessionPinCachedValue = False
					self.sessionPinTimer.start(self.pinIntervalSecondsCancel*1000,1) 
			
	def saveListToFile(self,sWhichList):
		#Replaces saveWhiteList and saveBlackList: 
		#I don't like to have two functions with identical code...
		if sWhichList == LIST_BLACKLIST:
			vList = self.blacklist
		else:
			vList = self.whitelist
		#Only Services that are selected directly and Bouqets are saved.
		#Services that are added by a bouquet are not saved.
		#This is the reason for the change in self.whitelist and self.blacklist
		path = resolveFilename(SCOPE_CONFIG, sWhichList)
		text = "".join(str(sService) + "\n" for sService, sType in vList.items()
			if TYPE_SERVICE in sType or TYPE_BOUQUET in sType)
		#written to a temporary file and moved over the old one: a full disk or a crash
		#while writing can no longer leave a half written list behind
		tmp = path + ".writing"
		try:
			#O_BINARY only exists on Windows (the test machine); on the receiver getattr returns 0
			fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
			try:
				os.write(fd, text.encode("utf-8"))
				os.fsync(fd)
			finally:
				os.close(fd)
			os.replace(tmp, path)
		except (IOError, OSError) as err:
			print("[ParentalControl] writing %s failed: %s" % (path, getattr(err, "strerror", None) or err))
			try:
				os.unlink(tmp)
			except OSError:
				pass

	def openListFromFile(self,sWhichList):
		#Replaces openWhiteList and openBlackList: 
		#I don't like to have two functions with identical code...
		if sWhichList == LIST_BLACKLIST:
			self.blacklist = {}
			vList = self.blacklist
		else:
			self.whitelist = {}
			vList = self.whitelist
		try:
			with open(resolveFilename(SCOPE_CONFIG, sWhichList ), 'r', encoding="utf-8") as file:
				lines = file.readlines()
			for x in lines:
				sPlain = x.strip()
				self.serviceMethodWrapper(sPlain, self.addServiceToList, vList)
		except:
			pass
	
	def addServiceToList(self, service, type, vList):
		#Replaces addWhitelistService and addBlacklistService
		#The lists are not only lists of service references any more. 
		#They are named lists with the service as key and an array of types as value:
		
		if service in vList:
			if not type in vList[service]:
				vList[service].append(type)
		else:
			vList[service] = [type]
	
	def removeServiceFromList(self, service, type, vList):
		#Replaces deleteWhitelistService and deleteBlacklistService
		if service in vList:
			if type in vList[service]:
				vList[service].remove(type)
			if not vList[service]:
				del vList[service]
		if service in self.serviceLevel:
			self.serviceLevel.remove(service)
		
	def readServicesFromBouquet(self,sBouquetSelection,formatstring):
		#This method gives back a list of services for a given bouquet
		from enigma import eServiceCenter, eServiceReference
		from Screens.ChannelSelection import service_types_tv
		serviceHandler = eServiceCenter.getInstance()
		refstr = sBouquetSelection
		root = eServiceReference(refstr)
		list = serviceHandler.list(root)
		if list is not None:
			services = list.getContent("CN", True) #(servicecomparestring, name)
			return services
		
	def save(self):
		# we need to open the files in case we havent's read them yet
		self.saveListToFile(LIST_BLACKLIST)
		self.saveListToFile(LIST_WHITELIST)
		
	def open(self):
		self.openListFromFile(LIST_BLACKLIST)
		self.openListFromFile(LIST_WHITELIST)

