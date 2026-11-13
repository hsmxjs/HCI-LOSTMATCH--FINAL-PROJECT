from datetime import datetime
from pathlib import Path
import sqlite3
import uuid

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / 'lostmatch.db'
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'lostmatch-development-secret-change-before-deployment'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

VALID_CATEGORIES = ['Electronics', 'Bags & Wallets', 'IDs & Cards', 'Accessories', 'Clothing', 'Books & Stationery', 'Keys', 'Mugs', 'Others']
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

DEMO_MATCHES = [
    {'id': 1, 'name': 'White AirPods', 'category': 'Electronics', 'color': 'White', 'location': 'Al Jubail Mall', 'date': 'Sep 26, 2026', 'score': 90, 'description': 'Apple AirPods with white case. Found near the food court.', 'type': 'lost', 'image': None},
    {'id': 2, 'name': 'Black Wallet', 'category': 'Bags & Wallets', 'color': 'Black', 'location': 'Al Jubail Corniche', 'date': 'Sep 22, 2026', 'score': 75, 'description': 'Black wallet found near the entrance.', 'type': 'lost', 'image': None},
    {'id': 3, 'name': 'Car Key', 'category': 'Keys', 'color': 'Black', 'location': 'Al Jubail Mall', 'date': 'Sep 21, 2026', 'score': 68, 'description': 'Car key found in the parking area.', 'type': 'found', 'image': None},
]


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_contact TEXT NOT NULL,
                report_type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                color TEXT,
                location TEXT NOT NULL,
                report_date TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'Searching',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS report_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS claim_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                sender_contact TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 1
            );
        ''')


def logged_in():
    return bool(session.get('user'))


def valid_upload(file):
    return bool(file.filename and '.' in file.filename and file.filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS)


def report_payload(form):
    return {
        'item_name': form.get('item_name', '').strip(),
        'category': form.get('category', '').strip(),
        'color': form.get('color', '').strip(),
        'location': form.get('location', '').strip(),
        'report_date': form.get('report_date', '').strip(),
        'description': form.get('description', '').strip(),
    }


def valid_report(data):
    return all(data[k] for k in ('item_name', 'location', 'report_date')) and data['category'] in VALID_CATEGORIES


def save_photos(files, report_id, db):
    for photo in files:
        extension = photo.filename.rsplit('.', 1)[-1].lower()
        filename = secure_filename(f'{uuid.uuid4().hex}.{extension}')
        photo.save(UPLOAD_DIR / filename)
        db.execute('INSERT INTO report_photos (report_id, filename) VALUES (?, ?)', (report_id, filename))


def owned_report(db, report_id):
    return db.execute('SELECT * FROM reports WHERE id = ? AND user_contact = ?', (report_id, session['user'])).fetchone()


def match_by_id(match_id):
    return next((match for match in DEMO_MATCHES if match['id'] == match_id), None)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        contact = (request.form.get('contact') or request.form.get('email') or '').strip()
        password = request.form.get('password', '')
        if contact and password:
            session['user'] = contact
            return redirect(url_for('dashboard'))
        return render_template('signup.html', error='Please complete all required fields.')
    return render_template('signup.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        message = 'Demo only: Your reset request was received. No email has been sent.' if email else 'Please enter your email address.'
        return render_template('forgot_password.html', message=message)
    return render_template('forgot_password.html')


@app.route('/login', methods=['POST'])
def login():
    contact = request.form.get('contact', '').strip() or request.form.get('email', '').strip()
    password = request.form.get('password', '')
    if not contact or not password:
        return render_template('index.html', error='Please enter your email/phone and password.')
    session['user'] = contact
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    if not logged_in():
        return redirect(url_for('home'))
    return render_template('dashboard.html')


@app.route('/select-category')
def select_category():
    if not logged_in():
        return redirect(url_for('home'))
    report_type = request.args.get('type', '')
    if report_type not in ('lost', 'found'):
        return redirect(url_for('dashboard'))
    return render_template('select_category.html', report_type=report_type)


@app.route('/report-form', methods=['GET', 'POST'])
def report_form():
    if not logged_in():
        return redirect(url_for('home'))
    report_type = request.values.get('type', '')
    category = request.values.get('category', '')
    if report_type not in ('lost', 'found'):
        return redirect(url_for('dashboard'))
    if request.method == 'GET':
        if category not in VALID_CATEGORIES:
            return redirect(url_for('select_category', type=report_type))
        return render_template('report_form.html', report_type=report_type, category=category, categories=VALID_CATEGORIES)

    data = report_payload(request.form)
    if not data['category'] and category in VALID_CATEGORIES:
        data['category'] = category
    photos = [p for p in request.files.getlist('photos') if p.filename]
    error = None
    if not valid_report(data):
        error = 'Please complete all required fields.'
    elif len(photos) > 5:
        error = 'You can upload up to 5 photos only.'
    elif any(not valid_upload(photo) for photo in photos):
        error = 'Only JPG, JPEG, PNG, WEBP and GIF images are allowed.'
    if error:
        return render_template('report_form.html', report_type=report_type, category=data['category'], categories=VALID_CATEGORIES, error=error), 400

    with get_db() as db:
        cursor = db.execute('''
            INSERT INTO reports (user_contact, report_type, item_name, category, color, location, report_date, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user'], report_type, data['item_name'], data['category'], data['color'], data['location'], data['report_date'], data['description'], 'Searching', datetime.now().isoformat()))
        report_id = cursor.lastrowid
        save_photos(photos, report_id, db)
    return redirect(url_for('report_details', report_id=report_id))


@app.route('/find-item')
def find_item():
    if not logged_in():
        return redirect(url_for('home'))
    return render_template('find_item.html')


@app.route('/find-results')
def find_results():
    if not logged_in():
        return redirect(url_for('home'))
    keyword = request.args.get('keyword', '').strip()
    with get_db() as db:
        if keyword:
            rows = db.execute('SELECT * FROM reports WHERE item_name LIKE ? ORDER BY id DESC', (f'%{keyword}%',)).fetchall()
        else:
            rows = db.execute('SELECT * FROM reports ORDER BY id DESC LIMIT 30').fetchall()
    return render_template('find_results.html', results=[dict(r) for r in rows])


@app.route('/my-reports')
def my_reports():
    if not logged_in():
        return redirect(url_for('home'))
    with get_db() as db:
        rows = db.execute('''
            SELECT r.*, (SELECT filename FROM report_photos WHERE report_id = r.id ORDER BY id LIMIT 1) AS photo
            FROM reports AS r WHERE r.user_contact = ? ORDER BY r.id DESC
        ''', (session['user'],)).fetchall()
    reports = {'lost': [], 'found': []}
    for row in rows:
        report = dict(row)
        report['name'] = report['item_name']
        report['date'] = report['report_date']
        report['image'] = url_for('static', filename='uploads/' + report['photo']) if report['photo'] else None
        reports[report['report_type']].append(report)
    selected_type = request.args.get('type', 'lost')
    if selected_type not in ('lost', 'found'):
        selected_type = 'lost'
    return render_template('my_reports.html', reports=reports, selected_type=selected_type)


@app.route('/report-details/<int:report_id>')
def report_details(report_id):
    if not logged_in():
        return redirect(url_for('home'))
    with get_db() as db:
        row = owned_report(db, report_id)
        if row is None:
            return redirect(url_for('my_reports'))
        photos = db.execute('SELECT filename FROM report_photos WHERE report_id = ? ORDER BY id', (report_id,)).fetchall()
    report = dict(row)
    report['photos'] = [url_for('static', filename='uploads/' + p['filename']) for p in photos]
    report['name'] = report['item_name']
    report['date'] = report['report_date']
    report['image'] = report['photos'][0] if report['photos'] else None
    return render_template('report_details.html', report=report)


@app.route('/report-details/<int:report_id>/close', methods=['POST'])
def close_report(report_id):
    if not logged_in():
        return redirect(url_for('home'))
    with get_db() as db:
        db.execute("UPDATE reports SET status = 'Closed' WHERE id = ? AND user_contact = ?", (report_id, session['user']))
    return redirect(url_for('report_details', report_id=report_id))


@app.route('/report-details/<int:report_id>/delete', methods=['POST'])
def delete_report(report_id):
    if not logged_in():
        return redirect(url_for('home'))
    with get_db() as db:
        row = owned_report(db, report_id)
        if row is None:
            return redirect(url_for('my_reports'))
        report_type = row['report_type']
        db.execute('DELETE FROM report_photos WHERE report_id = ?', (report_id,))
        db.execute('DELETE FROM reports WHERE id = ? AND user_contact = ?', (report_id, session['user']))
    return redirect(url_for('my_reports', type=report_type))


@app.route('/report-details/<int:report_id>/edit', methods=['GET', 'POST'])
def edit_report(report_id):
    if not logged_in():
        return redirect(url_for('home'))
    with get_db() as db:
        row = owned_report(db, report_id)
    if row is None:
        return redirect(url_for('my_reports'))
    report = dict(row)
    if request.method == 'POST':
        data = report_payload(request.form)
        if not valid_report(data):
            return render_template('edit_report.html', report=report, categories=VALID_CATEGORIES, error='Please complete all required fields.'), 400
        with get_db() as db:
            db.execute('''
                UPDATE reports SET item_name = ?, category = ?, color = ?, location = ?, report_date = ?, description = ?
                WHERE id = ? AND user_contact = ?
            ''', (data['item_name'], data['category'], data['color'], data['location'], data['report_date'], data['description'], report_id, session['user']))
        return redirect(url_for('report_details', report_id=report_id))
    return render_template('edit_report.html', report=report, categories=VALID_CATEGORIES)


@app.route('/my-matches')
def my_matches():
    if not logged_in():
        return redirect(url_for('home'))
    selected_type = request.args.get('type', 'lost')
    if selected_type not in ('lost', 'found'):
        selected_type = 'lost'
    return render_template('my_matches.html', matches=DEMO_MATCHES, selected_type=selected_type)


@app.route('/match-details/<int:match_id>')
def match_details(match_id):
    if not logged_in():
        return redirect(url_for('home'))
    match = match_by_id(match_id)
    if match is None:
        abort(404)
    return render_template('match_details.html', match=match)


@app.route('/claim-request/<int:match_id>', methods=['GET', 'POST'])
def claim_request(match_id):
    if not logged_in():
        return redirect(url_for('home'))
    match = match_by_id(match_id)
    if match is None:
        abort(404)
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if not 1 <= len(message) <= 300:
            return render_template('claim_request.html', match=match, error='Please enter a message of 1 to 300 characters.', draft=message, sent=False), 400
        with get_db() as db:
            db.execute('''
                INSERT INTO claim_requests (match_id, item_name, sender_contact, message, created_at, is_demo)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (match_id, match['name'], session['user'], message, datetime.now().isoformat()))
        return redirect(url_for('claim_request', match_id=match_id, sent=1))
    return render_template('claim_request.html', match=match, sent=request.args.get('sent') == '1', draft='')


@app.route('/profile')
def profile():
    if not logged_in():
        return redirect(url_for('home'))
    return render_template('profile.html')


if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
