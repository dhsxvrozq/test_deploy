#!/bin/bash

# Конфигурация
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$BASE_DIR/config.json"
USERS_FILE="$BASE_DIR/users.json"
CONTAINER_NAME="xray-server"

# Проверка зависимостей
check_dependencies() {
    command -v docker &>/dev/null || { echo "Ошибка: Docker не установлен"; exit 1; }
    command -v jq &>/dev/null || { echo "Ошибка: jq не установлен"; exit 1; }
    command -v ip &>/dev/null || { echo "Ошибка: iproute2 не установлен"; exit 1; }
}

# Получение IPv6 адреса
get_ipv6() {
    SERVER_IPV6=$(ip -6 addr show scope global | grep -v 'fd' | awk '/inet6/{print $2}' | cut -d'/' -f1 | head -n1)
    if [[ -z "$SERVER_IPV6" ]]; then
        echo "Ошибка: не найден IPv6 адрес"
        exit 1
    fi
    echo "$SERVER_IPV6"
}

# Инициализация файлов конфигурации
init_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cat > "$CONFIG_FILE" <<EOF
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "listen": "::",
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "www.google.com:443",
          "xver": 0,
          "serverNames": ["www.google.com"],
          "privateKey": "$(docker run --rm teddysun/xray xray x25519 | awk '/Private key:/ {print $3}')",
          "shortIds": ["$(head -c 8 /dev/urandom | xxd -p)"]
        }
      }
    }
  ],
  "outbounds": [{"protocol": "freedom"}]
}
EOF
        echo "Создан новый конфиг: $CONFIG_FILE"
    fi

    [[ ! -f "$USERS_FILE" ]] && echo "{}" > "$USERS_FILE"
}

# Запуск/перезапуск контейнера
restart_container() {
    docker stop "$CONTAINER_NAME" &>/dev/null
    docker rm "$CONTAINER_NAME" &>/dev/null
    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart=always \
        --network host \
        -v "$CONFIG_FILE:/etc/xray/config.json" \
        teddysun/xray
}

# Добавление пользователя
add_user() {
    local username=$1
    local uuid=$(uuidgen)
    local config=$(cat "$CONFIG_FILE")
    local users=$(cat "$USERS_FILE")
    local ipv6=$(get_ipv6)
    
    # Обновление users.json
    users=$(echo "$users" | jq --arg u "$username" --arg id "$uuid" '. + {($u): $id}')
    echo "$users" > "$USERS_FILE"
    
    # Обновление конфига Xray
    config=$(echo "$config" | jq \
        --arg id "$uuid" \
        '.inbounds[0].settings.clients += [{"id": $id, "flow": "xtls-rprx-vision"}]')
    
    echo "$config" > "$CONFIG_FILE"
    restart_container

    # Генерация ссылки
    local reality_settings=$(echo "$config" | jq '.inbounds[0].streamSettings.realitySettings')
    local private_key=$(echo "$reality_settings" | jq -r '.privateKey')
    local public_key=$(docker run --rm teddysun/xray xray x25519 -i "$private_key" | awk '/Public key:/ {print $3}')
    local short_id=$(echo "$reality_settings" | jq -r '.shortIds[0]')
    
    echo "✅ Пользователь $username добавлен"
    echo "🔗 VLESS-ссылка:"
    echo "vless://$uuid@[$ipv6]:443?security=reality&encryption=none&alpn=h2,http/1.1&headerType=none&fp=chrome&type=tcp&flow=xtls-rprx-vision&sni=www.google.com&pbk=$public_key&sid=$short_id#$username"
}

# Удаление пользователя
remove_user() {
    local username=$1
    local users=$(cat "$USERS_FILE")
    local user_id=$(echo "$users" | jq -r ".[\"$username\"]")
    
    if [[ -z "$user_id" || "$user_id" == "null" ]]; then
        echo "❌ Пользователь $username не найден"
        exit 1
    fi
    
    # Удаление из users.json
    users=$(echo "$users" | jq "del(.[\"$username\"])")
    echo "$users" > "$USERS_FILE"
    
    # Удаление из конфига Xray
    local config=$(cat "$CONFIG_FILE")
    config=$(echo "$config" | jq \
        --arg id "$user_id" \
        '.inbounds[0].settings.clients |= map(select(.id != $id))')
    
    echo "$config" > "$CONFIG_FILE"
    restart_container
    echo "✅ Пользователь $username удалён"
}

# Основной код
check_dependencies
init_config

case $1 in
    add)
        [[ -z "$2" ]] && { echo "Использование: $0 add <username>"; exit 1; }
        add_user "$2"
        ;;
    remove)
        [[ -z "$2" ]] && { echo "Использование: $0 remove <username>"; exit 1; }
        remove_user "$2"
        ;;
    *)
        echo "Использование:"
        echo "  $0 add <username>    - Добавить пользователя"
        echo "  $0 remove <username> - Удалить пользователя"
        exit 1
        ;;
esac