"""
app/utils/error_handlers.py
Global error handlers — return clean JSON responses without stack traces.
FR xlix: System must handle all errors gracefully with user-friendly messages.
"""
from flask import jsonify


def register_error_handlers(app):
    """Register all HTTP error handlers on the Flask app."""

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({
            'error': 'Bad Request',
            'message': str(e.description) if hasattr(e, 'description') else 'Invalid request data.'
        }), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication is required to access this resource.'
        }), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({
            'error': 'Forbidden',
            'message': 'You do not have permission to perform this action.'
        }), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource was not found.'
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            'error': 'Method Not Allowed',
            'message': 'The HTTP method is not allowed for this endpoint.'
        }), 405

    @app.errorhandler(409)
    def conflict(e):
        return jsonify({
            'error': 'Conflict',
            'message': str(e.description) if hasattr(e, 'description') else 'A conflict occurred.'
        }), 409

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return jsonify({
            'error': 'File Too Large',
            'message': 'Uploaded file exceeds the 10MB size limit.'
        }), 413

    @app.errorhandler(422)
    def unprocessable_entity(e):
        return jsonify({
            'error': 'Validation Error',
            'message': str(e.description) if hasattr(e, 'description') else 'Input data failed validation.'
        }), 422

    @app.errorhandler(429)
    def too_many_requests(e):
        return jsonify({
            'error': 'Too Many Requests',
            'message': 'Rate limit exceeded. Please try again later.'
        }), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        # No technical details exposed to client
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred. Please try again later.'
        }), 500
