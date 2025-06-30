from flask import Flask, render_template, request, redirect, session, url_for, jsonify,flash
import pymongo
import boto3
from boto3.dynamodb.conditions import Key, Attr
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
import uuid
import random
import urllib.parse
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = '37947df6845abbca9bfa81363c79e879ed6cf98521fd2f80051350f8e80ec6e6'

# AWS Setup using IAM Role
REGION = 'us-east-1'  # Replace with your actual AWS region
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sns_client = boto3.client('sns', region_name='us-east-1')

users_table = dynamodb.Table('travelgo_users')
trains_table = dynamodb.Table('trains')
bookings_table = dynamodb.Table('bookings')

SNS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:353250843450:TravelGoBookingTopic'  # Replace with actual SNS topic ARN

def send_sns_notification(subject, message):
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
    except Exception as e:
        print(f"SNS Error: {e}")


@app.route('/')
def home():
    return render_template('home.html', logged_in='email' in session)


@app.route('/welcome')
def welcome():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('welcome.html', username=session.get('username'))




@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        users.insert_one({"email": email, "username": username, "hashed_password": password, "login_count": 0})
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users.find_one({'email': email})
        if user and check_password_hash(user['hashed_password'], password):
            session['email'] = email
            session['username'] = user['username']
            users.update_one({'email': email}, {'$inc': {'login_count': 1}})
            return redirect(url_for('welcome'))
        else:
            return render_template('login.html', error="Invalid credentials.")
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    username = session.get('username', 'User')
    user_email = session['email']
    bookings = []
    for b in bookings_collection.find({'user_email': user_email}):
        booking_type = b.get('booking_type', 'Unknown').capitalize()
        if b.get('booking_type') in ['bus', 'train', 'flight']:
            details = f"{b.get('source')} → {b.get('destination')} @ {b.get('travel_date')}"
        elif b.get('booking_type') == 'hotel':
            details = f"{b.get('hotel_name')} from {b.get('checkin_date')}"
        else:
            details = "Details not available"
        bookings.append({
            'type': booking_type,
            'details': details,
            'date': b.get('booking_date', 'N/A')[:16].replace('T', ' '),
            'booking_id': str(b.get('_id'))
        })
    return render_template('dashboard.html', username=username, bookings=bookings)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/bus')
def bus_booking_page():
    return render_template('bus.html') if 'email' in session else redirect(url_for('login'))


@app.route('/confirm_bus_details')
def confirm_bus_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        name = request.args.get('name')
        source = request.args.get('source')
        destination = request.args.get('destination')
        time = request.args.get('time')
        bus_type = request.args.get('type')
        price = float(request.args.get('price'))
        date = request.args.get('date')
        persons = int(request.args.get('persons'))
        bus_id = request.args.get('busId')

        if not all([name, source, destination, time, bus_type, date, bus_id]):
            return "⚠ Missing booking information. Please try again.", 500

        booking_details = {
            'name': name,
            'source': source,
            'destination': destination,
            'time': time,
            'type': bus_type,
            'price_per_person': price,
            'travel_date': date,
            'num_persons': persons,
            'item_id': bus_id,
            'booking_type': 'bus',
            'user_email': session['email'],
            'total_price': price * persons
        }

        session['pending_booking'] = booking_details
        return render_template('confirm_bus_details.html', booking=booking_details)

    except Exception as e:
        print("❌ Error in confirm_bus_details:", str(e))
        return "❌ Error processing booking details.", 400

@app.route('/final_confirm_booking', methods=['POST'])
def final_confirm_booking():
    if 'pending_booking' not in session:
        return jsonify({"success": False, "message": "No pending booking found."})

    booking = session.pop('pending_booking')
    booking['booking_date'] = datetime.now().isoformat()
    bookings_collection.insert_one(booking)
    return jsonify({"success": True, "message": "Booking successful", "redirect": "/dashboard"})

@app.route('/bookings')
def bookings():
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    bookings = list(bookings_collection.find({'user_email': email}))
    return render_template('bookings.html', bookings=bookings)

@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'email' not in session:
        return redirect(url_for('login'))
    booking_id = request.form.get('booking_id')
    if booking_id:
        bookings_collection.delete_one({'_id': ObjectId(booking_id), 'user_email': session['email']})
    return redirect(url_for('bookings'))

@app.route('/train')
def train_booking_page():
    return render_template('train.html') if 'email' in session else redirect(url_for('login'))


@app.route('/flight')
def flight_booking_page():
    return render_template('flight.html') if 'email' in session else redirect(url_for('login'))


@app.route('/hotel')
def hotel_booking_page():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('hotel.html')





@app.route('/select_seats', methods=['GET', 'POST'])
def select_seats():
    if 'pending_booking' not in session:
        return "No pending booking found.", 400

    booking = session['pending_booking']

    if request.method == 'POST':
        selected = request.form.get('selected_seats', '')
        if selected:
            booking['selected_seats'] = selected
            booking['booking_date'] = datetime.now().isoformat()
            db.bookings.insert_one(booking)
            session.pop('pending_booking', None)
            return redirect(url_for('bookings'))  # or dashboard

    return render_template('select_seats.html', booking=booking)

@app.route('/start_booking', methods=['POST'])
def start_booking():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Login required'})

    data = request.get_json()
    booking_type = data['type']
    args = data['details']

    booking = {
        'booking_type': booking_type,
        'user_email': session['email'],
    }

    if booking_type == 'train':
        booking.update({
            'name': args[0], 'trainNo': args[1], 'source': args[2], 'destination': args[3],
            'travel_time': args[4], 'arrival': args[5], 'vehicle_type': args[6],
            'price_per_person': float(args[7]), 'travel_date': args[8], 'num_persons': int(args[9]),
            'total_price': float(args[7]) * int(args[9])
        })
    elif booking_type == 'flight':
        booking.update({
            'name': args[0], 'flightNo': args[1], 'source': args[2], 'destination': args[3],
            'travel_time': args[4], 'arrival': args[5], 'vehicle_type': args[6],
            'price_per_person': float(args[7]), 'travel_date': args[8], 'num_persons': int(args[9]),
            'total_price': float(args[7]) * int(args[9])
        })
    elif booking_type == 'hotel':
        booking.update({
            'hotel_name': args[0], 'location': args[1], 'checkin_date': args[2], 'checkout_date': args[3],
            'rooms': int(args[4]), 'guests': int(args[5]), 'price_per_night': float(args[6]), 'rating': int(args[7]),
            'nights': 1, 'total_price': float(args[6]) * int(args[4]),
            'booking_date': datetime.now().isoformat()
        })
        bookings_collection.insert_one(booking)
        return jsonify({'success': True, 'message': 'Hotel booking successful', 'redirect': '/dashboard'})
    else:
        return jsonify({'success': False, 'message': 'Invalid booking type'})

    session['pending_booking'] = booking
    return jsonify({'success': True, 'redirect': url_for('select_seats')})

@app.route('/confirm_hotel_details')
def confirm_hotel_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = {
        'booking_type': 'hotel',
        'hotel_name': request.args.get('hotelName'),
        'location': request.args.get('location'),
        'checkin_date': request.args.get('checkin'),
        'checkout_date': request.args.get('checkout'),
        'guests': int(request.args.get('guests', 1)),
        'rooms': int(request.args.get('rooms', 1)),
        'price_per_night': float(request.args.get('price', 0)),
        'rating': request.args.get('rating'),
        'total_price': float(request.args.get('price', 0)) * int(request.args.get('rooms', 1)),
        'user_email': session['email'],
    }

    session['pending_booking'] = booking
    return render_template('confirm_hotel_details.html', booking=booking)

@app.route('/wishlist')
def wishlist_page():
    if 'email' not in session:
        return redirect(url_for('login'))

    destinations = [
        {"id": "paris", "name": "Paris, France", "details": "City of love and lights. Price: $1200", "image": "paris.jpg"},
        {"id": "manali", "name": "Manali, India", "details": "Snowy mountains and serene beauty. Price: ₹8500", "image": "manali.jpg"},
        {"id": "coonoor", "name": "Coonoor, India", "details": "Green hills and tea gardens. Price: ₹7500", "image": "coonoor.jpg"},
        {"id": "bali", "name": "Bali, Indonesia", "details": "Tropical paradise. Price: $900", "image": "bali.jpg"},
        {"id": "tokyo", "name": "Tokyo, Japan", "details": "High-tech and tradition. Price: ¥100,000", "image": "tokyo.jpg"}
    ]
    saved_items = list(wishlist.find({'email': session['email']}))
    return render_template('wishlist.html', destinations=destinations, wishlist_items=saved_items)

@app.route('/add_to_wishlist', methods=['POST'])
def add_to_wishlist():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Login required'})
    data = request.get_json()
    wishlist.insert_one({
        'email': session['email'],
        'item_id': data['item_id'],
        'item_name': data['item_name'],
        'item_details': data['item_details'],
        'added_date': datetime.utcnow()
    })
    return jsonify({'success': True, 'message': 'Added to wishlist'})

@app.route('/remove_from_wishlist', methods=['POST'])
def remove_from_wishlist():
    if 'email' not in session:
        return jsonify({'success': False})
    item_id = request.json.get('item_id')
    wishlist.delete_one({'email': session['email'], 'item_id': item_id})
    return jsonify({'success': True, 'message': 'Removed from wishlist'})

@app.route('/checkout')
def checkout():
    return render_template('checkout.html', items=session.get('checkout_items', [])) if 'email' in session else redirect(url_for('login'))

@app.route('/order', methods=['GET', 'POST'])
def order():
    if 'email' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        session.pop('checkout_items', None)
        return render_template('order.html', order_completed=True, checkout_items=[], total_price=0.0)
    checkout_items = session.get('checkout_items', [])
    total_price = sum(float(item['price'].replace('₹', '').replace('$', '')) * item.get('quantity', 1) for item in checkout_items)
    return render_template('order.html', checkout_items=checkout_items, total_price=f"{total_price:.2f}", order_completed=False)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
