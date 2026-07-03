# HidroGIS Watershed Tools

Complemento QGIS base para herramientas hidrologicas e hidrometeorologicas.

El primer modulo implementado permite descargar y preprocesar modelos digitales de elevacion. La idea es que este complemento crezca con nuevos modulos para analisis morfometrico, analisis de estaciones, precipitacion media areal y otros procesos.

## Funciones incluidas

- Descargar DEM globales desde la API de OpenTopography.
- Usar rasters DEM locales como entrada.
- Trabajar con DEM raster georreferenciados de distintas fuentes: ASTER GDEM, SRTM, ALOS/PALSAR, LandViewer, OpenTopography u otras fuentes equivalentes.
- Unir multiples DEM mediante mosaico.
- Reproyectar el resultado a un CRS destino.
- Recortar por extension o por una capa poligonal.
- Delimitar cuencas desde un punto de salida.
- Reacondicionar el DEM quemando una red de drenaje existente.
- Rellenar depresiones en un DEM.
- Calcular direccion de flujo, acumulacion, red de drenaje, TCI y SPI.
- Manejar un umbral unico para controlar la densidad de la red de drenaje.
- Ajustar el punto de salida hacia la red de drenaje.
- Extraer red de drenaje raster y vectorial.
- Calcular parametros geomorfologicos para una cuenca unica; las subunidades quedan como modo de apoyo para flujos HEC-HMS/importados.
- Exportar resumen morfometrico a GeoPackage, CSV y Excel.
- Generar curvas hipsometricas en PNG para cada unidad y un grafico combinado.
- Agregar el raster final al proyecto QGIS.
- Definir una carpeta raiz de proyecto y crear subcarpetas estandar para DEM, cuenca, morfometria, tiempos de concentracion, HEC-HMS, reportes y temporales.

## Instalacion para desarrollo

1. Copia o enlaza la carpeta `hidrogis_tools` dentro del directorio de complementos de QGIS:

   En Windows suele estar en:

   `C:\Users\<usuario>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`

2. Reinicia QGIS o usa el complemento `Plugin Reloader`.
3. Activa `HidroGIS Watershed Tools` en el administrador de complementos.
4. Abre la ventana principal desde `Complementos > HidroGIS Watershed Tools > HidroGIS Watershed Tools`.

Tambien puedes comprimir la carpeta `hidrogis_tools` como ZIP e instalarla desde `Complementos > Administrar e instalar complementos > Instalar desde ZIP`.

## Manejo de salidas

En la ventana principal puedes seleccionar una `Carpeta del proyecto`. HidroGIS Watershed Tools crea automaticamente esta estructura:

- `01_DEM`
- `02_Cuenca`
- `03_Morfometria`
- `04_Tiempo_Concentracion`

El complemento guarda tambien un archivo `proyecto_hidrogis.json` en la raiz para recordar la estructura. Al aplicar la carpeta del proyecto, las herramientas de DEM, Cuencas y Morfometria actualizan sus carpetas de salida con las subcarpetas correspondientes.

Cuando ejecutas una herramienta con la misma carpeta de salida y el mismo prefijo, HidroGIS Watershed Tools reemplaza los archivos existentes y actualiza las capas cargadas en QGIS. Esto evita llenar el disco con versiones duplicadas. Para conservar una corrida anterior, usa otro prefijo.

## Nota sobre OpenTopography

La descarga usa el endpoint `globaldem` de OpenTopography, por lo que necesitas una API key de OpenTopography. El complemento no guarda la API key; debes pegarla cada vez que ejecutes una descarga.

## Flujo sugerido para DEM

1. Define el area usando la extension actual del mapa, una capa poligonal o poligonos seleccionados.
2. Descarga un DEM o agrega rasters locales.
3. Selecciona el CRS destino.
4. Elige si quieres recortar por extension o por poligono.
5. Ejecuta el proceso.

Los archivos intermedios se crean en la carpeta de salida con sufijos:

- `_raw.tif`
- `_01_mosaico.tif`
- `_02_reproyectado.tif`
- `_03_recortado.tif`

## Flujo sugerido para delimitacion de cuencas

1. Usa como entrada el DEM ya preprocesado.
2. Si tienes una red de rios/quebradas, activa el quemado de red para reacondicionar el DEM.
3. Define el umbral para la red de drenaje.
4. Elige el motor hidrologico: `GRASS` para el flujo estable o `HidroGIS D8 interno` para comparar resultados.
5. Crea la red y revisa si la densidad de drenaje es adecuada.
6. Carga o dibuja un punto de salida.
7. Revisa el punto ajustado. El punto visible se mueve al tramo de drenaje mas cercano dentro de la distancia de snap.
8. Crea la cuenca.

Con `Crear red`, QGIS carga la red vectorial para revisar umbrales y densidad de drenaje. Con `Crear cuenca`, QGIS carga las capas finales necesarias para los analisis: cuenca general y red de drenaje recortada a la cuenca. Si esta activa la opcion `Agregar DEM hidrologico final`, tambien se carga el DEM que realmente uso el motor hidrologico. Ese DEM puede ser el rellenado, el reacondicionado o el rellenado-reacondicionado, segun las opciones elegidas. Los demas rasters intermedios se guardan en la carpeta de salida, pero no se agregan al panel de capas salvo que actives `Agregar tambien capas intermedias`.

El motor `HidroGIS D8 interno` es experimental: calcula direccion de flujo D8, acumulacion, red por umbral y cuenca desde el punto de salida. Esta pensado para comparar y acercar el flujo de delimitacion con el maximo recorrido tipo HEC-HMS usado en morfometria. Para DEM grandes o zonas planas complejas, conserva `GRASS` como respaldo.

Cuando se activa a la vez `Quemar red de drenaje existente` y `Rellenar depresiones`, HidroGIS vuelve a quemar la red despues del rellenado para que el DEM final usado por `r.watershed` conserve mejor el cauce observado. Si el ancho de quemado indicado es menor que el tamano de celda del DEM, se usa automaticamente una celda como ancho minimo, porque un ancho inferior puede no modificar la grilla.

Las subunidades ya no se generan desde la pestana `Cuencas`. Si se requieren para contrastar resultados de HEC-HMS u otra fuente, se cargan como capas externas en `Morfometria > Subunidades HEC-HMS/importadas`.

Las capas visibles se cargan con nombres limpios. Si usas el prefijo tecnico por defecto `hidrogis`, se oculta en el panel de capas. Si escribes un prefijo propio, por ejemplo `PROJ_`, se muestra como `PROJ_DEM recortado`, `PROJ_Red de drenaje` o `PROJ_Cuenca`. El DEM usa una rampa de color de elevacion con minimos y maximos reales, la red de drenaje se dibuja en azul y la cuenca se muestra sin relleno, solo con contorno.

La red de drenaje se genera primero como GeoPackage para evitar limitaciones antiguas del formato Shapefile. Si activas `Exportar red de drenaje como Shapefile (.shp)`, HidroGIS crea tambien una copia `.shp` compatible.

Si QGIS mantiene una salida abierta o bloqueada, HidroGIS intenta liberar la capa y continuar automaticamente. Cuando el archivo no se puede reemplazar fisicamente, crea una salida alternativa y reemplaza la capa visible por nombre para no detener el flujo.

Los archivos principales del modulo de cuencas son:

- `_04_dem_reacondicionado.tif`
- `_05_dem_rellenado.tif`
- `_05_dem_rellenado_reacondicionado.tif`
- `_08_acumulacion.tif`
- `_09_direccion.tif`
- `_10_subcuencas.tif` (intermedio interno)
- `_14_red_drenaje.tif`
- `_15_red_drenaje.gpkg`
- `_15_red_drenaje.shp`
- `_17_cuenca.tif`
- `_18_cuenca.gpkg`
- `_19_punto_salida_ajustado.gpkg`
- `_21_red_drenaje_cuenca.gpkg`
- `_21_red_drenaje_cuenca.shp`

## Flujo sugerido para morfometria

1. Genera o carga el DEM preprocesado.
2. Genera o carga la cuenca general.
3. Abre la pestana `Morfometria`.
4. Usa el modo `Cuenca unica (QGIS/GRASS)` para calcular solo la cuenca delimitada.
5. Selecciona DEM, cuenca general y red de drenaje. Para morfometria se recomienda usar el DEM morfometrico original, normalmente el DEM recortado o reproyectado. El `DEM hidrologico` queda disponible para comparacion, pero no se prioriza automaticamente porque el quemado de cauces puede sesgar el maximo recorrido hacia la red reacondicionada.
6. Si tienes la capa `Punto de salida`, dejala seleccionada para que el maximo recorrido de la cuenca se oriente hacia la salida aguas abajo.
7. Elige el metodo para el maximo recorrido: `D8 interno tipo HEC-HMS`, `Red vectorial`, `GRASS r.drain` o `SAGA Next Gen`.
8. Define carpeta de salida y prefijo.
9. Ejecuta `Calcular parametros`.

Si necesitas revisar subunidades generadas por HEC-HMS u otra fuente externa, cambia el modo a `Subunidades HEC-HMS/importadas` y carga la capa de subunidades validada.

El modulo calcula parametros para la cuenca unica. En modo HEC-HMS/importado tambien puede procesar subunidades externas:

- Area, perimetro y centroide.
- Elevacion minima, media y maxima.
- Relieve, pendiente media e integral hipsometrica.
- Longitud de maximo recorrido sobre la red hasta el borde de la unidad, ancho medio, factor de forma y coeficiente de forma.
- Lc Snyder: longitud sobre el cauce principal desde la salida hasta el punto del cauce mas cercano al centroide.
- Coeficiente de compacidad, circularidad, elongacion y relacion de relieve.
- Coeficiente de masividad y coeficiente orografico.
- Longitud total de red de drenaje y cauce principal aproximado por maximo recorrido.
- Pendiente aproximada del cauce principal.
- Tiempos de concentracion por Kirpich, Kerby, Kerby-Kirpich, California, Ven Te Chow,
  Temez, Johnstone-Cross, SCS-Ranser, Ventura-Heras, Cuerpo de Ingenieros de EE.UU.,
  Tournon y Passini.
- Matriz de aplicabilidad por area, promedio de Tc, rango y tiempo de retardo.
- Densidad de drenaje, frecuencia de cauces y textura de drenaje.
- Longitud de escurrimiento superficial, constante de mantenimiento, numero de robustez y numero de infiltracion.

La integral hipsometrica se calcula como:

`IH = (Elev_media - Elev_min) / (Elev_max - Elev_min)`

Las salidas principales son:

- `_01_morfometria_cuenca.gpkg`
- `_02_morfometria_subunidades.gpkg` (modo HEC-HMS/importado)
- `_03_morfometria_resumen.csv`
- `_04_morfometria_resumen.xlsx`
- `_05_maximo_recorrido_cuenca.gpkg`
- `_06_maximo_recorrido_subunidades.gpkg` (modo HEC-HMS/importado)
- `_07_lc_snyder_cuenca.gpkg`
- `_08_lc_snyder_subunidades.gpkg` (modo HEC-HMS/importado)
- `_curvas_hipsometrica/`

El archivo Excel incluye una hoja `Resumen` y una hoja `Diccionario` con la descripcion de cada campo. Las curvas hipsometricas se guardan como archivos PNG individuales por unidad y un PNG combinado, y tambien se pueden revisar dentro del panel `Integral hipsometrica` de la herramienta. Para el maximo recorrido, HidroGIS incluye un metodo D8 interno que calcula celdas conectadas a la salida, acumula distancia hidraulica hacia esa salida y traza la ruta desde la celda mas lejana, buscando asemejarse al criterio de longest flowpath de HEC-HMS. Tambien conserva los metodos `Red vectorial`, `GRASS r.drain` y SAGA Next Gen `Maximum Flow Path Length` como alternativas de comparacion.

Por defecto se carga al proyecto solo el maximo recorrido de la cuenca general y su Lc Snyder. Los recorridos y Lc por subunidad solo se guardan o cargan en el modo `Subunidades HEC-HMS/importadas`, para evitar que visualmente se confundan con toda la red de drenaje.

Los tiempos de concentracion dependen directamente de la longitud de maximo recorrido y la pendiente del cauce. HidroGIS calcula un amplio abanico de formulas empiricas, pero evalua rigurosamente el area de la cuenca bajo estudio para promediar unicamente los metodos aplicables segun sus criterios de validez espaciales:

- `Kirpich`: rango de aplicacion de 0.0051 a 0.433 km2.
- `Kerby-Kirpich`: rango de aplicacion para cuencas medianas de 0.65 a 388.5 km2.
- `Temez`: cuencas menores a 3000 km2.
- `Johnstone-Cross`: rango de aplicacion de 64.8 a 4206.1 km2.
- `SCS-Ranser`: rango de aplicacion de 0.01 a 65.0 km2 (1 a 6500 ha).
- `Ventura-Heras`: cuencas pequenas menores o iguales a 2.0 km2 (<= 200 ha).
- `Cuerpo de Ingenieros de EE.UU.`: cuencas menores a 12000 km2.
- `Passini`: rango de aplicacion de 40 a 70000 km2.

Metodos puramente individuales de escurrimiento superficial (`Kerby`), duplicados (`California Culverts`) o pendientes de verificacion regional (`Ven Te Chow`, `Tournon`) se conservan en la tabla general como comparativos. El resumen principal muestra `Rango Tc h`, `Tc prom h` (promedio estrictamente filtrado) y `T retardo min`.

Ademas del reporte general de morfometria, el complemento genera automaticamente un reporte exclusivo (`_tiempos_concentracion.xlsx` y `.csv`) dentro de la subcarpeta `04_Tiempo_Concentracion`, incluyendo una hoja de resumen y un diccionario detallado de variables.

`T retardo = 0.6 * Tc promedio * 60`

Estos resultados deben revisarse con criterio hidrologico y con la calidad del DEM/red de drenaje.
