# coding=utf-8
from octoprint.events import Events

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

from flask import request, jsonify, make_response, url_for

import octoprint.gcodefiles as gcodefiles
import octoprint.util as util
from octoprint.filemanager.destinations import FileDestinations
from octoprint.settings import settings, valid_boolean_trues
from octoprint.server import printer, gcodeManager, eventManager, restricted_access, NO_CONTENT
from octoprint.server.api import api


#~~ GCODE file handling


@api.route("/files", methods=["GET"])
def readGcodeFiles():
	files = _getFileList(FileDestinations.LOCAL)
	files.extend(_getFileList(FileDestinations.SDCARD))
	#modify by kevin, for different path
	return jsonify(files=files, free=util.getFreeBytes(gcodeManager._uploadFolder))
	#modify end


@api.route("/files/<string:origin>", methods=["GET"])
def readGcodeFilesForOrigin(origin):
	if origin not in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		return make_response("Unknown origin: %s" % origin, 404)

	files = _getFileList(origin)

	if origin == FileDestinations.LOCAL:
		#modify by kevin, for different path
		return jsonify(files=files, free=util.getFreeBytes(gcodeManager._uploadFolder))
		#modify end
	else:
		return jsonify(files=files)


def _getFileDetails(origin, filename):
	files = _getFileList(origin)
	for file in files:
		if file["name"] == filename:
			return file
	return None


def _getFileList(origin):
	if origin == FileDestinations.SDCARD:
		sdFileList = printer.getSdFiles()

		files = []
		if sdFileList is not None:
			for sdFile in sdFileList:
				files.append({
					"name": sdFile,
					"origin": FileDestinations.SDCARD,
					"refs": {
						"resource": url_for(".readGcodeFile", target=FileDestinations.SDCARD, filename=sdFile, _external=True)
					}
				})
	else:
		#modify by kevin, for different path
		files = gcodeManager.getAllFileData(gcodeManager._uploadFolder)
		#modify end
		for file in files:
			file.update({
				"refs": {
					"resource": url_for(".readGcodeFile", target=FileDestinations.LOCAL, filename=file["name"], _external=True),
					"download": url_for("index", _external=True) + "downloads/files/" + FileDestinations.LOCAL + "/" + file["name"]
				}
			})
	return files


def _verifyFileExists(origin, filename):
	if origin == FileDestinations.SDCARD:
		availableFiles = printer.getSdFiles()
	else:
		#modify by kevin, for different path
		availableFiles = gcodeManager.getAllFilenames(gcodeManager._uploadFolder)
		#modify end
	return filename in availableFiles


@api.route("/files/<string:target>", methods=["POST"])
def uploadGcodeFile(target):
	if not target in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		return make_response("Unknown target: %s" % target, 404)

	if not "file" in request.files.keys():
		return make_response("No file included", 400)

	if target == FileDestinations.SDCARD and not settings().getBoolean(["feature", "sdSupport"]):
		return make_response("SD card support is disabled", 404)

	file = request.files["file"]
	sd = target == FileDestinations.SDCARD
	selectAfterUpload = "select" in request.values.keys() and request.values["select"] in valid_boolean_trues
	printAfterSelect = "print" in request.values.keys() and request.values["print"] in valid_boolean_trues

	if sd:
		# validate that all preconditions for SD upload are met before attempting it
		if not (printer.isOperational() and not (printer.isPrinting() or printer.isPaused())):
			return make_response("Can not upload to SD card, printer is either not operational or already busy", 409)
		if not printer.isSdReady():
			return make_response("Can not upload to SD card, not yet initialized", 409)

	# determine current job
	currentFilename = None
	currentSd = None
	currentJob = printer.getCurrentJob()
	if currentJob is not None and "filename" in currentJob.keys() and "sd" in currentJob.keys():
		currentFilename = currentJob["filename"]
		currentSd = currentJob["sd"]

	# determine future filename of file to be uploaded, abort if it can't be uploaded
	futureFilename = gcodeManager.getFutureFilename(file)
	if futureFilename is None or (not settings().getBoolean(["cura", "enabled"]) and not gcodefiles.isGcodeFileName(futureFilename)):
		return make_response("Can not upload file %s, wrong format?" % file.filename, 415)

	# prohibit overwriting currently selected file while it's being printed
	if futureFilename == currentFilename and sd == currentSd and (printer.isPrinting() or printer.isPaused()):
		return make_response("Trying to overwrite file that is currently being printed: %s" % currentFilename, 409)

	filename = None

	def fileProcessingFinished(filename, absFilename, destination):
		"""
		Callback for when the file processing (upload, optional slicing, addition to analysis queue) has
		finished.

		Depending on the file's destination triggers either streaming to SD card or directly calls selectAndOrPrint.
		"""
		if destination == FileDestinations.SDCARD:
			return filename, printer.addSdFile(filename, absFilename, selectAndOrPrint)
		else:
			selectAndOrPrint(absFilename, destination)
			return filename

	def selectAndOrPrint(nameToSelect, destination):
		"""
		Callback for when the file is ready to be selected and optionally printed. For SD file uploads this is only
		the case after they have finished streaming to the printer, which is why this callback is also used
		for the corresponding call to addSdFile.

		Selects the just uploaded file if either selectAfterUpload or printAfterSelect are True, or if the
		exact file is already selected, such reloading it.
		"""
		sd = destination == FileDestinations.SDCARD
		if selectAfterUpload or printAfterSelect or (currentFilename == filename and currentSd == sd):
			printer.selectFile(nameToSelect, sd, printAfterSelect)

	destination = FileDestinations.SDCARD if sd else FileDestinations.LOCAL
	filename, done = gcodeManager.addFile(file, destination, fileProcessingFinished)
	if filename is None:
		return make_response("Could not upload the file %s" % file.filename, 500)

	sdFilename = None
	if isinstance(filename, tuple):
		filename, sdFilename = filename

	eventManager.fire(Events.UPLOAD, {"file": filename, "target": target})

	files = {}
	if done:
		files.update({
			FileDestinations.LOCAL: {
				"name": filename,
				"origin": FileDestinations.LOCAL,
				"refs": {
					"resource": url_for(".readGcodeFile", target=FileDestinations.LOCAL, filename=filename, _external=True),
					"download": url_for("index", _external=True) + "downloads/files/" + FileDestinations.LOCAL + "/" + filename
				}
			}
		})

		if sd and sdFilename:
			files.update({
				FileDestinations.SDCARD: {
					"name": sdFilename,
					"origin": FileDestinations.SDCARD,
					"refs": {
						"resource": url_for(".readGcodeFile", target=FileDestinations.SDCARD, filename=sdFilename, _external=True)
					}
				}
			})

	return make_response(jsonify(files=files, done=done), 201)


@api.route("/files/<string:target>/<path:filename>", methods=["GET"])
def readGcodeFile(target, filename):
	if not target in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		return make_response("Unknown target: %s" % target, 404)

	file = _getFileDetails(target, filename)
	if not file:
		return make_response("File not found on '%s': %s" % (target, filename), 404)

	return jsonify(file)


@api.route("/files/<string:target>/<path:filename>", methods=["POST"])
def gcodeFileCommand(filename, target):
	if not target in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		return make_response("Unknown target: %s" % target, 404)

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


@api.route("/files/<string:target>/<path:filename>", methods=["DELETE"])
def deleteGcodeFile(filename, target):
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

	
#add by slc, for localfiles -> usbfiles or usbfiles -> localfiles

@api.route("/files/changeFilesPath", methods=["POST"])
def changeFilesPath():
	#modify by kevin, for use json format
	if not "application/json" in request.headers["Content-Type"]:
		return make_response("Expected content type JSON", 400)
	
	data = request.json

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
	
#add end, local->usb

#add by kevin, for copy file from usb to local

@api.route("/files/copyProgress", methods=["GET"])
def copyProgress():
	#print "has copyed:",gcodeManager._copyPercent
	return jsonify(copyPercent=gcodeManager._copyPercent)


@api.route("/files/copyFile", methods=["POST"])
def copyFile():
	#modify by kevin, for use json format
	if not "application/json" in request.headers["Content-Type"]:
		return make_response("Expected content type JSON", 400)
	
	data = request.json
	
	target = None
	filename = None
	
	if "target" in data.keys():
		target = data["target"]
	
	# if not target in [FileDestinations.LOCAL, FileDestinations.SDCARD]:
		# return make_response("Unknown target: %s" % target, 404)
		
	if "filename" in data.keys():
		filename = data["filename"]
	#modify end

	if not _verifyFileExists(target, filename):
		return make_response("File not found on '%s': %s" % (target, filename), 404)
	else:
		gcodeManager.startThreadToCopyFile(filename)
		
	return NO_CONTENT

#add end, copyFile
