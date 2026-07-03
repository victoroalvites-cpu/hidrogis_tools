import math

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TimeConcentrationDialog(QWidget):
    """Resumen de tiempos de concentracion calculados en Morfometria."""

    TC_FIELDS = [
        ("tipo", "Tipo"),
        ("codigo", "Codigo"),
        ("area_km2", "Area km2"),
        ("long_ax_km", "Long max rec km"),
        ("pend_cp", "Pend cauce %"),
        ("kerby_n", "N Kerby"),
        ("tc_kirpich_h", "Kirpich h"),
        ("tc_kerby_h", "Kerby h"),
        ("tc_kerby_kirpich_h", "Kerby-Kirpich h"),
        ("tc_california_h", "California h"),
        ("tc_chow_h", "Ven Te Chow h"),
        ("tc_temez_h", "Temez h"),
        ("tc_johnstone_h", "Johnstone-Cross h"),
        ("tc_scs_ranser_h", "SCS-Ranser h"),
        ("tc_ventura_h", "Ventura-Heras h"),
        ("tc_usace_h", "Ing EE.UU. h"),
        ("tc_tournon_h", "Tournon h"),
        ("tc_passini_h", "Passini h"),
        ("tc_validos", "Metodos incluidos"),
        ("tc_n_validos", "N metodos"),
        ("tc_rango_h", "Rango Tc h"),
        ("tc_prom_h", "Tc prom h"),
        ("t_retardo_min", "T retardo min"),
    ]

    def __init__(self, morphometry_dialog, open_morphometry_callback=None, parent=None):
        super().__init__(parent)
        self.morphometry_dialog = morphometry_dialog
        self.open_morphometry_callback = open_morphometry_callback
        self._build_ui()
        self.refresh_from_morphometry()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("Tiempo de concentracion")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        body = QLabel(
            "Esta vista resume los tiempos de concentracion calculados desde Morfometria. "
            "Primero calcula los parametros y luego actualiza esta tabla para revisar los "
            "metodos, el rango aceptado, el promedio y el tiempo de retardo."
        )
        body.setWordWrap(True)

        button_row = QHBoxLayout()
        self.open_morphometry_button = QPushButton("Ir a Morfometria")
        self.open_morphometry_button.clicked.connect(self._open_morphometry)
        self.refresh_button = QPushButton("Actualizar desde Morfometria")
        self.refresh_button.clicked.connect(self.refresh_from_morphometry)
        button_row.addWidget(self.open_morphometry_button)
        button_row.addStretch(1)
        button_row.addWidget(self.refresh_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.TC_FIELDS))
        self.table.setHorizontalHeaderLabels([label for _, label in self.TC_FIELDS])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        root.addWidget(title)
        root.addWidget(body)
        root.addLayout(button_row)
        root.addWidget(self.status_label)
        root.addWidget(self.table, 1)

    def _open_morphometry(self):
        if self.open_morphometry_callback:
            self.open_morphometry_callback()

    def set_project_context(self, project_folder, folders):
        self.project_folder = project_folder
        self.project_folders = folders

    def refresh_from_morphometry(self):
        rows = list(getattr(self.morphometry_dialog, "last_rows", []) or [])
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, (field_name, _) in enumerate(self.TC_FIELDS):
                item = QTableWidgetItem(self._format_value(row.get(field_name)))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_index, column_index, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

        if rows:
            self.status_label.setText(
                f"Mostrando {len(rows)} unidad(es). Los valores provienen del ultimo calculo "
                "ejecutado en la pestana Morfometria."
            )
        else:
            self.status_label.setText(
                "Aun no hay resultados. Ejecuta Calcular parametros en Morfometria y luego "
                "presiona Actualizar desde Morfometria."
            )

    def _format_value(self, value):
        if value is None:
            return ""
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return ""
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return str(value)
