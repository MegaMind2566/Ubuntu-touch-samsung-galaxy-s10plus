// SPDX-License-Identifier: GPL-3.0-only
// Native indicator actions for Ubuntu Touch 24.04 / Qt 5.15.
// See ../../upstream-api-evidence.json for the inspected source revisions.
import QtQuick 2.15
import QMenuModel 1.0
import GSettings 1.0
import "GlassStrings.js" as Strings

Item {
    id: backend
    visible: false
    property string language: "en"

    // The host owns the shell/greeter/modal policy. Default closed, including
    // the interval between construction and the host assigning its binding.
    property bool actionsAllowed: false
    // Keep slider arguments typed as qreal across the QML -> QVariant boundary.
    // A raw JS Math.min/max result of 0 or 1 can otherwise be serialized as an
    // int32, which a native GAction with a double state silently rejects.
    property real _requestedFraction: 0
    property bool _bluetoothAwaitingState: false
    property bool _bluetoothTarget: false
    property bool _brightnessFirstRead: false
    property real _brightnessObserved: NaN
    signal actionError(string message)
    signal volumePolicyChanged()

    readonly property bool wifiAvailable: actionAvailable(wifiAction, "boolean")
    readonly property bool wifiEnabled: booleanState(wifiAction)
    // The stock Lomiri Settings Bluetooth switch uses QDBusActionGroup.
    // Prefer that same native client for both the initial value and the
    // request; preserve the existing Ayatana observer as a guarded fallback.
    readonly property bool bluetoothDirectReady: bluetoothDirect.actionObject !== null
                                                && bluetoothDirect.actionObject !== undefined
                                                && typeof bluetoothDirect.actionObject.state === "boolean"
    // The time-bounded uOS27 bridge exports BlueZ Adapter1.Powered (not an
    // rfkill-only guess). If it is absent, preserve Ayatana's stock path.
    readonly property bool bluezBridgeReady: String(bluezBridgeModel.nameOwner) !== ""
                                              && bluezBridge.actionObject !== null
                                              && bluezBridge.actionObject !== undefined
                                              && typeof bluezBridge.actionObject.state === "boolean"
    readonly property bool bluetoothAvailable: bluezBridgeReady
                                               ? booleanState(bluetoothSupportedAction)
                                               : actionAvailable(bluetoothAction, "boolean")
                                                 && booleanState(bluetoothSupportedAction)
    readonly property bool bluetoothEnabled: bluezBridgeReady
                                              ? bluezBridge.actionObject.state
                                              : bluetoothDirectReady
                                                ? bluetoothDirect.actionObject.state
                                                : booleanState(bluetoothAction)
    onBluetoothEnabledChanged: {
        if (_bluetoothAwaitingState && bluetoothEnabled === _bluetoothTarget) {
            _bluetoothAwaitingState = false;
            bluetoothResponse.stop();
        }
    }
    onActionsAllowedChanged: {
        if (!actionsAllowed) {
            _bluetoothAwaitingState = false;
            bluetoothResponse.stop();
        } else {
            // QDBusActionGroup may connect after the panel is constructed.
            // Sample the service as soon as the user opens the controls.
            syncBrightness();
        }
    }
    readonly property bool airplaneAvailable: actionAvailable(airplaneAction, "boolean")
    readonly property bool airplaneEnabled: booleanState(airplaneAction)
    readonly property bool mobileDataAvailable: actionAvailable(mobileDataAction, "boolean")
    readonly property bool mobileDataEnabled: booleanState(mobileDataAction)
    readonly property bool silentAvailable: actionAvailable(silentAction, "boolean")
    readonly property bool silentEnabled: booleanState(silentAction)
    readonly property bool rotationAvailable: actionAvailable(rotationAction, "boolean")
    readonly property bool rotationLocked: booleanState(rotationAction)

    readonly property bool automaticBrightnessKnown: typeof systemSettings.autoBrightness === "boolean"
    readonly property bool brightnessAutomatic: automaticBrightnessKnown && systemSettings.autoBrightness
    // Read-only repowerd capability, distinct from the saved preference and
    // from physical acceptance. A stale QStateAction must lose authority when
    // its bridge owner disappears. These state-only actions are disabled by
    // design; action.enabled is deliberately not a support indication.
    readonly property bool automaticBrightnessSupportKnown: String(bluezBridgeModel.nameOwner) !== ""
            && autoBrightnessBridge.knownActionObject !== null
            && autoBrightnessBridge.knownActionObject !== undefined
            && typeof autoBrightnessBridge.knownActionObject.state === "boolean"
            && autoBrightnessBridge.knownActionObject.state === true
            && autoBrightnessBridge.supportedActionObject !== null
            && autoBrightnessBridge.supportedActionObject !== undefined
            && typeof autoBrightnessBridge.supportedActionObject.state === "boolean"
    readonly property bool automaticBrightnessSupported: automaticBrightnessSupportKnown
            && autoBrightnessBridge.supportedActionObject.state === true
    // Acceptance metadata only. Availability follows the live native service;
    // publishing a source profile or a saved preference does not set this flag.
    property bool automaticBrightnessProfileVerified: false
    property bool ambientLuxAvailable: false
    property real ambientLuxValue: NaN
    readonly property bool automaticBrightnessAvailable: automaticBrightnessKnown
            && automaticBrightnessSupportKnown && automaticBrightnessSupported
    readonly property string automaticBrightnessCapability: !automaticBrightnessKnown
            || !automaticBrightnessSupportKnown ? "unknown"
            : !automaticBrightnessSupported ? "unsupported"
            : !automaticBrightnessProfileVerified ? "supported-unverified" : "ready"
    readonly property var capabilities: ({
        wifi: { available: wifiAvailable, state: wifiEnabled, source: "Ubuntu indicator" },
        bluetooth: { available: bluetoothAvailable, state: bluetoothEnabled,
                     source: bluezBridgeReady ? "BlueZ readback bridge" : "Ayatana" },
        mobileData: { available: mobileDataAvailable, state: mobileDataEnabled },
        brightness: { available: brightnessAvailable, known: brightnessStateKnown,
                      value: brightnessValue, source: "Ayatana power GAction" },
        automaticBrightness: { available: automaticBrightnessAvailable,
             known: automaticBrightnessSupportKnown, supported: automaticBrightnessSupported,
             state: brightnessAutomatic, status: automaticBrightnessCapability,
             physicallyVerified: automaticBrightnessProfileVerified,
             source: "repowerd getBrightnessParams via read-only GAction bridge" },
        ambientLight: { available: ambientLuxAvailable, lux: ambientLuxAvailable ? ambientLuxValue : null },
        volume: { available: volumeAvailable, value: volumeValue }
    })
    function setAutomaticBrightness(enabled) {
        if (!canRequest(automaticBrightnessAvailable, "Luminosità automatica")) return;
        if (typeof enabled !== "boolean") return;
        // GSettings notifies readback; never assign brightnessAutomatic locally.
        systemSettings.autoBrightness = enabled;
    }
    readonly property bool brightnessStateKnown: String(powerModel.nameOwner) !== ""
        && (_brightnessFirstRead || brightnessDirectReady || actionHasState(brightnessAction, "number"))
    // Stock System Settings starts a QDBusActionGroup to retrieve brightness
    // on first construction. Mirror that reader instead of waiting for the
    // visual indicator's first state-change event (the 0.9.1 phone symptom).
    readonly property bool brightnessDirectReady: String(powerModel.nameOwner) !== ""
                                                 && typeof powerDirect.brightnessState === "number"
                                                 && isFinite(powerDirect.brightnessState)
    readonly property bool brightnessAvailable: brightnessStateKnown && automaticBrightnessKnown && !brightnessAutomatic
                                                && (brightnessDirectReady || actionAvailable(brightnessAction, "number"))
    readonly property real brightnessValue: _brightnessFirstRead
                                            ? Math.max(0, Math.min(1, _brightnessObserved))
                                            : brightnessDirectReady
                                              ? Math.max(0, Math.min(1, powerDirect.brightnessState))
                                              : numericState(brightnessAction)
    readonly property bool volumeAvailable: actionAvailable(volumeAction, "number")
    readonly property real volumeValue: numericState(volumeAction)

    // Ayatana emits volume-sync even when it has rejected/reset an identical
    // requested value. A host slider can cancel its local drag value on this
    // signal and read volumeValue again; it must never replay the rejected value.
    readonly property var volumeSyncToken: actionHasState(volumeSyncAction, "number")
                                           ? volumeSyncAction.state : undefined
    readonly property bool highVolumeWarning: booleanState(highVolumeAction)
    onVolumeSyncTokenChanged: volumePolicyChanged()

    function actionHasState(action, stateType) {
        return !!action && !!action.model && String(action.model.nameOwner) !== ""
                && action.valid && typeof action.state === stateType
                && (stateType !== "number" || isFinite(action.state));
    }

    function actionAvailable(action, stateType) {
        return actionHasState(action, stateType) && action.enabled;
    }

    function booleanState(action) {
        return actionHasState(action, "boolean") && action.state === true;
    }

    function numericState(action) {
        return actionHasState(action, "number") ? Math.max(0, Math.min(1, action.state)) : 0;
    }

    function canRequest(available, label) {
        // Closing the panel, locking, or opening a native modal can invalidate
        // a queued UI request. Discard it without creating another notification.
        if (!actionsAllowed)
            return false;
        if (!available) {
            actionError(label + ": " + Strings.tr("Control temporarily unavailable.", language));
            return false;
        }
        return true;
    }

    // These methods submit requests, not acknowledgements. State always comes
    // back from the service. In particular, do not assign any *Enabled property.
    function toggleWifi() {
        if (canRequest(wifiAvailable, Strings.tr("Wi-Fi", language)))
            wifiAction.activate();
    }

    function toggleBluetooth() {
        if (!canRequest(bluetoothAvailable, Strings.tr("Bluetooth", language)))
            return;
        // Ayatana's native action accepts a Boolean activation parameter.
        // Never pretend success: if the service or hardware declines it, the
        // user must see a diagnosis instead of a visually stuck switch.
        _bluetoothTarget = !bluetoothEnabled;
        _bluetoothAwaitingState = true;
        if (bluezBridgeReady)
            bluezBridge.actionObject.activate(_bluetoothTarget);
        else if (bluetoothDirectReady)
            bluetoothDirect.actionObject.activate(_bluetoothTarget);
        else
            bluetoothAction.activate(_bluetoothTarget);
        bluetoothResponse.restart();
    }

    Timer {
        id: bluetoothResponse
        interval: 3200
        repeat: false
        onTriggered: {
            if (backend._bluetoothAwaitingState && backend.actionsAllowed
                    && backend.bluetoothEnabled !== backend._bluetoothTarget) {
                backend.actionError(Strings.tr("Bluetooth did not change. Open its system settings.", backend.language));
            }
            backend._bluetoothAwaitingState = false;
        }
    }

    function toggleAirplane() {
        if (canRequest(airplaneAvailable, Strings.tr("Airplane mode", language)))
            airplaneAction.activate();
    }

    function toggleMobileData() {
        if (canRequest(mobileDataAvailable, Strings.tr("Mobile data", language)))
            mobileDataAction.activate();
    }

    function toggleSilent() {
        if (canRequest(silentAvailable, Strings.tr("Silent", language)))
            silentAction.activate(!silentEnabled);
    }

    function toggleRotation() {
        if (canRequest(rotationAvailable, Strings.tr("Rotation lock", language)))
            rotationAction.activate(!rotationLocked);
    }

    function requestNumber(action, value, available, label) {
        if (!canRequest(available, label))
            return;
        if (typeof value !== "number" || !isFinite(value)) {
            actionError(Strings.tr("Invalid requested value.", language));
            return;
        }
        _requestedFraction = Math.max(0, Math.min(1, value));
        action.changeState(_requestedFraction);
    }

    function setBrightness(value) {
        // Never change auto-brightness as a side effect of dragging the slider.
        // Stock Components/BrightnessControl.qml drives the power service's
        // QStateAction.updateState(real), not a synthetic visual value.
        if (brightnessDirectReady) {
            if (!canRequest(brightnessAvailable, Strings.tr("Manual brightness", language)))
                return;
            if (typeof value !== "number" || !isFinite(value)) {
                actionError(Strings.tr("Invalid requested value.", language));
                return;
            }
            _requestedFraction = Math.max(0, Math.min(1, value));
            powerDirect.brightnessActionObject.updateState(_requestedFraction);
        } else {
            requestNumber(brightnessAction, value, brightnessAvailable,
                          Strings.tr("Manual brightness", language));
        }
    }

    function syncBrightness() {
        // An explicit read after the action group starts addresses Qt's
        // late-initialisation race. A real hardware calibration is still
        // needed if the indicator itself publishes a stale brightness.
        var action = powerDirect.action("brightness");
        var reading = action && action.state;
        if (typeof reading === "number" && isFinite(reading)) {
            _brightnessObserved = Math.max(0, Math.min(1, reading));
            _brightnessFirstRead = true;
        } else if (actionAvailable(brightnessAction, "number")) {
            _brightnessObserved = numericState(brightnessAction);
            _brightnessFirstRead = true;
        }
    }

    Timer {
        id: brightnessRefresh
        interval: 500
        repeat: true
        running: backend.actionsAllowed
        onTriggered: backend.syncBrightness()
    }
    onBrightnessDirectReadyChanged: Qt.callLater(backend.syncBrightness)

    function setVolume(value) {
        // Use the indicator action, exactly as the stock menu does. Its native
        // high-volume notification, clamping and confirmation remain in charge.
        requestNumber(volumeAction, value, volumeAvailable, Strings.tr("Volume", language));
    }

    GSettings {
        id: systemSettings
        schema.id: "com.lomiri.touch.system"
    }

    // AyatanaMenuAction exposes enabled as well as valid/state. QStateAction
    // returned by QDBusActionGroup.action() does NOT expose enabled; using that
    // API here would lose the indicator's temporary disable / hardware gates.
    // Index -1 names an action directly, outside any section action namespace.
    // Assign names after model registration so the observer subscribes even if
    // a service already owns its bus name when this component is constructed.
    AyatanaMenuModel {
        id: networkModel
        busName: "com.lomiri.indicator.network"
        actions: ({ "indicator": "/com/lomiri/indicator/network" })
        menuObjectPath: "/com/lomiri/indicator/network/phone"
    }
    AyatanaMenuAction {
        id: wifiAction
        model: networkModel
        index: -1
        Component.onCompleted: name = "indicator.wifi.enable"
    }
    AyatanaMenuAction {
        id: airplaneAction
        model: networkModel
        index: -1
        Component.onCompleted: name = "indicator.airplane.enabled"
    }
    AyatanaMenuAction {
        id: mobileDataAction
        model: networkModel
        index: -1
        Component.onCompleted: name = "indicator.mobiledata.enabled"
    }

    AyatanaMenuModel {
        id: bluetoothModel
        busName: "org.ayatana.indicator.bluetooth"
        actions: ({ "indicator": "/org/ayatana/indicator/bluetooth" })
        menuObjectPath: "/org/ayatana/indicator/bluetooth/phone"
    }
    QDBusActionGroup {
        id: bluetoothDirect
        busType: DBus.SessionBus
        busName: "org.ayatana.indicator.bluetooth"
        objectPath: "/org/ayatana/indicator/bluetooth"
        property var actionObject: action("bluetooth-enabled")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: bluezBridge
        busType: DBus.SessionBus
        busName: "org.uos27.Control"
        objectPath: "/org/uos27/Control"
        property var actionObject: action("bluetooth-enabled")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: autoBrightnessBridge
        objectName: "automaticBrightnessCapabilityReader"
        busType: DBus.SessionBus
        busName: "org.uos27.Control"
        objectPath: "/org/uos27/Control"
        property var knownActionObject: action("auto-brightness-known")
        property var supportedActionObject: action("auto-brightness-supported")
        Component.onCompleted: start()
    }
    // A QStateAction can retain its last state after the bus name vanishes.
    // Observe the owner independently, so the temporary trial service never
    // leaves a stale icon or blocks the stock fallback when its TTL expires.
    AyatanaMenuModel {
        id: bluezBridgeModel
        busName: "org.uos27.Control"
        actions: ({ "bridge": "/org/uos27/Control" })
        menuObjectPath: "/org/uos27/Control/phone"
    }
    AyatanaMenuAction {
        id: bluetoothAction
        model: bluetoothModel
        index: -1
        Component.onCompleted: name = "indicator.bluetooth-enabled"
    }
    AyatanaMenuAction {
        id: bluetoothSupportedAction
        model: bluetoothModel
        index: -1
        Component.onCompleted: name = "indicator.bluetooth-supported"
    }

    AyatanaMenuModel {
        id: powerModel
        busName: "org.ayatana.indicator.power"
        actions: ({ "indicator": "/org/ayatana/indicator/power" })
        menuObjectPath: "/org/ayatana/indicator/power/phone"
    }
    QDBusActionGroup {
        id: powerDirect
        busType: DBus.SessionBus
        busName: "org.ayatana.indicator.power"
        objectPath: "/org/ayatana/indicator/power"
        property var brightnessActionObject: action("brightness")
        property var brightnessState: brightnessActionObject ? brightnessActionObject.state : undefined
        Component.onCompleted: {
            start();
            Qt.callLater(backend.syncBrightness);
        }
    }
    AyatanaMenuAction {
        id: brightnessAction
        model: powerModel
        index: -1
        Component.onCompleted: name = "indicator.brightness"
    }

    AyatanaMenuModel {
        id: soundModel
        busName: "org.ayatana.indicator.sound"
        actions: ({ "indicator": "/org/ayatana/indicator/sound" })
        menuObjectPath: "/org/ayatana/indicator/sound/phone"
    }
    AyatanaMenuAction {
        id: volumeAction
        model: soundModel
        index: -1
        Component.onCompleted: name = "indicator.volume"
    }
    AyatanaMenuAction {
        id: silentAction
        model: soundModel
        index: -1
        Component.onCompleted: name = "indicator.silent-mode"
    }
    AyatanaMenuAction {
        id: volumeSyncAction
        model: soundModel
        index: -1
        Component.onCompleted: name = "indicator.volume-sync"
    }
    AyatanaMenuAction {
        id: highVolumeAction
        model: soundModel
        index: -1
        Component.onCompleted: name = "indicator.high-volume"
    }

    AyatanaMenuModel {
        id: displayModel
        busName: "org.ayatana.indicator.display"
        actions: ({ "indicator": "/org/ayatana/indicator/display" })
        menuObjectPath: "/org/ayatana/indicator/display/phone"
    }
    AyatanaMenuAction {
        id: rotationAction
        model: displayModel
        index: -1
        Component.onCompleted: name = "indicator.rotation-lock"
    }
}
