# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile cer lista modurilor si schimbarea temporara a modului HDMI.
# Foloseste numai modurile oferite de VideoOutput, fara alte setari salvate.


class VideoHardware:
	def getModeList(self, port):
		"""[(rezolutie, [frecvente])], numai pentru iesirea digitala existenta."""
		if port not in ("HDMI", "DVI"):
			return []
		from Components import VideoOutput
		output = VideoOutput.videoOutput
		if output is None:
			return []
		result = []
		for value in output.screenModes():
			group = VideoOutput.groupKey(value)
			rate = VideoOutput.modeParts(value)[1]
			entry = next((item for item in result if item[0] == group), None)
			if entry is None:
				entry = (group, [])
				result.append(entry)
			if rate and rate + "Hz" not in entry[1]:
				entry[1].append(rate + "Hz")
		return result

	def setMode(self, port, mode, rate):
		"""Aplica temporar rezolutia si frecventa; False pentru o alegere neacceptata."""
		if port not in ("HDMI", "DVI"):
			return False
		from Components import VideoOutput
		output = VideoOutput.videoOutput
		if output is None:
			return False
		rate = str(rate).removesuffix("Hz")
		# Nu ghiceste frecventa pentru "auto" sau "multi" si nu alege o rezerva.
		for value in output.screenModes():
			if mode not in (value, VideoOutput.groupKey(value)):
				continue
			if VideoOutput.modeParts(value)[1] == rate:
				return output.apply({"videomode": value, "rate_by_channel": False})
		return False


video_hw = VideoHardware()
