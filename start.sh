# меняем имя хоста

wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/start.py/change_hostname.py
chmod +x change_hostname.py

wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/.env
chmod 400 .env
source .env


apt install python3-pip -y
pip install aiofiles
python3 change_hostname.py $SERVER_NAME 127.0.1.1

wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/vless_manager_swarm.py
chmod +x vless_manager.py
