"""Connection status and switches for external systems."""

from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from services.systems import SystemsService
from ui.components import Panel, SectionHeading
from ui.style import configure_page_layout


class SystemsWindow(QWidget):
    def __init__(self, service: SystemsService | None = None) -> None:
        super().__init__()
        self._service = service
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(SectionHeading("Համակարգեր"))
        card = Panel()
        body = QVBoxLayout(card)
        body.setContentsMargins(24, 24, 24, 24)
        body.addWidget(SectionHeading("Օնլայն ծառայություն"))
        self.status = QLabel()
        body.addWidget(self.status)
        self.toggle = QCheckBox("Միացնել կապը")
        self.toggle.setObjectName("onlineConnectionToggle")
        body.addWidget(self.toggle)
        note = QLabel(
            "Անջատելիս դադարում են օնլայն պատվերների և ապրանքների կապերը։ "
            "Միացնելիս կապը վերականգնվում է ավտոմատ։"
        )
        note.setWordWrap(True)
        body.addWidget(note)
        layout.addWidget(card)
        layout.addStretch()
        if service is not None:
            service.changed.connect(self._refresh)
            self.toggle.toggled.connect(service.set_enabled)
        self._refresh()

    def _refresh(self) -> None:
        service = self._service
        configured = service is not None and service.configured
        self.toggle.setEnabled(configured)
        self.toggle.blockSignals(True)
        self.toggle.setChecked(configured and service.enabled)
        self.toggle.blockSignals(False)
        if not configured:
            text = (
                "Կարգավորված չէ · անհրաժեշտ են օնլայն ծառայության URL-ը և API բանալին"
            )
        elif not service.enabled:
            text = "Անջատված է"
        elif service.connected:
            text = "Միացված է"
        else:
            text = "Կապ չկա · փորձում է միանալ"
        self.status.setText(text)
