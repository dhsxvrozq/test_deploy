#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import uuid
import random
import json
import subprocess
from pathlib import Path

# 1) Пути и глобальные константы
CONFIG_PATH = Path.home() / "vless-server"
USED_PORTS_FILE = CONFIG_PATH / "used_ports.txt"

def init_config_dir() -> None:
    """
    Создаёт основную директорию ~/vless-server, если её нет.
    """
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)

def get_next_port(start: int = 10000) -> int:
    """
    Читает USED_PORTS_FILE, ищет свободный порт >= start,
    дописывает его в файл и возвращает.
    Если файла нет, создаём и сразу возвращаем start.
    """
    if not USED_PORTS_FILE.exists():
        USED_PORTS_FILE.write_text(f"{start}\n")
        return start

    # Читаем все строки, приводим к int, выбираем уникальные и сортируем
    with open(USED_PORTS_FILE, "r") as f:
        used_ports = sorted({int(line.strip()) for line in f if line.strip().isdigit()})

    port = start
    while port in used_ports:
        port += 1

    # Дописываем найденный порт в файл
    with open(USED_PORTS_FILE, "a") as f:
        f.write(f"{port}\n")
    return port

def generate_x25519_keys() -> tuple[str, str]:
    """
    Запускает docker-контейнер teddysun/xray xray x25519 для генерации ключей.
    Возвращает (private_key, public_key).
    """
    proc = subprocess.run(
        ["docker", "run", "--rm", "teddysun/xray", "xray", "x25519"],
        capture_output=True,
        text=True
    )
    out = proc.stdout.splitlines()
    private_key = ""
    public_key = ""
    for line in out:
        if line.startswith("Private key:"):
            private_key = line.split(":", 1)[1].strip()
        elif line.startswith("Public key:"):
            public_key = line.split(":", 1)[1].strip()
    if not private_key or not public_key:
        raise RuntimeError("Не удалось сгенерировать x25519 ключи.")
    return private_key, public_key

def create_config_file(user: str, uuid_str: str, private_key: str, short_id: str, user_dir: Path) -> None:
    """
    Формирует JSON-конфиг для Xray/VLESS и сохраняет в <user_dir>/config.json
    """
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "port": 443,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": uuid_str, "flow": "xtls-rprx-vision"}
                    ],
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": "www.google.com:443",
                        "xver": 0,
                        "serverNames": ["www.google.com"],
                        "privateKey": private_key,
                        "shortIds": [short_id]
                    }
                }
            }
        ],
        "outbounds": [{"protocol": "freedom"}]
    }
    with open(user_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def create_vless_service(user: str, port: int, user_dir: Path) -> None:
    """
    В Docker Swarm создаёт сервис с именем vless-<user>, пробрасывает порт и
    монтирует директорию с конфигом.
    """
    service_name = f"vless-{user}"
    cmd = [
        "docker", "service", "create",
        "--name", service_name,
        "--replicas", "1",
        "--constraint", "node.role == manager",
        "--mount", f"type=bind,src={user_dir},dst=/etc/xray",
        "--publish", f"{port}:443/tcp",
        "--restart-condition", "any",
        "teddysun/xray"
    ]
    subprocess.run(cmd, check=True)

def add_user(user: str) -> None:
    """
    Основная функция регистрации нового пользователя:
      1) Создаёт папку ~/vless-server/<user>
      2) Берёт свободный порт (>=10000)
      3) Генерирует UUID, ключи, short_id
      4) Пишет config.json
      5) Создаёт Docker Swarm сервис
      6) Печатает VLESS‐линк для клиента
    """
    user_dir = CONFIG_PATH / user
    if user_dir.exists():
        print(f"❌ Пользователь «{user}» уже существует")
        sys.exit(1)

    # Создаём директорию для конфига
    user_dir.mkdir(parents=True)
    # 1) свободный порт
    port = get_next_port()

    # 2) UUID
    uuid_str = str(uuid.uuid4())

    # 3) x25519 ключи
    private_key, public_key = generate_x25519_keys()

    # 4) short_id
    short_id = ''.join(random.choice("0123456789abcdef") for _ in range(8))

    # 5) Пишем config.json
    create_config_file(user, uuid_str, private_key, short_id, user_dir)

    # 6) Запускаем Docker Swarm сервис
    create_vless_service(user, port, user_dir)

    # 7) Внешний IP (можно заменить на статический или домен)
    ip = "<ВАШ_СТАТИЧНЫЙ_IP_ИЛИ_ДОМЕН>"

    # 8) Формируем VLESS‐линк
    link = (
        f"vless://{uuid_str}@{ip}:{port}"
        f"?security=reality&encryption=none&alpn=h2,http/1.1&headerType=none"
        f"&fp=chrome&type=tcp&flow=xtls-rprx-vision&sni=www.google.com"
        f"&pbk={public_key}&sid={short_id}#{user}"
    )
    print("✅ Пользователь успешно добавлен.")
    print("VLESS‐ссылка для клиента:")
    print(link)

def remove_user(user: str) -> None:
    """
    Удаляет пользователя:
      1) Останавливает и удаляет сервис vless-<user> в Swarm
      2) Удаляет директорию ~/vless-server/<user>
      3) Удаляет файл used_ports.txt (в упрощенной логике) или очищает порт
    """
    user_dir = CONFIG_PATH / user
    if not user_dir.exists():
        print(f"❌ Пользователь «{user}» не найден")
        sys.exit(1)

    service_name = f"vless-{user}"
    # 1) Удаляем сервис из Swarm
    subprocess.run(["docker", "service", "rm", service_name], check=False)

    # 2) Удаляем файл used_ports.txt (упрощённо). В продакшн лучше хранить
    #    порт → пользователь в JSON/БД и удалять точно этот порт.
    if USED_PORTS_FILE.exists():
        USED_PORTS_FILE.unlink()

    # 3) Удаляем директорию пользователя
    for root, dirs, files in os.walk(user_dir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(user_dir)

    print(f"✅ Пользователь «{user}» удалён.")

def print_usage_and_exit() -> None:
    print("Использование:")
    print("  python3 vless_manager.py add <username>")
    print("  python3 vless_manager.py remove <username>")
    sys.exit(1)

if __name__ == "__main__":
    init_config_dir()

    if len(sys.argv) != 3:
        print_usage_and_exit()

    action = sys.argv[1].lower()
    username = sys.argv[2].strip()

    if action == "add":
        add_user(username)
    elif action == "remove":
        remove_user(username)
    else:
        print_usage_and_exit()
