# Modificat de moneasoftware.com si hdsatelit.com, 2026
import sys
try:
	from enigma import ePythonOutput
except Exception:
	ePythonOutput = None

class EnigmaOutput:
	def write(self, data):
		# Python 3: textul e deja str; SWIG il trece ca const char* (UTF-8)
		if isinstance(data, bytes):
			data = data.decode("UTF-8", "replace")
		if ePythonOutput is not None:
			# enigma2.log trebuie sa ramana UTF-8 valid: enigma2.sh il trece prin grep si LogManager il arata.
			# Inainte, argumentul const char * refuza un str cu surogate si escapul se facea pe ramura
			# de mai jos; acum conversia reuseste, deci escapul se face AICI, altfel octetii Latin-1 ai unui
			# nume de fisier ar intra bruti in jurnal si l-ar face binar.
			if not data.isascii():
				try:
					data.encode("utf-8")
				except UnicodeEncodeError:
					data = data.encode("utf-8", "backslashreplace").decode("utf-8")
			try:
				ePythonOutput(data)
			except (TypeError, ValueError):
				# a str that cannot be encoded as UTF-8 (a file name with bytes that are not UTF-8 comes with
				# surrogates): the const char * argument refuses it, and print() would raise in whatever code
				# printed the name (Navigation.playService, for one). Logged with the bad characters as \udcxx.
				ePythonOutput(data.encode("utf-8", "backslashreplace").decode("utf-8"))
		else:
			sys.__stdout__.write(data)

	def flush(self):
		if ePythonOutput is None:
			try:
				sys.__stdout__.flush()
			except Exception:
				pass

if ePythonOutput is not None:
	sys.stdout = sys.stderr = EnigmaOutput()

