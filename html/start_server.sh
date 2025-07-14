#!/data/data/com.termux/files/usr/bin/bash

# 进入项目目录
cd /data/data/com.termux/files/home/www/html

# 终止可能存在的旧进程
pkill -f "python app.py"
pkill nginx

# 启动 Nginx
nginx -c $(pwd)/nginx.conf

# 启动 Flask 后端
cd backend
python app.py &

# 获取IP地址
IP_ADDRESS=$(ifconfig | grep 'inet ' | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)
echo "=============================================="
echo "系统已启动！请在其他设备浏览器中访问："
echo "http://$IP_ADDRESS:8888"
echo "=============================================="
