from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import QByteArray, QDate, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QFrame, QHeaderView, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.style import (
    configure_action_button, configure_page_layout, configure_table_view,
    format_currency,
)
from ui.workers import run_in_background, wait_for_pending_threads


_ICON_PATHS = {
    "wallet": '<path d="M20 8V5a2 2 0 0 0-2-2H5a3 3 0 0 0 0 6h15v11H5a3 3 0 0 1-3-3V6"/><path d="M20 12h-5v4h5"/>',
    "people": '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3"/>',
    "document": '<path d="M14 2H5v20h14V7zM14 2v5h5M8 12h8M8 16h6"/>',
    "refresh": '<path d="M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5M4 17a9 9 0 0 0 15 2l3-3m0 5v-5h-5"/>',
    "add": '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 9-5M18 12v8M14 16h8"/>',
    "edit": '<path d="m15 4 5 5M4 16 16 4a2 2 0 0 1 4 4L8 20l-5 1z"/>',
    "power": '<path d="M12 2v10M6 5a9 9 0 1 0 12 0"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
}


def _page_icon(name, color="#2563eb", size=24):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_ICON_PATHS[name]}</svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size * 2, size * 2))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class CashWithdrawalsWindow(QWidget):
    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.rows = []
        self._history = []
        layout = QVBoxLayout(self)
        configure_page_layout(layout)

        intro = QHBoxLayout()
        emblem = QLabel()
        emblem.setPixmap(_page_icon("wallet", size=36).pixmap(QSize(36, 36)))
        emblem.setFixedSize(60, 60)
        emblem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emblem.setStyleSheet("background: #e8f0ff; border-radius: 16px;")
        intro.addWidget(emblem)
        intro.setSpacing(16)
        text = QVBoxLayout()
        title = QLabel("Դրամական շարժեր")
        title.setObjectName("pageTitle")
        text.addWidget(title)
        subtitle = QLabel("Կառավարեք գումար ստացող անձանց և հետևեք դուրսբերումներին")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        text.addWidget(subtitle)
        intro.addLayout(text, 1)
        self.refresh_button = self._button("Թարմացնել", self.reload, icon="refresh")
        intro.addWidget(self.refresh_button)
        layout.addLayout(intro)

        metrics = QHBoxLayout()
        self.total_value = self._metric(metrics, "Ընդհանուր դուրսբերումներ", "0 ֏", "primary", "wallet")
        self.count_value = self._metric(metrics, "Դուրսբերման փաստաթղթեր", "0", "info", "document")
        self.active_value = self._metric(metrics, "Ակտիվ ստացողներ", "0", "success", "people")
        layout.addLayout(metrics)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        people_panel, people_layout = self._panel("Գումար ստացող անձինք", "people")
        people_panel.setMinimumWidth(290)
        people_note = QLabel("Ընտրեք անձին՝ տվյալները կառավարելու համար")
        people_note.setObjectName("fieldHint")
        people_note.setWordWrap(True)
        people_layout.addWidget(people_note)
        people_layout.addWidget(self._button("Ավելացնել անձ", self.add, "primary", "add"))
        self.people = QTableWidget(0, 2)
        self.people.setHorizontalHeaderLabels(["Անուն", "Կարգավիճակ"])
        self._configure_table(self.people)
        self.people.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.people.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        people_layout.addWidget(self.people, 1)
        self.people_message = QLabel()
        self.people_message.setObjectName("fieldHint")
        people_layout.addWidget(self.people_message)
        actions = QHBoxLayout()
        self.rename_button = self._button("Խմբագրել", self.rename, icon="edit")
        self.toggle_button = self._button("Ապաակտիվացնել", self.toggle, icon="power")
        actions.addWidget(self.rename_button)
        actions.addWidget(self.toggle_button)
        people_layout.addLayout(actions)
        self.people.itemSelectionChanged.connect(self._update_actions)
        self.people.itemDoubleClicked.connect(lambda _: self.rename())
        splitter.addWidget(people_panel)

        history_panel, history_layout = self._panel("Դուրսբերումների պատմություն", "document")
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.addAction(_page_icon("search", "#7a8794"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setPlaceholderText("Որոնել անձ, պատճառ կամ փաստաթուղթ…")
        self.search.textChanged.connect(self._filter_history)
        history_layout.addWidget(self.search)
        dates = QHBoxLayout()
        dates.setSpacing(8)
        self.date_preset = QComboBox()
        self.date_preset.setAccessibleName("Ժամանակահատված")
        for caption, key in [
            ("Բոլոր ամսաթվերը", "all"),
            ("Այսօր", "today"),
            ("Երեկ", "yesterday"),
            ("Այս շաբաթ", "week"),
            ("Վերջին 7 օրը", "last7"),
            ("Այս ամիս", "month"),
            ("Նախորդ ամիս", "previous_month"),
            ("Վերջին 30 օրը", "last30"),
            ("Այս տարի", "year"),
            ("Նախորդ տարի", "previous_year"),
            ("Այլ ժամանակահատված", "custom"),
        ]:
            self.date_preset.addItem(caption, key)
        dates.addWidget(self.date_preset)
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_to = QDateEdit(QDate.currentDate())
        for editor, caption in ((self.date_from, "Սկիզբ"), (self.date_to, "Ավարտ")):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd.MM.yyyy")
            editor.setAccessibleName(caption)
            editor.setEnabled(False)
            editor.setStyleSheet("QDateEdit { min-height: 36px; padding: 4px 8px; border: 1px solid #cbd3dc; border-radius: 6px; background: white; } QDateEdit:disabled { color: #87909a; background: #eef0f2; }")
            dates.addWidget(QLabel(caption))
            dates.addWidget(editor)
        dates.addStretch()
        dates.addWidget(self._button("Մաքրել", self._reset_filters))
        history_layout.addLayout(dates)
        self.date_preset.currentIndexChanged.connect(self._date_preset_changed)
        self.date_from.dateChanged.connect(self._filter_history)
        self.date_to.dateChanged.connect(self._filter_history)
        self.history = QTableWidget(0, 7)
        self.history.setHorizontalHeaderLabels([
            "Ամսաթիվ", "Անձ", "Գումար", "Պատճառ", "Սեսիա", "Գանձապահ", "Փաստաթուղթ",
        ])
        self._configure_table(self.history)
        header = self.history.horizontalHeader()
        for column in range(7):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # Technical identifiers remain available in the document details.
        self.history.setColumnHidden(4, True)
        self.history.setColumnHidden(5, True)
        self.history.itemDoubleClicked.connect(self._show_details)
        history_layout.addWidget(self.history, 1)
        self.history_message = QLabel()
        self.history_message.setObjectName("fieldHint")
        self.history_message.setWordWrap(True)
        history_layout.addWidget(self.history_message)
        splitter.addWidget(history_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([340, 1000])
        layout.addWidget(splitter, 1)
        self._update_actions()
        self.reload()

    @staticmethod
    def _button(text, handler, variant="secondary", icon=None):
        button = QPushButton(text)
        configure_action_button(button)
        button.setProperty("variant", variant)
        if icon:
            button.setIcon(_page_icon(icon, "#ffffff" if variant == "primary" else "#526170"))
            button.setIconSize(QSize(20, 20))
        button.clicked.connect(handler)
        return button

    @staticmethod
    def _panel(title, icon):
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("sectionHeading")
        heading_row = QHBoxLayout()
        symbol = QLabel()
        symbol.setPixmap(_page_icon(icon, size=22).pixmap(QSize(22, 22)))
        heading_row.addWidget(symbol)
        heading_row.addWidget(heading, 1)
        layout.addLayout(heading_row)
        return panel, layout

    @staticmethod
    def _metric(layout, caption, value, tone, icon):
        card = QFrame()
        card.setObjectName("statCard")
        card.setProperty("tone", tone)
        body = QVBoxLayout(card)
        body.setContentsMargins(20, 16, 20, 16)
        label = QLabel(caption)
        label.setObjectName("statLabel")
        label.setWordWrap(True)
        number = QLabel(value)
        number.setObjectName("statValue")
        number.setProperty("tone", tone)
        top = QHBoxLayout()
        top.addWidget(label, 1)
        symbol = QLabel()
        color = "#087765" if tone == "success" else "#2563eb"
        symbol.setPixmap(_page_icon(icon, color, 24).pixmap(QSize(24, 24)))
        symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        symbol.setFixedSize(40, 40)
        symbol.setStyleSheet(f"background: {"#e8f4f1" if tone == "success" else "#e8f0ff"}; border-radius: 12px;")
        top.addWidget(symbol)
        body.addLayout(top)
        body.addWidget(number)
        layout.addWidget(card, 1)
        return number

    @staticmethod
    def _configure_table(table):
        configure_table_view(table)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(48)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def reload(self):
        self.refresh_button.setEnabled(False)
        self.history_message.setText("Տվյալները բեռնվում են…")
        run_in_background(
            self,
            lambda: (self.repository.recipients(), self.repository.history()),
            self.loaded,
            self.failed,
        )

    def loaded(self, data):
        selected = self.selected()
        selected_id = selected["id"] if selected else None
        self.rows, self._history = data
        self.people.clearSelection()
        self.people.setCurrentCell(-1, -1)
        self.people.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            self.people.setItem(i, 0, QTableWidgetItem(row["name"]))
            status = QTableWidgetItem("Ակտիվ" if row["is_active"] else "Ոչ ակտիվ")
            status.setForeground(QColor("#087765" if row["is_active"] else "#7a8794"))
            self.people.setItem(i, 1, status)
            if row["id"] == selected_id:
                self.people.selectRow(i)
        self.history.setRowCount(len(self._history))
        keys = ["taken_at", "recipient_name", "amount", "reason", "session_id", "cashier_id", "id"]
        for i, row in enumerate(self._history):
            for j, key in enumerate(keys):
                raw = str(row[key])
                value = raw
                if key == "session_id":
                    value = row.get("session_name", "—")
                elif key == "cashier_id":
                    value = row.get("cashier_name", "—")
                if key == "taken_at":
                    try:
                        value = datetime.fromisoformat(raw).strftime("%d.%m.%Y  %H:%M")
                    except ValueError:
                        pass
                elif key == "amount":
                    value = format_currency(Decimal(raw))
                elif key == "id":
                    value = raw[:8].upper()
                item = QTableWidgetItem(value)
                item.setToolTip(raw)
                if key == "amount":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.history.setItem(i, j, item)
        self.total_value.setText(format_currency(sum((Decimal(r["amount"]) for r in self._history), Decimal("0"))))
        self.count_value.setText(str(len(self._history)))
        self.active_value.setText(str(sum(bool(r["is_active"]) for r in self.rows)))
        self.people_message.setText(f"Ընդամենը՝ {len(self.rows)} անձ" if self.rows else "Ավելացրեք առաջին գումար ստացող անձին")
        self.refresh_button.setEnabled(True)
        self._update_actions()
        self._filter_history()

    def _update_actions(self):
        row = self.selected()
        self.rename_button.setEnabled(row is not None)
        self.toggle_button.setEnabled(row is not None)
        self.toggle_button.setText("Ապաակտիվացնել" if not row or row["is_active"] else "Ակտիվացնել")

    def _date_preset_changed(self, _index):
        preset = self.date_preset.currentData()
        today = QDate.currentDate()
        month_start = QDate(today.year(), today.month(), 1)
        ranges = {
            "today": (today, today),
            "yesterday": (today.addDays(-1), today.addDays(-1)),
            "week": (today.addDays(1 - today.dayOfWeek()), today),
            "last7": (today.addDays(-6), today),
            "month": (month_start, today),
            "previous_month": (month_start.addMonths(-1), month_start.addDays(-1)),
            "last30": (today.addDays(-29), today),
            "year": (QDate(today.year(), 1, 1), today),
            "previous_year": (QDate(today.year() - 1, 1, 1), QDate(today.year() - 1, 12, 31)),
        }
        if preset in ranges:
            start, end = ranges[preset]
            for editor, value in ((self.date_from, start), (self.date_to, end)):
                editor.blockSignals(True)
                editor.setDate(value)
                editor.blockSignals(False)
        self.date_from.setEnabled(preset == "custom")
        self.date_to.setEnabled(preset == "custom")
        self._filter_history()

    def _reset_filters(self):
        self.date_preset.setCurrentIndex(0)
        self.search.clear()
        self._filter_history()

    def _filter_history(self):
        query = self.search.text().strip().casefold()
        date_enabled = self.date_preset.currentData() != "all"
        start = self.date_from.date().toPython()
        end = self.date_to.date().toPython()
        if date_enabled and start > end:
            for i in range(len(self._history)):
                self.history.setRowHidden(i, True)
            self.history_message.setText("Սկզբի ամսաթիվը պետք է լինի ավարտի ամսաթվից առաջ կամ նույն օրը։")
            return
        visible = 0
        total = Decimal("0")
        for i, row in enumerate(self._history):
            match = not query or query in " ".join(str(v) for v in row.values()).casefold()
            if date_enabled:
                try:
                    taken_date = datetime.fromisoformat(str(row["taken_at"])).date()
                    match = match and start <= taken_date <= end
                except ValueError:
                    match = False
            self.history.setRowHidden(i, not match)
            if match:
                visible += 1
                total += Decimal(row["amount"])
        if visible:
            self.history_message.setText(f"{visible} փաստաթուղթ · {format_currency(total)} · Մանրամասների համար կրկնակի սեղմեք տողին")
        else:
            self.history_message.setText("Որոնման արդյունքներ չեն գտնվել" if query or date_enabled else "Դուրսբերումներ դեռ չկան")

    def _show_details(self, item):
        row = self._history[item.row()]
        labels = [("taken_at", "Ամսաթիվ"), ("recipient_name", "Անձ"), ("amount", "Գումար (֏)"), ("reason", "Պատճառ"), ("session_name", "Սեսիա"), ("cashier_name", "Գանձապահ"), ("id", "Փաստաթուղթ")]
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Դուրսբերման մանրամասներ")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText("\n\n".join(f"{label}: {row.get(key, '—')}" for key, label in labels))
        dialog.exec()

    def selected(self):
        index = self.people.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def save(self, name, recipient_id=None, active=True):
        run_in_background(
            self,
            lambda: self.repository.save_recipient(name, recipient_id, active),
            lambda _: self.reload(),
            self.failed,
        )

    def add(self):
        name, ok = QInputDialog.getText(self, "Ավելացնել անձ", "Անուն")
        if ok:
            self.save(name)

    def rename(self):
        row = self.selected()
        if row:
            name, ok = QInputDialog.getText(
                self, "Խմբագրել անձ", "Անուն", text=row["name"]
            )
            if ok:
                self.save(name, row["id"], row["is_active"])

    def toggle(self):
        row = self.selected()
        if row:
            self.save(row["name"], row["id"], not row["is_active"])

    def failed(self, error):
        self.refresh_button.setEnabled(True)
        self.history_message.setText("Չհաջողվեց բեռնել տվյալները։ Փորձեք թարմացնել։")
        QMessageBox.warning(self, "Սխալ", str(error))

    def closeEvent(self, event):
        wait_for_pending_threads(self)
        super().closeEvent(event)
