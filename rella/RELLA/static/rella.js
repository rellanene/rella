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
	function loadLeaveHistory() {
	    let start = document.getElementById("leave_start").value;
	    let end = document.getElementById("leave_end").value;
	    let staff = document.getElementById("leave_staff").value;

	    fetch(`/hr/history/leave?start=${start}&end=${end}&staff_id=${staff}`)
	        .then(r => r.json())
	        .then(data => {
	            let body = document.getElementById("leave_history_body");
	            body.innerHTML = "";

	            data.rows.forEach(r => {
	                body.innerHTML += `
	                    <tr>
	                        <td>${r.staff_name}</td>
	                        <td>${r.leave_type_name}</td>
	                        <td>${r.start_date}</td>
	                        <td>${r.end_date}</td>
	                        <td>${r.status}</td>
	                    </tr>
	                `;
	            });
	        });
	}
	function loadOvertimeHistory() {
	    let start = document.getElementById("ot_start").value;
	    let end = document.getElementById("ot_end").value;
	    let staff = document.getElementById("ot_staff").value;

	    fetch(`/hr/history/overtime?start=${start}&end=${end}&staff_id=${staff}`)
	        .then(r => r.json())
	        .then(data => {
	            let body = document.getElementById("ot_history_body");
	            body.innerHTML = "";

	            data.rows.forEach(r => {
	                body.innerHTML += `
	                    <tr>
	                        <td>${r.staff_name}</td>
	                        <td>${r.date}</td>
	                        <td>${r.hours}</td>
	                        <td>${r.status}</td>
	                    </tr>
	                `;
	            });
	        });
	}

