from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import boto3
from boto3.dynamodb.conditions import Key, Attr
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
import uuid
import random
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_in_production")

# AWS Setup
REGION = 'ap-south-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

# DynamoDB Tables
users_table = dynamodb.Table('travelgo_users')
bookings_table = dynamodb.Table('bookings')
wishlist_table = dynamodb.Table('wishlist')  # Added from first version

# SNS Topic
SNS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:353250843450:TravelGoBookingTopic'

def send_sns_notification(subject, message):
    try:
        sns_client.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    except Exception as e:
        print(f"SNS Error: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if 'Item' in users_table.get_item(Key={'email': email}):
            flash('Email already exists!', 'error')
            return render_template('register.html')
        hashed_password = generate_password_hash(password)
        users_table.put_item(Item={'email': email, 'password': hashed_password})
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_table.get_item(Key={'email': email})
        if 'Item' in user and check_password_hash(user['Item']['password'], password):
            session['email'] = email
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    user_email = session['email']
    response = bookings_table.query(
        KeyConditionExpression=Key('user_email').eq(user_email),
        ScanIndexForward=False
    )
    bookings = response.get('Items', [])
    for b in bookings:
        if 'total_price' in b:
            b['total_price'] = float(b['total_price'])
    return render_template('dashboard.html', username=user_email, bookings=bookings)

@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'email' not in session:
        return redirect(url_for('login'))
    booking_id = request.form.get('booking_id')
    booking_date = request.form.get('booking_date')
    if not booking_id or not booking_date:
        flash("Invalid cancellation request.", 'error')
        return redirect(url_for('dashboard'))
    try:
        bookings_table.delete_item(Key={'user_email': session['email'], 'booking_date': booking_date})
        flash("Booking cancelled successfully.", 'success')
    except Exception as e:
        flash(f"Cancellation failed: {str(e)}", 'error')
    return redirect(url_for('dashboard'))

# Add endpoints for /train, /bus, /flight, /hotel bookings from your second version here...
# Add wishlist logic from first version...

@app.route('/wishlist')
def wishlist_page():
    if 'email' not in session:
        return redirect(url_for('login'))
    destinations = [
        {"id": "paris", "name": "Paris", "details": "City of lights. $1200", "image": "paris.jpg"},
        {"id": "manali", "name": "Manali", "details": "Snowy getaway. ₹8500", "image": "manali.jpg"},
        {"id": "tokyo", "name": "Tokyo", "details": "Futuristic Tokyo. ¥100,000", "image": "tokyo.jpg"}
    ]
    response = wishlist_table.query(KeyConditionExpression=Key('email').eq(session['email']))
    saved_items = response.get('Items', [])
    return render_template('wishlist.html', destinations=destinations, wishlist_items=saved_items)

@app.route('/add_to_wishlist', methods=['POST'])
def add_to_wishlist():
    if 'email' not in session:
        return jsonify({'success': False})
    data = request.get_json()
    wishlist_table.put_item(Item={
        'email': session['email'],
        'item_id': data['item_id'],
        'item_name': data['item_name'],
        'item_details': data['item_details'],
        'added_date': datetime.utcnow().isoformat()
    })
    return jsonify({'success': True})

@app.route('/remove_from_wishlist', methods=['POST'])
def remove_from_wishlist():
    if 'email' not in session:
        return jsonify({'success': False})
    item_id = request.json.get('item_id')
    wishlist_table.delete_item(Key={'email': session['email'], 'item_id': item_id})
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
