import datetime
from firebase_admin import firestore
from firebase_admin_utils import db
import streamlit as st
from group_utils import get_group_member_public_keys, encrypt_for_group_members

def create_post(user_id, text):
    # Add a new post to the "posts" collection
    posts_ref = db.collection('posts')
    keys = get_group_member_public_keys(st.session_state['current_user']['uid'])
    encrypted_msg, encrypted_keys = encrypt_for_group_members(keys, text)
    posts_ref.add({'user_id': user_id, 'encrypted_text': encrypted_msg, 'encrypted_keys': encrypted_keys, 'timestamp': datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")})

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