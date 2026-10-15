import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

try:
    from PySide6.QtCore import Qt, QCoreApplication
except ImportError:
    pass
else:
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
