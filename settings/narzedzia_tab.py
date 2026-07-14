"""Small configuration panels shared by the domain-oriented settings UI."""

from aqt.qt import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QCheckBox, QSpinBox,
)

from ..common.ui import _expanding_line_edit, _scrollable, hint_label


def _chain_to_text(chain: list) -> str:
    return ", ".join(
        f"{s.get('nauka_field', '')}:{s.get('tak_field', '')}" for s in chain
    )


def _text_to_chain(text: str) -> list:
    chain = []
    for pair in text.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        nauka, tak = pair.split(":", 1)
        nauka, tak = nauka.strip(), tak.strip()
        if nauka and tak:
            chain.append({"nauka_field": nauka, "tak_field": tak})
    return chain


def _csv(text: str) -> list:
    return [item.strip() for item in text.split(",") if item.strip()]


def _scroll_panel(widget: QWidget) -> None:
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    inner = QWidget()
    widget._panel_layout = QVBoxLayout(inner)
    widget._panel_layout.setContentsMargins(12, 12, 12, 12)
    widget._panel_layout.setSpacing(8)
    outer.addWidget(_scrollable(inner))


class FieldSplitterSettings(QWidget):
    """Field splitting belongs to content workflows, not system maintenance."""

    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        fs = cfg.get("field_splitter", {})
        group = QGroupBox("Rozdzielanie pól")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._source = _expanding_line_edit(fs.get("source_field", "przyklad"))
        self._separator = _expanding_line_edit(fs.get("separator", "<br><br>"))
        self._targets = _expanding_line_edit(
            fs.get("target_fields", "p1, p2, p3, p4, p5")
        )
        self._overwrite = QCheckBox(
            "Nadpisuj istniejące pola (inaczej wypełniaj tylko puste)"
        )
        self._overwrite.setChecked(fs.get("overwrite", True))
        form.addRow("Pole źródłowe:", self._source)
        form.addRow("Separator:", self._separator)
        form.addRow("Pola docelowe:", self._targets)
        form.addRow("", self._overwrite)
        form.addRow("", hint_label(
            "Ten etap jest dostępny w workflowach oraz w menu kontekstowym. "
            "Pole źródłowe nie jest modyfikowane.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        fs = cfg.setdefault("field_splitter", {})
        fs["source_field"] = self._source.text().strip()
        fs["separator"] = self._separator.text().strip()
        fs["target_fields"] = self._targets.text().strip()
        fs["overwrite"] = self._overwrite.isChecked()


class AudioEmbedSettings(QWidget):
    """Rewrite [sound:...] into inline <audio> players in chosen note types/fields."""

    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        ae = cfg.get("audio_embed", {})
        group = QGroupBox("Osadzanie audio — [sound:...] → <audio>")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._note_types = _expanding_line_edit(
            ", ".join(ae.get("note_types", ["angielski"]))
        )
        self._fields = _expanding_line_edit(
            ", ".join(ae.get("fields", ["przyklad", "p1", "p2", "p3", "p4", "p5"]))
        )
        self._css_class = _expanding_line_edit(ae.get("css_class", "ex-audio"))
        self._preload = _expanding_line_edit(ae.get("preload", "none"))
        self._scan_on_sync = QCheckBox("Skanuj kolekcję po synchronizacji")
        self._scan_on_sync.setChecked(ae.get("scan_on_sync", True))
        form.addRow("Typy notatek:", self._note_types)
        form.addRow("Pola:", self._fields)
        form.addRow("Klasa CSS:", self._css_class)
        form.addRow("preload:", self._preload)
        form.addRow("", self._scan_on_sync)
        form.addRow("", hint_label(
            "Zamienia [sound:plik.mp3] na <audio class=\"…\" src=\"plik.mp3\" "
            "preload=\"…\"></audio> w wybranych polach. Pole audio (główne) zostaw "
            "poza listą — zachowa klasyczne [sound:...]. Typy notatek puste = "
            "wszystkie. Operacja jest idempotentna.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        ae = cfg.setdefault("audio_embed", {})
        ae["note_types"] = _csv(self._note_types.text())
        ae["fields"] = _csv(self._fields.text())
        ae["css_class"] = self._css_class.text().strip()
        ae["preload"] = self._preload.text().strip()
        ae["scan_on_sync"] = self._scan_on_sync.isChecked()


class LearningRulesSettings(QWidget):
    """Rules controlling when cards become available during learning."""

    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)

        sm = cfg.get("sibling_manager", {})
        sm_group = QGroupBox("Sibling Manager — dynamiczne zawieszanie siblingów")
        sm_form = QFormLayout(sm_group)
        sm_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._sm_interval = QSpinBox()
        self._sm_interval.setRange(1, 365)
        self._sm_interval.setSuffix(" dni")
        self._sm_interval.setValue(sm.get("interval", 30))
        self._sm_tag = _expanding_line_edit(sm.get("tag", "tk-sib-suspended"))
        self._sm_ignore_tag = _expanding_line_edit(
            sm.get("ignore_tag", "tk-sib-ignored")
        )
        self._sm_show_tooltip = QCheckBox(
            "Pokazuj podsumowanie po synchronizacji"
        )
        self._sm_show_tooltip.setChecked(sm.get("show_tooltip", True))
        sm_form.addRow("Próg dojrzałości:", self._sm_interval)
        sm_form.addRow("Tag zawieszonych:", self._sm_tag)
        sm_form.addRow("Tag ignorowanych:", self._sm_ignore_tag)
        sm_form.addRow("", self._sm_show_tooltip)
        sm_form.addRow("", hint_label(
            "Niedojrzała karta zawiesza nowe siblingi; dojrzała uwalnia siblingi "
            "oznaczone przez Anki Toolkit.", small=True,
        ))
        self._panel_layout.addWidget(sm_group)

        hm = cfg.get("homograph_manager", {})
        hm_group = QGroupBox("Homograph Manager — rozdzielanie słów o wielu znaczeniach")
        hm_form = QFormLayout(hm_group)
        hm_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._hm_interval = QSpinBox()
        self._hm_interval.setRange(1, 365)
        self._hm_interval.setSuffix(" dni")
        self._hm_interval.setValue(hm.get("interval", 30))
        self._hm_field = _expanding_line_edit(hm.get("field", "ang"))
        self._hm_tag = _expanding_line_edit(hm.get("tag", "tk-homograph-suspended"))
        self._hm_ignore_tag = _expanding_line_edit(
            hm.get("ignore_tag", "tk-homograph-ignored")
        )
        self._hm_show_tooltip = QCheckBox("Pokazuj podsumowanie po synchronizacji")
        self._hm_show_tooltip.setChecked(hm.get("show_tooltip", True))
        hm_form.addRow("Próg dojrzałości:", self._hm_interval)
        hm_form.addRow("Pole grupujące:", self._hm_field)
        hm_form.addRow("Tag zawieszonych:", self._hm_tag)
        hm_form.addRow("Tag ignorowanych:", self._hm_ignore_tag)
        hm_form.addRow("", self._hm_show_tooltip)
        hm_form.addRow("", hint_label(
            "Osobne notatki z tym samym słowem w polu grupującym (np. „assault”) "
            "uczą się po kolei: kolejne znaczenie odblokowuje się dopiero, gdy "
            "poprzednie osiągnie próg dojrzałości.", small=True,
        ))
        self._panel_layout.addWidget(hm_group)

        su = cfg.get("sentence_unlocker", {})
        su_group = QGroupBox("Sentence Unlocker — stopniowe odblokowywanie zdań")
        su_form = QFormLayout(su_group)
        su_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._su_model = _expanding_line_edit(su.get("model", "angielski"))
        self._su_threshold = QSpinBox()
        self._su_threshold.setRange(1, 365)
        self._su_threshold.setSuffix(" dni")
        self._su_threshold.setValue(su.get("threshold", 21))
        self._su_marker = _expanding_line_edit(su.get("marker", "tak"))
        self._su_main = _expanding_line_edit(
            ", ".join(su.get("main_templates", ["ang-pol", "pol-ang"]))
        )
        self._su_chain = _expanding_line_edit(_chain_to_text(
            su.get("chain", [
                {"nauka_field": "p1-nauka", "tak_field": "p1-tak"},
                {"nauka_field": "p2-nauka", "tak_field": "p2-tak"},
                {"nauka_field": "p3-nauka", "tak_field": "p3-tak"},
            ])
        ))
        self._su_ignore_tag = _expanding_line_edit(
            su.get("ignore_tag", "tk-unlock-ignored")
        )
        self._su_done_tag = _expanding_line_edit(
            su.get("done_tag", "tk-unlock-done")
        )
        self._su_show_tooltip = QCheckBox("Pokazuj podsumowanie po skanowaniu")
        self._su_show_tooltip.setChecked(su.get("show_tooltip", True))
        su_form.addRow("Typ notatki:", self._su_model)
        su_form.addRow("Próg dojrzałości:", self._su_threshold)
        su_form.addRow("Wartość znacznika:", self._su_marker)
        su_form.addRow("Karty główne:", self._su_main)
        su_form.addRow("Łańcuch pole-nauka:pole-tak:", self._su_chain)
        su_form.addRow("Tag ignorowanych:", self._su_ignore_tag)
        su_form.addRow("Tag ukończonych:", self._su_done_tag)
        su_form.addRow("", self._su_show_tooltip)
        su_form.addRow("", hint_label(
            "Reguła jest jednokierunkowa: raz wpisany znacznik nie jest usuwany, "
            "ponieważ usunęłoby to kartę wraz z historią.", small=True,
        ))
        self._panel_layout.addWidget(su_group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        sm = cfg.setdefault("sibling_manager", {})
        sm["interval"] = self._sm_interval.value()
        sm["tag"] = self._sm_tag.text().strip()
        sm["ignore_tag"] = self._sm_ignore_tag.text().strip()
        sm["show_tooltip"] = self._sm_show_tooltip.isChecked()

        hm = cfg.setdefault("homograph_manager", {})
        hm["interval"] = self._hm_interval.value()
        hm["field"] = self._hm_field.text().strip()
        hm["tag"] = self._hm_tag.text().strip()
        hm["ignore_tag"] = self._hm_ignore_tag.text().strip()
        hm["show_tooltip"] = self._hm_show_tooltip.isChecked()

        su = cfg.setdefault("sentence_unlocker", {})
        su["model"] = self._su_model.text().strip()
        su["threshold"] = self._su_threshold.value()
        su["marker"] = self._su_marker.text().strip()
        su["main_templates"] = _csv(self._su_main.text())
        su["chain"] = _text_to_chain(self._su_chain.text())
        su["ignore_tag"] = self._su_ignore_tag.text().strip()
        su["done_tag"] = self._su_done_tag.text().strip()
        su["show_tooltip"] = self._su_show_tooltip.isChecked()


class FilteredDeckSettings(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        fd = cfg.get("filtered_deck", {})
        group = QGroupBox("Presety powtórek — talia filtrowana")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._deck_name = _expanding_line_edit(
            fd.get("deck_name", "Angielski - Powtórka z wyprzedzeniem")
        )
        form.addRow("Nazwa bazowa talii:", self._deck_name)
        form.addRow("", hint_label(
            "Presety są uruchamiane z menu Narzędzia → Anki Toolkit.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("filtered_deck", {})["deck_name"] = (
            self._deck_name.text().strip()
        )


class HtmlCleanupSettings(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        values = cfg.get("nbsp_remover", {})
        group = QGroupBox("Czyszczenie pól HTML")
        box = QVBoxLayout(group)
        self._show_tooltip = QCheckBox("Pokazuj podsumowanie po wyczyszczeniu")
        self._show_tooltip.setChecked(values.get("show_tooltip", True))
        self._auto_run = QCheckBox("Automatycznie czyść kolekcję przy starcie Anki")
        self._auto_run.setChecked(values.get("auto_run_startup", False))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._skip_field = _expanding_line_edit(values.get("skip_field", "ang"))
        form.addRow("Pole traktowane jako zwykły tekst:", self._skip_field)
        box.addWidget(self._show_tooltip)
        box.addWidget(self._auto_run)
        box.addLayout(form)
        box.addWidget(hint_label(
            "Ręczne czyszczenie istniejących notatek pozostaje dostępne w menu "
            "Narzędzia → Anki Toolkit.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        values = cfg.setdefault("nbsp_remover", {})
        values["show_tooltip"] = self._show_tooltip.isChecked()
        values["auto_run_startup"] = self._auto_run.isChecked()
        values["skip_field"] = self._skip_field.text().strip()


class NarzedziaTab(QWidget):
    """Compatibility wrapper retained for callers outside the settings dialog."""

    def __init__(self, cfg: dict):
        super().__init__()
        layout = QVBoxLayout(self)
        self._children = [
            FieldSplitterSettings(cfg), LearningRulesSettings(cfg),
            FilteredDeckSettings(cfg), HtmlCleanupSettings(cfg),
        ]
        for child in self._children:
            layout.addWidget(child)

    def apply(self, cfg: dict) -> None:
        for child in self._children:
            child.apply(cfg)
