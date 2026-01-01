import os
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify
from flask_cors import CORS

# 1. Initialize Flask
app = Flask(__name__)
CORS(app)  # Allows your frontend to talk to this backend

# 2. Initialize Firebase Database
# ⚠️ MAKE SURE YOU HAVE 'serviceAccountKey.json' in your folder or set up via Env Vars
# If you haven't set up the key yet, this part will error until you do.
try:
    if not firebase_admin._apps:
        # Check if we are on Render (using environment variable) or local
        if os.environ.get('FIREBASE_KEY'):
            # If you pasted your JSON content into a Render Env Var called FIREBASE_KEY
            import json
            cred_info = json.loads(os.environ.get('FIREBASE_KEY'))
            cred = credentials.Certificate(cred_info)
        else:
            # Local fallback (looks for file)
            cred = credentials.Certificate("serviceAccountKey.json")
            
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
except Exception as e:
    print(f"Warning: Firebase not connected yet. Error: {e}")
    # We continue so the app doesn't crash, but DB calls will fail.

# --- ROUTES ---

@app.route('/')
def home():
    return "UPCentralBank Backend is Running!"

# MINING ENDPOINT
@app.route('/mine', methods=['POST'])
def mine_income():
    data = request.json
    username = data.get('username')
    time_seconds = data.get('time_seconds')
    provided_ip_hash = data.get('ip_hash')

    if not username or not time_seconds or not provided_ip_hash:
        return jsonify({"error": "Missing data"}), 400

    try:
        # Get user from DB
        user_ref = db.collection('users').document(username)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "User not found"}), 404

        user_data = user_doc.to_dict()
        stored_ip_hash = user_data.get('ip_hash')

        # SECURITY CHECK: IP HASH
        if stored_ip_hash != provided_ip_hash:
            return jsonify({"error": "Security Alert: IP Mismatch. Mining rejected."}), 403

        # CALCULATE REWARD (Example: 1 Coin per second)
        # You can change the multiplier here
        reward = int(time_seconds) * 1 
        
        # Update Balance
        # Uses Firestore increment for safety
        user_ref.update({"balance": firestore.Increment(reward)})

        return jsonify({
            "success": True, 
            "reward": reward, 
            "message": f"Mined {reward} coins for {time_seconds} seconds."
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# TRANSFER ENDPOINT (Anti-Alt Account)
@app.route('/transfer', methods=['POST'])
def transfer_money():
    data = request.json
    sender = data.get('sender')
    receiver = data.get('receiver')
    amount = data.get('amount')

    if not sender or not receiver or not amount:
        return jsonify({"error": "Missing data"}), 400

    try:
        sender_ref = db.collection('users').document(sender)
        receiver_ref = db.collection('users').document(receiver)

        sender_doc = sender_ref.get()
        receiver_doc = receiver_ref.get()

        if not sender_doc.exists or not receiver_doc.exists:
            return jsonify({"error": "One or both users not found"}), 404

        sender_data = sender_doc.to_dict()
        receiver_data = receiver_doc.to_dict()

        # SECURITY CHECK: PREVENT SELF/ALT TRANSFER
        # If both accounts have the exact same IP Hash, block it.
        if sender_data.get('ip_hash') == receiver_data.get('ip_hash'):
            return jsonify({"error": "Illegal Transfer: You cannot send money to an account on the same network."}), 403

        # CHECK BALANCE
        if sender_data.get('balance', 0) < amount:
            return jsonify({"error": "Insufficient funds"}), 400

        # EXECUTE TRANSFER (Atomic Transaction)
        # This ensures money isn't lost if the server crashes halfway
        transaction = db.transaction()
        
        @firestore.transactional
        def update_in_transaction(transaction, sender_ref, receiver_ref, amount):
            transaction.update(sender_ref, {"balance": firestore.Increment(-amount)})
            transaction.update(receiver_ref, {"balance": firestore.Increment(amount)})

        update_in_transaction(transaction, sender_ref, receiver_ref, amount)

        return jsonify({"success": True, "message": f"Transferred {amount} to {receiver}"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# UPDATE IP ENDPOINT
@app.route('/update_ip', methods=['POST'])
def update_ip():
    data = request.json
    username = data.get('username')
    new_ip_hash = data.get('new_ip_hash')
    # In a real app, you should verify a password here!
    
    if not username or not new_ip_hash:
        return jsonify({"error": "Missing data"}), 400

    try:
        user_ref = db.collection('users').document(username)
        # Check if user exists
        if not user_ref.get().exists:
             return jsonify({"error": "User not found"}), 404
             
        # Update the IP
        user_ref.update({"ip_hash": new_ip_hash})
        
        return jsonify({"success": True, "message": "IP Hash updated successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- SERVER STARTUP ---
if __name__ == '__main__':
    # This ensures it works on both Local (5000) and Render (Environmental Variable)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
