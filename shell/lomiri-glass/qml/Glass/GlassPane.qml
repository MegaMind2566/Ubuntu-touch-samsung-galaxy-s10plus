// SPDX-License-Identifier: GPL-3.0-only
// Lomiri-specific host for the independently renderable GlassCenter surface.
// The existing MenuContent is visually parented into nativeContentHost by
// PanelMenu. No notification contents or action parameters are copied here.
import QtQuick 2.15
import Lomiri.Components 1.3
import "GlassStrings.js" as Strings

StyledItem {
    id: root
    property var indicatorModel: null
    property bool panelVisible: false
    property bool actionsAllowed: false
    // Lightweight transforms and opacity are enabled by default; the caller
    // can switch to reduced motion without changing any control semantics.
    property bool reducedMotion: false
    property bool highContrast: false
    property bool applicationBehind: false
    readonly property string systemLanguage: typeof i18n !== "undefined" && i18n.language
          ? i18n.language : Qt.locale().name
    readonly property bool lightSurface: !highContrast && theme.palette.normal.background.hslLightness >= 0.5
    property string requestedIndicator: ""
    property alias nativeContentHost: center.nativeContentHost
    // Wi-Fi and cellular use dedicated pages; the old broad network menu
    // would also expose disconnected Ethernet and unrelated controls.
    readonly property bool nativeVisible: center.nativeVisible && center.nativePageAvailable
            && requestedIndicator !== "wifi" && requestedIndicator !== "mobile"
            && requestedIndicator !== "airplane"
    readonly property bool notificationView: center.mode === "notifications"
    signal menuIndexRequested(int index)
    signal closeRequested()

    // Inherit Lomiri's active theme; never pin SuruDark over a light profile.

    function selectView(view) {
        center.selectView(view === "notifications" ? "notifications" : "controls");
    }

    function beginGesture(horizontalFraction) {
        selectView(horizontalFraction < 0.5 ? "notifications" : "controls");
    }

    function refreshNativeSelection() {
        if (!requestedIndicator.length)
            return;
        for (var n = 0; n < catalog.count; ++n) {
            var entry = catalog.itemAt(n);
            if (!entry)
                continue;
            var identifier = entry.identifier;
            if (identifier === "ayatana-indicator-" + requestedIndicator
                    || identifier === "indicator-" + requestedIndicator) {
                center.nativePageAvailable = true;
                menuIndexRequested(n);
                return;
            }
        }
        center.nativePageAvailable = false;
    }

    function openNativePage(key) {
        var mapped = key === "rotation" ? "display" : key;
        var labels = {
            wifi: Strings.tr("Wi-Fi", systemLanguage),
            mobile: Strings.tr("Mobile data", systemLanguage),
            airplane: Strings.tr("Airplane mode", systemLanguage),
            network: Strings.tr("Connections", systemLanguage), bluetooth: Strings.tr("Bluetooth", systemLanguage),
            sound: Strings.tr("Audio and playback", systemLanguage), power: Strings.tr("Display and battery", systemLanguage),
            display: Strings.tr("Screen rotation", systemLanguage), datetime: Strings.tr("Date and time", systemLanguage),
            session: Strings.tr("System", systemLanguage), messages: Strings.tr("Your notifications", systemLanguage)
        };
        if (!labels.hasOwnProperty(mapped))
            return;
        requestedIndicator = mapped;
        center.detailTitle = labels[mapped];
        center.detailActive = true;
        if (mapped === "wifi" || mapped === "mobile" || mapped === "airplane") {
            center.nativePageAvailable = true;
            return;
        }
        refreshNativeSelection();
    }

    // Use the same profile-filtered model already loaded by Shell.qml. Never
    // construct a second unrestricted notification model for a greeter.
    Repeater {
        id: catalog
        model: root.indicatorModel
        delegate: Item {
            visible: false
            property string identifier: model.identifier
            property int rowIndex: index
            onIdentifierChanged: Qt.callLater(root.refreshNativeSelection)
            onRowIndexChanged: Qt.callLater(root.refreshNativeSelection)
        }
        onItemAdded: Qt.callLater(root.refreshNativeSelection)
        onItemRemoved: Qt.callLater(root.refreshNativeSelection)
    }

    Loader {
        id: backendLoader
        // Subscribe before the *first* pull-down: Ayatana's first brightness
        // GAction snapshot is asynchronous and constructing the group only
        // when the slider is exposed leaves an empty/stale initial fill.
        // No mutation is allowed until actionsAllowed AND panelVisible.
        active: true
        sourceComponent: NativeBackend {
            language: root.systemLanguage
            actionsAllowed: root.actionsAllowed && root.panelVisible
        }
    }

    GlassCenter {
        id: center
        anchors.fill: parent
        gu: units.gu(1)
        language: root.systemLanguage
        lightSurface: root.lightSurface
        backend: backendLoader.item
        enabled: root.actionsAllowed
        reducedMotion: root.reducedMotion
        highContrast: root.highContrast
        appBehind: root.applicationBehind
        onCloseRequested: root.closeRequested()
        onNativePageRequested: root.openNativePage(identifier)
        onViewSelected: {
            root.requestedIndicator = view === "notifications" ? "messages" : "";
            root.refreshNativeSelection();
        }
    }

    // Load the system-owned Wi-Fi list only when requested. Its dedicated
    // exported menu contains access points, not the general network/ethernet
    // screen, and keeps the same native actions as System Settings.
    Loader {
        id: wirelessDetail
        objectName: "glassWifiOnlyDetail"
        parent: center.nativeContentHost
        anchors.fill: parent
        active: root.requestedIndicator === "wifi" && root.panelVisible && center.detailActive
        visible: active
        source: "GlassWifiPage.qml"
        onLoaded: item.actionsAllowed = Qt.binding(function() { return root.actionsAllowed; })
    }

    Column {
        id: cellularDetail
        objectName: "glassMobileOnlyDetail"
        parent: center.nativeContentHost
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: units.gu(2.3)
        anchors.rightMargin: units.gu(2.3)
        spacing: units.gu(1.4)
        visible: center.detailActive && root.panelVisible
                && (root.requestedIndicator === "mobile" || root.requestedIndicator === "airplane")

        GlassTile {
            objectName: "mobileDetailRadioSwitch"
            width: cellularDetail.width
            height: units.gu(11)
            gu: units.gu(1)
            title: root.requestedIndicator === "airplane"
                    ? Strings.tr("Airplane mode", root.systemLanguage)
                    : Strings.tr("Mobile data", root.systemLanguage)
            iconName: root.requestedIndicator === "airplane" ? "airplane" : "mobile"
            checked: backendLoader.item && (root.requestedIndicator === "airplane"
                    ? backendLoader.item.airplaneEnabled : backendLoader.item.mobileDataEnabled)
            available: root.actionsAllowed && backendLoader.item && (root.requestedIndicator === "airplane"
                    ? backendLoader.item.airplaneAvailable : backendLoader.item.mobileDataAvailable)
            subtitle: !available ? Strings.tr("Unavailable", root.systemLanguage)
                    : checked ? Strings.tr("On", root.systemLanguage) : Strings.tr("Off", root.systemLanguage)
            language: root.systemLanguage
            lightSurface: root.lightSurface
            highContrast: root.highContrast
            reducedMotion: root.reducedMotion
            onActivated: {
                if (root.requestedIndicator === "airplane") backendLoader.item.toggleAirplane();
                else backendLoader.item.toggleMobileData();
            }
        }

        GlassTile {
            objectName: "mobileSettingsLink"
            width: cellularDetail.width
            height: units.gu(11)
            gu: units.gu(1)
            visible: root.requestedIndicator === "mobile"
            title: Strings.tr("SIM and mobile network settings", root.systemLanguage)
            iconName: "settings"
            available: root.actionsAllowed
            subtitle: Strings.tr("Open", root.systemLanguage)
            language: root.systemLanguage
            lightSurface: root.lightSurface
            highContrast: root.highContrast
            reducedMotion: root.reducedMotion
            onActivated: Qt.openUrlExternally("settings:///system/cellular")
        }
    }
}
