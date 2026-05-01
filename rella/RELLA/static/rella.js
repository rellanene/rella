@app.route('/tasks/update-status', methods=['POST'])
@require_login
def task_update_status_api():
    user = current_user()
    data = request.get_json(force=True)

    task_id = data.get('task_id')
    new_status = data.get('status')

    if not task_id or not new_status:
        return jsonify({'success': False, 'error': 'Missing data'})

    execute("""
        UPDATE tasks 
        SET status=%s, updated_by=%s 
        WHERE id=%s
    """, (new_status, user['id'], task_id))

    execute("""
        INSERT INTO task_history (task_id, user_id, action, details)
        VALUES (%s,%s,'kanban_status_change',%s)
    """, (task_id, user['id'], f"Moved to {new_status}"))

    return jsonify({'success': True})
