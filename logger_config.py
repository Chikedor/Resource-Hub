import logging
import os
import glob
import platform
import sys
from datetime import datetime
import json
import psutil
try:
    import GPUtil
except ImportError:
    GPUtil = None

# Import colorama for cross-platform color support
import colorama
colorama.init()

class CustomFormatter(logging.Formatter):
    """Formateador personalizado que incluye colores en la consola"""
    COLORS = {
        'DEBUG': colorama.Fore.CYAN,
        'INFO': colorama.Fore.GREEN,
        'WARNING': colorama.Fore.YELLOW,
        'ERROR': colorama.Fore.RED,
        'CRITICAL': colorama.Fore.MAGENTA
    }
    RESET = colorama.Style.RESET_ALL

    def format(self, record):
        # Añadir timestamp al mensaje si no existe
        if not hasattr(record, 'timestamp'):
            record.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Formatear mensaje según el tipo
        if hasattr(record, 'metrics'):
            record.msg = self._format_metrics(record.metrics)
        elif hasattr(record, 'system_info'):
            record.msg = self._format_system_info(record.system_info)
        elif hasattr(record, 'performance'):
            record.msg = self._format_performance(record.performance)

        # Añadir colores solo para la consola
        if hasattr(self, 'is_console'):
            color = self.COLORS.get(record.levelname, self.RESET)
            record.msg = f"{color}{record.msg}{self.RESET}"

        return super().format(record)

    def _format_metrics(self, metrics):
        """Formatea las métricas de manera consistente"""
        if 'type' in metrics and metrics['type'] == 'startup':
            return f"Inicio del sistema - {json.dumps(metrics['system'], indent=2)}"
        return f"Métricas del sistema:\n{json.dumps(metrics, indent=2)}"

    def _format_system_info(self, info):
        """Formatea la información del sistema de manera consistente"""
        return f"Sistema: {json.dumps(info, indent=2)}"

    def _format_performance(self, perf):
        """Formatea la información de rendimiento de manera consistente"""
        return f"Rendimiento del sistema:\n{json.dumps(perf, indent=2)}"

class SystemMonitorLogger:
    _instance = None
    _logger = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app_name="SystemMonitor"):
        if SystemMonitorLogger._logger is not None:
            return

        self.app_name = app_name
        self.log_dir = "logs"
        self.max_sessions = 10  # Mantener logs de las últimas 10 sesiones
        self._setup_logging()

    def _setup_logging(self):
        """Configura el sistema de logging"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self.cleanup_old_logs()

        # Crear logger principal
        logger = logging.getLogger(self.app_name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        # Timestamp para el nombre del archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(self.log_dir, f'{self.app_name}_{timestamp}.log')

        # Formatters
        file_formatter = CustomFormatter(
            '%(timestamp)s [%(levelname)s] %(module)s:%(lineno)d - %(message)s'
        )
        console_formatter = CustomFormatter(
            '%(timestamp)s [%(levelname)s] %(message)s'
        )
        console_formatter.is_console = True

        # File Handler (un archivo por sesión)
        file_handler = logging.FileHandler(
            log_file,
            mode='w',
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console Handler - Cambiar a DEBUG también para desarrollo
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        console_handler.is_console = True
        logger.addHandler(console_handler)

        # Log inicial con información del sistema
        system_info = self.get_system_info()
        logger.info("=== Iniciando nueva sesión de monitoreo ===")
        logger.info(f"Archivo de log: {log_file}")

        # Usar un LogRecord personalizado para la información del sistema
        record = logging.LogRecord(
            name=logger.name,
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='',
            args=(),
            exc_info=None
        )
        record.system_info = system_info
        logger.handle(record)

        SystemMonitorLogger._logger = logger

    def get_logger(self):
        """Retorna el logger configurado"""
        return SystemMonitorLogger._logger

    def log_metrics(self, metrics: dict):
        """Método específico para loguear métricas"""
        if self._logger:
            record = logging.LogRecord(
                name=self._logger.name,
                level=logging.INFO,
                pathname='',
                lineno=0,
                msg='',
                args=(),
                exc_info=None
            )
            record.metrics = metrics
            self._logger.handle(record)

    def get_system_info(self):
        """Recopila información detallada del sistema"""
        info = {
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor()
            },
            "python_version": sys.version,
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available
            },
            "disk": {},
            "gpu": []
        }

        # Información de discos
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                info["disk"][partition.mountpoint] = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free
                }
            except Exception:
                pass

        # Información de GPU
        if GPUtil:
            try:
                gpus = GPUtil.getGPUs()
                for gpu in gpus:
                    info["gpu"].append({
                        "name": gpu.name,
                        "memory_total": gpu.memoryTotal,
                        "driver": gpu.driver,
                        "temperature": getattr(gpu, 'temperature', 'N/A')
                    })
            except Exception:
                info["gpu"].append({"message": "Error al obtener información de GPU"})
        else:
            info["gpu"].append({"message": "GPUtil no está instalado"})

        return info

    def cleanup_old_logs(self):
        """Limpia logs antiguos manteniendo solo las sesiones más recientes"""
        log_files = glob.glob(os.path.join(self.log_dir, f'{self.app_name}_*.log'))
        if len(log_files) > self.max_sessions:
            sorted_files = sorted(log_files, key=os.path.getctime)
            for old_file in sorted_files[:-self.max_sessions]:
                try:
                    os.remove(old_file)
                except Exception as e:
                    print(f"Error eliminando log antiguo {old_file}: {e}")

def get_logger(app_name="SystemMonitor"):
    """Función helper para obtener el logger"""
    logger_instance = SystemMonitorLogger(app_name)
    return logger_instance.get_logger()

def log_metrics(metrics: dict, app_name="SystemMonitor"):
    """Función helper para loguear métricas"""
    logger_instance = SystemMonitorLogger(app_name)
    logger_instance.log_metrics(metrics)

def log_performance(perf: dict, app_name="SystemMonitor"):
    """Función helper para loguear información de rendimiento"""
    logger_instance = SystemMonitorLogger(app_name)
    if logger_instance._logger:
        record = logging.LogRecord(
            name=logger_instance._logger.name,
            level=logging.DEBUG,
            pathname='',
            lineno=0,
            msg='',
            args=(),
            exc_info=None
        )
        record.performance = perf
        logger_instance._logger.handle(record)

def log_error(error: str, exc_info=None, app_name="SystemMonitor"):
    """Función helper para loguear errores de manera consistente"""
    logger = get_logger(app_name)
    logger.error(error, exc_info=exc_info)

def log_warning(msg: str, app_name="SystemMonitor"):
    """Función helper para loguear advertencias de manera consistente"""
    logger = get_logger(app_name)
    logger.warning(msg)

def log_debug(msg: str, app_name="SystemMonitor"):
    """Función helper para loguear información de depuración"""
    logger = get_logger(app_name)
    logger.debug(msg)
