"""
app/__init__.py
Flask application factory for AssureX Claim Engine.
"""
import os
from flask import Flask
from .config import config
from .extensions import db, bcrypt, jwt, limiter, cors, jwt_blocklist


def create_app(config_name=None):
    """Application factory — creates and configures Flask app."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    root_dir = os.path.dirname(os.path.dirname(__file__))
    templates_dir = os.path.join(root_dir, 'templates')
    static_dir = os.path.join(root_dir, 'static')
    app = Flask(__name__, template_folder=templates_dir, static_folder=static_dir)
    app.config.from_object(config[config_name])

    if config_name != 'testing' and app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        raise RuntimeError(
            'Neon PostgreSQL is required. Set NEONDB_URL (or DATABASE_URL) before starting the app.'
        )

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(templates_dir, exist_ok=True)

    # ── Initialize extensions ─────────────────────────────────────────────────
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config['CORS_ORIGINS']}})

    # ── JWT token blocklist check ─────────────────────────────────────────────
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload.get('jti')
        return jti in jwt_blocklist

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        from flask import jsonify
        return jsonify({'error': 'Token has been revoked. Please log in again.'}), 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        from flask import jsonify
        return jsonify({'error': 'Token has expired. Please log in again.'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        from flask import jsonify
        return jsonify({'error': 'Invalid token. Please log in again.'}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        from flask import jsonify
        return jsonify({'error': 'Authentication token required.'}), 401

    # ── Register blueprints ───────────────────────────────────────────────────
    from .routes.auth import auth_bp
    from .routes.profile import profile_bp
    from .routes.products import products_bp
    from .routes.warranties import warranties_bp
    from .routes.documents import documents_bp
    from .routes.claims import claims_bp
    from .routes.ml import ml_bp
    from .routes.reviews import reviews_bp
    from .routes.dashboard import dashboard_bp
    from .routes.search import search_bp
    from .routes.reports import reports_bp
    from .routes.admin import admin_bp

    app.register_blueprint(auth_bp,       url_prefix='/api/auth')
    app.register_blueprint(profile_bp,    url_prefix='/api/profile')
    app.register_blueprint(products_bp,   url_prefix='/api/products')
    app.register_blueprint(warranties_bp, url_prefix='/api/warranties')
    app.register_blueprint(documents_bp,  url_prefix='/api/documents')
    app.register_blueprint(claims_bp,     url_prefix='/api/claims')
    app.register_blueprint(ml_bp,         url_prefix='/api/ml')
    app.register_blueprint(reviews_bp,    url_prefix='/api/reviews')
    app.register_blueprint(dashboard_bp,  url_prefix='/api/dashboard')
    app.register_blueprint(search_bp,     url_prefix='/api/search')
    app.register_blueprint(reports_bp,    url_prefix='/api/reports')
    app.register_blueprint(admin_bp,      url_prefix='/api/admin')

    # ── Register error handlers ───────────────────────────────────────────────
    from .utils.error_handlers import register_error_handlers
    register_error_handlers(app)

    # ── Ensure model versions and demo accounts are present in DB ─────────────
    try:
        with app.app_context():
            from .services.ml_service import ensure_model_versions_seeded
            ensure_model_versions_seeded()
            from .services.auth_service import ensure_initial_admin_seeded
            ensure_initial_admin_seeded()
    except Exception as e:
        app.logger.warning(f"Could not auto-seed model versions or admin: {e}")

    # ── Root Welcome & Web Application ────────────────────────────────────────
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    @limiter.exempt
    def catch_all(path):
        import urllib.request
        from flask import request, Response, jsonify, render_template

        # If it's an API route that somehow fell through
        if path.startswith('api/'):
            return jsonify({'error': 'Not Found', 'message': f'API endpoint /{path} does not exist.'}), 404

        if path == '' and request.headers.get('Accept') == 'application/json':
            return jsonify({
                'service': 'AssureX Claim Engine API',
                'status': 'online',
                'version': '1.0',
                'database': 'NeonDB (PostgreSQL)',
                'endpoints': {
                    'health': '/api/health',
                    'auth': '/api/auth',
                    'products': '/api/products',
                    'warranties': '/api/warranties',
                    'claims': '/api/claims',
                    'documents': '/api/documents',
                    'ml': '/api/ml',
                    'reviews': '/api/reviews',
                    'dashboard': '/api/dashboard/stats',
                    'reports': '/api/reports',
                    'admin': '/api/admin',
                    'search': '/api/search'
                }
            })

        # Serve the unified full-featured web application template instantly (0ms lag)
        # Optional Vite proxy only if ENABLE_VITE_PROXY is explicitly enabled and listening
        if os.getenv('ENABLE_VITE_PROXY', 'false').lower() == 'true':
            import socket
            try:
                with socket.create_connection(('127.0.0.1', 8080), timeout=0.05):
                    target_url = f"http://127.0.0.1:8080/{path}"
                    if request.query_string:
                        target_url += f"?{request.query_string.decode('utf-8')}"
                    req = urllib.request.Request(
                        target_url,
                        headers={k: v for k, v in request.headers if k.lower() not in ['host', 'content-length']}
                    )
                    with urllib.request.urlopen(req, timeout=1) as resp:
                        content = resp.read()
                        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
                        headers = [(name, value) for (name, value) in resp.getheaders() if name.lower() not in excluded_headers]
                        return Response(content, resp.status, headers)
            except Exception:
                pass

        return render_template('index.html')

    # ── Health check ──────────────────────────────────────────────────────────
    @app.route('/api/health')
    def health_check():
        from flask import jsonify
        return jsonify({
            'status': 'ok',
            'service': 'AssureX Claim Engine',
            'version': '1.0',
            'database': 'NeonDB (PostgreSQL)'
        }), 200

    return app

