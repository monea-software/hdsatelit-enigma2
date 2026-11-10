# Modificat de moneasoftware.com si hdsatelit.com, 2026
from xml.etree.ElementTree import parse


def readUnicableProducts(filename):
	# Produsele vechi fara format raman EN50494, cu cel mult opt benzi.
	root = parse(filename).getroot()

	def readSection(sectionName):
		manufacturers = {}
		section = root.find(sectionName)
		if section is None:
			return manufacturers
		for manufacturer in section.findall("manufacturer"):
			products = {}
			for product in manufacturer.findall("product"):
				standard = product.get("format", "EN50494")
				if standard not in ("EN50494", "EN50607"):
					raise ValueError("Format Unicable necunoscut: %s" % standard)
				bands = 32 if standard == "EN50607" else 8
				frequencies = [int(product.get("scr%d" % band, "0")) for band in range(1, bands + 1)]
				# Pastram benzile goale din interior pentru a nu schimba numarul UB.
				while frequencies and frequencies[-1] == 0:
					frequencies.pop()
				products[product.get("name")] = {
					"frequencies": tuple(frequencies),
					"positions": int(product.get("positions", 1)),
					"lofl": int(product.get("lofl", 9750)),
					"lofh": int(product.get("lofh", 10600)),
					"threshold": int(product.get("threshold", 11700)),
					"format": standard}
			manufacturers[manufacturer.get("name")] = products
		return manufacturers

	return readSection("lnb"), readSection("matrix")
