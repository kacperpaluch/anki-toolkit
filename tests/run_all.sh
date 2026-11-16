#!/bin/sh
# Every check in one go: unit tests, compile, whitespace, and the Qt smoke tests
# on the Qt that Anki ships (they need its Python packages, not a running Anki).
set -e
cd "$(dirname "$0")/.."
ANKI_PACKAGES="${ANKI_PACKAGES:-/Applications/Anki.app/Contents/Resources/app_packages}"
# Anki ships .pyc for Python 3.13 only; Homebrew may not have it, uv usually does.
ANKI_PYTHON="${ANKI_PYTHON:-$(command -v python3.13 || uv python find 3.13)}"

python3 -m unittest discover -s tests
python3 -m compileall -q -f .
git diff --check
for smoke in tests/qt_*_smoke.py; do
    QT_QPA_PLATFORM=offscreen PYTHONPATH="$ANKI_PACKAGES" "$ANKI_PYTHON" "$smoke"
done
echo "Wszystkie testy: OK"
