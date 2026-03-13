"""
applications.py — Job Application Blueprint
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)
from database import get_db

applications_blueprint = Blueprint('applications', __name__)


#Submit application
@applications_blueprint.route('/jobs/<int:job_id>/apply', methods=['GET', 'POST'])
def apply(job_id):
    if session.get('user_role') != 'seeker':
        flash('Please log in as a job seeker to apply.', 'error')
        return redirect(url_for('login.login'))

    conn = get_db()
    job = conn.execute("""
        SELECT j.*, c.name AS company_name
        FROM jobs j JOIN companies c ON j.company_id = c.id
        WHERE j.id = ?
    """, (job_id,)).fetchone()

    if not job:
        conn.close()
        flash('Job not found.', 'error')
        return redirect(url_for('jobs.browse'))

    if request.method == 'POST':
        cover_letter = request.form.get('cover_letter', '').strip()
        uid = session['user_id']

    
        exists = conn.execute(
            "SELECT 1 FROM applications WHERE job_id=? AND seeker_id=?",
            (job_id, uid)
        ).fetchone()

        if exists:
            conn.close()
            flash('You have already applied to this role.', 'info')
            return redirect(url_for('jobs.job_detail', job_id=job_id))

        conn.execute("""
            INSERT INTO applications (job_id, seeker_id, cover_letter)
            VALUES (?,?,?)
        """, (job_id, uid, cover_letter))

        # Notify recruiter
        recruiter = conn.execute("""
            SELECT c.recruiter_id FROM companies c
            JOIN jobs j ON j.company_id = c.id
            WHERE j.id = ?
        """, (job_id,)).fetchone()

        if recruiter:
            conn.execute("""
                INSERT INTO notifications (user_id, message, type)
                VALUES (?,?,?)
            """, (recruiter['recruiter_id'],
                  f"{session['user_name']} applied to '{job['title']}'",
                  'application'))

        conn.commit()
        conn.close()

        flash('Application submitted! 🎉 Good luck!', 'success')
        return redirect(url_for('applications.my_applications'))

    conn.close()
    return render_template('apply.html', job=job)


# ── Seeker: my applications
@applications_blueprint.route('/my-applications')
def my_applications():
    if session.get('user_role') != 'seeker':
        return redirect(url_for('login.login'))

    conn = get_db()
    apps = conn.execute("""
        SELECT a.id, a.status, a.applied_at, a.updated_at,
               j.title, j.location, j.job_type, j.salary_min, j.salary_max,
               c.name AS company_name
        FROM applications a
        JOIN jobs      j ON a.job_id      = j.id
        JOIN companies c ON j.company_id  = c.id
        WHERE a.seeker_id = ?
        ORDER BY a.applied_at DESC
    """, (session['user_id'],)).fetchall()

    
    stats = conn.execute("""
        SELECT
            COUNT(*)                                                AS total,
            SUM(CASE WHEN status='pending'     THEN 1 ELSE 0 END)  AS pending,
            SUM(CASE WHEN status='shortlisted' THEN 1 ELSE 0 END)  AS shortlisted,
            SUM(CASE WHEN status='hired'       THEN 1 ELSE 0 END)  AS hired,
            SUM(CASE WHEN status='rejected'    THEN 1 ELSE 0 END)  AS rejected
        FROM applications WHERE seeker_id=?
    """, (session['user_id'],)).fetchone()

    conn.close()
    return render_template('my_applications.html', apps=apps, stats=stats)


# ── Seeker: notifications 
@applications_blueprint.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('login.login'))

    conn = get_db()
    notifs = conn.execute("""
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 30
    """, (session['user_id'],)).fetchall()

    conn.execute(
        "UPDATE notifications SET read=1 WHERE user_id=?", (session['user_id'],)
    )
    conn.commit()
    conn.close()

    return render_template('notifications.html', notifs=notifs)
