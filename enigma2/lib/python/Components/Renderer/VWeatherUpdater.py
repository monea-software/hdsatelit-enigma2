# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Renderer/VWeatherUpdater.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
# keep it for compatibility, please note this renderer is deprecated --> remove it from your skins
from enigma import eLabel

from Components.Renderer.Renderer import Renderer


class VWeatherUpdater(Renderer):
	GUI_WIDGET = eLabel

	def __init__(self):
		Renderer.__init__(self)
