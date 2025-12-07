import os
import sys
from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QPushButton, QFileDialog, QLabel, QStatusBar,
                             QSplitter, QMessageBox, QProgressBar, QDockWidget,
                             QListWidget, QTextEdit, QMenuBar, QAction, QToolBar,
                             QApplication, QColorDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPalette, QColor, QIcon
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from log_processor import LogProcessor
from ui.parameter_tree import ParameterTreeWidget
from ui.plot_widget import PlotWidget

class ParseThread(QThread):
    finished = pyqtSignal(bool)
    progress = pyqtSignal(str)
    
    def __init__(self, processor, file_path):
        super().__init__()
        self.processor = processor
        self.file_path = file_path
    
    def run(self):
        self.progress.emit("Парсинг MAVLink лога...")
        try:
            self.processor.parse_log()
            self.finished.emit(True)
        except Exception as e:
            print(f"Ошибка парсинга: {e}")
            self.finished.emit(False)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = None
        self.current_plots = {}  # parameter_name: (x_data, y_data, color)
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("UAVLogViewer")
        self.setGeometry(100, 100, 1600, 900)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QHBoxLayout(central_widget)
        
        # Сплиттер
        splitter = QSplitter(Qt.Horizontal)
        
        # Виджет графика
        self.plot_widget = PlotWidget()
        self.plot_widget.time_type_changed.connect(self.on_time_type_changed)
        self.plot_widget.cursor_position_changed.connect(self.on_cursor_position_changed)
        self.plot_widget.active_plot_changed.connect(self.on_active_plot_changed)
        
        # Док-виджет для дерева параметров
        dock_widget = QDockWidget("Параметры MAVLink", self)
        dock_widget.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock_widget.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        
        self.tree_widget = ParameterTreeWidget()
        self.tree_widget.parameter_toggled.connect(self.on_parameter_toggled)
        self.tree_widget.color_changed.connect(self.on_color_changed)
        
        dock_widget.setWidget(self.tree_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, dock_widget)
        
        # Док-виджет для информации о курсоре
        info_dock = QDockWidget("Информация о точке", self)
        info_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.cursor_info_text = QTextEdit()
        self.cursor_info_text.setReadOnly(True)
        self.cursor_info_text.setMaximumHeight(150)
        self.cursor_info_text.setStyleSheet("font-family: monospace;")
        info_dock.setWidget(self.cursor_info_text)
        self.addDockWidget(Qt.BottomDockWidgetArea, info_dock)
        
        splitter.addWidget(self.plot_widget)
        main_layout.addWidget(splitter)
        
        # Статус бар
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        # Создаем меню и тулбар
        self.create_menu()
        self.create_toolbar()
        
        self.status_bar.showMessage("Готов к работе. Выберите файл лога для анализа.")
        
    def create_menu(self):
        """Создает меню приложения"""
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu('Файл')
        
        open_action = QAction('Открыть лог', self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        clear_action = QAction('Очистить все графики', self)
        clear_action.triggered.connect(self.clear_all_plots)
        file_menu.addAction(clear_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Выход', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Меню Вид
        view_menu = menubar.addMenu('Вид')
        
        reset_all_action = QAction('Сбросить масштаб всех графиков', self)
        reset_all_action.triggered.connect(self.plot_widget.reset_all_plots)
        view_menu.addAction(reset_all_action)
        
        reset_active_action = QAction('Сбросить масштаб активного графика', self)
        reset_active_action.triggered.connect(self.plot_widget.reset_active_plot)
        view_menu.addAction(reset_active_action)
        
        view_menu.addSeparator()
        
        change_color_action = QAction('Изменить цвет активного графика', self)
        change_color_action.triggered.connect(self.change_active_plot_color)
        view_menu.addAction(change_color_action)
        
        # Меню Справка
        help_menu = menubar.addMenu('Справка')
        
        about_action = QAction('О программе', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_toolbar(self):
        """Создает панель инструментов"""
        toolbar = QToolBar("Основные инструменты")
        toolbar.setIconSize(self.style().standardIcon(self.style().SP_ToolBarHorizontalExtensionButton).actualSize(self.size()))
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        
        # Кнопка открытия файла
        open_btn = QPushButton("Открыть лог")
        open_btn.clicked.connect(self.open_file)
        toolbar.addWidget(open_btn)
        
        toolbar.addSeparator()
        
        # Кнопка очистки графиков
        clear_btn = QPushButton("Очистить все")
        clear_btn.clicked.connect(self.clear_all_plots)
        toolbar.addWidget(clear_btn)
        
        toolbar.addSeparator()
        
        # Информация о активном графике
        self.active_plot_label = QLabel("Активный график: нет")
        toolbar.addWidget(self.active_plot_label)
        
        toolbar.addSeparator()
        
        # Кнопка изменения цвета
        self.color_btn = QPushButton("Изменить цвет")
        self.color_btn.clicked.connect(self.change_active_plot_color)
        self.color_btn.setEnabled(False)
        toolbar.addWidget(self.color_btn)
    
    def open_file(self):
        """Открытие файла через диалог"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите MAVLink лог",
            "",
            "MAVLink логи (*.tlog *.bin *.log);;Все файлы (*)"
        )
        
        if file_path:
            self.load_file(file_path)
    
    def load_file(self, file_path):
        """Загрузка и парсинг файла"""
        self.status_bar.showMessage(f"Загрузка файла: {os.path.basename(file_path)}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Индикатор прогресса без определенного конца
        
        # Очищаем предыдущие данные
        self.clear_all_plots()
        
        self.processor = LogProcessor(file_path)
        
        # Запускаем парсинг в отдельном потоке
        self.parse_thread = ParseThread(self.processor, file_path)
        self.parse_thread.finished.connect(self.on_parse_finished)
        self.parse_thread.progress.connect(self.status_bar.showMessage)
        self.parse_thread.start()
    
    def on_parse_finished(self, success):
        """Обработка завершения парсинга"""
        self.progress_bar.setVisible(False)
        
        if success:
            self.status_bar.showMessage("Парсинг завершен успешно")
            
            # Обновляем дерево параметров
            parameters_tree = self.processor.get_available_parameters()
            self.tree_widget.update_tree(parameters_tree)
            
            # Обновляем доступные типы времени
            time_types = self.processor.get_time_types_available()
            current_time_type = self.plot_widget.time_type_combo.currentText()
            self.plot_widget.time_type_combo.clear()
            self.plot_widget.time_type_combo.addItems(time_types)
            
            # Восстанавливаем предыдущий выбор времени, если он доступен
            if current_time_type in time_types:
                self.plot_widget.time_type_combo.setCurrentText(current_time_type)
            elif time_types:
                self.plot_widget.time_type_combo.setCurrentText(time_types[0])
            
        else:
            QMessageBox.critical(self, "Ошибка", 
                               "Не удалось распарсить файл. Убедитесь, что это корректный MAVLink лог.")
            self.status_bar.showMessage("Ошибка парсинга файла")
    
    def on_parameter_toggled(self, parameter_name, is_checked, color):
        """Обработка выбора параметра в дереве"""
        if is_checked:
            self.add_plot(parameter_name, color)
        else:
            self.remove_plot(parameter_name)
    
    def on_color_changed(self, parameter_name, color):
        """Обработка изменения цвета из дерева параметров"""
        # Обновляем цвет в текущих графиках
        if parameter_name in self.current_plots:
            self.plot_widget.update_plot_color(parameter_name, color)
            # Обновляем данные в current_plots
            x_data, y_data, _ = self.current_plots[parameter_name]
            self.current_plots[parameter_name] = (x_data, y_data, color)
    
    def add_plot(self, parameter_name, color):
        """Добавление графика"""
        if self.processor is None:
            QMessageBox.warning(self, "Предупреждение", "Сначала откройте файл лога")
            return
        
        time_type = self.plot_widget.time_type_combo.currentText()
        x_data, y_data = self.processor.get_parameter_data(parameter_name, time_type)
        
        if x_data is not None and y_data is not None and len(x_data) > 0:
            self.plot_widget.add_plot(parameter_name, x_data, y_data, color)
            self.current_plots[parameter_name] = (x_data, y_data, color)
            
            # Устанавливаем этот график как активный
            self.plot_widget.set_active_plot(parameter_name)
            
            self.status_bar.showMessage(f"Добавлен график: {parameter_name}")
        else:
            # Показываем какие временные метки доступны
            msg_type = parameter_name.split('.')[0]
            stats = self.processor.get_message_statistics()
            if msg_type in stats:
                available_times = stats[msg_type]['available_timestamps']
                message = (f"Для параметра {parameter_name} нет данных с временем '{time_type}'. "
                          f"Доступные типы времени: {', '.join(available_times)}")
            else:
                message = f"Для параметра {parameter_name} нет данных с временем '{time_type}'"
            
            QMessageBox.warning(self, "Данные недоступны", message)
            
            # Сбрасываем чекбокс в дереве
            if parameter_name in self.tree_widget.parameter_checkboxes:
                self.tree_widget.parameter_checkboxes[parameter_name].setChecked(False)
    
    def remove_plot(self, parameter_name):
        """Удаление графика"""
        self.plot_widget.remove_plot(parameter_name)
        if parameter_name in self.current_plots:
            del self.current_plots[parameter_name]
            self.status_bar.showMessage(f"Удален график: {parameter_name}")
    
    def clear_all_plots(self):
        """Очистка всех графиков"""
        # Очищаем графики
        self.plot_widget.plots.clear()
        self.plot_widget.plot_data.clear()
        self.plot_widget.plot_colors.clear()
        self.plot_widget.cursor_points.clear()
        self.plot_widget.graph_widget.clear()
        self.plot_widget.active_plot_combo.clear()
        self.plot_widget.active_plot = None
        
        # Очищаем данные
        self.current_plots.clear()
        
        # Сбрасываем чекбоксы в дереве
        for checkbox in self.tree_widget.parameter_checkboxes.values():
            checkbox.setChecked(False)
        
        # Обновляем интерфейс
        self.active_plot_label.setText("Активный график: нет")
        self.color_btn.setEnabled(False)
        
        self.status_bar.showMessage("Все графики очищены")
    
    def on_time_type_changed(self, time_type):
        """Обработка изменения типа времени"""
        if self.processor is None or not self.current_plots:
            return
        
        # Обновляем все активные графики с новым типом времени
        updated_plots = []
        failed_plots = []
        
        for parameter_name in list(self.current_plots.keys()):
            x_data, y_data = self.processor.get_parameter_data(parameter_name, time_type)
            
            if x_data is not None and y_data is not None and len(x_data) > 0:
                _, _, color = self.current_plots[parameter_name]
                self.current_plots[parameter_name] = (x_data, y_data, color)
                self.plot_widget.update_plot_data(parameter_name, x_data, y_data)
                updated_plots.append(parameter_name)
            else:
                # Если для этого типа времени нет данных, убираем график
                self.remove_plot(parameter_name)
                failed_plots.append(parameter_name)
        
        if updated_plots:
            self.status_bar.showMessage(f"Обновлено {len(updated_plots)} графиков с временем '{time_type}'")
        
        if failed_plots:
            QMessageBox.warning(self, "Данные недоступны", 
                              f"Для {len(failed_plots)} графиков нет данных с временем '{time_type}'. "
                              f"Графики были скрыты.")
    
    def on_cursor_position_changed(self, x_pos, parameter_values):
        """Обработка изменения позиции курсора"""
        if not parameter_values:
            self.cursor_info_text.setText("Нет данных для отображения")
            return
        
        info_text = f"Время: {x_pos:.3f} сек\n\n"
        
        # Показываем значение активного графика
        active_plot = self.plot_widget.active_plot
        if active_plot and active_plot in parameter_values:
            active_data = parameter_values[active_plot]
            info_text += f"► Активный график ({active_plot}):\n"
            info_text += f"   Значение: {active_data['y']:.6f}\n"
            info_text += f"   Время: {active_data['x']:.3f} сек\n\n"
        
        # Показываем значения всех графиков
        info_text += "Все графики:\n"
        for param_name, data in parameter_values.items():
            marker = "  " if param_name != active_plot else "► "
            info_text += f"{marker}{param_name}: {data['y']:.6f} (время: {data['x']:.3f} сек)\n"
        
        self.cursor_info_text.setText(info_text)
    
    def on_active_plot_changed(self, parameter_name):
        """Обработка изменения активного графика"""
        self.active_plot_label.setText(f"Активный график: {parameter_name}")
        self.color_btn.setEnabled(True)
        
        # Показываем информацию о параметре
        if self.processor:
            msg_type = parameter_name.split('.')[0]
            stats = self.processor.get_message_statistics()
            if msg_type in stats:
                available_times = stats[msg_type]['available_timestamps']
                self.status_bar.showMessage(
                    f"Активный: {parameter_name}. Доступное время: {', '.join(available_times)}"
                )
    
    def change_active_plot_color(self):
        """Изменение цвета активного графика"""
        if not self.plot_widget.active_plot:
            return
        
        current_color = self.plot_widget.plot_colors.get(self.plot_widget.active_plot, '#1f77b4')
        color = QColorDialog.getColor(QColor(current_color))
        
        if color.isValid():
            new_color = color.name()
            # Обновляем цвет в виджете графика
            self.plot_widget.update_plot_color(self.plot_widget.active_plot, new_color)
            
            # Обновляем цвет в дереве параметров
            if self.plot_widget.active_plot in self.tree_widget.parameter_colors:
                self.tree_widget.set_parameter_color(self.plot_widget.active_plot, new_color)
            
            # Обновляем данные в current_plots
            if self.plot_widget.active_plot in self.current_plots:
                x_data, y_data, _ = self.current_plots[self.plot_widget.active_plot]
                self.current_plots[self.plot_widget.active_plot] = (x_data, y_data, new_color)
            
            self.status_bar.showMessage(f"Цвет графика '{self.plot_widget.active_plot}' изменен")
    
    def show_about(self):
        """Показывает информацию о программе"""
        about_text = """
        <h2>MAVLink Log Analyzer</h2>
        <p>Приложение для анализа логов MAVLink</p>
        <p><b>Основные возможности:</b></p>
        <ul>
            <li>Визуализация параметров MAVLink в реальном времени</li>
            <li>Поддержка различных временных меток (TimeUS, GPS)</li>
            <li>Интерактивное управление графиками</li>
            <li>Точные измерения с помощью курсора</li>
            <li>Гибкая настройка цветов и отображения</li>
        </ul>
        <p><b>Управление:</b></p>
        <ul>
            <li><b>Клик по графику</b> - выбор активного графика</li>
            <li><b>Двойной клик</b> - сброс масштаба активного графика</li>
            <li><b>Перетаскивание</b> - перемещение по осям</li>
            <li><b>Колесо мыши</b> - масштабирование</li>
        </ul>
        """
        QMessageBox.about(self, "О программе", about_text)
    
    def closeEvent(self, event):
        """Обработка закрытия приложения"""
        # Останавливаем парсинг если он выполняется
        if hasattr(self, 'parse_thread') and self.parse_thread.isRunning():
            self.parse_thread.terminate()
            self.parse_thread.wait()
        
        event.accept()

if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Современный стиль
    
    # Настраиваем цветовую схему
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())