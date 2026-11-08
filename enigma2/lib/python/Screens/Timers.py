# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile cer editorul unei inregistrari si liste pentru extensiile lui.
# Editorul ramane cel al imaginii; listele pastreaza doar inregistrarile extensiilor.
from RecordTimer import RecordTimerEntry as _RecordTimerEntry
from Screens.TimerEntry import TimerEntry as RecordTimerEdit


class RecordTimerEntry(_RecordTimerEntry):
	def __init__(self, *args, fixDescription=False, **kwargs):
		# Optiunea este acceptata, fara o regula de rescriere a descrierii nedovedita.
		super().__init__(*args, **kwargs)


# Dovezile arata inscrierea functiilor, dar nu argumentele sau momentul apelarii.
# Nu sunt chemate pana cand contractul lor poate fi verificat.
onRecordTimerChannelChange = []
onRecordTimerCreate = []
onRecordTimerSave = []
onRecordTimerSetup = []

__all__ = ["RecordTimerEdit", "RecordTimerEntry", "onRecordTimerChannelChange",
	"onRecordTimerCreate", "onRecordTimerSave", "onRecordTimerSetup"]
