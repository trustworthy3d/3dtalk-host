# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import flask
import tornado.wsgi
from sockjs.tornado import SockJSRouter
from flask import Flask, render_template, send_from_directory, make_response
from flask.ext.login import LoginManager
from flask.ext.principal import Principal, Permission, RoleNeed, identity_loaded, UserNeed

import re
import os
import logging
import logging.config

SUCCESS = {}
NO_CONTENT = ("", 204)

app = Flask("octoprint")
debug = False

printer = None
gcodeManager = None
userManager = None
eventManager = None
loginManager = None

principals = Principal(app)
admin_permission = Permission(RoleNeed("admin"))
user_permission = Permission(RoleNeed("user"))

# only import the octoprint stuff down here, as it might depend on things defined above to be initialized already
from octoprint.server.util import LargeResponseHandler, ReverseProxied, restricted_access, PrinterStateConnection, admin_validator
from octoprint.printer import Printer, getConnectionOptions
from octoprint.settings import settings
import octoprint.gcodefiles as gcodefiles
import octoprint.util as util
import octoprint.users as users
import octoprint.events as events
import octoprint.timelapse
import octoprint._version

from octoprint.server.util import systemTimeMgt
uartScreen = None #add by kevin, for uartScreen

versions = octoprint._version.get_versions()
VERSION = versions['version']
BRANCH = versions['branch'] if 'branch' in versions else None
DISPLAY_VERSION = "%s (%s branch)" % (VERSION, BRANCH) if BRANCH else VERSION
del versions


#another way
@app.route("/threeDtalk")
def threeDtalk():
	return "3DTALK"
#add end
		

@app.route("/")
def index():
	#add by kevin,for multiLanguage
	language = settings().get(["appearance","language"])
	if "chinese" == language:
		index = "index_cn.jinja2.html"
	elif "chinese_tw" == language:
		index = "index_zh-tw.jinja2.html"
	elif "english" == language:
		index = "index_en.jinja2.html"
	else:
		index = "index_cn.jinja2.html"
	#add end,multiLanguage

	#add by kevin, for control webcamStream
	streamUrl = settings().get(["webcam", "stream"])

	wlan0_ip = getLocalIp("wlan0")
	if wlan0_ip:
		streamUrl = re.sub(r"(//\d+\.\d+\.\d+\.\d+:|//\w+:)", "//" + str(wlan0_ip) + ":", streamUrl)
		settings().set(["webcam", "stream"], streamUrl)

	if settings().get(["webcam", "streamBk", "flag"]) is True:
		if re.search(r"\d+\.\d+\.\d+\.\d+", streamUrl) is not None:
			settings().set(["webcam", "stream"], "http://your_printer_ip:8080/?action=stream")
			
	settings().set(["webcam", "streamBk", "flag"], True)
	#add end, for webcamStream
	
	return render_template(
		index, #modify by kevin
		alwaysEnableStream=settings().get(["webcam", "alwaysEnableStream"]), #add by keivn, for default disable webcamStream
		webcamStream=(settings().get(["webcam", "stream"]) and settings().get(["webcam", "enMonitor"])),
		enableTimelapse=(settings().get(["webcam", "snapshot"]) is not None and settings().get(["webcam", "ffmpeg"]) is not None and settings().get(["webcam", "enMonitor"])),
		enableGCodeVisualizer=settings().get(["gcodeViewer", "enabled"]),
		enableTemperatureGraph=settings().get(["feature", "temperatureGraph"]),
		enableSystemMenu=settings().get(["system"]) is not None and settings().get(["system", "actions", language]) is not None and len(settings().get(["system", "actions", language])) > 0, #modify by kevin, for multiLanguage
		enableAccessControl=userManager is not None,
		enableSdSupport=settings().get(["feature", "sdSupport"]),
		firstRun=settings().getBoolean(["server", "firstRun"]) and (userManager is None or not userManager.hasBeenCustomized()),
		debug=debug,
		version=VERSION,
		display_version=DISPLAY_VERSION,
		stylesheet=settings().get(["devel", "stylesheet"]),
		gcodeMobileThreshold=settings().get(["gcodeViewer", "mobileSizeThreshold"]),
		gcodeThreshold=settings().get(["gcodeViewer", "sizeThreshold"]),
		language=language,
		disableSimple=False,
		afterLogedin=True,
		xyz=settings().get(["printerParameters", "xyz"], {'x': 1, 'y': 1, 'z': 1}),
		hasHeatedBed=settings().get(["printerParameters", "hasHeatedBed"]),
		hasHeatedChamber=settings().get(["printerParameters", "hasHeatedChamber"]),
		hasCooledPump=settings().get(["printerParameters", "hasCooledPump"]),
		getTimeFromClient=settings().get(["system", "setTimeFlag"])
	)


@app.route("/robots.txt")
def robotsTxt():
	return send_from_directory(app.static_folder, "robots.txt")


@identity_loaded.connect_via(app)
def on_identity_loaded(sender, identity):
	user = load_user(identity.id)
	if user is None:
		return

	identity.provides.add(UserNeed(user.get_name()))
	if user.is_user():
		identity.provides.add(RoleNeed("user"))
	if user.is_admin():
		identity.provides.add(RoleNeed("admin"))


def load_user(id):
	if userManager is not None:
		return userManager.findUser(id)
	return users.DummyUser()


#add by kevin, for get local ipaddr

import socket, struct
try:
	import fcntl
except:
	pass

def getLocalIp(ifname="wlan0"):
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		return socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915,struct.pack('256s', ifname[:15]))[20:24])
	except:
		err = "Can't assign requested address"
		return None
	
#add end


#~~ startup code


class Server():
	def __init__(self, configfile=None, basedir=None, host="0.0.0.0", port=5000, 
	             debug=False, allowRoot=False, sus=True):
		self._configfile = configfile
		self._basedir = basedir
		self._host = host
		self._port = port
		self._debug = debug
		self._allowRoot = allowRoot
		self._startUartScreen = sus
		
	def run(self):
		if not self._allowRoot:
			self._checkForRoot()

		global printer
		global gcodeManager
		global userManager
		global eventManager
		global loginManager
		global debug

		from tornado.wsgi import WSGIContainer
		from tornado.httpserver import HTTPServer
		from tornado.ioloop import IOLoop
		from tornado.web import Application, FallbackHandler

		debug = self._debug

		# first initialize the settings singleton and make sure it uses given configfile and basedir if available
		self._initSettings(self._configfile, self._basedir)
		
		# then initialize logging
		self._initLogging(self._debug)
		logger = logging.getLogger(__name__)

		logger.info("Starting OctoPrint %s" % DISPLAY_VERSION)

		eventManager = events.eventManager()
		gcodeManager = gcodefiles.GcodeManager()
		printer = Printer(gcodeManager)

		# configure timelapse
		octoprint.timelapse.configureTimelapse()

		# setup command triggers
		events.CommandTrigger(printer)
		if self._debug:
			events.DebugEventListener()

		if settings().getBoolean(["accessControl", "enabled"]):
			userManagerName = settings().get(["accessControl", "userManager"])
			try:
				clazz = util.getClass(userManagerName)
				userManager = clazz()
			except AttributeError, e:
				logger.exception("Could not instantiate user manager %s, will run with accessControl disabled!" % userManagerName)

		app.wsgi_app = ReverseProxied(app.wsgi_app)

		secret_key = settings().get(["server", "secretKey"])
		if not secret_key:
			import string
			from random import choice
			chars = string.ascii_lowercase + string.ascii_uppercase + string.digits
			secret_key = "".join(choice(chars) for _ in xrange(32))
			settings().set(["server", "secretKey"], secret_key)
			settings().save()
		app.secret_key = secret_key
		loginManager = LoginManager()
		loginManager.session_protection = "strong"
		loginManager.user_callback = load_user
		if userManager is None:
			loginManager.anonymous_user = users.DummyUser
			principals.identity_loaders.appendleft(users.dummy_identity_loader)
		loginManager.init_app(app)

		if self._host is None:
			self._host = settings().get(["server", "host"])
		if self._port is None:
			self._port = settings().getInt(["server", "port"])
			
		systemTimeMgt(printer) #add by kevin, for set system's time
		#add by kevin, set default users
		if settings().getBoolean(["server", "firstRun"]) and userManager is not None:
			logger.info("Initialize defaults users")
			settings().setBoolean(["accessControl", "enabled"], True)
			try:
				for user in settings().get(["accessControl", "defaultUsers"]).itervalues():
					userManager.addUser(user["username"], user["password"], user["active"], user["roles"])
			except: pass
			settings().setBoolean(["server", "firstRun"], False)
			settings().save()
		#add end

		logger.info("Listening on http://%s:%d" % (self._host, self._port))
		app.debug = self._debug

		from octoprint.server.api import api

		app.register_blueprint(api, url_prefix="/api")

		self._router = SockJSRouter(self._createSocketConnection, "/sockjs")

		def admin_access_validation(request):
			"""
			Creates a custom wsgi and Flask request context in order to be able to process user information
			stored in the current session.

			:param request: The Tornado request for which to create the environment and context
			"""
			wsgi_environ = tornado.wsgi.WSGIContainer.environ(request)
			with app.request_context(wsgi_environ):
				app.session_interface.open_session(app, flask.request)
				loginManager.reload_user()
				admin_validator(flask.request)

		self._tornado_app = Application(self._router.urls + [
			(r"/downloads/timelapse/([^/]*\.mpg)", LargeResponseHandler, {"path": settings().getBaseFolder("timelapse"), "as_attachment": True}),
			(r"/downloads/files/local/([^/]*\.(gco|gcode|g|3dt))", LargeResponseHandler, {"path": settings().getBaseFolder("uploads"), "as_attachment": True}),
			(r"/downloads/logs/([^/]*)", LargeResponseHandler, {"path": settings().getBaseFolder("logs"), "as_attachment": True, "access_validation": admin_access_validation}),
			(r".*", FallbackHandler, {"fallback": WSGIContainer(app.wsgi_app)})
		])
		self._server = HTTPServer(self._tornado_app)
		self._server.listen(self._port, address=self._host)

		eventManager.fire(events.Events.STARTUP)
		if settings().getBoolean(["serial", "autoconnect"]):
			(port, baudrate) = settings().get(["serial", "port"]), settings().getInt(["serial", "baudrate"])
			connectionOptions = getConnectionOptions()
			if port in connectionOptions["ports"]:
				printer.connect(port, baudrate)
		
		#add by kevin, for uartScreen
		try:
			global uartScreen
			if self._startUartScreen in (True, "true"):
				try:
					from octoprint.uartScreen import uartScreenManager
				#add by slc, for update uartscreen
				except:
					from octoprint.uartScreen_backup import uartScreenManager
				#add end
				uartScreen = uartScreenManager(port=self._port)
		except:
			logger.error("There are some unexpected error, when start uartScreen")
		#add end
		
		try:
			IOLoop.instance().start()
		except KeyboardInterrupt:
			logger.info("Goodbye!")
		except:
			logger.fatal("Now that is embarrassing... Something really really went wrong here. Please report this including the stacktrace below in OctoPrint's bugtracker. Thanks!")
			logger.exception("Stacktrace follows:")

	def _createSocketConnection(self, session):
		global printer, gcodeManager, userManager, eventManager
		return PrinterStateConnection(printer, gcodeManager, userManager, eventManager, session)

	def _checkForRoot(self):
		if "geteuid" in dir(os) and os.geteuid() == 0:
			exit("You should not run OctoPrint as root!")

	def _initSettings(self, configfile, basedir):
		settings(init=True, basedir=basedir, configfile=configfile)

	def _initLogging(self, debug):
		config = {
			"version": 1,
			"formatters": {
				"simple": {
					"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
				}
			},
			"handlers": {
				"console": {
					"class": "logging.StreamHandler",
					"level": "DEBUG",
					"formatter": "simple",
					"stream": "ext://sys.stdout"
				},
				"file": {
					"class": "logging.handlers.TimedRotatingFileHandler",
					"level": "DEBUG",
					"formatter": "simple",
					"when": "D",
					"backupCount": "1",
					"filename": os.path.join(settings().getBaseFolder("logs"), "octoprint.log")
				},
				"serialFile": {
					"class": "logging.handlers.RotatingFileHandler",
					"level": "DEBUG",
					"formatter": "simple",
					"maxBytes": 2 * 1024 * 1024, # let's limit the serial log to 2MB in size
					"filename": os.path.join(settings().getBaseFolder("logs"), "serial.log")
				}
			},
			"loggers": {
				#"octoprint.timelapse": {
				#	"level": "DEBUG"
				#},
				#"octoprint.events": {
				#	"level": "DEBUG"
				#},
				"SERIAL": {
					"level": "CRITICAL",
					"handlers": ["serialFile"],
					"propagate": False
				}
			},
			"root": {
				"level": "INFO",
				"handlers": ["console", "file"]
			}
		}

		if debug:
			config["root"]["level"] = "DEBUG"

		logging.config.dictConfig(config)

		if settings().getBoolean(["serial", "log"]):
			# enable debug logging to serial.log
			logging.getLogger("SERIAL").setLevel(logging.DEBUG)
			logging.getLogger("SERIAL").debug("Enabling serial logging")

if __name__ == "__main__":
	octoprint = Server()
	octoprint.run()
