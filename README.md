# Resource Alert 🚀

_[Lee esto en español](README.es.md)_

Modern system resource monitor with graphical interface and alert system.

![Resource Alert Preview](docs/preview.png)

## ✨ Features

- 📊 **Real-time monitoring**:
  - CPU Usage
  - RAM Usage
  - Disk Usage
  - CPU Temperature (when sensors are available)
- 📈 **Historical graph** of CPU and RAM
- 🎨 **Modern dark interface**
- 🎚️ **Customizable thresholds** using sliders
- 🔔 **Notification system** with grace period
- 📊 **Visualization through cards and progress bars**
- 📝 **Complete logging system**

## 🛠️ Prerequisites

- Python 3.7 or higher
- Operating system: Windows, Linux or macOS

## 🚀 Installation

1. Clone the repository:

```bash
git clone https://github.com/TU_USUARIO/Resource_Alert.git
cd Resource_Alert
```

2. Create and activate virtual environment:

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## 💻 Usage

1. Run the application:

```bash
python monitor.py
```

2. The application will display:

   - Cards with real-time metrics
   - Historical graph of CPU and RAM
   - Sliders to adjust thresholds

3. Notifications will be displayed when:
   - Thresholds are exceeded
   - Grace period has passed (5 minutes by default)

## ⚙️ Configuration

Thresholds can be adjusted in real-time using sliders:

- Default values:
  - CPU: 80%
  - RAM: 80%
  - Disk: 80%
  - Temperature: 70°C

## 📝 Logs

Logs are saved in:

- `logs/system_monitor.log`
- Automatic rotation when reaching 5MB
- Last 5 log files are retained

## 🤝 Contributing

1. Fork the project
2. Create a branch for your feature (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add: new feature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

## 👤 Author

Your Name

- GitHub: [@tu_usuario](https://github.com/tu_usuario)

## ⭐️ Show your support

Give this project a star if you found it useful!
