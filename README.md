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

## Flujo sugerido para morfometría

1. Genera o carga el DEM preprocesado.
2. Genera o carga la cuenca general.
3. Abre la pestaña `Morfometría`.
4. Usa el modo `Cuenca única (QGIS/GRASS)` para calcular solo la cuenca delimitada.
5. Selecciona DEM, cuenca general y red de drenaje. Para morfometría se recomienda usar el DEM morfométrico original, normalmente el DEM recortado o reproyectado. El `DEM hidrológico` queda disponible para comparación, pero no se prioriza automáticamente porque el quemado de cauces puede sesgar el máximo recorrido hacia la red reacondicionada.
6. Selecciona el punto de salida que coincide con el drenaje y la celda de acumulación; si existe `Punto de salida ajustado`, úsalo en lugar del punto original sin ajustar.
7. Elige el método para el máximo recorrido. Si ya generaste los rásteres de dirección y acumulación, usa `Dirección + acumulación ráster`; de lo contrario, puedes usar `D8 interno` o `Red vectorial`.
8. Define carpeta de salida y prefijo.
9. Ejecuta `Calcular parametros`.

Si necesitas revisar subunidades generadas por HEC-HMS u otra fuente externa, cambia el modo a `Subunidades HEC-HMS/importadas` y carga la capa de subunidades validada.

El modulo calcula parametros para la cuenca unica. En modo HEC-HMS/importado tambien puede procesar subunidades externas:

- Área, perímetro y centroide.
- Elevación mínima, media y máxima.
- Relieve, pendiente media e integral hipsométrica.
- Longitud máxima sobre el cauce o recorrido hidrológico conectado a la salida, usada para el ancho medio, los índices de forma, Snyder, la pendiente del cauce y los tiempos de concentración.
- Lc Snyder: longitud sobre el cauce principal desde la salida hasta el punto del cauce más cercano al centroide.
- Coeficiente de compacidad, circularidad, elongación y relación de relieve.
- Coeficiente de masividad y coeficiente orográfico.
- Longitud total de red de drenaje y cauce principal aproximado por maximo recorrido.
- Pendiente aproximada del cauce principal.
- Orden máximo, número y longitud de elementos, y distribución de la red de Strahler.
- Tiempos de concentracion por Kirpich, Kerby, Kerby-Kirpich, Ven Te Chow,
  Témez, Johnstone-Cross, Cuerpo de Ingenieros de EE. UU.,
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
- `_09_informe_parametros.docx`
- `_curvas_hipsometrica/`

El archivo Excel incluye las hojas `Parámetros` (matriz por subcuenca), `Datos` (formato normalizado), `Tiempos` y `Diccionario`. Las tablas emplean los nombres completos, unidades y descripciones reales de cada parámetro. El informe Word presenta metodología, cuadro resumen, parámetros por unidad, tiempos de concentración, métodos incluidos y observaciones. Las curvas hipsométricas se guardan como archivos PNG individuales por unidad y un PNG combinado. Para el máximo recorrido, HidroGIS puede seguir directamente el ráster de dirección y usa el flujo acumulado como criterio auxiliar al escoger la cabecera conectada a la salida. Una ruta corta o que no llega a la salida se rechaza; se prueban D8 interno y un respaldo híbrido que prolonga la red hasta la divisoria siguiendo el DEM. Si tampoco se valida un recorrido, la longitud de cauce, Snyder y los tiempos de concentración dependientes quedan sin resultado.

El botón `Ver reporte`, disponible en Morfometría y Tiempo de concentración, abre el PDF asociado cuando existe; en caso contrario abre el informe Word. El menú desplegable permite seleccionar explícitamente cualquiera de los dos formatos. Los valores numéricos del informe usan punto como separador decimal.

Al usar el ráster de dirección, selecciona su codificación: GRASS 1-8 (predeterminada) o SAGA 0-7. No se remuestrean los códigos de dirección para calcular el recorrido, pues eso cambiaría la conectividad. Los parámetros Strahler usan los tramos vectoriales cuando existe el campo `strahler`; si solo se entrega el ráster de orden, el conteo representa celdas y no se informa longitud vectorial.

El motor D8 genera `_22_orden_strahler.tif` y agrega el campo `strahler` a la red vectorial. Si `GRASS r.fill.dir` falla o no crea un raster valido, HidroGIS intenta automaticamente un relleno interno `Priority-Flood`; de ese modo la delimitacion no vuelve a solicitar un `_05_dem_rellenado.tif` inexistente.

Si GRASS tampoco completa `r.watershed` o la extraccion de red, HidroGIS comprueba las salidas y prueba el motor D8 interno. Este ultimo acepta como maximo 4 millones de celdas; para un DEM mas grande se debe recortar el area de analisis o resolver el proveedor GRASS. El registro indica claramente el motor usado.

### Estudios que cruzan las zonas UTM 18S y 19S

El complemento usa el CRS del **DEM**, no el CRS mostrado en la esquina inferior de QGIS para el proyecto. Prepara un DEM unico en un CRS proyectado en metros y transforma las capas vectoriales a ese mismo marco de trabajo. EPSG:32718 y EPSG:32719 son alternativas posibles segun la ubicacion de la cuenca; cambiar solo el CRS del proyecto no reproyecta el raster. Verifica el CRS en las propiedades de la capa y revisa la distorsion si el area de estudio es muy extensa a ambos lados del limite de zona.

Por defecto se cargan al proyecto el máximo recorrido validado y su Lc Snyder para la cuenca general. Las líneas por subunidad se guardan y solo se cargan si se activa esa opción en el modo `Subunidades HEC-HMS/importadas`.

Los tiempos de concentracion dependen directamente de la longitud de maximo recorrido y la pendiente del cauce. HidroGIS calcula un amplio abanico de formulas empiricas, pero evalua rigurosamente el area de la cuenca bajo estudio para promediar unicamente los metodos aplicables segun sus criterios de validez espaciales:

- `Kirpich`: rango de aplicacion de 0.0051 a 0.433 km2.
- `Kerby-Kirpich`: rango de aplicacion para cuencas medianas de 0.65 a 388.5 km2.
- `Temez`: cuencas menores a 3000 km2.
- `Johnstone-Cross`: rango de aplicacion de 64.8 a 4206.1 km2.
- `Cuerpo de Ingenieros de EE.UU.`: cuencas menores a 12000 km2.
- `Passini`: rango de aplicacion de 40 a 70000 km2; se muestra siempre como comparativo y solo entra al promedio cuando el usuario activa la opcion correspondiente.

`California Culverts` y `Ventura-Heras` se retiraron del calculo y de todos los reportes. Los metodos puramente individuales (`Kerby`) o pendientes de verificacion regional (`Ven Te Chow`, `Tournon`) se conservan como comparativos. El resumen principal muestra `Rango Tc h`, `Tc prom h` y `T retardo min`.

Ademas del reporte general de morfometria, el complemento genera automaticamente un reporte exclusivo (`_tiempos_concentracion.xlsx` y `.csv`) dentro de la subcarpeta `04_Tiempo_Concentracion`, incluyendo una hoja de resumen y un diccionario detallado de variables.

`T retardo = 0.6 * Tc promedio * 60`

Estos resultados deben revisarse con criterio hidrologico y con la calidad del DEM/red de drenaje.

### Compatibilidad futura

La lectura directa de insumos preparados en ArcGIS Pro, SWAT+ y otros entornos queda planificada para versiones posteriores. La versión actual no interpreta esas codificaciones de manera automática; deben emplearse los insumos y codificaciones expresamente disponibles en la interfaz.
