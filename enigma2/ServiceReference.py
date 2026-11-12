from enigma import eServiceReference, eServiceCenter

class ServiceReference(eServiceReference):
	def __init__(self, ref):
		if not isinstance(ref, eServiceReference):
			self.ref = eServiceReference(ref or "")
		else:
			self.ref = ref
		self.serviceHandler = eServiceCenter.getInstance()

	def __str__(self):
		return self.ref.toString()

	def toString(self):
		return self.ref.toString()

	def getServiceName(self):
		info = self.info()
		return info and info.getName(self.ref) or ""

	def info(self):
		return self.serviceHandler.info(self.ref)

	def list(self):
		return self.serviceHandler.list(self.ref)

	def getType(self):
		return self.ref.type

	def getPath(self):
		return self.ref.getPath()

	def getFlags(self):
		return self.ref.flags

	def isRecordable(self):
		ref = self.ref
		return ref.flags & eServiceReference.isGroup or (ref.type == eServiceReference.idDVB and ref.getPath() == "")

# numele cerute de pluginuri
service_types_tv_ref = eServiceReference('1:7:1:0:0:0:0:0:0:0:(type == 1) || (type == 17) || (type == 22) || (type == 25) || (type == 31) || (type == 134) || (type == 195)')
service_types_radio_ref = eServiceReference('1:7:2:0:0:0:0:0:0:0:(type == 2) || (type == 10)')


def isPlayableForCur(serviceref):
	info = eServiceCenter.getInstance().info(serviceref)
	return info and info.isPlayable(serviceref, eServiceReference())


def serviceRefAppendPath(sref, path):
	if not isinstance(sref, str):
		sref = sref.toString()
	return sref + path


def getPlayingref(ref):
	from NavigationInstance import instance
	playing = eServiceReference()
	if instance:
		playing = instance.getCurrentlyPlayingServiceOrGroup() or eServiceReference()
	return playing


# Numele OE-Alliance cerute de teme si pluginuri (lotul TOT, 12.11.2026; dupa sursele GPL enigma2 OE-Alliance, commitul
# 29d951a6ec2e, ServiceReference.py): resolveAlternate (13 teme: Aglare, Insprion80, popking159...), makeServiceQueryStr,
# isRadioServiceReference (convertorul ExtremeInfo).
def resolveAlternate(ref):
	"""Pentru o alternativa (grup), canalul care se poate reda acum; altfel None."""
	from enigma import getBestPlayableServiceReference
	nref = None
	if ref.flags & eServiceReference.isGroup:
		nref = getBestPlayableServiceReference(ref, getPlayingref(ref))
		if not nref:
			nref = getBestPlayableServiceReference(ref, eServiceReference(), True)
	return nref


def makeServiceQueryStr(serviceTypes):
	return " || ".join(["(type == %d)" % x for x in serviceTypes])


def isRadioServiceReference(ref):
	"""True cand ref e un canal de radio (DVB radio, radio AVC sau DAB)."""
	if not isinstance(ref, eServiceReference):
		ref = eServiceReference(ref or "")
	if not ref.valid():
		return False
	if ref.type == getattr(eServiceReference, "idServiceDAB", -1):
		return True
	return ref.getUnsignedData(0) in (2, 10)  # dRadio, dRadioAvc
