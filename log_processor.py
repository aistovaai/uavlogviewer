from pymavlink import mavutil
from collections import defaultdict
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Set, Union
import json
import os

class LogProcessor:
    def __init__(self, logfile_path):
        self.logfile_path: str = logfile_path
        self.message_data: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.message_descriptions: Dict[str, str] = self._load_message_descriptions()
        self.time_offset: int = 0
        
    def parse_log(self):
        """Парсинг лог-файла"""
        mav = mavutil.mavlink_connection(self.logfile_path, input='bin')

        offsets = []
        
        while True:
            msg = mav.recv_match()
            if msg is None:
                break
                
            msg_type = msg.get_type()

            timestamps = self._get_timestamps(msg)

            # Собираем смещения времени из GPS сообщений
            if hasattr(msg, 'TimeUS') and hasattr(msg, 'GMS') and hasattr(msg, 'GWk'):
                gps_time = self._gps_to_seconds(msg.GWk, msg.GMS)
                if gps_time > 0:
                    timeus_seconds = msg.TimeUS / 1e6
                    offset = gps_time - timeus_seconds
                    offsets.append(offset)
        
            
            # Сохраняем сообщение с временными метками
            message_record = {
                'timestamp': timestamps,
                'data': self._message_to_dict(msg)
            }
            
            self.message_data[msg_type].append(message_record)

        # Вычисляем среднее смещение между TimeUS и GPS
        if offsets:
            self.time_offset = np.mean(offsets)
            self._timeus_to_gps()
    
    def _get_timestamps(self, msg):
        """Извлекает все доступные временные метки из сообщения"""
        timestamps = {}
        
        # TimeUS - микросекунды с запуска системы
        if hasattr(msg, 'TimeUS'):
            timestamps['TimeUS'] = msg.TimeUS / 1e6
        
        # GPS время (GMS, GWk)
        if hasattr(msg, 'GMS') and hasattr(msg, 'GWk'):
            gps_time = self._gps_to_seconds(msg.GWk, msg.GMS)
            timestamps['GPS'] = gps_time

        return timestamps
    
    def _gps_to_seconds(self, gps_week, gps_ms):
        """Конвертирует GPS неделю и миллисекунды в секунды от эпохи"""

        # gps_epoch - начало 6 января 1980
        gps_epoch = 315964800
        seconds_per_week = 604800
        
        return gps_epoch + (gps_week * seconds_per_week) + (gps_ms / 1000.0)
    
    def _timeus_to_gps(self):
        """Конвертирует TimeUS в мировое время с использованием смещения"""
        for msg_type, messages in self.message_data.items():
            for message in messages:
                ts = message['timestamp']

                if 'TimeUS' in ts and 'GPS' not in ts:
                    message['timestamp']['GPS'] = ts['TimeUS'] + self.time_offset
        
    
    def _message_to_dict(self, msg):
        """Преобразует MAVLink сообщение в словарь (без временных меток)"""
        result = {}

        for field in msg.get_fieldnames():
            # Пропускаем временные метки, они уже сохранены отдельно
            if field not in ['TimeUS', 'GMS', 'GWk']:
                value = getattr(msg, field, None)
                result[field] = value
        return result
    

    def _load_message_descriptions(self):
        """Загружает описания сообщений/полей MAVLink из JSON (MSG и MSG.FIELD)."""
        descriptions = {}
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, "utils", "mavlink_params.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    descriptions = json.load(f)
            else:
                print(f"Файл описаний не найден: {path}")
        except Exception as e:
            print(f"Не удалось загрузить описания MAVLink: {e}")
        return descriptions

    
    
    def get_parameter_data(self, parameter_name, time_type='TimeUS'):
        """
        Получает данные параметра и соответствующие временные метки
        parameter_name в формате 'MSG_TYPE.FIELD_NAME'
        """
        try:
            msg_type, field_name = parameter_name.split('.', 1)
            
            if msg_type not in self.message_data:
                return None, None
            
            x_data = []
            y_data = []
            
            for message_record in self.message_data[msg_type]:
                # Получаем значение поля
                field_value = message_record['data'].get(field_name)
                if field_value is None:
                    continue
                
                # Получаем временную метку
                timestamp = message_record['timestamp'].get(time_type)
                if timestamp is None:
                    # Если запрошенный тип времени недоступен, попробуем другие (сообщить? или может ошибку дать)
                    for alt_time_type in ['TimeUS', 'GPS']:
                        timestamp = message_record['timestamp'].get(alt_time_type)
                        if timestamp is not None:
                            break
                
                if timestamp is not None and field_value is not None:
                    x_data.append(timestamp)
                    y_data.append(field_value)
            
            if not x_data:
                return None, None
                
            return np.array(x_data), np.array(y_data)
            
        except Exception as e:
            print(f"Ошибка получения данных для {parameter_name}: {e}")
            return None, None
    
    def get_available_parameters(self):
        """Возвращает древовидную структуру параметров с информацией о доступных временных метках"""
        tree = {}
        
        for msg_type, messages in self.message_data.items():
            if not messages:
                continue
                
            if msg_type not in tree:
                tree[msg_type] = {
                    'description': self.message_descriptions.get(msg_type, 'Описание недоступно'),
                    'available_timestamps': set(),
                    'fields': {}
                }
            
            # Собираем все доступные временные метки для этого типа сообщений
            for message in messages:
                tree[msg_type]['available_timestamps'].update(message['timestamp'].keys())
            
            # Собираем все поля из первого сообщения
            first_message_data = messages[0]['data']
            for field_name in first_message_data.keys():
                # Подсчитываем количество ненулевых значений
                has_data = sum(1 for msg in messages 
                                if msg['data'].get(field_name) is not None) > 0
                
                full_name = f"{msg_type}.{field_name}"
                tree[msg_type]['fields'][field_name] = {
                    'full_name': full_name,
                    'has_data': has_data,
                    'description': self.message_descriptions.get(full_name, "")
                }
        
        # Преобразуем множества в списки
        for msg_type in tree:
            tree[msg_type]['available_timestamps'] = list(tree[msg_type]['available_timestamps'])
            
        return tree

    def get_time_types_available(self):
        """Возвращает все доступные типы временных меток во всем логе"""
        all_time_types = set()
        for msg_type, messages in self.message_data.items():
            for message in messages:
                all_time_types.update(message['timestamp'].keys())
        return list(all_time_types)

    def get_message_statistics(self):
        """Статистика по сообщениям"""
        stats = {}
        for msg_type, messages in self.message_data.items():
            stats[msg_type] = {
                'available_timestamps': list(set().union(*(msg['timestamp'].keys() for msg in messages)))
            }
        return stats
