from PyQt5.QtWidgets import (QTreeWidget, QTreeWidgetItem, QHeaderView, 
                             QMenu, QAction, QCheckBox, QHBoxLayout, QWidget,
                             QColorDialog, QPushButton, QLabel)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

class ParameterTreeWidget(QTreeWidget):
    parameter_toggled = pyqtSignal(str, bool, str)  # parameter_name, is_checked, color
    color_changed = pyqtSignal(str, str)  # parameter_name, color
    
    def __init__(self):
        super().__init__()
        self.setHeaderLabels(["Параметр", "Цвет"])
        self.setColumnCount(2)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(1, 60)
        
        self.parameter_checkboxes = {}  # Словарь чекбоксов
        self.parameter_color_buttons = {}  # Словарь кнопок цвета
        self.parameter_colors = {}  # Храним цвета параметров
        
    def update_tree(self, parameters_tree):
        """Обновляет дерево параметров с информацией о временных метках"""
        self.clear()
        self.parameter_checkboxes.clear()
        self.parameter_color_buttons.clear()
        self.parameter_colors.clear()
        
        # Предопределенная палитра цветов
        default_colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
        ]
        color_index = 0
        
        for msg_type, msg_info in parameters_tree.items():
            msg_item = QTreeWidgetItem(self)
            msg_item.setText(0, msg_type)
            
            # Добавляем информацию о доступных временных метках
            time_info = f"Время: {', '.join(msg_info['available_timestamps'])}"
            msg_item.setToolTip(0, f"{msg_info['description']}\n{time_info}")
            
            # Выделяем заголовок жирным
            font = QFont()
            font.setBold(True)
            msg_item.setFont(0, font)
            
            for field_name, field_info in msg_info['fields'].items():
                if not field_info['has_data']:
                    continue  # Пропускаем поля без данных
                    
                field_item = QTreeWidgetItem(msg_item)
                field_item.setText(0, field_name)
                #field_item.setText(1, f"{field_info['data_points']}")
                
                # Назначаем цвет по умолчанию
                parameter_name = field_info['full_name']
                default_color = default_colors[color_index % len(default_colors)]
                self.parameter_colors[parameter_name] = default_color
                color_index += 1
                
                # Чекбокс для выбора параметра
                checkbox_widget = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_widget)
                checkbox_layout.setContentsMargins(2, 2, 2, 2)
                
                checkbox = QCheckBox()
                checkbox.stateChanged.connect(
                    lambda state, p=parameter_name: 
                    self._on_parameter_toggled(p, state == Qt.Checked)
                )
                
                checkbox_layout.addWidget(checkbox)
                checkbox_layout.setAlignment(checkbox, Qt.AlignCenter)
                
                # Кнопка выбора цвета
                color_button = QPushButton()
                color_button.setFixedSize(20, 20)
                color_button.setStyleSheet(f"background-color: {default_color}; border: 1px solid #666;")
                color_button.clicked.connect(
                    lambda checked=False, p=parameter_name: 
                    self._choose_color(p)
                )
                
                self.setItemWidget(field_item, 0, checkbox_widget)
                self.setItemWidget(field_item, 1, color_button)
                
                self.parameter_checkboxes[parameter_name] = checkbox
                self.parameter_color_buttons[parameter_name] = color_button
            
            # msg_item.setExpanded(True)
    
    def _on_parameter_toggled(self, parameter_name, is_checked):
        """Обработка переключения чекбокса"""
        color = self.parameter_colors[parameter_name]
        self.parameter_toggled.emit(parameter_name, is_checked, color)
    
    def _choose_color(self, parameter_name):
        """Выбор цвета для параметра"""
        current_color = QColor(self.parameter_colors[parameter_name])
        color = QColorDialog.getColor(current_color)
        if color.isValid():
            self.set_parameter_color(parameter_name, color.name())
            self.color_changed.emit(parameter_name, color.name())
    
    def set_parameter_color(self, parameter_name, color):
        """Устанавливает цвет для параметра и обновляет кнопку"""
        if parameter_name in self.parameter_color_buttons:
            self.parameter_colors[parameter_name] = color
            button = self.parameter_color_buttons[parameter_name]
            button.setStyleSheet(f"background-color: {color}; border: 1px solid #666;")
    
    def get_parameter_color(self, parameter_name):
        """Возвращает цвет параметра"""
        return self.parameter_colors.get(parameter_name, '#1f77b4')