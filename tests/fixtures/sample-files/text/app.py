#!/usr/bin/env python3
"""
Simple REST API for a todo list application.
Demonstrates basic CRUD operations with Flask.
"""

from flask import Flask, jsonify, request, abort
from datetime import datetime
from uuid import uuid4

app = Flask(__name__)

# In-memory storage
todos = {}


@app.route("/api/todos", methods=["GET"])
def list_todos():
    """List all todo items with optional filtering."""
    status_filter = request.args.get("status")
    items = list(todos.values())
    if status_filter:
        items = [t for t in items if t["status"] == status_filter]
    return jsonify({
        "items": sorted(items, key=lambda x: x["created_at"]),
        "total": len(items),
    })


@app.route("/api/todos", methods=["POST"])
def create_todo():
    """Create a new todo item."""
    data = request.get_json()
    if not data or "title" not in data:
        abort(400, description="Title is required")

    todo = {
        "id": str(uuid4()),
        "title": data["title"],
        "description": data.get("description", ""),
        "status": "pending",
        "priority": data.get("priority", "medium"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    todos[todo["id"]] = todo
    return jsonify(todo), 201


@app.route("/api/todos/<todo_id>", methods=["PUT"])
def update_todo(todo_id):
    """Update an existing todo item."""
    if todo_id not in todos:
        abort(404, description="Todo not found")

    data = request.get_json()
    todo = todos[todo_id]
    todo.update({
        k: v for k, v in data.items()
        if k in ("title", "description", "status", "priority")
    })
    todo["updated_at"] = datetime.utcnow().isoformat()
    return jsonify(todo)


@app.route("/api/todos/<todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    """Delete a todo item."""
    if todo_id not in todos:
        abort(404, description="Todo not found")
    del todos[todo_id]
    return "", 204


if __name__ == "__main__":
    app.run(debug=True, port=5000)
