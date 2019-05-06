# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

NO_CONTENT = ("", 204)

def make_response(err_str="default_err_str",err_code=0):
	return err_str,err_code

def getJsonCommandFromRequest(data, valid_commands):
	
	if data is None:
		return None, None,"data is None"
	
	if not "command" in data.keys() or not data["command"] in valid_commands.keys():
		return None, None, "Expected valid command"

	command = data["command"]
	for parameter in valid_commands[command]:
		if not parameter in data:
			return None, None, "Mandatory parameter %s missing for command %s" % (parameter, command)

	return command, data, None
