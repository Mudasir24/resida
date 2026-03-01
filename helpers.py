import os
from functools import wraps
from flask import session, redirect, url_for, flash
import string
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg
import logging

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URI = os.environ.get('DATABASE_URI')

SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')

# Helper function to generate unique invite code
def generate_invite_code():
    """Generate a secure invite code with only alphanumeric characters (no special chars)"""
    # Generate 8-character code with uppercase letters and digits only
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(8))


# Decorator to check if user is logged in for apartment (residents and admins)
def apartment_login_required(f):
    @wraps(f)
    def decorated_function(slug, *args, **kwargs):
        if f'apartment_{slug}_logged_in' not in session:
            return redirect(url_for('apartment_home', slug=slug))
        return f(slug, *args, **kwargs)
    return decorated_function


# Decorator to check if user is logged in as admin
def admin_login_required(f):
    @wraps(f)
    def decorated_function(slug, *args, **kwargs):
        if f'apartment_{slug}_logged_in' not in session:
            return redirect(url_for('apartment_home', slug=slug))
        if session.get(f'apartment_{slug}_role') != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('apartment_home', slug=slug))
        return f(slug, *args, **kwargs)
    return decorated_function


# Database connection function
def get_conn():
    """Create database connection"""
    return psycopg.connect(DATABASE_URI, autocommit=False)


def get_all_apartments():
    """
    Fetch all apartments for directory page
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, slug, photo
                FROM apartments
                ORDER BY name
            """)
            rows = cur.fetchall()

    apartments = {}
    for row in rows:
        apt_id, name, slug, photo = row
        apartments[slug] = {
            'id': apt_id,
            'name': name,
            'slug': slug,
            'photo': photo
        }
    return apartments


def get_apartment_by_slug(slug):
    """Get apartment by slug with basic info"""
    try:
        slug = str(slug)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(""" SELECT id, name, slug, photo FROM apartments WHERE slug = %s """, (slug,))
                row = cur.fetchone()
    except Exception as e:
        logger.error(f"Error fetching apartment by slug '{slug}': {str(e)}", exc_info=True)
        return None

    if row:
        apt_id, name, slug, photo = row
        return {
            'id': apt_id,
            'name': name,
            'slug': slug,
            'photo': photo
        }
    return None


def get_apartment_full_by_slug(slug):
    """Get apartment by slug with full details"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, slug, admin_email, phone, address, city, photo,
                    (SELECT COUNT(*) FROM users WHERE apartment_id = apartments.id AND role = 'resident') AS resident_count
                FROM apartments
                WHERE slug = %s
            """, (slug,))
            row = cur.fetchone()
    
    if row:
        apt_id, name, slug, admin_email, phone, address, city, photo, resident_count = row
        return {
            'id': apt_id,
            'name': name,
            'slug': slug,
            'admin_email': admin_email,
            'resident_count': resident_count,
            'phone': phone,
            'address': address,
            'city': city,
            'photo': photo
        }
    return None


def send_invite_email(to_email, apartment_name, invite_code, slug):
    """Send invitation email to new user"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = f"Invitation to register at {apartment_name}"

    body = f"""
    Dear Resident,
    You have been invited to register at {apartment_name}.
    
    Click the link below to complete your registration:
    {url_for('apartment_join', slug=slug, code=invite_code, _external=True) if slug else ""}
    
    Your invite code: {invite_code}
    This code will expire in 7 days.

    Best regards,
    {apartment_name} Management
    """

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
    except Exception as e:
        logger.error(f"Failed to send invite email to {to_email}: {str(e)}")
