import paramiko
import os
from datetime import datetime

# Настройки сервера
SERVER_HOST = "your_server_ip"  # Замените на IP-адрес вашего сервера
SERVER_PORT = 22  # Порт SSH (обычно 22)
SERVER_USERNAME = "your_username"  # Замените на имя пользователя сервера
# Замените на пароль (или используйте ключ ниже)
SERVER_PASSWORD = "your_password"
# Если используете SSH-ключ вместо пароля, укажите путь к ключу
# SSH_KEY_PATH = "/path/to/your/private/key"

# Путь к локальному файлу
LOCAL_FILE_PATH = "Kayhon.xlsx"  # Убедитесь, что файл находится в этой папке
# Путь на сервере, куда загружаем файл
# Замените на путь на сервере
REMOTE_FILE_PATH = "/path/to/your/server/directory/Kayhon.xlsx"


def upload_file():
    try:
        # Настройка SSH-клиента
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Подключение с паролем
        ssh.connect(SERVER_HOST, port=SERVER_PORT,
                    username=SERVER_USERNAME, password=SERVER_PASSWORD)
        # Если используете SSH-ключ, раскомментируйте следующую строку и закомментируйте предыдущую
        # ssh.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USERNAME, key_filename=SSH_KEY_PATH)

        # Открываем SFTP-сессию
        sftp = ssh.open_sftp()

        # Загружаем файл
        print(f"Uploading {LOCAL_FILE_PATH} to {REMOTE_FILE_PATH}...")
        sftp.put(LOCAL_FILE_PATH, REMOTE_FILE_PATH)
        print("File uploaded successfully!")

        # Закрываем соединения
        sftp.close()
        ssh.close()

    except Exception as e:
        print(f"Error uploading file: {e}")


if __name__ == "__main__":
    # Проверяем, существует ли локальный файл
    if not os.path.exists(LOCAL_FILE_PATH):
        print(f"Local file {LOCAL_FILE_PATH} not found!")
    else:
        upload_file()
