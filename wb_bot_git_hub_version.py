from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
from threading import Thread
import requests
import threading
import logging
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError

# Токен бота
TELEGRAM_BOT_TOKEN = 'YOUR_TELEGRAM_API_TOKEN'

# Минимальные цены для уведомлений
low_borders = {'PS5 Blu-Ray Slim': 42700,
               'MacBook Air 13': 51000,
               'MacBook m2 16/256': 53500,
               'M2 Midnight 16/256': 51000,
               'Macbook M2 16/256 (другая ссылка)': 52500,
               'PS5 SLIM (друг. ссылка)': 42700,
               'Apple Смартфон iPhone 17 Pro Max 256GB Deep Blue SIM+eSIM': 106000}

# Лучшие цены
best_prices = {
    'PS5 Blu-Ray Slim': {'price': 10 ** 18, 'url': ''},
    'MacBook Air 13': {'price': 10 ** 18, 'url': ''},
    'MacBook m2 16/256': {'price': 10 ** 18, 'url': ''},
    'M2 Midnight 16/256': {'price': 10 ** 18, 'url': ''},
    'Macbook M2 16/256 (другая ссылка)': {'price': 10 ** 18, 'url': ''},
    'PS5 SLIM (друг. ссылка)': {'price': 10 ** 18, 'url': ''},
    'Apple Смартфон iPhone 17 Pro Max 256GB Deep Blue SIM+eSIM': {'price': 10 ** 18, 'url': ''}
}

# Временные лучшие цены для текущего цикла
best_prices_now = {
    'PS5 Blu-Ray Slim': {'price': 10 ** 18, 'url': ''},
    'MacBook Air 13': {'price': 10 ** 18, 'url': ''},
    'MacBook m2 16/256': {'price': 10 ** 18, 'url': ''},
    'M2 Midnight 16/256': {'price': 10 ** 18, 'url': ''},
    'Macbook M2 16/256 (другая ссылка)': {'price': 10 ** 18, 'url': ''},
    'PS5 SLIM (друг. ссылка)': {'price': 10 ** 18, 'url': ''},
    'Apple Смартфон iPhone 17 Pro Max 256GB Deep Blue SIM+eSIM': {'price': 10 ** 18, 'url': ''}
}

# Пользователи, меняющие настройки
changing_min = {
    'PS5 Blu-Ray Slim': set(),
    'MacBook Air 13': set(),
    'MacBook m2 16/256': set(),
    'M2 Midnight 16/256': set(),
    'Macbook M2 16/256 (другая ссылка)': set(),
    'PS5 SLIM (друг. ссылка)': set(),
    'Apple Смартфон iPhone 17 Pro Max 256GB Deep Blue SIM+eSIM': set()
}

# Список для хранения chat_id пользователей
user_chat_ids = set()

# Глобальная переменная для управления циклом
restart_cycle = False

adding_product_steps = {}
adding_url_steps = {}
removing_url_steps = {}
removing_product_steps = {}
renaming_product_steps = {}

def send_telegram_message_to_user(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    response = requests.post(url, data=payload, timeout=10)

def send_telegram_message_to_all(message):
    for chat_id in user_chat_ids:
        send_telegram_message_to_user(chat_id, message)

def restart_parcing_cycle():
    global restart_cycle
    restart_cycle = True

def get_chat_ids():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    data = response.json()
    chat_ids = []
    if data.get('result'):
        for update in data['result']:
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                if chat_id not in chat_ids:
                    chat_ids.append(chat_id)
    return chat_ids

def setup_bot_commands():
    # Базовые команды
    commands = [
        {"command": "start", "description": "Запустить бота"},
        {"command": "current_settings", "description": "Текущие настройки"},
        {"command": "add_product", "description": "Добавить товар"},
        {"command": "add_url", "description": "Добавить ссылку на товар"},
        {"command": "remove_url", "description": "Удалить ссылку на товар"},
        {"command": "remove_product", "description": "Удалить товар"},
        {"command": "rename_product", "description": "Изменить название товара"}
    ]

    # Динамически добавляем команды для каждого продукта
    for product_name in changing_min.keys():
        product_key = product_name.lower().replace(' ', '_').replace('-', '_').replace('/', '_').replace('(', '').replace(')', '')
        commands.append({
            "command": f"set_{product_key}_min",
            "description": f"Поменять минимум {product_name}"
        })

    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setMyCommands",
        json={"commands": commands}
    )

def handle_command(chat_id, text):
    user_chat_ids.add(chat_id)
    product_emojis = ['🎮', '💻', '📱', '⌚', '🎧', '📷']

    # Обработка изменения минимума для любого продукта
    command_processed = False
    for i, product_name in enumerate(changing_min.keys()):
        if chat_id in changing_min[product_name]:
            try:
                new_min = int(text)
                low_borders[product_name] = new_min
                best_prices[product_name] = {'price': 10 ** 18, 'url': ''}
                changing_min[product_name].remove(chat_id)
                emoji = product_emojis[i % len(product_emojis)]
                send_telegram_message_to_user(chat_id, f"✅ Минимальная цена {product_name} изменена на {new_min} руб!")
            except ValueError:
                send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректное число")
            command_processed = True
            restart_parcing_cycle()
            break

    if command_processed:
        return

    # Обработка добавления товара
    if chat_id in adding_product_steps:
        handle_add_product(chat_id, text)
        return

    # Обработка добавления ссылки
    if chat_id in adding_url_steps:
        handle_add_url(chat_id, text)
        return

    # Обработка удаления ссылки
    if chat_id in removing_url_steps:
        handle_remove_url(chat_id, text)
        return

    # Обработка удаления товара
    if chat_id in removing_product_steps:
        handle_remove_product(chat_id, text)
        return

    # Обработка переименования товара
    if chat_id in renaming_product_steps:
        handle_rename_product(chat_id, text)
        return

    # Обработка команд
    if text == '/start':
        send_start_message(chat_id)

     # Обработка команд изменения минимума для любого продукта
    elif any(text == f'/set_{product_name.lower().replace(" ", "_").replace("-", "_").replace("/", "_").replace("(", "").replace(")", "")}_min' for product_name in changing_min.keys()):
        for i, product_name in enumerate(changing_min.keys()):
            product_key = product_name.lower().replace(' ', '_').replace('-', '_').replace('/', '_').replace('(', '').replace(')', '')
            if text == f'/set_{product_key}_min':
                changing_min[product_name].add(chat_id)
                emoji = product_emojis[i % len(product_emojis)]
                send_telegram_message_to_user(chat_id, 
                    f"{emoji} <b>Установите новую минимальную цену для {product_name}</b>\n\n"
                    "📝 Введите число в рублях:\n"
                    "<i>Например: 43000</i>"
                )
                break

    elif text == '/current_settings':
        send_current_settings(chat_id)

    elif text == '/add_product':
        adding_product_steps[chat_id] = {'step': 1}
        send_telegram_message_to_user(chat_id,
            "🆕 <b>Добавление нового товара</b>\n\n"
            "📝 <b>Шаг 1 из 3:</b> Введите название товара:\n"
            "<i>Например: iPhone 15 Pro</i>"
        )

    elif text == '/add_url':
        if not urls:
            send_telegram_message_to_user(chat_id, "❌ Нет товаров для добавления ссылок")
            return

        adding_url_steps[chat_id] = {'step': 1}
        products_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(urls.keys())])
        send_telegram_message_to_user(chat_id,
            "🔗 <b>Добавление ссылки на товар</b>\n\n"
            "📝 <b>Шаг 1 из 2:</b> Выберите товар (введите номер):\n"
            f"{products_list}"
        )

    elif text == '/remove_url':
        if not urls:
            send_telegram_message_to_user(chat_id, "❌ Нет товаров для удаления ссылок")
            return

        removing_url_steps[chat_id] = {'step': 1}
        products_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(urls.keys())])
        send_telegram_message_to_user(chat_id,
            "🗑️ <b>Удаление ссылки на товар</b>\n\n"
            "📝 <b>Шаг 1 из 2:</b> Выберите товар (введите номер):\n"
            f"{products_list}"
        )

    elif text == '/remove_product':
        if not urls:
            send_telegram_message_to_user(chat_id, "❌ Нет товаров для удаления")
            return

        removing_product_steps[chat_id] = {'step': 1}
        products_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(urls.keys())])
        send_telegram_message_to_user(chat_id,
            "🗑️ <b>Удаление товара</b>\n\n"
            "📝 <b>Шаг 1 из 1:</b> Выберите товар для удаления (введите номер):\n"
            f"{products_list}\n\n"
            "⚠️ <b>Внимание:</b> Это удалит товар и все его ссылки!"
        )

    elif text == '/rename_product':
        if not urls:
            send_telegram_message_to_user(chat_id, "❌ Нет товаров для переименования")
            return

        renaming_product_steps[chat_id] = {'step': 1}
        products_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(urls.keys())])
        send_telegram_message_to_user(chat_id,
            "✏️ <b>Изменение названия товара</b>\n\n"
            "📝 <b>Шаг 1 из 2:</b> Выберите товар (введите номер):\n"
            f"{products_list}"
        )

def handle_add_product(chat_id, text):
    step_data = adding_product_steps[chat_id]

    if step_data['step'] == 1:
        # Шаг 1: Получаем название товара
        if text in urls:
            send_telegram_message_to_user(chat_id, "❌ Товар с таким названием уже существует")
            del adding_product_steps[chat_id]
            return

        step_data['name'] = text
        step_data['step'] = 2
        send_telegram_message_to_user(chat_id,
            "💰 <b>Шаг 2 из 3:</b> Введите минимальную цену для уведомлений (в рублях):\n"
            "<i>Например: 50000</i>"
        )

    elif step_data['step'] == 2:
        # Шаг 2: Получаем минимальную цену
        try:
            border = int(text)
            step_data['border'] = border
            step_data['step'] = 3
            send_telegram_message_to_user(chat_id,
                "🔗 <b>Шаг 3 из 3:</b> Введите первую ссылку на товар:\n"
                "<i>Например: https://www.wildberries.ru/catalog/.../detail.aspx</i>"
            )
        except ValueError:
            send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректное число")

    elif step_data['step'] == 3:
        restart_parcing_cycle()
        # Шаг 3: Получаем ссылку и создаем товар
        url = text
        product_name = step_data['name']

        # Добавляем товар во все словари
        urls[product_name] = [url]
        low_borders[product_name] = step_data['border']
        best_prices[product_name] = {'price': 10 ** 18, 'url': ''}
        best_prices_now[product_name] = {'price': 10 ** 18, 'url': ''}
        changing_min[product_name] = set()

        # Переустанавливаем команды бота
        setup_bot_commands()

        send_telegram_message_to_user(chat_id,
            f"✅ <b>Товар '{product_name}' успешно добавлен!</b>\n\n"
            f"📊 Минимальная цена: {step_data['border']} руб\n"
            f"🔗 Первая ссылка: {url}\n\n"
            "🔄 Команды бота обновлены\n"
            "🔄 Цикл парсинга перезапущен"
        )
        del adding_product_steps[chat_id]

def handle_add_url(chat_id, text):
    step_data = adding_url_steps[chat_id]

    if step_data['step'] == 1:
        # Шаг 1: Выбор товара
        try:
            product_index = int(text) - 1
            product_names = list(urls.keys())
            if 0 <= product_index < len(product_names):
                step_data['product'] = product_names[product_index]
                step_data['step'] = 2
                send_telegram_message_to_user(chat_id,
                    f"🔗 <b>Шаг 2 из 2:</b> Введите новую ссылку для товара '{step_data['product']}':\n"
                    "<i>Например: https://www.wildberries.ru/catalog/.../detail.aspx</i>"
                )
            else:
                send_telegram_message_to_user(chat_id, "❌ Неверный номер товара")
        except ValueError:
            send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректный номер")

    elif step_data['step'] == 2:
        restart_parcing_cycle()
        # Шаг 2: Добавление ссылки
        url = text
        product_name = step_data['product']
        if url in urls[product_name]:
            send_telegram_message_to_user(chat_id, "❌ Эту ссылку вы уже добавляли")
            del adding_url_steps[chat_id]
            return   
        urls[product_name].append(url)
        send_telegram_message_to_user(chat_id,
            f"✅ <b>Ссылка добавлена к товару '{product_name}'!</b>\n\n"
            f"🔗 Новая ссылка: {url}\n"
            f"📊 Всего ссылок: {len(urls[product_name])}\n\n"
            "🔄 Цикл парсинга перезапущен"
        )
        del adding_url_steps[chat_id]

def handle_remove_url(chat_id, text):
    step_data = removing_url_steps[chat_id]

    if step_data['step'] == 1:
        # Шаг 1: Выбор товара
        try:
            product_index = int(text) - 1
            product_names = list(urls.keys())
            if 0 <= product_index < len(product_names):
                product_name = product_names[product_index]
                if len(urls[product_name]) <= 1:
                    send_telegram_message_to_user(chat_id, "❌ Нельзя удалить последнюю ссылку товара")
                    del removing_url_steps[chat_id]
                    return

                step_data['product'] = product_name
                step_data['step'] = 2

                # Показываем список ссылок для удаления
                urls_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(urls[product_name])])
                send_telegram_message_to_user(chat_id,
                    f"🗑️ <b>Шаг 2 из 2:</b> Выберите ссылку для удаления из товара '{product_name}':\n"
                    f"{urls_list}"
                )
            else:
                send_telegram_message_to_user(chat_id, "❌ Неверный номер товара")
        except ValueError:
            send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректный номер")

    elif step_data['step'] == 2:
        restart_parcing_cycle()
        # Шаг 2: Удаление ссылки
        try:
            url_index = int(text) - 1
            product_name = step_data['product']
            if 0 <= url_index < len(urls[product_name]):
                removed_url = urls[product_name].pop(url_index)

                send_telegram_message_to_user(chat_id,
                    f"✅ <b>Ссылка удалена из товара '{product_name}'!</b>\n\n"
                    f"🔗 Удаленная ссылка: {removed_url}\n"
                    f"📊 Осталось ссылок: {len(urls[product_name])}\n\n"
                    "🔄 Цикл парсинга перезапущен"
                )
            else:
                send_telegram_message_to_user(chat_id, "❌ Неверный номер ссылки")
        except ValueError:
            send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректный номер")
        finally:
            del removing_url_steps[chat_id]

def handle_remove_product(chat_id, text):
    step_data = removing_product_steps[chat_id]

    try:
        product_index = int(text) - 1
        product_names = list(urls.keys())
        if 0 <= product_index < len(product_names):
            product_name = product_names[product_index]
            restart_parcing_cycle()
            # Удаляем товар из всех словарей
            del urls[product_name]
            del low_borders[product_name]
            del best_prices[product_name]
            del best_prices_now[product_name]
            del changing_min[product_name]

            # Переустанавливаем команды бота
            setup_bot_commands()

            send_telegram_message_to_user(chat_id,
                f"✅ <b>Товар '{product_name}' успешно удален!</b>\n\n"
                "🔄 Команды бота обновлены\n"
                "🔄 Цикл парсинга перезапущен"
            )
        else:
            send_telegram_message_to_user(chat_id, "❌ Неверный номер товара")
    except ValueError:
        send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректный номер")
    finally:
        del removing_product_steps[chat_id]

def handle_rename_product(chat_id, text):
    step_data = renaming_product_steps[chat_id]

    if step_data['step'] == 1:
        # Шаг 1: Выбор товара
        try:
            product_index = int(text) - 1
            product_names = list(urls.keys())
            if 0 <= product_index < len(product_names):
                step_data['old_name'] = product_names[product_index]
                step_data['step'] = 2
                send_telegram_message_to_user(chat_id,
                    f"✏️ <b>Шаг 2 из 2:</b> Введите новое название для товара '{step_data['old_name']}':\n"
                    "<i>Например: iPhone 15 Pro Max</i>"
                )
            else:
                send_telegram_message_to_user(chat_id, "❌ Неверный номер товара")
        except ValueError:
            send_telegram_message_to_user(chat_id, "❌ Пожалуйста, введите корректный номер")

    elif step_data['step'] == 2:
        restart_parcing_cycle()
        # Шаг 2: Переименование
        new_name = text
        old_name = step_data['old_name']

        if new_name in urls:
            send_telegram_message_to_user(chat_id, "❌ Товар с таким названием уже существует")
            del renaming_product_steps[chat_id]
            return

        # Переименовываем во всех словарях
        urls[new_name] = urls.pop(old_name)
        low_borders[new_name] = low_borders.pop(old_name)
        best_prices[new_name] = best_prices.pop(old_name)
        best_prices_now[new_name] = best_prices_now.pop(old_name)
        changing_min[new_name] = changing_min.pop(old_name)

        # Переустанавливаем команды бота
        setup_bot_commands()

        send_telegram_message_to_user(chat_id,
            f"✅ <b>Товар успешно переименован!</b>\n\n"
            f"📝 Было: {old_name}\n"
            f"📝 Стало: {new_name}\n\n"
            "🔄 Команды бота обновлены\n"
            "🔄 Цикл парсинга перезапущен"
        )
        del renaming_product_steps[chat_id]

def send_start_message(chat_id):
    product_emojis = ['🎮', '💻', '📱', '⌚', '🎧', '📷']
    settings_text = ""
    for i, product_name in enumerate(low_borders.keys()):
        emoji = product_emojis[i % len(product_emojis)]
        settings_text += f"{emoji} {product_name} минимум: {low_borders[product_name]} руб\n"

    commands_text = ""
    for i, product_name in enumerate(changing_min.keys()):
        emoji = product_emojis[i % len(product_emojis)]
        product_key = product_name.lower().replace(' ', '_').replace('-', '_').replace('/', '_').replace('(', '').replace(')', '')
        commands_text += f"/set_{product_key}_min - изменить минимум {product_name}\n"

    send_telegram_message_to_user(chat_id, 
        f"🚀 <b>Бот мониторинга цен запущен!</b>\n\n"
        f"📊 <b>Текущие настройки:</b>\n{settings_text}\n"
        f"⚙️ <b>Основные команды:</b>\n"
        f"/add_product - добавить товар\n"
        f"/add_url - добавить ссылку\n"
        f"/remove_url - удалить ссылку\n"
        f"/remove_product - удалить товар\n"
        f"/rename_product - изменить название\n"
        f"/current_settings - текущие настройки\n\n"
        f"🎯 <b>Команды для товаров:</b>\n{commands_text}"
    )

def send_current_settings(chat_id):
    product_emojis = ['🎮', '💻', '📱', '⌚', '🎧', '📷']
    settings_text = ""
    best_prices_text = ""

    for i, product_name in enumerate(best_prices.keys()):
        emoji = product_emojis[i % len(product_emojis)]
        product_info = best_prices[product_name]

        # Текущие настройки
        settings_text += f"{emoji} {product_name} минимум: {low_borders[product_name]} руб\n"

        # Лучшие цены
        price_display = f"{product_info['price']} руб" if product_info['price'] < 10 ** 18 else 'не найдена (товара нет в наличии)'
        best_prices_text += f"🏆 Лучшая цена {product_name}: {price_display}\n🔗 {product_info['url']}\n\n"

    send_telegram_message_to_user(chat_id,
        f"⚙️ <b>Текущие настройки:</b>\n\n{settings_text}\n{best_prices_text}"
    )

def parsing_cycle():
    global restart_cycle
    restart_cycle = False
    cycle_count = 0

    while True:
        restart_cycle = False
        # Сбрасываем временные лучшие цены
        for product in best_prices_now:
            best_prices_now[product] = {'price': 10 ** 18, 'url': ''}

        cycle_count += 1
        print(f"🔄 Цикл проверки #{cycle_count}...")

        threads = []
        # Проходим по всем продуктам и их URL
        for product_name, product_urls in urls.items():
            for url in product_urls:
                thread = Thread(target=open_tab_selenium, args=(url, product_name))
                threads.append(thread)
                thread.start()
                if restart_cycle:
                    break
                time.sleep(3)
            if restart_cycle:
                break
        time.sleep(10)
        # Ждем завершения всех потоков
        for thread in threads:
            thread.join()

        if restart_cycle:
            continue

        # Обновляем глобальные лучшие цены
        for product in best_prices_now:
            best_prices[product] = best_prices_now[product].copy()

        # Проверяем и отправляем уведомления
        for product_name in best_prices:
            current_price = best_prices[product_name]['price']
            current_url = best_prices[product_name]['url']

            if current_price < low_borders[product_name]:
                message = f'🎉 <b>Цена на {product_name} достигла цели!</b>\n💰 Цена: {current_price} руб.\n🔗 Ссылка: {current_url}'

                send_telegram_message_to_all(message)
                print(f"Отправлено уведомление о {product_name}: {current_price}")
                low_borders[product_name] = current_price

        print(f"⏰ Цикл #{cycle_count} завершен, ждем 5 минут...")

        # Ждем 5 минут, но проверяем флаг перезапуска каждую секунду
        for _ in range(10):
            if restart_cycle:
                break
            time.sleep(1)
        print(f'\n\n\nСловарь ссылок:\n{urls}\n')
        print(f'Минимальные цены для уведомлений:\n{low_borders}\n\n\n')

def open_tab_selenium(url, product_name):
    if restart_cycle:
        driver.quit()
        return
    try:
        driver.get(url)
        xpath = {
            'price': '//span[@class="priceBlockPrice--xf8pi"]//ins'
        }
        time.sleep(5)
        element = driver.find_element(By.XPATH, xpath['price'])
        value = element.text.strip().replace(' ', '').replace('₽', '')
        value_end = int(int(value) * 0.93)
        print(f"Найдена цена: {value_end} для {product_name} - {url}")

        if value_end < best_prices_now[product_name]['price']:
            best_prices_now[product_name]['price'] = value_end
            best_prices_now[product_name]['url'] = url

    except Exception as e:
        print(f'Нет в наличии ({url})')

    driver.quit()

if __name__ == "__main__":
    print("🚀 Запуск бота...")

    # Загружаем существующих пользователей
    existing_chats = get_chat_ids()
    user_chat_ids.update(existing_chats)

    # Установка команд
    setup_bot_commands()

     # Запускаем polling с автоматическим восстановлением
    polling_thread = Thread(target=start_polling_with_restart)
    polling_thread.daemon = True
    polling_thread.start()
    print("✅ Устойчивый polling запущен")

    urls = {'PS5 Blu-Ray Slim': ['https://www.wildberries.ru/catalog/307521301/detail.aspx?size=466137463', 
                                 'https://www.wildberries.ru/catalog/473866619/detail.aspx?size=664048149', 
                                 'https://www.wildberries.ru/catalog/367514477/detail.aspx?size=538069520', 
                                 'https://www.wildberries.ru/catalog/307519101/detail.aspx?size=466134711', 
                                 'https://www.wildberries.ru/catalog/196486696/detail.aspx?size=318900742',
                                 'https://www.wildberries.ru/catalog/585854921/detail.aspx?size=800735860',
                                 'https://www.wildberries.ru/catalog/287517250/detail.aspx?size=439564813',
                                 'https://www.wildberries.ru/catalog/195963782/detail.aspx?size=318227474',
                                 'https://www.wildberries.ru/catalog/275190071/detail.aspx?size=424320334'],
            'MacBook Air 13': ['https://www.wildberries.ru/catalog/318450890/detail.aspx?size=480116768', 
                               'https://www.wildberries.ru/catalog/451710090/detail.aspx?size=637760871',
                               'https://www.wildberries.ru/catalog/274497515/detail.aspx?size=423340339',
                               'https://www.wildberries.ru/catalog/283834896/detail.aspx?size=434992965',
                               'https://www.wildberries.ru/catalog/516622771/detail.aspx?size=714174862'],
            'MacBook m2 16/256': ['https://www.wildberries.ru/catalog/498549847/detail.aspx?size=693014409'],
            'M2 Midnight 16/256': ['https://www.wildberries.ru/catalog/597147488/detail.aspx?size=814025272',
                                   'https://www.wildberries.ru/catalog/541579851/detail.aspx?size=746030908'],
            'Macbook M2 16/256 (другая ссылка)': ['https://www.wildberries.ru/catalog/593269739/detail.aspx?size=809161016'], 
            'PS5 SLIM (друг. ссылка)': ['https://www.wildberries.ru/catalog/559443494/detail.aspx?size=768330523'],
            'Apple Смартфон iPhone 17 Pro Max 256GB Deep Blue SIM+eSIM': ['https://www.wildberries.ru/catalog/519221907/detail.aspx?size=717927243',
                                                                          'https://www.wildberries.ru/catalog/565691450/detail.aspx?size=775980109']}

    # Запускаем цикл парсинга в отдельном потоке
    cycle_thread = Thread(target=parsing_cycle)
    cycle_thread.daemon = True
    cycle_thread.start()
    print("✅ Цикл парсинга запущен")

while True:
    time.sleep(1)
