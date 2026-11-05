// SPDX-License-Identifier: GPL-3.0-only
// Numeric Greeter presentation: the SAME LightDM challenge is reparented
// onto the cover wallpaper in portrait mode. No second login screen,
// independent credential verifier, or Maliit on-screen keyboard is needed.
import QtQuick 2.15
import AccountsService 0.1
import Lomiri.Components 1.3
import "../../Components"
import "GlassTheme.js" as UOS

FocusScope {
    id: root
    objectName: "uos27NumericGreeterPrompt"
    focus: true

    property string text
    property bool isSecret: true
    property bool interactive: true
    property bool loginError: false
    property bool hasKeyboard: false
    property string enteredText: ""
    property int pincodeLength: AccountsService.pincodeLength
    property bool submitted: false

    signal clicked()
    signal canceled()
    signal accepted(string response)

    function clearEntry(withAnimation) {
        enteredText = "";
        submitted = false;
        pad.clear(withAnimation);
        pad.forceActiveFocus();
    }

    onLoginErrorChanged: {
        if (loginError)
            clearEntry(true);
    }
    onInteractiveChanged: {
        if (interactive && submitted)
            clearEntry(false);
    }

    PinLockscreen {
        id: pad
        objectName: "uos27NativePinPad"
        anchors.fill: parent
        focus: true

        infoText: root.text
        retryText: ""
        errorText: ""
        foregroundColor: UOS.ink
        showCancelButton: true
        roundGlassKeys: true
        minPinLength: root.pincodeLength > 0 ? root.pincodeLength : 1
        maxPinLength: root.pincodeLength > 0 ? root.pincodeLength : -1
        entryEnabled: root.interactive && !root.submitted

        onEntered: {
            if (root.interactive && !root.submitted && passphrase.length > 0) {
                root.enteredText = passphrase;
                root.submitted = true;
                root.accepted(passphrase);
            }
        }
        onCancel: root.canceled()
    }
}
