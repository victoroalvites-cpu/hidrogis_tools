"""Reportes XLSX y DOCX sin dependencias externas para HidroGIS."""

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
import math
import zipfile


def _excel_col(index):
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _cell_xml(row, col, value, style=0):
    ref = f"{_excel_col(col)}{row}"
    if value is None or value == "":
        return f'<c r="{ref}" s="{style}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" s="{style}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def _sheet_xml(rows, widths=None, freeze="C2", autofilter=False):
    max_cols = max((len(row) for row in rows), default=1)
    cols = ""
    for index in range(1, max_cols + 1):
        width = (widths or {}).get(index, 14)
        cols += f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
    body = []
    for row_index, row in enumerate(rows, 1):
        cells = []
        for col_index, item in enumerate(row, 1):
            if isinstance(item, tuple):
                value, style = item
            else:
                value, style = item, (1 if row_index == 1 else 0)
            cells.append(_cell_xml(row_index, col_index, value, style))
        body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    pane = ""
    if freeze:
        letters = "".join(ch for ch in freeze if ch.isalpha())
        digits = "".join(ch for ch in freeze if ch.isdigit())
        xsplit = max(0, _letters_to_col(letters) - 1)
        ysplit = max(0, int(digits or "1") - 1)
        pane = (
            '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
            f'<pane xSplit="{xsplit}" ySplit="{ysplit}" topLeftCell="{freeze}" state="frozen"/>'
            '</sheetView></sheetViews>'
        )
    filter_xml = f'<autoFilter ref="A1:{_excel_col(max_cols)}{len(rows)}"/>' if autofilter and rows else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{pane}<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData>{filter_xml}</worksheet>'
    )


def _letters_to_col(letters):
    result = 0
    for char in letters.upper():
        result = result * 26 + ord(char) - 64
    return result


def _xlsx_styles():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="10"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Calibri"/></font><font><b/><color rgb="FF17365D"/><sz val="10"/><name val="Calibri"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F1"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD9D9D9"/></left><right style="thin"><color rgb="FFD9D9D9"/></right><top style="thin"><color rgb="FFD9D9D9"/></top><bottom style="thin"><color rgb="FFD9D9D9"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0"/><xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0"/><xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def write_workbook(path, sheets):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">', '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>', '<Default Extension="xml" ContentType="application/xml"/>', '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>', '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    workbook_sheets, relationships = [], []
    for index, (name, rows, options) in enumerate(sheets, 1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        workbook_sheets.append(f'<sheet name="{escape(name[:31])}" sheetId="{index}" r:id="rId{index}"/>')
        relationships.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
    relationships.append(f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    content_types.append('</Types>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(workbook_sheets) + '</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(relationships) + '</Relationships>')
        archive.writestr("xl/styles.xml", _xlsx_styles())
        for index, (_, rows, options) in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows, **options))
    return path


def write_morphometry_xlsx(path, data_rows, result_fields, tc_fields, field_notes, field_units=None):
    field_units = field_units or {}
    fields = list(result_fields) + list(tc_fields)
    units = [str(row.get("codigo") or f"Unidad {index}") for index, row in enumerate(data_rows, 1)]
    matrix = [[("PARÁMETROS MORFOMÉTRICOS", 1), ("Campo interno", 1), ("Unidad", 1)] + [(unit, 1) for unit in units]]
    groups = (
        ("GEOMETRÍA Y FORMA", {"area_km2", "area_ha", "perim_km", "lc_snyder_km", "ancho_med", "ff", "coef_forma", "kc", "rc", "re"}),
        ("RELIEVE", {"elev_min", "elev_med", "elev_max", "relieve_m", "int_hipso", "pend_med", "rh", "coef_masiv", "coef_orog"}),
        ("DRENAJE Y STRAHLER", {"long_red", "long_cp", "pend_cp", "dens_dren", "num_cauces", "frec_cauces", "text_dren", "long_esc_sup", "const_mant", "num_robust", "num_infil", "strahler_max", "strahler_tramos", "strahler_long_km", "strahler_dist"}),
        ("TIEMPOS DE CONCENTRACIÓN", {name for name, _, _ in tc_fields}),
        ("LOCALIZACIÓN", {"cent_x", "cent_y"}),
    )
    included = set()
    matrix_hidden = {"tc_estado", "tc_obs"}
    for title, names in groups:
        matrix.append([(title, 2), ("", 2), ("", 2)] + [("", 2) for _ in units])
        for name, label, _ in fields:
            if name not in names:
                continue
            if name in matrix_hidden:
                included.add(name)
                continue
            included.add(name)
            matrix.append(
                [(label, 4), (name, 4), (field_units.get(name, "adimensional"), 4)]
                + [(row.get(name), 3 if isinstance(row.get(name), (int, float)) else 4) for row in data_rows]
            )
    for name, label, _ in fields:
        if name not in included and name not in {"tipo", "codigo"} | matrix_hidden:
            matrix.append([(label, 4), (name, 4), (field_units.get(name, "adimensional"), 4)] + [(row.get(name), 4) for row in data_rows])

    data = [[(label, 1) for _, label, _ in fields]]
    data += [[row.get(name) for name, _, _ in fields] for row in data_rows]
    dictionary = [[("Campo", 1), ("Parámetro", 1), ("Unidad", 1), ("Descripción", 1)]]
    dictionary += [[name, label, field_units.get(name, "adimensional"), field_notes.get(name, "")] for name, label, _ in fields]
    tc_names = {name for name, _, _ in tc_fields}
    times = [[("Parámetro", 1)] + [(unit, 1) for unit in units]]
    for name, label, _ in tc_fields:
        if name in tc_names:
            times.append(
                [(label, 4)]
                + [
                    (
                        row.get(name),
                        3 if isinstance(row.get(name), (int, float)) else 4,
                    )
                    for row in data_rows
                ]
            )
    parameter_widths = {1: 42, 2: 24, 3: 18}
    time_widths = {1: 58}
    for index in range(len(units)):
        parameter_widths[index + 4] = 28
        time_widths[index + 2] = 42
    return write_workbook(path, [
        ("Parámetros", matrix, {"widths": parameter_widths, "freeze": "D2", "autofilter": False}),
        ("Datos", data, {"widths": {1: 19, 2: 18}, "freeze": "C2", "autofilter": True}),
        ("Tiempos", times, {"widths": time_widths, "freeze": "B2", "autofilter": False}),
        ("Diccionario", dictionary, {"widths": {1: 28, 2: 42, 3: 18, 4: 88}, "freeze": "A2", "autofilter": True}),
    ])


def _w_text(text, bold=False, color=None, size=None):
    props = ""
    if bold or color or size:
        props = "<w:rPr>" + ("<w:b/>" if bold else "") + (f'<w:color w:val="{color}"/>' if color else "") + (f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>' if size else "") + "</w:rPr>"
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(str(text))}</w:t></w:r>'


def _w_paragraph(text="", style=None, bold=False):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}{_w_text(text, bold=bold)}</w:p>'


def _w_table(rows, widths=None):
    table_width = sum(widths or []) or 9000
    xml = [
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
        f'<w:tblW w:w="{table_width}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
        '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar>'
        '</w:tblPr>'
    ]
    for row_index, row in enumerate(rows):
        tr_props = '<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if row_index == 0 else '<w:trPr><w:cantSplit/></w:trPr>'
        xml.append('<w:tr>' + tr_props)
        for col_index, value in enumerate(row):
            width = (widths or [])[col_index] if widths and col_index < len(widths) else 2200
            shade = '<w:shd w:fill="17365D"/>' if row_index == 0 else ('<w:shd w:fill="EAF2F8"/>' if row_index % 2 == 0 else '')
            color = "FFFFFF" if row_index == 0 else None
            alignment = "center" if row_index == 0 or col_index >= max(2, len(row) - 2) else "left"
            xml.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:vAlign w:val="center"/>{shade}</w:tcPr>'
                f'<w:p><w:pPr><w:jc w:val="{alignment}"/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
                f'{_w_text("" if value is None else value, bold=row_index == 0, color=color, size=18)}</w:p></w:tc>'
            )
        xml.append('</w:tr>')
    xml.append('</w:tbl>')
    return "".join(xml)


def _method_status_map(value):
    status = {}
    for item in str(value or "").split(";"):
        name, separator, detail = item.partition(":")
        if separator:
            status[name.strip()] = detail.strip()
    return status


def write_morphometry_docx(path, data_rows, result_fields=None, field_notes=None, field_units=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    field_notes = field_notes or {}
    field_units = field_units or {}
    body = [
        _w_paragraph("Informe de parámetros geomorfológicos", "Title"),
        _w_paragraph(f"Generado por HidroGIS Watershed Tools 1.1.3 — {datetime.now():%Y-%m-%d %H:%M}"),
        _w_paragraph("Resumen ejecutivo", "Heading1"),
        _w_paragraph(
            "El informe consolida la geometría, la forma, el relieve, el drenaje, el orden de Strahler "
            "y los tiempos de concentración de las unidades analizadas. Passini se presenta como valor "
            "comparativo y solo participa en el promedio cuando el usuario lo habilita y el área cumple "
            "su rango de aplicación."
        ),
        _w_paragraph("Metodología", "Heading1"),
        _w_paragraph(
            "Los parámetros planimétricos se obtienen de los polígonos. El relieve y la pendiente proceden "
            "del modelo digital de elevación. La red aporta la longitud y la frecuencia de los cauces. La "
            "longitud máxima del cauce corresponde al recorrido hidrológico validado desde la cabecera hasta "
            "el punto de salida; esta misma geometría alimenta Lc de Snyder y los tiempos de concentración. "
            "Los métodos de tiempo de concentración se filtran por sus rangos de aplicación."
        ),
        _w_paragraph("Cuadro resumen", "Heading1"),
    ]
    summary = [["Unidad", "Área (km²)", "Máximo recorrido (km)", "Strahler", "Tc promedio (h)", "Retardo (min)"]]
    for row in data_rows:
        summary.append([row.get("codigo", ""), _fmt(row.get("area_km2")), _fmt(row.get("long_cp")), row.get("strahler_max", ""), _fmt(row.get("tc_prom_h")), _fmt(row.get("t_retardo_min"))])
    body.append(_w_table(summary, [1400, 1350, 1800, 1050, 1600, 1500]))
    parameter_groups = (
        ("Geometría y forma", {"area_km2", "area_ha", "perim_km", "ancho_med", "ff", "coef_forma", "kc", "rc", "re"}),
        ("Relieve", {"elev_min", "elev_med", "elev_max", "relieve_m", "int_hipso", "pend_med", "rh", "coef_masiv", "coef_orog"}),
        ("Drenaje y Strahler", {"long_red", "long_cp", "lc_snyder_km", "pend_cp", "dens_dren", "num_cauces", "frec_cauces", "text_dren", "long_esc_sup", "const_mant", "num_robust", "num_infil", "strahler_max", "strahler_tramos", "strahler_long_km", "strahler_dist"}),
        ("Localización", {"cent_x", "cent_y"}),
    )
    result_fields = result_fields or []
    for row in data_rows:
        code = row.get("codigo") or "Unidad"
        body.extend(['<w:p><w:r><w:br w:type="page"/></w:r></w:p>', _w_paragraph(str(code), "Heading1"), _w_paragraph(f"Tipo de unidad: {row.get('tipo', '')}")])
        if result_fields:
            included = set()
            for heading, names in parameter_groups:
                params = [["Parámetro", "Descripción", "Unidad", "Resultado"]]
                for name, label, _ in result_fields:
                    if name in names:
                        params.append([label, field_notes.get(name, ""), field_units.get(name, "adimensional"), _fmt(row.get(name))])
                        included.add(name)
                if len(params) > 1:
                    body.append(_w_paragraph(heading, "Heading2"))
                    body.append(_w_table(params, [2500, 4700, 1050, 1350]))
            remaining = [(name, label) for name, label, _ in result_fields if name not in included and name not in {"tipo", "codigo"}]
            if remaining:
                body.append(_w_paragraph("Otros parámetros", "Heading2"))
                body.append(_w_table(
                    [["Parámetro", "Descripción", "Unidad", "Resultado"]]
                    + [[label, field_notes.get(name, ""), field_units.get(name, "adimensional"), _fmt(row.get(name))] for name, label in remaining],
                    [2500, 4700, 1050, 1350],
                ))
        else:
            params = [["Parámetro", "Resultado"], ["Área de la cuenca (km²)", _fmt(row.get("area_km2"))], ["Perímetro de la cuenca (km)", _fmt(row.get("perim_km"))], ["Longitud máxima del cauce (km)", _fmt(row.get("long_cp"))], ["Orden máximo de Strahler", row.get("strahler_max", "")]]
            body.append(_w_table(params, [6500, 2500]))
        body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        body.append(_w_paragraph("Tiempos de concentración", "Heading2"))
        tc = [["Método", "Descripción", "Tc (h)", "Aplicabilidad"]]
        status = _method_status_map(row.get("tc_estado"))
        for label, key in (("Kirpich", "tc_kirpich_h"), ("Kerby", "tc_kerby_h"), ("Kerby-Kirpich", "tc_kerby_kirpich_h"), ("Ven Te Chow", "tc_chow_h"), ("Témez", "tc_temez_h"), ("Johnstone-Cross", "tc_johnstone_h"), ("Cuerpo de Ingenieros de EE. UU.", "tc_usace_h"), ("Tournon", "tc_tournon_h"), ("Passini", "tc_passini_h")):
            tc.append([label, field_notes.get(key, ""), _fmt(row.get(key)), status.get(label, "Comparativo")])
        body.append(_w_table(tc, [1700, 4200, 1050, 2650]))
        tc_summary = [
            ["Resultado", "Descripción", "Unidad", "Valor"],
            ["Rango aceptado", field_notes.get("tc_rango_h", ""), "h", str(row.get("tc_rango_h", ""))],
            ["Promedio aceptado", field_notes.get("tc_prom_h", ""), "h", _fmt(row.get("tc_prom_h"))],
            ["Tiempo de retardo", field_notes.get("t_retardo_min", ""), "min", _fmt(row.get("t_retardo_min"))],
            ["Número de métodos incluidos", field_notes.get("tc_n_validos", ""), "métodos", row.get("tc_n_validos", "")],
            ["Métodos incluidos", field_notes.get("tc_validos", ""), "", row.get("tc_validos", "")],
        ]
        body.append(_w_table(tc_summary, [2300, 4400, 1000, 1900]))
        if row.get("tc_estado"):
            body.append(_w_paragraph("Aplicabilidad: " + str(row["tc_estado"])))
        if row.get("tc_obs"):
            body.append(_w_paragraph("Observaciones: " + str(row["tc_obs"])))
    body.append('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + "".join(body) + '</w:body></w:document>'
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="20"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="200"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="34"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="28"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="100"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="24"/></w:rPr></w:style><w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="D9D9D9"/><w:left w:val="single" w:sz="4" w:color="D9D9D9"/><w:bottom w:val="single" w:sz="4" w:color="D9D9D9"/><w:right w:val="single" w:sz="4" w:color="D9D9D9"/><w:insideH w:val="single" w:sz="4" w:color="D9D9D9"/><w:insideV w:val="single" w:sz="4" w:color="D9D9D9"/></w:tblBorders></w:tblPr></w:style></w:styles>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    return path


def _fmt(value):
    if value is None or value == "":
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)
