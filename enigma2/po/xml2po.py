#!/usr/bin/python
# Modificat de moneasoftware.com si hdsatelit.com, 2026
import sys
import os
import re
from xml.sax import make_parser
from xml.sax.handler import ContentHandler, property_lexical_handler
try:
	from _xmlplus.sax.saxlib import LexicalHandler
	no_comments = False
except ImportError:
	class LexicalHandler:
		pass
	no_comments = True

class parseXML(ContentHandler, LexicalHandler):
	def __init__(self, attrlist):
		self.isPointsElement, self.isReboundsElement = 0, 0
		self.attrlist = attrlist
		self.last_comment = None
		# valorile de culoare (#rrggbb, #aarrggbb: <color value="..."> din data/skin_default.xml) nu sunt texte de
		# tradus; aceeasi regula ca in xml2po.py din enigma2 OE-Alliance (GPL-2.0)
		self.ishex = re.compile(r'#[0-9a-fA-F]+\Z')

	def comment(self, comment):
		if comment.find("TRANSLATORS:") != -1:
			self.last_comment = comment

	def startElement(self, name, attrs):
		# "description" (textele de ajutor din data/setup.xml, 23.09.2026), ca in enigma2-ul mai nou
		for x in ["text", "title", "value", "caption", "description"]:
			try:
				if self.ishex.match(attrs[x]):
					continue
				attrlist.add((attrs[x], self.last_comment))
				self.last_comment = None
			except KeyError:
				pass

parser = make_parser()

attrlist = set()

contentHandler = parseXML(attrlist)
parser.setContentHandler(contentHandler)
if not no_comments:
	parser.setProperty(property_lexical_handler, contentHandler)

for arg in sys.argv[1:]:
	if os.path.isdir(arg):
		for file in os.listdir(arg):
			if (file.endswith(".xml")):
				parser.parse(os.path.join(arg, file))
	else:
		parser.parse(arg)

	attrlist = list(attrlist)
	attrlist.sort(key=lambda a: a[0])

	for (k,c) in attrlist:
		print()
		print('#: ' + arg)
		if c:
			for l in c.split('\n'):
				print("#. ", l)
		if str(k).strip() != "":
			print('msgid "' + str(k) + '"')
			print('msgstr ""')

	attrlist = set()
