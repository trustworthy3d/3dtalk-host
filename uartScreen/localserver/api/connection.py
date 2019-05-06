# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

from octoprint.settings import settings
from octoprint.printer import getConnectionOptions
from octoprint.server import printer, NO_CONTENT

import api_util as util
from api_util import make_response,NO_CONTENT



def connectionState():
	state, port, baudrate = printer.getCurrentConnection()
	current = {
		"state": state,
		"port": port,
		"baudrate": baudrate
	}
	return jsonify({"current": current, "options": getConnectionOptions()})

def connectionCommand(request=None):
	valid_commands = {
		"connect": ["autoconnect"],
		"disconnect": []
	}

	command, data, response = util.getJsonCommandFromRequest(request, valid_commands)
	print "connectionCommand",command, data, response,"connectionCommand"
	if response is not None:
		return response

	if command == "connect":
		options = getConnectionOptions()

		port = None
		baudrate = None
		if "port" in data.keys():
			port = data["port"]
			if port not in options["ports"]:
				return make_response("Invalid port: %s" % port, 400)
		if "baudrate" in data.keys():
			baudrate = data["baudrate"]
			if baudrate not in options["baudrates"]:
				return make_response("Invalid baudrate: %d" % baudrate, 400)
		if "save" in data.keys() and data["save"]:
			settings().set(["serial", "port"], port)
			settings().setInt(["serial", "baudrate"], baudrate)
		if "autoconnect" in data.keys():
			settings().setBoolean(["serial", "autoconnect"], data["autoconnect"])
		settings().save()
		printer.connect(port=port, baudrate=baudrate)
	elif command == "disconnect":
		printer.disconnect()

	return NO_CONTENT


