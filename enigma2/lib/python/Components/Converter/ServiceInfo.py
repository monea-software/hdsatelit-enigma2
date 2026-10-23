# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Converter.Converter import Converter
from enigma import iServiceInformation, iPlayableService
from Components.Element import cached

class ServiceInfo(Converter, object):
	HAS_TELETEXT = 0
	IS_MULTICHANNEL = 1
	IS_CRYPTED = 2
	IS_WIDESCREEN = 3
	SUBSERVICES_AVAILABLE = 4
	XRES = 5
	YRES = 6
	APID = 7
	VPID = 8
	PCRPID = 9
	PMTPID = 10
	TXTPID = 11
	TSID = 12
	ONID = 13
	SID = 14
	FRAMERATE = 15
	TRANSFERBPS = 16
	IS_HDR = 17
	IS_HDR10 = 18
	IS_HLG = 19
	IS_SDR = 20


	def __init__(self, type):
		Converter.__init__(self, type)
		# gama imaginii (sGamma, evVideoGammaChanged): cu getattr, ca un binar enigma2 mai vechi sa nu opreasca skinul
		gamma_ev = getattr(iPlayableService, "evVideoGammaChanged", iPlayableService.evVideoSizeChanged)
		self.type, self.interesting_events = {
				"HasTelext": (self.HAS_TELETEXT, (iPlayableService.evUpdatedInfo,)),
				"IsMultichannel": (self.IS_MULTICHANNEL, (iPlayableService.evUpdatedInfo,)),
				"IsCrypted": (self.IS_CRYPTED, (iPlayableService.evUpdatedInfo,)),
				"IsWidescreen": (self.IS_WIDESCREEN, (iPlayableService.evVideoSizeChanged,)),
				"SubservicesAvailable": (self.SUBSERVICES_AVAILABLE, (iPlayableService.evUpdatedEventInfo,)),
				"VideoWidth": (self.XRES, (iPlayableService.evVideoSizeChanged,)),
				"VideoHeight": (self.YRES, (iPlayableService.evVideoSizeChanged,)),
				"AudioPid": (self.APID, (iPlayableService.evUpdatedInfo,)),
				"VideoPid": (self.VPID, (iPlayableService.evUpdatedInfo,)),
				"PcrPid": (self.PCRPID, (iPlayableService.evUpdatedInfo,)),
				"PmtPid": (self.PMTPID, (iPlayableService.evUpdatedInfo,)),
				"TxtPid": (self.TXTPID, (iPlayableService.evUpdatedInfo,)),
				"TsId": (self.TSID, (iPlayableService.evUpdatedInfo,)),
				"OnId": (self.ONID, (iPlayableService.evUpdatedInfo,)),
				"Sid": (self.SID, (iPlayableService.evUpdatedInfo,)),
				"Framerate": (self.FRAMERATE, (iPlayableService.evVideoSizeChanged,iPlayableService.evUpdatedInfo,)),
				"TransferBPS": (self.TRANSFERBPS, (iPlayableService.evUpdatedInfo,)),
				# numele si evenimentele dupa enigma2 (GPLv2)
				"IsHDR": (self.IS_HDR, (iPlayableService.evVideoSizeChanged, gamma_ev)),
				"IsHDR10": (self.IS_HDR10, (iPlayableService.evVideoSizeChanged, gamma_ev)),
				"IsHLG": (self.IS_HLG, (iPlayableService.evVideoSizeChanged, gamma_ev)),
				"IsSDR": (self.IS_SDR, (iPlayableService.evVideoSizeChanged, gamma_ev)),
			}[type]

	def getServiceInfoString(self, info, what, convert = lambda x: "%d" % x):
		v = info.getInfo(what)
		if v == -1:
			return "N/A"
		if v == -2:
			return info.getInfoString(what)
		return convert(v)

	@cached
	def getBoolean(self):
		service = self.source.service
		info = service and service.info()
		if not info:
			return False
		
		if self.type == self.HAS_TELETEXT:
			tpid = info.getInfo(iServiceInformation.sTXTPID)
			return tpid != -1
		elif self.type == self.IS_MULTICHANNEL:
			# FIXME. but currently iAudioTrackInfo doesn't provide more information.
			audio = service.audioTracks()
			if audio:
				n = audio.getNumberOfTracks()
				idx = 0
				while idx < n:
					i = audio.getTrackInfo(idx)
					description = i.getDescription();
					if "AC3" in description or "DTS" in description:
						return True
					idx += 1
			return False
		elif self.type == self.IS_CRYPTED:
			return info.getInfo(iServiceInformation.sIsCrypted) == 1
		elif self.type == self.IS_WIDESCREEN:
			return info.getInfo(iServiceInformation.sAspect) in (3, 4, 7, 8, 0xB, 0xC, 0xF, 0x10)
		elif self.type == self.SUBSERVICES_AVAILABLE:
			subservices = service.subServices()
			return subservices and subservices.getNumberOfSubservices() > 0
		elif self.type in (self.IS_HDR, self.IS_HDR10, self.IS_HLG, self.IS_SDR):
			# conditiile dupa enigma2 (GPLv2; numai imagine UHD, ca skinurile
			# facute pentru alte imagini sa arate aceeasi sigla); gama: 0 SDR, 1 HDR, 2 HDR10, 3 HLG, -1 necunoscuta
			s_gamma = getattr(iServiceInformation, "sGamma", None)
			gamma = info.getInfo(s_gamma) if s_gamma is not None else -1
			width = info.getInfo(iServiceInformation.sVideoWidth)
			if not (2160 < width <= 3840):
				return False
			if self.type == self.IS_HDR:
				return gamma == 1
			if self.type == self.IS_HDR10:
				return gamma == 2
			if self.type == self.IS_HLG:
				return gamma == 3
			return gamma < 1

	boolean = property(getBoolean)
	
	@cached
	def getText(self):
		service = self.source.service
		info = service and service.info()
		if not info:
			return ""

		if self.type == self.XRES:
			return self.getServiceInfoString(info, iServiceInformation.sVideoWidth)
		elif self.type == self.YRES:
			return self.getServiceInfoString(info, iServiceInformation.sVideoHeight)
		elif self.type == self.APID:
			return self.getServiceInfoString(info, iServiceInformation.sAudioPID)
		elif self.type == self.VPID:
			return self.getServiceInfoString(info, iServiceInformation.sVideoPID)
		elif self.type == self.PCRPID:
			return self.getServiceInfoString(info, iServiceInformation.sPCRPID)
		elif self.type == self.PMTPID:
			return self.getServiceInfoString(info, iServiceInformation.sPMTPID)
		elif self.type == self.TXTPID:
			return self.getServiceInfoString(info, iServiceInformation.sTXTPID)
		elif self.type == self.TSID:
			return self.getServiceInfoString(info, iServiceInformation.sTSID)
		elif self.type == self.ONID:
			return self.getServiceInfoString(info, iServiceInformation.sONID)
		elif self.type == self.SID:
			return self.getServiceInfoString(info, iServiceInformation.sSID)
		elif self.type == self.FRAMERATE:
			return self.getServiceInfoString(info, iServiceInformation.sFrameRate, lambda x: "%d fps" % ((x+500)//1000))
		elif self.type == self.TRANSFERBPS:
			return self.getServiceInfoString(info, iServiceInformation.sTransferBPS, lambda x: "%d kB/s" % (x//1024))
		return ""

	text = property(getText)

	@cached
	def getValue(self):
		service = self.source.service
		info = service and service.info()
		if not info:
			return -1

		if self.type == self.XRES:
			return info.getInfo(iServiceInformation.sVideoWidth)
		if self.type == self.YRES:
			return info.getInfo(iServiceInformation.sVideoHeight)
		if self.type == self.FRAMERATE:
			return info.getInfo(iServiceInformation.sFrameRate)

		return -1

	value = property(getValue)

	def changed(self, what):
		if what[0] != self.CHANGED_SPECIFIC or what[1] in self.interesting_events:
			Converter.changed(self, what)
