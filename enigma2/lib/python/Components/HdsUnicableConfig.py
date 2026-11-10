# Modificat de moneasoftware.com si hdsatelit.com, 2026


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def unicableSnapshot(cfg):
	# Copia separa valorile editate de valorile deja salvate.
	from copy import deepcopy
	from Components import HdsLnb
	from Components.config import ConfigSubsection, ConfigSubDict, ConfigSubList

	structure = []
	def keepStructure(node):
		if isinstance(node, ConfigSubsection):
			children = dict(node.dict())
			structure.append((node, children))
			for child in children.values():
				keepStructure(child)
		elif isinstance(node, ConfigSubDict):
			children = dict(node)
			structure.append((node, children))
			for child in children.values():
				keepStructure(child)
		elif isinstance(node, ConfigSubList):
			children = list(node)
			structure.append((node, children))
			for child in children:
				keepStructure(child)
	keepStructure(cfg)
	values, forced = {}, {}
	for path, element in HdsLnb.frunze(cfg):
		if not HdsLnb._esteNimic(element):
			values[path] = HdsLnb.textElement(element)
			forced[path] = element.save_forced
	return {"saved": deepcopy(cfg.saved_value), "values": values,
		"forced": forced, "structure": structure}


def unicableRestore(cfg, snapshot):
	from copy import deepcopy
	from Components import HdsLnb
	from Components.config import ConfigSubsection, ConfigSubDict, ConfigSubList

	def restoreSaved(node, saved):
		if isinstance(node, ConfigSubsection):
			stored = saved if isinstance(saved, dict) else {}
			node.saved_value = deepcopy(stored)
			for key, child in list(node.dict().items()):
				restoreSaved(child, stored.get(str(key)))
		elif isinstance(node, (ConfigSubDict, ConfigSubList)):
			stored = saved if isinstance(saved, dict) else {}
			node.saved_value = deepcopy(stored)
			children = node.items() if isinstance(node, dict) else enumerate(node)
			for key, child in list(children):
				restoreSaved(child, stored.get(str(key)))
		else:
			node.saved_value = deepcopy(saved)

	def order(path):
		if path == "configMode":
			return 0, path
		if path.startswith("advanced.sat.") and path.endswith(".lnb"):
			return 1, path
		if path.endswith((".lof", ".diseqcMode")):
			return 2, path
		if path.endswith(".unicable"):
			return 3, path
		if path.endswith((".product", ".unicableLnbManufacturer", ".unicableMatrixManufacturer")):
			return 4, path
		if path.endswith(".satcrformat"):
			return 5, path
		if path.endswith(".satcrpositions"):
			return 6, path
		if path.endswith((".satcruser", ".satcrposition")):
			return 8, path
		return 7, path

	# Activarea poate inlocui ConfigNothing si crea liste noi.
	# Revenim la aceleasi obiecte, astfel incat urmatoarea activare sa fie curata.
	for node, children in snapshot["structure"]:
		if isinstance(node, ConfigSubsection):
			node.dict().clear()
			node.dict().update(children)
		elif isinstance(node, ConfigSubDict):
			dict.clear(node)
			dict.update(node, children)
		else:
			list.__setitem__(node, slice(None), children)
	restoreSaved(cfg, snapshot["saved"])
	paths = [path for path, element in HdsLnb.frunze(cfg)
		if not HdsLnb._esteNimic(element)]
	for path in sorted(paths, key=order):
		element = HdsLnb.element(cfg, path)
		if element is None or HdsLnb._esteNimic(element):
			continue
		if path.endswith(".satcrposition"):
			section = HdsLnb.element(cfg, path.rsplit(".", 1)[0])
			if section.lof.value == "unicable":
				from Components.NimManager import updateUnicablePositionChoices
				updateUnicablePositionChoices(section)
		if path in snapshot["values"]:
			text = snapshot["values"][path]
			if HdsLnb.textElement(element) != text:
				element.value = element.fromstring(text)
		else:
			element.load()
		element.save_forced = snapshot["forced"].get(path, False)
	# Niciun camp nu pastreaza valorile salvate de incercarea esuata.
	restoreSaved(cfg, snapshot["saved"])
	for path, text in snapshot["values"].items():
		element = HdsLnb.element(cfg, path)
		if element is None or HdsLnb.textElement(element) != text:
			raise RuntimeError(_t("Nu s-a restaurat campul Unicable: %s") % path)
	if cfg.saved_value != snapshot["saved"]:
		raise RuntimeError(_t("Nu s-au restaurat valorile salvate Unicable"))


def unicableRows(lnb, advanced=None, manager=None, slot=None):
	# Aceleasi randuri si elemente config pe televizor si in pagina web.
	from Components.config import ConfigSelection, NoSave
	from Components.NimManager import getUnicableConfig, updateUnicablePositionChoices
	updateUnicablePositionChoices(lnb)
	protocol, band, frequencies, positions = getUnicableConfig(lnb)
	rows = [("mode", "Unicable " + _t("Configuration Mode"), lnb.unicable, False)]
	manual = lnb.unicable.value == "unicable_user"
	if not manual:
		if lnb.unicable.value == "unicable_lnb":
			manufacturer = lnb.unicableLnbManufacturer
			products = lnb.unicableLnb
		else:
			manufacturer = lnb.unicableMatrixManufacturer
			products = lnb.unicableMatrix
		rows.extend((("manufacturer", _t("Manufacturer"), manufacturer, False),
			("product", _t("Type"), products[manufacturer.value].product, False)))
	rows.append(("format", _t("Unicable protocol"), protocol, not manual))
	count = len(band.choices.choices)
	rows.append(("bands", _t("User bands"), NoSave(ConfigSelection([(str(count), str(count))])), True))
	rows.append(("band", _t("User band"), band, False))
	rows.append(("frequency", _t("Frequency"), frequencies[band.index], not manual))
	if manual:
		rows.extend((("positions", _t("Satellite positions"), lnb.satcrpositions, False),
			("lofl", _t("LOF/L"), lnb.lofl, False),
			("lofh", _t("LOF/H"), lnb.lofh, False),
			("threshold", _t("Threshold"), lnb.threshold, False)))
	if positions > 1:
		rows.append(("position", _t("Satellite position"), lnb.satcrposition, False))
	rows.append(("pinEnabled", _t("Use PIN"), lnb.satcrpinEnabled, False))
	if lnb.satcrpinEnabled.value:
		rows.append(("pin", _t("PIN"), lnb.satcrpin, False))
	if advanced is not None and manager is not None:
		choices = [(str(n), manager.getNimDescription(n)) for n in manager.canConnectTo(slot)]
		if choices:
			rows.append(("connected", _t("connected"), advanced.unicableconnected, False))
			if advanced.unicableconnected.value:
				advanced.unicableconnectedTo.setChoices(choices)
				rows.append(("connectedTo", _t("Connected to"), advanced.unicableconnectedTo, False))
	return rows
