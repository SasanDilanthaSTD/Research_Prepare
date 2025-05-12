import os
import shutil
from queue import Queue
from PyQt5 import QtWidgets, QtCore

class Window(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # UI Elements
        self.button = QtWidgets.QPushButton('Choose Directories')
        self.process_button = QtWidgets.QPushButton('Process Images')
        self.listWidget = QtWidgets.QListWidget()
        self.status_label = QtWidgets.QLabel("Status: Ready")
        self.progress_bar = QtWidgets.QProgressBar()
        
        # Initialize variables
        self.image_queue = Queue()
        self.selected_dirs = []
        self.counter = 1
        
        # Setup layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.listWidget)
        layout.addWidget(self.button)
        layout.addWidget(self.process_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        
        # Connect signals
        self.button.clicked.connect(self.handleChooseDirectories)
        self.process_button.clicked.connect(self.processImages)
        
        # Create temp directory
        self.temp_dir = os.path.join(os.getcwd(), 'temp', 'images')
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Disable process button initially
        self.process_button.setEnabled(False)
        self.progress_bar.setVisible(False)

    def handleChooseDirectories(self):
        dialog = QtWidgets.QFileDialog(self)
        dialog.setWindowTitle('Choose Directories')
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QtWidgets.QFileDialog.DirectoryOnly)
        
        for view in dialog.findChildren((QtWidgets.QListView, QtWidgets.QTreeView)):
            if isinstance(view.model(), QtWidgets.QFileSystemModel):
                view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.listWidget.clear()
            self.selected_dirs = dialog.selectedFiles()
            self.listWidget.addItems(self.selected_dirs)
            self.status_label.setText(f"Status: {len(self.selected_dirs)} directories selected")
            self.process_button.setEnabled(True)
        
        dialog.deleteLater()
    
    def processImages(self):
        if not self.selected_dirs:
            self.status_label.setText("Status: No directories selected")
            return
        
        # Clear previous data
        self.image_queue = Queue()
        self._clear_temp_directory()
        self.counter = 1
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.selected_dirs))
        self.progress_bar.setValue(0)
        
        # Process each directory one by one
        for i, directory in enumerate(self.selected_dirs, 1):
            self.status_label.setText(f"Processing: {os.path.basename(directory)}")
            QtCore.QCoreApplication.processEvents()  # Keep UI responsive
            
            # Add all images from this directory to queue
            self._add_images_to_queue(directory)
            
            # Update progress
            self.progress_bar.setValue(i)
        
        # Now save images from queue to temp folder
        self._save_images_from_queue()
        
        # Update status
        self.status_label.setText(f"Completed: Saved {self.counter-1} images to temp/images")
        self.progress_bar.setVisible(False)
    
    def _add_images_to_queue(self, directory):
        """Recursively find all .TIF files and add to queue"""
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.tif'):
                    file_path = os.path.join(root, file)
                    self.image_queue.put(file_path)
    
    def _save_images_from_queue(self):
        """Save images from queue to temp folder with sequential names"""
        while not self.image_queue.empty():
            src_path = self.image_queue.get()
            new_name = f"image_{self.counter:04d}.tif"
            dest_path = os.path.join(self.temp_dir, new_name)
            shutil.copy2(src_path, dest_path)
            self.counter += 1
    
    def _clear_temp_directory(self):
        """Clear the temp/images directory"""
        for filename in os.listdir(self.temp_dir):
            file_path = os.path.join(self.temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

if __name__ == '__main__':
    app = QtWidgets.QApplication(['Test'])
    window = Window()
    window.setWindowTitle("TIF Image Collector")
    window.resize(500, 400)
    window.show()
    app.exec_()