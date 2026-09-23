"""Algoritmos hidrologicos puros usados por HidroGIS.

Este modulo no depende de QGIS y por ello puede validarse con pruebas unitarias.
"""

from collections import deque
import heapq


def priority_flood_fill(elevation, valid_mask=None):
    """Rellena depresiones cerradas mediante Priority-Flood de 8 vecinos.

    Devuelve una copia ``float64``. Las celdas no validas conservan su valor.
    """
    import numpy as np

    source = np.asarray(elevation, dtype="float64")
    if source.ndim != 2:
        raise ValueError("El DEM debe ser una matriz bidimensional.")
    valid = np.isfinite(source) if valid_mask is None else np.asarray(valid_mask, dtype=bool)
    if valid.shape != source.shape:
        raise ValueError("La mascara valida no coincide con el DEM.")
    result = source.copy()
    if not valid.any():
        return result

    height, width = source.shape
    visited = np.zeros(source.shape, dtype=bool)
    heap = []
    neighbors = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))

    def seed(row, col):
        if valid[row, col] and not visited[row, col]:
            visited[row, col] = True
            heapq.heappush(heap, (float(result[row, col]), row, col))

    # El contorno del raster y los bordes de huecos NoData son salidas abiertas.
    for row in range(height):
        for col in range(width):
            if not valid[row, col]:
                continue
            if row in (0, height - 1) or col in (0, width - 1):
                seed(row, col)
                continue
            if any(not valid[row + dr, col + dc] for dr, dc in neighbors):
                seed(row, col)

    while heap:
        level, row, col = heapq.heappop(heap)
        for dr, dc in neighbors:
            nrow, ncol = row + dr, col + dc
            if not (0 <= nrow < height and 0 <= ncol < width):
                continue
            if not valid[nrow, ncol] or visited[nrow, ncol]:
                continue
            visited[nrow, ncol] = True
            filled = max(float(source[nrow, ncol]), level)
            result[nrow, ncol] = filled
            heapq.heappush(heap, (filled, nrow, ncol))
    return result


def strahler_order(receivers, active_mask):
    """Calcula el orden de Strahler sobre una red D8 dirigida.

    ``receivers`` contiene el indice plano de la celda receptora o -1.
    ``active_mask`` identifica las celdas pertenecientes a la red.
    """
    import numpy as np

    receiver_array = np.asarray(receivers, dtype="int64").ravel()
    active = np.asarray(active_mask, dtype=bool)
    active_flat = active.ravel()
    if receiver_array.size != active_flat.size:
        raise ValueError("La red y sus receptores no tienen el mismo tamano.")

    indegree = np.zeros(receiver_array.size, dtype="int32")
    for index in np.flatnonzero(active_flat):
        receiver = int(receiver_array[index])
        if 0 <= receiver < active_flat.size and active_flat[receiver]:
            indegree[receiver] += 1

    order = np.zeros(receiver_array.size, dtype="int16")
    max_upstream = np.zeros(receiver_array.size, dtype="int16")
    max_count = np.zeros(receiver_array.size, dtype="int16")
    queue = deque(int(i) for i in np.flatnonzero(active_flat & (indegree == 0)))
    for index in queue:
        order[index] = 1

    while queue:
        index = queue.popleft()
        receiver = int(receiver_array[index])
        if receiver < 0 or receiver >= active_flat.size or not active_flat[receiver]:
            continue
        incoming = int(order[index]) or 1
        if incoming > max_upstream[receiver]:
            max_upstream[receiver] = incoming
            max_count[receiver] = 1
        elif incoming == max_upstream[receiver]:
            max_count[receiver] += 1
        indegree[receiver] -= 1
        if indegree[receiver] == 0:
            maximum = int(max_upstream[receiver]) or 1
            order[receiver] = maximum + 1 if max_count[receiver] >= 2 else maximum
            queue.append(receiver)

    # Una red D8 valida es aciclica. Este respaldo hace visibles las celdas
    # anómalas en vez de perderlas si un raster externo contiene un ciclo.
    order[active_flat & (order == 0)] = 1
    return order.reshape(active.shape)
