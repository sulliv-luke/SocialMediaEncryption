import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
import datetime
import requests
import os                         
import base64                                                                                                                                                                                 
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from gen_keys import generate_key_pair
from encrypt_decrypt import encrypt_for_group_members, decrypt_message_with_private_key
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

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

from cryptography.hazmat.primitives import serialization

def get_group_member_public_keys(user_id):
    # Fetch all groups where user_id is a member
    groups_ref = db.collection('groups')
    user_groups = groups_ref.where('members', 'array_contains', user_id).get()
    print(f"USER GROUPS LENGTH: {len(user_groups)}")
    user_ids = set()
    for group in user_groups:
        members = group.to_dict().get('members', [])
        user_ids.update(members)

    # Remove the original user_id to avoid encrypting for oneself
    user_ids.discard(user_id)

    # Fetch public keys for all these users
    users_ref = db.collection('users')
    group_public_keys = {}
    for uid in user_ids:
        user_doc = users_ref.document(uid).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            public_key_serialized = user_data.get('public key')
            
            # Assuming public keys are stored in PEM format
            public_key = serialization.load_pem_public_key(
                public_key_serialized.encode(),
                backend=default_backend()
            )

            group_public_keys[uid] = public_key

    return group_public_keys

def create_post(user_id, text):
    # Add a new post to the "posts" collection
    posts_ref = db.collection('posts')
    keys = get_group_member_public_keys(st.session_state['current_user']['uid'])
    encrypted_msg, encrypted_keys = encrypt_for_group_members(keys, text)
    posts_ref.add({'user_id': user_id, 'encrypted_text': encrypted_msg, 'encrypted_keys': encrypted_keys, 'timestamp': datetime.datetime.now()})


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
        public_key_pem = generate_key_pair(user_id)
        doc_ref = db.collection(u'users').document(user_id)
        doc_ref.set({
            u'username': username,
            u'email': email,
            u'public key': public_key_pem.decode()
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
    if existing_group:
        return None # Group already exists
    
    admin_already_has_group = groups_ref.where('admin', '==', admin_id).get()
    if admin_already_has_group:
        return None # Admin already has group
    
    _, group_doc_ref = groups_ref.add({  # Unpack the tuple to get the DocumentReference
        'name': group_name,
        'admin': admin_id,
        'members': [admin_id]
    })
    return group_doc_ref.id  # Now correctly getting the ID from the DocumentReference


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
            post_data = post.to_dict()
            post_data['post_id'] = post.id  # Include the document ID as 'post_id'
            posts.append(post_data)

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

def get_excluded_user_ids(user_id):
    groups_ref = db.collection('groups')
    groups = groups_ref.where('members', 'array_contains', user_id).get()

    excluded_user_ids = set([user_id])  # Start with the current user's ID
    for group in groups:
        members = group.to_dict().get('members', [])
        excluded_user_ids.update(members)

    return excluded_user_ids


def get_recent_posts(limit=50, exclude_user_ids=None):
    posts_ref = db.collection('posts')
    recent_posts_query = posts_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
    recent_posts = recent_posts_query.stream()

    posts_list = []
    for post in recent_posts:
        post_data = post.to_dict()
        post_data['post_id'] = post.id
        
        # Exclude posts by the current user and their group members
        if exclude_user_ids and post_data['user_id'] not in exclude_user_ids:
            posts_list.append(post_data)

    return posts_list




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
    st.write("### Posts from people in your groups")
    posts = get_group_posts(user_id)
    for post in posts:
        post_user_details = db.collection('users').document(post['user_id']).get()
        post_username = post_user_details.to_dict().get('username')
    
        # Create a unique key for each post's decryption state
        decrypt_key = f"decrypt_{post['post_id']}"
        # Create a container for each post
        with st.container():
            # Use columns to layout the "Posted by user" and the decrypt button
            col1, col2 = st.columns([8, 2])
            with col1:
                st.markdown(f"**Posted by:** {post_username}")
            with col2:
                # Assuming you have a way to properly decode or handle `post['encrypted_text']`
                if st.button("Decrypt", key=post['post_id']):
                    decrypted_text = decrypt_message_with_private_key(post['encrypted_text'].decode(), post['encrypted_keys'][user_id], user_id)
                    # Output decrypted text in a new container or adjust layout as needed
                    st.session_state[decrypt_key] = decrypted_text
        
            # Display the encrypted post text in the middle of the container
            st.write(f"**Encrypted post:** {post['encrypted_text'].decode()}")

            # Check if the decrypted text should be displayed
            if decrypt_key in st.session_state and st.session_state[decrypt_key]:
                st.write(f"**Decrypted post:** {st.session_state[decrypt_key]}")


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
                st.write(f"{post['encrypted_text'].decode()}")
                st.write(f"Posted on: {post['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                if st.button("Delete", key=post['post_id']):
                    delete_post(post['post_id'])
                    st.rerun()  # Refresh the page to reflect the deletion
    else:
        st.write("You haven't posted anything yet.")

def explore_page(user_id):
    st.title("Explore Recent Posts")

    # Get user IDs to exclude: the current user and their group members
    exclude_user_ids = get_excluded_user_ids(user_id)

    # Fetch recent posts excluding those user IDs
    recent_posts = get_recent_posts(limit=50, exclude_user_ids=exclude_user_ids)

    for post in recent_posts:
        post_user_details = db.collection('users').document(post['user_id']).get()
        post_username = post_user_details.to_dict().get('username', 'Unknown user')
        
        # Create a container for each post with an outline
        with st.container():
            col1, col2 = st.columns([8, 2])
            with col1:
                st.markdown(f"**Posted by:** {post_username}")
            with col2:
                st.markdown(f"**Post ID:** {post['post_id']}")
                
            st.write(f"**Encrypted post:** {post['encrypted_text']}")
            st.markdown("---")  # Add a horizontal line for visual separation



def main():
    st.sidebar.title("Navigation")
    if 'current_user' in st.session_state and st.session_state['current_user']:
        page = st.sidebar.radio("Go to", ("Dashboard", "Group Management", "Explore", "My Posts", "Logout"))
        
        if page == "Dashboard":
            dashboard_page()
        elif page == "Explore":
            explore_page(st.session_state['current_user']['uid'])
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
