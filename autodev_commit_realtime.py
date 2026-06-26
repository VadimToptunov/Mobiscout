#!/usr/bin/env python3
import os
import re
import subprocess
import time
from datetime import datetime

# ---------------------------
# Настройки
# ---------------------------
WATCH_EXTENSIONS = (".py", ".kt", ".java", ".js", ".ts", ".go", ".cs", ".swift")
IGNORE_EXTENSIONS = (".md", ".pdf", ".html", ".png", ".jpg", ".apk", ".jar", ".zip")

CHECK_INTERVAL = 60  # секунд между проверками новых файлов

processed_steps = set()
file_timestamps = {}


# ---------------------------
# Вспомогательные функции
# ---------------------------
def run_command(cmd):
    """Запуск команды в shell"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def run_unit_tests():
    """Запуск unit-тестов Python (можно расширить под другие языки)"""
    code, output = run_command("pytest -q --tb=short")
    return code == 0, output


def auto_fix_errors():
    """Автофикс для Python (расширяемо под другие языки)"""
    print("⚠️ Ошибки обнаружены. Пытаемся автофикс...")
    run_command("autopep8 --in-place -r .")
    run_command("git add .")


def detect_new_step_files():
    """Ищет новые или изменённые файлы с STEP комментариями"""
    new_steps = []
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(WATCH_EXTENSIONS) and not file.endswith(IGNORE_EXTENSIONS):
                path = os.path.join(root, file)
                mtime = os.path.getmtime(path)
                if path not in file_timestamps or file_timestamps[path] < mtime:
                    # Пытаемся прочитать файл безопасно
                    content = None
                    for enc in ("utf-8", "latin1"):
                        try:
                            with open(path, "r", encoding=enc) as f:
                                content = f.read()
                            break
                        except UnicodeDecodeError:
                            continue
                    if content is None:
                        print(f"⚠️ Пропускаем файл {path}, невозможно прочитать")
                        continue
                    # Ищем STEP комментарии
                    matches = re.findall(r"#\s*STEP\s*(\d+):\s*(.+)", content)
                    for match in matches:
                        step_number = int(match[0])
                        step_desc = match[1].strip()
                        if step_number not in processed_steps:
                            new_steps.append((step_number, step_desc))
                    file_timestamps[path] = mtime
    return sorted(new_steps)


def git_commit_push(step_number, step_description):
    """Автокоммит и push с фильтром .md и других игнорируемых файлов"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{timestamp} - STEP {step_number}: {step_description}"
    run_command("git add --all ':(exclude)*.md' ':(exclude)*.pdf' ':(exclude)*.html'")
    run_command(f"git commit -m \"{message}\"")
    run_command("git push origin main")
    print(f"✅ Committed and pushed: {message}")


# ---------------------------
# Основной цикл
# ---------------------------
if __name__ == "__main__":
    print("🚀 Запуск Realtime STEP Commit скрипта...")
    while True:
        new_steps = detect_new_step_files()
        if not new_steps:
            print(f"ℹ️ Новых STEP пока нет. Ждем {CHECK_INTERVAL} секунд...")
        else:
            for step_number, step_desc in new_steps:
                print(f"⏱ Обрабатываем STEP {step_number}: {step_desc}")
                success, output = run_unit_tests()
                if success:
                    git_commit_push(step_number, step_desc)
                    processed_steps.add(step_number)
                else:
                    print("❌ Unit-tests failed:")
                    print(output)
                    auto_fix_errors()
                    success, output = run_unit_tests()
                    if success:
                        git_commit_push(step_number, step_desc)
                        processed_steps.add(step_number)
                    else:
                        print("❌ Ошибки остались. Ждем исправлений Copilot...")
        time.sleep(CHECK_INTERVAL)
