function NavigationViewModel(loginStateViewModel, appearanceViewModel, settingsViewModel, usersViewModel) {
    var self = this;

    self.loginState = loginStateViewModel;
    self.appearance = appearanceViewModel;
    self.systemActions = settingsViewModel.system_actions;
    self.availableLanguages = settingsViewModel.availableLanguages;
    self.recordlast_language = settingsViewModel.recordlast_language;
    self.users = usersViewModel;

    self.triggerLanguage = function(language) {
        if(self.recordlast_language() != language.language){
            var data = {"appearance" : {"language": language.language} };
            $.ajax({
                url: API_BASEURL + "settings/language",
                type: "POST",
                dataType: "json",
                contentType: "application/json; charset=UTF-8",
                data: JSON.stringify(data)
            });
            timer = setTimeout(function reload() {
                window.location.reload();
            }, 500);
        }
    }

    self.triggerAction = function(action) {
        var callback = function() {
            $.ajax({
                url: API_BASEURL + "system",
                type: "POST",
                dataType: "json",
                data: "action=" + action.action,
                success: function() {
                    $.pnotify({title: "成功", text: "命令 \""+ action.name +"\" 執行成功", type: "success"});
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    $.pnotify({title: "錯誤", text: "<p>命令 \"" + action.name + "\" 不能被執行。</p><p>原因是：<pre>" + jqXHR.responseText + "</pre></p>", type: "error"});
                }
            })
        }
        if (action.confirm) {
            var confirmationDialog = $("#confirmation_dialog");
            var confirmationDialogAck = $(".confirmation_dialog_acknowledge", confirmationDialog);

            $(".confirmation_dialog_message", confirmationDialog).text(action.confirm);
            confirmationDialogAck.unbind("click");
            confirmationDialogAck.bind("click", function(e) {
                e.preventDefault();
                $("#confirmation_dialog").modal("hide");
                callback();
            });
            confirmationDialog.modal("show");
        } else {
            callback();
        }
    }

	//add by kevin, for change network
	self.networkActions = [
		{"action": "connect", "name": "連接WiFi"},
		{"action": "create", "name": "創建WiFi"}
	];
	self.triggerNetwork = function(network) {
		if("connect" == network.action){
			self.showConnectWifiDialog();
		}else if("create" == network.action){
			self.showCreateWifiDialog();
		}
	}
	//add by kevin, for some other settings
	self.editorWifiName = ko.observable(undefined);
	self.editorWifiPassword = ko.observable(undefined);
	
	self.currentWifiName = ko.observable(undefined);
	self.availableWifiNames = ko.observableArray(undefined);

	self.getAvailableWifiNames = function() {
		$.ajax({
			url: API_BASEURL + "settings/getAvailableWifiNames",
			type: "GET",
			dataType: "json",
			success: function(response) {
				if(response.wifiNames.length){
					self.availableWifiNames(response.wifiNames);
				}else{
					self.availableWifiNames([gettext("Searching...")]);
				}
			}
		});
	}

	self.showConnectWifiDialog = function() {
		$("#network-otherDialogConnectWifi").modal("show");
	}

	self.confirmConnectWifi = function() {
		if(self.currentWifiName() && self.editorWifiPassword().length >= 8){
			var wifi = {ssid: self.currentWifiName(), password: self.editorWifiPassword(), flag: "connect"};
			self.systemCommand(wifi);
		}
		$("#network-otherDialogConnectWifi").modal("hide");
	}

	self.showCreateWifiDialog = function() {
		$("#network-otherDialogCreateWifi").modal("show");
	}

	self.confirmCreateWifi = function() {
		if(self.editorWifiName() && (self.editorWifiPassword().length >= 8 || self.editorWifiPassword().length == 0)){
			var wifi = {ssid: self.editorWifiName(), password: self.editorWifiPassword(), flag: "create"};
			self.systemCommand(wifi);
		}
		$("#network-otherDialogCreateWifi").modal("hide");
	}

	self.systemCommand = function(data) {
		if (data === undefined) {
			$.ajax({
				url: API_BASEURL + "settings/system/factoryReset",
				type: "POST"
			});
		} else {
			$.ajax({
				url: API_BASEURL + "settings/system/setWifi",
				type: "POST",
				contentType: "application/json; charset=UTF-8",
				data: JSON.stringify(data)
			});
		}
	}
	
	self.clearWifiInfo = function() {
		self.editorWifiName(undefined);
		self.editorWifiPassword(undefined);
	}
	//add end, for some other settings
}

