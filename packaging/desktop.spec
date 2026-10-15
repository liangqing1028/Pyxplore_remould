# Build on the target OS and architecture. Keep Qt and numerical libraries in one bundle.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = collect_data_files('wpem_desktop', include_py_files=True)
for package in ['pymatgen', 'plotly', 'ase']:
    datas += collect_data_files(package)
for package in ['numpy', 'scipy', 'pandas', 'pymatgen', 'tensorflow', 'PySide6', 'Bgolearn']:
    try:
        datas += copy_metadata(package)
    except Exception:
        if package not in {'tensorflow', 'Bgolearn'}:
            raise
hidden = collect_submodules('wpem_desktop._vendor.pywpem',
                            filter=lambda name: '.m3gnet.trainers' not in name and not name.endswith('.m3gnet.cli'))
hidden += collect_submodules('tf_keras')
hidden += ['matplotlib.backends.backend_qtagg', 'matplotlib.backends.backend_svg',
           'matplotlib.backends.backend_pdf', 'PySide6.QtSvg', 'PySide6.QtWebEngineWidgets']
analysis = Analysis([str(root / 'packaging/launcher.py')], pathex=[str(root)],
                    binaries=[], datas=datas, hiddenimports=hidden,
                    hookspath=[], hooksconfig={'matplotlib': {'backends': ['QtAgg', 'Agg']}},
                    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'pytest', 'IPython', 'ipywidgets'], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [('X utf8', None, 'OPTION')], exclude_binaries=True, name='PyWPEMDesktop',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, argv_emulation=False)
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='PyWPEMDesktop')
if os.sys.platform == 'darwin':
    app = BUNDLE(collection, name='PyWPEMDesktop.app', bundle_identifier='org.pywpem.desktop',
                 info_plist={'CFBundleShortVersionString': '0.1.0', 'NSHighResolutionCapable': True})
