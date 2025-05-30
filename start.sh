#!/bin/sh
apt update && apt upgrade
wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/start.py/change_hostname.py
chmod +x change_hostname.py
wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/.env
chmod 777 .env
source .env
export $(cat .env | xargs)
apt install -y python3-pip 
pip install aiofiles
python3 change_hostname.py $SERVER_NAME 127.0.1.1
wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/vless_manager.py
chmod +x vless_manager.py