from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QLineEdit, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal
from datetime import datetime, timezone
import pyqtgraph as pg
import numpy as np


class TimeAxis(pg.AxisItem):
    """Ось времени, которая для GPS показывает HH:MM:SS."""
    def __init__(self, get_time_type, get_time_offset, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._get_time_type = get_time_type
        self._get_time_offset = get_time_offset

    def tickStrings(self, values, scale, spacing):
        time_type = self._get_time_type()
        if time_type == 'GPS':
            offset = self._get_time_offset() or 0.0
            labels = []
            for v in values:
                try:
                    dt = datetime.fromtimestamp(v + offset, tz=timezone.utc)
                    labels.append(dt.strftime('%H:%M:%S'))
                except Exception:
                    labels.append('')
            return labels
        return super().tickStrings(values, scale, spacing)
    

class CustomViewBox(pg.ViewBox):
    """
    ViewBox с раздельным зумом по осям:
      - колесо мыши   -> зум только по X
      - Shift + колесо -> зум только по Y
    Панорамирование (drag) остаётся по обеим осям.
    """
    def wheelEvent(self, ev, axis=None):
        mods = ev.modifiers()
        # Если зажат Shift — зумим только по Y
        if mods & Qt.ShiftModifier:
            axis = 1   # 0 = X, 1 = Y
        else:
            # По умолчанию зумим только по X
            axis = 0

        super().wheelEvent(ev, axis=axis)


class PlotWidget(QWidget):
    time_type_changed = pyqtSignal(str)
    cursor_position_changed = pyqtSignal(float, dict)  # x_position, parameter_values
    active_plot_changed = pyqtSignal(str)  # Новый сигнал при смене активного графика
    
    def __init__(self):
        super().__init__()
        self.plots = {}  # parameter_name: plot_item
        self.plot_data = {}  # parameter_name: (x_data, y_data)
        self.plot_colors = {}  # parameter_name: color
        self.active_plot = None
        self.cursor_line = None
        self.cursor_points = {}  # Точки пересечения для каждого графика
        self.original_data = {}  # parameter_name: (original_x, original_y)
        self.scaling_applied = False  # Флаг масштабирования
        self.shift_original_data = {} # parameter_name: (original_x, original_y)
        self.shift_applied = False
        self.time_offset = 0.0  # смещение TimeUS -> GPS
        
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса графика"""
        layout = QVBoxLayout(self)

        # Панель управления сверху
        control_layout = QHBoxLayout()

        # Комбо для типа времени
        self.time_type_combo = QComboBox()
        self.time_type_combo.addItems(['TimeUS', 'GPS'])
        self.time_type_combo.currentTextChanged.connect(self._on_time_type_combo_changed)

        # Комбо для активного графика
        self.active_plot_combo = QComboBox()
        self.active_plot_combo.currentTextChanged.connect(self.on_active_plot_combo_changed)

        # Кнопка смены цвета
        self.color_btn = QPushButton("Изменить цвет")
        self.color_btn.clicked.connect(self.change_active_plot_color)
        self.color_btn.setEnabled(False)

        # Сброс масштаба всех -> Фокус на всех
        self.reset_all_btn = QPushButton("Фокус на всех")
        self.reset_all_btn.clicked.connect(self.reset_all_plots)

        # Сброс активного -> Фокус на активном
        self.reset_active_btn = QPushButton("Фокус на активный")
        self.reset_active_btn.clicked.connect(self.reset_active_plot)
        self.reset_active_btn.setEnabled(False)

        # Лейбл даты GPS (год-месяц-день)
        self.gps_date_label = QLabel("")
        self.gps_date_label.setStyleSheet("color: gray; font-size: 10px;")

        # Собираем control_layout
        control_layout.addWidget(QLabel("Ось времени:"))
        control_layout.addWidget(self.time_type_combo)
        control_layout.addWidget(QLabel("Активный график:"))
        control_layout.addWidget(self.active_plot_combo)
        control_layout.addWidget(self.color_btn)
        control_layout.addWidget(self.reset_all_btn)
        control_layout.addWidget(self.reset_active_btn)
        control_layout.addWidget(self.gps_date_label)
        control_layout.addStretch()

        # Добавляем шапку в основной layout
        layout.addLayout(control_layout)

        # График с пользовательской осью времени
        self.time_axis = TimeAxis(
            get_time_type=lambda: self.time_type_combo.currentText(),
            get_time_offset=lambda: self.time_offset,
            orientation='bottom'
        )

        # ViewBox с раздельным зумом
        self.view_box = CustomViewBox()
        self.graph_widget = pg.PlotWidget(viewBox=self.view_box,
                                        axisItems={'bottom': self.time_axis})
        self.graph_widget.setBackground('w')
        self.graph_widget.showGrid(x=True, y=True, alpha=0.3)
        self.graph_widget.setLabel('left', 'Значение')
        self.graph_widget.setLabel('bottom', 'Время')

        # Легенда
        self.legend = self.graph_widget.addLegend()

        # Линия курсора
        self.cursor_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen("#000000", width=1)
        )
        self.cursor_line.setVisible(False)
        self.graph_widget.addItem(self.cursor_line, ignoreBounds=True)

        # События мыши
        self.graph_widget.scene().sigMouseMoved.connect(self.on_mouse_moved)
        self.graph_widget.scene().sigMouseClicked.connect(self.on_mouse_clicked)

        # Добавляем график в layout
        layout.addWidget(self.graph_widget)

        # Панель масштабирования данных снизу
        scale_data_layout = QHBoxLayout()
        scale_data_layout.addWidget(QLabel("Масштаб данных:"))

        # Выбор оси
        self.scale_axis_combo = QComboBox()
        self.scale_axis_combo.addItems(["Ось X", "Ось Y"])
        scale_data_layout.addWidget(self.scale_axis_combo)

        # Выбор цели (активный / все)
        self.scale_target_combo = QComboBox()
        self.scale_target_combo.addItems(["Активный график", "Все графики"])
        scale_data_layout.addWidget(self.scale_target_combo)

        # Коэффициент
        self.scale_factor_edit = QLineEdit()
        self.scale_factor_edit.setPlaceholderText("Коэффициент")
        self.scale_factor_edit.setMaximumWidth(80)
        self.scale_factor_edit.setText("1.0")
        scale_data_layout.addWidget(self.scale_factor_edit)

        # Кнопки
        self.scale_apply_btn = QPushButton("Применить масштаб")
        self.scale_apply_btn.clicked.connect(self.apply_data_scaling)
        scale_data_layout.addWidget(self.scale_apply_btn)

        self.scale_reset_btn = QPushButton("Сбросить масштаб")
        self.scale_reset_btn.clicked.connect(self.reset_data_scaling)
        scale_data_layout.addWidget(self.scale_reset_btn)

        scale_data_layout.addStretch()

        # Добавляем панель масштаба в самый низ
        layout.addLayout(scale_data_layout)


        # Панель сдвига данных снизу
        shift_data_layout = QHBoxLayout()
        shift_data_layout.addWidget(QLabel("Сдвиг данных:"))

        # Ось
        self.shift_axis_combo = QComboBox()
        self.shift_axis_combo.addItems(["Ось X", "Ось Y"])
        shift_data_layout.addWidget(self.shift_axis_combo)

        # Цель
        self.shift_target_combo = QComboBox()
        self.shift_target_combo.addItems(["Активный график", "Все графики"])
        shift_data_layout.addWidget(self.shift_target_combo)

        # Величина сдвига
        self.shift_value_edit = QLineEdit()
        self.shift_value_edit.setPlaceholderText("Смещение")
        self.shift_value_edit.setMaximumWidth(80)
        self.shift_value_edit.setText("0.0")
        shift_data_layout.addWidget(self.shift_value_edit)

        # Кнопка "Применить"
        self.shift_apply_btn = QPushButton("Применить сдвиг")
        self.shift_apply_btn.clicked.connect(self.apply_data_shift)
        shift_data_layout.addWidget(self.shift_apply_btn)

        # Кнопка "Сбросить сдвиг"
        self.shift_reset_btn = QPushButton("Сбросить сдвиг")
        self.shift_reset_btn.clicked.connect(self.reset_data_shift)
        shift_data_layout.addWidget(self.shift_reset_btn)

        shift_data_layout.addStretch()

        layout.addLayout(shift_data_layout)

    
    def on_active_plot_combo_changed(self, plot_name):
        """Обработка изменения активного графика через комбобокс"""
        if plot_name and plot_name in self.plots:
            self.set_active_plot(plot_name)
    
    def change_active_plot_color(self):
        """Изменение цвета активного графика"""
        if self.active_plot:
            from PyQt5.QtWidgets import QColorDialog
            color = QColorDialog.getColor()
            if color.isValid():
                self.update_plot_color(self.active_plot, color.name())
                self.active_plot_changed.emit(self.active_plot)
    
    def add_plot(self, parameter_name, x_data, y_data, color='#1f77b4'):
        """Добавляет новый график"""
        if parameter_name in self.plots:
            self.remove_plot(parameter_name)
        
        # Создаем график
        plot = self.graph_widget.plot(x_data, y_data, 
                                    name=parameter_name, 
                                    pen=pg.mkPen(color, width=2))
        
        self.plots[parameter_name] = plot
        self.plot_data[parameter_name] = (x_data, y_data)
        self.plot_colors[parameter_name] = color
        
        # Обновляем комбобокс активных графиков
        self.active_plot_combo.addItem(parameter_name)
        
        # Создаем точку для курсора
        cursor_point = pg.ScatterPlotItem([0], [0], 
                                        pen=pg.mkPen(color, width=2),
                                        brush=pg.mkBrush(color),
                                        size=10, symbol='o')
        cursor_point.setVisible(False)
        self.graph_widget.addItem(cursor_point)
        self.cursor_points[parameter_name] = cursor_point

        # Устанавливаем начальную позицию курсора в видимой области
        if len(x_data) > 0:
            initial_pos = x_data[0]  # Первая точка данных
            self.cursor_line.setPos(initial_pos)
            self.cursor_line.setVisible(True)
        
        # Устанавливаем как активный если это первый график
        if self.active_plot is None:
            self.set_active_plot(parameter_name)
        else:
            # Для неактивных графиков делаем линию тоньше
            plot.setPen(pg.mkPen(color, width=2))

        # Обновляем подпись даты, если активен GPS
        self.update_gps_date_label()
        
        # Автомасштабирование по Y для нового графика
        self.auto_scale_y(parameter_name)
    
    def remove_plot(self, parameter_name):
        """Удаляет график"""
        if parameter_name in self.plots:
            self.graph_widget.removeItem(self.plots[parameter_name])
            if parameter_name in self.cursor_points:
                self.graph_widget.removeItem(self.cursor_points[parameter_name])
            
            # Удаляем из комбобокса
            index = self.active_plot_combo.findText(parameter_name)
            if index >= 0:
                self.active_plot_combo.removeItem(index)
            
            del self.plots[parameter_name]
            del self.plot_data[parameter_name]
            del self.cursor_points[parameter_name]
            del self.plot_colors[parameter_name]
            del self.original_data[parameter_name]
            del self.shift_original_data[parameter_name]
            
            if self.active_plot == parameter_name:
                # Выбираем следующий доступный график
                if self.plots:
                    new_active = list(self.plots.keys())[0]
                    self.set_active_plot(new_active)
                else:
                    self.active_plot = None
                    self.color_btn.setEnabled(False)
                    self.reset_active_btn.setEnabled(False)
                    self.scaling_applied = False
                    self.shift_applied = False


    def clear_all_plots(self):
        """Полностью очищает все графики, но сохраняет оси, легенду и линию курсора"""
        # Удаляем линии графиков
        for plot in self.plots.values():
            self.graph_widget.removeItem(plot)
        # Удаляем маркеры курсора
        for point in self.cursor_points.values():
            self.graph_widget.removeItem(point)

        self.plots.clear()
        self.plot_data.clear()
        self.plot_colors.clear()
        self.cursor_points.clear()
        self.original_data.clear()
        self.shift_original_data.clear()

        self.scaling_applied = False
        self.shift_applied = False

        self.active_plot_combo.clear()
        self.active_plot = None

        # Очищаем легенду, но не удаляем её
        if self.legend is not None:
            self.legend.clear()

        # Вертикальная линия
        if self.cursor_line is not None:
            self.cursor_line.setPos(0)
            self.cursor_line.setVisible(True)

        # Подпись даты для GPS
        self.update_gps_date_label()

    
    def set_active_plot(self, parameter_name):
        """Устанавливает активный график"""
        if parameter_name in self.plots:
            self.active_plot = parameter_name
            self.active_plot_combo.setCurrentText(parameter_name)
            
            # Включаем кнопки управления
            self.color_btn.setEnabled(True)
            self.reset_active_btn.setEnabled(True)
            
            # Подсвечиваем активный график
            for name, plot in self.plots.items():
                color = self.plot_colors[name]
                if name == parameter_name:
                    plot.setPen(pg.mkPen(color, width=3))  # Толще для активного
                else:
                    plot.setPen(pg.mkPen(color, width=2))  # Тоньше для неактивных
            
            self.active_plot_changed.emit(parameter_name)

            self.auto_scale_y(parameter_name) # масштабирование
    
    def update_plot_color(self, parameter_name, color):
        """Обновляет цвет графика"""
        if parameter_name in self.plots and parameter_name in self.plot_colors:
            self.plot_colors[parameter_name] = color
            plot = self.plots[parameter_name]
            cursor_point = self.cursor_points[parameter_name]
            
            # Обновляем цвет линии
            is_active = (parameter_name == self.active_plot)
            line_width = 3 if is_active else 1
            plot.setPen(pg.mkPen(color, width=line_width))
            
            # Обновляем цвет точки курсора
            cursor_point.setPen(pg.mkPen(color, width=2))
            cursor_point.setBrush(pg.mkBrush(color))
            
            # Обновляем легенду (перерисовываем график)
            x_data, y_data = self.plot_data[parameter_name]
            plot.setData(x_data, y_data)
    
    def auto_scale_y(self, parameter_name):
        """Автомасштабирование по Y для конкретного графика"""
        if parameter_name in self.plot_data:
            x_data, y_data = self.plot_data[parameter_name]
            if len(y_data) > 0:
                y_min, y_max = np.min(y_data), np.max(y_data)
                y_range = y_max - y_min
                
                if y_range > 0:
                    # Добавляем 10% запаса
                    padding = y_range * 0.1
                    self.graph_widget.setYRange(y_min - padding, y_max + padding, padding=0)
    
    def reset_all_plots(self):
        """Сброс масштаба всех графиков"""
        if self.plot_data:
            all_x = []
            all_y = []
            
            for x_data, y_data in self.plot_data.values():
                all_x.extend(x_data)
                all_y.extend(y_data)
            
            if all_x and all_y:
                x_min, x_max = np.min(all_x), np.max(all_x)
                y_min, y_max = np.min(all_y), np.max(all_y)
                
                x_range = x_max - x_min
                y_range = y_max - y_min
                
                if x_range > 0 and y_range > 0:
                    padding_x = x_range * 0.05
                    padding_y = y_range * 0.05
                    self.graph_widget.setRange(xRange=(x_min-padding_x, x_max+padding_x),
                                             yRange=(y_min-padding_y, y_max+padding_y))
    
    def reset_active_plot(self):
        """Сброс масштаба активного графика"""
        if self.active_plot:
            self.auto_scale_y(self.active_plot)
    
    def on_mouse_moved(self, pos):
        """Обработка движения мыши"""
        if self.graph_widget.plotItem.vb.mapSceneToView(pos) is None:
            return
            
        mouse_point = self.graph_widget.plotItem.vb.mapSceneToView(pos)
        x_pos = mouse_point.x()
        
        # Обновляем позицию линии курсора
        self.cursor_line.setPos(x_pos)
        self.cursor_line.setVisible(True)  # Линия видима
        
        # Находим ближайшие точки для каждого графика
        parameter_values = {}
        
        for param_name, (x_data, y_data) in self.plot_data.items():
            if len(x_data) > 0:
                # Находим ближайшую точку
                idx = np.argmin(np.abs(x_data - x_pos))
                
                if idx < len(x_data) and idx < len(y_data):
                    closest_x = x_data[idx]
                    closest_y = y_data[idx]
                    
                    # Обновляем позицию точки
                    self.cursor_points[param_name].setData([closest_x], [closest_y])
                    self.cursor_points[param_name].setVisible(True)
                    
                    parameter_values[param_name] = {
                        'x': closest_x,
                        'y': closest_y,
                        'distance': abs(closest_x - x_pos)
                    }
        
        # Подсвечиваем точку активного графика
        for param_name in self.cursor_points:
            if param_name == self.active_plot and param_name in parameter_values:
                point = self.cursor_points[param_name]
                point.setSize(12)  # Больше для активного
            else:
                point = self.cursor_points[param_name]
                point.setSize(8)
        
        self.cursor_position_changed.emit(x_pos, parameter_values)
    
    def on_mouse_clicked(self, event):
        """Обработка клика мыши для выбора активного графика"""
        if event.double():
            # Двойной клик - сброс масштаба активного графика
            self.reset_active_plot()
        else:
            # Одинарный клик - выбор графика под курсором
            if self.graph_widget.plotItem.vb.mapSceneToView(event.scenePos()) is None:
                return
                
            mouse_point = self.graph_widget.plotItem.vb.mapSceneToView(event.scenePos())
            
            # Находим ближайший график к точке клика
            closest_plot = None
            min_distance = float('inf')
            
            for param_name, (x_data, y_data) in self.plot_data.items():
                if len(x_data) > 0:
                    # Находим ближайшую точку на графике
                    distances = np.sqrt((x_data - mouse_point.x())**2 + (y_data - mouse_point.y())**2)
                    min_idx = np.argmin(distances)
                    distance = distances[min_idx]
                    
                    if distance < min_distance and distance < 0.1:  # Порог чувствительности
                        min_distance = distance
                        closest_plot = param_name
            
            if closest_plot and closest_plot != self.active_plot:
                self.set_active_plot(closest_plot)
    
    def update_plot_data(self, parameter_name, x_data, y_data):
        """Обновляет данные графика"""
        if parameter_name in self.plots and parameter_name in self.plot_data:
            self.plot_data[parameter_name] = (x_data, y_data)
            self.plots[parameter_name].setData(x_data, y_data)


    def _get_parameters_to_modify(self, target: str):
        """Возвращает список параметров для преобразования (масштаб/сдвиг)."""
        if target == "Активный график" and self.active_plot:
            return [self.active_plot]
        elif target == "Все графики":
            return list(self.plot_data.keys())
        return []


    def apply_data_scaling(self):
        """Применяет масштабирование к данным графика"""
        try:
            # Получаем параметры масштабирования
            axis = self.scale_axis_combo.currentText()  # "Ось X" или "Ось Y"
            target = self.scale_target_combo.currentText()  # "Активный график" или "Все графики"
            scale_factor = float(self.scale_factor_edit.text())
            
            if scale_factor == 0:
                QMessageBox.warning(self, "Ошибка", "Коэффициент масштабирования не может быть равен 0")
                return
            
            parameters_to_scale = self._get_parameters_to_modify(target)
            if not parameters_to_scale:
                QMessageBox.warning(self, "Ошибка", "Нет графиков для масштабирования")
                return
            
            # Сохраняем оригинальные данные если их нет
            for param_name in parameters_to_scale:
                if param_name not in self.original_data:
                    x_data, y_data = self.plot_data[param_name]
                    self.original_data[param_name] = (x_data.copy(), y_data.copy())
            
            # Применяем масштабирование
            for param_name in parameters_to_scale:
                if param_name in self.plot_data:
                    # Получаем оригинальные данные
                    curr_x, curr_y = self.plot_data[param_name]
                    
                    # Применяем масштабирование к выбранной оси
                    if axis == "Ось X":
                        new_x_data = curr_x * scale_factor
                        new_y_data = curr_y
                    else:  # "Ось Y"
                        new_x_data = curr_x
                        new_y_data = curr_y * scale_factor
                    
                    # Обновляем данные графика
                    self.plot_data[param_name] = (new_x_data, new_y_data)
                    self.plots[param_name].setData(new_x_data, new_y_data)

            # Устанавливаем флаг, что масштабирование применялось
            self.scaling_applied = True
            
            # Показываем сообщение о примененном масштабировании
            axis_name = "X (время)" if axis == "Ось X" else "Y (значения)"
            target_name = "активный график" if target == "Активный график" else "все графики"
            self.statusBar().showMessage(f"Применен масштаб {scale_factor} к оси {axis_name} для {target_name}")
            
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Введите корректный числовой коэффициент")

    def reset_data_scaling(self):
        """Сбрасывает масштабирование данных к оригинальным значениям"""
        if not self.scaling_applied:
            QMessageBox.information(self, "Информация", "Масштабирование не применялось")
            return
        
        # Восстанавливаем оригинальные данные для всех графиков
        for param_name, (orig_x, orig_y) in self.original_data.items():
            if param_name in self.plot_data:
                self.plot_data[param_name] = (orig_x.copy(), orig_y.copy())
                self.plots[param_name].setData(orig_x, orig_y)

        self.scaling_applied = False
        
        self.statusBar().showMessage("Масштабирование данных сброшено")


    def apply_data_shift(self):
        """Применяет сдвиг к данным графика (по X или Y)."""
        try:
            axis = self.shift_axis_combo.currentText()        # "Ось X" или "Ось Y"
            target = self.shift_target_combo.currentText()    # "Активный график" или "Все графики"
            shift_value = float(self.shift_value_edit.text())

            parameters_to_shift = self._get_parameters_to_modify(target)
            if not parameters_to_shift:
                QMessageBox.warning(self, "Ошибка", "Нет графиков для сдвига")
                return

            # Сохраняем "оригинальные" данные до сдвига (если ещё не сохранены)
            for param_name in parameters_to_shift:
                if param_name not in self.shift_original_data and param_name in self.plot_data:
                    x_data, y_data = self.plot_data[param_name]
                    self.shift_original_data[param_name] = (np.array(x_data, dtype=float).copy(),
                                                        np.array(y_data, dtype=float).copy())

            # Применяем сдвиг
            for param_name in parameters_to_shift:
                if param_name not in self.plot_data:
                    continue

                curr_x, curr_y = self.plot_data[param_name]
                curr_x = np.array(curr_x, dtype=float)
                curr_y = np.array(curr_y, dtype=float)

                if axis == "Ось X":
                    new_x = curr_x + shift_value
                    new_y = curr_y
                else:  # "Ось Y"
                    new_x = curr_x
                    new_y = curr_y + shift_value

                self.plot_data[param_name] = (new_x, new_y)
                self.plots[param_name].setData(new_x, new_y)

            self.shift_applied = True

            axis_name = "X (время)" if axis == "Ось X" else "Y (значения)"
            target_name = "активный график" if target == "Активный график" else "все графики"
            self.statusBar().showMessage(f"Применен сдвиг {shift_value} по оси {axis_name} для {target_name}")

        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Введите корректное числовое значение сдвига")


    def reset_data_shift(self):
        """Сбрасывает сдвиг данных к оригинальным значениям (без вычитания) — аналогично reset_data_scaling."""
        if not self.shift_applied:
            QMessageBox.information(self, "Информация", "Сдвиг не применялся")
            return

        # Восстанавливаем оригинальные данные для всех графиков, для которых сохранён "оригинал до сдвига"
        for param_name, (orig_x, orig_y) in self.shift_original_data.items():
            if param_name in self.plot_data and param_name in self.plots:
                self.plot_data[param_name] = (orig_x.copy(), orig_y.copy())
                self.plots[param_name].setData(orig_x, orig_y)

        self.shift_applied = False
        self.statusBar().showMessage("Сдвиг данных сброшен")


    def _on_time_type_combo_changed(self, text: str):
        """Локальная обработка выбора типа времени."""
        self.time_type_changed.emit(text)
        self.update_gps_date_label()

        # обновление оси
        axis = self.graph_widget.getPlotItem().getAxis('bottom')
        axis.picture = None
        axis.update()

    def update_gps_date_label(self):
        """Выводит один раз дату GPS на панели, когда выбрана шкала GPS."""
        if self.time_type_combo.currentText() != 'GPS':
            self.gps_date_label.setText("")
            return

        # Находим минимальный timestamp среди всех графиков
        first_ts = None
        for x_data, _ in self.plot_data.values():
            if len(x_data) > 0:
                ts = x_data[0]
                if first_ts is None or ts < first_ts:
                    first_ts = ts

        if first_ts is None:
            self.gps_date_label.setText("Дата GPS: нет данных")
            return
        
        offset = self.time_offset or 0.0
        dt = datetime.fromtimestamp(first_ts + offset, tz=timezone.utc)
        self.gps_date_label.setText(f"Дата GPS: {dt.strftime('%Y-%m-%d')}")

    def set_time_offset(self, offset: float):
        self.time_offset = offset
        self.update_gps_date_label()
