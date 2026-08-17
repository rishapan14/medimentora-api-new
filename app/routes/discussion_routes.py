from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import discussion_controller as ctrl

discussion_bp = Blueprint("discussions", __name__, url_prefix="/api/discussions")

discussion_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_discussions), methods=["GET"])
discussion_bp.add_url_rule("", view_func=jwt_required()(ctrl.create_discussion), methods=["POST"])
discussion_bp.add_url_rule("/<int:discussion_id>", view_func=jwt_required()(ctrl.get_discussion), methods=["GET"])
discussion_bp.add_url_rule("/<int:discussion_id>", view_func=jwt_required()(ctrl.update_discussion), methods=["PUT"])
discussion_bp.add_url_rule("/<int:discussion_id>", view_func=jwt_required()(ctrl.delete_discussion), methods=["DELETE"])
discussion_bp.add_url_rule("/<int:discussion_id>/comments", view_func=jwt_required()(ctrl.add_comment), methods=["POST"])
discussion_bp.add_url_rule("/comments/<int:comment_id>", view_func=jwt_required()(ctrl.delete_comment), methods=["DELETE"])
discussion_bp.add_url_rule("/<int:discussion_id>/like", view_func=jwt_required()(ctrl.like_discussion), methods=["POST"])
discussion_bp.add_url_rule("/comments/<int:comment_id>/like", view_func=jwt_required()(ctrl.like_comment), methods=["POST"])
