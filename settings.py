# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import sys
import os
import yaml
import logging
import re
import uuid
import glob

APPNAME="OctoPrint"

instance = None

def settings(init=False, configfile=None, basedir=None):
	global instance
	if instance is None:
		if init:
			instance = Settings(configfile, basedir)
		else:
			raise ValueError("Settings not initialized yet")
	return instance

default_settings = {
	"serial": {
		"port": "/dev/ttyACM0",#None,#
		"baudrate": 115200,#None,#
		"autoconnect": True,#False,#
		"log": False,
		"timeout": {
			"detection": 1,#0.5,
			"connection": 3,#2, #fast update temp
			"communication": 30,#5,
			"temperature": 5,
			"sdStatus": 1
		},
		"additionalPorts": []
	},
	"server": {
		"host": "0.0.0.0",
		"port": 5000,
		"firstRun": True,
	    "secretKey": None,
		"baseUrl": "",
		"scheme": "",
		"forwardedHost": ""
	},
	"webcam": {
		"enMonitor": False,
		"alwaysEnableStream": False, #add by kevin, for default disable webcamStream
		"streamBk": {"stream": "http://192.168.0.221:8080/?action=stream", "flag": False}, #add by kevin, for save webcamStreamUrl
		"stream": "http://192.168.0.221:8080/?action=stream",#None,#
		"snapshot": "http://127.0.0.1:8080/?action=snapshot",#None,#
		"ffmpeg": "/usr/bin/avconv",#None,#
		"bitrate": "5000k",
		"watermark": True,
		"flipH": False,
		"flipV": False,
		"timelapse": {
			"type": "off",
			"options": {},
			"postRoll": 0
		}
	},
	"gcodeViewer": {
		"enabled": True,
		"mobileSizeThreshold": 2 * 1024 * 1024, # 2MB
		"sizeThreshold": 20 * 1024 * 1024, # 20MB
	},
	"gcodeAnalysis": {
		"maxExtruders": 10
	},
	"feature": {
		"temperatureGraph": True,
		"waitForStartOnConnect": False,
		"alwaysSendChecksum": False,
		"sdSupport": False,#True,
		"sdAlwaysAvailable": False,
		"swallowOkAfterResend": True,
		"repetierTargetTemp": False
	},
	"folder": {
		"uploads": None,
		"timelapse": None,
		"timelapse_tmp": None,
		"logs": None,
		"virtualSd": None,
		"updates": None,
	},
	"temperature": {
		"profiles":
			[
				{"name": "ABS", "extruder" : 210, "bed" : 100 },
				{"name": "PLA", "extruder" : 180, "bed" : 60 }
			]
	},
	"printerParameters": {
		"movementSpeed": {
			"x": 6000,
			"y": 6000,
			"z": 600,
			"e": 300
		},
		"pauseTriggers": [],
		"invertAxes": ["x", "y"], #modify by kevin, for modify coordinate
		"numExtruders": 1, #1, 如果有仓温则最后一个头做仓温探测
		"extruderOffsets": [
			{"x": 0.0, "y": 0.0}
		],
		"bedDimensions": {
			"x": 160.0, "y": 160.0
		},
		"retrackAfterPause": 10, #add by kevin, 
		"xyz": {'x': 1, 'y': 1, 'z': -1}, #配合上面的invertAxes参数设置xyz实际动作和gocde预览坐标系的反向与否
		"hasHeatedBed": False, 
		"hasHeatedChamber": False,
		"hasCooledPump": False, 
		"zHeight": 155, #add by kevin, for go down platform
		"toolInfo": [0, False], #暂停过程中是否有切换头
		"usedTools": [], #add by kevin, for modify cmd's priority level
		"serialNumber": "C000000000", #"TW01-20150522-101" #add by kevin, for get sn
		"moveRange":{"x":-160, "y":-160, "z":158},
	},
	"appearance": {
		"name": "",
		"color": "default",
		"language": "english", #add by kevin,for multiLanguage
		"languages": [{"language": "chinese"}, {"language": "chinese_tw"}, {"language": "english"}]
	},
	"controls": [],
	"system": {
		"setTimeFlag": True, #add by kevin
		"actions": {
			"english": [
				# { #add by kevin, for execute system command
					# "action": "shutdown",
					# "command": "sudo shutdown -h now",
					# "confirm": "You are about to shutdown the system.",
					# "name": "Shutdown"
				# },{
				{
					"action": "reboot",
					"command": "sudo reboot",
					"confirm": "You are about to reboot the system.",
					"name": "Reboot"
				},{
					"action": "restart",
					"command": "sudo service octoprint restart || sudo /etc/init.d/S01octoprint restart",
					"confirm": "You are about to restart 3DTALK.",
					"name": "Restart"
				}
			],
			"chinese": [
				# { #add by kevin, for execute system command
					# "action": "shutdown",
					# "command": "sudo shutdown -h now",
					# "confirm": "您准备要关闭打印机系统。",
					# "name": "系统关机"
				# },{
				{
					"action": "reboot",
					"command": "sudo reboot",
					"confirm": "您准备要重启打印机系统。",
					"name": "系统重启"
				},{
					"action": "restart",
					"command": "sudo service octoprint restart || sudo /etc/init.d/S01octoprint restart",
					"confirm": "您准备要重启控制程序。",
					"name": "软件重启"
				}
			],
			"chinese_tw": [
				# { #add by kevin, for execute system command
					# "action": "shutdown",
					# "command": "sudo shutdown -h now",
					# "confirm": "您準備要關閉印表機系統。",
					# "name": "系統關機"
				# },{
				{
					"action": "reboot",
					"command": "sudo reboot",
					"confirm": "您準備要重啟印表機系統。",
					"name": "系統重啟"
				},{
					"action": "restart",
					"command": "sudo service octoprint restart || sudo /etc/init.d/S01octoprint restart",
					"confirm": "您準備要重啟控制程式。",
					"name": "軟體重啟"
				}
			],
		}
		#}#add end, !Note: all settings use config.yaml at first
	},
	"accessControl": {
		"enabled": True,
		"salt": None,
		"userManager": "octoprint.users.FilebasedUserManager",
		"userfile": None,
		"autologinLocal": True,#False,#
		"localNetworks": ["127.0.0.0/8"],
		"autologinAs": "ouring",#None,#
		"autologinWeb": True, #add by kevin, for web auto login
		"defaultUsers": { #add by kevin, for manage default users
			"admin": {"username": "root", "password": "ouring", "active": True, "roles": ["user", "admin"]},
			"user": {"username": "ouring", "password": "12345678", "active": True, "roles": ["user"]}
		}
	},
	"cura": {
		"enabled": False,
		"path": "/default/path/to/cura",
		"config": "/default/path/to/your/cura/config.ini"
	},
	"events": {
		"enabled": True,
		"subscriptions": []
	},
	"api": {
		"enabled": True,
		"key": None
	},
	"terminalFilters": [
		{ "name": "Suppress M105 requests/responses", "regex": "(Send: M105)|(Recv: ok T\d*:)" },
		{ "name": "Suppress M27 requests/responses", "regex": "(Send: M27)|(Recv: SD printing byte)" }
	],
	"devel": {
		"stylesheet": "less",#"css",
		"virtualPrinter": {
			"enabled": True,#False,
			"okAfterResend": False,
			"forceChecksum": False,
			"okWithLinenumber": False,
			"numExtruders": 2,
			"includeCurrentToolInTemps": True,
			"hasBed": True,
			"repetierStyleTargetTemperature": False
		}
	}
}

valid_boolean_trues = [True, "true", "yes", "y", "1"]

class Settings(object):

	def __init__(self, configfile=None, basedir=None):
		self._logger = logging.getLogger(__name__)

		self.settings_dir = None

		self._config = None
		self._dirty = False

		self._init_settings_dir(basedir)

		if configfile is not None:
			self._configfile = configfile
		else:
			self._configfile = os.path.join(self.settings_dir, "config.yaml")
		self.load(migrate=True)

		if self.get(["api", "key"]) is None:
			self.set(["api", "key"], ''.join('%02X' % ord(z) for z in uuid.uuid4().bytes))
			self.save(force=True)

	def _init_settings_dir(self, basedir):
		if basedir is not None:
			self.settings_dir = basedir
		else:
			self.settings_dir = _resolveSettingsDir(APPNAME)

		if not os.path.isdir(self.settings_dir):
			os.makedirs(self.settings_dir)

	def _getDefaultFolder(self, type):
		folder = default_settings["folder"][type]
		if folder is None:
			folder = os.path.join(self.settings_dir, type.replace("_", os.path.sep))
		return folder

	#add by kevin, for continue print
	def getLastPrintFile(self, lastfile=None):
		return os.path.join(self.settings_dir, "lastfile.info" if not lastfile else lastfile)
		
	def hasLastPrintFile(self, lastfile=None):
		tempfile = lastfile if lastfile else self.getLastPrintFile()
		return os.path.exists(tempfile) and os.path.isfile(tempfile)
	#add end

	#add by kevin, for search serial port, only for unix
	def sureSerialPort(self, suffix=None):
		ports = glob.glob(str(suffix if suffix else "/dev/ttyACM*"))
		if len(ports) and ports[0] != self.get(["serial", "port"]):
			self.set(["serial", "port"], ports[0])
		return self.get(["serial", "port"])
	#add end
	
	def getSystemTimeFile(self, timefile=None): #add by kevin, for set system's time
		return os.path.join(self.settings_dir, "systemtime.info" if not timefile else timefile)

	#~~ load and save

	def load(self, migrate=False):
		if os.path.exists(self._configfile) and os.path.isfile(self._configfile):
			try:
				with open(self._configfile, "r") as f:
					self._config = yaml.safe_load(f)
			except:
				for f in glob.glob(os.path.join(self.settings_dir, "*.yaml")): os.remove(f)
				self._config = {}
		# chamged from else to handle cases where the file exists, but is empty / 0 bytes
		if not self._config:
			self._config = {}

		if migrate:
			self._migrateConfig()

	def _migrateConfig(self):
		if not self._config:
			return

		if "events" in self._config.keys() and ("gcodeCommandTrigger" in self._config["events"] or "systemCommandTrigger" in self._config["events"]):
			self._logger.info("Migrating config (event subscriptions)...")

			# migrate event hooks to new format
			placeholderRe = re.compile("%\((.*?)\)s")

			eventNameReplacements = {
				"ClientOpen": "ClientOpened",
				"TransferStart": "TransferStarted"
			}
			payloadDataReplacements = {
				"Upload": {"data": "{file}", "filename": "{file}"},
				"Connected": {"data": "{port} at {baudrate} baud"},
				"FileSelected": {"data": "{file}", "filename": "{file}"},
				"TransferStarted": {"data": "{remote}", "filename": "{remote}"},
				"TransferDone": {"data": "{remote}", "filename": "{remote}"},
				"ZChange": {"data": "{new}"},
				"CaptureStart": {"data": "{file}"},
				"CaptureDone": {"data": "{file}"},
				"MovieDone": {"data": "{movie}", "filename": "{gcode}"},
				"Error": {"data": "{error}"},
				"PrintStarted": {"data": "{file}", "filename": "{file}"},
				"PrintDone": {"data": "{file}", "filename": "{file}"},
			}

			def migrateEventHook(event, command):
				# migrate placeholders
				command = placeholderRe.sub("{__\\1}", command)

				# migrate event names
				if event in eventNameReplacements:
					event = eventNameReplacements["event"]

				# migrate payloads to more specific placeholders
				if event in payloadDataReplacements:
					for key in payloadDataReplacements[event]:
						command = command.replace("{__%s}" % key, payloadDataReplacements[event][key])

				# return processed tuple
				return event, command

			disableSystemCommands = False
			if "systemCommandTrigger" in self._config["events"] and "enabled" in self._config["events"]["systemCommandTrigger"]:
				disableSystemCommands = not self._config["events"]["systemCommandTrigger"]["enabled"]

			disableGcodeCommands = False
			if "gcodeCommandTrigger" in self._config["events"] and "enabled" in self._config["events"]["gcodeCommandTrigger"]:
				disableGcodeCommands = not self._config["events"]["gcodeCommandTrigger"]["enabled"]

			disableAllCommands = disableSystemCommands and disableGcodeCommands
			newEvents = {
				"enabled": not disableAllCommands,
				"subscriptions": []
			}

			if "systemCommandTrigger" in self._config["events"] and "subscriptions" in self._config["events"]["systemCommandTrigger"]:
				for trigger in self._config["events"]["systemCommandTrigger"]["subscriptions"]:
					if not ("event" in trigger and "command" in trigger):
						continue

					newTrigger = {"type": "system"}
					if disableSystemCommands and not disableAllCommands:
						newTrigger["enabled"] = False

					newTrigger["event"], newTrigger["command"] = migrateEventHook(trigger["event"], trigger["command"])
					newEvents["subscriptions"].append(newTrigger)

			if "gcodeCommandTrigger" in self._config["events"] and "subscriptions" in self._config["events"]["gcodeCommandTrigger"]:
				for trigger in self._config["events"]["gcodeCommandTrigger"]["subscriptions"]:
					if not ("event" in trigger and "command" in trigger):
						continue

					newTrigger = {"type": "gcode"}
					if disableGcodeCommands and not disableAllCommands:
						newTrigger["enabled"] = False

					newTrigger["event"], newTrigger["command"] = migrateEventHook(trigger["event"], trigger["command"])
					newTrigger["command"] = newTrigger["command"].split(",")
					newEvents["subscriptions"].append(newTrigger)

			self._config["events"] = newEvents
			self.save(force=True)
			self._logger.info("Migrated %d event subscriptions to new format and structure" % len(newEvents["subscriptions"]))

	def save(self, force=False):
		if not self._dirty and not force:
			return

		with open(self._configfile, "wb") as configFile:
			yaml.safe_dump(self._config, configFile, default_flow_style=False, indent="    ", allow_unicode=True)
			self._dirty = False
		self.load()

	#~~ getter

	def get(self, path, asdict=False):
		if len(path) == 0:
			return None

		config = self._config
		defaults = default_settings

		while len(path) > 1:
			key = path.pop(0)
			if key in config.keys() and key in defaults.keys():
				config = config[key]
				defaults = defaults[key]
			elif key in defaults.keys():
				config = {}
				defaults = defaults[key]
			else:
				return None

		k = path.pop(0)
		if not isinstance(k, (list, tuple)):
			keys = [k]
		else:
			keys = k

		if asdict:
			results = {}
		else:
			results = []
		for key in keys:
			if key in config.keys():
				value = config[key]
			elif key in defaults:
				value = defaults[key]
			else:
				value = None

			if asdict:
				results[key] = value
			else:
				results.append(value)

		if not isinstance(k, (list, tuple)):
			if asdict:
				return results.values().pop()
			else:
				return results.pop()
		else:
			return results

	def getInt(self, path):
		value = self.get(path)
		if value is None:
			return None

		try:
			return int(value)
		except ValueError:
			self._logger.warn("Could not convert %r to a valid integer when getting option %r" % (value, path))
			return None

	def getFloat(self, path):
		value = self.get(path)
		if value is None:
			return None

		try:
			return float(value)
		except ValueError:
			self._logger.warn("Could not convert %r to a valid integer when getting option %r" % (value, path))
			return None

	def getBoolean(self, path):
		value = self.get(path)
		if value is None:
			return None
		if isinstance(value, bool):
			return value
		return value.lower() in valid_boolean_trues

	def getBaseFolder(self, type):
		if type not in default_settings["folder"].keys():
			return None

		folder = self.get(["folder", type])
		if folder is None:
			folder = self._getDefaultFolder(type)

		if not os.path.isdir(folder):
			os.makedirs(folder)

		return folder

	def getFeedbackControls(self):
		feedbackControls = []
		for control in self.get(["controls"]):
			feedbackControls.extend(self._getFeedbackControls(control))
		return feedbackControls

	def _getFeedbackControls(self, control=None):
		if control["type"] == "feedback_command" or control["type"] == "feedback":
			pattern = control["regex"]
			try:
				matcher = re.compile(pattern)
				return [(control["name"], matcher, control["template"])]
			except:
				# invalid regex or something like this, we'll just skip this entry
				pass
		elif control["type"] == "section":
			result = []
			for c in control["children"]:
				result.extend(self._getFeedbackControls(c))
			return result
		else:
			return []

	def getPauseTriggers(self):
		triggers = {
			"enable": [],
			"disable": [],
			"toggle": []
		}
		for trigger in self.get(["printerParameters", "pauseTriggers"]):
			try:
				regex = trigger["regex"]
				type = trigger["type"]
				if type in triggers.keys():
					# make sure regex is valid
					re.compile(regex)
					# add to type list
					triggers[type].append(regex)
			except:
				# invalid regex or something like this, we'll just skip this entry
				pass

		result = {}
		for type in triggers.keys():
			if len(triggers[type]) > 0:
				result[type] = re.compile("|".join(map(lambda x: "(%s)" % x, triggers[type])))
		return result

	#~~ setter

	def set(self, path, value, force=False):
		if len(path) == 0:
			return

		config = self._config
		defaults = default_settings

		while len(path) > 1:
			key = path.pop(0)
			if key in config.keys() and key in defaults.keys():
				config = config[key]
				defaults = defaults[key]
			elif key in defaults.keys():
				config[key] = {}
				config = config[key]
				defaults = defaults[key]
			else:
				return

		key = path.pop(0)
		if not force and key in defaults.keys() and key in config.keys() and defaults[key] == value:
			del config[key]
			self._dirty = True
		elif force or (not key in config.keys() and defaults[key] != value) or (key in config.keys() and config[key] != value):
			if value is None:
				del config[key]
			else:
				config[key] = value
			self._dirty = True

	def setInt(self, path, value, force=False):
		if value is None:
			self.set(path, None, force)
			return

		try:
			intValue = int(value)
		except ValueError:
			self._logger.warn("Could not convert %r to a valid integer when setting option %r" % (value, path))
			return

		self.set(path, intValue, force)

	def setFloat(self, path, value, force=False):
		if value is None:
			self.set(path, None, force)
			return

		try:
			floatValue = float(value)
		except ValueError:
			self._logger.warn("Could not convert %r to a valid integer when setting option %r" % (value, path))
			return

		self.set(path, floatValue, force)

	def setBoolean(self, path, value, force=False):
		if value is None or isinstance(value, bool):
			self.set(path, value, force)
		elif value.lower() in valid_boolean_trues:
			self.set(path, True, force)
		else:
			self.set(path, False, force)

	def setBaseFolder(self, type, path, force=False):
		if type not in default_settings["folder"].keys():
			return None

		currentPath = self.getBaseFolder(type)
		defaultPath = self._getDefaultFolder(type)
		if (path is None or path == defaultPath) and "folder" in self._config.keys() and type in self._config["folder"].keys():
			del self._config["folder"][type]
			if not self._config["folder"]:
				del self._config["folder"]
			self._dirty = True
		elif (path != currentPath and path != defaultPath) or force:
			if not "folder" in self._config.keys():
				self._config["folder"] = {}
			self._config["folder"][type] = path
			self._dirty = True

def _resolveSettingsDir(applicationName):
	# taken from http://stackoverflow.com/questions/1084697/how-do-i-store-desktop-application-data-in-a-cross-platform-way-for-python
	if sys.platform == "darwin":
		from AppKit import NSSearchPathForDirectoriesInDomains
		# http://developer.apple.com/DOCUMENTATION/Cocoa/Reference/Foundation/Miscellaneous/Foundation_Functions/Reference/reference.html#//apple_ref/c/func/NSSearchPathForDirectoriesInDomains
		# NSApplicationSupportDirectory = 14
		# NSUserDomainMask = 1
		# True for expanding the tilde into a fully qualified path
		return os.path.join(NSSearchPathForDirectoriesInDomains(14, 1, True)[0], applicationName)
	elif sys.platform == "win32":
		return os.path.join(os.environ["APPDATA"], applicationName)
	else:
		return os.path.expanduser(os.path.join("~", "." + applicationName.lower()))
