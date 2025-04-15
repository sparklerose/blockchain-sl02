# File: SL02.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import hashlib
import time
import argparse
from enum import Enum
import requests

app = Flask(__name__)
CORS(app)

# === 🔐 PoA Setup ===
is_leader = False  # Set to True for the leader node (e.g., port 5000)
peer_nodes = [
    "http://127.0.0.1:5000",  # Leader
    "http://127.0.0.1:5001",
    "http://127.0.0.1:5002"
]

class AttendanceStatus(Enum):
    PRESENT = "Present"
    LATE = "Late"
    ABSENT = "Absent"

class Blockchain:
    def __init__(self):
        self.chain = []
        self.transactions = []
        self.authorized_addresses = set()
        self.create_block(previous_hash='0')

    def create_block(self, previous_hash):
        start_time = time.time()
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'transactions': self.transactions.copy(),
            'previous_hash': previous_hash,
            'hash': ''
        }
        block['hash'] = self.hash_block(block)
        block['latency'] = round(time.time() - start_time, 4)  # ⏱️ Add latency value
        self.chain.append(block)
        self.transactions = []
        return block


    def add_transaction(self, data):
        transaction = {
            'student_id': data['student_id'],
            'student_name': data.get('student_name', ''),
            'project_name': data.get('project_name', ''),
            'supervisor_name': data.get('supervisor_name', ''),
            'department': data.get('department', ''),
            'completion_status': data.get('completion_status', ''),
            'remarks': data.get('remarks', ''),
            'timestamp': time.time(),
            'signature': data.get('signature', ''),
            'record_type': data['record_type']
        }
        self.transactions.append(transaction)
        return self.last_block['index'] + 1

    def hash_block(self, block):
        encoded_block = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(encoded_block).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def add_authorized(self, address):
        self.authorized_addresses.add(address)

    def is_authorized(self, address):
        return address in self.authorized_addresses

    def get_attendance_records(self, student_id, course_id=None):
        records = []
        for block in self.chain:
            for tx in block['transactions']:
                if tx.get('record_type') == 'Attendance' and tx['student_id'] == student_id:
                    if course_id is None or tx.get('remarks') == course_id:
                        records.append(tx)
        return sorted(records, key=lambda x: x['timestamp'])

    def calculate_attendance_rate(self, student_id, course_id):
        records = self.get_attendance_records(student_id, course_id)
        if not records:
            return (0.0, 0.0, 0.0)
        total = len(records)
        present = sum(1 for r in records if r["completion_status"] == AttendanceStatus.PRESENT.value)
        late = sum(1 for r in records if r["completion_status"] == AttendanceStatus.LATE.value)
        absent = total - present - late
        return (
            round(present / total * 100, 1),
            round(late / total * 100, 1),
            round(absent / total * 100, 1)
        )

blockchain = Blockchain()
blockchain.add_authorized("0xTeacher1")

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    data = request.get_json()
    required = ['student_id', 'record_type']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400

    if data['record_type'] not in ['ProjectCompletion', 'Attendance']:
        return jsonify({'error': 'Invalid record_type'}), 400

    if data['record_type'] == 'Attendance':
        teacher = data.get('supervisor_name', '')
        if not blockchain.is_authorized(teacher):
            return jsonify({'error': f"❌ Unauthorized teacher address: {teacher}"}), 403

        if data.get('completion_status') not in [s.value for s in AttendanceStatus]:
            return jsonify({'error': '❌ Invalid attendance status'}), 400

    # 🚦 PoA Forwarding
    if not is_leader:
        try:
            leader_url = peer_nodes[0]
            response = requests.post(f"{leader_url}/add_transaction", json=data)
            return jsonify(response.json()), response.status_code
        except Exception as e:
            return jsonify({'error': f"❌ Failed to forward to leader: {str(e)}"}), 500

    # ✅ Leader node: process and mine the transaction
    import datetime
    index = blockchain.add_transaction(data)
    start_time = time.time()
    new_block = blockchain.create_block(blockchain.last_block['hash'])
    end_time = time.time()
    latency = round(end_time - start_time, 4)
    print(f"⏱️ Block {new_block['index']} mined in {latency} seconds at {datetime.datetime.now()}")

    # 🚀 Broadcast to peers
    for peer in peer_nodes[1:]:
        try:
            requests.post(f"{peer}/receive_block", json={
                "index": new_block['index'],
                "timestamp": new_block['timestamp'],
                "transactions": new_block['transactions'],
                "previous_hash": new_block['previous_hash'],
                "hash": new_block['hash']
            })
            print(f"✅ Block sent to {peer}")
        except Exception as e:
            print(f"⚠️ Failed to replicate block to {peer}: {e}")

    return jsonify({'message': f'Transaction added and mined into Block {index} by Leader Node'}), 201



@app.route('/receive_block', methods=['POST'])
def receive_block():
    data = request.get_json()
    required = ['index', 'timestamp', 'transactions', 'previous_hash', 'hash']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing block fields'}), 400

    if data['index'] <= blockchain.last_block['index']:
        return jsonify({'error': 'Outdated block'}), 400

    blockchain.chain.append(data)
    return jsonify({'message': '✅ Block replicated successfully'}), 200

@app.route('/mine', methods=['GET'])
def mine():
    previous_hash = blockchain.last_block['hash']
    block = blockchain.create_block(previous_hash)
    return jsonify(block), 200

@app.route('/chain', methods=['GET'])
def get_chain():
    return jsonify({'chain': blockchain.chain, 'length': len(blockchain.chain)}), 200

@app.route('/all_projects', methods=['GET'])
def all_projects():
    projects = []
    for block in blockchain.chain:
        for tx in block['transactions']:
            if tx.get('record_type') == 'ProjectCompletion':
                projects.append({
                    'student_id': tx['student_id'],
                    'student_name': tx.get('student_name', ''),
                    'project_name': tx.get('project_name', ''),
                    'supervisor_name': tx.get('supervisor_name', ''),
                    'department': tx.get('department', ''),
                    'completion_status': tx.get('completion_status', ''),
                    'remarks': tx.get('remarks', ''),
                    'timestamp': tx['timestamp'],
                    'signature': tx.get('signature', '')
                })
    return jsonify({'projects': projects}), 200

@app.route('/all_attendance', methods=['GET'])
def all_attendance():
    attendance = []
    for block in blockchain.chain:
        for tx in block['transactions']:
            if tx.get('record_type') == 'Attendance':
                attendance.append({
                    'student_id': tx['student_id'],
                    'course_id': tx.get('remarks', ''),
                    'status': tx.get('completion_status', ''),
                    'marked_by': tx.get('supervisor_name', ''),
                    'timestamp': tx['timestamp']
                })
    return jsonify({'attendance': attendance}), 200

@app.route('/attendance_rate', methods=['GET'])
def attendance_rate():
    student_id = request.args.get('student_id')
    course_id = request.args.get('course_id')
    if not student_id or not course_id:
        return jsonify({'error': 'Missing student_id or course_id'}), 400

    present, late, absent = blockchain.calculate_attendance_rate(student_id, course_id)
    return jsonify({
        'student_id': student_id,
        'course_id': course_id,
        'present_percent': present,
        'late_percent': late,
        'absent_percent': absent
    }), 200

@app.route('/')
def index():
    return "<h1>Welcome to the Blockchain Node!</h1>"

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--leader', action='store_true', help="Run this node as leader")
    args = parser.parse_args()

    is_leader = args.leader
    print(f"✅ Blockchain started at port {args.port} | Leader: {is_leader}")
    app.run(host='0.0.0.0', port=args.port)
