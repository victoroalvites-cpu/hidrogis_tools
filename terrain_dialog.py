import math
from collections import deque
from pathlib import Path

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsUnitTypes,
    QgsWkbTypes,
)
from qgis.gui import QgsMapLayerComboBox

from .dem_dialog import TextFeedback
from .output_utils import add_or_replace_layer, discard_output_path, prepare_output_path


class TerrainFeedback(TextFeedback):
    NON_FATAL_GDAL_MESSAGES = (
        "SetColorTable() only supported for Byte or UInt16 bands in TIFF format",
    )

    def reportError(self, error, fatalError=False):
        text = str(error)
        if not fatalError and any(message in text for message in self.NON_FATAL_GDAL_MESSAGES):
            return
        super().reportError(error, fatalError)


class WatershedDelineationDialog(QWidget):
    def __init__(self, iface, parent=None, show_close_button=True):
        super().__init__(parent)
        self.iface = iface
        self.show_close_button = show_close_button
        self.last_outputs = {}
        self.manual_outlet_layer = None
        self.setWindowTitle("HidroGIS Watershed Tools - Cuencas: Delimitacion")
        self.resize(780, 680)
        self._build_ui()
        self.refresh_layers()

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_dem_tab(), "DEM")
        self.tabs.addTab(self._build_thresholds_tab(), "Red de drenaje")
        self.tabs.addTab(self._build_outlets_tab(), "Puntos de salida")
        self.tabs.addTab(self._build_outputs_tab(), "Salidas")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.create_streams_button = QPushButton("Crear red")
        self.create_watershed_button = QPushButton("Crear cuenca")
        button_row.addWidget(self.create_streams_button)
        button_row.addWidget(self.create_watershed_button)
        if self.show_close_button:
            self.close_button = QPushButton("Cerrar")
            button_row.addWidget(self.close_button)
        else:
            self.close_button = None

        root.addWidget(self.tabs)
        root.addWidget(QLabel("Registro"))
        root.addWidget(self.log)
        root.addLayout(button_row)

        self.dem_layer_combo.layerChanged.connect(self._update_dem_properties)
        self.stream_cells_spin.valueChanged.connect(self._sync_threshold_labels)
        self.output_folder_button.clicked.connect(self._choose_output_folder)
        self.load_stream_button.clicked.connect(self._load_stream_layer)
        self.load_outlets_button.clicked.connect(self._load_outlets_layer)
        self.draw_outlet_button.clicked.connect(self._create_manual_outlet_layer)
        self.review_snap_button.clicked.connect(self.review_snapped_outlet)
        self.create_streams_button.clicked.connect(self.create_streams)
        self.create_watershed_button.clicked.connect(self.create_watershed)
        if self.close_button is not None:
            self.close_button.clicked.connect(self.close)

    def _build_dem_tab(self):
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        dem_group = QGroupBox("1. DEM base")
        dem_layout = QFormLayout(dem_group)
        self.dem_layer_combo = QgsMapLayerComboBox()
        self.dem_layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.dem_properties_label = QLabel("Selecciona un DEM.")
        self.dem_properties_label.setWordWrap(True)
        self.dem_source_label = QLabel(
            "Admite cualquier DEM raster georreferenciado y proyectado: ASTER GDEM, SRTM, "
            "ALOS/PALSAR, LandViewer, OpenTopography u otra fuente equivalente."
        )
        self.dem_source_label.setWordWrap(True)
        dem_layout.addRow("DEM preprocesado", self.dem_layer_combo)
        dem_layout.addRow("Propiedades", self.dem_properties_label)
        dem_layout.addRow("Fuentes compatibles", self.dem_source_label)

        conditioning_group = QGroupBox("2. Reacondicionamiento del DEM")
        conditioning_layout = QFormLayout(conditioning_group)
        self.burn_streams_check = QCheckBox("Quemar red de drenaje existente")
        self.stream_layer_combo = QgsMapLayerComboBox()
        self.stream_layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.load_stream_button = QPushButton("Cargar red...")
        stream_row = QHBoxLayout()
        stream_row.addWidget(self.stream_layer_combo)
        stream_row.addWidget(self.load_stream_button)
        self.carve_width_spin = QSpinBox()
        self.carve_width_spin.setRange(0, 10000)
        self.carve_width_spin.setValue(0)
        self.carve_depth_spin = QSpinBox()
        self.carve_depth_spin.setRange(0, 1000)
        self.carve_depth_spin.setValue(10)
        self.fill_sinks_check = QCheckBox("Rellenar depresiones")
        self.fill_sinks_check.setChecked(True)
        conditioning_layout.addRow("", self.burn_streams_check)
        conditioning_layout.addRow("Red existente", stream_row)
        conditioning_layout.addRow("Ancho de quemado (m, minimo=celda)", self.carve_width_spin)
        conditioning_layout.addRow("Profundidad de quemado (m)", self.carve_depth_spin)
        conditioning_layout.addRow("", self.fill_sinks_check)

        layout.addWidget(dem_group)
        layout.addWidget(conditioning_group)
        layout.addStretch(1)
        return tab

    def _build_thresholds_tab(self):
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        threshold_group = QGroupBox("Umbrales")
        threshold_layout = QFormLayout(threshold_group)
        self.stream_cells_spin = QSpinBox()
        self.stream_cells_spin.setRange(1, 100000000)
        self.stream_cells_spin.setValue(100000)
        self.stream_cells_spin.setSingleStep(1000)
        self.stream_area_label = QLabel("Area equivalente: -")
        self.area_unit_combo = QComboBox()
        self.area_unit_combo.addItems(["km2", "ha"])
        self.area_unit_combo.currentIndexChanged.connect(self._sync_threshold_labels)
        self.hydrology_engine_combo = QComboBox()
        self.hydrology_engine_combo.addItem("GRASS r.watershed / r.stream.extract (estable)", "grass")
        self.hydrology_engine_combo.addItem("HidroGIS D8 interno (experimental)", "hidrogis_d8")
        self.d8_check = QCheckBox("Usar direccion de flujo D8")
        self.d8_check.setChecked(True)
        threshold_layout.addRow("Motor hidrologico", self.hydrology_engine_combo)
        threshold_layout.addRow("Umbral para red de drenaje (celdas)", self.stream_cells_spin)
        threshold_layout.addRow("", self.stream_area_label)
        threshold_layout.addRow("Unidad de area", self.area_unit_combo)
        threshold_layout.addRow("", self.d8_check)

        info = QLabel(
            "El umbral controla la densidad de la red de drenaje extraida y se usa como criterio unico "
            "para delimitar la cuenca general desde el punto de salida. "
            "GRASS es el motor estable; HidroGIS D8 es experimental y busca mayor consistencia con morfometria."
        )
        info.setWordWrap(True)

        layout.addWidget(threshold_group)
        layout.addWidget(info)
        layout.addStretch(1)
        return tab

    def _build_outlets_tab(self):
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        outlets_group = QGroupBox("Puntos de salida")
        outlets_layout = QFormLayout(outlets_group)
        self.outlet_layer_combo = QgsMapLayerComboBox()
        self.outlet_layer_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.load_outlets_button = QPushButton("Cargar puntos...")
        outlets_row = QHBoxLayout()
        outlets_row.addWidget(self.outlet_layer_combo)
        outlets_row.addWidget(self.load_outlets_button)
        self.draw_outlet_button = QPushButton("Crear capa para dibujar punto")
        self.snap_distance_spin = QSpinBox()
        self.snap_distance_spin.setRange(0, 100000)
        self.snap_distance_spin.setValue(300)
        self.review_snap_button = QPushButton("Revisar punto ajustado")
        outlets_layout.addRow("Capa de puntos", outlets_row)
        outlets_layout.addRow("", self.draw_outlet_button)
        outlets_layout.addRow("Distancia snap (m)", self.snap_distance_spin)
        outlets_layout.addRow("", self.review_snap_button)

        info = QLabel(
            "Selecciona un punto existente o crea una capa temporal para dibujarlo. "
            "Si ya creaste la red, el punto se ajustara al tramo de drenaje mas cercano dentro de la distancia indicada."
        )
        info.setWordWrap(True)

        layout.addWidget(outlets_group)
        layout.addWidget(info)
        layout.addStretch(1)
        return tab

    def _build_outputs_tab(self):
        tab = QGroupBox()
        layout = QFormLayout(tab)
        self.output_folder_edit = QLineEdit(str(Path.home()))
        self.output_folder_button = QPushButton("Examinar")
        output_folder_row = QHBoxLayout()
        output_folder_row.addWidget(self.output_folder_edit)
        output_folder_row.addWidget(self.output_folder_button)
        self.prefix_edit = QLineEdit("hidrogis_cuenca")
        self.add_results_check = QCheckBox("Agregar red y cuenca al proyecto")
        self.add_results_check.setChecked(True)
        self.add_hydrologic_dem_check = QCheckBox("Agregar DEM hidrologico final")
        self.add_hydrologic_dem_check.setChecked(True)
        self.export_stream_shp_check = QCheckBox("Exportar red de drenaje como Shapefile (.shp)")
        self.export_stream_shp_check.setChecked(True)
        # Conservados por compatibilidad con salidas antiguas; la delimitacion normal
        # ahora entrega una cuenca unica y no genera subunidades.
        self.subunit_prefix_edit = QLineEdit("SUB")
        self.merge_small_subunits_check = QCheckBox("Fusionar subunidades pequenas")
        self.merge_small_subunits_check.setChecked(False)
        self.min_subunit_area_spin = QDoubleSpinBox()
        self.min_subunit_area_spin.setRange(0.0, 1000000.0)
        self.min_subunit_area_spin.setDecimals(4)
        self.min_subunit_area_spin.setSingleStep(0.1)
        self.min_subunit_area_spin.setValue(0.0)
        self.min_subunit_area_spin.setSuffix(" km2")
        self.add_intermediate_check = QCheckBox("Agregar tambien capas intermedias")
        self.add_intermediate_check.setChecked(False)
        outputs_info = QLabel(
            "La delimitacion final genera una cuenca unica y la red de drenaje recortada. "
            "Las subunidades se trabajan como capas externas en Morfometria cuando provienen de HEC-HMS u otra fuente."
        )
        outputs_info.setWordWrap(True)
        layout.addRow("Carpeta de salida", output_folder_row)
        layout.addRow("Prefijo", self.prefix_edit)
        layout.addRow("", self.add_results_check)
        layout.addRow("", self.add_hydrologic_dem_check)
        layout.addRow("", self.export_stream_shp_check)
        layout.addRow("", self.add_intermediate_check)
        layout.addRow("", outputs_info)
        return tab

    def refresh_layers(self):
        self.dem_layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.stream_layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.outlet_layer_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        self._update_dem_properties()

    def _choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def set_output_folder(self, folder):
        self.output_folder_edit.setText(str(folder))

    def _load_stream_layer(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar red de drenaje",
            "",
            "Vectores (*.shp *.gpkg *.geojson);;Todos los archivos (*.*)",
        )
        if path:
            layer = QgsVectorLayer(path, Path(path).stem, "ogr")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.stream_layer_combo.setLayer(layer)
            else:
                QMessageBox.warning(self, "Capa invalida", "No se pudo cargar la red seleccionada.")

    def _load_outlets_layer(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar puntos de salida",
            "",
            "Vectores (*.shp *.gpkg *.geojson);;Todos los archivos (*.*)",
        )
        if path:
            layer = QgsVectorLayer(path, Path(path).stem, "ogr")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.outlet_layer_combo.setLayer(layer)
            else:
                QMessageBox.warning(self, "Capa invalida", "No se pudo cargar la capa de puntos seleccionada.")

    def _create_manual_outlet_layer(self):
        dem_layer = self._selected_dem()
        crs = dem_layer.crs().authid() or QgsProject.instance().crs().authid()
        layer = QgsVectorLayer(f"Point?crs={crs}", "Punto de salida", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.Int), QgsField("nombre", QVariant.String)])
        layer.updateFields()
        QgsProject.instance().addMapLayer(layer)
        layer.startEditing()
        self.manual_outlet_layer = layer
        self.outlet_layer_combo.setLayer(layer)
        self.iface.setActiveLayer(layer)
        self.iface.messageBar().pushMessage(
            "HidroGIS Watershed Tools",
            "Capa creada. Activa la herramienta de anadir punto de QGIS y dibuja el punto de salida.",
            level=Qgis.Info,
            duration=8,
        )

    def _update_dem_properties(self):
        layer = self.dem_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            self.dem_properties_label.setText("Selecciona un DEM.")
            return
        crs = layer.crs()
        pixel_x = abs(layer.rasterUnitsPerPixelX())
        pixel_y = abs(layer.rasterUnitsPerPixelY())
        extent = layer.extent()
        projected = "Si" if self._is_projected_crs(crs) else "No"
        self.dem_properties_label.setText(
            f"CRS: {crs.authid()} | Proyectado: {projected}\n"
            f"Tamano de celda: {pixel_x:.3f} x {pixel_y:.3f} unidades del CRS\n"
            f"Extension: {extent.xMinimum():.3f}, {extent.yMinimum():.3f}, "
            f"{extent.xMaximum():.3f}, {extent.yMaximum():.3f}"
        )
        self._sync_threshold_labels()

    def _sync_threshold_labels(self):
        layer = self.dem_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            self.stream_area_label.setText("Area equivalente: -")
            return
        self.stream_area_label.setText(
            f"Area equivalente: {self._cells_to_area_text(layer, self.stream_cells_spin.value())}"
        )

    def _cells_to_area_text(self, layer, cells):
        pixel_area = abs(layer.rasterUnitsPerPixelX() * layer.rasterUnitsPerPixelY())
        unit = self.area_unit_combo.currentText()
        if not self._is_projected_crs(layer.crs()):
            return "requiere DEM en CRS proyectado"
        area_m2 = cells * pixel_area
        if unit == "ha":
            return f"{area_m2 / 10000.0:.4f} ha"
        return f"{area_m2 / 1000000.0:.4f} km2"

    def _log(self, message):
        self.log.appendPlainText(str(message))

    def create_streams(self):
        self._run_stream_workflow(only_streams=True)

    def create_watershed(self):
        self._run_stream_workflow(only_streams=False)

    def _run_stream_workflow(self, only_streams):
        try:
            import processing
        except ImportError:
            QMessageBox.critical(self, "Processing no disponible", "No se pudo cargar el modulo Processing de QGIS.")
            return

        self.log.clear()
        self.create_streams_button.setEnabled(False)
        self.create_watershed_button.setEnabled(False)
        try:
            dem_layer = self._selected_dem()
            if not self._is_projected_crs(dem_layer.crs()):
                raise ValueError("Usa un DEM en un CRS proyectado en metros antes de delimitar cuencas.")

            output_dir = Path(self.output_folder_edit.text()).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
            prefix = self._safe_prefix(self.prefix_edit.text())
            feedback = TerrainFeedback(self._log)

            self.last_outputs = {}
            current_dem = self._condition_dem(processing, dem_layer, output_dir, prefix, feedback)
            self._fill_dem_if_needed(processing, current_dem, dem_layer, output_dir, prefix, feedback)
            self._reapply_conditioning_after_fill(processing, dem_layer, output_dir, prefix, feedback)
            self._register_hydrologic_dem(prefix)
            engine = self.hydrology_engine_combo.currentData() or "grass"
            self.last_outputs["hydrology_engine"] = engine
            if engine == "hidrogis_d8":
                self._run_hidrogis_d8_engine(
                    processing,
                    self.last_outputs["analysis_dem"],
                    dem_layer,
                    output_dir,
                    prefix,
                    feedback,
                )
            else:
                self._run_watershed(processing, self.last_outputs["analysis_dem"], dem_layer, output_dir, prefix, feedback)
                self._extract_stream_network(
                    processing,
                    self.last_outputs["analysis_dem"],
                    dem_layer,
                    output_dir,
                    prefix,
                    feedback,
                )

            if not only_streams:
                if engine == "hidrogis_d8":
                    self._create_watershed_from_outlet_d8(processing, dem_layer, output_dir, prefix, feedback)
                else:
                    self._create_watershed_from_outlet(processing, dem_layer, output_dir, prefix, feedback)

            if self.add_results_check.isChecked():
                if not only_streams:
                    self._remove_reference_layers_from_project()
                self._add_outputs_to_project(self._visible_outputs(only_streams))

            self._log("")
            self._log("Listo.")
            self.iface.messageBar().pushMessage(
                "HidroGIS Watershed Tools",
                "Proceso de delimitacion completado.",
                level=Qgis.Success,
                duration=6,
            )
        except Exception as exc:
            self._log(f"ERROR: {exc}")
            QMessageBox.critical(self, "Error en la delimitacion", str(exc))
        finally:
            self.create_streams_button.setEnabled(True)
            self.create_watershed_button.setEnabled(True)

    def _condition_dem(self, processing, dem_layer, output_dir, prefix, feedback):
        current_dem = dem_layer
        if not self.burn_streams_check.isChecked():
            self._log("Reacondicionamiento por red existente omitido.")
            return current_dem

        output = prepare_output_path(output_dir / f"{prefix}_04_dem_reacondicionado.tif", self._log)
        points = prepare_output_path(output_dir / f"{prefix}_04_puntos_carve.gpkg", self._log)
        self._log("Reacondicionando DEM con GRASS r.carve...")
        result = self._run_carve(processing, dem_layer, dem_layer, output, points, feedback)
        self.last_outputs["conditioned_dem"] = {
            "path": result["output"],
            "name": f"{prefix}_dem_reacondicionado",
            "type": "raster",
        }
        self.last_outputs["carve_points"] = {
            "path": result["points"],
            "name": f"{prefix}_puntos_carve",
            "type": "vector",
        }
        return result["output"]

    def _stream_layer_to_burn(self):
        stream_layer = self.stream_layer_combo.currentLayer()
        if stream_layer is None or not stream_layer.isValid():
            raise ValueError("Activa una red existente valida para quemarla en el DEM.")
        if QgsWkbTypes.geometryType(stream_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            raise ValueError("La red existente debe ser una capa de lineas.")
        return stream_layer

    def _effective_carve_width(self, raster_input):
        raster_layer = self._raster_layer_from_any(raster_input, "dem_ancho_quemado")
        pixel_size = max(abs(raster_layer.rasterUnitsPerPixelX()), abs(raster_layer.rasterUnitsPerPixelY()))
        requested_width = float(self.carve_width_spin.value())
        if requested_width <= 0:
            self._log(f"Ancho de quemado 0: se usara una celda ({pixel_size:.3f} unidades del CRS).")
            return pixel_size
        if pixel_size > 0 and requested_width < pixel_size:
            self._log(
                f"Ancho de quemado {requested_width:.3f} menor que la celda "
                f"({pixel_size:.3f}); se usara una celda para que el cauce afecte al DEM."
            )
            return pixel_size
        return requested_width

    def _run_carve(self, processing, raster_input, region_layer, output, points, feedback):
        return processing.run(
            self._grass_algorithm_id("r.carve"),
            {
                "raster": raster_input,
                "vector": self._stream_layer_to_burn(),
                "width": self._effective_carve_width(raster_input),
                "depth": self.carve_depth_spin.value() or None,
                "-n": True,
                "output": output,
                "points": points,
                "GRASS_REGION_PARAMETER": self._grass_region(region_layer),
                "GRASS_REGION_CELLSIZE_PARAMETER": 0,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": "",
                "GRASS_OUTPUT_TYPE_PARAMETER": 0,
                "GRASS_VECTOR_DSCO": "",
                "GRASS_VECTOR_LCO": "",
                "GRASS_VECTOR_EXPORT_NOCAT": False,
            },
            feedback=feedback,
        )

    def _fill_dem_if_needed(self, processing, current_dem, region_layer, output_dir, prefix, feedback):
        if not self.fill_sinks_check.isChecked():
            self._log("Relleno de depresiones omitido.")
            self.last_outputs["analysis_dem"] = current_dem
            return

        output = prepare_output_path(output_dir / f"{prefix}_05_dem_rellenado.tif", self._log)
        direction = prepare_output_path(output_dir / f"{prefix}_06_direccion_fill.tif", self._log)
        areas = prepare_output_path(output_dir / f"{prefix}_07_zonas_problema.tif", self._log)
        self._log("Rellenando depresiones con GRASS r.fill.dir...")
        result = processing.run(
            self._grass_algorithm_id("r.fill.dir"),
            {
                "input": current_dem,
                "format": 0,
                "-f": False,
                "output": output,
                "direction": direction,
                "areas": areas,
                "GRASS_REGION_PARAMETER": self._grass_region(region_layer),
                "GRASS_REGION_CELLSIZE_PARAMETER": 0,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": "",
            },
            feedback=feedback,
        )
        self.last_outputs["analysis_dem"] = result["output"]
        self.last_outputs["filled_dem"] = {
            "path": result["output"],
            "name": f"{prefix}_dem_rellenado",
            "type": "raster",
        }
        self.last_outputs["fill_direction"] = {
            "path": result["direction"],
            "name": f"{prefix}_direccion_fill",
            "type": "raster",
        }
        self.last_outputs["problem_areas"] = {
            "path": result["areas"],
            "name": f"{prefix}_zonas_problema",
            "type": "raster",
        }

    def _reapply_conditioning_after_fill(self, processing, region_layer, output_dir, prefix, feedback):
        if not self.burn_streams_check.isChecked() or not self.fill_sinks_check.isChecked():
            return
        analysis_dem = self.last_outputs.get("analysis_dem")
        if not analysis_dem:
            return

        output = prepare_output_path(output_dir / f"{prefix}_05_dem_rellenado_reacondicionado.tif", self._log)
        points = prepare_output_path(output_dir / f"{prefix}_05_puntos_carve_final.gpkg", self._log)
        self._log("Reaplicando quemado de red sobre el DEM rellenado...")
        result = self._run_carve(processing, analysis_dem, region_layer, output, points, feedback)
        self.last_outputs["analysis_dem"] = result["output"]
        self.last_outputs["analysis_conditioned_dem"] = {
            "path": result["output"],
            "name": f"{prefix}_dem_rellenado_reacondicionado",
            "type": "raster",
        }
        self.last_outputs["analysis_carve_points"] = {
            "path": result["points"],
            "name": f"{prefix}_puntos_carve_final",
            "type": "vector",
        }

    def _register_hydrologic_dem(self, prefix):
        analysis_dem = self.last_outputs.get("analysis_dem")
        if not analysis_dem or isinstance(analysis_dem, QgsRasterLayer):
            return
        self.last_outputs["hydrologic_dem"] = {
            "path": analysis_dem,
            "name": self._display_layer_name(prefix, "DEM hidrologico"),
            "type": "raster",
        }

    def _run_hidrogis_d8_engine(self, processing, dem_input, region_layer, output_dir, prefix, feedback):
        self._log("Calculando direccion y acumulacion con HidroGIS D8 interno (experimental)...")
        dem_layer = self._raster_layer_from_any(dem_input, "dem_analisis_d8")
        model = self._build_d8_model(dem_layer)
        self._d8_model = model

        accumulation = prepare_output_path(output_dir / f"{prefix}_08_acumulacion.tif", self._log)
        drainage = prepare_output_path(output_dir / f"{prefix}_09_direccion.tif", self._log)
        basins = prepare_output_path(output_dir / f"{prefix}_10_subcuencas.tif", self._log)
        channel_stream = prepare_output_path(output_dir / f"{prefix}_11_canales_delimitacion.tif", self._log)
        stream_raster = prepare_output_path(output_dir / f"{prefix}_14_red_drenaje.tif", self._log)
        stream_vector = prepare_output_path(output_dir / f"{prefix}_15_red_drenaje.gpkg", self._log)
        stream_direction = prepare_output_path(output_dir / f"{prefix}_16_direccion_red.tif", self._log)

        self._write_d8_raster(model, model["accumulation"].reshape(model["height"], model["width"]), accumulation, "float")
        self._write_d8_raster(model, model["direction"], drainage, "int")
        self._write_d8_raster(model, model["direction"], stream_direction, "int")

        channel_mask = self._d8_stream_mask(model, self.stream_cells_spin.value())
        stream_mask = self._d8_stream_mask(model, self.stream_cells_spin.value())
        subbasin_ids = self._d8_subbasin_ids(model, channel_mask)
        self._write_d8_raster(model, subbasin_ids, basins, "int", nodata=0)
        self._write_d8_raster(model, channel_mask.astype("int16"), channel_stream, "int", nodata=0)
        self._write_d8_raster(model, stream_mask.astype("int16"), stream_raster, "int", nodata=0)

        stream_name = self._display_layer_name(prefix, "Red de drenaje")
        self._save_d8_stream_vector(processing, model, stream_mask, stream_vector, stream_name, feedback)

        self.last_outputs["accumulation"] = {
            "path": accumulation,
            "name": f"{prefix}_acumulacion",
            "type": "raster",
        }
        self.last_outputs["drainage"] = {
            "path": drainage,
            "name": f"{prefix}_direccion",
            "type": "raster",
        }
        self.last_outputs["subbasins_raster"] = {
            "path": basins,
            "name": f"{prefix}_subcuencas_intermedio",
            "type": "raster",
        }
        self.last_outputs["channel_stream_raster"] = {
            "path": channel_stream,
            "name": f"{prefix}_canales_delimitacion",
            "type": "raster",
        }
        self.last_outputs["stream_raster"] = {
            "path": stream_raster,
            "name": f"{prefix}_red_drenaje",
            "type": "raster",
        }
        self.last_outputs["stream_vector"] = {
            "path": stream_vector,
            "name": stream_name,
            "type": "vector",
        }
        self.last_outputs["stream_direction"] = {
            "path": stream_direction,
            "name": f"{prefix}_direccion_red",
            "type": "raster",
        }
        self._log_vector_feature_count(stream_vector, stream_name)
        if self.export_stream_shp_check.isChecked():
            self._export_vector_output(
                processing,
                stream_vector,
                output_dir / f"{prefix}_15_red_drenaje.shp",
                stream_name,
                "stream_vector_shp",
                feedback,
            )

    def _build_d8_model(self, dem_layer):
        try:
            import numpy as np
            from osgeo import gdal
        except Exception as exc:
            raise ValueError(f"No se pudo cargar GDAL/NumPy para HidroGIS D8. Detalle: {exc}")

        source = self._raster_source_path(dem_layer)
        dataset = gdal.Open(source)
        if dataset is None:
            raise ValueError(f"No se pudo abrir el DEM para HidroGIS D8: {source}")
        band = dataset.GetRasterBand(1)
        elevation = band.ReadAsArray().astype("float64")
        nodata = band.GetNoDataValue()
        valid = np.isfinite(elevation)
        if nodata is not None:
            valid &= elevation != nodata
        if not valid.any():
            raise ValueError("El DEM no tiene celdas validas para calcular D8.")

        height, width = elevation.shape
        total_cells = height * width
        if total_cells > 4000000:
            raise ValueError(
                "HidroGIS D8 experimental evita procesar mas de 4 millones de celdas. "
                "Recorta el DEM o usa GRASS para esta escala."
            )

        geotransform = dataset.GetGeoTransform()
        projection = dataset.GetProjection()
        receivers = np.full(total_cells, -1, dtype="int64")
        direction = np.zeros((height, width), dtype="int16")
        valid_flat = valid.ravel()
        valid_indices = np.flatnonzero(valid_flat)
        pixel_x = abs(float(geotransform[1])) or abs(dem_layer.rasterUnitsPerPixelX()) or 1.0
        pixel_y = abs(float(geotransform[5])) or abs(dem_layer.rasterUnitsPerPixelY()) or 1.0
        diagonal = math.hypot(pixel_x, pixel_y)
        neighbors = (
            (-1, 0, 64, pixel_y),
            (-1, 1, 128, diagonal),
            (0, 1, 1, pixel_x),
            (1, 1, 2, diagonal),
            (1, 0, 4, pixel_y),
            (1, -1, 8, diagonal),
            (0, -1, 16, pixel_x),
            (-1, -1, 32, diagonal),
        )

        for index in valid_indices:
            row = int(index // width)
            col = int(index % width)
            value = elevation[row, col]
            best_receiver = -1
            best_code = 0
            best_slope = 0.0
            for row_delta, col_delta, code, distance in neighbors:
                nrow = row + row_delta
                ncol = col + col_delta
                if nrow < 0 or nrow >= height or ncol < 0 or ncol >= width or not valid[nrow, ncol]:
                    continue
                drop = value - elevation[nrow, ncol]
                if drop <= 0:
                    continue
                slope = drop / distance
                if slope > best_slope:
                    best_slope = slope
                    best_receiver = nrow * width + ncol
                    best_code = code
            receivers[index] = best_receiver
            direction[row, col] = best_code

        accumulation = self._d8_accumulation(valid_indices, receivers, valid_flat, total_cells)
        return {
            "np": np,
            "source": source,
            "width": width,
            "height": height,
            "elevation": elevation,
            "valid": valid,
            "valid_flat": valid_flat,
            "valid_indices": valid_indices,
            "receivers": receivers,
            "direction": direction,
            "accumulation": accumulation,
            "geotransform": geotransform,
            "projection": projection,
            "crs": dem_layer.crs(),
            "pixel_x": pixel_x,
            "pixel_y": pixel_y,
        }

    def _d8_accumulation(self, valid_indices, receivers, valid_flat, total_cells):
        np = __import__("numpy")
        indegree = np.zeros(total_cells, dtype="int32")
        for index in valid_indices:
            receiver = receivers[index]
            if receiver >= 0 and valid_flat[receiver]:
                indegree[receiver] += 1

        accumulation = np.zeros(total_cells, dtype="float64")
        accumulation[valid_indices] = 1.0
        queue = deque(int(index) for index in valid_indices if indegree[index] == 0)
        processed = 0
        while queue:
            index = queue.popleft()
            processed += 1
            receiver = receivers[index]
            if receiver >= 0 and valid_flat[receiver]:
                accumulation[receiver] += accumulation[index]
                indegree[receiver] -= 1
                if indegree[receiver] == 0:
                    queue.append(int(receiver))
        if processed < len(valid_indices):
            self._log(
                "HidroGIS D8 detecto algunas celdas sin resolver en zonas planas/depresiones; "
                "la acumulacion puede diferir de GRASS."
            )
        return accumulation

    def _d8_stream_mask(self, model, threshold):
        np = model["np"]
        accumulation = model["accumulation"].reshape(model["height"], model["width"])
        return (accumulation >= float(threshold)) & model["valid"]

    def _d8_subbasin_ids(self, model, channel_mask):
        np = model["np"]
        height = model["height"]
        width = model["width"]
        total_cells = height * width
        channel_flat = channel_mask.ravel()
        receivers = model["receivers"]
        valid_indices = model["valid_indices"]
        valid_flat = model["valid_flat"]

        channel_upstream_count = np.zeros(total_cells, dtype="int32")
        for index in valid_indices:
            receiver = receivers[index]
            if receiver >= 0 and channel_flat[index] and channel_flat[receiver]:
                channel_upstream_count[receiver] += 1

        link_ids = np.zeros(total_cells, dtype="int32")
        link_id = 0
        channel_indices = [int(index) for index in np.flatnonzero(channel_flat)]
        starts = [index for index in channel_indices if channel_upstream_count[index] != 1]
        for start in starts:
            receiver = receivers[start]
            if receiver < 0 or not channel_flat[receiver]:
                if link_ids[start] == 0:
                    link_id += 1
                    link_ids[start] = link_id
                continue
            link_id += 1
            current = start
            guard = 0
            while current >= 0 and channel_flat[current] and guard < total_cells:
                if link_ids[current] == 0:
                    link_ids[current] = link_id
                next_cell = receivers[current]
                if next_cell < 0 or not channel_flat[next_cell]:
                    break
                current = int(next_cell)
                if current != start and channel_upstream_count[current] != 1:
                    if link_ids[current] == 0:
                        link_ids[current] = link_id
                    break
                guard += 1

        for index in channel_indices:
            if link_ids[index] == 0:
                link_id += 1
                current = index
                guard = 0
                while current >= 0 and channel_flat[current] and link_ids[current] == 0 and guard < total_cells:
                    link_ids[current] = link_id
                    current = int(receivers[current])
                    guard += 1

        subbasins = np.zeros(total_cells, dtype="int32")
        memo = {}
        for index in valid_indices:
            index = int(index)
            path = []
            visited = set()
            current = index
            assigned = 0
            while current >= 0 and valid_flat[current]:
                if current in memo:
                    assigned = memo[current]
                    break
                if link_ids[current] > 0:
                    assigned = int(link_ids[current])
                    break
                if current in visited:
                    break
                visited.add(current)
                path.append(current)
                current = int(receivers[current])
            for item in path:
                memo[item] = assigned
                subbasins[item] = assigned
            if assigned:
                subbasins[index] = assigned

        return subbasins.reshape(height, width)

    def _write_d8_raster(self, model, array, output_path, value_type, nodata=None):
        from osgeo import gdal

        np = model["np"]
        output_path = str(output_path)
        if value_type == "float":
            gdal_type = gdal.GDT_Float32
            data = array.astype("float32")
            output_nodata = -9999.0 if nodata is None else nodata
        else:
            gdal_type = gdal.GDT_Int32
            data = array.astype("int32")
            output_nodata = -9999 if nodata is None else nodata

        if nodata is not None:
            data = np.where(model["valid"], data, output_nodata)
        else:
            data = np.where(model["valid"], data, output_nodata)

        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(
            output_path,
            model["width"],
            model["height"],
            1,
            gdal_type,
            options=["COMPRESS=LZW", "TILED=YES"],
        )
        if dataset is None:
            raise ValueError(f"No se pudo crear raster D8: {output_path}")
        dataset.SetGeoTransform(model["geotransform"])
        if model["projection"]:
            dataset.SetProjection(model["projection"])
        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(output_nodata)
        band.WriteArray(data)
        band.FlushCache()
        dataset.FlushCache()
        dataset = None

    def _save_d8_stream_vector(self, processing, model, stream_mask, output_path, layer_name, feedback):
        layer = QgsVectorLayer(f"LineString?crs={model['crs'].authid()}", layer_name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes(
            [
                QgsField("id", QVariant.Int),
                QgsField("accum", QVariant.Double),
            ]
        )
        layer.updateFields()

        stream_flat = stream_mask.ravel()
        feature_id = 1
        for index in model["valid_indices"]:
            index = int(index)
            receiver = int(model["receivers"][index])
            if not stream_flat[index] or receiver < 0 or not model["valid_flat"][receiver]:
                continue
            if not stream_flat[receiver]:
                continue
            start = self._d8_cell_center(model, index)
            end = self._d8_cell_center(model, receiver)
            if start == end:
                continue
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPolylineXY([start, end]))
            feature.setAttributes([feature_id, float(model["accumulation"][index])])
            provider.addFeature(feature)
            feature_id += 1

        layer.updateExtents()
        saved = processing.run(
            "native:savefeatures",
            {
                "INPUT": layer,
                "OUTPUT": output_path,
            },
            feedback=feedback,
        )
        return saved["OUTPUT"]

    def _d8_cell_center(self, model, index):
        row = int(index // model["width"])
        col = int(index % model["width"])
        gt = model["geotransform"]
        x = gt[0] + (col + 0.5) * gt[1] + (row + 0.5) * gt[2]
        y = gt[3] + (col + 0.5) * gt[4] + (row + 0.5) * gt[5]
        return QgsPointXY(float(x), float(y))

    def _d8_index_from_point(self, model, point):
        gt = model["geotransform"]
        if abs(gt[2]) > 1e-12 or abs(gt[4]) > 1e-12:
            return self._nearest_valid_d8_index(model, point)
        col = int((point.x() - gt[0]) / gt[1])
        row = int((point.y() - gt[3]) / gt[5])
        width = model["width"]
        height = model["height"]
        if 0 <= row < height and 0 <= col < width:
            index = row * width + col
            if model["valid_flat"][index]:
                return index
        return self._nearest_valid_d8_index(model, point)

    def _nearest_valid_d8_index(self, model, point):
        best_index = None
        best_distance = None
        for index in model["valid_indices"]:
            cell_point = self._d8_cell_center(model, int(index))
            distance = math.hypot(cell_point.x() - point.x(), cell_point.y() - point.y())
            if best_distance is None or distance < best_distance:
                best_index = int(index)
                best_distance = distance
        return best_index

    def _raster_layer_from_any(self, raster_input, name):
        if isinstance(raster_input, QgsRasterLayer):
            return raster_input
        layer = QgsRasterLayer(str(raster_input), name)
        if not layer.isValid():
            raise ValueError(f"No se pudo abrir raster: {raster_input}")
        return layer

    def _raster_source_path(self, raster_layer):
        return str(raster_layer.source()).split("|", 1)[0]

    def _run_watershed(self, processing, dem_input, region_layer, output_dir, prefix, feedback):
        self._log("Calculando direccion, acumulacion y drenaje base con GRASS r.watershed...")
        accumulation = prepare_output_path(output_dir / f"{prefix}_08_acumulacion.tif", self._log)
        drainage = prepare_output_path(output_dir / f"{prefix}_09_direccion.tif", self._log)
        basins = prepare_output_path(output_dir / f"{prefix}_10_subcuencas.tif", self._log)
        channel_stream = prepare_output_path(output_dir / f"{prefix}_11_canales_delimitacion.tif", self._log)
        tci = prepare_output_path(output_dir / f"{prefix}_12_tci.tif", self._log)
        spi = prepare_output_path(output_dir / f"{prefix}_13_spi.tif", self._log)
        result = processing.run(
            self._grass_algorithm_id("r.watershed"),
            {
                "elevation": dem_input,
                "depression": None,
                "flow": None,
                "disturbed_land": None,
                "blocking": None,
                "threshold": self.stream_cells_spin.value(),
                "max_slope_length": None,
                "convergence": 5,
                "memory": 300,
                "-s": self.d8_check.isChecked(),
                "-m": False,
                "-4": False,
                "-a": True,
                "-b": True,
                "accumulation": accumulation,
                "drainage": drainage,
                "basin": basins,
                "stream": channel_stream,
                "half_basin": None,
                "length_slope": None,
                "slope_steepness": None,
                "tci": tci,
                "spi": spi,
                "GRASS_REGION_PARAMETER": self._grass_region(region_layer),
                "GRASS_REGION_CELLSIZE_PARAMETER": 0,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": "",
            },
            feedback=feedback,
        )
        self.last_outputs["accumulation"] = {
            "path": result["accumulation"],
            "name": f"{prefix}_acumulacion",
            "type": "raster",
        }
        self.last_outputs["drainage"] = {
            "path": result["drainage"],
            "name": f"{prefix}_direccion",
            "type": "raster",
        }
        self.last_outputs["subbasins_raster"] = {
            "path": result["basin"],
            "name": f"{prefix}_subcuencas_intermedio",
            "type": "raster",
        }
        self.last_outputs["channel_stream_raster"] = {
            "path": result["stream"],
            "name": f"{prefix}_canales_delimitacion",
            "type": "raster",
        }
        self.last_outputs["tci"] = {"path": result["tci"], "name": f"{prefix}_tci", "type": "raster"}
        self.last_outputs["spi"] = {"path": result["spi"], "name": f"{prefix}_spi", "type": "raster"}

    def _extract_stream_network(self, processing, dem_input, region_layer, output_dir, prefix, feedback):
        self._log("Extrayendo red de drenaje con el umbral de red...")
        stream_raster = prepare_output_path(output_dir / f"{prefix}_14_red_drenaje.tif", self._log)
        stream_vector = prepare_output_path(output_dir / f"{prefix}_15_red_drenaje.gpkg", self._log)
        direction = prepare_output_path(output_dir / f"{prefix}_16_direccion_red.tif", self._log)
        result = processing.run(
            self._grass_algorithm_id("r.stream.extract"),
            {
                "elevation": dem_input,
                "accumulation": self.last_outputs["accumulation"]["path"],
                "depression": None,
                "threshold": float(self.stream_cells_spin.value()),
                "mexp": None,
                "stream_length": 0,
                "d8cut": None,
                "memory": 300,
                "stream_raster": stream_raster,
                "stream_vector": stream_vector,
                "direction": direction,
                "GRASS_REGION_PARAMETER": self._grass_region(region_layer),
                "GRASS_REGION_CELLSIZE_PARAMETER": 0,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": "",
                "GRASS_OUTPUT_TYPE_PARAMETER": 2,
                "GRASS_VECTOR_DSCO": "",
                "GRASS_VECTOR_LCO": "",
                "GRASS_VECTOR_EXPORT_NOCAT": False,
            },
            feedback=feedback,
        )
        stream_name = self._display_layer_name(prefix, "Red de drenaje")
        stream_vector_source = self._require_line_vector_output(result["stream_vector"], stream_name)
        self.last_outputs["stream_raster"] = {
            "path": result["stream_raster"],
            "name": f"{prefix}_red_drenaje",
            "type": "raster",
        }
        self.last_outputs["stream_vector"] = {
            "path": stream_vector_source,
            "name": stream_name,
            "type": "vector",
        }
        self._log_vector_feature_count(stream_vector_source, stream_name)
        self.last_outputs["stream_direction"] = {
            "path": result["direction"],
            "name": f"{prefix}_direccion_red",
            "type": "raster",
        }
        if self.export_stream_shp_check.isChecked():
            self._export_vector_output(
                processing,
                stream_vector_source,
                output_dir / f"{prefix}_15_red_drenaje.shp",
                stream_name,
                "stream_vector_shp",
                feedback,
            )

    def _create_watershed_from_outlet(self, processing, dem_layer, output_dir, prefix, feedback):
        point = self._snapped_outlet_point(dem_layer)
        self._move_current_outlet_to_point(point, dem_layer.crs())
        point_text = f"{point.x()},{point.y()} [{dem_layer.crs().authid()}]"
        basin_raster = prepare_output_path(output_dir / f"{prefix}_17_cuenca.tif", self._log)
        basin_vector = output_dir / f"{prefix}_18_cuenca.gpkg"
        snapped_point = output_dir / f"{prefix}_19_punto_salida_ajustado.gpkg"

        self._log(f"Delimitando cuenca desde punto ajustado: {point.x():.3f}, {point.y():.3f}")
        result = processing.run(
            self._grass_algorithm_id("r.water.outlet"),
            {
                "input": self.last_outputs["drainage"]["path"],
                "coordinates": point_text,
                "output": basin_raster,
                "GRASS_REGION_PARAMETER": self._grass_region(dem_layer),
                "GRASS_REGION_CELLSIZE_PARAMETER": 0,
                "GRASS_RASTER_FORMAT_OPT": "",
                "GRASS_RASTER_FORMAT_META": "",
            },
            feedback=feedback,
        )
        self.last_outputs["watershed_raster"] = {
            "path": result["output"],
            "name": f"{prefix}_cuenca",
            "type": "raster",
        }

        self._save_point_layer(processing, point, dem_layer.crs(), snapped_point, f"{prefix}_punto_salida_ajustado")
        self.last_outputs["snapped_outlet"] = {
            "path": snapped_point,
            "name": self._display_layer_name(prefix, "Punto de salida ajustado"),
            "type": "vector",
        }

        self._polygonize_output(
            processing,
            result["output"],
            basin_vector,
            "basin",
            self._display_layer_name(prefix, "Cuenca"),
            "watershed_polygon",
            feedback,
            filter_expression='"basin" > 0',
        )
        self._derive_watershed_outputs(processing, output_dir, prefix, feedback)

    def _create_watershed_from_outlet_d8(self, processing, dem_layer, output_dir, prefix, feedback):
        model = getattr(self, "_d8_model", None)
        if not model:
            raise ValueError("No existe un modelo D8 interno calculado. Ejecuta primero Crear red con HidroGIS D8.")

        point = self._snapped_outlet_point(dem_layer)
        self._move_current_outlet_to_point(point, dem_layer.crs())
        basin_raster = prepare_output_path(output_dir / f"{prefix}_17_cuenca.tif", self._log)
        basin_vector = output_dir / f"{prefix}_18_cuenca.gpkg"
        snapped_point = output_dir / f"{prefix}_19_punto_salida_ajustado.gpkg"

        self._log(f"Delimitando cuenca con HidroGIS D8 desde punto ajustado: {point.x():.3f}, {point.y():.3f}")
        basin = self._d8_watershed_mask(model, point)
        self._write_d8_raster(model, basin.astype("int16"), basin_raster, "int", nodata=0)
        self.last_outputs["watershed_raster"] = {
            "path": basin_raster,
            "name": f"{prefix}_cuenca",
            "type": "raster",
        }

        self._save_point_layer(processing, point, dem_layer.crs(), snapped_point, f"{prefix}_punto_salida_ajustado")
        self.last_outputs["snapped_outlet"] = {
            "path": snapped_point,
            "name": self._display_layer_name(prefix, "Punto de salida ajustado"),
            "type": "vector",
        }

        self._polygonize_output(
            processing,
            basin_raster,
            basin_vector,
            "basin",
            self._display_layer_name(prefix, "Cuenca"),
            "watershed_polygon",
            feedback,
            filter_expression='"basin" > 0',
        )
        self._derive_watershed_outputs(processing, output_dir, prefix, feedback)

    def _d8_watershed_mask(self, model, outlet_point):
        np = model["np"]
        outlet_index = self._d8_index_from_point(model, outlet_point)
        if outlet_index is None:
            raise ValueError("No se pudo ubicar el punto de salida en el raster D8.")

        upstream = {}
        receivers = model["receivers"]
        valid_flat = model["valid_flat"]
        for index in model["valid_indices"]:
            index = int(index)
            receiver = int(receivers[index])
            if receiver >= 0 and valid_flat[receiver]:
                upstream.setdefault(receiver, []).append(index)

        selected = np.zeros(model["height"] * model["width"], dtype="bool")
        queue = deque([outlet_index])
        selected[outlet_index] = True
        while queue:
            current = queue.popleft()
            for donor in upstream.get(current, []):
                if selected[donor]:
                    continue
                selected[donor] = True
                queue.append(donor)

        if selected.sum() <= 1:
            self._log(
                "HidroGIS D8 genero una cuenca muy pequena. "
                "Revisa si el punto de salida esta sobre la red D8 o aumenta la distancia de snap."
            )
        return selected.reshape(model["height"], model["width"])

    def review_snapped_outlet(self):
        try:
            dem_layer = self._selected_dem()
            point = self._snapped_outlet_point(dem_layer)
            moved = self._move_current_outlet_to_point(point, dem_layer.crs())
            self._log(
                f"Punto ajustado para la delimitacion: X={point.x():.3f}, "
                f"Y={point.y():.3f}, CRS={dem_layer.crs().authid()}"
            )
            self.iface.messageBar().pushMessage(
                "HidroGIS Watershed Tools",
                "Punto ajustado y movido a la red." if moved else "Punto ajustado calculado.",
                level=Qgis.Success if moved else Qgis.Info,
                duration=6,
            )
        except Exception as exc:
            QMessageBox.warning(self, "No se pudo revisar el punto", str(exc))

    def _snapped_outlet_point(self, dem_layer):
        point, point_crs = self._selected_outlet_point()
        point = self._transform_point(point, point_crs, dem_layer.crs())
        stream_layer = self._snap_reference_stream_layer(dem_layer.crs())
        if stream_layer is None or self.snap_distance_spin.value() <= 0:
            return point

        snapped = self._nearest_point_on_stream(point, dem_layer.crs(), stream_layer, self.snap_distance_spin.value())
        return snapped or point

    def _selected_outlet_point(self):
        _, _, point, crs = self._selected_outlet_feature()
        return point, crs

    def _selected_outlet_feature(self):
        layer = self.outlet_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            raise ValueError("Selecciona o dibuja una capa de puntos de salida.")
        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
            raise ValueError("La capa de salida debe ser puntual.")

        features = list(layer.getSelectedFeatures())
        if not features:
            features = list(layer.getFeatures())
        if not features:
            raise ValueError("La capa de puntos de salida no tiene entidades.")
        if len(features) > 1:
            self._log("Hay varios puntos; se usara el primero. Selecciona uno para controlar la salida.")

        feature = features[0]
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            raise ValueError("El punto de salida seleccionado no tiene geometria.")
        if geom.isMultipart():
            point = geom.asMultiPoint()[0]
        else:
            point = geom.asPoint()
        return layer, feature, QgsPointXY(point), layer.crs()

    def _snap_reference_stream_layer(self, target_crs):
        stream_output = self.last_outputs.get("stream_vector")
        if stream_output:
            layer = QgsVectorLayer(stream_output["path"], stream_output["name"], "ogr")
            if layer.isValid():
                return layer

        layer = self.stream_layer_combo.currentLayer()
        if layer is not None and layer.isValid():
            return layer
        return None

    def _nearest_point_on_stream(self, point, point_crs, stream_layer, max_distance):
        point_in_stream_crs = self._transform_point(point, point_crs, stream_layer.crs())
        point_geom = QgsGeometry.fromPointXY(point_in_stream_crs)
        nearest_point = None
        nearest_distance = None

        for feature in stream_layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            distance = geom.distance(point_geom)
            if nearest_distance is None or distance < nearest_distance:
                candidate = geom.nearestPoint(point_geom)
                if candidate and not candidate.isEmpty():
                    nearest_distance = distance
                    nearest_point = candidate.asPoint()

        if nearest_point is None or nearest_distance is None or nearest_distance > max_distance:
            self._log("No se encontro red dentro de la distancia de snap; se usara el punto original.")
            return None

        self._log(f"Punto ajustado a la red. Distancia: {nearest_distance:.3f} unidades del CRS de la red.")
        return self._transform_point(QgsPointXY(nearest_point), stream_layer.crs(), point_crs)

    def _move_current_outlet_to_point(self, point, point_crs):
        try:
            layer, feature, _, _ = self._selected_outlet_feature()
        except Exception as exc:
            self._log(f"No se pudo mover el punto de salida: {exc}")
            return False

        target_point = self._transform_point(point, point_crs, layer.crs())
        target_geometry = QgsGeometry.fromPointXY(target_point)
        was_editing = layer.isEditable()

        if not was_editing and not layer.startEditing():
            self._log("El punto ajustado fue calculado, pero la capa de puntos no permite edicion.")
            return False

        if not layer.changeGeometry(feature.id(), target_geometry):
            self._log("El punto ajustado fue calculado, pero no se pudo actualizar la geometria.")
            if not was_editing:
                layer.rollBack()
            return False

        layer.updateExtents()
        layer.triggerRepaint()
        self.iface.mapCanvas().refresh()

        if not was_editing and not layer.commitChanges():
            self._log("No se pudo guardar el movimiento del punto en la capa de origen.")
            layer.rollBack()
            return False

        self._log(f"Punto de salida movido a X={target_point.x():.3f}, Y={target_point.y():.3f}.")
        return True

    def _save_point_layer(self, processing, point, crs, output_path, name):
        output_path = prepare_output_path(output_path, self._log)
        layer = QgsVectorLayer(f"Point?crs={crs.authid()}", name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.Int), QgsField("tipo", QVariant.String)])
        layer.updateFields()
        feature = QgsFeature(layer.fields())
        feature.setAttributes([1, "outlet_snap"])
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        provider.addFeature(feature)
        layer.updateExtents()
        processing.run("native:savefeatures", {"INPUT": layer, "OUTPUT": output_path})

    def _polygonize_output(
        self,
        processing,
        raster_path,
        output_path,
        field_name,
        layer_name,
        output_key,
        feedback,
        filter_expression=None,
    ):
        output_path = prepare_output_path(output_path, self._log)
        self._log(f"Vectorizando {layer_name}...")
        polygonize_target = output_path
        if filter_expression:
            raw_path = Path(output_path)
            polygonize_target = prepare_output_path(
                raw_path.with_name(f"{raw_path.stem}_sin_filtrar{raw_path.suffix}"),
                self._log,
            )

        polygonized = processing.run(
            "gdal:polygonize",
            {
                "INPUT": raster_path,
                "BAND": 1,
                "FIELD": field_name,
                "EIGHT_CONNECTEDNESS": False,
                "EXTRA": "",
                "OUTPUT": polygonize_target,
            },
            feedback=feedback,
        )

        final_output = polygonized["OUTPUT"]
        if filter_expression:
            self._log(f"Filtrando {layer_name} con expresion: {filter_expression}")
            filtered = processing.run(
                "native:extractbyexpression",
                {
                    "INPUT": polygonized["OUTPUT"],
                    "EXPRESSION": filter_expression,
                    "OUTPUT": output_path,
                },
                feedback=feedback,
            )
            final_output = filtered["OUTPUT"]
            discard_output_path(polygonized["OUTPUT"], self._log)

        self.last_outputs[output_key] = {
            "path": final_output,
            "name": layer_name,
            "type": "vector",
        }

    def _derive_watershed_outputs(self, processing, output_dir, prefix, feedback):
        watershed = self.last_outputs.get("watershed_polygon")
        streams = self.last_outputs.get("stream_vector")
        if not watershed or not streams:
            self._log("No se pudieron crear salidas recortadas porque falta la cuenca o la red de drenaje.")
            return

        self._clip_vector_output(
            processing,
            streams["path"],
            watershed["path"],
            output_dir / f"{prefix}_21_red_drenaje_cuenca.gpkg",
            self._display_layer_name(prefix, "Red de drenaje"),
            "watershed_stream_vector",
            feedback,
        )
        if self.export_stream_shp_check.isChecked() and "watershed_stream_vector" in self.last_outputs:
            self._export_vector_output(
                processing,
                self.last_outputs["watershed_stream_vector"]["path"],
                output_dir / f"{prefix}_21_red_drenaje_cuenca.shp",
                self._display_layer_name(prefix, "Red de drenaje"),
                "watershed_stream_shp",
                feedback,
            )

    def _clip_vector_output(self, processing, source_path, overlay_path, output_path, layer_name, output_key, feedback):
        output_path = prepare_output_path(output_path, self._log)
        self._log(f"Recortando {layer_name} a la cuenca delimitada...")
        source_layer = QgsVectorLayer(source_path, layer_name, "ogr")
        overlay_layer = QgsVectorLayer(overlay_path, "cuenca_recorte", "ogr")
        if not source_layer.isValid():
            self._log(f"No se pudo recortar {layer_name}: la capa fuente no es valida.")
            return
        if not overlay_layer.isValid():
            self._log(f"No se pudo recortar {layer_name}: la cuenca de recorte no es valida.")
            return

        result = processing.run(
            "native:clip",
            {
                "INPUT": source_layer,
                "OVERLAY": overlay_layer,
                "OUTPUT": output_path,
            },
            feedback=feedback,
        )
        if output_key:
            self.last_outputs[output_key] = {
                "path": result["OUTPUT"],
                "name": layer_name,
                "type": "vector",
            }
        return result["OUTPUT"]

    def _postprocess_subunits(self, processing, source_path, output_path, layer_name, output_key, feedback):
        source_layer = QgsVectorLayer(source_path, f"{layer_name}_recorte", "ogr")
        if not source_layer.isValid():
            self._log("No se pudo postprocesar subunidades: la capa recortada no es valida.")
            return
        if QgsWkbTypes.geometryType(source_layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
            self._log("No se pudo postprocesar subunidades: la capa no es poligonal.")
            return

        self._log("Disolviendo subunidades por codigo hidrologico...")
        units = self._dissolved_subunit_units(source_layer)
        if not units:
            self._log("No se encontraron subunidades validas para postprocesar.")
            return

        before_count = len(units)
        min_area_m2 = self.min_subunit_area_spin.value() * 1000000.0
        if self.merge_small_subunits_check.isChecked() and min_area_m2 > 0:
            units, merged_count = self._merge_small_subunit_units(units, min_area_m2)
            self._log(
                f"Fusion de subunidades pequenas: {merged_count} unidad(es) menor(es) a "
                f"{self.min_subunit_area_spin.value():.4f} km2."
            )
        else:
            self._log("Fusion de subunidades pequenas omitida.")

        output_path = prepare_output_path(output_path, self._log)
        memory_layer = QgsVectorLayer(f"MultiPolygon?crs={source_layer.crs().authid()}", layer_name, "memory")
        provider = memory_layer.dataProvider()
        provider.addAttributes(
            [
                QgsField("sub_num", QVariant.Int),
                QgsField("sub_id", QVariant.String),
                QgsField("subbasin", QVariant.String),
                QgsField("area_km2", QVariant.Double),
                QgsField("area_ha", QVariant.Double),
            ]
        )
        memory_layer.updateFields()

        sub_prefix = self._safe_subunit_prefix(self.subunit_prefix_edit.text())
        width = max(2, len(str(len(units))))
        for index, unit in enumerate(self._sort_subunit_units(units), 1):
            geom = self._make_valid_geometry(unit["geometry"])
            if geom is None or geom.isEmpty():
                continue
            area_m2 = geom.area()
            feature = QgsFeature(memory_layer.fields())
            feature.setGeometry(geom)
            feature.setAttributes(
                [
                    index,
                    f"{sub_prefix}-{index:0{width}d}",
                    ",".join(str(value) for value in unit["subbasins"]),
                    area_m2 / 1000000.0,
                    area_m2 / 10000.0,
                ]
            )
            provider.addFeature(feature)

        memory_layer.updateExtents()
        saved = processing.run(
            "native:savefeatures",
            {
                "INPUT": memory_layer,
                "OUTPUT": output_path,
            },
            feedback=feedback,
        )
        self.last_outputs[output_key] = {
            "path": saved["OUTPUT"],
            "name": layer_name,
            "type": "vector",
        }
        self._log(f"Subunidades finales: {memory_layer.featureCount()} de {before_count} unidad(es) disuelta(s).")

    def _dissolved_subunit_units(self, layer):
        subbasin_index = layer.fields().lookupField("subbasin")
        groups = {}
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            key = feature[subbasin_index] if subbasin_index >= 0 else feature.id()
            if key in (None, ""):
                key = feature.id()
            groups.setdefault(key, []).append((feature.id(), QgsGeometry(geom)))

        units = []
        for key, items in groups.items():
            geometry = self._combine_geometries([item[1] for item in items])
            if geometry is None or geometry.isEmpty():
                continue
            units.append(
                {
                    "geometry": geometry,
                    "subbasins": [key],
                    "orig_ids": [item[0] for item in items],
                    "merged": False,
                }
            )
        return units

    def _merge_small_subunit_units(self, units, min_area_m2):
        units = list(units)
        merged_count = 0
        while len(units) > 1:
            small_index = None
            small_area = None
            for index, unit in enumerate(units):
                area = unit["geometry"].area()
                if area >= min_area_m2:
                    continue
                if small_area is None or area < small_area:
                    small_area = area
                    small_index = index

            if small_index is None:
                break

            target_index = self._best_merge_target_index(units, small_index)
            if target_index is None:
                break

            small_unit = units.pop(small_index)
            if small_index < target_index:
                target_index -= 1
            target_unit = units[target_index]
            target_unit["geometry"] = self._combine_geometries([target_unit["geometry"], small_unit["geometry"]])
            target_unit["subbasins"].extend(small_unit["subbasins"])
            target_unit["orig_ids"].extend(small_unit["orig_ids"])
            target_unit["merged"] = True
            merged_count += 1

        return units, merged_count

    def _best_merge_target_index(self, units, small_index):
        small_geom = units[small_index]["geometry"]
        best_index = None
        best_shared_length = -1.0
        best_distance = None

        for index, unit in enumerate(units):
            if index == small_index:
                continue
            geom = unit["geometry"]
            shared_length = self._shared_boundary_length(small_geom, geom)
            distance = small_geom.distance(geom)
            if (
                shared_length > best_shared_length
                or (shared_length == best_shared_length and (best_distance is None or distance < best_distance))
            ):
                best_index = index
                best_shared_length = shared_length
                best_distance = distance

        return best_index

    def _shared_boundary_length(self, geom_a, geom_b):
        try:
            shared = geom_a.boundary().intersection(geom_b.boundary())
            if shared is None or shared.isEmpty():
                return 0.0
            return shared.length()
        except Exception:
            return 0.0

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

    def _sort_subunit_units(self, units):
        def key(unit):
            centroid = unit["geometry"].centroid()
            if centroid is None or centroid.isEmpty():
                return (0, 0)
            point = centroid.asPoint()
            return (-point.y(), point.x())

        return sorted(units, key=key)

    def _export_vector_output(self, processing, source_path, output_path, layer_name, output_key, feedback):
        output_path = prepare_output_path(output_path, self._log)
        source_layer = QgsVectorLayer(source_path, layer_name, "ogr")
        if not source_layer.isValid():
            self._log(f"No se pudo exportar {layer_name}: la capa fuente no es valida.")
            return
        if QgsWkbTypes.geometryType(source_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            geometry_name = QgsWkbTypes.displayString(source_layer.wkbType())
            self._log(f"No se exporto {layer_name}: la geometria no es de lineas ({geometry_name}).")
            return

        self._log(f"Exportando {layer_name} a Shapefile...")
        try:
            result = processing.run(
                "native:savefeatures",
                {
                    "INPUT": source_layer,
                    "OUTPUT": output_path,
                },
                feedback=feedback,
            )
        except Exception as exc:
            self._log(f"No se pudo exportar Shapefile; se usara GeoPackage. Detalle: {exc}")
            return

        self.last_outputs[output_key] = {
            "path": result["OUTPUT"],
            "name": layer_name,
            "type": "vector",
        }

    def _require_line_vector_output(self, source_path, layer_name):
        layer = QgsVectorLayer(source_path, layer_name, "ogr")
        if not layer.isValid():
            raise ValueError(f"No se pudo abrir la red de drenaje vectorial generada: {source_path}")

        geometry_type = QgsWkbTypes.geometryType(layer.wkbType())
        if geometry_type == QgsWkbTypes.LineGeometry:
            return source_path

        geometry_name = QgsWkbTypes.displayString(layer.wkbType())
        raise ValueError(
            "La red de drenaje se genero como geometria "
            f"{geometry_name}, no como polilinea. Vuelve a ejecutar con esta version actualizada; "
            "si persiste, revisa que el proveedor GRASS de QGIS este actualizado."
        )

    def _log_vector_feature_count(self, source_path, layer_name):
        layer = QgsVectorLayer(source_path, layer_name, "ogr")
        if not layer.isValid():
            self._log(f"No se pudo validar la red vectorial: {source_path}")
            return
        count = layer.featureCount()
        if count == 0:
            self._log(
                "La red de drenaje no tiene tramos. Prueba con un umbral de red menor "
                "o revisa que el DEM tenga CRS proyectado, valores de elevacion validos y NoData correcto."
            )
        else:
            self._log(f"Red de drenaje generada con {count} tramos.")

    def _selected_dem(self):
        layer = self.dem_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            raise ValueError("Selecciona un DEM raster valido.")
        return layer

    def _grass_algorithm_id(self, name):
        registry = QgsApplication.processingRegistry()
        for provider_id in ("grass", "grass7"):
            algorithm_id = f"{provider_id}:{name}"
            if registry.algorithmById(algorithm_id) is not None:
                return algorithm_id
        raise ValueError(
            "No se encontro el proveedor GRASS en Processing. "
            "Activa 'GRASS GIS Processing Provider' en los complementos de QGIS."
        )

    def _add_outputs_to_project(self, outputs):
        for item in outputs:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not path:
                continue
            add_or_replace_layer(path, item.get("name", Path(path).stem), item.get("type", "raster"), self._log)

    def _remove_reference_layers_from_project(self):
        patterns = (
            "subcuencas",
            "red_drenaje",
            "hidrogis_cuenca",
        )
        keep_suffixes = ("cuenca", "red de drenaje")
        remove_ids = []
        for layer in QgsProject.instance().mapLayers().values():
            name = layer.name().lower()
            if any(name == suffix or name.endswith(f"_{suffix}") for suffix in keep_suffixes):
                continue
            if any(pattern in name for pattern in patterns):
                remove_ids.append(layer.id())
        if remove_ids:
            QgsProject.instance().removeMapLayers(remove_ids)

    def _visible_outputs(self, only_streams):
        if self.add_intermediate_check.isChecked():
            hidden_keys = {"subbasins_raster", "subbasins_polygon", "watershed_subbasins"}
            return [item for key, item in self.last_outputs.items() if key not in hidden_keys]

        if only_streams:
            keys = ["stream_vector_shp" if "stream_vector_shp" in self.last_outputs else "stream_vector"]
        else:
            keys = [
                "watershed_polygon",
                "watershed_stream_shp" if "watershed_stream_shp" in self.last_outputs else "watershed_stream_vector",
            ]
        if self.add_hydrologic_dem_check.isChecked() and "hydrologic_dem" in self.last_outputs:
            keys.insert(0, "hydrologic_dem")
        return [self.last_outputs[key] for key in keys if key in self.last_outputs]

    def _grass_region(self, layer):
        extent = layer.extent()
        crs = layer.crs().authid()
        return (
            f"{extent.xMinimum()},{extent.xMaximum()},"
            f"{extent.yMinimum()},{extent.yMaximum()} [{crs}]"
        )

    def _transform_point(self, point, source_crs, target_crs):
        if not isinstance(source_crs, QgsCoordinateReferenceSystem):
            source_crs = QgsCoordinateReferenceSystem(source_crs)
        if not isinstance(target_crs, QgsCoordinateReferenceSystem):
            target_crs = QgsCoordinateReferenceSystem(target_crs)
        if source_crs == target_crs:
            return QgsPointXY(point)
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        return transform.transform(QgsPointXY(point))

    def _is_projected_crs(self, crs):
        if hasattr(crs, "isProjected"):
            return crs.isProjected()
        if hasattr(crs, "isGeographic"):
            return not crs.isGeographic()
        return crs.mapUnits() != QgsUnitTypes.DistanceDegrees

    def _safe_prefix(self, text):
        prefix = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text.strip())
        prefix = prefix.strip("_-")
        return prefix or "hidrogis_cuenca"

    def _safe_subunit_prefix(self, text):
        prefix = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text.strip())
        return prefix or "SUB"

    def _display_layer_name(self, prefix, description):
        if not prefix or prefix.lower().startswith("hidrogis"):
            return description
        return f"{prefix}_{description}"
