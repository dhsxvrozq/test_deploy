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
import time

# -------------------------------------------------------------------
# Константы и пути
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
USED_PORTS_FILE = BASE_DIR / "used_ports.txt"
CONFIG_NAME_PREFIX = "vless-config"  # префикс для docker config: vless-config-<username>
RECORD_ID_FILE = BASE_DIR / "record_ids.json"  # файл для хранения RECORD_ID
BASE_DOMAIN = "vpn.example.com"  # базовый домен (настройте под себя)
TTL = 60  # TTL для DNS-записей в секундах

def load_record_ids() -> dict:
    """Загружает RECORD_ID из файла."""
    if RECORD_ID_FILE.exists():
        with open(RECORD_ID_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_record_ids(record_ids: dict) -> None:
    """Сохраняет RECORD_ID в файл."""
    with open(RECORD_ID_FILE, "w", encoding="utf-8") as f:
        json.dump(record_ids, f, indent=2)

def get_next_port(start: int = 10000) -> int:
    """Находит и возвра

щает следующий свободный порт, записывая его в used_ports.txt."""
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
    """Освобождает указанный порт из used_ports.txt."""
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
    """Генерирует x25519-ключи через Docker-контейнер teddysun/xray."""
    proc = subprocess.run(
        ["docker", "run", "--rm", "teddysun/xray", "xray", "x25519"],
        capture_output=True,
        text=True
    )
    if proc.returncode != 0:
        print("❌ Ошибка при генерации ключей x25519.")
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
    """Создаёт Docker config для пользователя."""
    config_name = f"{CONFIG_NAME_PREFIX}-{username}"
    subprocess.run(
        ["docker", "config", "rm", config_name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
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
    """Создаёт JSON-конфиг для Xray/VLESS."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "port": 443,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": uuid_str, "flow": "xtls-rprx-vision"}],
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

def get_node_ip(node_name: str) -> str:
    """Получает IP-адрес ноды в Docker Swarm."""
    try:
        proc = subprocess.run(
            ["docker", "node", "inspect", node_name, "--format", "{{.Status.Addr}}"],
            capture_output=True, text=True, check=True
        )
        return proc.stdout.strip()
    except subprocess.CalledProcessError:
        print(f"⚠️ Не удалось получить IP ноды {node_name}")
        return ""

def create_service(username: str, port: int, target_node: str | None = None) -> None:
    """Создаёт VLESS-сервис в Docker Swarm."""
    service_name = f"vless-{username}"
    config_name = f"{CONFIG_NAME_PREFIX}-{username}"
    subprocess.run(
        ["docker", "service", "rm", service_name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    cmd = [
        "docker", "service", "create",
        "--name", service_name,
        "--replicas", "1",
        "--publish", f"mode=host,target=443,published={port},protocol=tcp",
        "--restart-condition", "any",
        "--config", f"source={config_name},target=/etc/xray/config.json",
        "--label", f"vless-port={port}",
        "teddysun/xray"
    ]
    if target_node:
        cmd.extend(["--constraint", f"node.hostname=={target_node}"])
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"❌ Не удалось создать сервис «{service_name}»")
        print(proc.stderr.decode("utf-8"))
        sys.exit(1)

def add_subdomain(username: str, domain: str = BASE_DOMAIN) -> bool:
    """Добавляет поддомен для пользователя."""
    subdomain = f"{username}.{domain}"
    cmd = ["twc", "domain", "subdomain", "add", subdomain, "--output", "json"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ Поддомен {subdomain} создан.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Не удалось создать поддомен {subdomain}: {e.stderr}")
        return False

def add_dns_record(username: str, ip: str, domain: str = BASE_DOMAIN, ttl: int = TTL) -> str:
    """Добавляет A-запись для поддомена."""
    subdomain = f"{username}.{domain}"
    cmd = [
        "twc", "domain", "record", "add", subdomain,
        "--type", "A", "--value", ip, "--ttl", str(ttl), "--output", "json"
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        result = json.loads(proc.stdout)
        record_id = result.get("id", "")
        print(f"✅ A-запись для {subdomain} создана с IP {ip}.")
        return record_id
    except subprocess.CalledProcessError as e:
        print(f"❌ Не удалось создать A-запись для {subdomain}: {e.stderr}")
        return ""

def update_dns_record(username: str, new_ip: str, record_id: str, domain: str = BASE_DOMAIN, ttl: int = TTL) -> bool:
    """Обновляет A-запись поддомена."""
    subdomain = f"{username}.{domain}"
    cmd = [
        "twc", "domain", "record", "update", subdomain, record_id,
        "--type", "A", "--value", new_ip, "--ttl", str(ttl), "--output", "json"
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ A-запись для {subdomain} обновлена на {new_ip}.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Не удалось обновить A-запись для {subdomain}: {e.stderr}")
        return False

def remove_subdomain(username: str, domain: str = BASE_DOMAIN) -> None:
    """Удаляет поддомен пользователя."""
    subdomain = f"{username}.{domain}"
    cmd = ["twc", "domain", "subdomain", "remove", subdomain, "-y"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ Поддомен {subdomain} удалён.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Не удалось удалить поддомен {subdomain}: {e.stderr}")

def setup_proxy(old_node: str, new_ip: str, port: int, ttl: int = TTL) -> None:
    """Настраивает временное проксирование на старой ноде."""
    old_ip = get_node_ip(old_node)
    if not old_ip:
        print(f"⚠️ Не удалось получить IP старой ноды {old_node}, пропускаем прокси.")
        return

    iptables_cmd = [
        "ssh", f"root@{old_ip}",
        "iptables", "-t", "nat",
        "-A", "PREROUTING", "-p", "tcp", "--dport", str(port),
        "-j", "DNAT", "--to-destination", f"{new_ip}:{port}"
    ]
    iptables_masquerade = [
        "ssh", f"root@{old_ip}",
        "iptables", "-t", "nat",
        "-A", "POSTROUTING", "-j", "MASQUERADE"
    ]
    try:
        subprocess.run(iptables_cmd, check=True, capture_output=True)
        subprocess.run(iptables_masquerade, check=True, capture_output=True)
        print(f"✅ Прокси настроен на {old_node} ({old_ip}) для порта {port} -> {new_ip}:{port}")

        time.sleep(ttl)

        iptables_remove = [
            "ssh", f"root@{old_ip}",
            "iptables", "-t", "nat",
            "-D", "PREROUTING", "-p", "tcp", "--dport", str(port),
            "-j", "DNAT", "--to-destination", f"{new_ip}:{port}"
        ]
        iptables_remove_masquerade = [
            "ssh", f"root@{old_ip}",
            "iptables", "-t", "nat",
            "-D", "POSTROUTING", "-j", "MASQUERADE"
        ]
        subprocess.run(iptables_remove, check=True, capture_output=True)
        subprocess.run(iptables_remove_masquerade, check=True, capture_output=True)
        print(f"✅ Прокси на {old_node} ({old_ip}) удалён.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Ошибка настройки прокси на {old_node}: {e.stderr}")

def remove_user(username: str) -> None:
    """Удаляет пользователя и связанные ресурсы."""
    service_name = f"vless-{username}"
    config_name = f"{CONFIG_NAME_PREFIX}-{username}"
    subdomain = f"{username}.{BASE_DOMAIN}"

    port_to_release = None
    try:
        inspect = subprocess.run(
            ["docker", "service", "inspect", service_name,
             "--format", "{{json .Spec.Labels}}"],
            capture_output=True, text=True, check=False
        )
        if inspect.returncode == 0 and inspect.stdout.strip():
            labels = json.loads(inspect.stdout)
            if "vless-port" in labels:
                port_to_release = int(labels["vless-port"])
    except Exception:
        pass

    subprocess.run(["docker", "service", "rm", service_name], capture_output=True)
    subprocess.run(["docker", "config", "rm", config_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if port_to_release:
        release_port(port_to_release)

    cmd = ["twc", "domain", "record", "list", subdomain, "--output", "json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        records = json.loads(proc.stdout)
        for record in records:
            if record.get("type") == "A" and record.get("name") == subdomain:
                subprocess.run(
                    ["twc", "domain", "record", "remove", subdomain, record.get("id"), "-y"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                print(f"✅ A-запись для {subdomain} удалена.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Не удалось удалить DNS-записи для {subdomain}: {e.stderr}")

    remove_subdomain(username)
    record_ids = load_record_ids()
    if username in record_ids:
        del record_ids[username]
        save_record_ids(record_ids)
    print(f"✅ Пользователь «{username}» удалён.")

def migrate_user(username: str, target_node: str) -> None:
    """Переносит сервис пользователя на новую ноду."""
    service_name = f"vless-{username}"
    subdomain = f"{username}.{BASE_DOMAIN}"

    result = subprocess.run(
        ["docker", "service", "ls", "--filter", f"name={service_name}", "--format", "{{.Name}}"],
        capture_output=True, text=True
    )
    if service_name not in result.stdout.splitlines():
        print(f"❌ Сервис «{service_name}» не найден.")
        sys.exit(1)

    current_node = subprocess.run(
        ["docker", "service", "ps", service_name, "--format", "{{.Node}}"],
        capture_output=True, text=True
    ).stdout.strip()
    if not current_node:
        print(f"⚠️ Не удалось определить текущую ноду сервиса {service_name}.")

    new_ip = get_node_ip(target_node)
    if not new_ip:
        print(f"❌ Не удалось получить IP ноды {target_node}.")
        sys.exit(1)

    inspect = subprocess.run(
        ["docker", "service", "inspect", service_name, "--format", "{{json .Spec.Labels}}"],
        capture_output=True, text=True
    )
    labels = json.loads(inspect.stdout) if inspect.stdout.strip() else {}
    port = int(labels.get("vless-port", 0))
    if not port:
        print(f"❌ Не удалось определить порт сервиса {service_name}.")
        sys.exit(1)

    record_ids = load_record_ids()
    record_id = record_ids.get(username)
    if not record_id:
        print(f"❌ Не найдена RECORD_ID для {subdomain}.")
        sys.exit(1)

    setup_proxy(current_node, new_ip, port)

    inspect = subprocess.run(
        ["docker", "service", "inspect", service_name, "--format", "{{json .Spec.TaskTemplate.Placement}}"],
        capture_output=True, text=True
    )
    placement = json.loads(inspect.stdout) if inspect.stdout.strip() else {}
    current_constraints = placement.get("Constraints", []) if placement else []

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

    if not update_dns_record(username, new_ip, record_id):
        print("⚠️ Перенос успешен, но DNS не обновлён.")
    print(f"✅ Сервис «{service_name}» перенесён на ноду «{target_node}».")

def cleanup_docker_system(auto_confirm: bool = True) -> None:
    """Очищает неиспользуемые Docker-ресурсы."""
    print("🧹 Очистка системы Docker...")
    args = ["docker", "system", "prune", "-f"] if auto_confirm else ["docker", "system", "prune"]
    try:
        subprocess.run(args, check=True)
        print("✅ Очистка завершена.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Ошибка очистки: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python3 vless_manager_swarm.py add <username> [--node <имя_ноды>] | remove <username> | migrate <username> --to-node <имя_ноды>")
        sys.exit(1)

    action = sys.argv[1].lower()
    username = sys.argv[2].strip()

    if action == "add":
        node = None
        if "--node" in sys.argv:
            try:
                idx = sys.argv.index("--node")
                node = sys.argv[idx + 1]
            except (ValueError, IndexError):
                print("❌ Ошибка: --node указан некорректно.")
                sys.exit(1)

        port = get_next_port()
        uuid_str = str(uuid.uuid4())
        private_key, public_key = generate_x25519_keys()
        short_id = "".join(random.choice("0123456789abcdef") for _ in range(8))

        config_dict = create_config_object(username, uuid_str, private_key, short_id)
        create_docker_config(username, config_dict)

        node_ip = get_node_ip(node) if node else ""
        if not add_subdomain(username):
            print("❌ Ошибка создания поддомена, прерываем.")
            subprocess.run(["docker", "config", "rm", f"{CONFIG_NAME_PREFIX}-{username}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            release_port(port)
            sys.exit(1)

        record_id = add_dns_record(username, node_ip)
        if not record_id:
            print("❌ Ошибка создания DNS-записи, прерываем.")
            subprocess.run(["docker", "config", "rm", f"{CONFIG_NAME_PREFIX}-{username}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            release_port(port)
            remove_subdomain(username)
            sys.exit(1)

        record_ids = load_record_ids()
        record_ids[username] = record_id
        save_record_ids(record_ids)

        try:
            create_service(username, port, node)
        except Exception as e:
            print(f"❌ Ошибка создания сервиса: {e}")
            subprocess.run(["docker", "config", "rm", f"{CONFIG_NAME_PREFIX}-{username}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            release_port(port)
            remove_subdomain(username)
            sys.exit(1)

        ip_or_domain = f"{username}.{BASE_DOMAIN}"
        vless_link = (
            f"vless://{uuid_str}@{ip_or_domain}:{port}"
            f"?security=reality&encryption=none&alpn=h2,http/1.1&headerType=none"
            f"&fp=chrome&type=tcp&flow=xtls-rprx-vision&sni=www.google.com"
            f"&pbk={public_key}&sid={short_id}#{username}"
        )
        print("✅ Пользователь успешно добавлен.")
        if node:
            print(f"🎯 Сервис развёрнут на ноде: {node}")
        print("VLESS-ссылка для клиента:")
        print(vless_link)

    elif action == "remove":
        remove_user(username)
        cleanup_docker_system()

    elif action == "migrate":
        if "--to-node" not in sys.argv:
            print("❌ Ошибка: укажите --to-node <имя_ноды>.")
            sys.exit(1)
        try:
            idx = sys.argv.index("--to-node")
            target = sys.argv[idx + 1]
        except (ValueError, IndexError):
            print("❌ Ошибка: --to-node указан некорректно.")
            sys.exit(1)

        migrate_user(username, target)
        cleanup_docker_system()

    else:
        print("Использование: python3 vless_manager_swarm.py add <username> [--node <имя_ноды>] | remove <username> | migrate <username> --to-node <имя_ноды>")
        sys.exit(1)