#!/usr/bin/env python3
"""Exercise uOS27 GlassHome in real Qt5 with distinct simulated native models.

The pinned launcher model deliberately omits installed apps. The simulated
AppDrawerModel and AppDrawerProxyModel prove these still appear on Home and
remain searchable after dynamic installation. No compositor/GPU claims.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PyQt5.QtCore import (QAbstractListModel, QSortFilterProxyModel, QObject, QModelIndex,
                          QPointF, Qt, QUrl, QVariant, pyqtSlot, pyqtProperty,
                          pyqtSignal, qInstallMessageHandler)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import qmlRegisterType
from PyQt5.QtQuick import QQuickItem, QQuickView
from PyQt5.QtTest import QTest


class MockApplications(QAbstractListModel):
    IDENTIFIER, NAME, ICON = (Qt.UserRole + i for i in range(1, 4))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.apps = [("dialer", "Phone", ""), ("messaging", "Messages", ""),
                     ("browser", "Browser", ""), ("camera", "Camera", ""),
                     ("gallery", "Gallery", ""), ("settings", "Settings", "")]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.apps)

    def roleNames(self):
        return {self.IDENTIFIER: b"appId", self.NAME: b"name", self.ICON: b"icon"}

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.apps):
            return None
        return dict(zip((self.IDENTIFIER, self.NAME, self.ICON), self.apps[index.row()])).get(role)

    @pyqtSlot(int, result=QVariant)
    def get(self, index):
        if not 0 <= index < len(self.apps):
            return {}
        app_id, label, icon = self.apps[index]
        return {"appId": app_id, "name": label, "icon": icon}


class MockAppDrawerModel(MockApplications):
    instances = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.apps.extend((("notes", "Notes", ""), ("calendar", "Calendar", ""),
                          ("file-manager", "Files", "")))
        self.instances.append(self)

    @pyqtSlot()
    def refresh(self):
        self.beginResetModel()
        self.endResetModel()


class MockAppDrawerProxyModel(QSortFilterProxyModel):
    sourceChanged = pyqtSignal()
    filterStringChanged = pyqtSignal()
    sortByChanged = pyqtSignal()
    countChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filterString = ""
        self._sortBy = 0
        self.setDynamicSortFilter(True)
        self.setSortRole(MockApplications.NAME)
        self.modelReset.connect(self.countChanged)
        self.rowsInserted.connect(self.countChanged)
        self.rowsRemoved.connect(self.countChanged)

    @pyqtProperty(QObject, notify=sourceChanged)
    def source(self):
        return self.sourceModel()

    @source.setter
    def source(self, new_source):
        self.setSourceModel(new_source)
        self.sort(0, Qt.AscendingOrder)
        self.sourceChanged.emit()
        self.countChanged.emit()

    @pyqtProperty(str, notify=filterStringChanged)
    def filterString(self):
        return self._filterString

    @filterString.setter
    def filterString(self, value):
        self._filterString = value
        self.invalidateFilter()
        self.filterStringChanged.emit()
        self.countChanged.emit()

    @pyqtProperty(int, notify=sortByChanged)
    def sortBy(self):
        return self._sortBy

    @sortBy.setter
    def sortBy(self, value):
        self._sortBy = value
        self.sortByChanged.emit()

    @pyqtProperty(int, notify=countChanged)
    def count(self):
        return self.rowCount()

    @pyqtSlot(int, result=str)
    def appId(self, row):
        if row < 0 or row >= self.rowCount():
            return ""
        return self.data(self.index(row, 0), MockApplications.IDENTIFIER)

    def filterAcceptsRow(self, row, parent):
        source = self.sourceModel()
        if source is None:
            return False
        name = str(source.data(source.index(row, 0, parent), MockApplications.NAME) or "")
        return self._filterString.casefold() in name.casefold()


class I18n(QObject):
    languageChanged = pyqtSignal()


class Units(QObject):
    @pyqtSlot(float, result=float)
    def gu(self, number):
        return number * 8


def scene_item(root: QQuickItem, name: str):
    if root.objectName() == name:
        return root
    for child in root.childItems():
        found = scene_item(child, name)
        if found is not None:
            return found
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--progress", action="store_true", help="Flush fixture stage markers for native crash diagnosis")
    args = parser.parse_args()
    def progress(stage):
        if args.progress:
            print(json.dumps({"home_fixture_stage":stage}), flush=True)
    progress("starting")
    source = args.source / "qml/Panel/Glass"
    if not (source / "GlassHome.qml").is_file():
        raise SystemExit("Home module is missing from the prepared tree")
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    app = QGuiApplication([])
    progress("application-created")
    qmlRegisterType(MockAppDrawerModel, "Lomiri.Launcher", 0, 1, "AppDrawerModel")
    qmlRegisterType(MockAppDrawerProxyModel, "Utils", 0, 1, "AppDrawerProxyModel")
    pinned = MockApplications()
    units = Units()
    with tempfile.TemporaryDirectory(prefix="uos27-home-fixture-") as temporary:
        directory = Path(temporary)
        fixture = directory / "qml/Glass"
        fixture.mkdir(parents=True)
        for name in ("GlassHome.qml", "GlassTheme.js", "GlassStrings.js", "GlassIcon.qml"):
            shutil.copy2(source / name, fixture / name)
        imports = directory / "imports"
        lomiri = imports / "Lomiri/Components"
        lomiri.mkdir(parents=True)
        (lomiri / "qmldir").write_text("module Lomiri.Components\nLomiriShape 1.3 LomiriShape.qml\n")
        (lomiri / "LomiriShape.qml").write_text('''import QtQuick 2.15
Item {
  enum Aspect { Flat }
  enum FillMode { PreserveAspectCrop }
  property string radius: "medium"
  property int aspect: LomiriShape.Flat
  property Item source
  property int sourceFillMode
}
''')
        launcher = imports / "Lomiri/Launcher"
        launcher.mkdir(parents=True)
        (launcher / "qmldir").write_text("module Lomiri.Launcher\n")
        view = QQuickView()
        view.setResizeMode(QQuickView.SizeRootObjectToView)
        view.engine().addImportPath(str(imports))
        view.rootContext().setContextProperty("units", units)
        view.rootContext().setContextProperty("LauncherModel", pinned)
        view.rootContext().setContextProperty("i18n", I18n(view))
        view.setSource(QUrl.fromLocalFile(str(fixture / "GlassHome.qml")))
        progress("qml-loaded")
        if view.status() != QQuickView.Ready:
            raise AssertionError([str(x.toString()) for x in view.errors()])
        root = view.rootObject()
        root.applicationSelected.connect(lambda value: launched.append(value))
        launched = []
        checks = []
        view.show()
        for width, height in ((360, 780), (412, 915), (780, 360)):
            view.resize(width, height)
            QTest.qWait(80)
            assert abs(root.width() - width) <= 1
            assert abs(root.height() - height) <= 1
            dock = root.findChild(QObject, "uos27HomeDock")
            grid = root.findChild(QObject, "uos27HomeGrid")
            search = root.findChild(QObject, "uos27HomeSearchTrigger")
            assert dock and grid and search
            assert 0 <= dock.property("y") <= height
            assert grid.property("y") >= 0
            assert dock.property("x") >= 0 and dock.property("width") <= width
            checks.append(f"native Qt5 Home layout loads at {width}x{height}")
            progress(f"layout-{width}x{height}")
        view.resize(412, 915)
        QTest.qWait(100)
        browser = scene_item(root, "uos27HomeApp_browser")
        calendar = scene_item(root, "uos27HomeApp_calendar")
        camera = scene_item(root, "uos27HomeApp_camera")
        messages_item = scene_item(root, "uos27HomeApp_messaging")
        assert browser and calendar and camera and messages_item
        assert abs(browser.y() - calendar.y()) < 1 and abs(calendar.y() - camera.y()) < 1
        assert browser.x() < calendar.x() < camera.x()
        assert messages_item.y() > browser.y()
        checks.append("Portrait catalog fills four columns in row order instead of down columns")
        progress("portrait-row-order")
        first = scene_item(root, "uos27HomeApp_file-manager")
        assert first, ("An UNPINNED installed app is absent from Home", messages,
                       grid.property("count"))
        center = first.mapToScene(QPointF(first.width()/2, first.height()/2)).toPoint()
        QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, center)
        QTest.qWait(20)
        assert launched == ["file-manager"], launched
        checks.append("Unpinned installed icon launches via native app id")
        progress("native-launch-request")
        search = root.findChild(QObject, "uos27HomeSearchTrigger")
        center = search.mapToScene(QPointF(search.width()/2, search.height()/2)).toPoint()
        QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, center)
        QTest.qWait(30)
        assert root.property("searchOpen"), messages
        search_input = root.findChild(QObject, "uos27HomeSearchInput")
        search_input.setProperty("text", "files")
        QTest.qWait(40)
        assert grid.property("count") == 1, (grid.property("count"), messages)
        root.closeSearch()
        QTest.qWait(20)
        checks.append("Integrated Home search filters installed apps without opening Drawer")
        progress("search-filtered")

        catalog = MockAppDrawerModel.instances[-1]
        catalog.beginResetModel()
        catalog.apps.extend(("test-app-" + str(n), "App " + str(n), "") for n in range(48))
        catalog.endResetModel()
        progress("catalog-reset")
        QTest.qWait(90)
        assert grid.property("pageCount") > 1, (grid.property("pageCount"), messages)
        pagination = root.findChild(QObject, "uos27HomePagination")
        assert pagination and pagination.property("visible")
        grid.setProperty("contentX", grid.property("width"))
        QTest.qWait(50)
        assert grid.property("currentPage") >= 1, grid.property("currentPage")
        checks.append("Newly installed apps appear on multiple Home pages with native pagination")
        progress("native-pagination")
        previous_page = grid.property("currentPage")
        root.setProperty("visible", False)
        QTest.qWait(20)
        root.setProperty("visible", True)
        QTest.qWait(20)
        assert grid.property("currentPage") == previous_page, "Home page reset on app close"
        checks.append("Returning from an app retains the previous Home page")
        root.setProperty("wallpaperCoverVisible", True)
        QTest.qWait(20)
        backing = root.findChild(QObject, "uos27HomePrivacyBacking")
        assert backing and backing.property("visible"), "Live app content visible before wallpaper load"
        checks.append("An opaque backing hides running app content while Home wallpaper loads")
        assert len(pinned.apps) == 6
        assert grid.property("count") > len(pinned.apps)
        checks.append("Dock model remains distinct from complete installed-app Home model")
        progress("all-model-checks-complete")
        problems = [m for m in messages if any(needle in m for needle in (
            "ReferenceError", "TypeError", "Binding loop", "Cannot assign",
            "Cannot anchor", "is not a type", "is not a function"))]
        assert not problems, problems
        report = {"result": "pass", "scope": "Qt5 Home with separate pinned and installed QAbstractItemModels",
                  "checks": checks, "not_validated": ["handset", "native launch success",
                  "GPU", "real app-store install notifications"], "warnings": messages}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        progress("report-written")
        root.setProperty("wallpaperCoverVisible", False)
        QTest.qWait(75)
        view.close()
        progress("view-closed")
    progress("fixture-files-cleaned")


if __name__ == "__main__":
    main()
