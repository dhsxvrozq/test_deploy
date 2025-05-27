import asyncio
import aiofiles
import os
import sys

async def set_hostname(new_hostname, ip_address="127.0.1.1"):
    # Установить новое имя хоста
    await asyncio.create_subprocess_shell(f"hostnamectl set-hostname {new_hostname}")

    # Записать новое имя хоста в /etc/hostname
    async with aiofiles.open("/etc/hostname", "w") as f:
        await f.write(new_hostname + "\n")

    # Прочитать текущий /etc/hosts
    async with aiofiles.open("/etc/hosts", "r") as f:
        lines = await f.readlines()

    # Подготовить новые строки
    new_lines = []
    for line in lines:
        if "127.0.0.1" in line and "localhost" in line:
            new_lines.append("127.0.0.1\tlocalhost\n")
        elif new_hostname in line or "127.0.1.1" in line:
            continue  # Удалим старые упоминания
        else:
            new_lines.append(line)
    new_lines.append(f"{ip_address}\t{new_hostname}\n")

    # Перезаписать /etc/hosts
    async with aiofiles.open("/etc/hosts", "w") as f:
        await f.writelines(new_lines)

    # Применить изменения
    await asyncio.create_subprocess_shell("hostname -F /etc/hostname")
    await asyncio.create_subprocess_shell("systemctl restart systemd-hostnamed")

# Запуск из командной строки
if __name__ == "__main__":

    hostname = 'node3'
    ip = "127.0.1.1"

    asyncio.run(set_hostname(hostname, ip))
