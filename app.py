from __future__ import annotations

import csv
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from io import StringIO
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-before-production')

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)
DATABASE_FILE = DATA_DIR / 'site.db'
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

STATUSES = ['Новая', 'Подтверждена', 'Отклонена']
PRICE_TYPES = ['fixed', 'per_guest_night', 'free', 'custom']

DEFAULT_ROOMS: dict[str, dict[str, Any]] = {
    'Домик': {
        'capacity': 4,
        'weekday_price': 4000,
        'weekend_price': 5500,
        'description': 'Отдельный домик для семейного отдыха или небольшой компании.',
        'amenities': ['4 спальных места', 'отопление', 'мангальная зона', 'парковка'],
        'image': 'img/domiki.png',
        'badge': 'Для семьи',
        'sort_order': 10,
        'is_active': 1,
    },
    'Люкс': {
        'capacity': 5,
        'weekday_price': 4000,
        'weekend_price': 6000,
        'description': 'Просторный номер повышенной комфортности для семьи или компании.',
        'amenities': ['до 5 гостей', 'душ', 'Wi-Fi', 'удобная зона отдыха'],
        'image': 'img/terra.png',
        'badge': 'Популярно',
        'sort_order': 20,
        'is_active': 1,
    },
    'Полулюкс': {
        'capacity': 3,
        'weekday_price': 3500,
        'weekend_price': 5000,
        'description': 'Компактный вариант для пары или небольшой семьи.',
        'amenities': ['до 3 гостей', 'отопление', 'постельные принадлежности', 'парковка'],
        'image': 'img/bereg.png',
        'badge': 'Компактно',
        'sort_order': 30,
        'is_active': 1,
    },
    'Стандарт': {
        'capacity': 4,
        'weekday_price': 3500,
        'weekend_price': 5000,
        'description': 'Практичный номер для спокойного отдыха без лишних затрат.',
        'amenities': ['до 4 гостей', 'базовые удобства', 'доступ к территории', 'парковка'],
        'image': 'img/lesok.png',
        'badge': 'Практично',
        'sort_order': 40,
        'is_active': 1,
    },
}

DEFAULT_SERVICES: list[dict[str, Any]] = [
    {
        'code': 'bathhouse',
        'name': 'Баня',
        'description': 'Можно добавить баню при бронировании и сразу увидеть её в расчёте стоимости.',
        'price': 3000,
        'price_type': 'fixed',
        'icon': 'fa-solid fa-hot-tub-person',
        'display_on_site': 1,
        'available_in_booking': 1,
        'sort_order': 10,
        'is_active': 1,
    },
    {
        'code': 'breakfast',
        'name': 'Завтраки',
        'description': 'Дополнительная опция для гостей, рассчитывается автоматически по количеству человек и ночей.',
        'price': 500,
        'price_type': 'per_guest_night',
        'icon': 'fa-solid fa-utensils',
        'display_on_site': 1,
        'available_in_booking': 1,
        'sort_order': 20,
        'is_active': 1,
    },
    {
        'code': 'parking',
        'name': 'Парковка',
        'description': 'Бесплатная парковка отмечена как доступная услуга прямо в форме бронирования.',
        'price': 0,
        'price_type': 'free',
        'icon': 'fa-solid fa-car',
        'display_on_site': 1,
        'available_in_booking': 1,
        'sort_order': 30,
        'is_active': 1,
    },
    {
        'code': 'consultation',
        'name': 'Быстрая связь',
        'description': 'Можно оставить комментарий к заявке и уточнить детали по телефону или в Месседжер.',
        'price': 0,
        'price_type': 'custom',
        'icon': 'fa-solid fa-comments',
        'display_on_site': 1,
        'available_in_booking': 0,
        'sort_order': 40,
        'is_active': 1,
    },
]


def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_columns(db: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row['name'] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def init_db() -> None:
    with get_db() as db:
        db.executescript(
            '''
            CREATE TABLE IF NOT EXISTS rooms (
                name TEXT PRIMARY KEY,
                capacity INTEGER NOT NULL,
                weekday_price INTEGER NOT NULL,
                weekend_price INTEGER NOT NULL,
                description TEXT NOT NULL,
                amenities TEXT NOT NULL,
                image TEXT NOT NULL,
                badge TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS services (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL DEFAULT 0,
                price_type TEXT NOT NULL DEFAULT 'fixed',
                icon TEXT NOT NULL DEFAULT 'fa-solid fa-circle',
                display_on_site INTEGER NOT NULL DEFAULT 1,
                available_in_booking INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS gallery_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                image TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                guest_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                cottage TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                nights INTEGER NOT NULL,
                guests INTEGER NOT NULL,
                extras TEXT,
                comment TEXT,
                total_price INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Новая'
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            '''
        )

        ensure_columns(db, 'rooms', {
            'sort_order': 'INTEGER NOT NULL DEFAULT 0',
            'is_active': 'INTEGER NOT NULL DEFAULT 1',
        })

        for name, room in DEFAULT_ROOMS.items():
            db.execute(
                '''
                INSERT OR IGNORE INTO rooms (
                    name, capacity, weekday_price, weekend_price, description,
                    amenities, image, badge, sort_order, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    name,
                    room['capacity'],
                    room['weekday_price'],
                    room['weekend_price'],
                    room['description'],
                    '; '.join(room['amenities']),
                    room['image'],
                    room['badge'],
                    room['sort_order'],
                    room['is_active'],
                ),
            )

        for service in DEFAULT_SERVICES:
            db.execute(
                '''
                INSERT OR IGNORE INTO services (
                    code, name, description, price, price_type, icon,
                    display_on_site, available_in_booking, sort_order, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    service['code'],
                    service['name'],
                    service['description'],
                    service['price'],
                    service['price_type'],
                    service['icon'],
                    service['display_on_site'],
                    service['available_in_booking'],
                    service['sort_order'],
                    service['is_active'],
                ),
            )

        default_gallery = [
            ('Береговая зона', 'img/bereg.png', 10),
            ('Домики', 'img/domiki.png', 20),
            ('Баня', 'img/banya.png', 30),
            ('Территория', 'img/terra.png', 40),
            ('Спокойный отдых', 'img/lesok.png', 50),
        ]
        for title, image, sort_order in default_gallery:
            db.execute(
                '''
                INSERT OR IGNORE INTO gallery_photos (title, image, sort_order, is_active)
                VALUES (?, ?, ?, 1)
                ''',
                (title, image, sort_order),
            )

        admin_username = os.getenv('ADMIN_USERNAME', 'Olesya')
        admin_password = os.getenv('ADMIN_PASSWORD', 'RbJ-XmK-n2v-3Sf')

        if admin_username.lower() != 'admin':
            db.execute('DELETE FROM admins WHERE username = ?', ('admin',))

        existing_admin = db.execute(
            'SELECT id FROM admins WHERE username = ?',
            (admin_username,),
        ).fetchone()
        password_hash = generate_password_hash(admin_password)
        if existing_admin:
            db.execute(
                'UPDATE admins SET password_hash = ? WHERE username = ?',
                (password_hash, admin_username),
            )
        else:
            db.execute(
                'INSERT INTO admins (username, password_hash) VALUES (?, ?)',
                (admin_username, password_hash),
            )


def split_amenities(value: str) -> list[str]:
    parts = re.split(r'[;\n]+', value or '')
    return [part.strip() for part in parts if part.strip()]


def room_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'name': row['name'],
        'capacity': int(row['capacity']),
        'weekday_price': int(row['weekday_price']),
        'weekend_price': int(row['weekend_price']),
        'description': row['description'],
        'amenities': split_amenities(row['amenities']),
        'amenities_text': '\n'.join(split_amenities(row['amenities'])),
        'image': row['image'],
        'badge': row['badge'],
        'sort_order': int(row['sort_order']),
        'is_active': int(row['is_active']),
    }


def service_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'code': row['code'],
        'name': row['name'],
        'description': row['description'],
        'price': int(row['price']),
        'price_type': row['price_type'],
        'icon': row['icon'],
        'display_on_site': int(row['display_on_site']),
        'available_in_booking': int(row['available_in_booking']),
        'sort_order': int(row['sort_order']),
        'is_active': int(row['is_active']),
    }


def get_rooms(include_inactive: bool = False) -> dict[str, dict[str, Any]]:
    where = '' if include_inactive else 'WHERE is_active = 1'
    with get_db() as db:
        rows = db.execute(
            f'SELECT * FROM rooms {where} ORDER BY sort_order ASC, name ASC'
        ).fetchall()
    return {row['name']: room_to_dict(row) for row in rows}


def get_room_list(include_inactive: bool = False) -> list[dict[str, Any]]:
    return list(get_rooms(include_inactive=include_inactive).values())


def get_services(include_inactive: bool = False) -> list[dict[str, Any]]:
    where = '' if include_inactive else 'WHERE is_active = 1'
    with get_db() as db:
        rows = db.execute(
            f'SELECT * FROM services {where} ORDER BY sort_order ASC, name ASC'
        ).fetchall()
    return [service_to_dict(row) for row in rows]


def get_service_map(include_inactive: bool = False) -> dict[str, dict[str, Any]]:
    return {service['code']: service for service in get_services(include_inactive=include_inactive)}


def allowed_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_IMAGE_EXTENSIONS


def unique_upload_name(original_filename: str) -> str:
    safe_name = secure_filename(original_filename)
    suffix = Path(safe_name).suffix.lower()
    stem = Path(safe_name).stem or 'photo'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'{stem}_{stamp}_{secrets.token_hex(4)}{suffix}'


def get_image_files() -> list[str]:
    files: list[str] = []
    for folder_name in ('img', 'uploads'):
        image_dir = BASE_DIR / 'static' / folder_name
        if not image_dir.exists():
            continue
        for item in sorted(image_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
                files.append(f'{folder_name}/{item.name}')
    return files


def gallery_photo_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'id': int(row['id']),
        'title': row['title'],
        'image': row['image'],
        'sort_order': int(row['sort_order']),
        'is_active': int(row['is_active']),
    }


def get_gallery_photos(include_inactive: bool = False) -> list[dict[str, Any]]:
    where = '' if include_inactive else 'WHERE is_active = 1'
    with get_db() as db:
        rows = db.execute(
            f'SELECT * FROM gallery_photos {where} ORDER BY sort_order ASC, id ASC'
        ).fetchall()
    return [gallery_photo_to_dict(row) for row in rows]


def service_price_label(service: dict[str, Any] | sqlite3.Row) -> str:
    price = int(service['price'])
    price_type = service['price_type']
    if price_type == 'fixed':
        return f'+{price:,} ₽'.replace(',', ' ')
    if price_type == 'per_guest_night':
        return f'+{price:,} ₽ за гостя/ночь'.replace(',', ' ')
    if price_type == 'free':
        return 'бесплатно'
    return 'по согласованию'


def csrf_token() -> str:
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_hex(32)
        session['_csrf_token'] = token
    return token


def validate_csrf() -> bool:
    return bool(session.get('_csrf_token')) and request.form.get('_csrf_token') == session.get('_csrf_token')


app.jinja_env.globals['csrf_token'] = csrf_token
app.jinja_env.globals['service_price_label'] = service_price_label


def parse_date(value: str):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('Проверьте даты бронирования.') from exc


def validate_phone(phone: str) -> bool:
    digits = re.sub(r'\D+', '', phone)
    return 10 <= len(digits) <= 15


def calculate_total(cottage: str, check_in_raw: str, check_out_raw: str, guests_raw: str, extras: list[str]) -> tuple[int, int]:
    rooms = get_rooms(include_inactive=False)
    room = rooms.get(cottage)
    if not room:
        raise ValueError('Выбранный вариант размещения не найден или временно недоступен.')

    check_in = parse_date(check_in_raw)
    check_out = parse_date(check_out_raw)

    if check_out <= check_in:
        raise ValueError('Дата выезда должна быть позже даты заезда.')

    if check_in < datetime.now().date():
        raise ValueError('Дата заезда не может быть в прошлом.')

    try:
        guests = int(guests_raw)
    except ValueError as exc:
        raise ValueError('Проверьте количество гостей.') from exc

    if guests < 1:
        raise ValueError('Количество гостей должно быть не меньше 1.')
    if guests > room['capacity']:
        raise ValueError(f"Для варианта '{cottage}' максимальное количество гостей: {room['capacity']}.")

    nights = (check_out - check_in).days
    total = 0
    for offset in range(nights):
        ordinal_day = check_in.toordinal() + offset
        weekday = datetime.fromordinal(ordinal_day).weekday()
        total += room['weekend_price'] if weekday >= 4 else room['weekday_price']

    service_map = get_service_map(include_inactive=False)
    for code in extras:
        service = service_map.get(code)
        if not service or not service['available_in_booking']:
            continue
        price = int(service['price'])
        if service['price_type'] == 'fixed':
            total += price
        elif service['price_type'] == 'per_guest_night':
            total += guests * nights * price

    return nights, total


def is_room_busy(cottage: str, check_in: str, check_out: str, exclude_booking_id: int | None = None) -> bool:
    query = '''
        SELECT id FROM bookings
        WHERE cottage = ?
          AND status IN ('Новая', 'Подтверждена')
          AND check_in < ?
          AND check_out > ?
    '''
    params: list[Any] = [cottage, check_out, check_in]
    if exclude_booking_id is not None:
        query += ' AND id != ?'
        params.append(exclude_booking_id)

    with get_db() as db:
        return db.execute(query, params).fetchone() is not None


def get_occupied_ranges() -> dict[str, list[dict[str, str]]]:
    result = {room_name: [] for room_name in get_rooms(include_inactive=False)}
    with get_db() as db:
        rows = db.execute(
            '''
            SELECT cottage, check_in, check_out, status
            FROM bookings
            WHERE status IN ('Новая', 'Подтверждена')
            ORDER BY check_in ASC
            '''
        ).fetchall()
    for row in rows:
        if row['cottage'] in result:
            result[row['cottage']].append(
                {'check_in': row['check_in'], 'check_out': row['check_out'], 'status': row['status']}
            )
    return result


def save_booking(form_data: dict, nights: int, total_price: int) -> None:
    service_map = get_service_map(include_inactive=True)
    extras = [service_map.get(item, {'name': item})['name'] for item in form_data.getlist('extras')]
    with get_db() as db:
        db.execute(
            '''
            INSERT INTO bookings (
                created_at, guest_name, phone, cottage, check_in, check_out,
                nights, guests, extras, comment, total_price, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Новая')
            ''',
            (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                form_data.get('guest_name', '').strip(),
                form_data.get('phone', '').strip(),
                form_data.get('cottage', '').strip(),
                form_data.get('check_in', '').strip(),
                form_data.get('check_out', '').strip(),
                nights,
                form_data.get('guests', '').strip(),
                ', '.join(extras),
                form_data.get('comment', '').strip(),
                total_price,
            ),
        )


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Войдите в панель администратора.', 'error')
            return redirect(url_for('admin_login'))
        return view(*args, **kwargs)

    return wrapped_view


@app.get('/privacy')
def privacy_policy():
    return render_template('privacy.html')


@app.get('/')
def index():
    rooms = get_rooms(include_inactive=False)
    active_services = get_services(include_inactive=False)
    service_cards = [service for service in active_services if service['display_on_site']]
    booking_services = [service for service in active_services if service['available_in_booking']]
    return render_template(
        'index.html',
        rooms=rooms,
        service_cards=service_cards,
        booking_services=booking_services,
        service_map={service['code']: service for service in booking_services},
        gallery_photos=get_gallery_photos(include_inactive=False),
        occupied_ranges=get_occupied_ranges(),
    )


@app.post('/book')
def book():
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('index') + '#booking-result')

    guest_name = request.form.get('guest_name', '').strip()
    phone = request.form.get('phone', '').strip()
    cottage = request.form.get('cottage', '').strip()
    check_in = request.form.get('check_in', '').strip()
    check_out = request.form.get('check_out', '').strip()
    guests = request.form.get('guests', '').strip()
    extras = request.form.getlist('extras')
    consent = request.form.get('personal_data_consent')

    if not guest_name or not phone or not cottage or not check_in or not check_out or not guests:
        flash('Заполните обязательные поля формы бронирования.', 'error')
        return redirect(url_for('index') + '#booking-result')

    if not validate_phone(phone):
        flash('Укажите корректный номер телефона.', 'error')
        return redirect(url_for('index') + '#booking-result')

    if not consent:
        flash('Необходимо согласие на обработку персональных данных.', 'error')
        return redirect(url_for('index') + '#booking-result')

    try:
        nights, total_price = calculate_total(cottage, check_in, check_out, guests, extras)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('index') + '#booking-result')

    if is_room_busy(cottage, check_in, check_out):
        flash('На выбранные даты этот вариант уже занят или ожидает подтверждения. Выберите другие даты.', 'error')
        return redirect(url_for('index') + '#booking-result')

    save_booking(request.form, nights, total_price)
    flash(
        f'Спасибо! Заявка отправлена. Администратор базы отдыха свяжется с вами в ближайшее время для подтверждения бронирования. Предварительная стоимость: {total_price:,} ₽ за {nights} ноч.'.replace(',', ' '),
        'success',
    )
    return redirect(url_for('index') + '#booking-result')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if not validate_csrf():
            flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
            return redirect(url_for('admin_login'))

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        with get_db() as db:
            admin = db.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('Вы вошли в панель администратора.', 'success')
            return redirect(url_for('admin_panel'))
        flash('Неверный логин или пароль.', 'error')

    return render_template('admin_login.html')


@app.get('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Вы вышли из панели администратора.', 'success')
    return redirect(url_for('index'))


def build_booking_filter_sql() -> tuple[str, list[Any], dict[str, str]]:
    status_filter = request.args.get('status', 'all').strip()
    cottage_filter = request.args.get('cottage', 'all').strip()
    search_query = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    room_names = set(get_rooms(include_inactive=True).keys())

    where: list[str] = []
    params: list[Any] = []

    if status_filter in STATUSES:
        where.append('status = ?')
        params.append(status_filter)

    if cottage_filter in room_names:
        where.append('cottage = ?')
        params.append(cottage_filter)

    if search_query:
        like = f'%{search_query}%'
        where.append('(guest_name LIKE ? OR phone LIKE ? OR cottage LIKE ? OR extras LIKE ? OR comment LIKE ?)')
        params.extend([like, like, like, like, like])

    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_from):
        where.append('check_in >= ?')
        params.append(date_from)

    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_to):
        where.append('check_in <= ?')
        params.append(date_to)

    where_sql = ' WHERE ' + ' AND '.join(where) if where else ''
    filters = {
        'status': status_filter,
        'cottage': cottage_filter,
        'q': search_query,
        'date_from': date_from,
        'date_to': date_to,
    }
    return where_sql, params, filters


@app.get('/admin')
@login_required
def admin_panel():
    where_sql, params, filters = build_booking_filter_sql()
    today = datetime.now().date().isoformat()
    rooms = get_rooms(include_inactive=True)

    with get_db() as db:
        bookings = db.execute(
            f'SELECT * FROM bookings{where_sql} ORDER BY created_at DESC',
            params,
        ).fetchall()

        stats_rows = db.execute(
            'SELECT status, COUNT(*) AS count FROM bookings GROUP BY status'
        ).fetchall()
        totals = db.execute(
            """
            SELECT
                COUNT(*) AS total_bookings,
                COALESCE(SUM(CASE WHEN status = 'Подтверждена' THEN total_price ELSE 0 END), 0) AS confirmed_sum,
                COALESCE(SUM(CASE WHEN status = 'Подтверждена' THEN guests ELSE 0 END), 0) AS confirmed_guests,
                COALESCE(SUM(CASE WHEN status = 'Подтверждена' THEN nights ELSE 0 END), 0) AS confirmed_nights,
                COALESCE(AVG(CASE WHEN status = 'Подтверждена' THEN total_price END), 0) AS average_confirmed_price
            FROM bookings
            """
        ).fetchone()
        upcoming_bookings = db.execute(
            """
            SELECT * FROM bookings
            WHERE status = 'Подтверждена' AND check_in >= ?
            ORDER BY check_in ASC
            LIMIT 5
            """,
            (today,),
        ).fetchall()
        room_stats = db.execute(
            """
            SELECT cottage, COUNT(*) AS count, COALESCE(SUM(total_price), 0) AS amount
            FROM bookings
            GROUP BY cottage
            ORDER BY count DESC, cottage ASC
            """
        ).fetchall()
        operations = db.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status = 'Подтверждена' AND check_in = ? THEN 1 ELSE 0 END), 0) AS arrivals_today,
                COALESCE(SUM(CASE WHEN status = 'Подтверждена' AND check_out = ? THEN 1 ELSE 0 END), 0) AS departures_today,
                COALESCE(SUM(CASE WHEN status = 'Подтверждена' AND check_in <= ? AND check_out > ? THEN guests ELSE 0 END), 0) AS active_guests
            FROM bookings
            """,
            (today, today, today, today),
        ).fetchone()
        active_rooms = db.execute(
            """
            SELECT cottage, guest_name, status
            FROM bookings
            WHERE status IN ('Новая', 'Подтверждена')
              AND check_in <= ?
              AND check_out > ?
            ORDER BY status DESC, created_at DESC
            """,
            (today, today),
        ).fetchall()

    stats = {status: 0 for status in STATUSES}
    for row in stats_rows:
        stats[row['status']] = row['count']

    active_filter_count = sum(
        1 for value in filters.values()
        if value and value != 'all'
    )
    max_room_count = max([row['count'] for row in room_stats], default=1)
    total_bookings = totals['total_bookings'] or 0
    conversion_rate = round((stats['Подтверждена'] / total_bookings) * 100) if total_bookings else 0
    overview = {
        'conversion_rate': conversion_rate,
        'arrivals_today': operations['arrivals_today'],
        'departures_today': operations['departures_today'],
        'active_guests': operations['active_guests'],
        'average_confirmed_price': totals['average_confirmed_price'] or 0,
    }

    active_room_map = {row['cottage']: row for row in active_rooms}
    room_today_status = []
    for room_name, room in rooms.items():
        if not room['is_active']:
            continue
        active = active_room_map.get(room_name)
        if active:
            room_today_status.append({
                'room': room_name,
                'status': active['status'],
                'note': active['guest_name'],
            })
        else:
            room_today_status.append({
                'room': room_name,
                'status': 'Свободно',
                'note': 'можно принять заявку',
            })

    return render_template(
        'admin.html',
        bookings=bookings,
        statuses=STATUSES,
        stats=stats,
        totals=totals,
        confirmed_sum=totals['confirmed_sum'],
        filters=filters,
        active_filter_count=active_filter_count,
        rooms=rooms,
        upcoming_bookings=upcoming_bookings,
        room_stats=room_stats,
        max_room_count=max_room_count,
        today=today,
        overview=overview,
        room_today_status=room_today_status,
    )


@app.get('/admin/catalog')
@login_required
def admin_catalog():
    rooms = get_room_list(include_inactive=True)
    services = get_services(include_inactive=True)
    return render_template(
        'admin_catalog.html',
        rooms=rooms,
        services=services,
        price_types=PRICE_TYPES,
        image_files=get_image_files(),
        gallery_photos=get_gallery_photos(include_inactive=True),
    )


def parse_int_field(name: str, default: int = 0, min_value: int | None = None) -> int:
    raw = request.form.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f'Поле "{name}" должно быть числом.') from exc
    if min_value is not None and value < min_value:
        raise ValueError(f'Поле "{name}" не может быть меньше {min_value}.')
    return value


def form_checkbox(name: str) -> int:
    return 1 if request.form.get(name) == '1' else 0


@app.post('/admin/photo/upload')
@login_required
def upload_photo_admin():
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    file = request.files.get('photo')
    title = request.form.get('title', '').strip()
    add_to_gallery = form_checkbox('add_to_gallery')
    sort_order = 50
    try:
        sort_order = parse_int_field('photo_sort_order', default=50, min_value=0)
    except ValueError:
        pass

    if not file or not file.filename:
        flash('Выберите файл фотографии.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    if not allowed_image(file.filename):
        flash('Можно загрузить только изображения PNG, JPG, JPEG или WEBP.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    filename = unique_upload_name(file.filename)
    save_path = UPLOAD_DIR / filename
    file.save(save_path)
    image_path = f'uploads/{filename}'

    if add_to_gallery:
        with get_db() as db:
            db.execute(
                '''
                INSERT OR IGNORE INTO gallery_photos (title, image, sort_order, is_active)
                VALUES (?, ?, ?, 1)
                ''',
                (title or Path(filename).stem, image_path, sort_order),
            )

    flash('Фотография загружена. Теперь её можно выбрать в карточке размещения или показать в галерее.', 'success')
    return redirect(url_for('admin_catalog') + '#photos-management')


@app.post('/admin/gallery/save')
@login_required
def save_gallery_photo_admin():
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    try:
        photo_id = parse_int_field('photo_id', min_value=1)
        sort_order = parse_int_field('sort_order', default=0, min_value=0)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    title = request.form.get('title', '').strip()
    image = request.form.get('image', '').strip()
    is_active = form_checkbox('is_active')

    if not title:
        flash('Укажите название фотографии.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    if image not in get_image_files():
        flash('Выбранный файл фотографии не найден.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    with get_db() as db:
        db.execute(
            '''
            UPDATE gallery_photos
            SET title = ?, image = ?, sort_order = ?, is_active = ?
            WHERE id = ?
            ''',
            (title, image, sort_order, is_active, photo_id),
        )

    flash('Фотография галереи сохранена.', 'success')
    return redirect(url_for('admin_catalog') + '#photos-management')


@app.post('/admin/gallery/add-existing')
@login_required
def add_existing_gallery_photo_admin():
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    title = request.form.get('title', '').strip()
    image = request.form.get('image', '').strip()
    try:
        sort_order = parse_int_field('sort_order', default=50, min_value=0)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    if image not in get_image_files():
        flash('Выбранный файл фотографии не найден.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    with get_db() as db:
        db.execute(
            '''
            INSERT INTO gallery_photos (title, image, sort_order, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(image) DO UPDATE SET
                title = excluded.title,
                sort_order = excluded.sort_order,
                is_active = 1
            ''',
            (title or Path(image).stem, image, sort_order),
        )

    flash('Фотография добавлена в галерею сайта.', 'success')
    return redirect(url_for('admin_catalog') + '#photos-management')


@app.post('/admin/gallery/<int:photo_id>/delete')
@login_required
def delete_gallery_photo_admin(photo_id: int):
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog') + '#photos-management')

    with get_db() as db:
        db.execute('DELETE FROM gallery_photos WHERE id = ?', (photo_id,))
    flash('Фотография удалена из галереи. Сам файл остаётся доступен для карточек размещения.', 'success')
    return redirect(url_for('admin_catalog') + '#photos-management')


@app.post('/admin/room/save')
@login_required
def save_room_admin():
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog'))

    original_name = request.form.get('original_name', '').strip()
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    amenities_raw = request.form.get('amenities', '').strip()
    image = request.form.get('image', '').strip() or 'img/domiki.png'
    badge = request.form.get('badge', '').strip() or 'Размещение'

    if image not in get_image_files():
        flash('Выбранный файл фотографии не найден. Загрузите изображение через раздел «Фотографии».', 'error')
        return redirect(url_for('admin_catalog') + '#rooms-management')

    if not name:
        flash('Укажите название варианта размещения.', 'error')
        return redirect(url_for('admin_catalog'))
    if not description:
        flash('Заполните описание варианта размещения.', 'error')
        return redirect(url_for('admin_catalog'))

    try:
        capacity = parse_int_field('capacity', min_value=1)
        weekday_price = parse_int_field('weekday_price', min_value=0)
        weekend_price = parse_int_field('weekend_price', min_value=0)
        sort_order = parse_int_field('sort_order', default=0, min_value=0)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_catalog'))

    amenities = '; '.join(split_amenities(amenities_raw))
    is_active = form_checkbox('is_active')

    with get_db() as db:
        if original_name and original_name != name:
            conflict = db.execute('SELECT 1 FROM rooms WHERE name = ?', (name,)).fetchone()
            if conflict:
                flash('Вариант размещения с таким названием уже существует.', 'error')
                return redirect(url_for('admin_catalog'))
            db.execute(
                '''
                UPDATE rooms
                SET name = ?, capacity = ?, weekday_price = ?, weekend_price = ?,
                    description = ?, amenities = ?, image = ?, badge = ?,
                    sort_order = ?, is_active = ?
                WHERE name = ?
                ''',
                (name, capacity, weekday_price, weekend_price, description, amenities, image, badge, sort_order, is_active, original_name),
            )
            db.execute('UPDATE bookings SET cottage = ? WHERE cottage = ?', (name, original_name))
        else:
            db.execute(
                '''
                INSERT INTO rooms (
                    name, capacity, weekday_price, weekend_price, description,
                    amenities, image, badge, sort_order, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    capacity = excluded.capacity,
                    weekday_price = excluded.weekday_price,
                    weekend_price = excluded.weekend_price,
                    description = excluded.description,
                    amenities = excluded.amenities,
                    image = excluded.image,
                    badge = excluded.badge,
                    sort_order = excluded.sort_order,
                    is_active = excluded.is_active
                ''',
                (name, capacity, weekday_price, weekend_price, description, amenities, image, badge, sort_order, is_active),
            )

    flash('Данные варианта размещения сохранены.', 'success')
    return redirect(url_for('admin_catalog') + '#rooms-management')


@app.post('/admin/room/<path:room_name>/delete')
@login_required
def delete_room_admin(room_name: str):
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog'))

    with get_db() as db:
        booking_count = db.execute('SELECT COUNT(*) AS count FROM bookings WHERE cottage = ?', (room_name,)).fetchone()['count']
        if booking_count:
            db.execute('UPDATE rooms SET is_active = 0 WHERE name = ?', (room_name,))
            flash('У варианта есть заявки, поэтому он не удалён, а скрыт с сайта.', 'success')
        else:
            db.execute('DELETE FROM rooms WHERE name = ?', (room_name,))
            flash('Вариант размещения удалён.', 'success')
    return redirect(url_for('admin_catalog') + '#rooms-management')


@app.post('/admin/service/save')
@login_required
def save_service_admin():
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog'))

    original_code = request.form.get('original_code', '').strip()
    code = request.form.get('code', '').strip().lower()
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price_type = request.form.get('price_type', 'fixed').strip()
    icon = request.form.get('icon', '').strip() or 'fa-solid fa-circle'

    if not re.fullmatch(r'[a-z0-9_]+', code):
        flash('Код услуги может содержать только латинские буквы, цифры и подчёркивание.', 'error')
        return redirect(url_for('admin_catalog') + '#services-management')
    if not name or not description:
        flash('Заполните название и описание услуги.', 'error')
        return redirect(url_for('admin_catalog') + '#services-management')
    if price_type not in PRICE_TYPES:
        flash('Некорректный тип расчёта цены услуги.', 'error')
        return redirect(url_for('admin_catalog') + '#services-management')

    try:
        price = parse_int_field('price', default=0, min_value=0)
        sort_order = parse_int_field('sort_order', default=0, min_value=0)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_catalog') + '#services-management')

    display_on_site = form_checkbox('display_on_site')
    available_in_booking = form_checkbox('available_in_booking')
    is_active = form_checkbox('is_active')

    with get_db() as db:
        if original_code and original_code != code:
            conflict = db.execute('SELECT 1 FROM services WHERE code = ?', (code,)).fetchone()
            if conflict:
                flash('Услуга с таким кодом уже существует.', 'error')
                return redirect(url_for('admin_catalog') + '#services-management')
            db.execute(
                '''
                UPDATE services
                SET code = ?, name = ?, description = ?, price = ?, price_type = ?, icon = ?,
                    display_on_site = ?, available_in_booking = ?, sort_order = ?, is_active = ?
                WHERE code = ?
                ''',
                (code, name, description, price, price_type, icon, display_on_site, available_in_booking, sort_order, is_active, original_code),
            )
        else:
            db.execute(
                '''
                INSERT INTO services (
                    code, name, description, price, price_type, icon,
                    display_on_site, available_in_booking, sort_order, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    price = excluded.price,
                    price_type = excluded.price_type,
                    icon = excluded.icon,
                    display_on_site = excluded.display_on_site,
                    available_in_booking = excluded.available_in_booking,
                    sort_order = excluded.sort_order,
                    is_active = excluded.is_active
                ''',
                (code, name, description, price, price_type, icon, display_on_site, available_in_booking, sort_order, is_active),
            )

    flash('Данные услуги сохранены.', 'success')
    return redirect(url_for('admin_catalog') + '#services-management')


@app.post('/admin/service/<path:service_code>/delete')
@login_required
def delete_service_admin(service_code: str):
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(url_for('admin_catalog'))

    with get_db() as db:
        db.execute('DELETE FROM services WHERE code = ?', (service_code,))
    flash('Услуга удалена.', 'success')
    return redirect(url_for('admin_catalog') + '#services-management')


@app.post('/admin/booking/<int:booking_id>/status')
@login_required
def update_booking_status(booking_id: int):
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(request.referrer or url_for('admin_panel'))

    status = request.form.get('status', '').strip()
    if status not in STATUSES:
        flash('Некорректный статус заявки.', 'error')
        return redirect(request.referrer or url_for('admin_panel'))

    with get_db() as db:
        booking = db.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,)).fetchone()
        if not booking:
            flash('Заявка не найдена.', 'error')
            return redirect(request.referrer or url_for('admin_panel'))

        if status in ('Новая', 'Подтверждена') and is_room_busy(
            booking['cottage'], booking['check_in'], booking['check_out'], exclude_booking_id=booking_id
        ):
            flash('Нельзя подтвердить заявку: выбранные даты пересекаются с другой активной заявкой.', 'error')
            return redirect(request.referrer or url_for('admin_panel'))

        db.execute('UPDATE bookings SET status = ? WHERE id = ?', (status, booking_id))

    flash('Статус заявки обновлён.', 'success')
    return redirect(request.referrer or url_for('admin_panel'))


@app.post('/admin/booking/<int:booking_id>/delete')
@login_required
def delete_booking(booking_id: int):
    if not validate_csrf():
        flash('Ошибка безопасности формы. Обновите страницу и попробуйте ещё раз.', 'error')
        return redirect(request.referrer or url_for('admin_panel'))

    with get_db() as db:
        db.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
    flash('Заявка удалена.', 'success')
    return redirect(request.referrer or url_for('admin_panel'))


@app.get('/admin/export')
@login_required
def export_bookings():
    where_sql, params, _filters = build_booking_filter_sql()
    with get_db() as db:
        rows = db.execute(f'SELECT * FROM bookings{where_sql} ORDER BY created_at DESC', params).fetchall()

    output = StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'id', 'created_at', 'guest_name', 'phone', 'cottage', 'check_in', 'check_out',
        'nights', 'guests', 'extras', 'comment', 'total_price', 'status'
    ])
    for row in rows:
        writer.writerow([row[key] for key in row.keys()])

    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=bookings.csv'},
    )


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
