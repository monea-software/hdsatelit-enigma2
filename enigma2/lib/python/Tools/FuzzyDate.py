# Modificat de moneasoftware.com si hdsatelit.com, 2026
from time import localtime, time

def FuzzyTime(t, inPast=False):
	# inPast=True (cerut de pluginurile scrise pentru celelalte imagini Enigma2, de pilda listele de inregistrari): „Yesterday” si ziua
	# saptamanii in fata datei din anul acesta; fara el, totul ca inainte
	d = localtime(t)
	nt = time()
	n = localtime()
	zile = (_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun"))
	
	if d[:3] == n[:3]:
		# same day
		date = _("Today")
	elif inPast and d[0] == n[0] and d[7] == n[7] - 1:
		date = _("Yesterday")
	elif ((t - nt) < 7*86400) and (nt < t) and not inPast:
		# same week
		date = zile[d[6]]
	elif d[0] == n[0]:
		# same year
		date = ("%s %d.%d." % (zile[d[6]], d[2], d[1])) if inPast else ("%d.%d." % (d[2], d[1]))
	else:
		date = "%d.%d.%d" % (d[2], d[1], d[0])
	
	timeres = "%d:%02d" % (d[3], d[4])
	
	return (date, timeres)

if __name__ == "__main__":
	print("now:    %s %s" % FuzzyTime(time()))
	print("1 day:  %s %s" % FuzzyTime(time() + 86400))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *2))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *3))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *4))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *5))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *6))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *7))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *8))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *9))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *10))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *11))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *12))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *13))
	print("2 days: %s %s" % FuzzyTime(time() + 86400 *14))
