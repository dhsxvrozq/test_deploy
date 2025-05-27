#!/bin/bash

# Проверка, что скрипт запущен с правами root
if [ "$(id -u)" != "0" ]; then
  echo "Этот скрипт должен быть запущен с правами root (sudo)."
  exit 1
fi

# Запрос IP-адреса NFS-сервера
read -p "Введите IP-адрес NFS-сервера: " NFS_SERVER_IP
if [ -z "$NFS_SERVER_IP" ]; then
  echo "Ошибка: IP-адрес NFS-сервера не указан."
  exit 1
fi

# Установка NFS-клиента
echo "Устанавливаем NFS-клиент..."
apt update
apt install -y nfs-common

# Создание точки монтирования
echo "Создаём директорию /mnt/vless-configs..."
mkdir -p /mnt/vless-configs

# Монтирование NFS-директории
echo "Монтируем NFS-директорию..."
mount $NFS_SERVER_IP:/export/vless-configs /mnt/vless-configs

# Проверка монтирования
if mountpoint -q /mnt/vless-configs; then
  echo "Директория успешно смонтирована."
else
  echo "Ошибка монтирования. Проверьте настройки NFS-сервера и IP-адрес."
  exit 1
fi

# Добавление в /etc/fstab для автоматического монтирования
echo "Добавляем автоматическое монтирование в /etc/fstab..."
echo "$NFS_SERVER_IP:/export/vless-configs /mnt/vless-configs nfs defaults 0 0" >> /etc/fstab

# Проверка fstab
echo "Проверяем настройки монтирования..."
mount -a
if [ $? -eq 0 ]; then
  echo "NFS-клиент настроен! Директория /mnt/vless-configs готова к использованию."
else
  echo "Ошибка в настройке fstab. Проверьте конфигурацию."
  exit 1
fi