"""Установка всего, что нужно верхнему уровню (GUI_App).

Запуск:  python install.py        (на Windows удобнее install.bat)

Единственный источник списка зависимостей — requirements.txt рядом с этим
файлом: новые пакеты добавлять туда, скрипт менять не требуется.
"""
import subprocess
import sys
from pathlib import Path

MIN_PY = (3, 10)

# (import-имя, pip-имя) — проверка после установки
CHECKS = [
    ("serial", "pyserial"),
    ("dearpygui.dearpygui", "dearpygui"),
    ("numpy", "numpy"),
    ("pytest", "pytest"),
]


def main() -> int:
    ver = sys.version.split()[0]
    if sys.version_info < MIN_PY:
        print(f"Нужен Python {MIN_PY[0]}.{MIN_PY[1]}+ (NFR-01), запущен {ver}.")
        print("Поставь свежий Python с python.org и перезапусти установку.")
        return 1
    print(f"Python {ver} — ок")

    req = Path(__file__).with_name("requirements.txt")
    print(f"Установка зависимостей из {req.name} ...\n")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(req)]
    )
    if result.returncode != 0:
        print("\npip завершился с ошибкой — смотри сообщения выше.")
        return result.returncode

    print("\nПроверка импортов:")
    ok = True
    for mod, pip_name in CHECKS:
        try:
            __import__(mod)
            top = sys.modules[mod.split(".")[0]]
            print(f"  {pip_name:<10} {getattr(top, '__version__', '?'):<10} ок")
        except ImportError as exc:
            print(f"  {pip_name:<10} ОШИБКА: {exc}")
            ok = False

    print("\nГотово: всё установлено." if ok else "\nЕсть проблемы — смотри выше.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
