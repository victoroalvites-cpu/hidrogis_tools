from pathlib import Path

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from .dem_dialog import DemPreprocessDialog
from .morphometry_dialog import MorphometryDialog
from .project_utils import ensure_project_structure
from .terrain_dialog import WatershedDelineationDialog
from .tc_dialog import TimeConcentrationDialog


class HidroGISToolsDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("HidroGIS Watershed Tools")
        self.setMinimumSize(680, 460)
        self.setSizeGripEnabled(True)
        self._resize_to_screen()
        self._build_ui()
        self._load_project_folder()

    def _resize_to_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(860, 660)
            return
        available = screen.availableGeometry()
        width = min(920, max(760, int(available.width() * 0.72)))
        height = min(700, max(520, int(available.height() * 0.78)))
        self.resize(width, height)

    def _build_ui(self):
        root = QVBoxLayout(self)

        project_group = QGroupBox("Proyecto")
        project_layout = QHBoxLayout(project_group)
        self.project_folder_edit = QLineEdit()
        self.project_folder_edit.setPlaceholderText("Selecciona una carpeta raiz del proyecto")
        self.project_folder_button = QPushButton("Examinar")
        self.project_apply_button = QPushButton("Aplicar rutas")
        self.project_status_label = QLabel("")
        self.project_status_label.setWordWrap(True)
        project_layout.addWidget(QLabel("Carpeta"))
        project_layout.addWidget(self.project_folder_edit, 1)
        project_layout.addWidget(self.project_folder_button)
        project_layout.addWidget(self.project_apply_button)

        self.tabs = QTabWidget()
        self.dem_tab = DemPreprocessDialog(self.iface, self, show_close_button=False)
        self.watershed_tab = WatershedDelineationDialog(self.iface, self, show_close_button=False)
        self.morphometry_tab = MorphometryDialog(self.iface, self)
        self.tc_tab = TimeConcentrationDialog(
            self.morphometry_tab,
            open_morphometry_callback=self._show_morphometry_tab,
            parent=self,
        )

        self.tabs.addTab(self.dem_tab, "DEM")
        self.tabs.addTab(self.watershed_tab, "Cuencas")
        self.tabs.addTab(self.morphometry_tab, "Morfometria")
        self.tabs.addTab(self.tc_tab, "Tiempo de concentracion")

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)

        root.addWidget(project_group)
        root.addWidget(self.project_status_label)
        root.addWidget(self.tabs)
        root.addLayout(button_row)

        self.project_folder_button.clicked.connect(self._choose_project_folder)
        self.project_apply_button.clicked.connect(lambda: self._apply_project_folder(show_message=True))

    def _show_morphometry_tab(self):
        self.tabs.setCurrentWidget(self.morphometry_tab)

    def _choose_project_folder(self):
        start = self.project_folder_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta del proyecto", start)
        if folder:
            self.project_folder_edit.setText(folder)
            self._apply_project_folder(show_message=True)

    def _load_project_folder(self):
        saved_folder = QSettings().value("HidroGISTools/project_root", "") or ""
        if saved_folder:
            self.project_folder_edit.setText(saved_folder)
            self._apply_project_folder(show_message=False)

    def _apply_project_folder(self, show_message=False):
        folder_text = self.project_folder_edit.text().strip()
        if not folder_text:
            if show_message:
                QMessageBox.information(
                    self,
                    "Carpeta del proyecto",
                    "Selecciona una carpeta raiz para crear la estructura del proyecto.",
                )
            return

        root_folder, folders, config_path = ensure_project_structure(folder_text)
        QSettings().setValue("HidroGISTools/project_root", str(root_folder))

        self._set_output_folder(self.dem_tab, folders["dem"])
        self._set_output_folder(self.watershed_tab, folders["watershed"])
        self._set_output_folder(self.morphometry_tab, folders["morphometry"])
        if hasattr(self.tc_tab, "set_project_context"):
            self.tc_tab.set_project_context(root_folder, folders)

        self.project_status_label.setText(
            "Proyecto activo: {0} | DEM: 01_DEM, Cuenca: 02_Cuenca, "
            "Morfometria: 03_Morfometria, Tiempo: 04_Tiempo_Concentracion.".format(root_folder)
        )
        if show_message:
            QMessageBox.information(
                self,
                "Proyecto listo",
                "Se crearon/actualizaron las subcarpetas del proyecto.\n\n"
                f"Configuracion: {config_path}",
            )

    def _set_output_folder(self, dialog, folder):
        if hasattr(dialog, "set_output_folder"):
            dialog.set_output_folder(folder)
        elif hasattr(dialog, "output_folder_edit"):
            dialog.output_folder_edit.setText(str(folder))

    def refresh_layers(self):
        self.dem_tab.refresh_layers()
        self.watershed_tab.refresh_layers()
        self.morphometry_tab.refresh_layers()
        self.tc_tab.refresh_from_morphometry()
