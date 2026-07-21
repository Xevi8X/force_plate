import csv
import math
import struct
from shutil import rmtree
import sys
import tempfile
import time
import wave
from collections import deque
from datetime import datetime
from pathlib import Path

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from analysis import ALGORITHMS, ANALYSES, algorithm_for, append_summary, load_log, plot_analysis
from transducer.modbus_config import ModbusConfig
from transducer.transducer import Transducer


START_BEEP_FREQUENCY_HZ = 600
START_BEEP_DURATION_MS = 500
START_BEEP_DELAY_MS = 0

STOP_BEEP_FREQUENCY_HZ = 400
STOP_BEEP_DURATION_MS = 500
STOP_BEEP_DELAY_MS = 0

DOUBLE_SIGNAL_DELAY_MS = 1000
END_TIME_SIGNAL_DELAY_MS = 3000


class MeasurementWorker(QThread):
    sample_ready = pyqtSignal(float, float)
    read_error = pyqtSignal(str)

    def __init__(self, transducer):
        super().__init__()
        self.transducer = transducer
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            try:
                weight = self.transducer.read_weight()
            except Exception as error:
                self.read_error.emit(str(error))
                return
            self.sample_ready.emit(time.monotonic(), weight)


class MainWindow(QMainWindow):
    GRAVITY_CONSTANT = 9.805
    SCALE_FACTOR = 100
    WINDOW_SIZE = 20

    def __init__(self):
        super().__init__()
        self.transducer = None
        self.measurement_worker = None
        self.measurement_window = deque(maxlen=self.WINDOW_SIZE)
        self.sample_count = 0
        self.is_recording = False
        self.record_start_mono = None
        self.record_file = None
        self.record_file_path = None
        self.record_writer = None
        self.beep_directory = Path(tempfile.mkdtemp(prefix='platform_beeps_'))
        self.beep_sounds = {}
        self.test_signal_timers = []
        self.session_path = self.create_session_path()
        self.summary_path = self.session_path / 'summary'
        self.summary_path.mkdir()
        self.init_ui()

    def create_session_path(self):
        root = Path('logs')
        name = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = root / name
        suffix = 2
        while path.exists():
            path = root / f'{name}_{suffix}'
            suffix += 1
        path.mkdir(parents=True)
        return path

    def init_ui(self):
        self.setWindowTitle('Dynamometric platform')
        self.setGeometry(100, 100, 1200, 768)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.test_tab_index = self.tabs.addTab(self.create_test_tab(), 'Test')
        self.analysis_tab_index = self.tabs.addTab(self.create_analysis_tab(), 'Analysis')
        self.tabs.addTab(self.create_calibration_tab(), 'Calibration')
        self.tabs.addTab(self.create_settings_tab(), 'Settings')
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.update_record_controls()
        self.update_polling()

    def create_test_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.current_load_label = QLabel('-.-- kg')
        self.current_load_label.setAlignment(Qt.AlignCenter)
        self.current_load_label.setStyleSheet('font-size: 96px; font-weight: bold;')

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('Test:'))
        self.test_combo = QComboBox()
        self.test_combo.addItems(ANALYSES)
        mode_row.addWidget(self.test_combo)
        mode_row.addStretch()

        name_row = QHBoxLayout()
        self.custom_name_input = QLineEdit()
        self.custom_name_input.setPlaceholderText('e.g. athlete_01')
        name_row.addWidget(QLabel('Custom name:'))
        name_row.addWidget(self.custom_name_input)

        control_row = QHBoxLayout()
        self.analyse_after_test = QCheckBox('Analyse after test')
        self.analyse_after_test.setChecked(True)
        self.double_signal = QCheckBox('Double signal')
        self.end_time_signal = QCheckBox('End-of-time signal')
        self.start_button = QPushButton('Start')
        self.stop_button = QPushButton('Stop')
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(lambda: self.stop_recording(beep=True))
        control_row.addWidget(self.analyse_after_test)
        control_row.addWidget(self.double_signal)
        control_row.addWidget(self.end_time_signal)
        control_row.addStretch()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)

        layout.addLayout(mode_row)
        layout.addLayout(name_row)
        layout.addLayout(control_row)
        layout.addWidget(self.current_load_label)
        layout.addStretch()
        return tab

    def create_analysis_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(0)

        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)

        open_button = QPushButton('Open log')
        open_button.clicked.connect(self.open_log)

        self.analysis_file_label = QLabel('No log opened')
        self.analysis_file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        row.addWidget(open_button)
        row.addWidget(self.analysis_file_label, 1)
        header.setFixedHeight(open_button.sizeHint().height())

        self.analysis_figure = Figure(figsize=(10, 5))
        self.analysis_canvas = FigureCanvasQTAgg(self.analysis_figure)

        layout.addWidget(header)
        layout.addWidget(self.analysis_canvas, 1)

        return tab

    def create_calibration_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        zero_row = QHBoxLayout()
        self.zero_button = QPushButton('Zero')
        self.zero_button.clicked.connect(self.zero_transducer)
        zero_row.addWidget(QLabel('Zero the transducer:'))
        zero_row.addWidget(self.zero_button)

        weight_row = QHBoxLayout()
        self.weight_input = QDoubleSpinBox()
        self.weight_input.setRange(2.00, 100.00)
        self.weight_input.setDecimals(2)
        self.weight_input.setSingleStep(0.01)
        self.weight_input.setValue(50.00)
        self.calibrate_button = QPushButton('Calibrate weight')
        self.calibrate_button.clicked.connect(self.calibrate_weight)
        weight_row.addWidget(QLabel('Weight:'))
        weight_row.addWidget(self.weight_input)
        weight_row.addWidget(self.calibrate_button)

        layout.addLayout(zero_row)
        layout.addLayout(weight_row)
        layout.addStretch()
        return tab

    def create_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        port_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.addItems(port.device for port in list_ports.comports())
        port_row.addWidget(QLabel('Serial port:'))
        port_row.addWidget(self.port_combo)

        buttons_row = QHBoxLayout()
        self.connect_button = QPushButton('Connect')
        self.disconnect_button = QPushButton('Disconnect')
        self.connect_button.clicked.connect(self.connect_transducer)
        self.disconnect_button.clicked.connect(self.disconnect_transducer)
        buttons_row.addWidget(self.connect_button)
        buttons_row.addWidget(self.disconnect_button)

        layout.addLayout(port_row)
        layout.addLayout(buttons_row)
        layout.addStretch()
        self.update_connection_controls()
        return tab

    def selected_test(self):
        return self.test_combo.currentText()

    def schedule_beep(self, frequency, duration_ms, delay_ms):
        if delay_ms < 0:
            return
        QTimer.singleShot(delay_ms, lambda: self.play_beep(frequency, duration_ms))

    def schedule_test_beep(self, frequency, duration_ms, delay_ms):
        if delay_ms < 0:
            return

        timer = QTimer(self)
        timer.setSingleShot(True)

        def play():
            if timer not in self.test_signal_timers:
                return
            self.test_signal_timers.remove(timer)
            timer.deleteLater()
            if self.is_recording:
                self.play_beep(frequency, duration_ms)

        timer.timeout.connect(play)
        self.test_signal_timers.append(timer)
        timer.start(delay_ms)

    def cancel_test_signals(self):
        for timer in self.test_signal_timers:
            timer.stop()
            timer.deleteLater()
        self.test_signal_timers.clear()

    def schedule_test_signals(self):
        self.cancel_test_signals()
        if START_BEEP_DELAY_MS < 0:
            return

        self.schedule_test_beep(
            START_BEEP_FREQUENCY_HZ,
            START_BEEP_DURATION_MS,
            START_BEEP_DELAY_MS,
        )

        last_start_delay = START_BEEP_DELAY_MS
        if self.double_signal.isChecked():
            last_start_delay += DOUBLE_SIGNAL_DELAY_MS
            self.schedule_test_beep(
                START_BEEP_FREQUENCY_HZ,
                START_BEEP_DURATION_MS,
                last_start_delay,
            )

        if self.end_time_signal.isChecked():
            self.schedule_test_beep(
                STOP_BEEP_FREQUENCY_HZ,
                STOP_BEEP_DURATION_MS,
                last_start_delay + END_TIME_SIGNAL_DELAY_MS,
            )

    def play_beep(self, frequency, duration_ms):
        key = (frequency, duration_ms)
        sound = self.beep_sounds.get(key)
        if sound is None:
            file_path = self.beep_directory / f'{frequency}_{duration_ms}.wav'
            sample_rate = 44100
            sample_count = round(sample_rate * duration_ms / 1000)
            fade = min(sample_rate // 100, sample_count // 2)
            frames = bytearray(sample_count * 2)

            for index in range(sample_count):
                envelope = min(1.0, index / fade, (sample_count - index - 1) / fade) if fade else 1.0
                sample = round(16000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
                struct.pack_into('<h', frames, index * 2, sample)

            with wave.open(str(file_path), 'wb') as file:
                file.setnchannels(1)
                file.setsampwidth(2)
                file.setframerate(sample_rate)
                file.writeframes(frames)

            sound = QSoundEffect(self)
            sound.setSource(QUrl.fromLocalFile(str(file_path)))
            self.beep_sounds[key] = sound

        sound.stop()
        sound.play()

    def build_record_file_path(self, test_name: str, custom_name: str):
        safe_name = ''.join(char if char.isalnum() or char in '-_' else '_' for char in custom_name)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return self.session_path / test_name.lower().replace(' ', '_') / f'{timestamp}_{safe_name}.csv'

    def start_recording(self):
        if self.transducer is None:
            QMessageBox.warning(self, 'Measurement error', 'Connect to transducer first.')
            return
        if self.is_recording:
            return

        
        custom_name = self.custom_name_input.text().strip() or 'noname'
        test_name = self.selected_test()
        algorithm = algorithm_for(test_name)
        file_path = self.build_record_file_path(test_name, custom_name)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self.record_file = file_path.open('w', newline='', buffering=1)
            self.record_writer = csv.writer(self.record_file)
            self.record_file.write(f'# test: {test_name}\n')
            self.record_file.write(f'# analysis: {algorithm}\n')
            self.record_writer.writerow(('time_s', 'load_n'))
        except OSError as error:
            if self.record_file is not None:
                self.record_file.close()
            self.record_file = None
            self.record_writer = None
            QMessageBox.critical(self, 'Measurement error', f'Cannot open output file: {error}')
            return

        self.record_file_path = file_path
        self.record_start_mono = time.monotonic()
        self.is_recording = True
        self.update_record_controls()
        self.schedule_test_signals()

    def stop_recording(self, open_analysis=None, beep=False):
        if not self.is_recording and self.record_file is None:
            return

        file_path = self.record_file_path
        self.is_recording = False
        self.record_start_mono = None
        if self.record_file is not None:
            self.record_file.close()
        self.record_file = None
        self.record_writer = None
        self.record_file_path = None
        self.cancel_test_signals()
        self.update_record_controls()

        if beep:
            self.schedule_beep(
                STOP_BEEP_FREQUENCY_HZ,
                STOP_BEEP_DURATION_MS,
                STOP_BEEP_DELAY_MS,
            )

        if open_analysis is None:
            open_analysis = self.analyse_after_test.isChecked()
        if file_path is not None and open_analysis:
            self.show_analysis(file_path)

    def open_log(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Open log',
            str(Path('logs').resolve()),
            'CSV files (*.csv)',
        )
        if file_path:
            self.show_analysis(Path(file_path))

    def show_analysis(self, file_path):
        try:
            metadata, data = load_log(file_path)
            test_name = metadata.get('test')
            algorithm = metadata.get('analysis')
            if test_name not in ANALYSES:
                raise ValueError('Unknown or missing test name in log header.')
            if algorithm not in ALGORITHMS:
                raise ValueError('Unknown or missing analysis algorithm in log header.')
            if not data:
                raise ValueError('The log contains no measurement data.')
            metrics = plot_analysis(self.analysis_figure, test_name, data, algorithm)
            append_summary(self.summary_path, file_path, test_name, metrics)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, 'Analysis error', str(error))
            return

        self.analysis_file_label.setText(str(file_path))
        self.tabs.setCurrentIndex(self.analysis_tab_index)

    def on_tab_changed(self, index):
        if index != self.test_tab_index:
            self.stop_recording()
        self.update_polling()

    def update_polling(self):
        if self.tabs.currentIndex() == self.test_tab_index and self.transducer is not None:
            self.start_measurement_worker()
        else:
            self.stop_measurement_worker()

    def update_record_controls(self):
        self.start_button.setEnabled(self.transducer is not None and not self.is_recording)
        self.stop_button.setEnabled(self.is_recording)

    def update_connection_controls(self):
        connected = self.transducer is not None
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.port_combo.setEnabled(not connected)
        self.zero_button.setEnabled(connected)
        self.calibrate_button.setEnabled(connected)

    def connect_transducer(self):
        if self.transducer is not None:
            return
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, 'Connection error', 'No serial port selected.')
            return

        try:
            self.transducer = Transducer(config=ModbusConfig(port=port))
        except Exception as error:
            self.transducer = None
            QMessageBox.critical(self, 'Connection error', str(error))
            return

        self.update_connection_controls()
        self.update_record_controls()
        self.update_polling()

    def disconnect_transducer(self):
        if self.transducer is None:
            return
        self.stop_measurement_worker()
        self.stop_recording()
        self.transducer._modbus_client.close()
        self.transducer = None
        self.update_connection_controls()
        self.update_record_controls()

    def start_measurement_worker(self):
        if self.measurement_worker is not None and self.measurement_worker.isRunning():
            return
        if self.transducer is None:
            return
        self.measurement_worker = MeasurementWorker(self.transducer)
        self.measurement_worker.sample_ready.connect(self.handle_measurement_sample)
        self.measurement_worker.read_error.connect(self.handle_measurement_error)
        self.measurement_worker.start()

    def stop_measurement_worker(self):
        if self.measurement_worker is None:
            return
        self.measurement_worker.stop()
        self.measurement_worker.wait()
        self.measurement_worker = None

    def handle_measurement_sample(self, sample_time, weight):
        force_n = weight / self.SCALE_FACTOR
        load_kg = force_n / self.GRAVITY_CONSTANT
        self.sample_count += 1
        self.measurement_window.append(load_kg)

        if self.is_recording and self.record_writer is not None:
            self.record_writer.writerow((f'{sample_time - self.record_start_mono:.6f}', f'{force_n:.6f}'))

        if len(self.measurement_window) == self.WINDOW_SIZE and self.sample_count % self.WINDOW_SIZE == 0:
            self.current_load_label.setText(f'{sum(self.measurement_window) / self.WINDOW_SIZE:.2f} kg')

    def handle_measurement_error(self, error_text):
        self.stop_measurement_worker()
        self.stop_recording()
        QMessageBox.critical(self, 'Measurement error', error_text)

    def zero_transducer(self):
        if self.transducer is None:
            QMessageBox.warning(self, 'Calibration error', 'Connect to transducer first.')
            return
        try:
            self.transducer.zero_weight()
            QMessageBox.information(self, 'Zero', 'Zeroing completed.')
        except Exception as error:
            QMessageBox.critical(self, 'Calibration error', str(error))

    def calibrate_weight(self):
        if self.transducer is None:
            QMessageBox.warning(self, 'Calibration error', 'Connect to transducer first.')
            return
        weight = int(round(self.weight_input.value() * self.GRAVITY_CONSTANT * self.SCALE_FACTOR))
        try:
            self.transducer.set_weight(weight)
            QMessageBox.information(self, 'Calibration', 'Calibration completed.')
        except Exception as error:
            QMessageBox.critical(self, 'Calibration error', str(error))

    def closeEvent(self, event):
        self.stop_recording(open_analysis=False)
        self.cancel_test_signals()
        self.stop_measurement_worker()
        if self.transducer is not None:
            self.transducer._modbus_client.close()
        if self.session_path.exists() and not any(
            path.is_file() for path in self.session_path.rglob('*')):
            rmtree(self.session_path)
        for sound in self.beep_sounds.values():
            sound.stop()
            sound.setSource(QUrl())
        rmtree(self.beep_directory, ignore_errors=True)
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
