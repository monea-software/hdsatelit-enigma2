# Modificat de moneasoftware.com si hdsatelit.com, 2026
#read the comment to this file in lib/service/iservice.h !!
# Portat la Python 3.

import os

os.rename("enigma.py", "enigma.py.org")

with open("enigma.py.org", "r") as source, open("enigma.py", "w") as dest:
	line = 1
	for text in source:
		oldstr = text
		text = text.replace('_ENUMS)', ')')

		pos = text.find('_ENUMS')
		if pos != -1:
			spacepos = pos
			while spacepos > 0 and text[spacepos] != ' ':
				spacepos -= 1
			tmpstr = text[spacepos:pos]
			if tmpstr.find('_enigma.') == -1:
				text = text[:pos] + text[pos + 6:]

		if oldstr != text:
			print("!!! Patch enigma.py line %d\n%s\n%s" % (line, oldstr[:len(oldstr) - 1], text))

		dest.write(text)
		line += 1

	# HDSatelit: la coada, stratul de compatibilitate pentru pluginurile scrise pentru interfata comuna enigma2
	# (lib/python/HdsEnigmaCompat.py): pune numai numele care lipsesc; o greseala in el nu opreste enigma
	dest.write("""

# HDSatelit: stratul de compatibilitate al pluginurilor (HdsEnigmaCompat.py)
try:
	import HdsEnigmaCompat as _hdsCompat
	_hdsCompat.aplica(globals())
	del _hdsCompat
except Exception as _hdsEroare:
	print("[enigma] HdsEnigmaCompat: %s" % _hdsEroare)
""")

os.remove("enigma.py.org")
