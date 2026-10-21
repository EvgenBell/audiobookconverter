"""
Artwork tab for AudioBookConverter.
"""
import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QGroupBox, QStyle
)
from PySide6.QtCore import Qt, Signal, QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QImage

from core.models import Artwork
from i18n.translator import tr


class ArtworkTab(QWidget):
    """Tab for managing cover artwork."""

    artwork_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._artwork: Optional[Artwork] = None
        self._max_size = 1000

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)

        # Preview group
        preview_group = QGroupBox(tr("artwork.preview"))
        self.preview_group = preview_group
        preview_layout = QVBoxLayout(preview_group)

        # Image preview
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setMaximumSize(400, 400)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setObjectName("coverPreview")
        self.preview_label.setText(tr("artwork.no_image"))
        self.preview_label.setScaledContents(False)

        preview_layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)

        # Info label
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.info_label)

        layout.addWidget(preview_group)

        # Buttons
        btn_layout = QHBoxLayout()

        self.select_btn = QPushButton(tr("artwork.select_image"))
        self.remove_btn = QPushButton(tr("artwork.remove_image"))
        self.select_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.remove_btn.setEnabled(False)

        btn_layout.addWidget(self.select_btn)
        btn_layout.addWidget(self.remove_btn)

        layout.addLayout(btn_layout)

        # Size info
        self.size_info = QLabel(tr("artwork.resize_info", size=self._max_size))
        self.size_info.setObjectName("muted")
        layout.addWidget(self.size_info)

        # Add stretch
        layout.addStretch()

    def retranslate_ui(self) -> None:
        self.preview_group.setTitle(tr("artwork.preview"))
        self.select_btn.setText(tr("artwork.select_image"))
        self.remove_btn.setText(tr("artwork.remove_image"))
        self.size_info.setText(tr("artwork.resize_info", size=self._max_size))
        if not self._artwork:
            self.preview_label.setText(tr("artwork.no_image"))

    def _connect_signals(self) -> None:
        """Connect signals."""
        self.select_btn.clicked.connect(self._select_image)
        self.remove_btn.clicked.connect(self._remove_image)

    def _select_image(self) -> None:
        """Open file dialog to select an image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialogs.select_image"),
            "",
            f"{tr('artwork.images')} (*.jpg *.jpeg *.png)"
        )

        if file_path:
            self._load_image(file_path)

    def _load_image(self, file_path: str) -> None:
        """Load an image file."""
        if not os.path.exists(file_path):
            return

        # Create artwork object
        self._artwork = Artwork(path=file_path)

        # Load and display preview
        pixmap = QPixmap(file_path)

        if pixmap.isNull():
            self._show_error(tr("artwork.load_error"))
            return

        # Get dimensions
        self._artwork.width = pixmap.width()
        self._artwork.height = pixmap.height()

        # Determine mime type
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".png":
            self._artwork.mime_type = "image/png"
        else:
            self._artwork.mime_type = "image/jpeg"

        # Scale for preview
        scaled = pixmap.scaled(
            300, 300,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.preview_label.setPixmap(scaled)
        self.preview_label.setObjectName("coverPreview")

        # Update info
        self.info_label.setText(
            f"{pixmap.width()} x {pixmap.height()} px"
        )

        self.remove_btn.setEnabled(True)
        self.artwork_changed.emit()

    def _remove_image(self) -> None:
        """Remove the current artwork."""
        self._artwork = None

        self.preview_label.clear()
        self.preview_label.setText(tr("artwork.no_image"))
        self.preview_label.setObjectName("coverPreview")

        self.info_label.clear()
        self.remove_btn.setEnabled(False)
        self.artwork_changed.emit()

    def _show_error(self, message: str) -> None:
        """Show an error message."""
        self.preview_label.setText(f"❌ {message}")
        self._artwork = None
        self.remove_btn.setEnabled(False)

    def get_artwork(self) -> Optional[Artwork]:
        """Get the current artwork."""
        if self._artwork and max(self._artwork.width, self._artwork.height) > self._max_size:
            image = (QImage.fromData(self._artwork.embedded_data) if self._artwork.embedded_data
                     else QImage(self._artwork.path))
            if image.isNull():
                raise ValueError(tr("artwork.read_error"))
            image = image.scaled(self._max_size, self._max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            if not image.save(buffer, "PNG"):
                raise ValueError(tr("artwork.resize_error"))
            return Artwork(embedded_data=bytes(buffer.data()), mime_type="image/png",
                           width=image.width(), height=image.height())
        return self._artwork

    def set_artwork(self, artwork: Artwork) -> None:
        """Set the artwork."""
        if artwork.embedded_data:
            self._load_from_data(artwork.embedded_data)
        elif artwork.path and os.path.exists(artwork.path):
            self._load_image(artwork.path)
        else:
            self.clear()
            self._artwork = artwork

    def _load_from_data(self, data: bytes) -> None:
        """Load artwork from binary data."""
        image = QImage.fromData(data)

        if image.isNull():
            self._show_error(tr("artwork.load_error"))
            return

        self._artwork = Artwork(
            embedded_data=data,
            width=image.width(),
            height=image.height()
        )

        # Determine mime type
        if data[:4] == b'\x89PNG':
            self._artwork.mime_type = "image/png"
        else:
            self._artwork.mime_type = "image/jpeg"

        pixmap = QPixmap.fromImage(image)

        # Scale for preview
        scaled = pixmap.scaled(
            300, 300,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.preview_label.setPixmap(scaled)
        self.preview_label.setObjectName("coverPreview")

        self.info_label.setText(f"{image.width()} x {image.height()} px")
        self.remove_btn.setEnabled(True)

    def set_max_size(self, size: int) -> None:
        """Set the maximum artwork size for resizing."""
        self._max_size = size
        self.size_info.setText(tr("artwork.resize_info", size=size))

    def clear(self) -> None:
        """Clear the artwork."""
        self._remove_image()
