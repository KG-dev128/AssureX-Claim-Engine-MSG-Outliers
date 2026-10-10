"""
run.py
Entry point for AssureX Claim Engine Flask application.
Usage:
    python run.py               (development)
    gunicorn -w 4 run:app      (production)
"""
import os
from app import create_app
from app.extensions import db

app = create_app(os.getenv('FLASK_ENV', 'development'))


@app.cli.command('init-db')
def init_db():
    """Create all database tables."""
    with app.app_context():
        db.create_all()
        print('✓ Database tables created.')


@app.cli.command('seed-policies')
def seed_policies():
    """Seed default warranty policies into the database."""
    from app.services.policy_service import seed_default_policies
    with app.app_context():
        seed_default_policies()
        print('✓ Default warranty policies seeded.')


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'init-db':
            with app.app_context():
                db.create_all()
                print('[OK] Database tables created.')
            sys.exit(0)
        elif cmd == 'seed-policies':
            from app.services.policy_service import seed_default_policies
            with app.app_context():
                seed_default_policies()
                print('[OK] Default warranty policies seeded.')
            sys.exit(0)

    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=app.config['DEBUG'],
        use_reloader=False
    )
