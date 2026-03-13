import hashlib
from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)
from database import get_db

login_blueprint = Blueprint('login', __name__)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


@login_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, hash_password(password))
        ).fetchone()

        if user:
            conn.execute(
                "UPDATE users SET last_login = datetime('now') WHERE id = ?",
                (user['id'],)
            )
            conn.commit()
            conn.close()

            session['user_id']   = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']

            flash(f"Welcome back, {user['name'].split()[0]}!", 'success')

            if user['role'] == 'recruiter':
                return redirect(url_for('recruiter.dashboard'))
            else:
                return redirect(url_for('jobs.browse'))
        else:
            conn.close()
            flash('Invalid email or password.', 'error')

    return render_template('login.html')


@login_blueprint.route('/logout')
def logout():
    session.clear()
    flash('You have been signed out.', 'info')
    return redirect(url_for('home'))
