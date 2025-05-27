#!/bin/bash

# Проверка, что скрипт запущен с правами root
if [ "$(id -u)" != "0" ]; then
  echo "Этот скрипт должен быть запущен с правами root (sudo)."
  exit 1
fi

# Установка NFS-сервера
echo "Устанавливаем NFS-сервер..."
apt update
apt install -y nfs-kernel-server

# Создание директории для экспорта
echo "Создаём директорию /export/vless-configs..."
mkdir -p /export/vless-configs
chmod -R 777 /export/vless-configs  # Права для простоты, в продакшене настрой конкретных пользователей

# Настройка экспорта в /etc/exports
echo "Настраиваем экспорт директории..."
echo "/export/vless-configs *(rw,sync,no_subtree_check)" > /etc/exports

# Применение экспорта
echo "Применяем настройки экспорта..."
exportfs -a

# Перезапуск сервиса NFS
echo "Перезапускаем NFS-сервер..."
systemctl restart nfs-kernel-server
systemctl enable nfs-kernel-server

# Настройка брандмауэра (если ufw активен)
if command -v ufw >/dev/null; then
  echo "Открываем порты для NFS в ufw..."
  ufw allow from any to any port nfs
fi

echo "NFS-сервер настроен! Директория /export/vless-configs готова к использованию."