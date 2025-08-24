import sys
import os
from pathlib import Path
import logging

from src.App.config import Config
from src.App.component.tiff_processor import TiffProcessor
from src.App.component.map_generator import MapGenerator

from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QLabel, QFileDialog, QProgressBar)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QThread, pyqtSignal, QObject, pyqtSlot



class LogEmitter(QObject):
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

class MapGenerationThread(QThread):
    """Thread for running map generation to prevent UI freezing."""
    finished = pyqtSignal(Path)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    # log = pyqtSignal(str, str)  # message, level
    log = pyqtSignal(str)  # just one argument
    
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
            # Step 1: Process the TIFF file
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
                
            # Step 2: Generate the map
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

class MainWindow(QMainWindow):
    """Main application window for sugarcane growth stage visualization."""
    
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.processor = TiffProcessor(self.config)
        self.generator = MapGenerator(self.config)
        
        self.init_ui()
        self.setWindowTitle("Sugarcane Growth Stage Visualizer")
        self.resize(800, 600)
    
    def init_ui(self):
        """Initialize the user interface."""
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Sugarcane Growth Stage Visualizer")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Select Image Button
        self.select_btn = QPushButton("Select UAV Image")
        self.select_btn.clicked.connect(self.select_image)
        layout.addWidget(self.select_btn)
        
        # Process Button
        self.process_btn = QPushButton("Generate Growth Map")
        self.process_btn.clicked.connect(self.process_image)
        self.process_btn.setEnabled(False)
        layout.addWidget(self.process_btn)
        
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # Status Label
        self.status = QLabel()
        self.status.setVisible(False)
        layout.addWidget(self.status)
        
        # Log Display
        self.log_display = QLabel()
        self.log_display.setWordWrap(True)
        self.log_display.setStyleSheet("background-color: #f0f0f0; padding: 5px;")
        layout.addWidget(self.log_display)
        
        # Web View for displaying the map
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
    
    def log_message(self, message: str, level: str = "info"):
        """Display log messages in the UI."""
        current_text = self.log_display.text()
        new_text = f"{message}\n{current_text}"
        self.log_display.setText(new_text)
        
        # Scroll to top
        self.log_display.repaint()
    
    def select_image(self):
        """Open a file dialog to select the UAV image."""
        default_path = str(self.config.temp_dir / "odm_orthophoto" / "odm_orthophoto.tif")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select UAV Image",
            default_path,
            "GeoTIFF Files (*.tif *.tiff)"
        )
        
        if file_path:
            self.image_path = Path(file_path)
            self.process_btn.setEnabled(True)
            self.status.setText(f"Selected: {self.image_path.name}")
            self.status.setVisible(True)
            self.log_message(f"Selected image: {self.image_path.name}")
    
    def process_image(self):
        """Process the selected image and generate the growth stage map."""
        if not hasattr(self, 'image_path'):
            self.log_message("Please select an image first", "warning")
            return
            
        self.select_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText("Processing image...")
        self.log_message("Starting image processing...")
        
        # Create and start the worker thread
        self.worker = MapGenerationThread(
            self.processor,
            self.generator,
            self.image_path,
            self.config
        )
        self.worker.finished.connect(self.on_map_generated)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.log.connect(self.log_message)
        self.worker.start()
    
    def on_map_generated(self, map_path):
        """Handle successful map generation."""
        self.select_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText(f"Map generated successfully: {map_path.name}")
        self.log_message(f"Map saved to: {map_path}")
        
        # Display the generated map
        self.web_view.setUrl(QUrl.fromLocalFile(str(map_path)))
    
    def on_error(self, message):
        """Handle errors during processing."""
        self.select_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText(f"Error: {message}")
        self.log_message(f"Error: {message}", "error")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

# def hello():
#     return "Hello, World!"