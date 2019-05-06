# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

from flask.ext.principal import identity_changed, Identity
from tornado.web import StaticFileHandler, HTTPError
from flask import url_for, make_response, request, current_app
from flask.ext.login import login_required, login_user, current_user
from werkzeug.utils import redirect
from sockjs.tornado import SockJSConnection

import sys
import datetime
import stat
import mimetypes
import email
import time
import os
import threading
import logging
from functools import wraps

from octoprint.settings import settings
import octoprint.timelapse
import octoprint.server
from octoprint.users import ApiUser
from octoprint.events import Events


def restricted_access(func, apiEnabled=True):
	"""
	If you decorate a view with this, it will ensure that first setup has been
	done for OctoPrint's Access Control plus that any conditions of the
	login_required decorator are met. It also allows to login using the masterkey or any
	of the user's apikeys if API access is enabled globally and for the decorated view.

	If OctoPrint's Access Control has not been setup yet (indicated by the "firstRun"
	flag from the settings being set to True and the userManager not indicating
	that it's user database has been customized from default), the decorator
	will cause a HTTP 403 status code to be returned by the decorated resource.

	If an API key is provided and it matches a known key, the user will be logged in and
	the view will be called directly. If the provided key doesn't match any known key,
	a HTTP 403 status code will be returned by the decorated resource.

	Otherwise the result of calling login_required will be returned.
	"""
	@wraps(func)
	def decorated_view(*args, **kwargs):
		# if OctoPrint hasn't been set up yet, abort
		if settings().getBoolean(["server", "firstRun"]) and (octoprint.server.userManager is None or not octoprint.server.userManager.hasBeenCustomized()):
			return make_response("OctoPrint isn't setup yet", 403)

		# if API is globally enabled, enabled for this request and an api key is provided, try to use that
		apikey = _getApiKey(request)
		if settings().get(["api", "enabled"]) and apiEnabled and apikey is not None:
			if apikey == settings().get(["api", "key"]):
				# master key was used
				user = ApiUser()
			else:
				# user key might have been used
				user = octoprint.server.userManager.findUser(apikey=apikey)

			if user is None:
				make_response("Invalid API key", 401)
			if login_user(user, remember=False):
				identity_changed.send(current_app._get_current_object(), identity=Identity(user.get_id()))
				return func(*args, **kwargs)

		# call regular login_required decorator
		return login_required(func)(*args, **kwargs)
	return decorated_view


def api_access(func):
	@wraps(func)
	def decorated_view(*args, **kwargs):
		if not settings().get(["api", "enabled"]):
			make_response("API disabled", 401)
		apikey = _getApiKey(request)
		if apikey is None:
			make_response("No API key provided", 401)
		if apikey != settings().get(["api", "key"]):
			make_response("Invalid API key", 403)
		return func(*args, **kwargs)
	return decorated_view


def _getUserForApiKey(apikey):
	if settings().get(["api", "enabled"]) and apikey is not None:
		if apikey == settings().get(["api", "key"]):
			# master key was used
			return ApiUser()
		else:
			# user key might have been used
			return octoprint.server.userManager.findUser(apikey=apikey)
	else:
		return None


def _getApiKey(request):
	# Check Flask GET/POST arguments
	if hasattr(request, "values") and "apikey" in request.values:
		return request.values["apikey"]

	# Check Tornado GET/POST arguments
	if hasattr(request, "arguments") and "apikey" in request.arguments \
		and len(request.arguments["apikey"]) > 0 and len(request.arguments["apikey"].strip()) > 0:
		return request.arguments["apikey"]

	# Check Tornado and Flask headers
	if "X-Api-Key" in request.headers.keys():
		return request.headers.get("X-Api-Key")

	return None


#~~ Printer state


class PrinterStateConnection(SockJSConnection):
	EVENTS = [Events.UPDATED_FILES, Events.METADATA_ANALYSIS_FINISHED, Events.MOVIE_RENDERING, Events.MOVIE_DONE,
			  Events.MOVIE_FAILED, Events.SLICING_STARTED, Events.SLICING_DONE, Events.SLICING_FAILED,
			  Events.TRANSFER_STARTED, Events.TRANSFER_DONE]

	def __init__(self, printer, gcodeManager, userManager, eventManager, session):
		SockJSConnection.__init__(self, session)

		self._logger = logging.getLogger(__name__)

		self._temperatureBacklog = []
		self._temperatureBacklogMutex = threading.Lock()
		self._logBacklog = []
		self._logBacklogMutex = threading.Lock()
		self._messageBacklog = []
		self._messageBacklogMutex = threading.Lock()

		self._printer = printer
		self._gcodeManager = gcodeManager
		self._userManager = userManager
		self._eventManager = eventManager

	def _getRemoteAddress(self, info):
		forwardedFor = info.headers.get("X-Forwarded-For")
		if forwardedFor is not None:
			return forwardedFor.split(",")[0]
		return info.ip

	def on_open(self, info):
		remoteAddress = self._getRemoteAddress(info)
		self._logger.info("New connection from client: %s" % remoteAddress)
		self._printer.registerCallback(self)
		self._gcodeManager.registerCallback(self)
		octoprint.timelapse.registerCallback(self)

		self._eventManager.fire(Events.CLIENT_OPENED, {"remoteAddress": remoteAddress})
		for event in PrinterStateConnection.EVENTS:
			self._eventManager.subscribe(event, self._onEvent)

		octoprint.timelapse.notifyCallbacks(octoprint.timelapse.current)
		
		try:
			utcMilliSecs = float(systemTimeMgt().getNetworkTime())
			self._printer.mcLog("NetworkTime: %f" %utcMilliSecs)
		except: pass

	def on_close(self):
		self._logger.info("Client connection closed")
		self._printer.unregisterCallback(self)
		self._gcodeManager.unregisterCallback(self)
		octoprint.timelapse.unregisterCallback(self)

		self._eventManager.fire(Events.CLIENT_CLOSED)
		for event in PrinterStateConnection.EVENTS:
			self._eventManager.unsubscribe(event, self._onEvent)

	def on_message(self, message):
		pass

	def sendCurrentData(self, data):
		# add current temperature, log and message backlogs to sent data
		with self._temperatureBacklogMutex:
			temperatures = self._temperatureBacklog
			self._temperatureBacklog = []

		with self._logBacklogMutex:
			logs = self._logBacklog
			self._logBacklog = []

		with self._messageBacklogMutex:
			messages = self._messageBacklog
			self._messageBacklog = []

		data.update({
			"temps": temperatures,
			"logs": logs,
			"messages": messages
		})
		self._emit("current", data)

	def sendHistoryData(self, data):
		self._emit("history", data)

	def sendEvent(self, type, payload=None):
		self._emit("event", {"type": type, "payload": payload})

	def sendFeedbackCommandOutput(self, name, output):
		self._emit("feedbackCommandOutput", {"name": name, "output": output})

	def sendTimelapseConfig(self, timelapseConfig):
		self._emit("timelapse", timelapseConfig)

	def addLog(self, data):
		with self._logBacklogMutex:
			self._logBacklog.append(data)

	def addMessage(self, data):
		with self._messageBacklogMutex:
			self._messageBacklog.append(data)

	def addTemperature(self, data):
		with self._temperatureBacklogMutex:
			self._temperatureBacklog.append(data)

	def _onEvent(self, event, payload):
		self.sendEvent(event, payload)

	def _emit(self, type, payload):
		self.send({type: payload})


#~~ customized large response handler


class LargeResponseHandler(StaticFileHandler):

	CHUNK_SIZE = 16 * 1024

	def initialize(self, path, default_filename=None, as_attachment=False, access_validation=None):
		StaticFileHandler.initialize(self, path, default_filename)
		self._as_attachment = as_attachment
		self._access_validation = access_validation

	def get(self, path, include_body=True):
		if self._access_validation is not None:
			self._access_validation(self.request)

		path = self.parse_url_path(path)
		abspath = os.path.abspath(os.path.join(self.root, path))
		# os.path.abspath strips a trailing /
		# it needs to be temporarily added back for requests to root/
		if not (abspath + os.path.sep).startswith(self.root):
			raise HTTPError(403, "%s is not in root static directory", path)
		if os.path.isdir(abspath) and self.default_filename is not None:
			# need to look at the request.path here for when path is empty
			# but there is some prefix to the path that was already
			# trimmed by the routing
			if not self.request.path.endswith("/"):
				self.redirect(self.request.path + "/")
				return
			abspath = os.path.join(abspath, self.default_filename)
		if not os.path.exists(abspath):
			raise HTTPError(404)
		if not os.path.isfile(abspath):
			raise HTTPError(403, "%s is not a file", path)

		stat_result = os.stat(abspath)
		modified = datetime.datetime.fromtimestamp(stat_result[stat.ST_MTIME])

		self.set_header("Last-Modified", modified)

		mime_type, encoding = mimetypes.guess_type(abspath)
		if mime_type:
			self.set_header("Content-Type", mime_type)

		cache_time = self.get_cache_time(path, modified, mime_type)

		if cache_time > 0:
			self.set_header("Expires", datetime.datetime.utcnow() +
									   datetime.timedelta(seconds=cache_time))
			self.set_header("Cache-Control", "max-age=" + str(cache_time))

		self.set_extra_headers(path)

		# Check the If-Modified-Since, and don't send the result if the
		# content has not been modified
		ims_value = self.request.headers.get("If-Modified-Since")
		if ims_value is not None:
			date_tuple = email.utils.parsedate(ims_value)
			if_since = datetime.datetime.fromtimestamp(time.mktime(date_tuple))
			if if_since >= modified:
				self.set_status(304)
				return

		if not include_body:
			assert self.request.method == "HEAD"
			self.set_header("Content-Length", stat_result[stat.ST_SIZE])
		else:
			with open(abspath, "rb") as file:
				while True:
					data = file.read(LargeResponseHandler.CHUNK_SIZE)
					if not data:
						break
					self.write(data)
					self.flush()

	def set_extra_headers(self, path):
		if self._as_attachment:
			self.set_header("Content-Disposition", "attachment")


#~~ admin access validator for use with tornado


def admin_validator(request):
	"""
	Validates that the given request is made by an admin user, identified either by API key or existing Flask
	session.

	Must be executed in an existing Flask request context!

	:param request: The Flask request object
	"""

	apikey = _getApiKey(request)
	if settings().get(["api", "enabled"]) and apikey is not None:
		user = _getUserForApiKey(apikey)
	else:
		user = current_user

	if user is None or not user.is_authenticated() or not user.is_admin():
		raise HTTPError(403)


#~~ reverse proxy compatible wsgi middleware


class ReverseProxied(object):
	"""
	Wrap the application in this middleware and configure the
	front-end server to add these headers, to let you quietly bind
	this to a URL other than / and to an HTTP scheme that is
	different than what is used locally.

	In nginx:
		location /myprefix {
			proxy_pass http://192.168.0.1:5001;
			proxy_set_header Host $host;
			proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
			proxy_set_header X-Scheme $scheme;
			proxy_set_header X-Script-Name /myprefix;
		}

	Alternatively define prefix and scheme via config.yaml:
		server:
			baseUrl: /myprefix
			scheme: http

	:param app: the WSGI application
	"""

	def __init__(self, app):
		self.app = app

	def __call__(self, environ, start_response):
		script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
		if not script_name:
			script_name = settings().get(["server", "baseUrl"])

		if script_name:
			environ['SCRIPT_NAME'] = script_name
			path_info = environ['PATH_INFO']
			if path_info.startswith(script_name):
				environ['PATH_INFO'] = path_info[len(script_name):]

		scheme = environ.get('HTTP_X_SCHEME', '')
		if not scheme:
			scheme = settings().get(["server", "scheme"])

		if scheme:
			environ['wsgi.url_scheme'] = scheme

		host = environ.get('HTTP_X_FORWARDED_HOST', '')
		if not host:
			host = settings().get(["server", "forwardedHost"])

		if host:
			environ['HTTP_HOST'] = host

		return self.app(environ, start_response)


def redirectToTornado(request, target):
	requestUrl = request.url
	appBaseUrl = requestUrl[:requestUrl.find(url_for("index") + "api")]

	redirectUrl = appBaseUrl + target
	if "?" in requestUrl:
		fragment = requestUrl[requestUrl.rfind("?"):]
		redirectUrl += fragment
	return redirect(redirectUrl)


#add by kevin, for parse wifi info
import subprocess
import re
_instance = None
########################################################################
class WifiParse():
	""""""

	#----------------------------------------------------------------------
	def __init__(self):
		"""Constructor"""
		#self._regex_ESSID = re.compile("ESSID:(\S+)")
		self._regex_Encryption = re.compile("(WPA2|WPA)")
		self._regex_Quality = re.compile("(\d+)/100")
		self._parsed_cells = []
		self._enc_map = {
		    "wpa": ["wpa-ssid", "wpa-psk"],
		    "wep": ["wireless-essid", "wireless-key"],
		    "open": ["wireless-essid", ""]
		}
		self._mutex = threading.Lock()
		
	#----------------------------------------------------------------------
	def getAvailableWifiNames(self, sort=True):
		if self._mutex.locked() is True: return []
		self._mutex.acquire()
		if not len(self._parsed_cells):
			self._parsed_cells = []
			cells = self.count_cells(self.scan())
			parsed_cells = self.parse_cells(cells)
			if sort:
				self.sort_cells(parsed_cells)
			self._parsed_cells = parsed_cells
		wifiNames = []
		for item in parsed_cells:
			ssid = None if not isinstance(item, dict) else item.get("ESSID")
			if ssid is not None and ssid not in wifiNames:
				wifiNames.append(ssid)
		self._parsed_cells = []
		self._mutex.release()
		return wifiNames
		
	#----------------------------------------------------------------------
	def scan(self, name="wlan0"):
		""""""
		proc = subprocess.Popen("sudo iwlist %s scan 2> /dev/null" %name, shell=True, stdout=subprocess.PIPE)
		stdout_str = proc.communicate()[0]
		stdout_list = stdout_str.split('\n')
		return stdout_list
	
	#----------------------------------------------------------------------
	def _match_line(self, lines, keyword):
		""""""
		for line in lines:
			match = self._match(line, keyword)
			if match is not None:
				return match
		return None
	
	#----------------------------------------------------------------------
	def _match(self, line, keyword):
		""""""
		if isinstance(line, str) and isinstance(line, str):
			line = line.lstrip()
			length = len(keyword)
			if line[:length] == keyword:
				return line[length:]
			else:
				return None
		else:
			return None
	
	#----------------------------------------------------------------------
	def count_cells(self, iwlist_out=""):
		""""""
		cells = [[]]
		if iwlist_out:
			for line in iwlist_out:
				cell_line = self._match(line, "Cell ")
				if cell_line is not None:
					cells.append([])
					line = cell_line[-27:]
				cells[-1].append(line.rstrip())
		
		cells = cells[1:]
		return cells
	
	#----------------------------------------------------------------------	
	def parse_cells(self, cells=[]):
		parsed_cells = []
		for cell in cells:
			parsed_cell = self.parse_cell(cell)
			if parsed_cell:
				parsed_cells.append(parsed_cell)
		return parsed_cells

	#----------------------------------------------------------------------
	def get_ESSID(self, cell):
		return self._match_line(cell, "ESSID:")[1:-1]
	
	#----------------------------------------------------------------------
	def get_Encryption(self, cell):
		enc = ""
		if "off" == self._match_line(cell, "Encryption key:"):
			enc = "OPEN"
		else:
			for line in cell:
				match = self._match(line, "IE:")
				if match is not None:
					wpa = re.search(self._regex_Encryption, line)
					if wpa is not None:
						enc = wpa.group(1)
			if enc == "":
				enc = "WEP"
			
		return enc
	
	#----------------------------------------------------------------------
	def get_Quality(self, cell):
		result = 0
		quality = self._match_line(cell, "Quality=")
		if isinstance(quality, str):
			reg_quality = re.search(self._regex_Quality, quality)
			if reg_quality is not None:
				result = int(reg_quality.group(1))
		return result
	
	#----------------------------------------------------------------------
	def parse_cell(self, cell):
		rules = {
			"ESSID": self.get_ESSID, 
			"Encryption": self.get_Encryption, 
		    "Quality": self.get_Quality
		}
		parsed_cell = {}
		for item in rules.iteritems():
			parsed_cell.update({item[0]: item[1](cell)})
		return parsed_cell
	
	#----------------------------------------------------------------------
	def sort_cells(self, cells):
		sortby = "Quality"
		reverse = True
		cells.sort(None, lambda el:el[sortby], reverse)


#----------------------------------------------------------------------
def wifiParser():
	global _instance
	if _instance is None:
		_instance = WifiParse()
	return _instance


_instance2 = None
########################################################################
class SystemTimeMgt(threading.Thread):

	#----------------------------------------------------------------------
	def __init__(self, printer=None):
		threading.Thread.__init__(self)
		self.setDaemon(True)
		self._logger = logging.getLogger(__name__)
		self._printer = printer
		settings().set(["system", "setTimeFlag"], True)
		
		utcMilliSecs = self.getNetworkTime()
		if utcMilliSecs is None:
			utcMilliSecs = self.rCurrentTime()
		else:
			self.setSystemTimeZone()
		if utcMilliSecs is not None:
			self.setSystemTime(utcMilliSecs)
		
		self.start()
	
	#----------------------------------------------------------------------
	def setSystemTime(self, utcMilliSecs):
		if int(utcMilliSecs) <= int(time.time()):
			return
		utcMilliSecs = utcMilliSecs if isinstance(utcMilliSecs, float) else utcMilliSecs/1000.0
		tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst = time.localtime(utcMilliSecs)
		self.wCurrentTime(utcMilliSecs)
		if sys.platform == "darwin":
			pass
		elif sys.platform == "win32":
			try:
				import win32api
				win32api.SetSystemTime(tm_year, tm_mon, tm_wday, tm_mday, tm_hour, tm_min, tm_sec, 0)
			except: pass
		else:
			try:
				subprocess.check_output('sudo date -s "%d-%d-%d"' %(tm_year, tm_mon, tm_mday), shell=True)
				subprocess.check_output('sudo date -s "%d:%d:%d"' %(tm_hour, tm_min, tm_sec), shell=True)
			except: pass
		settings().set(["system", "setTimeFlag"], False)
	
	#----------------------------------------------------------------------
	def wCurrentTime(self, utcMilliSecs):
		with open(settings().getSystemTimeFile(), "w") as f:
			f.write(str(utcMilliSecs))
	
	#----------------------------------------------------------------------
	def rCurrentTime(self):
		utcMilliSecs = None
		try:
			with open(settings().getSystemTimeFile(), "r") as f:
				utcMilliSecs = float(f.readline().strip())
		except: pass
		return utcMilliSecs
		
	def setSystemTimeZone(self):
		try:
			#参考如下：
			#http://www.ophome.cn/question/22890
			#http://www.360doc.com/content/12/0511/11/2660674_210276794.shtml
			import urllib2, requests, glob
			ip = re.search('\d+\.\d+\.\d+\.\d+',urllib2.urlopen("http://www.whereismyip.com").read()).group(0)
			
			url = '{}/{}'.format("http://freegeoip.net/json/", ip)
			res = requests.get(url)
			res.raise_for_status()
			dat = res.json()
			
			tzfilepath = glob.glob("/usr/share/zoneinfo/{}".format(dat.get("time_zone")))[0]
			subprocess.check_output('sudo cp %s /etc/localtime' %tzfilepath, shell=True)
		except: pass
		
	#----------------------------------------------------------------------
	def getNetworkTime(self):
		def delay():
			try:
				import ntplib
				client = ntplib.NTPClient()
				response = client.request("time.windows.com")
				self._printer.mcLog("NetworkTime: %f" %float(response.tx_time))
				return response.tx_time
			except: return None

		temp = threading.Thread(target=delay)
		temp.daemon = True
		temp.start()
		return None
		
	def run(self):
		while True:
			try:
				self.wCurrentTime(time.time())
				time.sleep(30*60)
			except: pass


def systemTimeMgt(printer=None):
	global _instance2
	if _instance2 is None:
		_instance2 = SystemTimeMgt(printer)
	return _instance2


if __name__ == "__main__":
	wp = wifiParser()
	print wp.getAvailableWifiNames()
	print wp._parsed_cells
#add end
	
	
