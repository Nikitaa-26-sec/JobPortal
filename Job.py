from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)
from database import get_db

jobs_blueprint = Blueprint('jobs', __name__)


# ── Browse / Search jobs 
@jobs_blueprint.route('/jobs')
def browse():
    q        = request.args.get('q', '').strip()
    jtype    = request.args.get('type', '')
    remote   = request.args.get('remote', '')
    location = request.args.get('location', '').strip()
    page     = max(1, request.args.get('page', 1, type=int))
    per_page = 10

    
    filters = ["j.status = 'active'"]
    params  = []

    if q:
        filters.append(
            "(j.title LIKE ? OR j.description LIKE ? OR j.skills_needed LIKE ?)"
        )
        params += [f'%{q}%', f'%{q}%', f'%{q}%']

    if jtype:
        filters.append("j.job_type = ?")
        params.append(jtype)

    if remote == '1':
        filters.append("j.remote = 1")

    if location:
        filters.append("j.location LIKE ?")
        params.append(f'%{location}%')

    where = " AND ".join(filters)

    conn = get_db()
    total = conn.execute(
        f"SELECT COUNT(*) FROM jobs j WHERE {where}", params
    ).fetchone()[0]

    jobs = conn.execute(f"""
        SELECT j.*, c.name AS company_name, c.industry, c.location AS co_loc
        FROM jobs j
        JOIN companies c ON j.company_id = c.id
        WHERE {where}
        ORDER BY j.posted_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page]).fetchall()

    
    applied_ids = set()
    saved_ids   = set()
    if session.get('user_role') == 'seeker':
        uid = session['user_id']
        applied_ids = {
            r['job_id'] for r in conn.execute(
                "SELECT job_id FROM applications WHERE seeker_id=?", (uid,)
            ).fetchall()
        }
        saved_ids = {
            r['job_id'] for r in conn.execute(
                "SELECT job_id FROM saved_jobs WHERE seeker_id=?", (uid,)
            ).fetchall()
        }

    conn.close()

    pages = (total + per_page - 1) // per_page
    return render_template('jobs.html',
                           jobs=jobs, total=total, page=page, pages=pages,
                           q=q, jtype=jtype, remote=remote, location=location,
                           applied_ids=applied_ids, saved_ids=saved_ids)


# ── Single job detail
@jobs_blueprint.route('/jobs/<int:job_id>')
def job_detail(job_id):
    conn = get_db()
    conn.execute("UPDATE jobs SET views = views + 1 WHERE id=?", (job_id,))
    conn.commit()

    job = conn.execute("""
        SELECT j.*, c.name AS company_name, c.industry, c.size,
               c.website, c.description AS company_desc,
               c.location AS co_loc, c.founded_year
        FROM jobs j JOIN companies c ON j.company_id = c.id
        WHERE j.id = ?
    """, (job_id,)).fetchone()

    if not job:
        conn.close()
        flash('Job not found.', 'error')
        return redirect(url_for('jobs.browse'))

    applied = False
    saved   = False
    if session.get('user_role') == 'seeker':
        uid     = session['user_id']
        applied = bool(conn.execute(
            "SELECT 1 FROM applications WHERE job_id=? AND seeker_id=?",
            (job_id, uid)
        ).fetchone())
        saved = bool(conn.execute(
            "SELECT 1 FROM saved_jobs WHERE job_id=? AND seeker_id=?",
            (job_id, uid)
        ).fetchone())

    conn.close()
    return render_template('job_detail.html',
                           job=job, applied=applied, saved=saved)


# ── Post a new job (recruiter only) 
@jobs_blueprint.route('/jobs/post', methods=['GET', 'POST'])
def post_job():
    if session.get('user_role') != 'recruiter':
        flash('Only recruiters can post jobs.', 'error')
        return redirect(url_for('login.login'))

    if request.method == 'POST':
        title   = request.form.get('title', '').strip()
        desc    = request.form.get('description', '').strip()
        loc     = request.form.get('location', '').strip()
        jtype   = request.form.get('job_type', 'full-time')
        remote  = int(request.form.get('remote', 0))
        smin    = request.form.get('salary_min') or None
        smax    = request.form.get('salary_max') or None
        exp     = request.form.get('experience_req', 0)
        skills  = request.form.get('skills_needed', '').strip()
        reqs    = request.form.get('requirements', '').strip()

        if not all([title, desc, loc]):
            flash('Title, description and location are required.', 'error')
            return render_template('post_job.html')

        conn = get_db()
        company = conn.execute(
            "SELECT id FROM companies WHERE recruiter_id=?", (session['user_id'],)
        ).fetchone()

        if not company:
            conn.close()
            flash('Please complete your company profile first.', 'error')
            return redirect(url_for('recruiter.register_recruiter'))

        conn.execute("""
            INSERT INTO jobs
            (company_id, title, description, requirements, skills_needed,
             location, remote, job_type, salary_min, salary_max, experience_req)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (company['id'], title, desc, reqs, skills, loc, remote, jtype,
              int(smin) if smin else None,
              int(smax) if smax else None,
              int(exp) if exp else 0))
        conn.commit()
        conn.close()

        flash('Job posted successfully! ', 'success')
        return redirect(url_for('recruiter.manage_jobs'))

    return render_template('post_job.html')


# ── Save / unsave a job 
@jobs_blueprint.route('/jobs/<int:job_id>/save', methods=['POST'])
def toggle_save(job_id):
    if session.get('user_role') != 'seeker':
        flash('Please log in as a job seeker.', 'error')
        return redirect(url_for('login.login'))

    uid = session['user_id']
    conn = get_db()
    exists = conn.execute(
        "SELECT 1 FROM saved_jobs WHERE seeker_id=? AND job_id=?", (uid, job_id)
    ).fetchone()

    if exists:
        conn.execute(
            "DELETE FROM saved_jobs WHERE seeker_id=? AND job_id=?", (uid, job_id)
        )
        flash('Job removed from saved.', 'info')
    else:
        conn.execute(
            "INSERT INTO saved_jobs (seeker_id, job_id) VALUES (?,?)", (uid, job_id)
        )
        flash('Job saved! ', 'success')

    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('jobs.browse'))



@jobs_blueprint.route('/jobs/saved')
def saved_jobs():
    if session.get('user_role') != 'seeker':
        return redirect(url_for('login.login'))

    conn = get_db()
    jobs = conn.execute("""
        SELECT j.*, c.name AS company_name, sj.saved_at
        FROM saved_jobs sj
        JOIN jobs      j ON sj.job_id      = j.id
        JOIN companies c ON j.company_id   = c.id
        WHERE sj.seeker_id = ?
        ORDER BY sj.saved_at DESC
    """, (session['user_id'],)).fetchall()
    conn.close()

    return render_template('saved_jobs.html', jobs=jobs)
