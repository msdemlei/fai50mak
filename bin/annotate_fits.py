"""
This is a DaCHS processor (http://docs.g-vo.org/DaCHS/processors.html)
to add standard headers to FITS files from the FAI 50cm Maksutov telescope.
"""

import csv
import glob
import os
import re
import sys

from gavo.helpers import fitstricks
from gavo import api

TELESCOPE_LATIN = {
  "50cm менисковый телескоп Максутова":
    "Wide aperture Maksutov meniscus telescope with main mirror 50 cm",
  "Большой Шмидт": "Schmidt telescope (large camera)"}

FOCAL_LENGTHS = {
  "Wide aperture Maksutov meniscus telescope with main mirror 50 cm": 1.2,
  "Schmidt telescope (large camera)": 0.773,
  "Schmidt telescope (small camera)":0.17}
    
OBSERVERS_LATIN = {
  'Рожковский Д.А.': 'Rozhkovskij D.A.', 
  'Торопова Т.П.':'Tropova T.P.', 
  'Городецкий Д.И.':'Gordetskij D.I.',
  'Глушков Ю.И.':'Glushkovskij Yu.I.',
  'Торопова Т.П.  Рожковский Д.А.': 'Tropova T.P., Rozhkovskij D.A.',
  'Рожковский Д.А., Торопова Т.П.' : 'Rozhkovskij D.A., Tropova T.P.', 
  'Рожковский Д.А., Павлова Л.А.' : 'Rozhkovskij D.A., Pavlova L.A.',
  'Карягина З.В.':'Karyagina Z.V.', 
  'Матягин В.С.': 'Matyagin V.S.', 
  'Павлова Л.А': 'Pavlova L.A.', 
  'Гаврилов': 'Gavrilov', 
  'Курчаков А.В.': 'Kurchakov A.V.',
  'Рожковский Д.А.   Городецкий Д.И.':'Rozhkovskij D.A.   Gordetskij D.I.',
  'Солодовников В.В.': 'Solodovnikov V.V.'}



def parse_single_time(raw_time):
  """returns seconds of time for an h-m-s time string.

  Here is the syntax supported by the function.

  >>> parse_single_time("1h")
  3600.0
  >>> parse_single_time("4h30m")
  16200.0
  >>> parse_single_time("1h30m20s")
  5420.0
  >>> parse_single_time("20m")
  1200.0
  >>> parse_single_time("10.5m")
  630.0
  >>> parse_single_time("1m10s")
  70.0
  >>> parse_single_time("15s")
  15.0
  >>> parse_single_time("s23m")
  Traceback (most recent call last):
  ValueError: Cannot understand time 's23m'
  """
  mat = re.match(
    r"^(?P<hours>\d+(?:\.\d+)?h)?"
    r"(?P<minutes>\d+(?:\.\d+)?m)?"
    r"(?P<seconds>\d+(?:\.\d+)?s)?$", raw_time)
  if mat is None:
    raise ValueError(f"Cannot understand time '{raw_time}'")
  parts = mat.groupdict()

  return (float((parts["hours"] or "0h")[:-1])*3600
    + float((parts["minutes"] or "0m")[:-1])*60
    + float((parts["seconds"] or "0s")[:-1]))
  

def parse_exposure_times(raw_exp_times):
  """
  returns a list of floats giving the exposure times encoded in raw_exp_times.

  This is a ;-separated list of individual items.  see parse_single_time for
  details on the format.
  >>> parse_exposure_times("1h;2h;3h")
  [3600.0, 7200.0, 10800.0]
  >>> parse_exposure_times("1h30m20s;2h20m10s")
  [5420.0, 8410.0]
  >>> parse_exposure_times("1h30m20s;h20m10s")
  Traceback (most recent call last):
  ValueError: Cannot understand time 'h20m10s'
  """
  return [parse_single_time(raw_time) 
    for raw_time in raw_exp_times.split(";")]


def get_exposure_cards(raw_exp_times):
  """
  returns dict of keyword-value pairs for the FITS headers for our raw
  exposure times.

  >>> get_exposure_cards("1h")
  {'EXPTIME': 3600.0}
  >>> get_exposure_cards("1h;5h")
  {'EXPTIME': 3600.0, 'EXPTIM1': 3600.0, 'EXPTIM2': 18000.0}
  """
  exptimes = parse_exposure_times(raw_exp_times)
  if len(exptimes)==1:
    return {"EXPTIME": exptimes[0]}
  else:
    retval = {"EXPTIME": exptimes[0]}
    retval.update(dict(
      (f"EXPTIM{n+1}", val) for n, val in enumerate(exptimes)))
    return retval


def add_zero(num):
	"""
	returns "02" instead of "2"
	here num is number in str format
	"""
	if len(str(num))<2:
		return "0"+str(num)
	else:
		return str(num)
	

def reformat_one_tm(raw_time):
	"""	
	returns time in format hh:mm:ss
	>>> parcing_time(2h23m23s)
	'02:23:23'
	>>> parcing_time(5h31m)
	'05:31'
	>>> parcing_time(13h54)
	'13:54'
	"""
	if "m" not in raw_time: #we have values like "1h23" and patern doesn't work with it so we add "m" manually
		raw_time = raw_time+"m"
	mat = re.match(
    r"^(?P<hours>\d+(?:\.\d+)?h)?"
    r"(?P<minutes>\d+(?:\.\d+)?m)?"
    r"(?P<seconds>\d+(?:\.\d+)?s)?$", raw_time)
  if mat is None:
    raise ValueError(f"Cannot understand time '{raw_time}'")
  parts = mat.groupdict()
	for key in parts.keys():
		if parts[key]:
			parts[key] = add_zero(parts[key])
	if parts["second"]:
		return f"{parts["hours"]}:{parts["minutes"]}:{parts["seconds"]}"
	else:	
		return f"{parts["hours"]}:{parts["minutes"]}"	


def reformat_time(raw_time):
	"""
	returns time in format hh:mm:ss
	>>> parcing_time(2h23m23s;10h58m)
	['02:23:23','10:58']
	>>> parcing_time(5h31m;22h19m)
	['05:31','22:19']
	>>> parcing_time(1h54;13h49)
	['01:54','13:49']
	>>> parcing_time(2h23m23s;3h13m45s)
	['02:23:23','03:13:45']
	"""
	return [reformat_one_tm(tm) for tm in raw_time.split(";")]

def time_lt(raw_time):
	"""
	returns local time of start/end of observations in format "LT hh:mm:ss"
	"""
	return 'LT '+ time for time in reformat_time(raw_time)


def time_lst(raw_time):
	"""
	returns local sidereal time of start/end of observations in format "LST hh:mm:ss"
	"""
	return 'LST '+ time for time in reformat_time(raw_time)


def reformat_dec(raw_dec):
  """
  returns declination in the format "dd:mm:ss".

  >>> reformat_dec("29.06")
  '29:03:36'
  >>> reformat_dec("-23.30")
  '-23:18:00'
  >>> reformat_dec("50 41 45")
  '50:41:45'
  >>> reformat_dec("-01 28 02")
	'-01:28:02'
  >>> reformat_dec("-01 28")
  '-01:28'
	"""

  if "." in raw_dec:
    return api.degToDms(float(raw_dec), sepChar=":")
  else:
    return raw_dec.replace(" ", ":")

def dec_to_deg(raw_dec):
	"""
	returns declanation as float in degrees.

  >>> dec_to_deg("29.06")
  29.06
  >>> dec_to_deg("-23.30")
  -23.3
  >>> dec_to_deg("50 41 45")
  50.69583
  >>> dec_to_deg("-01 28 02")
	-1.46722
  >>> dec_to_deg("-01 28")
  -1.46667
	"""

	format_dec = reformat_dec(raw_dec)
	return api.dmsToDeg(format_deg,sepChar=":")

def reformat_ra(row_ra):
	"""
	returns right ascension in the format "hh:mm:ss"
	
  >>> reformat_ra("05 32 49")
  '05:32:49'
  >>> reformat_ra("05h33m")
  '05:33:00'
  >>> reformat_ra("02h41m45s")
  '02:41:45'
  >>> reformat_dec("01 28")
	'01:28'
	"""	
  if "h" in raw_ra:
		mat = re.match(
  	  r"^(?P<hours>\d+(?:\.\d+)?h)?"
    	r"(?P<minutes>\d+(?:\.\d+)?m)?"
    	r"(?P<seconds>\d+(?:\.\d+)?s)?$", raw_ra)
  	if mat is None:
    	raise ValueError(f"Cannot understand time '{raw_ra}'")
  	parts = mat.groupdict()   
		return (pats["hours"][:-1] or '00') +':' + (pats["minutes"][:-1] or '00') + ':' + (pats["seconds"][:-1] or '00')
  else:
    return raw_dec.replace(" ", ":")


def ra_to_deg(raw_ra):
	"""
	returns declanation as float in degrees.

  >>> ra_to_deg("05 32 49")
  83.20417
  >>> ra_to_deg("05h33m")
  83.25
  >>> ra_to_deg("02h41m45s")
  40.4375
  >>> ra_to_deg("01 28")
	22
	"""	

	format_ra = reformat_ra(raw_ra)
	return api.hmsToDeg(format_ra,sepChar=":")


def check_year(raw_date):
	date_split = raw_date.split(".")
	if len(date_split[-1])==4:
		return raw_date	
	else:
		return f'{date_split[0]}.{date_split[1]}.19{date_split[2]}'

def parce_one_date(raw_date)
	"""
	returns one date only (evining day, not exactly observation moment).
 
	>>> parce_one_date('13.03.1956')
	'13.03.1956'
	>>> parce_one_date('13.04.76')
 	'13.04.1976'
	>>> parce_one_date('01-02.01.1964')
	'01.01.1964' 
	>>> parce_one_date('01-02.01.64')
	'01.01.1964'
 	>>> parce_one_date('31.08-01.09.1967')
	'31.08.1967'
 	>>> parce_one_date('31.08-01.09.67')
	'31.08.1967'
 	>>> parce_one_date('31.12.1965-01.01.1966')
	'31.12.1965'	
 	>>> parce_one_date('31.12.65-01.01.66')
	'31.12.1965'
 	>>> parce_one_date('31.12.65-01.01.1966')
	'31.12.1965'
 	>>> parce_one_date('31.12.1965-01.01.66')
	'31.12.1965'
	"""
	if "-" not in raw_date:
		date = check_year(raw_date)	
	else:
		date_split = raw_date.split("-")
		ch = date_split[0] 		
		if len(ch)==2: #2 days
			date = ch + check_year(date_split[1])[2:] 	
		if len(ch)>2 and len(ch)<8: #2 months
			date = ch + check_year(date_split[1])[5:]
		if len(ch)>=8:	#2 years
			date = year_check(ch)

	return date


def parce_date(raw_dates):
	"""
	returns evining date of observations.For more information look at parce_one_data()

	>>> parce_date('13.03.1956;14.03.1956')
	['13.03.1956','14.03.1956']
	>>> parce_date('13.04.76;14.04.76')
 	['13.04.1976','14.04.1976']
	>>> parce_date('01-02.01.1964;02-03.01.1964')
	['01.01.1964','02.01.1964'] 
	>>> parce_date('01-02.01.64;02-03.01.64')
	['01-02.01.1964','02-03.01.1964']
 	>>> parce_date('31.08-01.09.1967;01-02.09.1967')
	['31.08.1967','01.09.1967']
 	>>> parce_date('31.08-01.09.67;01-02.09.67')
	['31.08.1967','01.09.1967']
 	>>> parce_date('31.12.1965-01.01.1966;01-02.01.1966')
	['31.12.1965','01.01.1966']	
 	>>> parce_date('31.12.65-01.01.66;01-02.01.66')
	['31.12.1965','01.01.66']
 	>>> parce_date('31.12.65-01.01.1966;01-02.01.1966')
	['31.12.1965','01.01.1966']
 	>>> parce_date('31.12.1965-01.01.66;01-02.01.1966')
	['31.12.1965','01.01.1966']
	"""
	return [parce_one_date(raw_date)
		for raw_date in raw_dates.split(";")]


def run_tests(*args):
  """
  runs all doctests and exits the program.
  """
  import doctest
  sys.exit(doctest.testmod()[0])


class PAHeaderAdder(api.HeaderProcessor):
  @staticmethod
  def addOptions(optParser):
    api.FileProcessor.addOptions(optParser)
    optParser.add_option("--test", help="Run unit tests, then exit",
      action="callback", callback=run_tests)

  def _createAuxiliaries(self, dd):
    logs_dir = os.path.join(
      dd.rd.resdir, "logbook")
    recs = []

    for src_f in glob.glob(logs_dir+"/*.csv"):
      with open(src_f, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        desired_keys = dict(
          (n, (n or "EMPTY").split()[0]) for n in rdr.fieldnames)
        source_key = os.path.basename(src_f).split(".")[0]

        for rec in rdr:
          new_rec = {
            "source-file": source_key}
          for k, v in rec.items():
            new_key = desired_keys[k]
            if new_key=="Идентификационный":
              new_key = "ID"
            new_rec[new_key] = v
          recs.append(new_rec)

    self.platemeta = dict(
      (rec["ID"], rec) for rec in recs)

  def _isProcessed(self, srcName):
    return os.path.exists(srcName+".hdr")

  def _mungeHeader(self, srcName, hdr):
    plateid = srcName.split(".")[-2].split("_")[-1]
    thismeta = self.platemeta[plateid]

#    mat = re.match(r"(\d\d)h(\d\d)m$", thismeta["RA"])
#    formatted_ra = "{}:{}".format(mat.group(1), mat.group(2))
#    mat = re.match(r"(\d\d)\.(\d\d)$", thismeta["DEC"])
#    formatted_dec = "{}:{}".format(mat.group(1), mat.group(2))

    cleaned_object = re.sub("[^ -~]+", "", thismeta["OBJECT"])

    dateorig = parce_date(thismeta["DATEOBS"])

    #time start
		tms = "unknown"
		if thismeta["TMS-LST"]:
			tms = time_lst(thismeta["TMS-LST"])
		else:
			if thismeta["TMS-LT"]:
				tms = time_lt(thismeta["TMS-LT"])
			
    #time end
		tme = "unknown"
		if thismeta["TME-LST"]:
			tme = time_lst(thismeta["TME-LST"])
		else:
			if thismeta["TME-LT"]:
				tme = time_lt(thismeta["TME-LT"])
			
    #obj_type = thismeta["OBJTYPE"] #we will add the column with data later

    numexp=len(parse_exposure_times(thismeta["EXPTIME"]))

    #observat
    observatory = "Fesenkov Astrophysical Institute"
    sitename = "https://www.fai.kz"
    sitelong = 43.17667
    sitelat = 76.96611
    siteelev = 1450

    #telescope
    telescope = "unknown"
    if thismeta["TELESCOPE"]:
      telescope = TELESCOPE_LATIN[thismeta["TELESCOPE"]]

    foclen = foclen_dic.get(telescope)
    
    observer = OBSERVERS_LATIN[thismeta["OBSERVER"]]

    variable_arguments = get_exposure_cards(thismeta["EXPTIME"])
    # variable_arguments.update(...)

    return fitstricks.makeHeaderFromTemplate(
      fitstricks.WFPDB_TEMPLATE,
      originalHeader=hdr,
			DATEORIG=dateorig,
#      RA_ORIG=formatted_ra,
#      DEC_ORIG=formatted_dec,
      RA_ORIG=thismeta["RA"],
      DEC_ORIG=thismeta["DEC"],
      RA=reformat_ra(thismeta["RA"]),
      DEC=reformat_dec(thismeta["DEC"]),
			RA_DEG = ra_to_deg(thismeta["RA"]),
			DEC_DEG =  dec_to_deg(thismeta["DEC"]),
#      OBSERVER=thismeta["OBSERVER"],
      OBJECT=cleaned_object,
      EXPTIM=exptime,
			NUMEXP=numexp,
			DATNAME="photographic plate",
      SCANAUTH="Shomshekova S., Umirbayeva A., Moshkina S.",
      ORIGIN="Contant",
      **variable_arguments)


if __name__=="__main__":
  api.procmain(PAHeaderAdder, "fai50mak/q", "import")
