"""
jobseeker_register.py — Job Seeker Registration Blueprint
Handles job seeker sign-up and profile management.
"""

import hashlib
from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)
from database import get_db

jobseeker_blueprint = Blueprint('jobseeker', __name__)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


@jobseeker_blueprint.route('/register/seeker', methods=['GET', 'POST'])
def register_seeker():
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        location = request.form.get('location', '').strip()
        skills   = request.form.get('skills', '').strip()
        exp      = request.form.get('exp_years', 0)
        headline = request.form.get('headline', '').strip()

        # ── Validation 
        if not all([name, email, password]):
            flash('Name, email and password are required.', 'error')
            return render_template('register_seeker.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register_seeker.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('register_seeker.html')

        conn = get_db()
        try:
            uid = conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                (name, email, hash_password(password), 'seeker')
            ).lastrowid

            conn.execute("""
                INSERT INTO seeker_profiles
                (user_id, headline, skills, location, exp_years)
                VALUES (?,?,?,?,?)
            """, (uid, headline, skills, location, int(exp) if exp else 0))

            conn.commit()

            # Auto-login after registration
            session['user_id']   = uid
            session['user_name'] = name
            session['user_role'] = 'seeker'

            flash(f"Welcome to Meridian, {name.split()[0]}! Start exploring roles.", 'success')
            return redirect(url_for('jobs.browse'))

        except Exception as e:
            conn.rollback()
            if 'UNIQUE' in str(e):
                flash('An account with that email already exists.', 'error')
            else:
                flash('Registration failed. Please try again.', 'error')
        finally:
            conn.close()

    return render_template('register_seeker.html')


@jobseeker_blueprint.route('/profile/seeker', methods=['GET', 'POST'])
def seeker_profile():
    if 'user_id' not in session or session.get('user_role') != 'seeker':
        flash('Please log in as a job seeker.', 'error')
        return redirect(url_for('login.login'))

    conn = get_db()

    if request.method == 'POST':
        headline  = request.form.get('headline', '')
        bio       = request.form.get('bio', '')
        skills    = request.form.get('skills', '')
        location  = request.form.get('location', '')
        exp       = request.form.get('exp_years', 0)
        salary    = request.form.get('salary_min', None)
        open_to   = request.form.get('open_to', 'full-time')

        conn.execute("""
            UPDATE seeker_profiles
            SET headline=?, bio=?, skills=?, location=?,
                exp_years=?, salary_min=?, open_to=?
            WHERE user_id=?
        """, (headline, bio, skills, location,
              int(exp) if exp else 0,
              int(salary) if salary else None,
              open_to, session['user_id']))
        conn.commit()
        flash('Profile updated!', 'success')

    profile = conn.execute(
        "SELECT * FROM seeker_profiles WHERE user_id=?",
        (session['user_id'],)
    ).fetchone()
    user = conn.execute(
        "SELECT * FROM users WHERE id=?", (session['user_id'],)
    ).fetchone()
    conn.close()

    return render_template('seeker_profile.html', profile=profile, user=user)
