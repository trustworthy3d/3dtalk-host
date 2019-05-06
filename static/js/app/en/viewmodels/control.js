function ControlViewModel(loginStateViewModel, settingsViewModel) {
    var self = this;

    self.loginState = loginStateViewModel;
    self.settings = settingsViewModel;

    self._createToolEntry = function() {
        return {
            name: ko.observable(),
            key: ko.observable()
        }
    };

    self.isErrorOrClosed = ko.observable(undefined);
    self.isOperational = ko.observable(undefined);
    self.isPrinting = ko.observable(undefined);
    self.isPaused = ko.observable(undefined);
    self.isError = ko.observable(undefined);
    self.isReady = ko.observable(undefined);
    self.isLoading = ko.observable(undefined);

	self.toolNum = ko.observable("(E) Tool 0"); //add by kevin, for display toolNum
    self.extrusionAmount = ko.observable(undefined);
    self.controls = ko.observableArray([]);

    self.tools = ko.observableArray([]);

    self.feedbackControlLookup = {};

    self.settings.printer_numExtruders.subscribe(function(oldVal, newVal) {
        var tools = [];

        var numExtruders = self.settings.printer_numExtruders();
        if (numExtruders > 1) {
            // multiple extruders
			//modify by kevin, for use tool2 replace chamber
			numExtruders = CONFIG_HEATEDCHAMBER ? numExtruders-1 : numExtruders;
            for (var extruder = 0; extruder < numExtruders; extruder++) {
                tools[extruder] = self._createToolEntry();
                tools[extruder]["name"]("Tool " + extruder);
                tools[extruder]["key"]("tool" + extruder);
            }
        } else {
            // only one extruder, no need to add numbers
            tools[0] = self._createToolEntry();
            tools[0]["name"]("Hotend");
            tools[0]["key"]("tool0");
        }

        self.tools(tools);
    });

    self.fromCurrentData = function(data) {
        self._processStateData(data.state);
    }

    self.fromHistoryData = function(data) {
        self._processStateData(data.state);
    }

    self._processStateData = function(data) {
        self.isErrorOrClosed(data.flags.closedOrError);
        self.isOperational(data.flags.operational);
        self.isPaused(data.flags.paused);
        self.isPrinting(data.flags.printing);
        self.isError(data.flags.error);
        self.isReady(data.flags.ready);
        self.isLoading(data.flags.loading);
    }

	//add by kevin, for control webcamStream
	self.onOffStream = function(data) {
		var callback = function() {
			if(CONFIG_WEBCAM_STREAM == "http://your_printer_ip:8080/?action=stream"){
				data = true;
			}else{
				data = false;
			}
			$.ajax({
				url: API_BASEURL + "printer/system/onOffStream",
				method: "POST",
				dataType: "json",
				contentType: "application/json; charset=UTF-8",
				data: JSON.stringify({enabled: data})
			});
			timer = setTimeout(function reload() {
				window.location.reload();
			}, 500);
		}
		
		var showConfirmationDialog = function() {
			var confirmationDialog = $("#confirmation_dialog");
			var confirmationDialogAck = $(".confirmation_dialog_acknowledge", confirmationDialog);

			if(CONFIG_WEBCAM_STREAM == "http://your_printer_ip:8080/?action=stream"){
				$(".confirmation_dialog_message", confirmationDialog).text("If you really want to open real-time video? Might negatively impact performance, Not recommended always keep it's open. And if it has been opened, it will auto close after one hour.");
			}else{
				$(".confirmation_dialog_message", confirmationDialog).text("If you really want to close real-time video?");
			}
			confirmationDialogAck.unbind("click");
			confirmationDialogAck.bind("click", function(e) {
				e.preventDefault();
				$("#confirmation_dialog").modal("hide");
				callback();
			});
			confirmationDialog.modal("show");
		}
		
		if(data == "call"){
			callback();
		}else{
			showConfirmationDialog();
		}
	}
	//add end, for webcamStream

    self.fromFeedbackCommandData = function(data) {
        if (data.name in self.feedbackControlLookup) {
            self.feedbackControlLookup[data.name](data.output);
        }
    }

    self.requestData = function() {
        $.ajax({
            url: API_BASEURL + "printer/command/custom",
            method: "GET",
            dataType: "json",
            success: function(response) {
                self._fromResponse(response);
            }
        });
    }

    self._fromResponse = function(response) {
        self.controls(self._processControls(response.controls));
    }

    self._processControls = function(controls) {
        for (var i = 0; i < controls.length; i++) {
            controls[i] = self._processControl(controls[i]);
        }
        return controls;
    }

    self._processControl = function(control) {
        if (control.type == "parametric_command" || control.type == "parametric_commands") {
            for (var i = 0; i < control.input.length; i++) {
                control.input[i].value = control.input[i].default;
            }
        } else if (control.type == "feedback_command" || control.type == "feedback") {
            control.output = ko.observable("");
            self.feedbackControlLookup[control.name] = control.output;
        } else if (control.type == "section") {
            control.children = self._processControls(control.children);
        }
        return control;
    }

    self.sendJogCommand = function(axis, multiplier, distance) {
        if (typeof distance === "undefined")
            distance = $('#jog_distance button.active').data('distance');
        if (self.settings.getPrinterInvertAxis(axis)) {
            multiplier *= -1;
        }

        var data = {
            "command": "jog"
        }
        data[axis] = distance * multiplier;

        $.ajax({
            url: API_BASEURL + "printer/printhead",
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify(data)
        });
    }

    self.sendHomeCommand = function(axis) {
        var data = {
            "command": "home",
            "axes": axis
        }

        $.ajax({
            url: API_BASEURL + "printer/printhead",
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify(data)
        });
    }

    self.sendExtrudeCommand = function() {
        self._sendECommand(1);
    };

    self.sendRetractCommand = function() {
        self._sendECommand(-1);
    };

    self._sendECommand = function(dir) {
        var length = self.extrusionAmount();
        if (!length) length = 5;

        var data = {
            command: "extrude",
            amount: length * dir
        };

        $.ajax({
            url: API_BASEURL + "printer/tool",
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify(data)
        });
    };

    self.sendSelectToolCommand = function(data) {
        if (!data || !data.key()) return;
		//add by kevin, for display toolNum
		if(data.key() == "tool0"){
			self.toolNum("(E) Tool 0");
		}else if(data.key() == "tool1"){
			self.toolNum("(E) Tool 1");
		}
		//add end
        var data = {
            command: "select",
            tool: data.key()
        }

        $.ajax({
            url: API_BASEURL + "printer/tool",
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify(data)
        });
    };

    self.sendCustomCommand = function(command) {
        if (!command)
            return;

        var data = undefined;
        if (command.type == "command" || command.type == "parametric_command" || command.type == "feedback_command") {
            // single command
            data = {"command" : command.command};
        } else if (command.type == "commands" || command.type == "parametric_commands") {
            // multi command
            data = {"commands": command.commands};
        }

        if (command.type == "parametric_command" || command.type == "parametric_commands") {
            // parametric command(s)
            data["parameters"] = {};
            for (var i = 0; i < command.input.length; i++) {
                data["parameters"][command.input[i].parameter] = command.input[i].value;
            }
        }

        if (data === undefined)
            return;

        $.ajax({
            url: API_BASEURL + "printer/command",
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify(data)
        })
    }

    self.displayMode = function(customControl) {
        switch (customControl.type) {
            case "section":
                return "customControls_sectionTemplate";
            case "command":
            case "commands":
                return "customControls_commandTemplate";
            case "parametric_command":
            case "parametric_commands":
                return "customControls_parametricCommandTemplate";
            case "feedback_command":
                return "customControls_feedbackCommandTemplate";
            case "feedback":
                return "customControls_feedbackTemplate";
            default:
                return "customControls_emptyTemplate";
        }
    }

}
