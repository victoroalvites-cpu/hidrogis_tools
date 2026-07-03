from pathlib import Path
import gc

from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsApplication,
    QgsColorRampShader,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsProject,
    QgsRasterBandStats,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
    QgsWkbTypes,
)


SHAPEFILE_EXTENSIONS = [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".qpj",
    ".qix",
    ".sbn",
    ".sbx",
    ".fix",
    ".shp.xml",
]

RASTER_AUX_EXTENSIONS = {
    ".aux.xml",
    ".ovr",
    ".msk",
    ".xml",
}


def prepare_output_path(path, logger=None):
    target = Path(path)
    remove_project_layers_for_paths(_related_paths(target))
    try:
        _delete_related_files(target, logger)
        return str(target)
    except PermissionError as exc:
        fallback = _available_fallback_path(target)
        if logger is not None:
            logger(
                f"{exc} Se continuara automaticamente escribiendo una salida alternativa: {fallback}"
            )
        remove_project_layers_for_paths(_related_paths(fallback))
        _delete_related_files(fallback, logger)
        return str(fallback)


def add_or_replace_layer(path, name, layer_type, logger=None):
    remove_project_layers_for_paths(_related_paths(Path(path)))
    remove_project_layers_by_name(name)
    if layer_type == "vector":
        layer = QgsVectorLayer(str(path), name, "ogr")
    else:
        layer = QgsRasterLayer(str(path), name)

    if layer.isValid():
        apply_default_style(layer, name, layer_type, logger)
        QgsProject.instance().addMapLayer(layer)
        return True

    if logger is not None:
        logger(f"No se pudo cargar automaticamente: {path}")
    return False


def apply_default_style(layer, name, layer_type, logger=None):
    try:
        if layer_type == "raster":
            _apply_dem_raster_style(layer, name)
        elif layer_type == "vector":
            _apply_vector_style(layer, name)
    except Exception as exc:
        if logger is not None:
            logger(f"No se pudo aplicar simbologia automatica a {name}: {exc}")


def _apply_dem_raster_style(layer, name):
    lowered = name.lower()
    if not any(word in lowered for word in ("dem", "reproyectado", "recortado", "rellenado", "reacondicionado")):
        return

    provider = layer.dataProvider()
    if hasattr(provider, "reloadData"):
        provider.reloadData()
    stats = provider.bandStatistics(
        1,
        QgsRasterBandStats.Min | QgsRasterBandStats.Max,
        layer.extent(),
        0,
    )
    min_value = stats.minimumValue
    max_value = stats.maximumValue
    if min_value is None or max_value is None or min_value == max_value:
        return

    span = max_value - min_value
    ramp = QgsColorRampShader()
    ramp.setColorRampType(QgsColorRampShader.Interpolated)
    ramp.setColorRampItemList(
        [
            QgsColorRampShader.ColorRampItem(min_value, QColor("#1f78b4"), "Bajo"),
            QgsColorRampShader.ColorRampItem(min_value + span * 0.25, QColor("#33a02c"), "Medio bajo"),
            QgsColorRampShader.ColorRampItem(min_value + span * 0.50, QColor("#f1e05a"), "Medio"),
            QgsColorRampShader.ColorRampItem(min_value + span * 0.75, QColor("#b15928"), "Medio alto"),
            QgsColorRampShader.ColorRampItem(max_value, QColor("#f7f7f7"), "Alto"),
        ]
    )
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
    if hasattr(renderer, "setClassificationMin"):
        renderer.setClassificationMin(min_value)
    if hasattr(renderer, "setClassificationMax"):
        renderer.setClassificationMax(max_value)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def _apply_vector_style(layer, name):
    geometry_type = QgsWkbTypes.geometryType(layer.wkbType())
    lowered = name.lower()

    if geometry_type == QgsWkbTypes.LineGeometry:
        if "axial" in lowered or "maximo" in lowered or "recorrido" in lowered:
            color = "#ff7f00"
            width = "0.75"
        elif "cauce" in lowered or "drenaje" in lowered or "red" in lowered:
            color = "#0066ff"
            width = "0.65"
        else:
            color = "#222222"
            width = "0.35"
        symbol = QgsLineSymbol.createSimple({"color": color, "width": width, "width_unit": "MM"})
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()
        return

    if geometry_type == QgsWkbTypes.PolygonGeometry:
        if "cuenca" in lowered and "sub" not in lowered:
            symbol = QgsFillSymbol.createSimple(
                {
                    "style": "no",
                    "outline_color": "#d7191c",
                    "outline_width": "0.85",
                    "outline_width_unit": "MM",
                }
            )
        elif "subunidad" in lowered or "subcuenca" in lowered:
            symbol = QgsFillSymbol.createSimple(
                {
                    "style": "no",
                    "outline_color": "#111111",
                    "outline_width": "0.45",
                    "outline_width_unit": "MM",
                }
            )
        else:
            symbol = QgsFillSymbol.createSimple(
                {
                    "style": "solid",
                    "color": "#f4a3b5",
                    "outline_color": "#333333",
                    "outline_width": "0.25",
                    "outline_width_unit": "MM",
                }
            )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()


def discard_output_path(path, logger=None):
    target = Path(path)
    remove_project_layers_for_paths(_related_paths(target))
    try:
        _delete_related_files(target, logger)
    except PermissionError as exc:
        if logger is not None:
            logger(f"No se pudo limpiar salida temporal {target}: {exc}")


def remove_project_layers_for_paths(paths):
    normalized_paths = {_normalize_path(path) for path in paths}
    project = QgsProject.instance()
    remove_ids = []

    for layer in project.mapLayers().values():
        source_path = _layer_source_path(layer.source())
        if _normalize_path(source_path) in normalized_paths:
            remove_ids.append(layer.id())

    if remove_ids:
        project.removeMapLayers(remove_ids)
        QgsApplication.processEvents()
        gc.collect()


def remove_project_layers_by_name(name):
    project = QgsProject.instance()
    remove_ids = [layer.id() for layer in project.mapLayers().values() if layer.name() == name]
    if remove_ids:
        project.removeMapLayers(remove_ids)
        QgsApplication.processEvents()
        gc.collect()


def _delete_related_files(path, logger=None):
    for related in _related_paths(path):
        if related.exists():
            if logger is not None:
                logger(f"Reemplazando salida existente: {related}")
            try:
                related.unlink()
            except PermissionError as exc:
                QgsApplication.processEvents()
                gc.collect()
                try:
                    related.unlink()
                except PermissionError as retry_exc:
                    raise PermissionError(
                        f"No se pudo reemplazar {related} porque todavia esta en uso."
                    ) from retry_exc


def _related_paths(path):
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".shp":
        return [path.with_suffix(extension) for extension in SHAPEFILE_EXTENSIONS]

    paths = [path]
    if suffix in (".tif", ".tiff", ".vrt", ".img"):
        paths.extend(Path(str(path) + extension) for extension in RASTER_AUX_EXTENSIONS)
    return paths


def _available_fallback_path(path):
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 1000):
        label = "actual" if index == 1 else f"actual_{index}"
        candidate = parent / f"{stem}_{label}{suffix}"
        if not any(related.exists() for related in _related_paths(candidate)):
            return candidate
    return parent / f"{stem}_actual_999{suffix}"


def _layer_source_path(source):
    return str(source).split("|", 1)[0]


def _normalize_path(path):
    return str(Path(path).resolve()).replace("\\", "/").lower()
