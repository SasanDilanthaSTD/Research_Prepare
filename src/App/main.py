from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                             QFileDialog, QLabel, QMessageBox)
from odm_processor import run_odm
from tiff_processor import generate_ndvi
import os

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJI Phantom 4 Multispectral Processor")
        self.setGeometry(100, 100, 400, 200)
        
        self.layout = QVBoxLayout()
        
        # Input folder selection
        self.btn_select = QPushButton("Select Image Folder")
        self.btn_select.clicked.connect(self.select_folder)
        self.layout.addWidget(self.btn_select)
        
        # Process button
        self.btn_process = QPushButton("Run Processing")
        self.btn_process.clicked.connect(self.run_processing)
        self.layout.addWidget(self.btn_process)
        
        # Status label
        self.label_status = QLabel("Ready.")
        self.layout.addWidget(self.label_status)
        
        self.setLayout(self.layout)
        self.image_dir = ""
    
    def select_folder(self):
        self.image_dir = QFileDialog.getExistingDirectory(self, "Select DJI Images Folder")
        self.label_status.setText(f"Selected: {self.image_dir}")
    
    def run_processing(self):
        if not self.image_dir:
            QMessageBox.warning(self, "Error", "No folder selected!")
            return
        
        try:
            self.label_status.setText("Running ODM...")
            QApplication.processEvents()  # Update GUI
            
            # Step 1: Run ODM (Docker)
            run_odm(self.image_dir)
            
            # Step 2: Generate NDVI
            red_band = os.path.join(self.image_dir, "DJI_0001_R.TIFF")
            nir_band = os.path.join(self.image_dir, "DJI_0001_NIR.TIFF")
            generate_ndvi(red_band, nir_band, "ndvi.tif")
            
            QMessageBox.information(self, "Success", "Processing completed! Check output files.")
            self.label_status.setText("Done.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed: {str(e)}")
            self.label_status.setText("Error.")

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()