# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import os
import time
import logging
import subprocess

from flask import request, jsonify, make_response, url_for
from werkzeug.utils import secure_filename

from octoprint.util import getFreeBytes
from octoprint.util.firmwareInstall import InstallFirmware
from octoprint.settings import settings
from octoprint.printer import getConnectionOptions
from octoprint.uartScreen.datasync import DataSyncManager

from octoprint.server import gcodeManager
from octoprint.server import restricted_access, admin_permission, NO_CONTENT
from octoprint.server.api import api

#add ky keivn, for store wifi's info
from octoprint.server.util import wifiParser
#add end


currentProgress = 0
updateTimeout = 30*60 #second
updateStartTime = 0
last_filename = ""

#~~ settings


@api.route("/settings", methods=["GET"])
def getSettings():
	s = settings()

	[movementSpeedX, movementSpeedY, movementSpeedZ, movementSpeedE] \
		= s.get(["printerParameters", "movementSpeed", ["x", "y", "z", "e"]])

	connectionOptions = getConnectionOptions()

	return jsonify({
		"api": {
			"enabled": s.getBoolean(["api", "enabled"]),
			"key": s.get(["api", "key"])
		},
		"appearance": {
			"name": s.get(["appearance", "name"]),
			"color": s.get(["appearance", "color"]),
			"language": s.get(["appearance", "language"]), #add by kevin,for multiLanguage
			"languages": s.get(["appearance", "languages"])
		},
		"printer": {
			"movementSpeedX": movementSpeedX,
			"movementSpeedY": movementSpeedY,
			"movementSpeedZ": movementSpeedZ,
			"movementSpeedE": movementSpeedE,
			"invertAxes": s.get(["printerParameters", "invertAxes"]),
			"numExtruders": s.get(["printerParameters", "numExtruders"]),
			"extruderOffsets": s.get(["printerParameters", "extruderOffsets"]),
			"bedDimensions": s.get(["printerParameters", "bedDimensions"])
		},
		"webcam": {
			"alwaysEnableStream": s.get(["webcam", "alwaysEnableStream"]), #add by keivn, for default disable webcamStream
			"streamUrl": s.get(["webcam", "stream"]),
			"snapshotUrl": s.get(["webcam", "snapshot"]),
			"ffmpegPath": s.get(["webcam", "ffmpeg"]),
			"bitrate": s.get(["webcam", "bitrate"]),
			"watermark": s.getBoolean(["webcam", "watermark"]),
			"flipH": s.getBoolean(["webcam", "flipH"]),
			"flipV": s.getBoolean(["webcam", "flipV"])
		},
		"feature": {
			"gcodeViewer": s.getBoolean(["gcodeViewer", "enabled"]),
			"temperatureGraph": s.getBoolean(["feature", "temperatureGraph"]),
			"waitForStart": s.getBoolean(["feature", "waitForStartOnConnect"]),
			"alwaysSendChecksum": s.getBoolean(["feature", "alwaysSendChecksum"]),
			"sdSupport": s.getBoolean(["feature", "sdSupport"]),
			"sdAlwaysAvailable": s.getBoolean(["feature", "sdAlwaysAvailable"]),
			"swallowOkAfterResend": s.getBoolean(["feature", "swallowOkAfterResend"]),
			"repetierTargetTemp": s.getBoolean(["feature", "repetierTargetTemp"])
		},
		"serial": {
			"port": connectionOptions["portPreference"],
			"baudrate": connectionOptions["baudratePreference"],
			"portOptions": connectionOptions["ports"],
			"baudrateOptions": connectionOptions["baudrates"],
			"autoconnect": s.getBoolean(["serial", "autoconnect"]),
			"timeoutConnection": s.getFloat(["serial", "timeout", "connection"]),
			"timeoutDetection": s.getFloat(["serial", "timeout", "detection"]),
			"timeoutCommunication": s.getFloat(["serial", "timeout", "communication"]),
			"timeoutTemperature": s.getFloat(["serial", "timeout", "temperature"]),
			"timeoutSdStatus": s.getFloat(["serial", "timeout", "sdStatus"]),
			"log": s.getBoolean(["serial", "log"])
		},
		"folder": {
			"uploads": s.getBaseFolder("uploads"),
			"timelapse": s.getBaseFolder("timelapse"),
			"timelapseTmp": s.getBaseFolder("timelapse_tmp"),
			"logs": s.getBaseFolder("logs")
		},
		"temperature": {
			"profiles": s.get(["temperature", "profiles"])
		},
		"system": {
			"actions": s.get(["system", "actions", s.get(["appearance", "language"])]), #modify by kevin, for multiLanguage
			"events": s.get(["system", "events"])
		},
		"terminalFilters": s.get(["terminalFilters"]),
		"cura": {
			"enabled": s.getBoolean(["cura", "enabled"]),
			"path": s.get(["cura", "path"]),
			"config": s.get(["cura", "config"])
		}
	})


@api.route("/settings", methods=["POST"])
@restricted_access
@admin_permission.require(403)
def setSettings():
	if "application/json" in request.headers["Content-Type"]:
		data = request.json
		s = settings()

		language = s.get(["appearance", "language"]) #add by kevin,for multiLanguage

		if "api" in data.keys():
			if "enabled" in data["api"].keys(): s.set(["api", "enabled"], data["api"]["enabled"])
			if "key" in data["api"].keys(): s.set(["api", "key"], data["api"]["key"], True)

		if "appearance" in data.keys():
			if "name" in data["appearance"].keys(): s.set(["appearance", "name"], data["appearance"]["name"])
			if "color" in data["appearance"].keys(): s.set(["appearance", "color"], data["appearance"]["color"])
			if "language" in data["appearance"].keys(): s.set(["appearance", "language"], data["appearance"]["language"]) #add by kevin,for multiLanguage

		if "printer" in data.keys():
			if "movementSpeedX" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "x"], data["printer"]["movementSpeedX"])
			if "movementSpeedY" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "y"], data["printer"]["movementSpeedY"])
			if "movementSpeedZ" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "z"], data["printer"]["movementSpeedZ"])
			if "movementSpeedE" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "e"], data["printer"]["movementSpeedE"])
			if "invertAxes" in data["printer"].keys(): s.set(["printerParameters", "invertAxes"], data["printer"]["invertAxes"])
			if "numExtruders" in data["printer"].keys(): s.setInt(["printerParameters", "numExtruders"], data["printer"]["numExtruders"])
			if "extruderOffsets" in data["printer"].keys(): s.set(["printerParameters", "extruderOffsets"], data["printer"]["extruderOffsets"])
			if "bedDimensions" in data["printer"].keys(): s.set(["printerParameters", "bedDimensions"], data["printer"]["bedDimensions"])

		if "webcam" in data.keys():
			if "alwaysEnableStream" in data["webcam"].keys(): s.set(["webcam", "alwaysEnableStream"], data["webcam"]["alwaysEnableStream"]) #add by keivn, for default disable webcamStream
			if "streamUrl" in data["webcam"].keys(): s.set(["webcam", "stream"], data["webcam"]["streamUrl"])
			if "snapshotUrl" in data["webcam"].keys(): s.set(["webcam", "snapshot"], data["webcam"]["snapshotUrl"])
			if "ffmpegPath" in data["webcam"].keys(): s.set(["webcam", "ffmpeg"], data["webcam"]["ffmpegPath"])
			if "bitrate" in data["webcam"].keys(): s.set(["webcam", "bitrate"], data["webcam"]["bitrate"])
			if "watermark" in data["webcam"].keys(): s.setBoolean(["webcam", "watermark"], data["webcam"]["watermark"])
			if "flipH" in data["webcam"].keys(): s.setBoolean(["webcam", "flipH"], data["webcam"]["flipH"])
			if "flipV" in data["webcam"].keys(): s.setBoolean(["webcam", "flipV"], data["webcam"]["flipV"])

		if "feature" in data.keys():
			if "gcodeViewer" in data["feature"].keys(): s.setBoolean(["gcodeViewer", "enabled"], data["feature"]["gcodeViewer"])
			if "temperatureGraph" in data["feature"].keys(): s.setBoolean(["feature", "temperatureGraph"], data["feature"]["temperatureGraph"])
			if "waitForStart" in data["feature"].keys(): s.setBoolean(["feature", "waitForStartOnConnect"], data["feature"]["waitForStart"])
			if "alwaysSendChecksum" in data["feature"].keys(): s.setBoolean(["feature", "alwaysSendChecksum"], data["feature"]["alwaysSendChecksum"])
			if "sdSupport" in data["feature"].keys(): s.setBoolean(["feature", "sdSupport"], data["feature"]["sdSupport"])
			if "sdAlwaysAvailable" in data["feature"].keys(): s.setBoolean(["feature", "sdAlwaysAvailable"], data["feature"]["sdAlwaysAvailable"])
			if "swallowOkAfterResend" in data["feature"].keys(): s.setBoolean(["feature", "swallowOkAfterResend"], data["feature"]["swallowOkAfterResend"])
			if "repetierTargetTemp" in data["feature"].keys(): s.setBoolean(["feature", "repetierTargetTemp"], data["feature"]["repetierTargetTemp"])

		if "serial" in data.keys():
			if "autoconnect" in data["serial"].keys(): s.setBoolean(["serial", "autoconnect"], data["serial"]["autoconnect"])
			if "port" in data["serial"].keys(): s.set(["serial", "port"], data["serial"]["port"])
			if "baudrate" in data["serial"].keys(): s.setInt(["serial", "baudrate"], data["serial"]["baudrate"])
			if "timeoutConnection" in data["serial"].keys(): s.setFloat(["serial", "timeout", "connection"], data["serial"]["timeoutConnection"])
			if "timeoutDetection" in data["serial"].keys(): s.setFloat(["serial", "timeout", "detection"], data["serial"]["timeoutDetection"])
			if "timeoutCommunication" in data["serial"].keys(): s.setFloat(["serial", "timeout", "communication"], data["serial"]["timeoutCommunication"])
			if "timeoutTemperature" in data["serial"].keys(): s.setFloat(["serial", "timeout", "temperature"], data["serial"]["timeoutTemperature"])
			if "timeoutSdStatus" in data["serial"].keys(): s.setFloat(["serial", "timeout", "sdStatus"], data["serial"]["timeoutSdStatus"])

			oldLog = s.getBoolean(["serial", "log"])
			if "log" in data["serial"].keys(): s.setBoolean(["serial", "log"], data["serial"]["log"])
			if oldLog and not s.getBoolean(["serial", "log"]):
				# disable debug logging to serial.log
				logging.getLogger("SERIAL").debug("Disabling serial logging")
				logging.getLogger("SERIAL").setLevel(logging.CRITICAL)
			elif not oldLog and s.getBoolean(["serial", "log"]):
				# enable debug logging to serial.log
				logging.getLogger("SERIAL").setLevel(logging.DEBUG)
				logging.getLogger("SERIAL").debug("Enabling serial logging")

		if "folder" in data.keys():
			if "uploads" in data["folder"].keys(): s.setBaseFolder("uploads", data["folder"]["uploads"])
			if "timelapse" in data["folder"].keys(): s.setBaseFolder("timelapse", data["folder"]["timelapse"])
			if "timelapseTmp" in data["folder"].keys(): s.setBaseFolder("timelapse_tmp", data["folder"]["timelapseTmp"])
			if "logs" in data["folder"].keys(): s.setBaseFolder("logs", data["folder"]["logs"])

		if "temperature" in data.keys():
			if "profiles" in data["temperature"].keys(): s.set(["temperature", "profiles"], data["temperature"]["profiles"])

		if "terminalFilters" in data.keys():
			s.set(["terminalFilters"], data["terminalFilters"])

		if "system" in data.keys():
			# if "actions" in data["system"].keys(): s.set(["system", "actions", language], data["system"]["actions"])
			if "events" in data["system"].keys(): s.set(["system", "events"], data["system"]["events"])

		cura = data.get("cura", None)
		if cura:
			path = cura.get("path")
			if path:
				s.set(["cura", "path"], path)

			config = cura.get("config")
			if config:
				s.set(["cura", "config"], config)

			# Enabled is a boolean so we cannot check that we have a result
			enabled = cura.get("enabled")
			s.setBoolean(["cura", "enabled"], enabled)

		s.save()

	return getSettings()

#add by kevin, for update our progress
@api.route("/getUpdateFiles", methods=["GET"])
def getUpdateFiles():
	return jsonify(files=_getUpdateFiles(), free=getFreeBytes(settings().getBaseFolder("updates")))


@api.route("/updateProgress", methods=["GET"])
@restricted_access
def updateProgress():
	global currentProgress
	global updateStartTime
	global updateTimeout

	#print "has updated:", currentProgress
	tmpCurrentProgress = currentProgress
	if currentProgress >= 100 or time.time() > updateStartTime + updateTimeout: 
		currentProgress = 0
		tmpCurrentProgress = 100
	return jsonify(updatedPercent=tmpCurrentProgress)


@api.route("/updates/<path:filename>", methods=["DELETE", "POST"])
@restricted_access
@admin_permission.require(403)
def dealUpdateFile(filename):
	secure_absolutePath = os.path.join(settings().getBaseFolder("updates"), secure_filename(filename))
	if not os.path.exists(secure_absolutePath):
		return make_response("File not found: %s" % filename, 404)

	global currentProgress
	global updateStartTime
	global last_filename

	last_filename = filename

	if request.method == "DELETE":
		if filename != last_filename:
			return make_response("After completion of ongoing updates, please wait try again!", 400)
		os.remove(secure_absolutePath)
	elif request.method == "POST":
		if currentProgress > 0 and currentProgress < 100:
			return make_response("After completion of ongoing updates, please wait try again!", 400)
		currentProgress = 1
		updateStartTime = time.time()
		prefix = filter(lambda x: filename.startswith(x), ("OctoPrint", "Repetier",  "UartScreen"))
		if not len(prefix):
			return make_response("File doesn't have a valid prefix!", 400)

		if filename.startswith("OctoPrint"):
			pass
		elif filename.startswith("Repetier"):
			InstallFirmware(secure_absolutePath, progressCallback=_onUpdateProgress)
		elif filename.startswith("UartScreen"):
			pass

	return NO_CONTENT


@api.route("/uploadUpdateFile", methods=["POST"])
@restricted_access
@admin_permission.require(403)
def uploadUpdateFile():
	if len(_getUpdateFiles()) >= 5:
		return make_response("Please remove some old packages!", 400)

	if not "file" in request.files.keys():
		return make_response("No file included", 400)

	file = request.files["file"]

	exts = filter(lambda x: file.filename.lower().endswith(x), (".zip", ".hex",  ".3dt"))
	if not len(exts):
		return make_response("File doesn't have a valid extension!", 400)

	filename, done = gcodeManager.addUpdateFile(file)

	return make_response(jsonify(files=_getUpdateFiles(), done=done), 201)
#add end


@api.route("/settings/language", methods=["POST"])

def setLanguage():
	if "application/json" in request.headers["Content-Type"]:
		data = request.json
		s = settings()

		if "appearance" in data.keys() and "language" in data["appearance"].keys():
			s.set(["appearance", "language"], data["appearance"]["language"])

		s.save()

	return NO_CONTENT

	
@api.route("/settings/getAvailableWifiNames", methods=["GET"])
def getAvailableWifiNames():
	return jsonify({"wifiNames": wifiParser().getAvailableWifiNames()})
	

@api.route("/settings/system/factoryReset", methods=["POST"])
@restricted_access
@admin_permission.require(403)
def factoryReset():
	try:
		subprocess.check_output("sudo ~/oprint/bin/config_octo r", shell=True)
	except: pass
	
	return NO_CONTENT


@api.route("/settings/system/clearUserData", methods=["POST"])
@restricted_access
@admin_permission.require(403)
def clearUserData():
	try:
		subprocess.check_output("sudo ~/oprint/bin/config_octo w", shell=True)
	except: pass

	return NO_CONTENT


@api.route("/settings/system/setWifi", methods=["POST"])
def setWifi():
	if not "application/json" in request.headers["Content-Type"]:
		return make_response("Expected content type JSON", 400)

	data = request.json
	
	try: _setWifi(data)
	except: pass
			
	return NO_CONTENT
	

def _setWifi(data):
	if "ssid" in data.keys() and "password" in data.keys() and "flag" in data.keys():
		if "connect" == data["flag"]:
			_writeWifiInfo(data["ssid"], data["password"], data["flag"])
			#subprocess.check_output("sudo ~/oprint/bin/config_octo c", shell=True)
		elif "create" == data["flag"] and len(data["ssid"]) > 0 and len(data["password"]) > 7:
			_writeWifiInfo(data["ssid"], data["password"], data["flag"])
			#subprocess.check_output("sudo ~/oprint/bin/config_octo o", shell=True)
	elif "create" == data.get("flag"):
		#subprocess.check_output("sudo ~/oprint/bin/config_octo d", shell=True)
		subprocess.check_output("sudo create_wifi".format(data["ssid"],data["password"]), shell=True)


def _writeWifiInfo(ssid, password, flag):
	if ssid and password and flag:
		ifacefile = ""
		interface = [
			"auto lo\n",
			"iface lo inet loopback\n\n",
			"auto eth0\n",
			"iface eth0 inet static\n",
			"address 192.168.2.221\n",
			"netmask 255.255.255.0\n\n",
			"auto wlan0\n",
			"allow-hotplug wlan0\n"
		]

		if "connect" == flag:
			enc = "WPA"
			for cell in wifiParser()._parsed_cells:
				if isinstance(cell, dict) and ssid in cell.values():
					enc = cell.get("Encryption")
					break
			enc_flag = []
			if enc == "WEP":
				#enc_flag = wifiParser()._enc_map.get("wep")
				subprocess.check_output("sudo connect_wifi_wep {0} {1}".format(ssid,password), shell=True)
				DataSyncManager().reloadip()
			elif enc == "OPEN":
				pass#enc_flag = wifiParser()._enc_map.get("open")
			else:
				#enc_flag = wifiParser()._enc_map.get("wpa")
				subprocess.check_output("sudo connect_wifi_wpa {0} {1}".format(ssid,password), shell=True)
				DataSyncManager().reloadip()
			# interface.append("iface wlan0 inet dhcp\n\n")
			# interface.append("{0} {1}\n".format(enc_flag[0], ssid))
			# if enc != "OPEN" and len(password) >= 8:
				# interface.append("{0} {1}\n".format(enc_flag[1], password))
			# ifacefile = "interfaces_bk"
		elif "create" == flag:
			subprocess.check_output("sudo create_wifi {0} {1}".format(ssid,password), shell=True)
			# interface.append("iface wlan0 inet static\n")
			# interface.append("address 192.168.0.221\n")
			# interface.append("netmask 255.255.255.0\n\n")
			# interface.append("up iptables-restore < /etc/iptables.ipv4.nat\n")
			# ifacefile = "interfaces_ap"
			
			# hostapd = [
				# "interface=wlan0\n",
				# "channel=6\n",
				# "ssid={0}\n\n".format(ssid),
				# "auth_algs=1\n",
				# "macaddr_acl=0\n",
				# "wmm_enabled=0\n",
				# "wpa=2\n",
				# "wpa_key_mgmt=WPA-PSK\n",
				# "wpa_pairwise=TKIP\n",
				# "rsn_pairwise=CCMP\n",
				# "wpa_passphrase={0}\n\n".format(password),
				# "driver=rtl871xdrv\n\n",
				# "hw_mode=g\n",
				# "ignore_broadcast_ssid=0\n"
			# ]
			
			# with open("/tmp/hostapd.conf", "w") as f:
				# for line in hostapd:
					# f.write(line)
		
		# with open("/tmp/{0}".format(ifacefile), "w") as f:
			# for line in interface:
				# f.write(line)


def _getUpdateFiles():
	files = []
	basedir = settings().getBaseFolder("updates")
	for osFile in os.listdir(basedir):
		statResult = os.stat(os.path.join(basedir, osFile))
		files.append({
			"name": osFile,
			"date": int(statResult.st_mtime),
			"size": statResult.st_size
		})

	return files


def _onUpdateProgress(value, max):
	global currentProgress
	currentProgress = int(round(((value+0.0)/max)*100))
	#print "value=%d, max=%d, %f" %(value, max, currentProgress)
	#print ">"*int(currentProgress)