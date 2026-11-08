# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Alternatives.py: canalele cu alternative (referintele 1:134:...), numele cerute de pluginuri.
from enigma import eServiceCenter, eServiceReference


def getAlternativeChannels(service):
	alternative = eServiceCenter.getInstance().list(eServiceReference(service))
	return alternative and alternative.getContent("S", True)


def CompareWithAlternatives(serviceA, serviceB):
	return serviceA and serviceB and (serviceA == serviceB
		or serviceA.startswith("1:134:") and serviceB in getAlternativeChannels(serviceA)
		or serviceB.startswith("1:134:") and serviceA in getAlternativeChannels(serviceB))


def GetWithAlternative(service):
	if service.startswith("1:134:"):
		canale = getAlternativeChannels(service)
		if canale:
			return canale[0]
	return service


def ResolveCiAlternative(ref, ignore_ref=None, record_mode=False):
	return ref
