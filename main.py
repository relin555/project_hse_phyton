import asyncio
import logging
import sys
import os
import aiohttp
from dotenv import load_dotenv
import json
import random

from aiogram import F, Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка хранилища
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

#  Загрузка JSON с вопросами
with open("question.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Загрузка ключей из
load_dotenv()
TOKEN = os.getenv("TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
print("WEATHER_API_KEY:", WEATHER_API_KEY)
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Помощь")],
            [KeyboardButton(text="Случайное число")],
            [KeyboardButton(text="Генерация котика")],
            [KeyboardButton(text="Погода")],
            [KeyboardButton(text="Игра угадай")],
            [KeyboardButton(text="Фильм на вечер")]
        ],
        resize_keyboard=True
    )

def back_button():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Вернуться в меню")]],
        resize_keyboard=True
    )
@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    help_text = (
        "Вот что я умею:\n\n"
        "Случайное число — выдаю случайное число от 1 до 100.\n"
        "Генерация котика — пришлю случайного милого котика.\n"
        "Погода — покажу погоду в выбранном городе.\n"
        "Игра угадай — маленькая викторина с вопросами.\n"
        "Вернуться в меню — возвращает тебя в главное меню.\n"
        "Фильм на вечер - подберет вам фильм для вечернего просмотра.\n"
    )
    await message.answer(help_text, reply_markup=back_button())

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}!\nВыбери пункт меню:",
        reply_markup=main_menu()
    )


class QuizStates(StatesGroup):
    waiting_for_answer = State()


@dp.message(F.text == "Игра угадай")
async def start_quiz(message: Message, state: FSMContext):
    await state.set_state(QuizStates.waiting_for_answer)
    await state.update_data(current_question=0)
    await send_question(message, state)


async def send_question(message: Message, state: FSMContext):
    user_data = await state.get_data()
    q_index = user_data.get("current_question", 0)

    if q_index >= len(data):
        await message.answer("Поздравляю вы ответили на все вопросы", reply_markup=back_button())
        await state.clear()
        return

    question = data[q_index]["question"]
    options = data[q_index]["options"]

    keyboard_rows = []
    for i in range(0, len(options), 2):
        row = [KeyboardButton(text=opt) for opt in options[i:i + 2]]
        keyboard_rows.append(row)
    keyboard_rows.append([KeyboardButton(text="Вернуться в меню")])

    kb = ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    await message.answer(f"{question}", reply_markup=kb)


@dp.message(QuizStates.waiting_for_answer)
async def handle_answer(message: Message, state: FSMContext):
    if message.text == "Вернуться в меню":
        await go_to_menu(message, state)
        return

    user_data = await state.get_data()
    q_index = user_data.get("current_question", 0)
    correct_answer = data[q_index]["answer"]

    if message.text == correct_answer:
        await message.answer("Верно!")
        await state.update_data(current_question=q_index + 1)
        await send_question(message, state)
    else:
        await message.answer(
            f"Неверно! Правильный ответ: {correct_answer}",
            reply_markup=back_button()
        )
        await state.clear()


@dp.message(F.text == "Случайное число")
async def random_number(message: Message):
    await message.answer(f"Твое число: {random.randint(1, 100)}", reply_markup=back_button())



@dp.message(F.text == "Генерация котика")
async def generation_img(message: Message):
    url = "https://api.thecatapi.com/v1/images/search"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                image_url = data[0]["url"]
                await message.answer_photo(photo=image_url, caption="Вот твой котик", reply_markup=back_button())
            else:
                await message.answer("Не удалось получить котика", reply_markup=back_button())


class WeatherStates(StatesGroup):
    waiting_for_city = State()


async def get_coordinates(city: str):
    url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data:
                    return data[0]["lat"], data[0]["lon"]
    return None, None


async def get_weather_yandex(lat, lon):
    url = f"https://api.weather.yandex.ru/v2/forecast?lat={lat}&lon={lon}"
    headers = {"X-Yandex-API-Key": WEATHER_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                fact = data["fact"]
                desc = {
                    "clear": "Ясно",
                    "partly-cloudy": "Малооблачно",
                    "cloudy": "Облачно",
                    "overcast": "Пасмурно",
                    "drizzle": "Морось",
                    "light-rain": "Лёгкий дождь",
                    "rain": "Дождь",
                    "heavy-rain": "Сильный дождь",
                    "snow": "Снег",
                    "thunderstorm": "Гроза"
                }.get(fact["condition"], fact["condition"])
                return (
                    f"{desc}\n"
                    f"Температура: {fact['temp']}°C (ощущается как {fact['feels_like']}°C)\n"
                    f"Ветер: {fact['wind_speed']} м/с\n"
                    f"Давление: {fact['pressure_mm']} мм рт. ст.\n"
                    f"Влажность: {fact['humidity']}%"
                )
            else:
                return "Не удалось получить погоду"


@dp.message(F.text == "Погода")
async def ask_city(message: Message, state: FSMContext):
    await state.set_state(WeatherStates.waiting_for_city)
    await message.answer("Введи название города:", reply_markup=back_button())


@dp.message(WeatherStates.waiting_for_city)
async def handle_city(message: Message, state: FSMContext):
    if message.text == "Вернуться в меню":
        await go_to_menu(message, state)
        return

    city = message.text.strip()
    lat, lon = await get_coordinates(city)
    if not lat:
        await message.answer("Не удалось определить координаты города", reply_markup=back_button())
        return

    weather_info = await get_weather_yandex(lat, lon)
    await message.answer(f"Погода в {city}:\n\n{weather_info}", reply_markup=back_button())
    await state.clear()
    
@dp.message(F.text == "Фильм на вечер")
async def movie_of_the_evening(message: Message):
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=ru-RU&page={random.randint(1, 10)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                if "results" in data and data["results"]:
                    film = random.choice(data["results"])
                    title = film.get("title")
                    overview = film.get("overview", "Описание отсутствует")
                    poster_path = film.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

                    if poster_url:
                        await message.answer_photo(
                            photo=poster_url,
                            caption=f"{title}\n\n{overview}",
                            reply_markup=back_button()
                        )
                    else:
                        await message.answer(f"🎬 {title}\n\n{overview}", reply_markup=back_button())
                else:
                    await message.answer("Не удалось найти фильм", reply_markup=back_button())
            else:
                await message.answer("Ошибка при получении фильма", reply_markup=back_button())


@dp.message(F.text == "Вернуться в меню")
async def go_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("<--- Возвращаемся в главное меню:", reply_markup=main_menu(), parse_mode=None)
dp.message.register(go_to_menu, F.text == "Вернуться в меню")

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())