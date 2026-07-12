import sys
import time
import os
from collections import deque
from serial.tools import list_ports
from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QLabel,
)

from transducer.modbus_config import ModbusConfig
from transducer.transducer import Transducer, TransducerException
from analysis import AnalysisMode, analyse  # type: ignore[reportMissingImports]


class MeasurementWorker(QThread):
    sample_ready = pyqtSignal(float, float)
    read_error = pyqtSignal(str)

    def __init__(self, transducer):
        super().__init__()
        self._transducer = transducer
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                weight = self._transducer.read_weight()
            except (TransducerException, Exception) as err:
                self.read_error.emit(str(err))
                break
            sample_time = time.monotonic()
            self.sample_ready.emit(sample_time, weight)


class MainWindow(QMainWindow):
    GRAVITY_CONSTANT = 9.805
    SCALE_FACTOR = 100
    WINDOW_SIZE = 20

    def __init__(self):
        super().__init__()
        self.transducer = None
        self.tabs = None
        self.measurement_tab_index = 0
        self.measurement_worker = None
        self.measurement_samples = []
        self.measurement_window = deque(maxlen=self.WINDOW_SIZE)
        self.current_load_label = None
        self.measurement_count_label = None
        self.measurement_latest_label = None
        self.mode_button_group = None
        self.mode_counter_movement_jump = None
        self.mode_triple_hop_test = None
        self.mode_drop_jump = None
        self.custom_name_input = None
        self.start_measurement_button = None
        self.stop_measurement_button = None
        self.is_recording = False
        self.record_start_mono = None
        self.record_file_handle = None
        self.record_file_path = None
        self.port_combo = None
        self.connect_button = None
        self.disconnect_button = None
        self.zero_button = None
        self.calibrate_button = None
        self.weight_input = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Dynamometric platform')
        self.setGeometry(100, 100, 1200, 768)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.measurement_tab_index = self.tabs.addTab(self.measurement_tab(), 'Measurement')
        self.tabs.addTab(self.calibration_tab(), 'Calibration')
        self.tabs.addTab(self.setting_tab(), 'Settings')

        self.update_measurement_polling_state()

    def measurement_tab(self):
        measurement_tab = QWidget()
        measurement_layout = QVBoxLayout()
        measurement_tab.setLayout(measurement_layout)

        self.current_load_label = QLabel('0.00 kg')
        self.current_load_label.setAlignment(Qt.AlignCenter)
        self.current_load_label.setStyleSheet('font-size: 96px; font-weight: bold;')

        mode_row = QHBoxLayout()
        mode_label = QLabel('Mode:')
        self.mode_counter_movement_jump = QRadioButton('Counter movement jump')
        self.mode_triple_hop_test = QRadioButton('Triple hop test')
        self.mode_drop_jump = QRadioButton('Drop jump')
        self.mode_counter_movement_jump.setChecked(True)

        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.addButton(self.mode_counter_movement_jump)
        self.mode_button_group.addButton(self.mode_triple_hop_test)
        self.mode_button_group.addButton(self.mode_drop_jump)

        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_counter_movement_jump)
        mode_row.addWidget(self.mode_triple_hop_test)
        mode_row.addWidget(self.mode_drop_jump)

        name_row = QHBoxLayout()
        name_label = QLabel('Custom name:')
        self.custom_name_input = QLineEdit()
        self.custom_name_input.setPlaceholderText('e.g. athlete_01')
        name_row.addWidget(name_label)
        name_row.addWidget(self.custom_name_input)

        control_row = QHBoxLayout()
        self.start_measurement_button = QPushButton('Start')
        self.stop_measurement_button = QPushButton('Stop')
        self.start_measurement_button.clicked.connect(self.start_recording)
        self.stop_measurement_button.clicked.connect(self.stop_recording)
        self.stop_measurement_button.setEnabled(False)
        control_row.addWidget(self.start_measurement_button)
        control_row.addWidget(self.stop_measurement_button)

        measurement_layout.addLayout(mode_row)
        measurement_layout.addLayout(name_row)
        measurement_layout.addLayout(control_row)
        measurement_layout.addWidget(self.current_load_label)
        measurement_layout.addStretch()

        return measurement_tab

    def calibration_tab(self):
        calibration_tab = QWidget()
        calibration_layout = QVBoxLayout()
        calibration_tab.setLayout(calibration_layout)

        zero_row = QHBoxLayout()
        zero_label = QLabel('Zero the transducer:')
        self.zero_button = QPushButton('Zero')
        self.zero_button.setEnabled(False)
        self.zero_button.clicked.connect(self.zero_transducer)
        zero_row.addWidget(zero_label)
        zero_row.addWidget(self.zero_button)
        calibration_layout.addLayout(zero_row)

        weight_row = QHBoxLayout()
        weight_label = QLabel('Weight:')
        self.weight_input = QDoubleSpinBox()
        self.weight_input.setRange(2.00, 100.00)
        self.weight_input.setDecimals(2)
        self.weight_input.setSingleStep(0.01)
        self.weight_input.setValue(50.00)

        self.calibrate_button = QPushButton('Calibrate Weight')
        self.calibrate_button.setEnabled(False)
        self.calibrate_button.clicked.connect(self.calibrate_weight)

        weight_row.addWidget(weight_label)
        weight_row.addWidget(self.weight_input)
        weight_row.addWidget(self.calibrate_button)
        calibration_layout.addLayout(weight_row)
        calibration_layout.addStretch()

        return calibration_tab

    def setting_tab(self):
        setting_tab = QWidget()
        setting_layout = QVBoxLayout()
        setting_tab.setLayout(setting_layout)

        port_row = QHBoxLayout()
        port_label = QLabel('Serial port:')
        self.port_combo = QComboBox()
        for port in self._get_serial_ports():
            self.port_combo.addItem(port)
        port_row.addWidget(port_label)
        port_row.addWidget(self.port_combo)
        setting_layout.addLayout(port_row)

        buttons_row = QHBoxLayout()
        self.connect_button = QPushButton('Connect')
        self.disconnect_button = QPushButton('Disconnect')
        self.disconnect_button.setEnabled(False)

        self.connect_button.clicked.connect(self.connect_transducer)
        self.disconnect_button.clicked.connect(self.disconnect_transducer)

        buttons_row.addWidget(self.connect_button)
        buttons_row.addWidget(self.disconnect_button)
        setting_layout.addLayout(buttons_row)
        setting_layout.addStretch()

        return setting_tab

    def _get_serial_ports(self):
        return [port.device for port in list_ports.comports()]

    def connect_transducer(self):
        if self.transducer is not None:
            return

        selected_port = self.port_combo.currentText().strip()
        if not selected_port:
            QMessageBox.warning(self, 'Connection error', 'No serial port selected.')
            return

        try:
            config = ModbusConfig(port=selected_port)
            self.transducer = Transducer(config=config)
        except (TransducerException, Exception) as err:
            self.transducer = None
            QMessageBox.critical(self, 'Connection error', str(err))
            return

        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.zero_button.setEnabled(True)
        self.calibrate_button.setEnabled(True)
        self.update_measurement_record_controls()
        self.update_measurement_polling_state()

    def disconnect_transducer(self):
        if self.transducer is None:
            return

        self.stop_measurement_worker()
        
        self.transducer._modbus_client.close()
        self.transducer = None
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.zero_button.setEnabled(False)
        self.calibrate_button.setEnabled(False)
        self.stop_recording()
        self.update_measurement_record_controls()
        self.update_measurement_polling_state()

    def on_tab_changed(self, _index):
        self.update_measurement_polling_state()

    def update_measurement_polling_state(self):
        measurement_is_active = self.tabs.currentIndex() == self.measurement_tab_index
        if measurement_is_active and self.transducer is not None:
            self.start_measurement_worker()
        else:
            self.stop_measurement_worker()
            self.stop_recording()

    def update_measurement_record_controls(self):
        can_start = self.transducer is not None and not self.is_recording
        if self.start_measurement_button is not None:
            self.start_measurement_button.setEnabled(can_start)
        if self.stop_measurement_button is not None:
            self.stop_measurement_button.setEnabled(self.is_recording)

    def selected_mode_name(self):
        return self.selected_mode().value

    def selected_mode(self):
        if self.mode_counter_movement_jump.isChecked():
            return AnalysisMode.COUNTER_MOVEMENT_JUMP
        if self.mode_triple_hop_test.isChecked():
            return AnalysisMode.TRIPLE_HOP_TEST
        return AnalysisMode.DROP_JUMP

    def build_record_file_path(self):
        mode_name = self.selected_mode_name()
        custom_name = self.custom_name_input.text().strip()
        if not custom_name:
            custom_name = 'noname'

        safe_custom_name = ''.join(
            char if char.isalnum() or char in ('-', '_') else '_'
            for char in custom_name
        )
        timestamp = time.strftime('%Y%m%d_%H%S')
        folder_path = os.path.join('logs', mode_name.lower().replace(' ', '_'))
        os.makedirs(folder_path, exist_ok=True)
        file_name = f'{timestamp}_{safe_custom_name}.csv'
        return os.path.join(folder_path, file_name)

    def start_recording(self):
        if self.transducer is None:
            QMessageBox.warning(self, 'Measurement error', 'Connect to transducer first.')
            return

        if self.is_recording:
            return

        try:
            file_path = self.build_record_file_path()
            self.record_file_handle = open(file_path, 'w', buffering=1)
            self.record_file_path = file_path
            self.record_file_handle.write('time,load\n')
        except OSError as err:
            self.record_file_handle = None
            self.record_file_path = None
            QMessageBox.critical(self, 'Measurement error', f'Cannot open output file: {err}')
            return

        self.record_start_mono = time.monotonic()
        self.is_recording = True
        self.update_measurement_record_controls()

    def stop_recording(self):
        if not self.is_recording and self.record_file_handle is None:
            return

        record_file_path = self.record_file_path
        mode = self.selected_mode()
        self.is_recording = False
        self.record_start_mono = None
        if self.record_file_handle is not None:
            self.record_file_handle.close()
            self.record_file_handle = None
        self.record_file_path = None

        if record_file_path:
            data = self.load_recorded_data(record_file_path)
            analyse(mode, data)
        self.update_measurement_record_controls()

    def load_recorded_data(self, file_path):
        data = []
        try:
            with open(file_path, 'r') as csv_file:
                for index, line in enumerate(csv_file):
                    stripped_line = line.strip()
                    if not stripped_line:
                        continue
                    if index == 0:
                        continue
                    parts = stripped_line.split(',')
                    if len(parts) != 2:
                        continue
                    try:
                        timestamp = float(parts[0])
                        load = float(parts[1])
                    except ValueError:
                        continue
                    data.append((timestamp, load))
        except OSError as err:
            QMessageBox.critical(self, 'Measurement error', f'Cannot read output file: {err}')
        return data

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
        self.measurement_samples.append((sample_time, load_kg))
        self.measurement_window.append(load_kg)

        if self.is_recording and self.record_file_handle is not None and self.record_start_mono is not None:
            elapsed_time = sample_time - self.record_start_mono
            self.record_file_handle.write(f'{elapsed_time:.6f},{force_n:.6f}\n')

        window_size = self.measurement_window.maxlen
        if len(self.measurement_window) < window_size:
            return

        if len(self.measurement_samples) % window_size != 0:
            return

        smoothed_load = sum(self.measurement_window) / window_size
        self.current_load_label.setText(f'{smoothed_load:.2f} kg')

    def handle_measurement_error(self, error_text):
        self.stop_measurement_worker()
        QMessageBox.critical(self, 'Measurement error', error_text)

    def zero_transducer(self):
        if self.transducer is None:
            QMessageBox.warning(self, 'Calibration error', 'Connect to transducer first.')
            return

        try:
            self.transducer.zero_weight()
            QMessageBox.information(self, 'Zero', 'Zeroing completed.')
        except (TransducerException, Exception) as err:
            QMessageBox.critical(self, 'Calibration error', str(err))

    def calibrate_weight(self):
        if self.transducer is None:
            QMessageBox.warning(self, 'Calibration error', 'Connect to transducer first.')
            return

        inserted_weight = self.weight_input.value()
        calibration_weight = int(round(inserted_weight * self.GRAVITY_CONSTANT * self.SCALE_FACTOR))

        try:
            self.transducer.set_weight(calibration_weight)
            QMessageBox.information(self, 'Calibration', 'Calibration completed.')
        except (TransducerException, Exception) as err:
            QMessageBox.critical(self, 'Calibration error', str(err))

    def closeEvent(self, event):
        self.stop_recording()
        self.stop_measurement_worker()
        if self.transducer is not None:
            self.transducer._modbus_client.close()
            self.transducer = None
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
