import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "job_portal.db")


def get_db():
    """Return a WAL-mode connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Create all tables and indexes if they don't exist."""
    conn = get_db()
    c = conn.cursor()

    # users 
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            role        TEXT    NOT NULL CHECK(role IN ('seeker','recruiter')),
            created_at  TEXT    DEFAULT (datetime('now')),
            last_login  TEXT
        )
    """)

    # seeker_profiles 
    c.execute("""
        CREATE TABLE IF NOT EXISTS seeker_profiles (
            user_id     INTEGER PRIMARY KEY
                        REFERENCES users(id) ON DELETE CASCADE,
            headline    TEXT,
            bio         TEXT,
            skills      TEXT,          -- comma-separated
            location    TEXT,
            resume_url  TEXT,
            exp_years   INTEGER DEFAULT 0,
            salary_min  INTEGER,
            open_to     TEXT    DEFAULT 'full-time'
        )
    """)

    #  companies 
    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            recruiter_id INTEGER NOT NULL
                         REFERENCES users(id) ON DELETE CASCADE,
            name         TEXT    NOT NULL,
            industry     TEXT,
            size         TEXT,
            website      TEXT,
            description  TEXT,
            location     TEXT,
            founded_year INTEGER,
            logo_url     TEXT
        )
    """)

    #  jobs 
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id     INTEGER NOT NULL
                           REFERENCES companies(id) ON DELETE CASCADE,
            title          TEXT    NOT NULL,
            description    TEXT    NOT NULL,
            requirements   TEXT,          -- newline-separated
            skills_needed  TEXT,          -- comma-separated
            location       TEXT    NOT NULL,
            remote         INTEGER DEFAULT 0,
            job_type       TEXT    DEFAULT 'full-time'
                           CHECK(job_type IN
                               ('full-time','part-time','contract',
                                'internship','freelance')),
            salary_min     INTEGER,
            salary_max     INTEGER,
            experience_req INTEGER DEFAULT 0,
            status         TEXT    DEFAULT 'active'
                           CHECK(status IN ('active','paused','closed')),
            posted_at      TEXT    DEFAULT (datetime('now')),
            views          INTEGER DEFAULT 0
        )
    """)

    # applications 
    c.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id        INTEGER NOT NULL
                          REFERENCES jobs(id) ON DELETE CASCADE,
            seeker_id     INTEGER NOT NULL
                          REFERENCES users(id) ON DELETE CASCADE,
            cover_letter  TEXT,
            status        TEXT DEFAULT 'pending'
                          CHECK(status IN
                              ('pending','reviewed','shortlisted',
                               'rejected','hired')),
            applied_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(job_id, seeker_id)
        )
    """)

    # saved_jobs
    c.execute("""
        CREATE TABLE IF NOT EXISTS saved_jobs (
            seeker_id   INTEGER REFERENCES users(id) ON DELETE CASCADE,
            job_id      INTEGER REFERENCES jobs(id)  ON DELETE CASCADE,
            saved_at    TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (seeker_id, job_id)
        )
    """)

    # notifications 
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            message    TEXT    NOT NULL,
            type       TEXT,
            read       INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    # INDEXES 
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_jobs_company  ON jobs(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_type     ON jobs(job_type)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_remote   ON jobs(remote)",
        "CREATE INDEX IF NOT EXISTS idx_apps_job      ON applications(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_apps_seeker   ON applications(seeker_id)",
        "CREATE INDEX IF NOT EXISTS idx_apps_status   ON applications(status)",
        "CREATE INDEX IF NOT EXISTS idx_notif_user    ON notifications(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_saved_seeker  ON saved_jobs(seeker_id)",
    ]
    for sql in indexes:
        c.execute(sql)

    conn.commit()
    conn.close()
    _seed_demo_data()


def _seed_demo_data():
    """Insert demo data only on first run."""
    import hashlib, json

    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    def hp(pw):
        return hashlib.sha256(pw.encode()).hexdigest()

    # Demo recruiters
    recruiters = [
        ("Alice Chen",  "alice@techcorp.com",  "TechCorp Inc.",    "Technology", "501-1000", "San Francisco, CA", 2010,
         "Building the future of cloud infrastructure."),
        ("Bob Patel",   "bob@designhub.com",   "DesignHub Agency", "Design",     "11-50",    "New York, NY",      2016,
         "Award-winning product design studio."),
        ("Carol Smith", "carol@finrise.com",   "FinRise Capital",  "Finance",    "51-200",   "Austin, TX",        2018,
         "Fintech company revolutionising payments."),
    ]
    company_ids = []
    for name, email, cname, ind, size, loc, yr, desc in recruiters:
        uid = conn.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
            (name, email, hp("password123"), "recruiter")
        ).lastrowid
        cid = conn.execute(
            """INSERT INTO companies
               (recruiter_id,name,industry,size,location,founded_year,description)
               VALUES (?,?,?,?,?,?,?)""",
            (uid, cname, ind, size, loc, yr, desc)
        ).lastrowid
        company_ids.append(cid)

    # Demo jobs
    jobs = [
        (company_ids[0], "Senior Backend Engineer",   "full-time",   "Bangalore, CA", 1, 140000, 180000, 5,
         "Design scalable microservices for our cloud platform.",
         "Python,Go,Kubernetes,AWS",
         "5+ years backend\nDistributed systems\nAPI design"),
        (company_ids[0], "DevOps Engineer",           "full-time",   "Remote",            1, 120000, 160000, 3,
         "Own the CI/CD pipeline and infrastructure-as-code initiatives.",
         "Terraform,Kubernetes,Docker,GitHub Actions,AWS",
         "3+ years DevOps\nIaC experience\nStrong Linux skills"),
        (company_ids[1], "Senior Product Designer",   "full-time",   "Chennai, X",      0, 110000, 140000, 4,
         "Lead end-to-end design for our enterprise SaaS products.",
         "Figma,Prototyping,User Research,Design Systems",
         "4+ years product design\nPortfolio required"),
        (company_ids[1], "UI Engineer",               "contract",    "Chennai, Y",      1,  80000, 100000, 2,
         "Implement pixel-perfect interfaces from design specs.",
         "React,TypeScript,CSS,Storybook,Figma",
         "2+ years frontend\nComponent-driven development"),
        (company_ids[2], "Data Engineer",             "full-time",   "Ahmedabad, Z",        1, 130000, 165000, 4,
         "Build real-time data pipelines processing millions of transactions.",
         "Spark,Kafka,Python,dbt,Snowflake",
         "4+ years data engineering\nStreaming systems\nSQL expert"),
        (company_ids[2], "Product Manager – Payments","full-time",   "Ahmedabad, X",        0, 125000, 155000, 5,
         "Own the payments product roadmap from discovery to launch.",
         "Roadmapping,SQL,Stakeholder Management,A/B Testing",
         "5+ years PM experience\nFintech preferred"),
    ]
    for (cid,title,jtype,loc,remote,smin,smax,exp,desc,skills,reqs) in jobs:
        conn.execute("""
            INSERT INTO jobs
            (company_id,title,job_type,location,remote,salary_min,salary_max,
             experience_req,description,skills_needed,requirements,views)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (cid,title,jtype,loc,remote,smin,smax,exp,desc,skills,reqs,
              __import__('random').randint(50,400)))

    # Demo seekers
    seekers = [
        ("Jordan ",  "dev@gmail.com",
         "Senior backend developer seeking impactful roles.",
         "Python,Go,PostgreSQL,Docker,Kubernetes", "San Francisco, CA", 6, 130000),
        ("Sam ",  "designer@gmail.com",
         "Product designer passionate about accessible interfaces.",
         "Figma,React,CSS,User Research,Prototyping", "New York, NY", 4, 100000),
        ("Morris", "data@gmail.com",
         "Data engineer who loves building robust pipelines.",
         "Python,Spark,SQL,dbt,Kafka", "Austin, TX", 5, 125000),
    ]
    for name, email, bio, skills, loc, exp, sal in seekers:
        uid = conn.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
            (name, email, hp("password123"), "seeker")
        ).lastrowid
        conn.execute("""
            INSERT INTO seeker_profiles
            (user_id,headline,bio,skills,location,exp_years,salary_min)
            VALUES (?,?,?,?,?,?,?)
        """, (uid, f"{name.split()[1]} & Developer", bio, skills, loc, exp, sal))

    conn.commit()
    conn.close()
