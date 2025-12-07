import sys
import os
from PyQt5.QtWidgets import QApplication

# Путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("UAVLogViewer")
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()