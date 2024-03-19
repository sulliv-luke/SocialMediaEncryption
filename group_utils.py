from encrypt_decrypt import encrypt_for_group_members, decrypt_message_with_private_key
from firebase_admin_utils import db
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from firebase_admin import firestore

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
    user_to_add_pub_key = user_docs[0].to_dict().get('certificate')
    
    # Load the user's public key
    certificate = x509.load_pem_x509_certificate(
        user_to_add_pub_key,
        backend=default_backend()
    )
    user_to_add_public_key = certificate.public_key()
    
    # Find the group and add the user to it
    groups_ref = db.collection('groups')
    group_doc = groups_ref.where('name', '==', group_name).where('admin', '==', admin_id).get()
    
    if not group_doc:
        return "Group not found or you're not the admin"
    
    group = group_doc[0]
    if user_to_add_id in group.to_dict()['members']:
        return "User already in the group"
    
    # Add user to the group
    groups_ref.document(group.id).update({
        'members': firestore.ArrayUnion([user_to_add_id])
    })
    
    # Re-encrypt existing posts for the new group member
    posts_ref = db.collection('posts')
    group_members = group.to_dict()['members'] + [user_to_add_id]  # Include the new member in the encryption
    
    for member_id in group_members:
        user_posts = posts_ref.where('user_id', '==', member_id).stream()
        for post in user_posts:
            post_data = post.to_dict()
            # Assuming post_data contains 'encrypted_text' and 'encrypted_keys'
            encrypted_msg = post_data['encrypted_text']
            encrypted_keys = post_data['encrypted_keys']
            
            # Fetch public keys of all current members including the new one
            all_member_keys = get_group_member_public_keys(admin_id)  # Might need to adjust this to ensure it includes the new user
            all_member_keys[user_to_add_id] = user_to_add_public_key
            
            # Re-encrypt the message for all group members
            new_encrypted_msg, new_encrypted_keys = encrypt_for_group_members(all_member_keys, decrypt_message_with_private_key(encrypted_msg, encrypted_keys[admin_id], admin_id))
            
            # Update the post with new encrypted keys
            posts_ref.document(post.id).update({'encrypted_keys': new_encrypted_keys})
            posts_ref.document(post.id).update({'encrypted_text': new_encrypted_msg})
    
    return "User added successfully and posts updated"

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
    #user_ids.discard(user_id)

    # Fetch certificates for all these users and extract public keys
    users_ref = db.collection('users')
    group_member_public_keys = {}
    for uid in user_ids:
        user_doc = users_ref.document(uid).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            certificate_pem = user_data.get('certificate')


            # Load the X.509 certificate
            certificate = x509.load_pem_x509_certificate(
                certificate_pem,
                backend=default_backend()
            )

            # Extract the public key from the certificate
            public_key = certificate.public_key()

            group_member_public_keys[uid] = public_key

    return group_member_public_keys

def remove_user_from_group(group_name, username_to_remove, admin_id):
    # Find the user ID of the user to remove
    users_ref = db.collection('users')
    user_docs = users_ref.where('username', '==', username_to_remove).get()
    if not user_docs:
        return "User not found"
    
    user_to_remove_id = user_docs[0].id
    
    # Find the group and remove the user from it
    groups_ref = db.collection('groups')
    group_doc = groups_ref.where('name', '==', group_name).where('admin', '==', admin_id).get()
    
    if not group_doc:
        return "Group not found or you're not the admin"
    
    group = group_doc[0]
    if user_to_remove_id not in group.to_dict()['members']:
        return "User is not in the group"
    
    # Remove the user from the group
    groups_ref.document(group.id).update({
        'members': firestore.ArrayRemove([user_to_remove_id])
    })

    # Update group_members to exclude the removed user
    group_members = [member for member in group.to_dict()['members'] if member != user_to_remove_id]

    # Fetch all posts made by the group members
    posts_ref = db.collection('posts')
    group_posts = posts_ref.where('user_id', 'in', group_members).stream()

    for post in group_posts:
        post_data = post.to_dict()
        encrypted_message = post_data['encrypted_text']
        encrypted_keys = post_data['encrypted_keys']

        # Check if the user to remove's encrypted key exists in the post
        if user_to_remove_id in encrypted_keys:
            # Remove the user's encrypted key from the post
            del encrypted_keys[user_to_remove_id]

        # Decrypt the message using the admin's private key for re-encryption
        decrypted_message = decrypt_message_with_private_key(
            encrypted_message,
            encrypted_keys[admin_id],
            admin_id
        )

        # Fetch public keys of all remaining members
        remaining_member_keys = get_group_member_public_keys(admin_id)

        # Re-encrypt the message for all remaining group members
        new_encrypted_msg, new_encrypted_keys = encrypt_for_group_members(remaining_member_keys, decrypted_message)

        # Update the post with the new encrypted message and keys
        posts_ref.document(post.id).update({
            'encrypted_text': new_encrypted_msg,
            'encrypted_keys': new_encrypted_keys
        })

    return "User removed successfully and posts updated for remaining group members"

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