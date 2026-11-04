import unicodedata


def stergeUltimaLitera(text):
	"""Remove the last base character together with its combining marks."""
	poz = len(text) - 1
	while poz > 0 and unicodedata.category(text[poz]).startswith("M"):
		poz -= 1
	return text[:max(0, poz)]
