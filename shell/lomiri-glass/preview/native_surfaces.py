"""Fixture service boundaries for byte-identical native notification/spread QML."""
from pathlib import Path
import hashlib
import shutil


def add_surfaces(target: Path, source: Path, write, module):
    names = ["Notifications/Notification.qml", "Notifications/NotificationButton.qml",
             "Notifications/SwipeToAct.qml", "Notifications/OptionToggle.qml",
             "Stage/Spread/Spread.qml", "Stage/Spread/WorkspacePreview.qml",
             "Stage/Spread/MathUtils.js", "Stage/Spread/BezierCurve.qml",
             "Stage/Spread/cubic-bezier.js", "Stage/Spread/KeySpline.js"]
    identities = {}
    for name in names:
        dest = target / "qml" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "qml" / name, dest)
        identities[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    lomiri = target / "imports/Lomiri/Components"
    with (lomiri / "qmldir").open("a", encoding="utf-8") as out:
        out.write("ShapedIcon 1.3 ShapedIcon.qml\nProgressBar 1.3 ProgressBar.qml\n")
    write(lomiri / "StyledItem.qml", '''import QtQuick 2.15
Item { property QtObject theme: QtObject { property string name:"Fixture"; property QtObject palette: QtObject { property QtObject normal: QtObject {
 property color background:"#d92b3850"; property color backgroundSecondaryText:"white"; property color backgroundTertiaryText:"#d0d8e5"; property color negative:"red"; property color base:"white"
} } } }
''')
    write(lomiri / "LomiriShape.qml", '''import QtQuick 2.15
Item { id:shape; enum Aspect { Flat } property color backgroundColor:"transparent"; property string radius:"medium"; property int aspect: LomiriShape.Flat
 Rectangle { anchors.fill:parent; radius:shape.radius === "medium" ? 23 : 8; color:shape.backgroundColor }
}
''')
    write(lomiri / "ShapedIcon.qml", '''import QtQuick 2.15
Rectangle { property url fileSource; property bool shaped:true; color:"#50bc91"; radius:shaped ? width*.23 : 0
 Text {anchors.centerIn:parent; text:"✉"; color:"white"; font.pixelSize:parent.height*.55} }
''')
    write(lomiri / "ProgressBar.qml", 'import QtQuick 2.15\nItem {property real value; property real minimumValue; property real maximumValue; property bool showProgressPercentage}\n')
    module(target, "Lomiri.Components.ListItems", {"ThinDivider 1.3": 'import QtQuick 2.15\nRectangle {height:1;color:"#50ffffff"}'})
    module(target, "Lomiri.Components.Popups", {"Unused 1.3": 'import QtQuick 2.15\nQtObject {}'})
    # Plugin enums and empty remote action/menu models. No notification service,
    # audio player, power API, app closure or remote menu action is executed.
    module(target, "Lomiri.Notifications", {
        "Notification 1.0": '''import QtQuick 2.15
QtObject { enum Type { Confirmation, Ephemeral, Interactive, SnapDecision, PlaceHolder, Critical } }
''', "NotificationAudio 1.0": 'import QtQuick 2.15\nQtObject {property url source; function play(){}}',
        "ActionModel 1.0": 'import QtQuick 2.15\nQtObject {enum Role {RoleActionId}}'})
    module(target, "Powerd", {"singleton Powerd 0.1": '''pragma Singleton
import QtQuick 2.15
QtObject {enum State {On,Off} enum Reason {Notification,SnapDecision} function setStatus(state,reason){} }
'''})
    module(target, "QMenuModel", {"AyatanaMenuModel 1.0": '''import QtQuick 2.15
ListModel {property string busName;property var actions;property string menuObjectPath;property string nameOwner:""}
'''})
    module(target, "Utils", {"LomiriMenuModelPaths 0.1": '''import QtQuick 2.15
QtObject {property var source; property string busNameHint;property string actionsHint;property string menuObjectPathHint;property string busName:"";property var actions:({});property string menuObjectPath:""}
'''})
    write(target / "qml/Notifications/NotificationMenuItemFactory.qml", '''import QtQuick 2.15
Item {property var menuModel;property var menuData;property int menuIndex;property int maxHeight;property url background;property bool fullscreen:false;signal loaded();signal accepted()}
''')
    write(target / "imports/QtGraphicalEffects/qmldir", "module QtGraphicalEffects\nUnused 1.0 Unused.qml\nUnused 1.12 Unused.qml\nFastBlur 1.12 FastBlur.qml\n")
    write(target / "imports/QtGraphicalEffects/FastBlur.qml", '''import QtQuick 2.15
Item {property Item source;property bool transparentBorder;property real radius
 Rectangle {anchors.fill:parent;color:"#50bc91";radius:width*.23} }
''')
    write(target / "NotificationsHarness.qml", '''import QtQuick 2.15
import Lomiri.Notifications 1.0 as Enums
import "qml/Notifications" as Native
Rectangle { id:root; width:412;height:870; color:"#1b2b43"; property bool privateContent:false
 gradient: Gradient {GradientStop {position:0;color:"#75879f"} GradientStop {position:1;color:"#131d35"}}
 Text {x:25;y:90;text:"Centro notifiche";color:"white";font.pixelSize:32;font.weight:Font.DemiBold}
 ListView {id:notifications;objectName:"nativeNotificationList";x:10;y:170;width:parent.width-20;height:parent.height-y-40;spacing:12;model:2;interactive:false;currentIndex:-1;property bool topmostIsFullscreen:false
 delegate:Native.Notification {objectName:"nativeNotification"+index;width:notifications.width;height:implicitHeight;maxHeight:notifications.height;property int count:0
  glassStyle:true;privacyMode:root.privateContent;type:Enums.Notification.Ephemeral
  notification:QtObject {property int urgency:0;property bool fullscreen:false;function close(){} function invokeAction(id){} }
  actions:0;hints:({"suppress-sound":"true"});iconSource:"fixture-message";summary:index===0 ? "Messaggi · anteprima" : "Promemoria · anteprima"
  body:index===0 ? "Testo dimostrativo: nessun messaggio personale." : "Confrontare notifiche, privacy e gesti sul dispositivo."
 }
 }
 Text {anchors.bottom:parent.bottom;anchors.bottomMargin:18;anchors.horizontalCenter:parent.horizontalCenter;text:root.privateContent ? "CONTENUTO PRIVATO · MODELLO SINTETICO" : "CARD NATIVA · MODELLO SINTETICO";color:"#bdcbe0";font.pixelSize:10}
}
''')
    module(target, "QtMir.Application", {"Unused 0.1": 'import QtQuick 2.15\nQtObject {}'})
    module(target, "WindowManager", {
        "Mir 1.0": '''import QtQuick 2.15
QtObject {enum State {MaximizedState,FullscreenState,VertMaximizedState,HorizMaximizedState,MaximizedLeftState,MaximizedRightState,MaximizedTopLeftState,MaximizedTopRightState,MaximizedBottomLeftState,MaximizedBottomRightState,MinimizedState,HiddenState} }
''', "MirSurfaceItem 1.0": '''import QtQuick 2.15
Rectangle {property var surface; implicitWidth:360;implicitHeight:720; color:surface ? surface.fixtureColor : "#edf3f7"
 Text {x:25;y:55;text:parent.surface ? parent.surface.name : "";color:"#25384c";font.pixelSize:32;font.weight:Font.DemiBold}
 Column {x:25;y:125;width:parent.width-50;spacing:22;Repeater {model:5;Rectangle {width:parent.width;height:52;radius:12;color:"#b7ffffff"}}}
}
'''})
    write(target / "qml/Stage/WindowDecoration.qml", 'import QtQuick 2.15\nItem {property string title}\n')
    write(target / "imports/Fixture/qmldir", "module Fixture\n")
    write(target / "SpreadHarness.qml", '''import QtQuick 2.15
import Fixture 1.0
import "qml/Stage/Spread" as Native
Rectangle {id:root;width:412;height:870;color:"#203047";property int closeRequests:0;property int leaveRequests:0;property int snapIndex:-1
 gradient: Gradient {GradientStop {position:0;color:"#75879f"} GradientStop {position:1;color:"#131d35"}}
 QtObject {id:catalog;property int count:2;function surfaceAt(i){return {name:i===0?"Note · demo":"Calendario · demo"}} function applicationAt(i){return surfaceAt(i)}}
 QtObject {id:screenInfo;property point position:Qt.point(0,0)}
 QtObject {id:rail;function snap(i){root.snapIndex=i}}
 Native.Spread {id:spread;objectName:"nativeSpread";anchors.fill:parent;model:catalog;spreadFlickable:rail;highlightedIndex:0;focus:true
 onCloseCurrentApp:root.closeRequests++;onLeaveSpread:root.leaveRequests++
 Repeater {model:2
  Native.WorkspacePreview {objectName:"nativeWorkspace"+index;width:root.width*.72;height:width*2;x:root.width*.14+index*(width+22);y:spread.contentTopMargin+40
   screen:screenInfo;screenHeight:720;isSelected:index===spread.highlightedIndex
   workspace:QtObject {property var windowModel:FixtureWindowModel {fixtureName:index===0?"Note":"Calendario"}}
  }
 }
 }
 Text {anchors.bottom:parent.bottom;anchors.bottomMargin:24;anchors.horizontalCenter:parent.horizontalCenter;text:"SPREAD NATIVO · SUPERFICI APP SINTETICHE";color:"#bdcbe0";font.pixelSize:10}
}
''')
    return identities
