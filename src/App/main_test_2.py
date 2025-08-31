import sys
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QLabel, QFileDialog, QLineEdit, QMessageBox, QHBoxLayout,
    QProgressBar
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QThread, pyqtSignal, QObject
import logging

# Append the project root to the sys path for proper module imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from src.App.config.config import Config
from src.App.component.tiff_processor import TiffProcessor
from src.App.component.map_generator import MapGenerator

# Setting up logging for this main file
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Worker(QObject):
    """
    A worker QObject to handle heavy-duty tasks in a separate thread.
    This includes running the ODM Docker container and processing the images.
    """
    # Signals to communicate with the main thread
    processing_status = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, input_folders: List[str], config: Config, tiff_processor: TiffProcessor, map_generator: MapGenerator):
        super().__init__()
        self.input_folders = [Path(f) for f in input_folders]
        self.config = config
        self.tiff_processor = tiff_processor
        self.map_generator = map_generator

    def run_process(self):
        """
        The main orchestration function for the worker thread.
        This method manages the entire process flow: copying files,
        running ODM via Docker, and generating the final map for each folder.
        """
        try:
            for i, input_folder in enumerate(self.input_folders):
                self.processing_status.emit(f"Processing folder {i+1} of {len(self.input_folders)}: {input_folder.name}")

                # Step 1: Prepare the temporary directory for ODM
                self.processing_status.emit("Preparing folders for ODM...")
                odm_workspace = self.config.temp_dir
                if odm_workspace.exists():
                    shutil.rmtree(odm_workspace)
                odm_workspace.mkdir(parents=True, exist_ok=True)
                
                # Step 2: Copy image files to the temporary folder
                self.processing_status.emit(f"Copying images from '{input_folder.name}' to '{odm_workspace}'...")
                
                if not any(input_folder.iterdir()):
                    self.error.emit(f"The selected folder '{input_folder}' is empty.")
                    return

                for file_path in input_folder.iterdir():
                    if file_path.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png']:
                        shutil.copy(file_path, odm_workspace)
                
                # Step 3: Execute ODM using Docker with the specified optimized command
                self.processing_status.emit("Starting ODM Docker process. This may take a while...")
                
                odm_host_path = Path(str(self.config.temp_dir)).parent
                
                docker_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{odm_host_path}:/datasets/code",
                    "opendronemap/odm",
                    "--project-path", "/datasets",
                    "--orthophoto-resolution", "5",
                    "--feature-quality", "high"
                ]
                
                logger.info("Running Docker command: %s", " ".join(docker_cmd))
                
                process = subprocess.Popen(
                    docker_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                for line in process.stdout:
                    logger.info(line.strip())
                    self.processing_status.emit(f"ODM: {line.strip()}")
                
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    error_msg = f"ODM Docker process failed. Exit code: {process.returncode}\nError: {stderr}"
                    self.error.emit(error_msg)
                    return

                self.processing_status.emit("ODM process completed. Retrieving output...")
                
                odm_output_geotiff = self.config.temp_dir / "odm_orthophoto" / "odm_orthophoto.tif"
                if not odm_output_geotiff.exists():
                    error_msg = f"ODM output file not found: {odm_output_geotiff}"
                    self.error.emit(error_msg)
                    return

                # Step 4: Process the GeoTIFF and generate the map using your classes
                self.processing_status.emit("Generating growth stage map from GeoTIFF...")
                geojson_path = self.tiff_processor.process_field(odm_output_geotiff)
                
                if not geojson_path:
                    self.error.emit("Failed to create GeoJSON from the GeoTIFF.")
                    return

                map_path = self.map_generator.generate_map(geojson_path, output_dir=self.config.temp_map_dir)
                
                if not map_path:
                    self.error.emit("Failed to generate the HTML map.")
                    return

                # Step 5: Clean up temporary files
                self.processing_status.emit("Cleaning up temporary files...")
                if odm_workspace.exists():
                    shutil.rmtree(odm_workspace)
            
            self.finished.emit("All folders processed.")

        except FileNotFoundError:
            self.error.emit("Docker command not found. Please ensure Docker is installed and in your system's PATH.")
        except subprocess.CalledProcessError as e:
            self.error.emit(f"Subprocess call failed: {e}")
        except Exception as e:
            logger.exception("An unexpected error occurred during processing.")
            self.error.emit(f"An unexpected error occurred: {str(e)}")


class MainWindow(QMainWindow):
    """
    Main application window for the Sugar Cane Growth Stage App.
    Handles UI, user interaction, and communication with the worker thread.
    """
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.tiff_processor = TiffProcessor(self.config)
        self.map_generator = MapGenerator(self.config)
        self.thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self.selected_folders: List[str] = []
        
        self.init_ui()
        logger.info("Main window UI initialized.")

    def init_ui(self):
        """
        Sets up the main window's layout and widgets.
        """
        self.setWindowTitle("Drone Image Growth Stage App")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # UI for folder selection
        folder_layout = QHBoxLayout()
        self.folder_path_input = QLineEdit()
        self.folder_path_input.setPlaceholderText("Select one or more folders of multispectral images...")
        self.folder_path_input.setReadOnly(True)
        self.browse_button = QPushButton("Browse Folders")
        self.browse_button.clicked.connect(self.browse_folders)
        folder_layout.addWidget(self.folder_path_input)
        folder_layout.addWidget(self.browse_button)

        # UI for processing
        self.process_button = QPushButton("Start Processing")
        self.process_button.clicked.connect(self.start_processing)
        self.process_button.setEnabled(False)

        # Status and map viewer
        self.status_label = QLabel("Ready. Please select one or more folders.")
        self.status_label.setStyleSheet("font-style: italic; color: #555;")
        self.map_viewer = QWebEngineView()
        self.map_viewer.setHtml("<h1>Welcome!</h1><p>Select one or more folders containing drone images and click 'Start Processing' to generate growth stage maps.</p>")

        # Add widgets to the main layout
        main_layout.addLayout(folder_layout)
        main_layout.addWidget(self.process_button)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.map_viewer)

    def browse_folders(self):
        """
        Opens a folder dialog for the user to select multiple input folders.
        """
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setWindowTitle("Select Folders Containing Images")

        # This option enables multiple directory selection
        dialog.setOptions(dialog.options() | QFileDialog.ShowDirsOnly | QFileDialog.ReadOnly)
        
        # Get the native view to add the multi-selection option
        for view in dialog.findChildren(QMessageBox):
            if isinstance(view, QMessageBox):
                view.setStyleSheet("QFileDialog::item:selected { background-color: blue; }")

        if dialog.exec_():
            self.selected_folders = dialog.selectedFiles()
            if self.selected_folders:
                self.folder_path_input.setText(", ".join(self.selected_folders))
                self.process_button.setEnabled(True)
                self.status_label.setText(f"{len(self.selected_folders)} folder(s) selected. Click 'Start Processing' to begin.")
                logger.info(f"Folders selected: {self.selected_folders}")

    def start_processing(self):
        """
        Initiates the processing flow by starting a worker thread.
        """
        if not self.selected_folders:
            self.show_message_box("Error", "Please select one or more valid folders.")
            return

        self.process_button.setEnabled(False)
        self.status_label.setText("Preparing and running ODM via Docker...")
        
        # Create the worker and thread
        self.thread = QThread()
        self.worker = Worker(self.selected_folders, self.config, self.tiff_processor, self.map_generator)
        self.worker.moveToThread(self.thread)

        # Connect signals and slots
        self.thread.started.connect(self.worker.run_process)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.error.connect(self.on_processing_error)
        self.worker.processing_status.connect(self.status_label.setText)

        # Clean up when the thread finishes
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.worker.deleteLater)

        self.thread.start()
        logger.info("Processing thread started.")

    def on_processing_finished(self, map_path: str):
        """
        Slot to handle successful completion of the worker thread.
        Loads the generated map into the web view.
        """
        logger.info(f"Processing finished. Map saved to {map_path}")
        self.status_label.setText("All processing complete. Loading map...")
        
        local_url = QUrl.fromLocalFile(os.path.abspath(map_path))
        self.map_viewer.load(local_url)
        self.map_viewer.loadFinished.connect(
            lambda: self.status_label.setText("Maps loaded successfully. Double-click on the map to interact.")
        )
        self.process_button.setEnabled(True)

    def on_processing_error(self, error_message: str):
        """
        Slot to handle errors from the worker thread.
        Displays an error message and re-enables the UI.
        """
        logger.error(f"Processing error: {error_message}")
        self.status_label.setText(f"Error: {error_message}")
        self.show_message_box("Processing Error", error_message)
        self.process_button.setEnabled(True)

    def show_message_box(self, title: str, message: str):
        """
        Utility function to display a message box.
        """
        msg_box = QMessageBox()
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()


def main():
    try:
        # Check if Docker is available
        subprocess.run(["docker", "info"], check=True, capture_output=True)
        
        # Check if the ODM image exists. If not, inform the user.
        result = subprocess.run(
            ["docker", "image", "ls", "-q", "opendronemap/odm"],
            capture_output=True,
            text=True
        )
        if not result.stdout.strip():
            logger.warning("ODM Docker image not found. Please install it with 'docker pull opendronemap/odm' for this app to function.")
    except FileNotFoundError:
        error_msg = (
            "Docker is not installed or not in your system's PATH. "
            "Please ensure Docker is installed and accessible via your command line."
        )
        print(error_msg, file=sys.stderr)
        logger.error(error_msg)
        sys.exit(1)
    except subprocess.CalledProcessError:
        error_msg = "Docker is not running. Please start the Docker service."
        print(error_msg, file=sys.stderr)
        logger.error(error_msg)
        sys.exit(1)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
