// SPDX-License-Identifier: GPL-3.0-only
// uOS27 Home. Lomiri's app drawer lists *all* installed applications;
// the separate pinned launcher model supplies the dock only.
// No simulated apps, assets, telephony state or private application database.
import QtQuick 2.15
import Lomiri.Components 1.3
import Lomiri.Launcher 0.1
import Utils 0.1
import "GlassTheme.js" as UOS
import "GlassStrings.js" as Strings

FocusScope {
    id: root
    objectName: "uos27Home"
    property bool reducedMotion: false
    property string language: "en"
    property real topInset: 0
    property url wallpaper
    property bool wallpaperCoverVisible: false
    property bool searchOpen: false
    signal applicationSelected(string appId)
    clip: true

    // Stage draws the native wallpaper when no app runs. On returning Home
    // above a live application, shield its contents with that same image.
    // The wallpaper is asynchronous. Never show a frame of the application
    // underneath while its image is still loading (or if its URL is absent).
    Rectangle {
        objectName: "uos27HomePrivacyBacking"
        anchors.fill: parent
        color: "#121929"
        visible: root.wallpaperCoverVisible
    }
    Image {
        id: homeWallpaperCover
        anchors.fill: parent
        visible: root.wallpaperCoverVisible
        source: root.wallpaper
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
    }

    // With an app still running below Home, no blank space may forward taps
    // or accidental gestures to that application's private UI.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onPressed: mouse.accepted = true
    }

    AppDrawerModel { id: installedApplications }
    AppDrawerProxyModel {
        id: visibleApplications
        source: installedApplications
        // Native AppDrawerProxyModel defaults to SortByAToZ (verified source).
        filterString: root.searchOpen ? searchInput.text : ""
    }

    Connections {
        target: i18n
        function onLanguageChanged() { installedApplications.refresh() }
    }

    onVisibleChanged: {
        if (!visible) closeSearch();
    }

    function openSearch() {
        searchOpen = true;
        searchInput.forceActiveFocus();
    }

    function closeSearch() {
        if (!searchOpen)
            return;
        searchOpen = false;
        searchInput.text = "";
        searchInput.focus = false;
        favorites.positionViewAtBeginning();
    }

    Flickable {
        id: favorites
        objectName: "uos27HomeGrid"
        anchors {
            top: parent.top
            topMargin: root.topInset + units.gu(root.searchOpen ? 11 : 3)
            left: parent.left
            leftMargin: units.gu(2)
            right: parent.right
            rightMargin: units.gu(2)
            bottom: dock.top
            bottomMargin: units.gu(8)
        }
        clip: true
        property var model: visibleApplications
        readonly property int count: applicationTiles.count
        // Native installed catalog covers unpinned apps, new installs and
        // removals. Dock launch paths remain pinned, unlike the page grid.
        readonly property int columns: width > height * 1.6 ? 6 : 4
        readonly property real cellWidth: width / columns
        readonly property real cellHeight: units.gu(12.0)
        readonly property int rows: Math.max(1, Math.floor(height / cellHeight))
        readonly property int itemsPerPage: columns * rows
        readonly property int pageCount: Math.max(1, Math.ceil(count / itemsPerPage))
        readonly property int currentPage: Math.max(0, Math.min(pageCount - 1,
                                                  Math.round(contentX / Math.max(1, width))))
        contentWidth: pageCount * width
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        function positionViewAtBeginning() { contentX = 0; }
        boundsBehavior: Flickable.StopAtBounds
        interactive: pageCount > 1
        onMovementEnded: {
            if (!root.reducedMotion && pageCount > 1) {
                var target = Math.min(Math.max(0, contentWidth - width), currentPage * width);
                if (Math.abs(contentX - target) > 1) {
                    settleAnimation.to = target;
                    settleAnimation.restart();
                }
            }
        }
        NumberAnimation {
            id: settleAnimation
            target: favorites
            property: "contentX"
            duration: 175
            easing.type: Easing.OutCubic
        }
        Repeater {
          id: applicationTiles
          model: favorites.model
          delegate: Item {
            id: favorite
            readonly property int indexOnPage: index % favorites.itemsPerPage
            x: Math.floor(index / favorites.itemsPerPage) * favorites.width
               + (indexOnPage % favorites.columns) * favorites.cellWidth
            y: Math.floor(indexOnPage / favorites.columns) * favorites.cellHeight
            objectName: "uos27HomeApp_" + model.appId
            width: favorites.cellWidth
            height: favorites.cellHeight
            activeFocusOnTab: true
            property string applicationId: model.appId
            property bool pressed: favoriteTap.pressed
            Accessible.role: Accessible.Button
            Accessible.name: model.name
            Accessible.onPressAction: root.applicationSelected(favorite.applicationId)
            Keys.onReturnPressed: root.applicationSelected(favorite.applicationId)
            Keys.onSpacePressed: root.applicationSelected(favorite.applicationId)
            scale: favorite.pressed && !root.reducedMotion ? 0.94 : 1
            Behavior on scale {
                enabled: !root.reducedMotion
                NumberAnimation { duration: UOS.pressMs; easing.type: Easing.OutCubic }
            }

            Column {
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - units.gu(0.6)
                spacing: units.gu(0.75)
                LomiriShape {
                    width: Math.min(units.gu(7.5), favorite.width - units.gu(2))
                    height: width
                    anchors.horizontalCenter: parent.horizontalCenter
                    radius: "medium"
                    aspect: LomiriShape.Flat
                    source: Image {
                        asynchronous: true
                        source: model.icon
                        sourceSize.width: units.gu(8)
                        sourceSize.height: units.gu(8)
                    }
                    sourceFillMode: LomiriShape.PreserveAspectCrop
                }
                Text {
                    text: model.name
                    color: UOS.ink
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                    font.pixelSize: units.gu(1.45)
                    font.weight: Font.Medium
                    maximumLineCount: 2
                    wrapMode: Text.Wrap
                    elide: Text.ElideRight
                    style: Text.Raised
                    styleColor: "#80070d1e"
                }
            }
            MouseArea {
                id: favoriteTap
                anchors.fill: parent
                onClicked: root.applicationSelected(favorite.applicationId)
            }
          }
        }
    }

    Row {
        objectName: "uos27HomePagination"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: dock.top
        anchors.bottomMargin: units.gu(8.2)
        spacing: units.gu(0.55)
        visible: favorites.pageCount > 1
        Repeater {
            model: favorites.pageCount
            Rectangle {
                width: index === favorites.currentPage ? units.gu(1.0) : units.gu(0.7)
                height: units.gu(0.7)
                radius: height / 2
                color: index === favorites.currentPage ? UOS.ink : UOS.muted
                opacity: index === favorites.currentPage ? 1 : 0.52
                Behavior on width {
                    enabled: !root.reducedMotion
                    NumberAnimation { duration: UOS.stateMs }
                }
            }
        }
    }

    Rectangle {
        id: dock
        objectName: "uos27HomeDock"
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            leftMargin: units.gu(2.0)
            rightMargin: units.gu(2.0)
            bottomMargin: units.gu(2.3)
        }
        height: units.gu(9.2)
        radius: units.gu(3.0)
        color: UOS.shellBackground
        border.width: 1
        border.color: UOS.border

        Row {
            anchors.fill: parent
            anchors.margins: units.gu(1.15)
            spacing: 0
            Repeater {
                model: 4
                Item {
                    id: dockItem
                    width: dock.width / 4 - units.gu(0.6)
                    height: parent.height
                    readonly property var pinned: LauncherModel.get(index)
                    readonly property string appId: pinned && pinned.appId ? pinned.appId : ""
                    activeFocusOnTab: appId !== ""
                    Accessible.role: Accessible.Button
                    Accessible.name: pinned && pinned.name ? pinned.name : ""
                    Accessible.onPressAction: {
                        if (dockItem.appId) root.applicationSelected(dockItem.appId);
                    }
                    Keys.onReturnPressed: {
                        if (dockItem.appId) root.applicationSelected(dockItem.appId);
                    }
                    scale: dockTap.pressed && !root.reducedMotion ? 0.94 : 1
                    Behavior on scale {
                        enabled: !root.reducedMotion
                        NumberAnimation { duration: UOS.pressMs; easing.type: Easing.OutCubic }
                    }
                    LomiriShape {
                        width: Math.min(parent.width, parent.height)
                        height: width
                        anchors.centerIn: parent
                        radius: "medium"
                        source: Image {
                            asynchronous: true
                            source: dockItem.pinned ? dockItem.pinned.icon : ""
                            sourceSize.width: units.gu(8)
                        }
                        sourceFillMode: LomiriShape.PreserveAspectCrop
                    }
                    MouseArea {
                        id: dockTap
                        anchors.fill: parent
                        enabled: dockItem.appId !== ""
                        onClicked: root.applicationSelected(dockItem.appId)
                    }
                }
            }
        }
    }

    // Search filters the SAME native catalog as the desktop Home grid. There
    // is no secondary app database and no request for the side Drawer.
    Rectangle {
        id: searchPanel
        objectName: "uos27HomeSearchPanel"
        visible: root.searchOpen
        anchors {
            top: parent.top
            topMargin: root.topInset + units.gu(2)
            left: parent.left
            right: parent.right
            leftMargin: units.gu(2.3)
            rightMargin: units.gu(2.3)
        }
        height: units.gu(5.5)
        radius: height / 2
        color: UOS.modalBackground
        border.width: 1
        border.color: UOS.border

        GlassIcon {
            name: "search"
            width: units.gu(2.6)
            height: width
            anchors { left: parent.left; leftMargin: units.gu(1.35); verticalCenter: parent.verticalCenter }
            color: UOS.ink
        }
        TextInput {
            id: searchInput
            objectName: "uos27HomeSearchInput"
            anchors {
                left: parent.left
                leftMargin: units.gu(5)
                right: dismissSearch.left
                rightMargin: units.gu(0.3)
                verticalCenter: parent.verticalCenter
            }
            font.pixelSize: units.gu(2.0)
            color: UOS.ink
            selectionColor: UOS.accent
            clip: true
            inputMethodHints: Qt.ImhNoPredictiveText
            Keys.onEscapePressed: root.closeSearch()
            onTextChanged: favorites.positionViewAtBeginning()
            onAccepted: {
                if (visibleApplications.count === 1) {
                    root.applicationSelected(visibleApplications.appId(0));
                }
            }
            Text {
                anchors.fill: parent
                text: Strings.tr("Search applications", root.language)
                color: UOS.secondaryInk
                font: parent.font
                visible: searchInput.text.length === 0
                verticalAlignment: Text.AlignVCenter
            }
        }
        GlassIcon {
            id: dismissSearch
            name: "close"
            width: units.gu(2.5)
            height: width
            anchors { right: parent.right; rightMargin: units.gu(1.4); verticalCenter: parent.verticalCenter }
            color: UOS.ink
            MouseArea { anchors.fill: parent; onClicked: root.closeSearch() }
        }
    }

    FocusScope {
        id: libraryButton
        objectName: "uos27HomeSearchTrigger"
        width: units.gu(12.5)
        height: units.gu(4.4)
        visible: !root.searchOpen
        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: dock.top
            bottomMargin: units.gu(1.5)
        }
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: Strings.tr("Search applications", root.language)
        Accessible.onPressAction: root.openSearch()
        Keys.onReturnPressed: root.openSearch()
        Keys.onSpacePressed: root.openSearch()
        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: UOS.tileBackground
            border.color: UOS.border
            border.width: 1
        }
        Row {
            anchors.centerIn: parent
            spacing: units.gu(0.75)
            GlassIcon {
                anchors.verticalCenter: parent.verticalCenter
                name: "search"
                width: units.gu(1.9)
                height: width
                color: UOS.ink
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: Strings.tr("Search", root.language)
                color: UOS.ink
                font.pixelSize: units.gu(1.55)
                font.weight: Font.DemiBold
            }
        }
        MouseArea { anchors.fill: parent; onClicked: root.openSearch() }
    }
}
