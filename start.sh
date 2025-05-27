# меняем имя хоста

apt install python3-pip -y
pip install aiofiles
wget https://raw.githubusercontent.com/dhsxvrozq/test_deploy/refs/heads/master/start.py/change_hostname.py
chmod +x change_hostname.py
python3 change_hostname.py node3 127.0.1.1

