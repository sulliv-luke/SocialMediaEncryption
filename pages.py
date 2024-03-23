import streamlit as st                                                                                                                                                                        
from encrypt_decrypt import decrypt_message_with_private_key
from firebase_admin_utils import authenticate_user, db, create_user, save_user_details
from group_utils import create_group, add_user_to_group, remove_user_from_group, get_group_posts
from post_utils import create_post, delete_post, get_excluded_user_ids, get_user_posts, get_recent_posts

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
                st.write(f"Posted at: {post['timestamp']}")
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

            st.markdown("---")  # Add a horizontal line for visual separation


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

    with st.form("remove_user_from_group"):
        group_name_remove = st.text_input("Enter group name to remove user from", key="group_name_remove")
        username_to_remove = st.text_input("Enter username of user to remove from group", key="username_to_remove")
        remove_user_button = st.form_submit_button("Remove User from Group")
        
        if remove_user_button and group_name_remove and username_to_remove:
            result = remove_user_from_group(group_name_remove, username_to_remove, st.session_state['current_user']['uid'])
            st.success(result)  # Display the result of the attempt to remove a user


def my_posts_page(user_id):
    st.title("My Posts")

    user_posts = get_user_posts(user_id)

    if user_posts:
        for post in user_posts:
            with st.container():
                # Generate a unique key for decryption button for each post
                decrypt_key = f"decrypt_{post['post_id']}"
                
                # Display the post's encrypted text
                st.write(f"**Encrypted Post:** {post['encrypted_text'].decode()}")
                
                # Layout for Post Details and Buttons
                col1, col2, col3 = st.columns([6,3,3])
                
                with col1:
                    # Display the timestamp for each post
                    st.write(f"Posted at: {post['timestamp']}")
                
                with col2:
                    # Button for decrypting the post
                    if st.button("Decrypt", key=f"{post['post_id']}_decrypt"):
                        # Assuming the decrypt_message_with_private_key function and necessary keys are available
                        decrypted_text = decrypt_message_with_private_key(post['encrypted_text'].decode(), post['encrypted_keys'][user_id], user_id)
                        st.session_state[decrypt_key] = decrypted_text
                
                with col3:
                    # Button for deleting the post
                    if st.button("Delete", key=post['post_id']):
                        delete_post(post['post_id'])
                        st.experimental_rerun()  # Refresh the page to reflect the deletion
                
                # Check if the post has been decrypted and display it
                if decrypt_key in st.session_state and st.session_state[decrypt_key]:
                    st.write(f"**Decrypted Post:** {st.session_state[decrypt_key]}")

                st.markdown("---")  # Add a horizontal line for visual separation
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
            col1, col2 = st.columns([8, 1])
            with col1:
                st.markdown(f"**Posted by:** {post_username}")
                st.markdown(f"**Posted at:** {post['timestamp']}")
                
            st.write(f"**Encrypted post:** {post['encrypted_text'].decode()}")
            st.markdown("---")  # Add a horizontal line for visual separation