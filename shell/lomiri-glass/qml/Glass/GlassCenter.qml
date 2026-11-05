// SPDX-License-Identifier: GPL-3.0-only
// Native QtQuick surface. All system state comes from the injected backend;
// persistent notifications and detailed pages remain Lomiri's own MenuContent.
import QtQuick 2.15
import "GlassStrings.js" as Strings

FocusScope {
    id: root
    Accessible.name: Strings.tr(root.mode === "notifications" ? "Notifications" : "Control Center", root.language)
    property var backend: null
    property string language: "en"
    property real gu: 8
    property string mode: "controls"
    property bool detailActive: false
    property string detailTitle: ""
    property bool nativePageAvailable: true
    property bool reducedMotion: false
    property bool highContrast: false
    property bool lightSurface: false
    // uOS27: retain the real Home wallpaper and running application beneath
    // the panel. A darker tint improves contrast in both views without
    // replacing the scene with an image, wallpaper or opaque overlay.
    property bool appBehind: false
    property alias nativeContentHost: nativeHost
    readonly property bool nativeVisible: mode === "notifications" || detailActive
    readonly property bool actionsAllowed: backend !== null && backend.actionsAllowed
    property string errorMessage: ""
    property bool _pendingWifi: false
    property bool _pendingBluetooth: false
    property bool _pendingMobile: false
    property bool _pendingAirplane: false
    property bool _pendingSilent: false
    property bool _pendingRotation: false
    property bool _pendingBrightness: false
    property bool _pendingVolume: false
    property real _requestedBrightness: 0
    property real _requestedVolume: 0
    property string _feedbackIcon: ""
    property string _feedbackLabel: ""
    property bool _feedbackVisible: false
    signal closeRequested()
    signal nativePageRequested(string identifier)
    signal viewSelected(string view)
    clip: true

    function selectView(view) {
        root.mode = view;
        root.detailActive = false;
        root.errorMessage = "";
        root._feedbackVisible = false;
        root.clearPending();
        root.viewSelected(view);
    }
    function clearPending() {
        root._pendingWifi = false;
        root._pendingBluetooth = false;
        root._pendingMobile = false;
        root._pendingAirplane = false;
        root._pendingSilent = false;
        root._pendingRotation = false;
        root._pendingBrightness = false;
        root._pendingVolume = false;
        pendingTimeout.stop();
    }
    function requestToggle(key) {
        if (!root.actionsAllowed)
            return;
        if (key === "wifi") { root._pendingWifi = true; root.backend.toggleWifi(); }
        else if (key === "bluetooth") { root._pendingBluetooth = true; root.backend.toggleBluetooth(); }
        else if (key === "mobile") { root._pendingMobile = true; root.backend.toggleMobileData(); }
        else if (key === "airplane") { root._pendingAirplane = true; root.backend.toggleAirplane(); }
        else if (key === "silent") { root._pendingSilent = true; root.backend.toggleSilent(); }
        else if (key === "rotation") { root._pendingRotation = true; root.backend.toggleRotation(); }
        pendingTimeout.restart();
    }
    function showFeedback(icon, title) {
        root._feedbackVisible = false;
        root._feedbackIcon = icon;
        root._feedbackLabel = title;
        root._feedbackVisible = true;
        feedbackTimeout.restart();
    }
    function confirmed(key, enabled) {
        var label = "";
        if (key === "wifi" && root._pendingWifi) { root._pendingWifi = false; label = Strings.tr("Wi-Fi", language); }
        else if (key === "bluetooth" && root._pendingBluetooth) { root._pendingBluetooth = false; label = Strings.tr("Bluetooth", language); }
        else if (key === "mobile" && root._pendingMobile) { root._pendingMobile = false; label = Strings.tr("Mobile data", language); }
        else if (key === "airplane" && root._pendingAirplane) { root._pendingAirplane = false; label = Strings.tr("Airplane mode", language); }
        else if (key === "silent" && root._pendingSilent) { root._pendingSilent = false; label = Strings.tr("Silent", language); }
        else if (key === "rotation" && root._pendingRotation) { root._pendingRotation = false; label = Strings.tr("Rotation lock", language); }
        if (label.length > 0 && root.actionsAllowed)
            root.showFeedback(key === "mobile" ? "mobile" : key,
                              label + " · " + Strings.tr(enabled ? "On" : "Off", language));
    }
    function stateLabel(available, checked) {
        return !available ? Strings.tr("Unavailable", language)
              : checked ? Strings.tr("On", language) : Strings.tr("Off", language);
    }
    function requestLevel(key, value) {
        if (!root.actionsAllowed || !isFinite(value))
            return;
        if (key === "brightness") {
            root._pendingBrightness = true;
            root._requestedBrightness = value;
            root.backend.setBrightness(value);
        } else if (key === "volume") {
            root._pendingVolume = true;
            root._requestedVolume = value;
            root.backend.setVolume(value);
        }
        pendingTimeout.restart();
    }
    function confirmLevel(key) {
        if (!root.actionsAllowed)
            return;
        if (key === "brightness" && root._pendingBrightness
                && Math.abs(root.backend.brightnessValue - root._requestedBrightness) <= 0.035) {
            root._pendingBrightness = false;
            root.showFeedback("sun", Strings.tr("Brightness", root.language));
        } else if (key === "volume" && root._pendingVolume
                && Math.abs(root.backend.volumeValue - root._requestedVolume) <= 0.035) {
            root._pendingVolume = false;
            root.showFeedback("volume", Strings.tr("Volume", root.language));
        }
    }
    function openDetail(identifier) {
        root.errorMessage = "";
        root.nativePageRequested(identifier);
    }
    Keys.onEscapePressed: {
        if (root.detailActive) root.selectView("controls");
        else root.closeRequested();
    }
    onActionsAllowedChanged: {
        if (!root.actionsAllowed) {
            root.clearPending();
            root._feedbackVisible = false;
        }
    }

    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onActionError(message) {
            root.clearPending();
            root._feedbackVisible = false;
            root.errorMessage = message;
            errorTimer.restart();
        }
        function onVolumePolicyChanged() {
            volumeSlider.cancelInteraction();
        }
        function onWifiEnabledChanged() { root.confirmed("wifi", root.backend.wifiEnabled); }
        function onBluetoothEnabledChanged() { root.confirmed("bluetooth", root.backend.bluetoothEnabled); }
        function onMobileDataEnabledChanged() { root.confirmed("mobile", root.backend.mobileDataEnabled); }
        function onAirplaneEnabledChanged() { root.confirmed("airplane", root.backend.airplaneEnabled); }
        function onSilentEnabledChanged() { root.confirmed("silent", root.backend.silentEnabled); }
        function onRotationLockedChanged() { root.confirmed("rotation", root.backend.rotationLocked); }
        function onBrightnessValueChanged() { root.confirmLevel("brightness"); }
        function onVolumeValueChanged() { root.confirmLevel("volume"); }
    }
    Timer { id: pendingTimeout; interval: 4500; onTriggered: root.clearPending() }
    Timer { id: feedbackTimeout; interval: 1650; onTriggered: root._feedbackVisible = false }
    Timer {
        id: errorTimer
        interval: 7000
        onTriggered: root.errorMessage = ""
    }

    // The scene under Lomiri's panel remains the real Home/application scene.
    // Tint it lightly for legibility; never paint a simulated wallpaper,
    // decorative shapes, or an opaque replacement for the user's wallpaper.
    // An opaque backing is used only when high-contrast mode is requested.
    Rectangle {
        objectName: "glassTranslucentScrim"
        anchors.fill: parent
        color: root.highContrast ? "#0d1221"
               : root.appBehind
                 ? Qt.rgba(0.013, 0.035, 0.093, 0.76)
                 : Qt.rgba(0.013, 0.035, 0.093, 0.66)
        Behavior on color {
            enabled: !root.reducedMotion
            ColorAnimation { duration: 180; easing.type: Easing.OutCubic }
        }
    }

    Column {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: root.gu * 1.4
        anchors.leftMargin: root.gu * 2.8
        anchors.rightMargin: root.gu * 2.8
        spacing: root.gu * 0.55

        Row {
            width: parent.width
            height: root.gu * 5.4
            spacing: root.gu * 0.75
            FocusScope {
                id: backButton
                objectName: "nativeBackButton"
                width: visible ? root.gu * 5.4 : 0
                height: parent.height
                visible: root.detailActive
                activeFocusOnTab: visible
                Accessible.role: Accessible.Button
                Accessible.name: Strings.tr("Back to controls", root.language)
                Accessible.onPressAction: root.selectView("controls")
                Keys.onSpacePressed: root.selectView("controls")
                Keys.onReturnPressed: root.selectView("controls")
                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: "#64405e86"
                    border.width: backButton.activeFocus ? 2 : 1
                    border.color: "#85afbbdf"
                }
                GlassIcon { anchors.centerIn: parent; width: root.gu * 3; height: width; name: "back" }
                MouseArea { anchors.fill: parent; onClicked: root.selectView("controls") }
            }
            Text {
                id: mainTitle
                // Control Center is an edge-to-edge utility sheet, not a
                // headed page. Keep headings for notification/detail views.
                width: parent.width - navigationButtons.width - parent.spacing
                       - (backButton.visible ? backButton.width + parent.spacing : 0)
                anchors.verticalCenter: parent.verticalCenter
                text: root.detailActive ? root.detailTitle
                      : root.mode === "notifications" ? Strings.tr("Notifications", root.language)
                      : ""
                // S10+ usable width is narrower than the concept art. Keep
                // the full Italian heading beside the compact view buttons.
                font.pixelSize: root.gu * (root.detailActive ? 2.25 : 2.35)
                font.weight: Font.DemiBold
                color: "#ffffff"
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }

            Row {
                id: navigationButtons
                width: root.gu * 10.0
                height: root.gu * 4.7
                anchors.verticalCenter: parent.verticalCenter
                spacing: root.gu * 0.45

                Repeater {
                    model: [
                        { key: "notifications", label: Strings.tr("Notifications", root.language), icon: "bell" },
                        { key: "controls", label: Strings.tr("Controls", root.language), icon: "settings" }
                    ]
                    delegate: FocusScope {
                        id: navigationButton
                        objectName: modelData.key + "Tab"
                        width: root.gu * 4.7
                        height: parent.height
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.label
                        Accessible.description: root.mode === modelData.key ? Strings.tr("Selected", root.language) : ""
                        Accessible.onPressAction: root.selectView(modelData.key)
                        Keys.onSpacePressed: root.selectView(modelData.key)
                        Keys.onReturnPressed: root.selectView(modelData.key)
                        Rectangle {
                            anchors.fill: parent
                            radius: height / 2
                            color: root.mode === modelData.key ? "#a95888d0" : "#71415f8e"
                            border.width: navigationButton.activeFocus ? 2 : 1
                            border.color: "#8ab2c6f0"
                        }
                        GlassIcon {
                            anchors.centerIn: parent
                            width: root.gu * 2.4
                            height: width
                            name: modelData.icon
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: { navigationButton.forceActiveFocus(); root.selectView(modelData.key); }
                        }
                    }
                }
            }
        }

        Text {
            width: parent.width
            height: visible ? implicitHeight : 0
            visible: root.mode === "notifications" || root.detailActive
            text: root.detailActive ? Strings.tr("Quick settings", root.language)
                  : root.mode === "notifications"
                    ? Qt.formatDate(new Date(), "dddd d MMMM")
                    : ""
            color: "#d4d4ee"
            font.pixelSize: root.gu * 1.45
            textFormat: Text.PlainText
        }

        Rectangle {
            width: parent.width
            height: visible ? errorText.height + root.gu * 2 : 0
            radius: root.gu * 1.5
            color: "#c96c4567"
            visible: root.errorMessage.length > 0
            Text {
                id: errorText
                x: root.gu
                y: root.gu
                width: parent.width - root.gu * 2
                text: root.errorMessage
                textFormat: Text.PlainText
                color: "#ffffff"
                wrapMode: Text.Wrap
                font.pixelSize: root.gu * 1.6
            }
        }
    }

    Flickable {
        id: controlsView
        objectName: "controlsScrollView"
        anchors.top: header.bottom
        anchors.topMargin: root.gu * 2.0
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        visible: !root.nativeVisible
        contentWidth: width
        contentHeight: controlsColumn.height + root.gu * 3
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height

        Column {
            id: controlsColumn
            width: Math.min(parent.width - root.gu * 4, root.gu * 112)
            x: (controlsView.width - width) / 2
            spacing: root.gu * 1.3
            Column {
                id: mosaic
                width: parent.width
                spacing: root.gu * 1.3

                Row {
                    id: topRow
                    width: parent.width
                    height: Math.max(root.gu * 22, Math.min(root.gu * 36, controlsView.height * 0.30))
                    spacing: root.gu * 1.2

                Item {
                    id: connectivityCard
                    width: (topRow.width - topRow.spacing) / 2
                    height: topRow.height
                    Rectangle {
                        anchors.fill: parent
                        radius: root.gu * 3.0
                        color: root.highContrast ? "#233a65" : "#80314972"
                        border.width: 1
                        border.color: "#8aa5b4d1"
                    }

                Grid {
                    id: connectivityGrid
                    anchors.fill: parent
                    columns: 2
                    spacing: root.gu * 0.55
                    GlassTile {
                        objectName: "wifiTile"
                        width: (connectivityGrid.width - connectivityGrid.spacing) / 2
                        height: (connectivityGrid.height - connectivityGrid.spacing) / 2
                        gu: root.gu
                        iconOnly: true
                        title: Strings.tr("Wi-Fi", root.language)
                        iconName: "wifi"
                        accent: "#14a4ff"
                        checked: root.backend !== null && root.backend.wifiEnabled
                        available: root.actionsAllowed && root.backend.wifiAvailable
                        subtitle: root.stateLabel(available, checked)
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onActivated: root.requestToggle("wifi")
                        onDetailRequested: root.openDetail("wifi")
                    }
                    GlassTile {
                        objectName: "bluetoothTile"
                        width: (connectivityGrid.width - connectivityGrid.spacing) / 2
                        height: (connectivityGrid.height - connectivityGrid.spacing) / 2
                        gu: root.gu
                        iconOnly: true
                        title: Strings.tr("Bluetooth", root.language)
                        iconName: "bluetooth"
                        accent: "#168bff"
                        checked: root.backend !== null && root.backend.bluetoothEnabled
                        available: root.actionsAllowed && root.backend.bluetoothAvailable
                        subtitle: root.stateLabel(available, checked)
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onActivated: root.requestToggle("bluetooth")
                        onDetailRequested: root.openDetail("bluetooth")
                    }
                    GlassTile {
                        objectName: "mobileDataTile"
                        width: (connectivityGrid.width - connectivityGrid.spacing) / 2
                        height: (connectivityGrid.height - connectivityGrid.spacing) / 2
                        gu: root.gu
                        iconOnly: true
                        // Smaller displays use a genuine short label, not an
                        // ellipsis that makes the native control ambiguous.
                        title: Strings.tr(root.width < 390 ? "Data" : "Mobile data", root.language)
                        iconName: "mobile"
                        accent: "#22bb78"
                        checked: root.backend !== null && root.backend.mobileDataEnabled
                        available: root.actionsAllowed && root.backend.mobileDataAvailable
                        subtitle: root.stateLabel(available, checked)
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onActivated: root.requestToggle("mobile")
                        onDetailRequested: root.openDetail("mobile")
                    }
                    GlassTile {
                        objectName: "airplaneTile"
                        width: (connectivityGrid.width - connectivityGrid.spacing) / 2
                        height: (connectivityGrid.height - connectivityGrid.spacing) / 2
                        gu: root.gu
                        iconOnly: true
                        title: Strings.tr("Airplane", root.language)
                        iconName: "airplane"
                        accent: "#8d91b9"
                        checked: root.backend !== null && root.backend.airplaneEnabled
                        available: root.actionsAllowed && root.backend.airplaneAvailable
                        subtitle: root.stateLabel(available, checked)
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onActivated: root.requestToggle("airplane")
                        onDetailRequested: root.openDetail("airplane")
                    }
                }

                } // connectivityCard

                } // topRow; mediaCard is parented into it below.

                Row {
                    id: mediaRow
                    width: parent.width
                    height: Math.max(root.gu * 23, Math.min(root.gu * 39, controlsView.height * 0.34))
                    spacing: root.gu * 1.2

                    FocusScope {
                        id: mediaCard
                        objectName: "soundDetailButton"
                        parent: topRow
                        width: (topRow.width - topRow.spacing) / 2
                        height: topRow.height
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: Strings.tr("Audio and playback", root.language)
                        Accessible.onPressAction: root.openDetail("sound")
                        Keys.onSpacePressed: root.openDetail("sound")
                        Keys.onReturnPressed: root.openDetail("sound")
                        Rectangle {
                            anchors.fill: parent
                            radius: root.gu * 3.0
                            color: "#80314972"
                            border.width: mediaCard.activeFocus ? 2 : 1
                            border.color: "#769ea3c6"
                        }
                        Rectangle {
                            id: mediaArt
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.leftMargin: root.gu * 1.8
                            anchors.topMargin: root.gu * 2.0
                            width: Math.min(root.gu * 9.0, mediaCard.width - root.gu * 3.6)
                            height: width
                            radius: root.gu * 1.8
                            color: "#527594c3"
                            border.width: 1
                            border.color: "#7cb6cde5"
                            GlassIcon {
                                anchors.centerIn: parent
                                width: parent.width * 0.48
                                height: width
                                name: "sound"
                                color: "#ffffff"
                            }
                        }
                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: mediaArt.bottom
                            anchors.leftMargin: root.gu * 1.7
                            anchors.rightMargin: root.gu * 1.7
                            anchors.topMargin: root.gu * 1.8
                            text: Strings.tr("Audio", root.language)
                            color: "#ffffff"
                            font.pixelSize: root.gu * 2.0
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                        Row {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.leftMargin: root.gu * 1.8
                            anchors.rightMargin: root.gu * 1.8
                            anchors.bottomMargin: root.gu * 2.0
                            spacing: root.gu * 0.5
                            Text {
                                width: parent.width - root.gu * 2
                                text: Strings.tr("Open media controls", root.language)
                                color: "#d3e5ff"
                                font.pixelSize: root.gu * 1.3
                                elide: Text.ElideRight
                            }
                            GlassIcon { width: root.gu * 1.5; height: width; name: "chevron" }
                        }
                        MouseArea { anchors.fill: parent; onClicked: root.openDetail("sound") }
                    }

                    GlassSlider {
                        objectName: "brightnessSlider"
                        width: (mediaRow.width - mediaRow.spacing * 2) / 4
                        height: parent.height
                        gu: root.gu
                        title: Strings.tr("Brightness", root.language)
                        iconName: "sun"
                        value: root.backend !== null ? root.backend.brightnessValue : 0
                        available: root.actionsAllowed && root.backend.brightnessAvailable
                        automatic: root.backend !== null && root.backend.brightnessAutomatic
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onValueRequested: {
                            root.requestLevel("brightness", value);
                        }
                        onDetailRequested: root.openDetail("power")
                    }
                    GlassSlider {
                        id: volumeSlider
                        objectName: "volumeSlider"
                        width: (mediaRow.width - mediaRow.spacing * 2) / 4
                        height: parent.height
                        gu: root.gu
                        title: Strings.tr("Volume", root.language)
                        iconName: "volume"
                        value: root.backend !== null ? root.backend.volumeValue : 0
                        available: root.actionsAllowed && root.backend.volumeAvailable
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onValueRequested: {
                            root.requestLevel("volume", value);
                        }
                        onDetailRequested: root.openDetail("sound")
                    }
                }

                Grid {
                    id: shortcutsGrid
                    parent: mediaRow
                    width: (mediaRow.width - mediaRow.spacing * 2) / 2
                    height: mediaRow.height
                    columns: 2
                    spacing: root.gu * 0.9

                    GlassTile {
                        objectName: "silentTile"
                        width: (shortcutsGrid.width - shortcutsGrid.spacing) / 2
                        height: (shortcutsGrid.height - shortcutsGrid.spacing) / 2
                        gu: root.gu
                        iconOnly: true
                        title: Strings.tr("Silent", root.language)
                        iconName: "moon"
                        accent: "#8e96ec"
                        checked: root.backend !== null && root.backend.silentEnabled
                        available: root.actionsAllowed && root.backend.silentAvailable
                        subtitle: root.stateLabel(available, checked)
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onActivated: root.requestToggle("silent")
                        onDetailRequested: root.openDetail("sound")
                    }
                    GlassTile {
                        objectName: "rotationTile"
                        width: (shortcutsGrid.width - shortcutsGrid.spacing) / 2
                        height: (shortcutsGrid.height - shortcutsGrid.spacing) / 2
                        gu: root.gu
                        iconOnly: true
                        title: Strings.tr("Rotation", root.language)
                        iconName: "rotation"
                        accent: "#168bff"
                        checked: root.backend !== null && root.backend.rotationLocked
                        available: root.actionsAllowed && root.backend.rotationAvailable
                        subtitle: !available ? Strings.tr("Unavailable", root.language)
                                 : checked ? Strings.tr("Locked", root.language) : Strings.tr("Automatic", root.language)
                        highContrast: root.highContrast
                        lightSurface: root.lightSurface
                        language: root.language
                        reducedMotion: root.reducedMotion
                        onActivated: root.requestToggle("rotation")
                        onDetailRequested: root.openDetail("rotation")
                    }
                    Repeater {
                        model: [
                            { title: Strings.tr("Audio", root.language), icon: "volume", target: "sound" },
                            { title: Strings.tr("System", root.language), icon: "settings", target: "session" }
                        ]
                        delegate: GlassTile {
                            objectName: modelData.target + "DetailButton"
                            width: (shortcutsGrid.width - shortcutsGrid.spacing) / 2
                            height: (shortcutsGrid.height - shortcutsGrid.spacing) / 2
                            gu: root.gu
                            iconOnly: true
                            title: modelData.title
                            iconName: modelData.icon
                            available: root.actionsAllowed
                            subtitle: Strings.tr("Open", root.language)
                            highContrast: root.highContrast
                            lightSurface: root.lightSurface
                            language: root.language
                            reducedMotion: root.reducedMotion
                            onActivated: root.openDetail(modelData.target)
                            onDetailRequested: root.openDetail(modelData.target)
                        }
                    }
                }

                // A separate, four-column utility row mirrors the visual
                // rhythm of the reference. Every button opens a real Lomiri
                // surface; none pretends that an unavailable camera/torch
                // command has changed hardware state.
                Row {
                    id: utilitiesRow
                    objectName: "uos27UtilityShortcuts"
                    width: mosaic.width
                    height: root.gu * 10.5
                    spacing: root.gu * 1.3

                    Repeater {
                        model: [
                            { key: "notifications", icon: "bell", label: Strings.tr("Notifications", root.language), page: "" },
                            { key: "clock", icon: "clock", label: Strings.tr("Date and time", root.language), page: "datetime" },
                            { key: "battery", icon: "battery", label: Strings.tr("Display and battery", root.language), page: "power" },
                            { key: "system", icon: "settings", label: Strings.tr("System", root.language), page: "session" }
                        ]
                        delegate: FocusScope {
                            id: utility
                            objectName: modelData.key + "UtilityShortcut"
                            width: (utilitiesRow.width - utilitiesRow.spacing * 3) / 4
                            height: utilitiesRow.height
                            activeFocusOnTab: true
                            Accessible.role: Accessible.Button
                            Accessible.name: modelData.label
                            Accessible.onPressAction: activateUtility()
                            Keys.onSpacePressed: activateUtility()
                            Keys.onReturnPressed: activateUtility()
                            function activateUtility() {
                                if (!root.actionsAllowed)
                                    return;
                                if (modelData.key === "notifications")
                                    root.selectView("notifications");
                                else
                                    root.openDetail(modelData.page);
                            }
                            Rectangle {
                                width: Math.min(utility.width, utility.height - root.gu * 0.7)
                                height: width
                                radius: width / 2
                                anchors.centerIn: parent
                                color: root.highContrast ? "#273f62" : "#a032507a"
                                border.width: utility.activeFocus ? 2 : 1
                                border.color: utility.activeFocus ? "#bddaff" : "#869eb9d8"
                                Behavior on color {
                                    enabled: !root.reducedMotion
                                    ColorAnimation { duration: 160 }
                                }
                                GlassIcon {
                                    anchors.centerIn: parent
                                    width: parent.width * 0.42
                                    height: width
                                    name: modelData.icon
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                enabled: root.actionsAllowed
                                onClicked: utility.activateUtility()
                            }
                        }
                    }
                }
                FocusScope {
                    id: automaticDisplay
                    objectName: "automaticBrightnessSettings"
                    width: mosaic.width
                    height: root.gu * 10.5
                    activeFocusOnTab: true
                    readonly property bool supported: root.backend !== null
                        && root.backend.automaticBrightnessAvailable === true
                    Accessible.role: Accessible.Button
                    Accessible.name: "Luminosità automatica"
                      Accessible.description: supported ? "Apri le impostazioni schermo" : "Disponibilità da verificare"
                    Accessible.onPressAction: root.openDetail("power")
                    Keys.onReturnPressed: root.openDetail("power")
                    Rectangle {
                        anchors.fill: parent
                        radius: root.gu * 3.0
                        color: root.highContrast ? "#233a65" : "#66314972"
                        border.width: automaticDisplay.activeFocus ? 2 : 1
                        border.color: "#698eabc9"
                    }
                    GlassIcon {
                        x: root.gu * 2.2; anchors.verticalCenter: parent.verticalCenter
                        width: root.gu * 3.0; height: width; name: "sun"
                    }
                    Column {
                          x: root.gu * 7.0; width: parent.width - x - root.gu * 11
                        anchors.verticalCenter: parent.verticalCenter; spacing: root.gu * 0.5
                          Text { width: parent.width; text: "Luminosità"; color: "white"; font.pixelSize: root.gu * 1.8; font.weight: Font.DemiBold; elide: Text.ElideRight }
                          Text { width: parent.width; text: automaticDisplay.supported ? "Automatica" : root.backend !== null && root.backend.automaticBrightnessSupportKnown === true ? "Automatica non disponibile" : "Verifica disponibilità…"; color: "#d7e5f5"; font.pixelSize: root.gu * 1.5; elide: Text.ElideRight }
                    }
                    MouseArea { anchors.fill: parent; enabled: root.actionsAllowed; onClicked: root.openDetail("power") }
                      FocusScope {
                          id: automaticSwitch
                          objectName: "automaticBrightnessSwitch"
                          anchors.right: parent.right; anchors.rightMargin: root.gu * 2
                          anchors.verticalCenter: parent.verticalCenter
                          width: root.gu * 7.0; height: root.gu * 5.5
                          activeFocusOnTab: automaticDisplay.supported && root.actionsAllowed
                          readonly property bool checked: root.backend !== null && root.backend.brightnessAutomatic === true
                          readonly property bool available: automaticDisplay.supported && root.actionsAllowed
                          function requestToggle() {
                              if (available) root.backend.setAutomaticBrightness(!checked);
                          }
                          Accessible.role: Accessible.CheckBox
                          Accessible.name: "Luminosità automatica"
                          Accessible.checked: checked
                          Accessible.onPressAction: requestToggle()
                          Keys.onSpacePressed: requestToggle()
                          Keys.onReturnPressed: requestToggle()
                          Rectangle {
                              anchors.centerIn: parent; width: root.gu * 6.3; height: root.gu * 3.8
                              radius: height / 2
                              color: automaticSwitch.checked ? "#37bc82" : "#58738b"
                              opacity: automaticSwitch.available ? 1 : 0.42
                              border.width: automaticSwitch.activeFocus ? 2 : 0; border.color: "white"
                              Rectangle {
                                  width: parent.height - root.gu * 0.6; height: width; radius: height / 2
                                  x: automaticSwitch.checked ? parent.width - width - root.gu * 0.3 : root.gu * 0.3
                                  y: root.gu * 0.3; color: "white"
                                  Behavior on x { NumberAnimation { duration: root.reducedMotion ? 0 : 170; easing.type: Easing.OutCubic } }
                              }
                          }
                          MouseArea { anchors.fill: parent; enabled: automaticSwitch.available; onClicked: automaticSwitch.requestToggle() }
                      }
                }
            }
        }
    }

    Item {
        id: nativeHost
        objectName: "nativeContentHost"
        anchors.top: header.bottom
        anchors.topMargin: root.gu * 2
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: root.nativeVisible && root.nativePageAvailable
        clip: true
        // The integrator reparents Lomiri's MenuContent here. No model is copied,
        // no notification body is cached and no gesture-eating overlay is added.
    }

    Column {
        anchors.centerIn: nativeHost
        width: root.width - root.gu * 8
        spacing: root.gu * 2
        visible: root.nativeVisible && !root.nativePageAvailable
        GlassIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.gu * 6
            height: width
            name: root.mode === "notifications" ? "bell" : "settings"
            color: "#b5c9df"
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: root.mode === "notifications" ? Strings.tr("Notifications service unavailable", root.language)
                  : Strings.tr("This control is unavailable", root.language)
            color: "#f0f5fc"
            font.pixelSize: root.gu * 2
            font.weight: Font.DemiBold
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: Strings.tr("Try again shortly. Other controls remain available.", root.language)
            color: "#c4d0df"
            font.pixelSize: root.gu * 1.6
        }
    }

    // A confirmation pill for explicit user gestures. Radio toggles only
    // announce ON/OFF after the backend publishes the corresponding state.
    // No fake progress or hardware success is shown on submission alone.
    Rectangle {
        id: controlFeedback
        objectName: "uos27ControlFeedback"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.gu * 3.6
        width: Math.max(root.gu * 18, Math.min(root.width - root.gu * 5, root.gu * 45))
        height: root.gu * 6.6
        radius: height / 2
        color: "#ec202740"
        border.color: "#8eafbadb"
        border.width: 1
        visible: root._feedbackVisible || opacity > 0.01
        opacity: root._feedbackVisible ? 1 : 0
        Behavior on opacity {
            enabled: !root.reducedMotion
            NumberAnimation { duration: 190; easing.type: Easing.OutCubic }
        }
        transform: Translate {
            y: root._feedbackVisible ? 0 : root.gu * 1.6
            Behavior on y {
                enabled: !root.reducedMotion
                NumberAnimation { duration: 210; easing.type: Easing.OutCubic }
            }
        }
        Row {
            anchors.centerIn: parent
            spacing: root.gu * 1.1
            GlassIcon {
                width: root.gu * 3.1
                height: width
                name: root._feedbackIcon
                color: "#ffffff"
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root._feedbackLabel
                textFormat: Text.PlainText
                font.pixelSize: root.gu * 1.85
                font.weight: Font.DemiBold
                color: "#ffffff"
            }
        }
    }
}
