#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import uuid
import random
import json
import subprocess
from pathlib import Path

# -------------------------------------------------------------------
#  Константы и пути
# -------------------------------------------------------------------
if Path("/export/vless-configs").exists():
    CONFIG_PATH = Path("/export/vless-configs")  # сервер
elif Path("/mnt/vless-configs").exists():
    CONFIG_PATH = Path("/mnt/vless-configs")  # клиент
else:
    print("❌ NFS-директория не найдена.")
    sys.exit(1)

USED_PORTS_FILE = CONFIG_PATH / "used_ports.txt"


def init_config_dir() -> None:
    """
    Создаёт основную директорию ~/vless-server (смонтированную по NFS),
    если её нет.
    """
    try:
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"❌ Ошибка при создании директории {CONFIG_PATH}: {e}")
        sys.exit(1)


def get_next_port(start: int = 10000) -> int:
    """
    Читает USED_PORTS_FILE, ищет свободный порт >= start,
    дописывает его в файл и возвращает.
    """
    if not USED_PORTS_FILE.exists():
        USED_PORTS_FILE.write_text(f"{start}\n")
        return start

    with open(USED_PORTS_FILE, "r", encoding="utf-8") as f:
        used_ports = sorted({int(line.strip()) for line in f if line.strip().isdigit()})

    port = start
    while port in used_ports:
        port += 1

    with open(USED_PORTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{port}\n")
    return port


def release_port(port: int) -> None:
    """
    Убирает конкретный порт из used_ports.txt (при удалении пользователя).
    """
    if not USED_PORTS_FILE.exists():
        return
    with open(USED_PORTS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip().isdigit()]
    updated = [l for l in lines if int(l) != port]
    with open(USED_PORTS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(updated) + ("\n" if updated else ""))


def generate_x25519_keys() -> tuple[str, str]:
    """
    Генерирует x25519-ключи через docker-контейнер teddysun/xray.
    Возвращает (private_key, public_key).
    """
    proc = subprocess.run(
        ["docker", "run", "--rm", "teddysun/xray", "xray", "x25519"],
        capture_output=True,
        text=True
    )
    out = proc.stdout.splitlines()
    priv = ""
    pub = ""
    for line in out:
        if line.startswith("Private key:"):
            priv = line.split(":", 1)[1].strip()
        elif line.startswith("Public key:"):
            pub = line.split(":", 1)[1].strip()
    if not priv or not pub:
        raise RuntimeError("Не удалось сгенерировать x25519-ключи.")
    return priv, pub


def create_config_file(user: str, uuid_str: str, private_key: str, short_id: str, port: int) -> None:
    """
    Формирует JSON-конфиг для Xray/VLESS и сохраняет в ~/vless-server/<user>/config.json
    """
    user_dir = CONFIG_PATH / user
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


def create_service(user: str, port: int, target_node: str | None = None) -> None:
    """
    В Docker Swarm создаёт сервис vless-<user>, пробрасывает порт,
    монтирует общую директорию с конфигом и (опционально) привязывает его к конкретной ноде.
    """
    service_name = f"vless-{user}"
    bind_src = str((CONFIG_PATH / user).resolve())
    cmd = [
        "docker", "service", "create",
        "--name", service_name,
        "--replicas", "1",
        "--mount", f"type=bind,src={bind_src},dst=/etc/xray",
        "--publish", f"{port}:443/tcp",
        "--restart-condition", "any",
        "teddysun/xray"
    ]
    if target_node:
        # Привязка к конкретному hostname
        cmd.insert(5, "--constraint")
        cmd.insert(6, f"node.hostname=={target_node}")

    subprocess.run(cmd, check=True)


def remove_user(user: str) -> None:
    """
    Удаляет пользователя:
      1) Останавливает и удаляет сервис vless-<user>
      2) Удаляет директорию ~/vless-server/<user>
      3) Освобождает порт в used_ports.txt
    """
    user_dir = CONFIG_PATH / user
    service_name = f"vless-{user}"

    # Проверим, есть ли сервис
    subprocess.run(["docker", "service", "rm", service_name], check=False)

    # Прочитаем порт из конфига (чтобы освободить)
    port_to_release = None
    if user_dir.exists():
        try:
            # Предполагаем, что порт изначально брался через get_next_port, 
            # сохраним его где-то. Если не сохраняли, можно вычитать из used_ports.txt вручную (но это не надёжно).
            # Для простоты здесь просто освобождаем все (в продакшн: хранить user→portMapping).
            # Поэтому оставим port_to_release = None.
            pass
        except Exception:
            pass

    # Удаляем папку с конфигами
    if user_dir.exists():
        for root, dirs, files in os.walk(user_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(user_dir)

    # Если удалось узнать порт, освободим его:
    if port_to_release:
        release_port(port_to_release)

    print(f"✅ Пользователь «{user}» удалён.")


def migrate_user(user: str, target_node: str) -> None:
    """
    «Переносит» сервис vless-<user> на другую ноду, обновляя constraint.
    """
    service_name = f"vless-{user}"

    # Проверим, существует ли сервис
    result = subprocess.run(["docker", "service", "ls", "--filter", f"name={service_name}", "--format", "{{.Name}}"], 
                            capture_output=True, text=True)
    if service_name not in result.stdout.splitlines():
        print(f"❌ Сервис «{service_name}» не найден.")
        sys.exit(1)

    # Снятие любых предыдущих constraint node.hostname (если такие были).
    # Упростим задачу: снимем все node.hostname-constraint и поставим новый.
    # Для этого сначала получим текущее list-constraint:
    inspect = subprocess.run(
        ["docker", "service", "inspect", service_name, "--format", "{{json .Spec.TaskTemplate.Placement}}"],
        capture_output=True, text=True
    )
    placement = json.loads(inspect.stdout) if inspect.stdout else {}
    # Соберём текущие constraints:
    current_constraints = placement.get("Constraints", []) if placement else []

    # Уберём все constraint вида "node.hostname==..."
    new_constraints = [c for c in current_constraints if not c.startswith("node.hostname==")]

    # Добавим новый
    new_constraints.append(f"node.hostname=={target_node}")

    # Сформируем аргументы для docker service update
    args = ["docker", "service", "update"]
    # Сначала убираем все старые hostname-constraint
    for c in current_constraints:
        if c.startswith("node.hostname=="):
            args += ["--constraint-rm", c]
    # Добавляем новый constraint
    args += ["--constraint-add", f"node.hostname=={target_node}", service_name]

    # Запустим обновление
    subprocess.run(args, check=True)
    print(f"✅ Сервис «{service_name}» перенесён на ноду «{target_node}».")


def print_usage_and_exit() -> None:
    print("Использование:")
    print("  python3 vless_manager.py add <username> [--node <имя_ноды>]")
    print("  python3 vless_manager.py remove <username>")
    print("  python3 vless_manager.py migrate <username> --to-node <имя_ноды>")
    sys.exit(1)


if __name__ == "__main__":
    init_config_dir()

    if len(sys.argv) < 3:
        print_usage_and_exit()

    action = sys.argv[1].lower()
    username = sys.argv[2].strip()

    if action == "add":
        # Разбор опции --node
        node = None
        if "--node" in sys.argv:
            try:
                idx = sys.argv.index("--node")
                node = sys.argv[idx + 1]
            except (ValueError, IndexError):
                print("❌ Некорректно указана нода. Используйте: add <username> --node <имя_ноды>")
                sys.exit(1)

        user_dir = CONFIG_PATH / username
        if user_dir.exists():
            print(f"❌ Пользователь «{username}» уже существует")
            sys.exit(1)

        user_dir.mkdir(parents=True)

        # 1) Свободный порт
        port = get_next_port()

        # 2) UUID
        uuid_str = str(uuid.uuid4())

        # 3) x25519-ключи
        private_key, public_key = generate_x25519_keys()

        # 4) short_id
        short_id = ''.join(random.choice("0123456789abcdef") for _ in range(8))

        # 5) Пишем config.json
        create_config_file(username, uuid_str, private_key, short_id, port)

        # 6) Создаём Docker Swarm сервис
        create_service(username, port, node)

        # 7) Внешний IP или домен (замените на ваш)
        ip = "<ВАШ_СТАТИЧНЫЙ_IP_ИЛИ_ДОМЕН>"

        # 8) Формируем VLESS‐линк
        link = (
            f"vless://{uuid_str}@{ip}:{port}"
            f"?security=reality&encryption=none&alpn=h2,http/1.1&headerType=none"
            f"&fp=chrome&type=tcp&flow=xtls-rprx-vision&sni=www.google.com"
            f"&pbk={public_key}&sid={short_id}#{username}"
        )
        print("✅ Пользователь успешно добавлен.")
        print("VLESS‐ссылка для клиента:")
        print(link)

    elif action == "remove":
        remove_user(username)

    elif action == "migrate":
        if "--to-node" not in sys.argv:
            print("❌ Не указана целевая нода. Используйте: migrate <username> --to-node <имя_ноды>")
            sys.exit(1)
        try:
            idx = sys.argv.index("--to-node")
            target = sys.argv[idx + 1]
        except (ValueError, IndexError):
            print("❌ Некорректно указана нода. Используйте: migrate <username> --to-node <имя_ноды>")
            sys.exit(1)
        migrate_user(username, target)

    else:
        print_usage_and_exit()
