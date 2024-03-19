import os
from dotenv import load_dotenv
import requests
import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
from gen_keys import generate_key_pair

# Initialize Firebase Admin once
if not firebase_admin._apps:
    cred = credentials.Certificate('firebase-admin.json')
    default_app = firebase_admin.initialize_app(cred)

# Firestore database
db = firestore.client()

# Function to create a new user in Firebase Authentication
def create_user(email, password):
    try:
        user = auth.create_user(email=email, password=password)
        return user
    except Exception as e:
        st.error(f"Error creating user: {str(e)}")
        return None
    
# Function to save user details in Firestore
def save_user_details(user_id, username, email):
    try:
        certificate = generate_key_pair(user_id)
        doc_ref = db.collection(u'users').document(user_id)
        doc_ref.set({
            u'username': username,
            u'email': email,
            u'certificate': certificate
        })
        return True
    except Exception as e:
        st.error(f"Error saving user details: {str(e)}")
        return False
    

def authenticate_user(email, password):
    load_dotenv()
    api_key = os.getenv("FIREBASE_KEY")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        user_details = response.json()
        # user_details now contains user info, including a token you can use to make authenticated requests
        return user_details
    else:
        return None