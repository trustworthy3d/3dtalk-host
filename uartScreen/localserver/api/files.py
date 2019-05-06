# coding=utf-8
from octoprint.events import Events

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import octoprint.gcodefiles as gcodefiles

from octoprint.filemanager.destinations import FileDestinations
from octoprint.settings import settings, valid_boolean_trues
from octoprint.server import printer, gcodeManager, eventManager

import api_util as util
from api_util import make_response,NO_CONTENT


#~~ GCODE file handling

def _verifyFileExists(origin, filename):
	if origin == FileDestinations.SDCARD:
		availableFiles = printer.getSdFiles()
	else:
		#modify by kevin, for different path
		availableFiles = gcodeManager.getAllFilenames(gcodeManager._uploadFolder)
		#modify end
	return filename in availableFiles

def gcodeFileCommand(filename=None, target=None,request=None):
	if not target in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		return make_response("Unknown target: %s" % target, 404)

	# not _verifyFileExists(target, filename):
		#return make_response("File not found on '%s': %s" % (target, filename), 404)

	filepath = gcodeManager._uploadFolder
	verifyResult = _verifyFileExists(target, filename)
	if verifyResult and gcodeManager._uploadFolder == gcodeManager._usbpath:
		filename = gcodeManager.startThreadToCopyFile(filename, timeout=3*60) #wait for 3 mins
		fileTempPath = gcodeManager._usbpath
		gcodeManager._uploadFolder = gcodeManager._localpath
	elif not verifyResult and gcodeManager._uploadFolder == gcodeManager._usbpath:
		fileTempPath = gcodeManager._usbpath
		gcodeManager._uploadFolder = gcodeManager._localpath
		
		if not _verifyFileExists(target, filename):
			gcodeManager._uploadFolder = filepath
			return make_response("File not found on '%s': %s" % (target, filename), 404)
	elif not verifyResult:
		return make_response("File not found on '%s': %s" % (target, filename), 404)		
		
	# valid file commands, dict mapping command name to mandatory parameters
	valid_commands = {
		"select": []
	}

	command, data, response = util.getJsonCommandFromRequest(request, valid_commands)
	#print "gcodeFileCommand",filename,target,command, data, response,"gcodeFileCommand"
	#if response is not None:
		#3return response
		
	if response is not None:
		gcodeManager._uploadFolder = filepath
		return response

	if command == "select":
		# selects/loads a file
		printAfterLoading = False
		if "print" in data.keys() and data["print"]:
			if not printer.isOperational():
				gcodeManager._uploadFolder = filepath
				return make_response("Printer is not operational, cannot directly start printing", 409)
			printAfterLoading = True

		sd = False
		if target == FileDestinations.SDCARD:
			filenameToSelect = filename
			sd = True
		else:
			filenameToSelect = gcodeManager.getAbsolutePath(filename)
		printer.selectFile(filenameToSelect, sd, printAfterLoading)
	gcodeManager._uploadFolder = filepath
	return NO_CONTENT

def deleteGcodeFile(filename=None, target=None):
	if not target in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		return make_response("Unknown target: %s" % target, 404)

	if not _verifyFileExists(target, filename):
		return make_response("File not found on '%s': %s" % (target, filename), 404)

	sd = target == FileDestinations.SDCARD

	currentJob = printer.getCurrentJob()
	currentFilename = None
	currentSd = None
	if currentJob is not None and "filename" in currentJob.keys() and "sd" in currentJob.keys():
		currentFilename = currentJob["filename"]
		currentSd = currentJob["sd"]

	# prohibit deleting the file that is currently being printed
	if currentFilename == filename and currentSd == sd and (printer.isPrinting() or printer.isPaused()):
		make_response("Trying to delete file that is currently being printed: %s" % filename, 409)

	# deselect the file if it's currently selected
	if currentFilename is not None and filename == currentFilename:
		printer.unselectFile()

	# delete it
	if sd:
		printer.deleteSdFile(filename)
	else:
		gcodeManager.removeFile(filename)

	return NO_CONTENT

def changeFilesPath(data=None):
	#modify by kevin, for use json format
	if data is None:
		return make_response("Expected content type JSON", 400)
	
	print "changeFilesPath",data,"changeFilesPath"

	if "filespath" in data.keys():
		if "local" == data["filespath"]:
			gcodeManager._uploadFolder = gcodeManager._localpath
		elif "usb" == data["filespath"]:
			gcodeManager._uploadFolder = gcodeManager._usbpath
	#modify end
			
	if "returnFiles" in data.keys() and data.get("returnFiles") is True:
		files = _getFileList(FileDestinations.LOCAL)
		files.extend(_getFileList(FileDestinations.SDCARD))
		return jsonify(files=files, free=util.getFreeBytes(gcodeManager._uploadFolder))
	
	return NO_CONTENT

def copyFile(data=None):
	if data is None:
		return make_response("Expected content type JSON", 400)
	
	target = None
	filename = None
	
	if "target" in data.keys():
		target = data["target"]
	
	if "filename" in data.keys():
		filename = data["filename"]

	if not _verifyFileExists(target, filename):
		return make_response("File not found on '%s': %s" % (target, filename), 404)
	else:
		gcodeManager.startThreadToCopyFile(filename)
		
	return NO_CONTENT

