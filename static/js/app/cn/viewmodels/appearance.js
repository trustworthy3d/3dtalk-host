function AppearanceViewModel(settingsViewModel) {
    var self = this;

    self.name = settingsViewModel.appearance_name;
    self.color = settingsViewModel.appearance_color;
    self.language = settingsViewModel.appearance_language; //add by kevin,for multiLanguage

    self.brand = ko.computed(function() {
        if (self.name())
            return "3DTALK: " + self.name();
        else
            return "3DTALK";
    })

    self.title = ko.computed(function() {
        if (self.name())
            return self.name() + " [3DTALK]";
        else
            return "3DTALK";
    })
}
