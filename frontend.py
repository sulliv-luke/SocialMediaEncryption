import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
import datetime
import requests
import os                                                                                                                                                                                                          
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

# Initialize Firebase Admin once
if not firebase_admin._apps:
    cred = credentials.Certificate('firebase-admin.json')
    default_app = firebase_admin.initialize_app(cred)

# Firestore database
db = firestore.client()

# Remove menu and footer
# =======================
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True) 
# =======================

def create_post(user_id, text):
    # Add a new post to the "posts" collection
    posts_ref = db.collection('posts')
    posts_ref.add({'user_id': user_id, 'text': text, 'timestamp': datetime.datetime.now()})


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
        doc_ref = db.collection(u'users').document(user_id)
        doc_ref.set({
            u'username': username,
            u'email': email,
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

    

def create_group(group_name, admin_id):
    groups_ref = db.collection('groups')
    # Check if the group already exists
    existing_group = groups_ref.where('name', '==', group_name).get()
    if not existing_group:
        _, group_doc_ref = groups_ref.add({  # Unpack the tuple to get the DocumentReference
            'name': group_name,
            'admin': admin_id,
            'members': [admin_id]
        })
        return group_doc_ref.id  # Now correctly getting the ID from the DocumentReference
    else:
        return None  # Group already exists


def add_user_to_group(group_name, username_to_add, admin_id):
    # Find the user ID of the user to add
    users_ref = db.collection('users')
    user_docs = users_ref.where('username', '==', username_to_add).get()
    if not user_docs:
        return "User not found"
    
    user_to_add_id = user_docs[0].id
    
    # Find the group and add the user to it
    groups_ref = db.collection('groups')
    group_doc = groups_ref.where('name', '==', group_name).where('admin', '==', admin_id).get()
    
    if not group_doc:
        return "Group not found or you're not the admin"
    
    group = group_doc[0]
    if user_to_add_id in group.to_dict()['members']:
        return "User already in the group"
    
    groups_ref.document(group.id).update({
        'members': firestore.ArrayUnion([user_to_add_id])
    })
    return "User added successfully"

def get_group_posts(user_id):
    # Step 1: Find all groups where the current user is a member
    groups_ref = db.collection('groups')
    groups = groups_ref.where('members', 'array_contains', user_id).get()

    # Step 2: Collect unique user IDs from these groups
    user_ids = set()
    for group in groups:
        members = group.to_dict().get('members', [])
        user_ids.update(members)

    # Optionally remove the current user's ID from the set if you don't want to see your own posts
    user_ids.discard(user_id)

    # Step 3: Fetch posts made by these users
    posts_ref = db.collection('posts')
    posts = []
    for uid in user_ids:
        user_posts = posts_ref.where('user_id', '==', uid).order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        for post in user_posts:
            posts.append(post.to_dict())

    # Optionally, you might want to sort all posts by timestamp here, as they are grouped by user above
    posts.sort(key=lambda x: x['timestamp'], reverse=True)

    return posts


# A function that gets all posts from a specific user
def get_user_posts(user_id):
    posts_ref = db.collection('posts')
    user_posts_query = posts_ref.where('user_id', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING)
    user_posts = user_posts_query.stream()

    user_posts_list = []
    for post in user_posts:
        post_data = post.to_dict()
        post_data['post_id'] = post.id  # Store Firestore document ID to identify the post for deletion
        user_posts_list.append(post_data)

    return user_posts_list

# A function that deletes a specific post
def delete_post(post_id):
    try:
        db.collection('posts').document(post_id).delete()
        st.success("Post deleted successfully.")
    except Exception as e:
        st.error(f"An error occurred while deleting the post: {e}")


    
def dashboard_page():
    # Ensure the user is logged in
    if 'current_user' not in st.session_state or not st.session_state['current_user']:
        st.error("Please login to view the dashboard.")
        return
    
    user_id = st.session_state['current_user']['uid']  # Use UID for internal processes
    username = st.session_state['current_user']['username']  # Use Username for display or other logic
    
    st.title(f"Dashboard - Welcome {username}!")
    
    # Allow the user to create a new post
    with st.form("new_post"):
        post_text = st.text_area("What's happening?")
        submit_post = st.form_submit_button("Post")
        if submit_post and post_text:
            create_post(user_id, post_text)
            st.success("Posted successfully!")
    
    # Display posts from users the current user follows
    st.write("### Posts from people you follow")
    posts = get_group_posts(user_id)
    for post in posts:
        post_user_details = db.collection('users').document(post['user_id']).get()
        post_username = post_user_details.to_dict().get('username')
        st.write(f"{post['text']} (Posted by: {post_username})")

# Function to render the signup form
def signup_page():
    with st.form("signup_form"):
        st.write("### Sign Up")
        email = st.text_input("Email")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        signup_button = st.form_submit_button("Sign Up")
        
        if signup_button:
            user = create_user(email, password)
            if user:
                save_success = save_user_details(user.uid, username, email)
                if save_success:
                    st.success("Account created successfully!")
                else:
                    st.error("Failed to save user details.")

def login_page():
    st.title("Social Media Login Page")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        
        # Login button
        login_button = st.form_submit_button("Login")
        
        if login_button:
            user_details = authenticate_user(email, password)
            if user_details:
                # Assuming user_details is the dictionary with authentication response
                # and user UID is under the key 'localId'
                user_id = user_details['localId']
                
                # Fetch additional user details from Firestore using user_id
                firestore_user_details = db.collection('users').document(user_id).get()
                if firestore_user_details.exists:
                    firestore_user_data = firestore_user_details.to_dict()
                    st.session_state['current_user'] = {
                        'uid': user_id,
                        'email': email,  # email is directly available from the login form input
                        'username': firestore_user_data.get('username')
                    }
                    st.success("Login Successful!")
                    # Redirect to the dashboard or another page
                    st.experimental_rerun()  # Correct method to rerun the app
                else:
                    st.error("User details not found.")
            else:
                st.error("Login Failed. Please check your email and password.")



def group_management_page():
    st.title("Group Management")
    
    with st.form("create_group"):
        new_group_name = st.text_input("Enter new group name")
        create_group_button = st.form_submit_button("Create Group")
        
        if create_group_button and new_group_name:
            result = create_group(new_group_name, st.session_state['current_user']['uid'])
            if result:
                st.success("Group created successfully!")
            else:
                st.error("Group already exists.")

    with st.form("add_user_to_group"):
        group_name = st.text_input("Enter group name to add user to")
        username_to_add = st.text_input("Enter username of user to add to group")
        add_user_button = st.form_submit_button("Add User to Group")
        
        if add_user_button and group_name and username_to_add:
            result = add_user_to_group(group_name, username_to_add, st.session_state['current_user']['uid'])
            st.success(result)  # Display the result of the attempt to add a user


def my_posts_page(user_id):
    st.title("My Posts")

    user_posts = get_user_posts(user_id)

    if user_posts:
        for post in user_posts:
            with st.container():
                st.write(f"{post['text']}")
                st.write(f"Posted on: {post['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                if st.button("Delete", key=post['post_id']):
                    delete_post(post['post_id'])
                    st.experimental_rerun()  # Refresh the page to reflect the deletion
    else:
        st.write("You haven't posted anything yet.")


def main():
    st.sidebar.title("Navigation")
    if 'current_user' in st.session_state and st.session_state['current_user']:
        page = st.sidebar.radio("Go to", ("Dashboard", "Group Management", "My Posts", "Logout"))
        
        if page == "Dashboard":
            dashboard_page()
        elif page == "Group Management":
            group_management_page()
        elif page == "My Posts":
            my_posts_page(st.session_state['current_user']['uid'])
        elif page == "Logout":
            del st.session_state['current_user']
            st.experimental_rerun()
    else:
        page = st.sidebar.radio("Go to", ("Login", "Sign Up"))
        if page == "Login":
            login_page()
        elif page == "Sign Up":
            signup_page()

if __name__ == "__main__":
    main()