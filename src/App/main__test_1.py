import os
import sys
import shutil
import subprocess
from pathlib import Path
from queue import Queue
import logging

from src.App.config import Config
from src.App.component.tiff_processor import TiffProcessor
from src.App.component.map_generator import MapGenerator

from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QPushButton, QLabel, QFileDialog, QProgressBar, QListWidget, QListWidgetItem, QDialog)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QThread, pyqtSignal, Qt
from PyQt5 import QtWidgets, QtCore

class LogEmitter(QtCore.QObject):
    """Emitter for log messages to be displayed in the UI."""
    log_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
    def emit(self, message: str, level: str = "info"):
        """Emit a log message."""
        self.log_signal.emit(f"[{level.upper()}] {message}")
        if level == "debug":
            self.logger.debug(message)
        elif level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "critical":
            self.logger.critical(message)

class CopyThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, directories, temp_dir):
        super().__init__()
        self.directories = directories
        self.temp_dir = temp_dir
        self.counter = 1

    def run(self):
        try:
            self._clear_temp_directory()
            copied = 0
            for directory in self.directories:
                for root, _, files in os.walk(directory):
                    for file in files:
                        if file.lower().endswith('.tif'):
                            src_path = os.path.join(root, file)
                            ext = os.path.splitext(file)[1]
                            new_name = f"image_{self.counter:04d}{ext}"
                            dest_path = os.path.join(self.temp_dir, new_name)
                            shutil.copy2(src_path, dest_path)
                            self.counter += 1
                            copied += 1
                            self.progress.emit(copied)
                            QtCore.QCoreApplication.processEvents()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _clear_temp_directory(self):
        for filename in os.listdir(self.temp_dir):
            file_path = os.path.join(self.temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                self.log.emit(f"Error deleting {file_path}: {e}")

class ODMThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, project_dir):
        super().__init__()
        self.project_dir = project_dir

    def run(self):
        try:
            command = [
                'docker', 'run', '-ti', '--rm',
                '-v', f"{self.project_dir}:/datasets/code",
                '--memory=16g',
                'opendronemap/odm', 
                '--project-path', '/datasets',
                '--orthophoto-resolution', '5',
                '--feature-quality', 'high'
            ]
            self.log.emit("Starting ODM processing...")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            for line in iter(process.stdout.readline, ''):
                self.log.emit(line.strip())
            process.wait()
            if process.returncode != 0:
                self.error.emit(f"ODM processing failed with exit code {process.returncode}")
            else:
                self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class MapGenerationThread(QThread):
    finished = pyqtSignal(Path)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    log = pyqtSignal(str)

    def __init__(self, processor, generator, image_path, config):
        super().__init__()
        self.processor = processor
        self.generator = generator
        self.image_path = image_path
        self.config = config
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.log.emit)
    
    def run(self):
        try:
            self.progress.emit(25)
            self.log_emitter.emit("Starting image processing", "info")
            
            geojson_path = self.processor.process_field(
                self.image_path,
                self.config.output_dir
            )
            
            if not geojson_path:
                error_msg = "No valid features found in the image."
                self.log_emitter.emit(error_msg, "error")
                self.error.emit(error_msg)
                return
                
            self.progress.emit(75)
            self.log_emitter.emit("Generating interactive map", "info")
            
            map_path = self.generator.generate_map(
                geojson_path,
                self.config.output_dir
            )
            
            self.progress.emit(100)
            self.log_emitter.emit("Map generation completed successfully", "info")
            self.finished.emit(map_path)
        except Exception as e:
            self.log_emitter.emit(f"Error during processing: {str(e)}", "error")
            self.error.emit(str(e))

class MapViewer(QMainWindow):
    def __init__(self, map_path):
        super().__init__()
        self.setWindowTitle("Growth Stage Map Viewer")
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl.fromLocalFile(str(map_path)))
        self.setCentralWidget(self.web_view)
        self.showFullScreen()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.processor = TiffProcessor(self.config)
        self.generator = MapGenerator(self.config)
        
        self.project_dir = os.path.join(os.getcwd(), 'temp')  # Adjust if needed to match user's path
        self.temp_dir = os.path.join(self.project_dir, 'images')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.ortho_path = Path(os.path.join(self.project_dir, 'odm_orthophoto', 'odm_orthophoto.tif'))
        
        self.selected_dirs = []
        
        self.init_ui()
        self.setWindowTitle("Sugarcane Growth Stage Visualizer")
        self.resize(1200, 800)
        self.populate_existing_maps()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        
        # Left sidebar for existing maps
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Existing Maps"))
        self.maps_list = QListWidget()
        self.maps_list.itemClicked.connect(self.open_existing_map)
        left_layout.addWidget(self.maps_list)
        main_layout.addWidget(left_widget, stretch=1)
        
        # Right main area
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Title
        title = QLabel("Sugarcane Growth Stage Visualizer")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        right_layout.addWidget(title)
        
        # Create New Button
        self.create_btn = QPushButton("Create New Growth-Stage Map")
        self.create_btn.setStyleSheet("""
            background-color: #007BFF; color: white; border: none; 
            padding: 15px; border-radius: 5px; font-size: 16px;
        """)
        self.create_btn.clicked.connect(self.start_new_project)
        right_layout.addWidget(self.create_btn)
        
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet("QProgressBar { height: 25px; }")
        right_layout.addWidget(self.progress)
        
        # Status Label
        self.status = QLabel()
        self.status.setVisible(False)
        right_layout.addWidget(self.status)
        
        # Log Display
        self.log_display = QLabel()
        self.log_display.setWordWrap(True)
        self.log_display.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        right_layout.addWidget(self.log_display, stretch=1)
        
        main_layout.addWidget(right_widget, stretch=3)
        self.setCentralWidget(central_widget)

    def populate_existing_maps(self):
        self.maps_list.clear()
        for map_path in sorted(self.config.output_dir.glob("*.html")):
            item = QListWidgetItem(map_path.name)
            item.setData(Qt.UserRole, str(map_path))
            self.maps_list.addItem(item)

    def open_existing_map(self, item):
        map_path = Path(item.data(Qt.UserRole))
        viewer = MapViewer(map_path)
        viewer.show()

    def start_new_project(self):
        self.create_btn.setEnabled(False)
        self.handle_choose_directories()

    def handle_choose_directories(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle('Choose Directories')
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        
        for view in dialog.findChildren((QtWidgets.QListView, QtWidgets.QTreeView)):
            if isinstance(view.model(), QtWidgets.QFileSystemModel):
                view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        
        if dialog.exec_() == QDialog.Accepted:
            self.selected_dirs = dialog.selectedFiles()
            if self.selected_dirs:
                self.start_copy_images()
        else:
            self.create_btn.setEnabled(True)

        dialog.deleteLater()

    def start_copy_images(self):
        total_files = 0
        for directory in self.selected_dirs:
            for root, _, files in os.walk(directory):
                total_files += sum(1 for file in files if file.lower().endswith('.tif'))

        if total_files == 0:
            self.log_message("No .TIF images found in selected directories.")
            self.create_btn.setEnabled(True)
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, total_files)
        self.progress.setValue(0)
        self.status.setText("Copying images to temp directory...")
        self.status.setVisible(True)

        self.copy_worker = CopyThread(self.selected_dirs, self.temp_dir)
        self.copy_worker.progress.connect(self.progress.setValue)
        self.copy_worker.finished.connect(self.on_copy_finished)
        self.copy_worker.error.connect(self.on_error)
        self.copy_worker.log.connect(self.log_message)
        self.copy_worker.start()

    def on_copy_finished(self):
        self.log_message("Image copying completed. Starting ODM processing...")
        self.start_odm_processing()

    def start_odm_processing(self):
        self.progress.setRange(0, 0)  # Busy mode
        self.status.setText("Running ODM processing (this may take a while)...")

        self.odm_worker = ODMThread(self.project_dir)
        self.odm_worker.finished.connect(self.on_odm_finished)
        self.odm_worker.error.connect(self.on_error)
        self.odm_worker.log.connect(self.log_message)
        self.odm_worker.start()

    def on_odm_finished(self):
        self.log_message("ODM processing completed. Starting map generation...")
        self.image_path = self.ortho_path
        if not self.image_path.exists():
            self.on_error("Orthophoto not found after ODM processing.")
            return
        self.start_map_generation()

    def start_map_generation(self):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText("Generating growth stage map...")

        self.map_worker = MapGenerationThread(
            self.processor,
            self.generator,
            self.image_path,
            self.config
        )
        self.map_worker.finished.connect(self.on_map_generated)
        self.map_worker.error.connect(self.on_error)
        self.map_worker.progress.connect(self.progress.setValue)
        self.map_worker.log.connect(self.log_message)
        self.map_worker.start()

    def on_map_generated(self, map_path):
        self.create_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText(f"Map generated successfully: {map_path.name}")
        self.log_message(f"Map saved to: {map_path}")
        
        # Add to existing maps
        self.populate_existing_maps()
        
        # Open in full-screen viewer
        viewer = MapViewer(map_path)
        viewer.show()

    def on_error(self, message):
        self.create_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText(f"Error: {message}")
        self.log_message(f"Error: {message}", "error")

    def log_message(self, message: str, level: str = "info"):
        current_text = self.log_display.text()
        new_text = f"[{level.upper()}] {message}\n{current_text}"
        self.log_display.setText(new_text)
        self.log_display.repaint()

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget { font-family: Arial; font-size: 14px; }
        QPushButton:hover { background-color: #0056D2; }
        QProgressBar { background-color: #E9ECEF; border-radius: 5px; text-align: center; }
        QProgressBar::chunk { background-color: #007BFF; border-radius: 5px; }
    """)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()