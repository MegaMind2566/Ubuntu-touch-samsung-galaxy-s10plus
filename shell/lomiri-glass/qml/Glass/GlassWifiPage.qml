// SPDX-License-Identifier: GPL-3.0-only
// This is the *Wi-Fi settings* menu exported by the native indicator. Unlike
// /phone, it contains neither Ethernet nor mobile-data/airplane sections.
import QtQuick 2.15
import QMenuModel 1.0
import ".." as NativePanel
import "../Indicators" as NativeIndicators

Item {
    id: root
    property bool actionsAllowed: false

    AyatanaMenuModel {
        id: wifiNetworks
        busName: "com.lomiri.indicator.network"
        actions: ({ "indicator": "/com/lomiri/indicator/network" })
        menuObjectPath: "/com/lomiri/indicator/network/phone_wifi_settings"
    }

    NativePanel.PanelMenuPage {
        id: networksPage
        objectName: "glassNativeWifiAccessPoints"
        anchors.fill: parent
        visible: root.actionsAllowed
        enabled: root.actionsAllowed
        menuModel: wifiNetworks
        // The dedicated settings model exports entries directly; unlike the
        // /phone indicator menu it has no index-0 root submenu to unwrap.
        factory: NativeIndicators.IndicatorMenuItemFactory {
            indicator: "indicator-network"
            rootModel: wifiNetworks
        }
    }
}
