#-*- coding=gbk -*-
__author__ = "_guess_"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import sys
import os
import yaml
import logging
import re
import uuid

APPNAME="UartScreen"

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
    "machine":{
            "available_languages":("chinese","chinese_tw","english"),
            "available_type":("3DTALK MINI","3DTALK II","3DTALK PRO400","3DTALK PRO600"),
            "current_language":"chinese",
            "current_type":"3DTALK MINI",
            "versons":"".center(12),
            "serialNumber":"".center(10)
            },
    "printerParameters":{
            "platform":{"x":155,"y":155,"z":160},
            "invertAxes":{"x":1,"y":1,"z":-1},
            "movementSpeed":{"x": 6000,"y": 6000,"z": 1200,"e": 300},
            "step":1
            },
    "filemanager":{
            "local":os.path.expanduser(os.path.join("~", ".octoprint/uploads")),
            "usb":os.path.expanduser(os.path.join("~", "udisk"))
            },
    "level_bed":{
            "level_speed":3200,
            "start":["G28","G21","G90"],
            "next":{0:"X75 Y22",1:"X130 Y130",2:"X20 Y130",3:None},
            "finish":["G1 Z145 F1500","G1 Y30 F9000","G28 X0"]
            },
    "material":{
            "init_action":["G21","G90","G28 X0 Y0","G1 X75 Y75 F3200","G1 Z155 F500"],
            "position":"X75 Y75"
            },
    "languaes":{
            "chinese":{None:"无连接","Operational":"已连接","Connecting":"连接中","Closed":"串口关闭","Offline":"串口断开","Printing":"打印中","Paused":"暂停","Opening serial port":"串口打开中"},
            "chinese_tw":{None:"无連接","Operational":"已連接","Connecting":"連接中","Closed":"串口關閉","Offline":"串口斷開","Printing":"列印中","Paused":"暫停","Opening serial port":"串口打開中"},
            "english":{None:"No Device","Operational":"Operational","Connecting":"Connecting","Closed":"Closed","Offline":"Offline","Printing":"Printing","Paused":"Paused","Opening serial port":"Opening port"}
            },
    "network":{
            "host_ip":"127.0.0.1",
            "broadcast":"255.255.255.255"
            },
    "connect":{
            "port":"VIRTUAL",
            "baudrate": "115200"
            },
    "status":{
            "error":False,
            "file_path":"local",
            "tool0_target":0,
            "tool1_target":0,
            "tool2_target":0,
            "bed_target":0,
            "target_temp":190,
            "last_set_temp":0,
            "tool":"tool0",
            "tool_step":1,
            "fan":"disable",
            "water_cooling":"disable",
            "chamber":"disable",
            "motor_disable":False
            },
    "page_jump":{
            #"check_jump":{"chinese":55,"english":56,"chinese_tw":57},
            "home_page":{"chinese":1,"english":20,"chinese_tw":37},
            "print_end":{"chinese":11,"english":28,"chinese_tw":45}, 
            "level_bed":{"chinese":7,"english":26,"chinese_tw":43},
            "update":{"chinese":10,"english":0,"chinese_tw":0},
            "material":{"chinese":0,"english":0,"chinese_tw":0}
    },
    "firstrun":True,
    "uart_display":{
            "languages":{"status":"\x00\x50"},
            "label":{"host_ip_text":"\x04\x00","stateString_text":"\x04\x10"},
            "homepage":{
                    "host_ip":"\x07\x00","stateString":"\x07\x10",
                    "tool0_actual":"\x07\x80","tool1_actual":"\x07\x90","tool2_actual":"\x07\xA0","bed_actual":"\x07\xB0",
                    "name":"\x07\x20",
                    "size":"\x07\x60",
                    "printTime":"\x07\x40",
                    "completion":"\x07\x50"
                    },
            "about":{"versons":"\x07\x70","serialNumber":"\x05\x20"},
            "print_paused":"\x00\x33",
            "pre_heat":"\x00\x4C",
            "water_cooling":"\x00\x4D",
            "tool0_takeback":"\x00\x3C","tool0_extrude":"\x00\x3E","tool1_takeback":"\x00\x3D","tool0_extrude":"\x00\x3F",
    }    
}

key_actions = {
        "action_time_init":"\x07",
	"print":{
                "action_file_path":'\x10',
                "action_slected_line":'\x11',
                "action_print_ctrl":"\x12",
                "action_value"		:'\x2D',
                "discrible"     :['\x00\xf3','\x01\xf3','\x02\xf3','\x03\xf3','\x04\xf3']
	},
	"settings":{
                "action_machine_type":'\x01',
                "action_language":'\x13',
                "action_level_bed":'\x14',
                "action_material":'\x15', 
                "action_temp_select"   :'\x60',
                "action_material_stop":'\x1B',
	},
	"advance":{
                "action_step":'\x16',
                "action_move":'\x17',
                "action_reset":'\x18',
                "action_switch":'\x19',
                "action_move_continuous":'\x1C',
                
		"direction":{
			"action_x_left_continuous"    :'\x0A',
			"action_x_right_continuous"   :'\x0B',
			"action_y_forward_continuous" :'\x0C',
			"action_y_backward_continuous":'\x0D',
			"action_z_up_continuous"      :'\x0E',
			"action_z_down_continuous"    :'\x0F',
		},
	},
        "action_setings":'\x1A',    
}

	
valid_boolean_trues = [True, "true", "yes", "y", "1"]





class Settings(object):

	def __init__(self, configfile=None, basedir=None):
		self._logger = logging.getLogger(__name__)

		self.settings_dir = None

		self._config = None
		self._dirty = False
		self.action_map = {}
		
		#if self.action_map is None:
		self._getkeyvalue(key_actions)		
		
		
		self._init_settings_dir(basedir)

		if configfile is not None:
			self._configfile = configfile
		else:
			self._configfile = os.path.join(self.settings_dir, "uartlcmconfig.yaml")
	
		self.load(migrate=True)
			
	def _getkeyvalue(self,key_action):
		if isinstance(key_action,dict):
			for key in key_action:
				if len(key_action[key])>1:
					self._getkeyvalue(key_action[key])
				else:
					self.action_map[key_action[key]]=key
					
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
	def get_config(self):
		return self._config

	#~~ load and save

	def load(self, migrate=False):
		if os.path.exists(self._configfile) and os.path.isfile(self._configfile):
			with open(self._configfile, "r") as f:
				self._config = yaml.safe_load(f)
		# chamged from else to handle cases where the file exists, but is empty / 0 bytes
		if not self._config:
			self._config = {}

		if migrate:
			self._migrateConfig()

	def _migrateConfig(self):
		if not self._config:
			self._config=default_settings
			self.save(force=True)
			self._logger.info("save default config")			
			return	
		

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

	#~~ setter
	def sets(self, path,keys,values,force=False):
		n=0
		for x in keys:
			temp=[]
			temp.append(x)
			#print path+temp,values[n]
			self.set(path+temp, values[n],force)
			n += 1
		
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
	if sys.platform == "darwin":
		from AppKit import NSSearchPathForDirectoriesInDomains
		return os.path.join(NSSearchPathForDirectoriesInDomains(14, 1, True)[0], applicationName)
	elif sys.platform == "win32":
		return os.path.join(os.environ["APPDATA"], applicationName)
	else:
		return os.path.expanduser(os.path.join("~", "." + applicationName.lower()))
