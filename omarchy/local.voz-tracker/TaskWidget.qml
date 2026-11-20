import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "local.voz-tracker"
  implicitWidth: icon.implicitWidth
  implicitHeight: icon.implicitHeight

  property var task: ({})
  property bool hidden: false
  property bool pinned: false
  property bool expired: false
  readonly property bool working: task.state === "working" || task.state === "cancelling"
  readonly property bool dockToLeft: task.corner === "top-left"
  readonly property bool canFollow: /^[0-9a-fA-F-]{36}$/.test(task.thread_id || "")
  readonly property string executable: Quickshell.env("HOME") + "/Work/voz-codex/voz-codex"
  // Keep the target monitor independent from PanelWindow.screen to avoid a
  // visible/screen binding loop while Quickshell reloads local plugins.
  readonly property var monitor: Quickshell.screens[0]

  function toggleCard() {
    if (pinned || !hidden) {
      hidden = true
      pinned = false
    } else {
      hidden = false
      pinned = true
    }
  }

  function runAction(action) {
    if (actionProc.running || !/^[a-f0-9]{32}$/.test(task.id || "")) return
    actionProc.command = action === "cancel"
      ? [executable, "cancel", "--task-id", task.id]
      : [executable, "follow", task.id]
    actionProc.running = true
  }

  Process { id: actionProc }
  ShellIpc {
    target: "local.voz-tracker"
    function toggle(): void { root.toggleCard() }
  }

  FileView {
    path: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/voz-codex/task.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        const content = text()
        if (content.length > 4096) return
        const next = JSON.parse(content)
        const changed = next.state !== root.task.state || next.id !== root.task.id
        root.task = next
        if (changed) {
          root.expired = false
          expiry.stop()
          if (next.state === "done" || next.state === "error" || next.state === "cancelled") expiry.start()
        }
      } catch (error) {
        root.task = ({})
      }
    }
    onLoadFailed: root.task = ({})
  }

  Timer { id: expiry; interval: 8500; onTriggered: root.expired = true }

  BarIconButton {
    id: icon
    anchors.fill: parent
    bar: root.bar
    text: root.working ? "\uf110" : "\uf120"
    slotSize: Style.bar.statusSlot
    tooltipText: "Seguimiento de Voz Codex"
    onPressed: root.toggleCard()
  }

  PanelWindow {
    id: card
    screen: root.monitor
    visible: !root.hidden && (root.pinned || root.working ||
      (!root.expired && ["done", "cancelled", "error"].includes(root.task.state)))
    anchors.top: true
    anchors.left: root.dockToLeft
    anchors.right: !root.dockToLeft
    margins.top: 8
    margins.left: root.dockToLeft ? 10 : 0
    margins.right: root.dockToLeft ? 0 : 10
    implicitWidth: 310
    implicitHeight: layout.implicitHeight + 26
    exclusionMode: ExclusionMode.Normal
    exclusiveZone: 0
    WlrLayershell.namespace: "voz-codex-tracker"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: grab.containsMouse ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    color: "transparent"

    Rectangle {
      anchors.fill: parent
      radius: 10
      color: Color.background
      border.color: root.working ? Color.accent : Color.muted
    }

    Rectangle {
      id: closeButton
      z: 3
      visible: grab.containsMouse
      anchors.top: parent.top
      anchors.right: parent.right
      anchors.topMargin: 6
      anchors.rightMargin: 6
      width: 24
      height: 24
      radius: 12
      color: closeArea.containsMouse ? Color.urgent : "transparent"

      Text {
        anchors.centerIn: parent
        textFormat: Text.PlainText
        text: "×"
        color: closeArea.containsMouse ? Color.background : Color.foreground
        font.pixelSize: 18
        font.bold: true
      }

      MouseArea {
        id: closeArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
          root.hidden = true
          root.pinned = false
        }
      }
    }

    Column {
      id: layout
      x: 13
      y: 13
      width: card.width - 26
      spacing: 8
      Text {
        textFormat: Text.PlainText
        text: root.working ? "Voz Codex · Trabajando" : "Voz Codex"
        color: Color.accent
        font.bold: true
      }
      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: typeof root.task.detail === "string" && root.task.detail
          ? root.task.detail.slice(0, 180) : "Sin tareas en curso."
        color: Color.foreground
        wrapMode: Text.Wrap
      }
      Text {
        textFormat: Text.PlainText
        text: root.working ? "Doble clic para abrir · Alt+X para cancelar"
                           : (root.canFollow ? "Doble clic para abrir el chat" : "")
        color: Color.muted
      }
    }

    MouseArea {
      id: grab
      anchors.fill: parent
      hoverEnabled: true
      onEntered: forceActiveFocus()
      onDoubleClicked: if (root.canFollow) root.runAction("follow")
      Keys.onPressed: event => {
        if (event.key === Qt.Key_X && (event.modifiers & Qt.AltModifier) && root.task.state === "working") {
          event.accepted = true
          root.runAction("cancel")
        }
      }
    }
  }
}
