from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .main_dialog import HidroGISToolsDialog


class HidroGISToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.menu_name = self.tr("&HidroGIS Watershed Tools")

    def tr(self, message):
        return QCoreApplication.translate("HidroGISTools", message)

    def initGui(self):
        icon = QIcon(str(Path(__file__).resolve().parent / "icon.png"))
        self.action = QAction(icon, self.tr("HidroGIS Watershed Tools"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu_name, self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(self.menu_name, self.action)
            self.action = None

    def run(self):
        if self.dialog is None:
            self.dialog = HidroGISToolsDialog(self.iface)
        self.dialog.refresh_layers()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
