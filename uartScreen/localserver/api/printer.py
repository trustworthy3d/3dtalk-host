# coding=utf-8

import subprocess
import re
from octoprint.settings import settings, valid_boolean_trues
from octoprint.server import printer

import api_util as util
from api_util import make_response,NO_CONTENT

#~~ Tool

def printerToolCommand(request=None):
	if not printer.isOperational():
		return make_response("Printer is not operational", 409)

	valid_commands = {
		"select": ["tool"],
		"target": ["targets"],
		"offset": ["offsets"],
		"extrude": ["amount"]
	}
	command, data, response = util.getJsonCommandFromRequest(request, valid_commands)
	print "printerToolCommand",command, data, response,"printerToolCommand"
	if response is not None:
		return response

	validation_regex = re.compile("tool\d+")

	##~~ tool selection
	if command == "select":
		tool = data["tool"]
		if re.match(validation_regex, tool) is None:
			return make_response("Invalid tool: %s" % tool, 400)
		if not tool.startswith("tool"):
			return make_response("Invalid tool for selection: %s" % tool, 400)

		printer.changeTool(tool)

	##~~ temperature
	elif command == "target":
		targets = data["targets"]

		# make sure the targets are valid and the values are numbers
		validated_values = {}
		for tool, value in targets.iteritems():
			if re.match(validation_regex, tool) is None:
				return make_response("Invalid target for setting temperature: %s" % tool, 400)
			if not isinstance(value, (int, long, float)):
				return make_response("Not a number for %s: %r" % (tool, value), 400)
			validated_values[tool] = value

		# perform the actual temperature commands
		for tool in validated_values.keys():
			printer.setTemperature(tool, validated_values[tool])

	##~~ temperature offset
	elif command == "offset":
		offsets = data["offsets"]

		# make sure the targets are valid, the values are numbers and in the range [-50, 50]
		validated_values = {}
		for tool, value in offsets.iteritems():
			if re.match(validation_regex, tool) is None:
				return make_response("Invalid target for setting temperature: %s" % tool, 400)
			if not isinstance(value, (int, long, float)):
				return make_response("Not a number for %s: %r" % (tool, value), 400)
			if not -50 <= value <= 50:
				return make_response("Offset %s not in range [-50, 50]: %f" % (tool, value), 400)
			validated_values[tool] = value

		# set the offsets
		printer.setTemperatureOffset(validated_values)

	##~~ extrusion
	elif command == "extrude":
		if printer.isPrinting():
			# do not extrude when a print job is running
			return make_response("Printer is currently printing", 409)

		amount = data["amount"]
		if not isinstance(amount, (int, long, float)):
			return make_response("Not a number for extrusion amount: %r" % amount, 400)
		printer.extrude(amount)

	return NO_CONTENT

def printerToolState():
	def deleteBed(x):
		data = dict(x)

		if "bed" in data.keys():
			del data["bed"]
		return data

	return jsonify(_getTemperatureData(deleteBed))


##~~ Heated bed

def printerBedCommand(request=None):
	if not printer.isOperational():
		return make_response("Printer is not operational", 409)

	valid_commands = {
		"target": ["target"],
		"offset": ["offset"]
	}
	command, data, response = util.getJsonCommandFromRequest(request, valid_commands)
	if response is not None:
		return response

	##~~ temperature
	if command == "target":
		target = data["target"]

		# make sure the target is a number
		if not isinstance(target, (int, long, float)):
			return make_response("Not a number: %r" % target, 400)

		# perform the actual temperature command
		printer.setTemperature("bed", target)

	##~~ temperature offset
	elif command == "offset":
		offset = data["offset"]

		# make sure the offset is valid
		if not isinstance(offset, (int, long, float)):
			return make_response("Not a number: %r" % offset, 400)
		if not -50 <= offset <= 50:
			return make_response("Offset not in range [-50, 50]: %f" % offset, 400)

		# set the offsets
		printer.setTemperatureOffset({"bed": offset})

	return NO_CONTENT

def printerBedState():
	def deleteTools(x):
		data = dict(x)

		for k in data.keys():
			if k.startswith("tool"):
				del data[k]
		return data

	return jsonify(_getTemperatureData(deleteTools))



##~~ Print head
	
def printerPrintheadCommand(request=None):
	if not printer.isOperational() or printer.isPrinting():
		# do not jog when a print job is running or we don't have a connection
		return make_response("Printer is not operational or currently printing", 409)

	valid_commands = {
                "jog": [],
                "home": ["axes"]
        }
	command, data, response = util.getJsonCommandFromRequest(request, valid_commands)
	print "command:",command,"data:", data,"response:", response
	if response is not None:
		return response

	valid_axes = ["x", "y", "z"]
	##~~ jog command
	if command == "jog":
		# validate all jog instructions, make sure that the values are numbers
		validated_values = {}
		for axis in valid_axes:
			if axis in data:
				value = data[axis]
				if not isinstance(value, (int, long, float)):
					return make_response("Not a number for axis %s: %r" % (axis, value), 400)
				validated_values[axis] = value

		# execute the jog commands
		for axis, value in validated_values.iteritems():
			printer.jog(axis, value)

	##~~ home command
	elif command == "home":
		validated_values = []
		axes = data["axes"]
		for axis in axes:
			if not axis in valid_axes:
				return make_response("Invalid axis: %s" % axis, 400)
			validated_values.append(axis)

		# execute the home command
		printer.home(validated_values)

	return NO_CONTENT


##~~ Commands

def printerCommand(data=None):
	# TODO: document me
	if not printer.isOperational():
		return make_response("Printer is not operational", 409)
	if data is None:
		return make_response("Expected content type JSON", 400)
	parameters = {}
	if "parameters" in data.keys(): parameters = data["parameters"]

	commands = []
	if "command" in data.keys(): commands = [data["command"]]
	elif "commands" in data.keys(): commands = data["commands"]

	commandsToSend = []
	for command in commands:
		commandToSend = command
		if len(parameters) > 0:
			commandToSend = command % parameters
		commandsToSend.append(commandToSend)

	printer.commands(commandsToSend)

	return NO_CONTENT
def getSerialNumber():
	if printer.isClosedOrError() or printer.isError():
		return "C000000000"
	else:
		return settings().get(["printerParameters", "serialNumber"])
	
def _getTemperatureData(filter):
	if not printer.isOperational():
		return make_response("Printer is not operational", 409)

	tempData = printer.getCurrentTemperatures()
	result = {
		"temps": filter(tempData)
	}

	if "history" in request.values.keys() and request.values["history"] in valid_boolean_trues:
		tempHistory = printer.getTemperatureHistory()

		limit = 300
		if "limit" in request.values.keys() and unicode(request.values["limit"]).isnumeric():
			limit = int(request.values["limit"])

		history = list(tempHistory)
		limit = min(limit, len(history))

		result.update({
			"history": map(lambda x: filter(x), history[-limit:])
		})

	return result