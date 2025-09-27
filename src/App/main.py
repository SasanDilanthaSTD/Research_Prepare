import os
import sys
import shutil
import subprocess
from pathlib import Path
from queue import Queue
import logging
from datetime import datetime
from src.App.config import Config
from src.App.component.tiff_processor import TiffProcessor
from src.App.component.map_generator import MapGenerator
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
                             QPushButton, QLabel, QFileDialog, QProgressBar, QListWidget, QListWidgetItem, QDialog, QComboBox, QMessageBox, QTextEdit, QSplitter, QStackedWidget, QGraphicsDropShadowEffect)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QObject, QThread, pyqtSignal, Qt, QUrl, QPropertyAnimation, QSequentialAnimationGroup
from PyQt5.QtGui import QTextCursor, QPixmap, QIcon, QFont
from PyQt5 import QtCore, QtWidgets

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
            total_files = sum(1 for dir in self.directories for root, _, files in os.walk(dir) for file in files if file.lower().endswith(('.tif', '.tiff')))
            for directory in self.directories:
                for root, _, files in os.walk(directory):
                    for file in files:
                        if file.lower().endswith(('.tif', '.tiff')): # Only copy .tif and .tiff files
                            src_path = os.path.join(root, file)
                            ext = os.path.splitext(file)[1]
                            new_name = f"image_{self.counter:04d}{ext}"
                            dest_path = os.path.join(self.temp_dir, new_name)
                            shutil.copy2(src_path, dest_path)
                            self.counter += 1
                            copied += 1
                            self.progress.emit(int(copied / total_files * 100))
                            self.log.emit(f"Copied {file} to temp directory")
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
    def __init__(self, project_dir, quality):
        super().__init__()
        self.project_dir = project_dir.replace('\\', '/')
        self.quality = quality
    def run(self):
        try:
            feature_quality = {
                'high': 'high',
                'medium': 'medium',
                'low': 'low'
            }.get(self.quality, 'medium')
           
            pc_quality = {
                'high': 'high',
                'medium': 'medium',
                'low': 'low'
            }.get(self.quality, 'medium')
           
            max_concurrency = {
                'high': 8,
                'medium': 4,
                'low': 2
            }.get(self.quality, 4)
           
            min_num_features = {
                'high': 12000,
                'medium': 8000,
                'low': 6000
            }.get(self.quality, 8000)
           
            feature_type = {
                'high': 'sift',
                'medium': 'sift',
                'low': 'orb'
            }.get(self.quality, 'sift')
            command = [
                'docker', 'run', '--rm',
                '-v', f"{self.project_dir}:/datasets/code",
                'opendronemap/odm',
                '--project-path', '/datasets',
                '--orthophoto-resolution', '5',
                '--feature-quality', feature_quality,
                '--pc-quality', pc_quality,
                '--max-concurrency', str(max_concurrency),
                '--min-num-features', str(min_num_features),
                '--ignore-gsd',
                '--feature-type', feature_type,
                '--skip-3dmodel', # Skip meshing to avoid memory issues
                'code'
            ]
            self.log.emit(f"Starting ODM processing with {self.quality} quality...")
            self.log.emit("Command: " + ' '.join(command))
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
           
            # Generate map name with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            map_name = f"sugarcane_growth_map_{timestamp}.html"
           
            map_path = self.generator.generate_map(
                geojson_path,
                self.config.output_dir,
                map_name=map_name
            )
           
            self.progress.emit(100)
            self.log_emitter.emit("Map generation completed successfully", "info")
            self.finished.emit(map_path)
        except Exception as e:
            self.log_emitter.emit(f"Error during processing: {str(e)}", "error")
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.processor = TiffProcessor(self.config)
        self.generator = MapGenerator(self.config)
       
        self.project_dir = os.path.join(os.getcwd(), 'temp') # Adjust if needed to match user's path
        self.temp_dir = os.path.join(self.project_dir, 'images')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.ortho_path = Path(os.path.join(self.project_dir, 'odm_orthophoto', 'odm_orthophoto.tif'))
       
        self.selected_dirs = []
        self.quality = 'medium' # Default
        self.current_preview_map = None
        self.current_preview_item = None
       
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.logo_path = os.path.join(script_dir, 'resource', 'temp_logo.png')
       
        self.init_ui()
        self.setWindowTitle("Sugarcane Growth Stage Visualizer")
        self.resize(1200, 800)
        self.populate_existing_maps()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
       
        # Create splitter for resizable left and right panels
        splitter = QSplitter(Qt.Horizontal)
       
        # Left sidebar for existing maps
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_title = QLabel("Existing Maps")
        left_title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        left_layout.addWidget(left_title)
        self.maps_list = QListWidget()
        self.maps_list.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e6f2ff;
                color: #007BFF;
            }
        """)
        self.maps_list.itemClicked.connect(self.preview_existing_map)
        left_layout.addWidget(self.maps_list)
       
        # Right main area - using stacked widget to switch between main view and preview
        self.right_stacked = QStackedWidget()
       
        # Page 0: Main controls view
        self.main_view = QWidget()
        main_view_layout = QVBoxLayout(self.main_view)
       
        # Header with logo and title
        header_layout = QHBoxLayout()
        if os.path.exists(self.logo_path):
            logo_label = QLabel()
            pixmap = QPixmap(self.logo_path)
            pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
            header_layout.addWidget(logo_label)
        title = QLabel("Sugarcane Growth Stage Visualizer")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        main_view_layout.addLayout(header_layout)
       
        # Quality selection
        quality_layout = QHBoxLayout()
        quality_label = QLabel("ODM Processing Quality:")
        quality_label.setStyleSheet("font-size: 16px; padding: 5px;")
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['high', 'medium', 'low'])
        self.quality_combo.setCurrentText(self.quality)
        self.quality_combo.setStyleSheet("""
            QComboBox {
                background-color: white;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 8px;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border-left: 1px solid #ced4da;
            }
        """)
        self.quality_combo.setToolTip("Select the processing quality. Higher quality may take longer and use more resources.")
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        main_view_layout.addLayout(quality_layout)
       
        # Create New Button
        self.create_btn = QPushButton("Create New Growth-Stage Map")
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #007BFF;
                color: white;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056D2;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(Qt.gray)
        shadow.setOffset(2, 2)
        self.create_btn.setGraphicsEffect(shadow)
        self.create_btn.setToolTip("Start the process to create a new growth-stage map by selecting directories with TIFF images.")
        self.create_btn.clicked.connect(self.start_new_project)
        main_view_layout.addWidget(self.create_btn)
       
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #E9ECEF;
                border-radius: 5px;
                text-align: center;
                height: 25px;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 5px;
            }
        """)
        main_view_layout.addWidget(self.progress)
       
        # Status Label
        self.status = QLabel()
        self.status.setVisible(False)
        self.status.setStyleSheet("font-size: 14px; color: #6c757d; padding: 10px;")
        main_view_layout.addWidget(self.status)
       
        # Log Display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 10px;
                font-family: Consolas, monospace;
                font-size: 13px;
            }
        """)
        main_view_layout.addWidget(self.log_display, stretch=1)
       
        # Page 1: Preview view
        self.preview_view_widget = QWidget()
        preview_layout = QVBoxLayout(self.preview_view_widget)
       
        # Preview controls
        preview_controls_layout = QHBoxLayout()
        if os.path.exists(self.logo_path):
            logo_label_preview = QLabel()
            pixmap_preview = QPixmap(self.logo_path)
            pixmap_preview = pixmap_preview.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label_preview.setPixmap(pixmap_preview)
            preview_controls_layout.addWidget(logo_label_preview)
        self.home_btn = QPushButton("← Home")
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self.home_btn.setToolTip("Return to the main view")
        self.home_btn.clicked.connect(self.show_main_view)
       
        self.delete_btn = QPushButton("🗑️ Delete Map")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.delete_btn.setToolTip("Delete the currently previewed map")
        self.delete_btn.clicked.connect(self.delete_current_map)
       
        preview_controls_layout.addWidget(self.home_btn)
        preview_controls_layout.addWidget(self.delete_btn)
        preview_controls_layout.addStretch()
        preview_layout.addLayout(preview_controls_layout)
       
        # Preview web view
        self.preview_web_view = QWebEngineView()
        self.preview_web_view.setUrl(QUrl("about:blank"))
        preview_layout.addWidget(self.preview_web_view)
       
        # Add both views to stacked widget
        self.right_stacked.addWidget(self.main_view)
        self.right_stacked.addWidget(self.preview_view_widget)
       
        # Initially show main view
        self.right_stacked.setCurrentIndex(0)
       
        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(self.right_stacked)
       
        # Set splitter proportions (1:3 ratio)
        splitter.setSizes([300, 900])
       
        main_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)

        # Add fade animation for stacked widget transitions
        self.fade_animation = QPropertyAnimation(self.right_stacked, b"opacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)

    def show_main_view(self):
        """Switch back to main controls view with fade"""
        self._fade_transition(0)
        self.current_preview_map = None
        self.current_preview_item = None

    def show_preview_view(self):
        """Switch to preview view with fade"""
        self._fade_transition(1)

    def _fade_transition(self, index):
        """Helper for fade transition"""
        self.fade_animation.stop()
        self.right_stacked.setCurrentIndex(index)
        self.fade_animation.start()

    def populate_existing_maps(self):
        self.maps_list.clear()
        for map_path in sorted(self.config.output_dir.glob("*.html"), key=os.path.getmtime, reverse=True):  # Sort by modification time, newest first
            item = QListWidgetItem(map_path.name)
            item.setData(Qt.UserRole, str(map_path))
            item.setToolTip(str(map_path))
            self.maps_list.addItem(item)

    def preview_existing_map(self, item):
        """Preview the selected map in the right panel"""
        map_path = Path(item.data(Qt.UserRole))
        self.current_preview_map = map_path
        self.current_preview_item = item
       
        # Load the map in the preview view
        self.preview_web_view.setUrl(QUrl.fromLocalFile(str(map_path)))
       
        # Switch to preview view
        self.show_preview_view()
       
        # Update status
        self.status.setText(f"Previewing: {map_path.name}")
        self.status.setVisible(True)

    def delete_current_map(self):
        """Delete the currently previewed map with confirmation"""
        if not self.current_preview_map or not self.current_preview_item:
            return
           
        map_path = self.current_preview_map
        map_name = map_path.name
       
        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            'Confirm Deletion',
            f'Are you sure you want to delete "{map_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
       
        if reply == QMessageBox.Yes:
            try:
                # Delete the map file
                if map_path.exists():
                    map_path.unlink()
                    self.log_message(f"Deleted map: {map_name}")
               
                # Remove from list widget
                row = self.maps_list.row(self.current_preview_item)
                self.maps_list.takeItem(row)
               
                # Also delete associated files (JSON, etc.)
                base_name = map_path.stem
                for file_type in ['.json', '.geojson']:
                    associated_file = map_path.parent / f"{base_name}{file_type}"
                    if associated_file.exists():
                        associated_file.unlink()
                        self.log_message(f"Deleted associated file: {associated_file.name}")
               
                # Switch back to main view
                self.show_main_view()
               
                # Clear current preview references
                self.current_preview_map = None
                self.current_preview_item = None
               
                self.status.setText(f"Map deleted successfully: {map_name}")
               
            except Exception as e:
                error_msg = f"Error deleting map: {str(e)}"
                self.log_message(error_msg, "error")
                QMessageBox.warning(self, "Deletion Error", error_msg)

    def start_new_project(self):
        self.quality = self.quality_combo.currentText()
        self.create_btn.setEnabled(False)
        self.handle_choose_directories()

    def handle_choose_directories(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle('Choose Directories with TIFF Images')
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
        total_files = sum(1 for directory in self.selected_dirs for root, _, files in os.walk(directory) for file in files if file.lower().endswith(('.tif', '.tiff')))
        if total_files == 0:
            self.log_message("No .TIF or .TIFF images found in selected directories.")
            self.create_btn.setEnabled(True)
            return
        if total_files > 500:
            msg = f"Large dataset detected ({total_files} images). This may require significant memory and time.\nRecommended quality: low\nProceed?"
            reply = QMessageBox.question(self, 'Warning', msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                self.create_btn.setEnabled(True)
                return
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
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
        self.progress.setRange(0, 0) # Busy mode
        self.start_odm_processing()

    def start_odm_processing(self):
        self.status.setText("Running ODM processing (this may take a while)...")
        self.odm_worker = ODMThread(self.project_dir, self.quality)
        self.odm_worker.finished.connect(self.on_odm_finished)
        self.odm_worker.error.connect(self.on_error)
        self.odm_worker.log.connect(self.log_message)
        self.odm_worker.start()

    def on_odm_finished(self):
        self.log_message("ODM processing completed. Starting map generation...")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        if not self.ortho_path.exists():
            self.on_error("Orthophoto not found after ODM processing.")
            return
        self.start_map_generation()

    def start_map_generation(self):
        self.status.setText("Generating growth stage map...")
        self.map_worker = MapGenerationThread(
            self.processor,
            self.generator,
            self.ortho_path,
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
       
        # Add to existing maps and preview it
        self.populate_existing_maps()
       
        # Find and select the new map in the list
        for i in range(self.maps_list.count()):
            item = self.maps_list.item(i)
            if Path(item.data(Qt.UserRole)) == map_path:
                self.maps_list.setCurrentItem(item)
                self.preview_existing_map(item)
                break

    def on_error(self, message):
        self.create_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText(f"Error: {message}")
        self.log_message(f"Error: {message}", "error")

    def log_message(self, message: str, level: str = "info"):
        new_text = f"[{level.upper()}] {message}\n"
        self.log_display.insertPlainText(new_text)
        self.log_display.moveCursor(QTextCursor.End)

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for a more modern look
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(script_dir, 'resource', 'temp_logo.png')
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))  # Set logo for application execution
    app.setStyleSheet("""
        QWidget {
            font-family: 'Segoe UI', Arial;
            font-size: 14px;
            background-color: #f0f4f8;
        }
        QMainWindow {
            background-color: #f0f4f8;
        }
        QLabel {
            color: #212529;
        }
        QPushButton:hover {
            background-color: #0056D2;
        }
        QPushButton[background-color="#dc3545"]:hover {
            background-color: #c82333;
        }
        QProgressBar {
            background-color: #E9ECEF;
            border-radius: 5px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #007BFF;
            border-radius: 5px;
        }
        QSplitter::handle {
            background-color: #dee2e6;
            width: 5px;
        }
        QSplitter::handle:hover {
            background-color: #ced4da;
        }
    """)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()