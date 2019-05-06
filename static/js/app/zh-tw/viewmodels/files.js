function GcodeFilesViewModel(printerStateViewModel, loginStateViewModel) {
    var self = this;

    self.printerState = printerStateViewModel;
    self.loginState = loginStateViewModel;
	self.filePath = ko.observable("local"); //add by kevin, for highlightFilePath
	self.isEnUpload = ko.observable(true); //add by kevin, for prevent some upload

    self.isErrorOrClosed = ko.observable(undefined);
    self.isOperational = ko.observable(undefined);
    self.isPrinting = ko.observable(undefined);
    self.isPaused = ko.observable(undefined);
    self.isError = ko.observable(undefined);
    self.isReady = ko.observable(undefined);
    self.isLoading = ko.observable(undefined);
    self.isSdReady = ko.observable(undefined);
	
	self.isCopying = ko.observable(false);
	self.copyPercent = 0; //add by kevin, for copyFile
	self.timer = null;

    self.freeSpace = ko.observable(undefined);
    self.freeSpaceString = ko.computed(function() {
        if (!self.freeSpace())
            return "-";
        return formatSize(self.freeSpace());
    });

    // initialize list helper
    self.listHelper = new ItemListHelper(
        "gcodeFiles",
        {
            "name": function(a, b) {
                // sorts ascending
                if (a["name"].toLocaleLowerCase() < b["name"].toLocaleLowerCase()) return -1;
                if (a["name"].toLocaleLowerCase() > b["name"].toLocaleLowerCase()) return 1;
                return 0;
            },
            "upload": function(a, b) {
                // sorts descending
                if (b["date"] === undefined || a["date"] > b["date"]) return -1;
                if (a["date"] < b["date"]) return 1;
                return 0;
            },
            "size": function(a, b) {
                // sorts descending
                if (b["bytes"] === undefined || a["bytes"] > b["bytes"]) return -1;
                if (a["bytes"] < b["bytes"]) return 1;
                return 0;
            }
        },
        {
            "printed": function(file) {
                return !(file["prints"] && file["prints"]["success"] && file["prints"]["success"] > 0);
            },
            "sd": function(file) {
                return file["origin"] && file["origin"] == "sdcard";
            },
            "local": function(file) {
                return !(file["origin"] && file["origin"] == "sdcard");
            }
        },
        "name",
        [],
        [["sd", "local"]],
        CONFIG_GCODEFILESPERPAGE
    );

    self.isLoadActionPossible = ko.computed(function() {
        return self.loginState.isUser() && !self.isPrinting() && !self.isPaused() && !self.isLoading();
    });

    self.isLoadAndPrintActionPossible = ko.computed(function() {
        return self.loginState.isUser() && self.isOperational() && self.isLoadActionPossible();
    });

    self.printerState.filename.subscribe(function(newValue) {
        self.highlightFilename(newValue);
    });

    self.highlightFilename = function(filename) {
        if (filename == undefined) {
            self.listHelper.selectNone();
        } else {
            self.listHelper.selectItem(function(item) {
                return item.name == filename;
            });
        }
    };

    self.fromCurrentData = function(data) {
        self._processStateData(data.state);
    };

    self.fromHistoryData = function(data) {
        self._processStateData(data.state);
    };

    self._processStateData = function(data) {
        self.isErrorOrClosed(data.flags.closedOrError);
        self.isOperational(data.flags.operational);
        self.isPaused(data.flags.paused);
        self.isPrinting(data.flags.printing);
        self.isError(data.flags.error);
        self.isReady(data.flags.ready);
        self.isLoading(data.flags.loading);
        self.isSdReady(data.flags.sdReady);
    };

    self.requestData = function(filenameToFocus, locationToFocus) {
        $.ajax({
            url: API_BASEURL + "files",
            method: "GET",
            dataType: "json",
            success: function(response) {
                self.fromResponse(response, filenameToFocus, locationToFocus);
            }
        });
    };

    self.fromResponse = function(response, filenameToFocus, locationToFocus) {
        var files = response.files;
        _.each(files, function(element, index, list) {
            if (!element.hasOwnProperty("size")) element.size = undefined;
            if (!element.hasOwnProperty("date")) element.date = undefined;
        });
        self.listHelper.updateItems(files);

        if (filenameToFocus) {
            // got a file to scroll to
            if (locationToFocus === undefined) {
                locationToFocus = "local";
            }
            self.listHelper.switchToItem(function(item) {return item.name == filenameToFocus && item.origin == locationToFocus});
        }

        if (response.free) {
            self.freeSpace(response.free);
        }

        self.highlightFilename(self.printerState.filename());
    };

	//add by kevin, for highlightFilePath
	self.isLocalFile = function() {
		return self.filePath() == "local";
	}
	
	self.isUsbFile = function() {
		return self.filePath() == "usb";
	}
	//add end

	//add by slc, for localfiles -> usbfiles or usbfiles -> localfiles
	self.changeFilesPath = function(command) {
		self.filePath(command); //add by kevin, for highlightFilePath
		//add by kevin, for prevent some upload
		if (command == "local") {
			self.isEnUpload(true);
		} else {
			self.isEnUpload(false);
		}
		//add end
		self.listHelper.clearItems();
		$.ajax({
			url: API_BASEURL + "files/changeFilesPath",
			type: "POST",
			dataType: "json",
			//modify by kevin, for use json format
			contentType: "application/json; charset=UTF-8",
			data: JSON.stringify({filespath: command}),
			//modify end
			success: function() {
				self.requestData();
			}
		});
	}
	//add end, local->usb

    self.loadFile = function(filename, printAfterLoad) {
        var file = self.listHelper.getItem(function(item) {return item.name == filename});
        if (!file || !file.refs || !file.refs.hasOwnProperty("resource")) return;

        $.ajax({
            url: file.refs.resource,
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify({command: "select", print: printAfterLoad})
        });
    };
	
	//add by slc, for copy file from usb to local
	self.getProgress = function() {
		$.ajax({
			url: API_BASEURL + "files/copyProgress",
			method: "GET",
			dataType: "json",
			success: function(response) {
				self.copyPercent = response.copyPercent;
			}
		});

		$("#gcode_upload_progress .bar").css("width", self.copyPercent + "%");
        $("#gcode_upload_progress .bar").text("正在拷貝 ...");

        if(100 <= self.copyPercent) {
			self.timer = setTimeout(function isFinishCopy(){
				// if(100 <= self.copyPercent){
					self.copyPercent = 0;
					$("#gcode_upload_progress .bar").css("width", self.copyPercent + "%");
					$("#gcode_upload_progress").removeClass("progress-striped").removeClass("active");
					$("#gcode_upload_progress .bar").text("");
					clearTimeout(self.timer);
					self.isCopying(false);
				// }
			}, 1000);
		} else {
			self.timer = setTimeout(self.getProgress, 100);
		}
	}

	self.copyFile = function(filename) {
		var file = self.listHelper.getItem(function(item) {return item.name == filename});
		if (!file) return;

		$.ajax({
			url: API_BASEURL + "files/copyFile",
			type: "POST",
			dataType: "json",
			//modify by kevin, for use json format
			contentType: "application/json; charset=UTF-8",
			data: JSON.stringify({filename: filename, target: file.origin}),
			//modify end
			success: function() {
				self.fromResponse
			}
		});
		self.isCopying(true);
		self.getProgress();
	};
	//add end, copyFile

    self.removeFile = function(filename) {
        var file = self.listHelper.getItem(function(item) {return item.name == filename});
        if (!file || !file.refs || !file.refs.hasOwnProperty("resource")) return;

        var origin;
        if (file.origin === undefined) {
            origin = "local";
        } else {
            origin = file.origin;
        }

        $.ajax({
            url: file.refs.resource,
            type: "DELETE",
            success: function() {
                self.requestData();
            }
        });
    };

    self.initSdCard = function() {
        self._sendSdCommand("init");
    };

    self.releaseSdCard = function() {
        self._sendSdCommand("release");
    };

    self.refreshSdFiles = function() {
        self._sendSdCommand("refresh");
    };

    self._sendSdCommand = function(command) {
        $.ajax({
            url: API_BASEURL + "printer/sd",
            type: "POST",
            dataType: "json",
            contentType: "application/json; charset=UTF-8",
            data: JSON.stringify({command: command})
        });
    };

    self.getPopoverContent = function(data) {
        var output = "<p><strong>上傳時間：</strong> " + formatDate(data["date"]) + "</p>";
        if (data["gcodeAnalysis"]) {
            output += "<p>";
            if (data["gcodeAnalysis"]["filament"] && typeof(data["gcodeAnalysis"]["filament"]) == "object") {
                var filament = data["gcodeAnalysis"]["filament"];
                if (_.keys(filament).length == 1) {
                    output += "<strong>耗材用量：</strong> " + formatFilament(data["gcodeAnalysis"]["filament"]["tool" + 0]) + "<br>";
                } else {
                    var i = 0;
                    do {
                        if (filament["tool" + i].hasOwnProperty("length") && filament["tool" + i]["length"] > 0) {
                            output += "<strong>Filament (Tool " + i + "):</strong> " + formatFilament(filament["tool" + i]) + "<br>";
                        }
                        i++;
                    } while (filament.hasOwnProperty("tool" + i));
                }
            }
            output += "<strong>預估列印時間：</strong> " + formatDuration(data["gcodeAnalysis"]["estimatedPrintTime"]);
            output += "</p>";
        }
        if (data["prints"] && data["prints"]["last"]) {
            output += "<p>";
            output += "<strong>上次列印時間：</strong> <span class=\"" + (data["prints"]["last"]["success"] ? "text-success" : "text-error") + "\">" + formatDate(data["prints"]["last"]["date"]) + "</span>";
            output += "</p>";
        }
        return output;
    };

    self.getSuccessClass = function(data) {
        if (!data["prints"] || !data["prints"]["last"]) {
            return "";
        }
        return data["prints"]["last"]["success"] ? "text-success" : "text-error";
    };
	
	//add by slc, for copy file from usb to local
	self.enableCopy = function(data) {
		return self.loginState.isUser() && !(self.listHelper.isSelected(data) && (self.isPrinting() || self.isPaused())) && !self.isCopying() && self.isUsbFile();
	};
	//add end, copyFile

	//modify by kevin, for prevent remove usb files
    self.enableRemove = function(data) {
        return self.loginState.isUser() && !(self.listHelper.isSelected(data) && (self.isPrinting() || self.isPaused())) && self.isLocalFile();
    };
	//modify end

    self.enableSelect = function(data, printAfterSelect) {
        var isLoadActionPossible = self.loginState.isUser() && self.isOperational() && !(self.isPrinting() || self.isPaused() || self.isLoading());
        return isLoadActionPossible && !self.listHelper.isSelected(data);
    };

}

