#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the actual integrated PanelMenu host in Qt 5 with controlled interfaces.

Copies the prepared source into a disposable fixture. PanelMenu, Showable,
MenuContent, GlassPane and GlassCenter are executed unchanged. The external
Lomiri theme, gesture recognizer, PanelBar and service backend are substituted;
this does not test the full shell, real gesture recognition or handset runtime.
"""


def main():
    import os,sys,shutil,tempfile,json,argparse
    from pathlib import Path
    os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_QUICK_BACKEND']='software'
    from PyQt5.QtCore import QObject,QUrl,QMetaObject,Q_ARG,QVariant,pyqtSlot,pyqtProperty,qInstallMessageHandler,QEasingCurve
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtQuick import QQuickView,QQuickItem
    from PyQt5.QtTest import QTest
    from PyQt5 import sip
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Prepared Lomiri root containing qml/')
    parser.add_argument('--report',type=Path,default=Path('out/lomiri-glass/integration-host-tests.json'))
    args=parser.parse_args()
    base=Path(tempfile.mkdtemp(prefix='lomiri-panel-smoke-'));source=args.source.resolve()/'qml'
    if not (source/'Panel/Glass/GlassPane.qml').is_file():
     raise SystemExit('Prepared source does not contain the integrated GlassPane.qml')
    (base/'qml/Panel/Indicators').mkdir(parents=True,exist_ok=True)
    messages=[]
    qInstallMessageHandler(lambda kind,context,message:messages.append(message))
    def write(p,s):
     p=base/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
    def copy(p):
     d=base/'qml'/p;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/p,d)
    for p in ['Components/Showable.qml','Panel/MenuContent.qml']:
     copy(Path(p))
    shutil.copytree(source/'Panel/Glass',base/'qml/Panel/Glass')
    write(Path('qml/Panel/Glass/NativeBackend.qml'),'import QtQuick 2.15\nItem {\n property string language:"en"\n property bool actionsAllowed:false\n signal actionError(string message)\n signal volumePolicyChanged()\n'+''.join(' property bool '+name+':false\n' for name in ['wifiAvailable','wifiEnabled','bluetoothAvailable','bluetoothEnabled','airplaneAvailable','airplaneEnabled','mobileDataAvailable','mobileDataEnabled','silentAvailable','silentEnabled','rotationAvailable','rotationLocked','brightnessAvailable','brightnessAutomatic','volumeAvailable'])+' property real brightnessValue:0.5\n property real volumeValue:0.4\n}')
    write(Path('qml/Components/StandardAnimation.qml'),'import QtQuick 2.15\nNumberAnimation {}')
    write(Path('qml/Components/BackgroundBlur.qml'),'import QtQuick 2.15\nItem {property var sourceItem:null;property rect blurRect;property bool occluding:false}')
    write(Path('qml/Components/Handle.qml'),'import QtQuick 2.15\nItem {property bool active:false}')
    write(Path('qml/Components/ScrollCalculator.qml'),'import QtQuick 2.15\nItem {property real forceScrollingPercentage;property real stopScrollThreshold;property int direction;property real lateralPosition;signal scroll(real scrollAmount)}')
    write(Path('qml/Components/DragHandle.qml'),'import QtQuick 2.15\nItem {property bool pressed:false;property bool dragging:false;property real distance:0;property int direction:0;property real autoCompleteDragThreshold:0;property bool stretch:false;property real overrideStartValue:0;property real maxTotalDragDistance:0;property real hintDisplacement:0;property point touchPosition:Qt.point(0,0)}')
    write(Path('qml/Panel/PanelVelocityCalculator.qml'),'import QtQuick 2.15\nItem {property real velocityThreshold:0;property real trackedValue:0;property bool velocityAboveThreshold:false;function reset(){}}')
    write(Path('imports/Lomiri/Components/qmldir'),'module Lomiri.Components\nStyledItem 1.3 StyledItem.qml\nThemeSettings 1.3 ThemeSettings.qml\nIcon 1.3 Icon.qml\n')
    write(Path('imports/Lomiri/Components/StyledItem.qml'),'import QtQuick 2.15\nItem {property QtObject theme:ThemeSettings{}}')
    write(Path('imports/Lomiri/Components/ThemeSettings.qml'),'import QtQuick 2.15\nQtObject {property string name:"Fixture";property QtObject palette:QtObject {property QtObject normal:QtObject {property color background:"#182838";property color backgroundText:"white"}}}')
    write(Path('imports/Lomiri/Components/Icon.qml'),'import QtQuick 2.15\nItem { property string source:""; property color color:"white" }')
    # Isolate the dedicated Wi-Fi Loader from unavailable host-only Lomiri
    # modules, while executing GlassWifiPage.qml itself without modification.
    write(Path('imports/QMenuModel/qmldir'),'module QMenuModel\nAyatanaMenuModel 1.0 AyatanaMenuModel.qml\n')
    write(Path('imports/QMenuModel/AyatanaMenuModel.qml'),'import QtQml 2.15\nQtObject { property string busName:""; property var actions:({}); property string menuObjectPath:"" }')
    write(Path('qml/Panel/PanelMenuPage.qml'),'import QtQuick 2.15\nItem {property var menuModel:null;property Component factory}')
    write(Path('qml/Panel/Indicators/IndicatorMenuItemFactory.qml'),'import QtQuick 2.15\nItem {property string indicator:"";property var rootModel:null}')
    for module in ['Lomiri/Indicators','Utils']:
     write(Path('imports')/module/'qmldir','module '+module.replace('/','.')+'\nUnused 0.1 Unused.qml\n')
     write(Path('imports')/module/'Unused.qml','import QtQuick 2.15\nQtObject {}')
    class Units(QObject):
     @pyqtSlot(float,result=float)
     def gu(self,v):return v*8
    class Animation(QObject):
     @pyqtProperty(int,constant=True)
     def BriskDuration(self):return 100
     @pyqtProperty(int,constant=True)
     def SnapDuration(self):return 0
     @pyqtProperty(QEasingCurve,constant=True)
     def StandardEasing(self):return QEasingCurve(QEasingCurve.OutCubic)
    app=QGuiApplication([]);units=Units();animation=Animation()
    write(Path('imports/Lomiri/Gestures/qmldir'),'module Lomiri.Gestures\nsingleton Direction 0.1 Direction.qml\n')
    write(Path('imports/Lomiri/Gestures/Direction.qml'),'pragma Singleton\nimport QtQuick 2.15\nQtObject {enum Directions { Upwards, Downwards } function isPositive(v){return v===1}}')
    bar='''import QtQuick 2.15
    Item {
     property var model:null;property var rowItemDelegate:null;property real overFlowWidth:width
     property int alignment:Qt.AlignRight;property bool hideRow:false;property bool expanded:false
     property bool finishedExpanding:true;property bool interactive:false;property bool enableLateralChanges:false
     property real lateralPosition:-1;property real unitProgress:0;property int currentItemIndex:0
     property int rowContentX:0;property int screenIndex:0;property int orientation:0
     function setCurrentItemIndex(i){currentItemIndex=i}
     function selectItemAt(i){currentItemIndex=0}
     function selectPreviousItem(){}
     function selectNextItem(){}
     function addScrollOffset(i){}
    }
    '''
    reports=[]
    for variant in ['WithoutCutouts','WithCutouts']:
     copy(Path('Panel')/variant/'LomiriPanel/PanelMenu.qml')
     write(Path('qml/Panel')/variant/'LomiriPanel/PanelBar.qml',bar)
     write(Path('Harness.qml'),'''import QtQuick 2.15
    import Lomiri.Components 1.3
    import "qml/Panel/'''+variant+'''/LomiriPanel" as Test
    Rectangle {
     width:412;height:915;color:"#123"
     property QtObject theme:ThemeSettings{}
     function removeMessages(){fixtureModel.remove(1)}
     function addMessages(){fixtureModel.append({identifier:"ayatana-indicator-messages"})}
     ListModel {id:fixtureModel;objectName:"fixtureModel";ListElement{identifier:"indicator-network"}ListElement{identifier:"ayatana-indicator-messages"}ListElement{identifier:"ayatana-indicator-sound"}}
     Test.PanelMenu {
     id:menu;objectName:"fixturePanel";width:parent.width;openedHeight:parent.height
     model:fixtureModel;glassEnabled:false;glassActionsAllowed:true
     pageDelegate:Item {objectName:"fixturePage-"+(modelData?modelData.identifier:"removed");function reset(){}}
     }
    }''')
     view=QQuickView();view.engine().addImportPath(str(base/'imports'));view.rootContext().setContextProperty('units',units);view.rootContext().setContextProperty('LomiriAnimation',animation)
     view.setSource(QUrl.fromLocalFile(str(base/'Harness.qml')))
     if view.status()==QQuickView.Error:raise RuntimeError([e.toString() for e in view.errors()])
     view.resize(412,915);view.show();QTest.qWait(100)
     root=view.rootObject();panel=root.findChild(QQuickItem,'fixturePanel');native=root.findChild(QQuickItem,'menuContent');original_parent=native.parentItem();original_model=native.property('model')
     assert not panel.property('glassActive')
     panel.setProperty('minimizedPanelHeight',43)
     panel.setProperty('glassNetworkIcons',['image://theme/nm-signal-75'])
     panel.setProperty('glassBluetoothIcons',['image://theme/bluetooth-active'])
     panel.setProperty('glassPowerIcons',['image://theme/battery-040'])
     panel.setProperty('glassPowerLabel','39%')
     panel.setProperty('glassEnabled',True);QTest.qWait(100)
     assert panel.property('glassActive'),messages
     clock=root.findChild(QQuickItem,'glassStatusClock')
     hardware=root.findChild(QQuickItem,'glassOrderedHardwareIndicators')
     battery=root.findChild(QQuickItem,'glassBatteryNearCamera')
     camera=root.findChild(QQuickItem,'glassCameraClearance')
     assert clock and hardware and battery and camera
     assert hardware.x() >= clock.x()+clock.width()-1
     assert hardware.x()+hardware.width() <= battery.x()+1
     assert battery.x()+battery.width() <= camera.x()+1
     assert camera.width() > 0 and battery.width() > 0
     pane=next(o for o in root.findChildren(QQuickItem) if o.property('requestedIndicator') is not None)
     host=pane.property('nativeContentHost')
     assert native.parentItem()==host
     center=next(o for o in root.findChildren(QQuickItem) if o.property('mode') is not None and o.property('nativePageAvailable') is not None)
     scrim=root.findChild(QQuickItem,'glassTranslucentScrim')
     assert scrim and center.property('mode')=='controls',messages
     assert abs(scrim.property('color').alphaF() - 0.66) < 0.015,'uOS27 Home wallpaper dimming not applied'
     panel.setProperty('glassAppInFront',True);QTest.qWait(250)
     assert pane.property('applicationBehind') and center.property('appBehind'),'App detection not propagated to glass'
     assert abs(scrim.property('color').alphaF() - 0.76) < 0.015,'uOS27 app-overlaid controls not dark enough'
     QMetaObject.invokeMethod(pane,'selectView',Q_ARG(QVariant,'notifications'));QTest.qWait(25)
     assert abs(scrim.property('color').alphaF() - 0.76) < 0.015,'uOS27 app-overlaid notifications not dark enough'
     panel.setProperty('glassAppInFront',False);QTest.qWait(250)
     assert abs(scrim.property('color').alphaF() - 0.66) < 0.015,'uOS27 Home notifications transparency not restored'
     QMetaObject.invokeMethod(pane,'selectView',Q_ARG(QVariant,'controls'))
     assert not center.property('appBehind')
     assert abs(scrim.property('color').alphaF() - 0.66) < 0.015,'uOS27 Home transparency not restored'
     QMetaObject.invokeMethod(panel,'chooseGlassView',Q_ARG(QVariant,70))
     QMetaObject.invokeMethod(panel,'showNow');QTest.qWait(150)
     assert pane.property('notificationView')
     assert panel.property('currentMenuIndex')==1
     assert pane.property('nativeVisible')
     assert native.isVisible()
     QMetaObject.invokeMethod(panel,'chooseGlassView',Q_ARG(QVariant,350))
     assert pane.property('notificationView'),'must not change selection mid-gesture'
     assert center.isEnabled()
     panel.setProperty('glassActionsAllowed',False);QTest.qWait(20)
     assert not center.isEnabled() and not native.isEnabled()
     panel.setProperty('glassActionsAllowed',True)
     QMetaObject.invokeMethod(pane,'openNativePage',Q_ARG(QVariant,'mobile'));QTest.qWait(40)
     mobile=root.findChild(QQuickItem,'glassMobileOnlyDetail')
     assert mobile and mobile.isVisible() and not pane.property('nativeVisible')
     assert not native.isVisible(),'Cellular details must not re-show the mixed Ethernet/network menu'
     QMetaObject.invokeMethod(pane,'openNativePage',Q_ARG(QVariant,'airplane'));QTest.qWait(25)
     assert mobile.isVisible() and not pane.property('nativeVisible')
     QMetaObject.invokeMethod(pane,'openNativePage',Q_ARG(QVariant,'wifi'));QTest.qWait(90)
     wifi=root.findChild(QQuickItem,'glassWifiOnlyDetail')
     networks=root.findChild(QQuickItem,'glassNativeWifiAccessPoints')
     assert wifi and networks and wifi.isVisible() and networks.isVisible(),messages
     assert not pane.property('nativeVisible') and not native.isVisible()
     assert any(o.property('menuObjectPath')=='/com/lomiri/indicator/network/phone_wifi_settings'
                for o in root.findChildren(QObject) if o.property('menuObjectPath') is not None)
     QMetaObject.invokeMethod(pane,'selectView',Q_ARG(QVariant,'notifications'));QTest.qWait(25)
     QMetaObject.invokeMethod(root,'removeMessages');QTest.qWait(80)
     assert not pane.property('nativeVisible') and not native.isVisible()
     QMetaObject.invokeMethod(root,'addMessages');QTest.qWait(80)
     assert pane.property('nativeVisible') and panel.property('currentMenuIndex')==2
     panel.setProperty('glassGestureChosen',False)
     QMetaObject.invokeMethod(panel,'chooseGlassView',Q_ARG(QVariant,350));QTest.qWait(20)
     assert not pane.property('notificationView') and not native.isVisible()
     panel.setProperty('glassEnabled',False);QTest.qWait(100)
     assert not sip.isdeleted(native),'Native MenuContent must survive loader unload'
     assert native.parentItem()==original_parent and native.property('model')==original_model
     assert not panel.property('glassActive') and panel.property('fullyClosed')
     problems=[s for s in messages if any(v in s for v in ['ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','Cannot anchor','is not a function'])]
     if problems:raise RuntimeError(problems)
     reports.append({'variant':variant,'result':'pass','checks':['fallback-to-native','native-object-survives-reparent-and-unload','ordered-live-status-icons','battery-before-camera-clearance','uos27-home-controls-alpha-0.66','uos27-app-controls-alpha-0.76','uos27-app-notifications-alpha-0.76','uos27-home-notifications-alpha-0.66','left-right-initial-choice','no-mid-gesture-switch','modal-disables-all-content','cellular-and-airplane-detail-isolated-from-ethernet','wifi-only-menu-loader-and-object-path','missing-indicator-hides-content','dynamic-model-reconnect','close-on-glass-disable']})
     view.close();view.deleteLater();QTest.qWait(30)
    report={'scope':'Actual patched PanelMenu, Showable, MenuContent, GlassPane and UI executed with Qt5; only external theme/gesture/PanelBar/backend interfaces stubbed','not_validated':['full shell','real gestures','live native notification widgets','handset'],'results':reports,'messages':messages,'source':str(source),'fixture':str(base)}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    print(json.dumps(report,indent=2));args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == "__main__":
    main()
