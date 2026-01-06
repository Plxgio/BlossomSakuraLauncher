import sys
import os
import json
import hashlib
import zipfile
import tempfile
import urllib.request
import urllib.error
import threading
import shutil
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import webbrowser

# ============================================
# CONFIGURACIÓN DEL SISTEMA DE ACTUALIZACIÓN
# ============================================
VERSION = "0.0.7"
UPDATE_SERVER = "https://raw.githubusercontent.com/Plxgio/SakuraLauncher/master/updates/"
VERSION_FILE = "launcher_version.json"
UPDATE_FILE = "launcher_update.zip"
CHECK_INTERVAL = 3600  # Segundos entre verificaciones (1 hora)

# ============================================
# CLASE PARA MANEJAR ACTUALIZACIONES
# ============================================

class UpdateManager(QObject):
    """Manejador de actualizaciones automáticas"""
    
    update_available = pyqtSignal(str, str)  # nueva_versión, changelog
    update_progress = pyqtSignal(int)  # progreso 0-100
    update_finished = pyqtSignal(bool, str)  # éxito, mensaje
    status_changed = pyqtSignal(str)  # estado actual
    
    def __init__(self):
        super().__init__()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(self.script_dir, "temp_updates")
        self.backup_dir = os.path.join(self.script_dir, "backup")
        self.last_check_file = os.path.join(self.script_dir, "last_check.txt")
        self.update_info_file = os.path.join(self.script_dir, "update_info.json")
        
        # Crear directorios si no existen
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def should_check_update(self):
        """Determina si debe verificar actualizaciones basado en la última verificación"""
        if not os.path.exists(self.last_check_file):
            return True
        
        try:
            with open(self.last_check_file, 'r') as f:
                last_check = float(f.read().strip())
            
            elapsed = datetime.now().timestamp() - last_check
            return elapsed > CHECK_INTERVAL
        except:
            return True
    
    def update_last_check(self):
        """Actualiza el timestamp de la última verificación"""
        try:
            with open(self.last_check_file, 'w') as f:
                f.write(str(datetime.now().timestamp()))
        except:
            pass
    
    def check_for_updates(self, force=False):
        """Verifica si hay actualizaciones disponibles"""
        if not force and not self.should_check_update():
            return False
        
        self.status_changed.emit("🔍 Buscando actualizaciones...")
        
        try:
            # Descargar información de versión
            version_url = f"{UPDATE_SERVER}{VERSION_FILE}"
            self.status_changed.emit(f"📡 Conectando a {UPDATE_SERVER}")
            
            response = urllib.request.urlopen(version_url, timeout=10)
            data = json.loads(response.read().decode('utf-8'))
            
            remote_version = data.get('version', '0.0.0')
            changelog = data.get('changelog', 'Sin información de cambios')
            download_url = data.get('download_url', '')
            
            self.status_changed.emit(f"🔄 Versión remota: {remote_version}")
            
            # Comparar versiones
            if self.compare_versions(remote_version, VERSION) > 0:
                self.status_changed.emit(f"🎯 ¡Nueva versión disponible! ({remote_version})")
                
                # Guardar información de la actualización
                update_info = {
                    'remote_version': remote_version,
                    'changelog': changelog,
                    'download_url': download_url,
                    'files': data.get('files', []),
                    'timestamp': datetime.now().isoformat()
                }
                
                with open(self.update_info_file, 'w') as f:
                    json.dump(update_info, f, indent=2)
                
                self.update_available.emit(remote_version, changelog)
                self.update_last_check()
                return True
            else:
                self.status_changed.emit("✅ Estás en la última versión")
                if force:
                    self.update_finished.emit(True, "Ya tienes la última versión")
                self.update_last_check()
                return False
                
        except urllib.error.URLError as e:
            self.status_changed.emit(f"⚠️ Error de conexión: {str(e)}")
            return False
        except Exception as e:
            self.status_changed.emit(f"❌ Error: {str(e)}")
            return False
    
    def compare_versions(self, v1, v2):
        """Compara dos versiones en formato semántico (x.y.z)"""
        v1_parts = list(map(int, v1.split('.')))
        v2_parts = list(map(int, v2.split('.')))
        
        # Asegurar que ambas versiones tengan la misma longitud
        while len(v1_parts) < len(v2_parts):
            v1_parts.append(0)
        while len(v2_parts) < len(v1_parts):
            v2_parts.append(0)
        
        for i in range(len(v1_parts)):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1
        
        return 0
    
    def download_update(self):
        """Descarga la actualización"""
        try:
            with open(self.update_info_file, 'r') as f:
                update_info = json.load(f)
            
            download_url = update_info.get('download_url')
            if not download_url:
                self.status_changed.emit("❌ No hay URL de descarga disponible")
                return False
            
            self.status_changed.emit("📥 Descargando actualización...")
            
            # Limpiar directorio temporal
            for file in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, file))
            
            # Descargar archivo
            temp_file = os.path.join(self.temp_dir, UPDATE_FILE)
            
            def report_progress(count, block_size, total_size):
                if total_size > 0:
                    percent = int(count * block_size * 100 / total_size)
                    self.update_progress.emit(min(percent, 100))
            
            urllib.request.urlretrieve(download_url, temp_file, report_progress)
            
            self.status_changed.emit("✅ Descarga completada")
            return temp_file
            
        except Exception as e:
            self.status_changed.emit(f"❌ Error en descarga: {str(e)}")
            return False
    
    def create_backup(self):
        """Crea una copia de seguridad de los archivos actuales"""
        self.status_changed.emit("💾 Creando copia de seguridad...")
        
        try:
            # Limpiar backup anterior
            if os.path.exists(self.backup_dir):
                shutil.rmtree(self.backup_dir)
            os.makedirs(self.backup_dir, exist_ok=True)
            
            # Archivos a respaldar
            files_to_backup = [
                'launcher.py',
                'assets/logo.png',
                'assets/fondo.png',
                'assets/background.png'
            ]
            
            for file_path in files_to_backup:
                full_path = os.path.join(self.script_dir, file_path)
                if os.path.exists(full_path):
                    # Crear directorios necesarios
                    dest_dir = os.path.join(self.backup_dir, os.path.dirname(file_path))
                    os.makedirs(dest_dir, exist_ok=True)
                    
                    # Copiar archivo
                    dest_path = os.path.join(self.backup_dir, file_path)
                    shutil.copy2(full_path, dest_path)
            
            self.status_changed.emit("✅ Copia de seguridad creada")
            return True
            
        except Exception as e:
            self.status_changed.emit(f"⚠️ Error en backup: {str(e)}")
            return False
    
    def apply_update(self, update_file):
        """Aplica la actualización"""
        try:
            self.status_changed.emit("🔄 Aplicando actualización...")
            
            # Crear backup primero
            if not self.create_backup():
                self.status_changed.emit("⚠️ Continuando sin backup...")
            
            # Extraer archivos
            with zipfile.ZipFile(update_file, 'r') as zip_ref:
                # Obtener lista de archivos
                file_list = zip_ref.namelist()
                
                # Extraer cada archivo
                for i, file in enumerate(file_list):
                    zip_ref.extract(file, self.script_dir)
                    
                    # Actualizar progreso
                    progress = int((i + 1) * 100 / len(file_list))
                    self.update_progress.emit(progress)
            
            # Limpiar archivos temporales
            self.cleanup_temp_files()
            
            self.status_changed.emit("✨ ¡Actualización aplicada con éxito!")
            
            # Actualizar información de versión
            with open(self.update_info_file, 'r') as f:
                update_info = json.load(f)
            
            return True, update_info.get('remote_version', '')
            
        except Exception as e:
            self.status_changed.emit(f"❌ Error aplicando update: {str(e)}")
            
            # Intentar restaurar desde backup
            self.restore_backup()
            return False, str(e)
    
    def restore_backup(self):
        """Restaura la copia de seguridad en caso de error"""
        try:
            self.status_changed.emit("🔄 Restaurando desde copia de seguridad...")
            
            if os.path.exists(self.backup_dir):
                # Copiar archivos del backup
                for root, dirs, files in os.walk(self.backup_dir):
                    for file in files:
                        src_path = os.path.join(root, file)
                        rel_path = os.path.relpath(src_path, self.backup_dir)
                        dst_path = os.path.join(self.script_dir, rel_path)
                        
                        # Crear directorio si no existe
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        
                        # Copiar archivo
                        shutil.copy2(src_path, dst_path)
                
                self.status_changed.emit("✅ Restauración completada")
                return True
            else:
                self.status_changed.emit("⚠️ No hay copia de seguridad disponible")
                return False
                
        except Exception as e:
            self.status_changed.emit(f"❌ Error en restauración: {str(e)}")
            return False
    
    def cleanup_temp_files(self):
        """Limpia archivos temporales"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            
            # Eliminar archivo de info de update
            if os.path.exists(self.update_info_file):
                os.remove(self.update_info_file)
            
            self.status_changed.emit("🧹 Archivos temporales limpiados")
        except:
            pass
    
    def get_update_info(self):
        """Obtiene información de la actualización pendiente"""
        try:
            if os.path.exists(self.update_info_file):
                with open(self.update_info_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return None

# ============================================
# DIALOGO DE ACTUALIZACIÓN
# ============================================

class UpdateDialog(QDialog):
    """Diálogo para mostrar y gestionar actualizaciones"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 Actualización Disponible")
        self.setFixedSize(500, 400)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = QLabel("¡Nueva Versión Disponible!")
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #ff68f2;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Información de versión
        self.version_label = QLabel()
        self.version_label.setStyleSheet("""
            font-size: 14px;
            color: #ecf0f1;
        """)
        layout.addWidget(self.version_label)
        
        # Changelog
        changelog_label = QLabel("Novedades:")
        changelog_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #9b59b6;
            margin-top: 10px;
        """)
        layout.addWidget(changelog_label)
        
        self.changelog_text = QTextEdit()
        self.changelog_text.setReadOnly(True)
        self.changelog_text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 104, 242, 0.3);
                border-radius: 8px;
                color: #ecf0f1;
                padding: 10px;
                font-size: 12px;
            }
        """)
        self.changelog_text.setFixedHeight(120)
        layout.addWidget(self.changelog_text)
        
        # Barra de progreso
        self.progress_label = QLabel("Progreso:")
        self.progress_label.setStyleSheet("font-size: 12px; color: #bdc3c7;")
        layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(255, 104, 242, 0.3);
                border-radius: 5px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #ff68f2;
                border-radius: 5px;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.update_btn = QPushButton("Actualizar Ahora")
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff68f2;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #ff80ff;
            }
        """)
        self.update_btn.clicked.connect(self.accept)
        
        self.later_btn = QPushButton("Recordarme Más Tarde")
        self.later_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ecf0f1;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.later_btn.clicked.connect(self.reject)
        
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(231, 76, 60, 0.8);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(231, 76, 60, 1);
            }
        """)
        self.cancel_btn.clicked.connect(self.close)
        
        button_layout.addWidget(self.update_btn)
        button_layout.addWidget(self.later_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        # Estado
        self.status_label = QLabel()
        self.status_label.setStyleSheet("""
            font-size: 11px;
            color: #7f8c8d;
            font-style: italic;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
    
    def set_update_info(self, version, changelog):
        self.version_label.setText(f"Versión {version} disponible")
        self.changelog_text.setText(changelog)
    
    def show_progress(self, show=True):
        self.progress_bar.setVisible(show)
        self.progress_label.setVisible(show)
    
    def set_progress(self, value):
        self.progress_bar.setValue(value)
    
    def set_status(self, text):
        self.status_label.setText(text)

# ============================================
# COMPONENTES ORIGINALES DEL LAUNCHER
# ============================================

class CompactTitleBar(QWidget):
    """Barra de título compacta y elegante"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(42)

        # IMPORTANTE
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(10)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 10, 30, 160);
                border-bottom: 2px solid rgba(255, 104, 242, 40);
            }
        """)
        
        # Logo desde assets/logo.png
        logo_label = QLabel()
        logo_paths = [
            "assets/logo.png",
            "./assets/logo.png",
            os.path.join(os.getcwd(), "assets", "logo.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"),
        ]
        
        logo_pixmap = None
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo_pixmap = QPixmap(path)
                    if not logo_pixmap.isNull():
                        break
                except:
                    continue
        
        if logo_pixmap and not logo_pixmap.isNull():
            # Escalar el logo a tamaño apropiado
            logo_pixmap = logo_pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
        else:
            # Fallback a emoji si no hay logo
            logo_label.setText("🌸")
            logo_label.setStyleSheet("font-size: 20px; color: #ff68f2;")
        
        layout.addWidget(logo_label)
        
        self.title_label = QLabel(f"Sakura Blossom Launcher v{VERSION}")
        self.title_label.setStyleSheet("""
            color: #ecf0f1;
            font-size: 14px;
            font-weight: 600;
            font-family: 'Segoe UI';
            padding-left: 5px;
        """)
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        self.minimize_btn = self.create_compact_button("—", "#bdc3c7")
        self.minimize_btn.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.minimize_btn)
        
        self.maximize_btn = self.create_compact_button("□", "#bdc3c7")
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        layout.addWidget(self.maximize_btn)
        
        self.close_btn = self.create_compact_button("✕", "#e74c3c")
        self.close_btn.clicked.connect(self.parent.close)
        layout.addWidget(self.close_btn)
    
    def create_compact_button(self, text, color):
        btn = QPushButton(text)
        btn.setFixedSize(26, 26)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.12);
                color: {color};
                border: 1px solid rgba(255, 255, 255, 0.15);
                font-size: 12px;
                font-weight: bold;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.25);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.35);
            }}
        """)
        return btn
    
    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.maximize_btn.setText("□")
        else:
            self.parent.showMaximized()
            self.maximize_btn.setText("❐")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.drag_position = event.globalPos() - self.parent.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self.parent, 'drag_position'):
            self.parent.move(event.globalPos() - self.parent.drag_position)
            event.accept()
    
    def mouseDoubleClickEvent(self, event):
        self.toggle_maximize()


class BackgroundWidget(QWidget):
    """Widget con fondo personalizado - VERSIÓN CORREGIDA"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.background_image = None
        self.load_background()
        
    def load_background(self):
        """Carga imagen de fondo - MÉTODO MEJORADO"""
        print("🔍 Buscando imagen de fondo...")
        
        # Buscar en varias ubicaciones posibles
        possible_paths = [
            "fondo.png",                # En la misma carpeta
            "background.png",           # En la misma carpeta
            "./fondo.png",              # Ruta relativa
            "./background.png",         # Ruta relativa
            os.path.join(os.getcwd(), "fondo.png"),      # Ruta absoluta
            os.path.join(os.getcwd(), "background.png"), # Ruta absoluta
            os.path.join("assets", "fondo.png"),
            os.path.join("assets", "background.png"),
        ]
        
        # También buscar en el directorio del script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths.extend([
            os.path.join(script_dir, "fondo.png"),
            os.path.join(script_dir, "background.png"),
            os.path.join(script_dir, "fondo.jpg"),
            os.path.join(script_dir, "background.jpg"),
            os.path.join(script_dir, "assets", "fondo.png"),
            os.path.join(script_dir, "assets", "background.png"),
            os.path.join(script_dir, "assets", "fondo.jpg"),
            os.path.join(script_dir, "assets", "background.jpg"),
        ])
        
        for img_path in possible_paths:
            print(f"  Probando: {img_path}")
            if os.path.exists(img_path):
                try:
                    print(f"  ✓ Imagen encontrada en: {img_path}")
                    print(f"  📏 Tamaño del archivo: {os.path.getsize(img_path)} bytes")
                    
                    # Cargar la imagen
                    self.background_image = QPixmap(img_path)
                    
                    if self.background_image.isNull():
                        print(f"  ✗ Error: No se pudo cargar la imagen (QPIxmap es nulo)")
                        continue
                    
                    print(f"  ✅ Imagen cargada exitosamente")
                    print(f"  🖼️ Dimensiones: {self.background_image.width()}x{self.background_image.height()}")
                    return  # Salir si se cargó exitosamente
                    
                except Exception as e:
                    print(f"  ✗ Error cargando {img_path}: {e}")
                    continue
        
        # Si no se encontró ninguna imagen, crear fondo por defecto
        print("  ⚠️ No se encontró imagen de fondo, creando fondo por defecto")
        self.create_default_background()
    
    def create_default_background(self):
        """Crea un fondo por defecto elegante"""
        print("  🎨 Creando fondo por defecto...")
        self.background_image = QPixmap(1920, 1080)
        
        painter = QPainter(self.background_image)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Gradiente elegante rosado/azul
        gradient = QLinearGradient(0, 0, 1920, 1080)
        gradient.setColorAt(0, QColor(30, 10, 40))      # Púrpura oscuro
        gradient.setColorAt(0.3, QColor(60, 20, 80))    # Púrpura medio
        gradient.setColorAt(0.7, QColor(40, 10, 60))    # Púrpura
        gradient.setColorAt(1, QColor(20, 5, 30))       # Púrpura muy oscuro
        painter.fillRect(self.background_image.rect(), gradient)
        
        # Efecto de partículas de sakura (pétalos rosados)
        import random
        painter.setPen(Qt.NoPen)
        for _ in range(150):
            x = random.randint(0, 1919)
            y = random.randint(0, 1079)
            size = random.randint(2, 8)
            alpha = random.randint(20, 80)
            color = QColor(255, 104, 242, alpha)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(x, y, size, size)
        
        # Efecto de brillo sutil
        for _ in range(100):
            x = random.randint(0, 1919)
            y = random.randint(0, 1079)
            size = random.randint(1, 3)
            alpha = random.randint(10, 40)
            color = QColor(255, 255, 255, alpha)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(x, y, size, size)
        
        painter.end()
        print("  ✅ Fondo por defecto creado")
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.background_image and not self.background_image.isNull():
            try:
                # Escalar manteniendo aspecto
                scaled_pixmap = self.background_image.scaled(
                    self.size(), 
                    Qt.KeepAspectRatioByExpanding, 
                    Qt.SmoothTransformation
                )
                
                # Centrar la imagen
                x = (self.width() - scaled_pixmap.width()) // 2
                y = (self.height() - scaled_pixmap.height()) // 2
                
                painter.drawPixmap(x, y, scaled_pixmap)
                
                # Overlay oscuro para mejor contraste
                overlay = QLinearGradient(0, 0, 0, self.height())
                overlay.setColorAt(0, QColor(0, 0, 0, 30))
                overlay.setColorAt(1, QColor(0, 0, 0, 70))
                painter.fillRect(self.rect(), overlay)
                
            except Exception as e:
                print(f"✗ Error pintando fondo: {e}")
                # En caso de error, pintar fondo sólido
                painter.fillRect(self.rect(), QColor(20, 5, 30))
        else:
            # Si no hay imagen, usar color sólido
            painter.fillRect(self.rect(), QColor(20, 5, 30))

class ModernButton(QPushButton):
    def __init__(self, text, color="#ff68f2", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.color = color
        self.set_style()
        
    def set_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {self.color},
                    stop: 1 {self.lighten_color(self.color, 20)}
                );
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
                font-family: 'Segoe UI';
                min-width: 120px;
            }}
            QPushButton:hover {{
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {self.lighten_color(self.color, 10)},
                    stop: 1 {self.lighten_color(self.color, 30)}
                );
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            QPushButton:pressed {{
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {self.darken_color(self.color, 10)},
                    stop: 1 {self.darken_color(self.color, 20)}
                );
            }}
        """)
    
    def lighten_color(self, hex_color, percent=115):
        color = QColor(hex_color)
        return color.lighter(percent).name()
    
    def darken_color(self, hex_color, percent=115):
        color = QColor(hex_color)
        return color.darker(percent).name()

# ============================================
# LAUNCHER CON SISTEMA DE ACTUALIZACIÓN
# ============================================

class SakuraLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        print("=" * 50)
        print("🌸 INICIANDO SAKURA BLOSSOM LAUNCHER 🌸")
        print(f"📊 Versión: {VERSION}")
        print("=" * 50)
        print(f"📂 Directorio actual: {os.getcwd()}")
        print(f"📂 Directorio del script: {os.path.dirname(os.path.abspath(__file__))}")
        
        # Inicializar sistema de actualización
        self.update_manager = UpdateManager()
        self.update_manager.update_available.connect(self.on_update_available)
        self.update_manager.update_progress.connect(self.on_update_progress)
        self.update_manager.update_finished.connect(self.on_update_finished)
        self.update_manager.status_changed.connect(self.on_update_status)
        
        self.user_logged_in = False
        self.current_user = ""
        
        # Configurar ventana
        self.setWindowTitle(f"Sakura Blossom Launcher v{VERSION}")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Barra de título (con indicador de actualización)
        self.title_bar = CompactTitleBar(self)
        main_layout.addWidget(self.title_bar)
        
        # Contenido principal
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Cargar fondo
        print("\n🖼️ CARGANDO FONDO...")
        self.background = BackgroundWidget()
        content_layout.addWidget(self.background)
        
        # Layout overlay para contenido
        self.overlay_layout = QVBoxLayout(self.background)
        self.overlay_layout.setContentsMargins(0, 0, 0, 0)
        
        # Mostrar login
        self.show_login_screen()
        
        main_layout.addWidget(content_widget)
        
        # Verificar actualizaciones en segundo plano después de 2 segundos
        QTimer.singleShot(2000, self.check_updates_on_start)
        
        print("\n✅ Launcher inicializado correctamente")
        print("=" * 50)
    
    def check_updates_on_start(self):
        """Verifica actualizaciones al iniciar"""
        print("🔍 Verificando actualizaciones...")
        thread = threading.Thread(target=self.update_manager.check_for_updates)
        thread.daemon = True
        thread.start()
    
    def on_update_available(self, version, changelog):
        """Se llama cuando hay una actualización disponible"""
        print(f"🎯 Actualización disponible: {version}")
        
        # Mostrar diálogo de actualización
        self.show_update_dialog(version, changelog)
    
    def on_update_progress(self, progress):
        """Actualiza la barra de progreso"""
        if hasattr(self, 'update_dialog'):
            self.update_dialog.set_progress(progress)
    
    def on_update_finished(self, success, message):
        """Se llama cuando la actualización termina"""
        print(f"📤 Actualización finalizada: {success} - {message}")
        
        if success:
            QMessageBox.information(self, "✅ Actualización Completada", 
                                   "La actualización se ha aplicado correctamente.\n"
                                   "El launcher se reiniciará automáticamente.",
                                   QMessageBox.Ok)
            
            # Reiniciar el launcher
            QTimer.singleShot(2000, self.restart_launcher)
        else:
            QMessageBox.warning(self, "⚠️ Error en Actualización", 
                               f"No se pudo completar la actualización:\n{message}",
                               QMessageBox.Ok)
    
    def on_update_status(self, status):
        """Actualiza el estado de la actualización"""
        print(f"📢 Estado actualización: {status}")
        if hasattr(self, 'update_dialog'):
            self.update_dialog.set_status(status)
    
    def show_update_dialog(self, version, changelog):
        """Muestra el diálogo de actualización"""
        self.update_dialog = UpdateDialog(self)
        self.update_dialog.set_update_info(version, changelog)
        
        # Conectar señales
        self.update_dialog.accepted.connect(self.start_update_process)
        
        # Mostrar diálogo
        self.update_dialog.exec_()
    
    def start_update_process(self):
        """Inicia el proceso de actualización"""
        print("🚀 Iniciando proceso de actualización...")
        
        # Mostrar progreso en el diálogo
        self.update_dialog.show_progress(True)
        self.update_dialog.update_btn.setEnabled(False)
        self.update_dialog.later_btn.setEnabled(False)
        self.update_dialog.cancel_btn.setEnabled(False)
        
        # Iniciar actualización en un hilo separado
        thread = threading.Thread(target=self.perform_update)
        thread.daemon = True
        thread.start()
    
    def perform_update(self):
        """Realiza la actualización completa"""
        try:
            # 1. Descargar actualización
            update_file = self.update_manager.download_update()
            if not update_file:
                self.update_manager.update_finished.emit(False, "Error en la descarga")
                return
            
            # 2. Aplicar actualización
            success, message = self.update_manager.apply_update(update_file)
            
            # 3. Emitir resultado
            self.update_manager.update_finished.emit(success, message)
            
        except Exception as e:
            self.update_manager.update_finished.emit(False, str(e))
    
    def restart_launcher(self):
        """Reinicia el launcher"""
        print("🔄 Reiniciando launcher...")
        
        # Cerrar aplicación actual
        self.close()
        
        # Reiniciar proceso
        python = sys.executable
        os.execl(python, python, *sys.argv)
    
    def clear_overlay(self):
        while self.overlay_layout.count():
            child = self.overlay_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def show_login_screen(self):
        self.clear_overlay()
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignCenter)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        login_frame = QFrame()
        login_frame.setFixedSize(550, 650)
        login_frame.setContentsMargins(20, 20, 20, 20)
        login_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(25, 15, 35, 230);
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            }
        """)
        
        frame_layout = QVBoxLayout(login_frame)
        frame_layout.setAlignment(Qt.AlignCenter)
        frame_layout.setContentsMargins(30, 40, 30, 40)
        frame_layout.setSpacing(15)
        
        # Logo con efecto - usar logo desde assets
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setAlignment(Qt.AlignCenter)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        
        logo_label = QLabel()
        logo_paths = [
            "assets/logo.png",
            "./assets/logo.png",
            os.path.join(os.getcwd(), "assets", "logo.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"),
        ]
        
        logo_pixmap = None
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo_pixmap = QPixmap(path)
                    if not logo_pixmap.isNull():
                        break
                except:
                    continue
        
        if logo_pixmap and not logo_pixmap.isNull():
            # Escalar el logo
            logo_pixmap = logo_pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)

            logo_label.setStyleSheet("background: transparent;")
            logo_label.setAlignment(Qt.AlignCenter)

        else:
            # Fallback a emoji
            logo_label.setText("🌸")
            logo_label.setStyleSheet("""
                font-size: 120px;
                color: #ff68f2;
                background: transparent;
            """)

            
            logo_label.setAlignment(Qt.AlignCenter)
        
        logo_layout.addWidget(logo_label)
        frame_layout.addWidget(logo_container)

        frame_layout.addSpacing(10)
        
        # Título con gradiente
        title = QLabel("SAKURA BLOSSOM")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            font-family: 'Segoe UI';
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ff68f2, stop:1 #9b59b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            color: transparent;
        """)
        title.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(title)
        
        subtitle = QLabel("Launcher BETA")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: rgba(200, 200, 220, 70);
            font-family: 'Segoe UI';
            letter-spacing: 2px;
        """)
        subtitle.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(subtitle)
        
        frame_layout.addSpacing(25)
        
        # Formulario con iconos
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setAlignment(Qt.AlignCenter)
        form_layout.setSpacing(12)
        
        # Campo de usuario con icono
        user_container = QWidget()
        user_container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                border: 2px solid rgba(255, 255, 255, 0.18);
            }
        """)
        user_layout = QHBoxLayout(user_container)
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_layout.setSpacing(0)
        
        user_icon = QLabel("👤")
        user_icon.setStyleSheet("""
            font-size: 20px;
            color: rgba(255, 104, 242, 80);
            padding: 10px;
        """)
        user_icon.setFixedWidth(50)
        user_icon.setAlignment(Qt.AlignCenter)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Usuario")
        self.username_input.setFixedHeight(48)
        self.username_input.setAlignment(Qt.AlignVCenter)
        self.username_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                padding-left: 12px;
                padding-right: 16px;
                color: #ecf0f1;
                font-size: 14px;
                font-family: 'Segoe UI';
                min-width: 250px;
            }
            QLineEdit::placeholder {
                color: rgba(236, 240, 241, 90);
            }
            QLineEdit:focus {
                border: none;
                background: transparent;
            }
        """)
        
        user_layout.addWidget(user_icon)
        user_layout.addWidget(self.username_input)
        form_layout.addWidget(user_container)
        
        # Campo de contraseña con icono
        pass_container = QWidget()
        pass_container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                border: 2px solid rgba(255, 255, 255, 0.18);
            }
        """)

        pass_layout = QHBoxLayout(pass_container)
        pass_layout.setContentsMargins(0, 0, 0, 0)
        
        pass_icon = QLabel("🔒")
        pass_icon.setStyleSheet("""
            font-size: 20px;
            color: rgba(255, 104, 242, 80);
            padding: 10px;
        """)
        pass_icon.setFixedWidth(50)
        pass_icon.setAlignment(Qt.AlignCenter)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Contraseña")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedHeight(48)
        self.password_input.setAlignment(Qt.AlignVCenter)
        self.password_input.setStyleSheet(self.username_input.styleSheet())
        
        pass_layout.addWidget(pass_icon)
        pass_layout.addWidget(self.password_input)
        form_layout.addWidget(pass_container)
        
        frame_layout.addWidget(form_widget)
        
        frame_layout.addSpacing(20)
        
        # Botón con efecto especial
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(0)
        
        login_btn = QPushButton("  INICIAR SESIÓN  ")
        login_btn.setFixedSize(320, 50)
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        login_btn.clicked.connect(self.attempt_login)
        login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(255, 104, 242, 255),
                    stop: 0.5 rgba(155, 89, 182, 255),
                    stop: 1 rgba(255, 104, 242, 255)
                );
                color: white;
                border: none;
                border-radius: 15px;
                padding: 15px 30px;
                font-size: 14px;
                font-weight: 600;
                font-family: 'Segoe UI';
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(255, 120, 255, 255),
                    stop: 0.5 rgba(175, 109, 202, 255),
                    stop: 1 rgba(255, 120, 255, 255)
                );
                border: 2px solid rgba(255, 255, 255, 0.3);
                transform: scale(1.02);
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(235, 84, 222, 255),
                    stop: 0.5 rgba(135, 69, 162, 255),
                    stop: 1 rgba(235, 84, 222, 255)
                );
            }
        """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(login_btn)
        btn_layout.addStretch()
        
        frame_layout.addWidget(btn_container)
        
        frame_layout.addStretch()
        
        # Versión con estilo mejorado
        version = QLabel(f"v{VERSION} | Coded with love, by Plxgio")
        version.setStyleSheet("""
            font-size: 10px;
            color: rgba(150, 150, 170, 70);
            font-family: 'Consolas', monospace;
            padding-top: 5px;
            border-top: 1px solid rgba(255, 104, 242, 20);
            min-height: 10px;
        """)
        version.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(version)
        
        container_layout.addWidget(login_frame)
        self.overlay_layout.addWidget(container)
    
    def attempt_login(self):
        username = self.username_input.text().strip()
        
        if username and username != "Ingresa tu nombre":
            self.current_user = username
            self.user_logged_in = True
            self.show_main_screen()
        else:
            QMessageBox.warning(self, "Error", "Por favor, ingresa un nombre de usuario")
    
    def show_main_screen(self):
        self.clear_overlay()
        
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Panel izquierdo - Menú
        left_panel = QFrame()
        left_panel.setFixedWidth(240)
        left_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(25, 15, 35, 230);
                border-radius: 15px;
                border: 1px solid rgba(255, 104, 242, 30);
            }
        """)
        
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 20, 15, 20)
        left_layout.setSpacing(10)
        
        # Logo del panel - usar logo desde assets
        logo_label = QLabel()
        logo_paths = [
            "assets/logo.png",
            "./assets/logo.png",
            os.path.join(os.getcwd(), "assets", "logo.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"),
        ]
        
        logo_pixmap = None
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo_pixmap = QPixmap(path)
                    if not logo_pixmap.isNull():
                        break
                except:
                    continue
        
        if logo_pixmap and not logo_pixmap.isNull():
            logo_pixmap = logo_pixmap.scaled(200, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setStyleSheet("""
                padding-bottom: 5px;
                border-bottom: 1px solid rgba(255, 104, 242, 30);
                margin-bottom: 15px;
                min-height: 60px;
            """)
        else:
            logo_label.setText("🌸 Sakura Blossom")
            logo_label.setStyleSheet("""
                font-size: 18px;
                font-weight: bold;
                color: #ff68f2;
                padding-bottom: 5px;
                border-bottom: 1px solid rgba(255, 104, 242, 30);
                margin-bottom: 15px;
                min-height: 60px;
            """)
        
        logo_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(logo_label)
        
        # Opciones del menú
        tabs = [
            ("🏠", "Inicio", "home", "#ff68f2"),
            ("👤", "Personaje", "character", "#9b59b6"),
            ("📖", "Lore", "lore", "#1abc9c"),
            ("🔧", "Mods", "mods", "#e67e22"),
            ("⚙️", "Opciones", "settings", "#3498db"),
            ("💬", "Soporte", "support", "#e74c3c")
        ]
        
        for icon, text, tab_id, color in tabs:
            btn = self.create_menu_button(icon, text, color)
            btn.clicked.connect(lambda checked, t=tab_id: self.show_tab(t))
            left_layout.addWidget(btn)
        
        # Botón de buscar actualizaciones
        update_btn = self.create_menu_button("🔄", "Buscar Actualizaciones", "#2ecc71")
        update_btn.clicked.connect(self.manual_check_updates)
        left_layout.addWidget(update_btn)
        
        left_layout.addStretch()
        
        # Información del servidor
        server_info = QLabel("🟢 Servidor encendido")
        server_info.setStyleSheet("""
            font-size: 12px;
            color: #2ecc71;
            background-color: rgba(46, 204, 113, 0.1);
            border-radius: 8px;
            padding: 8px;
            border: 1px solid rgba(46, 204, 113, 0.3);
            min-height: 35px;
        """)
        server_info.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(server_info)
        
        # Información del usuario
        user_container = QFrame()
        user_container.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 104, 242, 0.1);
                border-radius: 10px;
                border: 1px solid rgba(255, 104, 242, 0.3);
                min-height: 40px;
            }
        """)
        user_layout = QHBoxLayout(user_container)
        user_layout.setContentsMargins(10, 8, 10, 8)
        
        user_icon = QLabel("👤")
        user_icon.setStyleSheet("font-size: 16px;")
        
        user_label = QLabel(f"{self.current_user}")
        user_label.setStyleSheet("""
            font-size: 12px; 
            color: #ecf0f1; 
            font-weight: bold;
            min-width: 80px;
            padding-left: 5px;
        """)
        
        logout_btn = QPushButton("Salir")
        logout_btn.setFixedSize(50, 24)
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(231, 76, 60, 0.8);
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(231, 76, 60, 1);
            }
        """)
        logout_btn.clicked.connect(self.logout)
        
        user_layout.addWidget(user_icon)
        user_layout.addWidget(user_label)
        user_layout.addStretch()
        user_layout.addWidget(logout_btn)
        
        left_layout.addWidget(user_container)
        
        # Versión actual
        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("""
            font-size: 10px;
            color: rgba(150, 150, 170, 70);
            font-family: 'Consolas', monospace;
            padding-top: 5px;
            text-align: center;
        """)
        left_layout.addWidget(version_label)
        
        # Panel derecho - Contenido
        right_panel = QFrame()
        right_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(25, 15, 35, 230);
                border-radius: 15px;
                border: 1px solid rgba(255, 104, 242, 30);
            }
        """)
        
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(25, 25, 25, 25)
        
        # Stack de contenido
        self.content_stack = QStackedWidget()
        right_layout.addWidget(self.content_stack)
        
        self.create_all_tabs()
        
        # Botón de jugar
        play_container = QWidget()
        play_layout = QHBoxLayout(play_container)
        play_layout.setContentsMargins(0, 20, 0, 0)
        
        play_btn = QPushButton("  CONECTAR AL SERVIDOR  ")
        play_btn.setFixedSize(280, 50)
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        play_btn.clicked.connect(self.launch_minecraft)
        play_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #2ecc71,
                    stop: 0.5 #27ae60,
                    stop: 1 #2ecc71
                );
                color: white;
                border: none;
                border-radius: 12px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #58d68d,
                    stop: 0.5 #2ecc71,
                    stop: 1 #58d68d
                );
                border: 2px solid rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #239b56,
                    stop: 0.5 #1e8449,
                    stop: 1 #239b56
                );
            }
        """)
        
        play_layout.addStretch()
        play_layout.addWidget(play_btn)
        play_layout.addStretch()
        
        right_layout.addWidget(play_container)
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
        self.overlay_layout.addWidget(main_widget)
        
        self.show_tab("home")
    
    def create_menu_button(self, icon, text, color):
        btn = QPushButton(f"{icon}  {text}")
        btn.setFixedHeight(45)
        btn.setCursor(Qt.PointingHandCursor)
        
        # Extraer componentes RGB del color
        color_obj = QColor(color)
        r = color_obj.red()
        g = color_obj.green()
        b = color_obj.blue()
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 5);
                color: #ecf0f1;
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 10px;
                padding: 10px 15px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                min-width: 180px;
            }}
            QPushButton:hover {{
                background-color: rgba({r}, {g}, {b}, 20);
                border: 1px solid {color};
                transform: translateX(5px);
            }}
            QPushButton:pressed {{
                background-color: rgba({r}, {g}, {b}, 40);
            }}
        """)
        return btn
    
    def create_all_tabs(self):
        tabs_content = {
            'home': ("INICIO", """
                <h2 style="color: #ff68f2;">¡Bienvenido a Blossom Sakura!</h2>
                <p style="color: #ecf0f1; line-height: 1.6;">
                    Survival progresivo orientado al roleplay entre clanes con una economía real de por medio.
                     Explorá Sakura Valley y las tierras que la rodean, completá misiones, elegí tu distrito,
                     formá clanes y protegé tus tierras.
                </p>
                <h3 style="color: #9b59b6;">Características principales:</h3>
                <ul style="color: #bdc3c7; line-height: 1.8;">
                    <li><strong>Sistema de clanes y sectores</strong> - Crea tu propio clan y domina territorios.</li>
                    <li><strong>Economía balanceada</strong> - Sistema de comercio justo y cuidado.</li>
                    <li><strong>Granjas funcionales</strong> - Domina las granjas exteriores o alquila las seguras.</li>
                    <li><strong>Rol inmersivo</strong> - Historias únicas y eventos especiales.</li>
                    <li><strong>Sistema de parcelas</strong> - Construye tu hogar dentro de las protecciones de tu distrito.</li>
                    <li><strong>Mods personalizados</strong> - Experiencia única con mods exclusivos.</li>
                </ul>
                <p style="color: #ecf0f1; margin-top: 20px;">
                    <strong>IP del servidor:</strong> No definida por ahora<br>
                    <strong>Versión:</strong> Minecraft 1.20.1<br>
                    <strong>Estado:</strong> <span style="color: #2ecc71;">● En línea</span>
                </p>
            """),
            'character': ("MI PERSONAJE", """
                <h3 style="color: #9b59b6;">Próximamente...</h3>
            """),
            'lore': ("LORE", """
                <h3 style="color: #9b59b6;">Próximamente...</h3>
            """),
            'mods': ("MODS", """
                <h3 style="color: #e67e22;">Mods Requeridos</h3>
                <p style="color: #ecf0f1;">seguro ponga una lista aca de los mods activos y demás, pero nada desactivable o agregable</p>
               
                     """),
            'settings': ("OPCIONES", """
                <h3 style="color: #3498db;">Configuración</h3>
                <p style="color: #ecf0f1;">Ajusta la configuración del launcher y del juego.</p>
                
                <div style="background: rgba(52, 152, 219, 0.1); padding: 20px; border-radius: 10px; margin: 15px 0;">
                    <h4 style="color: #3498db;"> Configuración del launcher:</h4>
                    <p style="color: #ecf0f1;">
                        • Idioma esp/eng<br>
                        • Cerrar al jugar<br>
                        • Y no sé, dps veo q mas
                    </p>
                </div>
                
                <div style="background: rgba(52, 152, 219, 0.05); padding: 20px; border-radius: 10px; margin: 15px 0;">
                    <h4 style="color: #3498db;"> Configuración del juego:</h4>
                    <p style="color: #ecf0f1;">
                        • Asignación de RAM<br>
                        • Perfiles: Optimizado, medio, alto<br>
                    </p>
                </div>
            """),
            'support': ("SOPORTE", """
                <h3 style="color: #e74c3c;">Ayuda y Soporte</h3>
                <p style="color: #ecf0f1;">¿Necesitas ayuda? Hablanos para asistirte.</p>
                
                <div style="background: rgba(231, 76, 60, 0.1); padding: 20px; border-radius: 10px; margin: 15px 0;">
                    <h4 style="color: #e74c3c;"> Contacto:</h4>
                    <p style="color: #ecf0f1; line-height: 1.8;">
                        <span style="color: #7289da;">🎮</span> <strong>Owner:</strong> sofixr<br>
                        <span style="color: #7289da;">🎮</span> <strong>Developer:</strong> plxgio
                    </p>
                
                
                <div style="margin-top: 15px; padding-top: 10px; border-top: 1px solid rgba(231, 76, 60, 0.2);">
                        <p style="color: #ecf0f1;">
                            <strong>Recomendamos abrir un ticket en:</strong><br>
                            <a href="https://discord.gg/NGGyWUjzbx" style="color: #3498db; text-decoration: none; font-weight: bold;">
                                🌐 Discord | Blossom Sakura
                        </p>    </a>
                </div>
            """)
        }
        
        for tab_id, (title, content) in tabs_content.items():
            widget = QWidget()
            layout = QVBoxLayout(widget)
            
            title_label = QLabel(title)
            title_label.setStyleSheet("""
                font-size: 24px;
                font-weight: bold;
                color: #ff68f2;
                padding-bottom: 15px;
                border-bottom: 2px solid rgba(255, 104, 242, 30);
                margin-bottom: 20px;
                min-height: 40px;
            """)
            layout.addWidget(title_label)
            
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setStyleSheet("""
                QScrollArea {
                    border: none;
                    background: transparent;
                }
                QScrollBar:vertical {
                    border: none;
                    background: rgba(255, 255, 255, 0.05);
                    width: 10px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(255, 104, 242, 0.5);
                    border-radius: 5px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(255, 104, 242, 0.7);
                }
            """)
            
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(5, 5, 15, 5)
            
            content_label = QLabel(content)
            content_label.setStyleSheet("""
                font-size: 14px;
                color: #ecf0f1;
                line-height: 1.6;
                padding: 10px;
            """)
            content_label.setWordWrap(True)
            content_label.setTextFormat(Qt.RichText)
            content_label.setOpenExternalLinks(True)
            
            content_layout.addWidget(content_label)
            content_layout.addStretch()
            
            scroll_area.setWidget(content_widget)
            layout.addWidget(scroll_area)
            
            self.content_stack.addWidget(widget)
    
    def show_tab(self, tab_id):
        tab_index = {"home": 0, "character": 1, "lore": 2, 
                    "mods": 3, "settings": 4, "support": 5}
        self.content_stack.setCurrentIndex(tab_index[tab_id])
    
    def launch_minecraft(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("🎮 Conectando...")
        msg.setText(f"""
        <h3 style="color: #2ecc71;">Conectando al servidor</h3>
        <p style="color: #ecf0f1;">
            <b>Jugador:</b> {self.current_user}<br>
            <b>Servidor:</b> Sakura Blossom<br>
            <b>IP:</b> Por verse<br>
            <b>Estado:</b> Iniciando cliente de Minecraft...
        </p>
        """)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: rgba(25, 15, 35, 240);
                border: 2px solid rgba(255, 104, 242, 50);
                border-radius: 15px;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #ff68f2;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #ff80ff;
            }
        """)
        msg.exec_()
    
    def logout(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("🔒 Cerrar sesión")
        msg.setText(f"""
        <h3 style="color: #e74c3c;">¿Cerrar sesión?</h3>
        <p style="color: #ecf0f1;">
            Estás a punto de cerrar sesión como:<br>
            <b>{self.current_user}</b>
        </p>
        <p style="color: #bdc3c7; font-size: 12px;">
            Tu progreso está guardado en el servidor.
        </p>
        """)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: rgba(25, 15, 35, 240);
                border: 2px solid rgba(255, 104, 242, 50);
                border-radius: 15px;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                min-width: 80px;
                min-height: 30px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton[text="&Yes"] {
                background-color: #e74c3c;
                color: white;
            }
            QPushButton[text="&No"] {
                background-color: #7f8c8d;
                color: white;
            }
        """)
        
        if msg.exec_() == QMessageBox.Yes:
            self.user_logged_in = False
            self.current_user = ""
            self.show_login_screen()
    
    def manual_check_updates(self):
        """Verifica actualizaciones manualmente"""
        print("🔍 Búsqueda manual de actualizaciones...")
        
        # Mostrar mensaje de verificación
        QMessageBox.information(self, "🔍 Buscando actualizaciones", 
                               "Verificando si hay nuevas versiones disponibles...",
                               QMessageBox.Ok)
        
        # Verificar en un hilo separado
        thread = threading.Thread(target=lambda: self.update_manager.check_for_updates(force=True))
        thread.daemon = True
        thread.start()

# ============================================
# EJECUTAR
# ============================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Establecer paleta de colores
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(25, 15, 35))
    palette.setColor(QPalette.WindowText, QColor(236, 240, 241))
    palette.setColor(QPalette.Base, QColor(35, 25, 45))
    palette.setColor(QPalette.AlternateBase, QColor(45, 35, 55))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 104, 242))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(236, 240, 241))
    palette.setColor(QPalette.Button, QColor(55, 45, 65))
    palette.setColor(QPalette.ButtonText, QColor(236, 240, 241))
    palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.Highlight, QColor(255, 104, 242))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    launcher = SakuraLauncher()
    launcher.show()
    
    sys.exit(app.exec_())