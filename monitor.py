import customtkinter as ctk
import psutil
import threading
from datetime import datetime, timedelta
from plyer import notification
import platform
import logging
import os
from logging.handlers import RotatingFileHandler
import sys
from collections import deque
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

# Configuración de colores y tema
COLORS = {
    'primary': '#2196f3',
    'background': '#1e1e1e',
    'card_bg': '#2d2d2d',
    'text': '#ffffff',
    'danger': '#f44336',
    'success': '#4caf50'
}

# Configuración de matplotlib para modo oscuro
plt.style.use('dark_background')

# Configuración del sistema de logging
def setup_logging():
    # Crear directorio de logs si no existe
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configurar el logger
    logger = logging.getLogger('SystemMonitor')
    logger.setLevel(logging.DEBUG)

    # Crear formato para los logs
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Handler para archivo con rotación
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'system_monitor.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Limpiar handlers existentes
    logger.handlers.clear()

    # Añadir handlers al logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title, **kwargs):
        super().__init__(master, fg_color=COLORS['card_bg'], corner_radius=10, **kwargs)

        # Título
        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            text_color=COLORS['text'],
            font=('Segoe UI', 14)
        )
        self.title_label.grid(row=0, column=0, padx=15, pady=(15,5), sticky="w")

        # Valor
        self.value_label = ctk.CTkLabel(
            self,
            text="0%",
            text_color=COLORS['text'],
            font=('Segoe UI', 32, 'bold')
        )
        self.value_label.grid(row=1, column=0, padx=15, pady=5, sticky="w")

        # Barra de progreso
        self.progress = ctk.CTkProgressBar(
            self,
            progress_color=COLORS['primary'],
            height=8,
            corner_radius=4
        )
        self.progress.grid(row=2, column=0, padx=15, pady=(5,15), sticky="ew")
        self.progress.set(0)

        # Configurar grid
        self.grid_columnconfigure(0, weight=1)

        # Efecto hover
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)

    def on_enter(self, event):
        self.configure(fg_color=self.apply_brightness(COLORS['card_bg'], 1.1))

    def on_leave(self, event):
        self.configure(fg_color=COLORS['card_bg'])

    def apply_brightness(self, hex_color, factor):
        # Convertir hex a RGB
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        # Aplicar factor de brillo
        new_rgb = tuple(min(255, int(c * factor)) for c in rgb)
        # Convertir de vuelta a hex
        return '#{:02x}{:02x}{:02x}'.format(*new_rgb)

    def update(self, value, unit="%"):
        self.value_label.configure(text=f"{value:.1f}{unit}")
        self.progress.set(value/100.0 if unit == "%" else value/70.0)  # 70°C max para temperatura

class MonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Inicializar logger
        self.logger = setup_logging()
        self.logger.info("Iniciando System Monitor")

        # Configuración de la ventana
        self.title("System Monitor")
        self.geometry("1200x800")
        self.configure(fg_color=COLORS['background'])
        ctk.set_appearance_mode("dark")

        # Determinar la unidad principal del sistema
        if platform.system() == 'Windows':
            self.system_drive = os.getenv('SystemDrive', 'C:')
        else:
            self.system_drive = '/'

        self.logger.info(f"Unidad del sistema detectada: {self.system_drive}")

        # Histórico de datos
        self.max_data_points = 60  # 1 minuto de datos
        self.cpu_history = deque(maxlen=self.max_data_points)
        self.ram_history = deque(maxlen=self.max_data_points)
        self.time_history = deque(maxlen=self.max_data_points)

        # Umbrales predeterminados
        self.thresholds = {
            'cpu': 80,
            'ram': 80,
            'disk': 80,
            'temp': 70
        }

        # Control de notificaciones
        self.last_notifications = {
            'cpu': datetime.min,
            'ram': datetime.min,
            'disk': datetime.min,
            'temp': datetime.min
        }
        self.grace_period = 300

        # Crear interfaz
        self.create_widgets()
        self.create_threshold_controls()
        self.setup_graph()

        # Iniciar monitoreo
        self.running = True
        self.thread = threading.Thread(target=self.update_stats, daemon=True)
        self.thread.start()
        self.logger.info("Monitor iniciado correctamente")

    def setup_graph(self):
        # Crear figura y ejes
        self.fig, self.ax = plt.subplots(figsize=(12, 4), facecolor=COLORS['card_bg'])
        self.ax.set_facecolor(COLORS['card_bg'])

        # Configurar estilo del gráfico
        self.ax.grid(True, color='gray', alpha=0.2)
        self.ax.set_ylim(0, 100)

        # Configurar colores y etiquetas
        self.cpu_line, = self.ax.plot([], [], label='CPU', color=COLORS['primary'], linewidth=2)
        self.ram_line, = self.ax.plot([], [], label='RAM', color=COLORS['success'], linewidth=2)

        # Configurar leyenda
        self.ax.legend(facecolor=COLORS['card_bg'], edgecolor=COLORS['card_bg'])

        # Crear frame para el gráfico
        self.graph_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
        self.graph_frame.grid(row=2, column=0, padx=20, pady=20, sticky="nsew")

        # Crear canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)

        # Ajustar layout
        self.grid_rowconfigure(2, weight=2)

    def update_graph(self):
        # Actualizar datos
        self.cpu_line.set_data(range(len(self.cpu_history)), list(self.cpu_history))
        self.ram_line.set_data(range(len(self.ram_history)), list(self.ram_history))

        # Ajustar límites del eje x
        self.ax.set_xlim(0, self.max_data_points)

        # Redibujar
        self.canvas.draw_idle()

    def create_widgets(self):
        try:
            # Contenedor principal con padding
            main_container = ctk.CTkFrame(self, fg_color="transparent")
            main_container.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
            main_container.grid_columnconfigure(0, weight=1)

            # Grid de métricas
            metrics_grid = ctk.CTkFrame(main_container, fg_color="transparent")
            metrics_grid.grid(row=0, column=0, sticky="ew")
            metrics_grid.grid_columnconfigure((0,1,2,3), weight=1)

            # Tarjetas de métricas
            self.cpu_card = MetricCard(metrics_grid, "CPU Usage")
            self.cpu_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

            self.ram_card = MetricCard(metrics_grid, "RAM Usage")
            self.ram_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

            self.disk_card = MetricCard(metrics_grid, f"Disk Usage ({self.system_drive})")
            self.disk_card.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")

            self.temp_card = MetricCard(metrics_grid, "Temperature")
            self.temp_card.grid(row=0, column=3, padx=10, pady=10, sticky="nsew")

            # Configurar grid principal
            self.grid_columnconfigure(0, weight=1)

            self.logger.debug("Widgets creados correctamente")
        except Exception as e:
            self.logger.error(f"Error al crear widgets: {str(e)}", exc_info=True)
            raise

    def create_threshold_controls(self):
        try:
            # Frame para controles con estilo de tarjeta
            threshold_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=10)
            threshold_frame.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

            # Título del frame
            title_label = ctk.CTkLabel(
                threshold_frame,
                text="Alert Thresholds",
                font=('Segoe UI', 16, 'bold'),
                text_color=COLORS['text']
            )
            title_label.grid(row=0, column=0, columnspan=2, padx=15, pady=15, sticky="w")

            # Sliders con estilo moderno
            for i, (resource, value) in enumerate(self.thresholds.items(), start=1):
                label = ctk.CTkLabel(
                    threshold_frame,
                    text=f"{resource.upper()}:",
                    font=('Segoe UI', 12),
                    text_color=COLORS['text']
                )
                label.grid(row=i, column=0, padx=15, pady=5, sticky="w")

                slider = ctk.CTkSlider(
                    threshold_frame,
                    from_=0,
                    to=100,
                    number_of_steps=100,
                    progress_color=COLORS['primary'],
                    button_color=COLORS['primary'],
                    button_hover_color=self.apply_brightness(COLORS['primary'], 1.1)
                )
                slider.grid(row=i, column=1, padx=15, pady=5, sticky="ew")
                slider.set(value)
                slider.bind('<ButtonRelease-1>',
                           lambda e, r=resource: self.update_threshold(r, e.widget.get()))

            threshold_frame.grid_columnconfigure(1, weight=1)
            self.logger.debug("Controles de umbral creados correctamente")
        except Exception as e:
            self.logger.error(f"Error al crear controles de umbral: {str(e)}", exc_info=True)
            raise

    def apply_brightness(self, hex_color, factor):
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        new_rgb = tuple(min(255, int(c * factor)) for c in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*new_rgb)

    def update_stats(self):
        while self.running:
            try:
                # CPU
                cpu_percent = psutil.cpu_percent()
                self.cpu_card.update(cpu_percent)
                self.cpu_history.append(cpu_percent)
                self.logger.debug(f"CPU: {cpu_percent:.1f}%")

                # RAM
                ram = psutil.virtual_memory()
                ram_percent = ram.percent
                self.ram_card.update(ram_percent)
                self.ram_history.append(ram_percent)
                self.logger.debug(f"RAM: {ram_percent:.1f}%")

                # Actualizar gráfico
                self.update_graph()

                # Disk
                try:
                    disk = psutil.disk_usage(self.system_drive)
                    disk_percent = disk.percent
                    self.disk_card.update(disk_percent)
                    self.logger.debug(f"Disk ({self.system_drive}): {disk_percent:.1f}%")
                except Exception as disk_error:
                    self.logger.error(f"Error al obtener uso del disco: {str(disk_error)}", exc_info=True)
                    self.disk_card.update(0)

                # Temperature
                temp = self.get_cpu_temperature()
                if temp is not None:
                    self.temp_card.update(temp, "°C")
                    self.logger.debug(f"Temp: {temp:.1f}°C")
                else:
                    self.temp_card.update(0, "°C")
                    self.logger.debug("Temperatura no disponible")

                # Check thresholds
                self.check_thresholds(cpu_percent, ram_percent, disk_percent if 'disk_percent' in locals() else 0, temp)

            except Exception as e:
                self.logger.error(f"Error al actualizar estadísticas: {str(e)}", exc_info=True)

            time.sleep(1)  # Actualizar cada segundo

    def get_cpu_temperature(self):
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                self.logger.debug("No se encontraron sensores de temperatura")
                return None

            for name, entries in temps.items():
                if entries:
                    for entry in entries:
                        if 'cpu' in entry.label.lower() or 'core' in entry.label.lower():
                            self.logger.debug(f"Temperatura CPU encontrada: {entry.current}°C")
                            return entry.current
                    self.logger.debug(f"Usando primera temperatura disponible: {entries[0].current}°C")
                    return entries[0].current
            return None
        except Exception as e:
            self.logger.error(f"Error al obtener temperatura: {str(e)}", exc_info=True)
            return None

    def should_notify(self, resource):
        now = datetime.now()
        if (now - self.last_notifications[resource]).total_seconds() > self.grace_period:
            self.last_notifications[resource] = now
            return True
        return False

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

    def check_thresholds(self, cpu, ram, disk, temp):
        try:
            if cpu > self.thresholds['cpu'] and self.should_notify('cpu'):
                self.show_notification("CPU Alert", f"CPU uso alto: {cpu:.1f}%")
            if ram > self.thresholds['ram'] and self.should_notify('ram'):
                self.show_notification("RAM Alert", f"RAM uso alto: {ram:.1f}%")
            if disk > self.thresholds['disk'] and self.should_notify('disk'):
                self.show_notification("Disk Alert", f"Disco uso alto: {disk:.1f}%")
            if temp and temp > self.thresholds['temp'] and self.should_notify('temp'):
                self.show_notification("Temp Alert", f"Temperatura alta: {temp:.1f}°C")
        except Exception as e:
            self.logger.error(f"Error al verificar umbrales: {str(e)}", exc_info=True)

    def update_threshold(self, resource, value):
        try:
            self.thresholds[resource] = value
            self.logger.info(f"Umbral actualizado - {resource}: {value}")
        except Exception as e:
            self.logger.error(f"Error al actualizar umbral: {str(e)}", exc_info=True)

    def on_closing(self):
        self.logger.info("Cerrando aplicación")
        self.running = False
        self.quit()

if __name__ == "__main__":
    app = MonitorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
