# Third-party notices

SONIC WiFi Finder bundles the Python interpreter, PySide6 Essentials, Shiboken6,
Qt libraries, and the PyInstaller bootloader. These components retain their
respective copyright notices and licenses.

- **Python**: Python Software Foundation License Version 2 and associated
  notices. The native runtime license is copied into `licenses/runtime` during
  the build. Source: https://www.python.org/downloads/source/
- **PySide6 Essentials 6.8.3 and Shiboken6 6.8.3**: Copyright The Qt Company Ltd.
  and contributors. Distributed under LGPL v3 in this package.
  Source: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/
- **Qt 6.8.3 Core, GUI, Widgets and platform libraries**: Copyright The Qt
  Company Ltd. and contributors. LGPL v3; license text is included alongside
  the GPL v3 referenced by it. Qt's third-party components retain their own
  licenses. Source: https://download.qt.io/archive/qt/6.8/6.8.3/single/
- **PyInstaller 6.22.3 bootloader**: GPL v2 with the PyInstaller bootloader
  exception, which permits bundling an application under its own license.
  The installed distribution's license is copied into `licenses/runtime`
  during the build. Source: https://github.com/pyinstaller/pyinstaller/tree/v6.22.3

The application source and native build scripts are supplied separately so
the bundled libraries can be replaced and the application rebuilt. Modification
or reverse engineering needed to debug changes to these open-source libraries
is not prohibited. No commercial Qt license or Apple Developer signing identity
is asserted by this package.
