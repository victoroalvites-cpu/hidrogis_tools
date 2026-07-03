def classFactory(iface):
    from .plugin import HidroGISToolsPlugin

    return HidroGISToolsPlugin(iface)
