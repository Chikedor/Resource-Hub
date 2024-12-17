import customtkinter as ctk
import psutil
import threading
from datetime import datetime, timedelta
from plyer import notification
import platform
import os
import sys
from collections import deque
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
import glob
import json
from logger_config import (
    get_logger,
    log_metrics,
    log_performance,
    log_error,
    log_warning,
    log_debug
)
import cProfile
import io
import pstats
from functools import wraps
from typing import Deque, Callable, Optional, Any, Dict
import numpy as np
from dataclasses import dataclass
from threading import Lock
import tkinter.messagebox as messagebox
import tkinter as tk

# Tema estándar
THEME = {
    'primary': '#2196f3',
    'background': '#1e1e1e',
    'card_bg': '#2d2d2d',
    'text': '#ffffff',
    'danger': '#f44336',
    'success': '#4caf50',
    'warning': '#ff9800',
    'info': '#00bcd4',
    'metrics': {
        'cpu': '#2196f3',
        'ram': '#4caf50',
        'disk': '#ff9800',
        'gpu': '#f44336'
    }
}

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    print("GPUtil no está disponible. La monitorización de GPU estará desactivada.")

class UIFactory:
    """Clase utilitaria para crear widgets de UI consistentes"""
    @staticmethod
    def create_button(
        master: Any,
        text: str,
        command: Callable,
        width: int = 100,
        fg_color: Optional[str] = None,
        hover_color: Optional[str] = None,
        **kwargs
    ) -> ctk.CTkButton:
        """Crea un botón con estilo consistente"""
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            width=width,
            fg_color=fg_color or THEME['primary'],
            hover_color=hover_color or UIFactory.apply_brightness(fg_color or THEME['primary'], 0.8),
            **kwargs
        )

    @staticmethod
    def create_label(
        master: Any,
        text: str,
        font_size: int = 12,
        bold: bool = False,
        text_color: Optional[str] = None,
        **kwargs
    ) -> ctk.CTkLabel:
        """Crea una etiqueta con estilo consistente"""
        font = ('Segoe UI', font_size, 'bold') if bold else ('Segoe UI', font_size)
        return ctk.CTkLabel(
            master,
            text=text,
            font=font,
            text_color=text_color or THEME['text'],
            **kwargs
        )

    @staticmethod
    def create_frame(
        master: Any,
        transparent: bool = False,
        **kwargs
    ) -> ctk.CTkFrame:
        """Crea un frame con estilo consistente"""
        if 'fg_color' not in kwargs:
            kwargs['fg_color'] = 'transparent' if transparent else THEME['card_bg']
        return ctk.CTkFrame(
            master,
            **kwargs
        )

    @staticmethod
    def create_separator(
        master: Any,
        height: int = 1,
        **kwargs
    ) -> ctk.CTkFrame:
        """Crea un separador con estilo consistente"""
        return ctk.CTkFrame(
            master,
            height=height,
            fg_color=THEME['primary'],
            **kwargs
        )

    @staticmethod
    def apply_brightness(hex_color: str, factor: float) -> str:
        """Ajusta el brillo de un color hexadecimal"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        new_rgb = tuple(min(255, int(c * factor)) for c in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*new_rgb)

    @staticmethod
    def create_tooltip(
        widget: Any,
        text: str,
        background: Optional[str] = None,
        foreground: Optional[str] = None
    ) -> None:
        """Agrega un tooltip a un widget"""
        tooltip = tk.Toplevel(widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{widget.winfo_rootx() + widget.winfo_width() + 5}+{widget.winfo_rooty() + 5}")

        label = tk.Label(
            tooltip,
            text=text,
            justify='left',
            background=background or THEME['card_bg'],
            foreground=foreground or THEME['text'],
            relief='solid',
            borderwidth=1,
            padx=8,
            pady=4,
            font=('Segoe UI', 10)
        )
        label.pack()
        return tooltip

@dataclass
class MetricData:
    """Clase para almacenar datos de métricas con optimización de memoria"""
    timestamp: float
    value: float

class PerformanceMonitor:
    """Clase para monitorear el rendimiento de la aplicación"""
    def __init__(self, logger):
        self.profiler = cProfile.Profile()
        self.logger = logger
        self.is_profiling = False
        self._lock = Lock()

    def start_profiling(self):
        with self._lock:
            if not self.is_profiling:
                self.profiler.enable()
                self.is_profiling = True
                self.logger.debug("Iniciando perfilado de rendimiento")

    def stop_profiling(self):
        with self._lock:
            if self.is_profiling:
                self.profiler.disable()
                s = io.StringIO()
                stats = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
                stats.print_stats(20)  # Mostrar las 20 funciones más costosas
                self.logger.debug(f"Resultados del perfilado:\n{s.getvalue()}")
                self.profiler = cProfile.Profile()  # Reset profiler
                self.is_profiling = False

def performance_monitor(func):
    """Decorador para monitorear el rendimiento de funciones específicas"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        execution_time = time.perf_counter() - start_time

        # Obtener el logger de la instancia si está disponible, o usar el logger global
        logger = args[0].logger if hasattr(args[0], 'logger') else get_logger()

        if execution_time > 0.1:  # Log solo si toma más de 100ms
            logger.debug(f"Rendimiento: {func.__name__} tomó {execution_time:.3f} segundos")
        return result
    return wrapper

class OptimizedMetricStorage:
    """Clase para manejar el almacenamiento optimizado de métricas"""
    def __init__(self, max_points: int = 60):
        self.max_points = max_points
        # Usar arrays de numpy para mejor rendimiento
        self.timestamps = np.zeros(max_points)
        self.values = np.zeros(max_points)
        self.current_index = 0
        self.is_filled = False
        self._lock = Lock()

    def add_metric(self, value: float, timestamp: float = None):
        with self._lock:
            if timestamp is None:
                timestamp = time.time()

            self.timestamps[self.current_index] = timestamp
            self.values[self.current_index] = value

            self.current_index = (self.current_index + 1) % self.max_points
            if self.current_index == 0:
                self.is_filled = True

    def get_values(self) -> np.ndarray:
        with self._lock:
            if self.is_filled:
                return np.roll(self.values, -self.current_index)
            return self.values[:self.current_index]

    def get_timestamps(self) -> np.ndarray:
        with self._lock:
            if self.is_filled:
                return np.roll(self.timestamps, -self.current_index)
            return self.timestamps[:self.current_index]

    def clear(self):
        with self._lock:
            # Más eficiente que crear nuevos arrays
            self.timestamps.fill(0)
            self.values.fill(0)
            self.current_index = 0
            self.is_filled = False

class Settings:
    def __init__(self):
        self.config_file = 'config.json'
        self.default_settings = {
            'update_interval': 1.0,
            'max_data_points': 60,
            'show_notifications': True,
            'notification_grace_period': 300,
            'thresholds': {
                'cpu': 80,
                'ram': 80,
                'gpu': 80
            },
            'graph': {
                'show': True,
                'line_width': 2,
                'grid_alpha': 0.2
            }
        }
        self.settings = self.load_settings()

    def load_settings(self):
        try:
            if os.path.exists(self.config_file):
                loaded_settings = json.load(open(self.config_file, 'r'))
                # Asegurarse de que no existe 'disk' en los thresholds
                if 'thresholds' in loaded_settings:
                    loaded_settings['thresholds'] = {
                        k: v for k, v in loaded_settings['thresholds'].items()
                        if k in ['cpu', 'ram', 'gpu']
                    }
                return {**self.default_settings, **loaded_settings}
            return self.default_settings.copy()
        except Exception:
            return self.default_settings.copy()

    def save_settings(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

class CustomizationPanel(ctk.CTkFrame):
    def __init__(self, master, settings, on_settings_change, **kwargs):
        super().__init__(master, **kwargs)
        self.settings = settings
        self.on_settings_change = on_settings_change

        # Título
        title = ctk.CTkLabel(
            self,
            text="General Settings",
            font=('Segoe UI', 20, 'bold')
        )
        title.pack(pady=(0,20))

        # Contenedor principal
        main_container = ctk.CTkFrame(self, fg_color=THEME['card_bg'])
        main_container.pack(fill='both', expand=True, padx=5, pady=5)

        # Update Interval
        interval_frame = ctk.CTkFrame(main_container, fg_color='transparent')
        interval_frame.pack(pady=15, padx=15, fill='x')

        # Label del intervalo
        interval_title = ctk.CTkLabel(
            interval_frame,
            text="Update Interval",
            font=('Segoe UI', 14, 'bold')
        )
        interval_title.pack(side='top', anchor='w')

        # Frame para el valor y descripción
        value_frame = ctk.CTkFrame(interval_frame, fg_color='transparent')
        value_frame.pack(fill='x', pady=(5,10))

        self.interval_label = ctk.CTkLabel(
            value_frame,
            text="Current: 1.0s",
            font=('Segoe UI', 12)
        )
        self.interval_label.pack(side='left')

        interval_desc = ctk.CTkLabel(
            value_frame,
            text="(0.1s - 5.0s)",
            font=('Segoe UI', 10),
            text_color='gray'
        )
        interval_desc.pack(side='right')

        # Frame para el slider y botones
        slider_frame = ctk.CTkFrame(interval_frame, fg_color='transparent')
        slider_frame.pack(fill='x')

        # Botón decrementar
        self.decrease_btn = ctk.CTkButton(
            slider_frame,
            text="-",
            width=30,
            command=self._decrease_interval,
            fg_color=THEME['primary']
        )
        self.decrease_btn.pack(side='left', padx=(0, 5))

        # Slider
        self.interval_slider = ctk.CTkSlider(
            slider_frame,
            from_=0.1,
            to=5.0,
            number_of_steps=49,
            command=self._on_interval_change
        )
        self.interval_slider.set(settings.settings['update_interval'])
        self.interval_slider.pack(side='left', fill='x', expand=True, padx=5)

        # Botón incrementar
        self.increase_btn = ctk.CTkButton(
            slider_frame,
            text="+",
            width=30,
            command=self._increase_interval,
            fg_color=THEME['primary']
        )
        self.increase_btn.pack(side='left', padx=(5, 0))

        # Separador
        separator1 = ctk.CTkFrame(main_container, height=1, fg_color=THEME['primary'])
        separator1.pack(fill='x', padx=15, pady=15)

        # Graph Settings
        graph_frame = ctk.CTkFrame(main_container, fg_color='transparent')
        graph_frame.pack(pady=15, padx=15, fill='x')

        graph_title = ctk.CTkLabel(
            graph_frame,
            text="Graph Settings",
            font=('Segoe UI', 14, 'bold')
        )
        graph_title.pack(anchor='w', pady=(0,10))

        self.show_graph_var = ctk.BooleanVar(value=settings.settings['graph']['show'])
        show_graph_cb = ctk.CTkCheckBox(
            graph_frame,
            text="Show Graph",
            variable=self.show_graph_var,
            command=self._on_graph_toggle,
            font=('Segoe UI', 12)
        )
        show_graph_cb.pack(anchor='w')

        # Separador
        separator2 = ctk.CTkFrame(main_container, height=1, fg_color=THEME['primary'])
        separator2.pack(fill='x', padx=15, pady=15)

        # Notifications
        notif_frame = ctk.CTkFrame(main_container, fg_color='transparent')
        notif_frame.pack(pady=15, padx=15, fill='x')

        notif_title = ctk.CTkLabel(
            notif_frame,
            text="Notifications",
            font=('Segoe UI', 14, 'bold')
        )
        notif_title.pack(anchor='w', pady=(0,10))

        self.show_notif_var = ctk.BooleanVar(value=settings.settings['show_notifications'])
        show_notif_cb = ctk.CTkCheckBox(
            notif_frame,
            text="Show Notifications",
            variable=self.show_notif_var,
            command=self._on_notifications_toggle,
            font=('Segoe UI', 12)
        )
        show_notif_cb.pack(anchor='w')

    def _format_interval(self, value):
        if value < 1:
            return f"{value:.1f}s"
        elif value == 1:
            return "1.0s"
        elif value.is_integer():
            return f"{int(value)}s"
        else:
            return f"{value:.1f}s"

    def _on_interval_change(self, value):
        formatted_value = self._format_interval(float(value))
        self.interval_label.configure(text=f"Current: {formatted_value}")
        self.settings.settings['update_interval'] = float(value)
        self.settings.save_settings()
        self.on_settings_change()

    def _decrease_interval(self):
        current = self.interval_slider.get()
        new_value = max(0.1, current - 0.1)
        self.interval_slider.set(new_value)
        self._on_interval_change(new_value)

    def _increase_interval(self):
        current = self.interval_slider.get()
        new_value = min(5.0, current + 0.1)
        self.interval_slider.set(new_value)
        self._on_interval_change(new_value)

    def _on_graph_toggle(self):
        self.settings.settings['graph']['show'] = self.show_graph_var.get()
        self.settings.save_settings()
        self.on_settings_change()

    def _on_notifications_toggle(self):
        self.settings.settings['show_notifications'] = self.show_notif_var.get()
        self.settings.save_settings()
        self.on_settings_change()

class MetricCard(ctk.CTkFrame):
    """Tarjeta optimizada para mostrar métricas del sistema"""
    def __init__(
        self,
        master: Any,
        title: str,
        tooltip_text: str = "",
        metric_color: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            master,
            fg_color=THEME['card_bg'],
            corner_radius=10,
            **kwargs
        )

        self.tooltip = None
        self.tooltip_text = tooltip_text
        self.metric_color = metric_color or THEME['primary']
        self._last_value = 0
        self._animation_after_id = None
        self._setup_ui(title)
        self._setup_events()

    def _setup_ui(self, title: str) -> None:
        """Configura los elementos de la UI"""
        # Título
        self.title_label = UIFactory.create_label(
            self,
            text=title,
            font_size=14,
            bold=True
        )
        self.title_label.grid(row=0, column=0, padx=15, pady=(15,5), sticky="w")

        # Valor principal
        self.value_label = UIFactory.create_label(
            self,
            text="0%",
            font_size=32,
            bold=True
        )
        self.value_label.grid(row=1, column=0, padx=15, pady=5, sticky="w")

        # Información adicional
        self.info_label = UIFactory.create_label(
            self,
            text="",
            font_size=10
        )
        self.info_label.grid(row=2, column=0, padx=15, pady=(0,5), sticky="w")

        # Barra de progreso
        self.progress = ctk.CTkProgressBar(
            self,
            progress_color=self.metric_color,
            height=8,
            corner_radius=4
        )
        self.progress.grid(row=3, column=0, padx=15, pady=(5,15), sticky="ew")
        self.progress.set(0)

        # Configurar grid
        self.grid_columnconfigure(0, weight=1)

    def _setup_events(self) -> None:
        """Configura los eventos de la tarjeta"""
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

    def _on_enter(self, event: Any) -> None:
        """Maneja el evento de entrada del mouse"""
        self.configure(fg_color=UIFactory.apply_brightness(THEME['card_bg'], 1.1))
        if self.tooltip_text:
            self.tooltip = UIFactory.create_tooltip(self, self.tooltip_text)

    def _on_leave(self, event: Any) -> None:
        """Maneja el evento de salida del mouse"""
        self.configure(fg_color=THEME['card_bg'])
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def update(self, value: float, info_text: Optional[str] = None) -> None:
        """Actualiza los valores de la tarjeta con animación optimizada"""
        # Cancelar animación anterior si existe
        if self._animation_after_id:
            self.after_cancel(self._animation_after_id)
            self._animation_after_id = None

        # Actualizar valor con animación solo si el cambio es significativo
        if abs(value - self._last_value) > 0.5:
            self._animate_value(self._last_value, value)
        else:
            self.value_label.configure(text=f"{value:.1f}%")
            self.progress.set(value/100.0)

        self._last_value = value

        # Actualizar información adicional si se proporciona
        if info_text:
            self.info_label.configure(text=info_text)

    def _animate_value(self, start: float, end: float, duration: float = 0.2) -> None:
        """Animación optimizada del valor"""
        steps = 8
        step_size = (end - start) / steps
        step_duration = int((duration * 1000) / steps)

        def update_step(step: int) -> None:
            if step < steps:
                current = start + (step_size * step)
                self.value_label.configure(text=f"{current:.1f}%")
                self.progress.set(current/100.0)
                self._animation_after_id = self.after(
                    step_duration,
                    lambda: update_step(step + 1)
                )
            else:
                self.value_label.configure(text=f"{end:.1f}%")
                self.progress.set(end/100.0)
                self._animation_after_id = None

        update_step(0)

class ThresholdControl(ctk.CTkFrame):
    """Control optimizado para manejar umbrales de recursos"""
    def __init__(
        self,
        master: Any,
        title: str,
        initial_value: float,
        colors: Optional[Dict[str, str]] = None,
        on_change: Optional[Callable[[float], None]] = None,
        **kwargs
    ):
        self.colors = colors or THEME
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_change = on_change
        self._setup_ui(title, initial_value)

    def _setup_ui(self, title: str, initial_value: float) -> None:
        """Configura los elementos de la UI"""
        # Label del título
        self.title_label = UIFactory.create_label(
            self,
            text=title,
            font_size=12,
            text_color=self.colors['text']
        )
        self.title_label.grid(row=0, column=0, padx=15, pady=5, sticky="w")

        # Frame para el control
        self.control_frame = UIFactory.create_frame(
            self,
            transparent=True
        )
        self.control_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        # Botón decrementar
        self.decrease_btn = UIFactory.create_button(
            self.control_frame,
            text="-",
            width=30,
            command=self.decrease_value,
            fg_color=self.colors['primary']
        )
        self.decrease_btn.grid(row=0, column=0, padx=(0,5))

        # Slider
        self.slider = ctk.CTkSlider(
            self.control_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            progress_color=self.colors['primary'],
            button_color=self.colors['primary'],
            button_hover_color=UIFactory.apply_brightness(self.colors['primary'], 0.8)
        )
        self.slider.grid(row=0, column=1, padx=5, sticky="ew")
        self.slider.set(initial_value)
        self.slider.bind('<ButtonRelease-1>', self._on_slider_release)

        # Botón incrementar
        self.increase_btn = UIFactory.create_button(
            self.control_frame,
            text="+",
            width=30,
            command=self.increase_value,
            fg_color=self.colors['primary']
        )
        self.increase_btn.grid(row=0, column=2, padx=(5,0))

        # Label para el valor
        self.value_label = UIFactory.create_label(
            self.control_frame,
            text=f"{initial_value}%",
            font_size=12,
            text_color=self.colors['text'],
            width=50
        )
        self.value_label.grid(row=0, column=3, padx=10)

        # Configurar grid
        self.control_frame.grid_columnconfigure(1, weight=1)

    def decrease_value(self) -> None:
        """Decrementa el valor del control"""
        current = self.slider.get()
        new_value = max(0, current - 1)
        self._update_value(new_value)

    def increase_value(self) -> None:
        """Incrementa el valor del control"""
        current = self.slider.get()
        new_value = min(100, current + 1)
        self._update_value(new_value)

    def _update_value(self, value: float) -> None:
        """Actualiza el valor del control y notifica el cambio"""
        self.slider.set(value)
        self.value_label.configure(text=f"{value:.0f}%")
        if self.on_change:
            self.on_change(value)

    def _on_slider_release(self, event: Any) -> None:
        """Maneja el evento de soltar el slider"""
        value = self.slider.get()
        self._update_value(value)

    def get(self) -> float:
        """Obtiene el valor actual del control"""
        return self.slider.get()

class MonitorApp(ctk.CTk):
    """Aplicación principal de monitoreo del sistema"""
    def __init__(self):
        super().__init__()

        # Inicializar logger
        self.logger = get_logger()

        # Cargar configuración
        self.settings = Settings()
        self.colors = THEME

        # Loguear información inicial
        log_metrics({
            'type': 'startup',
            'system': {
                'os': f"{platform.system()} {platform.release()}",
                'python': sys.version,
                'config': self.settings.settings
            }
        })

        # Inicializar monitor de rendimiento
        self.performance_monitor = PerformanceMonitor(self.logger)

        # Configuración de la ventana y componentes
        self._setup_window()
        self._setup_containers()
        self._initialize_metrics()
        self._setup_notifications()

        # Mostrar vista inicial
        self.show_monitor_view()

        # Iniciar monitoreo
        self._start_monitoring()

    def _setup_window(self):
        """Configura la ventana principal"""
        self.title("System Monitor")
        self.geometry("1200x800")
        log_debug("Ventana principal configurada")

        self.configure(fg_color=self.colors['background'])
        ctk.set_appearance_mode("dark" if self.settings.settings['theme'] == 'dark' else "light")
        log_debug(f"Tema configurado: {self.settings.settings['theme']}")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind("<Configure>", self.on_resize)

    def _setup_containers(self) -> None:
        """Configura los contenedores principales"""
        # Crear menú
        self.create_menu()

        # Crear contenedor principal
        self.main_container = UIFactory.create_frame(
            self,
            transparent=True
        )
        self.main_container.pack(fill='both', expand=True, padx=20, pady=20)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        # Crear contenedor para las vistas
        self.view_container = UIFactory.create_frame(
            self.main_container,
            transparent=True
        )
        self.view_container.grid(row=0, column=0, sticky="nsew")
        self.view_container.grid_columnconfigure(0, weight=1)
        self.view_container.grid_rowconfigure(1, weight=1)

        # Inicializar vistas
        self.monitor_view = None
        self.settings_view = None
        self.current_view = None

    def _initialize_metrics(self) -> None:
        """Inicializa el almacenamiento de métricas"""
        self.max_data_points = self.settings.settings['max_data_points']
        self.cpu_metrics = OptimizedMetricStorage(self.max_data_points)
        self.ram_metrics = OptimizedMetricStorage(self.max_data_points)
        self.gpu_metrics = OptimizedMetricStorage(self.max_data_points)

        # Control de errores y rendimiento
        self.last_update = {
            'cpu': 0,
            'ram': 0,
            'gpu': 0
        }
        self.update_threshold = 0.5
        self.last_update_time = time.time()
        self.update_interval = max(0.5, self.settings.settings['update_interval'])
        self.skip_updates = 0

    def _setup_notifications(self) -> None:
        """Configura el sistema de notificaciones"""
        self.thresholds = self.settings.settings['thresholds']
        self.last_notifications = {
            'cpu': datetime.min,
            'ram': datetime.min,
            'gpu': datetime.min
        }
        self.notification_cooldown = {}
        self.grace_period = self.settings.settings['notification_grace_period']

    def _start_monitoring(self) -> None:
        """Inicia el monitoreo del sistema"""
        self.running = True
        self.thread = threading.Thread(target=self.update_stats, daemon=True)
        self.thread.start()
        self.logger.info("Monitor iniciado correctamente")

    def create_menu(self) -> None:
        """Crea la barra de menú"""
        toolbar = UIFactory.create_frame(
            self,
            height=40
        )
        toolbar.pack(fill='x', padx=0, pady=0)

        # Botones de navegación
        self.monitor_btn = UIFactory.create_button(
            toolbar,
            text="Monitor",
            command=self.show_monitor_view,
            width=100
        )
        self.monitor_btn.pack(side='left', padx=5, pady=5)

        self.settings_btn = UIFactory.create_button(
            toolbar,
            text="Settings",
            command=self.show_settings,
            width=100
        )
        self.settings_btn.pack(side='left', padx=5, pady=5)

    def show_monitor_view(self):
        """Muestra la vista del monitor"""
        if self.current_view == "monitor":
            return

        # Limpiar vista actual
        if self.settings_view:
            self.settings_view.pack_forget()

        # Crear vista de monitor si no existe
        if not self.monitor_view:
            self.monitor_view = UIFactory.create_frame(
                self.view_container,
                transparent=True
            )
            self.monitor_view.pack(fill='both', expand=True)

            # Grid de métricas
            metrics_grid = UIFactory.create_frame(
                self.monitor_view,
                transparent=True
            )
            metrics_grid.pack(fill='x', padx=10, pady=10)

            # Configurar grid
            for i in range(3):
                metrics_grid.grid_columnconfigure(i, weight=1, uniform="metric")
            metrics_grid.grid_rowconfigure(0, weight=1)

            # Tarjetas de métricas
            self.cpu_card = MetricCard(
                metrics_grid,
                "CPU Usage",
                tooltip_text="Porcentaje de uso del procesador\nMuestra la carga actual de la CPU",
                metric_color=self.colors['metrics']['cpu']
            )
            self.cpu_card.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

            self.ram_card = MetricCard(
                metrics_grid,
                "RAM Usage",
                tooltip_text="Porcentaje de uso de memoria RAM\nMuestra el consumo actual de memoria",
                metric_color=self.colors['metrics']['ram']
            )
            self.ram_card.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

            self.gpu_card = MetricCard(
                metrics_grid,
                "GPU Usage",
                tooltip_text="Porcentaje de uso de la GPU\nMuestra la carga actual de la tarjeta gráfica",
                metric_color=self.colors['metrics']['gpu']
            )
            self.gpu_card.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

            # Configurar gráfico
            if self.settings.settings['graph']['show']:
                self.setup_graph()

        self.current_view = "monitor"

        # Actualizar estado de botones
        self.monitor_btn.configure(fg_color=self.colors['primary'])
        self.settings_btn.configure(fg_color="transparent")

        self.logger.debug("Vista de monitor mostrada correctamente")

    def show_settings(self):
        try:
            self.logger.debug("Cambiando a vista de configuración")

            # Ocultar vista actual si existe
            if self.current_view:
                self.current_view.grid_remove()

            # Crear vista de configuración si no existe
            if not self.settings_view:
                self.settings_view = ctk.CTkFrame(self.view_container, fg_color="transparent")
                self.settings_view.grid(row=0, column=0, sticky="nsew")

                # Crear contenedor principal
                main_settings = ctk.CTkFrame(
                    self.settings_view,
                    fg_color=self.colors['card_bg']
                )
                main_settings.pack(fill='both', expand=True, padx=20, pady=20)

                # Título principal
                title = ctk.CTkLabel(
                    main_settings,
                    text="System Monitor Settings",
                    font=('Segoe UI', 24, 'bold'),
                    text_color=self.colors['text']
                )
                title.pack(pady=(20,30))

                # Contenedor para los paneles
                panels_container = ctk.CTkFrame(
                    main_settings,
                    fg_color="transparent"
                )
                panels_container.pack(fill='both', expand=True, padx=40, pady=(0,20))
                panels_container.grid_columnconfigure(0, weight=1)
                panels_container.grid_columnconfigure(1, weight=1)

                # Panel de personalización
                customization_panel = CustomizationPanel(
                    panels_container,
                    self.settings,
                    self.apply_settings,
                    fg_color="transparent"
                )
                customization_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

                # Panel de umbrales
                threshold_panel = self.create_threshold_panel(panels_container)
                threshold_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

            # Mostrar vista de configuración
            self.settings_view.grid()
            self.current_view = self.settings_view

            # Actualizar estado de botones
            self.monitor_btn.configure(fg_color="transparent")
            self.settings_btn.configure(fg_color=self.colors['primary'])

        except Exception as e:
            self.logger.error(f"Error al mostrar configuración: {str(e)}")
            messagebox.showerror("Error", "No se pudo abrir la configuración. Por favor, intente nuevamente.")

    def create_threshold_panel(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        # Título
        title = ctk.CTkLabel(
            frame,
            text="Alert Thresholds",
            font=('Segoe UI', 20, 'bold'),
            text_color=self.colors['text']
        )
        title.pack(pady=(0,20))

        # Contenedor principal
        main_container = ctk.CTkFrame(frame, fg_color=THEME['card_bg'])
        main_container.pack(fill='both', expand=True, padx=5, pady=5)

        # Descripción
        desc = ctk.CTkLabel(
            main_container,
            text="Set the threshold values for resource usage alerts",
            font=('Segoe UI', 12),
            text_color='gray'
        )
        desc.pack(pady=(15,20), padx=15)

        # Controles de umbral
        self.threshold_controls = {}
        resources = [
            ('CPU', 'cpu'),
            ('RAM', 'ram'),
            ('GPU', 'gpu')
        ]

        for display_name, resource in resources:
            # Frame para cada control
            control_frame = ctk.CTkFrame(main_container, fg_color='transparent')
            control_frame.pack(padx=15, pady=10, fill='x')

            # Título del recurso
            resource_title = ctk.CTkLabel(
                control_frame,
                text=f"{display_name} Threshold",
                font=('Segoe UI', 14, 'bold'),
                text_color=self.colors['text']
            )
            resource_title.pack(anchor='w', pady=(0,5))

            # Control
            control = ThresholdControl(
                control_frame,
                "",  # Título vacío porque ya lo pusimos arriba
                self.settings.settings['thresholds'].get(resource, 80),
                colors=self.colors
            )
            control.pack(fill='x')
            self.threshold_controls[resource] = control

            # Separador (excepto para el último)
            if resource != 'gpu':
                separator = ctk.CTkFrame(main_container, height=1, fg_color=THEME['primary'])
                separator.pack(fill='x', padx=15, pady=10)

        return frame

    def setup_graph(self):
        # Configurar estilo de matplotlib según el tema
        if self.settings.settings['theme'] == 'dark':
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        # Crear figura y ejes con un tamaño inicial ms pequeño y márgenes ajustados
        self.fig = plt.figure(figsize=(8, 3), facecolor=self.colors['card_bg'])
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.2)

        self.ax.set_facecolor(self.colors['card_bg'])

        # Configurar estilo del gráfico
        self.ax.grid(True, color=self.colors['text'], alpha=self.settings.settings['graph']['grid_alpha'], linestyle='--')
        self.ax.set_ylim(0, 100)

        # Configurar colores y etiquetas con líneas más visibles
        self.cpu_line, = self.ax.plot([], [],
            label='CPU',
            color=self.colors['metrics']['cpu'],
            linewidth=self.settings.settings['graph']['line_width'],
            marker='.',
            markersize=4,
            linestyle='-',
            solid_capstyle='round'
        )
        self.ram_line, = self.ax.plot([], [],
            label='RAM',
            color=self.colors['metrics']['ram'],
            linewidth=self.settings.settings['graph']['line_width'],
            marker='.',
            markersize=4,
            linestyle='-',
            solid_capstyle='round'
        )
        self.gpu_line, = self.ax.plot([], [],
            label='GPU',
            color=self.colors['metrics']['gpu'],
            linewidth=self.settings.settings['graph']['line_width'],
            marker='.',
            markersize=4,
            linestyle='-',
            solid_capstyle='round'
        )

        # Configurar leyenda con mejor visibilidad
        self.ax.legend(
            facecolor=self.colors['card_bg'],
            edgecolor=self.colors['text'],
            labelcolor=self.colors['text'],
            loc='upper left',
            bbox_to_anchor=(0.02, 0.98),
            framealpha=0.8,
            shadow=True
        )

        # Configurar etiquetas de ejes con mejor visibilidad
        self.ax.tick_params(colors=self.colors['text'], length=6, width=1, direction='out')
        for spine in self.ax.spines.values():
            spine.set_color(self.colors['text'])
            spine.set_linewidth(1)

        # Configurar el formateador de fechas para el eje X
        locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
        formatter = mdates.DateFormatter('%H:%M:%S')
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(formatter)

        # Rotar etiquetas para mejor legibilidad
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # Crear frame para el gráfico
        if hasattr(self, 'graph_frame'):
            self.graph_frame.destroy()

        self.graph_frame = ctk.CTkFrame(self.monitor_view, fg_color=self.colors['card_bg'], corner_radius=10)
        self.graph_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Crear canvas con mejor resolución
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.fig.set_dpi(100)  # Aumentar DPI para mejor calidad
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)

        # Configurar el manejo de eventos de redimensionamiento
        self._resize_timer = None

    def update_graph(self):
        """Actualización optimizada del gráfico con manejo de errores"""
        try:
            if not hasattr(self, 'canvas') or not self.settings.settings['graph']['show']:
                return

            timestamps = self.cpu_metrics.get_timestamps()
            if len(timestamps) < 2:
                return

            # Convertir timestamps a datetime de manera segura
            try:
                timestamps = [datetime.fromtimestamp(ts) for ts in timestamps]
            except (ValueError, TypeError) as e:
                self.logger.error(f"Error al convertir timestamps: {str(e)}")
                return

            cpu_data = self.cpu_metrics.get_values()
            ram_data = self.ram_metrics.get_values()
            gpu_data = self.gpu_metrics.get_values()

            # Validar datos antes de actualizar
            if len(timestamps) != len(cpu_data) or len(timestamps) != len(ram_data) or len(timestamps) != len(gpu_data):
                self.logger.error("Inconsistencia en la longitud de los datos")
                return

            # Asegurarse de que los datos no estén vacíos y sean válidos
            if not any(len(data) > 0 for data in [cpu_data, ram_data, gpu_data]):
                return

            # Validar que los datos estén en el rango correcto
            cpu_data = np.clip(cpu_data, 0, 100)
            ram_data = np.clip(ram_data, 0, 100)
            gpu_data = np.clip(gpu_data, 0, 100)

            # Actualizar datos de manera segura
            try:
                self.cpu_line.set_data(timestamps, cpu_data)
                self.ram_line.set_data(timestamps, ram_data)
                self.gpu_line.set_data(timestamps, gpu_data)

                # Ajustar límites del eje X con margen
                if timestamps:
                    x_min, x_max = timestamps[0], timestamps[-1]
                    margin = timedelta(seconds=5)
                    self.ax.set_xlim(x_min - margin, x_max + margin)

                # Ajustar límites del eje Y si es necesario
                y_max = max(max(cpu_data), max(ram_data), max(gpu_data))
                if y_max > 100:
                    self.ax.set_ylim(0, min(y_max * 1.1, 100))
                else:
                    self.ax.set_ylim(0, 100)

                # Actualizar vista solo si es necesario
                if not hasattr(self, '_last_draw') or time.time() - self._last_draw > 0.5:
                    self.canvas.draw_idle()
                    self._last_draw = time.time()
                    self.logger.debug("Gráfico actualizado correctamente")

            except Exception as e:
                self.logger.error(f"Error al actualizar datos del gráfico: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error en update_graph: {str(e)}", exc_info=True)

    def on_resize(self, event):
        # Solo procesar eventos de la ventana principal
        if event.widget == self:
            # Cancelar el timer anterior si existe
            if hasattr(self, '_resize_timer') and self._resize_timer is not None:
                self.after_cancel(self._resize_timer)

            # Crear un nuevo timer
            self._resize_timer = self.after(100, self._delayed_resize)

    def _delayed_resize(self):
        """Realizar el redimensionamiento después de un delay"""
        try:
            if hasattr(self, 'fig') and hasattr(self, 'graph_frame'):
                # Obtener el nuevo tamaño del contenedor
                width = self.graph_frame.winfo_width() / 100
                height = self.graph_frame.winfo_height() / 100

                # Actualizar el tamaño de la figura
                self.fig.set_size_inches(width, height)

                # Redibujar el canvas
                self.canvas.draw_idle()
        except Exception as e:
            self.logger.error(f"Error en _delayed_resize: {str(e)}", exc_info=True)
        finally:
            self._resize_timer = None

    def on_closing(self):
        """Limpieza y cierre optimizado"""
        self.logger.info("Cerrando aplicación")
        self.running = False
        self.performance_monitor.stop_profiling()
        self.quit()

    def apply_settings(self):
        """Aplica la configuración de manera segura"""
        try:
            # Aplicar nuevo tema
            self.colors = THEME
            self.configure(fg_color=self.colors['background'])

            # Actualizar modo de apariencia
            try:
                ctk.set_appearance_mode("dark" if self.settings.settings.get('theme') == 'dark' else "light")
            except Exception as e:
                self.logger.error(f"Error al cambiar el tema: {str(e)}")

            # Actualizar widgets si existen
            if hasattr(self, '_update_widget_colors'):
                self._update_widget_colors()

            # Actualizar gráfico si es necesario
            if hasattr(self, 'graph_frame'):
                try:
                    if self.settings.settings.get('graph', {}).get('show', True):
                        self.setup_graph()
                    else:
                        self.graph_frame.grid_remove()
                except Exception as e:
                    self.logger.error(f"Error al actualizar el gráfico: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error al aplicar configuración: {str(e)}", exc_info=True)
            messagebox.showerror("Error", "No se pudo aplicar la configuración. Se utilizará la configuración por defecto.")

    def _update_widget_colors(self):
        # Actualizar colores de las tarjetas
        for card, metric in [
            (self.cpu_card, 'cpu'),
            (self.ram_card, 'ram'),
            (self.gpu_card, 'gpu')
        ]:
            card.configure(fg_color=self.colors['card_bg'])
            card.progress.configure(
                progress_color=self.colors['metrics'][metric],
                fg_color=self.colors['background']
            )
            card.title_label.configure(text_color=self.colors['text'])
            card.value_label.configure(text_color=self.colors['text'])

    def get_gpu_usage(self):
        """Obtiene el uso de GPU de manera segura"""
        if not GPU_AVAILABLE:
            return 0, None

        try:
            gpus = GPUtil.getGPUs()
            if gpus and len(gpus) > 0:
                gpu = gpus[0]
                return gpu.load * 100 if gpu.load is not None else 0, getattr(gpu, 'temperature', None)
        except Exception as e:
            self.logger.error(f"Error al obtener información de GPU: {str(e)}", exc_info=True)
        return 0, None

    def get_disk_usage(self):
        try:
            if platform.system() == 'Windows':
                disk = psutil.disk_usage('C:\\')  # Usar la unidad C: en Windows
            else:
                disk = psutil.disk_usage('/')  # Usar root en sistemas Unix
            return disk.percent
        except Exception as e:
            self.logger.error(f"Error al obtener uso de disco: {str(e)}", exc_info=True)
            return 0

    def check_thresholds(self, cpu, ram, gpu):
        try:
            if cpu > self.thresholds['cpu'] and self.should_notify('cpu'):
                self.show_notification("CPU Alert", f"CPU uso alto: {cpu:.1f}%")
            if ram > self.thresholds['ram'] and self.should_notify('ram'):
                self.show_notification("RAM Alert", f"RAM uso alto: {ram:.1f}%")
            if gpu > self.thresholds['gpu'] and self.should_notify('gpu'):
                self.show_notification("GPU Alert", f"GPU uso alto: {gpu:.1f}%")
        except Exception as e:
            self.logger.error(f"Error al verificar umbrales: {str(e)}", exc_info=True)

    def show_notification(self, title, message):
        try:
            notification.notify(
                title=title,
                message=message,
                app_icon=None,
                timeout=10,
            )
            self.logger.info(f"Notificación enviada: {title} - {message}")
        except Exception as e:
            self.logger.error(f"Error al mostrar notificación: {str(e)}", exc_info=True)

    def update_threshold(self, resource, value):
        try:
            self.thresholds[resource] = value
            self.logger.info(f"Umbral actualizado - {resource}: {value}")
        except Exception as e:
            self.logger.error(f"Error al actualizar umbral: {str(e)}", exc_info=True)

    def should_notify(self, resource):
        """Control mejorado de notificaciones"""
        now = datetime.now()
        if resource not in self.notification_cooldown:
            self.notification_cooldown[resource] = 0

        # Verificar el tiempo transcurrido desde la última notificación
        if (now - self.last_notifications[resource]).total_seconds() > self.grace_period:
            # Verificar el cooldown dinámico
            current_time = time.time()
            if current_time - self.notification_cooldown[resource] > self.grace_period:
                self.last_notifications[resource] = now
                self.notification_cooldown[resource] = current_time
                return True
        return False

    @performance_monitor
    def update_stats(self):
        """Actualización optimizada de estadísticas"""
        last_metrics_update = 0
        metrics_update_interval = self.update_interval / 2
        error_count = 0
        max_errors = 3
        min_update_interval = 0.1
        max_update_interval = 2.0
        last_log_time = 0
        log_interval = 60  # Loguear métricas cada 60 segundos

        self.logger.info("Iniciando monitoreo de recursos")

        log_debug("Iniciando bucle de monitoreo")
        while self.running:
            try:
                current_time = time.time()
                elapsed = current_time - self.last_update_time

                # Logging periódico
                if current_time - last_log_time >= log_interval:
                    log_debug(f"Intervalo actual de actualización: {self.update_interval:.2f}s")
                    metrics = self._get_system_metrics()
                    if metrics:
                        cpu_percent, ram_percent, gpu_percent = metrics
                        log_metrics({
                            'timestamp': datetime.now().isoformat(),
                            'metrics': {
                                'cpu': {
                                    'percent': cpu_percent,
                                    'frequency': self._get_cpu_frequency()
                                },
                                'ram': {
                                    'percent': ram_percent,
                                    'used_gb': psutil.virtual_memory().used / (1024**3),
                                    'total_gb': psutil.virtual_memory().total / (1024**3)
                                },
                                'gpu': {
                                    'percent': gpu_percent,
                                    'info': self._get_gpu_info()
                                }
                            }
                        })
                        log_debug(f"Métricas actualizadas - CPU: {cpu_percent:.1f}%, RAM: {ram_percent:.1f}%, GPU: {gpu_percent:.1f}%")

                        # Logging de rendimiento
                        log_performance({
                            'update_interval': self.update_interval,
                            'elapsed_time': elapsed,
                            'error_count': error_count,
                            'metrics_count': len(self.cpu_metrics.get_values())
                        })
                    else:
                        log_warning("No se pudieron obtener métricas del sistema")

                    last_log_time = current_time

                # Control de frecuencia de actualización
                if elapsed < self.update_interval * 0.9:
                    time.sleep(max(min_update_interval, self.update_interval - elapsed))
                    continue

                # Actualización de métricas
                metrics = self._get_system_metrics()
                if metrics:
                    cpu_percent, ram_percent, gpu_percent = metrics
                    timestamp = current_time

                    # Almacenar métricas de manera segura
                    try:
                        with self._get_metrics_lock():
                            self.cpu_metrics.add_metric(cpu_percent, timestamp)
                            self.ram_metrics.add_metric(ram_percent, timestamp)
                            self.gpu_metrics.add_metric(gpu_percent, timestamp)
                            log_debug(f"Métricas almacenadas - CPU: {cpu_percent:.1f}%, RAM: {ram_percent:.1f}%, GPU: {gpu_percent:.1f}%")

                        # Actualizar UI y gráfico
                        self.after(0, lambda: self.update_ui(cpu_percent, ram_percent, gpu_percent))
                        self.after(0, self.update_graph)

                    except Exception as e:
                        self.logger.error(f"Error al almacenar métricas: {str(e)}")
                        error_count += 1

                    self.last_update_time = current_time

            except Exception as e:
                error_count += 1
                self.logger.error(f"Error en update_stats: {str(e)}", exc_info=True)
                if error_count >= max_errors:
                    self.logger.error("Demasiados errores consecutivos, ajustando intervalo")
                    self.update_interval = min(max_update_interval, self.update_interval * 1.5)
                    error_count = 0
                time.sleep(self.update_interval)

    def _get_metrics_lock(self) -> Lock:
        """Obtiene el lock para actualización de métricas"""
        if not hasattr(self, '_metrics_lock'):
            self._metrics_lock = Lock()
        return self._metrics_lock

    def _get_system_metrics(self) -> Optional[tuple[float, float, float]]:
        """Obtiene las métricas del sistema de manera segura"""
        try:
            # Obtener CPU con timeout
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Obtener RAM
            ram = psutil.virtual_memory()
            ram_percent = ram.percent

            # Obtener GPU de manera segura
            gpu_percent, _ = self.get_gpu_usage()

            # Validar valores
            cpu_percent = max(0, min(100, float(cpu_percent)))
            ram_percent = max(0, min(100, float(ram_percent)))
            gpu_percent = max(0, min(100, float(gpu_percent)))

            return cpu_percent, ram_percent, gpu_percent

        except Exception as e:
            self.logger.error(f"Error al obtener métricas del sistema: {str(e)}", exc_info=True)
            return None

    def _log_system_details(self):
        """Registra detalles adicionales del sistema"""
        try:
            # CPU
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                self.logger.debug(f"CPU Frecuencia - Current: {cpu_freq.current:.1f}MHz, "
                                f"Min: {cpu_freq.min:.1f}MHz, Max: {cpu_freq.max:.1f}MHz")

            # Memoria
            mem = psutil.virtual_memory()
            self.logger.debug(
                f"Memoria - Total: {mem.total/1024**3:.1f}GB, "
                f"Disponible: {mem.available/1024**3:.1f}GB, "
                f"Usado: {(mem.total - mem.available)/1024**3:.1f}GB"
            )

            # Disco
            disk = psutil.disk_usage('/')
            self.logger.debug(
                f"Disco - Total: {disk.total/1024**3:.1f}GB, "
                f"Usado: {disk.used/1024**3:.1f}GB, "
                f"Libre: {disk.free/1024**3:.1f}GB"
            )

            # GPU si está disponible
            if GPU_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    for i, gpu in enumerate(gpus):
                        self.logger.debug(
                            f"GPU {i} - {gpu.name}: Memoria Total: {gpu.memoryTotal}MB, "
                            f"Usada: {gpu.memoryUsed}MB, Temp: {getattr(gpu, 'temperature', 'N/A')}°C"
                        )
                except Exception as e:
                    self.logger.error(f"Error al obtener información detallada de GPU: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error al registrar detalles del sistema: {str(e)}")

    @performance_monitor
    def update_ui(self, cpu_percent: float, ram_percent: float, gpu_percent: float) -> None:
        """Actualización optimizada de la interfaz de usuario"""
        try:
            # Actualizar CPU
            try:
                freq = psutil.cpu_freq()
                freq_info = f"Frecuencia: {freq.current:.0f}MHz" if freq else ""
                self.cpu_card.update(cpu_percent, info_text=freq_info)
                log_debug(f"UI CPU actualizada: {cpu_percent:.1f}% {freq_info}")
            except Exception as e:
                log_error(f"Error al actualizar UI CPU: {str(e)}")
                self.cpu_card.update(cpu_percent)

            # Actualizar RAM
            try:
                ram = psutil.virtual_memory()
                total_gb = ram.total / (1024**3)
                used_gb = (ram.total - ram.available) / (1024**3)
                info_text = f"Usado: {used_gb:.1f}GB de {total_gb:.1f}GB"
                self.ram_card.update(ram_percent, info_text=info_text)
                log_debug(f"UI RAM actualizada: {ram_percent:.1f}% ({info_text})")
            except Exception as e:
                log_error(f"Error al actualizar UI RAM: {str(e)}")
                self.ram_card.update(ram_percent)

            # Actualizar GPU
            try:
                if GPU_AVAILABLE:
                    gpu_info = self._get_gpu_info()
                    if gpu_info:
                        info_text = (f"Memoria: {gpu_info['memory_used']:.0f}MB/"
                                   f"{gpu_info['memory_total']:.0f}MB")
                        if gpu_info['temperature']:
                            info_text += f" | Temp: {gpu_info['temperature']}°C"
                        self.gpu_card.update(gpu_percent, info_text=info_text)
                        log_debug(f"UI GPU actualizada: {gpu_percent:.1f}% ({info_text})")
                    else:
                        self.gpu_card.update(0, info_text="GPU no disponible")
                        log_debug("GPU no disponible")
                else:
                    self.gpu_card.update(0, info_text="GPUtil no instalado")
                    log_debug("GPUtil no instalado")
            except Exception as e:
                log_error(f"Error al actualizar UI GPU: {str(e)}")
                self.gpu_card.update(0, info_text="Error al leer GPU")

            # Actualizar gráfico si está visible y hay cambios significativos
            if (self.settings.settings['graph']['show'] and
                hasattr(self, 'graph_frame') and
                any(abs(x - y) > 0.5 for x, y in [
                    (cpu_percent, self.cpu_metrics.get_values()[-1] if self.cpu_metrics.get_values().size > 0 else 0),
                    (ram_percent, self.ram_metrics.get_values()[-1] if self.ram_metrics.get_values().size > 0 else 0),
                    (gpu_percent, self.gpu_metrics.get_values()[-1] if self.gpu_metrics.get_values().size > 0 else 0)
                ])):
                self.update_graph()

            # Verificar umbrales
            self.check_thresholds(cpu_percent, ram_percent, gpu_percent)

        except Exception as e:
            log_error("Error general en actualización de UI", exc_info=True)

    def check_thresholds(self, cpu: float, ram: float, gpu: float) -> None:
        """Verificación optimizada de umbrales"""
        try:
            current_time = time.time()
            for resource, value in [('cpu', cpu), ('ram', ram), ('gpu', gpu)]:
                if (value > self.thresholds[resource] and
                    current_time - self.notification_cooldown.get(resource, 0) > self.grace_period):
                    message = f"{resource.upper()} uso alto: {value:.1f}%"
                    self.show_notification(f"{resource.upper()} Alert", message)
                    log_warning(f"Umbral excedido - {message}")
                    self.notification_cooldown[resource] = current_time
        except Exception as e:
            log_error(f"Error al verificar umbrales: {str(e)}", exc_info=True)

    def show_notification(self, title: str, message: str) -> None:
        """Muestra notificaciones de manera segura"""
        try:
            if self.settings.settings['show_notifications']:
                notification.notify(
                    title=title,
                    message=message,
                    app_icon=None,
                    timeout=10,
                )
                log_debug(f"Notificación enviada: {title} - {message}")
        except Exception as e:
            log_error(f"Error al mostrar notificación: {str(e)}", exc_info=True)

    def _get_cpu_frequency(self):
        try:
            freq = psutil.cpu_freq()
            if freq:
                return {
                    'current': freq.current,
                    'min': freq.min,
                    'max': freq.max
                }
        except Exception as e:
            log_error(f"Error al obtener frecuencia de CPU: {str(e)}")
        return None

    def _get_gpu_info(self):
        try:
            if GPU_AVAILABLE:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    return {
                        'name': gpu.name,
                        'memory_used': gpu.memoryUsed,
                        'memory_total': gpu.memoryTotal,
                        'temperature': getattr(gpu, 'temperature', None)
                    }
        except Exception as e:
            log_error(f"Error al obtener información de GPU: {str(e)}")
        return None

if __name__ == "__main__":
    app = MonitorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
