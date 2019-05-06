function DataUpdater(loginStateViewModel, connectionViewModel, printerStateViewModel, temperatureViewModel, controlViewModel, terminalViewModel, gcodeFilesViewModel, timelapseViewModel, gcodeViewModel, logViewModel) {
    var self = this;

    self.loginStateViewModel = loginStateViewModel;
    self.connectionViewModel = connectionViewModel;
    self.printerStateViewModel = printerStateViewModel;
    self.temperatureViewModel = temperatureViewModel;
    self.controlViewModel = controlViewModel;
    self.terminalViewModel = terminalViewModel;
    self.gcodeFilesViewModel = gcodeFilesViewModel;
    self.timelapseViewModel = timelapseViewModel;
    self.gcodeViewModel = gcodeViewModel;
    self.logViewModel = logViewModel;

    self._socket = undefined;
    self._autoReconnecting = false;
    self._autoReconnectTrial = 0;
    self._autoReconnectTimeouts = [1, 1, 2, 3, 5, 8, 13, 20, 40, 100];

    self.connect = function() {
        var options = {};
        if (SOCKJS_DEBUG) {
            options["debug"] = true;
        }

        self._socket = new SockJS(SOCKJS_URI, undefined, options);
        self._socket.onopen = self._onconnect;
        self._socket.onclose = self._onclose;
        self._socket.onmessage = self._onmessage;
    }

    self.reconnect = function() {
        delete self._socket;
        self.connect();
    }

    self._onconnect = function() {
        self._autoReconnecting = false;
        self._autoReconnectTrial = 0;

        if ($("#offline_overlay").is(":visible")) {
        	$("#offline_overlay").hide();
        	self.logViewModel.requestData();
            self.timelapseViewModel.requestData();
            $("#webcam_image").attr("src", CONFIG_WEBCAM_STREAM + "?" + new Date().getTime());
            self.loginStateViewModel.requestData();
            self.gcodeFilesViewModel.requestData();
            self.gcodeViewModel.reset();

            if ($('#tabs li[class="active"] a').attr("href") == "#control") {
                $("#webcam_image").attr("src", CONFIG_WEBCAM_STREAM + "?" + new Date().getTime());
            }
        }
    }

    self._onclose = function() {
        $("#offline_overlay_message").html(
		"由於列印服務被斷開，因而現不能從它獲取任何回應。目前正在努力嘗試自動" +
                "<strong>在接下來的幾分鐘重新連接它</strong>，當然您也可以通過點擊下麵的按鈕，嘗試手動重連。"
        );
        if (!$("#offline_overlay").is(":visible"))
            $("#offline_overlay").show();

        if (self._autoReconnectTrial < self._autoReconnectTimeouts.length) {
            var timeout = self._autoReconnectTimeouts[self._autoReconnectTrial];
            console.log("Reconnect trial #" + self._autoReconnectTrial + ", waiting " + timeout + "s");
            setTimeout(self.reconnect, timeout * 1000);
            self._autoReconnectTrial++;
        } else {
            self._onreconnectfailed();
        }
    }

    self._onreconnectfailed = function() {
        $("#offline_overlay_message").html(
            "由於列印服務被斷開，因而現不能從它獲取任何回應。<strong>目前已不能自動再重新連接它，" +
                "但是您可以通過點擊下麵的按鈕，嘗試手動重連。"
        );
    }

    self._onmessage = function(e) {
        for (var prop in e.data) {
            var data = e.data[prop];

            switch (prop) {
                case "history": {
                    self.connectionViewModel.fromHistoryData(data);
                    self.printerStateViewModel.fromHistoryData(data);
                    self.temperatureViewModel.fromHistoryData(data);
                    self.controlViewModel.fromHistoryData(data);
                    self.terminalViewModel.fromHistoryData(data);
                    self.timelapseViewModel.fromHistoryData(data);
                    self.gcodeViewModel.fromHistoryData(data);
                    self.gcodeFilesViewModel.fromCurrentData(data);
                    break;
                }
                case "current": {
                    self.connectionViewModel.fromCurrentData(data);
                    self.printerStateViewModel.fromCurrentData(data);
                    self.temperatureViewModel.fromCurrentData(data);
                    self.controlViewModel.fromCurrentData(data);
                    self.terminalViewModel.fromCurrentData(data);
                    self.timelapseViewModel.fromCurrentData(data);
                    self.gcodeViewModel.fromCurrentData(data);
                    self.gcodeFilesViewModel.fromCurrentData(data);
                    break;
                }
                case "event": {
                    var type = data["type"];
                    var payload = data["payload"];

                    var gcodeUploadProgress = $("#gcode_upload_progress");
                    var gcodeUploadProgressBar = $(".bar", gcodeUploadProgress);

                    if ((type == "UpdatedFiles" && payload.type == "gcode") || type == "MetadataAnalysisFinished") {
                        gcodeFilesViewModel.requestData();
                    } else if (type == "MovieRendering") {
                        $.pnotify({title: "呈現間隔拍攝", text: "正在為您呈現間隔拍攝 " + payload.movie_basename});
                    } else if (type == "MovieDone") {
                        $.pnotify({title: "拍攝準備", text: "新的拍攝 " + payload.movie_basename + " 已完成即將呈現"});
                        timelapseViewModel.requestData();
                    } else if (type == "MovieFailed") {
                        $.pnotify({title: "呈現失敗", text: "呈現間隔拍攝 " + payload.movie_basename + " 失敗，錯誤代碼為 " + payload.returncode, type: "error"});
                    } else if (type == "SlicingStarted") {
                        gcodeUploadProgress.addClass("progress-striped").addClass("active");
                        gcodeUploadProgressBar.css("width", "100%");
                        gcodeUploadProgressBar.text("正在切片 ...");
                    } else if (type == "SlicingDone") {
                        gcodeUploadProgress.removeClass("progress-striped").removeClass("active");
                        gcodeUploadProgressBar.css("width", "0%");
                        gcodeUploadProgressBar.text("");
                        $.pnotify({title: "切片完成", text: "完成模型 " + payload.stl + " 切片，並保存到 " + payload.gcode + "檔， 總共花費了" + _.sprintf("%.2f", payload.time) + " 秒"});
                        gcodeFilesViewModel.requestData(payload.gcode);
                    } else if (type == "SlicingFailed") {
                        gcodeUploadProgress.removeClass("progress-striped").removeClass("active");
                        gcodeUploadProgressBar.css("width", "0%");
                        gcodeUploadProgressBar.text("");
                        $.pnotify({title: "切片失敗", text: "不能進行模型 " + payload.stl + " 切片和保存 " + payload.gcode + ": " + payload.reason, type: "error"});
                    } else if (type == "TransferStarted") {
                        gcodeUploadProgress.addClass("progress-striped").addClass("active");
                        gcodeUploadProgressBar.css("width", "100%");
                        gcodeUploadProgressBar.text("正在傳輸 ...");
                    } else if (type == "TransferDone") {
                        gcodeUploadProgress.removeClass("progress-striped").removeClass("active");
                        gcodeUploadProgressBar.css("width", "0%");
                        gcodeUploadProgressBar.text("");
                        $.pnotify({title: "傳輸完成", text: "完成 " + payload.local + " 傳輸到位於SD上的 " + payload.remote + "總共花費了 " + _.sprintf("%.2f", payload.time) + " 秒"});
                        gcodeFilesViewModel.requestData(payload.remote, "sdcard");
                    }
                    break;
                }
                case "feedbackCommandOutput": {
                    self.controlViewModel.fromFeedbackCommandData(data);
                    break;
                }
                case "timelapse": {
                    self.printerStateViewModel.fromTimelapseData(data);
                    break;
                }
            }
        }
    }

    self.connect();
}
