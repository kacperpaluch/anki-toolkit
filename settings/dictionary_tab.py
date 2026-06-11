"""Dictionary tab — source/target fields, IPA, network, button config."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QGroupBox,
)

from ..common.ui import _expanding_line_edit, _scrollable


class DictionaryTab(QWidget):
    _IPA_FORMATS = ["compact", "both", "uk_only", "us_only"]

    def __init__(self, cfg: dict):
        super().__init__()
        d = cfg.get("dictionary", {})

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._source = _expanding_line_edit(d.get("source_field", "ang"))
        self._target = _expanding_line_edit(d.get("target_field", "audio"))
        self._ipa_field = _expanding_line_edit(d.get("ipa_field", "IPA"))
        self._ipa_format = QComboBox()
        self._ipa_format.addItems(self._IPA_FORMATS)
        fmt = d.get("ipa_format", "compact")
        self._ipa_format.setCurrentIndex(
            self._IPA_FORMATS.index(fmt) if fmt in self._IPA_FORMATS else 0
        )

        self._wiktionary_fallback = QCheckBox("Wiktionary jako fallback IPA")
        self._wiktionary_fallback.setChecked(d.get("wiktionary_ipa_fallback", True))
        self._wiktionary_fallback.setToolTip(
            "Gdy Oxford/Cambridge nie znajdzie IPA dla słowa, automatycznie odpyta Wiktionary API.\n"
            "Wiktionary dostarcza tylko IPA — nie dostarcza audio."
        )

        self._diki_ipa_fallback = QCheckBox("Pobierz IPA dla Diki z:")
        self._diki_ipa_fallback.setChecked(d.get("diki_ipa_fallback", False))
        self._diki_ipa_fallback.setToolTip(
            "Diki nie zawiera transkrypcji IPA. Po zaznaczeniu tej opcji IPA\n"
            "zostanie pobrane z wybranego słownika podczas fetchowania z Diki."
        )
        _IPA_SOURCES = ["wiktionary", "oxford", "cambridge"]
        self._diki_ipa_source = QComboBox()
        self._diki_ipa_source.addItems(_IPA_SOURCES)
        src = d.get("diki_ipa_fallback_source", "wiktionary")
        self._diki_ipa_source.setCurrentIndex(
            _IPA_SOURCES.index(src) if src in _IPA_SOURCES else 0
        )
        self._diki_ipa_source.setEnabled(self._diki_ipa_fallback.isChecked())
        self._diki_ipa_fallback.toggled.connect(self._diki_ipa_source.setEnabled)

        diki_ipa_row = QHBoxLayout()
        diki_ipa_row.setContentsMargins(0, 0, 0, 0)
        diki_ipa_row.addWidget(self._diki_ipa_fallback)
        diki_ipa_row.addWidget(self._diki_ipa_source)
        diki_ipa_row.addStretch()

        form.addRow("Pole źródłowe (słowo ang):", self._source)
        form.addRow("Pole docelowe (audio):", self._target)
        form.addRow("Pole IPA (puste = wyłącz):", self._ipa_field)
        form.addRow("Format IPA:", self._ipa_format)
        form.addRow("", self._wiktionary_fallback)
        form.addRow("", diki_ipa_row)
        layout.addLayout(form)
        layout.addSpacing(8)

        net_group = QGroupBox("Sieć")
        net_form = QFormLayout(net_group)
        net_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._max_retries = QSpinBox()
        self._max_retries.setRange(1, 10)
        self._max_retries.setValue(d.get("max_retries", 3))
        self._max_retries.setToolTip("Liczba prób przy błędach sieci (429, 5xx)")
        self._page_timeout = QSpinBox()
        self._page_timeout.setRange(1, 120)
        self._page_timeout.setSuffix(" s")
        self._page_timeout.setValue(d.get("page_timeout", 10))
        self._page_timeout.setToolTip("Timeout pobierania strony słownika")
        self._mp3_timeout = QSpinBox()
        self._mp3_timeout.setRange(1, 120)
        self._mp3_timeout.setSuffix(" s")
        self._mp3_timeout.setValue(d.get("mp3_timeout", 10))
        self._mp3_timeout.setToolTip("Timeout pobierania pliku MP3")
        net_form.addRow("Maks. prób (retry):", self._max_retries)
        net_form.addRow("Timeout strony:", self._page_timeout)
        net_form.addRow("Timeout MP3:", self._mp3_timeout)
        layout.addWidget(net_group)
        layout.addSpacing(8)

        group = QGroupBox("Przyciski w edytorze")
        btn_layout = QVBoxLayout(group)
        btn_layout.addWidget(
            QLabel("Zaznacz słowniki, których przyciski mają być widoczne w edytorze kart.")
        )

        buttons_cfg = d.get("buttons", [])
        self._btn_checks: dict[str, tuple] = {}
        btn_map = {"+".join(b.get("dictionaries", [])): b for b in buttons_cfg}

        standard = [
            ("Diki",      ["diki_uk", "diki_us"]),
            ("Oxford",    ["oxford_uk", "oxford_us"]),
            ("Cambridge", ["cambridge_uk", "cambridge_us"]),
            ("Longman",   ["longman_uk", "longman_us"]),
        ]
        standard_keys = {"+".join(keys) for _label, keys in standard}
        # Buttons configured by hand (custom dictionary combinations) get a
        # checkbox too, instead of being silently dropped on save.
        for key, b in btn_map.items():
            if key in standard_keys or not isinstance(b, dict):
                continue
            standard.append((b.get("label", key), list(b.get("dictionaries", []))))

        for label, keys in standard:
            key = "+".join(keys)
            b = btn_map.get(key, {})
            cb = QCheckBox(f"{label}  ({', '.join(keys)})")
            cb.setChecked(b.get("enabled", False))
            self._btn_checks[key] = (cb, label, keys)
            btn_layout.addWidget(cb)

        layout.addWidget(group)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scrollable(inner))

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("dictionary", {})
        d = cfg["dictionary"]
        d["source_field"] = self._source.text().strip()
        d["target_field"] = self._target.text().strip()
        d["ipa_field"] = self._ipa_field.text().strip()
        d["ipa_format"] = self._ipa_format.currentText()
        d["wiktionary_ipa_fallback"] = self._wiktionary_fallback.isChecked()
        d["diki_ipa_fallback"] = self._diki_ipa_fallback.isChecked()
        d["diki_ipa_fallback_source"] = self._diki_ipa_source.currentText()
        d["max_retries"] = self._max_retries.value()
        d["page_timeout"] = self._page_timeout.value()
        d["mp3_timeout"] = self._mp3_timeout.value()
        d["buttons"] = [
            {"dictionaries": keys, "label": label, "enabled": cb.isChecked()}
            for _key, (cb, label, keys) in self._btn_checks.items()
        ]
