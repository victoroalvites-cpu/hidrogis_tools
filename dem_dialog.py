from pathlib import Path
from urllib.parse import urlencode, urlparse

from qgis.PyQt.QtCore import Qt, QEventLoop, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsNetworkAccessManager


from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsMapLayerProxyModel,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsMapLayerComboBox, QgsProjectionSelectionWidget

from .output_utils import add_or_replace_layer, prepare_output_path


class TextFeedback(QgsProcessingFeedback):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger

    def pushInfo(self, info):
        self.logger(info)
        super().pushInfo(info)

    def reportError(self, error, fatalError=False):
        self.logger(error)
        super().reportError(error, fatalError)

    def setProgressText(self, text):
        self.logger(text)
        super().setProgressText(text)


class DemPreprocessDialog(QWidget):
    OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"
    GDAL_MERGE_FLOAT32 = 5
    GDAL_RASTER_FLOAT32 = 6

    DEM_TYPES = {
        "SRTM 30 m (SRTMGL1)": "SRTMGL1",
        "SRTM 90 m (SRTMGL3)": "SRTMGL3",
        "ALOS World 3D 30 m (AW3D30)": "AW3D30",
        "Copernicus 30 m (COP30)": "COP30",
        "Copernicus 90 m (COP90)": "COP90",
    }

    def _download_file(self, url, output_path):
        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise ValueError("Solo se permiten descargas mediante HTTPS.")

        if parsed.netloc.lower() != "portal.opentopography.org":
            raise ValueError("Dominio de descarga no permitido.")

        request = QNetworkRequest(QUrl(url))
        manager = QgsNetworkAccessManager.instance()
        reply = manager.get(request)

        loop = QEventLoop()
        reply.finished.connect(loop.quit)
        loop.exec_()

        try:
            if reply.error():
                raise ValueError(f"Error descargando DEM: {reply.errorString()}")

            data = reply.readAll()
            if data.isEmpty():
                raise ValueError("La descarga no devolvió contenido.")

            with open(output_path, "wb") as file:
                file.write(bytes(data))

        finally:
            reply.deleteLater()

    def __init__(self, iface, parent=None, show_close_button=True):
        super().__init__(parent)
        self.iface = iface
        self.show_close_button = show_close_button
        self.setWindowTitle("HidroGIS Watershed Tools - Descargar y preprocesar DEM")
        self.resize(760, 700)
        self._build_ui()
        self.refresh_layers()

    def _build_ui(self):
        root = QVBoxLayout(self)

        source_group = QGroupBox("1. Fuente del DEM")
        source_layout = QFormLayout(source_group)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Descargar desde OpenTopography", "Usar rasters locales"])
        self.dem_type_combo = QComboBox()
        self.dem_type_combo.addItems(self.DEM_TYPES.keys())
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("API key de OpenTopography")
        self.local_rasters = QListWidget()
        self.local_rasters.setMinimumHeight(90)
        raster_buttons = QHBoxLayout()
        self.add_raster_button = QPushButton("Agregar rasters")
        self.remove_raster_button = QPushButton("Quitar seleccionados")
        raster_buttons.addWidget(self.add_raster_button)
        raster_buttons.addWidget(self.remove_raster_button)
        source_layout.addRow("Modo", self.source_combo)
        source_layout.addRow("DEM global", self.dem_type_combo)
        source_layout.addRow("API key", self.api_key_edit)
        source_layout.addRow("Rasters locales", self.local_rasters)
        source_layout.addRow("", raster_buttons)

        area_group = QGroupBox("2. Area de trabajo")
        area_layout = QFormLayout(area_group)
        self.area_mode_combo = QComboBox()
        self.area_mode_combo.addItems(
            [
                "Extension actual del mapa",
                "Extension de capa poligonal",
                "Poligonos seleccionados",
            ]
        )
        self.polygon_layer_combo = QgsMapLayerComboBox()
        self.polygon_layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.clip_mode_combo = QComboBox()
        self.clip_mode_combo.addItems(["Recortar por extension", "Recortar por poligono", "No recortar"])
        area_layout.addRow("Area", self.area_mode_combo)
        area_layout.addRow("Capa poligonal", self.polygon_layer_combo)
        area_layout.addRow("Recorte final", self.clip_mode_combo)

        output_group = QGroupBox("3. Salida y reproyeccion")
        output_layout = QFormLayout(output_group)
        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setCrs(QgsProject.instance().crs())
        self.output_folder_edit = QLineEdit(str(Path.home()))
        self.output_folder_button = QPushButton("Examinar")
        output_folder_row = QHBoxLayout()
        output_folder_row.addWidget(self.output_folder_edit)
        output_folder_row.addWidget(self.output_folder_button)
        self.prefix_edit = QLineEdit("hidrogis_dem")
        self.add_result_check = QCheckBox("Agregar resultado al proyecto")
        self.add_result_check.setChecked(True)
        output_layout.addRow("CRS destino", self.crs_widget)
        output_layout.addRow("Carpeta de salida", output_folder_row)
        output_layout.addRow("Prefijo", self.prefix_edit)
        output_layout.addRow("", self.add_result_check)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.run_button = QPushButton("Ejecutar")
        button_row.addWidget(self.run_button)
        if self.show_close_button:
            self.close_button = QPushButton("Cerrar")
            button_row.addWidget(self.close_button)
        else:
            self.close_button = None

        root.addWidget(source_group)
        root.addWidget(area_group)
        root.addWidget(output_group)
        root.addWidget(QLabel("Registro"))
        root.addWidget(self.log)
        root.addLayout(button_row)

        self.source_combo.currentIndexChanged.connect(self._sync_enabled_state)
        self.area_mode_combo.currentIndexChanged.connect(self._sync_enabled_state)
        self.clip_mode_combo.currentIndexChanged.connect(self._sync_enabled_state)
        self.output_folder_button.clicked.connect(self._choose_output_folder)
        self.add_raster_button.clicked.connect(self._add_local_rasters)
        self.remove_raster_button.clicked.connect(self._remove_local_rasters)
        self.run_button.clicked.connect(self.run_workflow)
        if self.close_button is not None:
            self.close_button.clicked.connect(self.close)
        self._sync_enabled_state()

    def refresh_layers(self):
        self.polygon_layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)

    def _sync_enabled_state(self):
        download_mode = self.source_combo.currentIndex() == 0
        polygon_needed = self.area_mode_combo.currentIndex() in (1, 2) or self.clip_mode_combo.currentIndex() == 1
        self.dem_type_combo.setEnabled(download_mode)
        self.api_key_edit.setEnabled(download_mode)
        self.local_rasters.setEnabled(not download_mode)
        self.add_raster_button.setEnabled(not download_mode)
        self.remove_raster_button.setEnabled(not download_mode)
        self.polygon_layer_combo.setEnabled(polygon_needed)

    def _choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def set_output_folder(self, folder):
        self.output_folder_edit.setText(str(folder))

    def _add_local_rasters(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar rasters DEM",
            "",
            "Rasters (*.tif *.tiff *.vrt *.img *.asc);;Todos los archivos (*.*)",
        )
        for file_path in files:
            if not self.local_rasters.findItems(file_path, Qt.MatchExactly):
                self.local_rasters.addItem(file_path)

    def _remove_local_rasters(self):
        for item in self.local_rasters.selectedItems():
            self.local_rasters.takeItem(self.local_rasters.row(item))

    def _log(self, message):
        self.log.appendPlainText(str(message))

    def run_workflow(self):
        try:
            import processing
        except ImportError:
            QMessageBox.critical(self, "Processing no disponible", "No se pudo cargar el modulo Processing de QGIS.")
            return

        self.log.clear()
        self.run_button.setEnabled(False)
        try:
            output_dir = Path(self.output_folder_edit.text()).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
            prefix = self._safe_prefix(self.prefix_edit.text())
            target_crs = self.crs_widget.crs()
            if not target_crs.isValid():
                raise ValueError("Selecciona un CRS destino valido.")

            feedback = TextFeedback(self._log)
            source_rasters = self._prepare_source_rasters(output_dir, prefix)
            if not source_rasters:
                raise ValueError("No hay rasters DEM para procesar.")

            current = self._merge_if_needed(processing, source_rasters, output_dir, prefix, feedback)
            current = self._reproject(processing, current, target_crs, output_dir, prefix, feedback)
            current = self._clip(processing, current, target_crs, output_dir, prefix, feedback)

            if self.add_result_check.isChecked():
                add_or_replace_layer(current, self._dem_layer_name(current, prefix), "raster", self._log)

            self._log("")
            self._log(f"Listo: {current}")
            self.iface.messageBar().pushMessage(
                "HidroGIS Watershed Tools",
                "Preprocesamiento terminado.",
                level=Qgis.Success,
                duration=6,
            )
        except Exception as exc:
            self._log(f"ERROR: {exc}")
            QMessageBox.critical(self, "Error en el procesamiento", str(exc))
        finally:
            self.run_button.setEnabled(True)

    def _safe_prefix(self, text):
        prefix = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text.strip())
        prefix = prefix.strip("_-")
        return prefix or "hidrogis_dem"

    def _dem_layer_name(self, path, prefix):
        name = Path(path).stem.lower()
        if "recortado" in name:
            return self._display_layer_name(prefix, "DEM recortado")
        if "reproyectado" in name:
            return self._display_layer_name(prefix, "DEM reproyectado")
        if "mosaico" in name:
            return self._display_layer_name(prefix, "DEM mosaico")
        return self._display_layer_name(prefix, "DEM")

    def _display_layer_name(self, prefix, description):
        if not prefix or prefix.lower().startswith("hidrogis"):
            return description
        return f"{prefix}_{description}"

    def _prepare_source_rasters(self, output_dir, prefix):
        if self.source_combo.currentIndex() == 0:
            bbox = self._area_extent_4326()
            dem_type = self.DEM_TYPES[self.dem_type_combo.currentText()]
            raw_path = output_dir / f"{prefix}_{dem_type}_raw.tif"
            prepare_output_path(raw_path, self._log)
            self._download_opentopography(dem_type, bbox, raw_path)
            return [str(raw_path)]

        rasters = [self.local_rasters.item(row).text() for row in range(self.local_rasters.count())]
        missing = [path for path in rasters if not Path(path).exists()]
        if missing:
            raise ValueError("Estos rasters no existen: " + ", ".join(missing))
        return rasters

    def _download_opentopography(self, dem_type, bbox, output_path):
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            raise ValueError("OpenTopography requiere una API key para descargar DEM globales.")

        west, south, east, north = bbox
        params = {
            "demtype": dem_type,
            "south": f"{south:.8f}",
            "north": f"{north:.8f}",
            "west": f"{west:.8f}",
            "east": f"{east:.8f}",
            "outputFormat": "GTiff",
            "API_Key": api_key,
        }
        url = f"{self.OPENTOPO_URL}?{urlencode(params)}"
        self._log(f"Descargando DEM {dem_type} desde OpenTopography...")
        self._log(f"BBOX EPSG:4326: oeste={west:.6f}, sur={south:.6f}, este={east:.6f}, norte={north:.6f}")
        self._download_file(url, output_path)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ValueError("La descarga no genero un archivo valido.")

        downloaded = QgsRasterLayer(str(output_path), "dem_descargado")
        if not downloaded.isValid():
            response_preview = output_path.read_bytes()[:500].decode("utf-8", errors="replace")
            raise ValueError(
                "La respuesta de OpenTopography no es un raster valido. "
                f"Revisa la API key, el area solicitada o el tipo de DEM. Respuesta: {response_preview}"
            )
        self._log(f"Descarga guardada: {output_path}")

    def _merge_if_needed(self, processing, rasters, output_dir, prefix, feedback):
        if len(rasters) == 1:
            self._log("Mosaico omitido: solo hay un raster de entrada.")
            return rasters[0]

        output = prepare_output_path(output_dir / f"{prefix}_01_mosaico.tif", self._log)
        self._log("Uniendo rasters mediante mosaico...")
        result = processing.run(
            "gdal:merge",
            {
                "INPUT": rasters,
                "PCT": False,
                "SEPARATE": False,
                "NODATA_INPUT": None,
                "NODATA_OUTPUT": -9999,
                "OPTIONS": "",
                "EXTRA": "",
                "DATA_TYPE": self.GDAL_MERGE_FLOAT32,
                "OUTPUT": output,
            },
            feedback=feedback,
        )
        return result["OUTPUT"]

    def _reproject(self, processing, raster, target_crs, output_dir, prefix, feedback):
        output = prepare_output_path(output_dir / f"{prefix}_02_reproyectado.tif", self._log)
        self._log(f"Reproyectando a {target_crs.authid()}...")
        result = processing.run(
            "gdal:warpreproject",
            {
                "INPUT": raster,
                "SOURCE_CRS": None,
                "TARGET_CRS": target_crs,
                "RESAMPLING": 1,
                "NODATA": -9999,
                "TARGET_RESOLUTION": None,
                "OPTIONS": "",
                "DATA_TYPE": self.GDAL_RASTER_FLOAT32,
                "TARGET_EXTENT": None,
                "TARGET_EXTENT_CRS": None,
                "MULTITHREADING": True,
                "EXTRA": "",
                "OUTPUT": output,
            },
            feedback=feedback,
        )
        return result["OUTPUT"]

    def _clip(self, processing, raster, target_crs, output_dir, prefix, feedback):
        mode = self.clip_mode_combo.currentIndex()
        if mode == 2:
            self._log("Recorte omitido.")
            return raster

        output = prepare_output_path(output_dir / f"{prefix}_03_recortado.tif", self._log)
        if mode == 0:
            extent = self._area_extent_in_crs(target_crs)
            self._log("Recortando por extension...")
            result = processing.run(
                "gdal:cliprasterbyextent",
                {
                    "INPUT": raster,
                    "PROJWIN": extent,
                    "OVERCRS": False,
                    "NODATA": -9999,
                    "OPTIONS": "",
                    "DATA_TYPE": self.GDAL_RASTER_FLOAT32,
                    "EXTRA": "",
                    "OUTPUT": output,
                },
                feedback=feedback,
            )
            return result["OUTPUT"]

        mask_layer = self._mask_layer_for_clip(processing, output_dir, prefix, feedback)
        self._log("Recortando por poligono...")
        result = processing.run(
            "gdal:cliprasterbymasklayer",
            {
                "INPUT": raster,
                "MASK": mask_layer,
                "SOURCE_CRS": target_crs,
                "TARGET_CRS": target_crs,
                "NODATA": -9999,
                "ALPHA_BAND": False,
                "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True,
                "SET_RESOLUTION": False,
                "X_RESOLUTION": None,
                "Y_RESOLUTION": None,
                "MULTITHREADING": True,
                "OPTIONS": "",
                "DATA_TYPE": self.GDAL_RASTER_FLOAT32,
                "EXTRA": "",
                "OUTPUT": output,
            },
            feedback=feedback,
        )
        return result["OUTPUT"]

    def _mask_layer_for_clip(self, processing, output_dir, prefix, feedback):
        layer = self._selected_polygon_layer()
        if self.area_mode_combo.currentIndex() != 2:
            return layer

        if layer.selectedFeatureCount() == 0:
            raise ValueError("El recorte por poligonos seleccionados requiere al menos una entidad seleccionada.")

        mask_path = prepare_output_path(output_dir / f"{prefix}_mask_seleccion.gpkg", self._log)
        self._log("Guardando poligonos seleccionados como mascara temporal...")
        result = processing.run(
            "native:saveselectedfeatures",
            {
                "INPUT": layer,
                "OUTPUT": mask_path,
            },
            feedback=feedback,
        )
        return result["OUTPUT"]

    def _selected_polygon_layer(self):
        layer = self.polygon_layer_combo.currentLayer()
        if layer is None or not layer.isValid():
            raise ValueError("Selecciona una capa poligonal valida.")
        if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
            raise ValueError("La capa seleccionada no es poligonal.")
        return layer

    def _area_extent_4326(self):
        return self._extent_tuple(self._area_extent_in_crs(QgsCoordinateReferenceSystem("EPSG:4326")))

    def _area_extent_in_crs(self, target_crs):
        source_extent, source_crs = self._raw_area_extent()
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        return transform.transformBoundingBox(source_extent)

    def _raw_area_extent(self):
        mode = self.area_mode_combo.currentIndex()
        if mode == 0:
            canvas = self.iface.mapCanvas()
            return QgsRectangle(canvas.extent()), canvas.mapSettings().destinationCrs()

        layer = self._selected_polygon_layer()
        if mode == 1:
            return QgsRectangle(layer.extent()), layer.crs()

        selected_count = layer.selectedFeatureCount()
        if selected_count == 0:
            raise ValueError("El modo de poligonos seleccionados requiere al menos una entidad seleccionada.")

        extent = QgsRectangle()
        extent.setMinimal()
        request = QgsFeatureRequest().setNoAttributes()
        for feature in layer.getSelectedFeatures(request):
            geom = feature.geometry()
            if geom and not geom.isEmpty():
                extent.combineExtentWith(geom.boundingBox())
        if extent.isEmpty():
            raise ValueError("No se pudo obtener la extension de los poligonos seleccionados.")
        return extent, layer.crs()

    def _extent_tuple(self, rectangle):
        west = min(rectangle.xMinimum(), rectangle.xMaximum())
        east = max(rectangle.xMinimum(), rectangle.xMaximum())
        south = min(rectangle.yMinimum(), rectangle.yMaximum())
        north = max(rectangle.yMinimum(), rectangle.yMaximum())
        if west == east or south == north:
            raise ValueError("La extension del area de trabajo es invalida.")
        return west, south, east, north
