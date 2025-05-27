#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import uuid
import random
import json
import subprocess
import urllib.request
from pathlib import Path

# -------------------------------------------------------------------
#  Константы и пути
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
USED_PORTS_FILE = BASE_DIR / "used_ports.txt"
CONFIG_NAME_PREFIX = "vless-config"   # префикс для docker config: vless-config-<username>


def get_next_port(start: int = 10000) -> int:
    """
    Читает USED_PORTS_FILE (./used_ports.txt), ищет первый свободный порт >= start,
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
        if updated:
            f.write("\n".join(updated) + "\n")
        else:
            f.write("")


def generate_x25519_keys() -> tuple[str, str]:
    """
    Генерирует x25519-ключи через Docker-контейнер teddysun/xray.
    Возвращает (private_key, public_key).
    """
    proc = subprocess.run(
        ["docker", "run", "--rm", "teddysun/xray", "xray", "x25519"],
        capture_output=True,
        text=True
    )
    if proc.returncode != 0:
        print("❌ Ошибка при запуске контейнера teddysun/xray для генерации ключей.")
        print(proc.stderr)
        sys.exit(1)

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


def create_docker_config(username: str, config_json: dict) -> None:
    """
    Создаёт Docker config c именем vless-config-<username> со своим JSON-содержимым.
    Если config с таким именем уже есть — удаляет старый и создаёт заново.
    """
    config_name = f"{CONFIG_NAME_PREFIX}-{username}"

    # Если конфиг с таким именем уже есть, удалим
    subprocess.run(
        ["docker", "config", "rm", config_name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Сериализуем JSON и передаём в stdin для `docker config create`
    json_bytes = json.dumps(config_json, ensure_ascii=False, indent=2).encode("utf-8")
    proc = subprocess.run(
        ["docker", "config", "create", config_name, "-"],
        input=json_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        print(f"❌ Не удалось создать Docker config «{config_name}»")
        print(proc.stderr.decode("utf-8"))
        sys.exit(1)


def create_config_object(username: str, uuid_str: str, private_key: str, short_id: str) -> dict:
    """
    Формирует Python-словарь (dict) с JSON-конфигом для Xray/VLESS.
    Возвращает этот словарь.
    """
    return {
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


def get_external_ip() -> str:
    """
    Определяет внешний публичный IP сервера через сервис api.ipify.org.
    Возвращает строку с IP или пустую строку при ошибке.
    """
    try:
        with urllib.request.urlopen("https://api.ipify.org") as response:
            ip = response.read().decode('utf-8').strip()
            return ip
    except Exception as e:
        print(f"⚠️ Не удалось определить внешний IP: {e}")
        return ""


def create_service(username: str, port: int, target_node: str | None = None) -> None:
    """
    В Docker Swarm создаёт сервис vless-<username>:
      • пробрасывает порт <port>:443/tcp
      • монтирует ранее созданный Docker config (vless-config-<username>) в /etc/xray/config.json
      • (опционально) привязывает сервис к конкретной ноде через --constraint node.hostname==<target_node>
    """
    service_name = f"vless-{username}"
    config_name = f"{CONFIG_NAME_PREFIX}-{username}"

    # Удаляем старый сервис, если вдруг он уже есть (чтобы не было конфликтов)
    subprocess.run(
        ["docker", "service", "rm", service_name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    cmd = [
        "docker", "service", "create",
        "--name", service_name,
        "--replicas", "1",
        "--publish", f"{port}:443/tcp",
        "--restart-condition", "any",
        "--config", f"source={config_name},target=/etc/xray/config.json",
        "teddysun/xray"
    ]
    if target_node:
        cmd.insert(5, "--constraint")
        cmd.insert(6, f"node.hostname=={target_node}")

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"❌ Не удалось создать сервис «{service_name}»")
        print(proc.stderr.decode("utf-8"))
        sys.exit(1)


def remove_user(username: str) -> None:
    """
    Удаляет пользователя:
      1) Останавливает и удаляет сервис vless-<username>
      2) Удаляет Docker config vless-config-<username>
      3) Освобождает порт (если удалось его узнать)
    """
    service_name = f"vless-{username}"
    config_name = f"{CONFIG_NAME_PREFIX}-{username}"

    # 1) Удаляем сервис (игнорируем ошибку, если его нет)
    subprocess.run(["docker", "service", "rm", service_name], check=False)

    # 2) Удаляем Docker config (игнорируем ошибку, если его нет)
    subprocess.run(["docker", "config", "rm", config_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3) Освобождаем порт:
    try:
        inspect = subprocess.run(
            ["docker", "service", "inspect", service_name,
             "--format", "{{json .Spec.Labels}}"],
            capture_output=True, text=True, check=False
        )
        labels = json.loads(inspect.stdout) if inspect.stdout.strip() else {}
        if labels and "vless-port" in labels:
            port_to_release = int(labels["vless-port"])
            release_port(port_to_release)
    except Exception:
        pass

    print(f"✅ Пользователь «{username}» удалён.")


def migrate_user(username: str, target_node: str) -> None:
    """
    Переносит сервис vless-<username> на другую ноду, обновляя constraint:
      • docker service update --constraint-rm ... --constraint-add node.hostname==<target_node> ...
    """
    service_name = f"vless-{username}"

    # Проверим, существует ли сервис
    result = subprocess.run(
        ["docker", "service", "ls", "--filter", f"name={service_name}", "--format", "{{.Name}}"],
        capture_output=True, text=True
    )
    if service_name not in result.stdout.splitlines():
        print(f"❌ Сервис «{service_name}» не найден.")
        sys.exit(1)

    # Получаем текущее Placement (список constraints)
    inspect = subprocess.run(
        ["docker", "service", "inspect", service_name, "--format", "{{json .Spec.TaskTemplate.Placement}}"],
        capture_output=True, text=True
    )
    placement = json.loads(inspect.stdout) if inspect.stdout.strip() else {}
    current_constraints = placement.get("Constraints", []) if placement else []

    # Убираем все node.hostname==* и добавляем новую привязку
    args = ["docker", "service", "update"]
    for c in current_constraints:
        if c.startswith("node.hostname=="):
            args += ["--constraint-rm", c]
    args += ["--constraint-add", f"node.hostname=={target_node}", service_name]

    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        print(f"❌ Не удалось перенести сервис «{service_name}» на ноду «{target_node}»")
        print(proc.stderr.decode("utf-8"))
        sys.exit(1)

    print(f"✅ Сервис «{service_name}» перенесён на ноду «{target_node}».")


def print_usage_and_exit() -> None:
    print("Использование:")
    print("  python3 vless_manager_swarm.py add <username> [--node <имя_ноды>]")
    print("  python3 vless_manager_swarm.py remove <username>")
    print("  python3 vless_manager_swarm.py migrate <username> --to-node <имя_ноды>")
    sys.exit(1)


if __name__ == "__main__":
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

        # 1) Генерация случайных параметров
        port = get_next_port()
        uuid_str = str(uuid.uuid4())
        private_key, public_key = generate_x25519_keys()
        short_id = "".join(random.choice("0123456789abcdef") for _ in range(8))

        # 2) Составляем JSON-конфиг в виде Python-словаря
        config_dict = create_config_object(username, uuid_str, private_key, short_id)

        # 3) Создаём Docker config (внутри Swarm) с этим JSON
        create_docker_config(username, config_dict)

        # 4) Создаём сервис, монтируя только что созданный config
        #    Добавляем метку vless-port=<port>, чтобы потом при удалении узнать порт
        label = f"vless-port={port}"
        cmd_labels = ["--label", label]

        # Формируем команду "docker service create"
        service_name = f"vless-{username}"
        docker_cmd = [
            "docker", "service", "create",
            "--name", service_name,
            "--replicas", "1",
            "--publish", f"{port}:443/tcp",
            "--restart-condition", "any",
            "--config", f"source={CONFIG_NAME_PREFIX}-{username},target=/etc/xray/config.json",
            *cmd_labels,
            "teddysun/xray"
        ]
        if node:
            docker_cmd.insert(5, "--constraint")
            docker_cmd.insert(6, f"node.hostname=={node}")

        proc = subprocess.run(docker_cmd, capture_output=True)
        if proc.returncode != 0:
            print(f"❌ Не удалось создать сервис «{service_name}»")
            print(proc.stderr.decode("utf-8"))
            # Если сервис не создался, удалим созданный config и освободим порт
            subprocess.run(["docker", "config", "rm", f"{CONFIG_NAME_PREFIX}-{username}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            release_port(port)
            sys.exit(1)

        # 5) Собираем VLESS-ссылку для клиента с автоматическим определением IP
        ip_or_domain = get_external_ip()
        if not ip_or_domain:
            # Если IP не удалось получить, оставляем заглушку для ручной подстановки
            ip_or_domain = "<ВАШ_СТАТИЧНЫЙ_IP_ИЛИ_ДОМЕН>"

        vless_link = (
            f"vless://{uuid_str}@{ip_or_domain}:{port}"
            f"?security=reality&encryption=none&alpn=h2,http/1.1&headerType=none"
            f"&fp=chrome&type=tcp&flow=xtls-rprx-vision&sni=www.google.com"
            f"&pbk={public_key}&sid={short_id}#{username}"
        )
        print("✅ Пользователь успешно добавлен.")
        print("VLESS-ссылка для клиента:")
        print(vless_link)

    elif action == "remove":
        # –– удаляем сервис, config и освобождаем порт (через метку)
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
