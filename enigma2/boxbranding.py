# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# boxbranding.py: pluginurile vechi intreaba de aici numele aparatului si al imaginii (in alte imagini e un modul C). Aici raspunde BoxInfo; orice alt get...() da "".
# __all__: `from boxbranding import *` (un plugin de pornire multipla) ia numai numele din __all__, prin __getattr__ de mai jos; fara el nu primea nimic
# si cadea pe getImageFileSystem.
_CHEI = {
	"getBoxType": ("model",),
	"getMachineBuild": ("machinebuild", "model"),
	"getMachineMake": ("machinebuild", "model"),
	"getMachineName": ("displaymodel", "model"),
	"getMachineBrand": ("displaybrand", "brand"),
	"getDisplayModel": ("displaymodel", "model"),
	"getBrandOEM": ("brand",),
	"getOEVersion": ("oe",),
	"getImageDistro": ("distro",),
	"getImageVersion": ("imageversion",),
	"getImageBuild": ("imagebuild",),
	"getImageDevBuild": ("imagedevbuild",),
	"getImageType": ("imagetype",),
	"getDriverDate": ("driversdate",),
	"getFeedsUrl": ("feedsurl",),
	"getImageArch": ("architecture",),
	"getImageFolder": ("imagedir",),
	"getImageFileSystem": ("imagefs",),
	"getMachineKernelFile": ("kernelfile",),
	"getMachineRootFile": ("rootfile",),
	"getMachineMtdKernel": ("mtdkernel",),
	"getMachineMtdRoot": ("mtdrootfs",),
	"getMachineMtdBoot": ("mtdbootfs",),
	"getMachineMKUBIFS": ("mkubifs",),
	"getMachineUBINIZE": ("ubinize",),
	"getMachineProcModel": ("model",),
	"getDisplayType": ("displaytype",),
}
# ca in modulul C: "True" sau "False", ca text
_DA_NU = {
	"getHaveHDMI": "hdmi",
	"getHaveYUV": "yuv",
	"getHaveRCA": "rca",
	"getHaveAVJACK": "avjack",
	"getHaveSCART": "scart",
	"getHaveSCARTYUV": "scartyuv",
	"getHaveDVI": "dvi",
	"getHaveSVIDEO": "svideo",
	"getHaveMiniTV": "minitv",
	"getHaveHDMIinHD": "hdmihdin",
	"getHaveHDMIinFHD": "hdmifhdin",
	"getHaveWOL": "wol",
	"getHaveWWOL": "wwol",
	"getHaveTranscoding1": "transcoding",
	"getHaveTranscoding2": "multitranscoding",
	"getHaveCI": "ci",
	"getHaveVFDSymbol": "vfdsymbol",
}
__all__ = sorted(set(_CHEI) | set(_DA_NU))


def _citeste(chei):
	from Components.SystemInfo import BoxInfo
	for c in chei:
		v = BoxInfo.getItem(c)
		if v:
			return v
	return ""


def _daNu(cheie):
	from Components.SystemInfo import BoxInfo
	return "True" if BoxInfo.getItem(cheie) else "False"


def __getattr__(nume):
	if nume in _DA_NU:
		cheie = _DA_NU[nume]
		return lambda: _daNu(cheie)
	if nume.startswith("get"):
		chei = _CHEI.get(nume, ())
		return lambda: _citeste(chei)
	raise AttributeError(nume)
