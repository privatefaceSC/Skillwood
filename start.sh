#!/bin/bash
# Запуск Skillwood на Replit (шаблон Python).
# cd в каталог самого скрипта — работает при ЛЮБОМ имени папки клонирования,
# править эту строку вручную (как в примере урока) не нужно.
cd "$(dirname "$0")"
export PORT=5000
unset PIP_USER

# Создать venv, если его ещё нет.
if [ ! -d "venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv venv --system-site-packages
fi

# Активировать.
source venv/bin/activate

# Поставить зависимости (если pip сломан — пакеты могут быть предустановлены
# системой, поэтому не падаем).
if [ -f "requirements.txt" ]; then
    echo "Проверяю зависимости..."
    pip install -r requirements.txt || echo "pip install не прошёл — продолжаю (пакеты могут быть предустановлены)."
fi

echo "Запуск приложения..."
python main.py
