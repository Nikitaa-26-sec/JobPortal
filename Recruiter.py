
import hashlib
from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)
from database import get_db

recruiter_blueprint = Blueprint('recruiter', __name__)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── Registration
@recruiter_blueprint.route('/register/recruiter', methods=['GET', 'POST'])
def register_recruiter():
    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        email       = request.form.get('email', '').strip().lower()
        password    = request.form.get('password', '')
        confirm     = request.form.get('confirm_password', '')
        company     = request.form.get('company_name', '').strip()
        industry    = request.form.get('industry', '')
        size        = request.form.get('size', '')
        location    = request.form.get('location', '')
        description = request.form.get('description', '')

        if not all([name, email, password, company]):
            flash('All required fields must be filled.', 'error')
            return render_template('register_recruiter.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register_recruiter.html')

        conn = get_db()
        try:
            uid = conn.execute(
                "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
                (name, email, hash_password(password), 'recruiter')
            ).lastrowid
            conn.execute("""
                INSERT INTO companies
                (recruiter_id,name,industry,size,location,description)
                VALUES (?,?,?,?,?,?)
            """, (uid, company, industry, size, location, description))
            conn.commit()

            session['user_id']   = uid
            session['user_name'] = name
            session['user_role'] = 'recruiter'

            flash(f"Welcome, {name.split()[0]}! Your recruiter account is ready.", 'success')
            return redirect(url_for('recruiter.dashboard'))

        except Exception as e:
            conn.rollback()
            if 'UNIQUE' in str(e):
                flash('An account with that email already exists.', 'error')
            else:
                flash('Registration failed. Please try again.', 'error')
        finally:
            conn.close()

    return render_template('register_recruiter.html')


# ── Dashboard
@recruiter_blueprint.route('/recruiter/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('user_role') != 'recruiter':
        flash('Please log in as a recruiter.', 'error')
        return redirect(url_for('login.login'))

    conn = get_db()
    company = conn.execute(
        "SELECT * FROM companies WHERE recruiter_id=?", (session['user_id'],)
    ).fetchone()

    if not company:
        conn.close()
        flash('Please complete your company profile.', 'info')
        return redirect(url_for('recruiter.register_recruiter'))

    # ── Aggregate stats
    stats = conn.execute("""
        SELECT
            COUNT(DISTINCT j.id)                                     AS total_jobs,
            SUM(CASE WHEN j.status='active'  THEN 1 ELSE 0 END)     AS active_jobs,
            COALESCE(SUM(j.views), 0)                                AS total_views,
            COUNT(DISTINCT a.id)                                     AS total_applications,
            SUM(CASE WHEN a.status='pending'     THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN a.status='shortlisted' THEN 1 ELSE 0 END) AS shortlisted,
            SUM(CASE WHEN a.status='hired'       THEN 1 ELSE 0 END) AS hired
        FROM jobs j
        LEFT JOIN applications a ON j.id = a.job_id
        WHERE j.company_id = ?
    """, (company['id'],)).fetchone()

    recent_apps = conn.execute("""
        SELECT a.id, a.status, a.applied_at,
               u.name AS seeker_name,
               j.title AS job_title
        FROM applications a
        JOIN users u ON a.seeker_id = u.id
        JOIN jobs  j ON a.job_id    = j.id
        WHERE j.company_id = ?
        ORDER BY a.applied_at DESC
        LIMIT 6
    """, (company['id'],)).fetchall()

    top_jobs = conn.execute("""
        SELECT j.id, j.title, j.views, j.status,
               COUNT(a.id) AS app_count
        FROM jobs j
        LEFT JOIN applications a ON j.id = a.job_id
        WHERE j.company_id = ?
        GROUP BY j.id
        ORDER BY app_count DESC, j.views DESC
        LIMIT 5
    """, (company['id'],)).fetchall()

    conn.close()
    return render_template('recruiter_dashboard.html',
                           company=company, stats=stats,
                           recent_apps=recent_apps, top_jobs=top_jobs)


# ── Manage jobs list 
@recruiter_blueprint.route('/recruiter/jobs')
def manage_jobs():
    if 'user_id' not in session or session.get('user_role') != 'recruiter':
        return redirect(url_for('login.login'))

    conn = get_db()
    company = conn.execute(
        "SELECT id FROM companies WHERE recruiter_id=?", (session['user_id'],)
    ).fetchone()

    jobs = conn.execute("""
        SELECT j.*, COUNT(a.id) AS app_count
        FROM jobs j
        LEFT JOIN applications a ON j.id = a.job_id
        WHERE j.company_id = ?
        GROUP BY j.id
        ORDER BY j.posted_at DESC
    """, (company['id'] if company else 0,)).fetchall()
    conn.close()

    return render_template('manage_jobs.html', jobs=jobs)


# ── Update job status 
@recruiter_blueprint.route('/recruiter/jobs/<int:job_id>/status', methods=['POST'])
def update_job_status(job_id):
    if 'user_id' not in session or session.get('user_role') != 'recruiter':
        return redirect(url_for('login.login'))

    status = request.form.get('status')
    if status in ('active', 'paused', 'closed'):
        conn = get_db()
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        conn.commit()
        conn.close()
        flash(f'Job status updated to {status}.', 'success')

    return redirect(url_for('recruiter.manage_jobs'))


# ── View all incoming applications 
@recruiter_blueprint.route('/recruiter/applications')
def view_applications():
    if 'user_id' not in session or session.get('user_role') != 'recruiter':
        return redirect(url_for('login.login'))

    status_filter = request.args.get('status', 'all')
    conn = get_db()
    company = conn.execute(
        "SELECT id FROM companies WHERE recruiter_id=?", (session['user_id'],)
    ).fetchone()

    query = """
        SELECT a.id, a.status, a.applied_at, a.cover_letter,
               u.name   AS seeker_name,
               u.email  AS seeker_email,
               sp.headline, sp.skills, sp.exp_years, sp.location,
               j.title  AS job_title, j.id AS job_id
        FROM applications a
        JOIN users u ON a.seeker_id = u.id
        JOIN jobs  j ON a.job_id    = j.id
        LEFT JOIN seeker_profiles sp ON sp.user_id = u.id
        WHERE j.company_id = ?
    """
    params = [company['id'] if company else 0]
    if status_filter != 'all':
        query += " AND a.status = ?"
        params.append(status_filter)
    query += " ORDER BY a.applied_at DESC"

    apps = conn.execute(query, params).fetchall()

    
    counts = conn.execute("""
        SELECT a.status, COUNT(*) AS cnt
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE j.company_id = ?
        GROUP BY a.status
    """, (company['id'] if company else 0,)).fetchall()
    conn.close()

    count_map = {r['status']: r['cnt'] for r in counts}
    count_map['all'] = sum(count_map.values())

    return render_template('recruiter_applications.html',
                           apps=apps, status_filter=status_filter,
                           count_map=count_map)



@recruiter_blueprint.route('/recruiter/applications/<int:app_id>/status', methods=['POST'])
def update_app_status(app_id):
    if 'user_id' not in session or session.get('user_role') != 'recruiter':
        return redirect(url_for('login.login'))

    new_status = request.form.get('status')
    valid = ('pending', 'reviewed', 'shortlisted', 'rejected', 'hired')
    if new_status not in valid:
        flash('Invalid status.', 'error')
        return redirect(url_for('recruiter.view_applications'))

    conn = get_db()
    row = conn.execute("""
        SELECT a.seeker_id, j.title
        FROM applications a JOIN jobs j ON a.job_id = j.id
        WHERE a.id = ?
    """, (app_id,)).fetchone()

    conn.execute("""
        UPDATE applications
        SET status=?, updated_at=datetime('now')
        WHERE id=?
    """, (new_status, app_id))

    if row:
        conn.execute("""
            INSERT INTO notifications (user_id, message, type)
            VALUES (?,?,?)
        """, (row['seeker_id'],
              f"Your application for '{row['title']}' is now: {new_status}",
              'status_update'))

    conn.commit()
    conn.close()
    flash(f'Application status updated to {new_status}.', 'success')
    return redirect(url_for('recruiter.view_applications'))
