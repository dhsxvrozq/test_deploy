
import os
import asyncio
from typing import Optional
from objects.models import Server  # Импортируем твою Pydantic-модель


async def run_server(server_name: str) -> Optional[str]:
    # """
    # Асинхронно запускает создание сервера с заданным именем.

    # Аргументы:
    #     server_name (str): Имя сервера, который нужно создать.

    # Возвращает:
    #     Optional[str]: ID созданного сервера, если запуск успешен, иначе None.

    # Логика работы:
    # 1. Получает шаблон команды запуска сервера из переменной окружения `RUN_SERVER_CMD`.
    #    Если переменная не установлена — выводит сообщение и завершает работу.
    # 2. Формирует команду запуска, подставляя имя сервера в шаблон.
    # 3. Асинхронно запускает сформированную команду с помощью `asyncio.create_subprocess_shell`.
    # 4. Ждёт завершения процесса и считывает stdout и stderr.
    # 5. Если команда завершилась с ошибкой — выводит stderr и возвращает None.
    # 6. Извлекает ID сервера из последней строки вывода stdout.
    # 7. Выводит ID созданного сервера и возвращает его.

    # Примечание: предполагается, что последняя строка вывода содержит ID сервера в первом столбце.
    # """
    # run_server_cmd = os.getenv('RUN_SERVER_CMD')
    # if not run_server_cmd:
    #     print("Переменная окружения RUN_SERVER_CMD не установлена.")
    #     return None

   


    RUN_SERVER_CMD = f'twc server create \
            --name master-{server_name} \
            --type standard \
            --preset-id 3340 \
            --project-id 1497193 \
            --software-id 25 \
            --image 79 \
            --availability-zone ams-1 \
            --region nl-1 \
            --ssh-key 302545'
                
    

    cmd = RUN_SERVER_CMD.format(server_name=server_name)
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        print("Ошибка при создании сервера:", stderr.decode())
        return None

    output = stdout.decode()
    server_id = output.strip().splitlines()[-1].split()[0]
    print(f"Создан сервер с ID: {server_id}")
    return server_id


async def get_server_info(server_id: str, interval: int = 10) -> Optional[Server]:

    #     """
    # Асинхронно развертывает сервер и отслеживает его статус.

    # Аргументы:
    #     server_id (str): ID сервера, который нужно развернуть.
    #     interval (int): Интервал времени (в секундах) между проверками статуса (по умолчанию 10 секунд).

    # Возвращает:
    #     Optional[Server]: Объект Server, если сервер успешно развернут, иначе None.

    # Логика работы:
    # 1. Входит в бесконечный цикл, чтобы регулярно проверять статус сервера.
    # 2. С помощью `asyncio.create_subprocess_exec` выполняет команду получения информации о сервере.
    # 3. Если команда завершилась с ошибкой — выводит сообщение об ошибке и повторяет попытку через заданный интервал.
    # 4. Если вывод команды некорректен или неполный — сообщает об этом и повторяет попытку позже.
    # 5. Извлекает текущий статус сервера. Если статус `on`, то парсит данные и возвращает объект Server.
    # 6. Если статус `installing`, ожидает и повторяет проверку через заданный интервал.
    # 7. Если получен неожиданный статус — выводит предупреждение и повторяет попытку.
    # 8. При возникновении исключения — выводит информацию об ошибке и повторяет попытку.

    # Примечание: функция предполагает наличие класса `Server`.
    # """
    
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(
                'twc', 'server', 'get', str(server_id),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                print(f"Ошибка выполнения команды: {stderr.decode().strip()}")
                await asyncio.sleep(interval)
                continue

            output = stdout.decode().strip()
            lines = output.splitlines()

            if len(lines) < 2:
                print("Не удалось получить данные о сервере. Повтор через 10 секунд.")
                await asyncio.sleep(interval)
                continue

            status = lines[1].split()[3].lower()
            print(f"Текущий статус: {status}")

            if status == 'on':
                headers = lines[0].split()
                values = lines[1].split()
                server_info = dict(zip(headers, values))
                print('Сервер готов!')
                print(server_info)
                return Server(
                    id=int(server_info['ID']),
                    name=server_info['NAME'],
                    ip=None if server_info['IPV4'] == 'None' else server_info['IPV4'],
                    region=server_info['REGION'],
                    status=server_info['STATUS']
                )

            elif status == 'installing':
                await asyncio.sleep(interval)
            else:
                print(f"Неожиданный статус: {status}. Повтор через 10 секунд.")
                await asyncio.sleep(interval)

        except Exception as e:
            print(f"Ошибка: {e}")
            await asyncio.sleep(interval)


async def create_and_monitor_server(i):
    server_name = str(i)


    server_id = await run_server(server_name)
    server = await get_server_info(server_id)

        # Сохраняем IP в файл
    async with asyncio.Lock():  # защищаем от одновременной записи
        with open("ips.txt", "a") as f:
            f.write(f"ssh root@{server.ip}\n")


async def main():
    tasks = [create_and_monitor_server(i) for i in range(1, 4)]
    await asyncio.gather(*tasks)

# Запуск
asyncio.run(main())