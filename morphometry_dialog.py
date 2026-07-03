import csv
import heapq
import math
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.analysis import QgsZonalStatistics
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapLayerComboBox

from .output_utils import add_or_replace_layer, prepare_output_path, remove_project_layers_by_name


class MorphometryDialog(QWidget):
    KERBY_TERRAIN_OPTIONS = (
        ("Acera", 0.02),
        ("Suelo suave, descubierto y compactado", 0.10),
        ("Vegetacion pobre, cultivos en hileras o superficies compactadas", 0.20),
        ("Pasto y vegetacion promedio", 0.40),
        ("Bosques caducifolios", 0.60),
        ("Vegetacion densa, bosque de coniferas o bosques caducifolios", 0.80),
    )

    RESULT_FIELDS = [
        ("tipo", "Tipo", QVariant.String),
        ("codigo", "Codigo", QVariant.String),
        ("area_km2", "Area km2", QVariant.Double),
        ("area_ha", "Area ha", QVariant.Double),
        ("perim_km", "Perim km", QVariant.Double),
        ("long_ax_km", "Long max rec km", QVariant.Double),
        ("lc_snyder_km", "Lc Snyder km", QVariant.Double),
        ("ancho_med", "Ancho med km", QVariant.Double),
        ("ff", "Factor forma", QVariant.Double),
        ("coef_forma", "Coef forma L2/A", QVariant.Double),
        ("kc", "Compacidad", QVariant.Double),
        ("rc", "Circularidad", QVariant.Double),
        ("re", "Elongacion", QVariant.Double),
        ("elev_min", "Elev min", QVariant.Double),
        ("elev_med", "Elev med", QVariant.Double),
        ("elev_max", "Elev max", QVariant.Double),
        ("relieve_m", "Relieve m", QVariant.Double),
        ("int_hipso", "Int hipso", QVariant.Double),
        ("pend_med", "Pend med %", QVariant.Double),
        ("rh", "Rel relieve", QVariant.Double),
        ("coef_masiv", "Coef masividad", QVariant.Double),
        ("coef_orog", "Coef orografico", QVariant.Double),
        ("long_red", "Long red km", QVariant.Double),
        ("long_cp", "Long cauce km", QVariant.Double),
        ("pend_cp", "Pend cauce %", QVariant.Double),
        ("dens_dren", "Dens dren", QVariant.Double),
        ("num_cauces", "Num cauces", QVariant.Int),
        ("frec_cauces", "Frec cauces", QVariant.Double),
        ("text_dren", "Text dren", QVariant.Double),
        ("long_esc_sup", "Long esc sup km", QVariant.Double),
        ("const_mant", "Const mant km", QVariant.Double),
        ("num_robust", "Num robustez", QVariant.Double),
        ("num_infil", "Num infiltracion", QVariant.Double),
        ("cent_x", "Centroide X", QVariant.Double),
        ("cent_y", "Centroide Y", QVariant.Double),
    ]

    TC_RESULT_FIELDS = [
        ("kerby_n", "N Kerby", QVariant.Double),
        ("tc_kirpich_h", "Tc Kirpich h", QVariant.Double),
        ("tc_kerby_h", "Tc Kerby h", QVariant.Double),
        ("tc_kerby_kirpich_h", "Tc Kerby-Kirpich h", QVariant.Double),
        ("tc_california_h", "Tc California h", QVariant.Double),
        ("tc_chow_h", "Tc Ven Te Chow h", QVariant.Double),
        ("tc_temez_h", "Tc Temez h", QVariant.Double),
        ("tc_johnstone_h", "Tc Johnstone-Cross h", QVariant.Double),
        ("tc_scs_ranser_h", "Tc SCS-Ranser h", QVariant.Double),
        ("tc_ventura_h", "Tc Ventura-Heras h", QVariant.Double),
        ("tc_usace_h", "Tc Ing EE.UU. h", QVariant.Double),
        ("tc_tournon_h", "Tc Tournon h", QVariant.Double),
        ("tc_passini_h", "Tc Passini h", QVariant.Double),
        ("tc_validos", "Metodos Tc", QVariant.String),
        ("tc_n_validos", "N metodos Tc", QVariant.Int),
        ("tc_rango_h", "Rango Tc h", QVariant.String),
        ("tc_prom_h", "Tc prom h", QVariant.Double),
        ("t_retardo_min", "T retardo min", QVariant.Double),
    ]

    FIELD_NOTES = {
        "tipo": "Tipo de unidad: cuenca general o subunidad hidrografica.",
        "codigo": "Identificador de la unidad analizada.",
        "area_km2": "Area planimetrica de la unidad en kilometros cuadrados.",
        "area_ha": "Area planimetrica de la unidad en hectareas.",
        "perim_km": "Perimetro de la unidad en kilometros.",
        "cent_x": "Coordenada X del centroide en el CRS de trabajo.",
        "cent_y": "Coordenada Y del centroide en el CRS de trabajo.",
        "elev_min": "Elevacion minima zonal del DEM.",
        "elev_med": "Elevacion media zonal del DEM.",
        "elev_max": "Elevacion maxima zonal del DEM.",
        "relieve_m": "Diferencia entre elevacion maxima y minima.",
        "int_hipso": "Integral hipsometrica: (Elev_media - Elev_min) / (Elev_max - Elev_min).",
        "pend_med": "Pendiente media zonal calculada a partir del raster de pendiente en porcentaje.",
        "long_ax_km": "Longitud de maximo recorrido hidrologico sobre la red de drenaje.",
        "lc_snyder_km": "Longitud Lc de Snyder: distancia sobre el cauce principal desde la salida hasta el punto del cauce mas cercano al centroide.",
        "ancho_med": "Ancho medio: Area / longitud de maximo recorrido.",
        "ff": "Factor de forma: Area / longitud de maximo recorrido^2.",
        "coef_forma": "Coeficiente de forma de Horton: longitud de maximo recorrido^2 / Area.",
        "kc": "Coeficiente de compacidad de Gravelius.",
        "rc": "Relacion de circularidad: 4*pi*Area / Perimetro^2.",
        "re": "Relacion de elongacion: diametro de circulo equivalente / longitud de maximo recorrido.",
        "rh": "Relacion de relieve: Relieve / longitud de maximo recorrido.",
        "coef_masiv": "Coeficiente de masividad: elevacion media / area.",
        "coef_orog": "Coeficiente orografico: elevacion media^2 / area.",
        "long_red": "Longitud total de red de drenaje dentro de la unidad.",
        "long_cp": "Longitud del cauce principal aproximada con la misma ruta de maximo recorrido.",
        "pend_cp": "Pendiente aproximada del cauce: Relieve / Longitud del cauce principal.",
        "tc_kirpich_h": "Tiempo de concentracion por Kirpich, en horas. Formula orientada a cuencas pequenas y pendientes pronunciadas.",
        "kerby_n": "Coeficiente de retardo N usado para los metodos Kerby y Kerby-Kirpich.",
        "tc_kerby_h": "Tiempo de concentracion por Kerby, en horas. Usa el coeficiente de retardo N seleccionado.",
        "tc_kerby_kirpich_h": "Tiempo de concentracion combinado Kerby-Kirpich, en horas.",
        "tc_california_h": "Tiempo de concentracion por California Culverts Practice, en horas.",
        "tc_chow_h": "Tiempo de concentracion por Ven Te Chow, en horas.",
        "tc_temez_h": "Tiempo de concentracion por Temez, en horas. Formula practica para cuencas naturales con cauce definido.",
        "tc_johnstone_h": "Tiempo de concentracion por Johnstone-Cross, en horas. Usa longitud en km y pendiente del cauce en m/km.",
        "tc_scs_ranser_h": "Tiempo de concentracion por SCS-Ranser, en horas. Usa longitud del cauce y diferencia de cotas.",
        "tc_ventura_h": "Tiempo de concentracion por Ventura-Heras, en horas. Usa longitud en km y pendiente del cauce en porcentaje.",
        "tc_usace_h": "Tiempo de concentracion por el Cuerpo de Ingenieros de EE.UU., en horas.",
        "tc_tournon_h": "Tiempo de concentracion por Tournon, en horas.",
        "tc_passini_h": "Tiempo de concentracion por Passini, en horas. Formula empirica basada en area, longitud y pendiente.",
        "tc_validos": "Metodos de tiempo de concentracion incluidos en el promedio.",
        "tc_n_validos": "Numero de metodos usados para el promedio.",
        "tc_rango_h": "Rango minimo-maximo de los tiempos de concentracion aceptados, en horas.",
        "tc_prom_h": "Promedio de los tiempos de concentracion incluidos, en horas.",
        "t_retardo_min": "Tiempo de retardo calculado como 0.6 * Tc promedio, en minutos.",
        "dens_dren": "Densidad de drenaje: longitud total de red / area.",
        "num_cauces": "Numero de tramos de drenaje intersectados por la unidad.",
        "frec_cauces": "Frecuencia de cauces: numero de tramos / area.",
        "text_dren": "Textura de drenaje: numero de tramos / perimetro.",
        "long_esc_sup": "Longitud de escurrimiento superficial aproximada: 1 / (2 * densidad de drenaje).",
        "const_mant": "Constante de mantenimiento de canales: 1 / densidad de drenaje.",
        "num_robust": "Numero de robustez: densidad de drenaje * relieve en km.",
        "num_infil": "Numero de infiltracion: densidad de drenaje * frecuencia de cauces.",
    }

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("HidroGIS Watershed Tools - Morfometria")
        self.resize(920, 760)
        self.last_rows = []
        self.last_combined_graph = None
        self._build_ui()
        self.refresh_layers()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        input_group = QGroupBox("1. Capas de entrada")
        input_layout = QFormLayout(input_group)
        self.input_layout = input_layout
        self.morphometry_mode_combo = QComboBox()
        self.morphometry_mode_combo.addItem("Cuenca unica (QGIS/GRASS)", "qgis")
        self.morphometry_mode_combo.addItem("Subunidades HEC-HMS/importadas", "hms")
        self.morphometry_mode_combo.setToolTip(
            "Cuenca unica calcula los parametros de una sola cuenca delimitada en QGIS. "
            "Subunidades HEC-HMS/importadas permite usar subcuencas y longest flowpath externos."
        )
        self.dem_layer_combo = QgsMapLayerComboBox()
        self.dem_layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.basin_layer_combo = QgsMapLayerComboBox()
        self.basin_layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.include_basin_check = QCheckBox("Incluir tambien la cuenca general")
        self.include_basin_check.setChecked(False)
        self.include_basin_check.setToolTip(
            "Desactivado por defecto para trabajar solo con subunidades. Activalo si necesitas "
            "parametros y recorridos de la cuenca general."
        )
        self.subunits_layer_combo = QgsMapLayerComboBox()
        self.subunits_layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.stream_layer_combo = QgsMapLayerComboBox()
        self.stream_layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.external_flowpath_combo = QgsMapLayerComboBox()
        self.external_flowpath_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        if hasattr(self.external_flowpath_combo, "setAllowEmptyLayer"):
            self.external_flowpath_combo.setAllowEmptyLayer(True)
        self.external_flowpath_combo.setToolTip(
            "Usa aqui el longest flowpath importado de HEC-HMS. Esta capa solo alimenta la longitud "
            "maxima del cauce y Lc Snyder; la densidad de drenaje sigue usando la red completa."
        )
        self.outlet_layer_combo = QgsMapLayerComboBox()
        self.outlet_layer_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        if hasattr(self.outlet_layer_combo, "setAllowEmptyLayer"):
            self.outlet_layer_combo.setAllowEmptyLayer(True)
        self.dem_note_label = QLabel(
            "Para maximo recorrido y parametros de relieve se recomienda el DEM morfometrico "
            "(recortado/reproyectado). El DEM hidrologico queda disponible para comparacion."
        )
        self.dem_note_label.setWordWrap(True)
        input_layout.addRow("Modo de morfometria", self.morphometry_mode_combo)
        input_layout.addRow("DEM morfometrico", self.dem_layer_combo)
        input_layout.addRow("", self.dem_note_label)
        input_layout.addRow("Cuenca general", self.basin_layer_combo)
        input_layout.addRow("", self.include_basin_check)
        input_layout.addRow("Subunidades", self.subunits_layer_combo)
        input_layout.addRow("Red de drenaje", self.stream_layer_combo)
        input_layout.addRow("Longest flowpath externo", self.external_flowpath_combo)
        input_layout.addRow("Punto de salida", self.outlet_layer_combo)

        output_group = QGroupBox("2. Salidas")
        output_layout = QFormLayout(output_group)
        self.output_layout = output_layout
        self.output_folder_edit = QLineEdit(str(Path.home()))
        self.output_folder_button = QPushButton("Examinar")
        output_folder_row = QHBoxLayout()
        output_folder_row.addWidget(self.output_folder_edit)
        output_folder_row.addWidget(self.output_folder_button)
        self.prefix_edit = QLineEdit("hidrogis_morfometria")
        self.add_results_check = QCheckBox("Agregar resultados al proyecto")
        self.add_results_check.setChecked(True)
        self.max_flow_method_combo = QComboBox()
        self.max_flow_method_combo.addItem("D8 interno tipo HEC-HMS (Recomendado)", "d8")
        self.max_flow_method_combo.addItem("Red vectorial (Respaldo)", "network")
        self.max_flow_method_combo.setToolTip(
            "Define como se traza el maximo recorrido. D8 interno es el metodo recomendado "
            "ya que traza la ruta topográfica desde la divisoria de aguas. Red vectorial queda como "
            "respaldo para conectar el cauce principal."
        )
        self.add_subunit_routes_check = QCheckBox("Agregar tambien recorridos por subunidad")
        self.add_subunit_routes_check.setChecked(False)
        self.add_subunit_routes_check.setToolTip(
            "Se guardan siempre, pero se cargan al proyecto solo si activas esta opcion. "
            "Esto evita que el maximo recorrido se confunda visualmente con toda la red."
        )
        self.kerby_terrain_combo = QComboBox()
        for terrain_name, coefficient in self.KERBY_TERRAIN_OPTIONS:
            self.kerby_terrain_combo.addItem(f"{terrain_name} (N={coefficient:.2f})", coefficient)
        self.kerby_terrain_combo.addItem("Personalizado", None)
        self.kerby_terrain_combo.setCurrentIndex(1)
        self.kerby_terrain_combo.setToolTip(
            "Selecciona el coeficiente de retardo N para Kerby segun la cobertura predominante "
            "de la unidad hidrografica. Solo afecta Kerby y Kerby-Kirpich."
        )
        self.kerby_custom_spin = QDoubleSpinBox()
        self.kerby_custom_spin.setDecimals(2)
        self.kerby_custom_spin.setRange(0.01, 2.00)
        self.kerby_custom_spin.setSingleStep(0.01)
        self.kerby_custom_spin.setValue(0.10)
        self.kerby_custom_spin.setEnabled(False)
        self.kerby_custom_spin.setToolTip(
            "Valor N personalizado para Kerby. Se habilita al seleccionar Personalizado."
        )
        kerby_row = QHBoxLayout()
        kerby_row.setContentsMargins(0, 0, 0, 0)
        kerby_row.addWidget(self.kerby_terrain_combo, 1)
        kerby_row.addWidget(QLabel("N personalizado"))
        kerby_row.addWidget(self.kerby_custom_spin)
        output_layout.addRow("Carpeta de salida", output_folder_row)
        output_layout.addRow("Prefijo", self.prefix_edit)
        output_layout.addRow("", self.add_results_check)
        output_layout.addRow("Metodo maximo recorrido", self.max_flow_method_combo)
        output_layout.addRow("", self.add_subunit_routes_check)
        output_layout.addRow("Terreno / N Kerby", kerby_row)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.RESULT_FIELDS))
        self.table.setHorizontalHeaderLabels([field[1] for field in self.RESULT_FIELDS])
        self.table.setMinimumHeight(160)

        hypso_group = QGroupBox("Integral hipsometrica")
        hypso_layout = QVBoxLayout(hypso_group)
        hypso_selector_row = QHBoxLayout()
        self.hypso_combo = QComboBox()
        self.hypso_combo.setMinimumWidth(360)
        self.show_selected_hypso_button = QPushButton("Ver fila seleccionada")
        hypso_selector_row.addWidget(QLabel("Curva"))
        hypso_selector_row.addWidget(self.hypso_combo, 1)
        hypso_selector_row.addWidget(self.show_selected_hypso_button)
        self.hypso_info_label = QLabel("Calcula los parametros para ver aqui la curva hipsometrica.")
        self.hypso_image_label = QLabel("Sin curva hipsometrica cargada.")
        self.hypso_image_label.setAlignment(Qt.AlignCenter)
        self.hypso_image_label.setMinimumHeight(170)
        self.hypso_image_label.setStyleSheet("QLabel { background: #ffffff; border: 1px solid #b8b8b8; }")
        hypso_layout.addLayout(hypso_selector_row)
        hypso_layout.addWidget(self.hypso_info_label)
        hypso_layout.addWidget(self.hypso_image_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(95)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.refresh_button = QPushButton("Refrescar lista de capas")
        self.refresh_button.setToolTip(
            "Vuelve a leer las capas abiertas en QGIS y actualiza los desplegables de entrada."
        )
        self.run_button = QPushButton("Calcular parametros")
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.run_button)

        content_layout.addWidget(input_group)
        content_layout.addWidget(output_group)
        content_layout.addWidget(self.info_label)
        content_layout.addWidget(QLabel("Resultados"))
        content_layout.addWidget(self.table)
        content_layout.addWidget(hypso_group)
        content_layout.addWidget(QLabel("Registro"))
        content_layout.addWidget(self.log)
        root.addWidget(scroll, 1)
        root.addLayout(button_row)

        self.output_folder_button.clicked.connect(self._choose_output_folder)
        self.refresh_button.clicked.connect(self.refresh_layers)
        self.run_button.clicked.connect(self.calculate)
        self.kerby_terrain_combo.currentIndexChanged.connect(self._update_kerby_custom_control)
        self.morphometry_mode_combo.currentIndexChanged.connect(self._update_morphometry_mode_controls)
        self.hypso_combo.currentIndexChanged.connect(self._update_hypsometric_preview)
        self.show_selected_hypso_button.clicked.connect(self._show_hypsometric_for_selected_row)
        self._update_kerby_custom_control()
        self._update_morphometry_mode_controls()

    def refresh_layers(self):
        self.dem_layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.basin_layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.subunits_layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.stream_layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.external_flowpath_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.outlet_layer_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        self._select_layer_by_name(
            self.dem_layer_combo,
            (
                "dem recortado",
                "dem reproyectado",
                "dtm proyectado",
                "dem rellenado",
                "dem hidrologico",
                "dem rellenado reacondicionado",
                "dem",
            ),
            prefer_best=True,
        )
        self._select_layer_by_name(self.basin_layer_combo, ("cuenca",))
        self._select_layer_by_name(self.subunits_layer_combo, ("subunidades",))
        self._select_layer_by_name(self.stream_layer_combo, ("red de drenaje",))
        self._select_layer_by_name(
            self.external_flowpath_combo,
            ("longest_flowpath", "longest flowpath", "maximo recorrido", "maximum flow", "flowpath"),
        )
        self._select_layer_by_name(self.outlet_layer_combo, ("punto de salida", "punto salida", "outlet"))
        self._update_morphometry_mode_controls()

    def _choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def set_output_folder(self, folder):
        self.output_folder_edit.setText(str(folder))

    def _update_kerby_custom_control(self):
        is_custom = self.kerby_terrain_combo.currentData() is None
        self.kerby_custom_spin.setEnabled(is_custom)

    def _update_morphometry_mode_controls(self):
        is_hms_mode = (self.morphometry_mode_combo.currentData() or "qgis") == "hms"
        if not is_hms_mode:
            self.include_basin_check.setChecked(True)
        self.include_basin_check.setEnabled(is_hms_mode)
        self.subunits_layer_combo.setEnabled(is_hms_mode)
        self.external_flowpath_combo.setEnabled(is_hms_mode)
        self.max_flow_method_combo.setEnabled(not is_hms_mode)
        self._set_form_row_visible(self.input_layout, self.include_basin_check, is_hms_mode)
        self._set_form_row_visible(self.input_layout, self.subunits_layer_combo, is_hms_mode)
        self._set_form_row_visible(self.input_layout, self.external_flowpath_combo, is_hms_mode)
        self._set_form_row_visible(self.output_layout, self.add_subunit_routes_check, is_hms_mode)
        if is_hms_mode:
            self.dem_note_label.setText(
                "Modo HEC-HMS: usa el DEM elegido para relieve/pendiente y usa el longest flowpath "
                "externo para longitud maxima y Lc Snyder. La red de drenaje completa se conserva "
                "para densidad de drenaje."
            )
            self.info_label.setText(
                "Calcula parametros para subunidades importadas, pensado para comparar o completar "
                "un modelo de HEC-HMS. La capa de subunidades y el longest flowpath externo alimentan "
                "la longitud maxima y Lc Snyder; la densidad de drenaje sigue usando la red completa."
            )
        else:
            self.dem_note_label.setText(
                "Modo cuenca unica: calcula parametros para una sola cuenca delimitada. Para relieve "
                "y maximo recorrido se recomienda el DEM morfometrico recortado/reproyectado."
            )
            self.info_label.setText(
                "Calcula parametros de area, forma, relieve, pendiente, red de drenaje e integral "
                "hipsometrica solo para la cuenca general. Si necesitas trabajar con varias "
                "subunidades, cambia al modo HEC-HMS/importadas y usa capas externas ya revisadas."
            )

    def _set_form_row_visible(self, form_layout, widget, visible):
        label = form_layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
        widget.setVisible(visible)

    def _kerby_n_value(self):
        selected_value = self.kerby_terrain_combo.currentData()
        coefficient = self.kerby_custom_spin.value() if selected_value is None else selected_value
        coefficient = float(coefficient)
        if coefficient <= 0:
            raise ValueError("El coeficiente N de Kerby debe ser mayor que cero.")
        return coefficient

    def calculate(self):
        try:
            import processing
        except ImportError:
            QMessageBox.critical(self, "Processing no disponible", "No se pudo cargar el modulo Processing de QGIS.")
            return

        self.log.clear()
        self.table.setRowCount(0)
        self._clear_hypsometric_view()
        self.run_button.setEnabled(False)
        try:
            dem_layer = self._selected_dem()
            morphometry_mode = self.morphometry_mode_combo.currentData() or "qgis"
            is_hms_mode = morphometry_mode == "hms"
            include_basin = True if not is_hms_mode else self.include_basin_check.isChecked()
            basin_layer = self._selected_polygon_layer(self.basin_layer_combo, "cuenca general") if include_basin else None
            subunits_layer = self._selected_polygon_layer(self.subunits_layer_combo, "subunidades") if is_hms_mode else None
            stream_layer = self._selected_line_layer(self.stream_layer_combo, "red de drenaje")
            external_flowpath_layer = None
            if is_hms_mode:
                external_flowpath_layer = self._optional_line_layer(self.external_flowpath_combo)
                if external_flowpath_layer is None:
                    raise ValueError(
                        "En modo HEC-HMS selecciona una capa lineal de longest flowpath externo."
                    )
            outlet_layer = self._optional_point_layer()
            max_flow_method = "external" if morphometry_mode == "hms" else (self.max_flow_method_combo.currentData() or "network")
            kerby_n = self._kerby_n_value()
            if not self._is_projected_crs(dem_layer.crs()):
                raise ValueError("Usa un DEM en CRS proyectado para calcular parametros morfometricos.")
            if not include_basin and not is_hms_mode:
                raise ValueError("El modo cuenca unica necesita una capa de cuenca general.")

            output_dir = Path(self.output_folder_edit.text()).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
            prefix = self._safe_prefix(self.prefix_edit.text())
            graph_dir = output_dir / f"{prefix}_curvas_hipsometrica"
            graph_dir.mkdir(parents=True, exist_ok=True)

            slope_path = self._create_slope_raster(processing, dem_layer, output_dir, prefix)
            basin_output = output_dir / f"{prefix}_01_morfometria_cuenca.gpkg"
            subunits_output = output_dir / f"{prefix}_02_morfometria_subunidades.gpkg"
            csv_output = output_dir / f"{prefix}_03_morfometria_resumen.csv"
            xlsx_output = output_dir / f"{prefix}_04_morfometria_resumen.xlsx"
            max_flow_basin_output = output_dir / f"{prefix}_05_maximo_recorrido_cuenca.gpkg"
            max_flow_subunits_output = output_dir / f"{prefix}_06_maximo_recorrido_subunidades.gpkg"
            snyder_basin_output = output_dir / f"{prefix}_07_lc_snyder_cuenca.gpkg"
            snyder_subunits_output = output_dir / f"{prefix}_08_lc_snyder_subunidades.gpkg"
            combined_graph = graph_dir / f"{prefix}_curvas_hipsometrica_todas.png"

            basin_units = self._basin_units(basin_layer, dem_layer) if include_basin else []
            subunit_units = self._subunit_units(subunits_layer, dem_layer) if is_hms_mode else []
            outlet_points = self._outlet_points(outlet_layer, dem_layer.crs()) if outlet_layer else []
            self._log(f"Coeficiente N de Kerby: {kerby_n:.2f} ({self.kerby_terrain_combo.currentText()}).")
            if is_hms_mode:
                self._log(
                    f"Modo HEC-HMS: usando longest flowpath externo '{external_flowpath_layer.name()}' "
                    "para longitud maxima y Lc Snyder."
                )
            else:
                self._log("Modo cuenca unica: se omitieron subunidades y recorridos por subunidad.")
            if not include_basin:
                self._log("Cuenca general omitida. Se calcularan solo las subunidades.")

            basin_rows, basin_curves = [], []
            if include_basin:
                basin_rows, basin_curves = self._calculate_and_save_units(
                    processing,
                    dem_layer,
                    slope_path,
                    stream_layer,
                    basin_units,
                    basin_output,
                    self._display_layer_name(prefix, "Morfometria cuenca"),
                    graph_dir,
                    outlet_points,
                    max_flow_method,
                    kerby_n,
                    allow_nearest_outlet=True,
                    external_flowpath_layer=external_flowpath_layer,
                )
            subunit_rows, subunit_curves = [], []
            if is_hms_mode:
                subunit_rows, subunit_curves = self._calculate_and_save_units(
                    processing,
                    dem_layer,
                    slope_path,
                    stream_layer,
                    subunit_units,
                    subunits_output,
                    self._display_layer_name(prefix, "Morfometria subunidades"),
                    graph_dir,
                    outlet_points,
                    max_flow_method,
                    kerby_n,
                    allow_nearest_outlet=False,
                    external_flowpath_layer=external_flowpath_layer,
                )

            self.last_rows = basin_rows + subunit_rows
            self._save_line_results(
                processing,
                basin_rows,
                "_max_flow_geom",
                "long_ax_km",
                max_flow_basin_output,
                self._display_layer_name(prefix, "Maximo recorrido cuenca"),
                dem_layer.crs(),
                self.add_results_check.isChecked(),
            )
            if is_hms_mode:
                self._save_line_results(
                    processing,
                    subunit_rows,
                    "_max_flow_geom",
                    "long_ax_km",
                    max_flow_subunits_output,
                    self._display_layer_name(prefix, "Maximo recorrido subunidades"),
                    dem_layer.crs(),
                    self.add_results_check.isChecked() and self.add_subunit_routes_check.isChecked(),
                )
            self._save_line_results(
                processing,
                basin_rows,
                "_snyder_geom",
                "lc_snyder_km",
                snyder_basin_output,
                self._display_layer_name(prefix, "Lc Snyder cuenca"),
                dem_layer.crs(),
                self.add_results_check.isChecked(),
            )
            if is_hms_mode:
                self._save_line_results(
                    processing,
                    subunit_rows,
                    "_snyder_geom",
                    "lc_snyder_km",
                    snyder_subunits_output,
                    self._display_layer_name(prefix, "Lc Snyder subunidades"),
                    dem_layer.crs(),
                    self.add_results_check.isChecked() and self.add_subunit_routes_check.isChecked(),
                )
            self._write_csv(csv_output, self.last_rows)
            self._write_xlsx(xlsx_output, self.last_rows)

            tc_folder = output_dir.parent / "04_Tiempo_Concentracion"
            tc_folder.mkdir(parents=True, exist_ok=True)
            tc_xlsx = tc_folder / f"{prefix}_tiempos_concentracion.xlsx"
            tc_csv = tc_folder / f"{prefix}_tiempos_concentracion.csv"
            
            # 1. Guardar CSV exclusivo de Tiempos de Concentración
            tc_fields = [field[0] for field in self.TC_RESULT_FIELDS]
            with open(tc_csv, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["tipo", "codigo"] + tc_fields)
                writer.writeheader()
                for row in self.last_rows:
                    writer.writerow({k: row.get(k) for k in ["tipo", "codigo"] + tc_fields})
            tc_headers = ["Tipo", "Codigo"] + [field[1] for field in self.TC_RESULT_FIELDS]
            tc_keys = ["tipo", "codigo"] + tc_fields
            summary_rows = [tc_headers]
            for row in self.last_rows:
                summary_rows.append([row.get(key) for key in tc_keys])
            
            dictionary_rows = [["Campo", "Parametro", "Descripcion"]]
            for field_name, field_label, _ in self.TC_RESULT_FIELDS:
                dictionary_rows.append([field_name, field_label, self.FIELD_NOTES.get(field_name, "")])
            
            self._create_simple_xlsx(
                tc_xlsx,
                [
                    ("Resumen Tc", summary_rows),
                    ("Diccionario", dictionary_rows),
                ],
            )

            self._draw_combined_hypsometric_graph(combined_graph, basin_curves + subunit_curves)
            self._fill_table(self.last_rows)
            self._populate_hypsometric_view(self.last_rows, combined_graph)

            self._log("")
            self._log(f"Excel: {xlsx_output}")
            self._log(f"CSV: {csv_output}")
            self._log(f"Excel Tiempo de Concentracion: {tc_xlsx}")
            self._log(f"Graficos hipsometricos: {graph_dir}")
            self._log("Listo.")
            self.iface.messageBar().pushMessage(
                "HidroGIS Watershed Tools",
                "Parametros geomorfologicos calculados.",
                level=Qgis.Success,
                duration=6,
            )
        except Exception as exc:
            self._log(f"ERROR: {exc}")
            QMessageBox.critical(self, "Error en morfometria", str(exc))
        finally:
            self.run_button.setEnabled(True)

    def _calculate_and_save_units(
        self,
        processing,
        dem_layer,
        slope_path,
        stream_layer,
        units,
        output_path,
        layer_name,
        graph_dir,
        outlet_points=None,
        max_flow_method="network",
        kerby_n=0.10,
        allow_nearest_outlet=False,
        external_flowpath_layer=None,
    ):
        if not units:
            raise ValueError(f"No hay unidades validas para {layer_name}.")
        self._log(f"Calculando {layer_name}...")

        stats_layer = self._memory_layer_with_units(units, dem_layer.crs(), f"{layer_name}_stats")
        QgsZonalStatistics(
            stats_layer,
            dem_layer,
            "z_",
            1,
            QgsZonalStatistics.Min | QgsZonalStatistics.Max | QgsZonalStatistics.Mean,
        ).calculateStatistics(None)

        if slope_path:
            slope_layer = self._raster_layer_from_path(slope_path)
            if slope_layer and slope_layer.isValid():
                QgsZonalStatistics(
                    stats_layer,
                    slope_layer,
                    "s_",
                    1,
                    QgsZonalStatistics.Mean,
                ).calculateStatistics(None)

        rows = []
        curves = []
        final_layer = self._final_layer_template(stats_layer.crs(), layer_name)
        provider = final_layer.dataProvider()

        for feature in stats_layer.getFeatures():
            geom = QgsGeometry(feature.geometry())
            if geom is None or geom.isEmpty():
                continue
            outlet_point = self._outlet_point_for_geometry(
                geom,
                outlet_points or [],
                allow_nearest=allow_nearest_outlet,
            )
            row, curve = self._row_for_feature(
                feature,
                geom,
                dem_layer,
                stream_layer,
                graph_dir,
                outlet_point,
                processing,
                max_flow_method,
                kerby_n,
                external_flowpath_layer,
            )
            rows.append(row)
            if curve:
                curves.append(curve)

            out_feature = QgsFeature(final_layer.fields())
            out_feature.setGeometry(geom)
            out_feature.setAttributes([row[field[0]] for field in self.RESULT_FIELDS])
            provider.addFeature(out_feature)

        final_layer.updateExtents()
        output = prepare_output_path(output_path, self._log)
        result = processing.run("native:savefeatures", {"INPUT": final_layer, "OUTPUT": output})
        if self.add_results_check.isChecked():
            add_or_replace_layer(result["OUTPUT"], layer_name, "vector", self._log)
        return rows, curves

    def _row_for_feature(
        self,
        feature,
        geom,
        dem_layer,
        stream_layer,
        graph_dir,
        outlet_point=None,
        processing=None,
        max_flow_method="network",
        kerby_n=0.10,
        external_flowpath_layer=None,
    ):
        area_m2 = geom.area()
        area_km2 = area_m2 / 1000000.0 if area_m2 else None
        area_ha = area_m2 / 10000.0 if area_m2 else None
        perimeter_km = geom.length() / 1000.0 if geom.length() else None
        centroid = geom.centroid().asPoint()

        z_min = self._to_float(feature["z_min"])
        z_mean = self._to_float(feature["z_mean"])
        z_max = self._to_float(feature["z_max"])
        slope_mean = self._to_float(feature["s_mean"]) if feature.fields().lookupField("s_mean") >= 0 else None
        relief = z_max - z_min if z_min is not None and z_max is not None else None
        hypsometric = None
        if relief is not None and relief > 0 and z_mean is not None:
            hypsometric = (z_mean - z_min) / relief

        drainage = self._drainage_metrics(
            geom,
            stream_layer,
            dem_layer,
            outlet_point,
            processing,
            max_flow_method,
            external_flowpath_layer,
        )
        max_flow_km = drainage["main_km"]
        snyder_km, snyder_geom = self._snyder_centroid_length(
            drainage["main_geom"],
            centroid,
            outlet_point,
        )
        mean_width = area_km2 / max_flow_km if area_km2 and max_flow_km and max_flow_km > 0 else None
        form_factor = area_km2 / (max_flow_km * max_flow_km) if area_km2 and max_flow_km and max_flow_km > 0 else None
        form_coefficient = (max_flow_km * max_flow_km) / area_km2 if area_km2 and max_flow_km and area_km2 > 0 else None
        compactness = geom.length() / (2.0 * math.sqrt(math.pi * area_m2)) if area_m2 and geom.length() else None
        circularity = (4.0 * math.pi * area_m2) / (geom.length() ** 2) if area_m2 and geom.length() else None
        elongation = (2.0 * math.sqrt(area_m2 / math.pi)) / (max_flow_km * 1000.0) if area_m2 and max_flow_km else None
        relief_ratio = relief / (max_flow_km * 1000.0) if relief is not None and max_flow_km and max_flow_km > 0 else None
        massiveness = z_mean / area_km2 if z_mean is not None and area_km2 and area_km2 > 0 else None
        orographic = (z_mean * z_mean) / area_km2 if z_mean is not None and area_km2 and area_km2 > 0 else None

        drainage_density = drainage["total_km"] / area_km2 if area_km2 and area_km2 > 0 else None
        stream_frequency = drainage["count"] / area_km2 if area_km2 and area_km2 > 0 else None
        drainage_texture = drainage["count"] / perimeter_km if perimeter_km and perimeter_km > 0 else None
        channel_slope = (relief / (drainage["main_km"] * 1000.0)) * 100.0 if relief is not None and drainage["main_km"] > 0 else None
        channel_slope_fraction = channel_slope / 100.0 if channel_slope is not None else None
        tc = self._time_of_concentration_metrics(
            area_km2,
            drainage["main_km"],
            relief,
            z_min,
            z_mean,
            channel_slope_fraction,
            kerby_n,
        )
        overland_flow = 1.0 / (2.0 * drainage_density) if drainage_density and drainage_density > 0 else None
        maintenance_constant = 1.0 / drainage_density if drainage_density and drainage_density > 0 else None
        ruggedness = drainage_density * (relief / 1000.0) if drainage_density is not None and relief is not None else None
        infiltration_number = drainage_density * stream_frequency if drainage_density is not None and stream_frequency is not None else None

        code = str(feature["codigo"])
        graph_path, curve_points = self._create_hypsometric_graph(dem_layer, geom, graph_dir, code, hypsometric)

        row = {
            "tipo": feature["tipo"],
            "codigo": code,
            "area_km2": area_km2,
            "area_ha": area_ha,
            "perim_km": perimeter_km,
            "cent_x": centroid.x(),
            "cent_y": centroid.y(),
            "elev_min": z_min,
            "elev_med": z_mean,
            "elev_max": z_max,
            "relieve_m": relief,
            "int_hipso": hypsometric,
            "pend_med": slope_mean,
            "long_ax_km": max_flow_km,
            "lc_snyder_km": snyder_km,
            "ancho_med": mean_width,
            "ff": form_factor,
            "coef_forma": form_coefficient,
            "kc": compactness,
            "rc": circularity,
            "re": elongation,
            "rh": relief_ratio,
            "coef_masiv": massiveness,
            "coef_orog": orographic,
            "long_red": drainage["total_km"],
            "long_cp": drainage["main_km"],
            "pend_cp": channel_slope,
            "kerby_n": tc["kerby_n"],
            "tc_kirpich_h": tc["kirpich_h"],
            "tc_kerby_h": tc["kerby_h"],
            "tc_kerby_kirpich_h": tc["kerby_kirpich_h"],
            "tc_california_h": tc["california_h"],
            "tc_chow_h": tc["chow_h"],
            "tc_temez_h": tc["temez_h"],
            "tc_johnstone_h": tc["johnstone_h"],
            "tc_scs_ranser_h": tc["scs_ranser_h"],
            "tc_ventura_h": tc["ventura_h"],
            "tc_usace_h": tc["usace_h"],
            "tc_tournon_h": tc["tournon_h"],
            "tc_passini_h": tc["passini_h"],
            "tc_rango_h": tc["range_h"],
            "tc_prom_h": tc["average_h"],
            "t_retardo_min": tc["lag_min"],
            "tc_validos": tc["valid_methods"],
            "tc_n_validos": tc["valid_count"],
            "tc_estado": tc["method_status"],
            "tc_obs": tc["observation"],
            "dens_dren": drainage_density,
            "num_cauces": drainage["count"],
            "frec_cauces": stream_frequency,
            "text_dren": drainage_texture,
            "long_esc_sup": overland_flow,
            "const_mant": maintenance_constant,
            "num_robust": ruggedness,
            "num_infil": infiltration_number,
            "graph_path": str(graph_path) if graph_path else "",
            "_max_flow_geom": drainage["main_geom"],
            "_snyder_geom": snyder_geom,
        }
        curve = {"codigo": code, "points": curve_points} if curve_points else None
        return row, curve

    def _create_slope_raster(self, processing, dem_layer, output_dir, prefix):
        output = output_dir / f"{prefix}_00_pendiente_pct.tif"
        output = prepare_output_path(output, self._log)
        self._log("Calculando raster de pendiente para pendiente media de cuenca...")
        try:
            result = processing.run(
                "gdal:slope",
                {
                    "INPUT": dem_layer,
                    "BAND": 1,
                    "SCALE": 1,
                    "AS_PERCENT": True,
                    "COMPUTE_EDGES": True,
                    "ZEVENBERGEN": False,
                    "OPTIONS": "",
                    "EXTRA": "",
                    "OUTPUT": output,
                },
            )
            return result["OUTPUT"]
        except Exception as exc:
            self._log(f"No se pudo calcular pendiente media. Se continuara sin ese campo. Detalle: {exc}")
            return None

    def _time_of_concentration_metrics(
        self,
        area_km2,
        length_km,
        relief_m,
        z_min,
        z_mean,
        slope,
        kerby_n=0.10,
    ):
        metrics = {
            "kerby_n": None,
            "kirpich_h": None,
            "kerby_h": None,
            "kerby_kirpich_h": None,
            "california_h": None,
            "chow_h": None,
            "temez_h": None,
            "johnstone_h": None,
            "scs_ranser_h": None,
            "ventura_h": None,
            "usace_h": None,
            "tournon_h": None,
            "passini_h": None,
            "valid_methods": "",
            "valid_count": 0,
            "method_status": "",
            "range_h": "",
            "average_h": None,
            "lag_min": None,
            "observation": "",
        }
        try:
            kerby_retardance = float(kerby_n)
        except (TypeError, ValueError):
            kerby_retardance = 0.10
        kerby_retardance = max(kerby_retardance, 0.01)
        metrics["kerby_n"] = kerby_retardance

        if not area_km2 or area_km2 <= 0 or not length_km or length_km <= 0 or not slope or slope <= 0:
            metrics["observation"] = "No se pudo estimar Tc: falta area, longitud de cauce o pendiente valida."
            return metrics

        length_m = length_km * 1000.0

        # Kirpich: Tc(min)=0.01947*L^0.77*S^-0.385. L en m, S adimensional.
        metrics["kirpich_h"] = (0.01947 * (length_m ** 0.77) * (slope ** -0.385)) / 60.0

        # Kerby: Tc(h)=0.6061*N^0.467*L^0.467*S^-0.234. L en km, S adimensional.
        metrics["kerby_h"] = (
            0.6061
            * (kerby_retardance ** 0.467)
            * (length_km ** 0.467)
            * (slope ** -0.234)
        )

        # Kerby-Kirpich: aproximacion compuesta como suma de escurrimiento superficial y cauce.
        metrics["kerby_kirpich_h"] = metrics["kerby_h"] + metrics["kirpich_h"]

        # California Culverts Practice usa la misma forma metrica de Kirpich.
        metrics["california_h"] = metrics["kirpich_h"]

        # Ven Te Chow: Tc(h)=0.1602*(L/sqrt(S))^0.64. L en km, S adimensional.
        metrics["chow_h"] = 0.1602 * ((length_km / math.sqrt(slope)) ** 0.64)

        # Temez: Tc(h)=0.3*(L/S^0.25)^0.76. L en km, S adimensional.
        metrics["temez_h"] = 0.3 * ((length_km / (slope ** 0.25)) ** 0.76)

        # Johnstone-Cross: Tc(h)=2.6*(L/sqrt(S))^0.5. L en km, S en m/km.
        slope_m_per_km = slope * 1000.0
        metrics["johnstone_h"] = 2.6 * ((length_km / math.sqrt(slope_m_per_km)) ** 0.5)

        # SCS-Ranser: Tc(h)=0.947*(L^3/H)^0.385. L en km, H en m.
        if relief_m and relief_m > 0:
            metrics["scs_ranser_h"] = 0.947 * ((length_km ** 3 / relief_m) ** 0.385)

        # Ventura-Heras: Tc(h)=0.30*(L/S^0.25)^0.75. L en km, S en porcentaje.
        slope_percent = slope * 100.0
        metrics["ventura_h"] = 0.30 * ((length_km / (slope_percent ** 0.25)) ** 0.75)

        # Cuerpo de Ingenieros de EE.UU. (INVIAS): L en km, S adimensional.
        metrics["usace_h"] = 0.28 * ((length_km / (slope ** 0.25)) ** 0.76)

        # Tournon: expresion operativa hasta fijar la variante exacta del documento de referencia.
        metrics["tournon_h"] = 0.1600 * ((length_km / math.sqrt(slope)) ** 0.72)

        # Passini: Tc(h)=0.108*(A*L)^(1/3)/sqrt(S). A en km2, L en km, S adimensional.
        metrics["passini_h"] = 0.108 * ((area_km2 * length_km) ** (1.0 / 3.0)) / math.sqrt(slope)

        valid_methods, reason, method_status = self._applicable_tc_methods(area_km2, length_km, slope, metrics)
        tc_values = [metrics[key] for key, _ in valid_methods]
        if tc_values:
            metrics["average_h"] = sum(tc_values) / len(tc_values)
            metrics["lag_min"] = metrics["average_h"] * 0.6 * 60.0
            metrics["valid_methods"] = ", ".join(name for _, name in valid_methods)
            metrics["valid_count"] = len(valid_methods)
            metrics["range_h"] = f"{min(tc_values):.2f} - {max(tc_values):.2f}"
        metrics["method_status"] = method_status
        metrics["observation"] = self._tc_observation(
            f"{reason} Filtro aplicado solo por area; pendiente observada S={slope:.4f} m/m "
            f"(advertencia, no exclusion). Kerby calculado solo para comparacion con N={kerby_retardance:.2f}.",
            "",
            area_km2,
            length_km,
            slope,
        )
        return metrics

    def _applicable_tc_methods(self, area_km2, length_km, slope, metrics):
        # Filtrado estricto basado en literatura hidrologica para el calculo del promedio.
        # Las ecuaciones fuera de rango o comparativas se conservan en la tabla para analisis.
        criteria = (
            (
                "kirpich_h",
                "Kirpich",
                lambda: 0.0051 <= area_km2 <= 0.433,
                "A=0.0051-0.433 km2",
            ),
            (
                "kerby_kirpich_h",
                "Kerby-Kirpich",
                lambda: 0.65 <= area_km2 <= 388.5,
                "A=0.65-388.5 km2",
            ),
            (
                "temez_h",
                "Temez",
                lambda: area_km2 < 3000.0,
                "A<3000 km2",
            ),
            (
                "johnstone_h",
                "Johnstone-Cross",
                lambda: 64.8 <= area_km2 <= 4206.1,
                "A=64.8-4206.1 km2",
            ),
            (
                "scs_ranser_h",
                "SCS-Ranser",
                lambda: 0.01 <= area_km2 <= 65.0,
                "A=0.01-65.0 km2 (1-6500 ha)",
            ),
            (
                "ventura_h",
                "Ventura-Heras",
                lambda: area_km2 <= 2.0,
                "A<=2.0 km2 (<200 ha)",
            ),
            (
                "usace_h",
                "Cuerpo de Ingenieros EE.UU.",
                lambda: area_km2 < 12000.0,
                "A<12000 km2",
            ),
            (
                "passini_h",
                "Passini",
                lambda: 40.0 <= area_km2 <= 70000.0,
                "A=40-70000 km2",
            ),
        )
        accepted = []
        rejected = []
        status = []
        for key, name, is_applicable, rule in criteria:
            value = metrics.get(key)
            if value is None or value <= 0:
                rejected.append(f"{name} (sin Tc valido)")
                status.append(f"{name}: no calculado")
            elif is_applicable():
                accepted.append((key, name))
                status.append(f"{name}: aplicable ({rule})")
            else:
                rejected.append(f"{name} ({rule})")
                status.append(f"{name}: fuera de rango ({rule})")

        # Metodos puramente individuales o pendientes de calibracion regional
        status.extend(
            (
                "Kerby: comparativo individual de flujo terrestre",
                "California Culverts: comparativo, duplica Kirpich",
                "Ven Te Chow: comparativo, variante pendiente de confirmacion",
                "Tournon: comparativo, formula y unidades pendientes de confirmacion",
            )
        )

        if accepted:
            accepted_text = ", ".join(name for _, name in accepted)
            reason = f"Promedio con metodos aplicables: {accepted_text}."
        else:
            reason = "No hay metodos aplicables con criterios de area documentados."
        if rejected:
            reason = f"{reason} Excluidos: {'; '.join(rejected)}."
        return accepted, reason, "; ".join(status)

    def _tc_observation(self, base, filter_note, area_km2, length_km, slope):
        warnings = []
        if length_km < 0.2:
            warnings.append("longitud de cauce muy corta")
        if slope < 0.001:
            warnings.append("pendiente muy baja")
        if slope > 0.30:
            warnings.append("pendiente muy alta")
        if area_km2 > 3000:
            warnings.append("cuenca grande para formulas empiricas simples")
        notes = [base]
        if filter_note:
            notes.append(filter_note)
        if warnings:
            notes.append(f"Revisar: {', '.join(warnings)}.")
        return " ".join(notes)

    def _drainage_metrics(
        self,
        unit_geom,
        stream_layer,
        dem_layer,
        outlet_point=None,
        processing=None,
        max_flow_method="network",
        external_flowpath_layer=None,
    ):
        target_crs = dem_layer.crs()
        total_length = 0.0
        fallback_length = 0.0
        fallback_geom = None
        count = 0
        graph = {}
        node_points = {}
        tolerance = max(
            0.01,
            max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY())) * 0.5,
        )
        transform = None
        if stream_layer.crs() != target_crs:
            transform = QgsCoordinateTransform(stream_layer.crs(), target_crs, QgsProject.instance())
        for feature in stream_layer.getFeatures():
            geom = QgsGeometry(feature.geometry())
            if transform is not None and geom is not None and not geom.isEmpty():
                geom.transform(transform)
            if geom is None or geom.isEmpty() or not geom.intersects(unit_geom):
                continue
            clipped = geom.intersection(unit_geom)
            if clipped is None or clipped.isEmpty():
                continue
            feature_length = 0.0
            feature_geom = None
            for polyline in self._line_parts(clipped):
                if len(polyline) < 2:
                    continue
                line_geom = QgsGeometry.fromPolylineXY(polyline)
                line_length = line_geom.length()
                if line_length <= 0:
                    continue
                feature_length += line_length
                feature_geom = line_geom
                for point_a, point_b in zip(polyline[:-1], polyline[1:]):
                    segment_length = math.hypot(point_a.x() - point_b.x(), point_a.y() - point_b.y())
                    if segment_length <= 0:
                        continue
                    key_a = self._node_key(point_a, tolerance)
                    key_b = self._node_key(point_b, tolerance)
                    node_points.setdefault(key_a, QgsPointXY(point_a))
                    node_points.setdefault(key_b, QgsPointXY(point_b))
                    graph.setdefault(key_a, []).append((key_b, segment_length))
                    graph.setdefault(key_b, []).append((key_a, segment_length))
            if feature_length <= 0:
                continue
            total_length += feature_length
            count += 1
            if feature_length > fallback_length:
                fallback_length = feature_length
                fallback_geom = QgsGeometry(feature_geom) if feature_geom is not None else QgsGeometry(clipped)

        inferred_outlet = self._infer_unit_outlet_point(unit_geom, graph, node_points, dem_layer, outlet_point)
        main_length = 0.0
        main_geom = None
        used_raster_method = False

        if external_flowpath_layer is not None:
            external_length, external_geom = self._external_flowpath_for_unit(
                unit_geom,
                external_flowpath_layer,
                target_crs,
                inferred_outlet,
                dem_layer,
                tolerance * 8.0,
            )
            if external_geom is not None and not external_geom.isEmpty() and external_length > 0:
                main_length = external_length
                main_geom = external_geom
                self._log(f"Maximo recorrido externo: {main_length / 1000.0:.3f} km")
            else:
                self._log("No se encontro longest flowpath externo dentro de la unidad; se usara respaldo vectorial.")

        if main_geom is None and max_flow_method == "d8":
            main_geom = self._longest_flow_path_d8_internal(dem_layer, unit_geom, inferred_outlet)
            if main_geom is not None and not main_geom.isEmpty():
                main_length = main_geom.length()
                used_raster_method = True
                self._log(f"Maximo recorrido por D8 interno: {main_length / 1000.0:.3f} km")
                network_length, network_geom = self._longest_flow_path(graph, node_points, dem_layer, inferred_outlet)
                if (
                    network_geom is not None
                    and not network_geom.isEmpty()
                    and network_length > 0
                    and self._d8_path_looks_too_short(unit_geom, inferred_outlet, main_length, network_length)
                ):
                    self._log(
                        "D8 interno genero una ruta corta para la unidad; "
                        "se usara la red vectorial como respaldo para evitar un recorrido truncado."
                    )
                    main_length = network_length
                    main_geom = network_geom
                    used_raster_method = False
        if main_geom is None:
            main_length, main_geom = self._longest_flow_path(graph, node_points, dem_layer, inferred_outlet)
        if main_geom is None:
            main_length = fallback_length
            main_geom = fallback_geom
        if main_geom is not None and not main_geom.isEmpty() and not used_raster_method:
            main_geom = self._extend_path_to_boundary(unit_geom, main_geom, dem_layer)
            main_length = main_geom.length()
        return {
            "total_km": total_length / 1000.0,
            "main_km": main_length / 1000.0,
            "count": count,
            "main_geom": main_geom,
        }

    def _external_flowpath_for_unit(
        self,
        unit_geom,
        flowpath_layer,
        target_crs,
        outlet_point=None,
        dem_layer=None,
        snap_tolerance=1.0,
    ):
        if flowpath_layer is None or not flowpath_layer.isValid():
            return 0.0, None
        transform = None
        if flowpath_layer.crs() != target_crs:
            transform = QgsCoordinateTransform(flowpath_layer.crs(), target_crs, QgsProject.instance())

        best = None
        near_tolerance = max(0.01, snap_tolerance * 12.0)
        for feature in flowpath_layer.getFeatures():
            geom = QgsGeometry(feature.geometry())
            if geom is None or geom.isEmpty():
                continue
            if transform is not None:
                geom.transform(transform)
            if not geom.intersects(unit_geom):
                continue
            clipped = geom.intersection(unit_geom)
            if clipped is None or clipped.isEmpty():
                continue
            for polyline in self._line_parts(clipped):
                if len(polyline) < 2:
                    continue
                candidate = QgsGeometry.fromPolylineXY([QgsPointXY(point) for point in polyline])
                candidate = self._orient_external_flowpath(candidate, outlet_point, dem_layer, snap_tolerance)
                length = candidate.length() if candidate is not None and not candidate.isEmpty() else 0.0
                if length <= 0:
                    continue
                endpoint_distance = 0.0
                near_score = 1
                if outlet_point is not None:
                    points = self._line_parts(candidate)
                    if points:
                        line_points = points[0]
                        endpoint_distance = min(
                            self._point_distance(QgsPointXY(line_points[0]), outlet_point),
                            self._point_distance(QgsPointXY(line_points[-1]), outlet_point),
                        )
                        near_score = 1 if endpoint_distance <= near_tolerance else 0
                score = (near_score, length, -endpoint_distance)
                if best is None or score > best[0]:
                    best = (score, length, QgsGeometry(candidate))
        if best is None:
            return 0.0, None
        return best[1], best[2]

    def _orient_external_flowpath(self, geom, outlet_point=None, dem_layer=None, snap_tolerance=1.0):
        parts = self._line_parts(geom)
        if not parts:
            return geom
        points = [QgsPointXY(point) for point in max(parts, key=self._polyline_length)]
        if len(points) < 2:
            return geom

        if outlet_point is not None:
            first_distance = self._point_distance(points[0], outlet_point)
            last_distance = self._point_distance(points[-1], outlet_point)
            if first_distance < last_distance:
                points = list(reversed(points))
            end_distance = self._point_distance(points[-1], outlet_point)
            if 0.01 < end_distance <= max(0.01, snap_tolerance):
                points.append(QgsPointXY(outlet_point))
            return QgsGeometry.fromPolylineXY(points)

        if dem_layer is not None:
            first_z = self._sample_dem_point(dem_layer, points[0])
            last_z = self._sample_dem_point(dem_layer, points[-1])
            if first_z is not None and last_z is not None and first_z < last_z:
                points = list(reversed(points))
        return QgsGeometry.fromPolylineXY(points)

    def _snyder_centroid_length(self, main_geom, centroid_point, outlet_point=None):
        if main_geom is None or main_geom.isEmpty() or centroid_point is None:
            return None, None
        parts = self._line_parts(main_geom)
        if not parts:
            return None, None
        points = [QgsPointXY(point) for point in max(parts, key=self._polyline_length)]
        if len(points) < 2:
            return None, None

        if outlet_point is not None:
            first_distance = self._point_distance(points[0], outlet_point)
            last_distance = self._point_distance(points[-1], outlet_point)
            if first_distance < last_distance:
                points = list(reversed(points))

        total_length = self._polyline_length(points)
        if total_length <= 0:
            return None, None

        centroid = QgsPointXY(centroid_point)
        cumulative = 0.0
        best = None
        for index, (point_a, point_b) in enumerate(zip(points[:-1], points[1:])):
            segment_length = self._point_distance(point_a, point_b)
            if segment_length <= 0:
                continue
            projected, fraction = self._project_point_to_segment(centroid, point_a, point_b)
            distance = self._point_distance(centroid, projected)
            along = cumulative + fraction * segment_length
            if best is None or distance < best["distance"]:
                best = {
                    "distance": distance,
                    "index": index,
                    "point": projected,
                    "along": along,
                }
            cumulative += segment_length

        if best is None:
            return None, None

        length_to_outlet = max(0.0, total_length - best["along"])
        segment_points = [best["point"]]
        for point in points[best["index"] + 1 :]:
            if self._point_distance(segment_points[-1], point) > 0.001:
                segment_points.append(QgsPointXY(point))
        if len(segment_points) < 2:
            return length_to_outlet / 1000.0, None
        return length_to_outlet / 1000.0, QgsGeometry.fromPolylineXY(segment_points)

    def _project_point_to_segment(self, point, point_a, point_b):
        dx = point_b.x() - point_a.x()
        dy = point_b.y() - point_a.y()
        denominator = dx * dx + dy * dy
        if denominator <= 0:
            return QgsPointXY(point_a), 0.0
        fraction = ((point.x() - point_a.x()) * dx + (point.y() - point_a.y()) * dy) / denominator
        fraction = max(0.0, min(1.0, fraction))
        return QgsPointXY(point_a.x() + fraction * dx, point_a.y() + fraction * dy), fraction

    def _polyline_length(self, points):
        return sum(self._point_distance(point_a, point_b) for point_a, point_b in zip(points[:-1], points[1:]))

    def _infer_unit_outlet_point(self, unit_geom, graph, node_points, dem_layer, explicit_outlet_point=None):
        if explicit_outlet_point is not None:
            local_outlet = self._point_on_unit_for_outlet(unit_geom, explicit_outlet_point)
            if graph and node_points:
                tolerance = max(
                    0.01,
                    max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY())) * 1.5,
                )
                candidate_nodes = self._graph_boundary_nodes(unit_geom, node_points, tolerance)
                if not candidate_nodes:
                    candidate_nodes = set(node_points.keys())
                outlet_node = self._nearest_node(local_outlet, node_points, candidate_nodes)
                if outlet_node in node_points:
                    return QgsPointXY(node_points[outlet_node])
            return local_outlet
        if graph and node_points:
            tolerance = max(
                0.01,
                max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY())) * 1.5,
            )
            candidate_nodes = self._graph_boundary_nodes(unit_geom, node_points, tolerance)
            if not candidate_nodes:
                candidate_nodes = set(node_points.keys())
            best_node = self._lowest_node(candidate_nodes, node_points, dem_layer)
            if best_node in node_points:
                return QgsPointXY(node_points[best_node])
        return self._lowest_boundary_point(unit_geom, dem_layer)

    def _graph_boundary_nodes(self, unit_geom, node_points, tolerance):
        nodes = set()
        try:
            boundary = unit_geom.boundary()
            for node, point in node_points.items():
                point_geom = QgsGeometry.fromPointXY(point)
                if boundary.distance(point_geom) <= tolerance:
                    nodes.add(node)
        except Exception:
            return set()
        return nodes

    def _point_on_unit_for_outlet(self, unit_geom, outlet_point):
        outlet_geom = QgsGeometry.fromPointXY(outlet_point)
        try:
            if unit_geom.contains(outlet_geom) or unit_geom.touches(outlet_geom):
                return QgsPointXY(outlet_point)
        except Exception:
            pass
        try:
            boundary_point = unit_geom.boundary().nearestPoint(outlet_geom)
            if boundary_point is not None and not boundary_point.isEmpty():
                return QgsPointXY(boundary_point.asPoint())
        except Exception:
            pass
        try:
            nearest = unit_geom.nearestPoint(outlet_geom)
            if nearest is not None and not nearest.isEmpty():
                return QgsPointXY(nearest.asPoint())
        except Exception:
            pass
        return QgsPointXY(outlet_point)

    def _lowest_boundary_point(self, geom, dem_layer):
        try:
            points = [QgsPointXY(vertex) for vertex in geom.boundary().vertices()]
        except Exception:
            points = []
        if not points:
            try:
                points = [QgsPointXY(vertex) for vertex in geom.vertices()]
            except Exception:
                points = []
        if not points:
            return None
        max_points = 8000
        if len(points) > max_points:
            step = max(1, math.ceil(len(points) / max_points))
            points = points[::step]
        elevations = []
        for point in points:
            elevation = self._sample_dem_point(dem_layer, point)
            if elevation is not None:
                elevations.append((elevation, point))
        if elevations:
            elevations.sort(key=lambda item: item[0])
            return QgsPointXY(elevations[0][1])
        return min(points, key=lambda point: point.y())

    def _longest_flow_path_d8_internal(self, dem_layer, unit_geom, outlet_point):
        cell_size = max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY())) or 1.0
        analysis_geom = QgsGeometry(unit_geom)
        grid = self._raster_cells_in_geometry(dem_layer, analysis_geom, dem_layer.crs(), max_samples=700000)
        if not grid or len(grid["values"]) < 2:
            self._log("D8 interno omitido: no se pudieron leer celdas suficientes del DEM.")
            return None

        values = grid["values"]
        points = grid["points"]
        start_indices = self._d8_start_indices_inside_unit(values, points, unit_geom)
        if not start_indices:
            self._log("D8 interno omitido: no se encontraron celdas de inicio dentro de la unidad.")
            return None
        outlet_index = self._d8_outlet_index(values, points, outlet_point)
        if outlet_index is None:
            self._log("D8 interno omitido: no se pudo definir celda de salida.")
            return None

        terminal_indices = self._d8_terminal_indices(values, points, outlet_index, outlet_point, cell_size)
        receivers = self._d8_receivers(values, points, terminal_indices)
        distance_cache = {
            index: self._point_distance(points[index], outlet_point) if outlet_point is not None else 0.0
            for index in terminal_indices
        }
        best_index = None
        best_distance = 0.0
        valid_paths = 0
        for index in start_indices:
            distance = self._d8_distance_to_terminal(index, receivers, points, terminal_indices, distance_cache)
            if distance is None:
                continue
            valid_paths += 1
            if distance > best_distance:
                best_distance = distance
                best_index = index

        if best_index is None or best_distance <= 0:
            self._log("D8 interno no encontro una ruta completa hacia la salida; se usara otro metodo.")
            return None

        total_cells = len(values)
        if valid_paths < max(10, total_cells * 0.10):
            self._log(
                "D8 interno encontro pocas celdas conectadas a la salida; "
                "revisa si el DEM esta rellenado o si la salida cae fuera del cauce."
            )

        line_points = self._d8_path_points(best_index, receivers, points, terminal_indices)
        if len(line_points) < 2:
            return None
        if outlet_point is not None:
            last = line_points[-1]
            snap_distance = max(
                5.0,
                max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY())) * 2.0,
            )
            if 0.01 < self._point_distance(last, outlet_point) <= snap_distance * 3.0:
                line_points.append(QgsPointXY(outlet_point))

        line = QgsGeometry.fromPolylineXY(line_points)
        clipped = line.intersection(unit_geom)
        clipped_line = self._longest_line_from_geometry(clipped)
        if clipped_line is None or clipped_line.isEmpty():
            clipped_line = self._longest_line_from_geometry(line)
        if clipped_line is None or clipped_line.isEmpty():
            return None

        extended = self._extend_path_to_boundary(unit_geom, clipped_line)
        oriented = self._orient_line_from_headwater_to_outlet(
            extended,
            QgsPointXY(points[best_index]),
            None,
            max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY())) * 3.0,
        )
        return self._extend_path_to_outlet_if_inside(unit_geom, oriented, outlet_point, cell_size * 3.0)

    def _d8_start_indices_inside_unit(self, values, points, unit_geom):
        start_indices = []
        for index in values:
            point_geom = QgsGeometry.fromPointXY(points[index])
            try:
                if unit_geom.contains(point_geom) or unit_geom.touches(point_geom):
                    start_indices.append(index)
            except Exception:
                continue
        return start_indices

    def _d8_path_looks_too_short(self, unit_geom, outlet_point, path_length, network_length):
        if outlet_point is None or path_length <= 0:
            return False
        farthest = self._farthest_boundary_point(unit_geom, outlet_point)
        if farthest is None:
            return False
        straight_distance = self._point_distance(farthest, outlet_point)
        suspicious_by_geometry = straight_distance > 0 and path_length < straight_distance * 0.55
        suspicious_by_network = network_length and network_length > 0 and path_length < network_length * 0.65
        return suspicious_by_geometry or suspicious_by_network

    def _d8_outlet_index(self, values, points, outlet_point):
        if not values:
            return None
        if outlet_point is not None:
            return min(values, key=lambda index: self._point_distance(points[index], outlet_point))
        boundary_indices = self._d8_boundary_indices(values)
        candidates = boundary_indices or list(values.keys())
        return min(candidates, key=lambda index: values[index])

    def _d8_boundary_indices(self, values):
        boundary = []
        for row, col in values:
            is_boundary = False
            for row_delta in (-1, 0, 1):
                for col_delta in (-1, 0, 1):
                    if row_delta == 0 and col_delta == 0:
                        continue
                    if (row + row_delta, col + col_delta) not in values:
                        is_boundary = True
                        break
                if is_boundary:
                    break
            if is_boundary:
                boundary.append((row, col))
        return boundary

    def _d8_terminal_indices(self, values, points, outlet_index, outlet_point, cell_size):
        terminals = {outlet_index}
        if outlet_point is None:
            return terminals
        tolerance = max(cell_size * 1.5, 1.0)
        ranked = sorted(values, key=lambda index: self._point_distance(points[index], outlet_point))
        for index in ranked[:9]:
            if self._point_distance(points[index], outlet_point) <= tolerance * 2.0:
                terminals.add(index)
        return terminals

    def _nearest_d8_terminal_distance(self, index, points, terminal_indices):
        return min(self._point_distance(points[index], points[terminal]) for terminal in terminal_indices)

    def _d8_receivers(self, values, points, terminal_indices):
        receivers = {}
        epsilon = 1e-8
        for index, value in values.items():
            if index in terminal_indices:
                continue
            current_point = points[index]
            current_terminal_distance = self._nearest_d8_terminal_distance(index, points, terminal_indices)
            best_neighbor = None
            best_score = None
            row, col = index
            for row_delta in (-1, 0, 1):
                for col_delta in (-1, 0, 1):
                    if row_delta == 0 and col_delta == 0:
                        continue
                    neighbor = (row + row_delta, col + col_delta)
                    if neighbor not in values:
                        continue
                    neighbor_point = points[neighbor]
                    move_distance = self._point_distance(current_point, neighbor_point)
                    if move_distance <= 0:
                        continue
                    neighbor_terminal_distance = self._nearest_d8_terminal_distance(neighbor, points, terminal_indices)
                    drop = value - values[neighbor]
                    if neighbor in terminal_indices:
                        score = (4, -max(0.0, -drop), -move_distance)
                    elif drop > epsilon:
                        score = (3, drop / move_distance, current_terminal_distance - neighbor_terminal_distance)
                    elif abs(drop) <= epsilon and neighbor_terminal_distance < current_terminal_distance:
                        score = (2, current_terminal_distance - neighbor_terminal_distance, -move_distance)
                    else:
                        continue
                    if best_score is None or score > best_score:
                        best_score = score
                        best_neighbor = neighbor

            if best_neighbor is not None:
                receivers[index] = best_neighbor
        return receivers

    def _d8_distance_to_terminal(self, start, receivers, points, terminal_indices, distance_cache):
        if start in distance_cache:
            return distance_cache[start]
        stack = []
        visiting = set()
        current = start
        while current not in distance_cache:
            if current in visiting or current not in receivers:
                for index in stack:
                    distance_cache[index] = None
                return None
            visiting.add(current)
            stack.append(current)
            current = receivers[current]

        distance = distance_cache[current]
        if distance is None:
            for index in stack:
                distance_cache[index] = None
            return None
        for index in reversed(stack):
            receiver = receivers[index]
            distance += self._point_distance(points[index], points[receiver])
            distance_cache[index] = distance
        return distance_cache[start]

    def _d8_path_points(self, start, receivers, points, terminal_indices):
        path = [QgsPointXY(points[start])]
        current = start
        visited = {start}
        guard = 0
        while current not in terminal_indices and guard < 500000:
            current = receivers.get(current)
            if current is None or current in visited:
                return []
            path.append(QgsPointXY(points[current]))
            visited.add(current)
            guard += 1
        return path

    def _point_distance(self, point_a, point_b):
        return math.hypot(point_a.x() - point_b.x(), point_a.y() - point_b.y())

    def _raster_cells_in_geometry(self, raster_layer, geom, target_crs, max_samples=1500000):
        provider = raster_layer.dataProvider()
        search_geom = QgsGeometry(geom)
        transform_to_target = None
        if raster_layer.crs() != target_crs:
            transform_to_raster = QgsCoordinateTransform(target_crs, raster_layer.crs(), QgsProject.instance())
            search_geom.transform(transform_to_raster)
            transform_to_target = QgsCoordinateTransform(raster_layer.crs(), target_crs, QgsProject.instance())

        extent = search_geom.boundingBox().intersect(raster_layer.extent())
        if extent.isEmpty():
            return None
        pixel_x = abs(raster_layer.rasterUnitsPerPixelX()) or 1.0
        pixel_y = abs(raster_layer.rasterUnitsPerPixelY()) or 1.0
        width = max(1, int(math.ceil(extent.width() / pixel_x)))
        height = max(1, int(math.ceil(extent.height() / pixel_y)))
        cells = width * height
        scale = math.sqrt(cells / max_samples) if cells > max_samples else 1.0
        sample_width = max(1, int(width / scale))
        sample_height = max(1, int(height / scale))
        block = provider.block(1, extent, sample_width, sample_height)
        if block is None:
            return None

        values = {}
        points = {}
        dx = extent.width() / sample_width
        dy = extent.height() / sample_height
        for row in range(sample_height):
            y = extent.yMaximum() - (row + 0.5) * dy
            for col in range(sample_width):
                x = extent.xMinimum() + (col + 0.5) * dx
                point = QgsPointXY(x, y)
                point_geom = QgsGeometry.fromPointXY(point)
                if not (search_geom.contains(point_geom) or search_geom.touches(point_geom)):
                    continue
                if hasattr(block, "isNoData") and block.isNoData(row, col):
                    continue
                value = block.value(row, col)
                if value is None:
                    continue
                value = float(value)
                if math.isnan(value):
                    continue
                output_point = QgsPointXY(point)
                if transform_to_target is not None:
                    target_point_geom = QgsGeometry.fromPointXY(output_point)
                    target_point_geom.transform(transform_to_target)
                    output_point = QgsPointXY(target_point_geom.asPoint())
                index = (row, col)
                values[index] = value
                points[index] = output_point
        return {
            "values": values,
            "points": points,
            "pixel_x": extent.width() / sample_width if sample_width else pixel_x,
            "pixel_y": extent.height() / sample_height if sample_height else pixel_y,
        }

    def _farthest_boundary_point(self, geom, reference_point):
        try:
            points = [QgsPointXY(vertex) for vertex in geom.boundary().vertices()]
        except Exception:
            points = []
        if not points:
            try:
                points = [QgsPointXY(vertex) for vertex in geom.vertices()]
            except Exception:
                points = []
        if not points:
            return None
        max_points = 6000
        if len(points) > max_points:
            step = max(1, math.ceil(len(points) / max_points))
            points = points[::step]
        return max(points, key=lambda point: math.hypot(point.x() - reference_point.x(), point.y() - reference_point.y()))

    def _longest_line_from_geometry(self, geom):
        if geom is None or geom.isEmpty():
            return None
        best_line = None
        best_length = 0.0
        for polyline in self._line_parts(geom):
            if len(polyline) < 2:
                continue
            line = QgsGeometry.fromPolylineXY([QgsPointXY(point) for point in polyline])
            length = line.length()
            if length > best_length:
                best_length = length
                best_line = line
        return best_line

    def _orient_line_from_headwater_to_outlet(self, geom, headwater_point, outlet_point, snap_tolerance):
        try:
            points = geom.asPolyline()
            if len(points) < 2:
                return geom
            first = QgsPointXY(points[0])
            last = QgsPointXY(points[-1])
            first_score = math.hypot(first.x() - headwater_point.x(), first.y() - headwater_point.y())
            last_score = math.hypot(last.x() - headwater_point.x(), last.y() - headwater_point.y())
            if last_score < first_score:
                points = list(reversed(points))
            end = QgsPointXY(points[-1])
            if outlet_point is not None:
                outlet_distance = math.hypot(end.x() - outlet_point.x(), end.y() - outlet_point.y())
                if 0.01 < outlet_distance <= snap_tolerance:
                    points.append(QgsPointXY(outlet_point))
            return QgsGeometry.fromPolylineXY([QgsPointXY(point) for point in points])
        except Exception:
            return geom

    def _line_parts(self, geom):
        if geom is None or geom.isEmpty():
            return []
        try:
            if geom.isMultipart():
                return [part for part in geom.asMultiPolyline() if len(part) >= 2]
            polyline = geom.asPolyline()
            return [polyline] if len(polyline) >= 2 else []
        except Exception:
            pass
        parts = []
        try:
            for part in geom.asGeometryCollection():
                parts.extend(self._line_parts(part))
        except Exception:
            pass
        return parts

    def _node_key(self, point, tolerance):
        return (int(round(point.x() / tolerance)), int(round(point.y() / tolerance)))

    def _longest_flow_path(self, graph, node_points, dem_layer, outlet_point=None):
        if not graph or not node_points:
            return 0.0, None
        if outlet_point is not None:
            outlet = self._nearest_node(outlet_point, node_points)
            component = self._component_from_node(graph, outlet)
            distances, parents = self._dijkstra(graph, outlet, component)
            if not distances:
                return 0.0, None
            farthest = max(distances, key=distances.get)
            return distances[farthest], self._path_geometry(farthest, outlet, parents, node_points)

        best_length = 0.0
        best_path = None
        for component in self._graph_components(graph):
            if len(component) < 2:
                continue
            outlet = self._lowest_node(component, node_points, dem_layer)
            distances, parents = self._dijkstra(graph, outlet, component)
            if not distances:
                continue
            farthest = max(distances, key=distances.get)
            if distances[farthest] > best_length:
                best_length = distances[farthest]
                best_path = self._path_geometry(farthest, outlet, parents, node_points)
        return best_length, best_path

    def _nearest_node(self, point, node_points, allowed_nodes=None):
        nodes = allowed_nodes if allowed_nodes is not None else node_points.keys()
        return min(
            nodes,
            key=lambda node: math.hypot(node_points[node].x() - point.x(), node_points[node].y() - point.y()),
        )

    def _component_from_node(self, graph, start):
        visited = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor, _ in graph.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        return visited

    def _extend_path_to_boundary(self, unit_geom, path_geom, dem_layer=None):
        try:
            points = path_geom.asPolyline()
            if len(points) < 2:
                return path_geom
            
            if dem_layer is None:
                boundary = unit_geom.boundary()
                boundary_point_geom = boundary.nearestPoint(QgsGeometry.fromPointXY(QgsPointXY(points[0])))
                if boundary_point_geom is None or boundary_point_geom.isEmpty():
                    return path_geom
                return QgsGeometry.fromPolylineXY([QgsPointXY(boundary_point_geom.asPoint())] + [QgsPointXY(p) for p in points])

            # 1. Encontrar el punto MAS ALTO en el borde de la cuenca
            boundary = unit_geom.boundary()
            vertices = [QgsPointXY(v) for v in boundary.vertices()]
            
            best_boundary_pt = None
            max_z = -99999
            
            step = max(1, len(vertices) // 1500)
            for v in vertices[::step]:
                z = self._sample_dem_point(dem_layer, v)
                if z is not None and z > max_z:
                    max_z = z
                    best_boundary_pt = v
                    
            if best_boundary_pt is None:
                return path_geom
                
            # 2. Trazar la gota CUESTA ABAJO hasta chocar con el cauce
            cell_size = max(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY()))
            move_step = cell_size * 0.75 
            
            downhill_path = [best_boundary_pt]
            current_pt = best_boundary_pt
            
            stream_geom = QgsGeometry.fromPolylineXY(points)
            stream_buffer = stream_geom.buffer(cell_size * 1.5, 5) 
            
            for _ in range(8000): 
                if stream_buffer.contains(QgsGeometry.fromPointXY(current_pt)):
                    break 
                    
                current_z = self._sample_dem_point(dem_layer, current_pt)
                if current_z is None:
                    break
                    
                next_pt = None
                min_z = current_z
                
                for dx in [-move_step, 0, move_step]:
                    for dy in [-move_step, 0, move_step]:
                        if dx == 0 and dy == 0:
                            continue
                            
                        neighbor = QgsPointXY(current_pt.x() + dx, current_pt.y() + dy)
                        z = self._sample_dem_point(dem_layer, neighbor)
                        
                        if z is not None and z < min_z:
                            min_z = z
                            next_pt = neighbor
                            
                if next_pt is None:
                    break 
                    
                downhill_path.append(next_pt)
                current_pt = next_pt
                
            # 3. Empalmar las dos lineas limpiamente
            end_of_downhill = downhill_path[-1]
            min_dist = 999999
            insert_idx = 0
            
            for i, spt in enumerate(points):
                dist = end_of_downhill.sqrDist(spt)
                if dist < min_dist:
                    min_dist = dist
                    insert_idx = i
                    
            final_points = downhill_path + points[insert_idx:]
            return QgsGeometry.fromPolylineXY(final_points)
            
        except Exception as e:
            self._log(f"Error en trazado cuesta abajo: {e}")
            return path_geom

    def _extend_path_to_outlet_if_inside(self, unit_geom, path_geom, outlet_point, max_distance):
        if path_geom is None or path_geom.isEmpty() or outlet_point is None:
            return path_geom
        try:
            points = path_geom.asPolyline()
            if len(points) < 2:
                return path_geom
            end = QgsPointXY(points[-1])
            distance = self._point_distance(end, outlet_point)
            if distance <= 0.01 or distance > max_distance:
                return path_geom
            segment = QgsGeometry.fromPolylineXY([end, QgsPointXY(outlet_point)])
            tolerance = max(0.01, min(max_distance * 0.05, 5.0))
            if not self._segment_stays_inside(unit_geom, segment, tolerance):
                return path_geom
            return QgsGeometry.fromPolylineXY([QgsPointXY(point) for point in points] + [QgsPointXY(outlet_point)])
        except Exception:
            return path_geom

    def _extend_path_to_outlet_if_inside(self, unit_geom, path_geom, outlet_point, max_distance):
        if path_geom is None or path_geom.isEmpty() or outlet_point is None:
            return path_geom
        try:
            points = path_geom.asPolyline()
            if len(points) < 2:
                return path_geom
            end = QgsPointXY(points[-1])
            distance = self._point_distance(end, outlet_point)
            if distance <= 0.01 or distance > max_distance:
                return path_geom
            segment = QgsGeometry.fromPolylineXY([end, QgsPointXY(outlet_point)])
            tolerance = max(0.01, min(max_distance * 0.05, 5.0))
            if not self._segment_stays_inside(unit_geom, segment, tolerance):
                return path_geom
            return QgsGeometry.fromPolylineXY([QgsPointXY(point) for point in points] + [QgsPointXY(outlet_point)])
        except Exception:
            return path_geom

    def _segment_stays_inside(self, container_geom, segment_geom, tolerance=0.01):
        try:
            container = QgsGeometry(container_geom)
            if tolerance and tolerance > 0:
                buffered = container.buffer(tolerance, 4)
                if buffered is not None and not buffered.isEmpty():
                    container = buffered
            if container.contains(segment_geom):
                return True
            outside = segment_geom.difference(container)
            if outside is None or outside.isEmpty():
                return True
            try:
                return outside.length() <= max(0.01, tolerance * 0.25)
            except Exception:
                return False
        except Exception:
            return False

    def _graph_components(self, graph):
        visited = set()
        components = []
        for node in graph:
            if node in visited:
                continue
            stack = [node]
            component = set()
            visited.add(node)
            while stack:
                current = stack.pop()
                component.add(current)
                for neighbor, _ in graph.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            components.append(component)
        return components

    def _lowest_node(self, component, node_points, dem_layer):
        elevations = []
        for node in component:
            elevation = self._sample_dem_point(dem_layer, node_points[node])
            if elevation is not None:
                elevations.append((elevation, node))
        if elevations:
            elevations.sort(key=lambda item: item[0])
            return elevations[0][1]
        return min(component, key=lambda node: node_points[node].y())

    def _dijkstra(self, graph, start, allowed_nodes):
        distances = {start: 0.0}
        parents = {}
        heap = [(0.0, start)]
        while heap:
            distance, node = heapq.heappop(heap)
            if distance > distances.get(node, float("inf")):
                continue
            for neighbor, weight in graph.get(node, []):
                if neighbor not in allowed_nodes:
                    continue
                new_distance = distance + weight
                if new_distance < distances.get(neighbor, float("inf")):
                    distances[neighbor] = new_distance
                    parents[neighbor] = node
                    heapq.heappush(heap, (new_distance, neighbor))
        return distances, parents

    def _path_geometry(self, start, end, parents, node_points):
        if start == end:
            return None
        points = [QgsPointXY(node_points[start])]
        current = start
        guard = 0
        while current != end and guard < 100000:
            current = parents.get(current)
            if current is None:
                return None
            points.append(QgsPointXY(node_points[current]))
            guard += 1
        if len(points) < 2:
            return None
        return QgsGeometry.fromPolylineXY(points)

    def _sample_dem_point(self, dem_layer, point):
        try:
            result = dem_layer.dataProvider().sample(point, 1)
            if isinstance(result, tuple):
                value, ok = result
                if not ok:
                    return None
            else:
                value = result
            if value is None:
                return None
            value = float(value)
            if math.isnan(value):
                return None
            return value
        except Exception:
            return None

    def _save_line_results(self, processing, rows, geometry_key, length_key, output_path, layer_name, crs, add_to_project=True):
        line_rows = [row for row in rows if row.get(geometry_key) is not None and not row[geometry_key].isEmpty()]
        if not line_rows:
            return
        layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", layer_name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes(
            [
                QgsField("tipo", QVariant.String),
                QgsField("codigo", QVariant.String),
                QgsField("long_km", QVariant.Double),
            ]
        )
        layer.updateFields()
        for row in line_rows:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(row[geometry_key])
            feature.setAttributes([row.get("tipo"), row.get("codigo"), row.get(length_key)])
            provider.addFeature(feature)
        layer.updateExtents()
        output = prepare_output_path(output_path, self._log)
        result = processing.run("native:savefeatures", {"INPUT": layer, "OUTPUT": output})
        if add_to_project:
            add_or_replace_layer(result["OUTPUT"], layer_name, "vector", self._log)
        else:
            remove_project_layers_by_name(layer_name)

    def _sample_dem_values(self, dem_layer, geom, max_samples=40000):
        provider = dem_layer.dataProvider()
        extent = geom.boundingBox().intersect(dem_layer.extent())
        if extent.isEmpty():
            return []
        pixel_x = abs(dem_layer.rasterUnitsPerPixelX())
        pixel_y = abs(dem_layer.rasterUnitsPerPixelY())
        width = max(1, int(math.ceil(extent.width() / pixel_x)))
        height = max(1, int(math.ceil(extent.height() / pixel_y)))
        cells = width * height
        scale = math.sqrt(cells / max_samples) if cells > max_samples else 1.0
        sample_width = max(1, int(width / scale))
        sample_height = max(1, int(height / scale))
        block = provider.block(1, extent, sample_width, sample_height)
        if block is None:
            return []
        values = []
        dx = extent.width() / sample_width
        dy = extent.height() / sample_height
        for row in range(sample_height):
            y = extent.yMaximum() - (row + 0.5) * dy
            for col in range(sample_width):
                x = extent.xMinimum() + (col + 0.5) * dx
                point_geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                if not geom.contains(point_geom):
                    continue
                if hasattr(block, "isNoData") and block.isNoData(row, col):
                    continue
                value = block.value(row, col)
                if value is None or math.isnan(float(value)):
                    continue
                values.append(float(value))
        return values

    def _create_hypsometric_graph(self, dem_layer, geom, graph_dir, code, integral):
        values = self._sample_dem_values(dem_layer, geom)
        if len(values) < 5:
            return None, []
        values.sort()
        min_value = values[0]
        max_value = values[-1]
        relief = max_value - min_value
        if relief <= 0:
            return None, []

        points = []
        steps = min(100, len(values))
        for index in range(steps):
            pos = int(index * (len(values) - 1) / max(1, steps - 1))
            elevation = values[pos]
            relative_elevation = (elevation - min_value) / relief
            relative_area_above = (len(values) - pos) / len(values)
            points.append((relative_area_above, relative_elevation))
        points.sort()

        path = graph_dir / f"{self._safe_filename(code)}_curva_hipsometrica.png"
        self._draw_hypsometric_graph(path, code, points, integral)
        return path, points

    def _draw_hypsometric_graph(self, path, title, points, integral):
        image = QImage(900, 620, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        margin_left, margin_top, margin_right, margin_bottom = 90, 70, 40, 90
        plot_w = image.width() - margin_left - margin_right
        plot_h = image.height() - margin_top - margin_bottom

        painter.setPen(QPen(QColor("#222222"), 2))
        painter.setFont(QFont("Arial", 15, QFont.Bold))
        painter.drawText(0, 20, image.width(), 30, Qt.AlignCenter, f"Curva hipsometrica - {title}")
        painter.setFont(QFont("Arial", 10))
        if integral is not None:
            painter.drawText(margin_left, 50, f"Integral hipsometrica: {integral:.4f}")

        painter.setPen(QPen(QColor("#333333"), 2))
        x0, y0 = margin_left, image.height() - margin_bottom
        painter.drawLine(x0, y0, x0 + plot_w, y0)
        painter.drawLine(x0, y0, x0, margin_top)

        painter.setPen(QPen(QColor("#dddddd"), 1))
        for tick in range(0, 11):
            x = x0 + tick * plot_w / 10
            y = y0 - tick * plot_h / 10
            painter.drawLine(int(x), y0, int(x), margin_top)
            painter.drawLine(x0, int(y), x0 + plot_w, int(y))

        painter.setPen(QPen(QColor("#333333"), 1))
        painter.setFont(QFont("Arial", 9))
        for tick in range(0, 11):
            label = f"{tick / 10:.1f}"
            x = x0 + tick * plot_w / 10
            y = y0 - tick * plot_h / 10
            painter.drawText(int(x) - 12, y0 + 20, label)
            painter.drawText(x0 - 42, int(y) + 5, label)

        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(0, image.height() - 42, image.width(), 30, Qt.AlignCenter, "Area relativa sobre la cota")
        painter.save()
        painter.translate(28, margin_top + plot_h / 2 + 80)
        painter.rotate(-90)
        painter.drawText(0, 0, "Elevacion relativa")
        painter.restore()

        painter.setPen(QPen(QColor("#1f78b4"), 3))
        last = None
        for x_rel, y_rel in points:
            x = int(x0 + x_rel * plot_w)
            y = int(y0 - y_rel * plot_h)
            if last is not None:
                painter.drawLine(last[0], last[1], x, y)
            last = (x, y)
        painter.end()
        image.save(str(path), "PNG")

    def _draw_combined_hypsometric_graph(self, path, curves):
        curves = [curve for curve in curves if curve.get("points")]
        if not curves:
            return
        image = QImage(1000, 700, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        margin_left, margin_top, margin_right, margin_bottom = 90, 70, 220, 90
        plot_w = image.width() - margin_left - margin_right
        plot_h = image.height() - margin_top - margin_bottom
        x0, y0 = margin_left, image.height() - margin_bottom
        colors = ["#1f78b4", "#33a02c", "#e31a1c", "#ff7f00", "#6a3d9a", "#b15928", "#a6cee3", "#fb9a99"]

        painter.setPen(QPen(QColor("#222222"), 2))
        painter.setFont(QFont("Arial", 15, QFont.Bold))
        painter.drawText(0, 20, image.width(), 30, Qt.AlignCenter, "Curvas hipsometricas")
        painter.drawLine(x0, y0, x0 + plot_w, y0)
        painter.drawLine(x0, y0, x0, margin_top)

        for idx, curve in enumerate(curves[:40]):
            color = QColor(colors[idx % len(colors)])
            painter.setPen(QPen(color, 2))
            last = None
            for x_rel, y_rel in curve["points"]:
                x = int(x0 + x_rel * plot_w)
                y = int(y0 - y_rel * plot_h)
                if last is not None:
                    painter.drawLine(last[0], last[1], x, y)
                last = (x, y)
            painter.drawText(x0 + plot_w + 18, margin_top + 18 + idx * 14, curve["codigo"][:24])
        painter.end()
        image.save(str(path), "PNG")

    def _memory_layer_with_units(self, units, crs, name):
        layer = QgsVectorLayer(f"MultiPolygon?crs={crs.authid()}", name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes(
            [
                QgsField("tipo", QVariant.String),
                QgsField("codigo", QVariant.String),
                QgsField("src_id", QVariant.String),
            ]
        )
        layer.updateFields()
        for unit in units:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(unit["geometry"])
            feature.setAttributes([unit["tipo"], unit["codigo"], unit["src_id"]])
            provider.addFeature(feature)
        layer.updateExtents()
        return layer

    def _final_layer_template(self, crs, name):
        layer = QgsVectorLayer(f"MultiPolygon?crs={crs.authid()}", name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField(field_name, field_type) for field_name, _, field_type in self.RESULT_FIELDS])
        layer.updateFields()
        return layer

    def _basin_units(self, layer, dem_layer):
        geometries = []
        for feature in layer.getFeatures():
            geom = self._geometry_to_crs(feature.geometry(), layer.crs(), dem_layer.crs())
            if geom is not None and not geom.isEmpty():
                geometries.append(geom)
        combined = self._combine_geometries(geometries)
        if combined is None or combined.isEmpty():
            return []
        return [{"tipo": "Cuenca", "codigo": "CUENCA", "src_id": "cuenca", "geometry": combined}]

    def _subunit_units(self, layer, dem_layer):
        units = []
        sub_id_index = layer.fields().lookupField("sub_id")
        sub_num_index = layer.fields().lookupField("sub_num")
        subbasin_index = layer.fields().lookupField("subbasin")
        for position, feature in enumerate(layer.getFeatures(), 1):
            geom = self._geometry_to_crs(feature.geometry(), layer.crs(), dem_layer.crs())
            if geom is None or geom.isEmpty():
                continue
            code = None
            if sub_id_index >= 0:
                code = feature[sub_id_index]
            if not code and sub_num_index >= 0:
                code = f"SUB-{int(feature[sub_num_index]):02d}"
            if not code and subbasin_index >= 0:
                code = f"SUB-{feature[subbasin_index]}"
            if not code:
                code = f"SUB-{position:02d}"
            units.append({"tipo": "Subunidad", "codigo": str(code), "src_id": str(feature.id()), "geometry": geom})
        return units

    def _geometry_to_crs(self, geometry, source_crs, target_crs):
        if geometry is None or geometry.isEmpty():
            return None
        geom = QgsGeometry(geometry)
        if source_crs != target_crs:
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
            geom.transform(transform)
        return self._make_valid_geometry(geom)

    def _combine_geometries(self, geometries):
        valid_geometries = [self._make_valid_geometry(geom) for geom in geometries if geom is not None and not geom.isEmpty()]
        valid_geometries = [geom for geom in valid_geometries if geom is not None and not geom.isEmpty()]
        if not valid_geometries:
            return None
        combined = QgsGeometry(valid_geometries[0])
        for geom in valid_geometries[1:]:
            next_combined = combined.combine(geom)
            if next_combined is not None and not next_combined.isEmpty():
                combined = next_combined
        return self._make_valid_geometry(combined)

    def _make_valid_geometry(self, geometry):
        if geometry is None or geometry.isEmpty():
            return geometry
        try:
            valid = geometry.makeValid()
            if valid is not None and not valid.isEmpty():
                return valid
        except Exception:
            pass
        return geometry

    def _write_csv(self, output_path, rows):
        output = prepare_output_path(output_path, self._log)
        with open(output, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=[field[0] for field in self.RESULT_FIELDS] + ["graph_path"])
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key) for key in writer.fieldnames})

    def _write_xlsx(self, output_path, rows):
        output = prepare_output_path(output_path, self._log)
        headers = [field[1] for field in self.RESULT_FIELDS] + ["Grafico PNG"]
        keys = [field[0] for field in self.RESULT_FIELDS] + ["graph_path"]
        summary_rows = [headers]
        for row in rows:
            summary_rows.append([row.get(key) for key in keys])
        dictionary_rows = [["Campo", "Parametro", "Descripcion"]]
        for field_name, field_label, _ in self.RESULT_FIELDS:
            dictionary_rows.append([field_name, field_label, self.FIELD_NOTES.get(field_name, "")])
        dictionary_rows.append(["graph_path", "Grafico PNG", "Ruta del archivo PNG de curva hipsometrica de la unidad."])
        self._create_simple_xlsx(
            output,
            [
                ("Resumen", summary_rows),
                ("Diccionario", dictionary_rows),
            ],
        )

    def _create_simple_xlsx(self, output_path, sheets):
        sheet_defs = []
        workbook_rels = []
        content_overrides = []
        sheet_files = []
        for index, (sheet_name, rows) in enumerate(sheets, 1):
            sheet_defs.append(f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>')
            workbook_rels.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
            content_overrides.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            sheet_files.append((f"xl/worksheets/sheet{index}.xml", self._worksheet_xml(rows)))
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(sheet_defs)}</sheets></workbook>'
        )
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )
        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(workbook_rels)}'
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
        )
        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f'{"".join(content_overrides)}'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", rels_xml)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            archive.writestr("xl/styles.xml", styles_xml)
            for file_name, sheet_xml in sheet_files:
                archive.writestr(file_name, sheet_xml)

    def _worksheet_xml(self, rows):
        xml_rows = []
        max_columns = max((len(row) for row in rows), default=1)
        max_rows = max(len(rows), 1)
        dimension = f"A1:{self._excel_column(max_columns)}{max_rows}"
        cols = "".join(
            f'<col min="{index}" max="{index}" width="{self._excel_width(index)}" customWidth="1"/>'
            for index in range(1, max_columns + 1)
        )
        for row_index, row in enumerate(rows, 1):
            cells = []
            for column_index, value in enumerate(row, 1):
                ref = f"{self._excel_column(column_index)}{row_index}"
                style = ' s="1"' if row_index == 1 else ""
                if isinstance(value, (int, float)) and value is not None and not isinstance(value, bool):
                    cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
                else:
                    text = "" if value is None else escape(str(value))
                    cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>')
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<dimension ref="{dimension}"/>'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{cols}</cols>'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            f'<autoFilter ref="{dimension}"/>'
            '</worksheet>'
        )

    def _excel_column(self, index):
        letters = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    def _excel_width(self, index):
        if index <= 2:
            return 16
        if index >= len(self.RESULT_FIELDS) + 1:
            return 48
        return 14

    def _fill_table(self, rows):
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, (field_name, _, _) in enumerate(self.RESULT_FIELDS):
                value = row.get(field_name)
                text = self._format_table_value(value)
                self.table.setItem(row_index, column, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def _clear_hypsometric_view(self):
        self.last_combined_graph = None
        self.hypso_combo.blockSignals(True)
        self.hypso_combo.clear()
        self.hypso_combo.blockSignals(False)
        self.hypso_info_label.setText("Calcula los parametros para ver aqui la curva hipsometrica.")
        self.hypso_image_label.clear()
        self.hypso_image_label.setText("Sin curva hipsometrica cargada.")

    def _populate_hypsometric_view(self, rows, combined_graph):
        self.last_combined_graph = str(combined_graph) if combined_graph else None
        self.hypso_combo.blockSignals(True)
        self.hypso_combo.clear()
        if combined_graph and Path(combined_graph).exists():
            self.hypso_combo.addItem("Todas las unidades", str(combined_graph))
        for row in rows:
            graph_path = row.get("graph_path")
            if not graph_path or not Path(graph_path).exists():
                continue
            integral = row.get("int_hipso")
            integral_text = f" - IH {integral:.4f}" if isinstance(integral, float) else ""
            self.hypso_combo.addItem(f"{row.get('codigo')}{integral_text}", graph_path)
        self.hypso_combo.blockSignals(False)
        self._update_hypsometric_preview()

    def _update_hypsometric_preview(self):
        path = self.hypso_combo.currentData()
        if not path:
            self.hypso_info_label.setText("No hay curva hipsometrica disponible para mostrar.")
            self.hypso_image_label.clear()
            self.hypso_image_label.setText("Sin curva hipsometrica cargada.")
            return
        graph_path = Path(path)
        if not graph_path.exists():
            self.hypso_info_label.setText(f"No se encontro el grafico: {graph_path}")
            self.hypso_image_label.clear()
            self.hypso_image_label.setText("Grafico no disponible.")
            return
        pixmap = QPixmap(str(graph_path))
        if pixmap.isNull():
            self.hypso_info_label.setText(f"No se pudo cargar el grafico: {graph_path}")
            self.hypso_image_label.clear()
            self.hypso_image_label.setText("Grafico no disponible.")
            return
        width = max(520, self.hypso_image_label.width() - 12)
        height = max(220, self.hypso_image_label.height() - 12)
        self.hypso_image_label.setPixmap(pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.hypso_info_label.setText(f"Grafico mostrado: {graph_path}")

    def _show_hypsometric_for_selected_row(self):
        row_index = self.table.currentRow()
        if row_index < 0 or row_index >= len(self.last_rows):
            QMessageBox.information(self, "Integral hipsometrica", "Selecciona una fila de la tabla de resultados.")
            return
        graph_path = self.last_rows[row_index].get("graph_path")
        if not graph_path:
            QMessageBox.information(self, "Integral hipsometrica", "La fila seleccionada no tiene curva hipsometrica.")
            return
        for index in range(self.hypso_combo.count()):
            if self.hypso_combo.itemData(index) == graph_path:
                self.hypso_combo.setCurrentIndex(index)
                return
        QMessageBox.information(self, "Integral hipsometrica", "No se encontro la curva en el visor.")

    def _selected_dem(self):
        layer = self.dem_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            raise ValueError("Selecciona un DEM valido.")
        return layer

    def _selected_polygon_layer(self, combo, label):
        layer = combo.currentLayer()
        if layer is None or not layer.isValid():
            raise ValueError(f"Selecciona una capa valida para {label}.")
        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
            raise ValueError(f"La capa de {label} debe ser poligonal.")
        return layer

    def _selected_line_layer(self, combo, label):
        layer = combo.currentLayer()
        if layer is None or not layer.isValid():
            raise ValueError(f"Selecciona una capa valida para {label}.")
        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
            raise ValueError(f"La capa de {label} debe ser lineal.")
        return layer

    def _optional_line_layer(self, combo):
        layer = combo.currentLayer()
        if layer is None or not layer.isValid():
            return None
        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
            return None
        return layer

    def _optional_point_layer(self):
        layer = self.outlet_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            return None
        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
            return None
        return layer

    def _outlet_points(self, layer, target_crs):
        if layer is None or not layer.isValid():
            return []
        transform = None
        if layer.crs() != target_crs:
            transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
        features = layer.selectedFeatures() if layer.selectedFeatureCount() else list(layer.getFeatures())
        points = []
        for feature in features:
            geom = QgsGeometry(feature.geometry())
            if geom is None or geom.isEmpty():
                continue
            if transform is not None:
                geom.transform(transform)
            for point in self._point_parts(geom):
                points.append(point)
        return points

    def _point_parts(self, geom):
        if geom is None or geom.isEmpty():
            return []
        try:
            if geom.isMultipart():
                return [QgsPointXY(point) for point in geom.asMultiPoint()]
            return [QgsPointXY(geom.asPoint())]
        except Exception:
            return []

    def _outlet_point_for_geometry(self, geom, outlet_points, allow_nearest=False):
        if not outlet_points:
            return None
        point_geoms = [(point, QgsGeometry.fromPointXY(point)) for point in outlet_points]
        inside = [point for point, point_geom in point_geoms if geom.contains(point_geom) or geom.touches(point_geom)]
        if inside:
            centroid = geom.centroid().asPoint()
            return min(inside, key=lambda point: math.hypot(point.x() - centroid.x(), point.y() - centroid.y()))
        if not allow_nearest:
            return None
        return min(point_geoms, key=lambda item: geom.distance(item[1]))[0]

    def _raster_layer_from_path(self, path):
        layer = QgsRasterLayer(str(path), Path(path).stem)
        return layer if layer.isValid() else None

    def _select_layer_by_name(self, combo, candidates, prefer_best=False):
        current = combo.currentLayer()
        if current is not None and current.isValid() and not prefer_best:
            return
        current_score = None
        if current is not None and current.isValid():
            current_score = self._layer_name_score(current.name().lower(), candidates)
        matches = []
        for layer in QgsProject.instance().mapLayers().values():
            name = layer.name().lower()
            if "morfometria" in name:
                continue
            score = self._layer_name_score(name, candidates)
            if score is not None:
                matches.append((score, layer))
        if matches:
            matches.sort(key=lambda item: item[0])
            best_score, best_layer = matches[0]
            if current_score is not None and current_score <= best_score:
                return
            combo.setLayer(best_layer)

    def _layer_name_score(self, name, candidates):
        for index, candidate in enumerate(candidates):
            if name == candidate or name.endswith(f"_{candidate}"):
                return (0, index)
        for index, candidate in enumerate(candidates):
            if candidate in name:
                return (1, index)
        return None

    def _is_projected_crs(self, crs):
        if hasattr(crs, "isProjected"):
            return crs.isProjected()
        if hasattr(crs, "isGeographic"):
            return not crs.isGeographic()
        return crs.mapUnits() != QgsUnitTypes.DistanceDegrees

    def _safe_prefix(self, text):
        prefix = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text.strip())
        prefix = prefix.strip("_-")
        return prefix or "hidrogis_morfometria"

    def _safe_filename(self, text):
        return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in str(text).strip()) or "unidad"

    def _display_layer_name(self, prefix, description):
        if not prefix or prefix.lower().startswith("hidrogis"):
            return description
        return f"{prefix}_{description}"

    def _to_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _format_table_value(self, value):
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    def _log(self, message):
        self.log.appendPlainText(str(message))
