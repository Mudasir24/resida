import os
from dotenv import load_dotenv
load_dotenv()

from collections import defaultdict
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from datetime import date, datetime
import logging
import cloudinary
import cloudinary.uploader
from werkzeug.security import generate_password_hash, check_password_hash

# Import helper functions
from helpers import (
    generate_invite_code,
    apartment_login_required,
    admin_login_required,
    get_conn,
    get_all_apartments,
    get_apartment_by_slug,
    get_apartment_full_by_slug,
    send_invite_email,
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# Custom Jinja2 filter for date formatting
@app.template_filter('strftime')
def _jinja2_filter_datetime(date_string, fmt='%b %d, %Y'):
    """Format a date string or datetime object"""
    if not date_string:
        return 'N/A'
    if isinstance(date_string, str):
        try:
            date_obj = datetime.strptime(date_string, '%Y-%m-%d')
            return date_obj.strftime(fmt)
        except ValueError:
            return date_string
    elif isinstance(date_string, datetime):
        return date_string.strftime(fmt)
    else:
        return str(date_string)

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ============================================================================
# MAIN APPLICATION ROUTES
# ============================================================================

@app.route('/')
def index():
    """Public landing page"""
    return render_template('index.html')

@app.route('/about')
def about():
    """About the platform"""
    return render_template('about.html')

@app.route('/apartments')
def apartments_directory():
    """Directory of apartments (optional)"""
    apartments = get_all_apartments()
    return render_template('apartments_directory.html', apartments=apartments)

@app.route('/register-apartment', methods=['GET', 'POST'])
def register_apartment():
    """Apartment registration form"""
    if request.method == 'POST':
        # Handle apartment registration
        name = request.form.get('name')
        slug = request.form.get('slug')
        admin_email = request.form.get('admin_email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        city = request.form.get('city')

        if not name or not slug or not admin_email or not phone or not address or not city:
            flash("All fields are required.", "error")
            return redirect(url_for('register_apartment'))
        
        photo_file = request.files.get('photo')
        photo_url = None
        
        if photo_file and photo_file.filename:
            upload_result = cloudinary.uploader.upload(
                photo_file,
                folder='apartments/photos/'
            )
            photo_url = upload_result.get('secure_url')

        else:
            photo_url = os.environ.get('DEFAULT_APARTMENT_PHOTO')
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check if slug already exists
                cur.execute("SELECT 1 FROM apartments WHERE slug = %s", (slug,))
                if cur.fetchone():
                    return "Apartment slug already exists. Please choose a different one.", 400
                
                # Insert new apartment
                cur.execute("""
                    INSERT INTO apartments (name, slug, admin_email, phone, address, city, photo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (name, slug, admin_email, phone, address, city, photo_url))

                apartment_id = cur.fetchone()[0]

                admin_invite_code = generate_invite_code()

                cur.execute("""
                    INSERT INTO invites (apartment_id, role, invite_code, expires_at)
                            VALUES (%s, %s, %s, NOW() + INTERVAL '7 days')
                """, (apartment_id, 'admin', admin_invite_code))

        send_invite_email(admin_email, name, admin_invite_code, slug)

        flash(f'Apartment registered successfully! An invite email has been sent to your email address {admin_email}.', 'success')
        return redirect(url_for('apartment_home', slug=slug))
    return render_template('register_apartment.html')

@app.route('/api/check-slug')
def check_slug():
    slug = request.args.get('slug')

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM apartments WHERE slug = %s",
                (slug,)
            )
            exists = cur.fetchone() is not None

    return {"exists": exists}

# ============================================================================
# APARTMENT TENANT SPACE ROUTES
# ============================================================================

@app.route('/apartments/<slug>')
def apartment_home(slug):
    """Apartment homepage - shows same page for everyone, with different nav based on login status"""
    logger.info(f"apartment_home called with slug: {slug}")

    if not slug:
        flash("Invalid apartment slug.", "error")
        return redirect(url_for('apartments_directory'))

    try:
        # Check if apartment exists
        apartment = get_apartment_full_by_slug(slug)
        if not apartment:
            flash(f"Apartment '{slug}' not found", "error")
            return redirect(url_for('apartments_directory'))
        
        return render_template('apartment_home.html', 
                             apartment=apartment,
                             session=session)
    except Exception as e:
        logger.error(f"Error in apartment_home: {str(e)}", exc_info=True)
        return f"Error: {str(e)}<br><br>Check terminal for full traceback", 500 

@app.route('/apartments/<slug>/complete-registration', methods=['GET', 'POST'])
def complete_registration(slug):
    """Complete user registration with invite code - supports both admin and resident"""
    # Get apartment details
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, slug
                FROM apartments
                WHERE slug = %s
            """, (slug,))
            apartment = cur.fetchone()
    
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('index'))
    
    apartment_data = {
        'id': apartment[0],
        'name': apartment[1],
        'slug': apartment[2]
    }
    
    if request.method == 'GET':
        # Check if invite code is provided in URL
        invite_code = request.args.get('code', '')
        return render_template('complete_registration.html', apartment=apartment_data, invite_code=invite_code)
    
    # POST - Process the registration
    invite_code = request.form.get('invite_code', '').strip()
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    # Validation
    if not all([invite_code, username, full_name, email, password, confirm_password]):
        flash('All fields except phone are required', 'error')
        return render_template('complete_registration.html', apartment=apartment_data)
    
    if password != confirm_password:
        flash('Passwords do not match', 'error')
        return render_template('complete_registration.html', apartment=apartment_data)
    
    if len(password) < 8:
        flash('Password must be at least 8 characters long', 'error')
        return render_template('complete_registration.html', apartment=apartment_data)
    
    # Verify invite code and get role
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.id, i.apartment_id, i.role, i.type, i.flat
                FROM invites i
                JOIN apartments a ON a.id = i.apartment_id
                WHERE a.slug = %s
                  AND i.invite_code = %s
                  AND i.status = 'ACTIVE'
                  AND i.expires_at > now()
            """, (slug, invite_code))
            invite = cur.fetchone()
    
    if not invite:
        flash('Invalid or expired invite code', 'error')
        return render_template('complete_registration.html', apartment=apartment_data)
    
    invite_id, apartment_id, role, resident_type, flat = invite

    if role == 'admin':
        resident_type = None
    
    # Check if username already exists in this apartment
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM users
                WHERE apartment_id = %s AND username = %s
            """, (apartment_id, username))
            if cur.fetchone():
                flash('Username already exists in this apartment', 'error')
                return render_template('complete_registration.html', apartment=apartment_data)
    
    # Create user account
    password_hash = generate_password_hash(password)
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                if role == 'resident':

                    # Update plaveholder user created during invite generation
                    cur.execute("""
                        UPDATE users SET name = %s, username = %s, phone = %s, password_hash = %s, updated_at = now(), status = 'active'
                        WHERE apartment_id = %s AND email = %s AND status = 'invited'
                        RETURNING id
                    """, (full_name, username, phone, password_hash, apartment_id, email))
                    row = cur.fetchone()

                    if row:
                        user_id = row[0]
                    else:
                        # Insert new user
                        cur.execute("""
                            INSERT INTO users (apartment_id, name, username, email, phone, password_hash, flat, role, type, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                            RETURNING id
                        """, (apartment_id, full_name, username, email, phone, password_hash, flat, role, resident_type))
                        
                        user_id = cur.fetchone()[0]

                else:
                    # Admin registration
                    cur.execute("""
                        INSERT INTO users (apartment_id, name, username, email, phone, password_hash, role, type, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'admin', NULL, 'active', now())
                        RETURNING id
                    """, (apartment_id, full_name, username, email, phone, password_hash))
                    user_id = cur.fetchone()[0]
                
                # Mark invite as used
                cur.execute("""
                    UPDATE invites 
                    SET status = 'USED', used_by = %s
                    WHERE id = %s
                """, (user_id, invite_id))
                
                conn.commit()

        
        flash(f'✅ Welcome to {apartment_data["name"]}!', 'success')
        
        # Auto-login the user
        session[f'apartment_{slug}_logged_in'] = True
        session[f'apartment_{slug}_user'] = username
        session[f'apartment_{slug}_full_name'] = full_name
        session[f'apartment_{slug}_role'] = role
        session[f'apartment_{slug}_type'] = resident_type
        session[f'apartment_{slug}_flat'] = flat
        session['user_id'] = str(user_id)
        session['apartment_id'] = str(apartment_id)
        
        return redirect(url_for('apartment_home', slug=slug))
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        flash('An error occurred during registration. Please try again.', 'error')
        return render_template('complete_registration.html', apartment=apartment_data)

@app.route('/apartments/<slug>/join')
def apartment_join(slug):
    """Join apartment via invite link with code in URL"""
    invite_code = request.args.get('code', '')
    return redirect(url_for('complete_registration', slug=slug, code=invite_code))

@app.route('/apartments/<slug>/verify-invite', methods=['POST'])
def verify_invite_code(slug):
    """API endpoint to verify invite code and return role"""
    invite_code = request.json.get('invite_code', '').strip()
    
    if not invite_code:
        return jsonify({'valid': False, 'message': 'Invite code is required'})
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.role, i.type
                FROM invites i
                JOIN apartments a ON a.id = i.apartment_id
                WHERE a.slug = %s
                  AND i.invite_code = %s
                  AND i.status = 'ACTIVE'
                  AND i.expires_at > now()
            """, (slug, invite_code))
            invite = cur.fetchone()
    
    if not invite:
        return jsonify({
            'valid': False, 
            'message': 'Invalid or expired invite code'
        })
    
    role = invite[0]
    
    return jsonify({
        'valid': True,
        'role': role,
        'type': invite[1],
        'message': f'Valid invite code for {role} role'
    })

@app.route('/apartments/<slug>/check-username', methods=['POST'])
def check_username_availability(slug):
    """API endpoint to check if username is available"""
    username = request.json.get('username', '').strip()
    
    if not username:
        return jsonify({'available': False, 'message': 'Username is required'})
    
    # Validate username format
    if len(username) < 3:
        return jsonify({'available': False, 'message': 'Username must be at least 3 characters'})
    
    if len(username) > 20:
        return jsonify({'available': False, 'message': 'Username must be at most 20 characters'})
    
    # Get apartment
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        return jsonify({'available': False, 'message': 'Apartment not found'})
    
    # Check if username exists in this apartment
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM users
                WHERE apartment_id = %s AND username = %s
            """, (apartment['id'], username))
            count = cur.fetchone()[0]
    
    if count > 0:
        return jsonify({'available': False, 'message': 'Username already taken'})
    
    return jsonify({'available': True, 'message': 'Username is available'})

@app.route('/apartments/<slug>/auth', methods=['POST'])
def apartment_auth(slug):
    username = request.form.get('username')
    password = request.form.get('password')
    auth_type = request.form.get('auth_type', 'resident')

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.password_hash, u.role, u.name, u.username, a.id, u.flat
                FROM users u
                JOIN apartments a ON a.id = u.apartment_id
                WHERE a.slug = %s
                  AND u.username = %s
            """, (slug, username))
            user = cur.fetchone()

    if not user:
        flash('Invalid username or password', 'error')
        return redirect(url_for('apartment_home', slug=slug, error='Invalid credentials'))

    user_id, password_hash, role, name, user_username, apartment_id, flat = user

    if role != auth_type:
        flash('Unauthorized role', 'error')
        return redirect(url_for('apartment_home', slug=slug, error='Unauthorized role'))

    if not check_password_hash(password_hash, password):
        flash('Invalid password', 'error')
        return redirect(url_for('apartment_home', slug=slug, error='Invalid credentials'))

    # session - store consistently with complete_registration
    session[f"apartment_{slug}_logged_in"] = True
    session[f"apartment_{slug}_role"] = role
    session[f"apartment_{slug}_user"] = user_username
    session[f"apartment_{slug}_full_name"] = name
    session[f"apartment_{slug}_flat"] = flat
    session["user_id"] = str(user_id)
    session["apartment_id"] = str(apartment_id)


    flash(f'Welcome, {name}!', 'success')
    return redirect(url_for('apartment_home', slug=slug))

@app.route('/apartments/<slug>/logout')
def apartment_logout(slug):
    """Logout from apartment"""
    for key in [f'apartment_{slug}_logged_in', f'apartment_{slug}_user',
                f'apartment_{slug}_role', f'apartment_{slug}_full_name',
                f'apartment_{slug}_flat', f'apartment_{slug}_type',
                'user_id', 'apartment_id']:
        session.pop(key, None)
    return redirect(url_for('apartment_home', slug=slug))

# ============================================================================
# RESIDENT ROUTES (User auth required)
# ============================================================================

@app.route('/apartments/<slug>/resident/neighbors')
@apartment_login_required
def resident_neighbors(slug):
    """Resident neighbors/members page - shows all apartment members"""
    apartment = get_apartment_by_slug(slug)
    username = session.get(f'apartment_{slug}_user')
    
    # Fetch all active residents from database (excluding admin and inactive members)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, username, email, phone, role, flat, type, status
                FROM users
                WHERE apartment_id = %s AND role != 'admin'
                ORDER BY flat, name
            """, (apartment['id'],))
            residents_data = cur.fetchall()
    
    apartment_residents = []
    for row in residents_data:
        apartment_residents.append({
            'id': row[0],
            'full_name': row[1],
            'username': row[2],
            'email': row[3],
            'phone': row[4],
            'role': row[5],
            'flat_number': row[6],
            'resident_type': row[7] if len(row) > 7 else 'owner',
            'status': row[8] if len(row) > 8 else 'active'
        })
    
    return render_template('resident_neighbors.html',
                         apartment=apartment,
                         username=username,
                         residents=apartment_residents)

@app.route('/apartments/<slug>/resident/payments')
@apartment_login_required
def resident_payments(slug):
    """Resident payments page - shows assigned expense payments"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    username = session.get(f'apartment_{slug}_user')
    user_id = session.get("user_id")
    
    # Debug logging
    logger.info(f"Resident payments requested - User: {username}, User ID: {user_id}, Apartment: {apartment['id']}")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                
                # All bills assigned to this resident
                cur.execute("""
                    SELECT b.id, b.title, b.amount, b.due_date, b.status, b.paid_at, b.confirmed, b.proof_url, p.description
                    FROM bills b
                    LEFT JOIN payments p ON b.payment_id = p.id
                    WHERE b.user_id = %s AND b.apartment_id = %s
                    ORDER BY b.created_at DESC
                """, (user_id, apartment['id']))
                rows = cur.fetchall()
                logger.info(f"Bills fetched: {len(rows)} bills found")
                
                bills = [
                    {
                        'id': row[0],
                        'title': row[1],
                        'amount': row[2],
                        'due_date': row[3],
                        'status': row[4],
                        'paid_at': row[5],
                        'confirmed': row[6],
                        'proof_url': row[7],
                        'description': row[8]
                    } for row in rows
                ]

                # Split into active (pending/overdue) and past (paid)
                active_bills = [b for b in bills if b['status'] in ('pending', 'overdue')]
                payment_history = [b for b in bills if b['status'] == 'paid']

                # Summarize stats
                total_overdue = sum(b['amount'] for b in active_bills if b['status'] == 'overdue')
                total_pending = sum(b['amount'] for b in active_bills if b['status'] == 'pending')
                total_paid = sum(b['amount'] for b in payment_history)
                
                logger.info(f"Stats - Active: {len(active_bills)}, History: {len(payment_history)}, Total Due: {total_pending + total_overdue}")
    except Exception as e:
        logger.error(f"Error fetching payments: {e}", exc_info=True)
        flash('Error fetching payment data. Please try again later.', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    current_resident = {'flat_number': session.get(f'apartment_{slug}_flat', 'N/A')}
    return render_template('apartment_payments.html', apartment=apartment, username=username, current_resident=current_resident, bills=bills, active_bills=active_bills, payment_history=payment_history, total_overdue=total_overdue, total_pending=total_pending, total_paid=total_paid)

@app.route('/apartments/<slug>/resident/expenses')
@apartment_login_required
def resident_expenses(slug):
    """Resident expenses view - shows apartment expenses (read-only)"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    username = session.get(f'apartment_{slug}_user')
    
    month_filter = request.args.get('month')

    if not month_filter:
        current_date = date.today()
        month_filter = current_date.strftime('%Y-%m')

    query = """ SELECT id, title, amount, description, date, category, receipt
                FROM expenses
                WHERE apartment_id = %s """
    
    params = [apartment['id']]

    if month_filter == 'last_3_months':
        query += " AND date >= date_trunc('month', CURRENT_DATE) - interval '2 months' "
        query += " ORDER BY date DESC"

    else:
        start_date = f"{month_filter}-01"
        query += " AND date >= %s AND date < (%s::date + interval '1 month') "
        query += " ORDER BY date DESC"
        params.extend([start_date, start_date])
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            expenses_data = cur.fetchall()            
    
    # Process expenses
    expenses_list = []
    total_amount = 0
    for row in expenses_data:
        expense = {
            'id': row[0],
            'title': row[1],
            'amount': row[2],
            'description': row[3],
            'date': row[4],
            'category': row[5],
            'receipt': row[6]
        }
        expenses_list.append(expense)
        total_amount += float(row[2])
    
    expense_count = len(expenses_list)
    
    # Get available months for filter dropdown (last 2 specific months)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT EXTRACT(YEAR FROM date) as year, EXTRACT(MONTH FROM date) as month
                FROM expenses
                WHERE apartment_id = %s
                ORDER BY year DESC, month DESC
                LIMIT 3
            """, (apartment['id'],))
            months_data = cur.fetchall()
    
    available_months = []
    for row in months_data:
        if row[0] and row[1]:
            year = int(row[0])
            month = int(row[1])
            available_months.append({
                'value': f"{year}-{month:02d}",
                'label': datetime(year, month, 1).strftime('%B %Y')
            })
    
    return render_template('apartment_expenses.html', 
                         apartment=apartment, 
                         username=username,
                         expenses=expenses_list,
                         total_amount=total_amount,
                         expense_count=expense_count,
                         available_months=available_months,
                         selected_month=month_filter,
                         today=date.today().strftime('%Y-%m-%d'))

# ================================================================================================================================================================
# works
# ================================================================================================================================================================
@app.route('/apartments/<slug>/resident/works')
@apartment_login_required
def resident_works(slug):
    """Resident view of all the works"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get all works for this apartment
                cur.execute("""
                    SELECT id, title, description, estimated_cost, actual_cost, status, start_date, end_date
                    FROM works
                    WHERE apartment_id = %s
                    ORDER BY
                        CASE status
                            WHEN 'ongoing' THEN 1
                            WHEN 'planned' THEN 2
                            WHEN 'completed' THEN 3
                        END,
                        created_at DESC
                """, (apartment['id'],))
                works = [
                    {
                        'id': row[0],
                        'title': row[1],
                        'description': row[2],
                        'estimated_cost': row[3],
                        'actual_cost': row[4],
                        'status': row[5],
                        'start_date': row[6].strftime('%d %b %Y') if row[6] else None,
                        'end_date': row[7].strftime('%d %b %Y') if row[7] else None
                    }
                    for row in cur.fetchall()
                ]

                if works:
                    work_ids = [w['id'] for w in works]
                    cur.execute("""
                        SELECT id, work_id, title, is_done, photo_url, done_at
                        FROM work_checkpoints
                        WHERE work_id = ANY(%s)
                        ORDER BY created_at ASC
                    """, (work_ids,))

                    checkpoints_by_work = defaultdict(list)
                    for row in cur.fetchall():
                        checkpoints_by_work[row[1]].append({
                            'id': row[0],
                            'work_id': row[1],
                            'title': row[2],
                            'is_done': row[3],
                            'photo_url': row[4],
                            'done_at': row[5].strftime('%d %b %Y, %H:%M') if row[5] else None
                        })
                    for work in works:
                        work['checkpoints'] = checkpoints_by_work.get(work['id'], [])
                        total_checkpoints = len(work['checkpoints'])
                        completed_checkpoints = len([cp for cp in work['checkpoints'] if cp['is_done']])
                        work['progress'] = (completed_checkpoints / total_checkpoints * 100) if total_checkpoints > 0 else 0


                # Stats
                total_works = len(works)
                ongoing_works = len([w for w in works if w['status'] == 'ongoing'])
                planned_works = len([w for w in works if w['status'] == 'planned'])
                completed_works = len([w for w in works if w['status'] == 'completed'])

    except Exception as e:
        logger.error(f"Error fetching works: {e}", exc_info=True)
        flash('Error fetching works data. Please try again later.', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    return render_template('apartment_works.html', apartment=apartment, works=works, total_works=total_works, ongoing_works=ongoing_works, planned_works=planned_works, completed_works=completed_works)

# ==========================================================================================================================================================================================
# COMPLAINTS ROUTES
# ==========================================================================================================================================================================================

@app.route('/apartments/<slug>/resident/complaints')
@apartment_login_required
def resident_complaints(slug):
    """Community complaints board"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    username = session.get(f'apartment_{slug}_user')

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                
                # All complaints of this apartment
                cur.execute("""
                    SELECT c.id, c.title, c.description, c.status, c.created_at, c.updated_at, c.user_id, c.photo_url, u.name, u.flat
                    FROM complaints c
                    JOIN users u ON c.user_id = u.id
                    WHERE c.apartment_id = %s
                    ORDER BY c.created_at DESC
                """, (apartment['id'],))
                complaints = [
                    {
                        'id': row[0],
                        'title': row[1],
                        'description': row[2],
                        'status': row[3],
                        'created_at': row[4],
                        'updated_at': row[5],
                        'user_id': row[6],
                        'photo_url': row[7],
                        'user_name': row[8],
                        'user_flat': row[9]
                    }
                    for row in cur.fetchall()
                ]
                
                if complaints:
                    complaint_ids = [c['id'] for c in complaints]
                    cur.execute("""
                        SELECT cc.complaint_id, cc.comment, cc.is_admin, cc.created_at, c.updated_at, u.name
                        FROM complaint_comments cc
                        JOIN users u ON cc.user_id = u.id
                        JOIN complaints c ON cc.complaint_id = c.id
                        WHERE cc.complaint_id = ANY(%s)
                        ORDER BY cc.created_at ASC
                    """, (complaint_ids,))

                    comments_by_complaint = defaultdict(list)
                    for row in cur.fetchall():
                        comments_by_complaint[row[0]].append({
                            'comment': row[1],
                            'is_admin': row[2],
                            'created_at': row[3].strftime('%d %b %Y, %H:%M') if row[3] else None,
                            'updated_at': row[4].strftime('%d %b %Y, %H:%M') if row[4] else None,
                            'user_name': row[5]
                        })

                    for complaint in complaints:
                        complaint['comments'] = comments_by_complaint.get(complaint['id'], [])

                # Stats
                stats = {
                    'total': len(complaints),
                    'open': len([c for c in complaints if c['status'] == 'open']),
                    'in_progress': len([c for c in complaints if c['status'] == 'in_progress']),
                    'resolved': len([c for c in complaints if c['status'] == 'resolved']),
                }
    except Exception as e:
        logger.error(f"Error fetching complaints: {e}", exc_info=True)
        flash('Error fetching complaints data. Please try again later.', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    return render_template('apartment_complaints.html', apartment=apartment, resident={'username': username}, complaints=complaints, stats=stats)
                            
@app.route('/apartments/<slug>/resident/complaints/submit', methods=['POST'])
@apartment_login_required
def submit_complaint(slug):
    """Submit a new complaint"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    username = session.get(f'apartment_{slug}_user')
    user_id = session.get("user_id")
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    photo_url = None
    photo_file = request.files.get('photo')

    if photo_file and photo_file.filename:
        try:
            upload_result = cloudinary.uploader.upload(
                photo_file,
                folder='complaints/photos/'
            )
            photo_url = upload_result.get('secure_url')
        except Exception as e:
            logger.error(f"Photo upload failed: {e}")
            flash('Photo upload failed. Please try again.', 'error')
            return redirect(url_for('resident_complaints', slug=slug))
        

    if not all([title, description]):
        flash('Title and description are required', 'error')
        return redirect(url_for('resident_complaints', slug=slug))
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO complaints (apartment_id, user_id, title, description, photo_url, status)
                    VALUES (%s, %s, %s, %s, %s, 'open')
                """, (apartment['id'], user_id, title, description, photo_url))
                conn.commit()
        flash('Complaint submitted successfully', 'success')
    except Exception as e:
        logger.error(f"Error submitting complaint: {e}", exc_info=True)
        flash('Error submitting complaint. Please try again.', 'error')
    return redirect(url_for('resident_complaints', slug=slug))

@app.route('/apartments/<slug>/resident/complaints/<int:complaint_id>/comment', methods=['POST'])
@apartment_login_required
def submit_complaint_comment(slug, complaint_id):
    """Submit a comment on a complaint"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    user_id = session.get("user_id")
    comment = request.form.get('comment', '').strip()

    if not comment:
        flash('Comment cannot be empty', 'error')
        return redirect(url_for('resident_complaints', slug=slug))
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO complaint_comments (complaint_id, user_id, comment)
                    VALUES (%s, %s, %s)
                """, (complaint_id, user_id, comment))

                cur.execute("""
                    UPDATE complaints SET updated_at = now() WHERE id = %s
                """, (complaint_id,))

        flash('Comment added successfully', 'success')
    except Exception as e:
        logger.error(f"Error submitting comment: {e}", exc_info=True)
        flash('Error submitting comment. Please try again.', 'error')

    return redirect(url_for('resident_complaints', slug=slug))

# ===================================================================================================================================================================
# RESIDENT PAYMENT ROUTES
# ===================================================================================================================================================================

@app.route('/apartments/<slug>/resident/bills/<int:bill_id>/pay', methods=['POST'])
@apartment_login_required
def pay_bill(slug, bill_id):
    """Resident submit payment - supports upload and cash methods with optional proof files"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        return jsonify({'success': False, 'message': 'Apartment not found'}), 404
    
    user_id = session.get('user_id')
    username = session.get(f'apartment_{slug}_user')
    payment_method = request.form.get('payment_method', 'upload')
    
    # Validate payment method
    if payment_method not in ['upload', 'cash']:
        return jsonify({'success': False, 'message': 'Invalid payment method'}), 400
    
    # Handle optional file uploads
    proof_url = None
    receipt_files = request.files.getlist('receipts')
    
    if receipt_files and len(receipt_files) > 0:
        # Upload first file (in production, could handle multiple)
        for file in receipt_files:
            if file and file.filename:
                try:
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder=f"apartments/{slug}/bills/{bill_id}"
                    )
                    proof_url = upload_result.get('secure_url')
                    break  # Use first successful upload
                except Exception as e:
                    logger.error(f"Error uploading file: {str(e)}")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Update bill status to 'paid'
                cur.execute("""
                    UPDATE bills
                    SET status = 'paid', proof_url = %s, paid_at = NOW()
                    WHERE id = %s AND user_id = %s AND apartment_id = %s
                    RETURNING id
                """, (proof_url, bill_id, user_id, apartment['id']))
                
                result = cur.fetchone()
                if not result:
                    return jsonify({'success': False, 'message': 'Bill not found or not authorized'}), 404
                
                conn.commit()
        
        # Log payment submission
        logger.info(f"Bill {bill_id} marked as paid via {payment_method} by user {username}")
        
        return jsonify({
            'success': True, 
            'message': f'Payment submitted successfully via {payment_method}',
            'bill_id': bill_id
        })
        
    except Exception as e:
        logger.error(f"Error processing payment for bill {bill_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Error processing payment. Please try again.'}), 500

# ============================================================================
# RESIDENT ANALYTICS
# ============================================================================

@app.route('/apartments/<slug>/resident/analytics')
@apartment_login_required
def apartment_analytics(slug):
    """Resident analytics – community insights from a resident's perspective"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))

    username  = session.get(f'apartment_{slug}_user')
    user_id   = session.get('user_id')
    apt_id    = apartment['id']

    today = date.today()
    months_list = []
    for i in range(5, -1, -1):
        year  = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year  -= 1
        months_list.append(date(year, month, 1).strftime('%b %y'))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                # ── MY PERSONAL BILLS ──────────────────────────────────────
                cur.execute("""
                    SELECT
                        COUNT(*)                                              AS total,
                        COUNT(*) FILTER (WHERE status = 'paid')              AS paid,
                        COUNT(*) FILTER (WHERE status = 'pending')           AS pending,
                        COUNT(*) FILTER (WHERE status = 'pending'
                                         AND due_date < CURRENT_DATE)        AS overdue,
                        COALESCE(SUM(amount) FILTER (WHERE status = 'paid'), 0)     AS paid_amt,
                        COALESCE(SUM(amount) FILTER (WHERE status = 'pending'), 0)  AS pending_amt
                    FROM bills
                    WHERE user_id = %s AND apartment_id = %s
                """, (user_id, apt_id))
                mb = cur.fetchone()
                my_bills = {
                    'total': mb[0] or 0, 'paid': mb[1] or 0,
                    'pending': mb[2] or 0, 'overdue': mb[3] or 0,
                    'paid_amt': float(mb[4] or 0), 'pending_amt': float(mb[5] or 0),
                    'score': round((mb[1] / mb[0] * 100) if mb[0] else 100)
                }

                # ── COMMUNITY PAYMENT WALL ────────────────────────────────
                # One row per resident; show flat + first-name + payment score
                # for peer accountability — amounts hidden, just status signal
                cur.execute("""
                    SELECT
                        u.id,
                        SPLIT_PART(u.name, ' ', 1)                          AS first_name,
                        u.flat,
                        COUNT(b.id)                                         AS total_bills,
                        COUNT(b.id) FILTER (WHERE b.status = 'paid')        AS paid_bills,
                        COUNT(b.id) FILTER (WHERE b.status = 'pending'
                                             AND b.due_date < CURRENT_DATE) AS overdue_bills
                    FROM users u
                    LEFT JOIN bills b ON b.user_id = u.id AND b.apartment_id = %s
                    WHERE u.apartment_id = %s AND u.role = 'resident' AND u.status = 'active'
                    GROUP BY u.id, first_name, u.flat
                    ORDER BY u.flat
                """, (apt_id, apt_id))
                payment_wall = []
                for row in cur.fetchall():
                    total  = row[3] or 0
                    paid   = row[4] or 0
                    overdue= row[5] or 0
                    score  = round((paid / total * 100) if total > 0 else 100)
                    if total == 0:
                        status = 'none'
                    elif overdue > 0:
                        status = 'overdue'
                    elif paid == total:
                        status = 'paid'
                    else:
                        status = 'pending'
                    payment_wall.append({
                        'id': row[0],
                        'first_name': row[1] or '?',
                        'flat': row[2] or '–',
                        'score': score,
                        'status': status,
                        'is_me': (row[0] == user_id)
                    })

                # ── EXPENSE CATEGORIES (last 3 months) ────────────────────
                cur.execute("""
                    SELECT COALESCE(category, 'Other') AS cat,
                           COALESCE(SUM(amount), 0)   AS total
                    FROM expenses
                    WHERE apartment_id = %s
                      AND date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '2 months'
                    GROUP BY cat
                    ORDER BY total DESC
                """, (apt_id,))
                expense_cats = [{'label': r[0].title(), 'amount': float(r[1])} for r in cur.fetchall()]
                expense_total_3m = sum(e['amount'] for e in expense_cats)

                # ── MONTHLY INCOME TREND (6 months) ──────────────────────
                cur.execute("""
                    SELECT TO_CHAR(paid_at, 'Mon YY') AS lbl,
                           COALESCE(SUM(amount), 0)   AS total
                    FROM bills
                    WHERE apartment_id = %s AND status = 'paid' AND paid_at IS NOT NULL
                      AND paid_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                    GROUP BY lbl
                """, (apt_id,))
                income_map     = {r[0]: float(r[1]) for r in cur.fetchall()}
                monthly_income = [income_map.get(m, 0) for m in months_list]

                # ── WORKS IN PROGRESS ─────────────────────────────────────
                cur.execute("""
                    SELECT id, title, status, estimated_cost, actual_cost, start_date, end_date
                    FROM works
                    WHERE apartment_id = %s AND status IN ('ongoing', 'planned')
                    ORDER BY CASE status WHEN 'ongoing' THEN 1 ELSE 2 END, created_at DESC
                    LIMIT 6
                """, (apt_id,))
                works_raw = cur.fetchall()
                active_works = []
                if works_raw:
                    work_ids = [r[0] for r in works_raw]
                    cur.execute("""
                        SELECT work_id,
                               COUNT(*) AS total,
                               COUNT(*) FILTER (WHERE is_done) AS done
                        FROM work_checkpoints WHERE work_id = ANY(%s)
                        GROUP BY work_id
                    """, (work_ids,))
                    cp_map = {r[0]: {'total': r[1], 'done': r[2]} for r in cur.fetchall()}
                    for r in works_raw:
                        cp  = cp_map.get(r[0], {'total': 0, 'done': 0})
                        pct = round((cp['done'] / cp['total'] * 100) if cp['total'] else 0)
                        active_works.append({
                            'id': r[0], 'title': r[1], 'status': r[2],
                            'progress': pct,
                            'checkpoints_done': cp['done'],
                            'checkpoints_total': cp['total'],
                            'start_date': r[5].strftime('%d %b') if r[5] else None,
                            'end_date': r[6].strftime('%d %b %Y') if r[6] else None
                        })

                # ── COMPLAINT SUMMARY ─────────────────────────────────────
                cur.execute("""
                    SELECT
                        COUNT(*)                                    AS total,
                        COUNT(*) FILTER (WHERE status='open')       AS open,
                        COUNT(*) FILTER (WHERE status='in_progress')AS in_prog,
                        COUNT(*) FILTER (WHERE status='resolved')   AS resolved
                    FROM complaints WHERE apartment_id = %s
                """, (apt_id,))
                cc = cur.fetchone()
                complaint_summary = {
                    'total': cc[0] or 0, 'open': cc[1] or 0,
                    'in_progress': cc[2] or 0, 'resolved': cc[3] or 0
                }

    except Exception as e:
        logger.error(f"Error loading resident analytics: {e}", exc_info=True)
        flash('Error loading analytics data', 'error')
        return redirect(url_for('apartment_home', slug=slug))

    return render_template(
        'apartment_analytics.html',
        apartment=apartment,
        username=username,
        user_id=user_id,
        months_list=months_list,
        my_bills=my_bills,
        payment_wall=payment_wall,
        expense_cats=expense_cats,
        expense_total_3m=expense_total_3m,
        monthly_income=monthly_income,
        active_works=active_works,
        complaint_summary=complaint_summary
    )

# ============================================================================
# ADMIN MEMBERS MANAGEMENT
# ============================================================================

@app.route('/apartments/<slug>/admin/members')
@admin_login_required
def admin_members(slug):
    """Admin members management page with invite system"""

    apartment = get_apartment_by_slug(slug)
    username = session.get(f'apartment_{slug}_user')
    
    # Fetch residents from database
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, username, email, phone, role, flat, type, flat, status
                FROM users
                WHERE apartment_id = %s AND role != 'admin'
                ORDER BY id DESC
            """, (apartment['id'],))
            residents_data = cur.fetchall()
    
    apartment_residents = []
    for row in residents_data:
        apartment_residents.append({
            'id': row[0],
            'full_name': row[1],
            'username': row[2],
            'email': row[3],
            'phone': row[4],
            'role': row[5],
            'flat_number': row[6],
            'resident_type': row[7] if len(row) > 7 else 'owner',
            'status': row[8] if len(row) > 8 else 'active'
        })
    
    # Fetch pending invites from database
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, invite_code, role, status, expires_at, email, flat, type
                FROM invites
                WHERE apartment_id = %s AND status = 'ACTIVE'
                ORDER BY expires_at DESC
            """, (apartment['id'],))
            invites_data = cur.fetchall()
    
    apartment_invites = []
    for row in invites_data:
        apartment_invites.append({
            'id': row[0],
            'invite_code': row[1],
            'role': row[2],
            'status': row[3],
            'expires_at': row[4],
            'email': row[5] if len(row) > 5 else None,
            'flat_number': row[6] if len(row) > 6 else None,
            'resident_type': row[7] if len(row) > 7 else 'owner'
        })
    
    return render_template('admin_members.html', apartment=apartment, username=username, residents=apartment_residents, pending_invites=apartment_invites)

@app.route('/apartments/<slug>/admin/flats/add', methods=['POST'])
@admin_login_required
def admin_add_flat(slug):
    """Add a single flat and generate invite"""
    
    flat_number = request.form.get('flat_number')
    resident_email = request.form.get('email')
    resident_type = request.form.get('resident_type', 'owner')
    
    if not flat_number or not resident_email:
        flash('Flat number and email are required', 'error')
        return redirect(url_for('admin_members', slug=slug))
    
    # Get apartment details
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_members', slug=slug))
    
    # Generate unique invite code
    invite_code = generate_invite_code()
    
    # Insert invite into database
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO invites (apartment_id, invite_code, email, role, type, flat, status, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now() + interval '7 days')
                    RETURNING id
                """, (apartment['id'], invite_code, resident_email, 'resident', resident_type, flat_number, 'ACTIVE'))

                cur.execute("""
                    INSERT INTO users (apartment_id, email, flat, type, role, status, name, password_hash)
                    VALUES (%s, %s, %s, %s, 'resident', 'invited', %s, '')
                """, (apartment['id'], resident_email, flat_number, resident_type, resident_email.split('@')[0]))

            conn.commit()
        
        # Send email with invite code
        send_invite_email(resident_email, apartment['name'], invite_code, slug)
        
        flash(f'✅ Invite sent to {resident_email} for Flat {flat_number}!', 'success')
    except Exception as e:
        logger.error(f"Error creating invite: {str(e)}")
        flash(f'Error creating invite: {str(e)}', 'error')
    
    return redirect(url_for('admin_members', slug=slug))

@app.route('/apartments/<slug>/admin/flats/bulk-add', methods=['POST'])
@admin_login_required
def admin_bulk_add_flats(slug):
    """Bulk add flats and generate invites"""
    
    num_flats = int(request.form.get('num_flats', 0))
    if num_flats <= 0:
        flash('Please specify number of flats', 'error')
        return redirect(url_for('admin_members', slug=slug))
    
    # Get apartment details
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_members', slug=slug))
    
    generated_count = 0
    errors = []
    
    for i in range(num_flats):
        flat_number = request.form.get(f'flat_number_{i}', '').strip()
        flat_type = request.form.get(f'flat_type_{i}', 'owner')
        flat_email = request.form.get(f'flat_email_{i}', '').strip()
        
        if not flat_number or not flat_email:
            errors.append(f'Flat {i+1}: Missing flat number or email')
            continue
        
        # Generate unique invite code
        invite_code = generate_invite_code()
        
        # Insert invite into database
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO invites (apartment_id, invite_code, email, role, type, flat, status, expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, now() + interval '7 days')
                        RETURNING id
                    """, (apartment['id'], invite_code, flat_email, 'resident', flat_type, flat_number, 'ACTIVE'))

                    cur.execute("""
                        INSERT INTO users
                            (apartment_id, email, flat, type, role, status, name, password_hash)
                        VALUES (%s, %s, %s, %s, 'resident', 'invited', %s, '')
                    """, (apartment['id'], flat_email, flat_number, flat_type, flat_email.split('@')[0]))

                conn.commit()
            
            # Send email with invite code
            send_invite_email(flat_email, apartment['name'], invite_code, slug)
            generated_count += 1
        except Exception as e:
            logger.error(f"Error creating invite for {flat_email}: {str(e)}")
            errors.append(f'Flat {flat_number}: {str(e)}')
    
    if generated_count > 0:
        flash(f'✅ {generated_count} invites sent successfully!', 'success')
    if errors:
        for error in errors:
            flash(error, 'error')
    
    return redirect(url_for('admin_members', slug=slug))

@app.route('/apartments/<slug>/admin/invites/<invite_id>/resend', methods=['POST'])
@admin_login_required
def resend_invite(slug, invite_id):
    """Resend invite notification"""
    if session.get(f'apartment_{slug}_role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Get apartment details
        apartment = get_apartment_by_slug(slug)
        if not apartment:
            return jsonify({'error': 'Apartment not found'}), 404
        
        # Get invite details from database
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT email, invite_code, status
                    FROM invites
                    WHERE id = %s AND apartment_id = %s
                """, (invite_id, apartment['id']))
                invite_data = cur.fetchone()
        
        if not invite_data:
            return jsonify({'error': 'Invite not found'}), 404
        
        email, invite_code, status = invite_data
        
        if status != 'ACTIVE':
            return jsonify({'error': 'Invite is not active'}), 400
        
        # Resend the invite email
        send_invite_email(email, apartment['name'], invite_code, slug)
        
        return jsonify({'success': True, 'message': f'Invite resent to {email}'})
    except Exception as e:
        logger.error(f"Error resending invite {invite_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/apartments/<slug>/admin/residents/<resident_id>/toggle-status', methods=['POST'])
@admin_login_required
def toggle_resident_status(slug, resident_id):
    """Toggle resident status between active and inactive"""
    if session.get(f'apartment_{slug}_role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        new_status = data.get('status', 'active')
        
        if new_status not in ['active', 'inactive']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        apartment = get_apartment_by_slug(slug)
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users 
                    SET status = %s 
                    WHERE id = %s AND apartment_id = %s AND role != 'admin'
                """, (new_status, resident_id, apartment['id']))
        
        logger.info(f"Resident {resident_id} status changed to {new_status}")
        return jsonify({'success': True, 'message': f'Status updated to {new_status}'})
        
    except Exception as e:
        logger.error(f"Error toggling resident status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/apartments/<slug>/admin/invites/<invite_id>/delete', methods=['POST'])
@admin_login_required
def delete_invite(slug, invite_id):
    """Delete an invite"""
    if session.get(f'apartment_{slug}_role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM invites
                    WHERE id = %s
                """, (invite_id,))

            if cur.rowcount == 0:
                return jsonify({'error': 'Invite not found'}), 404
            
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting invite {invite_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/apartments/<slug>/admin/residents/<resident_id>/remove', methods=['POST'])
@admin_login_required
def remove_resident(slug, resident_id):
    """Remove a resident from the apartment"""
    if session.get(f'apartment_{slug}_role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        apartment = get_apartment_by_slug(slug)
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Delete the user (cascading deletes will handle related records)
                cur.execute("""
                    DELETE FROM users
                    WHERE id = %s AND apartment_id = %s AND role != 'admin'
                """, (resident_id, apartment['id']))
                
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Resident not found or cannot be removed'}), 404
        
        logger.info(f"Resident {resident_id} removed from apartment {slug}")
        return jsonify({'success': True, 'message': 'Resident removed successfully'})
        
    except Exception as e:
        logger.error(f"Error removing resident: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ADMIN EXPENSES
# ============================================================================

@app.route('/apartments/<slug>/admin/expenses', methods=['GET', 'POST'])
@admin_login_required
def admin_expenses(slug):
    """Admin expenses management page"""

    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    username = session.get(f'apartment_{slug}_user')

    if request.method == 'POST':
        # Handle adding new expense
        title = request.form.get('title', '').strip()
        amount = request.form.get('amount', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('date', '').strip()
        category = request.form.get('category', '').strip().lower()
        
        # Basic validation
        if not title or not amount or not category:
            flash('Title, Amount, Date, and Category are required fields.', 'error')
            return redirect(url_for('admin_expenses', slug=slug))
        
        try:
            amount_value = float(amount)
            expense_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Handle receipt upload to Cloudinary
            receipt_url = None
            receipt_file = request.files.get('receipt')
            
            if receipt_file and receipt_file.filename:
                upload_result = cloudinary.uploader.upload(
                    receipt_file,
                    folder=f'apartments/{slug}/expenses',
                    resource_type='auto'
                )
                receipt_url = upload_result.get('secure_url')
            
            # Insert into database
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO expenses (apartment_id, title, amount, description, date, category, receipt)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (apartment['id'], title, amount_value, description, expense_date, category, receipt_url))
                conn.commit()
             

            flash('✅ Expense added successfully!', 'success')
        except Exception as e:
            logger.error(f"Error adding expense: {str(e)}")
            flash(f'Error adding expense: {str(e)}', 'error')
        
        return redirect(url_for('admin_expenses', slug=slug))
    
    # GET - Fetch expenses from database with month filter only (category filtering via JS)
    month_filter = request.args.get('month')
    
    # Default to current month if no filter provided
    if not month_filter:
        current_date = date.today()
        month_filter = current_date.strftime('%Y-%m')

    query = """SELECT id, title, amount, description, date, category, receipt
               FROM expenses
               WHERE apartment_id = %s"""
    
    params = [apartment['id']]
    
    # Build query with month filter only
    if month_filter == 'last_3_months':
        # Last 3 months
        query += " AND date >= date_trunc('month', CURRENT_DATE) - interval '2 months'"
        query += " ORDER BY date DESC"

    else:
        # Specific month
        start_date = f"{month_filter}-01"
        query += " AND date >= %s AND date < (%s::date + interval '1 month')"
        query += " ORDER BY date DESC"
        params.extend([start_date, start_date])
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            expenses_data = cur.fetchall()
    
    apartment_expenses = []
    for row in expenses_data:
        expense_date = row[4]
        apartment_expenses.append({
            'id': row[0],
            'title': row[1],
            'amount': float(row[2]),
            'description': row[3],
            'date': expense_date.strftime('%Y-%m-%d') if expense_date else None,
            'month': expense_date.strftime('%Y-%m') if expense_date else None,
            'category': row[5],
            'receipt_url': row[6],
        })
    
    # Fetch residents for custom division (excluding admin)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, username, role
                FROM users
                WHERE apartment_id = %s AND role != 'admin'
                ORDER BY name
            """, (apartment['id'],))
            residents_data = cur.fetchall()
    
    residents_list = []
    for row in residents_data:
        residents_list.append({
            'id': row[0],
            'name': row[1],
            'username': row[2],
            'role': row[3]
        })
    
    # Get available months for filter dropdown (last 2 specific months)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT EXTRACT(YEAR FROM date) as year, EXTRACT(MONTH FROM date) as month
                FROM expenses
                WHERE apartment_id = %s
                ORDER BY year DESC, month DESC
                LIMIT 3
            """, (apartment['id'],))
            months_data = cur.fetchall()
    
    available_months = []
    for row in months_data:
        if row[0] and row[1]:
            year = int(row[0])
            month = int(row[1])
            available_months.append({
                'value': f"{year}-{month:02d}",
                'label': datetime(year, month, 1).strftime('%B %Y')
            })
    
    return render_template('admin_expenses.html',
                         apartment=apartment,
                         username=username,
                         expenses=apartment_expenses,
                         residents=residents_list,
                         available_months=available_months,
                         selected_month=month_filter,
                         today=date.today().strftime('%Y-%m-%d'))

@app.route('/apartments/<slug>/admin/expenses/<int:expense_id>/edit', methods=['POST'])
@admin_login_required
def edit_expense(slug, expense_id):
    """Edit an existing expense"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    # Get form data
    title = request.form.get('title', '').strip()
    amount = request.form.get('amount', '').strip()
    description = request.form.get('description', '').strip()
    date_str = request.form.get('date', '').strip()
    category = request.form.get('category', '').strip().lower()
    
    # Basic validation
    if not title or not amount or not date_str or not category:
        flash('Title, Amount, Date, and Category are required fields.', 'error')
        return redirect(url_for('admin_expenses', slug=slug))
    
    try:
        amount_value = float(amount)
        expense_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Handle receipt upload to Cloudinary (if new file provided)
        receipt_url = None
        receipt_file = request.files.get('receipt')
        
        if receipt_file and receipt_file.filename:
            upload_result = cloudinary.uploader.upload(
                receipt_file,
                folder='apartments/receipts/'
            )
            receipt_url = upload_result.get('secure_url')
        
        # Update database
        with get_conn() as conn:
            with conn.cursor() as cur:
                if receipt_url:
                    # Update with new receipt
                    cur.execute("""
                        UPDATE expenses 
                        SET title = %s, amount = %s, description = %s, date = %s, 
                            category = %s, receipt = %s
                        WHERE id = %s AND apartment_id = %s
                    """, (title, amount_value, description, expense_date, category, receipt_url, expense_id, apartment['id']))
                else:
                    # Update without changing receipt
                    cur.execute("""
                        UPDATE expenses 
                        SET title = %s, amount = %s, description = %s, date = %s, 
                            category = %s
                        WHERE id = %s AND apartment_id = %s
                    """, (title, amount_value, description, expense_date, category, expense_id, apartment['id']))
            conn.commit()
        
        flash('✅ Expense updated successfully!', 'success')
    except Exception as e:
        logger.error(f"Error updating expense: {str(e)}")
        flash(f'Error updating expense: {str(e)}', 'error')
    
    return redirect(url_for('admin_expenses', slug=slug))

@app.route('/apartments/<slug>/admin/expenses/<int:expense_id>/delete', methods=['POST'])
@admin_login_required
def delete_expense(slug, expense_id):
    """Delete an expense"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM expenses
                    WHERE id = %s AND apartment_id = %s
                """, (expense_id, apartment['id']))
            conn.commit()
        
        flash('✅ Expense deleted successfully!', 'success')
    except Exception as e:
        logger.error(f"Error deleting expense: {str(e)}")
        flash(f'Error deleting expense: {str(e)}', 'error')
    
    return redirect(url_for('admin_expenses', slug=slug))

# ============================================================================
# ADMIN COMPLAINTS ROUTES
# ============================================================================

@app.route('/apartments/<slug>/admin/complaints')
@admin_login_required
def admin_complaints(slug):
    """Admin complaints management"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT c.id, c.title, c.description, c.status,
                           c.created_at, c.updated_at, u.name, u.flat, c.photo_url
                    FROM complaints c
                    JOIN users u ON u.id = c.user_id
                    WHERE c.apartment_id = %s
                    ORDER BY
                        CASE c.status
                            WHEN 'open' THEN 1
                            WHEN 'in_progress' THEN 2
                            WHEN 'resolved' THEN 3
                        END,
                        c.created_at DESC
                """, (apartment['id'],))
                complaints = [
                    {
                        'id': r[0], 'title': r[1], 'description': r[2],
                        'status': r[3],
                        'created_at': r[4].strftime('%d %b %Y') if r[4] else None,
                        'updated_at': r[5].strftime('%d %b %Y') if r[5] else None,
                        'resident_name': r[6], 'flat': r[7], 'photo_url': r[8]
                    }
                    for r in cur.fetchall()
                ]

                if complaints:
                    complaint_ids = [c['id'] for c in complaints]
                    cur.execute("""
                        SELECT cc.complaint_id, cc.comment, cc.is_admin,
                               cc.created_at, u.name
                        FROM complaint_comments cc
                        JOIN users u ON u.id = cc.user_id
                        WHERE cc.complaint_id = ANY(%s)
                        ORDER BY cc.created_at ASC
                    """, (complaint_ids,))

                    comments_map = defaultdict(list)
                    for r in cur.fetchall():
                        comments_map[r[0]].append({
                            'comment': r[1], 'is_admin': r[2],
                            'created_at': r[3].strftime('%d %b %Y, %H:%M') if r[3] else None,
                            'author': r[4]
                        })
                    for c in complaints:
                        c['comments'] = comments_map.get(c['id'], [])

                stats = {
                    'total': len(complaints),
                    'open': sum(1 for c in complaints if c['status'] == 'open'),
                    'in_progress': sum(1 for c in complaints if c['status'] == 'in_progress'),
                    'resolved': sum(1 for c in complaints if c['status'] == 'resolved'),
                }

    except Exception as e:
        logger.error(f"Error loading admin complaints: {e}", exc_info=True)
        flash('Something went wrong', 'error')
        return redirect(url_for('admin_complaints', slug=slug))

    return render_template(
        'admin_complaints.html',
        apartment=apartment,
        complaints=complaints,
        stats=stats
    )

@app.route('/apartments/<slug>/admin/complaints/<int:complaint_id>/status', methods=['POST'])
@admin_login_required
def update_complaint_status(slug, complaint_id):
    """Admin updates complaint status"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_complaints', slug=slug))

    status = request.form.get('status', '').strip()
    if status not in ('open', 'in_progress', 'resolved'):
        flash('Invalid status', 'error')
        return redirect(url_for('admin_complaints', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE complaints
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s AND apartment_id = %s
                    RETURNING id
                """, (status, complaint_id, apartment['id']))

                if not cur.fetchone():
                    flash('Complaint not found', 'error')
                    return redirect(url_for('admin_complaints', slug=slug))

        flash('Status updated', 'success')

    except Exception as e:
        logger.error(f"Error updating complaint status: {e}", exc_info=True)
        flash('Something went wrong', 'error')

    return redirect(url_for('admin_complaints', slug=slug))

@app.route('/apartments/<slug>/admin/complaints/<int:complaint_id>/comment', methods=['POST'])
@admin_login_required
def add_complaint_comment(slug, complaint_id):
    """Admin posts a comment on a complaint"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_complaints', slug=slug))
    
    admin_user_id = session.get('user_id')

    comment = request.form.get('comment', '').strip()

    if not comment:
        flash('Comment cannot be empty', 'error')
        return redirect(url_for('admin_complaints', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify complaint belongs to this apartment
                cur.execute("""
                    SELECT id FROM complaints
                    WHERE id = %s AND apartment_id = %s
                """, (complaint_id, apartment['id']))

                if not cur.fetchone():
                    flash('Complaint not found', 'error')
                    return redirect(url_for('admin_complaints', slug=slug))

                cur.execute("""
                    INSERT INTO complaint_comments
                        (complaint_id, user_id, comment, is_admin)
                    VALUES (%s, %s, %s, TRUE)
                """, (complaint_id, admin_user_id, comment))

                # Also bump updated_at on the complaint
                cur.execute("""
                    UPDATE complaints SET updated_at = NOW()
                    WHERE id = %s
                """, (complaint_id,))

        flash('Comment added', 'success')

    except Exception as e:
        logger.error(f"Error adding comment: {e}", exc_info=True)
        flash('Something went wrong', 'error')

    return redirect(url_for('admin_complaints', slug=slug))

# ============================================================================
# WORK PROGRESS TRACKING ROUTES (Admin)
# ============================================================================

@app.route('/apartments/<slug>/admin/works')
@admin_login_required
def admin_works(slug):
    """Admin works management page"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT id, title, description, estimated_cost, actual_cost,
                           status, start_date, end_date, created_at
                    FROM works
                    WHERE apartment_id = %s
                    ORDER BY created_at DESC
                """, (apartment['id'],))
                works = [
                    {
                        'id': r[0], 'title': r[1], 'description': r[2],
                        'estimated_cost': float(r[3]) if r[3] else None,
                        'actual_cost': float(r[4]) if r[4] else None,
                        'status': r[5],
                        'start_date': r[6].strftime('%d %b %Y') if r[6] else None,
                        'end_date': r[7].strftime('%d %b %Y') if r[7] else None,
                        'created_at': r[8].strftime('%d %b %Y') if r[8] else None
                    }
                    for r in cur.fetchall()
                ]

                if works:
                    work_ids = [w['id'] for w in works]
                    cur.execute("""
                        SELECT id, work_id, title, is_done, photo_url, done_at
                        FROM work_checkpoints
                        WHERE work_id = ANY(%s)
                        ORDER BY created_at ASC
                    """, (work_ids,))
                    cp_map = defaultdict(list)
                    for r in cur.fetchall():
                        cp_map[r[1]].append({
                            'id': r[0], 'title': r[2], 'is_done': r[3],
                            'photo_url': r[4], 'done_at': r[5].strftime('%d %b %Y') if r[5] else None
                        })
                    for w in works:
                        w['checkpoints'] = cp_map.get(w['id'], [])
                        total = len(w['checkpoints'])
                        done  = sum(1 for c in w['checkpoints'] if c['is_done'])
                        w['progress'] = int((done / total) * 100) if total else 0

                stats = {
                    'total':     len(works),
                    'planned':   sum(1 for w in works if w['status'] == 'planned'),
                    'ongoing':   sum(1 for w in works if w['status'] == 'ongoing'),
                    'completed': sum(1 for w in works if w['status'] == 'completed'),
                }


    except Exception as e:
        logger.error(f"Error loading works: {e}", exc_info=True)
        flash('Something went wrong loading works', 'error')
        return redirect(url_for('admin_works', slug=slug))

    return render_template('admin_works.html', apartment=apartment, works=works, stats=stats)

@app.route('/apartments/<slug>/admin/works/create', methods=['POST'])
@admin_login_required
def create_work(slug):
    """Admin creates a new work"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))

    title          = request.form.get('title', '').strip()
    description    = request.form.get('description', '').strip()
    estimated_cost = request.form.get('estimated_cost', '').strip()
    start_date     = request.form.get('start_date', '').strip()
    end_date       = request.form.get('end_date', '').strip()

    if not all([title, estimated_cost, start_date]):
        flash('Title, Estimated Cost, and Start Date are required', 'error')
        return redirect(url_for('admin_works', slug=slug))

    try:
        estimated_cost = float(estimated_cost) if estimated_cost else None
        start_date     = date.fromisoformat(start_date) if start_date else None
        end_date       = date.fromisoformat(end_date) if end_date else None
    except ValueError:
        flash('Invalid cost or date format', 'error')
        return redirect(url_for('admin_works', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO works
                        (apartment_id, title, description, estimated_cost, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (apartment['id'], title, description, estimated_cost, start_date, end_date))

        flash(f'Work "{title}" created successfully', 'success')

    except Exception as e:
        logger.error(f"Error creating work: {e}", exc_info=True)
        flash('Something went wrong creating the work', 'error')

    return redirect(url_for('admin_works', slug=slug))

@app.route('/apartments/<slug>/admin/works/<int:work_id>/status', methods=['POST'])
@admin_login_required
def update_work_status(slug, work_id):
    """Admin updates work status — sets actual cost on completion"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_works', slug=slug))

    status      = request.form.get('status', '').strip()
    actual_cost = request.form.get('actual_cost', '').strip()

    if status not in ('planned', 'ongoing', 'completed'):
        flash('Invalid status', 'error')
        return redirect(url_for('admin_works', slug=slug))

    try:
        actual_cost = float(actual_cost) if actual_cost else None
    except ValueError:
        flash('Invalid actual cost', 'error')
        return redirect(url_for('admin_works', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE works
                    SET status = %s,
                        actual_cost = CASE WHEN %s = 'completed' THEN %s ELSE actual_cost END,
                        updated_at = NOW()
                    WHERE id = %s AND apartment_id = %s
                    RETURNING id
                """, (status, status, actual_cost, work_id, apartment['id']))

                if not cur.fetchone():
                    flash('Work not found', 'error')
                    return redirect(url_for('admin_works', slug=slug))

        flash('Work status updated', 'success')

    except Exception as e:
        logger.error(f"Error updating work status: {e}", exc_info=True)
        flash('Something went wrong', 'error')

    return redirect(url_for('admin_works', slug=slug))

@app.route('/apartments/<slug>/admin/works/<int:work_id>/checkpoints/add', methods=['POST'])
@admin_login_required
def add_checkpoint(slug, work_id):
    """Admin adds a checkpoint to a work (AJAX only)"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        return jsonify({'ok': False, 'error': 'Apartment not found'}), 404

    title = request.form.get('title', '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'Checkpoint title is required'}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify work belongs to this apartment
                cur.execute("""
                    SELECT id FROM works
                    WHERE id = %s AND apartment_id = %s
                """, (work_id, apartment['id']))

                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': 'Work not found'}), 404

                cur.execute("""
                    INSERT INTO work_checkpoints (work_id, title)
                    VALUES (%s, %s)
                    RETURNING id
                """, (work_id, title))
                
                cp_id = cur.fetchone()[0]
                conn.commit()

        return jsonify({
            'ok': True,
            'cp_id': cp_id,
            'title': title,
            'is_done': False,
            'done_at': None,
            'photo_url': None
        })

    except Exception as e:
        logger.error(f"Error adding checkpoint: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': 'Something went wrong'}), 500

@app.route('/apartments/<slug>/admin/works/<int:work_id>/checkpoints/<int:cp_id>/toggle', methods=['POST'])
@admin_login_required
def toggle_checkpoint(slug, work_id, cp_id):
    """Admin ticks/unticks a checkpoint, optionally uploading a photo"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_works', slug=slug))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                # Get current state
                cur.execute("""
                    SELECT wc.is_done FROM work_checkpoints wc
                    JOIN works w ON w.id = wc.work_id
                    WHERE wc.id = %s AND wc.work_id = %s AND w.apartment_id = %s
                """, (cp_id, work_id, apartment['id']))
                row = cur.fetchone()

                if not row:
                    flash('Checkpoint not found', 'error')
                    return redirect(url_for('admin_works', slug=slug))

                new_state = not row[0]

                # Handle optional photo upload (only when marking done)
                photo_url = None
                if new_state:
                    photo_file = request.files.get('photo')
                    if photo_file and photo_file.filename:
                        try:
                            upload_result = cloudinary.uploader.upload(
                                photo_file,
                                folder=f'apartments/{slug}/works/{work_id}'
                            )
                            photo_url = upload_result.get('secure_url')
                        except Exception as e:
                            logger.error(f"Checkpoint photo upload failed: {e}", exc_info=True)
                            flash('Photo upload failed', 'error')
                            return redirect(url_for('admin_works', slug=slug))

                cur.execute("""
                    UPDATE work_checkpoints
                    SET is_done  = %s,
                        done_at  = CASE WHEN %s THEN NOW() ELSE NULL END,
                        photo_url = CASE WHEN %s THEN %s ELSE photo_url END
                    WHERE id = %s
                """, (new_state, new_state, new_state, photo_url, cp_id))

                # Bump work updated_at
                cur.execute("""
                    UPDATE works SET updated_at = NOW() WHERE id = %s
                """, (work_id,))

                # Compute new progress while connection is still open
                cur.execute("""
                    SELECT COUNT(*) FROM work_checkpoints WHERE work_id = %s
                """, (work_id,))
                total = cur.fetchone()[0] or 0
                cur.execute("""
                    SELECT COUNT(*) FROM work_checkpoints WHERE work_id = %s AND is_done = TRUE
                """, (work_id,))
                done_count = cur.fetchone()[0] or 0

        progress = int((done_count / total) * 100) if total else 0

        # If AJAX request, return JSON for in-place update
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            done_at_str = datetime.now().strftime('%d %b %Y') if new_state else None
            return jsonify({
                'ok': True,
                'cp_id': cp_id,
                'new_state': bool(new_state),
                'done_at': done_at_str,
                'done': done_count,
                'total': total,
                'progress': progress
            })

        flash('Checkpoint updated', 'success')
        return redirect(url_for('admin_works', slug=slug))
    
    except Exception as e:
        logger.error(f"Error toggling checkpoint: {e}", exc_info=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': 'Internal error'}), 500
        flash('Something went wrong', 'error')
        return redirect(url_for('admin_works', slug=slug))

@app.route('/apartments/<slug>/admin/payments')
@admin_login_required
def admin_payments(slug):
    """Admin Payments - comprehensive payment management"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                
                # Payments 
                cur.execute("""
                    SELECT id, title, description, amount, frequency, distribution, due_date, is_active, created_at
                    FROM payments
                    WHERE apartment_id = %s
                    ORDER BY created_at DESC
                """, (apartment['id'],))
                rows = cur.fetchall()
                payments = [
                    {
                        'id': row[0],
                        'title': row[1],
                        'description': row[2],
                        'amount': float(row[3]),
                        'frequency': row[4],
                        'distribution': row[5],
                        'due_date': row[6].strftime('%Y-%m-%d') if row[6] else None,
                        'is_active': bool(row[7]),
                        'created_at': row[8].strftime('%Y-%m-%d') if row[8] else None
                    } for row in rows
                ]

                # All bills with resident details
                cur.execute("""
                    SELECT b.id, b.title, b.amount, b.due_date, b.status, b.paid_at, b.confirmed, b.proof_url, u.name, u.flat, b.payment_id
                    FROM bills b
                    JOIN users u ON b.user_id = u.id
                    WHERE b.apartment_id = %s
                    ORDER BY b.created_at DESC
                """, (apartment['id'],))
                rows = cur.fetchall()
                bills = [
                    {
                        'id': row[0],
                        'title': row[1],
                        'amount': float(row[2]),
                        'due_date': row[3].strftime('%Y-%m-%d') if row[3] else None,
                        'status': row[4],
                        'paid_at': row[5].strftime('%Y-%m-%d') if row[5] else None,
                        'confirmed': bool(row[6]),
                        'proof_url': row[7],
                        'resident_name': row[8],
                        'flat_number': row[9],
                        'payment_id': row[10]
                    } for row in rows
                ]

                # Pending confirmations
                pending_confirmations = [b for b in bills if b['status'] == 'paid' and not b['confirmed']]

                # Summary stats
                total_due = sum(b['amount'] for b in bills if b['status'] != 'paid')
                total_collected = sum(b['amount'] for b in bills if b['status'] == 'paid')
                total_pending = sum(b['amount'] for b in bills if b['status'] == 'pending')
                total_overdue = sum(b['amount'] for b in bills if b['status'] == 'pending' and b['due_date'] and b['due_date'] < datetime.now().strftime('%Y-%m-%d'))


    except Exception as e:
        logger.error(f"Error fetching payments data: {str(e)}")
        flash('Error fetching payments data', 'error')
        payments = []
        bills = []
        pending_confirmations = []
        total_due = total_collected = total_pending = 0
        return redirect(url_for('admin_payments', slug=slug))
    
    return render_template('admin_payments.html', apartment=apartment, payments=payments, bills=bills, pending_confirmations=pending_confirmations, total_due=total_due, total_collected=total_collected, total_pending=total_pending, total_overdue=total_overdue)

@app.route('/apartments/<slug>/admin/payments/residents-list', methods=['GET'])
@admin_login_required
def get_residents_for_payments(slug):
    """Get all residents for payment creation (AJAX endpoint)"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        return jsonify({'error': 'Apartment not found'}), 404
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, flat, status
                FROM users
                WHERE apartment_id = %s AND role = 'resident'
                ORDER BY flat ASC
            """, (apartment['id'],))
            residents_data = cur.fetchall()
    
    residents = []
    for row in residents_data:
        residents.append({
            'id': str(row[0]),
            'full_name': row[1],
            'flat': row[2],
            'status': row[3].lower() if row[3] else 'active'
        })
    
    return jsonify({'residents': residents})

@app.route('/apartments/<slug>/admin/payments/create', methods=['POST'])
@admin_login_required
def create_payment(slug):    
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('apartment_home', slug=slug))
    
    # Get form data
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    amount_str = request.form.get('amount', '').strip()
    frequency = request.form.get('frequency', 'once').strip().lower()
    distribution = request.form.get('distribution', '').strip().lower()
    due_date_str = request.form.get('due_date', '').strip()
    selected_residents = request.form.getlist('selected_residents')  # List of resident IDs for custom distribution

    if not all ([title, amount_str, frequency, distribution, due_date_str]):
        flash('All fields are required', 'error')
        return redirect(url_for('admin_payments', slug=slug))
    
    if frequency not in ('once', 'monthly', 'quarterly', 'annual'):
        flash('Invalid frequency', 'error')
        return redirect(url_for('admin_payments', slug=slug))

    if distribution not in ('all', 'specific'):
        flash('Invalid distribution', 'error')
        return redirect(url_for('admin_payments', slug=slug))
    
    if distribution == 'specific' and not selected_residents:
        flash('Select at least one resident for specific distribution', 'error')
        return redirect(url_for('admin_payments', slug=slug))
    
    try:
        amount   = float(amount_str)
        due_date = date.fromisoformat(due_date_str)
    except ValueError:
        flash('Invalid amount or date format', 'error')
        return redirect(url_for('admin_payments', slug=slug))
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 1. Create payment entry
                cur.execute("""
                    INSERT INTO payments (apartment_id, title, description, amount, frequency, distribution, due_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (apartment['id'], title, description, amount, frequency, distribution, due_date))
                payment_id = cur.fetchone()[0]

                # 2. Determine residents to bill
                if distribution == 'all':
                    cur.execute("""
                        SELECT id FROM users
                        WHERE apartment_id = %s AND role = 'resident'
                    """, (apartment['id'],))
                else:
                    # Validate selected residents belong to this apartment
                    cur.execute("""
                        SELECT id FROM users
                        WHERE apartment_id = %s AND role = 'resident' AND id = ANY(%s)
                    """, (apartment['id'], selected_residents))
                
                resident_ids = cur.fetchall()

                if not resident_ids:
                    flash('No valid residents found for billing', 'error')
                    return redirect(url_for('admin_payments', slug=slug))
                
                # 3. Generate bills for each resident
                cur.executemany("""
                    INSERT INTO bills (payment_id, apartment_id, user_id, title, amount, due_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, [(payment_id, apartment['id'], resident_id[0], title, amount / len(resident_ids), due_date) for resident_id in resident_ids])
            conn.commit()

        flash(f'Payment "{title}" created successfully and bills generated for {len(resident_ids)} residents!', 'success')
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        flash(f'Error creating payment: {str(e)}', 'error')

    return redirect(url_for('admin_payments', slug=slug))

@app.route('/apartments/<slug>/admin/bills/<int:bill_id>/confirm', methods=['POST'])
@admin_login_required
def confirm_bill(slug, bill_id):
    """Admin confirms a resident's payment"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('admin_payments', slug=slug))
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Update bill status to paid
                cur.execute("""
                    UPDATE bills
                    SET confirmed = TRUE, status = 'paid'
                    WHERE id = %s AND apartment_id = %s
                    RETURNING id
                """, (bill_id, apartment['id']))

                if not cur.fetchone():
                    flash('Bill not found', 'error')
                    return redirect(url_for('admin_payments', slug=slug))
            conn.commit()

        flash('Bill confirmed as paid!', 'success')

    except Exception as e:
        logger.error(f"Error confirming bill: {str(e)}")
        flash(f'Error confirming bill: {str(e)}', 'error')

    return redirect(url_for('admin_payments', slug=slug))

# ============================================================================
# ADMIN ANALYTICS
# ============================================================================

@app.route('/apartments/<slug>/admin/analytics')
@admin_login_required
def admin_analytics(slug):
    """Admin analytics – rich data insights for apartment management"""
    apartment = get_apartment_by_slug(slug)
    if not apartment:
        flash('Apartment not found', 'error')
        return redirect(url_for('index'))

    apt_id = apartment['id']

    # Build a reliable list of the last 6 calendar months (oldest → newest)
    # Format matches PostgreSQL  TO_CHAR(date, 'Mon YY')
    today = date.today()
    months_list = []
    for i in range(5, -1, -1):
        year  = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year  -= 1
        months_list.append(date(year, month, 1).strftime('%b %y'))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                # ── RESIDENT OVERVIEW ────────────────────────────────────
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE role = 'resident')                     AS total,
                        COUNT(*) FILTER (WHERE role = 'resident' AND status = 'active') AS active,
                        COUNT(*) FILTER (WHERE role = 'resident' AND type  = 'owner')  AS owners,
                        COUNT(*) FILTER (WHERE role = 'resident' AND type  = 'tenant') AS tenants,
                        COUNT(*) FILTER (WHERE role = 'resident' AND status = 'invited') AS invited
                    FROM users WHERE apartment_id = %s
                """, (apt_id,))
                r = cur.fetchone()
                residents_stats = {
                    'total': r[0] or 0, 'active': r[1] or 0,
                    'owners': r[2] or 0, 'tenants': r[3] or 0, 'invited': r[4] or 0
                }

                # ── BILLS / COLLECTIONS ───────────────────────────────────
                cur.execute("""
                    SELECT
                        COUNT(*)                                                          AS total,
                        COUNT(*) FILTER (WHERE status = 'paid')                          AS paid,
                        COUNT(*) FILTER (WHERE status = 'pending')                       AS pending,
                        COALESCE(SUM(amount) FILTER (WHERE status = 'paid'),  0)         AS collected,
                        COALESCE(SUM(amount) FILTER (WHERE status = 'pending'), 0)       AS pending_amt,
                        COALESCE(SUM(amount) FILTER (WHERE status = 'pending'
                                                    AND due_date < CURRENT_DATE), 0)     AS overdue_amt
                    FROM bills WHERE apartment_id = %s
                """, (apt_id,))
                b = cur.fetchone()
                bill_stats = {
                    'total': b[0] or 0, 'paid': b[1] or 0, 'pending': b[2] or 0,
                    'collected': float(b[3] or 0), 'pending_amount': float(b[4] or 0),
                    'overdue_amount': float(b[5] or 0),
                    'collection_rate': round((b[1] / b[0] * 100) if b[0] else 0, 1)
                }

                # ── MONTHLY INCOME (last 6 months) ────────────────────────
                cur.execute("""
                    SELECT TO_CHAR(paid_at, 'Mon YY') AS lbl,
                           COALESCE(SUM(amount), 0)   AS total
                    FROM bills
                    WHERE apartment_id = %s AND status = 'paid' AND paid_at IS NOT NULL
                      AND paid_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                    GROUP BY lbl
                """, (apt_id,))
                income_map = {row[0]: float(row[1]) for row in cur.fetchall()}

                # ── MONTHLY EXPENSES (last 6 months) ─────────────────────
                cur.execute("""
                    SELECT TO_CHAR(date, 'Mon YY') AS lbl,
                           COALESCE(SUM(amount), 0) AS total
                    FROM expenses
                    WHERE apartment_id = %s
                      AND date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                    GROUP BY lbl
                """, (apt_id,))
                expense_map = {row[0]: float(row[1]) for row in cur.fetchall()}

                cashflow_income   = [income_map.get(m, 0)  for m in months_list]
                cashflow_expenses = [expense_map.get(m, 0) for m in months_list]
                cashflow_net      = [i - e for i, e in zip(cashflow_income, cashflow_expenses)]

                # ── EXPENSE BY CATEGORY ───────────────────────────────────
                cur.execute("""
                    SELECT COALESCE(category, 'other') AS cat,
                           COALESCE(SUM(amount), 0)    AS total
                    FROM expenses WHERE apartment_id = %s
                    GROUP BY cat ORDER BY total DESC
                """, (apt_id,))
                expense_categories = [{'label': row[0].title(), 'amount': float(row[1])}
                                      for row in cur.fetchall()]

                # ── COMPLAINTS ────────────────────────────────────────────
                cur.execute("""
                    SELECT
                        COUNT(*)                                                    AS total,
                        COUNT(*) FILTER (WHERE status = 'open')                    AS open,
                        COUNT(*) FILTER (WHERE status = 'in_progress')             AS in_progress,
                        COUNT(*) FILTER (WHERE status = 'resolved')                AS resolved,
                        ROUND(AVG(
                            EXTRACT(EPOCH FROM (updated_at - created_at)) / 86400
                        ) FILTER (WHERE status = 'resolved' AND updated_at IS NOT NULL), 1)
                            AS avg_resolution_days
                    FROM complaints WHERE apartment_id = %s
                """, (apt_id,))
                c = cur.fetchone()
                complaint_stats = {
                    'total': c[0] or 0, 'open': c[1] or 0,
                    'in_progress': c[2] or 0, 'resolved': c[3] or 0,
                    'avg_resolution_days': float(c[4] or 0)
                }

                # ── MONTHLY COMPLAINT TREND ───────────────────────────────
                cur.execute("""
                    SELECT TO_CHAR(created_at, 'Mon YY') AS lbl, COUNT(*) AS cnt
                    FROM complaints WHERE apartment_id = %s
                      AND created_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                    GROUP BY lbl
                """, (apt_id,))
                complaint_map     = {row[0]: int(row[1]) for row in cur.fetchall()}
                complaint_monthly = [complaint_map.get(m, 0) for m in months_list]

                # ── WORKS ─────────────────────────────────────────────────
                cur.execute("""
                    SELECT
                        COUNT(*)                                             AS total,
                        COUNT(*) FILTER (WHERE status = 'planned')           AS planned,
                        COUNT(*) FILTER (WHERE status = 'ongoing')           AS ongoing,
                        COUNT(*) FILTER (WHERE status = 'completed')         AS completed,
                        COALESCE(SUM(estimated_cost) FILTER (WHERE status = 'completed'), 0) AS est_done,
                        COALESCE(SUM(actual_cost)    FILTER (WHERE status = 'completed'), 0) AS act_done
                    FROM works WHERE apartment_id = %s
                """, (apt_id,))
                w = cur.fetchone()
                est_done = float(w[4] or 0)
                act_done = float(w[5] or 0)
                works_stats = {
                    'total': w[0] or 0, 'planned': w[1] or 0,
                    'ongoing': w[2] or 0, 'completed': w[3] or 0,
                    'budget_variance_pct': round(
                        ((act_done - est_done) / est_done * 100) if est_done > 0 else 0, 1)
                }

                # Individual works for budget comparison chart (max 8)
                cur.execute("""
                    SELECT title, estimated_cost, actual_cost, status
                    FROM works WHERE apartment_id = %s AND estimated_cost IS NOT NULL
                    ORDER BY created_at DESC LIMIT 8
                """, (apt_id,))
                works_detail = [
                    {
                        'title': (r[0][:18] + '…') if len(r[0]) > 18 else r[0],
                        'estimated': float(r[1] or 0),
                        'actual': float(r[2] or 0),
                        'status': r[3]
                    }
                    for r in cur.fetchall()
                ]

                # ── RESIDENT PAYMENT SCORES ───────────────────────────────
                cur.execute("""
                    SELECT u.name, u.flat,
                           COUNT(b.id)                                                   AS total,
                           COUNT(b.id) FILTER (WHERE b.status = 'paid')                  AS paid,
                           COUNT(b.id) FILTER (WHERE b.status = 'pending'
                                               AND b.due_date < CURRENT_DATE)            AS overdue
                    FROM users u
                    LEFT JOIN bills b ON b.user_id = u.id AND b.apartment_id = %s
                    WHERE u.apartment_id = %s AND u.role = 'resident' AND u.status = 'active'
                    GROUP BY u.id, u.name, u.flat
                    ORDER BY
                        CASE WHEN COUNT(b.id) > 0
                             THEN COUNT(b.id) FILTER (WHERE b.status = 'paid')::float / COUNT(b.id)
                             ELSE 1 END DESC,
                        COUNT(b.id) FILTER (WHERE b.status = 'pending'
                                            AND b.due_date < CURRENT_DATE) ASC
                """, (apt_id, apt_id))
                resident_payment_scores = []
                for r in cur.fetchall():
                    total = r[2] or 0
                    paid  = r[3] or 0
                    score = round((paid / total * 100) if total > 0 else 100)
                    resident_payment_scores.append({
                        'name': r[0] or 'Unknown',
                        'flat': r[1] or '–',
                        'total': total, 'paid': paid,
                        'overdue': r[4] or 0,
                        'score': score
                    })

    except Exception as e:
        logger.error(f"Error loading analytics: {e}", exc_info=True)
        flash('Error loading analytics data', 'error')
        return redirect(url_for('admin_analytics', slug=slug))

    # ── COMPOSITE HEALTH SCORE (0–100) ────────────────────────────────────
    col_score  = bill_stats['collection_rate'] * 0.40
    res_rate   = (complaint_stats['resolved'] / complaint_stats['total'] * 100) \
                 if complaint_stats['total'] > 0 else 100
    comp_score = res_rate * 0.30
    work_rate  = (works_stats['completed'] / works_stats['total'] * 100) \
                 if works_stats['total'] > 0 else 100
    work_score = work_rate * 0.20
    occ_rate   = (residents_stats['active'] / residents_stats['total'] * 100) \
                 if residents_stats['total'] > 0 else 100
    occ_score  = occ_rate * 0.10
    health_score = round(col_score + comp_score + work_score + occ_score)

    username = session.get(f'apartment_{slug}_user')

    return render_template(
        'admin_analytics.html',
        apartment=apartment,
        username=username,
        months_list=months_list,
        residents_stats=residents_stats,
        bill_stats=bill_stats,
        cashflow_income=cashflow_income,
        cashflow_expenses=cashflow_expenses,
        cashflow_net=cashflow_net,
        expense_categories=expense_categories,
        complaint_stats=complaint_stats,
        complaint_monthly=complaint_monthly,
        works_stats=works_stats,
        works_detail=works_detail,
        resident_payment_scores=resident_payment_scores,
        health_score=health_score
    )

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(400)
def bad_request(e):
    return render_template('404.html', message='Bad request. Please check your input and try again.'), 400

@app.errorhandler(403)
def forbidden(e):
    return render_template('404.html', message="You don't have permission to access this page."), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', message='The page you are looking for does not exist.'), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return render_template('404.html', message='This action is not allowed.'), 405

@app.errorhandler(408)
def request_timeout(e):
    return render_template('500.html', message='The request timed out. Please try again.'), 408

@app.errorhandler(429)
def too_many_requests(e):
    return render_template('500.html', message='Too many requests. Please slow down and try again.'), 429

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500 Internal Server Error: {e}", exc_info=True)
    return render_template('500.html', message='Something went wrong on our end. Please try again later.'), 500

@app.errorhandler(502)
def bad_gateway(e):
    return render_template('500.html', message='Bad gateway. Please try again later.'), 502

@app.errorhandler(503)
def service_unavailable(e):
    return render_template('500.html', message='Service temporarily unavailable. Please try again later.'), 503

# Catch-all for any other HTTP exceptions
from werkzeug.exceptions import HTTPException

@app.errorhandler(HTTPException)
def handle_http_exception(e):
    logger.error(f"HTTP {e.code} error: {e.description}")
    if e.code and e.code < 500:
        return render_template('404.html', message=e.description or 'An error occurred.'), e.code
    return render_template('500.html', message=e.description or 'A server error occurred.'), e.code or 500

# Catch-all for unexpected Python exceptions
@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    return render_template('500.html', message='An unexpected error occurred. Please try again later.'), 500


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')