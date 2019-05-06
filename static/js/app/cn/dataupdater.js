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
		"由于打印服务被断开，因而现不能从它获取任何响应。目前正在努力尝试自动" +
                "<strong>在接下来的几分钟重新连接它</strong>，当然您也可以通过点击下面的按钮，尝试手动重连。"
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
            "由于打印服务被断开，因而现不能从它获取任何响应。<strong>目前已不能自动再重新连接它，" +
                "但是您可以通过点击下面的按钮，尝试手动重连。"
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
                        $.pnotify({title: "呈现间隔拍摄", text: "正在为您呈现间隔拍摄 " + payload.movie_basename});
                    } else if (type == "MovieDone") {
                        $.pnotify({title: "拍摄准备", text: "新的拍摄 " + payload.movie_basename + " 已完成即将呈现"});
                        timelapseViewModel.requestData();
                    } else if (type == "MovieFailed") {
                        $.pnotify({title: "呈现失败", text: "呈现间隔拍摄 " + payload.movie_basename + " 失败，错误代码为 " + payload.returncode, type: "error"});
                    } else if (type == "SlicingStarted") {
                        gcodeUploadProgress.addClass("progress-striped").addClass("active");
                        gcodeUploadProgressBar.css("width", "100%");
                        gcodeUploadProgressBar.text("正在切片 ...");
                    } else if (type == "SlicingDone") {
                        gcodeUploadProgress.removeClass("progress-striped").removeClass("active");
                        gcodeUploadProgressBar.css("width", "0%");
                        gcodeUploadProgressBar.text("");
                        $.pnotify({title: "切片完成", text: "完成模型 " + payload.stl + " 切片，并保存到 " + payload.gcode + "文件， 总共花费了" + _.sprintf("%.2f", payload.time) + " 秒"});
                        gcodeFilesViewModel.requestData(payload.gcode);
                    } else if (type == "SlicingFailed") {
                        gcodeUploadProgress.removeClass("progress-striped").removeClass("active");
                        gcodeUploadProgressBar.css("width", "0%");
                        gcodeUploadProgressBar.text("");
                        $.pnotify({title: "切片失败", text: "不能进行模型 " + payload.stl + " 切片和保存 " + payload.gcode + ": " + payload.reason, type: "error"});
                    } else if (type == "TransferStarted") {
                        gcodeUploadProgress.addClass("progress-striped").addClass("active");
                        gcodeUploadProgressBar.css("width", "100%");
                        gcodeUploadProgressBar.text("正在传输 ...");
                    } else if (type == "TransferDone") {
                        gcodeUploadProgress.removeClass("progress-striped").removeClass("active");
                        gcodeUploadProgressBar.css("width", "0%");
                        gcodeUploadProgressBar.text("");
                        $.pnotify({title: "传输完成", text: "完成 " + payload.local + " 传输到位于SD上的 " + payload.remote + "总共花费了 " + _.sprintf("%.2f", payload.time) + " 秒"});
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
