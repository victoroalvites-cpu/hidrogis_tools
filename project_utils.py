import json
from datetime import datetime
from pathlib import Path


PROJECT_FILE = "proyecto_hidrogis.json"

PROJECT_FOLDERS = {
    "dem": "01_DEM",
    "watershed": "02_Cuenca",
    "morphometry": "03_Morfometria",
    "time_concentration": "04_Tiempo_Concentracion",
}


def ensure_project_structure(root_folder):
    root = Path(root_folder).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    folders = {}
    for key, folder_name in PROJECT_FOLDERS.items():
        folder = root / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        folders[key] = folder

    config_path = root / PROJECT_FILE
    now = datetime.now().isoformat(timespec="seconds")
    created_at = now
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                previous = json.load(handle)
            created_at = previous.get("created_at") or created_at
        except (OSError, json.JSONDecodeError):
            pass

    data = {
        "schema": 1,
        "application": "HidroGIS Watershed Tools",
        "created_at": created_at,
        "updated_at": now,
        "root": str(root),
        "folders": {key: str(folder) for key, folder in folders.items()},
    }
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)

    return root, folders, config_path
